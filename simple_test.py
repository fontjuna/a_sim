#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData

def simple_test():
    """간단한 기본 함수 검증"""
    print("=== 간단한 기본 함수 검증 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성
    test_data = [
        {
            '종목코드': test_code,
            '체결시간': '20241201100000',
            '시가': 1000,
            '고가': 1100,
            '저가': 990,
            '현재가': 1050,
            '거래량': 1000,
            '거래대금': 1050000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100300',
            '시가': 1050,
            '고가': 1150,
            '저가': 1040,
            '현재가': 1120,
            '거래량': 1500,
            '거래대금': 1680000
        },
        {
            '종목코드': test_code,
            '체결시간': '20241201100600',
            '시가': 1120,
            '고가': 1180,
            '저가': 1100,
            '현재가': 1150,
            '거래량': 2000,
            '거래대금': 2300000
        }
    ]
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 각 함수별로 개별 테스트
    print("1. c() 함수 (종가)")
    for i in range(3):
        cm_val = cm.c(i)
        ncm_val = ncm.c(i)
        print(f"  c({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n2. o() 함수 (시가)")
    for i in range(3):
        cm_val = cm.o(i)
        ncm_val = ncm.o(i)
        print(f"  o({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n3. h() 함수 (고가)")
    for i in range(3):
        cm_val = cm.h(i)
        ncm_val = ncm.h(i)
        print(f"  h({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n4. l() 함수 (저가)")
    for i in range(3):
        cm_val = cm.l(i)
        ncm_val = ncm.l(i)
        print(f"  l({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n5. v() 함수 (거래량)")
    for i in range(3):
        cm_val = cm.v(i)
        ncm_val = ncm.v(i)
        print(f"  v({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n6. a() 함수 (거래대금)")
    for i in range(3):
        cm_val = cm.a(i)
        ncm_val = ncm.a(i)
        print(f"  a({i}): {cm_val} vs {ncm_val} - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n7. bar_time() 함수 (시간)")
    for i in range(3):
        cm_val = cm.bar_time(i)
        ncm_val = ncm.bar_time(i)
        print(f"  bar_time({i}): '{cm_val}' vs '{ncm_val}' - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n8. bar_date() 함수 (날짜)")
    for i in range(3):
        cm_val = cm.bar_date(i)
        ncm_val = ncm.bar_date(i)
        print(f"  bar_date({i}): '{cm_val}' vs '{ncm_val}' - {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n9. bar() 함수 (전체 봉 데이터)")
    for i in range(3):
        cm_val = cm.bar(i)
        ncm_val = ncm.bar(i)
        print(f"  bar({i}):")
        print(f"    ChartManager: {cm_val}")
        print(f"    NumChartManager: {ncm_val}")
        print(f"    일치: {'OK' if cm_val == ncm_val else 'FAIL'}")
    
    print("\n10. 데이터 길이")
    cm_len = cm.get_data_length()
    ncm_len = ncm.get_data_length()
    print(f"  ChartManager: {cm_len}")
    print(f"  NumChartManager: {ncm_len}")
    print(f"  일치: {'OK' if cm_len == ncm_len else 'FAIL'}")
    
    print("\n=== 검증 완료 ===")

if __name__ == "__main__":
    simple_test() 