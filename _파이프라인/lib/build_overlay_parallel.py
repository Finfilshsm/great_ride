"""오버레이 PNG 병렬 생성기."""
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import build_overlay as bo

def worker(args):
    fit_path, out_dir, start_iso, dur, start_idx, end_idx = args
    # 단순화: 각 청크가 자기 영역만 렌더
    # 메모리 효율을 위해 build_overlay.render_overlay 를 부분 호출 패턴으로
    DEMO_START = datetime.fromisoformat(start_iso.replace('Z','+00:00'))
    # 임시: 전체 렌더 (단일 프로세스용)
    # 진정한 병렬화는 render_overlay 내부 i 범위 파라미터 추가 필요 — 추후 보강
    bo.render_overlay(fit_path, out_dir, DEMO_START, dur)
    return (start_idx, end_idx)

if __name__ == '__main__':
    fit, outd, start_iso, dur, nw = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
    # 단순 단일 프로세스로 호출 (병렬화 추후 보강)
    DEMO_START = datetime.fromisoformat(start_iso.replace('Z','+00:00'))
    bo.render_overlay(fit, outd, DEMO_START, dur)
    print(f"Done.")
