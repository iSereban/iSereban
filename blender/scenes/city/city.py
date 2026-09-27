"""
Город: перекрёсток, кварталы с домами и магазинами — собран по координатам из библиотеки.

Каждый объект — отдельная спецификация (чертёж: blender/library/out/drawings/<код>.png),
здесь только РАССТАНОВКА: таблица LAYOUT (метры, поворот в градусах).
Оси: X — восток, Y — север, 0 — центр перекрёстка. Улица А идёт по X, улица Б — по Y.

  python city.py [--out out] [--samples 24] [--no-render]
  (или в Blender: Scripting → Run Script)
Результат: out/city.blend, out/city_plan.png (план), out/shot_*.jpg (скриншоты).
"""
import math
import os
import sys

import bpy  # noqa: I001

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
LIB = os.path.join(HERE, "..", "..", "library")
sys.path.insert(0, LIB)
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
import catalog_city as cc  # noqa: E402
import catalog_furniture as cf  # noqa: E402
import parts  # noqa: E402
import studio  # noqa: E402

ROAD_W = 7.0          # ширина проезжей части, м
WALK_W = 3.0          # ширина тротуара, м
EXTENT = 100.0        # половина размера участка, м

# ---------------------------------------------------------------------------
# РАССТАНОВКА: (код объекта, X м, Y м, поворот°, подпись на плане)
# поворот 0 — фасад на юг (−Y), 180 — на север, 90 — на восток, −90 — на запад
# ---------------------------------------------------------------------------
LAYOUT = [
    # северо-запад
    ("house_5fl", -40.0, 22.0, 0, "Пятиэтажка №1"),
    ("bus_stop", -22.0, 8.3, 0, "Остановка"),
    # юго-запад: сквер и дом
    ("house_5fl", -40.0, -24.0, 180, "Пятиэтажка №2"),
    # северо-восток: магазины и девятиэтажка
    ("shop_produkty", 17.0, 13.0, 0, "Продукты"),
    ("bakery", 33.0, 12.5, 0, "Хлеб"),
    ("kiosk", 9.5, 9.0, 0, "Киоск"),
    ("house_9fl", 34.0, 42.0, 0, "Девятиэтажка"),
    # юго-восток
    ("shop_apteka", 14.0, -12.5, 180, "Аптека"),
    ("cafe", 30.0, -13.5, 180, "Кафе"),
    # машины: полосы — правостороннее движение
    ("car_red", 25.0, -1.75, 90, ""), ("car_sedan", 52.0, -1.75, 90, ""), ("car_sedan", -30.0, 1.75, -90, ""),
    ("car_blue", 1.75, 30.0, 180, ""), ("car_yellow", -1.75, -38.0, 0, ""), ("car_blue", -58.0, 1.75, -90, ""),
    ("car_red", -26.0, 32.0, 90, ""), ("car_sedan", 20.0, 30.0, 0, ""),
    # светофоры по углам
    ("traffic_light", 6.0, 6.0, 0, ""), ("traffic_light", -6.0, -6.0, 180, ""),
    ("traffic_light", 6.0, -6.0, 90, ""), ("traffic_light", -6.0, 6.0, -90, ""),
]
# фонари вдоль улиц
for _x in range(-70, 71, 20):
    if abs(_x) > 10:
        LAYOUT += [("streetlight", _x, 6.1, 90, ""), ("streetlight", _x + 10, -6.1, -90, "")]
for _y in range(-70, 71, 20):
    if abs(_y) > 10:
        LAYOUT += [("streetlight", 6.1, _y, 0, ""), ("streetlight", -6.1, _y + 10, 180, "")]
# сквер: деревья, скамейки, урны
for _i, _x in enumerate(range(-66, -10, 8)):
    LAYOUT.append(("tree_birch" if _i % 2 else "tree", _x, -10.5 - (_i % 2) * 2.5, 0, ""))
    if _i % 2 == 0 and _x < -14:
        LAYOUT += [("bench", _x + 4, -9.0, 180, ""), ("trash_bin", _x + 5.4, -8.8, 0, "")]
# деревья во дворах и вдоль улицы Б
for _y in (16, 28, 52, 64, 76):
    LAYOUT += [("tree", 8.5, _y, 0, ""), ("tree_birch", -8.5, _y - 6, 0, "")]
for _y in (-16, -30, -44, -58, -72):
    LAYOUT += [("tree_birch", 8.5, _y, 0, ""), ("tree", -8.5, _y + 5, 0, "")]
for _x, _y in ((-62, 36), (-48, 38), (-30, 37), (-18, 34), (14, 55), (50, 58), (56, 24), (46, -30), (20, -30),
               (-62, -38), (-30, -40), (-12, -36)):
    LAYOUT.append(("tree" if (_x + _y) % 2 else "tree_birch", _x, _y, 0, ""))
LAYOUT += [("bench", -30.0, 31.0, 180, ""), ("bench", -50.0, 31.0, 180, ""), ("trash_bin", -19.5, 8.5, 0, ""),
           ("bench", 22.0, 34.0, 180, ""), ("trash_bin", 23.5, 34.5, 0, "")]


def _variety(layout):
    """Разнообразие деревьев: «tree» → липа 1–3, «tree_birch» → берёза 1–2."""
    out = []
    for i, (name, x, y, rot, label) in enumerate(layout):
        if name == "tree":
            name = f"tree_linden_{1 + (i * 7 + int(x)) % 3}"
            rot = (i * 53) % 360
        elif name == "tree_birch":
            name = f"tree_birch_{1 + (i + int(y)) % 2}"
            rot = (i * 71) % 360
        out.append((name, x, y, rot, label))
    return out


LAYOUT += [("tree_spruce_1", -56.0, 44.0, 0, ""), ("tree_spruce_1", -8.0, 44.0, 40, ""),
           ("tree_spruce_1", 58.0, 36.0, 80, ""), ("tree_spruce_1", -56.0, -44.0, 20, "")]
LAYOUT = _variety(LAYOUT)


def ground_spec():
    """Земля, проезжая часть, тротуары с бордюрами, разметка и зебры (мм)."""
    B = cf.B
    E, R, Wk = EXTENT * 1000, ROAD_W * 500, WALK_W * 1000
    p = [B(6 * E, 6 * E, 100, 0, 0, -100, "grass"),
         B(2 * E, 2 * R, 110, 0, 0, -100, "asphalt"), B(2 * R, 2 * E, 104, 0, 0, -100, "asphalt")]
    for sx in (-1, 1):
        for sy in (-1, 1):
            # тротуар вдоль улицы А и вдоль улицы Б (с угловым участком)
            p.append(B(E - R, Wk, 250, sx * (R + (E - R) / 2), sy * (R + Wk / 2), -100, "sidewalk"))
            p.append(B(Wk, E - R - Wk, 250, sx * (R + Wk / 2), sy * (R + Wk + (E - R - Wk) / 2), -100, "sidewalk"))
            p.append(B(E - R, 150, 280, sx * (R + (E - R) / 2), sy * (R + 75), -100, "curb"))
            p.append(B(150, E - R, 280, sx * (R + 75), sy * (R + (E - R) / 2), -100, "curb"))
    # осевая прерывистая
    for k in range(-16, 17):
        c = k * 6000
        if abs(c) > 14000:
            p.append(B(3000, 120, 12, c, 0, 10, "marking"))
            p.append(B(120, 3000, 12, 0, c, 10, "marking"))
    # зебры
    for s in (-1, 1):
        for j in range(-3, 4):
            p.append(B(3000, 500, 12, s * 10000, j * 1000, 10, "marking"))
            p.append(B(500, 3000, 12, j * 1000, s * 10000, 10, "marking"))
        p.append(B(300, 2 * R, 12, s * 12200, 0, 10, "marking"))     # стоп-линии
        p.append(B(2 * R, 300, 12, 0, s * 12200, 10, "marking"))
    return cf.spec("city_ground", "Перекрёсток: дороги, тротуары, разметка", "Город", p,
                   f"проезжая часть {ROAD_W} м, тротуары {WALK_W} м")


def get_spec(name):
    if name in cc.CATALOG:
        return cc.get(name)
    return cf.get(name)


def build():
    studio.clear_scene()
    col_g = studio.collection("Ground")
    col_b = studio.collection("Buildings")
    col_s = studio.collection("Street")
    col_c = studio.collection("Cars")
    parts.place(ground_spec(), col=col_g)
    cache, specs = {}, {}
    for name, x, y, rot, _label in LAYOUT:
        s = specs.setdefault(name, get_spec(name))
        col = col_b if name.startswith(("house", "shop", "cafe", "bakery", "kiosk")) else \
            col_c if name.startswith("car") else col_s
        parts.place(s, location=(x, y, 0), rot_deg=rot, col=col, mesh_cache=cache)
    # небо и солнце
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Sky")
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
        sky.sun_elevation = math.radians(38)
        sky.sun_rotation = math.radians(205)
    w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.25
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 3.0
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-25))
    sc.collection.objects.link(sun)
    return specs


SHOTS = {
    "shot_1_aerial": ((-62, -72, 55), (6, 6, 0), 30),
    "shot_2_crossroad": ((-7, -8, 1.7), (20, 14, 5), 22),
    "shot_3_shops": ((16, -4.5, 1.7), (25, 12, 3), 20),
    "shot_4_apteka_cafe": ((18, 3.0, 1.7), (24, -12, 2.5), 22),
    "shot_5_park": ((-18, -4.5, 1.7), (-40, -16, 5), 24),
    "shot_6_busstop_house": ((-12, -2.5, 1.7), (-30, 14, 6), 22),
    "shot_7_house9": ((12, 22, 1.7), (34, 40, 12), 22),
}


def draw_plan(out):
    import drawings
    items = [{"spec": ground_spec(), "x": 0, "y": 0, "rot": 0}]
    for name, x, y, rot, label in LAYOUT:
        items.append({"spec": get_spec(name), "x": x * 1000, "y": y * 1000, "rot": rot, "label": label})
    drawings.draw_plan(items, os.path.join(out, "city_plan.png"),
                       "План города (генплан): перекрёсток и кварталы, координаты в мм", size=(16, 16))


def main():
    out = os.path.abspath(studio.arg("--out", os.path.join(HERE, "out")))
    os.makedirs(out, exist_ok=True)
    try:
        draw_plan(out)
        print("plan", os.path.join(out, "city_plan.png"))
    except ImportError as e:  # в Blender без matplotlib — план пропускаем
        print("plan skipped:", e)
    build()
    studio.setup_render("CYCLES", studio.RES_480, int(studio.arg("--samples", 24)), exposure=-0.6)
    cams = {n: studio.camera(n, loc, tgt, lens) for n, (loc, tgt, lens) in SHOTS.items()}
    for c in cams.values():
        c.data.clip_end = 2000
    bpy.context.scene.camera = cams["shot_1_aerial"]
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "city.blend"), compress=True)
    print("saved", os.path.join(out, "city.blend"))
    if not studio.flag("--no-render"):
        only = studio.arg("--only")
        for n, c in cams.items():
            if only and only not in n:
                continue
            studio.render_still(os.path.join(out, f"{n}.jpg"), c)


if __name__ == "__main__":
    main()
