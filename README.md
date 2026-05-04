# Cycling Data Ride — 그란폰도 코칭 영상 자동화

GoPro 영상 + Garmin .fit 데이터를 데이터 코칭 영상으로 자동 변환하는 파이프라인.

## 기능

- ⛰ .fit 자동 분석 (클라임 검출, 베스트/페이드 자동 선정)
- 🎬 4K → 1080p 트랜스코드 + 게이지 오버레이 (속도·파워·심박·케이던스·미니맵·고도)
- 📝 코칭 자막 자동 생성 (시점별 데이터 기반)
- 🎙 OpenAI TTS 나레이션 (남성 echo, GPT-4o-mini로 친근한 동료 코치 톤)
- 🎵 BGM 자동 사이드체인 덕킹
- 🎞 인트로(10초 TDF 지도) + 아웃트로(8초)
- ✨ 장면 전환 효과 (fadeblack/smoothleft xfade)
- 📊 코스 프로파일 + 클라임 분포 카드

## 폴더 구조

```
~/cycling-tools/                   # 이 GitHub repo (Mac 로컬, Google Drive 외부)
├── .gitignore
├── README.md
├── INSTALL.command                # 최초 1회 실행
└── _파이프라인/
    ├── *.command                  # 진입점 스크립트들
    ├── lib/                       # 자동화 모듈 (.py, .sh)
    ├── highlight_b/               # 카드 PNG + 생성기
    ├── intro_video/               # 인트로 생성 코드
    ├── outro_video/               # 아웃트로 생성 코드
    ├── bgm/                       # BGM 폴더 (심볼릭 링크 → ~/Downloads/bgm)
    └── templates/                 # ride_meta.json 템플릿

Google Drive/Gran Fondo/           # 라이딩 데이터 (클라우드 백업)
└── 2026.X.XX...라이딩/
    ├── ACTIVITY.fit
    ├── GX*.MP4
    └── output_videos/
```

## 설치 (1회, Apple Silicon Mac 기준)

### 1. Homebrew (없으면)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### 2. ffmpeg-full (libass 필수 — 자막 번인용)
```bash
# 표준 ffmpeg에는 libass 미포함. third-party tap 필요.
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```
**주의**: `brew install ffmpeg`(표준)는 libass 누락으로 자막 번인 단계 실패. 반드시 `homebrew-ffmpeg/ffmpeg`.

### 3. Python 의존성 (wheel만 사용, GDAL 빌드 회피)
```bash
pip3 install --break-system-packages --prefer-binary \
  fitparse pandas numpy pillow geopandas pyogrio shapely
```
- geopandas 1.0+는 fiona 대신 pyogrio 사용 (GDAL 시스템 빌드 불요).
- `koreanize-matplotlib`은 의존성 충돌 잦으므로 NanumGothic 폰트 직접 다운로드 권장.

### 4. NanumGothic 폰트 (인트로 PNG 생성용)
```bash
FONT_DIR="$HOME/cycling-tools/_파이프라인/intro_video/fonts"
mkdir -p "$FONT_DIR"
curl -L -o "$FONT_DIR/NanumGothic.ttf"           https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf
curl -L -o "$FONT_DIR/NanumGothicBold.ttf"       https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf
curl -L -o "$FONT_DIR/NanumGothicExtraBold.ttf"  https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-ExtraBold.ttf
```

### 5. Natural Earth shapefile (인트로 지도용)
```bash
NE_DIR="$HOME/cycling-tools/_파이프라인/intro_video/ne_data"
mkdir -p "$NE_DIR"
curl -L -o /tmp/ne.zip https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip
unzip -o /tmp/ne.zip -d "$NE_DIR" && rm /tmp/ne.zip
```

### 6. OpenAI API key (TTS 나레이션 신규 생성 시 필요)
```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc
```
※ 캐시(`output_videos/_narration_echo/`)가 있으면 재사용되어 키 불요.

### 7. BGM 심볼릭 링크
```bash
bash INSTALL.command
```

---

## 알려진 호환성 이슈

| 증상 | 원인 | 해결 |
|---|---|---|
| `No such filter: 'subtitles'` | brew의 표준 ffmpeg는 libass 미포함 | `homebrew-ffmpeg/ffmpeg/ffmpeg` 사용 (위 2번) |
| `No option name near 'c.ass'` | ffmpeg 8.x에서 단축 문법 폐기 | `subtitles=filename=c.ass`로 명시 (이미 패치됨) |
| `gdal-config: not found` (fiona 빌드) | geopandas 0.x의 fiona hard dependency | `pip install geopandas`(1.0+, pyogrio 사용)로 회피 |
| `_meta.json` 절대경로 mismatch | 머신 이전 시 sandbox/CloudStorage 경로 잔재 | basename 기반 재구성 (PHASE2 스크립트 패턴 참조) |

## 매 라이딩 사용

```bash
# 새 라이딩 폴더: Google Drive/Gran Fondo/2026.X.XX.요일.HHMM 코스명/
#   - .fit 파일
#   - GX*.MP4 (GoPro)

# 자동 처리
bash ~/cycling-tools/_파이프라인/PROCESS_RIDE.command
# → 폴더 선택 다이얼로그 → 2~3시간 후 본편 + 하이라이트 자동 생성
```

## 라이선스

MIT License — 개인 사용·수정 자유.
