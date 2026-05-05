#!/bin/bash
# Phase 0: GoPro 4K + Garmin .fit → 1080p 오버레이 본편 + SRT 시간 보정
# - lib/build_overlay_pipeline.py 호출 (PNG 렌더 + ffmpeg 합성 + concat)
# - lib/shift_for_trim.py 호출 (SRT/_meta.json 트림 영상 타임라인 정렬)
# 예상 시간: 60~90분 (라이딩 길이 + 4K 양에 따라)

set -e
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/_common.sh"

resolve_ride_dir "$@"
detect_ffmpeg
load_ride_metadata
init_log "phase0_overlay"

clear
print_header "Phase 0: 오버레이 + 시간 정렬"

# 사전 점검
[ ! -f "$RIDE_DIR/_videos.json" ] && { echo "✗ _videos.json 없음 — RUN_RIDE.command 먼저 실행"; exit 1; }
[ ! -f "$RIDE_DIR/_analysis.json" ] && { echo "✗ _analysis.json 없음 — RUN_RIDE.command 먼저 실행"; exit 1; }
[ ! -f "$RIDE_DIR/coaching.srt" ] && { echo "✗ coaching.srt 없음 — RUN_RIDE.command 먼저 실행"; exit 1; }

# ----- [1] 오버레이 파이프라인 -----
echo "[1] build_overlay_pipeline.py..."
echo "    예상: PNG 렌더 + ffmpeg 합성 + concat ≈ 60~90분"
echo ""
caffeinate -i python3 "$LIB_DIR/build_overlay_pipeline.py" "$RIDE_DIR"

OVERLAY="$OUT_DIR/전체_라이딩_오버레이.mp4"
[ ! -f "$OVERLAY" ] && { echo "  ✗ 오버레이 영상 미생성"; exit 1; }
GB=$(echo "scale=2; $(stat -f%z "$OVERLAY") / 1073741824" | bc)
DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OVERLAY")
echo ""
echo "  ✓ 오버레이 본편: ${GB}GB / $(printf '%.1f' "$(echo "$DUR/60" | bc -l)")분"
echo ""

# ----- [2] SRT/meta 시간 정렬 (트림된 영상 타임라인) -----
echo "[2] shift_for_trim.py — SRT/메타 정렬..."
python3 "$LIB_DIR/shift_for_trim.py" "$RIDE_DIR"
echo ""

echo "=========================================="
echo "✓ Phase 0 완료"
echo "  산출물: $OVERLAY"
echo "=========================================="
echo ""
echo "다음: PHASE1_REBURN_SUBTITLES.command"
