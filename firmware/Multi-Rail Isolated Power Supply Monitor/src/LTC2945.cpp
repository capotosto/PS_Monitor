/*
  LTC2945 voltage/current monitor driver.

  Each driver instance represents one LTC2945 connected to an isolated
  measurement channel.

  The driver handles:

    - I2C device validation and register access
    - explicit CONTROL-register configuration
    - automatic recovery after LTC2945 power cycling
    - selectable VIN source (SENSE+ or VDD)
    - CONTROL-register readback verification
    - 12-bit ADC register decoding
    - conversion of raw values to engineering units
    - channel-specific voltage/current polarity
    - current calculation from configured shunt resistance
    - I2C and data-validity error reporting

  Positive rails use SENSE+ as the VIN measurement source.

  Negative rails using low-side current sensing use VDD as the VIN
  measurement source. The LTC2945 sees this as a positive local voltage
  magnitude. voltageSign_ converts that magnitude to the negative
  system-level rail voltage.

  The CONTROL register is checked before each measurement. This is
  important because an LTC2945 that loses power while the Arduino remains
  running will return to its power-up CONTROL value. The driver detects
  that condition and restores the channel configuration automatically.
*/

#include "LTC2945.h"

#include <math.h>


/*
  Construct one LTC2945 channel.

  Params:
    wire          - I2C bus used by this device
    address       - LTC2945 7-bit I2C address
    shuntOhms     - installed current-sense resistance in ohms
    voltageSign   - +1 or -1 multiplier applied to reported VIN
    currentSign   - +1 or -1 multiplier applied to reported current
    voltageSource - VIN ADC source
*/
LTC2945::LTC2945(
  TwoWire &wire,
  uint8_t address,
  float shuntOhms,
  float voltageSign,
  float currentSign,
  LTC2945::VoltageSource voltageSource
)
  : wire_(wire),
    address_(address),
    shuntOhms_(shuntOhms),
    voltageSign_(voltageSign),
    currentSign_(currentSign),
    voltageSource_(voltageSource) {}


/*
  Return the CONTROL-register value required for this channel.
*/
uint8_t LTC2945::expectedControlValue() const {
  if (voltageSource_ == VoltageSource::Vdd) {
    return CONTROL_CONTINUOUS_VDD;
  }

  return CONTROL_CONTINUOUS_SENSE_PLUS;
}


/*
  Configure the LTC2945 CONTROL register and verify that the value
  was accepted.

  Software error:
    0xF7 - CONTROL register readback did not match expected value
*/
bool LTC2945::configure() {
  const uint8_t expected = expectedControlValue();

  if (!writeRegister8(REG_CONTROL, expected)) {
    return false;
  }

  uint8_t readback = 0;

  if (!readRegister8(REG_CONTROL, readback)) {
    return false;
  }

  if (readback != expected) {
    lastError_ = 0xF7;
    return false;
  }

  lastError_ = 0;
  return true;
}


/*
  Confirm that the device still has the correct CONTROL configuration.

  This provides automatic recovery when an individual monitored rail is
  power-cycled while the Arduino remains powered.

  Example for -5V / -15V:

    normal configured state:
      CONTROL = 0x01

    rail power cycled:
      LTC2945 resets
      CONTROL returns to 0x05

    next measurement:
      driver detects 0x05
      driver rewrites 0x01
      measurement proceeds normally
*/
bool LTC2945::ensureConfigured() {
  const uint8_t expected = expectedControlValue();

  uint8_t current = 0;

  if (!readRegister8(REG_CONTROL, current)) {
    return false;
  }

  if (current == expected) {
    lastError_ = 0;
    return true;
  }

  return configure();
}


/*
  Validate the configured device parameters, confirm that the LTC2945
  acknowledges, configure its CONTROL register, and verify the
  configuration.

  Software errors:
    0xF1 - configured I2C address outside LTC2945 range
    0xF2 - invalid shunt resistance
    0xF7 - CONTROL register verification failed

  Wire/I2C errors are stored directly in lastError_.
*/
bool LTC2945::begin() {
  if (address_ < 0x67 || address_ > 0x6F) {
    lastError_ = 0xF1;
    return false;
  }

  if (!isfinite(shuntOhms_) || shuntOhms_ <= 0.0f) {
    lastError_ = 0xF2;
    return false;
  }

  if (!ping()) {
    return false;
  }

  return configure();
}


/*
  Probe the configured I2C address without transferring register data.
*/
bool LTC2945::ping() {
  wire_.beginTransmission(address_);

  lastError_ = wire_.endTransmission();

  return lastError_ == 0;
}


/*
  Write one 8-bit LTC2945 register.
*/
bool LTC2945::writeRegister8(
  uint8_t reg,
  uint8_t value
) {
  wire_.beginTransmission(address_);

  wire_.write(reg);
  wire_.write(value);

  lastError_ = wire_.endTransmission();

  return lastError_ == 0;
}


/*
  Read one 8-bit LTC2945 register.
*/
bool LTC2945::readRegister8(
  uint8_t reg,
  uint8_t &value
) {
  return readRegisters(
    reg,
    &value,
    1
  );
}


/*
  Read a contiguous block of LTC2945 registers.

  The register pointer is written first, followed by a repeated START
  so the bus remains under control while switching from write to read.

  The Wire receive buffer is limited, so reads larger than 32 bytes
  are rejected.

  Software errors:
    0xF3 - invalid destination buffer or requested length
    0xF4 - fewer bytes returned than requested
    0xF5 - receive buffer became empty before all bytes were copied
*/
bool LTC2945::readRegisters(
  uint8_t startReg,
  uint8_t *buffer,
  size_t length
) {
  if (
    buffer == nullptr ||
    length == 0 ||
    length > 32
  ) {
    lastError_ = 0xF3;
    return false;
  }

  wire_.beginTransmission(address_);
  wire_.write(startReg);

  /*
    Repeated START:
    keep control of the bus while switching from write to read.
  */
  lastError_ = wire_.endTransmission(false);

  if (lastError_ != 0) {
    return false;
  }

  const size_t received = wire_.requestFrom(
    static_cast<int>(address_),
    static_cast<int>(length)
  );

  if (received != length) {
    lastError_ = 0xF4;

    while (wire_.available()) {
      wire_.read();
    }

    return false;
  }

  for (size_t i = 0; i < length; ++i) {
    if (!wire_.available()) {
      lastError_ = 0xF5;
      return false;
    }

    buffer[i] =
      static_cast<uint8_t>(wire_.read());
  }

  lastError_ = 0;
  return true;
}


/*
  Read one 12-bit LTC2945 ADC result from its two-register
  representation.
*/
bool LTC2945::read12Bit(
  uint8_t msbRegister,
  uint16_t &code
) {
  uint8_t bytes[2];

  if (!readRegisters(
        msbRegister,
        bytes,
        sizeof(bytes)
      )) {
    return false;
  }

  /*
    ADC results are left-justified:

      first byte:
        bits 11..4

      second byte:
        bits 3..0 in the upper nibble
  */
  const uint16_t packed =
    (static_cast<uint16_t>(bytes[0]) << 8) |
    static_cast<uint16_t>(bytes[1]);

  code = packed >> 4;

  return true;
}


/*
  Read voltage and current measurements.

  Before accepting a measurement, the CONTROL register is checked.

  This means an individual LTC2945 can lose power and restart while
  the Arduino remains powered. When the device returns, its CONTROL
  register is automatically restored before measurement data is used.
*/
bool LTC2945::read(
  Reading &reading
) {
  reading = Reading{};

  /*
    Verify the channel configuration before reading ADC results.

    This is especially important for the negative rails. Their
    LTC2945s must use:

      CONTROL = 0x01
      VIN source = VDD

    rather than the power-up default:

      CONTROL = 0x05
      VIN source = SENSE+
  */
  if (!ensureConfigured()) {
    reading.i2cError = lastError_;
    return false;
  }

  if (!read12Bit(
        REG_VIN_MSB,
        reading.voltageCode
      )) {
    reading.i2cError = lastError_;
    return false;
  }

  if (!read12Bit(
        REG_DELTA_SENSE_MSB,
        reading.currentCode
      )) {
    reading.i2cError = lastError_;
    return false;
  }

  /*
    VIN ADC:
      25 mV / LSB

    Positive rails:
      source = SENSE+

    Negative rails:
      source = VDD

    voltageSign_ converts the positive local VDD magnitude of a
    negative rail to its negative system-level value.
  */
  reading.voltage =
    voltageSign_ *
    static_cast<float>(
      reading.voltageCode
    ) *
    VIN_LSB_VOLTS;

  /*
    Delta-sense ADC:
      25 uV / LSB

    Current:
      I = Vsense / Rshunt
  */
  const float senseVoltage =
    static_cast<float>(
      reading.currentCode
    ) *
    DELTA_SENSE_LSB_VOLTS;

  reading.current =
    currentSign_ *
    senseVoltage /
    shuntOhms_;

  /*
    Calculate signed electrical power from the engineering-unit
    voltage and current values.
  */
  reading.power =
    reading.voltage *
    reading.current;

  reading.valid =
    isfinite(reading.voltage) &&
    isfinite(reading.current) &&
    isfinite(reading.power);

  if (!reading.valid) {
    reading.i2cError = 0xF6;
    lastError_ = 0xF6;

    return false;
  }

  reading.i2cError = 0;
  lastError_ = 0;

  return true;
}


uint8_t LTC2945::address() const {
  return address_;
}


uint8_t LTC2945::lastError() const {
  return lastError_;
}