#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData

def test_technical_indicators():
    """기술적 지표들과 캔들패턴 인식 함수들 검증"""
    print("=== ChartManager vs NumChartManager 기술적 지표 검증 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (다양한 패턴을 포함한 데이터)
    test_data = []
    base_price = 1000
    
    # 다양한 캔들 패턴을 포함한 데이터 생성
    patterns = [
        # 도지, 망치형, 유성형 등 다양한 패턴
        {'open': 1000, 'high': 1010, 'low': 990, 'close': 1000, 'volume': 1000},  # 도지
        {'open': 1000, 'high': 1020, 'low': 950, 'close': 1005, 'volume': 1500},  # 망치형
        {'open': 1005, 'high': 1050, 'low': 1000, 'close': 1000, 'volume': 2000}, # 유성형
        {'open': 1000, 'high': 1010, 'low': 990, 'close': 1010, 'volume': 1200},  # 상승봉
        {'open': 1010, 'high': 1010, 'low': 980, 'close': 980, 'volume': 1800},   # 하락봉
        {'open': 980, 'high': 1020, 'low': 980, 'close': 1020, 'volume': 1600},   # 포괄상승
        {'open': 1020, 'high': 1020, 'low': 970, 'close': 970, 'volume': 1400},   # 포괄하락
    ]
    
    for i, pattern in enumerate(patterns):
        time_str = f'20241201{10:02d}{i*3:02d}00'
        test_data.append({
            '종목코드': test_code,
            '체결시간': time_str,
            '시가': pattern['open'],
            '고가': pattern['high'],
            '저가': pattern['low'],
            '현재가': pattern['close'],
            '거래량': pattern['volume'],
            '거래대금': pattern['close'] * pattern['volume']
        })
    
    # 추가 데이터 (기술적 지표 계산용)
    for i in range(20):
        time_str = f'20241201{11:02d}{i*3:02d}00'
        price_change = (i % 5 - 2) * 5
        current_price = base_price + price_change
        
        test_data.append({
            '종목코드': test_code,
            '체결시간': time_str,
            '시가': current_price - 2,
            '고가': current_price + 5,
            '저가': current_price - 5,
            '현재가': current_price,
            '거래량': 1000 + (i % 3) * 200,
            '거래대금': current_price * (1000 + (i % 3) * 200)
        })
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 1. RSI 검증
    print("1. RSI 검증")
    print("-" * 50)
    
    for period in [14]:
        for offset in [0, 1]:
            cm_val = cm.rsi(period, offset)
            ncm_val = ncm.rsi(period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  RSI({period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 2. MACD 검증
    print("2. MACD 검증")
    print("-" * 50)
    
    cm_macd = cm.macd(12, 26, 9, 0)
    ncm_macd = ncm.macd(12, 26, 9, 0)
    
    cm_line, cm_signal, cm_hist = cm_macd
    ncm_line, ncm_signal, ncm_hist = ncm_macd
    
    match1 = "OK" if abs(cm_line - ncm_line) < 0.001 else "FAIL"
    match2 = "OK" if abs(cm_signal - ncm_signal) < 0.001 else "FAIL"
    match3 = "OK" if abs(cm_hist - ncm_hist) < 0.001 else "FAIL"
    
    print(f"  MACD Line: {cm_line:.2f} vs {ncm_line:.2f} - {match1}")
    print(f"  Signal Line: {cm_signal:.2f} vs {ncm_signal:.2f} - {match2}")
    print(f"  Histogram: {cm_hist:.2f} vs {ncm_hist:.2f} - {match3}")
    
    print()
    
    # 3. 볼린저 밴드 검증
    print("3. 볼린저 밴드 검증")
    print("-" * 50)
    
    cm_bb = cm.bollinger_bands(20, 2, 0)
    ncm_bb = ncm.bollinger_bands(20, 2, 0)
    
    cm_upper, cm_middle, cm_lower = cm_bb
    ncm_upper, ncm_middle, ncm_lower = ncm_bb
    
    match1 = "OK" if abs(cm_upper - ncm_upper) < 0.001 else "FAIL"
    match2 = "OK" if abs(cm_middle - ncm_middle) < 0.001 else "FAIL"
    match3 = "OK" if abs(cm_lower - ncm_lower) < 0.001 else "FAIL"
    
    print(f"  Upper Band: {cm_upper:.2f} vs {ncm_upper:.2f} - {match1}")
    print(f"  Middle Band: {cm_middle:.2f} vs {ncm_middle:.2f} - {match2}")
    print(f"  Lower Band: {cm_lower:.2f} vs {ncm_lower:.2f} - {match3}")
    
    print()
    
    # 4. 스토캐스틱 검증
    print("4. 스토캐스틱 검증")
    print("-" * 50)
    
    cm_stoch = cm.stochastic(14, 3, 0)
    ncm_stoch = ncm.stochastic(14, 3, 0)
    
    cm_k, cm_d = cm_stoch
    ncm_k, ncm_d = ncm_stoch
    
    match1 = "OK" if abs(cm_k - ncm_k) < 0.001 else "FAIL"
    match2 = "OK" if abs(cm_d - ncm_d) < 0.001 else "FAIL"
    
    print(f"  %K: {cm_k:.2f} vs {ncm_k:.2f} - {match1}")
    print(f"  %D: {cm_d:.2f} vs {ncm_d:.2f} - {match2}")
    
    print()
    
    # 5. ATR 검증
    print("5. ATR 검증")
    print("-" * 50)
    
    for period in [14]:
        for offset in [0, 1]:
            cm_val = cm.atr(period, offset)
            ncm_val = ncm.atr(period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  ATR({period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 6. 도지 캔들 패턴 검증
    print("6. 도지 캔들 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        cm_val = cm.is_doji(i)
        ncm_val = ncm.is_doji(i)
        match = "OK" if cm_val == ncm_val else "FAIL"
        print(f"  is_doji({i}): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 7. 유성형(슈팅스타) 캔들 패턴 검증
    print("7. 유성형(슈팅스타) 캔들 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        cm_val = cm.is_shooting_star(i)
        ncm_val = ncm.is_shooting_star(i)
        match = "OK" if cm_val == ncm_val else "FAIL"
        print(f"  is_shooting_star({i}): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 8. 역망치형 캔들 패턴 검증
    print("8. 역망치형 캔들 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        cm_val = cm.is_inverted_hammer(i)
        ncm_val = ncm.is_inverted_hammer(i)
        match = "OK" if cm_val == ncm_val else "FAIL"
        print(f"  is_inverted_hammer({i}): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 9. 교수형 캔들 패턴 검증
    print("9. 교수형 캔들 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        cm_val = cm.is_hanging_man(i)
        ncm_val = ncm.is_hanging_man(i)
        match = "OK" if cm_val == ncm_val else "FAIL"
        print(f"  is_hanging_man({i}): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 10. 망치형 캔들 패턴 검증
    print("10. 망치형 캔들 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        cm_val = cm.is_hammer(i)
        ncm_val = ncm.is_hammer(i)
        match = "OK" if cm_val == ncm_val else "FAIL"
        print(f"  is_hammer({i}): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 11. 포괄 패턴 검증
    print("11. 포괄 패턴 검증")
    print("-" * 50)
    
    for i in range(3):
        # 상승 포괄
        cm_val = cm.is_engulfing(i, True)
        ncm_val = ncm.is_engulfing(i, True)
        match1 = "OK" if cm_val == ncm_val else "FAIL"
        
        # 하락 포괄
        cm_val2 = cm.is_engulfing(i, False)
        ncm_val2 = ncm.is_engulfing(i, False)
        match2 = "OK" if cm_val2 == ncm_val2 else "FAIL"
        
        print(f"  is_engulfing({i}, True): {cm_val} vs {ncm_val} - {match1}")
        print(f"  is_engulfing({i}, False): {cm_val2} vs {ncm_val2} - {match2}")
    
    print()
    
    # 12. OBV 배열 검증
    print("12. OBV 배열 검증")
    print("-" * 50)
    
    for count in [5, 10]:
        cm_obv = cm.get_obv_array(count)
        ncm_obv = ncm.get_obv_array(count)
        
        if len(cm_obv) == len(ncm_obv):
            all_match = True
            for i in range(len(cm_obv)):
                if abs(cm_obv[i] - ncm_obv[i]) > 0.001:
                    all_match = False
                    break
            match = "OK" if all_match else "FAIL"
        else:
            match = "FAIL"
        
        print(f"  get_obv_array({count}): 길이 {len(cm_obv)} vs {len(ncm_obv)} - {match}")
        if match == "OK":
            print(f"    첫 3개 값: {cm_obv[:3]} vs {ncm_obv[:3]}")
    
    print()
    
    # 13. 극값 계산 검증
    print("13. 극값 계산 검증")
    print("-" * 50)
    
    for n in [10, 20]:
        for m in [0, 1]:
            cm_extremes = cm.get_extremes(n, m)
            ncm_extremes = ncm.get_extremes(n, m)
            
            # 주요 값들만 비교
            cm_hh = cm_extremes.get('hh', 0)
            ncm_hh = ncm_extremes.get('hh', 0)
            cm_ll = cm_extremes.get('ll', 0)
            ncm_ll = ncm_extremes.get('ll', 0)
            
            match1 = "OK" if cm_hh == ncm_hh else "FAIL"
            match2 = "OK" if cm_ll == ncm_ll else "FAIL"
            
            print(f"  get_extremes({n}, {m}):")
            print(f"    최고고가: {cm_hh} vs {ncm_hh} - {match1}")
            print(f"    최저저가: {cm_ll} vs {ncm_ll} - {match2}")
    
    print()
    
    # 14. 거래량 상위 평균 검증
    print("14. 거래량 상위 평균 검증")
    print("-" * 50)
    
    for n in [10, 20]:
        for cnt in [3, 5]:
            for m in [0, 1]:
                cm_val = cm.top_volume_avg(n, cnt, m)
                ncm_val = ncm.top_volume_avg(n, cnt, m)
                match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
                print(f"  top_volume_avg({n}, {cnt}, {m}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 15. 거래대금 상위 평균 검증
    print("15. 거래대금 상위 평균 검증")
    print("-" * 50)
    
    for n in [10, 20]:
        for cnt in [3, 5]:
            for m in [0, 1]:
                cm_val = cm.top_amount_avg(n, cnt, m)
                ncm_val = ncm.top_amount_avg(n, cnt, m)
                match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
                print(f"  top_amount_avg({n}, {cnt}, {m}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print("\n=== 기술적 지표 검증 완료 ===")

if __name__ == "__main__":
    test_technical_indicators() 