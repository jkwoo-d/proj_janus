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
                motion_type = 'directed'   # super-ballistic → directed로 보수적 처리
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


def filter_unreliable_fits(fit_results: dict[int, dict]) -> tuple[dict[int, dict], list[dict]]:
    """fitting 품질이 낮은 입자를 제거한다.

    제거 기준 (OR 조건):
      1. D_err / D > config.D_ERR_RATIO_MAX  — fitting 불신뢰 (trajectory 링킹 오류 등)
      2. alpha < config.ALPHA_MIN            — power-law 퇴화 (α≈0 → D 값 무의미)

    Returns:
        kept    — 필터 통과 입자의 fit_results dict
        removed — 제거된 입자 정보 리스트 (particle, reason, D, alpha, D_err 포함)
    """
    kept: dict[int, dict] = {}
    removed: list[dict] = []
    for pid, res in fit_results.items():
        D, D_err, alpha = res['D'], res['D_err'], res['alpha']
        rel_err = D_err / max(D, 1e-12)
        if rel_err > config.D_ERR_RATIO_MAX:
            reason = f'D_err/D={rel_err:.2f}'
        elif config.D_ERR_ABS_MAX is not None and D_err > config.D_ERR_ABS_MAX:
            reason = f'D_err={D_err:.4f}'
        elif alpha < config.ALPHA_MIN:
            reason = f'alpha={alpha:.3f}'
        else:
            kept[pid] = res
            continue
        removed.append({'particle': pid, 'reason': reason, **res})
    return kept, removed


def filter_outlier_D(fit_results: dict[int, dict]) -> tuple[dict[int, dict], list[dict]]:
    """log(D) IQR 기반 앙상블 D outlier 제거.

    fitting 품질 필터 통과 후 D 값의 log 분포에서 Tukey fence를 벗어나는 입자를 제거.
    fence: [Q1 - k*IQR, Q3 + k*IQR] on log(D), k = config.D_OUTLIER_IQR_K.
    입자 수가 4 미만이면 건너뜀.
    """
    if len(fit_results) < 4:
        return fit_results, []

    log_D = np.array([np.log(res['D']) for res in fit_results.values()])
    Q1, Q3 = np.percentile(log_D, [25, 75])
    IQR = Q3 - Q1
    lo = Q1 - config.D_OUTLIER_IQR_K * IQR
    hi = Q3 + config.D_OUTLIER_IQR_K * IQR

    kept: dict[int, dict] = {}
    removed: list[dict] = []
    for pid, res in fit_results.items():
        log_d = np.log(res['D'])
        if log_d < lo:
            removed.append({'particle': pid, 'reason': f'D_low={res["D"]:.4f}', **res})
        elif log_d > hi:
            removed.append({'particle': pid, 'reason': f'D_high={res["D"]:.4f}', **res})
        else:
            kept[pid] = res

    return kept, removed


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


def compute_angular_displacement(trajectories_df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """각 입자별 프레임별 속도벡터 방향, 각변위, 누적 각변위 계산.

    중심차분으로 속도벡터 방향 θ를 구하고, 연속 프레임 간 θ 변화량(각변위)을
    -π ~ π 범위로 누적합산해 누적 각변위를 반환한다.
    """
    results = {}
    for pid, traj in trajectories_df.groupby('particle'):
        traj = traj.sort_values('frame').reset_index(drop=True)
        if len(traj) < 3:
            continue

        x = traj['x'].values
        y = traj['y'].values
        frames = traj['frame'].values
        n = len(traj)

        # frame gap 마스크 — MEMORY > 0으로 생긴 불연속 구간 감지
        gaps = np.diff(frames) > 1   # gaps[i]=True: frames[i]→frames[i+1] 불연속

        # 속도벡터 방향 θ — 중심차분 (gap 경계는 단방향 차분으로 대체)
        theta = np.empty(n)
        theta[0]  = np.arctan2(y[1]  - y[0],  x[1]  - x[0])
        theta[-1] = np.arctan2(y[-1] - y[-2], x[-1] - x[-2])
        for i in range(1, n - 1):
            before_gap = gaps[i - 1]   # frames[i-1]→frames[i] 불연속
            after_gap  = gaps[i]       # frames[i]→frames[i+1] 불연속
            if before_gap:
                theta[i] = np.arctan2(y[i + 1] - y[i], x[i + 1] - x[i])
            elif after_gap:
                theta[i] = np.arctan2(y[i] - y[i - 1], x[i] - x[i - 1])
            else:
                theta[i] = np.arctan2(y[i + 1] - y[i - 1], x[i + 1] - x[i - 1])

        # 각변위 Δθ: 연속 프레임 간 θ 변화, -π ~ π wrap
        delta = np.empty(n)
        delta[0] = 0.0
        delta[1:] = np.angle(np.exp(1j * np.diff(theta)))  # wrap 처리
        # gap 직후 delta는 의미 없으므로 0으로 마스킹
        for i in range(1, n):
            if gaps[i - 1]:
                delta[i] = 0.0

        # 누적 각변위 (첫 프레임 기준 0)
        cumulative = np.cumsum(delta)

        results[int(pid)] = pd.DataFrame({
            'frame':          frames,
            'theta_rad':      theta,
            'delta_theta_rad': delta,
            'cumulative_rad': cumulative,
            'cumulative_deg': np.degrees(cumulative),
        })

    return results


def compute_ensemble_angular_stats(angular_dict: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """누적 각변위의 앙상블 통계 — lag step별 mean, std, sem, n."""
    if not angular_dict:
        return pd.DataFrame()

    lag_data: dict[int, list] = {}
    for df in angular_dict.values():
        cum = df['cumulative_deg'].values
        for lag, val in enumerate(cum):
            lag_data.setdefault(lag, []).append(val)

    rows = []
    for lag in sorted(lag_data):
        vals = np.array(lag_data[lag])
        rows.append({
            'lag_step':          lag,
            'lag_time_s':        lag / config.FPS,
            'mean_cumulative_deg': float(vals.mean()),
            'std_cumulative_deg':  float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
            'sem_cumulative_deg':  float(vals.std(ddof=1) / np.sqrt(len(vals))) if len(vals) > 1 else 0.0,
            'n':                 len(vals),
        })

    return pd.DataFrame(rows)


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


def compute_brightness_dynamics(trajectories_df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """입자별 프레임별 밝기(mass) 시계열 추출.

    선형 추세를 제거한 detrended signal과 정규화 signal을 함께 반환한다.
    자전으로 인한 주기적 밝기 변동 분석에 사용.
    """
    results = {}
    for pid, traj in trajectories_df.groupby('particle'):
        traj = traj.sort_values('frame').reset_index(drop=True)
        if 'mass' not in traj.columns or len(traj) < 5:
            continue

        frames = traj['frame'].values
        mass = traj['mass'].values.astype(float)
        time_s = frames / config.FPS

        mean_mass = mass.mean()
        mass_norm = (mass - mean_mass) / mean_mass if mean_mass > 0 else mass - mean_mass

        poly = np.polyfit(time_s, mass, 1)
        mass_detrended = mass - np.polyval(poly, time_s)

        results[int(pid)] = pd.DataFrame({
            'frame':          frames,
            'time_s':         time_s,
            'mass':           mass,
            'mass_norm':      mass_norm,
            'mass_detrended': mass_detrended,
        })

    return results


def compute_brightness_fft(brightness_dict: dict[int, pd.DataFrame]) -> dict[int, dict]:
    """입자별 밝기 시계열의 FFT 파워 스펙트럼 계산.

    detrended signal에 Hann 윈도우를 적용한 후 FFT.
    peak 주파수와 해당 주기를 함께 반환한다.
    """
    results = {}
    dt = 1.0 / config.FPS

    for pid, df in brightness_dict.items():
        signal = df['mass_detrended'].values
        n = len(signal)
        if n < 10:
            continue

        window = np.hanning(n)
        fft_vals = np.fft.rfft(signal * window)
        freqs = np.fft.rfftfreq(n, d=dt)
        power = np.abs(fft_vals) ** 2

        mask = freqs > 0
        freqs_pos = freqs[mask]
        power_pos = power[mask]

        if len(power_pos) > 0:
            peak_idx = np.argmax(power_pos)
            peak_freq = float(freqs_pos[peak_idx])
            peak_period_s = 1.0 / peak_freq if peak_freq > 0 else np.inf
        else:
            peak_freq, peak_period_s = 0.0, np.inf

        results[int(pid)] = {
            'freq':          freqs_pos,
            'power':         power_pos,
            'peak_freq':     peak_freq,
            'peak_period_s': peak_period_s,
        }

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
