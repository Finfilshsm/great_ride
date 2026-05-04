#!/bin/bash
# OpenAI TTS 나레이션을 영상에 믹싱 (사이드체인 덕킹)
# 사용법: ADD_NARRATION.command <input.mp4> <ride_dir> [voice=echo] [model=gpt-4o-mini-tts]

set -e
[ -z "$OPENAI_API_KEY" ] && { echo "✗ OPENAI_API_KEY 미설정"; exit 1; }

if [ -x "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" ]; then
  FFMPEG="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
  FFPROBE="/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
else
  FFMPEG="ffmpeg"; FFPROBE="ffprobe"
fi

cd "$(dirname "$0")"
PIPE_DIR="$(pwd)"

INPUT="$1"; RIDE_DIR="$2"; VOICE="${3:-echo}"; MODEL="${4:-gpt-4o-mini-tts}"
[ -z "$INPUT" ] && { echo "사용법: $0 <input.mp4> <ride_dir> [voice] [model]"; exit 1; }

INPUT_DIR="$(dirname "$INPUT")"; INPUT_BASE="$(basename "$INPUT" .mp4)"
OUTPUT="$INPUT_DIR/${INPUT_BASE}_나레이션.mp4"
NARR_DIR="$INPUT_DIR/_narration_${VOICE}"
NARR_TRACK="$INPUT_DIR/_narration_full_${VOICE}.wav"

clear
echo "=========================================="
echo "  나레이션 추가 ($VOICE)"
echo "=========================================="

if [ ! -f "$RIDE_DIR/narration.srt" ] || [ "$RIDE_DIR/coaching.srt" -nt "$RIDE_DIR/narration.srt" ]; then
  python3 "$PIPE_DIR/lib/rewrite_narration.py" "$RIDE_DIR"
fi

echo "[1/2] TTS 생성/캐시..."
python3 "$PIPE_DIR/lib/generate_narration.py" "$RIDE_DIR/narration.srt" "$NARR_DIR" "$VOICE" "$MODEL"

META="$NARR_DIR/_meta.json"
N=$(python3 -c "import json; print(len(json.load(open('$META'))))")
VIDEO_DUR=$("$FFPROBE" -v quiet -show_entries format=duration -of csv=p=0 "$INPUT")

echo "[2/2] 나레이션 합본 + 영상 믹싱..."

# 나레이션 합본 WAV (병렬 입력)
INPUT_ARGS=""; FILTER=""; LABELS=""
for i in $(seq 1 $N); do
  IDX=$((i-1))
  F=$(python3 -c "import json,os; print(os.path.realpath(json.load(open('$META'))[$IDX]['file']))")
  START_S=$(python3 -c "import json; print(json.load(open('$META'))[$IDX]['start_s'])")
  START_MS=$(python3 -c "print(int($START_S * 1000))")
  INPUT_ARGS="$INPUT_ARGS -i \"$F\""
  FILTER+="[${IDX}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,adelay=${START_MS}|${START_MS},volume=2.0[n${i}];"
  LABELS+="[n${i}]"
done
FILTER+="${LABELS}amix=inputs=${N}:duration=longest:normalize=0[narr_out]"

eval "\"$FFMPEG\" -y $INPUT_ARGS \
  -filter_complex \"$FILTER\" \
  -map \"[narr_out]\" -t \"$VIDEO_DUR\" \
  -ar 48000 -ac 2 -sample_fmt s16 \
  \"$NARR_TRACK\"" 2>/dev/null

if [[ "$(uname -m)" == "arm64" ]]; then
  ENC="-c:v hevc_videotoolbox -q:v 50 -tag:v hvc1"
else
  ENC="-c:v libx264 -preset medium -crf 22"
fi

"$FFMPEG" -y -i "$INPUT" -i "$NARR_TRACK" \
  -filter_complex "[0:a]volume=0.5[bg];[1:a]volume=2.5[fg];[bg][fg]amix=inputs=2:duration=first:normalize=0[final]" \
  -map 0:v -map "[final]" $ENC -c:a aac -b:a 192k -movflags +faststart "$OUTPUT"

SIZE=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")
echo ""
echo "✓ 완료: $OUTPUT ($((SIZE/1024/1024))MB)"
