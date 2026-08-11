"""
NTA Analysis — IDE 실행용
========================
CLI 없이 IDE(PyCharm, VSCode 등)에서 바로 실행할 수 있는 스크립트입니다.
아래 [설정] 섹션의 값만 수정하고 파일 전체를 실행하세요.

영상 파일은 ide_runner/input/ 디렉토리에 넣어주세요.
분석 결과는 ide_runner/output/ 디렉토리에 저장됩니다.
"""

import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl_cache')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── [설정] 여기만 수정하세요 ──────────────────────────────────────────

VIDEO_FILE            = "test3_conv.mp4"   # input/ 디렉토리 안의 파일명

FPS                   = 10
PIXEL_SIZE_NM         = None               # nm/pixel. None이면 픽셀 단위 출력

PARTICLE_DIAMETER     = 5                  # 홀수, 픽셀 단위
MIN_MASS              = 200               # 최소 밝기 임계값
SEARCH_RANGE          = 10                # 프레임 간 최대 이동 허용 픽셀
MEMORY                = 3                 # 소실 후 재등장 허용 프레임 수
MIN_TRAJECTORY_LENGTH = 20               # 분석에 포함할 최소 프레임 수

NO_DRIFT              = False             # True면 drift 보정 생략
PLOT_TRACK_ID         = None             # 특정 입자 ID 개별 분석 (None이면 생략)
PLOT_ALL              = False            # True면 모든 입자 개별 분석

# ─────────────────────────────────────────────────────────────────────

import config

config.FPS                   = FPS
config.PIXEL_SIZE_NM         = PIXEL_SIZE_NM
config.PARTICLE_DIAMETER     = PARTICLE_DIAMETER
config.MIN_MASS              = MIN_MASS
config.SEARCH_RANGE          = SEARCH_RANGE
config.MEMORY                = MEMORY
config.MIN_TRAJECTORY_LENGTH = MIN_TRAJECTORY_LENGTH

import io_video
import detection
import tracking
import analysis
import nta_stats
import visualization as viz

# 경로 설정
video_path = os.path.join(ROOT, "input", VIDEO_FILE)
if not os.path.isfile(video_path):
    raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}\n"
                            f"ide_runner/input/ 폴더에 영상 파일을 넣어주세요.")

stem      = os.path.splitext(VIDEO_FILE)[0]
param_tag = f"d{PARTICLE_DIAMETER}_m{MIN_MASS}"
config.OUTPUT_DIR = os.path.join(ROOT, "output", stem, param_tag)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

# ── 1. 영상 정보 ──────────────────────────────────────────────────────

print(f"\n=== NTA Analysis: {VIDEO_FILE} ===")
info = io_video.get_video_info(video_path)
print(f"Video  {info['total_frames']} frames  |  {info['fps']:.1f} fps  "
      f"|  {info['width']}×{info['height']} px")

if PIXEL_SIZE_NM is None:
    print("WARNING: PIXEL_SIZE_NM not set — 결과가 픽셀 단위로 출력됩니다.")
else:
    print(f"Scale  {PIXEL_SIZE_NM} nm/pixel")

# ── 2. 입자 검출 ──────────────────────────────────────────────────────

print("\n[1/5] Detecting particles...")
frames_gen  = io_video.load_video_frames(video_path)
detected_df = detection.detect_particles(frames_gen)

if detected_df.empty:
    raise RuntimeError("입자가 검출되지 않았습니다. MIN_MASS를 낮추거나 PARTICLE_DIAMETER를 조정하세요.")

n_per_frame = len(detected_df) / detected_df['frame'].nunique()
if n_per_frame > 500:
    raise RuntimeError(
        f"프레임당 검출 수가 {n_per_frame:.0f}개로 너무 많습니다 (노이즈 과다).\n"
        f"MIN_MASS를 높여주세요. 현재: {MIN_MASS}"
    )

# ── 3. Trajectory 링킹 ───────────────────────────────────────────────

print("\n[2/5] Linking trajectories...")
trajectories = tracking.link_trajectories(detected_df)

if trajectories.empty or trajectories['particle'].nunique() == 0:
    raise RuntimeError("Trajectory가 없습니다. MIN_TRAJECTORY_LENGTH 또는 SEARCH_RANGE를 조정하세요.")

# ── 4. Drift 보정 ─────────────────────────────────────────────────────

trajectories_original = trajectories.copy()
drift_df = None

if not NO_DRIFT:
    print("\n[3/5] Drift correction...")
    trajectories, drift_df = tracking.compute_and_correct_drift(trajectories)
    viz.plot_drift(drift_df)
else:
    print("\n[3/5] Drift correction skipped.")

# ── 5. MSD 분석 ───────────────────────────────────────────────────────

print("\n[4/5] MSD analysis...")
msd_dict    = analysis.compute_msd_per_particle(trajectories)
emsd_df     = analysis.compute_ensemble_msd(trajectories)
fit_results = analysis.fit_msd(msd_dict)
print(f"  Fitted {len(fit_results)} / {trajectories['particle'].nunique()} trajectories")

# ── 6. 통계 ───────────────────────────────────────────────────────────

print("\n[5/5] Computing statistics...")
ensemble_stats, per_particle_df = nta_stats.compute_ensemble_stats(fit_results)
nta_stats.save_results(ensemble_stats, per_particle_df)

if not ensemble_stats.empty:
    print("\n=== Ensemble Statistics ===")
    print(ensemble_stats.T.to_string(header=False))

# ── 7. 시각화 ─────────────────────────────────────────────────────────

print("\n=== Generating plots ===")
bg_frame = io_video.get_frame(video_path, 0)

viz.plot_all_trajectories(trajectories_original, bg_frame)
viz.plot_msd_ensemble(emsd_df)

if fit_results:
    viz.plot_diffusion_distribution(fit_results)
    viz.plot_alpha_distribution(fit_results)
    viz.plot_motion_type_pie(fit_results)

if PLOT_TRACK_ID is not None:
    viz.plot_single_trajectory(trajectories, PLOT_TRACK_ID, msd_dict, fit_results)

if PLOT_ALL:
    for pid in sorted(trajectories['particle'].unique()):
        viz.plot_single_trajectory(trajectories, int(pid), msd_dict, fit_results)

print("\n  Generating tracking video...")
viz.create_tracking_video(trajectories_original, video_path, fit_results)

print(f"\nDone. All outputs → {config.OUTPUT_DIR}/")
