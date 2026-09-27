"""
Операторская работа: планы (шоты) с движением камеры, сглаженной целью, фокусом, «дикими» стенами
и проверкой, что персонажа ничего не заслоняет.
"""
import math

import bpy  # noqa: I001
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

import studio


class Shot:
    """План: кадры f0…f1, камера движется по keys [(кадр, (x,y,z))] или функции f → (x,y,z).
    aim: ('head'|'chest'|'hips'|'hand.R', смещение) — цель на девочке (сглаживается) или точка (x,y,z).
    wild: объекты, невидимые для камеры в этом плане (стена за камерой)."""

    def __init__(self, name, f0, f1, cam, aim=("chest", (0, 0, 0)), lens=35, lens_to=None, fstop=4.0,
                 wild=(), shake=1.0, smooth=6):
        self.name, self.f0, self.f1 = name, f0, f1
        self.cam, self.aim, self.lens, self.lens_to = cam, aim, lens, lens_to
        self.fstop, self.wild, self.shake, self.smooth = fstop, list(wild), shake, smooth


def _girl_point(g, part, off):
    if part == "head":
        p = g.bone_world("head").lerp(g.bone_world("head", "tail"), 0.4)
    elif part == "chest":
        p = g.bone_world("chest").lerp(g.bone_world("chest", "tail"), 0.6)
    elif part == "hips":
        p = g.bone_world("hips")
    elif part.startswith("hand"):
        p = g.bone_world(part, "tail")
    else:
        raise ValueError(part)
    return p + Vector(off)


def build_shots(g, shots, col, all_wild=()):
    sc = bpy.context.scene
    sc.timeline_markers.clear()
    wild_all = set()
    for s in shots:
        wild_all.update(s.wild)
    wild_all.update(all_wild)
    for s in shots:
        cam = studio.camera("Cam_" + s.name, (0, 0, 0), (0, 1, 0), s.lens, col)
        cam.data.sensor_width = 36
        tgt = bpy.data.objects.new("Aim_" + s.name, None)
        col.objects.link(tgt)
        # цель: сглаженная траектория точки на девочке
        pts = []
        for f in range(s.f0 - 6, s.f1 + 7):
            if isinstance(s.aim, tuple) and isinstance(s.aim[0], str):
                sc.frame_set(max(f, 1))
                pts.append((f, _girl_point(g, s.aim[0], s.aim[1])))
            else:
                pts.append((f, Vector(s.aim)))
        k = s.smooth
        for i in range(0, len(pts), 2):
            lo, hi = max(0, i - k), min(len(pts), i + k + 1)
            avg = sum((p for _, p in pts[lo:hi]), Vector()) / (hi - lo)
            tgt.location = avg
            tgt.keyframe_insert("location", frame=pts[i][0])
        # камера
        if callable(s.cam):
            for f in range(s.f0 - 2, s.f1 + 3, 3):
                cam.location = Vector(s.cam(f))
                cam.keyframe_insert("location", frame=f)
        else:
            for f, loc in s.cam:
                cam.location = Vector(loc)
                cam.keyframe_insert("location", frame=f)
        cam.constraints.clear()
        studio.track_to(cam, tgt)
        if s.lens_to:
            cam.data.lens = s.lens
            cam.data.keyframe_insert("lens", frame=s.f0)
            cam.data.lens = s.lens_to
            cam.data.keyframe_insert("lens", frame=s.f1)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_object = tgt
        cam.data.dof.aperture_fstop = s.fstop
        # лёгкая «ручная» камера
        if s.shake and cam.animation_data and cam.animation_data.action:
            for fc in _fcurves(cam.animation_data.action):
                if fc.data_path == "location":
                    mod = fc.modifiers.new('NOISE')
                    mod.scale = 40
                    mod.strength = 0.006 * s.shake
                    mod.phase = fc.array_index * 13 + len(s.name)
        m = sc.timeline_markers.new(s.name, frame=s.f0)
        m.camera = cam
        s.obj, s.target = cam, tgt
    # «дикие» стены: видимость для камеры по планам
    for ob in wild_all:
        for s in shots:
            ob.visible_camera = ob not in s.wild
            ob.keyframe_insert("visible_camera", frame=s.f0)
    sc.camera = shots[0].obj
    sc.frame_set(shots[0].f0)


def _fcurves(action):
    if hasattr(action, "fcurves") and action.fcurves is not None:
        try:
            return list(action.fcurves)
        except TypeError:
            pass
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def check(g, shots, extra_ignore=(), step=3, verbose=True):
    """Проверка планов: перекрыт ли персонаж (лучи к голове/груди/рукам) и в кадре ли голова."""
    sc = bpy.context.scene
    ignore = {g.obj} | set(extra_ignore) | {p.obj for p in g.props}
    report = []
    for s in shots:
        blocked, outside, total, who = 0, 0, 0, {}
        for f in range(s.f0, s.f1 + 1, step):
            sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            cam = s.obj
            o = cam.matrix_world.translation.copy()
            for part in ("head", "chest", "hips", "hand.R"):
                p = _girl_point(g, part, (0, 0, 0))
                d = p - o
                dist = d.length
                hit, loc, nrm, idx, ob, mat = sc.ray_cast(dg, o, d.normalized(), distance=dist - 0.05)
                total += 1
                if hit and ob not in ignore and ob not in s.wild and (ob.parent not in s.wild if ob.parent else True):
                    blocked += 1
                    who[ob.name] = who.get(ob.name, 0) + 1
            hv = world_to_camera_view(sc, cam, _girl_point(g, "head", (0, 0, 0)))
            if not (0.03 < hv.x < 0.97 and 0.03 < hv.y < 0.97 and hv.z > 0):
                outside += 1
        n = (s.f1 - s.f0) // step + 1
        report.append((s.name, blocked / max(total, 1), outside / n, who))
        if verbose:
            print(f"  план {s.name:18s} перекрыто {100 * blocked / max(total, 1):5.1f}%  голова вне кадра {100 * outside / n:5.1f}%"
                  + (f"  мешает: {who}" if who else ""))
    return report
