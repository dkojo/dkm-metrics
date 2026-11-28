"""Demo: score each variant's replies with an LLM judge.

Needs a running dkm server (see chatbot_demo.py) and Anthropic credentials:

    pip install -e "sdk/python[judge]"
    export ANTHROPIC_API_KEY=...          # or: ant auth login
    DKM_API_KEY=dkm_local_dev_key python examples/judge_demo.py

This makes real Claude calls (one per reply judged), so it costs a little money.
The "helpfulness" metric then shows up on the support-prompt experiment page.
"""

import os

from dkm import DKM
from dkm.judge import Judge

from chatbot_demo import EXPERIMENT, setup_experiment

QUESTIONS = [
    "How do I reset my password?",
    "Can I change the email on my account?",
    "Why was I charged twice this month?",
]

# Canned replies per variant, standing in for your real model calls.
REPLIES = {
    "control": "Please consult the documentation for information about account settings.",
    "concise": "Go to Settings > Account, click 'Edit', and save. If you get stuck, reply here and I'll help.",
}


def main(users: int = 12) -> None:
    setup_experiment()
    dkm = DKM(api_key=os.getenv("DKM_API_KEY", "dkm_local_dev_key"))
    helpfulness = Judge(
        metric="helpfulness",
        criteria="Does the reply directly and correctly help the user with their question, "
        "with concrete steps where relevant?",
        # model="claude-haiku-5-5",  # a cheaper judge, if you prefer
    )

    for i in range(users):
        v = dkm.variant(EXPERIMENT, f"judge-user-{i}", default={"prompt": "You are helpful."})
        question = QUESTIONS[i % len(QUESTIONS)]
        reply = REPLIES.get(v.variant or "control", REPLIES["control"])
        dkm.judge(v, helpfulness, input=question, output=reply)  # runs in the background

    dkm.close()  # waits for the judgments, then flushes
    print(f"Judged {users} replies. See 'helpfulness' at http://localhost:3000/experiments/{EXPERIMENT}")


if __name__ == "__main__":
    main()
