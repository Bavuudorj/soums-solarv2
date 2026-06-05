"""
Folium интерактив газрын зураг үүсгэх:
  • Сум — хэрэглээ (кВт), сүлжээний нийлбэр, нарны систем + батарей + өртөг
  • Шугам — урт, хүчдэл, нэвтрүүлэх чадвар
  • Суурингүй зангилаа — холбоотой сумдын нийлбэр ачаалал
  • Зөвлөмжит төвлөрсөн станцын байршил
"""

import re

import pandas as pd
import folium

from solar import Assumptions, size_solar_system
from network import analyze, _code


def fmt(value, decimals=0):
    if value is None or pd.isna(value):
        return 'Тодорхойгүй'
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def parse_voltage(text):
    if text is None or pd.isna(text):
        return None
    m = re.search(r'\d+(?:[.,]\d+)?', str(text))
    return float(m.group().replace(',', '.')) if m else None


def get_voltage_color(kv):
    if kv is None:
        return '#888888'
    if kv >= 110:
        return '#d73027'
    if kv >= 35:
        return '#fc8d59'
    if kv >= 15:
        return '#1a9850'
    if kv >= 10:
        return '#4575b4'
    return '#762a83'


def get_consumption_color(consumption, max_val):
    if max_val == 0 or pd.isna(max_val) or pd.isna(consumption):
        return '#4575b4'
    ratio = consumption / max_val
    if ratio > 0.7:
        return '#d73027'
    if ratio > 0.4:
        return '#f46d43'
    if ratio > 0.1:
        return '#fdae61'
    return '#4575b4'


def get_radius(consumption):
    if pd.isna(consumption) or consumption <= 0:
        return 4
    return max(min((consumption ** 0.5) * 0.45, 22), 4)


def get_line_width(capacity):
    if capacity is None or pd.isna(capacity) or capacity <= 0:
        return 1.5
    return max(min((capacity ** 0.5) * 1.1, 8), 1.5)


def _solar_popup_block(system, title):
    """Нарны системийн тооцооллыг popup-д харуулах HTML хэсэг."""
    return (
        f"<hr style='margin:5px 0'><b>{title}</b><br>"
        f"☀️ Нарны чадал: {fmt(system['pv_kwp'], 1)} кВт ({system['panels']} панель)<br>"
        f"🔋 Батарей: {fmt(system['battery_kwh'], 1)} кВт·ц<br>"
        f"💲 Өртөг: ${fmt(system['cost_total'], 0)}"
    )


def build_map(soums, lines, assumptions: Assumptions = None, analysis=None):
    """Газрын зураг үүсгэж folium.Map буцаана."""
    if assumptions is None:
        assumptions = Assumptions()
    if analysis is None:
        analysis = analyze(soums, lines, assumptions)

    code_to_comp = analysis['code_to_comp']
    coords = analysis['coords']

    map_mongolia = folium.Map(location=[46.8625, 103.0062], zoom_start=6, tiles='OpenStreetMap')

    # --- Шугамууд ---
    for _, row in lines.iterrows():
        kv = parse_voltage(row['хүчдэл_кв'])
        capacity = row['чадвар_мвт']
        color = get_voltage_color(kv)
        start_name = row['эхлэл_нэр'] if not pd.isna(row['эхлэл_нэр']) else '?'
        end_name = row['дуусах_нэр'] if not pd.isna(row['дуусах_нэр']) else '?'

        popup = [f"<b>Шугам:</b> {start_name} → {end_name}",
                 f"<b>Урт:</b> {fmt(row['урт_хэмжсэн'], 1)} км",
                 f"<b>Хүчдэл:</b> {row['хүчдэл_кв'] if not pd.isna(row['хүчдэл_кв']) else 'Тодорхойгүй'}",
                 f"<b>Нэвтрүүлэх чадвар:</b> {fmt(capacity, 2)} МВт"]

        folium.PolyLine(
            locations=[[row['эхлэл_lat'], row['эхлэл_lon']], [row['дуусах_lat'], row['дуусах_lon']]],
            color=color, weight=get_line_width(capacity), opacity=0.8,
            popup=folium.Popup('<br>'.join(popup), max_width=320),
            tooltip=f"{start_name} → {end_name} | {row['хүчдэл_кв'] if not pd.isna(row['хүчдэл_кв']) else '?'}"
        ).add_to(map_mongolia)

    # --- Суурингүй зангилаа (ногоон) ---
    soum_codes_set = set(analysis['soum_loads'])
    soum_coords = {(round(la, 4), round(lo, 4)) for la, lo in zip(soums['lat'], soums['lon'])
                   if not (pd.isna(la) or pd.isna(lo))}
    endpoints = {}
    for _, row in lines.iterrows():
        for code, name, lat, lon in [
            (row['эхлэл_код'], row['эхлэл_нэр'], row['эхлэл_lat'], row['эхлэл_lon']),
            (row['дуусах_код'], row['дуусах_нэр'], row['дуусах_lat'], row['дуусах_lon']),
        ]:
            if pd.isna(lat) or pd.isna(lon):
                continue
            c = _code(code)
            settled = (c in soum_codes_set) or ((round(lat, 4), round(lon, 4)) in soum_coords)
            if settled:
                continue
            key = (round(lat, 4), round(lon, 4))
            if key not in endpoints:
                endpoints[key] = (str(name) if not pd.isna(name) else 'Зангилаа', c)

    for (lat, lon), (name, c) in endpoints.items():
        parts = [f"<b>Суурингүй зангилаа:</b> {name}"]
        comp = code_to_comp.get(c)
        if comp:
            parts.append(f"<b>Холбоотой сум:</b> {comp['soum_count']}")
            parts.append(f"<b>Нийлбэр ачаалал:</b> {fmt(comp['total_load_kw'], 0)} кВт")
        folium.CircleMarker(
            location=[lat, lon], radius=5, color='#1a7a34', fill=True,
            fill_color='#2ca02c', fill_opacity=1.0, weight=2,
            popup=folium.Popup('<br>'.join(parts), max_width=280),
            tooltip=f"Зангилаа: {name}"
        ).add_to(map_mongolia)

    # --- Зөвлөмжит төвлөрсөн станцууд (улаан од) ---
    for comp in analysis['components']:
        if comp['recommended'] == 'centralized' and comp['plant_coord']:
            la, lo = comp['plant_coord']
            sysd = comp['central_system']
            popup = [f"<b>★ Төвлөрсөн нарны станц</b>",
                     f"<b>Хангах сум:</b> {comp['soum_count']}",
                     f"<b>Нийт ачаалал:</b> {fmt(comp['total_load_kw'], 0)} кВт",
                     f"☀️ Нарны чадал: {fmt(sysd['pv_kwp'], 1)} кВт",
                     f"🔋 Батарей: {fmt(sysd['battery_kwh'], 1)} кВт·ц",
                     f"💲 Нийт өртөг: ${fmt(sysd['cost_total'], 0)}"]
            folium.Marker(
                location=[la, lo],
                icon=folium.Icon(color='red', icon='bolt', prefix='fa'),
                popup=folium.Popup('<br>'.join(popup), max_width=300),
                tooltip=f"Төвлөрсөн станц: {fmt(comp['total_load_kw'], 0)} кВт"
            ).add_to(map_mongolia)

    # --- Сумын тэмдэглэгээ ---
    max_consumption = soums['хэрэглээ_квт'].max()
    for _, row in soums.iterrows():
        consumption = row['хэрэглээ_квт']
        color = get_consumption_color(consumption, max_consumption)
        aimag = row['аймаг'] if not pd.isna(row['аймаг']) else 'Тодорхойгүй'
        sum_name = row['сум'] if not pd.isna(row['сум']) else '?'
        soum_type = row['төрөл'] if not pd.isna(row['төрөл']) else None
        c = _code(row['код'])

        parts = [f"<b>Аймаг:</b> {aimag}", f"<b>Сум:</b> {sum_name}"]
        if soum_type:
            parts.append(f"<b>Төрөл:</b> {soum_type}")
        parts.append(f"<b>Хэрэглээ:</b> {fmt(consumption, 0)} кВт")

        comp = code_to_comp.get(c)
        if comp:
            parts.append(f"<b>Нийлбэр:</b> {fmt(comp['total_load_kw'], 0)} кВт ({comp['soum_count']} сум)")
            # Сумын өөрийн нарны систем
            own = comp['per_soum_system'].get(c) or size_solar_system(consumption, assumptions)
            parts.append(_solar_popup_block(own, "Өөрийн систем (тараангуй)"))
            # Сүлжээний зөвлөмж
            if comp['recommended'] == 'centralized':
                parts.append(
                    f"<hr style='margin:5px 0'><b>Зөвлөмж: ТӨВЛӨРСӨН станц</b><br>"
                    f"Сүлжээний нийт өртөг: ${fmt(comp['centralized_cost'], 0)}<br>"
                    f"<span style='color:#1a7a34'>Хэмнэлт: ${fmt(comp['savings'], 0)}</span>"
                )
            else:
                reason = "чадвар хүрэлцэхгүй" if not comp['centralized_feasible'] else "хямд"
                parts.append(
                    f"<hr style='margin:5px 0'><b>Зөвлөмж: ТАРААНГУЙ ({reason})</b><br>"
                    f"Сүлжээний нийт өртөг: ${fmt(comp['distributed_cost'], 0)}"
                )

        folium.CircleMarker(
            location=[row['lat'], row['lon']], radius=get_radius(consumption),
            popup=folium.Popup('<br>'.join(parts), max_width=320),
            tooltip=f"{sum_name}: {fmt(consumption, 0)} кВт",
            color=color, fill=True, fill_color=color, fill_opacity=0.85, weight=1.2
        ).add_to(map_mongolia)

    _add_legend(map_mongolia)
    return map_mongolia


def _add_legend(map_obj):
    legend_html = """
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
                background: rgba(255,255,255,0.92); padding: 10px 14px;
                border: 1px solid #999; border-radius: 6px; font-size: 12px;
                line-height: 1.6; box-shadow: 0 1px 4px rgba(0,0,0,0.3);">
        <b>Шугамын хүчдэл</b><br>
        <span style="color:#d73027;">&#9644;</span> 110 кВ &nbsp;
        <span style="color:#fc8d59;">&#9644;</span> 35 кВ<br>
        <span style="color:#1a9850;">&#9644;</span> 15 кВ &nbsp;
        <span style="color:#4575b4;">&#9644;</span> 10 кВ &nbsp;
        <span style="color:#762a83;">&#9644;</span> 6 кВ<br>
        <hr style="margin:6px 0;">
        <span style="color:#2ca02c;">&#9679;</span> Суурингүй зангилаа<br>
        <span style="color:#d73027;">&#9733;</span> Зөвлөмжит төвлөрсөн станц<br>
        <span style="color:#d73027;">&#9679;</span> Их &nbsp;
        <span style="color:#fdae61;">&#9679;</span> Дунд &nbsp;
        <span style="color:#4575b4;">&#9679;</span> Бага хэрэглээ
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(legend_html))
