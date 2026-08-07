#include "AppState.h"

#include <Arduino.h>

const NetworkSettings COMPILED_NETWORK_SETTINGS = {
  {192, 168, 1, 177},  // IP address
  {192, 168, 1, 1},    // DNS server
  {192, 168, 1, 1},    // Gateway
  {255, 255, 255, 0}   // Subnet mask
};

NetworkSettings networkSettings = COMPILED_NETWORK_SETTINGS;

MonitorChannel channels[CHANNEL_COUNT] = {
  // name, nominal V/I, measured V/I, limits, four alarms,
  // reading valid, sensor online, error, failures, last-valid time
  {"CH1 +6VA",   6.00f, 0.60f, 0.0f, 0.0f,
   { 5.40f,  6.60f, 0.00f, 1.20f},
   false, false, false, false, false, false, 0, 0, 0},

  {"CH2 +6VB",   6.00f, 0.60f, 0.0f, 0.0f,
   { 5.40f,  6.60f, 0.00f, 1.20f},
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

bool settingsStorageReady = false;
bool networkRestartRequired = false;
bool ethernetHardwarePresent = false;

bool channelIsInAlarm(const MonitorChannel &channel) {
  return !channel.sensorOnline ||
         channel.voltageLowAlarm ||
         channel.voltageHighAlarm ||
         channel.currentLowAlarm ||
         channel.currentHighAlarm;
}

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
