#!/bin/bash
# 본편 자막을 나레이션 길이에 맞춰 자동 연장 + 재번인
# 사용법: SYNC_REBUILD_MAIN.command <ride_dir> [voice=echo] [model=gpt-4o-mini-tts]

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

RIDE_DIR="$1"; VOICE="${2:-echo}"; MODEL="${3:-gpt-4o-mini-tts}"
[ -z "$RIDE_DIR" ] && { echo "사용법: $0 <ride_dir> [voice] [model]"; exit 1; }

OUT_DIR="$RIDE_DIR/output_videos"
SRC="$OUT_DIR/전체_라이딩_오버레이.mp4"
COACHING="$RIDE_DIR/coaching.srt"
SYNCED="$RIDE_DIR/coaching_synced.srt"
OUTPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크.mp4"
NARR_DIR="$OUT_DIR/_narration_${VOICE}"

[ ! -f "$SRC" ] && { echo "✗ $SRC 없음 (자막 없는 원본 필요)"; exit 1; }
[ ! -f "$COACHING" ] && { echo "✗ $COACHING 없음"; exit 1; }

clear
echo "=========================================="
echo "  자막 ↔ 나레이션 싱크 + 본편 재번인"
echo "=========================================="

if [ ! -f "$RIDE_DIR/narration.srt" ] || [ "$COACHING" -nt "$RIDE_DIR/narration.srt" ]; then
  echo ""
  echo "[1/4] 친근 톤 나레이션 텍스트 생성..."
  python3 "$PIPE_DIR/lib/rewrite_narration.py" "$RIDE_DIR"
fi

echo ""
echo "[2/4] OpenAI TTS 생성 (${VOICE})..."
python3 "$PIPE_DIR/lib/generate_narration.py" "$RIDE_DIR/narration.srt" "$NARR_DIR" "$VOICE" "$MODEL"

echo ""
echo "[3/4] 자막 ↔ 나레이션 싱크 보정..."
python3 "$PIPE_DIR/lib/sync_srt_to_narration.py" "$COACHING" "$NARR_DIR" "$SYNCED"

echo ""
echo "[4/4] 보정된 자막 재번인..."
if [[ "$(uname -m)" == "arm64" ]]; then
  ENC="-c:v hevc_videotoolbox -q:v 50 -tag:v hvc1"
else
  ENC="-c:v libx264 -preset medium -crf 22"
fi

TMP=$(mktemp -d -t synced); trap "rm -rf '$TMP'" EXIT
python3 "$PIPE_DIR/lib/srt_to_ass.py" "$SYNCED" "$TMP/c.ass" "AppleSDGothicNeo"
cd "$TMP"
"$FFMPEG" -y -i "$SRC" -vf "subtitles=filename=c.ass" $ENC -c:a copy -movflags +faststart "$OUTPUT"

SIZE=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")
echo ""
echo "✓ 완료: $OUTPUT ($((SIZE/1024/1024))MB)"
