# GuardedContext

A small guardrail + multi-provider-routing evaluation layer for
women's-health AI answers — built as an application demo, not a claim
about any real company's product.

**What it does:** takes a question (typed as one of four risk
categories), generates a contextual answer, and runs an independent
guardrail evaluation against four failure modes lifted directly from a
published women's-health LLM benchmark (missed urgency, inappropriate
recommendation, incorrect treatment advice, missing critical info). If
the answer fails, it retries once — optionally against a different
model/provider — before falling back to a safe, templated response. A
batch mode runs a curated 18-question set and scores the whole pipeline
against pre-tagged expectations, the same basic idea as the benchmark's
own accuracy scoring, at small scale.

**What it is not:** not affiliated with Saela or any other company, not
connected to any real product or user data, not medical advice, not a
chatbot, not a RAG system.

Background and full rationale: see `saela-demo-buildplan.md` from the
same research pass (evidence chain, opportunity selection, Loom script,
outreach angle).

## Project layout

```
guardedcontext/
  backend/
    requirements.txt
    .env.example
    app/
      main.py          FastAPI app, mounts the frontend, health check
      config.py         env-var settings (OpenAI-compatible client + options)
      schemas.py        typed Pydantic models for every AI call and API response
      db.py              SQLite persistence (SQLModel)
      sample_data.py    18 curated, pre-tagged sample questions
      llm_client.py     classifier / responder / guardrail-evaluator prompts
      pipeline.py       orchestration + 3-tier fallback logic
      auth.py            optional shared-passcode gate
      routers/
        evaluate.py     POST /evaluate  (single question)
        samples.py      GET  /samples
        history.py      GET  /history
        batch.py        POST /run-batch (streamed NDJSON)
  frontend/
    index.html          single page, no build step
    app.js               fetch logic, streaming batch reader, rendering
    styles.css
  Dockerfile
  Procfile
  .gitignore
```

## Run it locally

Requires Python 3.11+.

```bash
cd guardedcontext/backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set OPENAI_API_KEY at minimum

uvicorn app.main:app --reload
```

Open http://localhost:8000 — the FastAPI app serves both the API and the
static frontend from one process.

## Configuring multi-provider routing (nice-to-have, fully wired up)

The env-var contract is intentionally the simple OpenAI-compatible triple:

```
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL_NAME=...
```

Used as-is, every step (classifier, responder, guardrail evaluator,
fallback) calls the same provider/model. To get **literal** cross-provider
routing and fallback — the exact pattern described in the target job
posting (Claude / Gemini / others, with fallback) — point
`OPENAI_BASE_URL` at an OpenAI-compatible multi-provider gateway (a
router service that exposes multiple vendors behind one chat-completions
endpoint) and set:

```
GUARDRAIL_MODEL_NAME=<a different provider's model string>
FALLBACK_MODEL_NAME=<a different provider's model string again>
```

`pipeline.py` will then genuinely call a second vendor for the guardrail
check and, if needed, a third for the fallback regeneration — all through
the same client code, just a different `model` string per call. Exact
current model identifiers aren't hard-coded anywhere in this project on
purpose (they change frequently); confirm them with whichever gateway
you're using at setup time.

If you don't have a multi-provider gateway configured, leave the two
optional variables blank — the demo still fully works, it just calls one
provider for every role. The typed-schema and fallback *architecture* is
what's being demonstrated either way.

## Using the demo

1. **Single question** — pick a sample question or type your own, click
   *Evaluate*. Watch the risk classification, the raw (pre-guardrail)
   answer, the guardrail flags, and the final answer a user would
   actually see.
2. **Batch benchmark** — click *Run all 18 questions* to stream all
   curated samples through the pipeline live, populating a scorecard
   (accuracy vs. pre-tagged expectations, flag rate per risk category)
   as each one completes.
3. **History** — every run (single or batch) is logged under an
   anonymous session ID, never a name or email, as a small working
   example of identity/health-data separation.

## Deploying

Single deployable service (API + static frontend from one FastAPI
process). Two easy paths:

**Docker** (works on Render / Fly.io / Railway / any container host):
```bash
docker build -t guardedcontext .
docker run -p 8000:8000 --env-file backend/.env guardedcontext
```

**Buildpack-style host** (Railway/Render "native" deploy): the included
`Procfile` runs `uvicorn app.main:app` from the `backend` directory — set
the same environment variables in the host's dashboard instead of a
`.env` file.

SQLite is used for simplicity; on most hosts its storage is ephemeral
across deploys, which is fine for a demo (the batch run can always be
re-run to repopulate history).

If deploying somewhere public, set `DEMO_ACCESS_CODE` so random visitors
can't run up API costs — the frontend will prompt for it automatically
when `/health` reports `auth_required: true`.

## Notes on scope

- The 18 sample questions are curated by hand (not generated by the AI)
  with an `expected_risk_tier` and `expected_guardrail_trigger`, so the
  batch scorecard has a ground truth to score against — without this,
  "60% accuracy" would be a meaningless number pulled from nowhere.
- Every prompt keeps the "not a medical device / not medical advice"
  framing from the target company's own public positioning, and the
  safe-template fallback text reflects that same boundary.
- No wearable integration, no user accounts, no RAG, no free-form open
  chat UI — all deliberately out of scope (see `saela-demo-buildplan.md`,
  "Do not build").
