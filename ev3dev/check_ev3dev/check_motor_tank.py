#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
from ev3dev.ev3 import LargeMotor, OUTPUT_B, OUTPUT_C


class DifferentialDrive:
    def __init__(self, left_port=OUTPUT_B, right_port=OUTPUT_C):
        self.left = LargeMotor(left_port)
        self.right = LargeMotor(right_port)

        if not self.left.connected or not self.right.connected:
            raise RuntimeError("Motors must be connected to B and C")

        self.stop()

    def stop(self):
        self.left.stop(stop_action="brake")
        self.right.stop(stop_action="brake")

    def _run_rel(self, left_deg, right_deg, speed=300):
        """Повернуть моторы на относительные углы"""
        self.left.run_to_rel_pos(
            position_sp=left_deg,
            speed_sp=abs(speed),
            stop_action="brake"
        )

        self.right.run_to_rel_pos(
            position_sp=right_deg,
            speed_sp=abs(speed),
            stop_action="brake"
        )

        self.left.wait_while("running")
        self.right.wait_while("running")

    def forward(self, degrees, speed=300):
        """Движение вперёд"""
        self._run_rel(degrees, degrees, speed)

    def backward(self, degrees, speed=300):
        """Движение назад"""
        self._run_rel(-degrees, -degrees, speed)

    def turn_left(self, degrees, speed=250):
        """Поворот на месте влево"""
        self._run_rel(-degrees, degrees, speed)

    def turn_right(self, degrees, speed=250):
        """Поворот на месте вправо"""
        self._run_rel(degrees, -degrees, speed)

    def curve(self, left_deg, right_deg, speed=300):
        """Плавный поворот"""
        self._run_rel(left_deg, right_deg, speed)


def main():
    # Настройка консоли для отображения текста
    os.system('setfont Lat15-TerminusBold16')

    print("CHECK MOTOR DIFF\n")

    robot = DifferentialDrive()

    print("Forward")
    robot.forward(720)
    time.sleep(0.5)

    print("Turn left")
    robot.turn_left(360)
    time.sleep(0.5)

    print("Forward")
    robot.forward(360)
    time.sleep(0.5)

    print("Turn right")
    robot.turn_right(360)
    time.sleep(0.5)

    print("Backward")
    robot.backward(360)

    robot.stop()
    print("Done")


if __name__ == "__main__":
    main()
