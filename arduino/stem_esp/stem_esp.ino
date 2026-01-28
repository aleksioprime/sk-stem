/*
  Проект для ESP8266 (Wi-Fi Troyka Module):

  Задача:
  - ESP8266 поднимает точку доступа (Wi-Fi AP) и веб-страницу.
  - На веб-странице показываются "маршруты" и сколько людей их выбрало.
  - Arduino присылает события в ESP по Serial (UART).
  - ESP увеличивает счётчики и отдаёт их на страницу.

  Протокол по Serial:
    ROUTE=<index>\n
  где <index> — номер маршрута (0..N-1)

  Пример строки от Arduino:
    ROUTE=0
    ROUTE=2
    ROUTE=2

  Тогда счётчики станут:
    route0 += 1
    route2 += 2

  Как пользоваться:
  - Подключись к Wi-Fi: SSID "STEM_SK", пароль "passk123"
  - Открой в браузере: http://192.168.4.1/
*/

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// -------------------- Wi-Fi (точка доступа) --------------------
static const char* AP_SSID = "STEM_SK";
static const char* AP_PASS = "passk123";

// -------------------- Веб-сервер --------------------
ESP8266WebServer server(80);

// -------------------- Данные (маршруты и счётчики) --------------------
// Названия маршрутов
// Важно: количество маршрутов = ROUTES_COUNT
static const uint8_t ROUTES_COUNT = 3;

const char* ROUTE_NAMES[ROUTES_COUNT] = {
  "GREEN",
  "BLUE",
  "YELLOW",
};

// Счётчики (сколько людей выбрало маршрут)
volatile uint32_t routeCounts[ROUTES_COUNT] = {0, 0, 0};

// -------------------- Приём по Serial --------------------
// Буфер строки, которую читаем из UART
String serialLine;

// -------------------- HTML страница --------------------
// Cписок, который обновляется fetch'ем /data раз в 300 мс
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
  </style>
</head>
<body>
  <div class="card">
    <h1>Выбор маршрутов</h1>

    <ul id="list"></ul>

    <button id="resetBtn">Сбросить счётчики</button>
    <div id="status" class="status">Подключение…</div>
  </div>

<script>
async function load(){
  try{
    const r = await fetch('/data', { cache: 'no-store' });
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json(); // { routes: [{name, count}, ...] }

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

    document.getElementById('status').textContent =
      'Обновлено: ' + new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('status').textContent = 'Ошибка: ' + e.message;
  }
}

// Периодическое обновление
setInterval(load, 300);
load();

// Сброс — GET /reset
document.getElementById('resetBtn').onclick = async () => {
  await fetch('/reset', { cache: 'no-store' });
  load();
};
</script>
</body>
</html>
)HTML";

// -------------------- HTTP handlers --------------------

// Отдаём главную страницу
void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

// Отдаём данные в JSON:
// {
//   "routes":[{"name":"...","count":1}, ...]
// }
void handleData() {
  // Собираем JSON вручную, чтобы не тянуть дополнительные библиотеки

  String json;
  json.reserve(512); // чуть ускоряет работу/уменьшает фрагментацию памяти

  json += "{\"routes\":[";
  for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
    if (i > 0) json += ",";
    json += "{\"name\":\"";
    json += ROUTE_NAMES[i];
    json += "\",\"count\":";
    json += String(routeCounts[i]);
    json += "}";
  }
  json += "]}";

  server.send(200, "application/json; charset=utf-8", json);
}

// Сбросить счётчики
void handleReset() {
  for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
    routeCounts[i] = 0;
  }
  server.send(200, "text/plain; charset=utf-8", "OK");
}

// -------------------- Парсер Serial --------------------
/*
  Мы читаем UART посимвольно и копим строку до '\n'.
  Когда пришёл '\n', ожидаем формат:

    ROUTE=<index>

  Примеры корректных строк:
    ROUTE=0
    ROUTE=3
    ROUTE=2

  Если индекс некорректный — игнорируем
*/
void processSerialLine(const String& line) {
  // Защита от мусора
  if (!line.startsWith("ROUTE=")) return;

  // Берём подстроку после "ROUTE=" и превращаем в число
  int idx = line.substring(6).toInt();

  // Проверяем диапазон
  if (idx < 0 || idx >= ROUTES_COUNT) return;

  // Увеличиваем счётчик выбранного маршрута
  routeCounts[idx]++;
}

void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();

    // Если пришла новая строка
    if (c == '\n') {
      serialLine.trim();           // убираем пробелы и '\r' (Windows-окончания)
      if (serialLine.length() > 0) {
        processSerialLine(serialLine);
      }
      serialLine = "";             // очищаем буфер на следующую строку
    } else {
      // Ограничим размер буфера, чтобы не разрастался от мусора
      if (serialLine.length() < 80) {
        serialLine += c;
      } else {
        // Если строка слишком длинная — сброс (защита)
        serialLine = "";
      }
    }
  }
}

// -------------------- setup / loop --------------------
void setup() {
  /*
    Serial тут — UART, которым ESP общается с Arduino.
    Скорость должна совпадать у обеих сторон.
    115200 — удобно, но если на проводах шумно, можно поставить 9600/57600.
  */
  Serial.begin(115200);
  delay(50);

  // Поднимаем точку доступа
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);

  // Роут у ESP AP обычно 192.168.4.1 (стандартно для ESP8266 SoftAP)

  // Регистрируем маршруты HTTP
  server.on("/", HTTP_GET, handleRoot);
  server.on("/data", HTTP_GET, handleData);
  server.on("/reset", HTTP_GET, handleReset);

  server.begin();
}

void loop() {
  // Обслуживаем HTTP клиентов (браузер)
  server.handleClient();

  // Читаем события от Arduino
  pollSerial();
}
