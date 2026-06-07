"""
Block 1 (3.2) — Цаг тутмын эрэлтийн профайл.

soum_load_profile.xlsx (8760 цаг, оргилд нормчлогдсон Load_Factor)-аас
4 улирлын төлөөлөх өдрийг (улирал бүрийн дундаж 24 цагийн профайл) гаргана.

  Эрэлт:  D_{i,s,t} = P_pk_i · LF_s(t)      [кВт]
  Жин:    w_s = тухайн улирлын өдрийн тоо   (жилийн нийт = 365)
"""

import pandas as pd

SEASONS = ['Өвөл', 'Хавар', 'Зун', 'Намар']


def _season_of_day(d):
    if d <= 59 or d >= 335:      # 12,1,2 сар
        return 'Өвөл'
    if d <= 151:                 # 3,4,5 сар
        return 'Хавар'
    if d <= 243:                 # 6,7,8 сар
        return 'Зун'
    return 'Намар'               # 9,10,11 сар


def load_demand_profiles(path='soum_load_profile.xlsx'):
    """
    Буцаах: (rep, weights)
      rep[season] = [24 утга]  — оргилын эзлэх хувь (0..1)
      weights[season] = тухайн улирлын өдрийн тоо
    """
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    lf_col = next((c for c in df.columns if 'load' in c.lower() or 'factor' in c.lower()), df.columns[0])
    day_col = next((c for c in df.columns if c.lower().startswith('day')), 'Day')
    hour_col = next((c for c in df.columns if c.lower().startswith('hour')), 'Hour')

    df['_season'] = df[day_col].apply(_season_of_day)
    rep, weights = {}, {}
    for s in SEASONS:
        sub = df[df['_season'] == s]
        weights[s] = int(sub[day_col].nunique())
        prof = sub.groupby(hour_col)[lf_col].mean().reindex(range(24)).fillna(0.0)
        rep[s] = [float(v) for v in prof.values]
    return rep, weights


def synthetic_demand_profiles():
    """Файл байхгүй үеийн нөөц — хөдөөгийн оройн оргилтой энгийн профайл."""
    base = [0.45, 0.40, 0.38, 0.38, 0.40, 0.48, 0.60, 0.70, 0.68, 0.62,
            0.58, 0.60, 0.62, 0.60, 0.58, 0.60, 0.70, 0.85, 1.00, 0.95,
            0.85, 0.72, 0.60, 0.50]
    factor = {'Өвөл': 1.0, 'Хавар': 0.85, 'Зун': 0.75, 'Намар': 0.88}
    rep = {s: [min(v * f, 1.0) for v in base] for s, f in factor.items()}
    weights = {'Өвөл': 90, 'Хавар': 92, 'Зун': 92, 'Намар': 91}
    return rep, weights
