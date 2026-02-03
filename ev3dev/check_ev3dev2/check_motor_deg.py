#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from time import sleep
from ev3dev2.motor import LargeMotor, OUTPUT_B, OUTPUT_C, SpeedPercent
from ev3dev2.display import Display

lcd = Display()

b_state = "READY"
c_state = "READY"

def draw_screen():
    lcd.text_grid("CHECK MOTOR DEGREES", clear_screen=True, x=0, y=0, font="charB12")
    lcd.text_grid("B: " + b_state, clear_screen=False, x=0, y=3)
    lcd.text_grid("C: " + c_state, clear_screen=False, x=0, y=4)
    lcd.update()


def rotate_motor_deg(motor, degrees, label,
                     speed_percent=30, brake=True, update_dt=0.01):
    """
    Крутит мотор и обновляет соответствующую строку на экране
    """
    global b_state, c_state

    start_pos = motor.position

    motor.on_for_degrees(
        speed=SpeedPercent(int(speed_percent)),
        degrees=int(degrees),
        brake=bool(brake),
        block=False,
    )

    last_delta = None

    while motor.is_running:
        delta = motor.position - start_pos

        # обновляем только если значение изменилось
        if delta != last_delta:
            # пробелы в конце нужны, чтобы затирать "хвост" старой строки
            txt = "{:+d}     ".format(delta)

            if label == "B":
                b_state = txt
            else:
                c_state = txt

            draw_screen()
            last_delta = delta

        sleep(update_dt)

    final_delta = motor.position - start_pos
    final_txt = "{:+d} / {:+d}   ".format(final_delta, degrees)

    if label == "B":
        b_state = final_txt
    else:
        c_state = final_txt

    draw_screen()
    return final_delta


def main():
    motor_b = LargeMotor(OUTPUT_B)
    motor_c = LargeMotor(OUTPUT_C)

    draw_screen()
    sleep(0.5)

    rotate_motor_deg(motor_b, 360, label="B", update_dt=0.05)
    sleep(0.5)

    rotate_motor_deg(motor_c, -180, label="C", update_dt=0.05)
    sleep(0.5)


if __name__ == "__main__":
    main()
