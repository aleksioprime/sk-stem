#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from time import sleep
from ev3dev2.sensor.lego import ColorSensor
from ev3dev2.sensor import INPUT_2, INPUT_3
from ev3dev2.display import Display

lcd = Display()


def draw(v2, v3):
    lcd.text_grid("LINE SENSORS", clear_screen=True, x=0, y=0, font="charB12")
    lcd.text_grid("S2: {:>3d}".format(v2), clear_screen=False, x=0, y=3)
    lcd.text_grid("S3: {:>3d}".format(v3), clear_screen=False, x=0, y=4)
    lcd.text_grid("Mode: REFLECT", clear_screen=False, x=0, y=6)
    lcd.update()


def main():
    s2 = ColorSensor(INPUT_2)
    s3 = ColorSensor(INPUT_3)

    # Режим "отражённый свет" — классика для линии (0..100)
    s2.mode = 'COL-REFLECT'
    s3.mode = 'COL-REFLECT'

    draw(0, 0)
    sleep(0.5)

    while True:
        v2 = s2.value()
        v3 = s3.value()
        draw(v2, v3)
        sleep(0.05)  # ~20 обновлений/сек


if __name__ == "__main__":
    main()
