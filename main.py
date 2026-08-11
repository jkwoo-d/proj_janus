import argparse
import os
import sys
from datetime import datetime

os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl_cache')

import config
import io_video
import detection
import tracking
import analysis
import nta_stats
import visualization as viz

NOTES_DIR = "notes"


def _log_preview(video_stem: str, n_detected: int, frame_idx: int):
    os.makedirs(NOTES_DIR, exist_ok=True)
    log_path = os.path.join(NOTES_DIR, f"{video_stem}.md")
    is_new = not os.path.isfile(log_path)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"\n## {timestamp}\n"
        f"- **검출 입자 수**: {n_detected}개 (frame {frame_idx})\n"
        f"- PARTICLE_DIAMETER: `{config.PARTICLE_DIAMETER}`\n"
        f"- MIN_MASS: `{config.MIN_MASS}`\n"
        f"- SEARCH_RANGE: `{config.SEARCH_RANGE}`\n"
        f"- MEMORY: `{config.MEMORY}`\n"
        f"- MIN_TRAJECTORY_LENGTH: `{config.MIN_TRAJECTORY_LENGTH}`\n"
        f"- FPS: `{config.FPS}`\n"
        f"- PIXEL_SIZE_NM: `{config.PIXEL_SIZE_NM}`\n"
    )

    with open(log_path, "a") as f:
        if is_new:
            f.write(f"# Preview Log — {video_stem}\n")
        f.write(entry)

    print(f"  Log saved → {log_path}")


def run(args):
    # — config overrides —
    if args.fps is not None:
        config.FPS = args.fps
    if args.pixel_size is not None:
        config.PIXEL_SIZE_NM = args.pixel_size

    # 파일명만 입력한 경우 INPUT_DIR에서 찾음
    video_path = args.video
    if not os.path.isfile(video_path):
        candidate = os.path.join(config.INPUT_DIR, video_path)
        if os.path.isfile(candidate):
            video_path = candidate
        else:
            sys.exit(f"ERROR: video file not found: {video_path}\n"
                     f"       (searched in ./ and {config.INPUT_DIR}/)")

    # 영상 파일명(확장자 제외)으로 output 서브디렉토리 자동 설정
    stem = os.path.splitext(os.path.basename(video_path))[0]
    param_tag = f"d{config.PARTICLE_DIAMETER}_m{config.MIN_MASS}"
    config.OUTPUT_DIR = os.path.join("output", stem, param_tag)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # ── preview mode ───────────────────────────────────────────────────────────
    if args.preview:
        print("=== Preview Mode ===")
        info = io_video.get_video_info(video_path)
        mid = info['total_frames'] // 2
        frame = io_video.get_frame(video_path, mid)
        save_path = os.path.join(config.OUTPUT_DIR, 'preview_detection.png')
        f_detected = detection.preview_detection(frame, save_path=save_path)
        print(f"Saved → {save_path}")
        _log_preview(stem, n_detected=len(f_detected), frame_idx=mid)
        print("Adjust PARTICLE_DIAMETER / MIN_MASS in config.py and re-run --preview.")
        return

    # ── full analysis pipeline ─────────────────────────────────────────────────
    print(f"\n=== NTA Analysis: {video_path} ===")

    info = io_video.get_video_info(video_path)
    print(f"Video  {info['total_frames']} frames  |  {info['fps']:.1f} fps  |  "
          f"{info['width']}×{info['height']} px")

    if config.PIXEL_SIZE_NM is None:
        print("WARNING: PIXEL_SIZE_NM not set — results reported in pixel units. "
              "Use --pixel-size or set PIXEL_SIZE_NM in config.py for physical units.")
    else:
        print(f"Scale  {config.PIXEL_SIZE_NM} nm/pixel")

    # 1. Detect
    print("\n[1/5] Detecting particles...")
    frames_gen = io_video.load_video_frames(video_path)
    detected_df = detection.detect_particles(frames_gen)

    if detected_df.empty:
        sys.exit("No particles detected. Lower MIN_MASS or increase PARTICLE_DIAMETER in config.py.")

    n_frames = detected_df['frame'].nunique()
    n_per_frame = len(detected_df) / max(n_frames, 1)
    if n_per_frame > 500:
        sys.exit(
            f"프레임당 검출 수가 {n_per_frame:.0f}개로 너무 많습니다 (노이즈 과다).\n"
            f"  config.py에서 MIN_MASS를 높여주세요.\n"
            f"  현재: MIN_MASS={config.MIN_MASS}  →  50 이상으로 시작해보세요.\n"
            f"  --preview 로 먼저 확인 후 조정하세요."
        )

    # 2. Track
    print("\n[2/5] Linking trajectories...")
    trajectories = tracking.link_trajectories(detected_df)

    if trajectories.empty or trajectories['particle'].nunique() == 0:
        sys.exit("No trajectories found. Try lowering MIN_TRAJECTORY_LENGTH or SEARCH_RANGE in config.py.")

    # 3. Drift correction
    # 원본 좌표는 시각화(all_trajectories)에 사용, 보정된 좌표는 MSD 분석에 사용
    trajectories_original = trajectories.copy()
    drift_df = None
    if not args.no_drift:
        print("\n[3/5] Drift correction...")
        trajectories, drift_df = tracking.compute_and_correct_drift(trajectories)
        viz.plot_drift(drift_df)
    else:
        print("\n[3/5] Drift correction skipped (--no-drift).")

    # 4. MSD analysis
    print("\n[4/5] MSD analysis...")
    msd_dict = analysis.compute_msd_per_particle(trajectories)
    emsd_df = analysis.compute_ensemble_msd(trajectories)
    fit_results = analysis.fit_msd(msd_dict)
    print(f"  Fitted {len(fit_results)} / {trajectories['particle'].nunique()} trajectories")

    if not fit_results:
        print("WARNING: MSD fitting failed for all particles. "
              "Trajectories may be too short (increase MIN_TRAJECTORY_LENGTH).")

    # 5. Statistics + save
    print("\n[5/5] Computing statistics...")
    ensemble_stats, per_particle_df = nta_stats.compute_ensemble_stats(fit_results)
    nta_stats.save_results(ensemble_stats, per_particle_df)

    if not ensemble_stats.empty:
        print("\n=== Ensemble Statistics ===")
        print(ensemble_stats.T.to_string(header=False))

    # ── Visualisation ──────────────────────────────────────────────────────────
    print("\n=== Generating plots ===")
    bg_frame = io_video.get_frame(video_path, 0)

    # all_trajectories는 원본 좌표로 — drift 보정 후 좌표가 프레임 밖으로 나가는 문제 방지
    viz.plot_all_trajectories(trajectories_original, bg_frame)
    viz.plot_msd_ensemble(emsd_df)

    if fit_results:
        viz.plot_diffusion_distribution(fit_results)
        viz.plot_alpha_distribution(fit_results)
        viz.plot_motion_type_pie(fit_results)

    if args.plot_track is not None:
        viz.plot_single_trajectory(trajectories, args.plot_track, msd_dict, fit_results)

    if args.plot_all:
        n = trajectories['particle'].nunique()
        if n > 50:
            print(f"  WARNING: plotting {n} individual tracks — this may take a while.")
        for pid in sorted(trajectories['particle'].unique()):
            viz.plot_single_trajectory(trajectories, int(pid), msd_dict, fit_results)

    # 추적 영상 생성 (원본 좌표 사용 — 실제 영상 위치와 일치)
    print("\n  Generating tracking video...")
    viz.create_tracking_video(trajectories_original, video_path, fit_results)

    print(f"\nDone. All outputs → {config.OUTPUT_DIR}/")


def main():
    parser = argparse.ArgumentParser(
        description='Nanoparticle Tracking Analysis — dark-field microscopy video',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--video', required=True,
                        help='Path to AVI or MP4 video file')
    parser.add_argument('--preview', action='store_true',
                        help='Detect particles on the middle frame and exit\n'
                             '(use this to tune PARTICLE_DIAMETER / MIN_MASS in config.py)')
    parser.add_argument('--plot-track', type=int, default=None, metavar='ID',
                        help='Plot trajectory + MSD for the given particle ID')
    parser.add_argument('--plot-all', action='store_true',
                        help='Plot trajectory + MSD for every tracked particle')
    parser.add_argument('--no-drift', action='store_true',
                        help='Skip drift correction')
    parser.add_argument('--fps', type=float, default=None,
                        help='Frame rate in fps (overrides config.FPS)')
    parser.add_argument('--pixel-size', type=float, default=None, metavar='NM',
                        help='Pixel size in nm/pixel (overrides config.PIXEL_SIZE_NM)')

    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
