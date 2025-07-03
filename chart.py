from public import dc, gm
from datetime import datetime
from typing import Set, Optional, Any
import json
import numpy as np
import logging
import time
import ast
import traceback
import re
import os
import threading
import hashlib
import marshal
import pickle
import importlib.util
from datetime import timedelta
from collections import deque

class ChartData:
    """
    고성능 차트 데이터 관리 클래스 (메모리 기반, 0.01초 주기 최적화)
    """
    _instance = None
    _creation_lock = threading.Lock()

    # 데이터 크기 제한 (메모리 관리)
    MAX_CANDLES = {
        'mi1': 10000,   # 1분봉: 약 7일치
        'mi3': 3334,    # 3분봉: 약 7일치  
        'mi5': 2000,    # 5분봉: 약 7일치
        'mi10': 1000,   # 10분봉: 약 7일치
        'mi15': 672,    # 15분봉: 약 7일치
        'mi30': 336,    # 30분봉: 약 7일치
        'mi60': 168,    # 60분봉: 약 7일치
        'dy': 1000,     # 일봉: 약 3년치
        'wk': 520,      # 주봉: 약 10년치
        'mo': 120       # 월봉: 약 10년치
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._creation_lock:
                if cls._instance is None:
                    cls._instance = super(ChartData, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        with self._creation_lock:
            if not hasattr(self, "_initialized"):
                # 데이터 저장소 (메모리 기반)
                self._chart_data = {}        # {code: {cycle_key: deque}}
                self._data_versions = {}     # {code: version_number} - 캐시 무효화용
                self._last_update_time = {}  # {code: timestamp} - 마지막 업데이트 시간
                
                # 코드별 락만 사용 (단순화)
                self._code_locks = {}        # {code: RLock}
                self._code_locks_lock = threading.RLock()
                
                self._initialized = True
                logging.debug(f"[{datetime.now()}] ChartData initialized (memory-based) in PID: {os.getpid()}")
    
    def _get_code_lock(self, code: str) -> threading.RLock:
        """코드별 락 가져오기 (빠른 접근)"""
        # 이미 존재하는 락은 락 없이 바로 반환
        if code in self._code_locks:
            return self._code_locks[code]
        
        # 새 락 생성 시에만 보호
        with self._code_locks_lock:
            if code not in self._code_locks:
                self._code_locks[code] = threading.RLock()
            return self._code_locks[code]
    
    def _ensure_data_structure(self, code: str):
        """데이터 구조 사전 할당 (한 번만 실행)"""
        if code not in self._chart_data:
            self._chart_data[code] = {}
            self._data_versions[code] = 0
            self._last_update_time[code] = 0
            
            # 모든 주기별 deque 미리 생성
            for cycle_key, max_size in self.MAX_CANDLES.items():
                self._chart_data[code][cycle_key] = deque(maxlen=max_size)
    
    def _increment_version(self, code: str):
        """데이터 버전 증가 (캐시 무효화)"""
        self._data_versions[code] = self._data_versions.get(code, 0) + 1
        self._last_update_time[code] = time.time()
    
    def set_chart_data(self, code: str, data: list, cycle: str, tick: int = None):
        """차트 데이터 설정 (기존 인터페이스 유지)"""
        
        if not data:
            return
        
        # 1분봉과 일봉만 허용 (기존 로직 유지)
        if cycle == 'mi' and tick != 1:
            logging.warning(f"Only 1-minute data allowed. Rejected: {cycle}, tick={tick}")
            return
        elif cycle not in ['mi', 'dy']:
            logging.warning(f"Only 'mi'(tick=1) and 'dy' cycles allowed. Rejected: {cycle}")
            return
        
        code_lock = self._get_code_lock(code)
        with code_lock:
            # 데이터 구조 준비
            self._ensure_data_structure(code)
            
            if cycle == 'mi' and tick == 1:
                # 1분봉 설정
                self._set_minute_data(code, data)
                # 3분봉 자동 생성
                self._generate_aggregated_minute_data(code, 3)
                
            elif cycle == 'dy':
                # 일봉 설정
                self._set_day_data(code, data)
                # 주봉, 월봉 자동 생성
                self._generate_week_month_data(code)
            
            # 버전 업데이트
            self._increment_version(code)
        
    def _set_minute_data(self, code: str, data: list):
        """1분봉 데이터 설정 (여러 날짜 처리, 마지막 봉에만 전봉누적값 추가)"""
        minute_deque = self._chart_data[code]['mi1']
        minute_deque.clear()
        
        # 최신 MAX_CANDLES개만 유지 (data[0]이 최신)
        recent_data = data[:self.MAX_CANDLES['mi1']]
        
        if not recent_data:
            return
        
        # 마지막 봉(인덱스 0)의 날짜
        last_candle_date = recent_data[0]['체결시간'][:8]
        
        for i, candle_data in enumerate(recent_data):
            candle = candle_data.copy()
            
            if i == 0:  # 마지막 봉(인덱스 0)에만 전봉누적값 추가
                # 같은 날짜의 이전 봉들만 합계 (인덱스 1부터)
                prev_volume = 0
                prev_amount = 0
                
                for j in range(1, len(recent_data)):
                    prev_candle = recent_data[j]
                    prev_candle_date = prev_candle['체결시간'][:8]
                    
                    if prev_candle_date == last_candle_date:  # 같은 날짜만
                        prev_volume += prev_candle['거래량']
                        prev_amount += prev_candle.get('거래대금', 0)
                    else:
                        break  # 다른 날짜가 나오면 중단
                
                candle['전봉누적거래량'] = prev_volume      # 이전 봉까지의 누적 거래량 (같은 날만)
                candle['전봉누적거래대금'] = prev_amount    # 이전 봉까지의 누적 거래대금 (같은 날만)
            
            minute_deque.append(candle)
    
    def _set_day_data(self, code: str, data: list):
        """일봉 데이터 설정"""
        day_deque = self._chart_data[code]['dy']
        day_deque.clear()
        
        # 최신 MAX_CANDLES개만 유지 (data[0]이 최신)
        recent_data = data[:self.MAX_CANDLES['dy']]
        for candle in recent_data:
            day_deque.append(candle)
    
    def _generate_aggregated_minute_data(self, code: str, tick: int):
        """1분봉에서 집계 데이터 생성 (지연 계산)"""
        cycle_key = f'mi{tick}'
        if cycle_key not in self._chart_data[code]:
            return
        
        minute_data = list(self._chart_data[code]['mi1'])
        if not minute_data:
            return
        
        aggregated_data = self._aggregate_minute_data(minute_data, tick)
        
        # 기존 deque 클리어 후 새 데이터 추가
        agg_deque = self._chart_data[code][cycle_key]
        agg_deque.clear()
        for candle in aggregated_data:
            agg_deque.append(candle)
    
    def _generate_week_month_data(self, code: str):
        """일봉에서 주봉/월봉 생성"""
        day_data = list(self._chart_data[code]['dy'])
        if not day_data:
            return
        
        # 주봉 생성
        week_data = self._aggregate_day_data(day_data, 'week')
        week_deque = self._chart_data[code]['wk']
        week_deque.clear()
        for candle in week_data:
            week_deque.append(candle)
        
        # 월봉 생성
        month_data = self._aggregate_day_data(day_data, 'month')
        month_deque = self._chart_data[code]['mo']
        month_deque.clear()
        for candle in month_data:
            month_deque.append(candle)
    
    def get_chart_data(self, code: str, cycle: str, tick: int = None) -> list:
        """차트 데이터 반환 (항상 최신 데이터 보장)"""
        code_lock = self._get_code_lock(code)
        with code_lock:
            # 데이터 구조 확인
            if code not in self._chart_data:
                return []
            
            cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
            
            # 1분봉: 저장된 데이터 그대로 반환
            if cycle_key == 'mi1':
                result = list(self._chart_data[code]['mi1'])
            
            # 분봉: 항상 1분봉에서 동적 생성 (최신 보장)
            elif cycle == 'mi':
                result = self._get_dynamic_aggregated_data(code, tick)
            
            # 일/주/월봉: 저장된 데이터 그대로 반환 (update_chart에서 이미 최신 업데이트됨)
            elif cycle in ['dy', 'wk', 'mo']:
                if cycle_key in self._chart_data[code]:
                    result = list(self._chart_data[code][cycle_key])
                else:
                    result = []
            
            else:
                result = []
        
        return result

    def _get_dynamic_aggregated_data(self, code: str, tick: int) -> list:
        """동적으로 집계 데이터 생성 (캐시되지 않은 분봉)"""
        minute_data = list(self._chart_data[code]['mi1'])
        if not minute_data:
            return []
        
        return self._aggregate_minute_data(minute_data, tick)
    
    def update_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """실시간 차트 업데이트 (기존 인터페이스 유지)"""
        
        code_lock = self._get_code_lock(code)
        with code_lock:
            # 데이터 구조 확인
            if code not in self._chart_data:
                return
            
            # 1분봉 업데이트
            self._update_minute_chart(code, price, volume, amount, datetime_str)
            
            # 일봉 업데이트 (있는 경우에만)
            if self._chart_data[code]['dy']:
                self._update_day_chart(code, price, volume, amount, datetime_str)
                self._update_week_month_chart(code, price, volume, amount, datetime_str)
            
            # 버전 업데이트
            self._increment_version(code)
        
    def _update_minute_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """1분봉 업데이트 (전봉누적값 활용한 간단한 계산)"""
        base_time = datetime_str[:12] + '00'
        minute_deque = self._chart_data[code]['mi1']
        
        # 데이터가 없는 경우
        if not minute_deque:
            new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
            new_candle['전봉누적거래량'] = 0  # 첫봉은 0
            new_candle['전봉누적거래대금'] = 0
            minute_deque.appendleft(new_candle)
            return
        
        # 최신 봉 (인덱스 0) 확인
        latest_candle = minute_deque[0]
        latest_time = latest_candle['체결시간']
        
        if latest_time == base_time:
            # 같은 봉 업데이트
            actual_volume = volume - latest_candle['전봉누적거래량']
            actual_amount = amount - latest_candle['전봉누적거래대금']
            self._update_candle(latest_candle, price, None, actual_volume, actual_amount)
        else:
            # 새봉 생성
            # 1. 현재봉 복사
            new_candle = latest_candle.copy()
            
            # 2. 이전누적값 = 이전누적값 + 현재값
            new_prev_cumulative_volume = latest_candle['전봉누적거래량'] + latest_candle['거래량']
            new_prev_cumulative_amount = latest_candle['전봉누적거래대금'] + latest_candle['거래대금']
            
            # 3. 새시간, 시/고/저 = 현재가, 새로운 거래량/거래대금
            actual_volume = volume - new_prev_cumulative_volume
            actual_amount = amount - new_prev_cumulative_amount
            
            new_candle['체결시간'] = base_time
            new_candle['시가'] = price
            new_candle['고가'] = price
            new_candle['저가'] = price
            new_candle['현재가'] = price
            new_candle['거래량'] = actual_volume
            new_candle['거래대금'] = actual_amount
            new_candle['전봉누적거래량'] = new_prev_cumulative_volume
            new_candle['전봉누적거래대금'] = new_prev_cumulative_amount
            
            # 4. 인덱스 0에 추가
            minute_deque.appendleft(new_candle)

    def _calculate_candle_volume(self, code: str, current_cumulative: int, datetime_str: str) -> int:
        """현재 봉의 실제 거래량 계산 (누적값 - 이전 봉들 합계)"""
        minute_data = self._chart_data[code]['mi1']
        if not minute_data:
            return current_cumulative
        
        current_time = datetime_str[:12] + '00'  # 09:09:00
        previous_total = 0
        
        for candle in minute_data:
            candle_time = candle['체결시간']
            if candle_time < current_time:  # 이전 봉들만
                previous_total += candle['거래량']
            else:
                break  # 현재 봉이나 이후 봉은 제외
        
        return max(0, current_cumulative - previous_total)

    def _calculate_candle_amount(self, code: str, current_cumulative: int, datetime_str: str) -> int:
        """현재 봉의 실제 거래대금 계산 (누적값 - 이전 봉들 합계)"""
        minute_data = self._chart_data[code]['mi1']
        if not minute_data:
            return current_cumulative
        
        current_time = datetime_str[:12] + '00'  # 09:09:00
        previous_total = 0
        
        for candle in minute_data:
            candle_time = candle['체결시간']
            if candle_time < current_time:  # 이전 봉들만
                previous_total += candle.get('거래대금', 0)
            else:
                break  # 현재 봉이나 이후 봉은 제외
        
        return max(0, current_cumulative - previous_total)

    def _update_day_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """일봉 업데이트"""
        today = datetime_str[:8]
        day_deque = self._chart_data[code]['dy']
        
        if not day_deque:
            return
        
        latest_candle = day_deque[0]  # 인덱스 0이 최신
        if latest_candle['일자'] == today:
            self._update_candle(latest_candle, price, None, volume, amount)
        else:
            new_candle = {
                '종목코드': code,
                '일자': today,
                '시가': price,
                '고가': price,
                '저가': price,
                '현재가': price,
                '거래량': volume,
                '거래대금': amount
            }
            day_deque.appendleft(new_candle)  # 인덱스 0에 추가
    
    def _update_week_month_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """주봉/월봉 업데이트"""
        today = datetime_str[:8]
        
        try:
            year = int(today[:4])
            month = int(today[4:6])
            day = int(today[6:8])
            date_obj = datetime(year, month, day)
        except ValueError:
            return
        
        # 주봉 업데이트
        self._update_period_chart(code, price, volume, amount, date_obj, 'wk', 'week')
        
        # 월봉 업데이트
        self._update_period_chart(code, price, volume, amount, date_obj, 'mo', 'month')
    
    def _update_period_chart(self, code: str, price: int, volume: int, amount: int, date_obj: datetime, cycle_key: str, period_type: str):
        """주봉/월봉 공통 업데이트"""
        period_deque = self._chart_data[code][cycle_key]
        if not period_deque:
            return
        
        # 현재 주기 키 계산
        if period_type == 'week':
            days_since_monday = date_obj.weekday()
            monday = date_obj - timedelta(days=days_since_monday)
            current_period_key = monday.strftime('%Y%m%d')
        else:  # month
            current_period_key = date_obj.strftime('%Y%m01')
        
        latest_candle = period_deque[0]  # 인덱스 0이 최신
        if latest_candle['일자'] == current_period_key:
            self._update_candle(latest_candle, price, None, volume, amount)
        else:
            new_candle = {
                '종목코드': code,
                '일자': current_period_key,
                '시가': price,
                '고가': price,
                '저가': price,
                '현재가': price,
                '거래량': volume,
                '거래대금': amount
            }
            period_deque.appendleft(new_candle)  # 인덱스 0에 추가
    
    def is_code_registered(self, code: str) -> bool:
        """종목 등록 여부 확인 (메모리 기반으로 단순화)"""
        return code in self._chart_data and bool(self._chart_data[code].get('mi1') and bool(self._chart_data[code].get('dy')))
    
    def clean_up_safe(self):
        """메모리 정리 (메모리 기반으로 단순화)"""
        try:
            # 모든 데이터 클리어
            for code_data in self._chart_data.values():
                for deque_obj in code_data.values():
                    if hasattr(deque_obj, 'clear'):
                        deque_obj.clear()
            
            self._chart_data.clear()
            self._data_versions.clear()
            self._last_update_time.clear()
            
            # 락 정리
            with self._code_locks_lock:
                self._code_locks.clear()
            
            logging.debug(f"[{datetime.now()}] ChartData cleaned up in PID: {os.getpid()}")
            
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in cleanup: {str(e)}")
    
    # 헬퍼 함수들 (기존 로직 유지)
    def _create_candle(self, code, time_str, close, open, high, low, volume, amount, is_missing=False):
        """캔들 객체 생성"""
        candle = {
            '종목코드': code,
            '체결시간': time_str,
            '시가': open,
            '고가': high,
            '저가': low,
            '현재가': close,
            '거래량': volume,
            '거래대금': amount
        }
        if is_missing:
            candle['is_missing'] = True
        return candle
    
    def _update_candle(self, candle, price, open_price=None, volume=None, amount=None):
        """캔들 업데이트"""
        candle['현재가'] = price
        candle['고가'] = max(candle['고가'], price)
        candle['저가'] = min(candle['저가'], price)
        
        if open_price is not None:
            candle['시가'] = open_price
        if volume is not None:
            candle['거래량'] = volume
        if amount is not None:
            candle['거래대금'] = amount
        
        if 'is_missing' in candle:
            del candle['is_missing']
    
    def _calculate_tick_time(self, datetime_str: str, tick: int) -> str:
        """틱 시간 계산"""
        if len(datetime_str) < 12:
            return datetime_str
        
        hour = int(datetime_str[8:10])
        minute = int(datetime_str[10:12])
        total_minutes = hour * 60 + minute
        
        tick_start = (total_minutes // tick) * tick
        return f"{datetime_str[:8]}{tick_start//60:02d}{tick_start%60:02d}00"
    
    def _aggregate_minute_data(self, minute_data, tick):
        """1분봉 데이터를 특정 tick으로 집계 (기존 로직 유지)"""
        if not minute_data:
            return []
        
        grouped_data = {}
        
        for candle in minute_data:
            dt_str = candle['체결시간']
            if len(dt_str) < 12:
                continue
            
            hour = int(dt_str[8:10])
            minute = int(dt_str[10:12])
            total_minutes = hour * 60 + minute
            tick_start = (total_minutes // tick) * tick
            group_hour = tick_start // 60
            group_minute = tick_start % 60
            group_key = f"{dt_str[:8]}{group_hour:02d}{group_minute:02d}00"
            
            if group_key not in grouped_data:
                grouped_data[group_key] = {
                    '종목코드': candle['종목코드'],
                    '체결시간': group_key,
                    '시가': candle['시가'],
                    '고가': candle['고가'],
                    '저가': candle['저가'],
                    '현재가': candle['현재가'],
                    '거래량': candle['거래량'],
                    '거래대금': candle.get('거래대금', 0)
                }
            else:
                group = grouped_data[group_key]
                group['현재가'] = candle['현재가']
                group['고가'] = max(group['고가'], candle['고가'])
                group['저가'] = min(group['저가'], candle['저가'])
                group['거래량'] += candle['거래량']
                group['거래대금'] += candle.get('거래대금', 0)
        
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['체결시간'], reverse=True)
        return result
    
    def _aggregate_day_data(self, day_data, period_type):
        """일봉 데이터를 주봉/월봉으로 집계 (각 일봉 거래량 합계)"""
        if not day_data:
            return []
        
        grouped_data = {}
        
        for candle in day_data:
            date_str = candle['일자']
            if len(date_str) != 8:
                continue
            
            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                
                if period_type == 'week':
                    date_obj = datetime(year, month, day)
                    days_since_monday = date_obj.weekday()
                    monday = date_obj - timedelta(days=days_since_monday)
                    group_key = monday.strftime('%Y%m%d')
                else:  # month
                    group_key = f"{year:04d}{month:02d}01"
                
            except ValueError:
                continue
            
            if group_key not in grouped_data:
                grouped_data[group_key] = {
                    '종목코드': candle['종목코드'],
                    '일자': group_key,
                    '시가': candle['시가'],
                    '고가': candle['고가'],
                    '저가': candle['저가'],
                    '현재가': candle['현재가'],
                    '거래량': candle['거래량'],           # 첫 번째 값으로 초기화
                    '거래대금': candle.get('거래대금', 0)  # 첫 번째 값으로 초기화
                }
            else:
                group = grouped_data[group_key]
                group['현재가'] = candle['현재가']
                group['고가'] = max(group['고가'], candle['고가'])
                group['저가'] = min(group['저가'], candle['저가'])
                # 각 일봉의 거래량/거래대금 합계
                group['거래량'] += candle['거래량']
                group['거래대금'] += candle.get('거래대금', 0)
        
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['일자'], reverse=True)
        return result
    
class ChartManager:
    def __init__(self, code, cycle='mi', tick=3):
        self.cht_dt = ChartData()
        self.cycle = cycle  # 'mo', 'wk', 'dy', 'mi' 중 하나
        self.tick = tick    # 분봉일 경우 주기
        self._data_cache = {}  # 종목별 데이터 캐시 {code: data}
        self.code = code    # 종목코드 (없으면 컨텍스트에서 가져옴)

    def _get_data(self) -> list:
        """버전 기반 캐싱으로 최신 데이터 보장"""
        # 현재 데이터 버전 확인
        current_version = self.cht_dt._data_versions.get(self.code, 0)
        cache_key = f"{self.code}_{self.cycle}_{self.tick}"
        
        # 캐시 버전 관리 초기화
        if not hasattr(self, '_cache_versions'):
            self._cache_versions = {}
        
        # 캐시가 유효한지 확인 (버전 체크)
        if (cache_key in self._data_cache and 
            self._cache_versions.get(cache_key) == current_version):
            return self._data_cache[cache_key]
        
        # 캐시 무효화 후 새 데이터 로드
        new_data = self._load_chart_data(self.code)
        self._data_cache[cache_key] = new_data
        self._cache_versions[cache_key] = current_version
        
        return new_data
    
    def _load_chart_data(self, code: str) -> list:
        """차트 데이터 로드 및 변환"""
        data = self.cht_dt.get_chart_data(code, self.cycle, self.tick)
        
        # 데이터 변환 (API 형식 -> 내부 형식)
        result = []
        if self.cycle == 'mi':
            for item in data:
                result.append({
                    'time': item['체결시간'],
                    'open': item['시가'],
                    'high': item['고가'],
                    'low': item['저가'],
                    'close': item['현재가'],
                    'volume': item['거래량'],
                    'amount': item.get('거래대금', 0)
                })
        else:
            for item in data:
                result.append({
                    'date': item['일자'],
                    'open': item['시가'],
                    'high': item['고가'],
                    'low': item['저가'],
                    'close': item['현재가'],
                    'volume': item['거래량'],
                    'amount': item['거래대금']
                })
        return result
    
    def _get_value(self, n: int, key: str, default=0):
        """지정된 위치(n)의 데이터 값 가져오기"""
        data = self._get_data()
        
        # n이 데이터 범위를 벗어나면 기본값 반환
        if not data or n >= len(data):
            return default
        
        item = data[n]
        
        # 키에 따라 적절한 값 반환
        if key == 'open':
            return item['open']
        elif key == 'high':
            return item['high']
        elif key == 'low':
            return item['low']
        elif key == 'close':
            return item['close']
        elif key == 'volume':
            return item['volume']
        elif key == 'amount':
            return item.get('amount', 0)
        elif key == 'time' and self.cycle == 'mi':
            return item.get('time', '')
        elif key == 'date' and self.cycle != 'mi':
            return item.get('date', '')
        
        return default

    def _get_values(self, func, n: int, m: int = 0) -> list:
            """지정된 함수를 통해 n개의 값을 배열로 가져오기"""
            values = []
            for i in range(m, m + n):
                if callable(func):
                    values.append(func(i))
                else:
                    # func가 함수가 아니면 그대로 사용 (상수값)
                    values.append(func)
            return values
        
    def clear_cache(self, code=None):
        """특정 코드 또는 전체 캐시 초기화"""
        # if code is None:
        #     code = self._get_code()
            
        if code in self._data_cache:
            del self._data_cache[code]
        else:
            self._data_cache.clear()
    
    # 기본 값 반환 함수들
    def c(self, n: int = 0) -> float:
        """종가 반환"""
        return self._get_value(n, 'close')
    
    def o(self, n: int = 0) -> float:
        """시가 반환"""
        return self._get_value(n, 'open')
    
    def h(self, n: int = 0) -> float:
        """고가 반환"""
        return self._get_value(n, 'high')
    
    def l(self, n: int = 0) -> float:
        """저가 반환"""
        return self._get_value(n, 'low')
    
    def v(self, n: int = 0) -> int:
        """거래량 반환"""
        return int(self._get_value(n, 'volume', 0))
    
    def a(self, n: int = 0) -> float:
        """거래금액 반환"""
        return self._get_value(n, 'amount')
    
    def time(self, n: int = 0) -> str:
        """시간 반환"""
        if self.cycle != 'mi': return ''
        return self._get_value(n, 'time', '')
    
    def today(self) -> str:
        """오늘 날짜 반환"""
        return datetime.now().strftime('%Y%m%d')

# 계산 함수들
    def ma(self, n: int = 20, m: int = 0) -> float:
        """종가 이동평균 반환"""
        return self.avg(self.c, n, m)
    
    def avg(self, a, n: int, m: int = 0) -> float:
        """단순이동평균 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        return sum(values) / len(values)
    
    def eavg(self, a, n: int, m: int = 0) -> float:
        """지수이동평균 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        
        alpha = 2 / (n + 1)
        result = values[0]
        for i in range(1, len(values)):
            result = alpha * values[i] + (1 - alpha) * result
        return result
    
    def wavg(self, a, n: int, m: int = 0) -> float:
        """가중이동평균 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        
        weights = [i+1 for i in range(len(values))]
        return sum(v * w for v, w in zip(values, weights)) / sum(weights)
    
    def highest(self, a, n: int, m: int = 0) -> float:
        """가장 높은 값 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        return max(values)
    
    def lowest(self, a, n: int, m: int = 0) -> float:
        """가장 낮은 값 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        return min(values)
    
    def stdev(self, a, n: int, m: int = 0) -> float:
        """표준편차 계산"""
        values = self._get_values(a, n, m)
        if not values or len(values) < 2: return 0.0
        return np.std(values)
    
    def sum(self, a, n: int, m: int = 0) -> float:
        """합계 계산"""
        values = self._get_values(a, n, m)
        if not values: return 0.0
        return sum(values)

# 신호 함수들
    def cross_down(self, a, b) -> bool:
        """a가 b를 하향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(1), a(0)
            b_prev, b_curr = b(1), b(0)
            return a_prev >= b_prev and a_curr < b_curr
        return False
    
    def cross_up(self, a, b) -> bool:
        """a가 b를 상향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(1), a(0)
            b_prev, b_curr = b(1), b(0)
            return a_prev <= b_prev and a_curr > b_curr
        return False
    
    def bars_since(self, condition) -> int:
        """조건이 만족된 이후 지나간 봉 개수"""
        count = 0
        for i in range(len(self._get_data())):
            if condition(i):
                return count
            count += 1
        return count
    
    def highest_since(self, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최고값"""
        condition_met = 0
        highest_val = float('-inf')
        
        for i in range(len(self._get_data())):
            if condition(i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(j)
            highest_val = max(highest_val, val)
        
        return highest_val
    
    def lowest_since(self, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최저값"""
        condition_met = 0
        lowest_val = float('inf')
        
        for i in range(len(self._get_data())):
            if condition(i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(j)
            lowest_val = min(lowest_val, val)
        
        return lowest_val
    
    def value_when(self, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 시점의 data_func 값"""
        condition_met = 0
        
        for i in range(len(self._get_data())):
            if condition(i):
                condition_met += 1
                if condition_met == nth:
                    return data_func(i)
        
        return 0.0
    
# 수학 함수들
    def min_value(self, a, b):
        """두 값 중 최소값 반환"""
        return min(a, b)
    
    def max_value(self, a, b):
        """두 값 중 최대값 반환"""
        return max(a, b)
    
    def pow(self, a, n):
        """a의 n제곱 반환"""
        return a ** n
    
    def sqrt(self, a):
        """제곱근 반환"""
        return a ** 0.5 if a >= 0 else 0
    
    def log(self, a, base=10):
        """로그 값 반환"""
        import math
        try:
            return math.log(a, base) if a > 0 else 0
        except:
            return 0
    
    def exp(self, a):
        """지수 함수 값 반환"""
        import math
        try:
            return math.exp(a)
        except:
            return 0
    
    def div(self, a, b, default=0):
        """안전한 나눗셈 (0으로 나누기 방지)"""
        return a / b if b != 0 else default
    
    # 논리 함수들
    def iif(self, condition, true_value, false_value):
        """조건에 따른 값 선택 (조건부 삼항 연산자)"""
        return true_value if condition else false_value
    
    def all_true(self, condition_list):
        """모든 조건이 참인지 확인"""
        return all(condition_list)
    
    def any_true(self, condition_list):
        """하나라도 조건이 참인지 확인"""
        return any(condition_list)

    # ChartManager에 추가할 메소드
    def indicator(self, func, *args):
        """지표 계산 결과를 함수처럼 사용 가능한 객체 반환"""
        # 내부 함수 생성 (클로저)
        def callable_indicator(offset=0):
            return func(*args, offset)
        
        # 함수 반환
        return callable_indicator
    
# 보조지표 계산 함수들
    def rsi(self, period: int = 14, m: int = 0) -> float:
        """상대강도지수(RSI) 계산"""
        values = self._get_values(self.c, period + 1, m)
        if len(values) < period + 1:
            return 50  # 기본값
        
        gains = []
        losses = []
        for i in range(1, len(values)):
            change = values[i-1] - values[i]  # 이전 값 - 현재 값 (역순이므로)
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        else:
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9, m: int = 0) -> tuple:
        """MACD(Moving Average Convergence Divergence) 계산
        Returns: (MACD 라인, 시그널 라인, 히스토그램)
        """
        # 빠른 EMA
        fast_ema = self.eavg(self.c, fast, m)
        # 느린 EMA
        slow_ema = self.eavg(self.c, slow, m)
        # MACD 라인
        macd_line = fast_ema - slow_ema
        
        # 시그널 라인
        # 참고: 실제로는 MACD 값의 이력이 필요하나 단순화를 위해 현재 값만 사용
        signal_line = self.eavg(self.c, signal, m)
        
        # 히스토그램
        histogram = macd_line - signal_line
        
        return (macd_line, signal_line, histogram)
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2, m: int = 0) -> tuple:
        """볼린저 밴드 계산
        Returns: (상단 밴드, 중간 밴드(SMA), 하단 밴드)
        """
        middle_band = self.avg(self.c, period, m)
        stdev = self.stdev(self.c, period, m)
        
        upper_band = middle_band + (stdev * std_dev)
        lower_band = middle_band - (stdev * std_dev)
        
        return (upper_band, middle_band, lower_band)
    
    def stochastic(self, k_period: int = 14, d_period: int = 3, m: int = 0) -> tuple:
        """스토캐스틱 오실레이터 계산
        Returns: (%K, %D)
        """
        # 최고가, 최저가 가져오기
        highest_high = self.highest(self.h, k_period, m)
        lowest_low = self.lowest(self.l, k_period, m)
        
        # 현재 종가
        current_close = self.c(m)
        
        # %K 계산
        percent_k = 0
        if highest_high != lowest_low:
            percent_k = 100 * ((current_close - lowest_low) / (highest_high - lowest_low))
        
        # %D 계산 (간단한 이동평균 사용)
        # 참고: 실제로는 %K 값의 이력이 필요하나 단순화를 위해 현재 값으로 대체
        percent_d = self.avg(self.c, d_period, m)
        
        return (percent_k, percent_d)
    
    def atr(self, period: int = 14, m: int = 0) -> float:
        """평균 실제 범위(ATR) 계산"""
        data = self._get_data()
        if len(data) < period + 1 + m:
            return 0
        
        tr_values = []
        for i in range(m, m + period):
            if i + 1 >= len(data):
                break
                
            # 실제 범위 계산
            high = data[i]['high']
            low = data[i]['low']
            prev_close = data[i+1]['close']
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        # ATR 계산
        if not tr_values:
            return 0
        return sum(tr_values) / len(tr_values)
    
# 캔들패턴 인식 함수들
    def is_doji(self, n: int = 0, threshold: float = 0.1) -> bool:
        """도지 캔들 확인 (시가와 종가의 차이가 매우 작은 캔들)"""
        o = self.o(n)
        c = self.c(n)
        h = self.h(n)
        l = self.l(n)
        
        # 몸통 크기
        body = abs(o - c)
        # 전체 캔들 크기
        candle_range = h - l
        
        if candle_range == 0:
            return False
            
        # 몸통이 전체 캔들의 threshold% 이하이면 도지로 간주
        return body / candle_range <= threshold
    
    def is_hammer(self, n: int = 0) -> bool:
        """망치형 캔들 확인 (아래 꼬리가 긴 캔들)"""
        o = self.o(n)
        c = self.c(n)
        h = self.h(n)
        l = self.l(n)
        
        # 시가/종가 중 낮은 값
        lower_val = min(o, c)
        # 몸통 크기
        body = abs(o - c)
        # 아래 꼬리 크기
        lower_shadow = lower_val - l
        
        # 전체 캔들 크기
        candle_range = h - l
        
        if candle_range == 0 or body == 0:
            return False
            
        # 아래 꼬리가 몸통의 2배 이상이고, 전체 캔들의 1/3 이상이면 망치형으로 간주
        return (lower_shadow >= 2 * body) and (lower_shadow / candle_range >= 0.33)
    
    def is_engulfing(self, n: int = 0, bullish: bool = True) -> bool:
        """포괄 패턴 확인 (이전 캔들을 완전히 덮는 형태)
        bullish=True: 상승 포괄 패턴, bullish=False: 하락 포괄 패턴
        """
        if n + 1 >= len(self._get_data()):
            return False
            
        curr_o = self.o(n)
        curr_c = self.c(n)
        prev_o = self.o(n + 1)
        prev_c = self.c(n + 1)
        
        if bullish:
            # 상승 포괄 패턴: 현재 캔들이 상승이고, 이전 캔들은 하락이며
            # 현재 캔들이 이전 캔들의 시가/종가 범위를 모두 포함
            return (curr_c > curr_o and  # 현재 캔들이 상승
                    prev_c < prev_o and  # 이전 캔들이 하락
                    curr_o <= prev_c and  # 현재 시가가 이전 종가보다 낮거나 같음
                    curr_c >= prev_o)     # 현재 종가가 이전 시가보다 높거나 같음
        else:
            # 하락 포괄 패턴: 현재 캔들이 하락이고, 이전 캔들은 상승이며
            # 현재 캔들이 이전 캔들의 시가/종가 범위를 모두 포함
            return (curr_c < curr_o and   # 현재 캔들이 하락
                    prev_c > prev_o and   # 이전 캔들이 상승
                    curr_o >= prev_c and   # 현재 시가가 이전 종가보다 높거나 같음
                    curr_c <= prev_o)      # 현재 종가가 이전 시가보다 낮거나 같음
        
# 추세 분석 함수들
    def is_uptrend(self, period: int = 14, m: int = 0) -> bool:
        """상승 추세 여부 확인 (단순하게 종가가 이동평균보다 높은지 확인)"""
        current_close = self.c(m)
        avg_close = self.avg(self.c, period, m)
        
        return current_close > avg_close
    
    def is_downtrend(self, period: int = 14, m: int = 0) -> bool:
        """하락 추세 여부 확인 (단순하게 종가가 이동평균보다 낮은지 확인)"""
        current_close = self.c(m)
        avg_close = self.avg(self.c, period, m)
        
        return current_close < avg_close
    
    def momentum(self, period: int = 10, m: int = 0) -> float:
        """모멘텀 계산 (현재 종가와 n기간 이전 종가의 차이)"""
        current = self.c(m)
        previous = self.c(m + period)
        
        return current - previous

    # 데이터 변환 및 집계 함수들
    def rate_of_change(self, period: int = 1, m: int = 0) -> float:
        """변화율 계산 (현재 값과 n기간 이전 값의 백분율 변화)"""
        current = self.c(m)
        previous = self.c(m + period)
        
        if previous == 0:
            return 0
        
        return ((current - previous) / previous) * 100
    
    def normalized_volume(self, period: int = 20, m: int = 0) -> float:
        """거래량을 평균 거래량 대비 비율로 정규화"""
        current_volume = self.v(m)
        avg_volume = self.avg(self.v, period, m)
        
        if avg_volume == 0:
            return 0
        
        return current_volume / avg_volume
    
    def accumulation(self, values: list) -> list:
        """값의 누적 합계 계산"""
        result = []
        total = 0
        
        for val in values:
            total += val
            result.append(total)
            
        return result
    
    def streak_count(self, condition_func) -> int:
        """연속된 조건 만족 횟수 계산"""
        count = 0
        data = self._get_data()
        
        for i in range(len(data)):
            if condition_func(i):
                count += 1
            else:
                break
                
        return count
    
    def detect_pattern(self, pattern_func, length: int) -> bool:
        """특정 패턴 감지 (length 길이의 데이터에 pattern_func 적용)"""
        if len(self._get_data()) < length:
            return False
            
        # pattern_func에 데이터 전달하여 패턴 확인
        return pattern_func(length)

class ScriptManager:
    """
    투자 스크립트 관리 및 실행 클래스 (개선 버전)
    
    사용자 스크립트 실행, 검증, 관리(사용자 함수 포함)
    """
    # 허용된 Python 기능 목록 (whitelist 방식)
    ALLOWED_MODULES = ['re', 'math', 'datetime', 'random', 'logging', 'json', 'collections']

    # 허용된 Python 내장 함수 및 타입
    ALLOWED_BUILTINS = [
        # 기본 데이터 타입
        'int', 'float', 'str', 'bool', 'list', 'dict', 'set', 'tuple',

        # 데이터 처리 함수
        'len', 'max', 'min', 'sum', 'abs', 'all', 'any', 'round', 'sorted',
        'enumerate', 'zip', 'range',

        # 형변환 함수
        'int', 'float', 'str', 'bool', 'list', 'dict', 'set', 'tuple',
    ]

    # 허용되지 않는 문법 패턴
    FORBIDDEN_PATTERNS = [
        r'import\s+(?!(' + '|'.join(ALLOWED_MODULES) + ')$)',   # 허용된 모듈만 임포트 가능
        r'open\s*\(',                                           # 파일 열기 금지
        r'exec\s*\(',                                           # exec() 사용 금지
        r'eval\s*\(',                                           # eval() 사용 금지
        r'__import__',                                          # __import__ 사용 금지
        r'subprocess',                                          # subprocess 모듈 금지
        r'os\.',                                                # os 모듈 사용 금지
        r'sys\.',                                               # sys 모듈 사용 금지
        r'while\s+.*:',                                         # while 루프 금지 (무한 루프 방지)
    ]

    def __init__(self, script_file=dc.fp.scripts_file):
        """초기화
        
        Args:
            script_file: 스크립트 저장 파일 경로
        """
        self.script_file = script_file
        self.scripts = {}  # {script_name: {script: str, vars: dict, type: str, desc: str}}
        self.user_funcs = {}  # {script_name: {script: str, vars: dict, type: str, desc: str}}
        self._running_scripts = set()  # 실행 중인 스크립트 추적
        self._compiled_scripts = {}  # 컴파일된 스크립트 캐시 {script_name: code_obj}
        self.cht_dt = ChartData()  # 차트 데이터 관리자

        import datetime
        self.current_program_version = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        self._init_program_version()        

        # 파일에서 스크립트와 사용자 함수 로드
        self._load_scripts()

    def _init_program_version(self):
        """프로그램 버전 초기화"""
        try:
            cache_dir = os.path.dirname(self.script_file) or "."
            cache_dir = os.path.join(cache_dir, "cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            version_file = os.path.join(cache_dir, "program_version.txt")
            with open(version_file, "w") as f:
                f.write(self.current_program_version)
            
            self.cache_dir = cache_dir
            logging.info(f"프로그램 버전 초기화: {self.current_program_version}")
        except Exception as e:
            logging.error(f"프로그램 버전 초기화 오류: {e}")
            self.cache_dir = "."

    def _update_script_version(self, script_name: str):
        """스크립트 버전을 현재 프로그램 버전으로 업데이트"""
        try:
            version_file = os.path.join(self.cache_dir, f"{script_name}_version.txt")
            with open(version_file, "w") as f:
                f.write(self.current_program_version)
        except Exception as e:
            logging.error(f"스크립트 버전 업데이트 오류 ({script_name}): {e}")

    def _is_current_version(self, script_name: str) -> bool:
        """스크립트가 현재 버전인지 확인"""
        try:
            version_file = os.path.join(self.cache_dir, f"{script_name}_version.txt")
            if os.path.exists(version_file):
                with open(version_file) as f:
                    script_version = f.read().strip()
                return script_version == self.current_program_version
            return False
        except Exception as e:
            logging.error(f"버전 확인 오류 ({script_name}): {e}")
            return False

    def _load_scripts(self):
        """스크립트 파일에서 스크립트 로드"""
        try:
            if os.path.exists(self.script_file):
                with open(self.script_file, 'r', encoding='utf-8') as f:
                    self.scripts = json.load(f)
                logging.info(f"스크립트 {len(self.scripts)}개 로드 완료")
            else:
                logging.warning(f"스크립트 파일 없음: {self.script_file}")
                self.scripts = {}
        except json.JSONDecodeError as e:
            logging.error(f"스크립트 파일 형식 오류: {e}")
            self.scripts = {}
    
    def _save_scripts(self):
        """스크립트를 파일에 저장"""
        try:
            with open(self.script_file, 'w', encoding='utf-8') as f:
                json.dump(self.scripts, f, ensure_ascii=False, indent=4)
            logging.info(f"스크립트 {len(self.scripts)}개 저장 완료")
            return True
        except Exception as e:
            logging.error(f"스크립트 저장 오류: {e}")
            return False
    
    def get_scripts(self):
        """저장된 모든 스크립트 반환"""
        return self.scripts
    
    def get_script(self, script_name: str):
        """이름으로 스크립트 가져오기"""
        return self.scripts.get(script_name, {})
    
    def get_script_type(self, result):
        """결과값의 타입 확인"""
        if result is None: return 'error'
        elif isinstance(result, bool): return 'bool'
        elif isinstance(result, float): return 'float'
        elif isinstance(result, int): return 'int'
        elif isinstance(result, str): return 'str'
        elif isinstance(result, list): return 'list'
        elif isinstance(result, dict): return 'dict'
        elif isinstance(result, tuple): return 'tuple'
        elif isinstance(result, set): return 'set'
        else: return type(result).__name__

    def _validate_script_syntax(self, script: str, script_name: str) -> dict:
        """스크립트 구문 검증
        
        Args:
            script: 검증할 스크립트 코드
            script_name: 스크립트 이름
            
        Returns:
            dict: {'success': bool, 'error': str}
        """
        # 스크립트 이름 유효성 검사
        if not self._is_valid_identifier(script_name):
            return {'success': False, 'error': f"유효하지 않은 스크립트 이름: {script_name}"}
        
        # 구문 분석
        try:
            ast.parse(script)
        except SyntaxError as e:
            script_lines = script.splitlines()
            if e.lineno <= len(script_lines):
                error_line = script_lines[e.lineno-1].strip()
                error_msg = f"구문 오류 (행 {e.lineno}): {e.msg} → 수정: {error_line}"
            else:
                error_msg = f"구문 오류 (행 {e.lineno}): {e.msg}"
            return {'success': False, 'error': error_msg}
        except Exception as e:
            return {'success': False, 'error': f"스크립트 준비 오류: {type(e).__name__} - {e}"}
        
        # 보안 검증
        if self._has_forbidden_syntax(script):
            return {'success': False, 'error': "보안 위반 코드 포함"}
        
        return {'success': True, 'error': None}

    def _execute_validated_script(self, script_name: str, script: str, kwargs: dict) -> dict:
        """검증된 스크립트 실행 (공통 실행 로직)
        
        Args:
            script_name: 스크립트 이름
            script: 스크립트 코드
            kwargs: 실행 매개변수
            
        Returns:
            dict: 실행 결과
        """
        start_time = time.time()
        
        # 결과 초기화
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
            'exec_time': 0,
        }
        
        # 종목코드 검증
        code = kwargs.get('code')
        if code is None:
            result_dict['error'] = "종목코드가 지정되지 않았습니다."
            result_dict['logs'].append('ERROR: 종목코드가 지정되지 않았습니다.')
            return result_dict
        
        # 순환 참조 방지
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_name}"
            result_dict['logs'].append(f'ERROR: 순환 참조 감지: {script_name}')
            return result_dict
        
        # 실행 중인 스크립트에 추가
        self._running_scripts.add(script_key)
        
        try:
            # 실행 환경 준비
            globals_dict, script_logs = self._prepare_execution_globals(script_name)
            locals_dict = {}
            
            # 래퍼 스크립트 생성
            wrapped_script = self.make_wrapped_script(script, kwargs, self._indent_script)
            
            # 컴파일 및 실행
            code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
            
            # kwargs 변수 설정
            locals_dict['kwargs'] = kwargs
            globals_dict['_current_kwargs'] = kwargs
            
            # 코드 실행
            exec(code_obj, globals_dict, locals_dict)
            exec_time = time.time() - start_time
            
            # 실행 시간 경고 (기준 완화: 0.1초)
            if exec_time > 0.1:
                warning_msg = f"스크립트 실행 시간 초과 ({script_name}:{code}): {exec_time:.4f}초"
                logging.warning(warning_msg)
                script_logs.append(f'WARNING: {warning_msg}')
            
            # 실행 결과 가져오기
            script_result = locals_dict.get('result')
            
            result_dict['success'] = True
            result_dict['result'] = script_result
            result_dict['exec_time'] = exec_time
            result_dict['logs'] = script_logs
            
            return result_dict
            
        except Exception as e:
            tb = traceback.format_exc()
            
            # 상세한 에러 정보 생성
            detailed_error = self._get_script_error_location(tb, script)
            
            # 에러 로그 추가
            if not hasattr(script_logs, 'append'):
                script_logs = []
            
            script_logs.append(f"ERROR: {detailed_error}")
            script_logs.append(f"TRACEBACK: {tb}")
            
            # 시스템 로깅
            logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}\n{tb}")
            
            result_dict['error'] = detailed_error
            result_dict['logs'] = script_logs
            return result_dict
            
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if script_key in self._running_scripts:
                self._running_scripts.remove(script_key)
            
            # 실행 시간 기록
            result_dict['exec_time'] = time.time() - start_time

    def run_script(self, script_name, script_contents=None, check_only=False, kwargs=None):
        """스크립트 검사 및 실행 (검사용)
        
        Args:
            script_name: 스크립트 이름
            script_contents: 직접 제공된 스크립트 내용
            check_only: 검사만 수행 여부
            kwargs: 실행 매개변수
            
        Returns:
            dict: 실행 결과
        """
        if kwargs is None:
            kwargs = {}
        
        # 결과 초기화
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
            'exec_time': 0,
        }
        
        # 스크립트 내용 준비
        if script_contents is None:
            script_data = self.get_script(script_name)
            script_contents = script_data.get('script', '')
        
        if not script_contents:
            result_dict['error'] = f"스크립트 없음: {script_name}"
            return result_dict
        
        # 구문 검증
        validation_result = self._validate_script_syntax(script_contents, script_name)
        if not validation_result['success']:
            result_dict['error'] = validation_result['error']
            return result_dict
        
        # 실행
        exec_result = self._execute_validated_script(script_name, script_contents, kwargs)
        
        # 결과 복사
        result_dict['success'] = exec_result['success']
        result_dict['result'] = exec_result['result']
        result_dict['error'] = exec_result['error']
        result_dict['logs'] = exec_result['logs']
        result_dict['exec_time'] = exec_result['exec_time']
        
        # 타입 설정
        if result_dict['success']:
            result_dict['type'] = self.get_script_type(result_dict['result'])
        
        # check_only 모드에서 result 변수 확인
        if check_only and result_dict['success'] and result_dict['result'] is None:
            result_dict['success'] = False
            result_dict['error'] = "스크립트에 'result' 변수가 정의되지 않았습니다."
            result_dict['type'] = None
        
        return result_dict

    def set_script_compiled(self, script_name: str, script: str, desc: str = '', kwargs: dict = None, save: bool = True):
        """스크립트 검사, 저장 및 컴파일 (통합 메서드)
        
        Args:
            script_name: 스크립트 이름
            script: 스크립트 코드
            desc: 스크립트 설명
            kwargs: 검사에 사용할 매개변수
            save: True=저장+컴파일, False=검사만
        
        Returns:
            dict: {'success': bool, 'result': None, 'error': str, 'type': str, 'logs': list, 'exec_time': float}
        """
        if kwargs is None:
            kwargs = {}
        
        # 결과 초기화
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
            'exec_time': 0,
        }
        
        # 검사 실행
        check_result = self.run_script(script_name, check_only=True, script_contents=script, kwargs=kwargs)
        
        # 결과 복사
        result_dict['logs'] = check_result['logs'].copy()
        result_dict['exec_time'] = check_result['exec_time']
        result_dict['result'] = check_result['result']  # 이 줄 추가!
        
        if not check_result['success'] or check_result['type'] == 'error':
            result_dict['error'] = check_result['error'] or 'result가 None입니다.'
            return result_dict
        
        # 스크립트 타입 설정
        result_dict['type'] = check_result['type']
        
        # save=False면 검사까지만 하고 반환
        if not save:
            result_dict['success'] = True
            result_dict['logs'].append(f'INFO: 스크립트 검사 완료: {script_name} (타입: {result_dict["type"]})')
            return result_dict
        
        # save=True인 경우 저장 및 컴파일 진행
        
        # 스크립트 데이터 생성 및 저장
        script_data = {
            'script': script,
            'type': result_dict['type'],
            'desc': desc
        }
        
        self.scripts[script_name] = script_data
        
        # 컴파일된 스크립트 캐시에서 제거 (재컴파일 필요)
        if script_name in self._compiled_scripts:
            del self._compiled_scripts[script_name]
        
        # 파일 저장
        save_result = self._save_scripts()
        if not save_result:
            result_dict['error'] = '파일 저장 실패'
            result_dict['logs'].append('ERROR: 파일 저장 실패')
            return result_dict
        
        # 컴파일 수행 (확장 기능이 있는 경우)
        if hasattr(self, 'script_cache'):
            try:
                script_names = set(self.scripts.keys())
                compile_success = self.script_cache.compile_script(script_name, script, script_names)
                
                if compile_success:
                    result_dict['logs'].append(f'INFO: 스크립트 컴파일 완료: {script_name}')
                    
                    # 의존하는 스크립트들 재컴파일
                    affected = self.script_cache.invalidate_script(script_name)
                    for affected_name in affected:
                        if affected_name != script_name and affected_name in self.scripts:
                            affected_script = self.scripts[affected_name]['script']
                            self.script_cache.compile_script(affected_name, affected_script, script_names)
                    
                    if len(affected) > 1:
                        result_dict['logs'].append(f'INFO: 영향받은 스크립트 재컴파일: {len(affected)-1}개')
                        logging.info(f"스크립트 컴파일 완료: {script_name} (영향받은 스크립트: {len(affected)-1}개)")
                    else:
                        logging.info(f"스크립트 컴파일 완료: {script_name}")
                else:
                    result_dict['logs'].append(f'WARNING: 스크립트 컴파일 실패: {script_name}')
                    
            except Exception as e:
                error_msg = f'컴파일 오류: {e}'
                result_dict['logs'].append(f'ERROR: {error_msg}')
                logging.error(error_msg)
        
        self._update_script_version(script_name)

        # 성공
        result_dict['success'] = True
        result_dict['logs'].append(f'INFO: 스크립트 저장 완료: {script_name} (타입: {result_dict["type"]})')
        
        return result_dict

    def run_script_compiled(self, script_name: str, kwargs: dict = None):
        """컴파일된 스크립트 실행 (매매용 고속 실행)
        
        Args:
            script_name: 스크립트 이름
            kwargs: 실행 매개변수
            
        Returns:
            dict: 실행 결과
        """
        if kwargs is None:
            kwargs = {}
        
        start_time = time.time()
        
        # 결과 초기화
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
            'exec_time': 0,
        }
        
        # 기본 검증 (최소한)
        code = kwargs.get('code')
        if code is None:
            result_dict['error'] = "종목코드가 지정되지 않았습니다."
            result_dict['logs'].append('ERROR: 종목코드가 지정되지 않았습니다.')
            return result_dict
        
        # 스크립트 존재 확인
        if script_name not in self.scripts:
            result_dict['error'] = f"스크립트 없음: {script_name}"
            result_dict['logs'].append(f'ERROR: 스크립트 없음: {script_name}')
            return result_dict
        
        # 순환 참조 방지
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_name}"
            result_dict['logs'].append(f'ERROR: 순환 참조 감지: {script_name}')
            return result_dict
        
        # 실행 중인 스크립트에 추가
        self._running_scripts.add(script_key)
        
        try:
            # 차트 데이터 준비 상태 검사
            if not self.cht_dt.is_code_registered(code):
                result_dict['error'] = f"차트 데이터가 준비되지 않음: {code}"
                result_dict['logs'].append(f'ERROR: 차트 데이터가 준비되지 않음: {code}')
                return result_dict

            # 컴파일된 코드 가져오기
            code_obj = self._get_compiled_code_fast(script_name)
            if code_obj is None:
                result_dict['error'] = f"컴파일된 코드 없음: {script_name}"
                result_dict['logs'].append(f'ERROR: 컴파일된 코드 없음: {script_name}')
                return result_dict
            
            # 실행 환경 준비
            globals_dict, script_logs = self._prepare_execution_globals(script_name)
            locals_dict = {}
            
            # kwargs를 locals에 설정하고 단일 exec
            locals_dict['kwargs'] = kwargs
            exec(code_obj, globals_dict, locals_dict)

            # 실행 결과 가져오기
            script_result = locals_dict.get('result')
            exec_time = time.time() - start_time
            
            # 실행 시간 경고 (기준 완화: 0.1초)
            if exec_time > 0.1:
                warning_msg = f"컴파일된 스크립트 실행 시간 초과 ({script_name}:{code}): {exec_time:.4f}초"
                logging.warning(warning_msg)
                script_logs.append(f'WARNING: {warning_msg}')
            
            result_dict['success'] = True
            result_dict['result'] = script_result
            result_dict['type'] = self.get_script_type(script_result)
            result_dict['exec_time'] = exec_time
            result_dict['logs'] = script_logs
            
            return result_dict
            
        except Exception as e:
            tb = traceback.format_exc()
            
            # 에러 로그 추가
            error_msg = f"{type(e).__name__} - {e}"
            result_dict['logs'].append(f"ERROR: {error_msg}")
            result_dict['logs'].append(f"TRACEBACK: {tb}")
            
            # 시스템 로깅
            logging.error(f"{script_name} 컴파일된 스크립트 오류: {error_msg}")
            
            result_dict['error'] = f"실행 오류: {error_msg}"
            return result_dict
            
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if script_key in self._running_scripts:
                self._running_scripts.remove(script_key)
            
            # 실행 시간 기록
            result_dict['exec_time'] = time.time() - start_time

    def _get_compiled_code_fast(self, script_name: str):
        """컴파일된 코드 빠른 획득 (매매용) - 버전 관리 적용
        
        Args:
            script_name: 스크립트 이름
            
        Returns:
            code object: 컴파일된 코드 객체 또는 None
        """
        cache_key = f"{script_name}_compiled"
        
        # 메모리 캐시에 있으면 그냥 사용 (이미 현재 버전)
        if cache_key in self._compiled_scripts:
            return self._compiled_scripts[cache_key]
        
        # 확장 기능(파일 캐시) 확인
        if hasattr(self, 'script_cache'):
            cached_code = self.script_cache.load_compiled_script(script_name)
            if cached_code and self._is_current_version(script_name):
                # 파일 캐시가 현재 버전이면 메모리로 로드
                self._compiled_scripts[cache_key] = cached_code
                return cached_code
        
        # 현재 버전이 아니거나 캐시에 없으면 새로 컴파일
        return self._compile_new_version(script_name)

    def _compile_new_version(self, script_name: str):
        """스크립트를 새 버전으로 컴파일"""
        script_data = self.scripts.get(script_name, {})
        script = script_data.get('script', '')
        if not script:
            return None
        
        try:
            # 컴파일용 래퍼 스크립트 생성
            wrapped_script = self.make_wrapped_script(script, {}, self._indent_script, for_compiled=True)
            code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
            
            # 메모리 캐시 저장
            cache_key = f"{script_name}_compiled"
            self._compiled_scripts[cache_key] = code_obj
            
            # 파일 캐시 저장 (확장 기능이 있는 경우)
            if hasattr(self, 'script_cache'):
                script_names = set(self.scripts.keys())
                self.script_cache.compile_script(script_name, script, script_names)
            
            # 현재 버전으로 기록
            self._update_script_version(script_name)
            
            logging.info(f"스크립트 새 버전 컴파일 완료: {script_name}")
            return code_obj
            
        except Exception as e:
            logging.error(f"새 버전 컴파일 오류 ({script_name}): {e}")
            return None

    def delete_script(self, script_name: str):
        """스크립트 삭제
        
        Args:
            script_name: 삭제할 스크립트 이름
        
        Returns:
            bool: 삭제 성공 여부
        """
        if script_name in self.scripts:
            del self.scripts[script_name]
            # 컴파일된 스크립트 캐시에서도 제거
            cache_key = f"{script_name}_compiled"
            if cache_key in self._compiled_scripts:
                del self._compiled_scripts[cache_key]
            
            # 확장 기능이 있는 경우 컴파일 캐시도 정리
            if hasattr(self, 'script_cache'):
                self.script_cache.invalidate_script(script_name)

            # 버전 파일도 삭제
            try:
                version_file = os.path.join(self.cache_dir, f"{script_name}_version.txt")
                if os.path.exists(version_file):
                    os.remove(version_file)
            except Exception as e:
                logging.error(f"버전 파일 삭제 오류 ({script_name}): {e}")

            return self._save_scripts()
        return False
    
    def _has_forbidden_syntax(self, script: str) -> bool:
        """금지된 구문이 있는지 확인
        
        Args:
            script: 검사할 스크립트 코드
        
        Returns:
            bool: 금지된 구문이 있으면 True
        """
        # 허용된 모듈 패턴
        allowed_patterns = '|'.join(self.ALLOWED_MODULES)
        
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, script):
                return True
        
        # AST 분석을 통한 추가 검사
        try:
            tree = ast.parse(script)
            
            # 방문자 패턴으로 AST 노드 검사
            class ForbiddenSyntaxVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.has_forbidden = False
                    self.forbidden_reason = None
                
                def visit_Import(self, node):
                    for name in node.names:
                        if name.name not in ScriptManager.ALLOWED_MODULES:
                            self.has_forbidden = True
                            self.forbidden_reason = f"허용되지 않는 모듈 임포트: {name.name}"
                    self.generic_visit(node)
                
                def visit_ImportFrom(self, node):
                    if node.module not in ScriptManager.ALLOWED_MODULES:
                        self.has_forbidden = True
                        self.forbidden_reason = f"허용되지 않는 모듈에서 임포트: {node.module}"
                    self.generic_visit(node)
                
                def visit_Call(self, node):
                    # 함수 호출 확인
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                        if func_name in ['eval', 'exec', '__import__']:
                            self.has_forbidden = True
                            self.forbidden_reason = f"금지된 함수 호출: {func_name}"
                        
                    # 속성 접근 호출 확인 (예: os.system)
                    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        module_name = node.func.value.id
                        if module_name in ['os', 'sys', 'subprocess']:
                            self.has_forbidden = True
                            self.forbidden_reason = f"금지된 모듈 사용: {module_name}"
                    
                    self.generic_visit(node)
                
                def visit_While(self, node):
                    self.has_forbidden = True
                    self.forbidden_reason = "while 루프 사용 금지"
                    self.generic_visit(node)
            
            visitor = ForbiddenSyntaxVisitor()
            visitor.visit(tree)
            
            if visitor.has_forbidden:
                logging.warning(f"금지된 구문 감지: {visitor.forbidden_reason}")
                return True
                
        except SyntaxError as e:
            logging.error(f"구문 오류: {e}")
            return True
        
        return False
    
    def _safe_loop(self, iterable, func):
        """안전한 루프 실행 함수
        
        무한 루프 방지를 위한 for 루프 래퍼 함수.
        
        Args:
            iterable: 반복 가능한 객체
            func: 각 항목에 적용할 함수
        
        Returns:
            list: 각 항목에 func를 적용한 결과 리스트
        """
        results = []
        for item in iterable:
            results.append(func(item))
        return results

    def _indent_script(self, script, indent=4):
        """스크립트 들여쓰기 추가
        
        Args:
            script: 원본 스크립트
            indent: 들여쓰기 공백 수
            
        Returns:
            str: 들여쓰기가 추가된 스크립트
        """
        try:
            lines = script.split('\n')
            indented_lines = [' ' * indent + line if line.strip() else line for line in lines]
            return '\n'.join(indented_lines)
        except Exception as e:
            logging.error(f"들여쓰기 처리 오류: {e}")
            # 오류 발생 시 원본 반환 (실행은 실패하더라도 예외는 발생시키지 않음)
            return script

    def _is_valid_identifier(self, name):
        """유효한 식별자인지 확인"""
        return name.isidentifier()
    
    def _get_script_error_location(self, tb_str, script):
        """스크립트 에러 위치 추출하여 한 줄 에러 메시지 반환"""
        try:
            # 에러 라인 번호 찾기
            lines = tb_str.splitlines()
            error_line_num = None
            error_msg = "알 수 없는 오류"
            
            for line in lines:
                if "File \"<string>\"" in line and ", line " in line:
                    match = re.search(r", line (\d+)", line)
                    if match:
                        # 래퍼 함수 오프셋 제거 (try 라인까지 12라인)
                        wrapper_offset = 12
                        error_line_num = int(match.group(1)) - wrapper_offset
                elif any(err_type in line for err_type in ["TypeError:", "NameError:", "SyntaxError:", "ValueError:", "AttributeError:", "IndexError:"]):
                    error_msg = line.strip()
            
            if error_line_num and error_line_num > 0:
                script_lines = script.splitlines()
                if error_line_num <= len(script_lines):
                    error_line = script_lines[error_line_num-1].strip()
                    return f"실행 오류 (행 {error_line_num}): {error_msg} → 수정: {error_line}"
            
            return f"실행 오류: {error_msg}"
            
        except Exception as e:
            logging.error(f"에러 위치 파악 오류: {e}")
            return f"실행 오류: {error_msg}"

    def _prepare_execution_globals(self, current_script_name):
        """실행 환경의 글로벌 변수 준비 (로그 수집 포함)"""
        try:
            # 스크립트용 로그 수집 리스트
            script_logs = []
            
            # Python 내장 함수 제한 (허용된 것만 포함)
            restricted_builtins = {}
            builtins_dict = __builtins__ if isinstance(__builtins__, dict) else dir(__builtins__)
            
            for name in self.ALLOWED_BUILTINS:
                if name in builtins_dict:
                    if isinstance(__builtins__, dict):
                        restricted_builtins[name] = __builtins__[name]
                    else:
                        restricted_builtins[name] = getattr(__builtins__, name)
            
            # 필요한 모듈 로드
            modules = {}
            for module_name in self.ALLOWED_MODULES:
                try:
                    module = __import__(module_name)
                    modules[module_name] = module
                except ImportError:
                    logging.warning(f"모듈 로드 실패: {module_name}")
            
            # 로그 수집 래퍼 함수들
            def capture_debug(msg, *args, **kwargs):
                script_logs.append(f"{current_script_name}.DEBUG: {msg}")
            
            def capture_info(msg, *args, **kwargs):
                script_logs.append(f"{current_script_name}.INFO: {msg}")
            
            def capture_warning(msg, *args, **kwargs):
                script_logs.append(f"{current_script_name}.WARNING: {msg}")
            
            def capture_error(msg, *args, **kwargs):
                script_logs.append(f"{current_script_name}.ERROR: {msg}")
            
            def capture_critical(msg, *args, **kwargs):
                script_logs.append(f"{current_script_name}.CRITICAL: {msg}")

            def is_args(key, default_value):
                """스크립트 내에서 인자 확인 함수"""
                # 글로벌에서 직접 kwargs 참조 (성능 최적화)
                if '_current_kwargs' in globals_dict:
                    current_kwargs = globals_dict['_current_kwargs']
                    return current_kwargs.get(key, default_value)
                return default_value
                        
            # 글로벌 환경 설정
            globals_dict = {
                # Python 내장 함수들 (제한된 목록)
                **restricted_builtins,
                
                # 허용된 모듈들
                **modules,
                
                # 로그 수집 함수들
                'debug': capture_debug,
                'info': capture_info,
                'warning': capture_warning,
                'error': capture_error,
                'critical': capture_critical,
                
                # 차트 매니저 및 단축 변수들
                'ChartManager': ChartManager,
                'CM': ChartManager,
                
                # 유틸리티 함수
                'loop': self._safe_loop,
                'run_script': self._script_caller,
                'is_args': is_args,
                
                '_script_logs': script_logs,
                '_current_kwargs': {},
            }
            
            # 모든 스크립트를 함수로 등록 (*args, **kwargs 지원)
            for script_name, script_data in self.scripts.items():
                # 스크립트가 함수처럼 호출 가능하도록 래퍼 생성
                wrapper_code = f"""
def {script_name}(*args, **kwargs):
    # 스크립트 호출 함수 - 결과값만 반환
    return run_script('{script_name}', args, kwargs)
"""
                
                # 스크립트 래퍼 함수 컴파일 및 추가
                try:
                    exec(wrapper_code, globals_dict, globals_dict)
                except Exception as e:
                    logging.error(f"스크립트 래퍼 생성 오류 ({script_name}): {e}")
            
            # run_script 함수 추가 (스크립트 내에서 다른 스크립트 호출용)
            globals_dict['run_script'] = self._script_caller
            
            return globals_dict, script_logs
            
        except Exception as e:
            logging.error(f"실행 환경 준비 오류: {e}")
            # 기본 환경 반환
            return {'ChartManager': ChartManager}, []
                        
    def _script_caller(self, script_name, args=None, kwargs=None):
        """스크립트 내에서 다른 스크립트를 호출하기 위한 함수 (직접 인자 전달 방식)"""
        # 컨텍스트의 기존 kwargs 가져오기 (프레임 검사)
        try:
            import inspect
            frame = inspect.currentframe().f_back
            context_kwargs = {}
            current_script_logs = None
            original_kwargs_keys = set()
            
            while frame:
                if frame.f_code.co_name == 'execute_script':
                    context_kwargs = frame.f_locals.get('kwargs', {})
                    original_kwargs_keys = set(context_kwargs.keys())
                    # 현재 스크립트의 로그 리스트 찾기
                    for var_name, var_value in frame.f_globals.items():
                        if isinstance(var_value, list) and hasattr(var_value, 'append'):
                            if len(var_value) == 0 or (len(var_value) > 0 and isinstance(var_value[0], str)):
                                current_script_logs = var_value
                                break
                    break
                frame = frame.f_back
            
            # 현재 스크립트의 로컬 변수에서 원래 kwargs에 있던 변수들 확인
            if frame and original_kwargs_keys:
                current_locals = frame.f_locals
                for var_name in original_kwargs_keys:
                    if var_name in current_locals:
                        # 스크립트에서 변경된 값이 있으면 업데이트
                        context_kwargs[var_name] = current_locals[var_name]
                        
        except:
            context_kwargs = {}
            current_script_logs = None
        
        # 기본 kwargs에서 시작
        new_kwargs = context_kwargs.copy()
        
        # args와 kwargs 처리
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        
        # kwargs만 병합 (위치 인자는 스크립트에서 직접 처리하도록)
        new_kwargs.update(kwargs)
        
        # 순환 참조 검사
        code = new_kwargs.get('code')
        if code is None:
            logging.error(f"{script_name} 에서 code 가 지정되지 않았습니다.")
            return None
        
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            logging.error(f"순환 참조 감지: {script_name}")
            return None
        
        # 스크립트 실행 - 결과 받기
        result = self.run_script(script_name, kwargs=new_kwargs)
        
        # 로그 통합 (호출된 스크립트의 로그를 현재 스크립트 로그에 추가)
        if current_script_logs is not None and result.get('logs'):
            current_script_logs.extend(result['logs'])
        
        # 결과값만 반환 (스크립트에서 사용하기 편하게)
        return result['result'] if result['success'] else None

    @staticmethod
    def make_wrapped_script(script, combined_kwargs, indent_func, for_compiled=False):
        """중복되는 wrapped_script 생성 코드 헬퍼 (staticmethod)"""
        if for_compiled:
            # 컴파일용: locals()에서 kwargs 직접 참조하여 안전한 실행
            return f"""
try:
    # locals()에서 kwargs 직접 가져오기
    _kwargs = locals().get('kwargs', {{}})
    code = _kwargs.get('code')
    name = _kwargs.get('name', '')
    qty = _kwargs.get('qty', 0)
    price = _kwargs.get('price', 0)
    
    # 사용자 정의 변수들 추출
    for key, value in _kwargs.items():
        if key not in ['code', 'name', 'qty', 'price']:
            globals()[key] = value
    
    # 사용자 스크립트 실행
{indent_func(script, indent=4)}
except ZeroDivisionError:
    debug('ZeroDivisionError 발생 - 기본값으로 처리')
    result = False
except Exception as e:
    debug(f'스크립트 실행 오류: {{e}}')
    result = None
"""
        else:
            # 일반용: kwargs를 직접 하드코딩
            return f"""
def execute_script(kwargs):
    # 사용자 예약 변수들을 로컬 변수로 풀어서 직접 접근 가능하게 함
    code = kwargs.get('code')
    name = kwargs.get('name', '')
    qty = kwargs.get('qty', 0)
    price = kwargs.get('price', 0)
    
    # 사용자 정의 변수들도 로컬 변수로 추출
    for key, value in kwargs.items():
        if key not in ['code', 'name', 'qty', 'price']:
            globals()[key] = value
    
    # 사용자 스크립트 실행
    try:
{indent_func(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise  # 오류를 전파하여 감지할 수 있도록 함

# 스크립트 실행
result = execute_script({repr(combined_kwargs)})
"""
                                
class CompiledScriptCache:
        """컴파일된 스크립트 관리 클래스"""
        
        def __init__(self, cache_dir: str = dc.fp.cache_path):
            """초기화
            
            Args:
                cache_dir: 컴파일된 스크립트 캐시 디렉토리
            """
            self.cache_dir = cache_dir
            self.compiled_cache = {}  # 메모리 내 캐시 {script_name: code_obj}
            self.dependency_map = {}  # 의존성 맵 {script_name: set(dependencies)}
            self.hash_map = {}        # 스크립트 해시 맵 {script_name: hash_value}
            self.modules_cache = {}   # 로드된 모듈 캐시 {script_name: module}
            
            # 캐시 디렉토리 생성 (필요시 사용)
            # os.makedirs(cache_dir, exist_ok=True)
        
        def get_script_hash(self, script: str) -> str:
            """스크립트의 해시값 계산
            
            Args:
                script: 스크립트 코드
                
            Returns:
                str: 해시값
            """
            return hashlib.md5(script.encode('utf-8')).hexdigest()
        
        def get_cache_path(self, script_name: str) -> str:
            """캐시 파일 경로 생성
            
            Args:
                script_name: 스크립트 이름
                
            Returns:
                str: 캐시 파일 경로
            """
            return os.path.join(self.cache_dir, f"{script_name}.pyc")
        
        def get_dependency_path(self, script_name: str) -> str:
            """의존성 파일 경로 생성
            
            Args:
                script_name: 스크립트 이름
                
            Returns:
                str: 의존성 파일 경로
            """
            return os.path.join(self.cache_dir, f"{script_name}.dep")
        
        def analyze_dependencies(self, script: str, script_names: Set[str]) -> Set[str]:
            """스크립트의 의존성 분석
            
            Args:
                script: 스크립트 코드
                script_names: 시스템에 등록된 모든 스크립트 이름 집합
                
            Returns:
                Set[str]: 의존하는 스크립트 이름 집합
            """
            dependencies = set()
            
            try:
                tree = ast.parse(script)
                
                # 함수 호출 검사하는 방문자 패턴
                class DependencyVisitor(ast.NodeVisitor):
                    def visit_Call(self, node):
                        # 함수 호출 확인
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                            # 호출된 함수가 등록된 스크립트 이름이면 의존성 추가
                            if func_name in script_names:
                                dependencies.add(func_name)
                        
                        self.generic_visit(node)
                
                visitor = DependencyVisitor()
                visitor.visit(tree)
                
            except SyntaxError:
                # 구문 오류가 있는 경우 빈 의존성 집합 반환
                logging.warning(f"의존성 분석 중 구문 오류 발생")
            
            return dependencies
        
        def _indent_script(self, script, indent=4):
            """스크립트 들여쓰기 추가"""
            try:
                lines = script.split('\n')
                indented_lines = [' ' * indent + line if line.strip() else line for line in lines]
                return '\n'.join(indented_lines)
            except Exception as e:
                logging.error(f"들여쓰기 처리 오류: {e}")
                return script
                
        def compile_script(self, script_name: str, script: str, script_names: Set[str]) -> bool:
            """스크립트 컴파일 및 캐싱
            
            Args:
                script_name: 스크립트 이름
                script: 스크립트 코드
                script_names: 시스템에 등록된 모든 스크립트 이름 집합
                
            Returns:
                bool: 컴파일 성공 여부
            """
            try:
                # 해시값 계산
                script_hash = self.get_script_hash(script)
                self.hash_map[script_name] = script_hash
                
                # 의존성 분석
                dependencies = self.analyze_dependencies(script, script_names)
                self.dependency_map[script_name] = dependencies
                
                # 스크립트 컴파일 (새로운 형식으로 래핑)
                wrapped_script = ScriptManager.make_wrapped_script(script, {}, self._indent_script)
                code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                
                # 메모리 캐시에 저장
                self.compiled_cache[script_name] = code_obj
                
                # 파일에 저장 (필요한 경우)
                cache_path = self.get_cache_path(script_name)
                with open(cache_path, 'wb') as f:
                    f.write(importlib.util.MAGIC_NUMBER)  # Python 매직 넘버
                    f.write(b'\x00\x00\x00\x00')         # 타임스탬프 (0)
                    f.write(b'\x00\x00\x00\x00')         # 소스 크기 (0)
                    marshal.dump(code_obj, f)            # 코드 객체 저장
                
                # 의존성 정보 저장
                dep_path = self.get_dependency_path(script_name)
                with open(dep_path, 'wb') as f:
                    pickle.dump({
                        'hash': script_hash,
                        'dependencies': dependencies
                    }, f)
                
                return True
                
            except Exception as e:
                logging.error(f"스크립트 컴파일 오류: {e}", exc_info=True)
                return False
                    
        def load_compiled_script(self, script_name: str) -> Optional[Any]:
            """컴파일된 스크립트 로드
            
            Args:
                script_name: 스크립트 이름
                
            Returns:
                Any: 컴파일된 코드 객체 또는 None (실패 시)
            """
            # 이미 메모리에 있으면 바로 반환
            if script_name in self.compiled_cache:
                return self.compiled_cache[script_name]
            
            # 파일에서 로드
            cache_path = self.get_cache_path(script_name)
            if not os.path.exists(cache_path):
                return None
            
            try:
                with open(cache_path, 'rb') as f:
                    # 매직 넘버, 타임스탬프, 소스 크기 스킵
                    f.read(12)
                    code_obj = marshal.load(f)
                    
                    # 메모리 캐시에 저장
                    self.compiled_cache[script_name] = code_obj
                    return code_obj
                    
            except Exception as e:
                logging.error(f"컴파일된 스크립트 로드 오류: {e}")
                return None

        def get_affected_scripts(self, script_name: str) -> Set[str]:
            """특정 스크립트에 의존하는 모든 스크립트 찾기
            
            Args:
                script_name: 스크립트 이름
                
            Returns:
                Set[str]: 의존하는 스크립트 집합
            """
            affected = set()
            
            for name, deps in self.dependency_map.items():
                if script_name in deps:
                    affected.add(name)
                    # 재귀적으로 의존성 체크 (간접 의존성)
                    affected.update(self.get_affected_scripts(name))
            
            return affected

        def invalidate_script(self, script_name: str) -> Set[str]:
            """스크립트 및 의존하는 모든 스크립트의 캐시 무효화
            
            Args:
                script_name: 스크립트 이름
                
            Returns:
                Set[str]: 무효화된 스크립트 집합
            """
            # 이 스크립트에 의존하는 모든 스크립트 찾기
            affected_scripts = self.get_affected_scripts(script_name)
            affected_scripts.add(script_name)  # 자기 자신도 포함
            
            # 메모리 캐시에서 제거
            for name in affected_scripts:
                if name in self.compiled_cache:
                    del self.compiled_cache[name]
                if name in self.modules_cache:
                    del self.modules_cache[name]
            
            return affected_scripts

        def clear_cache(self):
            """모든 캐시 초기화"""
            self.compiled_cache.clear()
            self.dependency_map.clear()
            self.hash_map.clear()
            self.modules_cache.clear()
            
# 예제 실행
if __name__ == '__main__':
    mi3 = ChartManager('005930', 'mi', 3)

    print(f'{mi3.c()}')
    ma5 = mi3.indicator(mi3.ma, mi3.c, 5)
    ma20 = mi3.indicator(mi3.ma, mi3.c, 20)

    c1 = ma5() > ma20() and mi3.c > ma5()
    c2 = ma5(1) < ma5() and ma20(1) < ma20()

    result = ma5(1)

    print(result)
