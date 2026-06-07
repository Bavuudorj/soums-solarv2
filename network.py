"""
Өгөгдөл унших (soums_v2 / lines_v2), цахилгаан сүлжээний граф байгуулах,
шугамын нэвтрүүлэх чадварыг (хүчдэл+уртаас тооцоолсон) харгалзан
"төвлөрсөн vs тараангуй" хангамжийн хамгийн бага зардлыг тооцоолох.

Бүх дотоод тооцоо кВт нэгжээр явагдана (Ачаалал (МВт) -> ×1000 -> кВт).
"""

import re
import math
from collections import defaultdict, deque

import pandas as pd

from solar import Assumptions, size_solar_system
from capacity import GridParams, line_capacity_kw


# ---------------------------------------------------------------------------
# Баганын нэр таних
# ---------------------------------------------------------------------------

def normalize_key(text):
    t = str(text).strip().lower()
    t = re.sub(r'[\s\-–—_()/\\.,]+', '', t)
    return t


def pick_column(df, *candidates):
    norm_map = {}
    for c in df.columns:
        norm_map.setdefault(normalize_key(c), c)
    for cand in candidates:
        key = normalize_key(cand)
        if key in norm_map:
            return norm_map[key]
    for cand in candidates:
        key = normalize_key(cand)
        for nk, orig in norm_map.items():
            if key and (key in nk or nk in key):
                return orig
    return None


def _code(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def parse_voltage(text):
    """'10', '10 кВ', 10.0 зэргээс тоон утга (кВ) гаргана."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    m = re.search(r'\d+(?:[.,]\d+)?', str(text))
    return float(m.group().replace(',', '.')) if m else None


# ---------------------------------------------------------------------------
# Файл унших (v2 ба хуучин формат хоёуланг дэмжинэ)
# ---------------------------------------------------------------------------

def load_soums(path):
    df = pd.read_excel(path)
    code_c = pick_column(df, 'Код')
    aimag_c = pick_column(df, 'Аймаг')
    name_c = pick_column(df, 'Цэгийн нэр', 'Сум', 'Нэр')
    type_c = pick_column(df, 'Төрөл')
    lat_c = pick_column(df, 'Өргөрөг (lat)', 'Өргөрөг')
    lon_c = pick_column(df, 'Уртраг (lon)', 'Уртраг')
    mw_c = pick_column(df, 'Ачаалал (МВт)', 'Ачаалал МВт', 'Ачаалал')
    kw_c = pick_column(df, 'Хэрэглээ_кВт', 'Хэрэглээ кВт', 'Хэрэглээ')

    if name_c is None or lat_c is None or lon_c is None:
        raise ValueError("soums файлд нэр/координатын багана олдсонгүй.")

    out = pd.DataFrame()
    out['код'] = df[code_c] if code_c else None
    out['аймаг'] = df[aimag_c] if aimag_c else None
    out['сум'] = df[name_c]
    out['төрөл'] = df[type_c] if type_c else None
    out['lat'] = pd.to_numeric(df[lat_c], errors='coerce')
    out['lon'] = pd.to_numeric(df[lon_c], errors='coerce')

    # Ачаалал -> кВт (МВт байвал ×1000)
    if mw_c is not None:
        out['хэрэглээ_квт'] = pd.to_numeric(df[mw_c], errors='coerce') * 1000.0
    elif kw_c is not None:
        out['хэрэглээ_квт'] = pd.to_numeric(df[kw_c], errors='coerce')
    else:
        out['хэрэглээ_квт'] = float('nan')

    out = out.dropna(subset=['lat', 'lon']).reset_index(drop=True)
    return out


def load_lines(path):
    df = pd.read_excel(path)
    cols = {
        'эхлэл_код': pick_column(df, 'Эхлэл код'),
        'дуусах_код': pick_column(df, 'Төгсгөл код', 'Дуусах код'),
        'эхлэл_нэр': pick_column(df, 'Эхлэл нэр', 'Сум'),
        'дуусах_нэр': pick_column(df, 'Төгсгөл нэр', 'Дуусах нэр'),
        'эхлэл_lat': pick_column(df, 'Эхлэл өргөрөг', 'Эхлэл_lat', 'Эхлэл lat'),
        'эхлэл_lon': pick_column(df, 'Эхлэл уртраг', 'Эхлэл_lon', 'Эхлэл lon'),
        'дуусах_lat': pick_column(df, 'Төгсгөл өргөрөг', 'Дуусах_lat', 'Дуусах lat'),
        'дуусах_lon': pick_column(df, 'Төгсгөл уртраг', 'Дуусах_lon', 'Дуусах lon'),
        'урт': pick_column(df, 'Шулууны урт (км)', 'Зургаас хэмжсэн урт (км)', 'Урт'),
        'хүчдэл_кв': pick_column(df, 'Хүчдэл (кВ)', 'Хүчдэл_кВ', 'Хүчдэл кВ', 'Хүчдэл'),
    }
    needed = ['эхлэл_lat', 'эхлэл_lon', 'дуусах_lat', 'дуусах_lon']
    missing = [k for k in needed if cols[k] is None]
    if missing:
        raise ValueError(f"lines файлд координатын багана олдсонгүй: {missing}")

    out = pd.DataFrame()
    for std, orig in cols.items():
        out[std] = df[orig] if orig is not None else None
    for c in ('эхлэл_lat', 'эхлэл_lon', 'дуусах_lat', 'дуусах_lon', 'урт'):
        out[c] = pd.to_numeric(out[c], errors='coerce')
    out['хүчдэл_num'] = out['хүчдэл_кв'].apply(parse_voltage)
    out = out.dropna(subset=needed).reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Граф ба зангилааны мэдээлэл
# ---------------------------------------------------------------------------

def build_node_info(soums, lines):
    """код -> {name, aimag, type, lat, lon, load_kw}."""
    info = {}
    for _, r in soums.iterrows():
        c = _code(r['код'])
        if not c or pd.isna(r['lat']) or pd.isna(r['lon']):
            continue
        load = r['хэрэглээ_квт']
        info[c] = {
            'name': str(r['сум']) if not pd.isna(r['сум']) else c,
            'aimag': str(r['аймаг']) if not pd.isna(r['аймаг']) else None,
            'type': str(r['төрөл']) if not pd.isna(r['төрөл']) else None,
            'lat': float(r['lat']), 'lon': float(r['lon']),
            'load_kw': float(load) if not pd.isna(load) else None,
        }
    for _, r in lines.iterrows():
        for code, nm, la, lo in [
            (r['эхлэл_код'], r['эхлэл_нэр'], r['эхлэл_lat'], r['эхлэл_lon']),
            (r['дуусах_код'], r['дуусах_нэр'], r['дуусах_lat'], r['дуусах_lon']),
        ]:
            c = _code(code)
            if c and c not in info and not (pd.isna(la) or pd.isna(lo)):
                info[c] = {
                    'name': str(nm) if not pd.isna(nm) else c,
                    'aimag': None, 'type': None,
                    'lat': float(la), 'lon': float(lo), 'load_kw': None,
                }
    return info


def build_adjacency(lines, grid: GridParams):
    """
    adj[a][b] = тухайн хосыг холбосон шугамын нэвтрүүлэх чадвар (кВт).
    Чадварыг хүчдэл+уртаас тооцоолно. Хүчдэл тодорхойгүй бол хязгааргүй (inf).
    Зэрэгцээ шугам байвал чадварыг нэмнэ.
    """
    adj = defaultdict(dict)
    for _, r in lines.iterrows():
        a, b = _code(r['эхлэл_код']), _code(r['дуусах_код'])
        if not a or not b or a == b:
            continue
        cap = line_capacity_kw(r['хүчдэл_num'], r['урт'], grid)
        cap_val = math.inf if cap is None else float(cap)
        for x, y in ((a, b), (b, a)):
            prev = adj[x].get(y)
            if prev is None:
                adj[x][y] = cap_val
            elif math.isinf(prev) or math.isinf(cap_val):
                adj[x][y] = math.inf
            else:
                adj[x][y] = prev + cap_val   # зэрэгцээ шугам -> нэмэгдэнэ
    return adj


def find_components(adj, all_nodes):
    seen, comps = set(), []
    for start in all_nodes:
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.add(x)
            for v in adj.get(x, {}):
                if v not in seen:
                    stack.append(v)
        comps.append(comp)
    return comps


# ---------------------------------------------------------------------------
# Чадвараар хязгаарлагдсан төвлөрсөн хангамж (бүгд кВт)
# ---------------------------------------------------------------------------

def _check_root(root, adj, soum_loads):
    parent = {root: None}
    order = [root]
    dq = deque([root])
    while dq:
        u = dq.popleft()
        for v, cap in sorted(adj.get(u, {}).items(), key=lambda kv: -kv[1]):
            if v not in parent:
                parent[v] = u
                order.append(v)
                dq.append(v)

    sub = {n: float(soum_loads.get(n, 0.0)) for n in order}
    for n in reversed(order):
        p = parent[n]
        if p is not None:
            sub[p] += sub[n]

    used_unknown = False
    for n in order:
        p = parent[n]
        if p is None:
            continue
        flow_kw = sub[n]                 # доош дамжих ачаалал (кВт)
        cap = adj[p][n]                  # чадвар (кВт)
        if math.isinf(cap):
            used_unknown = True
        elif cap < flow_kw - 1e-6:
            return False, used_unknown, set(order)
    return True, used_unknown, set(order)


def centralized_feasible(comp_nodes, adj, soum_loads):
    soum_nodes = [n for n in comp_nodes if n in soum_loads]
    if not soum_nodes:
        return False, None, False
    candidates = sorted(comp_nodes, key=lambda n: -soum_loads.get(n, 0.0))
    for root in candidates:
        ok, used_unknown, reached = _check_root(root, adj, soum_loads)
        if ok and all(s in reached for s in soum_nodes):
            return True, root, used_unknown
    return False, None, False


# ---------------------------------------------------------------------------
# Үндсэн дүн шинжилгээ
# ---------------------------------------------------------------------------

def analyze(soums, lines, assumptions: Assumptions, grid: GridParams = None):
    if grid is None:
        grid = GridParams()

    node_info = build_node_info(soums, lines)
    adj = build_adjacency(lines, grid)
    soum_loads = {c: v['load_kw'] for c, v in node_info.items()
                  if v['load_kw'] is not None and v['load_kw'] > 0}

    all_nodes = set(adj) | set(node_info)
    comps = find_components(adj, all_nodes)

    components = []
    code_to_comp = {}
    for i, comp in enumerate(comps):
        soum_codes = [n for n in comp if n in soum_loads]
        if not soum_codes:
            continue
        total_load = sum(soum_loads[c] for c in soum_codes)
        soum_names = sorted(node_info.get(c, {}).get('name', c) for c in soum_codes)

        per_soum = {c: size_solar_system(soum_loads[c], assumptions) for c in soum_codes}
        distributed_cost = sum(s['cost_total'] for s in per_soum.values())
        central = size_solar_system(total_load, assumptions)
        centralized_cost = central['cost_total']

        feasible, plant_code, used_unknown = centralized_feasible(comp, adj, soum_loads)
        if feasible and centralized_cost <= distributed_cost:
            recommended, recommended_cost = 'centralized', centralized_cost
        else:
            recommended, recommended_cost = 'distributed', distributed_cost
            if not feasible:
                plant_code = None

        result = {
            'id': i, 'nodes': comp,
            'soum_codes': soum_codes, 'soum_names': soum_names,
            'soum_count': len(soum_codes), 'total_load_kw': total_load,
            'distributed_cost': distributed_cost, 'centralized_cost': centralized_cost,
            'centralized_feasible': feasible, 'capacity_unknown_used': used_unknown,
            'recommended': recommended, 'recommended_cost': recommended_cost,
            'savings': distributed_cost - recommended_cost,
            'plant_code': plant_code,
            'plant_coord': (node_info[plant_code]['lat'], node_info[plant_code]['lon'])
                           if plant_code and plant_code in node_info else None,
            'central_system': central, 'per_soum_system': per_soum,
        }
        components.append(result)
        for c in soum_codes:
            code_to_comp[c] = result

    summary = {
        'total_min_cost': sum(r['recommended_cost'] for r in components),
        'total_distributed_cost': sum(r['distributed_cost'] for r in components),
        'total_savings': sum(r['savings'] for r in components),
        'n_networks': len(components),
        'n_centralized': sum(1 for r in components if r['recommended'] == 'centralized'),
        'n_distributed': sum(1 for r in components if r['recommended'] == 'distributed'),
        'total_load_kw': sum(r['total_load_kw'] for r in components),
        'n_load_points': len(soum_loads),
    }

    return {
        'components': components, 'code_to_comp': code_to_comp,
        'node_info': node_info, 'soum_loads': soum_loads,
        'adj': adj, 'grid': grid, 'summary': summary,
    }
