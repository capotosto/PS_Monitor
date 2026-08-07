#include "PersistentStorage.h"

#include <Arduino.h>

#include "BlockDevice.h"
#include "MBRBlockDevice.h"
#include "LittleFileSystem.h"

#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "AppConfig.h"
#include "AppState.h"

using namespace mbed;

namespace {
BlockDevice *qspiRoot = BlockDevice::get_default_instance();
MBRBlockDevice qspiUserPartition(qspiRoot, 4);
LittleFileSystem qspiUserFileSystem("user");
}

uint32_t calculateChecksum(
  const uint8_t *bytes,
  size_t byteCount
) {
  // FNV-1a checksum.
  uint32_t hash = 2166136261UL;

  for (size_t i = 0; i < byteCount; ++i) {
    hash ^= bytes[i];
    hash *= 16777619UL;
  }

  return hash;
}

uint32_t calculateSettingsChecksum(
  const PersistentSettings &settings
) {
  return calculateChecksum(
    reinterpret_cast<const uint8_t *>(&settings),
    offsetof(PersistentSettings, checksum)
  );
}

bool alarmLimitsAreValid(const AlarmLimits &limits) {
  constexpr float ABSOLUTE_LIMIT = 10000.0f;

  return isfinite(limits.voltageLow) &&
         isfinite(limits.voltageHigh) &&
         isfinite(limits.currentLow) &&
         isfinite(limits.currentHigh) &&
         limits.voltageLow < limits.voltageHigh &&
         limits.currentLow < limits.currentHigh &&
         fabsf(limits.voltageLow) <= ABSOLUTE_LIMIT &&
         fabsf(limits.voltageHigh) <= ABSOLUTE_LIMIT &&
         fabsf(limits.currentLow) <= ABSOLUTE_LIMIT &&
         fabsf(limits.currentHigh) <= ABSOLUTE_LIMIT;
}

bool addressIsAll(
  const uint8_t address[4],
  uint8_t value
) {
  return address[0] == value &&
         address[1] == value &&
         address[2] == value &&
         address[3] == value;
}

bool hostAddressIsValid(const uint8_t address[4]) {
  if (addressIsAll(address, 0) ||
      addressIsAll(address, 255)) {
    return false;
  }

  // Reject multicast, experimental, and loopback ranges.
  return address[0] >= 1 &&
         address[0] <= 223 &&
         address[0] != 127;
}

bool optionalHostAddressIsValid(const uint8_t address[4]) {
  // A zero gateway or DNS address is allowed.
  return addressIsAll(address, 0) ||
         hostAddressIsValid(address);
}

bool subnetMaskIsValid(const uint8_t subnet[4]) {
  const uint32_t mask =
    (static_cast<uint32_t>(subnet[0]) << 24) |
    (static_cast<uint32_t>(subnet[1]) << 16) |
    (static_cast<uint32_t>(subnet[2]) << 8) |
    static_cast<uint32_t>(subnet[3]);

  if (mask == 0) {
    return false;
  }

  bool zeroBitSeen = false;

  for (int bit = 31; bit >= 0; --bit) {
    const bool one = (mask & (1UL << bit)) != 0;

    if (!one) {
      zeroBitSeen = true;
    } else if (zeroBitSeen) {
      // A valid mask cannot contain a 1 after its first 0.
      return false;
    }
  }

  return true;
}

bool networkSettingsAreValid(
  const NetworkSettings &settings
) {
  return hostAddressIsValid(settings.ip) &&
         optionalHostAddressIsValid(settings.dns) &&
         optionalHostAddressIsValid(settings.gateway) &&
         subnetMaskIsValid(settings.subnet);
}

void buildPersistentSettings(PersistentSettings &settings) {
  memset(&settings, 0, sizeof(settings));

  settings.magic = SETTINGS_MAGIC;
  settings.version = SETTINGS_VERSION;
  settings.channelCount = CHANNEL_COUNT;

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    settings.limits[i] = channels[i].limits;
  }

  settings.network = networkSettings;
  settings.checksum = calculateSettingsChecksum(settings);
}

bool persistentSettingsAreValid(
  const PersistentSettings &settings
) {
  if (settings.magic != SETTINGS_MAGIC ||
      settings.version != SETTINGS_VERSION ||
      settings.channelCount != CHANNEL_COUNT ||
      settings.checksum != calculateSettingsChecksum(settings) ||
      !networkSettingsAreValid(settings.network)) {
    return false;
  }

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    if (!alarmLimitsAreValid(settings.limits[i])) {
      return false;
    }
  }

  return true;
}

bool readPersistentSettingsFile(
  const char* path,
  PersistentSettings& settings
) {
  FILE* file = fopen(path, "rb");

  if (file == nullptr) {
    return false;
  }

  const size_t bytesRead =
    fread(&settings, 1, sizeof(settings), file);

  fclose(file);

  return bytesRead == sizeof(settings) &&
         persistentSettingsAreValid(settings);
}

void applyPersistentSettings(
  const PersistentSettings &settings
) {
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    channels[i].limits = settings.limits[i];
    updateAlarmState(channels[i]);
  }

  if (!FORCE_COMPILED_NETWORK_ON_BOOT) {
    networkSettings = settings.network;
  } else {
    networkSettings = COMPILED_NETWORK_SETTINGS;
  }
}

bool savePersistentSettings() {
  if (!settingsStorageReady) {
    return false;
  }

  PersistentSettings settings;
  buildPersistentSettings(settings);

  FILE *file = fopen(SETTINGS_TEMP_FILE, "wb");

  if (file == nullptr) {
    Serial.println("Could not open temporary settings file.");
    return false;
  }

  const size_t bytesWritten =
    fwrite(&settings, 1, sizeof(settings), file);

  const int flushResult = fflush(file);
  const int closeResult = fclose(file);

  if (bytesWritten != sizeof(settings) ||
      flushResult != 0 ||
      closeResult != 0) {
    remove(SETTINGS_TEMP_FILE);
    Serial.println("Persistent-settings write failed.");
    return false;
  }

  /*
    Keep the temporary file valid until the final rename. On startup, the
    loader checks both files, so a reset during this short replacement window
    can still recover the new settings.
  */
  remove(SETTINGS_FILE);

  if (rename(SETTINGS_TEMP_FILE, SETTINGS_FILE) != 0) {
    Serial.println("Could not promote temporary settings file.");
    return false;
  }

  Serial.println("Alarm and network settings saved to internal QSPI flash.");
  return true;
}

bool loadPersistentSettings() {
  if (!settingsStorageReady) {
    return false;
  }

  PersistentSettings settings;

  if (readPersistentSettingsFile(
        SETTINGS_FILE,
        settings
      )) {
    applyPersistentSettings(settings);

    Serial.println(
      "Alarm and network settings loaded from internal QSPI flash."
    );

    return true;
  }

  /*
    Recover a valid temporary file if power was removed between replacing
    the old settings file and renaming the new one.
  */
  if (readPersistentSettingsFile(
        SETTINGS_TEMP_FILE,
        settings
      )) {
    applyPersistentSettings(settings);

    remove(SETTINGS_FILE);
    rename(SETTINGS_TEMP_FILE, SETTINGS_FILE);

    Serial.println(
      "Recovered settings from temporary settings file."
    );

    return true;
  }

  return false;
}

bool initializeSettingsStorage() {
  int result = qspiUserFileSystem.mount(&qspiUserPartition);

  if (result != 0 && FORMAT_USER_PARTITION_IF_NEEDED) {
    Serial.println(
      "QSPI user partition is not mountable; formatting partition 4."
    );

    /*
      reformat() formats and mounts only partition 4. It does not format the
      Wi-Fi firmware, OTA, or provisioning partitions.
    */
    result = qspiUserFileSystem.reformat(&qspiUserPartition);
  }

  if (result != 0) {
    Serial.print("QSPI user storage unavailable; error ");
    Serial.println(result);
    settingsStorageReady = false;
    return false;
  }

  settingsStorageReady = true;

  if (!loadPersistentSettings()) {
    Serial.println(
      "No valid saved settings found; storing compiled defaults."
    );

    networkSettings = COMPILED_NETWORK_SETTINGS;

    if (!savePersistentSettings()) {
      Serial.println("Could not store compiled defaults.");
      return false;
    }
  }

  return true;
}
