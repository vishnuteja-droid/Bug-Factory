# Bug-Factory

An autonomous bug-fixing pipeline: a **ticket comes in**, AI agents **analyze an
unfamiliar codebase, localize the fault, plan and write a fix, verify it against
the test suite, and produce a merge request** — all running locally on a small
model via [Ollama](https://ollama.com).

This is the Phase 0 demo: one dummy repo, one ticket, the full flow working end
to end, plus a web UI to watch it.

## How it works

```
ticket (JSON)  →  Intake  →  Localize  →  Plan  →  Code  →  Validate  →  MR artifact
                   (LLM)    (repo map +   (LLM)   (LLM      (pytest:      (diff +
                             LLM pick)            edit)     red→green)    description)
```

The spine is the **red→green gate**: the factory first runs the suite to confirm
the bug reproduces, applies a fix, and accepts it **only when the failing test
passes and the rest of the suite stays green**. The model only makes small,
bounded choices; deterministic code does localization and validation — which is
what makes a 1B model viable.

The LLM is pluggable behind one interface (`bugfactory/llm/base.py`). Today:
`ollama` (real) and `mock` (deterministic, no server needed). Adding OpenAI,
a hosted model, etc. is a new adapter — no pipeline changes.

## Run it

```bash
pip install -r requirements.txt

# 1) Local model (the real demo)
ollama serve            # in one terminal
ollama pull gemma3:1b
python run_demo.py                      # CLI
uvicorn ui.server:app --reload          # UI at http://localhost:8000

# 2) No model server (verify the harness anywhere)
python run_demo.py --provider mock
PROVIDER=mock uvicorn ui.server:app --reload
```

Outputs (the proposed diff + MR description) land in `output/`.

## Layout

| Path | What |
|---|---|
| `sample_repo/` | dummy repo with a real bug + pytest suite |
| `tickets/` | input bug tickets (`BUG-101.json`) |
| `bugfactory/llm/` | provider-agnostic LLM interface + adapters |
| `bugfactory/codebase/` | repo map (`ast`) + safe function editing |
| `bugfactory/sandbox/` | runs the suite in a subprocess (Docker slots in here at scale) |
| `bugfactory/agents.py` | intake / localize / plan / code / review steps |
| `bugfactory/pipeline.py` | orchestrator; emits a stream of events |
| `ui/` | FastAPI + single-page live view (SSE) |

## Roadmap

- **Phase 1** — real Jira intake (webhook) + GitLab MR creation; retries + token budget.
- **Phase 2** — auto-generate a reproduction test; stronger self-review; respond to CI/review feedback.
- **Phase 3** — scale: task queue, parallel workers, Docker isolation for untrusted repos, per-repo index cache, human-review dashboard.
