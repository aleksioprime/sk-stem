/*
  Проект для ESP8266 (Wi-Fi Troyka Module):

  Алгоритм работы
  - ESP8266 подключается к существующей точке доступа (Wi-Fi роутеру) и поднимает веб-сервер в вашей сети.
  - Arduino присылает заявки по Serial (UART), которая содержит UID карты и выбранный маршрут.
  - ESP сохраняет заявки в память (уникально по UID карты) и считает, сколько уникальных карт выбрало каждый маршрут.
  - На веб-странице показываются маршруты и количество уникальных карт, которые их выбрали.

  Тест:
  - Для добавления заявки отправляем в Serial:
    - CARD=1234ABCD;ROUTE=1
    - CARD=4321ABCD;ROUTE=2
  - Для удаления заявки отправляем в Serial: REMOVE=1234ABCD
*/

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// WIFI параметры вашей сети
static const char* WIFI_SSID = "ALTEST";
static const char* WIFI_PASS = "passtest";

// AP параметры (точка доступа ESP)
static const char* AP_SSID = "STEM_SK";
static const char* AP_PASS = "passk123";

// Cоздаём веб-сервер на порту 80
ESP8266WebServer server(80);

// Данные маршрутов
static const uint8_t ROUTES_COUNT = 3;

const char* ROUTE_NAMES[ROUTES_COUNT] = {
  "GREEN",
  "BLUE",
  "YELLOW",
};

// Хранилище заявок по картам

// MAX_CARDS задаёт максимальное количество уникальных карт, которые мы запомним
static const uint16_t MAX_CARDS = 200;

// Заявка: (uid_hash + uid_len) -> route
// Храним hash (FNV-1a 32-bit) от HEX-строки и длину HEX-строки
struct CardRecord {
  uint32_t hash;
  uint8_t uidLen;  // длина HEX UID (символов)
  uint8_t route;   // 0..ROUTES_COUNT-1
  bool used;
};

CardRecord cards[MAX_CARDS];

// Счётчики маршрутов
uint16_t routeCounts[ROUTES_COUNT] = { 0, 0, 0 };

// Приём по Serial
String serialLine;

// HTML
const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Выбор маршрутов</title>
  <style>
    body { font-family: system-ui, sans-serif; padding: 18px; }
    .card { max-width: 720px; margin: 0 auto; border: 1px solid #ddd; border-radius: 16px; padding: 16px; }
    h1 { font-size: 20px; margin: 0 0 10px; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { display:flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid #eee; }
    li:first-child { border-top: none; }
    .name { opacity: .9; }
    .count { font-weight: 700; }
    .status { margin-top: 10px; font-size: 12px; opacity: .7; }
    button { margin-top: 12px; padding: 10px 12px; border-radius: 10px; border: 1px solid #ccc; background: #f7f7f7; cursor: pointer; }
    .row { display:flex; gap: 8px; flex-wrap: wrap; }
    select { padding: 10px 12px; border-radius: 10px; border: 1px solid #ccc; background: #fff; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Выбор маршрутов</h1>

    <ul id="list"></ul>

    <div class="row">
      <button id="resetAllBtn">Сбросить все</button>

      <br>
      <select id="routeSel"></select>
      <button id="resetRouteBtn">Сбросить выбранный маршрут</button>
    </div>

    <div id="status" class="status">Подключение…</div>
  </div>

<script>
async function load(){
  try{
    const r = await fetch('/data', { cache: 'no-store' });
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json(); // { routes:[{name,count,index},...], total }

    const ul = document.getElementById('list');
    ul.innerHTML = '';

    for(const item of data.routes){
      const li = document.createElement('li');

      const left = document.createElement('span');
      left.className = 'name';
      left.textContent = 'Маршрут ' + item.name;

      const right = document.createElement('span');
      right.className = 'count';
      right.textContent = item.count;

      li.appendChild(left);
      li.appendChild(right);
      ul.appendChild(li);
    }

    // селект для сброса маршрута (инициализируем один раз)
    const sel = document.getElementById('routeSel');
    if(sel.options.length === 0){
      for(const item of data.routes){
        const opt = document.createElement('option');
        opt.value = item.index;
        opt.textContent = item.name;
        sel.appendChild(opt);
      }
    }

    document.getElementById('status').textContent =
      'Обновлено: ' + new Date().toLocaleTimeString() + ' | Всего заявок: ' + data.total;
  }catch(e){
    document.getElementById('status').textContent = 'Ошибка: ' + e.message;
  }
}

setInterval(load, 300);
load();

document.getElementById('resetAllBtn').onclick = async () => {
  await fetch('/reset', { cache: 'no-store' });
  load();
};

document.getElementById('resetRouteBtn').onclick = async () => {
  const idx = document.getElementById('routeSel').value;
  await fetch('/reset?route=' + encodeURIComponent(idx), { cache: 'no-store' });
  load();
};
</script>
</body>
</html>
)HTML";

// Утилита FNV-1a 32-bit hash
uint32_t fnv1a(const char* s, uint8_t len) {
  uint32_t h = 2166136261u;
  for (uint8_t i = 0; i < len; i++) {
    h ^= (uint8_t)s[i];
    h *= 16777619u;
  }
  return h;
}

// Хранилище заявок по картам
int findCard(uint32_t hash, uint8_t uidLen) {
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].hash == hash && cards[i].uidLen == uidLen) return (int)i;
  }
  return -1;
}

// Найти свободный слот для новой карты
int findFreeSlot() {
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (!cards[i].used) return (int)i;
  }
  return -1;
}

// Подсчитать общее количество уникальных карт
uint16_t totalCards() {
  uint16_t t = 0;
  for (uint16_t i = 0; i < MAX_CARDS; i++)
    if (cards[i].used) t++;
  return t;
}

// Добавление или обновление заявки по карте
void applyVote(uint32_t hash, uint8_t uidLen, uint8_t route) {
  int pos = findCard(hash, uidLen);

  if (pos >= 0) {
    // Карта уже есть
    uint8_t oldRoute = cards[pos].route;
    if (oldRoute == route) {
      // Если тот же маршрут — ничего не делаем
      return;
    }
    // Переназначение маршрута
    if (oldRoute < ROUTES_COUNT && routeCounts[oldRoute] > 0) routeCounts[oldRoute]--;
    cards[pos].route = route;
    routeCounts[route]++;
    return;
  }

  // Новая карта
  int freePos = findFreeSlot();
  if (freePos < 0) {
    // Переполнение таблицы — можно игнорировать или сбрасывать всё
    // Здесь просто игнорируем новую карту
    return;
  }

  cards[freePos].used = true;
  cards[freePos].hash = hash;
  cards[freePos].uidLen = uidLen;
  cards[freePos].route = route;
  routeCounts[route]++;
}

// Удаление заявки по карте
bool removeVote(uint32_t hash, uint8_t uidLen) {
  int pos = findCard(hash, uidLen);
  if (pos < 0) return false;

  uint8_t r = cards[pos].route;
  if (r < ROUTES_COUNT && routeCounts[r] > 0) routeCounts[r]--;

  cards[pos].used = false;
  return true;
}

// Сброс всех заявок
void resetAll() {
  for (uint16_t i = 0; i < MAX_CARDS; i++) cards[i].used = false;
  for (uint8_t r = 0; r < ROUTES_COUNT; r++) routeCounts[r] = 0;
}

// Сброс заявок конкретного маршрута
void resetRoute(uint8_t route) {
  if (route >= ROUTES_COUNT) return;

  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].route == route) {
      cards[i].used = false;
    }
  }

  // Пересчёт счётчиков
  for (uint8_t r = 0; r < ROUTES_COUNT; r++) routeCounts[r] = 0;
  for (uint16_t i = 0; i < MAX_CARDS; i++) {
    if (cards[i].used && cards[i].route < ROUTES_COUNT) routeCounts[cards[i].route]++;
  }
}

// Хэндлер для корня /
void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

// Хэндлер для /data — отдаём JSON с данными
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

// Хэндлеры для /reset (сброс всего) или /reset?route=N (сброс маршрута N)
void handleReset() {
  if (server.hasArg("route")) {
    int r = server.arg("route").toInt();
    if (r >= 0 && r < ROUTES_COUNT) {
      resetRoute((uint8_t)r);
      server.send(200, "text/plain; charset=utf-8", "OK ROUTE RESET");
      return;
    }
    server.send(400, "text/plain; charset=utf-8", "Bad route");
    return;
  }

  resetAll();
  server.send(200, "text/plain; charset=utf-8", "OK ALL RESET");
}

// Парсер строки из Serial (CARD=<HEX>;ROUTE=<idx>)
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

// Проверка, что строка состоит из HEX символов
bool isHexString(const String& s) {
  for (uint16_t i = 0; i < s.length(); i++) {
    char c = s[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
    if (!ok) return false;
  }
  return true;
}

// Обработка строки из Serial
void processSerialLine(const String& rawLine) {
  String line = rawLine;
  line.trim();
  if (line.length() == 0) return;

  // Проверка удаления: REMOVE=<HEX_UID>
  if (line.startsWith("REMOVE=")) {
    String uidHex = line.substring(7);
    uidHex.trim();

    if (!isHexString(uidHex)) return;

    uint8_t uidLen = (uidHex.length() > 250) ? 250 : (uint8_t)uidHex.length();
    uint32_t h = fnv1a(uidHex.c_str(), uidLen);

    removeVote(h, uidLen);  // если не было — просто ничего
    return;
  }

  // Иначе — попытка парсинга CARD и ROUTE
  line.replace(" ", ";");

  String uidHex, routeStr;
  if (!parseKeyValue(line, "CARD=", uidHex)) return;
  if (!parseKeyValue(line, "ROUTE=", routeStr)) return;

  if (!isHexString(uidHex)) return;

  int route = routeStr.toInt();
  if (route < 0 || route >= ROUTES_COUNT) return;

  // Считаем hash от HEX строки UID
  uint8_t uidLen = (uidHex.length() > 250) ? 250 : (uint8_t)uidHex.length();
  uint32_t h = fnv1a(uidHex.c_str(), uidLen);

  applyVote(h, uidLen, (uint8_t)route);
}

// Опрашиваем Serial и собираем строки
void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();

    if (c == '\n') {
      serialLine.trim();
      if (serialLine.length() > 0) processSerialLine(serialLine);
      serialLine = "";
    } else {
      if (serialLine.length() < 120) serialLine += c;
      else serialLine = "";
    }
  }
}

// Подключение к Wi-Fi
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.println();
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);

  const uint32_t tStart = millis();
  const uint32_t timeoutMs = 20000;

  while (WiFi.status() != WL_CONNECTED && (millis() - tStart) < timeoutMs) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connect FAILED (timeout).");
  }
}

// Настройка и главный цикл
void setup() {
  Serial.begin(115200);
  delay(50);

  resetAll();

  // Соединяемся с Wi-Fi
  connectWiFi();

  // Поднимаем точку доступа
  // WiFi.mode(WIFI_AP);
  // WiFi.softAP(AP_SSID, AP_PASS);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/data", HTTP_GET, handleData);
  server.on("/reset", HTTP_GET, handleReset);

  server.begin();
  Serial.println("HTTP server started.");
}

void loop() {
  server.handleClient();
  pollSerial();
}