import pandas as pd
import trackpy as tp

import config


def link_trajectories(detected_df: pd.DataFrame) -> pd.DataFrame:
    tp.quiet()

    n_per_frame = len(detected_df) / detected_df['frame'].nunique()
    if n_per_frame > 200:
        print(f"  WARNING: 프레임당 평균 {n_per_frame:.0f}개 검출 — 너무 많습니다. "
              f"MIN_MASS를 높여 실제 입자만 남기세요.")

    try:
        linked = tp.link(detected_df, search_range=config.SEARCH_RANGE, memory=config.MEMORY)
    except Exception:
        # 입자 밀도가 너무 높을 때 adaptive 모드로 재시도
        print("  SubnetOversize 발생 → adaptive 모드로 재시도 (search_range 자동 축소)")
        linked = tp.link(detected_df, search_range=config.SEARCH_RANGE, memory=config.MEMORY,
                         adaptive_stop=1, adaptive_step=0.95)

    filtered = tp.filter_stubs(linked, threshold=config.MIN_TRAJECTORY_LENGTH)
    n_before = linked['particle'].nunique()
    n_after = filtered['particle'].nunique()
    print(f"  Linked {n_before} raw tracks → {n_after} tracks "
          f"(≥{config.MIN_TRAJECTORY_LENGTH} frames)")
    return filtered.reset_index(drop=True)


def compute_and_correct_drift(trajectories_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        drift = tp.compute_drift(trajectories_df)
    except Exception as e:
        print(f"  WARNING: drift computation failed ({e}). Skipping correction.")
        return trajectories_df, pd.DataFrame()

    corrected = tp.subtract_drift(trajectories_df.copy(), drift)
    corrected = corrected.reset_index(drop=True)
    max_drift = (drift['x'].abs().max(), drift['y'].abs().max())
    print(f"  Drift corrected (max per frame: x={max_drift[0]:.2f}px, y={max_drift[1]:.2f}px)")
    return corrected, drift
