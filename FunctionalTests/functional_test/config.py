from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

USB_ADDRESS = "USB0::0x1AB1::0x0E11::DL3A284M00251::INSTR"
DEFAULT_DATA_FILE = "capstone_rail_test_raw.csv"
DEFAULT_REPORT_FILE = "capstone_rail_test_report.pdf"
DEFAULT_CHECKLIST_FILE = "capstone_system_test_checklist.csv"
DEFAULT_IOC_PREFIX = "TEST:GIGA"


# LTC2945 ADC data used for tolerance documentation.
LTC2945_VIN_FULL_SCALE_V = 102.4
LTC2945_SENSE_FULL_SCALE_V = 0.1024
LTC2945_TUE_FS = 0.0075          # +/-0.75 % of full-scale, datasheet TUE definition
LTC2945_VIN_LSB_V = 0.025        # 25 mV/LSB
LTC2945_SENSE_LSB_V = 25e-6      # 25 uV/LSB
SHUNT_TOLERANCE = 0.01           # production current-sense resistors: 1 %

# Acceptance criteria for this system test.
# LTC2945 guaranteed +/-0.75 %FS VIN TUE
VOLTAGE_PERCENT_TOL = 0.02       # 2 % of reference voltage
VOLTAGE_ABS_FLOOR_V = 0.10       # 100 mV minimum window
CURRENT_PERCENT_TOL = 0.05       # 5 % of reference current (system test plan)
CURRENT_FLOOR_39M_A = 0.025      # 25 mA absolute floor for 39 mOhm channels
CURRENT_FLOOR_50M_A = 0.020      # 20 mA absolute floor for 50 mOhm channels

# Default load points cover the full intended operating range from 0 to 100 %.
DEFAULT_TEST_FRACTIONS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.00)


@dataclass(frozen=True)
class RailConfig:
    """Configuration data for one monitored power-supply rail.

    Attributes:
        key: Short command-line/internal identifier for the rail.
        label: Human-readable rail name used in prompts and reports.
        nominal_v: Nominal rail voltage in volts, including polarity.
        voltage_sign: +1 for positive rails and -1 for negative rails.
        ioc_channel_aliases: IOC channel names that may correspond to this rail.
        shunt_ohms: Installed current-sense resistor value in ohms.
        test_max_a: Maximum electronic-load current used during the test, in amps.
    """
    key: str
    label: str
    nominal_v: float
    voltage_sign: int
    ioc_channel_aliases: Tuple[str, ...]
    shunt_ohms: float
    test_max_a: float

    @property
    def current_floor_a(self) -> float:
        return CURRENT_FLOOR_39M_A if self.shunt_ohms < 0.045 else CURRENT_FLOOR_50M_A


RAILS: Dict[str, RailConfig] = {
    "5VA": RailConfig(
        key="5VA", label="+5VA", nominal_v=5.0, voltage_sign=+1,
        ioc_channel_aliases=("5VA", "6VA"), shunt_ohms=0.039, test_max_a=2.0,
    ),
    "5VB": RailConfig(
        key="5VB", label="+5VB", nominal_v=5.0, voltage_sign=+1,
        ioc_channel_aliases=("5VB", "6VB"), shunt_ohms=0.039, test_max_a=2.0,
    ),
    "P5V": RailConfig(
        key="P5V", label="+5V", nominal_v=5.0, voltage_sign=+1,
        ioc_channel_aliases=("P5V",), shunt_ohms=0.050, test_max_a=1.00,
    ),
    "M5V": RailConfig(
        key="M5V", label="-5V", nominal_v=-5.0, voltage_sign=-1,
        ioc_channel_aliases=("M5V",), shunt_ohms=0.050, test_max_a=1.00,
    ),
    "P15V": RailConfig(
        key="P15V", label="+15V", nominal_v=15.0, voltage_sign=+1,
        ioc_channel_aliases=("P15V",), shunt_ohms=0.050, test_max_a=1.0,
    ),
    "M15V": RailConfig(
        key="M15V", label="-15V", nominal_v=-15.0, voltage_sign=-1,
        ioc_channel_aliases=("M15V",), shunt_ohms=0.050, test_max_a=1.0,
    ),
}

RAIL_ORDER = ("5VA", "5VB", "P5V", "M5V", "P15V", "M15V")


@dataclass(frozen=True)
class SystemTestConfig:
    """One item from the Chapter 6 system-level test matrix."""

    test_id: str
    name: str
    method: str
    pass_criterion: str
    steps: Tuple[str, ...]
    automated_from_rail_data: bool = False


SYSTEM_TESTS: Tuple[SystemTestConfig, ...] = (
    SystemTestConfig(
        "ST-01",
        "Power On and Initialization",
        "Apply power to the complete system and verify Arduino, display, sensor channels, and network operation.",
        "The system initializes properly and all six channels are operational.",
        (
            "All power, sensor, display, and Ethernet connections have been inspected.",
            "The electronic load is disabled before power-up.",
            "The required monitored power supplies are energized.",
            "Power has been applied to the Arduino and monitoring electronics.",
            "The Arduino startup sequence completed normally.",
            "The GIGA Display initialized.",
            "All six expected rail channels are displayed.",
            "The EPICS IOC is running.",
            "The IOC established communication with the monitor.",
            "No startup error or unexpected behavior requiring manual recovery was observed.",
        ),
    ),
    SystemTestConfig(
        "ST-02",
        "Rail Identification",
        "Correlate each displayed channel with its physical rail connection and polarity.",
        "The correct rail identification and polarity are shown for each connected rail.",
        (
            "All six monitored rails are energized and connected to their intended monitor inputs.",
            "Each physical rail connection was correlated with the corresponding displayed channel.",
            "The +5VA, +5VB, +5V, -5V, +15V, and -15V rail identifications are correct.",
            "Positive and negative rail voltage polarity is reported correctly.",
            "Negative-rail current follows the sign convention used by the firmware.",
        ),
    ),
    SystemTestConfig(
        "ST-03",
        "Voltage Accuracy",
        "Measure each rail with the reference instrument and compare it with the EPICS monitor value at multiple operating points.",
        "Voltage error is within ±2% across the full tested operating range.",
        (
            "All six rails have a completed latest voltage-measurement attempt.",
            "Every required voltage sample in the latest attempts meets the ±2% system-level criterion.",
        ),
        automated_from_rail_data=True,
    ),
    SystemTestConfig(
        "ST-04",
        "Current Accuracy",
        "Apply multiple electronic-load currents to each rail and compare the reference current with the monitor measurement.",
        "Current error is within ±5% across the full intended operating range; reference uncertainty/resolution is considered at low current.",
        (
            "All six rails have a completed latest current-measurement attempt.",
            "Every required current sample in the latest attempts meets the ±5% system-level criterion, with the configured low-current floor.",
        ),
        automated_from_rail_data=True,
    ),
    SystemTestConfig(
        "ST-05",
        "Dynamic Load Response",
        "Change electronic-load current while monitoring the local display and EPICS values.",
        "Current and voltage readings change according to the load change.",
        (
            "The electronic-load current was changed over a safe range while the system was operating.",
            "The local display current reading changed in response to the load change.",
            "The EPICS current reading changed in response to the load change.",
            "The local and EPICS voltage readings responded appropriately to any rail-voltage change under load.",
            "No channel became unresponsive or produced an intermittent communication failure during the load change.",
        ),
    ),
    SystemTestConfig(
        "ST-06",
        "Local Display",
        "Observe voltage, current, rail identification, limits, and status for all channels.",
        "All necessary information is visible and correlates with the connected rail.",
        (
            "All six rail identifications are visible on the GIGA Display.",
            "Voltage is visible for each rail and corresponds with the connected rail.",
            "Current is visible for each rail and corresponds with the connected rail.",
            "Configured limits/status indications are visible for each rail.",
            "Communication/network state is visible and reasonable for the current operating condition.",
        ),
    ),
    SystemTestConfig(
        "ST-07",
        "EPICS Communications",
        "Run the IOC and verify all required voltage, current, and status process variables.",
        "Required process variables are connected and update properly; local display and EPICS agree within displayed resolution.",
        (
            "The complete monitor is powered and connected to Ethernet.",
            "The EPICS IOC is running.",
            "The IOC connects to the Arduino TCP server.",
            "Voltage and current process variables for all six rails are connected and updating.",
            "EPICS values have been compared with the local display and agree within displayed resolution/rounding.",
            "A load change on a selected rail caused the corresponding EPICS voltage/current values to update.",
            "The load-change/update check was completed on at least one positive rail.",
            "The load-change/update check was completed on at least one negative rail.",
        ),
    ),
    SystemTestConfig(
        "ST-08",
        "Limit / Alarm Operation",
        "Set a safe test limit and change load or supply until the threshold is crossed, then return inside limits.",
        "The proper limit indication is created when the threshold is crossed and clears after the value returns inside the limits.",
        (
            "A rail was selected for the limit/status test.",
            "The existing voltage/current limit settings were recorded before the test.",
            "A safe test limit was configured without exceeding the rating of the monitored supply, sensor, wiring, or electronic load.",
            "Normal status was verified while the measurement remained inside the limit.",
            "The applied load or supply was changed until the selected threshold was crossed.",
            "The local status indication changed appropriately when the threshold was crossed.",
            "The corresponding EPICS status changed appropriately when the threshold was crossed.",
            "The measurement was returned to the normal operating range.",
            "Local and EPICS status returned to normal.",
            "The original limit setting was restored.",
        ),
    ),
    SystemTestConfig(
        "ST-09",
        "Persistent Settings",
        "Change user-adjustable settings, power-cycle the controller/monitor electronics, and verify the settings after restart.",
        "Settings intended to be persistent are restored without Ethernet communication or manual re-entry.",
        (
            "One or more user-adjustable settings were changed to known values.",
            "The firmware accepted the changed settings.",
            "Power was removed from the Arduino and monitor electronics.",
            "The system remained unpowered for several seconds.",
            "Power was restored.",
            "Firmware initialization completed normally after power restoration.",
            "The previously modified settings were read after restart.",
            "The restored settings match the values stored before power removal.",
        ),
    ),
    SystemTestConfig(
        "ST-10",
        "Communication Recovery",
        "Disconnect Ethernet while the system is running, reconnect it, and monitor local operation and the IOC.",
        "Local monitoring continues during the network interruption and normal EPICS communication resumes after reconnection without firmware reprogramming.",
        (
            "Normal communication between the monitor and IOC was established before the interruption.",
            "EPICS values were verified to be updating before the interruption.",
            "The Ethernet cable/network connection was disconnected while the system was running.",
            "Local monitoring and the GIGA Display continued operating during the Ethernet interruption.",
            "The IOC response to communication loss was observed and was reasonable.",
            "Ethernet was reconnected.",
            "Communication was re-established without firmware reprogramming.",
            "Process variables resumed updating with valid values.",
        ),
    ),
    SystemTestConfig(
        "ST-11",
        "Repeatability",
        "Make repeated measurements at selected points, including after a power cycle.",
        "Measurements remain within the specified acceptance limits with no intermittent channel failures.",
        (
            "Repeated measurements were made at selected operating points.",
            "Repeated measurements were made after at least one power cycle.",
            "Repeated voltage measurements remained within the specified acceptance limits.",
            "Repeated current measurements remained within the specified acceptance limits.",
            "No intermittent sensor or communication failures were observed during repeatability testing.",
        ),
    ),
    SystemTestConfig(
        "ST-12",
        "End-To-End Demonstration",
        "Operate the complete system and demonstrate local and remote monitoring while changing the load on a selected channel.",
        "Hardware, firmware, display, network, IOC, and test software operate cooperatively with no system-level failure.",
        (
            "The complete hardware and firmware system is operating simultaneously.",
            "The local GIGA Display is operating and showing valid rail information.",
            "Ethernet and the EPICS IOC are connected and updating.",
            "Remote monitoring through EPICS/Phoebus is operating.",
            "The test software can acquire/record data from the system.",
            "Changing the load on a selected channel is reflected in both local and remote monitoring.",
            "The end-to-end demonstration completed without a system-level failure.",
        ),
    ),
)

SYSTEM_TEST_BY_ID = {test.test_id: test for test in SYSTEM_TESTS}


# Operator observations captured as part of each automated rail test.  These
# observations provide the pieces that cannot be measured electronically, such
# as whether the local GIGA Display is showing the correct channel and updating
# as the load changes.  They are stored in the checklist CSV as RAIL_EVIDENCE
# rows, so the raw measurement CSV format remains backward-compatible.
RAIL_OBSERVATION_PROMPTS: Tuple[Tuple[int, str, str], ...] = (
    (
        1,
        "IDENTITY",
        "Is the GIGA Display showing {rail} as the correct physical rail, with the correct voltage polarity?",
    ),
    (
        2,
        "UPDATES",
        "Did the GIGA Display voltage/current values update appropriately as the electronic-load current changed?",
    ),
    (
        3,
        "AGREEMENT",
        "Do the GIGA Display voltage/current values agree with the EPICS values within displayed resolution/rounding?",
    ),
    (
        4,
        "LIMITS",
        "Are the configured limits/status indications visible for this rail on the GIGA Display?",
    ),
    (
        5,
        "NETWORK",
        "Is the communication/network state visible and reasonable on the GIGA Display?",
    ),
)

RAIL_OBSERVATION_NAME_BY_INDEX = {
    index: name for index, name, _ in RAIL_OBSERVATION_PROMPTS
}

# These checklist steps are intentionally satisfied only by the automated rail
# test and its in-test local-display prompts.  If the required evidence has not
# been captured yet, they remain INCOMPLETE rather than asking the operator to
# re-enter the same information later from the offline checklist menu.
AUTO_ONLY_STEPS: Dict[str, Tuple[int, ...]] = {
    "ST-02": (1, 2, 3, 4, 5),
    "ST-03": (1, 2),
    "ST-04": (1, 2),
    "ST-05": (1, 2, 3, 4, 5),
    "ST-06": (1, 2, 3, 4, 5),
    "ST-07": (1, 2, 3, 4, 5, 6, 7, 8),
}


CHECKLIST_FIELDS = [
    "record_type",       # TEST_START, STEP, TEST_END
    "timestamp",
    "session_id",
    "test_run_id",
    "attempt",
    "dut_id",
    "operator",
    "test_id",
    "test_name",
    "step_index",
    "step_text",
    "step_result",      # PASS, FAIL, INCOMPLETE, N/A
    "test_result",      # PASS, FAIL, INCOMPLETE, RETEST
    "retest_outcome",   # PASS, FAIL, INCOMPLETE when test_result == RETEST
    "source",           # MANUAL or DERIVED_RAIL_DATA
    "notes",
]


CSV_FIELDS = [
    "record_type",       # RUN_START, SAMPLE, RUN_END
    "timestamp",
    "session_id",
    "run_id",
    "attempt",
    "dut_id",
    "operator",
    "rail_key",
    "rail_label",
    "ioc_prefix",
    "ioc_channel",
    "rigol_idn",
    "run_status",        # RUNNING, COMPLETE, ABORTED
    "run_pass",
    "setpoint_a",
    "sample_index",
    "load_input_on",
    "rigol_voltage_v",
    "rigol_current_a",
    "voltage_reference_v",
    "current_reference_a",
    "ioc_voltage_v",
    "ioc_voltage_raw_v",
    "ioc_current_ma",
    "ioc_current_raw_a",
    "voltage_error_v",
    "current_error_a",
    "voltage_tolerance_v",
    "current_tolerance_a",
    "voltage_pass",
    "current_pass",
    "sample_pass",
    "notes",
]

