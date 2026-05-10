#!/bin/bash
# Phase 3: 하이라이트 + 본편 결합 (일반화 버전)
# - 카드 PNG 자동 생성 (build_highlight_cards.py)
# - 클라임 영상 발췌 시각은 _analysis.json + _videos.json에서 동적 계산
# - 인트로/아웃트로 PNG 동적 생성
# - 출력: 하이라이트_<코스>_<일자>.mp4, 본편_최종_<코스>_<일자>.mp4

set -e
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/_common.sh"

resolve_ride_dir "$@"
detect_ffmpeg
load_ride_metadata
init_log "phase3_build"

clear
print_header "Phase 3: 하이라이트 + 본편 결합"

CARDS_DIR="$OUT_DIR/_cards"
BGM_DIR="$TOOLS_DIR/bgm"
WORK_DIR="$OUT_DIR/_phase3_work"
MAIN_VIDEO="$OUT_DIR/전체_라이딩_오버레이_자막싱크_나레이션.mp4"

HIGHLIGHT_OUT="$OUT_DIR/하이라이트_${COURSE_NAME}_${DATE_TAG}.mp4"
FULL_OUT="$OUT_DIR/본편_최종_${COURSE_NAME}_${DATE_TAG}.mp4"

mkdir -p "$WORK_DIR"

# ----- [0] 입력 점검 -----
echo "[0] 입력 자산 점검..."
[ ! -f "$MAIN_VIDEO" ] && { echo "  ✗ 본편 누락: $MAIN_VIDEO"; echo "    Phase 2 먼저 실행"; exit 1; }
[ -d "$BGM_DIR" ] || { echo "  ⚠ BGM 폴더 없음 — 기본값 BGM 미적용"; }
BGM_FILE=$(find "$BGM_DIR" -maxdepth 1 -iname "*.mp3" 2>/dev/null | head -1)
echo "  ✓ 본편: $(du -h "$MAIN_VIDEO" | cut -f1)"
echo "  ✓ BGM: ${BGM_FILE:-(없음)}"
echo ""

# ----- [A] 카드 PNG 동적 생성 (라이딩 + 누적 + 한국 인트로) -----
echo "[A] 라이딩별 카드 PNG 동적 생성..."
python3 "$LIB_DIR/build_highlight_cards.py" "$RIDE_DIR"
echo ""
echo "[A2] 누적 athlete_db 갱신..."
python3 "$LIB_DIR/athlete_db.py" "$(dirname "$RIDE_DIR")" 2>&1 | tail -5
echo ""
echo "[A3] 진행도 카드 (journey · load · readiness)..."
python3 "$LIB_DIR/build_progress_cards.py" "$RIDE_DIR"
echo "[A3b] 시즌 트렌드 카드 (TSS·디커플링·CTL·Seorak 가능성)..."
python3 "$LIB_DIR/build_season_trend.py" "$RIDE_DIR"
echo "[A3c] 4-stage 페이싱 분석 카드 (라이딩 전반 흐름)..."
python3 "$LIB_DIR/build_4stage_card.py" "$RIDE_DIR"
echo "[A3d] Seorak GF 코스 매핑 카드 (오늘 climb ↔ A-race 유사 구간)..."
python3 "$LIB_DIR/build_seorak_mapping_card.py" "$RIDE_DIR"
echo ""
echo "[A4] 한국 지도 인트로 (참고용) + TDF 애니메이션 인트로 (메인)..."
python3 "$LIB_DIR/build_intro_korea_map.py" "$RIDE_DIR"
python3 "$LIB_DIR/build_intro_tdf_animated.py" "$RIDE_DIR"
echo ""
echo "[A5] 다각적 브리핑 마크다운..."
(cd "$LIB_DIR" && python3 build_athlete_briefing.py "$RIDE_DIR")
echo ""

# ----- [B] 아웃트로 PNG 신규 생성 (코스·거리 동적) -----
echo "[B] 아웃트로 PNG 생성..."
OUTRO_PNG="$WORK_DIR/card_outro.png"
python3 << PYEOF
import json
from PIL import Image, ImageDraw, ImageFont

ride_dir = "$RIDE_DIR"
A = json.load(open(ride_dir + "/_analysis.json"))
M = json.load(open(ride_dir + "/ride_meta.json"))
s = A['summary']
W, H = 1920, 1080

img = Image.new('RGB', (W, H), (18, 24, 38))
d = ImageDraw.Draw(img)
FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
def f(sz, idx=0):
    try: return ImageFont.truetype(FONT, sz, index=idx)
    except: return ImageFont.truetype(FONT, sz)
def cen(t, y, fnt, color):
    bb = d.textbbox((0,0), t, font=fnt); d.text(((W-(bb[2]-bb[0]))//2, y), t, font=fnt, fill=color)

cen("Thank you for watching", 340, f(72, 1), (255, 184, 76))
cen("다음 라이딩에서 만나요", 460, f(56, 2), (240, 244, 250))
d.line([(W//2-200, 580), (W//2+200, 580)], fill=(255, 184, 76), width=3)
cen("DATA-DRIVEN COACHING", 620, f(28, 0), (160, 175, 200))
cen(f"그란폰도 시뮬레이션 · {M.get('코스명','')} · {s['distance_km']}km", 670, f(36, 1), (240, 244, 250))
cen("GoPro + Garmin .fit · OpenAI TTS · ffmpeg", 950, f(20, 0), (110, 125, 150))
img.save("$OUTRO_PNG", optimize=True)
print(f"  ✓ {'$OUTRO_PNG'}")
PYEOF
echo ""

# ----- [C] PNG → mp4 변환 함수 -----
png_to_mp4() {
  local PNG="$1"; local DUR="$2"; local OUT="$3"
  local FADE_OUT_ST=$(echo "$DUR - 0.5" | bc)
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel error \
    -loop 1 -framerate 30000/1001 -i "$PNG" \
    -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 \
    -t "$DUR" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#121826,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st=${FADE_OUT_ST}:d=0.5" \
    -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
    -c:a aac -b:a 192k -ar 48000 \
    -video_track_timescale 30000 \
    -movflags +faststart \
    "$OUT"
}

echo "[C] 카드/아웃트로 mp4 변환..."
# 인트로는 TDF 애니메이션 mp4를 별도로 재인코딩 (CARD_LIST에서는 제외)
# 라이딩 데이터 → 설악 준비도 → CTL/ATL/TSB → 주간부하 → 용어 → 코스 → climb → 분석 → 결론 → 액션 → 아웃트로
declare -a CARD_LIST=(
  "card1_overview.png|8|01_intro_overview.mp4"
  "card_seorak_readiness.png|10|02a_seorak_readiness.mp4"
  "card_athlete_journey.png|8|02b_athlete_journey.mp4"
  "card_weekly_load.png|6|02c_weekly_load.mp4"
  "card_season_trend.png|10|02d_season_trend.mp4"
  "card_4stage_overview.png|12|02e_4stage.mp4"
  "card_seorak_mapping.png|12|02f_seorak_map.mp4"
  "card2_glossary.png|10|03_glossary.mp4"
  "card_course_profile.png|6|04_course_profile.mp4"
  "card_course_climbs.png|6|05_course_climbs.mp4"
  "card_best_climb_intro.png|4|06_best_intro.mp4"
  "card_transition.png|7|08_transition.mp4"
  "card_fade_climb_intro.png|4|09_fade_intro.mp4"
  "card3_analysis.png|12|11_analysis.mp4"
  "card_conclusion.png|12|12_conclusion.mp4"
  "card_action.png|12|13_action.mp4"
)
START=$(date +%s)
for entry in "${CARD_LIST[@]}"; do
  IFS='|' read -r PNG_NAME DUR OUT_NAME <<< "$entry"
  PNG_PATH="$CARDS_DIR/$PNG_NAME"
  OUT_PATH="$WORK_DIR/$OUT_NAME"
  if [ ! -f "$PNG_PATH" ]; then
    echo "  ⚠ 카드 누락 (skip): $PNG_NAME"
    continue
  fi
  printf "  → %-30s (%2ss)\n" "$OUT_NAME" "$DUR"
  png_to_mp4 "$PNG_PATH" "$DUR" "$OUT_PATH"
done
printf "  → %-30s (%2ss)\n" "14_outro.mp4" "8"
png_to_mp4 "$OUTRO_PNG" "8" "$WORK_DIR/14_outro.mp4"

# TDF 애니메이션 인트로 — 코덱·오디오 트랙 정규화 (concat 호환)
TDF_INTRO_SRC="$RIDE_DIR/output_videos/_cards/card_intro_tdf_animated.mp4"
TDF_INTRO_OUT="$WORK_DIR/00_intro_tdf.mp4"
if [ -f "$TDF_INTRO_SRC" ]; then
  printf "  → %-30s (TDF 애니, ~8s)\n" "00_intro_tdf.mp4"
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel error \
    -i "$TDF_INTRO_SRC" \
    -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 \
    -vf "format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st=7.5:d=0.5" \
    -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
    -c:a aac -b:a 192k -ar 48000 -shortest \
    -video_track_timescale 30000 \
    -movflags +faststart \
    "$TDF_INTRO_OUT"
else
  echo "  ✗ TDF 애니메이션 인트로 누락: $TDF_INTRO_SRC"
  exit 1
fi
echo "  ✓ ${#CARD_LIST[@]}+1+1 카드 변환: $(($(date +%s)-START))초"
echo ""

# ----- [D] 클라임 영상 발췌 시각 자동 계산 -----
echo "[D] 베스트/페이드 클라임 영상 시각 자동 계산..."
read BEST_VT BEST_START FADE_VT FADE_START <<< $(python3 - "$RIDE_DIR" << 'PYEOF'
import json, re, sys
from pathlib import Path
ride = Path(sys.argv[1])
A = json.load(open(ride/'_analysis.json'))
B = A.get('best_climb') or {}
F = A.get('fade_climb') or {}
# coaching.srt를 블록 단위로 파싱 → 정확한 climb 큐의 시각 매칭
srt = (ride/'coaching.srt').read_text(encoding='utf-8')
blocks = re.split(r'\n\s*\n', srt.strip())
def find_cue_for_climb(climb_idx):
    if not climb_idx: return None
    pat = re.compile(rf'\[Climb #\s*{climb_idx}\b')
    for blk in blocks:
        lines = blk.strip().split('\n')
        if len(lines) < 3: continue
        body = '\n'.join(lines[2:])
        if pat.search(body):
            ts = re.match(r'(\d{2}):(\d{2}):(\d{2})', lines[1])
            if ts:
                return ts.group(0)
    return None

best_t = find_cue_for_climb(B.get('index'))
fade_t = find_cue_for_climb(F.get('index'))
def offset_pair(t_str):
    if not t_str: return (None, None)
    h, m, s = map(int, t_str.split(':'))
    total = h*3600 + m*60 + s
    fast = max(0, total - 40)
    fast_str = f"{fast//3600:02d}:{(fast%3600)//60:02d}:{fast%60:02d}"
    fine = total - fast
    fine_str = f"00:{fine//60:02d}:{fine%60:02d}"
    return (fast_str, fine_str)
bf, bs = offset_pair(best_t)
ff, fs = offset_pair(fade_t)
print(bf or "01:00:00", bs or "00:00:00", ff or "01:30:00", fs or "00:00:00")
PYEOF
)
echo "  ✓ 베스트 클라임 발췌 위치: $BEST_VT (+ $BEST_START)"
echo "  ✓ 페이드 클라임 발췌 위치: $FADE_VT (+ $FADE_START)"
echo ""

trim_main() {
  local FAST_SS="$1"; local FINE_SS="$2"; local DUR="$3"; local OUT="$4"
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel error -stats \
    -ss "$FAST_SS" -i "$MAIN_VIDEO" -ss "$FINE_SS" -t "$DUR" \
    -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
    -c:a aac -b:a 192k -ar 48000 \
    -video_track_timescale 30000 \
    -movflags +faststart \
    "$OUT"
}

echo "[E] 클라임 영상 90초 발췌..."
START=$(date +%s)
echo "  → 07_best_excerpt.mp4"
trim_main "$BEST_VT" "$BEST_START" "90" "$WORK_DIR/07_best_excerpt.mp4"
echo "  → 10_fade_excerpt.mp4"
trim_main "$FADE_VT" "$FADE_START" "90" "$WORK_DIR/10_fade_excerpt.mp4"
echo "  ✓ 발췌: $(($(date +%s)-START))초"
echo ""

# ----- [F] 시퀀스 concat (15개 클립) -----
echo "[F] 15개 클립 concat (한국 인트로 → 라이딩 → 누적 분석 → 클라임 → 결론 → 아웃트로)..."
CONCAT_LIST="$WORK_DIR/_concat_highlight.txt"
{
  for f in 00_intro_tdf 01_intro_overview 02a_seorak_readiness 02b_athlete_journey 02c_weekly_load 02d_season_trend 02e_4stage 02f_seorak_map \
           03_glossary 04_course_profile 05_course_climbs \
           06_best_intro 07_best_excerpt 08_transition 09_fade_intro 10_fade_excerpt \
           11_analysis 12_conclusion 13_action 14_outro; do
    [ -f "$WORK_DIR/${f}.mp4" ] && echo "file '$WORK_DIR/${f}.mp4'"
  done
} > "$CONCAT_LIST"

HIGHLIGHT_RAW="$WORK_DIR/highlight_raw.mp4"
START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c copy \
  -movflags +faststart \
  "$HIGHLIGHT_RAW"
echo "  ✓ concat: $(($(date +%s)-START))초 / $(du -h "$HIGHLIGHT_RAW" | cut -f1)"
echo ""

# ----- [G] BGM 사이드체인 덕킹 (BGM 있을 때만) -----
if [ -n "$BGM_FILE" ] && [ -f "$BGM_FILE" ]; then
  echo "[G] BGM 사이드체인 덕킹..."
  START=$(date +%s)
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
    -i "$HIGHLIGHT_RAW" -stream_loop -1 -i "$BGM_FILE" \
    -filter_complex "
      [0:a]asplit=2[orig][key];
      [1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.7[bgm];
      [bgm][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300:level_sc=1[bgm_ducked];
      [orig][bgm_ducked]amix=inputs=2:duration=first:normalize=0[final]
    " \
    -map 0:v -map "[final]" \
    -c:v copy -c:a aac -b:a 192k -ar 48000 \
    -shortest -movflags +faststart \
    "$HIGHLIGHT_OUT"
  echo "  ✓ BGM 덕킹: $(($(date +%s)-START))초"
else
  echo "[G] BGM 없음 — raw 그대로 사용"
  cp "$HIGHLIGHT_RAW" "$HIGHLIGHT_OUT"
fi
echo ""

# ----- [H] 본편 + 인트로(한국 지도) + 아웃트로 결합 -----
echo "[H] 본편 + 한국 지도 인트로 + 아웃트로 결합..."
FULL_CONCAT="$WORK_DIR/_concat_full.txt"
{
  echo "file '$WORK_DIR/00_intro_tdf.mp4'"
  echo "file '$MAIN_VIDEO'"
  echo "file '$WORK_DIR/14_outro.mp4'"
} > "$FULL_CONCAT"
START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$FULL_CONCAT" \
  -c copy \
  -movflags +faststart \
  "$FULL_OUT"
echo "  ✓ 결합: $(($(date +%s)-START))초"
echo ""

# ----- [I] 검증 -----
echo "[I] 산출물 검증..."
verify() {
  local OUT="$1" LABEL="$2"
  [ ! -f "$OUT" ] && { echo "  ✗ $LABEL 미생성"; return 1; }
  local SIZE GB DUR DUR_MIN
  SIZE=$(stat -f%z "$OUT")
  GB=$(echo "scale=2; $SIZE / 1073741824" | bc)
  DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUT")
  DUR_MIN=$(printf '%.2f' "$(echo "$DUR/60" | bc -l)")
  if "$FFPROBE" -v error "$OUT" >/dev/null 2>&1; then
    echo "  ✓ $LABEL: ${GB}GB / ${DUR_MIN}분"
    echo "      $(basename "$OUT")"
  else
    echo "  ✗ $LABEL: moov atom 이상"; return 1
  fi
}
verify "$HIGHLIGHT_OUT" "하이라이트"
verify "$FULL_OUT" "본편 최종"

echo ""
echo "=========================================="
echo "✓ Phase 3 완료"
echo ""
echo "  하이라이트: $HIGHLIGHT_OUT"
echo "  본편 최종:  $FULL_OUT"
echo "=========================================="
