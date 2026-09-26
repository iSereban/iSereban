"""
Woman 50 — стилизованный (Disney-like) персонаж, собранный по координатам скелета.

Источник координат: woman50_bone_coordinates.txt (лежит рядом, читается при запуске —
поменяешь цифры в файле, персонаж перестроится).

Что строится:
  * Арматура Woman50_Rig: все кости из файла (тело + лицевые ctrl_*) + пальцы
  * Тело (Skin-модификатор по суставам), скрыто под одеждой маской
  * Голова: череп, нос, щёки, подбородок, уши, рот с отверстием, губы, зубы, язык,
    глаза (зрачок/радужка), веки, брови, причёска «боб»
  * Одежда отдельными мешами: кардиган с пуговицами, брюки, домашние туфли
  * Лицевые shape keys: smile, frown, mouth_O, brow_up, cheek_puff
  * Кости рта/глаз работают: ctrl_jaw (открыть рот), ctrl_eye.* (взгляд),
    ctrl_lid_* (моргание), ctrl_tongue, ctrl_teeth_*

Система: метры, стоит на Z=0, лицом в −Y.

Запуск:
  * Blender → Scripting → Open → woman50.py → Run Script
  * blender -b -P woman50.py -- --out ./out         (сохранит out/woman50.blend)
  * из другого скрипта:  import woman50; rig = woman50.build()
"""

import math
import os
import re
import sys

import bpy  # noqa: I001
import bmesh
from mathutils import Matrix, Vector, kdtree

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    _HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "common"))
import studio  # noqa: E402

COORDS_FILE = os.path.join(_HERE, "woman50_bone_coordinates.txt")
NAME = "Woman50"

# ---------------------------------------------------------------------------
# Внешность (правится здесь)
# ---------------------------------------------------------------------------
SKIN = (0.60, 0.36, 0.26)          # цвета — линейные (как в Blender), не sRGB
LIPS = (0.42, 0.13, 0.12)
HAIR = (0.10, 0.065, 0.045)
HAIR_GREY = (0.18, 0.16, 0.15)
IRIS = (0.12, 0.06, 0.02)
CARDIGAN = (0.32, 0.10, 0.13)
PANTS = (0.035, 0.04, 0.06)
SHOES = (0.09, 0.045, 0.025)
BUTTON = (0.70, 0.62, 0.48)

EYE_R = 0.0165

# Иерархия костей (из раздела «ИЕРАРХИЯ» файла)
PARENTS = {
    "spine": None,
    "pelvis.L": "spine", "pelvis.R": "spine",
    "spine.001": "spine", "spine.002": "spine.001", "spine.003": "spine.002",
    "spine.004": "spine.003", "spine.005": "spine.004", "spine.006": "spine.005",
    "breast.L": "spine.003", "breast.R": "spine.003",
    "ctrl_jaw": "spine.006", "ctrl_teeth_up": "spine.006",
    "ctrl_eye.L": "spine.006", "ctrl_eye.R": "spine.006",
    "ctrl_lid_top.L": "ctrl_eye.L", "ctrl_lid_bot.L": "ctrl_eye.L",
    "ctrl_lid_top.R": "ctrl_eye.R", "ctrl_lid_bot.R": "ctrl_eye.R",
    "ctrl_mouth_C": "ctrl_jaw", "ctrl_mouth_L": "ctrl_jaw", "ctrl_mouth_R": "ctrl_jaw",
    "ctrl_smile.L": "ctrl_jaw", "ctrl_smile.R": "ctrl_jaw",
    "ctrl_teeth_lo": "ctrl_jaw", "ctrl_tongue": "ctrl_jaw",
}
for _s in ("L", "R"):
    PARENTS.update({
        f"thigh.{_s}": "spine", f"shin.{_s}": f"thigh.{_s}", f"foot.{_s}": f"shin.{_s}",
        f"toe.{_s}": f"foot.{_s}", f"heel.02.{_s}": f"foot.{_s}",
        f"shoulder.{_s}": "spine.003", f"upper_arm.{_s}": f"shoulder.{_s}",
        f"forearm.{_s}": f"upper_arm.{_s}", f"hand.{_s}": f"forearm.{_s}",
    })

NON_DEFORM = {"heel.02.L", "heel.02.R", "breast.L", "breast.R", "pelvis.L", "pelvis.R"}
FINGERS = (  # имя, смещение поперёк ладони (к большому пальцу +), длина
    ("f_index", 0.021, 0.074), ("f_middle", 0.007, 0.080),
    ("f_ring", -0.007, 0.074), ("f_pinky", -0.020, 0.058),
)


# ---------------------------------------------------------------------------
# Чтение координат
# ---------------------------------------------------------------------------
_NUM = r"(-?\d+\.\d+)"
_BONE_RE = re.compile(rf"^(\S+)(?:\s+\([^)]*\))?\s+{_NUM},\s*{_NUM},\s*{_NUM}\s+{_NUM},\s*{_NUM},\s*{_NUM}\s*$")
_LM_RE = re.compile(rf"^(LM_\S+)\s+{_NUM},\s*{_NUM},\s*{_NUM}\s*$")


def load_coords(path=COORDS_FILE):
    bones, landmarks = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            m = _BONE_RE.match(line)
            if m:
                v = [float(x) for x in m.groups()[1:]]
                bones[m.group(1)] = (Vector(v[:3]), Vector(v[3:]))
                continue
            m = _LM_RE.match(line)
            if m:
                landmarks[m.group(1)] = Vector([float(x) for x in m.groups()[1:]])
    return bones, landmarks


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Арматура
# ---------------------------------------------------------------------------
def hand_frame(bones, side):
    """Оси кисти: d — вдоль кисти, s — поперёк (к большому пальцу, вперёд), n — нормаль ладони."""
    h0, h1 = bones[f"hand.{side}"]
    d = (h1 - h0).normalized()
    fwd = Vector((0, -1, 0))
    s = (fwd - d * fwd.dot(d)).normalized()
    n = d.cross(s)
    if side == "R":
        n = -n
    return h0, h1, d, s, n


def finger_chains(bones, side):
    """{имя_кости: (head, tail)} для пальцев."""
    h0, h1, d, s, n = hand_frame(bones, side)
    out = {}
    for name, off, length in FINGERS:
        base = h1 + s * off
        dd = (d + s * off * 3.0).normalized()
        mid = base + dd * length * 0.55
        tip = mid + (dd - n * 0.25).normalized() * length * 0.45
        out[f"{name}.01.{side}"] = (base, mid)
        out[f"{name}.02.{side}"] = (mid, tip)
    tb = lerp(h0, h1, 0.35) + s * 0.022 - n * 0.008
    td = (d * 0.55 + s * 0.85).normalized()
    tm = tb + td * 0.034
    tt = tm + (td + d * 0.4).normalized() * 0.028
    out[f"f_thumb.01.{side}"] = (tb, tm)
    out[f"f_thumb.02.{side}"] = (tm, tt)
    return out


def build_armature(bones, col):
    arm_data = bpy.data.armatures.new(f"{NAME}_Rig")
    arm = bpy.data.objects.new(f"{NAME}_Rig", arm_data)
    col.objects.link(arm)
    arm.show_in_front = True
    arm_data.display_type = 'OCTAHEDRAL'

    all_bones = dict(bones)
    parents = dict(PARENTS)
    # веки: точка вращения — центр глаза (иначе веко при моргании съезжает с глазного яблока)
    for side in ("L", "R"):
        eye_h, _ = bones[f"ctrl_eye.{side}"]
        for lid in ("top", "bot"):
            name = f"ctrl_lid_{lid}.{side}"
            h, t = bones[name]
            all_bones[name] = (eye_h.copy(), eye_h + (t - h).normalized() * 0.02 + Vector((0, 0, h.z - eye_h.z)))
        for name, ht in finger_chains(bones, side).items():
            all_bones[name] = ht
            parents[name] = name.replace(".02.", ".01.") if ".02." in name else f"hand.{side}"

    with bpy.context.temp_override(object=arm, active_object=arm):
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm_data.edit_bones
        for name, (h, t) in all_bones.items():
            b = eb.new(name)
            b.head, b.tail = h, t
            b.roll = 0.0
            b.use_deform = not (name in NON_DEFORM or name.startswith("ctrl_"))
        for name in all_bones:
            p = parents.get(name)
            if p and p in eb:
                b = eb[name]
                b.parent = eb[p]
                b.use_connect = (b.head - eb[p].tail).length < 1e-4
        # «голова» лица: кость челюсти деформирует голову через вершинные группы
        eb["ctrl_jaw"].use_deform = True
        bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    return arm


# ---------------------------------------------------------------------------
# Тело / одежда: граф суставов + Skin-модификатор
# ---------------------------------------------------------------------------
def skeleton_nodes(bones):
    """Узлы (позиция, радиус X, радиус Y) и рёбра графа тела."""
    B = bones
    N, E = {}, []

    def node(k, p, rx, ry=None):
        N[k] = (Vector(p), rx, ry if ry is not None else rx)

    sp = B["spine"][0]
    node("pelvis", sp + Vector((0, -0.005, 0.0)), 0.150, 0.110)
    node("waist", B["spine"][1], 0.128, 0.092)
    node("belly", B["spine.001"][1], 0.122, 0.090)
    node("chest", B["spine.002"][1] + Vector((0, -0.012, 0)), 0.145, 0.105)
    node("chest_top", Vector((0, 0.012, B["shoulder.L"][0].z - 0.01)), 0.150, 0.088)
    node("neck0", B["spine.003"][1], 0.056, 0.052)
    node("neck1", B["spine.004"][1], 0.048, 0.048)
    node("neck2", B["spine.005"][1], 0.044, 0.044)
    E += [("pelvis", "waist"), ("waist", "belly"), ("belly", "chest"), ("chest", "chest_top"),
          ("chest_top", "neck0"), ("neck0", "neck1"), ("neck1", "neck2")]

    for s in ("L", "R"):
        th0, th1 = B[f"thigh.{s}"]
        sh0, sh1 = B[f"shin.{s}"]
        f0, f1 = B[f"foot.{s}"]
        t0, t1 = B[f"toe.{s}"]
        node(f"hip.{s}", th0 + Vector((0, 0, -0.035)), 0.088, 0.092)
        node(f"thigh.{s}", lerp(th0, th1, 0.45), 0.072, 0.075)
        node(f"knee.{s}", th1, 0.050, 0.054)
        node(f"calf.{s}", lerp(sh0, sh1, 0.30), 0.052, 0.058)
        node(f"ankle.{s}", sh1, 0.031, 0.033)
        node(f"ball.{s}", Vector((f1.x, f1.y, 0.021)), 0.040, 0.020)
        node(f"toe.{s}", Vector((t1.x, t1.y + 0.01, 0.016)), 0.030, 0.015)
        E += [("pelvis", f"hip.{s}"), (f"hip.{s}", f"thigh.{s}"), (f"thigh.{s}", f"knee.{s}"),
              (f"knee.{s}", f"calf.{s}"), (f"calf.{s}", f"ankle.{s}"), (f"ankle.{s}", f"ball.{s}"),
              (f"ball.{s}", f"toe.{s}")]

        ua0, ua1 = B[f"upper_arm.{s}"]
        fa0, fa1 = B[f"forearm.{s}"]
        h0, h1, d, sv, nv = hand_frame(B, s)
        node(f"shoulder.{s}", ua0 + Vector((0, 0, 0.005)), 0.052, 0.054)
        node(f"uarm.{s}", lerp(ua0, ua1, 0.5), 0.043, 0.043)
        node(f"elbow.{s}", fa0, 0.035, 0.035)
        node(f"farm.{s}", lerp(fa0, fa1, 0.5), 0.033, 0.030)
        node(f"wrist.{s}", h0, 0.024, 0.019)
        node(f"palm.{s}", lerp(h0, h1, 0.55), 0.034, 0.014)
        node(f"knuckle.{s}", h1 - d * 0.004, 0.036, 0.012)
        E += [("chest_top", f"shoulder.{s}"), (f"shoulder.{s}", f"uarm.{s}"), (f"uarm.{s}", f"elbow.{s}"),
              (f"elbow.{s}", f"farm.{s}"), (f"farm.{s}", f"wrist.{s}"), (f"wrist.{s}", f"palm.{s}"),
              (f"palm.{s}", f"knuckle.{s}")]
        fc = finger_chains(B, s)
        for fname, _off, _len in FINGERS:
            a, m = fc[f"{fname}.01.{s}"]
            _, tip = fc[f"{fname}.02.{s}"]
            r = 0.0085 if fname != "f_pinky" else 0.0075
            node(f"{fname}0.{s}", a, r)
            node(f"{fname}1.{s}", m, r * 0.95)
            node(f"{fname}2.{s}", tip, r * 0.8)
            E += [(f"knuckle.{s}", f"{fname}0.{s}"), (f"{fname}0.{s}", f"{fname}1.{s}"),
                  (f"{fname}1.{s}", f"{fname}2.{s}")]
        a, m = fc[f"f_thumb.01.{s}"]
        _, tip = fc[f"f_thumb.02.{s}"]
        node(f"thumb0.{s}", a, 0.011)
        node(f"thumb1.{s}", m, 0.0095)
        node(f"thumb2.{s}", tip, 0.008)
        E += [(f"palm.{s}", f"thumb0.{s}"), (f"thumb0.{s}", f"thumb1.{s}"), (f"thumb1.{s}", f"thumb2.{s}")]
    return N, E


def skin_mesh(name, nodes, edges, root, col, mat, subdiv=2):
    keys = list(nodes)
    idx = {k: i for i, k in enumerate(keys)}
    me = bpy.data.meshes.new(name)
    me.from_pydata([nodes[k][0] for k in keys], [(idx[a], idx[b]) for a, b in edges], [])
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    mod = obj.modifiers.new("Skin", 'SKIN')
    mod.use_smooth_shade = True
    mod.branch_smoothing = 0.5
    sv = me.skin_vertices[0].data
    for k in keys:
        _, rx, ry = nodes[k]
        sv[idx[k]].radius = (rx, ry)
        sv[idx[k]].use_root = (k in root) if isinstance(root, (set, tuple, list)) else (k == root)
    studio.apply_modifier(obj, mod)
    sub = obj.modifiers.new("Subdiv", 'SUBSURF')
    sub.levels = subdiv
    studio.apply_modifier(obj, sub)
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.materials.append(mat)
    return obj


def sub_graph(nodes, edges, keep, grow, extra=None):
    """Подграф для одежды: оставить узлы keep, увеличить радиусы на grow(key)."""
    N = {}
    for k in keep:
        p, rx, ry = nodes[k]
        g = grow(k)
        N[k] = (p.copy(), rx + g, ry + g)
    if extra:
        N.update(extra)
    E = [(a, b) for a, b in edges if a in N and b in N]
    return N, E


# ---------------------------------------------------------------------------
# Голова: параметрическая поверхность
# ---------------------------------------------------------------------------
class Head:
    """Поверхность головы P(θ, φ): θ — от макушки (0) к низу (π), φ — от лица (0) по кругу."""

    def __init__(self, bones, lm):
        top = lm.get("LM_head_top", Vector((0, -0.021, 1.683)))
        self.mouth = lm.get("LM_mouth", Vector((0, -0.09, 1.488)))
        self.eyes = {"L": bones["ctrl_eye.L"][0], "R": bones["ctrl_eye.R"][0]}
        self.az = 0.117
        self.c = Vector((0.0, -0.004, top.z - self.az))
        self.ax = 0.077
        self.ay = 0.086

    def raw(self, th, ph):
        x = self.ax * math.sin(th) * math.sin(ph)
        y = -self.ay * math.sin(th) * math.cos(ph)
        z = self.az * math.cos(th)
        fw = max(0.0, math.cos(ph)) ** 2           # «передняя» часть
        t = max(0.0, -z / self.az)
        x *= 1 - 0.20 * t ** 1.8                    # сужение к челюсти
        if y > 0:
            y *= 1 - 0.45 * t ** 1.3                # затылок → шея
            if z > -0.02:
                y *= 1.06
        zw = self.c.z + z

        def g(cx, cz, sx, sz):
            return math.exp(-((x - cx) / sx) ** 2 - ((zw - cz) / sz) ** 2)

        mz = self.mouth.z
        y -= 0.026 * fw * g(0, mz, 0.042, 0.036)                          # «мордочка» у рта
        y -= 0.010 * fw * g(0, mz - 0.032, 0.026, 0.014)                  # подбородок
        y -= 0.021 * fw * g(0, mz + 0.030, 0.011, 0.013)                  # нос
        y -= 0.006 * fw * g(0, mz + 0.055, 0.008, 0.013)                  # спинка носа
        for sx in (-1, 1):
            ex, ez = sx * abs(self.eyes["L"].x), self.eyes["L"].z
            y += 0.006 * fw * g(ex, ez, 0.016, 0.013)                     # глазницы
            y -= 0.004 * fw * g(ex, ez + 0.024, 0.02, 0.008)              # надбровья
            y -= 0.009 * fw * g(sx * 0.046, mz + 0.018, 0.022, 0.022)     # щёки
            x += sx * 0.006 * fw * g(sx * 0.05, mz + 0.016, 0.022, 0.028)
        return Vector((x, y, z)) + self.c

    def normal(self, th, ph, e=1e-3):
        a = self.raw(th + e, ph) - self.raw(th - e, ph)
        b = self.raw(th, ph + e) - self.raw(th, ph - e)
        n = a.cross(b)
        if n.length < 1e-12:
            return Vector((0, 0, 1 if th < 1 else -1))
        n.normalize()
        p = self.raw(th, ph) - self.c
        return n if n.dot(p) > 0 else -n

    def theta_at_z(self, z):
        return math.acos(max(-1, min(1, (z - self.c.z) / self.az)))

    def surface_y(self, x, z):
        """Y передней поверхности в точке (x, z)."""
        th = self.theta_at_z(z)
        lo, hi = -math.pi / 2, math.pi / 2
        for _ in range(50):
            mid = (lo + hi) / 2
            if self.raw(th, mid).x < x:
                lo = mid
            else:
                hi = mid
        return self.raw(th, (lo + hi) / 2).y, (th, (lo + hi) / 2)


def mouth_params(head, half_w=0.021, half_h=0.0020):
    th_m = head.theta_at_z(head.mouth.z)
    th_a = head.theta_at_z(head.mouth.z + half_h)
    th_b = head.theta_at_z(head.mouth.z - half_h)
    _, (_, ph_m) = head.surface_y(half_w, head.mouth.z)
    return th_m, th_a, th_b, ph_m


def build_head(head, col, mats):
    th_m, th_a, th_b, ph_m = mouth_params(head)
    nth, nph = 48, 72
    ths = sorted(set([math.pi * i / nth for i in range(nth + 1)] + [th_a, th_b]))
    phs = sorted(set([-math.pi + 2 * math.pi * i / nph for i in range(nph)] + [-ph_m, ph_m]))
    # сгущаем сетку вокруг рта
    extra_ph = [ph_m * k / 4 for k in range(-3, 4)]
    phs = sorted(set(phs + extra_ph))
    ths = sorted(set(ths + [lerp(th_a, th_b, 0.5), th_a - (th_b - th_a), th_b + (th_b - th_a)]))

    bm = bmesh.new()
    grid = [[bm.verts.new(head.raw(t, p)) for p in phs] for t in ths]
    for i in range(len(ths) - 1):
        for j in range(len(phs)):
            k = (j + 1) % len(phs)
            tc = (ths[i] + ths[i + 1]) / 2
            pc = (phs[j] + phs[k]) / 2 if k else (phs[j] + math.pi)
            if th_a < tc < th_b and -ph_m < pc < ph_m:
                continue  # отверстие рта
            bm.faces.new((grid[i][j], grid[i][k], grid[i + 1][k], grid[i + 1][j]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{NAME}_Head")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(f"{NAME}_Head", me)
    col.objects.link(obj)
    me.materials.append(mats["skin"])
    return obj


def build_lips(head, col, mats):
    th_m, th_a, th_b, ph_m = mouth_params(head)
    M, K = 72, 10
    bm = bmesh.new()
    rings, jaw_w = [], []
    hc = head.raw(th_m, 0.0)
    for i in range(M):
        s = 2 * math.pi * i / M
        c, sn = math.cos(s), math.sin(s)
        ph = ph_m * math.copysign(abs(c) ** 0.55, c) * 1.02
        th = th_m - (th_m - th_a) * 1.05 * math.copysign(abs(sn) ** 0.8, sn)
        p = head.raw(th, ph)
        n = head.normal(th, ph)
        out = p - hc
        out -= n * out.dot(n)
        out.normalize()
        upper = sn > 0
        rt = 0.0026 + ((0.0044 if upper else 0.0056) - 0.0026) * abs(sn) ** 0.7
        center = p + n * 0.0010 - out * rt * 0.55
        ring = []
        for k in range(K):
            a = 2 * math.pi * k / K
            ring.append(bm.verts.new(center + (n * math.cos(a) + out * math.sin(a)) * rt))
        rings.append(ring)
        jaw_w.append(smoothstep(0.5 - sn * 2.5))   # нижняя губа → челюсть, уголки пополам
    for i in range(M):
        r0, r1 = rings[i], rings[(i + 1) % M]
        for k in range(K):
            k1 = (k + 1) % K
            bm.faces.new((r0[k], r0[k1], r1[k1], r1[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{NAME}_Lips")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(f"{NAME}_Lips", me)
    col.objects.link(obj)
    me.materials.append(mats["lips"])
    g_head = obj.vertex_groups.new(name="spine.006")
    g_jaw = obj.vertex_groups.new(name="ctrl_jaw")
    for i, w in enumerate(jaw_w):
        idx = list(range(i * K, i * K + K))
        g_jaw.add(idx, w, 'REPLACE')
        g_head.add(idx, 1 - w, 'REPLACE')
    return obj


def ellipsoid(name, center, radii, mat, col, segs=24, rings=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    obj.location = center
    return obj


def build_teeth(head, col, mats, upper):
    th_m, th_a, th_b, ph_m = mouth_params(head)
    y_front, _ = head.surface_y(0.0, head.mouth.z)
    z = head.mouth.z + (0.0036 if upper else -0.0042)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=6, use_grid_fill=True)
    for v in bm.verts:
        x, y, zz = v.co
        v.co = Vector((x * 0.028, y * 0.009, zz * 0.0075))
        v.co.y += 14.0 * v.co.x ** 2          # дуга зубного ряда
    me = bpy.data.meshes.new("Teeth_Upper" if upper else "Teeth_Lower")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(me.name, me)
    col.objects.link(obj)
    obj.location = (0, y_front + 0.0105, z)
    sub = obj.modifiers.new("Round", 'SUBSURF')
    sub.levels = sub.render_levels = 2
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["teeth"])
    return obj


def eye_material(name="Eye"):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.08
    tc = nt.nodes.new("ShaderNodeTexCoord")
    norm = nt.nodes.new("ShaderNodeVectorMath")
    norm.operation = 'NORMALIZE'
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = (0, -1, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'LINEAR'
    cr.elements[0].position = 0.80
    cr.elements[0].color = (0.92, 0.90, 0.88, 1)
    cr.elements[1].position = 0.815
    cr.elements[1].color = (*IRIS, 1)
    e = cr.elements.new(0.935)
    e.color = (min(IRIS[0] * 1.8, 1), min(IRIS[1] * 1.8, 1), IRIS[2] * 1.5, 1)
    e = cr.elements.new(0.945)
    e.color = (0.01, 0.01, 0.01, 1)
    nt.links.new(tc.outputs["Object"], norm.inputs[0])
    nt.links.new(norm.outputs["Vector"], dot.inputs[0])
    nt.links.new(dot.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    mat.diffuse_color = (0.9, 0.9, 0.9, 1)
    return mat


def lid_shell(name, center, r, polar_from, polar_to, mats, col):
    """Веко: часть сферы; polar — угол от +Z (0 — верх, 180 — низ)."""
    bm = bmesh.new()
    nu, nv = 32, 10
    rows = []
    for i in range(nv + 1):
        pa = math.radians(lerp(polar_from, polar_to, i / nv))
        rows.append([bm.verts.new(Vector((r * math.sin(pa) * math.sin(2 * math.pi * j / nu),
                                          -r * math.sin(pa) * math.cos(2 * math.pi * j / nu),
                                          r * math.cos(pa)))) for j in range(nu)])
    edge_row = nv - 1 if polar_from < polar_to else 0
    for i in range(nv):
        for j in range(nu):
            k = (j + 1) % nu
            f = bm.faces.new((rows[i][j], rows[i][k], rows[i + 1][k], rows[i + 1][j]))
            lash = (i == nv - 1) if polar_from < 90 else (i == 0)
            f.material_index = 1 if lash else 0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    del edge_row
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["skin"])
    me.materials.append(mats["lash"])
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    obj.location = center
    sol = obj.modifiers.new("Thick", 'SOLIDIFY')
    sol.thickness = 0.0012
    return obj


def build_brows(head, col, mats):
    bm = bmesh.new()
    for sx in (-1, 1):
        ex, ez = abs(head.eyes["L"].x), head.eyes["L"].z
        pts = []
        for i in range(13):
            u = i / 12
            x = sx * (ex - 0.020 + 0.042 * u)
            z = ez + 0.021 + 0.006 * math.sin(math.pi * (u * 0.85 + 0.1)) - 0.003 * u
            y, (th, ph) = head.surface_y(x, z)
            n = head.normal(th, ph)
            w = 0.0028 * (1 - 0.6 * u) + 0.0008
            pts.append((Vector((x, y, z)) + n * 0.0012, n, w))
        rows = []
        for p, n, w in pts:
            up = Vector((0, 0, 1))
            up -= n * up.dot(n)
            up.normalize()
            rows.append([bm.verts.new(p + up * w), bm.verts.new(p - up * w),
                         bm.verts.new(p - up * w * 0.5 + n * 0.0012), bm.verts.new(p + up * w * 0.5 + n * 0.0012)])
        for i in range(len(rows) - 1):
            for k in range(4):
                k1 = (k + 1) % 4
                bm.faces.new((rows[i][k], rows[i][k1], rows[i + 1][k1], rows[i + 1][k]))
        bm.faces.new(rows[0][::-1])
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{NAME}_Brows")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["brow"])
    obj = bpy.data.objects.new(f"{NAME}_Brows", me)
    col.objects.link(obj)
    return obj


def build_hair(head, col, mats):
    """Причёска «боб» с косой чёлкой: оболочка над поверхностью головы."""
    nph, nt = 96, 30
    ez = head.eyes["L"].z
    bm = bmesh.new()
    grid = []
    for j in range(nph):
        ph = -math.pi + 2 * math.pi * j / nph
        a = abs(ph)
        # нижняя граница волос (мировая Z) по кругу: лоб → виски → каре → затылок
        front = ez + 0.058 - 0.022 * smoothstep((ph + 0.1) / 0.6) * (1 if ph > 0 else 0.3)
        side = head.mouth.z + 0.002
        back = head.mouth.z - 0.012
        if a < 1.45:
            z_lim = lerp(front, side, smoothstep((a - 0.55) / 0.85))
        else:
            z_lim = lerp(side, back, smoothstep((a - 1.7) / 1.1))
        th_lim = head.theta_at_z(z_lim)
        col_v = []
        for i in range(nt + 1):
            u = i / nt
            th = th_lim * (u ** 0.9)
            p = head.raw(th, ph)
            n = head.normal(th, ph)
            vol = 0.010 + 0.010 * math.cos(th) ** 2 + 0.006 * smoothstep((a - 0.6) / 1.0)
            flare = 0.012 * smoothstep((u - 0.75) / 0.25) * smoothstep((a - 1.3) / 0.5)
            col_v.append(bm.verts.new(p + n * (vol + flare)))
        grid.append(col_v)
    for j in range(nph):
        k = (j + 1) % nph
        for i in range(nt):
            bm.faces.new((grid[j][i], grid[k][i], grid[k][i + 1], grid[j][i + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{NAME}_Hair")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["hair"])
    obj = bpy.data.objects.new(f"{NAME}_Hair", me)
    col.objects.link(obj)
    sol = obj.modifiers.new("Thickness", 'SOLIDIFY')
    sol.thickness = 0.008
    sol.offset = -1
    sub = obj.modifiers.new("Smooth", 'SUBSURF')
    sub.levels = 0
    sub.render_levels = 1
    return obj


def hair_material():
    mat = bpy.data.materials.new("Hair")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.45
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (420, 420, 10)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.58
    ramp.color_ramp.elements[0].color = (*HAIR, 1)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (*HAIR_GREY, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    mat.diffuse_color = (*HAIR, 1)
    return mat


# ---------------------------------------------------------------------------
# Лицевые shape keys (одно поле смещений на все меши лица)
# ---------------------------------------------------------------------------
def _gauss(p, c, s):
    return math.exp(-((p - c).length / s) ** 2)


def face_displacement(key, p, head):
    mz = head.mouth.z
    ex, ez = abs(head.eyes["L"].x), head.eyes["L"].z
    d = Vector()
    for sx in (-1, 1):
        corner = Vector((sx * 0.022, p.y, mz))
        cheek = Vector((sx * 0.042, p.y, mz + 0.020))
        brow = Vector((sx * ex, p.y, ez + 0.024))
        if key == "smile":
            d += Vector((sx * 0.0030, 0.0022, 0.0048)) * _gauss(p, corner, 0.012)
            d += Vector((0, -0.0015, 0.0030)) * _gauss(p, cheek, 0.016)
        elif key == "frown":
            d += Vector((sx * 0.0008, 0.0008, -0.0040)) * _gauss(p, corner, 0.012)
        elif key == "mouth_O":
            d += Vector((-sx * 0.0070, -0.0035, 0.0)) * _gauss(p, corner, 0.013)
        elif key == "brow_up":
            d += Vector((0, 0, 0.0050)) * _gauss(p, brow, 0.02)
        elif key == "cheek_puff":
            d += Vector((sx * 0.0045, -0.0030, 0)) * _gauss(p, cheek, 0.02)
    return d


FACE_KEYS = ("smile", "frown", "mouth_O", "brow_up", "cheek_puff")


def add_face_shapekeys(obj, head):
    mw = obj.matrix_world
    inv = mw.inverted().to_3x3()
    obj.shape_key_add(name="Basis", from_mix=False)
    for key in FACE_KEYS:
        sk = obj.shape_key_add(name=key, from_mix=False)
        for i, v in enumerate(obj.data.vertices):
            wp = mw @ v.co
            sk.data[i].co = v.co + inv @ face_displacement(key, wp, head)


# ---------------------------------------------------------------------------
# Веса
# ---------------------------------------------------------------------------
def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (p - (a + ab * t)).length


def auto_weights(obj, arm):
    """Веса по расстоянию до костей (детерминированно, без bone heat)."""
    segs = [(b.name, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
            for b in arm.data.bones if b.use_deform and not b.name.startswith("ctrl_")]
    groups = {n: obj.vertex_groups.new(name=n) for n, _, _ in segs}
    mw = obj.matrix_world
    for v in obj.data.vertices:
        p = mw @ v.co
        ds = sorted(((max(_seg_dist(p, a, b), 1e-4), n) for n, a, b in segs))[:3]
        d0 = ds[0][0]
        ws = [(n, (d0 / d) ** 8) for d, n in ds]
        tot = sum(w for _, w in ws)
        for n, w in ws:
            if w / tot > 0.02:
                groups[n].add([v.index], w / tot, 'REPLACE')


def copy_weights(src, dst, k=4):
    """Перенос весов тело → одежда (по ближайшим вершинам)."""
    kd = kdtree.KDTree(len(src.data.vertices))
    for v in src.data.vertices:
        kd.insert(src.matrix_world @ v.co, v.index)
    kd.balance()
    names = [g.name for g in src.vertex_groups]
    gi = {g.index: g.name for g in src.vertex_groups}
    groups = {n: dst.vertex_groups.new(name=n) for n in names}
    for v in dst.data.vertices:
        acc = {}
        found = kd.find_n(dst.matrix_world @ v.co, k)
        wsum = 0.0
        for _co, idx, dist in found:
            w_pt = 1.0 / max(dist, 1e-4) ** 2
            wsum += w_pt
            for ge in src.data.vertices[idx].groups:
                acc[gi[ge.group]] = acc.get(gi[ge.group], 0.0) + ge.weight * w_pt
        for n, w in acc.items():
            if w / wsum > 0.01:
                groups[n].add([v.index], w / wsum, 'REPLACE')


def add_armature_mod(obj, arm):
    obj.parent = arm
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    # armature — первым в стеке (до subsurf/solidify)
    while obj.modifiers.find(mod.name) > 0:
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_move_up(modifier=mod.name)
    return mod


def head_weights(obj, head, arm, jaw_region=True):
    g_head = obj.vertex_groups.new(name="spine.006")
    g_jaw = obj.vertex_groups.new(name="ctrl_jaw")
    mz = head.mouth.z
    for v in obj.data.vertices:
        p = obj.matrix_world @ v.co
        w = 0.0
        if jaw_region:
            front = smoothstep((-(p.y - head.c.y) - 0.015) / 0.04)
            below = smoothstep((mz - p.z + 0.0012) / 0.0035)
            side = smoothstep((0.062 - abs(p.x)) / 0.03)
            w = front * below * side
        if w < 0.999:
            g_head.add([v.index], 1 - w, 'REPLACE')
        if w > 0.001:
            g_jaw.add([v.index], w, 'REPLACE')


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------
def build_materials():
    m = {
        "skin": studio.material("Skin", SKIN, roughness=0.5, sss=0.15, spec=0.4),
        "lips": studio.material("Lips", LIPS, roughness=0.35, sss=0.1),
        "mouth": studio.material("Mouth_Inside", (0.06, 0.008, 0.01), roughness=0.7),
        "tongue": studio.material("Tongue", (0.70, 0.30, 0.32), roughness=0.4, sss=0.2),
        "teeth": studio.material("Teeth", (0.92, 0.90, 0.84), roughness=0.25),
        "lash": studio.material("Lash_Line", (0.06, 0.04, 0.035), roughness=0.6),
        "brow": studio.material("Brows", (0.06, 0.04, 0.03), roughness=0.8),
        "cardigan": studio.material("Cardigan_Knit", CARDIGAN, roughness=0.9, sss=0.05),
        "pants": studio.material("Pants", PANTS, roughness=0.8),
        "shoes": studio.material("Shoes", SHOES, roughness=0.55),
        "button": studio.material("Buttons", BUTTON, roughness=0.3),
        "eye": eye_material(),
        "hair": hair_material(),
    }
    return m


def build(collection_name=NAME, coords_file=COORDS_FILE, clear=True, location=(0, 0, 0)):
    """Построить персонажа. Возвращает объект арматуры (двигать/анимировать через неё)."""
    if clear:
        studio.clear_scene()
    bones, lm = load_coords(coords_file)
    col = studio.collection(collection_name)
    mats = build_materials()
    arm = build_armature(bones, col)

    # --- тело и одежда
    nodes, edges = skeleton_nodes(bones)
    body = skin_mesh(f"{NAME}_Body", nodes, edges, "pelvis", col, mats["skin"])

    torso = ["pelvis", "waist", "belly", "chest", "chest_top", "neck0"]
    arms = [f"{k}.{s}" for s in "LR" for k in ("shoulder", "uarm", "elbow", "farm", "wrist")]
    cg_n, cg_e = sub_graph(nodes, edges, torso + arms,
                           lambda k: 0.016 if k in torso else (0.015 if "wrist" not in k else 0.016))
    cg_n["neck0"] = (cg_n["neck0"][0] + Vector((0, 0, -0.012)), 0.072, 0.068)
    p, rx, ry = cg_n["pelvis"]
    cg_n["pelvis"] = (p + Vector((0, 0, -0.07)), rx + 0.012, ry + 0.01)
    cardigan = skin_mesh(f"{NAME}_Cardigan", cg_n, cg_e, "pelvis", col, mats["cardigan"], subdiv=2)

    legs = [f"{k}.{s}" for s in "LR" for k in ("hip", "thigh", "knee", "calf", "ankle")]
    pn, pe = sub_graph(nodes, edges, ["pelvis", "waist"] + legs,
                       lambda k: 0.020 if "ankle" in k else 0.013)
    for s in "LR":
        p, rx, ry = pn[f"ankle.{s}"]
        pn[f"ankle.{s}"] = (p + Vector((0, 0, 0.03)), rx + 0.01, ry + 0.01)
    pants = skin_mesh(f"{NAME}_Pants", pn, pe, "pelvis", col, mats["pants"], subdiv=2)

    sn, se = {}, []
    for s in "LR":
        a = nodes[f"ankle.{s}"][0]
        b = nodes[f"ball.{s}"][0]
        t = nodes[f"toe.{s}"][0]
        sn[f"a.{s}"] = (Vector((a.x, a.y, 0.058)), 0.042, 0.044)
        sn[f"h.{s}"] = (Vector((a.x, a.y + 0.028, 0.034)), 0.036, 0.034)
        sn[f"b.{s}"] = (Vector((b.x, b.y, 0.030)), 0.050, 0.030)
        sn[f"t.{s}"] = (Vector((t.x, t.y - 0.006, 0.026)), 0.040, 0.026)
        se += [(f"a.{s}", f"h.{s}"), (f"a.{s}", f"b.{s}"), (f"b.{s}", f"t.{s}")]
    shoes = skin_mesh(f"{NAME}_Shoes", sn, se, ("a.L", "a.R"), col, mats["shoes"], subdiv=2)
    for v in shoes.data.vertices:
        if v.co.z < 0:
            v.co.z = 0.0

    # --- голова
    head = Head(bones, lm)
    head_obj = build_head(head, col, mats)
    lips = build_lips(head, col, mats)
    brows = build_brows(head, col, mats)
    hair = build_hair(head, col, mats)
    y_m, _ = head.surface_y(0, head.mouth.z)
    mouth_bag = ellipsoid("Mouth_Inside", (0, y_m + 0.043, head.mouth.z - 0.001), (0.019, 0.023, 0.0105),
                          mats["mouth"], col)
    tongue = ellipsoid("Tongue", (0, y_m + 0.034, head.mouth.z - 0.011), (0.014, 0.018, 0.005),
                       mats["tongue"], col)
    teeth_up = build_teeth(head, col, mats, upper=True)
    teeth_lo = build_teeth(head, col, mats, upper=False)
    ears = []
    for sx in (-1, 1):
        ex = head.raw(math.pi / 2, sx * math.pi / 2).x
        e = ellipsoid(f"Ear.{'L' if sx > 0 else 'R'}", (ex - sx * 0.002, head.c.y + 0.008, head.eyes["L"].z - 0.012),
                      (0.009, 0.017, 0.026), mats["skin"], col, 16, 12)
        e.rotation_euler = (0, 0, sx * math.radians(18))
        ears.append(e)

    # глаза и веки
    eyes, lids = [], []
    for s in "LR":
        c = bones[f"ctrl_eye.{s}"][0]
        eye = ellipsoid(f"Eye.{s}", c, (EYE_R,) * 3, mats["eye"], col, 32, 20)
        eyes.append((eye, s))
        top = lid_shell(f"Lid_Top.{s}", c, EYE_R + 0.0014, 0, 60, mats, col)
        bot = lid_shell(f"Lid_Bot.{s}", c, EYE_R + 0.0012, 124, 180, mats, col)
        lids += [(top, f"ctrl_lid_top.{s}"), (bot, f"ctrl_lid_bot.{s}")]

    # пуговицы кардигана — лучом по фасаду
    bpy.context.view_layer.update()
    buttons = []
    z0, z1 = bones["spine"][0].z - 0.04, bones["spine.002"][1].z + 0.02
    for i in range(5):
        z = lerp(z0, z1, i / 4)
        ok, loc, nrm, _ = cardigan.ray_cast(Vector((0, -1, z)), Vector((0, 1, 0)))
        if not ok:
            continue
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.0075, radius2=0.0068, depth=0.004)
        me = bpy.data.meshes.new(f"Button.{i}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats["button"])
        b = bpy.data.objects.new(f"Button.{i}", me)
        col.objects.link(b)
        b.location = loc + nrm * 0.001
        b.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
        buttons.append(b)

    # --- веса и привязка
    auto_weights(body, arm)
    for cloth in (cardigan, pants, shoes):
        copy_weights(body, cloth)
    # тело под одеждой скрываем маской (для другой одежды — выключить модификатор)
    g = body.vertex_groups.new(name="hidden_under_clothes")
    hand_x = abs(bones["hand.L"][0].x) - 0.012
    neck_z = nodes["neck0"][0].z - 0.005
    g.add([v.index for v in body.data.vertices
           if v.co.z < neck_z and abs(v.co.x) < hand_x], 1.0, 'REPLACE')
    mask = body.modifiers.new("HideUnderClothes", 'MASK')
    mask.vertex_group = "hidden_under_clothes"
    mask.invert_vertex_group = True

    for obj in (body, cardigan, pants, shoes):
        add_armature_mod(obj, arm)

    # голова/губы: челюсть через вершинные группы
    head_weights(head_obj, head, arm)
    for obj in (head_obj, lips):
        add_face_shapekeys(obj, head)
        add_armature_mod(obj, arm)
    add_face_shapekeys(brows, head)
    lip_sub = lips.modifiers.new("Smooth", 'SUBSURF')
    lip_sub.levels, lip_sub.render_levels = 1, 1
    hs = head_obj.modifiers.new("Smooth", 'SUBSURF')
    hs.levels, hs.render_levels = 1, 1

    for obj in (brows, hair, mouth_bag, teeth_up, *ears):
        studio.parent_to_bone(obj, arm, "spine.006")
    studio.parent_to_bone(teeth_lo, arm, "ctrl_teeth_lo")
    studio.parent_to_bone(tongue, arm, "ctrl_tongue")
    for eye, s in eyes:
        studio.parent_to_bone(eye, arm, f"ctrl_eye.{s}")
    for lid, bone in lids:
        studio.parent_to_bone(lid, arm, bone)
    for b in buttons:
        z = b.location.z
        bone = "spine" if z < bones["spine"][1].z else ("spine.001" if z < bones["spine.001"][1].z else "spine.002")
        studio.parent_to_bone(b, arm, bone)

    # ориентиры из файла
    lm_col = studio.collection(f"{NAME}_Landmarks", col)
    for name, p in lm.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.02
        e.location = p
        lm_col.objects.link(e)
        e.parent = arm
    lm_col.hide_render = True

    arm.location = location
    arm["character"] = NAME
    return arm


# ---------------------------------------------------------------------------
# Удобные позы / эмоции
# ---------------------------------------------------------------------------
def face_key(arm, key, value, frame=None):
    """Выставить shape key лица (smile, frown, mouth_O, brow_up, cheek_puff) на всех мешах лица."""
    for obj in arm.children_recursive:
        sk = obj.data.shape_keys if obj.type == 'MESH' and obj.data.shape_keys else None
        if sk and key in sk.key_blocks:
            sk.key_blocks[key].value = value
            if frame is not None:
                sk.key_blocks[key].keyframe_insert("value", frame=frame)


def pose(arm, bone, rot_deg=None, loc=None, frame=None):
    pb = arm.pose.bones[bone]
    if rot_deg is not None:
        pb.rotation_euler = [math.radians(a) for a in rot_deg]
        if frame is not None:
            pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = loc
        if frame is not None:
            pb.keyframe_insert("location", frame=frame)


def blink(arm, amount=1.0, frame=None):
    for s in "LR":
        pose(arm, f"ctrl_lid_top.{s}", (62 * amount, 0, 0), frame=frame)
        pose(arm, f"ctrl_lid_bot.{s}", (-12 * amount, 0, 0), frame=frame)


def jaw_open(arm, amount=1.0, frame=None):
    pose(arm, "ctrl_jaw", (14 * amount, 0, 0), frame=frame)


def main():
    arm = build()
    out = studio.arg("--out")
    if out:
        out = os.path.abspath(out)
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, "woman50.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
        print("saved", path)
    return arm


if __name__ == "__main__":
    main()
