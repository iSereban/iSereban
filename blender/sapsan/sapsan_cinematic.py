"""
Сапсан — кинематографичный ролик ~30 с: поезд идёт по перегону,
камеры снимают с разных ракурсов со склейками.

Состав едет в сторону -X (носом вперёд) со скоростью SPEED_KMH.
Склейки — маркеры таймлайна, привязанные к камерам (Ctrl+B в таймлайне).

Запуск:
  * в Blender: Scripting -> открыть этот файл -> Run Script
    (sapsan_velaro_rus.py должен лежать рядом), затем Render -> Render Animation
  * без интерфейса:
      blender -b -P sapsan_cinematic.py -- --out ./anim            (только сцена .blend)
      blender -b -P sapsan_cinematic.py -- --out ./anim --render   (+ кадры и mp4)
    опции: --engine EEVEE|CYCLES  --res 1920x1080  --samples N  --frames 1-750
"""

import math
import os
import random
import sys

import bpy  # noqa: I001
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(bpy.context.space_data.text.filepath))
                if bpy.context.space_data and getattr(bpy.context.space_data, "text", None)
                and bpy.context.space_data.text.filepath else os.path.dirname(os.path.abspath(__file__)))
import sapsan_velaro_rus as sapsan  # noqa: E402

# ---------------------------------------------------------------------------
# Параметры ролика
# ---------------------------------------------------------------------------
FPS = 25
DURATION = 30.0
FRAMES = int(FPS * DURATION)           # 750
SPEED_KMH = 200.0
SPEED = SPEED_KMH / 3.6                # м/с
TRAIN_LEN = sapsan.CARS[-1][1]         # 244.47 м
TRAVEL = SPEED * DURATION              # ~1667 м

TRACK_X0 = -TRAVEL - 400
TRACK_X1 = TRAIN_LEN + 250

random.seed(7)
FIELD_X = (-1900.0, -800.0)   # безлесный участок слева от пути


def nose_x(frame):
    """Мировая X носа состава в кадре frame."""
    return -SPEED * (frame - 1) / FPS


# ---------------------------------------------------------------------------
# Окружение
# ---------------------------------------------------------------------------
def mat_ground():
    m = bpy.data.materials.new("Grass_Procedural")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.08
    noise.inputs["Detail"].default_value = 6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.10, 0.16, 0.05, 1)
    ramp.color_ramp.elements[1].color = (0.28, 0.30, 0.10, 1)
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 3.0
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = 'MULTIPLY'
    mix.inputs["Fac"].default_value = 0.35
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(fine.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    m.diffuse_color = (0.18, 0.24, 0.08, 1)
    return m


def build_ground(col):
    me = bpy.data.meshes.new("Ground")
    y = 900
    me.from_pydata([(TRACK_X0 - 600, -y, -0.33), (TRACK_X1 + 600, -y, -0.33),
                    (TRACK_X1 + 600, y, -0.33), (TRACK_X0 - 600, y, -0.33)], [], [(0, 1, 2, 3)])
    me.materials.append(mat_ground())
    col.objects.link(bpy.data.objects.new("Ground", me))


def build_catenary(col, mats):
    """Опоры контактной сети через 60 м + контактный провод над осью пути."""
    wire_z = sapsan.BODY_HEIGHT + 1.85
    bm = bmesh.new()
    sapsan.add_box(bm, (0, 4.2, 3.8), (0.3, 0.3, 8.2))               # опора
    sapsan.add_box(bm, (0, 2.2, 7.3), (0.12, 4.2, 0.12))             # консоль
    sapsan.add_box(bm, (0, 0.0, wire_z + 0.55), (0.05, 0.05, 1.2))   # струна
    me = bpy.data.meshes.new("Catenary_Mast")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["steel"])
    mast = bpy.data.objects.new("Catenary_Masts", me)
    col.objects.link(mast)
    mast.location.x = TRACK_X0
    arr = mast.modifiers.new("Array", 'ARRAY')
    arr.use_relative_offset = False
    arr.use_constant_offset = True
    arr.constant_offset_displace = (60.0, 0, 0)
    arr.count = int((TRACK_X1 - TRACK_X0) / 60) + 1

    bm = bmesh.new()
    for y, z, r in ((0.0, wire_z, 0.012), (0.0, wire_z + 1.15, 0.01)):
        sapsan.add_box(bm, ((TRACK_X0 + TRACK_X1) / 2, y, z), (TRACK_X1 - TRACK_X0, r * 2, r * 2))
    me = bpy.data.meshes.new("Contact_Wire")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["dark"])
    col.objects.link(bpy.data.objects.new("Contact_Wire", me))


def build_trees(col):
    """Лесополосы по обе стороны: деревья в одной сетке (быстро)."""
    leaf = bpy.data.materials.new("Tree_Leaves")
    leaf.use_nodes = True
    leaf.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.12, 0.04, 1)
    leaf.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    leaf.diffuse_color = (0.05, 0.12, 0.04, 1)
    birch = bpy.data.materials.new("Tree_Leaves_Light")
    birch.use_nodes = True
    birch.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.16, 0.25, 0.06, 1)
    birch.diffuse_color = (0.16, 0.25, 0.06, 1)
    trunk = bpy.data.materials.new("Tree_Trunk")
    trunk.use_nodes = True
    trunk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.08, 0.05, 1)
    trunk.diffuse_color = (0.12, 0.08, 0.05, 1)

    bm = bmesh.new()
    x = TRACK_X0
    while x < TRACK_X1:
        for side in (-1, 1):
            if random.random() < 0.15:
                continue  # просеки
            for _ in range(random.randint(2, 5)):
                y = side * (random.uniform(18, 26) + random.expovariate(1 / 18))
                if side < 0 and FIELD_X[0] < x < FIELD_X[1] and abs(y) < 160:
                    continue  # поле под общий план (кадр 6)
                h = random.uniform(9, 18)
                px = x + random.uniform(-6, 6)
                spruce = random.random() < 0.55
                tr = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.25,
                                           radius2=0.18, depth=h * 0.35)
                for v in tr["verts"]:
                    v.co += Vector((px, y, h * 0.175 - 0.33))
                for f in {f for v in tr["verts"] for f in v.link_faces}:
                    f.material_index = 2
                if spruce:
                    cr = bmesh.ops.create_cone(bm, cap_ends=True, segments=8,
                                               radius1=h * 0.22, radius2=0.0, depth=h * 0.85)
                    zc = h * 0.15 + h * 0.425
                    mi = 0
                else:
                    cr = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=h * 0.28)
                    zc = h * 0.62
                    mi = 1
                for v in cr["verts"]:
                    v.co.z *= 1.0 if spruce else 1.25
                    v.co += Vector((px, y, zc - 0.33))
                for f in {f for v in cr["verts"] for f in v.link_faces}:
                    f.material_index = mi
        x += random.uniform(9, 16)
    me = bpy.data.meshes.new("Trees")
    bm.to_mesh(me)
    bm.free()
    for m in (leaf, birch, trunk):
        me.materials.append(m)
    col.objects.link(bpy.data.objects.new("Trees", me))


def build_world(scene):
    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.radians(28)
        sky.sun_rotation = math.radians(210)
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.22

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = (math.radians(62), 0, math.radians(-30))
    scene.collection.objects.link(sun)


# ---------------------------------------------------------------------------
# Анимация состава
# ---------------------------------------------------------------------------
def linear_fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    curves = []
    if hasattr(ad.action, "fcurves"):
        curves = list(ad.action.fcurves)
    if not curves:
        # Blender 4.4+/5.x: слои/слоты действия
        for layer in getattr(ad.action, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.extrapolation = 'LINEAR'


def animate_train(scene):
    rig = bpy.data.objects["Sapsan_Rig"]
    rig.location.x = nose_x(1)
    rig.keyframe_insert("location", index=0, frame=1)
    rig.location.x = nose_x(FRAMES)
    rig.keyframe_insert("location", index=0, frame=FRAMES)
    linear_fcurves(rig)

    # вращение колёсных пар: угол = путь / радиус
    angle = TRAVEL / sapsan.WHEEL_RADIUS
    for obj in bpy.data.objects:
        if "_Wheelset" not in obj.name:
            continue
        tail = obj.name.startswith(f"Car{len(sapsan.CARS):02d}")
        sign = 1 if tail else -1   # у хвостового вагона root зеркален по X
        obj.rotation_euler.y = 0
        obj.keyframe_insert("rotation_euler", index=1, frame=1)
        obj.rotation_euler.y = sign * angle * (FRAMES - 1) / FRAMES
        obj.keyframe_insert("rotation_euler", index=1, frame=FRAMES)
        linear_fcurves(obj)


# ---------------------------------------------------------------------------
# Камеры
# ---------------------------------------------------------------------------
def add_target(name, parent=None, loc=(0, 0, 0)):
    t = bpy.data.objects.new(name, None)
    t.empty_display_size = 0.5
    bpy.context.scene.collection.objects.link(t)
    t.parent = parent
    t.location = loc
    return t


def add_camera(name, lens, target, parent=None):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = lens
    cam.data.clip_start = 0.1
    cam.data.clip_end = 5000
    cam.data.sensor_width = 36
    cam.parent = parent
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    return cam


def key_path(obj, frames_locs, smooth=True):
    for f, loc in frames_locs:
        obj.location = loc
        obj.keyframe_insert("location", frame=f)
    if not smooth:
        linear_fcurves(obj)


def key_lens(cam, frames_lens):
    for f, lens in frames_lens:
        cam.data.lens = lens
        cam.data.keyframe_insert("lens", frame=f)


def build_shots(scene):
    rig = bpy.data.objects["Sapsan_Rig"]
    shots = []  # (start_frame, camera)

    # 1. Засада у полотна: поезд вылетает из дали и проносится мимо, камера панорамирует
    f0, f1 = 1, 100
    pass_frame = 82
    tgt = add_target("T1_nose", rig, (6, 0, 2.2))
    cam = add_camera("Shot1_Approach", 32, tgt)
    cam.location = (nose_x(pass_frame), -6.5, 1.1)
    key_path(cam, [(f0, (nose_x(pass_frame) - 1.0, -6.5, 1.0)), (f1, (nose_x(pass_frame) + 1.0, -6.3, 1.2))])
    key_lens(cam, [(f0, 70), (60, 40), (f1, 28)])
    shots.append((f0, cam))

    # 2. Дрон: облёт головы от 3/4 слева-спереди поверху на правую сторону
    f0, f1 = 101, 210
    tgt = add_target("T2_head", rig, (8, 0, 2.0))
    cam = add_camera("Shot2_Drone", 30, tgt, rig)
    key_path(cam, [(f0, (-35, -28, 14)), (155, (-24, 0, 16)), (f1, (-10, 24, 7))])
    shots.append((f0, cam))

    # 3. Крупно: колёса передней... задней тележки головного вагона, камера у рельса
    f0, f1 = 211, 290
    tgt = add_target("T3_bogie", rig, (21.455, 0, 0.55))
    cam = add_camera("Shot3_Wheels", 24, tgt, rig)
    key_path(cam, [(f0, (15.0, -3.1, 0.35)), (f1, (18.5, -2.8, 0.45))])
    shots.append((f0, cam))

    # 4. Камера впереди поезда, смотрит на лоб — «несётся прямо на нас»
    f0, f1 = 291, 390
    tgt = add_target("T4_front", rig, (4, 0, 2.3))
    cam = add_camera("Shot4_HeadOn", 45, tgt, rig)
    key_path(cam, [(f0, (-22, -2.5, 2.2)), (f1, (-13, -5.5, 3.2))])
    key_lens(cam, [(f0, 50), (f1, 32)])
    shots.append((f0, cam))

    # 5. Вдоль крыши к токоприёмнику 3-го вагона
    f0, f1 = 391, 490
    px = sapsan.CARS[2][0] + (sapsan.CARS[2][1] - sapsan.CARS[2][0]) / 2
    tgt = add_target("T5_panto", rig, (px, 0, 5.2))
    cam = add_camera("Shot5_Roof", 30, tgt, rig)
    key_path(cam, [(f0, (px - 26, -4.5, 7.2)), (f1, (px - 9, -3.2, 6.4))])
    shots.append((f0, cam))

    # 6. Общий план с высоты: состав проходит через кадр, камера ведёт середину поезда
    f0, f1 = 491, 630
    mid = add_target("T6_mid", rig, (TRAIN_LEN / 2, 0, 2.0))
    cx = nose_x(560) + TRAIN_LEN / 2
    cam = add_camera("Shot6_Wide", 40, mid)
    key_path(cam, [(f0, (cx + 20, -95, 26)), (f1, (cx - 20, -85, 20))])
    shots.append((f0, cam))

    # 7. Финал: хвост уходит вдаль, камера стоит у пути и медленно поднимается
    f0, f1 = 631, FRAMES
    tail = add_target("T7_tail", rig, (TRAIN_LEN - 8, 0, 2.0))
    cx = nose_x(f0) + TRAIN_LEN + 14
    cam = add_camera("Shot7_Departure", 35, tail)
    key_path(cam, [(f0, (cx, -3.4, 1.4)), (f1, (cx - 4, -3.0, 4.5))])
    key_lens(cam, [(f0, 30), (675, 70), (f1, 160)])
    shots.append((f0, cam))

    scene.timeline_markers.clear()
    for f, cam in shots:
        m = scene.timeline_markers.new(cam.name, frame=f)
        m.camera = cam
    scene.camera = shots[0][1]
    return shots


# ---------------------------------------------------------------------------
# Рендер
# ---------------------------------------------------------------------------
def setup_render(scene, engine="EEVEE", res=(1920, 1080), samples=64):
    scene.frame_start = 1
    scene.frame_end = FRAMES
    scene.render.fps = FPS
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = True
    if hasattr(scene.render, "motion_blur_shutter"):
        scene.render.motion_blur_shutter = 0.5
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    if engine.upper().startswith("EEVEE"):
        scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
        ee = scene.eevee
        ee.taa_render_samples = samples
        for attr, val in (("use_shadows", True), ("use_raytracing", True),
                          ("use_gtao", True), ("use_bloom", True)):
            if hasattr(ee, attr):
                setattr(ee, attr, val)
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
    vt = [i.identifier for i in scene.view_settings.bl_rna.properties['view_transform'].enum_items]
    scene.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
    scene.view_settings.exposure = -0.6
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue


def set_output_video(scene):
    """Вывод рядом с .blend: //render/sapsan_cinematic_0001-0750.mp4"""
    scene.render.filepath = "//render/sapsan_cinematic_"
    ims = scene.render.image_settings
    try:
        if hasattr(ims, "media_type"):   # Blender 5.x
            ims.media_type = 'VIDEO'
        ims.file_format = 'FFMPEG'
    except TypeError:
        # сборка без FFmpeg: пишем PNG-кадры, mp4 склеить внешним ffmpeg
        ims.file_format = 'PNG'
        scene.render.filepath = "//render/frames/f_"
        return
    ff = scene.render.ffmpeg
    ff.format = 'MPEG4'
    ff.codec = 'H264'
    ff.constant_rate_factor = 'HIGH'
    ff.ffmpeg_preset = 'GOOD'


def build_scene():
    sapsan.build_train(with_track=False)
    scene = bpy.context.scene
    mats = {m.name: m for m in bpy.data.materials}
    mat = {"steel": mats["Steel"], "dark": mats["Dark_Metal"],
           "sleeper": mats["Sleeper_Concrete"], "ground": mats["Ballast"]}

    env = bpy.data.collections.new("Environment")
    scene.collection.children.link(env)
    sapsan.build_track(env, mat, TRACK_X0, TRACK_X1)
    build_ground(env)
    build_catenary(env, mat)
    build_trees(env)
    build_world(scene)

    animate_train(scene)
    build_shots(scene)
    return scene


def arg(name, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return argv[argv.index(name) + 1] if name in argv else default


def main():
    scene = build_scene()
    engine = arg("--engine", "EEVEE")
    res = tuple(int(v) for v in arg("--res", "1920x1080").split("x"))
    samples = int(arg("--samples", 64 if engine.upper().startswith("EEVEE") else 32))
    setup_render(scene, engine, res, samples)
    set_output_video(scene)

    out = arg("--out")
    if not out:
        return  # запуск из интерфейса Blender: сцена готова, жми Render Animation
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "sapsan_cinematic.blend"), compress=True)
    print("saved scene", os.path.join(out, "sapsan_cinematic.blend"))

    if "--render" in sys.argv:
        frames = arg("--frames")
        if frames:
            a, b = (int(v) for v in frames.split("-"))
            scene.frame_start, scene.frame_end = a, b
        if scene.render.image_settings.file_format != 'FFMPEG':
            # нет FFmpeg: PNG-кадры (можно продолжить после обрыва), mp4 — внешним ffmpeg
            scene.render.filepath = os.path.join(out, "frames", "f_")
            scene.render.use_overwrite = False
        else:
            scene.render.filepath = os.path.join(out, "sapsan_cinematic_")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
