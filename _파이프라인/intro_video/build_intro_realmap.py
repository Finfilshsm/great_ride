"""인트로 컨셉 B v2 — 실제 지리 데이터 기반 프랑스 지도 + TDF 루트."""
import geopandas as gpd
from shapely.geometry import Point, LineString
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import koreanize_matplotlib
import math

W, H = 1920, 1080
OUT = "/sessions/relaxed-inspiring-mayer/mnt/outputs/intro_mockups"
SHP = "/sessions/relaxed-inspiring-mayer/.local/lib/python3.10/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"

FD = "/sessions/relaxed-inspiring-mayer/.local/lib/python3.10/site-packages/koreanize_matplotlib/fonts"
F_REG  = f"{FD}/NanumGothic.ttf"
F_BOLD = f"{FD}/NanumGothicBold.ttf"
F_EX   = f"{FD}/NanumGothicExtraBold.ttf"
def f(p, s): return ImageFont.truetype(p, s)

# 컬러 팔레트 (실제 지도 톤)
SEA       = (12, 22, 38)         # 짙은 바다
LAND_BG   = (28, 38, 52)         # 다른 국가 (어두움)
FRANCE    = (45, 62, 88)         # 프랑스 (강조)
FRANCE_HL = (62, 82, 115)        # 프랑스 하이라이트
COASTLINE = (90, 115, 155)       # 해안선
BORDER    = (60, 80, 105)        # 국경선

ACCENT     = (255, 184, 76)
ACCENT2    = (102, 222, 178)
ACCENT3    = (255, 107, 107)
TEXT_MAIN  = (245, 248, 252)
TEXT_SUB   = (170, 185, 210)
TEXT_DIM   = (90, 105, 130)
GRID       = (20, 30, 46)

# Natural Earth 데이터 로드
gdf = gpd.read_file(SHP)
NEIGHBORS = ['Spain', 'Portugal', 'Italy', 'Germany', 'Belgium', 'Netherlands',
             'Luxembourg', 'Switzerland', 'Austria', 'United Kingdom', 'Ireland']

# 지도 영역 (프랑스 본토 중심)
MAP_LAT_MIN, MAP_LAT_MAX = 41.0, 51.5
MAP_LON_MIN, MAP_LON_MAX = -5.5, 9.8

# 화면 좌측 절반에 지도 (1100×920)
MAP_X0, MAP_Y0 = 100, 80
MAP_W, MAP_H = 1100, 920

def project(lon, lat):
    asp = 0.72  # cos(46° 위도) 보정
    lon_r = (MAP_LON_MAX - MAP_LON_MIN) * asp
    lat_r = (MAP_LAT_MAX - MAP_LAT_MIN)
    scale = min(MAP_W / lon_r, MAP_H / lat_r) * 0.95
    cx = MAP_X0 + MAP_W / 2
    cy = MAP_Y0 + MAP_H / 2
    x = cx + (lon - (MAP_LON_MIN + MAP_LON_MAX)/2) * asp * scale
    y = cy - (lat - (MAP_LAT_MIN + MAP_LAT_MAX)/2) * scale
    return (x, y)

def polygon_to_pixels(polygon):
    return [project(x, y) for x, y in polygon.exterior.coords]

def draw_country(draw, country_name, fill, outline, outline_width=2):
    rows = gdf[gdf['name'] == country_name]
    if len(rows) == 0: return
    g = rows.geometry.iloc[0]
    polys = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    for p in polys:
        pts = polygon_to_pixels(p)
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill, outline=outline)
            # 외곽선 다시 강조
            if outline_width > 1:
                draw.line(pts + [pts[0]], fill=outline, width=outline_width)

# ───────────────────────────────────────────
# 메인 렌더링
# ───────────────────────────────────────────
img = Image.new('RGB', (W, H), SEA)
d = ImageDraw.Draw(img)

# 격자 (위경도 grid)
for x in range(0, W, 80):
    d.line([(x, 0), (x, H)], fill=GRID, width=1)
for y in range(0, H, 80):
    d.line([(0, y), (W, y)], fill=GRID, width=1)

# 위경도 라벨 (희미하게)
for lon in range(int(MAP_LON_MIN), int(MAP_LON_MAX)+1, 2):
    px, _ = project(lon, MAP_LAT_MAX)
    d.line([(px, MAP_Y0), (px, MAP_Y0+MAP_H)], fill=GRID, width=1)
    if MAP_X0 <= px <= MAP_X0+MAP_W:
        d.text((px+3, MAP_Y0+5), f"{lon}°", font=f(F_REG, 12), fill=TEXT_DIM)
for lat in range(int(MAP_LAT_MIN), int(MAP_LAT_MAX)+1, 2):
    _, py = project(0, lat)
    d.line([(MAP_X0, py), (MAP_X0+MAP_W, py)], fill=GRID, width=1)
    if MAP_Y0 <= py <= MAP_Y0+MAP_H:
        d.text((MAP_X0+5, py-15), f"{lat}°N", font=f(F_REG, 12), fill=TEXT_DIM)

# 주변국가 먼저 (배경)
for n in NEIGHBORS:
    draw_country(d, n, LAND_BG, BORDER, 1)

# 프랑스 (강조) - 그라데이션 효과를 위해 두 번 그리기
# 먼저 하이라이트 (밝게) 채워놓고
draw_country(d, 'France', FRANCE_HL, COASTLINE, 0)

# 프랑스 위에 살짝 어두운 오버레이 (gradient 느낌)
img_rgba = img.convert('RGBA')
overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
france_rows = gdf[gdf['name']=='France']
g = france_rows.geometry.iloc[0]
for p in g.geoms:
    pts = polygon_to_pixels(p)
    if len(pts) >= 3:
        od.polygon(pts, fill=FRANCE+(140,))
img_rgba.alpha_composite(overlay)
img = img_rgba.convert('RGB')
d = ImageDraw.Draw(img)

# 프랑스 해안선 다시 강조 (밝은 톤)
for p in g.geoms:
    pts = polygon_to_pixels(p)
    if len(pts) >= 3:
        d.line(pts + [pts[0]], fill=COASTLINE, width=2)

# 주요 강 (간단히 — 센, 루아르, 론)
RIVERS = [
    # 센강 (파리 → 르 아브르)
    [(2.35, 48.85), (1.0, 48.5), (0.1, 49.5)],
    # 루아르강 (오를레앙 → 낭트 → 대서양)
    [(4.85, 47.0), (3.0, 47.4), (1.5, 47.5), (-1.5, 47.27)],
    # 론강 (제네바 → 리옹 → 마르세유)
    [(5.7, 45.7), (4.84, 45.76), (4.83, 44.0), (4.5, 43.7)],
    # 가론강 (툴루즈 → 보르도)
    [(1.44, 43.6), (0.5, 44.5), (-0.58, 44.84)],
]
RIVER_COLOR = (90, 130, 175)
for river in RIVERS:
    pts = [project(lon, lat) for lon, lat in river]
    d.line(pts, fill=RIVER_COLOR, width=2)

# 산악 지역 (피레네, 알프스) - 산 모양 점 패턴
# 피레네
for lon in [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0]:
    px, py = project(lon, 42.7)
    d.polygon([(px-4, py+3), (px, py-5), (px+4, py+3)], fill=(110, 105, 95), outline=(140, 130, 110))
# 알프스
for lon, lat in [(6.0, 44.5), (6.5, 45.0), (6.8, 45.5), (7.0, 46.0), (6.5, 46.3), (6.0, 45.8)]:
    px, py = project(lon, lat)
    d.polygon([(px-5, py+4), (px, py-6), (px+5, py+4)], fill=(110, 105, 95), outline=(140, 130, 110))

# 바다 라벨
sea_labels = [
    (-3.5, 47.5, "ATLANTIC", 14),
    (4.5, 42.0, "Mediterranean", 14),
    (1.5, 50.5, "English Channel", 12),
    (-3.0, 50.0, "Bay of Biscay", 12),
]
for lon, lat, label, sz in sea_labels:
    px, py = project(lon, lat)
    if MAP_X0 < px < MAP_X0+MAP_W and MAP_Y0 < py < MAP_Y0+MAP_H:
        d.text((px-len(label)*sz//4, py), label, font=f(F_REG, sz), fill=TEXT_DIM)

# TDF 루트
TDF_ROUTE = [
    ("Lille",        50.63,  3.06,  "출발"),
    ("Rouen",        49.44,  1.10,  None),
    ("Rennes",       48.11, -1.68,  None),
    ("Bordeaux",     44.84, -0.58,  None),
    ("Pau",          43.30, -0.37,  "피레네"),
    ("Toulouse",     43.60,  1.44,  None),
    ("Montpellier",  43.61,  3.88,  None),
    ("Marseille",    43.30,  5.40,  None),
    ("Nice",         43.70,  7.27,  None),
    ("Briançon",     44.90,  6.64,  None),
    ("Alpe d'Huez",  45.09,  6.07,  "★ 알프 듀에즈"),
    ("Mont Blanc",   45.83,  6.86,  None),
    ("Grenoble",     45.19,  5.72,  None),
    ("Lyon",         45.76,  4.84,  None),
    ("Dijon",        47.32,  5.04,  None),
    ("Reims",        49.26,  4.03,  None),
    ("Paris",        48.85,  2.35,  "★ 골인"),
]
LEGENDARY = [("Mont Ventoux", 44.17, 5.27), ("Tourmalet", 42.91, 0.14), ("Galibier", 45.06, 6.41)]

# TDF 루트 글로우 (블러)
route_pts = [project(lo, la) for _, la, lo, _ in TDF_ROUTE]
glow = Image.new('RGBA', (W, H), (0,0,0,0))
gd = ImageDraw.Draw(glow)
gd.line(route_pts, fill=ACCENT+(220,), width=14)
glow = glow.filter(ImageFilter.GaussianBlur(8))
img_rgba = img.convert('RGBA')
img_rgba.alpha_composite(glow)
img = img_rgba.convert('RGB')
d = ImageDraw.Draw(img)
d.line(route_pts, fill=ACCENT, width=4)

# 도시 마커 + 라벨
for name, la, lo, special in TDF_ROUTE:
    px, py = project(lo, la)
    if special and "★" in special:
        d.ellipse([px-13, py-13, px+13, py+13], fill=ACCENT, outline=TEXT_MAIN, width=3)
        d.ellipse([px-5, py-5, px+5, py+5], fill=TEXT_MAIN)
    elif special == "출발":
        d.ellipse([px-11, py-11, px+11, py+11], fill=ACCENT2, outline=TEXT_MAIN, width=3)
    elif special == "피레네":
        d.ellipse([px-9, py-9, px+9, py+9], fill=ACCENT3, outline=TEXT_MAIN, width=2)
    else:
        d.ellipse([px-5, py-5, px+5, py+5], fill=TEXT_MAIN, outline=ACCENT, width=1)

    if special:
        color = ACCENT if "★" in special else (ACCENT2 if special == "출발" else ACCENT3)
        size = 22 if "★" in special else 22
        offsets = {"Lille":(15,-5), "Pau":(-110,-5), "Alpe d'Huez":(15,-5), "Paris":(15,-32)}
        ox, oy = offsets.get(name, (15, -10))
        d.text((px+ox, py+oy), name, font=f(F_BOLD, size), fill=color)

# 전설의 클라임
for name, la, lo in LEGENDARY:
    px, py = project(lo, la)
    diamond = [(px, py-9), (px+9, py), (px, py+9), (px-9, py)]
    d.polygon(diamond, fill=ACCENT3, outline=TEXT_MAIN)
    d.text((px+13, py-9), name, font=f(F_REG, 15), fill=TEXT_SUB)

# 우측 패널
PX = 1280
d.text((PX, 100), "ULTIMATE GOAL", font=f(F_REG, 24), fill=TEXT_DIM)
d.text((PX, 135), "TOUR DE FRANCE", font=f(F_EX, 56), fill=ACCENT)
d.rectangle([PX, 220, PX+500, 224], fill=ACCENT)

d.text((PX, 270), "그란폰도 코칭", font=f(F_EX, 64), fill=TEXT_MAIN)
d.text((PX, 355), "Data Ride", font=f(F_EX, 88), fill=ACCENT)

d.rectangle([PX, 470, PX+200, 474], fill=ACCENT2)
d.text((PX, 500), "Big Ride", font=f(F_EX, 72), fill=ACCENT2)

d.text((PX, 605), "데이터로 보는 라이딩의 모든 것", font=f(F_REG, 32), fill=TEXT_SUB)
d.text((PX, 650), "Power · HR · Pacing · Nutrition · Recovery", font=f(F_REG, 22), fill=TEXT_DIM)

# TDF 정보 박스
INFO_Y = 760
d.rounded_rectangle([PX, INFO_Y, PX+500, INFO_Y+220], radius=12, fill=(20,28,44), outline=(40,55,80), width=2)
d.text((PX+25, INFO_Y+20), "Tour de France", font=f(F_BOLD, 24), fill=ACCENT)
specs = [
    ("총 거리",    "약 3,400 km"),
    ("스테이지",  "21일 (총 23일)"),
    ("총 상승",    "약 50,000 m"),
    ("최고점",     "Col du Galibier (2,642m)"),
]
for i, (k, v) in enumerate(specs):
    sy = INFO_Y + 65 + i * 36
    d.text((PX+25, sy), k, font=f(F_REG, 20), fill=TEXT_SUB)
    d.text((PX+170, sy), v, font=f(F_BOLD, 20), fill=TEXT_MAIN)

# 좌측 코너 라벨
d.text((MAP_X0, MAP_Y0-40), "FRANCE", font=f(F_REG, 18), fill=TEXT_DIM)
d.line([(MAP_X0, MAP_Y0-15), (MAP_X0+80, MAP_Y0-15)], fill=ACCENT, width=2)
d.text((MAP_X0+95, MAP_Y0-32), "Source: Natural Earth", font=f(F_REG, 11), fill=TEXT_DIM)

# 범례
LEG_Y = H - 200
d.rounded_rectangle([MAP_X0, LEG_Y, MAP_X0+440, LEG_Y+170], radius=10, fill=(15,22,36), outline=(35,48,72), width=1)
d.text((MAP_X0+15, LEG_Y+15), "Legend", font=f(F_BOLD, 16), fill=TEXT_DIM)
items = [
    (ACCENT, "주요 스테이지 도시"),
    (ACCENT2, "출발 (Lille)"),
    (ACCENT3, "전설의 클라임"),
    (RIVER_COLOR, "주요 강 (Seine·Loire·Rhône·Garonne)"),
]
for i, (col, label) in enumerate(items):
    ly = LEG_Y + 45 + i * 28
    if isinstance(col, tuple) and len(col) == 3 and label.startswith("주요 강"):
        d.line([(MAP_X0+20, ly+7), (MAP_X0+34, ly+7)], fill=col, width=2)
    else:
        d.ellipse([MAP_X0+20, ly, MAP_X0+34, ly+14], fill=col)
    d.text((MAP_X0+50, ly-2), label, font=f(F_REG, 17), fill=TEXT_MAIN)

img.save(f"{OUT}/intro_B_TDF_realmap.png", optimize=True)
print(f"실제 지도 기반 인트로 PNG 생성 완료")
