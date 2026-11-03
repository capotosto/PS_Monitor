#pragma once

#include <Arduino.h>
#include <Wire.h>

class LTC2945 {
 public:
  struct Reading {
    float voltage = NAN;
    float current = NAN;
    float power = NAN;
    uint16_t voltageCode = 0;
    uint16_t currentCode = 0;
    bool valid = false;
    uint8_t i2cError = 0;
  };

  /*
      voltageSign:
      +1.0 for +6VA, +6VB, +5V, +15V
      -1.0 for -5V and -15V

    currentSign:
      +1.0 when normal load current produces SENSE+ > SENSE-
  */
  LTC2945(
    TwoWire &wire,
    uint8_t address,
    float shuntOhms,
    float voltageSign = 1.0f,
    float currentSign = 1.0f
  );

  bool begin();
  bool ping();
  bool read(Reading &reading);

  uint8_t address() const;
  uint8_t lastError() const;

 private:
  static constexpr uint8_t REG_CONTROL = 0x00;
  static constexpr uint8_t REG_DELTA_SENSE_MSB = 0x14;
  static constexpr uint8_t REG_VIN_MSB = 0x1E;

  static constexpr uint8_t CONTROL_CONTINUOUS_SENSE_PLUS = 0x05;

  static constexpr float VIN_LSB_VOLTS = 0.025f;
  static constexpr float DELTA_SENSE_LSB_VOLTS = 25.0e-6f;

  TwoWire &wire_;
  uint8_t address_;
  float shuntOhms_;
  float voltageSign_;
  float currentSign_;
  uint8_t lastError_ = 0;

  bool writeRegister8(uint8_t reg, uint8_t value);
  bool readRegisters(uint8_t startReg, uint8_t *buffer, size_t length);
  bool read12Bit(uint8_t msbRegister, uint16_t &code);
};
