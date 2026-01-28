/*
  Проект для Arduino

  Задача:
  - Есть 3 кнопки, каждая соответствует своему маршруту
  - При НАЖАТИИ кнопки отправляем в ESP событие по UART:
        ROUTE=<index>\n
  - ESP принимает и увеличивает счётчики на веб-странице

  Кнопки подключены к пинам:
    Route 0 -> D9
    Route 1 -> D12
    Route 2 -> A1 (как цифровой пин)

  Подключение кнопок:
  - Один контакт кнопки -> GND
  - Второй контакт кнопки -> указанный пин (D9 / D12 / A1)
  - В коде включаем INPUT_PULLUP, поэтому логика такая:
      отпущена = HIGH
      нажата   = LOW

  Связь с ESP:
  - Используем SoftwareSerial на A4/A5
*/

#include <SoftwareSerial.h>
#include <SPI.h>
#include <Adafruit_PN532.h>

// -------------------- UART к ESP --------------------
// (от TX, от RX)
SoftwareSerial esp(11, A3);

// -------------------- PN532 --------------------
#define PN532_IRQ  6
#define LED 9

Adafruit_PN532 nfc(PN532_IRQ, 100);

// -------------------- Маршруты --------------------
const uint8_t ROUTES_COUNT = 3;

// Кнопки маршрутов
const uint8_t BTN_ROUTE_GREEN = 13;
const uint8_t BTN_ROUTE_BLUE = 12;
const uint8_t BTN_ROUTE_YELOW = 10;

const uint8_t BTN_CANCEL = 8;

// Пины в массив для удобства
const uint8_t BTN_PINS[ROUTES_COUNT] = {BTN_ROUTE_GREEN, BTN_ROUTE_BLUE, BTN_ROUTE_YELOW};

// -------------------- Антидребезг --------------------
// Время, в течение которого игнорируем повторные срабатывания после клика
const unsigned long DEBOUNCE_MS = 80;
// Последнее подтверждённое состояние кнопок (true = нажата, false = отпущена)
bool lastPressed[ROUTES_COUNT] = {false, false, false};
// Время последнего изменения состояния (по каждой кнопке отдельно)
unsigned long lastChangeAt[ROUTES_COUNT] = {0, 0, 0};

enum SystemState {
  STATE_WAIT_CARD,
  STATE_WAIT_BUTTON
};

SystemState state = STATE_WAIT_CARD;

// Отправка маршрута
void sendRoute(uint8_t idx) {
  // Протокол: ROUTE=<index>\n
  esp.print("ROUTE=");
  esp.println(idx);

  // Лог в USB Serial
  Serial.print("Sent: ROUTE=");
  Serial.println(idx);
}

// Чтение кнопки с антидребезгом
bool checkButtonPressed(uint8_t i) {
  // При INPUT_PULLUP:
  //   отпущена -> HIGH
  //   нажата   -> LOW
  bool pressedNow = (digitalRead(BTN_PINS[i]) == LOW);

  // Если состояние изменилось — запоминаем время изменения
  if (pressedNow != lastPressed[i]) {
    // Сразу не принимаем, а ждём, пока пройдёт DEBOUNCE_MS
    if (millis() - lastChangeAt[i] >= DEBOUNCE_MS) {
      lastChangeAt[i] = millis();
      // Здесь фиксируем новое стабильное состояние
      bool wasPressed = lastPressed[i];
      lastPressed[i] = pressedNow;

      // Событие "нажатие" — это переход: было не нажато -> стало нажато
      if (!wasPressed && pressedNow) {
        return true;
      }
    }
  }

  return false;
}

// Проверка RFID
bool checkRFID() {
  uint8_t uid[8];
  uint8_t uidLength;

  bool success = nfc.readPassiveTargetID(
    PN532_MIFARE_ISO14443A,
    uid,
    &uidLength
  );

  if (success) {
    Serial.print("RFID UID: ");
    nfc.PrintHex(uid, uidLength);
    Serial.println();
    return true;
  }

  return false;
}

void setup() {
  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  // USB Serial
  Serial.begin(115200);

  // SoftwareSerial
  esp.begin(115200);

  // Настраиваем кнопки на вход с подтяжкой к питанию
  pinMode(BTN_ROUTE_GREEN, INPUT_PULLUP);
  pinMode(BTN_ROUTE_BLUE, INPUT_PULLUP);
  pinMode(BTN_ROUTE_YELOW, INPUT_PULLUP);
  pinMode(BTN_CANCEL, INPUT_PULLUP);

  // NFC
  nfc.begin();
  int versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.print("Didn't find RFID/NFC reader");
    while(1) {
    }
  }

  Serial.println("Found RFID/NFC reader");
  // Настраиваем модуль
  nfc.SAMConfig();
  Serial.println("Arduino started");}

void loop() {

  switch (state) {

    // ------------------ Ждём карту ------------------
    case STATE_WAIT_CARD: {
      digitalWrite(LED, LOW);

      if (checkRFID()) {
        Serial.println("Card accepted. Waiting for button...");
        state = STATE_WAIT_BUTTON;
      }
      break;
    }

    // ------------------ Ждём кнопку ------------------
    case STATE_WAIT_BUTTON: {
      digitalWrite(LED, HIGH);

      for (uint8_t i = 0; i < ROUTES_COUNT; i++) {
        if (checkButtonPressed(i)) {
          sendRoute(i);
          Serial.println("Route sent. Waiting for next card...");
          state = STATE_WAIT_CARD;
          break;
        }
      }
      break;
    }
  }

  delay(1);
}
