#pragma once

#include <Arduino.h>

constexpr uint32_t SENSOR_I2C_CLOCK_HZ = 100000;
constexpr uint32_t SENSOR_POLL_PERIOD_MS = 200;
constexpr uint8_t SENSOR_FAILURES_TO_OFFLINE = 3;

/*
  Arduino Wire uses 7-bit addresses.

  Schematic device-address byte -> Arduino address:
    CE       -> 0x67
    D0/D1    -> 0x68
    D2/D3    -> 0x69
    D4/D5    -> 0x6A
    D6/D7    -> 0x6B
    D8/D9    -> 0x6C
*/
constexpr uint8_t LTC_ADDRESS_6VA  = 0x67;
constexpr uint8_t LTC_ADDRESS_6VB  = 0x6D;
constexpr uint8_t LTC_ADDRESS_P15V = 0x69;
constexpr uint8_t LTC_ADDRESS_M15V = 0x6A;
constexpr uint8_t LTC_ADDRESS_P5V  = 0x6B;
constexpr uint8_t LTC_ADDRESS_M5V  = 0x6C;

constexpr float SHUNT_6VA_OHMS  = 0.039f;
constexpr float SHUNT_6VB_OHMS  = 0.039f;
constexpr float SHUNT_P5V_OHMS  = 0.050f;
constexpr float SHUNT_M5V_OHMS  = 0.050f;
constexpr float SHUNT_P15V_OHMS = 0.050f;
constexpr float SHUNT_M15V_OHMS = 0.050f;
