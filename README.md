# Программы для проекта логистической системы

## Робот на EV3

### Подготовка EV3

Скачайте дистрибутив операционной системы [ev3dev](https://www.ev3dev.org/docs/getting-started/#step-1-download-the-latest-ev3dev-image-file)

Залейте образ на SD-карту с помощью [Win32 Disk Imager](https://sourceforge.net/projects/win32diskimager/) или [Balena Etcher](https://etcher.balena.io/)

Вставьте SD-карту в блок Lego Mindstorms EV3 и включите его

Для подключения к WiFI необходимо WiFi-адаптер. Настроить подключение к WiFi можно с помощью встроенных инструментов блока EV3. Подключаться по SSH можно с использованием имени `robot` и пароля `maker`

### Подключение EV3 к компьютеру через кабель

Подключите через miniUSB кабель от блока EV3 к компьютеру

Выберите Wireless and Networks -> All Network Connections -> Wired -> Connect. Можно активировать параметр `Connect automatically` для автоподключения.

Откройте настройки `IPv4` в выберите `Load Windows default`. Посмотрите IP и укажите подобный в настройках сетевого подключения компьютера. Например, IP устройства `192.168.137.3`, то IP компьютера можно сделать `192.168.137.10`

При загрузке файла нужно его сделать исполняемым:
```sh
chmod +x /home/robot/stem.py
```

## Устройство на Arduino с ESP

### Прошивка ESP8266 (Troyka-модуль)

Подключите плату ESP8266 к ковертеру USB to TTL:
- 5V -> V (если плата работает от напряжения 5В) или 3.3V -> V
- GND -> G
- TX -> RX
- RX -> TX

Настройте Arduino IDE:
- Перейдите в меню Arduino IDE → Preferences → Additional Boards Manager URLs и вставьте `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
- Передите в меню Tools → Board → Boards Manager, найдите `ESP8266 by ESP8266 Community` и установите библиотеки
- Перейдите в меню Tools -> Board и выберите `Generic ESP8266 Module`

Войдите в режим прошивки на плате ESP8266:
- Зажмите `P` или `PROG`
- Нажмите `RST`
- Отпустите `RST`
- Отпустите `P`

Тестовый скетч:
```c++
void setup() {
  pinMode(2, OUTPUT);
}

void loop() {
  digitalWrite(2, LOW);
  delay(500);
  digitalWrite(2, HIGH);
  delay(500);
}
```