"""Fail-closed cross-platform Git checkout byte-integrity guard for MATRIX tennis.

This executes immediately after actions/checkout and BEFORE tests or capture.
It permits restoration of exactly one lossless CRLF->LF transformation.
It NEVER changes committed blobs, feature state, holdouts, or model metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

# All paths are fixed and trusted, no user supplied arbitrary file targets.
TRACKED = (
    "evidence/tennis_calendar_physical/2026-11-06/sofascore_verified_match_details.json",
    "evidence/tennis_calendar_reconciliation/2026-11-06/MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json",
    "evidence/tennis_calendar_reconciliation/2026-11-06/MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST.json",
    "evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json",
    "evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/identity/MATRIX_CLAY_IDENTITY_AUTHORITY_LAST.json",
)

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def git_blob(root: Path, filename: str) -> bytes:
    # Git outputs bytes unchanged even if core.autocrlf rewrote the worktree.
    p = subprocess.run(["git", "-C", str(root), "show", "HEAD:" + filename],
                       check=True, capture_output=True)
    return p.stdout

def verify(root: Path, *, restore_safe_newlines: bool = False) -> dict:
    paths = []
    for filename in TRACKED:
        q = root / filename
        if not q.is_file():
            raise ValueError("MATRIX_CHECKOUT_SOURCE_MISSING:" + filename)
        worktree = q.read_bytes()
        trusted = git_blob(root, filename)
        status = "BYTE_EXACT"
        if worktree != trusted:
            # Never replace arbitrary edits, even if JSON parses. Only a
            # reversible newline conversion of the *same* committed bytes.
            if not restore_safe_newlines or b"\\r\\n" in trusted or worktree.replace(b"\\r\\n", b"\\n") != trusted:
                raise ValueError("MATRIX_CHECKOUT_SOURCE_DRIFT:" + filename +
                                 ":git=" + digest(trusted) + ":worktree=" + digest(worktree))
            q.write_bytes(trusted)
            if q.read_bytes() != trusted:
                raise ValueError("MATRIX_CHECKOUT_RESTORE_VERIFICATION_FAILED:" + filename)
            status = "LOSSLESS_CRLF_CHECKOUT_RESTORED"
        paths.append({"path":filename, "status":status, "git_blob_sha256":digest(trusted),
                      "worktree_sha256":digest(q.read_bytes())})
    research=json.loads((root/TRACKED[2]).read_bytes())
    bound=research.get("source_sha256") or {}
    if bound.get("prematch_details") != paths[0]["git_blob_sha256"]:
        raise ValueError("MATRIX_ORIGINAL_PREMATCH_DETAIL_HASH_MISMATCH")
    if bound.get("source_crossmatch") != paths[1]["git_blob_sha256"]:
        raise ValueError("MATRIX_ORIGINAL_BROWSER_CROSSMATCH_HASH_MISMATCH")
    authorities=bound.get("original_authorities") or {}
    if authorities.get("Hard") != paths[3]["git_blob_sha256"] or authorities.get("Clay") != paths[4]["git_blob_sha256"]:
        raise ValueError("MATRIX_ORIGINAL_AUTHORITY_HASH_MISMATCH")
    return {"schema":"MATRIX_TENNIS_WINDOWS_GIT_CHECKOUT_SHA256_GUARD_V1",
            "verified_files":len(paths), "sources":paths,
            "research_evidence_source_bindings_verified":True,
            "real_money":"BLOCKED", "model_state_changed":False,
            "holdout_admissions":0}

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--restore-safe-newlines",action="store_true")
    args=p.parse_args()
    print(json.dumps(verify(args.root,restore_safe_newlines=args.restore_safe_newlines),sort_keys=True))

if __name__=="__main__":
    main()
