#!/bin/bash
# Phase 2: 나레이션 합성 (일반화 버전)
# - 자동 prep: rewrite_narration → generate_narration → sync_srt_to_narration (없으면)
# - 입력: 자막싱크본 + _narration_echo/*.mp3 + _meta.json
# - 출력: 자막싱크_나레이션.mp4 (BG 0.5x + 나레이션 2.5x amix)

set -e
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/_common.sh"

resolve_ride_dir "$@"
detect_ffmpeg
load_ride_metadata
init_log "phase2_narration"

clear
print_header "Phase 2: 나레이션 합성"

NARR_DIR="$OUT_DIR/_narration_echo"
META="$NARR_DIR/_meta.json"
INPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크.mp4"
NARR_TRACK="$OUT_DIR/_narration_full_echo.wav"
OUTPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크_나레이션.mp4"

# ----- [0] 입력 점검 -----
echo "[0] 입력 자산 점검..."
[ ! -f "$INPUT" ] && { echo "  ✗ 자막싱크본 없음: $INPUT"; echo "    Phase 1 먼저 실행"; exit 1; }
echo "  ✓ 자막싱크본"
echo ""

# ----- [1] 나레이션 prep (없으면 자동 생성) -----
if [ ! -f "$META" ]; then
  echo "[1] 나레이션 자산 자동 생성..."
  if [ -z "$OPENAI_API_KEY" ]; then
    echo "  ✗ OPENAI_API_KEY 미설정 — TTS 합성 필요. ~/.zshrc에 export OPENAI_API_KEY=\"sk-...\" 추가"
    exit 1
  fi

  # 1-1) coaching.srt → narration.srt (GPT 친근체)
  if [ ! -f "$RIDE_DIR/narration.srt" ]; then
    echo "  → rewrite_narration.py (GPT-4o-mini)..."
    python3 "$LIB_DIR/rewrite_narration.py" "$RIDE_DIR"
  else
    echo "  → narration.srt 존재 (skip)"
  fi

  # 1-2) narration.srt → MP3 + _meta.json (TTS)
  echo "  → generate_narration.py (echo voice)..."
  python3 "$LIB_DIR/generate_narration.py" "$RIDE_DIR/narration.srt" "$NARR_DIR" echo gpt-4o-mini-tts

  # 1-3) coaching.srt + MP3 길이 → coaching_synced.srt
  if [ ! -f "$RIDE_DIR/coaching_synced.srt" ]; then
    echo "  → sync_srt_to_narration.py..."
    python3 "$LIB_DIR/sync_srt_to_narration.py" "$RIDE_DIR/coaching.srt" "$NARR_DIR" "$RIDE_DIR/coaching_synced.srt"
  fi
  echo ""
else
  echo "[1] 나레이션 자산 존재 (skip)"
  echo ""
fi

# ----- [2] _meta.json 경로 보정 (다른 환경에서 만들어진 경우) -----
echo "[2] _meta.json 경로 보정..."
cp "$META" "$META.bak.$(date +%Y%m%d_%H%M%S)"
python3 << PYEOF
import json, os
META = "$META"; NARR_DIR = "$NARR_DIR"
data = json.load(open(META))
changed = 0
for item in data:
    bn = os.path.basename(item['file'])
    new = os.path.join(NARR_DIR, bn)
    if item['file'] != new:
        item['file'] = new; changed += 1
json.dump(data, open(META,'w'), ensure_ascii=False, indent=2)
print(f"  ✓ {changed}개 경로 보정 / 총 {len(data)}개")
PYEOF
echo ""

# ----- [3] mp3 캐시 검증 -----
echo "[3] TTS mp3 캐시 검증..."
N=$(python3 -c "import json; print(len(json.load(open('$META'))))")
MISSING=$(python3 -c "
import json, os
data = json.load(open('$META'))
print(len([1 for x in data if not os.path.isfile(x['file'])]))
")
[ "$MISSING" -gt 0 ] && { echo "  ✗ ${MISSING}개 mp3 누락"; exit 1; }
echo "  ✓ ${N}개 mp3 캐시 모두 정상"
echo ""

# ----- [4] 나레이션 통합 WAV 생성 -----
echo "[4] 나레이션 통합 WAV 생성..."
INPUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$INPUT")
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
echo "  ✓ WAV: ${WAV_ELAPSED}초 ($(du -h "$NARR_TRACK" | cut -f1))"
echo ""

# ----- [5] 영상 + 나레이션 믹싱 -----
echo "[5] 영상 + 나레이션 믹싱..."
START=$(date +%s)
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
  -i "$INPUT" -i "$NARR_TRACK" \
  -filter_complex "[0:a]volume=0.5[bg];[1:a]volume=2.5[fg];[bg][fg]amix=inputs=2:duration=first:normalize=0[final]" \
  -map 0:v -map "[final]" \
  -c:v copy \
  -c:a aac -b:a 192k -movflags +faststart \
  "$OUTPUT"
MIX_ELAPSED=$(($(date +%s) - START))
echo "  ✓ 믹싱: ${MIX_ELAPSED}초 ($((MIX_ELAPSED/60))분)"
echo ""

# ----- [6] 검증 -----
[ ! -f "$OUTPUT" ] && { echo "  ✗ 출력 미생성"; exit 1; }
OUT_GB=$(echo "scale=2; $(stat -f%z "$OUTPUT") / 1073741824" | bc)
OUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
OUT_DUR_MIN=$(printf '%.1f' "$(echo "$OUT_DUR/60" | bc -l)")
echo "[6] 검증 ✓ ${OUT_GB}GB / ${OUT_DUR_MIN}분"

echo ""
echo "=========================================="
echo "✓ Phase 2 완료"
echo "  산출물: $OUTPUT"
echo "=========================================="
echo ""
echo "다음: Phase 3 (인트로/하이라이트/본편 결합) 진행"
