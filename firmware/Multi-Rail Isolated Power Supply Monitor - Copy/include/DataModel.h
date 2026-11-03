#pragma once

#include <Arduino.h>

#include "AppConfig.h"

struct NetworkSettings {
  uint8_t ip[4];
  uint8_t dns[4];
  uint8_t gateway[4];
  uint8_t subnet[4];
};

struct AlarmLimits {
  float voltageLow;
  float voltageHigh;
  float currentLow;
  float currentHigh;
};

struct PersistentSettings {
  uint32_t magic;
  uint16_t version;
  uint16_t channelCount;
  AlarmLimits limits[CHANNEL_COUNT];
  NetworkSettings network;
  uint32_t checksum;
};

struct MonitorChannel {
  const char *name;
  float nominalVoltage;
  float nominalCurrent;
  float voltage;
  float current;
  AlarmLimits limits;
  bool voltageLowAlarm;
  bool voltageHighAlarm;
  bool currentLowAlarm;
  bool currentHighAlarm;

  bool readingValid;
  bool sensorOnline;
  uint8_t sensorError;
  uint8_t consecutiveSensorFailures;
  uint32_t lastValidReadingMs;
};
