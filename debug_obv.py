#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, ChartData

def debug_obv():
    """ChartManager OBV 계산 과정 디버깅"""
    print("=== ChartManager OBV 계산 과정 디버깅 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # ChartManager 생성
    cm = ChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성
    test_data = [
        {
            '종목코드': test_code,
            '체결시간': '20241201100000',
            '시가': 1000,
            '고가': 1010,
            '저가': 990,
            '현재가': 1000,  # 보합
            '거래량': 1000,
            '거래대금': 1000000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100300',
            '시가': 1000,
            '고가': 1020,
            '저가': 1000,
            '현재가': 1010,  # 상승 (+10)
            '거래량': 1500,
            '거래대금': 1515000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100600',
            '시가': 1010,
            '고가': 1010,
            '저가': 990,
            '현재가': 990,   # 하락 (-20)
            '거래량': 2000,
            '거래대금': 1980000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100900',
            '시가': 990,
            '고가': 1010,
            '저가': 990,
            '현재가': 1005,  # 상승 (+15)
            '거래량': 1200,
            '거래대금': 1206000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201101200',
            '시가': 1005,
            '고가': 1005,
            '저가': 995,
            '현재가': 995,   # 하락 (-10)
            '거래량': 1800,
            '거래대금': 1791000
        }
    ]
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터:")
    for i, data in enumerate(test_data):
        change = data['현재가'] - (test_data[i-1]['현재가'] if i > 0 else data['현재가'])
        change_str = f"{change:+d}" if i > 0 else "0"
        print(f"  봉{i}: {data['현재가']}원 ({change_str}), 거래량: {data['거래량']}")
    
    print()
    
    # ChartManager OBV 결과
    cm_obv = cm.get_obv_array(5)
    print(f"ChartManager OBV 결과: {cm_obv}")
    
    print()
    
    # 수동으로 OBV 계산 과정 시뮬레이션
    print("수동 OBV 계산 과정:")
    print("-" * 50)
    
    # ChartManager 로직 시뮬레이션
    obv_values = []
    running_obv = 0.0
    
    print("ChartManager 로직 시뮬레이션:")
    print("역순으로 처리 (과거 → 최신 순서)")
    
    for i in range(len(test_data) - 1, -1, -1):
        if i == len(test_data) - 1:
            print(f"  i={i} (가장 오래된 봉): OBV = 0 (기준점)")
            obv_values.append(0.0)
            continue
        
        current_close = test_data[i]['현재가']
        prev_close = test_data[i + 1]['현재가']
        volume = test_data[i]['거래량']
        
        change = current_close - prev_close
        if change > 0:
            running_obv += volume
            print(f"  i={i}: {current_close} > {prev_close} (상승+{change}) → OBV = {running_obv}")
        elif change < 0:
            running_obv -= volume
            print(f"  i={i}: {current_close} < {prev_close} (하락{change}) → OBV = {running_obv}")
        else:
            print(f"  i={i}: {current_close} = {prev_close} (보합) → OBV = {running_obv}")
        
        obv_values.append(running_obv)
    
    print()
    print(f"계산된 OBV 값들: {obv_values}")
    
    # 최신 순으로 뒤집기
    obv_values.reverse()
    print(f"뒤집은 후: {obv_values}")
    
    print()
    
    # 표준 OBV 계산 과정
    print("표준 OBV 계산 과정:")
    print("-" * 50)
    
    standard_obv = []
    running_obv = 0.0
    
    for i in range(len(test_data)):
        if i == 0:
            print(f"  봉{i}: {test_data[i]['현재가']}원 → OBV = 0 (기준점)")
            standard_obv.append(0.0)
            continue
        
        current_close = test_data[i]['현재가']
        prev_close = test_data[i-1]['현재가']
        volume = test_data[i]['거래량']
        
        change = current_close - prev_close
        if change > 0:
            running_obv += volume
            print(f"  봉{i}: {current_close} > {prev_close} (상승+{change}) → OBV = {running_obv}")
        elif change < 0:
            running_obv -= volume
            print(f"  봉{i}: {current_close} < {prev_close} (하락{change}) → OBV = {running_obv}")
        else:
            print(f"  봉{i}: {current_close} = {prev_close} (보합) → OBV = {running_obv}")
        
        standard_obv.append(running_obv)
    
    print(f"표준 OBV 값들: {standard_obv}")
    
    print("\n=== 디버깅 완료 ===")

if __name__ == "__main__":
    debug_obv() 