"""
Streamlit веб апп — Сумдын нарны эрчим хүчний хангамжийн төлөвлөлт.

Ажиллуулах:  streamlit run app.py
"""

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from solar import Assumptions, size_solar_system
from network import load_soums, load_lines, analyze
from mapbuilder import build_map

st.set_page_config(page_title="Нарны хангамжийн төлөвлөлт", layout="wide")


@st.cache_data
def get_data():
    return load_soums("soums.xlsx"), load_lines("lines.xlsx")


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
    a.autonomy_days = st.slider("Батарейн нөөц (өдөр)", 1.0, 3.0, 1.0, 0.5)
    a.performance_ratio = st.slider("Системийн ашиг (PR)", 0.60, 0.90, 0.75, 0.01)
    a.battery_dod = st.slider("Батарей DoD", 0.50, 0.95, 0.80, 0.05)
    st.divider()
    a.cost_per_wp = st.number_input("PV өртөг ($/Вт)", value=0.9, step=0.1, format="%.2f")
    a.cost_per_kwh = st.number_input("Батарей өртөг ($/кВт·ц)", value=350.0, step=10.0)
    a.fixed_cost = st.number_input("Станцын тогтмол зардал ($)", value=8000.0, step=500.0)
    a.panel_wp = st.number_input("Панелийн чадал (Вт)", value=550.0, step=10.0)

try:
    soums, lines = get_data()
except Exception as e:
    st.error(f"Өгөгдөл уншихад алдаа гарлаа: {e}")
    st.stop()

analysis = analyze(soums, lines, a)
s = analysis['summary']
comps = analysis['components']

# --- Нийт үзүүлэлт ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Нийт хамгийн бага зардал", f"${s['total_min_cost']:,.0f}")
c2.metric("Хэмнэлт (vs тараангуй)", f"${s['total_savings']:,.0f}")
c3.metric("Сүлжээ", f"{s['n_networks']}",
          help=f"Төвлөрсөн: {s['n_centralized']} | Тараангуй: {s['n_distributed']}")
c4.metric("Нийт ачаалал", f"{s['total_load_kw']:,.0f} кВт")

tab_map, tab_table, tab_detail = st.tabs(["🗺️ Газрын зураг", "📋 Сүлжээний хүснэгт", "🔍 Дэлгэрэнгүй"])

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
            "Зөвлөмж": "Төвлөрсөн" if r['recommended'] == 'centralized' else "Тараангуй",
            "Чадвар хүрэх": "✓" if r['centralized_feasible'] else "✗",
            "PV (кВт)": round(r['central_system']['pv_kwp'], 1),
            "Батарей (кВт·ц)": round(r['central_system']['battery_kwh'], 1),
            "Төвлөрсөн ($)": round(r['centralized_cost'], 0),
            "Тараангуй ($)": round(r['distributed_cost'], 0),
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
    names = analysis['names']
    soum_loads = analysis['soum_loads']
    options = sorted(soum_loads.keys(), key=lambda c: names.get(c, c))
    label = {c: f"{names.get(c, c)} ({soum_loads[c]:.0f} кВт)" for c in options}
    sel = st.selectbox("Сум сонгох", options, format_func=lambda c: label[c])

    if sel:
        own = size_solar_system(soum_loads[sel], a)
        comp = code_to_comp.get(sel)
        st.subheader(f"{names.get(sel, sel)} — өөрийн систем (тараангуй)")
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
                        "**Зөвлөмж: ТАРААНГУЙ** — шугамын нэвтрүүлэх чадвар хүрэлцэхгүй тул "
                        "сум бүрийг тусад нь хангах шаардлагатай."
                    )
                else:
                    st.warning("**Зөвлөмж: ТАРААНГУЙ** — энэ тохиолдолд тараангуй хувилбар хямд.")
