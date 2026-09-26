"""
Трёхкомнатная квартира с кухней (хозяйка — женщина 50+), собранная по координатам.

Каждый предмет — отдельная спецификация из библиотеки (чертёж: blender/library/out/drawings/<код>.png).
Здесь — ПЛАН (стены, проёмы, комнаты) и РАССТАНОВКА (таблица FURNITURE, мм).
Оси: X — восток, Y — север, 0 — внутренний юго-западный угол квартиры, Z — от пола. Потолок 2700.

  python apartment.py [--out out] [--samples 32] [--no-render] [--only living]
  (или в Blender: Scripting → Run Script)
Результат:
  out/apartment.blend               — вся квартира
  out/room_<комната>.blend          — отдельный файл каждой комнаты (оболочка + своя мебель + камеры)
  out/apartment_plan.png            — план с мебелью и размерами
  out/<комната>_*.jpg, overview_*.jpg — скриншоты
"""
import math
import os
import sys

import bpy  # noqa: I001

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
sys.path.insert(0, os.path.join(HERE, "..", "..", "library"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
import catalog_furniture as cf  # noqa: E402
import parts  # noqa: E402
import studio  # noqa: E402

H = 2700            # высота потолка
EXT = 300           # наружные стены
INT = 120           # перегородки
SILL, WIN_H = 850, 1500
DOOR_H = 2100

# ---------------------------------------------------------------------------
# ПЛАН: комнаты (внутренние размеры, мм)
# ---------------------------------------------------------------------------
ROOMS = {
    "living": ("Гостиная", 0, 0, 4800, 4200, "wood_floor"),
    "bedroom": ("Спальня", 4800, 0, 8400, 4200, "wood_floor"),
    "kitchen": ("Кухня", 8400, 0, 11600, 4200, "linoleum"),
    "room3": ("Комната 3 (рукоделие/гостевая)", 0, 4200, 3600, 7200, "wood_floor"),
    "hall": ("Прихожая", 3600, 4200, 9600, 7200, "wood_floor"),
    "bath": ("Ванная", 9600, 4200, 11600, 7200, "tile_beige"),
}
W_TOTAL, D_TOTAL = 11600, 7200

# Стены: (ось, координата линии, от, до, толщина, смещение: "neg"|"pos"|"mid", [проёмы (от, до, низ, верх, вид)])
WALLS = [
    ("x", 0, -EXT, W_TOTAL + EXT, EXT, "neg", [(1500, 3300, SILL, SILL + WIN_H, "window"),
                                              (5850, 7350, SILL, SILL + WIN_H, "window"),
                                              (9300, 10700, SILL, SILL + WIN_H, "window")]),
    ("x", D_TOTAL, -EXT, W_TOTAL + EXT, EXT, "pos", [(5900, 7000, 0, DOOR_H, "door")]),
    ("y", 0, 0, D_TOTAL, EXT, "neg", [(5000, 6400, SILL, SILL + WIN_H, "window")]),
    ("y", W_TOTAL, 0, D_TOTAL, EXT, "pos", []),
    ("x", 4200, 0, W_TOTAL, INT, "mid", [(3750, 4650, 0, DOOR_H, "door"), (5150, 6050, 0, DOOR_H, "door"),
                                         (8550, 9450, 0, DOOR_H, "door")]),
    ("y", 4800, 0, 4200, INT, "mid", []),
    ("y", 8400, 0, 4200, INT, "mid", []),
    ("y", 3600, 4200, D_TOTAL, INT, "mid", [(4550, 5450, 0, DOOR_H, "door")]),
    ("y", 9600, 4200, D_TOTAL, INT, "mid", [(5950, 6850, 0, DOOR_H, "door")]),
]

# ---------------------------------------------------------------------------
# РАССТАНОВКА: (комната, код, параметры, X, Y, Z, поворот°, подпись)
# поворот: 0 — фасад предмета на юг (−Y), 180 — на север, 90 — на восток, −90 — на запад
# ---------------------------------------------------------------------------
FURNITURE = [
    # --- Гостиная
    ("living", "wall_unit", {}, 265, 2100, 0, 90, "Стенка"),
    ("living", "tv", {}, 265, 1900, 560, 90, ""),
    ("living", "sofa", {}, 4275, 2100, 0, -90, "Диван"),
    ("living", "carpet", {}, 2550, 2100, 0, 90, ""),
    ("living", "coffee_table", {}, 2650, 2100, 0, 90, "Столик"),
    ("living", "armchair", {}, 1150, 850, 0, 135, "Кресло"),
    ("living", "floor_lamp", {}, 650, 250, 0, 0, ""),
    ("living", "plant_ficus", {}, 4450, 420, 0, 0, "Фикус"),
    ("living", "chandelier", {}, 2400, 2100, H, 0, ""),
    ("living", "window", {"w": 1800}, 2400, 0, 0, 180, ""),
    ("living", "curtains", {"w": 1800}, 2400, 0, 0, 180, ""),
    ("living", "radiator", {"sections": 12}, 2400, 110, 0, 180, ""),
    ("living", "plant_violet", {}, 2000, 170, SILL, 0, ""),
    ("living", "plant_violet", {}, 2800, 170, SILL, 0, ""),
    ("living", "wall_clock", {}, 1600, 4140, 2000, 0, ""),
    ("living", "picture", {}, 4740, 2100, 2150, -90, ""),
    ("living", "door_interior", {}, 4200, 4200, 0, 180, ""),
    # --- Спальня
    ("bedroom", "double_bed", {}, 7265, 2300, 0, -90, "Кровать"),
    ("bedroom", "carpet", {"w": 2400, "d": 1700, "m": "carpet_blue", "name": "carpet_bed"}, 6900, 2300, 0, 90, ""),
    ("bedroom", "nightstand", {}, 8140, 1150, 0, -90, ""),
    ("bedroom", "nightstand", {}, 8140, 3450, 0, -90, ""),
    ("bedroom", "table_lamp", {}, 8140, 1150, 563, 0, ""),
    ("bedroom", "table_lamp", {}, 8140, 3450, 563, 0, ""),
    ("bedroom", "wardrobe", {}, 5175, 2400, 0, 90, "Шкаф"),
    ("bedroom", "dresser_mirror", {}, 5350, 300, 0, 180, "Трюмо"),
    ("bedroom", "pouf", {}, 5350, 900, 0, 0, ""),
    ("bedroom", "chandelier", {}, 6600, 2100, H, 0, ""),
    ("bedroom", "window", {"w": 1500}, 6600, 0, 0, 180, ""),
    ("bedroom", "curtains", {"w": 1500}, 6600, 0, 0, 180, ""),
    ("bedroom", "radiator", {"sections": 10}, 6600, 110, 0, 180, ""),
    ("bedroom", "picture", {"w": 800, "h": 500, "m": "wallpaper_green", "name": "picture_bed"}, 8340, 2300, 2150, -90, ""),
    ("bedroom", "door_interior", {}, 5600, 4200, 0, 180, ""),
    # --- Кухня
    ("kitchen", "kitchen_set", {"L": 3000}, 11290, 1750, 0, -90, "Гарнитур"),
    ("kitchen", "fridge", {}, 11270, 3600, 0, -90, "Холодильник"),
    ("kitchen", "microwave", {}, 11330, 520, 900, -90, ""),
    ("kitchen", "kettle", {}, 11290, 1550, 912, -90, ""),
    ("kitchen", "dining_table", {}, 8980, 2000, 0, 90, "Стол"),
    ("kitchen", "tea_set", {}, 8980, 2000, 754, 90, ""),
    ("kitchen", "stool", {}, 9600, 1650, 0, 0, ""),
    ("kitchen", "stool", {}, 9600, 2350, 0, 0, ""),
    ("kitchen", "stool", {}, 8980, 2950, 0, 0, ""),
    ("kitchen", "ceiling_lamp", {}, 10000, 2100, H, 0, ""),
    ("kitchen", "window", {"w": 1400}, 10000, 0, 0, 180, ""),
    ("kitchen", "curtains", {"w": 1400, "h": 2400}, 10000, 0, 0, 180, ""),
    ("kitchen", "radiator", {"sections": 8}, 10000, 110, 0, 180, ""),
    ("kitchen", "plant_violet", {}, 10000, 170, SILL, 0, ""),
    ("kitchen", "wall_clock", {}, 8460, 2000, 1900, 90, ""),
    ("kitchen", "door_interior", {}, 9000, 4200, 0, 180, ""),
    # --- Комната 3
    ("room3", "sofa_bed", {}, 1700, 4710, 0, 180, "Диван-книжка"),
    ("room3", "carpet", {"w": 2000, "d": 1400, "m": "carpet_blue", "name": "carpet_small"}, 1700, 5750, 0, 0, ""),
    ("room3", "desk", {}, 1700, 6900, 0, 0, "Стол"),
    ("room3", "sewing_machine", {}, 1550, 6950, 750, 0, ""),
    ("room3", "table_lamp", {}, 2150, 7020, 750, 0, ""),
    ("room3", "chair", {}, 1700, 6350, 0, 180, ""),
    ("room3", "bookcase", {}, 3365, 6500, 0, -90, "Книги"),
    ("room3", "armchair", {"color": "fabric_green"}, 620, 6480, 0, 45, ""),
    ("room3", "plant_ficus", {}, 320, 4560, 0, 0, ""),
    ("room3", "ceiling_lamp", {}, 1800, 5700, H, 0, ""),
    ("room3", "window", {"w": 1400}, 0, 5700, 0, 90, ""),
    ("room3", "curtains", {"w": 1400}, 0, 5700, 0, 90, ""),
    ("room3", "radiator", {"sections": 8}, 110, 5700, 0, 90, ""),
    ("room3", "picture", {}, 1700, 4260, 2100, 180, ""),
    ("room3", "door_interior", {}, 3600, 5000, 0, 90, ""),
    # --- Прихожая
    ("hall", "entrance_door", {}, 6450, 7200, 0, 0, "Вход"),
    ("hall", "hall_wardrobe", {}, 4400, 7000, 0, 0, "Шкаф-прихожая"),
    ("hall", "rug", {}, 6450, 6550, 0, 0, ""),
    ("hall", "ceiling_lamp", {}, 6600, 5700, H, 0, ""),
    ("hall", "picture", {"w": 500, "h": 700, "name": "picture_hall"}, 8200, 7200, 1900, 0, ""),
    ("hall", "door_interior", {}, 9600, 6400, 0, 90, ""),
    # --- Ванная
    ("bath", "bathtub", {}, 11225, 5100, 0, -90, "Ванна"),
    ("bath", "washbasin", {}, 10200, 4485, 0, 180, ""),
    ("bath", "toilet", {}, 10900, 6875, 0, 0, ""),
    ("bath", "washing_machine", {}, 10000, 6925, 0, 0, ""),
    ("bath", "rug", {"w": 700, "d": 500, "name": "rug_bath", "m": "fabric_blue"}, 10300, 5400, 0, 0, ""),
    ("bath", "ceiling_lamp", {}, 10600, 5700, H, 0, ""),
]

# Камеры: (комната, имя, позиция мм, цель мм, фокусное)
CAMERAS = [
    ("living", "living_1", (4450, 3950, 1650), (700, 1300, 1000), 15),
    ("living", "living_2", (900, 450, 1550), (4300, 2600, 900), 15),
    ("bedroom", "bedroom_1", (5250, 3950, 1650), (7900, 1500, 900), 15),
    ("bedroom", "bedroom_2", (7950, 250, 1600), (5100, 3000, 1100), 15),
    ("kitchen", "kitchen_1", (8700, 3950, 1650), (11200, 1300, 1000), 15),
    ("kitchen", "kitchen_2", (11000, 250, 1650), (8700, 2800, 900), 15),
    ("room3", "room3_1", (3350, 4450, 1650), (500, 6800, 1000), 15),
    ("room3", "room3_2", (300, 4450, 1650), (2800, 6900, 900), 15),
    ("hall", "hall_1", (9250, 4650, 1650), (4200, 6900, 1100), 16),
    ("bath", "bath_1", (9850, 4450, 1650), (11300, 6800, 800), 14),
]


# ---------------------------------------------------------------------------
def wall_boxes():
    """Стены → прямоугольные блоки (мм): (x, y, z_низ, w, d, h)."""
    out = []
    for ax, c, a0, a1, t, side, ops in WALLS:
        off = {"neg": -t / 2, "pos": t / 2, "mid": 0}[side]
        cuts = sorted(ops)
        segs, pos = [], a0
        for o0, o1, z0, z1, _k in cuts:
            if o0 > pos:
                segs.append((pos, o0, 0, H))
            if z0 > 0:
                segs.append((o0, o1, 0, z0))
            if z1 < H:
                segs.append((o0, o1, z1, H))
            pos = o1
        if pos < a1:
            segs.append((pos, a1, 0, H))
        for s0, s1, z0, z1 in segs:
            if ax == "x":
                out.append(((s0 + s1) / 2, c + off, z0, s1 - s0, t, z1 - z0))
            else:
                out.append((c + off, (s0 + s1) / 2, z0, t, s1 - s0, z1 - z0))
    return out


def shell_spec():
    p = [cf.B(w, d, h, x, y, z, "wallpaper") for x, y, z, w, d, h in wall_boxes()]
    for _k, (_t, x0, y0, x1, y1, mat) in ROOMS.items():
        p.append(cf.B(x1 - x0 + INT, y1 - y0 + INT, 50, (x0 + x1) / 2, (y0 + y1) / 2, -50, mat))
    # плитка в ванной до 2000 мм
    x0, y0, x1, y1 = 9660, 4260, W_TOTAL, D_TOTAL
    p += [cf.B(x1 - x0, 8, 2000, (x0 + x1) / 2, y1 - 4, 0, "tile_white"),
          cf.B(8, y1 - y0, 2000, x1 - 4, (y0 + y1) / 2, 0, "tile_white"),
          cf.B(x1 - x0, 8, 2000, (x0 + x1) / 2, y0 + 4, 0, "tile_white")]
    # плинтус по комнатам
    for _k, (_t, rx0, ry0, rx1, ry1, _m) in ROOMS.items():
        e = INT / 2 if rx0 > 0 else 0
        p += [cf.B(rx1 - rx0, 15, 70, (rx0 + rx1) / 2, ry0 + (INT / 2 if ry0 > 0 else 0) + 8, 0, "wood_walnut"),
              cf.B(rx1 - rx0, 15, 70, (rx0 + rx1) / 2, ry1 - (INT / 2 if ry1 < D_TOTAL else 0) - 8, 0, "wood_walnut"),
              cf.B(15, ry1 - ry0, 70, rx0 + e + 8, (ry0 + ry1) / 2, 0, "wood_walnut")]
    return cf.spec("apartment_shell", "Квартира: стены, полы, плинтусы", "Квартира", p,
                   f"{W_TOTAL}×{D_TOTAL} мм по внутренним осям, потолок {H}")


def ceiling_spec():
    return cf.spec("apartment_ceiling", "Потолок", "Квартира",
                   [cf.B(W_TOTAL + 2 * EXT, D_TOTAL + 2 * EXT, 150, W_TOTAL / 2, D_TOTAL / 2, H, "paint_ceiling")])


def furniture_spec(code, kw):
    return cf.get(code, **kw)


def build(room=None):
    """room=None — вся квартира; иначе оболочка + мебель только этой комнаты."""
    studio.clear_scene()
    col_shell = studio.collection("Shell")
    parts.place(shell_spec(), col=col_shell)
    ceil = parts.place(ceiling_spec(), col=col_shell)
    cache = {}
    cols = {}
    for rm, code, kw, x, y, z, rot, _label in FURNITURE:
        if room and rm != room:
            continue
        col = cols.get(rm) or studio.collection(f"Room_{rm}")
        cols[rm] = col
        s = furniture_spec(code, kw)
        key = s["name"] + str(sorted(kw.items()))
        me = cache.get(key)
        if me is None:
            me = parts.build_mesh(s)
            cache[key] = me
        obj = bpy.data.objects.new(s["name"], me)
        col.objects.link(obj)
        obj.location = (x / 1000, y / 1000, z / 1000)
        obj.rotation_euler = (0, 0, math.radians(rot))
    lights(room)
    return ceil


def lights(room=None):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Outside")
    sc.world = w
    w.use_nodes = True
    sky = w.node_tree.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.radians(30)
        sky.sun_rotation = math.radians(170)
    w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(58), 0, math.radians(-160))
    sc.collection.objects.link(sun)
    # «улица» за окнами — двор на 3-м этаже
    me = bpy.data.meshes.new("Yard")
    me.from_pydata([(-60, -60, -7), (70, -60, -7), (70, 70, -7), (-60, 70, -7)], [], [(0, 1, 2, 3)])
    me.materials.append(parts.material("grass"))
    sc.collection.objects.link(bpy.data.objects.new("Yard", me))
    # мягкий свет в каждой комнате (как от люстр и окон)
    for k, (_t, x0, y0, x1, y1, _m) in ROOMS.items():
        if room and k != room and not (room and k == "hall"):
            continue
        ld = bpy.data.lights.new(f"Light_{k}", 'AREA')
        ld.shape = 'RECTANGLE'
        ld.size = (x1 - x0) / 1000 * 0.7
        ld.size_y = (y1 - y0) / 1000 * 0.7
        ld.energy = (x1 - x0) * (y1 - y0) / 1e6 * 22
        ld.color = (1.0, 0.9, 0.78)
        lo = bpy.data.objects.new(f"Light_{k}", ld)
        sc.collection.objects.link(lo)
        lo.location = ((x0 + x1) / 2000, (y0 + y1) / 2000, H / 1000 - 0.05)


def make_cameras(room=None):
    cams = {}
    for rm, name, pos, tgt, lens in CAMERAS:
        if room and rm != room:
            continue
        cams[name] = studio.camera(name, tuple(v / 1000 for v in pos), tuple(v / 1000 for v in tgt), lens)
        cams[name].data.clip_start = 0.05
    return cams


def draw_plan(out):
    import drawings
    items = []
    for rm, code, kw, x, y, z, rot, label in FURNITURE:
        s = furniture_spec(code, kw)
        if code in ("chandelier", "ceiling_lamp", "curtains"):
            continue
        items.append({"spec": s, "x": x, "y": y, "z": z, "rot": rot, "label": label})
    walls = [(x - w / 2, y - d / 2, x + w / 2, y + d / 2) for x, y, z, w, d, h in wall_boxes() if z == 0 and h == H]
    rooms = [(t, x0, y0, x1, y1) for _k, (t, x0, y0, x1, y1, _m) in ROOMS.items()]
    openings = []
    for ax, c, _a0, _a1, t, side, ops in WALLS:
        off = {"neg": -t / 2, "pos": t / 2, "mid": 0}[side]
        for o0, o1, _z0, _z1, kind in ops:
            if ax == "x":
                openings.append((kind, o0, c + off - t / 2, o1, c + off + t / 2))
            else:
                openings.append((kind, c + off - t / 2, o0, c + off + t / 2, o1))
    dims = [(0, -900, 4800, -900, "4800"), (4800, -900, 8400, -900, "3600"), (8400, -900, 11600, -900, "3200"),
            (0, -1500, 11600, -1500, "11600"), (-900, 0, -900, 4200, "4200"), (-900, 4200, -900, 7200, "3000"),
            (-1500, 0, -1500, 7200, "7200")]
    drawings.draw_plan(items, os.path.join(out, "apartment_plan.png"),
                       "План квартиры: 3 комнаты + кухня, мебель по координатам (мм), потолок 2700",
                       walls=walls, rooms=rooms, openings=openings, size=(18, 12), grid_step=500, dims=dims)


def main():
    out = os.path.abspath(studio.arg("--out", os.path.join(HERE, "out")))
    os.makedirs(out, exist_ok=True)
    samples = int(studio.arg("--samples", 32))
    only = studio.arg("--only")
    try:
        draw_plan(out)
        print("plan", os.path.join(out, "apartment_plan.png"))
    except ImportError as e:
        print("plan skipped:", e)

    # вся квартира
    ceil = build()
    cams = make_cameras()
    studio.setup_render("CYCLES", studio.RES_480, samples, exposure=0.0)
    bpy.context.scene.camera = cams["living_1"]
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "apartment.blend"), compress=True)
    print("saved apartment.blend")
    if not studio.flag("--no-render"):
        # обзор «кукольный домик»: без потолка
        ceil.hide_render = True
        bpy.context.scene.view_settings.exposure = -1.3
        ov = {"overview_1": ((-3.2, -7.5, 11.0), (5.8, 3.4, 0), 24), "overview_2": ((15.5, 12.0, 11.5), (5.8, 3.4, 0), 24)}
        for n, (loc, tgt, lens) in ov.items():
            if only and only not in n:
                continue
            studio.render_still(os.path.join(out, f"{n}.jpg"), studio.camera(n, loc, tgt, lens))
        top = studio.camera("overview_top", (5.8, 3.6, 20), (5.8, 3.6, 0), 50)
        top.data.type = 'ORTHO'
        top.data.ortho_scale = 13.5
        if not only or "top" in only:
            studio.render_still(os.path.join(out, "overview_top.jpg"), top)
        ceil.hide_render = False
        bpy.context.scene.view_settings.exposure = 0.0
        for n, c in cams.items():
            if only and only not in n:
                continue
            studio.render_still(os.path.join(out, f"{n}.jpg"), c)

    # отдельный файл каждой комнаты
    for rm in ROOMS:
        build(room=rm)
        cams = make_cameras(rm)
        studio.setup_render("CYCLES", studio.RES_480, samples, exposure=0.0)
        if cams:
            bpy.context.scene.camera = next(iter(cams.values()))
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"room_{rm}.blend"), compress=True)
        print("saved", f"room_{rm}.blend")


if __name__ == "__main__":
    main()
