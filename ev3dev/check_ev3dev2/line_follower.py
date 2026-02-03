#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Движение по линии на 2 датчиках (левый/правый) для ev3dev2
"""

import time
from ev3dev2.motor import LargeMotor, OUTPUT_B, OUTPUT_C
from ev3dev2.sensor.lego import ColorSensor
from ev3dev2.sensor import INPUT_2, INPUT_3
from ev3dev2.button import Button
from ev3dev2.display import Display

lcd = Display()
btn = Button()

def draw_menu():
    lcd.text_grid("LINE FOLLOWER", clear_screen=True, x=0, y=0, font="charB12")
    lcd.text_grid("UP: Calibrate", clear_screen=False, x=0, y=2)
    lcd.text_grid("ENT: Run",      clear_screen=False, x=0, y=3)
    lcd.text_grid("BACK: Exit",    clear_screen=False, x=0, y=4)
    lcd.update()

def draw_msg(lines):
    lcd.text_grid(lines[0] if len(lines) > 0 else "", clear_screen=True, x=0, y=0, font="charB12")
    for i in range(1, len(lines)):
        lcd.text_grid(lines[i], clear_screen=False, x=0, y=i+1)
    lcd.update()

def wait_release(delay=0.01):
    while btn.any():
        time.sleep(delay)

def wait_enter_or_back():
    wait_release()
    while True:
        if btn.backspace:
            time.sleep(0.05)
            wait_release()
            return False
        if btn.enter:
            time.sleep(0.05)
            wait_release()
            return True
        time.sleep(0.01)

def get_menu_choice():
    wait_release()
    while True:
        if btn.up:
            time.sleep(0.05); wait_release()
            return "calibrate"
        if btn.enter:
            time.sleep(0.05); wait_release()
            return "run"
        if btn.backspace:
            time.sleep(0.05); wait_release()
            return "exit"
        time.sleep(0.01)


class DifferentialDrive(object):
    def __init__(self, left_port=OUTPUT_B, right_port=OUTPUT_C):
        self.left = LargeMotor(left_port)
        self.right = LargeMotor(right_port)
        self.stop_action = 'brake'
        self.stop()

    def stop(self):
        self.left.stop(stop_action=self.stop_action)
        self.right.stop(stop_action=self.stop_action)

    def drive(self, left_speed_dps, right_speed_dps):
        # dps = degrees per second (как speed_sp в ev3dev v1)
        self.left.run_forever(speed_sp=int(left_speed_dps))
        self.right.run_forever(speed_sp=int(right_speed_dps))


class LineFollowerTwoSensors(object):
    def __init__(self,
                 left_sensor_port=INPUT_2,
                 right_sensor_port=INPUT_3,
                 base_speed=260,
                 kp=3.2,
                 max_speed=800):

        self.base_speed = float(base_speed)
        self.kp = float(kp)
        self.max_speed = float(max_speed)

        self.left = ColorSensor(left_sensor_port)
        self.right = ColorSensor(right_sensor_port)

        # режим отражения
        self.left.mode = 'COL-REFLECT'
        self.right.mode = 'COL-REFLECT'

        # дефолтная калибровка (подстроишь)
        self.l_white = 90
        self.l_black = 10
        self.r_white = 90
        self.r_black = 10

    @staticmethod
    def clamp(x, lo, hi):
        return lo if x < lo else hi if x > hi else x

    def norm_reflect(self, raw, black, white):
        if white == black:
            return 0.0
        v = (raw - black) * 100.0 / (white - black)
        return self.clamp(v, 0.0, 100.0)

    def read_error(self):
        l_raw = int(self.left.value())
        r_raw = int(self.right.value())

        l = self.norm_reflect(l_raw, self.l_black, self.l_white)
        r = self.norm_reflect(r_raw, self.r_black, self.r_white)

        return (l - r), l_raw, r_raw, l, r

    def calibrate_simple(self):
        draw_msg([
            "CALIBRATION",
            "",
            "WHITE -> ENTER",
            "BACK to cancel"
        ])
        if not wait_enter_or_back():
            draw_msg(["CANCELED"])
            time.sleep(0.6)
            return False

        self.l_white = int(self.left.value())
        self.r_white = int(self.right.value())

        draw_msg([
            "CALIBRATION",
            "WHITE: L=%d R=%d" % (self.l_white, self.r_white),
            "",
            "BLACK -> ENTER",
            "BACK to cancel"
        ])
        if not wait_enter_or_back():
            draw_msg(["CANCELED"])
            time.sleep(0.6)
            return False

        self.l_black = int(self.left.value())
        self.r_black = int(self.right.value())

        # если перепутали белое/чёрное
        if self.l_black > self.l_white:
            self.l_black, self.l_white = self.l_white, self.l_black
        if self.r_black > self.r_white:
            self.r_black, self.r_white = self.r_white, self.r_black

        draw_msg([
            "DONE",
            "L: B=%d W=%d" % (self.l_black, self.l_white),
            "R: B=%d W=%d" % (self.r_black, self.r_white)
        ])
        time.sleep(0.9)
        return True

def main():
    robot = DifferentialDrive()
    follower = LineFollowerTwoSensors(
        base_speed=260,
        kp=3.2,
        max_speed=800
    )

    while True:
        draw_menu()
        choice = get_menu_choice()

        if choice == "exit":
            draw_msg(["GOODBYE"])
            time.sleep(0.8)
            return

        if choice == "calibrate":
            follower.calibrate_simple()
            continue

        if choice == "run":
            break

    draw_msg(["RUN", "BACK to stop"])
    time.sleep(0.3)

    try:
        last_draw = 0.0
        while True:
            if btn.backspace:
                break

            error, l_raw, r_raw, l_norm, r_norm = follower.read_error()

            turn = follower.kp * error
            left_speed = follower.base_speed - turn
            right_speed = follower.base_speed + turn

            left_speed = follower.clamp(left_speed, -follower.max_speed, follower.max_speed)
            right_speed = follower.clamp(right_speed, -follower.max_speed, follower.max_speed)

            robot.drive(left_speed, right_speed)

            # обновляем экран ~10 раз/сек (чтобы не тормозило)
            now = time.time()
            if now - last_draw >= 0.10:
                last_draw = now
                lcd.text_grid("RUN", clear_screen=True, x=0, y=0, font="charB12")
                lcd.text_grid("L: %5.1f  (%3d)" % (l_norm, l_raw), clear_screen=False, x=0, y=2)
                lcd.text_grid("R: %5.1f  (%3d)" % (r_norm, r_raw), clear_screen=False, x=0, y=3)
                lcd.text_grid("ERR: %6.1f" % (error), clear_screen=False, x=0, y=4)
                lcd.text_grid("BACK: stop", clear_screen=False, x=0, y=6)
                lcd.update()

            time.sleep(0.01)

    except KeyboardInterrupt:
        pass
    finally:
        robot.stop()
        draw_msg(["STOPPED"])
        time.sleep(0.7)


if __name__ == "__main__":
    main()
