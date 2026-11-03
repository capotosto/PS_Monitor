#pragma once

#include <Arduino.h>

void initializePscServer();
void servicePsc();

bool pscIsConnected();

bool sendPscMeasurements();
bool sendPscLimits();
bool sendPscAlarms();
void sendPscChannelSetpointEchoes(uint8_t channelIndex);
void sendAllPscSetpointEchoes();
void sendCompletePscSnapshot();
