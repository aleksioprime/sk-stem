#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import os
from ev3dev.ev3 import ColorSensor, INPUT_2, INPUT_3


def main():
    # Настройка консоли для отображения текста
    os.system('setfont Lat15-TerminusBold16')
    os.system('clear')

    left = ColorSensor(INPUT_2)
    right = ColorSensor(INPUT_3)

    if not left.connected or not right.connected:
        print("ERROR: sensors not connected to ports 2 and 3")
        return

    left.mode = 'COL-REFLECT'
    right.mode = 'COL-REFLECT'

    print("LINE SENSORS\n")

    try:
        while True:
            l = left.value()
            r = right.value()

            # \r — возвращаем курсор в начало строки для перезаписи
            print("\rL=%3d   R=%3d   " % (l, r), end="")
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
