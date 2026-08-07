FPS = 10
PIXEL_SIZE_NM = None        # nm/pixel. None이면 픽셀 단위로 출력

# 입자 검출 파라미터 (--preview 로 확인하며 튜닝)
PARTICLE_DIAMETER = 5      # 홀수, 픽셀 단위 (입자 밝은 영역 직경)
MIN_MASS = 250              # 최소 밝기 임계값 (낮추면 더 많이 검출)

# 추적 파라미터
SEARCH_RANGE = 10           # 프레임 간 최대 이동 허용 픽셀
MEMORY = 3                  # 입자가 사라졌다 재등장 허용 프레임 수
MIN_TRAJECTORY_LENGTH = 20  # 분석에 포함할 최소 프레임 수

INPUT_DIR  = "input"
OUTPUT_DIR = "output"   # main.py에서 output/<영상이름>/으로 자동 설정됨
