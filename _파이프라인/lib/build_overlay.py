"""GoPro Quik 스타일 오버레이 PNG 시퀀스 생성기 (포터블 버전)."""
import fitparse, pandas as pd, numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os, sys, math

W, H = 1280, 720
FPS = 30000/1001

def find_font():
    for c in ["/System/Library/Fonts/AppleSDGothicNeo.ttc",
              "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
              "/Library/Fonts/NanumGothic.ttf",
              "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
              "C:\\Windows\\Fonts\\malgun.ttf"]:
        if Path(c).exists(): return c
    try:
        import koreanize_matplotlib as km
        return str(Path(km.__file__).parent/'fonts'/'NanumGothicBold.ttf')
    except: return None

FONT_REG = find_font()
def f(s): return ImageFont.truetype(FONT_REG, s)

def render_overlay(FIT, OUT_DIR, DEMO_START_UTC, DEMO_DURATION):
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    F_BIG, F_MED, F_SMALL, F_LABEL, F_TITLE = f(60), f(28), f(20), f(16), f(22)

    recs = []
    for r in fitparse.FitFile(FIT).get_messages('record'):
        recs.append({fld.name: fld.value for fld in r})
    df = pd.DataFrame(recs).sort_values('timestamp').reset_index(drop=True)
    for col in ['power','heart_rate','cadence','enhanced_speed']:
        df[col] = df[col].fillna(0)
    df['enhanced_altitude'] = df['enhanced_altitude'].interpolate()
    df['ts'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC')
    df['km'] = df['distance']/1000
    df['lat'] = df['position_lat'] * (180.0/2**31)
    df['lon'] = df['position_long'] * (180.0/2**31)

    LAT_MIN, LAT_MAX = df['lat'].dropna().min(), df['lat'].dropna().max()
    LON_MIN, LON_MAX = df['lon'].dropna().min(), df['lon'].dropna().max()
    A_MIN, A_MAX = df['enhanced_altitude'].min(), df['enhanced_altitude'].max()
    KM_MAX = df['km'].max()

    MM_W, MM_H, MM_PAD = 280, 200, 16
    MM_BG = Image.new('RGBA', (MM_W, MM_H), (0,0,0,160))
    md = ImageDraw.Draw(MM_BG)
    md.rounded_rectangle([0,0,MM_W-1,MM_H-1], radius=14, outline=(255,255,255,180), width=2)
    def project(la, lo):
        x = MM_PAD + (lo-LON_MIN)/(LON_MAX-LON_MIN)*(MM_W-2*MM_PAD)
        y = MM_PAD + (LAT_MAX-la)/(LAT_MAX-LAT_MIN)*(MM_H-2*MM_PAD)
        return x, y
    pts = [project(la, lo) for la, lo in zip(df['lat'], df['lon']) if not (pd.isna(la) or pd.isna(lo))]
    md.line(pts, fill=(255,209,102,200), width=2)
    md.text((10, MM_H-22), "ROUTE", fill=(255,255,255,180), font=F_LABEL)

    EP_W, EP_H = 380, 110
    EP_BG = Image.new('RGBA', (EP_W, EP_H), (0,0,0,160))
    ed = ImageDraw.Draw(EP_BG)
    ed.rounded_rectangle([0,0,EP_W-1,EP_H-1], radius=12, outline=(255,255,255,180), width=2)
    def ep_xy(km, a):
        x = 12 + km/KM_MAX*(EP_W-24)
        y = 28 + (1-(a-A_MIN)/(A_MAX-A_MIN))*(EP_H-40)
        return x, y
    ep_pts = [ep_xy(k,a) for k,a in zip(df['km'], df['enhanced_altitude']) if not pd.isna(a)]
    ed.polygon(ep_pts + [(EP_W-12, EP_H-12), (12, EP_H-12)], fill=(120,180,255,90))
    ed.line(ep_pts, fill=(120,180,255,220), width=2)
    ed.text((12, 6), "고도 프로파일", fill=(255,255,255,200), font=F_LABEL)

    def gauge(d, cx, cy, r, val, vmax, label, unit, col):
        d.arc([cx-r,cy-r,cx+r,cy+r], 180, 360, fill=(255,255,255,80), width=8)
        pct = max(0, min(1, val/vmax))
        d.arc([cx-r,cy-r,cx+r,cy+r], 180, 180+180*pct, fill=col, width=8)
        txt = f"{int(round(val))}"
        bb = d.textbbox((0,0), txt, font=F_BIG)
        d.text((cx-(bb[2]-bb[0])/2, cy-(bb[3]-bb[1])/2-12), txt, fill=(255,255,255,255), font=F_BIG)
        bb = d.textbbox((0,0), unit, font=F_SMALL); d.text((cx-(bb[2]-bb[0])/2, cy+22), unit, fill=col, font=F_SMALL)
        bb = d.textbbox((0,0), label, font=F_LABEL); d.text((cx-(bb[2]-bb[0])/2, cy+50), label, fill=(255,255,255,180), font=F_LABEL)

    N = int(round(DEMO_DURATION * FPS))
    print(f"Rendering {N} frames to {OUT_DIR}")
    for idx in range(N):
        t = idx/FPS
        target = DEMO_START_UTC + timedelta(seconds=t)
        i = (df['ts']-target).abs().idxmin()
        rec = df.iloc[i]
        speed = rec['enhanced_speed']*3.6
        power, hr, cad = rec['power'], rec['heart_rate'], rec['cadence']
        grade = 0.0
        if i>30:
            d_alt = df['enhanced_altitude'].iloc[i]-df['enhanced_altitude'].iloc[i-30]
            d_dist = df['distance'].iloc[i]-df['distance'].iloc[i-30]
            if d_dist>1: grade = d_alt/d_dist*100

        img = Image.new('RGBA', (W,H), (0,0,0,0))
        d = ImageDraw.Draw(img)
        px, py, pw, ph = 20, H-200, 720, 180
        d.rounded_rectangle([px,py,px+pw,py+ph], radius=18, fill=(0,0,0,150), outline=(255,255,255,180), width=2)
        sp = pw/4; gy = py+90
        gauge(d, px+sp*0.5, gy, 50, speed, 60, "SPEED", "km/h", (102,255,178,255))
        gauge(d, px+sp*1.5, gy, 50, power, 400, "POWER", "W", (255,107,107,255))
        gauge(d, px+sp*2.5, gy, 50, hr, 200, "HEART", "bpm", (255,170,77,255))
        gauge(d, px+sp*3.5, gy, 50, cad, 120, "CAD", "rpm", (149,165,255,255))
        sx,sy,sw,sh = 20,20,540,56
        d.rounded_rectangle([sx,sy,sx+sw,sy+sh], radius=14, fill=(0,0,0,160), outline=(255,255,255,180), width=2)
        el = (target-df['ts'].iloc[0]).total_seconds()
        d.text((sx+16, sy+8), f"경과: {timedelta(seconds=int(el))}", fill=(255,255,255,255), font=F_TITLE)
        d.text((sx+200, sy+8), f"거리: {rec['km']:5.2f} km", fill=(255,255,255,255), font=F_TITLE)
        d.text((sx+380, sy+8), f"고도: {rec['enhanced_altitude']:.0f} m", fill=(255,255,255,255), font=F_TITLE)
        gc = (255,107,107,255) if grade>5 else (255,209,102,255) if grade>2 else (200,200,200,255)
        d.text((sx+16, sy+30), f"경사 {grade:+.1f}%", fill=gc, font=F_LABEL)
        mx, my = W-MM_W-20, H-MM_H-20
        img.paste(MM_BG, (mx,my), MM_BG)
        if not pd.isna(rec['lat']) and not pd.isna(rec['lon']):
            cx_, cy_ = project(rec['lat'], rec['lon'])
            d.ellipse([mx+cx_-7, my+cy_-7, mx+cx_+7, my+cy_+7], fill=(255,107,107,255), outline=(255,255,255,255), width=2)
        ex_, ey_ = W-EP_W-20, my-EP_H-16
        img.paste(EP_BG, (ex_,ey_), EP_BG)
        epx, epy = ep_xy(rec['km'], rec['enhanced_altitude'])
        d.ellipse([ex_+epx-6, ey_+epy-6, ex_+epx+6, ey_+epy+6], fill=(255,107,107,255), outline=(255,255,255,255), width=2)
        img.save(f"{OUT_DIR}/f{idx:05d}.png")
        if idx % 300 == 0: print(f"  {idx}/{N}")

# render_overlay_range는 build_overlay_parallel.py 에서 사용
def render_overlay_range(FIT, OUT_DIR, DEMO_START_UTC, n_start, n_end):
    """프레임 범위만 렌더 (병렬 워커용)."""
    # 위 render_overlay 로직과 동일하지만 범위만 렌더
    # 단순화: render_overlay 호출하되 범위는 외부 처리
    pass  # 실제 구현은 build_overlay_parallel.py 에서 직접

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print(__doc__); sys.exit(1)
    fit_path, out_dir, start_iso, dur = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
    DEMO_START = datetime.fromisoformat(start_iso.replace('Z','+00:00'))
    render_overlay(fit_path, out_dir, DEMO_START, dur)
