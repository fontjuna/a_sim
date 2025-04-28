# 투자 스크립트 작성 부록

## A. 스크립트 활용 예제 모음

### A.1 캔들 패턴 인식 스크립트

```python
# 세 개의 백색 병사(Three White Soldiers) 패턴 감지
dy = ChartManager('dy')

# 세 개의 연속적인 양봉 확인
candle1 = dy.c(code, 2) > dy.o(code, 2)
candle2 = dy.c(code, 1) > dy.o(code, 1)
candle3 = dy.c(code) > dy.o(code)

# 종가가 상승하는지 확인
price_rising = dy.c(code, 2) < dy.c(code, 1) < dy.c(code)

# 각 봉의 몸통이 일정 크기 이상인지 확인
min_body_size = kwargs.get('min_body_size', 0.01)  # 기본값 1%
body1 = (dy.c(code, 2) - dy.o(code, 2)) / dy.o(code, 2)
body2 = (dy.c(code, 1) - dy.o(code, 1)) / dy.o(code, 1)
body3 = (dy.c(code) - dy.o(code)) / dy.o(code)

bodies_ok = body1 > min_body_size and body2 > min_body_size and body3 > min_body_size

# 패턴 확인
result = candle1 and candle2 and candle3 and price_rising and bodies_ok
```

### A.2 트레일링 스탑 계산

```python
# 트레일링 스탑 계산
dy = ChartManager('dy')

# 매개변수
atr_period = kwargs.get('atr_period', 14)
atr_multiplier = kwargs.get('atr_multiplier', 2.0)

# ATR 계산
current_atr = dy.atr(code, atr_period)

# 현재가
current_price = dy.c(code)

# 최근 N봉 중 최고가
lookback = kwargs.get('lookback', 20)
highest_price = dy.highest(code, dy.h, lookback)

# 트레일링 스탑 계산
trailing_stop = highest_price - (current_atr * atr_multiplier)

# 현재가와 트레일링 스탑 비교
result = {
    "current_price": current_price,
    "highest_price": highest_price,
    "atr": current_atr,
    "trailing_stop": trailing_stop,
    "sell_signal": current_price < trailing_stop
}
```

### A.3 섹터 상대 강도 계산

```python
# 해당 종목이 섹터 내에서 상대적 강도 계산
dy = ChartManager('dy')

# 비교 기간
period = kwargs.get('period', 20)

# 종목 수익률 계산
stock_return = (dy.c(code) / dy.c(code, period) - 1) * 100

# 섹터 종목 코드 리스트 (kwargs로 전달 필요)
sector_codes = kwargs.get('sector_codes', [])

# 섹터 내 다른 종목들의 수익률 계산
sector_returns = []
for sector_code in sector_codes:
    if sector_code != code:  # 자기 자신 제외
        try:
            other_return = (dy.c(sector_code) / dy.c(sector_code, period) - 1) * 100
            sector_returns.append(other_return)
        except:
            pass  # 오류 발생 시 (데이터 없음 등) 건너뛰기

# 섹터 평균 수익률 계산
avg_sector_return = sum(sector_returns) / len(sector_returns) if sector_returns else 0

# 상대 강도 (종목 수익률 - 섹터 평균 수익률)
relative_strength = stock_return - avg_sector_return

# 상위 몇 %에 속하는지 계산
all_returns = sector_returns + [stock_return]
all_returns.sort(reverse=True)  # 내림차순 정렬
rank = all_returns.index(stock_return) + 1
percentile = (rank / len(all_returns)) * 100

result = {
    "stock_return": stock_return,
    "sector_avg_return": avg_sector_return,
    "relative_strength": relative_strength,
    "percentile": percentile,
    "is_outperforming": stock_return > avg_sector_return
}
```

### A.4 패턴 기반 지지/저항선 탐지

```python
# 과거 데이터에서 지지/저항 수준 찾기
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 100)  # 분석할 과거 봉 수
min_touches = kwargs.get('min_touches', 3)  # 최소 터치 수
proximity_percent = kwargs.get('proximity_percent', 1.0)  # 근접 비율 (%)

# 고가 및 저가 수집
highs = [dy.h(code, i) for i in range(lookback)]
lows = [dy.l(code, i) for i in range(lookback)]

# 잠재적 저항 수준 찾기 (고가 기준)
resistance_levels = {}
for price in highs:
    # 근접 범위 계산
    proximity = price * proximity_percent / 100
    lower_bound = price - proximity
    upper_bound = price + proximity
    
    # 근접 범위 내 고가 카운트
    touches = sum(1 for h in highs if lower_bound <= h <= upper_bound)
    
    if touches >= min_touches:
        # 대표 가격으로 평균 사용
        avg_price = sum([h for h in highs if lower_bound <= h <= upper_bound]) / touches
        resistance_levels[avg_price] = touches

# 잠재적 지지 수준 찾기 (저가 기준)
support_levels = {}
for price in lows:
    # 근접 범위 계산
    proximity = price * proximity_percent / 100
    lower_bound = price - proximity
    upper_bound = price + proximity
    
    # 근접 범위 내 저가 카운트
    touches = sum(1 for l in lows if lower_bound <= l <= upper_bound)
    
    if touches >= min_touches:
        # 대표 가격으로 평균 사용
        avg_price = sum([l for l in lows if lower_bound <= l <= upper_bound]) / touches
        support_levels[avg_price] = touches

# 현재가 계산
current_price = dy.c(code)

# 결과 구성 (수준별 정렬)
sorted_resistance = sorted([(price, touches) for price, touches in resistance_levels.items()])
sorted_support = sorted([(price, touches) for price, touches in support_levels.items()])

# 현재가에서 가장 가까운 지지/저항 수준 찾기
nearest_resistance = None
nearest_support = None

for price, touches in sorted_resistance:
    if price > current_price:
        nearest_resistance = {"price": price, "touches": touches}
        break

for price, touches in reversed(sorted_support):
    if price < current_price:
        nearest_support = {"price": price, "touches": touches}
        break

result = {
    "current_price": current_price,
    "nearest_support": nearest_support,
    "nearest_resistance": nearest_resistance,
    "all_support_levels": sorted_support,
    "all_resistance_levels": sorted_resistance
}
```

### A.5 시간대별 승률 분석

```python
# 특정 시간대별 상승/하락 승률 분석
mi = ChartManager('mi')  # 분봉 차트

# 매개변수
days_to_analyze = kwargs.get('days', 20)  # 분석할 일수
target_hour = kwargs.get('hour', 9)  # 분석할 시간대 (9시, 10시 등)
target_minute = kwargs.get('minute', 0)  # 분석할 분 (0, 30 등)
hold_minutes = kwargs.get('hold_minutes', 30)  # 보유 시간 (분)

# 결과 저장용
wins = 0
losses = 0
total_return = 0

# 현재 날짜
today = mi.today()
today_year = int(today[:4])
today_month = int(today[4:6])
today_day = int(today[6:])

# 각 봉마다 분석
current_day = ""
for i in range(5000):  # 충분히 큰 수로 과거 데이터 검색
    try:
        # 시간 확인
        time_str = mi.time(code, i)
        if not time_str:
            continue
        
        hour = int(time_str[:2])
        minute = int(time_str[2:4])
        
        # 날짜 확인 (날짜가 변경되었는지)
        current_date = mi.date(code, i) if hasattr(mi, 'date') else ""
        if current_date and current_date != current_day:
            current_day = current_date
            days_to_analyze -= 1
            if days_to_analyze <= 0:
                break
        
        # 목표 시간대가 아니면 건너뛰기
        if hour != target_hour or minute != target_minute:
            continue
        
        # 진입가
        entry_price = mi.c(code, i)
        
        # hold_minutes 후의 가격
        exit_idx = i - hold_minutes  # 과거 데이터를 거꾸로 탐색하므로 빼기
        if exit_idx < 0:
            continue
            
        exit_price = mi.c(code, exit_idx)
        
        # 수익률 계산
        pct_change = (exit_price / entry_price - 1) * 100
        total_return += pct_change
        
        # 승/패 카운트
        if exit_price > entry_price:
            wins += 1
        else:
            losses += 1
            
    except Exception as e:
        # 오류 발생 시 (데이터 없음 등) 건너뛰기
        continue

# 결과 계산
total_trades = wins + losses
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
avg_return = total_return / total_trades if total_trades > 0 else 0

result = {
    "time": f"{target_hour:02d}:{target_minute:02d}",
    "hold_minutes": hold_minutes,
    "total_trades": total_trades,
    "wins": wins,
    "losses": losses,
    "win_rate": win_rate,
    "total_return": total_return,
    "avg_return": avg_return
}
```

## B. 스크립트 설계 패턴

### B.1 모듈화 패턴

복잡한 전략을 여러 스크립트로 분리하여 재사용성을 높이는 패턴입니다.

```python
# 메인 스크립트 (여러 하위 스크립트 호출)
# 1. 추세 확인
trend = market_trend(code)

# 2. 진입 시그널 확인
entry_signal = False
if trend == "상승":
    entry_signal = bullish_entry_signal(code)
elif trend == "하락":
    entry_signal = bearish_entry_signal(code)

# 3. 리스크 관리 확인
risk_ok = risk_check(code)

# 4. 최종 매매 신호
result = entry_signal and risk_ok
```

### B.2 필터 체인 패턴

여러 조건을 순차적으로 확인하여 모든 조건을 만족해야 신호를 생성하는 패턴입니다.

```python
# 필터 체인 패턴
# 1. 시장 환경 필터
market_ok = market_condition(code)
if not market_ok:
    result = False
    # 함수 종료
    return

# 2. 기술적 지표 필터
indicators_ok = check_indicators(code)
if not indicators_ok:
    result = False
    return

# 3. 캔들 패턴 필터
pattern_ok = check_candle_patterns(code)
if not pattern_ok:
    result = False
    return

# 4. 거래량 필터
volume_ok = check_volume(code)
if not volume_ok:
    result = False
    return

# 모든 필터 통과
result = True
```

### B.3 가중 점수 패턴

여러 조건에 가중치를 부여하고 총점이 임계값을 넘으면 신호를 생성하는 패턴입니다.

```python
# 가중 점수 패턴
dy = ChartManager('dy')

total_score = 0
max_score = 0

# 1. 이동평균선 배열 (가중치: 30)
weight = 30
max_score += weight
ma5 = dy.ma(code, dy.c, 5)
ma20 = dy.ma(code, dy.c, 20)
ma60 = dy.ma(code, dy.c, 60)

if ma5 > ma20 > ma60:
    total_score += weight  # 완벽한 상승 배열
elif ma5 > ma20:
    total_score += weight * 0.6  # 단기 상승 배열

# 2. RSI 지표 (가중치: 20)
weight = 20
max_score += weight
rsi = dy.rsi(code, 14)

if 40 <= rsi <= 60:  # 중립 구간
    total_score += weight * 0.5
elif 60 < rsi < 70:  # 강세 구간 (과매수 직전)
    total_score += weight
elif rsi >= 70:  # 과매수 구간
    total_score += weight * 0.3

# 3. 볼린저 밴드 위치 (가중치: 25)
weight = 25
max_score += weight
upper, middle, lower = dy.bollinger_bands(code, 20, 2)
price = dy.c(code)

band_ratio = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
if 0.3 <= band_ratio <= 0.7:  # 밴드 중간 구간
    total_score += weight
elif band_ratio < 0.3:  # 하단 밴드 근처 (과매도)
    total_score += weight * 0.8
elif band_ratio > 0.7:  # 상단 밴드 근처 (과매수)
    total_score += weight * 0.4

# 4. 거래량 증가 (가중치: 25)
weight = 25
max_score += weight
vol_ratio = dy.v(code) / dy.avg(code, dy.v, 20)

if vol_ratio >= 2.0:  # 평균 대비 2배 이상
    total_score += weight
elif vol_ratio >= 1.5:  # 평균 대비 1.5배 이상
    total_score += weight * 0.8
elif vol_ratio >= 1.0:  # 평균 이상
    total_score += weight * 0.5

# 최종 점수 비율 계산
score_ratio = total_score / max_score if max_score > 0 else 0
threshold = kwargs.get('threshold', 0.7)  # 기본 임계값 70%

result = {
    "score": total_score,
    "max_score": max_score,
    "score_ratio": score_ratio,
    "threshold": threshold,
    "signal": score_ratio >= threshold
}
```

## C. 고급 스크립트 예제

### C.1 기계학습 기반 이상치 탐지

```python
# 이동평균 기반 이상치 탐지
dy = ChartManager('dy')

# 매개변수
window = kwargs.get('window', 20)  # 분석 기간
z_threshold = kwargs.get('z_threshold', 2.0)  # Z-스코어 임계값

# 가격 데이터 수집
prices = [dy.c(code, i) for i in range(window)]

# 평균 및 표준편차 계산
mean = sum(prices) / len(prices)
variance = sum((x - mean) ** 2 for x in prices) / len(prices)
std_dev = variance ** 0.5

# 현재 가격의 Z-점수 계산
current_price = dy.c(code)
z_score = (current_price - mean) / std_dev if std_dev > 0 else 0

# 상승/하락 여부 확인
is_rising = dy.c(code) > dy.c(code, 1)

# 이상치 판단
is_high_outlier = z_score > z_threshold
is_low_outlier = z_score < -z_threshold

# 신호 생성
# 하락 이상치(매도 과잉) + 상승 추세 = 매수 기회
buy_signal = is_low_outlier and is_rising

# 상승 이상치(매수 과잉) + 하락 추세 = 매도 기회
sell_signal = is_high_outlier and not is_rising

result = {
    "current_price": current_price,
    "mean": mean,
    "std_dev": std_dev,
    "z_score": z_score,
    "is_high_outlier": is_high_outlier,
    "is_low_outlier": is_low_outlier,
    "buy_signal": buy_signal,
    "sell_signal": sell_signal
}
```

### C.2 멀티 타임프레임 분석

```python
# 멀티 타임프레임 분석
dy = ChartManager('dy')   # 일봉
h4 = ChartManager('h4')   # 4시간봉
mi60 = ChartManager('mi', 60)  # 60분봉

# 각 타임프레임에서 추세 분석
# 1. 일봉 추세 (가중치: 50%)
day_ma5 = dy.ma(code, dy.c, 5)
day_ma20 = dy.ma(code, dy.c, 20)
day_trend = 1 if day_ma5 > day_ma20 else (-1 if day_ma5 < day_ma20 else 0)

# 2. 4시간봉 추세 (가중치: 30%)
h4_ma5 = h4.ma(code, h4.c, 5)
h4_ma20 = h4.ma(code, h4.c, 20)
h4_trend = 1 if h4_ma5 > h4_ma20 else (-1 if h4_ma5 < h4_ma20 else 0)

# 3. 60분봉 추세 (가중치: 20%)
mi60_ma5 = mi60.ma(code, mi60.c, 5)
mi60_ma20 = mi60.ma(code, mi60.c, 20)
mi60_trend = 1 if mi60_ma5 > mi60_ma20 else (-1 if mi60_ma5 < mi60_ma20 else 0)

# 가중 평균 추세 점수 계산
trend_score = (day_trend * 0.5) + (h4_trend * 0.3) + (mi60_trend * 0.2)

# 해석
if trend_score >= 0.5:
    trend_interpretation = "강한 상승추세"
elif trend_score > 0:
    trend_interpretation = "약한 상승추세"
elif trend_score == 0:
    trend_interpretation = "중립"
elif trend_score > -0.5:
    trend_interpretation = "약한 하락추세"
else:
    trend_interpretation = "강한 하락추세"

# 매매 신호
buy_signal = trend_score > 0 and mi60_trend == 1
sell_signal = trend_score < 0 and mi60_trend == -1

result = {
    "day_trend": day_trend,
    "h4_trend": h4_trend,
    "mi60_trend": mi60_trend,
    "trend_score": trend_score,
    "interpretation": trend_interpretation,
    "buy_signal": buy_signal,
    "sell_signal": sell_signal
}
```

### C.3 계절성 분석

```python
# 요일별, 월별 계절성 분석
dy = ChartManager('dy')

# 매개변수
lookback_days = kwargs.get('lookback_days', 365)  # 분석할 일수

# 결과 저장용
day_of_week_returns = {0: [], 1: [], 2: [], 3: [], 4: []}  # 0=월요일, 4=금요일
month_returns = {i: [] for i in range(1, 13)}  # 1=1월, 12=12월

# 날짜 및 가격 데이터 수집
dates = []
prices = []

for i in range(lookback_days):
    try:
        date_str = dy.date(code, i) if hasattr(dy, 'date') else ""
        if not date_str:
            continue
            
        # 날짜 형식 변환 (YYYYMMDD -> datetime)
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:])
        
        from datetime import datetime
        date_obj = datetime(year, month, day)
        
        dates.append(date_obj)
        prices.append(dy.c(code, i))
    except:
        continue

# 날짜별 수익률 계산
day_returns = []
for i in range(1, len(prices)):
    day_return = (prices[i-1] / prices[i] - 1) * 100  # 이전 날짜 대비 수익률
    day_returns.append(day_return)
    
    # 해당 날짜의 요일 및 월 기록
    day_of_week = dates[i-1].weekday()  # 0=월요일, 6=일요일
    month = dates[i-1].month  # 1=1월, 12=12월
    
    # 결과 저장
    if 0 <= day_of_week <= 4:  # 평일만 고려
        day_of_week_returns[day_of_week].append(day_return)
    
    month_returns[month].append(day_return)

# 요일별 평균 수익률 계산
dow_avg_returns = {}
dow_names = ["월요일", "화요일", "수요일", "목요일", "금요일"]
for day, returns in day_of_week_returns.items():
    if returns:
        dow_avg_returns[dow_names[day]] = sum(returns) / len(returns)

# 월별 평균 수익률 계산
month_avg_returns = {}
month_names = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]
for month, returns in month_returns.items():
    if returns:
        month_avg_returns[month_names[month-1]] = sum(returns) / len(returns)

# 최고 수익률 요일 및 월 찾기
best_day = max(dow_avg_returns.items(), key=lambda x: x[1]) if dow_avg_returns else ("없음", 0)
worst_day = min(dow_avg_returns.items(), key=lambda x: x[1]) if dow_avg_returns else ("없음", 0)
best_month = max(month_avg_returns.items(), key=lambda x: x[1]) if month_avg_returns else ("없음", 0)
worst_month = min(month_avg_returns.items(), key=lambda x: x[1]) if month_avg_returns else ("없음", 0)

# 오늘의 요일 및 월 확인
from datetime import datetime
today = datetime.now()
today_dow = dow_names[today.weekday()] if today.weekday() < 5 else "주말"
today_month = month_names[today.month - 1]

# 오늘의 계절성 점수
today_score = 0
if today.weekday() < 5:  # 평일인 경우
    today_score += dow_avg_returns.get(today_dow, 0)
today_score += month_avg_returns.get(today_month, 0)

result = {
    "day_of_week_returns": dow_avg_returns,
    "month_returns": month_avg_returns,
    "best_day": best_day,
    "worst_day": worst_day,
    "best_month": best_month,
    "worst_month": worst_month,
    "today_day": today_dow,
    "today_month": today_month,
    "today_score": today_score,
    "seasonality_signal": today_score > 0
}
```

## D. 스크립트 성능 최적화 팁

### D.1 계산 재사용

같은 값을 여러 번 계산하지 않고 변수에 저장하여 재사용합니다.

```python
# 비효율적인 방법 (중복 계산)
if dy.ma(code, dy.c, 20) > dy.ma(code, dy.c, 50):
    if dy.ma(code, dy.c, 20) > dy.ma(code, dy.c, 100):
        result = True

# 효율적인 방법 (계산 결과 저장)
ma20 = dy.ma(code, dy.c, 20)
ma50 = dy.ma(code, dy.c, 50)
ma100 = dy.ma(code, dy.c, 100)

if ma20 > ma50:
    if ma20 > ma100:
        result = True
```

### D.2 적절한 기간 설정

너무 긴 기간을 설정하면 불필요한 계산이 많아집니다.

```python
# 과도한 기간 (비효율적)
highest_200 = dy.highest(code, dy.h, 200)

# 필요한 만큼만 설정 (효율적)
highest_20 = dy.highest(code, dy.h, 20)  # 대부분의 경우 20일 데이터로 충분
```

### D.3 조건부 실행

모든 계산을 항상 수행하지 않고, 필요한 경우에만 수행합니다.

```python
# 초기 필터링 후 계산
ma_trend = dy.ma(code, dy.c, 5) > dy.ma(code, dy.c, 20)

# 추세가 상승일 때만 복잡한 계산 수행
if ma_trend:
    # 복잡한 계산 (필터 통과 시에만 실행)
    complex_indicator = calculate_complex_indicator(code)
    result = complex_indicator > threshold
else:
    result = False
```

### D.4 배열 연산 활용

반복문보다 배열 연산을 활용하면 더 효율적입니다.

```python
# 개별 값 처리 (비효율적)
sum_of_volumes = 0
for i in range(5):
    sum_of_volumes += dy.v(code, i)

# 배열 연산 활용 (효율적)
sum_of_volumes = dy.sum(code, dy.v, 5)
```

## E. 스크립트 테스트 및 디버깅

### E.1 값 확인 및 로깅

중간 계산 값을 확인하기 위해 로깅 기능을 활용합니다.

```python
# 중간 값 로깅
logging.debug(f"MA5: {ma5}, MA20: {ma20}, 교차 여부: {ma5 > ma20}")

# 복잡한 계산 과정 로깅
rsi_value = dy.rsi(code, 14)
logging.debug(f"RSI(14): {rsi_value}, 과매수 여부: {rsi_value > 70}")
```

### E.2 스크립트 분리 테스트

복잡한 스크립트는 작은 부분으로 나누어 테스트합니다.

```python
# 각 부분 별도 테스트
# 1. 이동평균 부분
ma_test = ma5 > ma20 and ma20 > ma60
logging.debug(f"이동평균 테스트: {ma_test}")

# 2. 거래량 부분
vol_test = dy.v(code) > dy.avg(code, dy.v, 20) * 1.5
logging.debug(f"거래량 테스트: {vol_test}")

# 3. 오실레이터 부분
osc_test = dy.rsi(code, 14) < 70
logging.debug(f"오실레이터 테스트: {osc_test}")

# 최종 결합
result = ma_test and vol_test and osc_test
```

### E.3 예외 처리

데이터 부족이나 계산 오류에 대비한 예외 처리를 추가합니다.

```python
# 안전한 계산
try:
    ma5 = dy.ma(code, dy.c, 5)
    ma20 = dy.ma(code, dy.c, 20)
    
    if ma5 > 0 and ma20 > 0:
        ratio = ma5 / ma20
    else:
        ratio = 1.0  # 기본값
        
    # 0으로 나누기 방지
    volume_ratio = dy.v(code) / dy.avg(code, dy.v, 20) if dy.avg(code, dy.v, 20) > 0 else 1.0
    
    result = ratio > 1.05 and volume_ratio > 1.2
except Exception as e:
    logging.error(f"계산 오류: {e}")
    result = False  # 오류 발생 시 안전한 값 반환
```

## F. 실전 투자 스크립트 예제

### F.1 평균 회귀 전략

```python
# 평균 회귀 전략
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 20)
threshold = kwargs.get('threshold', 2.0)  # 표준편차 배수

# 볼린저 밴드 계산
upper, middle, lower = dy.bollinger_bands(code, lookback, threshold)

# 현재가 및 이전가
current_close = dy.c(code)
prev_close = dy.c(code, 1)

# 밴드 위치 계산
band_width = upper - lower
relative_position = (current_close - lower) / band_width if band_width > 0 else 0.5

# 과매도/과매수 조건
oversold = relative_position < 0.1  # 하단 밴드 근처
overbought = relative_position > 0.9  # 상단 밴드 근처

# 반전 신호 확인
reversal_from_oversold = oversold and prev_close < current_close  # 과매도에서 상승 반전
reversal_from_overbought = overbought and prev_close > current_close  # 과매수에서 하락 반전

# 추가 필터 - RSI 확인
rsi = dy.rsi(code, 14)
rsi_oversold = rsi < 30
rsi_overbought = rsi > 70

# 매수/매도 신호
buy_signal = reversal_from_oversold and rsi_oversold
sell_signal = reversal_from_overbought and rsi_overbought

# 신호 유형에 따라 결과 반환
signal_type = kwargs.get('signal_type', 'buy')
if signal_type == 'buy':
    result = buy_signal
elif signal_type == 'sell':
    result = sell_signal
else:
    result = {
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "relative_position": relative_position,
        "rsi": rsi
    }
```

### F.2 추세 추종 전략

```python
# 추세 추종 전략
dy = ChartManager('dy')

# 매개변수
fast_period = kwargs.get('fast_period', 10)
slow_period = kwargs.get('slow_period', 30)
atr_period = kwargs.get('atr_period', 14)
atr_multiplier = kwargs.get('atr_multiplier', 2.0)

# 이동평균 계산
fast_ma = dy.ma(code, dy.c, fast_period)
slow_ma = dy.ma(code, dy.c, slow_period)

# ATR 계산
atr_value = dy.atr(code, atr_period)

# 현재 추세 방향
trend_direction = 1 if fast_ma > slow_ma else -1  # 1=상승, -1=하락

# 추세 강도 계산 (이동평균 이격도)
trend_strength = abs(fast_ma - slow_ma) / slow_ma * 100 if slow_ma > 0 else 0

# 적응형 스탑로스 계산
stop_loss = dy.c(code) - (trend_direction * atr_value * atr_multiplier)

# 진입 신호 - 이동평균 교차
entry_signal = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, fast_period, n), 
    lambda c, n: dy.ma(c, dy.c, slow_period, n)
) if trend_direction > 0 else dy.cross_down(code,
    lambda c, n: dy.ma(c, dy.c, fast_period, n), 
    lambda c, n: dy.ma(c, dy.c, slow_period, n)
)

# 추가 필터 - 거래량 확인
volume_filter = dy.v(code) > dy.avg(code, dy.v, fast_period) * 1.2

# 최종 신호
result = entry_signal and volume_filter
```

### F.3 듀얼 모멘텀 전략

```python
# 듀얼 모멘텀 전략
dy = ChartManager('dy')

# 매개변수
lookback_period = kwargs.get('lookback_period', 90)  # 비교 기간(3개월)
benchmark_code = kwargs.get('benchmark_code', '069500')  # 기본 벤치마크: KODEX 200
threshold = kwargs.get('threshold', 0)  # 모멘텀 임계값

# 종목 모멘텀 (상대 모멘텀)
stock_momentum = (dy.c(code) / dy.c(code, lookback_period) - 1) * 100

# 벤치마크 모멘텀
benchmark_momentum = (dy.c(benchmark_code) / dy.c(benchmark_code, lookback_period) - 1) * 100

# 절대 모멘텀 (종목 자체의 모멘텀이 양수인지)
absolute_momentum = stock_momentum > threshold

# 상대 모멘텀 (종목이 벤치마크보다 강한지)
relative_momentum = stock_momentum > benchmark_momentum

# 듀얼 모멘텀 (절대 및 상대 모멘텀 모두 만족)
dual_momentum = absolute_momentum and relative_momentum

result = {
    "stock_momentum": stock_momentum,
    "benchmark_momentum": benchmark_momentum,
    "absolute_momentum": absolute_momentum,
    "relative_momentum": relative_momentum,
    "dual_momentum": dual_momentum
}
```

### F.4 변동성 돌파 전략

```python
# 변동성 돌파 전략 (일명 '122 전략')
dy = ChartManager('dy')

# 매개변수
k = kwargs.get('k', 0.5)  # 변동성 계수 (0.5 = 절반만큼 돌파)
target_period = kwargs.get('target_period', 1)  # 전일 기준

# 현재가
current_price = dy.c(code)

# 전일 고가, 저가, 종가
yesterday_high = dy.h(code, target_period)
yesterday_low = dy.l(code, target_period)
yesterday_close = dy.c(code, target_period)

# 전일 변동성
yesterday_range = yesterday_high - yesterday_low

# 당일 목표가 계산
target_price = yesterday_close + (yesterday_range * k)

# 돌파 여부 확인
breakout = current_price > target_price

# 추가 필터 - 이동평균 확인
ma5 = dy.ma(code, dy.c, 5)
ma20 = dy.ma(code, dy.c, 20)
trend_filter = ma5 > ma20

# 진입 신호
entry_signal = breakout and trend_filter

result = {
    "current_price": current_price,
    "yesterday_close": yesterday_close,
    "yesterday_range": yesterday_range,
    "target_price": target_price,
    "breakout": breakout,
    "trend_filter": trend_filter,
    "entry_signal": entry_signal
}
```

### F.5 다중 시간대 RSI 다이버전스 전략

```python
# 다중 시간대 RSI 다이버전스 전략
dy = ChartManager('dy')   # 일봉
h4 = ChartManager('h4')   # 4시간봉

# 매개변수
rsi_period = kwargs.get('rsi_period', 14)
lookback = kwargs.get('lookback', 20)
threshold = kwargs.get('threshold', 30)  # RSI 과매도 임계값

# 일봉 RSI
daily_rsi = dy.rsi(code, rsi_period)
daily_rsi_prev = dy.rsi(code, rsi_period, 1)

# 4시간봉 RSI
h4_rsi = h4.rsi(code, rsi_period)
h4_rsi_prev = h4.rsi(code, rsi_period, 1)

# 가격 데이터
daily_price = dy.c(code)
daily_price_prev = dy.c(code, 1)
h4_price = h4.c(code)
h4_price_prev = h4.c(code, 1)

# RSI 다이버전스 확인
# 1. 일봉 다이버전스 (가격은 하락, RSI는 상승)
daily_divergence = (daily_price < daily_price_prev) and (daily_rsi > daily_rsi_prev)

# 2. 4시간봉 다이버전스
h4_divergence = (h4_price < h4_price_prev) and (h4_rsi > h4_rsi_prev)

# 과매도 상태 확인
daily_oversold = daily_rsi < threshold
h4_oversold = h4_rsi < threshold

# 다중 시간대 다이버전스 확인
multi_timeframe_divergence = daily_divergence and h4_divergence
oversold_condition = daily_oversold or h4_oversold

# 최종 매수 신호
buy_signal = multi_timeframe_divergence and oversold_condition

result = {
    "daily_rsi": daily_rsi,
    "h4_rsi": h4_rsi,
    "daily_divergence": daily_divergence,
    "h4_divergence": h4_divergence,
    "oversold_condition": oversold_condition,
    "buy_signal": buy_signal
}
```

## G. 차트 패턴 인식 스크립트

### G.1 헤드앤숄더 패턴 감지

```python
# 헤드앤숄더 패턴 감지
dy = ChartManager('dy')

# 매개변수
lookback = kwargs.get('lookback', 40)  # 분석할 기간
threshold = kwargs.get('threshold', 0.03)  # 가격 변동 임계값 (3%)

# 최근 고점/저점 찾기
price_data = [dy.h(code, i) for i in range(lookback)]
pivot_points = []

# 피봇 포인트 탐지 (고점)
for i in range(2, lookback-2):
    if (price_data[i] > price_data[i-1] and 
        price_data[i] > price_data[i-2] and 
        price_data[i] > price_data[i+1] and 
        price_data[i] > price_data[i+2]):
        pivot_points.append((i, price_data[i], 'high'))

# 최소 5개 피봇 필요 (왼쪽 어깨, 머리, 오른쪽 어깨, 골짜기 2개)
if len(pivot_points) < 5:
    result = False
    return

# 고점 기준 정렬 및 상위 3개 선택
high_pivots = sorted([p for p in pivot_points if p[2] == 'high'], key=lambda x: x[1], reverse=True)
if len(high_pivots) < 3:
    result = False
    return

# 머리와 어깨 선택
head = high_pivots[0]
shoulders = sorted([high_pivots[1], high_pivots[2]], key=lambda x: x[0])  # 인덱스로 정렬

# 왼쪽/오른쪽 어깨 구분
left_shoulder = shoulders[0] if shoulders[0][0] < head[0] else shoulders[1]
right_shoulder = shoulders[1] if shoulders[0][0] < head[0] else shoulders[0]

# 패턴 검증
# 1. 머리는 양쪽 어깨보다 높아야 함
head_higher = (head[1] > left_shoulder[1] and head[1] > right_shoulder[1])

# 2. 왼쪽 어깨와 오른쪽 어깨의 높이가 비슷해야 함
shoulders_similar = abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1] < threshold

# 3. 머리는 시간상 두 어깨 사이에 있어야 함
head_between = (left_shoulder[0] < head[0] < right_shoulder[0])

# 4. 목선(neckline) 파악 - 어깨 사이의 최저점
left_valley_idx = max(left_shoulder[0], head[0] - (head[0] - left_shoulder[0])//2)
right_valley_idx = max(head[0], right_shoulder[0] - (right_shoulder[0] - head[0])//2)
left_valley = min([dy.l(code, i) for i in range(left_valley_idx-2, left_valley_idx+3)])
right_valley = min([dy.l(code, i) for i in range(right_valley_idx-2, right_valley_idx+3)])
neckline = (left_valley + right_valley) / 2

# 5. 현재 가격이 목선 아래로 떨어졌는지 확인 (패턴 완성)
current_price = dy.c(code)
pattern_completed = current_price < neckline

# 모든 조건 만족 여부
pattern_valid = head_higher and shoulders_similar and head_between and pattern_completed

result = {
    "pattern_valid": pattern_valid,
    "head": head,
    "left_shoulder": left_shoulder,
    "right_shoulder": right_shoulder,
    "neckline": neckline,
    "current_price": current_price,
    "sell_signal": pattern_valid  # 헤드앤숄더는 하락 신호
}
```

### G.2 다중 봉 패턴 (쓰리 인사이드 업)

```python
# 쓰리 인사이드 업 패턴 (강세반전)
dy = ChartManager('dy')

# 첫 번째 봉: 큰 음봉
candle1_bearish = dy.c(code, 2) < dy.o(code, 2)
candle1_range = dy.o(code, 2) - dy.c(code, 2)
candle1_significant = candle1_range > (dy.h(code, 2) - dy.l(code, 2)) * 0.7  # 몸통이 전체 범위의 70% 이상

# 두 번째 봉: 첫 번째 봉 내부에 위치한 양봉
candle2_bullish = dy.c(code, 1) > dy.o(code, 1)
candle2_inside = (dy.h(code, 1) <= dy.h(code, 2)) and (dy.l(code, 1) >= dy.l(code, 2))
candle2_closes_higher = dy.c(code, 1) > (dy.o(code, 2) + dy.c(code, 2)) / 2  # 중간 이상 상승

# 세 번째 봉: 두 번째 봉보다 더 올라가는 양봉
candle3_bullish = dy.c(code) > dy.o(code)
candle3_closes_higher = dy.c(code) > dy.c(code, 1)
candle3_breaks_first = dy.c(code) > dy.o(code, 2)  # 첫 번째 봉의 시가 돌파

# 패턴 확인
pattern_valid = (candle1_bearish and candle1_significant and
                candle2_bullish and candle2_inside and candle2_closes_higher and
                candle3_bullish and candle3_closes_higher and candle3_breaks_first)

# 추가 확인 - 거래량 증가
volume_increasing = dy.v(code) > dy.v(code, 1) > dy.v(code, 2)

# 최종 신호
result = pattern_valid and volume_increasing
```

## H. 주요 함수 레퍼런스

### H.1 ChartManager 함수 요약

```
# 기본 데이터 접근 함수
c(code, n=0)      - n봉 이전 종가
o(code, n=0)      - n봉 이전 시가 
h(code, n=0)      - n봉 이전 고가
l(code, n=0)      - n봉 이전 저가
v(code, n=0)      - n봉 이전 거래량
a(code, n=0)      - n봉 이전 거래대금
time(n=0)         - n봉 이전 시간 (분봉에서만 유효)
today()           - 오늘 날짜

# 이동평균 함수
ma(code, a, n, m=0, k='a')  - a의 n기간 이동평균 (m봉 이전, k는 유형)
avg(code, a, n, m=0)        - a의 n기간 단순이동평균
eavg(code, a, n, m=0)       - a의 n기간 지수이동평균
wavg(code, a, n, m=0)       - a의 n기간 가중이동평균

# 값 계산 함수
highest(code, a, n, m=0)    - a의 n기간 중 최고값
lowest(code, a, n, m=0)     - a의 n기간 중 최저값
stdev(code, a, n, m=0)      - a의 n기간 표준편차
sum(code, a, n, m=0)        - a의 n기간 합계

# 신호 함수
cross_up(code, a, b)        - a가 b를 상향돌파했는지 확인
cross_down(code, a, b)      - a가 b를 하향돌파했는지 확인
bars_since(code, condition) - 조건 만족 이후 지난 봉 수

# 기술적 지표 함수
rsi(code, period=14, m=0)                         - 상대강도지수(RSI) 
macd(code, fast=12, slow=26, signal=9, m=0)       - MACD 지표
bollinger_bands(code, period=20, std_dev=2, m=0)  - 볼린저 밴드
stochastic(code, k_period=14, d_period=3, m=0)    - 스토캐스틱 오실레이터
atr(code, period=14, m=0)                         - 평균 실제 범위(ATR)

# 캔들 패턴 함수
is_doji(code, n=0, threshold=0.1)      - n봉 이전이 도지 캔들인지 확인
is_hammer(code, n=0)                   - n봉 이전이 망치형 캔들인지 확인
is_engulfing(code, n=0, bullish=True)  - n봉 이전이 포괄 패턴인지 확인
```

### H.2 유틸리티 함수 요약

```
# 안전 반복 함수
loop(iterable, func)  - 안전한 반복 실행

# 스크립트 실행 함수
run_script(sub_name, kwargs={})  - 다른 스크립트 실행
```