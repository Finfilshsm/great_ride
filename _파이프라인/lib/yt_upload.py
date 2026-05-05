#!/usr/bin/env python3
"""YouTube Data API v3 자동 업로드 모듈.

Usage:
    python3 yt_upload.py <ride_dir> <target> [privacy]
        target: highlight | main | both
        privacy: private | unlisted (default) | public

요구 사항:
    - cycling-tools/_파이프라인/auth/client_secret.json (OAuth 2.0 desktop app)
    - 첫 실행 시 브라우저로 동의 → token.json 자동 저장
    - 재실행 시 token.json + refresh_token으로 자동 갱신
"""

import os
import sys
import re
import json
from pathlib import Path

# oauthlib는 기본적으로 redirect_uri가 https가 아니면 InsecureTransportError를 던짐.
# Desktop app OAuth는 http://localhost로 redirect되므로 이 가드를 풀어줘야 함.
# (Google은 localhost http redirect를 공식 허용 — 로컬 루프백이라 보안 영향 없음)
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError as e:
    print(f"✗ Python 의존성 누락: {e}")
    print("  설치: pip3 install --break-system-packages --prefer-binary "
          "google-api-python-client google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl',  # brand 채널 다중 접근
]

# 업로드 대상 채널 — 인증 후 이 이름과 일치하지 않으면 자동 재인증 유도
TARGET_CHANNEL = 'Great Ride'

# ----- 인증 -----
def get_youtube_service(client_secret_path: Path, token_path: Path):
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  → 토큰 자동 갱신...")
            creds.refresh(Request())
        else:
            print("  → 첫 실행: OAuth 동의 진행...", flush=True)
            import socket, subprocess, sys
            import wsgiref.simple_server, wsgiref.util

            # 1) 빈 포트 확보
            sock = socket.socket()
            sock.bind(('localhost', 0))
            port = sock.getsockname()[1]
            sock.close()

            # 2) flow + redirect_uri
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            flow.redirect_uri = f'http://localhost:{port}'

            # 3) authorization URL 생성 (state 자동, redirect_uri 포함)
            auth_url, _state = flow.authorization_url(
                access_type='offline',
                prompt='consent select_account',
                include_granted_scopes='true'
            )

            # ── PRE-OAUTH: 브라우저에서 Great Ride 채널로 전환 강제 ──
            # YouTube Data API의 OAuth는 인증 시점에 브라우저에서 활성화된
            # 채널에 토큰이 묶이므로, 인증 URL을 열기 전에 반드시
            # Great Ride 채널이 활성화되어 있어야 함.
            print(flush=True)
            print("=" * 70, flush=True)
            print(f"  ⚠ STEP 1: 브라우저에서 '{TARGET_CHANNEL}' 채널로 전환 필요", flush=True)
            print("=" * 70, flush=True)
            print("  YouTube를 자동으로 엽니다. 다음 절차로 채널 전환:", flush=True)
            print("    1. 우상단 프로필 아이콘 클릭", flush=True)
            print("    2. '계정 전환(Switch account)' 클릭", flush=True)
            print(f"    3. '{TARGET_CHANNEL}' 선택", flush=True)
            print(f"    4. 우상단 프로필이 '{TARGET_CHANNEL}'로 바뀐 것 확인", flush=True)
            print("=" * 70, flush=True)
            print(flush=True)

            try:
                subprocess.run(['open', 'https://www.youtube.com/account_advanced'], check=False)
            except Exception:
                pass

            # 사용자에게 채널 전환 완료 확인 다이얼로그
            try:
                confirm = subprocess.run([
                    'osascript', '-e',
                    f'display dialog "유튜브 우상단 프로필이 \\"{TARGET_CHANNEL}\\"으로 바뀐 것을 확인했나요?\\n\\n확인하지 않으면 JYJ 채널에 업로드됩니다." '
                    'buttons {"취소", "전환 완료 — 다음"} default button "전환 완료 — 다음" '
                    'with title "채널 전환 확인" with icon caution'
                ], capture_output=True, text=True, timeout=600)
                if 'button returned:취소' in confirm.stdout or confirm.returncode != 0:
                    print("  ✗ 사용자 취소 — 인증 중단", flush=True)
                    sys.exit(0)
            except subprocess.TimeoutExpired:
                print("  ✗ 시간 초과 — 인증 중단", flush=True)
                sys.exit(1)
            except Exception:
                # CLI 환경 등 osascript 불가 시 키 입력으로 대체
                try:
                    input(f"  → '{TARGET_CHANNEL}' 채널로 전환 후 Enter: ")
                except (EOFError, KeyboardInterrupt):
                    sys.exit(1)

            # 4) 클립보드 복사
            try:
                subprocess.run(['pbcopy'], input=auth_url, text=True, check=True)
                clip_msg = "  ✓ URL 클립보드 자동 복사됨 (Cmd+V로 붙여넣기)"
            except Exception:
                clip_msg = "  (pbcopy 실패 — 위 URL 수동 복사)"

            # 5) 출력
            print(flush=True)
            print("=" * 70, flush=True)
            print(f"  STEP 2: '{TARGET_CHANNEL}' 채널이 활성된 동일 브라우저에 URL 붙여넣기", flush=True)
            print("=" * 70, flush=True)
            print(flush=True)
            print(auth_url, flush=True)
            print(flush=True)
            print(clip_msg, flush=True)
            print(f"  → redirect_uri: http://localhost:{port}", flush=True)
            print()
            print("=" * 70, flush=True)
            print(f"  ★★★ 가장 중요한 단계 ★★★", flush=True)
            print("=" * 70, flush=True)
            print("  URL 붙여넣은 후 'Google 계정 선택' 화면이 뜹니다.", flush=True)
            print(f"  여기서 절대 'joyoungjin2.0@gmail.com'을 클릭하지 마세요!", flush=True)
            print(f"  → 목록에서 '{TARGET_CHANNEL}' 항목을 찾아서 클릭해야 함", flush=True)
            print(f"  → '{TARGET_CHANNEL}'이 안 보이면: '다른 계정 사용' 클릭하지 말고,", flush=True)
            print(f"     STEP 1로 돌아가 채널 전환 후 페이지 새로고침하고 재시도", flush=True)
            print("=" * 70, flush=True)
            print(flush=True)
            print("  → 권한 부여 후 자동으로 다음 단계 진행 (대기 중)...", flush=True)
            print(flush=True)
            sys.stdout.flush()

            # 계정 선택 단계의 결정적 안내 다이얼로그 (브라우저 동작 전에 보여줌)
            try:
                subprocess.Popen([
                    'osascript', '-e',
                    f'display dialog "OAuth URL을 브라우저에 붙여넣은 후 \\"계정 선택\\" 화면이 뜨면:\\n\\n  ❌ joyoungjin2.0@gmail.com 클릭 금지 (= JYJ로 인증됨)\\n  ✅ 목록에서 \\"{TARGET_CHANNEL}\\" 항목을 찾아 클릭\\n\\n\\"{TARGET_CHANNEL}\\" 항목이 안 보이면:\\n  → 취소하고 youtube.com에서 다시 채널 전환 후 재시도" '
                    'buttons {"확인"} default button "확인" with title "★ 계정 선택 단계 안내" with icon note'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            # 6) macOS notification
            try:
                subprocess.Popen([
                    'osascript', '-e',
                    'display notification "OAuth URL이 클립보드에 복사됨" with title "YT Upload"'
                ])
            except Exception:
                pass

            # 7) WSGI redirect handler — 직접 구현 (state 일관성 유지)
            class _RedirectHandler:
                def __init__(self):
                    self.last_uri = None
                def __call__(self, environ, start_response):
                    start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
                    self.last_uri = wsgiref.util.request_uri(environ)
                    return ['인증 완료. 이 창을 닫고 터미널로 돌아가세요.'.encode('utf-8')]

            # WSGI server 로그 출력 안하게
            class _SilentHandler(wsgiref.simple_server.WSGIRequestHandler):
                def log_message(self, format, *args):
                    pass

            handler = _RedirectHandler()
            server = wsgiref.simple_server.make_server(
                'localhost', port, handler,
                handler_class=_SilentHandler
            )
            server.handle_request()  # 단일 redirect 대기
            server.server_close()

            if not handler.last_uri:
                print("  ✗ redirect 응답 없음 — 인증 실패", flush=True)
                sys.exit(1)

            # 8) state 일관 유지하며 token fetch
            print("  → 인증 응답 수신 — token 교환 중...", flush=True)
            flow.fetch_token(authorization_response=handler.last_uri)
            creds = flow.credentials
        token_path.write_text(creds.to_json())
        token_path.chmod(0o600)
        print(f"  ✓ token.json 저장: {token_path}")

    return build('youtube', 'v3', credentials=creds)


# ----- 메타데이터 파싱 -----
def parse_metadata(md_path: Path, chapters_path: Path):
    """yt_metadata.md + yt_chapters.txt → (title, description, tags)"""
    md = md_path.read_text(encoding='utf-8')

    # 제목 (첫 후보)
    title_match = re.search(r'1\.\s*\*\*([^*]+?)\*\*', md)
    title = title_match.group(1).strip() if title_match else "Cycling Ride"

    # 설명 (## 설명 (Description) 다음 ```...``` 블록)
    desc_match = re.search(r'##\s*설명.*?\n```\n(.*?)\n```', md, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ""

    # 챕터 → description 끝에 추가 (유튜브 자동 인식)
    if chapters_path.exists():
        chapters = chapters_path.read_text(encoding='utf-8').strip()
        description = description + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📍 챕터\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + chapters

    # 태그
    tags_match = re.search(r'##\s*태그.*?\n```\n(.*?)\n```', md, re.DOTALL)
    tags = []
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).split(',') if t.strip()]
        tags = [t for t in tags if len(t) <= 30][:30]  # YouTube 제한

    # YouTube 제한
    title = title[:100]
    description = description[:5000]

    return title, description, tags


# ----- 업로드 -----
def upload_video(youtube, video_path: Path, title: str, description: str,
                 tags: list, thumbnail_path: Path = None, privacy: str = 'unlisted'):
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': '17',  # Sports
            'defaultLanguage': 'ko',
            'defaultAudioLanguage': 'ko',
        },
        'status': {
            'privacyStatus': privacy,  # private | unlisted | public
            'selfDeclaredMadeForKids': False,
            'embeddable': True,
        },
    }

    file_size = video_path.stat().st_size
    print(f"  → 업로드 시작: {video_path.name} ({file_size/1024/1024:.0f}MB)")

    media = MediaFileUpload(
        str(video_path),
        chunksize=8 * 1024 * 1024,  # 8MB chunks
        resumable=True,
        mimetype='video/mp4'
    )
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )

    response = None
    last_pct = -1
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct != last_pct and pct % 5 == 0:
                    print(f"    진행률: {pct}%")
                    last_pct = pct
        except HttpError as e:
            print(f"    ✗ 업로드 에러: {e}")
            raise

    video_id = response['id']
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  ✓ 업로드 완료: {url}")

    # 썸네일
    if thumbnail_path and thumbnail_path.exists():
        try:
            print(f"  → 썸네일 업로드: {thumbnail_path.name}")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype='image/png')
            ).execute()
            print(f"  ✓ 썸네일 적용 완료")
        except HttpError as e:
            print(f"  ⚠ 썸네일 업로드 실패 (채널 인증 미완료 가능): {e}")
            print(f"    (영상 자체는 업로드 완료, 썸네일은 YouTube Studio에서 수동 설정 가능)")

    return url, video_id


# ----- 메인 -----
def main():
    if len(sys.argv) < 3:
        print("Usage: yt_upload.py <ride_dir> <target> [privacy]")
        print("  target: highlight | main | both")
        print("  privacy: private | unlisted (default) | public")
        sys.exit(1)

    ride_dir = Path(sys.argv[1])
    target = sys.argv[2]
    privacy = sys.argv[3] if len(sys.argv) > 3 else 'unlisted'

    if not ride_dir.is_dir():
        print(f"✗ 라이딩 폴더 없음: {ride_dir}")
        sys.exit(1)

    # 인증
    auth_dir = Path(__file__).parent.parent / 'auth'
    client_secret = auth_dir / 'client_secret.json'
    token_path = auth_dir / 'token.json'

    if not client_secret.exists():
        print(f"✗ OAuth 인증 파일 없음: {client_secret}")
        print("  Google Cloud Console에서 OAuth 클라이언트(Desktop app) 발급 후")
        print("  client_secret.json으로 rename 후 위 위치에 배치")
        sys.exit(1)

    print("=" * 50)
    print("  YouTube 자동 업로드")
    print("=" * 50)
    print(f"  라이딩 폴더: {ride_dir}")
    print(f"  대상: {target}")
    print(f"  공개 설정: {privacy}")
    print()

    print("[1] OAuth 인증...")
    youtube = get_youtube_service(client_secret, token_path)
    print()

    # ----- 채널 확인 안전장치 -----
    print("[1.5] 인증된 채널 확인...")
    try:
        ch_resp = youtube.channels().list(part='snippet,id', mine=True).execute()
        items = ch_resp.get('items', [])
        if not items:
            print("  ✗ 인증된 채널 없음")
            sys.exit(1)
        ch = items[0]
        ch_title = ch['snippet']['title']
        ch_id = ch['id']
        print(f"  → 현재 활성 채널: {ch_title}")
        print(f"  → 채널 ID: {ch_id}")
    except Exception as e:
        print(f"  ⚠ 채널 조회 실패: {e}")
        ch_title = "(확인 불가)"
        ch_id = ""

    # 자동 검증: 인증된 채널명이 TARGET_CHANNEL과 일치하는지
    import subprocess
    target_norm = TARGET_CHANNEL.strip().lower().replace(' ', '')
    actual_norm = ch_title.strip().lower().replace(' ', '')
    is_match = (target_norm == actual_norm) or (target_norm in actual_norm) or (actual_norm in target_norm)

    if not is_match:
        print()
        print("  ✗ 잘못된 채널 인증됨!")
        print(f"     기대: {TARGET_CHANNEL}")
        print(f"     실제: {ch_title}")
        print()
        print(f"  → token.json 자동 삭제 후 재인증 안내")
        try:
            token_path.unlink()
            print(f"  ✓ 삭제됨: {token_path}")
        except Exception as e:
            print(f"  ⚠ 토큰 삭제 실패: {e}")

        try:
            subprocess.run([
                'osascript', '-e',
                f'display dialog "잘못된 채널이 인증되었습니다.\\n\\n  기대: {TARGET_CHANNEL}\\n  실제: {ch_title}\\n\\n토큰을 삭제했습니다. YT_UPLOAD.command를 다시 실행하고\\n인증 단계에서 반드시 \\"{TARGET_CHANNEL}\\" 채널로 전환 후 진행하세요." '
                'buttons {"확인"} default button "확인" with title "채널 불일치" with icon stop'
            ], capture_output=True, text=True, timeout=60)
        except Exception:
            pass
        sys.exit(1)

    # 일치하는 경우에도 한번 더 시각적 확인 (안전장치)
    try:
        result = subprocess.run([
            'osascript', '-e',
            f'display dialog "이 채널로 업로드합니다:\\n\\n  ▸ {ch_title}\\n\\n계속할까요?" buttons {{"취소", "업로드 진행"}} default button "업로드 진행" with title "채널 확인"'
        ], capture_output=True, text=True, timeout=120)
        if 'button returned:취소' in result.stdout:
            print("  ✗ 사용자 취소")
            sys.exit(0)
    except Exception:
        pass  # osascript 실패 시 그냥 진행 (CLI 환경 등)
    print()

    # 메타데이터 파싱
    print("[2] 메타데이터 파싱...")
    md_path = ride_dir / 'yt_metadata.md'
    chap_path = ride_dir / 'yt_chapters.txt'
    if not md_path.exists():
        print(f"✗ yt_metadata.md 없음 — GENERATE_YOUTUBE_PACKAGE.command 먼저 실행")
        sys.exit(1)

    title, description, tags = parse_metadata(md_path, chap_path)
    print(f"  ✓ 제목: {title}")
    print(f"  ✓ 설명: {len(description)}자 (챕터 포함)")
    print(f"  ✓ 태그: {len(tags)}개")
    print()

    # 업로드 대상 결정
    out_dir = ride_dir / 'output_videos'
    thumbnail = ride_dir / 'yt_thumbnail_1280x720.png'
    if not thumbnail.exists():
        thumbnail = ride_dir / 'yt_thumbnail.png'

    targets = []
    if target in ('highlight', 'both'):
        h = sorted(out_dir.glob('하이라이트_*.mp4'))
        if h:
            targets.append(('하이라이트', h[0], title))

    if target in ('main', 'both'):
        m = sorted(out_dir.glob('본편_최종_*.mp4'))
        if m:
            # 본편은 제목에 [본편] 추가
            main_title = ('[본편 풀버전] ' + title)[:100]
            targets.append(('본편', m[0], main_title))

    if not targets:
        print(f"✗ 업로드할 영상 없음 (output_videos/하이라이트_*.mp4 또는 본편_최종_*.mp4)")
        sys.exit(1)

    print(f"[3] {len(targets)}개 영상 업로드 시작 ({privacy})")
    print()
    results = []
    for i, (label, video_path, vtitle) in enumerate(targets, 1):
        print(f"━━━ [{i}/{len(targets)}] {label} 업로드 ━━━")
        try:
            url, vid = upload_video(youtube, video_path, vtitle, description, tags,
                                    thumbnail_path=thumbnail, privacy=privacy)
            results.append((label, url, vid))
        except Exception as e:
            print(f"✗ {label} 업로드 실패: {e}")
            results.append((label, None, None))
        print()

    print("=" * 50)
    print("✓ 업로드 종료")
    print("=" * 50)
    for label, url, vid in results:
        if url:
            print(f"  {label}: {url}")
        else:
            print(f"  {label}: 실패")
    print()
    print(f"공개 설정: {privacy}")
    if privacy == 'unlisted':
        print("  → YouTube Studio에서 검토 후 'public'으로 변경 권장")


if __name__ == '__main__':
    main()
