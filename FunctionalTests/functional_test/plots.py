from __future__ import annotations

import math
from io import BytesIO
from typing import Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analysis import mean_field
from .config import RailConfig
from .utils import current_tolerance_a, run_disposition, voltage_tolerance_v

STATUS_FILL_MPL = {
    "PASS": "#EEF7EA",
    "FAIL": "#FCEBEC",
    "INCOMPLETE": "#FFF8DC",
}

def apply_plot_status_highlight(axis, run: Dict[str, object]) -> None:
    """Tint a rail plot according to its latest run disposition."""
    category = run_disposition(run)
    axis.set_facecolor(STATUS_FILL_MPL[category])

def build_rail_voltage_plot(
    rail: RailConfig,
    run: Dict[str, object],
) -> BytesIO:
    """Build the rail-voltage ideal-versus-measured report plot."""

    setpoints = []
    ioc_voltage = []
    eload_sense_voltage = []

    points = run.get("points", {})

    if not isinstance(points, dict):
        raise RuntimeError(
            f"No point data available for {rail.label} voltage plot."
        )

    for setpoint in sorted(points.keys()):
        samples_at_point = points[setpoint]

        if (
            not isinstance(samples_at_point, list)
            or not samples_at_point
        ):
            continue

        ioc_value = mean_field(
            samples_at_point,
            "ioc_voltage_v",
        )

        eload_value = mean_field(
            samples_at_point,
            "voltage_reference_v",
        )

        if (
            not math.isfinite(ioc_value)
            or not math.isfinite(eload_value)
        ):
            continue

        setpoints.append(float(setpoint))
        ioc_voltage.append(ioc_value)
        eload_sense_voltage.append(eload_value)

    if not setpoints:
        raise RuntimeError(
            f"Not enough data available for {rail.label} voltage plot."
        )

    ideal_voltage = [
        rail.nominal_v
        for _ in setpoints
    ]

    voltage_tol = voltage_tolerance_v(
        rail.nominal_v
    )

    voltage_upper = [
        rail.nominal_v + voltage_tol
        for _ in setpoints
    ]

    voltage_lower = [
        rail.nominal_v - voltage_tol
        for _ in setpoints
    ]

    figure = plt.figure(
        figsize=(9.0, 3.4),
    )

    axis = figure.add_subplot(111)
    apply_plot_status_highlight(axis, run)

    axis.fill_between(
        setpoints,
        voltage_lower,
        voltage_upper,
        alpha=0.20,
        label=f"Voltage tolerance band (±{voltage_tol:.3f} V)",
    )

    axis.plot(
        setpoints,
        ideal_voltage,
        linestyle="--",
        label="Ideal rail voltage",
    )

    axis.plot(
        setpoints,
        eload_sense_voltage,
        marker="o",
        label="E-load sense voltage",
    )

    axis.plot(
        setpoints,
        ioc_voltage,
        marker="o",
        label="IOC measured voltage",
    )

    axis.set_title(
        f"{rail.label} Voltage - Ideal vs Measured"
    )

    axis.set_xlabel(
        "Electronic-load setpoint (A)"
    )

    axis.set_ylabel(
        "Voltage (V)"
    )

    axis.grid(True)
    axis.legend()

    figure.tight_layout()

    image_buffer = BytesIO()

    figure.savefig(
        image_buffer,
        format="png",
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(figure)
    image_buffer.seek(0)
    return image_buffer


def build_rail_current_plot(
    rail: RailConfig,
    run: Dict[str, object],
) -> BytesIO:
    """Build the rail-current ideal-versus-measured report plot."""

    setpoints = []
    measured_current = []

    points = run.get("points", {})

    if not isinstance(points, dict):
        raise RuntimeError(
            f"No point data available for {rail.label} current plot."
        )

    for setpoint in sorted(points.keys()):
        samples_at_point = points[setpoint]

        if (
            not isinstance(samples_at_point, list)
            or not samples_at_point
        ):
            continue

        ioc_current_ma = mean_field(
            samples_at_point,
            "ioc_current_ma",
        )

        if not math.isfinite(ioc_current_ma):
            continue

        setpoints.append(float(setpoint))
        measured_current.append(
            ioc_current_ma / 1000.0
        )

    if not setpoints:
        raise RuntimeError(
            f"Not enough data available for {rail.label} current plot."
        )

    ideal_current = list(setpoints)

    current_upper = []
    current_lower = []

    for setpoint in setpoints:
        current_tol = current_tolerance_a(
            setpoint,
            rail,
        )

        current_upper.append(
            setpoint + current_tol
        )

        current_lower.append(
            setpoint - current_tol
        )

    figure = plt.figure(
        figsize=(9.0, 4.4),
    )

    axis = figure.add_subplot(111)
    apply_plot_status_highlight(axis, run)

    axis.fill_between(
        setpoints,
        current_lower,
        current_upper,
        alpha=0.25,
        label="Current tolerance band",
    )

    axis.plot(
        setpoints,
        ideal_current,
        linestyle="--",
        label="Ideal e-load setpoint",
    )

    axis.plot(
        setpoints,
        measured_current,
        marker="o",
        label="IOC measured current",
    )

    axis.set_title(
        f"{rail.label} Current - Ideal vs Measured"
    )

    axis.set_xlabel(
        "Electronic-load setpoint (A)"
    )

    axis.set_ylabel(
        "Current (A)"
    )

    axis.grid(True)
    axis.legend()

    figure.tight_layout()

    image_buffer = BytesIO()

    figure.savefig(
        image_buffer,
        format="png",
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(figure)
    image_buffer.seek(0)
    return image_buffer


def build_rail_current_error_plot(
    rail: RailConfig,
    run: Dict[str, object],
) -> BytesIO:
    """Build a magnified current-error plot showing the tolerance clearly."""

    setpoints = []
    current_error_ma = []
    tolerance_ma = []

    points = run.get("points", {})

    if not isinstance(points, dict):
        raise RuntimeError(
            f"No point data available for {rail.label} current error plot."
        )

    for setpoint in sorted(points.keys()):
        samples_at_point = points[setpoint]

        if (
            not isinstance(samples_at_point, list)
            or not samples_at_point
        ):
            continue

        ioc_current_ma = mean_field(
            samples_at_point,
            "ioc_current_ma",
        )

        if not math.isfinite(ioc_current_ma):
            continue

        setpoint_a = float(setpoint)

        setpoints.append(setpoint_a)

        current_error_ma.append(
            ioc_current_ma
            - (setpoint_a * 1000.0)
        )

        tolerance_ma.append(
            current_tolerance_a(
                setpoint_a,
                rail,
            )
            * 1000.0
        )

    if not setpoints:
        raise RuntimeError(
            f"Not enough data available for {rail.label} current error plot."
        )

    positive_tolerance = list(tolerance_ma)

    negative_tolerance = [
        -value
        for value in tolerance_ma
    ]

    all_values = (
        current_error_ma
        + positive_tolerance
        + negative_tolerance
    )

    largest_value = max(
        abs(value)
        for value in all_values
    )

    y_limit = max(
        25.0,
        largest_value * 1.20,
    )

    figure = plt.figure(
        figsize=(9.0, 4.2),
    )

    axis = figure.add_subplot(111)
    apply_plot_status_highlight(axis, run)

    axis.fill_between(
        setpoints,
        negative_tolerance,
        positive_tolerance,
        alpha=0.25,
        label="Allowed tolerance",
    )

    axis.axhline(
        0.0,
        linestyle="--",
        label="Ideal error = 0 mA",
    )

    axis.plot(
        setpoints,
        current_error_ma,
        marker="o",
        color="red",
        label="IOC current error",
    )

    axis.set_ylim(
        -y_limit,
        y_limit,
    )

    axis.set_title(
        f"{rail.label} Current Error - Tolerance Magnified"
    )

    axis.set_xlabel(
        "Electronic-load setpoint (A)"
    )

    axis.set_ylabel(
        "Current error (mA)"
    )

    axis.grid(True)
    axis.legend()

    figure.tight_layout()

    image_buffer = BytesIO()

    figure.savefig(
        image_buffer,
        format="png",
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(figure)
    image_buffer.seek(0)
    return image_buffer


