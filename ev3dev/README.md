# Устройство на EV3

Справочная информация:
- https://sites.google.com/site/ev3devpython
- https://ev3dev-lang.readthedocs.io/


Перед копированием программы на блок EV3 нужно дать права доступа на запуск:
```sh
chmod +x stem_ev3.py
```

Загрузка файлов на блок Lego EV3 с ev3dev через VS Code:
- Откройте в VS Code палитру: Ctrl+Shift+P
- Введите `ev3dev: Connect to a device` и выберите подключаемый блок или `I don't see my device...`, затем укажите название и IP адрес (имя пользователя: `robot`, пароль: `maker`)
- В боковой панели найдите EV3DEV DEVICE BROWSER и подключитесь к устройству
- Можете загружать файлы на устройство перетаскиванием из вашей рабочей области в браузер робота в `/home/robot`
