# dkm-metrics

A/B test any part of your LLM application (prompts, models, parameters, RAG settings, whole chains) so you can ship faster and with higher quality.

```
 Your LLM app                      dkm-metrics
┌──────────────────┐   config    ┌──────────────────────────┐
│  dkm SDK         │◄────────────│  server/  (FastAPI)      │
│  - variant()     │             │  - experiments API       │
│  - trace/track() │────────────►│  - event ingest          │
└──────────────────┘   events    │  - stats engine          │
                                 │  SQLite → Postgres       │
                                 └────────────▲─────────────┘
                                              │
                                 ┌────────────┴─────────────┐
                                 │  dashboard/  (Next.js)   │
                                 └──────────────────────────┘
```

## How it works

1. **Create an experiment** in the dashboard. Each variant is a JSON config, e.g. `{"prompt": "...", "model": "..."}`. The first variant is the control.
2. **Ask the SDK for a variant** in your app. Assignment is a deterministic hash of experiment + user, so the same user always gets the same variant. It runs locally, with no network call on the hot path.
3. **Record outcomes.** `dkm.trace()` records `latency_ms` and `error` automatically. Use `t.record()` / `dkm.track()` for anything else: `thumbs_up`, `tokens`, `cost`, ratings, conversions.
4. **Read the verdict.** The dashboard compares each variant to the control: a two-proportion z-test for 0/1 metrics and Welch's t-test for continuous ones, with 95% confidence intervals and an estimate of how many more samples you need.

```python
from dkm import DKM

dkm = DKM()  # reads DKM_API_KEY, DKM_BASE_URL (default http://localhost:8000)

v = dkm.variant("support-prompt", user_id=user.id, default={"prompt": "You are helpful."})
with dkm.trace(v) as t:
    reply = client.messages.create(model=v["model"], system=v["prompt"], ...)
    t.record(tokens=reply.usage.output_tokens)

dkm.track(v, "thumbs_up", user_liked_it)
```

If the experiment isn't running, or the server is unreachable, `variant()` returns your `default` config and tracking becomes a no-op. The SDK never breaks your app.

## LLM-as-judge scoring

Score quality automatically, not just with thumbs-up. A judge asks Claude to rate each reply against your criteria and records the score as an ordinary metric, so the dashboard compares it across variants with no extra setup.

```python
from dkm.judge import Judge   # pip install "dkm[judge]"

helpfulness = Judge(
    metric="helpfulness",
    criteria="Does the reply directly and correctly answer the user's question?",
    scale="1-5",               # or "pass_fail" (tested as a rate)
    # model="claude-haiku-5-5" # default is claude-opus-5-5; pick a cheaper judge if you prefer
)

dkm.judge(v, helpfulness, input=question, output=reply, reference=expected_answer)  # reference is optional
```

- **Never blocks your app:** judging runs in a background thread pool. `dkm.close()` waits for pending judgments before the final flush.
- **Private by design:** it runs in your process with your Anthropic credentials (`ANTHROPIC_API_KEY` or an `ant auth login` profile). Your inputs and outputs go to Claude, never to the dkm server.
- **No fake scores:** if Claude declines, the reply is cut off, or the call fails, no score is recorded (and a warning is logged).
- **Cost:** one Claude call per judged reply. Untracked users (experiment not running) are never judged. To control spend, judge a sample (e.g. `if random.random() < 0.1:`) or use a cheaper `model`.
- Structured outputs guarantee a valid `{reasoning, score}`; with Claude Opus 5.5 / Sonnet 5.5, server-side refusal fallbacks are on; the criteria prompt is marked for prompt caching (it takes effect once a rubric is long enough).

Try it: `python examples/judge_demo.py` (needs Anthropic credentials; makes a few real calls).

## Quick start

**Docker:**
```bash
DKM_DASHBOARD_PASSWORD=pick-a-password docker compose up --build
# dashboard: http://localhost:3000 (sign in with that password)   API: http://localhost:8000/docs
# API key: dkm_local_dev_key (override with DKM_API_KEY=...)
```

**Local dev:**
```bash
# 1. server
cd server
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]" -e ../sdk/python
DKM_API_KEY=dkm_local_dev_key uvicorn dkm_server.main:app --reload

# 2. dashboard (new terminal)
cd dashboard
cp .env.example .env.local      # sets the dashboard password: change-me-locally
npm install && npm run dev

# 3. demo data (new terminal, server venv active)
python examples/chatbot_demo.py
```

Open http://localhost:3000.

## Project layout

| Path | What |
|---|---|
| `server/dkm_server/models.py` | The 4 tables: Project, Experiment, Variant, Event |
| `server/dkm_server/main.py` | REST API |
| `server/dkm_server/stats.py` | Significance tests and verdicts |
| `sdk/python/dkm/client.py` | Python SDK (zero dependencies) |
| `dashboard/` | Next.js dashboard (server components plus server actions; the API key stays server-side) |
| `dashboard/proxy.ts`, `dashboard/lib/session.ts` | Dashboard login: redirects signed-out visitors; signed, httpOnly session cookie |
| `sdk/python/dkm/judge.py` | LLM-as-judge scoring (optional `[judge]` extra) |
| `examples/chatbot_demo.py` | Simulated prompt A/B test |
| `examples/judge_demo.py` | LLM-judge scoring demo (real Claude calls) |

## API

All endpoints take `Authorization: Bearer <api key>`. Interactive docs are at `/docs`.

| Method | Path | |
|---|---|---|
| GET / POST | `/api/experiments` | list / create |
| GET / PATCH / DELETE | `/api/experiments/{key}` | read / update (incl. `status`: draft, running, stopped) / delete |
| GET | `/api/experiments/{key}/results` | per-metric, per-variant stats |
| GET | `/api/sdk/config` | running experiments, for the SDK |
| POST | `/api/events` | batch ingest (max 1000 per request) |

## Tests

```bash
cd server && .venv/Scripts/python -m pytest          # API + stats
cd sdk/python && ../../server/.venv/Scripts/python -m pytest   # SDK + end-to-end
cd dashboard && npm run lint && npm run build
```

## Dashboard login

The dashboard is protected by a single password (`DKM_DASHBOARD_PASSWORD`). Signing in sets a signed, httpOnly session cookie that lasts 7 days. Every page and action checks it: `proxy.ts` redirects signed-out visitors, and the data layer (`lib/api.ts`) checks again before any API call. Changing the password signs everyone out. If no password is set, the dashboard stays locked.

The SDK and REST API are unaffected; they keep using the API key.

## Configuration

| Variable | Used by | Default |
|---|---|---|
| `DKM_API_KEY` | server (first start), SDK, dashboard | generated and printed on first start |
| `DKM_DATABASE_URL` | server | `sqlite:///./dkm.db` (any SQLAlchemy URL, e.g. Postgres) |
| `DKM_BASE_URL` | SDK | `http://localhost:8000` |
| `DKM_API_URL` | dashboard | `http://localhost:8000` |
| `DKM_DASHBOARD_PASSWORD` | dashboard | none: **required**, the dashboard stays locked without it |
| `DKM_SECURE_COOKIES` | dashboard | `false`. Set `true` behind HTTPS if your proxy doesn't send `X-Forwarded-Proto` |

## Known v1 limits

- **One shared dashboard password**, no individual user accounts. Failed logins are slowed down, not rate-limited per IP, so use a strong password if the dashboard is reachable from the internet.
- One project per server.
- Stats are computed per event, not per user. Metrics recorded once per user (like a single thumbs up) are exact; repeated events from the same user are treated as independent.
- Results load all events into memory. Fine up to roughly 1M events per experiment.
- Don't peek and stop early: decide your sample size up front (the dashboard's "~N more needed" helps).

## Roadmap

offline evals on datasets · TypeScript SDK · multi-project and user accounts · sequential testing for safe early stopping.
