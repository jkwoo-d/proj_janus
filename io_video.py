import cv2
import numpy as np
import subprocess
from typing import Generator


def get_video_info(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    info = {
        'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        'fps': cap.get(cv2.CAP_PROP_FPS),
        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    cap.release()
    return info


def _read_frame_test(path: str) -> bool:
    """Return True if OpenCV can read a non-black frame from the video."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return False
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray.max() > 0


def _ffmpeg_frames(path: str, width: int, height: int) -> Generator[np.ndarray, None, None]:
    """Yield grayscale frames via ffmpeg pipe (fallback for formats OpenCV can't decode)."""
    cmd = [
        'ffmpeg', '-i', path,
        '-f', 'rawvideo', '-pix_fmt', 'gray',
        '-loglevel', 'error',
        'pipe:1',
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = width * height
    try:
        while True:
            data = proc.stdout.read(frame_bytes)
            if len(data) < frame_bytes:
                break
            yield np.frombuffer(data, dtype=np.uint8).reshape(height, width)
    finally:
        proc.stdout.close()
        proc.wait()


def load_video_frames(path: str) -> Generator[np.ndarray, None, None]:
    if _read_frame_test(path):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {path}")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        finally:
            cap.release()
    else:
        info = get_video_info(path)
        yield from _ffmpeg_frames(path, info['width'], info['height'])


def get_frame(path: str, frame_idx: int) -> np.ndarray:
    if _read_frame_test(path):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {path}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise ValueError(f"Cannot read frame {frame_idx} from {path}")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        info = get_video_info(path)
        cmd = [
            'ffmpeg', '-i', path,
            '-vf', f'select=eq(n\\,{frame_idx})',
            '-vframes', '1',
            '-f', 'rawvideo', '-pix_fmt', 'gray',
            '-loglevel', 'error',
            'pipe:1',
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        data, _ = proc.communicate()
        frame_bytes = info['width'] * info['height']
        if len(data) < frame_bytes:
            raise ValueError(f"Cannot read frame {frame_idx} from {path}")
        return np.frombuffer(data, dtype=np.uint8).reshape(info['height'], info['width'])
