#!/usr/bin/env python3
"""유튜브 메타데이터(yt_metadata.md + yt_chapters.txt) 동적 생성.

_analysis.json + ride_meta.json + coaching.srt 기반.
"""
import sys
import os
import json
import re
from pathlib import Path


def srt_to_chapters(srt_path, intro_offset=10):
    if not Path(srt_path).exists():
        return ""
    txt = Path(srt_path).read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*\n', txt.strip())
    out = ["0:00 인트로"]
    for blk in blocks:
        lines = blk.strip().split('\n')
        if len(lines) < 3:
            continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->', lines[1])
        if not m:
            continue
        h, mm, ss = map(int, m.groups())
        total_s = h * 3600 + mm * 60 + ss + intro_offset
        ts_h = total_s // 3600
        ts_m = (total_s % 3600) // 60
        ts_s = total_s % 60
        title = lines[2].strip()
        title = re.sub(r'^\[(.+?)\]\s*', r'\1: ', title)
        title = title[:50]
        if ts_h > 0:
            out.append(f"{ts_h}:{ts_m:02d}:{ts_s:02d} {title}")
        else:
            out.append(f"{ts_m}:{ts_s:02d} {title}")
    return '\n'.join(out) + '\n'


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_yt_metadata.py <ride_dir> [course_name] [date_tag]")
    ride = Path(sys.argv[1])
    course_name = sys.argv[2] if len(sys.argv) > 2 else ride.name.split()[-1]
    date_tag = sys.argv[3] if len(sys.argv) > 3 else os.environ.get('DATE_TAG', '')

    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8'))
    s = A['summary']
    b = A.get('best_climb') or {}
    fade = A.get('fade_climb') or {}
    r = A['rider']

    decoupling = s.get('decoupling_pct', 0)
    vam_drop = 0
    if b and fade and b.get('vam_m_per_h'):
        vam_drop = (1 - fade.get('vam_m_per_h', 0) / b['vam_m_per_h']) * 100

    # 제목 후보
    titles = [
        f"[그란폰도 시뮬레이션] {course_name} {s['distance_km']}km · TSS {s['tss']} — 데이터 기반 페이싱·영양 코칭",
        f"{course_name} {s['distance_km']}km — Climb #{b.get('index','?')}(VAM {b.get('vam_m_per_h',0):.0f}) vs Climb #{fade.get('index','?')}(VAM {fade.get('vam_m_per_h',0):.0f}) 분석",
        f"FTP {r['ftp_w']}W 라이더의 그란폰도 시뮬 — {course_name} {s['distance_km']}km · TSS {s['tss']} · 디커플링 {decoupling}%",
    ]

    # 설명 동적
    intro = f"🚴 {M.get('코스명','')}"
    if M.get('코스_설명'):
        intro += f" ({M['코스_설명']})"
    if M.get('출발지'):
        intro += f" — {M['출발지']} 출발"
    if M.get('코스_약자_풀이'):
        intro += f"\n{M['코스_약자_풀이']}"

    actions = ["출발 30분 전 탄수 80g — 글리코겐 비축"]
    if decoupling > 8:
        actions.append("보급 시간당 60g 분할 (한 번에 1,000 kcal 금지)")
    else:
        actions.append("현재 보급 패턴 유지 + 거리 5~10% 증량 검토")
    if s['avg_cadence'] < 85:
        actions.append(f"케이던스 80+ 유지 (오늘 평균 {s['avg_cadence']}rpm)")
    else:
        actions.append(f"케이던스 {s['avg_cadence']}rpm — 그대로 유지")

    cause = "영양 패턴 (사전 미흡 + 보급 불균등)" if decoupling > 10 else "후반 누적 피로 + 영양 부족"

    desc_parts = [
        intro,
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📊 라이딩 지표',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        f"▸ 거리:    {s['distance_km']}km",
        f"▸ 상승:    +{s['elev_gain_m']}m  ({s['elev_per_km']}m/km)",
        f"▸ 경과시간: {s.get('elapsed_h','?')}  (주행 {s.get('moving_h','?')})",
        f"▸ 평균속도: {s['avg_speed_kmh']} km/h",
        '',
        f"▸ 평균파워: {s['avg_power_w']}W (NP {s['np_w']}W)",
        f"▸ TSS:    {s['tss']}    IF: {s['if_']}    VI: {s['vi']}",
        f"▸ 평균HR: {s['avg_hr']} bpm  (Max {s['max_hr']})",
        f"▸ 평균케이던스: {s['avg_cadence']} rpm",
        f"▸ Pw:Hr 디커플링: {decoupling}%  (5% 이하 정상)",
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '👤 라이더 프로파일',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        f"▸ FTP:  {r['ftp_w']}W",
        f"▸ 체중: {r['weight_kg']}kg",
        f"▸ W/kg: {r['w_per_kg']}",
        f"▸ LTHR: {r['lthr']} bpm",
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '🔍 오늘의 코칭 포인트',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ]
    if b and fade and vam_drop > 0:
        desc_parts.extend([
            f"같은 클라임 영역에서 Climb #{b.get('index')}(km {b.get('start_km',0):.1f}, VAM {b.get('vam_m_per_h',0):.0f}) 베스트,",
            f"Climb #{fade.get('index')}(km {fade.get('start_km',0):.1f}, VAM {fade.get('vam_m_per_h',0):.0f}) 페이드 -{vam_drop:.0f}%.",
            '',
            f"▶ 1차 원인: {cause}",
            f"▶ 데이터 근거: Pw:Hr 디커플링 {decoupling}% (정상 5% 이하)",
        ])
    desc_parts.extend([
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📌 다음 라이딩 액션',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        f"1. {actions[0]}",
        f"2. {actions[1]}",
        f"3. {actions[2]}",
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '🛠 데이터 출처',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '- Garmin .fit (Edge / 파워미터)',
        '- GoPro 4K → 1080p 게이지 오버레이',
        '- OpenAI TTS 코칭 나레이션 (한국어 echo)',
        '- 자체 분석 파이프라인 (cycling-tools)',
        '',
        f"#그란폰도 #사이클링 #FTP #TSS #파워미터 #VAM #그란폰도시뮬레이션 #{course_name} #DataRide #BigRide #사이클링코칭",
    ])
    desc = '\n'.join(desc_parts)

    chapters = srt_to_chapters(ride / 'coaching.srt')

    tags = ", ".join([
        "그란폰도", "사이클링", course_name, "FTP", "TSS", "파워미터", "VAM",
        "그란폰도 시뮬레이션", "사이클링 코칭", "Data Ride", "Big Ride",
        "GoPro", "Garmin", "데이터 분석", "Climb 분석", "페이드", "영양 코칭",
        "디커플링", "사이클링 훈련", "라이더 코칭",
    ])

    md = f"""# 유튜브 업로드 메타데이터 — {course_name} ({s['distance_km']}km)

## 제목 후보
1. **{titles[0]}**
2. {titles[1]}
3. {titles[2]}

## 설명 (Description)
```
{desc.strip()}
```

## 태그 (Tags)
```
{tags}
```

## 카테고리
스포츠 (Sports)

## 추천 설정
- 화질: 1080p HEVC
- 자막: coaching_synced.srt 활용
- 챕터: yt_chapters.txt 내용을 설명 끝에 추가
"""
    (ride / 'yt_metadata.md').write_text(md, encoding='utf-8')
    print(f"  ✓ yt_metadata.md")

    (ride / 'yt_chapters.txt').write_text(chapters, encoding='utf-8')
    print(f"  ✓ yt_chapters.txt ({len(chapters.splitlines())}개 챕터)")


if __name__ == '__main__':
    main()
