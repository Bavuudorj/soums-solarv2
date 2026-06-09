"""
Нарны үйлдвэрлэлийн цаг тутмын коэффициент (capacity factor) ĝ_t.

  • fetch_pvgis_hourly(lat, lon)      — PVGIS API-аас 1 кВт суурилуулсан системийн
                                         цаг тутмын гаралтыг (кВт/кВт) татна.
  • seasonal_solar_profiles(lat, lon) — 4 улирлын дундаж 24 цагийн профайл.
                                         Кэштэй; API амжилтгүй бол офлайн загвар.

ĝ_t тийм нэгжтэй: ∑_t ĝ_t (24ц) ≈ өдрийн нарны эрчим [кВт·ц/кВт] (PSH-тэй дүйцнэ).
"""

import os
import json
import math

try:
    import requests
except Exception:
    requests = None

from profiles import SEASONS

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
CACHE_PATH = "pvgis_cache.json"
STATIC_PATH = "pvgis_data.json"   # build_pvgis_cache.py-аар нэг удаа үүсгэсэн статик өгөгдөл
ROUND_DEG = 1                     # координат бүлэглэх нарийвчлал (0.1°)

# Монголд тохирсон улирлын нарны эрчим (кВт·ц/кВт/өдөр, офлайн загварт)
SEASON_PSH = {'Өвөл': 2.8, 'Хавар': 4.8, 'Зун': 6.0, 'Намар': 4.0}
SEASON_DAYLIGHT = {'Өвөл': 9.0, 'Хавар': 12.5, 'Зун': 15.0, 'Намар': 11.0}


def _season_of_month(month):
    if month in (12, 1, 2):
        return 'Өвөл'
    if month in (3, 4, 5):
        return 'Хавар'
    if month in (6, 7, 8):
        return 'Зун'
    return 'Намар'


def fetch_pvgis_hourly(lat, lon, angle=35, aspect=0, loss=14, timeout=30):
    """
    PVGIS-аас 1 кВтp системийн цаг тутмын гаралтыг татаж,
    {season: [24 дундаж CF]} буцаана. Алдаа гарвал ValueError шиднэ.
    """
    if requests is None:
        raise RuntimeError("requests сан байхгүй байна.")
    params = {
        'lat': lat, 'lon': lon, 'pvcalculation': 1, 'peakpower': 1,
        'loss': loss, 'angle': angle, 'aspect': aspect, 'outputformat': 'json',
    }
    resp = requests.get(PVGIS_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    hourly = resp.json()['outputs']['hourly']

    sums = {s: [0.0] * 24 for s in SEASONS}
    cnts = {s: [0] * 24 for s in SEASONS}
    for rec in hourly:
        ts = str(rec['time'])           # "20200101:0010"
        month = int(ts[4:6])
        hour = int(ts[9:11])
        cf = float(rec['P']) / 1000.0   # W -> кВт/кВтp
        s = _season_of_month(month)
        sums[s][hour] += cf
        cnts[s][hour] += 1
    profiles = {}
    for s in SEASONS:
        profiles[s] = [sums[s][h] / cnts[s][h] if cnts[s][h] else 0.0 for h in range(24)]
    return profiles


def synthetic_solar_profiles(lat=47.0):
    """Офлайн нарны загвар — өдрийн гэрэлт цагт төвлөрсөн хагас-синус муруй."""
    profiles = {}
    for s in SEASONS:
        psh = SEASON_PSH[s]
        daylight = SEASON_DAYLIGHT[s]
        start = 12.0 - daylight / 2.0
        end = 12.0 + daylight / 2.0
        shape = []
        for h in range(24):
            hc = h + 0.5
            if start <= hc <= end:
                shape.append(math.sin(math.pi * (hc - start) / daylight))
            else:
                shape.append(0.0)
        ssum = sum(shape)
        profiles[s] = [(v / ssum) * psh if ssum > 0 else 0.0 for v in shape]
    return profiles


def _load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception:
        pass


_STATIC = None


def _get_static(path=STATIC_PATH):
    """Урьдчилан татсан PVGIS статик өгөгдлийг нэг удаа ачаалж кэшэлнэ."""
    global _STATIC
    if _STATIC is None:
        _STATIC = _load_cache(path)
    return _STATIC


def seasonal_solar_profiles(lat, lon, use_api=False):
    """
    {season: [24 CF]} буцаана.
      use_api=True : дотоод статик файлаас (build_pvgis_cache.py-аар татсан PVGIS).
                     Тухайн цэг файлд байхгүй бол офлайн загвар руу шилжинэ.
      use_api=False: офлайн (синтетик) загвар.
    Үндсэн апп ШУУД PVGIS API руу хандахгүй (хугацаа/нөөц хэмнэх).
    """
    if use_api:
        data = _get_static()
        key = f"{round(lat, ROUND_DEG)},{round(lon, ROUND_DEG)}"
        if key in data:
            return {s: data[key][s] for s in SEASONS}
        # Статик файлд байхгүй бол — синтетик нөөц
    return synthetic_solar_profiles(lat)
