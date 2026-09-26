"""
Сапсан (Siemens Velaro RUS, ЭВС1/ЭВС2) — процедурная модель для Blender 4.x / 5.x.

Строится по открытым данным (не заводская КД Siemens):
  * 10 вагонов: головные 25 535 мм, промежуточные 24 175 мм, всего 244 470 мм по кузовам
  * ширина кузова 3 265 мм, высота от УГР 4 400 мм, пол 1 360 мм
  * колея 1 520 мм, база тележки 2 500 мм, между центрами тележек 17 375 мм
  * центры тележек: головной 4 080 / 21 455, промежуточный 3 400 / 20 775 от начала вагона

Система координат (1 единица Blender = 1 м):
  X — вдоль состава, 0 = нос первого вагона, растёт к хвосту
  Y — поперёк, 0 = ось пути
  Z — вверх, 0 = уровень головки рельса (УГР)

Запуск:
  * в Blender: вкладка Scripting -> Open -> Run Script
  * без интерфейса: blender -b -P sapsan_velaro_rus.py -- --out ./out
  * как модуль bpy:  python sapsan_velaro_rus.py --out ./out
"""

import math
import os
import sys

import bpy  # noqa: I001 — bpy до bmesh (важно для pip-модуля bpy)
import bmesh
from mathutils import Vector

# ---------------------------------------------------------------------------
# Параметры (мм -> м)
# ---------------------------------------------------------------------------
MM = 0.001

BODY_WIDTH = 3265 * MM
BODY_HEIGHT = 4400 * MM          # верх крыши над УГР
FLOOR_HEIGHT = 1360 * MM
GAUGE = 1520 * MM
BOGIE_WHEELBASE = 2500 * MM
WHEEL_RADIUS = 460 * MM          # колесо Ø920
BODY_BOTTOM = 300 * MM           # низ юбки кузова
BODY_WIDEST_Z = 1900 * MM        # уровень наибольшей ширины

# (X начало, X конец) по таблице
CARS = [
    (0, 25535), (25535, 49710), (49710, 73885), (73885, 98060),
    (98060, 122235), (122235, 146410), (146410, 170585), (170585, 194760),
    (194760, 218935), (218935, 244470),
]
CARS = [(a * MM, b * MM) for a, b in CARS]

HEAD_BOGIES = (4080 * MM, 21455 * MM)
MID_BOGIES = (3400 * MM, 20775 * MM)

NOSE_LENGTH = 7.0                # длина обтекаемой части головы
NOSE_TIP_Z = 1.05                # высота кончика носа
CAR_GAP = 0.20                   # зазор кузова у каждого торца (место под переход)
PANTOGRAPH_CARS = (2, 7)         # индексы вагонов с токоприёмниками

# Окна / двери (высоты над УГР)
WIN_Z = (2.05, 2.85)
DOOR_Z = (1.36, 3.30)
DOOR_WIDTH = 0.90
WIN_WIDTH = 1.20
WIN_PITCH = 1.75

# Ливрея (высоты над УГР)
SKIRT_TOP = 0.85
STRIPE_TOP = 1.25
ROOF_Z = 3.95

# Разрешение сетки
PROFILE_SEGMENTS = 96
STEP_BODY = 0.25
STEP_NOSE = 0.10


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def spow(v, p):
    return math.copysign(abs(v) ** p, v)


def clear_scene():
    """Удаляет всё из текущего файла (безопасно и в интерфейсе Blender)."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights, bpy.data.worlds):
        for item in list(block):
            block.remove(item)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.length_unit = 'MILLIMETERS'
    sc.unit_settings.scale_length = 1.0


def make_material(name, color, metallic=0.0, roughness=0.4, emission=None, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 5.0
    return mat


def build_materials():
    return {
        "white": make_material("Sapsan_White", (0.85, 0.86, 0.87), roughness=0.25),
        "red": make_material("Sapsan_Red", (0.60, 0.02, 0.03), roughness=0.3),
        "skirt": make_material("Sapsan_Skirt", (0.08, 0.08, 0.09), roughness=0.6),
        "roof": make_material("Sapsan_Roof", (0.45, 0.46, 0.48), roughness=0.5),
        "glass": make_material("Sapsan_Glass", (0.01, 0.015, 0.02), metallic=0.3, roughness=0.05),
        "door": make_material("Sapsan_Door", (0.62, 0.63, 0.65), roughness=0.3),
        "light": make_material("Sapsan_Headlight", (1, 1, 1), emission=(1, 0.97, 0.9)),
        "tail": make_material("Sapsan_Taillight", (1, 0, 0), emission=(1, 0.05, 0.02)),
        "steel": make_material("Steel", (0.55, 0.55, 0.57), metallic=1.0, roughness=0.35),
        "dark": make_material("Dark_Metal", (0.05, 0.05, 0.05), metallic=0.6, roughness=0.5),
        "bellows": make_material("Bellows", (0.03, 0.03, 0.03), roughness=0.9),
        "sleeper": make_material("Sleeper_Concrete", (0.35, 0.34, 0.32), roughness=0.9),
        "ground": make_material("Ballast", (0.22, 0.2, 0.18), roughness=1.0),
    }


def new_object(name, mesh, collection, parent=None):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


# ---------------------------------------------------------------------------
# Поперечный профиль кузова: асимметричный суперэллипс
#   верхняя половина — (a, bt, nt), нижняя — (a, bb, nb), центр zc
# ---------------------------------------------------------------------------
BODY_PROFILE = dict(
    a=BODY_WIDTH / 2,
    zc=BODY_WIDEST_Z,
    bt=BODY_HEIGHT - BODY_WIDEST_Z,
    bb=BODY_WIDEST_Z - BODY_BOTTOM,
    nt=4.0,
    nb=5.0,
)


LEVELS = (SKIRT_TOP, STRIPE_TOP, WIN_Z[0], WIN_Z[1], DOOR_Z[1], ROOF_Z)
# полосы профиля между уровнями (снизу вверх, одна сторона)
BAND_KIND = ("skirt", "red", "white", "winband", "white", "white", "roof")
HALF_SEGMENTS = PROFILE_SEGMENTS // 2


def superellipse_point(prof, t):
    a, zc, bt, bb, nt, nb = (prof[k] for k in ("a", "zc", "bt", "bb", "nt", "nb"))
    c, s = math.cos(t), math.sin(t)
    if s >= 0:
        return a * spow(c, 2 / nt), zc + bt * spow(s, 2 / nt)
    return a * spow(c, 2 / nb), zc + bb * spow(s, 2 / nb)


def theta_of_z(prof, z):
    """Параметр точки правой боковины профиля на высоте z."""
    if z >= prof["zc"]:
        s = ((z - prof["zc"]) / prof["bt"]) ** (prof["nt"] / 2) if prof["bt"] > 1e-9 else 1.0
    else:
        s = -(((prof["zc"] - z) / prof["bb"]) ** (prof["nb"] / 2)) if prof["bb"] > 1e-9 else -1.0
    return math.asin(max(-1.0, min(1.0, s)))


def band_anchors(prof):
    a = [-math.pi / 2] + [theta_of_z(prof, z) for z in LEVELS] + [math.pi / 2]
    d = 0.002
    for i in range(len(a) - 2, 0, -1):
        a[i] = min(a[i], a[i + 1] - d)
    for i in range(1, len(a) - 1):
        a[i] = max(a[i], a[i - 1] + d)
    return a


def _band_counts():
    a = band_anchors(BODY_PROFILE)
    lengths = []
    for i in range(len(a) - 1):
        pts = [superellipse_point(BODY_PROFILE, a[i] + (a[i + 1] - a[i]) * k / 50) for k in range(51)]
        lengths.append(sum(math.dist(pts[k], pts[k + 1]) for k in range(50)))
    total = sum(lengths)
    return [max(2, round(L / total * HALF_SEGMENTS)) for L in lengths]


BAND_COUNTS = _band_counts()


def ring_thetas(prof):
    """Параметры точек кольца + вид полосы для каждого сегмента.
    Обход: низ по центру -> правая боковина -> крыша -> левая боковина -> низ."""
    a = band_anchors(prof)
    right, kinds = [], []
    for b, n in enumerate(BAND_COUNTS):
        for k in range(n):
            right.append(a[b] + (a[b + 1] - a[b]) * k / n)
            kinds.append(BAND_KIND[b])
    left = [math.pi - t for t in [math.pi / 2] + right[:0:-1]]
    return right + left, kinds + kinds[::-1]


def section(prof, x, thetas=None):
    if thetas is None:
        thetas = [2 * math.pi * i / PROFILE_SEGMENTS for i in range(PROFILE_SEGMENTS)]
    return [Vector((x, *superellipse_point(prof, t))) for t in thetas]


def nose_profile(s):
    """Профиль сечения носа, s = 0 (кончик) .. 1 (полное сечение)."""
    s = max(0.0, min(1.0, s))
    p = BODY_PROFILE
    zt_full = p["zc"] + p["bt"]
    zb_full = p["zc"] - p["bb"]
    a = p["a"] * (1 - (1 - s) ** 2.4) ** 0.5
    zt = NOSE_TIP_Z + (zt_full - NOSE_TIP_Z) * (1 - (1 - s) ** 1.8) ** 0.75
    zb = NOSE_TIP_Z - (NOSE_TIP_Z - zb_full) * (1 - (1 - s) ** 3) ** 0.5
    zc = NOSE_TIP_Z + (p["zc"] - NOSE_TIP_Z) * (1 - (1 - s) ** 2) ** 0.7
    k = smoothstep(s / 0.8)
    return dict(
        a=a, zc=zc, bt=max(zt - zc, 0.0), bb=max(zc - zb, 0.0),
        nt=2.2 + (p["nt"] - 2.2) * k, nb=2.5 + (p["nb"] - 2.5) * k,
    )


def end_profile(d):
    """Лёгкое скругление торца промежуточного вагона, d — расстояние до торца."""
    p = dict(BODY_PROFILE)
    f = 0.93 + 0.07 * smoothstep(d / 0.45)
    p["a"] *= f
    p["bt"] *= 0.96 + 0.04 * smoothstep(d / 0.45)
    p["bb"] *= f
    return p


# ---------------------------------------------------------------------------
# Раскладка окон и дверей (локальные X от начала вагона, нос/перед = 0)
# ---------------------------------------------------------------------------
def car_openings(length, is_head):
    doors, windows = [], []
    if is_head:
        doors.append((7.0, 7.0 + DOOR_WIDTH))
        start = 8.9
    else:
        doors.append((1.0, 1.0 + DOOR_WIDTH))
        start = 2.9
    end = length - 1.6
    x = start
    while x + WIN_WIDTH <= end:
        windows.append((x, x + WIN_WIDTH))
        x += WIN_PITCH
    if not is_head:
        doors.append((length - 1.0 - DOOR_WIDTH, length - 1.0))
        windows = [w for w in windows if w[1] < length - 1.2 - DOOR_WIDTH]
    return doors, windows


# ---------------------------------------------------------------------------
# Кузов
# ---------------------------------------------------------------------------
def profile_at(x, length, is_head):
    body_start = 0.0 if is_head else CAR_GAP
    body_end = length - CAR_GAP
    if is_head and x < NOSE_LENGTH:
        return nose_profile(x / NOSE_LENGTH)
    d = min(body_end - x, 99 if is_head else x - body_start)
    return end_profile(d) if d < 0.45 else BODY_PROFILE


def body_stations(length, is_head, doors, windows):
    xs = set()
    body_start = 0.0 if is_head else CAR_GAP
    body_end = length - CAR_GAP
    if is_head:
        n = int(NOSE_LENGTH / STEP_NOSE)
        xs.update(NOSE_LENGTH * (i / n) ** 1.6 for i in range(n + 1))
    else:
        xs.update(body_start + 0.45 * (i / 6) for i in range(7))
    xs.update(body_end - 0.45 * (i / 6) for i in range(7))
    x = body_start
    while x < body_end:
        xs.add(x)
        x += STEP_BODY
    for a, b in doors + windows:
        xs.update((a, b))
    if is_head:
        xs.update(CAB_WINDOW)
    xs = sorted(v for v in xs if body_start <= v <= body_end)
    out = [xs[0]]
    for v in xs[1:]:
        if v - out[-1] > 0.01:
            out.append(v)
    return out


CAB_WINDOW = (4.9, 5.9)
MAT_SLOTS = ("white", "red", "skirt", "roof", "glass", "door", "light", "tail")


def build_body_mesh(name, length, is_head, mats):
    doors, windows = car_openings(length, is_head)
    if is_head:
        windows = [CAB_WINDOW] + windows
    xs = body_stations(length, is_head, doors, windows)

    bm = bmesh.new()
    rings, kinds = [], None
    for x in xs:
        th, kinds = ring_thetas(profile_at(x, length, is_head))
        rings.append([bm.verts.new(p) for p in section(profile_at(x, length, is_head), x, th)])

    slot = {k: i for i, k in enumerate(MAT_SLOTS)}

    def in_ranges(v, ranges):
        return any(a <= v <= b for a, b in ranges)

    m = len(kinds)
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        xm = (xs[i] + xs[i + 1]) / 2
        is_door = in_ranges(xm, doors)
        is_win = in_ranges(xm, windows)
        for j in range(m):
            k = (j + 1) % m
            f = bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
            kind = kinds[j]
            if kind == "winband":
                kind = "glass" if (is_win or is_door) else "white"
            elif is_door and kind == "white":
                # дверь: полосы между красной и уровнем верха двери
                zc = (r0[j].co.z + r0[k].co.z) / 2
                if zc < DOOR_Z[1]:
                    kind = "door"
            f.material_index = slot[kind]
            f.smooth = True
    # крышка хвостового торца (и переднего у промежуточного)
    cap = bm.faces.new(list(reversed(rings[-1])))
    cap.material_index = slot["skirt"]
    if not is_head:
        cap = bm.faces.new(rings[0])
        cap.material_index = slot["skirt"]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for k in MAT_SLOTS:
        me.materials.append(mats[k])
    return me


# ---------------------------------------------------------------------------
# Накладки на нос: лобовое стекло и фары (гладкий контур, повторяют поверхность)
# ---------------------------------------------------------------------------
def nose_surface(x, t):
    prof = nose_profile(x / NOSE_LENGTH) if x < NOSE_LENGTH else BODY_PROFILE
    return Vector((x, *superellipse_point(prof, t)))


def nose_surface_z(x, z, side):
    prof = nose_profile(x / NOSE_LENGTH) if x < NOSE_LENGTH else BODY_PROFILE
    t = theta_of_z(prof, z)
    if side < 0:
        t = math.pi - t
    return Vector((x, *superellipse_point(prof, t)))


def offset_grid(points, off):
    """Сдвиг сетки точек (строки x столбцы) по нормали поверхности наружу."""
    rows, cols = len(points), len(points[0])
    out = []
    for i in range(rows):
        row = []
        for j in range(cols):
            p = points[i][j]
            du = points[min(i + 1, rows - 1)][j] - points[max(i - 1, 0)][j]
            dv = points[i][min(j + 1, cols - 1)] - points[i][max(j - 1, 0)]
            n = du.cross(dv)
            if n.length < 1e-9:
                n = Vector((0, p.y, p.z - 2.0))
            n.normalize()
            # наружу — от оси кузова
            if n.dot(Vector((0, p.y, p.z - BODY_WIDEST_Z)) + Vector((-0.3, 0, 0))) < 0:
                n = -n
            row.append(p + n * off)
        out.append(row)
    return out


def grid_mesh(name, grid, mat):
    bm = bmesh.new()
    vs = [[bm.verts.new(p) for p in row] for row in grid]
    for i in range(len(vs) - 1):
        for j in range(len(vs[0]) - 1):
            f = bm.faces.new((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]))
            f.smooth = True
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    return me


WINDSHIELD = dict(x0=1.45, x1=4.75, depth=1.55)


def build_windshield(mats):
    """Лобовое стекло-«визор»: по X от x0 до x1, по контуру — от линии
    z_edge(x) на левой боковине через крышу до правой."""
    x0, x1, depth = WINDSHIELD["x0"], WINDSHIELD["x1"], WINDSHIELD["depth"]
    nx, nt = 60, 48
    grid = []
    for i in range(nx + 1):
        u = i / nx
        x = x0 + (x1 - x0) * (1 - math.cos(u * math.pi)) / 2
        tt = (x - x0) / (x1 - x0)
        prof = nose_profile(x / NOSE_LENGTH)
        zt = prof["zc"] + prof["bt"]
        dz = depth * (max(tt, 0) ** 0.5) * max(1 - tt ** 5, 0) ** 0.5
        t_edge = theta_of_z(prof, max(zt - dz, prof["zc"] + 1e-3))
        row = []
        for j in range(nt + 1):
            t = t_edge + (math.pi - 2 * t_edge) * j / nt
            row.append(nose_surface(x, t))
        grid.append(row)
    return grid_mesh("Windshield", offset_grid(grid, 0.006), mats["glass"])


def build_headlights(mats, name="Headlights", mat_key="light"):
    """Фары: тёмный вытянутый корпус по бокам носа и светящиеся линзы в нём."""
    def lens(side, xa, xb, h0, off):
        nx, nz = 24, 8
        grid = []
        for i in range(nx + 1):
            u = i / nx
            x = xa + (xb - xa) * u
            zc = 1.40 + 0.10 * (x - 0.3)
            h = h0 * math.sin(math.pi * u) ** 0.5 + 1e-3
            grid.append([nose_surface_z(x, zc - h + 2 * h * k / nz, side) for k in range(nz + 1)])
        return offset_grid(grid, off)

    bm = bmesh.new()
    for side in (-1, 1):
        for grid, mi in ((lens(side, 0.30, 1.75, 0.11, 0.006), 0),
                         (lens(side, 0.55, 1.05, 0.05, 0.012), 1),
                         (lens(side, 1.15, 1.55, 0.04, 0.012), 1)):
            vs = [[bm.verts.new(p) for p in row] for row in grid]
            for i in range(len(vs) - 1):
                for j in range(len(vs[0]) - 1):
                    f = bm.faces.new((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]))
                    f.material_index = mi
                    f.smooth = True
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["glass"])
    me.materials.append(mats[mat_key])
    return me


def bogie_cutter(xc, mats, col):
    """Вырез в юбке кузова над тележкой."""
    me = bpy.data.meshes.new("cutter")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = xc + v.co.x * 3.9
        v.co.y *= 4.0
        v.co.z = -0.5 + (v.co.z + 0.5) * 1.5  # z: -0.5 .. 1.0
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["skirt"])
    obj = bpy.data.objects.new("cutter", me)
    col.objects.link(obj)
    return obj


def apply_boolean(target, cutters):
    for ct in cutters:
        mod = target.modifiers.new("cut", 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = ct
        with bpy.context.temp_override(object=target, active_object=target):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(ct, do_unlink=True)


# ---------------------------------------------------------------------------
# Тележка
# ---------------------------------------------------------------------------
def add_box(bm, center, size):
    geom = bmesh.ops.create_cube(bm, size=1.0)
    for v in geom["verts"]:
        v.co = Vector((center[0] + v.co.x * size[0],
                       center[1] + v.co.y * size[1],
                       center[2] + v.co.z * size[2]))
    return geom["verts"]


def add_cyl_y(bm, center, radius, depth, segs=32):
    geom = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                 radius1=radius, radius2=radius, depth=depth)
    for v in geom["verts"]:
        x, y, z = v.co
        v.co = Vector((center[0] + x, center[1] + z, center[2] + y))
    return geom["verts"]


def _merge_parts(name, parts, mat_list):
    """parts: [(bmesh, material_index)] -> mesh."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for part, mi in parts:
        for f in part.faces:
            f.material_index = mi
            f.smooth = False
        tmp = bpy.data.meshes.new("tmp")
        part.to_mesh(tmp)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        part.free()
    bm.to_mesh(me)
    bm.free()
    for m in mat_list:
        me.materials.append(m)
    return me


def build_wheelset(name, mats):
    """Колёсная пара, центр оси в начале координат, ось вращения — Y."""
    wy = GAUGE / 2 + 0.035
    bm_wheel, bm_steel, bm_dark = bmesh.new(), bmesh.new(), bmesh.new()
    for sy in (-1, 1):
        add_cyl_y(bm_wheel, (0, sy * wy, 0), WHEEL_RADIUS, 0.135, 48)
        add_cyl_y(bm_dark, (0, sy * (wy + 0.07), 0), WHEEL_RADIUS * 0.78, 0.01, 32)  # диск колеса
        add_cyl_y(bm_steel, (0, sy * (wy + 0.078), 0), 0.12, 0.012, 16)                # ступица
        for k in range(6):  # отверстия/метки, чтобы видно было вращение
            a = k * math.pi / 3
            c = Vector((math.cos(a) * 0.24, sy * (wy + 0.078), math.sin(a) * 0.24))
            add_cyl_y(bm_steel, c, 0.045, 0.012, 10)
        add_cyl_y(bm_steel, (0, sy * (wy - 0.25), 0), 0.32, 0.06, 32)  # тормозной диск
    add_cyl_y(bm_steel, (0, 0, 0), 0.085, 2.25, 24)
    return _merge_parts(name, [(bm_wheel, 0), (bm_dark, 1), (bm_steel, 0)],
                        [mats["steel"], mats["dark"]])


def build_bogie(name, mats):
    """Рама тележки (без колёсных пар)."""
    bm = bmesh.new()
    half = BOGIE_WHEELBASE / 2
    for sy in (-1, 1):
        add_box(bm, (0, sy * 1.02, 0.62), (3.3, 0.22, 0.30))
        for sx in (-1, 1):  # буксы
            add_box(bm, (sx * half, sy * 1.02, 0.46), (0.40, 0.26, 0.30))
    add_box(bm, (0, 0, 0.66), (0.5, 2.1, 0.28))
    bm_s = bmesh.new()
    for sx in (-1, 1):  # пружины (упрощённо)
        for sy in (-1, 1):
            add_cyl_y(bm_s, (sx * 0.45, sy * 1.02, 0.88), 0.12, 0.2, 16)
    return _merge_parts(name, [(bm, 0), (bm_s, 1)], [mats["dark"], mats["steel"]])


# ---------------------------------------------------------------------------
# Межвагонный переход (гармошка)
# ---------------------------------------------------------------------------
def build_gangway(name, mats):
    prof = dict(a=1.35, zc=2.3, bt=1.55, bb=1.25, nt=4.0, nb=4.0)
    bm = bmesh.new()
    folds = 8
    length = 2 * CAR_GAP + 0.06
    rings = []
    for i in range(folds * 2 + 1):
        x = -length / 2 + length * i / (folds * 2)
        k = 1.0 if i % 2 == 0 else 0.96
        p = dict(prof, a=prof["a"] * k, bt=prof["bt"] * k, bb=prof["bb"] * k)
        rings.append([bm.verts.new(v) for v in section(p, x)])
    m = PROFILE_SEGMENTS
    for i in range(len(rings) - 1):
        for j in range(m):
            k = (j + 1) % m
            bm.faces.new((rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["bellows"])
    return me


# ---------------------------------------------------------------------------
# Токоприёмник (однорычажный, поднят)
# ---------------------------------------------------------------------------
def build_pantograph(name, mats):
    bm = bmesh.new()
    base_z = BODY_HEIGHT - 0.03
    # изоляторы и рама основания
    for sx in (-0.6, 0.6):
        for sy in (-0.45, 0.45):
            add_cyl_y(bm, (sx, sy, base_z + 0.12), 0.07, 0.07, 12)
            add_box(bm, (sx, sy, base_z + 0.1), (0.1, 0.1, 0.2))
    add_box(bm, (0, 0, base_z + 0.22), (1.5, 1.0, 0.06))

    def bar(p0, p1, w):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        me_bm = bmesh.new()
        add_box(me_bm, (0, 0, 0), (w, w, 1.0))
        q = Vector((0, 0, 1)).rotation_difference(d.normalized())
        for v in me_bm.verts:
            v.co.z *= d.length
            v.co = q @ v.co + (p0 + p1) / 2
        tmp = bpy.data.meshes.new("tmp")
        me_bm.to_mesh(tmp)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        me_bm.free()

    knee = (-0.9, 0, base_z + 0.95)
    top = (0.35, 0, base_z + 1.75)
    for sy in (-0.3, 0.3):
        bar((0.55, sy, base_z + 0.25), (knee[0], sy * 0.3, knee[2]), 0.07)
    bar(knee, top, 0.05)
    bar((0.25, 0, base_z + 0.25), (-0.8, 0, base_z + 0.9), 0.03)
    # полоз
    add_box(bm, (top[0], 0, top[2] + 0.05), (0.08, 1.95, 0.05))
    for sy in (-1, 1):
        add_box(bm, (top[0], sy * 1.0, top[2]), (0.06, 0.12, 0.08))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["steel"])
    return me


# ---------------------------------------------------------------------------
# Путь
# ---------------------------------------------------------------------------
def build_track(col, mats, x0, x1):
    rail_y = GAUGE / 2 + 0.0365
    bm = bmesh.new()
    for sy in (-1, 1):
        add_box(bm, ((x0 + x1) / 2, sy * rail_y, -0.075), (x1 - x0, 0.073, 0.15))
        add_box(bm, ((x0 + x1) / 2, sy * rail_y, -0.14), (x1 - x0, 0.15, 0.02))
    me = bpy.data.meshes.new("Rails")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["steel"])
    new_object("Rails", me, col)

    bm = bmesh.new()
    add_box(bm, (0, 0, -0.23), (0.26, 2.75, 0.18))
    me = bpy.data.meshes.new("Sleeper")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["sleeper"])
    sl = new_object("Sleepers", me, col)
    sl.location.x = x0
    arr = sl.modifiers.new("Array", 'ARRAY')
    arr.use_relative_offset = False
    arr.use_constant_offset = True
    arr.constant_offset_displace = (0.6, 0, 0)
    arr.count = int((x1 - x0) / 0.6)

    bm = bmesh.new()
    verts = [bm.verts.new(v) for v in (
        (x0, -2.6, -0.32), (x1, -2.6, -0.32), (x1, -1.6, -0.14), (x0, -1.6, -0.14),
        (x1, 1.6, -0.14), (x0, 1.6, -0.14), (x1, 2.6, -0.32), (x0, 2.6, -0.32))]
    bm.faces.new((verts[0], verts[1], verts[2], verts[3]))
    bm.faces.new((verts[3], verts[2], verts[4], verts[5]))
    bm.faces.new((verts[5], verts[4], verts[6], verts[7]))
    me = bpy.data.meshes.new("Ballast")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["ground"])
    new_object("Ballast", me, col)


# ---------------------------------------------------------------------------
# Сборка состава
# ---------------------------------------------------------------------------
def build_train(with_track=True):
    clear_scene()
    mats = build_materials()
    scene = bpy.context.scene
    train_col = bpy.data.collections.new("Sapsan_Velaro_RUS")
    scene.collection.children.link(train_col)
    # общий «риг» состава: двигать/анимировать весь поезд — через него
    rig = bpy.data.objects.new("Sapsan_Rig", None)
    rig.empty_display_type = 'PLAIN_AXES'
    rig.empty_display_size = 5
    train_col.objects.link(rig)

    bogie_mesh = build_bogie("Bogie", mats)
    wheelset_mesh = build_wheelset("Wheelset", mats)
    gangway_mesh = build_gangway("Gangway", mats)
    panto_mesh = build_pantograph("Pantograph", mats)
    windshield_mesh = build_windshield(mats)
    light_mesh = build_headlights(mats)
    tail_mesh = build_headlights(mats, "Taillights", "tail")

    n = len(CARS)
    for i, (x0, x1) in enumerate(CARS):
        length = x1 - x0
        head = i in (0, n - 1)
        tail = i == n - 1
        name = f"Car{i + 1:02d}"
        col = bpy.data.collections.new(name)
        train_col.children.link(col)

        root = bpy.data.objects.new(f"{name}_Root", None)
        col.objects.link(root)
        root.empty_display_type = 'ARROWS'
        root.parent = rig

        body_me = build_body_mesh(f"{name}_Body", length, head, mats)
        body = new_object(f"{name}_Body", body_me, col, root)

        bogies = HEAD_BOGIES if head else MID_BOGIES
        cutters = [bogie_cutter(bx, mats, col) for bx in bogies]
        apply_boolean(body, cutters)

        if head:
            new_object(f"{name}_Windshield", windshield_mesh, col, root)
            new_object(f"{name}_Lights", tail_mesh if tail else light_mesh, col, root)

        for j, bx in enumerate(bogies):
            b = new_object(f"{name}_Bogie{j + 1}", bogie_mesh, col, root)
            b.location.x = bx
            for w, sx in enumerate((-1, 1)):
                ws = new_object(f"{name}_Bogie{j + 1}_Wheelset{w + 1}", wheelset_mesh, col, b)
                ws.location = (sx * BOGIE_WHEELBASE / 2, 0, WHEEL_RADIUS)
        if i in PANTOGRAPH_CARS:
            p = new_object(f"{name}_Pantograph", panto_mesh, col, root)
            p.location.x = length / 2
            if i > n / 2:
                p.scale.x = -1

        # расположение: хвостовой вагон развёрнут носом назад
        if tail:
            root.location.x = x1
            root.scale.x = -1
        else:
            root.location.x = x0

        if i < n - 1:
            g = new_object(f"Gangway_{i + 1:02d}_{i + 2:02d}", gangway_mesh, train_col, rig)
            g.location.x = x1

    if with_track:
        track_col = bpy.data.collections.new("Track")
        scene.collection.children.link(track_col)
        build_track(track_col, mats, -15.0, CARS[-1][1] + 15.0)

    # отрицательный масштаб у хвоста -> нормали в порядке, но применим трансформ,
    # чтобы экспорт в STL/FBX не путал ориентацию граней
    return train_col


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_out():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    if "--out" in argv:
        return os.path.abspath(argv[argv.index("--out") + 1])
    return None


def main():
    build_train()
    out = parse_out()
    if out:
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, "sapsan_velaro_rus.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
        print("saved", path)


if __name__ == "__main__":
    main()
