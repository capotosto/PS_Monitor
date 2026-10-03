/*
  Arduino GIGA R1 + GIGA Display Shield + Ethernet Shield 2
  Modular six-channel power monitor.

  Services:
    HTTP dashboard: TCP port 80
    EPICS PSCDriver: TCP port 8765
*/

#include <Arduino.h>
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

void setup() {
  Serial.begin(115200);

  const uint32_t serialWaitStart = millis();
  while (!Serial && millis() - serialWaitStart < 1500) {
    delay(10);
  }

  initializeSettingsStorage();  //Initialize QSPI configuration
  initializeSensors();  //Initialize I2C PMICs
  initializeDisplay();  //Initialize display shield
  initializeEthernet();  //Initialize ethernet shield
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
}
