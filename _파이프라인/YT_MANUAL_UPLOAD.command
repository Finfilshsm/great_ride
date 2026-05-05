#!/bin/bash
# YT_MANUAL_UPLOAD.command — 반자동 YouTube 업로드 (브랜드 채널 우회)
#
# 작동 원리:
# - YouTube API의 channel selector가 자동 표시되지 않는 경우 우회
# - yt_metadata.md 파싱 → 단계별 클립보드 자동 복사
# - YouTube Studio + Finder에서 영상/썸네일 자동 reveal
# - 사용자는 5~10분 동안 Studio UI 따라 영상 드래그 + 메타데이터 붙여넣기

set -e

TOOLS_DIR="/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo/cycling-tools/_파이프라인"

clear
echo "=========================================="
echo "  YouTube 반자동 업로드 (Brand 채널용)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# ----- [1] 라이딩 폴더 선택 -----
RIDE_DIR=$(osascript <<'OSAEOF'
tell application "Finder"
    activate
    set folderRef to choose folder with prompt "업로드할 라이딩 폴더 선택 (yt_metadata.md 포함)"
    return POSIX path of folderRef
end tell
OSAEOF
)
RIDE_DIR="${RIDE_DIR%/}"
[ -z "$RIDE_DIR" ] && exit 0

[ ! -f "$RIDE_DIR/yt_metadata.md" ] && {
  osascript -e 'display dialog "yt_metadata.md 없음 — GENERATE_YOUTUBE_PACKAGE.command 먼저 실행" buttons {"확인"}'
  exit 1
}

# ----- [2] 업로드 대상 -----
TARGET_CHOICE=$(osascript <<'OSAEOF'
set choices to {"하이라이트만 (300~500MB, 빠름) — 권장", "본편만 (15~20GB, 길게)"}
set selected to choose from list choices with prompt "업로드할 영상" default items {"하이라이트만 (300~500MB, 빠름) — 권장"}
if selected is false then return ""
return item 1 of selected
OSAEOF
)
[ -z "$TARGET_CHOICE" ] && exit 0

case "$TARGET_CHOICE" in
  *하이라이트*) VIDEO_GLOB="output_videos/하이라이트_*.mp4"; LABEL="하이라이트" ;;
  *본편*) VIDEO_GLOB="output_videos/본편_최종_*.mp4"; LABEL="본편" ;;
esac

VIDEO=$(ls "$RIDE_DIR"/$VIDEO_GLOB 2>/dev/null | head -1)
[ -z "$VIDEO" ] && {
  osascript -e "display dialog \"$LABEL 영상 없음 — PHASE3 먼저 실행\" buttons {\"확인\"}"
  exit 1
}

THUMBNAIL="$RIDE_DIR/yt_thumbnail_1280x720.png"
[ ! -f "$THUMBNAIL" ] && THUMBNAIL="$RIDE_DIR/yt_thumbnail.png"

VIDEO_SIZE=$(du -h "$VIDEO" | cut -f1)
echo "▸ 영상: $(basename "$VIDEO") ($VIDEO_SIZE)"
echo "▸ 썸네일: $(basename "$THUMBNAIL")"
echo ""

# ----- [3] 메타데이터 자체 생성 (_analysis.json + ride_meta.json 기반) -----
PASTE_FILE="$RIDE_DIR/yt_studio_paste.txt"
RIDE_DIR_ENV="$RIDE_DIR" LABEL_ENV="$LABEL" python3 <<'PYEOF'
import json, os
from pathlib import Path

ride = Path(os.environ['RIDE_DIR_ENV'])
label = os.environ['LABEL_ENV']

# 데이터 로드
analysis = json.loads((ride / "_analysis.json").read_text(encoding='utf-8'))
ride_meta = json.loads((ride / "ride_meta.json").read_text(encoding='utf-8'))
chap_path = ride / "yt_chapters.txt"
chap = chap_path.read_text(encoding='utf-8') if chap_path.exists() else ""

s = analysis["summary"]
b = analysis.get("best_climb", {})
fade = analysis.get("fade_climb", {})
r = analysis["rider"]

# 제목 (라벨 prefix 포함)
course = ride_meta.get('코스명', '라이딩')
title = f"[그란폰도 시뮬레이션] {course} {s['distance_km']}km · TSS {s['tss']} — 같은 경사 다른 결과, 영양 패턴이 만든 -17% 페이드"
if label == "하이라이트":
    title = f"[하이라이트] {title}"
elif label == "본편":
    title = f"[본편 풀버전] {title}"
title = title[:100]

# 설명 (헐몰헐 패턴 그대로)
lines = [
    f"🚴 {ride_meta.get('코스명', '')} ({ride_meta.get('코스_설명', '')}) — {ride_meta.get('출발지', '')} 출발",
    ride_meta.get('코스_약자_풀이', ''),
    "",
    "━" * 27,
    "📊 라이딩 지표",
    "━" * 27,
    f"▸ 거리:    {s['distance_km']}km",
    f"▸ 상승:    +{s['elev_gain_m']}m  ({s['elev_per_km']}m/km)",
    f"▸ 경과시간: {s['elapsed_h']}  (주행 {s['moving_h']})",
    f"▸ 평균속도: {s['avg_speed_kmh']} km/h",
    "",
    f"▸ 평균파워: {s['avg_power_w']}W (NP {s['np_w']}W)",
    f"▸ TSS:    {s['tss']}    IF: {s['if_']}    VI: {s['vi']}",
    f"▸ 평균HR: {s['avg_hr']} bpm  (Max {s['max_hr']})",
    f"▸ 평균케이던스: {s['avg_cadence']} rpm",
    f"▸ Pw:Hr 디커플링: {s['decoupling_pct']}%  (5% 이하 정상)",
    "",
    "━" * 27,
    "👤 라이더 프로파일",
    "━" * 27,
    f"▸ FTP:  {r['ftp_w']}W",
    f"▸ 체중: {r['weight_kg']}kg",
    f"▸ W/kg: {r['w_per_kg']}  (Cat 4~5 진입권)",
    f"▸ LTHR: {r['lthr']} bpm",
    "",
    "━" * 27,
    "🔍 오늘의 코칭 포인트",
    "━" * 27,
]
if b and fade:
    lines.append(f"같은 7%대 경사임에도 Climb #{b.get('index')} (km {b.get('start_km',0):.1f}, VAM {b.get('vam_m_per_h',0):.0f})는 베스트 페이싱,")
    lines.append(f"Climb #{fade.get('index')} (km {fade.get('start_km',0):.1f}, VAM {fade.get('vam_m_per_h',0):.0f})는 후반 페이드 -17%.")
    lines.append("")
lines.extend([
    "▶ 1차 원인: 영양 패턴 (보급 1,600 kcal 일괄 섭취 → 위 부담·흡수율 저하)",
    f"▶ 데이터 근거: Pw:Hr 디커플링 {s['decoupling_pct']}% (정상 5% 이하)",
    "",
    "━" * 27,
    "📌 다음 라이딩 액션",
    "━" * 27,
    "1. 출발 30분 전 탄수 80g — 글리코겐 비축",
    "2. 보급 시간당 60g 분할 (한 번에 1,000 kcal 금지)",
    "3. 케이던스 80+ 유지",
    "",
    "━" * 27,
    "🛠 데이터 출처",
    "━" * 27,
    "- Garmin .fit (Edge / 파워미터)",
    "- GoPro 4K 영상 → 1080p 게이지 오버레이",
    "- OpenAI TTS 코칭 나레이션",
    "- 자체 분석 파이프라인 (cycling-tools)",
    "",
    "#그란폰도 #사이클링 #FTP #TSS #파워미터 #VAM #그란폰도시뮬레이션 #DataRide #BigRide",
])
desc = "\n".join(lines)

# 챕터 추가
if chap:
    sep = "\n\n" + ("━" * 27) + "\n📍 챕터\n" + ("━" * 27) + "\n"
    desc = desc + sep + chap.strip()
desc = desc[:5000]

# 태그
tags_list = [
    "그란폰도", "사이클링", course, "FTP", "TSS", "파워미터", "VAM",
    "그란폰도 시뮬레이션", "사이클링 코칭", "Data Ride", "Big Ride",
    "GoPro", "Garmin", "데이터 분석", "Climb 분석", "페이드", "영양 코칭",
    "디커플링", "사이클링 훈련", "라이더 코칭"
]
tags = ", ".join([t for t in tags_list if t and len(t) <= 30])

# 페이스트 파일
paste = (
    "=== Studio 제목 필드에 붙여넣기 (Cmd+V) ===\n\n"
    + title + "\n\n\n"
    + "=== Studio 설명 필드에 붙여넣기 ===\n\n"
    + desc + "\n\n\n"
    + "=== Studio 태그 필드에 붙여넣기 (Show more → Tags) ===\n\n"
    + tags + "\n\n\n"
    + "=== 카테고리: Sports / Made for kids: No / Visibility: Unlisted ===\n"
)
(ride / "yt_studio_paste.txt").write_text(paste, encoding='utf-8')

(ride / ".yt_title.tmp").write_text(title, encoding='utf-8')
(ride / ".yt_desc.tmp").write_text(desc, encoding='utf-8')
(ride / ".yt_tags.tmp").write_text(tags, encoding='utf-8')

print(f"  ✓ 제목 ({len(title)}자)")
print(f"  ✓ 설명 ({len(desc)}자, 챕터 포함)")
print(f"  ✓ 태그 ({len(tags_list)}개)")
PYEOF
echo ""

TITLE=$(cat "$RIDE_DIR/.yt_title.tmp")

# ----- [4] YouTube Studio 자동 열기 -----
echo "[4] YouTube Studio 열기 + Great Ride 채널 전환 안내..."
open "https://studio.youtube.com/"
sleep 1

osascript <<OSAEOF
display dialog "▸ YouTube Studio가 열렸습니다.

1. 우상단 프로필 아이콘 클릭
2. 'Switch account' → 'Great Ride' 선택
3. 좌상단 채널 표시가 'Great Ride'로 바뀐 것 확인

준비되시면 [다음] 클릭" buttons {"다음"} default button "다음" with title "Step 1/6 — 채널 전환"
OSAEOF

# ----- [5] 영상 파일 reveal + 드래그 -----
echo "[5] 영상 파일 Finder reveal..."
open -R "$VIDEO"
sleep 1

osascript <<OSAEOF
display dialog "▸ Finder가 열렸습니다.

1. Studio 우상단 'CREATE' (또는 비디오 카메라 아이콘) → 'Upload videos' 클릭
2. Finder에서 영상 파일을 Studio 업로드 영역에 드래그

영상: $(basename "$VIDEO") ($VIDEO_SIZE)

드래그 완료 후 [다음]" buttons {"다음"} default button "다음" with title "Step 2/6 — 영상 드래그"
OSAEOF

# ----- [6] 제목 클립보드 -----
echo "[6] 제목 클립보드 복사..."
cat "$RIDE_DIR/.yt_title.tmp" | pbcopy

osascript <<OSAEOF
display dialog "▸ 제목이 클립보드에 복사되었습니다.

[$TITLE]

Studio:
- 'Title' 필드 클릭 → 기존 자동 제목 삭제 (Cmd+A → Delete)
- Cmd+V로 붙여넣기

→ [다음]" buttons {"다음"} default button "다음" with title "Step 3/6 — 제목 붙여넣기"
OSAEOF

# ----- [7] 설명+챕터 클립보드 -----
echo "[7] 설명+챕터 클립보드 복사..."
cat "$RIDE_DIR/.yt_desc.tmp" | pbcopy

osascript <<'OSAEOF'
display dialog "▸ 설명 + 챕터 마커가 클립보드에 복사되었습니다.

Studio:
- 'Description' 필드 클릭
- Cmd+V로 붙여넣기

(챕터는 0:00 형식으로 포함되어 있어 유튜브가 자동 인식)

→ [다음]" buttons {"다음"} default button "다음" with title "Step 4/6 — 설명 붙여넣기"
OSAEOF

# ----- [8] 썸네일 reveal + 업로드 -----
echo "[8] 썸네일 Finder reveal..."
open -R "$THUMBNAIL"
sleep 1

osascript <<OSAEOF
display dialog "▸ 썸네일 Finder 열림.

Studio 'Thumbnail' 섹션:
- 'Upload file' 클릭 또는 직접 드래그
- 파일: $(basename "$THUMBNAIL")

→ [다음]" buttons {"다음"} default button "다음" with title "Step 5/6 — 썸네일 업로드"
OSAEOF

# ----- [9] 태그 + 마무리 설정 -----
echo "[9] 태그 클립보드 복사..."
cat "$RIDE_DIR/.yt_tags.tmp" | pbcopy

osascript <<'OSAEOF'
display dialog "▸ 태그가 클립보드에 복사되었습니다.

Studio:
1. 'Show more' 클릭 (페이지 하단)
2. 'Tags' 필드에 Cmd+V

추가 설정:
- Category: Sports
- Audience: 'No, it's not made for kids'
- Visibility: 'Unlisted' (검토 후 Public 권장)

마지막으로 우상단 'NEXT' → ... → 'PUBLISH' 클릭

→ [완료]" buttons {"완료"} default button "완료" with title "Step 6/6 — 태그 + 게시"
OSAEOF

# ----- [10] 임시 파일 정리 -----
rm -f "$RIDE_DIR/.yt_title.tmp" "$RIDE_DIR/.yt_desc.tmp" "$RIDE_DIR/.yt_tags.tmp"

echo ""
echo "=========================================="
echo "✓ 반자동 업로드 가이드 종료"
echo "=========================================="
echo ""
echo "참고:"
echo "  - $RIDE_DIR/yt_studio_paste.txt (전체 메타데이터 일괄 참조용)"
echo "  - 업로드 완료 후 YouTube Studio에서 검토 → 'Public' 전환"
echo "  - Channel: Great Ride (https://studio.youtube.com)"
