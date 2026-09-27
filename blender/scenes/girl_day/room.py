"""
Часть 1 (кадры 1–900, 36 с): детская комната.

Сюжет: девочка пишет в тетради → откладывает карандаш, закрывает тетрадь → отодвигает стул, встаёт →
идёт к комоду → расчёсывается перед зеркалом → звонит телефон, смотрит, радуется → телефон в карман →
идёт к рюкзаку, приседает, поднимает, закидывает на спину → открывается дверь, уходит.
"""
import math

import bpy  # noqa: I001
from mathutils import Euler, Matrix, Vector

import catalog_furniture as CF
import catalog_girl as CG
import parts
import performer as P
from performer import Hold, Path, Prop, Track, Walk
import studio

FRAMES = 900
ROOM = dict(x0=-2.1, x1=2.1, y0=-1.8, y1=1.8, h=2.6, t=0.12)
WINDOW = dict(x=-0.8, w=1.2, sill=0.8, h=1.2)
DOOR = dict(x0=0.55, x1=1.45, h=2.05)
DESK = (-0.8, 1.54)
CHAIR0, CHAIR1 = (-0.8, 1.10), (-0.8, 0.80)
DRESSER = (-1.88, -0.2)
BAG = (1.45, -0.63)


# ---------------------------------------------------------------------------
# Комната
# ---------------------------------------------------------------------------
def _box_spec(name, boxes, m):
    return {"name": name, "title": name, "group": "Комната",
            "parts": [{"t": "box", "s": [w * 1000, d * 1000, h * 1000], "p": [x * 1000, y * 1000, (z + h / 2) * 1000], "m": m}
                      for (w, d, h, x, y, z) in boxes], "note": ""}


def build_room(col):
    R = ROOM
    W, D, Hh, t = R["x1"] - R["x0"], R["y1"] - R["y0"], R["h"], R["t"]
    walls = {}
    parts.place(_box_spec("Floor", [(W + 2 * t, D + 2 * t, 0.05, 0, 0, -0.05)], "wood_floor"), col=col)
    parts.place(_box_spec("Ceiling", [(W + 2 * t, D + 2 * t, 0.05, 0, 0, Hh)], "paint_ceiling"), col=col)
    wx0, wx1 = WINDOW["x"] - WINDOW["w"] / 2, WINDOW["x"] + WINDOW["w"] / 2
    ws, wt = WINDOW["sill"], WINDOW["sill"] + WINDOW["h"]
    yN = R["y1"] + t / 2
    north = [(wx0 - R["x0"] + t, t, Hh, (R["x0"] - t + wx0) / 2, yN, 0),
             (R["x1"] + t - wx1, t, Hh, (wx1 + R["x1"] + t) / 2, yN, 0),
             (WINDOW["w"], t, ws, WINDOW["x"], yN, 0), (WINDOW["w"], t, Hh - wt, WINDOW["x"], yN, wt)]
    walls["Wall_N"] = parts.place(_box_spec("Wall_N", north, "wallpaper_kids"), col=col)
    yS = R["y0"] - t / 2
    south = [(DOOR["x0"] - R["x0"] + t, t, Hh, (R["x0"] - t + DOOR["x0"]) / 2, yS, 0),
             (R["x1"] + t - DOOR["x1"], t, Hh, (DOOR["x1"] + R["x1"] + t) / 2, yS, 0),
             (DOOR["x1"] - DOOR["x0"], t, Hh - DOOR["h"], (DOOR["x0"] + DOOR["x1"]) / 2, yS, DOOR["h"])]
    walls["Wall_S"] = parts.place(_box_spec("Wall_S", south, "wallpaper_kids"), col=col)
    walls["Wall_E"] = parts.place(_box_spec("Wall_E", [(t, D, Hh, R["x1"] + t / 2, 0, 0)], "wallpaper_kids"), col=col)
    walls["Wall_W"] = parts.place(_box_spec("Wall_W", [(t, D, Hh, R["x0"] - t / 2, 0, 0)], "wallpaper_kids"), col=col)
    # плинтусы
    parts.place(_box_spec("Skirting", [(W, 0.02, 0.07, 0, R["y1"] - 0.01, 0), (W, 0.02, 0.07, 0, R["y0"] + 0.01, 0),
                                       (0.02, D, 0.07, R["x1"] - 0.01, 0, 0), (0.02, D, 0.07, R["x0"] + 0.01, 0, 0)],
                          "wood_white"), col=col)
    # коридор за дверью (чтобы в проёме не было пустоты)
    parts.place(_box_spec("Hall", [(2.4, 0.05, 2.6, 1.0, -3.3, 0), (2.4, 2.0, 0.05, 1.0, -2.8, -0.05),
                                   (0.05, 2.0, 2.6, -0.2, -2.8, 0), (0.05, 2.0, 2.6, 2.2, -2.8, 0)], "plaster_white"), col=col)
    # окно, шторы
    win = parts.place(CF.get("window", w=int(WINDOW["w"] * 1000), h=int(WINDOW["h"] * 1000), sill_z=int(ws * 1000)),
                      location=(WINDOW["x"], R["y1"] + t / 2, 0), col=col)
    cur = parts.place(CF.get("curtains", w=1500, h=2500), location=(WINDOW["x"], R["y1"], 0), col=col)
    walls["Window"], walls["Curtains"] = win, cur
    # дверь: коробка + полотно на петле (петля у x1)
    parts.place(_box_spec("DoorFrame", [(0.06, 0.16, DOOR["h"], DOOR["x0"] - 0.03, R["y0"] - t / 2, 0),
                                        (0.06, 0.16, DOOR["h"], DOOR["x1"] + 0.03, R["y0"] - t / 2, 0),
                                        (DOOR["x1"] - DOOR["x0"] + 0.12, 0.16, 0.06, (DOOR["x0"] + DOOR["x1"]) / 2,
                                         R["y0"] - t / 2, DOOR["h"])], "wood_white"), col=col)
    hinge = bpy.data.objects.new("DoorHinge", None)
    col.objects.link(hinge)
    hinge.location = (DOOR["x1"], R["y0"] + 0.02, 0)
    lw = DOOR["x1"] - DOOR["x0"] - 0.02
    leaf = parts.place(_box_spec("DoorLeaf", [(lw, 0.04, DOOR["h"] - 0.02, -lw / 2, 0, 0)], "wood_white"), col=col)
    knob = parts.place(_box_spec("DoorKnob", [(0.12, 0.05, 0.025, -lw + 0.12, 0.04, 0.95), (0.12, 0.05, 0.025, -lw + 0.12, -0.04, 0.95)],
                                 "chrome"), col=col)
    for o in (leaf, knob):
        o.parent = hinge
    # мебель
    parts.place(CG.get("kid_desk"), location=(*DESK, 0), col=col)
    chair = parts.place(CG.get("kid_chair"), location=(*CHAIR0, 0), rot_deg=180, col=col)
    parts.place(CG.get("desk_lamp"), location=(-0.43, 1.66, 0.56), rot_deg=200, col=col)
    parts.place(CG.get("textbook"), location=(-1.10, 1.46, 0.56), rot_deg=12, col=col)
    parts.place(CG.get("pencil_cup"), location=(-1.14, 1.69, 0.56), col=col)
    parts.place(CG.get("kid_bed"), location=(1.63, 0.62, 0), col=col)
    parts.place(CG.get("plush_bear"), location=(1.55, 1.25, 0.45), rot_deg=-110, col=col)
    parts.place(CG.get("bookshelf_kid"), location=(0.55, 1.64, 0), col=col)
    walls["Dresser"] = parts.place(CG.get("kid_dresser", mirror=False), location=(*DRESSER, 0), rot_deg=90, col=col)
    walls["Mirror"] = parts.place(CG.get("kid_mirror"), location=(*DRESSER, 0), rot_deg=90, col=col)
    parts.place(CF.get("wardrobe"), location=(-1.15, -1.47, 0), rot_deg=180, col=col)
    parts.place(CF.get("rug", w=1700, d=1200, m="carpet_blue", name="rug_kids"), location=(0.05, 0.15, 0), col=col)
    parts.place(CF.get("ceiling_lamp"), location=(0, 0, R["h"]), col=col)
    parts.place(CF.get("picture", w=500, h=380, m="fabric_floral", name="pic1"), location=(R["x1"], 0.55, 1.45), rot_deg=-90, col=col)
    parts.place(CF.get("picture", w=380, h=480, m="flower_pink", name="pic2"), location=(R["x1"], 1.2, 1.5), rot_deg=-90, col=col)
    parts.place(CF.get("picture", w=420, h=320, m="wallpaper_green", name="pic3"), location=(0.1, R["y0"], 1.5), rot_deg=180, col=col)
    return walls, hinge, chair


def lights(col):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("RoomSky")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.55, 0.72, 1.0, 1)
    bg.inputs[1].default_value = 1.6
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 4.5
    sun.data.angle = math.radians(2)
    sun.data.color = (1.0, 0.93, 0.82)
    col.objects.link(sun)
    sun.rotation_euler = Euler((math.radians(-50), 0, math.radians(15)))   # свет из окна (с севера) вниз
    for name, loc, size, energy, color in (("Ceiling", (0.0, 0.0, 2.5), 1.4, 170, (1.0, 0.85, 0.65)),
                                           ("FillSouth", (0.3, -1.3, 2.45), 1.6, 110, (0.95, 0.95, 1.0)),
                                           ("FillWest", (-1.2, -0.2, 2.45), 1.0, 60, (1.0, 0.9, 0.8))):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.size, ld.energy, ld.color = size, energy, color
        lo = bpy.data.objects.new(name, ld)
        col.objects.link(lo)
        lo.location = loc
    pl = bpy.data.objects.new("DeskBulb", bpy.data.lights.new("DeskBulb", 'POINT'))
    pl.data.energy, pl.data.shadow_soft_size, pl.data.color = 8, 0.03, (1.0, 0.8, 0.55)
    col.objects.link(pl)
    pl.location = (-0.45, 1.47, 0.78)


# ---------------------------------------------------------------------------
# Хореография
# ---------------------------------------------------------------------------
def V(*a):
    return Vector(a)


def choreograph(g, props_col):
    H = g.H
    seat_top = 0.34
    sit_z = seat_top + 0.065 - g.hip_rest
    sitA, sitB = V(-0.8, 1.13, 0), V(-0.8, 0.83, 0)
    stand = V(-0.8, 1.04, 0)
    at_dresser = V(-1.42, -0.16, 0)
    at_bag = V(1.10, -0.62, 0)
    g.path = Path([
        Hold(1, 268, sitA, 180),
        Walk(269, 290, [sitA, sitB], ease=10),                        # отъезжает со стулом
        Hold(291, 300, sitB, 180),
        Walk(301, 318, [sitB, stand], ease=9),                        # соскальзывает вперёд и встаёт
        Hold(319, 328, stand, 180, 240),
        Walk(329, 392, [stand, (-1.25, 0.9), (-1.36, 0.4), at_dresser], ease=12),
        Hold(393, 712, at_dresser, -90),
        Walk(713, 785, [at_dresser, (-0.6, -0.36), (0.3, -0.5), at_bag], ease=12, turn_in=16),
        Hold(786, 850, at_bag, 90, 5),
        Walk(851, 900, [at_bag, (1.02, -1.25), (1.0, -1.9), (1.0, -2.45)], ease=10, turn_in=4),
    ])
    g.set("sit", [(1, 1.0), (300, 1.0), (318, 0.0)])
    g.set("sit_z", [(1, sit_z)])
    g.set("lean", [(1, 14), (230, 14), (262, 4), (268, 0), (380, 0), (398, 18), (408, 6), (530, 6), (538, 16),
                   (546, 4), (572, 16), (582, 4), (598, 8), (690, 6), (700, 0), (786, 0), (800, 20), (812, 0)])
    g.set("squat", [(786, 0.0), (800, 0.85), (806, 0.85), (818, 0.0)])
    g.set("hop", [(630, 0.0), (637, 0.06), (644, 0.0), (650, 0.05), (657, 0.0)])
    g.set("tilt", [(600, 0), (620, 10), (640, -6), (662, 8), (690, 0)])
    # взгляд
    notebook = V(-0.78, 1.36, 0.57)
    g.set("look", [(1, notebook), (240, notebook), (262, V(-0.8, 2.2, 1.2)), (330, V(-1.6, -0.2, 0.8)),
                   (392, V(-2.0, -0.16, 1.0)), (540, V(-2.0, -0.16, 1.0)), (548, V(-1.74, 0.2, 0.66)),
                   (578, V(-1.74, 0.2, 0.66)), (590, V(-1.62, -0.19, 0.80)), (690, V(-1.62, -0.19, 0.80)),
                   (700, None)])
    g.set("look_w", [(1, 1.0), (262, 1.0), (272, 0.3), (330, 0.4), (392, 0.6), (540, 0.6), (548, 1.0), (585, 1.0),
                     (600, 0.85), (690, 0.85), (700, 0.0)])
    g.set("bow", [(592, 0), (600, 6), (628, 6), (636, 0), (660, 0), (675, 8), (690, 6), (700, 0)])

    # --- правая рука: цели по фазам
    def right_hand(f):
        pos, psi = g.path.at(f)
        F = V(math.sin(psi), -math.cos(psi), 0)
        Lv = V(math.cos(psi), math.sin(psi), 0)
        Z = V(0, 0, 1)
        if f <= 236:                                                  # пишет
            line = (f // 46) % 4
            u = (f % 46) / 46
            return V(-0.86 + 0.12 * u, 1.33 + 0.018 * line, 0.585 + 0.004 * abs(math.sin(f * 1.3))) \
                + V(0.004 * math.sin(f * 2.1), 0.003 * math.cos(f * 2.9), 0)
        if f <= 246:
            return V(-0.62, 1.34, 0.58)                               # кладёт карандаш
        if f <= 262:
            u = (f - 246) / 16
            return V(-0.66 - 0.2 * u, 1.36, 0.59 + 0.03 * math.sin(math.pi * u))   # закрывает тетрадь
        if 392 <= f <= 402:
            return V(-1.70, 0.04, 0.70)                               # к расчёске
        if 402 < f <= 520:                                            # расчёсывается: 3 движения сверху вниз
            k = (f - 402) / 118 * 3
            u = k % 1
            down = u / 0.7 if u < 0.7 else 1 - (u - 0.7) / 0.3
            top = pos + Z * 0.93 * H / 1.3 - Lv * 0.21 + F * 0.02
            bot = pos + Z * 0.70 * H / 1.3 - Lv * 0.19 + F * 0.05
            return top.lerp(bot, P.smooth(down))
        if 520 < f <= 540:
            return V(-1.70, 0.04, 0.71)                               # кладёт расчёску
        if 560 <= f <= 580:
            return V(-1.72, 0.20, 0.70)                               # берёт телефон
        if 580 < f <= 692:
            return pos + Z * 0.74 * H / 1.3 + F * 0.17 - Lv * 0.03    # телефон перед лицом
        if 692 < f <= 706:
            return pos + Z * 0.42 * H / 1.3 - Lv * 0.15 + F * 0.04    # в карман
        if 786 <= f <= 812:
            return V(BAG[0], BAG[1], 0.30)                            # за ручку рюкзака
        if 812 < f <= 842:
            u = (f - 812) / 30
            a = pos + Z * 0.55 - Lv * 0.16 + F * 0.12
            b = pos + Z * 0.88 * H / 1.3 - Lv * 0.12 - F * 0.02       # через плечо
            return a.lerp(b, P.smooth(u))
        return pos + Z * 0.45 - Lv * 0.15
    g.T["hand_R"] = right_hand
    g.set("ik_R", [(1, 1.0), (262, 1.0), (272, 0.0), (386, 0.0), (394, 1.0), (540, 1.0), (548, 0.0), (556, 0.0),
                   (564, 1.0), (706, 1.0), (714, 0.0), (784, 0.0), (792, 1.0), (840, 1.0), (850, 0.0)])

    # левая рука: на столе, придерживает тетрадь
    g.T["hand_L"] = Track([(1, V(-0.97, 1.31, 0.585))])
    g.set("ik_L", [(1, 1.0), (262, 1.0), (272, 0.0)])

    # --- реквизит
    def put(name, loc, rot=(0, 0, 0), **kw):
        ob = parts.place(CG.get(name, **kw), location=loc, col=props_col)
        ob.rotation_euler = [math.radians(a) for a in rot]
        return ob

    pencil = put("pencil", (-0.62, 1.34, 0.564), (0, 0, 20))
    nb_open = put("notebook_open", (-0.78, 1.37, 0.56), (0, 0, 3))
    nb_closed = put("notebook_closed", (-0.87, 1.37, 0.56), (0, 0, 3))
    comb = put("comb", (-1.70, 0.04, 0.652), (0, 0, 80))
    phone = put("phone", (-1.73, 0.21, 0.652), (0, 0, 75))
    bag = put("backpack", (BAG[0], BAG[1], 0.0), (-12, 0, 90))
    bpy.context.view_layer.update()
    pencil_desk = pencil.matrix_world.copy()
    g.props = [
        Prop(pencil, [(1, "hand_R", "pencil"), (244, "world", pencil_desk)], blend=6),
        Prop(nb_open, [(256, "hidden")]),
        Prop(nb_closed, [(1, "hidden"), (256, "world", None)]),
        Prop(comb, [(400, "hand_R", "comb"), (536, "world", comb.matrix_world.copy())], blend=5),
        Prop(phone, [(578, "hand_R", "phone"), (704, "hidden")], blend=6),
        Prop(bag, [(810, "hand_R", "bag"), (832, "back")], blend=10, scale=0.8),
    ]
    # экран телефона загорается при звонке
    m = bpy.data.materials.get("M_screen_on")
    if m:
        b = m.node_tree.nodes.get("Principled BSDF")
        for f, v in ((1, 0.0), (544, 0.0), (546, 4.0), (704, 4.0)):
            b.inputs["Emission Strength"].default_value = v
            b.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
    return {"chair": None, "phone": phone}


def animate_set(hinge, chair):
    # стул отъезжает назад вместе с девочкой
    chair.location = (*CHAIR0, 0)
    chair.keyframe_insert("location", frame=269)
    chair.location = (*CHAIR1, 0)
    chair.keyframe_insert("location", frame=290)
    # дверь открывается внутрь
    hinge.rotation_euler = (0, 0, 0)
    hinge.keyframe_insert("rotation_euler", frame=832)
    hinge.rotation_euler = (0, 0, math.radians(-100))
    hinge.keyframe_insert("rotation_euler", frame=858)


def shots(walls):
    from cinema import Shot
    N = [walls["Wall_N"], walls["Window"], walls["Curtains"]]
    Wd = [walls["Wall_W"], walls["Mirror"]]
    return [
        Shot("R1_establish", 1, 110, [(1, (1.75, -1.45, 1.65)), (110, (1.25, -0.95, 1.45))], ("chest", (0, 0, 0)), 22, fstop=5.6),
        Shot("R2_shoulder", 111, 180, [(111, (-0.16, 0.92, 1.42)), (180, (-0.22, 0.98, 1.36))],
             ("hand.R", (0, 0, -0.02)), 30, fstop=4.0),
        Shot("R3_face", 181, 275, [(181, (-0.70, 2.85, 1.0)), (275, (-0.80, 2.65, 0.98))], ("head", (0, 0, -0.14)), 32,
             fstop=4.0, wild=N),
        Shot("R4_standup", 276, 365, [(276, (0.95, 0.35, 1.2)), (365, (0.7, 0.1, 1.15))], ("chest", (0, 0, 0.08)), 26),
        Shot("R5_comb", 366, 450, [(366, (-1.30, 0.95, 1.12)), (450, (-1.42, 0.80, 1.08))], ("head", (0, 0, -0.12)), 30),
        Shot("R6_comb_close", 451, 545, [(451, (-2.75, 0.62, 1.04)), (545, (-2.65, 0.56, 1.02))], ("head", (0, 0, -0.12)), 35,
             fstop=4.0, wild=Wd),
        Shot("R7_phone", 546, 700, [(546, (-2.65, -0.98, 0.98)), (700, (-2.55, -0.92, 0.95))], ("head", (0, 0, -0.18)), 32,
             fstop=4.0, wild=Wd),
        Shot("R8_to_bag", 701, 790, [(701, (-1.55, 1.15, 1.5)), (790, (-1.3, 1.0, 1.4))], ("chest", (0, 0, 0)), 24),
        Shot("R9_exit", 791, 900, [(791, (0.1, 0.7, 0.6)), (900, (0.25, 0.55, 0.75))], ("chest", (0, 0, 0)), 26),
    ]
