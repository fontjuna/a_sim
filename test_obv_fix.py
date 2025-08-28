#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData

def test_obv_fix():
    """수정된 OBV 함수 테스트"""
    print("=== 수정된 OBV 함수 테스트 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (가격 변화가 명확한 데이터)
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
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 데이터 확인
    print("테스트 데이터:")
    for i, data in enumerate(test_data):
        change = data['현재가'] - (test_data[i-1]['현재가'] if i > 0 else data['현재가'])
        change_str = f"{change:+d}" if i > 0 else "0"
        print(f"  봉{i}: {data['현재가']}원 ({change_str}), 거래량: {data['거래량']}")
    
    print()
    
    # OBV 계산 결과 비교
    print("OBV 계산 결과 비교:")
    print("-" * 50)
    
    cm_obv = cm.get_obv_array(5)
    ncm_obv = ncm.get_obv_array(5)
    
    print(f"ChartManager OBV: {cm_obv}")
    print(f"NumChartManager OBV: {ncm_obv}")
    
    # 일치 여부 확인
    if len(cm_obv) == len(ncm_obv):
        all_match = True
        for i in range(len(cm_obv)):
            if abs(cm_obv[i] - ncm_obv[i]) > 0.001:
                all_match = False
                break
        match = "OK" if all_match else "FAIL"
    else:
        match = "FAIL"
    
    print(f"일치 여부: {match}")
    
    print()
    
    # OBV 계산 과정 설명
    print("OBV 계산 과정:")
    print("-" * 50)
    
    print("1. 첫 번째 봉 (1000원): OBV = 0 (기준점)")
    print("2. 두 번째 봉 (1010원): 상승(+10) → OBV = 0 + 1500 = 1500")
    print("3. 세 번째 봉 (990원): 하락(-20) → OBV = 1500 - 2000 = -500")
    print("4. 네 번째 봉 (1005원): 상승(+15) → OBV = -500 + 1200 = 700")
    print("5. 다섯 번째 봉 (995원): 하락(-10) → OBV = 700 - 1800 = -1100")
    
    print()
    
    # 예상 결과와 실제 결과 비교
    expected_obv = [0, 1500, -500, 700, -1100]
    print("예상 OBV 값:", expected_obv)
    print("실제 OBV 값:", cm_obv)
    
    # 예상값과 일치 여부
    if len(expected_obv) == len(cm_obv):
        expected_match = True
        for i in range(len(expected_obv)):
            if abs(expected_obv[i] - cm_obv[i]) > 0.001:
                expected_match = False
                break
        expected_result = "OK" if expected_match else "FAIL"
    else:
        expected_result = "FAIL"
    
    print(f"예상값과 일치: {expected_result}")
    
    print("\n=== OBV 테스트 완료 ===")

if __name__ == "__main__":
    test_obv_fix() 