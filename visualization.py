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

    ax.autoscale()
    ax.set_xlabel('x (pixels)')
    ax.set_ylabel('y (pixels)')
    ax.set_title(f'All Trajectories  (n={len(particles)} particles)\n'
                 f'○ start  ●  end  |  opacity: early → late')
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

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot(drift_df.index, drift_df['x'], label='x drift')
    axes[0].plot(drift_df.index, drift_df['y'], label='y drift')
    axes[0].set_xlabel('Frame')
    axes[0].set_ylabel('Drift per frame (pixels)')
    axes[0].set_title('Per-frame Drift')
    axes[0].legend()

    cx = drift_df['x'].cumsum()
    cy = drift_df['y'].cumsum()
    axes[1].plot(cx, cy, 'b-')
    axes[1].set_xlabel('Cumulative x drift (pixels)')
    axes[1].set_ylabel('Cumulative y drift (pixels)')
    axes[1].set_title('Cumulative Drift Path')

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


def create_tracking_video(trajectories_df: pd.DataFrame, video_path: str,
                          circle_radius: int = 8):
    """원본 영상의 매 프레임마다 추적 중인 입자에 동그라미를 쳐서 영상 생성."""
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
            cx, cy = int(round(x)), int(round(y))
            color  = bgr_map[pid]
            cv2.circle(frame, (cx, cy), circle_radius, color, 1, cv2.LINE_AA)

        cv2.putText(frame, f'frame {frame_idx:4d}', (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        writer.write(frame)

    cap.release()
    writer.release()
    print(f"  Saved: {out_path}")
