#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JIT 최적화 정확한 성능 테스트
첫 실행 오버헤드 제거 후 실제 성능 측정
"""

import time
import random
from chart import ChartManager, OldChartManager, ChartData
from datetime import datetime, timedelta

def generate_test_data(count=2700):
    """테스트용 차트 데이터 생성"""
    print(f"테스트 데이터 {count}개 생성 중...")
    
    base_price = 50000
    base_time = datetime.now()
    
    test_data = []
    for i in range(count):
        # 가격 변동 (현실적인 패턴)
        change = random.randint(-500, 500)
        base_price = max(1000, base_price + change)
        
        # 시간 생성 (1분 간격)
        candle_time = base_time - timedelta(minutes=i)
        time_str = candle_time.strftime('%Y%m%d%H%M%S')
        
        # 거래량과 거래대금
        volume = random.randint(1000, 100000)
        amount = volume * base_price
        
        candle = {
            '종목코드': '005930',
            '체결시간': time_str,
            '시가': base_price + random.randint(-100, 100),
            '고가': base_price + random.randint(0, 200),
            '저가': base_price - random.randint(0, 200),
            '현재가': base_price,
            '거래량': volume,
            '거래대금': amount
        }
        test_data.append(candle)
    
    print(f"테스트 데이터 생성 완료: {len(test_data)}개")
    return test_data

def warmup_jit_functions(cm_jit):
    """JIT 함수들을 미리 실행하여 컴파일 오버헤드 제거"""
    print("🔥 JIT 함수 워밍업 중...")
    
    # 각 JIT 함수를 한 번씩 실행
    cm_jit.ma(20, 0)
    cm_jit.get_extremes(128, 1)
    cm_jit.rsi(14, 0)
    cm_jit.get_obv_array(20)
    cm_jit.get_close_tops(128, 80, 1)
    cm_jit.top_volume_avg(128, 10, 1)
    cm_jit.top_amount_avg(128, 10, 1)
    
    # 연속 조건 함수들도 워밍업
    def test_condition(i):
        return cm_jit.c(i) > cm_jit.c(i+1)
    
    cm_jit.consecutive_count(test_condition, 0, 50)
    cm_jit.consecutive_true_false(test_condition, 0, 50)
    cm_jit.streak_pattern(test_condition, "TTFF", 0, 50)
    cm_jit.find_last_condition_break(test_condition, 0, 50)
    
    print("✅ JIT 함수 워밍업 완료!")

def test_basic_functions(cm_jit, cm_old, test_count=10000):
    """기본 함수들 성능 테스트 (대량 데이터로 정확한 측정)"""
    print("\n=== 기본 함수 성능 테스트 ===")
    
    # c, h, l, o, v, a 함수 테스트
    functions = ['c', 'h', 'l', 'o', 'v', 'a']
    
    for func_name in functions:
        func_jit = getattr(cm_jit, func_name)
        func_old = getattr(cm_old, func_name)
        
        # JIT 버전 시간 측정
        start_time = time.time()
        for i in range(test_count):
            result_jit = func_jit(i % 100)
        jit_time = time.time() - start_time
        
        # 기존 버전 시간 측정
        start_time = time.time()
        for i in range(test_count):
            result_old = func_old(i % 100)
        old_time = time.time() - start_time
        
        # 결과 검증
        if result_jit == result_old:
            speedup = old_time / jit_time if jit_time > 0 else float('inf')
            print(f"{func_name:>2}: JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
        else:
            print(f"{func_name:>2}: ❌ 결과 불일치! JIT={result_jit}, 기존={result_old}")

def test_calculation_functions(cm_jit, cm_old, test_count=1000):
    """계산 함수들 성능 테스트"""
    print("\n=== 계산 함수 성능 테스트 ===")
    
    # 이동평균 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.ma(20, i % 50)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.ma(20, i % 50)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"ma(20): JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # 극값 계산 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.get_extremes(128, i % 10)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.get_extremes(128, i % 10)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"get_extremes: JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # 결과 검증
    if result_jit == result_old:
        print("✅ 극값 계산 결과 일치")
    else:
        print("❌ 극값 계산 결과 불일치!")
        print(f"  JIT: {result_jit}")
        print(f"  기존: {result_old}")

def test_technical_indicators(cm_jit, cm_old, test_count=500):
    """기술적 지표 성능 테스트"""
    print("\n=== 기술적 지표 성능 테스트 ===")
    
    # RSI 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.rsi(14, i % 20)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.rsi(14, i % 20)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"RSI(14): JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # OBV 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.get_obv_array(20)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.get_obv_array(20)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"OBV(20): JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # 결과 검증
    if len(result_jit) == len(result_old):
        print("✅ OBV 배열 길이 일치")
        # 첫 번째와 마지막 값만 비교
        if abs(result_jit[0] - result_old[0]) < 0.01 and abs(result_jit[-1] - result_old[-1]) < 0.01:
            print("✅ OBV 값 일치")
        else:
            print("❌ OBV 값 불일치!")
            print(f"  JIT 첫값: {result_jit[0]}, 마지막값: {result_jit[-1]}")
            print(f"  기존 첫값: {result_old[0]}, 마지막값: {result_old[-1]}")
    else:
        print("❌ OBV 배열 길이 불일치!")

def test_pattern_functions(cm_jit, cm_old, test_count=300):
    """패턴 함수들 성능 테스트"""
    print("\n=== 패턴 함수 성능 테스트 ===")
    
    # get_close_tops 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.get_close_tops(128, 80, i % 10)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.get_close_tops(128, 80, i % 10)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"get_close_tops: JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # top_volume_avg 테스트
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.top_volume_avg(128, 10, i % 10)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.top_volume_avg(128, 10, i % 10)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"top_volume_avg: JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")
    
    # 결과 검증
    if abs(result_jit - result_old) < 0.01:
        print("✅ top_volume_avg 결과 일치")
    else:
        print("❌ top_volume_avg 결과 불일치!")
        print(f"  JIT: {result_jit}")
        print(f"  기존: {result_old}")

def test_consecutive_functions(cm_jit, cm_old, test_count=200):
    """연속 조건 함수들 성능 테스트"""
    print("\n=== 연속 조건 함수 성능 테스트 ===")
    
    # consecutive_count 테스트
    def test_condition(i):
        return cm_jit.c(i) > cm_jit.c(i+1)  # 상승 조건
    
    start_time = time.time()
    for i in range(test_count):
        result_jit = cm_jit.consecutive_count(test_condition, i % 10, 50)
    jit_time = time.time() - start_time
    
    start_time = time.time()
    for i in range(test_count):
        result_old = cm_old.consecutive_count(test_condition, i % 10, 50)
    old_time = time.time() - start_time
    
    speedup = old_time / jit_time if jit_time > 0 else float('inf')
    print(f"consecutive_count: JIT={jit_time*1000:6.2f}ms, 기존={old_time*1000:6.2f}ms, 개선율={speedup:5.1f}배")

def comprehensive_test():
    """종합 성능 테스트"""
    print("🚀 JIT 최적화 정확한 성능 테스트 시작!")
    print("=" * 60)
    
    # 테스트 데이터 생성
    test_data = generate_test_data(2700)
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data('005930', test_data, 'mi', 1)
    
    # ChartManager 인스턴스 생성 (JIT 최적화 버전)
    cm_jit = ChartManager('005930', 'mi', 1)
    
    # OldChartManager 인스턴스 생성 (기존 버전)
    cm_old = OldChartManager('005930', 'mi', 1)
    
    print(f"데이터 길이: {cm_jit.get_data_length()}")
    
    # JIT 함수들 워밍업 (컴파일 오버헤드 제거)
    warmup_jit_functions(cm_jit)
    
    print("\n" + "=" * 60)
    print("📊 워밍업 완료 후 실제 성능 측정 시작!")
    print("=" * 60)
    
    # 각종 테스트 실행
    test_basic_functions(cm_jit, cm_old)
    test_calculation_functions(cm_jit, cm_old)
    test_technical_indicators(cm_jit, cm_old)
    test_pattern_functions(cm_jit, cm_old)
    test_consecutive_functions(cm_jit, cm_old)
    
    print("\n" + "=" * 60)
    print("🎉 JIT 최적화 정확한 성능 테스트 완료!")
    print("📊 결과 요약:")
    print("   - 워밍업 후 JIT 함수들의 실제 성능 측정")
    print("   - 결과 일치성 검증 완료")
    print("   - 정확한 성능 개선율 계산")

if __name__ == "__main__":
    comprehensive_test() 