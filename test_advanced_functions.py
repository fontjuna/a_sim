#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData

def test_advanced_functions():
    """고급 함수들 검증"""
    print("=== ChartManager vs NumChartManager 고급 함수 검증 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (더 많은 데이터로 이동평균 테스트)
    test_data = []
    base_price = 1000
    for i in range(30):  # 30개 데이터
        time_str = f'20241201{10:02d}{i*3:02d}00'
        price_change = (i % 7 - 3) * 10  # -30 ~ +30 범위의 가격 변화
        current_price = base_price + price_change
        
        test_data.append({
            '종목코드': test_code,
            '체결시간': time_str,
            '시가': current_price - 5,
            '고가': current_price + 10,
            '저가': current_price - 10,
            '현재가': current_price,
            '거래량': 1000 + (i % 5) * 100,
            '거래대금': (current_price * (1000 + (i % 5) * 100))
        })
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 1. ma() 함수 검증 (이동평균)
    print("1. ma() 함수 검증 (이동평균)")
    print("-" * 50)
    
    periods = [5, 10, 20]
    for period in periods:
        for offset in [0, 1, 2]:
            cm_val = cm.ma(period, offset)
            ncm_val = ncm.ma(period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  ma({period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 2. avg() 함수 검증 (단순이동평균)
    print("2. avg() 함수 검증 (단순이동평균)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.avg(cm.c, period, offset)
            ncm_val = ncm.avg(ncm.c, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  avg(c, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 3. highest() 함수 검증 (최고값)
    print("3. highest() 함수 검증 (최고값)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.highest(cm.h, period, offset)
            ncm_val = ncm.highest(ncm.h, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  highest(h, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 4. lowest() 함수 검증 (최저값)
    print("4. lowest() 함수 검증 (최저값)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.lowest(cm.l, period, offset)
            ncm_val = ncm.lowest(ncm.l, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  lowest(l, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 5. sum() 함수 검증 (합계)
    print("5. sum() 함수 검증 (합계)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.sum(cm.v, period, offset)
            ncm_val = ncm.sum(ncm.v, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  sum(v, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 6. eavg() 함수 검증 (지수이동평균)
    print("6. eavg() 함수 검증 (지수이동평균)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.eavg(cm.c, period, offset)
            ncm_val = ncm.eavg(ncm.c, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  eavg(c, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 7. wavg() 함수 검증 (가중이동평균)
    print("7. wavg() 함수 검증 (가중이동평균)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.wavg(cm.c, period, offset)
            ncm_val = ncm.wavg(cm.c, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  wavg(c, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 8. stdev() 함수 검증 (표준편차)
    print("8. stdev() 함수 검증 (표준편차)")
    print("-" * 50)
    
    for period in [5, 10]:
        for offset in [0, 1]:
            cm_val = cm.stdev(cm.c, period, offset)
            ncm_val = ncm.stdev(ncm.c, period, offset)
            match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
            print(f"  stdev(c, {period}, {offset}): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 9. cross_up() 함수 검증 (상향돌파)
    print("9. cross_up() 함수 검증 (상향돌파)")
    print("-" * 50)
    
    # 5일선과 10일선의 상향돌파 확인
    cm_val = cm.cross_up(lambda n: cm.ma(5, n), lambda n: cm.ma(10, n))
    ncm_val = ncm.cross_up(lambda n: ncm.ma(5, n), lambda n: ncm.ma(10, n))
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  cross_up(ma5, ma10): {cm_val} vs {ncm_val} - {match}")
    
    # 현재가와 20일선의 상향돌파 확인
    cm_val = cm.cross_up(cm.c, lambda n: cm.ma(20, n))
    ncm_val = ncm.cross_up(ncm.c, lambda n: ncm.ma(20, n))
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  cross_up(c, ma20): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 10. cross_down() 함수 검증 (하향돌파)
    print("10. cross_down() 함수 검증 (하향돌파)")
    print("-" * 50)
    
    # 5일선과 10일선의 하향돌파 확인
    cm_val = cm.cross_down(lambda n: cm.ma(5, n), lambda n: cm.ma(10, n))
    ncm_val = ncm.cross_down(lambda n: ncm.ma(5, n), lambda n: ncm.ma(10, n))
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  cross_down(ma5, ma10): {cm_val} vs {ncm_val} - {match}")
    
    # 현재가와 20일선의 하향돌파 확인
    cm_val = cm.cross_down(cm.c, lambda n: cm.ma(20, n))
    ncm_val = ncm.cross_down(ncm.c, lambda n: ncm.ma(20, n))
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  cross_down(c, ma20): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 11. bars_since() 함수 검증 (조건 만족 이후 봉 개수)
    print("11. bars_since() 함수 검증 (조건 만족 이후 봉 개수)")
    print("-" * 50)
    
    # 종가가 1000 미만인 봉 이후 경과 봉수
    cm_val = cm.bars_since(lambda i: cm.c(i) < 1000)
    ncm_val = ncm.bars_since(lambda i: ncm.c(i) < 1000)
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  bars_since(c < 1000): {cm_val} vs {ncm_val} - {match}")
    
    # 거래량이 평균의 2배 이상인 봉 이후 경과 봉수
    cm_val = cm.bars_since(lambda i: cm.v(i) > cm.avg(cm.v, 20, i) * 2)
    ncm_val = ncm.bars_since(lambda i: ncm.v(i) > ncm.avg(ncm.v, 20, i) * 2)
    match = "OK" if cm_val == ncm_val else "FAIL"
    print(f"  bars_since(v > avg*2): {cm_val} vs {ncm_val} - {match}")
    
    print()
    
    # 12. highest_since() 함수 검증 (조건 만족 이후 최고값)
    print("12. highest_since() 함수 검증 (조건 만족 이후 최고값)")
    print("-" * 50)
    
    # 최근 2번째로 종가가 1000 미만 이후부터 현재까지 고가의 최고값
    cm_val = cm.highest_since(2, lambda i: cm.c(i) < 1000, cm.h)
    ncm_val = ncm.highest_since(2, lambda i: ncm.c(i) < 1000, ncm.h)
    match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
    print(f"  highest_since(2, c<1000, h): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 13. lowest_since() 함수 검증 (조건 만족 이후 최저값)
    print("13. lowest_since() 함수 검증 (조건 만족 이후 최저값)")
    print("-" * 50)
    
    # 최근 3번째로 종가가 1000 초과 이후부터 현재까지 저가의 최저값
    cm_val = cm.lowest_since(3, lambda i: cm.c(i) > 1000, cm.l)
    ncm_val = ncm.lowest_since(3, lambda i: ncm.c(i) > 1000, ncm.l)
    match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
    print(f"  lowest_since(3, c>1000, l): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 14. value_when() 함수 검증 (조건 만족 시점의 값)
    print("14. value_when() 함수 검증 (조건 만족 시점의 값)")
    print("-" * 50)
    
    # 최근 3번째로 종가가 1000을 넘은 시점의 시가
    cm_val = cm.value_when(3, lambda i: cm.c(i) > 1000, cm.o)
    ncm_val = ncm.value_when(3, lambda i: ncm.c(i) > 1000, ncm.o)
    match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
    print(f"  value_when(3, c>1000, o): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print()
    
    # 15. indicator() 함수 검증 (지표 함수 생성)
    print("15. indicator() 함수 검증 (지표 함수 생성)")
    print("-" * 50)
    
    # 이동평균 지표 생성
    cm_indicator = cm.indicator(cm.ma, 20)
    ncm_indicator = ncm.indicator(ncm.ma, 20)
    
    # 지표 함수 실행
    cm_val = cm_indicator(0)
    ncm_val = ncm_indicator(0)
    match = "OK" if abs(cm_val - ncm_val) < 0.001 else "FAIL"
    print(f"  indicator(ma, 20)(0): {cm_val:.2f} vs {ncm_val:.2f} - {match}")
    
    print("\n=== 고급 함수 검증 완료 ===")

if __name__ == "__main__":
    test_advanced_functions() 