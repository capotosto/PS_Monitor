#pragma once

#include "DataModel.h"

bool initializeSettingsStorage();
bool loadPersistentSettings();
bool savePersistentSettings();

bool alarmLimitsAreValid(const AlarmLimits &limits);
bool hostAddressIsValid(const uint8_t address[4]);
bool optionalHostAddressIsValid(const uint8_t address[4]);
bool subnetMaskIsValid(const uint8_t subnet[4]);
bool networkSettingsAreValid(const NetworkSettings &settings);
