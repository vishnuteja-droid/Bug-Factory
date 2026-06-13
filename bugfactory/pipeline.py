"""The orchestrator: ticket in -> verified fix + MR artifact out.

Implemented as a generator that yields Events so a CLI or web UI can watch
each stage live. The spine is the red->green gate: we confirm the bug
reproduces, apply a fix, and accept only when the failing test passes and the
rest of the suite stays green.
"""
from __future__ import annotations

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
    workdir = tempfile.mkdtemp(prefix="bugfactory-")
    dst = os.path.join(workdir, "repo")
    shutil.copytree(src_repo, dst)
    return dst


def run_pipeline(repo_path: str, ticket: dict, provider, max_fix_attempts: int = 3, output_dir: str = "output"):
    key = ticket.get("key", "TICKET")

    yield Event("intake", "start", f"Picked up {key}: {ticket.get('title','')}")
    triage = agents.intake(provider, ticket)
    yield Event("intake", "success", triage["summary"],
                {"keywords": triage["keywords"], "model": provider.model})

    # Work on an isolated copy so reruns are clean.
    work_repo = _copy_repo(repo_path)
    yield Event("localize", "start", "Building a map of an unfamiliar codebase...")
    repo_map = build_repo_map(work_repo)
    yield Event("localize", "info", f"Indexed {len(repo_map)} functions across the repo",
                {"functions": [f"{fn.function} ({fn.file})" for fn in repo_map]})

    # Confirm the bug actually reproduces before touching anything.
    yield Event("validate", "start", "Reproducing the bug: running the test suite on the clean repo...")
    baseline = run_tests(work_repo)
    if baseline["passed"]:
        yield Event("validate", "error",
                    "All tests already pass on the clean repo — cannot reproduce. Flagging for a human.",
                    {"output": baseline["output"]})
        yield Event("done", "error", "No reproducible failure; stopping.")
        return
    yield Event("validate", "info", f"Bug reproduced. Failing tests: {', '.join(baseline['failing'])}",
                {"failing": baseline["failing"]})

    target, candidates = agents.localize(provider, ticket, triage["keywords"], repo_map)
    yield Event("localize", "success",
                f"Located likely culprit: {target.function}() in {target.file}",
                {"candidates": [c.function for c in candidates], "chosen": target.function,
                 "file": target.file})

    func_src = get_function_source(target.abspath, target.function)
    fix_plan = agents.plan(provider, ticket, target, func_src)
    yield Event("plan", "success", fix_plan, {"target": f"{target.function} ({target.file})"})

    # Code -> validate loop.
    last_error = None
    old_source = new_source = None
    accepted = False
    for attempt in range(1, max_fix_attempts + 1):
        yield Event("code", "start", f"Attempt {attempt}/{max_fix_attempts}: writing a fix...")
        new_func = agents.code_fix(provider, ticket, target, func_src, last_error)
        if not new_func.strip():
            yield Event("code", "error", "Model returned no code; retrying.")
            last_error = "empty output"
            continue
        try:
            old_source, new_source = replace_function(target.abspath, target.function, new_func)
        except (ValueError, SyntaxError) as exc:
            yield Event("code", "error", f"Edit did not apply cleanly: {exc}. Retrying.")
            last_error = str(exc)
            continue

        yield Event("code", "info", f"Applied edit to {target.function}()", {"new_function": new_func})
        yield Event("validate", "start", f"Attempt {attempt}: re-running the test suite...")
        result = run_tests(work_repo)
        if result["passed"]:
            yield Event("validate", "success", "All tests pass. Fix verified (red -> green).",
                        {"failing_before": baseline["failing"]})
            accepted = True
            break

        yield Event("validate", "info",
                    f"Still failing: {', '.join(result['failing'])}. Feeding the error back to the coder.",
                    {"failing": result["failing"]})
        last_error = result["output"][-1500:]
        # Reset the function source for the next attempt's prompt context.
        func_src = new_func

    if not accepted:
        yield Event("done", "error",
                    f"Could not produce a passing fix in {max_fix_attempts} attempts. Flagging for a human.")
        return

    # Build the MR artifact.
    diff = make_diff(old_source, new_source, target.file)
    review_note = agents.review(provider, ticket, diff)
    yield Event("review", "success", review_note)

    description = make_mr_description(ticket, triage["summary"], fix_plan, diff, review_note)
    os.makedirs(output_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    diff_path = os.path.join(output_dir, f"{key}-{stamp}.diff")
    mr_path = os.path.join(output_dir, f"{key}-{stamp}.md")
    with open(diff_path, "w") as fh:
        fh.write(diff)
    with open(mr_path, "w") as fh:
        fh.write(description)

    yield Event("mr", "success", f"Merge request prepared for {key}",
                {"diff": diff, "description": description,
                 "diff_path": diff_path, "mr_path": mr_path})
    yield Event("done", "success", f"{key} fixed and MR ready.")
