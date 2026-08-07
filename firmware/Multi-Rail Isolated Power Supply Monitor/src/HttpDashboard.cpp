#include "HttpDashboard.h"

#include <Arduino.h>
#include <Ethernet.h>

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "AppConfig.h"
#include "AppState.h"
#include "PersistentStorage.h"
#include "PscProtocol.h"

namespace {
EthernetServer httpServer(HTTP_PORT);
}

void initializeHttpServer() {
  httpServer.begin();
}

String readHttpLine(EthernetClient &client, uint32_t timeoutMs, size_t maxLength) {
  String line;
  line.reserve(maxLength);

  const uint32_t start = millis();

  while (client.connected() && (millis() - start < timeoutMs)) {
    while (client.available()) {
      const char c = static_cast<char>(client.read());

      if (c == '\n') {
        return line;
      }

      if (c != '\r' && line.length() < maxLength) {
        line += c;
      }
    }
  }

  return line;
}

void discardHttpHeaders(EthernetClient &client) {
  for (uint8_t i = 0; i < 30; ++i) {
    String line = readHttpLine(client, 300, 255);

    if (line.length() == 0) {
      break;
    }
  }
}

void sendHttpHeader(
  EthernetClient &client,
  const char *status,
  const char *contentType
) {
  client.print(F("HTTP/1.1 "));
  client.println(status);
  client.print(F("Content-Type: "));
  client.println(contentType);
  client.println(F("Cache-Control: no-store"));
  client.println(F("Access-Control-Allow-Origin: *"));
  client.println(F("Connection: close"));
  client.println();
}

void sendRedirectToDashboard(EthernetClient &client) {
  client.println(F("HTTP/1.1 303 See Other"));
  client.println(F("Location: /"));
  client.println(F("Cache-Control: no-store"));
  client.println(F("Connection: close"));
  client.println();
}

void sendBadRequest(EthernetClient &client, const char *message) {
  sendHttpHeader(client, "400 Bad Request", "text/plain; charset=utf-8");
  client.println(message);
}

void sendNotFound(EthernetClient &client) {
  sendHttpHeader(client, "404 Not Found", "text/plain; charset=utf-8");
  client.println(F("Not found"));
}

bool getQueryParameter(
  const String &target,
  const char *key,
  String &value
) {
  const int questionMark = target.indexOf('?');

  if (questionMark < 0) {
    return false;
  }

  int start = questionMark + 1;

  while (start < static_cast<int>(target.length())) {
    int end = target.indexOf('&', start);

    if (end < 0) {
      end = target.length();
    }

    const String pair = target.substring(start, end);
    const int equals = pair.indexOf('=');

    if (equals > 0 && pair.substring(0, equals) == key) {
      value = pair.substring(equals + 1);
      return true;
    }

    start = end + 1;
  }

  return false;
}

bool parseStrictFloat(const String &text, float &value) {
  if (text.length() == 0) {
    return false;
  }

  char *endPointer = nullptr;
  value = strtof(text.c_str(), &endPointer);

  return endPointer != text.c_str() &&
         *endPointer == '\0' &&
         isfinite(value);
}

bool parseStrictInt(const String &text, int &value) {
  if (text.length() == 0) {
    return false;
  }

  char *endPointer = nullptr;
  const long parsed = strtol(text.c_str(), &endPointer, 10);

  if (endPointer == text.c_str() || *endPointer != '\0') {
    return false;
  }

  value = static_cast<int>(parsed);
  return true;
}

bool parseIpv4Address(
  const String &text,
  uint8_t address[4]
) {
  int values[4];
  char trailingCharacter = '\0';

  const int fields = sscanf(
    text.c_str(),
    "%d.%d.%d.%d%c",
    &values[0],
    &values[1],
    &values[2],
    &values[3],
    &trailingCharacter
  );

  if (fields != 4) {
    return false;
  }

  for (uint8_t i = 0; i < 4; ++i) {
    if (values[i] < 0 || values[i] > 255) {
      return false;
    }

    address[i] = static_cast<uint8_t>(values[i]);
  }

  return true;
}

void formatIpv4Address(
  const uint8_t address[4],
  char *buffer,
  size_t bufferSize
) {
  snprintf(
    buffer,
    bufferSize,
    "%u.%u.%u.%u",
    address[0],
    address[1],
    address[2],
    address[3]
  );
}

bool updateNetworkFromRequest(
  const String &target,
  char *errorMessage,
  size_t errorMessageSize
) {
  String ipText;
  String dnsText;
  String gatewayText;
  String subnetText;

  if (!getQueryParameter(target, "ip", ipText) ||
      !getQueryParameter(target, "dns", dnsText) ||
      !getQueryParameter(target, "gateway", gatewayText) ||
      !getQueryParameter(target, "subnet", subnetText)) {
    snprintf(
      errorMessage,
      errorMessageSize,
      "Required parameters: ip, dns, gateway, subnet"
    );
    return false;
  }

  NetworkSettings requestedSettings;

  if (!parseIpv4Address(ipText, requestedSettings.ip) ||
      !parseIpv4Address(dnsText, requestedSettings.dns) ||
      !parseIpv4Address(gatewayText, requestedSettings.gateway) ||
      !parseIpv4Address(subnetText, requestedSettings.subnet)) {
    snprintf(
      errorMessage,
      errorMessageSize,
      "Enter each address in dotted-decimal form"
    );
    return false;
  }

  if (!hostAddressIsValid(requestedSettings.ip)) {
    snprintf(errorMessage, errorMessageSize, "Invalid device IP address");
    return false;
  }

  if (!optionalHostAddressIsValid(requestedSettings.dns)) {
    snprintf(errorMessage, errorMessageSize, "Invalid DNS address");
    return false;
  }

  if (!optionalHostAddressIsValid(requestedSettings.gateway)) {
    snprintf(errorMessage, errorMessageSize, "Invalid gateway address");
    return false;
  }

  if (!subnetMaskIsValid(requestedSettings.subnet)) {
    snprintf(errorMessage, errorMessageSize, "Invalid subnet mask");
    return false;
  }

  const NetworkSettings previousSettings = networkSettings;
  networkSettings = requestedSettings;

  if (!savePersistentSettings()) {
    networkSettings = previousSettings;

    snprintf(
      errorMessage,
      errorMessageSize,
      "Persistent storage write failed; network was not changed"
    );
    return false;
  }

  networkRestartRequired = true;
  return true;
}

bool updateLimitsFromRequest(
  const String &target,
  char *errorMessage,
  size_t errorMessageSize
) {
  String channelText;
  String voltageLowText;
  String voltageHighText;
  String currentLowText;
  String currentHighText;

  if (!getQueryParameter(target, "ch", channelText) ||
      !getQueryParameter(target, "vlow", voltageLowText) ||
      !getQueryParameter(target, "vhigh", voltageHighText) ||
      !getQueryParameter(target, "ilow", currentLowText) ||
      !getQueryParameter(target, "ihigh", currentHighText)) {
    snprintf(
      errorMessage,
      errorMessageSize,
      "Required parameters: ch, vlow, vhigh, ilow, ihigh"
    );
    return false;
  }

  int channelNumber = 0;
  float voltageLow = 0.0f;
  float voltageHigh = 0.0f;
  float currentLow = 0.0f;
  float currentHigh = 0.0f;

  if (!parseStrictInt(channelText, channelNumber) ||
      !parseStrictFloat(voltageLowText, voltageLow) ||
      !parseStrictFloat(voltageHighText, voltageHigh) ||
      !parseStrictFloat(currentLowText, currentLow) ||
      !parseStrictFloat(currentHighText, currentHigh)) {
    snprintf(errorMessage, errorMessageSize, "One or more values are invalid");
    return false;
  }

  if (channelNumber < 1 || channelNumber > CHANNEL_COUNT) {
    snprintf(errorMessage, errorMessageSize, "Channel must be 1 through 6");
    return false;
  }

  if (!(voltageLow < voltageHigh)) {
    snprintf(errorMessage, errorMessageSize, "vlow must be less than vhigh");
    return false;
  }

  if (!(currentLow < currentHigh)) {
    snprintf(errorMessage, errorMessageSize, "ilow must be less than ihigh");
    return false;
  }

  MonitorChannel &channel = channels[channelNumber - 1];
  const AlarmLimits previousLimits = channel.limits;

  channel.limits.voltageLow = voltageLow;
  channel.limits.voltageHigh = voltageHigh;
  channel.limits.currentLow = currentLow;
  channel.limits.currentHigh = currentHigh;

  updateAlarmState(channel);

  if (!savePersistentSettings()) {
    channel.limits = previousLimits;
    updateAlarmState(channel);

    snprintf(
      errorMessage,
      errorMessageSize,
      "Persistent storage write failed; limits were not changed"
    );
    return false;
  }

  sendPscLimits();
  sendPscAlarms();
  sendPscChannelSetpointEchoes(channelNumber - 1);
  return true;
}

void sendStatusJson(EthernetClient &client) {
  sendHttpHeader(client, "200 OK", "application/json; charset=utf-8");

  client.print(F("{\"channels\":["));

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    const MonitorChannel &channel = channels[i];

    if (i > 0) {
      client.print(',');
    }

    client.print(F("{\"channel\":"));
    client.print(i + 1);
    client.print(F(",\"name\":\""));
    client.print(channel.name);
    client.print(F("\",\"voltage\":"));
    if (channel.readingValid) {
      client.print(channel.voltage, 4);
    } else {
      client.print(F("null"));
    }

    client.print(F(",\"current\":"));
    if (channel.readingValid) {
      client.print(channel.current, 4);
    } else {
      client.print(F("null"));
    }

    client.print(F(",\"sensor\":{\"online\":"));
    client.print(channel.sensorOnline ? F("true") : F("false"));
    client.print(F(",\"i2c_error\":"));
    client.print(channel.sensorError);
    client.print(F(",\"last_valid_ms\":"));
    client.print(channel.lastValidReadingMs);
    client.print(F("},\"limits\":{\"vlow\":"));
    client.print(channel.limits.voltageLow, 4);
    client.print(F(",\"vhigh\":"));
    client.print(channel.limits.voltageHigh, 4);
    client.print(F(",\"ilow\":"));
    client.print(channel.limits.currentLow, 4);
    client.print(F(",\"ihigh\":"));
    client.print(channel.limits.currentHigh, 4);
    client.print(F("},\"alarms\":{\"undervoltage\":"));
    client.print(channel.voltageLowAlarm ? F("true") : F("false"));
    client.print(F(",\"overvoltage\":"));
    client.print(channel.voltageHighAlarm ? F("true") : F("false"));
    client.print(F(",\"undercurrent\":"));
    client.print(channel.currentLowAlarm ? F("true") : F("false"));
    client.print(F(",\"overcurrent\":"));
    client.print(channel.currentHighAlarm ? F("true") : F("false"));
    client.print(F(",\"sensor_comm\":"));
    client.print(!channel.sensorOnline ? F("true") : F("false"));
    client.print(F(",\"any\":"));
    client.print(channelIsInAlarm(channel) ? F("true") : F("false"));
    client.print(F("}}"));
  }

  IPAddress ip = Ethernet.localIP();

  client.print(F("],\"device_ip\":\""));
  client.print(ip);
  char configuredIp[20];
  char configuredDns[20];
  char configuredGateway[20];
  char configuredSubnet[20];

  formatIpv4Address(
    networkSettings.ip,
    configuredIp,
    sizeof(configuredIp)
  );
  formatIpv4Address(
    networkSettings.dns,
    configuredDns,
    sizeof(configuredDns)
  );
  formatIpv4Address(
    networkSettings.gateway,
    configuredGateway,
    sizeof(configuredGateway)
  );
  formatIpv4Address(
    networkSettings.subnet,
    configuredSubnet,
    sizeof(configuredSubnet)
  );

  client.print(F("\",\"network_config\":{\"ip\":\""));
  client.print(configuredIp);
  client.print(F("\",\"dns\":\""));
  client.print(configuredDns);
  client.print(F("\",\"gateway\":\""));
  client.print(configuredGateway);
  client.print(F("\",\"subnet\":\""));
  client.print(configuredSubnet);
  client.print(F("\",\"restart_required\":"));
  client.print(networkRestartRequired ? F("true") : F("false"));
  client.print(F("},\"psc_connected\":"));
  client.print(pscIsConnected() ? F("true") : F("false"));
  client.print(F(",\"psc_port\":"));
  client.print(PSC_PORT);
  client.print(F(",\"settings_persistent\":"));
  client.print(settingsStorageReady ? F("true") : F("false"));
  client.print(F(",\"uptime_ms\":"));
  client.print(millis());
  client.println(F("}"));
}

void sendEpicsCsv(EthernetClient &client) {
  sendHttpHeader(client, "200 OK", "text/plain; charset=utf-8");

  // channel,voltage,current,vlow,vhigh,ilow,ihigh,alarm
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    const MonitorChannel &channel = channels[i];

    client.print(i + 1);
    client.print(',');
    if (channel.readingValid) {
      client.print(channel.voltage, 4);
    } else {
      client.print(F("nan"));
    }
    client.print(',');
    if (channel.readingValid) {
      client.print(channel.current, 4);
    } else {
      client.print(F("nan"));
    }
    client.print(',');
    client.print(channel.limits.voltageLow, 4);
    client.print(',');
    client.print(channel.limits.voltageHigh, 4);
    client.print(',');
    client.print(channel.limits.currentLow, 4);
    client.print(',');
    client.print(channel.limits.currentHigh, 4);
    client.print(',');
    client.println(channelIsInAlarm(channel) ? 1 : 0);
  }
}

void printHtmlFloatInput(
  EthernetClient &client,
  const char *formId,
  const char *name,
  float value
) {
  client.print(F("<input type='number' step='0.001' form='"));
  client.print(formId);
  client.print(F("' name='"));
  client.print(name);
  client.print(F("' value='"));
  client.print(value, 3);
  client.print(F("' required>"));
}

void printHtmlIpInput(
  EthernetClient &client,
  const char *name,
  const uint8_t address[4]
) {
  char addressText[20];
  formatIpv4Address(address, addressText, sizeof(addressText));

  client.print(F("<input class='ipinput' type='text' name='"));
  client.print(name);
  client.print(F("' value='"));
  client.print(addressText);
  client.print(
    F("' inputmode='decimal' pattern='[0-9]{1,3}(\\.[0-9]{1,3}){3}' required>")
  );
}

void sendNetworkSavedPage(EthernetClient &client) {
  char newIp[20];
  formatIpv4Address(networkSettings.ip, newIp, sizeof(newIp));

  sendHttpHeader(client, "200 OK", "text/html; charset=utf-8");

  client.println(F(
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Network settings saved</title>"
    "<style>"
    "body{font-family:Arial,sans-serif;background:#101820;color:#eef4f8;margin:32px}"
    "a{color:#67c7ff}code{background:#243342;padding:4px 6px}"
    "</style></head><body>"
    "<h1>Network settings saved</h1>"
    "<p>The GIGA is still using its old address for this session.</p>"
    "<p>Reset or power-cycle the board, then open:</p><p><code>http://"
  ));
  client.print(newIp);
  client.println(F(
    "/</code></p>"
    "<p>Use the reset button or cycle power after this page finishes loading.</p>"
    "<p><a href='/'>Return to the current dashboard</a></p>"
    "</body></html>"
  ));
}

void sendDashboard(EthernetClient &client) {
  sendHttpHeader(client, "200 OK", "text/html; charset=utf-8");

  client.println(F(
    "<!doctype html><html><head>"
    "<meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>GIGA Multi-Rail Monitor</title>"
    "<style>"
    "body{font-family:Arial,sans-serif;background:#101820;color:#eef4f8;margin:24px}"
    "h1{margin-bottom:4px}"
    "a{color:#67c7ff}"
    "table{border-collapse:collapse;width:100%;max-width:1200px;background:#1e2b38}"
    "th,td{border:1px solid #526579;padding:8px;text-align:center}"
    "th{background:#26394b}"
    "tr.alarm{background:#551f26}"
    "tr.ok{background:#20372d}"
    "input{width:80px;padding:5px;background:#f7fafc;border:1px solid #9aabba}""input.ipinput{width:132px}"".network{max-width:900px;background:#1e2b38;border:1px solid #526579;padding:16px;margin:18px 0}"".network label{display:inline-block;margin:6px 12px 6px 0}"
    "button{padding:7px 12px;font-weight:bold}"
    "code{background:#243342;padding:3px 5px}"
    ".small{color:#b5c5d4;font-size:.9rem}"
    "</style></head><body>"
  ));

  client.println(F("<h1>Arduino GIGA Multi-Rail Monitor</h1>"));
  client.print(F("<p class='small'>Live LTC2945 measurements. Alarm limits are "));
  client.print(
    settingsStorageReady
      ? F("saved in internal QSPI flash.")
      : F("not persistent because storage is unavailable.")
  );
  client.println(F("</p>"));
  client.println(F("<p><a href='/api/status'>JSON status</a> | <a href='/epics'>EPICS CSV</a> | <a href='/'>Refresh</a></p>"));
  client.print(F("<p class='small'>PSCDriver endpoint: <code>"));
  client.print(Ethernet.localIP());
  client.print(F(":"));
  client.print(PSC_PORT);
  client.print(F("</code> &mdash; "));
  client.print(pscIsConnected() ? F("IOC connected") : F("waiting for IOC"));
  client.println(F("</p>"));

  client.println(F(
    "<div class='network'><h2>Network settings</h2>"
    "<p class='small'>Changes are stored immediately and applied after reset.</p>"
    "<form method='get' action='/api/network'>"
  ));

  client.print(F("<label>IP address<br>"));
  printHtmlIpInput(client, "ip", networkSettings.ip);
  client.println(F("</label>"));

  client.print(F("<label>Gateway<br>"));
  printHtmlIpInput(client, "gateway", networkSettings.gateway);
  client.println(F("</label>"));

  client.print(F("<label>Subnet mask<br>"));
  printHtmlIpInput(client, "subnet", networkSettings.subnet);
  client.println(F("</label>"));

  client.print(F("<label>DNS server<br>"));
  printHtmlIpInput(client, "dns", networkSettings.dns);
  client.println(F("</label>"));

  client.println(F(
    "<br><button type='submit'>Save network settings</button>"
    "</form>"
  ));

  if (networkRestartRequired) {
    client.println(F(
      "<p><strong>Reset required:</strong> saved network settings differ "
      "from the address currently in use.</p>"
    ));
  }

  client.println(F(
    "<p class='small'>A wrong but valid address can make this page unreachable. "
    "Recovery: set <code>FORCE_COMPILED_NETWORK_ON_BOOT</code> to "
    "<code>true</code> and upload over USB.</p></div>"
  ));

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    client.print(F("<form id='limitForm"));
    client.print(i + 1);
    client.println(F("' method='get' action='/api/limits'></form>"));
  }

  client.println(F(
    "<table><thead><tr>"
    "<th>Channel</th><th>Voltage</th><th>Current</th><th>State</th>"
    "<th>V low</th><th>V high</th><th>I low</th><th>I high</th><th>Apply</th>"
    "</tr></thead><tbody>"
  ));

  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    const MonitorChannel &channel = channels[i];
    char formId[20];
    snprintf(formId, sizeof(formId), "limitForm%u", i + 1);

    client.print(F("<tr class='"));
    client.print(channelIsInAlarm(channel) ? F("alarm") : F("ok"));
    client.print(F("'>"));

    client.print(F("<td><strong>"));
    client.print(channel.name);
    client.print(F("</strong><input type='hidden' form='"));
    client.print(formId);
    client.print(F("' name='ch' value='"));
    client.print(i + 1);
    client.println(F("'></td>"));

    client.print(F("<td>"));
    if (channel.readingValid) {
      client.print(channel.voltage, 3);
      client.print(F(" V"));
    } else {
      client.print(F("---"));
    }
    client.println(F("</td>"));

    client.print(F("<td>"));
    if (channel.readingValid) {
      client.print(channel.current, 3);
      client.print(F(" A"));
    } else {
      client.print(F("---"));
    }
    client.println(F("</td>"));

    client.print(F("<td>"));
    if (!channel.sensorOnline) {
      client.print(F("I2C ERROR 0x"));
      client.print(channel.sensorError, HEX);
    } else {
      client.print(channelIsInAlarm(channel) ? F("ALARM") : F("OK"));
    }
    client.println(F("</td>"));

    client.print(F("<td>"));
    printHtmlFloatInput(client, formId, "vlow", channel.limits.voltageLow);
    client.println(F("</td>"));

    client.print(F("<td>"));
    printHtmlFloatInput(client, formId, "vhigh", channel.limits.voltageHigh);
    client.println(F("</td>"));

    client.print(F("<td>"));
    printHtmlFloatInput(client, formId, "ilow", channel.limits.currentLow);
    client.println(F("</td>"));

    client.print(F("<td>"));
    printHtmlFloatInput(client, formId, "ihigh", channel.limits.currentHigh);
    client.println(F("</td>"));

    client.print(F("<td><button type='submit' form='"));
    client.print(formId);
    client.println(F("'>Set</button></td>"));
    client.println(F("</tr>"));
  }

  client.println(F("</tbody></table>"));
  client.println(F(
    "<p class='small'>Direct update example:<br>"
    "<code>/api/limits?ch=1&amp;vlow=3.00&amp;vhigh=3.60&amp;ilow=0.00&amp;ihigh=1.00</code>"
    "</p>"
  ));
  client.println(F("</body></html>"));
}

void handleHttpRequest(EthernetClient &client, const String &requestLine) {
  const int firstSpace = requestLine.indexOf(' ');
  const int secondSpace = requestLine.indexOf(' ', firstSpace + 1);

  if (firstSpace < 0 || secondSpace < 0) {
    sendBadRequest(client, "Malformed HTTP request line");
    return;
  }

  const String method = requestLine.substring(0, firstSpace);
  const String target = requestLine.substring(firstSpace + 1, secondSpace);

  if (method != "GET") {
    sendHttpHeader(client, "405 Method Not Allowed", "text/plain; charset=utf-8");
    client.println(F("Only GET is supported"));
    return;
  }

  if (target == "/" || target.startsWith("/?")) {
    sendDashboard(client);
    return;
  }

  if (target == "/api/status") {
    sendStatusJson(client);
    return;
  }

  if (target == "/epics") {
    sendEpicsCsv(client);
    return;
  }

  if (target.startsWith("/api/network?")) {
    char errorMessage[128];

    if (!updateNetworkFromRequest(
          target,
          errorMessage,
          sizeof(errorMessage)
        )) {
      sendBadRequest(client, errorMessage);
      return;
    }

    sendNetworkSavedPage(client);
    return;
  }

  if (target.startsWith("/api/limits?")) {
    char errorMessage[96];

    if (!updateLimitsFromRequest(target, errorMessage, sizeof(errorMessage))) {
      sendBadRequest(client, errorMessage);
      return;
    }

    sendRedirectToDashboard(client);
    return;
  }

  sendNotFound(client);
}

void serviceHttp() {
  if (!ethernetHardwarePresent) {
    return;
  }

  EthernetClient client = httpServer.available();

  if (!client) {
    return;
  }

  const String requestLine = readHttpLine(client, 500, 300);
  discardHttpHeaders(client);

  if (requestLine.length() > 0) {
    Serial.println(requestLine);
    handleHttpRequest(client, requestLine);
  }

  delay(1);
  client.stop();
}
