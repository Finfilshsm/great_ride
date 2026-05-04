#!/bin/bash
# 유튜브 업로드 패키지 자동 생성
# - yt_metadata.md (제목/설명/태그)
# - yt_chapters.txt (챕터 마커, TDF 인트로 +10s 오프셋 적용)
# - yt_thumbnail.png (1920x1080, 카드 디자인 톤)

set -e

RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
LOG="$RIDE_DIR/yt_package.log"

exec > >(tee -a "$LOG") 2>&1

clear
echo "=========================================="
echo "  유튜브 업로드 패키지 생성"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# ----- [1] 메타데이터(md) + 챕터(txt) 생성 -----
echo "[1] 메타데이터 + 챕터 마커 생성..."
python3 << PYEOF
import json
from pathlib import Path

RIDE = Path("$RIDE_DIR")
ride_meta = json.load(open(RIDE / "ride_meta.json"))
analysis = json.load(open(RIDE / "_analysis.json"))

s = analysis["summary"]
b = analysis["best_climb"]
fade = analysis["fade_climb"]
r = analysis["rider"]

# ----- 제목 (3가지 후보) -----
titles = [
    f"[그란폰도 시뮬레이션] {ride_meta['코스명']} {s['distance_km']}km · TSS {s['tss']} — 같은 경사 다른 결과, 영양 패턴이 만든 -17% 페이드",
    f"{ride_meta['코스명']} {s['distance_km']}km 그란폰도 라이딩 — Climb #{b['index']}(VAM {b['vam_m_per_h']:.0f}) vs Climb #{fade['index']}(VAM {fade['vam_m_per_h']:.0f}) 데이터 분석",
    f"FTP {r['ftp_w']}W 라이더의 그란폰도 시뮬레이션 — {ride_meta['코스명']} 73.9km · TSS 303 데이터로 본 후반 페이드의 진짜 원인",
]

# ----- 설명 -----
desc = f'''🚴 {ride_meta['코스명']} ({ride_meta['코스_설명']}) — {ride_meta['출발지']} 출발
{ride_meta['코스_약자_풀이']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 라이딩 지표
━━━━━━━━━━━━━━━━━━━━━━━━━━━
▸ 거리:    {s['distance_km']}km
▸ 상승:    +{s['elev_gain_m']}m  ({s['elev_per_km']}m/km)
▸ 경과시간: {s['elapsed_h']}  (주행 {s['moving_h']})
▸ 평균속도: {s['avg_speed_kmh']} km/h

▸ 평균파워: {s['avg_power_w']}W (NP {s['np_w']}W)
▸ TSS:    {s['tss']}    IF: {s['if_']}    VI: {s['vi']}
▸ 평균HR: {s['avg_hr']} bpm  (Max {s['max_hr']})
▸ 평균케이던스: {s['avg_cadence']} rpm
▸ Pw:Hr 디커플링: {s['decoupling_pct']}%  (5% 이하 정상)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 라이더 프로파일
━━━━━━━━━━━━━━━━━━━━━━━━━━━
▸ FTP:  {r['ftp_w']}W
▸ 체중: {r['weight_kg']}kg
▸ W/kg: {r['w_per_kg']}  (Cat 4~5 진입권)
▸ LTHR: {r['lthr']} bpm

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 오늘의 코칭 포인트
━━━━━━━━━━━━━━━━━━━━━━━━━━━
같은 7%대 경사임에도 Climb #{b['index']}(km {b['start_km']:.1f}, VAM {b['vam_m_per_h']:.0f})는 베스트 페이싱,
Climb #{fade['index']}(km {fade['start_km']:.1f}, VAM {fade['vam_m_per_h']:.0f})는 후반 페이드 -17%.

▶ 1차 원인: 영양 패턴 (보급 1,600 kcal 일괄 섭취 → 위 부담·흡수율 저하)
▶ 데이터 근거: Pw:Hr 디커플링 {s['decoupling_pct']}% (정상 5% 이하)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 다음 라이딩 액션
━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 출발 30분 전 탄수 80g — 글리코겐 비축
2. 보급 시간당 60g 분할 (한 번에 1,000 kcal 금지)
3. 케이던스 80+ 유지 (오늘 평균 70rpm)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛠 데이터 출처
━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Garmin .fit (Edge / 파워미터)
- GoPro 4K 영상 → 1080p 게이지 오버레이
- OpenAI TTS 코칭 나레이션 (한국어 echo voice)
- 자체 분석 파이프라인 (cycling-tools)

#그란폰도 #사이클링 #FTP #TSS #파워미터 #VAM #그란폰도시뮬레이션 #헐몰헐 #DataRide #BigRide #사이클링코칭
'''

# ----- 챕터 마커 (TDF 인트로 +10s 오프셋) -----
chapters = '''0:00 인트로 (TDF 지도 · 채널 브랜딩)
0:15 헐몰헐 73.9km · TSS 303 라이딩 개요
1:10 Climb #1 진입 (5.0% × 0.8km · 출발 직후)
4:45 Climb #1 정점 (218W · IF 1.21)
15:23 Climb #2 (2.9% 회복 구간)
34:11 Climb #4 진입 (6.9% × 2.4km · 162m gain)
49:51 Climb #4 정점 (NP 188W · IF 1.04)
1:05:50 ★ Climb #5 — 베스트 페이싱 (VAM 713)
1:16:31 화면 점프 안내 (배터리 교체 50분)
1:25:18 CU 보급 — 영양 코칭 (1,600 kcal 경고)
1:43:44 롤링 47-50km — 탄수 부족 진단
1:52:26 ★ Climb #6 — 후반 페이드 (VAM 598)
1:59:06 Climb #6 중간 — 디커플링 진행
2:24:50 종합 평가 (TSS 303 · 회복 72h)
2:25:05 다음 라이딩 액션 3가지
'''

# ----- 태그 -----
tags = ", ".join([
    "그란폰도", "사이클링", "헐몰헐", "FTP", "TSS", "파워미터", "VAM",
    "그란폰도 시뮬레이션", "사이클링 코칭", "Data Ride", "Big Ride",
    "GoPro", "Garmin", "데이터 분석", "Climb 분석", "페이드", "영양 코칭",
    "디커플링", "사이클링 훈련", "라이더 코칭"
])

# ----- 마크다운 출력 -----
md_path = RIDE / "yt_metadata.md"
md = f'''# 유튜브 업로드 메타데이터 — {ride_meta['코스명']} ({s['distance_km']}km)

## 제목 후보
1. **{titles[0]}**
2. {titles[1]}
3. {titles[2]}

## 설명 (Description)
```
{desc.strip()}
```

## 태그 (Tags)
```
{tags}
```

## 카테고리
스포츠 (Sports)

## 시청자층
- 일반 (모든 사용자 대상)
- 아동용 콘텐츠 아님

## 추천 설정
- 화질: 1080p HEVC
- 자막: 자동 생성 + 수동 보정 권장 (coaching_synced.srt 활용)
- 최종 화면: 다음 라이딩 영상으로 연결
- 카드: Climb #5/#6 시점에 관련 분석 영상 카드
'''
md_path.write_text(md, encoding='utf-8')
print(f"  ✓ {md_path.name}")

# ----- 챕터 출력 -----
chap_path = RIDE / "yt_chapters.txt"
chap_path.write_text(chapters, encoding='utf-8')
print(f"  ✓ {chap_path.name} (15개 챕터)")
PYEOF
echo ""

# ----- [2] 썸네일 PNG 생성 (1920x1080) -----
echo "[2] 썸네일 PNG 생성..."
python3 << PYEOF
from PIL import Image, ImageDraw, ImageFont
import json
from pathlib import Path

RIDE = Path("$RIDE_DIR")
analysis = json.load(open(RIDE / "_analysis.json"))
ride_meta = json.load(open(RIDE / "ride_meta.json"))
s = analysis["summary"]
b = analysis["best_climb"]
fade = analysis["fade_climb"]

W, H = 1920, 1080
img = Image.new('RGB', (W, H), (12, 22, 38))
d = ImageDraw.Draw(img)

# 시스템 한글 폰트
SYS_FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
def f(sz, idx=0):
    try: return ImageFont.truetype(SYS_FONT, sz, index=idx)
    except Exception: return ImageFont.truetype(SYS_FONT, sz)

# 색상 팔레트 (카드 톤 통일)
ACCENT  = (255, 184, 76)
ACCENT2 = (102, 222, 178)
ACCENT3 = (255, 107, 107)
TEXT_M  = (245, 248, 252)
TEXT_S  = (170, 185, 210)
TEXT_D  = (110, 125, 150)

# 그라데이션 효과 (단순)
for y in range(H):
    alpha = y / H
    r0, g0, b0 = 12, 22, 38
    r1, g1, b1 = 28, 38, 58
    color = tuple(int(r0 + (r1-r0)*alpha) for r0, r1 in [(r0,r1),(g0,g1),(b0,b1)])
    d.line([(0, y), (W, y)], fill=color)

# 좌상단: 라이딩 식별
d.text((100, 90), "GRAN FONDO SIMULATION", font=f(34, 0), fill=TEXT_S)
d.line([(100, 145), (480, 145)], fill=ACCENT, width=4)

# 메인 타이틀: 코스명
d.text((100, 175), ride_meta['코스명'], font=f(180, 3), fill=ACCENT)
d.text((100, 380), f"{s['distance_km']}km · +{s['elev_gain_m']}m · TSS {s['tss']}",
       font=f(58, 2), fill=TEXT_M)

# 중앙: 핵심 메시지 (Climb 비교)
d.line([(100, 510), (1820, 510)], fill=(50, 65, 95), width=2)
d.text((100, 540), "같은 7%대 경사 — 다른 결과", font=f(46, 1), fill=TEXT_S)

# VAM 비교 (대형 숫자)
y_vam = 620
d.text((100, y_vam+30), "VAM", font=f(48, 0), fill=TEXT_S)
d.text((250, y_vam), str(int(b['vam_m_per_h'])), font=f(200, 3), fill=ACCENT2)
d.text((620, y_vam+50), "→", font=f(140, 0), fill=TEXT_M)
d.text((820, y_vam), str(int(fade['vam_m_per_h'])), font=f(200, 3), fill=ACCENT3)
d.text((1180, y_vam+30), "-17%", font=f(140, 3), fill=ACCENT3)

# 우상단: Climb 라벨
d.text((250, y_vam-50), f"Climb #{b['index']} 베스트", font=f(28, 1), fill=ACCENT2)
d.text((820, y_vam-50), f"Climb #{fade['index']} 페이드", font=f(28, 1), fill=ACCENT3)

# 하단: 채널 브랜딩
d.line([(100, 920), (1820, 920)], fill=(50, 65, 95), width=2)
d.text((100, 945), "DATA-DRIVEN COACHING", font=f(28, 0), fill=TEXT_D)
d.text((100, 990), "Data Ride · 그란폰도 시뮬레이션", font=f(48, 2), fill=ACCENT)

# 우측: 일자
d.text((1700, 945), "2026.5.2", font=f(30, 0), fill=TEXT_S)
d.text((1620, 990), "헐몰헐 코스", font=f(36, 2), fill=TEXT_M)

# 모서리 액센트
d.rectangle([0, 0, 12, H], fill=ACCENT)

# 저장 (1920x1080 + 1280x720 두 사이즈)
out_path = RIDE / "yt_thumbnail.png"
img.save(out_path, optimize=True)
print(f"  ✓ {out_path.name} (1920x1080)")

# 1280x720 리사이즈본도 생성 (유튜브 권장 사이즈)
img_720 = img.resize((1280, 720), Image.LANCZOS)
out_720 = RIDE / "yt_thumbnail_1280x720.png"
img_720.save(out_720, optimize=True)
print(f"  ✓ {out_720.name} (1280x720, 유튜브 권장)")
PYEOF
echo ""

# ----- [3] 결과 요약 -----
echo "=========================================="
echo "✓ 유튜브 업로드 패키지 생성 완료"
echo "=========================================="
echo ""
echo "산출물 위치: $RIDE_DIR/"
ls -lh "$RIDE_DIR/yt_metadata.md" "$RIDE_DIR/yt_chapters.txt" \
       "$RIDE_DIR/yt_thumbnail.png" "$RIDE_DIR/yt_thumbnail_1280x720.png" 2>/dev/null \
  | awk '{printf "  %s  %s\n", $5, $9}' | sed "s|$RIDE_DIR/||"
echo ""
echo "사용 방법:"
echo "  1. yt_metadata.md — 제목/설명/태그 복사하여 유튜브 업로드 폼에 붙여넣기"
echo "  2. yt_chapters.txt — 설명 끝부분에 추가 (유튜브 자동 챕터 인식)"
echo "  3. yt_thumbnail_1280x720.png — 커스텀 썸네일 업로드"
