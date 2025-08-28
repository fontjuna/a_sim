#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JIT 최적화 문제 해결 및 정확한 성능 테스트
"""

import time
import random
from chart import ChartManager, OldChartManager, ChartData
from datetime import datetime, timedelta

def generate_simple_test_data(count=100):
    """간단한 테스트 데이터 생성 (결과 검증용)"""
    print(f"간단한 테스트 데이터 {count}개 생성 중...")
    
    test_data = []
    for i in range(count):
        # 순차적으로 증가하는 가격
        price = 50000 + i * 10
        
        candle = {
            '종목코드': '005930',
            '체결시간': f'20250101{12:02d}{i:02d}00',
            '시가': price,
            '고가': price + 100,
            '저가': price - 100,
            '현재가': price,
            '거래량': 1000 + i,
            '거래대금': (1000 + i) * price
        }
        test_data.append(candle)
    
    print(f"간단한 테스트 데이터 생성 완료: {len(test_data)}개")
    return test_data

def test_extremes_accuracy(cm_jit, cm_old):
    """극값 계산 정확성 테스트"""
    print("\n=== 극값 계산 정확성 테스트 ===")
    
    # 간단한 데이터로 테스트
    result_jit = cm_jit.get_extremes(50, 0)
    result_old = cm_old.get_extremes(50, 0)
    
    print("JIT 결과:")
    for key, value in result_jit.items():
        print(f"  {key}: {value}")
    
    print("\n기존 결과:")
    for key, value in result_old.items():
        print(f"  {key}: {value}")
    
    # 주요 값들 비교
    print(f"\n비교 결과:")
    print(f"  최고고가(hh): JIT={result_jit['hh']}, 기존={result_old['hh']} - {'✅' if result_jit['hh'] == result_old['hh'] else '❌'}")
    print(f"  최고종가(hc): JIT={result_jit['hc']}, 기존={result_old['hc']} - {'✅' if result_jit['hc'] == result_old['hc'] else '❌'}")
    print(f"  최저종가(lc): JIT={result_jit['lc']}, 기존={result_old['lc']} - {'✅' if result_jit['lc'] == result_old['lc'] else '❌'}")
    print(f"  최저저가(ll): JIT={result_jit['ll']}, 기존={result_old['ll']} - {'✅' if result_jit['ll'] == result_old['ll'] else '❌'}")
    print(f"  최고거래량(hv): JIT={result_jit['hv']}, 기존={result_old['hv']} - {'✅' if result_jit['hv'] == result_old['hv'] else '❌'}")
    print(f"  최저거래량(lv): JIT={result_jit['lv']}, 기존={result_old['lv']} - {'✅' if result_jit['lv'] == result_old['lv'] else '❌'}")

def test_obv_accuracy(cm_jit, cm_old):
    """OBV 계산 정확성 테스트"""
    print("\n=== OBV 계산 정확성 테스트 ===")
    
    # 간단한 데이터로 테스트
    result_jit = cm_jit.get_obv_array(10)
    result_old = cm_old.get_obv_array(10)
    
    print(f"JIT OBV 배열: {result_jit}")
    print(f"기존 OBV 배열: {result_old}")
    
    # 첫 번째와 마지막 값 비교
    if len(result_jit) > 0 and len(result_old) > 0:
        print(f"\n비교 결과:")
        print(f"  첫 번째 값: JIT={result_jit[0]}, 기존={result_old[0]} - {'✅' if abs(result_jit[0] - result_old[0]) < 0.01 else '❌'}")
        print(f"  마지막 값: JIT={result_jit[-1]}, 기존={result_old[-1]} - {'✅' if abs(result_jit[-1] - result_old[-1]) < 0.01 else '❌'}")

def test_ma_accuracy(cm_jit, cm_old):
    """이동평균 계산 정확성 테스트"""
    print("\n=== 이동평균 계산 정확성 테스트 ===")
    
    # 간단한 데이터로 테스트
    result_jit = cm_jit.ma(5, 0)
    result_old = cm_old.ma(5, 0)
    
    print(f"JIT MA(5): {result_jit}")
    print(f"기존 MA(5): {result_old}")
    
    if abs(result_jit - result_old) < 0.01:
        print("✅ 이동평균 결과 일치")
    else:
        print("❌ 이동평균 결과 불일치!")

def test_rsi_accuracy(cm_jit, cm_old):
    """RSI 계산 정확성 테스트"""
    print("\n=== RSI 계산 정확성 테스트 ===")
    
    # 간단한 데이터로 테스트
    result_jit = cm_jit.rsi(5, 0)
    result_old = cm_old.rsi(5, 0)
    
    print(f"JIT RSI(5): {result_jit}")
    print(f"기존 RSI(5): {result_old}")
    
    if abs(result_jit - result_old) < 0.01:
        print("✅ RSI 결과 일치")
    else:
        print("❌ RSI 결과 불일치!")

def test_top_volume_accuracy(cm_jit, cm_old):
    """상위 거래량 평균 정확성 테스트"""
    print("\n=== 상위 거래량 평균 정확성 테스트 ===")
    
    # 간단한 데이터로 테스트
    result_jit = cm_jit.top_volume_avg(50, 5, 0)
    result_old = cm_old.top_volume_avg(50, 5, 0)
    
    print(f"JIT top_volume_avg: {result_jit}")
    print(f"기존 top_volume_avg: {result_old}")
    
    if abs(result_jit - result_old) < 0.01:
        print("✅ 상위 거래량 평균 결과 일치")
    else:
        print("❌ 상위 거래량 평균 결과 불일치!")

def comprehensive_accuracy_test():
    """종합 정확성 테스트"""
    print("🔍 JIT 최적화 정확성 테스트 시작!")
    print("=" * 60)
    
    # 간단한 테스트 데이터 생성
    test_data = generate_simple_test_data(100)
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data('005930', test_data, 'mi', 1)
    
    # ChartManager 인스턴스 생성 (JIT 최적화 버전)
    cm_jit = ChartManager('005930', 'mi', 1)
    
    # OldChartManager 인스턴스 생성 (기존 버전)
    cm_old = OldChartManager('005930', 'mi', 1)
    
    print(f"데이터 길이: {cm_jit.get_data_length()}")
    
    # 각종 정확성 테스트 실행
    test_extremes_accuracy(cm_jit, cm_old)
    test_obv_accuracy(cm_jit, cm_old)
    test_ma_accuracy(cm_jit, cm_old)
    test_rsi_accuracy(cm_jit, cm_old)
    test_top_volume_accuracy(cm_jit, cm_old)
    
    print("\n" + "=" * 60)
    print("🎯 JIT 최적화 정확성 테스트 완료!")
    print("📊 문제점 분석:")
    print("   - 극값 계산: bars 값 불일치")
    print("   - OBV 계산: 누적 로직 차이")
    print("   - 기타 함수: 대부분 정확")

if __name__ == "__main__":
    comprehensive_accuracy_test() 