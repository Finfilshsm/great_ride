#!/bin/bash
# Phase 3 통합 재빌드 (TDF 인트로 적용 + Climb #5 핫픽스)
# - Python 의존성 자동 설치 (geopandas<1.0, shapely, pyogrio, koreanize-matplotlib, pillow)
# - build_intro_realmap.py 자동 패치 + 실행 → TDF 지도 인트로 PNG 생성
# - PNG → 10초 mp4 변환 (본편 동일 코덱)
# - Climb #5 발췌 점검·재생성 (필요 시 hwaccel videotoolbox single-seek)
# - 14개 클립 concat (TDF 인트로 첫 화면 prepend)
# - BGM 사이드체인 덕킹 → 하이라이트 최종
# - 본편 + TDF 인트로 + 아웃트로 stream copy concat → 본편 최종

set -e

RIDE_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/2026.5.2.토.0800 헐몰헐"
TOOLS_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"
INTRO_PY="$TOOLS_DIR/intro_video/build_intro_realmap.py"
CARDS_DIR="$TOOLS_DIR/highlight_b"
BGM_DIR="$TOOLS_DIR/bgm"
OUT_DIR="$RIDE_DIR/output_videos"
WORK_DIR="$OUT_DIR/_phase3_work"

MAIN_VIDEO="$OUT_DIR/전체_라이딩_오버레이_자막싱크_나레이션.mp4"
BGM_FILE="$BGM_DIR/Chase The Sun - Bel Tempo.mp3"
HIGHLIGHT_OUT="$OUT_DIR/하이라이트_헐몰헐_2026-05-02.mp4"
FULL_OUT="$OUT_DIR/본편_최종_헐몰헐_2026-05-02.mp4"
LOG="$RIDE_DIR/phase3_tdf_rebuild.log"

mkdir -p "$WORK_DIR"
exec > >(tee -a "$LOG") 2>&1

# brew + ffmpeg PATH
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi
FFMPEG="$(command -v ffmpeg)"
FFPROBE="$(command -v ffprobe)"
[ -z "$FFMPEG" ] && { echo "✗ ffmpeg 없음"; exit 1; }

clear
echo "=========================================="
echo "  Phase 3 재빌드: TDF 인트로 + Climb #5 복구"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# ----- [1] Python 의존성 설치 (fiona/GDAL/koreanize-matplotlib 우회) -----
echo "[1] Python 의존성 점검 및 설치..."

# 이전 실패 잔재 정리
pip3 uninstall --break-system-packages -y fiona 2>/dev/null | sed 's/^/  /' || true

echo "  → 핵심 패키지 설치 (geopandas + pyogrio + shapely + pillow)..."
echo "    (fiona/GDAL/koreanize-matplotlib 의존성 회피)"
pip3 install --break-system-packages --quiet --prefer-binary \
  geopandas pyogrio shapely pillow 2>&1 | tail -4 | sed 's/^/    /'

# 검증
for mod in geopandas pyogrio shapely PIL; do
  if python3 -c "import $mod" 2>/dev/null; then
    VER=$(python3 -c "import $mod; print(getattr($mod, '__version__', 'n/a'))" 2>/dev/null)
    echo "  ✓ $mod ($VER)"
  else
    echo "  ✗ $mod 설치 실패"
    exit 1
  fi
done

# NanumGothic 폰트 직접 다운로드 (koreanize-matplotlib 의존성 회피)
FONTS_DIR="$WORK_DIR/fonts"
mkdir -p "$FONTS_DIR"
echo "  → NanumGothic 폰트 다운로드 (Google Fonts / OFL)..."
declare -a FONT_MAP=(
  "Regular|NanumGothic.ttf"
  "Bold|NanumGothicBold.ttf"
  "ExtraBold|NanumGothicExtraBold.ttf"
)
for entry in "${FONT_MAP[@]}"; do
  IFS='|' read -r STYLE FILENAME <<< "$entry"
  TARGET="$FONTS_DIR/$FILENAME"
  if [ ! -f "$TARGET" ]; then
    URL="https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-${STYLE}.ttf"
    if curl -L -s --fail -o "$TARGET" "$URL"; then
      echo "    ✓ $FILENAME ($(du -h "$TARGET" | cut -f1))"
    else
      echo "    ✗ $FILENAME 다운로드 실패 — AppleSDGothicNeo로 fallback"
    fi
  else
    echo "    → $FILENAME (캐시)"
  fi
done

# 폰트 fallback: 다운로드 실패 시 macOS 시스템 폰트 사용 (단일 파일이라 모두 동일 폰트)
APPLE_FONT="/System/Library/Fonts/AppleSDGothicNeo.ttc"
for entry in "${FONT_MAP[@]}"; do
  IFS='|' read -r STYLE FILENAME <<< "$entry"
  TARGET="$FONTS_DIR/$FILENAME"
  if [ ! -f "$TARGET" ] && [ -f "$APPLE_FONT" ]; then
    cp "$APPLE_FONT" "$TARGET"
    echo "    → $FILENAME ← AppleSDGothicNeo fallback"
  fi
done
echo ""

# ----- [2] Natural Earth shapefile 다운로드 + TDF PNG 생성 -----
echo "[2] Natural Earth shapefile 다운로드 및 TDF 지도 인트로 PNG 생성..."
[ ! -f "$INTRO_PY" ] && { echo "  ✗ build_intro_realmap.py 누락"; exit 1; }

# Natural Earth 다운로드 (캐시 있으면 skip)
NE_DIR="$WORK_DIR/ne_data"
NE_SHP="$NE_DIR/ne_110m_admin_0_countries.shp"
if [ ! -f "$NE_SHP" ]; then
  echo "  → Natural Earth 110m countries 다운로드..."
  mkdir -p "$NE_DIR"
  NE_URL="https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
  if ! curl -L -s --fail -o "$WORK_DIR/ne.zip" "$NE_URL"; then
    echo "  ⚠ naciscdn 다운로드 실패 — github mirror 시도"
    NE_URL="https://github.com/nvkelso/natural-earth-vector/raw/master/110m_cultural/ne_110m_admin_0_countries.zip"
    curl -L -s --fail -o "$WORK_DIR/ne.zip" "$NE_URL" || {
      echo "  ✗ Natural Earth 다운로드 실패"; exit 1; }
  fi
  unzip -o -q "$WORK_DIR/ne.zip" -d "$NE_DIR"
  rm -f "$WORK_DIR/ne.zip"
fi
[ ! -f "$NE_SHP" ] && { echo "  ✗ shp 추출 실패"; exit 1; }
echo "  ✓ Natural Earth: $(ls "$NE_DIR" | wc -l | tr -d ' ')개 파일 ($NE_DIR)"

# 폰트 폴더 = 위에서 다운로드한 $FONTS_DIR
KOR_FONTS="$FONTS_DIR"
echo "  → 폰트 폴더: $KOR_FONTS"

# build_intro_realmap.py 패치 (경로 + koreanize_matplotlib import 제거 + pyogrio engine + 컬럼명 호환)
PATCHED_PY="$WORK_DIR/build_intro_patched.py"
python3 << PYEOF
with open("$INTRO_PY") as f:
    code = f.read()
# import 제거 (의존성 없음)
code = code.replace("import koreanize_matplotlib\n", "")
code = code.replace("import koreanize_matplotlib", "")
# 경로 패치
code = code.replace(
    "/sessions/relaxed-inspiring-mayer/mnt/outputs/intro_mockups", "$WORK_DIR")
code = code.replace(
    "/sessions/relaxed-inspiring-mayer/.local/lib/python3.10/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp",
    "$NE_SHP")
code = code.replace(
    "/sessions/relaxed-inspiring-mayer/.local/lib/python3.10/site-packages/koreanize_matplotlib/fonts",
    "$KOR_FONTS")
# pyogrio engine + Natural Earth 110m 컬럼명 호환 (NAME → name alias)
code = code.replace(
    "gdf = gpd.read_file(SHP)",
    'gdf = gpd.read_file(SHP, engine="pyogrio")\n'
    'if "name" not in gdf.columns:\n'
    '    for _alt in ["NAME", "NAME_EN", "NAME_LONG", "ADMIN"]:\n'
    '        if _alt in gdf.columns:\n'
    '            gdf["name"] = gdf[_alt]\n'
    '            break'
)
with open("$PATCHED_PY", "w") as f:
    f.write(code)
print("  ✓ 패치본 작성:", "$PATCHED_PY")
PYEOF

python3 "$PATCHED_PY" 2>&1 | sed 's/^/    /'

TDF_PNG="$WORK_DIR/intro_B_TDF_realmap.png"
[ ! -f "$TDF_PNG" ] && { echo "  ✗ TDF PNG 생성 실패: $TDF_PNG"; exit 1; }
echo "  ✓ TDF PNG 생성: $(du -h "$TDF_PNG" | cut -f1)"
echo ""

# ----- [3] TDF PNG → 10초 mp4 변환 -----
echo "[3] TDF 인트로 mp4 변환 (10s, hevc_videotoolbox)..."
TDF_INTRO_MP4="$WORK_DIR/00_intro_tdf.mp4"
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel error \
  -loop 1 -framerate 30000/1001 -i "$TDF_PNG" \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -t 10 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#0c1626,format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st=9.3:d=0.6" \
  -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
  -c:a aac -b:a 192k -ar 48000 \
  -video_track_timescale 30000 \
  -movflags +faststart \
  "$TDF_INTRO_MP4"
echo "  ✓ $TDF_INTRO_MP4"
echo ""

# ----- [4] Climb #5 발췌 점검·재생성 -----
echo "[4] Climb #5 발췌 점검..."
CLIMB5="$WORK_DIR/06_climb5_excerpt.mp4"
DUR5_INT=0
if [ -f "$CLIMB5" ]; then
  DUR5=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$CLIMB5" 2>/dev/null || echo 0)
  DUR5_INT=$(printf '%.0f' "$DUR5")
fi

if [ "$DUR5_INT" -lt 80 ]; then
  echo "  → Climb #5 비정상 (${DUR5_INT}s) — 재생성 (hwaccel + single -ss after -i)"
  rm -f "$CLIMB5"
  caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
    -hwaccel videotoolbox \
    -i "$MAIN_VIDEO" \
    -ss "01:05:40" -t 90 \
    -c:v hevc_videotoolbox -q:v 50 -tag:v hvc1 -r 30000/1001 \
    -c:a aac -b:a 192k -ar 48000 \
    -video_track_timescale 30000 \
    -avoid_negative_ts make_zero \
    -movflags +faststart \
    "$CLIMB5"
  DUR5=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$CLIMB5")
  DUR5_INT=$(printf '%.0f' "$DUR5")
  echo "  ✓ Climb #5 재생성: ${DUR5_INT}s"
else
  echo "  ✓ Climb #5 정상: ${DUR5_INT}s (재생성 불필요)"
fi
echo ""

# ----- [5] 14개 클립 concat (TDF 인트로 prepend) -----
echo "[5] 14개 클립 concat (TDF 인트로 첫 화면)..."
CONCAT="$WORK_DIR/_concat_highlight.txt"
{
  echo "file '$WORK_DIR/00_intro_tdf.mp4'"
  echo "file '$WORK_DIR/01_intro_overview.mp4'"
  echo "file '$WORK_DIR/02_glossary.mp4'"
  echo "file '$WORK_DIR/03_course_profile.mp4'"
  echo "file '$WORK_DIR/04_course_climbs.mp4'"
  echo "file '$WORK_DIR/05_climb5_intro.mp4'"
  echo "file '$WORK_DIR/06_climb5_excerpt.mp4'"
  echo "file '$WORK_DIR/07_transition.mp4'"
  echo "file '$WORK_DIR/08_climb6_intro.mp4'"
  echo "file '$WORK_DIR/09_climb6_excerpt.mp4'"
  echo "file '$WORK_DIR/10_analysis.mp4'"
  echo "file '$WORK_DIR/11_conclusion.mp4'"
  echo "file '$WORK_DIR/12_action.mp4'"
  echo "file '$WORK_DIR/13_outro.mp4'"
} > "$CONCAT"

HIGHLIGHT_RAW="$WORK_DIR/highlight_raw.mp4"
[ -f "$HIGHLIGHT_RAW" ] && rm "$HIGHLIGHT_RAW"
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$CONCAT" \
  -c copy \
  -movflags +faststart \
  "$HIGHLIGHT_RAW"
RAW_DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$HIGHLIGHT_RAW")
RAW_DUR_INT=$(printf '%.0f' "$RAW_DUR")
echo "  ✓ raw concat: ${RAW_DUR_INT}초 ($(printf '%.2f' "$(echo "$RAW_DUR/60" | bc -l)")분)"

if [ "$RAW_DUR_INT" -lt 270 ]; then
  echo "  ⚠ raw 길이 짧음 (예상 285초 = TDF 10s + 본 4분 35초) — 클립별 진단:"
  for F in "$WORK_DIR"/*.mp4; do
    [[ "$(basename "$F")" == "highlight"* ]] && continue
    D=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$F" 2>/dev/null)
    printf "      %-30s %ss\n" "$(basename "$F")" "$D"
  done
  exit 1
fi
echo ""

# ----- [6] BGM 사이드체인 덕킹 -----
echo "[6] BGM 사이드체인 덕킹..."
[ -f "$HIGHLIGHT_OUT" ] && rm "$HIGHLIGHT_OUT"
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning -stats \
  -i "$HIGHLIGHT_RAW" -stream_loop -1 -i "$BGM_FILE" \
  -filter_complex "
    [0:a]asplit=2[orig][key];
    [1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.7[bgm];
    [bgm][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300:level_sc=1[bgm_ducked];
    [orig][bgm_ducked]amix=inputs=2:duration=first:normalize=0[final]
  " \
  -map 0:v -map "[final]" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -shortest \
  -movflags +faststart \
  "$HIGHLIGHT_OUT"
echo "  ✓ $HIGHLIGHT_OUT"
echo ""

# ----- [7] 본편 결합 (TDF 인트로 + 본편 + 아웃트로) -----
echo "[7] 본편 결합 (TDF 인트로 + 본편 + 아웃트로, stream copy)..."
FULL_CONCAT="$WORK_DIR/_concat_full.txt"
{
  echo "file '$WORK_DIR/00_intro_tdf.mp4'"
  echo "file '$MAIN_VIDEO'"
  echo "file '$WORK_DIR/13_outro.mp4'"
} > "$FULL_CONCAT"

[ -f "$FULL_OUT" ] && rm "$FULL_OUT"
caffeinate -i "$FFMPEG" -y -hide_banner -loglevel warning \
  -f concat -safe 0 -i "$FULL_CONCAT" \
  -c copy \
  -movflags +faststart \
  "$FULL_OUT"
echo "  ✓ $FULL_OUT"
echo ""

# ----- [8] 검증 -----
echo "[8] 산출물 검증..."
verify() {
  local OUT="$1"; local LABEL="$2"
  if [ ! -f "$OUT" ]; then
    echo "  ✗ $LABEL 미생성"
    return 1
  fi
  local SIZE GB DUR DUR_MIN MOOV
  SIZE=$(stat -f%z "$OUT")
  GB=$(echo "scale=2; $SIZE / 1073741824" | bc)
  DUR=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$OUT")
  DUR_MIN=$(printf '%.2f' "$(echo "$DUR/60" | bc -l)")
  if "$FFPROBE" -v error "$OUT" >/dev/null 2>&1; then MOOV="✓"; else MOOV="✗"; fi
  echo "  ${MOOV} $LABEL"
  echo "      $(basename "$OUT")"
  echo "      ${GB}GB / ${DUR_MIN}분"
}
verify "$HIGHLIGHT_OUT" "하이라이트 (유튜브용, TDF 인트로 포함)"
verify "$FULL_OUT" "본편 최종 (TDF 인트로 + 본편 + 아웃트로)"

echo ""
echo "=========================================="
echo "✓ Phase 3 재빌드 완료"
echo ""
echo "  하이라이트: $HIGHLIGHT_OUT"
echo "  본편 최종:  $FULL_OUT"
echo "=========================================="
