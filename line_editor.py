"""
🔌 Сүлжээ засварлагч — бие даасан, локал апп.

soums_v2.xlsx (зангилаа) / lines_v2.xlsx (шугам)-аас уншиж газрын зураг дээр гаргана:
  ЗАНГИЛАА:  газрын зураг дээр дарж сонгох → нэр/координат/ачаалал засах, устгах;
             шинээр нэмэх (сүүлд дарсан цэгт).
  ШУГАМ:     шугам зурж нэмэх (ойрын зангилаанд залгана), дарж сонгох → засах/устгах;
             зангилаагаар нэмэх.
  Шугамын координат нь зангилааны кодоос тооцогдоно (зангилаа зөөвөл дагана).
  Эцэст нь soums_v2.xlsx ба lines_v2.xlsx-д буцааж ХАДГАЛНА.

Ажиллуулах:  streamlit run line_editor.py
"""

import io
import math

import pandas as pd
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium

from network import load_soums, load_lines, build_node_info, _code

SOUMS_FILE = "soums_v2.xlsx"
LINES_FILE = "lines_v2.xlsx"
KV_OPTS = [6.0, 10.0, 15.0, 35.0, 110.0]

st.set_page_config(page_title="Сүлжээ засварлагч", layout="wide")


@st.cache_data
def initial_data():
    s = load_soums(SOUMS_FILE)
    l = load_lines(LINES_FILE)
    info = build_node_info(s, l)
    nodes = {}
    for c, v in info.items():
        nodes[c] = {
            'name': v.get('name') or c, 'aimag': v.get('aimag'),
            'type': v.get('type'), 'lat': v.get('lat'), 'lon': v.get('lon'),
            'load_mw': (v['load_kw'] / 1000.0) if v.get('load_kw') else None,
        }
    lines = []
    for i, (_, r) in enumerate(l.iterrows(), 1):
        sc, ec = _code(r['эхлэл_код']), _code(r['дуусах_код'])
        if sc and ec:
            lines.append({'id': i, 'scode': sc, 'ecode': ec, 'kv': r['хүчдэл_num']})
    return nodes, lines


def haversine(lat1, lon1, lat2, lon2):
    R, p = 6371.0, math.pi / 180
    h = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return round(2 * R * math.asin(math.sqrt(h)), 1)


def nearest_node(lat, lon, wn):
    best, bd = None, 1e18
    for code, v in wn.items():
        if v.get('lat') is None:
            continue
        dd = (v['lat'] - lat) ** 2 + (v['lon'] - lon) ** 2
        if dd < bd:
            bd, best = dd, code
    return best


def vcolor(kv):
    try:
        kv = float(kv)
    except (TypeError, ValueError):
        return '#888888'
    if kv >= 110:
        return '#d73027'
    if kv >= 35:
        return '#1a9850'
    if kv >= 15:
        return '#8c510a'
    return '#ff8c00'


def build_frames(wn, wl):
    """Ажлын зангилаа/шугамаас soums_v2 ба lines_v2 бүтэцтэй DataFrame үүсгэнэ."""
    soums_df = pd.DataFrame([{
        'Код': c, 'Аймаг': v.get('aimag'), 'Цэгийн нэр': v.get('name'),
        'Төрөл': v.get('type'), 'Өргөрөг (lat)': v.get('lat'), 'Уртраг (lon)': v.get('lon'),
        'Координатын эх сурвалж': None, 'Ачаалал (МВт)': v.get('load_mw'),
    } for c, v in wn.items()])
    lrows = []
    for i, ln in enumerate(wl, 1):
        s, e = wn.get(ln['scode'], {}), wn.get(ln['ecode'], {})
        length = None
        if s.get('lat') is not None and e.get('lat') is not None:
            length = haversine(s['lat'], s['lon'], e['lat'], e['lon'])
        lrows.append({
            '№': i, 'Эхлэл код': ln['scode'], 'Эхлэл нэр': s.get('name'),
            'Эхлэл аймаг': s.get('aimag'), 'Эхлэл өргөрөг': s.get('lat'),
            'Эхлэл уртраг': s.get('lon'), 'Төгсгөл код': ln['ecode'],
            'Төгсгөл нэр': e.get('name'), 'Төгсгөл аймаг': e.get('aimag'),
            'Төгсгөл өргөрөг': e.get('lat'), 'Төгсгөл уртраг': e.get('lon'),
            'Шулууны урт (км)': length, 'Хүчдэл (кВ)': ln['kv'],
        })
    return soums_df, pd.DataFrame(lrows)


def to_xlsx_bytes(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    return buf.getvalue()


# --- Ажлын төлөв ---
if 'wn' not in st.session_state:
    _nodes, _lines = initial_data()
    st.session_state['wn'] = _nodes
    st.session_state['wl'] = _lines
    st.session_state['next_lid'] = (max((x['id'] for x in _lines), default=0) + 1)
    st.session_state['zseq'] = 1
    st.session_state['draw_n'] = 0
    st.session_state['sel'] = None          # ('N', code) | ('L', id)
    st.session_state['last_click'] = None    # (lat, lon)

wn = st.session_state['wn']
wl = st.session_state['wl']


def node_label(c):
    v = wn.get(c, {})
    return f"{v.get('name', c)} ({c})"


def new_code():
    while True:
        c = f"Z-{st.session_state['zseq']}"
        st.session_state['zseq'] += 1
        if c not in wn:
            return c


def build_map():
    m = folium.Map(location=[46.8625, 103.0062], zoom_start=6, tiles='OpenStreetMap')
    sel = st.session_state.get('sel')
    # Шугамууд (координат зангилаанаас)
    for ln in wl:
        s, e = wn.get(ln['scode']), wn.get(ln['ecode'])
        if not s or not e or s.get('lat') is None or e.get('lat') is None:
            continue
        is_sel = sel == ('L', ln['id'])
        folium.PolyLine(
            [[s['lat'], s['lon']], [e['lat'], e['lon']]],
            color='#000000' if is_sel else vcolor(ln['kv']),
            weight=7 if is_sel else 3, opacity=0.95 if is_sel else 0.8,
            tooltip=f"L:{ln['id']}",
            popup=f"{s['name']} → {e['name']} | {ln['kv']} кВ").add_to(m)
    # Зангилаа
    for code, v in wn.items():
        if v.get('lat') is None:
            continue
        is_sel = sel == ('N', code)
        has_load = v.get('load_mw') not in (None, 0)
        color = '#d73027' if is_sel else ('#1f77b4' if has_load else '#777777')
        folium.CircleMarker(
            [v['lat'], v['lon']], radius=7 if is_sel else 4, color=color, fill=True,
            fill_color=color, fill_opacity=0.9, weight=2,
            tooltip=f"N:{code}",
            popup=f"<b>{v.get('name')}</b> ({code})<br>{v.get('aimag') or ''}").add_to(m)
    Draw(export=False,
         draw_options={'polyline': True, 'polygon': False, 'rectangle': False,
                       'circle': False, 'marker': False, 'circlemarker': False},
         edit_options={'edit': False, 'remove': False}).add_to(m)
    return m


st.title("🔌 Сүлжээ засварлагч (зангилаа + шугам)")
st.caption("Зангилаа/шугам дээр **дарж сонгоод** засах/устгах · шугам **зурж** нэмэх · "
           "сүүлд дарсан цэгт **зангилаа нэмэх** · эцэст нь файлд **хадгалах**.")

col_map, col_side = st.columns([3, 2])
with col_map:
    state = st_folium(build_map(), height=620, width=None, key='emap',
                      returned_objects=['all_drawings', 'last_object_clicked_tooltip',
                                        'last_clicked'])

# Сүүлд дарсан координат (зангилаа нэмэхэд)
if state and state.get('last_clicked'):
    st.session_state['last_click'] = (state['last_clicked']['lat'], state['last_clicked']['lng'])

# Зурсан шинэ шугам → ойрын зангилаанд залгана
draws = (state or {}).get('all_drawings') or []
if len(draws) > st.session_state['draw_n']:
    for feat in draws[st.session_state['draw_n']:]:
        try:
            coords = feat['geometry']['coordinates']
            (lon1, lat1), (lon2, lat2) = coords[0], coords[-1]
            sc, ec = nearest_node(lat1, lon1, wn), nearest_node(lat2, lon2, wn)
            if sc and ec and sc != ec:
                wl.append({'id': st.session_state['next_lid'], 'scode': sc, 'ecode': ec, 'kv': None})
                st.session_state['next_lid'] += 1
        except Exception:
            pass
    st.session_state['draw_n'] = len(draws)
    st.rerun()

# Дарж сонгох
clicked = (state or {}).get('last_object_clicked_tooltip')
if clicked:
    if str(clicked).startswith('N:'):
        st.session_state['sel'] = ('N', clicked[2:])
    elif str(clicked).startswith('L:') and clicked[2:].isdigit():
        st.session_state['sel'] = ('L', int(clicked[2:]))

with col_side:
    sel = st.session_state.get('sel')

    # ===== Зангилаа засах =====
    if sel and sel[0] == 'N' and sel[1] in wn:
        code = sel[1]
        v = wn[code]
        st.subheader(f"🔵 Зангилаа: {code}")
        new_c = st.text_input("Код", value=code, key=f"nc_{code}")
        nm = st.text_input("Нэр", value=v.get('name') or '', key=f"nm_{code}")
        ai = st.text_input("Аймаг", value=v.get('aimag') or '', key=f"ai_{code}")
        ty = st.text_input("Төрөл", value=v.get('type') or '', key=f"ty_{code}")
        la = st.number_input("Өргөрөг", value=float(v.get('lat') or 0), format="%.5f", key=f"la_{code}")
        lo = st.number_input("Уртраг", value=float(v.get('lon') or 0), format="%.5f", key=f"lo_{code}")
        ld = st.number_input("Ачаалал (МВт)", value=float(v.get('load_mw') or 0), step=0.1, key=f"ld_{code}")
        b1, b2 = st.columns(2)
        if b1.button("💾 Хадгалах", key=f"nsv_{code}"):
            v.update({'name': nm, 'aimag': ai, 'type': ty, 'lat': la, 'lon': lo,
                      'load_mw': ld if ld > 0 else None})
            if new_c and new_c != code:
                wn[new_c] = wn.pop(code)
                for ln in wl:
                    if ln['scode'] == code:
                        ln['scode'] = new_c
                    if ln['ecode'] == code:
                        ln['ecode'] = new_c
                st.session_state['sel'] = ('N', new_c)
            st.rerun()
        if b2.button("🗑️ Устгах", key=f"ndl_{code}"):
            removed = [ln for ln in wl if ln['scode'] == code or ln['ecode'] == code]
            st.session_state['wl'] = [ln for ln in wl if ln['scode'] != code and ln['ecode'] != code]
            wn.pop(code, None)
            st.session_state['sel'] = None
            st.warning(f"Зангилаа + холбоотой {len(removed)} шугам устгагдлаа.")
            st.rerun()

    # ===== Шугам засах =====
    elif sel and sel[0] == 'L':
        ln = next((x for x in wl if x['id'] == sel[1]), None)
        if ln:
            st.subheader(f"➖ Шугам #{ln['id']}")
            codes = sorted(wn)
            sc = st.selectbox("Эхлэл", codes, index=codes.index(ln['scode']) if ln['scode'] in codes else 0,
                              format_func=node_label, key=f"lsc_{ln['id']}")
            ec = st.selectbox("Төгсгөл", codes, index=codes.index(ln['ecode']) if ln['ecode'] in codes else 0,
                              format_func=node_label, key=f"lec_{ln['id']}")
            kv = st.selectbox("Хүчдэл (кВ)", KV_OPTS,
                              index=KV_OPTS.index(ln['kv']) if ln['kv'] in KV_OPTS else 1, key=f"lkv_{ln['id']}")
            b1, b2 = st.columns(2)
            if b1.button("💾 Хадгалах", key=f"lsv_{ln['id']}"):
                ln.update({'scode': sc, 'ecode': ec, 'kv': kv})
                st.rerun()
            if b2.button("🗑️ Устгах", key=f"ldl_{ln['id']}"):
                st.session_state['wl'] = [x for x in wl if x['id'] != ln['id']]
                st.session_state['sel'] = None
                st.rerun()
    else:
        st.info("👉 Газрын зураг дээр зангилаа/шугам дээр дарж сонгоно.")

    st.divider()
    # ===== Шинэ зангилаа =====
    st.subheader("🆕 Зангилаа нэмэх")
    lc = st.session_state.get('last_click')
    dlat = lc[0] if lc else 47.0
    dlon = lc[1] if lc else 103.0
    if lc:
        st.caption(f"📍 Сүүлд дарсан цэг: {dlat:.4f}, {dlon:.4f}")
    nn_name = st.text_input("Нэр", key="nn_name")
    nn_aimag = st.text_input("Аймаг", key="nn_aimag")
    nlat = st.number_input("Өргөрөг", value=float(dlat), format="%.5f", key="nn_lat")
    nlon = st.number_input("Уртраг", value=float(dlon), format="%.5f", key="nn_lon")
    nload = st.number_input("Ачаалал (МВт)", value=0.0, step=0.1, key="nn_load")
    if st.button("➕ Зангилаа нэмэх"):
        c = new_code()
        wn[c] = {'name': nn_name or c, 'aimag': nn_aimag or None, 'type': 'Зангилаа',
                 'lat': nlat, 'lon': nlon, 'load_mw': nload if nload > 0 else None}
        st.session_state['sel'] = ('N', c)
        st.rerun()

    st.divider()
    # ===== Шинэ шугам =====
    st.subheader("➕ Шугам нэмэх")
    codes = sorted(wn)
    a_sc = st.selectbox("Эхлэл", codes, format_func=node_label, key="al_sc")
    a_ec = st.selectbox("Төгсгөл", codes, format_func=node_label, key="al_ec")
    a_kv = st.selectbox("Хүчдэл (кВ)", KV_OPTS, index=1, key="al_kv")
    if st.button("➕ Шугам нэмэх", key="al_btn"):
        if a_sc == a_ec:
            st.warning("Эхлэл ба төгсгөл ижил байж болохгүй.")
        else:
            wl.append({'id': st.session_state['next_lid'], 'scode': a_sc, 'ecode': a_ec, 'kv': a_kv})
            st.session_state['next_lid'] += 1
            st.rerun()

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Зангилаа", len(wn))
    c2.metric("Шугам", len(wl))
    if c3.button("↩️ Дахин", help="Файлаас дахин ачаалах"):
        for k in ('wn', 'wl', 'next_lid', 'zseq', 'draw_n', 'sel', 'last_click'):
            st.session_state.pop(k, None)
        st.rerun()

    soums_df, lines_df = build_frames(wn, wl)

    # Локал файлд бичих (зөвхөн локалаар тогтвортой)
    if st.button("💾 Файлд хадгалах (зөвхөн локал)", type="primary"):
        try:
            soums_df.to_excel(SOUMS_FILE, index=False)
            lines_df.to_excel(LINES_FILE, index=False)
            st.success(f"✅ Хадгалагдлаа: {SOUMS_FILE} ({len(wn)}), {LINES_FILE} ({len(wl)})")
        except Exception as ex:
            st.error(f"Файлд бичих боломжгүй (Cloud дээр доорх татах товчийг ашиглана уу): {ex}")

    # Татаж авах (Cloud дээр — татаад GitHub-д commit хийнэ)
    st.caption("☁️ Streamlit Cloud дээр доорхоос татаж аваад GitHub-д commit хийнэ:")
    dc1, dc2 = st.columns(2)
    dc1.download_button("⬇️ soums_v2.xlsx", to_xlsx_bytes(soums_df),
                        "soums_v2.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    dc2.download_button("⬇️ lines_v2.xlsx", to_xlsx_bytes(lines_df),
                        "lines_v2.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("📋 Зангилаа / Шугамын хүснэгт"):
    t1, t2 = st.tabs(["Зангилаа", "Шугам"])
    t1.dataframe(pd.DataFrame([
        {'Код': c, 'Нэр': v.get('name'), 'Аймаг': v.get('aimag'), 'Төрөл': v.get('type'),
         'Ачаалал (МВт)': v.get('load_mw')} for c, v in wn.items()],),
        width='stretch', hide_index=True, height=280)
    t2.dataframe(pd.DataFrame([
        {'#': ln['id'], 'Эхлэл': ln['scode'], 'Төгсгөл': ln['ecode'], 'кВ': ln['kv']} for ln in wl],),
        width='stretch', hide_index=True, height=280)
