"""SRT → ASS 변환기 (스타일 내장)."""
import sys, re
from pathlib import Path

def srt_to_ass(srt_path, ass_path, font_name="AppleSDGothicNeo"):
    srt = Path(srt_path).read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*\n', srt.strip())
    cues = []
    for b in blocks:
        lines = b.strip().split('\n')
        if len(lines) < 3: continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', lines[1])
        if not m: continue
        sh,sm,ss,sms,eh,em,es,ems = map(int, m.groups())
        start = f"{sh}:{sm:02d}:{ss:02d}.{sms//10:02d}"
        end = f"{eh}:{em:02d}:{es:02d}.{ems//10:02d}"
        text = "\\N".join(lines[2:])
        cues.append((start, end, text))
    ass = f"""[Script Info]
Title: 코칭 해설
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Coach,{font_name},38,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC0000000,1,0,0,0,100,100,0,0,4,2,0,2,30,30,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    for s, e, t in cues:
        ass += f"Dialogue: 0,{s},{e},Coach,,0,0,0,,{t}\n"
    Path(ass_path).write_text(ass, encoding='utf-8')
    print(f"Converted {len(cues)} cues → {ass_path}")
    return len(cues)

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    font = sys.argv[3] if len(sys.argv) > 3 else "AppleSDGothicNeo"
    srt_to_ass(src, dst, font)
