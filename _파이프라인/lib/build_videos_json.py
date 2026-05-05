#!/usr/bin/env python3
"""GoPro MP4 파일들 → _videos.json 정확히 생성.

핵심: GoPro의 각 파일별 metadata creation_time을 신뢰한다.
- 같은 파일의 chunks (예: GX010016, GX020016, GX030016)은 모두 동일한 creation_time을 공유
  (recording 시작 시각). chunks의 chronological start_utc는 file_creation + 누적 chunk duration.
- 다른 파일들 (예: GX*0016 vs GX*0017) 사이에는 GAP이 있을 수 있다 (배터리 교체 등).
  각 파일의 creation_time이 다르므로 자동으로 처리됨.

기존 RUN_RIDE.command의 _videos.json 생성기는 "첫 chunk creation_time + 누적 duration"으로
모든 chunk 시간을 추정했는데, 이는 파일 사이 갭을 무시한 잘못된 가정.

사용법:
    python3 build_videos_json.py <ride_dir>
"""
import sys
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone


def ffprobe_format(mp4):
    out = subprocess.check_output([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format_tags=creation_time:format=duration',
        '-of', 'json', str(mp4)
    ], text=True)
    return json.loads(out).get('format', {})


def parse_iso(s):
    """ISO datetime string → tz-aware UTC datetime."""
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_videos_json.py <ride_dir>")
    ride = Path(sys.argv[1])
    if not ride.is_dir():
        sys.exit(f"✗ 폴더 없음: {ride}")

    # GoPro 파일 패턴: GX[chunk2][file4].MP4
    # chunk: 01, 02, 03 (한 파일이 여러 chunks로 분할됨)
    # file: 0015, 0016 등 (recording session 단위)
    mp4s = sorted(list(ride.glob('GX*.MP4')) + list(ride.glob('GX*.mp4')))
    if not mp4s:
        sys.exit("✗ GX*.MP4 없음")

    # File 단위 그룹화
    groups = {}  # file_id → [(chunk_num, mp4_path), ...]
    for mp4 in mp4s:
        m = re.match(r'GX(\d{2})(\d{4})\.MP4', mp4.name, re.IGNORECASE)
        if not m:
            print(f"  ⚠ 패턴 매칭 안됨: {mp4.name} (skip)")
            continue
        chunk_num = int(m.group(1))
        file_id = m.group(2)
        groups.setdefault(file_id, []).append((chunk_num, mp4))

    # 각 그룹 내 chunk 순서대로 정렬
    for file_id in groups:
        groups[file_id].sort()

    videos = []
    for file_id, chunks in groups.items():
        first_chunk = chunks[0][1]
        info = ffprobe_format(first_chunk)
        file_creation = parse_iso(info.get('tags', {}).get('creation_time', ''))
        if file_creation is None:
            print(f"  ⚠ {first_chunk.name}: creation_time 없음, skip group")
            continue

        # 같은 파일의 chunks는 첫 chunk creation + 누적 duration으로 시간 매핑
        cum = 0.0
        for chunk_num, mp4 in chunks:
            chunk_info = ffprobe_format(mp4) if mp4 != first_chunk else info
            duration = float(chunk_info.get('duration', 0))
            chunk_start = file_creation + timedelta(seconds=cum)
            videos.append({
                'file': mp4.name,
                'start_utc': chunk_start.isoformat(),
                'duration_s': duration,
                'file_id': file_id,
                'chunk_num': chunk_num,
            })
            cum += duration

    # 최종 chronological 정렬 (start_utc 순)
    videos.sort(key=lambda v: v['start_utc'])

    out = {'ride_videos_chronological': [
        {'file': v['file'], 'start_utc': v['start_utc'], 'duration_s': v['duration_s']}
        for v in videos
    ]}

    target = ride / '_videos.json'
    if target.exists():
        bak = ride / '_videos.json.bak'
        if not bak.exists():
            bak.write_text(target.read_text(encoding='utf-8'), encoding='utf-8')
    target.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')

    print(f"  ✓ {len(videos)}개 chunks → {target.name}")
    for v in videos:
        print(f"    {v['file']:20s} start={v['start_utc']}  dur={v['duration_s']:.1f}s")

    # 시간 갭 분석 (파일 사이 GAP 감지)
    print("\n  파일 사이 GAP 분석:")
    prev = None
    for v in videos:
        if prev is not None:
            prev_end = parse_iso(prev['start_utc']) + timedelta(seconds=prev['duration_s'])
            cur_start = parse_iso(v['start_utc'])
            gap = (cur_start - prev_end).total_seconds()
            if gap > 5:
                print(f"    ⚠ GAP {gap:.0f}s ({gap/60:.1f}min): {prev['file']} 끝 → {v['file']} 시작")
                print(f"        ({prev['file_id']} → {v['file_id']}) 배터리 교체/재시작 추정")
        prev = v


if __name__ == '__main__':
    main()
