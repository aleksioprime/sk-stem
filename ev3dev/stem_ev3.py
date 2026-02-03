#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json

from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from ev3dev2.motor import MoveTank, OUTPUT_B, OUTPUT_C
from ev3dev2.sensor.lego import ColorSensor
from ev3dev2.sensor import INPUT_2, INPUT_3
from ev3dev2.display import Display

# --- Настройки ---
ESP_IP = "192.168.1.104"
REFRESH_SEC = 1.0
HTTP_TIMEOUT = 2.0

# --- Настройки робота ---
THRESHOLD_COUNT = 5           # Количество заявок для старта
TOTAL_INTERSECTIONS = 4       # Общее количество перекрёстков
STOP_AT_INTERSECTION = 2      # На каком перекрёстке остановиться (задержка)
STOP_DELAY = 3.0              # Время задержки на перекрёстке (секунды)

# Параметры движения
BASE_SPEED = 30              # Базовая скорость (% от максимальной)
KP = 3.2
MAX_SPEED = 90               # Максимальная скорость (% от максимальной)

# Калибровка датчиков
L_WHITE = 90
L_BLACK = 10
R_WHITE = 90
R_BLACK = 10


def fetch_routes(ip):
    """Получить данные о маршрутах с ESP"""
    url = "http://{}/data".format(ip)
    r = urlopen(url, timeout=HTTP_TIMEOUT)
    data = json.loads(r.read().decode("utf-8", "replace"))
    return data.get("routes", [])


def check_threshold(routes, threshold):
    """Проверить, есть ли маршрут с нужным количеством заявок"""
    for route in routes:
        if route.get("count", 0) >= threshold:
            return True
    return False


def draw_waiting(display, routes, threshold, ip):
    """Отображение маршрутов во время ожидания"""
    display.clear()
    display.text_grid("Connected: OK ({})".format(ip), x=0, y=0, clear_screen=False)
    display.text_grid("STATUS: Waiting", x=0, y=2, clear_screen=False, font="charB12")
    display.text_grid("Threshold: {}".format(threshold), x=0, y=4, clear_screen=False)
    display.text_grid("Routes:", x=0, y=5, clear_screen=False)

    for i, route in enumerate(routes[:4]):
        name = str(route.get("name", "?"))[:8]
        count = int(route.get("count", 0))
        line = "  {} - {}".format(name, count)
        display.text_grid(line, x=0, y=6 + i, clear_screen=False)

    display.update()


def draw_error(display, ip):
    """Отображение ошибки подключения"""
    display.clear()
    display.text_grid("Connected: FAIL ({})".format(ip), x=0, y=0, clear_screen=False)
    display.text_grid("STATUS: Error", x=0, y=2, clear_screen=False, font="charB12")
    display.update()


def draw_status(display, status, ip, intersections=0, total=0):
    """Отображение текущего статуса"""
    display.clear()
    display.text_grid("Connected: OK ({})".format(ip), x=0, y=0, clear_screen=False)
    display.text_grid("STATUS: {}".format(status), x=0, y=2, clear_screen=False, font="charB12")

    if intersections > 0 or total > 0:
        display.text_grid("Intersections: {}/{}".format(intersections, total),
                         x=0, y=4, clear_screen=False)

    display.update()


class Robot(object):
    """Управление роботом через MoveTank"""
    def __init__(self, left_port=OUTPUT_B, right_port=OUTPUT_C):
        self.tank = MoveTank(left_port, right_port)

    def stop(self):
        self.tank.off(brake=True)

    def drive(self, left_speed, right_speed):
        self.tank.on(left_speed, right_speed)

    def drive_degrees(self, left_speed, right_speed, degrees):
        self.tank.on_for_degrees(left_speed, right_speed, degrees, brake=True, block=True)


class LineFollower(object):
    """Следование по линии с двумя датчиками"""
    def __init__(self, left_port=INPUT_2, right_port=INPUT_3):
        self.left = ColorSensor(left_port)
        self.right = ColorSensor(right_port)

        self.left.mode = 'COL-REFLECT'
        self.right.mode = 'COL-REFLECT'

        self.l_white = L_WHITE
        self.l_black = L_BLACK
        self.r_white = R_WHITE
        self.r_black = R_BLACK

    @staticmethod
    def clamp(x, lo, hi):
        return lo if x < lo else hi if x > hi else x

    def norm_reflect(self, raw, black, white):
        if white == black:
            return 0.0
        v = (raw - black) * 100.0 / (white - black)
        return self.clamp(v, 0.0, 100.0)

    def read_error(self):
        """Читает датчики и возвращает ошибку"""
        l_raw = int(self.left.value())
        r_raw = int(self.right.value())

        l = self.norm_reflect(l_raw, self.l_black, self.l_white)
        r = self.norm_reflect(r_raw, self.r_black, self.r_white)

        return l - r

    def detect_intersection(self):
        """Определяет перекрёсток (оба датчика видят чёрное)"""
        l_raw = int(self.left.value())
        r_raw = int(self.right.value())

        # Оба датчика близки к чёрному
        threshold = (self.l_black + self.l_white) / 2
        return l_raw < threshold and r_raw < threshold


def follow_line_with_intersections(robot, follower, display, ip, total_intersections, stop_at):
    """
    Едет по линии, считает перекрёстки
    """
    intersections_passed = 0
    on_intersection = False
    last_draw = 0.0

    draw_status(display, "Moving", ip, intersections_passed, total_intersections)

    # Если робот стоит на перекрёстке при старте, нужно сначала съехать с него
    if follower.detect_intersection():
        on_intersection = True
        robot.drive_degrees(BASE_SPEED, BASE_SPEED, 300)
        on_intersection = False

    while intersections_passed < total_intersections:
        # Проверка перекрёстка
        is_intersection = follower.detect_intersection()

        if is_intersection and not on_intersection:
            # Новый перекрёсток обнаружен
            on_intersection = True
            intersections_passed += 1

            draw_status(display, "Moving", ip, intersections_passed, total_intersections)

            # Задержка на нужном перекрёстке
            if intersections_passed == stop_at:
                robot.stop()
                draw_status(display, "Picking up passengers", ip, intersections_passed, total_intersections)
                time.sleep(STOP_DELAY)
                draw_status(display, "Moving", ip, intersections_passed, total_intersections)

        elif not is_intersection and on_intersection:
            # Покинули перекрёсток
            on_intersection = False

        # Движение по линии
        error = follower.read_error()
        turn = KP * error

        left_speed = BASE_SPEED - turn
        right_speed = BASE_SPEED + turn

        left_speed = follower.clamp(left_speed, -MAX_SPEED, MAX_SPEED)
        right_speed = follower.clamp(right_speed, -MAX_SPEED, MAX_SPEED)

        robot.drive(left_speed, right_speed)

        # Обновляем экран периодически
        now = time.time()
        if now - last_draw >= 0.5:
            last_draw = now
            draw_status(display, "Moving", ip, intersections_passed, total_intersections)

        time.sleep(0.01)

    robot.stop()
    draw_status(display, "Finished", ip)


def main():
    ip = ESP_IP

    display = Display()

    # Ждём набора заявок
    while True:
        try:
            routes = fetch_routes(ip)
            draw_waiting(display, routes, THRESHOLD_COUNT, ip)

            if check_threshold(routes, THRESHOLD_COUNT):
                break
        except (HTTPError, URLError, ValueError, Exception) as e:
            draw_error(display, ip)

        time.sleep(REFRESH_SEC)

    # Инициализация робота
    robot = Robot()
    follower = LineFollower()

    try:
        # Движение по маршруту
        follow_line_with_intersections(
            robot,
            follower,
            display,
            ip,
            TOTAL_INTERSECTIONS,
            STOP_AT_INTERSECTION
        )

        # Задержка перед завершением
        time.sleep(3.0)

    except KeyboardInterrupt:
        draw_status(display, "Interrupted", ip)
    finally:
        robot.stop()


if __name__ == "__main__":
    main()
