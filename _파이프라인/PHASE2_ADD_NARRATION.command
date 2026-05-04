#!/bin/bash
# Phase 2: 나레이션 합성 (캐시 모드, OPENAI_API_KEY 불요)
# - _meta.json 경로 자동 보정 (맥북프로 → 맥미니)
# - 기존 TTS 캐시 mp3 사용 (신규 호출 없음)
# - 자막싱크본 + 나레이션 사이드체인 덕킹 (BG 0.5x + 나레이션 2.5x)
# - 산출물 검증 (moov atom, duration, 오디오 트랙)

set -e

# ----- 경로 -----
RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
OUT_DIR="$RIDE_DIR/output_videos"
NARR_DIR="$OUT_DIR/_narration_echo"
META="$NARR_DIR/_meta.json"
INPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크.mp4"
NARR_TRACK="$OUT_DIR/_narration_full_echo.wav"
OUTPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크_나레이션.mp4"
LOG="$RIDE_DIR/phase2_narration.log"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

# ----- ffmpeg PATH -----
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi

if command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG="$(command -v ffmpeg)"
  FFPROBE="$(command -v ffprobe)"
else
  echo "✗ ffmpeg 미설치"
  exit 1
fi

clear
echo "=========================================="
echo "  Phase 2: 나레이션 합성 (캐시 모드)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  ffmpeg: $FFMPEG"
echo "=========================================="
echo ""

# ----- [1/5] 입력 파일 점검 -----
echo "[1/5] 입력 파일 점검..."
[ ! -f "$INPUT" ] && { echo "  ✗ 자막싱크본 없음: $INPUT"; exit 1; }
[ ! -f "$META" ] && { echo "  ✗ _meta.json 없음: $META"; exit 1; }
INPUT_SIZE=$(echo "scale=1; $(stat -f%z "$INPUT") / 1073741824" | bc)
INPUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$INPUT")
INPUT_DUR_MIN=$(printf '%.1f' "$(echo "$INPUT_DUR/60" | bc -l)")
echo "  ✓ 자막싱크본: ${INPUT_SIZE}GB / ${INPUT_DUR_MIN}분"
echo "  ✓ _meta.json: $(stat -f%z "$META") bytes"
echo ""

# ----- [2/5] _meta.json 경로 자동 보정 -----
echo "[2/5] _meta.json 경로 보정 (맥북프로 → 맥미니)..."
BACKUP="$META.bak.$(date +%Y%m%d_%H%M%S)"
cp "$META" "$BACKUP"
echo "  ✓ 백업: $BACKUP"

python3 << PYEOF
import json, os, sys

META = "$META"
NARR_DIR = "$NARR_DIR"

with open(META) as f:
    data = json.load(f)

changed = 0
for item in data:
    old_file = item['file']
    basename = os.path.basename(old_file)
    new_file = os.path.join(NARR_DIR, basename)
    if old_file != new_file:
        item['file'] = new_file
        changed += 1

with open(META, 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"  ✓ 경로 항목 {changed}개 보정 (총 {len(data)}개 항목)")
PYEOF
echo ""

# ----- [3/5] TTS 캐시 mp3 존재 검증 -----
echo "[3/5] TTS 캐시 mp3 존재 검증..."
N=$(python3 -c "import json; print(len(json.load(open('$META'))))")
echo "  → 나레이션 cue: $N개"

MISSING=$(python3 -c "
import json, os
data = json.load(open('$META'))
missing = [i for i,x in enumerate(data) if not os.path.isfile(x['file'])]
print(len(missing))
")

if [ "$MISSING" -gt 0 ]; then
  echo "  ✗ ${MISSING}개 mp3 누락 — 경로 보정 또는 캐시 손상 진단 필요"
  python3 -c "
import json, os
data = json.load(open('$META'))
for i,x in enumerate(data):
    if not os.path.isfile(x['file']): print(f'    [{i+1}] missing: {x[\"file\"]}')
"
  exit 1
fi
echo "  ✓ ${N}개 mp3 캐시 모두 정상"
echo ""

# ----- [4/5] 나레이션 통합 + 사이드체인 덕킹 -----
echo "[4/5] 나레이션 합성 (BG 0.5x + 나레이션 2.5x amix)..."
echo ""

# Step 4-1: 나레이션 통합 WAV 생성
echo "  [4-1/2] 나레이션 통합 WAV 생성..."
INPUT_ARGS=()
FILTER=""
LABELS=""
for i in $(seq 0 $((N-1))); do
  J=$((i+1))
  F=$(python3 -c "import json; print(json.load(open('$META'))[$i]['file'])")
  START_S=$(python3 -c "import json; print(json.load(open('$META'))[$i]['start_s'])")
  START_MS=$(python3 -c "print(int($START_S * 1000))")
  INPUT_ARGS+=(-i "$F")
  FILTER="${FILTER}[${i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,adelay=${START_MS}|${START_MS},volume=2.0[n${J}];"
  LABELS="${LABELS}[n${J}]"
done
FILTER="${FILTER}${LABELS}amix=inputs=${N}:duration=longest:normalize=0[narr_out]"

START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  "${INPUT_ARGS[@]}" \
  -filter_complex "$FILTER" \
  -map "[narr_out]" -t "$INPUT_DUR" \
  -ar 48000 -ac 2 -sample_fmt s16 \
  "$NARR_TRACK"
WAV_ELAPSED=$(($(date +%s) - START))
echo "  ✓ WAV 생성 완료: ${WAV_ELAPSED}초 ($(du -h "$NARR_TRACK" | cut -f1))"
echo ""

# Step 4-2: 영상 + 나레이션 WAV 믹싱 (audio re-encode, video copy)
echo "  [4-2/2] 영상 + 나레이션 믹싱 (video copy + audio re-encode)..."
START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
  -i "$INPUT" -i "$NARR_TRACK" \
  -filter_complex "[0:a]volume=0.5[bg];[1:a]volume=2.5[fg];[bg][fg]amix=inputs=2:duration=first:normalize=0[final]" \
  -map 0:v -map "[final]" \
  -c:v copy \
  -c:a aac -b:a 192k -movflags +faststart \
  "$OUTPUT"
MIX_ELAPSED=$(($(date +%s) - START))
echo "  ✓ 합성 완료: ${MIX_ELAPSED}초 ($((MIX_ELAPSED/60))분 $((MIX_ELAPSED%60))초)"
echo ""

# ----- [5/5] 산출물 검증 -----
echo "[5/5] 산출물 검증..."
[ ! -f "$OUTPUT" ] && { echo "  ✗ 출력 파일 미생성"; exit 1; }
OUT_SIZE=$(stat -f%z "$OUTPUT")
OUT_GB=$(echo "scale=2; $OUT_SIZE / 1073741824" | bc)

if ! "$FFPROBE" -v error "$OUTPUT" >/dev/null 2>&1; then
  echo "  ✗ moov atom 또는 컨테이너 이상"
  exit 1
fi

OUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
OUT_DUR_MIN=$(printf '%.1f' "$(echo "$OUT_DUR/60" | bc -l)")
DUR_DIFF=$(echo "$INPUT_DUR - $OUT_DUR" | bc | tr -d '-')

echo "  ✓ moov atom 정상"
echo "  ✓ 파일 크기: ${OUT_GB}GB"
echo "  ✓ duration:  ${OUT_DUR_MIN}분 (입력 ${INPUT_DUR_MIN}분, 차이 ${DUR_DIFF}초)"

A_INFO=$("$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_name,channels,sample_rate,bit_rate -of default=nw=1 "$OUTPUT" | tr '\n' ' ')
echo "  ✓ 오디오: $A_INFO"

V_INFO=$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of default=nw=1 "$OUTPUT" | tr '\n' ' ')
echo "  ✓ 비디오: $V_INFO"

echo ""
echo "=========================================="
echo "✓ Phase 2 완료"
echo "  산출물: $OUTPUT"
echo "  ${OUT_GB}GB / ${OUT_DUR_MIN}분"
echo "  WAV 생성 ${WAV_ELAPSED}초 + 믹싱 ${MIX_ELAPSED}초"
echo "=========================================="
echo ""
echo "전체 파이프라인 종료. 임시 파일 정리는 다음 명령으로:"
echo "  rm \"$NARR_TRACK\""
