#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, ChartData

def debug_close_tops():
    """get_close_tops 함수 디버깅"""
    print("=== get_close_tops 함수 디버깅 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # ChartManager 생성
    cm = ChartManager(test_code, 'mi', 3)
    
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
    
    print("테스트 데이터:")
    for i, data in enumerate(test_data):
        print(f"  봉{i}: {data['현재가']}원")
    
    print()
    
    # 파라미터 분석
    n, cnt, m = 128, 128, 1
    print(f"파라미터: n={n}, cnt={cnt}, m={m}")
    
    # 인덱스 계산
    start_idx = n - 1 + m  # 128 - 1 + 1 = 128
    end_idx = m            # 1
    
    print(f"start_idx = {n} - 1 + {m} = {start_idx}")
    print(f"end_idx = {m}")
    
    # 데이터 길이 확인
    cm._update_numpy_cache()
    data_length = cm._data_length
    print(f"데이터 길이: {data_length}")
    
    # 범위 검증
    if start_idx >= data_length:
        print(f"⚠️  start_idx({start_idx}) >= data_length({data_length})")
        print("   → 빈 결과 반환")
    else:
        print(f"✅ start_idx({start_idx}) < data_length({data_length})")
        
        # 실제 검사할 인덱스들
        indices_to_check = list(range(start_idx, end_idx - 1, -1))
        print(f"검사할 인덱스들: {indices_to_check}")
        
        # 각 인덱스별 분석
        for current_idx in indices_to_check:
            if current_idx >= data_length:
                print(f"  인덱스 {current_idx}: 범위 초과")
                continue
                
            current_close = cm._np_cache['c'][current_idx]
            print(f"  인덱스 {current_idx}: 종가 {current_close}원")
            
            # 비교 범위 계산
            compare_start = current_idx
            compare_end = min(current_idx + cnt, data_length)
            
            print(f"    비교 범위: {compare_start} ~ {compare_end}")
            
            if compare_start >= compare_end:
                print(f"    → 비교 범위 무효")
                continue
            
            # numpy로 최대값 계산
            compare_closes = cm._np_cache['c'][compare_start:compare_end]
            max_close = max(compare_closes)
            
            print(f"    비교 범위 최대값: {max_close}원")
            print(f"    현재값 >= 최대값: {current_close} >= {max_close} = {current_close >= max_close}")
            
            if current_close >= max_close and max_close > 0:
                print(f"    ✅ 최고종가 인덱스 추가: {current_idx}")
            else:
                print(f"    ❌ 최고종가 아님")
    
    print("\n=== 디버깅 완료 ===")

if __name__ == "__main__":
    debug_close_tops() 