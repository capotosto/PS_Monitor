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

  Positive rails use SENSE+ as the LTC2945 VIN source.

  The -5V and -15V channels use low-side current sensing. Their
  LTC2945 VIN ADC therefore measures VDD instead of SENSE+.

  For negative rails the local VDD measurement is a positive
  magnitude. The -1.0 voltage polarity multiplier converts that
  magnitude to the corresponding negative system-level voltage.
*/


// Constructor arguments:
//
//   I2C bus
//   device address
//   shunt resistance
//   voltage polarity multiplier
//   current polarity multiplier
//   VIN measurement source
//
LTC2945 sensors[CHANNEL_COUNT] = {
  {
    sensorBus,
    LTC_ADDRESS_6VA,
    SHUNT_6VA_OHMS,
    +1.0f,
    +1.0f,
    LTC2945::VoltageSource::SensePlus
  },

  {
    sensorBus,
    LTC_ADDRESS_6VB,
    SHUNT_6VB_OHMS,
    +1.0f,
    +1.0f,
    LTC2945::VoltageSource::SensePlus
  },

  {
    sensorBus,
    LTC_ADDRESS_P5V,
    SHUNT_P5V_OHMS,
    +1.0f,
    +1.0f,
    LTC2945::VoltageSource::SensePlus
  },

  {
    sensorBus,
    LTC_ADDRESS_M5V,
    SHUNT_M5V_OHMS,
    -1.0f,
    +1.0f,
    LTC2945::VoltageSource::Vdd
  },

  {
    sensorBus,
    LTC_ADDRESS_P15V,
    SHUNT_P15V_OHMS,
    +1.0f,
    +1.0f,
    LTC2945::VoltageSource::SensePlus
  },

  {
    sensorBus,
    LTC_ADDRESS_M15V,
    SHUNT_M15V_OHMS,
    -1.0f,
    +1.0f,
    LTC2945::VoltageSource::Vdd
  }
};


void printAddress(
  uint8_t address
) {
  Serial.print("0x");

  if (address < 0x10) {
    Serial.print('0');
  }

  Serial.print(
    address,
    HEX
  );
}


void reportSensorTransition(
  uint8_t index,
  bool previousOnline,
  bool currentOnline
) {
  if (
    previousOnline ==
    currentOnline
  ) {
    return;
  }

  Serial.print(
    channels[index].name
  );

  Serial.print(" ");

  Serial.println(
    currentOnline
      ? "ONLINE"
      : "OFFLINE"
  );
}

}


/*
  Print channel names and configured I2C addresses.
*/
void printSensorConfiguration() {
  Serial.println();

  Serial.println(
    "LTC2945 sensor configuration:"
  );

  for (
    uint8_t i = 0;
    i < CHANNEL_COUNT;
    ++i
  ) {
    Serial.print("  ");

    Serial.print(
      channels[i].name
    );

    Serial.print(
      "  address "
    );

    printAddress(
      sensors[i].address()
    );

    Serial.println();
  }

  Serial.println();
}


/*
  Initialize the I2C bus and each LTC2945 monitor.

  Each channel begins in an invalid/offline state.

  LTC2945::begin():

    - verifies the device responds
    - writes the appropriate CONTROL value
    - reads the CONTROL register back
    - verifies the configuration

  Positive rails:
    CONTROL = 0x05
    VIN = SENSE+

  Negative rails:
    CONTROL = 0x01
    VIN = VDD

  Failed initialization records the communication/configuration error
  and immediately sets the failure count to the offline threshold.

  A complete measurement pass is performed before the display and PSC
  interfaces begin.
*/
void initializeSensors() {
  sensorBus.begin();

  sensorBus.setClock(
    SENSOR_I2C_CLOCK_HZ
  );

  printSensorConfiguration();

  for (
    uint8_t i = 0;
    i < CHANNEL_COUNT;
    ++i
  ) {
    MonitorChannel &channel =
      channels[i];

    channel.readingValid = false;
    channel.sensorOnline = false;
    channel.sensorError = 0;
    channel.consecutiveSensorFailures = 0;
    channel.lastValidReadingMs = 0;

    const bool initialized =
      sensors[i].begin();

    Serial.print(
      channel.name
    );

    Serial.print(
      " at "
    );

    printAddress(
      sensors[i].address()
    );

    if (initialized) {
      Serial.println(
        " acknowledged and configured"
      );
    } else {
      channel.sensorError =
        sensors[i].lastError();

      channel.consecutiveSensorFailures =
        SENSOR_FAILURES_TO_OFFLINE;

      Serial.print(
        " failed, error 0x"
      );

      Serial.println(
        channel.sensorError,
        HEX
      );
    }
  }

  /*
    Populate the first complete snapshot before the display and
    PSC services begin.
  */
  updateSensorMeasurements();
}


/*
  Poll all six LTC2945 channels and update MonitorChannel state.

  LTC2945::read() verifies the CONTROL register before every
  measurement.

  This makes recovery automatic if an individual monitored supply is
  switched off and back on while the Arduino remains powered.

  Example:

    -5V monitor running:
      CONTROL = 0x01

    -5V supply turned off:
      LTC2945 loses power

    -5V supply turned back on:
      LTC2945 starts with CONTROL = 0x05

    next Arduino poll:
      read() detects incorrect CONTROL value
      CONTROL is rewritten to 0x01
      readback is verified
      voltage/current measurements are then acquired

  Successful reads:

    - replace voltage/current with newest measurement
    - mark reading valid
    - mark sensor online
    - clear communication error
    - clear failure counter
    - update timestamp
    - update alarm state

  Failed reads:

    - preserve last valid measurement values
    - record LTC2945/I2C error
    - increment failure counter
    - mark sensor offline after the configured failure threshold
*/
void updateSensorMeasurements() {
  for (
    uint8_t i = 0;
    i < CHANNEL_COUNT;
    ++i
  ) {
    MonitorChannel &channel =
      channels[i];

    const bool previousOnline =
      channel.sensorOnline;

    LTC2945::Reading reading;

    if (
      sensors[i].read(reading)
    ) {
      channel.voltage =
        reading.voltage;

      channel.current =
        reading.current;

      channel.readingValid = true;
      channel.sensorOnline = true;
      channel.sensorError = 0;
      channel.consecutiveSensorFailures = 0;
      channel.lastValidReadingMs = millis();

      updateAlarmState(
        channel
      );
    } else {
      channel.sensorError =
        sensors[i].lastError();

      if (
        channel.consecutiveSensorFailures <
        255
      ) {
        ++channel.consecutiveSensorFailures;
      }

      if (
        channel.consecutiveSensorFailures >=
        SENSOR_FAILURES_TO_OFFLINE
      ) {
        channel.sensorOnline = false;
      }

      /*
        Keep the last valid voltage and current.

        Replacing a failed read with zero could make an I2C or
        configuration fault appear to be a genuine rail
        undervoltage condition.
      */
    }

    /*
      Log only actual ONLINE/OFFLINE transitions.
    */
    reportSensorTransition(
      i,
      previousOnline,
      channel.sensorOnline
    );
  }
}