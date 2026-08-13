# Nanoparticle Tracking Analysis (NTA)

100배율 암시야(dark-field) 현미경으로 촬영한 AVI/MP4 영상에서 나노입자의 trajectory를 추출하고 운동 특성을 분석하는 CLI 도구입니다.

암시야 현미경은 어두운 배경에 나노입자가 밝은 점으로 보이는 방식으로, 이 코드는 각 프레임에서 밝은 점을 검출하고 프레임 간 연결(linking)을 통해 각 입자의 이동 경로를 추적합니다. 추적된 경로에서 MSD(Mean Squared Displacement)를 계산해 입자의 확산계수 D와 운동 유형(Brownian / confined / directed)을 분류합니다.

---

## 환경별 실행 방법

### Linux — 터미널(CLI)로 실행

**1. 필수 프로그램 설치**

```bash
# Python 패키지
pip install -r requirements.txt

# ffmpeg (AVI 변환용)
sudo apt install ffmpeg
```

**2. 실행**

```bash
# 파라미터 튜닝
python3 main.py --video video_conv.mp4 --preview

# 전체 분석
python3 main.py --video video_conv.mp4
```

`main.py`와 `input/`, `output/` 디렉토리를 기준으로 동작합니다.

---

### Windows — PyCharm IDE로 실행

Windows에서는 터미널 대신 PyCharm IDE를 통해 `ide_runner/` 폴더만으로 실행합니다.

**1. Python 설치**

[python.org/downloads](https://www.python.org/downloads/) 에서 Python 3.10 이상을 다운로드해 설치합니다.
설치 시 **"Add Python to PATH"** 체크박스를 반드시 체크합니다.

**2. PyCharm 설치**

[jetbrains.com/pycharm/download](https://www.jetbrains.com/pycharm/download/) 에서 Community Edition(무료)을 다운로드해 설치합니다.

**3. ffmpeg 설치 (AVI 디코딩 및 변환용)**

[ffmpeg.org/download.html](https://ffmpeg.org/download.html) → Windows 빌드 다운로드 후 압축 해제.
`ffmpeg.exe`가 있는 `bin/` 폴더 경로를 Windows 환경변수 PATH에 추가합니다.

> PATH 추가 방법: 시스템 속성 → 고급 → 환경 변수 → Path → 편집 → 새로 만들기 → `C:\ffmpeg\bin` 입력

**4. 저장소 클론**

```bash
git clone https://github.com/jkwoo-d/proj_janus.git
```

또는 GitHub에서 ZIP으로 다운로드 후 압축 해제합니다.

**5. PyCharm에서 프로젝트 열기**

PyCharm 실행 → `Open` → `proj_janus/ide_runner/` 폴더 선택.

**6. Python 인터프리터 설정**

`File > Settings > Project > Python Interpreter` → Python 3.10+ 선택.
우측 `+` 버튼을 눌러 아래 패키지를 설치합니다.

```
trackpy
opencv-python
numpy
scipy
matplotlib
pandas
pims
```

또는 PyCharm 하단 터미널에서:

```bash
pip install -r ../requirements.txt
```

**7. 영상 파일 준비**

- AVI 파일은 먼저 ffmpeg로 변환합니다 (PowerShell 또는 cmd에서 실행):

```bash
ffmpeg -i video.avi -c:v libx264 -pix_fmt yuv420p video_conv.mp4
```

- 변환된 MP4 파일을 `ide_runner/input/` 폴더에 넣습니다.

**8. 파라미터 튜닝 및 분석 실행**

`ide_runner/run_preview.py` 열기 → 상단 `[설정]` 섹션에서 `VIDEO_FILE` 등 수정 → ▶ 버튼 클릭.

결과 이미지(`preview_detection.png`)를 확인하며 `MIN_MASS`, `PARTICLE_DIAMETER`를 조정합니다.
파라미터가 확정되면 `run_analysis.py`를 같은 방식으로 실행합니다.

모든 결과 파일은 `ide_runner/output/{영상이름}/d{diameter}_m{min_mass}/`에 저장됩니다.

---

## 설치 (Linux CLI 전용)

```bash
pip install -r requirements.txt
```

---

## 분석 워크플로우

### Step 1 — 입력 영상 준비

영상 파일을 `input/` 디렉토리에 넣습니다. AVI와 MP4 모두 지원합니다.

DV 카메라 등 일부 AVI 코덱(yuv411p 등)은 OpenCV가 직접 디코딩하지 못하는 경우가 있습니다. 이 경우 ffmpeg를 통해 자동으로 읽도록 fallback이 내장되어 있으므로 별도 변환 없이 AVI 파일을 그대로 사용할 수 있습니다. 다만 ffmpeg pipe 방식은 속도가 느리므로, 반복 분석이 필요하다면 미리 MP4로 변환해두는 것을 권장합니다.

```bash
ffmpeg -i input/video.avi -c:v libx264 -pix_fmt yuv420p input/video.mp4
```

---

### Step 2 — 검출 파라미터 튜닝 (`--preview`)

실제 분석 전에 반드시 먼저 실행합니다. 영상 중간 프레임 한 장에서 입자를 검출하고 결과 이미지를 저장합니다. 이 단계에서 파라미터를 조정해 노이즈를 배제하고 실제 입자만 포착되는 조건을 찾습니다.

```bash
python3 main.py --video video_conv.mp4 --preview
```

생성 파일: `output/{영상이름}/preview_d{diameter}_m{min_mass}.png`

> **참고**: `--preview`는 파라미터 서브디렉토리를 생성하지 않습니다. 파일명에 파라미터가 포함되어 있어 파라미터를 바꿔가며 실행해도 덮어쓰이지 않습니다.

**`preview_detection.png` 해석 방법**
- 영상 프레임 위에 검출된 입자 위치가 원으로 표시됩니다.
- 원이 실제 밝은 입자 위치에 잘 얹혀 있어야 합니다.
- 노이즈나 배경이 원으로 잡힌다 → `MIN_MASS`를 높임
- 실제 입자가 잡히지 않는다 → `MIN_MASS`를 낮춤
- 원의 크기가 입자와 맞지 않는다 → `PARTICLE_DIAMETER` 조정 (반드시 홀수)

파라미터를 바꿀 때마다 `config.py`를 수정하고 `--preview`를 반복 실행합니다. 각 실행 결과는 `notes/{영상이름}.md`에 자동 기록됩니다.

---

### Step 3 — 전체 분석 실행

파라미터가 확정되면 전체 파이프라인을 실행합니다.

```bash
python3 main.py --video video_conv.mp4
```

내부적으로 아래 순서로 처리됩니다.

```
[1/3] 프레임별 입자 검출 (trackpy Crocker-Grier 알고리즘)
        ↓
[2/3] Trajectory 링킹 + 짧은 track 제거 (MIN_TRAJECTORY_LENGTH 미만 제외)
        ↓
[3/3] Drift 계산 (앙상블 평균 변위 산출)
        ↓
      ┌─────────────────────────┬─────────────────────────┐
      │ drift/                  │ no_drift/               │
      │ drift 보정 후 MSD 분석  │ drift 미보정 MSD 분석   │
      └─────────────────────────┴─────────────────────────┘
      각 디렉토리에 통계·시각화 저장
```

출력 파일은 `output/{영상이름}/d{diameter}_m{min_mass}/drift/` 및 `no_drift/` 두 디렉토리에 동시 저장됩니다.

---

### Step 4 — 개별 입자 분석 (선택)

특정 입자의 trajectory와 MSD를 개별 확인하고 싶을 때 사용합니다.

```bash
# 특정 입자 ID 하나
python3 main.py --video video_conv.mp4 --plot-track 5

# 모든 입자 개별 출력
python3 main.py --video video_conv.mp4 --plot-all
```

---

## IDE에서 실행하기 (PyCharm / VSCode)

터미널 없이 PyCharm, VSCode 등 IDE에서 Run 버튼으로 바로 실행할 수 있도록 `ide_runner/` 디렉토리에 별도 스크립트가 준비되어 있습니다.

```
ide_runner/
├── run_preview.py    # 파라미터 튜닝용 preview 실행
└── run_analysis.py   # 전체 분석 파이프라인 실행
```

### PyCharm 설정 방법

1. PyCharm에서 `proj_janus/` 폴더를 프로젝트로 엽니다.
2. 우측 상단 또는 `File > Settings > Project > Python Interpreter`에서 Python 인터프리터를 설정합니다.
   - 패키지가 설치된 환경(venv 또는 시스템 Python)을 선택합니다.
3. 왼쪽 파일 트리에서 `ide_runner/run_preview.py` 또는 `ide_runner/run_analysis.py`를 엽니다.
4. 파일 상단 `[설정]` 섹션에서 파라미터를 수정합니다.
5. 편집창 우클릭 → `Run 'run_preview'` 또는 상단 ▶ 버튼을 클릭합니다.

### VSCode 설정 방법

1. VSCode에서 `proj_janus/` 폴더를 엽니다.
2. `Ctrl+Shift+P` → `Python: Select Interpreter`로 인터프리터를 지정합니다.
3. `ide_runner/run_preview.py` 또는 `ide_runner/run_analysis.py`를 엽니다.
4. 파일 상단 `[설정]` 섹션을 수정합니다.
5. 우측 상단 ▶ 버튼 또는 `F5`로 실행합니다.

---

### run_preview.py — 파라미터 튜닝

전체 분석 전에 파라미터가 적절한지 확인합니다. 영상 중간 프레임 한 장만 처리하므로 수 초 내에 완료됩니다.

수정해야 할 부분 (`[설정]` 섹션):

```python
VIDEO_FILE        = "test3_conv.mp4"   # ← 분석할 영상 파일명으로 변경
FPS               = 10                 # ← 영상 프레임 레이트
PARTICLE_DIAMETER = 5                  # ← 홀수로 설정, 입자 크기에 맞게 조정
MIN_MASS          = 200               # ← 낮추면 더 많이 검출, 높이면 노이즈 제거
```

실행하면 `output/{영상이름}/d{diameter}_m{min_mass}/preview_detection.png`가 생성됩니다. 이 이미지를 열어 원이 실제 입자 위에 잘 얹혀 있는지 확인합니다. 맞지 않으면 `MIN_MASS`나 `PARTICLE_DIAMETER`를 수정하고 다시 실행합니다.

---

### run_analysis.py — 전체 분석

preview에서 파라미터가 확정되면 이 파일을 실행합니다. 전체 영상을 처리하므로 영상 길이에 따라 수십 초~수 분이 소요됩니다.

수정해야 할 부분 (`[설정]` 섹션):

```python
VIDEO_FILE            = "test3_conv.mp4"   # ← 분석할 영상 파일명
FPS                   = 10                 # ← 영상 프레임 레이트
PIXEL_SIZE_NM         = None              # ← nm/pixel 값 (모르면 None 유지)

PARTICLE_DIAMETER     = 5                  # ← preview에서 확정한 값
MIN_MASS              = 200               # ← preview에서 확정한 값
SEARCH_RANGE          = 10                # ← 입자가 빠르면 증가
MEMORY                = 3                 # ← 입자 소실 허용 프레임 수
MIN_TRAJECTORY_LENGTH = 20               # ← 이 프레임 수 미만인 track은 제외

NO_DRIFT              = False             # ← True면 drift 보정 생략
PLOT_TRACK_ID         = None             # ← 특정 입자 ID 개별 분석 (예: 5)
PLOT_ALL              = False            # ← True면 모든 입자 개별 분석
```

실행이 완료되면 `output/{영상이름}/d{diameter}_m{min_mass}/` 에 모든 결과 파일이 저장되고 터미널(Run 창)에 앙상블 통계가 출력됩니다.

---

### 파라미터를 바꿔가며 비교할 때

`MIN_MASS` 등을 바꾸면 출력 디렉토리가 자동으로 달라집니다. 예를 들어:

```
output/test3_conv/d5_m200/   ← MIN_MASS=200으로 분석한 결과
output/test3_conv/d5_m150/   ← MIN_MASS=150으로 분석한 결과
```

두 결과를 나란히 열어 비교할 수 있으며, 서로 덮어쓰이지 않습니다.

---

## 전체 옵션

```
python3 main.py --video VIDEO [옵션]

필수:
  --video VIDEO         분석할 영상 파일명 (input/ 디렉토리에서 자동 검색)

선택:
  --preview             중간 프레임 검출 결과만 확인하고 종료 (파라미터 튜닝용)
  --diameter PX         입자 직경 픽셀 (홀수, config.py의 PARTICLE_DIAMETER 오버라이드)
  --min-mass VAL        최소 밝기 임계값 (config.py의 MIN_MASS 오버라이드)
  --fps FPS             프레임 레이트 (config.py의 FPS 오버라이드)
  --pixel-size NM       픽셀 크기 nm/pixel (설정 시 결과가 물리 단위로 출력)
  --plot-track ID       특정 입자 ID의 trajectory + MSD 그래프 생성
  --plot-all            모든 입자의 trajectory + MSD 그래프 개별 생성
```

---

## 출력 파일 설명

출력 경로: `output/{영상이름}/d{PARTICLE_DIAMETER}_m{MIN_MASS}/`

```
output/{영상이름}/
├── preview_d{diameter}_m{min_mass}.png   ← --preview 결과 (파라미터별 별도 저장)
└── d{diameter}_m{min_mass}/
    ├── drift/                            ← drift 보정 후 분석 결과
    │   ├── drift_correction.png
    │   ├── all_trajectories.png
    │   ├── ensemble_msd.png
    │   ├── ensemble_stats.csv
    │   ├── per_particle_results.csv
    │   ├── ensemble_angular_stats.csv
    │   ├── per_particle_angular.csv
    │   ├── angular_displacement.png
    │   ├── ensemble_angular_displacement.png
    │   ├── diffusion_distribution.png
    │   ├── alpha_distribution.png
    │   ├── motion_type_distribution.png
    │   └── tracking_video.mp4
    └── no_drift/                         ← drift 미보정 분석 결과
        ├── all_trajectories.png
        ├── ensemble_msd.png
        ├── ensemble_stats.csv
        ├── per_particle_results.csv
        ├── ensemble_angular_stats.csv
        ├── per_particle_angular.csv
        ├── angular_displacement.png
        ├── ensemble_angular_displacement.png
        ├── diffusion_distribution.png
        ├── alpha_distribution.png
        ├── motion_type_distribution.png
        └── tracking_video.mp4
```

### `drift/` vs `no_drift/` — 두 결과의 차이

전체 분석 실행 시 drift 보정 여부에 따라 두 결과를 동시에 저장합니다. 비교를 통해 어느 결과가 실험 상황에 더 적합한지 판단할 수 있습니다.

| | `drift/` | `no_drift/` |
|---|---|---|
| **MSD 분석 대상** | drift 보정된 궤적 | 원본 궤적 |
| **적합한 상황** | bulk flow 또는 stage drift가 있는 실험 | 유체 흐름이 없는 순수 확산 실험 |
| **주의** | 정지 입자가 drift 반대 방향으로 움직이는 artifact 가능 (자동 필터 적용) | bulk flow가 있으면 drift 영향이 MSD에 포함되어 α가 과대 추정될 수 있음 |

**drift 보정 원리**: 모든 입자의 앙상블 평균 변위를 프레임마다 계산하고, 이를 개별 궤적에서 차감합니다. 이로써 stage drift나 유체 흐름(bulk flow) 같은 공통 이동을 제거하고 입자 고유의 운동만 남깁니다.

---

### `preview_detection.png` — 검출 파라미터 확인용

`--preview` 모드에서 생성됩니다. 영상 중간 프레임 위에 검출된 입자 위치를 원으로 표시합니다. 파라미터 튜닝의 기준이 되는 이미지로, 실제 분석 전 이 이미지를 통해 `MIN_MASS`와 `PARTICLE_DIAMETER`를 조정합니다. 검출이 잘 된 조건이 확인되면 전체 분석을 실행합니다.

---

### `all_trajectories.png` — 전체 입자 궤적 오버레이

영상 첫 프레임을 배경으로, 추적에 성공한 모든 입자의 이동 경로를 겹쳐 표시합니다. 각 입자는 서로 다른 색으로 구분되며, 경로의 투명도가 시간에 따라 옅은 색(초기)에서 진한 색(후기)으로 변합니다. 시작점은 빈 원(○), 끝점은 채운 원(●)으로 표시됩니다.

**활용 방법**
- 입자들이 특정 방향으로 치우쳐 이동한다면 drift가 존재한다는 신호입니다.
- 경로가 매우 짧거나 한 자리에 머문다면 입자가 갇혀 있는(confined) 상태일 수 있습니다.
- drift 보정 후에도 방향성이 있는 입자가 있다면 directed motion 후보입니다.

좌표계: y=0이 이미지 상단, y가 증가할수록 하단 (영상 좌표계와 동일).

---

### `tracking_video.mp4` — 프레임별 입자 추적 영상

원본 영상 위에 매 프레임마다 추적 중인 입자에 색상 원을 표시한 영상입니다. 입자별로 고유한 색이 부여되며, 추적이 끊긴 프레임에서는 원이 사라집니다. 이를 통해 어떤 입자가 얼마나 오래 추적되는지, 추적이 끊기는 원인이 입자 소실인지 파라미터 문제인지 직관적으로 확인할 수 있습니다.

**확인 포인트**
- 원이 실제 밝은 점(입자)에 정확히 얹혀 있는가
- 원이 자주 깜빡인다면 `MEMORY` 값 증가를 고려
- 입자가 빠르게 이동하는데 원이 따라가지 못한다면 `SEARCH_RANGE` 증가를 고려

---

### `drift_correction.png` — Drift 보정 결과

세 개의 패널로 구성됩니다.

- **왼쪽 (Per-frame Drift)**: 프레임마다 모든 입자의 평균 변위로 추정한 순간 drift. 값이 일정하면 stage가 일정 속도로 이동 중, 들쭉날쭉하면 진동이나 입자 수 부족.
- **가운데 (Cumulative Drift vs Frame)**: 누적 drift를 프레임 번호에 따라 표시. x/y 각각의 추세를 시간 축으로 확인할 수 있습니다.
- **오른쪽 (Cumulative Drift Path)**: 누적 drift를 x-y 2D 좌표로 표시한 경로. 초록점이 시작, 빨간점이 끝. stage가 실제로 어떤 방향으로 흘렀는지 직관적으로 파악할 수 있습니다.

drift 보정은 앙상블 평균 변위를 각 입자 trajectory에서 차감하는 방식으로 수행됩니다. 보정 후 남은 이동이 개별 입자의 실제 운동(확산 + 자기추진)에 해당합니다.

---

### `ensemble_msd.png` — 앙상블 MSD 곡선

모든 입자의 MSD를 평균낸 앙상블 MSD를 log-log 스케일로 표시하고, `MSD = 4D · Δt^α` 모델을 fitting한 곡선을 겹쳐 그립니다.

- log-log 그래프에서 직선에 가까울수록 멱함수 관계가 성립
- 기울기(α)가 1이면 Brownian, 1보다 작으면 confined, 1보다 크면 directed
- 단일 입자 MSD보다 통계적 노이즈가 적어 전체적인 운동 성격을 파악하는 데 유용

---

### `diffusion_distribution.png` — 확산계수 D 분포

입자별로 fitting된 확산계수 D의 히스토그램입니다. D가 크다는 것은 입자가 더 빠르게 확산한다는 의미입니다. 분포가 넓을수록 입자 집단이 균질하지 않음을 나타냅니다.

PIXEL_SIZE_NM을 설정한 경우 단위가 µm²/s로 변환되며, Stokes-Einstein 방정식 `D = kT / (6πηr)` 을 통해 유체역학적 직경을 역산할 수 있습니다.

---

### `alpha_distribution.png` — 이상확산 지수 α 분포

입자별 α 값의 히스토그램입니다. 세 영역으로 나뉩니다.

| α 범위 | 운동 유형 | 의미 |
|--------|-----------|------|
| α < 0.85 | confined | 물리적·화학적 장벽에 의한 제한 확산 |
| 0.85 ≤ α ≤ 1.15 | brownian | 자유 확산 (정상 Brownian motion) |
| α > 1.15 | directed | 외력 또는 자기추진에 의한 방향성 운동 |

Janus 입자 실험에서 대조군(일반 나노입자) 대비 α > 1.15인 입자 비율이 증가하면 자기추진이 발생한 것으로 해석합니다.

---

### `motion_type_distribution.png` — 운동 유형 파이차트

confined / brownian / directed 세 유형의 비율을 시각화합니다. 앙상블 통계의 핵심 요약 지표입니다.

---

### `ensemble_stats.csv` — 앙상블 통계 수치

터미널 출력과 동일한 내용을 CSV로 저장합니다. 주요 항목은 다음과 같습니다.

| 항목 | 의미 |
|------|------|
| `n_particles` | 분석된 총 입자 수 |
| `D_mean` / `D_median` / `D_std` | 확산계수 분포 (중앙값이 이상치에 강건해 대표값으로 적합) |
| `D_p25` / `D_p75` | D의 25·75 백분위수 (중간 50% 범위, IQR) |
| `alpha_mean` / `alpha_median` / `alpha_std` | α 분포 |
| `n_brownian` / `pct_brownian` | Brownian 입자 수·비율 |
| `n_confined` / `pct_confined` | Confined 입자 수·비율 |
| `n_directed` / `pct_directed` | Directed 입자 수·비율 |
| `net_disp_mean` / `net_disp_median` / `net_disp_std` | 입자별 net displacement(이동 거리 크기)의 분포. 항상 원본 좌표 기준 |
| `vec_mean_dx` / `vec_mean_dy` | 앙상블 평균 변위 벡터의 x, y 성분 |
| `vec_mean_mag` | 앙상블 평균 변위 벡터의 크기 `√(⟨Δx⟩² + ⟨Δy⟩²)` |

---

#### 앙상블 평균 변위 벡터 (`vec_mean_dx`, `vec_mean_dy`, `vec_mean_mag`) 해석

**개념**

`vec_mean_dx = ⟨Δx⟩`, `vec_mean_dy = ⟨Δy⟩`는 전체 입자의 시작→끝 변위를 벡터로 평균한 값입니다. 각 성분은 양수/음수 모두 가능하며, 전체 입자가 특정 방향으로 얼마나 편향되었는지를 나타냅니다.

이 값은 개별 입자의 이동 거리(net displacement)의 평균과 다릅니다. 개별 이동 거리는 항상 ≥ 0이므로 순수 Brownian에서도 표본 수에 따라 상당히 크게 나올 수 있습니다. 반면 벡터 평균은 이론적으로 순수 Brownian에서 입자 수가 충분하면 0에 수렴합니다.

**해석 기준**

| 상황 | ⟨Δx⟩, ⟨Δy⟩ | 의미 |
|------|------------|------|
| 순수 Brownian | ≈ 0 | 방향성 없는 랜덤 확산 |
| Stage drift 또는 bulk flow 존재 | 한 방향으로 편향 (예: ⟨Δy⟩ > 0 일관) | 공통 외력에 의한 계통적 이동 |
| Drift 보정 후에도 잔류 | 보정 후 값이 보정 전과 같거나 오히려 증가 | 입자 수 부족으로 drift 추정이 불안정하거나, 실제 directional flow가 존재 |

**drift/ vs no_drift/ 비교 방법**

분석 실행 시 터미널에 아래와 같이 보정 전후 비교가 출력됩니다.

```
=== 앙상블 평균 변위 벡터 (N=52 particles) ===
              ⟨Δx⟩       ⟨Δy⟩       |⟨Δr⟩|
  원본          -7.85 px   +15.30 px   17.20 px
  drift 보정후  +4.00 px   -0.47 px    4.02 px
```

- **보정 후 크게 감소**: stage drift가 주된 원인이었음. 보정이 효과적으로 작동한 것
- **보정 후에도 크게 남음**: 잔류 flow가 있거나, 추적 입자 수가 너무 적어 drift 추정이 부정확한 것
- **보정 후 오히려 증가**: 입자 수 부족(일반적으로 N < 20)으로 과보정이 발생한 것. 이 경우 `no_drift/` 결과를 우선 참고

`drift/ensemble_stats.csv`에는 보정된 궤적 기준 벡터 평균이, `no_drift/ensemble_stats.csv`에는 원본 궤적 기준 벡터 평균이 저장됩니다.

---

### `angular_displacement.png` — 입자별 각변위

각 입자의 속도 벡터 방향(θ)을 중심차분법으로 계산하고, 프레임별 각변위(Δθ)와 누적 각변위를 2패널로 표시합니다.

- **왼쪽**: 프레임별 Δθ (−π ~ +π 범위로 wrap). 입자가 시계/반시계 방향으로 어떻게 회전하는지 확인.
- **오른쪽**: 누적 각변위. 단조 증가하면 지속적인 한 방향 회전(chirality 신호).

---

### `ensemble_angular_displacement.png` — 앙상블 누적 각변위

모든 입자의 누적 각변위 앙상블 평균(실선)과 95% CI(음영)를 표시합니다. 각 입자는 첫 검출 시점을 lag=0으로 정렬하므로 나중에 검출된 입자도 통계에 올바르게 포함됩니다.

- **평균이 0에서 단조 이탈**: 입자 집단 전체에 방향성 있는 회전 경향이 있음 → chirality 또는 외부 토크 신호
- **95% CI가 0을 포함**: 해당 lag time에서 평균이 통계적으로 0과 구분되지 않음
- **95% CI = mean ± 2 × SEM** (N이 작으면 t분포가 더 정확하나, 경향성 파악에는 충분)

---

### `ensemble_angular_stats.csv` — 앙상블 각변위 통계

| 항목 | 의미 |
|------|------|
| `lag_step` | 상대 lag (각 입자 첫 검출 기준) |
| `mean_cumulative_deg` | 누적 각변위 앙상블 평균 (도) |
| `std_cumulative_deg` | 표준편차 |
| `sem_cumulative_deg` | 표준오차 (SEM = std / √N) |
| `ci95_deg` | 95% CI 반폭 (= 2 × SEM) |
| `n` | 해당 lag에 기여한 입자 수 |

---

### `per_particle_angular.csv` — 입자별 각변위 원시 데이터

| 항목 | 의미 |
|------|------|
| `particle` | 입자 ID |
| `frame` | 절대 프레임 번호 |
| `theta_rad` | 속도 벡터 방향각 (라디안) |
| `delta_theta_rad` | 프레임 간 각변위 (−π ~ +π) |
| `cumulative_rad` | 누적 각변위 (라디안) |
| `cumulative_deg` | 누적 각변위 (도) |

---

### `per_particle_results.csv` — 입자별 분석 결과

입자 하나하나의 D, α, 운동 유형이 담긴 전체 목록입니다. 특정 입자를 선별하거나 추가 통계 분석을 할 때 활용합니다. `--plot-track ID`로 관심 있는 입자의 개별 trajectory를 확인할 수 있습니다.

---

## 파라미터 설정 (`config.py`)

```python
FPS = 30                    # 영상 프레임 레이트 (--fps 옵션으로 오버라이드 가능)
PIXEL_SIZE_NM = None        # nm/pixel. None이면 픽셀 단위, 값 설정 시 물리 단위 출력

# 입자 검출 — --preview로 확인하며 조정
PARTICLE_DIAMETER = 5       # 입자 밝은 영역 직경 (홀수, 픽셀 단위)
MIN_MASS = 150              # 최소 밝기 임계값. 낮추면 더 많이 검출, 높이면 노이즈 제거

# 추적
SEARCH_RANGE = 10           # 프레임 간 최대 이동 허용 픽셀. 입자가 빠르면 증가
MEMORY = 3                  # 입자 소실 후 재등장 허용 프레임 수
MIN_TRAJECTORY_LENGTH = 20  # 분석에 포함할 최소 프레임 수. 짧은 noise track 제거
```

파라미터를 바꾸면 출력 디렉토리가 `d{PARTICLE_DIAMETER}_m{MIN_MASS}` 형식으로 자동 분리되어, 같은 영상에 대해 여러 파라미터 결과를 나란히 보관할 수 있습니다.

---

## 파라미터 튜닝 로그 (`notes/`)

`--preview` 실행 시마다 `notes/{영상이름}.md`에 사용 파라미터와 검출 수가 자동 기록됩니다. 파라미터를 반복 조정한 이력을 추적하는 데 활용합니다.

---

## Janus 입자 directed motion 분석 (추후 확장)

현재 코드는 일반 나노입자의 Brownian motion + drift 분석을 기본으로 합니다. Janus 나노입자(자기추진 입자)를 분석할 경우 `analysis.py`에 이미 구현된 확장 함수를 활용할 수 있습니다.

```python
from analysis import fit_msd_directed, compute_straightness

# MSD = 4Dt + v²t² 모델로 fitting → 확산계수 D와 자기추진 속도 v 동시 추출
directed_results = fit_msd_directed(msd_dict)

# 직선성 지수 계산 (0~1, 1이면 완전 직진 운동)
straightness = compute_straightness(trajectories)
```

대조군(일반 나노입자) 대비 `pct_directed` 비율과 직선성 지수가 유의미하게 증가하면 자기추진 운동이 발생한 것으로 판단합니다.
