#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart import ChartManager, NumChartManager, ChartData

def simple_technical_test():
    """기술적 지표들 간단 테스트"""
    print("=== 기술적 지표 간단 테스트 ===\n")
    
    # 테스트용 종목코드
    test_code = '005930'
    
    # 두 매니저 생성
    cm = ChartManager(test_code, 'mi', 3)
    ncm = NumChartManager(test_code, 'mi', 3)
    
    # 테스트 데이터 생성
    test_data = []
    base_price = 1000
    
    # 30개 데이터 생성
    for i in range(30):
        time_str = f'20241201{10:02d}{i*3:02d}00'
        price_change = (i % 7 - 3) * 10
        current_price = base_price + price_change
        
        test_data.append({
            '종목코드': test_code,
            '체결시간': time_str,
            '시가': current_price - 5,
            '고가': current_price + 10,
            '저가': current_price - 10,
            '현재가': current_price,
            '거래량': 1000 + (i % 5) * 100,
            '거래대금': (current_price * (1000 + (i % 5) * 100))
        })
    
    # ChartData에 테스트 데이터 설정
    chart_data = ChartData()
    chart_data.set_chart_data(test_code, test_data, 'mi', 1)
    
    print("테스트 데이터 설정 완료")
    print(f"데이터 개수: {len(test_data)}")
    print()
    
    # 각 지표별로 개별 테스트
    print("1. RSI")
    cm_rsi = cm.rsi(14, 0)
    ncm_rsi = ncm.rsi(14, 0)
    print(f"  RSI(14, 0): {cm_rsi:.2f} vs {ncm_rsi:.2f} - {'OK' if abs(cm_rsi - ncm_rsi) < 0.001 else 'FAIL'}")
    
    print("\n2. MACD")
    cm_macd = cm.macd(12, 26, 9, 0)
    ncm_macd = ncm.macd(12, 26, 9, 0)
    print(f"  MACD: {cm_macd} vs {ncm_macd}")
    
    print("\n3. 볼린저 밴드")
    cm_bb = cm.bollinger_bands(20, 2, 0)
    ncm_bb = ncm.bollinger_bands(20, 2, 0)
    print(f"  볼린저: {cm_bb} vs {ncm_bb}")
    
    print("\n4. 스토캐스틱")
    cm_stoch = cm.stochastic(14, 3, 0)
    ncm_stoch = ncm.stochastic(14, 3, 0)
    print(f"  스토캐스틱: {cm_stoch} vs {ncm_stoch}")
    
    print("\n5. ATR")
    cm_atr = cm.atr(14, 0)
    ncm_atr = ncm.atr(14, 0)
    print(f"  ATR: {cm_atr:.2f} vs {ncm_atr:.2f} - {'OK' if abs(cm_atr - ncm_atr) < 0.001 else 'FAIL'}")
    
    print("\n6. 도지 패턴")
    cm_doji = cm.is_doji(0)
    ncm_doji = ncm.is_doji(0)
    print(f"  is_doji(0): {cm_doji} vs {ncm_doji} - {'OK' if cm_doji == ncm_doji else 'FAIL'}")
    
    print("\n7. 유성형 패턴")
    cm_star = cm.is_shooting_star(0)
    ncm_star = ncm.is_shooting_star(0)
    print(f"  is_shooting_star(0): {cm_star} vs {ncm_star} - {'OK' if cm_star == ncm_star else 'FAIL'}")
    
    print("\n8. 망치형 패턴")
    cm_hammer = cm.is_hammer(0)
    ncm_hammer = ncm.is_hammer(0)
    print(f"  is_hammer(0): {cm_hammer} vs {ncm_hammer} - {'OK' if cm_hammer == ncm_hammer else 'FAIL'}")
    
    print("\n9. 포괄 패턴")
    cm_engulf = cm.is_engulfing(0, True)
    ncm_engulf = ncm.is_engulfing(0, True)
    print(f"  is_engulfing(0, True): {cm_engulf} vs {ncm_engulf} - {'OK' if cm_engulf == ncm_engulf else 'FAIL'}")
    
    print("\n10. OBV 배열")
    cm_obv = cm.get_obv_array(5)
    ncm_obv = ncm.get_obv_array(5)
    print(f"  get_obv_array(5): 길이 {len(cm_obv)} vs {len(ncm_obv)}")
    if len(cm_obv) == len(ncm_obv):
        all_match = True
        for i in range(min(3, len(cm_obv))):
            if abs(cm_obv[i] - ncm_obv[i]) > 0.001:
                all_match = False
                break
        print(f"    첫 3개 값 일치: {'OK' if all_match else 'FAIL'}")
    
    print("\n11. 극값 계산")
    cm_ext = cm.get_extremes(20, 0)
    ncm_ext = ncm.get_extremes(20, 0)
    print(f"  get_extremes(20, 0):")
    print(f"    최고고가: {cm_ext.get('hh', 0)} vs {ncm_ext.get('hh', 0)}")
    print(f"    최저저가: {cm_ext.get('ll', 0)} vs {ncm_ext.get('ll', 0)}")
    
    print("\n12. 거래량 상위 평균")
    cm_vol = cm.top_volume_avg(20, 5, 0)
    ncm_vol = ncm.top_volume_avg(20, 5, 0)
    print(f"  top_volume_avg(20, 5, 0): {cm_vol:.2f} vs {ncm_vol:.2f} - {'OK' if abs(cm_vol - ncm_vol) < 0.001 else 'FAIL'}")
    
    print("\n13. 거래대금 상위 평균")
    cm_amt = cm.top_amount_avg(20, 5, 0)
    ncm_amt = ncm.top_amount_avg(20, 5, 0)
    print(f"  top_amount_avg(20, 5, 0): {cm_amt:.2f} vs {ncm_amt:.2f} - {'OK' if abs(cm_amt - ncm_amt) < 0.001 else 'FAIL'}")
    
    print("\n14. 최고종가 인덱스")
    cm_tops = cm.get_close_tops(20, 10, 0)
    ncm_tops = ncm.get_close_tops(20, 10, 0)
    print(f"  get_close_tops(20, 10, 0):")
    print(f"    인덱스 개수: {len(cm_tops[0])} vs {len(ncm_tops[0])}")
    print(f"    당일봉수: {cm_tops[1]} vs {ncm_tops[1]}")
    
    print("\n15. 연속 조건 개수")
    cm_cons = cm.consecutive_count(lambda i: cm.c(i) > cm.c(i+1), 0)
    ncm_cons = ncm.consecutive_count(lambda i: ncm.c(i) > ncm.c(i+1), 0)
    print(f"  consecutive_count(c>c+1, 0): {cm_cons} vs {ncm_cons} - {'OK' if cm_cons == ncm_cons else 'FAIL'}")
    
    print("\n=== 기술적 지표 테스트 완료 ===")

if __name__ == "__main__":
    simple_technical_test() 