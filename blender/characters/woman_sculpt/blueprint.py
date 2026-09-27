"""
Чертёж женщины по референсу: вид спереди и сбоку поверх картинок + уровни + таблица размеров.

  python blueprint.py            → out/blueprint.png, out/blueprint_head.png
"""
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402
from PIL import Image  # noqa: E402

import spec as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "woman_meshy", "reference")
OUT = os.path.join(HERE, "out")
LINE = dict(color="#0050d0", lw=1.3)
LINE2 = dict(color="#d02020", lw=1.1)
LINE3 = dict(color="#108040", lw=1.1)


def backdrop(ax, info, horiz_key):
    img = Image.open(os.path.join(REF, info["file"])).convert("L")
    w, h = img.size
    s, c, sole = info["mm_px"], info[horiz_key], info["sole"]
    ax.imshow(np.asarray(img), cmap="gray", alpha=0.35, extent=[(0 - c) * s, (w - c) * s, (sole - h) * s, sole * s])


def levels(ax, x0, x1, labels=True):
    for name, z in S.LEVELS.items():
        ax.plot([x0, x1], [z, z], color="#999", lw=0.5, ls=":")
        if labels:
            ax.text(x1 + 8, z, f"{name} {z}", fontsize=6.5, va="center", color="#444")


def mirror(ax, xs, zs, **kw):
    ax.plot(xs, zs, **kw)
    ax.plot([-x for x in xs], zs, **kw)


def front(ax):
    backdrop(ax, S.FRONT_IMG, "cx")
    levels(ax, -330, 330)
    # корпус
    mirror(ax, [t[1] for t in S.TORSO], [t[0] for t in S.TORSO], **LINE)
    # кардиган + проём
    cr = S.CARDIGAN["rings"]
    mirror(ax, [r[1] for r in cr], [r[0] for r in cr], **LINE2)
    op = S.CARDIGAN["opening"]
    mirror(ax, [o[1] for o in op], [o[0] for o in op], **LINE2, ls="--")
    mirror(ax, [o[1] + S.CARDIGAN["band_w"] for o in op], [o[0] for o in op], **LINE2, ls=":")
    # ноги
    for sgn in (1, -1):
        ax.plot([sgn * (l[1] + l[2]) for l in S.LEG], [l[0] for l in S.LEG], **LINE)
        ax.plot([sgn * (l[1] - l[2]) for l in S.LEG], [l[0] for l in S.LEG], **LINE)
    # руки: ось и контур рукава
    pts = np.array([a[:3] for a in S.ARM], float)
    rad = np.array([a[3] for a in S.ARM], float)
    for sgn in (1, -1):
        ax.plot(sgn * pts[:, 0], pts[:, 2], color="#0050d0", lw=0.7, ls="-.")
        ax.plot(sgn * (pts[:, 0] + rad), pts[:, 2], **LINE)
        ax.plot(sgn * (pts[:, 0] - rad), pts[:, 2], **LINE)
        wx, _, wz = S.HAND["wrist"]
        ax.add_patch(Ellipse((sgn * wx, wz - S.HAND["length"] / 2), S.HAND["thick"] * 1.3, S.HAND["length"],
                             fill=False, **LINE3))
    head_front(ax)
    ax.set_title("Вид спереди (мм)", fontsize=10)
    ax.set_xlim(-330, 420)
    ax.set_ylim(-20, 1700)
    ax.set_aspect("equal")


def head_front(ax):
    H = S.HEAD
    for key in ("cranium", "face"):
        c, r = H[key]["c"], H[key]["r"]
        ax.add_patch(Ellipse((c[0], c[2]), 2 * r[0], 2 * r[2], fill=False, **LINE3))
    e = H["eyes"]
    for sgn in (1, -1):
        ax.add_patch(Ellipse((sgn * e["x"], e["z"]), 2 * e["r"], 2 * e["r"], fill=False, **LINE3))
        ax.add_patch(Ellipse((sgn * H["cheeks"]["c"][0], H["cheeks"]["c"][2]), 2 * H["cheeks"]["r"],
                             2 * H["cheeks"]["r"], fill=False, color="#108040", lw=0.6, ls=":"))
        bx = np.linspace(*H["brow"]["x"], 12)
        ax.plot(sgn * bx, H["brow"]["z"] + H["brow"]["arch"] * np.sin(np.pi * (bx - bx[0]) / (bx[-1] - bx[0])),
                color="#402010", lw=1.6)
    m = H["mouth"]
    xs = np.linspace(-m["w"] / 2, m["w"] / 2, 30)
    up = m["z"] + m["corner_up"] * (2 * xs / m["w"]) ** 2
    ax.plot(xs, up, **LINE2)
    ax.plot(xs, up - m["open"] * (1 - (2 * xs / m["w"]) ** 2), **LINE2)
    ax.plot([0], [H["nose"]["tip"][2]], "o", color="#108040", ms=3)
    # причёска
    hr = S.HAIR
    t = np.linspace(0, 2 * math.pi, 100)
    zc = (hr["top"] + hr["bottom"]) / 2
    ax.plot(hr["half_w"] * np.cos(t) * (1 - 0.08 * np.sin(t)), zc + (hr["top"] - zc) * np.sin(t),
            color="#805020", lw=1.0, ls="--")


def side(ax):
    backdrop(ax, S.SIDE_IMG, "cy")
    levels(ax, -300, 300, labels=False)
    ax.plot([t[2] for t in S.TORSO], [t[0] for t in S.TORSO], **LINE)
    ax.plot([t[3] for t in S.TORSO], [t[0] for t in S.TORSO], **LINE)
    cr = S.CARDIGAN["rings"]
    ax.plot([r[2] for r in cr], [r[0] for r in cr], **LINE2)
    ax.plot([r[3] for r in cr], [r[0] for r in cr], **LINE2)
    ax.plot([l[4] - l[3] for l in S.LEG], [l[0] for l in S.LEG], **LINE)
    ax.plot([l[4] + l[3] for l in S.LEG], [l[0] for l in S.LEG], **LINE)
    sk = S.SOCK
    ax.add_patch(Ellipse((-sk["foot_len"] / 2 + sk["heel_y"], sk["foot_h"] / 2), sk["foot_len"], sk["foot_h"],
                         fill=False, **LINE3))
    pts = np.array([a[:3] for a in S.ARM], float)
    ax.plot(pts[:, 1], pts[:, 2], color="#0050d0", lw=0.7, ls="-.")
    H = S.HEAD
    for key in ("cranium", "face"):
        c, r = H[key]["c"], H[key]["r"]
        ax.add_patch(Ellipse((c[1], c[2]), 2 * r[1], 2 * r[2], fill=False, **LINE3))
    n = H["nose"]
    ax.plot([n["bridge"][0][1], n["bridge"][1][1]], [n["bridge"][0][2], n["bridge"][1][2]], **LINE3)
    ax.add_patch(Ellipse((n["tip"][1], n["tip"][2]), 2 * n["tip_r"], 2 * n["tip_r"], fill=False, **LINE3))
    e = H["eyes"]
    ax.add_patch(Ellipse((e["y_front"] + e["r"], e["z"]), 2 * e["r"], 2 * e["r"], fill=False, **LINE3))
    ax.add_patch(Ellipse((H["chin"]["c"][1], H["chin"]["c"][2]), 2 * H["chin"]["r"], 2 * H["chin"]["r"],
                         fill=False, **LINE3))
    hr = S.HAIR
    t = np.linspace(0, 2 * math.pi, 100)
    yc, zc = (hr["front_y"] + hr["back_y"]) / 2, (hr["top"] + hr["bottom"]) / 2
    ax.plot(yc + (hr["back_y"] - yc) * np.cos(t), zc + (hr["top"] - zc) * np.sin(t), color="#805020", lw=1.0, ls="--")
    ax.set_title("Вид сбоку, лицо влево (мм)", fontsize=10)
    ax.set_xlim(-300, 300)
    ax.set_ylim(-20, 1700)
    ax.set_aspect("equal")


def table(ax):
    ax.axis("off")
    rows = [("Рост с причёской", "1660"), ("Рост до темени", "1606"), ("Ширина плеч (кардиган)", "350"),
            ("Ширина по кардигану внизу", "380"), ("Ширина бёдер (брюки)", "372"), ("Глубина груди", "210"),
            ("Длина руки плечо–запястье", "≈ 480"), ("Кисть", "175 × 80"), ("Стопа (носок)", "245 × 98"),
            ("Голова: ширина лица", "176"), ("Голова: подбородок–темя", "258"), ("Межзрачковое", "82"),
            ("Глаз (открытие)", "38 × 15,5"), ("Ширина рта (улыбка)", "82"), ("Причёска: ширина", "356"),
            ("Кардиган: полоса борта", "55 × 20"), ("Кардиган: низ", "682 от пола"), ("Брюки: отворот", "150–190")]
    tb = ax.table(cellText=rows, colLabels=("Размер", "мм"), loc="upper center", colWidths=(0.75, 0.25))
    tb.auto_set_font_size(False)
    tb.set_fontsize(7.5)
    tb.scale(1, 1.25)
    ax.text(0.0, 0.02, "синий — тело/брюки/рукава, красный — кардиган и проём,\n"
                       "зелёный — голова, кисти, стопы, коричневый — причёска", fontsize=7, transform=ax.transAxes)


def head_sheet(path):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 6.5))
    front(a1)
    side(a2)
    for a in (a1, a2):
        a.set_ylim(1250, 1700)
    a1.set_xlim(-230, 230)
    a2.set_xlim(-220, 240)
    a1.set_title("Голова спереди (мм)")
    a2.set_title("Голова сбоку (мм)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    fig = plt.figure(figsize=(17, 11))
    gs = fig.add_gridspec(1, 3, width_ratios=(1.25, 1.0, 0.7))
    front(fig.add_subplot(gs[0]))
    side(fig.add_subplot(gs[1]))
    table(fig.add_subplot(gs[2]))
    fig.suptitle("Женщина 50+ — чертёж по референсу (мм). Оси: X влево персонажа, Y назад, Z вверх", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "blueprint.png"), dpi=110)
    plt.close(fig)
    head_sheet(os.path.join(OUT, "blueprint_head.png"))
    print("saved", OUT)


if __name__ == "__main__":
    main()
