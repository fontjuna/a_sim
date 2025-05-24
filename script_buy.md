# A. 매수 스크립트
## A.1 하락, 횡보 후 상승 전환
```
# 스크립트명: bullish_reversal_detector
# 상승 전환 신호 탐지기
# 하락 또는 횡보 후 상승 초입을 포착하는 스크립트

# 매개변수 설정
strength_threshold = kwargs.get('strength', 65)  # 신호 강도 임계값(0-100)
confirmation_count = kwargs.get('confirmations', 3)  # 필요한 확인 신호 개수
lookback_period = kwargs.get('lookback', 20)  # 기준 기간

# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉
h4 = ChartManager('mi', 240)  # 4시간봉
dy60 = ChartManager('mi', 60)  # 60분봉

# 감지된 상승 신호 저장 목록
bullish_signals = []
signal_strengths = []

# 1. 선행 하락/횡보 확인 (상승 초입을 판단하기 위한 전제 조건)
# 기준: 최근 20일 중 최고가 대비 5% 이상 하락 또는 ±3% 범위내 횡보

# 최근 lookback_period일 중 최고가와 최저가
recent_high = dy.highest(dy.h, lookback_period)
recent_low = dy.lowest(dy.l, lookback_period)
current_price = dy.c()

# 최고가 대비 하락률
decline_pct = (recent_high - current_price) / recent_high * 100

# 횡보 여부 - 최근 N일간 가격 범위가 ±3% 이내
is_sideways = (recent_high - recent_low) / recent_low <= 0.06

# 하락 또는 횡보 확인
prior_downtrend = decline_pct >= 5
is_valid_setup = prior_downtrend or is_sideways

if prior_downtrend:
    debug(f"선행 하락 확인: 최고가 대비 {decline_pct:.1f}% 하락")
elif is_sideways:
    debug(f"선행 횡보 확인: 최근 {lookback_period}일간 ±3% 범위 내 등락")
else:
    debug("선행 하락 또는 횡보 패턴이 확인되지 않음 (상승 초입 분석 조건 미충족)")

# 상승 초입 신호 탐색 (선행 조건이 맞을 경우)
if is_valid_setup:
    # 2. 과매도 RSI 반등
    rsi = dy.rsi(14)
    rsi_prev = dy.rsi(14, 1)
    rsi_prev2 = dy.rsi(14, 2)
    
    # RSI가 30 이하에서 상승 반전
    if rsi > rsi_prev and rsi_prev <= 30:
        bullish_signals.append("RSI 과매도 반등")
        # 반등 강도에 따른 신호 강도 계산
        rsi_bounce = rsi - rsi_prev
        rsi_strength = min(100, 50 + rsi_bounce * 10)
        signal_strengths.append(rsi_strength)
        debug(f"RSI 과매도 반등: {rsi_prev:.1f} -> {rsi:.1f} (신호 강도: {rsi_strength:.0f})")
    
    # RSI가 상승 추세로 전환 (2일 연속 상승)
    if rsi > rsi_prev and rsi_prev > rsi_prev2 and rsi_prev < 45:
        bullish_signals.append("RSI 상승 전환")
        signal_strengths.append(60)
        debug(f"RSI 상승 전환: {rsi_prev2:.1f} -> {rsi_prev:.1f} -> {rsi:.1f} (신호 강도: 60)")
    
    # 3. 볼린저 밴드 신호
    upper, middle, lower = dy.bollinger_bands(20, 2)
    
    # 3.1 밴드 하단 튕김
    if dy.l() <= lower * 1.01 and dy.c() > dy.o():
        bullish_signals.append("볼린저 밴드 하단 반등")
        bounce_strength = min(100, 70 + (dy.c() - dy.o()) / (dy.h() - dy.l()) * 30)
        signal_strengths.append(bounce_strength)
        debug(f"볼린저 밴드 하단 반등 (신호 강도: {bounce_strength:.0f})")
    
    # 3.2 밴드 폭 수축 후 확장 시작 (변동성 증가)
    bb_width = (upper - lower) / middle * 100
    bb_width_prev = (dy.bollinger_bands(20, 2, 1)[0] - dy.bollinger_bands(20, 2, 1)[2]) / dy.bollinger_bands(20, 2, 1)[1] * 100
    bb_width_prev5 = (dy.bollinger_bands(20, 2, 5)[0] - dy.bollinger_bands(20, 2, 5)[2]) / dy.bollinger_bands(20, 2, 5)[1] * 100
    
    if bb_width > bb_width_prev and bb_width_prev < bb_width_prev5 * 0.8:
        bullish_signals.append("볼린저 밴드 확장 시작")
        signal_strengths.append(55)
        debug("볼린저 밴드 확장 시작 - 변동성 증가 (신호 강도: 55)")
    
    # 4. 캔들 패턴 확인
    # 4.1 강한 양봉 (실체가 전체 크기의 70% 이상)
    if dy.c() > dy.o() and (dy.c() - dy.o()) >= (dy.h() - dy.l()) * 0.7:
        bullish_signals.append("강한 양봉 출현")
        signal_strengths.append(65)
        debug("강한 양봉 출현 - 상승 동력 확인 (신호 강도: 65)")
    
    # 4.2 망치형 캔들 (하락 후 반전 신호)
    if dy.is_hammer():
        bullish_signals.append("망치형 캔들")
        signal_strengths.append(75)
        debug("망치형 캔들 출현 - 강한 반전 신호 (신호 강도: 75)")
    
    # 4.3 상승 포괄형 패턴
    if dy.is_engulfing(bullish=True):
        bullish_signals.append("상승 포괄형 캔들")
        signal_strengths.append(80)
        debug("상승 포괄형 캔들 - 매우 강한 반전 신호 (신호 강도: 80)")
    
    # 4.4 모닝 스타 패턴(Morning Star) - 3일 패턴
    if (dy.c(2) < dy.o(2) and  # 첫날 음봉
        abs(dy.c(1) - dy.o(1)) < (dy.h(1) - dy.l(1)) * 0.3 and  # 둘째날 소형 캔들
        dy.c() > dy.o() and  # 셋째날 양봉
        dy.c() > (dy.c(2) + dy.o(2)) / 2):  # 셋째날 첫째날 중간 위로 종가
        
        bullish_signals.append("모닝 스타 패턴")
        signal_strengths.append(90)  # 매우 강력한 반전 신호
        debug("모닝 스타 패턴(Morning Star) 감지 - 매우 강한 반전 신호 (신호 강도: 90)")
    
    # 5. 이동평균 신호
    ma5 = dy.ma(dy.c, 5)
    ma20 = dy.ma(dy.c, 20)
    ma60 = dy.ma(dy.c, 60)
    
    ma5_prev = dy.ma(dy.c, 5, 1)
    ma20_prev = dy.ma(dy.c, 20, 1)
    
    # 5.1 단기 이동평균 상승 전환
    if ma5 > ma5_prev and ma5_prev <= ma5_prev:
        bullish_signals.append("단기 이동평균 상승 전환")
        signal_strengths.append(50)
        debug("5일 이동평균 상승 전환 (신호 강도: 50)")
    
    # 5.2 골든크로스 임박 또는 발생
    if (ma5 > ma20 and ma5_prev <= ma20_prev) or (ma5 < ma20 and ma5/ma20 > 0.98):
        if ma5 > ma20:
            bullish_signals.append("골든크로스 발생")
            signal_strengths.append(75)
            debug("골든크로스 발생 - 5일선이 20일선 상향 돌파 (신호 강도: 75)")
        else:
            bullish_signals.append("골든크로스 임박")
            signal_strengths.append(60)
            cross_pct = (ma5/ma20 - 0.95) * 20 # 0.95에서 1.0까지를 0-100%로 정규화
            debug(f"골든크로스 임박 - 진행률 약 {cross_pct:.0f}% (신호 강도: 60)")
    
    # 5.3 20일선 지지 확인 (가격이 20일선 부근에서 반등)
    if dy.l() <= ma20 * 1.01 and dy.c() > ma20 and dy.c() > dy.o():
        bullish_signals.append("20일선 지지 확인")
        signal_strengths.append(70)
        debug("20일선 지지 확인 - 주요 이동평균에서 반등 (신호 강도: 70)")
    
    # 6. MACD 신호
    macd, signal, hist = dy.macd(12, 26, 9)
    macd_prev, signal_prev, hist_prev = dy.macd(12, 26, 9, 1)
    
    # 6.1 MACD 히스토그램 상승 전환 (음수에서 양수로)
    if hist > 0 and hist_prev <= 0:
        bullish_signals.append("MACD 히스토그램 양전")
        signal_strengths.append(80)
        debug("MACD 히스토그램 상승 전환 (음수→양수) - 강한 모멘텀 신호 (신호 강도: 80)")
    
    # 6.2 MACD 히스토그램 증가 (2일 연속)
    if hist > hist_prev and hist_prev > dy.macd(12, 26, 9, 2)[2]:
        bullish_signals.append("MACD 모멘텀 증가")
        signal_strengths.append(65)
        debug("MACD 히스토그램 2일 연속 증가 - 상승 모멘텀 강화 (신호 강도: 65)")
    
    # 7. 거래량 분석
    # 7.1 거래량 증가하며 양봉
    vol_increase = dy.v() > dy.ma(dy.v, 20) * 1.3
    if vol_increase and dy.c() > dy.o():
        bullish_signals.append("거래량 증가 양봉")
        vol_ratio = dy.v() / dy.ma(dy.v, 20)
        vol_strength = min(100, 50 + vol_ratio * 10)
        signal_strengths.append(vol_strength)
        debug(f"거래량 증가 양봉: 평균 대비 {vol_ratio:.1f}배 (신호 강도: {vol_strength:.0f})")
    
    # 7.2 상승 거래량 > 하락 거래량 (최근 5일)
    up_volume = sum([dy.v(i) for i in range(5) if dy.c(i) > dy.o(i)], 0)
    down_volume = sum([dy.v(i) for i in range(5) if dy.c(i) <= dy.o(i)], 0)
    
    if up_volume > down_volume * 1.5:
        bullish_signals.append("상승 거래량 우위")
        volume_ratio = up_volume / down_volume if down_volume > 0 else 3
        vol_dom_strength = min(100, 50 + volume_ratio * 10)
        signal_strengths.append(vol_dom_strength)
        debug(f"상승 거래량 우위: 하락 거래량 대비 {volume_ratio:.1f}배 (신호 강도: {vol_dom_strength:.0f})")
    
    # 8. 다중 타임프레임 분석
    # 8.1 단기 타임프레임 상승 확인 (60분봉)
    h1_ma5 = dy60.ma(dy60.c, 5)
    h1_ma20 = dy60.ma(dy60.c, 20)
    
    if h1_ma5 > h1_ma20 and dy60.c() > h1_ma5:
        bullish_signals.append("60분봉 상승세 확인")
        signal_strengths.append(60)
        debug("60분봉 차트 상승세 확인 - 5시간선 > 20시간선 (신호 강도: 60)")
    
    # 8.2 4시간봉 RSI 상승 전환
    h4_rsi = h4.rsi(14)
    h4_rsi_prev = h4.rsi(14, 1)
    
    if h4_rsi > h4_rsi_prev and h4_rsi_prev < 40:
        bullish_signals.append("4시간봉 RSI 상승 전환")
        signal_strengths.append(65)
        debug(f"4시간봉 RSI 상승 전환: {h4_rsi_prev:.1f} -> {h4_rsi:.1f} (신호 강도: 65)")
    
    # 9. 추세선 분석
    # 9.1 하락 추세선 상향 돌파
    # 간단한 하락 추세선: 최근 하락장의 고점 연결
    # 최근 고점들 찾기
    peaks = []
    for i in range(2, lookback_period - 2):
        if dy.h(i) > dy.h(i-1) and dy.h(i) > dy.h(i-2) and dy.h(i) > dy.h(i+1) and dy.h(i) > dy.h(i+2):
            peaks.append((i, dy.h(i)))
    
    # 하락 추세선 계산 (최소 2개 고점 필요)
    if len(peaks) >= 2:
        # 최근 두 고점 선택
        recent_peaks = sorted(peaks, key=lambda x: x[0])[:2]
        days_diff = recent_peaks[1][0] - recent_peaks[0][0]
        price_diff = recent_peaks[1][1] - recent_peaks[0][1]
        
        # 하락 추세선인 경우
        if price_diff < 0:
            # 오늘 기준 추세선 위치 계산
            trend_slope = price_diff / days_diff
            days_since_last_peak = recent_peaks[1][0]
            trend_line = recent_peaks[1][1] + (trend_slope * days_since_last_peak)
            
            # 추세선 돌파 확인
            if dy.c() > trend_line:
                bullish_signals.append("하락 추세선 상향 돌파")
                breakout_pct = (dy.c() / trend_line - 1) * 100
                trend_strength = min(100, 70 + breakout_pct * 5)
                signal_strengths.append(trend_strength)
                debug(f"하락 추세선 상향 돌파: {breakout_pct:.1f}% (신호 강도: {trend_strength:.0f})")
    
    # 10. 다이버전스 분석 (숨겨진 강세 다이버전스: 가격 하락, RSI 상승)
    price_lower_low = dy.c() < dy.c(5) and dy.c(5) < dy.c(10)
    rsi_higher_low = rsi > dy.rsi(14, 5) and dy.rsi(14, 5) < 40
    
    if price_lower_low and rsi_higher_low:
        bullish_signals.append("숨겨진 강세 다이버전스")
        div_strength = 85
        signal_strengths.append(div_strength)
        debug(f"숨겨진 강세 다이버전스 감지 - 가격은 하락, RSI는 상승 (신호 강도: {div_strength})")

# 종합 상승 전환 신호 강도 계산
signal_count = len(bullish_signals)
avg_strength = sum(signal_strengths) / len(signal_strengths) if signal_strengths else 0
total_strength = avg_strength * (signal_count / confirmation_count) if confirmation_count > 0 else 0

# 최종 판단
is_bullish_reversal = is_valid_setup and total_strength >= strength_threshold and signal_count >= confirmation_count

# 결과 정리 및 로깅
if is_bullish_reversal:
    info("=== 상승 전환 신호 감지! (하락/횡보 후 상승 초입) ===")
    info(f"감지된 신호: {signal_count}개 (필요 신호: {confirmation_count}개)")
    info(f"신호 강도: {total_strength:.1f}/100 (임계값: {strength_threshold})")
    for signal in bullish_signals:
        info(f"- {signal}")
    
    # 현재 가격 대비 예상 상승 목표 계산
    potential_gain = 0
    
    # 볼린저 밴드 기반 상승 예상
    if "볼린저 밴드 하단 반등" in bullish_signals:
        bb_gain = (middle - current_price) / current_price * 100  # 중간 밴드까지 상승 예상
        potential_gain = max(potential_gain, bb_gain)
    
    # RSI 기반 상승 예상
    if "RSI 과매도 반등" in bullish_signals or "RSI 상승 전환" in bullish_signals:
        rsi_gain = (30 - rsi) / 20 * 10 if rsi < 50 else 5  # RSI 30=10%, 40=5%, 50=5% 상승 예상
        potential_gain = max(potential_gain, rsi_gain)
    
    # 이동평균 기반 상승 예상
    if "골든크로스 발생" in bullish_signals or "골든크로스 임박" in bullish_signals:
        ma_gain = (ma20 - current_price) / current_price * 100 if current_price < ma20 else 5
        potential_gain = max(potential_gain, ma_gain)
    
    # 최소 기대 상승률 설정
    potential_gain = max(potential_gain, 5)  # 최소 5% 상승 기대
    
    info(f"예상 상승 폭: 약 {potential_gain:.1f}% (목표가: {price * (1 + potential_gain/100):.0f})")
else:
    if not is_valid_setup:
        debug("하락 또는 횡보 패턴이 확인되지 않음 (상승 초입 분석 전제 조건 미충족)")
    elif signal_count > 0:
        debug(f"상승 전환 신호 일부 감지: {signal_count}개 (신호 강도: {total_strength:.1f}/100)")
        debug("강력한 상승 전환으로 판단하기에는 불충분")
    else:
        debug("상승 전환 신호가 감지되지 않음")

# 최종 결과 반환
result = {
    'is_bullish_reversal': is_bullish_reversal,
    'signals': bullish_signals,
    'signal_count': signal_count,
    'strength': total_strength,
    'potential_gain_pct': potential_gain if is_bullish_reversal else 0,
    'prior_downtrend': prior_downtrend,
    'is_sideways': is_sideways
}
```