#!/usr/bin/env python3
"""유튜브 썸네일 PNG 동적 생성 (1920x1080 + 1280x720)."""
import sys
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: build_yt_thumbnail.py <ride_dir> [course_name] [date_tag]")
    ride = Path(sys.argv[1])
    course_name = sys.argv[2] if len(sys.argv) > 2 else ride.name.split()[-1]
    date_tag = sys.argv[3] if len(sys.argv) > 3 else os.environ.get('DATE_TAG', '')

    A = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    M = json.loads((ride / 'ride_meta.json').read_text(encoding='utf-8')) if (ride / 'ride_meta.json').exists() else {}
    s = A['summary']
    b = A.get('best_climb') or {}
    fd = A.get('fade_climb') or {}

    W, H = 1920, 1080
    img = Image.new('RGB', (W, H), (12, 22, 38))
    d = ImageDraw.Draw(img)
    SYS = '/System/Library/Fonts/AppleSDGothicNeo.ttc'

    def f(sz, idx=0):
        try:
            return ImageFont.truetype(SYS, sz, index=idx)
        except Exception:
            return ImageFont.truetype(SYS, sz)

    ACCENT, ACCENT2, ACCENT3 = (255, 184, 76), (102, 222, 178), (255, 107, 107)
    TEXT_M, TEXT_S, TEXT_D = (245, 248, 252), (170, 185, 210), (110, 125, 150)

    # 그라데이션
    for y in range(H):
        a = y / H
        c = tuple(int(12 + (28 - 12) * a if i == 0
                      else 22 + (38 - 22) * a if i == 1
                      else 38 + (58 - 38) * a) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)

    d.text((100, 90), "GRAN FONDO SIMULATION", font=f(34, 0), fill=TEXT_S)
    d.line([(100, 145), (480, 145)], fill=ACCENT, width=4)
    d.text((100, 175), course_name, font=f(180, 3), fill=ACCENT)
    d.text((100, 380), f"{s['distance_km']}km · +{s['elev_gain_m']}m · TSS {s['tss']}",
           font=f(58, 2), fill=TEXT_M)

    d.line([(100, 510), (1820, 510)], fill=(50, 65, 95), width=2)

    if b and fd and b.get('vam_m_per_h'):
        d.text((100, 540), "같은 코스 — 다른 결과", font=f(46, 1), fill=TEXT_S)
        drop_pct = int((1 - fd.get('vam_m_per_h', 0) / b['vam_m_per_h']) * 100)
        y_vam = 620
        d.text((100, y_vam + 30), "VAM", font=f(48, 0), fill=TEXT_S)
        d.text((250, y_vam), str(int(b.get('vam_m_per_h', 0))), font=f(200, 3), fill=ACCENT2)
        d.text((620, y_vam + 50), "→", font=f(140, 0), fill=TEXT_M)
        d.text((820, y_vam), str(int(fd.get('vam_m_per_h', 0))), font=f(200, 3), fill=ACCENT3)
        d.text((1180, y_vam + 30), f"-{drop_pct}%", font=f(140, 3), fill=ACCENT3)
        d.text((250, y_vam - 50), f"Climb #{b.get('index', '?')} 베스트", font=f(28, 1), fill=ACCENT2)
        d.text((820, y_vam - 50), f"Climb #{fd.get('index', '?')} 페이드", font=f(28, 1), fill=ACCENT3)
    else:
        d.text((100, 580),
               f"Avg {s['avg_power_w']}W · NP {s['np_w']}W · IF {s['if_']}",
               font=f(60, 2), fill=TEXT_M)
        d.text((100, 680),
               f"디커플링 {s.get('decoupling_pct', 0)}% · 케이던스 {s['avg_cadence']} rpm",
               font=f(54, 2), fill=TEXT_S)

    d.line([(100, 920), (1820, 920)], fill=(50, 65, 95), width=2)
    d.text((100, 945), "DATA-DRIVEN COACHING", font=f(28, 0), fill=TEXT_D)
    d.text((100, 990), "Data Ride · 그란폰도 시뮬레이션", font=f(48, 2), fill=ACCENT)
    d.text((1700, 945), date_tag, font=f(30, 0), fill=TEXT_S)
    d.text((1620, 990), f"{course_name} 코스", font=f(36, 2), fill=TEXT_M)
    d.rectangle([0, 0, 12, H], fill=ACCENT)

    out = ride / "yt_thumbnail.png"
    img.save(out, optimize=True)
    print(f"  ✓ {out.name}")

    img_720 = img.resize((1280, 720), Image.LANCZOS)
    img_720.save(ride / "yt_thumbnail_1280x720.png", optimize=True)
    print(f"  ✓ yt_thumbnail_1280x720.png")


if __name__ == '__main__':
    main()
