#!/usr/bin/env python3
"""Seorak GF 코스 분석 + 오늘 라이딩 climb 매핑 카드.

채널 차별화: 매 훈련 라이딩의 climb이 Seorak GF 어떤 climb과 유사한지 자동 매핑.
시청자에게 "이 훈련이 A-race의 어떤 부분을 닮았나" 시각화.

레이아웃 (1920×1080):
- Top: Seorak GF 9 climb 통계 + 컷오프 정보
- Middle: scatter (grade × length) — Seorak 9 점 + 오늘 라이딩 N 점, 가까운 짝 연결선
- Bottom: 매핑 결과 표 (오늘 climb ↔ Seorak 유사 climb + 차이)

사용법:
    python3 build_seorak_mapping_card.py <ride_dir> [output_png]
"""
import sys
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
F_REG  = str(FD / 'NanumGothic.ttf')
F_BOLD = str(FD / 'NanumGothicBold.ttf')
F_EX   = str(FD / 'NanumGothicExtraBold.ttf')


def f(p, s):
    return ImageFont.truetype(p, s)


BG       = (18, 24, 38)
PANEL_BG = (28, 36, 52)
ACCENT   = (255, 184, 76)   # yellow
ACCENT2  = (102, 222, 178)  # green = Seorak
ACCENT3  = (255, 107, 107)  # red
ACCENT4  = (140, 200, 255)  # blue
TODAY    = (255, 184, 76)   # orange = today's ride
SEORAK   = (102, 222, 178)
TEXT     = (245, 248, 252)
SUB      = (170, 185, 210)
DIM      = (90, 105, 130)
GRID     = (40, 55, 80)


def similarity(today_climb, seorak_climb):
    """grade + length 기반 유사도 score (낮을수록 유사)."""
    gd = abs(today_climb['avg_grade_pct'] - seorak_climb['avg_grade_pct'])
    ld = abs((today_climb['distance_m']/1000) - (seorak_climb['distance_m']/1000))
    ed = abs(today_climb.get('elev_gain_m', 0) - seorak_climb.get('elev_gain_m', 0)) / 100
    # weighted: length 차이가 가장 의미 있음 (climb 시간), grade 다음, elev_gain 보조
    return ld * 2.0 + gd * 1.0 + ed * 0.5


def match_climbs(today_climbs, seorak_climbs):
    """오늘 각 climb의 가장 유사한 Seorak climb 매핑 (greedy)."""
    pairs = []
    for tc in today_climbs:
        scores = [(similarity(tc, sc), sc) for sc in seorak_climbs]
        scores.sort(key=lambda x: x[0])
        best_score, best_sc = scores[0]
        pairs.append((tc, best_sc, best_score))
    return pairs


def draw_scatter(d, x0, y0, w, h, seorak_climbs, today_climbs, pairs):
    """grade × length scatter plot."""
    # 차트 영역
    pad_l, pad_r, pad_t, pad_b = 70, 30, 50, 50
    cx0 = x0 + pad_l
    cy0 = y0 + pad_t
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b

    # 범위
    all_points = list(seorak_climbs) + list(today_climbs)
    grades = [c['avg_grade_pct'] for c in all_points]
    lengths = [c['distance_m']/1000 for c in all_points]
    if not grades or not lengths:
        return
    g_min, g_max = 0, max(12, max(grades) * 1.1)
    l_min, l_max = 0, max(12, max(lengths) * 1.1)

    def to_xy(grade, length):
        x = cx0 + (grade - g_min) / (g_max - g_min) * cw
        y = cy0 + ch - (length - l_min) / (l_max - l_min) * ch
        return (x, y)

    # 격자 + 축 라벨
    for i in range(5):
        gv = g_min + (g_max - g_min) * i / 4
        x = cx0 + (gv - g_min) / (g_max - g_min) * cw
        d.line([(x, cy0), (x, cy0 + ch)], fill=GRID, width=1)
        d.text((x - 10, cy0 + ch + 8), f"{gv:.0f}%", font=f(F_REG, 12), fill=DIM)
        lv = l_min + (l_max - l_min) * i / 4
        y = cy0 + ch - (lv - l_min) / (l_max - l_min) * ch
        d.line([(cx0, y), (cx0 + cw, y)], fill=GRID, width=1)
        d.text((x0 + 5, y - 7), f"{lv:.0f}km", font=f(F_REG, 12), fill=DIM)

    # 축 제목
    d.text((cx0 + cw // 2 - 30, y0 + h - 25), "평균 경사 (%)", font=f(F_BOLD, 14), fill=SUB)
    # y축 라벨 (회전 안 됨, 좌상에 표시)
    d.text((x0 + 5, y0 + 25), "거리 (km)", font=f(F_BOLD, 14), fill=SUB)

    # 매핑 라인 (먼저 그려서 점 뒤에)
    for tc, sc, score in pairs:
        tx, ty = to_xy(tc['avg_grade_pct'], tc['distance_m']/1000)
        sx, sy = to_xy(sc['avg_grade_pct'], sc['distance_m']/1000)
        d.line([(tx, ty), (sx, sy)], fill=(80, 90, 110), width=1)

    # Seorak 점 (green, 크게)
    for sc in seorak_climbs:
        sx, sy = to_xy(sc['avg_grade_pct'], sc['distance_m']/1000)
        # glow
        for r in (10, 7):
            d.ellipse([sx-r, sy-r, sx+r, sy+r], fill=SEORAK)
        d.ellipse([sx-4, sy-4, sx+4, sy+4], fill=TEXT, outline=SEORAK)
        d.text((sx+8, sy-10), f"#{sc['index']}", font=f(F_BOLD, 12), fill=SEORAK)

    # 오늘 점 (orange)
    for tc in today_climbs:
        tx, ty = to_xy(tc['avg_grade_pct'], tc['distance_m']/1000)
        # 다이아몬드 (Seorak 원과 구분)
        d.polygon([(tx, ty-7), (tx+7, ty), (tx, ty+7), (tx-7, ty)], fill=TODAY, outline=TEXT)
        d.text((tx+10, ty-10), f"#{tc.get('index','?')}", font=f(F_BOLD, 12), fill=TODAY)

    # 외곽
    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=GRID, width=1)


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_seorak_mapping_card.py <ride_dir> [output_png]")
    ride_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ride_dir / 'output_videos' / '_cards' / 'card_seorak_mapping.png'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    A = json.loads((ride_dir / '_analysis.json').read_text(encoding='utf-8'))
    today_climbs = A.get('climbs', []) or []

    # Seorak 코스 로드
    sys.path.insert(0, str(SCRIPT_DIR))
    import seorak
    sc = seorak.load_seorak_course(ride_dir.parent)
    seorak_climbs = sc['climbs']

    pairs = match_climbs(today_climbs, seorak_climbs) if today_climbs else []

    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # 헤더
    d.text((60, 40), "🏔 SEORAK GF 코스 매핑 — 오늘의 climb이 닮은 A-race 구간",
           font=f(F_EX, 34), fill=ACCENT)
    d.text((60, 90),
           f"Seorak GF 208km · {sc['elev_gain_m']:.0f}m · 9 climb · 컷오프 12:00@82km / 15:40@167km",
           font=f(F_REG, 16), fill=SUB)
    d.line([(60, 125), (W-60, 125)], fill=ACCENT, width=2)

    # 범례
    LX = W - 320
    d.text((LX, 50), "● Seorak GF 9 climb", font=f(F_BOLD, 14), fill=SEORAK)
    d.text((LX, 75), "◆ 오늘 라이딩 climb", font=f(F_BOLD, 14), fill=TODAY)
    d.text((LX, 100), "─ 가장 유사 매핑", font=f(F_REG, 12), fill=DIM)

    # Scatter (좌측)
    draw_scatter(d, 60, 160, 1100, 560, seorak_climbs, today_climbs, pairs)

    # 우측: 매핑 표
    TX = 1180
    TW = W - TX - 60
    d.rounded_rectangle([TX, 160, TX+TW, 720], radius=12, fill=PANEL_BG, outline=GRID)
    d.text((TX+18, 175), "📋 매핑 결과", font=f(F_EX, 22), fill=ACCENT)
    d.text((TX+18, 210),
           f"오늘 climb {len(today_climbs)}개 → 가장 유사한 Seorak climb",
           font=f(F_REG, 13), fill=DIM)

    if pairs:
        # 표 헤더
        row_y = 245
        d.text((TX+18, row_y), "오늘", font=f(F_BOLD, 13), fill=TODAY)
        d.text((TX+150, row_y), "↔ Seorak", font=f(F_BOLD, 13), fill=SEORAK)
        d.text((TX+330, row_y), "차이", font=f(F_BOLD, 13), fill=SUB)
        d.line([(TX+18, row_y+22), (TX+TW-18, row_y+22)], fill=GRID, width=1)

        # 행
        for i, (tc, sc_match, score) in enumerate(pairs[:12]):
            ry = row_y + 32 + i*32
            t_km = tc['distance_m']/1000
            s_km = sc_match['distance_m']/1000
            t_gr = tc['avg_grade_pct']
            s_gr = sc_match['avg_grade_pct']
            d.text((TX+18, ry),
                   f"#{tc.get('index','?'):2}  {t_gr:.1f}%·{t_km:.1f}km",
                   font=f(F_REG, 13), fill=TODAY)
            d.text((TX+150, ry),
                   f"#{sc_match['index']:2}  {s_gr:.1f}%·{s_km:.1f}km",
                   font=f(F_REG, 13), fill=SEORAK)
            gd = t_gr - s_gr
            ld = t_km - s_km
            d.text((TX+330, ry),
                   f"{gd:+.1f}% · {ld:+.1f}km",
                   font=f(F_REG, 12), fill=DIM)

    # 하단: Seorak waypoints + 컷오프
    LY = 760
    d.rounded_rectangle([60, LY, W-60, LY+260], radius=12, fill=PANEL_BG, outline=GRID)
    d.text((78, LY+15), "📍 Seorak GF 코스 마일스톤", font=f(F_EX, 22), fill=ACCENT)

    # 컷오프
    d.text((78, LY+55), "⏱ 컷오프 1", font=f(F_BOLD, 16), fill=ACCENT3)
    d.text((78, LY+82), "12:00 @ km 82  · 평균 20.5 km/h 유지", font=f(F_REG, 14), fill=TEXT)

    d.text((78, LY+115), "⏱ 컷오프 2", font=f(F_BOLD, 16), fill=ACCENT3)
    d.text((78, LY+142), "15:40 @ km 167 · 평균 21.4 km/h 유지", font=f(F_REG, 14), fill=TEXT)

    d.text((78, LY+175), "🏁 컷오프 3 (최종)", font=f(F_BOLD, 16), fill=ACCENT)
    d.text((78, LY+202), "18:00 @ km 208 · 평균 20.8 km/h (목표 10h 완주 = 평균 20.8 km/h)",
           font=f(F_REG, 14), fill=TEXT)

    # waypoint 일부
    wp = sc.get('waypoints', [])
    if wp:
        d.text((620, LY+55), "📍 주요 waypoints", font=f(F_BOLD, 16), fill=ACCENT2)
        for i, w in enumerate(wp[:6]):
            ry = LY + 82 + i * 28
            d.text((620, ry), f"km {w['km']:5.1f}  ·  {w.get('name','')[:30]}",
                   font=f(F_REG, 14), fill=TEXT)

    # 9 climb 요약 (좌하)
    d.text((1150, LY+55), "🏔 Seorak 9 climb",
           font=f(F_BOLD, 16), fill=ACCENT2)
    for i, scl in enumerate(seorak_climbs[:9]):
        col = i // 5
        row = i % 5
        ry = LY + 82 + row * 28
        rx = 1150 + col * 350
        d.text((rx, ry),
               f"#{scl['index']:2} km{scl['start_km']:5.1f}  {scl['distance_m']/1000:.1f}km·{scl['avg_grade_pct']:.1f}%  {scl['category']}",
               font=f(F_REG, 12), fill=SEORAK if scl in [p[1] for p in pairs] else SUB)

    img.save(out_path, optimize=True)
    print(f"  ✓ {out_path}")
    print(f"  매핑: 오늘 {len(today_climbs)}개 ↔ Seorak {len(seorak_climbs)}개 climb")


if __name__ == '__main__':
    main()
