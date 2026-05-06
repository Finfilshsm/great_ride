#!/usr/bin/env python3
"""한국 지도 + 오늘 라이딩 + Seorak GF 3개 지도 + 3계층 시간 비전 인트로.

레이아웃:
- 좌상 (1200×340): KOREA 전체 지도 (오늘/Seorak 위치 box 표시)
- 좌중 (1200×340): TODAY — 오늘 라이딩 GPS 트랙 줌인 (climb 마커 포함)
- 좌하 (1200×340): A-RACE — Seorak GF 208km 코스 (waypoints + climbs)
- 우 (660×1080): 3계층 시간 비전 (LONG-TERM TDF · THIS YEAR Seorak · TODAY 라이딩)

사용법:
    python3 build_intro_korea_map.py <ride_dir> [output_png]
"""
import sys
import os
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


# 컬러 팔레트
SEA       = (12, 22, 38)
LAND_BG   = (28, 38, 52)
KOREA     = (45, 62, 88)
KOREA_HL  = (62, 82, 115)
COASTLINE = (90, 115, 155)
BORDER    = (60, 80, 105)
ACCENT    = (255, 184, 76)
ACCENT2   = (102, 222, 178)
ACCENT3   = (255, 107, 107)
TEXT_MAIN = (245, 248, 252)
TEXT_SUB  = (170, 185, 210)
TEXT_DIM  = (90, 105, 130)
GRID      = (20, 30, 46)


# ───── 좌측 3개 지도 영역 ─────
LEFT_X0 = 60
LEFT_W = 1200
PANEL_H = 340
PANEL_GAP = 15

KOREA_PANEL = {'x0': LEFT_X0, 'y0': 30,                     'w': LEFT_W, 'h': PANEL_H}
TODAY_PANEL = {'x0': LEFT_X0, 'y0': 30 + PANEL_H + PANEL_GAP,           'w': LEFT_W, 'h': PANEL_H}
RACE_PANEL  = {'x0': LEFT_X0, 'y0': 30 + (PANEL_H + PANEL_GAP) * 2,     'w': LEFT_W, 'h': PANEL_H}


def make_projector(lat_min, lat_max, lon_min, lon_max, x0, y0, w, h, pad=20):
    """주어진 경위도 범위 → 패널 내부 좌표 (sub-image local 좌표).

    x0, y0는 sub-image 안에서 지도 영역 시작 위치.
    """
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


def draw_elevation_profile(d, x0, y0, w, h, kms, eles, climbs=None, line_color=ACCENT, fill_color=(255, 184, 76, 80)):
    """고도 단면도 차트.
    kms, eles: 시계열 거리(km)·고도(m) 리스트.
    climbs: [{'start_km', 'end_km' or distance_m, 'index', 'category'}] — 음영 + 라벨
    """
    if not kms or not eles or len(kms) != len(eles):
        return
    pad_l = 50  # Y축 라벨 공간
    pad_r = 10
    pad_t = 25
    pad_b = 22  # X축 라벨 공간
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

    # Y축 격자 + 고도 라벨
    for i in range(4):
        ele_val = ele_min + (ele_max - ele_min) * i / 3
        y = cy0 + ch - ((ele_val - ele_min) / (ele_max - ele_min)) * ch
        d.line([(cx0, y), (cx0 + cw, y)], fill=GRID, width=1)
        d.text((x0 + 5, y - 6), f"{int(ele_val)}m", font=f(F_REG, 10), fill=TEXT_DIM)

    # Climb 음영
    if climbs:
        for c in climbs:
            start_km = c.get('start_km')
            if start_km is None:
                continue
            end_km = c.get('end_km')
            if end_km is None:
                end_km = start_km + (c.get('distance_m', 0) or 0) / 1000
            x1 = cx0 + (start_km / km_max) * cw
            x2 = cx0 + (end_km / km_max) * cw
            # 반투명 빨강
            overlay = Image.new('RGBA', (max(1, int(x2 - x1)), int(ch)), (255, 107, 107, 50))
            # 직접 그리기 어려우니 그냥 outline + light fill
            d.rectangle([x1, cy0, x2, cy0 + ch], fill=(60, 35, 50), outline=None)

    # 고도 단면 polygon (fill)
    pts = [to_xy(km, ele) for km, ele in zip(kms, eles)]
    fill_pts = pts + [(pts[-1][0], cy0 + ch), (pts[0][0], cy0 + ch)]
    d.polygon(fill_pts, fill=fill_color[:3])
    # 라인
    d.line(pts, fill=line_color, width=2)

    # X축 km 라벨
    n_labels = 5
    for i in range(n_labels + 1):
        km_val = km_max * i / n_labels
        x = cx0 + (km_val / km_max) * cw
        d.text((x - 12, cy0 + ch + 4), f"{int(km_val)}km", font=f(F_REG, 10), fill=TEXT_DIM)

    # Climb 인덱스/카테고리 라벨 (위쪽)
    if climbs:
        for c in climbs:
            start_km = c.get('start_km')
            if start_km is None:
                continue
            x = cx0 + (start_km / km_max) * cw
            idx = c.get('index', '?')
            cat = c.get('category', '')
            label = cat if cat and cat != 'NC' else f"#{idx}"
            d.text((x - 10, cy0 + 2), label, font=f(F_BOLD, 10), fill=ACCENT3)

    # 차트 외곽 박스
    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=(50, 65, 95), width=1)
    # "고도 프로파일" 라벨
    d.text((cx0, y0 + 3), "고도 프로파일 (Elevation)", font=f(F_BOLD, 12), fill=TEXT_SUB)


def render_map_panel(panel, render_fn):
    """패널 sub-image 생성 → render_fn(sub_img, sub_draw)에서 그림 그리기 → return sub_image.

    sub_image는 panel 크기. 좌표는 (0,0) 기준 local.
    """
    sub = Image.new('RGB', (panel['w'], panel['h']), SEA)
    sub_d = ImageDraw.Draw(sub)
    # 격자
    for x in range(0, panel['w'], 80):
        sub_d.line([(x, 0), (x, panel['h'])], fill=GRID, width=1)
    for y in range(0, panel['h'], 80):
        sub_d.line([(0, y), (panel['w'], y)], fill=GRID, width=1)
    render_fn(sub, sub_d)
    return sub


def panel_border(d, panel, label_left, label_right=None):
    """패널 경계 + 라벨."""
    x0, y0, w, h = panel['x0'], panel['y0'], panel['w'], panel['h']
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=8, outline=BORDER, width=1)
    d.text((x0 + 10, y0 + 8), label_left, font=f(F_BOLD, 16), fill=ACCENT)
    if label_right:
        bb = d.textbbox((0, 0), label_right, font=f(F_REG, 12))
        d.text((x0 + w - (bb[2] - bb[0]) - 10, y0 + 11), label_right,
               font=f(F_REG, 12), fill=TEXT_DIM)


def draw_country_in_panel(d, gdf, country_name, projector, fill, outline, outline_width=2, name_col='NAME_EN'):
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


def clip_in_panel(pts, panel):
    """패널 영역 안에 있는 점만 필터."""
    x0, y0, w, h = panel['x0'], panel['y0'], panel['w'], panel['h']
    return [(x, y) for x, y in pts if x0 <= x <= x0 + w and y0 <= y <= y0 + h]


def extract_gps_from_fit(ride_dir):
    """라이딩 폴더의 .fit에서 GPS·거리·고도 추출. (lat, lon, dist_m, ele_m)"""
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


def find_climb_gps(records, target_d_m):
    """주어진 거리(미터)에 가장 가까운 GPS 좌표 찾기."""
    best = None
    best_diff = float('inf')
    for rec in records:
        lat, lon, d = rec[0], rec[1], rec[2]
        if d is None:
            continue
        diff = abs(d - target_d_m)
        if diff < best_diff:
            best_diff = diff
            best = (lat, lon)
        if diff < 50:
            return best
    return best


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
        sys.exit("사용법: build_intro_korea_map.py <ride_dir> [output_png]")
    ride_dir = Path(sys.argv[1])
    out_png = Path(sys.argv[2]) if len(sys.argv) > 2 else ride_dir / 'output_videos' / '_cards' / 'card_intro_korea.png'
    out_png.parent.mkdir(parents=True, exist_ok=True)

    A, M = load_ride(ride_dir)
    s = A['summary']
    R = A.get('rider', {})
    climbs = A.get('climbs', []) or []
    course_name = M.get('코스명', '') or ride_dir.name.split()[-1]

    # 오늘 GPS 트랙
    today_records = extract_gps_from_fit(ride_dir)
    today_lats = [p[0] for p in today_records]
    today_lons = [p[1] for p in today_records]
    today_kms = [p[2] / 1000 for p in today_records if p[2] is not None]
    today_eles = [p[3] for p in today_records if p[2] is not None and p[3] is not None]

    # Natural Earth shapefile
    NE_DIR = SCRIPT_DIR.parent / 'intro_video' / 'ne_data'
    shp = NE_DIR / 'ne_10m_admin_0_countries.shp'
    if not shp.exists():
        shp = NE_DIR / 'ne_110m_admin_0_countries.shp'
    if not shp.exists():
        sys.exit(f"✗ Natural Earth shapefile 없음: {NE_DIR}")
    gdf = gpd.read_file(shp)

    name_col = 'NAME_EN' if 'NAME_EN' in gdf.columns else 'name'
    country_kr = 'South Korea' if (gdf[name_col] == 'South Korea').any() else 'Korea, South'

    # Seorak GF 코스 (athlete_db 부모 폴더에 GPX)
    seorak_course = None
    if seorak_mod:
        try:
            seorak_course = seorak_mod.load_seorak_course(ride_dir.parent)
        except Exception as e:
            print(f"  ⚠ Seorak GPX 로드 실패: {e}")

    img = Image.new('RGB', (W, H), SEA)
    d = ImageDraw.Draw(img)

    # 전체 배경 격자
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # ─────────────────── 좌상: KOREA 전체 (sub-image) ───────────────────
    def render_korea(sub, sub_d):
        pj = make_projector(33.5, 38.8, 125.5, 130.0,
                            0, 0, KOREA_PANEL['w'], KOREA_PANEL['h'])
        for c in ['North Korea', 'China', 'Japan', 'Russia']:
            try:
                draw_country_in_panel(sub_d, gdf, c, pj, LAND_BG, BORDER, 1, name_col)
            except Exception:
                pass
        draw_country_in_panel(sub_d, gdf, country_kr, pj, KOREA_HL, COASTLINE, 2, name_col)

        # 오늘 위치 box
        if today_lats:
            lat_lo, lat_hi = min(today_lats), max(today_lats)
            lon_lo, lon_hi = min(today_lons), max(today_lons)
            pad_lat = (lat_hi - lat_lo) * 0.6 + 0.05
            pad_lon = (lon_hi - lon_lo) * 0.6 + 0.05
            x0p, y0p = pj(lon_lo - pad_lon, lat_hi + pad_lat)
            x1p, y1p = pj(lon_hi + pad_lon, lat_lo - pad_lat)
            sub_d.rectangle([x0p, y0p, x1p, y1p], outline=ACCENT, width=2)
            sub_d.text((x1p + 5, y0p), "TODAY", font=f(F_BOLD, 11), fill=ACCENT)

        # Seorak 위치 box
        if seorak_course and seorak_course.get('trkpts'):
            s_lats = [p['lat'] for p in seorak_course['trkpts']]
            s_lons = [p['lon'] for p in seorak_course['trkpts']]
            sx0, sy0 = pj(min(s_lons) - 0.05, max(s_lats) + 0.05)
            sx1, sy1 = pj(max(s_lons) + 0.05, min(s_lats) - 0.05)
            sub_d.rectangle([sx0, sy0, sx1, sy1], outline=ACCENT2, width=2)
            sub_d.text((sx0, sy0 - 14), "A-RACE", font=f(F_BOLD, 11), fill=ACCENT2)

        # 라벨
        sub_d.text((10, 8), "🌏 KOREA · 전체 컨텍스트", font=f(F_BOLD, 16), fill=ACCENT)
        sub_d.text((KOREA_PANEL['w'] - 130, 11), "Natural Earth", font=f(F_REG, 11), fill=TEXT_DIM)

    korea_sub = render_map_panel(KOREA_PANEL, render_korea)
    img.paste(korea_sub, (KOREA_PANEL['x0'], KOREA_PANEL['y0']))

    # ─────────────────── 좌중: TODAY (좌:고도프로파일 + 우:지도) ───────────────────
    def render_today(sub, sub_d):
        if not today_lats:
            sub_d.text((20, 20), "GPS 데이터 없음", font=f(F_REG, 18), fill=TEXT_DIM)
            return

        # ── 좌측 절반: 고도 프로파일 (별도 sub) ──
        chart_w = TODAY_PANEL['w'] // 2 - 20
        chart_h = TODAY_PANEL['h'] - 60
        chart_sub = Image.new('RGB', (chart_w, chart_h), (15, 22, 36))
        chart_d = ImageDraw.Draw(chart_sub)
        if today_kms and today_eles:
            draw_elevation_profile(chart_d, 0, 0, chart_w, chart_h,
                                   today_kms, today_eles, climbs)
        sub.paste(chart_sub, (10, 32))

        # ── 우측 절반: 지도 (별도 sub) ──
        map_x = TODAY_PANEL['w'] // 2 + 10
        map_w = TODAY_PANEL['w'] - map_x - 10
        map_h = TODAY_PANEL['h'] - 60
        map_sub = Image.new('RGB', (map_w, map_h), SEA)
        map_d = ImageDraw.Draw(map_sub)

        lat_pad = (max(today_lats) - min(today_lats)) * 0.15 + 0.005
        lon_pad = (max(today_lons) - min(today_lons)) * 0.15 + 0.005
        pj = make_projector(min(today_lats) - lat_pad, max(today_lats) + lat_pad,
                            min(today_lons) - lon_pad, max(today_lons) + lon_pad,
                            0, 0, map_w, map_h)
        # 한국 outline 배경
        # 격자 (map_sub)
        for x in range(0, map_w, 60):
            map_d.line([(x, 0), (x, map_h)], fill=GRID, width=1)
        for y in range(0, map_h, 60):
            map_d.line([(0, y), (map_w, y)], fill=GRID, width=1)
        draw_country_in_panel(map_d, gdf, country_kr, pj, KOREA_HL, COASTLINE, 1, name_col)

        # GPS 트랙 + 글로우
        track_pts = [pj(lo, la) for la, lo in zip(today_lats, today_lons)]
        glow = Image.new('RGBA', (map_w, map_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.line(track_pts, fill=ACCENT + (220,), width=8)
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        map_rgba = map_sub.convert('RGBA')
        map_rgba.alpha_composite(glow)
        map_sub.paste(map_rgba.convert('RGB'))
        map_d2 = ImageDraw.Draw(map_sub)
        map_d2.line(track_pts, fill=ACCENT, width=3)

        # Start/End
        map_d2.ellipse([track_pts[0][0] - 8, track_pts[0][1] - 8,
                        track_pts[0][0] + 8, track_pts[0][1] + 8],
                       fill=ACCENT2, outline=TEXT_MAIN, width=2)
        map_d2.ellipse([track_pts[-1][0] - 8, track_pts[-1][1] - 8,
                        track_pts[-1][0] + 8, track_pts[-1][1] + 8],
                       fill=ACCENT3, outline=TEXT_MAIN, width=2)

        # Climb 마커
        for c in climbs:
            target_d = (c.get('start_km', 0) or 0) * 1000
            gp = find_climb_gps(today_records, target_d)
            if not gp:
                continue
            cx, cy = pj(gp[1], gp[0])
            if not (0 <= cx <= map_w and 0 <= cy <= map_h):
                continue
            diamond = [(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)]
            map_d2.polygon(diamond, fill=ACCENT3, outline=TEXT_MAIN)
            map_d2.text((cx + 10, cy - 8), f"#{c.get('index', '?')}",
                        font=f(F_BOLD, 12), fill=ACCENT3)

        sub.paste(map_sub, (map_x, 32))
        sub_d2 = ImageDraw.Draw(sub)

        # 라벨 (배경 박스 위에 그리기 위해 마지막에)
        sub_d2.rectangle([0, 0, TODAY_PANEL['w'], 30], fill=(15, 22, 36, 200))
        sub_d2.text((10, 8), f"📍 TODAY · {course_name} "
                    f"({s.get('distance_km', 0)}km · +{s.get('elev_gain_m', 0):,}m)",
                    font=f(F_BOLD, 16), fill=ACCENT)
        # 아래쪽 통계
        max_vam = max((c.get('vam_m_per_h', 0) for c in climbs), default=0)
        sub_d2.rectangle([0, TODAY_PANEL['h'] - 26, TODAY_PANEL['w'], TODAY_PANEL['h']],
                         fill=(15, 22, 36, 200))
        sub_d2.text((10, TODAY_PANEL['h'] - 22),
                    f"TSS {s.get('tss', 0)} · IF {s.get('if_', 0)} · "
                    f"NP {s.get('np_w', 0)}W · 디커플링 {s.get('decoupling_pct', 0)}% · "
                    f"VAM 최고 {max_vam:.0f}",
                    font=f(F_REG, 12), fill=TEXT_SUB)

    today_sub = render_map_panel(TODAY_PANEL, render_today)
    img.paste(today_sub, (TODAY_PANEL['x0'], TODAY_PANEL['y0']))

    # ─────────────────── 좌하: A-RACE (좌:고도프로파일 + 우:코스 지도) ───────────────────
    def render_race(sub, sub_d):
        if not (seorak_course and seorak_course.get('trkpts')):
            sub_d.text((20, 100), "Seorak GPX 파일이 데이터 폴더에 없음",
                       font=f(F_REG, 18), fill=TEXT_DIM)
            return

        # ── 좌측 절반: 고도 프로파일 ──
        race_kms = [p['km'] for p in seorak_course['trkpts']]
        race_eles = [p.get('ele', 0) for p in seorak_course['trkpts']]
        chart_w = RACE_PANEL['w'] // 2 - 20
        chart_h = RACE_PANEL['h'] - 60
        chart_sub = Image.new('RGB', (chart_w, chart_h), (15, 22, 36))
        chart_d = ImageDraw.Draw(chart_sub)
        draw_elevation_profile(chart_d, 0, 0, chart_w, chart_h,
                               race_kms, race_eles, seorak_course.get('climbs', []),
                               line_color=ACCENT2, fill_color=(102, 222, 178, 80))
        sub.paste(chart_sub, (10, 32))

        # ── 우측 절반: 코스 지도 ──
        map_x = RACE_PANEL['w'] // 2 + 10
        map_w = RACE_PANEL['w'] - map_x - 10
        map_h = RACE_PANEL['h'] - 60
        map_sub = Image.new('RGB', (map_w, map_h), SEA)
        map_d = ImageDraw.Draw(map_sub)
        for x in range(0, map_w, 60):
            map_d.line([(x, 0), (x, map_h)], fill=GRID, width=1)
        for y in range(0, map_h, 60):
            map_d.line([(0, y), (map_w, y)], fill=GRID, width=1)

        s_lats_l = [p['lat'] for p in seorak_course['trkpts']]
        s_lons_l = [p['lon'] for p in seorak_course['trkpts']]
        s_lat_pad = (max(s_lats_l) - min(s_lats_l)) * 0.15 + 0.005
        s_lon_pad = (max(s_lons_l) - min(s_lons_l)) * 0.15 + 0.005
        pj = make_projector(min(s_lats_l) - s_lat_pad, max(s_lats_l) + s_lat_pad,
                            min(s_lons_l) - s_lon_pad, max(s_lons_l) + s_lon_pad,
                            0, 0, map_w, map_h)

        draw_country_in_panel(map_d, gdf, country_kr, pj, KOREA_HL, COASTLINE, 1, name_col)

        # 코스 트랙 + 글로우
        track_pts = [pj(p['lon'], p['lat']) for p in seorak_course['trkpts']]
        glow = Image.new('RGBA', (map_w, map_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.line(track_pts, fill=ACCENT2 + (220,), width=8)
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        map_rgba = map_sub.convert('RGBA')
        map_rgba.alpha_composite(glow)
        map_sub.paste(map_rgba.convert('RGB'))
        map_d2 = ImageDraw.Draw(map_sub)
        map_d2.line(track_pts, fill=ACCENT2, width=3)

        # Waypoints
        for w in seorak_course.get('waypoints', []):
            lat, lon = w.get('lat'), w.get('lon')
            if lat is None or lon is None:
                continue
            wx, wy = pj(lon, lat)
            if not (0 <= wx <= map_w and 0 <= wy <= map_h):
                continue
            name = w.get('name', '')
            if 'START' in name.upper():
                map_d2.ellipse([wx - 8, wy - 8, wx + 8, wy + 8], fill=ACCENT2, outline=TEXT_MAIN, width=2)
                map_d2.text((wx + 11, wy - 6), 'START', font=f(F_BOLD, 11), fill=ACCENT2)
            elif 'FINISH' in name.upper():
                map_d2.ellipse([wx - 8, wy - 8, wx + 8, wy + 8], fill=ACCENT3, outline=TEXT_MAIN, width=2)
                map_d2.text((wx + 11, wy - 6), 'FINISH', font=f(F_BOLD, 11), fill=ACCENT3)
            elif 'cut' in name.lower() or 'CUT' in name:
                map_d2.ellipse([wx - 5, wy - 5, wx + 5, wy + 5], fill=ACCENT, outline=TEXT_MAIN, width=1)
                km = w.get('km', 0)
                map_d2.text((wx + 8, wy - 6), f'CUT {km:.0f}km', font=f(F_BOLD, 10), fill=ACCENT)

        # Major climbs (HC/Cat1/Cat2)
        for c in seorak_course.get('climbs', []):
            cat = c.get('category', 'NC')
            if cat in ('HC', 'Cat1', 'Cat2'):
                target_km = c.get('start_km', 0)
                best = None
                best_diff = float('inf')
                for p in seorak_course['trkpts']:
                    diff = abs(p.get('km', 0) - target_km)
                    if diff < best_diff:
                        best_diff = diff
                        best = (p['lat'], p['lon'])
                if best:
                    cx, cy = pj(best[1], best[0])
                    if 0 <= cx <= map_w and 0 <= cy <= map_h:
                        diamond = [(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)]
                        map_d2.polygon(diamond, fill=ACCENT3, outline=TEXT_MAIN)
                        map_d2.text((cx + 9, cy - 7), cat, font=f(F_BOLD, 10), fill=ACCENT3)

        sub.paste(map_sub, (map_x, 32))
        sub_d2 = ImageDraw.Draw(sub)

        # 라벨
        sub_d2.rectangle([0, 0, RACE_PANEL['w'], 30], fill=(15, 22, 36, 200))
        sub_d2.text((10, 8), "🏆 A-RACE · Seorak Granfondo", font=f(F_BOLD, 16), fill=ACCENT2)
        sub_d2.text((RACE_PANEL['w'] - 200, 11),
                    f"D-{days_until('2026-06-20')} · 2026.06.20",
                    font=f(F_REG, 12), fill=TEXT_DIM)
        # 아래쪽 통계
        sub_d2.rectangle([0, RACE_PANEL['h'] - 26, RACE_PANEL['w'], RACE_PANEL['h']],
                         fill=(15, 22, 36, 200))
        info_text = (f"{seorak_course.get('total_km', 208):.0f}km · "
                     f"+{seorak_course.get('elev_gain_m', 3800):.0f}m · "
                     f"climbs {len(seorak_course.get('climbs', []))}개 · "
                     f"컷오프 12:00@82km / 15:40@167km")
        sub_d2.text((10, RACE_PANEL['h'] - 22), info_text, font=f(F_REG, 12), fill=TEXT_SUB)

    race_sub = render_map_panel(RACE_PANEL, render_race)
    img.paste(race_sub, (RACE_PANEL['x0'], RACE_PANEL['y0']))

    d = ImageDraw.Draw(img)

    # ─────────────────── 우측 패널: 3계층 시간 비전 ───────────────────
    PX = 1295
    PW = 580

    # athlete_db에서 W/kg
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

    # ─ 계층 1: LONG-TERM TDF ─
    d.text((PX, 50), "LONG-TERM · 10년 비전", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 75), "TOUR DE FRANCE", font=f(F_EX, 36), fill=ACCENT)
    d.rectangle([PX, 120, PX + PW, 124], fill=ACCENT)

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
    bar_y = 165
    bar_h = 6
    d.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], fill=(40, 55, 80))
    progress_pct = min(1.0, max(0, (cur_wpk - 2.0) / (5.5 - 2.0)))
    if progress_pct > 0:
        d.rectangle([bar_x0, bar_y, bar_x0 + int((bar_x1 - bar_x0) * progress_pct), bar_y + bar_h], fill=ACCENT)
    for w, label in milestones:
        ratio = (w - 2.0) / (5.5 - 2.0)
        x = bar_x0 + int((bar_x1 - bar_x0) * ratio)
        achieved = cur_wpk >= w
        col = ACCENT if achieved else TEXT_DIM
        d.ellipse([x - 5, bar_y - 4, x + 5, bar_y + bar_h + 4], fill=col,
                  outline=TEXT_MAIN if achieved else None, width=1)
        d.text((x - 12, bar_y + bar_h + 6), f"{w}", font=f(F_REG, 11), fill=col)
        d.text((x - 22, bar_y + bar_h + 22), label, font=f(F_REG, 10), fill=col)

    # 현재 위치 NOW 마커
    cur_x = bar_x0 + int((bar_x1 - bar_x0) * progress_pct)
    d.text((cur_x - 35, bar_y - 28), f"NOW {cur_wpk:.2f}W/kg", font=f(F_BOLD, 13), fill=ACCENT3)
    d.polygon([(cur_x, bar_y - 6), (cur_x - 6, bar_y - 12), (cur_x + 6, bar_y - 12)], fill=ACCENT3)

    # ─ 계층 2: THIS YEAR Seorak GF ─
    d.text((PX, 250), "THIS YEAR · 2026 시즌 A-race", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 275), "SEORAK GRANFONDO", font=f(F_EX, 32), fill=ACCENT2)
    d.text((PX, 320), "208km · +3,800m · 2026.06.20", font=f(F_REG, 18), fill=TEXT_SUB)
    d.rectangle([PX, 350, PX + 200, 354], fill=ACCENT2)

    days = days_until('2026-06-20')
    if days >= 0:
        d.text((PX, 365), f"D-{days}", font=f(F_EX, 56), fill=ACCENT3)
        d.text((PX + 195, 388), "남은 일수", font=f(F_REG, 20), fill=TEXT_SUB)
        d.text((PX + 195, 415), f"컷오프 12:00@82km / 15:40@167km",
               font=f(F_REG, 13), fill=TEXT_DIM)

    # ─ 계층 3: TODAY ─
    d.text((PX, 480), "TODAY · 오늘의 라이딩", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 505), course_name, font=f(F_EX, 40), fill=TEXT_MAIN)
    d.rectangle([PX, 555, PX + PW, 558], fill=TEXT_MAIN)

    INFO_Y = 575
    d.rounded_rectangle([PX, INFO_Y, PX + PW, INFO_Y + 480], radius=12,
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
        ('Climbs',      f"{len(climbs)}개 · VAM 최고 {max((c.get('vam_m_per_h', 0) for c in climbs), default=0):.0f}"),
    ]
    for i, (k, v) in enumerate(specs):
        sy = INFO_Y + 30 + i * 45
        d.text((PX + 25, sy), k, font=f(F_REG, 18), fill=TEXT_SUB)
        d.text((PX + 200, sy), v, font=f(F_BOLD, 18), fill=TEXT_MAIN)

    img.save(out_png, optimize=True)
    print(f"  ✓ {out_png}")
    if seorak_course:
        print(f"  Seorak GPX: {seorak_course.get('total_km', 0):.0f}km, "
              f"climbs {len(seorak_course.get('climbs', []))}개, "
              f"waypoints {len(seorak_course.get('waypoints', []))}개")


if __name__ == '__main__':
    main()
