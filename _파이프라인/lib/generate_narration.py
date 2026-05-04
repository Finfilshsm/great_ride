"""OpenAI TTS로 SRT → MP3 시퀀스 생성 (한국어 최적화, echo 남성 기본)."""
import os, sys, json, re, hashlib, urllib.request, urllib.error
from pathlib import Path
from collections import OrderedDict

API_KEY = os.environ.get('OPENAI_API_KEY')
if not API_KEY: sys.exit("✗ OPENAI_API_KEY 미설정")

VALID_VOICES = ['alloy','echo','fable','onyx','nova','shimmer']
SINO_DIGITS = "영일이삼사오육칠팔구"
SINO_PLACES = ["", "십", "백", "천"]
SINO_UNITS  = ["", "만", "억", "조"]

def int_to_korean(n):
    if n == 0: return "영"
    if n < 0: return "마이너스 " + int_to_korean(-n)
    s = str(n); pad = (4-len(s)%4)%4; s = "0"*pad + s
    groups = [s[i:i+4] for i in range(0,len(s),4)]; n_groups = len(groups); parts = []
    for i, g in enumerate(groups):
        unit_idx = n_groups-1-i; gstr = ""
        for j, d in enumerate(g):
            d = int(d)
            if d == 0: continue
            p_idx = 3-j
            gstr += (SINO_PLACES[p_idx] if d==1 and p_idx>0 else SINO_DIGITS[d]+SINO_PLACES[p_idx])
        if gstr: parts.append(gstr + SINO_UNITS[unit_idx])
    return "".join(parts) if parts else "영"

def num_str_to_korean(s):
    s = s.replace(',','')
    if '.' in s:
        whole, frac = s.split('.',1)
        return f"{int_to_korean(int(whole)) if whole else '영'} 점 {' '.join(SINO_DIGITS[int(d)] for d in frac if d.isdigit())}"
    return int_to_korean(int(s))

ORDINAL_KOR = {1:"첫 번째",2:"두 번째",3:"세 번째",4:"네 번째",5:"다섯 번째",6:"여섯 번째",7:"일곱 번째",8:"여덟 번째",9:"아홉 번째",10:"열 번째",11:"열한 번째",12:"열두 번째",13:"열세 번째",14:"열네 번째",15:"열다섯 번째"}

def clean_text(text):
    text = text.strip()
    text = re.sub(r'(\d),(\d{3})', r'\1\2', text); text = re.sub(r'(\d),(\d{3})', r'\1\2', text)
    text = re.sub(r'^\s*\[(.+?)\]\s*', r'\1. ', text); text = re.sub(r'\[(.+?)\]', r'\1', text)
    text = re.sub(r'^\s*[▸•*★◀▶]+\s*', '', text)
    for ch in ['★','▸','▶','◀','•']: text = text.replace(ch,'')
    text = re.sub(r'Climb\s*#?\s*(\d+)', lambda m: f"{ORDINAL_KOR.get(int(m.group(1)), m.group(1)+'번째')} 클라임", text)
    units = OrderedDict([('km/h','시속 킬로미터'),('W/kg','와트 퍼 킬로그램'),('m/h','미터 퍼 시간'),('m/km','미터 퍼 킬로미터'),('km','킬로미터'),('kg','킬로그램'),('bpm','비피엠'),('rpm','알피엠'),('kcal','킬로칼로리'),('cal','칼로리'),('%','퍼센트'),('W','와트'),('m','미터'),('hr','시간'),('h','시간')])
    for ue, uk in units.items():
        b = r'\b' if ue[-1].isalpha() else ''
        text = re.sub(r'([+\-]?\d+(?:\.\d+)?)\s*' + re.escape(ue) + b,
                      lambda m, u=uk: f"{num_str_to_korean(m.group(1).lstrip('+'))} {u}", text)
    text = re.sub(r'\+(\d+)', lambda m: int_to_korean(int(m.group(1))), text)
    text = re.sub(r'(\d+):(\d+)', lambda m: f"{int_to_korean(int(m.group(1)))}시 {int_to_korean(int(m.group(2)))}분", text)
    abbr = OrderedDict([('VAM','브이에이엠'),('FTP','에프티피'),('TSS','티에스에스'),('LTHR','엘티에이치알'),('RHR','안정시 심박'),('IF','아이에프'),('VI','브이아이'),('NP','엔피'),('HR','심박'),('Pw:Hr','파워 대 심박'),('TDF','티디에프')])
    for k, v in abbr.items(): text = re.sub(r'\b'+re.escape(k)+r'\b', v, text)
    text = re.sub(r'\d+\.\d+', lambda m: num_str_to_korean(m.group(0)), text)
    text = re.sub(r'\b(\d{3,})\b', lambda m: int_to_korean(int(m.group(0))), text)
    text = text.replace(' · ',', ').replace('·',', ').replace(' — ',', ').replace('—',', ').replace(' – ',', ').replace('–',', ')
    text = re.sub(r'\s+/\s+',', ', text)
    text = re.sub(r'([가-힣])(\d)', r'\1 \2', text); text = re.sub(r'(\d)([가-힣])', r'\1 \2', text)
    text = re.sub(r'\s+',' ',text).strip(); text = re.sub(r',\s*,',',', text)
    if text and text[-1] not in '.?!,。': text += '.'
    return text

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
        raw = '\n'.join(lines[2:]).strip()
        clean = ' '.join(clean_text(l) for l in raw.split('\n') if l.strip())
        cues.append((sh*3600+sm*60+ss+sms/1000, eh*3600+em*60+es+ems/1000, raw, clean))
    return cues

def tts(text, voice, model):
    payload = {'model': model, 'voice': voice, 'input': text, 'response_format': 'mp3'}
    if 'gpt-4o' in model:
        payload['instructions'] = '당신은 한국어 사이클링 코칭 영상의 나레이터입니다. 동료 라이더에게 자기 경험을 친근하게 들려주는 코치처럼 따뜻한 톤으로 읽으세요. 그란폰도를 준비하는 입문~중급 라이더들에게 도움이 되는 친절한 어조입니다. 권위적이지 않게, 옆에서 조언해주는 동료의 느낌으로. 숫자와 단위 사이는 자연스럽게 끊어 읽고, 핵심 데이터는 살짝 강조하며, 문장 끝에서 충분히 호흡을 두세요. 너무 빠르지 않게, 약간 느긋한 속도가 좋습니다.'
    else:
        payload['speed'] = 0.95
    req = urllib.request.Request('https://api.openai.com/v1/audio/speech',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ OpenAI 오류 {e.code}: {e.read().decode('utf-8',errors='ignore')[:300]}")

def cache_key(t, v, m): return hashlib.sha256(f"{v}|{m}|{t}".encode('utf-8')).hexdigest()[:16]

def main():
    if len(sys.argv) < 3: sys.exit("사용법: python3 generate_narration.py <srt> <out_dir> [voice=echo] [model=gpt-4o-mini-tts]")
    srt_path, out_dir = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else 'echo'
    model = sys.argv[4] if len(sys.argv) > 4 else 'gpt-4o-mini-tts'
    if voice not in VALID_VOICES: sys.exit(f"✗ 음성: {VALID_VOICES}")
    cues = parse_srt(srt_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cache_dir = Path(out_dir)/'cache'; cache_dir.mkdir(exist_ok=True)
    print(f"  📢 {voice}/{model}, {len(cues)}개 큐, {sum(len(c[3]) for c in cues)}자")
    metadata, hits = [], 0
    for i, (s,e,raw,clean) in enumerate(cues, 1):
        ck = cache_key(clean, voice, model); cache_path = cache_dir/f'{ck}.mp3'; out_path = Path(out_dir)/f'tts_{i:02d}.mp3'
        if cache_path.exists() and cache_path.stat().st_size > 100:
            hits += 1; print(f"    [{i:2d}/{len(cues)}] 💾 {clean[:50]}...")
        else:
            print(f"    [{i:2d}/{len(cues)}] 🌐 {clean[:50]}...")
            cache_path.write_bytes(tts(clean, voice, model))
        if out_path.exists() or out_path.is_symlink(): out_path.unlink()
        out_path.write_bytes(cache_path.read_bytes())
        metadata.append({'index':i,'start_s':s,'end_s':e,'file':str(out_path),'text_raw':raw,'text_tts':clean})
    Path(out_dir,'_meta.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  ✓ 신규 {len(cues)-hits}개 / 캐시 {hits}개")

if __name__ == '__main__': main()
