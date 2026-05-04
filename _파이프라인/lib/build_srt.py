"""자동 분석 결과(_analysis.json) + 영상 매칭(_videos.json) → coaching.srt 생성."""
import sys, json
from pathlib import Path
from datetime import datetime, timedelta

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def fmt_srt(s):
    if s < 0: s = 0
    h = int(s//3600); m = int((s%3600)//60); ss = int(s%60); ms = int((s-int(s))*1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"

def main(ride_dir):
    analysis = load(Path(ride_dir)/'_analysis.json')
    videos = load(Path(ride_dir)/'_videos.json')

    ride_start = datetime.fromisoformat(analysis['ride_start_utc'])
    rider, summ = analysis['rider'], analysis['summary']

    rv = videos['ride_videos_chronological']
    vid_starts, cum = [], 0
    for v in rv:
        st = datetime.fromisoformat(v['start_utc'])
        vid_starts.append({'utc_start': st, 'utc_end': st + timedelta(seconds=v['duration_s']),
                           'cum_start_s': cum, 'cum_end_s': cum + v['duration_s']})
        cum += v['duration_s']
    total_vs = cum

    def ride_to_video(rs):
        target = ride_start + timedelta(seconds=rs)
        for v in vid_starts:
            if v['utc_start'] <= target <= v['utc_end']:
                return v['cum_start_s'] + (target - v['utc_start']).total_seconds()
        return None

    cues = []
    cues.append((5, 9, [
        f"오늘의 라이딩: {summ['distance_km']} km / +{summ['elev_gain_m']:,}m ({summ['elev_per_km']} m/km)",
        f"체중 {rider['weight_kg']}kg · FTP {rider['ftp_w']}W ({rider['w_per_kg']} W/kg) · 그란폰도 시뮬레이션",
    ]))

    for c in analysis['climbs']:
        vt = ride_to_video(c['ride_elapsed_start_s'])
        if vt is None: continue
        idx = c['index']
        is_best = analysis.get('best_climb') and analysis['best_climb']['index'] == idx
        is_fade = analysis.get('fade_climb') and analysis['fade_climb']['index'] == idx
        ftp = rider['ftp_w']; ifp = c['avg_power_w']/ftp

        if is_best:
            lines = [
                f"[Climb #{idx} 진입] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km — 베스트 페이싱 후보",
                f"VAM {c['vam_m_per_h']:.0f} m/h, 평균 {c['avg_power_w']:.0f}W (IF {ifp:.2f})",
                "이 페이스를 몸이 기억하도록 집중",
            ]
        elif is_fade:
            best = analysis.get('best_climb')
            vam_drop = (1 - c['vam_m_per_h']/best['vam_m_per_h'])*100 if best else 0
            lines = [
                f"[Climb #{idx} 진입] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km — 후반 시험",
                f"VAM {c['vam_m_per_h']:.0f} (베스트 #{best['index']} 대비 -{vam_drop:.0f}%)" if best else f"VAM {c['vam_m_per_h']:.0f}",
                "후반 누적 피로 — 페이싱 절제 필요",
            ]
        else:
            lines = [
                f"[Climb #{idx}] {c['avg_grade_pct']:.1f}% × {c['distance_m']/1000:.1f}km, +{c['elev_gain_m']:.0f}m",
                f"평균 {c['avg_power_w']:.0f}W (IF {ifp:.2f}) · HR {c['avg_hr']:.0f}",
            ]
        cues.append((vt, 8, lines))

    # 종합 + 액션
    cues.append((max(0, total_vs - 25), 11, [
        "[오늘의 종합 평가]",
        f"TSS {summ['tss']} · IF {summ['if_']} · VI {summ['vi']}",
        f"디커플링 {summ['decoupling_pct']}% · 회복 권장 {72 if summ['tss']>250 else 48}h",
    ]))
    cues.append((max(0, total_vs - 12), 11, [
        "[다음 라이딩 액션]",
        "1. 출발 30분 전 탄수 80g  2. 시간당 60g 분할 보급",
        "3. 케이던스 80+ 유지 (근피로 가속 방지)",
    ]))

    cues.sort(key=lambda c: c[0])
    adjusted, last_end = [], 0
    for vt, dur, lines in cues:
        if vt < last_end + 0.5: vt = last_end + 0.5
        adjusted.append((vt, dur, lines)); last_end = vt + dur

    out = []
    for i, (vt, dur, lines) in enumerate(adjusted, 1):
        out.extend([str(i), f"{fmt_srt(vt)} --> {fmt_srt(vt+dur)}"] + lines + [""])

    srt_path = Path(ride_dir)/'coaching.srt'
    srt_path.write_text("\n".join(out), encoding='utf-8')
    print(f"  ✓ {len(adjusted)}개 큐 → {srt_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit("사용법: python3 build_srt.py <ride_dir>")
    main(sys.argv[1])
