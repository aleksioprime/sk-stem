#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import sys

from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from ev3dev2.display import Display

# --- Настройки ---
ESP_IP = "192.168.1.104"
REFRESH_SEC = 1.0
HTTP_TIMEOUT = 2.0


def fetch_routes(ip):
    url = "http://{}/data".format(ip)
    r = urlopen(url, timeout=HTTP_TIMEOUT)
    data = json.loads(r.read().decode("utf-8", "replace"))
    return data.get("routes", [])


def leader_index(routes):
    if not routes:
        return None
    best_i = 0
    best_v = routes[0].get("count", 0)
    for i in range(1, len(routes)):
        if routes[i].get("count", 0) > best_v:
            best_v = routes[i]["count"]
            best_i = i
    return best_i


def draw_success(display, ip, routes):
    display.clear()
    display.text_grid("SUCCESS ({ip})".format(ip=ip), x=0, y=0, clear_screen=False)

    display.text_grid("Routes:", x=0, y=2, clear_screen=False, font="charB12")

    li = leader_index(routes)

    for i, r in enumerate(routes[:6]):
        mark = ">" if i == li else " "
        name = str(r.get("name", "?"))
        count = int(r.get("count", 0))
        line = "{} {} - {}".format(mark, name, count)
        display.text_grid(line[:20], x=0, y=4 + i, clear_screen=False)

    display.update()


def draw_error(display, ip):
    display.clear()
    display.text_grid("Connect: ERROR ({ip})".format(ip=ip), x=0, y=0, clear_screen=False)
    display.update()


def main():
    ip = ESP_IP
    if len(sys.argv) >= 2:
        ip = sys.argv[1].strip()

    disp = Display()

    while True:
        try:
            routes = fetch_routes(ip)
            draw_success(disp, ip, routes)
        except (HTTPError, URLError, ValueError, Exception):
            draw_error(disp, ip)

        time.sleep(REFRESH_SEC)


if __name__ == "__main__":
    main()
