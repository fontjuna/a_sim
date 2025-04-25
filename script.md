# 스크립트 시스템 사용 안내서

## 1. 개요

이 스크립트 시스템은 차트 데이터를 분석하고 매매 신호를 생성하기 위한 유연한 도구입니다. Python 문법을 기반으로 하여 다양한 매매 전략을 구현할 수 있습니다.

## 2. 기본 구조

스크립트는 다음과 같은 기본 구조를 가집니다:

```python
# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉
mi3 = ChartManager('mi', 3)  # 3분봉

# 분석 코드 작성...

# 로깅 (선택사항)
logging.debug(f"분석 결과: {some_value}")

# 결과 반환 (필수)
result = True  # True = 매수 신호, False = 매수 신호 없음
```

## 3. ChartManager 사용법

ChartManager는 차트 데이터에 접근하고 분석하는 핵심 클래스입니다.

### 3.1 인스턴스 생성

```python
# 일봉 차트 매니저
dy = ChartManager('dy')

# 분봉 차트 매니저 (3분봉)
mi3 = ChartManager('mi', 3)

# 주봉 차트 매니저
wk = ChartManager('wk')

# 월봉 차트 매니저
mo = ChartManager('mo')
```

### 3.2 데이터 접근

```python
# n번째 이전 봉의 데이터 (n=0이 가장 최근 봉)
current_close = dy.c(code, 0)      # 현재 종가
previous_close = dy.c(code, 1)     # 이전 종가
open_price = dy.o(code, 0)        # 시가
high_price = dy.h(code, 0)        # 고가
low_price = dy.l(code, 0)         # 저가
volume = dy.v(code, 0)            # 거래량
amount = dy.a(code, 0)            # 거래대금
```

### 3.3 기술 지표 계산

```python
# 이동평균
ma20 = dy.ma(code, dy.c, 20, 0, 'a')   # 20일 단순이동평균
ema12 = dy.ma(code, dy.c, 12, 0, 'e')  # 12일 지수이동평균
wma10 = dy.ma(code, dy.c, 10, 0, 'w')  # 10일 가중이동평균

# 볼린저 밴드 (20일, 2배 표준편차)
upper, middle, lower = dy.bollinger_bands(code, 20, 2)

# RSI (14일)
rsi14 = dy.rsi(code, 14)

# MACD (12,26,9)
macd_line, signal_line, histogram = dy.macd(code, 12, 26, 9)

# 스토캐스틱 (14,3)
k_percent, d_percent = dy.stochastic(code, 14, 3)

# ATR (14일)
atr14 = dy.atr(code, 14)
```

### 3.4 신호 함수

```python
# 골든 크로스 (5일 이평이 20일 이평을 상향돌파)
golden_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n, 'a'), 
    lambda c, n: dy.ma(c, dy.c, 20, n, 'a'))

# 데드 크로스 (5일 이평이 20일 이평을 하향돌파)
dead_cross = dy.cross_down(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n, 'a'), 
    lambda c, n: dy.ma(c, dy.c, 20, n, 'a'))

# 상승추세 여부
uptrend = dy.is_uptrend(code, 20)

# 하락추세 여부
downtrend = dy.is_downtrend(code, 20)
```

### 3.5 캔들 패턴 분석

```python
# 도지 캔들 확인
is_doji = dy.is_doji(code, 0)

# 해머 패턴 확인
is_hammer = dy.is_hammer(code, 0)

# 상승 포괄 패턴 확인
is_bullish_engulfing = dy.is_engulfing(code, 0, True)
```

## 4. Python 함수 사용

스크립트 내에서는 다음 Python 내장 함수 및 모듈을 사용할 수 있습니다:

### 4.1 내장 함수

```python
# 수학 연산
max_value = max(value1, value2)
min_value = min(value1, value2)
total = sum([1, 2, 3, 4, 5])
absolute = abs(-10)
rounded = round(3.14159, 2)

# 반복문 대신 loop 함수 사용
values = loop(range(10), lambda i: dy.c(code, i))
```

### 4.2 조건문 및 논리 연산

```python
# 조건문
if value > threshold:
    signal = True
else:
    signal = False

# 조건 표현식
signal = value > threshold

# iif 함수 (중첩 조건에 유용)
signal_type = dy.iif(rsi > 70, "과매수", 
                    dy.iif(rsi < 30, "과매도", "중립"))
```

### 4.3 로깅

```python
# 디버그 로그
logging.debug(f"RSI 값: {rsi}")

# 정보 로그
logging.info(f"신호 발생: {signal_type}")

# 경고 로그
logging.warning(f"비정상 값 감지: {value}")
```

## 5. 여러 주기 활용

여러 주기를 함께 분석하는 예:

```python
# 일봉과 3분봉 함께 분석
dy = ChartManager('dy')
mi3 = ChartManager('mi', 3)

# 일봉 상승추세일 때 3분봉 골든크로스 확인
daily_uptrend = dy.is_uptrend(code, 20)
minute_golden_cross = mi3.cross_up(code, 
    lambda c, n: mi3.ma(c, mi3.c, 5, n, 'a'), 
    lambda c, n: mi3.ma(c, mi3.c, 20, n, 'a'))

# 두 조건 모두 만족할 때 매수 신호
result = daily_uptrend and minute_golden_cross
```

## 6. 다른 스크립트 호출

다른 스크립트를 호출하여 결과를 재사용할 수 있습니다:

```python
# 'GoldenCross' 스크립트 실행
golden_cross_signal = run_script('GoldenCross')

# 'RSIOverSold' 스크립트 실행
rsi_signal = run_script('RSIOverSold')

# 두 스크립트 모두 매수 신호일 때
result = golden_cross_signal and rsi_signal
```

## 7. 주의사항

1. 반복문은 `loop()` 함수를 사용해 안전하게 구현합니다.
2. 스크립트 끝에는 반드시 `result` 변수에 결과를 할당해야 합니다.
3. 무한 루프가 발생하지 않도록 주의합니다.
4. 실행 시간이 0.1초를 초과하지 않도록 효율적으로 작성합니다.
5. 허용된 모듈만 임포트할 수 있습니다 (math, datetime, re, logging, json, collections).

## 8. 예제 스크립트

### 8.1 골든 크로스 전략

```python
# 골든 크로스 전략
dy = ChartManager('dy')  # 일봉

# 단기/장기 이동평균
short_ma = dy.ma(code, dy.c, 5, 0, 'a')
long_ma = dy.ma(code, dy.c, 20, 0, 'a')

# 골든 크로스 확인
is_golden_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n, 'a'), 
    lambda c, n: dy.ma(c, dy.c, 20, n, 'a'))

# 결과 로깅
logging.debug(f"코드: {code}, 5MA: {short_ma:.2f}, 20MA: {long_ma:.2f}, 신호: {is_golden_cross}")

# 결과 반환
result = is_golden_cross
```

### 8.2 RSI 반전 전략

```python
# RSI 반전 전략
dy = ChartManager('dy')  # 일봉

# RSI 계산
current_rsi = dy.rsi(code, 14)
prev_rsi = dy.rsi(code, 14, 1)

# 과매도 상태에서 반등 확인
oversold_bounce = prev_rsi < 30 and current_rsi > prev_rsi

# 결과 로깅
logging.debug(f"코드: {code}, 현재RSI: {current_rsi:.2f}, 이전RSI: {prev_rsi:.2f}")

# 과매도 상태에서 반등 시 매수 신호
result = oversold_bounce
```

### 8.3 다중 주기 전략

```python
# 다중 주기 전략
dy = ChartManager('dy')   # 일봉
mi3 = ChartManager('mi', 3)  # 3분봉

# 일봉 상승추세 확인
daily_uptrend = dy.is_uptrend(code, 20)
daily_rsi = dy.rsi(code, 14)

# 3분봉 매매신호 확인
minute_ma5 = mi3.ma(code, mi3.c, 5, 0, 'a')
minute_ma20 = mi3.ma(code, mi3.c, 20, 0, 'a')
minute_cross_up = mi3.cross_up(code, 
    lambda c, n: mi3.ma(c, mi3.c, 5, n, 'a'), 
    lambda c, n: mi3.ma(c, mi3.c, 20, n, 'a'))

# 결과 로깅
logging.debug(f"코드: {code}, 일봉추세: {'상승' if daily_uptrend else '하락'}, 일봉RSI: {daily_rsi:.2f}")
logging.debug(f"3분봉 5MA: {minute_ma5:.2f}, 3분봉 20MA: {minute_ma20:.2f}, 3분봉 골든크로스: {minute_cross_up}")

# 일봉 상승추세 + 3분봉 골든크로스 + 일봉 RSI가 과매도 아님
result = daily_uptrend and minute_cross_up and daily_rsi > 30
```

### 9 스크립트 예제

# 1. 골든 크로스 전략
GOLDEN_CROSS_SCRIPT = """
# 골든 크로스 전략 (단기 이동평균이 장기 이동평균을 상향 돌파하면 매수 신호)
# 변수: short_period=5, long_period=20

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 단기 이동평균 계산
short_ma = dy.ma(code, dy.c, short_period, 0, 'a')  # 5일 단순이동평균
# 장기 이동평균 계산
long_ma = dy.ma(code, dy.c, long_period, 0, 'a')   # 20일 단순이동평균

# 골든 크로스 확인 (단기 이동평균이 장기 이동평균을 상향 돌파)
is_golden_cross = dy.cross_up(code, 
                             lambda c, n: dy.ma(c, dy.c, short_period, n, 'a'), 
                             lambda c, n: dy.ma(c, dy.c, long_period, n, 'a'))

# 결과 기록
logging.debug(f"종목코드: {code}, 단기이평: {short_ma:.2f}, 장기이평: {long_ma:.2f}, 골든크로스: {is_golden_cross}")

# 결과 반환 (True이면 매수 신호)
result = is_golden_cross
"""

# 2. 볼린저 밴드 돌파 전략
BOLLINGER_BREAKOUT_SCRIPT = """
# 볼린저 밴드 돌파 전략 (가격이 밴드를 상향 돌파하면 매수 신호)
# 변수: period=20, std_multiplier=2

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 볼린저 밴드 계산
upper_band, middle_band, lower_band = dy.bollinger_bands(code, period, std_multiplier)

# 현재가 및 전일 종가
current_price = dy.c(code, 0)
prev_price = dy.c(code, 1)

# 상단 밴드 돌파 확인 (이전에는 밴드 아래였다가 지금은 밴드 위로)
prev_upper_band = dy.bollinger_bands(code, period, std_multiplier, 1)[0]
upper_breakout = prev_price < prev_upper_band and current_price > upper_band

# 하단 밴드 돌파 확인 (이전에는 밴드 위였다가 지금은 밴드 아래로)
prev_lower_band = dy.bollinger_bands(code, period, std_multiplier, 1)[2]
lower_breakout = prev_price > prev_lower_band and current_price < lower_band

# 결과 기록
logging.debug(f"종목코드: {code}, 현재가: {current_price}, 상단밴드: {upper_band:.2f}, 중간밴드: {middle_band:.2f}, 하단밴드: {lower_band:.2f}")
logging.debug(f"상단돌파: {upper_breakout}, 하단돌파: {lower_breakout}")

# 결과 반환 (상단 돌파시 매수 신호)
result = upper_breakout
"""

# 3. 이중 전략 (골든 크로스 + RSI)
DUAL_STRATEGY_SCRIPT = """
# 이중 전략: 골든 크로스와 RSI가 모두 매수 신호일 때 매수
# 변수: short_period=5, long_period=20, rsi_period=14, rsi_oversold=30

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 골든 크로스 확인
golden_cross = run_script('GoldenCross')

# RSI 계산
current_rsi = dy.rsi(code, rsi_period)

# RSI 매수 신호 (과매도 상태에서 반등)
rsi_signal = current_rsi < rsi_oversold and dy.rsi(code, rsi_period, 1) < current_rsi

# 결과 기록
logging.debug(f"종목코드: {code}, 골든크로스: {golden_cross}, RSI: {current_rsi:.2f}, RSI신호: {rsi_signal}")

# 두 신호 모두 만족할 때
result = golden_cross and rsi_signal
"""

# 4. 캔들 패턴 인식 전략
CANDLE_PATTERN_SCRIPT = """
# 캔들 패턴 인식 전략 (해머 패턴이나 상승 포괄 패턴)
# 변수: 없음

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 해머 패턴 확인
is_hammer = dy.is_hammer(code, 0)

# 상승 포괄 패턴 확인
is_bullish_engulfing = dy.is_engulfing(code, 0, True)

# 이전 봉 종가 대비 상승률
prev_close = dy.c(code, 1)
current_close = dy.c(code, 0)
price_change_rate = ((current_close - prev_close) / prev_close) * 100 if prev_close > 0 else 0

# 거래량 증가 확인
volume_increase = dy.v(code, 0) > dy.v(code, 1) * 1.5  # 150% 이상 증가

# 결과 기록
logging.debug(f"종목코드: {code}, 해머패턴: {is_hammer}, 상승포괄패턴: {is_bullish_engulfing}")
logging.debug(f"가격변화율: {price_change_rate:.2f}%, 거래량증가: {volume_increase}")

# 패턴 중 하나와 거래량 증가가 동시에 발생할 때
result = (is_hammer or is_bullish_engulfing) and volume_increase
"""

# 5. 반복문 활용 예제 (loop 함수 사용)
LOOP_EXAMPLE_SCRIPT = """
# 반복문(loop) 활용 예제 - 최근 N개 봉 중 최고가 찾기
# 변수: check_days=10

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 최근 10개 봉 고가 확인 (loop 함수 활용)
days_range = range(check_days)
high_prices = loop(days_range, lambda i: dy.h(code, i))

# 최고가 및 위치 찾기
max_high_price = max(high_prices)
max_high_day = high_prices.index(max_high_price)

# 현재가와 최고가 비교
current_price = dy.c(code, 0)
drop_from_high = ((max_high_price - current_price) / max_high_price) * 100 if max_high_price > 0 else 0

# 결과 기록
logging.debug(f"종목코드: {code}, 현재가: {current_price}, 최근 {check_days}일 최고가: {max_high_price}")
logging.debug(f"최고가 발생일: {max_high_day}일 전, 최고가 대비 하락률: {drop_from_high:.2f}%")

# 최고가 대비 10% 이상 하락한 경우 매수 신호
result = drop_from_high >= 10
"""

# 6. 여러 주기 활용 예제
MULTI_TIMEFRAME_SCRIPT = """
# 여러 주기 활용 예제 - 일봉과 3분봉 함께 분석
# 변수: 없음

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')   # 일봉
mi3 = ChartManager('mi', 3)  # 3분봉
    
# 일봉에서 추세 확인
daily_uptrend = dy.is_uptrend(code, 20)
daily_rsi = dy.rsi(code, 14)
    
# 3분봉에서 매매 시그널 확인
minute_ma5 = mi3.ma(code, mi3.c, 5, 0, 'a')
minute_ma20 = mi3.ma(code, mi3.c, 20, 0, 'a')
minute_cross_up = mi3.cross_up(code, 
                              lambda c, n: mi3.ma(c, mi3.c, 5, n, 'a'), 
                              lambda c, n: mi3.ma(c, mi3.c, 20, n, 'a'))
    
# 결과 기록
logging.debug(f"종목코드: {code}, 일봉추세: {'상승' if daily_uptrend else '하락'}, 일봉RSI: {daily_rsi:.2f}")
logging.debug(f"3분봉 5MA: {minute_ma5:.2f}, 3분봉 20MA: {minute_ma20:.2f}, 3분봉 골든크로스: {minute_cross_up}")
    
# 일봉이 상승추세이고 3분봉에서 골든크로스 발생한 경우
signal = daily_uptrend and minute_cross_up
    
# 결과 반환
result = signal
"""

# 7. MACD 크로스오버 전략
MACD_CROSSOVER_SCRIPT = """
# MACD 크로스오버 전략
# 변수: fast_period=12, slow_period=26, signal_period=9

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 현재 MACD 값 계산
current_macd, current_signal, current_hist = dy.macd(code, fast_period, slow_period, signal_period)

# 이전 MACD 값 계산
prev_macd, prev_signal, prev_hist = dy.macd(code, fast_period, slow_period, signal_period, 1)

# MACD 라인이 시그널 라인을 상향 돌파하는지 확인
macd_crossover = prev_macd < prev_signal and current_macd > current_signal

# 결과 기록
logging.debug(f"종목코드: {code}, MACD: {current_macd:.2f}, 시그널: {current_signal:.2f}, 히스토그램: {current_hist:.2f}")
logging.debug(f"MACD 크로스오버: {macd_crossover}")

# MACD 크로스오버 발생 시 매수 신호
result = macd_crossover
"""

# 8. 변동성 돌파 전략
VOLATILITY_BREAKOUT_SCRIPT = """
# 변동성 돌파 전략 (전일 변동폭의 일정 비율 돌파 시 매수)
# 변수: k=0.5

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 전일 고가-저가 범위
prev_high = dy.h(code, 1)
prev_low = dy.l(code, 1)
prev_range = prev_high - prev_low

# 당일 시가 및 현재가
today_open = dy.o(code, 0)
current_price = dy.c(code, 0)

# 목표가 계산 (시가 + 전일변동폭 * k)
target_price = today_open + prev_range * k

# 돌파 여부 확인
breakout = current_price > target_price

# 결과 기록
logging.debug(f"종목코드: {code}, 전일범위: {prev_range}, 목표가: {target_price}, 현재가: {current_price}")
logging.debug(f"돌파 여부: {breakout}")

# 목표가 돌파 시 매수 신호
result = breakout
"""

# 9. 이평선 지지/저항 전략
MOVING_AVERAGE_SUPPORT_SCRIPT = """
# 이동평균선 지지/저항 전략
# 변수: ma_period=50

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 50일 이동평균 계산
ma50 = dy.ma(code, dy.c, ma_period, 0, 'a')

# 현재가 및 저가
current_price = dy.c(code, 0)
low_price = dy.l(code, 0)

# 이동평균선 지지 확인 (저가가 이평선 근처까지 내려갔다가 반등)
support_bounce = low_price <= ma50 * 1.02 and low_price >= ma50 * 0.98 and current_price > ma50

# 추세 확인 (20일 이평이 50일 이평보다 높음)
ma20 = dy.ma(code, dy.c, 20, 0, 'a')
uptrend = ma20 > ma50

# 결과 기록
logging.debug(f"종목코드: {code}, 현재가: {current_price}, 50MA: {ma50:.2f}, 20MA: {ma20:.2f}")
logging.debug(f"이평선 지지 반등: {support_bounce}, 상승추세: {uptrend}")

# 상승추세에서 이동평균선 지지 확인 시 매수 신호
result = uptrend and support_bounce
"""

# 10. 스토캐스틱 + RSI 결합 전략
STOCHASTIC_RSI_SCRIPT = """
# 스토캐스틱과 RSI 결합 전략
# 변수: k_period=14, d_period=3, rsi_period=14

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 스토캐스틱 계산
k_percent, d_percent = dy.stochastic(code, k_period, d_period)
prev_k, prev_d = dy.stochastic(code, k_period, d_period, 1)

# RSI 계산
rsi = dy.rsi(code, rsi_period)

# 과매도 영역에서 반등 신호 확인
oversold_stochastic = prev_k < 20 and k_percent > prev_k and k_percent > d_percent
oversold_rsi = rsi < 30 and rsi > dy.rsi(code, rsi_period, 1)

# 결과 기록
logging.debug(f"종목코드: {code}, 스토캐스틱 K: {k_percent:.2f}, D: {d_percent:.2f}, RSI: {rsi:.2f}")
logging.debug(f"스토캐스틱 반등: {oversold_stochastic}, RSI 반등: {oversold_rsi}")

# 스토캐스틱과 RSI 모두 과매도에서 반등 시 매수 신호
result = oversold_stochastic and oversold_rsi
"""
