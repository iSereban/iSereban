"""
Woman 50 — превью и демо-анимация (проверка рига), качество 480p.

  python render_woman50.py --out ./out            (bpy-модуль)
  blender -b -P render_woman50.py -- --out ./out [--samples 16] [--no-anim]

Результат в out/:
  woman50.blend         — персонаж + свет + камера + демо-анимация 4 с
  preview_*.png         — кадры 854×480
  woman50_demo.mp4      — демо (или PNG-кадры в frames/, если нет FFmpeg)
"""
import os
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Vector  # noqa: F401

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import woman50 as w  # noqa: E402
import studio  # noqa: E402  (путь добавляет woman50)


def aim(arm, bone, direction, frame=None):
    """Повернуть кость так, чтобы она смотрела в мировом направлении direction."""
    bpy.context.view_layer.update()
    pb = arm.pose.bones[bone]
    mw = arm.matrix_world
    cur = (mw @ pb.tail - mw @ pb.head).normalized()
    q = cur.rotation_difference(Vector(direction).normalized())
    m = pb.matrix.copy()
    h = m.translation.copy()
    pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ m
    bpy.context.view_layer.update()
    if frame is not None:
        pb.keyframe_insert("rotation_euler", frame=frame)


def relaxed_arms(arm, frame=None):
    aim(arm, "upper_arm.L", (0.16, 0.03, -1), frame)
    aim(arm, "forearm.L", (0.10, -0.30, -1), frame)
    aim(arm, "upper_arm.R", (-0.16, 0.03, -1), frame)
    aim(arm, "forearm.R", (-0.10, -0.30, -1), frame)


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)


def demo_animation(arm, frames=100):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    reset_pose(arm)
    # руки: опущены → правая машет → опускается
    relaxed_arms(arm, 1)
    relaxed_arms(arm, 12)
    aim(arm, "upper_arm.R", (-0.45, -0.10, 0.55), 26)
    aim(arm, "forearm.R", (0.05, -0.15, 1.0), 26)
    for i, f in enumerate(range(32, 80, 8)):
        aim(arm, "forearm.R", ((-0.40 if i % 2 else 0.25), -0.15, 1.0), f)
    aim(arm, "forearm.R", (0.05, -0.15, 1.0), 82)
    aim(arm, "upper_arm.R", (-0.45, -0.10, 0.55), 82)
    aim(arm, "upper_arm.R", (-0.16, 0.03, -1), 98)
    aim(arm, "forearm.R", (-0.10, -0.30, -1), 98)

    # голова: лёгкий поворот и наклон
    w.pose(arm, "spine.006", (0, 0, 0), frame=1)
    w.pose(arm, "spine.006", (4, 12, -5), frame=30)
    w.pose(arm, "spine.006", (0, -8, 3), frame=65)
    w.pose(arm, "spine.006", (0, 0, 0), frame=98)
    # взгляд
    for s in "LR":
        w.pose(arm, f"ctrl_eye.{s}", (0, 0, 0), frame=1)
        w.pose(arm, f"ctrl_eye.{s}", (0, 0, 10), frame=30)
        w.pose(arm, f"ctrl_eye.{s}", (0, 0, -6), frame=65)
        w.pose(arm, f"ctrl_eye.{s}", (0, 0, 0), frame=98)
    # улыбка, брови
    w.face_key(arm, "smile", 0.0, 1)
    w.face_key(arm, "smile", 1.0, 16)
    w.face_key(arm, "smile", 0.7, 60)
    w.face_key(arm, "smile", 1.0, 90)
    w.face_key(arm, "brow_up", 0.0, 10)
    w.face_key(arm, "brow_up", 1.0, 20)
    w.face_key(arm, "brow_up", 0.0, 34)
    # моргания
    for f0 in (38, 86):
        w.blink(arm, 0.0, f0)
        w.blink(arm, 1.0, f0 + 2)
        w.blink(arm, 0.0, f0 + 5)
    # «говорит»: челюсть + O
    w.jaw_open(arm, 0.0, 44)
    for i, f in enumerate(range(47, 78, 3)):
        w.jaw_open(arm, (0.9, 0.3, 0.7, 0.2)[i % 4], f)
        w.face_key(arm, "mouth_O", (0.0, 0.6, 0.2, 0.8)[i % 4], f)
    w.jaw_open(arm, 0.0, 80)
    w.face_key(arm, "mouth_O", 0.0, 80)
    sc.frame_set(1)


def main():
    out = os.path.abspath(studio.arg("--out", os.path.join(_HERE, "out")))
    samples = int(studio.arg("--samples", 16))
    os.makedirs(out, exist_ok=True)

    arm = w.build()
    studio.studio_lights(target=(0, 0, 1.1))
    studio.floor(color=(0.45, 0.40, 0.36))
    studio.setup_render("CYCLES", studio.RES_480, samples, exposure=-0.3)

    cams = {
        "preview_front": studio.camera("Cam_Front", (0, -4.3, 1.0), (0, 0, 0.86), 50),
        "preview_34": studio.camera("Cam_34", (-2.3, -3.5, 1.3), (0, 0, 0.88), 50),
        "preview_face": studio.camera("Cam_Face", (-0.22, -0.72, 1.57), (0, -0.03, 1.52), 55),
        "preview_side": studio.camera("Cam_Side", (4.3, 0, 1.0), (0, 0, 0.86), 50),
    }
    # A-поза как в координатах
    studio.render_still(os.path.join(out, "preview_front_apose.png"), cams["preview_front"])

    relaxed_arms(arm)
    w.face_key(arm, "smile", 0.9)
    w.jaw_open(arm, 0.25)
    for name in ("preview_front", "preview_34", "preview_side"):
        studio.render_still(os.path.join(out, f"{name}.png"), cams[name])
    for key, fn in (("smile", lambda: (w.face_key(arm, "smile", 0.9), w.jaw_open(arm, 0.25))),
                    ("talk", lambda: (w.jaw_open(arm, 0.8), w.face_key(arm, "mouth_O", 0.5))),
                    ("blink", lambda: w.blink(arm, 1.0))):
        w.face_key(arm, "smile", 0)
        w.face_key(arm, "mouth_O", 0)
        w.jaw_open(arm, 0)
        w.blink(arm, 0)
        fn()
        bpy.context.view_layer.update()
        studio.render_still(os.path.join(out, f"preview_face_{key}.png"), cams["preview_face"])

    demo_animation(arm)
    cam = studio.camera("Cam_Demo", (-0.9, -2.2, 1.45), (0, 0, 1.25), 45)
    cam.location = (-0.9, -2.2, 1.45)
    cam.keyframe_insert("location", frame=1)
    cam.location = (-0.45, -1.6, 1.45)
    cam.keyframe_insert("location", frame=100)
    tgt = bpy.data.objects.new("Cam_Demo_Target", None)
    bpy.context.scene.collection.objects.link(tgt)
    tgt.location = (0, 0, 1.28)
    studio.track_to(cam, tgt)
    bpy.context.scene.camera = cam
    video = studio.output_video("//render/woman50_demo_")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "woman50.blend"), compress=True)
    print("saved", os.path.join(out, "woman50.blend"))

    if not studio.flag("--no-anim"):
        sc = bpy.context.scene
        frames_dir = os.path.join(out, "frames")
        if video:
            sc.render.filepath = os.path.join(out, "woman50_demo_")
        else:
            sc.render.filepath = os.path.join(frames_dir, "f_")
        bpy.ops.render.render(animation=True)
        if not video and studio.frames_to_mp4(frames_dir, os.path.join(out, "woman50_demo.mp4")):
            print("video", os.path.join(out, "woman50_demo.mp4"))


if __name__ == "__main__":
    main()
