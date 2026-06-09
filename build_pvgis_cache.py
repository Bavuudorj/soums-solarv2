"""
PVGIS API-аас бүх сумдын байрлал дээр нарны өгөгдлийг ТАТАЖ, дотоод статик файл
(pvgis_data.json) болгож хадгална. Энэ скриптийг НЭГ УДАА ажиллуулна:

    python build_pvgis_cache.py

Дараа нь үндсэн апп PVGIS API руу шууд хандахгүй — энэ статик файлаас уншина.
soums_v2.xlsx эсвэл байршил өөрчлөгдвөл дахин ажиллуулна.
"""

import os
import sys
import json
import time

from network import load_soums, load_lines, build_node_info
from pvgis import fetch_pvgis_hourly, STATIC_PATH, ROUND_DEG

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def main(soums_path="soums_v2.xlsx", lines_path="lines_v2.xlsx", out=STATIC_PATH):
    info = build_node_info(load_soums(soums_path), load_lines(lines_path))

    # Координатыг ROUND_DEG нарийвчлалаар бүлэглэж өвөрмөц цэгүүд гаргана
    cells = {}
    for v in info.values():
        if v.get('lat') is None or v.get('lon') is None:
            continue
        key = f"{round(v['lat'], ROUND_DEG)},{round(v['lon'], ROUND_DEG)}"
        cells.setdefault(key, (round(v['lat'], ROUND_DEG), round(v['lon'], ROUND_DEG)))

    # Өмнө татсан өгөгдлийг ачаалж, дутууг нь л татна (incremental)
    data = {}
    if os.path.exists(out):
        try:
            with open(out, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
    todo = {k: v for k, v in cells.items() if k not in data}
    print(f"Нийт {len(cells)} цэг | татсан {len(data)} | татах {len(todo)} (0.1°)")
    ok = len(data)
    for i, (key, (lat, lon)) in enumerate(todo.items(), 1):
        profiles = None
        for attempt in range(3):                 # rate-limit-д дахин оролдоно
            try:
                profiles = fetch_pvgis_hourly(lat, lon)
                break
            except Exception as e:
                last = str(e)[:60]
                time.sleep(1.0 + attempt * 1.5)
        if profiles is not None:
            data[key] = profiles
            ok += 1
            print(f"  [{i}/{len(todo)}] {key}  OK")
        else:
            print(f"  [{i}/{len(todo)}] {key}  АЛДАА: {last}")
        time.sleep(0.25)                          # PVGIS-д эелдэг хандах
        if i % 25 == 0:                           # завсрын хадгалалт
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(data, f)

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f"\nХадгалсан: {out} — {ok}/{len(cells)} цэг амжилттай")


if __name__ == '__main__':
    main()
