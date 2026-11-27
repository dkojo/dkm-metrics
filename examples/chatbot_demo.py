"""Demo: A/B test two system prompts for a support chatbot.

Uses a fake LLM so it runs without any model API key. Swap `fake_llm` for your
real model call (Claude, etc.) and it works the same way.

    DKM_API_KEY=dkm_local_dev_key python examples/chatbot_demo.py
"""

import json
import os
import random
import time
import urllib.error
import urllib.request

from dkm import DKM

BASE_URL = os.getenv("DKM_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("DKM_API_KEY", "dkm_local_dev_key")
EXPERIMENT = "support-prompt"


def setup_experiment() -> None:
    """Create and start the experiment through the REST API (normally you'd use the dashboard)."""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    def call(method, path, body=None):
        req = urllib.request.Request(
            BASE_URL + path, method=method, headers=headers,
            data=json.dumps(body).encode() if body else None,
        )
        return urllib.request.urlopen(req)

    try:
        call("POST", "/api/experiments", {
            "key": EXPERIMENT,
            "name": "Support bot system prompt",
            "description": "Does a warmer, more concise prompt get more thumbs-up?",
            "primary_metric": "thumbs_up",
            "variants": [
                {"key": "control", "config": {"model": "claude-haiku-5-5", "prompt": "You are a helpful support agent."}},
                {"key": "concise", "config": {"model": "claude-haiku-5-5", "prompt": "You are a warm support agent. Answer in 2-3 sentences."}},
            ],
        })
        print(f"Created experiment '{EXPERIMENT}'")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise
    call("PATCH", f"/api/experiments/{EXPERIMENT}", {"status": "running"})


def fake_llm(model: str, prompt: str, question: str) -> dict:
    """Pretend model call. The 'concise' prompt is faster and a bit better liked."""
    concise = "2-3 sentences" in prompt
    tokens = int(random.gauss(90 if concise else 220, 25))
    time.sleep(0.001)
    return {
        "text": f"[{model}] answer to: {question}",
        "tokens": max(tokens, 10),
        "latency": random.gauss(600 if concise else 900, 120),
        "liked": random.random() < (0.62 if concise else 0.50),
    }


def main(users: int = 800) -> None:
    setup_experiment()
    dkm = DKM(api_key=API_KEY, base_url=BASE_URL)

    for i in range(users):
        user_id = f"user-{i}"
        v = dkm.variant(EXPERIMENT, user_id, default={"model": "claude-haiku-5-5", "prompt": "You are helpful."})

        with dkm.trace(v) as t:
            reply = fake_llm(v["model"], v["prompt"], "How do I reset my password?")
            # trace() measures real latency; we override it with the simulated one for the demo
            t.record(latency_ms=reply["latency"], tokens=reply["tokens"], cost=reply["tokens"] * 0.000004)

        dkm.track(v, "thumbs_up", reply["liked"])

    dkm.close()  # flush remaining events
    print(f"Sent events for {users} users. Open http://localhost:3000/experiments/{EXPERIMENT}")


if __name__ == "__main__":
    main()
