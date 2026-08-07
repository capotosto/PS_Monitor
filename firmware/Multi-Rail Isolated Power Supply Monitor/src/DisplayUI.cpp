#include "DisplayUI.h"

#include <Arduino.h>
#include <Arduino_GigaDisplay_GFX.h>
#include <Ethernet.h>

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "AppConfig.h"
#include "AppState.h"

namespace {

GigaDisplay_GFX display;

uint16_t COLOR_BLACK;
uint16_t COLOR_WHITE;
uint16_t COLOR_BACKGROUND;
uint16_t COLOR_HEADER;
uint16_t COLOR_CARD;
uint16_t COLOR_BORDER;
uint16_t COLOR_OK;
uint16_t COLOR_ALARM;
uint16_t COLOR_WARNING;
uint16_t COLOR_CYAN;
uint16_t COLOR_MUTED;

constexpr int SCREEN_WIDTH = 800;
constexpr int SCREEN_HEIGHT = 480;
constexpr int HEADER_HEIGHT = 58;
constexpr int MARGIN_X = 12;
constexpr int GAP_X = 10;
constexpr int GAP_Y = 10;
constexpr int CARD_WIDTH = 252;
constexpr int CARD_HEIGHT = 202;

struct ChannelDisplaySnapshot {
  bool initialized = false;

  int32_t voltageMilli = 0;
  int32_t currentMilli = 0;

  int32_t voltageLowMilli = 0;
  int32_t voltageHighMilli = 0;
  int32_t currentLowMilli = 0;
  int32_t currentHighMilli = 0;

  uint8_t alarmMask = 0;
  bool readingValid = false;
  bool sensorOnline = false;
  bool overallAlarm = false;
};

struct HeaderDisplaySnapshot {
  bool initialized = false;
  bool hardwarePresent = false;
  int linkStatus = -1;
  uint32_t packedIp = 0;
};

ChannelDisplaySnapshot channelDisplayCache[CHANNEL_COUNT];
HeaderDisplaySnapshot headerDisplayCache;

/*
  Screen arrangement:

    +6VA     +5V      +15V
    +6VB     -5V      -15V

  Values are indexes into channels[].
*/
constexpr uint8_t DISPLAY_ORDER[CHANNEL_COUNT] = {
  0, 2, 4,
  1, 3, 5
};

int32_t toDisplayedMilli(float value) {
  return static_cast<int32_t>(lroundf(value * 1000.0f));
}

uint32_t packIp(const IPAddress &ip) {
  return
    (static_cast<uint32_t>(ip[0]) << 24) |
    (static_cast<uint32_t>(ip[1]) << 16) |
    (static_cast<uint32_t>(ip[2]) << 8) |
    static_cast<uint32_t>(ip[3]);
}

uint8_t makeDisplayAlarmMask(const MonitorChannel &channel) {
  uint8_t mask = 0;

  if (channel.voltageLowAlarm) {
    mask |= 1U << 0;  // UVL
  }
  if (channel.voltageHighAlarm) {
    mask |= 1U << 1;  // OVL
  }
  if (channel.currentLowAlarm) {
    mask |= 1U << 2;  // UCL
  }
  if (channel.currentHighAlarm) {
    mask |= 1U << 3;  // OCL
  }
  if (!channel.sensorOnline) {
    mask |= 1U << 4;  // I2C
  }

  return mask;
}

ChannelDisplaySnapshot captureChannel(
  const MonitorChannel &channel
) {
  ChannelDisplaySnapshot snapshot;

  snapshot.initialized = true;

  snapshot.voltageMilli = toDisplayedMilli(channel.voltage);
  snapshot.currentMilli = toDisplayedMilli(channel.current);

  snapshot.voltageLowMilli =
    toDisplayedMilli(channel.limits.voltageLow);

  snapshot.voltageHighMilli =
    toDisplayedMilli(channel.limits.voltageHigh);

  snapshot.currentLowMilli =
    toDisplayedMilli(channel.limits.currentLow);

  snapshot.currentHighMilli =
    toDisplayedMilli(channel.limits.currentHigh);

  snapshot.alarmMask = makeDisplayAlarmMask(channel);
  snapshot.readingValid = channel.readingValid;
  snapshot.sensorOnline = channel.sensorOnline;
  snapshot.overallAlarm = channelIsInAlarm(channel);

  return snapshot;
}

HeaderDisplaySnapshot captureHeader() {
  HeaderDisplaySnapshot snapshot;

  snapshot.initialized = true;
  snapshot.hardwarePresent = ethernetHardwarePresent;

  if (!ethernetHardwarePresent) {
    snapshot.linkStatus = -1;
    snapshot.packedIp = 0;
    return snapshot;
  }

  snapshot.linkStatus =
    static_cast<int>(Ethernet.linkStatus());

  snapshot.packedIp = packIp(Ethernet.localIP());
  return snapshot;
}

bool headerChanged(
  const HeaderDisplaySnapshot &previous,
  const HeaderDisplaySnapshot &current
) {
  return
    !previous.initialized ||
    previous.hardwarePresent != current.hardwarePresent ||
    previous.linkStatus != current.linkStatus ||
    previous.packedIp != current.packedIp;
}

void cardPosition(
  uint8_t displaySlot,
  int &x,
  int &y
) {
  const uint8_t column = displaySlot % 3;
  const uint8_t row = displaySlot / 3;

  x = MARGIN_X + column * (CARD_WIDTH + GAP_X);
  y = HEADER_HEIGHT + row * (CARD_HEIGHT + GAP_Y);
}

uint16_t channelCardColor(const MonitorChannel &channel) {
  return channelIsInAlarm(channel)
    ? display.color565(72, 23, 29)
    : COLOR_CARD;
}

uint16_t channelStatusColor(const MonitorChannel &channel) {
  return channelIsInAlarm(channel)
    ? COLOR_ALARM
    : COLOR_OK;
}

void printAt(
  int x,
  int y,
  uint8_t size,
  uint16_t color,
  const char *text
) {
  display.setTextSize(size);
  display.setTextColor(color);
  display.setCursor(x, y);
  display.print(text);
}

void clearField(
  int x,
  int y,
  int width,
  int height,
  uint16_t background
) {
  display.fillRect(x, y, width, height, background);
}

void drawStaticLayout() {
  display.fillScreen(COLOR_BACKGROUND);
  display.fillRect(
    0,
    0,
    SCREEN_WIDTH,
    HEADER_HEIGHT,
    COLOR_HEADER
  );

  printAt(14, 9, 3, COLOR_WHITE, "MULTI-RAIL MONITOR");
}

void drawHeaderNetworkStatus() {
  display.fillRect(
    500,
    0,
    300,
    HEADER_HEIGHT,
    COLOR_HEADER
  );

  char line1[32];
  char line2[32];

  if (!ethernetHardwarePresent) {
    snprintf(line1, sizeof(line1), "ETHERNET: NO HW");
    snprintf(line2, sizeof(line2), "Check shield/SPI");

    printAt(510, 10, 2, COLOR_ALARM, line1);
    printAt(510, 35, 1, COLOR_MUTED, line2);
    return;
  }

  const EthernetLinkStatus link = Ethernet.linkStatus();

  if (link == LinkOFF) {
    snprintf(line1, sizeof(line1), "ETHERNET: LINK OFF");

    const IPAddress ip = Ethernet.localIP();

    snprintf(
      line2,
      sizeof(line2),
      "IP %u.%u.%u.%u",
      ip[0],
      ip[1],
      ip[2],
      ip[3]
    );

    printAt(510, 10, 2, COLOR_WARNING, line1);
    printAt(510, 35, 1, COLOR_MUTED, line2);
    return;
  }

  const IPAddress ip = Ethernet.localIP();

  snprintf(
    line1,
    sizeof(line1),
    "IP %u.%u.%u.%u",
    ip[0],
    ip[1],
    ip[2],
    ip[3]
  );

  snprintf(
    line2,
    sizeof(line2),
    "HTTP PORT# %u  EPICS PORT #%u",
    HTTP_PORT,
    PSC_PORT
  );

  printAt(510, 10, 2, COLOR_CYAN, line1);
  printAt(510, 35, 1, COLOR_MUTED, line2);
}

void drawChannelHeaderState(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  int x;
  int y;
  cardPosition(displaySlot, x, y);

  const MonitorChannel &channel = channels[channelIndex];
  const uint16_t background = channelCardColor(channel);
  const uint16_t statusColor = channelStatusColor(channel);

  const char *headerState =
    !channel.sensorOnline ? "I2C" :
    channelIsInAlarm(channel) ? "ALM" :
    "OK";

  clearField(
    x + 178,
    y + 6,
    66,
    25,
    background
  );

  printAt(
    x + 188,
    y + 9,
    2,
    statusColor,
    headerState
  );
}

void drawChannelVoltage(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  int x;
  int y;
  cardPosition(displaySlot, x, y);

  const MonitorChannel &channel = channels[channelIndex];
  const uint16_t background = channelCardColor(channel);

  char buffer[32];

  if (channel.readingValid) {
    snprintf(
      buffer,
      sizeof(buffer),
      "%7.3f V",
      channel.voltage
    );
  } else {
    snprintf(buffer, sizeof(buffer), "    --- V");
  }

  clearField(
    x + 8,
    y + 38,
    226,
    35,
    background
  );

  printAt(
    x + 10,
    y + 42,
    3,
    COLOR_CYAN,
    buffer
  );
}

void drawChannelCurrent(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  int x;
  int y;
  cardPosition(displaySlot, x, y);

  const MonitorChannel &channel = channels[channelIndex];
  const uint16_t background = channelCardColor(channel);

  char buffer[32];

  if (channel.readingValid) {
    snprintf(
      buffer,
      sizeof(buffer),
      "%7.3f mA",
      channel.current * 1000.0f
    );
  } else {
    snprintf(buffer, sizeof(buffer), "    --- A");
  }

  clearField(
    x + 8,
    y + 74,
    226,
    35,
    background
  );

  printAt(
    x + 10,
    y + 78,
    3,
    COLOR_WHITE,
    buffer
  );
}

void drawChannelLimits(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  int x;
  int y;
  cardPosition(displaySlot, x, y);

  const MonitorChannel &channel = channels[channelIndex];
  const uint16_t background = channelCardColor(channel);

  char buffer[32];

  clearField(
    x + 8,
    y + 114,
    236,
    80,
    background
  );

  snprintf(
    buffer,
    sizeof(buffer),
    "VL (V)%6.2f..%6.2f",
    channel.limits.voltageLow,
    channel.limits.voltageHigh
  );

  printAt(
    x + 10,
    y + 126,
    2,
    COLOR_MUTED,
    buffer
  );

  snprintf(
    buffer,
    sizeof(buffer),
    "IL (A)%6.2f..%6.2f",
    channel.limits.currentLow,
    channel.limits.currentHigh
  );

  printAt(
    x + 10,
    y + 158,
    2,
    COLOR_MUTED,
    buffer
  );
}

void drawCompleteChannelCard(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  int x;
  int y;
  cardPosition(displaySlot, x, y);

  const MonitorChannel &channel = channels[channelIndex];
  const bool alarm = channelIsInAlarm(channel);
  const uint16_t cardColor = channelCardColor(channel);

  display.fillRect(
    x,
    y,
    CARD_WIDTH,
    CARD_HEIGHT,
    cardColor
  );

  display.drawRect(
    x,
    y,
    CARD_WIDTH,
    CARD_HEIGHT,
    alarm ? COLOR_ALARM : COLOR_BORDER
  );

  printAt(
    x + 10,
    y + 9,
    2,
    COLOR_WHITE,
    channel.name
  );

  drawChannelHeaderState(channelIndex, displaySlot);
  drawChannelVoltage(channelIndex, displaySlot);
  drawChannelCurrent(channelIndex, displaySlot);
  drawChannelLimits(channelIndex, displaySlot);
}

void refreshChannelCard(
  uint8_t channelIndex,
  uint8_t displaySlot
) {
  const MonitorChannel &channel = channels[channelIndex];

  ChannelDisplaySnapshot &previous =
    channelDisplayCache[channelIndex];

  const ChannelDisplaySnapshot current =
    captureChannel(channel);

  if (
    !previous.initialized ||
    previous.overallAlarm != current.overallAlarm
  ) {
    drawCompleteChannelCard(
      channelIndex,
      displaySlot
    );

    previous = current;
    return;
  }

  if (
    previous.readingValid != current.readingValid ||
    previous.voltageMilli != current.voltageMilli
  ) {
    drawChannelVoltage(
      channelIndex,
      displaySlot
    );
  }

  if (
    previous.readingValid != current.readingValid ||
    previous.currentMilli != current.currentMilli
  ) {
    drawChannelCurrent(
      channelIndex,
      displaySlot
    );
  }

  if (
    previous.voltageLowMilli != current.voltageLowMilli ||
    previous.voltageHighMilli != current.voltageHighMilli ||
    previous.currentLowMilli != current.currentLowMilli ||
    previous.currentHighMilli != current.currentHighMilli
  ) {
    drawChannelLimits(
      channelIndex,
      displaySlot
    );
  }

  if (
    previous.sensorOnline != current.sensorOnline ||
    previous.alarmMask != current.alarmMask
  ) {
    drawChannelHeaderState(
      channelIndex,
      displaySlot
    );
  }

  previous = current;
}

}

void initializeColors() {
  COLOR_BLACK      = display.color565(0, 0, 0);
  COLOR_WHITE      = display.color565(255, 255, 255);
  COLOR_BACKGROUND = display.color565(12, 18, 25);
  COLOR_HEADER     = display.color565(24, 35, 48);
  COLOR_CARD       = display.color565(31, 43, 56);
  COLOR_BORDER     = display.color565(77, 96, 115);
  COLOR_OK         = display.color565(34, 177, 76);
  COLOR_ALARM      = display.color565(185, 36, 45);
  COLOR_WARNING    = display.color565(235, 170, 35);
  COLOR_CYAN       = display.color565(64, 196, 255);
  COLOR_MUTED      = display.color565(175, 190, 205);
}

void redrawDisplay() {
  const HeaderDisplaySnapshot currentHeader =
    captureHeader();

  if (
    headerChanged(
      headerDisplayCache,
      currentHeader
    )
  ) {
    drawHeaderNetworkStatus();
    headerDisplayCache = currentHeader;
  }

  for (
    uint8_t displaySlot = 0;
    displaySlot < CHANNEL_COUNT;
    ++displaySlot
  ) {
    refreshChannelCard(
      DISPLAY_ORDER[displaySlot],
      displaySlot
    );
  }
}

void initializeDisplay() {
  display.begin();
  display.setRotation(1);
  display.setTextWrap(false);

  initializeColors();
  drawStaticLayout();

  redrawDisplay();
}
