#include "EthernetServices.h"

#include <Arduino.h>
#include <Ethernet.h>
#include <SPI.h>

#include "AppConfig.h"
#include "AppState.h"
#include "HttpDashboard.h"
#include "PscProtocol.h"

namespace {
byte macAddress[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xDE, 0xAD};
}

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

  if (ethernetHardwarePresent) {
    Serial.print("HTTP server: http://");
    Serial.println(Ethernet.localIP());
    Serial.print("PSC server: ");
    Serial.print(Ethernet.localIP());
    Serial.print(":");
    Serial.println(PSC_PORT);
  }
}
