#pragma once

#include <Arduino.h>

void initializeEthernet();
void serviceEthernet();

IPAddress getEthernetLocalIP();
bool isEthernetLinkUp();

uint8_t readW6100Register(uint16_t address);

void writeW6100Register(uint16_t address, uint8_t value);

void resetW6100Phy();

void forceW6100_100Full();

uint16_t readW6100PhyRegister(uint8_t phyAddress);