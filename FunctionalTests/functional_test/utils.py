from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Dict

from .config import (
    CURRENT_PERCENT_TOL, LTC2945_SENSE_FULL_SCALE_V, LTC2945_TUE_FS,
    LTC2945_VIN_FULL_SCALE_V, SHUNT_TOLERANCE, VOLTAGE_ABS_FLOOR_V,
    VOLTAGE_PERCENT_TOL, RailConfig,
)

def compact_instrument_id(idn: str) -> str:
    """Keep only manufacturer, model, and serial number from a SCPI *IDN? reply.

    A normal *IDN? response is manufacturer,model,serial,firmware.  The firmware
    field is not needed in the report and can make the metadata table overflow.
    """
    text = str(idn or "").strip()
    if not text:
        return text
    parts = [part.strip() for part in text.split(",")]
    if len(parts) >= 3:
        return ", ".join(parts[:3])
    return text


def run_disposition(run: Dict[str, object]) -> str:
    """Return PASS, FAIL, or INCOMPLETE for one rail run."""
    status = str(run.get("status", "INCOMPLETE") or "INCOMPLETE").upper()
    run_pass = run.get("run_pass")
    if status == "COMPLETE" and run_pass is True:
        return "PASS"
    if status == "COMPLETE" and run_pass is False:
        return "FAIL"
    return "INCOMPLETE"

def now_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def timestamped_report_path(pdf_path: Path) -> Path:
    """Return a report filename with the current timestamp appended."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if pdf_path.suffix:
        suffix = pdf_path.suffix
        stem = pdf_path.stem
    else:
        suffix = ".pdf"
        stem = pdf_path.name

    return pdf_path.with_name(
        f"{stem}_{timestamp}{suffix}"
    )


def as_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass"}


def safe_float(value, default=float("nan")) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_num(value: float, places: int = 4) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{places}f}"


def voltage_tolerance_v(reference_v: float) -> float:
    """Acceptance tolerance for the voltage comparison."""
    return max(VOLTAGE_ABS_FLOOR_V, VOLTAGE_PERCENT_TOL * abs(reference_v))


def current_tolerance_a(reference_a: float, rail: RailConfig) -> float:
    """Acceptance tolerance for the current comparison."""
    return max(rail.current_floor_a, CURRENT_PERCENT_TOL * abs(reference_a))


def ltc2945_current_datasheet_error_a(reference_a: float, rail: RailConfig) -> float:
    """Approximate worst-case sensor-chain current error before added wiring margin.

    Components included:
       LTC2945 delta-sense TUE: 0.75 % of 102.4 mV full scale
       1 % current-sense resistor tolerance
    """
    adc_abs_a = (LTC2945_TUE_FS * LTC2945_SENSE_FULL_SCALE_V) / rail.shunt_ohms
    shunt_gain_a = SHUNT_TOLERANCE * abs(reference_a)
    return adc_abs_a + shunt_gain_a


def ltc2945_voltage_datasheet_error_v() -> float:
    """LTC2945 guaranteed VIN TUE expressed as an absolute full-scale error."""
    return LTC2945_TUE_FS * LTC2945_VIN_FULL_SCALE_V


