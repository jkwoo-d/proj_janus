# Drift 보정 — 알고리즘 상세 설명

## Drift란 무엇인가

NTA 실험에서 관측되는 입자 이동에는 두 가지 성분이 혼재한다.

1. **입자 고유 운동**: Brownian 확산, 능동 추진(H₂O₂ 분해)
2. **Drift**: 실험 장치 전체에 공통으로 작용하는 외부 이동 성분

Drift의 주요 원인:

| 원인 | 설명 |
|------|------|
| 기계적 진동 | 현미경 스테이지, 공조 시스템, 건물 진동 |
| 유동(flow) | 시료 챔버의 압력 차이, 증발에 의한 대류 |
| 열팽창 | 광원 열로 인한 스테이지 위치 변화 |

Drift가 보정되지 않으면:
- MSD가 실제보다 과대 추정됨 ($\text{MSD}_{\text{obs}} = \text{MSD}_{\text{true}} + v_{\text{drift}}^2 \tau^2$)
- Brownian 입자가 directed motion으로 오분류됨
- D 값이 상향 편향됨

---

## 보정 알고리즘

`trackpy.compute_drift()` + `trackpy.subtract_drift()`를 사용한다.

### Step 1: 프레임별 앙상블 평균 변위 계산

각 프레임 t에서 전체 추적 입자들의 평균 변위를 계산한다.

$$\Delta\bar{x}(t) = \frac{1}{N(t)} \sum_{i=1}^{N(t)} \left[x_i(t) - x_i(t-1)\right]$$

$$\Delta\bar{y}(t) = \frac{1}{N(t)} \sum_{i=1}^{N(t)} \left[y_i(t) - y_i(t-1)\right]$$

여기서 $N(t)$는 프레임 t와 t-1 모두에 존재하는 입자 수.

**핵심 가정**: 모든 입자는 동일한 drift에 노출되어 있고, 각 입자의 Brownian 운동은 앙상블 평균에서 서로 상쇄된다. 즉, 충분히 많은 입자가 있을 때

$$\langle \Delta x_i^{\text{Brownian}} \rangle_i \approx 0$$

이므로 앙상블 평균 변위 ≈ drift 성분이 된다.

### Step 2: 누적 drift 추정

프레임별 평균 변위를 누적 합산해 각 프레임에서의 절대 drift 위치를 구한다.

$$\text{drift}_x(t) = \sum_{s=1}^{t} \Delta\bar{x}(s)$$

$$\text{drift}_y(t) = \sum_{s=1}^{t} \Delta\bar{y}(s)$$

이 값이 시간 함수로서 drift의 궤적(drift trajectory)이다.

### Step 3: Drift 제거

각 입자의 좌표에서 해당 프레임의 drift를 뺀다.

$$x_i^{\text{corr}}(t) = x_i^{\text{obs}}(t) - \text{drift}_x(t)$$

$$y_i^{\text{corr}}(t) = y_i^{\text{obs}}(t) - \text{drift}_y(t)$$

---

## 본 실험에서의 적용

### 두 모드 병렬 분석

파이프라인은 **drift 보정 / 미보정** 두 결과를 항상 동시에 생성한다. 이는 다음 이유에서다.

- drift 보정이 과도하면(예: 입자 수가 너무 적을 때) 실제 능동 운동 성분까지 제거될 수 있음
- 미보정 결과와 비교해 보정의 타당성을 검증 가능

### 앙상블 평균 변위 벡터 출력

분석 시작 시 다음이 출력된다:

```
=== 앙상블 평균 변위 벡터 ===
              ⟨Δx⟩       ⟨Δy⟩       |⟨Δr⟩|
원본          -16.78 µm  -9.54 µm   19.30 µm
drift 보정후  +5.54 µm   +2.55 µm    6.10 µm
```

- **원본 |⟨Δr⟩|이 클수록** drift가 강하게 존재함을 의미
- **보정 후 |⟨Δr⟩|이 0에 가까울수록** 보정이 효과적으로 이루어진 것

### Drift artifact 필터

drift 보정 후 directed로 분류된 입자 중, 다음 조건에 해당하면 brownian으로 재분류한다.

$$\frac{\text{net displacement}_{\text{original}}}{\text{net displacement}_{\text{corrected}}} < 0.1$$

이는 원본에서 거의 정지해 있던 입자가 drift 보정 후 큰 net displacement를 갖는 경우를 제거하기 위함이다. 원본에서 정지 = drift 방향과 입자 실제 운동이 상쇄된 것 → 보정 후 반대 방향으로 크게 이동하는 것처럼 보이는 artifact이다.

---

## 보정의 한계

### 한계 1: 입자 수가 적을 때

추적 입자 수 N이 적으면 프레임당 앙상블 평균의 통계 오차가 크다.

$$\text{SE}(\Delta\bar{x}) = \frac{\sigma_{\text{Brownian}}}{\sqrt{N}}$$

N이 작으면 Brownian noise가 drift 추정에 섞여 들어가 **과보정(over-correction)**이 발생할 수 있다. 이 경우 drift 미보정 결과가 더 신뢰할 수 있다.

### 한계 2: 비균질 drift

시야 내 위치에 따라 drift 방향/크기가 다른 경우(예: 와류성 대류), 앙상블 평균 drift가 모든 입자에 균등하게 적용되지 않는다. 단순 평균 차감으로는 완전한 보정이 불가능하다.

### 한계 3: 능동 운동 성분의 부분 제거

H₂O₂ 환경에서 모든 입자가 같은 방향으로 능동 추진한다면, 이 성분도 앙상블 평균에 포함되어 drift로 잘못 추정된다. 그러나 Janus 입자의 방향성 운동은 Brownian 자전으로 인해 방향이 무작위하므로, 앙상블 평균에서는 이 성분이 상쇄되어 실질적인 오차가 크지 않다.

---

## 검증 방법

1. **drift_correction.png**: 프레임별 drift 궤적을 확인. 단조 증가하거나 급격한 방향 전환이 없으면 정상
2. **앙상블 평균 변위 벡터**: 보정 후 |⟨Δr⟩|이 보정 전보다 유의미하게 감소했는지 확인
3. **D 분포 비교**: drift 보정 / 미보정의 D 분포가 크게 다르면 drift가 실험에 큰 영향을 줬음을 의미
