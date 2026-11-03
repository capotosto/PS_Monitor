#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Application size and scheduling
// ---------------------------------------------------------------------------
constexpr uint8_t CHANNEL_COUNT = 6;
constexpr uint32_t DISPLAY_REFRESH_PERIOD_MS = 500;

// ---------------------------------------------------------------------------
// Ethernet Shield 2
// ---------------------------------------------------------------------------
constexpr uint8_t ETHERNET_CS_PIN = 10;
constexpr uint8_t ETHERNET_INT_PIN = 2;
//constexpr uint8_t SD_CS_PIN = 4;
constexpr uint16_t HTTP_PORT = 80;
constexpr uint16_t PSC_PORT = 8765;

// ---------------------------------------------------------------------------
// PSCDriver protocol
// ---------------------------------------------------------------------------
constexpr uint32_t PSC_PUBLISH_PERIOD_MS = 500;
constexpr uint32_t PSC_WRITE_TIMEOUT_MS = 250;
constexpr uint32_t PSC_MAX_BODY_LENGTH = 256;

constexpr uint16_t PSC_MSG_MEASUREMENTS = 1;
constexpr uint16_t PSC_MSG_LIMITS = 2;
constexpr uint16_t PSC_MSG_ALARMS = 3;
constexpr uint16_t PSC_MSG_SETPOINT = 10;

// ---------------------------------------------------------------------------
// Persistent QSPI settings
// ---------------------------------------------------------------------------
constexpr bool FORMAT_USER_PARTITION_IF_NEEDED = true;

constexpr uint32_t SETTINGS_MAGIC = 0x4D524C4DUL;  // "MRLM"
constexpr uint16_t SETTINGS_VERSION = 2;

constexpr const char *SETTINGS_FILE = "/user/rail_limits.bin";
constexpr const char *SETTINGS_TEMP_FILE = "/user/rail_limits.tmp";

/*
  Recovery mode:
  Set true and upload over USB if a saved IP address makes the web interface
  unreachable. The compiled network defaults will be used for that boot.
*/
constexpr bool FORCE_COMPILED_NETWORK_ON_BOOT = false;
