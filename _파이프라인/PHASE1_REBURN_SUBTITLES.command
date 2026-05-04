#!/bin/bash
# Phase 1: 자막 재번인 복구 (Mac Mini용)
# - 손상된 자막싱크본 삭제
# - coaching_synced.srt → ASS 변환
# - hevc_videotoolbox로 자막 번인 (10~20분 예상)
# - 산출물 검증 (moov atom, duration)
#
# 실행: Finder에서 더블클릭 또는 터미널에서 bash PHASE1_REBURN_SUBTITLES.command

set -e

# ----- 경로 설정 -----
RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
PIPE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"

OUT_DIR="$RIDE_DIR/output_videos"
SRC="$OUT_DIR/전체_라이딩_오버레이.mp4"
SYNCED="$RIDE_DIR/coaching_synced.srt"
OUTPUT="$OUT_DIR/전체_라이딩_오버레이_자막싱크.mp4"
LOG="$RIDE_DIR/phase1_reburn.log"

# ----- ffmpeg 경로 자동 탐지 -----
if [ -x "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" ]; then
  FFMPEG="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
  FFPROBE="/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
elif command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG="$(command -v ffmpeg)"
  FFPROBE="$(command -v ffprobe)"
else
  echo "✗ ffmpeg 미설치. 'brew install ffmpeg-full' 또는 'brew install ffmpeg' 후 재실행"
  exit 1
fi

clear
echo "=========================================="
echo "  Phase 1: 자막 재번인 복구 (Mac Mini)"
echo "=========================================="
echo "  ffmpeg: $FFMPEG"
echo "  로그:   $LOG"
echo ""

exec > >(tee -a "$LOG") 2>&1

# ----- [1/5] 사전 점검 -----
echo "[1/5] 입력 파일 점검..."
[ ! -f "$SRC" ] && { echo "  ✗ 입력 누락: $SRC"; exit 1; }
[ ! -f "$SYNCED" ] && { echo "  ✗ 자막 누락: $SYNCED"; exit 1; }
[ ! -f "$PIPE_DIR/lib/srt_to_ass.py" ] && { echo "  ✗ srt_to_ass.py 누락"; exit 1; }
SRC_SIZE_GB=$(echo "scale=1; $(stat -f%z "$SRC") / 1073741824" | bc)
SRC_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$SRC")
SRC_DUR_MIN=$(printf '%.1f' "$(echo "$SRC_DUR/60" | bc -l)")
echo "  ✓ 원본 본편: ${SRC_SIZE_GB}GB / ${SRC_DUR_MIN}분"
echo "  ✓ 싱크 자막: $(wc -l < "$SYNCED" | tr -d ' ')줄"
echo ""

# ----- [2/5] 손상 파일 정리 -----
echo "[2/5] 손상 파일 정리..."
if [ -f "$OUTPUT" ]; then
  CORRUPT_SIZE=$(stat -f%z "$OUTPUT")
  CORRUPT_MB=$((CORRUPT_SIZE / 1024 / 1024))
  # moov atom 검증으로 손상 여부 판단
  if "$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT" >/dev/null 2>&1; then
    echo "  → 기존 파일이 정상으로 보임 (${CORRUPT_MB}MB) — 안전을 위해 .bak로 이동"
    mv "$OUTPUT" "${OUTPUT}.bak.$(date +%Y%m%d_%H%M%S)"
  else
    rm "$OUTPUT" && echo "  ✓ 손상 파일 삭제 (${CORRUPT_MB}MB, moov atom 없음)"
  fi
else
  echo "  → 기존 자막싱크본 없음 (clean state)"
fi
echo ""

# ----- [3/5] ASS 자막 생성 -----
echo "[3/5] SRT → ASS 변환 (한글 폰트: AppleSDGothicNeo)..."
TMP=$(mktemp -d -t syncburn); trap "rm -rf '$TMP'" EXIT
python3 "$PIPE_DIR/lib/srt_to_ass.py" "$SYNCED" "$TMP/c.ass" "AppleSDGothicNeo"
echo "  ✓ ASS 생성: $(wc -l < "$TMP/c.ass" | tr -d ' ')줄"
echo ""

# ----- [4/5] ffmpeg 자막 번인 -----
echo "[4/5] ffmpeg 자막 번인 (hevc_videotoolbox, 절전 방지)..."
echo "      예상 소요: 10~20분 (M-series 기준)"
echo "      Google Drive 동기화 일시정지 권고"
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
echo "  ✓ 인코딩 완료: ${ELAPSED}초 ($((ELAPSED / 60))분 $((ELAPSED % 60))초)"
echo ""

# ----- [5/5] 산출물 검증 -----
echo "[5/5] 산출물 검증..."
[ ! -f "$OUTPUT" ] && { echo "  ✗ 출력 파일 미생성"; exit 1; }
OUT_SIZE=$(stat -f%z "$OUTPUT")
OUT_GB=$(echo "scale=2; $OUT_SIZE / 1073741824" | bc)

# moov atom 확인
if ! "$FFPROBE" -v error "$OUTPUT" >/dev/null 2>&1; then
  echo "  ✗ moov atom 또는 컨테이너 이상 — 재실행 필요"
  exit 1
fi

OUT_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
OUT_DUR_MIN=$(printf '%.1f' "$(echo "$OUT_DUR/60" | bc -l)")
DUR_DIFF=$(echo "$SRC_DUR - $OUT_DUR" | bc | tr -d '-')
DUR_DIFF_OK=$(echo "$DUR_DIFF < 1.0" | bc)

echo "  ✓ moov atom 정상"
echo "  ✓ 파일 크기: ${OUT_GB}GB"
echo "  ✓ duration:  ${OUT_DUR_MIN}분 (원본 ${SRC_DUR_MIN}분, 차이 ${DUR_DIFF}초)"

if [ "$DUR_DIFF_OK" != "1" ]; then
  echo "  ⚠ duration 차이 1초 초과 — 수동 검증 권고"
fi

echo ""
echo "=========================================="
echo "✓ Phase 1 완료"
echo "  산출물: $OUTPUT"
echo "  ${OUT_GB}GB / ${OUT_DUR_MIN}분 / ${ELAPSED}초 인코딩"
echo "=========================================="
echo ""
echo "다음: Phase 2 (나레이션 합성) 진행"
