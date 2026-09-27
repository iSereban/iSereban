"""
Каталог для детской комнаты и ролика «День девочки» (мм).
Начало — центр основания, фасад в −Y, Z — вверх (как в catalog_furniture).
Мебель — детского размера под персонажа ростом 1,3 м.
"""
import math

from catalog_furniture import B, C, CO, S, spec


# ---------------------------------------------------------------------------
# Мебель
# ---------------------------------------------------------------------------
def kid_desk():
    """Детский письменный стол: столешница 900×520 на высоте 560, тумба с ящиками справа."""
    W, D, Z = 900, 520, 560
    p = [B(W, D, 25, 0, 0, Z - 25, "wood_white", b=4),
         B(22, D - 20, Z - 25, -W / 2 + 11, 0, 0, "wood_white"),
         B(300, D - 20, Z - 25, W / 2 - 150, 0, 0, "wood_white", b=3),
         B(W - 320, 16, 300, -10, D / 2 - 18, Z - 325, "wood_white")]
    for z in (40, 200, 360):
        p.append(B(280, 10, 140, W / 2 - 150, -D / 2 + 5, z, "plastic_pink", b=3))
        p.append(C(10, 14, W / 2 - 150, -D / 2 - 6, z + 70, "chrome", axis="y"))
    return spec("kid_desk", "Детский письменный стол", "Детская", p, "столешница 900×520, высота 560")


def kid_chair():
    """Детский стул: сиденье 340×340 на высоте 320, спинка до 650."""
    p = [B(340, 340, 25, 0, 0, 295, "wood_white", b=4), B(320, 320, 20, 0, -5, 320, "fabric_pink", b=8),
         B(340, 22, 280, 0, 160, 370, "wood_white", b=6)]
    p += [C(14, 295, sx * 145, sy * 145, 0, "wood_white") for sx in (-1, 1) for sy in (-1, 1)]
    p += [C(12, 330, sx * 145, 160, 320, "wood_white") for sx in (-1, 1)]
    return spec("kid_chair", "Детский стул", "Детская", p, "сиденье на высоте 320")


def kid_bed():
    """Кровать 900×1900: изголовье у +Y (к стене), матрас 450."""
    W, L = 900, 1900
    p = [B(W, L, 250, 0, 0, 120, "wood_white", b=6), B(W - 40, L - 40, 160, 0, 0, 290, "pillow_white", b=40),
         B(W + 40, 50, 850, 0, L / 2 + 25, 0, "wood_white", b=10), B(W + 40, 40, 520, 0, -L / 2 - 20, 0, "wood_white", b=10),
         B(W - 20, L * 0.62, 60, 0, -L * 0.16, 440, "fabric_pink", b=25),
         B(W + 30, 700, 30, 0, -L * 0.16, 330, "fabric_pink", b=10),
         S(300, 150, 90, 0, L / 2 - 260, 520, "pillow_white", seg=24)]
    p += [C(25, 120, sx * (W / 2 - 40), sy * (L / 2 - 40), 0, "wood_white") for sx in (-1, 1) for sy in (-1, 1)]
    return spec("kid_bed", "Детская кровать", "Детская", p, "900×1900, матрас 450")


def kid_dresser(mirror=True):
    """Комод 800×400×650 с круглым зеркалом на подставке (mirror=False — без зеркала)."""
    W, D, Hh = 800, 400, 650
    p = [B(W, D, Hh - 60, 0, 0, 60, "wood_white", b=6), B(W + 20, D + 20, 20, 0, 0, Hh, "wood_white", b=4)]
    p += [C(20, 60, sx * (W / 2 - 40), sy * (D / 2 - 40), 0, "wood_white") for sx in (-1, 1) for sy in (-1, 1)]
    for z in (90, 270, 450):
        p.append(B(W - 40, 12, 160, 0, -D / 2 - 2, z, "plastic_pink", b=3))
        p.append(C(12, 16, 0, -D / 2 - 14, z + 80, "chrome", axis="y"))
    if mirror:
        p += kid_mirror(Hh)["parts"]
    return spec("kid_dresser" if mirror else "kid_dresser_body", "Комод с зеркалом" if mirror else "Комод",
                "Детская", p, "800×400, верх 650, зеркало Ø480")


def kid_mirror(z0=650):
    """Круглое зеркало Ø480 на стене над комодом (начало — центр комода на полу, стена — в +Y)."""
    zc = z0 + 460
    p = [C(245, 25, 0, 205, zc, "wood_white", axis="y", seg=48), C(220, 8, 0, 188, zc, "mirror", axis="y", seg=48)]
    return spec("kid_mirror", "Зеркало настенное круглое", "Детская", p, "Ø490, центр на высоте 1110")


def bookshelf_kid():
    W, D, Hh = 700, 300, 1400
    p = [B(W, D, 20, 0, 0, z, "wood_white") for z in (0, 350, 700, 1050, 1380)]
    p += [B(20, D, Hh, sx * (W / 2 - 10), 0, 0, "wood_white") for sx in (-1, 1)]
    p.append(B(W, 10, Hh, 0, D / 2 - 5, 0, "wood_white"))
    cols = ("book_red", "book_blue", "fabric_yellow", "book_green", "plastic_purple", "fabric_pink")
    for k, z in enumerate((20, 370, 720)):
        x, i = -W / 2 + 30, k
        while x < W / 2 - 60:
            w = 25 + (i * 7) % 20
            h = 200 + (i * 37) % 90
            p.append(B(w, 200, h, x + w / 2, 0, z, cols[i % len(cols)]))
            x += w + 3
            i += 1
    p.append(S(70, 60, 70, 150, -10, 1120, "plush_brown", seg=16))
    return spec("bookshelf_kid", "Детский стеллаж с книгами", "Детская", p, "700×300×1400")


def plush_bear():
    p = [S(110, 90, 120, 0, 0, 120, "plush_brown", seg=20), S(80, 75, 75, 0, -10, 290, "plush_brown", seg=20),
         S(28, 18, 28, -55, -10, 350, "plush_brown", seg=12), S(28, 18, 28, 55, -10, 350, "plush_brown", seg=12),
         S(30, 25, 22, 0, -80, 275, "cream", seg=12), S(10, 8, 8, 0, -100, 285, "black_plastic", seg=8),
         S(8, 6, 8, -28, -72, 305, "black_plastic", seg=8), S(8, 6, 8, 28, -72, 305, "black_plastic", seg=8)]
    p += [S(40, 40, 55, sx * 100, -20, 150, "plush_brown", seg=12) for sx in (-1, 1)]
    p += [S(45, 55, 35, sx * 55, -70, 30, "plush_brown", seg=12) for sx in (-1, 1)]
    return spec("plush_bear", "Плюшевый мишка", "Детская", p, "высота 380")


def desk_lamp():
    p = [C(70, 18, 0, 0, 0, "plastic_white"), C(9, 260, 0, 0, 18, "plastic_white"),
         B(18, 200, 18, 0, -95, 270, "plastic_white", rot=[20, 0, 0]),
         CO(70, 35, 90, 0, -190, 210, "plastic_pink"), S(22, 22, 22, 0, -190, 225, "bulb", seg=12)]
    return spec("desk_lamp", "Настольная лампа детская", "Детская", p, "высота 300")


# ---------------------------------------------------------------------------
# Мелкие предметы (реквизит)
# ---------------------------------------------------------------------------
def comb():
    """Расчёска 180×45×8: ручка + спинка + 26 зубцов. Начало — центр, лежит плашмя."""
    p = [B(80, 22, 8, -50, 0, 0, "plastic_pink", b=4), B(100, 12, 8, 40, 12, 0, "plastic_pink", b=3)]
    for i in range(26):
        x = -8 + i * 3.8
        p.append(B(2.2, 22, 6, x, -5, 1, "plastic_pink"))
    return spec("comb", "Расчёска", "Реквизит", p, "180×45×8 мм, 26 зубцов")


def phone():
    """Смартфон 72×150×8, экран вверх (+Z). Начало — центр основания."""
    p = [B(72, 150, 8, 0, 0, 0, "plastic_purple", b=6), B(66, 138, 1, 0, 0, 8, "screen"),
         B(62, 132, 1, 0, 0, 8.6, "screen_on"), C(4, 1, -24, 62, 9, "black_plastic", seg=8)]
    return spec("phone", "Смартфон", "Реквизит", p, "72×150×8 мм")


def backpack():
    """Школьный рюкзак 300×150×380: лямки на стороне +Y (к спине). Начало — центр дна."""
    p = [B(300, 150, 380, 0, 0, 0, "fabric_teal", b=45), B(240, 60, 180, 0, -95, 40, "fabric_yellow", b=25),
         B(250, 8, 6, 0, -125, 225, "chrome"), B(280, 8, 6, 0, -78, 360, "chrome"),
         C(40, 12, 0, 0, 400, "fabric_teal", axis="y", seg=16)]
    for sx in (-1, 1):
        p.append(B(45, 25, 330, sx * 75, 90, 30, "fabric_pink", b=10))
        p.append(B(30, 30, 30, sx * 75, 95, 25, "chrome", b=5))
    p.append(S(35, 12, 35, 60, -130, 120, "fabric_pink", seg=12))            # брелок-сердечко
    return spec("backpack", "Школьный рюкзак", "Реквизит", p, "300×150×380 мм")


def notebook_open():
    """Открытая тетрадь 340×240 (две страницы), корешок по X=0."""
    p = [B(345, 245, 2, 0, 0, 0, "plastic_purple"), B(165, 235, 4, -84, 0, 2, "paper"), B(165, 235, 4, 84, 0, 2, "paper")]
    p += [B(150, 1, 0.5, sx * 84, -100 + i * 12, 6.2, "book_blue") for sx in (-1, 1) for i in range(17)]
    p.append(B(4, 235, 5, 0, 0, 2, "black_plastic"))
    return spec("notebook_open", "Тетрадь (раскрыта)", "Реквизит", p, "340×240 мм, в линейку")


def notebook_closed():
    p = [B(172, 245, 8, 0, 0, 0, "plastic_purple", b=2), S(25, 25, 1, 0, 0, 8, "plastic_pink", seg=12)]
    return spec("notebook_closed", "Тетрадь (закрыта)", "Реквизит", p, "170×240×8 мм")


def textbook():
    p = [B(200, 260, 16, 0, 0, 0, "book_blue", b=2), B(190, 250, 14, 5, 0, 1, "paper"),
         B(120, 60, 1, 0, 30, 16, "fabric_yellow")]
    return spec("textbook", "Учебник", "Реквизит", p, "200×260×16 мм")


def pencil():
    """Карандаш 175 мм вдоль X: шестигранник, заточенный конец в +X, ластик в −X. Начало — центр."""
    p = [C(3.6, 140, 0, 0, 0, "pencil_yellow", axis="x", seg=6),
         {"t": "cone", "r1": 3.6, "r2": 0.6, "h": 20, "p": [80, 0, 0], "m": "wood_light", "seg": 12, "axis": "x"},
         C(3.8, 10, -75, 0, 0, "chrome", axis="x", seg=12), C(3.6, 10, -85, 0, 0, "eraser_pink", axis="x", seg=12)]
    return spec("pencil", "Карандаш", "Реквизит", p, "175×7 мм")


def pencil_cup():
    p = [C(40, 100, 0, 0, 0, "plastic_pink", seg=24)]
    cols = ("pencil_yellow", "book_blue", "book_red", "book_green")
    for i in range(6):
        a = i * math.pi / 3
        p.append({"t": "cyl", "r": 3.5, "h": 170, "p": [22 * math.cos(a), 22 * math.sin(a), 100], "m": cols[i % 4],
                  "axis": "z", "seg": 6, "rot": [8 * math.cos(a), -8 * math.sin(a), 0]})
    return spec("pencil_cup", "Стаканчик с карандашами", "Реквизит", p, "Ø80×100 мм")


CATALOG = {
    "kid_desk": kid_desk, "kid_chair": kid_chair, "kid_bed": kid_bed, "kid_dresser": kid_dresser, "kid_mirror": kid_mirror,
    "bookshelf_kid": bookshelf_kid, "plush_bear": plush_bear, "desk_lamp": desk_lamp,
    "comb": comb, "phone": phone, "backpack": backpack, "notebook_open": notebook_open,
    "notebook_closed": notebook_closed, "textbook": textbook, "pencil": pencil, "pencil_cup": pencil_cup,
}


def get(code, /, **kw):
    return CATALOG[code](**kw)
