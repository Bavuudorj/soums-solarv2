"""
Folium интерактив газрын зураг:
  • Ачаалалтай цэг — хэрэглээ (кВт), сүлжээний нийлбэр, нарны систем + батарей + өртөг
  • Шугам — урт, хүчдэл, тооцоолсон нэвтрүүлэх чадвар (кВт)
  • Ачаалалгүй зангилаа — ногоон цэг, холбоотой сумдын нийлбэр
  • Зөвлөмжит төвлөрсөн станц
"""

import os
import base64
import io

import pandas as pd
import folium

from solar import Assumptions, size_solar_system
from capacity import line_capacity_kw
from network import analyze, _code

_ICON_CACHE = {}


def icon_data_uri(path="icon1.png", size=48):
    """Зургийг жижигсгэж base64 data URI болгоно (маркерт зориулсан)."""
    key = (path, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    uri = None
    try:
        from PIL import Image
        if os.path.exists(path):
            im = Image.open(path).convert("RGBA").resize((size, size))
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = None
    _ICON_CACHE[key] = uri
    return uri


def fmt(value, decimals=0):
    if value is None or pd.isna(value):
        return 'Тодорхойгүй'
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def get_voltage_color(kv):
    if kv is None or pd.isna(kv):
        return '#888888'
    if kv >= 110:
        return '#d73027'   # улаан
    if kv >= 35:
        return '#1a9850'   # ногоон
    if kv >= 15:
        return '#8c510a'   # бор
    return '#ff8c00'       # улбар шар (6, 10 кВ)


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
    if consumption is None or pd.isna(consumption) or consumption <= 0:
        return 4
    return max(min((consumption ** 0.5) * 0.12, 22), 4)


def get_line_width(capacity_kw):
    if capacity_kw is None or pd.isna(capacity_kw) or capacity_kw <= 0:
        return 1.5
    return max(min((capacity_kw ** 0.5) * 0.06, 8), 1.5)


def _solar_block(system, title):
    return (
        f"<hr style='margin:5px 0'><b>{title}</b><br>"
        f"☀️ Нарны чадал: {fmt(system['pv_kwp'], 0)} кВт ({fmt(system['panels'],0)} панель)<br>"
        f"🔋 Батарей: {fmt(system['battery_kwh'], 0)} кВт·ц<br>"
        f"💲 Өртөг: ${fmt(system['cost_total'], 0)}"
    )


def build_map(soums, lines, assumptions: Assumptions = None, analysis=None):
    if assumptions is None:
        assumptions = Assumptions()
    if analysis is None:
        analysis = analyze(soums, lines, assumptions)

    code_to_comp = analysis['code_to_comp']
    node_info = analysis['node_info']
    soum_loads = analysis['soum_loads']
    grid = analysis['grid']

    m = folium.Map(location=[46.8625, 103.0062], zoom_start=6, tiles='OpenStreetMap')

    # --- Шугамууд ---
    for _, row in lines.iterrows():
        kv = row['хүчдэл_num']
        length = row['урт']
        cap, br = line_capacity_kw(kv, length, grid, breakdown=True)
        color = get_voltage_color(kv)
        sname = row['эхлэл_нэр'] if not pd.isna(row['эхлэл_нэр']) else '?'
        ename = row['дуусах_нэр'] if not pd.isna(row['дуусах_нэр']) else '?'

        popup = [f"<b>Шугам:</b> {sname} → {ename}",
                 f"<b>Урт:</b> {fmt(length, 1)} км",
                 f"<b>Хүчдэл:</b> {fmt(kv, 0)} кВ" if kv else "<b>Хүчдэл:</b> Тодорхойгүй"]
        if cap is not None:
            popup.append(f"<b>Нэвтрүүлэх чадвар:</b> {fmt(cap, 0)} кВт")
            popup.append(f"<span style='font-size:11px;color:#555'>Хязгаарлагч: {br['binding']}</span>")
        else:
            popup.append("<b>Нэвтрүүлэх чадвар:</b> тооцоолох боломжгүй")

        folium.PolyLine(
            locations=[[row['эхлэл_lat'], row['эхлэл_lon']], [row['дуусах_lat'], row['дуусах_lon']]],
            color=color, weight=get_line_width(cap), opacity=0.8,
            popup=folium.Popup('<br>'.join(popup), max_width=320),
            tooltip=f"{sname} → {ename} | {fmt(kv,0)} кВ | {fmt(cap,0)} кВт"
        ).add_to(m)

    # --- Зөвлөмжит төвлөрсөн станцууд (icon1.png) ---
    plant_uri = icon_data_uri("icon1.png", size=64)
    for comp in analysis['components']:
        if comp['recommended'] == 'centralized' and comp['plant_coord']:
            la, lo = comp['plant_coord']
            sd = comp['central_system']
            popup = ["<b>★ Төвлөрсөн нарны станц</b>",
                     f"<b>Хангах сум:</b> {comp['soum_count']}",
                     f"<b>Нийт ачаалал:</b> {fmt(comp['total_load_kw'], 0)} кВт",
                     f"☀️ Нарны чадал: {fmt(sd['pv_kwp'], 0)} кВт",
                     f"🔋 Батарей: {fmt(sd['battery_kwh'], 0)} кВт·ц",
                     f"💲 Нийт өртөг: ${fmt(sd['cost_total'], 0)}"]
            if plant_uri:
                icon = folium.CustomIcon(plant_uri, icon_size=(32, 32))
            else:
                icon = folium.Icon(color='red', icon='bolt', prefix='fa')
            folium.Marker(
                location=[la, lo], icon=icon,
                popup=folium.Popup('<br>'.join(popup), max_width=300),
                tooltip=f"Төвлөрсөн станц: {fmt(comp['total_load_kw'], 0)} кВт"
            ).add_to(m)

    # --- Зангилаа (ачаалалгүй цэг, ногоон) ---
    for c, info in node_info.items():
        if c in soum_loads:
            continue
        comp = code_to_comp.get(c)
        parts = [f"<b>Зангилаа:</b> {info['name']}"]
        if info.get('type'):
            parts.append(f"<b>Төрөл:</b> {info['type']}")
        if comp:
            parts.append(f"<b>Холбоотой сум:</b> {comp['soum_count']}")
            parts.append(f"<b>Нийлбэр ачаалал:</b> {fmt(comp['total_load_kw'], 0)} кВт")
        folium.CircleMarker(
            location=[info['lat'], info['lon']], radius=4, color='#1a7a34', fill=True,
            fill_color='#2ca02c', fill_opacity=1.0, weight=1.5,
            popup=folium.Popup('<br>'.join(parts), max_width=280),
            tooltip=f"Зангилаа: {info['name']}"
        ).add_to(m)

    # --- Ачаалалтай цэг (сум) ---
    max_load = max(soum_loads.values()) if soum_loads else 0
    for c, info in node_info.items():
        if c not in soum_loads:
            continue
        load = soum_loads[c]
        color = get_consumption_color(load, max_load)
        parts = [f"<b>Аймаг:</b> {info.get('aimag') or 'Тодорхойгүй'}",
                 f"<b>Цэг:</b> {info['name']}"]
        if info.get('type'):
            parts.append(f"<b>Төрөл:</b> {info['type']}")
        parts.append(f"<b>Хэрэглээ:</b> {fmt(load, 0)} кВт")

        comp = code_to_comp.get(c)
        if comp:
            parts.append(f"<b>Нийлбэр:</b> {fmt(comp['total_load_kw'], 0)} кВт ({comp['soum_count']} сум)")
            own = comp['per_soum_system'].get(c) or size_solar_system(load, assumptions)
            parts.append(_solar_block(own, "Өөрийн систем (тархмал)"))
            if comp['recommended'] == 'centralized':
                parts.append(
                    f"<hr style='margin:5px 0'><b>Зөвлөмж: ТӨВЛӨРСӨН станц</b><br>"
                    f"Сүлжээний өртөг: ${fmt(comp['centralized_cost'], 0)}<br>"
                    f"<span style='color:#1a7a34'>Хэмнэлт: ${fmt(comp['savings'], 0)}</span>"
                )
            else:
                reason = "чадвар хүрэлцэхгүй" if not comp['centralized_feasible'] else "хямд"
                parts.append(
                    f"<hr style='margin:5px 0'><b>Зөвлөмж: ТАРХМАЛ ({reason})</b><br>"
                    f"Сүлжээний өртөг: ${fmt(comp['distributed_cost'], 0)}"
                )

        folium.CircleMarker(
            location=[info['lat'], info['lon']], radius=get_radius(load),
            popup=folium.Popup('<br>'.join(parts), max_width=320),
            tooltip=f"{info['name']}: {fmt(load, 0)} кВт",
            color=color, fill=True, fill_color=color, fill_opacity=0.85, weight=1.2
        ).add_to(m)

    _add_legend(m)
    return m


def _add_legend(map_obj):
    plant_uri = icon_data_uri("icon1.png", size=64)
    plant_symbol = (f'<img src="{plant_uri}" style="height:14px;vertical-align:middle">'
                    if plant_uri else '<span style="color:#d73027;">&#9733;</span>')
    legend_html = """
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
                background: rgba(255,255,255,0.92); padding: 10px 14px;
                border: 1px solid #999; border-radius: 6px; font-size: 12px;
                line-height: 1.6; box-shadow: 0 1px 4px rgba(0,0,0,0.3);">
        <b>Шугамын хүчдэл</b><br>
        <span style="color:#d73027;">&#9644;</span> 110 кВ &nbsp;
        <span style="color:#1a9850;">&#9644;</span> 35 кВ<br>
        <span style="color:#8c510a;">&#9644;</span> 15 кВ &nbsp;
        <span style="color:#ff8c00;">&#9644;</span> 6 / 10 кВ<br>
        <hr style="margin:6px 0;">
        <span style="color:#2ca02c;">&#9679;</span> Ачаалалгүй зангилаа<br>
        __PLANT_SYMBOL__ Зөвлөмжит төвлөрсөн станц<br>
        <span style="color:#d73027;">&#9679;</span> Их &nbsp;
        <span style="color:#fdae61;">&#9679;</span> Дунд &nbsp;
        <span style="color:#4575b4;">&#9679;</span> Бага хэрэглээ
    </div>
    """
    legend_html = legend_html.replace('__PLANT_SYMBOL__', plant_symbol)
    map_obj.get_root().html.add_child(folium.Element(legend_html))


def build_milp_map(stations, lines=None, icon_path="icon1.png", icon_size=32):
    """
    MILP-ийн санал болгосон нар+батарей станцуудыг газрын зураг дээр харуулна.
    stations: [{code,name,lat,lon,pv_kw,batt_kwh,batt_kw,lcoe,network}]
    Станцууд нь асаах/унтраах боломжтой давхаргад (LayerControl) байрлана.
    Marker дээр дарахад tooltip-д код буцаана (сонголт барихад).
    """
    m = folium.Map(location=[46.8625, 103.0062], zoom_start=6, tiles='OpenStreetMap')

    # Шугамыг бүдэг саарал дэвсгэр болгон (нэмэлт давхарга)
    if lines is not None:
        line_fg = folium.FeatureGroup(name="Шугам", show=True)
        for _, row in lines.iterrows():
            folium.PolyLine(
                locations=[[row['эхлэл_lat'], row['эхлэл_lon']],
                           [row['дуусах_lat'], row['дуусах_lon']]],
                color='#aaaaaa', weight=1.0, opacity=0.5
            ).add_to(line_fg)
        line_fg.add_to(m)

    data_uri = icon_data_uri(icon_path, size=64)
    station_fg = folium.FeatureGroup(name="☀️ Нар+батарей станц", show=True)
    for stn in stations:
        popup = [f"<b>{stn['name']}</b>",
                 f"☀️ Нарны чадал: {fmt(stn['pv_kw'], 0)} кВт",
                 f"🔋 Батарей: {fmt(stn['batt_kwh'], 0)} кВт·ц / {fmt(stn['batt_kw'], 0)} кВт"]
        if stn.get('lcoe'):
            popup.append(f"💲 LCOE: ${stn['lcoe']:.3f}/кВт·ц")
        if data_uri:
            icon = folium.CustomIcon(data_uri, icon_size=(icon_size, icon_size))
        else:
            icon = folium.Icon(color='orange', icon='solar-panel', prefix='fa')
        folium.Marker(
            location=[stn['lat'], stn['lon']],
            icon=icon,
            popup=folium.Popup('<br>'.join(popup), max_width=280),
            tooltip=stn['code'],          # код — сонголт барихад ашиглана
        ).add_to(station_fg)
    station_fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
