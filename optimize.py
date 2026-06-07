"""
Block 3 — Хоёр шатлалт оновчлол (LP/MILP).

Сүлжээ (component) бүрт grid-холболттой, LinDistFlow сүлжээ-холбоост загвараар
PV/батарейн хэмжээ ба цаг тутмын диспэтчийг нэгэн зэрэг оновчлоно.

  • Slack = хамгийн өндөр хүчдэлийн зангилаа (grid импорт/экспорт энд)
  • 4 улирлын төлөөлөх өдөр × 24 цаг
  • Зорилго: annualized нийт зардал (CRF·CAPEX + O&M + ажиллагаа)
  • Хязгаар: C1 баланс, C2 PV, C3–C4 батарей, C5 шугам (thermal + voltage),
            C6 элэгдэл, C7 найдвартай байдал
"""

import math
from dataclasses import dataclass
from collections import defaultdict, deque

import pulp

from capacity import GridParams, _conductor_for
from profiles import SEASONS


@dataclass
class EconParams:
    c_pv: float = 800.0       # PV CAPEX, $/кВт
    c_be: float = 300.0       # Батарей энерги CAPEX, $/кВт·ц
    c_bp: float = 200.0       # Батарей чадал CAPEX, $/кВт
    m_pv: float = 12.0        # PV O&M, $/кВт/жил
    m_b: float = 5.0          # Батарей O&M, $/кВт/жил
    lambda_imp: float = 0.08  # Импорт тариф, $/кВт·ц
    lambda_exp: float = 0.04  # Экспорт (feed-in), $/кВт·ц
    voll: float = 1.0         # Үнэ цэнэ алдагдсан ачаалал (VoLL), $/кВт·ц
    r: float = 0.08           # Хямдруулалтын хүү
    N: int = 25               # Төслийн хугацаа, жил
    L_B: int = 10             # Батарейн ашиглалт, жил
    N_cyc: int = 4000         # Батарейн бүтэн цикл
    eta_ch: float = 0.95      # Цэнэглэх ашиг
    eta_dis: float = 0.95     # Цэнэг алдах ашиг
    soc_min: float = 0.10     # SoC доод хязгаар (хувь)
    soc_max: float = 1.00     # SoC дээд хязгаар (хувь)
    alpha: float = 0.99       # Найдвартай байдал (1-LPSP)


def crf(rate, years):
    if rate <= 0:
        return 1.0 / years
    f = (1 + rate) ** years
    return rate * f / (f - 1)


# ---------------------------------------------------------------------------
# Сүлжээний топологи (slack + цацраг мод + салааны параметр)
# ---------------------------------------------------------------------------

def build_topology(comp_nodes, node_info, line_edges, grid: GridParams):
    """
    line_edges: dict (a,b) -> (voltage_kv, length_km)  (хосын хамгийн өндөр хүчдэл)
    Буцаах: slack, parent, children, subtree, branch_param[(p,c)] = {Pth, kvolt}
    """
    tan_phi = math.tan(math.acos(max(min(grid.cos_phi, 1.0), 1e-6)))

    # Зэргэлдээ хүснэгт + хосын хамгийн өндөр хүчдэл
    adj = defaultdict(dict)
    for (a, b), (kv, ln) in line_edges.items():
        if a in comp_nodes and b in comp_nodes:
            for x, y in ((a, b), (b, a)):
                cur = adj[x].get(y)
                if cur is None or (kv or 0) > (cur[0] or 0):
                    adj[x][y] = (kv, ln)

    # Slack = хамгийн өндөр хүчдэлийн шугамд холбогдсон зангилаа
    best = None
    for a in adj:
        for b, (kv, ln) in adj[a].items():
            if kv is not None and (best is None or kv > best[1]):
                best = (a, kv)
    slack = best[0] if best else next(iter(comp_nodes))

    # BFS цацраг мод (өндөр хүчдэлийн шугамыг эхэлж сонгох)
    parent = {slack: None}
    order = [slack]
    dq = deque([slack])
    while dq:
        u = dq.popleft()
        for v, (kv, ln) in sorted(adj[u].items(), key=lambda kvp: -(kvp[1][0] or 0)):
            if v not in parent:
                parent[v] = u
                order.append(v)
                dq.append(v)

    children = defaultdict(list)
    for n, p in parent.items():
        if p is not None:
            children[p].append(n)

    # Дэд мод (descendants, өөрийгөө оруулаад)
    subtree = {n: {n} for n in order}
    for n in reversed(order):
        p = parent[n]
        if p is not None:
            subtree[p] |= subtree[n]

    # Салааны параметр
    branch = {}
    for n in order:
        p = parent[n]
        if p is None:
            continue
        kv, ln = adj[p][n]
        if kv is None or kv <= 0:
            branch[(p, n)] = {'Pth': math.inf, 'kvolt': 0.0, 'kv': None}
        else:
            Imax, r, x = _conductor_for(kv)
            Pth = math.sqrt(3) * kv * Imax * grid.cos_phi
            ln_eff = ln if (ln and ln > 0) else grid.default_length_km
            kvolt = ln_eff * (r + x * tan_phi) / (10.0 * kv ** 2)  # ΔU% нэгж кВт тутамд
            branch[(p, n)] = {'Pth': Pth, 'kvolt': kvolt, 'kv': kv}
    return slack, parent, children, subtree, branch, adj


# ---------------------------------------------------------------------------
# Нэг сүлжээний оновчлол
# ---------------------------------------------------------------------------

def optimize_network(comp, node_info, line_edges, demand_rep, demand_w,
                     solar_by_code, econ: EconParams, grid: GridParams):
    comp_nodes = set(comp['nodes'])
    soum_codes = comp['soum_codes']
    slack, parent, children, subtree, branch, adj = build_topology(
        comp_nodes, node_info, line_edges, grid)

    # Grid импорт/экспортын хязгаар = slack-ийн хамгийн өндөр хүчдэлийн шугамын thermal
    grid_cap = 0.0
    for v, (kv, ln) in adj.get(slack, {}).items():
        if kv:
            Imax, r, x = _conductor_for(kv)
            grid_cap = max(grid_cap, math.sqrt(3) * kv * Imax * grid.cos_phi)
    if grid_cap <= 0:
        grid_cap = math.inf  # хүчдэл тодорхойгүй -> хязгааргүй

    prob = pulp.LpProblem("soum_milp", pulp.LpMinimize)
    H = range(24)
    dU_max = grid.dU_max

    # Хэмжээний хувьсагч (зөвхөн ачаалалтай зангилаа)
    xPV, EB, PB = {}, {}, {}
    for c in soum_codes:
        xPV[c] = pulp.LpVariable(f"xpv_{c}", lowBound=0)
        EB[c] = pulp.LpVariable(f"eb_{c}", lowBound=0)
        PB[c] = pulp.LpVariable(f"pb_{c}", lowBound=0)

    # Диспэтчийн хувьсагч
    g, pch, pdis, soc, ens = {}, {}, {}, {}, {}
    imp, exp = {}, {}
    for s in SEASONS:
        for t in H:
            imp[s, t] = pulp.LpVariable(f"imp_{s}_{t}", lowBound=0, upBound=grid_cap if grid_cap != math.inf else None)
            exp[s, t] = pulp.LpVariable(f"exp_{s}_{t}", lowBound=0, upBound=grid_cap if grid_cap != math.inf else None)
            for c in soum_codes:
                g[c, s, t] = pulp.LpVariable(f"g_{c}_{s}_{t}", lowBound=0)
                pch[c, s, t] = pulp.LpVariable(f"pch_{c}_{s}_{t}", lowBound=0)
                pdis[c, s, t] = pulp.LpVariable(f"pdis_{c}_{s}_{t}", lowBound=0)
                soc[c, s, t] = pulp.LpVariable(f"soc_{c}_{s}_{t}", lowBound=0)
                ens[c, s, t] = pulp.LpVariable(f"ens_{c}_{s}_{t}", lowBound=0)

    def demand(c, s, t):
        return node_info[c]['load_kw'] * demand_rep[s][t]

    def net_load(c, s, t):
        # эерэг = алдагдал (сүлжээнээс татна), сөрөг = илүүдэл (сүлжээ рүү)
        return demand(c, s, t) - g[c, s, t] - pdis[c, s, t] + pch[c, s, t] - ens[c, s, t]

    # Зорилго
    invest = pulp.lpSum(
        crf(econ.r, econ.N) * econ.c_pv * xPV[c]
        + crf(econ.r, econ.L_B) * (econ.c_be * EB[c] + econ.c_bp * PB[c])
        for c in soum_codes)
    om = pulp.lpSum(econ.m_pv * xPV[c] + econ.m_b * PB[c] for c in soum_codes)
    oper = pulp.lpSum(
        demand_w[s] * (econ.lambda_imp * imp[s, t] - econ.lambda_exp * exp[s, t]
                       + econ.voll * pulp.lpSum(ens[c, s, t] for c in soum_codes))
        for s in SEASONS for t in H)
    prob += invest + om + oper

    for s in SEASONS:
        for t in H:
            # Slack баланс: grid солилцоо = сүлжээний нийт алдагдал
            prob += imp[s, t] - exp[s, t] == pulp.lpSum(net_load(c, s, t) for c in comp_nodes if c in soum_codes)
            # Салааны thermal + voltage
            for (p, c), bp in branch.items():
                flow = pulp.lpSum(net_load(j, s, t) for j in subtree[c] if j in soum_codes)
                if bp['Pth'] != math.inf:
                    prob += flow <= bp['Pth']
                    prob += flow >= -bp['Pth']
            # Voltage: slack-аас зам дагуух хуримтлагдсан ΔU%
            for c in soum_codes:
                path = []
                node = c
                while parent[node] is not None:
                    path.append((parent[node], node))
                    node = parent[node]
                if path:
                    dv = pulp.lpSum(
                        branch[b]['kvolt'] * pulp.lpSum(net_load(j, s, t) for j in subtree[b[1]] if j in soum_codes)
                        for b in path)
                    prob += dv <= dU_max
                    prob += dv >= -dU_max
            # PV байгаа эсэх (C2)
            for c in soum_codes:
                prob += g[c, s, t] <= solar_by_code[c][s][t] * xPV[c]
            # Батарей (C4)
            for c in soum_codes:
                prob += soc[c, s, t] <= econ.soc_max * EB[c]
                prob += soc[c, s, t] >= econ.soc_min * EB[c]
                prob += pch[c, s, t] <= PB[c]
                prob += pdis[c, s, t] <= PB[c]
                prob += ens[c, s, t] <= demand(c, s, t)

    # Батарей SoC динамик (C3), өдөр тутам циклээр хаана
    for c in soum_codes:
        for s in SEASONS:
            for t in H:
                t2 = (t + 1) % 24
                prob += soc[c, s, t2] == soc[c, s, t] + econ.eta_ch * pch[c, s, t] - pdis[c, s, t] / econ.eta_dis
        # Элэгдэл (C6): жилийн нийт цэнэг алдалт
        prob += pulp.lpSum(demand_w[s] * pdis[c, s, t] for s in SEASONS for t in H) \
            <= econ.N_cyc * (econ.soc_max - econ.soc_min) * EB[c] / econ.L_B
        # Найдвартай байдал (C7)
        tot_d = sum(demand_w[s] * demand(c, s, t) for s in SEASONS for t in H)
        prob += pulp.lpSum(demand_w[s] * ens[c, s, t] for s in SEASONS for t in H) <= (1 - econ.alpha) * tot_d

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]

    sizing = {}
    for c in soum_codes:
        sizing[c] = {
            'pv_kw': xPV[c].value() or 0.0,
            'batt_kwh': EB[c].value() or 0.0,
            'batt_kw': PB[c].value() or 0.0,
        }
    served = sum(demand_w[s] * (demand(c, s, t) - (ens[c, s, t].value() or 0.0))
                 for c in soum_codes for s in SEASONS for t in H)
    ann_imp = sum(demand_w[s] * (imp[s, t].value() or 0.0) for s in SEASONS for t in H)
    ann_exp = sum(demand_w[s] * (exp[s, t].value() or 0.0) for s in SEASONS for t in H)
    ann_ens = sum(demand_w[s] * (ens[c, s, t].value() or 0.0)
                  for c in soum_codes for s in SEASONS for t in H)
    capex = sum(econ.c_pv * sizing[c]['pv_kw'] + econ.c_be * sizing[c]['batt_kwh']
                + econ.c_bp * sizing[c]['batt_kw'] for c in soum_codes)
    annual_cost = pulp.value(prob.objective) or 0.0

    return {
        'status': status, 'slack': slack, 'sizing': sizing,
        'annual_cost': annual_cost, 'capex': capex,
        'annual_import_kwh': ann_imp, 'annual_export_kwh': ann_exp,
        'annual_ens_kwh': ann_ens, 'served_kwh': served,
        'lcoe': (annual_cost / served) if served > 0 else None,
        'total_pv_kw': sum(v['pv_kw'] for v in sizing.values()),
        'total_batt_kwh': sum(v['batt_kwh'] for v in sizing.values()),
        'total_batt_kw': sum(v['batt_kw'] for v in sizing.values()),
    }


# ---------------------------------------------------------------------------
# Бүх сүлжээ
# ---------------------------------------------------------------------------

def build_line_edges(lines):
    """dict (a,b) -> (voltage_kv, length_km), хосын хамгийн өндөр хүчдэл."""
    from network import _code
    edges = {}
    for _, r in lines.iterrows():
        a, b = _code(r['эхлэл_код']), _code(r['дуусах_код'])
        if not a or not b or a == b:
            continue
        kv = r['хүчдэл_num'] if not (r['хүчдэл_num'] is None) else None
        try:
            kv = float(kv) if kv == kv else None
        except (TypeError, ValueError):
            kv = None
        ln = float(r['урт']) if r['урт'] == r['урт'] else None
        key = (a, b) if a < b else (b, a)
        cur = edges.get(key)
        if cur is None or (kv or 0) > (cur[0] or 0):
            edges[key] = (kv, ln)
    # хоёр чиглэлд хайхад хялбар болгох
    full = {}
    for (a, b), v in edges.items():
        full[(a, b)] = v
        full[(b, a)] = v
    return full


def optimize_all(analysis, lines, demand_rep, demand_w, solar_by_code,
                 econ: EconParams = None, grid: GridParams = None, progress=None):
    if econ is None:
        econ = EconParams()
    if grid is None:
        grid = analysis.get('grid') or GridParams()
    line_edges = build_line_edges(lines)
    node_info = analysis['node_info']

    results = []
    for i, comp in enumerate(analysis['components']):
        res = optimize_network(comp, node_info, line_edges, demand_rep, demand_w,
                               solar_by_code, econ, grid)
        res['component'] = comp
        results.append(res)
        if progress:
            progress(i + 1, len(analysis['components']))

    summary = {
        'total_annual_cost': sum(r['annual_cost'] for r in results),
        'total_capex': sum(r['capex'] for r in results),
        'total_pv_kw': sum(r['total_pv_kw'] for r in results),
        'total_batt_kwh': sum(r['total_batt_kwh'] for r in results),
        'total_batt_kw': sum(r['total_batt_kw'] for r in results),
        'total_import_kwh': sum(r['annual_import_kwh'] for r in results),
        'total_export_kwh': sum(r['annual_export_kwh'] for r in results),
        'total_ens_kwh': sum(r['annual_ens_kwh'] for r in results),
        'total_served_kwh': sum(r['served_kwh'] for r in results),
        'n_solved': sum(1 for r in results if r['status'] == 'Optimal'),
        'n_networks': len(results),
    }
    summary['system_lcoe'] = (summary['total_annual_cost'] / summary['total_served_kwh']
                              if summary['total_served_kwh'] > 0 else None)
    return {'results': results, 'summary': summary}
