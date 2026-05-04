"""하이라이트 클립 B용 인트로 대시보드 PNG 생성."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import koreanize_matplotlib
import os

W, H = 1920, 1080
OUT_DIR = "/sessions/relaxed-inspiring-mayer/mnt/outputs/highlight_b"
Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

FONT_DIR = "/sessions/relaxed-inspiring-mayer/.local/lib/python3.10/site-packages/koreanize_matplotlib/fonts"
F_REG  = f"{FONT_DIR}/NanumGothic.ttf"
F_BOLD = f"{FONT_DIR}/NanumGothicBold.ttf"
F_EX   = f"{FONT_DIR}/NanumGothicExtraBold.ttf"

def f(path, sz): return ImageFont.truetype(path, sz)

# 색상 팔레트
BG_DARK    = (18, 24, 38)        # 짙은 네이비
BG_PANEL   = (28, 38, 58)        # 패널 배경
ACCENT     = (255, 184, 76)      # 오렌지 (액센트)
ACCENT2    = (102, 222, 178)     # 민트 (긍정)
ACCENT3    = (255, 107, 107)     # 코랄 (경고)
TEXT_MAIN  = (240, 244, 250)
TEXT_SUB   = (160, 175, 200)
TEXT_DIM   = (110, 125, 150)
DIVIDER    = (50, 65, 95)

def draw_text_centered(d, text, y, font, color=TEXT_MAIN):
    bb = d.textbbox((0, 0), text, font=font)
    tw = bb[2] - bb[0]
    d.text(((W - tw) // 2, y), text, font=font, fill=color)

def draw_text_xy(d, text, x, y, font, color=TEXT_MAIN, anchor="lt"):
    if anchor == "lt":
        d.text((x, y), text, font=font, fill=color)
    elif anchor == "rt":
        bb = d.textbbox((0, 0), text, font=font)
        d.text((x - (bb[2]-bb[0]), y), text, font=font, fill=color)
    elif anchor == "ct":
        bb = d.textbbox((0, 0), text, font=font)
        d.text((x - (bb[2]-bb[0])//2, y), text, font=font, fill=color)

def panel(d, x, y, w, h, fill=BG_PANEL):
    d.rounded_rectangle([x, y, x+w, y+h], radius=18, fill=fill, outline=DIVIDER, width=2)

# ───────────────────────────────────────────
# Card 1 — 라이딩 개요
# ───────────────────────────────────────────
def card1():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)

    # 헤더
    draw_text_centered(d, "그란폰도 훈련 — 헐몰헐", 60, f(F_EX, 64), TEXT_MAIN)
    draw_text_centered(d, "2026.5.2 (토) · 토일동 출발", 145, f(F_REG, 32), TEXT_SUB)

    # 가로선
    d.line([(W//2-200, 200), (W//2+200, 200)], fill=ACCENT, width=3)

    # 4-quadrant 핵심 지표
    quad_w, quad_h = 800, 220
    pad = 40
    cx_l = W//2 - quad_w - pad//2
    cx_r = W//2 + pad//2
    quads = [
        (cx_l, 240, "거리 / 상승", "73.9 km", "+1,327 m  (18 m/km)", ACCENT),
        (cx_r, 240, "시간 / 평균속도", "4시간 35분", "주행 18.3 km/h", ACCENT),
        (cx_l, 480, "강도 (TSS · IF · VI)", "303 · 0.88 · 1.26", "회복 72시간 권장", ACCENT3),
        (cx_r, 480, "라이더 (FTP · 체중 · W/kg)", "180W · 73kg", "2.47 W/kg (Cat 4~5)", ACCENT2),
    ]
    for x, y, label, big, small, col in quads:
        panel(d, x, y, quad_w, quad_h)
        draw_text_xy(d, label, x+30, y+20, f(F_REG, 26), TEXT_SUB)
        draw_text_xy(d, big,   x+30, y+58, f(F_EX, 64), col)
        draw_text_xy(d, small, x+30, y+150, f(F_REG, 28), TEXT_MAIN)

    # 하단 라벨
    draw_text_centered(d, "오늘의 데이터로 본 코칭 분석", 760, f(F_BOLD, 38), TEXT_MAIN)
    draw_text_centered(d, "Climb #5 (베스트) vs Climb #6 (페이드) 비교", 815, f(F_REG, 28), ACCENT)

    # 푸터
    d.line([(60, 1000), (W-60, 1000)], fill=DIVIDER, width=1)
    draw_text_centered(d, "DATA-DRIVEN COACHING · GoPro + Garmin .fit", 1025, f(F_REG, 20), TEXT_DIM)

    img.save(f"{OUT_DIR}/card1_overview.png", optimize=True)
    print(f"  ✓ card1_overview.png")

# ───────────────────────────────────────────
# Card 2 — 용어 사전
# ───────────────────────────────────────────
def card2():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)

    # 헤더
    draw_text_centered(d, "사이클링 데이터 용어 사전", 50, f(F_EX, 56), TEXT_MAIN)
    draw_text_centered(d, "본 영상에서 사용되는 핵심 지표 8개", 130, f(F_REG, 26), TEXT_SUB)
    d.line([(W//2-200, 175), (W//2+200, 175)], fill=ACCENT, width=2)

    # 4x2 그리드
    terms = [
        ("FTP",     "Functional Threshold Power",    "1시간 유지 가능한 최대 평균 파워 (W)",                ACCENT),
        ("NP",      "Normalized Power",              "변동성을 반영한 가중 평균 파워 (W)",                  ACCENT),
        ("IF",      "Intensity Factor",              "NP ÷ FTP — 1.00이면 임계치 강도",                     ACCENT),
        ("TSS",     "Training Stress Score",         "강도 × 시간 합산. 100 = FTP로 1시간",                 ACCENT),
        ("VI",      "Variability Index",             "NP ÷ 평균파워 — 1.10 이하가 좋은 페이싱",             ACCENT2),
        ("VAM",     "Velocità Ascensionale Media",   "시간당 등반 고도 (m/h) — 700+이 그란폰도 강자",       ACCENT2),
        ("디커플링", "Aerobic Decoupling (Pw:Hr)",    "동일 파워 시 심박 상승률 — 5% 이하가 정상",          ACCENT3),
        ("W/kg",    "Power-to-Weight Ratio",          "체중 대비 파워. 카테고리 분류 기준",                  ACCENT3),
    ]
    cell_w, cell_h = 880, 180
    pad_x, pad_y = 50, 30
    grid_x0 = (W - cell_w*2 - pad_x) // 2
    grid_y0 = 220
    for i, (term, en, desc, col) in enumerate(terms):
        col_idx = i % 2
        row_idx = i // 2
        x = grid_x0 + col_idx * (cell_w + pad_x)
        y = grid_y0 + row_idx * (cell_h + pad_y)
        panel(d, x, y, cell_w, cell_h)
        # 색상 막대
        d.rounded_rectangle([x, y, x+10, y+cell_h], radius=4, fill=col)
        draw_text_xy(d, term, x+30, y+18, f(F_EX, 44), col)
        draw_text_xy(d, en, x+30, y+78, f(F_REG, 22), TEXT_DIM)
        draw_text_xy(d, desc, x+30, y+118, f(F_BOLD, 26), TEXT_MAIN)

    img.save(f"{OUT_DIR}/card2_glossary.png", optimize=True)
    print(f"  ✓ card2_glossary.png")

# ───────────────────────────────────────────
# Card 3 — 분석 포인트
# ───────────────────────────────────────────
def card3():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)

    draw_text_centered(d, "오늘의 코칭 포인트", 70, f(F_EX, 64), TEXT_MAIN)
    draw_text_centered(d, "같은 7% 경사 — Climb #5 vs Climb #6", 175, f(F_BOLD, 36), ACCENT)
    d.line([(W//2-300, 240), (W//2+300, 240)], fill=ACCENT, width=2)

    # 좌우 비교 카드
    card_w, card_h = 780, 580
    pad = 60
    lx = W//2 - card_w - pad//2
    rx = W//2 + pad//2
    cy = 290

    # Climb #5 (베스트)
    panel(d, lx, cy, card_w, card_h, fill=(35, 60, 50))
    d.rounded_rectangle([lx, cy, lx+12, cy+card_h], radius=4, fill=ACCENT2)
    draw_text_xy(d, "Climb #5", lx+40, cy+30, f(F_EX, 56), ACCENT2)
    draw_text_xy(d, "베스트 페이싱", lx+40, cy+105, f(F_BOLD, 32), TEXT_MAIN)
    draw_text_xy(d, "km 20.2 · 7.8% × 1.7km", lx+40, cy+165, f(F_REG, 26), TEXT_SUB)

    metrics_5 = [
        ("VAM",      "713 m/h",   "그란폰도 강자 수준"),
        ("평균 파워", "172 W",     "IF 0.96 (임계치)"),
        ("심박",      "159 bpm",   "Z3 안정 유지"),
        ("페이드",    "없음",      "후반까지 유지"),
    ]
    for i, (k, v, note) in enumerate(metrics_5):
        my = cy + 240 + i*70
        draw_text_xy(d, k, lx+50, my, f(F_BOLD, 26), TEXT_SUB)
        draw_text_xy(d, v, lx+220, my, f(F_EX, 32), ACCENT2)
        draw_text_xy(d, note, lx+400, my+5, f(F_REG, 22), TEXT_MAIN)

    # Climb #6 (페이드)
    panel(d, rx, cy, card_w, card_h, fill=(60, 40, 40))
    d.rounded_rectangle([rx, cy, rx+12, cy+card_h], radius=4, fill=ACCENT3)
    draw_text_xy(d, "Climb #6", rx+40, cy+30, f(F_EX, 56), ACCENT3)
    draw_text_xy(d, "후반 페이드", rx+40, cy+105, f(F_BOLD, 32), TEXT_MAIN)
    draw_text_xy(d, "km 50.0 · 7.7% × 2.2km", rx+40, cy+165, f(F_REG, 26), TEXT_SUB)

    metrics_6 = [
        ("VAM",      "598 m/h",   "-17% (#5 대비)"),
        ("평균 파워", "146 W",     "IF 0.81 (-15W)"),
        ("심박",      "163 bpm",   "더 높은 심박"),
        ("디커플링",  "+19.8%",    "후반 누적 피로"),
    ]
    for i, (k, v, note) in enumerate(metrics_6):
        my = cy + 240 + i*70
        draw_text_xy(d, k, rx+50, my, f(F_BOLD, 26), TEXT_SUB)
        draw_text_xy(d, v, rx+220, my, f(F_EX, 32), ACCENT3)
        draw_text_xy(d, note, rx+400, my+5, f(F_REG, 22), TEXT_MAIN)

    # 하단 임팩트 카피
    d.rounded_rectangle([100, 920, W-100, 1010], radius=18, fill=(45, 35, 50), outline=ACCENT, width=2)
    draw_text_centered(d, "▶  같은 경사, 다른 결과 — 데이터로 보는 영양·페이싱의 영향", 945, f(F_BOLD, 32), ACCENT)

    img.save(f"{OUT_DIR}/card3_analysis.png", optimize=True)
    print(f"  ✓ card3_analysis.png")

# ───────────────────────────────────────────
# Climb #5 도입 카드
# ───────────────────────────────────────────
def card_climb5_intro():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)
    draw_text_centered(d, "Part 1", 380, f(F_REG, 36), TEXT_DIM)
    draw_text_centered(d, "Climb #5 — 베스트 페이싱", 440, f(F_EX, 80), ACCENT2)
    draw_text_centered(d, "km 20.2 · 7.8% × 1.7km · VAM 713", 560, f(F_BOLD, 36), TEXT_MAIN)
    draw_text_centered(d, "이 페이스를 몸이 기억하도록 집중", 630, f(F_REG, 30), TEXT_SUB)
    img.save(f"{OUT_DIR}/card_climb5_intro.png")
    print(f"  ✓ card_climb5_intro.png")

# ───────────────────────────────────────────
# 전환 카드 (Climb #5 → #6)
# ───────────────────────────────────────────
def card_transition():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)
    draw_text_centered(d, "그러나, 같은 경사 다른 결과가 후반에 발생", 220, f(F_BOLD, 36), TEXT_SUB)
    draw_text_centered(d, "VAM  713  ->  598", 320, f(F_EX, 88), ACCENT3)
    draw_text_centered(d, "-17 %", 440, f(F_EX, 100), ACCENT3)

    # 비교 표
    panel(d, W//2-500, 600, 1000, 280)
    rows = [
        ("",          "Climb #5",       "Climb #6"),
        ("VAM",        "713 m/h",       "598 m/h  (-17%)"),
        ("평균 파워",  "172 W",         "146 W  (-15%)"),
        ("심박",        "159 bpm",      "163 bpm  (+4)"),
    ]
    for i, (a, b, c) in enumerate(rows):
        my = 620 + i*60
        col = ACCENT if i==0 else TEXT_MAIN
        font_use = f(F_EX, 28) if i==0 else f(F_BOLD, 28)
        draw_text_xy(d, a, W//2-460, my, font_use, col)
        draw_text_xy(d, b, W//2-150, my, font_use, ACCENT2 if i>0 else col)
        draw_text_xy(d, c, W//2+150, my, font_use, ACCENT3 if i>0 else col)

    draw_text_centered(d, "왜 이런 차이가 발생했을까?", 950, f(F_BOLD, 32), ACCENT)
    img.save(f"{OUT_DIR}/card_transition.png")
    print(f"  ✓ card_transition.png")

# ───────────────────────────────────────────
# Climb #6 도입 카드
# ───────────────────────────────────────────
def card_climb6_intro():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)
    draw_text_centered(d, "Part 2", 380, f(F_REG, 36), TEXT_DIM)
    draw_text_centered(d, "Climb #6 — 후반 페이드", 440, f(F_EX, 80), ACCENT3)
    draw_text_centered(d, "km 50.0 · 7.7% × 2.2km · VAM 598", 560, f(F_BOLD, 36), TEXT_MAIN)
    draw_text_centered(d, "라이딩 2시간 41분 경과 시점 · 영양 패턴이 만든 결과", 630, f(F_REG, 30), TEXT_SUB)
    img.save(f"{OUT_DIR}/card_climb6_intro.png")
    print(f"  ✓ card_climb6_intro.png")

# ───────────────────────────────────────────
# 결론 카드
# ───────────────────────────────────────────
def card_conclusion():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)
    draw_text_centered(d, "결론", 80, f(F_EX, 64), TEXT_MAIN)
    d.line([(W//2-100, 175), (W//2+100, 175)], fill=ACCENT, width=3)
    draw_text_centered(d, "차이는 영양 패턴", 230, f(F_EX, 80), ACCENT)
    draw_text_centered(d, "보급 1,600 kcal 일괄섭취 → 위 부담·흡수율 저하 → 후반 출력 -17%", 360, f(F_BOLD, 32), TEXT_MAIN)
    draw_text_centered(d, "베이스 부족이 아닌, 연료 관리 실패가 1차 원인", 425, f(F_REG, 28), TEXT_SUB)

    panel(d, 200, 530, W-400, 360, fill=(35, 50, 70))
    draw_text_xy(d, "데이터 근거", 240, 555, f(F_EX, 36), ACCENT)
    rows = [
        "▸ 0~25km : BCAA 음료만 (탄수 0g) — 거의 공복 라이딩",
        "▸ 40km 보급 : 소세지 + 땅콩 + 크림빵 = 1,600 kcal 일괄",
        "▸ 50~74km : 물·콜라만 (탄수 시간당 ~30g, 권장의 절반)",
        "▸ Pw:Hr 디커플링 19.8% (5% 이하가 정상)",
    ]
    for i, t in enumerate(rows):
        draw_text_xy(d, t, 260, 620 + i*55, f(F_BOLD, 28), TEXT_MAIN)

    img.save(f"{OUT_DIR}/card_conclusion.png")
    print(f"  ✓ card_conclusion.png")

# ───────────────────────────────────────────
# 다음 액션 카드
# ───────────────────────────────────────────
def card_action():
    img = Image.new('RGB', (W, H), BG_DARK)
    d = ImageDraw.Draw(img)
    draw_text_centered(d, "다음 라이딩 액션", 80, f(F_EX, 64), TEXT_MAIN)
    d.line([(W//2-150, 175), (W//2+150, 175)], fill=ACCENT, width=3)

    actions = [
        ("01", "출발 30분 전 탄수 80g 섭취",
               "오늘은 공복 시작 — 글리코겐 비축 부족으로 후반 페이드 가속",
               ACCENT),
        ("02", "보급은 시간당 60g 분할",
               "한 번에 1,000 kcal 금지 — 위 부담 ↑, 흡수율 ↓",
               ACCENT2),
        ("03", "케이던스 80+ 유지",
               "오늘 평균 70 rpm — 동일 파워에서 근피로 가속",
               ACCENT3),
    ]
    for i, (num, title, desc, col) in enumerate(actions):
        y = 240 + i*220
        panel(d, 150, y, W-300, 180)
        d.rounded_rectangle([150, y, 162, y+180], radius=4, fill=col)
        draw_text_xy(d, num, 200, y+30, f(F_EX, 80), col)
        draw_text_xy(d, title, 380, y+35, f(F_EX, 44), TEXT_MAIN)
        draw_text_xy(d, desc, 380, y+105, f(F_REG, 28), TEXT_SUB)

    img.save(f"{OUT_DIR}/card_action.png")
    print(f"  ✓ card_action.png")

card1(); card2(); card3()
card_climb5_intro(); card_transition(); card_climb6_intro()
card_conclusion(); card_action()
print("\n모든 대시보드 PNG 생성 완료")
