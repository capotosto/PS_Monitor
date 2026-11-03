#include "SensorManager.h"

#include <Arduino.h>
#include <Wire.h>

#include "AppConfig.h"
#include "AppState.h"
#include "LTC2945.h"
#include "SensorConfig.h"

namespace {

// All six isolator outputs share the same GIGA-side bus.
TwoWire &sensorBus = Wire2;

/*
  Array order must match channels[] in AppState.cpp:
    0 +6VA
    1 +6VB
    2 +5V
    3 -5V
    4 +15V
    5 -15V

  The two negative rails remain in SENSE+ high-side mode. Only the reported
  voltage sign is inverted in software.
*/

// Constructor arguments:
//   I2C bus, device address, shunt resistance,
//   voltage polarity multiplier, current polarity multiplier
LTC2945 sensors[CHANNEL_COUNT] = {
  {sensorBus, LTC_ADDRESS_6VA,  SHUNT_6VA_OHMS,  +1.0f, +1.0f},
  {sensorBus, LTC_ADDRESS_6VB,  SHUNT_6VB_OHMS,  +1.0f, +1.0f},
  {sensorBus, LTC_ADDRESS_P5V,  SHUNT_P5V_OHMS,  +1.0f, +1.0f},
  {sensorBus, LTC_ADDRESS_M5V,  SHUNT_M5V_OHMS,  -1.0f, +1.0f},
  {sensorBus, LTC_ADDRESS_P15V, SHUNT_P15V_OHMS, +1.0f, +1.0f},
  {sensorBus, LTC_ADDRESS_M15V, SHUNT_M15V_OHMS, -1.0f, +1.0f}
};

void printAddress(uint8_t address) {
  Serial.print("0x");

  if (address < 0x10) {
    Serial.print('0');
  }

  Serial.print(address, HEX);
}

void reportSensorTransition(
  uint8_t index,
  bool previousOnline,
  bool currentOnline
) {
  if (previousOnline == currentOnline) {
    return;
  }

  Serial.print(channels[index].name);
  Serial.print(" ");
  Serial.println(currentOnline ? "ONLINE" : "OFFLINE");
}

}

//Prints the channel names and I2C addresses to console. 
void printSensorConfiguration() {
  Serial.println();
  Serial.println("LTC2945 sensor configuration:");

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    Serial.print("  ");
    Serial.print(channels[i].name);
    Serial.print("  address ");
    printAddress(sensors[i].address());
    Serial.println();
  }

  Serial.println();
}

/*
  Initializes the I2C bus and each LTC2945 monitor.

  Each channel begins in an invalid/offline state. A sensor that responds
  successfully is configured by LTC2945::begin().
  
  Failed initialization records the I2C error and immediately sets the failure count to the
  offline threshold.

  A complete measurement pass is performed before the display and PSC
  interfaces begin so users get initialized data.
*/
void initializeSensors() {
  sensorBus.begin();
  sensorBus.setClock(SENSOR_I2C_CLOCK_HZ);

  printSensorConfiguration();

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    MonitorChannel &channel = channels[i];

    channel.readingValid = false;
    channel.sensorOnline = false;
    channel.sensorError = 0;
    channel.consecutiveSensorFailures = 0;
    channel.lastValidReadingMs = 0;

    const bool initialized = sensors[i].begin();

    Serial.print(channel.name);
    Serial.print(" at ");
    printAddress(sensors[i].address());

    if (initialized) {
      Serial.println(" acknowledged and configured");
    } else {
      channel.sensorError = sensors[i].lastError();
      channel.consecutiveSensorFailures =
        SENSOR_FAILURES_TO_OFFLINE;

      Serial.print(" failed, error 0x");
      Serial.println(channel.sensorError, HEX);
    }
  }

  // Populate the first complete snapshot before the display and PSC start.
  updateSensorMeasurements();
}

/*
  Polls all six LTC2945 channels and updates the shared MonitorChannel state.

  Successful reads:
    - replace V/I with the newest measurement
    - mark the reading valid and sensor online
    - clear the communication error/failure counter
    - update the timestamp and alarm state

  Failed reads:
    - preserve the last valid voltage/current values
    - record the LTC2945 communication error
    - increment the fail counter
    - mark the sensor offline only after the configured failure threshold

  The failure threshold prevents a single transient I2C error from causing
  an unnecessary ONLINE/OFFLINE state transition.
*/
void updateSensorMeasurements() {
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    MonitorChannel &channel = channels[i];
    const bool previousOnline = channel.sensorOnline;

    LTC2945::Reading reading;

    if (sensors[i].read(reading)) {
      channel.voltage = reading.voltage;
      channel.current = reading.current;
      channel.readingValid = true;
      channel.sensorOnline = true;
      channel.sensorError = 0;
      channel.consecutiveSensorFailures = 0;
      channel.lastValidReadingMs = millis();

      updateAlarmState(channel);
    } else {
      channel.sensorError = sensors[i].lastError();

      if (channel.consecutiveSensorFailures < 255) {
        ++channel.consecutiveSensorFailures;
      }

      if (channel.consecutiveSensorFailures >=
          SENSOR_FAILURES_TO_OFFLINE) {
        channel.sensorOnline = false;
      }

      /*
        Keep the last valid voltage and current. Replacing a failed read with
        zero would make an I2C fault look like a real rail undervoltage.
      */
    }

    // Log sensor state changes only to prevent needless prints
    reportSensorTransition(
      i,
      previousOnline,
      channel.sensorOnline
    );
  }
}
