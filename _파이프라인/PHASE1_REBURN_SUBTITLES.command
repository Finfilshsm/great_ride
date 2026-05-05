#!/bin/bash
# Phase 1: 자막 재번인 (일반화 버전)
# - 입력: $RIDE_DIR/output_videos/전체_라이딩_오버레이.mp4 + $RIDE_DIR/coaching_synced.srt
# - 출력: $RIDE_DIR/output_videos/전체_라이딩_오버레이_자막싱크.mp4
#
# 실행 방법:
#   - 더블클릭 (Finder에서 폴더 선택 다이얼로그)
#   - 또는: RIDE_DIR="<경로>" bash PHASE1_REBURN_SUBTITLES.command
#   - 또는: bash PHASE1_REBURN_SUBTITLES.command "<경로>"

set -e
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/_common.sh"

resolve_ride_dir "$@"
detect_ffmpeg
load_ride_metadata
init_log "phase1_reburn"

clear
print_header "Phase 1: 자막 재번인"

SRC="$OUT_DIR/전체_라이딩_오버레이.mp4"
SYNCED="$RIDE_DIR/coaching_synced.srt"
OUTPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크.mp4"

# ----- [1/5] 사전 점검 -----
echo "[1/5] 입력 파일 점검..."
[ ! -f "$SRC" ] && { echo "  ✗ 입력 누락: $SRC"; echo "    먼저 build_overlay_pipeline.py 실행 필요"; exit 1; }
[ ! -f "$SYNCED" ] && { echo "  ✗ 자막 누락: $SYNCED"; echo "    먼저 sync_srt_to_narration.py 실행 필요"; exit 1; }
[ ! -f "$LIB_DIR/srt_to_ass.py" ] && { echo "  ✗ srt_to_ass.py 누락"; exit 1; }
SRC_SIZE_GB=$(echo "scale=1; $(stat -f%z "$SRC") / 1073741824" | bc)
SRC_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$SRC")
SRC_DUR_MIN=$(printf '%.1f' "$(echo "$SRC_DUR/60" | bc -l)")
echo "  ✓ 원본 본편: ${SRC_SIZE_GB}GB / ${SRC_DUR_MIN}분"
echo "  ✓ 싱크 자막: $(wc -l < "$SYNCED" | tr -d ' ')줄"
echo ""

# ----- [2/5] 손상 파일 정리 -----
echo "[2/5] 손상 파일 정리..."
if [ -f "$OUTPUT" ]; then
  if "$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT" >/dev/null 2>&1; then
    echo "  → 기존 파일 정상 — .bak로 이동"
    mv "$OUTPUT" "${OUTPUT}.bak.$(date +%Y%m%d_%H%M%S)"
  else
    rm "$OUTPUT" && echo "  ✓ 손상 파일 삭제"
  fi
else
  echo "  → 기존 자막싱크본 없음 (clean state)"
fi
echo ""

# ----- [3/5] ASS 자막 생성 -----
echo "[3/5] SRT → ASS 변환..."
TMP=$(mktemp -d -t syncburn); trap "rm -rf '$TMP'" EXIT
python3 "$LIB_DIR/srt_to_ass.py" "$SYNCED" "$TMP/c.ass" "AppleSDGothicNeo"
echo "  ✓ ASS 생성: $(wc -l < "$TMP/c.ass" | tr -d ' ')줄"
echo ""

# ----- [4/5] ffmpeg 자막 번인 -----
echo "[4/5] ffmpeg 자막 번인 (hevc_videotoolbox)..."
echo "      예상 소요: 10~30분"
echo ""
START=$(date +%s)
cd "$TMP"
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
  -i "$SRC" \
  -vf "subtitles=filename=c.ass" \
  -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 \
  -c:a copy \
  -movflags +faststart \
  "$OUTPUT"
ELAPSED=$(($(date +%s) - START))
echo ""
echo "  ✓ 인코딩: ${ELAPSED}초 ($((ELAPSED/60))분 $((ELAPSED%60))초)"
echo ""

# ----- [5/5] 검증 -----
echo "[5/5] 산출물 검증..."
[ ! -f "$OUTPUT" ] && { echo "  ✗ 출력 미생성"; exit 1; }
OUT_SIZE=$(stat -f%z "$OUTPUT")
OUT_GB=$(echo "scale=2; $OUT_SIZE / 1073741824" | bc)

if ! "$FFPROBE" -v error "$OUTPUT" >/dev/null 2>&1; then
  echo "  ✗ moov atom 또는 컨테이너 이상"; exit 1
fi
OUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
OUT_DUR_MIN=$(printf '%.1f' "$(echo "$OUT_DUR/60" | bc -l)")
DUR_DIFF=$(echo "$SRC_DUR - $OUT_DUR" | bc | tr -d '-')

echo "  ✓ moov atom 정상"
echo "  ✓ 파일 크기: ${OUT_GB}GB"
echo "  ✓ duration:  ${OUT_DUR_MIN}분 (원본 ${SRC_DUR_MIN}분, 차이 ${DUR_DIFF}초)"

echo ""
echo "=========================================="
echo "✓ Phase 1 완료"
echo "  산출물: $OUTPUT"
echo "=========================================="
echo ""
echo "다음: Phase 2 (나레이션 합성) 진행"
