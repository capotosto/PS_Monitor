from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import CHECKLIST_FIELDS, CSV_FIELDS, SYSTEM_TEST_BY_ID
from .utils import as_bool

def append_csv(path: Path, record: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0

    normalized = {field: record.get(field, "") for field in CSV_FIELDS}
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(normalized)
        f.flush()
        os.fsync(f.fileno())


def load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Raw data file not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def append_checklist_csv(path: Path, record: Dict[str, object]) -> None:
    """Append one system-test checklist record to the separate checklist CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    normalized = {field: record.get(field, "") for field in CHECKLIST_FIELDS}

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHECKLIST_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(normalized)
        f.flush()
        os.fsync(f.fileno())


def load_checklist_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def checklist_test_runs(rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, object]]:
    """Reconstruct append-only checklist test attempts from TEST_START/STEP/TEST_END rows."""

    starts: Dict[str, Dict[str, str]] = {}
    ends: Dict[str, Dict[str, str]] = {}
    steps: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    for row in rows:
        run_id = row.get("test_run_id", "")
        if not run_id:
            continue
        record_type = row.get("record_type", "")
        if record_type == "TEST_START":
            starts[run_id] = row
        elif record_type == "STEP":
            steps[run_id].append(row)
        elif record_type == "TEST_END":
            ends[run_id] = row

    result: Dict[str, Dict[str, object]] = {}
    for run_id in set(starts) | set(ends) | set(steps):
        meta = starts.get(run_id) or ends.get(run_id) or {}
        end = ends.get(run_id, {})
        result[run_id] = {
            "meta": meta,
            "end": end,
            "steps": sorted(
                steps.get(run_id, []),
                key=lambda row: int(row.get("step_index", "0") or 0),
            ),
            "test_result": end.get("test_result", "INCOMPLETE") if end else "INCOMPLETE",
            "retest_outcome": end.get("retest_outcome", "") if end else "",
        }
    return result


def effective_checklist_result(run: Dict[str, object]) -> str:
    result = str(run.get("test_result", "INCOMPLETE") or "INCOMPLETE").upper()
    if result == "RETEST":
        outcome = str(run.get("retest_outcome", "") or "INCOMPLETE").upper()
        return outcome if outcome in {"PASS", "FAIL", "INCOMPLETE"} else "INCOMPLETE"
    return result if result in {"PASS", "FAIL", "INCOMPLETE"} else "INCOMPLETE"


def latest_checklist_by_test(
    rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> Dict[str, Tuple[str, Dict[str, object]]]:
    runs = checklist_test_runs(rows)
    selected: Dict[str, Tuple[str, Dict[str, object]]] = {}

    for run_id, run in runs.items():
        meta = run.get("meta", {})
        if not isinstance(meta, dict):
            continue
        if dut_id and meta.get("dut_id", "") != dut_id:
            continue
        test_id = meta.get("test_id", "")
        if test_id not in SYSTEM_TEST_BY_ID:
            continue
        try:
            attempt = int(meta.get("attempt", "0") or 0)
        except (TypeError, ValueError):
            attempt = 0

        if test_id not in selected:
            selected[test_id] = (run_id, run)
            continue

        old_meta = selected[test_id][1].get("meta", {})
        try:
            old_attempt = int(old_meta.get("attempt", "0") or 0) if isinstance(old_meta, dict) else 0
        except (TypeError, ValueError):
            old_attempt = 0
        if attempt >= old_attempt:
            selected[test_id] = (run_id, run)

    return selected


def next_checklist_attempt(path: Path, test_id: str, dut_id: str) -> int:
    rows = load_checklist_csv(path)
    attempts: List[int] = []
    for row in rows:
        if row.get("test_id") == test_id and row.get("dut_id", "") == dut_id:
            try:
                attempts.append(int(row.get("attempt", "0") or 0))
            except (TypeError, ValueError):
                pass
    return max(attempts, default=0) + 1


def next_attempt(path: Path, rail_key: str, dut_id: str) -> int:
    if not path.exists():
        return 1
    rows = load_csv(path)
    attempts = []
    for row in rows:
        if row.get("rail_key") == rail_key and row.get("dut_id", "") == dut_id:
            try:
                attempts.append(int(row.get("attempt", "0")))
            except ValueError:
                pass
    return (max(attempts) + 1) if attempts else 1


