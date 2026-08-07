# Multi-Rail Isolated Power Supply Monitoring System

**Repository:** `PS_Monitor`  
**Author:** Mike Capotosto

## Project Overview

The Multi-Rail Isolated Power Supply Monitoring System measures the voltage and current of up to six floating power-supply rails while preserving galvanic isolation between measurement channels. Each rail is monitored by an LTC2945 power monitor connected through an isolated I²C interface to an Arduino GIGA R1 WiFi. The Arduino firmware performs data acquisition, engineering-unit conversion, alarm evaluation, persistent configuration storage, local display control, HTTP service, and Ethernet communication with an EPICS Input/Output Controller. Measurement and status information is presented locally on the GIGA Display Shield, through a browser-based dashboard, and remotely through a Phoebus Control System Studio operator interface.

The monitored rails are:

- `+6VA`
- `+6VB`
- `+5V`
- `-5V`
- `+15V`
- `-15V`

---

## System Features

- Six isolated voltage and current measurement channels
- LTC2945 voltage, current, and power monitoring
- Independent I²C isolation for each floating rail
- Support for positive and negative supply rails
- Configurable upper and lower voltage limits
- Configurable upper and lower current limits
- Persistent alarm and network settings stored in internal QSPI flash
- Local touchscreen display using the Arduino GIGA Display Shield
- Browser-based monitoring and configuration dashboard
- Ethernet communication through the Arduino Ethernet Shield
- PSC (Portable Streaming Controller) protocol interface for EPICS integration
- EPICS Process Variables for measurements, limits, alarms, and status
- Phoebus OPI for centralized operator monitoring
- I²C communication-error detection
- Text-based alarm states such as `OVL`, `UVL` (over/under voltage limit), `OCL`, and `UCL` (over/under current limit)

---

## System Architecture

### Data Flow

```text
┌──────────────────────────────────────────────┐
│ Floating Power-Supply Rails                  │
│ +6VA, +6VB, +5V, -5V, +15V, and -15V        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ LTC2945 Voltage and Current Monitors         │
│ One monitor per power-supply rail            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Isolated I²C Interfaces                      │
│ Maintains isolation between floating rails   │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ Arduino GIGA R1 WiFi Firmware                │
│                                              │
│ • Sensor acquisition                         │
│ • Engineering-unit conversion                │
│ • Negative-rail sign correction              │
│ • Alarm evaluation                           │
│ • Persistent settings                        │
│ • Local display                              │
│ • HTTP dashboard                             │
│ • PSC protocol server                        │
└───────────────┬────────────────────┬─────────┘
                │                    │
                ▼                    ▼
┌─────────────────────────┐  ┌──────────────────────┐
│ GIGA Display Shield     │  │ Ethernet Network     │
│ Local touchscreen UI    │  │ HTTP and PSC         │
└─────────────────────────┘  └──────────┬───────────┘
                                       │
                                       ▼
                            ┌────────────────────────┐
                            │ EPICS IOC              │
                            │ PSCDriver and records  │
                            └──────────┬─────────────┘
                                       │
                                       ▼
                            ┌────────────────────────┐
                            │ Phoebus / CSS OPI      │
                            │ Operator interface     │
                            └────────────────────────┘
```

### Major Subsystems

| Subsystem | Function |
|---|---|
| Sensor hardware | Measures rail voltage, shunt voltage, current, and power |
| I²C isolation | Preserves galvanic isolation between floating rails |
| Arduino firmware | Acquires data, evaluates alarms, stores settings, and manages communications |
| Local display | Shows rail measurements, limits, alarms, and communication status |
| HTTP dashboard | Provides browser-based monitoring and configuration |
| PSC interface | Transfers measurement and status data to the EPICS IOC |
| EPICS IOC | Converts device data into EPICS Process Variables |
| Phoebus OPI | Provides the centralized operator interface |

---

## Repository Structure

```text
PS_Monitor/
├── README.md
├── hardware/
│   ├── kicad/
│   ├── bom/
│   ├── gerbers/
│   ├── mechanical/
│   └── datasheets/
├── firmware/
│   ├── platformio.ini
│   ├── include/
│   ├── lib/
│   ├── src/
│   └── test/
├── epics-ioc/
│   ├── configure/
│   ├── db/
│   ├── dbd/
│   ├── iocBoot/
│   ├── psuMonitorApp/
│   └── opi/
└── documentation/
```

### Directory Descriptions

- **`/hardware`**  
  KiCad schematic and PCB files, manufacturing outputs, bill of materials, mechanical drawings, and related.

- **`/firmware`**  
  PlatformIO project for the Arduino GIGA R1 WiFi. This directory contains the application source code, configuration headers, local libraries, and build configuration.

- **`/epics-ioc`**  
  EPICS IOC source tree containing database files, record definitions, startup scripts, PSCDriver configuration, device communication settings, and Phoebus Control System Studio displays.

- **`/documentation`**  
  Assorted Documentation

---

## Hardware

### Primary Components

- Arduino GIGA R1 WiFi
- Arduino GIGA Display Shield
- Arduino Ethernet Shield
- LTC2945 voltage, current, and power monitors
- DC1697A LTC2945 demonstration board for prototype testing
- Per-channel I²C digital isolators
- Current-sense shunt resistors
- Custom monitoring and interface PCB
- Six isolated power-supply inputs

### Measurement Method

Each LTC2945 measures:

- Supply voltage
- Differential voltage across a current-sense shunt
- Calculated load current
- Calculated electrical power

Because each monitored supply may float at a different potential, every sensor channel communicates through its own isolated I²C interface. Negative rails are monitored within their isolated domains, and the firmware applies the appropriate sign to the reported engineering values.

---

## Firmware

The firmware is built with PlatformIO using the Arduino Mbed OS framework.

### Main Firmware Modules

| Module | Responsibility |
|---|---|
| `AppState` | Global channel data, settings, alarms, and system state |
| `SensorManager` | Sensor initialization, acquisition, and channel updates |
| `LTC2945` | Low-level LTC2945 register access and unit conversion |
| `DisplayUI` | GIGA Display Shield rendering and status updates |
| `EthernetServices` | Ethernet initialization and network service handling |
| `HttpDashboard` | Browser-based monitoring and configuration |
| `PscProtocol` | PSC protocol communication with the EPICS IOC |
| `PersistentStorage` | QSPI storage of alarm limits and network settings |
| `main` | System initialization and application scheduling |

### Firmware Configuration

Hardware-specific settings are stored in configuration headers, including:

- I²C addresses
- Shunt-resistance values
- Channel names
- Rail polarity
- Voltage and current scaling
- Default alarm limits
- Static network configuration
- MAC address
- PSC port configuration
- Sensor polling intervals

---

## Persistent Settings

The firmware stores configuration data in the Arduino GIGA internal QSPI flash using LittleFS.

Saved settings include:

- Per-channel voltage-low limit
- Per-channel voltage-high limit
- Per-channel current-low limit
- Per-channel current-high limit
- Static IP address
- Subnet mask
- Gateway address
- DNS server address
---

## Network Interfaces

### HTTP Dashboard

The firmware hosts a local web interface for:

- Viewing voltage and current measurements
- Viewing alarm and communication status
- Editing alarm limits
- Editing network parameters
- Saving settings to QSPI

### PSC Protocol

The Arduino exposes a PSC protocol service over Ethernet. The EPICS IOC connects to the device using PSCDriver and maps transmitted parameters into EPICS records.

---

## EPICS IOC

### Requirements

- EPICS Base
- ASYN
- PSCDriver
- A supported Linux environment
- Phoebus for the operator interface

### Build the IOC

From the repository root:

```bash
cd epics-ioc
make
```

### Start the IOC

```bash
cd iocBoot/iocpsuMonitor
./st.cmd
```

An equivalent direct launch command may also be used:

```bash
../../bin/linux-x86_64/psuMonitor st.cmd
```

### Example IOC Configuration

```text
P=TEST:
R=GIGA
DEVICE=GIGA_PSC
HOST=192.168.1.177
PORT=8765
```

The final values are defined in the IOC startup script.

---

## EPICS Process Variables

The IOC is intended to provide Process Variables for:

- Channel voltage
- Channel current
- Voltage-low limit
- Voltage-high limit
- Current-low limit
- Current-high limit
- Voltage alarm status
- Current alarm status
- Sensor communication status
- I²C error status
- Arduino connection status
- Network information
- Firmware status

### Alarm States

| Status | Meaning |
|---|---|
| `OK` | Measurement is within configured limits |
| `OVL` | Over-voltage limit |
| `UVL` | Under-voltage limit |
| `OCL` | Over-current limit |
| `UCL` | Under-current limit |
| `I2C Error` | Sensor communication failure |
| `Disconnected` | IOC communication failure |

---

## Operator Interface

The Phoebus OPI provides a centralized display for all monitored rails.

Planned or implemented interface elements include:

- Voltage and current readbacks
- Alarm-limit displays
- Text-based alarm indicators
- Connection-status indicator
- I²C error indicator
- Per-channel status cards
- Network and firmware information
- Overall system status

---

## Project Milestones

- [x] Define system requirements and monitored power rails
- [x] Select the Arduino GIGA R1 WiFi as the primary controller
- [x] Establish the PlatformIO firmware project
- [x] Develop the initial six-channel display layout
- [x] Add configurable voltage and current alarm limits
- [x] Establish the Ethernet and PSC communication architecture
- [x] Complete single-channel LTC2945 prototype validation
- [ ] Verify current scaling for each shunt-resistor value
- [ ] Complete six-channel isolated I²C hardware
- [ ] Finalize persistent storage and recovery testing
- [ ] Complete browser-based configuration testing
- [ ] Finalize EPICS database records
- [ ] Complete Phoebus OPI
- [ ] Fabricate and assemble the custom PCB
- [ ] Calibrate all measurement channels
- [ ] Perform end-to-end system validation
- [ ] Complete final project documentation

---
