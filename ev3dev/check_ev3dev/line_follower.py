#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Движение по линии на 2 датчиках (левый/правый) для ev3dev.

Подключения:
- Моторы: B (левый), C (правый)
- Датчики отражения (ColorSensor в режиме COL-REFLECT): 2 (левый), 3 (правый)

Управление при старте:
- ▲ (Up)  — калибровка
- ● (Enter/Center) — запуск без калибровки
- ◀ Back — выход

Останов во время движения: Ctrl+C или Back (если запущено с блока/терминала с обработкой кнопки)
"""

import os
import time
from ev3dev.ev3 import (
    LargeMotor, OUTPUT_B, OUTPUT_C,
    ColorSensor, INPUT_2, INPUT_3,
    Button
)

def wait_release(btn, check_delay=0.01):
    """Ждём, пока пользователь отпустит все кнопки (анти-дребезг)"""
    while any(btn.buttons_pressed):
        time.sleep(check_delay)


def wait_enter_or_cancel(btn, enter_attr="enter", cancel_attr="left", check_delay=0.01):
    """
    Ждём нажатия ENTER (по умолчанию btn.enter) или CANCEL (по умолчанию btn.left).
    Возвращает True если ENTER, False если CANCEL.
    """
    wait_release(btn)
    while True:
        if getattr(btn, cancel_attr):
            time.sleep(0.05)
            wait_release(btn)
            return False
        if getattr(btn, enter_attr):
            time.sleep(0.05)
            wait_release(btn)
            return True
        time.sleep(check_delay)


def wait_for(btn, predicate, check_delay=0.01):
    """
    Ждём, пока выполнится predicate(btn),
    затем делаем debounce: дождаться отпускания кнопки
    """
    while True:
        if predicate(btn):
            time.sleep(0.05)
            wait_release(btn)
            return
        time.sleep(check_delay)


def show_menu_and_get_choice(btn):
    """
    Меню при запуске программы
    """
    os.system('clear')
    print("LINE FOLLOWER\n")
    print("MENU\n")
    print("UP       : Calibration")
    print("CENTER   : Run")
    print("LEFT     : Exit\n")

    # на всякий случай: если кнопка зажата при старте — подождать отпускания
    wait_release(btn)

    while True:
        if btn.up:
            time.sleep(0.05)
            wait_release(btn)
            return "calibrate"
        if btn.enter:
            time.sleep(0.05)
            wait_release(btn)
            return "run"
        if btn.left:
            time.sleep(0.05)
            wait_release(btn)
            return "exit"
        time.sleep(0.01)


class DifferentialDrive:
    def __init__(self, left_port=OUTPUT_B, right_port=OUTPUT_C):
        self.left = LargeMotor(left_port)
        self.right = LargeMotor(right_port)

        if not self.left.connected or not self.right.connected:
            raise RuntimeError("Motors must be connected to B and C")

        self.left.stop_action = "brake"
        self.right.stop_action = "brake"

        self.stop()

    def stop(self):
        self.left.stop(stop_action="brake")
        self.right.stop(stop_action="brake")

    def drive(self, left_speed, right_speed):
        """
        Непрерывная езда. Скорость указывается в градусах/сек (deg/s)
        и может быть отрицательной при движении назад
        """
        self.left.run_forever(speed_sp=int(left_speed))
        self.right.run_forever(speed_sp=int(right_speed))


class LineFollowerTwoSensors:
    def __init__(self,
                 left_sensor_port=INPUT_2,
                 right_sensor_port=INPUT_3,
                 base_speed=250,
                 kp=3.0,
                 max_speed=700,
                 print_interval=0.1):
        self.base_speed = base_speed
        self.kp = kp
        self.max_speed = max_speed
        self.print_interval = print_interval

        self.left = ColorSensor(left_sensor_port)
        self.right = ColorSensor(right_sensor_port)

        if not self.left.connected or not self.right.connected:
            raise RuntimeError("Sensors must be connected to ports 2 and 3")

        self.left.mode = 'COL-REFLECT'
        self.right.mode = 'COL-REFLECT'

        # Значения калибровки
        self.l_white = 98
        self.l_black = 8
        self.r_white = 98
        self.r_black = 8

    @staticmethod
    def _clamp(x, lo, hi):
        """Ограничение значения в диапазоне [lo, hi]"""
        return lo if x < lo else hi if x > hi else x

    def _norm_reflect(self, raw, black, white):
        """
        Нормируем отражение в диапазон 0..100, чтобы левый/правый датчики
        сравнивались честнее, даже если у них разные "сырые" значения.
        """
        if white == black:
            return 0.0
        v = (raw - black) * 100.0 / (white - black)
        return self._clamp(v, 0.0, 100.0)

    def calibrate_simple(self, btn):
        """
        Простая калибровка:
        - положи оба датчика на белое и нажми Enter
        - положи оба датчика на чёрную линию и нажми Enter
        """
        os.system('clear')
        print("CALIBRATION")
        print("CANCEL to abort\n")

        print("WHITE area...")
        if not wait_enter_or_cancel(btn):
            print("\nCalibration canceled")
            time.sleep(0.5)
            return False

        self.l_white = self.left.value()
        self.r_white = self.right.value()
        print("WHITE: L=%d  R=%d" % (self.l_white, self.r_white))

        print("BLACK line...")
        if not wait_enter_or_cancel(btn):
            print("\nCalibration canceled")
            time.sleep(0.5)
            return False

        self.l_black = self.left.value()
        self.r_black = self.right.value()
        print("BLACK: L=%d  R=%d" % (self.l_black, self.r_black))

        # На случай если пользователь перепутал белое/чёрное (бывает)
        if self.l_black > self.l_white:
            self.l_black, self.l_white = self.l_white, self.l_black
        if self.r_black > self.r_white:
            self.r_black, self.r_white = self.r_white, self.r_black

        print("DONE")
        time.sleep(0.7)
        return True

    def read_error(self):
        """
        Возвращает ошибку (L - R) в "нормализованных процентах" и сырые значения датчиков.
        0..100% — нормализованное отражение (0 — чёрное, 100 — белое)
        """
        l_raw = self.left.value()
        r_raw = self.right.value()

        l = self._norm_reflect(l_raw, self.l_black, self.l_white)
        r = self._norm_reflect(r_raw, self.r_black, self.r_white)

        return (l - r), l_raw, r_raw, l, r


def main():
    # Настройка консоли для отображения текста
    os.system('setfont Lat15-TerminusBold16')
    os.system('clear')

    btn = Button()

    robot = DifferentialDrive()
    follower = LineFollowerTwoSensors(
        base_speed=260,     # базовая скорость (подбирай)
        kp=3.2,             # усиление поворота (подбирай)
        max_speed=800,      # ограничение скорости
        print_interval=0.1  # частота вывода
    )

    while True:
        choice = show_menu_and_get_choice(btn)

        if choice == "exit":
            os.system('clear')
            print("Goodbye!")
            time.sleep(1)
            return

        if choice == "calibrate":
            follower.calibrate_simple(btn)
            continue

        if choice == "run":
            # Запускаем движение
            break

    os.system('clear')
    print("RUN\n")

    last_print = 0.0

    try:
        while True:
            error, l_raw, r_raw, l_norm, r_norm = follower.read_error()

            # Пропорциональный регулятор
            turn = follower.kp * error

            left_speed = follower.base_speed - turn
            right_speed = follower.base_speed + turn

            # Ограничение
            left_speed = follower._clamp(left_speed, -follower.max_speed, follower.max_speed)
            right_speed = follower._clamp(right_speed, -follower.max_speed, follower.max_speed)

            robot.drive(left_speed, right_speed)

            # Печать состояния
            now = time.time()
            if now - last_print >= follower.print_interval:
                last_print = now
                print("\rL = %3.1f R = %3.1f" % (l_norm, r_norm), end="")

            time.sleep(0.01)

    except KeyboardInterrupt:
        pass
    finally:
        robot.stop()
        print("\nStopped")


if __name__ == "__main__":
    main()
