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

The spine is the **red→green gate** (the same idea SWE-bench uses): the factory
runs the suite a few times to confirm the bug reproduces **stably** (flaky
failures are filtered out), applies a fix, and accepts it **only when the
ticket's failing test now passes AND no previously-green test regresses**. The
model only makes small, bounded choices; deterministic code does localization
and validation — which is what makes a 1B model viable.

**Localization scales without a vector DB.** Suspects are ranked by combining
(1) stack-trace frames in the ticket, (2) whole-word symbol-name matches, and
(3) lexical hits in function bodies. The model picks from the shortlist; if its
top suspect can't be fixed, the pipeline **falls back to the next candidate**.
Fixes work on module-level functions *and* class methods (`Cart.total`),
re-indented to drop cleanly back into place.

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
python run_demo.py --provider mock --ticket tickets/BUG-202.json   # class-method fix
PROVIDER=mock uvicorn ui.server:app --reload

# factory self-tests (run anywhere, no model server)
python -m pytest -q
```

Outputs (the proposed diff, MR description, and a full event log) land in `output/`.

## Layout

| Path | What |
|---|---|
| `sample_repo/` | dummy repo with two real bugs (a function + a class method) + pytest suite |
| `tickets/` | input bug tickets (`BUG-101`, `BUG-202` with a stack trace) |
| `bugfactory/llm/` | provider-agnostic LLM interface + Ollama/Mock adapters |
| `bugfactory/codebase/` | repo map, function/method editing, stack-trace + lexical search |
| `bugfactory/sandbox/` | runs the suite in a subprocess (Docker slots in here at scale) |
| `bugfactory/agents.py` | intake / rank+choose / plan / code / review steps |
| `bugfactory/pipeline.py` | orchestrator; emits a stream of events; persists a run log |
| `bugfactory/config.py` | run configuration (env-overridable) |
| `tests/` | factory self-tests (mock-driven, run anywhere) |
| `ui/` | FastAPI + single-page live view (SSE) |

## Roadmap

- **Phase 1** — real Jira intake (webhook) + GitLab MR creation; retries + token budget.
- **Phase 2** — auto-generate a reproduction test; stronger self-review; respond to CI/review feedback.
- **Phase 3** — scale: task queue, parallel workers, Docker isolation for untrusted repos, per-repo index cache, human-review dashboard.
