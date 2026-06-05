"""
Нарны систем + батарейн хэмжээ, өртгийн тооцоолол.

Загвар: Хэрэглээ нь оргил чадал (кВт) бөгөөд өдөрт 24 цаг ажиллана гэж үзнэ.
  Өдрийн эрчим хүч  E = load_kw * 24  (кВт·ц/өдөр)
  Нарны чадал       PV_kWp = E / (PSH * PR)
  Батарей           Battery_kWh = E * autonomy / (DoD * batt_eff)
  Өртөг             тогтмол суурь зардал + (PV + батарей) * угсралтын коэф
"""

import math
from dataclasses import dataclass


@dataclass
class Assumptions:
    """Тооцооллын таамаглалууд (Streamlit-аас тохируулж болно)."""
    psh: float = 4.5                 # Нар ашиглалт, цаг/өдөр (Монголын дундаж)
    performance_ratio: float = 0.75  # Системийн нийт ашиг (инвертер, дулаан, тоос)
    autonomy_days: float = 1.0       # Батарейн нөөц (нар байхгүй өдөр)
    battery_dod: float = 0.8         # Батарейн цэнэг ашиглах гүн (LiFePO4)
    battery_efficiency: float = 0.9  # Батарейн цэнэг/цэнэггүйжих ашиг
    operating_hours: float = 24.0    # Ачаалал өдөрт хэдэн цаг ажиллах
    panel_wp: float = 550.0          # Нэг панелийн чадал, Вт
    panel_area_m2: float = 2.6       # Нэг панелийн талбай, м²
    cost_per_wp: float = 0.9         # PV өртөг, $/Вт
    cost_per_kwh: float = 350.0      # Батарей өртөг, $/кВт·ц
    bos_factor: float = 1.2          # Угсралт + туслах төхөөрөмжийн коэффициент
    fixed_cost: float = 8000.0       # Станц бүрийн тогтмол суурь зардал, $


def size_solar_system(load_kw, a: Assumptions):
    """
    Өгөгдсөн ачаалал (кВт)-д тохирох нарны систем + батарейн хэмжээ, өртгийг тооцоолно.
    Буцаах: dict (бүх үзүүлэлт болон өртгийн задаргаа).
    """
    if load_kw is None or load_kw <= 0 or (isinstance(load_kw, float) and math.isnan(load_kw)):
        return {
            'load_kw': 0.0, 'energy_kwh_day': 0.0, 'pv_kwp': 0.0,
            'battery_kwh': 0.0, 'panels': 0, 'area_m2': 0.0,
            'cost_pv': 0.0, 'cost_battery': 0.0, 'cost_variable': 0.0,
            'fixed_cost': 0.0, 'cost_total': 0.0,
        }

    energy = load_kw * a.operating_hours                       # кВт·ц/өдөр
    pv_kwp = energy / (a.psh * a.performance_ratio)            # кВт (DC оргил)
    battery_kwh = energy * a.autonomy_days / (a.battery_dod * a.battery_efficiency)
    panels = math.ceil(pv_kwp * 1000.0 / a.panel_wp)
    area = panels * a.panel_area_m2

    cost_pv = pv_kwp * 1000.0 * a.cost_per_wp
    cost_battery = battery_kwh * a.cost_per_kwh
    cost_variable = (cost_pv + cost_battery) * a.bos_factor
    cost_total = cost_variable + a.fixed_cost

    return {
        'load_kw': load_kw,
        'energy_kwh_day': energy,
        'pv_kwp': pv_kwp,
        'battery_kwh': battery_kwh,
        'panels': panels,
        'area_m2': area,
        'cost_pv': cost_pv,
        'cost_battery': cost_battery,
        'cost_variable': cost_variable,
        'fixed_cost': a.fixed_cost,
        'cost_total': cost_total,
    }
