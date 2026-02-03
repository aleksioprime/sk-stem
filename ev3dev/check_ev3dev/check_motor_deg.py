#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from ev3dev.ev3 import LargeMotor, OUTPUT_B, OUTPUT_C


def rotate_motor_deg(port, degrees, speed=300, brake=True):
    """
    Повернуть LargeMotor на заданное количество градусов (encoder-based)
    """
    m = LargeMotor(port)
    if not m.connected:
        raise RuntimeError("Motor on %s not connected" % port)

    stop_action = "brake" if brake else "coast"

    start_pos = m.position

    m.run_to_rel_pos(
        position_sp=degrees,
        speed_sp=abs(speed),
        stop_action=stop_action
    )

    m.wait_while("running")

    return m.position - start_pos


def main():
    # Настройка консоли для отображения текста
    os.system('setfont Lat15-TerminusBold16')

    print("CHECK MOTOR DEGREES\n")

    print("B: +360 deg")
    delta = rotate_motor_deg(OUTPUT_B, 360)
    print("Actual:", delta)

    print("C: -180 deg")
    delta = rotate_motor_deg(OUTPUT_C, -180)
    print("Actual:", delta)


if __name__ == "__main__":
    main()