#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, OldChartManager, ChartData

def test_rsi_fix():
    """수정된 RSI 함수 테스트"""
    print("=== RSI 함수 수정 테스트 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ocm = OldChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성 (가격 변화가 명확한 데이터)
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
            '시가': 1000, '고가': 1020, '저가': 1000, '현재가': 1010,  # +10
            '거래량': 1500, '거래대금': 1515000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100600',
            '시가': 1010, '고가': 1010, '저가': 990, '현재가': 990,   # -20
            '거래량': 2000, '거래대금': 1980000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}100900',
            '시가': 990, '고가': 1015, '저가': 990, '현재가': 1015,   # +25
            '거래량': 1200, '거래대금': 1218000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101200',
            '시가': 1015, '고가': 1015, '저가': 995, '현재가': 995,   # -20
            '거래량': 1800, '거래대금': 1791000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101500',
            '시가': 995, '고가': 1020, '저가': 995, '현재가': 1020,   # +25
            '거래량': 2000, '거래대금': 2040000
        },
        {
            '종목코드': test_code,
            '체결시간': f'{datetime.now().strftime("%Y%m%d")}101800',
            '시가': 1020, '고가': 1020, '저가': 1000, '현재가': 1000, # -20
            '거래량': 1600, '거래대금': 1600000
        }
    ]
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터:")
    for i, data in enumerate(test_data):
        change = data['현재가'] - (test_data[i-1]['현재가'] if i > 0 else data['현재가'])
        change_str = f"{change:+d}" if i > 0 else "0"
        print(f"  봉{i}: {data['현재가']}원 ({change_str})")
    
    print()
    
    # RSI 계산 결과 비교
    print("RSI 계산 결과 비교:")
    print("-" * 50)
    
    # 다양한 period로 테스트
    test_periods = [3, 5, 7]
    
    for period in test_periods:
        print(f"\nRSI({period}) 계산:")
        
        cm_rsi = cm.rsi(period, 0)
        ocm_rsi = ocm.rsi(period, 0)
        
        print(f"  ChartManager: {cm_rsi:.2f}")
        print(f"  OldChartManager: {ocm_rsi:.2f}")
        
        # 일치 여부 확인
        if abs(cm_rsi - ocm_rsi) < 0.001:
            match = "OK"
        else:
            match = f"FAIL (차이: {abs(cm_rsi - ocm_rsi):.2f})"
        
        print(f"  일치 여부: {match}")
        
        # RSI 계산 과정 설명
        print(f"  계산 과정:")
        gains = 0.0
        losses = 0.0
        
        for i in range(1, period + 1):
            prev_price = test_data[i]['현재가']
            curr_price = test_data[i-1]['현재가']
            change = curr_price - prev_price
            
            if change > 0:
                gains += change
                print(f"    봉{i-1}→봉{i}: {change:+d} (상승)")
            else:
                losses += abs(change)
                print(f"    봉{i-1}→봉{i}: {change:+d} (하락)")
        
        print(f"    총 상승: {gains:.0f}")
        print(f"    총 하락: {losses:.0f}")
        print(f"    평균 상승: {gains/period:.2f}")
        print(f"    평균 하락: {losses/period:.2f}")
        
        if losses > 0:
            rs = (gains/period) / (losses/period)
            expected_rsi = 100 - (100 / (1 + rs))
            print(f"    RS: {rs:.2f}")
            print(f"    예상 RSI: {expected_rsi:.2f}")
    
    print("\n=== RSI 테스트 완료 ===")

if __name__ == "__main__":
    test_rsi_fix() 