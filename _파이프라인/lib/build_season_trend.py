#!/usr/bin/env python3
"""시즌 진척도 카드 — 매 영상 끝에 1장 추가하는 누적 트렌드.

차별화 포인트: 라이딩 1회의 데이터가 아니라 시즌 전체 흐름을 매 영상에 노출.
4-패널 (TSS / 디커플링 / CTL / Seorak 가능성):
- 시청자가 "내 trajectory가 어떻게 변하나" 궁금해지도록
- 라이딩 N회 누적 → "여정"의 시각적 응집

사용법:
    python3 build_season_trend.py <ride_dir> [output_png]
"""
import sys
import json
import math
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
F_REG  = str(FD / 'NanumGothic.ttf')
F_BOLD = str(FD / 'NanumGothicBold.ttf')
F_EX   = str(FD / 'NanumGothicExtraBold.ttf')


def f(p, s):
    return ImageFont.truetype(p, s)


# 색상
BG       = (18, 24, 38)
PANEL_BG = (28, 36, 52)
ACCENT   = (255, 184, 76)   # yellow (TSS, 시즌 strong)
ACCENT2  = (102, 222, 178)  # green (Seorak)
ACCENT3  = (255, 107, 107)  # red (디커플링 - 낮을수록 좋음)
ACCENT4  = (140, 200, 255)  # blue (CTL fitness)
TEXT     = (245, 248, 252)
SUB      = (170, 185, 210)
DIM      = (90, 105, 130)
GRID     = (40, 55, 80)


def load_seorak_per_ride(ride_dir, ride_name):
    """라이딩 폴더의 _analysis.json에서 Seorak 시뮬 가능성%."""
    folder = ride_dir.parent / ride_name
    if not folder.is_dir():
        return None
    a = folder / '_analysis.json'
    if not a.exists():
        return None
    try:
        d = json.loads(a.read_text(encoding='utf-8'))
        return (d.get('seorak_simulation') or {}).get('feasibility_pct')
    except Exception:
        return None


def draw_metric_chart(d, x0, y0, w, h, x_labels, values, label, fmt, color,
                      target=None, lower_is_better=False, mode='line', highlight_last=True):
    """X축: 라벨 (날짜 또는 ride 번호), Y축: 값."""
    if not values:
        d.text((x0+20, y0+h//2), '데이터 누적 중', font=f(F_REG, 18), fill=DIM)
        return
    pad_l, pad_r, pad_t, pad_b = 75, 25, 50, 35
    cx0 = x0 + pad_l
    cy0 = y0 + pad_t
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b

    pool = list(values)
    if target is not None:
        pool.append(target)
    vmin = min(pool); vmax = max(pool)
    if vmax - vmin < 1e-3:
        vmax = vmin + 1
    # 5% headroom
    vrange = vmax - vmin
    vmin -= vrange * 0.10
    vmax += vrange * 0.10

    def to_xy(i, v):
        n = max(1, len(values) - 1)
        x = cx0 + (i / n) * cw if n > 0 else cx0 + cw / 2
        y = cy0 + ch - ((v - vmin) / (vmax - vmin)) * ch
        return (x, y)

    # Y축 grid + 라벨
    for i in range(4):
        v = vmin + (vmax - vmin) * i / 3
        y = cy0 + ch - ((v - vmin) / (vmax - vmin)) * ch
        d.line([(cx0, y), (cx0 + cw, y)], fill=GRID, width=1)
        d.text((x0 + 8, y - 8), fmt.format(v), font=f(F_REG, 11), fill=DIM)

    # 목표선
    if target is not None:
        ty = cy0 + ch - ((target - vmin) / (vmax - vmin)) * ch
        d.line([(cx0, ty), (cx0 + cw, ty)], fill=ACCENT, width=2)
        tlbl = f"목표 {fmt.format(target).strip()}"
        d.text((cx0 + cw - 70, ty - 14), tlbl, font=f(F_BOLD, 11), fill=ACCENT)

    pts = [to_xy(i, v) for i, v in enumerate(values)]

    if mode == 'bar' and len(values) > 0:
        # 막대 차트
        bar_w = max(8, cw / max(1, len(values)) * 0.6)
        for i, (px, py) in enumerate(pts):
            x1, x2 = px - bar_w/2, px + bar_w/2
            y0_b = cy0 + ch
            col = color
            if highlight_last and i == len(pts) - 1:
                # 글로우
                d.rectangle([x1-2, py-3, x2+2, y0_b], fill=col)
                d.text((px - 18, py - 22), fmt.format(values[i]), font=f(F_BOLD, 13), fill=col)
            else:
                d.rectangle([x1, py, x2, y0_b], fill=col)
    else:
        # 라인 차트
        if len(pts) >= 2:
            d.line(pts, fill=color, width=3)
        for i, (px, py) in enumerate(pts):
            if highlight_last and i == len(pts) - 1:
                # 글로우
                for r in (12, 8):
                    d.ellipse([px-r, py-r, px+r, py+r], fill=color)
                d.ellipse([px-4, py-4, px+4, py+4], fill=TEXT, outline=color)
                d.text((px + 12, py - 8), fmt.format(values[i]), font=f(F_BOLD, 14), fill=color)
            else:
                d.ellipse([px-3, py-3, px+3, py+3], fill=color)

    # X축 라벨
    n = len(x_labels)
    step = max(1, n // 6)
    for i in range(0, n, step):
        if i < len(pts):
            px = pts[i][0]
            d.text((px - 18, cy0 + ch + 8), x_labels[i], font=f(F_REG, 11), fill=DIM)
    if n > 0 and (n - 1) % step != 0:
        # 마지막 라벨도 표시
        i = n - 1
        if i < len(pts):
            px = pts[i][0]
            d.text((px - 18, cy0 + ch + 8), x_labels[i], font=f(F_REG, 11), fill=DIM)

    # 박스
    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=GRID, width=1)
    # 패널 라벨
    d.text((x0 + 14, y0 + 12), label, font=f(F_BOLD, 18), fill=color)

    # 추세 화살표 (마지막 vs 직전)
    if len(values) >= 2:
        diff = values[-1] - values[-2]
        better = (diff < 0 if lower_is_better else diff > 0)
        sym = '▲' if diff > 0 else ('▼' if diff < 0 else '·')
        if abs(diff) < 1e-3:
            col = SUB
        else:
            col = ACCENT2 if better else ACCENT3
        d.text((x0 + w - 100, y0 + 12), f"{sym} {fmt.format(abs(diff)).strip()}", font=f(F_BOLD, 14), fill=col)


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_season_trend.py <ride_dir> [output_png]")
    ride_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ride_dir / 'output_videos' / '_cards' / 'card_season_trend.png'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db_path = ride_dir.parent / 'athlete_db.json'
    if not db_path.exists():
        print(f"  ⚠ athlete_db.json 없음 ({db_path})")
        return

    db = json.loads(db_path.read_text(encoding='utf-8'))
    rides = sorted(db.get('rides', []), key=lambda r: r.get('date', ''))
    pmc = db.get('pmc', [])

    # 데이터 부족 시 안내 카드
    if len(rides) < 2:
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((W//2 - 280, H//2 - 30),
               "📈 SEASON 진척도 — 데이터 누적 중",
               font=f(F_EX, 36), fill=ACCENT)
        d.text((W//2 - 240, H//2 + 30),
               f"라이딩 {len(rides)}회 (>2회 필요)",
               font=f(F_REG, 22), fill=SUB)
        img.save(out_path)
        print(f"  ✓ {out_path} (placeholder)")
        return

    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # 헤더
    d.text((60, 40), f"📈 SEASON 진척도 — 라이딩 {len(rides)}회 누적",
           font=f(F_EX, 38), fill=ACCENT)
    d.text((60, 95),
           "Seorak GF 10h를 향한 실시간 그래프 — 매 라이딩의 데이터가 trajectory를 그립니다",
           font=f(F_REG, 18), fill=SUB)
    d.line([(60, 130), (W - 60, 130)], fill=ACCENT, width=2)

    # 4-패널 그리드
    PW = (W - 60 * 3) // 2
    PH = 380
    PY1 = 160
    PY2 = 160 + PH + 30

    # 1) TSS — 막대 차트
    tss_vals = [r.get('tss', 0) for r in rides]
    tss_labels = [r.get('date', '?')[5:] for r in rides]
    d.rounded_rectangle([60, PY1, 60 + PW, PY1 + PH], radius=12, fill=PANEL_BG, outline=GRID)
    draw_metric_chart(d, 60, PY1, PW, PH, tss_labels, tss_vals,
                      'TSS · 라이딩별 훈련 부하', '{:.0f}', ACCENT, mode='bar')

    # 2) 디커플링 — 라인, 목표 8% 선
    dec_vals = [r.get('decoupling_pct', 0) for r in rides]
    d.rounded_rectangle([60 + PW + 60, PY1, 60 + PW + 60 + PW, PY1 + PH],
                        radius=12, fill=PANEL_BG, outline=GRID)
    draw_metric_chart(d, 60 + PW + 60, PY1, PW, PH, tss_labels, dec_vals,
                      '디커플링 % · 영양·회복 인디케이터', '{:.1f}%',
                      ACCENT3, target=8, lower_is_better=True, mode='line')

    # 3) CTL — pmc 시계열 (idle days 포함)
    if isinstance(pmc, list) and pmc:
        ctl_dates = [p.get('date', '?')[5:] for p in pmc]
        ctl_vals = [p.get('ctl', 0) for p in pmc]
    else:
        ctl_dates, ctl_vals = [], []
    d.rounded_rectangle([60, PY2, 60 + PW, PY2 + PH], radius=12, fill=PANEL_BG, outline=GRID)
    draw_metric_chart(d, 60, PY2, PW, PH, ctl_dates, ctl_vals,
                      'CTL · 피트니스 (14d EWMA)', '{:.1f}', ACCENT4, mode='line')

    # 4) Seorak 가능성 % — per-ride _analysis.json
    seo_vals = []
    seo_labels = []
    for r in rides:
        v = load_seorak_per_ride(ride_dir, r.get('name', ''))
        if v is not None:
            seo_vals.append(v)
            seo_labels.append(r.get('date', '?')[5:])
    d.rounded_rectangle([60 + PW + 60, PY2, 60 + PW + 60 + PW, PY2 + PH],
                        radius=12, fill=PANEL_BG, outline=GRID)
    draw_metric_chart(d, 60 + PW + 60, PY2, PW, PH, seo_labels, seo_vals,
                      'Seorak 10h 가능성 % · 매 라이딩 시뮬 결과',
                      '{:.0f}%', ACCENT2, target=80, mode='line')

    img.save(out_path, optimize=True)
    print(f"  ✓ {out_path} (라이딩 {len(rides)}회 · pmc {len(pmc)}일)")


if __name__ == '__main__':
    main()
