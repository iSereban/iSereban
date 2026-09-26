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
SKIN = (0.46, 0.25, 0.155)          # цвета — линейные (как в Blender), не sRGB
BLUSH = (0.50, 0.14, 0.10)
LIPS = (0.36, 0.10, 0.09)
HAIR = (0.022, 0.010, 0.0045)       # тёмно-каштановые
HAIR_GREY = (0.15, 0.145, 0.14)     # седая прядь
IRIS = (0.08, 0.028, 0.006)
CARDIGAN = (0.30, 0.10, 0.11)      # пыльно-розовый
BLOUSE = (0.60, 0.50, 0.35)        # кремовая
PANTS = (0.36, 0.27, 0.18)         # бежевые
SOCKS = (0.58, 0.52, 0.42)         # вязаные, молочные
BUTTON = (0.10, 0.05, 0.025)       # коричневые пуговицы
PART_PH = 0.35                     # пробор (угол от лица, + — её левая сторона)

EYE_R = 0.0185

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
    node("pelvis", sp + Vector((0, -0.005, 0.0)), 0.166, 0.120)
    node("waist", B["spine"][1], 0.142, 0.100)
    node("belly", B["spine.001"][1], 0.140, 0.104)
    node("chest", B["spine.002"][1] + Vector((0, -0.016, 0)), 0.152, 0.114)
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
        node(f"hip.{s}", th0 + Vector((0, 0, -0.035)), 0.096, 0.100)
        node(f"thigh.{s}", lerp(th0, th1, 0.45), 0.078, 0.080)
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
        node(f"uarm.{s}", lerp(ua0, ua1, 0.5), 0.047, 0.047)
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
        self.ax = 0.082
        self.ay = 0.086

    def raw(self, th, ph):
        x = self.ax * math.sin(th) * math.sin(ph)
        y = -self.ay * math.sin(th) * math.cos(ph)
        z = self.az * math.cos(th)
        fw = max(0.0, math.cos(ph)) ** 2           # «передняя» часть
        t = max(0.0, -z / self.az)
        x *= 1 - 0.14 * t ** 2.2                    # сужение к челюсти
        if y > 0:
            y *= 1 - 0.45 * t ** 1.3                # затылок → шея
            if z > -0.02:
                y *= 1.06
        zw = self.c.z + z

        def g(cx, cz, sx, sz):
            return math.exp(-((x - cx) / sx) ** 2 - ((zw - cz) / sz) ** 2)

        mz = self.mouth.z
        y -= 0.026 * fw * g(0, mz, 0.042, 0.036)                          # «мордочка» у рта
        y -= 0.009 * fw * g(0, mz - 0.030, 0.030, 0.016)                  # подбородок
        y -= 0.024 * fw * g(0, mz + 0.028, 0.013, 0.012)                  # нос (кончик)
        for nx in (-0.011, 0.011):
            y -= 0.008 * fw * g(nx, mz + 0.024, 0.008, 0.007)              # крылья носа
        y -= 0.006 * fw * g(0, mz + 0.055, 0.008, 0.013)                  # спинка носа
        for sx in (-1, 1):
            ex, ez = sx * abs(self.eyes["L"].x), self.eyes["L"].z
            y += 0.007 * fw * g(ex, ez, 0.019, 0.015)                     # глазницы
            y -= 0.004 * fw * g(ex, ez + 0.024, 0.02, 0.008)              # надбровья
            y -= 0.012 * fw * g(sx * 0.047, mz + 0.020, 0.026, 0.026)     # щёки-«яблочки»
            x += sx * 0.009 * fw * g(sx * 0.055, mz + 0.012, 0.026, 0.032)
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


def mouth_params(head, half_w=0.025, half_h=0.0020):
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
    me.materials.append(mats["skin_face"])
    # румянец: вершинный атрибут blush (щёки, кончик носа)
    attr = me.attributes.new("blush", 'FLOAT', 'POINT')
    mz = head.mouth.z
    for v in me.vertices:
        p = v.co
        if p.y > head.c.y:
            attr.data[v.index].value = 0.0
            continue
        w = 0.0
        for sx in (-1, 1):
            w += math.exp(-((p.x - sx * 0.050) / 0.022) ** 2 - ((p.z - (mz + 0.024)) / 0.020) ** 2)
        w += 0.35 * math.exp(-(p.x / 0.012) ** 2 - ((p.z - (mz + 0.028)) / 0.010) ** 2)
        attr.data[v.index].value = min(w, 1.0)
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
        rt = 0.0026 + ((0.0045 if upper else 0.0062) - 0.0026) * abs(sn) ** 0.7
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
    z = head.mouth.z + (0.0026 if upper else -0.0040)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=6, use_grid_fill=True)
    for v in bm.verts:
        x, y, zz = v.co
        v.co = Vector((x * 0.036, y * 0.009, zz * 0.0075))
        v.co.y += 14.0 * v.co.x ** 2          # дуга зубного ряда
    me = bpy.data.meshes.new("Teeth_Upper" if upper else "Teeth_Lower")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(me.name, me)
    col.objects.link(obj)
    obj.location = (0, y_front + 0.0080, z)
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
    cr.elements[0].position = 0.70
    cr.elements[0].color = (0.90, 0.88, 0.86, 1)
    cr.elements[1].position = 0.715
    cr.elements[1].color = (0.03, 0.012, 0.004, 1)
    e = cr.elements.new(0.74)
    e.color = (*IRIS, 1)
    e = cr.elements.new(0.90)
    e.color = (IRIS[0] * 1.9, IRIS[1] * 1.8, IRIS[2] * 1.5, 1)
    e = cr.elements.new(0.91)
    e.color = (0.01, 0.01, 0.01, 1)
    nt.links.new(tc.outputs["Object"], norm.inputs[0])
    nt.links.new(norm.outputs["Vector"], dot.inputs[0])
    nt.links.new(dot.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    mat.diffuse_color = (0.9, 0.9, 0.9, 1)
    return mat


def lid_shell(name, center, r, polar_from, polar_to, mats, col, lashes=False):
    """Веко: часть сферы; polar — угол от +Z (0 — верх, 180 — низ). lashes — ресницы по краю."""
    bm = bmesh.new()
    nu, nv = 40, 10
    rows = []
    for i in range(nv + 1):
        pa = math.radians(lerp(polar_from, polar_to, i / nv))
        rows.append([bm.verts.new(Vector((r * math.sin(pa) * math.sin(2 * math.pi * j / nu),
                                          -r * math.sin(pa) * math.cos(2 * math.pi * j / nu),
                                          r * math.cos(pa)))) for j in range(nu)])
    for i in range(nv):
        for j in range(nu):
            k = (j + 1) % nu
            f = bm.faces.new((rows[i][j], rows[i][k], rows[i + 1][k], rows[i + 1][j]))
            lash = (i >= nv - 2) if polar_from < 90 else (i == 0)
            f.material_index = 1 if lash else 0
    if lashes:
        # ресницы: полоска, отогнутая наружу-вверх, только спереди (±80°)
        edge = rows[-1]
        pa = math.radians(polar_to)
        for j in range(nu):
            k = (j + 1) % nu
            a0 = 2 * math.pi * j / nu
            a1 = 2 * math.pi * k / nu
            if max(abs(math.remainder(a0, 2 * math.pi)), abs(math.remainder(a1, 2 * math.pi))) > math.radians(80):
                continue
            outs = []
            for a, v in ((a0, edge[j]), (a1, edge[k])):
                side = abs(math.sin(a))
                L = 0.0045 * (1 - 0.5 * side) + 0.0015 * (math.sin(a) > 0.3)   # длиннее к внешнему углу
                d = Vector((math.sin(pa) * math.sin(a), -math.sin(pa) * math.cos(a), math.cos(pa)))
                up = Vector((0, 0, 1))
                outs.append(bm.verts.new(v.co + (d * 0.6 + up * 0.8).normalized() * L))
            f = bm.faces.new((edge[j], edge[k], outs[1], outs[0]))
            f.material_index = 1
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
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
            z = ez + 0.026 + 0.008 * math.sin(math.pi * (u * 0.8 + 0.12)) - 0.004 * u
            y, (th, ph) = head.surface_y(x, z)
            n = head.normal(th, ph)
            w = 0.0036 * (1 - 0.55 * u) + 0.0010
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


def hairline_z(head, ph):
    """Нижняя граница волосяного покрова (мировая Z) по углу φ: лоб → виски → затылок."""
    a = abs(ph)
    ez = head.eyes["L"].z
    front = ez + 0.062
    side = ez - 0.010
    back = head.mouth.z - 0.020
    if a < 1.35:
        return lerp(front, side, smoothstep((a - 0.55) / 0.8))
    return lerp(side, back, smoothstep((a - 1.6) / 1.2))


def build_hair_cap(head, col, mats):
    """Плотная основа причёски у кожи головы (под прядями)."""
    nph, nt = 96, 26
    bm = bmesh.new()
    grid = []
    for j in range(nph):
        ph = -math.pi + 2 * math.pi * j / nph
        th_lim = head.theta_at_z(hairline_z(head, ph))
        col_v = []
        for i in range(nt + 1):
            th = th_lim * (i / nt) ** 0.9
            col_v.append(bm.verts.new(head.raw(th, ph) + head.normal(th, ph) * (0.004 + 0.008 * math.cos(th) ** 2)))
        grid.append(col_v)
    for j in range(nph):
        k = (j + 1) % nph
        for i in range(nt):
            bm.faces.new((grid[j][i], grid[k][i], grid[k][i + 1], grid[j][i + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{NAME}_HairCap")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["hair"])
    obj = bpy.data.objects.new(f"{NAME}_HairCap", me)
    col.objects.link(obj)
    return obj


def _head_radius(head, z, ph):
    """Расстояние от оси головы до поверхности (в плоскости XY) на высоте z."""
    zc = max(min(z, head.c.z + head.az * 0.999), head.c.z - head.az * 0.8)
    p = head.raw(head.theta_at_z(zc), ph)
    return math.hypot(p.x - head.c.x, p.y - head.c.y)


def build_hair(head, col, mats, seed=5):
    """Волнистые пряди до плеч от пробора, с седой прядью спереди (кривые с толщиной)."""
    import random
    rng = random.Random(seed)
    z_shoulder = head.mouth.z - 0.135
    splines = {"hair": [], "grey": []}
    rows = ((0.18, 14), (0.42, 24), (0.68, 32), (0.95, 36), (1.20, 40), (1.45, 36))
    for th_r, n in rows:
        for k in range(n):
            ph0 = -math.pi + 2 * math.pi * (k + rng.random()) / n
            if th_r > head.theta_at_z(hairline_z(head, ph0)) - 0.04:
                continue
            p0 = head.raw(th_r, ph0)
            side = 1 if math.remainder(ph0 - PART_PH, 2 * math.pi) > 0 else -1
            a0 = abs(ph0)
            if a0 < 1.3:   # передние пряди уходят от пробора на бок, открывая лицо
                ph_end = side * max(a0 if (ph0 > 0) == (side > 0) else 0, 1.2) + side * rng.uniform(0.05, 0.4)
            else:
                ph_end = ph0 + side * rng.uniform(0.05, 0.25)
            z_end = z_shoulder + rng.uniform(-0.02, 0.05) + (0.03 if a0 < 1.6 else 0.0)
            seed1, seed2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
            curl = rng.choice((-1, 1)) * rng.uniform(0.008, 0.02)
            pts, core_prev = [], 0.0
            lift = 0.012 + 0.006 * rng.random()
            N = 26
            for i in range(N + 1):
                t = i / N
                ph = ph0 + (ph_end - ph0) * smoothstep(t / 0.3)
                z = p0.z + (z_end - p0.z) * t
                base = _head_radius(head, z, ph) if z > head.c.z - head.az * 0.75 else 0.07
                bob = 0.050 * smoothstep((t - 0.30) / 0.60) * (1.0 if abs(ph) > 1.0 else 0.6)
                core = max(base + lift, core_prev - 0.003)
                core_prev = core
                r = core + bob
                amp = 0.020 * smoothstep((t - 0.22) / 0.30)
                r += amp * math.sin(2 * math.pi * z / 0.15 + seed1)
                ph_w = ph + amp * 1.4 * math.cos(2 * math.pi * z / 0.16 + seed2)
                r += curl * smoothstep((t - 0.82) / 0.18)
                if i == 0:
                    r = math.hypot(p0.x - head.c.x, p0.y - head.c.y) + 0.004
                rad = (0.0125 + 0.006 * math.sin(math.pi * min(t * 1.4, 1))) * (1 - 0.75 * t ** 3)
                pts.append((Vector((head.c.x + r * math.sin(ph_w), head.c.y - r * math.cos(ph_w), z)), rad))
            grey = (-1.05 < math.remainder(ph0 - PART_PH, 2 * math.pi) < -0.30 and th_r < 0.8) or rng.random() < 0.06
            splines["grey" if grey else "hair"].append(pts)

    objs = []
    for key, lst in splines.items():
        cu = bpy.data.curves.new(f"{NAME}_Hair_{key}", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 1.0
        cu.bevel_resolution = 2
        cu.use_fill_caps = True
        for pts in lst:
            sp = cu.splines.new('POLY')
            sp.points.add(len(pts) - 1)
            for i, (p, rad) in enumerate(pts):
                sp.points[i].co = (p.x, p.y, p.z, 1.0)
                sp.points[i].radius = rad
            sp.use_smooth = True
        cu.materials.append(mats["hair"] if key == "hair" else mats["hair_grey"])
        obj = bpy.data.objects.new(f"{NAME}_Hair_{'Locks' if key == 'hair' else 'Grey'}", cu)
        col.objects.link(obj)
        objs.append(obj)
    return objs


def hair_material(name="Hair", color=HAIR, light=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.55
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 0.05
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (220, 220, 25)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    light = light or tuple(min(c * 2.0, 1) for c in color)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*color, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*light, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    mat.diffuse_color = (*color, 1)
    return mat


# ---------------------------------------------------------------------------
# Одежда: вспомогательные функции
# ---------------------------------------------------------------------------
def delete_faces(obj, pred):
    """Удалить грани, для которых pred(center, normal) == True."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    kill = [f for f in bm.faces if pred(f.calc_center_median(), f.normal)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(obj.data)
    bm.free()


def boundary_loops(obj):
    """Замкнутые контуры открытых краёв меша (списки координат)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = [e for e in bm.edges if e.is_boundary]
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a.index, []).append(b.index)
        adj.setdefault(b.index, []).append(a.index)
    co = {v.index: obj.matrix_world @ v.co.copy() for v in bm.verts}
    bm.free()
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append([co[i] for i in loop])
    return loops


def smooth_path(pts, iters=4, closed=True):
    pts = [p.copy() for p in pts]
    n = len(pts)
    for _ in range(iters):
        new = []
        for i in range(n):
            if not closed and i in (0, n - 1):
                new.append(pts[i])
                continue
            new.append((pts[i - 1] + pts[i] * 2 + pts[(i + 1) % n]) / 4)
        pts = new
    return pts


def tube_mesh(name, pts, radius, mat, col, closed=True, flat=1.0, segs=10):
    """Трубка вдоль пути (кант, резинка, манжета). flat<1 — сплющенная по нормали к телу."""
    bm = bmesh.new()
    n = len(pts)
    center = sum(pts, Vector()) / n
    rings = []
    for i in range(n):
        p = pts[i]
        t = (pts[(i + 1) % n] - pts[i - 1]) if closed else (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)])
        t.normalize()
        out = p - center
        out -= t * out.dot(t)
        if out.length < 1e-6:
            out = Vector((0, -1, 0))
        out.normalize()
        side = t.cross(out)
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            ring.append(bm.verts.new(p + (out * math.cos(a) * flat + side * math.sin(a)) * radius))
        rings.append(ring)
    last = n if closed else n - 1
    for i in range(last):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            k1 = (k + 1) % segs
            bm.faces.new((r0[k], r0[k1], r1[k1], r1[k]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    return obj


def ellipse_pts(center, rx, ry, n=40):
    return [center + Vector((rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n), 0))
            for i in range(n)]


def knit_material(name, color, rib=(0.0, 1.0), rib_scale=350.0, rib_strength=0.35, fuzz=0.25, roughness=0.9):
    """Вязаная/тканевая фактура: рубчик (полосы) + ворс. Координаты Generated — не «плывут» при анимации."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    if "Sheen Weight" in b.inputs:
        b.inputs["Sheen Weight"].default_value = 0.4
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'X' if rib[0] == 0 else 'Z'
    wave.inputs["Scale"].default_value = rib_scale
    wave.inputs["Distortion"].default_value = 1.5
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 900.0
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = 'MULTIPLY_ADD'
    mix.inputs[1].default_value = rib_strength
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nzm = nt.nodes.new("ShaderNodeMath")
    nzm.operation = 'MULTIPLY'
    nzm.inputs[1].default_value = fuzz
    nt.links.new(tc.outputs["Generated"], wave.inputs["Vector"])
    nt.links.new(tc.outputs["Generated"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], nzm.inputs[0])
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])
    nt.links.new(nzm.outputs["Value"], mix.inputs[2])
    nt.links.new(mix.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    mat.diffuse_color = (*color, 1)
    return mat


def small_button(name, loc, nrm, radius, mat, col):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=radius, radius2=radius * 0.85, depth=radius * 0.5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    b = bpy.data.objects.new(name, me)
    col.objects.link(b)
    b.location = loc + nrm * radius * 0.2
    b.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
    return b


def build_clothes(nodes, edges, bones, col, mats):
    """Блузка, открытый кардиган (резинка по краю, манжеты, пуговицы), брюки с подворотом, носки."""
    torso = ["pelvis", "waist", "belly", "chest", "chest_top", "neck0"]
    arms = [f"{k}.{s}" for s in "LR" for k in ("shoulder", "uarm", "elbow", "farm", "wrist")]
    neck_z = nodes["neck0"][0].z
    parts, extras = {}, []

    # --- блузка (хенли): под кардиганом, V-вырез с планкой
    bn, be = sub_graph(nodes, edges, torso + [f"shoulder.{s}" for s in "LR"], lambda k: 0.011)
    bn["neck0"] = (bn["neck0"][0] + Vector((0, 0, -0.018)), 0.066, 0.062)
    p, rx, ry = bn["pelvis"]
    bn["pelvis"] = (p + Vector((0, 0, -0.030)), rx + 0.012, ry + 0.010)
    blouse = skin_mesh(f"{NAME}_Blouse", bn, be, "pelvis", col, mats["blouse"], subdiv=2)
    hem_b = bn["pelvis"][0].z
    v_top, v_bot = neck_z - 0.02, neck_z - 0.085
    delete_faces(blouse, lambda c, n: (n.z < -0.55 and c.z < hem_b + 0.03)
                 or (n.z > 0.45 and c.z > neck_z - 0.04 and abs(c.x) < 0.08)
                 or (c.y < 0 and v_bot < c.z and abs(c.x) < 0.004 + 0.022 * (c.z - v_bot) / (v_top - v_bot)))
    parts["blouse"] = blouse

    # --- кардиган: свободнее, длиннее, открытая перёдка, шалевый край
    cg_n, cg_e = sub_graph(nodes, edges, torso + arms,
                           lambda k: 0.019 if k in torso else (0.016 if "wrist" not in k else 0.016))
    cg_n["neck0"] = (cg_n["neck0"][0] + Vector((0, 0.01, -0.020)), 0.080, 0.076)
    p, rx, ry = cg_n["pelvis"]
    cg_n["pelvis"] = (p + Vector((0, 0, -0.105)), rx + 0.010, ry + 0.008)
    cardigan = skin_mesh(f"{NAME}_Cardigan", cg_n, cg_e, "pelvis", col, mats["cardigan"], subdiv=2)
    hem = cg_n["pelvis"][0].z
    wr = {s: (cg_n[f"wrist.{s}"][0], (cg_n[f"wrist.{s}"][0] - cg_n[f"elbow.{s}"][0]).normalized()) for s in "LR"}

    def open_front(c, n):
        if n.z < -0.5 and c.z < hem + 0.06:
            return True                                            # низ
        if n.z > 0.4 and c.z > neck_z - 0.05 and abs(c.x) < 0.10:
            return True                                            # горловина
        for s in "LR":
            w0, d = wr[s]
            if (c - w0).length < 0.045 and n.dot(d) > 0.5:
                return True                                        # рукав у запястья
        if c.y < -0.02 and c.z > hem - 0.05:
            half = 0.040 + 0.050 * smoothstep((c.z - 1.02) / 0.30)  # раскрытие шире к шее
            return abs(c.x) < half
        return False

    delete_faces(cardigan, open_front)
    loops = sorted(boundary_loops(cardigan), key=len, reverse=True)
    sol = cardigan.modifiers.new("Thickness", 'SOLIDIFY')
    sol.thickness = 0.006
    sol.offset = 1
    parts["cardigan"] = cardigan
    # резинка по краю полочек/низу/горловине и манжеты
    band = tube_mesh(f"{NAME}_Cardigan_Band", smooth_path(loops[0][::2], 6), 0.017, mats["cardigan_rib"], col,
                     flat=0.45)
    parts["cardigan_band"] = band
    for i, lp in enumerate(loops[1:3]):
        cuff = tube_mesh(f"{NAME}_Cardigan_Cuff.{i}", smooth_path(lp, 3), 0.016, mats["cardigan_rib"], col, flat=0.9)
        parts[f"cuff{i}"] = cuff
    # пуговицы на левой полочке (её левая сторона, x>0)
    band_pts = [p for p in loops[0] if p.x > 0 and p.y < 0]
    for i, z in enumerate((hem + 0.03, hem + 0.12, hem + 0.21)):
        if not band_pts:
            break
        bp = min(band_pts, key=lambda p: abs(p.z - z))
        extras.append(small_button(f"Cardigan_Button.{i}", bp + Vector((0, -0.008, 0)), Vector((0, -1, 0)),
                                   0.009, mats["button"], col))
    # пуговки блузки на планке
    bpy.context.view_layer.update()
    for i in range(3):
        z = v_bot - 0.012 - i * 0.03
        ok, loc, nrm, _ = blouse.ray_cast(Vector((0.0, -1, z)), Vector((0, 1, 0)))
        if ok:
            extras.append(small_button(f"Blouse_Button.{i}", loc, nrm, 0.0045, mats["blouse_button"], col))

    # --- брюки: свободные, подворот
    legs = [f"{k}.{s}" for s in "LR" for k in ("hip", "thigh", "knee", "calf", "ankle")]
    pn, pe = sub_graph(nodes, edges, ["pelvis", "waist"] + legs,
                       lambda k: 0.030 if k[:3] in ("kne", "cal", "ank") else 0.020)
    cuff_z = 0.125
    for s in "LR":
        p, rx, ry = pn[f"ankle.{s}"]
        pn[f"ankle.{s}"] = (Vector((p.x, p.y, cuff_z)), 0.060, 0.064)
    pants = skin_mesh(f"{NAME}_Pants", pn, pe, "pelvis", col, mats["pants"], subdiv=2)
    delete_faces(pants, lambda c, n: n.z < -0.6 and c.z < cuff_z + 0.03)
    parts["pants"] = pants
    for s in "LR":
        p = pn[f"ankle.{s}"][0]
        parts[f"pants_cuff.{s}"] = tube_mesh(f"{NAME}_Pants_Cuff.{s}", ellipse_pts(Vector((p.x, p.y, cuff_z + 0.012)),
                                                                               0.062, 0.066), 0.020,
                                             mats["pants"], col, flat=0.55)

    # --- вязаные носки
    sn, se = {}, []
    for s in "LR":
        a = nodes[f"ankle.{s}"][0]
        b = nodes[f"ball.{s}"][0]
        t = nodes[f"toe.{s}"][0]
        sn[f"top.{s}"] = (Vector((a.x, a.y, 0.170)), 0.050, 0.052)
        sn[f"a.{s}"] = (Vector((a.x, a.y, 0.075)), 0.048, 0.050)
        sn[f"h.{s}"] = (Vector((a.x, a.y + 0.030, 0.036)), 0.044, 0.040)
        sn[f"b.{s}"] = (Vector((b.x, b.y, 0.030)), 0.054, 0.032)
        sn[f"t.{s}"] = (Vector((t.x, t.y - 0.008, 0.028)), 0.044, 0.028)
        se += [(f"top.{s}", f"a.{s}"), (f"a.{s}", f"h.{s}"), (f"a.{s}", f"b.{s}"), (f"b.{s}", f"t.{s}")]
    socks = skin_mesh(f"{NAME}_Socks", sn, se, ("top.L", "top.R"), col, mats["socks"], subdiv=2)
    for v in socks.data.vertices:
        v.co.z = max(v.co.z, 0.0)
    parts["socks"] = socks
    return parts, extras


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
        corner = Vector((sx * 0.026, p.y, mz))
        cheek = Vector((sx * 0.042, p.y, mz + 0.020))
        brow = Vector((sx * ex, p.y, ez + 0.024))
        if key == "smile":
            d += Vector((sx * 0.0040, 0.0030, 0.0070)) * _gauss(p, corner, 0.013)
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
def face_skin_material():
    mat = studio.material("Skin_Face", SKIN, roughness=0.5, sss=0.15, spec=0.4)
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "blush"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.inputs["A"].default_value = (*SKIN, 1)
    mix.inputs["B"].default_value = (*BLUSH, 1)
    fac = nt.nodes.new("ShaderNodeMath")
    fac.operation = 'MULTIPLY'
    fac.inputs[1].default_value = 0.45
    nt.links.new(at.outputs["Fac"], fac.inputs[0])
    nt.links.new(fac.outputs["Value"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    return mat


def build_materials():
    m = {
        "skin_face": face_skin_material(),
        "skin": studio.material("Skin", SKIN, roughness=0.5, sss=0.15, spec=0.4),
        "lips": studio.material("Lips", LIPS, roughness=0.35, sss=0.1),
        "mouth": studio.material("Mouth_Inside", (0.06, 0.008, 0.01), roughness=0.7),
        "tongue": studio.material("Tongue", (0.70, 0.30, 0.32), roughness=0.4, sss=0.2),
        "teeth": studio.material("Teeth", (0.92, 0.90, 0.84), roughness=0.25),
        "lash": studio.material("Lash_Line", (0.06, 0.04, 0.035), roughness=0.6),
        "brow": studio.material("Brows", (0.030, 0.014, 0.007), roughness=0.8),
        "cardigan": knit_material("Cardigan_Knit", CARDIGAN, rib=(0, 1), rib_scale=260, rib_strength=0.5),
        "cardigan_rib": knit_material("Cardigan_Rib", tuple(c * 0.92 for c in CARDIGAN), rib=(1, 0),
                                      rib_scale=900, rib_strength=0.8),
        "blouse": knit_material("Blouse", BLOUSE, rib=(0, 1), rib_scale=500, rib_strength=0.15, fuzz=0.1,
                                roughness=0.7),
        "blouse_button": studio.material("Blouse_Buttons", (0.80, 0.74, 0.62), roughness=0.3),
        "pants": knit_material("Pants_Wool", PANTS, rib=(0, 1), rib_scale=40, rib_strength=0.05, fuzz=0.4),
        "socks": knit_material("Socks_Knit", SOCKS, rib=(1, 0), rib_scale=90, rib_strength=0.9, fuzz=0.4),
        "button": studio.material("Buttons", BUTTON, roughness=0.3),
        "eye": eye_material(),
        "hair": hair_material(),
        "hair_grey": hair_material("Hair_Grey", HAIR_GREY, light=(0.40, 0.39, 0.38)),
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

    clothes, clothes_extras = build_clothes(nodes, edges, bones, col, mats)

    # --- голова
    head = Head(bones, lm)
    head_obj = build_head(head, col, mats)
    lips = build_lips(head, col, mats)
    brows = build_brows(head, col, mats)
    hair_cap = build_hair_cap(head, col, mats)
    hair_locks = build_hair(head, col, mats)
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
        top = lid_shell(f"Lid_Top.{s}", c, EYE_R + 0.0014, 0, 50, mats, col, lashes=True)
        bot = lid_shell(f"Lid_Bot.{s}", c, EYE_R + 0.0012, 128, 180, mats, col)
        lids += [(top, f"ctrl_lid_top.{s}"), (bot, f"ctrl_lid_bot.{s}")]

    # --- веса и привязка
    auto_weights(body, arm)
    for cloth in clothes.values():
        copy_weights(body, cloth)
    # тело под одеждой скрываем маской (для другой одежды — выключить модификатор)
    g = body.vertex_groups.new(name="hidden_under_clothes")
    hand_x = abs(bones["hand.L"][0].x) - 0.012
    neck_z = nodes["neck0"][0].z - 0.095   # V-вырез блузки открывает шею и ключицы
    g.add([v.index for v in body.data.vertices
           if v.co.z < neck_z and abs(v.co.x) < hand_x], 1.0, 'REPLACE')
    mask = body.modifiers.new("HideUnderClothes", 'MASK')
    mask.vertex_group = "hidden_under_clothes"
    mask.invert_vertex_group = True

    for obj in (body, *clothes.values()):
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

    for obj in (brows, hair_cap, *hair_locks, mouth_bag, teeth_up, *ears):
        studio.parent_to_bone(obj, arm, "spine.006")
    studio.parent_to_bone(teeth_lo, arm, "ctrl_teeth_lo")
    studio.parent_to_bone(tongue, arm, "ctrl_tongue")
    for eye, s in eyes:
        studio.parent_to_bone(eye, arm, f"ctrl_eye.{s}")
    for lid, bone in lids:
        studio.parent_to_bone(lid, arm, bone)
    for b in clothes_extras:
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
        pose(arm, f"ctrl_lid_top.{s}", (74 * amount, 0, 0), frame=frame)
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
