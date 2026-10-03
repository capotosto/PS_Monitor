/*
  PSC protocol server for communication between the Arduino GIGA and
  the EPICS PSCDriver IOC.

  Packet format:
    Bytes 0-1 : ASCII magic "PS"
    Bytes 2-3 : 16-bit message ID, big-endian
    Bytes 4-7 : 32-bit body length, big-endian
    Bytes 8+  : message body

  The server:
    - accepts one PSC client connection at a time
    - periodically publishes measurements and alarm states
    - publishes a complete state snapshot when a client connects
    - accepts alarm-limit setpoints from the IOC
    - validates and stores accepted limits in persistent storage
    - echoes the actual stored value so EPICS AO records can resynchronize

  All multibyte numeric values are serialized in big-endian order.
*/

#include "PscProtocol.h"

#include <Arduino.h>
#include <Ethernet.h>

#include <math.h>
#include <string.h>

#include "AppConfig.h"
#include "AppState.h"
#include "PersistentStorage.h"

namespace {
EthernetServer pscServer(PSC_PORT);
EthernetClient pscClient;

/* Incremental receive-parser state. Ethernet data may arrive in partial 
packets, so the header and body are assembled across servicePsc() calls.*/
uint32_t lastPscPublishMs = 0;
uint8_t pscHeaderBuffer[8];
uint8_t pscBodyBuffer[PSC_MAX_BODY_LENGTH];
uint8_t pscHeaderIndex = 0;
uint32_t pscBodyIndex = 0;
uint16_t pscIncomingMessageId = 0;
uint32_t pscIncomingBodyLength = 0;
bool pscReadingBody = false;
}

void initializePscServer() {
  pscServer.begin();
}

bool pscIsConnected() {
  return static_cast<bool>(pscClient) && pscClient.connected();
}

void resetPscReceiveState() {
  pscHeaderIndex = 0;
  pscBodyIndex = 0;
  pscIncomingMessageId = 0;
  pscIncomingBodyLength = 0;
  pscReadingBody = false;
}

/*PSC messages use big-endian. Helpers convert ints and floats between
wire represnetation and Giga native.*/
uint16_t readU16BigEndian(const uint8_t *source) {
  return
    (static_cast<uint16_t>(source[0]) << 8) |
    static_cast<uint16_t>(source[1]);
}

uint32_t readU32BigEndian(const uint8_t *source) {
  return
    (static_cast<uint32_t>(source[0]) << 24) |
    (static_cast<uint32_t>(source[1]) << 16) |
    (static_cast<uint32_t>(source[2]) << 8) |
    static_cast<uint32_t>(source[3]);
}

void writeU16BigEndian(uint8_t *destination, uint16_t value) {
  destination[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
  destination[1] = static_cast<uint8_t>(value & 0xFF);
}

void writeU32BigEndian(uint8_t *destination, uint32_t value) {
  destination[0] = static_cast<uint8_t>((value >> 24) & 0xFF);
  destination[1] = static_cast<uint8_t>((value >> 16) & 0xFF);
  destination[2] = static_cast<uint8_t>((value >> 8) & 0xFF);
  destination[3] = static_cast<uint8_t>(value & 0xFF);
}

float readFloatBigEndian(const uint8_t *source) {
  const uint32_t bits = readU32BigEndian(source);
  float value = 0.0f;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

void writeFloatBigEndian(uint8_t *destination, float value) {
  uint32_t bits = 0;
  memcpy(&bits, &value, sizeof(bits));
  writeU32BigEndian(destination, bits);
}

/*Writes a PSC packet segment to the connected TCP client.

  EthernetClient::write() is not assumed to transmit the complete buffer
  in one call. Continue writing until all bytes are sent, the connection
  closes, or PSC_WRITE_TIMEOUT_MS expires.*/

bool writeAllPscBytes(const uint8_t *data, size_t length) {
  if (!pscIsConnected()) {
    return false;
  }

  size_t offset = 0;
  const uint32_t start = millis();

  while (offset < length && pscClient.connected()) {
    const size_t written = pscClient.write(data + offset, length - offset);

    if (written > 0) {
      offset += written;
      continue;
    }

    if (millis() - start >= PSC_WRITE_TIMEOUT_MS) {
      break;
    }

    delay(1);
  }

  return offset == length;
}

/*Builds and transmits one PSC message.
  Header:
    "PS" + uint16 message ID + uint32 payload length
*/
bool sendPscMessage(
  uint16_t messageId,
  const uint8_t *body,
  uint32_t bodyLength
) {
  if (!pscIsConnected()) {
    return false;
  }

  uint8_t header[8];
  header[0] = 'P';
  header[1] = 'S';
  writeU16BigEndian(&header[2], messageId);
  writeU32BigEndian(&header[4], bodyLength);

  if (!writeAllPscBytes(header, sizeof(header))) {
    return false;
  }

  return bodyLength == 0 || writeAllPscBytes(body, bodyLength);
}

/*
  Alarm/status bit definitions sent in PSC_MSG_ALARMS:

    bit 0 - voltage low alarm
    bit 1 - voltage high alarm
    bit 2 - current low alarm
    bit 3 - current high alarm
    bit 4 - sensor offline / communication fault

  Remaining bits are reserved.
*/
uint32_t alarmMaskForChannel(const MonitorChannel &channel) {
  uint32_t mask = 0;

  if (channel.voltageLowAlarm) {
    mask |= 1UL << 0;
  }
  if (channel.voltageHighAlarm) {
    mask |= 1UL << 1;
  }
  if (channel.currentLowAlarm) {
    mask |= 1UL << 2;
  }
  if (channel.currentHighAlarm) {
    mask |= 1UL << 3;
  }
  if (!channel.sensorOnline) {
    mask |= 1UL << 4;
  }

  return mask;
}

/*Write out voltage/current pairs for all channels.

  Invalid channels are written as NaN rather than 0.0 so an
  I2C or sensor failure cannot be mistaken for real readouts.*/
bool sendPscMeasurements() {
  uint8_t body[CHANNEL_COUNT * 2 * sizeof(float)];
  size_t offset = 0;

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    const float voltage =
      channels[i].readingValid ? channels[i].voltage : NAN;

    const float current =
      channels[i].readingValid ? channels[i].current : NAN;

    writeFloatBigEndian(&body[offset], voltage);
    offset += sizeof(float);
    writeFloatBigEndian(&body[offset], current);
    offset += sizeof(float);
  }

  return sendPscMessage(
    PSC_MSG_MEASUREMENTS,
    body,
    sizeof(body)
  );
}

bool sendPscLimits() {
  uint8_t body[CHANNEL_COUNT * 4 * sizeof(float)];
  size_t offset = 0;

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    writeFloatBigEndian(&body[offset], channels[i].limits.voltageLow);
    offset += sizeof(float);
    writeFloatBigEndian(&body[offset], channels[i].limits.voltageHigh);
    offset += sizeof(float);
    writeFloatBigEndian(&body[offset], channels[i].limits.currentLow);
    offset += sizeof(float);
    writeFloatBigEndian(&body[offset], channels[i].limits.currentHigh);
    offset += sizeof(float);
  }

  return sendPscMessage(PSC_MSG_LIMITS, body, sizeof(body));
}

bool sendPscAlarms() {
  uint8_t body[CHANNEL_COUNT * sizeof(uint32_t)];
  size_t offset = 0;

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    writeU32BigEndian(&body[offset], alarmMaskForChannel(channels[i]));
    offset += sizeof(uint32_t);
  }

  return sendPscMessage(PSC_MSG_ALARMS, body, sizeof(body));
}

/*PSC setpoint address map.

  Each channel holds four consecutive addresses:

    channel * 4 + 0 : voltage low limit
    channel * 4 + 1 : voltage high limit
    channel * 4 + 2 : current low limit
    channel * 4 + 3 : current high limit

  Example:
    addresses 0-3   -> channel 0
    addresses 4-7   -> channel 1
    ...
*/
float limitValueByAddress(uint32_t address) {
  const uint8_t channelIndex = address / 4;
  const uint8_t fieldIndex = address % 4;
  const AlarmLimits &limits = channels[channelIndex].limits;

  switch (fieldIndex) {
    case 0:
      return limits.voltageLow;
    case 1:
      return limits.voltageHigh;
    case 2:
      return limits.currentLow;
    default:
      return limits.currentHigh;
  }
}

bool sendPscSetpointEcho(uint32_t address, float value) {
  uint8_t body[8];
  writeU32BigEndian(&body[0], address);
  writeFloatBigEndian(&body[4], value);
  return sendPscMessage(PSC_MSG_SETPOINT, body, sizeof(body));
}

void sendPscChannelSetpointEchoes(uint8_t channelIndex) {
  if (!pscIsConnected() || channelIndex >= CHANNEL_COUNT) {
    return;
  }

  const uint32_t firstAddress = static_cast<uint32_t>(channelIndex) * 4;

  for (uint32_t address = firstAddress;
       address < firstAddress + 4;
       ++address) {
    sendPscSetpointEcho(address, limitValueByAddress(address));
  }
}

void sendAllPscSetpointEchoes() {
  if (!pscIsConnected()) {
    return;
  }

  for (uint32_t address = 0; address < CHANNEL_COUNT * 4; ++address) {
    sendPscSetpointEcho(address, limitValueByAddress(address));
  }
}

/*Send all states required to synchronize the IOC.
  This prevents the IOC from waiting for multiple periodic publish cycles
  before measurements, limits, alarms, and AO setpoint readbacks are valid.*/
void sendCompletePscSnapshot() {
  if (!pscIsConnected()) {
    return;
  }

  sendPscMeasurements();
  sendPscLimits();
  sendPscAlarms();
  sendAllPscSetpointEchoes();
  lastPscPublishMs = millis();
}

/*Apply one alarm-limit update received from EPICS.

  The requested value is accepted only if:
    1. the address maps to a valid channel/limit field,
    2. the value is finite,
    3. the complete set of limits remains logically valid, and
    4. the updated configuration can be saved to persistent storage.

  If validation or persistent storage fails, the previous limits are
  restored so RAM and NVM configuration remain consistent.*/
bool applyPscSetpoint(uint32_t address, float requestedValue) {
  if (address >= CHANNEL_COUNT * 4 || !isfinite(requestedValue)) {
    return false;
  }

  const uint8_t channelIndex = address / 4;
  const uint8_t fieldIndex = address % 4;
  MonitorChannel &channel = channels[channelIndex];
  const AlarmLimits previousLimits = channel.limits;

  switch (fieldIndex) {
    case 0:
      channel.limits.voltageLow = requestedValue;
      break;
    case 1:
      channel.limits.voltageHigh = requestedValue;
      break;
    case 2:
      channel.limits.currentLow = requestedValue;
      break;
    case 3:
      channel.limits.currentHigh = requestedValue;
      break;
    default:
      return false;
  }

  if (!alarmLimitsAreValid(channel.limits)) {
    channel.limits = previousLimits;
    return false;
  }

  updateAlarmState(channel);

  if (!savePersistentSettings()) {
    channel.limits = previousLimits;
    updateAlarmState(channel);
    return false;
  }

  return true;
}

/*Process a complete received PSC message. The embedded controller currently
accepts only PSC_MSG_SETPOINT messagesfrom the IOC. All other message types
are ignored and reported over the serial console.*/

void handlePscMessage(
  uint16_t messageId,
  const uint8_t *body,
  uint32_t bodyLength
) {
  if (messageId != PSC_MSG_SETPOINT || bodyLength != 8) {
    Serial.print("Ignoring PSC message ID ");
    Serial.print(messageId);
    Serial.print(" with body length ");
    Serial.println(bodyLength);
    return;
  }

  const uint32_t address = readU32BigEndian(&body[0]);
  const float requestedValue = readFloatBigEndian(&body[4]);

  if (address >= CHANNEL_COUNT * 4) {
    Serial.print("Rejected PSC setpoint address ");
    Serial.println(address);
    return;
  }

  const bool accepted = applyPscSetpoint(address, requestedValue);
  const float actualValue = limitValueByAddress(address);

  Serial.print("PSC setpoint address ");
  Serial.print(address);
  Serial.print(accepted ? " accepted: " : " rejected; actual: ");
  Serial.println(actualValue, 4);

  // Echo the actual device value so info(SYNC, "SAME") AO records resync.
  sendPscSetpointEcho(address, actualValue);
  sendPscLimits();
  sendPscAlarms();
}

/*
  Incremental PSC packet parser.

  TCP is a byte stream, so a complete PSC packet may not arrive in a single
  read. This state machine:

    1. searches for the "PS" synchronization bytes,
    2. collects the remaining 8-byte header,
    3. extracts message ID and body length,
    4. validates the body length,
    5. collects the body,
    6. dispatches the complete message.

  If synchronization is lost, incoming bytes are discarded until another
  valid "PS" header prefix is found.
*/
void consumePscByte(uint8_t value) {
  if (pscReadingBody) {
    pscBodyBuffer[pscBodyIndex++] = value;

    if (pscBodyIndex >= pscIncomingBodyLength) {
      handlePscMessage(
        pscIncomingMessageId,
        pscBodyBuffer,
        pscIncomingBodyLength
      );
      resetPscReceiveState();
    }

    return;
  }

  if (pscHeaderIndex == 0) {
    if (value == 'P') {
      pscHeaderBuffer[0] = value;
      pscHeaderIndex = 1;
    }
    return;
  }

  if (pscHeaderIndex == 1) {
    if (value == 'S') {
      pscHeaderBuffer[1] = value;
      pscHeaderIndex = 2;
    } else if (value == 'P') {
      pscHeaderBuffer[0] = value;
      pscHeaderIndex = 1;
    } else {
      pscHeaderIndex = 0;
    }
    return;
  }

  pscHeaderBuffer[pscHeaderIndex++] = value;

  if (pscHeaderIndex < sizeof(pscHeaderBuffer)) {
    return;
  }

  pscIncomingMessageId = readU16BigEndian(&pscHeaderBuffer[2]);
  pscIncomingBodyLength = readU32BigEndian(&pscHeaderBuffer[4]);
  pscBodyIndex = 0;

  if (pscIncomingBodyLength > PSC_MAX_BODY_LENGTH) {
    Serial.print("PSC body too large: ");
    Serial.println(pscIncomingBodyLength);
    pscClient.stop();
    resetPscReceiveState();
    return;
  }

  if (pscIncomingBodyLength == 0) {
    handlePscMessage(pscIncomingMessageId, nullptr, 0);
    resetPscReceiveState();
    return;
  }

  pscReadingBody = true;
}

void acceptPscClient() {
  EthernetClient incoming = pscServer.accept();

  if (!incoming) {
    return;
  }

  if (pscIsConnected()) {
    // PSCDriver normally creates only one connection. Reject extras cleanly.
    incoming.stop();
    return;
  }

  pscClient.stop();
  pscClient = incoming;
  resetPscReceiveState();

  Serial.print("PSC client connected from ");
  Serial.println(pscClient.remoteIP());
  sendCompletePscSnapshot();
}

/*
  Non-blocking PSC network service routine.

  Called repeatedly from the main application loop to:
    - detect disconnected clients,
    - accept a new IOC connection,
    - consume all currently available receive bytes,
    - periodically publish measurements and alarm state.

  Limits are not sent every cycle because they change only when
  configuration is modified; a complete copy is sent on initial connection
  and after a setpoint transaction.
*/
void servicePsc() {
  if (!ethernetHardwarePresent) {
    return;
  }

  if (pscClient && !pscClient.connected()) {
    Serial.println("PSC client disconnected.");
    pscClient.stop();
    resetPscReceiveState();
  }

  acceptPscClient();

  if (!pscIsConnected()) {
    return;
  }

  while (pscClient.available() > 0) {
    const int value = pscClient.read();

    if (value < 0) {
      break;
    }

    consumePscByte(static_cast<uint8_t>(value));
  }

  const uint32_t now = millis();

  if (now - lastPscPublishMs >= PSC_PUBLISH_PERIOD_MS) {
    lastPscPublishMs = now;
    sendPscMeasurements();
    sendPscAlarms();
  }
}
