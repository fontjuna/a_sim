from public import dc, profile_operation, hoga
from datetime import datetime, timedelta
from typing import Dict, Any
from collections import deque
import os
import time
import json
import ast
import re
import logging
import threading
import traceback
import numpy as np
from numba import jit, njit, prange

class ChartData:
    """
    고성능 차트 데이터 관리 클래스 (메모리 기반, 0.01초 주기 최적화)
    """
    _instance = None
    _creation_lock = threading.Lock()

    # 데이터 크기 제한 (메모리 관리)
    MAX_CANDLES = {
        'mi1': 2700,   # 1분봉: 약 7일치
        'mi3': 900,    # 3분봉: 약 7일치  
        'mi5': 540,    # 5분봉: 약 7일치
        'mi10': 270,   # 10분봉: 약 7일치
        'mi15': 180,    # 15분봉: 약 7일치
        'mi30': 90,    # 30분봉: 약 7일치
        'mi60': 45,    # 60분봉: 약 7일치
        'dy': 600,     # 일봉: 약 2.5년치
        'wk': 140,      # 주봉: 약 2.5년치 
        'mo': 30       # 월봉: 약 2.5년치
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
        """데이터 구조 사전 할당 (전체 주기)"""
        if code not in self._chart_data:
            self._chart_data[code] = {}
            self._data_versions[code] = 0
            self._last_update_time[code] = 0
            
            # 모든 주기들을 미리 생성
            for cycle_key in self.MAX_CANDLES.keys():
                max_size = self.MAX_CANDLES.get(cycle_key, 1000)
                self._chart_data[code][cycle_key] = deque(maxlen=max_size)
    
    def _increment_version(self, code: str):
        """데이터 버전 증가 (캐시 무효화)"""
        self._data_versions[code] = self._data_versions.get(code, 0) + 1
        self._last_update_time[code] = time.time()
    
    def _set_minute_chart(self, code: str, data: list):
        """1분봉 데이터 설정 (여러 날짜 처리, 마지막 봉에만 전봉누적값 추가)"""
        minute_deque = self._chart_data[code]['mi1']
        minute_deque.clear()
        
        # 최신 MAX_CANDLES개만 유지 (data[0]이 최신)
        recent_data = data[:self.MAX_CANDLES['mi1']]
        
        if not recent_data: return
        
        # 마지막 봉(인덱스 0)의 날짜
        last_candle_date = time.strftime('%Y%m%d', time.localtime()) #recent_data[0]['체결시간'][:8]
        
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
    
    def _set_all_minute_chart(self, code: str):
        """모든 분봉들을 한번에 초고속 생성"""
        minute_data = list(self._chart_data[code]['mi1'])
        if not minute_data:
            return
        
        # 분봉별 그룹 데이터 (한번 순회로 모든 분봉 생성)
        ticks = [3, 5, 10, 15, 30, 60]
        grouped_data = {tick: {} for tick in ticks}
        
        # 역순으로 처리 (과거 → 최신 순서) - 단일 순회
        for candle in reversed(minute_data):
            dt_str = candle['체결시간']
            if len(dt_str) < 12: continue
            
            hour = int(dt_str[8:10])
            minute = int(dt_str[10:12])
            total_minutes = hour * 60 + minute
            
            # 모든 tick에 대해 동시 처리
            for tick in ticks:
                tick_start = (total_minutes // tick) * tick
                group_hour = tick_start // 60
                group_minute = tick_start % 60
                group_key = f"{dt_str[:8]}{group_hour:02d}{group_minute:02d}00"
                
                if group_key not in grouped_data[tick]:
                    grouped_data[tick][group_key] = {
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
                    group = grouped_data[tick][group_key]
                    group['현재가'] = candle['현재가']
                    group['고가'] = max(group['고가'], candle['고가'])
                    group['저가'] = min(group['저가'], candle['저가'])
                    group['거래량'] += candle['거래량']
                    group['거래대금'] += candle.get('거래대금', 0)
        
        # 결과를 각 deque에 저장 (고속)
        for tick in ticks:
            cycle_key = f'mi{tick}'
            if cycle_key in self._chart_data[code]:
                result = list(grouped_data[tick].values())
                result.sort(key=lambda x: x['체결시간'], reverse=True)
                
                target_deque = self._chart_data[code][cycle_key]
                target_deque.clear()
                target_deque.extend(result)

    def _set_day_chart(self, code: str, data: list):
        """일봉 데이터 설정"""
        day_deque = self._chart_data[code]['dy']
        day_deque.clear()
        
        # 최신 MAX_CANDLES개만 유지 (data[0]이 최신)
        recent_data = data[:self.MAX_CANDLES['dy']]
        for candle in recent_data:
            day_deque.append(candle)

    def _set_week_month_chart(self, code: str):
        """일봉에서 주봉/월봉 생성"""
        day_data = list(self._chart_data[code]['dy'])
        if not day_data: return
        
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
    
    def is_code_registered(self, code: str) -> bool:
        """종목 등록 여부 확인 (메모리 기반으로 단순화)"""
        return code in self._chart_data and bool(self._chart_data[code].get('mi1') and bool(self._chart_data[code].get('dy')))
    
    #@profile_operation
    def set_chart_data(self, code: str, data: list, cycle: str, tick: int = None):
        """차트 데이터 설정 (초고속 버전)"""
        
        if not data:
            return
        
        # 1분봉과 일봉만 허용
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
                self._set_minute_chart(code, data)
                # 모든 분봉들 한번에 생성
                self._set_all_minute_chart(code)
                
            elif cycle == 'dy':
                # 일봉 설정
                self._set_day_chart(code, data)
                # 주봉, 월봉 자동 생성
                self._set_week_month_chart(code)
            
            # 버전 업데이트
            self._increment_version(code)
        
    def get_chart_data(self, code: str, cycle: str, tick: int = None) -> list:
        """차트 데이터 반환 (항상 최신 데이터 보장)"""
        code_lock = self._get_code_lock(code)
        with code_lock:
            # 데이터 구조 확인
            if code not in self._chart_data: return []
            
            cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
            
            if cycle_key in self._chart_data[code]:
                result = list(self._chart_data[code][cycle_key])
            else:
                result = []
        
        return result

    def update_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """실시간 차트 업데이트 (누적값 처리 통합)"""
        
        code_lock = self._get_code_lock(code)
        with code_lock:
            # 데이터 구조 확인
            if code not in self._chart_data: return
            
            # 1분봉 업데이트 (누적값 → 실제 거래량 변환)
            is_new_minute = self._update_minute_chart(code, price, volume, amount, datetime_str)
            
            if is_new_minute:
                # 새 분봉 생성 (누적값 처리 로직 적용)
                self._create_minute_candles(code)
            else:
                # 기존 분봉 업데이트 (누적값 처리 로직 적용)
                self._update_minute_candles(code, price, volume, amount, datetime_str)
            
            # 일봉 업데이트 (있는 경우에만)
            if self._chart_data[code]['dy']:
                self._update_day_chart(code, price, volume, amount, datetime_str)
                self._update_week_month_chart(code, price, volume, amount, datetime_str)
            
            # 버전 업데이트
            self._increment_version(code)

    def _create_minute_candles(self, code: str):
        """새 분봉들 생성 (누적값 처리 로직 적용)"""
        minute_data = self._chart_data[code]['mi1']
        if not minute_data:
            return
        
        latest_minute = minute_data[0]
        base_time = latest_minute['체결시간']
        current_date = base_time[:8]
        
        # 모든 분봉에 새 봉 추가
        for tick in [3, 5, 10, 15, 30, 60]:
            cycle_key = f'mi{tick}'
            if cycle_key not in self._chart_data[code]:
                continue
            
            # 새 분봉 시간 계산
            new_time = self._calculate_tick_time(base_time, tick)
            target_deque = self._chart_data[code][cycle_key]
            
            # 기존 봉과 같은 시간이면 업데이트, 다르면 새 봉 추가
            if target_deque and target_deque[0]['체결시간'] == new_time:
                # 기존 봉에 합치기 - 1분봉의 실제 거래량만 더하기
                existing = target_deque[0]
                existing['고가'] = max(existing['고가'], latest_minute['현재가'])
                existing['저가'] = min(existing['저가'], latest_minute['현재가'])
                existing['현재가'] = latest_minute['현재가']
                existing['거래량'] += latest_minute['거래량']  # 1분봉의 실제 거래량
                existing['거래대금'] += latest_minute.get('거래대금', 0)
            else:
                # 기존 로직: 최신 분봉의 누적값 + 거래량
                if target_deque:
                    prev_candle = target_deque[0]
                    new_prev_cumulative_volume = prev_candle.get('전봉누적거래량', 0) + prev_candle.get('거래량', 0)
                    new_prev_cumulative_amount = prev_candle.get('전봉누적거래대금', 0) + prev_candle.get('거래대금', 0)
                else:
                    new_prev_cumulative_volume = 0
                    new_prev_cumulative_amount = 0
                
                # 새 분봉 생성
                new_candle = {
                    '종목코드': latest_minute['종목코드'],
                    '체결시간': new_time,
                    '시가': latest_minute['현재가'],
                    '고가': latest_minute['현재가'],
                    '저가': latest_minute['현재가'],
                    '현재가': latest_minute['현재가'],
                    '거래량': latest_minute['거래량'],  # 1분봉의 실제 거래량
                    '거래대금': latest_minute.get('거래대금', 0),
                    '전봉누적거래량': new_prev_cumulative_volume,
                    '전봉누적거래대금': new_prev_cumulative_amount
                }
                
                target_deque.appendleft(new_candle)

    def _update_minute_candles(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """기존 분봉들 업데이트 (누적값 처리 로직 적용)"""
        minute_data = self._chart_data[code]['mi1']
        if not minute_data:
            return
        
        latest_minute = minute_data[0]
        base_time = latest_minute['체결시간']
        
        # 1분봉의 거래량 증분 계산 (누적값에서 실제 거래량으로 변환된 값)
        actual_minute_volume = latest_minute['거래량']
        actual_minute_amount = latest_minute.get('거래대금', 0)
        
        # 이전 값과 비교하여 증분 계산
        prev_volume = latest_minute.get('_prev_volume', actual_minute_volume)
        prev_amount = latest_minute.get('_prev_amount', actual_minute_amount)
        
        volume_diff = actual_minute_volume - prev_volume
        amount_diff = actual_minute_amount - prev_amount
        
        # 현재 값을 이전 값으로 저장
        latest_minute['_prev_volume'] = actual_minute_volume
        latest_minute['_prev_amount'] = actual_minute_amount
        
        # 모든 분봉의 최신 봉 업데이트
        for tick in [3, 5, 10, 15, 30, 60]:
            cycle_key = f'mi{tick}'
            if cycle_key not in self._chart_data[code]:
                continue
            
            target_deque = self._chart_data[code][cycle_key]
            if not target_deque:
                continue
            
            # 현재 분봉 시간 확인
            tick_time = self._calculate_tick_time(base_time, tick)
            
            # 같은 시간 구간이면 업데이트
            if target_deque[0]['체결시간'] == tick_time:
                candle = target_deque[0]
                candle['현재가'] = price
                candle['고가'] = max(candle['고가'], price)
                candle['저가'] = min(candle['저가'], price)
                
                # 증분만 더하기 (첫 실행시에는 증분이 0이 됨)
                if volume_diff > 0:
                    candle['거래량'] += volume_diff
                if amount_diff > 0:
                    candle['거래대금'] += amount_diff

    def _update_minute_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str) -> bool:
        """1분봉 업데이트 (새 봉 여부 반환)"""
        base_time = datetime_str[:12] + '00'
        minute_deque = self._chart_data[code]['mi1']
        
        # 데이터가 없는 경우
        if not minute_deque:
            new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
            new_candle['전봉누적거래량'] = 0
            new_candle['전봉누적거래대금'] = 0
            minute_deque.appendleft(new_candle)
            return True
        
        # 최신 봉 확인
        latest_candle = minute_deque[0]
        latest_time = latest_candle['체결시간']
        
        if latest_time == base_time:
            # 같은 봉 업데이트
            actual_volume = volume - latest_candle['전봉누적거래량']
            actual_amount = amount - latest_candle['전봉누적거래대금']
            self._update_candle(latest_candle, price, None, actual_volume, actual_amount)
            return False
        else:
            # 새봉 생성
            new_candle = latest_candle.copy()

            new_prev_cumulative_volume = latest_candle['전봉누적거래량'] + latest_candle['거래량']
            new_prev_cumulative_amount = latest_candle['전봉누적거래대금'] + latest_candle['거래대금']
                
            actual_volume = volume - new_prev_cumulative_volume
            actual_amount = amount - new_prev_cumulative_amount
            
            new_candle.update({
                '체결시간': base_time,
                '시가': price,
                '고가': price,
                '저가': price,
                '현재가': price,
                '거래량': actual_volume,
                '거래대금': actual_amount,
                '전봉누적거래량': new_prev_cumulative_volume,
                '전봉누적거래대금': new_prev_cumulative_amount
            })
            
            minute_deque.appendleft(new_candle)
            return True

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

    def _aggregate_day_data(self, day_data: list, period_type: str) -> list:
        """일봉 데이터를 주봉/월봉으로 집계"""
        if not day_data:
            return []
        
        grouped_data = {}
        
        # 역순으로 처리 (과거 → 최신 순서)
        for candle in reversed(day_data):
            date_str = candle.get('일자', '')
            if len(date_str) < 8:
                continue
            
            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                date_obj = datetime(year, month, day)
            except ValueError:
                continue
            
            # 그룹 키 계산
            if period_type == 'week':
                # 월요일 기준으로 주 시작
                days_since_monday = date_obj.weekday()
                monday = date_obj - timedelta(days=days_since_monday)
                group_key = monday.strftime('%Y%m%d')
            else:  # month
                # 월 첫째 날 기준
                group_key = date_obj.strftime('%Y%m01')
            
            if group_key not in grouped_data:
                grouped_data[group_key] = {
                    '종목코드': candle['종목코드'],
                    '일자': group_key,
                    '시가': candle['시가'],
                    '고가': candle['고가'],
                    '저가': candle['저가'],
                    '현재가': candle['현재가'],
                    '거래량': candle['거래량'],
                    '거래대금': candle.get('거래대금', 0)
                }
            else:
                group = grouped_data[group_key]
                group['현재가'] = candle['현재가']  # 최신 종가로 업데이트
                group['고가'] = max(group['고가'], candle['고가'])
                group['저가'] = min(group['저가'], candle['저가'])
                group['거래량'] += candle['거래량']
                group['거래대금'] += candle.get('거래대금', 0)
        
        # 결과를 시간순으로 정렬 (최신이 앞)
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['일자'], reverse=True)
        
        return result

    def _calculate_tick_time(self, datetime_str: str, tick: int) -> str:
        """틱 시간 계산"""
        if len(datetime_str) < 12:
            return datetime_str
        
        hour = int(datetime_str[8:10])
        minute = int(datetime_str[10:12])
        total_minutes = hour * 60 + minute
        
        tick_start = (total_minutes // tick) * tick
        return f"{datetime_str[:8]}{tick_start//60:02d}{tick_start%60:02d}00"

class ChartManager:
    """고성능 차트 매니저 - 속도 최적화 버전"""
    
    def __init__(self, code, cycle='mi', tick=3):
        self.cht_dt = ChartData()
        self.cycle = cycle
        self.tick = tick
        self.code = code
        
        # 성능 최적화를 위한 캐시
        self._raw_data = None  # 원본 데이터 직접 참조
        self._cache_version = -1
        self._data_length = 0
        
    def _ensure_data_cache(self):
        """데이터 캐시 확인 및 업데이트 (최적화)"""
        current_version = self.cht_dt._data_versions.get(self.code, 0)
        
        # 버전이 같으면 즉시 리턴
        if self._cache_version == current_version and self._raw_data is not None:
            return
        
        # 버전이 다를 때만 데이터 갱신
        if self.cycle == 'mi':
            cycle_key = f'mi{self.tick}'
            # 모든 분봉은 ChartData에서 실시간 업데이트됨 - 직접 가져오기
            self._raw_data = self.cht_dt._chart_data.get(self.code, {}).get(cycle_key, [])
        else:
            # 일/주/월봉: ChartData에서 실시간 업데이트됨 - 직접 가져오기
            self._raw_data = self.cht_dt._chart_data.get(self.code, {}).get(self.cycle, [])
        
        self._cache_version = current_version
        self._data_length = len(self._raw_data) if self._raw_data else 0

    # 고속 기본값 반환 함수들 (직접 접근)
    def c(self, n: int = 0) -> float:
        """종가 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        
        return self._raw_data[n].get('현재가', 0)
    
    def o(self, n: int = 0) -> float:
        """시가 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        
        return self._raw_data[n].get('시가', 0)
    
    def h(self, n: int = 0) -> float:
        """고가 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        
        return self._raw_data[n].get('고가', 0)
    
    def l(self, n: int = 0) -> float:
        """저가 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        
        return self._raw_data[n].get('저가', 0)
    
    def v(self, n: int = 0) -> int:
        """거래량 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0
        
        return int(self._raw_data[n].get('거래량', 0))
    
    def a(self, n: int = 0) -> float:
        """거래금액 반환 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        
        return self._raw_data[n].get('거래대금', 0)

    def bar_time(self, n: int = 0) -> str:
        """시간 반환 - 고속 버전"""
        if self.cycle != 'mi': return ''
        
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return ''
        
        time_str = self._raw_data[n].get('체결시간', '')
        return time_str[8:] if time_str else ''
    
    def bar_date(self, n: int = 0) -> str:
        """오늘 날짜 반환"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return ''
        if self.cycle == 'mi':
            time_str = self._raw_data[n].get('체결시간', '')
            if time_str:
                return time_str[:8]
            return ''
        else:
            return self._raw_data[n].get('일자', '')

    # 고속 계산 함수들
    def ma(self, period: int = 20, before: int = 0) -> float:
        """이동평균 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or before + period > self._data_length:
            return 0.0
        
        total = 0.0
        
        for i in range(before, before + period):
            total += self._raw_data[i].get('현재가', 0)
        
        return total / period
    
    def avg(self, value_func, n: int, m: int = 0) -> float:
        """단순이동평균 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        total = 0.0
        for i in range(m, m + n):
            total += value_func(i)
        
        return total / n if n > 0 else 0.0
    
    def highest(self, value_func, n: int, m: int = 0) -> float:
        """최고값 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        max_val = float('-inf')
        for i in range(m, m + n):
            val = value_func(i)
            if val > max_val:
                max_val = val
        
        return max_val if max_val != float('-inf') else 0.0
    
    def lowest(self, value_func, n: int, m: int = 0) -> float:
        """최저값 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        min_val = float('inf')
        for i in range(m, m + n):
            val = value_func(i)
            if val < min_val:
                min_val = val
        
        return min_val if min_val != float('inf') else 0.0
    
    def sum(self, value_func, n: int, m: int = 0) -> float:
        """합계 - 고속 버전"""
        if not callable(value_func):
            return float(value_func) * n
        
        total = 0.0
        for i in range(m, m + n):
            total += value_func(i)
        
        return total
    
    # 계산 함수들 (호환성 유지)
    def eavg(self, value_func, n: int, m: int = 0) -> float:
        """지수이동평균"""
        if not callable(value_func):
            return float(value_func)
        
        if n <= 0:
            return 0.0
        
        alpha = 2.0 / (n + 1)
        result = value_func(m + n - 1)
        
        for i in range(m + n - 2, m - 1, -1):
            result = alpha * value_func(i) + (1 - alpha) * result
        
        return result
    
    def wavg(self, value_func, n: int, m: int = 0) -> float:
        """가중이동평균 계산"""
        if not callable(value_func):
            return float(value_func)
        
        total_value = 0.0
        total_weight = 0.0
        
        for i in range(m, m + n):
            weight = n - (i - m)  # 최신 데이터일수록 가중치 높음
            value = value_func(i)
            total_value += value * weight
            total_weight += weight
        
        return total_value / total_weight if total_weight > 0 else 0.0
    
    def stdev(self, value_func, n: int, m: int = 0) -> float:
        """표준편차"""
        if not callable(value_func) or n <= 1:
            return 0.0
        
        # 평균 계산
        total = 0.0
        for i in range(m, m + n):
            total += value_func(i)
        mean = total / n
        
        # 분산 계산
        variance = 0.0
        for i in range(m, m + n):
            diff = value_func(i) - mean
            variance += diff * diff
        variance /= n
        
        return variance ** 0.5
    
    # 신호 함수들
    def cross_up(self, a_func, b_func) -> bool:
        """상향돌파"""
        if not (callable(a_func) and callable(b_func)): return False
        
        a_prev, a_curr = a_func(1), a_func(0)
        b_prev, b_curr = b_func(1), b_func(0)
        return a_prev <= b_prev and a_curr > b_curr
    
    def cross_down(self, a_func, b_func) -> bool:
        """하향돌파"""
        if not (callable(a_func) and callable(b_func)): return False
        
        a_prev, a_curr = a_func(1), a_func(0)
        b_prev, b_curr = b_func(1), b_func(0)
        return a_prev >= b_prev and a_curr < b_curr

    def bars_since(self, condition_func) -> int:
        """조건이 만족된 이후 지나간 봉 개수"""
        self._ensure_data_cache()
        if not self._raw_data: return 0
        
        for i in range(self._data_length):
            if condition_func(i):
                return i
        return self._data_length

    def highest_since(self, nth: int, condition_func, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최고값"""
        self._ensure_data_cache()
        if not self._raw_data:
            return 0.0
        
        condition_met = 0
        highest_val = float('-inf')
        
        for i in range(self._data_length):
            if condition_func(i):
                condition_met += 1
                if condition_met == nth:
                    # 이 지점부터 현재까지의 최고값 계산
                    for j in range(i, -1, -1):
                        val = data_func(j)
                        highest_val = max(highest_val, val)
                    break
        
        return highest_val if highest_val != float('-inf') else 0.0

    def lowest_since(self, nth: int, condition_func, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최저값"""
        self._ensure_data_cache()
        if not self._raw_data:
            return 0.0
        
        condition_met = 0
        lowest_val = float('inf')
        
        for i in range(self._data_length):
            if condition_func(i):
                condition_met += 1
                if condition_met == nth:
                    # 이 지점부터 현재까지의 최저값 계산
                    for j in range(i, -1, -1):
                        val = data_func(j)
                        lowest_val = min(lowest_val, val)
                    break
        
        return lowest_val if lowest_val != float('inf') else 0.0

    def value_when(self, nth: int, condition_func, data_func) -> float:
        """조건이 nth번째 만족된 시점의 data_func 값"""
        self._ensure_data_cache()
        if not self._raw_data: return 0.0
        
        condition_met = 0
        
        for i in range(self._data_length):
            if condition_func(i):
                condition_met += 1
                if condition_met == nth:
                    return data_func(i)
        
        return 0.0
    
    # ChartManager에 추가할 메소드
    def indicator(self, func, *args):
        """지표 계산 결과를 함수처럼 사용 가능한 객체 반환"""
        # 내부 함수 생성 (클로저)
        def callable_indicator(offset=0):
            return func(*args, offset)
        
        # 함수 반환
        return callable_indicator
    
    # 보조지표 계산 함수들
    def get_obv_array(self, count: int = 10) -> list:
        """OBV 배열을 표준 방식으로 계산하여 반환"""
        self._ensure_data_cache()
        if not self._raw_data or self._data_length < 2:
            return [0.0] * count
        
        obv_values = []
        running_obv = 0.0
        
        # 시간 순서대로 처리 (과거 → 최신)
        for i in range(self._data_length):
            if i == 0:
                # 첫 번째 봉은 기준점
                obv_values.append(0.0)
                continue
            
            current_close = self._raw_data[i].get('현재가', 0)
            prev_close = self._raw_data[i - 1].get('현재가', 0)
            volume = self._raw_data[i].get('거래량', 0)
            
            if current_close > prev_close:
                # 상승일: 거래량을 더함
                running_obv += volume
            elif current_close < prev_close:
                # 하락일: 거래량을 뺌
                running_obv -= volume
            # 보합일: 변화 없음
            
            obv_values.append(running_obv)
        
        # count만큼 반환 (최신 데이터부터)
        return obv_values[-count:] if len(obv_values) >= count else obv_values
        
    def rsi(self, period: int = 14, m: int = 0) -> float:
        """상대강도지수(RSI) 계산"""
        self._ensure_data_cache()
        if not self._raw_data or m + period + 1 > self._data_length:
            return 50.0
        
        gains = 0.0
        losses = 0.0
        
        for i in range(m + 1, m + period + 1):
            prev_price = self._raw_data[i].get('현재가', 0)
            curr_price = self._raw_data[i - 1].get('현재가', 0)
            change = curr_price - prev_price
            
            if change > 0:
                gains += change
            else:
                losses += abs(change)
        
        if losses == 0:
            return 100.0
        
        avg_gain = gains / period
        avg_loss = losses / period
        rs = avg_gain / avg_loss
        
        return 100 - (100 / (1 + rs))
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9, m: int = 0) -> tuple:
        """MACD(Moving Average Convergence Divergence) 계산
        Returns: (MACD 라인, 시그널 라인, 히스토그램)
        """
        fast_ema = self.eavg(self.c, fast, m)
        slow_ema = self.eavg(self.c, slow, m)
        macd_line = fast_ema - slow_ema
        
        # 간단한 시그널 라인 (실제로는 MACD 값들의 EMA가 필요)
        signal_line = self.eavg(self.c, signal, m)
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
        hh = self.highest(self.h, k_period, m)
        ll = self.lowest(self.l, k_period, m)
        current_close = self.c(m)
        
        # %K 계산
        percent_k = 0
        if hh != ll:
            percent_k = 100 * ((current_close - ll) / (hh - ll))
        
        # %D 계산 (간단한 이동평균 사용)
        percent_d = self.avg(self.c, d_period, m)
        
        return (percent_k, percent_d)
    
    def atr(self, period: int = 14, m: int = 0) -> float:
        """평균 실제 범위(ATR) 계산"""
        self._ensure_data_cache()
        if not self._raw_data or self._data_length < period + 1 + m:
            return 0.0
        
        tr_values = []
        for i in range(m, m + period):
            if i + 1 >= len(self._raw_data):
                break
                
            high = self._raw_data[i].get('고가', 0)
            low = self._raw_data[i].get('저가', 0)
            prev_close = self._raw_data[i+1].get('현재가', 0)
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        return sum(tr_values) / len(tr_values) if tr_values else 0.0
    
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

    def is_shooting_star(self, n: int = 0, upper_ratio: float = 2.0, body_ratio: float = 0.3) -> bool:
        """
        유성형(슈팅스타) 캔들 패턴 판단
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            upper_ratio: 위꼬리가 몸통의 몇 배 이상이어야 하는지 (기본값: 2.0)
            body_ratio: 몸통이 전체 캔들의 몇 % 이하여야 하는지 (기본값: 0.3)
        
        Returns:
            bool: 유성형 캔들이면 True
            
        유성형 조건:
        1. 위꼬리가 몸통보다 현저히 길어야 함 (upper_ratio배 이상)
        2. 아래꼬리는 짧거나 없어야 함 (몸통의 50% 이하)
        3. 몸통은 전체 캔들 대비 작아야 함 (body_ratio 이하)
        4. 상승 추세에서 나타나는 하락 반전 신호
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return False
        
        candle = self._raw_data[n]
        
        o = candle.get('시가', 0)
        h = candle.get('고가', 0) 
        l = candle.get('저가', 0)
        c = candle.get('현재가', 0)
        
        # 기본 검증
        if h <= l or o <= 0 or c <= 0: return False
        
        # 몸통, 위꼬리, 아래꼬리 크기 계산
        body = abs(c - o)                    # 몸통 크기
        upper_shadow = h - max(o, c)         # 위꼬리 크기  
        lower_shadow = min(o, c) - l         # 아래꼬리 크기
        total_range = h - l                  # 전체 캔들 크기
        
        # 전체 캔들 크기가 0이면 판단 불가
        if total_range == 0: return False
        
        # 조건 1: 위꼬리가 몸통의 upper_ratio배 이상
        if body > 0:
            upper_body_ratio = upper_shadow / body
            if upper_body_ratio < upper_ratio:
                return False
        else:
            # 몸통이 0이면 위꼬리만 있어도 유성형으로 간주
            if upper_shadow == 0:
                return False
        
        # 조건 2: 아래꼬리는 몸통의 50% 이하 (짧아야 함)
        if body > 0 and lower_shadow > body * 0.5:
            return False
        
        # 조건 3: 몸통이 전체 캔들의 body_ratio 이하 (작아야 함)
        body_percentage = body / total_range
        if body_percentage > body_ratio:
            return False
        
        # 조건 4: 위꼬리가 전체 캔들의 상당 부분을 차지해야 함 (50% 이상)
        upper_percentage = upper_shadow / total_range
        if upper_percentage < 0.5:
            return False
        
        return True

    def is_inverted_hammer(self, n: int = 0, upper_ratio: float = 2.0, body_ratio: float = 0.3) -> bool:
        """
        역망치형(역해머) 캔들 패턴 판단 - 하락 추세에서의 상승 반전 신호
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            upper_ratio: 위꼬리가 몸통의 몇 배 이상이어야 하는지
            body_ratio: 몸통이 전체 캔들의 몇 % 이하여야 하는지
        
        Returns:
            bool: 역망치형 캔들이면 True
            
        Note: 유성형과 모양은 같지만 나타나는 위치(하락 추세)에 따라 의미가 다름
        """
        # 캔들 모양은 유성형과 동일
        return self.is_shooting_star(n, upper_ratio, body_ratio)

    def is_hanging_man(self, n: int = 0, lower_ratio: float = 2.0, body_ratio: float = 0.3) -> bool:
        """
        교수형(행잉맨) 캔들 패턴 판단 - 상승 추세에서의 하락 반전 신호
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            lower_ratio: 아래꼬리가 몸통의 몇 배 이상이어야 하는지
            body_ratio: 몸통이 전체 캔들의 몇 % 이하여야 하는지
        
        Returns:
            bool: 교수형 캔들이면 True
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        
        candle = self._raw_data[n]
        
        o = candle.get('시가', 0)
        h = candle.get('고가', 0)
        l = candle.get('저가', 0)
        c = candle.get('현재가', 0)
        
        if h <= l or o <= 0 or c <= 0:
            return False
        
        body = abs(c - o)
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        total_range = h - l
        
        if total_range == 0:
            return False
        
        # 조건 1: 아래꼬리가 몸통의 lower_ratio배 이상
        if body > 0:
            lower_body_ratio = lower_shadow / body
            if lower_body_ratio < lower_ratio:
                return False
        else:
            if lower_shadow == 0:
                return False
        
        # 조건 2: 위꼬리는 몸통의 50% 이하 (짧아야 함)
        if body > 0 and upper_shadow > body * 0.5:
            return False
        
        # 조건 3: 몸통이 전체 캔들의 body_ratio 이하
        body_percentage = body / total_range
        if body_percentage > body_ratio:
            return False
        
        # 조건 4: 아래꼬리가 전체 캔들의 상당 부분을 차지해야 함
        lower_percentage = lower_shadow / total_range
        if lower_percentage < 0.5:
            return False
        
        return True
    
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
        
        if candle_range == 0 or body == 0: return False
            
        # 아래 꼬리가 몸통의 2배 이상이고, 전체 캔들의 1/3 이상이면 망치형으로 간주
        return (lower_shadow >= 2 * body) and (lower_shadow / candle_range >= 0.33)
    
    def is_engulfing(self, n: int = 0, bullish: bool = True) -> bool:
        """포괄 패턴 확인 (이전 캔들을 완전히 덮는 형태)
        bullish=True: 상승 포괄 패턴, bullish=False: 하락 포괄 패턴
        """
        self._ensure_data_cache()
        if not self._raw_data or n + 1 >= self._data_length: return False
            
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
        
    # 스크립트 함수들
    def bar(self, n: int = 0) -> int:
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return (0, 0, 0, 0, 0, 0)
        
        return (self._raw_data[n].get('시가', 0), self._raw_data[n].get('고가', 0), self._raw_data[n].get('저가', 0), \
            self._raw_data[n].get('현재가', 0), self._raw_data[n].get('거래량', 0), self._raw_data[n].get('거래대금', 0),)

    def longest_bar(self, p: float = 2.0, n: int = 0) -> tuple:
        """
            당일 가장 긴 봉 찾기
            P: 현재가 대비 몇 % 이상 조건
            n: 검사할 기준날짜 봉 인덱스 0=현재봉
        """
        if self.cycle != 'mi': return (0, '', 0, 0, 0, 0, 0, 0)
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return (0, '', 0, 0, 0, 0, 0, 0)
        date_str = self._raw_data[n].get('체결시간', '')[:8]
        length, pos = 0, 0
        for i in range(n, len(self._raw_data)):
            if self._raw_data[i].get('체결시간', '')[:8] != date_str:
                break
            diff = self._raw_data[i].get('종가', 0) - self._raw_data[i].get('시가', 0)
            if diff > length:
                length = diff
                pos = i
        if (length / self._raw_data[pos].get('시가', 0)) * 100 < p: return (0, '', 0, 0, 0, 0, 0, 0)
        time, open, high, low, close, volume, amount = self._raw_data[pos].get('체결시간', ''), self._raw_data[pos].get('시가', 0), self._raw_data[pos].get('고가', 0), \
            self._raw_data[pos].get('저가', 0), self._raw_data[pos].get('현재가', 0), self._raw_data[pos].get('거래량', 0), \
            self._raw_data[pos].get('거래대금', 0)

        return (pos, time, open, high, low, close, volume, amount)

    def past_bars(self, dt: str = None) -> int:
        """당일 분봉 개수 반환"""
        if self.cycle != 'mi': return 0
        self._ensure_data_cache()
        if not self._raw_data: return 0
        if dt is None: dt = datetime.now().strftime('%Y%m%d')
        bars = 0
        for i in range(self._data_length):
            if self._raw_data[i].get('체결시간', '')[:8] == dt:
                bars += 1
            else:
                break
        return bars

    def get_extremes(self, n: int = 128, m: int = 1) -> dict:
        """
        현재봉 기준 n개 봉에서 각종 극값들을 구함
        
        Args:
            n: 검사할 봉 개수
            m: 시작 봉 인덱스 0=현재봉
        
        Returns:
            dict: {
                'hh': 최고고가,
                'hc': 최고종가, 
                'lc': 최저종가,
                'll': 최저저가,
                'hv': 최고거래량,
                'lv': 최저거래량,
                'ha': 최고거래대금,
                'la': 최저거래대금,
                'close': 전일종가,
                'bars': 당일 봉 개수
            }
        """
        self._ensure_data_cache()
        if not self._raw_data or n <= 0:
            return { 'hh': 0, 'hc': 0, 'lc': 0, 'll': 0, 'hv': 0, 'lv': 0, 'ha': 0, 'la': 0, 'close': 0, 'bars': 0 }
        
        # 시작 인덱스 설정
        today = datetime.now().strftime('%Y%m%d')
        start_idx = m
        end_idx = start_idx + n
        
        # 데이터 길이 체크
        if end_idx > self._data_length:
            end_idx = self._data_length
        
        if start_idx >= end_idx:
            return { 'hh': 0, 'hc': 0, 'lc': 0, 'll': 0, 'hv': 0, 'lv': 0, 'ha': 0, 'la': 0, 'close': 0, 'bars': 0 }
        
        # 초기값 설정 (첫 번째 봉)
        first_candle = self._raw_data[start_idx]
        hh = first_candle.get('고가', 0)
        hc = first_candle.get('현재가', 0)
        lc = first_candle.get('현재가', 0)
        ll = first_candle.get('저가', 0)
        hv = first_candle.get('거래량', 0)
        lv = first_candle.get('거래량', 0)
        ha = first_candle.get('거래대금', 0)
        la = first_candle.get('거래대금', 0)
        close = 0
        bars = m + 1
        
        # n개 봉 순회하면서 극값 찾기
        for i in range(start_idx + 1, end_idx):
            candle = self._raw_data[i]
            
            high = candle.get('고가', 0)
            close = candle.get('현재가', 0)
            low = candle.get('저가', 0)
            volume = candle.get('거래량', 0)
            amount = candle.get('거래대금', 0)
            
            # 최고값들 업데이트
            if high > hh: hh = high
            if close > hc: hc = close
            if volume > hv: hv = volume
            if amount > ha: ha = amount
            
            # 최저값들 업데이트
            if close < lc: lc = close
            if low < ll: ll = low
            if volume < lv: lv = volume
            if amount < la: la = amount
        
            if self.cycle == 'mi':
                if candle.get('체결시간', '')[:8] == today:
                    bars += 1

        # bars가 데이터 범위를 벗어나지 않도록 안전하게 처리
        if bars < self._data_length:
            close = self._raw_data[bars].get('현재가', 0)
        else:
            close = 0
        return { 'hh': hh, 'hc': hc, 'lc': lc, 'll': ll, 'hv': hv, 'lv': lv, 'ha': ha, 'la': la, 'close': close, 'bars': bars }

    def top_volume_avg(self, n: int = 128, cnt: int = 10, m: int = 1) -> float:
        """
        현재봉 기준 m봉 이전부터 n개 봉 중 거래량 상위 cnt개의 평균값
        
        Args:
            m: 현재봉에서 m봉 이전부터 시작 (기본값: 1)
            n: 검사할 봉 개수 (기본값: 128) 
            cnt: 상위 몇 개를 선택할지 (기본값: 10)
        
        Returns:
            float: 상위 cnt개 거래량의 평균값
        """
        self._ensure_data_cache()
        if not self._raw_data or n <= 0 or cnt <= 0 or m < 0:
            return 0.0
        
        # 시작 인덱스와 끝 인덱스 설정
        start_idx = m
        end_idx = start_idx + n
        
        # 데이터 길이 체크
        if start_idx >= self._data_length:
            return 0.0
        
        if end_idx > self._data_length:
            end_idx = self._data_length
        
        if start_idx >= end_idx:
            return 0.0
        
        # 지정된 범위의 거래량 수집
        volumes = []
        for i in range(start_idx, end_idx):
            volume = self._raw_data[i].get('거래량', 0)
            if volume > 0:  # 0보다 큰 거래량만 수집
                volumes.append(volume)
        
        # 거래량이 없으면 0 반환
        if not volumes:
            return 0.0
        
        # cnt가 실제 데이터 개수보다 크면 전체 데이터 사용
        actual_cnt = min(cnt, len(volumes))
        
        # 거래량 내림차순 정렬 후 상위 cnt개 선택
        volumes.sort(reverse=True)
        top_volumes = volumes[:actual_cnt]
        
        # 평균 계산
        return sum(top_volumes) / len(top_volumes)

    def top_amount_avg(self, n: int = 128, cnt: int = 10, m: int = 1) -> float:
        """
        현재봉 기준 m봉 이전부터 n개 봉 중 거래대금 상위 cnt개의 평균값
        
        Args:
            m: 현재봉에서 m봉 이전부터 시작 (기본값: 1)
            n: 검사할 봉 개수 (기본값: 130)
            cnt: 상위 몇 개를 선택할지 (기본값: 10)
        
        Returns:
            float: 상위 cnt개 거래대금의 평균값
        """
        self._ensure_data_cache()
        if not self._raw_data or n <= 0 or cnt <= 0 or m < 0:
            return 0.0
        
        # 시작 인덱스와 끝 인덱스 설정
        start_idx = m
        end_idx = start_idx + n
        
        # 데이터 길이 체크
        if start_idx >= self._data_length:
            return 0.0
        
        if end_idx > self._data_length:
            end_idx = self._data_length
        
        if start_idx >= end_idx:
            return 0.0
        
        # 지정된 범위의 거래대금 수집
        amounts = []
        for i in range(start_idx, end_idx):
            amount = self._raw_data[i].get('거래대금', 0)
            if amount > 0:  # 0보다 큰 거래대금만 수집
                amounts.append(amount)
        
        # 거래대금이 없으면 0 반환
        if not amounts:
            return 0.0
        
        # cnt가 실제 데이터 개수보다 크면 전체 데이터 사용
        actual_cnt = min(cnt, len(amounts))
        
        # 거래대금 내림차순 정렬 후 상위 cnt개 선택
        amounts.sort(reverse=True)
        top_amounts = amounts[:actual_cnt]
        
        # 평균 계산
        return sum(top_amounts) / len(top_amounts)

    def get_close_tops(self, n: int = 128, cnt: int = 80, m: int = 1) -> tuple:
        """
        각 봉이 자신을 포함한 cnt개 봉 중 최고 종가인지 확인하여 인덱스를 수집 분봉만 해당
        
        Args:
            m: 검사 종료 인덱스 (0=현재봉까지, 1=1봉까지, 3=3봉까지...)
            n: 검사 시작 기준 (130이면 129+m부터 시작)
            cnt: 비교할 봉 개수 (자신 포함)
        
        Returns:
            tuple: (최고종가_인덱스_리스트, 당일_봉_개수)
            
        """
        if self.cycle != 'mi': return ([], 0)

        self._ensure_data_cache()
        if not self._raw_data or m < 0 or n <= 0 or cnt <= 0:
            return ([], 0)
        
        high_close_indices = []
        
        # 당일 봉 개수 계산
        today_bars = 0
        today = datetime.now().strftime('%Y%m%d')
        for i in range(self._data_length):
            if self._raw_data[i].get('체결시간', '')[:8] == today:
                today_bars += 1
            else:
                break
        
        # n-1+m부터 m까지 역순으로 검사
        start_idx = n - 1 + m  # n=130, m=0이면 129부터, m=3이면 132부터
        end_idx = m            # m=0이면 0까지, m=3이면 3까지
        
        for current_idx in range(start_idx, end_idx - 1, -1):  # 역순
            if current_idx >= self._data_length:
                continue
            
            # 현재 검사 중인 봉의 종가
            current_close = self._raw_data[current_idx].get('현재가', 0)
            
            # 비교 범위: current_idx부터 current_idx + cnt - 1까지
            compare_start = current_idx
            compare_end = current_idx + cnt
            
            # 데이터 길이 체크
            if compare_end > self._data_length:
                compare_end = self._data_length
            
            if compare_start >= compare_end:
                continue
            
            # 비교 범위에서 최고 종가 찾기
            max_close = 0
            for i in range(compare_start, compare_end):
                close = self._raw_data[i].get('현재가', 0)
                if close > max_close:
                    max_close = close
            
            # 현재 봉의 종가가 비교 범위의 최고 종가 이상이면 인덱스 추가
            if current_close >= max_close and max_close > 0:
                high_close_indices.append(current_idx)
        
        return (high_close_indices, today_bars)

    def consecutive_count(self, condition_func, m: int = 0, max_check: int = 128) -> int:
        """
        이전 m봉 기준으로 condition이 몇 번 연속으로 발생했는지 계산
        
        Args:
            condition_func: 조건을 확인할 함수 (인덱스를 받아 bool 반환)
            m: 시작 기준 봉 (0=현재봉부터, 1=1봉전부터...)
            max_check: 최대 확인할 봉 개수 (무한루프 방지)
        
        Returns:
            int: 연속으로 조건을 만족한 봉의 개수
            
        예시:
            # 현재봉부터 연속으로 상승한 봉 개수
            count = cm.consecutive_count(lambda i: cm.c(i) > cm.c(i+1), 0)
            
            # 1봉 전부터 연속으로 거래량이 평균보다 높은 봉 개수  
            count = cm.consecutive_count(lambda i: cm.v(i) > cm.avg(cm.v, 20, i), 1)
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func):
            return 0
        
        count = 0
        current_idx = m
        
        # m봉부터 시작해서 조건이 만족되는 동안 계속 확인
        while current_idx < self._data_length and count < max_check:
            try:
                # 조건 함수 호출하여 확인
                if condition_func(current_idx):
                    count += 1
                    current_idx += 1
                else:
                    # 조건이 만족되지 않으면 중단
                    break
            except (IndexError, TypeError, ValueError):
                # 조건 함수에서 오류 발생시 중단
                break
        
        return count

    def consecutive_true_false(self, condition_func, m: int = 0, max_check: int = 100) -> tuple:
        """
        이전 m봉 기준으로 연속 True 개수와 그 이후 연속 False 개수를 반환
        
        Args:
            condition_func: 조건을 확인할 함수
            m: 시작 기준 봉 
            max_check: 최대 확인할 봉 개수
        
        Returns:
            tuple: (연속_True_개수, 연속_False_개수)
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func):
            return (0, 0)
        
        true_count = 0
        false_count = 0
        current_idx = m
        checking_true = True  # 처음에는 True 개수를 세는 중
        
        while current_idx < self._data_length and (true_count + false_count) < max_check:
            try:
                result = condition_func(current_idx)
                
                if checking_true:
                    if result:
                        true_count += 1
                    else:
                        # True에서 False로 전환
                        checking_true = False
                        false_count += 1
                else:
                    if not result:
                        false_count += 1
                    else:
                        # False에서 True로 전환되면 중단
                        break
                
                current_idx += 1
                
            except (IndexError, TypeError, ValueError):
                break
        
        return (true_count, false_count)

    def streak_pattern(self, condition_func, pattern: str, m: int = 0, max_check: int = 100) -> bool:
        """
        특정 패턴이 연속으로 나타나는지 확인
        
        Args:
            condition_func: 조건을 확인할 함수
            pattern: 확인할 패턴 ('T'=True, 'F'=False) 예: "TTTFF", "TFTF"
            m: 시작 기준 봉
            max_check: 최대 확인할 봉 개수
        
        Returns:
            bool: 패턴이 일치하면 True
            
        예시:
            # 상승-상승-하락-하락 패턴 확인
            pattern_match = cm.streak_pattern(
                lambda i: cm.c(i) > cm.c(i+1), 
                "TTFF", 
                0
            )
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func) or not pattern:
            return False
        
        pattern_length = len(pattern)
        if pattern_length > max_check:
            return False
        
        for i, expected in enumerate(pattern):
            current_idx = m + i
            
            if current_idx >= self._data_length:
                return False
            
            try:
                actual = condition_func(current_idx)
                expected_bool = (expected.upper() == 'T')
                
                if actual != expected_bool:
                    return False
                    
            except (IndexError, TypeError, ValueError):
                return False
        
        return True

    def find_last_condition_break(self, condition_func, m: int = 0, max_check: int = 128) -> int:
        """
        m봉부터 시작해서 조건이 마지막으로 깨진 위치 찾기
        
        Args:
            condition_func: 조건을 확인할 함수
            m: 시작 기준 봉
            max_check: 최대 확인할 봉 개수
        
        Returns:
            int: 조건이 마지막으로 깨진 봉의 인덱스 (-1이면 찾지 못함)
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func):
            return -1
        
        last_break_idx = -1
        current_idx = m
        
        while current_idx < self._data_length and (current_idx - m) < max_check:
            try:
                if not condition_func(current_idx):
                    last_break_idx = current_idx
                current_idx += 1
            except (IndexError, TypeError, ValueError):
                break
        
        return last_break_idx

    # 캐시 관리 함수들
    def clear_cache(self, code=None):
        """특정 코드 또는 전체 캐시 초기화"""
        if code:
            # 특정 코드만 캐시 초기화
            if hasattr(self, '_cache_version'):
                self._cache_version = -1
            if hasattr(self, '_raw_data'):
                self._raw_data = None
        else:
            # 전체 캐시 초기화
            if hasattr(self, '_cache_version'):
                self._cache_version = -1
            if hasattr(self, '_raw_data'):
                self._raw_data = None

    def get_ma(self, period: int = 20, count: int = 1) -> list:
        """이동평균 리스트 반환"""
        self._ensure_data_cache()
        if not self._raw_data or self._data_length < period:
            return []
        
        ma_list = []
        for i in range(count):
            if i + period > len(self._raw_data):
                break
            total = 0.0
            for j in range(i, i + period):
                total += self._raw_data[j].get('현재가', 0)
            ma_list.append(total / period)
        
        return ma_list
    
    # 원본 데이터 직접 접근 함수
    def get_raw_data(self):
        """원본 데이터 직접 반환 (최고 성능)"""
        self._ensure_data_cache()
        return self._raw_data
    
    def get_data_length(self) -> int:
        """데이터 길이 반환"""
        self._ensure_data_cache()
        return self._data_length
                
class ScriptManager:
    # 허용된 Python 기능 목록 (whitelist 방식)
    ALLOWED_MODULES = [
        're', 'math', 'datetime', 'random', 'logging', 'json', 'collections',
        'time', 'calendar', 'decimal', 'fractions', 'statistics',
        'itertools', 'functools', 'operator', 'string', 'textwrap', 'unicodedata',
        'copy', 'heapq', 'bisect', 'weakref', 'array', 'struct'
    ]

    # 허용된 Python 내장 함수 및 타입
    ALLOWED_BUILTINS = [
        'int', 'float', 'str', 'bool', 'list', 'dict', 'set', 'tuple',
        'len', 'max', 'min', 'sum', 'abs', 'all', 'any', 'round', 'sorted',
        'enumerate', 'zip', 'range', 'type', 'isinstance', 'hasattr', 'getattr', 'setattr',
        'reversed', 'filter', 'map', 'next', 'iter', 'chr', 'ord', 'hex', 'oct', 'bin',
        'divmod', 'pow', 'slice', 'vars', 'dir', 'callable', 'format', 'repr',
        'frozenset', 'bytearray', 'bytes', 'memoryview', 'complex', 'property',
        'staticmethod', 'classmethod', 'super', 'object'
    ]

    # 허용되지 않는 문법 패턴
    FORBIDDEN_PATTERNS = [
        r'import\s+(?!(' + '|'.join(ALLOWED_MODULES) + ')$)',
        r'open\s*\(',
        r'exec\s*\(',
        r'eval\s*\(',
        r'__import__',
        r'subprocess',
        r'os\.',
        r'sys\.',
        r'while\s+.*:',
    ]

    def __init__(self, script_file=dc.fp.scripts_file):
        """초기화"""
        self.script_file = script_file
        self.scripts = {}  # {script_name: {script: str, type: str, desc: str}}
        self._running_scripts = set()  # 실행 중인 스크립트 추적
        self.cht_dt = ChartData()  # 차트 데이터 관리자
        
        # 스레드별 컨텍스트 관리
        self._thread_local = threading.local()
        
        # 🚀 성능 최적화를 위한 캐시들
        self._module_cache = {}  # 모듈 캐시
        self._script_wrapper_cache = {}  # 스크립트 래퍼 캐시
        self._compiled_script_cache = {}  # 컴파일된 스크립트 캐시

        # 파일에서 스크립트 로드
        self._load_scripts()

    def _get_current_context(self) -> Dict[str, Any]:
        """현재 스레드의 실행 컨텍스트 가져오기"""
        if not hasattr(self._thread_local, 'context'):
            self._thread_local.context = {}
        return self._thread_local.context

    def _set_current_context(self, kwargs: Dict[str, Any]):
        """현재 스레드의 실행 컨텍스트 설정"""
        self._thread_local.context = kwargs.copy()

    def _update_context_variable(self, key: str, value: Any):
        """컨텍스트 특정 변수 업데이트"""
        if hasattr(self._thread_local, 'context'):
            self._thread_local.context[key] = value

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
        """스크립트 구문 검증"""
        # 스크립트 이름 유효성 검사
        if not script_name.isidentifier():
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
        """검증된 스크립트 실행"""
        start_time = time.time()
        
        # 결과 초기화
        result_dict = {
            'result': None,     # 스크립트 실행 결과값 (ret()로 설정된 값)
            'error': None,      # 에러 메시지 (None이면 정상, 값이 있으면 실패)
            'type': None,       # result의 데이터 타입
            'logs': [],         # 실행 로그 (성공/실패 관계없이 수집)
        }
        
        # 종목코드 검증 (check_only=True일 때는 건너뛰기)
        if not hasattr(self, '_check_only') or not self._check_only:
            code = kwargs.get('code')
            if code is None:
                result_dict['error'] = "종목코드가 지정되지 않았습니다."
                result_dict['logs'].append('ERROR: 종목코드가 지정되지 않았습니다.')
                return result_dict
        else:
            # check_only=True일 때는 임시 코드 사용
            code = 'CHECK_ONLY'
        
        # 순환 참조 방지 (check_only=True일 때는 건너뛰기)
        if not hasattr(self, '_check_only') or not self._check_only:
            # 호출 스택 기반 순환 참조 감지
            current_stack = self._get_current_call_stack()
            if script_name in current_stack:
                result_dict['error'] = f"순환 참조 감지: {script_name} → {' → '.join(current_stack)}"
                result_dict['logs'].append(f'ERROR: 순환 참조 감지: {script_name} → {" → ".join(current_stack)}')
                return result_dict
            
            # 실행 중인 스크립트에 추가 (스택 기반)
            self._add_to_running_stack(script_name)
        
        # 현재 컨텍스트 설정
        self._set_current_context(kwargs)
        
        try:
            # 실행 환경 준비
            globals_dict, script_logs = self._prepare_execution_globals(script_name)
            locals_dict = {}
            
            # 🚀 스크립트 컴파일 캐싱 - 스크립트 내용만으로 키 생성
            script_key = f"{script_name}:{hash(script)}"
            
            if script_key not in self._compiled_script_cache:
                logging.debug(f"🔄 {script_name} 컴파일 중... (첫 실행)")
                # 스크립트 내용만으로 래퍼 생성 (kwargs 제외)
                wrapped_script = self._make_wrapped_script(script)
                code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                self._compiled_script_cache[script_key] = code_obj
            # else:
            #     logging.debug(f"⚡ {script_name} 캐시 사용 (재실행)")
            
            # ✅ 캐시된 코드 사용, kwargs는 실행 시점에 전달
            code_obj = self._compiled_script_cache[script_key]
            
            # 🚀 kwargs 변수 설정 - 실행 시점에 전달
            locals_dict['kwargs'] = kwargs
            globals_dict['kwargs'] = kwargs  # 래퍼 스크립트에서 접근할 수 있도록
            globals_dict['_current_kwargs'] = kwargs
            
            # 코드 실행
            script_result = None
            try:
                exec(code_obj, globals_dict, locals_dict)
                script_result = globals_dict.get('_script_result')
            except SystemExit as e:
                if str(e) == 'script_return':
                    script_result = globals_dict.get('_script_result')
                else:
                    raise e
            
            exec_time = time.time() - start_time
            
            # 실행 시간 경고
            if exec_time > 0.01:
                warning_msg = f"스크립트 실행 기준(0.01초) ({script_name}:{code}): {exec_time:.4f}초"
                #logging.warning(warning_msg)
                script_logs.append(f'WARNING: {warning_msg}')
            
            result_dict['result'] = script_result
            result_dict['logs'] = script_logs
            
            return result_dict
            
        except Exception as e:
            tb = traceback.format_exc()
            
            # 상세한 에러 정보 생성
            detailed_error = self._get_script_error_location(tb, script)
            
            if not hasattr(script_logs, 'append'):
                script_logs = []
            
            script_logs.append(f"ERROR: {detailed_error}")
            script_logs.append(f"TRACEBACK: {tb}")
            
            logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}\n{tb}")
            
            result_dict['error'] = detailed_error
            result_dict['logs'] = script_logs
            return result_dict
            
        finally:
            # 실행 완료 후 추적 목록에서 제거 (check_only=True일 때는 건너뛰기)
            if not hasattr(self, '_check_only') or not self._check_only:
                # 기존 방식 제거
                if hasattr(self, '_running_scripts') and script_key in self._running_scripts:
                    self._running_scripts.remove(script_key)
                
                # 새로운 스택 방식 제거
                self._remove_from_running_stack(script_name)

    def run_script(self, script_name, script_contents=None, check_only=False, kwargs=None):
        """스크립트 검사 및 실행"""
        if kwargs is None:
            kwargs = {}
        
        # 결과 초기화
        result_dict = {
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
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
        if check_only:
            self._check_only = True
        exec_result = self._execute_validated_script(script_name, script_contents, kwargs)
        if check_only:
            self._check_only = False
        
        # 결과 복사
        result_dict['result'] = exec_result['result']
        result_dict['error'] = exec_result['error']
        result_dict['logs'] = exec_result['logs']
        
        # 타입 설정 (정상 실행된 경우에만)
        if result_dict['error'] is None:
            result_dict['type'] = self.get_script_type(result_dict['result'])
        
        return result_dict

    def set_script(self, script_name: str, script: str, desc: str = '', kwargs: dict = None, save: bool = True):
        """스크립트 검사 및 저장"""
        if kwargs is None:
            kwargs = {}
        
        # 🚀 스크립트 변경 시 캐시 무효화
        self._invalidate_script_cache(script_name)
        
        # 결과 초기화
        result_dict = {
            'result': None,
            'error': None,
            'type': None,
            'logs': [],
        }
        
        # 검사 실행 (check_only=True일 때는 kwargs 검증 건너뛰기)
        check_result = self.run_script(script_name, check_only=True, script_contents=script, kwargs={})
        
        # 결과 복사
        result_dict['logs'] = check_result['logs'].copy()
        result_dict['result'] = check_result['result']
        
        if check_result['error'] is not None or check_result['type'] == 'error':
            result_dict['error'] = check_result['error'] or 'result가 None입니다.'
            return result_dict
        
        # 스크립트 타입 설정
        result_dict['type'] = check_result['type']
        
        # save=False면 검사까지만 하고 반환
        if not save:
            return result_dict
        
        # save=True인 경우 저장 진행
        script_data = {
            'script': script,
            'type': result_dict['type'],
            'desc': desc
        }
        
        self.scripts[script_name] = script_data
        
        # 파일 저장
        save_result = self._save_scripts()
        if not save_result:
            result_dict['error'] = '파일 저장 실패'
            result_dict['logs'].append('ERROR: 파일 저장 실패')
            return result_dict

        # 성공
        result_dict['logs'].append(f'INFO: 스크립트 저장 완료: {script_name}')
        
        return result_dict

    def delete_script(self, script_name: str):
        """스크립트 삭제"""
        if script_name in self.scripts:
            try:
                del self.scripts[script_name]
                logging.info(f"스크립트 삭제 완료: {script_name}")
                return self._save_scripts()
            except Exception as e:
                logging.error(f"스크립트 삭제 오류 ({script_name}): {e}")
                return False
        return False
    
    def _has_forbidden_syntax(self, script: str) -> bool:
        """금지된 구문이 있는지 확인"""
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, script):
                return True
        
        # AST 분석을 통한 추가 검사
        try:
            tree = ast.parse(script)
            
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
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                        if func_name in ['eval', 'exec', '__import__']:
                            self.has_forbidden = True
                            self.forbidden_reason = f"금지된 함수 호출: {func_name}"
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
        """안전한 루프 실행 함수"""
        results = []
        for item in iterable:
            results.append(func(item))
        return results
    
    def _get_script_error_location(self, tb_str, script):
        """스크립트 에러 위치 추출하여 한 줄 에러 메시지 반환"""
        try:
            lines = tb_str.splitlines()
            error_line_num = None
            error_msg = "알 수 없는 오류"
            
            for line in lines:
                if "File \"<string>\"" in line and ", line " in line:
                    match = re.search(r", line (\d+)", line)
                    if match:
                        wrapper_offset = 13
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
        """실행 환경의 글로벌 변수 준비"""
        try:
            script_logs = []
            
            # Python 내장 함수 제한
            restricted_builtins = {}
            builtins_dict = __builtins__ if isinstance(__builtins__, dict) else dir(__builtins__)
            
            for name in self.ALLOWED_BUILTINS:
                if name in builtins_dict:
                    if isinstance(__builtins__, dict):
                        restricted_builtins[name] = __builtins__[name]
                    else:
                        restricted_builtins[name] = getattr(__builtins__, name)
            
            # 🚀 모듈 캐싱 - 한 번만 로드
            if not self._module_cache:
                for module_name in self.ALLOWED_MODULES:
                    try:
                        self._module_cache[module_name] = __import__(module_name)
                    except ImportError:
                        logging.warning(f"모듈 로드 실패: {module_name}")
            
            # ✅ 캐시된 모듈 사용
            modules = self._module_cache.copy()
            
            # 유틸리티 함수들
            def echo(msg):
                script_logs.append(f"{current_script_name}: {msg}")

            def script_return(result=None):
                script_return.caller_globals['_script_result'] = result
                raise SystemExit('script_return')
            
            def is_args(key, default_value):
                # 현재 스크립트 호출시 전달된 kwargs에서 확인
                if '_call_kwargs' in globals_dict:
                    call_kwargs = globals_dict['_call_kwargs']
                    if key in call_kwargs:
                        return call_kwargs[key]
                
                # 전체 컨텍스트에서 확인
                current_context = self._get_current_context()
                return current_context.get(key, default_value)
            
            def safe_div(a, b, default=0):
                try:
                    return a / b
                except:
                    return default
                
            def safe_iif(condition, true_value, false_value):
                try:
                    return true_value if condition else false_value
                except:
                    return false_value
                
            # 글로벌 환경 설정
            globals_dict = {
                **restricted_builtins,
                **modules,
                'ChartManager': ChartManager,
                'CM': ChartManager,
                'loop': self._safe_loop,
                'div': safe_div,
                'iif': safe_iif,
                'run_script': self._script_caller,
                'is_args': is_args,
                'hoga': lambda x, y: hoga(x, y),
                'echo': echo,
                'ret': script_return,
                '_script_logs': script_logs,
                '_current_kwargs': {},
                '_script_result': None,
            }
            
            script_return.caller_globals = globals_dict
            
            # 🚀 스크립트 래퍼 캐싱 - 한 번만 생성
            if not self._script_wrapper_cache:
                for script_name, script_data in self.scripts.items():
                    wrapper_code = f"""
def {script_name}(*args, **kwargs):
    return run_script('{script_name}', args, kwargs)
"""
                    try:
                        # 래퍼 함수를 미리 컴파일하여 캐시
                        compiled_wrapper = compile(wrapper_code, f"<wrapper_{script_name}>", 'exec')
                        self._script_wrapper_cache[script_name] = compiled_wrapper
                    except Exception as e:
                        logging.error(f"스크립트 래퍼 생성 오류 ({script_name}): {e}")
            
            # ✅ 캐시된 래퍼 실행
            for script_name, compiled_wrapper in self._script_wrapper_cache.items():
                exec(compiled_wrapper, globals_dict, globals_dict)
            
            return globals_dict, script_logs
            
        except Exception as e:
            logging.error(f"실행 환경 준비 오류: {e}")
            return {'ChartManager': ChartManager}, []
        
    def _script_caller(self, script_name, args=None, kwargs=None):
        """스크립트 내에서 다른 스크립트를 호출하기 위한 함수"""
        # 현재 컨텍스트에서 기본값 가져오기
        current_context = self._get_current_context()
        
        # 프레임 검사로 현재 실행 중인 변수값 가져오기
        try:
            import inspect
            frame = inspect.currentframe().f_back
            
            while frame:
                if frame.f_code.co_name == 'user_script':
                    frame_locals = frame.f_locals
                    # 현재 로컬 변수값으로 컨텍스트 업데이트
                    if 'code' in frame_locals:
                        self._update_context_variable('code', frame_locals['code'])
                    if 'name' in frame_locals:
                        self._update_context_variable('name', frame_locals['name'])
                    if 'qty' in frame_locals:
                        self._update_context_variable('qty', frame_locals['qty'])
                    if 'price' in frame_locals:
                        self._update_context_variable('price', frame_locals['price'])
                    break
                frame = frame.f_back
                        
        except:
            pass
        
        # 업데이트된 컨텍스트 가져오기
        new_kwargs = self._get_current_context().copy()
        
        # 추가 인자 처리
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        
        new_kwargs.update(kwargs)
        
        # 기본 검증
        code = new_kwargs.get('code')
        if code is None:
            logging.error(f"{script_name} 에서 code 가 지정되지 않았습니다.")
            return None
        
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            logging.error(f"순환 참조 감지: {script_name}")
            return None
        
        # 스크립트 실행
        result = self.run_script(script_name, kwargs=new_kwargs)
        
        # 실행 전에 호출 kwargs 설정 (is_args용)
        try:
            import inspect
            frame = inspect.currentframe().f_back
            while frame:
                if '_current_kwargs' in frame.f_globals:
                    frame.f_globals['_call_kwargs'] = kwargs or {}
                    break
                frame = frame.f_back
        except:
            pass
        
        # 하위 스크립트 로그를 상위로 통합
        try:
            import inspect
            frame = inspect.currentframe().f_back
            while frame:
                if '_script_logs' in frame.f_globals:
                    parent_logs = frame.f_globals['_script_logs']
                    if result.get('logs'):
                        parent_logs.extend(result['logs'])
                    break
                frame = frame.f_back
        except:
            pass
        
        return result['result'] if result['error'] is None else False  # 실행 성공시 result, 실패시 False 반환
    
    def _invalidate_script_cache(self, script_name: str):
        """스크립트 변경 시 캐시 무효화"""
        # 컴파일된 스크립트 캐시에서 해당 스크립트 제거
        keys_to_remove = [key for key in self._compiled_script_cache.keys() if key.startswith(f"{script_name}:")]
        for key in keys_to_remove:
            del self._compiled_script_cache[key]
        
        # 스크립트 래퍼 캐시에서도 제거
        if script_name in self._script_wrapper_cache:
            del self._script_wrapper_cache[script_name]
        
        logging.debug(f"🗑️ {script_name} 캐시 무효화 완료")
    
    def get_cache_status(self):
        """캐시 상태 확인"""
        return {
            'module_cache': len(self._module_cache),
            'script_wrapper_cache': len(self._script_wrapper_cache),
            'compiled_script_cache': len(self._compiled_script_cache),
            'total_scripts': len(self.scripts)
        }
    
    def clear_all_caches(self):
        """모든 캐시 초기화"""
        self._module_cache.clear()
        self._script_wrapper_cache.clear()
        self._compiled_script_cache.clear()
        logging.debug("🧹 모든 캐시 초기화 완료")
    
    def _get_current_call_stack(self):
        """현재 호출 스택 반환"""
        if not hasattr(self, '_call_stack'):
            self._call_stack = []
        return self._call_stack.copy()
    
    def _add_to_running_stack(self, script_name):
        """실행 중인 스크립트 스택에 추가"""
        if not hasattr(self, '_call_stack'):
            self._call_stack = []
        self._call_stack.append(script_name)
    
    def _remove_from_running_stack(self, script_name):
        """실행 중인 스크립트 스택에서 제거"""
        if hasattr(self, '_call_stack') and script_name in self._call_stack:
            self._call_stack.remove(script_name)

    def _make_wrapped_script(self, script):
        """kwargs를 제외한 순수 스크립트 래퍼 생성"""
        indented_script = '\n'.join(' ' * 8 + line if line.strip() else line for line in script.split('\n'))
        
        return f"""
def execute_script():
    def user_script():
        # kwargs는 실행 시점에 globals에서 가져옴
        kwargs = globals().get('kwargs', {{}})
        
        # 기본 변수들 설정
        code = kwargs.get('code', '')
        name = kwargs.get('name', '')
        qty = kwargs.get('qty', 0)
        price = kwargs.get('price', 0)
        
        # 전역 변수로 설정하여 사용자 스크립트에서 접근 가능하게
        globals()['code'] = code
        globals()['name'] = name
        globals()['qty'] = qty
        globals()['price'] = price
        
        # 사용자 정의 변수들 추출
        for key, value in kwargs.items():
            if key not in ['code', 'name', 'qty', 'price']:
                globals()[key] = value
        
        # 사용자 스크립트 실행
{indented_script}
        
        return None
    
    try:
        user_script()
        return globals().get('_script_result')
    except SystemExit as e:
        if str(e) == "script_return":
            return globals().get('_script_result')
        else:
            raise
    except ZeroDivisionError:
        echo('ZeroDivisionError 발생 - 기본값으로 처리')
        return False
    except Exception as e:
        echo(f'스크립트 실행 오류: {{e}}')
        import traceback
        tb = traceback.format_exc()
        raise

# 스크립트 실행 (kwargs는 실행 시점에 설정됨)
result = execute_script()
"""
                    
# 예제 실행
if __name__ == '__main__':
    ct = ChartManager('005930', 'mi', 3)

    logging.debug(f'{ct.c()}')

    c1 = ct.ma(5) > ct.ma(20) and ct.c > ct.ma(5)
    c2 = ct.ma(5) < ct.ma(5) and ct.ma(20) < ct.ma(20)

    result = c1 and c2

    logging.debug(result)
