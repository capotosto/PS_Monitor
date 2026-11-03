from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Dict, List, Sequence

import epics
from Py_Instrument_Driver_Package.instrument_module.rigol_dl3000 import DL3000

from .checklist import prompt_and_record_rail_observations
from .config import USB_ADDRESS, RailConfig
from .storage import append_csv, next_attempt
from .utils import current_tolerance_a, fmt_num, now_timestamp, voltage_tolerance_v

class ChannelAccess:
    """Small pyepics Channel Access wrapper with a PV-object cache."""

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
        self._pvs: Dict[str, epics.PV] = {}

    def _pv(self, pv_name: str) -> epics.PV:
        pv = self._pvs.get(pv_name)
        if pv is None:
            pv = epics.PV(pv_name, connection_timeout=self.timeout)
            self._pvs[pv_name] = pv
        if not pv.wait_for_connection(timeout=self.timeout):
            raise RuntimeError(f"Could not connect to PV {pv_name}")
        return pv

    def read(self, pv_name: str) -> float:
        pv = self._pv(pv_name)
        value = pv.get(timeout=self.timeout, use_monitor=False)
        if value is None:
            raise RuntimeError(f"No response from PV {pv_name}")
        return float(value)

    def available(self, pv_name: str) -> bool:
        try:
            self._pv(pv_name)
            return True
        except Exception:
            return False


def normalize_prefix(prefix: str) -> str:
    return prefix.strip().rstrip(":")


def pv_name(prefix: str, channel: str, suffix: str) -> str:
    return f"{normalize_prefix(prefix)}:{channel}:{suffix}"


def resolve_ioc_channel(ca: ChannelAccess, prefix: str, rail: RailConfig) -> str:
    for alias in rail.ioc_channel_aliases:
        if ca.available(pv_name(prefix, alias, "VOLT")):
            return alias
    aliases = ", ".join(rail.ioc_channel_aliases)
    raise RuntimeError(
        f"Could not find the IOC VOLT PV for {rail.label}. Tried channel aliases: {aliases}"
    )


def read_ioc_snapshot(ca: ChannelAccess, prefix: str, channel: str) -> Dict[str, float]:
    return {
        "ioc_voltage_v": ca.read(pv_name(prefix, channel, "VOLT")),
        "ioc_voltage_raw_v": ca.read(pv_name(prefix, channel, "VOLT_RAW")),
        "ioc_current_ma": ca.read(pv_name(prefix, channel, "CURR")),
        "ioc_current_raw_a": ca.read(pv_name(prefix, channel, "CURR_RAW")),
    }


def discard_transition_readings(
    load,
    ca: ChannelAccess,
    ioc_prefix: str,
    channel: str,
    sample_interval_s: float,
) -> None:
    """Discard the first instrument/IOC readings after changing the load."""

    load.measure_voltage()
    load.measure_current()

    read_ioc_snapshot(
        ca,
        ioc_prefix,
        channel,
    )

    time.sleep(sample_interval_s)


def connect_load() -> DL3000:
    """Connect to the Rigol DL3021 and enable remote sense."""

    load = DL3000(
        connection_method="USB",
        address=USB_ADDRESS,
    )

    if getattr(load, "status", None) != "Connected":
        raise RuntimeError(
            f"Rigol electronic load did not connect at {USB_ADDRESS}."
        )

    load.set_sense("ON")

    if not load.get_sense():
        raise RuntimeError(
            "Rigol electronic-load remote sense did not enable."
        )

    return load


def rail_test_points(rail: RailConfig, fractions: Sequence[float]) -> List[float]:
    points = []
    for frac in fractions:
        value = round(float(frac) * rail.test_max_a, 6)
        if value not in points:
            points.append(value)
    return points


def wiring_text(rail: RailConfig) -> str:
    if rail.voltage_sign > 0:
        return (
            f"{rail.label}: connect DL3021 LOAD+ to the monitored rail OUTPUT/load side "
            "and LOAD- to that rail's isolated return. Connect S+ to the monitored rail "
            "voltage test point and S- to the isolated return."
        )

    return (
        f"{rail.label}: reverse the load connection so the DL3021 always sees positive "
        "input voltage: LOAD+ to the rail's isolated return (0 V side), and LOAD- to "
        f"the {rail.label} OUTPUT/load side. Connect S+ to the isolated return and S- "
        f"to the {rail.label} voltage test point. The script applies the negative sign "
        "to the voltage reference; current remains a positive load-current magnitude."
    )


def perform_rail_test(
    rail: RailConfig,
    load,
    ca: ChannelAccess,
    data_path: Path,
    checklist_path: Path,
    ioc_prefix: str,
    dut_id: str,
    operator: str,
    session_id: str,
    samples: int,
    settle_s: float,
    sample_interval_s: float,
    fractions: Sequence[float],
    notes: str = "",
) -> bool:
    ioc_prefix = normalize_prefix(ioc_prefix)
    connected_pv = f"{ioc_prefix}:CONNECTED"
    try:
        if int(round(ca.read(connected_pv))) != 1:
            raise RuntimeError(f"IOC reports {connected_pv} != 1 (not connected).")
    except Exception as exc:
        raise RuntimeError(f"IOC connection check failed: {exc}") from exc

    channel = resolve_ioc_channel(ca, ioc_prefix, rail)
    attempt = next_attempt(data_path, rail.key, dut_id)
    run_id = str(uuid.uuid4())
    rigol_idn = load.get_idn()

    print("\n" + "=" * 78)
    print(f"Testing {rail.label} — attempt {attempt}")
    print(wiring_text(rail))
    print(f"IOC channel resolved to: {channel}")
    print(f"Shunt: {rail.shunt_ohms * 1000:.1f} mΩ")
    print(f"Maximum test current: {rail.test_max_a:.3f} A")
    print("=" * 78)
    input("Verify the wiring and supply rating, then press Enter to continue (Ctrl+C aborts). ")

    base = {
        "timestamp": now_timestamp(),
        "session_id": session_id,
        "run_id": run_id,
        "attempt": attempt,
        "dut_id": dut_id,
        "operator": operator,
        "rail_key": rail.key,
        "rail_label": rail.label,
        "ioc_prefix": ioc_prefix,
        "ioc_channel": channel,
        "rigol_idn": rigol_idn,
        "notes": notes,
    }
    append_csv(data_path, {**base, "record_type": "RUN_START", "run_status": "RUNNING"})

    all_samples_pass = True
    completed = False
    try:
        # Use the DL3021 low current range. All configured capstone test points are <4 A.
        load.toggle_input("OFF")
        load.set_function_mode("FIX")
        load.set_function("CC")
        load.set_current_range(4)

        points = rail_test_points(rail, fractions)
        for point_index, setpoint_a in enumerate(points, start=1):
            if setpoint_a <= 0:
                load.toggle_input("OFF")
            else:
                load.set_current(setpoint_a)
                load.toggle_input("ON")

            time.sleep(settle_s)

            discard_transition_readings(
                load,
                ca,
                ioc_prefix,
                channel,
                sample_interval_s,
            )

            print(f"\n{rail.label} point {point_index}/{len(points)}: {setpoint_a:.4f} A")

            for sample_index in range(1, samples + 1):
                rigol_v_mag = float(load.measure_voltage())
                rigol_i = abs(float(load.measure_current()))
                snap = read_ioc_snapshot(ca, ioc_prefix, channel)

                # Remote sense measures the DUT voltage directly at the selected
                # rail voltage test point, so no lead-drop or shunt-drop correction
                # is applied to the Rigol voltage measurement.
                ref_v = rail.voltage_sign * rigol_v_mag
                ref_i = rigol_i

                ioc_v = snap["ioc_voltage_v"]
                ioc_i_a = snap["ioc_current_ma"] / 1000.0
                v_err = ioc_v - ref_v
                i_err = ioc_i_a - ref_i
                v_tol = voltage_tolerance_v(ref_v)
                i_tol = current_tolerance_a(ref_i, rail)
                v_pass = abs(v_err) <= v_tol
                i_pass = abs(i_err) <= i_tol
                sample_pass = v_pass and i_pass
                all_samples_pass &= sample_pass

                record = {
                    **base,
                    "record_type": "SAMPLE",
                    "timestamp": now_timestamp(),
                    "run_status": "RUNNING",
                    "setpoint_a": fmt_num(setpoint_a, 6),
                    "sample_index": sample_index,
                    "load_input_on": int(setpoint_a > 0),
                    "rigol_voltage_v": fmt_num(rigol_v_mag, 6),
                    "rigol_current_a": fmt_num(rigol_i, 6),
                    "voltage_reference_v": fmt_num(ref_v, 6),
                    "current_reference_a": fmt_num(ref_i, 6),
                    "ioc_voltage_v": fmt_num(ioc_v, 6),
                    "ioc_voltage_raw_v": fmt_num(snap["ioc_voltage_raw_v"], 6),
                    "ioc_current_ma": fmt_num(snap["ioc_current_ma"], 6),
                    "ioc_current_raw_a": fmt_num(snap["ioc_current_raw_a"], 6),
                    "voltage_error_v": fmt_num(v_err, 6),
                    "current_error_a": fmt_num(i_err, 6),
                    "voltage_tolerance_v": fmt_num(v_tol, 6),
                    "current_tolerance_a": fmt_num(i_tol, 6),
                    "voltage_pass": int(v_pass),
                    "current_pass": int(i_pass),
                    "sample_pass": int(sample_pass),
                }
                append_csv(data_path, record)

                print(
                    f"  sample {sample_index}: "
                    f"Vref={ref_v:+.4f} V, IOC={ioc_v:+.4f} V, Δ={v_err:+.4f} V "
                    f"({'PASS' if v_pass else 'FAIL'}); "
                    f"Iref={ref_i:.4f} A, IOC={ioc_i_a:.4f} A, Δ={i_err:+.4f} A "
                    f"({'PASS' if i_pass else 'FAIL'})"
                )
                if sample_index < samples:
                    time.sleep(sample_interval_s)

        completed = True
        append_csv(
            data_path,
            {
                **base,
                "record_type": "RUN_END",
                "timestamp": now_timestamp(),
                "run_status": "COMPLETE",
                "run_pass": int(all_samples_pass),
            },
        )
        print(f"\n{rail.label} attempt {attempt}: {'PASS' if all_samples_pass else 'FAIL'}")

        # Capture the local-display observations while the test setup is still
        # in front of the operator.  These answers are kept separately from the
        # raw measurement CSV and are used to auto-fill ST-02/ST-05/ST-06/ST-07
        # and portions of the other Chapter 6 checklist items.
        try:
            prompt_and_record_rail_observations(
                checklist_path=checklist_path,
                rail=rail,
                dut_id=dut_id,
                operator=operator,
                session_id=session_id,
                measurement_run_id=run_id,
                measurement_attempt=attempt,
            )
        except KeyboardInterrupt:
            print("\nDisplay-observation prompts skipped; the rail measurement data remains saved.")

        return all_samples_pass

    except KeyboardInterrupt:
        print("\nTest aborted by operator.")
        raise
    finally:
        try:
            load.toggle_input("OFF")
        except Exception:
            pass
        if not completed:
            append_csv(
                data_path,
                {
                    **base,
                    "record_type": "RUN_END",
                    "timestamp": now_timestamp(),
                    "run_status": "ABORTED",
                    "run_pass": "",
                    "notes": (notes + " | " if notes else "") + "Run aborted or terminated before completion.",
                },
            )


