# Cycling Data Ride — 그란폰도 코칭 영상 자동화

GoPro 영상 + Garmin .fit 데이터를 데이터 코칭 영상으로 자동 변환하는 파이프라인.

## 기능

- ⛰ .fit 자동 분석 (클라임 검출, 베스트/페이드 자동 선정, 디커플링·VAM·TSS·IF 계산)
- 🎬 4K → 1080p 트랜스코드 + 게이지 오버레이 (속도·파워·심박·케이던스·미니맵·고도 프로파일)
- 📝 코칭 자막 자동 생성 (시점별 데이터 기반)
- 🎙 OpenAI TTS 나레이션 (한국어 echo, GPT-4o-mini로 친근한 동료 코치 톤)
- 🎵 BGM 자동 사이드체인 덕킹
- 🎞 인트로(10초 데이터 카드) + 아웃트로(8초)
- 📊 라이딩별 동적 카드 10장 (개요·용어·코스·클라임·분석·결론·액션)
- ☁️ YouTube 자동 업로드 (Brand Account 인증 포함)

## 폴더 구조 — 코드(git)와 데이터(클라우드) 분리

**코드(git)**: 어느 PC든 동일하게 ~/cycling-tools/. push/pull로 동기화.

**데이터(Google Drive 또는 외장)**: PC별로 다를 수 있음. `$CYCLING_DATA_DIR` 환경변수로 지정.

```
~/cycling-tools/                  # GitHub repo (로컬 SSD, git managed)
├── .gitignore
├── README.md
├── INSTALL.command               # 최초 1회 실행
└── _파이프라인/
    ├── RUN_RIDE.command          # 매 라이딩 진입점 (메타·자막·카드 자동)
    ├── PHASE0_OVERLAY.command    # 오버레이 + 시간정렬 (~1~3h)
    ├── PHASE1_REBURN_SUBTITLES.command   # 자막 번인
    ├── PHASE2_ADD_NARRATION.command      # TTS 나레이션 합성
    ├── PHASE3_BUILD_FINAL_VIDEOS.command # 인트로/하이라이트/본편 결합
    ├── GENERATE_YOUTUBE_PACKAGE.command  # 메타·챕터·썸네일
    ├── YT_UPLOAD.command                 # Great Ride 채널 업로드
    ├── lib/                      # Python·shell 모듈 (athlete_db, build_*, seorak)
    ├── intro_video/              # 인트로 PNG 생성기
    │   ├── fonts/                # NanumGothic (.gitignore — INSTALL로 다운)
    │   └── ne_data/              # Natural Earth shapefile (.gitignore)
    ├── outro_video/
    ├── bgm/                      # BGM 폴더 (.gitignore — 라이선스/용량)
    └── auth/                     # OAuth (절대 commit 금지)
        ├── client_secret.json
        ├── token.json (첫 인증 시 자동)
        └── target_channel_id.txt

$CYCLING_DATA_DIR/                # 데이터 폴더 (Google Drive·외장 가능)
├── athlete_db.json (자동 누적)
├── Seorak_Granfondo-208km.gpx (A-race 코스)
└── 2026.X.XX 라이딩 폴더/          # 라이딩별 데이터
├── XXX_ACTIVITY.fit              # Garmin
├── GX*.MP4                       # GoPro 원본
├── _analysis.json (자동 생성)
├── _videos.json (자동 생성)
├── ride_meta.json (자동 생성)
├── coaching.srt (자동 생성)
├── output_videos/
│   ├── _cards/                   # 라이딩별 동적 카드 10장
│   ├── _overlay_work/            # PNG 시퀀스 (임시)
│   ├── _phase3_work/             # 클립 mp4 (임시)
│   ├── _narration_echo/          # TTS 캐시
│   ├── 전체_라이딩_오버레이.mp4
│   ├── 전체_라이딩_오버레이_자막싱크.mp4
│   ├── 전체_라이딩_오버레이_자막싱크_나레이션.mp4
│   ├── 본편_최종_<코스>_<일자>.mp4
│   └── 하이라이트_<코스>_<일자>.mp4
├── yt_metadata.md
├── yt_chapters.txt
└── yt_thumbnail*.png
```

## 매 라이딩 사용 (3분 안에 백그라운드 시작)

```bash
# 1) 라이딩 폴더 생성: <repo_root>/2026.X.XX.요일.HHMM 코스명/
# 2) FIT 파일 + GX*.MP4 떨궈두기
# 3) 더블클릭 또는:
bash _파이프라인/RUN_RIDE.command         # 메타·자막·카드 (1분)
bash _파이프라인/PHASE0_OVERLAY.command   # 오버레이 (~1~3h, 백그라운드)
bash _파이프라인/PHASE1_REBURN_SUBTITLES.command   # 자막 번인 (~25min)
bash _파이프라인/PHASE2_ADD_NARRATION.command      # 나레이션 (~5min)
bash _파이프라인/PHASE3_BUILD_FINAL_VIDEOS.command # 결합 (~10min)
bash _파이프라인/GENERATE_YOUTUBE_PACKAGE.command  # 메타·썸네일
bash _파이프라인/YT_UPLOAD.command                  # 업로드
```

각 .command는 osascript 폴더 선택 다이얼로그가 떠서 라이딩 폴더 선택. 또는 `RIDE_DIR=<경로> bash *.command`로 환경변수.

---

## 새 PC 셋업 (어느 Mac에서도 동작 — 경로 자동 인식)

### 0. Repo clone (홈 디렉토리 권장 — 로컬 SSD, Google Drive 외부)
```bash
git clone https://github.com/Finfilshsm/great_ride.git ~/cycling-tools
cd ~/cycling-tools
```

코드는 git이 동기화하니 어느 PC든 동일. 데이터(라이딩 폴더, FIT, GoPro)는 별도 위치 — 다음 단계에서 환경변수로 지정.

### 0-1. 데이터 폴더 위치 환경변수 설정 (PC별로 다름)
```bash
echo 'export CYCLING_DATA_DIR="/Volumes/<외장>/<클라우드>/Gran Fondo"' >> ~/.zshrc
source ~/.zshrc
```
- 집 맥미니: `/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo`
- 사무실 데스크탑: `~/Google Drive/Gran Fondo` 등 PC별로 다른 경로 OK
- 데이터 폴더에 라이딩 폴더(`2026.X.X...`)들과 `athlete_db.json`, `Seorak_*.gpx`가 있어야 함

### 1. Homebrew (없으면)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### 2. ffmpeg-full (libass 필수 — 자막 번인용)
```bash
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```
**주의**: `brew install ffmpeg`(표준)는 libass 누락으로 자막 번인 실패. 반드시 `homebrew-ffmpeg/ffmpeg`.

### 3. Python 의존성
```bash
pip3 install --break-system-packages --prefer-binary \
  fitparse pandas numpy pillow geopandas pyogrio shapely \
  google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### 4. NanumGothic 폰트 (인트로 PNG 생성용)
```bash
FONT_DIR="_파이프라인/intro_video/fonts"
mkdir -p "$FONT_DIR"
curl -L -o "$FONT_DIR/NanumGothic.ttf"           https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf
curl -L -o "$FONT_DIR/NanumGothicBold.ttf"       https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf
curl -L -o "$FONT_DIR/NanumGothicExtraBold.ttf"  https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-ExtraBold.ttf
```

### 5. Natural Earth shapefile (인트로 지도용)
```bash
NE_DIR="_파이프라인/intro_video/ne_data"
mkdir -p "$NE_DIR"
curl -L -o /tmp/ne.zip https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip
unzip -o /tmp/ne.zip -d "$NE_DIR" && rm /tmp/ne.zip
```

### 6. OpenAI API key (TTS 나레이션 신규 생성 시)
```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc
```
※ 캐시(`output_videos/_narration_echo/cache/`)가 있으면 재사용되어 키 불요.

### 7. YouTube OAuth 인증 (절대 커밋 금지)

**`_파이프라인/auth/client_secret.json`**: Google Cloud Console에서 OAuth 2.0 Desktop app으로 발급받은 JSON. **다른 PC로 옮길 때**:
- 1Password 같은 보안 저장소 또는 USB 메모리로 직접 복사
- 절대 git/이메일/Slack 등으로 전달 금지

**`_파이프라인/auth/token.json`**: 첫 OAuth 인증 시 자동 생성. PC별로 별도 발급 필요. `YT_UPLOAD.command` 실행하면 브라우저 OAuth 흐름 시작됨.

**`_파이프라인/auth/target_channel_id.txt`**: 업로드 대상 YouTube 채널 ID (Great Ride 등). 한 줄 텍스트. 다른 PC에 직접 복사.

### 8. BGM (라이선스 + 용량으로 git 미포함)
```bash
# ~/Downloads/bgm/ 또는 다른 곳에 mp3 모은 후
ln -s ~/Downloads/bgm _파이프라인/bgm
```

또는 INSTALL.command 실행:
```bash
bash INSTALL.command
```

---

## 알려진 호환성 이슈

| 증상 | 원인 | 해결 |
|---|---|---|
| `No such filter: 'subtitles'` | brew 표준 ffmpeg는 libass 미포함 | `homebrew-ffmpeg/ffmpeg/ffmpeg` 사용 |
| `gdal-config: not found` (fiona 빌드) | geopandas 0.x의 fiona dependency | geopandas 1.0+ (pyogrio 사용)로 |
| `socket.timeout` (TTS) | OpenAI API 일시 장애 | 재실행하면 캐시 활용 |
| `redirect_uri_mismatch` (OAuth) | OAuth client가 Web app | Desktop app 타입으로 재발급 |
| `Access blocked: not completed verification` | Test users 미등록 | Google Cloud Console → OAuth consent → Test users에 추가 |
| GoPro 시간 어긋남 (배터리 교체 후) | metadata creation_time 가정 | `lib/build_videos_json.py` 사용 (각 파일별 creation_time 정확) |

## 라이선스

MIT License — 개인 사용·수정 자유.
