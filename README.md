# Nanoparticle Tracking Analysis (NTA)

100배율 암시야(dark-field) 현미경으로 촬영한 AVI/MP4 영상에서 나노입자의 trajectory를 추출하고 운동 특성을 분석하는 CLI 도구입니다.

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 빠른 시작

### 1단계: 검출 파라미터 확인 (필수)

실제 분석 전에 영상 중간 프레임에서 입자가 잘 검출되는지 확인합니다.

```bash
python3 main.py --video your_video.mp4 --preview
```

`output/preview_detection.png`를 열어 확인합니다.
- 입자가 너무 적게 잡힌다 → `config.py`에서 `MIN_MASS`를 낮춤
- 노이즈가 입자로 잡힌다 → `MIN_MASS`를 높임
- 입자 크기가 맞지 않는다 → `PARTICLE_DIAMETER` 조정 (반드시 홀수)

### 2단계: 전체 분석 실행

```bash
python3 main.py --video your_video.mp4 --fps 30
```

fps를 알고 있다면 `--fps`로 지정합니다. `config.py`의 `FPS`를 직접 수정해도 됩니다.

### 3단계: 물리 단위 변환 (선택)

픽셀 크기(nm/pixel)를 알고 있다면 지정하면 결과가 nm, µm²/s 단위로 출력됩니다.

```bash
python3 main.py --video your_video.mp4 --fps 30 --pixel-size 65
```

---

## 전체 옵션

```
python3 main.py --video VIDEO [옵션]

필수:
  --video VIDEO         분석할 AVI 또는 MP4 영상 경로

선택:
  --preview             중간 프레임 검출 결과만 확인하고 종료
  --fps FPS             프레임 레이트 (config.py의 FPS 오버라이드)
  --pixel-size NM       픽셀 크기 nm/pixel (config.py의 PIXEL_SIZE_NM 오버라이드)
  --no-drift            drift 보정 생략
  --plot-track ID       특정 track ID 입자의 trajectory + MSD 그래프 생성
  --plot-all            모든 입자의 trajectory + MSD 그래프 개별 생성
```

---

## 출력 파일 (`output/`)

| 파일 | 설명 |
|------|------|
| `preview_detection.png` | `--preview` 시 검출 결과 확인용 |
| `drift_correction.png` | 프레임별 drift 벡터 및 누적 drift 경로 |
| `all_trajectories.png` | 전체 입자 trajectory 오버레이 (색상으로 입자 구분) |
| `ensemble_msd.png` | 앙상블 평균 MSD 곡선 + 파워 법칙 fitting |
| `diffusion_distribution.png` | 확산계수 D 분포 히스토그램 |
| `alpha_distribution.png` | 이상확산 지수 α 분포 히스토그램 |
| `motion_type_distribution.png` | 운동 유형 비율 파이차트 |
| `track_N.png` | `--plot-track N` 시 해당 입자의 trajectory + MSD |
| `ensemble_stats.csv` | 앙상블 통계 수치 (D, α 평균/중앙값/표준편차, 운동 유형 비율) |
| `per_particle_results.csv` | 입자별 D, α, 운동 유형, fitting 오차 |

---

## 파라미터 설정 (`config.py`)

```python
FPS = 30                    # 프레임 레이트
PIXEL_SIZE_NM = None        # nm/pixel. None이면 픽셀 단위로 출력

# 입자 검출 (--preview로 확인하며 조정)
PARTICLE_DIAMETER = 11      # 입자 밝은 영역 직경 (홀수, 픽셀 단위)
MIN_MASS = 100              # 최소 밝기 임계값

# 추적
SEARCH_RANGE = 10           # 프레임 간 최대 이동 허용 픽셀
MEMORY = 3                  # 입자 소실 후 재등장 허용 프레임 수
MIN_TRAJECTORY_LENGTH = 20  # 분석에 포함할 최소 프레임 수

OUTPUT_DIR = "output"
```

---

## 앙상블 통계 결과 해석 (`ensemble_stats.csv`)

분석이 완료되면 터미널과 CSV 파일에 아래 항목들이 출력됩니다.

### 분석 입자 수

| 항목 | 의미 |
|------|------|
| `n_particles` | 분석에 사용된 총 입자 수 (`MIN_TRAJECTORY_LENGTH` 이상의 궤적만 포함) |

### 확산계수 D 분포

확산계수 D는 입자가 얼마나 빠르게 퍼지는지를 나타냅니다. 단위는 픽셀 크기 설정 여부에 따라 `px²/s` 또는 `µm²/s`로 표시됩니다.

| 항목 | 의미 |
|------|------|
| `D_mean` | D의 산술 평균. 이상치(outlier)에 민감하므로 참고값으로만 사용 |
| `D_median` | D의 중앙값. 이상치에 강건하여 대표값으로 더 신뢰할 수 있음 |
| `D_std` | D의 표준편차. 값이 크면 입자 집단이 균일하지 않음을 의미 |
| `D_p25` / `D_p75` | D의 25·75 백분위수. 중간 50% 입자의 D 범위를 나타냄 (IQR) |

> **물리적 해석**: Stokes-Einstein 방정식 `D = kT / (6πηr)` 를 이용해 유체 점도(η)와 온도(T)를 알고 있으면 입자의 유체역학적 직경(r)을 역산할 수 있습니다.

### 이상확산 지수 α 분포

α는 입자 운동의 성격을 나타내는 지수입니다. MSD ~ Δt^α 관계에서 도출됩니다.

| 항목 | 의미 |
|------|------|
| `alpha_mean` | α의 산술 평균. 전체 집단의 평균적 운동 성격 |
| `alpha_median` | α의 중앙값. 이상치에 강건한 대표값 |
| `alpha_std` | α의 표준편차. 크면 집단 내 운동 유형이 혼재함을 의미 |

> **해석 기준**: α = 1이면 순수 Brownian, α < 1이면 제한/방해 확산, α > 1이면 방향성 운동. α_mean이 1에 가까울수록 실험 조건이 순수 확산에 가깝습니다.

### 운동 유형 분포

| 항목 | 의미 |
|------|------|
| `n_brownian` / `pct_brownian` | 정상 Brownian 입자 수·비율 (α ≈ 1). 자유 확산 상태 |
| `n_confined` / `pct_confined` | Confined 입자 수·비율 (α < 0.85). 물리적·화학적 장벽에 갇힌 상태 |
| `n_directed` / `pct_directed` | Directed 입자 수·비율 (α > 1.15). 외력·자기추진에 의한 방향성 운동 |

> **Janus 입자 실험 목표**: `pct_directed`가 유의미하게 증가하면 자기추진 운동이 발생했음을 의미합니다. 대조군(일반 나노입자)의 `pct_directed`와 비교해 판단합니다.

---

## 운동 유형 분류 기준

MSD를 `MSD = 4D · Δt^α` 로 fitting한 α 값으로 분류합니다.

| α 범위 | 운동 유형 | 의미 |
|--------|-----------|------|
| α < 0.85 | confined | 제한된 공간 내 운동 |
| 0.85 ≤ α ≤ 1.15 | brownian | 정상 Brownian 확산 |
| α > 1.15 | directed | 방향성 운동 (초확산) |

---

## 분석 파이프라인

```
AVI/MP4
  ↓ OpenCV 로드 (그레이스케일)
프레임별 입자 검출 (trackpy Crocker-Grier)
  ↓
Trajectory 링킹 + 짧은 track 제거
  ↓
Drift 보정 (앙상블 평균 변위 차감)
  ↓
입자별 MSD + 앙상블 MSD 계산
  ↓
MSD fitting → D, α, 운동 유형 분류
  ↓
통계 집계 + 시각화 저장
```

---

## Janus 입자 directed motion 분석 (추후 확장)

`analysis.py`에 아래 함수가 이미 구현되어 있습니다.

```python
from analysis import fit_msd_directed, compute_straightness

# MSD = 4Dt + v²t² 모델로 fitting → D, v(속도) 추출
directed_results = fit_msd_directed(msd_dict)

# 직선성 지수 계산 (0~1, 1이면 완전 직진)
straightness = compute_straightness(trajectories)
```
