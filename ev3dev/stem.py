#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EV3dev: опрос ESP8266 и вывод счётчиков маршрутов
"""

import time
import json

from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from ev3dev2.display import Display

ESP_URL = "http://192.168.4.1/data"
REFRESH_SEC = 1.0
HTTP_TIMEOUT = 2.0

def to_ascii(s):
    # Приводим к str и выбрасываем все не-ASCII символы
    if not isinstance(s, str):
        s = str(s)
    return s.encode('ascii', 'replace').decode('ascii')


def fetch_routes():
    response = urlopen(ESP_URL, timeout=HTTP_TIMEOUT)
    raw = response.read().decode("utf-8")

    data = json.loads(raw)

    if "routes" not in data:
        raise ValueError("No 'routes' field")

    routes = []
    for r in data["routes"]:
        routes.append({
            "name": str(r.get("name", "")),
            "count": int(r.get("count", 0))
        })

    return routes


def draw_routes(display, routes):
    display.clear()
    display.text_grid("ESP Routes", x=0, y=0, clear_screen=False)

    y = 2
    for i, r in enumerate(routes[:7]):
        name = to_ascii(r["name"])

        # только ASCII многоточие
        if len(name) > 14:
            name = name[:14] + "..."

        line = "{} {} {}".format(
            i + 1,
            name.ljust(16),
            str(r["count"]).rjust(4)
        )
        display.text_grid(line, x=0, y=y, clear_screen=False)
        y += 1

    display.update()


def draw_error(display, msg):
    display.clear()
    display.text_grid("ESP ERROR", x=0, y=0, clear_screen=False)

    msg = to_ascii(msg)

    # перенос строк
    max_len = 18
    lines = []
    while msg:
        lines.append(msg[:max_len])
        msg = msg[max_len:]

    y = 2
    for line in lines[:7]:
        display.text_grid(line, x=0, y=y, clear_screen=False)
        y += 1

    display.update()



def main():
    disp = Display()
    disp.clear()
    disp.text_grid("Starting...", x=0, y=0)
    disp.update()

    while True:
        try:
            routes = fetch_routes()
            draw_routes(disp, routes)

        except HTTPError as e:
            draw_error(disp, "HTTP {}".format(e.code))
        except URLError:
            draw_error(disp, "No connection")
        except ValueError as e:
            draw_error(disp, str(e))
        except Exception as e:
            draw_error(disp, type(e).__name__)

        time.sleep(REFRESH_SEC)


if __name__ == "__main__":
    main()