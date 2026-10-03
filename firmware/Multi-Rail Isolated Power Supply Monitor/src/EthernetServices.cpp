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
#include <Ethernet.h>
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
void initializeEthernet() {
  Ethernet.init(ETHERNET_CS_PIN);  
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);

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


  // Configure the interface using the saved/static network configuration
  Ethernet.begin(macAddress, localIp, dnsServer, gateway, subnetMask);
  delay(250);

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
    Serial.println(Ethernet.localIP());
    Serial.print("PSC server: ");
    Serial.print(Ethernet.localIP());
    Serial.print(":");
    Serial.println(PSC_PORT);
  }
}
