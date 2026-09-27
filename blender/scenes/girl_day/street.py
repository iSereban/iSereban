"""
Часть 2 (кадры 1–600, 24 с): девочка выходит из подъезда пятиэтажки №1 и гуляет по городу.
Город — scenes/city (перекрёсток, дома, магазины, деревья); к подъезду №2 добавлены ступеньки.
"""
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

import catalog_girl as CG
import parts
from performer import Hold, Path, Prop, Walk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "city"))
import city  # noqa: E402

FRAMES = 600
ENTR = (-47.5, 15.4)                  # крыльцо подъезда №2 (верх 0,8 м, y 14,8…16,0)
WALK_Y = 4.9                          # линия движения по северному тротуару


def ground(x, y):
    if abs(x - ENTR[0]) < 1.25:
        if y >= 14.8:
            return 0.8
        if y > 13.6:
            return 0.8 * (y - 13.6) / 1.2
    return 0.0


def build_street(col=None):
    city.build()                                  # сам очищает сцену → свою коллекцию создаём после
    import studio
    col = studio.collection("Porch")
    # ступеньки крыльца
    steps = []
    for k, h in enumerate((0.64, 0.48, 0.32, 0.16)):
        steps.append({"t": "box", "s": [1600, 300, h * 1000], "p": [0, -150 - 300 * k, h * 500], "m": "concrete"})
    spec = {"name": "porch_steps", "title": "Ступени крыльца", "group": "Город", "parts": steps, "note": ""}
    parts.place(spec, location=(ENTR[0], 14.8, 0), col=col)
    return {}


def choreograph(g, props_col):
    g.ground = ground
    x0 = -44.0
    x1 = x0 + 449 / 25 * 0.72
    g.path = Path([
        Hold(1, 14, Vector((ENTR[0], 15.35, 0)), 0),
        Walk(15, 150, [(ENTR[0], 15.35), (ENTR[0], 13.4), (ENTR[0] + 0.3, 11.5)], ease=8),
        Walk(151, 600, [(x0, WALK_Y), (x0 + 4, WALK_Y + 0.1), (x0 + 8.5, WALK_Y - 0.05), (x1, WALK_Y)], ease=3),
    ])

    # оглядывается: на дома (север), на дорогу (юг), вверх на деревья
    def look(f):
        pos, psi = g.path.at(f)
        if 200 <= f <= 280:
            return pos + Vector((1.5, 6.0, 2.5))
        if 330 <= f <= 400:
            return pos + Vector((2.0, -5.0, 1.0))
        if 470 <= f <= 530:
            return pos + Vector((3.0, 1.0, 4.0))
        return pos + Vector((3.0, 0, 1.0))
    g.T["look"] = look
    g.set("look_w", [(190, 0.0), (205, 0.9), (275, 0.9), (290, 0.0), (325, 0.0), (340, 0.8), (395, 0.8), (410, 0.0),
                     (465, 0.0), (480, 0.9), (525, 0.9), (540, 0.0)])
    bag = parts.place(CG.get("backpack"), location=(0, 0, 0), col=props_col)
    g.props = [Prop(bag, [(1, "back")], scale=0.8)]


def shots(walls):
    from cinema import Shot

    return [
        Shot("C1_porch", 1, 150, [(1, (-45.0, 8.6, 2.9)), (80, (-45.2, 8.3, 1.5)), (150, (-45.3, 8.2, 1.2))],
             ("chest", (0, 0, 0.05)), 30, fstop=5.6),
        Shot("C2_side", 151, 300, "side", ("chest", (0, 0, 0)), 35, fstop=4.0),
        Shot("C3_front_low", 301, 420, "front", ("head", (0, 0, -0.05)), 30, fstop=4.0),
        Shot("C4_behind", 421, 510, "behind", ("chest", (0, 0, 0.1)), 35, fstop=5.6),
        Shot("C5_crane", 511, 600, "crane", ("chest", (2.5, 0, 0.25)), 32, lens_to=24, fstop=8.0),
    ]


def resolve_camera_paths(g, shot_list):
    """Камеры, привязанные к пути девочки (едут вместе с ней)."""
    for s in shot_list:
        if not isinstance(s.cam, str):
            continue
        kind = s.cam

        def fn(f, kind=kind, s=s):
            p, _ = g.path.at(max(s.f0, min(s.f1, f)))
            if kind == "side":
                return (p.x + 0.6, 2.3, 1.0)
            if kind == "front":
                return (p.x + 2.4, WALK_Y - 0.2, 0.55)
            if kind == "behind":
                return (p.x - 2.2, WALK_Y + 0.5, 1.35)
            u = (f - s.f0) / (s.f1 - s.f0)
            return (p.x - 2.4 - 2.6 * u, WALK_Y + 0.9 + 0.3 * u, 1.2 + 3.6 * u * u)
        s.cam = fn
