from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .config import (
    AUTO_ONLY_STEPS, RAILS, RAIL_OBSERVATION_NAME_BY_INDEX, RAIL_ORDER,
    SYSTEM_TESTS, RailConfig, SystemTestConfig,
)
from .storage import latest_checklist_by_test
from .utils import as_bool, safe_float

def group_samples(rows: Iterable[Dict[str, str]]) -> Dict[str, Dict[float, List[Dict[str, str]]]]:
    grouped: Dict[str, Dict[float, List[Dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("record_type") != "SAMPLE":
            continue
        setpoint = safe_float(row.get("setpoint_a"))
        if not math.isfinite(setpoint):
            continue
        grouped[row.get("run_id", "")][setpoint].append(row)
    return grouped


def mean_field(rows: Sequence[Dict[str, str]], field: str) -> float:
    vals = [safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if math.isfinite(v)]
    return statistics.mean(vals) if vals else float("nan")


def run_records(rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, object]]:
    starts: Dict[str, Dict[str, str]] = {}
    ends: Dict[str, Dict[str, str]] = {}
    for row in rows:
        run_id = row.get("run_id", "")
        if not run_id:
            continue
        if row.get("record_type") == "RUN_START":
            starts[run_id] = row
        elif row.get("record_type") == "RUN_END":
            ends[run_id] = row

    samples = group_samples(rows)
    result: Dict[str, Dict[str, object]] = {}
    for run_id in set(starts) | set(ends) | set(samples):
        meta = starts.get(run_id) or ends.get(run_id) or {}
        end = ends.get(run_id, {})
        result[run_id] = {
            "meta": meta,
            "end": end,
            "points": samples.get(run_id, {}),
            "status": end.get("run_status", "INCOMPLETE") if end else "INCOMPLETE",
            "run_pass": as_bool(end.get("run_pass")) if end.get("run_pass", "") != "" else None,
        }
    return result


def latest_attempt_by_rail(
    runs: Dict[str, Dict[str, object]],
    dut_id: Optional[str],
) -> Dict[str, Tuple[str, Dict[str, object]]]:
    """Return only the highest-numbered attempt recorded for each rail."""

    selected: Dict[str, Tuple[str, Dict[str, object]]] = {}

    for run_id, run in runs.items():
        meta = run.get("meta", {})

        if not isinstance(meta, dict):
            continue

        if dut_id and meta.get("dut_id", "") != dut_id:
            continue

        rail_key = meta.get("rail_key", "")

        if rail_key not in RAILS:
            continue

        try:
            attempt = int(meta.get("attempt", "0") or 0)
        except (TypeError, ValueError):
            attempt = 0

        if rail_key not in selected:
            selected[rail_key] = (run_id, run)
            continue

        old_meta = selected[rail_key][1].get("meta", {})

        if isinstance(old_meta, dict):
            try:
                old_attempt = int(old_meta.get("attempt", "0") or 0)
            except (TypeError, ValueError):
                old_attempt = 0
        else:
            old_attempt = 0

        if attempt >= old_attempt:
            selected[rail_key] = (run_id, run)

    return selected


def derive_accuracy_status(
    rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
    field: str,
) -> Tuple[str, str]:

    if field not in {"voltage_pass", "current_pass"}:
        raise ValueError(f"Unsupported derived field: {field}")

    filtered = [
        row for row in rows
        if (not dut_id or row.get("dut_id", "") == dut_id)
    ]
    runs = run_records(filtered)
    latest = latest_attempt_by_rail(runs, dut_id)

    missing = [RAILS[key].label for key in RAIL_ORDER if key not in latest]
    if missing:
        return "INCOMPLETE", "Missing latest measurement attempt for: " + ", ".join(missing)

    failed_rails: List[str] = []
    incomplete_rails: List[str] = []

    for key in RAIL_ORDER:
        _, run = latest[key]
        if run.get("status") != "COMPLETE":
            incomplete_rails.append(RAILS[key].label)
            continue

        points = run.get("points", {})
        samples: List[Dict[str, str]] = []
        if isinstance(points, dict):
            for sample_rows in points.values():
                if isinstance(sample_rows, list):
                    samples.extend(sample_rows)

        if not samples:
            incomplete_rails.append(RAILS[key].label)
            continue

        if not all(as_bool(sample.get(field)) for sample in samples):
            failed_rails.append(RAILS[key].label)

    if failed_rails:
        return "FAIL", "Latest attempt contains one or more failed samples on: " + ", ".join(failed_rails)
    if incomplete_rails:
        return "INCOMPLETE", "Incomplete latest measurement attempt on: " + ", ".join(incomplete_rails)

    label = "voltage" if field == "voltage_pass" else "current"
    return "PASS", f"All six latest rail attempts satisfy the configured {label} acceptance criterion."



def _run_samples(run: Dict[str, object]) -> List[Dict[str, str]]:
    samples: List[Dict[str, str]] = []
    points = run.get("points", {})
    if isinstance(points, dict):
        for sample_rows in points.values():
            if isinstance(sample_rows, list):
                samples.extend(sample_rows)
    return samples


def _run_is_complete(run: Dict[str, object]) -> bool:
    return run.get("status") == "COMPLETE" and bool(_run_samples(run))


def _run_has_sweep(run: Dict[str, object]) -> bool:
    """Return True when a completed run contains multiple load-current points."""
    if not _run_is_complete(run):
        return False
    points = run.get("points", {})
    if not isinstance(points, dict):
        return False
    numeric = sorted(float(value) for value in points.keys())
    return len(numeric) >= 2 and (numeric[-1] - numeric[0]) > 0.05


def _run_epics_current_followed_load(run: Dict[str, object]) -> bool:
    """Use the recorded current-pass data to prove EPICS tracked the load sweep."""
    if not _run_has_sweep(run):
        return False
    samples = _run_samples(run)
    return bool(samples) and all(as_bool(row.get("current_pass")) for row in samples)


def _run_voltage_polarity_ok(run: Dict[str, object], rail: RailConfig) -> bool:
    samples = _run_samples(run)
    if not samples:
        return False
    values = [safe_float(row.get("ioc_voltage_v")) for row in samples]
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return False
    if rail.voltage_sign > 0:
        return all(value >= -0.05 for value in values)
    return all(value <= 0.05 for value in values)


def _negative_current_sign_ok(run: Dict[str, object]) -> bool:
    """Negative rails use a positive load-current magnitude in this firmware/test."""
    samples = _run_samples(run)
    if not samples:
        return False
    values_ma = [safe_float(row.get("ioc_current_ma")) for row in samples]
    values_ma = [value for value in values_ma if math.isfinite(value)]
    return bool(values_ma) and all(value >= -5.0 for value in values_ma)


def _latest_runs_for_dut(
    data_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> Dict[str, Tuple[str, Dict[str, object]]]:
    filtered = [
        row for row in data_rows
        if (not dut_id or row.get("dut_id", "") == dut_id)
    ]
    return latest_attempt_by_rail(run_records(filtered), dut_id)


def latest_rail_observations(
    data_rows: Sequence[Dict[str, str]],
    checklist_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> Dict[str, Dict[int, Dict[str, str]]]:
    """Return display observations matching each rail's latest measurement attempt."""

    latest_runs = _latest_runs_for_dut(data_rows, dut_id)
    latest_attempts: Dict[str, int] = {}
    for rail_key, (_, run) in latest_runs.items():
        meta = run.get("meta", {})
        if isinstance(meta, dict):
            try:
                latest_attempts[rail_key] = int(meta.get("attempt", "0") or 0)
            except (TypeError, ValueError):
                pass

    result: Dict[str, Dict[int, Dict[str, str]]] = defaultdict(dict)
    for row in checklist_rows:
        if row.get("record_type") != "RAIL_EVIDENCE":
            continue
        if dut_id and row.get("dut_id", "") != dut_id:
            continue
        test_id = row.get("test_id", "")
        if not test_id.startswith("RAIL-"):
            continue
        rail_key = test_id[5:]
        if rail_key not in RAILS or rail_key not in latest_attempts:
            continue
        try:
            attempt = int(row.get("attempt", "0") or 0)
            step_index = int(row.get("step_index", "0") or 0)
        except (TypeError, ValueError):
            continue
        if attempt != latest_attempts[rail_key] or step_index not in RAIL_OBSERVATION_NAME_BY_INDEX:
            continue
        result[rail_key][step_index] = row

    return dict(result)


def _aggregate_observation_all_rails(
    observations: Dict[str, Dict[int, Dict[str, str]]],
    observation_index: int,
) -> Optional[Tuple[str, str]]:
    """Aggregate an observation that must be confirmed for all six latest rail tests."""

    seen: List[Tuple[str, str]] = []
    for key in RAIL_ORDER:
        row = observations.get(key, {}).get(observation_index)
        if row is None:
            continue
        seen.append((RAILS[key].label, str(row.get("step_result", "")).upper()))

    failures = [label for label, result in seen if result == "FAIL"]
    if failures:
        return "FAIL", "Operator reported a failure on: " + ", ".join(failures)

    incompletes = [label for label, result in seen if result == "INCOMPLETE"]
    if incompletes:
        return "INCOMPLETE", "Operator marked incomplete on: " + ", ".join(incompletes)

    if len(seen) == len(RAIL_ORDER) and all(result in {"PASS", "N/A"} for _, result in seen):
        return "PASS", "Confirmed during the latest automated test of all six rails."

    return None


def _aggregate_observation_any_rail(
    observations: Dict[str, Dict[int, Dict[str, str]]],
    observation_index: int,
) -> Optional[Tuple[str, str]]:
    """Aggregate an observation where one successful demonstrated rail is sufficient."""

    seen: List[Tuple[str, str]] = []
    for key in RAIL_ORDER:
        row = observations.get(key, {}).get(observation_index)
        if row is None:
            continue
        seen.append((RAILS[key].label, str(row.get("step_result", "")).upper()))

    failures = [label for label, result in seen if result == "FAIL"]
    if failures:
        return "FAIL", "Operator reported a failure on: " + ", ".join(failures)
    passes = [label for label, result in seen if result == "PASS"]
    if passes:
        return "PASS", "Confirmed during rail test(s): " + ", ".join(passes)
    if seen:
        return "INCOMPLETE", "Available rail observation is incomplete."
    return None


def _manual_step_results_for_test(
    checklist_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
    test_id: str,
) -> Dict[int, Dict[str, str]]:
    latest = latest_checklist_by_test(checklist_rows, dut_id)
    if test_id not in latest:
        return {}
    _, run = latest[test_id]
    result: Dict[int, Dict[str, str]] = {}
    for row in run.get("steps", []):
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("step_index", "0") or 0)
        except (TypeError, ValueError):
            continue
        result[index] = row
    return result


def derive_automatic_step_results(
    test: SystemTestConfig,
    data_rows: Sequence[Dict[str, str]],
    checklist_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> Dict[int, Tuple[str, str]]:

    auto: Dict[int, Tuple[str, str]] = {}
    latest = _latest_runs_for_dut(data_rows, dut_id)
    observations = latest_rail_observations(data_rows, checklist_rows, dut_id)

    complete_keys = [key for key in RAIL_ORDER if key in latest and _run_is_complete(latest[key][1])]
    all_six_complete = len(complete_keys) == len(RAIL_ORDER)
    any_complete = bool(complete_keys)

    identity_all = _aggregate_observation_all_rails(observations, 1)
    updates_all = _aggregate_observation_all_rails(observations, 2)
    updates_any = _aggregate_observation_any_rail(observations, 2)
    agreement_all = _aggregate_observation_all_rails(observations, 3)
    limits_all = _aggregate_observation_all_rails(observations, 4)
    network_all = _aggregate_observation_all_rails(observations, 5)
    network_any = _aggregate_observation_any_rail(observations, 5)

    sweep_keys = [
        key for key in complete_keys
        if _run_epics_current_followed_load(latest[key][1])
    ]
    positive_sweep = any(RAILS[key].voltage_sign > 0 for key in sweep_keys)
    negative_sweep = any(RAILS[key].voltage_sign < 0 for key in sweep_keys)

    if test.test_id == "ST-01":
        if observations:
            auto[6] = ("PASS", "The operator interacted with the initialized GIGA Display during rail testing.")
        if identity_all:
            auto[7] = identity_all
        if any_complete:
            auto[8] = ("PASS", "A completed rail test required a running EPICS IOC.")
            auto[9] = ("PASS", "A completed rail test required successful IOC/monitor communication.")

    elif test.test_id == "ST-02":
        if identity_all:
            auto[1] = identity_all
            auto[2] = identity_all
            auto[3] = identity_all

        if all_six_complete and all(
            _run_voltage_polarity_ok(latest[key][1], RAILS[key])
            for key in RAIL_ORDER
        ):
            auto[4] = ("PASS", "Recorded IOC voltage data has the correct polarity on all six latest rail tests.")

        if all_six_complete and all(
            _negative_current_sign_ok(latest[key][1])
            for key in ("M5V", "M15V")
        ):
            auto[5] = ("PASS", "Both negative-rail IOC currents follow the positive load-current magnitude convention.")

    elif test.test_id == "ST-03":
        result, explanation = derive_accuracy_status(data_rows, dut_id, "voltage_pass")
        auto[1] = (result, explanation)
        auto[2] = (result, explanation)

    elif test.test_id == "ST-04":
        result, explanation = derive_accuracy_status(data_rows, dut_id, "current_pass")
        auto[1] = (result, explanation)
        auto[2] = (result, explanation)

    elif test.test_id == "ST-05":
        if sweep_keys:
            labels = ", ".join(RAILS[key].label for key in sweep_keys)
            auto[1] = ("PASS", f"Automated current sweeps were recorded on: {labels}.")
            auto[3] = ("PASS", f"EPICS current followed the programmed load sweep on: {labels}.")
        if updates_any:
            auto[2] = updates_any
            auto[4] = updates_any
        if all_six_complete:
            auto[5] = ("PASS", "All six latest rail tests completed without a Channel Access read failure.")

    elif test.test_id == "ST-06":
        if identity_all:
            auto[1] = identity_all
        if updates_all:
            auto[2] = updates_all
            auto[3] = updates_all
        if limits_all:
            auto[4] = limits_all
        if network_all:
            auto[5] = network_all

    elif test.test_id == "ST-07":
        if all_six_complete:
            auto[1] = ("PASS", "All six latest rail tests completed with a live Ethernet/IOC connection.")
            auto[4] = ("PASS", "Voltage/current PVs for all six rails were resolved and sampled successfully.")
        if any_complete:
            auto[2] = ("PASS", "A completed rail test required the EPICS IOC to be running.")
            auto[3] = ("PASS", "The IOC connection check and rail PV resolution succeeded during testing.")
        if agreement_all:
            auto[5] = agreement_all
        if sweep_keys:
            auto[6] = ("PASS", "Recorded EPICS current values followed at least one programmed load sweep.")
        if positive_sweep:
            auto[7] = ("PASS", "A positive rail completed a multi-point load sweep with valid EPICS updates.")
        if negative_sweep:
            auto[8] = ("PASS", "A negative rail completed a multi-point load sweep with valid EPICS updates.")

    elif test.test_id == "ST-10":
        if any_complete:
            auto[1] = ("PASS", "Normal monitor/IOC communication was established during rail testing.")
            auto[2] = ("PASS", "EPICS values were sampled successfully before any communication-recovery test.")

    elif test.test_id == "ST-11":
        filtered = [
            row for row in data_rows
            if (not dut_id or row.get("dut_id", "") == dut_id)
        ]
        all_runs = run_records(filtered)
        by_rail: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for run in all_runs.values():
            meta = run.get("meta", {})
            if isinstance(meta, dict) and meta.get("rail_key") in RAILS and _run_is_complete(run):
                by_rail[str(meta.get("rail_key"))].append(run)
        repeated = {key: runs for key, runs in by_rail.items() if len(runs) >= 2}
        if repeated:
            labels = ", ".join(RAILS[key].label for key in repeated)
            auto[1] = ("PASS", f"Multiple completed measurement attempts exist for: {labels}.")
            voltage_ok = all(
                all(as_bool(sample.get("voltage_pass")) for sample in _run_samples(run))
                for runs in repeated.values() for run in runs
            )
            current_ok = all(
                all(as_bool(sample.get("current_pass")) for sample in _run_samples(run))
                for runs in repeated.values() for run in runs
            )
            if voltage_ok:
                auto[3] = ("PASS", "Repeated voltage samples remain within the configured acceptance limit.")
            if current_ok:
                auto[4] = ("PASS", "Repeated current samples remain within the configured acceptance limit.")
            auto[5] = ("PASS", "Repeated attempts completed without an acquisition/communication abort.")

    elif test.test_id == "ST-12":
        if all_six_complete:
            auto[1] = ("PASS", "The complete measurement chain has been exercised successfully on all six rails.")
            auto[3] = ("PASS", "Ethernet/IOC communication was active while all six latest rail tests were acquired.")
        if identity_all and updates_all:
            auto[2] = ("PASS", "Local-display identity and update behavior were confirmed on all six latest rail tests.")
        if any_complete:
            auto[5] = ("PASS", "The Python test software successfully acquired and saved measurement data.")
        if sweep_keys and updates_any:
            auto[6] = ("PASS", "A load sweep was reflected in recorded EPICS data and confirmed on the local display.")

    for step_index in AUTO_ONLY_STEPS.get(test.test_id, ()):
        auto.setdefault(
            step_index,
            (
                "INCOMPLETE",
                "Awaiting evidence from the automated rail test and/or its in-test local-display prompts.",
            ),
        )

    return auto


def merged_test_step_results(
    test: SystemTestConfig,
    data_rows: Sequence[Dict[str, str]],
    checklist_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> List[Dict[str, str]]:

    automatic = derive_automatic_step_results(test, data_rows, checklist_rows, dut_id)
    manual = _manual_step_results_for_test(checklist_rows, dut_id, test.test_id)
    merged: List[Dict[str, str]] = []

    for index, step_text in enumerate(test.steps, start=1):
        if index in automatic:
            result, note = automatic[index]
            merged.append({
                "step_index": str(index),
                "step_text": step_text,
                "step_result": result,
                "source": "AUTO",
                "notes": note,
            })
            continue

        row = manual.get(index)
        if row is not None:
            merged.append({
                "step_index": str(index),
                "step_text": step_text,
                "step_result": str(row.get("step_result", "INCOMPLETE") or "INCOMPLETE").upper(),
                "source": "CHECKLIST",
                "notes": str(row.get("notes", "") or ""),
            })
            continue

        merged.append({
            "step_index": str(index),
            "step_text": step_text,
            "step_result": "INCOMPLETE",
            "source": "PENDING",
            "notes": "No automatic evidence or operator checklist result is available yet.",
        })

    return merged


def _effective_result_from_steps(steps: Sequence[Dict[str, str]]) -> str:
    results = [str(step.get("step_result", "INCOMPLETE") or "INCOMPLETE").upper() for step in steps]
    if any(result == "FAIL" for result in results):
        return "FAIL"
    if any(result == "INCOMPLETE" for result in results):
        return "INCOMPLETE"
    return "PASS"


def system_test_matrix_statuses(
    data_rows: Sequence[Dict[str, str]],
    checklist_rows: Sequence[Dict[str, str]],
    dut_id: Optional[str],
) -> Dict[str, Dict[str, str]]:
    

    latest_manual = latest_checklist_by_test(checklist_rows, dut_id)
    statuses: Dict[str, Dict[str, str]] = {}

    for test in SYSTEM_TESTS:
        merged_steps = merged_test_step_results(test, data_rows, checklist_rows, dut_id)
        effective = _effective_result_from_steps(merged_steps)
        auto_count = sum(1 for step in merged_steps if step["source"] == "AUTO")
        manual_count = sum(1 for step in merged_steps if step["source"] == "CHECKLIST")
        pending = [step for step in merged_steps if step["source"] == "PENDING"]
        failed = [step for step in merged_steps if step["step_result"] == "FAIL"]

        attempt = "—"
        classification = effective
        retest_outcome = ""
        if test.test_id in latest_manual:
            _, run = latest_manual[test.test_id]
            meta = run.get("meta", {})
            try:
                attempt = str(int(meta.get("attempt", "0") or 0)) if isinstance(meta, dict) else ""
            except (TypeError, ValueError):
                attempt = ""
            classification = str(run.get("test_result", effective) or effective).upper()
            retest_outcome = str(run.get("retest_outcome", "") or "").upper()

        source_parts = []
        if auto_count:
            source_parts.append(f"{auto_count} auto")
        if manual_count:
            source_parts.append(f"{manual_count} checklist")
        if pending:
            source_parts.append(f"{len(pending)} pending")
        source = " + ".join(source_parts) if source_parts else "No evidence"

        if failed:
            notes = "Failed step(s): " + "; ".join(
                f"{step['step_index']} {step['step_text']}" for step in failed
            )
        elif pending:
            notes = "Pending step(s): " + "; ".join(
                f"{step['step_index']} {step['step_text']}" for step in pending
            )
        else:
            notes = "All checklist steps are satisfied by automatic evidence and/or operator confirmation."

        statuses[test.test_id] = {
            "display": effective,
            "effective": effective,
            "attempt": attempt,
            "source": source,
            "notes": notes,
            "classification": classification,
            "retest_outcome": retest_outcome,
        }

    return statuses


def overall_system_test_status(statuses: Dict[str, Dict[str, str]]) -> str:
    effective = [statuses[test.test_id]["effective"] for test in SYSTEM_TESTS]
    if any(result == "FAIL" for result in effective):
        return "FAIL"
    if all(result == "PASS" for result in effective):
        return "PASS"
    return "INCOMPLETE"


