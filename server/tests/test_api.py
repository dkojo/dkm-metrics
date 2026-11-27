import os
import random

os.environ["DKM_DATABASE_URL"] = "sqlite:///./test_dkm.db"
os.environ["DKM_API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient

from dkm_server.db import Base, engine
from dkm_server.main import app

AUTH = {"Authorization": "Bearer test-key"}

EXPERIMENT = {
    "key": "support-prompt",
    "name": "Support bot prompt",
    "primary_metric": "thumbs_up",
    "variants": [
        {"key": "control", "config": {"prompt": "You are helpful."}},
        {"key": "friendly", "config": {"prompt": "You are warm and helpful."}},
    ],
}


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def test_requires_api_key(client):
    assert client.get("/api/experiments").status_code == 401
    assert client.get("/api/experiments", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_experiment_lifecycle(client):
    r = client.post("/api/experiments", json=EXPERIMENT, headers=AUTH)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"

    assert client.post("/api/experiments", json=EXPERIMENT, headers=AUTH).status_code == 409

    # Drafts are not served to the SDK
    assert client.get("/api/sdk/config", headers=AUTH).json()["experiments"] == {}

    client.patch("/api/experiments/support-prompt", json={"status": "running"}, headers=AUTH)
    cfg = client.get("/api/sdk/config", headers=AUTH).json()["experiments"]
    assert [v["key"] for v in cfg["support-prompt"]["variants"]] == ["control", "friendly"]

    assert client.delete("/api/experiments/support-prompt", headers=AUTH).status_code == 204
    assert client.get("/api/experiments/support-prompt", headers=AUTH).status_code == 404


def test_validation(client):
    bad = {**EXPERIMENT, "variants": EXPERIMENT["variants"][:1]}
    assert client.post("/api/experiments", json=bad, headers=AUTH).status_code == 422
    bad = {**EXPERIMENT, "key": "Has Spaces"}
    assert client.post("/api/experiments", json=bad, headers=AUTH).status_code == 422


def test_ingest_and_results(client):
    client.post("/api/experiments", json=EXPERIMENT, headers=AUTH)
    client.patch("/api/experiments/support-prompt", json={"status": "running"}, headers=AUTH)

    rng = random.Random(0)
    events = []
    for i in range(400):
        variant = "control" if i % 2 == 0 else "friendly"
        rate = 0.4 if variant == "control" else 0.7
        events.append({"experiment": "support-prompt", "variant": variant, "user_id": f"u{i}",
                       "metric": "thumbs_up", "value": 1.0 if rng.random() < rate else 0.0})
        events.append({"experiment": "support-prompt", "variant": variant, "user_id": f"u{i}",
                       "metric": "latency_ms", "value": rng.gauss(800, 100)})
    events.append({"experiment": "support-prompt", "variant": "ghost", "user_id": "x",
                   "metric": "thumbs_up", "value": 1})

    r = client.post("/api/events", json={"events": events}, headers=AUTH)
    assert r.json() == {"accepted": 800, "rejected": 1}

    res = client.get("/api/experiments/support-prompt/results", headers=AUTH).json()
    assert res["users"] == {"control": 200, "friendly": 200}
    primary = res["metrics"][0]
    assert primary["metric"] == "thumbs_up" and primary["binary"]
    friendly = next(v for v in primary["variants"] if v["variant"] == "friendly")
    assert friendly["comparison"]["verdict"] == "better"
    assert friendly["comparison"]["test"] == "proportion"

    latency = next(m for m in res["metrics"] if m["metric"] == "latency_ms")
    assert latency["lower_is_better"]
    lf = next(v for v in latency["variants"] if v["variant"] == "friendly")
    assert lf["comparison"]["verdict"] in ("no_difference", "better", "worse")


def test_events_rejected_when_not_running(client):
    client.post("/api/experiments", json=EXPERIMENT, headers=AUTH)
    ev = {"experiment": "support-prompt", "variant": "control", "user_id": "u", "metric": "m", "value": 1}
    assert client.post("/api/events", json={"events": [ev]}, headers=AUTH).json()["accepted"] == 0
