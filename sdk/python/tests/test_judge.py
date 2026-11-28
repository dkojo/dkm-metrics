import json
from types import SimpleNamespace

from dkm import DKM, Assignment
from dkm.judge import Judge


class FakeMessages:
    """Stands in for client.beta.messages: records requests, returns a canned response."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response
        self.error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(response=None, error=None):
    messages = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def reply(payload, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(payload))],
    )


def test_scores_and_sends_a_well_formed_request():
    client, messages = fake_client(reply({"reasoning": "Clear and correct.", "score": 4}))
    judge = Judge("helpfulness", "Is it helpful?", client=client)
    s = judge.score("How do I reset my password?", "Click 'Forgot password'.", reference="Use the reset link.")
    assert s.value == 4.0 and s.reasoning == "Clear and correct."

    req = messages.calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["output_config"]["effort"] == "medium"
    schema = req["output_config"]["format"]["schema"]
    assert schema["properties"]["score"]["enum"] == [1, 2, 3, 4, 5]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Is it helpful?" in req["system"][0]["text"]
    user = req["messages"][0]["content"]
    assert "<input>" in user and "<response>" in user and "<reference_answer>" in user


def test_pass_fail_scale():
    client, messages = fake_client(reply({"reasoning": "ok", "score": True}))
    judge = Judge("on_topic", "Stays on topic?", scale="pass_fail", client=client)
    assert judge.score("q", "a").value == 1.0
    assert messages.calls[0]["output_config"]["format"]["schema"]["properties"]["score"] == {"type": "boolean"}


def test_no_fallbacks_for_models_without_support():
    client, messages = fake_client(reply({"reasoning": "ok", "score": 3}))
    Judge("m", "c", model="claude-haiku-5-5", client=client).score("q", "a")
    assert "fallbacks" not in messages.calls[0] and "betas" not in messages.calls[0]


def test_refusal_truncation_and_errors_give_no_score():
    for resp in (reply({}, stop_reason="refusal"), reply({}, stop_reason="max_tokens")):
        client, _ = fake_client(resp)
        assert Judge("m", "c", client=client).score("q", "a") is None
    client, _ = fake_client(error=RuntimeError("network down"))
    assert Judge("m", "c", client=client).score("q", "a") is None
    client, _ = fake_client(SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="not json")]))
    assert Judge("m", "c", client=client).score("q", "a") is None


def test_dkm_judge_records_metric_in_background():
    client, _ = fake_client(reply({"reasoning": "good", "score": 5}))
    judge = Judge("helpfulness", "Is it helpful?", client=client)
    dkm = DKM(api_key="k", base_url="http://127.0.0.1:1", timeout=0.2)
    a = Assignment("exp", "u1", "b", {})

    future = dkm.judge(a, judge, input="q", output="a")
    assert future.result(timeout=5).value == 5.0
    events = list(dkm._queue.queue)
    assert [(e["metric"], e["value"], e["variant"]) for e in events] == [("helpfulness", 5.0, "b")]


def test_untracked_assignment_makes_no_judge_call():
    client, messages = fake_client(reply({"reasoning": "x", "score": 1}))
    dkm = DKM(api_key="k", base_url="http://127.0.0.1:1")
    untracked = Assignment("exp", "u1", None, {}, tracked=False)
    assert dkm.judge(untracked, Judge("m", "c", client=client), input="q", output="a") is None
    assert messages.calls == []


def test_close_waits_for_pending_judgments():
    import threading

    gate = threading.Event()

    class Slow(FakeMessages):
        def create(self, **kwargs):
            gate.wait(5)
            return reply({"reasoning": "late", "score": 2})

    client = SimpleNamespace(beta=SimpleNamespace(messages=Slow()))
    dkm = DKM(api_key="k", base_url="http://127.0.0.1:1", timeout=0.2)
    dkm.judge(Assignment("exp", "u1", "b", {}), Judge("m", "c", client=client), input="q", output="a")
    flushed = []
    dkm.flush = lambda: flushed.extend(list(dkm._queue.queue))  # capture instead of sending
    threading.Timer(0.2, gate.set).start()
    dkm.close()
    assert [e["value"] for e in flushed] == [2.0]
