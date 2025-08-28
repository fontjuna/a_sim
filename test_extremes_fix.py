#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
get_extremes 함수 수정 테스트
"""

from chart import ChartManager, OldChartManager, ChartData
from datetime import datetime

def test_extremes_fix():
    """get_extremes 함수 수정 테스트"""
    print("=== get_extremes 함수 수정 테스트 ===\n")
    
    # 테스트 데이터 준비
    test_code = "005930"
    chart_data = ChartData()
    
    # 간단한 테스트 데이터 (7개 봉)
    test_data = [
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090000',
            '시가': 1000, '고가': 1010, '저가': 990, '현재가': 1005,
            '거래량': 1000, '거래대금': 1000000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090100',
            '시가': 1005, '고가': 1020, '저가': 1000, '현재가': 1010,
            '거래량': 1500, '거래대금': 1500000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090200',
            '시가': 1010, '고가': 1015, '저가': 995, '현재가': 990,
            '거래량': 800, '거래대금': 800000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090300',
            '시가': 990, '고가': 1018, '저가': 990, '현재가': 1015,
            '거래량': 2000, '거래대금': 2000000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090400',
            '시가': 1015, '고가': 1015, '저가': 1000, '현재가': 995,
            '거래량': 1200, '거래대금': 1200000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090500',
            '시가': 995, '고가': 1025, '저가': 995, '현재가': 1020,
            '거래량': 1800, '거래대금': 1800000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}090600',
            '시가': 1020, '고가': 1020, '저가': 1005, '현재가': 1000,
            '거래량': 900, '거래대금': 900000
        }
    ]
    
    print("테스트 데이터:")
    for i, data in enumerate(test_data):
        print(f"  봉{i}: {data['현재가']}원 (고가:{data['고가']}, 저가:{data['저가']}, 거래량:{data['거래량']})")
    
    # 차트 데이터 설정
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    # ChartManager와 OldChartManager 생성
    cm = ChartManager(test_code, 'mi', 1)
    old_cm = OldChartManager(test_code, 'mi', 1)
    
    print("\n=== get_extremes() 함수 테스트 ===")
    print("--------------------------------------------------")
    
    # 다양한 파라미터로 테스트
    test_cases = [
        (3, 1),   # 3봉, 1봉전부터
        (5, 0),   # 5봉, 현재봉부터
        (7, 1),   # 7봉, 1봉전부터
        (2, 2),   # 2봉, 2봉전부터
    ]
    
    for n, m in test_cases:
        print(f"\nget_extremes({n}, {m}):")
        
        try:
            # ChartManager 결과
            result_cm = cm.get_extremes(n, m)
            print(f"  ChartManager: OK")
            print(f"    hh: {result_cm['hh']}, hc: {result_cm['hc']}, lc: {result_cm['lc']}, ll: {result_cm['ll']}")
            print(f"    hv: {result_cm['hv']}, lv: {result_cm['lv']}, ha: {result_cm['ha']}, la: {result_cm['la']}")
            print(f"    close: {result_cm['close']}, bars: {result_cm['bars']}")
            
        except Exception as e:
            print(f"  ChartManager: ERROR - {type(e).__name__}: {e}")
        
        try:
            # OldChartManager 결과
            result_old = old_cm.get_extremes(n, m)
            print(f"  OldChartManager: OK")
            print(f"    hh: {result_old['hh']}, hc: {result_old['hc']}, lc: {result_old['lc']}, ll: {result_old['ll']}")
            print(f"    hv: {result_old['hv']}, lv: {result_old['lv']}, ha: {result_old['ha']}, la: {result_old['la']}")
            print(f"    close: {result_old['close']}, bars: {result_old['bars']}")
            
        except Exception as e:
            print(f"  OldChartManager: ERROR - {type(e).__name__}: {e}")
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    test_extremes_fix() 