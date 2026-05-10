#!/usr/bin/env python3
"""4-stage 페이싱 분석 카드 — 라이딩 전반 흐름을 4개 동등 구간으로 보여줌.

기존 best/fade climb 2개 단순 비교를 대체.
각 stage 구간의 NP/IF/HR/cadence 표시 → 시간 흐름에 따른 fade 패턴 시각화.

사용법:
    python3 build_4stage_card.py <ride_dir> [output_png]
"""
import sys
import json
from pathlib import Path
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SCRIPT_DIR = Path(__file__).parent
FD = SCRIPT_DIR.parent / 'intro_video' / 'fonts'
F_REG  = str(FD / 'NanumGothic.ttf')
F_BOLD = str(FD / 'NanumGothicBold.ttf')
F_EX   = str(FD / 'NanumGothicExtraBold.ttf')


def f(p, s):
    return ImageFont.truetype(p, s)


BG       = (18, 24, 38)
PANEL_BG = (28, 36, 52)
ACCENT   = (255, 184, 76)
ACCENT2  = (102, 222, 178)
ACCENT3  = (255, 107, 107)
ACCENT4  = (140, 200, 255)
TEXT     = (245, 248, 252)
SUB      = (170, 185, 210)
DIM      = (90, 105, 130)
GRID     = (40, 55, 80)


def hms(s):
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:01d}:{m:02d}:{sec:02d}"


def stage_stats(records, t_start, t_end, ftp, lthr):
    """t_start~t_end 구간의 NP/IF/HR/cadence 계산.
    records: fit records [{'timestamp_s', 'power', 'hr', 'cadence', ...}]
    """
    seg = [r for r in records if t_start <= r.get('timestamp_s', 0) <= t_end]
    if not seg:
        return None
    powers = [r.get('power', 0) or 0 for r in seg]
    hrs = [r.get('hr', 0) or 0 for r in seg if r.get('hr')]
    cads = [r.get('cadence', 0) or 0 for r in seg if r.get('cadence')]
    avg_p = sum(powers) / len(powers) if powers else 0
    # NP (rolling 30s avg, ** 4, mean, ** 0.25)
    if len(powers) >= 30:
        rolling = []
        for i in range(len(powers) - 29):
            rolling.append(sum(powers[i:i+30]) / 30)
        np = (sum(r ** 4 for r in rolling) / len(rolling)) ** 0.25 if rolling else avg_p
    else:
        np = avg_p
    if_ = np / ftp if ftp else 0
    avg_hr = sum(hrs) / len(hrs) if hrs else 0
    avg_cad = sum(cads) / len(cads) if cads else 0
    return {
        'duration_s': t_end - t_start,
        'avg_power': round(avg_p),
        'np': round(np),
        'if': round(if_, 3),
        'avg_hr': round(avg_hr),
        'avg_cad': round(avg_cad),
        'hr_pct_lthr': round(avg_hr / lthr * 100) if lthr else 0,
    }


def load_fit_records(ride_dir):
    """fit 파일에서 timestamp/power/hr/cadence 추출."""
    from fitparse import FitFile
    fits = list(Path(ride_dir).glob('*.fit')) + list(Path(ride_dir).glob('*.FIT'))
    if not fits:
        return []
    fit = FitFile(str(fits[0]))
    recs = []
    first_ts = None
    for r in fit.get_messages('record'):
        d = {f.name: f.value for f in r}
        ts = d.get('timestamp')
        if ts is None:
            continue
        if first_ts is None:
            first_ts = ts
        recs.append({
            'timestamp_s': (ts - first_ts).total_seconds(),
            'power': d.get('power'),
            'hr': d.get('heart_rate'),
            'cadence': d.get('cadence'),
            'distance': d.get('distance'),
            'speed': d.get('speed') or d.get('enhanced_speed'),
        })
    return recs


def draw_stage_panel(d, x0, y0, w, h, idx, name, t_start, t_end, stats, total_s):
    """단일 stage 패널."""
    d.rounded_rectangle([x0, y0, x0+w, y0+h], radius=12, fill=PANEL_BG, outline=GRID)
    # 헤더
    colors = [ACCENT4, ACCENT, ACCENT3, ACCENT2]  # 워밍업/빌드/피크/마무리
    col = colors[idx-1]
    d.rectangle([x0, y0, x0+w, y0+50], fill=col)
    d.text((x0+18, y0+12), f"STAGE {idx}  ·  {name}", font=f(F_EX, 22), fill=BG)
    # 시각
    d.text((x0+18, y0+62), f"{hms(t_start)} ~ {hms(t_end)}  ({(t_end-t_start)//60:.0f}분)",
           font=f(F_REG, 14), fill=SUB)

    if not stats:
        d.text((x0+18, y0+h//2), "데이터 없음", font=f(F_REG, 18), fill=DIM)
        return

    # 4개 지표 (NP / IF / HR / Cadence)
    metrics = [
        ('NP',       f"{stats['np']:>3d}W",            ACCENT),
        ('IF',       f"{stats['if']:.2f}",             ACCENT3),
        ('HR',       f"{stats['avg_hr']:>3d}",         ACCENT4),
        ('Cad',      f"{stats['avg_cad']:>3d}rpm",     ACCENT2),
    ]
    metric_y = y0 + 100
    for i, (label, val, col) in enumerate(metrics):
        my = metric_y + i * 50
        d.text((x0+24, my+6), label, font=f(F_REG, 16), fill=SUB)
        d.text((x0+w-130, my), val, font=f(F_BOLD, 28), fill=col)

    # HR %LTHR 추가
    if stats.get('hr_pct_lthr'):
        d.text((x0+24, y0+h-32), f"({stats['hr_pct_lthr']}% LTHR)",
               font=f(F_REG, 13), fill=DIM)


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_4stage_card.py <ride_dir> [output_png]")
    ride_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ride_dir / 'output_videos' / '_cards' / 'card_4stage_overview.png'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    A = json.loads((ride_dir / '_analysis.json').read_text(encoding='utf-8'))
    s = A.get('summary', {})
    rider = A.get('rider', {})
    ftp = rider.get('ftp_w', 180)
    lthr = rider.get('lthr', 168)

    # 라이딩 총 길이 (FIT 기준 elapsed)
    elapsed = s.get('elapsed_h', '0:0:0')
    try:
        h, m, sec = map(int, elapsed.split(':'))
        total_s = h*3600 + m*60 + sec
    except Exception:
        total_s = 14400  # 4h default

    # 4 stage 균등 분할
    stages = [
        (1, '워밍업',  0,            total_s/4),
        (2, '빌드업',  total_s/4,    total_s/2),
        (3, '피크',    total_s/2,    total_s*3/4),
        (4, '마무리',  total_s*3/4,  total_s),
    ]

    # FIT records 로드
    records = load_fit_records(ride_dir)
    print(f"  ✓ FIT records {len(records)}개 로드")

    # 각 stage 통계
    stage_data = []
    for idx, name, t0, t1 in stages:
        stats = stage_stats(records, t0, t1, ftp, lthr)
        stage_data.append((idx, name, t0, t1, stats))

    # 카드 그리기
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # 헤더
    d.text((60, 40), "📊 4-STAGE 페이싱 분석 — 라이딩 전반 흐름",
           font=f(F_EX, 38), fill=ACCENT)
    d.text((60, 95),
           "best vs fade 단순 비교 대신 시간 흐름에 따른 페이스/심박/케이던스 변화 추적",
           font=f(F_REG, 18), fill=SUB)
    d.line([(60, 130), (W-60, 130)], fill=ACCENT, width=2)

    # 4 패널 가로 배치
    PW = (W - 60*5) // 4
    PH = 480
    PY = 170
    for i, (idx, name, t0, t1, stats) in enumerate(stage_data):
        px = 60 + i * (PW + 60)
        draw_stage_panel(d, px, PY, PW, PH, idx, name, t0, t1, stats, total_s)

    # 하단: NP/IF 변화 흐름 (전반 vs 후반)
    valid = [sd for sd in stage_data if sd[4]]
    if len(valid) >= 2:
        np_vals = [sd[4]['np'] for sd in valid]
        if_vals = [sd[4]['if'] for sd in valid]
        first_half_avg_np = sum(np_vals[:2]) / 2
        second_half_avg_np = sum(np_vals[2:]) / 2 if len(np_vals) >= 3 else np_vals[-1]
        fade_pct = (second_half_avg_np - first_half_avg_np) / first_half_avg_np * 100 if first_half_avg_np else 0

        d.text((60, 700), "🔥 후반 페이드 검출", font=f(F_EX, 28), fill=ACCENT)
        d.text((60, 745),
               f"전반(stage 1-2) NP 평균 {first_half_avg_np:.0f}W  →  후반(stage 3-4) NP 평균 {second_half_avg_np:.0f}W",
               font=f(F_REG, 22), fill=TEXT)
        msg_col = ACCENT3 if fade_pct < -5 else (ACCENT if -5 <= fade_pct < 0 else ACCENT2)
        d.text((60, 785),
               f"{'+' if fade_pct >= 0 else ''}{fade_pct:.1f}% — " +
               ("후반 강하게 유지" if fade_pct >= 0 else
                ("약한 fade — 안정적" if fade_pct > -5 else
                 "fade 감지 — 영양·페이싱 점검 필요")),
               font=f(F_BOLD, 26), fill=msg_col)

    # 디커플링/IF 정보 우하단
    d.text((60, 870), "라이딩 전체", font=f(F_REG, 14), fill=DIM)
    d.text((60, 895),
           f"TSS {s.get('tss',0)} · IF {s.get('if_',0)} · 디커플링 {s.get('decoupling_pct',0)}%",
           font=f(F_BOLD, 22), fill=ACCENT)
    half = A.get('half_split') or {}
    if half:
        d.text((60, 935),
               f"half_split verdict: {half.get('verdict','?')}",
               font=f(F_REG, 16), fill=SUB)

    # 메모: 신체 신호 (ride_meta.json 이슈)
    meta_path = ride_dir / 'ride_meta.json'
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text(encoding='utf-8'))
            issue = m.get('이슈')
            if issue:
                d.text((W-700, 870), "⚠ 신체 신호", font=f(F_REG, 14), fill=ACCENT3)
                d.text((W-700, 895), f"{issue.get('type','')}",
                       font=f(F_BOLD, 20), fill=ACCENT3)
                d.text((W-700, 925), f"trigger: {issue.get('trigger','')[:60]}",
                       font=f(F_REG, 14), fill=DIM)
        except Exception:
            pass

    img.save(out_path, optimize=True)
    print(f"  ✓ {out_path}")


if __name__ == '__main__':
    main()
