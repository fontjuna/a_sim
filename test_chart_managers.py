#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData
import numpy as np
from datetime import datetime

def test_basic_functions():
    """기본 데이터 접근 함수들 검증"""
    print("=== ChartManager vs NumChartManager 기본 함수 검증 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'  # 삼성전자
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (가상의 차트 데이터)
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
    
    # 1. c() 함수 검증 (종가)
    print("1. c() 함수 검증 (종가)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.c(i)
        ncm_result = ncm.c(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"c({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 2. o() 함수 검증 (시가)
    print("2. o() 함수 검증 (시가)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.o(i)
        ncm_result = ncm.o(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"o({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 3. h() 함수 검증 (고가)
    print("3. h() 함수 검증 (고가)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.h(i)
        ncm_result = ncm.h(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"h({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 4. l() 함수 검증 (저가)
    print("4. l() 함수 검증 (저가)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.l(i)
        ncm_result = ncm.l(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"l({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 5. v() 함수 검증 (거래량)
    print("5. v() 함수 검증 (거래량)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.v(i)
        ncm_result = ncm.v(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"v({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 6. a() 함수 검증 (거래대금)
    print("6. a() 함수 검증 (거래대금)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.a(i)
        ncm_result = ncm.a(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"a({i}): ChartManager={cm_result}, NumChartManager={ncm_result} {match}")
    
    print()
    
    # 7. bar_time() 함수 검증 (시간)
    print("7. bar_time() 함수 검증 (시간)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.bar_time(i)
        ncm_result = ncm.bar_time(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"bar_time({i}): ChartManager='{cm_result}', NumChartManager='{ncm_result}' {match}")
    
    print()
    
    # 8. bar_date() 함수 검증 (날짜)
    print("8. bar_date() 함수 검증 (날짜)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.bar_date(i)
        ncm_result = ncm.bar_date(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"bar_date({i}): ChartManager='{cm_result}', NumChartManager='{ncm_result}' {match}")
    
    print()
    
    # 9. bar() 함수 검증 (전체 봉 데이터)
    print("9. bar() 함수 검증 (전체 봉 데이터)")
    print("-" * 50)
    
    for i in range(3):
        cm_result = cm.bar(i)
        ncm_result = ncm.bar(i)
        match = "OK" if cm_result == ncm_result else "FAIL"
        print(f"bar({i}):")
        print(f"  ChartManager: {cm_result}")
        print(f"  NumChartManager: {ncm_result}")
        print(f"  일치: {match}")
        print()
    
    # 10. 데이터 길이 검증
    print("10. 데이터 길이 검증")
    print("-" * 50)
    
    cm_length = cm.get_data_length()
    ncm_length = ncm.get_data_length()
    match = "OK" if cm_length == ncm_length else "FAIL"
    print(f"데이터 길이: ChartManager={cm_length}, NumChartManager={ncm_length} {match}")
    
    print()
    
    # 11. 원본 데이터 비교
    print("11. 원본 데이터 비교")
    print("-" * 50)
    
    cm_raw = cm.get_raw_data()
    ncm_raw = ncm.get_raw_data()
    
    print(f"ChartManager 원본 데이터 타입: {type(cm_raw)}")
    print(f"NumChartManager 원본 데이터 타입: {type(ncm_raw)}")
    
    if isinstance(cm_raw, list) and isinstance(ncm_raw, dict):
        print("OK 데이터 구조가 예상대로 다름 (ChartManager: list, NumChartManager: dict)")
    else:
        print("FAIL 데이터 구조가 예상과 다름")
    
    print()
    
    # 12. numpy 캐시 상태 확인
    print("12. NumChartManager numpy 캐시 상태")
    print("-" * 50)
    
    print(f"캐시 버전: {ncm._cache_version}")
    print(f"데이터 길이: {ncm._data_length}")
    print(f"numpy 캐시 키들: {list(ncm._np_cache.keys()) if ncm._np_cache else 'None'}")
    
    if ncm._np_cache:
        for key, arr in ncm._np_cache.items():
            print(f"  {key}: {type(arr)}, shape={arr.shape if hasattr(arr, 'shape') else 'N/A'}")
    
    print("\n=== 검증 완료 ===")

if __name__ == "__main__":
    test_basic_functions() 