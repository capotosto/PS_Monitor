"""cli.py
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Optional, Tuple

from .analysis import latest_attempt_by_rail, overall_system_test_status, run_records, \
    system_test_matrix_statuses
from .checklist import run_system_test_checklist
from .config import (
    DEFAULT_CHECKLIST_FILE, DEFAULT_DATA_FILE, DEFAULT_IOC_PREFIX, DEFAULT_REPORT_FILE,
    DEFAULT_TEST_FRACTIONS, RAILS, RAIL_ORDER, SYSTEM_TESTS, USB_ADDRESS,
)
from .report import generate_report
from .storage import load_checklist_csv, load_csv


def print_status(
    data_path: Path,
    checklist_path: Path,
    dut_id: Optional[str],
) -> None:
    rows = load_csv(data_path) if data_path.exists() else []
    if dut_id:
        rows = [r for r in rows if r.get("dut_id", "") == dut_id]

    runs = run_records(rows)
    latest = latest_attempt_by_rail(runs, dut_id)

    print("\nLatest measurement attempt by rail:")
    for key in RAIL_ORDER:
        rail = RAILS[key]
        if key not in latest:
            print(f"  {rail.label:>5}: NOT TESTED")
            continue
        _, run = latest[key]
        meta = run.get("meta", {})
        attempt = meta.get("attempt", "") if isinstance(meta, dict) else ""
        run_status = str(run.get("status", "INCOMPLETE"))
        run_pass = run.get("run_pass")

        if run_pass is True and run_status == "COMPLETE":
            status = "PASS"
        elif run_pass is False and run_status == "COMPLETE":
            status = "FAIL"
        else:
            status = run_status

        print(f"  {rail.label:>5}: attempt {attempt} — {status}")

    checklist_rows = load_checklist_csv(checklist_path)
    if dut_id:
        checklist_rows = [r for r in checklist_rows if r.get("dut_id", "") == dut_id]
    matrix = system_test_matrix_statuses(rows, checklist_rows, dut_id)

    print("\nSystem test matrix:")
    for test in SYSTEM_TESTS:
        status = matrix[test.test_id]
        attempt = status["attempt"]
        suffix = f" attempt {attempt}" if attempt not in {"", "—"} else ""
        print(f"  {test.test_id} {test.name:<28} {status['display']}{suffix}")

    print(f"\nOverall system test status: {overall_system_test_status(matrix)}")


def choose_rail() -> Optional[str]:
    print("\nSelect rail to test:")
    for idx, key in enumerate(RAIL_ORDER, start=1):
        rail = RAILS[key]
        print(f"  {idx}. {rail.label:>5}   max test current {rail.test_max_a:.3f} A")
    print("  0. Cancel")
    value = input("Choice: ").strip()
    if value == "0" or not value:
        return None
    try:
        idx = int(value)
    except ValueError:
        print("Invalid choice.")
        return None
    if not 1 <= idx <= len(RAIL_ORDER):
        print("Invalid choice.")
        return None
    return RAIL_ORDER[idx - 1]


def parse_fractions(text: str) -> Tuple[float, ...]:
    vals = []
    for part in text.split(","):
        val = float(part.strip())
        if val < 0 or val > 1.0:
            raise argparse.ArgumentTypeError(
                "Test fractions must be between 0 and 1.0 for the planned operating-range test."
            )
        vals.append(val)
    if not vals:
        raise argparse.ArgumentTypeError("At least one test fraction is required.")
    return tuple(vals)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Execute the capstone system test plan and rail voltage/current verification.")
    p.add_argument("--data", default=DEFAULT_DATA_FILE, help="Append-only raw rail-measurement CSV data file.")
    p.add_argument("--checklist", default=DEFAULT_CHECKLIST_FILE, help="Append-only system-test checklist CSV file.")
    p.add_argument("--pdf", default=DEFAULT_REPORT_FILE, help="Base PDF report path; a timestamp is appended to the filename.")
    p.add_argument("--report-only", action="store_true", help="Generate the PDF from saved rail/checklist data; do not connect to hardware.")
    p.add_argument("--checklist-only", action="store_true", help="Fill/update the system-test checklist without connecting to the DL3021 or IOC.")
    p.add_argument("--dut", default="", help="DUT/board serial or identifier. Prompted if omitted during acquisition.")
    p.add_argument("--operator", default="", help="Operator name/initials. Prompted if omitted during acquisition.")
    p.add_argument("--ioc-prefix", default=DEFAULT_IOC_PREFIX, help="IOC prefix without trailing colon (default TEST:GIGA).")
    p.add_argument("--rail", choices=RAIL_ORDER, help="Test one rail non-interactively after the wiring confirmation.")
    p.add_argument("--samples", type=int, default=5, help="Samples per current point (default 5).")
    p.add_argument("--settle", type=float, default=1.0, help="Settling time after changing load current, seconds.")
    p.add_argument("--sample-interval", type=float, default=0.20, help="Delay between samples, seconds.")
    p.add_argument(
        "--fractions",
        type=parse_fractions,
        default=DEFAULT_TEST_FRACTIONS,
        help="Comma-separated fractions of each rail's max test current (default 0.0 through 1.0 in 0.10 steps).",
    )
    p.add_argument("--notes", default="", help="Notes stored with each run in this invocation.")
    return p


def connect_test_hardware():
    """Lazily import and connect the hardware-only dependencies."""
    from .hardware import ChannelAccess, connect_load

    print("Connecting to Rigol DL3021...")
    print(f"USB address: {USB_ADDRESS}")
    load = connect_load()
    print(f"Connected: {load.get_idn()}")
    print("Rigol remote sense: ON")

    print("Initializing EPICS Channel Access with pyepics...")
    ca = ChannelAccess(timeout=2.0)
    print("pyepics Channel Access initialized.")
    return load, ca


def main() -> int:
    args = build_arg_parser().parse_args()
    data_path = Path(args.data)
    checklist_path = Path(args.checklist)
    pdf_path = Path(args.pdf)

    if args.report_only:
        generate_report(data_path, checklist_path, pdf_path, args.dut or None)
        return 0

    if args.samples < 1:
        raise SystemExit("--samples must be >= 1")

    dut_id = args.dut.strip() or input("DUT / board identifier: ").strip() or "UNSPECIFIED"
    operator = args.operator.strip() or input("Operator name/initials: ").strip() or "UNSPECIFIED"
    session_id = str(uuid.uuid4())

    if args.checklist_only:
        run_system_test_checklist(data_path, checklist_path, dut_id, operator, session_id)
        if data_path.exists() or checklist_path.exists():
            try:
                generate_report(data_path, checklist_path, pdf_path, dut_id)
            except Exception as exc:
                print(f"Report generation warning: {exc}")
        return 0

    # Hardware remains disconnected until T or --rail explicitly requests it.
    load = None
    ca = None

    try:
        if args.rail:
            from .hardware import perform_rail_test
            load, ca = connect_test_hardware()
            perform_rail_test(
                RAILS[args.rail], load, ca, data_path, checklist_path, args.ioc_prefix,
                dut_id, operator, session_id, args.samples, args.settle,
                args.sample_interval, args.fractions, args.notes,
            )
            generate_report(data_path, checklist_path, pdf_path, dut_id)
            return 0

        while True:
            print("\n" + "-" * 72)
            print("Capstone System Test")
            print("  T  Test/re-test one rail")
            print("  C  Fill/update Chapter 6 system-test checklist")
            print("  S  Show current rail and system-test status")
            print("  R  Generate consolidated PDF system-test report")
            print("  Q  Quit")
            choice = input("Choice: ").strip().upper()

            if choice == "T":
                key = choose_rail()
                if not key:
                    continue
                if load is None or ca is None:
                    try:
                        load, ca = connect_test_hardware()
                    except Exception as exc:
                        load = None
                        ca = None
                        print(f"HARDWARE CONNECTION ERROR: {exc}")
                        print("Returning to the menu. C, S, and R remain available offline.")
                        continue
                try:
                    from .hardware import perform_rail_test
                    perform_rail_test(
                        RAILS[key], load, ca, data_path, checklist_path, args.ioc_prefix,
                        dut_id, operator, session_id, args.samples, args.settle,
                        args.sample_interval, args.fractions, args.notes,
                    )
                except KeyboardInterrupt:
                    print("Returned to menu; electronic-load input has been turned OFF.")
                except Exception as exc:
                    print(f"TEST ERROR: {exc}")

            elif choice == "C":
                run_system_test_checklist(data_path, checklist_path, dut_id, operator, session_id)
            elif choice == "S":
                print_status(data_path, checklist_path, dut_id)
            elif choice == "R":
                try:
                    generate_report(data_path, checklist_path, pdf_path, dut_id)
                except Exception as exc:
                    print(f"Report generation error: {exc}")
            elif choice == "Q":
                break
            else:
                print("Invalid choice.")
    finally:
        if load is not None:
            try:
                load.toggle_input("OFF")
            except Exception:
                pass

    if data_path.exists() or checklist_path.exists():
        try:
            generate_report(data_path, checklist_path, pdf_path, dut_id)
        except Exception as exc:
            print(f"Report generation warning: {exc}")
    return 0
