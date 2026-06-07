"""
Агаарын шугамын нэвтрүүлэх чадварыг хүчдэлийн түвшин ба уртаас тооцоолох.

Хэрэглэх чадвар T нь гурван физик хязгаарын хамгийн багатай тэнцэнэ:
    T = min( P_дулаан , P_хүчдэлийн_уналт , P_SIL )

  • Дулааны (ampacity):   P_th = √3 · U · I_max · cosφ
  • Хүчдэлийн уналт:       P_ΔU = 10 · ΔU_max · U² / ( l · (r + x·tanφ) )
  • SIL/тогтворжилт:        P_SIL = k(l) · U²/Z_c · 1000   (St. Clair ачааллаж чадвар)

Энд U [кВ], l [км], I_max [A], r,x [Ω/км]; үр дүн [кВт].
Эх сурвалж: цахилгаан дамжуулах шугамын дамжуулах чадварын стандарт аргачлал.
"""

import math
from dataclasses import dataclass


# Хүчдэлийн түвшин -> (I_max [A], r [Ω/км], x [Ω/км]) — ердийн ACSR дамжуулагч.
# Бодит утгыг шугамын паспортоор солиж болно.
CONDUCTORS = {
    6:   (210, 0.60, 0.40),   # AC-50
    10:  (210, 0.60, 0.40),   # AC-50
    15:  (210, 0.60, 0.40),   # AC-50
    35:  (265, 0.43, 0.41),   # AC-70
    110: (380, 0.25, 0.41),   # AC-120
}


@dataclass
class GridParams:
    cos_phi: float = 0.9        # Чадварын коэффициент
    dU_max: float = 6.0         # Зөвшөөрөгдөх хүчдэлийн уналт, %
    Zc: float = 400.0           # Долгионы (surge) эсэргүүцэл, Ω
    default_length_km: float = 40.0   # Урт тодорхойгүй үеийн анхны утга


def _conductor_for(kv):
    if kv in CONDUCTORS:
        return CONDUCTORS[kv]
    nearest = min(CONDUCTORS, key=lambda lv: abs(lv - kv))
    return CONDUCTORS[nearest]


def _stclair_factor(length_km):
    """St. Clair муруйн ачааллаж чадварын ойролцоо коэффициент (SIL-ийн үржвэр)."""
    if length_km <= 80:
        return 3.0
    if length_km >= 300:
        return 1.0
    return 3.0 + (1.0 - 3.0) * (length_km - 80.0) / (300.0 - 80.0)


def line_capacity_kw(voltage_kv, length_km, p: GridParams = None, breakdown=False):
    """
    Шугамын нэвтрүүлэх чадварыг кВт-аар буцаана.
    Хүчдэл тодорхойгүй бол None (тооцох боломжгүй -> хүрэлцэнэ гэж үзнэ).
    breakdown=True үед (T, {p_th, p_du, p_sil, binding}) задаргааг буцаана.
    """
    if p is None:
        p = GridParams()
    if voltage_kv is None or (isinstance(voltage_kv, float) and math.isnan(voltage_kv)) or voltage_kv <= 0:
        return (None, None) if breakdown else None

    U = float(voltage_kv)
    Imax, r, x = _conductor_for(U)
    tan_phi = math.tan(math.acos(max(min(p.cos_phi, 1.0), 1e-6)))

    # Дулааны хязгаар
    p_th = math.sqrt(3) * U * Imax * p.cos_phi

    # Урт
    l = float(length_km) if (length_km is not None and not (isinstance(length_km, float) and math.isnan(length_km)) and length_km > 0) else p.default_length_km

    # Хүчдэлийн уналтын хязгаар
    denom = l * (r + x * tan_phi)
    p_du = (10.0 * p.dU_max * U ** 2) / denom if denom > 0 else math.inf

    # SIL хязгаар (St. Clair)
    p_sil = _stclair_factor(l) * (U ** 2 / p.Zc) * 1000.0

    limits = {'дулаан': p_th, 'хүчдэлийн_уналт': p_du, 'SIL': p_sil}
    binding = min(limits, key=limits.get)
    T = limits[binding]

    if breakdown:
        return T, {'p_th': p_th, 'p_du': p_du, 'p_sil': p_sil, 'binding': binding}
    return T
