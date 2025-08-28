#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, OldChartManager, ChartData

def test_numpy_optimization():
    """numpy 최적화된 함수들의 성능과 정확성 테스트"""
    print("=== numpy 최적화 테스트 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ocm = OldChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성
    test_data = [
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100000',
            '시가': 1000, '고가': 1010, '저가': 990, '현재가': 1000,
            '거래량': 1000, '거래대금': 1000000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100300',
            '시가': 1000, '고가': 1020, '저가': 1000, '현재가': 1010,
            '거래량': 1500, '거래대금': 1515000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100600',
            '시가': 1010, '고가': 1010, '저가': 990, '현재가': 990,
            '거래량': 2000, '거래대금': 1980000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100900',
            '시가': 990, '고가': 1015, '저가': 990, '현재가': 1015,
            '거래량': 1200, '거래대금': 1218000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101200',
            '시가': 1015, '고가': 1015, '저가': 995, '현재가': 995,
            '거래량': 1800, '거래대금': 1791000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101500',
            '시가': 995, '고가': 1020, '저가': 995, '현재가': 1020,
            '거래량': 2000, '거래대금': 2040000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101800',
            '시가': 1020, '고가': 1020, '저가': 1000, '현재가': 1000,
            '거래량': 1600, '거래대금': 1600000
        }
    ]
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 1. OBV 함수 테스트
    print("=== OBV 함수 테스트 ===")
    print("-" * 40)
    
    # 정확성 테스트
    cm_obv = cm.get_obv_array(7)
    ocm_obv = ocm.get_obv_array(7)
    
    print(f"ChartManager OBV: {cm_obv}")
    print(f"OldChartManager OBV: {ocm_obv}")
    
    # 일치 여부 확인
    if len(cm_obv) == len(ocm_obv):
        all_match = True
        for i in range(len(cm_obv)):
            if abs(cm_obv[i] - ocm_obv[i]) > 0.001:
                all_match = False
                break
        match = "OK" if all_match else "FAIL"
    else:
        match = "FAIL"
    
    print(f"정확성: {match}")
    
    # 성능 테스트
    print("\n성능 테스트 (1000회 실행):")
    
    # ChartManager 성능
    start = time.time()
    for _ in range(1000):
        cm.get_obv_array(7)
    cm_time = time.time() - start
    
    # OldChartManager 성능
    start = time.time()
    for _ in range(1000):
        ocm.get_obv_array(7)
    ocm_time = time.time() - start
    
    print(f"ChartManager (numpy): {cm_time:.4f}초")
    print(f"OldChartManager: {ocm_time:.4f}초")
    print(f"속도 개선: {ocm_time/cm_time:.2f}배")
    
    print()
    
    # 2. get_close_tops 함수 테스트
    print("=== get_close_tops 함수 테스트 ===")
    print("-" * 40)
    
    # 정확성 테스트
    cm_tops = cm.get_close_tops(128, 128, 1)
    ocm_tops = ocm.get_close_tops(128, 128, 1)
    
    print(f"ChartManager 결과: {cm_tops}")
    print(f"OldChartManager 결과: {ocm_tops}")
    
    # 일치 여부 확인
    if len(cm_tops[0]) == len(ocm_tops[0]) and cm_tops[1] == ocm_tops[1]:
        match = "OK"
    else:
        match = "FAIL"
    
    print(f"정확성: {match}")
    
    # 성능 테스트
    print("\n성능 테스트 (1000회 실행):")
    
    # ChartManager 성능
    start = time.time()
    for _ in range(1000):
        cm.get_close_tops(128, 128, 1)
    cm_time = time.time() - start
    
    # OldChartManager 성능
    start = time.time()
    for _ in range(1000):
        ocm.get_close_tops(128, 128, 1)
    ocm_time = time.time() - start
    
    print(f"ChartManager (numpy): {cm_time:.4f}초")
    print(f"OldChartManager: {ocm_time:.4f}초")
    print(f"속도 개선: {ocm_time/cm_time:.2f}배")
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    test_numpy_optimization() 