/*
  Клиентская прошивка ESP8266:
  - подключается к Wi-Fi точке сервера STEM_SK
  - принимает команды от Arduino по Serial:
      CARD=<HEX_UID>;ROUTE=<idx>
      REMOVE=<HEX_UID>
  - пересылает команды на сервер:
      /api/vote?card=<HEX_UID>&route=<idx>
      /api/remove?card=<HEX_UID>

  Тест:
  1) Запустите серверную прошивку и убедитесь, что точка STEM_SK поднята.
  2) Прошейте этот скетч, откройте Serial Monitor (115200) и дождитесь "Wi-Fi connected.".
  3) Отправьте строку: CARD=1234ABCD;ROUTE=1
     Ожидание: в Serial появится "HTTP 200 ... OK VOTE".
  4) Отправьте строку: CARD=1234ABCD;ROUTE=2
     Ожидание: заявка той же карты будет переназначена на маршрут 2.
  5) Отправьте строку: REMOVE=1234ABCD
     Ожидание: в Serial появится "HTTP 200 ... OK REMOVE".
*/

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

// Точка доступа, которую поднимает серверная прошивка.
static const char* WIFI_SSID = "STEM_SK";
static const char* WIFI_PASS = "passk123";

// Адрес server NodeMCU в режиме AP по умолчанию.
static const char* SERVER_HOST = "192.168.4.1";
static const uint16_t SERVER_PORT = 80;

static const uint8_t ROUTES_COUNT = 3;

String serialLine;
uint32_t lastReconnectTryMs = 0;

bool parseKeyValue(const String& line, const char* key, String& out) {
  int p = line.indexOf(key);
  if (p < 0) return false;
  p += strlen(key);

  int end = line.indexOf(';', p);
  if (end < 0) end = line.length();

  out = line.substring(p, end);
  out.trim();
  return out.length() > 0;
}

bool isHexString(const String& s) {
  if (s.length() == 0) return false;
  for (uint16_t i = 0; i < s.length(); i++) {
    char c = s[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
    if (!ok) return false;
  }
  return true;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.println();
  Serial.print("Connecting to server AP: ");
  Serial.println(WIFI_SSID);

  uint32_t startMs = millis();
  const uint32_t timeoutMs = 15000;
  while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < timeoutMs) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected.");
    Serial.print("Local IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection timeout.");
  }
}

void ensureWiFiConnected() {
  if (WiFi.status() == WL_CONNECTED) return;

  uint32_t now = millis();
  if (now - lastReconnectTryMs < 5000) return;
  lastReconnectTryMs = now;

  Serial.println("Wi-Fi disconnected, reconnecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

bool callServer(const String& pathAndQuery) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Skip send: Wi-Fi is not connected.");
    return false;
  }

  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + String(SERVER_PORT) + pathAndQuery;

  if (!http.begin(client, url)) {
    Serial.println("HTTP begin failed.");
    return false;
  }

  int code = http.GET();
  String body = http.getString();
  http.end();

  Serial.print("HTTP ");
  Serial.print(code);
  Serial.print(" for ");
  Serial.print(pathAndQuery);
  Serial.print(" -> ");
  Serial.println(body);

  return (code >= 200 && code < 300);
}

void sendVote(const String& uidHex, uint8_t route) {
  String path = "/api/vote?card=" + uidHex + "&route=" + String(route);
  callServer(path);
}

void sendRemove(const String& uidHex) {
  String path = "/api/remove?card=" + uidHex;
  callServer(path);
}

void processSerialLine(const String& rawLine) {
  String line = rawLine;
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("REMOVE=")) {
    String uidHex = line.substring(7);
    uidHex.trim();
    if (!isHexString(uidHex)) {
      Serial.println("Invalid REMOVE uid.");
      return;
    }
    sendRemove(uidHex);
    return;
  }

  line.replace(" ", ";");

  String uidHex;
  String routeStr;
  if (!parseKeyValue(line, "CARD=", uidHex)) {
    Serial.println("CARD key is missing.");
    return;
  }
  if (!parseKeyValue(line, "ROUTE=", routeStr)) {
    Serial.println("ROUTE key is missing.");
    return;
  }
  if (!isHexString(uidHex)) {
    Serial.println("Invalid CARD uid.");
    return;
  }

  int route = routeStr.toInt();
  if (route < 0 || route >= ROUTES_COUNT) {
    Serial.println("Invalid route index.");
    return;
  }

  sendVote(uidHex, (uint8_t)route);
}

void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();

    if (c == '\n') {
      serialLine.trim();
      if (serialLine.length() > 0) processSerialLine(serialLine);
      serialLine = "";
      continue;
    }

    if (c == '\r') continue;

    if (serialLine.length() < 120) {
      serialLine += c;
    } else {
      serialLine = "";
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);

  connectWiFi();
  Serial.println("ESP client started.");
}

void loop() {
  ensureWiFiConnected();
  pollSerial();
  delay(2);
}
