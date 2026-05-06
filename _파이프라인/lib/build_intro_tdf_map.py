#!/usr/bin/env python3
"""TDF 강조 인트로 카드 (2안) — 프랑스/유럽 지도의 TDF 코스 + 고도 프로파일.

레이아웃:
- 상단 (1200×500): 프랑스/유럽 지도 + TDF 2025 코스 (주요 스테이지 도시 + 상징 climb)
- 중단 (1200×280): TDF 시즌 전체 고도 프로파일 (Mont Ventoux, Col de la Loze 등 표기)
- 하단 (1200×220): 오늘 라이딩 + Seorak A-race 압축 비교
- 우측 (660×1080): 3계층 시간 비전 (LONG-TERM TDF 강조 · THIS YEAR Seorak · TODAY)

사용법:
    python3 build_intro_tdf_map.py <ride_dir> [output_png]
"""
import sys
import json
import math
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import geopandas as gpd

try:
    import seorak as seorak_mod
except Exception:
    seorak_mod = None

W, H = 1920, 1080

SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
F_REG  = str(FD / 'NanumGothic.ttf')
F_BOLD = str(FD / 'NanumGothicBold.ttf')
F_EX   = str(FD / 'NanumGothicExtraBold.ttf')


def f(p, s):
    return ImageFont.truetype(p, s)


SEA       = (12, 22, 38)
LAND_BG   = (28, 38, 52)
FRANCE    = (52, 70, 100)
FRANCE_HL = (72, 95, 135)
COASTLINE = (110, 140, 180)
BORDER    = (60, 80, 105)
ACCENT    = (255, 184, 76)    # TDF yellow
ACCENT2   = (102, 222, 178)   # green (Seorak)
ACCENT3   = (255, 107, 107)   # red (TDF KOM polka-dot)
ACCENT4   = (140, 200, 255)   # blue (today)
TEXT_MAIN = (245, 248, 252)
TEXT_SUB  = (170, 185, 210)
TEXT_DIM  = (90, 105, 130)
GRID      = (20, 30, 46)


# ───── 상단 TDF 지도 + 중단 고도 + 하단 비교 ─────
LEFT_X0 = 60
LEFT_W  = 1200
GAP     = 12

TDF_MAP_PANEL  = {'x0': LEFT_X0, 'y0': 30,                  'w': LEFT_W, 'h': 500}
TDF_PROF_PANEL = {'x0': LEFT_X0, 'y0': 30 + 500 + GAP,      'w': LEFT_W, 'h': 280}
COMPARE_PANEL  = {'x0': LEFT_X0, 'y0': 30 + 500 + 280 + GAP * 2, 'w': LEFT_W, 'h': 220}


# ───── TDF 2025 — 주요 스테이지 도시 / 상징 climb ─────
# (lat, lon, name, kind)  kind: 'start'/'finish'/'mountain'/'city'
TDF_STAGES = [
    (50.629,  3.057,  'Lille',           'start'),
    (50.726,  1.614,  'Boulogne',        'city'),
    (51.038,  2.377,  'Dunkerque',       'city'),
    (49.443,  1.099,  'Rouen',           'city'),
    (49.183, -0.370,  'Caen',            'city'),
    (48.190, -2.999,  'Mûr-de-Bretagne', 'city'),
    (47.394, -0.553,  'Angers',          'city'),
    (46.812,  1.690,  'Châteauroux',     'city'),
    (45.575,  2.806,  'Le Mont-Dore',    'mountain'),
    (43.605,  1.444,  'Toulouse',        'city'),
    (42.987,  0.037,  'Hautacam',        'mountain'),
    (43.295, -0.371,  'Pau',             'city'),
    (43.213,  2.351,  'Carcassonne',     'city'),
    (44.174,  5.278,  'Mont Ventoux',    'mountain'),
    (44.933,  4.892,  'Valence',         'city'),
    (45.413,  6.633,  'Col de la Loze',  'mountain'),
    (45.510,  6.679,  'La Plagne',       'mountain'),
    (46.907,  6.355,  'Pontarlier',      'city'),
    (48.857,  2.352,  'PARIS',           'finish'),
]


# ───── TDF 2025 고도 프로파일 (대표 데이터 포인트 — km, elevation m) ─────
# 21개 스테이지, 총 ~3,338km, 누적 +52,000m
TDF_ELEVATION = [
    (0, 30),     (30, 60),    (90, 50),    (180, 80),   (270, 120),  (360, 90),
    (450, 60),   (540, 200),  (630, 180),  (720, 250),  (810, 350),  (900, 450),
    (990, 600),  (1080, 850), (1170, 1100),(1260, 1380),(1320, 1635),                        # 11 Hautacam
    (1380, 950), (1450, 1200),(1520, 1480),(1580, 1200),(1640, 350), (1720, 250),            # 12 Loudenvielle ITT, 13 Pau-Superbagnères
    (1800, 500), (1880, 400), (1960, 200), (2040, 150), (2120, 280), (2180, 1200),(2230, 1909),  # 14-16 Mont Ventoux
    (2280, 800), (2340, 350), (2400, 350), (2470, 700), (2530, 1300),(2600, 1900),(2660, 2304),  # 17-18 Col de la Loze
    (2710, 1400),(2760, 1700),(2810, 2050),                                                       # 19 La Plagne
    (2870, 1100),(2940, 750), (3010, 600), (3080, 400), (3150, 250), (3220, 150),(3280, 80),(3338, 35),
]

TDF_CLIMBS = [
    {'km': 1320, 'name': 'Hautacam',         'elev': 1635, 'cat': 'HC'},
    {'km': 2230, 'name': 'Mont Ventoux',     'elev': 1909, 'cat': 'HC'},
    {'km': 2660, 'name': 'Col de la Loze',   'elev': 2304, 'cat': 'HC'},
    {'km': 2810, 'name': 'La Plagne',        'elev': 2050, 'cat': 'HC'},
]


def make_projector(lat_min, lat_max, lon_min, lon_max, x0, y0, w, h, pad=24):
    asp = math.cos(math.radians((lat_min + lat_max) / 2))
    lon_r = (lon_max - lon_min) * asp
    lat_r = (lat_max - lat_min)
    if lon_r <= 0 or lat_r <= 0:
        return None
    scale = min((w - 2 * pad) / lon_r, (h - 2 * pad) / lat_r) * 0.95
    cx = x0 + w / 2
    cy = y0 + h / 2

    def project(lon, lat):
        x = cx + (lon - (lon_min + lon_max) / 2) * asp * scale
        y = cy - (lat - (lat_min + lat_max) / 2) * scale
        return (x, y)
    return project


def draw_country_in_panel(d, gdf, country_name, projector, fill, outline, outline_width=2,
                          name_col='NAME_EN'):
    if name_col not in gdf.columns:
        name_col = 'name'
    rows = gdf[gdf[name_col] == country_name]
    if len(rows) == 0:
        return
    g = rows.geometry.iloc[0]
    polys = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    for p in polys:
        pts = [projector(x, y) for x, y in p.exterior.coords]
        if len(pts) >= 3:
            d.polygon(pts, fill=fill, outline=outline)
            if outline_width > 1:
                d.line(pts + [pts[0]], fill=outline, width=outline_width)


def render_panel(panel, render_fn):
    sub = Image.new('RGB', (panel['w'], panel['h']), SEA)
    sub_d = ImageDraw.Draw(sub)
    for x in range(0, panel['w'], 80):
        sub_d.line([(x, 0), (x, panel['h'])], fill=GRID, width=1)
    for y in range(0, panel['h'], 80):
        sub_d.line([(0, y), (panel['w'], y)], fill=GRID, width=1)
    render_fn(sub, sub_d)
    return sub


def draw_elevation_profile(d, x0, y0, w, h, kms, eles, climbs=None,
                           line_color=ACCENT, fill_color=(255, 184, 76, 80),
                           label_climb_names=False):
    if not kms or not eles or len(kms) != len(eles):
        return
    pad_l, pad_r, pad_t, pad_b = 60, 20, 35, 28
    cx0 = x0 + pad_l
    cy0 = y0 + pad_t
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b

    km_max = max(kms)
    ele_min, ele_max = min(eles), max(eles)
    if km_max <= 0 or ele_max <= ele_min:
        return

    def to_xy(km, ele):
        x = cx0 + (km / km_max) * cw
        y = cy0 + ch - ((ele - ele_min) / (ele_max - ele_min)) * ch
        return (x, y)

    # Y축 + 라벨
    for i in range(5):
        ele_val = ele_min + (ele_max - ele_min) * i / 4
        y = cy0 + ch - ((ele_val - ele_min) / (ele_max - ele_min)) * ch
        d.line([(cx0, y), (cx0 + cw, y)], fill=GRID, width=1)
        d.text((x0 + 6, y - 6), f"{int(ele_val)}m", font=f(F_REG, 11), fill=TEXT_DIM)

    # 산악 음영
    if climbs:
        for c in climbs:
            km = c.get('km')
            if km is None:
                continue
            cx = cx0 + (km / km_max) * cw
            d.rectangle([cx - 8, cy0, cx + 8, cy0 + ch], fill=(70, 35, 50))

    # 폴리곤 + 라인
    pts = [to_xy(km, ele) for km, ele in zip(kms, eles)]
    fill_pts = pts + [(pts[-1][0], cy0 + ch), (pts[0][0], cy0 + ch)]
    d.polygon(fill_pts, fill=fill_color[:3])
    d.line(pts, fill=line_color, width=2)

    # 산악 라벨 (위쪽)
    if climbs and label_climb_names:
        for c in climbs:
            km = c.get('km')
            if km is None:
                continue
            cx = cx0 + (km / km_max) * cw
            label = f"{c['name']} {c['elev']}m ({c['cat']})"
            d.text((cx - 5, cy0 - 18), label, font=f(F_BOLD, 11), fill=ACCENT3)
            cy_peak = cy0 + ch - ((c['elev'] - ele_min) / (ele_max - ele_min)) * ch
            d.ellipse([cx - 4, cy_peak - 4, cx + 4, cy_peak + 4], fill=ACCENT3,
                      outline=TEXT_MAIN)

    # X축
    n_labels = 8
    for i in range(n_labels + 1):
        km_val = km_max * i / n_labels
        x = cx0 + (km_val / km_max) * cw
        d.text((x - 14, cy0 + ch + 6), f"{int(km_val)}km", font=f(F_REG, 11), fill=TEXT_DIM)

    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=(50, 65, 95), width=1)


def panel_border(d, panel):
    x0, y0, w, h = panel['x0'], panel['y0'], panel['w'], panel['h']
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=8, outline=BORDER, width=1)


def extract_gps_from_fit(ride_dir):
    from fitparse import FitFile
    fits = list(Path(ride_dir).glob('*.fit')) + list(Path(ride_dir).glob('*.FIT'))
    if not fits:
        return []
    fit = FitFile(str(fits[0]))
    pts = []
    for r in fit.get_messages('record'):
        d = {f.name: f.value for f in r}
        lat, lon = d.get('position_lat'), d.get('position_long')
        if lat is None or lon is None:
            continue
        ele = d.get('altitude') if d.get('altitude') is not None else d.get('enhanced_altitude')
        pts.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31),
                    d.get('distance', 0), ele or 0))
    return pts


def days_until(target_date_str, today=None):
    target = datetime.fromisoformat(target_date_str).date()
    today = (today or datetime.now()).date()
    return (target - today).days


def load_ride(ride_dir):
    ride = Path(ride_dir)
    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8')) if (ride / 'ride_meta.json').exists() else {}
    return A, M


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_intro_tdf_map.py <ride_dir> [output_png]")
    ride_dir = Path(sys.argv[1])
    out_png = Path(sys.argv[2]) if len(sys.argv) > 2 else ride_dir / 'output_videos' / '_cards' / 'card_intro_tdf.png'
    out_png.parent.mkdir(parents=True, exist_ok=True)

    A, M = load_ride(ride_dir)
    s = A['summary']
    R = A.get('rider', {})
    climbs = A.get('climbs', []) or []
    course_name = M.get('코스명', '') or ride_dir.name.split()[-1]

    today_records = extract_gps_from_fit(ride_dir)
    today_kms = [p[2] / 1000 for p in today_records if p[2] is not None]
    today_eles = [p[3] for p in today_records if p[2] is not None and p[3] is not None]

    NE_DIR = SCRIPT_DIR.parent / 'intro_video' / 'ne_data'
    shp = NE_DIR / 'ne_10m_admin_0_countries.shp'
    if not shp.exists():
        shp = NE_DIR / 'ne_110m_admin_0_countries.shp'
    if not shp.exists():
        sys.exit(f"✗ Natural Earth shapefile 없음: {NE_DIR}")
    gdf = gpd.read_file(shp)
    name_col = 'NAME_EN' if 'NAME_EN' in gdf.columns else 'name'

    seorak_course = None
    if seorak_mod:
        try:
            seorak_course = seorak_mod.load_seorak_course(ride_dir.parent)
        except Exception as e:
            print(f"  ⚠ Seorak GPX 로드 실패: {e}")

    img = Image.new('RGB', (W, H), SEA)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # ─────────────────── 상단: TDF 지도 ───────────────────
    def render_tdf_map(sub, sub_d):
        # 프랑스 + 주변국 보이도록 lat/lon 범위 (south France 42 → north 51, west -5 → east 8)
        pj = make_projector(41.5, 51.5, -5.5, 9.0, 0, 0, TDF_MAP_PANEL['w'], TDF_MAP_PANEL['h'])

        # 주변국 (배경)
        for c in ['Spain', 'Portugal', 'Italy', 'Switzerland', 'Germany',
                  'Belgium', 'Netherlands', 'Luxembourg', 'United Kingdom',
                  'Ireland', 'Andorra', 'Monaco']:
            try:
                draw_country_in_panel(sub_d, gdf, c, pj, LAND_BG, BORDER, 1, name_col)
            except Exception:
                pass
        # 프랑스 강조
        draw_country_in_panel(sub_d, gdf, 'France', pj, FRANCE_HL, COASTLINE, 2, name_col)

        # TDF 스테이지 라인 (글로우)
        track = [pj(lon, lat) for lat, lon, _, _ in TDF_STAGES]
        glow = Image.new('RGBA', (TDF_MAP_PANEL['w'], TDF_MAP_PANEL['h']), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.line(track, fill=ACCENT + (220,), width=10)
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        sub_rgba = sub.convert('RGBA')
        sub_rgba.alpha_composite(glow)
        sub.paste(sub_rgba.convert('RGB'))
        sub_d2 = ImageDraw.Draw(sub)
        sub_d2.line(track, fill=ACCENT, width=3)

        # 스테이지 도시 마커
        for lat, lon, name, kind in TDF_STAGES:
            x, y = pj(lon, lat)
            if kind == 'mountain':
                # 삼각형 (산악)
                sub_d2.polygon([(x, y - 8), (x - 7, y + 5), (x + 7, y + 5)],
                               fill=ACCENT3, outline=TEXT_MAIN)
                sub_d2.text((x + 10, y - 6), name, font=f(F_BOLD, 12), fill=ACCENT3)
            elif kind == 'start':
                sub_d2.ellipse([x - 7, y - 7, x + 7, y + 7], fill=ACCENT2, outline=TEXT_MAIN, width=2)
                sub_d2.text((x + 12, y - 8), f"START · {name}", font=f(F_EX, 14), fill=ACCENT2)
            elif kind == 'finish':
                # 별 (피니시)
                pts = []
                for k in range(10):
                    a = math.pi / 2 + k * math.pi / 5
                    r = 11 if k % 2 == 0 else 5
                    pts.append((x + r * math.cos(a), y - r * math.sin(a)))
                sub_d2.polygon(pts, fill=ACCENT, outline=TEXT_MAIN)
                sub_d2.text((x + 16, y - 10), f"FINISH · {name}", font=f(F_EX, 16), fill=ACCENT)
            else:
                sub_d2.ellipse([x - 3, y - 3, x + 3, y + 3], fill=TEXT_SUB)
                sub_d2.text((x + 6, y - 7), name, font=f(F_REG, 10), fill=TEXT_SUB)

        # 헤더 라벨
        sub_d2.rectangle([0, 0, TDF_MAP_PANEL['w'], 36], fill=(15, 22, 36))
        sub_d2.text((10, 8), "🇫🇷 TOUR DE FRANCE 2025 · 21 stages · 3,338km · +52,000m",
                    font=f(F_EX, 18), fill=ACCENT)
        legend_x = TDF_MAP_PANEL['w'] - 320
        sub_d2.text((legend_x, 11),
                    "● START   ★ FINISH   ▲ HC MOUNTAIN",
                    font=f(F_BOLD, 12), fill=TEXT_SUB)

    tdf_sub = render_panel(TDF_MAP_PANEL, render_tdf_map)
    img.paste(tdf_sub, (TDF_MAP_PANEL['x0'], TDF_MAP_PANEL['y0']))
    panel_border(d, TDF_MAP_PANEL)

    # ─────────────────── 중단: TDF 시즌 고도 프로파일 ───────────────────
    def render_tdf_profile(sub, sub_d):
        chart_w = TDF_PROF_PANEL['w'] - 20
        chart_h = TDF_PROF_PANEL['h'] - 60
        chart_sub = Image.new('RGB', (chart_w, chart_h), (15, 22, 36))
        chart_d = ImageDraw.Draw(chart_sub)
        kms = [p[0] for p in TDF_ELEVATION]
        eles = [p[1] for p in TDF_ELEVATION]
        draw_elevation_profile(chart_d, 0, 0, chart_w, chart_h,
                               kms, eles, TDF_CLIMBS,
                               line_color=ACCENT,
                               fill_color=(255, 184, 76, 80),
                               label_climb_names=True)
        sub.paste(chart_sub, (10, 32))

        sub_d2 = ImageDraw.Draw(sub)
        sub_d2.rectangle([0, 0, TDF_PROF_PANEL['w'], 30], fill=(15, 22, 36))
        sub_d2.text((10, 8), "📈 TDF 2025 · SEASON ELEVATION PROFILE",
                    font=f(F_BOLD, 16), fill=ACCENT)
        sub_d2.text((TDF_PROF_PANEL['w'] - 360, 11),
                    "▲ Hautacam · Ventoux · Loze · La Plagne (HC peaks)",
                    font=f(F_REG, 12), fill=TEXT_DIM)
        sub_d2.rectangle([0, TDF_PROF_PANEL['h'] - 26, TDF_PROF_PANEL['w'], TDF_PROF_PANEL['h']],
                         fill=(15, 22, 36))
        sub_d2.text((10, TDF_PROF_PANEL['h'] - 22),
                    "Pyrenees → Provence → Alps → Paris · 약 6 mountain stages, "
                    "최고점 Col de la Loze 2,304m",
                    font=f(F_REG, 12), fill=TEXT_SUB)

    tdf_prof_sub = render_panel(TDF_PROF_PANEL, render_tdf_profile)
    img.paste(tdf_prof_sub, (TDF_PROF_PANEL['x0'], TDF_PROF_PANEL['y0']))
    panel_border(d, TDF_PROF_PANEL)

    # ─────────────────── 하단: TODAY + Seorak 압축 비교 ───────────────────
    def render_compare(sub, sub_d):
        half_w = (COMPARE_PANEL['w'] - 30) // 2

        # 좌: 오늘 라이딩
        ts_w = half_w
        ts_h = COMPARE_PANEL['h'] - 60
        if today_kms and today_eles:
            chart_sub = Image.new('RGB', (ts_w, ts_h), (15, 22, 36))
            chart_d = ImageDraw.Draw(chart_sub)
            draw_elevation_profile(chart_d, 0, 0, ts_w, ts_h,
                                   today_kms, today_eles, climbs,
                                   line_color=ACCENT4,
                                   fill_color=(140, 200, 255, 80))
            sub.paste(chart_sub, (10, 32))

        # 우: Seorak A-race
        if seorak_course and seorak_course.get('trkpts'):
            race_kms = [p['km'] for p in seorak_course['trkpts']]
            race_eles = [p.get('ele', 0) for p in seorak_course['trkpts']]
            chart_sub2 = Image.new('RGB', (ts_w, ts_h), (15, 22, 36))
            chart_d2 = ImageDraw.Draw(chart_sub2)
            draw_elevation_profile(chart_d2, 0, 0, ts_w, ts_h,
                                   race_kms, race_eles, seorak_course.get('climbs', []),
                                   line_color=ACCENT2,
                                   fill_color=(102, 222, 178, 80))
            sub.paste(chart_sub2, (20 + ts_w, 32))

        sub_d2 = ImageDraw.Draw(sub)
        sub_d2.rectangle([0, 0, COMPARE_PANEL['w'], 30], fill=(15, 22, 36))
        sub_d2.text((10, 8),
                    f"📍 TODAY · {course_name} ({s.get('distance_km', 0)}km · "
                    f"+{s.get('elev_gain_m', 0):,}m)",
                    font=f(F_BOLD, 14), fill=ACCENT4)
        sub_d2.text((20 + ts_w, 8),
                    f"🏆 A-RACE · Seorak GF "
                    f"({seorak_course.get('total_km', 208) if seorak_course else 208:.0f}km · "
                    f"+{seorak_course.get('elev_gain_m', 3800) if seorak_course else 3800:.0f}m)",
                    font=f(F_BOLD, 14), fill=ACCENT2)

    compare_sub = render_panel(COMPARE_PANEL, render_compare)
    img.paste(compare_sub, (COMPARE_PANEL['x0'], COMPARE_PANEL['y0']))
    panel_border(d, COMPARE_PANEL)

    d = ImageDraw.Draw(img)

    # ─────────────────── 우측 패널: 3계층 시간 비전 ───────────────────
    PX = 1295
    PW = 580

    base_dir = ride_dir.parent
    db_path = base_dir / 'athlete_db.json'
    cur_wpk = R.get('w_per_kg', 2.47)
    if db_path.exists():
        try:
            db = json.loads(db_path.read_text(encoding='utf-8'))
            ft = db.get('ftp_trend') or {}
            if ft.get('current_estimated_w_per_kg'):
                cur_wpk = ft['current_estimated_w_per_kg']
        except Exception:
            pass

    # ─ LONG-TERM TDF ─
    d.text((PX, 50), "LONG-TERM · 10년 비전", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 75), "TOUR DE FRANCE", font=f(F_EX, 36), fill=ACCENT)
    d.text((PX, 118), "★ 21 stages · 3,338km · +52,000m",
           font=f(F_REG, 14), fill=TEXT_SUB)
    d.rectangle([PX, 145, PX + PW, 149], fill=ACCENT)

    # W/kg 마일스톤 진척도
    milestones = [
        (2.5, 'Cat 4-5'),
        (3.0, 'Cat 3'),
        (3.5, 'Cat 2'),
        (4.0, 'Cat 1'),
        (4.5, 'Pro/TDF'),
        (5.5, 'GC'),
    ]
    bar_x0, bar_x1 = PX, PX + PW
    bar_y = 190
    bar_h = 6
    d.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], fill=(40, 55, 80))
    progress_pct = min(1.0, max(0, (cur_wpk - 2.0) / (5.5 - 2.0)))
    if progress_pct > 0:
        d.rectangle([bar_x0, bar_y, bar_x0 + int((bar_x1 - bar_x0) * progress_pct),
                     bar_y + bar_h], fill=ACCENT)
    for w, label in milestones:
        ratio = (w - 2.0) / (5.5 - 2.0)
        x = bar_x0 + int((bar_x1 - bar_x0) * ratio)
        achieved = cur_wpk >= w
        col = ACCENT if achieved else TEXT_DIM
        d.ellipse([x - 5, bar_y - 4, x + 5, bar_y + bar_h + 4], fill=col,
                  outline=TEXT_MAIN if achieved else None, width=1)
        d.text((x - 12, bar_y + bar_h + 6), f"{w}", font=f(F_REG, 11), fill=col)
        d.text((x - 22, bar_y + bar_h + 22), label, font=f(F_REG, 10), fill=col)

    cur_x = bar_x0 + int((bar_x1 - bar_x0) * progress_pct)
    d.text((cur_x - 35, bar_y - 28), f"NOW {cur_wpk:.2f}W/kg", font=f(F_BOLD, 13), fill=ACCENT3)
    d.polygon([(cur_x, bar_y - 6), (cur_x - 6, bar_y - 12), (cur_x + 6, bar_y - 12)],
              fill=ACCENT3)

    # ─ THIS YEAR Seorak GF ─
    d.text((PX, 270), "THIS YEAR · 2026 시즌 A-race", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 295), "SEORAK GRANFONDO", font=f(F_EX, 30), fill=ACCENT2)
    d.text((PX, 338), "208km · +3,800m · 2026.06.20", font=f(F_REG, 17), fill=TEXT_SUB)
    d.rectangle([PX, 366, PX + 200, 370], fill=ACCENT2)

    days = days_until('2026-06-20')
    if days >= 0:
        d.text((PX, 380), f"D-{days}", font=f(F_EX, 56), fill=ACCENT3)
        d.text((PX + 195, 403), "남은 일수", font=f(F_REG, 20), fill=TEXT_SUB)
        d.text((PX + 195, 430), "컷오프 12:00@82km / 15:40@167km",
               font=f(F_REG, 13), fill=TEXT_DIM)

    # ─ TODAY ─
    d.text((PX, 495), "TODAY · 오늘의 라이딩", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 520), course_name, font=f(F_EX, 38), fill=TEXT_MAIN)
    d.rectangle([PX, 568, PX + PW, 571], fill=TEXT_MAIN)

    INFO_Y = 588
    d.rounded_rectangle([PX, INFO_Y, PX + PW, INFO_Y + 470], radius=12,
                        fill=(20, 28, 44), outline=(40, 55, 80), width=2)
    specs = [
        ('거리 / 상승',  f"{s.get('distance_km', 0)} km · +{s.get('elev_gain_m', 0):,}m"),
        ('주행 시간',    f"{s.get('moving_h', '?')}"),
        ('평균 속도',    f"{s.get('avg_speed_kmh', 0)} km/h"),
        ('TSS · IF',    f"{s.get('tss', 0)} · {s.get('if_', 0)}"),
        ('Avg / NP',    f"{s.get('avg_power_w', 0)}W / {s.get('np_w', 0)}W"),
        ('평균 HR',      f"{s.get('avg_hr', 0)} bpm"),
        ('케이던스',     f"{s.get('avg_cadence', 0)} rpm"),
        ('디커플링',    f"{s.get('decoupling_pct', 0)}%"),
        ('Climbs',      f"{len(climbs)}개 · VAM 최고 "
                        f"{max((c.get('vam_m_per_h', 0) for c in climbs), default=0):.0f}"),
    ]
    for i, (k, v) in enumerate(specs):
        sy = INFO_Y + 30 + i * 45
        d.text((PX + 25, sy), k, font=f(F_REG, 18), fill=TEXT_SUB)
        d.text((PX + 200, sy), v, font=f(F_BOLD, 18), fill=TEXT_MAIN)

    img.save(out_png, optimize=True)
    print(f"  ✓ {out_png}")
    print(f"  TDF 2025: 21 stages, {len(TDF_STAGES)} key cities, {len(TDF_CLIMBS)} HC peaks")


if __name__ == '__main__':
    main()
