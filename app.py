"""
Streamlit веб апп — Сумдын нарны эрчим хүчний хангамжийн төлөвлөлт.

Ажиллуулах:  streamlit run app.py
"""

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from dataclasses import asdict

from solar import Assumptions, size_solar_system
from capacity import GridParams
from network import load_soums, load_lines, analyze
from mapbuilder import build_map, build_milp_map
from profiles import load_demand_profiles
from pvgis import seasonal_solar_profiles
from optimize import EconParams, optimize_all

st.set_page_config(page_title="Нарны хангамжийн төлөвлөлт", layout="wide")


@st.cache_data
def get_data():
    return load_soums("soums_v2.xlsx"), load_lines("lines_v2.xlsx")


@st.cache_data(show_spinner=False)
def run_milp(econ_dict, grid_dict, use_api):
    soums, lines = get_data()
    grid = GridParams(**grid_dict)
    an = analyze(soums, lines, Assumptions(), grid)
    rep, w = load_demand_profiles()
    solar = {c: seasonal_solar_profiles(info['lat'], info['lon'], use_api=use_api)
             for c, info in an['node_info'].items()}
    return optimize_all(an, lines, rep, w, solar, EconParams(**econ_dict), grid)


st.title("☀️ Сумдын нарны эрчим хүчний хангамжийн төлөвлөлт")
st.caption(
    "Шугамын нэвтрүүлэх чадварыг харгалзан сумдыг батарейтай нарны системээр "
    "хамгийн бага зардлаар хэрхэн хангах вэ?"
)

# --- Хажуугийн самбар: таамаглалууд ---
with st.sidebar:
    st.header("⚙️ Таамаглалууд")
    a = Assumptions()
    a.psh = st.slider("Нар ашиглалт (цаг/өдөр)", 3.0, 6.0, 4.5, 0.1)
    a.load_factor = st.slider("Ачааллын коэф. LF (дундаж/оргил)", 0.20, 0.60, 0.35, 0.01,
                              help="Оргил чадлыг өдрийн дундаж руу шилжүүлнэ: E = 24·LF·P")
    a.autonomy_days = st.slider("Батарейн нөөц (өдөр)", 0.25, 3.0, 1.0, 0.25)
    a.performance_ratio = st.slider("Системийн ашиг (PR)", 0.60, 0.90, 0.75, 0.01)
    a.battery_dod = st.slider("Батарей DoD", 0.50, 0.95, 0.80, 0.05)
    st.divider()
    a.cost_per_wp = st.number_input("PV өртөг ($/Вт)", value=0.9, step=0.1, format="%.2f")
    a.cost_per_kwh = st.number_input("Батарей өртөг ($/кВт·ц)", value=350.0, step=10.0)
    a.fixed_cost = st.number_input("Станцын тогтмол зардал ($)", value=8000.0, step=500.0)
    a.panel_wp = st.number_input("Панелийн чадал (Вт)", value=550.0, step=10.0)
    st.divider()
    st.caption("Шугамын чадварын тооцоо")
    g = GridParams()
    g.cos_phi = st.slider("Чадварын коэф. (cosφ)", 0.80, 1.00, 0.90, 0.01)
    g.dU_max = st.slider("Зөвш. хүчдэлийн уналт (%)", 4.0, 10.0, 6.0, 0.5)

    st.divider()
    with st.expander("⚡ MILP оновчлолын параметр"):
        econ = EconParams()
        econ.c_pv = st.number_input("PV CAPEX ($/кВт)", value=800.0, step=50.0)
        econ.c_be = st.number_input("Батарей энерги ($/кВт·ц)", value=300.0, step=10.0)
        econ.c_bp = st.number_input("Батарей чадал ($/кВт)", value=200.0, step=10.0)
        econ.lambda_imp = st.number_input("Импортын тариф ($/кВт·ц)", value=0.08, step=0.01, format="%.3f")
        econ.lambda_exp = st.number_input("Экспортын үнэ ($/кВт·ц)", value=0.04, step=0.01, format="%.3f")
        econ.voll = st.number_input("VoLL ($/кВт·ц)", value=1.0, step=0.1)
        econ.r = st.slider("Хямдруулалтын хүү", 0.03, 0.15, 0.08, 0.01)
        econ.alpha = st.slider("Найдвартай байдал α", 0.90, 0.999, 0.99, 0.005)
        use_api = st.checkbox("Нарны өгөгдөл PVGIS API-аас (удаан)", value=False)

try:
    soums, lines = get_data()
except Exception as e:
    st.error(f"Өгөгдөл уншихад алдаа гарлаа: {e}")
    st.stop()

analysis = analyze(soums, lines, a, g)
s = analysis['summary']
comps = analysis['components']

# --- Нийт үзүүлэлт ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Нийт хамгийн бага зардал", f"${s['total_min_cost']:,.0f}")
c2.metric("Хэмнэлт (vs тархмал)", f"${s['total_savings']:,.0f}")
c3.metric("Сүлжээ", f"{s['n_networks']}",
          help=f"Төвлөрсөн: {s['n_centralized']} | Тархмал: {s['n_distributed']}")
c4.metric("Нийт ачаалал", f"{s['total_load_kw']:,.0f} кВт")

tab_map, tab_table, tab_detail, tab_milp, tab_stations = st.tabs(
    ["🗺️ Газрын зураг", "📋 Сүлжээний хүснэгт", "🔍 Дэлгэрэнгүй",
     "⚡ MILP оновчлол", "🏭 Станц сонголт"])

# --- Газрын зураг ---
with tab_map:
    m = build_map(soums, lines, a, analysis=analysis)
    st_folium(m, height=600, width=None, returned_objects=[])
    st.caption("Тэмдэглэгээ дээр дарж дэлгэрэнгүй тооцоог харна уу.")

# --- Сүлжээний хүснэгт ---
with tab_table:
    rows = []
    for r in comps:
        rows.append({
            "Сүлжээ": ", ".join(r['soum_names'][:3]) + (" …" if r['soum_count'] > 3 else ""),
            "Сум": r['soum_count'],
            "Ачаалал (кВт)": round(r['total_load_kw'], 0),
            "Зөвлөмж": "Төвлөрсөн" if r['recommended'] == 'centralized' else "Тархмал",
            "Чадвар хүрэх": "✓" if r['centralized_feasible'] else "✗",
            "PV (кВт)": round(r['central_system']['pv_kwp'], 1),
            "Батарей (кВт·ц)": round(r['central_system']['battery_kwh'], 1),
            "Төвлөрсөн ($)": round(r['centralized_cost'], 0),
            "Тархмал ($)": round(r['distributed_cost'], 0),
            "Хамгийн бага ($)": round(r['recommended_cost'], 0),
            "Хэмнэлт ($)": round(r['savings'], 0),
        })
    df = pd.DataFrame(rows).sort_values("Ачаалал (кВт)", ascending=False)
    st.dataframe(df, width='stretch', hide_index=True)

    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("⬇️ CSV татах", csv, "network_plan.csv", "text/csv")

# --- Дэлгэрэнгүй (сум сонгох) ---
with tab_detail:
    code_to_comp = analysis['code_to_comp']
    node_info = analysis['node_info']
    names = {c: info['name'] for c, info in node_info.items()}
    soum_loads = analysis['soum_loads']
    options = sorted(soum_loads.keys(), key=lambda c: names.get(c, c))
    label = {c: f"{names.get(c, c)} ({soum_loads[c]:.0f} кВт)" for c in options}
    sel = st.selectbox("Сум сонгох", options, format_func=lambda c: label[c])

    if sel:
        own = size_solar_system(soum_loads[sel], a)
        comp = code_to_comp.get(sel)
        st.subheader(f"{names.get(sel, sel)} — өөрийн систем (тархмал)")
        d1, d2, d3 = st.columns(3)
        d1.metric("Нарны чадал", f"{own['pv_kwp']:.1f} кВт", f"{own['panels']} панель")
        d2.metric("Батарей", f"{own['battery_kwh']:.1f} кВт·ц")
        d3.metric("Өртөг", f"${own['cost_total']:,.0f}")

        if comp:
            st.divider()
            st.subheader(f"Холбогдсон сүлжээ ({comp['soum_count']} сум, "
                         f"{comp['total_load_kw']:.0f} кВт)")
            st.write("**Холбоотой сумд:** " + ", ".join(comp['soum_names']))
            cs = comp['central_system']
            e1, e2, e3 = st.columns(3)
            e1.metric("Төвлөрсөн PV", f"{cs['pv_kwp']:.1f} кВт")
            e2.metric("Төвлөрсөн батарей", f"{cs['battery_kwh']:.1f} кВт·ц")
            e3.metric("Төвлөрсөн өртөг", f"${cs['cost_total']:,.0f}")

            if comp['recommended'] == 'centralized':
                st.success(
                    f"**Зөвлөмж: ТӨВЛӨРСӨН станц** — нэг станцаар бүх сумыг хангах нь "
                    f"${comp['savings']:,.0f} хэмнэнэ "
                    f"(${comp['distributed_cost']:,.0f} → ${comp['centralized_cost']:,.0f})."
                )
                if comp['capacity_unknown_used']:
                    st.info("⚠️ Зарим шугамын чадвар тодорхойгүй тул хүрэлцэнэ гэж үзсэн.")
            else:
                if not comp['centralized_feasible']:
                    st.warning(
                        "**Зөвлөмж: ТАРХМАЛ** — шугамын нэвтрүүлэх чадвар хүрэлцэхгүй тул "
                        "сум бүрийг тусад нь хангах шаардлагатай."
                    )
                else:
                    st.warning("**Зөвлөмж: ТАРХМАЛ** — энэ тохиолдолд тархмал хувилбар хямд.")

# --- MILP оновчлол ---
with tab_milp:
    st.markdown("**Block 3 — Цаг тутмын MILP оновчлол** (grid-холболттой, LinDistFlow, "
                "4 улирлын төлөөлөх өдөр). PV/батарейн хэмжээ ба диспэтчийг нэгэн зэрэг оновчилно.")
    st.caption("Анхааруулга: бүх сүлжээг бодоход ~1.5 минут болдог. Үр дүн кэшлэгдэнэ.")

    if st.button("⚡ MILP оновчлол ажиллуулах", type="primary"):
        with st.spinner("Оновчлол хийж байна… (CBC солвер, 35 сүлжээ)"):
            milp = run_milp(asdict(econ), asdict(g), use_api)
        st.session_state['milp'] = milp

    milp = st.session_state.get('milp')
    if milp:
        ms = milp['summary']
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Жилийн нийт зардал", f"${ms['total_annual_cost']:,.0f}")
        m2.metric("Нийт CAPEX", f"${ms['total_capex']:,.0f}")
        m3.metric("Систем LCOE", f"${ms['system_lcoe']:.3f}/кВт·ц" if ms['system_lcoe'] else "—")
        m4.metric("Шийдсэн сүлжээ", f"{ms['n_solved']}/{ms['n_networks']}")
        n1, n2, n3 = st.columns(3)
        n1.metric("Нийт PV", f"{ms['total_pv_kw']:,.0f} кВт")
        n2.metric("Нийт батарей", f"{ms['total_batt_kwh']:,.0f} кВт·ц")
        n3.metric("Жилийн импорт", f"{ms['total_import_kwh']:,.0f} кВт·ц")

        node_info = analysis['node_info']
        st.info("Станцуудыг газрын зураг дээр сонгож асаах/унтраах, дэлгэрэнгүй "
                "жагсаалтыг **🏭 Станц сонголт** табаас үзнэ үү.")
        rows = []
        for r in milp['results']:
            comp = r['component']
            rows.append({
                "Сүлжээ": ", ".join(comp['soum_names'][:3]) + (" …" if comp['soum_count'] > 3 else ""),
                "Сум": comp['soum_count'],
                "Ачаалал (кВт)": round(comp['total_load_kw'], 0),
                "Slack": node_info.get(r['slack'], {}).get('name', r['slack']),
                "PV (кВт)": round(r['total_pv_kw'], 0),
                "Батарей (кВт·ц)": round(r['total_batt_kwh'], 0),
                "Батарей (кВт)": round(r['total_batt_kw'], 0),
                "CAPEX ($)": round(r['capex'], 0),
                "Жилийн ($)": round(r['annual_cost'], 0),
                "Импорт (кВт·ц)": round(r['annual_import_kwh'], 0),
                "ENS (кВт·ц)": round(r['annual_ens_kwh'], 0),
                "LCOE ($/кВтц)": round(r['lcoe'], 3) if r['lcoe'] else None,
                "Статус": r['status'],
            })
        dfm = pd.DataFrame(rows).sort_values("Ачаалал (кВт)", ascending=False)
        st.dataframe(dfm, width='stretch', hide_index=True)
        st.download_button("⬇️ MILP үр дүн (CSV)", dfm.to_csv(index=False).encode('utf-8-sig'),
                           "milp_results.csv", "text/csv")
    else:
        st.info("Дээрх товчийг дарж оновчлолыг эхлүүлнэ үү.")

# --- Станц сонголт (асаах/унтраах + сонгосны дэлгэрэнгүй жагсаалт) ---
with tab_stations:
    milp = st.session_state.get('milp')
    if not milp:
        st.info("Эхлээд **⚡ MILP оновчлол** табд оновчлолыг ажиллуулна уу.")
    else:
        node_info = analysis['node_info']
        stations = []
        for r in milp['results']:
            for code, sz in r['sizing'].items():
                if sz['pv_kw'] <= 0 and sz['batt_kwh'] <= 0:
                    continue
                info = node_info.get(code, {})
                stations.append({
                    'code': code, 'name': info.get('name', code),
                    'lat': info.get('lat'), 'lon': info.get('lon'),
                    'pv_kw': sz['pv_kw'], 'batt_kwh': sz['batt_kwh'], 'batt_kw': sz['batt_kw'],
                    'lcoe': r['lcoe'], 'network': node_info.get(r['slack'], {}).get('name', r['slack']),
                })
        station_by_code = {s['code']: s for s in stations}
        all_codes = sorted(station_by_code, key=lambda c: -station_by_code[c]['pv_kw'])

        # --- Сонголтын төлөв (унтраалттай станцууд + undo/redo түүх) ---
        ss = st.session_state
        ss.setdefault('stn_off', set())
        ss.setdefault('stn_undo', [])
        ss.setdefault('stn_redo', [])
        ss.setdefault('stn_lastclick', None)
        ss.setdefault('stn_view', None)
        ss['stn_off'] = {c for c in ss['stn_off'] if c in station_by_code}  # хүчинтэй болгох
        off = ss['stn_off']
        shown_codes = [c for c in all_codes if c not in off]

        st.markdown(f"**Нийт {len(all_codes)} станц.** "
                    "Газрын зураг дээрх **икон дээр дарж** тухайн станцыг унтраана.")

        # --- Газрын зураг (харагдацыг хадгална) ---
        view = ss['stn_view']
        center = {'lat': view[0], 'lng': view[1]} if view else None
        zoom = view[2] if view else None
        shown = [station_by_code[c] for c in shown_codes if station_by_code[c]['lat'] is not None]
        fmap = build_milp_map(shown, lines=lines, center=center, zoom=zoom)
        state = st_folium(fmap, height=520, width=None, key='stn_map',
                          returned_objects=['last_object_clicked_tooltip', 'center', 'zoom'])
        if state:
            if state.get('center') and state.get('zoom') is not None:
                ss['stn_view'] = [state['center']['lat'], state['center']['lng'], state['zoom']]
        click = state.get('last_object_clicked_tooltip') if state else None

        # --- Reset / Undo / Redo товчнууд ---
        b1, b2, b3, b4 = st.columns([1, 1, 1, 3])
        reset = b1.button("🔄 Бүгдийг сэргээх")
        undo = b2.button("↩️ Буцаах", disabled=not ss['stn_undo'])
        redo = b3.button("↪️ Дахих", disabled=not ss['stn_redo'])
        b4.caption(f"🔴 Унтраалттай: {len(off)}  |  🟢 Асаалттай: {len(shown_codes)}")

        acted = False
        if reset:
            ss['stn_undo'].append(set(off)); ss['stn_redo'].clear()
            ss['stn_off'] = set(); ss['stn_lastclick'] = click; acted = True
        elif undo:
            ss['stn_redo'].append(set(off)); ss['stn_off'] = ss['stn_undo'].pop()
            ss['stn_lastclick'] = click; acted = True
        elif redo:
            ss['stn_undo'].append(set(off)); ss['stn_off'] = ss['stn_redo'].pop()
            ss['stn_lastclick'] = click; acted = True
        elif click and click in station_by_code and click != ss['stn_lastclick'] and click not in off:
            ss['stn_undo'].append(set(off)); ss['stn_redo'].clear()
            ss['stn_off'] = off | {click}; ss['stn_lastclick'] = click; acted = True
        ss['stn_undo'] = ss['stn_undo'][-50:]  # түүхийг хязгаарлах
        if acted:
            st.rerun()

        # --- Асаалттай станцуудын дэлгэрэнгүй жагсаалт ---
        st.subheader(f"📋 Асаалттай станцуудын дэлгэрэнгүй ({len(shown_codes)})")
        if shown_codes:
            srows = [{
                "Станц": station_by_code[c]['name'], "Код": c,
                "Нарны чадал (кВт)": round(station_by_code[c]['pv_kw'], 0),
                "Батарей (кВт·ц)": round(station_by_code[c]['batt_kwh'], 0),
                "Батарей чадал (кВт)": round(station_by_code[c]['batt_kw'], 0),
                "Сүлжээ": station_by_code[c]['network'],
                "LCOE ($/кВтц)": round(station_by_code[c]['lcoe'], 3) if station_by_code[c]['lcoe'] else None,
            } for c in shown_codes]
            sdf = pd.DataFrame(srows).sort_values("Нарны чадал (кВт)", ascending=False)
            t1, t2, t3 = st.columns(3)
            t1.metric("Асаалттай станц", f"{len(shown_codes)}")
            t2.metric("Нийт PV", f"{sum(station_by_code[c]['pv_kw'] for c in shown_codes):,.0f} кВт")
            t3.metric("Нийт батарей", f"{sum(station_by_code[c]['batt_kwh'] for c in shown_codes):,.0f} кВт·ц")
            st.dataframe(sdf, width='stretch', hide_index=True)
            st.download_button("⬇️ Жагсаалт (CSV)", sdf.to_csv(index=False).encode('utf-8-sig'),
                               "selected_stations.csv", "text/csv", key="sel_stations_csv")
        else:
            st.info("Бүх станц унтраалттай байна. '🔄 Бүгдийг сэргээх'-ийг дарна уу.")
