#!/usr/bin/env python3
"""모든 라이딩의 _analysis.json을 누적 → 단일 athlete_db.json.

DB 위치: <cycling-tools 부모 폴더>/athlete_db.json (라이딩 폴더와 형제)

이 모듈은:
- 모든 라이딩 폴더를 자동 탐색 (날짜 패턴: 2026.X.X..., 2027... 등)
- 각 폴더의 _analysis.json + ride_meta.json + 영양 메모를 통합
- CTL/ATL/TSB, 주별 부하, 코스 베스트, 영양 효율 데이터를 계산
- A-race 준비도 평가

사용법:
    from athlete_db import load_db, refresh_db
    db = refresh_db()  # 또는 load_db() (이미 있으면 그대로)
"""
import re
import json
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone


# ───────── 라이더 프로파일 (개인 설정) ─────────
RIDER = {
    'ftp_w': 180,
    'weight_kg': 73,
    'lthr': 168,
    'w_per_kg': 2.47,
}

# A-race
A_RACE = {
    'name': 'Seorak Granfondo 208km',
    'date': '2026-06-20',
    'distance_km': 208,
    'elev_gain_m': 3800,
    'cutoff_1_h': 4.0,    # 12:00 ~ start 8:00 = 4h to km 82
    'cutoff_1_km': 82,
    'cutoff_2_h': 7.67,   # 15:40
    'cutoff_2_km': 167,
    'major_climbs': [
        {'name': 'Seorim pass HC', 'distance_km': 4.3, 'grade_pct': 10.9, 'gain_m': 470},
        {'name': 'Hangye pass', 'distance_km': 10.6, 'grade_pct': 4.4, 'gain_m': 466},
        {'name': 'Guyong pass (final)', 'distance_km': 20.5, 'grade_pct': 4.2, 'gain_m': 860},
    ],
}


def find_ride_dirs(base_dir):
    """기본 폴더에서 라이딩 폴더(_analysis.json 보유)를 모두 찾는다."""
    base = Path(base_dir)
    rides = []
    pat = re.compile(r'^20\d{2}\.\d+\.\d+')
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if not pat.match(child.name):
            continue
        if (child / '_analysis.json').exists():
            rides.append(child)
    rides.sort(key=lambda p: p.name)
    return rides


def load_ride(ride_dir):
    """단일 라이딩 폴더에서 분석·메타 통합 로드."""
    ride_dir = Path(ride_dir)
    out = {'dir': str(ride_dir), 'name': ride_dir.name}

    a_path = ride_dir / '_analysis.json'
    if a_path.exists():
        out['analysis'] = json.loads(a_path.read_text(encoding='utf-8'))
    m_path = ride_dir / 'ride_meta.json'
    if m_path.exists():
        out['meta'] = json.loads(m_path.read_text(encoding='utf-8'))

    # 폴더명에서 일자 추출 (예: "2026.5.5.화.0900 헐몰팔" → "2026-05-05")
    m = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', ride_dir.name)
    if m:
        out['date'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # ride_start_utc fallback
    if 'date' not in out and 'analysis' in out:
        try:
            dt = datetime.fromisoformat(out['analysis']['ride_start_utc'].replace('Z', '+00:00'))
            out['date'] = dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    return out


# ───────── CTL/ATL/TSB (Training Stress Balance) ─────────
def compute_pmc(rides, today=None):
    """Performance Management Chart — CTL(42d EWMA), ATL(7d EWMA), TSB(CTL-ATL), ACWR.

    ACWR (Acute:Chronic Workload Ratio) — 부상 위험 예측:
      - acute = 7일 누적 TSS
      - chronic = 28일 평균 일일 TSS × 7
      - ratio = acute / chronic
      - 0.8~1.3 = sweet spot, 1.5+ = 부상 위험, <0.8 = detrain

    Returns: list of {date, tss, ctl, atl, tsb, acwr, acwr_state}
    """
    if not rides:
        return []

    def ewma(alpha, prev, x):
        return alpha * x + (1 - alpha) * prev

    a_ctl = 1 / 42
    a_atl = 1 / 7

    rides_sorted = sorted([r for r in rides if r.get('date')], key=lambda r: r['date'])
    if not rides_sorted:
        return []
    start = datetime.fromisoformat(rides_sorted[0]['date'])
    end = datetime.fromisoformat(today) if today else datetime.now()

    by_date = {}
    for r in rides_sorted:
        ts = (r.get('analysis', {}).get('summary', {}) or {}).get('tss', 0)
        by_date[r['date']] = (by_date.get(r['date'], 0) + ts)

    ctl, atl = 0.0, 0.0
    out = []
    daily_tss = []  # 시간순 일별 TSS (ACWR 계산용)
    cur = start
    while cur <= end:
        date_str = cur.strftime('%Y-%m-%d')
        tss = by_date.get(date_str, 0)
        daily_tss.append(tss)
        ctl = ewma(a_ctl, ctl, tss)
        atl = ewma(a_atl, atl, tss)

        # ACWR
        acute = sum(daily_tss[-7:])
        chronic_28d = daily_tss[-28:] if len(daily_tss) >= 28 else daily_tss
        chronic = sum(chronic_28d) / len(chronic_28d) * 7 if chronic_28d else 0
        acwr = round(acute / chronic, 2) if chronic > 0 else 0
        if acwr == 0:
            state = 'no_data'
        elif acwr < 0.8:
            state = 'detrain'
        elif acwr <= 1.3:
            state = 'safe'
        elif acwr <= 1.5:
            state = 'caution'
        else:
            state = 'injury_risk'

        out.append({
            'date': date_str,
            'tss': tss,
            'ctl': round(ctl, 1),
            'atl': round(atl, 1),
            'tsb': round(ctl - atl, 1),
            'acwr': acwr,
            'acwr_state': state,
        })
        cur += timedelta(days=1)
    return out


# ───────── 주간 부하 ─────────
def weekly_loads(rides, n_weeks=8):
    """최근 n주 주간 부하 (TSS·거리·상승·주행시간)."""
    if not rides:
        return []
    today = datetime.now().date()
    weeks = []
    for w in range(n_weeks):
        end = today - timedelta(days=today.weekday()) + timedelta(days=6) - timedelta(weeks=w)
        start = end - timedelta(days=6)
        wk = {
            'week_start': start.isoformat(),
            'week_end': end.isoformat(),
            'tss': 0,
            'distance_km': 0,
            'elev_gain_m': 0,
            'rides': 0,
        }
        for r in rides:
            d = r.get('date')
            if not d:
                continue
            d_obj = datetime.fromisoformat(d).date()
            if start <= d_obj <= end:
                s = r.get('analysis', {}).get('summary', {}) or {}
                wk['tss'] += s.get('tss', 0) or 0
                wk['distance_km'] += s.get('distance_km', 0) or 0
                wk['elev_gain_m'] += s.get('elev_gain_m', 0) or 0
                wk['rides'] += 1
        weeks.append(wk)
    return list(reversed(weeks))


# ───────── 코스/Climb 베스트 라이브러리 ─────────
def climb_records(rides):
    """모든 라이딩의 climb를 distance·grade 키로 그룹화 → 베스트 VAM 추출."""
    library = {}
    for r in rides:
        clbs = (r.get('analysis', {}) or {}).get('climbs', []) or []
        for c in clbs:
            length_km = round((c.get('distance_m', 0) or 0) / 1000, 1)
            grade = round(c.get('avg_grade_pct', 0) or 0, 1)
            key = f"{length_km}km @ {grade}%"
            entry = library.setdefault(key, {'records': []})
            entry['records'].append({
                'ride': r.get('name'),
                'date': r.get('date'),
                'vam': c.get('vam_m_per_h', 0),
                'avg_power_w': c.get('avg_power_w', 0),
                'avg_hr': c.get('avg_hr', 0),
                'avg_cadence': c.get('avg_cadence', 0),
            })
    # 베스트 추출
    for key in library:
        recs = library[key]['records']
        recs.sort(key=lambda r: -(r.get('vam') or 0))
        library[key]['best_vam'] = recs[0] if recs else None
        library[key]['n_attempts'] = len(recs)
    return library


# ───────── A-race 준비도 (Seorak GF 기준) ─────────
def seorak_readiness(rides, race=A_RACE):
    """5가지 차원에서 A-race 준비도 평가 (0~100%)."""
    if not rides:
        return None

    # 최근 라이딩 중 가장 큰 거리·상승·시간 (하루)
    max_dist = max((r.get('analysis', {}).get('summary', {}).get('distance_km', 0) or 0) for r in rides)
    max_elev = max((r.get('analysis', {}).get('summary', {}).get('elev_gain_m', 0) or 0) for r in rides)
    longest_h_str = ''
    longest_h = 0
    for r in rides:
        h_str = r.get('analysis', {}).get('summary', {}).get('elapsed_h', '0:0:0')
        try:
            h, m, s = h_str.split(':')
            h_val = int(h) + int(m)/60 + int(s)/3600
        except Exception:
            h_val = 0
        if h_val > longest_h:
            longest_h = h_val
            longest_h_str = h_str

    # 최근 4주 평균 디커플링
    cutoff = datetime.now().date() - timedelta(days=28)
    recent = [r for r in rides if r.get('date') and datetime.fromisoformat(r['date']).date() >= cutoff]
    if recent:
        decs = [r.get('analysis', {}).get('summary', {}).get('decoupling_pct', 99) for r in recent]
        decs = [d for d in decs if d is not None]
        avg_dec = sum(decs) / len(decs) if decs else None
    else:
        avg_dec = None

    # 차원별 점수 (0~100%)
    dist_pct = min(100, max_dist / race['distance_km'] * 100)
    elev_pct = min(100, max_elev / race['elev_gain_m'] * 100)
    time_pct = min(100, longest_h / 9.5 * 100)  # 9.5h 컷오프 추정
    # 디커플링: 5% 이하면 100점, 20%이면 0점
    if avg_dec is None:
        dec_pct = None
    else:
        dec_pct = max(0, min(100, (20 - avg_dec) / 15 * 100))

    return {
        'dimensions': {
            'distance': {'current_max_km': round(max_dist, 1), 'target_km': race['distance_km'], 'pct': round(dist_pct)},
            'elevation': {'current_max_m': int(max_elev), 'target_m': race['elev_gain_m'], 'pct': round(elev_pct)},
            'duration': {'current_max_h': round(longest_h, 1), 'target_h': 9.5, 'pct': round(time_pct)},
            'decoupling': {'recent_4w_avg': round(avg_dec, 1) if avg_dec else None, 'target_max': 8, 'pct': round(dec_pct) if dec_pct else None},
        },
        'overall_pct': round((dist_pct + elev_pct + time_pct + (dec_pct or 0)) / (4 if dec_pct else 3)),
    }


# ───────── FTP 추정 / W/kg trend ─────────
def ftp_trend(rides, weight_kg, manual_ftp=None):
    """라이딩별 20분 베스트 × 0.95 = FTP 추정.

    실제 FTP 측정 없이도 라이딩 데이터로 자동 추정.
    - per_ride: 각 라이딩의 추정 FTP (라이딩 길이 ≥1h, 20분 베스트 ≥80W일 때만)
    - rolling_30d: 지난 30일의 best 20분 × 0.95 (단일 측정 노이즈 완화)
    - manual_ftp: rider_profile.json 의 수동 입력값 (있으면 비교용으로 함께 표시)

    Returns: {per_ride: [...], rolling: [...], current_estimated_ftp, current_w_per_kg}
    """
    per_ride = []
    for r in rides:
        date = r.get('date')
        if not date:
            continue
        a = r.get('analysis', {}) or {}
        mmp = a.get('mean_max_power') or {}
        p20 = mmp.get('1200s')
        if p20 is None or p20 < 80:
            continue
        # 1시간 미만 라이딩이면 신뢰도 낮음 — 제외
        h_str = a.get('summary', {}).get('moving_h', '0:0:0')
        try:
            h, m, s = h_str.split(':')
            moving_h = int(h) + int(m)/60 + int(s)/3600
        except Exception:
            moving_h = 0
        if moving_h < 1:
            continue
        est_ftp = round(p20 * 0.95, 1)
        per_ride.append({
            'date': date,
            'p20_w': p20,
            'estimated_ftp_w': est_ftp,
            'w_per_kg': round(est_ftp / weight_kg, 2) if weight_kg else None,
        })

    # 30일 rolling (각 라이딩 시점의 지난 30일 최대값 기반)
    rolling = []
    for i, r in enumerate(per_ride):
        cur_date = datetime.fromisoformat(r['date']).date()
        cutoff = cur_date - timedelta(days=30)
        recent = [pr for pr in per_ride[:i+1]
                  if datetime.fromisoformat(pr['date']).date() >= cutoff]
        if not recent:
            continue
        peak_p20 = max(pr['p20_w'] for pr in recent)
        ftp_est = round(peak_p20 * 0.95, 1)
        rolling.append({
            'date': r['date'],
            'rolling_p20_w': peak_p20,
            'rolling_ftp_w': ftp_est,
            'w_per_kg': round(ftp_est / weight_kg, 2) if weight_kg else None,
        })

    current_est = rolling[-1]['rolling_ftp_w'] if rolling else None
    current_wpk = rolling[-1]['w_per_kg'] if rolling else None

    return {
        'per_ride': per_ride,
        'rolling_30d': rolling,
        'manual_ftp_w': manual_ftp,
        'current_estimated_ftp_w': current_est,
        'current_estimated_w_per_kg': current_wpk,
        'manual_vs_estimated_delta': round(current_est - manual_ftp, 1) if (current_est and manual_ftp) else None,
    }


# ───────── 영양 효율 추적 ─────────
def nutrition_efficiency(rides):
    """ride_meta.json의 영양 메모(있으면) + 디커플링 결과 매칭."""
    out = []
    for r in rides:
        meta = r.get('meta', {}) or {}
        nutrition = meta.get('영양', meta.get('보급', meta.get('nutrition_pattern', '')))
        s = (r.get('analysis', {}) or {}).get('summary', {}) or {}
        out.append({
            'date': r.get('date'),
            'name': r.get('name'),
            'nutrition_note': nutrition,
            'tss': s.get('tss'),
            'decoupling_pct': s.get('decoupling_pct'),
            'avg_cadence': s.get('avg_cadence'),
            'distance_km': s.get('distance_km'),
            'elev_gain_m': s.get('elev_gain_m'),
        })
    return out


# ───────── DB build/refresh ─────────
def build_db(base_dir, today=None):
    """전체 DB 빌드."""
    rides = [load_ride(rd) for rd in find_ride_dirs(base_dir)]

    # 인덱스만 유지 + 핵심 지표만 (큰 climbs 배열은 별도)
    summaries = []
    for r in rides:
        s = r.get('analysis', {}).get('summary', {}) or {}
        summaries.append({
            'name': r.get('name'),
            'date': r.get('date'),
            'distance_km': s.get('distance_km'),
            'elev_gain_m': s.get('elev_gain_m'),
            'elapsed_h': s.get('elapsed_h'),
            'moving_h': s.get('moving_h'),
            'avg_speed_kmh': s.get('avg_speed_kmh'),
            'avg_power_w': s.get('avg_power_w'),
            'np_w': s.get('np_w'),
            'if_': s.get('if_'),
            'tss': s.get('tss'),
            'avg_hr': s.get('avg_hr'),
            'avg_cadence': s.get('avg_cadence'),
            'decoupling_pct': s.get('decoupling_pct'),
        })

    db = {
        'rider': RIDER,
        'a_race': A_RACE,
        'updated_utc': datetime.now(timezone.utc).isoformat(),
        'rides': summaries,
        'pmc': compute_pmc(rides, today=today),
        'weekly_loads': weekly_loads(rides),
        'climb_records': climb_records(rides),
        'seorak_readiness': seorak_readiness(rides),
        'nutrition_log': nutrition_efficiency(rides),
        'ftp_trend': ftp_trend(rides, RIDER['weight_kg'], manual_ftp=RIDER['ftp_w']),
    }
    return db


def save_db(base_dir, db):
    p = Path(base_dir) / 'athlete_db.json'
    p.write_text(json.dumps(db, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return p


def load_db(base_dir):
    p = Path(base_dir) / 'athlete_db.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return None


def refresh_db(base_dir):
    """전체 다시 빌드 + 저장."""
    db = build_db(base_dir)
    p = save_db(base_dir, db)
    return db, p


def main():
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "/Volumes/McMini4TB/GoodleDrive_JYJ/JYJ/04_Cycling/Gran Fondo"
    db, p = refresh_db(base)
    print(f"  ✓ athlete_db.json: {p}")
    print(f"    rides: {len(db['rides'])}개")
    print(f"    PMC days: {len(db['pmc'])}일")
    print(f"    climb records: {len(db['climb_records'])}개 코스")
    print(f"    seorak readiness: {db['seorak_readiness']['overall_pct']}%")
    ft = db.get('ftp_trend') or {}
    if ft.get('current_estimated_ftp_w'):
        delta = ft.get('manual_vs_estimated_delta', 0) or 0
        sign = '+' if delta > 0 else ''
        print(f"    FTP 추정: {ft['current_estimated_ftp_w']}W ({ft['current_estimated_w_per_kg']} W/kg) "
              f"vs 수동 {ft['manual_ftp_w']}W ({sign}{delta}W)")
    if db.get('pmc'):
        latest = db['pmc'][-1]
        print(f"    오늘 ACWR: {latest['acwr']} [{latest['acwr_state']}] · TSB {latest['tsb']:+.1f}")
    print()
    print("  최근 라이딩 5개:")
    for r in db['rides'][-5:]:
        print(f"    {r['date']} {r['name']:30s}  TSS {r['tss']:>4}  IF {r.get('if_',0):>4}  Dec {r.get('decoupling_pct','?')}%")


if __name__ == '__main__':
    main()
