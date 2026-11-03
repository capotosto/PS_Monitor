#pragma once

#include "DataModel.h"

// Compiled defaults and current runtime settings.
extern const NetworkSettings COMPILED_NETWORK_SETTINGS;
extern NetworkSettings networkSettings;

extern MonitorChannel channels[CHANNEL_COUNT];

extern bool settingsStorageReady;
extern bool networkRestartRequired;
extern bool ethernetHardwarePresent;

bool channelIsInAlarm(const MonitorChannel &channel);
void updateAlarmState(MonitorChannel &channel);
