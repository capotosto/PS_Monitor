/*Ethernet initialization for the multi-rail power supply monitor.

  This module:
    - configures the Ethernet Shield SPI chip-select pins
    - applies the current static IPv4 configuration
    - initializes the Arduino Ethernet interface
    - verifies that Ethernet hardware is present
    - starts the HTTP dashboard and PSC/EPICS servers

  Network settings are loaded into networkSettings before this function is
  called, either from persistent QSPI storage or from compiled defaults.*/
#include "EthernetServices.h"

#include <Arduino.h>
//#include <Ethernet.h>
#include "EthernetConfig.h"
#include <SPI.h>

#include "AppConfig.h"
#include "AppState.h"
#include "HttpDashboard.h"
#include "PscProtocol.h"

//Sets the MAC address used by the Ethernet interface.
namespace {
byte macAddress[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xDE, 0xAD};
}

/*Initialize the Ethernet hardware and network services.

  Startup sequence:
    1. Select the Ethernet controller SPI chip-select pin.
    2. Disable the SD-card SPI device so it cannot interfere with Ethernet.
    3. Convert the stored byte-array network configuration to IPAddress
       objects required by the Arduino Ethernet library.
    4. Start Ethernet using the configured static IP parameters.
    5. Verify that the Ethernet controller is physically detected.
    6. Start the HTTP dashboard and PSC server only when hardware is present.*/
void initializeEthernet()
{
    pinMode(ETHERNET_CS_PIN, OUTPUT);
    digitalWrite(ETHERNET_CS_PIN, HIGH);

    pinMode(ETHERNET_INT_PIN, INPUT_PULLUP);

    Serial.println("Starting SPI for W6100...");
    SPI1.begin();

    Ethernet.init(ETHERNET_CS_PIN);

  const IPAddress localIp(
    networkSettings.ip[0],
    networkSettings.ip[1],
    networkSettings.ip[2],
    networkSettings.ip[3]
  );
  const IPAddress dnsServer(
    networkSettings.dns[0],
    networkSettings.dns[1],
    networkSettings.dns[2],
    networkSettings.dns[3]
  );
  const IPAddress gateway(
    networkSettings.gateway[0],
    networkSettings.gateway[1],
    networkSettings.gateway[2],
    networkSettings.gateway[3]
  );
  const IPAddress subnetMask(
    networkSettings.subnet[0],
    networkSettings.subnet[1],
    networkSettings.subnet[2],
    networkSettings.subnet[3]
  );

  Serial.print("Configured IP: ");
  Serial.println(localIp);

  Serial.print("Gateway: ");
  Serial.println(gateway);

  Serial.print("Subnet: ");
  Serial.println(subnetMask);

  Serial.print("DNS: ");
  Serial.println(dnsServer);

  // Configure the interface using the saved/static network configuration
  Ethernet.begin(macAddress, localIp, dnsServer, gateway, subnetMask);
  
  Ethernet.setLocalIP(localIp);
  Ethernet.setGatewayIP(gateway);
  Ethernet.setSubnetMask(subnetMask);
  Ethernet.setDnsServerIP(dnsServer);

  delay(250);

  Serial.print("W6100 IP after configuration: ");
  Serial.println(Ethernet.localIP());

  Serial.print("W6100 gateway: ");
  Serial.println(Ethernet.gatewayIP());

  Serial.print("W6100 subnet: ");
  Serial.println(Ethernet.subnetMask());

  ethernetHardwarePresent =
    Ethernet.hardwareStatus() != EthernetNoHardware;

  if (ethernetHardwarePresent) {
    initializeHttpServer();
    initializePscServer();
  }

  Serial.print("Ethernet hardware: ");
  Serial.println(ethernetHardwarePresent ? "present" : "not detected");

  //If hardware is absent, leave the services stopped
  if (ethernetHardwarePresent) {
    Serial.print("HTTP server: http://");
    Serial.println(getEthernetLocalIP());
    Serial.print("PSC server: ");
    Serial.print(getEthernetLocalIP());
    Serial.print(":");
    Serial.println(PSC_PORT);
  }
}

IPAddress getEthernetLocalIP()
{
    return Ethernet.localIP();
}

bool isEthernetLinkUp()
{
    return Ethernet.linkStatus() == LinkON;
}

uint8_t readW6100Register(uint16_t address)
{
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

    digitalWrite(ETHERNET_CS_PIN, LOW);

    // 16-bit register offset
    SPI.transfer((address >> 8) & 0xFF);
    SPI.transfer(address & 0xFF);

    // Common Register Block + READ + VDM
    SPI.transfer(0x00);

    uint8_t value = SPI.transfer(0x00);

    digitalWrite(ETHERNET_CS_PIN, HIGH);

    SPI.endTransaction();

    return value;
}

void writeW6100Register(uint16_t address, uint8_t value)
{
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

    digitalWrite(ETHERNET_CS_PIN, LOW);

    SPI.transfer((address >> 8) & 0xFF);
    SPI.transfer(address & 0xFF);

    // Common Register Block + WRITE + VDM
    SPI.transfer(0x04);

    SPI.transfer(value);

    digitalWrite(ETHERNET_CS_PIN, HIGH);

    SPI.endTransaction();
}

void resetW6100Phy()
{
    Serial.println("Resetting W6100 PHY...");

    // Unlock PHY configuration registers
    writeW6100Register(0x41F6, 0x53);

    // Auto-negotiation
    writeW6100Register(0x301C, 0x00);

    // Bit 6 must remain 1.
    // Bit 0 = PHY reset.
    writeW6100Register(0x301D, 0x41);

    delay(2);

    // Lock PHY configuration again
    writeW6100Register(0x41F6, 0x00);

    Serial.print("PHYCR1 = 0x");
    Serial.println(readW6100Register(0x301D), HEX);

    Serial.print("PHYSR  = 0x");
    Serial.println(readW6100Register(0x3000), HEX);
}

void forceW6100_100Full()
{
    Serial.println("Forcing W6100 PHY to 100BASE-TX full duplex...");

    // Unlock PHYCR0 / PHYCR1
    writeW6100Register(0x41F6, 0x53);

    // MODE[2:0] = 100 = 100BASE-TX full duplex
    writeW6100Register(0x301C, 0x04);

    // Bit 6 must always be 1; bit 0 triggers PHY reset
    writeW6100Register(0x301D, 0x41);

    delay(5);

    // Lock PHY controls again
    writeW6100Register(0x41F6, 0x00);

    uint8_t physr = readW6100Register(0x3000);
    uint8_t phycr1 = readW6100Register(0x301D);

    Serial.print("PHYSR after force = 0x");
    Serial.println(physr, HEX);

    Serial.print("PHYCR1 = 0x");
    Serial.println(phycr1, HEX);
}

uint16_t readW6100PhyRegister(uint8_t phyAddress)
{
    // Select internal PHY register
    writeW6100Register(0x3008, phyAddress & 0x1F);

    // Start PHY read
    writeW6100Register(0x3014, 0x02);

    const uint32_t start = millis();

    while (readW6100Register(0x3014) != 0x00) {
        if (millis() - start > 20) {
            Serial.println("PHY MDIO read timeout");
            return 0xFFFF;
        }
    }

    uint8_t low  = readW6100Register(0x3010);
    uint8_t high = readW6100Register(0x3011);

    return (static_cast<uint16_t>(high) << 8) | low;
}