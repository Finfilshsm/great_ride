#!/usr/bin/env python3
"""FIT 파일 → _analysis.json 자동 생성.

스키마 (5/2 헐몰헐 _analysis.json + build_srt.py 의존성 합산):
{
  fit_path, ride_start_utc,
  rider: {ftp_w, weight_kg, w_per_kg, lthr},
  summary: {distance_km, elev_gain_m, elev_per_km, elapsed_h, moving_h,
            avg_speed_kmh, avg_power_w, np_w, vi, if_, tss,
            avg_hr, max_hr, avg_cadence, max_power_w, decoupling_pct},
  climbs: [...],
  best_climb: {...},
  fade_climb: {...}
}

가민 session 메시지 우선(공식 TSS/IF/NP), 없는 항목만 records에서 계산.
"""
import sys
import json
from pathlib import Path
from datetime import timedelta, timezone
from fitparse import FitFile

# 라이더 기본값 (사용자 프로필)
DEFAULT_RIDER = {'ftp_w': 180, 'weight_kg': 73, 'lthr': 168}


def fmt_h(s):
    if s is None:
        return None
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h}:{m:02d}:{sec:02d}"


def normalized_power(power_series):
    if not power_series:
        return 0.0
    rolled = []
    for i in range(len(power_series)):
        s = max(0, i - 29)
        seg = [p for p in power_series[s:i+1] if p is not None]
        if seg:
            rolled.append(sum(seg) / len(seg))
    if not rolled:
        return 0.0
    return (sum(p**4 for p in rolled) / len(rolled)) ** 0.25


def decoupling_pct(records):
    """Joe Friel: 후반 NP/HR ratio가 전반 대비 얼마나 떨어졌는지 (%)."""
    valid = [r for r in records
             if r.get('power') is not None
             and r.get('heart_rate') is not None
             and r.get('heart_rate') > 0]
    if len(valid) < 60:
        return None
    half = len(valid) // 2
    h1, h2 = valid[:half], valid[half:]
    np1 = normalized_power([r['power'] for r in h1])
    np2 = normalized_power([r['power'] for r in h2])
    hr1 = sum(r['heart_rate'] for r in h1) / len(h1)
    hr2 = sum(r['heart_rate'] for r in h2) / len(h2)
    if hr1 == 0 or hr2 == 0:
        return None
    r1 = np1 / hr1
    r2 = np2 / hr2
    return round((r1 - r2) / r1 * 100, 2)


def detect_climbs(records, win_m=500, climb_grade=2.5, min_gain=80, min_length=600, gap_m=400):
    """평활화 기반 climb 검출.
    - win_m 윈도우 단위로 grade 계산
    - grade ≥ climb_grade인 윈도우를 "climbing"으로 마크
    - 인접 climbing 윈도우 사이 gap_m 이하의 비-climbing은 같은 climb로 병합
    - 누적 gain ≥ min_gain, 거리 ≥ min_length만 채택
    """
    # 거리·고도 시리즈 추출 (None 제외)
    pts = []
    for i, r in enumerate(records):
        alt = r.get('altitude') if r.get('altitude') is not None else r.get('enhanced_altitude')
        dist = r.get('distance')
        ts = r.get('timestamp')
        if alt is None or dist is None or ts is None:
            continue
        pts.append({'i': i, 'd': dist, 'a': alt, 't': ts})
    if not pts:
        return []

    # win_m마다 시작/끝 인덱스를 모아 grade 측정
    segments = []
    j = 0
    for k in range(len(pts)):
        # j는 pts[k] 기준 win_m 이전 포인트
        while pts[k]['d'] - pts[j]['d'] > win_m and j < k:
            j += 1
        if pts[k]['d'] - pts[j]['d'] >= win_m * 0.6:  # 최소 60% 윈도우
            length = pts[k]['d'] - pts[j]['d']
            gain = pts[k]['a'] - pts[j]['a']
            grade = gain / length * 100 if length > 0 else 0
            segments.append({
                'd_mid': (pts[k]['d'] + pts[j]['d']) / 2,
                'climbing': grade >= climb_grade,
                'i_start': pts[j]['i'],
                'i_end': pts[k]['i'],
                'd_start': pts[j]['d'],
                'd_end': pts[k]['d'],
                'a_start': pts[j]['a'],
                'a_end': pts[k]['a'],
            })

    # climbing 그룹화 (gap_m 이내 비-climbing 허용)
    groups = []
    cur = None
    last_climbing_d = -1e9
    for s in segments:
        if s['climbing']:
            if cur is None or (s['d_start'] - last_climbing_d > gap_m):
                if cur is not None:
                    groups.append(cur)
                cur = {'i_start': s['i_start'], 'd_start': s['d_start'], 'a_start': s['a_start'],
                       'i_end': s['i_end'], 'd_end': s['d_end'], 'a_end': s['a_end']}
            else:
                cur['i_end'] = s['i_end']
                cur['d_end'] = s['d_end']
                cur['a_end'] = s['a_end']
            last_climbing_d = s['d_end']
    if cur is not None:
        groups.append(cur)

    # 그룹 → climb dict
    climbs = []
    idx = 0
    ride_t0 = records[0].get('timestamp') if records else None
    for g in groups:
        # 실제 시작·끝의 고도는 records 내 최저점·최고점으로 보정 (그룹 범위 내)
        seg = records[g['i_start']:g['i_end']+1]
        alts = [r.get('altitude') if r.get('altitude') is not None else r.get('enhanced_altitude')
                for r in seg if (r.get('altitude') is not None or r.get('enhanced_altitude') is not None)]
        if not alts:
            continue
        gain = max(alts) - min(alts)
        length = g['d_end'] - g['d_start']
        if gain < min_gain or length < min_length:
            continue
        grade = gain / length * 100 if length > 0 else 0
        t_start = records[g['i_start']].get('timestamp')
        t_end = records[g['i_end']].get('timestamp')
        duration_s = (t_end - t_start).total_seconds() if t_start and t_end else 0
        if duration_s <= 0:
            continue
        vam = gain / duration_s * 3600
        ps = [r.get('power') for r in seg if r.get('power') is not None]
        hs = [r.get('heart_rate') for r in seg if r.get('heart_rate') is not None and r.get('heart_rate') > 0]
        cs = [r.get('cadence') for r in seg if r.get('cadence') is not None and r.get('cadence') > 0]
        elapsed_start = (t_start - ride_t0).total_seconds() if ride_t0 else 0
        idx += 1
        climbs.append({
            'index': idx,
            'start_km': round(g['d_start'] / 1000, 2),
            'duration_s': int(duration_s),
            'distance_m': round(length, 2),
            'elev_gain_m': round(gain, 2),
            'avg_grade_pct': round(grade, 2),
            'avg_power_w': round(sum(ps) / len(ps), 2) if ps else 0,
            'avg_hr': round(sum(hs) / len(hs), 1) if hs else 0,
            'avg_cadence': round(sum(cs) / len(cs), 1) if cs else 0,
            'vam_m_per_h': round(vam, 2),
            'ride_elapsed_start_s': int(elapsed_start),
        })
    return climbs


def pick_best_fade(climbs):
    """베스트: 가장 높은 VAM. 페이드: 후반부 climb 중 베스트와 grade·distance 유사하면서 VAM 가장 떨어진 것."""
    if not climbs:
        return None, None
    best = max(climbs, key=lambda c: c['vam_m_per_h'])
    # 페이드 후보: best 이후 발생한 climb 중 grade·길이 비슷한 것
    candidates = [
        c for c in climbs
        if c['ride_elapsed_start_s'] > best['ride_elapsed_start_s']
        and abs(c['avg_grade_pct'] - best['avg_grade_pct']) <= 4.0
        and c['index'] != best['index']
    ]
    if candidates:
        fade = min(candidates, key=lambda c: c['vam_m_per_h'])
    else:
        # fallback: 최후반 climb
        late = [c for c in climbs if c['index'] != best['index']]
        fade = late[-1] if late else None
    return best, fade


# ───────── 라이딩 전반 분석 ─────────

POWER_ZONES = [  # Coggan 7-zone, %FTP 상한 (lo, hi]
    ('Z1_recovery',     0.00, 0.55),
    ('Z2_endurance',    0.55, 0.75),
    ('Z3_tempo',        0.75, 0.90),
    ('Z4_threshold',    0.90, 1.05),
    ('Z5_vo2max',       1.05, 1.20),
    ('Z6_anaerobic',    1.20, 1.50),
    ('Z7_neuromuscular', 1.50, 99.0),
]
HR_ZONES = [  # 5-zone, %LTHR
    ('Z1_recovery',  0.00, 0.81),
    ('Z2_endurance', 0.81, 0.89),
    ('Z3_tempo',     0.89, 0.94),
    ('Z4_threshold', 0.94, 1.00),
    ('Z5_vo2max',    1.00, 99.0),
]


def power_zone_distribution(records, ftp_w):
    """파워 존별 시간(초)·비율(%). 0W도 Z1로 포함 (다운힐·코스팅 = 회복)."""
    if not ftp_w:
        return None
    counts = {z[0]: 0 for z in POWER_ZONES}
    total = 0
    for r in records:
        p = r.get('power')
        if p is None:
            continue
        ratio = p / ftp_w
        for name, lo, hi in POWER_ZONES:
            if lo <= ratio < hi:
                counts[name] += 1
                break
        total += 1
    if total == 0:
        return None
    return {z: {'sec': counts[z], 'pct': round(counts[z] / total * 100, 1)} for z in counts}


def hr_zone_distribution(records, lthr):
    """HR 존별 시간·비율."""
    if not lthr:
        return None
    counts = {z[0]: 0 for z in HR_ZONES}
    total = 0
    for r in records:
        h = r.get('heart_rate')
        if h is None or h <= 0:
            continue
        ratio = h / lthr
        for name, lo, hi in HR_ZONES:
            if lo <= ratio < hi:
                counts[name] += 1
                break
        total += 1
    if total == 0:
        return None
    return {z: {'sec': counts[z], 'pct': round(counts[z] / total * 100, 1)} for z in counts}


def mean_max_power(records, durations=(5, 30, 60, 300, 600, 1200, 3600)):
    """Mean-max curve: 각 윈도우의 최대 평균 파워. record 간격 ≈ 1s 가정 (FIT 표준)."""
    powers = [r.get('power') for r in records]
    powers = [p if p is not None else 0 for p in powers]
    if not powers:
        return {}
    out = {}
    for d in durations:
        if d > len(powers):
            continue
        # 슬라이딩 평균 (O(n))
        s = sum(powers[:d])
        best = s
        for i in range(d, len(powers)):
            s += powers[i] - powers[i-d]
            if s > best:
                best = s
        out[f"{d}s"] = round(best / d, 1)
    return out


def time_series_drift(records, bucket_min=30):
    """N분 단위 NP·avg_HR·avg_speed·avg_cadence 추이. 라이딩 전반 페이싱 드리프트 시각화용."""
    if not records:
        return []
    t0 = records[0].get('timestamp')
    if t0 is None:
        return []
    bucket_s = bucket_min * 60
    buckets = {}
    for r in records:
        ts = r.get('timestamp')
        if ts is None:
            continue
        offset = (ts - t0).total_seconds()
        b = int(offset // bucket_s)
        buckets.setdefault(b, []).append(r)
    out = []
    for b in sorted(buckets):
        seg = buckets[b]
        ps = [r.get('power') for r in seg if r.get('power') is not None]
        hs = [r.get('heart_rate') for r in seg if r.get('heart_rate') is not None and r.get('heart_rate') > 0]
        cs = [r.get('cadence') for r in seg if r.get('cadence') is not None and r.get('cadence') > 0]
        speeds = [r.get('speed') for r in seg if r.get('speed') is not None]  # m/s
        out.append({
            'bucket_min_start': b * bucket_min,
            'bucket_min_end': (b + 1) * bucket_min,
            'np_w': round(normalized_power(ps), 1) if ps else 0,
            'avg_power_w': round(sum(ps)/len(ps), 1) if ps else 0,
            'avg_hr': round(sum(hs)/len(hs), 1) if hs else 0,
            'avg_cadence': round(sum(cs)/len(cs), 1) if cs else 0,
            'avg_speed_kmh': round(sum(speeds)/len(speeds) * 3.6, 1) if speeds else 0,
        })
    return out


def half_split_pacing(records, ftp_w):
    """전·후반 절반 분할 NP·HR·속도·VI 비교. Negative split / Positive split 판정."""
    if len(records) < 60:
        return None
    half = len(records) // 2
    h1, h2 = records[:half], records[half:]

    def stats(seg):
        ps = [r.get('power') for r in seg if r.get('power') is not None]
        hs = [r.get('heart_rate') for r in seg if r.get('heart_rate') is not None and r.get('heart_rate') > 0]
        speeds = [r.get('speed') for r in seg if r.get('speed') is not None]
        np = normalized_power(ps) if ps else 0
        avg = sum(ps)/len(ps) if ps else 0
        return {
            'np_w': round(np, 1),
            'avg_power_w': round(avg, 1),
            'vi': round(np/avg, 3) if avg else 0,
            'if_': round(np/ftp_w, 3) if ftp_w else 0,
            'avg_hr': round(sum(hs)/len(hs), 1) if hs else 0,
            'avg_speed_kmh': round(sum(speeds)/len(speeds) * 3.6, 1) if speeds else 0,
        }

    s1, s2 = stats(h1), stats(h2)
    np_drop_pct = round((s2['np_w'] - s1['np_w']) / s1['np_w'] * 100, 1) if s1['np_w'] else 0
    if np_drop_pct >= 2:
        verdict = 'positive_split'  # 후반 더 셈
    elif np_drop_pct <= -8:
        verdict = 'severe_fade'
    elif np_drop_pct <= -2:
        verdict = 'negative_split'  # 후반 떨어짐
    else:
        verdict = 'even'
    return {
        'first_half': s1,
        'second_half': s2,
        'np_change_pct': np_drop_pct,
        'verdict': verdict,
    }


def categorize_climb(climb):
    """UCI 점수(거리m × grade%)로 HC/Cat1~4 분류."""
    if not climb:
        return None
    score = climb.get('distance_m', 0) * climb.get('avg_grade_pct', 0)
    if score >= 80000:
        return 'HC'
    if score >= 64000:
        return 'Cat1'
    if score >= 32000:
        return 'Cat2'
    if score >= 16000:
        return 'Cat3'
    if score >= 8000:
        return 'Cat4'
    return 'NC'  # 비분류


def detect_intervals(records, ftp_w, min_duration_s=60, threshold_ratio=0.91):
    """Z4 이상(>=91% FTP) 1분 이상 지속 구간 자동 검출. 인터벌·어택 노출."""
    if not ftp_w:
        return []
    threshold = ftp_w * threshold_ratio
    intervals = []
    cur_start = None
    cur_powers = []
    ride_t0 = records[0].get('timestamp') if records else None
    for i, r in enumerate(records):
        p = r.get('power')
        ts = r.get('timestamp')
        if p is None or ts is None:
            continue
        if p >= threshold:
            if cur_start is None:
                cur_start = (i, ts)
                cur_powers = []
            cur_powers.append(p)
        else:
            if cur_start is not None and len(cur_powers) >= min_duration_s:
                start_i, start_ts = cur_start
                duration = (ts - start_ts).total_seconds()
                avg_p = sum(cur_powers)/len(cur_powers)
                max_p = max(cur_powers)
                elapsed = (start_ts - ride_t0).total_seconds() if ride_t0 else 0
                start_dist = records[start_i].get('distance')
                intervals.append({
                    'ride_elapsed_start_s': int(elapsed),
                    'start_km': round(start_dist/1000, 2) if start_dist else None,
                    'duration_s': int(duration),
                    'avg_power_w': round(avg_p, 1),
                    'max_power_w': int(max_p),
                    'if_': round(avg_p/ftp_w, 3),
                })
            cur_start = None
            cur_powers = []
    # 끝까지 지속된 인터벌
    if cur_start is not None and len(cur_powers) >= min_duration_s:
        start_i, start_ts = cur_start
        last_ts = records[-1].get('timestamp')
        duration = (last_ts - start_ts).total_seconds()
        avg_p = sum(cur_powers)/len(cur_powers)
        max_p = max(cur_powers)
        elapsed = (start_ts - ride_t0).total_seconds() if ride_t0 else 0
        start_dist = records[start_i].get('distance')
        intervals.append({
            'ride_elapsed_start_s': int(elapsed),
            'start_km': round(start_dist/1000, 2) if start_dist else None,
            'duration_s': int(duration),
            'avg_power_w': round(avg_p, 1),
            'max_power_w': int(max_p),
            'if_': round(avg_p/ftp_w, 3),
        })
    return intervals


def endurance_metrics(records, ftp_w, lthr):
    """시간 구간별 (0-1h, 1-2h, 2-3h, 3-4h, 4h+) NP·VI·IF·HR·케이던스·속도.

    장거리 페이싱 추적용 — Seorak 10h 라이딩에서 후반 구간 출력 유지율을 본다.
    추가로 Power Durability 지표:
    - first_5min_best_w: 라이딩 첫 1시간 내 5분 베스트 파워
    - late_5min_best_w: 마지막 1/3 시간 내 5분 베스트 파워
    - durability_pct: late / first × 100
    """
    if not records or not ftp_w:
        return None
    t0 = records[0].get('timestamp')
    if t0 is None:
        return None

    bands = [
        ('0-1h', 0, 3600),
        ('1-2h', 3600, 7200),
        ('2-3h', 7200, 10800),
        ('3-4h', 10800, 14400),
        ('4-5h', 14400, 18000),
        ('5h+',  18000, 10**9),
    ]
    out = []
    for label, lo, hi in bands:
        seg = []
        for r in records:
            ts = r.get('timestamp')
            if ts is None:
                continue
            offset = (ts - t0).total_seconds()
            if lo <= offset < hi:
                seg.append(r)
        if not seg or len(seg) < 30:
            continue
        ps = [r.get('power') for r in seg if r.get('power') is not None]
        hs = [r.get('heart_rate') for r in seg if r.get('heart_rate') is not None and r.get('heart_rate') > 0]
        cs = [r.get('cadence') for r in seg if r.get('cadence') is not None and r.get('cadence') > 0]
        speeds = [r.get('speed') for r in seg if r.get('speed') is not None]
        np = normalized_power(ps) if ps else 0
        avg = sum(ps)/len(ps) if ps else 0
        out.append({
            'band': label,
            'duration_s': len(seg),
            'np_w': round(np, 1),
            'avg_power_w': round(avg, 1),
            'vi': round(np/avg, 3) if avg else 0,
            'if_': round(np/ftp_w, 3) if ftp_w else 0,
            'avg_hr': round(sum(hs)/len(hs), 1) if hs else 0,
            'hr_pct_lthr': round(sum(hs)/len(hs) / lthr * 100, 1) if hs and lthr else 0,
            'avg_cadence': round(sum(cs)/len(cs), 1) if cs else 0,
            'avg_speed_kmh': round(sum(speeds)/len(speeds) * 3.6, 1) if speeds else 0,
        })

    # Power Durability — 첫 1h vs 마지막 1/3 시간의 5분 베스트 비교
    durability = None
    n = len(records)
    if n >= 1800:  # 30분 이상
        first_seg = []
        for r in records:
            ts = r.get('timestamp')
            if ts is None:
                continue
            if (ts - t0).total_seconds() < 3600:
                first_seg.append(r)
        last_third_start = int(n * 2/3)
        last_seg = records[last_third_start:]

        def best_5min(seg):
            ps = [r.get('power') if r.get('power') is not None else 0 for r in seg]
            if len(ps) < 300:
                return None
            s = sum(ps[:300])
            best = s
            for i in range(300, len(ps)):
                s += ps[i] - ps[i-300]
                if s > best:
                    best = s
            return round(best/300, 1)

        first_5 = best_5min(first_seg)
        late_5 = best_5min(last_seg)
        if first_5 and late_5 and first_5 > 0:
            durability = {
                'first_hour_5min_best_w': first_5,
                'last_third_5min_best_w': late_5,
                'durability_pct': round(late_5 / first_5 * 100, 1),
            }

    return {'bands': out, 'durability': durability}


def fueling_recommendation(tss, moving_s, weight_kg, distance_km):
    """탄수·수분 권장량. ACSM/Burke 기준.
    - 탄수: TSS·시간 기반 (1~2h: 30g/h, 2~3h: 60g/h, 3h+: 60~90g/h)
    - 수분: 시간당 500~800ml (체중·온도 무관 보수적 권장)
    """
    h = (moving_s or 0) / 3600
    if h < 1:
        carb_per_h = 30
    elif h < 2.5:
        carb_per_h = 60
    else:
        carb_per_h = 75  # 90까지 가도 되지만 위장 적응 필요
    total_carb = round(carb_per_h * h)
    fluid_per_h = 600  # ml
    total_fluid = round(fluid_per_h * h)
    # 칼로리 추정 (실측 W/시간 사용)
    # TSS=100 ≈ FTP에서 1시간 → ~3,600 kJ * 24% efficiency 손실 = 약 약 720kcal? 단순화: TSS×3.6 kcal
    kcal_est = round(tss * 3.6) if tss else 0
    return {
        'total_carb_g': total_carb,
        'carb_per_h_g': carb_per_h,
        'total_fluid_ml': total_fluid,
        'fluid_per_h_ml': fluid_per_h,
        'kcal_est': kcal_est,
    }


def segment_ride(records, win_m=500, climb_grade=2.5, descent_grade=-2.5):
    """라이딩을 flat / climb / descent 구간 시퀀스로 분할.
    - 평활화된 grade로 climb/descent/flat 라벨링
    - 같은 라벨 연속 구간을 병합
    """
    pts = []
    for r in records:
        alt = r.get('altitude') if r.get('altitude') is not None else r.get('enhanced_altitude')
        dist = r.get('distance')
        ts = r.get('timestamp')
        if alt is None or dist is None or ts is None:
            continue
        pts.append({'d': dist, 'a': alt, 't': ts})
    if len(pts) < 2:
        return []

    # 윈도우 grade
    labels = []
    j = 0
    for k in range(len(pts)):
        while pts[k]['d'] - pts[j]['d'] > win_m and j < k:
            j += 1
        length = pts[k]['d'] - pts[j]['d']
        if length < win_m * 0.4:
            labels.append('flat')
            continue
        gain = pts[k]['a'] - pts[j]['a']
        grade = gain / length * 100 if length > 0 else 0
        if grade >= climb_grade:
            labels.append('climb')
        elif grade <= descent_grade:
            labels.append('descent')
        else:
            labels.append('flat')

    # 같은 라벨 병합 (스파이크 제거: 30초 이내 단일 라벨은 인접에 흡수)
    segments = []
    cur_label = labels[0]
    cur_start = 0
    for i in range(1, len(labels)):
        if labels[i] != cur_label:
            segments.append({'label': cur_label, 'i_start': cur_start, 'i_end': i - 1})
            cur_label = labels[i]
            cur_start = i
    segments.append({'label': cur_label, 'i_start': cur_start, 'i_end': len(labels) - 1})

    # 짧은 세그먼트 흡수 (60s 미만)
    merged = []
    for s in segments:
        seg_dur = (pts[s['i_end']]['t'] - pts[s['i_start']]['t']).total_seconds()
        if merged and seg_dur < 60:
            merged[-1]['i_end'] = s['i_end']
        else:
            merged.append({**s, 'duration_s': seg_dur})

    # 출력 포맷
    out = []
    ride_t0 = pts[0]['t']
    for s in merged:
        a = pts[s['i_start']]
        b = pts[s['i_end']]
        dur = (b['t'] - a['t']).total_seconds()
        dist = b['d'] - a['d']
        gain = b['a'] - a['a']
        out.append({
            'label': s['label'],
            'start_km': round(a['d']/1000, 2),
            'end_km': round(b['d']/1000, 2),
            'distance_m': round(dist, 1),
            'duration_s': int(dur),
            'elev_change_m': round(gain, 1),
            'ride_elapsed_start_s': int((a['t'] - ride_t0).total_seconds()),
        })
    return out


def build_analysis(fit_path, rider=None):
    rider = {**DEFAULT_RIDER, **(rider or {})}
    rider['w_per_kg'] = round(rider['ftp_w'] / rider['weight_kg'], 2)

    fit = FitFile(str(fit_path))

    # Records 수집
    records = []
    for rec in fit.get_messages('record'):
        records.append({f.name: f.value for f in rec})
    if not records:
        raise ValueError("FIT records 없음")

    # Session 메시지 (가민 공식 계산값)
    session = {}
    for s in fit.get_messages('session'):
        session = {f.name: f.value for f in s}
        break

    t0 = records[0].get('timestamp')
    t1 = records[-1].get('timestamp')

    # 거리·고도
    distances = [r.get('distance') for r in records if r.get('distance') is not None]
    distance_km = (max(distances) - min(distances)) / 1000 if distances else 0
    if 'total_distance' in session and session['total_distance']:
        distance_km = session['total_distance'] / 1000

    elev_gain = session.get('total_ascent')
    if elev_gain is None:
        alts = [r.get('altitude') or r.get('enhanced_altitude') for r in records]
        alts = [a for a in alts if a is not None]
        elev_gain = 0
        for i in range(1, len(alts)):
            if alts[i] > alts[i-1]:
                elev_gain += alts[i] - alts[i-1]

    elapsed_s = session.get('total_elapsed_time')
    if elapsed_s is None and t0 and t1:
        elapsed_s = (t1 - t0).total_seconds()
    moving_s = session.get('total_timer_time') or elapsed_s

    avg_speed_kmh = (distance_km / (moving_s / 3600)) if moving_s else 0

    # 파워
    powers = [r.get('power') for r in records if r.get('power') is not None]
    avg_power = session.get('avg_power') or (sum(powers) / len(powers) if powers else 0)
    np_w = session.get('normalized_power') or normalized_power([r.get('power') for r in records])
    vi = round(np_w / avg_power, 3) if avg_power else 0
    # IF/TSS는 가민 session 값을 신뢰하지 않음 — 디바이스에 설정된 FTP가 다를 수 있음.
    # 항상 라이더 프로필의 FTP로 재계산.
    if_ = (np_w / rider['ftp_w']) if rider['ftp_w'] else 0
    tss = round((moving_s * np_w * if_) / (rider['ftp_w'] * 3600) * 100) if (moving_s and rider['ftp_w']) else 0
    max_power = session.get('max_power') or (max(powers) if powers else 0)

    # HR
    hrs = [r.get('heart_rate') for r in records
           if r.get('heart_rate') is not None and r.get('heart_rate') > 0]
    avg_hr = session.get('avg_heart_rate') or (sum(hrs) / len(hrs) if hrs else 0)
    max_hr = session.get('max_heart_rate') or (max(hrs) if hrs else 0)

    # 케이던스
    avg_cad = session.get('avg_cadence')
    if avg_cad is None:
        cads = [r.get('cadence') for r in records
                if r.get('cadence') is not None and r.get('cadence') > 0]
        avg_cad = sum(cads) / len(cads) if cads else 0

    # 디커플링
    dec = decoupling_pct(records)

    # 클라임
    climbs = detect_climbs(records)
    best, fade = pick_best_fade(climbs)
    for c in climbs:
        c['category'] = categorize_climb(c)

    # 라이딩 전반 분석
    pz = power_zone_distribution(records, rider['ftp_w'])
    hz = hr_zone_distribution(records, rider['lthr'])
    mmp = mean_max_power(records)
    drift = time_series_drift(records, bucket_min=30)
    halves = half_split_pacing(records, rider['ftp_w'])
    intervals = detect_intervals(records, rider['ftp_w'])
    segments = segment_ride(records)

    summary = {
        'distance_km': round(distance_km, 2),
        'elev_gain_m': int(round(elev_gain)),
        'elev_per_km': round(elev_gain / distance_km, 1) if distance_km else 0,
        'elapsed_h': fmt_h(elapsed_s),
        'moving_h': fmt_h(moving_s),
        'avg_speed_kmh': round(avg_speed_kmh, 1),
        'avg_power_w': round(avg_power, 1) if avg_power else 0,
        'np_w': round(np_w, 1) if np_w else 0,
        'vi': vi,
        'if_': round(if_, 3) if if_ else 0,
        'tss': int(round(tss)) if tss else 0,
        'avg_hr': int(round(avg_hr)),
        'max_hr': int(round(max_hr)),
        'avg_cadence': int(round(avg_cad)),
        'max_power_w': int(round(max_power)),
        'decoupling_pct': dec if dec is not None else 0,
    }

    # FIT 타임스탬프는 UTC (가민 표준). tz info 명시.
    ride_start_utc = ''
    if t0:
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        ride_start_utc = t0.isoformat()

    fueling = fueling_recommendation(summary['tss'], moving_s, rider['weight_kg'], summary['distance_km'])
    endurance = endurance_metrics(records, rider['ftp_w'], rider['lthr'])

    # Seorak 시뮬 + TDF 10년 trajectory (옵션, lib.seorak 사용 가능 시)
    seorak_sim = None
    tdf_traj = None
    try:
        import seorak
        seorak_sim = seorak.seorak_simulation(summary)
        # athlete_db.json 있으면 ftp_trend 활용 — 두 단계 위 (data 폴더)
        ftp_trend = None
        for parent in [Path(fit_path).parent, Path(fit_path).parent.parent]:
            db_path = parent / 'athlete_db.json'
            if db_path.exists():
                try:
                    db = json.loads(db_path.read_text(encoding='utf-8'))
                    ftp_trend = db.get('ftp_trend')
                    break
                except Exception:
                    pass
        tdf_traj = seorak.tdf_trajectory(
            current_wpk=rider.get('w_per_kg'),
            ftp_trend=ftp_trend,
            today_tss=summary.get('tss'),
            weight_kg=rider.get('weight_kg'),
            today_iso=ride_start_utc[:10] if ride_start_utc else None,
        )
    except Exception:
        pass

    out = {
        'fit_path': Path(fit_path).name,
        'ride_start_utc': ride_start_utc,
        'rider': rider,
        'summary': summary,
        'climbs': climbs,
        'best_climb': best,
        'fade_climb': fade,
        'power_zones': pz,
        'hr_zones': hz,
        'mean_max_power': mmp,
        'time_drift': drift,
        'half_split': halves,
        'intervals': intervals,
        'segments': segments,
        'fueling': fueling,
        'endurance': endurance,
        'seorak_simulation': seorak_sim,
        'tdf_trajectory': tdf_traj,
    }
    return out


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 build_analysis.py <ride_dir> [fit_file]")
        sys.exit(1)
    ride_dir = Path(sys.argv[1])
    if not ride_dir.is_dir():
        print(f"✗ 폴더 없음: {ride_dir}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        fit_path = Path(sys.argv[2])
    else:
        fits = list(ride_dir.glob('*.fit')) + list(ride_dir.glob('*.FIT'))
        if not fits:
            print(f"✗ .fit 파일 없음: {ride_dir}")
            sys.exit(1)
        fit_path = fits[0]

    print(f"  → FIT: {fit_path.name}")
    analysis = build_analysis(fit_path)

    out_path = ride_dir / '_analysis.json'
    out_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"  ✓ 저장: {out_path}")

    s = analysis['summary']
    print(f"\n  === 요약 ===")
    print(f"    거리       : {s['distance_km']} km")
    print(f"    상승       : {s['elev_gain_m']} m ({s['elev_per_km']} m/km)")
    print(f"    경과/이동  : {s['elapsed_h']} / {s['moving_h']}")
    print(f"    평균속도   : {s['avg_speed_kmh']} km/h")
    print(f"    Avg/NP     : {s['avg_power_w']}W / {s['np_w']}W (VI {s['vi']})")
    print(f"    IF/TSS     : {s['if_']} / {s['tss']}")
    print(f"    HR avg/max : {s['avg_hr']} / {s['max_hr']} bpm")
    print(f"    케이던스   : {s['avg_cadence']} rpm")
    print(f"    디커플링   : {s['decoupling_pct']}%")
    print(f"  === 클라임 {len(analysis['climbs'])}개 ===")
    for c in analysis['climbs']:
        marker = ''
        if analysis['best_climb'] and c['index'] == analysis['best_climb']['index']:
            marker = ' ★ BEST'
        if analysis['fade_climb'] and c['index'] == analysis['fade_climb']['index']:
            marker = ' ⚠ FADE'
        cat = c.get('category') or '-'
        print(f"    [{c['index']}] {c['start_km']:.1f}km · {c['distance_m']/1000:.2f}km · "
              f"+{c['elev_gain_m']:.0f}m · {c['avg_grade_pct']:.1f}% · "
              f"{c['avg_power_w']:.0f}W · VAM {c['vam_m_per_h']:.0f} · {cat}{marker}")

    pz = analysis.get('power_zones')
    if pz:
        print(f"  === 파워 존 분포 ===")
        for z, v in pz.items():
            bar = '█' * int(v['pct'] / 2)
            print(f"    {z:18s} {v['pct']:5.1f}% {bar}")

    mmp = analysis.get('mean_max_power') or {}
    if mmp:
        print(f"  === Mean-max Power ===")
        for d, w in mmp.items():
            print(f"    {d:>5s}: {w:.0f}W")

    halves = analysis.get('half_split')
    if halves:
        print(f"  === 전·후반 페이싱 ===")
        h1, h2 = halves['first_half'], halves['second_half']
        print(f"    전반: NP {h1['np_w']:.0f}W · IF {h1['if_']:.2f} · HR {h1['avg_hr']:.0f} · {h1['avg_speed_kmh']:.1f} km/h")
        print(f"    후반: NP {h2['np_w']:.0f}W · IF {h2['if_']:.2f} · HR {h2['avg_hr']:.0f} · {h2['avg_speed_kmh']:.1f} km/h")
        print(f"    NP 변화: {halves['np_change_pct']:+.1f}% → {halves['verdict']}")

    intervals = analysis.get('intervals') or []
    if intervals:
        print(f"  === Z4+ 인터벌 {len(intervals)}개 ===")
        for it in intervals:
            print(f"    {it['ride_elapsed_start_s']//60:>3d}m | {it['duration_s']}s · {it['avg_power_w']:.0f}W (IF {it['if_']:.2f})")

    segments = analysis.get('segments') or []
    if segments:
        cnt = {'flat':0,'climb':0,'descent':0}
        dur = {'flat':0,'climb':0,'descent':0}
        for s in segments:
            cnt[s['label']] = cnt.get(s['label'], 0) + 1
            dur[s['label']] = dur.get(s['label'], 0) + s['duration_s']
        print(f"  === 구간 분류 ({len(segments)}개) ===")
        for label in ('climb','flat','descent'):
            print(f"    {label:>7s}: {cnt.get(label,0)}회 · 누적 {dur.get(label,0)//60}분")

    fueling = analysis.get('fueling')
    if fueling:
        print(f"  === 영양 권장 ===")
        print(f"    탄수: {fueling['carb_per_h_g']}g/h × → 총 {fueling['total_carb_g']}g")
        print(f"    수분: {fueling['fluid_per_h_ml']}ml/h × → 총 {fueling['total_fluid_ml']}ml")
        print(f"    소비 칼로리(추정): {fueling['kcal_est']} kcal")

    endurance = analysis.get('endurance')
    if endurance and endurance.get('bands'):
        print(f"  === 시간 구간별 endurance ===")
        for b in endurance['bands']:
            print(f"    {b['band']:>5s}: NP {b['np_w']:>5.0f}W (IF {b['if_']:.2f}) · "
                  f"HR {b['avg_hr']:>3.0f} ({b['hr_pct_lthr']:.0f}%LTHR) · "
                  f"케이던스 {b['avg_cadence']:>3.0f} · 속도 {b['avg_speed_kmh']:.1f}km/h")
        d = endurance.get('durability')
        if d:
            print(f"    Durability: 첫 1h 5분best {d['first_hour_5min_best_w']:.0f}W → "
                  f"마지막 1/3 5분best {d['last_third_5min_best_w']:.0f}W "
                  f"({d['durability_pct']:.0f}% 유지)")

    seo = analysis.get('seorak_simulation')
    if seo:
        print(f"  === 설악 GF 시뮬 ===")
        print(f"    같은 페이스 → {seo['extrap_finish_h']}h, 디커플링 보정 {seo['adjusted_finish_h']}h (목표 {seo['target_finish_h']}h)")
        print(f"    컷오프 1: {'✓' if seo['cutoff_1_pass'] else '✗'} ({seo['today_avg_kmh']:.1f} vs {seo['cutoff_1_pace_kmh']:.1f}km/h)")
        print(f"    컷오프 2: {'✓' if seo['cutoff_2_pass'] else '✗'} ({seo['today_avg_kmh']:.1f} vs {seo['cutoff_2_pace_kmh']:.1f}km/h)")
        print(f"    종합 가능성: {seo['feasibility_pct']}% · 가장 큰 갭: {seo['biggest_gap']['dim']}")
        print(f"    10h 완주 권장 IF: {seo['target_if_for_10h']:.2f} (오늘 {seo['today_if']:.2f})")


if __name__ == '__main__':
    main()
