#!/bin/bash
# YT_UPLOAD.command — YouTube 자동 업로드
# - 라이딩 폴더 선택 다이얼로그
# - 업로드 대상 선택 (하이라이트 / 본편 / 둘 다)
# - 공개 설정 선택 (private / unlisted / public)
# - Python 의존성 자동 설치
# - lib/yt_upload.py 호출 (OAuth + 메타데이터 + 썸네일 + 챕터)

set -e

TOOLS_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"
PY_SCRIPT="$TOOLS_DIR/lib/yt_upload.py"
AUTH_DIR="$TOOLS_DIR/auth"

# brew + ffmpeg PATH (Python pip 위치)
[ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null

clear
echo "=========================================="
echo "  YouTube 자동 업로드"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# ----- [0] OAuth 인증 파일 점검 -----
if [ ! -f "$AUTH_DIR/client_secret.json" ]; then
  echo "✗ OAuth 인증 파일 없음: $AUTH_DIR/client_secret.json"
  echo ""
  echo "  Google Cloud Console에서 OAuth 클라이언트(Desktop app) 발급 후"
  echo "  client_secret.json으로 위 경로에 배치 필요"
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
echo "[0] OAuth 인증 파일 확인 ✓"
echo ""

# ----- [1] 라이딩 폴더 선택 -----
echo "[1] 라이딩 폴더 선택..."
RIDE_DIR=$(osascript <<'OSAEOF'
tell application "Finder"
    activate
    set folderRef to choose folder with prompt "업로드할 라이딩 폴더 선택 (yt_metadata.md 포함되어 있어야 함)"
    return POSIX path of folderRef
end tell
OSAEOF
)
RIDE_DIR="${RIDE_DIR%/}"
[ -z "$RIDE_DIR" ] && exit 0

if [ ! -f "$RIDE_DIR/yt_metadata.md" ]; then
  echo "✗ yt_metadata.md 없음: $RIDE_DIR"
  echo "  GENERATE_YOUTUBE_PACKAGE.command 먼저 실행 필요"
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
echo "  ✓ $RIDE_DIR"
echo ""

# ----- [2] 업로드 대상 선택 -----
echo "[2] 업로드 대상 선택..."
TARGET_CHOICE=$(osascript <<'OSAEOF'
set choices to {"하이라이트만 (300~500MB, 빠름)", "본편만 (15~20GB, 길게)", "둘 다 (하이라이트 → 본편)"}
set selected to choose from list choices with prompt "업로드할 영상 선택" default items {"하이라이트만 (300~500MB, 빠름)"}
if selected is false then
    return ""
else
    return item 1 of selected
end if
OSAEOF
)
[ -z "$TARGET_CHOICE" ] && exit 0

case "$TARGET_CHOICE" in
  *하이라이트만*) TARGET="highlight" ;;
  *본편만*) TARGET="main" ;;
  *둘\ 다*) TARGET="both" ;;
  *) TARGET="highlight" ;;
esac
echo "  ✓ $TARGET ($TARGET_CHOICE)"
echo ""

# ----- [3] 공개 설정 선택 -----
echo "[3] 공개 설정 선택..."
PRIVACY_CHOICE=$(osascript <<'OSAEOF'
set choices to {"unlisted (링크 있는 사람만, 권장)", "private (본인만)", "public (즉시 공개, 신중)"}
set selected to choose from list choices with prompt "공개 설정 선택" default items {"unlisted (링크 있는 사람만, 권장)"}
if selected is false then
    return ""
else
    return item 1 of selected
end if
OSAEOF
)
[ -z "$PRIVACY_CHOICE" ] && exit 0

case "$PRIVACY_CHOICE" in
  *unlisted*) PRIVACY="unlisted" ;;
  *private*) PRIVACY="private" ;;
  *public*) PRIVACY="public" ;;
  *) PRIVACY="unlisted" ;;
esac
echo "  ✓ $PRIVACY"
echo ""

# ----- [4] Python 의존성 자동 설치 -----
echo "[4] Python 의존성 점검..."
NEED_INSTALL=0
for mod in google_auth_oauthlib googleapiclient google.auth; do
  if ! python3 -c "import $mod" 2>/dev/null; then
    NEED_INSTALL=1
    break
  fi
done

if [ "$NEED_INSTALL" = "1" ]; then
  echo "  → 설치 진행 (1~2분)..."
  pip3 install --break-system-packages --quiet --prefer-binary \
    google-api-python-client google-auth-oauthlib google-auth-httplib2 2>&1 | tail -4 | sed 's/^/    /'
  echo "  ✓ 설치 완료"
else
  echo "  ✓ 모든 의존성 충족"
fi
echo ""

# ----- [5] 업로드 실행 -----
echo "[5] yt_upload.py 호출..."
echo ""

LOG="$RIDE_DIR/yt_upload.log"
caffeinate -i python3 "$PY_SCRIPT" "$RIDE_DIR" "$TARGET" "$PRIVACY" 2>&1 | tee "$LOG"

UPLOAD_EXIT=${PIPESTATUS[0]}
echo ""
if [ "$UPLOAD_EXIT" -eq 0 ]; then
  echo "=========================================="
  echo "✓ YouTube 업로드 완료"
  echo "=========================================="
  echo ""
  echo "로그: $LOG"
  if [ "$PRIVACY" = "unlisted" ]; then
    echo ""
    echo "▶ YouTube Studio에서 검토 후 'public'으로 변경 권장"
    echo "  https://studio.youtube.com/"
  fi
else
  echo "✗ 업로드 실패 — 로그 확인: $LOG"
  exit $UPLOAD_EXIT
fi
