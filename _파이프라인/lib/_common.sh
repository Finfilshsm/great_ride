#!/bin/bash
# 파이프라인 공통 환경 — 모든 PHASE/.command 스크립트가 source하는 헬퍼.
# - RIDE_DIR 해석: 환경변수 → 인자 → osascript 폴더 선택 다이얼로그
# - 표준 변수 export: RIDE_DIR, OUT_DIR, TOOLS_DIR, FFMPEG, FFPROBE, COURSE_NAME, DATE_TAG
# - _analysis.json/ride_meta.json 자동 로드 (jq 또는 python3로 값 추출)
#
# 사용법 (각 PHASE 상단에):
#   source "$(dirname "$0")/lib/_common.sh"
#   resolve_ride_dir "$@"   # $1 = RIDE_DIR (옵션)
#   detect_ffmpeg
#   load_ride_metadata
#
# 또는 더블클릭 실행 시 RIDE_DIR 비어 있으면 osascript 다이얼로그가 뜸.

# ----- 공통 경로 (자기 위치 기준 동적 결정 — 어느 PC/경로에서도 동작) -----
# 코드(git managed) 위치 — _common.sh 자기 자신 기준
_COMMON_SH="${BASH_SOURCE[0]}"
LIB_DIR="$(cd "$(dirname "$_COMMON_SH")" && pwd)"
TOOLS_DIR="$(dirname "$LIB_DIR")"

# BASE_DIR = 라이딩 데이터 폴더들의 부모 (FIT, GoPro, athlete_db.json 위치)
# 코드와 데이터 분리: 코드는 git, 데이터는 클라우드/외장. PC별로 데이터 위치 다름.
# 우선순위: $CYCLING_DATA_DIR (env) > 레거시 호환(cycling-tools 부모) > $HOME
if [ -n "$CYCLING_DATA_DIR" ] && [ -d "$CYCLING_DATA_DIR" ]; then
  BASE_DIR="$CYCLING_DATA_DIR"
else
  # 레거시: cycling-tools가 데이터 폴더 부모에 함께 있던 구조
  _legacy_base="$(dirname "$(dirname "$TOOLS_DIR")")"
  if ls -d "$_legacy_base"/2[0-9][0-9][0-9].* 2>/dev/null | head -1 >/dev/null; then
    BASE_DIR="$_legacy_base"
  else
    BASE_DIR="$HOME"
  fi
fi

# ----- RIDE_DIR 해석 -----
resolve_ride_dir() {
  # 1순위: 환경변수
  if [ -n "$RIDE_DIR" ] && [ -d "$RIDE_DIR" ]; then
    return 0
  fi

  # 2순위: 첫 인자
  if [ -n "$1" ] && [ -d "$1" ]; then
    RIDE_DIR="${1%/}"
    export RIDE_DIR
    return 0
  fi

  # 3순위: osascript 폴더 선택 다이얼로그
  RIDE_DIR=$(osascript <<OSAEOF
tell application "Finder"
    activate
    set defaultLoc to POSIX file "$BASE_DIR" as alias
    set folderRef to choose folder default location defaultLoc with prompt "라이딩 폴더 선택 (.fit + GX*.MP4 포함)"
    return POSIX path of folderRef
end tell
OSAEOF
)
  RIDE_DIR="${RIDE_DIR%/}"

  if [ -z "$RIDE_DIR" ] || [ ! -d "$RIDE_DIR" ]; then
    echo "✗ RIDE_DIR 미선택 또는 존재 안함" >&2
    exit 1
  fi
  export RIDE_DIR
}

# ----- ffmpeg 탐지 -----
detect_ffmpeg() {
  # Homebrew PATH
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
  fi

  # ffmpeg-full 우선 (libass 포함)
  if [ -x "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" ]; then
    FFMPEG="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
    FFPROBE="/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
  elif command -v ffmpeg >/dev/null 2>&1; then
    FFMPEG="$(command -v ffmpeg)"
    FFPROBE="$(command -v ffprobe)"
  else
    echo "✗ ffmpeg 미설치 — 'brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg' 후 재실행" >&2
    exit 1
  fi
  export FFMPEG FFPROBE
}

# ----- _analysis.json + ride_meta.json 메타 로드 -----
load_ride_metadata() {
  if [ ! -f "$RIDE_DIR/_analysis.json" ]; then
    echo "✗ _analysis.json 없음 — RUN_RIDE.command 또는 lib/build_analysis.py 먼저 실행" >&2
    exit 1
  fi

  # 라이딩 일자 추출 (RIDE_DIR 폴더명에서) — 예: "2026.5.5.화.0900 헐몰팔" → "2026-05-05"
  local FOLDER_NAME
  FOLDER_NAME=$(basename "$RIDE_DIR")
  # 정규식으로 yyyy.M.D 추출
  if [[ "$FOLDER_NAME" =~ ^([0-9]{4})\.([0-9]{1,2})\.([0-9]{1,2}) ]]; then
    DATE_TAG=$(printf "%s-%02d-%02d" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}")
  else
    # _analysis.json의 ride_start_utc fallback
    DATE_TAG=$(python3 -c "
import json, sys
from datetime import datetime
d = json.load(open('$RIDE_DIR/_analysis.json'))
ts = d.get('ride_start_utc','')
try:
    dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
    print(dt.strftime('%Y-%m-%d'))
except Exception:
    print('unknown')
")
  fi

  # 코스명: ride_meta.json의 코스명 우선, 없으면 폴더명에서 추출
  if [ -f "$RIDE_DIR/ride_meta.json" ]; then
    COURSE_NAME=$(python3 -c "
import json
d = json.load(open('$RIDE_DIR/ride_meta.json'))
print(d.get('코스명','').strip())
")
  fi
  if [ -z "$COURSE_NAME" ]; then
    # 폴더명 마지막 토큰
    COURSE_NAME=$(echo "$FOLDER_NAME" | awk -F' ' '{print $NF}')
  fi

  OUT_DIR="$RIDE_DIR/output_videos"
  mkdir -p "$OUT_DIR"

  export DATE_TAG COURSE_NAME OUT_DIR
}

# ----- 로깅 -----
init_log() {
  local SUFFIX="${1:-pipeline}"
  LOG="$RIDE_DIR/${SUFFIX}.log"
  exec > >(tee -a "$LOG") 2>&1
  export LOG
}

# ----- 공통 헤더 -----
print_header() {
  local TITLE="$1"
  echo "=========================================="
  echo "  $TITLE"
  echo "  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=========================================="
  echo "  RIDE_DIR    : $RIDE_DIR"
  echo "  COURSE_NAME : $COURSE_NAME"
  echo "  DATE_TAG    : $DATE_TAG"
  echo "  ffmpeg      : $FFMPEG"
  echo "=========================================="
  echo ""
}
