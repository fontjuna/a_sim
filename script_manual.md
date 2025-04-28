# 투자 스크립트 작성 안내서

## 1. 개요

투자 스크립트는 매매 신호 생성 및 투자 로직 구현을 위한 Python 기반 스크립팅 시스템입니다. 간단한 문법으로 복잡한 투자 전략을 구현할 수 있으며, 다양한 기술적 지표와 차트 패턴을 활용할 수 있습니다.

### 1.1 핵심 특징

- **Python 기반**: 익숙한 Python 문법 사용
- **다양한 용도**: 매매 신호 생성부터 복잡한 기술 지표 계산까지 가능
- **재사용성**: 스크립트를 다른 스크립트에서 호출 가능
- **보안성**: 안전한 실행 환경 제공
- **통합 관리**: 모든 스크립트를 단일 인터페이스에서 관리

## 2. 스크립트 기본 구조

### 2.1 기본 형식

```python
# 매매 신호 스크립트 예제
dy = ChartManager('dy')  # 일봉 차트 매니저

# 이동평균선 계산
ma5 = dy.ma(code, dy.c, 5)  # 5일 이동평균
ma20 = dy.ma(code, dy.c, 20)  # 20일 이동평균

# 골든 크로스 확인
is_golden_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n), 
    lambda c, n: dy.ma(c, dy.c, 20, n))

# 결과 반환
result = is_golden_cross  # 불리언 값 반환
```

### 2.2 반환 타입에 따른 스크립트 용도

스크립트는 반환하는 `result` 값의 타입에 따라 다음과 같이 활용할 수 있습니다:

| 반환 타입 | 용도 | 예시 |
|----------|------|------|
| `bool` | 매매 신호 생성 | `result = price > ma20 and volume > avg_volume` |
| `int`, `float` | 지표값 계산 | `result = (close - low) / (high - low) * 100` |
| `str` | 상태 정보 반환 | `result = "상승추세" if price > ma20 else "하락추세"` |
| `list`, `tuple` | 복합 데이터 반환 | `result = [upper, middle, lower]  # 볼린저 밴드` |
| `dict` | 구조화된 정보 반환 | `result = {"trend": trend, "strength": strength}` |

## 3. 차트 데이터 접근하기

### 3.1 ChartManager 초기화

```python
# 일봉 차트 매니저
dy = ChartManager('dy')

# 분봉 차트 매니저 (3분봉)
mi3 = ChartManager('mi', 3)

# 틱 차트 매니저 (10틱)
tk10 = ChartManager('tk', 10)
```

### 3.2 기본 데이터 접근 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `c(code[,n])` | n봉 이전 종가 반환, 기본값은 0(현재 봉) | `dy.c(code)` - 현재봉 종가<br>`dy.c(code, 1)` - 1봉 전 종가 |
| `o(code[,n])` | n봉 이전 시가 반환, 기본값은 0(현재 봉) | `dy.o(code)` - 현재봉 시가<br>`dy.o(code, 1)` - 1봉 전 시가 |
| `h(code[,n])` | n봉 이전 고가 반환, 기본값은 0(현재 봉) | `dy.h(code)` - 현재봉 고가<br>`dy.h(code, 1)` - 1봉 전 고가 |
| `l(code[,n])` | n봉 이전 저가 반환, 기본값은 0(현재 봉) | `dy.l(code)` - 현재봉 저가<br>`dy.l(code, 1)` - 1봉 전 저가 |
| `v(code[,n])` | n봉 이전 거래량 반환, 기본값은 0(현재 봉) | `dy.v(code)` - 현재봉 거래량<br>`dy.v(code, 1)` - 1봉 전 거래량 |
| `a(code[,n])` | n봉 이전 거래대금 반환, 기본값은 0(현재 봉) | `dy.a(code)` - 현재봉 거래대금<br>`dy.a(code, 1)` - 1봉 전 거래대금 |
| `time([n])` | n봉 이전 시간 반환(분봉에서만 유효) | `mi3.time()` - 현재봉 시간<br>`mi3.time(1)` - 1봉 전 시간 |
| `today()` | 오늘 날짜 반환 | `dy.today()` - 'YYYYMMDD' 형식 |

### 3.3 이동평균 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `ma(code, a, n[, m, k])` | a의 n기간 이동평균 (m봉 이전, k는 유형) | `dy.ma(code, dy.c, 5)` - 종가 5일 단순이동평균<br>`dy.ma(code, dy.c, 5, 1, 'e')` - 1봉 전 종가 5일 지수이동평균 |
| `avg(code, a, n[, m])` | a의 n기간 단순이동평균 (m봉 이전) | `dy.avg(code, dy.c, 5)` - 종가 5일 단순이동평균 |
| `eavg(code, a, n[, m])` | a의 n기간 지수이동평균 (m봉 이전) | `dy.eavg(code, dy.c, 12)` - 종가 12일 지수이동평균 |
| `wavg(code, a, n[, m])` | a의 n기간 가중이동평균 (m봉 이전) | `dy.wavg(code, dy.c, 9)` - 종가 9일 가중이동평균 |

**매개변수 설명**:
- `code`: 종목코드
- `a`: 값을 가져올 함수 (c, o, h, l, v, a 등)
- `n`: 기간 (일수 또는 봉 수)
- `m`: 이전 봉 위치 (기본값 0, 현재 봉)
- `k`: 이동평균 유형 ('a': 단순, 'e': 지수, 'w': 가중)

## 4. 지표 및 신호 함수

### 4.1 기술적 지표 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `rsi(code, period[, m])` | 상대강도지수(RSI) | `dy.rsi(code, 14)` - 14일 RSI |
| `macd(code, fast, slow, signal[, m])` | MACD 지표 | `dy.macd(code, 12, 26, 9)` - MACD(12,26,9) |
| `bollinger_bands(code, period, std_dev[, m])` | 볼린저 밴드 | `dy.bollinger_bands(code, 20, 2)` - 20일, 2표준편차 볼린저 밴드 |
| `stochastic(code, k_period, d_period[, m])` | 스토캐스틱 오실레이터 | `dy.stochastic(code, 14, 3)` - 14,3 스토캐스틱 |
| `atr(code, period[, m])` | 평균 실제 범위(ATR) | `dy.atr(code, 14)` - 14일 ATR |

### 4.2 값 계산 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `highest(code, a, n[, m])` | a의 n기간 중 최고값 | `dy.highest(code, dy.h, 10)` - 최근 10봉 중 최고 고가 |
| `lowest(code, a, n[, m])` | a의 n기간 중 최저값 | `dy.lowest(code, dy.l, 10)` - 최근 10봉 중 최저 저가 |
| `stdev(code, a, n[, m])` | a의 n기간 표준편차 | `dy.stdev(code, dy.c, 20)` - 최근 20봉 종가의 표준편차 |
| `sum(code, a, n[, m])` | a의 n기간 합계 | `dy.sum(code, dy.v, 5)` - 최근 5봉 거래량 합계 |

### 4.3 신호 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `cross_up(code, a, b)` | a가 b를 상향돌파했는지 확인 | `dy.cross_up(code, lambda c, n: dy.ma(c, dy.c, 5, n), lambda c, n: dy.ma(c, dy.c, 20, n))` - 5일선이 20일선 상향돌파 |
| `cross_down(code, a, b)` | a가 b를 하향돌파했는지 확인 | `dy.cross_down(code, lambda c, n: dy.ma(c, dy.c, 5, n), lambda c, n: dy.ma(c, dy.c, 20, n))` - 5일선이 20일선 하향돌파 |
| `bars_since(code, condition)` | 조건 만족 이후 지난 봉 수 | `dy.bars_since(code, lambda c, n: dy.c(c, n) > dy.o(c, n))` - 마지막으로 종가가 시가보다 높았던 이후 봉 수 |

### 4.4 캔들 패턴 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `is_doji(code[, n, threshold])` | n봉 이전이 도지 캔들인지 확인 | `dy.is_doji(code)` - 현재봉이 도지 캔들인지 |
| `is_hammer(code[, n])` | n봉 이전이 망치형 캔들인지 확인 | `dy.is_hammer(code)` - 현재봉이 망치형 캔들인지 |
| `is_engulfing(code[, n, bullish])` | n봉 이전이 포괄 패턴인지 확인 | `dy.is_engulfing(code, 0, True)` - 현재봉이 상승 포괄 패턴인지 |

## 5. 스크립트 재사용 및 호출

### 5.1 스크립트 호출하기

다른 스크립트를 호출하여 재사용할 수 있습니다. 이는 코드 중복을 줄이고 모듈화된 구조를 만드는 데 도움됩니다.

```python
# 다른 스크립트 호출 예시
is_golden_cross = golden_cross(code)  # 'golden_cross' 스크립트 호출
is_volume_surge = volume_surge(code, kwargs={'threshold': 2.0})  # 매개변수 전달

# 여러 스크립트 결과 조합
result = is_golden_cross and is_volume_surge
```

### 5.2 스크립트 작성 패턴

다양한 용도의 스크립트를 작성하여 재사용 가능한 구조를 만들 수 있습니다:

#### 5.2.1 매매 신호 생성 스크립트 (불리언 반환)

```python
# 골든 크로스 매매 신호
dy = ChartManager('dy')
ma5 = dy.ma(code, dy.c, 5)
ma20 = dy.ma(code, dy.c, 20)
result = ma5 > ma20 and dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n), 
    lambda c, n: dy.ma(c, dy.c, 20, n))
```

#### 5.2.2 지표 계산 스크립트 (다양한 타입 반환)

```python
# 볼린저 밴드 계산
dy = ChartManager('dy')
period = kwargs.get('period', 20)
std_dev = kwargs.get('std_dev', 2)
bands = dy.bollinger_bands(code, period, std_dev)
result = bands  # (upper, middle, lower) 튜플 반환
```

#### 5.2.3 조건 판별 스크립트 (문자열 반환)

```python
# 시장 상태 판별
dy = ChartManager('dy')
price = dy.c(code)
ma20 = dy.ma(code, dy.c, 20)
ma60 = dy.ma(code, dy.c, 60)

if price > ma20 and ma20 > ma60:
    result = "강세장"
elif price < ma20 and ma20 < ma60:
    result = "약세장"
else:
    result = "중립시장"
```

## 6. 고급 기법

### 6.1 `kwargs` 활용하기

스크립트는 `kwargs` 인자를 통해 추가 매개변수를 받을 수 있습니다.

```python
# kwargs 활용 예시
period = kwargs.get('period', 20)  # 기본값 20
threshold = kwargs.get('threshold', 1.5)  # 기본값 1.5

# 입력된 매개변수로 계산
ma = dy.ma(code, dy.c, period)
vol_ratio = dy.v(code) / dy.avg(code, dy.v, period)
result = vol_ratio > threshold
```

### 6.2 람다 함수 활용

람다 함수를 사용하여 콜백 함수를 정의할 수 있습니다.

```python
# 단순한 람다 함수
is_up_candle = lambda c, n: dy.c(c, n) > dy.o(c, n)

# 이동평균 교차 확인
is_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n), 
    lambda c, n: dy.ma(c, dy.c, 20, n))
```

### 6.3 안전한 반복문 사용

`while` 루프는 금지되어 있으나, `loop` 함수를 사용하여 안전하게 반복 작업을 수행할 수 있습니다.

```python
# 최근 5개 봉 중 상승봉 수 계산
check_candle = lambda i: 1 if dy.c(code, i) > dy.o(code, i) else 0
up_candles = loop(range(5), check_candle)
up_count = sum(up_candles)
result = up_count  # 상승봉 개수 반환
```

## 7. 실제 예제

### 7.1 볼린저 밴드 돌파 전략

```python
# 볼린저 밴드 돌파 전략
dy = ChartManager('dy')

# 볼린저 밴드 계산 (20일, 2표준편차)
period = kwargs.get('period', 20)
std_dev = kwargs.get('std_dev', 2)
upper, middle, lower = dy.bollinger_bands(code, period, std_dev)

# 현재 종가
current_close = dy.c(code)

# 전일 종가
prev_close = dy.c(code, 1)

# 상단 돌파 조건 (전일 종가는 밴드 내부, 현재 종가는 상단 돌파)
is_upper_breakout = prev_close < upper and current_close > upper

# 하단 돌파 조건 (전일 종가는 밴드 내부, 현재 종가는 하단 돌파)
is_lower_breakout = prev_close > lower and current_close < lower

# 상단 돌파는 매도 신호, 하단 돌파는 매수 신호
if kwargs.get('signal_type', 'buy') == 'buy':
    result = is_lower_breakout
else:
    result = is_upper_breakout
```

### 7.2 MACD 다이버전스 스크립트

```python
# MACD 다이버전스 검출
dy = ChartManager('dy')

# MACD 계산
fast = kwargs.get('fast', 12)
slow = kwargs.get('slow', 26)
signal = kwargs.get('signal', 9)
lookback = kwargs.get('lookback', 20)

# 가격 패턴과 MACD 패턴 분석
price_lows = []
macd_lows = []

# 최근 N봉 검사
for i in range(lookback):
    # 저점 판별 (전봉과 다음봉보다 낮은지)
    if i > 0 and i < lookback-1:
        if dy.l(code, i) < dy.l(code, i-1) and dy.l(code, i) < dy.l(code, i+1):
            price_lows.append((i, dy.l(code, i)))
            
            # 해당 시점의 MACD 값
            macd_val = dy.macd(code, fast, slow, signal, i)[0]
            macd_lows.append((i, macd_val))

# 다이버전스 확인 (최소 2개 이상의 저점 필요)
has_divergence = False
if len(price_lows) >= 2 and len(macd_lows) >= 2:
    # 가격은 하락 저점, MACD는 상승 저점인지 확인
    if price_lows[-1][1] < price_lows[-2][1] and macd_lows[-1][1] > macd_lows[-2][1]:
        has_divergence = True

result = has_divergence
```

### 7.3 여러 스크립트 조합한 복합 전략

```python
# 복합 매매 전략 (여러 스크립트 조합)
# 골든 크로스 + 볼린저 밴드 하단 접근 + 거래량 급증

# 골든 크로스 확인
is_golden_cross = golden_cross(code)

# 볼린저 밴드 위치 확인
band_position = bollinger_position(code)
near_lower_band = band_position == -1  # 하단 밴드 근처

# 거래량 급증 확인
vol_surge = volume_surge(code, kwargs={'threshold': 1.8})

# 복합 매수 조건: 골든 크로스 + 볼린저 하단 + 거래량 급증
result = is_golden_cross and near_lower_band and vol_surge
```

## 8. 모범 사례 및 팁

### 8.1 코딩 스타일

- **간결한 코드**: 스크립트는 짧고 집중적으로 작성
- **명확한 변수명**: 이해하기 쉬운 변수명 사용
- **주석 추가**: 복잡한 로직은 주석으로 설명
- **재사용성 고려**: 범용적인 스크립트 작성

### 8.2 성능 최적화

- **불필요한 계산 제거**: 동일한 계산을 반복하지 않기
- **적절한 기간 설정**: 너무 긴 기간 사용 시 성능 저하
- **캐싱 활용**: 자주 사용하는 값은 변수에 저장하여 재사용

### 8.3 오류 방지

- **경계 조건 확인**: 데이터 부족 시 처리 방법 고려
- **0으로 나누기 방지**: 분모가 0이 될 수 있는 경우 대비
- **타입 변환 주의**: 문자열과 숫자 간 변환 시 오류 확인

## 9. 부록

### 9.1 허용된 Python 기능

#### 9.1.1 내장 함수 및 타입

- 데이터 타입: `int`, `float`, `str`, `bool`, `list`, `dict`, `set`, `tuple`
- 수학 함수: `max`, `min`, `sum`, `abs`, `round`
- 반복 함수: `range`, `enumerate`, `zip`, `sorted`
- 논리 함수: `all`, `any`, `len`

#### 9.1.2 허용된 모듈

- `math`: 수학 함수 (sin, cos, log 등)
- `datetime`: 날짜 및 시간 처리
- `re`: 정규 표현식
- `random`: 난수 생성
- `logging`: 로깅 기능
- `json`: JSON 데이터 처리
- `collections`: 컬렉션 자료구조

### 9.2 제한된 기능

다음 기능은 보안상의 이유로 사용이 제한됩니다:

- `while` 루프 (무한 루프 방지)
- 파일 시스템 접근 (`open()` 등)
- `eval()`, `exec()` 함수
- 시스템 모듈 (`os`, `sys`, `subprocess` 등)
- 네트워크 관련 기능
- 외부 프로세스 실행

### 9.3 유용한 스크립팅 패턴

#### 9.3.1 안전한 나눗셈

```python
# 0으로 나누기 방지
def safe_div(a, b, default=0):
    return a / b if b != 0 else default

# 사용 예시
ratio = safe_div(current, average, 1.0)
```

#### 9.3.2 조건부 값 선택

```python
# 조건에 따른 값 선택
value = good_value if condition else bad_value

# 다중 조건
if condition1:
    value = value1
elif condition2:
    value = value2
else:
    value = default_value
```

#### 9.3.3 값 범위 제한

```python
# 값을 특정 범위로 제한
clamped_value = max(min_value, min(value, max_value))
```

### 9.4 자주 사용되는 기술적 지표 공식

#### 9.4.1 상대강도지수(RSI)

```python
# RSI 직접 계산 예시
period = 14
gains = []
losses = []

# 가격 변화 수집
for i in range(1, period + 1):
    change = dy.c(code, i-1) - dy.c(code, i)
    if change >= 0:
        gains.append(change)
        losses.append(0)
    else:
        gains.append(0)
        losses.append(-change)

# 평균 상승/하락 계산
avg_gain = sum(gains) / period
avg_loss = sum(losses) / period

# RSI 계산
if avg_loss == 0:
    rsi = 100
else:
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

result = rsi
```

#### 9.4.2 이격도

```python
# 이격도 계산 (현재가와 이동평균의 비율)
current = dy.c(code)
ma20 = dy.ma(code, dy.c, 20)
disparity = (current / ma20 * 100) if ma20 > 0 else 100

result = disparity
```