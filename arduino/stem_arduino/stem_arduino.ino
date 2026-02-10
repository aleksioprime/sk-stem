#include <SoftwareSerial.h>
#include <SPI.h>
#include <Adafruit_PN532.h>

// -------------------- UART к ESP --------------------
// Arduino RX <- ESP TX
// Arduino TX -> ESP RX
SoftwareSerial esp(11, A3);  // RX=11, TX=A3

// -------------------- PN532 --------------------
// Вариант с IRQ + I2C
#define PN532_IRQ 6
#define PN532_RESET -1  // -1 если reset pin не подключён
Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);

// -------------------- Маршруты --------------------
const uint8_t ROUTES_COUNT = 3;

// Кнопки маршрутов
const uint8_t BTN_ROUTE_GREEN = 10;
const uint8_t BTN_ROUTE_BLUE = 12;
const uint8_t BTN_ROUTE_YELOW = 13;

const uint8_t BTN_CANCEL = 8;

// LED-индикатор состояния
const uint8_t LED_PIN = 9;

// Пины в массив для удобства
const uint8_t BTN_PINS[ROUTES_COUNT] = { BTN_ROUTE_GREEN, BTN_ROUTE_BLUE, BTN_ROUTE_YELOW };

// -------------------- Антидребезг --------------------
const unsigned long DEBOUNCE_MS = 80;

struct DebouncedButton {
  uint8_t pin;
  bool lastStable;
  unsigned long lastChangeAt;
};

DebouncedButton btnRoutes[ROUTES_COUNT];
DebouncedButton btnCancel;

// -------------------- FSM --------------------
enum SystemState {
  STATE_WAIT_CARD,
  STATE_WAIT_BUTTON
};

SystemState state = STATE_WAIT_CARD;

String lastUidHex;  // UID последней карты в hex
unsigned long waitButtonSince = 0;
const unsigned long WAIT_BUTTON_TIMEOUT_MS = 10000;  // 10 сек на выбор маршрута

// -------------------- helpers --------------------
bool isPressedRaw(uint8_t pin) {
  // INPUT_PULLUP: pressed = LOW
  return (digitalRead(pin) == LOW);
}

bool checkPressed(DebouncedButton& b) {
  bool pressedNow = isPressedRaw(b.pin);

  // Если состояние изменилось — ждём стабилизацию
  if (pressedNow != b.lastStable) {
    if (millis() - b.lastChangeAt >= DEBOUNCE_MS) {
      b.lastChangeAt = millis();
      bool was = b.lastStable;
      b.lastStable = pressedNow;

      // событие "нажатие" = переход false -> true
      if (!was && pressedNow) return true;
    }
  }
  return false;
}

String uidToHex(const uint8_t* uid, uint8_t len) {
  const char* hex = "0123456789ABCDEF";
  String s;
  s.reserve(len * 2);
  for (uint8_t i = 0; i < len; i++) {
    uint8_t v = uid[i];
    s += hex[(v >> 4) & 0x0F];
    s += hex[v & 0x0F];
  }
  return s;
}

// Отправка заявки в ESP: CARD=<uid>;ROUTE=<idx>
void sendVote(const String& uidHex, uint8_t idx) {
  esp.print("CARD=");
  esp.print(uidHex);
  esp.print(";ROUTE=");
  esp.println(idx);

  Serial.print("Sent: CARD=");
  Serial.print(uidHex);
  Serial.print(";ROUTE=");
  Serial.println(idx);
}

// Отправка удаления заявки по карте: REMOVE=<uid>
void sendRemove(const String& uidHex) {
  esp.print("REMOVE=");
  esp.println(uidHex);

  Serial.print("Sent: REMOVE=");
  Serial.println(uidHex);
}

// Проверка RFID: если карта найдена — сохраняем UID в lastUidHex
bool checkRFID() {
  uint8_t uid[8];
  uint8_t uidLength;

  bool success = nfc.readPassiveTargetID(
    PN532_MIFARE_ISO14443A,
    uid,
    &uidLength);

  if (!success) return false;

  lastUidHex = uidToHex(uid, uidLength);

  Serial.print("RFID UID: ");
  Serial.println(lastUidHex);

  return true;
}

void setupButtons() {
  // Инициализация кнопок маршрутов
  for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
    btnRoutes[i].pin = BTN_PINS[i];
    btnRoutes[i].lastStable = false;
    btnRoutes[i].lastChangeAt = 0;
    pinMode(BTN_PINS[i], INPUT_PULLUP);
  }

  // CANCEL
  btnCancel.pin = BTN_CANCEL;
  btnCancel.lastStable = false;
  btnCancel.lastChangeAt = 0;
  pinMode(BTN_CANCEL, INPUT_PULLUP);
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  esp.begin(115200);

  setupButtons();

  // NFC
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("Didn't find PN532");
    while (1) { delay(50); }
  }
  Serial.println("Found PN532");
  nfc.SAMConfig();

  Serial.println("Arduino started");
}

void loop() {
  switch (state) {

    case STATE_WAIT_CARD:
      {
        digitalWrite(LED_PIN, LOW);

        // Ждём карту
        if (checkRFID()) {
          Serial.println("Card accepted. Waiting for route button or cancel...");
          waitButtonSince = millis();
          state = STATE_WAIT_BUTTON;
        }
        break;
      }

    case STATE_WAIT_BUTTON:
      {
        digitalWrite(LED_PIN, HIGH);

        // Таймаут ожидания выбора
        if (millis() - waitButtonSince > WAIT_BUTTON_TIMEOUT_MS) {
          Serial.println("Timeout. Waiting for next card...");
          lastUidHex = "";
          state = STATE_WAIT_CARD;
          break;
        }

        // CANCEL — удалить заявку по этой карте (неважно какой маршрут)
        if (checkPressed(btnCancel)) {
          if (lastUidHex.length() > 0) {
            sendRemove(lastUidHex);
          }
          Serial.println("Cancel processed. Waiting for next card...");
          lastUidHex = "";
          state = STATE_WAIT_CARD;
          break;
        }

        // Кнопки маршрутов — отправить заявку
        for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
          if (checkPressed(btnRoutes[i])) {
            if (lastUidHex.length() > 0) {
              sendVote(lastUidHex, i);
            }
            Serial.println("Route sent. Waiting for next card...");
            lastUidHex = "";
            state = STATE_WAIT_CARD;
            break;
          }
        }

        break;
      }
  }

  delay(1);
}
