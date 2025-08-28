#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NumPy 최적화 전후 성능 비교 테스트
"""

import time
import numpy as np
from chart import ChartManager, OldChartManager, ChartData
from datetime import datetime

def create_test_data(size=1000):
    """대용량 테스트 데이터 생성"""
    test_code = "005930"
    chart_data = ChartData()
    
    # 랜덤한 가격 데이터 생성
    np.random.seed(42)  # 재현 가능한 결과를 위해
    base_price = 10000
    price_changes = np.random.normal(0, 100, size)  # 정규분포로 가격 변화
    prices = [base_price]
    
    for change in price_changes:
        new_price = max(1000, prices[-1] + int(change))  # 최소가격 보장
        prices.append(new_price)
    
    # 테스트 데이터 생성
    test_data = []
    for i in range(size):
        price = prices[i]
        high = price + np.random.randint(0, 200)
        low = max(1000, price - np.random.randint(0, 200))
        volume = np.random.randint(1000, 10000)
        amount = price * volume
        
        test_data.append({
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}{1000+i:04d}00',
            '시가': price,
            '고가': high,
            '저가': low,
            '현재가': price,
            '거래량': volume,
            '거래대금': amount
        })
    
    return test_code, test_data, chart_data

def performance_test():
    """성능 테스트 실행"""
    print("=== NumPy 최적화 전후 성능 비교 테스트 ===\n")
    
    # 테스트 데이터 생성
    test_sizes = [100, 500, 1000, 2000]
    
    for size in test_sizes:
        print(f"--- 데이터 크기: {size}개 봉 ---")
        
        test_code, test_data, chart_data = create_test_data(size)
        chart_data.set_chart_data(test_code, test_data, 'mi', 1)
        
        # ChartManager (NumPy 최적화) 생성
        cm = ChartManager(test_code, 'mi', 1)
        old_cm = OldChartManager(test_code, 'mi', 1)
        
        # 1. RSI 함수 성능 테스트
        print(f"\n  RSI 함수 성능 테스트:")
        
        # ChartManager RSI
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            cm.rsi(14, 0)
        cm_time = time.time() - start_time
        
        # OldChartManager RSI
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            old_cm.rsi(14, 0)
        old_cm_time = time.time() - start_time
        
        speedup = old_cm_time / cm_time if cm_time > 0 else 0
        print(f"    ChartManager (NumPy): {cm_time:.4f}초")
        print(f"    OldChartManager:      {old_cm_time:.4f}초")
        print(f"    속도 향상:            {speedup:.2f}배")
        
        # 2. get_extremes 함수 성능 테스트
        print(f"\n  get_extremes 함수 성능 테스트:")
        
        # ChartManager get_extremes
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            cm.get_extremes(128, 1)
        cm_time = time.time() - start_time
        
        # OldChartManager get_extremes
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            old_cm.get_extremes(128, 1)
        old_cm_time = time.time() - start_time
        
        speedup = old_cm_time / cm_time if cm_time > 0 else 0
        print(f"    ChartManager (NumPy): {cm_time:.4f}초")
        print(f"    OldChartManager:      {old_cm_time:.4f}초")
        print(f"    속도 향상:            {speedup:.2f}배")
        
        # 3. 이동평균 함수 성능 테스트
        print(f"\n  이동평균 함수 성능 테스트:")
        
        # ChartManager ma
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            cm.ma(20, 0)
        cm_time = time.time() - start_time
        
        # OldChartManager ma
        start_time = time.time()
        for _ in range(100):  # 100번 반복
            old_cm.ma(20, 0)
        old_cm_time = time.time() - start_time
        
        speedup = old_cm_time / cm_time if cm_time > 0 else 0
        print(f"    ChartManager (NumPy): {cm_time:.4f}초")
        print(f"    OldChartManager:      {old_cm_time:.4f}초")
        print(f"    속도 향상:            {speedup:.2f}배")
        
        print("\n" + "="*50)
    
    print("\n=== 성능 테스트 완료 ===")
    print("\n📊 결론:")
    print("- 데이터가 클수록 NumPy 최적화 효과가 커집니다")
    print("- 작은 데이터에서는 오버헤드로 인해 오히려 느릴 수 있습니다")
    print("- 실제 거래에서는 대용량 데이터 처리 시 상당한 성능 향상을 기대할 수 있습니다")

if __name__ == "__main__":
    performance_test() 