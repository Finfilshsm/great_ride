#!/bin/bash
# RUN_RIDE.command — 매 라이딩 단일 진입점
# 더블클릭 → osascript 폴더 선택 → 자동 후처리
#
# 입력 (라이딩 폴더에 사용자가 두는 것):
#   - XXXXX_ACTIVITY.fit       (Garmin)
#   - GX*.MP4                  (GoPro 원본)
#   - _analysis.json           (라이딩 분석; 사전 생성 필요)
#   - (선택) ride_meta.json    (없으면 폴더명에서 자동 추출)
#
# 자동 처리:
#   1. 환경 점검 (ffmpeg/Python)
#   2. _videos.json 자동 생성 (ffprobe로 GoPro 챕터 매핑)
#   3. coaching.srt 자동 생성 (lib/build_srt.py)
#   4. (선조건) 게이지 오버레이 — 다음 라이딩에서 단계적 자동화 예정
#   5. 본편 concat + 자막 번인
#   6. TTS 나레이션 합성 (OPENAI_API_KEY 또는 캐시)
#   7. 인트로/카드/하이라이트/본편 결합 — 일반화 진행 중
#   8. 유튜브 패키지 — 일반화 진행 중

set -e

# 자기 위치 기준 — 어느 PC에서도 동작
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"

# ----- 라이딩 폴더 선택 다이얼로그 -----
RIDE_DIR=$(osascript <<'OSAEOF'
tell application "Finder"
    activate
    set folderRef to choose folder with prompt "라이딩 폴더 선택 (.fit + GX*.MP4 + _analysis.json 포함)"
    return POSIX path of folderRef
end tell
OSAEOF
)
RIDE_DIR="${RIDE_DIR%/}"
[ -z "$RIDE_DIR" ] && exit 0

LOG="$RIDE_DIR/run_ride.log"
exec > >(tee -a "$LOG") 2>&1

clear
echo "=========================================="
echo "  RUN_RIDE — 매 라이딩 자동 후처리"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""
echo "라이딩 폴더: $RIDE_DIR"
echo ""

# ----- [0] 환경 -----
[ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null
FFMPEG="$(command -v ffmpeg)"
FFPROBE="$(command -v ffprobe)"
[ -z "$FFMPEG" ] && { echo "✗ ffmpeg 없음 — UPGRADE_FFMPEG_AND_RUN_PHASE1.command 패턴으로 ffmpeg-full 설치 필요"; exit 1; }
echo "[0] ffmpeg: $FFMPEG"
echo ""

# ----- [1] 입력 자산 점검 -----
echo "[1] 입력 자산 점검..."
FIT_FILE=$(find "$RIDE_DIR" -maxdepth 1 -iname "*.fit" | head -1)
GOPRO_COUNT=$(find "$RIDE_DIR" -maxdepth 1 -iname "GX*.MP4" | wc -l | tr -d ' ')

[ -z "$FIT_FILE" ] && { echo "  ✗ .fit 파일 없음"; exit 1; }
[ "$GOPRO_COUNT" -eq 0 ] && { echo "  ✗ GoPro MP4 없음"; exit 1; }

echo "  ✓ .fit: $(basename "$FIT_FILE")"
echo "  ✓ GoPro MP4: ${GOPRO_COUNT}개"

if [ ! -f "$RIDE_DIR/_analysis.json" ]; then
  echo "  → _analysis.json 자동 생성 (lib/build_analysis.py)..."
  python3 "$TOOLS_DIR/lib/build_analysis.py" "$RIDE_DIR" 2>&1 | tail -8
fi
[ ! -f "$RIDE_DIR/_analysis.json" ] && { echo "  ✗ _analysis.json 생성 실패"; exit 1; }
echo "  ✓ _analysis.json"

# ride_meta.json 자동 생성 (폴더명 기반)
if [ ! -f "$RIDE_DIR/ride_meta.json" ]; then
  COURSE=$(basename "$RIDE_DIR" | awk -F' ' '{$1=""; print $0}' | sed 's/^ //')
  python3 -c "
import json, os
meta = {'출발지': '', '코스명': '$COURSE', '코스_설명': '', '코스_약자_풀이': '', '라이더_메모': ''}
with open(os.path.join('$RIDE_DIR', 'ride_meta.json'), 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
"
  echo "  ✓ ride_meta.json 자동 생성 (수동 보완 권장: 출발지·설명·약자풀이)"
fi
echo ""

# ----- [2] _videos.json 자동 생성 (lib/build_videos_json.py 사용 — 파일별 creation_time 정확) -----
echo "[2] GoPro 챕터 매핑 (_videos.json)..."
if [ ! -f "$RIDE_DIR/_videos.json" ]; then
  python3 "$TOOLS_DIR/lib/build_videos_json.py" "$RIDE_DIR" 2>&1 | grep -E "✓|⚠"
else
  echo "  → 이미 있음 (skip)"
fi
echo ""

# ----- [3] coaching.srt 자동 생성 -----
echo "[3] coaching.srt 자동 생성 (lib/build_srt.py)..."
if [ ! -f "$RIDE_DIR/coaching.srt" ] || [ "$RIDE_DIR/_analysis.json" -nt "$RIDE_DIR/coaching.srt" ]; then
  python3 "$TOOLS_DIR/lib/build_srt.py" "$RIDE_DIR" || {
    echo "  ⚠ build_srt.py 실패 — 수동 작성 또는 lib 보강 필요"
  }
  [ -f "$RIDE_DIR/coaching.srt" ] && echo "  ✓ $(wc -l < "$RIDE_DIR/coaching.srt" | tr -d ' ')줄"
else
  echo "  → 이미 최신 (skip)"
fi
echo ""

# ----- [4] 게이지 오버레이 자동 (다음 단계 보강 예정) -----
echo "[4] 게이지 오버레이 (다음 단계 자동화 예정)..."
mkdir -p "$RIDE_DIR/output_videos"
OVL_COUNT=$(find "$RIDE_DIR/output_videos" -maxdepth 1 -iname "GX*_overlay.mp4" 2>/dev/null | wc -l | tr -d ' ')
if [ "$OVL_COUNT" -eq 0 ]; then
  echo "  ⚠ output_videos/GX*_overlay.mp4 없음"
  echo ""
  echo "  build_overlay 단계는 라이딩별 챕터 매핑·VIDEOS 배열이 정교해야 하므로"
  echo "  다음 라이딩 1~2회 검증 후 자동화 코드 보강 예정"
  echo "  현재는 사전에 build_overlay_parallel.py로 챕터별 mp4 생성 필요"
  echo ""
  echo "수동 호출 예시:"
  echo "  python3 \"$TOOLS_DIR/lib/build_overlay_parallel.py\" \\"
  echo "    \"$FIT_FILE\" \"$RIDE_DIR/output_videos\" \\"
  echo "    \"<챕터별 start_utc>\" <duration> 4"
  exit 0
fi
echo "  ✓ ${OVL_COUNT}개 오버레이 영상 확인"
echo ""

# ----- [5] 본편 concat + 자막 번인 + 나레이션 + 유튜브 패키지 -----
echo "[5~8] 후처리 단계는 PHASE2/PHASE3/GENERATE_YOUTUBE_PACKAGE 통합 진행 중"
echo "       현재 헐몰헐 전용 하드코딩 → 일반화 작업 필요 (다음 라이딩 검증 후)"
echo ""

echo "=========================================="
echo "RUN_RIDE framework 종료"
echo "=========================================="
echo ""
echo "▶ 현재 자동화 범위:"
echo "    ✓ ride_meta.json 자동 생성"
echo "    ✓ _videos.json 자동 추출 (ffprobe + 누적 duration)"
echo "    ✓ coaching.srt 자동 생성 (build_srt.py)"
echo ""
echo "▶ 다음 라이딩에서 보강 예정:"
echo "    - .fit → _analysis.json 자동 분석 (fitparse, 클라임 검출, TSS/IF/VAM 계산)"
echo "    - 게이지 오버레이 자동 (build_overlay_parallel.py 정교화)"
echo "    - PHASE3·유튜브 패키지 일반화 (RIDE_DIR 변수화, 카드 텍스트 동적)"
echo ""
echo "▶ 신규 라이딩 처리 절차 (현재):"
echo "    1. 새 폴더 (일시-코스명) 생성"
echo "    2. .fit + GX*.MP4 업로드"
echo "    3. _analysis.json 별도 작성 (현재) → 본 .command 실행"
echo "    4. coaching.srt 자동 생성됨 → 검토/수정 후 PHASE1~3 .command 차례 실행"
