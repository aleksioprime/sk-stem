/*
  Серверная прошивка ESP8266 (NodeMCU):
  - поднимает Wi-Fi точку доступа
  - принимает заявки на маршруты по HTTP API
  - хранит и редактирует заявки (уникально по UID)
  - отдаёт веб-страницу мониторинга и управления

  Тест:
  1) Прошейте скетч, откройте Serial Monitor (115200) и проверьте "AP start: OK" и "AP IP: 192.168.4.1".
  2) Подключитесь к Wi-Fi "STEM_SK" (пароль: passk123).
  3) Откройте в браузере http://192.168.4.1/ и убедитесь, что страница мониторинга загружается.
  4) Проверьте API заявки:
     http://192.168.4.1/api/vote?card=1234ABCD&route=1
     Ожидание: ответ "OK VOTE", а на /data маршрут 1 увеличится.
  5) Проверьте изменение маршрута той же карты:
     http://192.168.4.1/api/vote?card=1234ABCD&route=2
     Ожидание: счётчик маршрута 1 уменьшится, маршрута 2 увеличится.
  6) Проверьте удаление:
     http://192.168.4.1/api/remove?card=1234ABCD
     Ожидание: ответ "OK REMOVE", карта исчезнет из подсчёта.
  7) Проверьте сброс:
     http://192.168.4.1/reset            (сброс всех)
     http://192.168.4.1/reset?route=1    (сброс только маршрута 1)
*/

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// Параметры точки доступа (режим по умолчанию).
static const char* AP_SSID = "STEM_SK";
static const char* AP_PASS = "passk123";

// Параметры режима клиента (вариант подключения к внешней сети).
// static const char* WIFI_SSID = "ALTEST";
// static const char* WIFI_PASS = "passtest";

ESP8266WebServer server(80);

static const uint8_t ROUTES_COUNT = 3;
const char* ROUTE_NAMES[ROUTES_COUNT] = {
  "GREEN",
  "BLUE",
  "YELLOW",
};

static const uint16_t MAX_CARDS = 200;

struct CardRecord {
  uint32_t hash;
  uint8_t uidLen;
  uint8_t route;
  bool used;
};

CardRecord cards[MAX_CARDS];
uint16_t routeCounts[ROUTES_COUNT] = { 0, 0, 0 };

const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>STEM Route Server</title>
  <style>
    body { font-family: system-ui, sans-serif; padding: 18px; background: #fafafa; }
    .card { max-width: 760px; margin: 0 auto; border: 1px solid #ddd; border-radius: 16px; padding: 16px; background: #fff; }
    h1 { margin: 0 0 10px; font-size: 20px; }
    .status { font-size: 12px; opacity: .75; margin-bottom: 10px; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; justify-content: space-between; gap: 8px; border-top: 1px solid #eee; padding: 10px 0; }
    li:first-child { border-top: none; }
    .count { font-weight: 700; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    button, select { border: 1px solid #ccc; border-radius: 10px; padding: 10px 12px; background: #f8f8f8; }
    button { cursor: pointer; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Мониторинг маршрутов</h1>
    <div id="status" class="status">Подключение...</div>
    <ul id="list"></ul>
    <div class="row">
      <button id="resetAllBtn">Сбросить все</button>
      <select id="routeSel"></select>
      <button id="resetRouteBtn">Сбросить маршрут</button>
    </div>
  </div>
<script>
async function loadData() {
  try {
    const r = await fetch('/data', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();

    const ul = document.getElementById('list');
    ul.innerHTML = '';
    for (const item of data.routes) {
      const li = document.createElement('li');
      li.innerHTML = '<span>Маршрут ' + item.name + '</span><span class="count">' + item.count + '</span>';
      ul.appendChild(li);
    }

    const sel = document.getElementById('routeSel');
    if (sel.options.length === 0) {
      for (const item of data.routes) {
        const opt = document.createElement('option');
        opt.value = item.index;
        opt.textContent = item.name;
        sel.appendChild(opt);
      }
    }

    document.getElementById('status').textContent =
      'Обновлено: ' + new Date().toLocaleTimeString() + ' | Всего заявок: ' + data.total;
  } catch (e) {
    document.getElementById('status').textContent = 'Ошибка: ' + e.message;
  }
}

document.getElementById('resetAllBtn').onclick = async () => {
  await fetch('/reset', { cache: 'no-store' });
  loadData();
};

document.getElementById('resetRouteBtn').onclick = async () => {
  const route = document.getElementById('routeSel').value;
  await fetch('/reset?route=' + encodeURIComponent(route), { cache: 'no-store' });
  loadData();
};

setInterval(loadData, 400);
loadData();
</script>
</body>
</html>
)HTML";

uint32_t fnv1a(const char* s, uint8_t len) {
  uint32_t h = 2166136261u;
  for (uint8_t i = 0; i < len; i++) {
    h ^= (uint8_t)s[i];
    h *= 16777619u;
  }
  return h;
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

int findCard(uint32_t hash, uint8_t uidLen) {
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].hash == hash && cards[i].uidLen == uidLen) return (int)i;
  }
  return -1;
}

int findFreeSlot() {
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (!cards[i].used) return (int)i;
  }
  return -1;
}

uint16_t totalCards() {
  uint16_t total = 0;
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used) total++;
  }
  return total;
}

void applyVote(uint32_t hash, uint8_t uidLen, uint8_t route) {
  int pos = findCard(hash, uidLen);

  if (pos >= 0) {
    uint8_t oldRoute = cards[pos].route;
    if (oldRoute == route) return;

    if (oldRoute < ROUTES_COUNT && routeCounts[oldRoute] > 0) routeCounts[oldRoute]--;
    cards[pos].route = route;
    routeCounts[route]++;
    return;
  }

  int freePos = findFreeSlot();
  if (freePos < 0) return;

  cards[freePos].used = true;
  cards[freePos].hash = hash;
  cards[freePos].uidLen = uidLen;
  cards[freePos].route = route;
  routeCounts[route]++;
}

bool removeVote(uint32_t hash, uint8_t uidLen) {
  int pos = findCard(hash, uidLen);
  if (pos < 0) return false;

  uint8_t route = cards[pos].route;
  if (route < ROUTES_COUNT && routeCounts[route] > 0) routeCounts[route]--;
  cards[pos].used = false;
  return true;
}

void resetAll() {
  for (uint16_t i = 0; i < MAX_CARDS; i++) cards[i].used = false;
  for (uint8_t r = 0; r < ROUTES_COUNT; r++) routeCounts[r] = 0;
}

void resetRoute(uint8_t route) {
  if (route >= ROUTES_COUNT) return;

  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].route == route) cards[i].used = false;
  }

  for (uint8_t r = 0; r < ROUTES_COUNT; r++) routeCounts[r] = 0;
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].route < ROUTES_COUNT) routeCounts[cards[i].route]++;
  }
}

void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

void handleData() {
  String json;
  json.reserve(512);
  json += "{\"routes\":[";
  for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
    if (i > 0) json += ",";
    json += "{\"index\":";
    json += String(i);
    json += ",\"name\":\"";
    json += ROUTE_NAMES[i];
    json += "\",\"count\":";
    json += String(routeCounts[i]);
    json += "}";
  }
  json += "],\"total\":";
  json += String(totalCards());
  json += "}";
  server.send(200, "application/json; charset=utf-8", json);
}

void handleVote() {
  if (!server.hasArg("card") || !server.hasArg("route")) {
    server.send(400, "text/plain; charset=utf-8", "Missing card/route");
    return;
  }

  String uidHex = server.arg("card");
  uidHex.trim();
  if (!isHexString(uidHex)) {
    server.send(400, "text/plain; charset=utf-8", "Bad card");
    return;
  }

  int route = server.arg("route").toInt();
  if (route < 0 || route >= ROUTES_COUNT) {
    server.send(400, "text/plain; charset=utf-8", "Bad route");
    return;
  }

  uint8_t uidLen = (uidHex.length() > 250) ? 250 : (uint8_t)uidHex.length();
  uint32_t hash = fnv1a(uidHex.c_str(), uidLen);
  applyVote(hash, uidLen, (uint8_t)route);

  server.send(200, "text/plain; charset=utf-8", "OK VOTE");
}

void handleRemove() {
  if (!server.hasArg("card")) {
    server.send(400, "text/plain; charset=utf-8", "Missing card");
    return;
  }

  String uidHex = server.arg("card");
  uidHex.trim();
  if (!isHexString(uidHex)) {
    server.send(400, "text/plain; charset=utf-8", "Bad card");
    return;
  }

  uint8_t uidLen = (uidHex.length() > 250) ? 250 : (uint8_t)uidHex.length();
  uint32_t hash = fnv1a(uidHex.c_str(), uidLen);
  removeVote(hash, uidLen);

  server.send(200, "text/plain; charset=utf-8", "OK REMOVE");
}

void handleReset() {
  if (server.hasArg("route")) {
    int route = server.arg("route").toInt();
    if (route < 0 || route >= ROUTES_COUNT) {
      server.send(400, "text/plain; charset=utf-8", "Bad route");
      return;
    }
    resetRoute((uint8_t)route);
    server.send(200, "text/plain; charset=utf-8", "OK ROUTE RESET");
    return;
  }

  resetAll();
  server.send(200, "text/plain; charset=utf-8", "OK ALL RESET");
}

void handleNotFound() {
  server.send(404, "text/plain; charset=utf-8", "Not found");
}

void startAccessPoint() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  bool ok = WiFi.softAP(AP_SSID, AP_PASS);
  Serial.print("AP start: ");
  Serial.println(ok ? "OK" : "FAIL");
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
}

// void connectWiFiStation() {
//   WiFi.persistent(false);
//   WiFi.mode(WIFI_STA);
//   WiFi.begin(WIFI_SSID, WIFI_PASS);
//   Serial.print("Connecting to Wi-Fi: ");
//   Serial.println(WIFI_SSID);
//   while (WiFi.status() != WL_CONNECTED) {
//     delay(300);
//     Serial.print(".");
//   }
//   Serial.println();
//   Serial.print("Station IP: ");
//   Serial.println(WiFi.localIP());
// }

void setup() {
  Serial.begin(115200);
  delay(100);

  resetAll();

  // Режим по умолчанию: отдельный сервер с собственной точкой доступа.
  startAccessPoint();

  // Если нужен режим клиента внешней сети, включите функцию ниже.
  // connectWiFiStation();

  server.on("/", HTTP_GET, handleRoot);
  server.on("/data", HTTP_GET, handleData);
  server.on("/api/vote", HTTP_GET, handleVote);
  server.on("/api/remove", HTTP_GET, handleRemove);
  server.on("/reset", HTTP_GET, handleReset);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started.");
}

void loop() {
  server.handleClient();
}
