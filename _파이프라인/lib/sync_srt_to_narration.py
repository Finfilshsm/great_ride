"""TTS mp3 길이를 측정해서 SRT 큐 종료 시간을 자동 연장 (자막↔나레이션 싱크)."""
import sys, json, re, subprocess
from pathlib import Path

def mp3_duration(p):
    out = subprocess.check_output(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',str(p)]).decode().strip()
    return float(out)

def parse_srt(p):
    content = Path(p).read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*\n', content.strip())
    cues = []
    for b in blocks:
        lines = b.strip().split('\n')
        if len(lines) < 3: continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', lines[1])
        if not m: continue
        sh,sm,ss,sms,eh,em,es,ems = map(int, m.groups())
        cues.append([sh*3600+sm*60+ss+sms/1000, eh*3600+em*60+es+ems/1000, '\n'.join(lines[2:]).strip()])
    return cues

def fmt(s):
    if s < 0: s = 0
    h, m = int(s//3600), int((s%3600)//60); ss = int(s%60); ms = int((s-int(s))*1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"

def main():
    srt_in, narr_dir, srt_out = sys.argv[1], sys.argv[2], sys.argv[3]
    cues = parse_srt(srt_in)
    meta = json.loads((Path(narr_dir)/'_meta.json').read_text(encoding='utf-8'))
    durations = [mp3_duration(e['file']) if Path(e['file']).exists() else 0 for e in meta]
    BUFFER, GAP = 0.4, 0.2
    adjusted = 0
    for i, c in enumerate(cues):
        if i >= len(durations) or durations[i] == 0: continue
        natural = c[0] + durations[i] + BUFFER
        next_start = cues[i+1][0] - GAP if i < len(cues)-1 else natural + 1
        new_end = min(natural, next_start)
        if new_end > c[1]: c[1] = new_end; adjusted += 1
    out = []
    for i, (s,e,t) in enumerate(cues, 1):
        out.extend([str(i), f"{fmt(s)} --> {fmt(e)}", t, ""])
    Path(srt_out).write_text("\n".join(out), encoding='utf-8')
    print(f"  ✓ {adjusted}개 큐 종료 시간 연장 → {srt_out}")

if __name__ == '__main__': main()
