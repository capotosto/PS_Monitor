/*
  LTC2945 voltage/current monitor driver.

  Each driver instance represents one LTC2945 connected to an isolated
  measurement channel. The class handles:

    - I2C device validation and register access
    - explicit control-register configuration
    - 12-bit ADC register decoding
    - conversion of raw VIN and delta-sense codes to engineering units
    - channel-specific voltage/current polarity
    - current calculation from the configured shunt resistance
    - basic I2C and data-validity error reporting
*/

#include "LTC2945.h"

#include <math.h>

/*Construct one LTC2945 channel.
  Params:
    wire        - I2C bus used by this device
    address     - LTC2945 7-bit I2C address
    shuntOhms   - installed current-sense resistance in ohms
    voltageSign - +1 or -1 multiplier applied to reported VIN
    currentSign - +1 or -1 multiplier applied to reported current*/
LTC2945::LTC2945(
  TwoWire &wire,
  uint8_t address,
  float shuntOhms,
  float voltageSign,
  float currentSign
)
  : wire_(wire),
    address_(address),
    shuntOhms_(shuntOhms),
    voltageSign_(voltageSign),
    currentSign_(currentSign) {}

/*Validate the configured device parameters, confirm that the LTC2945
  acknowledges on the I2C bus, and place it in the continuous
  SENSE+ measurement mode.
  Software error codes:
    0xF1 - configured I2C address outside LTC2945 range
    0xF2 - invalid shunt resistance

  I2C transaction errors returned by Wire are stored directly in lastError_.*/
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

  /*
    0x05:
      A7 = 0  continuous conversion
      A4 = 0  test mode disabled
      A2 = 1  measure SENSE+ as VIN
      A1 = 0  normal operation
      A0 = 1  multiply SENSE+ by delta-sense

    This is also the LTC2945 power-up default, but it is written explicitly
    so a previously configured device is returned to the expected mode.
  */
  return writeRegister8(
    REG_CONTROL,
    CONTROL_CONTINUOUS_SENSE_PLUS
  );
}

// Probe the configured I2C address without transferring register data.
bool LTC2945::ping() {
  wire_.beginTransmission(address_);
  lastError_ = wire_.endTransmission();
  return lastError_ == 0;
}

//Write one 8-bit LTC2945 register.
bool LTC2945::writeRegister8(uint8_t reg, uint8_t value) {
  wire_.beginTransmission(address_);
  wire_.write(reg);
  wire_.write(value);
  lastError_ = wire_.endTransmission();
  return lastError_ == 0;
}

/*Read a contiguous block of LTC2945 registers.

  The register pointer is written first, followed by a repeated START so the
  bus remains under control while switching from write to read operation.

  The Wire receive buffer is limited, so reads larger than 32 bytes
  are rejected.

  Custom software error codes:
    0xF3 - invalid destination buffer or requested length
    0xF4 - fewer bytes returned than requested
    0xF5 - receive buffer became empty before all bytes were copied*/
bool LTC2945::readRegisters(
  uint8_t startReg,
  uint8_t *buffer,
  size_t length
) {
  if (buffer == nullptr || length == 0 || length > 32) {
    lastError_ = 0xF3;
    return false;
  }

  wire_.beginTransmission(address_);
  wire_.write(startReg);

  // Repeated START: do not release the bus before the read address.
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

    buffer[i] = static_cast<uint8_t>(wire_.read());
  }

  lastError_ = 0;
  return true;
}

//Read one 12-bit LTC2945 ADC result from its two-register representation.
bool LTC2945::read12Bit(
  uint8_t msbRegister,
  uint16_t &code
) {
  uint8_t bytes[2];

  if (!readRegisters(msbRegister, bytes, sizeof(bytes))) {
    return false;
  }

  /*
    Results are left-justified:
      first byte  = bits 11..4
      second byte = bits 3..0 in the upper nibble
  */
  const uint16_t packed =
    (static_cast<uint16_t>(bytes[0]) << 8) |
    static_cast<uint16_t>(bytes[1]);

  code = packed >> 4;
  return true;
}

bool LTC2945::read(Reading &reading) {
  reading = Reading{};

  if (!read12Bit(REG_VIN_MSB, reading.voltageCode)) {
    reading.i2cError = lastError_;
    return false;
  }

  if (!read12Bit(REG_DELTA_SENSE_MSB, reading.currentCode)) {
    reading.i2cError = lastError_;
    return false;
  }

  reading.voltage =
    voltageSign_ *
    static_cast<float>(reading.voltageCode) *
    VIN_LSB_VOLTS;

  const float senseVoltage =
    static_cast<float>(reading.currentCode) *
    DELTA_SENSE_LSB_VOLTS;

  reading.current =
    currentSign_ *
    senseVoltage /
    shuntOhms_;

  reading.power = reading.voltage * reading.current;
  reading.valid =
    isfinite(reading.voltage) &&
    isfinite(reading.current) &&
    isfinite(reading.power);

  reading.i2cError = reading.valid ? 0 : 0xF6;
  lastError_ = reading.i2cError;
  return reading.valid;
}

uint8_t LTC2945::address() const {
  return address_;
}

uint8_t LTC2945::lastError() const {
  return lastError_;
}
