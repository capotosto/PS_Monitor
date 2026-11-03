/*
  Arduino GIGA R1 + GIGA Display Shield + Ethernet Shield 2
  Modular six-channel power monitor.

  Services:
    HTTP dashboard: TCP port 80
    EPICS PSCDriver: TCP port 8765
*/

#include <Arduino.h>
#include <SPI.h>
#include "AppConfig.h"
#include "AppState.h"
#include "DisplayUI.h"
#include "EthernetServices.h"
#include "HttpDashboard.h"
#include "PersistentStorage.h"
#include "PscProtocol.h"
#include "SensorConfig.h"
#include "SensorManager.h"

namespace {
uint32_t lastSensorPollMs = 0;
uint32_t lastDisplayMs = 0;
}

void debug() {
    Serial.println();
    Serial.println("Raw W6100 SPI ID test:");

    pinMode(ETHERNET_CS_PIN, OUTPUT);
    digitalWrite(ETHERNET_CS_PIN, HIGH);

    SPI.begin();

    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

    digitalWrite(ETHERNET_CS_PIN, LOW);

    // Start at Common Register address 0x0000
    SPI.transfer(0x00);  // Address high byte
    SPI.transfer(0x00);  // Address low byte

    // Common Register Block, READ, VDM mode
    SPI.transfer(0x00);

    // Sequentially read CIDR0, CIDR1, VER0, VER1
    uint8_t cidr0 = SPI.transfer(0x00);
    uint8_t cidr1 = SPI.transfer(0x00);
    uint8_t ver0  = SPI.transfer(0x00);
    uint8_t ver1  = SPI.transfer(0x00);

    digitalWrite(ETHERNET_CS_PIN, HIGH);

    SPI.endTransaction();

    Serial.print("CIDR0 = 0x");
    Serial.println(cidr0, HEX);

    Serial.print("CIDR1 = 0x");
    Serial.println(cidr1, HEX);

    Serial.print("VER0  = 0x");
    Serial.println(ver0, HEX);

    Serial.print("VER1  = 0x");
    Serial.println(ver1, HEX);

    Serial.println();
    
    uint8_t physr = readW6100Register(0x3000);

    Serial.print("PHYSR = 0x");
    Serial.print(physr, HEX);

    Serial.print("  Cable = ");
    Serial.print((physr & 0x80) ? "UNPLUGGED" : "PLUGGED");

    Serial.print("  Link = ");
    Serial.println((physr & 0x01) ? "UP" : "DOWN");

    uint8_t phycr1 = readW6100Register(0x301D);

    Serial.print("PHYCR1 = 0x");
    Serial.println(phycr1, HEX);

    Serial.print("PWDN = ");
    Serial.println((phycr1 & 0x20) ? "YES" : "NO");

    Serial.print("10BASE-Te = ");
    Serial.println((phycr1 & 0x08) ? "YES" : "NO");

    uint16_t bmcr = readW6100PhyRegister(0x00);

    // Read BMSR twice because link-status registers are commonly latch-low.
    uint16_t bmsr1 = readW6100PhyRegister(0x01);
    uint16_t bmsr2 = readW6100PhyRegister(0x01);

    Serial.print("BMCR  = 0x");
    Serial.println(bmcr, HEX);

    Serial.print("BMSR1 = 0x");
    Serial.println(bmsr1, HEX);

    Serial.print("BMSR2 = 0x");
    Serial.println(bmsr2, HEX);

    Serial.print("Auto-neg capable: ");
    Serial.println((bmsr2 & 0x0008) ? "YES" : "NO");

    Serial.print("Auto-neg complete: ");
    Serial.println((bmsr2 & 0x0020) ? "YES" : "NO");

    Serial.print("PHY link: ");
    Serial.println((bmsr2 & 0x0004) ? "UP" : "DOWN");

    uint16_t anar   = readW6100PhyRegister(0x04);
    uint16_t anlpar = readW6100PhyRegister(0x05);
    uint16_t aner   = readW6100PhyRegister(0x06);

    Serial.print("ANAR   = 0x");
    Serial.println(anar, HEX);

    Serial.print("ANLPAR = 0x");
    Serial.println(anlpar, HEX);

    Serial.print("ANER   = 0x");
    Serial.println(aner, HEX);

    Serial.print("Partner auto-neg capable: ");
    Serial.println((aner & 0x0001) ? "YES" : "NO");

    Serial.print("Partner page received: ");
    Serial.println((aner & 0x0002) ? "YES" : "NO");

    delay(500);
}

void setup() {

  Serial.begin(115200);

  delay(10000);

  const uint32_t serialWaitStart = millis();
  while (!Serial && millis() - serialWaitStart < 1500) {
    delay(10);
  }

  initializeSettingsStorage();  //Initialize QSPI configuration
  initializeSensors();  //Initialize I2C PMICs
  initializeDisplay();  //Initialize display shield
  initializeEthernet();  //Initialize ethernet shield
  resetW6100Phy();
  writeW6100Register(0x301C, 0x06);  // 10BASE-T full duplex
  writeW6100Register(0x301D, 0x41);  // PHY reset
  //forceW6100_100Full();
  redrawDisplay();  //Redraw display
}

void loop() {
  const uint32_t now = millis();

  if (now - lastSensorPollMs >= SENSOR_POLL_PERIOD_MS) {
    lastSensorPollMs = now;
    updateSensorMeasurements();  //Update the sensor readouts
  }

  if (now - lastDisplayMs >= DISPLAY_REFRESH_PERIOD_MS) {
    lastDisplayMs = now;
    redrawDisplay();  //Redraw display with new values
  }

  /*
    PSC is serviced both before and after HTTP so a browser request cannot
    unnecessarily delay the persistent IOC connection.
  */
  servicePsc();  //R/W to the IOC
  serviceHttp();  //R/W to the webpage
  servicePsc();  //R/W to the IOC
  debug();
}
