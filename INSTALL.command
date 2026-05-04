#!/bin/bash
# Cycling Data Ride 최초 설치 스크립트
# 사용법: bash INSTALL.command

set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

clear
cat << 'BANNER'
==========================================================
  Cycling Data Ride — 설치 스크립트
==========================================================
BANNER

# 1. ffmpeg-full 확인
if [ -x "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" ]; then
  echo "✓ ffmpeg-full 설치됨"
else
  echo "! ffmpeg-full 미설치 → brew install ffmpeg-full 필요"
  echo "  brew install ffmpeg-full"
  exit 1
fi

# 2. Python 패키지 확인
echo ""
echo "[Python 패키지 확인]"
python3 -c "import fitparse, pandas, numpy, PIL, geopandas, pyogrio, koreanize_matplotlib" 2>/dev/null && \
  echo "  ✓ 모든 패키지 OK" || {
  echo "  ! 일부 패키지 누락 → 설치 중..."
  pip3 install --user fitparse pandas numpy Pillow geopandas pyogrio koreanize-matplotlib 2>&1 | tail -3
}

# 3. OPENAI_API_KEY 확인
echo ""
echo "[OPENAI_API_KEY 확인]"
if [ -n "$OPENAI_API_KEY" ]; then
  echo "  ✓ 등록됨: ${OPENAI_API_KEY:0:8}..."
else
  echo "  ! 미설정. 다음 명령으로 설정 후 새 터미널 열기:"
  echo "    echo 'export OPENAI_API_KEY=\"sk-...\"' >> ~/.zshrc"
  echo "    source ~/.zshrc"
fi

# 4. BGM 심볼릭 링크
echo ""
echo "[BGM 폴더 연결]"
BGM_DIR="$ROOT/_파이프라인/bgm"
SOURCES=(
  "$HOME/Downloads/bgm"
  "$HOME/Music/cycling-bgm"
  "$HOME/Downloads/그란폰도BGM"
)
LINKED=false
for src in "${SOURCES[@]}"; do
  if [ -d "$src" ]; then
    count=$(ls "$src"/*.mp3 2>/dev/null | wc -l | xargs)
    if [ "$count" -gt 0 ]; then
      # 기존 mp3 정리 후 심볼릭 링크
      rm -f "$BGM_DIR"/*.mp3 2>/dev/null
      for f in "$src"/*.mp3; do
        ln -sf "$f" "$BGM_DIR/$(basename "$f")"
      done
      echo "  ✓ $src → BGM 폴더 링크 ($count 곡)"
      LINKED=true
      break
    fi
  fi
done

if [ "$LINKED" = false ]; then
  echo "  ! BGM 자동 발견 실패. 수동 연결:"
  echo "    ln -s ~/Downloads/그대로/위치 \"$BGM_DIR\""
  echo "  또는 mp3 파일을 $BGM_DIR/ 에 직접 복사"
fi

# 5. .command 권한
echo ""
echo "[.command 실행 권한 부여]"
find "$ROOT" -name "*.command" -type f -exec chmod +x {} \;
find "$ROOT" -name "*.sh" -type f -exec chmod +x {} \;
echo "  ✓ 모든 .command/.sh 파일 +x"

echo ""
echo "=========================================="
echo "설치 완료. 다음 라이딩 처리 시:"
echo "  bash $ROOT/_파이프라인/PROCESS_RIDE.command"
echo "=========================================="
