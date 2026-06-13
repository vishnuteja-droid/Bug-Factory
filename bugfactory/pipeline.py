"""The orchestrator: ticket in -> verified fix + MR artifact out.

Implemented as a generator that yields Events so a CLI or web UI can watch each
stage live. The spine is the red->green gate: confirm the bug reproduces
(stably, not flakily), apply a fix, and accept only when the failing tests pass
and the rest of the suite stays green. If the top suspect can't be fixed, we
fall back to the next candidate; if none work, we flag for a human.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time

from . import agents
from .codebase import build_repo_map, get_function_source, replace_function
from .events import Event
from .mr import make_diff, make_mr_description
from .sandbox import run_tests


def _copy_repo(src_repo: str) -> str:
    dst = os.path.join(tempfile.mkdtemp(prefix="bugfactory-"), "repo")
    shutil.copytree(src_repo, dst)
    return dst


def _baseline(repo: str, runs: int):
    """Run the clean suite `runs` times. Return (stable_failing, collected) where
    stable_failing are tests that fail on EVERY run (flaky ones fail only some and
    drop out). `collected` is the full set of test node ids."""
    failing_each, collected = [], set()
    for _ in range(max(1, runs)):
        r = run_tests(repo)
        collected |= r["collected"]
        failing_each.append(r["failing"] if not r["passed"] else set())
    stable = set.intersection(*failing_each) if failing_each else set()
    return stable, collected


def run_pipeline(repo_path, ticket, provider, max_fix_attempts=3, max_candidates=3,
                 baseline_runs=2, output_dir="output"):
    key = ticket.get("key", "TICKET")
    log: list[dict] = []

    def emit(stage, status, message, data=None):
        ev = Event(stage, status, message, data or {})
        log.append(ev.to_dict())
        return ev

    yield emit("intake", "start", f"Picked up {key}: {ticket.get('title','')}")
    triage = agents.intake(provider, ticket)
    yield emit("intake", "success", triage["summary"],
               {"keywords": triage["keywords"][:12], "model": provider.model})

    reference = _copy_repo(repo_path)
    yield emit("localize", "start", "Mapping an unfamiliar codebase...")
    repo_map = build_repo_map(reference)
    source_syms = [f.qualname for f in repo_map if not f.is_test]
    yield emit("localize", "info",
               f"Indexed {len(source_syms)} source symbols (functions + methods)",
               {"symbols": source_syms})

    # Confirm the bug reproduces stably before touching anything.
    yield emit("validate", "start",
               f"Reproducing the bug: running the suite {baseline_runs}x on the clean repo...")
    stable_failing, collected = _baseline(reference, baseline_runs)
    if not stable_failing:
        yield emit("validate", "error",
                   "No stable failing test on the clean repo (passes, or only flaky failures). "
                   "Cannot establish a reproduction signal. Flagging for a human.")
        yield emit("done", "error", "No reproducible failure; stopping.")
        _write_log(output_dir, key, log)
        return
    baseline_passing = collected - stable_failing
    yield emit("validate", "info", f"Bug reproduced. Stable failing tests: {', '.join(sorted(stable_failing))}",
               {"failing": sorted(stable_failing)})

    candidates = agents.rank_candidates(ticket, triage["keywords"], repo_map, max_candidates=max_candidates)
    chosen = agents.choose_candidate(provider, ticket, candidates)
    # Try the model's pick first, then the rest of the ranked list.
    order = [chosen] + [c for c in candidates if c.qualname != chosen.qualname]
    yield emit("localize", "success",
               f"Ranked suspects: {', '.join(c.qualname for c in order)}; starting with {chosen.qualname}",
               {"candidates": [c.qualname for c in order], "chosen": chosen.qualname, "file": chosen.file})

    accepted = None
    for cand_no, target in enumerate(order, 1):
        work = _copy_repo(repo_path)
        target_path = os.path.join(work, target.file)
        try:
            func_src = get_function_source(target_path, target.qualname)
        except ValueError as exc:
            yield emit("code", "error", f"Could not read {target.qualname}: {exc}; next suspect.")
            continue

        fix_plan = agents.plan(provider, ticket, target, func_src)
        yield emit("plan", "success", fix_plan,
                   {"target": f"{target.qualname} ({target.file})", "suspect": f"{cand_no}/{len(order)}"})

        last_error = None
        attempt_src = func_src
        for attempt in range(1, max_fix_attempts + 1):
            yield emit("code", "start",
                       f"Suspect {cand_no} '{target.qualname}', attempt {attempt}/{max_fix_attempts}...")
            new_func = agents.code_fix(provider, ticket, target, attempt_src, last_error)
            if not new_func.strip():
                last_error = "empty output"
                yield emit("code", "error", "Model returned no code; retrying.")
                continue
            try:
                old_source, new_source = replace_function(target_path, target.qualname, new_func)
            except (ValueError, SyntaxError) as exc:
                last_error = str(exc)
                yield emit("code", "error", f"Edit did not apply/parse: {exc}; retrying.")
                continue

            yield emit("code", "info", f"Applied edit to {target.qualname}", {"new_function": new_func})
            yield emit("validate", "start", f"Re-running the suite (suspect {cand_no}, attempt {attempt})...")
            result = run_tests(work)

            resolved = stable_failing - result["failing"]          # bug tests that now pass
            regressions = result["failing"] & baseline_passing      # previously-green tests now broken
            if resolved and not regressions:
                yield emit("validate", "success",
                           f"Fix verified (red -> green). Resolved: {', '.join(sorted(resolved))}.",
                           {"resolved": sorted(resolved), "still_open": sorted(result["failing"])})
                accepted = {"target": target, "old": old_source, "new": new_source,
                            "plan": fix_plan, "resolved": sorted(resolved)}
                break

            last_error = result["output"][-1500:]
            attempt_src = new_func
            reason = ("introduced regressions: " + ", ".join(sorted(regressions))) if regressions \
                else "did not resolve the failing test(s)"
            yield emit("validate", "info", f"Rejected ({reason}). Feeding the error back.",
                       {"failing": sorted(result["failing"]), "regressions": sorted(regressions)})
        if accepted:
            break
        yield emit("localize", "info", f"Suspect '{target.qualname}' exhausted; moving to next.")

    if not accepted:
        yield emit("done", "error",
                   f"No passing fix across {len(order)} suspect(s). Flagging for a human.")
        _write_log(output_dir, key, log)
        return

    target = accepted["target"]
    diff = make_diff(accepted["old"], accepted["new"], target.file)
    review_note = agents.review(provider, ticket, diff)
    yield emit("review", "success", review_note)

    description = make_mr_description(ticket, triage["summary"], accepted["plan"], diff, review_note)
    os.makedirs(output_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(output_dir, f"{key}-{stamp}.diff"), "w") as fh:
        fh.write(diff)
    with open(os.path.join(output_dir, f"{key}-{stamp}.md"), "w") as fh:
        fh.write(description)

    yield emit("mr", "success", f"Merge request prepared for {key}",
               {"diff": diff, "description": description})
    yield emit("done", "success", f"{key} fixed and MR ready.")
    _write_log(output_dir, key, log)


def _write_log(output_dir: str, key: str, log: list[dict]):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{key}-{time.strftime('%Y%m%d-%H%M%S')}.events.json")
    with open(path, "w") as fh:
        json.dump(log, fh, indent=2)
