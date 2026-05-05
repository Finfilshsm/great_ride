#!/usr/bin/env python3
"""다각적 라이딩 브리핑 마크다운 생성.

athlete_db.json + 현재 라이딩 _analysis.json을 조합해 7개 관점에서 분석:
1. 자체 분석 — 이번 라이딩 핵심 지표
2. 시계열 추이 — CTL/ATL/TSB 4주
3. 누적 비교 — 전 라이딩 대비 Δ
4. 코스 베스트 — climb 라이브러리 + 진보율
5. 영양 효율 — 보급 패턴별 디커플링 결과
6. A-race 준비도 — Seorak GF 5차원 게이지
7. D-day 권장 — Build/Peak/Taper 단계별 액션

사용법:
    python3 build_athlete_briefing.py <ride_dir>
산출물: <ride_dir>/analysis_briefing_<date>.md
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

import athlete_db


def fmt_h(s):
    if not s or not isinstance(s, str):
        return '?'
    return s


def briefing(ride_dir):
    ride = Path(ride_dir)
    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8')) if (ride / 'ride_meta.json').exists() else {}
    s = A['summary']
    R = A.get('rider', athlete_db.RIDER)
    climbs = A.get('climbs', []) or []

    # athlete_db (cycling-tools 부모 폴더)
    base_dir = ride.parent
    db = athlete_db.load_db(base_dir)
    if db is None:
        db, _ = athlete_db.refresh_db(base_dir)

    # 일자
    course_name = M.get('코스명', '') or ride.name.split()[-1]
    m = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', ride.name)
    date_str = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ''

    # ───── 1. 자체 분석 ─────
    tss = s.get('tss', 0) or 0
    if_val = s.get('if_', 0) or 0
    decoupling = s.get('decoupling_pct', 0) or 0
    cadence = s.get('avg_cadence', 0) or 0

    sec1 = [
        f"## 1. 오늘의 라이딩 — {course_name} ({date_str})",
        '',
        f"- **거리·상승**: {s.get('distance_km', 0)} km · +{s.get('elev_gain_m', 0):,}m ({s.get('elev_per_km', 0)} m/km)",
        f"- **시간**: 경과 {fmt_h(s.get('elapsed_h'))} · 주행 {fmt_h(s.get('moving_h'))} · 평균 {s.get('avg_speed_kmh', 0)} km/h",
        f"- **파워**: Avg {s.get('avg_power_w', 0)}W / NP {s.get('np_w', 0)}W (VI {s.get('vi', 0)})",
        f"- **TSS · IF**: **{tss}** · **{if_val}**",
        f"- **HR**: 평균 {s.get('avg_hr', 0)} bpm / Max {s.get('max_hr', 0)} bpm",
        f"- **케이던스**: {cadence} rpm",
        f"- **디커플링**: **{decoupling}%** {'⚠️ 높음 (영양/페이싱 점검)' if decoupling > 8 else '✓ 양호'}",
        f"- **클라임**: {len(climbs)}개 검출",
    ]

    # 평가
    if tss > 250:
        sec1.append(f"\n→ 고강도 라이딩 (TSS {tss}). **72시간 회복 윈도우** 권장.")
    elif tss > 150:
        sec1.append(f"\n→ 중강도 베이스 라이딩 (TSS {tss}). 48시간 후 다음 자극 가능.")
    else:
        sec1.append(f"\n→ 회복·베이스 라이딩 (TSS {tss}).")

    # ───── 2. 시계열 추이 (CTL/ATL/TSB) ─────
    pmc = db.get('pmc', [])
    today_pmc = next((p for p in reversed(pmc) if p['date'] == date_str), pmc[-1] if pmc else None)

    sec2 = ['## 2. Performance Management Chart (CTL/ATL/TSB)', '']
    if today_pmc:
        ctl = today_pmc['ctl']
        atl = today_pmc['atl']
        tsb = today_pmc['tsb']
        # TSB 해석
        if tsb < -20:
            tsb_state = '⚠️ 깊은 피로 (회복 필요)'
        elif tsb < -10:
            tsb_state = '🟠 누적 피로 (조심)'
        elif tsb < 5:
            tsb_state = '🟢 균형 (적응 중)'
        elif tsb < 25:
            tsb_state = '✨ Peak — 컨디션 좋음'
        else:
            tsb_state = '🔵 Detrain (강도 부족)'

        sec2.extend([
            f"- **CTL (피트니스, 42d)**: {ctl}",
            f"- **ATL (피로, 7d)**: {atl}",
            f"- **TSB (밸런스)**: {tsb} — {tsb_state}",
            '',
        ])

    # 최근 7일 추이
    if len(pmc) >= 7:
        recent = pmc[-7:]
        sec2.append('### 최근 7일 추이')
        sec2.append('| 날짜 | TSS | CTL | ATL | TSB |')
        sec2.append('|---|---:|---:|---:|---:|')
        for p in recent:
            sec2.append(f"| {p['date']} | {p['tss']:.0f} | {p['ctl']:.1f} | {p['atl']:.1f} | {p['tsb']:+.1f} |")

    # ───── 3. 누적 비교 (전 라이딩 대비) ─────
    rides = db.get('rides', [])
    prev_ride = None
    for r in reversed(rides):
        if r['date'] and r['date'] < date_str:
            prev_ride = r
            break

    sec3 = ['## 3. 전 라이딩 대비 변화', '']
    if prev_ride:
        sec3.append(f"비교 대상: **{prev_ride['name']}** ({prev_ride['date']})")
        sec3.append('')
        sec3.append('| 지표 | 이번 | 이전 | Δ |')
        sec3.append('|---|---:|---:|---:|')

        def cmp_row(label, cur, prev, fmt='{:.1f}'):
            if cur is None or prev is None:
                return f'| {label} | {cur or "?"} | {prev or "?"} | - |'
            diff = cur - prev
            sign = '+' if diff > 0 else ''
            return f'| {label} | {fmt.format(cur)} | {fmt.format(prev)} | {sign}{fmt.format(diff)} |'

        sec3.append(cmp_row('거리 (km)', s.get('distance_km'), prev_ride.get('distance_km')))
        sec3.append(cmp_row('상승 (m)', s.get('elev_gain_m'), prev_ride.get('elev_gain_m'), '{:.0f}'))
        sec3.append(cmp_row('TSS', tss, prev_ride.get('tss'), '{:.0f}'))
        sec3.append(cmp_row('IF', if_val, prev_ride.get('if_'), '{:.3f}'))
        sec3.append(cmp_row('NP (W)', s.get('np_w'), prev_ride.get('np_w'), '{:.0f}'))
        sec3.append(cmp_row('Avg HR', s.get('avg_hr'), prev_ride.get('avg_hr'), '{:.0f}'))
        sec3.append(cmp_row('케이던스', cadence, prev_ride.get('avg_cadence'), '{:.0f}'))
        sec3.append(cmp_row('디커플링 (%)', decoupling, prev_ride.get('decoupling_pct'), '{:.1f}'))
    else:
        sec3.append('첫 기록된 라이딩 — 비교 대상 없음.')

    # ───── 4. 코스 / Climb 베스트 ─────
    sec4 = ['## 4. Climb 베스트 라이브러리', '']
    cl_records = db.get('climb_records', {})
    today_climbs = []
    for c in climbs:
        length = round(c.get('distance_m', 0) / 1000, 1)
        grade = round(c.get('avg_grade_pct', 0), 1)
        key = f"{length}km @ {grade}%"
        rec = cl_records.get(key, {})
        best = rec.get('best_vam')
        n_attempts = rec.get('n_attempts', 1)
        cur_vam = c.get('vam_m_per_h', 0)
        is_pr = best and best.get('vam') == cur_vam and best.get('date') == date_str
        today_climbs.append({
            'index': c.get('index'),
            'key': key,
            'cur_vam': cur_vam,
            'best_vam': best.get('vam') if best else None,
            'best_date': best.get('date') if best else None,
            'n_attempts': n_attempts,
            'is_pr': is_pr,
        })
    sec4.append('| Climb | 코스 | 오늘 VAM | 베스트 | 베스트 일자 | 시도 횟수 |')
    sec4.append('|---|---|---:|---:|---|---:|')
    for tc in today_climbs:
        marker = ' 🔥 PR!' if tc['is_pr'] else ''
        sec4.append(f"| #{tc['index']} | {tc['key']} | {tc['cur_vam']:.0f}{marker} | "
                    f"{tc['best_vam']:.0f} | {tc['best_date']} | {tc['n_attempts']} |")

    # ───── 5. 영양 효율 ─────
    sec5 = ['## 5. 영양 프로토콜 효율 (누적)', '']
    nlog = db.get('nutrition_log', [])
    if nlog:
        sec5.append('| 일자 | 라이딩 | 영양 메모 | 디커플링 |')
        sec5.append('|---|---|---|---:|')
        for n in nlog[-5:]:
            note = n.get('nutrition_note') or '(미기록)'
            note = note[:40] + '…' if len(note) > 40 else note
            dec = f"{n['decoupling_pct']}%" if n.get('decoupling_pct') is not None else '?'
            sec5.append(f"| {n['date']} | {(n.get('name') or '')[:25]} | {note} | {dec} |")
        sec5.append('')
        sec5.append('💡 디커플링 8% 이하로 들어오는 영양 패턴이 검증된 패턴. 그 패턴을 D-day까지 유지·강화.')

    # ───── 6. A-race 준비도 ─────
    sec6 = ['## 6. 설악 그란폰도 208km 준비도', '']
    rd = db.get('seorak_readiness') or {}
    overall = rd.get('overall_pct', 0)
    sec6.append(f"### 종합: **{overall}%**\n")
    dims = rd.get('dimensions', {})
    if dims:
        sec6.append('| 차원 | 현재 최고 | 목표 (Seorak GF) | 준비도 |')
        sec6.append('|---|---:|---:|---:|')
        d_dist = dims.get('distance', {})
        d_elev = dims.get('elevation', {})
        d_dur = dims.get('duration', {})
        d_dec = dims.get('decoupling', {})
        sec6.append(f"| 거리 | {d_dist.get('current_max_km',0)} km | {d_dist.get('target_km',208)} km | {d_dist.get('pct',0)}% |")
        sec6.append(f"| 상승 | {d_elev.get('current_max_m',0)} m | {d_elev.get('target_m',3800)} m | {d_elev.get('pct',0)}% |")
        sec6.append(f"| 시간 | {d_dur.get('current_max_h',0)} h | {d_dur.get('target_h',9.5)} h | {d_dur.get('pct',0)}% |")
        if d_dec.get('recent_4w_avg') is not None:
            sec6.append(f"| 디커플링 | {d_dec.get('recent_4w_avg')}% | ≤ {d_dec.get('target_max',8)}% | {d_dec.get('pct',0)}% |")

    # 컷오프 페이스 검증
    sec6.append('')
    sec6.append('### 컷오프 페이스 검증')
    avg_kmh = s.get('avg_speed_kmh', 0) or 0
    if avg_kmh > 0:
        cutoff_1_pace = 82 / 4.0  # km/h
        if avg_kmh >= cutoff_1_pace:
            sec6.append(f"- 오늘 평균 {avg_kmh} km/h vs 1차 컷오프 {cutoff_1_pace:.1f} km/h 필요 → **✓ 통과**")
        else:
            shortfall = cutoff_1_pace - avg_kmh
            sec6.append(f"- 오늘 평균 {avg_kmh} km/h vs 1차 컷오프 {cutoff_1_pace:.1f} km/h 필요 → **⚠️ -{shortfall:.1f} km/h**")

    # ───── 7. D-day 권장 ─────
    today = datetime.fromisoformat(date_str) if date_str else datetime.now()
    days = (datetime(2026, 6, 20) - today).days

    sec7 = ['## 7. D-day 권장 일정', '']
    sec7.append(f"**오늘은 D-{days}**\n")

    if days > 35:
        phase = 'Build 1 — 베이스 강화'
        actions = [
            '- 100km+ Z2 라이딩 거리 누적',
            '- climb 반복으로 W/kg 향상',
            '- 영양 프로토콜 시간당 50g+ 검증',
            '- 디커플링 < 8% 사수',
        ]
    elif days > 20:
        phase = 'Build 2 — 거리·강도 동시 증량'
        actions = [
            '- 150~180km 1회 (장거리 적응)',
            '- HC climb 페이싱 검증 (Z3 IF 0.85~0.88)',
            '- 4시간+ 영양 프로토콜 통합 리허설',
        ]
    elif days > 11:
        phase = 'Peak — A-race 시뮬'
        actions = [
            '- **180~200km 1회** (208km 사전 리허설, D-15 권장)',
            '- Z4 인터벌로 임계 출력 강화',
            '- 보급 풀 시뮬 (50~60g/h, 카페인 젤 포함)',
            '- 회복 후 디커플링 < 6% 확인',
        ]
    elif days > 0:
        phase = 'Taper — 강도 감량 + 컨디션 안정'
        actions = [
            '- 강도 -50%, 거리 -60%',
            '- 짧은 Z3 인터벌로 신경계 활성',
            '- 혈당·수면·수분 강화',
            '- D-3부터 완전 휴식',
        ]
    else:
        phase = '🏁 Race day or Recovery'
        actions = ['- 레이스 후 회복 + 데이터 분석']

    sec7.append(f"**현재 단계: {phase}**\n")
    sec7.extend(actions)

    # 다음 라이딩 액션 (이번 라이딩 결과 기반)
    sec7.append('\n### 이번 라이딩 결과 기반 즉시 액션')
    next_actions = []
    if decoupling > 8:
        next_actions.append(f"1. **영양 보강**: 디커플링 {decoupling}%. 시간당 탄수 +20g 증량 (Maurten 또는 추가 젤)")
    if cadence < 85:
        next_actions.append(f"2. **케이던스 드릴**: 오늘 평균 {cadence}rpm → 다음 라이딩 85+ 의식적 유지")
    if tss > 280:
        next_actions.append(f"3. **회복**: TSS {tss} 고강도. 72h 회복 + 다음 자극은 Z2 베이스로")
    if not next_actions:
        next_actions.append('1. 현재 페이스·영양 패턴 유지하며 거리 5~10% 증량 시도')
    sec7.extend(next_actions)

    # ───── 합치기 ─────
    md = '\n'.join([
        f"# 📊 라이딩 브리핑 — {date_str} {course_name}",
        '',
        f"_athlete_db.json 기반 다각적 분석_",
        '',
        '\n'.join(sec1),
        '',
        '---',
        '',
        '\n'.join(sec2),
        '',
        '---',
        '',
        '\n'.join(sec3),
        '',
        '---',
        '',
        '\n'.join(sec4),
        '',
        '---',
        '',
        '\n'.join(sec5),
        '',
        '---',
        '',
        '\n'.join(sec6),
        '',
        '---',
        '',
        '\n'.join(sec7),
        '',
        '---',
        '',
        '_Auto-generated by `lib/build_athlete_briefing.py`. 데이터: athlete_db.json + 이번 라이딩 _analysis.json_',
    ])

    out_path = ride / f"analysis_briefing_{date_str}.md"
    out_path.write_text(md, encoding='utf-8')
    print(f"  ✓ {out_path}")
    return out_path


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_athlete_briefing.py <ride_dir>")
    briefing(sys.argv[1])


if __name__ == '__main__':
    main()
