#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
from datetime import datetime

class NumChartManager32Bit:
    """32비트 Python 환경에 최적화된 차트 매니저"""
    
    def __init__(self, code, cycle='mi', tick=3):
        self.cht_dt = None  # ChartData 인스턴스는 외부에서 주입
        self.cycle = cycle
        self.tick = tick
        self.code = code
        
        # 32비트 최적화: float32 사용으로 메모리 절약
        self._np_cache = {}
        self._cache_version = -1
        self._data_length = 0

    def _update_numpy_cache(self):
        """numpy 배열 캐시 업데이트 (32비트 최적화)"""
        if not hasattr(self, 'cht_dt') or self.cht_dt is None:
            return
            
        current_version = self.cht_dt._data_versions.get(self.code, 0)
        
        if self._cache_version == current_version and self._np_cache:
            return
        
        # 원본 데이터 가져오기
        if self.cycle == 'mi':
            cycle_key = f'mi{self.tick}'
            raw_data = self.cht_dt._chart_data.get(self.code, {}).get(cycle_key, [])
        else:
            raw_data = self.cht_dt._chart_data.get(self.code, {}).get(self.cycle, [])
        
        self._data_length = len(raw_data) if raw_data else 0
        
        if not raw_data:
            # 32비트 최적화: float32 사용
            self._np_cache = {
                'c': np.array([], dtype=np.int32),
                'h': np.array([], dtype=np.int32),
                'l': np.array([], dtype=np.int32),
                'o': np.array([], dtype=np.int32),
                'v': np.array([], dtype=np.float32),  # float32로 메모리 절약
                'a': np.array([], dtype=np.float32)   # float32로 메모리 절약
            }
            self._cache_version = current_version
            return
        
        # 32비트 최적화: numpy 배열로 일괄 변환 (float32 사용)
        self._np_cache = {
            'c': np.array([d.get('현재가', 0) for d in raw_data], dtype=np.int32),
            'h': np.array([d.get('고가', 0) for d in raw_data], dtype=np.int32),
            'l': np.array([d.get('저가', 0) for d in raw_data], dtype=np.int32),
            'o': np.array([d.get('시가', 0) for d in raw_data], dtype=np.int32),
            'v': np.array([d.get('거래량', 0) for d in raw_data], dtype=np.float32),  # float32
            'a': np.array([d.get('거래대금', 0) for d in raw_data], dtype=np.float32)  # float32
        }
        
        self._cache_version = current_version

    # 기본 데이터 접근 메서드들 (32비트 최적화)
    def c(self, n: int = 0) -> int:
        """종가 반환"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['c'][n])  # int32 반환
    
    def h(self, n: int = 0) -> int:
        """고가 반환"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['h'][n])  # int32 반환
    
    def l(self, n: int = 0) -> int:
        """저가 반환"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['l'][n])  # int32 반환
    
    def o(self, n: int = 0) -> int:
        """시가 반환"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['o'][n])  # int32 반환
    
    def v(self, n: int = 0) -> int:
        """거래량 반환"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['v'][n])  # float32를 int로 변환
    
    def a(self, n: int = 0) -> int:
        """거래금액 반환 (원화 정수)"""
        self._update_numpy_cache()
        if n >= self._data_length:
            return 0
        return int(self._np_cache['a'][n])  # float32를 int로 변환

    # 이동평균 및 통계 함수들 (32비트 최적화)
    def ma(self, period: int = 20, before: int = 0) -> float:
        """이동평균 - 32비트 최적화"""
        self._update_numpy_cache()
        if before + period > self._data_length:
            return 0.0
        
        closes = self._np_cache['c'][before:before + period]
        return float(np.mean(closes))  # float 반환 (32비트 호환)
    
    def avg(self, value_func, n: int, m: int = 0) -> float:
        """단순이동평균 - 32비트 최적화"""
        if not callable(value_func):
            return float(value_func)
        
        if n <= 0:
            return 0.0
            
        # 함수가 self.c, self.h 등이면 직접 numpy 배열 사용
        if hasattr(value_func, '__self__') and value_func.__self__ is self:
            func_name = value_func.__name__
            if func_name in self._np_cache and m + n <= self._data_length:
                arr = self._np_cache[func_name][m:m + n]
                return float(np.mean(arr))  # float 반환
        
        # fallback: 기존 방식
        total = 0.0
        for i in range(m, m + n):
            total += value_func(i)
        return total / n
    
    def highest(self, value_func, n: int, m: int = 0) -> float:
        """최고값 - 32비트 최적화"""
        if not callable(value_func):
            return float(value_func)
        
        if hasattr(value_func, '__self__') and value_func.__self__ is self:
            func_name = value_func.__name__
            if func_name in self._np_cache and m + n <= self._data_length:
                arr = self._np_cache[func_name][m:m + n]
                return float(np.max(arr))  # float 반환
        
        # fallback
        max_val = float('-inf')
        for i in range(m, m + n):
            val = value_func(i)
            if val > max_val:
                max_val = val
        return max_val if max_val != float('-inf') else 0.0
    
    def lowest(self, value_func, n: int, m: int = 0) -> float:
        """최저값 - 32비트 최적화"""
        if not callable(value_func):
            return float(value_func)
        
        if hasattr(value_func, '__self__') and value_func.__self__ is self:
            func_name = value_func.__name__
            if func_name in self._np_cache and m + n <= self._data_length:
                arr = self._np_cache[func_name][m:m + n]
                return float(np.min(arr))  # float 반환
        
        # fallback
        min_val = float('inf')
        for i in range(m, m + n):
            val = value_func(i)
            if val < min_val:
                min_val = val
        return min_val if min_val != float('inf') else 0.0
    
    def sum(self, value_func, n: int, m: int = 0) -> float:
        """합계 - 32비트 최적화"""
        if not callable(value_func):
            return float(value_func) * n
        
        if hasattr(value_func, '__self__') and value_func.__self__ is self:
            func_name = value_func.__name__
            if func_name in self._np_cache and m + n <= self._data_length:
                arr = self._np_cache[func_name][m:m + n]
                return float(np.sum(arr))  # float 반환
        
        # fallback
        total = 0.0
        for i in range(m, m + n):
            total += value_func(i)
        return total

    # 32비트 최적화된 기술적 지표들
    def rsi(self, period: int = 14, m: int = 0) -> float:
        """RSI 계산 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['c'].size or m + period + 1 > self._data_length:
            return 50.0
        
        closes = self._np_cache['c'][m:m + period + 1]
        price_changes = np.diff(closes)
        
        gains = np.where(price_changes > 0, price_changes, 0)
        losses = np.where(price_changes < 0, -price_changes, 0)
        
        if np.sum(losses) == 0:
            return 100.0
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9, m: int = 0) -> tuple:
        """MACD 계산 - 32비트 최적화"""
        fast_ema = self.eavg(self.c, fast, m)
        slow_ema = self.eavg(self.c, slow, m)
        macd_line = fast_ema - slow_ema
        
        signal_line = self.eavg(self.c, signal, m)
        histogram = macd_line - signal_line
        
        # 32비트 최적화: float 반환 (numpy 타입 제거)
        return (float(macd_line), float(signal_line), float(histogram))
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2, m: int = 0) -> tuple:
        """볼린저 밴드 계산 - 32비트 최적화"""
        middle_band = self.avg(self.c, period, m)
        stdev = self.stdev(self.c, period, m)
        
        upper_band = middle_band + (stdev * std_dev)
        lower_band = middle_band - (stdev * std_dev)
        
        # 32비트 최적화: float 반환
        return (float(upper_band), float(middle_band), float(lower_band))
    
    def stochastic(self, k_period: int = 14, d_period: int = 3, m: int = 0) -> tuple:
        """스토캐스틱 오실레이터 계산 - 32비트 최적화"""
        hh = self.highest(self.h, k_period, m)
        ll = self.lowest(self.l, k_period, m)
        current_close = self.c(m)
        
        # %K 계산
        percent_k = 0
        if hh != ll:
            percent_k = 100 * ((current_close - ll) / (hh - ll))
        
        # %D 계산
        percent_d = self.avg(self.c, d_period, m)
        
        # 32비트 최적화: float 반환
        return (float(percent_k), float(percent_d))
    
    def atr(self, period: int = 14, m: int = 0) -> float:
        """평균 실제 범위(ATR) 계산 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['c'].size or self._data_length < period + 1 + m:
            return 0.0
        
        highs = self._np_cache['h'][m:m + period]
        lows = self._np_cache['l'][m:m + period]
        prev_closes = self._np_cache['c'][m + 1:m + period + 1]
        
        tr1 = highs - lows
        tr2 = np.abs(highs - prev_closes)
        tr3 = np.abs(lows - prev_closes)
        
        true_ranges = np.maximum(tr1, np.maximum(tr2, tr3))
        
        return float(np.mean(true_ranges))

    # 32비트 최적화된 캔들패턴 인식
    def is_doji(self, n: int = 0, threshold: float = 0.1) -> bool:
        """도지 캔들 확인 - 32비트 최적화"""
        o = self.o(n)
        c = self.c(n)
        h = self.h(n)
        l = self.l(n)
        
        body = abs(o - c)
        candle_range = h - l
        
        if candle_range == 0:
            return False
            
        return body / candle_range <= threshold

    def is_shooting_star(self, n: int = 0, upper_ratio: float = 2.0, body_ratio: float = 0.3) -> bool:
        """유성형(슈팅스타) 캔들 패턴 판단 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['c'].size or n >= self._data_length:
            return False
        
        o = self.o(n)
        h = self.h(n)
        l = self.l(n)
        c = self.c(n)
        
        if h <= l or o <= 0 or c <= 0:
            return False
        
        body = abs(c - o)
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        total_range = h - l
        
        if total_range == 0:
            return False
        
        # 조건 검증
        if body > 0:
            upper_body_ratio = upper_shadow / body
            if upper_body_ratio < upper_ratio:
                return False
        else:
            if upper_shadow == 0:
                return False
        
        if body > 0 and lower_shadow > body * 0.5:
            return False
        
        body_percentage = body / total_range
        if body_percentage > body_ratio:
            return False
        
        upper_percentage = upper_shadow / total_range
        if upper_percentage < 0.5:
            return False
        
        return True

    # 32비트 최적화된 스크립트 함수들
    def top_volume_avg(self, n: int = 128, cnt: int = 10, m: int = 1) -> float:
        """거래량 상위 평균 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['v'].size or n <= 0 or cnt <= 0 or m < 0:
            return 0.0
        
        start_idx = m
        end_idx = min(start_idx + n, self._data_length)
        
        if start_idx >= end_idx:
            return 0.0
        
        volumes = self._np_cache['v'][start_idx:end_idx]
        volumes = volumes[volumes > 0]  # 0보다 큰 거래량만
        
        if len(volumes) == 0:
            return 0.0
        
        actual_cnt = min(cnt, len(volumes))
        top_volumes = np.partition(volumes, -actual_cnt)[-actual_cnt:]
        
        return float(np.mean(top_volumes))  # float 반환
    
    def top_amount_avg(self, n: int = 128, cnt: int = 10, m: int = 1) -> float:
        """거래대금 상위 평균 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['a'].size or n <= 0 or cnt <= 0 or m < 0:
            return 0.0
        
        start_idx = m
        end_idx = min(start_idx + n, self._data_length)
        
        if start_idx >= end_idx:
            return 0.0
        
        amounts = self._np_cache['a'][start_idx:end_idx]
        amounts = amounts[amounts > 0]
        
        if len(amounts) == 0:
            return 0.0
        
        actual_cnt = min(cnt, len(amounts))
        top_amounts = np.partition(amounts, -actual_cnt)[-actual_cnt:]
        
        return float(np.mean(top_amounts))  # float 반환

    def get_extremes(self, n: int = 128, m: int = 1) -> dict:
        """극값 계산 - 32비트 최적화"""
        self._update_numpy_cache()
        if not self._np_cache['c'].size or n <= 0:
            return {'hh': 0, 'hc': 0, 'lc': 0, 'll': 0, 'hv': 0, 'lv': 0, 'ha': 0, 'la': 0, 'close': 0, 'bars': 0}
        
        start_idx = m
        end_idx = min(start_idx + n, self._data_length)
        
        if start_idx >= end_idx:
            return {'hh': 0, 'hc': 0, 'lc': 0, 'll': 0, 'hv': 0, 'lv': 0, 'ha': 0, 'la': 0, 'close': 0, 'bars': 0}
        
        # numpy 배열 슬라이싱
        highs = self._np_cache['h'][start_idx:end_idx]
        closes = self._np_cache['c'][start_idx:end_idx]
        lows = self._np_cache['l'][start_idx:end_idx]
        volumes = self._np_cache['v'][start_idx:end_idx]
        amounts = self._np_cache['a'][start_idx:end_idx]
        
        # 한번에 모든 극값 계산 (32비트 최적화)
        result = {
            'hh': int(np.max(highs)),      # int 반환
            'hc': int(np.max(closes)),     # int 반환
            'lc': int(np.min(closes)),     # int 반환
            'll': int(np.min(lows)),       # int 반환
            'hv': int(np.max(volumes)),    # int 반환
            'lv': int(np.min(volumes)),    # int 반환
            'ha': float(np.max(amounts)),  # float 반환
            'la': float(np.min(amounts)),  # float 반환
            'close': int(closes[min(m + 1, len(closes) - 1)] if len(closes) > m + 1 else 0),
            'bars': m + 1
        }
        
        return result

    # 캐시 관리
    def clear_cache(self):
        """캐시 초기화"""
        self._np_cache = {}
        self._cache_version = -1
        self._data_length = 0

    def get_data_length(self) -> int:
        """데이터 길이 반환"""
        self._update_numpy_cache()
        return self._data_length

    def get_raw_data(self):
        """원본 데이터 직접 반환 (32비트 최적화)"""
        self._update_numpy_cache()
        return self._np_cache

# 사용 예시
if __name__ == '__main__':
    # 32비트 최적화된 매니저 생성
    ncm = NumChartManager32Bit('005930', 'mi', 3)
    
    print("32비트 Python 환경에 최적화된 NumChartManager")
    print("메모리 사용량 최적화: float32 사용")
    print("키움 API와 완벽 호환") 