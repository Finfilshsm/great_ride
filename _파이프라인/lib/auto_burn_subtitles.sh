#!/bin/bash
# 자막 번인 (SRT → ASS 변환 후 ffmpeg subtitles 필터)
set -e
RIDE_DIR="$1"
PIPE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FFMPEG="${FFMPEG:-ffmpeg}"

INPUT="$RIDE_DIR/output_videos/전체_라이딩_오버레이.mp4"
OUTPUT="$RIDE_DIR/output_videos/전체_라이딩_오버레이_자막.mp4"
SRT="$RIDE_DIR/coaching.srt"

[ ! -f "$INPUT" ] && { echo "✗ $INPUT 없음"; exit 1; }
[ ! -f "$SRT" ] && { echo "✗ $SRT 없음"; exit 1; }

if [[ "$(uname -m)" == "arm64" ]]; then
  ENC="-c:v hevc_videotoolbox -q:v 50 -tag:v hvc1"; FONT="AppleSDGothicNeo"
else
  ENC="-c:v libx264 -preset medium -crf 22"; FONT="NanumGothic"
fi

TMP=$(mktemp -d -t srtburn); trap "rm -rf $TMP" EXIT
python3 "$PIPE_DIR/lib/srt_to_ass.py" "$SRT" "$TMP/c.ass" "$FONT"
cd "$TMP"
"$FFMPEG" -y -i "$INPUT" -vf "subtitles=c.ass" $ENC -c:a copy -movflags +faststart "$OUTPUT"
echo "✓ $OUTPUT"
