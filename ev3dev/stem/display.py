#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading

from ev3dev2.display import Display


class DisplayUpdater(object):
    """Обновление дисплея в отдельном потоке для неблокирующей работы"""
    def __init__(self, display=Display()):
        self.display = display
        self.lock = threading.Lock()
        self.status = ""
        self.ip = ""
        self.intersections = 0
        self.total = 0
        self.route_name = ""
        self.running = False
        self.thread = None

    def start(self):
        """Запустить поток обновления дисплея"""
        self.running = True
        self.thread = threading.Thread(target=self._update_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """Остановить поток обновления дисплея"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def update(self, status, ip, intersections=0, total=0, route_name=""):
        """Обновить данные для отображения (неблокирующий вызов)"""
        with self.lock:
            self.status = status
            self.ip = ip
            self.intersections = intersections
            self.total = total
            self.route_name = route_name

    def draw_waiting(self, routes, threshold, ip, leader_idx=None):
        """Отображение маршрутов во время ожидания"""
        self.display.clear()
        self.display.text_grid("Connected: OK ({})".format(ip), x=0, y=0, clear_screen=False)
        self.display.text_grid("STATUS: Waiting", x=0, y=2, clear_screen=False, font="charB12")
        self.display.text_grid("Threshold: {}".format(threshold), x=0, y=4, clear_screen=False)
        self.display.text_grid("Routes:", x=0, y=5, clear_screen=False)

        for i, route in enumerate(routes[:4]):
            mark = ">" if i == leader_idx else " "
            name = str(route.get("name", "?"))[:8]
            count = int(route.get("count", 0))
            line = "{} {} - {}".format(mark, name, count)
            self.display.text_grid(line, x=0, y=6 + i, clear_screen=False)

        self.display.update()

    def draw_error(self, ip):
        """Отображение ошибки подключения"""
        self.display.clear()
        self.display.text_grid("Connected: FAIL ({})".format(ip), x=0, y=0, clear_screen=False)
        self.display.text_grid("STATUS: Error", x=0, y=2, clear_screen=False, font="charB12")
        self.display.update()

    def draw_status(self, status, ip, intersections=0, total=0):
        """Отображение текущего статуса"""
        self.display.clear()
        self.display.text_grid("Connected: OK ({})".format(ip), x=0, y=0, clear_screen=False)
        self.display.text_grid("STATUS: {}".format(status), x=0, y=2, clear_screen=False, font="charB12")

        if intersections > 0 or total > 0:
            self.display.text_grid("Intersections: {}/{}".format(intersections, total),
                                 x=0, y=4, clear_screen=False)

        self.display.update()

    def _update_loop(self):
        """Цикл обновления дисплея в отдельном потоке"""
        while self.running:
            with self.lock:
                status = self.status
                ip = self.ip
                intersections = self.intersections
                total = self.total
                route_name = self.route_name

            # Обновление дисплея (медленная операция)
            self.display.clear()
            self.display.text_grid("Connected: OK ({})".format(ip), x=0, y=0, clear_screen=False)

            self.display.text_grid("STATUS: {}".format(status), x=0, y=2, clear_screen=False, font="charB12")

            if intersections > 0 or total > 0:
                self.display.text_grid("Intersections: {}/{}".format(intersections, total),
                                     x=0, y=4, clear_screen=False)

            if route_name:
                self.display.text_grid("Route: {}".format(route_name[:15]), x=0, y=6, clear_screen=False)

            self.display.update()
            time.sleep(0.3)  # Обновляем дисплей ~3 раза в секунду
