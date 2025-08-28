#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, OldChartManager, ChartData

def test_close_tops():
    """get_close_tops 함수 테스트"""
    print("=== get_close_tops 함수 테스트 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ocm = OldChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (최고종가 갱신이 여러 번 일어나는 데이터)
    test_data = [
        {
            '종목코드': test_code,
            '체결시간': '20241201100000',
            '시가': 1000,
            '고가': 1010,
            '저가': 990,
            '현재가': 1000,  # 첫 번째 봉
            '거래량': 1000,
            '거래대금': 1000000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100300',
            '시가': 1000,
            '고가': 1020,
            '저가': 1000,
            '현재가': 1010,  # 상승 (+10) - 최고종가 갱신 #1
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
            '고가': 1015,
            '저가': 990,
            '현재가': 1015,  # 상승 (+25) - 최고종가 갱신 #2
            '거래량': 1200,
            '거래대금': 1218000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201101200',
            '시가': 1015,
            '고가': 1015,
            '저가': 995,
            '현재가': 995,   # 하락 (-20)
            '거래량': 1800,
            '거래대금': 1791000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201101500',
            '시가': 995,
            '고가': 1020,
            '저가': 995,
            '현재가': 1020,  # 상승 (+25) - 최고종가 갱신 #3
            '거래량': 2000,
            '거래대금': 2040000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201101800',
            '시가': 1020,
            '고가': 1020,
            '저가': 1000,
            '현재가': 1000,  # 하락 (-20)
            '거래량': 1600,
            '거래대금': 1600000
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
    
    # 최고종가 갱신 지점 확인
    print("최고종가 갱신 지점:")
    max_close = 0
    for i, data in enumerate(test_data):
        if data['현재가'] > max_close:
            max_close = data['현재가']
            print(f"  봉{i}: {data['현재가']}원 (새로운 최고종가 갱신)")
    
    print()
    
    # get_close_tops 결과 비교
    print("get_close_tops 결과 비교:")
    print("-" * 60)
    
    # 다양한 파라미터로 테스트
    test_cases = [
        (128, 128, 1, "전체 범위 검사"),
        (128, 80, 1, "80봉 범위 검사"),
        (128, 50, 1, "50봉 범위 검사"),
        (128, 20, 1, "20봉 범위 검사")
    ]
    
    for n, cnt, m, desc in test_cases:
        print(f"\n{desc} (n={n}, cnt={cnt}, m={m}):")
        
        cm_result = cm.get_close_tops(n, cnt, m)
        ocm_result = ocm.get_close_tops(n, cnt, m)
        
        print(f"  ChartManager: {cm_result}")
        print(f"  OldChartManager: {cm_result}")
        
        # 결과 비교
        if len(cm_result[0]) == len(ocm_result[0]) and cm_result[1] == ocm_result[1]:
            match = "OK"
        else:
            match = "FAIL"
        
        print(f"  일치 여부: {match}")
        
        if match == "FAIL":
            print(f"    ChartManager 최고종가 개수: {len(cm_result[0])}")
            print(f"    OldChartManager 최고종가 개수: {len(ocm_result[0])}")
            print(f"    ChartManager 당일봉수: {cm_result[1]}")
            print(f"    OldChartManager 당일봉수: {ocm_result[1]}")
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    test_close_tops() 