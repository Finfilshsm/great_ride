"""GPT-4o-mini로 분석적 자막 → 친근한 동료 코치 나레이션 변환."""
import os, sys, json, re, urllib.request, urllib.error
from pathlib import Path

API_KEY = os.environ.get('OPENAI_API_KEY')
if not API_KEY: sys.exit("✗ OPENAI_API_KEY 미설정")

SYSTEM = """당신은 한국어 사이클링 코칭 유튜브 채널 'Data Ride'의 시나리오 작가입니다.
시청자는 그란폰도를 준비하는 입문~중급 라이더(FTP 150-200W, W/kg 2.0-3.5)들입니다.

분석적인 자막 텍스트를 동료 코치가 옆에서 친근하게 들려주는 대화체 나레이션으로 변환하세요.

규칙:
1. 분석 라벨 형식 ('[Climb #5 진입] VAM 714') → 자연스러운 한국어 문장
2. 핵심 데이터(VAM, 파워, 경사, 거리)는 보존하되 흐르듯 녹여서
3. 그란폰도 준비자들에게 도움 되는 코칭 팁을 자연스럽게 추가
4. 길이는 자막 표시 시간보다 약간 길어도 OK (12-18초 분량 = 2-3 문장)
5. 권위적이지 않은 동료의 톤. "~하시면 좋아요", "~네요", "~인데요" 같은 부드러운 어미
6. 'Climb #N' → 'N번째 클라임' (다섯 번째 등)
7. 약자(VAM, FTP, IF, TSS)는 그대로 유지

응답: 변환된 텍스트만 반환. 설명·따옴표 없이."""

def chat(messages, model='gpt-4o-mini'):
    payload = {'model':model,'messages':messages,'temperature':0.7,'max_tokens':400}
    req = urllib.request.Request('https://api.openai.com/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':f'Bearer {API_KEY}','Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode('utf-8'))['choices'][0]['message']['content'].strip()
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ OpenAI {e.code}: {e.read().decode('utf-8',errors='ignore')[:300]}")

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
        cues.append((sh*3600+sm*60+ss+sms/1000, eh*3600+em*60+es+ems/1000, '\n'.join(lines[2:]).strip()))
    return cues

def fmt(s):
    if s<0: s=0
    h=int(s//3600); m=int((s%3600)//60); ss=int(s%60); ms=int((s-int(s))*1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"

def main():
    if len(sys.argv) < 2: sys.exit("사용법: python3 rewrite_narration.py <ride_dir>")
    ride = Path(sys.argv[1])
    coaching = ride/'coaching.srt'
    if not coaching.exists(): sys.exit(f"✗ {coaching} 없음")
    analysis = json.loads((ride/'_analysis.json').read_text(encoding='utf-8'))
    meta = json.loads((ride/'ride_meta.json').read_text(encoding='utf-8')) if (ride/'ride_meta.json').exists() else {}
    cues = parse_srt(coaching)
    print(f"  📝 {len(cues)}개 큐 변환 중 (GPT-4o-mini)...")
    new_cues = []
    for i, (s,e,t) in enumerate(cues, 1):
        rewritten = chat([{'role':'system','content':SYSTEM},
                         {'role':'user','content':f"다음 자막을 동료 코치 나레이션으로 변환:\n\n{t}"}])
        print(f"    [{i:2d}/{len(cues)}] {rewritten[:50]}...")
        new_cues.append((s, e, rewritten))

    summ = analysis['summary']
    intro = chat([
        {'role':'system','content':SYSTEM+'\n\n특별 지시: 영상 인트로. 환영 인사 + 오늘 코스 소개. 약 12초.'},
        {'role':'user','content':f"다음을 친근한 인트로 나레이션으로:\n\n오늘은 {meta.get('출발지','출발지')} 출발 {meta.get('코스_설명',meta.get('코스명',''))} {summ['distance_km']}km, 누적 상승 {summ['elev_gain_m']}m 코스를 분석해드릴게요."}])
    outro = chat([
        {'role':'system','content':SYSTEM+'\n\n특별 지시: 영상 아웃트로. 마무리 + 구독 권유 + 다음 만남. 약 8초.'},
        {'role':'user','content':"다음을 친근한 아웃트로로:\n\n오늘 영상이 도움이 되셨다면 구독·좋아요 부탁드립니다. 그란폰도 준비하시는 분들 응원해요. 다음 라이딩에서 만나요."}])
    (ride/'_narration_extras.json').write_text(json.dumps({'intro':intro,'outro':outro}, ensure_ascii=False, indent=2), encoding='utf-8')

    out = []
    for i, (s,e,t) in enumerate(new_cues, 1):
        out.extend([str(i), f"{fmt(s)} --> {fmt(e)}", t, ""])
    (ride/'narration.srt').write_text("\n".join(out), encoding='utf-8')
    print(f"  ✓ narration.srt + _narration_extras.json")

if __name__ == '__main__': main()
