"""
Каталог мебели и предметов быта для квартиры женщины 50+.

Каждая функция возвращает спецификацию объекта в координатах (мм).
Начало координат — центр основания объекта на полу; фасад смотрит в −Y; Z — вверх.
Настенные/потолочные предметы: начало — точка крепления (стена Y=0 / потолок Z=0).
"""

import math


# ---------------------------------------------------------------------------
# Помощники: z — НИЗ детали (удобно писать), в спецификацию пишется центр
# ---------------------------------------------------------------------------
def B(w, d, h, x, y, z, m, b=0, rot=None):
    p = {"t": "box", "s": [w, d, h], "p": [x, y, z + h / 2], "m": m}
    if b:
        p["b"] = b
    if rot:
        p["rot"] = rot
    return p


def C(r, h, x, y, z, m, axis="z", seg=24):
    """Цилиндр: для axis=z — z низ; для x/y — z центр."""
    zc = z + h / 2 if axis == "z" else z
    return {"t": "cyl", "r": r, "h": h, "p": [x, y, zc], "m": m, "axis": axis, "seg": seg}


def CO(r1, r2, h, x, y, z, m, seg=24):
    return {"t": "cone", "r1": r1, "r2": r2, "h": h, "p": [x, y, z + h / 2], "m": m, "seg": seg}


def S(rx, ry, rz, x, y, z, m, seg=20):
    return {"t": "sph", "s": [rx, ry, rz], "p": [x, y, z], "m": m, "seg": seg}


def T(text, size, x, y, z, m, depth=20):
    return {"t": "text", "text": text, "size": size, "depth": depth, "p": [x, y, z], "m": m}


def spec(name, title, group, parts, note=""):
    return {"name": name, "title": title, "group": group, "parts": parts, "note": note}


def books(x0, x1, y, z, depth, hmax, seed=1):
    """Ряд книг от x0 до x1 на полке с высоты z."""
    cols = ("book_red", "book_blue", "book_green", "book_brown", "cream")
    out, x, i = [], x0, seed
    while x < x1 - 25:
        w = 22 + (i * 7) % 18
        h = hmax - (i * 13) % 60
        out.append(B(w, depth, h, x + w / 2, y, z, cols[i % len(cols)]))
        x += w + 2
        i += 3
    return out


# ---------------------------------------------------------------------------
# Гостиная
# ---------------------------------------------------------------------------
def sofa(color="fabric_burgundy"):
    W, D = 2200, 950
    p = [B(W - 360, 850, 320, 0, 25, 60, color, b=20)]
    for i in (-1, 0, 1):
        p.append(B(600, 660, 160, i * 612, -70, 380, color, b=45))
        p.append(B(600, 190, 430, i * 612, 250, 420, color, b=60))
    p.append(B(W - 360, 180, 540, 0, 385, 360, color, b=30))
    for sx in (-1, 1):
        p.append(B(180, D, 640, sx * (W / 2 - 90), 0, 0, color, b=55))
        p += [C(22, 60, sx * (W / 2 - 120), sy * 380, 0, "wood_walnut") for sy in (-1, 1)]
    p.append(S(190, 70, 190, -W / 2 + 330, 190, 700, "fabric_floral"))
    p.append(S(190, 70, 190, W / 2 - 330, 190, 700, "fabric_floral"))
    return spec("sofa", "Диван трёхместный", "Гостиная", p, "обивка — бордовый велюр")


def armchair(color="fabric_burgundy"):
    W, D = 900, 900
    p = [B(W - 320, 820, 300, 0, 40, 60, color, b=20),
         B(560, 620, 150, 0, -60, 360, color, b=45),
         B(W - 320, 200, 560, 0, 350, 360, color, b=45)]
    for sx in (-1, 1):
        p.append(B(160, D, 620, sx * (W / 2 - 80), 0, 0, color, b=50))
        p += [C(20, 60, sx * (W / 2 - 110), sy * 350, 0, "wood_walnut") for sy in (-1, 1)]
    p.append(B(560, 10, 380, 0, 300, 560, "cream"))    # салфетка на спинке
    return spec("armchair", "Кресло", "Гостиная", p)


def coffee_table():
    p = [B(1000, 600, 30, 0, 0, 450, "wood_walnut", b=6), B(900, 500, 20, 0, 0, 150, "wood_walnut")]
    p += [B(50, 50, 450, sx * 450, sy * 250, 0, "wood_walnut") for sx in (-1, 1) for sy in (-1, 1)]
    p.append(C(200, 3, 0, 0, 480, "cream", seg=32))                     # вязаная салфетка
    p.append(CO(45, 60, 180, 0, 0, 483, "porcelain"))                   # ваза
    p += [S(40, 40, 40, dx, dy, 700, "flower_pink") for dx, dy in ((0, 0), (40, 20), (-35, 25), (10, -40))]
    p += [S(60, 30, 20, dx, dy, 640, "leaf") for dx, dy in ((70, 0), (-70, 10))]
    return spec("coffee_table", "Журнальный столик с вазой", "Гостиная", p)


def wall_unit():
    """«Стенка»: витрина с сервизом, ниша под ТВ, шкаф, книжные полки."""
    W, D, H = 3200, 500, 2300
    p = [B(W, D, 60, 0, 0, 0, "wood_walnut"), B(W, 20, H, 0, D / 2 - 10, 0, "wood_walnut"),
         B(W, D, 30, 0, 0, H - 30, "wood_walnut", b=5), B(W + 40, D + 30, 60, 0, -10, H, "wood_walnut", b=10)]
    for x in (-1600, -800, 400, 1200, 1600):
        p.append(B(24, D, H - 60, x - 12 * (1 if x > 0 else -1), 0, 60, "wood_walnut"))
    # А: витрина с сервизом (−1600…−800)
    xa = -1200
    p.append(B(780, 22, 540, xa, -D / 2 + 11, 60, "wood_walnut", b=4))
    p.append(C(12, 30, xa - 200, -D / 2 - 10, 330, "gold", axis="y"))
    p.append(C(12, 30, xa + 200, -D / 2 - 10, 330, "gold", axis="y"))
    for z in (620, 1000, 1400, 1800):
        p.append(B(760, 420, 8, xa, 20, z, "glass"))
    for z in (628, 1008, 1408):
        for i in range(5):
            p.append(C(105, 10, xa - 280 + i * 140, 150, z + 110, "dishes", axis="y"))
        for i in range(6):
            p.append(C(38, 75, xa - 300 + i * 120, -60, z, "dishes"))
    for i in range(3):
        p.append(S(70, 70, 90, xa - 200 + i * 200, 20, 1808 + 90, "dishes"))  # чайник/сахарницы
    p.append(B(780, 10, 1600, xa, -D / 2 + 5, 620, "glass"))
    # Б: ниша под ТВ (−800…400)
    xb = -200
    p.append(B(1180, D - 30, 500, xb, 0, 60, "wood_walnut", b=3))
    for dx in (-295, 295):
        p.append(B(575, 10, 200, xb + dx, -D / 2 - 5, 320, "wood_walnut", b=3))
        p.append(B(575, 10, 200, xb + dx, -D / 2 - 5, 90, "wood_walnut", b=3))
        p.append(B(120, 14, 14, xb + dx, -D / 2 - 15, 415, "gold"))
        p.append(B(120, 14, 14, xb + dx, -D / 2 - 15, 185, "gold"))
    p.append(B(1180, D - 30, 600, xb, 0, 1670, "wood_walnut", b=3))
    for dx in (-295, 295):
        p.append(B(575, 12, 580, xb + dx, -D / 2 - 6, 1680, "wood_walnut", b=4))
    p.append(C(60, 5, xb + 450, 60, 560, "cream"))
    p.append(CO(35, 55, 160, xb + 450, 60, 565, "porcelain"))            # вазочка
    # В: платяной шкаф (400…1200)
    xc = 800
    for dx in (-197, 197):
        p.append(B(390, 22, 2180, xc + dx, -D / 2 + 11, 70, "wood_walnut", b=5))
        p.append(B(12, 16, 220, xc + dx * 0.08, -D / 2 - 8, 1000, "gold"))
    # Г: открытые полки с книгами (1200…1600)
    xd = 1400
    for z in (60, 480, 900, 1320, 1740):
        p.append(B(380, D - 30, 20, xd, 0, z, "wood_walnut"))
        p += books(xd - 180, xd + 180, 30, z + 20, 220, 300, seed=int(z))
    return spec("wall_unit", "Стенка с сервизом и нишей под ТВ", "Гостиная", p,
                "витрина с сервизом, ниша ТВ, шкаф, книжные полки")


def tv():
    p = [B(400, 240, 20, 0, 0, 0, "black_plastic", b=5), B(80, 50, 70, 0, 20, 20, "black_plastic"),
         B(1100, 55, 660, 0, 0, 80, "black_plastic", b=8), B(1060, 6, 610, 0, -30, 105, "screen")]
    return spec("tv", "Телевизор 43\"", "Гостиная", p)


def floor_lamp():
    p = [C(190, 30, 0, 0, 0, "gold", seg=32), C(13, 1380, 0, 0, 30, "gold"),
         CO(230, 150, 320, 0, 0, 1330, "lampshade", seg=32), S(45, 45, 60, 0, 0, 1450, "bulb")]
    return spec("floor_lamp", "Торшер", "Гостиная", p)


def carpet(w=3000, d=2000, m="carpet_red", name="carpet", title="Ковёр"):
    p = [B(w, d, 8, 0, 0, 0, m), B(w - 120, 20, 9, 0, -d / 2 + 60, 0, "gold"), B(w - 120, 20, 9, 0, d / 2 - 60, 0, "gold"),
         B(20, d - 120, 9, -w / 2 + 60, 0, 0, "gold"), B(20, d - 120, 9, w / 2 - 60, 0, 0, "gold")]
    return spec(name, f"{title} {w // 10}×{d // 10} см", "Текстиль", p)


def plant_ficus():
    p = [CO(170, 220, 360, 0, 0, 0, "terracotta", seg=24), C(200, 10, 0, 0, 340, "soil"), C(22, 800, 0, 0, 350, "trunk")]
    import random
    rng = random.Random(4)
    for i in range(14):
        a = i * 2.4
        r = 120 + rng.random() * 160
        z = 850 + rng.random() * 550
        p.append(S(110, 60, 45, math.cos(a) * r, math.sin(a) * r, z, "leaf" if i % 3 else "leaf_light", seg=12))
    return spec("plant_ficus", "Фикус в кашпо", "Растения", p)


def plant_violet():
    p = [CO(55, 70, 100, 0, 0, 0, "terracotta"), C(62, 5, 0, 0, 95, "soil")]
    for i in range(7):
        a = i * 0.9
        p.append(S(45, 25, 12, math.cos(a) * 45, math.sin(a) * 45, 115, "leaf", seg=10))
    p += [S(14, 14, 14, math.cos(a) * 20, math.sin(a) * 20, 140, "flower_pink", seg=8) for a in (0, 2, 4)]
    return spec("plant_violet", "Фиалка на подоконник", "Растения", p)


def chandelier():
    p = [C(70, 30, 0, 0, -30, "gold"), C(8, 280, 0, 0, -310, "gold"), S(60, 60, 60, 0, 0, -340, "gold")]
    for i in range(5):
        a = i * 2 * math.pi / 5
        x, y = math.cos(a) * 230, math.sin(a) * 230
        p.append(B(230, 14, 14, x / 2, y / 2, -350, "gold", rot=[0, 0, math.degrees(a)]))
        p.append(CO(45, 80, 140, x, y, -390, "lampshade"))
        p.append(S(12, 12, 20, x, y, -410, "glass", seg=8))
    return spec("chandelier", "Люстра пятирожковая", "Свет", p, "крепится к потолку (Z=0 — потолок)")


def ceiling_lamp():
    return spec("ceiling_lamp", "Плафон потолочный", "Свет",
                [C(160, 20, 0, 0, -20, "white"), S(200, 200, 90, 0, 0, -40, "lampshade", seg=24)],
                "крепится к потолку (Z=0 — потолок)")


def table_lamp():
    p = [C(80, 20, 0, 0, 0, "gold"), CO(40, 20, 200, 0, 0, 20, "porcelain"), C(8, 60, 0, 0, 220, "gold"),
         CO(150, 90, 180, 0, 0, 250, "lampshade", seg=24), S(30, 30, 40, 0, 0, 320, "bulb")]
    return spec("table_lamp", "Настольная лампа с абажуром", "Свет", p)


def curtains(w=2000, h=2600, name="curtains"):
    """Тюль + две портьеры на карнизе. Начало — центр окна на стене (Y=0), низ — пол."""
    p = [C(15, w + 400, 0, -120, h + 20, "gold", axis="x"),
         B(w, 12, h - 60, 0, -100, 40, "tulle")]
    for sx in (-1, 1):
        cx = sx * (w / 2 + 50)
        for k in range(6):
            p.append(B(70, 50, h - 50, cx + (k - 2.5) * 55, -150 - (k % 2) * 35, 30, "curtain_heavy", b=20))
    return spec(name, f"Шторы с тюлем (окно {w} мм)", "Текстиль", p, "крепится к стене над окном")


def wall_clock():
    p = [C(160, 45, 0, -22, 0, "wood_walnut", axis="y", seg=32), C(140, 4, 0, -46, 0, "cream", axis="y", seg=32),
         B(8, 4, 100, 0, -50, 0, "black_plastic"), B(70, 4, 8, 30, -50, 0, "black_plastic")]
    return spec("wall_clock", "Часы настенные", "Декор", p, "центр на стене")


def picture(w=600, h=450, m="fabric_floral", name="picture"):
    p = [B(w, 30, h, 0, -15, -h / 2, "gold", b=6), B(w - 80, 32, h - 80, 0, -16, -h / 2 + 40, m)]
    return spec(name, "Картина в раме", "Декор", p, "крепится к стене")


def tea_set():
    p = [S(75, 75, 65, 0, 0, 65, "dishes"), CO(20, 10, 80, 90, 0, 60, "dishes"), C(40, 20, 0, 0, 125, "dishes")]
    for dx in (-160, 160):
        p += [C(70, 8, dx, -60, 0, "dishes"), C(40, 60, dx, -60, 8, "dishes")]
    p.append(C(45, 70, 0, 110, 0, "dishes"))
    return spec("tea_set", "Чайный сервиз на столе", "Кухня", p)


# ---------------------------------------------------------------------------
# Спальня
# ---------------------------------------------------------------------------
def double_bed():
    p = [B(1700, 2100, 280, 0, 0, 150, "wood_cherry", b=10),
         B(1600, 2000, 230, 0, -20, 430, "white", b=40),
         B(1640, 1500, 90, 0, -290, 640, "bedding", b=40),
         B(1700, 300, 30, 0, -1020, 400, "bedding", b=10),
         B(650, 420, 160, -380, 700, 660, "pillow_white", b=70), B(650, 420, 160, 380, 700, 660, "pillow_white", b=70),
         B(1740, 70, 1150, 0, 1015, 0, "wood_cherry", b=15), B(1740, 50, 620, 0, -1035, 0, "wood_cherry", b=10)]
    p += [C(30, 150, sx * 800, sy * 980, 0, "wood_cherry") for sx in (-1, 1) for sy in (-1, 1)]
    return spec("double_bed", "Кровать двуспальная 160×200", "Спальня", p)


def nightstand():
    p = [B(450, 400, 500, 0, 0, 60, "wood_cherry", b=6)]
    p += [C(18, 60, sx * 190, sy * 160, 0, "wood_cherry") for sx in (-1, 1) for sy in (-1, 1)]
    for z in (90, 330):
        p.append(B(410, 10, 200, 0, -205, z, "wood_cherry", b=4))
        p.append(S(15, 15, 15, 0, -220, z + 100, "gold", seg=8))
    p.append(C(170, 3, 0, 0, 560, "cream"))
    return spec("nightstand", "Тумбочка прикроватная", "Спальня", p)


def wardrobe():
    W, D, H = 1800, 600, 2200
    p = [B(W, D, 80, 0, 0, 0, "wood_cherry"), B(W, D, H - 80, 0, 0, 80, "wood_cherry", b=5),
         B(W + 40, D + 30, 60, 0, -15, H, "wood_cherry", b=10)]
    for i, dx in enumerate((-600, 0, 600)):
        p.append(B(590, 12, 2080, dx, -D / 2 - 6, 100, "wood_cherry", b=5))
        if i == 1:
            p.append(B(450, 6, 1700, dx, -D / 2 - 14, 300, "mirror"))
        p.append(B(14, 20, 250, dx + (260 if i != 2 else -260), -D / 2 - 20, 1000, "gold"))
    return spec("wardrobe", "Шкаф платяной с зеркалом", "Спальня", p)


def dresser_mirror():
    p = [B(1000, 450, 700, 0, 0, 60, "wood_cherry", b=6)]
    p += [C(20, 60, sx * 450, sy * 180, 0, "wood_cherry") for sx in (-1, 1) for sy in (-1, 1)]
    for z in (90, 320, 550):
        p.append(B(940, 10, 200, 0, -230, z, "wood_cherry", b=4))
        p.append(B(160, 14, 14, 0, -240, z + 100, "gold"))
    p.append(B(620, 30, 900, 0, 180, 760, "wood_cherry", b=8))
    p.append(B(560, 6, 840, 0, 162, 790, "mirror"))
    for sx in (-1, 1):
        p.append(B(300, 25, 750, sx * 470, 150, 780, "wood_cherry", b=6, rot=[0, 0, -sx * 25]))
        p.append(B(260, 6, 700, sx * 468, 136, 800, "mirror", rot=[0, 0, -sx * 25]))
    p += [C(22, 90, -300 + i * 60, -60, 760, "glass") for i in range(3)]      # флаконы
    p.append(B(180, 120, 90, 300, -40, 760, "wood_walnut", b=10))           # шкатулка
    p.append(C(260, 3, 0, -20, 760, "cream"))
    return spec("dresser_mirror", "Трюмо с зеркалами", "Спальня", p)


def pouf():
    p = [C(220, 380, 0, 0, 60, "fabric_burgundy", seg=32), S(220, 220, 50, 0, 0, 440, "fabric_burgundy", seg=32)]
    p += [C(15, 60, math.cos(a) * 160, math.sin(a) * 160, 0, "gold") for a in (0.8, 2.4, 3.9, 5.5)]
    return spec("pouf", "Пуф", "Спальня", p)


# ---------------------------------------------------------------------------
# Третья комната (рукоделие / гостевая)
# ---------------------------------------------------------------------------
def sofa_bed():
    W, D = 2000, 900
    p = [B(W - 200, 800, 300, 0, 40, 60, "fabric_green", b=20), B(W - 220, 640, 150, 0, -40, 360, "fabric_green", b=40),
         B(W - 200, 220, 500, 0, 330, 360, "fabric_green", b=50)]
    for sx in (-1, 1):
        p.append(B(110, D, 560, sx * (W / 2 - 55), 0, 0, "fabric_green", b=40))
        p += [C(20, 60, sx * (W / 2 - 80), sy * 350, 0, "wood_oak") for sy in (-1, 1)]
    p.append(B(900, 700, 30, -400, -20, 512, "fabric_floral", b=10))     # плед
    p.append(S(180, 70, 180, 650, 150, 650, "pillow_white"))
    return spec("sofa_bed", "Диван-книжка", "Комната 3", p)


def desk():
    p = [B(1200, 600, 30, 0, 0, 720, "wood_oak", b=5), B(420, 560, 700, 380, 0, 20, "wood_oak", b=4),
         B(30, 560, 720, -580, 0, 0, "wood_oak")]
    for z in (60, 290, 510):
        p.append(B(400, 10, 200, 380, -285, z, "wood_oak", b=4))
        p.append(S(14, 14, 14, 380, -300, z + 100, "gold", seg=8))
    p.append(B(1100, 18, 400, -100, 280, 300, "wood_oak"))
    return spec("desk", "Письменный стол с тумбой", "Комната 3", p)


def chair(cushion="fabric_green", name="chair", title="Стул"):
    p = [B(440, 440, 40, 0, 0, 440, "wood_oak", b=5), B(420, 420, 40, 0, -10, 480, cushion, b=15),
         B(440, 30, 460, 0, 205, 480, "wood_oak", b=5)]
    p += [C(16, 440, sx * 190, sy * 190, 0, "wood_oak") for sx in (-1, 1) for sy in (-1, 1)]
    return spec(name, title, "Мебель", p)


def stool():
    p = [B(340, 340, 30, 0, 0, 420, "wood_light", b=5)]
    p += [B(35, 35, 420, sx * 140, sy * 140, 0, "wood_light") for sx in (-1, 1) for sy in (-1, 1)]
    p += [B(280, 20, 20, 0, sy * 140, 150, "wood_light") for sy in (-1, 1)]
    return spec("stool", "Табурет", "Кухня", p)


def sewing_machine():
    p = [B(420, 200, 60, 0, 0, 0, "black_plastic", b=10), B(90, 130, 200, 150, 10, 60, "black_plastic", b=20),
         B(380, 110, 80, 10, 10, 230, "black_plastic", b=25), B(90, 100, 90, -150, 10, 170, "black_plastic", b=15),
         C(8, 60, -165, -20, 130, "chrome"), C(55, 20, 205, 10, 270, "chrome", axis="x", seg=24),
         B(300, 4, 20, 20, -46, 250, "gold")]
    return spec("sewing_machine", "Швейная машинка «Чайка»", "Комната 3", p)


def bookcase():
    W, D, H = 900, 350, 2000
    p = [B(W, D, 60, 0, 0, 0, "wood_oak"), B(W, 15, H, 0, D / 2 - 8, 0, "wood_oak"),
         B(20, D, H, -W / 2 + 10, 0, 0, "wood_oak"), B(20, D, H, W / 2 - 10, 0, 0, "wood_oak"),
         B(W, D, 25, 0, 0, H - 25, "wood_oak")]
    for i, z in enumerate((60, 440, 820, 1200, 1580)):
        p.append(B(W - 40, D - 20, 20, 0, 0, z, "wood_oak"))
        p += books(-W / 2 + 25, W / 2 - 25, 20, z + 20, 220, 300, seed=i * 5 + 1)
    return spec("bookcase", "Книжный шкаф", "Комната 3", p)


# ---------------------------------------------------------------------------
# Кухня
# ---------------------------------------------------------------------------
def kitchen_set(L=3300):
    """Гарнитур вдоль стены: мойка, ящики, плита с духовкой, шкафы; верх с вытяжкой."""
    D = 600
    x0 = -L / 2
    p = [B(L, 500, 100, 0, 30, 0, "black_plastic"), B(L, 560, 760, 0, 20, 100, "white"),
         B(L, D, 40, 0, 0, 860, "wood_light", b=3),
         B(L, 12, 640, 0, D / 2 - 6, 900, "tile_white")]
    # модули низа: (ширина, тип)
    mods = [(800, "sink"), (600, "drawers"), (600, "stove"), (600, "door"), (L - 2600, "door")]
    x = x0
    for w, kind in mods:
        cx = x + w / 2
        if kind == "stove":
            p += [B(w - 4, D - 20, 860, cx, 0, 40, "enamel_white", b=6), B(w - 20, D - 40, 12, cx, 0, 900, "black_plastic"),
                  B(w - 60, 10, 420, cx, -D / 2 - 2, 120, "glass"), B(w - 60, 20, 30, cx, -D / 2 - 12, 600, "chrome")]
            p += [C(75, 10, cx + dx, dy, 912, "black_plastic") for dx in (-140, 140) for dy in (-130, 130)]
            p += [C(20, 25, cx - 200 + i * 100, -D / 2 - 10, 780, "black_plastic", axis="y") for i in range(5)]
        else:
            if kind == "drawers":
                for z in (140, 380, 620):
                    p.append(B(w - 8, 18, 220, cx, -D / 2 + 10, z, "cream", b=4))
                    p.append(B(160, 16, 14, cx, -D / 2 - 5, z + 180, "chrome"))
            else:
                n = 2 if w > 650 else 1
                for k in range(n):
                    dx = (k - (n - 1) / 2) * w / n
                    p.append(B(w / n - 8, 18, 720, cx + dx, -D / 2 + 10, 120, "cream", b=4))
                    p.append(B(14, 16, 160, cx + dx + (w / n / 2 - 60) * (1 if k else -1 if n > 1 else 1), -D / 2 - 5, 700,
                               "chrome"))
            if kind == "sink":
                p += [B(520, 420, 30, cx, 0, 872, "metal"), B(460, 360, 10, cx, 0, 875, "black_plastic"),
                      C(18, 250, cx, 220, 900, "chrome"), B(20, 180, 20, cx, 150, 1130, "chrome")]
        x += w
    # верхние шкафы, над плитой — вытяжка
    stove_cx = x0 + 800 + 600 + 300
    xs = x0
    for w in (800, 600, 600, 600, L - 2600):
        cx = xs + w / 2
        if abs(cx - stove_cx) < 1:
            p += [B(w, 500, 120, cx, 50, 1580, "metal", b=10), B(200, 250, 500, cx, 175, 1700, "metal")]
        else:
            p.append(B(w, 330, 720, cx, D / 2 - 165, 1540, "white"))
            p.append(B(w - 8, 18, 700, cx, D / 2 - 330 - 9, 1550, "cream", b=4))
            p.append(B(14, 16, 160, cx + w / 2 - 60, D / 2 - 345, 1570, "chrome"))
        xs += w
    p.append(B(L, 330, 20, 0, D / 2 - 165, 2260, "wood_light"))
    return spec("kitchen_set", f"Кухонный гарнитур {L} мм", "Кухня", p,
                "мойка 800, ящики 600, плита 600, шкафы; верх — шкафы и вытяжка")


def fridge():
    p = [B(600, 640, 1850, 0, 0, 0, "enamel_white", b=20), B(600, 4, 4, 0, -322, 1250, "grey_plastic"),
         B(22, 30, 300, 260, -335, 1350, "chrome"), B(22, 30, 400, 260, -335, 700, "chrome"),
         B(120, 4, 30, -150, -322, 1780, "chrome")]
    p += [B(40 + i * 20, 5, 40 + (i % 2) * 20, -150 + i * 60, -323, 1500 + (i % 3) * 60, ("sign_red", "sign_blue", "leaf_light")[i % 3])
          for i in range(4)]            # магнитики
    return spec("fridge", "Холодильник двухкамерный", "Кухня", p)


def dining_table():
    p = [B(1100, 700, 30, 0, 0, 720, "wood_oak", b=5), B(1200, 800, 4, 0, 0, 750, "fabric_floral"),
         B(1200, 4, 120, 0, -400, 634, "fabric_floral"), B(1200, 4, 120, 0, 400, 634, "fabric_floral"),
         B(4, 800, 120, -600, 0, 634, "fabric_floral"), B(4, 800, 120, 600, 0, 634, "fabric_floral")]
    p += [B(50, 50, 720, sx * 500, sy * 300, 0, "wood_oak") for sx in (-1, 1) for sy in (-1, 1)]
    return spec("dining_table", "Кухонный стол со скатертью", "Кухня", p)


def microwave():
    p = [B(460, 350, 270, 0, 0, 0, "enamel_white", b=10), B(320, 6, 220, -50, -176, 25, "screen"),
         B(90, 6, 220, 170, -176, 25, "grey_plastic")]
    return spec("microwave", "Микроволновая печь", "Кухня", p)


def kettle():
    p = [S(100, 100, 90, 0, 0, 90, "enamel_red", seg=24), C(95, 20, 0, 0, 0, "enamel_red"),
         S(50, 50, 18, 0, 0, 175, "enamel_white", seg=16), CO(22, 10, 110, 120, 0, 90, "enamel_red"),
         B(160, 18, 18, 0, 0, 210, "black_plastic")]
    return spec("kettle", "Чайник эмалированный", "Кухня", p)


# ---------------------------------------------------------------------------
# Прихожая, ванная, общие элементы квартиры
# ---------------------------------------------------------------------------
def hall_wardrobe():
    p = [B(600, 400, 2100, -300, 0, 0, "wood_oak", b=5), B(590, 12, 2000, -300, -206, 60, "wood_oak", b=5),
         B(14, 16, 200, -60, -218, 1000, "gold"),
         B(600, 350, 400, 300, 25, 0, "wood_oak"), B(600, 20, 1400, 300, 190, 700, "wood_oak"),
         B(600, 300, 20, 300, 50, 1900, "wood_oak")]
    for i in range(5):
        p.append(C(8, 60, 110 + i * 95, 150, 1700, "gold", axis="y"))
    p += [B(380, 180, 900, 200, 60, 800, "fabric_blue", b=60), B(360, 180, 850, 430, 60, 850, "curtain_heavy", b=60)]
    p += [B(260, 110, 100, 180, -80, 400, "black_plastic", b=30), B(260, 110, 100, 440, -80, 400, "sign_brown", b=30)]
    p.append(B(450, 10, 700, 300, 176, 1000, "mirror"))
    return spec("hall_wardrobe", "Прихожая: шкаф, вешалка, полка для обуви, зеркало", "Прихожая", p)


def radiator(sections=10):
    w = sections * 80
    p = [B(70, 90, 560, -w / 2 + 40 + i * 80, 0, 100, "enamel_white", b=15) for i in range(sections)]
    p += [C(18, w + 100, 0, 0, 160, "enamel_white", axis="x"), C(18, w + 100, 0, 0, 600, "enamel_white", axis="x")]
    return spec("radiator", "Батарея чугунная", "Отопление", p, "под окном, отступ от стены 60 мм")


def window(w=1500, h=1500, sill_z=850, name="window"):
    """Окно в проёме: начало — центр проёма внизу по полу, фасад (подоконник) в −Y (в комнату)."""
    f = 70
    z0 = sill_z
    p = [B(w, 80, f, 0, 0, z0, "frame_white"), B(w, 80, f, 0, 0, z0 + h - f, "frame_white"),
         B(f, 80, h, -w / 2 + f / 2, 0, z0, "frame_white"), B(f, 80, h, w / 2 - f / 2, 0, z0, "frame_white"),
         B(f, 80, h - 2 * f, 0, 0, z0 + f, "frame_white"), B(w - 2 * f, 10, h - 2 * f, 0, 0, z0 + f, "glass"),
         B(w + 120, 320, 30, 0, -150, z0 - 30, "white", b=4)]
    return spec(name, f"Окно {w}×{h} с подоконником", "Окна/двери", p)


def door_interior(open_deg=70, name="door_interior"):
    a = math.radians(open_deg)
    hx = -380
    leaf_c = (hx + 380 * math.cos(a), -380 * math.sin(a) - 20)
    p = [B(80, 140, 2080, -440, 0, 0, "wood_light"), B(80, 140, 2080, 440, 0, 0, "wood_light"),
         B(960, 140, 80, 0, 0, 2080, "wood_light"),
         B(760, 40, 2000, leaf_c[0], leaf_c[1], 0, "wood_light", rot=[0, 0, -open_deg]),
         B(380, 42, 900, leaf_c[0], leaf_c[1], 950, "glass", rot=[0, 0, -open_deg])]
    return spec(name, "Дверь межкомнатная 800 со стеклом", "Окна/двери", p, f"открыта на {open_deg}°")


def entrance_door():
    p = [B(100, 160, 2100, -500, 0, 0, "metal"), B(100, 160, 2100, 500, 0, 0, "metal"), B(1100, 160, 100, 0, 0, 2100, "metal"),
         B(900, 60, 2050, 0, -20, 0, "sign_brown", b=8), C(20, 30, 330, -60, 1000, "gold", axis="y"),
         B(40, 20, 160, 330, -60, 1050, "gold"), C(10, 10, 0, -52, 1550, "glass", axis="y")]
    return spec("entrance_door", "Дверь входная металлическая", "Окна/двери", p)


def bathtub():
    p = [B(1700, 750, 560, 0, 0, 0, "enamel_white", b=40), B(1560, 610, 6, 0, 0, 560, "porcelain", b=30),
         B(1500, 560, 4, 0, 0, 520, "glass"),
         C(15, 250, 0, 330, 560, "chrome"), B(20, 200, 20, 0, 250, 810, "chrome"), S(40, 40, 15, 0, 150, 1400, "chrome")]
    return spec("bathtub", "Ванна чугунная 170 см", "Ванная", p)


def washbasin():
    p = [C(90, 650, 0, 60, 0, "porcelain"), B(600, 450, 180, 0, 0, 650, "porcelain", b=50),
         B(480, 330, 6, 0, -20, 830, "white", b=30), C(15, 150, 0, 170, 830, "chrome"), B(20, 120, 20, 0, 120, 960, "chrome"),
         B(500, 120, 700, 0, 170, 1150, "white", b=10), B(460, 6, 600, 0, 108, 1200, "mirror")]
    return spec("washbasin", "Раковина с зеркальным шкафчиком", "Ванная", p)


def toilet():
    p = [CO(150, 180, 380, 0, -60, 0, "porcelain"), S(190, 250, 60, 0, -120, 400, "porcelain", seg=24),
         B(400, 180, 360, 0, 230, 400, "porcelain", b=30), B(60, 30, 20, 0, 230, 770, "chrome")]
    return spec("toilet", "Унитаз с бачком", "Ванная", p)


def washing_machine():
    p = [B(600, 550, 850, 0, 0, 0, "enamel_white", b=15), C(190, 20, -20, -280, 430, "chrome", axis="y", seg=32),
         C(150, 22, -20, -282, 430, "glass", axis="y", seg=32), B(560, 6, 110, 0, -277, 720, "grey_plastic"),
         C(30, 25, 200, -290, 775, "chrome", axis="y")]
    return spec("washing_machine", "Стиральная машина", "Ванная", p)


def rug(w=900, d=600, name="rug", m="carpet_blue"):
    return spec(name, f"Коврик {w // 10}×{d // 10} см", "Текстиль", [B(w, d, 10, 0, 0, 0, m, b=4)])


# ---------------------------------------------------------------------------
CATALOG = {
    "sofa": sofa, "armchair": armchair, "coffee_table": coffee_table, "wall_unit": wall_unit, "tv": tv,
    "floor_lamp": floor_lamp, "carpet": carpet, "plant_ficus": plant_ficus, "plant_violet": plant_violet,
    "chandelier": chandelier, "ceiling_lamp": ceiling_lamp, "table_lamp": table_lamp, "curtains": curtains,
    "wall_clock": wall_clock, "picture": picture, "tea_set": tea_set,
    "double_bed": double_bed, "nightstand": nightstand, "wardrobe": wardrobe, "dresser_mirror": dresser_mirror,
    "pouf": pouf, "sofa_bed": sofa_bed, "desk": desk, "chair": chair, "stool": stool,
    "sewing_machine": sewing_machine, "bookcase": bookcase,
    "kitchen_set": kitchen_set, "fridge": fridge, "dining_table": dining_table, "microwave": microwave,
    "kettle": kettle, "hall_wardrobe": hall_wardrobe, "radiator": radiator, "window": window,
    "door_interior": door_interior, "entrance_door": entrance_door,
    "bathtub": bathtub, "washbasin": washbasin, "toilet": toilet, "washing_machine": washing_machine, "rug": rug,
}


def get(code, /, **kw):
    return CATALOG[code](**kw)
