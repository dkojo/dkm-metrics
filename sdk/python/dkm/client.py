"""dkm-metrics Python SDK.

    dkm = DKM(api_key="...")
    v = dkm.variant("support-prompt", user_id="u123", default={"prompt": "You are helpful."})
    with dkm.trace(v) as t:                 # records latency_ms and error automatically
        resp = call_llm(v.config["prompt"])
        t.record(tokens=resp.usage.total_tokens)
    dkm.track(v, "thumbs_up", 1)
    dkm.judge(v, helpfulness, input=question, output=reply)   # optional LLM-as-judge score (see judge.py)

Design rules:
- Variant assignment is local and deterministic (hash of experiment + user): no network on the hot path.
- Events are queued and sent in batches by a background thread.
- The SDK never raises into your app because of network problems; it logs and falls back.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .judge import Judge

log = logging.getLogger("dkm")

DEFAULT_BASE_URL = "http://localhost:8000"
MAX_QUEUE = 10_000


def bucket(experiment: str, user_id: str) -> float:
    """Deterministic number in [0, 1) for this (experiment, user) pair."""
    digest = hashlib.sha256(f"{experiment}:{user_id}".encode()).hexdigest()
    return int(digest[:15], 16) / 16**15


def assign(experiment: str, user_id: str, variants: list[dict]) -> dict:
    """Pick a variant by weight. Same inputs always give the same variant."""
    total = sum(v["weight"] for v in variants)
    point = bucket(experiment, user_id) * total
    cumulative = 0.0
    for v in variants:
        cumulative += v["weight"]
        if point < cumulative:
            return v
    return variants[-1]


@dataclass
class Assignment:
    """The variant a user got. `tracked` is False when falling back to the default config."""

    experiment: str
    user_id: str
    variant: str | None
    config: dict[str, Any] = field(default_factory=dict)
    tracked: bool = True

    def __getitem__(self, key: str) -> Any:
        return self.config[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


class Trace:
    """Context manager that times a block and records metrics for one assignment."""

    def __init__(self, client: DKM, assignment: Assignment):
        self._client = client
        self._assignment = assignment
        self._metrics: dict[str, float] = {}

    def record(self, **metrics: float) -> None:
        self._metrics.update(metrics)

    def __enter__(self) -> Trace:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._metrics.setdefault("latency_ms", (time.perf_counter() - self._start) * 1000)
        self._metrics.setdefault("error", 1.0 if exc_type else 0.0)
        for name, value in self._metrics.items():
            self._client.track(self._assignment, name, value)
        return False  # never swallow exceptions


class DKM:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        refresh_interval: float = 30.0,
        flush_interval: float = 2.0,
        batch_size: int = 100,
        timeout: float = 5.0,
        enabled: bool = True,
        judge_workers: int = 4,
    ):
        self.api_key = api_key or os.getenv("DKM_API_KEY", "")
        self.base_url = (base_url or os.getenv("DKM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.refresh_interval = refresh_interval
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.timeout = timeout
        self.enabled = enabled and bool(self.api_key)
        if enabled and not self.api_key:
            log.warning("dkm: no API key (set DKM_API_KEY); running with defaults, not tracking")

        self._experiments: dict[str, dict] = {}
        self._config_loaded_at = 0.0
        self._config_lock = threading.Lock()
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=MAX_QUEUE)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self.judge_workers = judge_workers
        self._judge_pool: ThreadPoolExecutor | None = None
        self._judge_lock = threading.Lock()

    # ---------- public API ----------

    def variant(self, experiment: str, user_id: str, default: dict | None = None) -> Assignment:
        """Return the variant for this user. Falls back to `default` (untracked) if the
        experiment is unknown, not running, or the server is unreachable."""
        user_id = str(user_id)
        if self.enabled:
            self._ensure_started()
            exp = self._experiments.get(experiment)
            if exp and exp["variants"]:
                v = assign(experiment, user_id, exp["variants"])
                return Assignment(experiment, user_id, v["key"], dict(v["config"]))
        return Assignment(experiment, user_id, None, dict(default or {}), tracked=False)

    def track(self, assignment: Assignment, metric: str, value: float | bool) -> None:
        """Record one metric value for the user's variant."""
        if not (self.enabled and assignment.tracked):
            return
        event = {
            "experiment": assignment.experiment,
            "variant": assignment.variant,
            "user_id": assignment.user_id,
            "metric": metric,
            "value": float(value),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            log.warning("dkm: event queue full, dropping event")

    def trace(self, assignment: Assignment) -> Trace:
        return Trace(self, assignment)

    def judge(
        self,
        assignment: Assignment,
        judge: Judge,
        *,
        input: str,
        output: str,
        reference: str | None = None,
    ) -> Future | None:
        """Score `output` with an LLM judge in the background and record it as `judge.metric`.
        Returns a Future (resolving to the Score, or None), or None when not tracking:
        no judge call is made (or paid for) for untracked assignments."""
        if not (self.enabled and assignment.tracked):
            return None
        with self._judge_lock:
            if self._judge_pool is None:
                self._judge_pool = ThreadPoolExecutor(max_workers=self.judge_workers, thread_name_prefix="dkm-judge")
            pool = self._judge_pool

        def run():
            result = judge.score(input, output, reference)
            if result is not None:
                self.track(assignment, judge.metric, result.value)
            return result

        return pool.submit(run)

    def flush(self) -> None:
        """Send all queued events now."""
        while not self._queue.empty():
            batch = []
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if batch:
                self._request("POST", "/api/events", {"events": batch})

    def refresh(self) -> None:
        """Fetch the latest experiment config from the server."""
        data = self._request("GET", "/api/sdk/config")
        if data is not None:
            with self._config_lock:
                self._experiments = data.get("experiments", {})
                self._config_loaded_at = time.monotonic()

    def close(self) -> None:
        if self._judge_pool is not None:
            self._judge_pool.shutdown(wait=True)  # let pending judgments record their scores
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=self.timeout)
        self.flush()

    # ---------- internals ----------

    def _ensure_started(self) -> None:
        if self._worker:
            return
        with self._worker_lock:
            if self._worker:
                return
            self.refresh()  # blocking once, so the first call already sees experiments
            self._worker = threading.Thread(target=self._run, name="dkm-worker", daemon=True)
            self._worker.start()
            atexit.register(self.close)

    def _run(self) -> None:
        while not self._stop.wait(self.flush_interval):
            self.flush()
            if time.monotonic() - self._config_loaded_at >= self.refresh_interval:
                self.refresh()

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | None:
        req = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"null")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            log.warning("dkm: %s %s failed: %s", method, path, e)
            return None
