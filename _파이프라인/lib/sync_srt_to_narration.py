"""TTS mp3 길이를 측정해서 SRT cue 시각 + _meta.json 모두 정합되게 정렬.

기존 동작: cue end만 mp3 길이로 연장 (자막 표시).
신규 동작 (overlap 방지):
  1. 이전 cue가 mp3 길이 + GAP 만큼 끝나기 전에 다음 cue가 시작하면, 다음 cue start_s를 시프트
  2. 시프트된 cue들은 _meta.json의 start_s도 동기화 갱신 → narration ffmpeg 합성 시 자연 분리
  3. 자막 end도 새 start_s + mp3 길이 + BUFFER로 갱신
"""
import sys, json, re, subprocess
from pathlib import Path

BUFFER = 0.4   # cue 끝 (자막) — narration mp3 + 0.4초까지 표시
GAP    = 0.5   # cue 간 최소 간격 (overlap 방지)


def mp3_duration(p):
    out = subprocess.check_output(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',str(p)]).decode().strip()
    return float(out)


def parse_srt(p):
    content = Path(p).read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*\n', content.strip())
    cues = []
    for b in blocks:
        lines = b.strip().split('\n')
        if len(lines) < 3:
            continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', lines[1])
        if not m:
            continue
        sh,sm,ss,sms,eh,em,es,ems = map(int, m.groups())
        cues.append([sh*3600+sm*60+ss+sms/1000, eh*3600+em*60+es+ems/1000, '\n'.join(lines[2:]).strip()])
    return cues


def fmt(s):
    if s < 0:
        s = 0
    h, m = int(s//3600), int((s%3600)//60)
    ss = int(s%60)
    ms = int(round((s-int(s))*1000))
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"


def video_duration(narr_dir):
    """자막싱크본 영상 길이 측정 — 끝 넘는 cue 차단용."""
    candidates = [
        Path(narr_dir).parent / '전체_라이딩_오버레이_자막싱크.mp4',
        Path(narr_dir).parent / '전체_라이딩_오버레이.mp4',
    ]
    for p in candidates:
        if p.exists():
            try:
                return mp3_duration(str(p))
            except Exception:
                pass
    return None


def main():
    srt_in, narr_dir, srt_out = sys.argv[1], sys.argv[2], sys.argv[3]
    cues = parse_srt(srt_in)
    meta_path = Path(narr_dir)/'_meta.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    durations = [mp3_duration(e['file']) if Path(e['file']).exists() else 0 for e in meta]
    video_dur = video_duration(narr_dir)  # 자막싱크본 길이 (있으면)

    n = min(len(cues), len(durations))
    shifted = 0
    extended = 0
    backshifted = 0

    # 1) cue start_s 자동 시프트 — 이전 cue (start + mp3 + BUFFER) + GAP 이후로
    for i in range(1, n):
        prev_dur = durations[i-1] if durations[i-1] > 0 else 0
        prev_natural_end = cues[i-1][0] + prev_dur + BUFFER
        min_start = prev_natural_end + GAP
        if cues[i][0] < min_start:
            shift = min_start - cues[i][0]
            cues[i][0] += shift
            cues[i][1] += shift  # end도 같이
            shifted += 1

    # 1b) 끝 cue가 영상 길이를 넘으면 뒤에서부터 압축 (cascade backshift)
    if video_dur and n > 0:
        max_end = video_dur - 1.0  # 1초 buffer
        # 마지막 cue부터 거꾸로: end가 max_end 넘으면 start를 (max_end - mp3_dur)로 강제
        for i in range(n - 1, -1, -1):
            mp3 = durations[i] if i < len(durations) else 0
            limit_start = max_end - mp3 - BUFFER
            if cues[i][0] > limit_start:
                back = cues[i][0] - limit_start
                cues[i][0] = limit_start
                cues[i][1] -= back
                backshifted += 1
                # 이전 cue도 검사 (이전 cue end가 새 cue start 넘으면 해당 cue도 backshift)
                if i > 0:
                    prev_end = cues[i-1][0] + (durations[i-1] if i-1 < len(durations) else 0) + BUFFER
                    if prev_end > cues[i][0] - GAP:
                        new_prev_end = cues[i][0] - GAP
                        new_prev_start = new_prev_end - (durations[i-1] if i-1 < len(durations) else 0) - BUFFER
                        cues[i-1][1] -= (cues[i-1][0] - new_prev_start)
                        cues[i-1][0] = new_prev_start
            max_end = cues[i][0] - GAP  # 다음(이전 시각상) cue의 max_end

    # 2) cue end를 mp3 길이로 연장 (자막 표시) — 다음 cue 시작 직전까지만
    for i in range(n):
        if durations[i] == 0:
            continue
        natural_end = cues[i][0] + durations[i] + BUFFER
        next_start = cues[i+1][0] - 0.1 if i+1 < n else natural_end + 1
        new_end = min(natural_end, next_start)
        if new_end > cues[i][1]:
            cues[i][1] = new_end
            extended += 1

    # 3) _meta.json의 start_s를 갱신된 cue 시각으로 동기화
    for i in range(n):
        if i < len(meta):
            meta[i]['start_s'] = round(cues[i][0], 3)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    # 4) SRT 출력
    out_lines = []
    for i, (s, e, t) in enumerate(cues, 1):
        out_lines.extend([str(i), f"{fmt(s)} --> {fmt(e)}", t, ""])
    Path(srt_out).write_text("\n".join(out_lines), encoding='utf-8')
    print(f"  ✓ overlap 방지: {shifted}개 cue 시프트 · 끝 보호: {backshifted}개 backshift · 자막 연장: {extended}개 → {srt_out}")
    print(f"  ✓ _meta.json start_s 동기화 ({n}개)" + (f" · 영상 {video_dur:.0f}s 검증" if video_dur else ""))


if __name__ == '__main__':
    main()
