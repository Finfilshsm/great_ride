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

    out = {
        'fit_path': Path(fit_path).name,
        'ride_start_utc': ride_start_utc,
        'rider': rider,
        'summary': summary,
        'climbs': climbs,
        'best_climb': best,
        'fade_climb': fade,
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
        print(f"    [{c['index']}] {c['start_km']:.1f}km · {c['distance_m']/1000:.2f}km · "
              f"+{c['elev_gain_m']:.0f}m · {c['avg_grade_pct']:.1f}% · "
              f"{c['avg_power_w']:.0f}W · VAM {c['vam_m_per_h']:.0f}{marker}")


if __name__ == '__main__':
    main()
