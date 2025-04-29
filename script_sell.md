# 매도 전략 1장: 기본 매도 전략

## 1.1 개요

매도 전략은 투자에서 매수만큼이나 중요합니다. 적절한 매도 시점을 찾지 못하면 수익을 실현하지 못하거나 큰 손실을 볼 수 있습니다. 이 장에서는 다양한 기본 매도 전략을 살펴봅니다.

## 1.2 기술적 지표 기반 매도 신호

### 1.2.1 과매수 영역 RSI 매도 전략

```python
# RSI 과매수 영역 매도 전략
dy = ChartManager('dy')

# 매개변수
rsi_period = kwargs.get('rsi_period', 14)
overbought_threshold = kwargs.get('overbought_threshold', 70)
confirmation_days = kwargs.get('confirmation_days', 2)

# RSI 계산
current_rsi = dy.rsi(code, rsi_period)

# 과매수 확인
is_overbought = current_rsi > overbought_threshold

# 확인 기간 동안 RSI가 과매수 영역에 있었는지 확인
confirmation_count = 0
for i in range(1, confirmation_days + 1):
    if dy.rsi(code, rsi_period, i) > overbought_threshold:
        confirmation_count += 1

# 확인 기간 동안 계속 과매수 상태였다가 현재 하락 시작하는지 확인
rsi_turning_down = current_rsi < dy.rsi(code, rsi_period, 1)

# 최종 매도 신호: 현재 과매수 + 확인 기간 동안 과매수 지속 + RSI 하락 전환
sell_signal = is_overbought and confirmation_count >= confirmation_days - 1 and rsi_turning_down

result = {
    "current_rsi": current_rsi,
    "is_overbought": is_overbought,
    "confirmation_count": confirmation_count,
    "rsi_turning_down": rsi_turning_down,
    "sell_signal": sell_signal
}
```

### 1.2.2 이동평균 기반 데스 크로스 매도 전략

```python
# 이동평균 데스 크로스 매도 전략
dy = ChartManager('dy')

# 단기/장기 이동평균 기간
short_period = kwargs.get('short_period', 5)
long_period = kwargs.get('long_period', 20)

# 이동평균 계산
short_ma = dy.ma(code, dy.c, short_period)
long_ma = dy.ma(code, dy.c, long_period)

# 데스 크로스 확인 (단기 이평선이 장기 이평선을 하향 돌파)
death_cross = dy.cross_down(code,
    lambda c, n: dy.ma(c, dy.c, short_period, n),
    lambda c, n: dy.ma(c, dy.c, long_period, n))

# 거래량 급증 확인
volume_surge = dy.v(code) > dy.avg(code, dy.v, 20) * 1.5

# 매도 신호: 데스 크로스 + 거래량 급증
sell_signal = death_cross and volume_surge

result = {
    "short_ma": short_ma,
    "long_ma": long_ma,
    "death_cross": death_cross,
    "volume_surge": volume_surge,
    "sell_signal": sell_signal
}
```

### 1.2.3 MACD 하향 교차 매도 전략

```python
# MACD 하향 교차 매도 전략
dy = ChartManager('dy')

# MACD 파라미터
fast_period = kwargs.get('fast_period', 12)
slow_period = kwargs.get('slow_period', 26)
signal_period = kwargs.get('signal_period', 9)

# MACD 계산
macd_line, signal_line, histogram = dy.macd(code, fast_period, slow_period, signal_period)

# 이전 MACD 값
prev_macd_line, prev_signal_line, prev_histogram = dy.macd(code, fast_period, slow_period, signal_period, 1)

# MACD 하향 교차 (매도 신호)
bearish_cross = macd_line < signal_line and prev_macd_line >= prev_signal_line

# 히스토그램 하향 전환 (약한 매도 신호)
histogram_turning_negative = histogram < 0 and prev_histogram >= 0

# 최종 매도 신호
sell_signal = bearish_cross or histogram_turning_negative

# 강도 평가 (0-10)
if bearish_cross and histogram_turning_negative:
    strength = 10  # 가장 강한 신호
elif bearish_cross:
    strength = 8   # 강한 신호
elif histogram_turning_negative:
    strength = 5   # 중간 강도 신호
else:
    strength = 0   # 신호 없음

result = {
    "macd_line": macd_line,
    "signal_line": signal_line,
    "histogram": histogram,
    "bearish_cross": bearish_cross,
    "histogram_turning_negative": histogram_turning_negative,
    "sell_signal": sell_signal,
    "signal_strength": strength
}
```

## 1.3 가격 패턴 기반 매도 신호

### 1.3.1 이중 고점 매도 전략 (Double Top)

```python
# 이중 고점(Double Top) 매도 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 30)  # 분석 기간
threshold = kwargs.get('threshold', 0.03)  # 고점 유사성 임계값 (3%)

# 최근 고점 찾기
price_data = [dy.h(code, i) for i in range(lookback)]
highs = []

# 고점 탐지 (양쪽 봉보다 높은 봉)
for i in range(2, lookback-2):
    if (price_data[i] > price_data[i-1] and 
        price_data[i] > price_data[i-2] and 
        price_data[i] > price_data[i+1] and 
        price_data[i] > price_data[i+2]):
        highs.append((i, price_data[i]))

# 고점이 최소 2개 필요
if len(highs) < 2:
    result = {"sell_signal": False, "pattern": "이중 고점 없음"}
    return

# 시간순으로 정렬된 고점들
sorted_highs = sorted(highs, key=lambda x: x[0])
recent_highs = sorted_highs[:2]  # 가장 최근 2개 고점

# 두 고점의 가격 유사성 확인
price_diff_pct = abs(recent_highs[0][1] - recent_highs[1][1]) / recent_highs[0][1]
similar_heights = price_diff_pct <= threshold

# 두 고점 사이 저점 찾기
valley_start = recent_highs[0][0]
valley_end = recent_highs[1][0]
valley_prices = [dy.l(code, i) for i in range(valley_start, valley_end+1)]
valley_low = min(valley_prices)
valley_low_idx = valley_prices.index(valley_low) + valley_start

# 이중 고점 이후 넥라인(지지선) 돌파 확인
neckline = valley_low
current_price = dy.c(code)
breaks_neckline = current_price < neckline

# 패턴 완성 여부
pattern_complete = similar_heights and breaks_neckline

# 추가 확인: 거래량 증가
volume_increasing = dy.v(code) > dy.avg(code, dy.v, 5)

# 최종 매도 신호
sell_signal = pattern_complete and volume_increasing

result = {
    "pattern": "이중 고점 감지",
    "high1": recent_highs[0][1],
    "high2": recent_highs[1][1],
    "price_diff_pct": price_diff_pct * 100,
    "similar_heights": similar_heights,
    "neckline": neckline,
    "breaks_neckline": breaks_neckline,
    "pattern_complete": pattern_complete,
    "volume_increasing": volume_increasing,
    "sell_signal": sell_signal
}
```

### 1.3.2 상승 쐐기형 매도 전략 (Rising Wedge)

```python
# 상승 쐐기형(Rising Wedge) 매도 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 20)  # 분석 기간
min_points = kwargs.get('min_points', 5)  # 최소 터치 포인트 수

# 고가/저가 데이터 수집
highs = [dy.h(code, i) for i in range(lookback)]
lows = [dy.l(code, i) for i in range(lookback)]

# 상단선, 하단선에 각각 최소 터치 포인트 찾기
high_points = []
low_points = []

for i in range(2, lookback-2):
    # 고점 찾기 (양쪽 2봉보다 높은 봉)
    if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
        high_points.append((i, highs[i]))
    
    # 저점 찾기 (양쪽 2봉보다 낮은 봉)
    if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
        low_points.append((i, lows[i]))

# 충분한 포인트가 있는지 확인
if len(high_points) < 3 or len(low_points) < 3:
    result = {"sell_signal": False, "pattern": "상승 쐐기형 패턴 포인트 부족"}
    return

# 선형 회귀로 상단선, 하단선의 기울기 계산
def calculate_slope(points):
    x = [p[0] for p in points]
    y = [p[1] for p in points]
    n = len(points)
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator != 0 else 0

upper_slope = calculate_slope(high_points)
lower_slope = calculate_slope(low_points)

# 상승 쐐기형 확인 (두 추세선 모두 상승하며, 수렴)
rising_wedge = upper_slope > 0 and lower_slope > 0 and upper_slope < lower_slope

# 패턴 하향 돌파 확인
current_price = dy.c(code)
latest_idx = 0
lower_trendline_value = low_points[-1][1] + lower_slope * (0 - low_points[-1][0])
breakdown = current_price < lower_trendline_value

# 거래량 확인
volume_surge = dy.v(code) > dy.avg(code, dy.v, 5)

# 최종 매도 신호
sell_signal = rising_wedge and breakdown and volume_surge

result = {
    "pattern": "상승 쐐기형 패턴",
    "upper_slope": upper_slope,
    "lower_slope": lower_slope,
    "rising_wedge": rising_wedge,
    "lower_trendline": lower_trendline_value,
    "breakdown": breakdown,
    "volume_surge": volume_surge,
    "sell_signal": sell_signal
}
```

### 1.3.3 헤드앤숄더 매도 전략 (Head and Shoulders)

```python
# 헤드앤숄더(Head and Shoulders) 매도 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 40)  # 분석 기간
threshold = kwargs.get('threshold', 0.03)  # 어깨 유사성 임계값 (3%)

# 최근 고점 찾기
price_data = [dy.h(code, i) for i in range(lookback)]
pivot_points = []

# 피봇 포인트 탐지 (고점)
for i in range(2, lookback-2):
    if (price_data[i] > price_data[i-1] and 
        price_data[i] > price_data[i-2] and 
        price_data[i] > price_data[i+1] and 
        price_data[i] > price_data[i+2]):
        pivot_points.append((i, price_data[i]))

# 최소 3개 피봇 필요 (왼쪽 어깨, 머리, 오른쪽 어깨)
if len(pivot_points) < 3:
    result = {"sell_signal": False, "pattern": "헤드앤숄더 패턴 포인트 부족"}
    return

# 고점 기준 정렬 및 상위 3개 선택
sorted_by_height = sorted(pivot_points, key=lambda x: x[1], reverse=True)
top_three = sorted_by_height[:3]

# 시간순 정렬
top_three.sort(key=lambda x: x[0])

# 패턴이 맞는지 확인 (중간이 제일 높아야 함)
if top_three[1][1] <= top_three[0][1] or top_three[1][1] <= top_three[2][1]:
    result = {"sell_signal": False, "pattern": "헤드앤숄더 패턴 아님 (머리가 제일 높지 않음)"}
    return

# 왼쪽/오른쪽 어깨 높이 유사성 확인
left_shoulder = top_three[0]
head = top_three[1]
right_shoulder = top_three[2]

shoulder_diff_pct = abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1]
similar_shoulders = shoulder_diff_pct <= threshold

# 넥라인(목선) 계산 - 두 어깨 사이의 저점들 연결
left_valley_idx = (left_shoulder[0] + head[0]) // 2
right_valley_idx = (head[0] + right_shoulder[0]) // 2

left_valley = min([dy.l(code, i) for i in range(left_valley_idx-2, left_valley_idx+3)])
right_valley = min([dy.l(code, i) for i in range(right_valley_idx-2, right_valley_idx+3)])

# 넥라인이 수평인지 확인
neckline_slope = (right_valley - left_valley) / (right_valley_idx - left_valley_idx)
flat_neckline = abs(neckline_slope) < 0.001  # 거의 수평

# 현재 넥라인 값 계산
current_neckline = right_valley + neckline_slope * (0 - right_valley_idx)

# 넥라인 돌파 확인
current_price = dy.c(code)
breaks_neckline = current_price < current_neckline

# 패턴 확인
pattern_valid = similar_shoulders and breaks_neckline

# 추가 확인: 거래량 증가
volume_increasing = dy.v(code) > dy.avg(code, dy.v, 5)

# 최종 매도 신호
sell_signal = pattern_valid and volume_increasing

result = {
    "pattern": "헤드앤숄더 패턴",
    "left_shoulder": left_shoulder[1],
    "head": head[1],
    "right_shoulder": right_shoulder[1],
    "shoulder_diff_pct": shoulder_diff_pct * 100,
    "similar_shoulders": similar_shoulders,
    "neckline_value": current_neckline,
    "breaks_neckline": breaks_neckline,
    "pattern_valid": pattern_valid,
    "volume_increasing": volume_increasing,
    "sell_signal": sell_signal
}
```

# 매도 전략 2장: 손절매 및 이익실현 전략

## 2.1 손절매 전략

손절매(Stop Loss)는 투자 손실을 제한하기 위한 필수적인 전략입니다. 적절한 손절매 전략은 대규모 손실을 방지하고 자본을 보존하는 데 도움이 됩니다.

### 2.1.1 고정 비율 손절매 전략

```python
# 고정 비율 손절매 전략
dy = ChartManager('dy')

# 매개변수
stop_loss_pct = kwargs.get('stop_loss_pct', 5.0)  # 손절매 비율 (%)
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 손실률 계산
loss_pct = (entry_price - current_price) / entry_price * 100

# 손절매 신호
stop_loss_triggered = loss_pct >= stop_loss_pct

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "loss_pct": loss_pct,
    "stop_loss_threshold": stop_loss_pct,
    "stop_loss_triggered": stop_loss_triggered
}
```

### 2.1.2 ATR 기반 손절매 전략

```python
# ATR 기반 손절매 전략
dy = ChartManager('dy')

# 매개변수
atr_period = kwargs.get('atr_period', 14)  # ATR 계산 기간
atr_multiplier = kwargs.get('atr_multiplier', 2.0)  # ATR 배수
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# ATR 계산
atr_value = dy.atr(code, atr_period)

# 손절매 가격 계산
stop_loss_price = entry_price - (atr_value * atr_multiplier)

# 손절매 신호
stop_loss_triggered = current_price <= stop_loss_price

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "atr_value": atr_value,
    "stop_loss_price": stop_loss_price,
    "stop_loss_triggered": stop_loss_triggered
}
```

### 2.1.3 이동평균 기반 손절매 전략

```python
# 이동평균 기반 손절매 전략
dy = ChartManager('dy')

# 매개변수
ma_period = kwargs.get('ma_period', 20)  # 이동평균 기간
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 이동평균 계산
ma_value = dy.ma(code, dy.c, ma_period)

# 손절매 신호: 가격이 이동평균선 아래로 하락
stop_loss_triggered = current_price < ma_value

# 손실률 계산
loss_pct = (entry_price - current_price) / entry_price * 100 if current_price < entry_price else 0

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "ma_value": ma_value,
    "loss_pct": loss_pct,
    "stop_loss_triggered": stop_loss_triggered
}
```

### 2.1.4 변동성 돌파 손절매 전략

```python
# 변동성 돌파 손절매 전략
dy = ChartManager('dy')

# 매개변수
volatility_period = kwargs.get('volatility_period', 10)  # 변동성 계산 기간
volatility_multiplier = kwargs.get('volatility_multiplier', 1.5)  # 변동성 배수
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 최근 변동성 계산 (일일 고가-저가 범위의 평균)
volatility = 0
for i in range(volatility_period):
    daily_range = dy.h(code, i) - dy.l(code, i)
    volatility += daily_range
volatility /= volatility_period

# 손절매 가격 계산
stop_loss_price = entry_price - (volatility * volatility_multiplier)

# 손절매 신호
stop_loss_triggered = current_price <= stop_loss_price

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "volatility": volatility,
    "stop_loss_price": stop_loss_price,
    "stop_loss_triggered": stop_loss_triggered
}
```

## 2.2 이익실현 전략

이익실현(Take Profit)은 투자 수익을 확정하는 전략입니다. 적절한 이익실현 전략은 수익을 보호하고 자본 증가를 도모합니다.

### 2.2.1 고정 비율 이익실현 전략

```python
# 고정 비율 이익실현 전략
dy = ChartManager('dy')

# 매개변수
take_profit_pct = kwargs.get('take_profit_pct', 10.0)  # 이익실현 비율 (%)
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 수익률 계산
profit_pct = (current_price - entry_price) / entry_price * 100

# 이익실현 신호
take_profit_triggered = profit_pct >= take_profit_pct

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "profit_pct": profit_pct,
    "take_profit_threshold": take_profit_pct,
    "take_profit_triggered": take_profit_triggered
}
```

### 2.2.2 피보나치 되돌림 이익실현 전략

```python
# 피보나치 되돌림 이익실현 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 60)  # 분석 기간
fib_level = kwargs.get('fib_level', 1.618)  # 피보나치 되돌림 레벨
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 최근 주요 저점과 고점 찾기
highs = [dy.h(code, i) for i in range(lookback)]
lows = [dy.l(code, i) for i in range(lookback)]

swing_high = max(highs)
swing_high_idx = highs.index(swing_high)
swing_low = min(lows[swing_high_idx:]) if swing_high_idx < len(lows) else min(lows)

# 가격 범위
price_range = swing_high - swing_low

# 피보나치 목표가 계산
fib_target = swing_low + (price_range * fib_level)

# 이익실현 신호
take_profit_triggered = current_price >= fib_target

# 수익률 계산
profit_pct = (current_price - entry_price) / entry_price * 100 if current_price > entry_price else 0

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "swing_high": swing_high,
    "swing_low": swing_low,
    "fib_target": fib_target,
    "profit_pct": profit_pct,
    "take_profit_triggered": take_profit_triggered
}
```

### 2.2.3 추세선 돌파 이익실현 전략

```python
# 추세선 돌파 이익실현 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 20)  # 분석 기간
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 고가 데이터 수집
highs = [dy.h(code, i) for i in range(lookback)]

# 상승 추세선 계산 (고점 연결)
high_points = []
for i in range(2, lookback-2):
    if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
        high_points.append((i, highs[i]))

# 고점이 최소 2개 필요
if len(high_points) < 2:
    result = {
        "take_profit_triggered": False,
        "reason": "충분한 고점을 찾을 수 없음"
    }
    return

# 최근 두 고점 선택
sorted_high_points = sorted(high_points, key=lambda x: x[0])
recent_high_points = sorted_high_points[-2:]

# 추세선 기울기 계산
x1, y1 = recent_high_points[0]
x2, y2 = recent_high_points[1]
slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0

# 현재 시점의 추세선 값 계산
trendline_value = y2 + slope * (0 - x2)

# 추세선 돌파 확인
breaks_trendline = current_price > trendline_value

# 이익실현 신호
take_profit_triggered = breaks_trendline

# 수익률 계산
profit_pct = (current_price - entry_price) / entry_price * 100 if current_price > entry_price else 0

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "trendline_value": trendline_value,
    "breaks_trendline": breaks_trendline,
    "profit_pct": profit_pct,
    "take_profit_triggered": take_profit_triggered
}
```

### 2.2.4 볼린저 밴드 이익실현 전략

```python
# 볼린저 밴드 이익실현 전략
dy = ChartManager('dy')

# 매개변수
bb_period = kwargs.get('bb_period', 20)  # 볼린저 밴드 기간
bb_std = kwargs.get('bb_std', 2)  # 표준편차 배수
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 볼린저 밴드 계산
upper, middle, lower = dy.bollinger_bands(code, bb_period, bb_std)

# 이익실현 신호: 가격이 상단 밴드에 도달
take_profit_triggered = current_price >= upper

# 이익실현 강도 계산 (0-10)
band_width = upper - lower
if band_width > 0:
    relative_position = (current_price - middle) / (band_width / 2)  # 중앙선 기준 상대 위치
    signal_strength = min(10, max(0, int(relative_position * 5))) if relative_position > 0 else 0
else:
    signal_strength = 0

# 수익률 계산
profit_pct = (current_price - entry_price) / entry_price * 100 if current_price > entry_price else 0

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "upper_band": upper,
    "middle_band": middle,
    "lower_band": lower,
    "profit_pct": profit_pct,
    "signal_strength": signal_strength,
    "take_profit_triggered": take_profit_triggered
}
```

## 2.3 트레일링 스탑(Trailing Stop) 전략

트레일링 스탑은 손절매 가격을 가격 움직임에 따라 조정하는 동적 손절매 전략입니다. 이를 통해 이익을 보호하면서 추가 상승 가능성을 열어둘 수 있습니다.

### 2.3.1 기본 트레일링 스탑 전략

```python
# 기본 트레일링 스탑 전략
dy = ChartManager('dy')

# 매개변수
trailing_pct = kwargs.get('trailing_pct', 5.0)  # 트레일링 스탑 비율 (%)
entry_price = kwargs.get('entry_price', 0)  # 진입가격
highest_since_entry = kwargs.get('highest_since_entry', 0)  # 진입 후 최고가

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# 진입 후 최고가 업데이트
if highest_since_entry == 0:
    # 이전 데이터에서 최고가 검색
    lookback = 30  # 최대 30봉 전까지 검색
    prices = [dy.h(code, i) for i in range(lookback)]
    entry_idx = prices.index(entry_price) if entry_price in prices else 0
    highest_since_entry = max(prices[:entry_idx+1])
else:
    # 제공된 최고가와 현재가 비교하여 업데이트
    highest_since_entry = max(highest_since_entry, current_price)

# 트레일링 스탑 가격 계산
stop_price = highest_since_entry * (1 - trailing_pct / 100)

# 트레일링 스탑 발동 여부
stop_triggered = current_price <= stop_price

# 현재 수익률
current_profit_pct = (current_price - entry_price) / entry_price * 100

# 트레일링 스탑 발동 시 확정 수익률
locked_profit_pct = (stop_price - entry_price) / entry_price * 100

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "highest_since_entry": highest_since_entry,
    "stop_price": stop_price,
    "current_profit_pct": current_profit_pct,
    "locked_profit_pct": locked_profit_pct,
    "stop_triggered": stop_triggered,
    # 다음 호출 시 사용할 최고가 기록
    "highest_since_entry_next": highest_since_entry
}
```

### 2.3.2 ATR 트레일링 스탑 전략

```python
# ATR 트레일링 스탑 전략
dy = ChartManager('dy')

# 매개변수
atr_period = kwargs.get('atr_period', 14)  # ATR 계산 기간
atr_multiplier = kwargs.get('atr_multiplier', 3.0)  # ATR 배수
entry_price = kwargs.get('entry_price', 0)  # 진입가격
highest_since_entry = kwargs.get('highest_since_entry', 0)  # 진입 후 최고가

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격
current_price = dy.c(code)

# ATR 계산
atr_value = dy.atr(code, atr_period)

# 진입 후 최고가 업데이트
if highest_since_entry == 0:
    # 이전 데이터에서 최고가 검색
    lookback = 30  # 최대 30봉 전까지 검색
    prices = [dy.h(code, i) for i in range(lookback)]
    entry_idx = prices.index(entry_price) if entry_price in prices else 0
    highest_since_entry = max(prices[:entry_idx+1])
else:
    # 제공된 최고가와 현재가 비교하여 업데이트
    highest_since_entry = max(highest_since_entry, current_price)

# ATR 트레일링 스탑 가격 계산
stop_price = highest_since_entry - (atr_value * atr_multiplier)

# 트레일링 스탑 발동 여부
stop_triggered = current_price <= stop_price

# 현재 수익률
current_profit_pct = (current_price - entry_price) / entry_price * 100

# 트레일링 스탑 발동 시 확정 수익률
locked_profit_pct = (stop_price - entry_price) / entry_price * 100

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "highest_since_entry": highest_since_entry,
    "atr_value": atr_value,
    "stop_price": stop_price,
    "current_profit_pct": current_profit_pct,
    "locked_profit_pct": locked_profit_pct,
    "stop_triggered": stop_triggered,
    # 다음 호출 시 사용할 최고가 기록
    "highest_since_entry_next": highest_since_entry
}
```

### 2.3.3 파라볼릭 SAR 트레일링 스탑 전략

```python
# 파라볼릭 SAR 트레일링 스탑 전략
dy = ChartManager('dy')

# 매개변수
acceleration_factor = kwargs.get('acceleration_factor', 0.02)  # 가속 계수
max_acceleration = kwargs.get('max_acceleration', 0.2)  # 최대 가속 계수
entry_price = kwargs.get('entry_price', 0)  # 진입가격

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 현재가격 및 이전 가격 데이터
current_price = dy.c(code)
prev_price = dy.c(code, 1)
current_high = dy.h(code)
prev_high = dy.h(code, 1)

# 이전 SAR 값 (제공되지 않은 경우 진입가의 95% 사용)
prev_sar = kwargs.get('prev_sar', entry_price * 0.95)

# 이전 EP (Extreme Point, 제공되지 않은 경우 진입가 사용)
prev_ep = kwargs.get('prev_ep', entry_price)

# 이전 AF (Acceleration Factor, 제공되지 않은 경우 초기값 사용)
prev_af = kwargs.get('prev_af', acceleration_factor)

# 새로운 EP 계산 (상승 추세에서는 최고가)
current_ep = max(prev_ep, current_high)

# 새로운 AF 계산 (새 고점 갱신 시 AF 증가)
current_af = prev_af
if current_ep > prev_ep:
    current_af = min(prev_af + acceleration_factor, max_acceleration)

# 새로운 SAR 계산
current_sar = prev_sar + prev_af * (prev_ep - prev_sar)

# SAR 위치 조정 (가격보다 위에 있으면 안 됨)
if current_sar > prev_price or current_sar > current_price:
    current_sar = min(prev_price, current_price)

# 트레일링 스탑 발동 여부
stop_triggered = current_price <= current_sar

# 현재 수익률
current_profit_pct = (current_price - entry_price) / entry_price * 100

# 트레일링 스탑 발동 시 확정 수익률
locked_profit_pct = (current_sar - entry_price) / entry_price * 100

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "current_sar": current_sar,
    "current_ep": current_ep,
    "current_af": current_af,
    "current_profit_pct": current_profit_pct,
    "locked_profit_pct": locked_profit_pct,
    "stop_triggered": stop_triggered,
    # 다음 호출 시 사용할 값들
    "prev_sar_next": current_sar,
    "prev_ep_next": current_ep,
    "prev_af_next": current_af
}
```
# 매도 전략 3장: 복합 매도 전략 및 실전 적용

## 3.1 복합 매도 지표 전략

단일 지표 대신 여러 지표를 결합하여 매도 신호의 정확성을 높일 수 있습니다. 복합 지표 전략은 오판단 가능성을 줄이고 더 강력한 매도 신호를 생성합니다.

### 3.1.1 RSI + MACD + 볼린저 밴드 복합 매도 전략

```python
# RSI + MACD + 볼린저 밴드 복합 매도 전략
dy = ChartManager('dy')

# 매개변수
rsi_period = kwargs.get('rsi_period', 14)
rsi_threshold = kwargs.get('rsi_threshold', 70)
macd_fast = kwargs.get('macd_fast', 12)
macd_slow = kwargs.get('macd_slow', 26)
macd_signal = kwargs.get('macd_signal', 9)
bb_period = kwargs.get('bb_period', 20)
bb_std = kwargs.get('bb_std', 2)
min_signals = kwargs.get('min_signals', 2)  # 최소 매도 신호 수

# 1. RSI 과매수 확인
rsi_value = dy.rsi(code, rsi_period)
rsi_sell = rsi_value > rsi_threshold

# 2. MACD 하향 교차 확인
macd_line, signal_line, histogram = dy.macd(code, macd_fast, macd_slow, macd_signal)
prev_macd, prev_signal, prev_hist = dy.macd(code, macd_fast, macd_slow, macd_signal, 1)
macd_bearish_cross = macd_line < signal_line and prev_macd >= prev_signal
macd_turning_negative = histogram < 0 and prev_hist >= 0
macd_sell = macd_bearish_cross or macd_turning_negative

# 3. 볼린저 밴드 상단 터치 확인
upper, middle, lower = dy.bollinger_bands(code, bb_period, bb_std)
current_price = dy.c(code)
bb_sell = current_price >= upper

# 매도 신호 카운트
sell_signals = [rsi_sell, macd_sell, bb_sell]
signal_count = sum(sell_signals)

# 최종 매도 신호: 최소 N개 이상의 지표가 매도 신호 발생
sell_signal = signal_count >= min_signals

# 매도 강도 (0-100%)
sell_strength = (signal_count / len(sell_signals)) * 100

# 지표별 상세 정보
details = {
    "rsi": {
        "value": rsi_value,
        "threshold": rsi_threshold,
        "sell_signal": rsi_sell
    },
    "macd": {
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
        "bearish_cross": macd_bearish_cross,
        "turning_negative": macd_turning_negative,
        "sell_signal": macd_sell
    },
    "bollinger": {
        "current_price": current_price,
        "upper_band": upper,
        "middle_band": middle,
        "lower_band": lower,
        "sell_signal": bb_sell
    }
}

result = {
    "signal_count": signal_count,
    "sell_signal": sell_signal,
    "sell_strength": sell_strength,
    "details": details
}
```

### 3.1.2 이동평균 교차 + 패턴 인식 복합 매도 전략

```python
# 이동평균 교차 + 패턴 인식 복합 매도 전략
dy = ChartManager('dy')

# 매개변수
short_ma = kwargs.get('short_ma', 5)
medium_ma = kwargs.get('medium_ma', 20)
long_ma = kwargs.get('long_ma', 60)
min_signals = kwargs.get('min_signals', 2)  # 최소 매도 신호 수

# 현재 가격
current_price = dy.c(code)

# 1. 이동평균 교차 확인
ma_short = dy.ma(code, dy.c, short_ma)
ma_medium = dy.ma(code, dy.c, medium_ma)
ma_long = dy.ma(code, dy.c, long_ma)

# 데스 크로스 확인 (단기 이평선이 중기 이평선을 하향 돌파)
death_cross = dy.cross_down(code, 
    lambda c, n: dy.ma(c, dy.c, short_ma, n),
    lambda c, n: dy.ma(c, dy.c, medium_ma, n))

# 이동평균 하락 배열 확인
bearish_alignment = ma_short < ma_medium < ma_long

# 이동평균 신호 조합
ma_sell = death_cross or bearish_alignment

# 2. 캔들 패턴 확인
# 2.1 상승 고갈 패턴 (캔들 크기 감소)
candle_sizes = []
for i in range(5):
    candle_size = abs(dy.c(code, i) - dy.o(code, i))
    candle_sizes.append(candle_size)

diminishing_candles = all(candle_sizes[i] > candle_sizes[i-1] for i in range(1, 5))

# 2.2 하락 캔들 연속 확인
bearish_candles = 0
for i in range(3):
    if dy.c(code, i) < dy.o(code, i):
        bearish_candles += 1

# 2.3 도지 캔들 확인 (몸통이 작은 캔들)
doji = abs(dy.c(code) - dy.o(code)) / (dy.h(code) - dy.l(code)) < 0.1 if (dy.h(code) - dy.l(code)) > 0 else False

# 캔들 패턴 신호 조합
candle_sell = diminishing_candles or bearish_candles >= 2 or doji

# 3. 거래량 확인
# 3.1 거래량 감소 추세
volume_decline = dy.v(code) < dy.avg(code, dy.v, 5)

# 3.2 거래량 이상치 (평균의 2배 이상)
volume_spike = dy.v(code) > dy.avg(code, dy.v, 20) * 2

# 거래량 신호 조합
volume_sell = volume_decline or volume_spike

# 매도 신호 카운트
sell_signals = [ma_sell, candle_sell, volume_sell]
signal_count = sum(sell_signals)

# 최종 매도 신호: 최소 N개 이상의 지표가 매도 신호 발생
sell_signal = signal_count >= min_signals

# 매도 강도 (0-100%)
sell_strength = (signal_count / len(sell_signals)) * 100

# 시장 환경 평가
if ma_short < ma_medium and ma_medium < ma_long:
    market_condition = "약세장"
elif ma_short < ma_medium and ma_medium > ma_long:
    market_condition = "약세 전환 중"
elif ma_short > ma_medium and ma_medium < ma_long:
    market_condition = "강세 전환 중"
else:
    market_condition = "강세장"

result = {
    "current_price": current_price,
    "market_condition": market_condition,
    "ma_signals": {
        "death_cross": death_cross,
        "bearish_alignment": bearish_alignment,
        "sell_signal": ma_sell
    },
    "candle_signals": {
        "diminishing_candles": diminishing_candles,
        "bearish_candles": bearish_candles,
        "doji": doji,
        "sell_signal": candle_sell
    },
    "volume_signals": {
        "volume_decline": volume_decline,
        "volume_spike": volume_spike,
        "sell_signal": volume_sell
    },
    "signal_count": signal_count,
    "sell_strength": sell_strength,
    "sell_signal": sell_signal
}
```

### 3.1.3 점수 기반 복합 매도 전략

```python
# 점수 기반 복합 매도 전략
dy = ChartManager('dy')

# 매개변수
threshold = kwargs.get('threshold', 70)  # 매도 임계값 (0-100)

# 점수 초기화 (0-100)
total_score = 0
max_score = 0

# 1. 이동평균 분석 (최대 30점)
weight = 30
max_score += weight

ma5 = dy.ma(code, dy.c, 5)
ma20 = dy.ma(code, dy.c, 20)
ma60 = dy.ma(code, dy.c, 60)
current_price = dy.c(code)

# 이동평균 배열 점수
if ma5 < ma20 < ma60:
    total_score += weight  # 완벽한 하락 배열
elif ma5 < ma20:
    total_score += weight * 0.7  # 단기 하락 배열
elif current_price < ma20:
    total_score += weight * 0.4  # 중기선 아래

# 2. RSI 분석 (최대 20점)
weight = 20
max_score += weight

rsi = dy.rsi(code, 14)
prev_rsi = dy.rsi(code, 14, 1)

# RSI 점수
if rsi > 70:
    total_score += weight  # 과매수
elif rsi > 60:
    total_score += weight * 0.7  # 매수세 강함
elif rsi > prev_rsi and rsi > 50:
    total_score += weight * 0.3  # 상승 중이지만 아직 높지 않음

# 3. 볼린저 밴드 분석 (최대 20점)
weight = 20
max_score += weight

upper, middle, lower = dy.bollinger_bands(code, 20, 2)
bandwidth = (upper - lower) / middle if middle > 0 else 0

# 볼린저 밴드 점수
if current_price > upper:
    total_score += weight  # 상단 밴드 돌파
elif current_price > middle + (upper - middle) * 0.8:
    total_score += weight * 0.8  # 상단 밴드 근접
elif current_price > middle:
    total_score += weight * 0.4  # 중간선 위

# 4. MACD 분석 (최대 15점)
weight = 15
max_score += weight

macd, signal, hist = dy.macd(code, 12, 26, 9)
prev_macd, prev_signal, prev_hist = dy.macd(code, 12, 26, 9, 1)

# MACD 점수
if macd < signal and prev_macd >= prev_signal:
    total_score += weight  # 하향 교차
elif macd < signal:
    total_score += weight * 0.6  # 시그널 아래
elif hist < 0 and prev_hist > 0:
    total_score += weight * 0.8  # 히스토그램 전환

# 5. 거래량 분석 (최대 15점)
weight = 15
max_score += weight

vol = dy.v(code)
avg_vol = dy.avg(code, dy.v, 20)

# 거래량 점수
if vol > avg_vol * 2 and current_price < dy.c(code, 1):
    total_score += weight  # 거래량 급증 + 가격 하락
elif vol > avg_vol * 1.5:
    total_score += weight * 0.7  # 거래량 증가
elif vol < avg_vol * 0.7:
    total_score += weight * 0.4  # 거래량 감소 (매수세 약화)

# 최종 점수 비율 계산
score_ratio = (total_score / max_score) * 100 if max_score > 0 else 0

# 매도 신호
sell_signal = score_ratio >= threshold

result = {
    "total_score": total_score,
    "max_score": max_score,
    "score_ratio": score_ratio,
    "threshold": threshold,
    "sell_signal": sell_signal,
    "components": {
        "moving_averages": {
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "price": current_price
        },
        "rsi": {
            "value": rsi,
            "previous": prev_rsi
        },
        "bollinger_bands": {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth
        },
        "macd": {
            "macd": macd,
            "signal": signal,
            "histogram": hist
        },
        "volume": {
            "current": vol,
            "average": avg_vol,
            "ratio": vol / avg_vol if avg_vol > 0 else 0
        }
    }
}
```

## 3.2 상황별 매도 전략

시장 상황과 자산별 특성에 따라 다른 매도 전략을 적용하는 것이 효과적입니다. 다음은 다양한 상황에 적합한 매도 전략을 제시합니다.

### 3.2.1 조기 수익 확정 매도 전략 (단기 투자)

```python
# 조기 수익 확정 매도 전략 (단기 투자)
dy = ChartManager('dy')

# 매개변수
profit_target = kwargs.get('profit_target', 5.0)  # 목표 수익률 (%)
stop_loss = kwargs.get('stop_loss', 2.0)  # 손절매 수익률 (%)
day_limit = kwargs.get('day_limit', 5)  # 보유 기간 제한 (일)
entry_price = kwargs.get('entry_price', 0)  # 진입가격
entry_date = kwargs.get('entry_date', '')  # 진입일자 (YYYYMMDD)

# 진입가격이 제공되지 않은 경우 이전 주기 종가 사용
if entry_price == 0:
    entry_price = dy.c(code, 1)

# 진입일자가 제공되지 않은 경우 이전 주기 날짜로 가정
if entry_date == '':
    # 실제 구현에서는 이전 날짜를 적절히 구해야 함
    entry_date = '20230101'  # 임의의 날짜

# 현재가격
current_price = dy.c(code)

# 현재 날짜
current_date = dy.today()

# 수익률 계산
profit_pct = (current_price - entry_price) / entry_price * 100

# 보유 기간 계산 (실제 구현에서는 날짜 차이를 계산해야 함)
days_held = 3  # 예시 값 (실제로는 current_date와 entry_date 차이로 계산)

# 매도 조건 확인
profit_target_reached = profit_pct >= profit_target
stop_loss_triggered = profit_pct <= -stop_loss
time_limit_reached = days_held >= day_limit

# 매도 신호
sell_signal = profit_target_reached or stop_loss_triggered or time_limit_reached

# 매도 이유
sell_reason = ""
if profit_target_reached:
    sell_reason = "목표 수익 달성"
elif stop_loss_triggered:
    sell_reason = "손절매 실행"
elif time_limit_reached:
    sell_reason = "보유 기간 초과"

result = {
    "entry_price": entry_price,
    "current_price": current_price,
    "profit_pct": profit_pct,
    "days_held": days_held,
    "profit_target_reached": profit_target_reached,
    "stop_loss_triggered": stop_loss_triggered,
    "time_limit_reached": time_limit_reached,
    "sell_signal": sell_signal,
    "sell_reason": sell_reason
}
```

### 3.2.2 추세 전환 매도 전략 (중장기 투자)

```python
# 추세 전환 매도 전략 (중장기 투자)
dy = ChartManager('dy')

# 매개변수
ma_short = kwargs.get('ma_short', 20)  # 단기 이동평균
ma_long = kwargs.get('ma_long', 60)  # 장기 이동평균
rsi_period = kwargs.get('rsi_period', 14)  # RSI 기간
volume_period = kwargs.get('volume_period', 20)  # 거래량 평균 기간

# 현재가격
current_price = dy.c(code)

# 이동평균 계산
ma_short_value = dy.ma(code, dy.c, ma_short)
ma_long_value = dy.ma(code, dy.c, ma_long)

# 이전 이동평균 (5일 전)
ma_short_prev = dy.ma(code, dy.c, ma_short, 5)
ma_long_prev = dy.ma(code, dy.c, ma_long, 5)

# 이동평균 방향 변화 확인
ma_short_direction_change = (ma_short_value < ma_short_prev)
ma_long_direction_change = (ma_long_value < ma_long_prev)

# 이동평균 교차 확인
cross_down = dy.cross_down(code, 
    lambda c, n: dy.ma(c, dy.c, ma_short, n),
    lambda c, n: dy.ma(c, dy.c, ma_long, n))

# RSI 계산 및 하락 추세 확인
rsi = dy.rsi(code, rsi_period)
rsi_prev = dy.rsi(code, rsi_period, 5)
rsi_declining = rsi < rsi_prev and rsi < 70

# 거래량 변화 확인
volume = dy.v(code)
avg_volume = dy.avg(code, dy.v, volume_period)
volume_surge = volume > avg_volume * 1.5 and current_price < dy.c(code, 1)

# 추세 점수 계산 (0-100)
trend_score = 0

# 이동평균 교차 및 방향
if cross_down:
    trend_score += 40  # 가장 강한 추세 전환 신호
elif ma_short_value < ma_long_value:
    trend_score += 30  # 이미 하락 추세
elif ma_short_direction_change:
    trend_score += 20  # 단기 추세 전환

# RSI 하락
if rsi < 30:
    trend_score += 15  # 과매도 (상승 가능성)
elif rsi < 50 and rsi_declining:
    trend_score += 25  # 하락 추세
elif rsi_declining:
    trend_score += 15  # RSI 하락 중

# 거래량 급증
if volume_surge:
    trend_score += 20  # 거래량 급증 + 가격 하락

# 매도 신호 (추세 점수 50 이상)
sell_signal = trend_score >= 50

# 추세 상태 평가
if trend_score >= 75:
    trend_status = "강한 하락 추세"
elif trend_score >= 50:
    trend_status = "하락 추세 진입"
elif trend_score >= 25:
    trend_status = "약한 하락 신호"
else:
    trend_status = "추세 유지"

result = {
    "current_price": current_price,
    "ma_short": ma_short_value,
    "ma_long": ma_long_value,
    "rsi": rsi,
    "volume_ratio": volume / avg_volume if avg_volume > 0 else 0,
    "trend_score": trend_score,
    "trend_status": trend_status,
    "sell_signal": sell_signal
}
```

### 3.2.3 변동성 대응 매도 전략 (시장 급변 시)

```python
# 변동성 대응 매도 전략 (시장 급변 시)
dy = ChartManager('dy')

# 매개변수
volatility_window = kwargs.get('volatility_window', 10)  # 변동성 측정 기간
volatility_threshold = kwargs.get('volatility_threshold', 2.0)  # 정상 대비 변동성 임계값
abnormal_drop = kwargs.get('abnormal_drop', 5.0)  # 비정상적 하락률 (%)
vix_threshold = kwargs.get('vix_threshold', 25)  # VIX 임계값 (실제로는 VIX 데이터 필요)

# 현재가격
current_price = dy.c(code)

# 변동성 계산 (ATR 사용)
current_atr = dy.atr(code, volatility_window)
normal_atr = dy.atr(code, volatility_window, 20)  # 20일 전 ATR (정상 기간 가정)

# 변동성 비율
volatility_ratio = current_atr / normal_atr if normal_atr > 0 else 1.0

# 가격 급락 확인
recent_high = dy.highest(code, dy.h, 5)
drop_pct = (recent_high - current_price) / recent_high * 100 if recent_high > 0 else 0

# 거래량 급증 확인
volume = dy.v(code)
avg_volume = dy.avg(code, dy.v, 20)
volume_surge = volume > avg_volume * 2

# 이격도 계산 (20일 이동평균 대비)
ma20 = dy.ma(code, dy.c, 20)
disparity = (current_price / ma20 * 100) - 100 if ma20 > 0 else 0

# VIX 지수 수준 (실제로는 외부 데이터 필요)
vix_level = 20  # 예시 값 (실제로는 VIX 데이터 필요)

# 위험 점수 계산 (0-100)
risk_score = 0

# 변동성 요소
if volatility_ratio >= volatility_threshold:
    risk_score += 30
elif volatility_ratio >= volatility_threshold * 0.7:
    risk_score += 20

# 가격 급락 요소
if drop_pct >= abnormal_drop:
    risk_score += 30
elif drop_pct >= abnormal_drop * 0.7:
    risk_score += 20

# 거래량 요소
if volume_surge:
    risk_score += 20

# 이격도 요소
if disparity <= -10:
    risk_score += 10
elif disparity >= 15:
    risk_score += 15  # 고평가 가능성

# VIX 요소
if vix_level >= vix_threshold:
    risk_score += 10

# 매도 신호 임계값 설정 (변동성이 높을수록 낮은 임계값)
threshold = 60
if volatility_ratio >= volatility_threshold * 1.5:
    threshold = 50  # 극심한 변동성 시기에는 더 빨리 매도

# 매도 신호
sell_signal = risk_score >= threshold

# 위험 수준 평가
if risk_score >= 80:
    risk_level = "매우 높음"
elif risk_score >= 60:
    risk_level = "높음"
elif risk_score >= 40:
    risk_level = "중간"
else:
    risk_level = "낮음"

result = {
    "current_price": current_price,
    "volatility_ratio": volatility_ratio,
    "price_drop_pct": drop_pct,
    "volume_surge": volume_surge,
    "disparity": disparity,
    "vix_level": vix_level,
    "risk_score": risk_score,
    "risk_level": risk_level,
    "threshold": threshold,
    "sell_signal": sell_signal
}
```

## 3.3 멀티 타임프레임 매도 전략

여러 시간대의 데이터를 분석하여 더 종합적인 매도 결정을 내릴 수 있습니다. 멀티 타임프레임 접근법은 단기적 노이즈에 좌우되지 않는 보다 안정적인 신호를 제공합니다.

### 3.3.1 3중 타임프레임 매도 전략

```python
# 3중 타임프레임 매도 전략
dy = ChartManager('dy')    # 일봉
h4 = ChartManager('h4')    # 4시간봉
mi60 = ChartManager('mi', 60)  # 60분봉

# 매개변수
rsi_period = kwargs.get('rsi_period', 14)
ma_short = kwargs.get('ma_short', 5)
ma_long = kwargs.get('ma_long', 20)
min_signals = kwargs.get('min_signals', 2)  # 최소 매도 타임프레임 수

# 각 타임프레임별 매도 신호 확인
# 1. 일봉 분석
# 1.1 RSI 과매수
daily_rsi = dy.rsi(code, rsi_period)
daily_rsi_overbought = daily_rsi > 70

# 1.2 이동평균 데스 크로스
daily_cross_down = dy.cross_down(code, 
    lambda c, n: dy.ma(c, dy.c, ma_short, n),
    lambda c, n: dy.ma(c, dy.c, ma_long, n))

# 1.3 볼린저 밴드 상단 접촉
daily_upper, daily_middle, daily_lower = dy.bollinger_bands(code, 20, 2)
daily_price = dy.c(code)
daily_bb_top_touch = daily_price >= daily_upper

# 일봉 매도 신호
daily_sell = daily_rsi_overbought or daily_cross_down or daily_bb_top_touch

# 2. 4시간봉 분석
# 2.1 RSI 과매수
h4_rsi = h4.rsi(code, rsi_period)
h4_rsi_overbought = h4_rsi > 70

# 2.2 이동평균 데스 크로스
h4_cross_down = h4.cross_down(code, 
    lambda c, n: h4.ma(c, h4.c, ma_short, n),
    lambda c, n: h4.ma(c, h4.c, ma_long, n))

# 2.3 볼린저 밴드 상단 접촉
h4_upper, h4_middle, h4_lower = h4.bollinger_bands(code, 20, 2)
h4_price = h4.c(code)
h4_bb_top_touch = h4_price >= h4_upper

# 4시간봉 매도 신호
h4_sell = h4_rsi_overbought or h4_cross_down or h4_bb_top_touch

# 3. 60분봉 분석
# 3.1 RSI 과매수
mi60_rsi = mi60.rsi(code, rsi_period)
mi60_rsi_overbought = mi60_rsi > 70

# 3.2 이동평균 데스 크로스
mi60_cross_down = mi60.cross_down(code, 
    lambda c, n: mi60.ma(c, mi60.c, ma_short, n),
    lambda c, n: mi60.ma(c, mi60.c, ma_long, n))

# 3.3 볼린저 밴드 상단 접촉
mi60_upper, mi60_middle, mi60_lower = mi60.bollinger_bands(code, 20, 2)
mi60_price = mi60.c(code)
mi60_bb_top_touch = mi60_price >= mi60_upper

# 60분봉 매도 신호
mi60_sell = mi60_rsi_overbought or mi60_cross_down or mi60_bb_top_touch

# 타임프레임별 가중치 (일봉 > 4시간봉 > 60분봉)
daily_weight = 0.5
h4_weight = 0.3
mi60_weight = 0.2

# 가중 매도 점수 계산
sell_score = (daily_sell * daily_weight) + (h4_sell * h4_weight) + (mi60_sell * mi60_weight)

# 매도 신호 카운트
sell_signals = [daily_sell, h4_sell, mi60_sell]
signal_count = sum(sell_signals)

# 최종 매도 신호: 최소 N개 이상의 타임프레임에서 매도 신호 발생 또는 가중 점수가 0.6 이상
sell_signal = signal_count >= min_signals or sell_score >= 0.6

result = {
    "daily": {
        "price": daily_price,
        "rsi": daily_rsi,
        "rsi_overbought": daily_rsi_overbought,
        "cross_down": daily_cross_down,
        "bb_top_touch": daily_bb_top_touch,
        "sell_signal": daily_sell
    },
    "h4": {
        "price": h4_price,
        "rsi": h4_rsi,
        "rsi_overbought": h4_rsi_overbought,
        "cross_down": h4_cross_down,
        "bb_top_touch": h4_bb_top_touch,
        "sell_signal": h4_sell
    },
    "mi60": {
        "price": mi60_price,
        "rsi": mi60_rsi,
        "rsi_overbought": mi60_rsi_overbought,
        "cross_down": mi60_cross_down,
        "bb_top_touch": mi60_bb_top_touch,
        "sell_signal": mi60_sell
    },
    "signal_count": signal_count,
    "sell_score": sell_score,
    "sell_signal": sell_signal
}
```

# 매도 전략 4장: 실전 포트폴리오 매도 관리

## 4.1 포트폴리오 밸런싱 매도 전략

포트폴리오 균형을 유지하기 위한 전략적 매도는 장기적인 자산 관리에 중요한 요소입니다. 이 전략들은 자산 배분과 위험 관리에 초점을 맞춥니다.

### 4.1.1 자산 비중 재조정 매도 전략

```python
# 자산 비중 재조정 매도 전략
dy = ChartManager('dy')

# 매개변수
portfolio = kwargs.get('portfolio', {})  # {종목코드: 보유비중(%) 또는 보유금액}
target_weights = kwargs.get('target_weights', {})  # {종목코드: 목표비중(%)}
rebalance_threshold = kwargs.get('rebalance_threshold', 5.0)  # 재조정 임계값(%)

# 현재 종목의 정보
current_price = dy.c(code)
current_weight = portfolio.get(code, 0)  # 현재 비중

# 목표 비중
target_weight = target_weights.get(code, 0)

# 비중 차이 계산
weight_diff = current_weight - target_weight

# 매도 조건: 현재 비중이 목표 비중보다 rebalance_threshold% 이상 높을 때
sell_signal = weight_diff >= rebalance_threshold

# 매도 비율 계산 (초과 비중)
sell_ratio = weight_diff / current_weight if current_weight > 0 else 0

# 재조정 후 예상 비중
expected_weight = current_weight - (sell_ratio * current_weight) if sell_signal else current_weight

result = {
    "current_price": current_price,
    "current_weight": current_weight,
    "target_weight": target_weight,
    "weight_diff": weight_diff,
    "rebalance_threshold": rebalance_threshold,
    "sell_signal": sell_signal,
    "sell_ratio": sell_ratio,
    "expected_weight": expected_weight
}
```

### 4.1.2 섹터 집중도 관리 매도 전략

```python
# 섹터 집중도 관리 매도 전략
dy = ChartManager('dy')

# 매개변수
sector_allocation = kwargs.get('sector_allocation', {})  # {섹터: 현재비중(%)}
sector_targets = kwargs.get('sector_targets', {})  # {섹터: 목표비중(%)}
stock_sectors = kwargs.get('stock_sectors', {})  # {종목코드: 소속섹터}
max_sector_weight = kwargs.get('max_sector_weight', 30.0)  # 최대 섹터 비중(%)
stock_weight = kwargs.get('stock_weight', 5.0)  # 현재 종목 비중(%)

# 현재 종목의 섹터
current_sector = stock_sectors.get(code, "")

# 현재 섹터의 비중 및 목표
current_sector_weight = sector_allocation.get(current_sector, 0)
target_sector_weight = sector_targets.get(current_sector, 0)

# 현재가격
current_price = dy.c(code)

# 섹터 초과 비중 계산
sector_overweight = current_sector_weight - target_sector_weight

# 섹터 집중도 검사 (현재 섹터 비중이 목표 또는 최대치를 초과하는지)
sector_overallocated = sector_overweight > 0 or current_sector_weight > max_sector_weight

# 매도 신호: 섹터 초과 배분 + 종목 비중이 충분히 큼
sell_signal = sector_overallocated and stock_weight > 2.0

# 매도 우선순위 점수 (0-100)
if sell_signal:
    # 섹터 초과 비중 + 종목 비중 고려한 점수
    priority_score = min(100, (sector_overweight * 2) + (stock_weight * 4))
else:
    priority_score = 0

result = {
    "current_price": current_price,
    "stock_weight": stock_weight,
    "sector": current_sector,
    "sector_weight": current_sector_weight,
    "target_sector_weight": target_sector_weight,
    "sector_overweight": sector_overweight,
    "sector_overallocated": sector_overallocated,
    "sell_signal": sell_signal,
    "priority_score": priority_score
}
```

### 4.1.3 상관관계 분산 매도 전략

```python
# 상관관계 분산 매도 전략
dy = ChartManager('dy')

# 매개변수
correlations = kwargs.get('correlations', {})  # {종목코드: [다른 종목과의 상관계수 리스트]}
max_avg_correlation = kwargs.get('max_avg_correlation', 0.6)  # 최대 평균 상관계수
min_stocks_to_keep = kwargs.get('min_stocks_to_keep', 5)  # 최소 유지 종목 수
portfolio_stocks = kwargs.get('portfolio_stocks', [])  # 포트폴리오 내 종목 리스트
portfolio_size = len(portfolio_stocks)

# 현재 종목의 상관관계 리스트
stock_correlations = correlations.get(code, [])

# 평균 상관계수 계산
avg_correlation = sum(stock_correlations) / len(stock_correlations) if stock_correlations else 0

# 상관관계 점수 (0-100, 높을수록 상관성 높음)
correlation_score = min(100, avg_correlation * 100)

# 매도 조건: 평균 상관계수가 임계값 이상이고 포트폴리오에 충분한 종목이 있을 때
sell_signal = avg_correlation > max_avg_correlation and portfolio_size > min_stocks_to_keep

result = {
    "avg_correlation": avg_correlation,
    "correlation_score": correlation_score,
    "max_avg_correlation": max_avg_correlation,
    "portfolio_size": portfolio_size,
    "min_stocks_to_keep": min_stocks_to_keep,
    "sell_signal": sell_signal
}
```

## 4.2 카테고리별 매도 전략

종목 유형과 시장 특성에 따라 차별화된 매도 전략을 적용하면 각 카테고리의 특성에 맞는 최적의 결정을 할 수 있습니다.

### 4.2.1 성장주 매도 전략

```python
# 성장주 매도 전략
dy = ChartManager('dy')

# 매개변수
growth_threshold = kwargs.get('growth_threshold', 30)  # 성장률 임계값 (%)
pe_warning = kwargs.get('pe_warning', 50)  # 경고 P/E 레벨
pe_max = kwargs.get('pe_max', 80)  # 최대 허용 P/E
revenue_growth = kwargs.get('revenue_growth', 0)  # 매출 성장률 (%)
earnings_growth = kwargs.get('earnings_growth', 0)  # 순이익 성장률 (%)
pe_ratio = kwargs.get('pe_ratio', 0)  # 현재 P/E

# 현재가격
current_price = dy.c(code)

# 이동평균 계산
ma20 = dy.ma(code, dy.c, 20)
ma50 = dy.ma(code, dy.c, 50)
ma200 = dy.ma(code, dy.c, 200)

# 기술적 매도 신호 확인
# 1. 200일선 하향 돌파
ma200_breakdown = dy.cross_down(code,
    lambda c, n: dy.c(c, n),
    lambda c, n: dy.ma(c, dy.c, 200, n))

# 2. 50일선 하향 돌파 (약한 신호)
ma50_breakdown = dy.cross_down(code,
    lambda c, n: dy.c(c, n),
    lambda c, n: dy.ma(c, dy.c, 50, n))

# 3. 20일선 하향 돌파 (단기 신호)
ma20_breakdown = dy.cross_down(code,
    lambda c, n: dy.c(c, n),
    lambda c, n: dy.ma(c, dy.c, 20, n))

# 4. RSI 과매수 및 하락 전환
rsi = dy.rsi(code, 14)
prev_rsi = dy.rsi(code, 14, 1)
rsi_sell = rsi < prev_rsi and prev_rsi > 70

# 기술적 위험 점수 (0-100)
technical_risk = 0
if ma200_breakdown:
    technical_risk += 40  # 강한 하락 신호
elif ma50_breakdown:
    technical_risk += 30  # 중기 하락 신호
elif ma20_breakdown:
    technical_risk += 20  # 단기 하락 신호

if rsi_sell:
    technical_risk += 30  # RSI 하락 전환

# 기본적 위험 점수 (0-100)
fundamental_risk = 0

# 1. 성장률 하락
if revenue_growth < growth_threshold / 2:
    fundamental_risk += 30
elif revenue_growth < growth_threshold:
    fundamental_risk += 20

if earnings_growth < growth_threshold / 2:
    fundamental_risk += 30
elif earnings_growth < growth_threshold:
    fundamental_risk += 20

# 2. 밸류에이션 경고
if pe_ratio > pe_max:
    fundamental_risk += 40  # 심각한 고평가
elif pe_ratio > pe_warning:
    fundamental_risk += 25  # 경고 수준

# 종합 위험 점수 (0-100)
total_risk = (technical_risk * 0.5) + (fundamental_risk * 0.5)

# 매도 신호 임계값
threshold = 50

# 매도 신호
sell_signal = total_risk >= threshold

# 매도 이유 결정
sell_reason = ""
if sell_signal:
    if technical_risk >= 40 and fundamental_risk >= 40:
        sell_reason = "기술적 및 기본적 지표 모두 악화"
    elif technical_risk >= 40:
        sell_reason = "주요 기술적 지표 악화"
    elif fundamental_risk >= 40:
        sell_reason = "주요 기본적 지표 악화"
    else:
        sell_reason = "복합적 위험 신호"

result = {
    "current_price": current_price,
    "technical_risk": technical_risk,
    "fundamental_risk": fundamental_risk,
    "total_risk": total_risk,
    "threshold": threshold,
    "sell_signal": sell_signal,
    "sell_reason": sell_reason,
    "details": {
        "ma_signals": {
            "ma20_breakdown": ma20_breakdown,
            "ma50_breakdown": ma50_breakdown,
            "ma200_breakdown": ma200_breakdown
        },
        "rsi_signal": rsi_sell,
        "growth_metrics": {
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            "growth_threshold": growth_threshold
        },
        "valuation": {
            "pe_ratio": pe_ratio,
            "pe_warning": pe_warning,
            "pe_max": pe_max
        }
    }
}
```

### 4.2.2 가치주 매도 전략

```python
# 가치주 매도 전략
dy = ChartManager('dy')

# 매개변수
pb_threshold = kwargs.get('pb_threshold', 1.5)  # P/B 임계값
pe_threshold = kwargs.get('pe_threshold', 15)  # P/E 임계값
dividend_min = kwargs.get('dividend_min', 2.0)  # 최소 배당률 (%)
roe_min = kwargs.get('roe_min', 5.0)  # 최소 ROE (%)
pb_ratio = kwargs.get('pb_ratio', 0)  # 현재 P/B
pe_ratio = kwargs.get('pe_ratio', 0)  # 현재 P/E
dividend_yield = kwargs.get('dividend_yield', 0)  # 현재 배당률 (%)
roe = kwargs.get('roe', 0)  # 현재 ROE (%)

# 현재가격
current_price = dy.c(code)

# 기본적 매도 신호 확인
# 1. 밸류에이션 상승
valuation_high = pb_ratio > pb_threshold or pe_ratio > pe_threshold

# 2. 배당률 하락
dividend_low = dividend_yield < dividend_min

# 3. ROE 하락
roe_low = roe < roe_min

# 기술적 매도 신호 확인
# 1. 20일 이동평균 하향 돌파
ma20 = dy.ma(code, dy.c, 20)
ma20_breakdown = dy.cross_down(code,
    lambda c, n: dy.c(c, n),
    lambda c, n: dy.ma(c, dy.c, 20, n))

# 2. 최근 고점에서 10% 이상 하락
recent_high = dy.highest(code, dy.h, 20)
price_drop = (recent_high - current_price) / recent_high * 100 if recent_high > 0 else 0
price_significant_drop = price_drop >= 10

# 3. 거래량 급증 확인
volume = dy.v(code)
avg_volume = dy.avg(code, dy.v, 20)
volume_surge = volume > avg_volume * 1.5 and current_price < dy.c(code, 1)

# 기본적 매도 점수 (0-100)
fundamental_risk = 0
if valuation_high:
    fundamental_risk += 40
if dividend_low:
    fundamental_risk += 30
if roe_low:
    fundamental_risk += 30

# 기술적 매도 점수 (0-100)
technical_risk = 0
if ma20_breakdown:
    technical_risk += 30
if price_significant_drop:
    technical_risk += 40
if volume_surge:
    technical_risk += 30

# 가치주 특성에 맞게 가중치 적용 (기본적 분석 중시)
total_risk = (fundamental_risk * 0.7) + (technical_risk * 0.3)

# 매도 신호 임계값
threshold = 60

# 매도 신호
sell_signal = total_risk >= threshold

# 매도 이유 결정
sell_reason = ""
if sell_signal:
    if valuation_high and (dividend_low or roe_low):
        sell_reason = "밸류에이션 상승 및 펀더멘탈 악화"
    elif valuation_high:
        sell_reason = "밸류에이션 상승"
    elif dividend_low and roe_low:
        sell_reason = "배당률 및 ROE 동시 하락"
    elif price_significant_drop:
        sell_reason = "주가 급락 (10% 이상)"
    else:
        sell_reason = "복합적 위험 신호"

result = {
    "current_price": current_price,
    "fundamental_risk": fundamental_risk,
    "technical_risk": technical_risk,
    "total_risk": total_risk,
    "threshold": threshold,
    "sell_signal": sell_signal,
    "sell_reason": sell_reason,
    "details": {
        "valuation": {
            "pb_ratio": pb_ratio,
            "pb_threshold": pb_threshold,
            "pe_ratio": pe_ratio,
            "pe_threshold": pe_threshold,
            "valuation_high": valuation_high
        },
        "fundamentals": {
            "dividend_yield": dividend_yield,
            "dividend_min": dividend_min,
            "dividend_low": dividend_low,
            "roe": roe,
            "roe_min": roe_min,
            "roe_low": roe_low
        },
        "technicals": {
            "ma20_breakdown": ma20_breakdown,
            "price_drop": price_drop,
            "price_significant_drop": price_significant_drop,
            "volume_surge": volume_surge
        }
    }
}
```

### 4.2.3 배당주 매도 전략

```python
# 배당주 매도 전략
dy = ChartManager('dy')

# 매개변수
min_dividend = kwargs.get('min_dividend', 3.0)  # 최소 배당률 (%)
max_payout = kwargs.get('max_payout', 70.0)  # 최대 배당성향 (%)
dividend_history = kwargs.get('dividend_history', [])  # 과거 배당률 [최근 -> 과거]
current_dividend = kwargs.get('current_dividend', 0)  # 현재 배당률 (%)
payout_ratio = kwargs.get('payout_ratio', 0)  # 현재 배당성향 (%)
debt_ratio = kwargs.get('debt_ratio', 0)  # 부채비율 (%)
max_debt = kwargs.get('max_debt', 150)  # 최대 허용 부채비율 (%)

# 현재가격
current_price = dy.c(code)

# 배당 관련 매도 신호 확인
# 1. 배당률 하락
dividend_declining = False
if len(dividend_history) >= 2:
    dividend_declining = current_dividend < dividend_history[0]

# 2. 최소 배당률 미달
dividend_too_low = current_dividend < min_dividend

# 3. 배당성향 과다 (수익 대비 배당 비중이 너무 높음)
payout_too_high = payout_ratio > max_payout

# 재무 관련 매도 신호 확인
# 1. 부채비율 과다
debt_too_high = debt_ratio > max_debt

# 기술적 매도 신호 확인
# 1. 50일 이동평균 하향 돌파
ma50_breakdown = dy.cross_down(code,
    lambda c, n: dy.c(c, n),
    lambda c, n: dy.ma(c, dy.c, 50, n))

# 2. 상대강도 하락
rsi = dy.rsi(code, 14)
prev_rsi = dy.rsi(code, 14, 10)  # 10일 전 RSI
rsi_declining = rsi < prev_rsi and rsi < 50

# 배당 관련 위험 점수 (0-100)
dividend_risk = 0
if dividend_declining:
    dividend_risk += 30
if dividend_too_low:
    dividend_risk += 40
if payout_too_high:
    dividend_risk += 30

# 재무 관련 위험 점수 (0-100)
financial_risk = 0
if debt_too_high:
    financial_risk += 50

# 기술적 위험 점수 (0-100)
technical_risk = 0
if ma50_breakdown:
    technical_risk += 30
if rsi_declining:
    technical_risk += 20

# 배당주 특성에 맞게 가중치 적용
total_risk = (dividend_risk * 0.5) + (financial_risk * 0.3) + (technical_risk * 0.2)

# 매도 신호 임계값
threshold = 50

# 매도 신호
sell_signal = total_risk >= threshold

# 매도 이유 결정
sell_reason = ""
if sell_signal:
    if dividend_too_low:
        sell_reason = "배당률 하락"
    elif payout_too_high and debt_too_high:
        sell_reason = "배당성향 과다 및 부채비율 증가"
    elif debt_too_high:
        sell_reason = "부채비율 증가"
    elif ma50_breakdown:
        sell_reason = "주가 추세 악화"
    else:
        sell_reason = "복합적 위험 신호"

result = {
    "current_price": current_price,
    "dividend_risk": dividend_risk,
    "financial_risk": financial_risk,
    "technical_risk": technical_risk,
    "total_risk": total_risk,
    "threshold": threshold,
    "sell_signal": sell_signal,
    "sell_reason": sell_reason,
    "details": {
        "dividend": {
            "current_dividend": current_dividend,
            "min_dividend": min_dividend,
            "dividend_declining": dividend_declining,
            "dividend_too_low": dividend_too_low
        },
        "payout": {
            "payout_ratio": payout_ratio,
            "max_payout": max_payout,
            "payout_too_high": payout_too_high
        },
        "debt": {
            "debt_ratio": debt_ratio,
            "max_debt": max_debt,
            "debt_too_high": debt_too_high
        },
        "technicals": {
            "ma50_breakdown": ma50_breakdown,
            "rsi": rsi,
            "prev_rsi": prev_rsi,
            "rsi_declining": rsi_declining
        }
    }
}
```weight - (sell_ratio * current_weight) if sell_signal else current_weight

result = {
    "current_price": current_