"""Строит модель и рендерит превью (Cycles CPU) + экспорт .blend / .glb.

python render_preview.py --out ./out [--samples 32] [--no-export]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sapsan_velaro_rus as sapsan  # noqa: E402


def arg(name, default=None):
    argv = sys.argv
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def setup_render(samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 800
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [
        i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'

    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    world.node_tree.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.35

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 4.0
    sun.data.angle = math.radians(3)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-40))
    sc.collection.objects.link(sun)

    ground = bpy.data.meshes.new("Ground")
    ground.from_pydata([(-400, -300, -0.33), (700, -300, -0.33), (700, 300, -0.33), (-400, 300, -0.33)], [], [(0, 1, 2, 3)])
    ground.materials.append(sapsan.make_material("Grass", (0.12, 0.18, 0.08), roughness=1))
    sc.collection.objects.link(bpy.data.objects.new("Ground", ground))


def shot(name, loc, target, out, lens=50, ortho=None):
    sc = bpy.context.scene
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    sc.collection.objects.link(cam)
    cam.location = loc
    look_at(cam, target)
    cam.data.lens = lens
    cam.data.clip_end = 2000
    if ortho:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = ortho
    sc.camera = cam
    sc.render.filepath = os.path.join(out, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)


def main():
    out = os.path.abspath(arg("--out", "out"))
    samples = int(arg("--samples", 32))
    only = arg("--only")
    os.makedirs(out, exist_ok=True)

    sapsan.build_train()

    if "--no-export" not in sys.argv:
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "sapsan_velaro_rus.glb"),
                                  export_format='GLB', export_apply=True)

    setup_render(samples)
    shots = {
        "preview_front_3q": ((-14, -11, 4.2), (6, 0, 1.8), 35, None),
        "preview_nose_side": ((6, -18, 2.2), (6, 0, 2.0), 50, None),
        "preview_train_perspective": ((-30, -38, 12), (70, 0, 1.5), 28, None),
        "preview_tail_3q": ((258, 10, 3.5), (238, 0, 1.8), 35, None),
        "preview_front": ((-40, 0, 2.2), (0, 0, 2.2), 120, None),
        "preview_middle_side": ((85, -20, 2.2), (85, 0, 2.2), 30, None),
    }
    for name, (loc, tgt, lens, ortho) in shots.items():
        if only and only not in name:
            continue
        shot(name, loc, tgt, out, lens, ortho)

    if "--no-export" not in sys.argv:
        # .blend сохраняем со светом, небом и камерами — сразу готов к рендеру
        bpy.context.scene.camera = bpy.data.objects.get("preview_front_3q", bpy.context.scene.camera)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "sapsan_velaro_rus.blend"), compress=True)


if __name__ == "__main__":
    main()
