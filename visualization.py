import os
from collections import Counter

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.collections import LineCollection
from scipy.optimize import curve_fit

import config


def _save(fig: plt.Figure, filename: str):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def _get_cmap(name: str, n: int):
    try:
        return plt.colormaps[name].resampled(n)
    except AttributeError:
        return cm.get_cmap(name, n)


def _pos_unit() -> str:
    return 'µm²' if config.PIXEL_SIZE_NM else 'px²'


def plot_all_trajectories(trajectories_df: pd.DataFrame, bg_frame: np.ndarray = None):
    fig, ax = plt.subplots(figsize=(10, 8))

    if bg_frame is not None:
        ax.imshow(bg_frame, cmap='gray', alpha=0.4, origin='upper')

    particles = trajectories_df['particle'].unique()
    cmap = _get_cmap('tab20', max(len(particles), 1))

    for i, pid in enumerate(particles):
        traj = trajectories_df[trajectories_df['particle'] == pid].sort_values('frame')
        if len(traj) < 2:
            continue

        x, y = traj['x'].values, traj['y'].values
        base_rgba = cmap(i % 20)           # (r, g, b, a)
        base_rgb  = base_rgba[:3]

        # 각 선분을 시간 순서에 따라 alpha 0.1 → 1.0 으로 그라데이션
        points   = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        n        = len(segments)
        alphas   = np.linspace(0.1, 1.0, n)
        colors   = [(*base_rgb, a) for a in alphas]

        lc = LineCollection(segments, colors=colors, linewidth=1.2)
        ax.add_collection(lc)

        # 시작점(빈 원)과 끝점(채운 원) 표시
        ax.plot(x[0],  y[0],  'o', color=base_rgb, markersize=3,
                markerfacecolor='none', markeredgewidth=0.8)
        ax.plot(x[-1], y[-1], 'o', color=base_rgb, markersize=4)

        # 끝점 옆에 추적 프레임 수 표시
        n_frames_traj = len(traj)
        ax.text(x[-1] + 4, y[-1], str(n_frames_traj),
                fontsize=5, color=base_rgb, va='center')

    ax.autoscale()
    ax.set_xlabel('x (pixels)')
    ax.set_ylabel('y (pixels)')
    ax.set_title(f'All Trajectories  (n={len(particles)} particles)\n'
                 f'○ start  ●  end  |  opacity: early → late')
    if not ax.yaxis_inverted():
        ax.invert_yaxis()

    _save(fig, 'all_trajectories.png')


def plot_single_trajectory(trajectories_df: pd.DataFrame, particle_id: int,
                           msd_dict: dict = None, fit_results: dict = None):
    traj = trajectories_df[trajectories_df['particle'] == particle_id].sort_values('frame')
    if traj.empty:
        print(f"  WARNING: particle {particle_id} not found.")
        return

    has_msd = msd_dict and particle_id in msd_dict
    ncols = 2 if has_msd else 1
    fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 5))
    if ncols == 1:
        axes = [axes]

    # — trajectory (colour = time) —
    ax = axes[0]
    sc = ax.scatter(traj['x'], traj['y'], c=traj['frame'], cmap='coolwarm', s=8, zorder=3)
    ax.plot(traj['x'], traj['y'], 'k-', linewidth=0.5, alpha=0.3)
    ax.plot(traj['x'].iloc[0], traj['y'].iloc[0], 'go', markersize=6, label='start', zorder=4)
    ax.plot(traj['x'].iloc[-1], traj['y'].iloc[-1], 'r^', markersize=6, label='end', zorder=4)
    plt.colorbar(sc, ax=ax, label='Frame')
    ax.set_xlabel('x (pixels)')
    ax.set_ylabel('y (pixels)')
    ax.set_title(f'Particle {particle_id}  ({len(traj)} frames)')
    ax.legend(fontsize=8)
    ax.invert_yaxis()

    # — MSD + fit —
    if has_msd:
        ax = axes[1]
        msd_df = msd_dict[particle_id]
        # tp.msd() stores seconds in 'lagt' column
        lag = msd_df['lagt'].values.astype(float)
        msd_vals = msd_df['msd'].values.astype(float)
        mask = (lag > 0) & np.isfinite(msd_vals) & (msd_vals > 0)

        ax.loglog(lag[mask], msd_vals[mask], 'o', markersize=3, label='MSD data')

        if fit_results and particle_id in fit_results:
            r = fit_results[particle_id]
            t_fit = np.logspace(np.log10(lag[mask].min()), np.log10(lag[mask].max()), 200)
            ax.loglog(t_fit, 4 * r['D'] * t_fit ** r['alpha'], 'r-',
                      label=f"D={r['D']:.3g}, α={r['alpha']:.2f}\n({r['motion_type']})")

        ax.set_xlabel('Lag time (s)')
        ax.set_ylabel(f'MSD ({_pos_unit()})')
        ax.set_title(f'Particle {particle_id} MSD')
        ax.legend(fontsize=8)

    fig.suptitle(f'Particle {particle_id}  (drift-corrected coordinates)', fontsize=12)
    _save(fig, f'track_{particle_id}.png')


def plot_drift(drift_df: pd.DataFrame):
    if drift_df.empty:
        return

    # tp.compute_drift() returns cumulative drift (cumsum of per-frame means)
    # drift_df['x'][f] = total x displacement from frame 0 to frame f
    per_frame = drift_df.diff().fillna(drift_df.iloc[[0]])

    fig, axes = plt.subplots(1, 3, figsize=(17, 4))

    # Panel 1: per-frame drift increment
    axes[0].plot(per_frame.index, per_frame['x'], label='x', alpha=0.7)
    axes[0].plot(per_frame.index, per_frame['y'], label='y', alpha=0.7)
    axes[0].set_xlabel('Frame')
    axes[0].set_ylabel('Drift per frame (pixels)')
    axes[0].set_title('Per-frame Drift')
    axes[0].legend()

    # Panel 2: cumulative drift vs frame
    axes[1].plot(drift_df.index, drift_df['x'], label='x cumulative', alpha=0.7)
    axes[1].plot(drift_df.index, drift_df['y'], label='y cumulative', alpha=0.7)
    axes[1].set_xlabel('Frame')
    axes[1].set_ylabel('Cumulative drift (pixels)')
    axes[1].set_title('Cumulative Drift vs Frame')
    axes[1].legend()

    # Panel 3: 2D cumulative drift path
    axes[2].plot(drift_df['x'], drift_df['y'], 'b-')
    axes[2].scatter(drift_df['x'].iloc[0], drift_df['y'].iloc[0],
                    color='green', zorder=5, label='start')
    axes[2].scatter(drift_df['x'].iloc[-1], drift_df['y'].iloc[-1],
                    color='red', zorder=5, label='end')
    axes[2].set_xlabel('Cumulative x drift (pixels)')
    axes[2].set_ylabel('Cumulative y drift (pixels)')
    axes[2].set_title('Cumulative Drift Path')
    axes[2].legend()

    fig.tight_layout()
    _save(fig, 'drift_correction.png')


def plot_msd_ensemble(emsd_df):
    # tp.emsd() returns a Series indexed by lag time (seconds)
    fig, ax = plt.subplots(figsize=(7, 5))

    lag = emsd_df.index.values.astype(float)
    msd_vals = emsd_df.values.astype(float)
    mask = (lag > 0) & np.isfinite(msd_vals) & (msd_vals > 0)

    ax.loglog(lag[mask], msd_vals[mask], 'ko', markersize=4, label='Ensemble MSD')

    if mask.sum() >= 4:
        try:
            def _power_law(t, D, alpha):
                return 4.0 * D * t ** alpha
            popt, _ = curve_fit(_power_law, lag[mask], msd_vals[mask],
                                p0=[1.0, 1.0], bounds=([0, 0], [np.inf, 3.0]))
            D, alpha = popt
            t_fit = np.logspace(np.log10(lag[mask].min()), np.log10(lag[mask].max()), 200)
            ax.loglog(t_fit, 4 * D * t_fit ** alpha, 'r-',
                      label=f'Fit: D={D:.3g}, α={alpha:.2f}')
        except (RuntimeError, ValueError):
            pass

    ax.set_xlabel('Lag time (s)')
    ax.set_ylabel(f'Ensemble MSD ({_pos_unit()})')
    ax.set_title('Ensemble Mean Squared Displacement')
    ax.legend()

    _save(fig, 'ensemble_msd.png')


def plot_diffusion_distribution(fit_results: dict):
    D_values = [r['D'] for r in fit_results.values()]
    if not D_values:
        return
    unit = 'µm²/s' if config.PIXEL_SIZE_NM else 'px²/s'

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(D_values, bins=20, edgecolor='black', color='steelblue')
    ax.axvline(float(np.median(D_values)), color='r', linestyle='--',
               label=f'median={np.median(D_values):.3g}')
    ax.set_xlabel(f'Diffusion Coefficient D ({unit})')
    ax.set_ylabel('Count')
    ax.set_title(f'D Distribution  (n={len(D_values)})\n'
                 f'mean={np.mean(D_values):.3g}  std={np.std(D_values):.3g}')
    ax.legend()

    _save(fig, 'diffusion_distribution.png')


def plot_alpha_distribution(fit_results: dict):
    alpha_values = [r['alpha'] for r in fit_results.values()]
    if not alpha_values:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(alpha_values, bins=20, edgecolor='black', color='coral')
    ax.axvline(1.0, color='k', linestyle='--', linewidth=1.5, label='Brownian (α=1)')
    ax.axvspan(0.85, 1.15, alpha=0.12, color='green', label='Brownian range')
    ax.axvline(float(np.median(alpha_values)), color='r', linestyle='--',
               label=f'median={np.median(alpha_values):.2f}')
    ax.set_xlabel('Anomalous Exponent α')
    ax.set_ylabel('Count')
    ax.set_title(f'α Distribution  (n={len(alpha_values)})\n'
                 f'mean={np.mean(alpha_values):.2f}  std={np.std(alpha_values):.2f}')
    ax.legend(fontsize=8)

    _save(fig, 'alpha_distribution.png')


def plot_motion_type_pie(fit_results: dict):
    counts = Counter(r['motion_type'] for r in fit_results.values())
    if not counts:
        return

    color_map = {'brownian': 'steelblue', 'confined': 'coral', 'directed': 'mediumseagreen'}
    labels = list(counts.keys())
    sizes = list(counts.values())
    colors = [color_map.get(l, 'gray') for l in labels]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(sizes,
           labels=[f'{l}\n({s}, {100*s/sum(sizes):.1f}%)' for l, s in zip(labels, sizes)],
           colors=colors, startangle=90, wedgeprops={'edgecolor': 'white', 'linewidth': 1.5})
    ax.set_title(f'Motion Type Distribution  (n={sum(sizes)} particles)')

    _save(fig, 'motion_type_distribution.png')


def _draw_marker(frame: np.ndarray, cx: int, cy: int, radius: int,
                 color: tuple, motion_type: str):
    """motion_type에 따라 다른 모양의 marker를 그린다."""
    if motion_type == 'confined':
        # 사각형
        cv2.rectangle(frame, (cx - radius, cy - radius),
                      (cx + radius, cy + radius), color, 1, cv2.LINE_AA)
    elif motion_type == 'directed':
        # 위쪽 방향 삼각형
        pts = np.array([[cx, cy - radius],
                        [cx - radius, cy + radius],
                        [cx + radius, cy + radius]], np.int32)
        cv2.polylines(frame, [pts.reshape(-1, 1, 2)], True, color, 1, cv2.LINE_AA)
    else:
        # brownian 또는 미분류 → 원
        cv2.circle(frame, (cx, cy), radius, color, 1, cv2.LINE_AA)


def _draw_legend(frame: np.ndarray, present_types: set, radius: int = 7):
    """오른쪽 위 코너에 운동 유형별 marker 범례를 그린다."""
    entries = [(t, t.capitalize()) for t in ('brownian', 'confined', 'directed')
               if t in present_types]
    if not entries:
        return

    H, W   = frame.shape[:2]
    row_h  = 24
    pad    = 8
    leg_w  = 115
    leg_h  = len(entries) * row_h + pad * 2
    x0, y0 = W - leg_w - 10, 10

    # 반투명 배경
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + leg_w, y0 + leg_h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    for i, (mtype, label) in enumerate(entries):
        cy = y0 + pad + i * row_h + row_h // 2
        cx = x0 + pad + radius + 2
        _draw_marker(frame, cx, cy, radius, (210, 210, 210), mtype)
        cv2.putText(frame, label, (cx + radius + 7, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)


def create_tracking_video(trajectories_df: pd.DataFrame, video_path: str,
                          fit_results: dict = None, circle_radius: int = 8):
    """원본 영상의 매 프레임마다 추적 중인 입자에 marker를 쳐서 영상 생성.

    fit_results가 주어지면 운동 유형(brownian/confined/directed)에 따라
    marker 모양(원/사각형/삼각형)을 다르게 표시하고 우상단에 범례를 추가한다.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  WARNING: 영상을 열 수 없어 추적 영상 생성 생략: {video_path}")
        return

    fps   = cap.get(cv2.CAP_PROP_FPS) or 10
    W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUT_DIR, 'tracking_video.mp4')
    fourcc   = cv2.VideoWriter_fourcc(*'mp4v')
    writer   = cv2.VideoWriter(out_path, fourcc, fps, (W, H))

    # 입자별 BGR 색상
    particles = sorted(trajectories_df['particle'].unique())
    cmap_src  = _get_cmap('tab20', max(len(particles), 1))
    bgr_map   = {}
    for i, pid in enumerate(particles):
        r, g, b, _ = cmap_src(i % 20)
        bgr_map[int(pid)] = (int(b * 255), int(g * 255), int(r * 255))

    # 입자별 운동 유형 매핑
    motion_map: dict[int, str] = {}
    if fit_results:
        for pid, res in fit_results.items():
            motion_map[int(pid)] = res.get('motion_type', 'brownian')
    present_types = set(motion_map.values()) if motion_map else set()

    # 프레임별로 {frame: [(pid, x, y), ...]} 인덱스 구성
    frame_index: dict[int, list] = {}
    for pid, grp in trajectories_df.groupby('particle'):
        for _, row in grp.iterrows():
            fi = int(row['frame'])
            frame_index.setdefault(fi, []).append(
                (int(pid), float(row['x']), float(row['y']))
            )

    max_frame = int(trajectories_df['frame'].max())

    for frame_idx in range(min(total, max_frame + 1)):
        ret, frame = cap.read()
        if not ret:
            break

        for pid, x, y in frame_index.get(frame_idx, []):
            cx, cy     = int(round(x)), int(round(y))
            color      = bgr_map[pid]
            mtype      = motion_map.get(pid, 'brownian')
            _draw_marker(frame, cx, cy, circle_radius, color, mtype)

        if present_types:
            _draw_legend(frame, present_types, radius=circle_radius - 1)

        cv2.putText(frame, f'frame {frame_idx:4d}', (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        writer.write(frame)

    cap.release()
    writer.release()
    print(f"  Saved: {out_path}")


def plot_angular_displacement(angular_dict: dict):
    """입자별 누적 각변위 vs 시간 (단위: degree)."""
    if not angular_dict:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    cmap = _get_cmap('tab20', max(len(angular_dict), 1))

    for i, (pid, df) in enumerate(sorted(angular_dict.items())):
        t = (df['frame'].values - df['frame'].values[0]) / config.FPS
        color = cmap(i % 20)
        # 왼쪽: 각변위 (Δθ)
        axes[0].plot(t, np.degrees(df['delta_theta_rad'].values),
                     lw=0.8, alpha=0.7, color=color, label=str(pid))
        # 오른쪽: 누적 각변위
        axes[1].plot(t, df['cumulative_deg'].values,
                     lw=0.8, alpha=0.7, color=color, label=str(pid))

    axes[0].axhline(0, color='k', lw=0.5, ls='--')
    axes[0].set_xlabel('Time (s)')
    axes[0].set_ylabel('Δθ (°)')
    axes[0].set_title('Angular displacement per frame')

    axes[1].axhline(0, color='k', lw=0.5, ls='--')
    axes[1].set_xlabel('Time (s)')
    axes[1].set_ylabel('Cumulative angle (°)')
    axes[1].set_title('Cumulative angular displacement')

    n = len(angular_dict)
    if n <= 20:
        axes[1].legend(title='particle', fontsize=6, ncol=2)

    fig.tight_layout()
    _save(fig, 'angular_displacement.png')


def plot_per_particle_cumulative_angular(angular_dict: dict):
    """30초 이상 tracking된 입자 개별 누적 각변위 — 입자당 한 subplot."""
    if not angular_dict:
        return

    pids = sorted(angular_dict.keys())
    n = len(pids)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows), squeeze=False)
    cmap = _get_cmap('tab20', max(n, 1))

    for idx, pid in enumerate(pids):
        ax = axes[idx // ncols][idx % ncols]
        df = angular_dict[pid]
        t = (df['frame'].values - df['frame'].values[0]) / config.FPS
        cum = df['cumulative_deg'].values
        color = cmap(idx % 20)
        ax.plot(t, cum, lw=1.0, color=color)
        ax.axhline(0, color='k', lw=0.5, ls='--')
        ax.set_title(f'particle {pid}', fontsize=8)
        ax.set_xlabel('Time (s)', fontsize=7)
        ax.set_ylabel('Cum. angle (°)', fontsize=7)
        ax.tick_params(labelsize=6)
        final = cum[-1]
        ax.annotate(f'{final:+.1f}°', xy=(t[-1], final),
                    xytext=(0.97, 0.05), textcoords='axes fraction',
                    ha='right', fontsize=7, color=color)

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(
        f'Per-particle cumulative angular displacement  (N={n}, ≥{config.ANGULAR_MIN_DURATION_S:.0f}s)',
        fontsize=10, y=1.01)
    fig.tight_layout()
    _save(fig, 'per_particle_cumulative_angular.png')


def plot_brightness_per_particle(brightness_dict: dict):
    """입자별 밝기(mass) 시계열 — 자전에 의한 주기적 변동 관찰."""
    if not brightness_dict:
        return

    pids = sorted(brightness_dict.keys())
    n = len(pids)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows + 0.8), squeeze=False)
    cmap = _get_cmap('tab20', max(n, 1))

    interp_text = (
        "【해석 가이드】  각 subplot = 개별 입자의 산란 밝기(mass) vs 시간\n"
        "• 평탄한 신호 → 방향 고정 또는 자전 없음\n"
        "• 주기적 진동 → Janus 입자 자전 가능성 (Au/Pt 면 교대 노출)\n"
        "• CV(변동계수) 높을수록 밝기 변동 큼 (자전 또는 포커스 이탈)"
    )
    fig.text(0.01, 0.99, interp_text, va='top', ha='left', fontsize=7.5,
             bbox=dict(boxstyle='round,pad=0.4', fc='lightyellow', ec='goldenrod', alpha=0.85))

    for idx, pid in enumerate(pids):
        ax = axes[idx // ncols][idx % ncols]
        df = brightness_dict[pid]
        t = df['time_s'].values
        mass = df['mass'].values
        color = cmap(idx % 20)

        ax.plot(t, mass, lw=0.7, color=color, alpha=0.85)
        ax.axhline(mass.mean(), color='k', lw=0.5, ls='--')

        cv = mass.std() / mass.mean() * 100 if mass.mean() > 0 else 0
        cv_color = 'red' if cv > 15 else ('orange' if cv > 8 else 'gray')
        ax.set_title(f'particle {pid}', fontsize=8)
        ax.set_xlabel('Time (s)', fontsize=7)
        ax.set_ylabel('Mass (a.u.)', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.annotate(f'CV={cv:.1f}%', xy=(0.97, 0.95), textcoords='axes fraction',
                    ha='right', va='top', fontsize=7, color=cv_color,
                    fontweight='bold' if cv > 8 else 'normal')

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(
        f'Per-particle brightness dynamics  (N={n}, ≥{config.ANGULAR_MIN_DURATION_S:.0f}s)\n'
        f'산란 밝기의 시간 변화 — 주기적 패턴이 있으면 자전(rotation) 신호',
        fontsize=9, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save(fig, 'brightness_per_particle.png')


def plot_brightness_acf(acf_dict: dict, fit_dict: dict = None):
    """입자별 밝기 ACF + 피팅 (Brownian decay / damped oscillation)."""
    if not acf_dict:
        return

    pids = sorted(acf_dict.keys())
    n = len(pids)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows + 1.2), squeeze=False)
    cmap = _get_cmap('tab20', max(n, 1))

    dt_ms = 1000.0 / config.FPS
    interp_text = (
        "【해석 가이드】  ACF(자기상관함수) = 밝기 변동이 시간차 τ 후에도 유지되는 정도\n"
        f"  프레임 간격 = {dt_ms:.0f} ms  |  관측 가능 최소 주기 = {2*dt_ms:.0f} ms (Nyquist)\n"
        "  ── (파란 점선) Brownian 모델: ACF = A·exp(−τ/τᵣ)  →  단조 감쇠 → 순수 브라운 자전\n"
        "  ── (빨간 실선) Rotation 모델: ACF = A·exp(−τ/τᵣ)·cos(ωτ)  →  감쇠 진동 → 자전 coupling 신호\n"
        "  ※ ACF ≈ 0 everywhere: Brownian 자전이 프레임 간격보다 빠름 (신호 감지 한계)"
    )
    fig.text(0.01, 0.99, interp_text, va='top', ha='left', fontsize=7,
             bbox=dict(boxstyle='round,pad=0.4', fc='#eef4ff', ec='steelblue', alpha=0.9))

    for idx, pid in enumerate(pids):
        ax = axes[idx // ncols][idx % ncols]
        df = acf_dict[pid]
        t = df['lag_time_s'].values
        acf_vals = df['acf'].values
        color = cmap(idx % 20)

        ax.plot(t, acf_vals, lw=0.8, color=color, alpha=0.85, label='ACF')
        ax.axhline(0, color='k', lw=0.5, ls='--')
        # 95% noise band (approx 1/sqrt(N) for uncorrelated signal)
        n_pts = len(acf_vals)
        noise = 1.96 / np.sqrt(n_pts)
        ax.axhspan(-noise, noise, alpha=0.08, color='gray', label=f'±95% noise ({noise:.2f})')

        result_label = ''
        if fit_dict and pid in fit_dict:
            fit = fit_dict[pid]
            t_fit = np.linspace(t[1], t[-1], 300)
            if 'brownian' in fit:
                r = fit['brownian']
                y_b = r['A'] * np.exp(-t_fit / r['tau_r']) + r['C0']
                ax.plot(t_fit, y_b, 'b--', lw=1.0, label=f"Brownian (τ={r['tau_r']:.2f}s)")
            if 'rotation' in fit:
                r = fit['rotation']
                y_r = r['A'] * np.exp(-t_fit / r['tau_r']) * np.cos(r['omega'] * t_fit) + r['C0']
                ax.plot(t_fit, y_r, 'r-', lw=1.2,
                        label=f"Rotation (T={r['period_s']:.2f}s)")
                result_label = f"⟳ T={r['period_s']:.2f}s"

        title_color = 'darkred' if result_label else 'black'
        ax.set_title(f'particle {pid}' + (f'\n{result_label}' if result_label else ''),
                     fontsize=8, color=title_color)
        ax.set_xlabel('Lag time τ (s)', fontsize=7)
        ax.set_ylabel('ACF C(τ)', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_ylim(-1.1, 1.1)
        ax.legend(fontsize=5, loc='upper right')

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(
        f'Per-particle brightness ACF  (N={n})\n'
        '단조 감쇠 → Brownian 자전만 존재 | 감쇠 진동 → translation-rotation coupling 가능성',
        fontsize=9, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    _save(fig, 'brightness_acf.png')


def plot_ensemble_brightness_acf(acf_dict: dict, fit_dict: dict = None):
    """앙상블 평균 밝기 ACF ± SEM.

    개별 입자 ACF를 lag별로 평균내어 noise를 줄인다.
    Brownian 기여(exp decay)를 제거한 잔차(residuals)도 별도 표시.
    """
    if not acf_dict:
        return

    lag_data: dict[int, list] = {}
    for df in acf_dict.values():
        for lag, val in zip(df['lag_frames'].values, df['acf'].values):
            lag_data.setdefault(int(lag), []).append(float(val))

    lags, means, sems, ns = [], [], [], []
    for lag in sorted(lag_data):
        vals = np.array(lag_data[lag])
        lags.append(lag)
        means.append(float(vals.mean()))
        sems.append(float(vals.std(ddof=1) / np.sqrt(len(vals))) if len(vals) > 1 else 0.0)
        ns.append(len(vals))

    lags = np.array(lags)
    means = np.array(means)
    sems = np.array(sems)
    t = lags / config.FPS

    # truncate to N/4 of shortest trajectory
    n_max = ns[0]
    valid = np.array(ns) >= n_max / config.ANGULAR_MIN_N_RATIO
    t, means, sems = t[valid], means[valid], sems[valid]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.subplots_adjust(top=0.78)

    dt_ms = 1000.0 / config.FPS
    header = (
        "【앙상블 밝기 ACF — 해석 가이드】\n"
        f"  프레임 간격 = {dt_ms:.0f} ms  →  Brownian 자전 (τᵣ ~ 수십 ms) 신호는 첫 lag에서 이미 소멸\n"
        "  ∴ lag ≥ 1 frame에서 유의미한 ACF가 존재하면 → 방향성 자전(directed rotation) 신호\n"
        "  [좌] 앙상블 평균 ACF + Brownian 지수감쇠 피팅   [우] Brownian 성분 제거 후 잔차"
    )
    fig.text(0.5, 0.97, header, ha='center', va='top', fontsize=8,
             bbox=dict(boxstyle='round,pad=0.5', fc='#fff8e8', ec='darkorange', alpha=0.92))

    # Panel 1: 앙상블 ACF
    axes[0].fill_between(t, means - 2 * sems, means + 2 * sems, alpha=0.25, color='steelblue',
                         label='95% CI')
    axes[0].plot(t, means, lw=1.5, color='steelblue', label='Ensemble ACF')
    axes[0].axhline(0, color='k', lw=0.7, ls='--')

    noise_band = 1.96 / np.sqrt(len(acf_dict))
    axes[0].axhspan(-noise_band, noise_band, alpha=0.1, color='gray',
                    label=f'±95% noise (N={len(acf_dict)})')

    axes[0].text(0.02, 0.05,
                 "단조 감쇠 → Brownian 자전 지배\n감쇠 진동 → directed rotation 존재\nACF ≈ 0 → 신호 감지 한계 (τᵣ < 프레임 간격)",
                 transform=axes[0].transAxes, fontsize=7, va='bottom',
                 bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='gray', alpha=0.8))

    # 앙상블 Brownian 피팅
    residuals_b = None
    popt_b = None
    if len(t) > 4:
        from scipy.optimize import curve_fit
        t_fit_data = t[1:]
        acf_fit_data = means[1:]
        try:
            def _model_b(x, A, tau_r, C0):
                return A * np.exp(-x / tau_r) + C0
            popt_b, _ = curve_fit(_model_b, t_fit_data, acf_fit_data,
                                  p0=[acf_fit_data[0], t_fit_data[-1] / 3, 0.0],
                                  bounds=([-2, 1e-6, -1], [2, 1e6, 1]), maxfev=5000)
            t_dense = np.linspace(t[1], t[-1], 300)
            axes[0].plot(t_dense, _model_b(t_dense, *popt_b), 'r--', lw=1.5,
                         label=f'Brownian fit\nτᵣ={popt_b[1]:.2f}s')
            residuals_b = acf_fit_data - _model_b(t_fit_data, *popt_b)
        except (RuntimeError, ValueError):
            pass

    axes[0].set_xlabel('Lag time τ (s)', fontsize=10)
    axes[0].set_ylabel('Ensemble ACF  C(τ)', fontsize=10)
    axes[0].set_title('① Ensemble brightness ACF', fontsize=10, fontweight='bold')
    axes[0].set_ylim(-1.1, 1.1)
    axes[0].legend(fontsize=8)

    # Panel 2: Brownian 제거 후 잔차
    if residuals_b is not None:
        res_std = float(np.std(residuals_b))
        axes[1].plot(t[1:], residuals_b, 'o-', lw=1.0, ms=4, color='steelblue', label='Residual')
        axes[1].axhline(0, color='k', lw=0.7, ls='--')
        axes[1].axhspan(-2 * res_std, 2 * res_std, alpha=0.12, color='gray',
                        label=f'±2σ noise ({2*res_std:.3f})')

        axes[1].text(0.02, 0.97,
                     "잔차 해석:\n"
                     "• 잔차 ≈ 0 (±2σ 내) → translation-rotation coupling 없음\n"
                     "• 잔차에 진동 패턴 → coupling에 의한 방향성 자전 가능성\n"
                     "  진동 주기 T ≈ 자전 주기",
                     transform=axes[1].transAxes, fontsize=7.5, va='top',
                     bbox=dict(boxstyle='round,pad=0.4', fc='#eeffee', ec='seagreen', alpha=0.9))

        axes[1].set_xlabel('Lag time τ (s)', fontsize=10)
        axes[1].set_ylabel('ACF residual', fontsize=10)
        axes[1].set_title('② Residuals after Brownian subtraction\n→ translation-rotation coupling signal?',
                          fontsize=9, fontweight='bold')
        axes[1].legend(fontsize=8)
    else:
        axes[1].text(0.5, 0.5, 'Brownian fit failed\n(ACF too noisy)', transform=axes[1].transAxes,
                     ha='center', va='center', fontsize=11, color='gray')
        axes[1].set_title('② Residuals (Brownian subtraction)', fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.78])
    _save(fig, 'ensemble_brightness_acf.png')


def plot_brightness_fft(fft_dict: dict):
    """입자별 밝기 FFT 파워 스펙트럼 — 자전 주파수 탐색."""
    if not fft_dict:
        return

    pids = sorted(fft_dict.keys())
    n = len(pids)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols
    nyquist = config.FPS / 2

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows + 1.0), squeeze=False)
    cmap = _get_cmap('tab20', max(n, 1))

    interp_text = (
        "【해석 가이드】  FFT 파워 스펙트럼 = 밝기 진동의 주파수 성분\n"
        f"  관측 가능 범위: 0 ~ {nyquist:.1f} Hz (Nyquist)  |  피크 주파수 f → 자전 주기 T = 1/f\n"
        "  • 1/f² 형태의 스펙트럼 → 브라운 노이즈 (자전 신호 없음)\n"
        "  • 특정 주파수에서 뚜렷한 피크 → 해당 주파수로 자전하는 입자 가능성\n"
        "  ⚠ 빨간 점선 = 최대 파워 지점 (노이즈 피크일 수 있음 — ACF로 교차 검증 필요)"
    )
    fig.text(0.01, 0.99, interp_text, va='top', ha='left', fontsize=7.5,
             bbox=dict(boxstyle='round,pad=0.4', fc='#f5eeff', ec='mediumpurple', alpha=0.9))

    for idx, pid in enumerate(pids):
        ax = axes[idx // ncols][idx % ncols]
        r = fft_dict[pid]
        color = cmap(idx % 20)

        ax.semilogy(r['freq'], r['power'], lw=0.8, color=color)
        ax.axvspan(0, r['freq'][0] if len(r['freq']) > 0 else 0.01,
                   alpha=0.15, color='gray')  # DC 근방

        if r['peak_freq'] > 0:
            ax.axvline(r['peak_freq'], color='r', lw=1.0, ls='--')
            ax.annotate(
                f"peak: {r['peak_freq']:.2f} Hz\nT = {r['peak_period_s']:.2f} s",
                xy=(0.97, 0.95), textcoords='axes fraction',
                ha='right', va='top', fontsize=6.5, color='darkred',
                bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='red', alpha=0.7))

        ax.set_title(f'particle {pid}', fontsize=8)
        ax.set_xlabel('Frequency (Hz)', fontsize=7)
        ax.set_ylabel('Power (a.u.)', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_xlim(left=0)

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(
        f'Brightness FFT power spectrum  (N={n})\n'
        f'Nyquist = {nyquist:.2f} Hz (T_min = {1/nyquist:.2f}s)  |  '
        f'뚜렷한 피크 = 자전 신호 후보, 1/f² 스펙트럼 = 브라운 노이즈',
        fontsize=9, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    _save(fig, 'brightness_fft.png')


def plot_ensemble_angular_displacement(ensemble_df: 'pd.DataFrame'):
    """앙상블 평균 누적 각변위 ± 95% CI vs 시간."""
    if ensemble_df is None or ensemble_df.empty:
        return

    t   = ensemble_df['lag_time_s'].values
    mu  = ensemble_df['mean_cumulative_deg'].values
    sem = ensemble_df['sem_cumulative_deg'].values
    n   = ensemble_df['n'].values

    ci95 = 2 * sem  # 95% CI (정규 근사)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.fill_between(t, mu - ci95, mu + ci95, alpha=0.25, label='95% CI')
    ax.plot(t, mu, lw=1.5, label='Ensemble mean')
    ax.axhline(0, color='k', lw=0.5, ls='--')

    # 오른쪽 y축에 입자 수 표시
    ax2 = ax.twinx()
    ax2.plot(t, n, lw=0.8, ls=':', color='gray', alpha=0.6)
    ax2.set_ylabel('N particles', color='gray', fontsize=9)
    ax2.tick_params(axis='y', labelcolor='gray')

    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Cumulative angle (°)')
    ax.set_title('Ensemble cumulative angular displacement')
    ax.legend()

    fig.tight_layout()
    _save(fig, 'ensemble_angular_displacement.png')
