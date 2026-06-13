"""Self-tests for the bug factory itself, driven by the deterministic mock
provider so they run anywhere (no model server). They prove the pipeline
localizes, edits (module function AND class method), and verifies a fix
end to end.
"""
import json
import os

import pytest

from bugfactory import run_pipeline
from bugfactory.llm import build_provider
from bugfactory.codebase import build_repo_map, replace_function, get_function_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "sample_repo")


def _run(ticket_key):
    with open(os.path.join(ROOT, "tickets", f"{ticket_key}.json")) as fh:
        ticket = json.load(fh)
    provider = build_provider("mock")
    out = os.path.join(ROOT, "output")
    return list(run_pipeline(REPO, ticket, provider, output_dir=out))


@pytest.mark.parametrize("key", ["BUG-101", "BUG-202"])
def test_pipeline_produces_verified_fix(key):
    events = _run(key)
    assert events[-1].stage == "done"
    assert events[-1].status == "success", f"{key} did not finish green"
    assert any(e.stage == "validate" and e.status == "success" for e in events)
    assert any(e.stage == "mr" and e.status == "success" for e in events)


def test_localization_picks_right_symbol():
    repo_map = build_repo_map(REPO)
    names = {f.qualname for f in repo_map}
    assert "subtract" in names
    assert "Cart.total" in names  # methods are mapped with qualified names


def test_method_edit_reindents(tmp_path):
    """A method returned at column 0 must drop back into the class correctly."""
    src = tmp_path / "m.py"
    src.write_text("class C:\n    def f(self):\n        return 1\n")
    replace_function(str(src), "C.f", "def f(self):\n    return 2")
    assert get_function_source(str(src), "C.f") == "    def f(self):\n        return 2"


def test_unreproducible_bug_is_flagged():
    """A ticket whose tests already pass should be flagged, not 'fixed'."""
    with open(os.path.join(ROOT, "tickets", "BUG-101.json")) as fh:
        ticket = json.load(fh)
    ticket["key"] = "NOREPRO"
    # point at a repo with no failing tests by using a fresh copy where we fix the bug first
    import shutil, tempfile
    work = os.path.join(tempfile.mkdtemp(), "repo")
    shutil.copytree(REPO, work)
    # Repair every seeded bug so the suite is fully green -> nothing to reproduce.
    replace_function(os.path.join(work, "src", "calc.py"), "subtract", "def subtract(a, b):\n    return a - b")
    replace_function(os.path.join(work, "src", "orders.py"), "Cart.total",
                     "def total(self, tax_rate):\n    return self.subtotal() * (1 + tax_rate)")
    events = list(run_pipeline(work, ticket, build_provider("mock"), output_dir=os.path.join(ROOT, "output")))
    assert events[-1].status == "error"
