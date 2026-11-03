from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

from .analysis import derive_automatic_step_results, system_test_matrix_statuses
from .config import RAIL_OBSERVATION_PROMPTS, SYSTEM_TESTS, RailConfig, SystemTestConfig
from .storage import (
    append_checklist_csv, effective_checklist_result, latest_checklist_by_test,
    load_checklist_csv, load_csv, next_checklist_attempt,
)
from .utils import now_timestamp

def prompt_and_record_rail_observations(
    checklist_path: Path,
    rail: RailConfig,
    dut_id: str,
    operator: str,
    session_id: str,
    measurement_run_id: str,
    measurement_attempt: int,
) -> None:
    """Prompt for local-display observations made during one rail test.

    The automated test already proves the IOC connection and records the EPICS
    voltage/current values.  These prompts therefore ask only for information
    that cannot be obtained through Channel Access: what the operator sees on
    the local GIGA Display.
    """

    print("\nLocal display observations for this rail")
    print("These answers will auto-fill the Chapter 6 checklist where applicable.")

    for index, observation_name, prompt_template in RAIL_OBSERVATION_PROMPTS:
        prompt_text = prompt_template.format(rail=rail.label)
        result = prompt_step_result(prompt_text)
        append_checklist_csv(
            checklist_path,
            {
                "record_type": "RAIL_EVIDENCE",
                "timestamp": now_timestamp(),
                "session_id": session_id,
                "test_run_id": measurement_run_id,
                "attempt": measurement_attempt,
                "dut_id": dut_id,
                "operator": operator,
                "test_id": f"RAIL-{rail.key}",
                "test_name": rail.label,
                "step_index": index,
                "step_text": f"[{observation_name}] {prompt_text}",
                "step_result": result,
                "source": "RAIL_TEST_PROMPT",
            },
        )


def prompt_step_result(step_text: str) -> str:
    """Prompt one checklist item and return PASS/FAIL/INCOMPLETE/N/A."""

    while True:
        value = input(f"  {step_text} [Y/n/i/a]: ").strip().lower()
        if value in {"", "y", "yes", "p", "pass"}:
            return "PASS"
        if value in {"n", "no", "f", "fail"}:
            return "FAIL"
        if value in {"i", "incomplete"}:
            return "INCOMPLETE"
        if value in {"a", "na", "n/a"}:
            return "N/A"
        print("    Enter Y/Enter=pass, N=fail, I=incomplete, or A=not applicable.")


def prompt_result_override(suggested: str) -> str:
    while True:
        value = input(
            f"Suggested result: {suggested}. Press Enter to accept, or enter P/F/I to override: "
        ).strip().lower()
        if not value:
            return suggested
        if value in {"p", "pass"}:
            return "PASS"
        if value in {"f", "fail"}:
            return "FAIL"
        if value in {"i", "incomplete"}:
            return "INCOMPLETE"
        print("Enter P, F, I, or press Enter to accept the suggested result.")


def previous_checklist_effective_result(
    checklist_path: Path,
    test_id: str,
    dut_id: str,
) -> Optional[str]:
    rows = load_checklist_csv(checklist_path)
    latest = latest_checklist_by_test(rows, dut_id)
    if test_id not in latest:
        return None
    return effective_checklist_result(latest[test_id][1])


def conduct_system_test_item(
    test: SystemTestConfig,
    data_path: Path,
    checklist_path: Path,
    dut_id: str,
    operator: str,
    session_id: str,
) -> str:
    """Execute/fill one system-test item, auto-filling any supported steps."""

    previous_effective = previous_checklist_effective_result(checklist_path, test.test_id, dut_id)
    attempt = next_checklist_attempt(checklist_path, test.test_id, dut_id)
    test_run_id = str(uuid.uuid4())

    data_rows = load_csv(data_path) if data_path.exists() else []
    checklist_rows = load_checklist_csv(checklist_path)
    automatic = derive_automatic_step_results(test, data_rows, checklist_rows, dut_id)

    print("\n" + "=" * 78)
    print(f"{test.test_id}: {test.name} — checklist attempt {attempt}")
    print(f"Method: {test.method}")
    print(f"Pass criterion: {test.pass_criterion}")
    if previous_effective:
        print(f"Previous effective result: {previous_effective}")
    if automatic:
        print(f"Automatic evidence available for {len(automatic)} of {len(test.steps)} checklist steps.")
    print("=" * 78)

    base = {
        "timestamp": now_timestamp(),
        "session_id": session_id,
        "test_run_id": test_run_id,
        "attempt": attempt,
        "dut_id": dut_id,
        "operator": operator,
        "test_id": test.test_id,
        "test_name": test.name,
        "source": "AUTO+MANUAL" if automatic else "MANUAL",
    }
    append_checklist_csv(checklist_path, {**base, "record_type": "TEST_START"})

    step_results: List[str] = []

    for index, step in enumerate(test.steps, start=1):
        if index in automatic:
            result, explanation = automatic[index]
            step_results.append(result)
            print(f"  {index:2d}. [AUTO {result}] {step}")
            print(f"      {explanation}")
            append_checklist_csv(
                checklist_path,
                {
                    **base,
                    "record_type": "STEP",
                    "timestamp": now_timestamp(),
                    "step_index": index,
                    "step_text": step,
                    "step_result": result,
                    "source": "AUTO",
                    "notes": explanation,
                },
            )
            continue

        result = prompt_step_result(step)
        step_results.append(result)
        append_checklist_csv(
            checklist_path,
            {
                **base,
                "record_type": "STEP",
                "timestamp": now_timestamp(),
                "step_index": index,
                "step_text": step,
                "step_result": result,
                "source": "MANUAL",
            },
        )

    if any(result == "FAIL" for result in step_results):
        suggested = "FAIL"
    elif any(result == "INCOMPLETE" for result in step_results):
        suggested = "INCOMPLETE"
    else:
        suggested = "PASS"

    outcome = prompt_result_override(suggested)
    notes = input("Operator notes for this test (optional): ").strip()

    is_retest = attempt > 1 and previous_effective in {"FAIL", "INCOMPLETE"}
    if is_retest:
        classification = "RETEST"
        retest_outcome = outcome
    else:
        classification = outcome
        retest_outcome = ""

    append_checklist_csv(
        checklist_path,
        {
            **base,
            "record_type": "TEST_END",
            "timestamp": now_timestamp(),
            "test_result": classification,
            "retest_outcome": retest_outcome,
            "notes": notes,
        },
    )

    display = f"RETEST — {outcome}" if classification == "RETEST" else outcome
    print(f"Recorded {test.test_id}: {display}")
    return outcome


def print_suspension_criteria() -> None:
    print("\nSuspend testing immediately for overheating, suspected shorts/incorrect wiring,")
    print("operation outside test-equipment ratings, unstable supply output, unintended-load")
    print("firmware behavior, loss of required isolation, or any condition that could damage")
    print("the prototype or test equipment.")


def choose_system_test() -> Optional[SystemTestConfig]:
    print("\nSystem test checklist:")
    for index, test in enumerate(SYSTEM_TESTS, start=1):
        auto = " [auto-filled where evidence is available]" if test.test_id in {"ST-02", "ST-03", "ST-04", "ST-05", "ST-06", "ST-07"} else ""
        print(f"  {index:2d}. {test.test_id}  {test.name}{auto}")
    print("   A. Walk through all tests that are not currently PASS")
    print("   0. Cancel")

    value = input("Choice: ").strip().upper()
    if value in {"", "0"}:
        return None
    if value == "A":
        # Caller handles this special selection.
        return SystemTestConfig("ALL", "ALL", "", "", tuple())
    try:
        index = int(value)
    except ValueError:
        print("Invalid choice.")
        return None
    if not 1 <= index <= len(SYSTEM_TESTS):
        print("Invalid choice.")
        return None
    return SYSTEM_TESTS[index - 1]


def run_system_test_checklist(
    data_path: Path,
    checklist_path: Path,
    dut_id: str,
    operator: str,
    session_id: str,
) -> None:
    print_suspension_criteria()
    selected = choose_system_test()
    if selected is None:
        return

    if selected.test_id != "ALL":
        conduct_system_test_item(
            selected, data_path, checklist_path, dut_id, operator, session_id
        )
        return

    data_rows = load_csv(data_path) if data_path.exists() else []
    checklist_rows = load_checklist_csv(checklist_path)
    statuses = system_test_matrix_statuses(data_rows, checklist_rows, dut_id)
    pending = [
        test for test in SYSTEM_TESTS
        if statuses[test.test_id]["effective"] != "PASS"
    ]

    if not pending:
        print("All system tests currently have an effective PASS result.")
        return

    for test in pending:
        print(f"\nNext: {test.test_id} {test.name}")
        answer = input("Run/fill this checklist item now? [Y/n/q]: ").strip().lower()
        if answer in {"q", "quit"}:
            break
        if answer in {"n", "no"}:
            continue
        conduct_system_test_item(
            test, data_path, checklist_path, dut_id, operator, session_id
        )


