"""_analysis.json + _videos.json → coaching.srt.

라이딩 전반 코칭 흐름:
  1. 인트로 — 오늘의 라이딩 개요
  2. 워밍업 — 출발 페이싱
  3. 클라임별 진입·정상 회복
  4. 영양 리마인더 — 25~30분 간격
  5. 중간 지점 — 전·후반 페이싱 예고
  6. 후반 드리프트 경고 — 디커플링 감지 시점
  7. 인터벌 하이라이트 — Z4+ 1분 이상
  8. 종합 평가 + 다음 액션

큐 우선순위 (낮을수록 보존): 0=intro/outro, 1=climb, 2=interval, 3=midpoint/drift, 4=fueling/warmup
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta


def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def fmt_srt(s):
    if s < 0:
        s = 0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    ss = int(s % 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"


# ───────── 큐 생성기 ─────────

def cue_intro(summ, rider):
    return [(5, 9, [
        f"오늘의 라이딩: {summ['distance_km']} km / +{summ['elev_gain_m']:,}m ({summ['elev_per_km']} m/km)",
        f"체중 {rider['weight_kg']}kg · FTP {rider['ftp_w']}W ({rider['w_per_kg']} W/kg) · 그란폰도 시뮬레이션",
    ], 0)]


def cue_warmup(climbs, ride_to_video):
    """첫 climb 진입 ~5분 전 (영상 시간이 충분하면) 또는 출발 후 8분 시점에 워밍업 메시지."""
    if not climbs:
        return []
    first = climbs[0]
    target_ride_s = max(60, first['ride_elapsed_start_s'] - 240)
    vt = ride_to_video(target_ride_s)
    if vt is None:
        return []
    return [(vt, 7, [
        "[워밍업] 출발 후 20~30분은 Z2 — HR 안정시키며 진입",
        "심박 너무 빨리 오르면 첫 climb에서 무너짐",
    ], 4)]


def cue_climbs(analysis, ride_to_video):
    """클라임별: 진입 + 정상 회복 큐."""
    out = []
    rider = analysis['rider']
    ftp = rider['ftp_w']
    best = analysis.get('best_climb')
    fade = analysis.get('fade_climb')

    for c in analysis.get('climbs', []):
        idx = c['index']
        is_best = best and best['index'] == idx
        is_fade = fade and fade['index'] == idx
        ifp = c['avg_power_w'] / ftp if ftp else 0
        cat = c.get('category') or '-'

        # 진입
        vt = ride_to_video(c['ride_elapsed_start_s'])
        if vt is None:
            continue

        if is_best:
            lines = [
                f"[Climb #{idx} · {cat}] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km — 베스트 페이싱 후보",
                f"VAM {c['vam_m_per_h']:.0f} m/h, 평균 {c['avg_power_w']:.0f}W (IF {ifp:.2f})",
                "이 페이스를 몸이 기억하도록 집중",
            ]
        elif is_fade:
            vam_drop = (1 - c['vam_m_per_h'] / best['vam_m_per_h']) * 100 if best else 0
            lines = [
                f"[Climb #{idx} · {cat}] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km — 후반 시험",
                f"VAM {c['vam_m_per_h']:.0f} (베스트 #{best['index']} 대비 -{vam_drop:.0f}%)" if best else f"VAM {c['vam_m_per_h']:.0f}",
                "후반 누적 피로 — 페이싱 절제 필요",
            ]
        else:
            lines = [
                f"[Climb #{idx} · {cat}] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km, +{c['elev_gain_m']:.0f}m",
                f"평균 {c['avg_power_w']:.0f}W (IF {ifp:.2f}) · HR {c['avg_hr']:.0f} · VAM {c['vam_m_per_h']:.0f}",
            ]
        out.append((vt, 8, lines, 1))

        # 정상 직후 (climb 끝 +10초)
        top_ride_s = c['ride_elapsed_start_s'] + c['duration_s'] + 10
        vt_top = ride_to_video(top_ride_s)
        if vt_top is None:
            continue
        cad = c.get('avg_cadence', 0) or 0
        cad_msg = f"케이던스 {cad:.0f} — " + ('회전 양호' if cad >= 75 else '저rpm, 무릎 부담')
        out.append((vt_top, 6, [
            f"[Climb #{idx} 정상] HR 회복 속도 = 페이싱 적정 지표",
            cad_msg,
        ], 2))

    return out


def cue_intervals(intervals, climbs, ride_to_video, ftp):
    """Z4+ 인터벌 중 climb과 겹치지 않는 것만 강조 (climb 큐와 중복 방지)."""
    if not intervals:
        return []
    climb_ranges = [(c['ride_elapsed_start_s'], c['ride_elapsed_start_s'] + c['duration_s']) for c in climbs]

    def in_climb(t):
        for s, e in climb_ranges:
            if s - 30 <= t <= e + 30:
                return True
        return False

    out = []
    for it in intervals:
        if in_climb(it['ride_elapsed_start_s']):
            continue
        vt = ride_to_video(it['ride_elapsed_start_s'] + 10)  # 인터벌 시작 +10초 시점에 표시
        if vt is None:
            continue
        out.append((vt, 6, [
            f"[Z4+ 어택] {it['duration_s']}초 · 평균 {it['avg_power_w']:.0f}W (IF {it['if_']:.2f})",
            "페달 에너지 큰 구간 — 회복 후 영양 보급 잊지 말기",
        ], 2))
    return out


def cue_fueling_reminders(total_video_s, ride_to_video, analysis, ride_duration_s):
    """30분 간격 영양 리마인더. climb 큐와 겹치지 않게 자동 회피."""
    fueling = analysis.get('fueling') or {}
    carb_per_h = fueling.get('carb_per_h_g', 60)
    out = []
    # 첫 리마인더 = 25분 시점, 그 후 30분 간격
    t = 25 * 60
    n = 1
    while t < ride_duration_s - 600:  # 마지막 10분 전까지
        vt = ride_to_video(t)
        if vt is not None:
            tip_pool = [
                f"[보급 #{n}] 시간당 탄수 {carb_per_h}g — 젤·바·드링크 분할",
                "수분 200~250ml 한 모금 — 갈증 느끼면 늦음",
                "케이던스 80+ 유지 — 근피로 가속 방지",
                "어깨 풀고 그립 위치 바꿔 — 상체 긴장 누적 방지",
            ]
            out.append((vt, 6, [tip_pool[n % len(tip_pool)], "(영양·자세 리마인더)"], 4))
            n += 1
        t += 30 * 60
    return out


def cue_midpoint(analysis, ride_to_video, ride_duration_s):
    """라이딩 절반 시점에 전·후반 페이싱 예고."""
    halves = analysis.get('half_split')
    if not halves or ride_duration_s < 1200:
        return []
    vt = ride_to_video(ride_duration_s // 2)
    if vt is None:
        return []
    h1 = halves['first_half']
    return [(vt, 7, [
        f"[중간점] 전반 NP {h1['np_w']:.0f}W · IF {h1['if_']:.2f} · HR {h1['avg_hr']:.0f}",
        "후반 IF 떨어지지 않게 — 영양·페이스 점검",
    ], 3)]


def cue_drift_warning(analysis, ride_to_video, ride_duration_s):
    """디커플링이 8% 이상이면 후반 60% 시점에 드리프트 경고."""
    decoupling = analysis.get('summary', {}).get('decoupling_pct', 0) or 0
    if decoupling < 8 or ride_duration_s < 1800:
        return []
    target = int(ride_duration_s * 0.6)
    vt = ride_to_video(target)
    if vt is None:
        return []
    return [(vt, 7, [
        f"[드리프트 경고] 디커플링 {decoupling}% — 같은 파워 유지에 HR 더 듦",
        "탄수 +20g 추가 보급 · 케이던스 5rpm 올려 근부담 분산",
    ], 3)]


def cue_mmp_highlight(analysis, ride_to_video):
    """5분 / 20분 mean-max가 라이더 FTP 대비 의미있게 높으면 하이라이트.

    실제 시점 검출은 별도 시계열 계산이 필요해 건너뛰고, 종합 평가 직전 1회 노출.
    """
    mmp = analysis.get('mean_max_power') or {}
    ftp = analysis.get('rider', {}).get('ftp_w', 0)
    if not mmp or not ftp:
        return []
    p20 = mmp.get('1200s', 0) or 0
    p5 = mmp.get('300s', 0) or 0
    if p20 == 0:
        return []
    # 출력은 마지막 종합 직전에 cue_outro에서 같이 처리. 여기선 빈 리스트.
    return []


def cue_outro(analysis, total_video_s):
    """종합 평가 + Mean-max 하이라이트 + Seorak 시뮬 + 다음 액션."""
    summ = analysis.get('summary', {})
    mmp = analysis.get('mean_max_power') or {}
    halves = analysis.get('half_split') or {}
    fueling = analysis.get('fueling') or {}
    seo = analysis.get('seorak_simulation') or {}
    decoupling = summ.get('decoupling_pct', 0) or 0
    cadence = summ.get('avg_cadence', 0) or 0
    tss = summ.get('tss', 0) or 0

    cues = []

    # outro cue들: narration TTS mp3가 25~30초씩이라 시각 간 갭 50초로 안전 마진.
    # 분산: -360(MMP) → -300(Seorak) → -240(TDF) → -180(종합) → -120(액션)
    # ※ total_video_s는 GoPro 챕터 누적(trim 전)일 수 있어 trim 후 영상에서도
    #    안전히 들어가도록 영상 끝 기준 충분히 앞당김 (마지막 cue 끝 = -90s).
    # 1) Mean-max 하이라이트 (-360, 30s)
    p5 = mmp.get('300s', 0) or 0
    p20 = mmp.get('1200s', 0) or 0
    if p20 > 0:
        cues.append((max(0, total_video_s - 360), 30, [
            f"[오늘의 베스트 출력]",
            f"5분 {p5:.0f}W · 20분 {p20:.0f}W · 1분 {mmp.get('60s', 0):.0f}W",
        ], 0))

    # 2) Seorak 시뮬 (-300, 30s)
    if seo:
        c1 = '✓' if seo.get('cutoff_1_pass') else '✗'
        c2 = '✓' if seo.get('cutoff_2_pass') else '✗'
        cues.append((max(0, total_video_s - 300), 30, [
            f"[Seorak GF 시뮬 — D-day {seo.get('race_date','?')}]",
            f"오늘 페이스로 완주: {seo.get('adjusted_finish_h','?')}h (목표 10h)",
            f"컷오프1 {c1} · 컷오프2 {c2} · 종합 가능성 {seo.get('feasibility_pct','?')}%",
        ], 0))

    # 2b) TDF 10년 trajectory (-120, 35s)
    tdf = analysis.get('tdf_trajectory') or {}
    if tdf and tdf.get('current_wpk'):
        nm = tdf.get('next_milestone') or {}
        eta = nm.get('eta_years')
        eta_str = f"ETA {eta}y" if eta else 'ETA 추세 누적 중'
        cues.append((max(0, total_video_s - 240), 35, [
            f"[TDF 10년 trajectory · 진척 {tdf.get('progress_pct',0)}%]",
            f"현재 {tdf.get('current_wpk',0)} W/kg → 목표 {tdf.get('target_wpk',4.5)} W/kg ({tdf.get('target_year',2036)})",
            f"필요 +{tdf.get('annual_increase_needed',0):.2f}/yr · {tdf.get('status','')[:34]}",
            f"다음: {nm.get('label','')} ({nm.get('wpk','?')} W/kg, {eta_str})",
        ], 0))

    # 3) 페이싱 평가 (-27, 10s)
    verdict_msg = {
        'positive_split': '후반에 더 강함 — 영양·전략 성공',
        'even': '균형 페이스 — 안정 라이딩',
        'negative_split': '후반 페이스 떨어짐 — 영양·페이싱 점검',
        'severe_fade': '후반 급격한 페이드 — 영양·강도 재설계 필요',
    }.get(halves.get('verdict'), '')
    cues.append((max(0, total_video_s - 180), 30, [
        "[오늘의 종합 평가]",
        f"TSS {tss} · IF {summ.get('if_', 0)} · VI {summ.get('vi', 0)} · 디커플링 {decoupling}%",
        verdict_msg or f"회복 권장 {72 if tss > 250 else 48}h",
    ], 0))

    # 3) 다음 액션 (-40, 30s)
    actions = []
    if decoupling > 10:
        actions.append(f"1. 영양 +20g/h (현재 권장 {fueling.get('carb_per_h_g', 60)}g/h → 시도 80g/h)")
    elif decoupling > 8:
        actions.append(f"1. 영양 패턴 점검 — 시간당 {fueling.get('carb_per_h_g', 60)}g 분할 보급 확실히")
    if cadence < 80:
        actions.append(f"2. 케이던스 {cadence}→85+ 의식 (다음 라이딩)")
    if not actions:
        actions = [
            "1. 페이스·영양 패턴 유지하며 거리 5~10% 증량",
            "2. 다음 라이딩 전 충분한 회복",
        ]
    cues.append((max(0, total_video_s - 120), 30, [
        "[다음 라이딩 액션]",
    ] + actions[:2], 0))

    return cues


# ───────── 메인 ─────────

def main(ride_dir):
    analysis = load(Path(ride_dir) / '_analysis.json')
    videos = load(Path(ride_dir) / '_videos.json')

    ride_start = datetime.fromisoformat(analysis['ride_start_utc'])
    rider = analysis['rider']
    summ = analysis['summary']

    rv = videos['ride_videos_chronological']
    vid_starts, cum = [], 0
    for v in rv:
        st = datetime.fromisoformat(v['start_utc'])
        vid_starts.append({
            'utc_start': st,
            'utc_end': st + timedelta(seconds=v['duration_s']),
            'cum_start_s': cum,
            'cum_end_s': cum + v['duration_s'],
        })
        cum += v['duration_s']
    total_vs = cum

    # 라이딩 총 길이 (FIT 기준)
    ride_duration_s = 0
    try:
        h, m, s = (summ.get('elapsed_h') or '0:0:0').split(':')
        ride_duration_s = int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        ride_duration_s = total_vs

    def ride_to_video(rs):
        target = ride_start + timedelta(seconds=rs)
        for v in vid_starts:
            if v['utc_start'] <= target <= v['utc_end']:
                return v['cum_start_s'] + (target - v['utc_start']).total_seconds()
        return None

    climbs = analysis.get('climbs', []) or []
    intervals = analysis.get('intervals', []) or []

    # 모든 큐 모으기
    cues = []
    cues += cue_intro(summ, rider)
    cues += cue_warmup(climbs, ride_to_video)
    cues += cue_climbs(analysis, ride_to_video)
    cues += cue_intervals(intervals, climbs, ride_to_video, rider['ftp_w'])
    cues += cue_fueling_reminders(total_vs, ride_to_video, analysis, ride_duration_s)
    cues += cue_midpoint(analysis, ride_to_video, ride_duration_s)
    cues += cue_drift_warning(analysis, ride_to_video, ride_duration_s)
    cues += cue_outro(analysis, total_vs)

    # 큐: (vt, dur, lines, prio)
    cues.sort(key=lambda c: (c[0], c[3]))

    # 충돌 해결: 같은 시점 ±5초 이내에 priority 낮은 큐가 있으면 우선, 더 높은 prio 큐는 컷
    resolved = []
    for c in cues:
        vt, dur, lines, prio = c
        # 직전 큐와 충돌?
        if resolved:
            prev_vt, prev_dur, prev_lines, prev_prio = resolved[-1]
            prev_end = prev_vt + prev_dur
            if vt < prev_end + 0.5:
                # 우선순위 낮은 큐 (prio 작은) 보존
                if prio < prev_prio:
                    resolved[-1] = c
                    continue
                else:
                    # 뒤로 미루기
                    vt = prev_end + 0.5
                    if vt + dur > total_vs:
                        continue  # 영상 끝 넘으면 제외
        resolved.append((vt, dur, lines, prio))

    # SRT 출력
    out_lines = []
    for i, (vt, dur, lines, _prio) in enumerate(resolved, 1):
        out_lines.extend([str(i), f"{fmt_srt(vt)} --> {fmt_srt(vt + dur)}"] + lines + [""])

    srt_path = Path(ride_dir) / 'coaching.srt'
    srt_path.write_text("\n".join(out_lines), encoding='utf-8')
    print(f"  ✓ {len(resolved)}개 큐 → {srt_path}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("사용법: python3 build_srt.py <ride_dir>")
    main(sys.argv[1])
