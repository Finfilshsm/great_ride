#!/usr/bin/env python3
"""라이딩별 하이라이트 카드 PNG 동적 생성.

_analysis.json + ride_meta.json을 읽어 코스명·거리·상승·TSS 등을 카드에 박아 넣음.
산출 위치: <RIDE_DIR>/output_videos/_cards/

생성되는 카드 (PHASE3가 참조):
  card1_overview.png        — 라이딩 개요
  card2_glossary.png        — 용어 사전
  card_course_profile.png   — 거리·상승·시간 프로파일
  card_course_climbs.png    — 검출된 클라임 목록
  card_best_climb_intro.png — 베스트 클라임 인트로 (구 climb5_intro)
  card_transition.png       — 전환 카드
  card_fade_climb_intro.png — 페이드 클라임 인트로 (구 climb6_intro)
  card3_analysis.png        — 종합 분석 (TSS·IF·디커플링)
  card_conclusion.png       — 결론
  card_action.png           — 다음 라이딩 액션
"""
import sys
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080

# 색상 팔레트
BG_DARK    = (18, 24, 38)
BG_PANEL   = (28, 38, 58)
ACCENT     = (255, 184, 76)
ACCENT2    = (102, 222, 178)
ACCENT3    = (255, 107, 107)
TEXT_MAIN  = (240, 244, 250)
TEXT_SUB   = (160, 175, 200)
TEXT_DIM   = (110, 125, 150)
DIVIDER    = (50, 65, 95)

# 한글 폰트 (시스템 우선, 없으면 NanumGothic)
SYS_FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
NANUM_DIR = Path(__file__).parent.parent / 'intro_video' / 'fonts'
NANUM_REG  = NANUM_DIR / 'NanumGothic.ttf'
NANUM_BOLD = NANUM_DIR / 'NanumGothicBold.ttf'
NANUM_EX   = NANUM_DIR / 'NanumGothicExtraBold.ttf'


def font(sz, weight='reg'):
    """가용 폰트 자동 선택. weight: reg|bold|ex"""
    # NanumGothic 우선 (영문 + 한글 미려)
    nanum_map = {'reg': NANUM_REG, 'bold': NANUM_BOLD, 'ex': NANUM_EX}
    p = nanum_map.get(weight)
    if p and p.exists():
        return ImageFont.truetype(str(p), sz)
    # 시스템 폰트 fallback (TTC index: 0=Regular, 1=Bold, 2=Heavy, 3=ExtraBold)
    idx_map = {'reg': 0, 'bold': 1, 'ex': 3}
    try:
        return ImageFont.truetype(SYS_FONT, sz, index=idx_map.get(weight, 0))
    except Exception:
        return ImageFont.load_default()


def text_centered(d, txt, y, fnt, color=TEXT_MAIN):
    bb = d.textbbox((0, 0), txt, font=fnt)
    tw = bb[2] - bb[0]
    d.text(((W - tw) // 2, y), txt, font=fnt, fill=color)


def text_xy(d, txt, x, y, fnt, color=TEXT_MAIN, anchor='lt'):
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


def gradient_bg(img, top=(12, 22, 38), bottom=(28, 38, 58)):
    d = ImageDraw.Draw(img)
    for y in range(H):
        a = y / H
        c = tuple(int(top[i] + (bottom[i] - top[i]) * a) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    return d


# ───── Card 1: 개요 ─────
def card_overview(out, A, R, M, date_str):
    s = A['summary']; r = A['rider']
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, f"그란폰도 훈련 — {M.get('코스명','')}", 60, font(64, 'ex'))
    text_centered(d, f"{date_str}  ·  {M.get('출발지','')} 출발", 145, font(32, 'reg'), TEXT_SUB)
    d.line([(W // 2 - 200, 200), (W // 2 + 200, 200)], fill=ACCENT, width=3)

    quad_w, quad_h, pad = 800, 220, 40
    cx_l = W // 2 - quad_w - pad // 2
    cx_r = W // 2 + pad // 2
    moving = s.get('moving_h', '')
    quads = [
        (cx_l, 240, '거리 / 상승', f"{s['distance_km']} km",
         f"+{s['elev_gain_m']:,} m  ({s['elev_per_km']} m/km)", ACCENT),
        (cx_r, 240, '시간 / 평균속도', s.get('elapsed_h', '?'),
         f"주행 {s['avg_speed_kmh']} km/h", ACCENT),
        (cx_l, 480, '강도 (TSS · IF · VI)', f"{s['tss']} · {s['if_']} · {s['vi']}",
         f"회복 {72 if s['tss'] > 250 else 48}시간 권장", ACCENT3),
        (cx_r, 480, '라이더 (FTP · 체중 · W/kg)',
         f"{r['ftp_w']}W · {r['weight_kg']}kg", f"{r['w_per_kg']} W/kg", ACCENT2),
    ]
    for x, y, label, big, small, col in quads:
        panel(d, x, y, quad_w, quad_h)
        text_xy(d, label, x + 30, y + 20, font(26, 'reg'), TEXT_SUB)
        text_xy(d, big, x + 30, y + 58, font(60, 'ex'), col)
        text_xy(d, small, x + 30, y + 150, font(28, 'reg'))
    text_centered(d, '오늘의 데이터로 본 코칭 분석', 760, font(38, 'bold'))
    if A.get('best_climb') and A.get('fade_climb'):
        b, fd = A['best_climb'], A['fade_climb']
        text_centered(d, f"Climb #{b['index']} (베스트) vs Climb #{fd['index']} (페이드) 비교",
                      815, font(28, 'reg'), ACCENT)
    d.line([(60, 1000), (W - 60, 1000)], fill=DIVIDER, width=1)
    text_centered(d, 'DATA-DRIVEN COACHING · GoPro + Garmin .fit', 1025, font(20, 'reg'), TEXT_DIM)
    img.save(out, optimize=True)


# ───── Card 2: 용어 사전 ─────
def card_glossary(out, A, R, M, date_str):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '사이클링 데이터 용어 사전', 50, font(56, 'ex'))
    text_centered(d, '본 영상에서 사용되는 핵심 지표', 130, font(26, 'reg'), TEXT_SUB)
    d.line([(W // 2 - 200, 175), (W // 2 + 200, 175)], fill=ACCENT, width=2)
    items = [
        ('FTP',  '1시간 동안 유지 가능한 최대 평균 파워'),
        ('NP',   'Normalized Power — 파워 변동 보정 평균'),
        ('IF',   'Intensity Factor (NP/FTP) — 라이딩 강도'),
        ('TSS',  'Training Stress Score — 누적 훈련 부하'),
        ('VAM',  'Vertical Ascent in Meters/h — 시간당 상승 m'),
        ('LTHR', '젖산 임계 심박수 (≈ FTP의 심박)'),
        ('VI',   'Variability Index (NP/AvgPower) — 일관성'),
        ('Pw:Hr 디커플링', '동일 파워에서 후반 HR 상승률 (5%↓ 정상)'),
    ]
    y = 230
    for term, desc in items:
        panel(d, 120, y, W - 240, 80)
        text_xy(d, term, 150, y + 20, font(38, 'ex'), ACCENT)
        text_xy(d, desc, 480, y + 28, font(28, 'reg'))
        y += 95
    img.save(out, optimize=True)


# ───── Card: 코스 프로파일 ─────
def card_course_profile(out, A, R, M, date_str):
    s = A['summary']
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '코스 프로파일', 80, font(72, 'ex'), ACCENT)
    text_centered(d, M.get('코스명', ''), 180, font(40, 'reg'), TEXT_SUB)
    panel(d, 200, 320, W - 400, 600)
    items = [
        ('총 거리',     f"{s['distance_km']} km"),
        ('누적 상승',   f"+{s['elev_gain_m']:,} m"),
        ('상승률',      f"{s['elev_per_km']} m/km"),
        ('경과 시간',   s.get('elapsed_h', '?')),
        ('주행 시간',   s.get('moving_h', '?')),
        ('평균 속도',   f"{s['avg_speed_kmh']} km/h"),
    ]
    y = 380
    for label, val in items:
        text_xy(d, label, 280, y, font(36, 'reg'), TEXT_SUB)
        text_xy(d, val,   1500, y, font(44, 'ex'), TEXT_MAIN, anchor='rt')
        y += 90
    img.save(out, optimize=True)


# ───── Card: 코스 클라임 목록 ─────
def card_course_climbs(out, A, R, M, date_str):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, f"검출된 클라임 — 총 {len(A.get('climbs', []))}개", 80, font(60, 'ex'), ACCENT)
    text_centered(d, f"{M.get('코스명','')} · {A['summary']['distance_km']}km",
                  170, font(32, 'reg'), TEXT_SUB)
    y = 260
    best_idx = A.get('best_climb', {}).get('index') if A.get('best_climb') else None
    fade_idx = A.get('fade_climb', {}).get('index') if A.get('fade_climb') else None
    for c in A.get('climbs', [])[:8]:  # 최대 8개 표시
        col = ACCENT2 if c['index'] == best_idx else (ACCENT3 if c['index'] == fade_idx else TEXT_MAIN)
        marker = '★' if c['index'] == best_idx else ('⚠' if c['index'] == fade_idx else '·')
        text_xy(d, f"{marker} #{c['index']}", 180, y, font(38, 'ex'), col)
        text_xy(d, f"{c['start_km']:.1f} km", 320, y, font(34, 'reg'))
        text_xy(d, f"{c['distance_m']/1000:.1f} km", 530, y, font(34, 'reg'))
        text_xy(d, f"+{c['elev_gain_m']:.0f} m", 730, y, font(34, 'reg'))
        text_xy(d, f"{c['avg_grade_pct']:.1f}%", 920, y, font(34, 'reg'))
        text_xy(d, f"{c['avg_power_w']:.0f}W", 1080, y, font(34, 'reg'))
        text_xy(d, f"VAM {c['vam_m_per_h']:.0f}", 1280, y, font(34, 'reg'), col)
        y += 80
    # 헤더
    text_xy(d, '#', 180, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, '시작', 320, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, '거리', 530, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, '상승', 730, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, '경사', 920, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, '파워', 1080, 220, font(22, 'reg'), TEXT_DIM)
    text_xy(d, 'VAM', 1280, 220, font(22, 'reg'), TEXT_DIM)
    img.save(out, optimize=True)


# ───── Card: Climb 인트로 (베스트 또는 페이드) ─────
def card_climb_intro(out, A, R, M, date_str, climb, kind='best'):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    color = ACCENT2 if kind == 'best' else ACCENT3
    label = '★ 베스트 페이싱 후보' if kind == 'best' else '⚠ 후반 시험 — 페이드'
    title = f"Climb #{climb['index']}"
    text_centered(d, label, 100, font(38, 'reg'), color)
    text_centered(d, title, 180, font(180, 'ex'), color)
    panel(d, 200, 460, W - 400, 380)
    items = [
        ('지점',        f"{climb['start_km']:.1f} km"),
        ('거리 · 경사', f"{climb['distance_m']/1000:.2f} km · {climb['avg_grade_pct']:.1f}%"),
        ('상승',        f"+{climb['elev_gain_m']:.0f} m"),
        ('소요',        f"{climb['duration_s']//60}분 {climb['duration_s']%60}초"),
        ('VAM',         f"{climb['vam_m_per_h']:.0f} m/h"),
        ('평균 파워',   f"{climb['avg_power_w']:.0f} W (IF {climb['avg_power_w']/R['ftp_w']:.2f})"),
    ]
    y = 510
    for lab, val in items:
        text_xy(d, lab, 280, y, font(30, 'reg'), TEXT_SUB)
        text_xy(d, val, 1500, y, font(38, 'ex'), color, anchor='rt')
        y += 55
    img.save(out, optimize=True)


# ───── Card: 전환 ─────
def card_transition(out, A, R, M, date_str):
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '비교', 380, font(56, 'reg'), TEXT_SUB)
    text_centered(d, '같은 라이더 · 같은 코스 — 다른 결과', 480, font(60, 'ex'), ACCENT)
    text_centered(d, '데이터로 본 차이의 진짜 원인', 580, font(36, 'reg'), TEXT_MAIN)
    d.line([(W // 2 - 300, 660), (W // 2 + 300, 660)], fill=ACCENT, width=2)
    img.save(out, optimize=True)


# ───── Card: 종합 분석 ─────
def card_analysis(out, A, R, M, date_str):
    s = A['summary']
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '종합 분석', 60, font(60, 'ex'), ACCENT)
    text_centered(d, '오늘 데이터가 말해주는 것', 145, font(28, 'reg'), TEXT_SUB)
    panel(d, 100, 240, W - 200, 750)
    rows = [
        ('TSS (누적 부하)',         f"{s['tss']}",             f"{72 if s['tss']>250 else 48}h 회복 권장",  ACCENT3 if s['tss']>250 else ACCENT2),
        ('IF (강도)',                f"{s['if_']}",             '0.85+ = 그란폰도 페이싱',                    ACCENT),
        ('VI (변동성)',              f"{s['vi']}",              '1.05↓ 균등 / 1.20↑ 들쑥날쑥',                ACCENT),
        ('평균 케이던스',            f"{s['avg_cadence']} rpm",  '85~95 권장 (근피로 지연)',                   ACCENT2 if s['avg_cadence']>=80 else ACCENT3),
        ('Pw:Hr 디커플링',           f"{s['decoupling_pct']}%", '5%↓ 정상 / 10%+ 영양·페이싱 점검',           ACCENT2 if s['decoupling_pct']<8 else ACCENT3),
    ]
    y = 290
    for label, val, hint, col in rows:
        text_xy(d, label, 150, y + 15, font(32, 'reg'), TEXT_SUB)
        text_xy(d, val,   850, y, font(56, 'ex'), col)
        text_xy(d, hint,  1200, y + 20, font(26, 'reg'), TEXT_SUB)
        y += 130
    img.save(out, optimize=True)


# ───── Card: 결론 ─────
def card_conclusion(out, A, R, M, date_str):
    s = A['summary']
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '결론', 80, font(72, 'ex'), ACCENT)
    text_centered(d, '오늘 라이딩이 남긴 인사이트', 180, font(32, 'reg'), TEXT_SUB)
    panel(d, 200, 320, W - 400, 580)
    points = []
    if s['tss'] > 250:
        points.append('• 고강도 라이딩 — 72시간 회복 윈도우 필수')
    elif s['tss'] > 150:
        points.append('• 중강도 베이스 — 48시간 회복 후 다음 자극')
    if s['decoupling_pct'] > 10:
        points.append('• 디커플링 높음 — 영양·페이싱 점검 필요')
    elif s['decoupling_pct'] < 5:
        points.append('• 디커플링 양호 — 영양·페이싱 효과적')
    else:
        points.append('• 디커플링 중간 — 후반 영양·수분 추가 권장')
    if s['avg_cadence'] < 80:
        points.append(f"• 케이던스 {s['avg_cadence']}rpm — 80+로 끌어올려 근피로 지연")
    else:
        points.append(f"• 케이던스 {s['avg_cadence']}rpm — 양호")
    if A.get('best_climb') and A.get('fade_climb'):
        b, fd = A['best_climb'], A['fade_climb']
        drop = (1 - fd['vam_m_per_h']/b['vam_m_per_h']) * 100 if b['vam_m_per_h'] else 0
        points.append(f"• 베스트(VAM {b['vam_m_per_h']:.0f}) vs 페이드(VAM {fd['vam_m_per_h']:.0f}) — {drop:.0f}% 차이")
    y = 380
    for p in points[:5]:
        text_xy(d, p, 270, y, font(36, 'reg'))
        y += 85
    img.save(out, optimize=True)


# ───── Card: 다음 라이딩 액션 ─────
def card_action(out, A, R, M, date_str):
    s = A['summary']
    img = Image.new('RGB', (W, H), BG_DARK)
    d = gradient_bg(img)
    text_centered(d, '다음 라이딩 액션', 80, font(72, 'ex'), ACCENT)
    text_centered(d, '오늘 데이터가 알려주는 3가지', 180, font(32, 'reg'), TEXT_SUB)
    panel(d, 200, 320, W - 400, 580)
    actions = []
    actions.append(('1. 사전 영양', '출발 30분 전 탄수 80g — 글리코겐 비축'))
    if s['decoupling_pct'] > 8:
        actions.append(('2. 보급 패턴', '시간당 60g 분할 (한 번에 1,000 kcal 금지)'))
    else:
        actions.append(('2. 보급 패턴', '현재 패턴 유지 + 거리 5~10% 증량 검토'))
    if s['avg_cadence'] < 85:
        actions.append(('3. 케이던스', f"오늘 {s['avg_cadence']}rpm → 85+ 의식적 유지"))
    else:
        actions.append(('3. 케이던스', f"오늘 {s['avg_cadence']}rpm — 그대로 유지"))
    y = 380
    for label, desc in actions:
        text_xy(d, label, 280, y, font(40, 'ex'), ACCENT2)
        text_xy(d, desc, 700, y + 8, font(34, 'reg'))
        y += 130
    img.save(out, optimize=True)


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_highlight_cards.py <ride_dir>")
    ride = Path(sys.argv[1])
    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    R = A.get('rider', {})
    try:
        M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        M = {'코스명': ride.name}

    # 일자 추출
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(A['ride_start_utc'].replace('Z', '+00:00'))
        date_str = dt.strftime('%Y.%m.%d')
    except Exception:
        date_str = ''

    out_dir = ride / 'output_videos' / '_cards'
    out_dir.mkdir(parents=True, exist_ok=True)

    # 베스트/페이드 클라임
    best = A.get('best_climb')
    fade = A.get('fade_climb')

    cards = [
        ('card1_overview.png',         lambda p: card_overview(p, A, R, M, date_str)),
        ('card2_glossary.png',         lambda p: card_glossary(p, A, R, M, date_str)),
        ('card_course_profile.png',    lambda p: card_course_profile(p, A, R, M, date_str)),
        ('card_course_climbs.png',     lambda p: card_course_climbs(p, A, R, M, date_str)),
        ('card_best_climb_intro.png',  lambda p: card_climb_intro(p, A, R, M, date_str, best, 'best') if best else None),
        ('card_transition.png',        lambda p: card_transition(p, A, R, M, date_str)),
        ('card_fade_climb_intro.png',  lambda p: card_climb_intro(p, A, R, M, date_str, fade, 'fade') if fade else None),
        ('card3_analysis.png',         lambda p: card_analysis(p, A, R, M, date_str)),
        ('card_conclusion.png',        lambda p: card_conclusion(p, A, R, M, date_str)),
        ('card_action.png',            lambda p: card_action(p, A, R, M, date_str)),
    ]
    for name, fn in cards:
        out_path = out_dir / name
        result = fn(out_path)
        if result is None and not out_path.exists():
            print(f"  - {name} (skip — 데이터 부족)")
        else:
            print(f"  ✓ {name}")
    print(f"\n  산출물 폴더: {out_dir}")


if __name__ == '__main__':
    main()
