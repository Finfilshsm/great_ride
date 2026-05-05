#!/bin/bash
# 유튜브 업로드 패키지 자동 생성 (일반화 버전)
# - yt_metadata.md (제목/설명/태그) — _analysis.json + ride_meta.json 기반
# - yt_chapters.txt — coaching.srt 기반 (인트로 +10s 오프셋)
# - yt_thumbnail.png + 1280x720 — 코스명·VAM 비교 동적

set -e
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/_common.sh"

resolve_ride_dir "$@"
detect_ffmpeg
load_ride_metadata
init_log "yt_package"

clear
print_header "유튜브 업로드 패키지 생성"

# ride_meta.json 없으면 RUN_RIDE 패턴으로 자동 생성
if [ ! -f "$RIDE_DIR/ride_meta.json" ]; then
  echo "  ⚠ ride_meta.json 없음 — 폴더명 기반 자동 생성"
  python3 -c "
import json
from pathlib import Path
p = Path('$RIDE_DIR/ride_meta.json')
meta = {'출발지': '', '코스명': '$COURSE_NAME', '코스_설명': '', '코스_약자_풀이': '', '라이더_메모': ''}
p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'  ✓ {p}')
"
fi
echo ""

echo "[1] yt_metadata.md + yt_chapters.txt 생성..."
python3 "$LIB_DIR/build_yt_metadata.py" "$RIDE_DIR" "$COURSE_NAME" "$DATE_TAG"
echo ""

echo "[2] yt_thumbnail.png 생성..."
python3 "$LIB_DIR/build_yt_thumbnail.py" "$RIDE_DIR" "$COURSE_NAME" "$DATE_TAG"
echo ""

echo "=========================================="
echo "✓ 유튜브 패키지 생성 완료"
echo "=========================================="
ls -lh "$RIDE_DIR/yt_metadata.md" "$RIDE_DIR/yt_chapters.txt" \
       "$RIDE_DIR/yt_thumbnail.png" "$RIDE_DIR/yt_thumbnail_1280x720.png" 2>/dev/null \
  | awk '{printf "  %s  %s\n", $5, $9}' | sed "s|$RIDE_DIR/||"
echo ""
echo "다음: YT_UPLOAD.command 실행 (Great Ride 채널)"
