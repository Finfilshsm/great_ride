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

## 설치 (1회)

```bash
# 1. 도구 위치
git clone https://github.com/USER/cycling-data-ride.git ~/cycling-tools
cd ~/cycling-tools

# 2. 의존성
brew install ffmpeg-full python3
pip3 install fitparse pandas numpy Pillow geopandas pyogrio koreanize-matplotlib

# 3. 환경 변수
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc

# 4. BGM 심볼릭 링크 (이미 다운로드된 BGM 재사용)
bash INSTALL.command
```

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
