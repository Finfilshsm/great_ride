"""Seorak Granfondo 208km 코스 모형 + 페이스 환산 시뮬.

기능:
1. GPX 파싱 — Seorak_Granfondo-208km.gpx에서 코스 프로파일·waypoints 추출
2. 컷오프·피드존 자동 인식
3. 오늘 라이딩 데이터로 Seorak 완주 시뮬 (디커플링 보정 포함)

GPX 위치: <repo 부모폴더>/Seorak_Granfondo-208km.gpx (cycling-tools와 형제)
"""
import re
import math
import xml.etree.ElementTree as ET
from pathlib import Path


# ───────── 코스 상수 ─────────

SEORAK = {
    'name': 'Seorak Granfondo 208km',
    'date': '2026-06-20',
    'distance_km': 208,
    'elev_gain_m': 3800,
    'cutoff_1_h': 4.0,         # 12:00 - 08:00 start
    'cutoff_1_km': 82,
    'cutoff_2_h': 7.67,        # 15:40
    'cutoff_2_km': 167,
    'target_finish_h': 10.0,   # 사용자 목표
}


# ───────── IF ↔ 지속시간 (Coggan 표준 곡선) ─────────

_IF_DURATION_TABLE = [
    (0.95, 1.0),
    (0.90, 2.0),
    (0.85, 4.0),
    (0.80, 5.5),
    (0.75, 7.0),
    (0.70, 9.0),
    (0.65, 12.0),
    (0.60, 18.0),
    (0.55, 24.0),
]


def if_to_max_duration_h(if_):
    """주어진 IF로 지속 가능한 최대 시간 (h). 보간."""
    if not if_ or if_ <= 0:
        return 0
    if if_ >= 0.95:
        return 1.0
    for i in range(len(_IF_DURATION_TABLE) - 1):
        ifa, ha = _IF_DURATION_TABLE[i]
        ifb, hb = _IF_DURATION_TABLE[i + 1]
        if ifa >= if_ >= ifb:
            # 선형 보간
            ratio = (ifa - if_) / (ifa - ifb) if ifa != ifb else 0
            return round(ha + (hb - ha) * ratio, 1)
    return _IF_DURATION_TABLE[-1][1]


def duration_to_target_if(h):
    """완주 목표 시간 → 권장 IF (역방향 보간)."""
    if h <= 1:
        return 0.95
    for i in range(len(_IF_DURATION_TABLE) - 1):
        ifa, ha = _IF_DURATION_TABLE[i]
        ifb, hb = _IF_DURATION_TABLE[i + 1]
        if ha <= h <= hb:
            ratio = (h - ha) / (hb - ha) if ha != hb else 0
            return round(ifa + (ifb - ifa) * ratio, 3)
    return _IF_DURATION_TABLE[-1][0]


# ───────── GPX 파싱 ─────────

GPX_NS = '{http://www.topografix.com/GPX/1/1}'


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _smooth_elevation(eles, window=5):
    """가민/Strava 표준 평활화: 5점 이동 평균. GPS 기압 노이즈 제거."""
    if len(eles) < window:
        return eles[:]
    half = window // 2
    out = []
    for i in range(len(eles)):
        s = max(0, i - half)
        e = min(len(eles), i + half + 1)
        out.append(sum(eles[s:e]) / (e - s))
    return out


def _compute_elev_gain(eles, threshold_m=3.0):
    """평활화된 ele 시퀀스에서 임계값 기반 누적 상승.

    가민 방식: 마지막 "유의미한" 고도점 이후 +threshold_m 이상 올라간 누적만 카운트.
    노이즈 ±2m 진동은 무시 → 실제 측정 신호와 매칭.
    """
    if len(eles) < 2:
        return 0.0
    gain = 0.0
    last_anchor = eles[0]
    pending = 0.0
    for i in range(1, len(eles)):
        d = eles[i] - last_anchor
        if d > 0:
            if d >= threshold_m:
                gain += d
                last_anchor = eles[i]
        else:
            # 내려가면 anchor 갱신 (반대 방향 노이즈 방지)
            if abs(d) >= threshold_m:
                last_anchor = eles[i]
    return gain


def _map_waypoint_forward(waypoints_raw, trkpts):
    """closed-loop 코스에서 waypoint를 진행 순서대로 매핑.

    각 waypoint의 거리를 desc/name 텍스트에서 우선 추출 (예: '1st(33km)', '147km')
    실패 시 forward-greedy nearest 매핑 (이미 매핑된 km 이후 trkpt 중 nearest).
    """
    pat_km = re.compile(r'(\d+)\s*km', re.IGNORECASE)

    def km_from_text(*texts):
        for t in texts:
            if not t:
                continue
            m = pat_km.search(t)
            if m:
                return float(m.group(1))
        return None

    out = []
    last_km = 0.0
    for wpt in waypoints_raw:
        # 1) 텍스트에서 km 추출 시도
        km = km_from_text(wpt.get('name'), wpt.get('desc'))
        if km is not None:
            out.append({**wpt, 'km': km, 'mapped_by': 'text'})
            continue
        # 2) forward-greedy nearest (last_km 이후만)
        candidates = [t for t in trkpts if t['km'] >= last_km - 0.5]
        if not candidates:
            candidates = trkpts
        best = min(candidates, key=lambda t: _haversine_m(wpt['lat'], wpt['lon'], t['lat'], t['lon']))
        out.append({**wpt, 'km': best['km'], 'mapped_by': 'geo'})
        last_km = best['km']

    out.sort(key=lambda w: w['km'])
    return out


def parse_gpx(gpx_path, smooth_window=5, gain_threshold_m=3.0):
    """GPX → {trkpts, waypoints, total_km, elev_gain_m}.

    elevation gain은 가민 표준 방식으로 평활화 + 임계값 필터 적용.
    """
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()

    raw = []
    for trkpt in root.iter(f'{GPX_NS}trkpt'):
        lat = float(trkpt.attrib['lat'])
        lon = float(trkpt.attrib['lon'])
        ele_el = trkpt.find(f'{GPX_NS}ele')
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0
        raw.append({'lat': lat, 'lon': lon, 'ele': ele})

    cum = 0
    raw_eles = [p['ele'] for p in raw]
    smooth_eles = _smooth_elevation(raw_eles, window=smooth_window)

    trkpts = []
    for i, p in enumerate(raw):
        if i > 0:
            cum += _haversine_m(raw[i-1]['lat'], raw[i-1]['lon'], p['lat'], p['lon'])
        trkpts.append({
            'km': round(cum / 1000, 4),
            'ele': round(smooth_eles[i], 1),
            'ele_raw': p['ele'],
            'lat': p['lat'],
            'lon': p['lon'],
        })

    elev_gain = _compute_elev_gain(smooth_eles, threshold_m=gain_threshold_m)

    raw_wpts = []
    for wpt in root.iter(f'{GPX_NS}wpt'):
        lat = float(wpt.attrib['lat'])
        lon = float(wpt.attrib['lon'])
        name_el = wpt.find(f'{GPX_NS}name')
        desc_el = wpt.find(f'{GPX_NS}desc')
        raw_wpts.append({
            'name': name_el.text if name_el is not None else '',
            'desc': desc_el.text if desc_el is not None else '',
            'lat': lat,
            'lon': lon,
        })
    waypoints = _map_waypoint_forward(raw_wpts, trkpts)

    return {
        'trkpts': trkpts,
        'waypoints': waypoints,
        'total_km': round(trkpts[-1]['km'], 2) if trkpts else 0,
        'elev_gain_m': round(elev_gain, 1),
    }


def detect_climbs_from_trkpts(trkpts, win_m=500, climb_grade=2.5, min_gain=80, min_length=600, gap_m=400):
    """GPX trkpt 시퀀스에서 climb 검출. build_analysis의 detect_climbs와 동일 로직."""
    if not trkpts:
        return []
    pts = [{'i': i, 'd': p['km'] * 1000, 'a': p['ele']} for i, p in enumerate(trkpts)]

    segments = []
    j = 0
    for k in range(len(pts)):
        while pts[k]['d'] - pts[j]['d'] > win_m and j < k:
            j += 1
        length = pts[k]['d'] - pts[j]['d']
        if length < win_m * 0.6:
            continue
        gain = pts[k]['a'] - pts[j]['a']
        grade = gain / length * 100 if length > 0 else 0
        segments.append({
            'climbing': grade >= climb_grade,
            'd_start': pts[j]['d'], 'd_end': pts[k]['d'],
            'a_start': pts[j]['a'], 'a_end': pts[k]['a'],
        })

    groups = []
    cur = None
    last_d = -1e9
    for s in segments:
        if s['climbing']:
            if cur is None or s['d_start'] - last_d > gap_m:
                if cur is not None:
                    groups.append(cur)
                cur = {**s}
            else:
                cur['d_end'] = s['d_end']
                cur['a_end'] = s['a_end']
            last_d = s['d_end']
    if cur is not None:
        groups.append(cur)

    climbs = []
    for g in groups:
        length = g['d_end'] - g['d_start']
        gain = g['a_end'] - g['a_start']
        if gain < min_gain or length < min_length:
            continue
        climbs.append({
            'start_km': round(g['d_start'] / 1000, 2),
            'end_km': round(g['d_end'] / 1000, 2),
            'distance_m': round(length, 1),
            'elev_gain_m': round(gain, 1),
            'avg_grade_pct': round(gain / length * 100, 2) if length else 0,
        })
    for i, c in enumerate(climbs, 1):
        c['index'] = i
    # 카테고리는 build_analysis.categorize_climb 같은 로직 (점수 = 거리×grade)
    for c in climbs:
        score = c['distance_m'] * c['avg_grade_pct']
        if score >= 80000: c['category'] = 'HC'
        elif score >= 64000: c['category'] = 'Cat1'
        elif score >= 32000: c['category'] = 'Cat2'
        elif score >= 16000: c['category'] = 'Cat3'
        elif score >= 8000: c['category'] = 'Cat4'
        else: c['category'] = 'NC'
    return climbs


def find_gpx(base_dir):
    """base_dir에서 Seorak GPX 자동 탐색."""
    base = Path(base_dir)
    for p in base.glob('Seorak*.gpx'):
        return p
    for p in base.glob('*Seorak*.gpx'):
        return p
    for p in base.glob('*.gpx'):
        return p
    return None


def load_seorak_course(base_dir):
    """캐시된 결과 또는 GPX 파싱."""
    gpx = find_gpx(base_dir)
    if not gpx:
        return None
    parsed = parse_gpx(gpx)
    parsed['climbs'] = detect_climbs_from_trkpts(parsed['trkpts'])
    parsed['gpx_path'] = str(gpx)
    return parsed


# ───────── Seorak 시뮬 ─────────

def parse_h_str(s):
    """'4:35:04' → 4.5844 (h)."""
    if not s or not isinstance(s, str):
        return 0
    try:
        h, m, sec = s.split(':')
        return int(h) + int(m) / 60 + int(sec) / 3600
    except Exception:
        return 0


def seorak_simulation(today_summary, race=None):
    """오늘 라이딩 데이터로 Seorak 완주 시뮬.

    오늘 데이터로 다음을 산출:
    - 같은 페이스 유지 시 Seorak 완주 시간 (디커플링 무보정)
    - 디커플링 보정 후 예상 완주 시간
    - 컷오프 1·2 통과 가능성
    - 10시간 완주 권장 IF
    - 오늘 IF로 지속 가능한 최대 시간 (Coggan 모델)
    - 종합 가능성 % (5차원 평균)
    """
    race = race or SEORAK
    s = today_summary

    avg_kmh = s.get('avg_speed_kmh', 0) or 0
    if_ = s.get('if_', 0) or 0
    np_w = s.get('np_w', 0) or 0
    decoupling = s.get('decoupling_pct', 0) or 0
    moving_h = parse_h_str(s.get('moving_h'))

    # 1) 같은 페이스 유지 가정 — Seorak 완주 시간
    extrap_h = race['distance_km'] / avg_kmh if avg_kmh > 0 else None

    # 2) 디커플링 보정
    # 가정: 오늘 라이딩이 X시간이고 디커플링 D%였으면, Seorak에서 시간 비례로 추가 페이드.
    # Seorak 시간이 오늘의 R배라면 디커플링 페널티도 R배 (선형 보수적 추정).
    adjusted_h = None
    if extrap_h and moving_h > 0 and decoupling > 0:
        scale = extrap_h / moving_h
        # 후반 절반에 페널티 50% 적용 → 평균 페이스 손실 ≈ decoupling × scale × 0.5 / 100
        penalty = decoupling * scale * 0.5 / 100
        # 페이스 손실분만큼 시간 늘어남
        adjusted_h = round(extrap_h * (1 + penalty), 2)
        extrap_h = round(extrap_h, 2)
    elif extrap_h:
        extrap_h = round(extrap_h, 2)
        adjusted_h = extrap_h

    # 3) 컷오프 통과
    cutoff_1_pace = race['cutoff_1_km'] / race['cutoff_1_h']  # km/h
    cutoff_2_pace = race['cutoff_2_km'] / race['cutoff_2_h']
    target_pace = race['distance_km'] / race['target_finish_h']

    cutoff_1_pass = avg_kmh >= cutoff_1_pace
    cutoff_2_pass = avg_kmh >= cutoff_2_pace
    target_pass = avg_kmh >= target_pace

    # 4) IF ↔ 지속시간
    target_if = duration_to_target_if(race['target_finish_h'])
    today_max_h = if_to_max_duration_h(if_) if if_ > 0 else 0
    # 오늘 NP를 Seorak 페이스(target_if)로 환산 — FTP 곱이 필요
    # NP_seorak_target = ftp × target_if (직접 FTP 필요, 여기선 if_ 비교만)

    # 5) 종합 가능성 (3차원 평균)
    speed_pct = min(100, (avg_kmh / target_pace) * 100) if avg_kmh > 0 else 0
    # 디커플링: 8% 이하 = 100점, 20% 이상 = 0점
    decoupling_score = max(0, min(100, (20 - decoupling) / 12 * 100))
    # 지속시간: 오늘 IF로 10시간 가능성
    duration_pct = min(100, today_max_h / race['target_finish_h'] * 100) if today_max_h else 0

    feasibility = round((speed_pct + decoupling_score + duration_pct) / 3)

    # 가장 큰 갭 식별
    gaps = [
        ('속도', round(speed_pct), target_pace, avg_kmh, 'km/h'),
        ('디커플링', round(decoupling_score), 8, decoupling, '%'),
        ('지속시간', round(duration_pct), race['target_finish_h'], today_max_h, 'h'),
    ]
    biggest_gap = min(gaps, key=lambda g: g[1])

    return {
        'race': race['name'],
        'race_date': race['date'],
        'target_finish_h': race['target_finish_h'],
        'extrap_finish_h': extrap_h,
        'adjusted_finish_h': adjusted_h,
        'cutoff_1_pass': cutoff_1_pass,
        'cutoff_2_pass': cutoff_2_pass,
        'target_pass': target_pass,
        'cutoff_1_pace_kmh': round(cutoff_1_pace, 1),
        'cutoff_2_pace_kmh': round(cutoff_2_pace, 1),
        'target_pace_kmh': round(target_pace, 1),
        'today_avg_kmh': avg_kmh,
        'today_if': if_,
        'today_max_duration_h': today_max_h,
        'target_if_for_10h': target_if,
        'today_decoupling_pct': decoupling,
        'feasibility_pct': feasibility,
        'biggest_gap': {
            'dim': biggest_gap[0],
            'score_pct': biggest_gap[1],
            'target': biggest_gap[2],
            'current': biggest_gap[3],
            'unit': biggest_gap[4],
        },
        'dimension_scores': {
            'speed': round(speed_pct),
            'decoupling': round(decoupling_score),
            'duration': round(duration_pct),
        },
    }


# ───────── TDF 10년 trajectory ─────────

TDF_TARGET_WPK = 4.5  # Pro/Elite TDF 입문선
TDF_PROJECT_START_YEAR = 2026
TDF_PROJECT_TARGET_YEAR = 2036
TDF_MILESTONES = [
    (2.5, 'Cat 4-5 입문'),
    (3.0, 'Cat 3'),
    (3.5, 'Cat 2'),
    (4.0, 'Cat 1'),
    (4.5, 'Pro/Elite (TDF 입문선)'),
    (5.5, 'TDF GC contender'),
]


def tdf_trajectory(current_wpk, ftp_trend=None, today_tss=None,
                   weight_kg=None, today_iso=None,
                   target_wpk=TDF_TARGET_WPK,
                   target_year=TDF_PROJECT_TARGET_YEAR,
                   start_year=TDF_PROJECT_START_YEAR):
    """TDF 10년 trajectory 분석 — 현재 W/kg → 4.5 W/kg(TDF 입문선)까지 진척·필요 증가율.

    `ftp_trend`는 athlete_db.json의 `ftp_trend` 객체 (rolling_30d 리스트 포함).
    추세 데이터가 있으면 실제 연간 증가율(annual_increase_actual)도 산출.
    """
    from datetime import datetime
    if not current_wpk or current_wpk <= 0:
        return None

    try:
        today = datetime.fromisoformat(today_iso) if today_iso else datetime.now()
    except Exception:
        today = datetime.now()

    years_elapsed = max(0.0, today.year - start_year + (today.month - 1) / 12)
    years_remaining = max(0.5, target_year - today.year - (today.month - 1) / 12)

    gap = max(0.0, target_wpk - current_wpk)
    annual_needed = gap / years_remaining if years_remaining > 0 else 0.0

    # 실제 연간 증가율 (rolling_30d 첫·마지막 비교 → 연환산)
    annual_actual = None
    rolling = (ftp_trend or {}).get('rolling_30d') or []
    if len(rolling) >= 2:
        try:
            first, last = rolling[0], rolling[-1]
            d0 = datetime.fromisoformat(first['date'])
            d1 = datetime.fromisoformat(last['date'])
            days = max(1, (d1 - d0).days)
            w0 = first.get('w_per_kg', 0) or 0
            w1 = last.get('w_per_kg', 0) or 0
            if w0 > 0 and w1 > 0:
                annual_actual = round((w1 - w0) * 365 / days, 3)
        except Exception:
            pass

    # 진척도 (2.0 baseline → 4.5 target)
    base_wpk = 2.0
    progress_pct = round(max(0, min(100, (current_wpk - base_wpk) / (target_wpk - base_wpk) * 100)), 1)

    # 다음 마일스톤
    next_ms = None
    for w, label in TDF_MILESTONES:
        if w > current_wpk + 1e-6:
            next_ms = (w, label)
            break
    eta_years = None
    if next_ms and annual_actual and annual_actual > 0:
        eta_years = round((next_ms[0] - current_wpk) / annual_actual, 1)

    # 상태
    if annual_actual is None:
        status = '추세 데이터 누적 중 (>2 라이딩 필요)'
    elif annual_actual <= 0:
        status = '정체 — Build 기간 늘리고 강도 점진 상향'
    elif annual_actual >= annual_needed:
        status = f'on track (+{annual_actual:+.2f} W/kg/yr ≥ 필요 +{annual_needed:.2f})'
    else:
        deficit = annual_needed - annual_actual
        status = f'behind (실제 +{annual_actual:.2f} < 필요 +{annual_needed:.2f}, Δ -{deficit:.2f})'

    # 오늘 라이딩 기여 (CTL 1일 변화 ≈ TSS / 42, fitness 누적)
    today_ctl_contrib = round((today_tss or 0) / 42, 2)

    return {
        'project': 'TDF 10년 프로젝트',
        'start_year': start_year,
        'target_year': target_year,
        'target_wpk': target_wpk,
        'target_label': 'Pro/Elite (TDF 입문선)',
        'current_wpk': round(current_wpk, 2),
        'gap_wpk': round(gap, 2),
        'years_elapsed': round(years_elapsed, 2),
        'years_remaining': round(years_remaining, 2),
        'annual_increase_needed': round(annual_needed, 3),
        'annual_increase_actual': annual_actual,
        'on_track': annual_actual is not None and annual_actual >= annual_needed,
        'status': status,
        'progress_pct': progress_pct,
        'next_milestone': {
            'wpk': next_ms[0],
            'label': next_ms[1],
            'eta_years': eta_years,
        } if next_ms else None,
        'today_tss': today_tss,
        'today_ctl_contrib_per_day': today_ctl_contrib,
        'ftp_target_w': round(target_wpk * weight_kg) if weight_kg else None,
    }


# ───────── 메인 (CLI 검증용) ─────────

def main():
    import sys
    import json
    if len(sys.argv) < 2:
        sys.exit("사용법: seorak.py <base_dir 또는 gpx_path>")
    p = Path(sys.argv[1])
    if p.is_dir():
        course = load_seorak_course(p)
    elif p.suffix.lower() == '.gpx':
        course = parse_gpx(p)
        course['climbs'] = detect_climbs_from_trkpts(course['trkpts'])
        course['gpx_path'] = str(p)
    else:
        sys.exit(f"GPX 또는 디렉터리 경로 필요: {p}")

    if not course:
        sys.exit("GPX 못 찾음")

    print(f"GPX: {course.get('gpx_path')}")
    print(f"총 거리: {course['total_km']} km")
    print(f"상승: {course['elev_gain_m']:.0f} m")
    print(f"Trkpts: {len(course['trkpts'])}개")
    print(f"\nWaypoints ({len(course['waypoints'])}):")
    for w in course['waypoints']:
        print(f"  km {w['km']:>6.2f} | {w['name']}")
    print(f"\nClimbs ({len(course['climbs'])}):")
    for c in course['climbs']:
        print(f"  #{c['index']} km {c['start_km']:>6.2f}~{c['end_km']:>6.2f} | "
              f"{c['distance_m']/1000:>4.1f}km × {c['avg_grade_pct']:>4.1f}% · "
              f"+{c['elev_gain_m']:>4.0f}m · {c['category']}")


if __name__ == '__main__':
    main()
