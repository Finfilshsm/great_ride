#!/usr/bin/env python3
"""GoPro 4K + Garmin .fit → 1080p 오버레이 본편 자동 빌드.

기존 build_overlay.py(PNG 시퀀스 렌더)에 누락된 컴포지션·concat 단계를 보강:
1) _videos.json 읽어 챕터별 (GoPro MP4, start_utc, duration) 결정
2) 각 챕터별로 PNG 시퀀스 렌더 (build_overlay.render_overlay_range로 메모리 절약)
   — GoPro pre-ride 구간(=라이딩 시작 전 영상)은 PNG 없이 통과
3) ffmpeg로 GoPro 4K + PNG 오버레이 합성 → 1080p hevc_videotoolbox MP4
4) 모든 챕터 MP4를 concat → 전체_라이딩_오버레이.mp4

병렬화: ProcessPoolExecutor로 PNG 렌더는 챕터 단위 분산.
ffmpeg 컴포지트는 GPU(videotoolbox)가 직렬 처리.

사용법:
    python3 build_overlay_pipeline.py <ride_dir>
    환경변수 RIDE_DIR도 가능.
"""
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed

# build_overlay 모듈 import
sys.path.insert(0, str(Path(__file__).parent))
import build_overlay as bo


def find_ffmpeg():
    candidates = [
        '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg',
        '/opt/homebrew/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
    ]
    for c in candidates:
        if Path(c).exists() and os.access(c, os.X_OK):
            return c
    # PATH fallback
    p = shutil.which('ffmpeg')
    if p:
        return p
    sys.exit("✗ ffmpeg 없음")


def render_chapter_pngs(args):
    """단일 챕터의 PNG 프레임 시퀀스 생성. (병렬 워커)"""
    fit_path, png_dir, start_utc_iso, duration_s = args
    png_dir = Path(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)
    start_utc = datetime.fromisoformat(start_utc_iso)
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    bo.render_overlay(fit_path, str(png_dir), start_utc, duration_s)
    return str(png_dir)


def composite_chapter(ffmpeg, gopro_mp4, png_dir, out_mp4, fps='30000/1001',
                       trim_ss=0, trim_t=None):
    """GoPro 4K MP4 + PNG 오버레이 → 1080p HEVC MP4.

    trim_ss: GoPro 챕터 시작에서 몇 초를 잘라내고 시작할지
    trim_t:  몇 초간 사용할지 (None이면 끝까지)
    """
    # PNG 폴더의 첫 프레임 확인
    pngs = sorted(Path(png_dir).glob('f*.png'))
    trim_args_in = []
    if trim_ss and trim_ss > 0.01:
        trim_args_in = ['-ss', f"{trim_ss:.3f}"]
    trim_args_out = []
    if trim_t and trim_t > 0:
        trim_args_out = ['-t', f"{trim_t:.3f}"]

    if not pngs:
        # PNG 없음 → 단순 4K→1080p downscale (trim 적용)
        cmd = [
            ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-stats',
            *trim_args_in,
            '-i', str(gopro_mp4),
            *trim_args_out,
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'hevc_videotoolbox', '-q:v', '50', '-tag:v', 'hvc1',
            '-r', fps, '-video_track_timescale', '30000',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
            '-movflags', '+faststart',
            str(out_mp4),
        ]
    else:
        # PNG 시퀀스(이미 ride 시작 시점부터 렌더됨) + GoPro(trim 적용) 합성
        png_pattern = str(Path(png_dir) / 'f%05d.png')
        cmd = [
            ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-stats',
            *trim_args_in,
            '-i', str(gopro_mp4),
            *trim_args_out,
            '-framerate', fps, '-i', png_pattern,
            '-filter_complex',
            '[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2[bg];'
            '[1:v]scale=1920:1080[ov];'
            '[bg][ov]overlay=0:0:shortest=1[v]',
            '-map', '[v]', '-map', '0:a?',
            '-c:v', 'hevc_videotoolbox', '-q:v', '50', '-tag:v', 'hvc1',
            '-r', fps, '-video_track_timescale', '30000',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
            '-movflags', '+faststart',
            str(out_mp4),
        ]
    print(f"    ffmpeg trim_ss={trim_ss}s trim_t={trim_t}s")
    subprocess.run(cmd, check=True)


def concat_chapters(ffmpeg, chapter_mp4s, out_mp4):
    """concat demuxer로 stream copy 결합 (모든 챕터가 동일 코덱·해상도여야 함)."""
    list_file = Path(out_mp4).parent / '_concat_overlay.txt'
    list_file.write_text(''.join(f"file '{p}'\n" for p in chapter_mp4s), encoding='utf-8')
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'warning',
        '-f', 'concat', '-safe', '0', '-i', str(list_file),
        '-c', 'copy',
        '-movflags', '+faststart',
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)
    list_file.unlink(missing_ok=True)


def main():
    ride_dir = sys.argv[1] if len(sys.argv) >= 2 else os.environ.get('RIDE_DIR')
    if not ride_dir:
        sys.exit("사용법: build_overlay_pipeline.py <ride_dir>")
    ride = Path(ride_dir)
    if not ride.is_dir():
        sys.exit(f"✗ 폴더 없음: {ride}")

    fit_files = list(ride.glob('*.fit')) + list(ride.glob('*.FIT'))
    if not fit_files:
        sys.exit(f"✗ .fit 없음: {ride}")
    fit_path = fit_files[0]

    videos_json = ride / '_videos.json'
    if not videos_json.exists():
        sys.exit(f"✗ _videos.json 없음 — RUN_RIDE 먼저 실행")
    videos = json.loads(videos_json.read_text(encoding='utf-8'))['ride_videos_chronological']

    analysis = json.loads((ride / '_analysis.json').read_text(encoding='utf-8'))
    ride_start_iso = analysis['ride_start_utc']
    ride_start = datetime.fromisoformat(ride_start_iso)
    if ride_start.tzinfo is None:
        ride_start = ride_start.replace(tzinfo=timezone.utc)

    out_dir = ride / 'output_videos'
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / '_overlay_work'
    work_dir.mkdir(parents=True, exist_ok=True)
    pngs_root = work_dir / 'pngs'
    pngs_root.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    print(f"  ffmpeg: {ffmpeg}")

    # 라이딩 종료 시각 — moving_h 또는 elapsed_h 파싱
    def parse_h(s):
        """'3:11:06' → 11466.0초 또는 None"""
        if not s or not isinstance(s, str):
            return None
        try:
            parts = s.split(':')
            if len(parts) == 3:
                h, m, sec = parts
                return int(h)*3600 + int(m)*60 + float(sec)
        except Exception:
            return None
        return None
    elapsed_s = parse_h(analysis['summary'].get('elapsed_h'))
    if not elapsed_s:
        elapsed_s = parse_h(analysis['summary'].get('moving_h')) or 0
    ride_end = ride_start + timedelta(seconds=elapsed_s)
    print(f"  ride window: {ride_start.isoformat()} → {ride_end.isoformat()} ({elapsed_s/60:.1f}min)")

    # ───── 1) 챕터별 ride 윈도우 trim 정보 계산 ─────
    print(f"\n[1/3] PNG 오버레이 시퀀스 렌더 (라이딩 윈도우 trim 적용)...")
    render_jobs = []
    chapter_meta = []
    for i, v in enumerate(videos, 1):
        gp_path = ride / v['file']
        v_start = datetime.fromisoformat(v['start_utc'])
        if v_start.tzinfo is None:
            v_start = v_start.replace(tzinfo=timezone.utc)
        v_end = v_start + timedelta(seconds=v['duration_s'])

        # ride 윈도우와 overlap
        eff_start = max(v_start, ride_start)
        eff_end = min(v_end, ride_end)
        overlap_s = (eff_end - eff_start).total_seconds()

        if overlap_s <= 1.0:
            # 라이딩 시간과 겹치지 않음 → 챕터 통째로 SKIP
            print(f"    ch{i:02d} {v['file']:20s} (raw {v['duration_s']:.0f}s) — SKIP (라이딩 외)")
            chapter_meta.append({'i': i, 'gp': gp_path, 'skip': True})
            continue

        trim_ss_in_chapter = (eff_start - v_start).total_seconds()  # GoPro 챕터에서 잘라낼 앞부분(s)
        trim_t = overlap_s  # 사용할 길이(s)
        png_dir = pngs_root / f"ch{i:02d}"

        chapter_meta.append({
            'i': i, 'gp': gp_path, 'png_dir': png_dir,
            'skip': False, 'trim_ss': trim_ss_in_chapter, 'trim_t': trim_t,
            'eff_start': eff_start,
        })
        # PNG 렌더 시작 시각 = eff_start, 길이 = trim_t (즉 라이딩 portion)
        render_jobs.append((str(fit_path), str(png_dir), eff_start.isoformat(), trim_t))
        print(f"    ch{i:02d} {v['file']:20s} (raw {v['duration_s']:.0f}s) → trim_ss={trim_ss_in_chapter:.0f}s · use {trim_t:.0f}s")

    if render_jobs:
        max_workers = min(3, len(render_jobs))
        print(f"\n    병렬 PNG 렌더 시작 ({max_workers}개 워커)...")
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(render_chapter_pngs, job) for job in render_jobs]
            for k, fut in enumerate(as_completed(futs), 1):
                try:
                    result = fut.result()
                    print(f"      ✓ {k}/{len(futs)} 완료: {Path(result).name}")
                except Exception as e:
                    print(f"      ✗ 렌더 실패: {e}")
                    raise

    # ───── 2) ffmpeg 합성 (라이딩 portion만) ─────
    print(f"\n[2/3] GoPro 4K + 오버레이 합성 → 1080p HEVC (trim 적용)...")
    chapter_mp4s = []
    for cm in chapter_meta:
        if cm.get('skip'):
            continue
        out_mp4 = out_dir / f"GX{cm['i']:02d}_overlay.mp4"
        chapter_mp4s.append(out_mp4)
        if out_mp4.exists() and out_mp4.stat().st_size > 1024*1024:
            print(f"    ch{cm['i']:02d} 이미 존재 (skip): {out_mp4.name} ({out_mp4.stat().st_size/1024/1024:.0f}MB)")
            continue
        print(f"    ch{cm['i']:02d} 합성 시작: {cm['gp'].name} → {out_mp4.name}")
        composite_chapter(ffmpeg, cm['gp'], cm['png_dir'], out_mp4,
                          trim_ss=cm['trim_ss'], trim_t=cm['trim_t'])
        print(f"    ch{cm['i']:02d} 완료: {out_mp4.stat().st_size/1024/1024/1024:.2f}GB")

    # ───── 3) concat ─────
    print(f"\n[3/3] {len(chapter_mp4s)}개 챕터 concat → 전체_라이딩_오버레이.mp4")
    overlay_full = out_dir / '전체_라이딩_오버레이.mp4'
    concat_chapters(ffmpeg, [str(p) for p in chapter_mp4s], overlay_full)
    sz = overlay_full.stat().st_size / 1024 / 1024 / 1024
    print(f"    ✓ {overlay_full.name} ({sz:.2f}GB)")

    print("\n  ✓ Overlay pipeline 완료")
    print(f"    산출물: {overlay_full}")
    print(f"    임시 작업물: {work_dir} (정리 가능)")


if __name__ == '__main__':
    main()
