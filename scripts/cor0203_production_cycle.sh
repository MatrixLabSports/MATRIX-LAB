#!/usr/bin/env bash
set -euo pipefail

TRIGGER_SHA=""
TARGET_BRANCH="${MATRIX_TARGET_BRANCH:-repair/cor09-world-pipeline}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trigger-sha)
      TRIGGER_SHA="${2:-}"
      shift 2
      ;;
    --target-branch)
      TARGET_BRANCH="${2:-}"
      shift 2
      ;;
    *)
      echo "UNKNOWN_ARGUMENT:$1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TRIGGER_SHA" ]]; then
  echo "TRIGGER_SHA_REQUIRED" >&2
  exit 2
fi

STATE="evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64"
BUNDLE="evidence/cor0203/runtime/MATRIX_COR0203_ELO_GLICKO_PROSPECTIVE_BUNDLE_R706.json"
ANNUAL="evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv"
ONGOING="evidence/cor0203/preholdout/challenger_ongoing_tourneys_live_snapshot.csv"
STATIC_CUT="evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json"
DISCOVERY="/tmp/MATRIX_COR0203_API_TENNIS_DISCOVERY.json"
PREREG_LAST="evidence/cor0203/runtime/MATRIX_COR0203_DISCOVERY_PREREG_LAST.json"
CROSSWALK_LAST="evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_CROSSWALK_LAST.json"
STAGE_LAST="evidence/cor0203/runtime/MATRIX_COR0203_AUTO_STAGE_LAST.json"
RUNNER_LAST="evidence/cor0203/runtime/MATRIX_COR0203_BATCH_RUNNER_LAST.json"
INTEGRITY_LAST="evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json"
HEARTBEAT="evidence/cor0203/runtime/MATRIX_COR0203_SCHEDULER_HEARTBEAT.json"

test -s "$STATE"
test -s "$BUNDLE"
test -s "$ANNUAL"
test -s "$ONGOING"
test "$(sha256sum "$STATE" | awk '{print $1}')" = "384b5537ad9715b552d26464db3d01980021a24e9f6d7e0fcc93ba154efde125"
test "$(sha256sum "$BUNDLE" | awk '{print $1}')" = "ef5788fa4212c67880a52af85359bed1483ba1d59b1655e28390bbfaf0187ec8"
test "$(sha256sum "$ANNUAL" | awk '{print $1}')" = "d3f0e7edca273d0e1fcd4700581cf00398e46719f0aaadb62a1c97ec0ffa6ab5"

python -m tools.cor0203_build_static_cut_index \
  --csv "$ONGOING" \
  --cut 20260921 \
  --out "$STATIC_CUT"

python -m tools.cor0203_api_tennis_discovery \
  --out "$DISCOVERY" \
  --days 2

python -m tools.cor0203_preregister_discovery \
  --discovery "$DISCOVERY" \
  --result-out "$PREREG_LAST"

python -m tools.cor0203_build_identity_crosswalk \
  --static-cut "$STATIC_CUT" \
  --summary-out "$CROSSWALK_LAST"

python -m tools.cor0203_stage_from_registry \
  --summary-out "$STAGE_LAST"

python -m tools.cor0203_batch_runner \
  --state-b64 "$STATE" \
  --bundle "$BUNDLE" \
  --annual-2026 "$ANNUAL" \
  --trigger-sha "$TRIGGER_SHA" \
  --summary-out "$RUNNER_LAST"

python -m tools.cor0203_holdout_integrity_audit \
  --runtime-dir evidence/cor0203/runtime \
  --holdout-dir evidence/cor0203/holdout \
  --state-b64 "$STATE" \
  --bundle "$BUNDLE" \
  --annual-2026 "$ANNUAL" \
  --binding evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json \
  --out "$INTEGRITY_LAST"

python - <<'PY'
import json
import re
from pathlib import Path

runtime = Path("evidence/cor0203/runtime")
holdout = Path("evidence/cor0203/holdout")

prereg = json.loads((runtime / "MATRIX_COR0203_DISCOVERY_PREREG_LAST.json").read_text())
crosswalk = json.loads((runtime / "MATRIX_COR0203_IDENTITY_CROSSWALK_LAST.json").read_text())
stage = json.loads((runtime / "MATRIX_COR0203_AUTO_STAGE_LAST.json").read_text())
runner = json.loads((runtime / "MATRIX_COR0203_BATCH_RUNNER_LAST.json").read_text())
integrity = json.loads((runtime / "MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json").read_text())

assert prereg["status"] in {"NO_DISCOVERY_INPUT", "NO_NEW_EVENTS", "PREREGISTERED"}
assert crosswalk["real_money"] == "BLOCKED"
assert stage["real_money"] == "BLOCKED"
assert runner["ending_physical_count"] >= runner["starting_physical_count"]
assert integrity["result"] == "PASS"
assert integrity["admissible_observations"] == runner["ending_physical_count"]
assert integrity["audited_observations"] == integrity["passed_observations"]
assert integrity["failed_observations"] == 0
assert integrity["outcomes_read"] == 0
assert integrity["metrics_opened"] is False
assert integrity["median_or_neutral_fallback_admissible"] is False

exact_batch = re.compile(r"^MATRIX_COR0203_HOLDOUT_BATCH_R\d+\.json$")
for path in holdout.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
    if not exact_batch.match(path.name):
        continue
    payload = json.loads(path.read_text())
    assert payload.get("metrics") == "SEALED_UNTIL_600"
    assert payload.get("outcomes_read") == 0
    for observation in payload.get("observations", []):
        assert observation.get("outcome") is None
        assert observation.get("metrics_opened") is False
        assert observation["freeze_at_utc"] < observation["event_start_utc"]

print(json.dumps({
    "prereg_status": prereg["status"],
    "crosswalk_revisions": len(crosswalk.get("crosswalk_revisions", [])),
    "ending_physical_count": runner["ending_physical_count"],
    "new_freezes": runner["new_freezes"],
    "new_blocked": runner["new_blocked"],
    "holdout_integrity": integrity["result"],
    "audited_observations": integrity["audited_observations"],
}, sort_keys=True))
PY

git config user.name "${MATRIX_GIT_USER_NAME:-matrix-production}"
git config user.email "${MATRIX_GIT_USER_EMAIL:-matrix-production@users.noreply.github.com}"

# Stage append-only/revision evidence first. Mutable *_LAST/heartbeat files do
# not define whether a cycle is material; this prevents empty cycles from
# creating commits or racing with code changes.
git add evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_CROSSWALK_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_STAGE_BLOCKERS_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_STATIC4_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_PROSPECTIVE_EVENTS_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_BATCH_PREFLIGHT_R*.json 2>/dev/null || true
git add evidence/cor0203/runtime/MATRIX_COR0203_HISTORY_GATE_R*.json 2>/dev/null || true
git add evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R*.json 2>/dev/null || true

if git diff --cached --quiet; then
  echo "COR0203_CYCLE_NO_MATERIAL_CHANGE"
  exit 0
fi

# Only a material append-only change is allowed to carry mutable summaries.
git add "$STATIC_CUT"
git add "$PREREG_LAST"
git add "$CROSSWALK_LAST"
git add "$STAGE_LAST"
git add "$RUNNER_LAST"
git add "$INTEGRITY_LAST"
if [[ -f "$HEARTBEAT" ]]; then
  git add "$HEARTBEAT"
fi

git commit -m "evidence(cor02-03): governed autonomous production cycle"
git fetch origin "$TARGET_BRANCH"
git rebase "origin/$TARGET_BRANCH"
git push origin "HEAD:$TARGET_BRANCH"
