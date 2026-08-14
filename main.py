import argparse
import os
import sys
from datetime import datetime

import pandas as pd

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


def _analyze_and_save(label: str,
                      trajectories_for_msd,
                      trajectories_original,
                      drift_df,
                      video_path: str,
                      output_dir: str,
                      args):
    """한 번의 분석 파이프라인 (drift 보정 여부만 다름)."""
    config.OUTPUT_DIR = output_dir
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'━'*55}")
    print(f"  [{label}]  →  {output_dir}/")
    print(f"{'━'*55}")

    if drift_df is not None:
        viz.plot_drift(drift_df)

    # MSD 분석
    msd_dict = analysis.compute_msd_per_particle(trajectories_for_msd)
    emsd_df = analysis.compute_ensemble_msd(trajectories_for_msd)
    fit_results = analysis.fit_msd(msd_dict)

    if drift_df is not None:
        fit_results = analysis.filter_drift_artifacts(
            fit_results, trajectories_original, trajectories_for_msd)

    fit_results, removed = analysis.filter_unreliable_fits(fit_results)
    n_total = trajectories_for_msd['particle'].nunique()
    print(f"  Fitted {len(fit_results)} / {n_total} trajectories"
          + (f"  ({len(removed)} outlier removed)" if removed else ""))
    if removed:
        for r in removed:
            print(f"    ✗ particle {r['particle']:>5}  {r['reason']}")

    if not fit_results:
        print("  WARNING: MSD fitting failed for all particles.")

    # 통계 저장 + 출력
    ensemble_stats, per_particle_df = nta_stats.compute_ensemble_stats(
        fit_results, trajectories_original, trajectories_for_msd)
    nta_stats.save_results(ensemble_stats, per_particle_df, removed)

    if not ensemble_stats.empty:
        print(f"\n=== Ensemble Statistics [{label}] ===")
        print(ensemble_stats.T.to_string(header=False))

    # 각변위 분석
    angular_dict = analysis.compute_angular_displacement(trajectories_for_msd)
    ensemble_angular_df = analysis.compute_ensemble_angular_stats(angular_dict)

    if not ensemble_angular_df.empty:
        ensemble_angular_df.to_csv(
            os.path.join(output_dir, 'ensemble_angular_stats.csv'), index=False)
    if angular_dict:
        per_angular = pd.concat(
            [df.assign(particle=pid) for pid, df in angular_dict.items()],
            ignore_index=True
        )[['particle', 'frame', 'theta_rad', 'delta_theta_rad', 'cumulative_rad', 'cumulative_deg']]
        per_angular.to_csv(
            os.path.join(output_dir, 'per_particle_angular.csv'), index=False)

    # 시각화
    bg_frame = io_video.get_frame(video_path, 0)
    viz.plot_all_trajectories(trajectories_original, bg_frame)
    viz.plot_msd_ensemble(emsd_df)
    viz.plot_angular_displacement(angular_dict)
    viz.plot_ensemble_angular_displacement(ensemble_angular_df)

    if fit_results:
        viz.plot_diffusion_distribution(fit_results)
        viz.plot_alpha_distribution(fit_results)
        viz.plot_motion_type_pie(fit_results)

    if args.plot_track is not None:
        viz.plot_single_trajectory(trajectories_for_msd, args.plot_track, msd_dict, fit_results)

    if args.plot_all:
        n = trajectories_for_msd['particle'].nunique()
        if n > 50:
            print(f"  WARNING: plotting {n} individual tracks — this may take a while.")
        for pid in sorted(trajectories_for_msd['particle'].unique()):
            viz.plot_single_trajectory(trajectories_for_msd, int(pid), msd_dict, fit_results)

    print(f"\n  Generating tracking video...")
    viz.create_tracking_video(trajectories_original, video_path, fit_results)
    print(f"  Done → {output_dir}/")


def run(args):
    # 1. 영상 경로 확정 + stem 추출
    video_path = args.video
    if not os.path.isfile(video_path):
        candidate = os.path.join(config.INPUT_DIR, video_path)
        if os.path.isfile(candidate):
            video_path = candidate
        else:
            sys.exit(f"ERROR: video file not found: {video_path}\n"
                     f"       (searched in ./ and {config.INPUT_DIR}/)")

    stem = os.path.splitext(os.path.basename(video_path))[0]

    # 2. CLI 인자 적용 (지정된 경우 config.py 기본값 덮어씀)
    if args.diameter is not None:
        config.PARTICLE_DIAMETER = args.diameter
    if args.min_mass is not None:
        config.MIN_MASS = args.min_mass
    if args.fps is not None:
        config.FPS = args.fps
    if args.pixel_size is not None:
        config.PIXEL_SIZE_NM = args.pixel_size

    param_tag = f"d{config.PARTICLE_DIAMETER}_m{config.MIN_MASS}"
    stem_output_dir = os.path.join("output", stem)

    # ── preview mode ───────────────────────────────────────────────────────────
    if args.preview:
        print("=== Preview Mode ===")
        os.makedirs(stem_output_dir, exist_ok=True)
        info = io_video.get_video_info(video_path)
        mid = info['total_frames'] // 2
        frame = io_video.get_frame(video_path, mid)
        save_path = os.path.join(stem_output_dir, f"preview_{param_tag}.png")
        f_detected = detection.preview_detection(frame, save_path=save_path)
        print(f"Saved → {save_path}")
        _log_preview(stem, n_detected=len(f_detected), frame_idx=mid)
        print("Adjust PARTICLE_DIAMETER / MIN_MASS in config.py and re-run --preview.")
        return

    # base output 디렉토리 (drift/no_drift 공통 상위) — 실제 분석 시에만 생성
    base_output_dir = os.path.join(stem_output_dir, param_tag)
    os.makedirs(base_output_dir, exist_ok=True)
    config.OUTPUT_DIR = base_output_dir

    print(f"\n=== NTA Analysis: {video_path} ===")

    info = io_video.get_video_info(video_path)
    print(f"Video  {info['total_frames']} frames  |  {info['fps']:.1f} fps  |  "
          f"{info['width']}×{info['height']} px")

    if config.PIXEL_SIZE_NM is None:
        print("WARNING: PIXEL_SIZE_NM not set — results reported in pixel units.")
    else:
        print(f"Scale  {config.PIXEL_SIZE_NM} nm/pixel")

    # [1/3] Detect
    print("\n[1/3] Detecting particles...")
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
            f"  현재: MIN_MASS={config.MIN_MASS}\n"
            f"  --preview 로 먼저 확인 후 조정하세요."
        )

    # [2/3] Track
    print("\n[2/3] Linking trajectories...")
    trajectories = tracking.link_trajectories(detected_df)

    if trajectories.empty or trajectories['particle'].nunique() == 0:
        sys.exit("No trajectories found. Try lowering MIN_TRAJECTORY_LENGTH or SEARCH_RANGE.")

    trajectories_original = trajectories.copy()

    # [3/3] Drift correction (공통 계산 — 두 모드에서 재사용)
    print("\n[3/3] Computing drift...")
    trajectories_corr, drift_df = tracking.compute_and_correct_drift(trajectories.copy())

    # ── 앙상블 평균 변위 벡터 비교 ────────────────────────────────────────────
    vm_orig = nta_stats.compute_vector_mean_displacement(trajectories_original)
    vm_corr = nta_stats.compute_vector_mean_displacement(trajectories_corr)
    u = vm_orig['unit']
    print(f"\n=== 앙상블 평균 변위 벡터 (N={vm_orig['n']} particles) ===")
    print(f"  {'':12}  ⟨Δx⟩       ⟨Δy⟩       |⟨Δr⟩|")
    print(f"  {'원본':12}  {vm_orig['mean_dx']:+7.2f} {u}  {vm_orig['mean_dy']:+7.2f} {u}  {vm_orig['magnitude']:6.2f} {u}")
    print(f"  {'drift 보정후':12}  {vm_corr['mean_dx']:+7.2f} {u}  {vm_corr['mean_dy']:+7.2f} {u}  {vm_corr['magnitude']:6.2f} {u}")

    # ── 두 모드 분석 ───────────────────────────────────────────────────────────
    print("\n=== Generating plots ===")

    _analyze_and_save(
        label="drift 보정",
        trajectories_for_msd=trajectories_corr,
        trajectories_original=trajectories_original,
        drift_df=drift_df,
        video_path=video_path,
        output_dir=os.path.join(base_output_dir, "drift"),
        args=args,
    )

    _analyze_and_save(
        label="drift 미보정",
        trajectories_for_msd=trajectories_original,
        trajectories_original=trajectories_original,
        drift_df=None,
        video_path=video_path,
        output_dir=os.path.join(base_output_dir, "no_drift"),
        args=args,
    )

    print(f"\nDone. All outputs → {base_output_dir}/")
    print(f"  ├── drift/      (drift 보정 결과)")
    print(f"  └── no_drift/   (drift 미보정 결과)")


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
    parser.add_argument('--diameter', type=int, default=None, metavar='PX',
                        help='Particle diameter in pixels, odd number (overrides config.PARTICLE_DIAMETER)')
    parser.add_argument('--min-mass', type=int, default=None, metavar='VAL',
                        help='Minimum brightness threshold (overrides config.MIN_MASS)')
    parser.add_argument('--fps', type=float, default=None,
                        help='Frame rate in fps (overrides config.FPS)')
    parser.add_argument('--pixel-size', type=float, default=None, metavar='NM',
                        help='Pixel size in nm/pixel (overrides config.PIXEL_SIZE_NM)')

    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
