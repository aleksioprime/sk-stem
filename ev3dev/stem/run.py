#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json

from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from ev3dev2.motor import MoveTank, OUTPUT_B, OUTPUT_C
from ev3dev2.sensor.lego import ColorSensor
from ev3dev2.sensor import INPUT_2, INPUT_3
from ev3dev2.button import Button

from display import DisplayUpdater

# --- Настройки ---
SERVER_IP = "192.168.1.104" # IP адрес сервера, с которого получать данные о маршрутах
REFRESH_SEC = 1.0 # Частота обновления данных (секунды)
HTTP_TIMEOUT = 2.0 # Таймаут HTTP запросов (секунды)

# --- Настройки робота ---
THRESHOLD_COUNT = 3 # Количество заявок для старта
TOTAL_INTERSECTIONS = 3 # Общее количество перекрёстков
STOP_AT_INTERSECTION = 1 # На каком перекрёстке остановиться (задержка)
STOP_DELAY = 3.0 # Время задержки на перекрёстке (секунды)

# Параметры движения
BASE_SPEED = 30 # Базовая скорость (% от максимальной)
KP = 0.2 # Коэффициент пропорциональной части для управления (настройка для лучшего следования по линии)
MAX_SPEED = 90 # Максимальная скорость (% от максимальной)
TURN_SPEED = 25 # Скорость поворота на перекрёстке
TURN_DEGREES = 180 # Градусы поворота (подбирается под геометрию трассы)
UTURN_DEGREES = 360 # Градусы разворота (обычно около 2 * TURN_DEGREES)
PASS_INTERSECTION_DEGREES = 100 # Проезд перекрёстка прямо
BEFORE_TURN_DEGREES = 100 # Движение вперёд после поворота для захвата линии
PAUSE_DELAY = 2.0 # Пауза на перекрёстке для действия "pause" (секунды)

# Калибровка датчиков
L_WHITE = 70 # Отражение белого для левого датчика
L_BLACK = 8 # Отражение чёрного для левого датчика
R_WHITE = 70 # Отражение белого для правого датчика
R_BLACK = 8 # Отражение чёрного для правого датчика

# Сценарии движения по перекрёсткам после остановки "Picking up passengers"
# Для green:
# 1 - left, 2 - straight, 3 - right, 4 - stop, 5 - u_turn, 6 - pause
# Доступные действия: left, straight, right, stop, u_turn, pause
ROUTE_POST_STOP_ACTIONS = {
    "green": ("straight", "u_turn", "straight", "straight", "stop"),
    "blue": ("left", "right", "u_turn", "left", "right", "straight", "stop"),
    "yellow": ("left", "straight", "right", "u_turn", "left", "straight", "right", "straight", "stop"),
}


def fetch_routes(ip):
    """Получить данные о маршрутах с сервера"""
    url = "http://{}/data".format(ip)
    result = urlopen(url, timeout=HTTP_TIMEOUT)
    data = json.loads(result.read().decode("utf-8", "replace"))
    return data.get("routes", [])


def reset_route(ip, route_index):
    """Сбросить заявки на конкретном маршруте"""
    try:
        url = "http://{}/reset?route={}".format(ip, route_index)
        urlopen(url, timeout=HTTP_TIMEOUT)
        return True
    except (HTTPError, URLError, Exception):
        return False


def check_threshold(routes, threshold):
    """Проверить, есть ли маршрут с нужным количеством заявок"""
    for route in routes:
        if route.get("count", 0) >= threshold:
            return True
    return False


def get_leader(routes):
    """Получить индекс и маршрут с максимальным количеством заявок"""
    if not routes:
        return None, None

    best_idx = max(range(len(routes)), key=lambda i: routes[i].get("count", 0))
    return best_idx, routes[best_idx]


def get_post_stop_actions(route_name):
    """Вернуть действия после остановки в зависимости от маршрута"""
    normalized = str(route_name or "").strip().lower()
    for route_key, actions in ROUTE_POST_STOP_ACTIONS.items():
        if route_key in normalized:
            return list(actions)
    return []


class Robot(object):
    """Управление роботом через MoveTank"""
    def __init__(self, left_port=OUTPUT_C, right_port=OUTPUT_B):
        self.tank = MoveTank(left_port, right_port)

    def stop(self):
        """Остановить робота"""
        self.tank.off(brake=True)

    def drive(self, left_speed, right_speed):
        """Движение с заданными скоростями для левого и правого моторов"""
        self.tank.on(left_speed, right_speed)

    def drive_degrees(self, left_speed, right_speed, degrees):
        """Движение на определённое количество градусов (используется для съезда с перекрёстка при старте) """
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
        """Ограничить значение x диапазоном [lo, hi]"""
        return lo if x < lo else hi if x > hi else x

    def norm_reflect(self, raw, black, white):
        """Нормализовать значение отражения в диапазон 0..100"""
        if white == black:
            return 0.0
        v = (raw - black) * 100.0 / (white - black)
        return self.clamp(v, 0.0, 100.0)

    def read_error(self):
        """Читает датчики и возвращает ошибку (левый - правый)"""
        l_raw = int(self.left.value())
        r_raw = int(self.right.value())

        l = self.norm_reflect(l_raw, self.l_black, self.l_white)
        r = self.norm_reflect(r_raw, self.r_black, self.r_white)

        return l - r

    def detect_intersection(self):
        """Определяет перекрёсток (оба датчика видят чёрное)"""
        l_raw = int(self.left.value())
        r_raw = int(self.right.value())

        threshold = (self.l_black + self.l_white) / 2
        return l_raw < threshold and r_raw < threshold


def movement(robot, follower, display, button, route_name="", total_intersections=TOTAL_INTERSECTIONS, stop_at=STOP_AT_INTERSECTION):
    """
    Едет по линии, считает перекрёстки
    При нажатии кнопки DOWN - прерывает движение
    """
    intersections_passed = 0
    on_intersection = False
    picked_up_passengers = False
    post_stop_intersections = 0
    route_actions = get_post_stop_actions(route_name)

    # Для маршрутов со сценарием после остановки показываем общее количество
    # перекрёстков: до остановки + количество действий после остановки.
    display_total = total_intersections
    if route_actions:
        display_total = stop_at + len(route_actions)

    display.update("Moving", SERVER_IP, intersections_passed, display_total, route_name)

    # Робот выезжает со зоны старта на линию
    robot.drive_degrees(BASE_SPEED, BASE_SPEED, 300)

    # Основной цикл движения по линии с подсчётом перекрёстков
    while True:
        # Проверка кнопки "вниз" для прерывания движения
        if button.down:
            robot.stop()
            display.update("Cancelled by user", SERVER_IP, route_name=route_name)
            time.sleep(1.0)
            return

        # Проверка перекрёстка
        is_intersection = follower.detect_intersection()

        if is_intersection and not on_intersection:
            # Новый перекрёсток обнаружен
            on_intersection = True
            intersections_passed += 1

            display.update("Moving", SERVER_IP, intersections_passed, display_total, route_name)

            # Задержка на нужном перекрёстке
            just_picked_up = False
            if intersections_passed == stop_at:
                robot.stop()
                display.update("Picking up passengers", SERVER_IP, intersections_passed, display_total, route_name)
                time.sleep(STOP_DELAY)
                display.update("Moving", SERVER_IP, intersections_passed, display_total, route_name)
                picked_up_passengers = True
                just_picked_up = True

            # Если для маршрута задан сценарий после остановки - выполняем его.
            # Первый перекрёсток с действиями начинается ПОСЛЕ перекрёстка остановки.
            if route_actions and picked_up_passengers and not just_picked_up:
                post_stop_intersections += 1
                action = route_actions[post_stop_intersections - 1] if post_stop_intersections <= len(route_actions) else "stop"

                if action == "left":
                    display.update("Turn left", SERVER_IP, intersections_passed, display_total, route_name)
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, BEFORE_TURN_DEGREES)
                    robot.drive_degrees(-TURN_SPEED, TURN_SPEED, TURN_DEGREES)
                elif action == "right":
                    display.update("Turn right", SERVER_IP, intersections_passed, display_total, route_name)
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, BEFORE_TURN_DEGREES)
                    robot.drive_degrees(TURN_SPEED, -TURN_SPEED, TURN_DEGREES)
                elif action == "straight":
                    display.update("Go straight", SERVER_IP, intersections_passed, display_total, route_name)
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, PASS_INTERSECTION_DEGREES)
                elif action == "u_turn":
                    display.update("U-turn", SERVER_IP, intersections_passed, display_total, route_name)
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, BEFORE_TURN_DEGREES)
                    robot.drive_degrees(-TURN_SPEED, TURN_SPEED, UTURN_DEGREES)
                elif action == "pause":
                    robot.stop()
                    display.update("Pause", SERVER_IP, intersections_passed, display_total, route_name)
                    time.sleep(PAUSE_DELAY)
                    display.update("Moving", SERVER_IP, intersections_passed, display_total, route_name)
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, PASS_INTERSECTION_DEGREES)
                elif action == "stop":
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, 370)
                    robot.drive_degrees(-TURN_SPEED, TURN_SPEED, 370)
                    robot.stop()
                    break
                else:
                    # Неизвестное действие: безопасно едем прямо
                    robot.drive_degrees(BASE_SPEED, BASE_SPEED, PASS_INTERSECTION_DEGREES)
            else:
                # Проезжаем перекрёсток, чтобы не считать его повторно
                robot.drive_degrees(BASE_SPEED, BASE_SPEED, PASS_INTERSECTION_DEGREES)

                # Старое поведение для маршрутов без специальных сценариев
                if not route_actions and intersections_passed >= total_intersections:
                    break

        elif not is_intersection:
            # Покинули перекрёсток - сбрасываем флаг
            on_intersection = False

        # Движение по линии
        error = follower.read_error()
        turn = KP * error

        left_speed = BASE_SPEED - turn
        right_speed = BASE_SPEED + turn

        left_speed = follower.clamp(left_speed, -MAX_SPEED, MAX_SPEED)
        right_speed = follower.clamp(right_speed, -MAX_SPEED, MAX_SPEED)

        robot.drive(left_speed, right_speed)

    robot.stop()
    display.update("Finished", SERVER_IP, route_name=route_name)


def main():
    button = Button()

    # Инициализация робота (один раз)
    robot = Robot()
    follower = LineFollower()

    # Инициализация обновления дисплея в отдельном потоке
    display = DisplayUpdater()

    # Основной цикл работы
    while True:
        # Ждём набора заявок или нажатия кнопки
        route_name = ""
        route_index = None
        while True:
            try:
                routes = fetch_routes(SERVER_IP)
                leader_idx, leader_route = get_leader(routes)
                display.draw_waiting(routes, THRESHOLD_COUNT, SERVER_IP, leader_idx)

                # Проверка нажатия кнопки "вверх"
                if button.up and leader_route:
                    route_name = str(leader_route.get("name", "Unknown"))[:15]
                    route_index = leader_route.get("index")
                    display.draw_status("Manual start in 2s...", SERVER_IP)
                    time.sleep(2.0)
                    break

                # Проверка автоматического порога
                if check_threshold(routes, THRESHOLD_COUNT) and leader_route:
                    route_name = str(leader_route.get("name", "Unknown"))[:15]
                    route_index = leader_route.get("index")
                    break
            except (HTTPError, URLError, ValueError, Exception) as e:
                display.draw_error(SERVER_IP)

            time.sleep(REFRESH_SEC)

        # Показываем выбранный маршрут
        if route_name:
            display.draw_status("Starting {}".format(route_name), SERVER_IP)
            time.sleep(2.0)

        # Обнуляем заявки на выбранном маршруте
        if route_index is not None:
            reset_route(SERVER_IP, route_index)

        # Запускаем поток обновления дисплея перед началом движения
        display.start()

        # Движение по маршруту
        movement(robot, follower, display, button, route_name)

        # Останавливаем поток обновления после завершения движения
        display.stop()

        # Показываем финальный статус напрямую
        display.draw_status("Finished", SERVER_IP)

        # Задержка перед возвратом к ожиданию
        time.sleep(3.0)


if __name__ == "__main__":
    main()
