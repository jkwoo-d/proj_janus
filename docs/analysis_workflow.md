# NTA 분석 파이프라인 — 알고리즘 설명

## 개요

본 파이프라인은 암시야 현미경(dark-field microscopy) 동영상에서 나노입자를 검출·추적하고, 확산계수(D) 및 운동 유형을 정량적으로 분석하는 Nanoparticle Tracking Analysis(NTA) 시스템이다. 헬리코이드 구조 Janus 나노입자(Au/Pt)의 H₂O₂ 존재 하 능동 운동 특성 분석을 목적으로 한다.

---

## 전체 파이프라인

```
동영상 입력
    │
    ▼
[1단계] 입자 검출 (detection.py)
    │  ─ 프레임별 blob 검출 (trackpy.locate)
    │
    ▼
[2단계] 궤적 연결 (tracking.py)
    │  ─ 프레임 간 동일 입자 연결 (trackpy.link)
    │  ─ 짧은 noise track 제거
    │
    ▼
[3단계] Drift 보정 (tracking.py)
    │  ─ 앙상블 평균 변위로 기계적 drift 추정·제거
    │
    ▼
[4단계] MSD 분석 (analysis.py)
    │  ─ 입자별 Mean Squared Displacement 계산
    │  ─ Power-law 피팅: MSD = 4Dt^α
    │  ─ 운동 유형 분류 (Brownian / confined / directed)
    │  ─ Outlier 필터링
    │
    ▼
[5단계] 각변위 분석 (analysis.py)
    │  ─ 속도벡터 방향 θ 계산
    │  ─ 누적 각변위 (trajectory 곡률)
    │
    ▼
[6단계] 밝기 변동 분석 (analysis.py)
    │  ─ 입자별 산란 밝기(mass) 시계열
    │  ─ ACF 피팅: Brownian vs 자전 신호 분리
    │  ─ FFT 파워 스펙트럼
    │
    ▼
시각화 + CSV 저장 (visualization.py, nta_stats.py)
```

---

## 1단계: 입자 검출

### 알고리즘

`trackpy.locate()`를 사용한다. 내부적으로 **Gaussian 스무딩 + Laplacian of Gaussian(LoG) 유사 연산**으로 동작한다.

1. **Bandpass filtering**: 지정된 `PARTICLE_DIAMETER`(픽셀, 홀수)로 저역통과 필터 적용 → 배경 노이즈 제거
2. **로컬 최대값 검출**: 각 픽셀이 주변 `diameter × diameter` 영역에서 최대인지 확인
3. **밝기 임계값(MIN_MASS) 필터**: 검출된 blob의 통합 밝기(`mass`)가 `MIN_MASS` 미만이면 제거
4. **서브픽셀 정밀도**: 밝기 가중 무게중심으로 위치를 서브픽셀 수준까지 정밀화

### 출력

프레임별 입자 목록: `(x, y, mass, size, ecc, frame)`

| 컬럼 | 설명 |
|------|------|
| `x`, `y` | 서브픽셀 위치 (pixel) |
| `mass` | 통합 산란 밝기 |
| `size` | blob 반경 (픽셀) |
| `ecc` | 이심률 (0=원형) |

---

## 2단계: 궤적 연결 (Linking)

### 알고리즘

`trackpy.link()`를 사용한다. **Hungarian algorithm(최소 비용 이분 매칭)**으로 연속 프레임 간 입자를 연결한다.

1. **Search range 제한**: 두 프레임 간 동일 입자의 최대 허용 이동 거리 = `SEARCH_RANGE`(픽셀)
2. **최소 비용 매칭**: 가능한 모든 연결 조합 중 총 이동 거리를 최소화하는 매칭 선택
3. **Memory(간헐적 소멸 허용)**: 입자가 최대 `MEMORY` 프레임 동안 사라졌다 재등장해도 같은 궤적으로 연결. 이 구간은 선형 보간이 아닌 gap으로 처리됨
4. **Subnet overflow 대응**: 입자 밀도가 너무 높으면 `adaptive` 모드로 자동 전환 (search_range를 0.95배씩 줄임)
5. **짧은 궤적 제거**: `MIN_TRAJECTORY_LENGTH` 프레임 미만 track은 noise track으로 간주하고 제거

---

## 3단계: Drift 보정

별도 문서(`drift_correction.md`) 참조.

---

## 4단계: MSD 분석

### MSD 계산

입자별로 `trackpy.msd()`를 사용해 Mean Squared Displacement를 계산한다.

$$\text{MSD}(\tau) = \langle [x(t+\tau) - x(t)]^2 + [y(t+\tau) - y(t)]^2 \rangle_t$$

- 신뢰 가능한 lag time 상한: **N/4** (여기서 N = 궤적 프레임 수). N/4를 초과하면 각 lag에 참여하는 데이터 포인트 수가 부족해 통계 불안정
- 단위 변환: `mpp = PIXEL_SIZE_NM / 1000` (µm/pixel)

### Power-law 피팅

$$\text{MSD}(\tau) = 4D\tau^\alpha$$

`scipy.optimize.curve_fit`으로 D와 α를 동시에 피팅한다.

- **2D 확산계수 D**: Stokes-Einstein 관계식 $D = k_BT / (6\pi\eta r)$ (3D)에서, 2D tracking MSD = $4D\tau$이므로 계수 4를 사용. $3\pi\eta r$로 쓰면 2배 과대추정 오류 발생
- **α (이상확산 지수)**: 운동 유형 판별 지표

### 운동 유형 분류

| 조건 | 분류 |
|------|------|
| α < 0.85 | **confined** (국소 구속 운동) |
| 0.85 ≤ α ≤ 1.15 | **brownian** (정상 확산) |
| α > 1.15 (lag point ≥ 8개) | **directed** (능동·직진 운동) |
| α > 2.0 | **directed** (super-ballistic) |

### Outlier 필터링

3단계 필터가 순차 적용된다.

**① 피팅 품질 필터**

| 제거 기준 | 의미 |
|----------|------|
| `D_err / D > 0.5` | 피팅 불신뢰 (궤적 링킹 오류 등) |
| `α < 0.2` | power-law 퇴화 → D 값 무의미 |

**② Drift artifact 필터**

drift 보정 좌표에서 directed로 분류된 입자 중, 원본 net displacement / 보정 net displacement < 0.1인 경우 → 정지 입자가 drift 반대 방향으로 흐르는 artifact → brownian으로 재분류

**③ Ensemble D 분포 outlier 필터**

log(D) 분포에서 Tukey fence 적용:

$$\text{fence} = [Q_1 - k \cdot \text{IQR},\ Q_3 + k \cdot \text{IQR}], \quad k = 1.0$$

### 입자 크기 추정

Stokes-Einstein:

$$d\ [\text{nm}] = \frac{k_B T}{3\pi\eta D} \approx \frac{490}{D\ [\mu\text{m}^2/\text{s}]}$$

(25°C, 물, η = 8.9×10⁻⁴ Pa·s 기준)

---

## 5단계: 각변위 분석

≥ `ANGULAR_MIN_DURATION_S` 초 동안 추적된 입자만 대상으로 한다.

### 속도벡터 방향 θ

**중심차분(centered difference)**으로 각 프레임에서의 이동 방향을 계산한다.

$$\theta_i = \arctan2\!\left(y_{i+1} - y_{i-1},\ x_{i+1} - x_{i-1}\right)$$

프레임 gap(MEMORY로 생긴 불연속) 경계는 단방향 차분으로 대체한다.

### 각변위 Δθ

연속 프레임 간 θ 변화를 −π ~ π 범위로 wrap 처리:

$$\Delta\theta_i = \text{arg}\!\left(e^{i(\theta_i - \theta_{i-1})}\right)$$

프레임 gap 직후의 Δθ는 의미 없으므로 0으로 마스킹한다.

### 누적 각변위

$$\Theta(t) = \sum_{k=0}^{t} \Delta\theta_k$$

**주의**: 이 분석은 **입자 자체의 자전(spin)**이 아니라 **궤적의 곡률 누적**을 측정한다. Brownian 입자는 좌우 회전이 무작위하므로 앙상블 평균 ⟨Θ⟩ → 0이 되어야 한다. 일방적인 방향성이 관측된다면 chirality에 의한 trajectory 편향을 시사하지만, 단독 증거로는 불충분하다.

---

## 6단계: 밝기 변동 분석

### 배경

Janus 입자(Au 면 / Pt 면)는 두 면의 산란 효율이 다르다. 입자가 자전하면 카메라 방향으로 향하는 면이 교대로 바뀌며 trackpy `mass` 값이 주기적으로 변동한다. 이를 분석하면 NTA 데이터만으로 자전 신호를 간접 관찰할 수 있다.

### 밝기 시계열 전처리

1. `mass` 추출: trackpy가 각 프레임에서 이미 계산한 통합 산란 밝기
2. **선형 detrending**: 광원 안정화·소광 등 완만한 추세를 1차 다항식으로 제거
   $$\delta I(t) = I(t) - (at + b)$$
3. **정규화**: $\delta I_{\text{norm}} = (I - \bar{I}) / \bar{I}$

### 자기상관함수(ACF)

$$C(\tau) = \frac{\langle\delta I(t)\,\delta I(t+\tau)\rangle}{\langle\delta I(t)^2\rangle}$$

max lag = N/4 적용. 두 모델을 피팅한다:

| 모델 | 수식 | 의미 |
|------|------|------|
| **Model B** (Brownian) | $A\,e^{-\tau/\tau_r} + C_0$ | 단조 감쇠. 순수 Brownian 자전 |
| **Model R** (Rotation) | $A\,e^{-\tau/\tau_r}\cos(\omega\tau) + C_0$ | 감쇠 진동. 주기 T = 2π/ω → 자전 주기 후보 |

**FPS 한계**: ~500 nm 입자의 Brownian 자전 τᵣ ≈ 13 ms << 프레임 간격(0818: 139 ms, 0811: 100 ms). 따라서 lag ≥ 1 프레임에서 Brownian ACF ≈ 0이 되어야 한다. 잔류 신호가 있다면 translation-rotation coupling에 의한 directed rotation을 시사한다.

### FFT 파워 스펙트럼

detrended signal에 **Hann 윈도우**를 적용한 뒤 FFT:

- 1/f² 형태 → Brownian noise
- 뚜렷한 피크 → 자전 주파수 후보. ACF와 교차 검증 필요
- Nyquist 주파수 = FPS/2 (검출 가능한 최대 주파수)
