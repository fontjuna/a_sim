#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간단한 JIT + 순수 Python 최적화 테스트
"""

from chart import ChartManager, OldChartManager
import time

def main():
    print("🎯 **JIT + 순수 Python 최적화 간단 테스트**")
    
    # 테스트 데이터 생성
    test_data = [
        {
            '체결시간': '20241201120000',
            '현재가': 50000,
            '시가': 50000,
            '고가': 51000,
            '저가': 49000,
            '거래량': 1000000,
            '거래대금': 50000000000
        },
        {
            '체결시간': '20241201120100',
            '현재가': 51000,
            '시가': 50000,
            '고가': 52000,
            '저가': 50000,
            '거래량': 1200000,
            '거래대금': 61200000000
        },
        {
            '체결시간': '20241201120200',
            '현재가': 52000,
            '시가': 51000,
            '고가': 53000,
            '저가': 51000,
            '거래량': 1500000,
            '거래대금': 78000000000
        }
    ]
    
    # ChartManager 초기화
    cm = ChartManager('TEST')
    cm._raw_data = test_data
    cm._data_length = len(test_data)
    cm.cycle = 'mi'
    cm.tick = 1
    
    # OldChartManager 초기화
    old_cm = OldChartManager('TEST')
    old_cm._raw_data = test_data
    old_cm._data_length = len(test_data)
    old_cm.cycle = 'mi'
    old_cm.tick = 1
    
    print(f"테스트 데이터: {len(test_data)}개 봉")
    
    # 1. get_extremes 테스트
    print("\n1️⃣ **get_extremes 테스트**")
    try:
        new_result = cm.get_extremes(3, 0)
        old_result = old_cm.get_extremes(3, 0)
        print(f"새로운 결과: {new_result}")
        print(f"기존 결과: {old_result}")
        print(f"일치 여부: {'✅' if new_result == old_result else '❌'}")
    except Exception as e:
        print(f"에러: {e}")
    
    # 2. top_volume_avg 테스트
    print("\n2️⃣ **top_volume_avg 테스트**")
    try:
        new_result = cm.top_volume_avg(3, 2, 0)
        old_result = old_cm.top_volume_avg(3, 2, 0)
        print(f"새로운 결과: {new_result}")
        print(f"기존 결과: {old_result}")
        print(f"일치 여부: {'✅' if abs(new_result - old_result) < 0.01 else '❌'}")
    except Exception as e:
        print(f"에러: {e}")
    
    # 3. get_obv_array 테스트
    print("\n3️⃣ **get_obv_array 테스트**")
    try:
        new_result = cm.get_obv_array(3)
        old_result = old_cm.get_obv_array(3)
        print(f"새로운 결과: {new_result}")
        print(f"기존 결과: {old_result}")
        print(f"일치 여부: {'✅' if new_result == old_result else '❌'}")
    except Exception as e:
        print(f"에러: {e}")
    
    # 4. 성능 테스트
    print("\n4️⃣ **성능 테스트**")
    try:
        # 새로운 함수 성능
        start_time = time.perf_counter()
        for _ in range(1000):
            cm.get_extremes(3, 0)
        new_time = time.perf_counter() - start_time
        
        # 기존 함수 성능
        start_time = time.perf_counter()
        for _ in range(1000):
            old_cm.get_extremes(3, 0)
        old_time = time.perf_counter() - start_time
        
        print(f"새로운 함수: {new_time*1000:.2f}ms")
        print(f"기존 함수: {old_time*1000:.2f}ms")
        if old_time > 0:
            speedup = old_time / new_time
            print(f"성능 향상: {speedup:.2f}x")
    except Exception as e:
        print(f"에러: {e}")
    
    print("\n🎉 **테스트 완료!**")

if __name__ == "__main__":
    main() 