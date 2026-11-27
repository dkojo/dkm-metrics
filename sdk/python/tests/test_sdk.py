import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections import Counter

import pytest

from dkm import DKM, assign


def test_assignment_is_deterministic_and_weighted():
    variants = [{"key": "a", "weight": 1}, {"key": "b", "weight": 3}]
    assert assign("exp", "user-1", variants) == assign("exp", "user-1", variants)
    counts = Counter(assign("exp", f"u{i}", variants)["key"] for i in range(20_000))
    assert 0.23 < counts["a"] / 20_000 < 0.27


def test_no_api_key_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DKM_API_KEY", raising=False)
    dkm = DKM()
    v = dkm.variant("exp", "u1", default={"prompt": "hi"})
    assert v.variant is None and not v.tracked and v["prompt"] == "hi"
    dkm.track(v, "m", 1)  # no-op, must not raise


def test_unreachable_server_falls_back():
    dkm = DKM(api_key="k", base_url="http://127.0.0.1:1", timeout=0.5)
    v = dkm.variant("exp", "u1", default={"model": "small"})
    assert not v.tracked and v["model"] == "small"
    dkm.close()


def test_trace_records_latency_and_error():
    dkm = DKM(api_key="k", base_url="http://127.0.0.1:1", timeout=0.5)
    from dkm import Assignment

    a = Assignment("exp", "u1", "b", {})
    with pytest.raises(ValueError):
        with dkm.trace(a) as t:
            t.record(tokens=42)
            raise ValueError("boom")
    events = {e["metric"]: e["value"] for e in list(dkm._queue.queue)}
    assert events["tokens"] == 42 and events["error"] == 1.0 and events["latency_ms"] >= 0


# ---------- end-to-end against a real server ----------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(tmp_path):
    """Run the real dkm server in a subprocess (skipped if it isn't installed)."""
    pytest.importorskip("dkm_server")
    port = _free_port()
    env = {
        **os.environ,
        "DKM_DATABASE_URL": f"sqlite:///{(tmp_path / 'e2e.db').as_posix()}",
        "DKM_API_KEY": "e2e-key",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dkm_server.main:app", "--port", str(port), "--log-level", "error"],
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while True:
        try:
            urllib.request.urlopen(base + "/health", timeout=1)
            break
        except OSError:
            if proc.poll() is not None or time.monotonic() > deadline:
                proc.kill()
                pytest.fail("dkm server failed to start")
            time.sleep(0.1)
    yield base
    proc.terminate()
    proc.wait(10)


def _api(base, method, path, body=None):
    req = urllib.request.Request(
        base + path, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer e2e-key", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"null")


def test_end_to_end(server):
    _api(server, "POST", "/api/experiments", {
        "key": "prompt", "name": "Prompt test",
        "variants": [{"key": "control", "config": {"p": "A"}}, {"key": "new", "config": {"p": "B"}}],
    })
    _api(server, "PATCH", "/api/experiments/prompt", {"status": "running"})

    dkm = DKM(api_key="e2e-key", base_url=server)
    seen = set()
    for i in range(50):
        v = dkm.variant("prompt", f"user{i}")
        assert v.tracked and v["p"] in ("A", "B")
        seen.add(v.variant)
        dkm.track(v, "thumbs_up", i % 2)
    assert seen == {"control", "new"}
    dkm.close()

    res = _api(server, "GET", "/api/experiments/prompt/results")
    assert sum(res["users"].values()) == 50
    assert res["metrics"][0]["metric"] == "thumbs_up"
