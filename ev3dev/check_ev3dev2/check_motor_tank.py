#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from time import sleep
from ev3dev2.motor import MoveTank, OUTPUT_B, OUTPUT_C, SpeedPercent
from ev3dev2.display import Display

lcd = Display()

b_state = "READY"
c_state = "READY"


def draw_screen(title="ROBOT MOVE"):
    lcd.text_grid(title, clear_screen=True, x=0, y=0, font="charB12")
    lcd.text_grid("B: " + b_state, clear_screen=False, x=0, y=3)
    lcd.text_grid("C: " + c_state, clear_screen=False, x=0, y=4)
    lcd.update()


def move_tank_deg(tank, deg_b, deg_c,
                  speed=30,
                  update_dt=0.05,
                  title="MOVE"):
    """
    Движение робота с контролем энкодеров
    """
    global b_state, c_state

    motor_b = tank.left_motor
    motor_c = tank.right_motor

    start_b = motor_b.position
    start_c = motor_c.position

    tank.on_for_degrees(
        SpeedPercent(speed),
        SpeedPercent(speed),
        degrees=max(abs(deg_b), abs(deg_c)),
        brake=True,
        block=False
    )

    # корректируем направление
    motor_b.polarity = "normal" if deg_b >= 0 else "inversed"
    motor_c.polarity = "normal" if deg_c >= 0 else "inversed"

    last_db = None
    last_dc = None

    while motor_b.is_running or motor_c.is_running:
        db = motor_b.position - start_b
        dc = motor_c.position - start_c

        changed = False

        if db != last_db:
            b_state = "{:+d} / {:+d}   ".format(db, deg_b)
            last_db = db
            changed = True

        if dc != last_dc:
            c_state = "{:+d} / {:+d}   ".format(dc, deg_c)
            last_dc = dc
            changed = True

        if changed:
            draw_screen(title)

        sleep(update_dt)

    b_state = "{:+d} / {:+d} DONE".format(db, deg_b)
    c_state = "{:+d} / {:+d} DONE".format(dc, deg_c)
    draw_screen(title)


def main():
    tank = MoveTank(OUTPUT_B, OUTPUT_C)

    SPEED = 35
    FWD = 720
    TURN = 220

    draw_screen("ROBOT MOVE (MoveTank)")
    sleep(0.5)

    # Движение вперёд
    move_tank_deg(tank, FWD, FWD, SPEED, title="FORWARD")
    sleep(0.5)

    # Движение влево
    move_tank_deg(tank, -TURN, TURN, SPEED, title="LEFT")
    sleep(0.5)

    # Движение назад
    move_tank_deg(tank, -FWD, -FWD, SPEED, title="BACK")
    sleep(0.5)

    # Движение вправо
    move_tank_deg(tank, TURN, -TURN, SPEED, title="RIGHT")
    sleep(0.5)

    # Разворот
    move_tank_deg(tank, 2 * TURN, -2 * TURN, SPEED, title="TURN AROUND")


if __name__ == "__main__":
    main()
