#!/usr/bin/env python3
"""다각적 라이딩 브리핑 마크다운 생성.

athlete_db.json + 현재 라이딩 _analysis.json을 조합해 9개 관점에서 분석:
1. 자체 분석 — 이번 라이딩 핵심 지표
2. 강도 프로파일 — 파워·HR 존, MMP, 클라임 카테고리
3. 페이싱·영양 — 전·후반 split, 인터벌, 탄수·수분 권장
4. 시계열 추이 — CTL/ATL/TSB 4주
5. 누적 비교 — 전 라이딩 대비 Δ
6. 코스 베스트 — climb 라이브러리 + 진보율
7. 영양 효율 — 보급 패턴별 디커플링 결과
8. A-race 준비도 — Seorak GF 5차원 게이지
9. D-day 권장 — Build/Peak/Taper 단계별 액션

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

try:
    from seorak import SEORAK
    SEORAK_CUTOFF_1_KM = SEORAK['cutoff_1_km']
    SEORAK_CUTOFF_2_KM = SEORAK['cutoff_2_km']
except Exception:
    SEORAK_CUTOFF_1_KM = 82
    SEORAK_CUTOFF_2_KM = 167


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

    # ───── 2. 강도 프로파일 (NEW) ─────
    sec1b = ['## 2. 강도 프로파일', '']
    pz = A.get('power_zones')
    hz = A.get('hr_zones')
    mmp = A.get('mean_max_power') or {}

    if pz:
        sec1b.append('### 파워 존 (Coggan, %FTP)')
        sec1b.append('| 존 | 시간 | 비율 | |')
        sec1b.append('|---|---:|---:|---|')
        labels_p = {
            'Z1_recovery': 'Z1 Recovery (<55%)',
            'Z2_endurance': 'Z2 Endurance (55–75%)',
            'Z3_tempo': 'Z3 Tempo (75–90%)',
            'Z4_threshold': 'Z4 Threshold (90–105%)',
            'Z5_vo2max': 'Z5 VO₂max (105–120%)',
            'Z6_anaerobic': 'Z6 Anaerobic (120–150%)',
            'Z7_neuromuscular': 'Z7 NM (>150%)',
        }
        for z, v in pz.items():
            mins = v['sec'] // 60
            bar = '█' * int(v['pct'] / 2)
            sec1b.append(f"| {labels_p.get(z, z)} | {mins}분 | {v['pct']}% | {bar} |")
        sec1b.append('')

    if hz:
        sec1b.append('### HR 존 (%LTHR)')
        sec1b.append('| 존 | 시간 | 비율 | |')
        sec1b.append('|---|---:|---:|---|')
        labels_h = {
            'Z1_recovery': 'Z1 Recovery (<81%)',
            'Z2_endurance': 'Z2 Endurance (81–89%)',
            'Z3_tempo': 'Z3 Tempo (89–94%)',
            'Z4_threshold': 'Z4 Threshold (94–100%)',
            'Z5_vo2max': 'Z5 VO₂max (≥100%)',
        }
        for z, v in hz.items():
            mins = v['sec'] // 60
            bar = '█' * int(v['pct'] / 2)
            sec1b.append(f"| {labels_h.get(z, z)} | {mins}분 | {v['pct']}% | {bar} |")
        sec1b.append('')

    if mmp:
        sec1b.append('### Mean-max Power (오늘의 베스트)')
        sec1b.append('| 윈도우 | 파워 | %FTP |')
        sec1b.append('|---|---:|---:|')
        ftp = R.get('ftp_w', 180)
        for d in ('5s', '30s', '60s', '300s', '600s', '1200s', '3600s'):
            w = mmp.get(d)
            if w is None:
                continue
            label = {'5s':'5초','30s':'30초','60s':'1분','300s':'5분','600s':'10분','1200s':'20분','3600s':'1시간'}[d]
            sec1b.append(f"| {label} | {w:.0f}W | {w/ftp*100:.0f}% |")
        sec1b.append('')

    # 클라임 카테고리 분포
    if climbs:
        from collections import Counter
        cats = Counter(c.get('category', 'NC') for c in climbs)
        cat_summary = ' · '.join(f"{cat} ×{n}" for cat, n in sorted(cats.items()))
        sec1b.append(f"### 클라임 카테고리: {cat_summary}")
        sec1b.append('')
        sec1b.append('| # | 거리 | 평균grade | VAM | 분류 |')
        sec1b.append('|---:|---:|---:|---:|---|')
        for c in climbs:
            sec1b.append(f"| {c.get('index')} | {c.get('distance_m',0)/1000:.1f}km | {c.get('avg_grade_pct',0):.1f}% | {c.get('vam_m_per_h',0):.0f} | {c.get('category','-')} |")

    # ───── 3. 페이싱·영양 (NEW) ─────
    sec1c = ['## 3. 페이싱·영양', '']
    half = A.get('half_split')
    if half:
        h1, h2 = half['first_half'], half['second_half']
        verdict_kr = {
            'positive_split': '✓ Positive split — 후반 더 강함',
            'even': '✓ Even — 균형 페이스',
            'negative_split': '⚠️ Negative split — 후반 페이스 떨어짐',
            'severe_fade': '🔴 Severe fade — 영양·강도 재설계 필요',
        }.get(half.get('verdict'), '?')
        sec1c.append(f"### 전·후반 분할 — {verdict_kr}")
        sec1c.append('| 구간 | NP | IF | VI | HR | 평속 |')
        sec1c.append('|---|---:|---:|---:|---:|---:|')
        sec1c.append(f"| 전반 | {h1['np_w']:.0f}W | {h1['if_']:.2f} | {h1['vi']:.2f} | {h1['avg_hr']:.0f} | {h1['avg_speed_kmh']:.1f} |")
        sec1c.append(f"| 후반 | {h2['np_w']:.0f}W | {h2['if_']:.2f} | {h2['vi']:.2f} | {h2['avg_hr']:.0f} | {h2['avg_speed_kmh']:.1f} |")
        sec1c.append(f"| **NP 변화** | **{half['np_change_pct']:+.1f}%** |")
        sec1c.append('')

    intervals = A.get('intervals') or []
    if intervals:
        sec1c.append(f"### Z4+ 인터벌 자동 검출 ({len(intervals)}개)")
        sec1c.append('| 시점 | 거리 | 길이 | 평균 | IF |')
        sec1c.append('|---|---:|---:|---:|---:|')
        for it in intervals:
            t = it.get('ride_elapsed_start_s', 0) // 60
            sec1c.append(f"| {t//60}h{t%60:02d}m | {it.get('start_km','?')}km | {it.get('duration_s')}s | {it.get('avg_power_w'):.0f}W | {it.get('if_'):.2f} |")
        sec1c.append('')

    fuel = A.get('fueling') or {}
    if fuel:
        sec1c.append('### 영양 권장 (이번 강도 기준)')
        sec1c.append(f"- **탄수**: {fuel.get('carb_per_h_g','?')}g/h × {fmt_h(s.get('moving_h')) or '?'} ≈ **{fuel.get('total_carb_g','?')}g**")
        sec1c.append(f"- **수분**: {fuel.get('fluid_per_h_ml','?')}ml/h ≈ **{fuel.get('total_fluid_ml','?')}ml**")
        sec1c.append(f"- **소비 칼로리(추정)**: {fuel.get('kcal_est','?')} kcal")

    # ───── 4. 장거리 endurance (시간 구간별) ─────
    sec1d = ['## 4. 장거리 Endurance — 시간 구간별 페이싱', '']
    end = A.get('endurance') or {}
    bands = end.get('bands') or []
    if bands:
        sec1d.append('| 구간 | NP | IF | HR (%LTHR) | 케이던스 | 평속 |')
        sec1d.append('|---|---:|---:|---:|---:|---:|')
        for b in bands:
            sec1d.append(f"| {b['band']} | {b['np_w']:.0f}W | {b['if_']:.2f} | "
                         f"{b['avg_hr']:.0f} ({b['hr_pct_lthr']:.0f}%) | "
                         f"{b['avg_cadence']:.0f} | {b['avg_speed_kmh']:.1f} km/h |")
        sec1d.append('')
    dur = end.get('durability')
    if dur:
        emoji = '✓ 강한' if dur['durability_pct'] >= 90 else '🟠 보통' if dur['durability_pct'] >= 80 else '⚠️ 약한'
        sec1d.append(f"### Power Durability — {emoji} 후반 출력 유지력")
        sec1d.append(f"- **첫 1시간 5분 베스트**: {dur['first_hour_5min_best_w']:.0f}W")
        sec1d.append(f"- **마지막 1/3 시간 5분 베스트**: {dur['last_third_5min_best_w']:.0f}W")
        sec1d.append(f"- **유지율**: {dur['durability_pct']:.0f}% (90%+ 강함, 80~90% 보통, <80% 약함)")
    sec1d.append('')
    sec1d.append('💡 Seorak 10시간 라이딩 = 4h 시점 IF 0.65~0.70 유지가 기준. 후반 IF 0.75 넘으면 페이드 시작.')

    # ───── 5. 시계열 추이 (CTL/ATL/TSB + ACWR) ─────
    pmc = db.get('pmc', [])
    today_pmc = next((p for p in reversed(pmc) if p['date'] == date_str), pmc[-1] if pmc else None)

    sec2 = ['## 5. Performance Management Chart (CTL/ATL/TSB + ACWR)', '']
    if today_pmc:
        ctl = today_pmc['ctl']
        atl = today_pmc['atl']
        tsb = today_pmc['tsb']
        acwr = today_pmc.get('acwr', 0)
        acwr_state = today_pmc.get('acwr_state', 'no_data')
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
        # ACWR 해석
        acwr_emoji = {'detrain':'🔵','safe':'🟢','caution':'🟡','injury_risk':'🔴','no_data':'-'}.get(acwr_state, '?')
        acwr_kr = {
            'detrain': 'Detrain — 강도 부족 (적응 손실 위험)',
            'safe': 'Safe Sweet Spot — 적정 부하',
            'caution': '⚠️ Caution — 피로 누적 단계',
            'injury_risk': '🔴 부상 위험 (1.5+ Acute Spike)',
            'no_data': '데이터 부족',
        }[acwr_state]

        sec2.extend([
            f"- **CTL (피트니스, 42d)**: {ctl}",
            f"- **ATL (피로, 7d)**: {atl}",
            f"- **TSB (밸런스)**: {tsb} — {tsb_state}",
            f"- **ACWR (Acute:Chronic)**: {acwr} {acwr_emoji} — {acwr_kr}",
            '',
        ])

    # 최근 7일 추이
    if len(pmc) >= 7:
        recent = pmc[-7:]
        sec2.append('### 최근 7일 추이')
        sec2.append('| 날짜 | TSS | CTL | ATL | TSB | ACWR |')
        sec2.append('|---|---:|---:|---:|---:|---:|')
        for p in recent:
            sec2.append(f"| {p['date']} | {p['tss']:.0f} | {p['ctl']:.1f} | {p['atl']:.1f} | {p['tsb']:+.1f} | {p.get('acwr',0):.2f} |")

    # ───── 3. 누적 비교 (전 라이딩 대비) ─────
    rides = db.get('rides', [])
    prev_ride = None
    for r in reversed(rides):
        if r['date'] and r['date'] < date_str:
            prev_ride = r
            break

    sec3 = ['## 6. 전 라이딩 대비 변화', '']
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
    sec4 = ['## 7. Climb 베스트 라이브러리', '']
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
    sec5 = ['## 8. 영양 프로토콜 효율 (누적)', '']
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
    sec6 = ['## 9. 설악 그란폰도 208km 준비도', '']
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

    # 컷오프 페이스 검증 + 오늘 라이딩 기준 시뮬 (seorak.seorak_simulation 활용)
    sec6.append('')
    seo = A.get('seorak_simulation')
    if seo:
        sec6.append('### 오늘 페이스로 Seorak 시뮬')
        sec6.append('')
        c1_mark = '✓ 통과' if seo['cutoff_1_pass'] else '⚠️ 미달'
        c2_mark = '✓ 통과' if seo['cutoff_2_pass'] else '⚠️ 미달'
        sec6.append(f"- **같은 페이스 유지 시 완주**: {seo['extrap_finish_h']}h "
                    f"(목표 {seo['target_finish_h']}h)")
        sec6.append(f"- **디커플링 보정 후 예상**: {seo['adjusted_finish_h']}h "
                    f"(오늘 디커플링 {seo['today_decoupling_pct']}% 가정 누적)")
        sec6.append(f"- **컷오프 1 (km {SEORAK_CUTOFF_1_KM}/{seo['cutoff_1_pace_kmh']:.1f}km/h)**: "
                    f"{c1_mark} (오늘 {seo['today_avg_kmh']:.1f}km/h)")
        sec6.append(f"- **컷오프 2 (km {SEORAK_CUTOFF_2_KM}/{seo['cutoff_2_pace_kmh']:.1f}km/h)**: "
                    f"{c2_mark}")
        sec6.append(f"- **10시간 완주 권장 IF**: {seo['target_if_for_10h']:.2f} "
                    f"(오늘 {seo['today_if']:.3f})")
        sec6.append(f"- **오늘 IF로 지속 가능 시간**: {seo['today_max_duration_h']}h (Coggan 모델)")
        sec6.append('')
        sec6.append(f"### 종합 가능성 (오늘 데이터 기준): **{seo['feasibility_pct']}%**")
        sec6.append('')
        ds = seo.get('dimension_scores', {})
        sec6.append('| 차원 | 점수 |')
        sec6.append('|---|---:|')
        sec6.append(f"| 속도 | {ds.get('speed', 0)}% |")
        sec6.append(f"| 디커플링 (장거리 페이드 저항) | {ds.get('decoupling', 0)}% |")
        sec6.append(f"| 지속시간 (IF별 한계) | {ds.get('duration', 0)}% |")
        bg = seo.get('biggest_gap', {})
        if bg:
            sec6.append('')
            sec6.append(f"⚠️ **가장 큰 갭**: {bg['dim']} (현재 {bg['current']}{bg['unit']} → 목표 {bg['target']}{bg['unit']})")

    # ───── 10. FTP / W/kg 진보 ─────
    sec_ftp = ['## 10. FTP / W/kg 진보 추적', '']
    ft = db.get('ftp_trend') or {}
    cur_est = ft.get('current_estimated_ftp_w')
    cur_wpk = ft.get('current_estimated_w_per_kg')
    manual = ft.get('manual_ftp_w')
    delta = ft.get('manual_vs_estimated_delta')
    if cur_est:
        sign = '+' if (delta or 0) > 0 else ''
        sec_ftp.append(f"- **현재 추정 FTP** (지난 30일 P20 best × 0.95): **{cur_est}W** ({cur_wpk} W/kg)")
        sec_ftp.append(f"- **수동 입력 FTP**: {manual}W (Δ {sign}{delta}W)")
        if delta is not None and delta >= 5:
            sec_ftp.append(f"- 💡 추정 FTP가 수동 입력보다 {sign}{delta}W 높음 → **수동 FTP 갱신 검토**")
        sec_ftp.append('')

    rolling = ft.get('rolling_30d') or []
    if len(rolling) >= 2:
        sec_ftp.append('### 추정 FTP 추이 (최근 8 라이딩)')
        sec_ftp.append('| 날짜 | rolling P20 | 추정 FTP | W/kg |')
        sec_ftp.append('|---|---:|---:|---:|')
        for r in rolling[-8:]:
            sec_ftp.append(f"| {r['date']} | {r['rolling_p20_w']:.0f}W | {r['rolling_ftp_w']:.0f}W | {r['w_per_kg']:.2f} |")

    # TDF 10년 trajectory (분석에 직접 반영)
    sec_ftp.append('')
    sec_ftp.append('### TDF 10년 trajectory — 최종 기준')
    tdf = A.get('tdf_trajectory') or {}
    if tdf and tdf.get('current_wpk'):
        # 진척 바 (텍스트)
        prog = tdf.get('progress_pct', 0)
        bar_full = 30
        filled = int(prog / 100 * bar_full)
        bar = '█' * filled + '░' * (bar_full - filled)
        sec_ftp.append(f"`{bar}` **{prog}%** (2.0 → {tdf['target_wpk']} W/kg)")
        sec_ftp.append('')
        sec_ftp.append(f"- **현재**: {tdf['current_wpk']:.2f} W/kg · **목표**: {tdf['target_wpk']} W/kg "
                       f"({tdf.get('target_label','')}, {tdf['target_year']}년)")
        sec_ftp.append(f"- **남은 시간**: {tdf['years_remaining']:.1f}년 · "
                       f"**필요 증가율**: +{tdf['annual_increase_needed']:.2f} W/kg/yr")
        ann_act = tdf.get('annual_increase_actual')
        if ann_act is not None:
            sec_ftp.append(f"- **현 추세**: {ann_act:+.2f} W/kg/yr · 상태: **{tdf.get('status','')}**")
        else:
            sec_ftp.append(f"- 상태: {tdf.get('status','')}")
        nm = tdf.get('next_milestone')
        if nm:
            eta = nm.get('eta_years')
            eta_s = f" · 추세 ETA: **{eta}년**" if eta else ' · 추세 ETA: 추세 누적 중'
            sec_ftp.append(f"- **다음 마일스톤**: {nm['label']} ({nm['wpk']} W/kg, Δ {nm['wpk']-tdf['current_wpk']:+.2f}){eta_s}")
        if tdf.get('ftp_target_w'):
            sec_ftp.append(f"- **목표 FTP** (체중 {A.get('rider',{}).get('weight_kg','?')}kg): "
                           f"**{tdf['ftp_target_w']}W**")
        sec_ftp.append(f"- 오늘 라이딩 기여: TSS {tdf.get('today_tss',0)} · "
                       f"CTL +{tdf.get('today_ctl_contrib_per_day',0)}/day")
    sec_ftp.append('')

    sec_ftp.append('### W/kg 마일스톤 누적')
    if cur_wpk:
        from seorak import TDF_MILESTONES as _MS
        for w, label in _MS:
            mark = '✓' if cur_wpk >= w else '○'
            gap = '' if cur_wpk >= w else f' (Δ {w - cur_wpk:.2f})'
            sec_ftp.append(f"- {mark} **{w} W/kg** — {label}{gap}")

    # ───── 11. D-day 권장 ─────
    today = datetime.fromisoformat(date_str) if date_str else datetime.now()
    days = (datetime(2026, 6, 20) - today).days

    sec7 = ['## 11. D-day 권장 일정', '']
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
        '\n'.join(sec1b),
        '',
        '---',
        '',
        '\n'.join(sec1c),
        '',
        '---',
        '',
        '\n'.join(sec1d),
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
        '\n'.join(sec_ftp),
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
