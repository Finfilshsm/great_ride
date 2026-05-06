#!/usr/bin/env python3
"""TDF 애니메이션 인트로 (2안 動) — 시작→종료점 이동 화살표 + 고도 플레이헤드 동기화 mp4.

레이아웃은 build_intro_tdf_map.py 와 동일. 차이:
- TDF 지도: 전체 코스는 dim, 시작점에서 현재 위치까지 bright + 화살표 헤드
- TDF 고도: 전체 프로파일은 dim, 0→현재 km까지 bright fill + 수직 playhead

출력: card_intro_tdf_animated.mp4 (1920×1080 · 30fps · 8초)

사용법:
    python3 build_intro_tdf_animated.py <ride_dir> [output_mp4]
"""
import sys
import json
import math
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter
import geopandas as gpd

# ─── 공유 상수/헬퍼 import ───
import build_intro_tdf_map as base_mod
from build_intro_tdf_map import (
    TDF_STAGES, TDF_ELEVATION, TDF_CLIMBS,
    TDF_MAP_PANEL, TDF_PROF_PANEL, COMPARE_PANEL,
    SEA, LAND_BG, FRANCE, FRANCE_HL, COASTLINE, BORDER,
    ACCENT, ACCENT2, ACCENT3, ACCENT4,
    TEXT_MAIN, TEXT_SUB, TEXT_DIM, GRID,
    F_REG, F_BOLD, F_EX, f,
    W, H, SCRIPT_DIR,
    make_projector, draw_country_in_panel, render_panel,
    draw_elevation_profile, panel_border,
    extract_gps_from_fit, days_until, load_ride,
)


FPS = 30
DURATION_SEC = 8
N_FRAMES = FPS * DURATION_SEC


# ───── 폴리라인 보간 ─────
def polyline_total(points):
    total = 0.0
    seg = []
    for i in range(len(points) - 1):
        dx = points[i + 1][0] - points[i][0]
        dy = points[i + 1][1] - points[i][1]
        L = math.sqrt(dx * dx + dy * dy)
        seg.append(L)
        total += L
    return total, seg


def partial_polyline(points, t):
    """t in [0,1] → 시작부터 t만큼의 부분 폴리라인 + 끝점·방향."""
    if t <= 0:
        return [points[0]], points[0], (1.0, 0.0)
    total, segs = polyline_total(points)
    if t >= 1:
        # 마지막 segment 방향
        if len(points) >= 2:
            dx = points[-1][0] - points[-2][0]
            dy = points[-1][1] - points[-2][1]
            L = math.sqrt(dx * dx + dy * dy) or 1.0
            return list(points), points[-1], (dx / L, dy / L)
        return list(points), points[-1], (1.0, 0.0)

    target = total * t
    cum = 0.0
    result = [points[0]]
    for i, L in enumerate(segs):
        if cum + L >= target and L > 0:
            r = (target - cum) / L
            x = points[i][0] + r * (points[i + 1][0] - points[i][0])
            y = points[i][1] + r * (points[i + 1][1] - points[i][1])
            result.append((x, y))
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            Ld = math.sqrt(dx * dx + dy * dy) or 1.0
            return result, (x, y), (dx / Ld, dy / Ld)
        cum += L
        result.append(points[i + 1])
    return result, points[-1], (1.0, 0.0)


def draw_arrow(d, pos, direction, color, size=14):
    x, y = pos
    dx, dy = direction
    # 화살촉: 끝점에서 뒤로 size만큼, 양옆으로 size*0.5 spread
    bx = x - dx * size
    by = y - dy * size
    # 수직 방향
    px = -dy
    py = dx
    p1 = (x, y)
    p2 = (bx + px * size * 0.55, by + py * size * 0.55)
    p3 = (bx - px * size * 0.55, by - py * size * 0.55)
    d.polygon([p1, p2, p3], fill=color, outline=TEXT_MAIN)


# ───── BASE 렌더 (정적 부분만) ─────
def render_base(ride_dir, gdf, name_col, today_records, today_kms, today_eles,
                seorak_course, course_name, A, R, climbs, s):
    img = Image.new('RGB', (W, H), SEA)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # ─ TDF 지도 (route 없이 — dim 전체 + 도시 markers)─
    def render_tdf_map_base(sub, sub_d):
        pj = make_projector(41.5, 51.5, -5.5, 9.0, 0, 0,
                            TDF_MAP_PANEL['w'], TDF_MAP_PANEL['h'])
        for c in ['Spain', 'Portugal', 'Italy', 'Switzerland', 'Germany',
                  'Belgium', 'Netherlands', 'Luxembourg', 'United Kingdom',
                  'Ireland', 'Andorra', 'Monaco']:
            try:
                draw_country_in_panel(sub_d, gdf, c, pj, LAND_BG, BORDER, 1, name_col)
            except Exception:
                pass
        draw_country_in_panel(sub_d, gdf, 'France', pj, FRANCE_HL, COASTLINE, 2, name_col)

        # 전체 코스 — dim 점선
        track = [pj(lon, lat) for lat, lon, _, _ in TDF_STAGES]
        sub_d.line(track, fill=(120, 100, 50), width=2)

        # 도시 마커
        for lat, lon, name, kind in TDF_STAGES:
            x, y = pj(lon, lat)
            if kind == 'mountain':
                sub_d.polygon([(x, y - 8), (x - 7, y + 5), (x + 7, y + 5)],
                              fill=ACCENT3, outline=TEXT_MAIN)
                sub_d.text((x + 10, y - 6), name, font=f(F_BOLD, 12), fill=ACCENT3)
            elif kind == 'start':
                sub_d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=ACCENT2,
                              outline=TEXT_MAIN, width=2)
                sub_d.text((x + 12, y - 8), f"START · {name}",
                           font=f(F_EX, 14), fill=ACCENT2)
            elif kind == 'finish':
                pts = []
                for k in range(10):
                    a = math.pi / 2 + k * math.pi / 5
                    r = 11 if k % 2 == 0 else 5
                    pts.append((x + r * math.cos(a), y - r * math.sin(a)))
                sub_d.polygon(pts, fill=ACCENT, outline=TEXT_MAIN)
                sub_d.text((x + 16, y - 10), f"FINISH · {name}",
                           font=f(F_EX, 16), fill=ACCENT)
            else:
                sub_d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=TEXT_SUB)
                sub_d.text((x + 6, y - 7), name, font=f(F_REG, 10), fill=TEXT_SUB)

        sub_d.rectangle([0, 0, TDF_MAP_PANEL['w'], 36], fill=(15, 22, 36))
        sub_d.text((10, 8), "🇫🇷 TOUR DE FRANCE 2025 · 21 stages · 3,338km · +52,000m",
                   font=f(F_EX, 18), fill=ACCENT)
        sub_d.text((TDF_MAP_PANEL['w'] - 320, 11),
                   "● START   ★ FINISH   ▲ HC MOUNTAIN",
                   font=f(F_BOLD, 12), fill=TEXT_SUB)

    tdf_sub = render_panel(TDF_MAP_PANEL, render_tdf_map_base)
    img.paste(tdf_sub, (TDF_MAP_PANEL['x0'], TDF_MAP_PANEL['y0']))
    panel_border(d, TDF_MAP_PANEL)

    # ─ TDF 고도 base — dim 전체 + climb 라벨 (밝은 fill은 frame마다)─
    def render_tdf_prof_base(sub, sub_d):
        chart_w = TDF_PROF_PANEL['w'] - 20
        chart_h = TDF_PROF_PANEL['h'] - 60
        chart_sub = Image.new('RGB', (chart_w, chart_h), (15, 22, 36))
        chart_d = ImageDraw.Draw(chart_sub)
        kms = [p[0] for p in TDF_ELEVATION]
        eles = [p[1] for p in TDF_ELEVATION]
        # 어두운 fill + dim line
        draw_elevation_profile(chart_d, 0, 0, chart_w, chart_h,
                               kms, eles, TDF_CLIMBS,
                               line_color=(120, 100, 50),
                               fill_color=(60, 50, 30, 80),
                               label_climb_names=True)
        sub.paste(chart_sub, (10, 32))

        sub_d.rectangle([0, 0, TDF_PROF_PANEL['w'], 30], fill=(15, 22, 36))
        sub_d.text((10, 8), "📈 TDF 2025 · SEASON ELEVATION PROFILE",
                   font=f(F_BOLD, 16), fill=ACCENT)
        sub_d.text((TDF_PROF_PANEL['w'] - 360, 11),
                   "▲ Hautacam · Ventoux · Loze · La Plagne (HC peaks)",
                   font=f(F_REG, 12), fill=TEXT_DIM)
        sub_d.rectangle([0, TDF_PROF_PANEL['h'] - 26, TDF_PROF_PANEL['w'], TDF_PROF_PANEL['h']],
                        fill=(15, 22, 36))
        sub_d.text((10, TDF_PROF_PANEL['h'] - 22),
                   "Pyrenees → Provence → Alps → Paris · 약 6 mountain stages, "
                   "최고점 Col de la Loze 2,304m",
                   font=f(F_REG, 12), fill=TEXT_SUB)

    prof_sub = render_panel(TDF_PROF_PANEL, render_tdf_prof_base)
    img.paste(prof_sub, (TDF_PROF_PANEL['x0'], TDF_PROF_PANEL['y0']))
    panel_border(d, TDF_PROF_PANEL)

    # ─ 하단 비교 (정적) ─
    def render_compare(sub, sub_d):
        half_w = (COMPARE_PANEL['w'] - 30) // 2
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

        sub_d.rectangle([0, 0, COMPARE_PANEL['w'], 30], fill=(15, 22, 36))
        sub_d.text((10, 8),
                   f"📍 TODAY · {course_name} ({s.get('distance_km', 0)}km · "
                   f"+{s.get('elev_gain_m', 0):,}m)",
                   font=f(F_BOLD, 14), fill=ACCENT4)
        sub_d.text((20 + ts_w, 8),
                   f"🏆 A-RACE · Seorak GF "
                   f"({seorak_course.get('total_km', 208) if seorak_course else 208:.0f}km · "
                   f"+{seorak_course.get('elev_gain_m', 3800) if seorak_course else 3800:.0f}m)",
                   font=f(F_BOLD, 14), fill=ACCENT2)

    cmp_sub = render_panel(COMPARE_PANEL, render_compare)
    img.paste(cmp_sub, (COMPARE_PANEL['x0'], COMPARE_PANEL['y0']))
    panel_border(d, COMPARE_PANEL)

    # ─ 우측 패널 (정적, build_intro_tdf_map.py 와 동일) ─
    d = ImageDraw.Draw(img)
    PX, PW = 1295, 580
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

    d.text((PX, 50), "LONG-TERM · 10년 비전", font=f(F_REG, 16), fill=TEXT_DIM)
    d.text((PX, 75), "TOUR DE FRANCE", font=f(F_EX, 36), fill=ACCENT)
    d.text((PX, 118), "★ 21 stages · 3,338km · +52,000m",
           font=f(F_REG, 14), fill=TEXT_SUB)
    d.rectangle([PX, 145, PX + PW, 149], fill=ACCENT)

    milestones = [(2.5, 'Cat 4-5'), (3.0, 'Cat 3'), (3.5, 'Cat 2'),
                  (4.0, 'Cat 1'), (4.5, 'Pro/TDF'), (5.5, 'GC')]
    bar_x0, bar_x1 = PX, PX + PW
    bar_y, bar_h = 190, 6
    d.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], fill=(40, 55, 80))
    progress_pct = min(1.0, max(0, (cur_wpk - 2.0) / (5.5 - 2.0)))
    if progress_pct > 0:
        d.rectangle([bar_x0, bar_y,
                     bar_x0 + int((bar_x1 - bar_x0) * progress_pct),
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
    d.text((cur_x - 35, bar_y - 28), f"NOW {cur_wpk:.2f}W/kg",
           font=f(F_BOLD, 13), fill=ACCENT3)
    d.polygon([(cur_x, bar_y - 6), (cur_x - 6, bar_y - 12), (cur_x + 6, bar_y - 12)],
              fill=ACCENT3)

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

    return img


# ───── 프레임별 dynamic overlay ─────
def draw_frame_overlay(base_img, t, tdf_track_screen,
                       tdf_prof_geom, tdf_kms, tdf_eles):
    """t in [0,1] — base_img의 copy에 화살표·플레이헤드 그리기."""
    img = base_img.copy()
    d = ImageDraw.Draw(img, 'RGBA')

    # ── TDF 지도: 부분 트랙 + 화살표 ──
    partial, head_pos, head_dir = partial_polyline(tdf_track_screen, t)
    if len(partial) >= 2:
        # 글로우
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.line(partial, fill=ACCENT + (220,), width=10)
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        img_rgba = img.convert('RGBA')
        img_rgba.alpha_composite(glow)
        img = img_rgba.convert('RGB')
        d = ImageDraw.Draw(img, 'RGBA')
        d.line(partial, fill=ACCENT, width=4)
    # 화살표 헤드
    draw_arrow(d, head_pos, head_dir, ACCENT3, size=18)
    # 위치 라벨
    cur_km = TDF_ELEVATION[-1][0] * t
    d.text((head_pos[0] + 12, head_pos[1] - 24),
           f"{cur_km:.0f} km", font=f(F_BOLD, 13), fill=ACCENT3)

    # ── TDF 고도: 부분 fill + 수직 playhead ──
    cx0, cy0, cw, ch, km_max, ele_min, ele_max = tdf_prof_geom
    if km_max > 0 and ele_max > ele_min:
        target_km = km_max * t
        # bright fill + line up to target_km
        bright_pts = []
        for km, ele in zip(tdf_kms, tdf_eles):
            if km <= target_km:
                x = cx0 + (km / km_max) * cw
                y = cy0 + ch - ((ele - ele_min) / (ele_max - ele_min)) * ch
                bright_pts.append((x, y))
            else:
                # 보간 종점 추가
                if bright_pts:
                    x_end = cx0 + (target_km / km_max) * cw
                    # 마지막 점과의 보간 ele
                    prev_km = bright_pts[-1]
                    # simple: use last point ele
                    bright_pts.append((x_end, prev_km[1]))
                break
        if len(bright_pts) >= 2:
            fill_pts = bright_pts + [(bright_pts[-1][0], cy0 + ch),
                                     (bright_pts[0][0], cy0 + ch)]
            d.polygon(fill_pts, fill=ACCENT)
            d.line(bright_pts, fill=ACCENT, width=2)

        # 수직 playhead
        ph_x = cx0 + (target_km / km_max) * cw
        d.line([(ph_x, cy0), (ph_x, cy0 + ch)], fill=ACCENT3, width=2)
        d.ellipse([ph_x - 5, cy0 - 5, ph_x + 5, cy0 + 5], fill=ACCENT3,
                  outline=TEXT_MAIN)
        # 수직 라벨
        d.text((ph_x + 6, cy0 + 4), f"{target_km:.0f}km",
               font=f(F_BOLD, 12), fill=ACCENT3)

    return img


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_intro_tdf_animated.py <ride_dir> [output_mp4]")
    ride_dir = Path(sys.argv[1])
    out_mp4 = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        ride_dir / 'output_videos' / '_cards' / 'card_intro_tdf_animated.mp4'
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

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
    try:
        import seorak as seorak_mod
        seorak_course = seorak_mod.load_seorak_course(ride_dir.parent)
    except Exception as e:
        print(f"  ⚠ Seorak GPX 로드 실패: {e}")

    print("  베이스 이미지 렌더…")
    base_img = render_base(ride_dir, gdf, name_col, today_records,
                           today_kms, today_eles, seorak_course,
                           course_name, A, R, climbs, s)

    # ─ TDF 트랙 스크린 좌표 (메인 이미지 기준) ─
    pj_panel = make_projector(41.5, 51.5, -5.5, 9.0, 0, 0,
                              TDF_MAP_PANEL['w'], TDF_MAP_PANEL['h'])
    tdf_track_screen = []
    for lat, lon, _, _ in TDF_STAGES:
        x, y = pj_panel(lon, lat)
        tdf_track_screen.append((x + TDF_MAP_PANEL['x0'], y + TDF_MAP_PANEL['y0']))

    # ─ TDF 프로파일 차트 좌표 (메인 이미지 기준) ─
    chart_w = TDF_PROF_PANEL['w'] - 20
    chart_h = TDF_PROF_PANEL['h'] - 60
    pad_l, pad_r, pad_t, pad_b = 60, 20, 35, 28
    chart_offset_x = TDF_PROF_PANEL['x0'] + 10
    chart_offset_y = TDF_PROF_PANEL['y0'] + 32
    cx0 = chart_offset_x + pad_l
    cy0 = chart_offset_y + pad_t
    cw = chart_w - pad_l - pad_r
    ch = chart_h - pad_t - pad_b
    tdf_kms = [p[0] for p in TDF_ELEVATION]
    tdf_eles = [p[1] for p in TDF_ELEVATION]
    km_max = max(tdf_kms)
    ele_min, ele_max = min(tdf_eles), max(tdf_eles)
    tdf_prof_geom = (cx0, cy0, cw, ch, km_max, ele_min, ele_max)

    # ─ 프레임 렌더 ─
    tmp_dir = Path(tempfile.mkdtemp(prefix='tdf_anim_'))
    print(f"  {N_FRAMES} 프레임 렌더 → {tmp_dir}")
    try:
        for i in range(N_FRAMES):
            t = i / (N_FRAMES - 1)
            # ease in/out (cosine smooth)
            t_eased = 0.5 - 0.5 * math.cos(t * math.pi)
            frame = draw_frame_overlay(base_img, t_eased, tdf_track_screen,
                                       tdf_prof_geom, tdf_kms, tdf_eles)
            frame.save(tmp_dir / f"frame_{i:04d}.png", optimize=False)
            if (i + 1) % 30 == 0:
                print(f"    {i + 1}/{N_FRAMES}")

        # ffmpeg encode
        print(f"  ffmpeg → {out_mp4}")
        subprocess.run([
            'ffmpeg', '-y',
            '-framerate', str(FPS),
            '-i', str(tmp_dir / 'frame_%04d.png'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', '18',
            '-preset', 'medium',
            str(out_mp4),
        ], check=True, capture_output=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"  ✓ {out_mp4}")
    print(f"  TDF 2025: {N_FRAMES} frames · {DURATION_SEC}s · {FPS}fps")


if __name__ == '__main__':
    main()
