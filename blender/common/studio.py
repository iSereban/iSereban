"""
Общие утилиты студии: очистка сцены, материалы, камеры, свет, рендер.

Все персонажи / объекты / локации импортируют этот модуль, чтобы сцены
собирались одинаково. Качество по умолчанию — 480p (854×480), 25 fps.

Подключение из скрипта в любой подпапке blender/…:
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "common"))
    import studio
"""

import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

RES_480 = (854, 480)
FPS = 25


# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------
def script_dir(file_var=None):
    """Папка текущего скрипта: работает и в Blender Text Editor, и из консоли."""
    sd = getattr(bpy.context, "space_data", None)
    text = getattr(sd, "text", None) if sd else None
    if text and text.filepath:
        return os.path.dirname(bpy.path.abspath(text.filepath))
    if file_var:
        return os.path.dirname(os.path.abspath(file_var))
    return os.getcwd()


def cli_args():
    """Аргументы после «--» (blender -b -P script.py -- ...) или обычные argv."""
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else argv[1:]


def arg(name, default=None):
    a = cli_args()
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


def flag(name):
    return name in cli_args()


# ---------------------------------------------------------------------------
# Сцена
# ---------------------------------------------------------------------------
def clear_scene():
    """Удаляет всё содержимое файла (безопасно в интерфейсе Blender)."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights,
                  bpy.data.worlds, bpy.data.armatures, bpy.data.actions, bpy.data.curves):
        for item in list(block):
            block.remove(item)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.timeline_markers.clear()
    return sc


def collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def link(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def material(name, color, roughness=0.5, metallic=0.0, sss=0.0, emission=None, spec=0.5):
    """Principled-материал; color — RGB 0..1."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    if sss:
        key = "Subsurface Weight" if "Subsurface Weight" in b.inputs else "Subsurface"
        b.inputs[key].default_value = sss
        if "Subsurface Radius" in b.inputs:
            b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        if "Subsurface Scale" in b.inputs:
            b.inputs["Subsurface Scale"].default_value = 0.01
    key = "Specular IOR Level" if "Specular IOR Level" in b.inputs else "Specular"
    if key in b.inputs:
        b.inputs[key].default_value = spec
    if emission:
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = 3.0
    return mat


def apply_modifier(obj, mod):
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def parent_to_bone(obj, arm, bone):
    """Привязать объект к кости, сохранив его мировое положение."""
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = 'BONE'
    obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = mw


def linear_fcurves(idblock):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return
    curves = list(getattr(ad.action, "fcurves", []) or [])
    if not curves:  # Blender 4.4+/5.x: слои действия
        for layer in getattr(ad.action, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


# ---------------------------------------------------------------------------
# Камера / свет / мир
# ---------------------------------------------------------------------------
def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def camera(name, loc, target, lens=50, col=None):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    (col or bpy.context.scene.collection).objects.link(cam)
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 1000
    look_at(cam, target)
    return cam


def track_to(obj, target_obj):
    con = obj.constraints.new('TRACK_TO')
    con.target = target_obj
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    return con


def studio_lights(col=None, target=(0, 0, 1.0), strength=1.0):
    """Трёхточечный свет (ключевой, заполняющий, контровой) + мягкий мир."""
    col = col or bpy.context.scene.collection
    lights = []
    for name, loc, energy, size, color in (
        ("Key", (-2.2, -2.8, 2.6), 350, 1.5, (1.0, 0.95, 0.9)),
        ("Fill", (2.8, -2.0, 1.6), 120, 2.5, (0.85, 0.9, 1.0)),
        ("Rim", (0.8, 2.8, 2.4), 260, 1.0, (1.0, 1.0, 1.0)),
    ):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy * strength
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        col.objects.link(lo)
        lo.location = loc
        look_at(lo, target)
        lights.append(lo)
    world(0.25)
    return lights


def world(strength=0.3, color=(0.62, 0.68, 0.75)):
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    return w


def floor(size=20, color=(0.55, 0.55, 0.57), col=None, name="Floor"):
    me = bpy.data.meshes.new(name)
    s = size / 2
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(material(name + "_Mat", color, roughness=0.8))
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Рендер
# ---------------------------------------------------------------------------
def setup_render(engine="CYCLES", res=RES_480, samples=24, fps=FPS, motion_blur=False):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = fps
    sc.render.use_motion_blur = motion_blur
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    if engine.upper().startswith("EEVEE"):
        sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = samples
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 4
    vt = [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items]
    sc.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
    return sc


def output_video(path_prefix="//render/video_"):
    """MP4 H.264, если в сборке Blender есть FFmpeg; иначе PNG-кадры. Возвращает True для видео."""
    sc = bpy.context.scene
    ims = sc.render.image_settings
    try:
        if hasattr(ims, "media_type"):
            ims.media_type = 'VIDEO'
        ims.file_format = 'FFMPEG'
    except TypeError:
        if hasattr(ims, "media_type"):
            ims.media_type = 'IMAGE'
        ims.file_format = 'PNG'
        sc.render.filepath = path_prefix.rsplit("/", 1)[0] + "/frames/f_"
        return False
    ff = sc.render.ffmpeg
    ff.format = 'MPEG4'
    ff.codec = 'H264'
    ff.constant_rate_factor = 'HIGH'
    sc.render.filepath = path_prefix
    return True


def render_still(path, cam=None):
    sc = bpy.context.scene
    if cam:
        sc.camera = cam
    ims = sc.render.image_settings
    if hasattr(ims, "media_type"):
        ims.media_type = 'IMAGE'
    ims.file_format = 'PNG'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def frames_to_mp4(frames_dir, out_path, fps=FPS):
    """Склейка PNG-кадров в mp4 внешним ffmpeg (если он есть в системе)."""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return False
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-pattern_type", "glob", "-i", os.path.join(frames_dir, "*.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    "-movflags", "+faststart", out_path], check=True)
    return True
