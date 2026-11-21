"""Offline GitHub Actions contract tests; synthetic schedules are not outcomes.

These assertions prevent accidental no-result fanout, altered wagers, or
missing workflow-dispatch permissions. They do NOT assert that outcomes exist.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"

CHAIN = (
    ("matrix-independent-over25-research-settlement.yml",
     "matrix-independent-free-poisson-oos.yml",
     "Wake independent Poisson OOS only after newly certified provider results",
     "newly_settled_count", "newly_settled_verified"),
    ("matrix-independent-free-poisson-oos.yml",
     "matrix-hybrid-three-model-prospective-oos.yml",
     "Wake three-model OOS only for newly verified paired results",
     "independently_verified_settled_pairs", "previous_oos"),
    ("matrix-hybrid-three-model-prospective-oos.yml",
     "matrix-hybrid-four-model-prospective-oos.yml",
     "Wake four-model OOS only after new three-model settled outcomes",
     "three_model_authenticated_settled_count", "previous_three"),
)


def workflow(name):
    path = ROOT / name
    assert path.is_file(), f"MISSING_WORKFLOW:{name}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("upstream,downstream,step_title,count_token,previous_step", CHAIN)
def test_one_verified_transition_only(upstream, downstream, step_title, count_token,
                                     previous_step):
    source = workflow(upstream)
    target = workflow(downstream)
    assert source["permissions"]["contents"] == "write"
    assert source["permissions"]["actions"] == "write"
    assert target.get("on", target.get(True))["workflow_dispatch"] is None
    steps = source["jobs"][next(iter(source["jobs"]))]["steps"]
    matching = [s for s in steps if s.get("name") == step_title]
    assert len(matching) == 1
    stage = matching[0]
    assert stage["if"] == "success()"
    assert stage["env"]["GH_TOKEN"] == "${{ github.token }}"
    script = stage["run"]
    assert count_token in script
    assert "gh workflow run " + downstream in script
    assert "--ref repair/cor09-world-pipeline" in script
    assert "real_money" in script or "real_money" in script.lower()
    assert "telegram_signal_authorized" in script
    assert "if [ \"$" in script and " -gt 0 ]; then" in script
    assert "else" in script and "NO_" in script
    if previous_step != "newly_settled_verified":
        previous = [s for s in steps if s.get("id") == previous_step]
        assert len(previous) == 1
        assert "GITHUB_OUTPUT" in previous[0]["run"]
        assert previous_step in str(stage["env"])
        assert "after>=before" in script
    else:
        # A settlement is allowed to trigger the chain only for newly
        # authenticated provider results, never for a refreshed timestamp.
        assert "newly_settled_count" in script


def test_research_only_guards_remain_unchanged():
    for name in {a for a, *_ in CHAIN}:
        source = workflow(name)
        assert source["permissions"]["actions"] == "write"
        all_scripts = "\n".join(str(s.get("run", "")) for
                                job in source["jobs"].values() for s in job["steps"])
        assert "BLOCKED" in all_scripts
        assert "telegram_signal_authorized" in all_scripts
        assert "gh workflow run" in all_scripts


def test_pipeline_has_no_closed_dispatch_cycle():
    nodes = [x[0] for x in CHAIN]
    sinks = [x[1] for x in CHAIN]
    assert len(nodes) == len(set(nodes))
    assert nodes[1:] == sinks[:-1]
    assert sinks[-1] not in nodes
    assert sinks[-1] == "matrix-hybrid-four-model-prospective-oos.yml"
