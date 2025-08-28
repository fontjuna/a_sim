#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
성능 비교 테스트 - ChartManager vs OldChartManager
"""

from chart import ChartManager, OldChartManager
import time
import random

def create_large_test_data(size=1000):
    """대용량 테스트 데이터 생성"""
    test_data = []
    base_price = 50000
    base_volume = 1000000
    
    for i in range(size):
        # 가격 변동 (랜덤 워크)
        change = random.uniform(-0.02, 0.02)
        base_price *= (1 + change)
        
        # 고가, 저가, 현재가 생성
        high = base_price * random.uniform(1.0, 1.01)
        low = base_price * random.uniform(0.99, 1.0)
        close = random.uniform(low, high)
        open_price = random.uniform(low, high)
        
        # 거래량과 거래대금
        volume = int(base_volume * random.uniform(0.5, 2.0))
        amount = volume * close
        
        # 시간 생성
        timestamp = f"20241201{120000 + i:06d}"
        
        candle = {
            '체결시간': timestamp,
            '현재가': int(close),
            '시가': int(open_price),
            '고가': int(high),
            '저가': int(low),
            '거래량': volume,
            '거래대금': int(amount)
        }
        test_data.append(candle)
    
    return test_data

def test_performance():
    """성능 테스트 실행"""
    print("🚀 **성능 비교 테스트 - ChartManager vs OldChartManager**")
    print("=" * 60)
    
    # 테스트 데이터 크기별 성능 측정
    test_sizes = [100, 500, 1000, 2000]
    
    for size in test_sizes:
        print(f"\n📊 **테스트 데이터 크기: {size}개 봉**")
        print("-" * 40)
        
        # 테스트 데이터 생성
        test_data = create_large_test_data(size)
        
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
        
        # 테스트할 함수들
        test_functions = [
            ('get_extremes', lambda: cm.get_extremes(100, 1), lambda: old_cm.get_extremes(100, 1)),
            ('top_volume_avg', lambda: cm.top_volume_avg(100, 10, 1), lambda: old_cm.top_volume_avg(100, 10, 1)),
            ('top_amount_avg', lambda: cm.top_amount_avg(100, 10, 1), lambda: old_cm.top_amount_avg(100, 10, 1)),
            ('get_obv_array', lambda: cm.get_obv_array(20), lambda: old_cm.get_obv_array(20)),
            ('get_close_tops', lambda: cm.get_close_tops(100, 50, 1), lambda: old_cm.get_close_tops(100, 50, 1)),
            ('rsi', lambda: cm.rsi(14, 0), lambda: old_cm.rsi(14, 0)),
            ('ma', lambda: cm.ma(20, 0), lambda: old_cm.ma(20, 0)),
            ('atr', lambda: cm.atr(14, 0), lambda: old_cm.atr(14, 0)),
        ]
        
        results = {}
        
        for func_name, new_func, old_func in test_functions:
            # 워밍업 (JIT 컴파일)
            for _ in range(3):
                try:
                    new_func()
                    old_func()
                except:
                    pass
            
            # ChartManager 성능 측정
            start_time = time.perf_counter()
            for _ in range(100):
                try:
                    new_result = new_func()
                except:
                    pass
            new_time = time.perf_counter() - start_time
            
            # OldChartManager 성능 측정
            start_time = time.perf_counter()
            for _ in range(100):
                try:
                    old_result = old_func()
                except:
                    pass
            old_time = time.perf_counter() - start_time
            
            # 성능 비교
            if old_time > 0:
                speedup = old_time / new_time
                results[func_name] = {
                    'new_time': new_time * 1000,  # ms
                    'old_time': old_time * 1000,  # ms
                    'speedup': speedup
                }
            else:
                results[func_name] = {
                    'new_time': new_time * 1000,
                    'old_time': old_time * 1000,
                    'speedup': 0
                }
        
        # 결과 출력
        print(f"{'함수명':<20} {'ChartManager':<15} {'OldChartManager':<15} {'성능향상':<10}")
        print("-" * 60)
        
        for func_name, result in results.items():
            new_ms = f"{result['new_time']:.2f}ms"
            old_ms = f"{result['old_time']:.2f}ms"
            speedup = f"{result['speedup']:.2f}x"
            
            print(f"{func_name:<20} {new_ms:<15} {old_ms:<15} {speedup:<10}")
        
        # 평균 성능 향상
        valid_speedups = [r['speedup'] for r in results.values() if r['speedup'] > 0]
        if valid_speedups:
            avg_speedup = sum(valid_speedups) / len(valid_speedups)
            print(f"\n📈 **평균 성능 향상: {avg_speedup:.2f}x**")

def main():
    """메인 실행"""
    test_performance()
    print("\n🎉 **성능 테스트 완료!**")

if __name__ == "__main__":
    main() 