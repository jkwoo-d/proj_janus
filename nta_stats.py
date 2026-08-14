import os
import numpy as np
import pandas as pd

import config


def compute_vector_mean_displacement(trajectories_df: pd.DataFrame) -> dict:
    """앙상블 평균 변위 벡터 ⟨Δx⟩, ⟨Δy⟩ 계산."""
    mpp = config.PIXEL_SIZE_NM / 1000.0 if config.PIXEL_SIZE_NM else 1.0
    unit = 'µm' if config.PIXEL_SIZE_NM else 'px'
    dx_list, dy_list = [], []
    for pid, traj in trajectories_df.groupby('particle'):
        traj = traj.sort_values('frame')
        dx_list.append((traj['x'].iloc[-1] - traj['x'].iloc[0]) * mpp)
        dy_list.append((traj['y'].iloc[-1] - traj['y'].iloc[0]) * mpp)
    mean_dx = float(np.mean(dx_list))
    mean_dy = float(np.mean(dy_list))
    return {
        'unit': unit,
        'mean_dx': mean_dx,
        'mean_dy': mean_dy,
        'magnitude': float(np.sqrt(mean_dx**2 + mean_dy**2)),
        'n': len(dx_list),
    }


def _compute_net_displacement(trajectories_df: pd.DataFrame) -> pd.Series:
    """각 입자의 net displacement (원본 좌표, drift 미보정)."""
    mpp = config.PIXEL_SIZE_NM / 1000.0 if config.PIXEL_SIZE_NM else 1.0
    values = {}
    for pid, traj in trajectories_df.groupby('particle'):
        traj = traj.sort_values('frame')
        dx = (traj['x'].iloc[-1] - traj['x'].iloc[0]) * mpp
        dy = (traj['y'].iloc[-1] - traj['y'].iloc[0]) * mpp
        values[int(pid)] = float(np.sqrt(dx**2 + dy**2))
    return pd.Series(values, name='net_displacement')


def compute_ensemble_stats(fit_results: dict,
                           trajectories_original=None,
                           trajectories_for_stats=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not fit_results:
        return pd.DataFrame(), pd.DataFrame()

    per_particle = pd.DataFrame(
        [{'particle': pid, **vals} for pid, vals in fit_results.items()]
    )

    D = per_particle['D']
    alpha = per_particle['alpha']
    unit = 'µm²/s' if config.PIXEL_SIZE_NM else 'px²/s'
    disp_unit = 'µm' if config.PIXEL_SIZE_NM else 'px'

    row = {
        'n_particles': len(per_particle),
        f'D_mean_{unit}': D.mean(),
        f'D_median_{unit}': D.median(),
        f'D_std_{unit}': D.std(),
        f'D_p25_{unit}': D.quantile(0.25),
        f'D_p75_{unit}': D.quantile(0.75),
        'alpha_mean': alpha.mean(),
        'alpha_median': alpha.median(),
        'alpha_std': alpha.std(),
    }

    for mtype in ['brownian', 'confined', 'directed']:
        count = int((per_particle['motion_type'] == mtype).sum())
        row[f'n_{mtype}'] = count
        row[f'pct_{mtype}'] = round(100.0 * count / len(per_particle), 1)

    if trajectories_original is not None:
        net_disp = _compute_net_displacement(trajectories_original)
        net_disp_fitted = net_disp[net_disp.index.isin(per_particle['particle'])]
        per_particle = per_particle.merge(
            net_disp_fitted.rename(f'net_displacement_{disp_unit}').reset_index().rename(columns={'index': 'particle'}),
            on='particle', how='left'
        )
        nd = net_disp_fitted
        row[f'net_disp_mean_{disp_unit}'] = nd.mean()
        row[f'net_disp_median_{disp_unit}'] = nd.median()
        row[f'net_disp_std_{disp_unit}'] = nd.std()

    # 벡터 평균 변위 (drift 보정 여부에 따라 다른 trajectory 사용)
    traj_for_vec = trajectories_for_stats if trajectories_for_stats is not None else trajectories_original
    if traj_for_vec is not None:
        vm = compute_vector_mean_displacement(traj_for_vec)
        u = vm['unit']
        row[f'vec_mean_dx_{u}'] = vm['mean_dx']
        row[f'vec_mean_dy_{u}'] = vm['mean_dy']
        row[f'vec_mean_mag_{u}'] = vm['magnitude']

    return pd.DataFrame([row]), per_particle


def save_results(ensemble_stats: pd.DataFrame, per_particle: pd.DataFrame,
                 removed: list[dict] | None = None):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    ensemble_stats.to_csv(f"{config.OUTPUT_DIR}/ensemble_stats.csv", index=False)
    per_particle.to_csv(f"{config.OUTPUT_DIR}/per_particle_results.csv", index=False)
    if removed:
        pd.DataFrame(removed).to_csv(
            f"{config.OUTPUT_DIR}/outliers_removed.csv", index=False)
    print(f"  CSVs saved → {config.OUTPUT_DIR}/")
