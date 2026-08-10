"""
NTA Preview — IDE 실행용
========================
파라미터 튜닝용 preview 스크립트입니다.
영상 중간 프레임에서 입자 검출 결과를 확인합니다.
아래 [설정] 섹션의 값을 수정하고 실행하세요.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl_cache')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# ── [설정] 여기만 수정하세요 ──────────────────────────────────────────

VIDEO_FILE        = "test3_conv.mp4"   # input/ 디렉토리 안의 파일명

FPS               = 10
PARTICLE_DIAMETER = 5                  # 홀수, 픽셀 단위
MIN_MASS          = 200               # 최소 밝기 임계값

# ─────────────────────────────────────────────────────────────────────

import config

config.FPS               = FPS
config.PARTICLE_DIAMETER = PARTICLE_DIAMETER
config.MIN_MASS          = MIN_MASS

import io_video
import detection
from datetime import datetime

video_path = os.path.join(ROOT, "input", VIDEO_FILE)
if not os.path.isfile(video_path):
    raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}")

stem      = os.path.splitext(VIDEO_FILE)[0]
param_tag = f"d{PARTICLE_DIAMETER}_m{MIN_MASS}"
config.OUTPUT_DIR = os.path.join(ROOT, "output", stem, param_tag)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

print(f"=== Preview: {VIDEO_FILE} ===")
info    = io_video.get_video_info(video_path)
mid     = info['total_frames'] // 2
frame   = io_video.get_frame(video_path, mid)

save_path  = os.path.join(config.OUTPUT_DIR, "preview_detection.png")
f_detected = detection.preview_detection(frame, save_path=save_path)

print(f"Frame {mid} / {info['total_frames']}  |  검출 입자 수: {len(f_detected)}개")
print(f"Saved → {save_path}")

# 파라미터 로그 기록
notes_dir  = os.path.join(ROOT, "notes")
os.makedirs(notes_dir, exist_ok=True)
log_path   = os.path.join(notes_dir, f"{stem}.md")
is_new     = not os.path.isfile(log_path)
timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

entry = (
    f"\n## {timestamp}\n"
    f"- **검출 입자 수**: {len(f_detected)}개 (frame {mid})\n"
    f"- PARTICLE_DIAMETER: `{PARTICLE_DIAMETER}`\n"
    f"- MIN_MASS: `{MIN_MASS}`\n"
    f"- FPS: `{FPS}`\n"
    f"- PIXEL_SIZE_NM: `{config.PIXEL_SIZE_NM}`\n"
)
with open(log_path, "a") as f:
    if is_new:
        f.write(f"# Preview Log — {stem}\n")
    f.write(entry)

print(f"Log saved → {log_path}")
print("\nMIN_MASS / PARTICLE_DIAMETER를 수정하고 다시 실행해 파라미터를 튜닝하세요.")
