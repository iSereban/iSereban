"""
Тест: сгенерированный персонаж (Meshy/Tripo .glb) — ролик 15 с, 854×480.

Сценарий: идёт к камере → приседает → снова идёт → разворачивается → прыгает от радости →
машет в камеру. Снято «как в кино»: 6 планов со склейками (наезд спереди, профиль на
приседе, ноги у земли, кран сверху, общий на развороте, героический нижний ракурс).

Скелет строится автоматически по форме модели (blender/common/autorig.py) — модель может
быть любой: чиби, взрослый, мультяшный.

ЗАПУСК У СЕБЯ (Blender 3.6 / 4.x / 5.x):
  1) Укажи путь к модели в GLB_PATH ниже (или --glb в командной строке).
  2) Scripting → Open → chibi_walk.py → Run Script. Сцена соберётся.
  3) Render → Render Animation (Ctrl+F12). Видео: render/chibi_walk_0001-0375.mp4
     рядом с сохранённым .blend (сохрани файл перед рендером, иначе — рядом с Blender).
  Командная строка:
     blender -b -P chibi_walk.py -- --glb "C:\\Users\\New\\Downloads\\model.glb" --out out --render
  Опции: --height 1.0 (рост, м)  --turn 180 (если модель стоит спиной)  --engine CYCLES|EEVEE
"""

import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Vector

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    _HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "common"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "library"))
import autorig  # noqa: E402
import studio  # noqa: E402

GLB_PATH = r"C:\Users\New\Downloads\Meshy_AI_Chibi_Figure_0926172701_texture.glb"
HEIGHT = 1.0          # рост персонажа, м (чиби ~1 м)
TURN = 0.0            # доп. поворот модели вокруг Z, если она стоит не лицом к −Y
FPS = 25
FRAMES = 375          # 15 с

# фазы (кадры)
WALK1 = (1, 100)
SQUAT = (101, 150)
WALK2 = (151, 250)
TURN_F = (251, 295)
JUMP = (296, 335)
WAVE = (336, 375)


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def window(f, a, b, ease=8):
    """1 внутри [a, b] с плавным входом/выходом ease кадров."""
    return smoothstep((f - a) / ease) * smoothstep((b - f) / ease)


# ---------------------------------------------------------------------------
# Окружение: парк с дорожкой
# ---------------------------------------------------------------------------
def build_set(H):
    col = studio.collection("Set")
    s = 40 * H
    me = bpy.data.meshes.new("Ground")
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    grass = bpy.data.materials.new("Grass")
    grass.use_nodes = True
    nt = grass.node_tree
    b = nt.nodes["Principled BSDF"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0 / H
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.05, 0.12, 0.03, 1)
    ramp.color_ramp.elements[1].color = (0.16, 0.26, 0.06, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 1.0
    grass.diffuse_color = (0.1, 0.2, 0.05, 1)
    me.materials.append(grass)
    col.objects.link(bpy.data.objects.new("Ground", me))

    # дорожка из плитки вдоль Y
    w = 1.6 * H
    me = bpy.data.meshes.new("Path")
    me.from_pydata([(-w / 2, -s, 0.002), (w / 2, -s, 0.002), (w / 2, s, 0.002), (-w / 2, s, 0.002)], [],
                   [(0, 1, 2, 3)])
    tile = bpy.data.materials.new("Path_Tiles")
    tile.use_nodes = True
    nt = tile.node_tree
    b = nt.nodes["Principled BSDF"]
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 2.5 / H
    br.inputs["Color1"].default_value = (0.45, 0.38, 0.30, 1)
    br.inputs["Color2"].default_value = (0.36, 0.30, 0.24, 1)
    br.inputs["Mortar"].default_value = (0.15, 0.13, 0.11, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.8
    tile.diffuse_color = (0.4, 0.34, 0.27, 1)
    me.materials.append(tile)
    col.objects.link(bpy.data.objects.new("Path", me))

    # деревья, кусты, фонари — для глубины кадра
    import random
    rng = random.Random(3)
    leaf = studio.material("Leaves", (0.06, 0.18, 0.04), roughness=0.9)
    leaf2 = studio.material("Leaves_Light", (0.18, 0.30, 0.05), roughness=0.9)
    trunk = studio.material("Trunk", (0.12, 0.07, 0.04), roughness=0.9)
    lamp = studio.material("Lamp_Post", (0.03, 0.03, 0.035), roughness=0.4, metallic=0.8)
    glow = studio.material("Lamp_Glow", (1, 0.85, 0.6), emission=(1, 0.8, 0.5))
    import bmesh
    bm = bmesh.new()
    mats_idx = []

    def add(geom, mi):
        for f in {f for v in geom["verts"] for f in v.link_faces}:
            f.material_index = mi

    # реалистичные деревья из библиотеки (липы, берёзы, ели) — один меш на породу, экземпляры
    import catalog_city
    import parts
    kinds = ["tree_linden_1", "tree_linden_2", "tree_linden_3", "tree_birch_1", "tree_birch_2", "tree_spruce_1"]
    cache = {}
    tcol = studio.collection("Trees")
    for i in range(46):
        side = rng.choice((-1, 1))
        x = side * rng.uniform(3.5, 16) * H
        y = rng.uniform(-18, 18) * H
        k = kinds[i % len(kinds)] if i % 9 else "tree_spruce_1"
        obj = parts.place(catalog_city.get(k), location=(x, y, 0), rot_deg=rng.uniform(0, 360), col=tcol,
                          mesh_cache=cache)
        obj.scale = (rng.uniform(0.85, 1.1),) * 3
    for i in range(40):
        side = rng.choice((-1, 1))
        x = side * rng.uniform(1.1, 3.0) * H
        y = rng.uniform(-15, 15) * H
        g = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rng.uniform(0.25, 0.45) * H)
        for v in g["verts"]:
            v.co.z *= 0.7
            v.co += Vector((x, y, 0.12 * H))
        add(g, 1)
    for y in range(-16, 17, 6):
        for side in (-1, 1):
            x = side * 1.05 * H
            g = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.03 * H, radius2=0.03 * H,
                                      depth=2.6 * H)
            for v in g["verts"]:
                v.co += Vector((x, y * H, 1.3 * H))
            add(g, 3)
            g = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.12 * H)
            for v in g["verts"]:
                v.co += Vector((x, y * H, 2.65 * H))
            add(g, 4)
    me = bpy.data.meshes.new("Props")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    for m in (leaf, leaf2, trunk, lamp, glow):
        me.materials.append(m)
    col.objects.link(bpy.data.objects.new("Props", me))
    del mats_idx

    # небо + солнце
    sc = bpy.context.scene
    world = bpy.data.worlds.new("Sky")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.radians(35)
        sky.sun_rotation = math.radians(140)
    nt.links.new(sky.outputs[0], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs[1].default_value = 0.18
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 2.6
    sun.data.angle = math.radians(2)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    col.objects.link(sun)


# ---------------------------------------------------------------------------
# Анимация
# ---------------------------------------------------------------------------
class Motion:
    """Процедурная анимация: ходьба, присед, разворот, прыжок, взмах рукой."""

    def __init__(self, arm, lm):
        self.arm = arm
        self.lm = lm
        H = lm["H"]
        self.H = H
        self.leg = autorig.bone_length(arm, "thigh.L") + autorig.bone_length(arm, "shin.L")
        self.stride = 1.25 * self.leg              # длина цикла (2 шага)
        self.cycle = 1.0                           # с на цикл
        self.speed = self.stride / self.cycle
        self.arm_style = "rest" if "joints" in lm else "swing"
        self.hip_rest = arm.data.bones["thigh.L"].head_local.z
        self.ankle_z = arm.data.bones["foot.L"].head_local.z
        fb = arm.data.bones["foot.L"]
        v = fb.tail_local - fb.head_local
        self.foot_slope = math.atan2(-v.z, max(math.hypot(v.x, v.y), 1e-6))
        # траектория: заранее интегрируем позицию, курс и фазу шага
        self.track = {}
        pos, psi, phase = Vector((0, 3.0 * H, 0)), 0.0, 0.0
        for f in range(1, FRAMES + 1):
            walk = max(window(f, *WALK1), window(f, *WALK2))
            turn = window(f, *TURN_F, ease=6)
            if TURN_F[0] <= f <= TURN_F[1]:
                psi = math.pi * smoothstep((f - TURN_F[0]) / (TURN_F[1] - TURN_F[0]))
            fwd = Vector((-math.sin(psi), -math.cos(psi), 0))
            pos = pos + fwd * self.speed * walk / FPS
            phase += 2 * math.pi * (walk + 0.55 * turn) / (self.cycle * FPS)
            self.track[f] = (pos.copy(), psi, phase, walk, turn)

    def frame(self, f):
        arm, H = self.arm, self.H
        pos, psi, phase, walk, turn = self.track[f]
        Z = Vector((0, 0, 1))
        F = Vector((-math.sin(psi), -math.cos(psi), 0))      # вперёд
        Lv = Vector((math.cos(psi), -math.sin(psi), 0))       # влево персонажа (+X при взгляде в −Y)
        step = max(walk, 0.5 * turn)

        squat = math.sin(math.pi * max(0.0, min(1.0, (f - SQUAT[0] - 6) / 40))) if SQUAT[0] <= f <= SQUAT[1] else 0.0
        squat = smoothstep(squat * 1.15)
        # прыжок: присед 296–305, полёт 306–322, приземление 322–335
        jz, jcrouch, jarms = 0.0, 0.0, 0.0
        if JUMP[0] <= f <= JUMP[1]:
            if f <= 305:
                jcrouch = smoothstep((f - JUMP[0]) / 9) * 0.55
            elif f <= 322:
                t = (f - 306) / 16
                jz = 4 * 0.30 * H * t * (1 - t)
                jcrouch = 0.0
            else:
                jcrouch = 0.45 * math.sin(math.pi * min(1, (f - 322) / 13))
            jarms = smoothstep((f - 300) / 6) * (1 - smoothstep((f - 328) / 7))
        wave = window(f, WAVE[0], WAVE[1] + 20, ease=8)

        # --- ноги
        legs = {}
        for s, off in (("L", 0.0), ("R", math.pi)):
            ph = phase + off
            th = math.radians(24) * math.sin(ph) * step
            knee = math.radians(6 + 48 * max(0.0, math.cos(ph)) ** 1.5 * step)
            crouch = max(squat, jcrouch)
            th += math.radians(80) * crouch
            knee += math.radians(115) * crouch
            legs[s] = (th, knee)
        lt = autorig.bone_length(arm, "thigh.L")
        ls = autorig.bone_length(arm, "shin.L")
        drops = [lt * math.cos(th) + ls * math.cos(th - kn) for th, kn in legs.values()]
        hip_drop = (lt + ls) - max(drops)                    # насколько опустить таз
        bob = 0.012 * H * abs(math.cos(phase)) * step

        arm.location = pos + Vector((0, 0, jz - hip_drop + bob))
        arm.rotation_euler = (0, 0, psi)
        bpy.context.view_layer.update()
        autorig.reset_pose(arm)

        lean = math.radians(6 * step + 25 * max(squat, jcrouch))
        autorig.aim(arm, "hips", Z * math.cos(lean * 0.5) + F * math.sin(lean * 0.5))
        autorig.aim(arm, "spine", Z * math.cos(lean) + F * math.sin(lean))
        autorig.aim(arm, "chest", Z * math.cos(lean * 0.6) + F * math.sin(lean * 0.6))
        nod = math.radians(3 * math.sin(phase * 2) * step - 8 * jarms)
        look = math.radians(12 * wave)
        autorig.aim(arm, "head", Z * math.cos(nod) - F * math.sin(nod) * -1 + Lv * math.sin(look) * 0.3)

        for s, sg in (("L", 1), ("R", -1)):
            th, kn = legs[s]
            autorig.aim(arm, f"thigh.{s}", -Z * math.cos(th) + F * math.sin(th) + Lv * sg * 0.03)
            ts = th - kn
            autorig.aim(arm, f"shin.{s}", -Z * math.cos(ts) + F * math.sin(ts))
            toe_lift = math.radians(15) * max(0.0, math.cos(phase + (0 if s == "L" else math.pi))) * step
            fa = self.foot_slope - toe_lift
            autorig.aim(arm, f"foot.{s}", F * math.cos(fa) - Z * math.sin(fa))

        # --- руки
        if self.arm_style == "rest":
            self._arms_from_rest(f, phase, step, squat, jarms, wave, F, Lv, Z)
            return
        for s, sg, off in (("L", 1, math.pi), ("R", -1, 0.0)):
            swing = math.radians(28) * math.sin(phase + off) * step
            out = math.radians(18)
            ua = -Z * math.cos(swing) * math.cos(out) + F * math.sin(swing) + Lv * sg * math.sin(out)
            fa = ua + F * 0.35
            # присед: руки вперёд для баланса
            sq = max(squat, 0.0)
            ua = ua.lerp((F * 0.95 - Z * 0.15 + Lv * sg * 0.15), sq)
            fa = fa.lerp(F, sq)
            # прыжок: руки вверх
            ua = ua.lerp(Z * 0.85 + Lv * sg * 0.5, jarms)
            fa = fa.lerp(Z + Lv * sg * 0.3, jarms)
            # взмах правой рукой в конце
            if s == "R" and wave > 0:
                t = (f - WAVE[0]) / FPS
                ua = ua.lerp(Z * 0.75 + Lv * sg * 0.6 + F * 0.15, wave)
                fa = fa.lerp(Z + Lv * sg * 0.45 * math.sin(2 * math.pi * 2.2 * t) + F * 0.1, wave)
            autorig.aim(arm, f"upper_arm.{s}", ua)
            autorig.aim(arm, f"forearm.{s}", fa)
            autorig.aim(arm, f"hand.{s}", fa)

    def _rest_dir(self, bone):
        b = self.arm.data.bones[bone]
        return (self.arm.matrix_world.to_3x3() @ (b.tail_local - b.head_local)).normalized()

    def _arms_from_rest(self, f, phase, step, squat, jarms, wave, F, Lv, Z):
        """Для моделей с «зафиксированными» руками (в карманах): лёгкие движения от исходной позы.
        Левая рука остаётся в кармане, правая покачивается / поднимается / машет."""
        from mathutils import Matrix as _M
        arm = self.arm
        rot = lambda v, axis, ang: _M.Rotation(ang, 3, axis) @ v   # noqa: E731
        # левая: чуть-чуть покачивается вместе с корпусом
        for b in ("upper_arm.L", "forearm.L"):
            autorig.aim(arm, b, rot(self._rest_dir(b), Lv, math.radians(4) * math.sin(phase) * step))
        # правая
        sw = math.radians(16) * math.sin(phase) * step
        ua = rot(self._rest_dir("upper_arm.R"), Lv, sw)
        fa = rot(self._rest_dir("forearm.R"), Lv, sw * 1.3)
        sq = squat
        ua = ua.lerp(-Z * 0.6 + F * 0.8, sq * 0.6)
        fa = fa.lerp(F, sq * 0.7)
        up = max(jarms, wave)
        if up > 0:
            t = (f - WAVE[0]) / FPS
            ua_up = (-Lv * 0.85 + Z * 0.45 + F * 0.1).normalized()          # в сторону-вверх
            fa_up = (Z - Lv * 0.15 + F * 0.1).normalized()
            if wave > 0:
                fa_up = rot(fa_up, F, math.radians(28) * math.sin(2 * math.pi * 2.0 * t) * wave)
            ua = ua.normalized().lerp(ua_up, up)
            fa = fa.normalized().lerp(fa_up, up)
        autorig.aim(arm, "upper_arm.R", ua)
        autorig.aim(arm, "forearm.R", fa)
        autorig.aim(arm, "hand.R", fa)

    def bake(self):
        arm = self.arm
        for pb in arm.pose.bones:
            pb.rotation_mode = 'QUATERNION'
        prev = {}
        for f in range(1, FRAMES + 1):
            bpy.context.scene.frame_set(f)
            self.frame(f)
            arm.keyframe_insert("location", frame=f)
            arm.keyframe_insert("rotation_euler", frame=f)
            for pb in arm.pose.bones:
                q = pb.rotation_quaternion.copy()
                if pb.name in prev and prev[pb.name].dot(q) < 0:
                    q.negate()
                    pb.rotation_quaternion = q
                prev[pb.name] = q
                pb.keyframe_insert("rotation_quaternion", frame=f)
        bpy.context.scene.frame_set(1)

    def pos(self, f):
        return self.track[max(1, min(FRAMES, f))][0]


# ---------------------------------------------------------------------------
# Камеры
# ---------------------------------------------------------------------------
def build_cameras(arm, motion):
    H = motion.H
    sc = bpy.context.scene
    col = studio.collection("Cameras")
    t_chest = bpy.data.objects.new("T_Chest", None)
    col.objects.link(t_chest)
    t_chest.parent = arm
    t_chest.parent_type = 'BONE'
    t_chest.parent_bone = "chest"
    t_chest.location = (0, 0, 0)
    t_feet = bpy.data.objects.new("T_Feet", None)
    col.objects.link(t_feet)
    t_feet.parent = arm
    t_feet.location = (0, 0, 0.12 * H)
    t_head = bpy.data.objects.new("T_Head", None)
    col.objects.link(t_head)
    t_head.parent = arm
    t_head.parent_type = 'BONE'
    t_head.parent_bone = "head"

    shots = []
    Fw = Vector((0, -1, 0))   # фазы 1–250 персонаж идёт в −Y
    Lw = Vector((1, 0, 0))

    def cam(name, lens, target, keys, lens_keys=None):
        c = studio.camera(name, keys[0][1], (0, 0, 0), lens, col)
        c.constraints.clear()
        studio.track_to(c, target)
        for f, loc in keys:
            c.location = loc
            c.keyframe_insert("location", frame=f)
        for f, ln in (lens_keys or []):
            c.data.lens = ln
            c.data.keyframe_insert("lens", frame=f)
        c.data.dof.use_dof = False
        return c

    # 1. Наезд спереди: камера пятится перед персонажем, приближаясь
    p = motion.pos
    k = [(f, p(f) + Fw * (3.2 - 1.6 * (f - 1) / 99) * H + Lw * 0.7 * H + Vector((0, 0, 0.55 * H)))
         for f in range(1, 101, 10)] + [(100, p(100) + Fw * 1.6 * H + Lw * 0.7 * H + Vector((0, 0, 0.55 * H)))]
    shots.append((1, cam("Shot1_FrontDolly", 40, t_chest, k)))
    # 2. Профиль на приседании
    c = p(125) + Lw * 2.6 * H + Vector((0, 0, 0.5 * H))
    shots.append((101, cam("Shot2_SquatProfile", 45, t_chest, [(101, c), (150, c + Fw * 0.25 * H)])))
    # 3. Ноги у земли, камера едет рядом
    k = [(f, p(f) + Lw * 1.1 * H + Fw * 0.4 * H + Vector((0, 0, 0.10 * H))) for f in range(151, 201, 10)] + \
        [(200, p(200) + Lw * 1.1 * H + Fw * 0.4 * H + Vector((0, 0, 0.10 * H)))]
    shots.append((151, cam("Shot3_FeetTracking", 28, t_feet, k)))
    # 4. Кран: сверху-сзади опускается
    shots.append((201, cam("Shot4_Crane", 32, t_chest,
                           [(201, p(201) - Fw * 3.0 * H + Lw * 2.0 * H + Vector((0, 0, 3.0 * H))),
                            (250, p(250) - Fw * 1.2 * H + Lw * 1.6 * H + Vector((0, 0, 0.9 * H)))])))
    # 5. Общий план на развороте
    c = p(270) + Fw * 2.4 * H - Lw * 2.6 * H + Vector((0, 0, 1.0 * H))
    shots.append((251, cam("Shot5_TurnWide", 30, t_chest, [(251, c), (295, c + Lw * 0.3 * H)])))
    # 6. Героический нижний ракурс спереди (персонаж теперь смотрит в +Y)
    c0 = p(300) - Fw * 2.8 * H + Lw * 0.4 * H + Vector((0, 0, 0.25 * H))
    c1 = p(300) - Fw * 1.7 * H + Lw * 0.2 * H + Vector((0, 0, 0.35 * H))
    shots.append((296, cam("Shot6_HeroLow", 32, t_chest, [(296, c0), (375, c1)], [(296, 30), (375, 40)])))

    sc.timeline_markers.clear()
    for f, c in shots:
        m = sc.timeline_markers.new(c.name, frame=f)
        m.camera = c
    sc.camera = shots[0][1]
    return shots


# ---------------------------------------------------------------------------
def build(glb=None, height=None, turn=None):
    studio.clear_scene()
    glb = glb or studio.arg("--glb", GLB_PATH)
    if not os.path.exists(glb):
        raise FileNotFoundError(f"Нет файла модели: {glb}\nУкажи путь в GLB_PATH вверху скрипта.")
    H = float(height or studio.arg("--height", HEIGHT))
    turn = float(turn if turn is not None else studio.arg("--turn", TURN))
    chcol = studio.collection("Character")
    obj = autorig.import_character(glb, height=H, turn_deg=turn, name="Character", col=chcol)
    # суставы: из файла <имя модели>.joints.json (рядом со скриптом или с моделью), иначе — автопоиск
    lm = None
    base = os.path.splitext(os.path.basename(glb))[0] + ".joints.json"
    for d in (_HERE, os.path.dirname(glb)):
        jp = os.path.join(d, base)
        if os.path.exists(jp):
            import json
            with open(jp, encoding="utf-8") as fh:
                lm = autorig.landmarks_from_joints(json.load(fh), H)
            print("joints from", jp)
            break
    if lm is None:
        lm = autorig.find_landmarks(obj)
    many = len(obj.data.vertices) > 60000       # bone heat на тяжёлых сетках медленный — сразу по расстоянию
    arm = autorig.build_rig(obj, lm, name="Character_Rig", col=chcol, weights="distance" if many else "auto")
    print("landmarks:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in lm.items()
                         if k in ("H", "crotch", "neck", "shoulder_z", "torso_hw")})
    build_set(H)
    motion = Motion(arm, lm)
    # во время запекания меш не нужен — так быстрее
    for m in obj.modifiers:
        m.show_viewport = False
    motion.bake()
    for m in obj.modifiers:
        m.show_viewport = True
    build_cameras(arm, motion)

    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, FRAMES
    engine = studio.arg("--engine", "EEVEE")
    studio.setup_render(engine, studio.RES_480, int(studio.arg("--samples", 16 if engine == "CYCLES" else 32)),
                        fps=FPS, motion_blur=False, exposure=-0.8)
    studio.output_video("//render/chibi_walk_")
    return arm


def main():
    build()
    out = studio.arg("--out")
    if out:
        out = os.path.abspath(out)
        os.makedirs(out, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "chibi_walk.blend"), compress=True)
        print("saved", os.path.join(out, "chibi_walk.blend"))
        if studio.flag("--render"):
            sc = bpy.context.scene
            fr = studio.arg("--frames")
            if fr:
                sc.frame_start, sc.frame_end = (int(v) for v in fr.split("-"))
            sc.render.filepath = os.path.join(out, "chibi_walk_")
            bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
