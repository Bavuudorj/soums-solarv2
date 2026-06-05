"""
Өгөгдөл унших, цахилгаан сүлжээний граф байгуулах, нэвтрүүлэх чадварыг
харгалзан "төвлөрсөн vs тараангуй" хангамжийн хамгийн бага зардлыг тооцоолох.
"""

import re
import math
from collections import defaultdict, deque

import pandas as pd

from solar import Assumptions, size_solar_system


# ---------------------------------------------------------------------------
# Баганын нэр таних туслахууд
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
    """Кодыг цэвэр мөр болгож буцаана (хоосон бол None)."""
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Файл унших
# ---------------------------------------------------------------------------

def load_soums(path):
    df = pd.read_excel(path)
    cols = {
        'код': pick_column(df, 'Код'),
        'аймаг': pick_column(df, 'Аймаг'),
        'сум': pick_column(df, 'Сум'),
        'төрөл': pick_column(df, 'Төрөл'),
        'lat': pick_column(df, 'Өргөрөг'),
        'lon': pick_column(df, 'Уртраг'),
        'хэрэглээ_квт': pick_column(df, 'Хэрэглээ_кВт', 'Хэрэглээ кВт', 'Хэрэглээ'),
    }
    missing = [k for k in ('сум', 'lat', 'lon', 'хэрэглээ_квт') if cols[k] is None]
    if missing:
        raise ValueError(f"soums.xlsx-д дараах багана олдсонгүй: {missing}")

    out = pd.DataFrame()
    for std, orig in cols.items():
        out[std] = df[orig] if orig is not None else None
    out['lat'] = pd.to_numeric(out['lat'], errors='coerce')
    out['lon'] = pd.to_numeric(out['lon'], errors='coerce')
    out['хэрэглээ_квт'] = pd.to_numeric(out['хэрэглээ_квт'], errors='coerce')
    out = out.dropna(subset=['lat', 'lon']).reset_index(drop=True)
    return out


def load_lines(path):
    df = pd.read_excel(path)
    cols = {
        'эхлэл_код': pick_column(df, 'Эхлэл код'),
        'дуусах_код': pick_column(df, 'Дуусах код'),
        'эхлэл_нэр': pick_column(df, 'Сум', 'Эхлэл нэр'),
        'дуусах_нэр': pick_column(df, 'Дуусах нэр'),
        'эхлэл_lat': pick_column(df, 'Эхлэл_lat', 'Эхлэл lat'),
        'эхлэл_lon': pick_column(df, 'Эхлэл_lon', 'Эхлэл lon'),
        'дуусах_lat': pick_column(df, 'Дуусах_lat', 'Дуусах lat'),
        'дуусах_lon': pick_column(df, 'Дуусах_lon', 'Дуусах lon'),
        'урт_хэмжсэн': pick_column(df, 'Зургаас хэмжсэн урт (км)', 'Хэмжсэн урт'),
        'урт_шулуун': pick_column(df, 'Шулууны урт (км)', 'Шулуун урт'),
        'чадвар_мвт': pick_column(df, 'Чадвар_МВт', 'Чадвар МВт', 'Чадвар'),
        'хүчдэл_кв': pick_column(df, 'Хүчдэл_кВ', 'Хүчдэл кВ', 'Хүчдэл_кВт', 'Хүчдэл'),
    }
    needed = ['эхлэл_lat', 'эхлэл_lon', 'дуусах_lat', 'дуусах_lon']
    missing = [k for k in needed if cols[k] is None]
    if missing:
        raise ValueError(f"lines.xlsx-д дараах координатын багана олдсонгүй: {missing}")

    out = pd.DataFrame()
    for std, orig in cols.items():
        out[std] = df[orig] if orig is not None else None
    for c in ('эхлэл_lat', 'эхлэл_lon', 'дуусах_lat', 'дуусах_lon',
              'урт_хэмжсэн', 'урт_шулуун', 'чадвар_мвт'):
        out[c] = pd.to_numeric(out[c], errors='coerce')
    out = out.dropna(subset=needed).reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Граф байгуулах
# ---------------------------------------------------------------------------

def build_node_index(soums, lines):
    """код -> (lat, lon) ба код -> нэр толь бичиг."""
    coords, names = {}, {}
    for _, r in soums.iterrows():
        c = _code(r['код'])
        if c and not (pd.isna(r['lat']) or pd.isna(r['lon'])):
            coords[c] = (float(r['lat']), float(r['lon']))
            names[c] = str(r['сум']) if not pd.isna(r['сум']) else c
    for _, r in lines.iterrows():
        for code, nm, la, lo in [
            (r['эхлэл_код'], r['эхлэл_нэр'], r['эхлэл_lat'], r['эхлэл_lon']),
            (r['дуусах_код'], r['дуусах_нэр'], r['дуусах_lat'], r['дуусах_lon']),
        ]:
            c = _code(code)
            if c and c not in coords and not (pd.isna(la) or pd.isna(lo)):
                coords[c] = (float(la), float(lo))
                names.setdefault(c, str(nm) if not pd.isna(nm) else c)
    return coords, names


def build_adjacency(lines):
    """
    adj[a][b] = тухайн хосыг холбосон шугамын нэвтрүүлэх чадвар (МВт).
    Тодорхойгүй (NaN) чадварыг хязгааргүй (inf) гэж үзнэ — өөрөөр хэлбэл
    "хүрэлцэнэ гэж таамаглана". Хэд хэдэн зэрэгцээ шугам байвал хамгийн ихийг авна.
    """
    adj = defaultdict(dict)
    for _, r in lines.iterrows():
        a, b = _code(r['эхлэл_код']), _code(r['дуусах_код'])
        if not a or not b or a == b:
            continue
        cap = r['чадвар_мвт']
        cap_val = math.inf if pd.isna(cap) else float(cap)
        for x, y in ((a, b), (b, a)):
            adj[x][y] = max(adj[x].get(y, -math.inf), cap_val)
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
# Чадвараар хязгаарлагдсан төвлөрсөн хангамж боломжтой эсэх
# ---------------------------------------------------------------------------

def _check_root(root, adj, soum_loads):
    """
    root цэгт станц байрлуулж, BFS-ээр цацраг (radial) сүлжээ үүсгэн,
    шугам бүрийн дамжуулах урсгал (доош байрлах сумдын ачаалал) нь
    тухайн шугамын чадвараас хэтрэхгүй эсэхийг шалгана.
    Буцаах: (боломжтой_эсэх, тодорхойгүй_чадвар_ашигласан_эсэх, хүрэх_цэгүүд)
    """
    parent = {root: None}
    order = [root]
    dq = deque([root])
    while dq:
        u = dq.popleft()
        # Илүү их чадвартай шугамыг эхэлж сонгох (модыг сайжруулна)
        for v, cap in sorted(adj.get(u, {}).items(), key=lambda kv: -kv[1]):
            if v not in parent:
                parent[v] = u
                order.append(v)
                dq.append(v)

    # Дэд модны ачаалал (доороос дээш)
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
        flow_mw = sub[n] / 1000.0          # доош дамжих ачаалал (кВт -> МВт)
        cap = adj[p][n]
        if math.isinf(cap):
            used_unknown = True
        elif cap < flow_mw - 1e-9:
            return False, used_unknown, set(order)
    return True, used_unknown, set(order)


def centralized_feasible(comp_nodes, adj, soum_loads):
    """
    Сүлжээний аль нэг цэгт станц байрлуулбал бүх сумыг чадварын
    хязгаарт багтаан хангаж болох эсэх. Боломжтой эхний цэгийг (root) буцаана.
    """
    soum_nodes = [n for n in comp_nodes if n in soum_loads]
    if not soum_nodes:
        return False, None, False
    # Ачаалал ихтэй цэгүүдийг эхэлж туршвал төв байрлал олдох магадлал өндөр
    candidates = sorted(comp_nodes, key=lambda n: -soum_loads.get(n, 0.0))
    for root in candidates:
        ok, used_unknown, reached = _check_root(root, adj, soum_loads)
        if ok and all(s in reached for s in soum_nodes):
            return True, root, used_unknown
    return False, None, False


# ---------------------------------------------------------------------------
# Үндсэн дүн шинжилгээ
# ---------------------------------------------------------------------------

def analyze(soums, lines, assumptions: Assumptions):
    """
    Сүлжээ (component) бүрээр төвлөрсөн ба тараангуй хувилбарыг тооцоолж,
    чадварын хязгаарыг харгалзан хамгийн бага зардлын зөвлөмжийг гаргана.
    """
    coords, names = build_node_index(soums, lines)
    adj = build_adjacency(lines)
    soum_loads = {}
    for _, r in soums.iterrows():
        c = _code(r['код'])
        if c and not pd.isna(r['хэрэглээ_квт']):
            soum_loads[c] = float(r['хэрэглээ_квт'])

    all_nodes = set(adj) | set(soum_loads)
    comps = find_components(adj, all_nodes)

    components = []
    code_to_comp = {}
    for i, comp in enumerate(comps):
        soum_codes = [n for n in comp if n in soum_loads]
        if not soum_codes:
            continue  # ачаалалгүй сүлжээ (зөвхөн зангилаа) — алгасна
        total_load = sum(soum_loads[c] for c in soum_codes)
        soum_names = sorted(names.get(c, c) for c in soum_codes)

        # Тараангуй: сум бүр өөрийн станцтай
        per_soum = {c: size_solar_system(soum_loads[c], assumptions) for c in soum_codes}
        distributed_cost = sum(s['cost_total'] for s in per_soum.values())

        # Төвлөрсөн: нэг станц бүх сүлжээг
        central = size_solar_system(total_load, assumptions)
        centralized_cost = central['cost_total']

        feasible, plant_code, used_unknown = centralized_feasible(comp, adj, soum_loads)

        if feasible and centralized_cost <= distributed_cost:
            recommended = 'centralized'
            recommended_cost = centralized_cost
        else:
            recommended = 'distributed'
            recommended_cost = distributed_cost
            if not feasible:
                plant_code = None

        result = {
            'id': i,
            'nodes': comp,
            'soum_codes': soum_codes,
            'soum_names': soum_names,
            'soum_count': len(soum_codes),
            'total_load_kw': total_load,
            'distributed_cost': distributed_cost,
            'centralized_cost': centralized_cost,
            'centralized_feasible': feasible,
            'capacity_unknown_used': used_unknown,
            'recommended': recommended,
            'recommended_cost': recommended_cost,
            'savings': distributed_cost - recommended_cost,
            'plant_code': plant_code,
            'plant_coord': coords.get(plant_code) if plant_code else None,
            'central_system': central,
            'per_soum_system': per_soum,
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
    }

    return {
        'components': components,
        'code_to_comp': code_to_comp,
        'coords': coords,
        'names': names,
        'soum_loads': soum_loads,
        'summary': summary,
    }
