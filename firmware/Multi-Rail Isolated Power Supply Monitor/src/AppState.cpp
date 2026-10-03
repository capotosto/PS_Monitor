/*
  Global application state for the multi-rail power supply monitor.

  This module defines:
    - compiled/default Ethernet configuration
    - runtime network configuration
    - configuration and live state for all six monitor channels
    - system-wide storage/network status flags
    - common alarm-state evaluation functions

  The channel array is the shared source of live measurement, limit, alarm,
  and sensor-status information used by the display, HTTP interface, PSC
  protocol, and persistent-storage modules.
*/

#include "AppState.h"

#include <Arduino.h>

//Default static Ethernet configuration.
const NetworkSettings COMPILED_NETWORK_SETTINGS = {
  {192, 168, 1, 177},  // IP address
  {192, 168, 1, 1},    // DNS server
  {192, 168, 1, 1},    // Gateway
  {255, 255, 255, 0}   // Subnet mask
};

NetworkSettings networkSettings = COMPILED_NETWORK_SETTINGS;

/*Initial state for each monitored rail.

  MonitorChannel field order:
    name
    nominal voltage
    nominal current
    measured voltage
    measured current
    alarm limits {V low, V high, I low, I high}
    voltage-low alarm
    voltage-high alarm
    current-low alarm
    current-high alarm
    reading valid
    sensor online
    sensor/I2C error code
    consecutive sensor failures
    timestamp of last valid reading

  Measured values and status fields are initialized to zero/false and are
  populated by SensorManager after the LTC2945 devices are initialized*/
MonitorChannel channels[CHANNEL_COUNT] = {
  // name, nominal V/I, measured V/I, limits, four alarms,
  // reading valid, sensor online, error, failures, last-valid time
  {"CH1 +5VA",   5.00f, 0.60f, 0.0f, 0.0f,
   { 4.40f,  5.60f, 0.00f, 1.20f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH2 +5VB",   6.00f, 0.60f, 0.0f, 0.0f,
   { 4.40f,  5.60f, 0.00f, 1.20f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH3 +5V",    5.00f, 0.50f, 0.0f, 0.0f,
   { 4.50f,  5.50f, 0.00f, 1.00f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH4 -5V",   -5.00f, 0.50f, 0.0f, 0.0f,
   {-5.50f, -4.50f, 0.00f, 1.00f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH5 +15V",  15.00f, 0.35f, 0.0f, 0.0f,
   {13.50f, 16.50f, 0.00f, 0.75f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH6 -15V", -15.00f, 0.35f, 0.0f, 0.0f,
   {-16.50f, -13.50f, 0.00f, 0.75f},
   false, false, false, false, false, false, 0, 0, 0}
};

/*System status flags shared between application modules.

  settingsStorageReady   - QSPI settings filesystem mounted and usable
  networkRestartRequired - saved network settings differ from active settings
  ethernetHardwarePresent- Ethernet controller was detected successfully*/
bool settingsStorageReady = false;
bool networkRestartRequired = false;
bool ethernetHardwarePresent = false;

//Return the overall fault/alarm state for a channel
bool channelIsInAlarm(const MonitorChannel &channel) {
  return !channel.sensorOnline ||
         channel.voltageLowAlarm ||
         channel.voltageHighAlarm ||
         channel.currentLowAlarm ||
         channel.currentHighAlarm;
}

/*Recalculate the four electrical alarm flags from the latest measurement
  and the configured alarm limits.

    UVL - undervoltage / insufficient voltage magnitude
    OVL - overvoltage / excessive voltage magnitude
    UCL - current below lower limit
    OCL - current above upper limit

  Positive and negative voltage rails require different numeric comparisons
  for UVL/OVL. For example, on a -5 V rail:

    -4.3 V is insufficient magnitude -> UVL
    -5.7 V is excessive magnitude    -> OVL

  Current is represented as positive load-current magnitude, so current
  alarm comparisons use the same direction for positive and negative rails.*/
void updateAlarmState(MonitorChannel &channel) {
  /*
    These booleans are semantic:
      voltageLowAlarm  = UVL
      voltageHighAlarm = OVL

    For a negative rail:
      -5.7 V is excessive magnitude and must be OVL.
      -4.3 V is insufficient magnitude and must be UVL.
  */
  if (channel.nominalVoltage < 0.0f) {
    channel.voltageLowAlarm =
      channel.voltage > channel.limits.voltageHigh;  // UVL

    channel.voltageHighAlarm =
      channel.voltage < channel.limits.voltageLow;   // OVL
  } else {
    channel.voltageLowAlarm =
      channel.voltage < channel.limits.voltageLow;   // UVL

    channel.voltageHighAlarm =
      channel.voltage > channel.limits.voltageHigh;  // OVL
  }

  channel.currentLowAlarm =
    channel.current < channel.limits.currentLow;      // UCL

  channel.currentHighAlarm =
    channel.current > channel.limits.currentHigh;     // OCL
}
