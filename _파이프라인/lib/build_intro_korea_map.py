#!/usr/bin/env python3
"""한국 지도 + 사용자 GPS 트랙 + 라이딩 정밀 데이터 인트로 PNG.

5/2 TDF 인트로 컨셉 유지하면서:
- 좌측 절반: 한국 지도 (라이더 + GPS 트랙 + 코스명·climb 마커)
- 우측 절반: 그란폰도 코칭 / Data Ride / Big Ride 브랜딩 + A-race(설악 GF) 정보

라이딩별 동적: _analysis.json + _videos.json + ride_meta.json + FIT GPS 사용.

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
from shapely.geometry import Point, LineString


W, H = 1920, 1080

# 폰트 — pipeline/intro_video/fonts/
SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
F_REG  = str(FD / 'NanumGothic.ttf')
F_BOLD = str(FD / 'NanumGothicBold.ttf')
F_EX   = str(FD / 'NanumGothicExtraBold.ttf')

def f(p, s):
    return ImageFont.truetype(p, s)


# 컬러 팔레트 (TDF 인트로와 통일)
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
RIVER_COL = (90, 130, 175)


# 한국 본토 지도 영역 (위경도)
MAP_LAT_MIN, MAP_LAT_MAX = 33.5, 38.8
MAP_LON_MIN, MAP_LON_MAX = 125.5, 130.0

# 화면 좌측 1/2에 지도
MAP_X0, MAP_Y0 = 80, 80
MAP_W, MAP_H = 1100, 920


def project(lon, lat):
    """위경도 → 픽셀 (38°N 기준 cos 보정)."""
    asp = math.cos(math.radians(36.0))
    lon_r = (MAP_LON_MAX - MAP_LON_MIN) * asp
    lat_r = (MAP_LAT_MAX - MAP_LAT_MIN)
    scale = min(MAP_W / lon_r, MAP_H / lat_r) * 0.95
    cx = MAP_X0 + MAP_W / 2
    cy = MAP_Y0 + MAP_H / 2
    x = cx + (lon - (MAP_LON_MIN + MAP_LON_MAX) / 2) * asp * scale
    y = cy - (lat - (MAP_LAT_MAX + MAP_LAT_MIN) / 2) * scale
    return (x, y)


def polygon_to_pixels(polygon):
    return [project(x, y) for x, y in polygon.exterior.coords]


def draw_country(d, gdf, country_name, fill, outline, outline_width=2):
    rows = gdf[gdf['NAME_EN'] == country_name] if 'NAME_EN' in gdf.columns else gdf[gdf['name'] == country_name]
    if len(rows) == 0:
        return
    g = rows.geometry.iloc[0]
    polys = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    for p in polys:
        pts = polygon_to_pixels(p)
        if len(pts) >= 3:
            d.polygon(pts, fill=fill, outline=outline)
            if outline_width > 1:
                d.line(pts + [pts[0]], fill=outline, width=outline_width)


def parse_iso(s):
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    return datetime.fromisoformat(s)


def extract_gps_track(ride_dir):
    """라이딩 폴더의 .fit에서 GPS 트랙 추출."""
    from fitparse import FitFile
    fits = list(Path(ride_dir).glob('*.fit')) + list(Path(ride_dir).glob('*.FIT'))
    if not fits:
        return [], []
    fit = FitFile(str(fits[0]))
    lats, lons = [], []
    for r in fit.get_messages('record'):
        d = {f.name: f.value for f in r}
        lat = d.get('position_lat')
        lon = d.get('position_long')
        if lat is None or lon is None:
            continue
        lats.append(lat * (180.0 / 2**31))
        lons.append(lon * (180.0 / 2**31))
    return lats, lons


def load_ride(ride_dir):
    ride = Path(ride_dir)
    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8')) if (ride / 'ride_meta.json').exists() else {}
    return A, M


def days_until(target_date_str, today=None):
    """target_date까지 남은 일수."""
    target = datetime.fromisoformat(target_date_str).date()
    today = (today or datetime.now()).date()
    return (target - today).days


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

    # FIT GPS
    lats, lons = extract_gps_track(ride_dir)
    print(f"  → GPS points: {len(lats)}")

    # Natural Earth shapefile (10m 우선, 없으면 110m)
    NE_DIR = SCRIPT_DIR.parent / 'intro_video' / 'ne_data'
    shp = NE_DIR / 'ne_10m_admin_0_countries.shp'
    if not shp.exists():
        shp = NE_DIR / 'ne_110m_admin_0_countries.shp'
    if not shp.exists():
        sys.exit(f"✗ Natural Earth shapefile 없음: {NE_DIR}")
    gdf = gpd.read_file(shp)

    # 한국 컬럼명 확인
    name_col = 'NAME_EN' if 'NAME_EN' in gdf.columns else 'name'
    country_kr = 'South Korea' if (gdf[name_col] == 'South Korea').any() else 'Korea, South'

    img = Image.new('RGB', (W, H), SEA)
    d = ImageDraw.Draw(img)

    # ───── 격자 ─────
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # 위경도 라벨
    for lon in range(int(MAP_LON_MIN), int(MAP_LON_MAX) + 1):
        px, _ = project(lon, MAP_LAT_MAX)
        if MAP_X0 <= px <= MAP_X0 + MAP_W:
            d.line([(px, MAP_Y0), (px, MAP_Y0 + MAP_H)], fill=GRID, width=1)
            d.text((px + 3, MAP_Y0 + 5), f"{lon}°E", font=f(F_REG, 12), fill=TEXT_DIM)
    for lat in range(int(MAP_LAT_MIN), int(MAP_LAT_MAX) + 1):
        _, py = project(127, lat)
        if MAP_Y0 <= py <= MAP_Y0 + MAP_H:
            d.line([(MAP_X0, py), (MAP_X0 + MAP_W, py)], fill=GRID, width=1)
            d.text((MAP_X0 + 5, py - 15), f"{lat}°N", font=f(F_REG, 12), fill=TEXT_DIM)

    # ───── 주변국 (배경) ─────
    for c in ['North Korea', 'China', 'Japan', 'Russia']:
        try:
            draw_country(d, gdf, c, LAND_BG, BORDER, 1)
        except Exception:
            pass

    # ───── 한국 (강조) ─────
    draw_country(d, gdf, country_kr, KOREA_HL, COASTLINE, 0)

    # 한국 위에 어두운 오버레이 (그라데이션 느낌)
    img_rgba = img.convert('RGBA')
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    rows = gdf[gdf[name_col] == country_kr]
    if len(rows):
        g = rows.geometry.iloc[0]
        polys = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
        for p in polys:
            pts = polygon_to_pixels(p)
            if len(pts) >= 3:
                od.polygon(pts, fill=KOREA + (140,))
        img_rgba.alpha_composite(overlay)
        img = img_rgba.convert('RGB')
        d = ImageDraw.Draw(img)

        # 해안선 다시 강조
        for p in polys:
            pts = polygon_to_pixels(p)
            if len(pts) >= 3:
                d.line(pts + [pts[0]], fill=COASTLINE, width=2)

    # ───── 주요 도시 마커 (작게) ─────
    cities = [
        ('Seoul', 37.566, 126.978),
        ('Daegu', 35.871, 128.601),
        ('Busan', 35.180, 129.075),
        ('Sokcho', 38.207, 128.591),  # 설악 GF 출발 인근
    ]
    for name, lat, lon in cities:
        px, py = project(lon, lat)
        d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=TEXT_DIM)
        d.text((px + 6, py - 8), name, font=f(F_REG, 12), fill=TEXT_DIM)

    # ───── 사용자 GPS 트랙 (글로우 + 라인) ─────
    if lats:
        track_pts = [project(lo, la) for la, lo in zip(lats, lons)]
        # 글로우 효과
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.line(track_pts, fill=ACCENT + (220,), width=10)
        glow = glow.filter(ImageFilter.GaussianBlur(6))
        img_rgba = img.convert('RGBA')
        img_rgba.alpha_composite(glow)
        img = img_rgba.convert('RGB')
        d = ImageDraw.Draw(img)
        d.line(track_pts, fill=ACCENT, width=3)

        # 출발·도착 마커
        d.ellipse([track_pts[0][0] - 10, track_pts[0][1] - 10,
                   track_pts[0][0] + 10, track_pts[0][1] + 10],
                  fill=ACCENT2, outline=TEXT_MAIN, width=3)
        d.ellipse([track_pts[-1][0] - 10, track_pts[-1][1] - 10,
                   track_pts[-1][0] + 10, track_pts[-1][1] + 10],
                  fill=ACCENT3, outline=TEXT_MAIN, width=3)

    # ───── Climb 마커 (다이아몬드) ─────
    # FIT 데이터의 climb start_km을 GPS로 매핑
    if lats and climbs:
        from fitparse import FitFile
        fits = list(ride_dir.glob('*.fit'))
        if fits:
            fit = FitFile(str(fits[0]))
            recs = []
            for r in fit.get_messages('record'):
                rd = {field.name: field.value for field in r}
                if rd.get('position_lat') is not None and rd.get('distance') is not None:
                    recs.append(rd)
            for c in climbs:
                target_d = (c.get('start_km', 0) or 0) * 1000
                for r in recs:
                    if abs((r.get('distance') or 0) - target_d) < 100:
                        clat = r['position_lat'] * (180.0 / 2**31)
                        clon = r['position_long'] * (180.0 / 2**31)
                        cx, cy = project(clon, clat)
                        diamond = [(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)]
                        d.polygon(diamond, fill=ACCENT3, outline=TEXT_MAIN)
                        # 클라임 라벨
                        idx = c.get('index', '?')
                        d.text((cx + 12, cy - 10), f"#{idx}", font=f(F_BOLD, 14), fill=ACCENT3)
                        break

    # ───── 좌측 코너 라벨 ─────
    d.text((MAP_X0, MAP_Y0 - 40), "KOREA · 대한민국", font=f(F_REG, 18), fill=TEXT_DIM)
    d.line([(MAP_X0, MAP_Y0 - 15), (MAP_X0 + 80, MAP_Y0 - 15)], fill=ACCENT, width=2)
    d.text((MAP_X0 + 95, MAP_Y0 - 32), "Source: Natural Earth · GPS: Garmin .fit",
           font=f(F_REG, 11), fill=TEXT_DIM)

    # ───── 우측 패널 ─────
    PX = 1280
    course_name = M.get('코스명', '') or ride_dir.name.split()[-1]

    d.text((PX, 80), "ULTIMATE GOAL", font=f(F_REG, 22), fill=TEXT_DIM)
    d.text((PX, 110), "SEORAK GRANFONDO", font=f(F_EX, 48), fill=ACCENT)
    d.text((PX, 165), "208km · +3,800m · 2026.06.20", font=f(F_REG, 22), fill=TEXT_SUB)
    d.rectangle([PX, 200, PX + 500, 204], fill=ACCENT)

    # D-day 카운트
    days = days_until('2026-06-20')
    if days >= 0:
        d.text((PX, 220), f"D-{days}", font=f(F_EX, 56), fill=ACCENT3)
        d.text((PX + 180, 240), f"남은 일수", font=f(F_REG, 24), fill=TEXT_SUB)

    # 채널 브랜딩
    d.text((PX, 320), "그란폰도 코칭", font=f(F_EX, 56), fill=TEXT_MAIN)
    d.text((PX, 395), "Data Ride", font=f(F_EX, 80), fill=ACCENT)
    d.rectangle([PX, 500, PX + 200, 504], fill=ACCENT2)
    d.text((PX, 525), "Big Ride", font=f(F_EX, 64), fill=ACCENT2)

    d.text((PX, 615), "데이터로 보는 라이딩의 모든 것", font=f(F_REG, 28), fill=TEXT_SUB)
    d.text((PX, 655), "Power · HR · Pacing · Nutrition · Recovery", font=f(F_REG, 20), fill=TEXT_DIM)

    # 오늘의 라이딩 정보 박스
    INFO_Y = 740
    d.rounded_rectangle([PX, INFO_Y, PX + 500, INFO_Y + 270], radius=12,
                        fill=(20, 28, 44), outline=(40, 55, 80), width=2)
    d.text((PX + 25, INFO_Y + 20), f"오늘의 라이딩 — {course_name}",
           font=f(F_BOLD, 22), fill=ACCENT)
    specs = [
        ('거리 / 상승',  f"{s.get('distance_km', 0)} km · +{s.get('elev_gain_m', 0):,}m"),
        ('주행 시간',    f"{s.get('moving_h', '?')} (평균 {s.get('avg_speed_kmh', 0)} km/h)"),
        ('TSS · IF',    f"{s.get('tss', 0)} · {s.get('if_', 0)}"),
        ('Avg / NP',    f"{s.get('avg_power_w', 0)}W / {s.get('np_w', 0)}W"),
        ('디커플링',    f"{s.get('decoupling_pct', 0)}%"),
        ('Climbs',      f"{len(climbs)}개 (HC↓: VAM 최고 {max((c.get('vam_m_per_h', 0) for c in climbs), default=0):.0f})"),
    ]
    for i, (k, v) in enumerate(specs):
        sy = INFO_Y + 60 + i * 35
        d.text((PX + 25, sy), k, font=f(F_REG, 18), fill=TEXT_SUB)
        d.text((PX + 180, sy), v, font=f(F_BOLD, 18), fill=TEXT_MAIN)

    # ───── 범례 ─────
    LEG_Y = H - 200
    d.rounded_rectangle([MAP_X0, LEG_Y, MAP_X0 + 440, LEG_Y + 170],
                        radius=10, fill=(15, 22, 36), outline=(35, 48, 72), width=1)
    d.text((MAP_X0 + 15, LEG_Y + 15), "Legend", font=f(F_BOLD, 16), fill=TEXT_DIM)
    items = [
        (ACCENT, "GPS 트랙 (Garmin .fit)"),
        (ACCENT2, "출발 (Start)"),
        (ACCENT3, "Climb / 도착"),
    ]
    for i, (col, label) in enumerate(items):
        ly = LEG_Y + 50 + i * 32
        d.ellipse([MAP_X0 + 20, ly, MAP_X0 + 36, ly + 16], fill=col)
        d.text((MAP_X0 + 50, ly - 1), label, font=f(F_REG, 17), fill=TEXT_MAIN)

    img.save(out_png, optimize=True)
    print(f"  ✓ {out_png}")


if __name__ == '__main__':
    main()
