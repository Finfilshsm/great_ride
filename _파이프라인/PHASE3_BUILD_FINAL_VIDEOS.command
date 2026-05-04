#!/bin/bash
# Phase 3: 하이라이트 영상 + 본편 결합 통합 빌드 (표준값)
# - 인트로(card1_overview 10s) / 아웃트로(신규 디자인 8s) 빌드
# - 카드 PNG 8개 mp4 변환 (페이드인/아웃)
# - 본편에서 Climb #5 (1:05:40~), Climb #6 (1:52:16~) 각 90s 발췌
# - 13개 클립 concat (stream copy) → 하이라이트 raw
# - BGM 사이드체인 덕킹 → 하이라이트 최종
# - 본편 + 인트로 + 아웃트로 stream copy concat → 본편 최종
# - 양쪽 ffprobe 검증

set -e

# ----- 경로 -----
RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
TOOLS_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"
CARDS_DIR="$TOOLS_DIR/highlight_b"
BGM_DIR="$TOOLS_DIR/bgm"
OUT_DIR="$RIDE_DIR/output_videos"
WORK_DIR="$OUT_DIR/_phase3_work"
LOG="$RIDE_DIR/phase3_build.log"

MAIN_VIDEO="$OUT_DIR/전체_라이딩_오버레이_자막싱크_나레이션.mp4"
BGM_FILE="$BGM_DIR/Chase The Sun - Bel Tempo.mp3"

DATE_TAG="2026-05-02"
HIGHLIGHT_OUT="$OUT_DIR/하이라이트_헐몰헐_${DATE_TAG}.mp4"
FULL_OUT="$OUT_DIR/본편_최종_헐몰헐_${DATE_TAG}.mp4"

mkdir -p "$WORK_DIR"
exec > >(tee -a "$LOG") 2>&1

# ----- ffmpeg PATH -----
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi
FFMPEG="$(command -v ffmpeg)"
FFPROBE="$(command -v ffprobe)"
[ -z "$FFMPEG" ] && { echo "✗ ffmpeg 없음"; exit 1; }

clear
echo "=========================================="
echo "  Phase 3: 하이라이트 + 본편 결합"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  ffmpeg: $FFMPEG"
echo "=========================================="
echo ""

# ----- 입력 점검 -----
echo "[0] 입력 자산 점검..."
[ ! -f "$MAIN_VIDEO" ] && { echo "  ✗ 본편 누락: $MAIN_VIDEO"; exit 1; }
[ ! -d "$CARDS_DIR" ] && { echo "  ✗ 카드 폴더 누락"; exit 1; }
[ ! -f "$BGM_FILE" ] && { echo "  ✗ BGM 누락: $BGM_FILE"; exit 1; }
echo "  ✓ 본편: $(du -h "$MAIN_VIDEO" | cut -f1)"
echo "  ✓ 카드 PNG: $(ls "$CARDS_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')개"
echo "  ✓ BGM: $(basename "$BGM_FILE")"
echo ""

# ----- [A] 아웃트로 PNG 신규 생성 -----
echo "[A] 아웃트로 PNG 신규 생성..."
OUTRO_PNG="$WORK_DIR/card_outro.png"
python3 << PYEOF
from PIL import Image, ImageDraw, ImageFont
W, H = 1920, 1080
img = Image.new('RGB', (W, H), (18, 24, 38))
d = ImageDraw.Draw(img)

FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'

def f(sz, idx=0):
    try:
        return ImageFont.truetype(FONT, sz, index=idx)
    except Exception:
        return ImageFont.truetype(FONT, sz)

def centered(txt, y, font, color):
    bb = d.textbbox((0,0), txt, font=font)
    tw = bb[2]-bb[0]
    d.text(((W-tw)//2, y), txt, font=font, fill=color)

centered("Thank you for watching", 340, f(72, 1), (255, 184, 76))
centered("다음 라이딩에서 만나요", 460, f(56, 2), (240, 244, 250))
d.line([(W//2-200, 580), (W//2+200, 580)], fill=(255, 184, 76), width=3)
centered("DATA-DRIVEN COACHING", 620, f(28, 0), (160, 175, 200))
centered("그란폰도 시뮬레이션 · 헐몰헐 · 73.9km", 670, f(36, 1), (240, 244, 250))
centered("GoPro + Garmin .fit · OpenAI TTS · ffmpeg", 950, f(20, 0), (110, 125, 150))

img.save("$OUTRO_PNG", optimize=True)
print("  ✓ 아웃트로 PNG 생성: $OUTRO_PNG")
PYEOF
echo ""

# ----- [B] PNG → mp4 변환 함수 -----
png_to_mp4() {
  local PNG="$1"; local DUR="$2"; local OUT="$3"
  local FADE_OUT_ST
  FADE_OUT_ST=$(echo "$DUR - 0.5" | bc)
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

echo "[B] 카드/인트로/아웃트로 mp4 변환..."
declare -a CARD_LIST=(
  "card1_overview.png|10|01_intro_overview.mp4"
  "card2_glossary.png|12|02_glossary.mp4"
  "card_course_profile.png|6|03_course_profile.mp4"
  "card_course_climbs.png|6|04_course_climbs.mp4"
  "card_climb5_intro.png|4|05_climb5_intro.mp4"
  "card_transition.png|7|07_transition.mp4"
  "card_climb6_intro.png|4|08_climb6_intro.mp4"
  "card3_analysis.png|14|10_analysis.mp4"
  "card_conclusion.png|12|11_conclusion.mp4"
  "card_action.png|12|12_action.mp4"
)

START=$(date +%s)
for entry in "${CARD_LIST[@]}"; do
  IFS='|' read -r PNG_NAME DUR OUT_NAME <<< "$entry"
  PNG_PATH="$CARDS_DIR/$PNG_NAME"
  OUT_PATH="$WORK_DIR/$OUT_NAME"
  if [ ! -f "$PNG_PATH" ]; then
    echo "  ✗ 카드 PNG 누락: $PNG_NAME"
    exit 1
  fi
  printf "  → %-30s (%2ss)\n" "$OUT_NAME" "$DUR"
  png_to_mp4 "$PNG_PATH" "$DUR" "$OUT_PATH"
done
printf "  → %-30s (%2ss)\n" "13_outro.mp4" "8"
png_to_mp4 "$OUTRO_PNG" "8" "$WORK_DIR/13_outro.mp4"
echo "  ✓ 카드 mp4 변환 완료: $(($(date +%s)-START))초"
echo ""

# ----- [C] 본편 발췌 (Climb #5/#6) -----
echo "[C] 본편 발췌 (Climb #5: 1:05:40~+90s, Climb #6: 1:52:16~+90s)..."

trim_main() {
  local FAST_SS="$1"   # keyframe 빠른 seek
  local FINE_SS="$2"   # frame accurate
  local DUR="$3"
  local OUT="$4"
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel error -stats \
    -ss "$FAST_SS" -i "$MAIN_VIDEO" -ss "$FINE_SS" -t "$DUR" \
    -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
    -c:a aac -b:a 192k -ar 48000 \
    -video_track_timescale 30000 \
    -movflags +faststart \
    "$OUT"
}

START=$(date +%s)
echo "  → 06_climb5_excerpt.mp4 (1:05:40 + 90s)"
trim_main "01:05:00" "00:00:40" "90" "$WORK_DIR/06_climb5_excerpt.mp4"
echo "  → 09_climb6_excerpt.mp4 (1:52:16 + 90s)"
trim_main "01:51:30" "00:00:46" "90" "$WORK_DIR/09_climb6_excerpt.mp4"
echo "  ✓ 발췌 완료: $(($(date +%s)-START))초"
echo ""

# ----- [D] 시퀀스 concat (stream copy) -----
echo "[D] 13개 클립 concat (stream copy)..."
CONCAT_LIST="$WORK_DIR/_concat_highlight.txt"
{
  echo "file '$WORK_DIR/01_intro_overview.mp4'"
  echo "file '$WORK_DIR/02_glossary.mp4'"
  echo "file '$WORK_DIR/03_course_profile.mp4'"
  echo "file '$WORK_DIR/04_course_climbs.mp4'"
  echo "file '$WORK_DIR/05_climb5_intro.mp4'"
  echo "file '$WORK_DIR/06_climb5_excerpt.mp4'"
  echo "file '$WORK_DIR/07_transition.mp4'"
  echo "file '$WORK_DIR/08_climb6_intro.mp4'"
  echo "file '$WORK_DIR/09_climb6_excerpt.mp4'"
  echo "file '$WORK_DIR/10_analysis.mp4'"
  echo "file '$WORK_DIR/11_conclusion.mp4'"
  echo "file '$WORK_DIR/12_action.mp4'"
  echo "file '$WORK_DIR/13_outro.mp4'"
} > "$CONCAT_LIST"

HIGHLIGHT_RAW="$WORK_DIR/highlight_raw.mp4"
START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c copy \
  -movflags +faststart \
  "$HIGHLIGHT_RAW"
echo "  ✓ concat 완료: $(($(date +%s)-START))초 / $(du -h "$HIGHLIGHT_RAW" | cut -f1)"
echo ""

# ----- [E] BGM 사이드체인 덕킹 -----
echo "[E] BGM 사이드체인 덕킹 (Chase The Sun - Bel Tempo)..."
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
  -shortest \
  -movflags +faststart \
  "$HIGHLIGHT_OUT"
echo "  ✓ BGM 덕킹 완료: $(($(date +%s)-START))초"
echo ""

# ----- [F] 본편 + 인트로 + 아웃트로 결합 -----
echo "[F] 본편 + 인트로 + 아웃트로 결합 (stream copy)..."
FULL_CONCAT="$WORK_DIR/_concat_full.txt"
{
  echo "file '$WORK_DIR/01_intro_overview.mp4'"
  echo "file '$MAIN_VIDEO'"
  echo "file '$WORK_DIR/13_outro.mp4'"
} > "$FULL_CONCAT"

START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$FULL_CONCAT" \
  -c copy \
  -movflags +faststart \
  "$FULL_OUT"
echo "  ✓ 본편 결합 완료: $(($(date +%s)-START))초"
echo ""

# ----- [G] 검증 -----
echo "[G] 산출물 검증..."
verify() {
  local OUT="$1"; local LABEL="$2"
  if [ ! -f "$OUT" ]; then
    echo "  ✗ $LABEL 미생성"
    return 1
  fi
  local SIZE GB DUR DUR_MIN
  SIZE=$(stat -f%z "$OUT")
  GB=$(echo "scale=2; $SIZE / 1073741824" | bc)
  DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUT")
  DUR_MIN=$(printf '%.2f' "$(echo "$DUR/60" | bc -l)")
  if "$FFPROBE" -v error "$OUT" >/dev/null 2>&1; then
    echo "  ✓ $LABEL"
    echo "      $(basename "$OUT")"
    echo "      ${GB}GB / ${DUR_MIN}분 / moov atom 정상"
  else
    echo "  ✗ $LABEL: moov atom 또는 컨테이너 이상"
    return 1
  fi
}

verify "$HIGHLIGHT_OUT" "하이라이트 (유튜브용)"
verify "$FULL_OUT" "본편 최종 (인트로+본편+아웃트로)"

echo ""
echo "=========================================="
echo "✓ Phase 3 완료"
echo ""
echo "  하이라이트: $HIGHLIGHT_OUT"
echo "  본편 최종:  $FULL_OUT"
echo "=========================================="
echo ""
echo "임시 작업 폴더 정리 (선택):"
echo "  rm -rf '$WORK_DIR'"
