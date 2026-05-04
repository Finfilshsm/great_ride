#!/bin/bash
# 헐몰헐 라이딩 폴더 + cycling-tools 통합 정리
# - 임시 파일/폴더 영구 삭제
# - 중간 산출물 → _archive_yyyymmdd/ (검토 후 사용자가 영구 삭제)
# - 로그·백업·옛 _파이프라인 → archive
# - cycling-tools 일회용 .command → archive

set -e

RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
TOOLS_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"
ARCHIVE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/_archive_$(date +%Y%m%d)"

mkdir -p "$ARCHIVE_DIR"/{intermediate_videos,logs,oneoff_commands,old_pipeline,backups,demos}

clear
echo "=========================================="
echo "  헐몰헐 라이딩 정리 + 폴더 구조 정돈"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""
echo "Archive 위치: $ARCHIVE_DIR"
echo ""

move_to() {
  local DST="$1"; shift
  for f in "$@"; do
    if [ -e "$f" ]; then
      mv "$f" "$DST/" 2>/dev/null && echo "  → $(basename "$f")"
    fi
  done
}

remove_perm() {
  for f in "$@"; do
    if [ -e "$f" ]; then
      rm -rf "$f" && echo "  ✗ $(basename "$f")"
    fi
  done
}

# ----- [1] 중간 산출물 영상 → archive -----
echo "[1] 중간 산출물 영상 → archive/intermediate_videos/ (~71GB)"
move_to "$ARCHIVE_DIR/intermediate_videos" \
  "$RIDE_DIR/output_videos/전체_라이딩_오버레이.mp4" \
  "$RIDE_DIR/output_videos/전체_라이딩_오버레이_자막싱크.mp4" \
  "$RIDE_DIR/output_videos/전체_라이딩_오버레이_자막싱크_나레이션.mp4" \
  "$RIDE_DIR/output_videos/_narration_full_echo.wav" \
  "$RIDE_DIR/output_videos/전체_라이딩_오버레이_자막.srt" \
  "$RIDE_DIR/output_videos/전체_라이딩_오버레이_자막.ass"

for OV in "$RIDE_DIR/output_videos/"GX*_overlay.mp4; do
  [ -f "$OV" ] && mv "$OV" "$ARCHIVE_DIR/intermediate_videos/" && echo "  → $(basename "$OV")"
done
echo ""

# ----- [2] 데모 영상 → archive/demos -----
echo "[2] 작업 중 데모 영상 → archive/demos/"
for DM in "$RIDE_DIR/"데모_*.mp4; do
  [ -f "$DM" ] && mv "$DM" "$ARCHIVE_DIR/demos/" && echo "  → $(basename "$DM")"
done
echo ""

# ----- [3] 임시 폴더·파일 영구 삭제 -----
echo "[3] 임시 폴더·파일 영구 삭제..."
remove_perm \
  "$RIDE_DIR/output_videos/_phase3_work" \
  "$RIDE_DIR/output_videos/_concat.txt"
echo ""

# ----- [4] 백업 파일 → archive/backups -----
echo "[4] 백업 파일 → archive/backups/"
for BAK in "$RIDE_DIR/output_videos/_narration_echo/"_meta.json.bak.*; do
  [ -f "$BAK" ] && mv "$BAK" "$ARCHIVE_DIR/backups/" && echo "  → $(basename "$BAK")"
done
echo ""

# ----- [5] 로그 파일 → archive/logs -----
echo "[5] 로그 파일 → archive/logs/"
move_to "$ARCHIVE_DIR/logs" \
  "$RIDE_DIR/render.log" \
  "$RIDE_DIR/render_redo.log" \
  "$RIDE_DIR/phase1_reburn.log" \
  "$RIDE_DIR/phase2_narration.log" \
  "$RIDE_DIR/phase3_build.log" \
  "$RIDE_DIR/phase3_hotfix.log" \
  "$RIDE_DIR/phase3_tdf_rebuild.log" \
  "$RIDE_DIR/setup_and_phase1.log" \
  "$RIDE_DIR/ffmpeg_upgrade.log"
echo ""

# ----- [6] 라이딩 폴더 내 옛 _파이프라인 → archive -----
echo "[6] 라이딩 폴더 내 옛 _파이프라인/ → archive/old_pipeline/"
if [ -d "$RIDE_DIR/_파이프라인" ]; then
  mv "$RIDE_DIR/_파이프라인" "$ARCHIVE_DIR/old_pipeline/_파이프라인_헐몰헐"
  echo "  → _파이프라인/ (현재 cycling-tools/_파이프라인/lib/에 통합 완료)"
fi
echo ""

# ----- [7] cycling-tools 일회용 .command → archive -----
echo "[7] cycling-tools 일회용 .command → archive/oneoff_commands/"
move_to "$ARCHIVE_DIR/oneoff_commands" \
  "$TOOLS_DIR/SETUP_AND_RUN_PHASE1.command" \
  "$TOOLS_DIR/UPGRADE_FFMPEG_AND_RUN_PHASE1.command" \
  "$TOOLS_DIR/PHASE3_HOTFIX_CLIMB5.command"
echo ""

# ----- [8] 결과 보고 -----
echo "=========================================="
echo "✓ 정리 완료"
echo "=========================================="
echo ""

echo "라이딩 폴더 현재 크기:"
du -sh "$RIDE_DIR" 2>/dev/null | sed 's/^/  /'
echo ""

echo "라이딩 폴더 최종 산출물 (보존):"
for F in "$RIDE_DIR/output_videos/"*.mp4 "$RIDE_DIR/"*.docx "$RIDE_DIR/"*.fit; do
  if [ -f "$F" ]; then
    SIZE=$(du -h "$F" | cut -f1)
    NAME=$(basename "$F")
    printf "  %-8s  %s\n" "$SIZE" "$NAME"
  fi
done
echo ""

echo "Archive 폴더 크기:"
du -sh "$ARCHIVE_DIR" 2>/dev/null | sed 's/^/  /'
du -sh "$ARCHIVE_DIR"/* 2>/dev/null | sed 's/^/    /'
echo ""

echo "▶ Archive 검토 후 영구 삭제 (약 75GB 추가 회수):"
echo "  rm -rf '$ARCHIVE_DIR'"
