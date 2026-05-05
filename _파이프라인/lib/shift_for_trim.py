#!/usr/bin/env python3
"""build_overlay_pipeline가 사전 GoPro 풋티지를 trim했을 때, 다운스트림 자산들의
타임스탬프를 맞춰주는 유틸.

처리 대상:
  - coaching.srt
  - coaching_synced.srt
  - narration.srt
  - output_videos/_narration_echo/_meta.json (start_s/end_s)

계산:
  trim_offset = sum(ch.duration for ch where ch가 fully skipped)
                + (ride_start_utc - first_partial_chapter.start_utc)

원본 SRT는 .pretrim.bak 으로 백업.
"""
import sys
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone


def parse_srt_blocks(text):
    blocks = re.split(r'\n\s*\n', text.strip())
    out = []
    for b in blocks:
        lines = b.strip().split('\n')
        if len(lines) < 3:
            continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', lines[1])
        if not m:
            continue
        sh, sm, ss, sms, eh, em, es, ems = map(int, m.groups())
        start = sh*3600 + sm*60 + ss + sms/1000
        end   = eh*3600 + em*60 + es + ems/1000
        body = '\n'.join(lines[2:])
        out.append([start, end, body])
    return out


def fmt_srt(s):
    if s < 0:
        s = 0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    ss = int(s % 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"


def shift_srt(path, offset_s, trimmed_dur=None, out_path=None):
    """SRT 시간 -offset_s 만큼 시프트.
    음수 시작은 0으로 클램프 (인트로 큐만), trimmed_dur 초과 큐는 끝쪽으로 클램프."""
    txt = Path(path).read_text(encoding='utf-8')
    cues = parse_srt_blocks(txt)
    new_cues = []
    for s, e, body in cues:
        new_s = s - offset_s
        new_e = e - offset_s
        if new_e < 0:
            # 큐가 trim 영역에 완전히 포함됨 → 인트로 큐만 0초로 끌어올림 (한 번만)
            if not new_cues and re.search(r'(오늘의 라이딩|개요|overview)', body, re.IGNORECASE):
                new_s, new_e = 0.5, 9.5
            else:
                continue
        elif new_s < 0:
            new_s = 0
        # 큐 시작이 트림된 영상 끝 이후이면 영상 끝쪽으로 클램프 (종합/액션 큐)
        if trimmed_dur is not None and new_s >= trimmed_dur:
            duration = e - s
            new_e = max(0, trimmed_dur - 1)
            new_s = max(0, new_e - duration)
        new_cues.append((new_s, new_e, body))

    out_lines = []
    for i, (s, e, body) in enumerate(new_cues, 1):
        out_lines.extend([str(i), f"{fmt_srt(s)} --> {fmt_srt(e)}", body, ""])
    out_path = out_path or path
    Path(out_path).write_text('\n'.join(out_lines), encoding='utf-8')
    return len(new_cues)


def shift_meta(path, offset_s, trimmed_dur=None):
    """_meta.json의 start_s, end_s를 시프트. 시프트 후 음수면 인트로만 keep, trimmed_dur 초과 시 끝쪽으로 클램프."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    new_data = []
    for item in data:
        old_s = item['start_s']
        old_e = item['end_s']
        ns = old_s - offset_s
        ne = old_e - offset_s
        if ne < 0:
            if not new_data:
                ns, ne = 0.5, 9.5
                item = {**item, 'start_s': ns, 'end_s': ne}
                new_data.append(item)
            continue
        if ns < 0:
            ns = 0
        # 트림 끝 초과 → 끝쪽으로 클램프
        if trimmed_dur is not None and ns >= trimmed_dur:
            duration = old_e - old_s
            ne = max(0, trimmed_dur - 1)
            ns = max(0, ne - duration)
        item = {**item, 'start_s': ns, 'end_s': ne}
        new_data.append(item)
    for i, item in enumerate(new_data, 1):
        item['index'] = i
    Path(path).write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(new_data)


def compute_trim_offset_and_duration(ride_dir):
    """_videos.json + ride_start/end로 trim offset(start) + 트림 영상 총 길이 계산."""
    from datetime import timedelta
    ride = Path(ride_dir)
    videos = json.loads((ride / '_videos.json').read_text(encoding='utf-8'))['ride_videos_chronological']
    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    ride_start = datetime.fromisoformat(A['ride_start_utc'])
    if ride_start.tzinfo is None:
        ride_start = ride_start.replace(tzinfo=timezone.utc)

    # ride_end = ride_start + elapsed_h
    elapsed_str = A['summary'].get('elapsed_h', '0:0:0')
    h, m, s = elapsed_str.split(':')
    elapsed_s = int(h)*3600 + int(m)*60 + int(s)
    ride_end = ride_start + timedelta(seconds=elapsed_s)

    cum = 0
    offset = None
    trimmed_duration = 0
    for v in videos:
        v_start = datetime.fromisoformat(v['start_utc'])
        if v_start.tzinfo is None:
            v_start = v_start.replace(tzinfo=timezone.utc)
        v_end = v_start + timedelta(seconds=v['duration_s'])

        # ride 윈도우와 overlap
        eff_start = max(v_start, ride_start)
        eff_end = min(v_end, ride_end)
        overlap = (eff_end - eff_start).total_seconds()

        if overlap <= 1.0:
            # 사전·사후 외부
            if v_end <= ride_start:
                cum += v['duration_s']
            continue

        # 첫 partial chapter (ride_start 위치)
        if offset is None:
            partial = (ride_start - v_start).total_seconds()
            offset = cum + max(0, partial)

        # 트림 후 사용 시간
        trimmed_duration += overlap

    return offset if offset is not None else 0, trimmed_duration


def compute_trim_offset(ride_dir):
    """역호환 wrapper."""
    offset, _ = compute_trim_offset_and_duration(ride_dir)
    return offset


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: shift_for_trim.py <ride_dir>")
    ride = Path(sys.argv[1])
    offset, trimmed_dur = compute_trim_offset_and_duration(ride)
    print(f"  → Trim offset: {offset:.3f}s ({int(offset//3600)}h {int((offset%3600)//60)}m {offset%60:.1f}s)")
    print(f"  → 트림된 영상 총 길이: {trimmed_dur:.0f}s ({int(trimmed_dur//3600)}h {int((trimmed_dur%3600)//60)}m {trimmed_dur%60:.0f}s)")

    targets = [
        ride / 'coaching.srt',
        ride / 'coaching_synced.srt',
        ride / 'narration.srt',
    ]
    for p in targets:
        if not p.exists():
            print(f"    ✗ {p.name} 없음 (skip)")
            continue
        bak = p.with_suffix(p.suffix + '.pretrim.bak')
        if not bak.exists():
            shutil.copy2(p, bak)
        n = shift_srt(p, offset, trimmed_dur=trimmed_dur)
        print(f"    ✓ {p.name}: {n}개 큐 (백업 {bak.name})")

    meta = ride / 'output_videos' / '_narration_echo' / '_meta.json'
    if meta.exists():
        bak = meta.with_suffix('.json.pretrim.bak')
        if not bak.exists():
            shutil.copy2(meta, bak)
        n = shift_meta(meta, offset, trimmed_dur=trimmed_dur)
        print(f"    ✓ {meta.name}: {n}개 항목 (백업 {bak.name})")


if __name__ == '__main__':
    main()
