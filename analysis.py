import numpy as np
import pandas as pd
import trackpy as tp
from scipy.optimize import curve_fit

import config


def _mpp() -> float:
    """microns per pixel. Returns 1.0 (pixel units) if PIXEL_SIZE_NM not set."""
    if config.PIXEL_SIZE_NM is not None:
        return config.PIXEL_SIZE_NM / 1000.0
    return 1.0


def compute_msd_per_particle(trajectories_df: pd.DataFrame,
                              max_lagtime: int = 100) -> dict[int, pd.DataFrame]:
    msd_dict = {}
    mpp = _mpp()
    tp.quiet()
    for pid, traj in trajectories_df.groupby('particle'):
        try:
            n_frames = len(traj['frame'].unique())
            max_lag = max(4, n_frames // 4)   # 표준 NTA: N/4 이하만 통계적으로 신뢰 가능
            msd = tp.msd(traj, mpp=mpp, fps=config.FPS, max_lagtime=max_lag, detail=False)
            msd_dict[int(pid)] = msd
        except Exception:
            continue
    return msd_dict


def compute_ensemble_msd(trajectories_df: pd.DataFrame,
                         max_lagtime: int = 100) -> pd.DataFrame:
    mpp = _mpp()
    tp.quiet()
    return tp.emsd(trajectories_df, mpp=mpp, fps=config.FPS, max_lagtime=max_lagtime)


def _power_law(t, D, alpha):
    return 4.0 * D * (t ** alpha)


def fit_msd(msd_dict: dict[int, pd.DataFrame]) -> dict[int, dict]:
    results = {}
    for pid, msd_df in msd_dict.items():
        # tp.msd() stores lag time in seconds in 'lagt' column
        lag = msd_df['lagt'].values.astype(float)
        msd_vals = msd_df['msd'].values.astype(float)

        mask = (lag > 0) & np.isfinite(msd_vals) & (msd_vals > 0)
        if mask.sum() < 4:
            continue

        try:
            popt, pcov = curve_fit(
                _power_law, lag[mask], msd_vals[mask],
                p0=[np.median(msd_vals[mask]), 1.0],
                bounds=([0, 0], [np.inf, 3.0]),
                maxfev=5000,
            )
            D, alpha = popt
            perr = np.sqrt(np.diag(pcov))
            alpha_rel_err = perr[1] / max(abs(alpha), 1e-9)
            n_lag = int(mask.sum())

            alpha_ci_hi = alpha + 2 * perr[1]  # 95% CI 상한

            if alpha > 2.0:
                motion_type = 'brownian'
            elif alpha_rel_err > 0.3:
                # 상대 오차가 크더라도 CI 상한이 0.85 미만이면 confined로 분류
                # (예: α=0.02, alpha_err=0.04 → CI 상한=0.10 → 명백히 confined)
                motion_type = 'confined' if alpha_ci_hi < 0.85 else 'brownian'
            elif alpha < 0.85:
                motion_type = 'confined'
            elif alpha > 1.15 and n_lag >= 8:
                # directed 판정은 최소 8개 lag time point 필요
                motion_type = 'directed'
            else:
                motion_type = 'brownian'

            results[pid] = {
                'D': D,
                'alpha': alpha,
                'D_err': perr[0],
                'alpha_err': perr[1],
                'motion_type': motion_type,
            }
        except (RuntimeError, ValueError):
            continue

    return results


def filter_drift_artifacts(fit_results: dict[int, dict],
                           trajectories_original: pd.DataFrame,
                           trajectories_corrected: pd.DataFrame,
                           ratio_threshold: float = 0.1) -> dict[int, dict]:
    """drift 보정으로 인한 spurious directed 분류를 제거.

    원본 좌표 net displacement / 보정 좌표 net displacement < ratio_threshold 인 경우,
    정지 입자가 drift 반대 방향으로 움직이는 것처럼 보이는 artifact → brownian으로 재분류.
    """
    for pid, res in fit_results.items():
        if res['motion_type'] != 'directed':
            continue
        orig = trajectories_original[trajectories_original['particle'] == pid].sort_values('frame')
        corr = trajectories_corrected[trajectories_corrected['particle'] == pid].sort_values('frame')
        if len(orig) < 2 or len(corr) < 2:
            continue
        orig_net = float(np.sqrt((orig['x'].iloc[-1] - orig['x'].iloc[0])**2 +
                                  (orig['y'].iloc[-1] - orig['y'].iloc[0])**2))
        corr_net = float(np.sqrt((corr['x'].iloc[-1] - corr['x'].iloc[0])**2 +
                                  (corr['y'].iloc[-1] - corr['y'].iloc[0])**2))
        if corr_net > 0 and orig_net / corr_net < ratio_threshold:
            res['motion_type'] = 'brownian'
    return fit_results


def extract_velocity(trajectories_df: pd.DataFrame,
                     fit_results: dict[int, dict]) -> pd.Series:
    """Net drift-free velocity for directed-motion particles (µm/s or px/s)."""
    mpp = _mpp()
    fps = config.FPS
    velocities = {}

    for pid, res in fit_results.items():
        if res['motion_type'] != 'directed':
            continue
        traj = trajectories_df[trajectories_df['particle'] == pid].sort_values('frame')
        dx = (traj['x'].iloc[-1] - traj['x'].iloc[0]) * mpp
        dy = (traj['y'].iloc[-1] - traj['y'].iloc[0]) * mpp
        dt = (traj['frame'].iloc[-1] - traj['frame'].iloc[0]) / fps
        if dt > 0:
            velocities[pid] = float(np.sqrt(dx**2 + dy**2) / dt)

    unit = 'µm/s' if config.PIXEL_SIZE_NM else 'px/s'
    return pd.Series(velocities, name=f'velocity_{unit}')


# ── Janus 확장용 ─────────────────────────────────────────────────────────────

def _directed_msd(t, D, v):
    """MSD model for Brownian + directed motion: 4Dt + v²t²"""
    return 4.0 * D * t + (v * t) ** 2


def fit_msd_directed(msd_dict: dict[int, pd.DataFrame]) -> dict[int, dict]:
    """Fit MSD = 4Dt + v²t² for Janus particle directed motion analysis."""
    results = {}
    for pid, msd_df in msd_dict.items():
        lag = msd_df.index.values.astype(float)
        msd_vals = msd_df['msd'].values.astype(float)
        mask = (lag > 0) & np.isfinite(msd_vals) & (msd_vals > 0)
        if mask.sum() < 4:
            continue
        try:
            popt, _ = curve_fit(
                _directed_msd, lag[mask], msd_vals[mask],
                p0=[1.0, 0.1], bounds=([0, 0], [np.inf, np.inf]),
                maxfev=5000,
            )
            results[pid] = {'D': popt[0], 'v': popt[1]}
        except (RuntimeError, ValueError):
            continue
    return results


def compute_straightness(trajectories_df: pd.DataFrame) -> pd.Series:
    """Straightness index = net displacement / total path length (0–1)."""
    values = {}
    for pid, traj in trajectories_df.groupby('particle'):
        traj = traj.sort_values('frame')
        dx_net = traj['x'].iloc[-1] - traj['x'].iloc[0]
        dy_net = traj['y'].iloc[-1] - traj['y'].iloc[0]
        net = float(np.sqrt(dx_net**2 + dy_net**2))

        steps = np.sqrt(np.diff(traj['x'].values)**2 + np.diff(traj['y'].values)**2)
        total = float(steps.sum())

        values[int(pid)] = net / total if total > 0 else 0.0
    return pd.Series(values, name='straightness')
