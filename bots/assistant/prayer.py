#!/usr/bin/env python3
"""Время намаза для Алматы (офлайн расчёт, без интернета).
Параметры: Фаджр 18°, Иша 17°, Аср по Ханафи (тень x2). Сверяйте с ДУМК и при расхождении правьте углы ниже.
Использование: prayer.py [YYYY-MM-DD]"""
import sys, math, datetime as dt

LAT, LON, TZ = 43.2389, 76.8897, 5.0
FAJR, ISHA, ASR_FACTOR = 18.0, 17.0, 2
rad, deg = math.radians, math.degrees

def sun(jd):
    d = jd - 2451545.0
    g = (357.529 + 0.98560028 * d) % 360
    q = (280.459 + 0.98564736 * d) % 360
    L = (q + 1.915 * math.sin(rad(g)) + 0.020 * math.sin(rad(2 * g))) % 360
    e = 23.439 - 0.00000036 * d
    ra = deg(math.atan2(math.cos(rad(e)) * math.sin(rad(L)), math.cos(rad(L)))) / 15 % 24
    decl = deg(math.asin(math.sin(rad(e)) * math.sin(rad(L))))
    eqt = q / 15 - ra
    eqt = (eqt + 12) % 24 - 12
    return decl, eqt

def hour_angle(angle, decl):
    x = (-math.sin(rad(angle)) - math.sin(rad(LAT)) * math.sin(rad(decl))) / (math.cos(rad(LAT)) * math.cos(rad(decl)))
    return deg(math.acos(max(-1, min(1, x)))) / 15

def times(day):
    jd = day.toordinal() + 1721424.5
    decl, eqt = sun(jd + 0.5 - TZ / 24)
    noon = 12 + TZ - LON / 15 - eqt
    asr_angle = -deg(math.atan(1 / (ASR_FACTOR + math.tan(rad(abs(LAT - decl))))))
    t = {
        "Таң (Фаджр)": noon - hour_angle(FAJR, decl),
        "Күн шығуы": noon - hour_angle(0.833, decl),
        "Бесін (Зухр)": noon + 2 / 60,
        "Екінті (Аср)": noon + hour_angle(asr_angle, decl),
        "Ақшам (Магриб)": noon + hour_angle(0.833, decl),
        "Құфтан (Иша)": noon + hour_angle(ISHA, decl),
    }
    return {k: "%02d:%02d" % divmod(int(round(v * 60)), 60) for k, v in t.items()}

if __name__ == "__main__":
    day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    for k, v in times(day).items():
        print(f"{v}  {k}")
