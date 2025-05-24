# 스크립트 시스템 사용 안내서

## 1. 개요

### 1.1 특징

스크립트 시스템은 투자 전략을 쉽게 작성하고 테스트할 수 있는 강력한 도구입니다. 본 시스템의 특징은 다음과 같습니다:

- **파이썬 기반**: 널리 사용되는 파이썬 문법을 활용하여 직관적인 스크립트 작성
- **내장 함수**: 차트 데이터 분석, 기술적 지표 계산 등 다양한 내장 함수 제공
- **재사용성**: 작성한 스크립트를 함수처럼 다른 스크립트에서 호출 가능
- **안전성**: 악의적인 코드 실행을 방지하는 보안 기능 내장
- **자동화**: 매매 시스템과 연동하여 자동 매매 전략 구현 가능

### 1.2 활용 분야

- **매매 신호 생성**: 매수/매도 판단을 위한 조건식 작성
- **기술적 지표 계산**: 맞춤형 기술적 지표 생성 및 계산
- **차트 분석**: 다양한 주기의 차트 데이터 분석
- **백테스팅**: 과거 데이터를 기반으로 전략의 성능 검증
- **복합 전략**: 여러 전략의 조합으로 더 정교한 투자 전략 구현

## 2. 기본 구조

### 2.1 기본 형식

스크립트의 기본 형식은 다음과 같습니다:

```python
# 스크립트 설명 주석
# 차트 매니저 인스턴스 생성
# 스크립스 실행 종목의 code(종목코드), name(종목명), price(매수단가), qty(보유수량)은 자동지정 되므로 
# 스크립트내에서 다른 용도로 사용하면 뜻하지 않는 결과가 나올 수 있습니다.(변수 역할 변경 금지)
# 단, 특별히 다른 code의 차트매니저를 생성 하고 싶을땐 dy005930 = ChartManager('005930', 'dy')로 생성
dy = ChartManager(code, 'dy')  # 일봉 차트

# 계산 로직
ma20 = dy.ma(dy.c, 20)  # 20일 이동평균
current = dy.c()         # 현재 종가

# 판단 또는 결과값 반환
result = current > ma20  # 현재가가 20일 이동평균보다 높으면 True
```

모든 스크립트는 최종적으로 `result` 변수에 결과값을 할당해야 합니다. 이 값이 스크립트의 반환값이 됩니다.

### 2.2 반환 타입에 따른 스크립트 용도

스크립트의 반환 타입에 따라 다양한 용도로 활용할 수 있습니다:

- **Boolean (True/False)**: 매수/매도 판단용 스크립트
- **Number (int/float)**: 가격, 수량, 지표값 계산 스크립트
- **String**: 메시지, 알림, 로그 생성 스크립트
- **List/Dictionary**: 복잡한 데이터 구조가 필요한 분석 스크립트
- **None**: 다른 스크립트에서 사용하는 중간 계산 스크립트

예시:
```python
# Boolean 반환 스크립트 (매수 조건)
result = dy.c() > dy.ma(dy.c, 20) and dy.v() > dy.ma(dy.v, 20) * 2

# Number 반환 스크립트 (매수 가격 계산)
result = min(dy.c() * 1.01, dy.h() * 0.99)

# String 반환 스크립트 (알림 메시지)
result = f"{name} 종목이 {dy.c()} 원에 매수 신호 발생"
```

## 3. ChartManager 함수

### 3.1 인스턴스 생성

ChartManager 클래스는 차트 데이터에 접근하고 분석하는 기능을 제공합니다. 다양한 주기의 차트 데이터를 다룰 수 있습니다.
지원 되는 종목은 실행 된 매수검색식에 검색 된 종목에 한해서 가능 합니다.


```python
# 10분봉 차트 인스턴스 생성
mi10 = ChartManager(code, 'mi', 10)

# 특수 주기 분봉 차트 인스턴스 생성
mi7 = ChartManager(code, 'mi', 7)

# 일봉 차트 인스턴스 생성
dy = ChartManager(code, 'dy')

# 다른 종목이 필요할 경우
dy_005930 = ChartManager('005930, 'dy')
dy_code = ChartManger(code, 'dy')
삼성높음 = dy_005930.c() > dy_code.c()
```

### 3.2 기본 데이터 함수

ChartManager는 OHLCV(시가, 고가, 저가, 종가, 거래량) 데이터에 쉽게 접근할 수 있는 메서드를 제공합니다:

```python
cm = ChartManager(code, 'dy')  # 일봉 차트

# 기본 가격 데이터 접근
cm.o()      # 현재 봉의 시가
cm.h()      # 현재 봉의 고가
cm.l()      # 현재 봉의 저가
cm.c()      # 현재 봉의 종가
cm.v()      # 현재 봉의 거래량
cm.a()      # 현재 봉의 거래대금

# 이전 봉 데이터 접근 (n: 이전 봉 개수)
cm.c(1)     # 1봉 이전의 종가
cm.c(5)     # 5봉 이전의 종가
cm.v(3)     # 3봉 이전의 거래량

# 날짜 및 시간 정보
cm.time()   # 현재 봉의 시간 (분봉 차트의 경우)
cm.today()  # 오늘 날짜 (YYYYMMDD 형식)
```
### 3.3 이동평균 함수

이동평균은 가격의 추세를 파악하는 데 중요한 지표입니다. ChartManager는 여러 종류의 이동평균을 계산하는 함수를 제공합니다:

```python
cm = ChartManager(code, 'dy')

# 다양한 이동평균 계산
sma = cm.ma(cm.c, 20)                # 20일 단순이동평균 (기본값)
sma_alt = cm.avg(cm.c, 20)           # 20일 단순이동평균 (avg 메서드)
ema = cm.ma(cm.c, 20, k='e')         # 20일 지수이동평균
ema_alt = cm.eavg(cm.c, 20)          # 20일 지수이동평균 (eavg 메서드)
wma = cm.ma(cm.c, 20, k='w')         # 20일 가중이동평균
wma_alt = cm.wavg(cm.c, 20)          # 20일 가중이동평균 (wavg 메서드)

# 이전 데이터의 이동평균
prev_sma = cm.ma(cm.c, 20, 1)        # 1봉 이전의 20일 단순이동평균
prev_ema = cm.eavg(cm.c, 20, 5)      # 5봉 이전의 20일 지수이동평균

# 다른 데이터의 이동평균
vol_sma = cm.ma(cm.v, 20)            # 20일 거래량 단순이동평균
high_sma = cm.ma(cm.h, 20)           # 20일 고가 단순이동평균
```

**매개변수 설명**:
- `a`: 값을 가져올 함수 (c, o, h, l, v, a 등)
- `n`: 기간 (일수 또는 봉 수)
- `m`: 이전 봉 위치 (기본값 0, 현재 봉)
- `k`: 이동평균 유형 ('a': 단순, 'e': 지수, 'w': 가중)

### 3.4 indicator와 offset
```python
# 스크립트 예시
dy = ChartManager(code, 'dy')

# indicator로 함수처럼 호출 가능한 지표 생성
ma20 = dy.indicator(dy.ma, dy.c, 20)
rsi14 = dy.indicator(dy.rsi, 14)

# ma(offset)으로 이전 값 접근
current_ma20 = ma20()        # 현재 MA20
prev_ma20 = ma20(1)          # 1일 전 MA20
prev2_ma20 = ma20(2)         # 2일 전 MA20

# MACD도 동일하게 활용
macd = dy.indicator(dy.macd, 12, 26, 9)
current_macd, current_signal, current_hist = macd()
prev_macd, prev_signal, prev_hist = macd(1)

# 조건 판단
if ma20() > ma20(1) and rsi14() < 70:
    result = True
```
### 3.4 기술적 지표 함수

ChartManager는 다양한 기술적 지표를 계산하는 함수를 제공합니다:

```python
cm = ChartManager(code, 'dy')

# RSI (상대강도지수)
rsi = cm.rsi()                # 기본 14일 RSI
rsi_9 = cm.rsi(9)             # 9일 RSI
rsi_prev = cm.rsi(14, 1)      # 1봉 이전의 14일 RSI

# MACD (이동평균수렴확산지수)
macd, signal, hist = cm.macd()  # 기본 MACD (12, 26, 9)
macd2, signal2, hist2 = cm.macd(5, 35, 5)  # 커스텀 MACD

# 볼린저 밴드
upper, middle, lower = cm.bollinger_bands()  # 기본 볼린저 밴드 (20일, 2시그마)
upper2, middle2, lower2 = cm.bollinger_bands(10, 2.5)  # 커스텀 볼린저 밴드

# 스토캐스틱
k, d = cm.stochastic()  # 기본 스토캐스틱 (14, 3)
k2, d2 = cm.stochastic(5, 3)  # 커스텀 스토캐스틱

# ATR (평균진폭)
atr = cm.atr()  # 기본 14일 ATR
atr_5 = cm.atr(5)  # 5일 ATR
```

### 3.5 값 계산 함수

ChartManager는 데이터 분석에 유용한 여러 계산 함수를 제공합니다:

```python
cm = ChartManager(code, 'dy')

# 최고값/최저값 찾기
highest = cm.highest(cm.h, 20)        # 20일간 고가 중 최고값
lowest = cm.lowest(cm.l, 20)          # 20일간 저가 중 최저값
prev_highest = cm.highest(cm.h, 20, 5) # 5봉 이전부터 20일간 고가 중 최고값

# 표준편차 계산
std_dev = cm.stdev(cm.c, 20)          # 20일간 종가의 표준편차

# 합계 계산
volume_sum = cm.sum(cm.v, 5)          # 5일간 거래량 합계
```

### 3.6 신호 함수

기술적 지표의 신호를 감지하는 함수들을 제공합니다:

```python
cm = ChartManager(code, 'dy')

# 골든크로스/데드크로스 감지
golden_cross = cm.cross_up(cm.ma(cm.c, 5), cm.ma(cm.c, 20))
dead_cross = cm.cross_down(cm.ma(cm.c, 5), cm.ma(cm.c, 20))

# 특정 조건 이후 경과한 봉 개수
days_since_up = cm.bars_since(lambda n: cm.c(n) > cm.o(n))  # 음봉 이후 경과한 봉 수

# 특정 조건이 만족된 시점의 값
value_at_cross = cm.value_when(1, 
                              lambda n: cm.cross_up(cm.ma(cm.c, 5), cm.ma(cm.c, 20), n), 
                              cm.c)  # 첫 번째 골든크로스 시점의 종가
```

### 3.7 캔들 패턴 함수

캔들 패턴 감지를 위한 함수들이 제공됩니다:

```python
cm = ChartManager(code, 'dy')

# 기본 캔들 패턴 감지
is_doji = cm.is_doji()                 # 도지 캔들 확인
is_hammer = cm.is_hammer()             # 망치형 캔들 확인
is_bull_engulfing = cm.is_engulfing(bullish=True)  # 상승 포괄형 패턴 확인
is_bear_engulfing = cm.is_engulfing(bullish=False) # 하락 포괄형 패턴 확인

# 이전 봉의 패턴 확인
prev_doji = cm.is_doji(1)              # 1봉 이전 도지 캔들 확인
```
### 3.8 그 밖의 함수들

ChartManager는 추세 분석, 모멘텀 계산 등 다양한 보조 함수들을 제공합니다:

```python
cm = ChartManager(code, 'dy')

# 추세 분석
uptrend = cm.is_uptrend()              # 상승 추세 확인(기본 14일)
downtrend = cm.is_downtrend(30)        # 하락 추세 확인(30일)

# 모멘텀 계산
momentum = cm.momentum()               # 현재 모멘텀(기본 10일)
momentum_5 = cm.momentum(5)            # 5일 모멘텀

# 변화율 계산
roc = cm.rate_of_change()              # 변화율(기본 1일)
roc_5 = cm.rate_of_change(5)           # 5일 변화율

# 거래량 분석
vol_ratio = cm.normalized_volume()      # 정규화된 거래량(기본 20일 평균 대비)
```

## 4. Python 함수 사용

### 4.1 사용가능, 불가능 모듈

스크립트 시스템에서는 보안상의 이유로 사용 가능한 모듈이 제한되어 있습니다.

**사용 가능한 모듈**:
- `re`: 정규 표현식
- `math`: 수학 함수
- `datetime`: 날짜/시간 처리
- `random`: 난수 생성
- `logging`: 로그 기록
- `json`: JSON 처리
- `collections`: 컬렉션 자료구조

**사용 불가능한 모듈**:
- `os`: 운영체제 접근
- `sys`: 시스템 접근
- `subprocess`: 외부 프로세스 실행
- `socket`: 네트워크 소켓
- 그 외 파일 시스템, 네트워크, 외부 프로세스와 관련된 모듈

### 4.2 내장 함수

다음 Python 내장 함수들을 사용할 수 있습니다:

```python
# 기본 데이터 타입
int, float, str, bool, list, dict, set, tuple

# 데이터 처리 함수
len, max, min, sum, abs, all, any, round, sorted, enumerate, zip, range

# 형변환 함수
int, float, str, bool, list, dict, set, tuple
```

예시:
```python
# 내장함수 사용 예
dy = ChartManager(code, 'dy')
closes = [dy.c(i) for i in range(5)]  # 최근 5일 종가 리스트
avg_close = sum(closes) / len(closes)  # 평균 종가 계산
max_close = max(closes)               # 최고 종가
is_all_up = all(closes[i] > closes[i+1] for i in range(len(closes)-1))  # 모두 상승 중인지
```

### 4.3 변수 및 자료형

스크립트 내에서는 파이썬의 기본 자료형을 모두 사용할 수 있습니다:

```python
# 숫자 타입
integer_var = 123
float_var = 45.67

# 문자열
string_var = "삼성전자"
f_string = f"{name} 종목의 현재가: {price}"

# 불리언
bool_var = True
comparison = price > 50000

# 리스트
price_list = [100, 200, 300, 400, 500]
mixed_list = [1, "문자열", True, [1, 2, 3]]
list_comp = [dy.c(i) for i in range(5)]  # 리스트 컴프리헨션

# 딕셔너리
stock_info = {
    "code": "005930",
    "name": "삼성전자",
    "current_price": 65000,
    "prices": [63000, 64000, 65000]
}

# 집합
unique_values = {1, 2, 3, 4, 5}
```

### 4.4 조건문 및 논리 연산

스크립트 내에서 조건문과 논리 연산자를 사용할 수 있습니다:

```python
dy = ChartManager(code, 'dy')

# 기본 조건문
if dy.c() > dy.ma(dy.c, 20):
    result = True
else:
    result = False

# 복합 조건문
if dy.c() > dy.ma(dy.c, 20) and dy.v() > dy.ma(dy.v, 20):
    result = "강한 매수 신호"
elif dy.c() > dy.ma(dy.c, 20):
    result = "약한 매수 신호"
else:
    result = "매수 신호 없음"

# 논리 연산자
is_bullish = dy.c() > dy.o()
is_high_volume = dy.v() > dy.ma(dy.v, 20)
is_trending = dy.c() > dy.ma(dy.c, 20)

buy_signal = is_bullish and is_high_volume and is_trending

# 삼항 연산자
result = "매수" if dy.c() > dy.ma(dy.c, 20) else "관망"
```
### 4.5 반복문과 배열

스크립트 내에서 for 루프를 사용하여 데이터를 처리할 수 있습니다:

```python
dy = ChartManager(code, 'dy')

# 리스트 생성
closes = []
for i in range(5):
    closes.append(dy.c(i))

# 최근 5일간 상승 횟수 계산
up_days = 0
for i in range(5):
    if dy.c(i) > dy.o(i):
        up_days += 1

# 리스트 컴프리헨션 (더 간결한 방법)
closes = [dy.c(i) for i in range(5)]
up_days = sum(1 for i in range(5) if dy.c(i) > dy.o(i))

# 안전한 루프 사용 (무한 루프 방지)
result = loop(range(5), lambda i: dy.c(i))  # 최근 5일 종가 리스트
```

**주의**: 성능 및 보안 상의 이유로 `while` 루프는 허용되지 않습니다. 대신 `for` 루프나 `loop()` 함수를 사용하세요.

### 4.6 loop(), iif() 함수

시스템에서 제공하는 특수 함수들:

```python
# loop() 함수: 안전한 반복 처리
result = loop(range(10), lambda i: i * 2)  # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

# iif() 함수: 조건부 값 선택 (삼항 연산자 대체)
result = iif(price > 50000, "비싸다", "저렴하다")

# 복잡한 조건에서 iif() 활용
signal = iif(
    dy.c() > dy.ma(dy.c, 20),
    iif(dy.v() > dy.ma(dy.v, 20) * 1.5, "강한 매수", "약한 매수"),
    "매수 신호 없음"
)
```

### 4.7 lambda 식 해설

lambda 식은 간단한 익명 함수를 만드는 방법입니다:

```python
# 기본 lambda 함수
square = lambda x: x * x
result = square(5)  # 25

# 여러 인자를 받는 lambda
add = lambda x, y: x + y
result = add(3, 4)  # 7

# 조건부 lambda
is_up = lambda i: dy.c(i) > dy.o(i)
up_days = sum(1 for i in range(5) if is_up(i))

# 함수에 lambda 전달
highest_close = dy.highest(lambda i: dy.c(i), 20)  # 최근 20일 중 최고 종가
```

### 4.8 로깅

스크립트 내에서 로깅 함수를 사용하여 디버깅 및 정보 출력을 할 수 있습니다:

```python
# 다양한 로그 레벨
debug("디버그 메시지")            # 상세 디버깅 정보
info("정보 메시지")               # 일반 정보
warning("경고 메시지")            # 경고
error("오류 메시지")              # 오류
critical("심각한 오류 메시지")     # 심각한 오류

# 변수 값 포함
current_price = dy.c()
debug(f"현재 가격: {current_price}")

# 조건부 로깅
if dy.c() > dy.ma(dy.c, 20):
    info(f"{name} 종목 상승 추세 진입 (현재가: {price})")
```

### 4.9 예외 처리

스크립트 내에서 예외를 처리하여 안정적인 실행을 보장할 수 있습니다:

```python
# 기본 예외 처리
try:
    result = price / qty  # qty가 0일 수 있음
except ZeroDivisionError:
    result = 0
    error("수량이 0이어서 계산할 수 없습니다")

# 다양한 예외 처리
try:
    high_value = float(high_price_str)
    ratio = current_price / high_value
except ValueError:
    error("가격 값이 올바른 숫자 형식이 아닙니다")
    ratio = 1.0
except ZeroDivisionError:
    warning("최고가가 0입니다")
    ratio = 1.0
except Exception as e:
    error(f"알 수 없는 오류 발생: {e}")
    ratio = 1.0

# finally 블록
try:
    # 계산 수행
    value = complex_calculation()
except Exception:
    value = default_value
finally:
    # 무조건 실행되는 코드
    debug("계산 완료")
```
## 5. 스크립트 작성

### 5.1 기본 작성 법과 변수 사용

스크립트 작성 시 다음과 같은 기본 원칙을 따르세요:

1. 모든 스크립트는 최종적으로 `result` 변수에 결과값을 할당해야 합니다.
2. 예약 변수(`code`, `name`, `qty`, `price`)는 자동으로 제공되며 바로 사용할 수 있습니다.
3. 일반적으로 스크립트는 차트 데이터를 분석하여 매매 신호나 가격 정보를 반환합니다.

```python
# 기본 스크립트 예제
dy = ChartManager(code, 'dy')
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)

# 예약 변수 사용
current_value = qty * price
expected_value = qty * dy.c()

# 골든크로스 확인
result = ma20 > ma60 and dy.c() > ma20
```

### 5.2 함수 처럼 사용하는 스크립트

스크립트는 함수처럼 작동하여 다른 스크립트에서 호출될 수 있습니다:

```python
# RSI 계산 스크립트
dy = ChartManager(code, 'dy')
rsi_period = 14  # 기본값

# 매개변수 확인 (다른 스크립트에서 전달 가능)
if 'period' in globals():
    rsi_period = period

# RSI 계산
result = dy.rsi(rsi_period)
```

이 스크립트는 다른 스크립트에서 다음과 같이 호출할 수 있습니다:

```python
# 다른 스크립트에서 호출
rsi_value = calculate_rsi(period=9)  # 9일 RSI 계산
```

### 5.3 매매 판단에 사용하는 스크립트

매매 판단에 사용되는 스크립트는 일반적으로 불리언(True/False) 값을 반환합니다:

```python
# 매수 판단 스크립트
dy = ChartManager(code, 'dy')

# 이동평균 확인
ma5 = dy.ma(dy.c, 5)
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)

# MACD 확인
macd, signal, hist = dy.macd()

# 매수 조건 설정
condition1 = ma5 > ma20  # 단기 이평이 중기 이평보다 위
condition2 = ma20 > ma60  # 중기 이평이 장기 이평보다 위
condition3 = hist > 0 and hist > hist(1)  # MACD 히스토그램 증가
condition4 = dy.v() > dy.ma(dy.v, 20) * 1.5  # 거래량 증가

# 최종 매수 신호
result = condition1 and condition2 and condition3 and condition4

# 로깅
if result:
    info(f"{name}({code}) 매수 신호 발생: 현재가 {price}원")
```

### 5.4 여러 주기의 혼합 사용

다양한 주기의 차트 데이터를 분석하여 더 정교한 전략을 구현할 수 있습니다:

```python
# 다양한 주기 분석 스크립트
dy = ChartManager(code, 'dy')    # 일봉
mi60 = ChartManager(code, 'mi', 60)  # 60분봉
wk = ChartManager(code, 'wk')    # 주봉

# 각 주기별 상승 추세 확인
daily_uptrend = dy.c() > dy.ma(dy.c, 20)
hourly_uptrend = mi60.c() > mi60.ma(mi60.c, 20)
weekly_uptrend = wk.c() > wk.ma(wk.c, 20)

# 모든 주기에서 상승 추세일 때 매수 신호
result = daily_uptrend and hourly_uptrend and weekly_uptrend
```

### 5.5 기 작성된 스크립트를 재사용하여 작성하는 방법과 인수 전달

이미 작성된 스크립트를 재활용하여 새로운 전략을 쉽게 구현할 수 있습니다:

```python
# 기존 스크립트를 호출하는 방법
# (calculate_rsi, check_macd_signal, golden_cross 스크립트가 이미 존재한다고 가정)

# 기본 호출
rsi_value = calculate_rsi()  # 기본 매개변수 사용

# 매개변수 전달
short_rsi = calculate_rsi(period=9)  # 커스텀 기간 지정
is_macd_buy = check_macd_signal(fast=8, slow=17)  # 여러 매개변수 전달

# 종목 코드 지정
samsung_cross = golden_cross(code='005930')  # 삼성전자 골든크로스 확인
hyundai_cross = golden_cross(code='005380')  # 현대차 골든크로스 확인

# 복합 조건
result = rsi_value < 30 and is_macd_buy  # 과매도 상태이면서 MACD 매수 신호
```

매개변수는 키워드 인자(keyword arguments)로 전달됩니다. 전달된 매개변수는 호출된 스크립트 내에서 변수로 사용할 수 있습니다.

### 5.6 스크립트 테스트와 디버깅

스크립트를 작성하고 테스트하는 방법:

1. **로깅 활용**: `debug()`, `info()` 함수를 사용하여 중간 값을 확인합니다.
2. **단계적 개발**: 복잡한 스크립트는 작은 부분으로 나누어 개발하고 테스트합니다.
3. **예외 처리**: 오류가 발생할 수 있는 부분에 예외 처리를 추가합니다.
4. **테스트 케이스**: 다양한 시장 상황에서 스크립트를 테스트합니다.

```python
# 디버깅을 포함한 스크립트 예제
dy = ChartManager(code, 'dy')

try:
    # 데이터 수집
    current = dy.c()
    ma20 = dy.ma(dy.c, 20)
    ma60 = dy.ma(dy.c, 60)
    
    # 중간 값 로깅
    debug(f"현재가: {current}, 20일 이평: {ma20}, 60일 이평: {ma60}")
    
    # 조건 확인
    condition1 = current > ma20
    condition2 = ma20 > ma60
    
    debug(f"조건1 (현재가 > 20일 이평): {condition1}")
    debug(f"조건2 (20일 이평 > 60일 이평): {condition2}")
    
    # 결과 계산
    result = condition1 and condition2
    info(f"최종 판단: {'매수' if result else '관망'}")
    
except Exception as e:
    error(f"스크립트 실행 중 오류 발생: {e}")
    result = False
```
## 6. 스크립트 작성의 고급 기법

### 6.1 복합 지표 생성

여러 기술적 지표를 조합하여 더 강력한 신호를 생성할 수 있습니다:

```python
# 복합 지표 스크립트
dy = ChartManager(code, 'dy')

# 이동평균 데이터
ma5 = dy.ma(dy.c, 5)
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)

# RSI 데이터
rsi = dy.rsi(14)
rsi_prev = dy.rsi(14, 1)

# 볼린저 밴드
upper, middle, lower = dy.bollinger_bands(20, 2)

# MACD
macd, signal, hist = dy.macd(12, 26, 9)

# 복합 지표 계산
trend_strength = ((dy.c() - ma60) / ma60) * 100  # 장기 추세 강도 (%)
volatility = (upper - lower) / middle * 100      # 변동성 (%)
momentum_score = (rsi - rsi_prev) * 2            # 모멘텀 점수

# 최종 점수 계산 (0-100)
final_score = 0

# 추세 점수 (최대 40점)
if dy.c() > ma5 > ma20 > ma60:  # 강한 상승 추세
    final_score += 40
elif dy.c() > ma20 > ma60:      # 중간 상승 추세
    final_score += 30
elif dy.c() > ma60:              # 약한 상승 추세
    final_score += 20
elif dy.c() < ma5 < ma20 < ma60:  # 강한 하락 추세
    final_score += 0
else:                            # 중립
    final_score += 10

# RSI 점수 (최대 25점)
if rsi > 70:                     # 과매수
    final_score += 5
elif rsi > 60:                   # 강세
    final_score += 25
elif rsi > 50:                   # 중립 상승
    final_score += 20
elif rsi > 40:                   # 중립 하락
    final_score += 10
elif rsi > 30:                   # 약세
    final_score += 5
else:                            # 과매도
    final_score += 15

# MACD 점수 (최대 25점)
if hist > 0 and hist > hist(1):  # 상승 모멘텀 강화
    final_score += 25
elif hist > 0:                   # 상승 모멘텀
    final_score += 20
elif hist > hist(1):             # 하락세 둔화
    final_score += 15
else:                            # 하락 모멘텀
    final_score += 5

# 볼륨 점수 (최대 10점)
volume_ratio = dy.v() / dy.ma(dy.v, 20)
if volume_ratio > 2.0:           # 매우 높은 거래량
    final_score += 10
elif volume_ratio > 1.5:         # 높은 거래량
    final_score += 8
elif volume_ratio > 1.0:         # 평균 이상 거래량
    final_score += 5
else:                            # 평균 이하 거래량
    final_score += 2

# 최종 매수 강도 점수 반환
result = final_score  # 0-100 사이의 값 반환
```

### 6.2 날짜/시간 기반 전략

특정 시간대나 요일에 따라 매매 전략을 다르게 적용할 수 있습니다:

```python
# 날짜/시간 기반 전략
import datetime

# 현재 날짜/시간 정보
now = datetime.datetime.now()
weekday = now.weekday()  # 0:월요일, 1:화요일, ..., 4:금요일, 5:토요일, 6:일요일
hour = now.hour
minute = now.minute

# 차트 데이터
mi15 = ChartManager(code, 'mi', 15)  # 15분봉
dy = ChartManager(code, 'dy')        # 일봉

# 전략 설정
if weekday == 0:  # 월요일은 보수적
    strategy = "conservative"
    threshold = 2.0
elif weekday == 4:  # 금요일은 더 보수적
    strategy = "very_conservative"
    threshold = 3.0
else:  # 다른 날은 일반적
    strategy = "normal"
    threshold = 1.5

# 시간대별 전략
if 9 <= hour < 10:  # 장 초반
    # 갭 분석
    gap_percentage = (dy.o() - dy.c(1)) / dy.c(1) * 100
    signal = gap_percentage > threshold  # 갭 상승 확인
elif 14 <= hour < 15:  # 장 후반
    # 당일 추세 분석
    intraday_change = (mi15.c() - dy.o()) / dy.o() * 100
    signal = intraday_change > threshold  # 당일 상승세 확인
else:  # 그 외 시간대
    # 표준 신호
    signal = mi15.c() > mi15.ma(mi15.c, 20) and dy.c() > dy.ma(dy.c, 20)

result = signal
```

### 6.3 확률 기반 접근법

과거 패턴 분석을 통해 확률적 접근법을 구현할 수 있습니다:

```python
# 확률 기반 매매 전략
dy = ChartManager(code, 'dy')

# 최근 N일간의 상승/하락 패턴 분석
N = 5
up_down_pattern = []
for i in range(N):
    up_down_pattern.append(1 if dy.c(i) > dy.c(i+1) else 0)

# 패턴을 문자열로 변환 (이진수 문자열)
pattern_str = ''.join(map(str, up_down_pattern))

# 과거에 이 패턴 이후 상승한 확률 계산
# (실제로는 더 많은 과거 데이터를 분석해야 함)
success_probabilities = {
    '11111': 0.3,  # 5일 연속 상승 후 다음날 상승 확률 30%
    '00000': 0.65, # 5일 연속 하락 후 다음날 상승 확률 65%
    '10101': 0.55, # 상승/하락 반복 후 다음날 상승 확률 55%
    '01010': 0.48, # 하락/상승 반복 후 다음날 상승 확률 48%
    '11110': 0.40, # 4일 상승 후 1일 하락 시 다음날 상승 확률 40%
    '00001': 0.60, # 4일 하락 후 1일 상승 시 다음날 상승 확률 60%
    # ... 다른 패턴들
}

# 현재 패턴의 성공 확률 (없으면 기본값 50%)
probability = success_probabilities.get(pattern_str, 0.5)

# 추가 요소로 확률 보정
# RSI로 보정
rsi = dy.rsi()
if rsi > 70:  # 과매수
    probability -= 0.1
elif rsi < 30:  # 과매도
    probability += 0.1

# 거래량으로 보정
vol_ratio = dy.v() / dy.ma(dy.v, 20)
if vol_ratio > 2.0:  # 거래량 급증
    probability += 0.05

# 최종 결정 (확률이 60% 이상일 때 매수 신호)
result = probability >= 0.6

# 로깅
debug(f"현재 패턴: {pattern_str}, 상승 확률: {probability:.2%}")
```
## 7. 스크립트 작성 시 팁과 주의 사항

### 7.1 성능 최적화 팁

스크립트 실행 성능을 향상시키기 위한 팁:

1. **불필요한 계산 피하기**: 같은 값을 반복해서 계산하지 말고 변수에 저장하여 재사용하세요.

```python
# 비효율적인 방법
if dy.ma(dy.c, 20) > dy.ma(dy.c, 60) and dy.c() > dy.ma(dy.c, 20):
    result = True

# 효율적인 방법
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)
if ma20 > ma60 and dy.c() > ma20:
    result = True
```

2. **필요한 데이터만 로드**: 사용하지 않는 주기의 차트 데이터는 로드하지 마세요.

3. **복잡한 조건은 단계적으로 평가**: 계산 비용이 큰 조건은 간단한 조건 이후에 평가하세요.

```python
# 비효율적인 방법
result = (complex_calculation1() and complex_calculation2()) or simple_check()

# 효율적인 방법 (단락 평가 활용)
if simple_check():
    result = True
else:
    result = complex_calculation1() and complex_calculation2()
```

4. **리스트 컴프리헨션 활용**: 루프보다 리스트 컴프리헨션이 일반적으로 더 빠릅니다.

```python
# 비효율적인 방법
values = []
for i in range(10):
    values.append(dy.c(i))

# 효율적인 방법
values = [dy.c(i) for i in range(10)]
```

5. **최적화된 내장 함수 사용**: 루프 대신 `sum()`, `max()`, `min()` 등의 내장 함수를 사용하세요.

```python
# 비효율적인 방법
total = 0
for i in range(5):
    total += dy.c(i)
avg = total / 5

# 효율적인 방법
values = [dy.c(i) for i in range(5)]
avg = sum(values) / len(values)
```

6. **캐싱 활용**: 자주 사용하는 값은 변수에 저장하여 재사용하세요.

```python
# 비효율적인 방법
for i in range(10):
    ratio = dy.c(i) / dy.ma(dy.c, 20, i)
    # ratio 사용...

# 효율적인 방법
closes = [dy.c(i) for i in range(10)]
ma20_values = [dy.ma(dy.c, 20, i) for i in range(10)]
ratios = [c / ma for c, ma in zip(closes, ma20_values)]
# ratios 사용...
```

### 7.2 일반적인 실수와 주의 사항

스크립트 작성 시 흔히 발생하는 실수와 주의사항:

1. **필수 변수 누락**: 모든 스크립트는 반드시 `result` 변수에 결과를 할당해야 합니다.

2. **제로 디비전 에러**: 숫자를 0으로 나누는 상황을 방지하세요.

```python
# 잘못된 방법
ratio = current_price / average_price  # average_price가 0일 수 있음

# 올바른 방법
ratio = current_price / average_price if average_price != 0 else 1.0
```

3. **타입 혼합**: 다른 타입끼리 연산 시 예상치 못한 결과가 발생할 수 있습니다.

```python
# 잘못된 방법
result = "현재가: " + dy.c()  # TypeError 발생

# 올바른 방법
result = f"현재가: {dy.c()}"
```

4. **while 루프 사용**: `while` 루프는 허용되지 않으므로 `for` 루프나 `loop()` 함수를 사용하세요.

5. **큰 데이터 처리**: 너무 많은 데이터를 한 번에 처리하면 성능 문제가 발생할 수 있습니다.

6. **무거운 연산**: 복잡한 수학 연산이나 재귀 호출 등은 성능 저하의 원인이 됩니다.

### 7.3 디버깅 팁

스크립트 디버깅을 위한 효과적인 방법:

1. **로깅 활용**: 중요한 값이나 상태를 로깅하여 문제를 찾습니다.

```python
debug(f"현재가: {dy.c()}, MA20: {ma20}, RSI: {rsi}")
```

2. **단계별 검증**: 복잡한 로직은 작은 부분으로 나누어 각각 검증합니다.

```python
debug("조건 1 검증 중...")
condition1 = dy.c() > dy.ma(dy.c, 20)
debug(f"조건 1 결과: {condition1}")

debug("조건 2 검증 중...")
condition2 = dy.v() > dy.ma(dy.v, 20) * 1.5
debug(f"조건 2 결과: {condition2}")

result = condition1 and condition2
```

3. **예외 처리**: 오류가 발생할 수 있는 부분에 예외 처리를 추가합니다.

4. **기본값 설정**: 누락될 수 있는 값에는 기본값을 설정합니다.

```python
period = kwargs.get('period', 14)  # period가 없으면 14 사용
```

5. **상태 확인**: 계산 전에 필요한 데이터의 유효성을 먼저 확인합니다.

```python
if len(values) < period:
    debug(f"데이터 부족: {len(values)} < {period}")
    result = None
    return
```
## 8. 예제 스크립트, 고급 스크립트

### 8.1 기본 매매 전략 스크립트

#### 골든크로스 매수 전략

```python
# 골든크로스 매수 전략
dy = ChartManager(code, 'dy')

# 이동평균 계산
ma5 = dy.ma(dy.c, 5)
ma20 = dy.ma(dy.c, 20)

# 골든크로스 확인 (5일선이 20일선을 상향 돌파)
cross_up = ma5 > ma20 and ma5(1) <= ma20(1)

# 추가 확인: 거래량 증가
volume_increase = dy.v() > dy.ma(dy.v, 20) * 1.2

# 최종 매수 신호
result = cross_up and volume_increase

# 로깅
if result:
    debug(f"{name}({code}) 매수 신호 발생: 골든크로스, 거래량 증가")
```

#### RSI 과매도 매수 전략

```python
# RSI 과매도 반등 매수 전략
dy = ChartManager(code, 'dy')

# RSI 계산
rsi = dy.rsi(14)
rsi_prev = dy.rsi(14, 1)

# 과매도 상태에서 반등
oversold_bounce = rsi_prev < 30 and rsi > rsi_prev

# 추가 확인: 양봉 발생
bullish_candle = dy.c() > dy.o()

# 최종 매수 신호
result = oversold_bounce and bullish_candle

# 로깅
if result:
    debug(f"{name}({code}) 매수 신호 발생: RSI 과매도 반등, 양봉")
```

### 8.2 고급 매매 전략 스크립트

#### 멀티 타임프레임 돌파 전략

```python
# 멀티 타임프레임 돌파 전략
# 여러 주기에서 동시에 저항선 돌파 시 매수

# 다양한 주기 차트 설정
dy = ChartManager(code, 'dy')    # 일봉
mi60 = ChartManager(code, 'mi', 60)  # 60분봉
wk = ChartManager(code, 'wk')    # 주봉

# 각 차트별 저항선 설정 (최근 20봉 중 최고가의 0.5% 위)
daily_resistance = dy.highest(dy.h, 20) * 1.005
hourly_resistance = mi60.highest(mi60.h, 20) * 1.005
weekly_resistance = wk.highest(wk.h, 20) * 1.005

# 현재가
current = dy.c()

# 돌파 확인
daily_breakout = current > daily_resistance
hourly_breakout = mi60.c() > hourly_resistance
weekly_approaching = current > weekly_resistance * 0.98  # 주봉 저항선 근처

# 추가 조건: RSI 과열 상태 아님
daily_rsi = dy.rsi()
rsi_ok = daily_rsi < 70

# 볼륨 확인
volume_surge = dy.v() > dy.ma(dy.v, 20) * 1.5

# 최종 매수 신호 (일봉과 60분봉 돌파, 주봉 저항선 접근, RSI 과열 아님, 거래량 급증)
result = daily_breakout and hourly_breakout and weekly_approaching and rsi_ok and volume_surge

# 로깅
if result:
    breakout_strength = (current - daily_resistance) / daily_resistance * 100
    debug(f"{name}({code}) 매수 신호: 멀티타임프레임 돌파")
    debug(f"돌파 강도: {breakout_strength:.2f}%, RSI: {daily_rsi:.1f}")
```

#### MACD 히스토그램 다이버전스 전략

```python
# MACD 히스토그램 다이버전스 전략
dy = ChartManager(code, 'dy')

# MACD 데이터 수집
macd_periods = 10  # 확인할 기간
macd_values = []
histogram_values = []

for i in range(macd_periods):
    macd, signal, hist = dy.macd(12, 26, 9, i)
    macd_values.append(macd)
    histogram_values.append(hist)

# 종가 데이터 수집
closes = [dy.c(i) for i in range(macd_periods)]

# 가격 하락 중 MACD 히스토그램 개선 확인 (숨겨진 강세 다이버전스)
price_downtrend = closes[0] < closes[2] < closes[4] < closes[6]
hist_improving = histogram_values[0] > histogram_values[2]  # 히스토그램 개선

# 추가 조건: 히스토그램이 음수에서 개선 중
histogram_negative = histogram_values[0] < 0
crossover_soon = histogram_values[0] > histogram_values[1] * 1.5  # 빠르게 개선 중

# 볼륨 확인
volume_steady = dy.v() > dy.ma(dy.v, 20) * 0.8  # 평균 거래량의 80% 이상

# 최종 매수 신호
result = price_downtrend and hist_improving and histogram_negative and crossover_soon and volume_steady

# 로깅
if result:
    debug(f"{name}({code}) 매수 신호: MACD 히스토그램 다이버전스")
    debug(f"MACD: {macd_values[0]:.2f}, 히스토그램: {histogram_values[0]:.2f}")
```

### 8.3 가격 계산 스크립트

#### 매수 가격 최적화 스크립트

```python
# 매수 가격 최적화 스크립트
dy = ChartManager(code, 'dy')

# 현재 시장 상황 확인
current = dy.c()
ma20 = dy.ma(dy.c, 20)
atr = dy.atr(14)  # 평균 실제 범위

# 기준 매수 가격 설정
base_price = current

# 상황별 매수 가격 조정
if current > ma20 * 1.1:  # 20일 이평선보다 10% 이상 높은 경우 (과열)
    # 현재가보다 1 ATR 아래에 주문
    buy_price = current - atr
    debug(f"과열 구간: 현재가보다 1 ATR 아래 ({buy_price}) 매수 추천")
elif current > ma20:  # 상승 추세
    # 현재가의 0.5% 아래에 주문
    buy_price = current * 0.995
    debug(f"상승 추세: 현재가의 0.5% 아래 ({buy_price}) 매수 추천")
elif current > ma20 * 0.9:  # 20일 이평선 근처
    # 현재가로 주문
    buy_price = current
    debug(f"중립 구간: 현재가 ({buy_price}) 매수 추천")
else:  # 하락 추세
    # 추가 하락 가능성 대비, 현재가의 2% 아래에 주문
    buy_price = current * 0.98
    debug(f"하락 추세: 현재가의 2% 아래 ({buy_price}) 매수 추천")

# 매수 가격 반환
result = round(buy_price, 2)  # 소수점 둘째 자리까지 반올림
```

#### 목표가 및 손절가 계산 스크립트

```python
# 목표가 및 손절가 계산 스크립트
dy = ChartManager(code, 'dy')

# 손절가, 목표가 비율 설정 (기본값)
sl_ratio = 0.05  # 5% 손절
tp_ratio = 0.15  # 15% 목표

# 매개변수 확인 (사용자 정의)
if 'sl_percent' in globals():
    sl_ratio = sl_percent / 100
if 'tp_percent' in globals():
    tp_ratio = tp_percent / 100

# 현재 시장 상황 분석
current = dy.c()
atr = dy.atr(14)
rsi = dy.rsi()
volatility = (dy.h() - dy.l()) / dy.o() * 100  # 당일 변동폭 비율

# 변동성에 따른 조정
if volatility > 5:  # 고변동성
    sl_ratio = sl_ratio * 1.2  # 손절폭 20% 증가
    tp_ratio = tp_ratio * 1.1  # 목표가도 10% 증가
    debug("변동성이 높아 손절폭/목표폭 증가 적용")
elif volatility < 2:  # 저변동성
    sl_ratio = sl_ratio * 0.8  # 손절폭 20% 감소
    tp_ratio = tp_ratio * 0.9  # 목표가도 10% 감소
    debug("변동성이 낮아 손절폭/목표폭 감소 적용")

# RSI에 따른 조정
if rsi > 70:  # 과매수
    tp_ratio = tp_ratio * 0.9  # 목표가 10% 감소
elif rsi < 30:  # 과매도
    tp_ratio = tp_ratio * 1.1  # 목표가 10% 증가

# 손절가와 목표가 계산
stop_loss = current * (1 - sl_ratio)
take_profit = current * (1 + tp_ratio)

# 결과 반환 (사전 형태)
result = {
    "current_price": current,
    "stop_loss": round(stop_loss, 2),
    "take_profit": round(take_profit, 2),
    "sl_percent": round(sl_ratio * 100, 1),
    "tp_percent": round(tp_ratio * 100, 1)
}
```
# 스크립트 시스템 사용 안내서 - 부록

## 부록 A: 함수 레퍼런스

### A.1 기본 데이터 접근 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `o()` | 시가 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 시가 |
| `h()` | 고가 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 고가 |
| `l()` | 저가 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 저가 |
| `c()` | 종가 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 종가 |
| `v()` | 거래량 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 거래량 |
| `a()` | 거래대금 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 거래대금 |
| `time()` | 시간 | `n`: 이전 봉 위치 (기본값 0) | 해당 봉의 시간 (분봉 차트) |
| `today()` | 오늘 날짜 | 없음 | 현재 날짜 (YYYYMMDD 형식) |

**사용 예**:
```python
current_close = dy.c()      # 현재 봉의 종가
prev_close = dy.c(1)       # 1봉 이전의 종가
two_days_high = dy.h(2)    # 2봉 이전의 고가
```

### A.2 이동평균 관련 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `ma(a, n, m, k)` | 이동평균 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0)<br>`k`: 이동평균 유형 ('a', 'e', 'w') | 이동평균값 |
| `avg(a, n, m)` | 단순이동평균 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 단순이동평균값 |
| `eavg(a, n, m)` | 지수이동평균 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 지수이동평균값 |
| `wavg(a, n, m)` | 가중이동평균 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 가중이동평균값 |

**사용 예**:
```python
# 다양한 이동평균 계산
sma20 = dy.ma(dy.c, 20)             # 20일 단순이동평균
ema20 = dy.ma(dy.c, 20, k='e')      # 20일 지수이동평균
wma20 = dy.ma(dy.c, 20, k='w')      # 20일 가중이동평균

# 이전 데이터의 이동평균
prev_sma20 = dy.ma(dy.c, 20, 1)     # 1봉 이전의 20일 단순이동평균

# 다른 데이터의 이동평균
vol_sma20 = dy.ma(dy.v, 20)         # 20일 거래량 단순이동평균
```

### A.3 값 계산 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `highest(a, n, m)` | 최고값 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 해당 기간 내 최고값 |
| `lowest(a, n, m)` | 최저값 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 해당 기간 내 최저값 |
| `stdev(a, n, m)` | 표준편차 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 표준편차 |
| `sum(a, n, m)` | 합계 | `a`: 계산할 함수<br>`n`: 기간<br>`m`: 이전 봉 위치 (기본값 0) | 합계 |

**사용 예**:
```python
highest_high = dy.highest(dy.h, 20)     # 최근 20일 중 최고 고가
lowest_low = dy.lowest(dy.l, 20)        # 최근 20일 중 최저 저가
price_stdev = dy.stdev(dy.c, 20)        # 최근 20일 종가의 표준편차
total_volume = dy.sum(dy.v, 5)          # 최근 5일간 거래량 합계
```

### A.4 신호 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `cross_up(a, b)` | 상향돌파 | `a`, `b`: 비교할 함수/값 | a가 b를 상향돌파하면 True |
| `cross_down(a, b)` | 하향돌파 | `a`, `b`: 비교할 함수/값 | a가 b를 하향돌파하면 True |
| `bars_since(condition)` | 조건 이후 경과 봉 수 | `condition`: 조건 함수 | 조건이 참인 이후 경과한 봉 수 |
| `value_when(nth, condition, data_func)` | 조건 만족 시점의 값 | `nth`: n번째 조건 만족<br>`condition`: 조건 함수<br>`data_func`: 값 함수 | 조건 만족 시점의 값 |
| `highest_since(nth, condition, data_func)` | 조건 이후 최고값 | `nth`: n번째 조건 만족<br>`condition`: 조건 함수<br>`data_func`: 값 함수 | 조건 이후 최고값 |
| `lowest_since(nth, condition, data_func)` | 조건 이후 최저값 | `nth`: n번째 조건 만족<br>`condition`: 조건 함수<br>`data_func`: 값 함수 | 조건 이후 최저값 |

**사용 예**:
```python
# 골든크로스 확인
golden_cross = dy.cross_up(dy.ma(dy.c, 5), dy.ma(dy.c, 20))

# 데드크로스 확인
dead_cross = dy.cross_down(dy.ma(dy.c, 5), dy.ma(dy.c, 20))

# 마지막 상승봉 이후 경과한 봉 수
days_since_up = dy.bars_since(lambda n: dy.c(n) > dy.o(n))

# 골든크로스 시점의 종가
cross_price = dy.value_when(1, 
                         lambda n: dy.cross_up(dy.ma(dy.c, 5), dy.ma(dy.c, 20), n), 
                         dy.c)
```
### A.5 기술적 지표 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `rsi(period, m)` | RSI | `period`: 기간 (기본값 14)<br>`m`: 이전 봉 위치 (기본값 0) | RSI 값 (0-100) |
| `macd(fast, slow, signal, m)` | MACD | `fast`: 단기 EMA 기간 (기본값 12)<br>`slow`: 장기 EMA 기간 (기본값 26)<br>`signal`: 시그널 기간 (기본값 9)<br>`m`: 이전 봉 위치 (기본값 0) | (MACD, 시그널, 히스토그램) 튜플 |
| `bollinger_bands(period, std_dev, m)` | 볼린저 밴드 | `period`: 기간 (기본값 20)<br>`std_dev`: 표준편차 배수 (기본값 2)<br>`m`: 이전 봉 위치 (기본값 0) | (상단, 중간, 하단) 튜플 |
| `stochastic(k_period, d_period, m)` | 스토캐스틱 | `k_period`: %K 기간 (기본값 14)<br>`d_period`: %D 기간 (기본값 3)<br>`m`: 이전 봉 위치 (기본값 0) | (%K, %D) 튜플 |
| `atr(period, m)` | 평균실제범위 | `period`: 기간 (기본값 14)<br>`m`: 이전 봉 위치 (기본값 0) | ATR 값 |

**사용 예**:
```python
# RSI 계산
rsi_value = dy.rsi()                  # 기본 14일 RSI
rsi_9 = dy.rsi(9)                     # 9일 RSI
rsi_prev = dy.rsi(14, 1)              # 1봉 이전의 14일 RSI

# MACD 계산
macd, signal, hist = dy.macd()        # 기본 MACD (12, 26, 9)
macd2, signal2, hist2 = dy.macd(5, 35, 5)  # 커스텀 MACD

# 볼린저 밴드 계산
upper, middle, lower = dy.bollinger_bands()  # 기본 볼린저 밴드 (20일, 2시그마)
upper2, middle2, lower2 = dy.bollinger_bands(10, 2.5)  # 커스텀 볼린저 밴드

# 스토캐스틱 계산
k, d = dy.stochastic()                # 기본 스토캐스틱 (14, 3)
k2, d2 = dy.stochastic(5, 3)          # 커스텀 스토캐스틱

# ATR 계산
atr_value = dy.atr()                  # 기본 14일 ATR
atr_5 = dy.atr(5)                     # 5일 ATR
```

### A.6 캔들 패턴 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `is_doji(n, threshold)` | 도지 캔들 확인 | `n`: 이전 봉 위치 (기본값 0)<br>`threshold`: 도지 판정 임계값 (기본값 0.1) | 도지 캔들이면 True |
| `is_hammer(n)` | 망치형 캔들 확인 | `n`: 이전 봉 위치 (기본값 0) | 망치형 캔들이면 True |
| `is_engulfing(n, bullish)` | 포괄형 패턴 확인 | `n`: 이전 봉 위치 (기본값 0)<br>`bullish`: True면 상승 포괄, False면 하락 포괄 | 포괄형 패턴이면 True |

**사용 예**:
```python
# 캔들 패턴 확인
is_current_doji = dy.is_doji()                     # 현재 봉이 도지인지 확인
was_hammer = dy.is_hammer(1)                       # 이전 봉이 망치형인지 확인
bull_engulfing = dy.is_engulfing(bullish=True)     # 상승 포괄형 패턴 확인
bear_engulfing = dy.is_engulfing(bullish=False)    # 하락 포괄형 패턴 확인
```

### A.7 추세 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `is_uptrend(period, m)` | 상승 추세 확인 | `period`: 기간 (기본값 14)<br>`m`: 이전 봉 위치 (기본값 0) | 상승 추세이면 True |
| `is_downtrend(period, m)` | 하락 추세 확인 | `period`: 기간 (기본값 14)<br>`m`: 이전 봉 위치 (기본값 0) | 하락 추세이면 True |
| `momentum(period, m)` | 모멘텀 계산 | `period`: 기간 (기본값 10)<br>`m`: 이전 봉 위치 (기본값 0) | 모멘텀 값 |
| `rate_of_change(period, m)` | 변화율 계산 | `period`: 기간 (기본값 1)<br>`m`: 이전 봉 위치 (기본값 0) | 변화율 (%) |

**사용 예**:
```python
# 추세 확인
uptrend = dy.is_uptrend()              # 기본 14일 기준 상승 추세 확인
downtrend = dy.is_downtrend(30)        # 30일 기준 하락 추세 확인

# 모멘텀 계산
mom = dy.momentum()                    # 기본 10일 모멘텀
mom_5 = dy.momentum(5)                 # 5일 모멘텀

# 변화율 계산
daily_change = dy.rate_of_change()     # 1일 변화율
weekly_change = dy.rate_of_change(5)   # 5일 변화율
```

### A.8 논리 함수

| 함수 | 설명 | 인수 | 반환값 |
|------|------|------|--------|
| `iif(condition, true_value, false_value)` | 조건부 값 선택 | `condition`: 조건<br>`true_value`: 참일 때 값<br>`false_value`: 거짓일 때 값 | 선택된 값 |
| `all_true(condition_list)` | 모든 조건 참 확인 | `condition_list`: 조건 리스트 | 모든 조건이 참이면 True |
| `any_true(condition_list)` | 하나라도 참 확인 | `condition_list`: 조건 리스트 | 하나라도 참이면 True |

**사용 예**:
```python
# iif 함수 사용
result = dy.iif(dy.c() > dy.ma(dy.c, 20), "상승 추세", "하락 추세")

# all_true 함수 사용
all_conditions_met = dy.all_true([
    dy.c() > dy.ma(dy.c, 20),
    dy.v() > dy.ma(dy.v, 20),
    dy.rsi() < 70
])

# any_true 함수 사용
any_condition_met = dy.any_true([
    dy.c() > dy.h(1),
    dy.v() > dy.ma(dy.v, 20) * 2,
    dy.rsi() < 30
])
```
### A.9 Python 내장 함수

스크립트에서 사용 가능한 Python 내장 함수들입니다.

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `max(iterable)` 또는 `max(a, b, ...)` | 최대값 반환 | `max([10, 5, 20])` - 20 반환<br>`max(c(), o())` - 종가와 시가 중 큰 값 | 최대값 |
| `min(iterable)` 또는 `min(a, b, ...)` | 최소값 반환 | `min([10, 5, 20])` - 5 반환<br>`min(c(), o())` - 종가와 시가 중 작은 값 | 최소값 |
| `sum(iterable)` | 합계 계산 | `sum([1, 2, 3, 4])` - 10 반환 | 합계 |
| `abs(x)` | 절대값 계산 | `abs(-10)` - 10 반환<br>`abs(c() - o())` - 종가와 시가의 차이(절대값) | 절대값 |
| `round(x[, n])` | 반올림 (n자리까지) | `round(3.14159, 2)` - 3.14 반환 | 반올림된 값 |
| `int(x)` | 정수로 변환 | `int(3.7)` - 3 반환 | 정수 |
| `float(x)` | 실수로 변환 | `float(3)` - 3.0 반환 | 실수 |
| `str(x)` | 문자열로 변환 | `str(123)` - "123" 반환 | 문자열 |
| `bool(x)` | 불리언으로 변환 | `bool(0)` - False 반환<br>`bool(1)` - True 반환 | True/False |
| `len(x)` | 객체의 길이 반환 | `len([1, 2, 3])` - 3 반환 | 정수 |
| `list(iterable)` | 리스트로 변환 | `list(range(3))` - [0, 1, 2] 반환 | 리스트 |
| `tuple(iterable)` | 튜플로 변환 | `tuple([1, 2, 3])` - (1, 2, 3) 반환 | 튜플 |
| `sorted(iterable)` | 정렬된 리스트 반환 | `sorted([3, 1, 2])` - [1, 2, 3] 반환 | 리스트 |
| `reversed(sequence)` | 역순 이터레이터 반환 | `list(reversed([1, 2, 3]))` - [3, 2, 1] 반환 | 이터레이터 |
| `enumerate(iterable)` | (인덱스, 값) 쌍 생성 | `list(enumerate(['a', 'b']))` - [(0, 'a'), (1, 'b')] | 이터레이터 |
| `zip(*iterables)` | 여러 이터러블 요소 묶기 | `list(zip([1, 2], ['a', 'b']))` - [(1, 'a'), (2, 'b')] | 이터레이터 |
| `any(iterable)` | 하나라도 참이면 True | `any([False, True, False])` - True 반환 | 불리언 |
| `all(iterable)` | 모두 참이면 True | `all([True, True, False])` - False 반환 | 불리언 |
| `range(start, stop[, step])` | 범위 생성 | `list(range(1, 5))` - [1, 2, 3, 4] 반환 | 이터레이터 |
| `dict(mapping)` | 딕셔너리 생성 | `dict(a=1, b=2)` - {'a': 1, 'b': 2} 반환 | 딕셔너리 |
| `set(iterable)` | 집합 생성 | `set([1, 2, 2, 3])` - {1, 2, 3} 반환 | 집합 |
| `filter(function, iterable)` | 필터링된 이터레이터 | `list(filter(lambda x: x > 0, [-1, 0, 1, 2]))` - [1, 2] | 이터레이터 |
| `map(function, iterable)` | 매핑된 이터레이터 | `list(map(lambda x: x*2, [1, 2, 3]))` - [2, 4, 6] | 이터레이터 |

### A.10 수학 관련 함수 (math 모듈)

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `math.sqrt(x)` | 제곱근 계산 | `math.sqrt(16)` - 4.0 반환 | 실수 |
| `math.pow(x, y)` | x의 y제곱 계산 | `math.pow(2, 3)` - 8.0 반환 | 실수 |
| `math.exp(x)` | e의 x제곱 계산 | `math.exp(1)` - 2.718... 반환 | 실수 |
| `math.log(x[, base])` | 로그 계산 | `math.log(100, 10)` - 2.0 반환 | 실수 |
| `math.log10(x)` | 밑이 10인 로그 | `math.log10(100)` - 2.0 반환 | 실수 |
| `math.floor(x)` | 내림 | `math.floor(3.7)` - 3 반환 | 정수 |
| `math.ceil(x)` | 올림 | `math.ceil(3.2)` - 4 반환 | 정수 |
| `math.sin(x)` | 사인 | `math.sin(math.pi/2)` - 1.0 반환 | 실수 |
| `math.cos(x)` | 코사인 | `math.cos(0)` - 1.0 반환 | 실수 |
| `math.tan(x)` | 탄젠트 | `math.tan(math.pi/4)` - 1.0 반환 | 실수 |
| `math.radians(x)` | 각도를 라디안으로 변환 | `math.radians(180)` - π 반환 | 실수 |
| `math.degrees(x)` | 라디안을 각도로 변환 | `math.degrees(math.pi)` - 180.0 반환 | 실수 |
| `math.fabs(x)` | 절대값 (실수) | `math.fabs(-3.14)` - 3.14 반환 | 실수 |
| `math.factorial(x)` | 팩토리얼 | `math.factorial(5)` - 120 반환 | 정수 |
| `math.gcd(a, b)` | 최대공약수 | `math.gcd(12, 8)` - 4 반환 | 정수 |

### A.11 문자열 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `str.upper()` | 대문자로 변환 | `"hello".upper()` - "HELLO" 반환 | 문자열 |
| `str.lower()` | 소문자로 변환 | `"HELLO".lower()` - "hello" 반환 | 문자열 |
| `str.strip()` | 앞뒤 공백 제거 | `" hello ".strip()` - "hello" 반환 | 문자열 |
| `str.replace(old, new)` | 문자열 치환 | `"hello".replace("l", "x")` - "hexxo" 반환 | 문자열 |
| `str.split(sep)` | 문자열 분할 | `"a,b,c".split(",")` - ["a", "b", "c"] 반환 | 리스트 |
| `str.join(iterable)` | 문자열 결합 | `",".join(["a", "b", "c"])` - "a,b,c" 반환 | 문자열 |
| `str.startswith(prefix)` | 접두사 확인 | `"hello".startswith("he")` - True 반환 | 불리언 |
| `str.endswith(suffix)` | 접미사 확인 | `"hello".endswith("lo")` - True 반환 | 불리언 |
| `str.find(sub)` | 부분문자열 위치 | `"hello".find("l")` - 2 반환 (첫 일치) | 정수 |
| `str.isdigit()` | 숫자 문자열 확인 | `"123".isdigit()` - True 반환 | 불리언 |
| `str.isalpha()` | 알파벳 문자열 확인 | `"abc".isalpha()` - True 반환 | 불리언 |
| `str.format()` | 문자열 포맷팅 | `"{} {}".format("hello", "world")` - "hello world" | 문자열 |

### A.12 리스트 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `list.append(x)` | 항목 추가 | `[1, 2].append(3)` - [1, 2, 3] | None (변경) |
| `list.extend(iterable)` | 리스트 확장 | `[1, 2].extend([3, 4])` - [1, 2, 3, 4] | None (변경) |
| `list.insert(i, x)` | 특정 위치에 삽입 | `[1, 3].insert(1, 2)` - [1, 2, 3] | None (변경) |
| `list.remove(x)` | 항목 제거 | `[1, 2, 3].remove(2)` - [1, 3] | None (변경) |
| `list.pop([i])` | 항목 추출 | `[1, 2, 3].pop(1)` - 2 반환, 리스트는 [1, 3] | 항목 |
| `list.index(x)` | 항목 위치 반환 | `[1, 2, 3].index(2)` - 1 반환 | 정수 |
| `list.count(x)` | 항목 개수 세기 | `[1, 2, 2, 3].count(2)` - 2 반환 | 정수 |
| `list.sort()` | 정렬 | `[3, 1, 2].sort()` - [1, 2, 3] | None (변경) |
| `list.reverse()` | 역순 정렬 | `[1, 2, 3].reverse()` - [3, 2, 1] | None (변경) |
| `list.copy()` | 리스트 복사 | `[1, 2, 3].copy()` - [1, 2, 3] 반환 | 리스트 |

### A.13 딕셔너리 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `dict.get(key[, default])` | 키로 값 가져오기 | `{"a": 1, "b": 2}.get("a")` - 1 반환<br>`{"a": 1}.get("b", 0)` - 0 반환 | 값 |
| `dict.keys()` | 모든 키 반환 | `{"a": 1, "b": 2}.keys()` - dict_keys(['a', 'b']) | dict_keys |
| `dict.values()` | 모든 값 반환 | `{"a": 1, "b": 2}.values()` - dict_values([1, 2]) | dict_values |
| `dict.items()` | (키, 값) 쌍 반환 | `{"a": 1, "b": 2}.items()` - dict_items([('a', 1), ('b', 2)]) | dict_items |
| `dict.update(other)` | 딕셔너리 갱신 | `{"a": 1}.update({"b": 2})` - {"a": 1, "b": 2} | None (변경) |
| `dict.pop(key[, default])` | 키로 값 제거 | `{"a": 1, "b": 2}.pop("a")` - 1 반환, 딕셔너리는 {"b": 2} | 값 |
| `dict.setdefault(key[, default])` | 키가 없으면 추가 | `{"a": 1}.setdefault("b", 2)` - 2 반환, 딕셔너리는 {"a": 1, "b": 2} | 값 |

### A.14 datetime 모듈 함수

| 함수/클래스 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `datetime.now()` | 현재 날짜와 시간 | `datetime.now()` - 현재 날짜시간 | datetime 객체 |
| `datetime.strptime(date_str, format)` | 문자열을 날짜로 변환 | `datetime.strptime("20240101", "%Y%m%d")` | datetime 객체 |
| `datetime.strftime(format)` | 날짜를 문자열로 변환 | `datetime.now().strftime("%Y-%m-%d")` - "2024-01-01" 형식 | 문자열 |
| `timedelta(days=0, seconds=0, ...)` | 시간 간격 | `datetime.now() + timedelta(days=1)` - 내일 날짜 | datetime 객체 |
| `date.year, date.month, date.day` | 날짜 속성 | `datetime.now().year` - 현재 연도 | 정수 |
| `time.hour, time.minute, time.second` | 시간 속성 | `datetime.now().hour` - 현재 시간 | 정수 |


## 부록 B: 스크립트 제약사항 및 주의점

### B.1 금지된 기능

보안 및 시스템 안정성을 위해 다음 기능들은 스크립트에서 사용할 수 없습니다:

1. **파일 시스템 접근**: 파일 읽기/쓰기 작업 (`open()`, `read()`, `write()` 등)
2. **코드 실행 함수**: `exec()`, `eval()`, `__import__()` 등
3. **시스템 모듈**: `os`, `sys`, `subprocess` 등
4. **네트워크 관련 모듈**: `socket`, `requests`, `urllib` 등
5. **무한 루프**: `while` 루프는 사용 불가 (대신 `for` 루프 또는 `loop()` 함수 사용)

다음 패턴들이 감지되면 스크립트가 실행되지 않습니다:
- `import`문을 통한 허용되지 않은 모듈 임포트
- `open()` 함수 호출
- `exec()`, `eval()` 함수 호출
- `__import__()` 함수 호출
- `subprocess` 모듈 사용
- `os`, `sys` 모듈 사용
- `while` 루프 사용

### B.2 허용된 모듈

스크립트 내에서 사용 가능한 모듈들:

1. **re**: 정규 표현식
```python
import re
pattern = re.compile(r'^\d+$')
is_number = pattern.match('12345') is not None
```

2. **math**: 수학 함수
```python
import math
sqrt_value = math.sqrt(price)
log_value = math.log10(price)
```

3. **datetime**: 날짜/시간 처리
```python
from datetime import datetime, timedelta
today = datetime.now()
one_week_ago = today - timedelta(days=7)
```

4. **random**: 난수 생성
```python
import random
random_value = random.random()  # 0.0 ~ 1.0 사이의 난수
coin_flip = random.choice(['앞면', '뒷면'])
```

5. **logging**: 로그 기록
```python
import logging
logging.debug("디버그 메시지")
logging.error("오류 메시지")
```

6. **json**: JSON 처리
```python
import json
json_str = json.dumps({"price": 10000, "qty": 5})
data = json.loads('{"result": true}')
```

7. **collections**: 컬렉션 자료구조
```python
from collections import Counter, defaultdict
word_counts = Counter(['a', 'b', 'a', 'c', 'a'])
grouped_data = defaultdict(list)
```

### B.3 성능 최적화 팁

스크립트 실행 성능을 높이기 위한 추가 팁:

1. **반복 계산 피하기**
```python
# 비효율적
for i in range(100):
    if dy.ma(dy.c, 20) > dy.ma(dy.c, 60):
        # 작업...

# 효율적
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)
for i in range(100):
    if ma20 > ma60:
        # 작업...
```

2. **데이터 미리 로드**
```python
# 비효율적
result = []
for i in range(10):
    result.append(dy.c(i) / dy.ma(dy.c, 20, i))

# 효율적
closes = [dy.c(i) for i in range(10)]
ma20s = [dy.ma(dy.c, 20, i) for i in range(10)]
result = [c / m for c, m in zip(closes, ma20s)]
```

3. **조건부 실행**
```python
# 비효율적
heavy_result = heavy_calculation()
if simple_condition():
    result = heavy_result
else:
    result = default_value

# 효율적
if simple_condition():
    result = heavy_calculation()
else:
    result = default_value
```

4. **내장함수 활용**
```python
# 비효율적
max_value = 0
for i in range(10):
    if dy.c(i) > max_value:
        max_value = dy.c(i)

# 효율적
closes = [dy.c(i) for i in range(10)]
max_value = max(closes)
```

## 부록 C: 샘플 스크립트

### C.1 매수전략

#### 볼린저 밴드 돌파 전략

```python
# 볼린저 밴드 돌파 매수 전략
dy = ChartManager(code, 'dy')

# 볼린저 밴드 계산 (20일, 2시그마)
upper, middle, lower = dy.bollinger_bands(20, 2)

# 가격이 하단 밴드 아래에서 상승 전환
price = dy.c()
prev_price = dy.c(1)

# 매수 조건: 
# 1. 이전 종가가 하단 밴드보다 낮음
# 2. 현재 종가가 하단 밴드보다 높아짐 (상향 돌파)
# 3. 거래량 증가
bottom_breakout = prev_price < lower(1) and price > lower
volume_confirm = dy.v() > dy.ma(dy.v, 20) * 1.2

# 추가 필터: RSI 과매도 확인
rsi = dy.rsi(14)
rsi_oversold = rsi < 40 and rsi > rsi(1)  # RSI가 40 미만에서 반등

# 최종 매수 신호
result = bottom_breakout and volume_confirm and rsi_oversold

# 로깅
if result:
    bb_width = (upper - lower) / middle * 100  # 밴드 폭 (%)
    debug(f"{name}({code}) 볼린저 밴드 하단 돌파 매수 신호")
    debug(f"밴드폭: {bb_width:.1f}%, RSI: {rsi:.1f}")
```

#### 3중 이동평균 매수 전략

```python
# 3중 이동평균 매수 전략
dy = ChartManager(code, 'dy')

# 이동평균 계산
ma5 = dy.ma(dy.c, 5)
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)

# 전일 이동평균
ma5_prev = ma5(1)
ma20_prev = ma20(1)
ma60_prev = ma60(1)

# 이동평균 정렬 확인 (단기 > 중기 > 장기)
aligned_now = ma5 > ma20 > ma60
aligned_prev = ma5_prev > ma20_prev > ma60_prev

# 상승 스윙 확인 (5일선이 상승으로 전환)
ma5_rising = ma5 > ma5_prev

# 이동평균이 새롭게 정렬되는 시점 확인
new_alignment = aligned_now and not aligned_prev

# 거래량 확인
volume_confirm = dy.v() > dy.ma(dy.v, 20)

# 최종 매수 신호
result = (new_alignment or (aligned_now and ma5_rising)) and volume_confirm

# 로깅
if result:
    debug(f"{name}({code}) 3중 이동평균 매수 신호")
    if new_alignment:
        debug("이유: 이동평균 새롭게 정렬")
    else:
        debug("이유: 이동평균 정렬 유지 및 단기선 상승")
```
### C.2 매도 전략

#### 이중 고점 매도 전략

```python
# 이중 고점 매도 전략
dy = ChartManager(code, 'dy')

# RSI 계산
rsi = dy.rsi(14)
rsi_prev = dy.rsi(14, 1)
rsi_prev2 = dy.rsi(14, 2)

# 이중 고점 확인 (두 번째 고점이 첫 번째보다 낮은 패턴)
first_peak = rsi_prev > rsi_prev2 and rsi_prev > rsi
second_peak = rsi > rsi(1) and rsi < rsi_prev
double_top = first_peak and rsi_prev > 70 and rsi > 65

# 볼린저 밴드 계산
upper, middle, lower = dy.bollinger_bands(20, 2)

# 볼린저 밴드 상단 접근
near_upper = dy.c() > upper * 0.985

# 추세 전환 확인
ma5 = dy.ma(dy.c, 5)
ma20 = dy.ma(dy.c, 20)
trend_weakening = ma5(1) > ma5  # 5일선이 하락으로 전환

# 최종 매도 신호
result = double_top and near_upper and trend_weakening

# 로깅
if result:
    debug(f"{name}({code}) 이중 고점 매도 신호")
    debug(f"RSI: {rsi:.1f}, 이전 RSI: {rsi_prev:.1f}")
    debug(f"상단 밴드와의 거리: {(upper - dy.c()) / dy.c() * 100:.2f}%")
```

#### 손절매 전략

```python
# 손절매 전략
dy = ChartManager(code, 'dy')

# 주요 지지선 계산 (최근 20일 중 최저가의 95%)
key_support = dy.lowest(dy.l, 20) * 0.95

# 평균 매수 단가
avg_buy_price = price  # 예약 변수 (매수 평균가)

# 손절 기준
stop_loss_pct = 5.0  # 5% 손절매
stop_loss_price = avg_buy_price * (1 - stop_loss_pct / 100)

# 손절 조건
below_support = dy.c() < key_support
max_loss_reached = dy.c() < stop_loss_price

# MA 하락추세 확인
ma20 = dy.ma(dy.c, 20)
ma60 = dy.ma(dy.c, 60)
downtrend = ma20 < ma60 and dy.c() < ma20

# 손절 조건 (지지선 붕괴 또는 최대 손실 도달)
result = (below_support and downtrend) or max_loss_reached

# 로깅
if result:
    current_loss = (dy.c() - avg_buy_price) / avg_buy_price * 100
    debug(f"{name}({code}) 손절매 신호")
    
    if below_support:
        debug(f"이유: 주요 지지선({key_support:.0f}) 붕괴")
    
    if max_loss_reached:
        debug(f"이유: 최대 손실 허용치 도달 (손실률: {current_loss:.1f}%)")
```

### C.3 알려진 유용한 전략들

#### 스윙 트레이딩 전략: 3일 고/저점 돌파

```python
# 3일 고/저점 돌파 스윙 전략
dy = ChartManager(code, 'dy')

# 전략 설정
lookback = 3  # 확인 기간 (일)
breakout_pct = 1.0  # 돌파 기준 (%)

# 최근 N일 고점/저점 계산
n_day_high = dy.highest(dy.h, lookback, 1)  # 1일전부터 lookback일간 고점
n_day_low = dy.lowest(dy.l, lookback, 1)    # 1일전부터 lookback일간 저점

# 브레이크아웃 계산
up_breakout = dy.c() > n_day_high * (1 + breakout_pct/100)  # 상향 돌파
down_breakout = dy.c() < n_day_low * (1 - breakout_pct/100)  # 하향 돌파

# 거래량 확인
volume_confirm = dy.v() > dy.ma(dy.v, 20) * 1.3

# 추가 필터: ATR 기준 변동성 확인
atr = dy.atr(14)
price_volatility = atr / dy.c() * 100  # 가격 대비 ATR (%)
volatility_ok = price_volatility > 1.5  # 변동성이 충분히 높은지 확인

# 매매 신호
if up_breakout and volume_confirm and volatility_ok:
    result = "BUY"
    debug(f"{name}({code}) 상향 돌파 매수 신호 (3일 고점: {n_day_high})")
elif down_breakout and volume_confirm and volatility_ok:
    result = "SELL"
    debug(f"{name}({code}) 하향 돌파 매도 신호 (3일 저점: {n_day_low})")
else:
    result = "NONE"
```

#### 변동성 돌파 전략

```python
# 변동성 돌파 전략 (일명 "낙수 전략")
dy = ChartManager(code, 'dy')

# 전략 설정
k = 0.5  # 변동폭 계수 (0.5 = 50%)

# 당일 시가
today_open = dy.o()

# 전일 변동폭
yesterday_high = dy.h(1)
yesterday_low = dy.l(1)
yesterday_range = yesterday_high - yesterday_low

# 돌파 기준가 계산
target_price = today_open + yesterday_range * k

# 현재가가 목표가 돌파 여부 확인
breakout = dy.c() > target_price

# 추가 필터: 이동평균 확인
ma20 = dy.ma(dy.c, 20)
above_ma = dy.c() > ma20

# 매수 조건
result = breakout and above_ma

# 로깅
if result:
    debug(f"{name}({code}) 변동성 돌파 매수 신호")
    debug(f"목표가: {target_price:.0f}, 현재가: {dy.c():.0f}")
    debug(f"돌파율: {(dy.c() - target_price) / yesterday_range * 100:.1f}%")
```

## 부록 D: 스크립트 작성 예 (메인 + 서브)

다양한 기법을 보여 주기 위한 스크립트 예제이며 실제 구현 시 기능별로 더 잘게 분리하는 것이 좋음

### D.1 메인스크립트 : 통합 트레이딩 시스템
```
# 통합 트레이딩 시스템
# 여러 서브스크립트를 조합하여 종합적인 매매 판단 제공
# 다양한 파이썬 기법과 차트매니저 기능 활용

# 필요한 내장 모듈 임포트
import re
import math
import collections
from datetime import datetime, timedelta
import random

# 환경설정 (사용자 정의 변수)
strategy_type = kwargs.get('strategy', 'trend_following')  # 전략 유형
risk_level = kwargs.get('risk', 'medium')                  # 위험 수준 (low/medium/high)
use_indicators = kwargs.get('indicators', ['rsi', 'macd', 'ma'])  # 사용할 지표

# 위험 수준에 따른 매개변수 설정
if risk_level == 'low':
    stop_loss = 3.0      # 손절 비율 (%)
    take_profit = 6.0    # 익절 비율 (%)
    position_size = 0.1  # 자본금 대비 포지션 크기
elif risk_level == 'high':
    stop_loss = 7.0
    take_profit = 21.0
    position_size = 0.3
else:  # medium (기본값)
    stop_loss = 5.0
    take_profit = 15.0
    position_size = 0.2

# 오늘 날짜/시간 정보
now = datetime.now()
today_str = now.strftime('%Y-%m-%d')
weekday = now.weekday()  # 0: 월요일, ..., 4: 금요일

# 주간 거래 일수 제한 설정 (예: 월, 수, 금만 거래)
trading_days = [0, 2, 4]  # 월, 수, 금
is_trading_day = weekday in trading_days

# 거래 가능 시간대 설정 (예: 오전 10시 ~ 오후 2시)
trading_hours = (10, 14)
current_hour = now.hour
is_trading_hour = trading_hours[0] <= current_hour < trading_hours[1]

# 차트 매니저 인스턴스 생성
dy = ChartManager(code, 'dy')  # 일봉
mi60 = ChartManager(code, 'mi', 60)  # 60분봉

# -------------------------------------------------------------
# 1. 기술적 지표 분석 (서브스크립트 활용)
# -------------------------------------------------------------

# RSI 분석 (tech_indicator 서브스크립트 호출)
rsi_data = tech_indicator(indicator='rsi', period1=14)
rsi_value = rsi_data() if callable(rsi_data) else dy.rsi(14)

# MACD 분석 (tech_indicator 서브스크립트 호출)
macd_data = tech_indicator(indicator='macd', period1=12, period2=26, period3=9)
if callable(macd_data):
    macd_line, signal_line, histogram = macd_data()
else:
    macd_line, signal_line, histogram = dy.macd(12, 26, 9)

# 볼린저 밴드 분석 (tech_indicator 서브스크립트 호출)
bb_data = tech_indicator(indicator='bb', period1=20, multiplier=2)
if callable(bb_data):
    upper, middle, lower = bb_data()
else:
    upper, middle, lower = dy.bollinger_bands(20, 2)

# 가격 위치 계산
price = dy.c()
bb_position = (price - lower) / (upper - lower) * 100  # 밴드 내 위치 (0-100%)

# -------------------------------------------------------------
# 2. 멀티 타임프레임 분석 (서브스크립트 활용)
# -------------------------------------------------------------

# 추세 분석 (multi_timeframe_analyzer 서브스크립트 호출)
trend_data = multi_timeframe_analyzer(analysis='trend')
trend_score = trend_data.get('score', 0) if isinstance(trend_data, dict) else 0
trend_strength = trend_data.get('strength', 'unknown') if isinstance(trend_data, dict) else 'unknown'

# 골든크로스/데드크로스 확인 (multi_timeframe_analyzer 서브스크립트 호출)
cross_data = multi_timeframe_analyzer(analysis='cross', cross='golden')
has_cross = cross_data.get('daily', False) if isinstance(cross_data, dict) else False

# -------------------------------------------------------------
# 3. 패턴 인식 (서브스크립트 활용)
# -------------------------------------------------------------

# 모든 패턴 분석 (pattern_recognizer 서브스크립트 호출)
patterns = pattern_recognizer(pattern='all', lookback=20)
pattern_signal = patterns.get('signal', 'NEUTRAL') if isinstance(patterns, dict) else 'NEUTRAL'

# -------------------------------------------------------------
# 4. 고급 파이썬 기법 시연
# -------------------------------------------------------------

# 리스트 컴프리헨션으로 최근 N일 종가 가져오기
recent_closes = [dy.c(i) for i in range(10)]

# 람다 함수로 상승/하락일 계산
is_up_day = lambda i: dy.c(i) > dy.o(i)
up_days = sum(1 for i in range(5) if is_up_day(i))
debug(f"최근 5일 중 {up_days}일 상승")

# Collections 모듈 활용 - Counter
price_movements = [dy.c(i) > dy.c(i+1) for i in range(10)]
movement_count = collections.Counter(price_movements)
debug(f"최근 10일 움직임: 상승 {movement_count[True]}일, 하락 {movement_count[False]}일")

# 데이터 처리 - 이동평균의 기울기 계산
def calculate_slope(values):
    if len(values) < 2:
        return 0
    
    # 선형 회귀 기울기 간소화 계산
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    
    numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    return numerator / denominator if denominator != 0 else 0

# 20일 이동평균선의 최근 5일 기울기 계산
ma20_values = [dy.ma(dy.c, 20, i) for i in range(5)]
ma20_slope = calculate_slope(ma20_values)
debug(f"20일 이동평균선 기울기: {ma20_slope:.4f}")

# 예외 처리 활용 - 안전한 계산
try:
    # 위험한 연산 (0으로 나누기 가능성)
    price_ratio = price / dy.o() if dy.o() != 0 else 1.0
except Exception as e:
    debug(f"계산 오류 발생: {e}")
    price_ratio = 1.0

# 딕셔너리 컴프리헨션으로 다양한 이동평균 계산
ma_periods = [5, 10, 20, 60, 120]
ma_values = {f"MA{period}": dy.ma(dy.c, period) for period in ma_periods}

# -------------------------------------------------------------
# 5. 매매 신호 및 전략별 로직 구현
# -------------------------------------------------------------
# 매매 신호 초기화
trade_signal = 'NEUTRAL'
trade_reason = []
risk_reward_ratio = take_profit / stop_loss

# 전략별 매매 신호 계산
if strategy_type == 'trend_following':
    # 추세 추종 전략
    
    # 1. 추세 확인
    trend_condition = trend_score >= 60  # 60점 이상이면 상승 추세로 판단
    
    # 2. 진입 조건
    # - RSI가 30-70 사이 (과열/과매도 아님)
    # - 가격이 20일선 위
    # - MACD 히스토그램 양수
    entry_conditions = [
        30 <= rsi_value <= 70,
        price > dy.ma(dy.c, 20),
        histogram > 0
    ]
    
    # 3. 필터 조건
    # - 거래량 증가
    # - 밴드 내 위치 적절
    filter_conditions = [
        dy.v() > dy.ma(dy.v, 20),
        30 <= bb_position <= 70
    ]
    
    # 매수 조건: 추세 + 진입 조건 + 필터 (대부분 충족)
    if trend_condition and sum(entry_conditions) >= 2 and sum(filter_conditions) >= 1:
        trade_signal = 'BUY'
        trade_reason = [
            f"상승 추세 점수: {trend_score}/100",
            f"RSI: {rsi_value:.1f}",
            f"MACD 히스토그램: {histogram:.2f}",
            f"가격이 20일 이동평균 {(price / dy.ma(dy.c, 20) - 1) * 100:.1f}% 위에 위치"
        ]
    
elif strategy_type == 'mean_reversion':
    # 평균 회귀 전략
    
    # 1. 과매수/과매도 확인
    oversold = rsi_value < 30
    overbought = rsi_value > 70
    
    # 2. 볼린저 밴드 위치 확인
    near_lower = bb_position < 20
    near_upper = bb_position > 80
    
    # 3. 추가 확인
    # - 캔들 패턴
    # - MACD 반전 징후
    candle_reversal = patterns.get('patterns', {}).get('candle', {}).get('hammer', False) or \
                     patterns.get('patterns', {}).get('candle', {}).get('bullish_engulfing', False)
    
    macd_reversal = histogram > histogram(1) if callable(histogram) else False
    
    # 매수 조건 (과매도 상태에서 반등 징후)
    if oversold and near_lower and (candle_reversal or macd_reversal):
        trade_signal = 'BUY'
        trade_reason = [
            f"RSI 과매도: {rsi_value:.1f}",
            f"볼린저 밴드 하단 접근: {bb_position:.1f}%",
            "캔들 반전 패턴 감지" if candle_reversal else "",
            "MACD 반등 징후" if macd_reversal else ""
        ]
        trade_reason = [r for r in trade_reason if r]  # 빈 문자열 제거
    
    # 매도 조건 (과매수 상태에서 하락 징후)
    elif overbought and near_upper and not trend_condition:
        trade_signal = 'SELL'
        trade_reason = [
            f"RSI 과매수: {rsi_value:.1f}",
            f"볼린저 밴드 상단 접근: {bb_position:.1f}%",
            "추세 점수 낮음" if trend_score < 40 else ""
        ]
        trade_reason = [r for r in trade_reason if r]

elif strategy_type == 'breakout':
    # 돌파 전략
    
    # 1. 저항/지지선 확인
    resistance_breakout = patterns.get('patterns', {}).get('breakout', {}).get('resistance', False)
    
    # 2. 볼륨 확인
    volume_surge = dy.v() > dy.ma(dy.v, 20) * 1.5
    
    # 3. 이동평균 정렬 확인
    ma_alignment = dy.ma(dy.c, 5) > dy.ma(dy.c, 10) > dy.ma(dy.c, 20)
    
    # 매수 조건 (저항선 돌파 + 거래량 급증)
    if resistance_breakout and volume_surge and ma_alignment:
        trade_signal = 'BUY'
        recent_high = patterns.get('patterns', {}).get('breakout', {}).get('high', price)
        trade_reason = [
            f"저항선 돌파: {recent_high:.2f}",
            f"거래량 급증: 평균 대비 {dy.v() / dy.ma(dy.v, 20):.1f}배",
            "이동평균 상승 정렬"
        ]

else:  # 패턴 기반 전략 (기본값)
    # 패턴 감지 결과 사용
    trade_signal = pattern_signal
    
    if pattern_signal == 'BUY':
        trade_reason = ["패턴 인식기 매수 신호"]
    elif pattern_signal == 'SELL':
        trade_reason = ["패턴 인식기 매도 신호"]

# -------------------------------------------------------------
# 6. 거래 필터 및 위험 관리
# -------------------------------------------------------------

# 거래일 필터 적용
if not is_trading_day:
    debug("오늘은 거래일이 아닙니다. 신호 무시.")
    trade_signal = 'NEUTRAL'

# 거래 시간 필터 적용
if not is_trading_hour:
    debug(f"현재 시간은 거래 시간대가 아닙니다 ({current_hour}시). 신호 무시.")
    trade_signal = 'NEUTRAL'

# 위험 수준에 따른 추가 필터
if risk_level == 'low' and trade_signal == 'BUY':
    # 저위험 전략에서는 추가 확인
    if trend_score < 70 or rsi_value > 65:
        debug("저위험 전략: 추세 점수가 낮거나 RSI가 높아 매수 신호 취소")
        trade_signal = 'NEUTRAL'

# 포지션 계산 (매수 시)
if trade_signal == 'BUY':
    # 총자산 대비 포지션 크기 계산
    total_capital = kwargs.get('capital', 10000000)  # 기본값 1000만원
    
    # ATR 기반 위험 관리
    atr_value = dy.atr(14)
    
    # 손절 가격 (ATR의 2배 아래 또는 고정 비율 중 작은 값)
    atr_stop_price = price - (atr_value * 2)
    fixed_stop_price = price * (1 - stop_loss/100)
    stop_price = max(atr_stop_price, fixed_stop_price)
    
    # 목표가 (R:R 비율에 따라 설정)
    target_price = price * (1 + take_profit/100)
    
    # 예상 손실 금액 기준으로 수량 계산
    max_loss_amount = total_capital * position_size * (risk_level == 'high' ? 0.02 : 0.01)  # 1~2%만 위험노출
    price_gap = price - stop_price
    
    # 비율 기준 수량 = 최대 손실액 ÷ 가격 갭
    quantity = math.floor(max_loss_amount / price_gap) if price_gap > 0 else 0
    
    # 추가 정보 저장
    trade_info = {
        'entry_price': price,
        'stop_price': stop_price,
        'target_price': target_price,
        'quantity': quantity,
        'expected_profit': (target_price - price) * quantity,
        'expected_loss': (price - stop_price) * quantity
    }
    
    debug(f"매수 정보: 진입가 {price:.2f}, 손절가 {stop_price:.2f}, 목표가 {target_price:.2f}")
    debug(f"수량: {quantity}주, 예상 수익: {trade_info['expected_profit']:.0f}원, 예상 손실: {trade_info['expected_loss']:.0f}원")

# -------------------------------------------------------------
# 7. 최종 매매 결정 및 로깅
# -------------------------------------------------------------

# 최종 매매 신호 및 정보 로깅
if trade_signal == 'BUY':
    info(f"*** 매수 신호 감지 ({today_str}) ***")
    for reason in trade_reason:
        info(f"- {reason}")
    
    # 매수 주문 예시 (실제 주문은 아님)
    info(f"매수 예정: {name}({code}) {quantity}주 @ {price:.2f}원")
    info(f"손절가: {stop_price:.2f}원 (-{stop_loss:.1f}%), 목표가: {target_price:.2f}원 (+{take_profit:.1f}%)")
    info(f"수익률 = 1:{risk_reward_ratio:.1f}")
    
elif trade_signal == 'SELL':
    info(f"*** 매도 신호 감지 ({today_str}) ***")
    for reason in trade_reason:
        info(f"- {reason}")
    
    # 현재 보유량 확인
    current_position = qty  # 예약 변수
    
    if current_position > 0:
        info(f"매도 예정: {name}({code}) {current_position}주 @ {price:.2f}원")
    else:
        info("보유 수량이 없어 매도 실행 불가")
        
else:  # NEUTRAL
    debug(f"매매 신호 없음 ({today_str})")
    debug(f"RSI: {rsi_value:.1f}, 추세 점수: {trend_score}, 밴드 위치: {bb_position:.1f}%")

# -------------------------------------------------------------
# 8. 최종 결과 값 반환
# -------------------------------------------------------------

# 거래 신호 및 관련 정보 반환
result = {
    'signal': trade_signal,
    'strategy': strategy_type,
    'risk_level': risk_level,
    'date': today_str,
    'price': price,
    'indicators': {
        'rsi': rsi_value,
        'macd': {
            'line': macd_line,
            'signal': signal_line,
            'histogram': histogram
        },
        'bollinger': {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'position': bb_position
        }
    },
    'trend': {
        'score': trend_score,
        'strength': trend_strength
    },
    'patterns': patterns.get('patterns', {}),
    'reasons': trade_reason
}

# 매수 신호인 경우 거래 정보 추가
if trade_signal == 'BUY' and 'trade_info' in locals():
    result['trade'] = trade_info

# 디버그 요약 출력
debug(f"신호: {trade_signal}, 전략: {strategy_type}, 위험수준: {risk_level}")
debug(f"종합 분석 완료: {today_str}, {name}({code})")
```
### D.2 서브스크립트1 : 기술적 지표 계산기 (tech_indicator)
```
# 기술적 지표 계산기
# 다양한 기술적 지표를 계산하여 반환하는 스크립트
# 단독 사용 시 RSI 계산 결과 반환

# 파라미터 설정 (매개변수로 받을 경우 사용)
indicator_type = kwargs.get('indicator', 'rsi')  # 기본값은 RSI
period1 = kwargs.get('period1', 14)              # 첫 번째 기간
period2 = kwargs.get('period2', 9)               # 두 번째 기간
period3 = kwargs.get('period3', 5)               # 세 번째 기간
multiplier = kwargs.get('multiplier', 2)         # 승수(볼린저밴드용)

# 차트 매니저 인스턴스 생성
dy = ChartManager(code, 'dy')  # 일봉 차트
h4 = ChartManager(code, 'mi', 240)  # 4시간봉 차트

# 람다 함수를 활용한 지표 생성 (함수처럼 사용 가능)
def create_indicator(func, *args):
    return lambda offset=0: func(*args, offset)

# 다양한 지표 계산
if indicator_type == 'rsi':
    # RSI 계산
    result = create_indicator(dy.rsi, period1)
    
    # 결과 로깅
    debug(f"RSI({period1}): 현재={result():.2f}, 1일전={result(1):.2f}, 2일전={result(2):.2f}")
    
elif indicator_type == 'macd':
    # MACD 계산
    result = create_indicator(dy.macd, period1, period2, period3)
    
    # 결과 값 추출
    macd_now, signal_now, hist_now = result()
    macd_prev, signal_prev, hist_prev = result(1)
    
    # 로깅
    debug(f"MACD({period1},{period2},{period3}): {macd_now:.2f}, Signal: {signal_now:.2f}, Hist: {hist_now:.2f}")
    debug(f"히스토그램 변화: {hist_now - hist_prev:.2f}")
    
elif indicator_type == 'bb':
    # 볼린저 밴드 계산
    result = create_indicator(dy.bollinger_bands, period1, multiplier)
    
    # 현재 밴드 값
    upper, middle, lower = result()
    
    # 밴드 폭 계산
    band_width = (upper - lower) / middle * 100
    
    # 로깅
    debug(f"볼린저 밴드({period1},{multiplier}): 상단={upper:.2f}, 중간={middle:.2f}, 하단={lower:.2f}")
    debug(f"밴드 폭: {band_width:.2f}%")
    
elif indicator_type == 'stoch':
    # 스토캐스틱 계산
    result = create_indicator(dy.stochastic, period1, period2)
    
    # 현재/이전 값
    k_now, d_now = result()
    k_prev, d_prev = result(1)
    
    # 로깅
    debug(f"스토캐스틱({period1},{period2}): %K={k_now:.2f}, %D={d_now:.2f}")
    debug(f"%K 변화: {k_now - k_prev:.2f}, %D 변화: {d_now - d_prev:.2f}")
    
elif indicator_type == 'atr':
    # ATR 계산
    result = create_indicator(dy.atr, period1)
    
    # ATR 값
    atr_value = result()
    
    # 상대 ATR (가격 대비 비율)
    relative_atr = atr_value / dy.c() * 100
    
    # 로깅
    debug(f"ATR({period1}): {atr_value:.2f} ({relative_atr:.2f}%)")
    
else:
    # 지원하지 않는 지표
    debug(f"지원하지 않는 지표 타입: {indicator_type}")
    result = None

# 기본 반환은 RSI 지표
if result is None:
    result = create_indicator(dy.rsi, 14)
```
### D.3 서브스크립트2 : 멀티 타임 프레임 분석기 (multi_timeframe_analyzer)
```
# 멀티 타임프레임 분석기
# 여러 시간대의 차트를 분석하여 통합된 결과 제공
# 단독 사용 시 여러 시간대 추세 정보 반환

# 분석 대상 종목 및 설정
analysis_type = kwargs.get('analysis', 'trend')  # 기본은 추세 분석
cross_type = kwargs.get('cross', 'golden')       # 교차 타입 (golden/death)

# 여러 시간대 차트 준비
mi15 = ChartManager(code, 'mi', 15)   # 15분봉
mi60 = ChartManager(code, 'mi', 60)   # 60분봉
dy = ChartManager(code, 'dy')         # 일봉
wk = ChartManager(code, 'wk')         # 주봉

# 기간 설정
short_period = 5
mid_period = 20
long_period = 60

# 이동평균 계산 함수 (Lambda 활용)
def calculate_ma(cm, period, offset=0):
    return cm.ma(cm.c, period, offset)

# 각 시간대별 이동평균 계산
if analysis_type == 'trend':
    # 모든 시간대의 추세 정보 수집
    trends = {
        '15min': {
            'ma5': calculate_ma(mi15, short_period),
            'ma20': calculate_ma(mi15, mid_period),
            'bullish': mi15.c() > calculate_ma(mi15, mid_period),
            'rising': calculate_ma(mi15, short_period) > calculate_ma(mi15, short_period, 1)
        },
        '60min': {
            'ma5': calculate_ma(mi60, short_period),
            'ma20': calculate_ma(mi60, mid_period),
            'bullish': mi60.c() > calculate_ma(mi60, mid_period),
            'rising': calculate_ma(mi60, short_period) > calculate_ma(mi60, short_period, 1)
        },
        'daily': {
            'ma5': calculate_ma(dy, short_period),
            'ma20': calculate_ma(dy, mid_period),
            'ma60': calculate_ma(dy, long_period),
            'bullish': dy.c() > calculate_ma(dy, mid_period),
            'rising': calculate_ma(dy, short_period) > calculate_ma(dy, short_period, 1)
        },
        'weekly': {
            'ma5': calculate_ma(wk, short_period),
            'ma20': calculate_ma(wk, mid_period),
            'bullish': wk.c() > calculate_ma(wk, mid_period),
            'rising': calculate_ma(wk, short_period) > calculate_ma(wk, short_period, 1)
        }
    }
    
    # 종합 추세 점수 계산 (0-100)
    trend_score = 0
    
    # 각 시간대별 가중치 적용
    if trends['15min']['bullish']: trend_score += 5
    if trends['15min']['rising']: trend_score += 5
    
    if trends['60min']['bullish']: trend_score += 10
    if trends['60min']['rising']: trend_score += 10
    
    if trends['daily']['bullish']: trend_score += 20
    if trends['daily']['rising']: trend_score += 20
    if dy.c() > trends['daily']['ma60']: trend_score += 10
    
    if trends['weekly']['bullish']: trend_score += 10
    if trends['weekly']['rising']: trend_score += 10
    
    # 결과 로깅
    debug(f"멀티 타임프레임 추세 분석 결과:")
    debug(f"15분봉: {'상승' if trends['15min']['bullish'] else '하락'} 추세")
    debug(f"60분봉: {'상승' if trends['60min']['bullish'] else '하락'} 추세")
    debug(f"일봉: {'상승' if trends['daily']['bullish'] else '하락'} 추세")
    debug(f"주봉: {'상승' if trends['weekly']['bullish'] else '하락'} 추세")
    debug(f"종합 추세 점수: {trend_score}/100")
    
    # 추세 강도 등급 부여
    if trend_score >= 80:
        trend_strength = "매우 강한 상승세"
    elif trend_score >= 60:
        trend_strength = "상승세"
    elif trend_score >= 40:
        trend_strength = "중립"
    elif trend_score >= 20:
        trend_strength = "하락세"
    else:
        trend_strength = "매우 강한 하락세"
    
    debug(f"추세 강도: {trend_strength}")
    
    # 추세 정보 반환
    result = {
        'trends': trends,
        'score': trend_score,
        'strength': trend_strength
    }
    
elif analysis_type == 'cross':
    # 여러 시간대의 골든크로스/데드크로스 확인
    crosses = {}
    
    # 교차 확인 함수
    def check_cross(cm, type='golden'):
        short_ma = calculate_ma(cm, short_period)
        mid_ma = calculate_ma(cm, mid_period)
        
        short_ma_prev = calculate_ma(cm, short_period, 1)
        mid_ma_prev = calculate_ma(cm, mid_period, 1)
        
        if type == 'golden':
            # 골든크로스 (단기>장기, 전날은 단기<장기)
            return short_ma > mid_ma and short_ma_prev <= mid_ma_prev
        else:
            # 데드크로스 (단기<장기, 전날은 단기>=장기)
            return short_ma < mid_ma and short_ma_prev >= mid_ma_prev
    
    # 각 시간대별 교차 확인
    crosses['15min'] = check_cross(mi15, cross_type)
    crosses['60min'] = check_cross(mi60, cross_type)
    crosses['daily'] = check_cross(dy, cross_type)
    crosses['weekly'] = check_cross(wk, cross_type)
    
    # 결과 로깅
    cross_name = "골든크로스" if cross_type == 'golden' else "데드크로스"
    debug(f"멀티 타임프레임 {cross_name} 분석:")
    
    for timeframe, has_cross in crosses.items():
        status = "발생" if has_cross else "없음"
        debug(f"{timeframe}: {status}")
    
    # 교차 정보 반환
    result = crosses

else:
    debug(f"지원하지 않는 분석 유형: {analysis_type}")
    result = None

# 기본 반환값
if result is None:
    # 일봉 추세 정보만 반환
    result = {
        'bullish': dy.c() > calculate_ma(dy, mid_period),
        'ma5': calculate_ma(dy, short_period),
        'ma20': calculate_ma(dy, mid_period)
    }
``` 
### D.4 서브스크립트3 : 고급 패턴 인식기 (pattern_recognizer)
```
# 고급 패턴 인식기
# 다양한 차트 패턴을 인식하여 매매 신호 생성
# 단독 사용 시 인식된 패턴 정보 반환

# 패턴 타입 설정
pattern_type = kwargs.get('pattern', 'all')  # 기본값은 모든 패턴 확인
lookback = kwargs.get('lookback', 20)        # 확인할 최대 기간

# 차트 매니저 인스턴스
dy = ChartManager(code, 'dy')  # 일봉 차트

# 패턴 인식 결과 저장소
patterns_found = {}

# 1. 캔들 패턴 확인
if pattern_type in ['all', 'candle']:
    # 도지 확인
    is_doji = dy.is_doji()
    is_prev_doji = dy.is_doji(1)
    
    # 망치형 확인
    is_hammer = dy.is_hammer()
    
    # 포괄형 확인
    is_bullish_engulfing = dy.is_engulfing(bullish=True)
    is_bearish_engulfing = dy.is_engulfing(bullish=False)
    
    # 캔들 패턴 저장
    patterns_found['candle'] = {
        'doji': is_doji,
        'hammer': is_hammer,
        'bullish_engulfing': is_bullish_engulfing,
        'bearish_engulfing': is_bearish_engulfing
    }
    
    # 캔들 패턴 로깅
    if is_doji:
        debug("도지 패턴 발견: 시장 방향성 불확실")
    if is_hammer:
        debug("망치형 패턴 발견: 잠재적 반등 신호")
    if is_bullish_engulfing:
        debug("상승 포괄형 패턴 발견: 강한 상승 반전 신호")
    if is_bearish_engulfing:
        debug("하락 포괄형 패턴 발견: 강한 하락 반전 신호")

# 2. 지지/저항 돌파 확인
if pattern_type in ['all', 'breakout']:
    # 최근 N일 고점/저점 계산
    recent_high = dy.highest(dy.h, lookback, 1)  # 최근 고점 (전날까지)
    recent_low = dy.lowest(dy.l, lookback, 1)    # 최근 저점 (전날까지)
    
    # 고점/저점 대비 현재가 계산
    curr_price = dy.c()
    high_ratio = (curr_price - recent_high) / recent_high * 100
    low_ratio = (curr_price - recent_low) / recent_low * 100
    
    # 돌파 판단 (고점 0.5% 이상, 저점 0.5% 이상)
    resistance_breakout = high_ratio > 0.5
    support_breakout = low_ratio < -0.5
    
    # 볼륨 확인
    vol_increase = dy.v() > dy.ma(dy.v, 20) * 1.5
    
    # 지지/저항 패턴 저장
    patterns_found['breakout'] = {
        'resistance': resistance_breakout and vol_increase,
        'support': support_breakout and vol_increase,
        'high': recent_high,
        'low': recent_low
    }
    
    # 돌파 로깅
    if resistance_breakout and vol_increase:
        debug(f"저항선({recent_high:.2f}) 상향 돌파: {high_ratio:.2f}% 상승")
    if support_breakout and vol_increase:
        debug(f"지지선({recent_low:.2f}) 하향 돌파: {low_ratio:.2f}% 하락")

# 3. 다이버전스 패턴 확인
if pattern_type in ['all', 'divergence']:
    # RSI 계산
    rsi_now = dy.rsi(14, 0)
    rsi_prev = dy.rsi(14, 1)
    rsi_prev2 = dy.rsi(14, 2)
    
    # 가격 정보
    price_now = dy.c()
    price_prev = dy.c(1)
    price_prev2 = dy.c(2)
    
    # 다이버전스 확인
    # 1. 상승 다이버전스 (가격 하향, RSI 상향) - 매수 신호
    bullish_div = (price_now < price_prev2) and (rsi_now > rsi_prev2)
    
    # 2. 하락 다이버전스 (가격 상향, RSI 하향) - 매도 신호
    bearish_div = (price_now > price_prev2) and (rsi_now < rsi_prev2)
    
    # 다이버전스 패턴 저장
    patterns_found['divergence'] = {
        'bullish': bullish_div,
        'bearish': bearish_div,
        'rsi': rsi_now
    }
    
    # 다이버전스 로깅
    if bullish_div:
        debug("상승 다이버전스 감지: 가격은 하락 중이나 RSI는 상승 (매수 신호)")
    if bearish_div:
        debug("하락 다이버전스 감지: 가격은 상승 중이나 RSI는 하락 (매도 신호)")

# 4. 이동평균 기반 패턴
if pattern_type in ['all', 'ma']:
    # 이동평균 계산
    ma5 = dy.ma(dy.c, 5)
    ma10 = dy.ma(dy.c, 10)
    ma20 = dy.ma(dy.c, 20)
    ma60 = dy.ma(dy.c, 60)
    
    # 이전 이동평균
    ma5_prev = dy.ma(dy.c, 5, 1)
    ma20_prev = dy.ma(dy.c, 20, 1)
    
    # 골든크로스/데드크로스 확인
    golden_cross = ma5 > ma20 and ma5_prev <= ma20_prev
    death_cross = ma5 < ma20 and ma5_prev >= ma20_prev
    
    # 이동평균 정렬 확인
    bullish_align = ma5 > ma10 > ma20 > ma60  # 완벽한 상승 정렬
    bearish_align = ma5 < ma10 < ma20 < ma60  # 완벽한 하락 정렬
    
    # MA 패턴 저장
    patterns_found['ma'] = {
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'bullish_align': bullish_align,
        'bearish_align': bearish_align
    }
    
    # MA 패턴 로깅
    if golden_cross:
        debug("골든크로스 발생: 5일선이 20일선을 상향 돌파 (매수 신호)")
    if death_cross:
        debug("데드크로스 발생: 5일선이 20일선을 하향 돌파 (매도 신호)")
    if bullish_align:
        debug("완벽한 상승 정렬: 단기>중기>장기 이동평균 (강한 상승세)")
    if bearish_align:
        debug("완벽한 하락 정렬: 단기<중기<장기 이동평균 (강한 하락세)")

# 최종 결과 생성
result = {
    'patterns': patterns_found,
    'signal': None
}

# 매매 신호 결정 (모든 패턴 분석)
if pattern_type == 'all':
    buy_signals = 0
    sell_signals = 0
    
    # 매수 신호 집계
    if patterns_found.get('candle', {}).get('hammer', False):
        buy_signals += 1
    if patterns_found.get('candle', {}).get('bullish_engulfing', False):
        buy_signals += 1
    if patterns_found.get('breakout', {}).get('resistance', False):
        buy_signals += 1
    if patterns_found.get('divergence', {}).get('bullish', False):
        buy_signals += 1
    if patterns_found.get('ma', {}).get('golden_cross', False):
        buy_signals += 1
    
    # 매도 신호 집계
    if patterns_found.get('candle', {}).get('bearish_engulfing', False):
        sell_signals += 1
    if patterns_found.get('breakout', {}).get('support', False):
        sell_signals += 1
    if patterns_found.get('divergence', {}).get('bearish', False):
        sell_signals += 1
    if patterns_found.get('ma', {}).get('death_cross', False):
        sell_signals += 1
    
    # 최종 신호 결정 (3개 이상일 때 확정)
    if buy_signals >= 3:
        result['signal'] = 'BUY'
        debug(f"강한 매수 신호 감지 (총 {buy_signals}개 매수 패턴)")
    elif sell_signals >= 3:
        result['signal'] = 'SELL'
        debug(f"강한 매도 신호 감지 (총 {sell_signals}개 매도 패턴)")
    else:
        result['signal'] = 'NEUTRAL'
        debug(f"중립 신호 (매수: {buy_signals}개, 매도: {sell_signals}개 패턴)")
```
## 부록 E: 자주 묻는 질문 (FAQ)

### E.1 기본 사용법 관련

**Q: 스크립트에서 꼭 `result` 변수에 값을 저장해야 하나요?**  
A: 네. 모든 스크립트는 최종 결과값을 `result` 변수에 저장해야 합니다. 이 값이 스크립트의 반환값이 됩니다.

**Q: 기본으로 제공되는 변수들에는 어떤 것이 있나요?**  
A: `code`(종목코드), `name`(종목명), `qty`(보유수량), `price`(매수가)가 기본 제공됩니다. 이 변수들은 스크립트 내에서 직접 접근 가능합니다.

**Q: 다른 스크립트를 호출할 때 매개변수를 어떻게 전달하나요?**  
A: 스크립트 이름 뒤에 키워드 인자(keyword arguments)로 매개변수를 전달합니다.  
예: `my_script(period=5, threshold=1.5)`

**Q: 어떤 차트 주기를 사용할 수 있나요?**  
A: 분봉(mi), 일봉(dy), 주봉(wk), 월봉(mo) 주기를 사용할 수 있습니다. 분봉은 틱 수를 지정할 수 있습니다. (예: 5분봉은 `ChartManager(code, 'mi', 5)`)

### E.2 오류 및 디버깅 관련

**Q: "구문 오류" 메시지가 나타나면 어떻게 해야 하나요?**  
A: 오류 메시지에 표시된 행 번호를 확인하고, 해당 라인의 문법 오류를 수정합니다. 괄호, 따옴표, 들여쓰기 등을 확인하세요.

**Q: "보안 위반 코드 포함" 오류는 무엇인가요?**  
A: 허용되지 않는 코드(파일 접근, 시스템 명령 등)가 포함된 경우입니다. 금지된 기능 목록을 확인하세요.

**Q: 스크립트 실행 중 발생하는 오류를 어떻게 확인할 수 있나요?**  
A: `debug()`, `error()` 함수를 사용하여 중간 값이나 오류 정보를 로그로 출력하고 확인할 수 있습니다.

**Q: "순환 참조 감지" 오류는 무엇인가요?**  
A: 스크립트 A가 스크립트 B를 호출하고, B가 다시 A를 호출하는 등의 순환 참조가 발생할 때 나타납니다. 스크립트 간 호출 구조를 수정하세요.

**Q: 스크립트가 너무 느리게 실행될 경우 어떻게 최적화할 수 있나요?**  
A: 반복적인 계산은 변수에 저장하여 재사용하고, 필요한 데이터만 로드하세요. 부록 B.3의 성능 최적화 팁을 참고하세요.
