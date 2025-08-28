#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, OldChartManager, ChartData

def test_basic_functions(cm, ocm):
    """기본 데이터 접근 함수들 검증"""
    print("=== 기본 데이터 접근 함수들 검증 ===")
    print("-" * 50)
    
    results = {}
    
    # 1. c(), h(), l(), o(), v(), a()
    basic_funcs = ['c', 'h', 'l', 'o', 'v', 'a']
    for func_name in basic_funcs:
        cm_func = getattr(cm, func_name)
        ocm_func = getattr(ocm, func_name)
        
        # 여러 인덱스로 테스트
        for i in range(3):
            try:
                cm_val = cm_func(i)
                ocm_val = ocm_func(i)
                
                if abs(cm_val - ocm_val) < 0.001:
                    status = "OK"
                else:
                    status = f"FAIL (cm:{cm_val} vs ocm:{ocm_val})"
                
                if func_name not in results:
                    results[func_name] = {}
                results[func_name][f"인덱스{i}"] = status
                
            except Exception as e:
                status = f"ERROR: {e}"
                if func_name not in results:
                    results[func_name] = {}
                results[func_name][f"인덱스{i}"] = status
    
    # 결과 출력 및 통합 상태 계산
    for func_name, tests in results.items():
        print(f"{func_name}():")
        all_ok = True
        for test_name, status in tests.items():
            print(f"  {test_name}: {status}")
            if status != "OK":
                all_ok = False
        print()
        
        # 함수별 통합 상태 설정
        results[func_name] = "OK" if all_ok else "FAIL"
    
    return results

def test_calculation_functions(cm, ocm):
    """계산 함수들 검증"""
    print("=== 계산 함수들 검증 ===")
    print("-" * 50)
    
    results = {}
    
    # 1. ma() - 이동평균
    try:
        cm_ma = cm.ma(5, 0)
        ocm_ma = ocm.ma(5, 0)
        if abs(cm_ma - ocm_ma) < 0.001:
            results['ma()'] = "OK"
        else:
            results['ma()'] = f"FAIL (cm:{cm_ma} vs ocm:{ocm_ma})"
    except Exception as e:
        results['ma()'] = f"ERROR: {e}"
    
    # 2. avg() - 단순이동평균
    try:
        cm_avg = cm.avg(cm.c, 5, 0)
        ocm_avg = ocm.avg(ocm.c, 5, 0)
        if abs(cm_avg - ocm_avg) < 0.001:
            results['avg()'] = "OK"
        else:
            results['avg()'] = f"FAIL (cm:{cm_avg} vs ocm:{ocm_avg})"
    except Exception as e:
        results['avg()'] = f"ERROR: {e}"
    
    # 3. highest() - 최고값
    try:
        cm_high = cm.highest(cm.c, 5, 0)
        ocm_high = ocm.highest(ocm.c, 5, 0)
        if abs(cm_high - ocm_high) < 0.001:
            results['highest()'] = "OK"
        else:
            results['highest()'] = f"FAIL (cm:{cm_high} vs ocm:{ocm_high})"
    except Exception as e:
        results['highest()'] = f"ERROR: {e}"
    
    # 4. lowest() - 최저값
    try:
        cm_low = cm.lowest(cm.c, 5, 0)
        ocm_low = ocm.lowest(ocm.c, 5, 0)
        if abs(cm_low - ocm_low) < 0.001:
            results['lowest()'] = "OK"
        else:
            results['lowest()'] = f"FAIL (cm:{cm_low} vs ocm:{cm_low})"
    except Exception as e:
        results['lowest()'] = f"ERROR: {e}"
    
    # 결과 출력
    for func_name, status in results.items():
        print(f"{func_name}: {status}")
    
    print()
    return results

def test_signal_functions(cm, ocm):
    """신호 함수들 검증"""
    print("=== 신호 함수들 검증 ===")
    print("-" * 50)
    
    results = {}
    
    # 1. cross_up() - 상향돌파
    try:
        cm_cross = cm.cross_up(lambda n: cm.c(n), lambda n: cm.ma(5, n))
        ocm_cross = ocm.cross_up(lambda n: ocm.c(n), lambda n: ocm.ma(5, n))
        if cm_cross == ocm_cross:
            results['cross_up()'] = "OK"
        else:
            results['cross_up()'] = f"FAIL (cm:{cm_cross} vs ocm:{ocm_cross})"
    except Exception as e:
        results['cross_up()'] = f"ERROR: {e}"
    
    # 2. cross_down() - 하향돌파
    try:
        cm_cross = cm.cross_down(lambda n: cm.c(n), lambda n: cm.ma(5, n))
        ocm_cross = ocm.cross_down(lambda n: ocm.c(n), lambda n: ocm.ma(5, n))
        if cm_cross == ocm_cross:
            results['cross_down()'] = "OK"
        else:
            results['cross_down()'] = f"FAIL (cm:{cm_cross} vs ocm:{ocm_cross})"
    except Exception as e:
        results['cross_down()'] = f"ERROR: {e}"
    
    # 결과 출력
    for func_name, status in results.items():
        print(f"{func_name}: {status}")
    
    print()
    return results

def test_technical_indicators(cm, ocm):
    """기술적 지표들 검증"""
    print("=== 기술적 지표들 검증 ===")
    print("-" * 50)
    
    results = {}
    
    # 1. RSI
    try:
        cm_rsi = cm.rsi(5, 0)
        ocm_rsi = ocm.rsi(5, 0)
        if abs(cm_rsi - ocm_rsi) < 0.001:
            results['rsi()'] = "OK"
        else:
            results['rsi()'] = f"FAIL (cm:{cm_rsi} vs ocm:{ocm_rsi})"
    except Exception as e:
        results['rsi()'] = f"ERROR: {e}"
    
    # 2. ATR
    try:
        cm_atr = cm.atr(5, 0)
        ocm_atr = ocm.atr(5, 0)
        if abs(cm_atr - ocm_atr) < 0.001:
            results['atr()'] = "OK"
        else:
            results['atr()'] = f"FAIL (cm:{cm_atr} vs ocm:{ocm_atr})"
    except Exception as e:
        results['atr()'] = f"ERROR: {e}"
    
    # 결과 출력
    for func_name, status in results.items():
        print(f"{func_name}: {status}")
    
    print()
    return results

def test_script_functions(cm, ocm):
    """스크립트 전용 함수들 검증"""
    print("=== 스크립트 전용 함수들 검증 ===")
    print("-" * 50)
    
    results = {}
    
    # 1. get_extremes()
    try:
        cm_ext = cm.get_extremes(10, 1)
        ocm_ext = ocm.get_extremes(10, 1)
        
        # 주요 키들 비교
        key_checks = ['hh', 'hc', 'lc', 'll', 'hv', 'lv']
        all_match = True
        for key in key_checks:
            if abs(cm_ext.get(key, 0) - ocm_ext.get(key, 0)) > 0.001:
                all_match = False
                break
        
        if all_match:
            results['get_extremes()'] = "OK"
        else:
            results['get_extremes()'] = f"FAIL (cm:{cm_ext} vs ocm:{ocm_ext})"
    except Exception as e:
        results['get_extremes()'] = f"ERROR: {e}"
    
    # 2. top_volume_avg()
    try:
        cm_vol = cm.top_volume_avg(10, 5, 1)
        ocm_vol = ocm.top_volume_avg(10, 5, 1)
        if abs(cm_vol - ocm_vol) < 0.001:
            results['top_volume_avg()'] = "OK"
        else:
            results['top_volume_avg()'] = f"FAIL (cm:{cm_vol} vs ocm:{ocm_vol})"
    except Exception as e:
        results['top_volume_avg()'] = f"ERROR: {e}"
    
    # 3. get_close_tops()
    try:
        cm_tops = cm.get_close_tops(128, 128, 1)
        ocm_tops = ocm.get_close_tops(128, 128, 1)
        
        if (len(cm_tops[0]) == len(ocm_tops[0]) and 
            cm_tops[1] == ocm_tops[1]):
            results['get_close_tops()'] = "OK"
        else:
            results['get_close_tops()'] = f"FAIL (cm:{cm_tops} vs ocm:{ocm_tops})"
    except Exception as e:
        results['get_close_tops()'] = f"ERROR: {e}"
    
    # 결과 출력
    for func_name, status in results.items():
        print(f"{func_name}: {status}")
    
    print()
    return results

def comprehensive_validation():
    """포괄적 검증 실행"""
    print("=== 스크립트 함수들 포괄적 검증 ===\n")
    
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
    
    # 각 카테고리별 검증 실행
    all_results = {}
    
    all_results['basic'] = test_basic_functions(cm, ocm)
    all_results['calculation'] = test_calculation_functions(cm, ocm)
    all_results['signal'] = test_signal_functions(cm, ocm)
    all_results['technical'] = test_technical_indicators(cm, ocm)
    all_results['script'] = test_script_functions(cm, ocm)
    
    # 전체 결과 요약
    print("=== 검증 결과 요약 ===")
    print("-" * 50)
    
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    error_tests = 0
    
    for category, results in all_results.items():
        print(f"\n{category.upper()} 카테고리:")
        for func_name, status in results.items():
            total_tests += 1
            if isinstance(status, str) and status == "OK":
                passed_tests += 1
                print(f"  ✅ {func_name}: {status}")
            elif isinstance(status, str) and status.startswith("FAIL"):
                failed_tests += 1
                print(f"  ❌ {func_name}: {status}")
            else:
                error_tests += 1
                print(f"  ⚠️  {func_name}: {status}")
    
    print(f"\n=== 최종 결과 ===")
    print(f"전체 테스트: {total_tests}")
    print(f"통과: {passed_tests} ✅")
    print(f"실패: {failed_tests} ❌")
    print(f"오류: {error_tests} ⚠️")
    print(f"성공률: {(passed_tests/total_tests)*100:.1f}%")

if __name__ == "__main__":
    comprehensive_validation() 