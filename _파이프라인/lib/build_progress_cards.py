#!/usr/bin/env python3
"""athlete_db.json 기반 진행도/부하/준비도 카드 PNG.

- card_athlete_journey.png  : 시즌 라이딩 누적 (CTL/ATL/TSB 추이)
- card_weekly_load.png      : 최근 8주 주간 TSS·거리·상승
- card_seorak_readiness.png : 설악 GF 5차원 준비도 게이지

산출물 위치: <ride_dir>/output_videos/_cards/
"""
import sys
import json
import math
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

import athlete_db


W, H = 1920, 1080

SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
NANUM_REG  = FD / 'NanumGothic.ttf'
NANUM_BOLD = FD / 'NanumGothicBold.ttf'
NANUM_EX   = FD / 'NanumGothicExtraBold.ttf'
SYS_FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'


def font(sz, weight='reg'):
    nanum_map = {'reg': NANUM_REG, 'bold': NANUM_BOLD, 'ex': NANUM_EX}
    p = nanum_map.get(weight)
    if p and p.exists():
        return ImageFont.truetype(str(p), sz)
    idx = {'reg': 0, 'bold': 1, 'ex': 3}.get(weight, 0)
    try:
        return ImageFont.truetype(SYS_FONT, sz, index=idx)
    except Exception:
        return ImageFont.load_default()


# 컬러
BG_DARK = (18, 24, 38)
BG_PANEL = (28, 38, 58)
ACCENT = (255, 184, 76)
ACCENT2 = (102, 222, 178)
ACCENT3 = (255, 107, 107)
TEXT_M = (240, 244, 250)
TEXT_S = (160, 175, 200)
TEXT_D = (110, 125, 150)
DIVIDER = (50, 65, 95)


def gradient_bg(img, top=(12, 22, 38), bottom=(28, 38, 58)):
    d = ImageDraw.Draw(img)
    for y in range(H):
        a = y / H
        c = tuple(int(top[i] + (bottom[i] - top[i]) * a) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    return d


def text_centered(d, txt, y, fnt, color=TEXT_M):
    bb = d.textbbox((0, 0), txt, font=fnt)
    d.text(((W - (bb[2] - bb[0])) // 2, y), txt, font=fnt, fill=color)


def text_xy(d, txt, x, y, fnt, color=TEXT_M, anchor='lt'):
    if anchor == 'lt':
        d.text((x, y), txt, font=fnt, fill=color)
    elif anchor == 'rt':
        bb = d.textbbox((0, 0), txt, font=fnt)
        d.text((x - (bb[2] - bb[0]), y), txt, font=fnt, fill=color)
    elif anchor == 'ct':
        bb = d.textbbox((0, 0), txt, font=fnt)
        d.text((x - (bb[2] - bb[0]) // 2, y), txt, font=fnt, fill=color)


def panel(d, x, y, w, h, fill=BG_PANEL, outline=DIVIDER):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=fill, outline=outline, width=2)


# ───── Card: Athlete Journey (CTL/ATL/TSB 추이) ─────
def card_athlete_journey(out_path, db):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '시즌 누적 — 피트니스/피로/밸런스', 70, font(60, 'ex'), ACCENT)
    text_centered(d, 'CTL (Fitness) · ATL (Fatigue) · TSB (Form)', 160, font(28, 'reg'), TEXT_S)

    pmc = db.get('pmc', [])
    if not pmc:
        text_centered(d, '(데이터 누적 중)', 540, font(40, 'reg'), TEXT_S)
        img.save(out_path, optimize=True)
        return

    # 차트 영역
    CX0, CY0 = 150, 250
    CW, CH = W - 300, 600

    # 데이터 범위
    ctls = [p['ctl'] for p in pmc]
    atls = [p['atl'] for p in pmc]
    tsbs = [p['tsb'] for p in pmc]
    y_max = max(max(ctls), max(atls), 50)
    y_min = min(min(tsbs), -20)

    # 격자
    for v in range(int(y_min // 10) * 10, int(y_max // 10 + 1) * 10 + 1, 10):
        ys = CY0 + CH - (v - y_min) / (y_max - y_min) * CH
        d.line([(CX0, ys), (CX0 + CW, ys)], fill=DIVIDER, width=1)
        text_xy(d, str(v), CX0 - 10, ys - 10, font(16, 'reg'), TEXT_D, anchor='rt')

    # 0 라인 강조
    if y_min < 0 < y_max:
        ys0 = CY0 + CH - (0 - y_min) / (y_max - y_min) * CH
        d.line([(CX0, ys0), (CX0 + CW, ys0)], fill=TEXT_D, width=2)

    # 라인 그리기
    n = len(pmc)
    def to_xy(i, v):
        x = CX0 + (i / max(1, n - 1)) * CW
        y = CY0 + CH - (v - y_min) / (y_max - y_min) * CH
        return (x, y)

    ctl_pts = [to_xy(i, p['ctl']) for i, p in enumerate(pmc)]
    atl_pts = [to_xy(i, p['atl']) for i, p in enumerate(pmc)]
    tsb_pts = [to_xy(i, p['tsb']) for i, p in enumerate(pmc)]

    if len(ctl_pts) > 1:
        d.line(ctl_pts, fill=ACCENT, width=4)
        d.line(atl_pts, fill=ACCENT3, width=3)
        d.line(tsb_pts, fill=ACCENT2, width=3)

    # X축 날짜
    for i in [0, n // 2, n - 1] if n > 2 else range(n):
        x = CX0 + (i / max(1, n - 1)) * CW
        text_xy(d, pmc[i]['date'], x, CY0 + CH + 15, font(16, 'reg'), TEXT_D, anchor='ct')

    # 범례
    LX, LY = CX0, CY0 + CH + 70
    items = [(ACCENT, f"CTL (피트니스): {ctls[-1]:.1f}"),
             (ACCENT3, f"ATL (피로): {atls[-1]:.1f}"),
             (ACCENT2, f"TSB (밸런스): {tsbs[-1]:+.1f}")]
    for i, (col, label) in enumerate(items):
        x = LX + i * 380
        d.rectangle([x, LY + 8, x + 30, LY + 13], fill=col)
        text_xy(d, label, x + 40, LY, font(28, 'bold'), TEXT_M)

    # 해석
    last_tsb = tsbs[-1]
    if last_tsb < -20:
        verdict = '⚠️ 깊은 피로 — 회복 우선'
        col = ACCENT3
    elif last_tsb < -10:
        verdict = '🟠 누적 피로 — 강도 조절'
        col = ACCENT
    elif last_tsb < 5:
        verdict = '🟢 균형 — 적응 중'
        col = ACCENT2
    elif last_tsb < 25:
        verdict = '✨ Peak — 최고 컨디션'
        col = ACCENT2
    else:
        verdict = '🔵 Detrain — 강도 부족'
        col = TEXT_S
    text_centered(d, verdict, LY + 60, font(32, 'bold'), col)

    img.save(out_path, optimize=True)


# ───── Card: Weekly Load ─────
def card_weekly_load(out_path, db):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '주간 부하 — 최근 8주', 70, font(60, 'ex'), ACCENT)
    text_centered(d, 'TSS · 거리 · 상승 누적', 160, font(28, 'reg'), TEXT_S)

    weeks = db.get('weekly_loads', [])
    if not weeks:
        text_centered(d, '(데이터 누적 중)', 540, font(40, 'reg'), TEXT_S)
        img.save(out_path, optimize=True)
        return

    # 차트 영역
    CX0, CY0 = 150, 250
    CW, CH = W - 300, 600

    n = len(weeks)
    bar_w = CW / n / 2.5

    max_tss = max((w['tss'] for w in weeks), default=1) or 1

    # TSS 바 차트
    for i, w in enumerate(weeks):
        cx = CX0 + (i + 0.5) / n * CW
        bh = w['tss'] / max_tss * (CH - 50)
        d.rectangle([cx - bar_w / 2, CY0 + CH - bh,
                     cx + bar_w / 2, CY0 + CH], fill=ACCENT)
        # TSS 라벨
        if w['tss'] > 0:
            text_xy(d, f"{w['tss']:.0f}", cx, CY0 + CH - bh - 25, font(20, 'bold'), TEXT_M, anchor='ct')
        # 주 라벨
        wk_label = w['week_start'][5:]  # MM-DD
        text_xy(d, wk_label, cx, CY0 + CH + 15, font(16, 'reg'), TEXT_D, anchor='ct')

    # Y축 라벨
    text_xy(d, '주간 TSS', CX0 - 10, CY0, font(20, 'reg'), TEXT_S, anchor='rt')

    # 범례 + 통계
    LY = CY0 + CH + 80
    text_centered(d, f"이번 주 TSS: {weeks[-1]['tss']:.0f} · "
                     f"거리 {weeks[-1]['distance_km']:.1f}km · "
                     f"상승 {weeks[-1]['elev_gain_m']:.0f}m · "
                     f"라이딩 {weeks[-1]['rides']}회",
                  LY, font(28, 'bold'), TEXT_M)

    img.save(out_path, optimize=True)


# ───── Card: Seorak GF Readiness ─────
def card_seorak_readiness(out_path, db):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '설악 그란폰도 208km 준비도', 70, font(56, 'ex'), ACCENT)

    # D-day
    days = (datetime(2026, 6, 20) - datetime.now()).days
    text_centered(d, f"D-{days} · 2026.06.20", 150, font(34, 'reg'), TEXT_S)

    rd = db.get('seorak_readiness') or {}
    overall = rd.get('overall_pct', 0)
    dims = rd.get('dimensions', {})

    # 종합 게이지 (큰 원)
    cx, cy, r = W // 2, 350, 130
    # 배경 원
    d.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=DIVIDER, width=20)
    # 진행도 원호
    end_angle = -90 + (overall / 100) * 360
    if overall >= 75:
        col = ACCENT2
    elif overall >= 50:
        col = ACCENT
    else:
        col = ACCENT3
    d.arc([cx - r, cy - r, cx + r, cy + r], -90, end_angle, fill=col, width=20)
    text_centered(d, f"{overall}%", cy - 50, font(96, 'ex'), col)
    text_centered(d, '종합 준비도', cy + 50, font(28, 'reg'), TEXT_S)

    # 4개 차원 게이지 (가로 배열)
    GY = 580
    GW = (W - 200) // 4
    for i, (key, label) in enumerate([
        ('distance', '거리'), ('elevation', '상승'), ('duration', '시간'), ('decoupling', '디커플링')
    ]):
        gx = 100 + i * GW
        dim = dims.get(key, {})
        pct = dim.get('pct')
        if pct is None:
            pct = 0
            label_extra = '(데이터 부족)'
        else:
            label_extra = ''

        # 패널
        panel(d, gx + 20, GY, GW - 40, 380)

        # 차원 이름
        text_centered_panel = lambda txt, ty, fnt, col: text_xy(d, txt, gx + GW // 2, GY + ty, fnt, col, anchor='ct')
        text_centered_panel(label, 30, font(34, 'ex'), TEXT_M)

        # 색상 결정
        if pct >= 75:
            gc = ACCENT2
        elif pct >= 50:
            gc = ACCENT
        else:
            gc = ACCENT3

        # 풀 원 게이지 (종합 게이지와 디자인 통일) — 12시부터 시계 방향
        ggx, ggy, ggr = gx + GW // 2, GY + 165, 65
        d.arc([ggx - ggr, ggy - ggr, ggx + ggr, ggy + ggr], 0, 360, fill=DIVIDER, width=10)
        end_angle = -90 + (pct / 100) * 360
        d.arc([ggx - ggr, ggy - ggr, ggx + ggr, ggy + ggr], -90, end_angle, fill=gc, width=10)
        # 게이지 중앙 % 텍스트 (호와 안 겹치게 작게)
        text_centered_panel(f"{pct}%", 140, font(44, 'ex'), gc)

        # 현재값 / 목표값
        if key == 'distance':
            curr = f"{dim.get('current_max_km', 0):.0f} km"
            targ = f"목표 {dim.get('target_km', 208)} km"
        elif key == 'elevation':
            curr = f"{dim.get('current_max_m', 0):,} m"
            targ = f"목표 {dim.get('target_m', 3800):,} m"
        elif key == 'duration':
            curr = f"{dim.get('current_max_h', 0):.1f} h"
            targ = f"목표 {dim.get('target_h', 9.5)} h"
        else:
            cur_dec = dim.get('recent_4w_avg')
            curr = f"{cur_dec}%" if cur_dec else '?'
            targ = f"목표 ≤ {dim.get('target_max', 8)}%"

        text_centered_panel(curr, 280, font(28, 'bold'), TEXT_M)
        text_centered_panel(targ, 320, font(20, 'reg'), TEXT_S)

    # 하단 요약
    if overall >= 75:
        msg = f"✓ 핵심 능력 준비됨 — Peak 단계로 진입 가능"
    elif overall >= 50:
        msg = f"🟠 절반 진척 — Build 2 단계 집중 필요"
    else:
        msg = f"⚠️ 거리·상승·디커플링 모두 보강 필요"
    text_centered(d, msg, H - 60, font(32, 'bold'), col)

    img.save(out_path, optimize=True)


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_progress_cards.py <ride_dir>")
    ride = Path(sys.argv[1])
    base_dir = ride.parent
    db = athlete_db.load_db(base_dir) or athlete_db.refresh_db(base_dir)[0]

    out_dir = ride / 'output_videos' / '_cards'
    out_dir.mkdir(parents=True, exist_ok=True)

    cards = [
        ('card_athlete_journey.png', card_athlete_journey),
        ('card_weekly_load.png', card_weekly_load),
        ('card_seorak_readiness.png', card_seorak_readiness),
    ]
    for name, fn in cards:
        out_path = out_dir / name
        fn(out_path, db)
        print(f"  ✓ {name}")


if __name__ == '__main__':
    main()
