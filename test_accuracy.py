#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
정확성 테스트 - ChartManager vs OldChartManager
"""

from chart import ChartManager, OldChartManager
from datetime import datetime

def main():
    print("🎯 **정확성 테스트 - ChartManager vs OldChartManager**")
    
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
        print(f"ChartManager 결과: {new_result}")
        print(f"OldChartManager 결과: {old_result}")
        print(f"일치 여부: {'✅' if new_result == old_result else '❌'}")
        
        # bars 값 상세 비교
        if new_result['bars'] != old_result['bars']:
            print(f"⚠️ bars 불일치: {new_result['bars']} vs {old_result['bars']}")
    except Exception as e:
        print(f"에러: {e}")
    
    # 2. top_volume_avg 테스트
    print("\n2️⃣ **top_volume_avg 테스트**")
    try:
        new_result = cm.top_volume_avg(3, 2, 0)
        old_result = old_cm.top_volume_avg(3, 2, 0)
        print(f"ChartManager 결과: {new_result}")
        print(f"OldChartManager 결과: {old_result}")
        print(f"일치 여부: {'✅' if abs(new_result - old_result) < 0.01 else '❌'}")
    except Exception as e:
        print(f"에러: {e}")
    
    # 3. get_obv_array 테스트
    print("\n3️⃣ **get_obv_array 테스트**")
    try:
        new_result = cm.get_obv_array(3)
        old_result = old_cm.get_obv_array(3)
        print(f"ChartManager 결과: {new_result}")
        print(f"OldChartManager 결과: {old_result}")
        print(f"일치 여부: {'✅' if new_result == old_result else '❌'}")
    except Exception as e:
        print(f"에러: {e}")
    
    print("\n🎉 **테스트 완료!**")

if __name__ == "__main__":
    main() 