"""
Каталог городских объектов (мм). Начало — центр основания, фасад в −Y, Z — вверх.
"""

import math

from catalog_furniture import B, C, CO, S, T, spec


# ---------------------------------------------------------------------------
# Жилые дома
# ---------------------------------------------------------------------------
def _facade_windows(p, W, face_y, floors, per_floor, z0, floor_h, win_w=1400, win_h=1500, sill=900, lit_every=0,
                    sign=-1):
    """Окна по фасаду: рама + стекло. sign=−1 — фасад в −Y, +1 — в +Y."""
    step = W / per_floor
    k = 0
    for f in range(floors):
        zb = z0 + f * floor_h + sill
        for i in range(per_floor):
            x = -W / 2 + step * (i + 0.5)
            k += 1
            glass = "window_lit" if lit_every and k % lit_every == 0 else "window_dark"
            p.append(B(win_w + 100, 60, win_h + 100, x, face_y + sign * 30, zb - 50, "frame_white"))
            p.append(B(win_w, 60, win_h, x, face_y + sign * 60, zb, glass))
            p.append(B(win_w + 200, 250, 50, x, face_y + sign * 110, zb - 60, "concrete"))


def house_5fl():
    """Кирпичная пятиэтажка, 4 подъезда, 60×12 м."""
    W, D, H, fh = 60000, 12000, 15000, 2800
    p = [B(W, D, H, 0, 0, 0, "brick_white"), B(W + 400, D + 400, 400, 0, 0, H, "roof_dark"),
         B(W + 200, D + 200, 800, 0, 0, 0, "concrete")]
    _facade_windows(p, W, -D / 2, 5, 16, 800, fh, lit_every=7)
    _facade_windows(p, W, D / 2, 5, 16, 800, fh, lit_every=9, sign=1)
    for i in range(4):
        x = -W / 2 + W / 4 * (i + 0.5)
        p += [B(1400, 300, 2300, x, -D / 2 - 100, 800, "sign_brown"), B(2400, 1600, 180, x, -D / 2 - 800, 3300, "concrete"),
              B(2400, 1200, 800, x, -D / 2 - 600, 0, "concrete"), B(700, 60, 250, x, -D / 2 - 170, 3180, "sign_blue"),
              T(str(i + 1), 180, x, -D / 2 - 205, 3305, "sign_text", 10)]
        for f in range(1, 5):
            for dx in (-5000, 5000):
                z = 800 + f * fh
                p += [B(3000, 1100, 150, x + dx, -D / 2 - 550, z, "concrete"),
                      B(3000, 60, 1000, x + dx, -D / 2 - 1070, z + 150, "panel_grey"),
                      B(60, 1100, 1000, x + dx - 1470, -D / 2 - 550, z + 150, "panel_grey"),
                      B(60, 1100, 1000, x + dx + 1470, -D / 2 - 550, z + 150, "panel_grey")]
    return spec("house_5fl", "Пятиэтажка кирпичная (4 подъезда)", "Жилые дома", p, "60×12×15,4 м")


def house_9fl():
    """Панельная девятиэтажка, 3 подъезда, 36×12 м."""
    W, D, H, fh = 36000, 12000, 26000, 2800
    p = [B(W, D, H, 0, 0, 0, "panel_beige"), B(W + 300, D + 300, 500, 0, 0, H, "roof_dark"),
         B(W + 200, D + 200, 800, 0, 0, 0, "concrete")]
    _facade_windows(p, W, -D / 2, 9, 12, 800, fh, win_w=1500, lit_every=5)
    _facade_windows(p, W, D / 2, 9, 12, 800, fh, win_w=1500, lit_every=6, sign=1)
    for i in range(3):
        x = -W / 2 + W / 3 * (i + 0.5)
        p += [B(1500, 300, 2300, x, -D / 2 - 100, 800, "sign_brown"), B(2600, 1600, 180, x, -D / 2 - 800, 3300, "concrete"),
              B(2600, 1200, 800, x, -D / 2 - 600, 0, "concrete"),
              B(1800, 400, 3000, x, 0, H, "panel_grey")]
    return spec("house_9fl", "Девятиэтажка панельная (3 подъезда)", "Жилые дома", p, "36×12×26,5 м")


# ---------------------------------------------------------------------------
# Магазины
# ---------------------------------------------------------------------------
def _shop(name, title, W, D, H, wall, sign_m, text, text_m="sign_text", awning=False, extra=None):
    p = [B(W, D, H, 0, 0, 0, wall), B(W + 300, D + 300, 250, 0, 0, H, "roof_dark"),
         B(W - 2000, 150, 2600, 0, -D / 2 - 40, 300, "frame_white"),
         B(W - 2200, 160, 2400, 0, -D / 2 - 50, 400, "window_lit"),
         B(1600, 200, 2300, W / 2 - 2200, -D / 2 - 60, 300, "glass"),
         B(W - 1000, 400, 1000, 0, -D / 2 - 200, H - 1300, sign_m),
         T(text, 650, 0, -D / 2 - 420, H - 800, text_m, 60),
         B(W + 1000, 2000, 300, 0, -D / 2 - 800, 0, "sidewalk")]
    if awning:
        p.append(B(W - 1600, 1400, 120, 0, -D / 2 - 700, 3000, "awning_red", rot=[-12, 0, 0]))
    p += extra or []
    return spec(name, title, "Магазины", p, f"{W // 1000}×{D // 1000} м")


def shop_produkty():
    return _shop("shop_produkty", "Магазин «Продукты»", 14000, 9000, 4200, "plaster_white", "sign_green", "ПРОДУКТЫ")


def shop_apteka():
    extra = [B(900, 300, 300, 4200, -4800, 3450, "green_light"), B(300, 300, 900, 4200, -4800, 3150, "green_light")]
    return _shop("shop_apteka", "Аптека", 10000, 8000, 4000, "plaster_white", "sign_blue", "АПТЕКА", extra=extra)


def cafe():
    extra = []
    for dx in (-3500, 0, 3500):
        extra += [C(400, 20, dx, -7200, 720, "white"), C(30, 720, dx, -7200, 0, "metal"),
                  C(25, 2300, dx, -7200, 0, "metal"), CO(1300, 50, 500, dx, -7200, 2200, "awning_red")]
        extra += [B(400, 400, 40, dx + sx * 650, -7200, 450, "wood_oak") for sx in (-1, 1)]
    return _shop("cafe", "Кафе «Уют»", 12000, 9000, 4200, "brick_red", "sign_brown", "КАФЕ УЮТ", awning=True, extra=extra)


def bakery():
    return _shop("bakery", "Пекарня «Хлеб»", 9000, 8000, 4000, "plaster_yellow", "sign_brown", "ХЛЕБ", awning=True)


def kiosk():
    p = [B(3000, 2000, 2600, 0, 0, 0, "sign_blue", b=40), B(3300, 2300, 200, 0, 0, 2600, "roof_dark"),
         B(2400, 60, 1200, 0, -1000, 900, "window_lit"), B(2800, 300, 500, 0, -1100, 2700, "white"),
         T("ПРЕССА", 350, 0, -1260, 2950, "sign_blue", 40)]
    return spec("kiosk", "Киоск «Пресса»", "Магазины", p)


# ---------------------------------------------------------------------------
# Улица
# ---------------------------------------------------------------------------
def bus_stop():
    p = [B(4200, 1800, 120, 0, 0, 2500, "roof_dark"), B(4000, 40, 2000, 0, 800, 400, "glass"),
         B(40, 1600, 2000, -1980, 0, 400, "glass"), B(40, 1600, 2000, 1980, 0, 400, "glass")]
    p += [C(50, 2500, sx * 1950, sy * 780, 0, "metal") for sx in (-1, 1) for sy in (-1, 1)]
    p += [B(2500, 400, 50, 0, 500, 450, "wood_oak"), B(40, 400, 450, -1200, 500, 0, "metal"), B(40, 400, 450, 1200, 500, 0, "metal"),
          C(40, 3000, 2600, -700, 0, "metal"), B(600, 40, 600, 2600, -700, 2500, "sign_blue"),
          T("A", 400, 2600, -730, 2800, "sign_text", 10), B(2400, 50, 350, 0, -900, 2550, "sign_blue"),
          T("ОСТАНОВКА", 220, 0, -930, 2725, "sign_text", 10)]
    return spec("bus_stop", "Остановка общественного транспорта", "Улица", p)


def streetlight():
    p = [C(120, 400, 0, 0, 0, "concrete"), CO(90, 60, 8000, 0, 0, 0, "lamp_post"),
         B(1500, 80, 80, -700, 0, 7700, "lamp_post", rot=[0, -8, 0]), B(600, 280, 150, -1400, 0, 7550, "lamp_post", b=40),
         B(500, 240, 20, -1400, 0, 7530, "amber_light")]
    return spec("streetlight", "Фонарь уличный", "Улица", p, "высота 8 м, вылет 1,4 м")


def traffic_light():
    p = [C(70, 3200, 0, 0, 0, "lamp_post"), B(320, 250, 950, 0, -150, 2300, "black_plastic", b=30)]
    for i, m in enumerate(("red_light", "amber_light", "green_light")):
        p.append(C(90, 30, 0, -290, 3050 - i * 300, m, axis="y"))
    return spec("traffic_light", "Светофор", "Улица", p)


def tree(kind="linden"):
    p = []
    if kind == "birch":
        p.append(CO(170, 70, 6000, 0, 0, 0, "plaster_white"))
        crowns = [(0, 0, 5500, 1600, "tree_crown2"), (700, 300, 4600, 1200, "tree_crown2"), (-600, -300, 4800, 1200, "tree_crown")]
    else:
        p.append(CO(250, 120, 4500, 0, 0, 0, "trunk"))
        crowns = [(0, 0, 5600, 2300, "tree_crown"), (1100, 400, 4700, 1600, "tree_crown2"),
                  (-1000, -300, 4900, 1700, "tree_crown"), (200, -900, 4400, 1500, "tree_crown2")]
    for x, y, z, r, m in crowns:
        p.append(S(r, r, r * 0.9, x, y, z, m, seg=14))
    return spec("tree" if kind != "birch" else "tree_birch", "Дерево (липа)" if kind != "birch" else "Берёза", "Улица", p)


def bench():
    p = [B(1800, 450, 40, 0, 0, 430, "wood_oak", b=5), B(1800, 40, 380, 0, 220, 480, "wood_oak", b=5)]
    for sx in (-1, 1):
        p += [B(60, 500, 60, sx * 750, 0, 370, "lamp_post"), B(60, 60, 430, sx * 750, -200, 0, "lamp_post"),
              B(60, 60, 850, sx * 750, 230, 0, "lamp_post")]
    return spec("bench", "Скамейка", "Улица", p)


def trash_bin():
    return spec("trash_bin", "Урна", "Улица", [CO(200, 240, 700, 0, 0, 0, "bin_green"), C(250, 30, 0, 0, 700, "lamp_post")])


def car(color="car_white", name="car_sedan"):
    """Седан. Длина вдоль Y, перед — в −Y."""
    L, W = 4400, 1760
    p = [B(W, L, 620, 0, 0, 300, color, b=110), B(W - 180, 2150, 500, 0, 250, 860, color, b=130),
         B(W - 150, 1950, 400, 0, 250, 900, "window_dark", b=110),
         B(W - 300, 10, 120, 0, -L / 2 - 2, 620, "grey_plastic"),
         B(320, 20, 120, -W / 2 + 250, -L / 2 - 5, 700, "headlight"), B(320, 20, 120, W / 2 - 250, -L / 2 - 5, 700, "headlight"),
         B(300, 20, 100, -W / 2 + 250, L / 2 + 5, 720, "red_light"), B(300, 20, 100, W / 2 - 250, L / 2 + 5, 720, "red_light")]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p += [C(320, 230, sx * (W / 2 - 80), sy * 1350, 320, "tire", axis="x", seg=24),
                  C(190, 240, sx * (W / 2 - 80), sy * 1350, 320, "metal", axis="x", seg=16)]
    return spec(name, "Легковой автомобиль", "Транспорт", p, "длина 4,4 м")


CATALOG = {
    "house_5fl": house_5fl, "house_9fl": house_9fl, "shop_produkty": shop_produkty, "shop_apteka": shop_apteka,
    "cafe": cafe, "bakery": bakery, "kiosk": kiosk, "bus_stop": bus_stop, "streetlight": streetlight,
    "traffic_light": traffic_light, "tree": tree, "tree_birch": lambda: tree("birch"), "bench": bench,
    "trash_bin": trash_bin, "car_sedan": car,
    "car_red": lambda: car("car_red", "car_red"), "car_blue": lambda: car("car_blue", "car_blue"),
    "car_yellow": lambda: car("car_yellow", "car_yellow"),
}


def get(code, /, **kw):
    return CATALOG[code](**kw)
