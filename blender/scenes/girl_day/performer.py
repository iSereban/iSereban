"""
Актёр: чиби-девочка (Meshy .glb) со скелетом autorig и «режиссёрской» анимацией.

Анимация задаётся дорожками (Track) по кадрам и сегментами пути (Hold / Walk):
  • путь корня: стоять/поворачиваться (Hold) или идти по точкам (Walk) с разгоном и торможением;
    фаза шага считается по пройденному расстоянию — ноги не скользят
  • позы: sit (сидит), squat (присед), lean (наклон корпуса, °), hop (подскок, м), bow (кивок, °)
  • взгляд: look (точка в мире) с весом look_w
  • руки: IK к цели (hand_R / hand_L, вес ik_R / ik_L), иначе — исходная поза «руки в карманах»
  • реквизит: world → hand → back… с плавной передачей (Prop.modes)
Всё запекается в ключи (кватернионы костей + матрицы реквизита).
"""
import json
import math
import os

import bpy  # noqa: I001
from mathutils import Matrix, Quaternion, Vector

import autorig


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    if isinstance(a, (int, float)):
        return a + (b - a) * t
    return Vector(a).lerp(Vector(b), t)


class Track:
    """Ключи [(кадр, значение)], между ключами — плавно (smoothstep), вне — держит крайние."""

    def __init__(self, keys=(), default=0.0):
        self.keys = sorted(keys, key=lambda k: k[0])
        self.default = default

    def __call__(self, f):
        k = self.keys
        if not k:
            return self.default
        if f <= k[0][0]:
            return k[0][1]
        if f >= k[-1][0]:
            return k[-1][1]
        for (f0, v0), (f1, v1) in zip(k, k[1:]):
            if f0 <= f <= f1:
                if v0 is None or v1 is None:
                    return v0 if f < f1 else v1
                return _lerp(v0, v1, smooth((f - f0) / max(f1 - f0, 1e-6)))
        return k[-1][1]


# ---------------------------------------------------------------------------
# Путь корня
# ---------------------------------------------------------------------------
class Hold:
    """Стоять на месте (можно поворачиваться): psi — курс в градусах (0 — лицом в −Y)."""

    def __init__(self, f0, f1, pos, psi0, psi1=None):
        self.f0, self.f1 = f0, f1
        self.pos = Vector(pos)
        self.psi0 = math.radians(psi0)
        self.psi1 = math.radians(psi0 if psi1 is None else psi1)

    def at(self, f):
        t = smooth((f - self.f0) / max(self.f1 - self.f0, 1))
        return self.pos.copy(), self.psi0 + (self.psi1 - self.psi0) * t


class Walk:
    """Идти по точкам (x, y[, z]) за кадры f0…f1: разгон/торможение ~0,4 с, курс — по касательной."""

    def __init__(self, f0, f1, pts, ease=10, turn_in=8):
        self.f0, self.f1 = f0, f1
        P = [Vector((p[0], p[1], p[2] if len(p) > 2 else 0.0)) for p in pts]
        # сглаженная ломаная (Catmull–Rom)
        dense = []
        Q = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
        for i in range(1, len(Q) - 2):
            for k in range(12):
                t = k / 12
                p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
                dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                                    (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
        dense.append(P[-1])
        self.pts = dense
        self.cum = [0.0]
        for a, b in zip(dense, dense[1:]):
            self.cum.append(self.cum[-1] + (b - a).length)
        self.L = self.cum[-1]
        self.ease = ease
        self.turn_in = turn_in
        self.psi_prev = None

    def _s(self, f):
        n = self.f1 - self.f0
        e = min(self.ease, n / 2)
        vmax = self.L / max(n - e, 1)                     # трапеция скорости
        t = f - self.f0
        if t <= 0:
            return 0.0
        if t >= n:
            return self.L
        if t < e:
            return vmax * t * t / (2 * e)
        if t > n - e:
            r = n - t
            return self.L - vmax * r * r / (2 * e)
        return vmax * (t - e / 2)

    def at(self, f):
        s = self._s(f)
        i = 0
        while i < len(self.cum) - 2 and self.cum[i + 1] < s:
            i += 1
        a, b = self.pts[i], self.pts[i + 1]
        seg = max(self.cum[i + 1] - self.cum[i], 1e-9)
        p = a.lerp(b, (s - self.cum[i]) / seg)
        d = b - a
        psi = math.atan2(d.x, -d.y)                       # вперёд = (sin ψ, −cos ψ) — как поворот объекта на ψ
        if self.psi_prev is not None and f - self.f0 < self.turn_in:
            k = smooth((f - self.f0) / self.turn_in)
            dp = math.remainder(psi - self.psi_prev, 2 * math.pi)
            psi = self.psi_prev + dp * k
        return p, psi


class Path:
    def __init__(self, segments):
        self.segs = sorted(segments, key=lambda s: s.f0)
        prev_psi = None
        for s in self.segs:
            if isinstance(s, Walk):
                s.psi_prev = prev_psi
            prev_psi = s.at(s.f1)[1]

    def at(self, f):
        for s in self.segs:
            if s.f0 <= f <= s.f1:
                return s.at(f)
        if f < self.segs[0].f0:
            return self.segs[0].at(self.segs[0].f0)
        last = [s for s in self.segs if s.f1 < f][-1]
        return last.at(last.f1)


# ---------------------------------------------------------------------------
# Реквизит
# ---------------------------------------------------------------------------
class Prop:
    """Объект реквизита. modes: [(кадр, режим, параметры)], режим: 'world' | 'hand_R' | 'hand_L' | 'back' | 'hidden'.
    Переход между режимами — плавный за blend кадров."""

    def __init__(self, obj, modes, blend=6, scale=1.0):
        self.obj = obj
        self.modes = sorted(modes, key=lambda m: m[0])
        self.blend = blend
        self.scale = scale
        obj.scale = (scale,) * 3
        bpy.context.view_layer.update()
        self.world0 = Matrix.LocRotScale(obj.matrix_world.to_translation(), obj.matrix_world.to_quaternion(), None)


# ---------------------------------------------------------------------------
# Девочка
# ---------------------------------------------------------------------------
class Girl:
    def __init__(self, glb, joints_json, H=1.3, col=None, name="Girl"):
        self.H = H
        self.obj = autorig.import_character(glb, height=H, name=name, col=col)
        with open(joints_json, encoding="utf-8") as fh:
            self.lm = autorig.landmarks_from_joints(json.load(fh), H)
        self.arm = autorig.build_rig(self.obj, self.lm, name=name + "_Rig", col=col, weights="distance")
        arm = self.arm
        self.lt = autorig.bone_length(arm, "thigh.L")
        self.ls = autorig.bone_length(arm, "shin.L")
        self.la = autorig.bone_length(arm, "upper_arm.R")
        self.lf = autorig.bone_length(arm, "forearm.R")
        self.hip_rest = arm.data.bones["thigh.L"].head_local.z
        fb = arm.data.bones["foot.L"]
        v = fb.tail_local - fb.head_local
        self.foot_slope = math.atan2(-v.z, max(math.hypot(v.x, v.y), 1e-6))
        # параметры походки
        self.stride = 1.35 * (self.lt + self.ls)        # длина двойного шага
        # дорожки по умолчанию
        self.path = None
        self.T = {k: Track(default=d) for k, d in (
            ("sit", 0.0), ("squat", 0.0), ("lean", 0.0), ("hop", 0.0), ("bow", 0.0), ("look_w", 0.0),
            ("ik_R", 0.0), ("ik_L", 0.0), ("sit_z", 0.0), ("zoff", 0.0), ("tilt", 0.0))}
        self.T["look"] = Track(default=None)
        self.T["hand_R"] = Track(default=None)
        self.T["hand_L"] = Track(default=None)
        self.props = []
        self.ground = None            # функция (x, y) → z (ступеньки)

    # ---------------- вспомогательное
    def set(self, name, keys):
        self.T[name] = Track(keys, self.T[name].default if name in self.T else 0.0)

    def bone_world(self, bone, where="head"):
        pb = self.arm.pose.bones[bone]
        return self.arm.matrix_world @ (pb.head if where == "head" else pb.tail)

    def _rest_dir(self, bone):
        b = self.arm.data.bones[bone]
        return (self.arm.matrix_world.to_3x3() @ (b.tail_local - b.head_local)).normalized()

    # ---------------- предварительный проход: фаза и амплитуда шага
    def _gait(self, f_last):
        self.gait = {}
        phase, step_s = 0.0, 0.0
        prev = None
        for f in range(1, f_last + 1):
            p, psi = self.path.at(f)
            if prev is None:
                dist, dpsi = 0.0, 0.0
            else:
                dist = (p.xy - prev[0].xy).length
                dpsi = abs(math.remainder(psi - prev[1], 2 * math.pi))
            v = dist * 25.0
            target = min(1.0, v / 0.35) if v > 0.02 else 0.0
            target = max(target, min(1.0, dpsi / 0.035))
            step_s += (target - step_s) * 0.25
            phase += 2 * math.pi * (dist / self.stride) + dpsi * 1.2
            self.gait[f] = (phase, step_s)
            prev = (p, psi)

    # ---------------- поза в кадре f
    def pose(self, f):
        arm, H, T = self.arm, self.H, self.T
        pos, psi = self.path.at(f)
        phase, step = self.gait[f]
        Z = Vector((0, 0, 1))
        F = Vector((math.sin(psi), -math.cos(psi), 0))
        Lv = Vector((math.cos(psi), math.sin(psi), 0))        # влево персонажа
        sit, squat = T["sit"](f), T["squat"](f)
        walk_k = step * (1 - sit)

        # --- ноги
        legs = {}
        for s, off in (("L", 0.0), ("R", math.pi)):
            ph = phase + off
            th = math.radians(24) * math.sin(ph) * walk_k
            knee = math.radians(6 + 48 * max(0.0, math.cos(ph)) ** 1.5 * walk_k)
            th += math.radians(80) * squat
            knee += math.radians(115) * squat
            legs[s] = (th, knee)
        drops = [self.lt * math.cos(th) + self.ls * math.cos(th - kn) for th, kn in legs.values()]
        hip_drop = (self.lt + self.ls) - max(drops)
        bob = 0.012 * H * abs(math.cos(phase)) * walk_k
        z_ground = self.ground(pos.x, pos.y) if self.ground else 0.0
        z = pos.z + z_ground + (1 - sit) * (-hip_drop + bob) + sit * T["sit_z"](f) + T["hop"](f) + T["zoff"](f)
        arm.location = Vector((pos.x, pos.y, z))
        arm.rotation_euler = (0, 0, psi)
        bpy.context.view_layer.update()
        autorig.reset_pose(arm)

        # --- корпус
        lean = math.radians(6 * walk_k + 25 * squat + T["lean"](f))
        tilt = math.radians(T["tilt"](f))
        side = Lv * math.sin(tilt)
        autorig.aim(arm, "hips", Z * math.cos(lean * 0.5) + F * math.sin(lean * 0.5))
        autorig.aim(arm, "spine", Z * math.cos(lean) + F * math.sin(lean) + side * 0.5)
        autorig.aim(arm, "chest", Z * math.cos(lean * 0.6) + F * math.sin(lean * 0.6) + side)

        # --- голова: кивок + взгляд
        nod = math.radians(3 * math.sin(phase * 2) * walk_k + T["bow"](f))
        hd = Z * math.cos(nod) + F * math.sin(nod) + side * 1.2
        look, lw = T["look"](f), T["look_w"](f)
        if look is not None and lw > 0:
            hp = self.bone_world("head")
            d = (Vector(look) - hp).normalized()
            hd = hd.normalized().lerp((Z * 1.0 + d * 0.55).normalized(), lw)
        autorig.aim(arm, "head", hd)

        # --- ноги (после таза)
        for s, sg in (("L", 1), ("R", -1)):
            th, kn = legs[s]
            tdir = -Z * math.cos(th) + F * math.sin(th) + Lv * sg * 0.03
            ts = th - kn
            sdir = -Z * math.cos(ts) + F * math.sin(ts)
            if sit > 0:
                tdir = tdir.normalized().lerp((F - Z * 0.08 + Lv * sg * 0.08).normalized(), sit)
                swing = math.sin(f * 0.11 + (0 if s == "L" else 2.0)) * 0.12      # болтает ногами
                sdir = sdir.normalized().lerp((-Z + F * (0.25 + swing)).normalized(), sit)
            autorig.aim(arm, f"thigh.{s}", tdir)
            autorig.aim(arm, f"shin.{s}", sdir)
            toe_lift = math.radians(15) * max(0.0, math.cos(phase + (0 if s == "L" else math.pi))) * walk_k
            fa = self.foot_slope - toe_lift
            autorig.aim(arm, f"foot.{s}", F * math.cos(fa) - Z * math.sin(fa))

        # --- руки: покой (в карманах) + IK
        for s, sg in (("L", 1), ("R", -1)):
            sw = math.radians(4 if s == "L" else 14) * math.sin(phase + (0 if s == "R" else math.pi)) * walk_k
            rot = Matrix.Rotation(sw, 3, Lv)
            ua_rest = rot @ self._rest_dir(f"upper_arm.{s}")
            fa_rest = rot @ self._rest_dir(f"forearm.{s}")
            w = T["ik_" + s](f)
            tgt = T["hand_" + s](f)
            if w > 0 and tgt is not None:
                S = self.bone_world(f"upper_arm.{s}")
                pole = (-F * 0.3 + Lv * sg * 1.0 - Z * 0.6)
                u, fdir = ik_dirs(S, Vector(tgt), self.la, self.lf, pole)
                ua = ua_rest.lerp(u, w)
                fa = fa_rest.lerp(fdir, w)
            else:
                ua, fa = ua_rest, fa_rest
            autorig.aim(arm, f"upper_arm.{s}", ua)
            autorig.aim(arm, f"forearm.{s}", fa)
            autorig.aim(arm, f"hand.{s}", fa)
        self._frame_basis = (F, Lv, Z)

    # ---------------- реквизит
    def prop_matrix(self, prop, mode, par, f):
        F, Lv, Z = self._frame_basis
        if mode == "world":
            return prop.world0 if par is None else par
        if mode == "hidden":
            return None
        if mode.startswith("hand"):
            s = mode[-1]
            h0, h1 = self.bone_world(f"hand.{s}"), self.bone_world(f"hand.{s}", "tail")
            palm = h0.lerp(h1, 0.6)
            style = par or "fist"
            head = self.bone_world("head").lerp(self.bone_world("head", "tail"), 0.35)
            fdir = (h1 - h0).normalized()
            if style == "pencil":
                x = (fdir * 0.2 - Z + F * 0.35).normalized()
                z = F.cross(x).normalized()
                return _mat(palm, x, x.cross(z) * -1, z)
            if style == "comb":
                to_head = (head - palm)
                x = (fdir - to_head.normalized() * fdir.dot(to_head.normalized())).normalized()
                ny = (to_head - x * x.dot(to_head)).normalized()          # зубцы (−Y) к волосам
                y = -ny
                return _mat(palm, x, y, x.cross(y))
            if style == "phone":
                eye = head
                zax = (eye - palm).normalized()                           # экран к лицу
                yax = (Z - zax * Z.dot(zax)).normalized()
                xax = yax.cross(zax)
                return _mat(palm + zax * 0.01, xax, yax, zax)
            if style == "bag":
                yax = F
                xax = Lv
                return _mat(palm - Z * 0.33, xax, yax, Z)
            return _mat(palm, Lv, F, Z)
        if mode == "back":
            c0, c1 = self.bone_world("chest"), self.bone_world("chest", "tail")
            up = (c1 - c0).normalized()
            fwd = (F - up * F.dot(up)).normalized()
            base = self.bone_world("hips").lerp(c0, 0.5)
            loc = base - fwd * (0.12 * self.H + 0.06)
            return _mat(loc, fwd.cross(up), fwd, up)
        raise ValueError(mode)

    def _prop_step(self, prop, f, f0):
        """Матрица реквизита в кадре f с учётом плавной передачи между режимами (состояние в prop.st)."""
        st = prop.st
        modes = prop.modes
        idx = -1
        for i, m in enumerate(modes):
            if m[0] <= f:
                idx = i
        mode, par = ("world", None) if idx < 0 else (modes[idx][1], modes[idx][2] if len(modes[idx]) > 2 else None)
        if idx != st["idx"]:
            st["from"] = st["last"]
            st["start"] = f if (idx < 0 or modes[idx][0] > f0) else f - prop.blend
            st["idx"] = idx
            if mode == "world" and par is None:
                st["anchor"] = st["last"]
        if mode == "world":
            Mt = st["anchor"] if par is None else par
        else:
            Mt = self.prop_matrix(prop, mode, par, f)
        if Mt is None:
            return None
        k = (f - st["start"]) / max(prop.blend, 1)
        M = _blend(st["from"], Mt, smooth(k)) if k < 1 and st["from"] is not None else Mt
        st["last"] = M
        return M

    # ---------------- запекание
    def bake(self, f0, f1):
        arm = self.arm
        for pb in arm.pose.bones:
            pb.rotation_mode = 'QUATERNION'
        self._gait(f1)
        for m in self.obj.modifiers:
            m.show_viewport = False
        prev = {}
        sc = bpy.context.scene
        for pr in self.props:
            pr.st = {"idx": -2, "from": pr.world0, "last": pr.world0, "anchor": pr.world0, "start": f0}
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            self.pose(f)
            arm.keyframe_insert("location", frame=f)
            arm.keyframe_insert("rotation_euler", frame=f)
            for pb in arm.pose.bones:
                q = pb.rotation_quaternion.copy()
                if pb.name in prev and prev[pb.name].dot(q) < 0:
                    q.negate()
                    pb.rotation_quaternion = q
                prev[pb.name] = q
                pb.keyframe_insert("rotation_quaternion", frame=f)
            for pr in self.props:
                M = self._prop_step(pr, f, f0)
                ob = pr.obj
                if M is None:
                    ob.scale = (0.001, 0.001, 0.001)
                else:
                    ob.matrix_world = M
                    ob.scale = (pr.scale,) * 3
                ob.keyframe_insert("location", frame=f)
                ob.keyframe_insert("rotation_euler", frame=f)
                ob.keyframe_insert("scale", frame=f)
        for m in self.obj.modifiers:
            m.show_viewport = True
        sc.frame_set(f0)


def _mat(loc, x, y, z):
    M = Matrix((x.normalized(), y.normalized(), z.normalized())).transposed().to_4x4()
    M.translation = loc
    return M


def _blend(A, B, t):
    la, ra, _ = A.decompose()
    lb, rb, _ = B.decompose()
    q = ra.slerp(rb, t)
    M = q.to_matrix().to_4x4()
    M.translation = la.lerp(lb, t)
    return M


def ik_dirs(S, T, a, b, pole):
    d = T - S
    L = max(min(d.length, (a + b) * 0.995), abs(a - b) + 1e-4)
    dn = d.normalized()
    ca = max(-1.0, min(1.0, (a * a + L * L - b * b) / (2 * a * L)))
    sa = math.sqrt(max(0.0, 1 - ca * ca))
    p = pole - dn * pole.dot(dn)
    if p.length < 1e-6:
        p = dn.orthogonal()
    p.normalize()
    E = S + dn * a * ca + p * a * sa
    return (E - S).normalized(), (S + dn * L - E).normalized()


def place_world(obj, loc, rot_deg=(0, 0, 0)):
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot_deg]
    bpy.context.view_layer.update()


def glb_default():
    return os.environ.get("GIRL_GLB", r"C:\Users\New\Downloads\Meshy_AI_Chibi_Figure_0926172701_texture.glb")
