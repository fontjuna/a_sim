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
import math
from contextlib import contextmanager

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
    def __init__(self, code, cycle='mi', tick=3):
        self.chart_data = ChartData()
        self.cycle = cycle
        self.tick = tick
        self.code = code
        
        # 성능 최적화를 위한 캐시
        self._raw_data = None  # 원본 데이터 직접 참조
        self._cache_version = -1
        self._data_length = 0
        
        # ensure 일시 중지 카운터 (중첩 안전)
        self._ensure_suspended = 0
        
    def __enter__(self):
        """with ChartManager(...) as cm: 사용 시 시작에 보장할 작업이 있으면 여기에 추가"""
        return self
    
    def __exit__(self, exc_type, exc, tb):
        """with 블록 종료 시 상태 복구 (ensure 중지 카운터 클린업)"""
        self._ensure_suspended = 0
        return False  # 예외 전파
    
    @contextmanager
    def suspend_ensure(self):
        """블록 내부에서 _ensure_data_cache()를 일시 중지 (중첩 안전)"""
        self._ensure_suspended += 1
        try:
            yield
        finally:
            self._ensure_suspended -= 1

    def _ensure_data_cache(self):
        """데이터 캐시 확인 및 업데이트 (최적화)"""
        if getattr(self, '_ensure_suspended', 0) > 0: return

        current_version = self.chart_data._data_versions.get(self.code, 0)
        
        # 버전이 같으면 즉시 리턴
        if self._cache_version == current_version and self._raw_data is not None:
            return
        
        # 버전이 다를 때만 데이터 갱신
        if self.cycle == 'mi':
            cycle_key = f'mi{self.tick}'
            # 모든 분봉은 ChartData에서 실시간 업데이트됨 - 직접 가져오기
            self._raw_data = self.chart_data._chart_data.get(self.code, {}).get(cycle_key, [])
        else:
            # 일/주/월봉: ChartData에서 실시간 업데이트됨 - 직접 가져오기
            self._raw_data = self.chart_data._chart_data.get(self.code, {}).get(self.cycle, [])
        
        self._cache_version = current_version
        self._data_length = len(self._raw_data) if self._raw_data else 0

    # 기본값 반환 함수들 (직접 접근)
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

    def snapshot(self, *idx: int) -> dict:
        """요청 인덱스들의 O/H/L/C/V/A 스냅샷 반환 (중복 인덱스는 1회만 계산)"""
        self._ensure_data_cache()
        if not self._raw_data: return {}
        with self.suspend_ensure():
            snap, seen = {}, set()
            for i in idx:
                if i in seen: continue
                seen.add(i)
                if 0 <= i < self._data_length:
                    c = self._raw_data[i]
                    snap[i] = self.get_candle_data(i)
                    # {
                    #     'o': c.get('시가', 0), 'h': c.get('고가', 0), 'l': c.get('저가', 0),
                    #     'c': c.get('현재가', 0), 'v': c.get('거래량', 0), 'a': c.get('거래대금', 0),
                    # }
            return snap   
        
    # 원본 데이터 직접 접근 함수
    def get_raw_data(self):
        """원본 데이터 직접 반환 (최고 성능)"""
        self._ensure_data_cache()
        return self._raw_data
    
    # 캔들 특성 함수들
    def red(self, n: int = 0) -> bool:
        """음봉 여부 반환"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        
        return self._raw_data[n].get('현재가', 0) >= self._raw_data[n].get('시가', 0)
    
    def blue(self, n: int = 0) -> bool:
        """양봉 여부 반환"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        
        return self._raw_data[n].get('현재가', 0) < self._raw_data[n].get('시가', 0)
    
    def doji(self, n: int = 0) -> bool:
        """당일 도지 봉 여부 반환"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        
        return self._raw_data[n].get('현재가', 0) == self._raw_data[n].get('시가', 0)
    
    def marubozu(self, n: int = 0) -> bool:
        """n봉전의 마루보즈 여부"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        with self.suspend_ensure():
            return self.body(n) > 0 and self.up_tail(n) == 0 and self.down_tail(n) == 0
    
    def body(self, n: int = 0) -> float:
        """몸통 길이 반환 (abs(c-o))"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        c = self._raw_data[n].get('현재가', 0)
        return abs(c - o)
    
    def body_top(self, n: int = 0) -> float:
        """몸통 상단값 반환 (max(o,c))"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        c = self._raw_data[n].get('현재가', 0)
        return max(o, c)
    
    def body_bottom(self, n: int = 0) -> float:
        """몸통 하단값 반환 (min(o,c))"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        c = self._raw_data[n].get('현재가', 0)
        return min(o, c)
    
    def body_center(self, n: int = 0) -> float:
        """몸통 중앙값 반환 ((max(o,c)+min(o,c))/2)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        with self.suspend_ensure():
            top = self.body_top(n)
            bottom = self.body_bottom(n)
            if top == 0.0 and bottom == 0.0:
                return 0.0
            return (top + bottom) / 2.0

    def up_tail(self, n: int = 0) -> float:
        """윗꼬리 길이 반환 (h-max(o,c))"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        h = self._raw_data[n].get('고가', 0)
        o = self._raw_data[n].get('시가', 0)
        c = self._raw_data[n].get('현재가', 0)
        return h - max(o, c)
    
    def down_tail(self, n: int = 0) -> float:
        """아랫꼬리 길이 반환 (min(o,c)-l)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        l = self._raw_data[n].get('저가', 0)
        o = self._raw_data[n].get('시가', 0)
        c = self._raw_data[n].get('현재가', 0)
        return min(o, c) - l
    
    def length(self, n: int = 0) -> float:
        """캔들 전체 길이 반환 (h-l)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        h = self._raw_data[n].get('고가', 0)
        l = self._raw_data[n].get('저가', 0)
        return h - l
    
    def body_pct(self, n: int = 0) -> float:
        """몸통 길이(시가 대비 %)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        if o == 0:
            return 0.0
        with self.suspend_ensure():
            b = self.body(n)
        return (b / o) * 100.0 if o != 0 else 0.0
    
    def up_tail_pct(self, n: int = 0) -> float:
        """윗꼬리 길이(시가 대비 %)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        if o == 0:
            return 0.0
        with self.suspend_ensure():
            up = self.up_tail(n)
        return (up / o) * 100.0 if o != 0 else 0.0
    
    def down_tail_pct(self, n: int = 0) -> float:
        """아랫꼬리 길이(시가 대비 %)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        if o == 0:
            return 0.0
        with self.suspend_ensure():
            dn = self.down_tail(n)
        return (dn / o) * 100.0 if o != 0 else 0.0
    
    def length_pct(self, n: int = 0) -> float:
        """캔들 전체 길이(시가 대비 %)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return 0.0
        o = self._raw_data[n].get('시가', 0)
        if o == 0:
            return 0.0
        with self.suspend_ensure():
            L = self.length(n)
        return (L / o) * 100.0 if o != 0 else 0.0

    def long_body(self, k: float = 2.0, m: int = 10, n: int = 0) -> bool:
        """n봉전의 몸통 길이가 직전 m개 몸통 평균의 k배 이상인지"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length or m <= 0:
            return False
        start = n + 1
        end = min(n + 1 + m, self._data_length)
        if start >= end:
            return False
        total = 0.0
        cnt = 0
        for i in range(start, end):
            total += self.body(i)
            cnt += 1
        if cnt == 0:
            return False
        avg = total / cnt
        if avg <= 0:
            return False
        return self.body(n) >= avg * k
    
    def short_body(self, k: float = 0.5, m: int = 10, n: int = 0) -> bool:
        """n봉전의 몸통 길이가 직전 m개 몸통 평균의 k배 이하인지"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length or m <= 0:
            return False
        start = n + 1
        end = min(n + 1 + m, self._data_length)
        if start >= end:
            return False
        total = 0.0
        cnt = 0
        for i in range(start, end):
            total += self.body(i)
            cnt += 1
        if cnt == 0:
            return False
        avg = total / cnt
        if avg <= 0:
            return False
        return self.body(n) <= avg * k

    def price_position(self, price: int = 0, n: int = 0) -> tuple:
        """
        시가(o) 기준 라벨과 시가대비 OHLC/price 퍼센트를 반환
        (n=0 and price=0 일 때 라벨이 'bottom'이면 음봉, 'top'이면 양봉 또는 price_pct 부호로 판단)

        반환:
          - (label: str, pct: dict)
          - pct keys:
            - 'price_pct': (price - o) / o × 100  (현재 측정가격의 시가대비 %)
            - 'h_pct': (h - o) / o × 100
            - 'l_pct': (l - o) / o × 100
            - 'c_pct': (c - o) / o × 100
            - 'body_pct': (price - bottom) / (top - bottom) × 100  (몸통 내 위치 %)

        라벨 규칙:
          - 4P 도지(o==h==l==c): price>o→'over high', price<o→'under low', 그 외 'doji_4p'
          - 일반:
            - price<l → 'under low', price==l → 'low'
            - price<bottom → 'under bottom', price==bottom → 'bottom' (o==c이면 'doji')
            - o!=c and bottom<price<top → 몸통 내 위치에 따라 구간 라벨(under 25%, 33.4%, middle, 50%, 66.7%, 75%, under top)
            - price==top → 'top'
            - price< h → 'under high', price==h → 'high', price>h → 'over high'
        """
        self._ensure_data_cache()
        if not self._raw_data or n < 0 or n >= self._data_length: 
            return ('n/a', { 'price_pct': 0.0, 'h_pct': 0.0, 'l_pct': 0.0, 'c_pct': 0.0, 'body_pct': 0.0 })
        
        with self.suspend_ensure():
            o, h, l, c = self._raw_data[n].get('시가', 0), self._raw_data[n].get('고가', 0), self._raw_data[n].get('저가', 0), self._raw_data[n].get('현재가', 0)
            if price == 0: price = self._raw_data[0].get('현재가', 0)
            # 현재가 기준 시가대비 % (라벨 외 보조정보)
            price_pct = (price - o) / o * 100.0

            # 4-프라이스 도지: 범위 0, 위치만 상하로 구분
            if o == c == h == l:
                return ('over high' if price > o else 'under low' if price < o else 'doji_4p', {'price_pct': price_pct, 'h_pct': 0, 'l_pct': 0, 'c_pct': 0, 'body_pct': 0 })

            bottom = min(o, c)
            top = max(o, c)

            # 시가 대비 OHLC 퍼센트 (단순 비율)
            h_pct = (h - o) / o * 100.0
            l_pct = (l - o) / o * 100.0
            c_pct = (c - o) / o * 100.0
            body_pct = 0.0

            # 라벨 결정: 저가/바닥/몸통/상단/고가 순서로 판정
            if price < l: label = 'under low'
            elif price == l: label = 'low'
            elif price < bottom: label = 'under bottom'
            elif price == bottom: label = 'bottom' if o != c else 'doji'
            elif o != c and price < top:  # 몸통 내부 상단 영역
                body_pct = (price - bottom) / (top - bottom) * 100.0
                if body_pct < 25: label = 'under 25%'
                elif body_pct < 33.4: label = 'under 33.4%'
                elif body_pct == 50: label = 'middle'
                elif body_pct < 50: label = 'under 50%'
                elif body_pct < 66.7: label = 'under 66.7%'
                elif body_pct < 75: label = 'under 75%'
                else: label = 'under top'
            elif price == top: label = 'top'
            elif price < h: label = 'under high'
            elif price == h: label = 'high'
            else: label = 'over high'

            hlc_pct = {'price_pct': price_pct, 'h_pct': h_pct, 'l_pct': l_pct, 'c_pct': c_pct, 'body_pct': body_pct }

            return (label, hlc_pct)

    def in_up_tail(self, price: int = 0, n: int = 0) -> bool:
        """위꼬리 안에 있는지"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        return self.h(n) > price > self.body_top(n)

    def in_down_tail(self, price: int = 0, n: int = 0) -> bool:
        """아래꼬리 안에 있는지"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        return self.l(n) < price < self.body_bottom(n)

    def in_body(self, price: int = 0, n: int = 0) -> bool:
        """몸통 안에 있는지"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        return self.body_bottom(n) < price < self.body_top(n)

    # 캔들 패턴 함수들
    def get_candle_data(self, n: int = 0) -> dict:
        """
        기본 캔들 데이터 추출 함수
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            
        Returns:
            dict: {
                'o': 시가, 'h': 고가, 'l': 저가, 'c': 종가,
                'body': 몸통크기, 'up_tail': 위꼬리, 'down_tail': 아래꼬리,
                'length': 전체캔들크기, 'is_valid': 유효성여부,
                'body_pct': 몸통크기(시가대비%), 'up_tail_pct': 위꼬리(시가대비%),
                'down_tail_pct': 아래꼬리(시가대비%), 'length_pct': 전체캔들크기(시가대비%),
                'red': 상승캔들, 'blue': 하락캔들, 'doji': 도지캔들,
                'body_top': 몸통상단, 'body_bottom': 몸통하단, 'body_center': 몸통중앙
            }
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return {'is_valid': False}
        
        candle = self._raw_data[n]
        o = candle.get('시가', 0)
        h = candle.get('고가', 0)
        l = candle.get('저가', 0)
        c = candle.get('현재가', 0)
        
        # 기본 유효성 검사
        if h <= l or o <= 0 or c <= 0: return {'is_valid': False}
        
        # 캔들 구성 요소 계산
        body = abs(c - o)
        top = max(o, c)
        bottom = min(o, c)
        center = (top + bottom) / 2
        up_tail = h - top
        down_tail = bottom - l
        length = h - l
        
        # 시가 대비 퍼센트 계산 (0으로 나누기 방지)
        if o > 0:
            body_pct = (body / o) * 100
            up_tail_pct = (up_tail / o) * 100
            down_tail_pct = (down_tail / o) * 100
            length_pct = (length / o) * 100
        else:
            body_pct = up_tail_pct = down_tail_pct = length_pct = 0
        
        return {
            'is_valid': True,
            'o': o, 'h': h, 'l': l, 'c': c,
            'red': c >= o, 'blue': c < o, 'doji': c == o,
            'length': length, 'body': body, 'up_tail': up_tail, 'down_tail': down_tail,
            'length_pct': length_pct, 'body_pct': body_pct, 'up_tail_pct': up_tail_pct, 'down_tail_pct': down_tail_pct,            
            'top': top, 'bottom': bottom, 'center': center
        }
    
    def gap_up(self, n: int = 0) -> bool:
        """상승 갭 확인: n봉전 시가 > (n+1)봉전 몸통 상단"""
        self._ensure_data_cache()
        with self.suspend_ensure():
            return self.o(n) > self.body_top(n + 1)
    
    def gap_down(self, n: int = 0) -> bool:
        """하락 갭 확인: n봉전 시가 < (n+1)봉전 몸통 하단"""
        self._ensure_data_cache()
        with self.suspend_ensure():
            return self.o(n) < self.body_bottom(n + 1)
    
    def is_doji(self, threshold: float = 0.1, n: int = 0) -> bool:
        """도지 캔들 확인 (몸통/전체길이 비율이 threshold 이하)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return False
        with self.suspend_ensure():
            total_len = self.length(n)
            if total_len <= 0: return False
            return (self.body(n) / total_len) <= threshold

    def is_shooting_star(self, length: float = 2.0, up: float = 2.0, down: float = None, n: int = 0) -> bool:
        """
        유성형 캔들 판단
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            length: 위꼬리가 현재가 대비 몇 % 이상
            up: 위꼬리가 몸통의 몇 배 이상
            down: 아래꼬리가 위꼬리의 몇 배 이하
        """
        # 스냅샷 없이 헬퍼로 계산 (성능/일관성 균형)
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        with self.suspend_ensure():
            b = self.body(n)
            up_tail_pct = self.up_tail_pct(n)
            
            # 조건 1: 위꼬리가 몸통의 up배 이상
            if b > 0 and (self.up_tail(n) / b) < up: return False
            
            # 조건 2: 위꼬리가 현재가 대비 length% 이상
            if up_tail_pct < length: return False
            
            # 조건 3: 아래꼬리가 위꼬리의 down배 이하 (down이 None이면 검사하지 않음)
            if down is not None and b > 0 and (self.down_tail(n) / self.up_tail(n)) > down: return False
        
        return True

    def is_hanging_man(self, length: float = 2.0, down: float = 2.0, up: float = None, n: int = 0) -> bool:
        """
        교수형(행잉맨) 캔들 패턴 판단
        
        Args:
            n: 검사할 봉 인덱스 (0=현재봉)
            down: 아래꼬리가 몸통의 몇 배 이상
            length: 아래꼬리가 현재가 대비 몇 % 이상
            up: 위꼬리가 아랫꼬리의 몇 배 이하
        
        Returns:
            bool: 교수형 캔들이면 True
            
        사용예:
            # 상승추세에서 교수형 확인
            if cm.c() > cm.ma(20) and cm.is_hanging_man():
                echo("상승추세 중 교수형!")
        """
        # 스냅샷 없이 헬퍼로 계산
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return False
        with self.suspend_ensure():
            b = self.body(n)
            
            # 조건 1: 아래꼬리가 몸통의 down배 이상
            if b > 0 and (self.down_tail(n) / b) < down:
                return False
            elif b == 0 and self.down_tail(n) == 0:
                return False
            
            # 조건 2: 아래꼬리가 현재가 대비 length% 이상
            if self.down_tail_pct(n) < length:
                return False
            
            # 조건 3: 위꼬리가 아랫꼬리의 up배 이하 (up이 None이면 검사하지 않음)
            if up is not None and b > 0 and (self.up_tail(n) / self.down_tail(n)) > up:
                return False
        
        return True

    def is_hammer(self, n: int = 0) -> bool:
        """망치형 캔들 확인 (아래 꼬리가 긴 캔들)"""
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return False
        with self.suspend_ensure():
            total_len = self.length(n)
            b = self.body(n)
            if total_len <= 0 or b <= 0:
                return False
            down = self.down_tail(n)
            # 아래 꼬리가 몸통의 2배 이상이고, 전체 길이의 1/3 이상
            return (down >= 2 * b) and ((down / total_len) >= (1/3))
    
    def is_engulfing(self, min_body_pct: float = 1.0, bullish: bool = True, n: int = 0) -> tuple:
        """장악형 패턴 확인 (이전 캔들을 완전히 덮는 형태)
        Returns: (match: bool, ratio_pct: float)
        """
        self._ensure_data_cache()
        if not self._raw_data or n + 1 >= self._data_length: return (False, 0.0)
        with self.suspend_ensure():
            if self.body_pct(n) < min_body_pct: return (False, 0.0)
            # 상승 장악: 현재 양, 이전 음 / 하락 장악: 현재 음, 이전 양
            if bullish and (self.red(n + 1) or self.blue(n)): return (False, 0.0)
            if (not bullish) and (self.blue(n + 1) or self.red(n)): return (False, 0.0)
            return self.body_top(n) > self.body_top(n + 1) and self.body_bottom(n) < self.body_bottom(n + 1)
    
    def is_harami(self, min_body_pct: float = 1.0, bullish: bool = True, n: int = 0) -> tuple:
        """잉태형 패턴 확인 (이전 캔들에 포함되는 형태)
        Returns: (match: bool, ratio_pct: float)
        """
        self._ensure_data_cache()
        if not self._raw_data or n + 1 >= self._data_length: return (False, 0.0)
        with self.suspend_ensure():
            if self.body_pct(n) < min_body_pct: return (False, 0.0)
            if bullish and (self.red(n + 1) or self.blue(n)): return (False, 0.0)
            if (not bullish) and (self.blue(n + 1) or self.red(n)): return (False, 0.0)
            return self.body_top(n) < self.body_top(n + 1) and self.body_bottom(n) > self.body_bottom(n + 1)
    
    #  지표 함수들                
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
            return self._raw_data[n].get('체결시간', '')[:8]

    def ma(self, mp: int = 20, n: int = 0) -> float:
        """이동평균 - 고속 버전"""
        self._ensure_data_cache()
        if not self._raw_data or n + mp > self._data_length:
            return 0.0
        
        total = 0.0
        
        for i in range(n, n + mp):
            total += self._raw_data[i].get('현재가', 0)
        
        return total / mp
    
    def get_ma(self, mp: int = 20, m: int = 1, n: int = 0) -> list:
        """이동평균 리스트 반환 (n봉전부터 m개)
        mp: 기간
        m: 반환 개수
        n: 시작 오프셋(0=현재봉부터)
        """
        self._ensure_data_cache()
        if not self._raw_data or mp <= 0:
            return []
        
        data_len = self._data_length
        start_idx = 0 if n < 0 else n
        
        ma_list = []
        for i in range(start_idx, start_idx + m):
            if i + mp > data_len:
                break
            total = 0.0
            for j in range(i, i + mp):
                total += self._raw_data[j].get('현재가', 0)
            ma_list.append(total / mp)
        
        return ma_list

    # 계산 함수들
    def avg(self, value_func, m: int, n: int = 0) -> float:
        """단순이동평균 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        total = 0.0
        for i in range(n, n + m):
            total += value_func(i)
        
        return total / m if m > 0 else 0.0
    
    def highest(self, value_func, m: int, n: int = 0) -> float:
        """최고값 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        max_val = float('-inf')
        for i in range(n, n + m):
            val = value_func(i)
            if val > max_val:
                max_val = val
        
        return max_val if max_val != float('-inf') else 0.0
    
    def lowest(self, value_func, m: int, n: int = 0) -> float:
        """최저값 - 고속 버전"""
        if not callable(value_func):
            return float(value_func)
        
        min_val = float('inf')
        for i in range(n, n + m):
            val = value_func(i)
            if val < min_val:
                min_val = val
        
        return min_val if min_val != float('inf') else 0.0
    
    def sum(self, value_func, m: int, n: int = 0) -> float:
        """합계 - 고속 버전"""
        if not callable(value_func):
            return float(value_func) * m
        
        total = 0.0
        for i in range(n, n + m):
            total += value_func(i)
        
        return total
    
    def eavg(self, value_func, m: int, n: int = 0) -> float:
        """지수이동평균"""
        if not callable(value_func):
            return float(value_func)
        
        if m <= 0:
            return 0.0
        
        alpha = 2.0 / (m + 1)
        result = value_func(n + m - 1)
        
        for i in range(n + m - 2, n - 1, -1):
            result = alpha * value_func(i) + (1 - alpha) * result
        
        return result
    
    def wavg(self, value_func, m: int, n: int = 0) -> float:
        """가중이동평균 계산"""
        if not callable(value_func):
            return float(value_func)
        
        total_value = 0.0
        total_weight = 0.0
        
        for i in range(n, n + m):
            weight = m - (i - n)  # 최신 데이터일수록 가중치 높음
            value = value_func(i)
            total_value += value * weight
            total_weight += weight
        
        return total_value / total_weight if total_weight > 0 else 0.0
    
    def stdev(self, value_func, m: int, n: int = 0) -> float:
        """표준편차"""
        if not callable(value_func) or m <= 1:
            return 0.0
        
        # 평균 계산
        total = 0.0
        for i in range(n, n + m):
            total += value_func(i)
        mean = total / m
        
        # 분산 계산
        variance = 0.0
        for i in range(n, n + m):
            diff = value_func(i) - mean
            variance += diff * diff
        variance /= m
        
        return variance ** 0.5
    
    # 신호 함수들
    def trend_up(self, mp: int = 20, n: int = 0) -> bool:
        """n봉전의 종가가 mp이평 위에 있는지"""
        return self.c(n) > self.ma(mp, n)
    
    def trend_down(self, mp: int = 20, n: int = 0) -> bool:
        """n봉전의 종가가 mp이평 아래에 있는지"""
        return self.c(n) < self.ma(mp, n)
    
    def reverse_up(self, mp: int = 5, n: int = 0) -> bool:
        """상승 반전"""
        self._ensure_data_cache()
        if not self._raw_data or n + 2 >= self._data_length: return False
        with self.suspend_ensure():
            ma2, ma1, ma0 = self.ma(mp, n+2), self.ma(mp, n+1), self.ma(mp, n)
            return ma2 >= ma1 and ma1 < ma0
    
    def reverse_down(self, mp: int = 5, n: int = 0) -> bool:
        """하락 반전"""
        self._ensure_data_cache()
        if not self._raw_data or n + 2 >= self._data_length: return False
        with self.suspend_ensure():
            ma2, ma1, ma0 = self.ma(mp, n+2), self.ma(mp, n+1), self.ma(mp, n)
            return ma2 <= ma1 and ma1 > ma0
        
    def cross_up(self, a_func, b_func) -> bool:
        """상향돌파
        사용법:
        - a_func, b_func는 인덱스를 인자로 받아 값을 반환하는 호출가능 객체여야 함
        예시:
          # 5이평이 10이평 상향돌파 여부 (현재봉 기준)
          cm.cross_up(lambda i: cm.ma(5, i), lambda i: cm.ma(10, i))
          
          # 종가가 특정 값 10000을 상향돌파
          cm.cross_up(cm.c, lambda i: 10000)
        조건:
          a_prev<=b_prev 이고 a_curr>b_curr 이면 True
        """
        if not (callable(a_func) and callable(b_func)): return False
        self._ensure_data_cache()
        with self.suspend_ensure():
            a_prev, a_curr = a_func(1), a_func(0)
            b_prev, b_curr = b_func(1), b_func(0)
            return a_prev <= b_prev and a_curr > b_curr
    
    def cross_down(self, a_func, b_func) -> bool:
        """하향돌파
        사용법/예시:
          cm.cross_down(lambda i: cm.ma(5, i), lambda i: cm.ma(10, i))
          cm.cross_down(cm.c, lambda i: 10000)
        조건:
          a_prev>=b_prev 이고 a_curr<b_curr 이면 True
        """
        if not (callable(a_func) and callable(b_func)): return False
        self._ensure_data_cache()
        with self.suspend_ensure():
            a_prev, a_curr = a_func(1), a_func(0)
            b_prev, b_curr = b_func(1), b_func(0)
            return a_prev >= b_prev and a_curr < b_curr

    def bars_since(self, condition_func) -> int:
        """조건이 만족된 이후 지나간 봉 개수
        사용법:
          # 최근 "양봉" 이후 경과봉
          cm.bars_since(lambda i: cm.c(i) > cm.o(i))
        반환:
          처음 True가 발생한 인덱스를 반환(현재=0). 없으면 데이터 길이.
        """
        self._ensure_data_cache()
        if not self._raw_data: return 0
        with self.suspend_ensure():
            for i in range(self._data_length):
                if condition_func(i):
                    return i
            return self._data_length

    def highest_since(self, nth: int, condition_func, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최고값
        사용법:
          # 최근(또는 n번째) 양봉 이후 최고가
          cm.highest_since(1, lambda i: cm.c(i) > cm.o(i), cm.h)
        반환:
          조건 성립 지점부터 현재까지 data_func의 최고값
        """
        self._ensure_data_cache()
        if not self._raw_data:
            return 0.0
        
        condition_met = 0
        highest_val = float('-inf')
        with self.suspend_ensure():
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
        """조건이 nth번째 만족된 이후 data_func의 최저값
        사용법:
          # 최근(또는 n번째) 양봉 이후 최저가
          cm.lowest_since(1, lambda i: cm.c(i) > cm.o(i), cm.l)
        반환:
          조건 성립 지점부터 현재까지 data_func의 최저값
        """
        self._ensure_data_cache()
        if not self._raw_data:
            return 0.0
        
        condition_met = 0
        lowest_val = float('inf')
        with self.suspend_ensure():
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
        """조건이 nth번째 만족된 시점의 data_func 값
        사용법:
          # 최근 양봉이었던 시점의 종가
          cm.value_when(1, lambda i: cm.c(i) > cm.o(i), cm.c)
        반환:
          조건이 nth번째로 True였던 시점의 data_func 결과값
        """
        self._ensure_data_cache()
        if not self._raw_data: return 0.0
        with self.suspend_ensure():
            condition_met = 0
            
            for i in range(self._data_length):
                if condition_func(i):
                    condition_met += 1
                    if condition_met == nth:
                        return data_func(i)
        
        return 0.0
    
    def indicator(self, func, *args):
        """지표 계산 결과를 함수처럼 사용 가능한 객체 반환"""
        # 내부 함수 생성 (클로저)
        def callable_indicator(offset=0):
            self._ensure_data_cache()
            with self.suspend_ensure():
                return func(*args, offset)
        
        # 함수 반환
        return callable_indicator
    
    # 보조지표 계산 함수들
    def get_obv_array(self, m: int = 10) -> list:
        """OBV 배열을 표준 방식으로 계산하여 반환"""
        self._ensure_data_cache()
        if not self._raw_data or self._data_length < 2:
            return [0.0] * m
        
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
        
        # m만큼 반환 (최신 데이터부터)
        return obv_values[-m:] if len(obv_values) >= m else obv_values
        
    def rsi(self, period: int = 14, n: int = 0) -> float:
        """상대강도지수(RSI) 계산"""
        self._ensure_data_cache()
        if not self._raw_data or n + period + 1 > self._data_length:
            return 50.0
        
        gains = 0.0
        losses = 0.0
        
        for i in range(n + 1, n + period + 1):
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
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9, n: int = 0) -> tuple:
        """MACD(Moving Average Convergence Divergence) 계산
        Returns: (MACD 라인, 시그널 라인, 히스토그램)
        """
        self._ensure_data_cache()
        with self.suspend_ensure():
            fast_ema = self.eavg(self.c, fast, n)
            slow_ema = self.eavg(self.c, slow, n)
            macd_line = fast_ema - slow_ema
            
            # 간단한 시그널 라인 (실제로는 MACD 값들의 EMA가 필요)
            signal_line = self.eavg(self.c, signal, n)
            histogram = macd_line - signal_line
            
            return (macd_line, signal_line, histogram)
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2, n: int = 0) -> tuple:
        """볼린저 밴드 계산
        Returns: (상단 밴드, 중간 밴드(SMA), 하단 밴드)
        """
        self._ensure_data_cache()
        with self.suspend_ensure():
            middle_band = self.avg(self.c, period, n)
            stdev = self.stdev(self.c, period, n)
            
            upper_band = middle_band + (stdev * std_dev)
            lower_band = middle_band - (stdev * std_dev)
            
            return (upper_band, middle_band, lower_band)
    
    def stochastic(self, k_period: int = 14, d_period: int = 3, n: int = 0) -> tuple:
        """스토캐스틱 오실레이터 계산
        Returns: (%K, %D)
        """
        self._ensure_data_cache()
        with self.suspend_ensure():
            hh = self.highest(self.h, k_period, n)
            ll = self.lowest(self.l, k_period, n)
            current_close = self.c(n)
            
            # %K 계산
            percent_k = 0
            if hh != ll:
                percent_k = 100 * ((current_close - ll) / (hh - ll))
            
            # %D 계산 (간단한 이동평균 사용)
            percent_d = self.avg(self.c, d_period, n)
            
            return (percent_k, percent_d)
    
    def atr(self, period: int = 14, n: int = 0) -> float:
        """평균 실제 범위(ATR) 계산"""
        self._ensure_data_cache()
        if not self._raw_data or self._data_length < period + 1 + n:
            return 0.0
        
        tr_values = []
        with self.suspend_ensure():
            for i in range(n, n + period):
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

    def base_line(self, m: int = 26, n: int = 0) -> float:
        """기준선 계산"""
        self._ensure_data_cache()
        if not self._raw_data or n + m + 1 > self._data_length:
            return 0.0
        
        return (self.highest(self.h, m, n) + self.lowest(self.l, m, n)) / 2
    
    # 스크립트 함수들
    def up_start(self, n: int = 0) -> bool:
        """상승 시작 확인"""
        self._ensure_data_cache()
        with self.suspend_ensure():
            return self.o(n) > self.c(n+1)
    
    def down_start(self, n: int = 0) -> bool:
        """하락 시작 확인"""
        self._ensure_data_cache()
        with self.suspend_ensure():
            return self.o(n) < self.c(n+1)
    
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
            diff = self._raw_data[i].get('현재가', 0) - self._raw_data[i].get('시가', 0)
            if diff > length:
                length = diff
                pos = i
        if (length / self._raw_data[pos].get('시가', 0)) * 100 < p: return (0, '', 0, 0, 0, 0, 0, 0)
        time, open, high, low, close, volume, amount = self._raw_data[pos].get('체결시간', ''), self._raw_data[pos].get('시가', 0), self._raw_data[pos].get('고가', 0), \
            self._raw_data[pos].get('저가', 0), self._raw_data[pos].get('현재가', 0), self._raw_data[pos].get('거래량', 0), \
            self._raw_data[pos].get('거래대금', 0)

        return (pos, time, open, high, low, close, volume, amount)

    def get_highest_candle(self, m: int = 128, n: int = 0) -> tuple:
        """
        m개 봉 중에서 가장 긴 봉(고가-저가 차이가 가장 큰 봉) 찾기
        
        Args:
            m: 검사할 봉 개수 (기본값: 128)
            n: 시작 봉 인덱스 (기본값: 0=현재봉)
            
        Returns:
            tuple: (인덱스, 봉데이터)
                   찾지 못하면 (0, {}) 반환
        """
        self._ensure_data_cache()
        if not self._raw_data or m <= 0: return (0, {})
        
        # 검사 범위 설정
        start_idx = n
        end_idx = min(start_idx + m, self._data_length)
        
        if start_idx >= end_idx: return (0, {})
        
        candle = {}
        max_range = 0
        max_range_idx = start_idx
        
        # m개 봉 중에서 가장 긴 봉 찾기
        for i in range(start_idx, end_idx):
            candle = self._raw_data[i]
            high = candle.get('고가', 0)
            low = candle.get('저가', 0)
            candle_range = high - low
            
            if candle_range > max_range:
                max_range = candle_range
                max_range_idx = i
        
        # 최고 긴봉 데이터 반환
        if max_range > 0: candle = self._raw_data[max_range_idx]
            
        return (max_range_idx, candle)

    def get_highest_volume(self, m: int = 128, n: int = 0) -> tuple:
        """
        m개 봉 중에서 가장 거래량이 많은 봉 찾기
        
        Args:
            m: 검사할 봉 개수 (기본값: 128)
            n: 시작 봉 인덱스 (기본값: 0=현재봉)
            
        Returns:
            tuple: (인덱스, 봉데이터)
                   찾지 못하면 (0, {}) 반환
        """
        self._ensure_data_cache()
        if not self._raw_data or m <= 0: return (0, {})
        
        # 검사 범위 설정
        candle = {}
        start_idx = n
        end_idx = min(start_idx + m, self._data_length)
        
        if start_idx >= end_idx: return (0, {})
        
        max_volume = 0
        max_volume_idx = start_idx
        
        # m개 봉 중에서 가장 거래량이 많은 봉 찾기
        for i in range(start_idx, end_idx):
            candle = self._raw_data[i]
            volume = candle.get('거래량', 0)
            
            if volume > max_volume:
                max_volume = volume
                max_volume_idx = i
        
        # 최고 거래량 봉 데이터 반환
        if max_volume > 0: candle = self._raw_data[max_volume_idx]
            
        return (max_volume_idx, candle)

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

    def segment_angle_slope(self, m: int, n: int, max_daily_pct: float = 0.30):
        """
        (m+n)봉전 시가 → n봉전 종가 구간의 각도(°)와 기울기(%) 계산
        
        정의
        - X축 정규화: elapsed_minutes/380 (분봉/일봉/주봉/월봉 환산)
        - Y축 정규화: pct_change/max_daily_pct (기본 max_daily_pct=0.30 → 30%)
        - 각도(°): atan2(Y, X) in degrees
        - 기울기(%): (Y/X)×100  → 100%는 1:1 (상승:시간) 기울기
        
        해석 예시
        - 38분에 +3%: X=0.1, Y=0.1 → 각도=45°, 기울기=100%
        - 12분(3분×4봉)에 각도 45°: 상승률 ≈ 12/380×30% ≈ 0.95%
        - 80°의 기울기 ≈ tan(80°)×100 ≈ 567%
        
        참조 표 (기울기를 정수 비율로 본 각도)
        (상승률 예시: X=경과시간/380=0.1 기준, 상승률≈ 기울기비×X×30% = 비율×3%)
        - 0:1 → 0.00° (상승률≈ 0.0%)
        - 1:10 → 5.71° (상승률≈ 0.3%)
        - 1:8 → 7.13° (상승률≈ 0.4%)
        - 1:6 → 9.46° (상승률≈ 0.5%)
        - 1:5 → 11.31° (상승률≈ 0.6%)
        - 1:4 → 14.04° (상승률≈ 0.8%)
        - 1:3 → 18.43° (상승률≈ 1.0%)
        - 1:2 → 26.57° (상승률≈ 1.5%)
        - 2:3 → 33.69° (상승률≈ 2.0%)
        - 1:1 → 45.00° (상승률≈ 3.0%)
        - 3:2 → 56.31° (상승률≈ 4.5%)
        - 2:1 → 63.43° (상승률≈ 6.0%)
        - 3:1 → 71.57° (상승률≈ 9.0%)
        - 4:1 → 75.96° (상승률≈ 12.0%)
        - 5:1 → 78.69° (상승률≈ 15.0%)
        - 6:1 → 80.54° (상승률≈ 18.0%)
        - 8:1 → 82.87° (상승률≈ 24.0%)
        - 10:1 → 84.29° (상승률≈ 30.0%)
        
        참조 표 (기울기-각도-상승률, 예: 경과시간=38분 → X=0.1, max_daily_pct=30%)
        - 관계식: rise_pct ≈ (slope_percent/100) × X × 30%
        - slope 50%  → 각도≈26.6° → 상승률≈1.5%
        - slope 100% → 각도≈45.0° → 상승률≈3.0%
        - slope 150% → 각도≈56.3° → 상승률≈4.5%
        - slope 200% → 각도≈63.4° → 상승률≈6.0%
        - slope 300% → 각도≈71.6° → 상승률≈9.0%
        
        Returns: (angle_deg, slope_percent, pct_change, elapsed_minutes)
        """
        # 바 하나의 분 단위 환산
        if self.cycle == 'mi':
            minutes_per_bar = int(self.tick)
        elif self.cycle == 'dy':
            minutes_per_bar = 380
        elif self.cycle == 'wk':
            minutes_per_bar = 5 * 380
        elif self.cycle == 'mo':
            minutes_per_bar = 20 * 380
        else:
            minutes_per_bar = 1
        self._ensure_data_cache()
        with self.suspend_ensure():
            start_idx = n + m
            if start_idx >= self._data_length:
                return 0.0, 0.0, 0.0, 0

            start_open = self.o(start_idx)
            end_close = self.c(n)
            pct = (end_close - start_open) / start_open if start_open > 0 else 0

            elapsed_minutes = max(1, m * minutes_per_bar)
            x = elapsed_minutes / 380.0
            y = pct / max_daily_pct

            angle_deg = math.degrees(math.atan2(y, x))
            slope_percent = (y / x) * 100.0 if x > 0 else 0.0

            return angle_deg, slope_percent, pct, elapsed_minutes

    def get_extremes(self, m: int = 128, n: int = 1) -> dict:
        """
        현재봉 기준 m개 봉에서 각종 극값들을 구함
        
        Args:
            m: 검사할 봉 개수
            n: 시작 봉 인덱스 0=현재봉
        
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
        if not self._raw_data or m <= 0:
            return { 'hh': 0, 'hc': 0, 'lc': 0, 'll': 0, 'hv': 0, 'lv': 0, 'ha': 0, 'la': 0, 'close': 0, 'bars': 0 }
        
        # 시작 인덱스 설정
        today = datetime.now().strftime('%Y%m%d')
        start_idx = n
        end_idx = start_idx + m
        
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
        bars = n + 1 # 현재봉 포함
        
        # m개 봉 순회하면서 극값 찾기
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

    def top_volume_avg(self, k: int = 10, m: int = 128, n: int = 1) -> float:
        """
        현재봉 기준 n봉 이전부터 m개 봉 중 거래량 상위 k개의 평균값
        
        Args:
            n: 현재봉에서 n봉 이전부터 시작 (기본값: 1)
            m: 검사할 봉 개수 (기본값: 128) 
            k: 상위 몇 개를 선택할지 (기본값: 10)
        
        Returns:
            float: 상위 k개 거래량의 평균값
        """
        self._ensure_data_cache()
        if not self._raw_data or m <= 0 or k <= 0 or n < 0:
            return 0.0
        
        # 시작 인덱스와 끝 인덱스 설정
        start_idx = n
        end_idx = start_idx + m
        
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
        
        # k가 실제 데이터 개수보다 크면 전체 데이터 사용
        actual_k = min(k, len(volumes))
        
        # 거래량 내림차순 정렬 후 상위 k개 선택
        volumes.sort(reverse=True)
        top_volumes = volumes[:actual_k]
        
        # 평균 계산
        return sum(top_volumes) / len(top_volumes)

    def top_amount_avg(self, k: int = 10, m: int = 128, n: int = 1) -> float:
        """
        현재봉 기준 n봉 이전부터 m개 봉 중 거래대금 상위 k개의 평균값
        
        Args:
            n: 현재봉에서 n봉 이전부터 시작 (기본값: 1)
            m: 검사할 봉 개수 (기본값: 130)
            k: 상위 몇 개를 선택할지 (기본값: 10)
        
        Returns:
            float: 상위 k개 거래대금의 평균값
        """
        self._ensure_data_cache()
        if not self._raw_data or m <= 0 or k <= 0 or n < 0:
            return 0.0
        
        # 시작 인덱스와 끝 인덱스 설정
        start_idx = n
        end_idx = start_idx + m
        
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
        
        # k가 실제 데이터 개수보다 크면 전체 데이터 사용
        actual_k = min(k, len(amounts))
        
        # 거래대금 내림차순 정렬 후 상위 k개 선택
        amounts.sort(reverse=True)
        top_amounts = amounts[:actual_k]
        
        # 평균 계산
        return sum(top_amounts) / len(top_amounts)

    def get_volume_stats(self, k: int = 10, m: int = 128, n: int = 0) -> dict:
        """
        n봉 기준 m개 봉의 거래량 통계
        
        Args:
            k: 극단값 제외 개수 (기본값: 0)
            m: 검사할 봉 개수 (기본값: 128)
            n: 시작 봉 인덱스 (기본값: 0=현재봉)
            
        Returns:
            dict: {
                'max': 최고 거래량,
                'avg': 평균 거래량,
                'min': 최저 거래량,
                'total': 총 거래량,
                'k_max': 최대 k개를 제외한 평균 (k > 0일 때),
                'k_min': 최소 k개를 제외한 평균 (k > 0일 때),
                'k_avg': 최대 k개와 최소 k개를 모두 제외한 평균 (k > 0일 때)
            }
        """
        self._ensure_data_cache()
        if not self._raw_data or m <= 0 or n < 0:
            return {'max': 0, 'avg': 0.0, 'min': 0, 'total': 0}
        
        # 시작 인덱스와 끝 인덱스 설정
        start_idx = n
        end_idx = start_idx + m
        
        # 데이터 길이 체크
        if start_idx >= self._data_length:
            return {'max': 0, 'avg': 0.0, 'min': 0, 'total': 0}
        
        if end_idx > self._data_length:
            end_idx = self._data_length
        
        if start_idx >= end_idx:
            return {'max': 0, 'avg': 0.0, 'min': 0, 'total': 0}
        
        # 거래량 수집 (리스트로 저장하여 정렬 가능하게)
        volumes = []
        total_volume = 0
        
        for i in range(start_idx, end_idx):
            volume = self._raw_data[i].get('거래량', 0)
            if volume > 0:
                volumes.append(volume)
                total_volume += volume
        
        if not volumes:
            return {'max': 0, 'avg': 0.0, 'min': 0, 'total': 0}
        
        # 기본 통계
        max_volume = max(volumes)
        min_volume = min(volumes)
        avg_volume = total_volume / len(volumes)
        
        result = {
            'max': max_volume,
            'avg': avg_volume,
            'min': min_volume,
            'total': total_volume
        }
        
        # k가 0보다 크면 극단값 제외 평균 계산
        if k > 0 and len(volumes) > k * 2:
            # 정렬된 리스트 생성
            sorted_volumes = sorted(volumes)
            
            # 최대 k개를 제외한 평균
            if len(sorted_volumes) > k:
                volumes_without_max = sorted_volumes[:-k]
                result['k_max'] = sum(volumes_without_max) / len(volumes_without_max)
            else:
                result['k_max'] = 0.0
            
            # 최소 k개를 제외한 평균
            if len(sorted_volumes) > k:
                volumes_without_min = sorted_volumes[k:]
                result['k_min'] = sum(volumes_without_min) / len(volumes_without_min)
            else:
                result['k_min'] = 0.0
            
            # 최대 k개와 최소 k개를 모두 제외한 평균
            if len(sorted_volumes) > k * 2:
                volumes_without_extremes = sorted_volumes[k:-k]
                result['k_avg'] = sum(volumes_without_extremes) / len(volumes_without_extremes)
            else:
                result['k_avg'] = 0.0
        
        return result

    def get_close_tops(self, k: int = 1, w: int = 80, m: int = 128, n: int = 1) -> tuple:
        """
        각 봉이 자신을 포함한 w개 봉 중 최고 종가인지 확인하여 인덱스를 수집 (분봉만 해당)
        
        Args:
            k: 필요한 최고종가 인덱스 개수 (가까운 것부터 찾고 k개 채우면 즉시 종료; None이면 전체)
            w: 비교할 봉 개수 (자신 포함)
            m: 검사 시작 기준 (m이면 m-1+n부터 시작)
            n: 검사 종료 인덱스 (0=현재봉까지, 1=1봉까지, 3=3봉까지...)
        
        Returns:
            tuple: (최고종가_인덱스_리스트, 당일_봉_개수)
        """
        if self.cycle != 'mi': return ([], 0)

        self._ensure_data_cache()
        if not self._raw_data or n < 0 or m <= 0 or w <= 0:
            return ([], 0)
        
        # 스냅샷: 연산 중 데이터 변동 방지 (일관성 확보)
        data = list(self._raw_data)
        data_length = len(data)
        
        high_close_indices = []
        
        # 당일 봉 개수 계산
        today_bars = 0
        today = datetime.now().strftime('%Y%m%d')
        for i in range(data_length):
            if data[i].get('체결시간', '')[:8] == today:
                today_bars += 1
            else:
                break
        
        # 검사 범위 설정 (최근→과거 순으로 탐색하여 k개 찾으면 조기 종료)
        start_idx = max(0, min(m - 1 + n, data_length - 1))
        end_idx = n
        
        for current_idx in range(end_idx, start_idx + 1):  # 최근(n) → 과거(start_idx)
            if current_idx >= data_length:
                break
            
            # 현재 검사 중인 봉의 종가
            current_close = data[current_idx].get('현재가', 0)
            
            # 비교 범위: current_idx 이후(w-1개)만 비교하여 동률은 제외
            compare_start = current_idx + 1  # 자신 제외
            compare_end = min(current_idx + w, data_length)
            if compare_start >= compare_end:
                continue
            
            max_close = 0
            for j in range(compare_start, compare_end):
                close = data[j].get('현재가', 0)
                if close > max_close:
                    max_close = close
            
            # 이전 최고종가보다 엄격히 더 높을 때만 인덱스 추가
            if current_close > max_close:
                high_close_indices.append(current_idx)
                if len(high_close_indices) >= k:
                    break
        
        return (high_close_indices, today_bars)
    
    def get_daily_top_close(self, n: int = 0) -> tuple:
        """
        당일 최고 종가봉의 인덱스와 당일 봉수 구하기
        
        Args:
            n: 기준 봉 인덱스 (0=현재봉)
            
        Returns:
            tuple: (당일 최고 종가봉 인덱스, 당일 봉수)
                   (-1, 0)이면 찾지 못함
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return (-1, 0)
        
        # 당일 날짜 구하기
        today = datetime.now().strftime('%Y%m%d')
        
        # 당일 봉들 중에서 최고 종가 찾기
        highest_close = 0
        highest_close_index = -1
        daily_bar_count = 0
        
        with self.suspend_ensure():
            for i in range(n, self._data_length):
                candle = self._raw_data[i]
                candle_date = candle.get('체결시간', '')[:8]
                
                # 당일이 아니면 중단
                if candle_date != today:
                    break
                
                daily_bar_count += 1
                close_price = candle.get('현재가', 0)
                if close_price > highest_close:
                    highest_close = close_price
                    highest_close_index = i
        
        return (highest_close_index, daily_bar_count)

    def get_rise_percentage(self, n: int = 0) -> dict:
        """
        현재봉 기준 첫 양봉 분석
        
        Args:
            n: 기준 봉 인덱스 (0=현재봉)
            
        Returns:
            dict: {
                'rise_pct': 상승률(%) - 시작 음봉 종가 대비 이어진 양봉들의 마지막 양봉 종가의 상승률,
                'red_idx': 마지막 양봉의 인덱스,
                'red_cnt': 연속된 양봉의 개수,
                'bottom': 시작 음봉의 종가,
                'top': 마지막 양봉의 종가,
                'red_max': 양봉들 중 몸통이 제일 긴 봉의 시가대비 종가 퍼센트
            }
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return { 'rise_pct': 0.0, 'red_idx': -1, 'red_cnt': 0, 'bottom': 0.0, 'top': 0.0 }
        
        # 현재봉부터 과거로 검색하여 첫 양봉 찾기
        red_idx = -1
        
        with self.suspend_ensure():
            for i in range(n, self._data_length):
                candle = self._raw_data[i]
                if candle['현재가'] >= candle['시가']:  # 양봉
                    red_idx = i
                    break
        
        if red_idx == -1:
            return { 'rise_pct': 0.0, 'red_idx': -1, 'red_cnt': 0, 'bottom': 0.0, 'top': 0.0 }
        
        # 첫 양봉 이후의 첫 음봉 찾기 (양봉 이후 음봉)
        bottom = 0.0
        red_cnt = 0
        red_max = 0
        with self.suspend_ensure():
            for i in range(red_idx, self._data_length):
                candle = self._raw_data[i]
                if candle['현재가'] < candle['시가']:  # 음봉
                    bottom = candle['현재가']
                    break
                red_cnt += 1
                pct = (candle['현재가'] - candle['시가']) / candle['시가'] * 100
                if pct > red_max:
                    red_max = pct
        
            # 첫 양봉의 종가
            top = self._raw_data[red_idx]['현재가']
        
        # 상승률 계산
        rise_pct = 0.0
        if bottom > 0:
            rise_pct = ((top - bottom) / bottom) * 100
        
        return { 'rise_pct': rise_pct, 'red_idx': red_idx, 'red_cnt': red_cnt, 'bottom': bottom, 'top': top, 'red_max': red_max }

    def get_rise_analysis(self, ma: int = 5, n: int = 0) -> dict:
        """
        이평선 기반 상승률 분석

        Args:
            ma: 이평주기 (기본값: 5)
            n: 기준 봉 인덱스 (0=현재봉)
            
        Returns:
            dict: {
                'rise_pct': 상승률(%) - B봉 대비 A봉 종가의 상승률,
                'top_idx': A봉(당일 최고 종가봉) 인덱스,
                'start_idx': B봉(ma이평 이하 첫 종가봉) 인덱스,
                'top_c': A봉 종가,
                'start_c': B봉 종가,
                'in_today': B봉이 당일에 있는지 여부 (False면 전일 종가),
                'max_pct': A봉과 B봉 사이 양봉 중 최대 몸통 길이의 시가대비 종가 퍼센트,
                'red_cnt': A봉과 B봉 사이 양봉의 개수,
                'bar_cnt': A봉과 B봉 사이 봉의 개수
            }
        """
        
        if self.cycle != 'mi':
            return {
                'rise_pct': 0.0, 'top_idx': -1, 'start_idx': -1,
                'top_c': 0.0, 'start_c': 0.0, 'in_today': False,
                'max_pct': 0.0, 'red_cnt': 0, 'bar_cnt': 0    
            }

        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length:
            return {
                'rise_pct': 0.0, 'top_idx': -1, 'start_idx': -1,
                'top_c': 0.0, 'start_c': 0.0, 'in_today': False,
                'max_pct': 0.0, 'red_cnt': 0, 'bar_cnt': 0
            }
        
        today = datetime.now().strftime('%Y%m%d')
        top_idx = -1
        top_c = 0.0
        start_idx = -1
        start_c = 0.0
        in_today = False
        max_pct = 0.0
        red_cnt = 0
        
        with self.suspend_ensure():
            # 1. n봉부터 당일 봉들 중에서 최고 종가(A) 찾기
            for i in range(n, self._data_length):
                candle = self._raw_data[i]
                candle_date = candle.get('체결시간', '')[:8]
                
                if candle_date != today:
                    break
                
                close_price = candle.get('현재가', 0)
                if close_price > top_c:
                    top_c = close_price
                    top_idx = i
            
            if top_idx == -1:
                return {
                    'rise_pct': 0.0, 'top_idx': -1, 'start_idx': -1,
                    'top_c': 0.0, 'start_c': 0.0, 'in_today': False,
                    'max_pct': 0.0, 'red_cnt': 0, 'bar_cnt': 0
                }
            
            # 2. A봉부터 검사하면서 ma이평 이하 종가 봉(B) 찾기 + 최대 몸통 길이 계산
            for i in range(top_idx, self._data_length):
                candle = self._raw_data[i]
                candle_date = candle.get('체결시간', '')[:8]
                
                close_price = candle.get('현재가', 0)
                ma_k = self.ma(ma, i)
                
                # 당일 봉인 경우
                if candle_date == today:
                    # ma이평 이하에 종가가 형성되면 B봉으로 설정
                    if close_price <= ma_k:
                        start_idx = i
                        start_c = close_price
                        in_today = True
                        break
                    
                    # 최대 몸통 길이 계산 (양봉인 경우만)
                    open_price = candle.get('시가', 0)
                    if close_price >= open_price and open_price > 0:
                        red_cnt += 1
                        body_pct = ((close_price - open_price) / open_price) * 100.0
                        if body_pct > max_pct:
                            max_pct = body_pct
                
                # 전일 봉인 경우 (당일에 B봉을 찾지 못했을 때)
                elif candle_date < today and start_idx == -1:
                    start_idx = i
                    start_c = close_price
                    in_today = False
                    break
            
            if start_idx == -1 or start_c <= 0:
                return {
                    'rise_pct': 0.0, 'top_idx': top_idx, 'start_idx': -1,
                    'top_c': top_c, 'start_c': 0.0, 'in_today': False,
                    'max_pct': max_pct, 'red_cnt': red_cnt, 'bar_cnt': 0
                }
        
        rise_pct = ((top_c - start_c) / start_c) * 100.0 if start_c > 0 else 0.0
        
        return {
            'rise_pct': rise_pct,
            'top_idx': top_idx,
            'start_idx': start_idx,
            'top_c': top_c,
            'start_c': start_c,
            'in_today': in_today,
            'max_pct': max_pct, 'red_cnt': red_cnt, 'bar_cnt': start_idx - top_idx - 1
        }
            
    def consecutive_count(self, condition_func, max_check: int = 128, n: int = 0) -> int:
        """
        이전 n봉 기준으로 condition이 몇 번 연속으로 발생했는지 계산
        
        Args:
            condition_func: 조건을 확인할 함수 (인덱스를 받아 bool 반환)
            n: 시작 기준 봉 (0=현재봉부터, 1=1봉전부터...)
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
        current_idx = n
        with self.suspend_ensure():
            # n봉부터 시작해서 조건이 만족되는 동안 계속 확인
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

    def consecutive_true_false(self, condition_func, pattern: str = None, max_check: int = 100, n: int = 0) -> tuple:
        """
        이전 n봉 기준으로 연속 True 개수와 그 이후 연속 False 개수를 반환
        
        Args:
            condition_func: 조건을 확인할 함수
            pattern: 사용하지 않음(호환성 유지용)
            n: 시작 기준 봉 
            max_check: 최대 확인할 봉 개수
        
        Returns:
            tuple: (연속_True_개수, 연속_False_개수)
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func):
            return (0, 0)
        
        true_count = 0
        false_count = 0
        current_idx = n
        checking_true = True  # 처음에는 True 개수를 세는 중
        
        with self.suspend_ensure():
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

    def streak_pattern(self, condition_func, pattern: str, max_check: int = 100, n: int = 0) -> bool:
        """
        특정 패턴이 연속으로 나타나는지 확인
        
        Args:
            condition_func: 조건을 확인할 함수
            pattern: 확인할 패턴 ('T'=True, 'F'=False) 예: "TTTFF", "TFTF"
            n: 시작 기준 봉
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
        
        with self.suspend_ensure():
            for i, expected in enumerate(pattern):
                current_idx = n + i
                
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

    def find_last_condition_break(self, condition_func, max_check: int = 128, n: int = 0) -> int:
        """
        n봉부터 시작해서 조건이 마지막으로 깨진 위치 찾기
        
        Args:
            condition_func: 조건을 확인할 함수
            n: 시작 기준 봉
            max_check: 최대 확인할 봉 개수
        
        Returns:
            int: 조건이 마지막으로 깨진 봉의 인덱스 (-1이면 찾지 못함)
        """
        self._ensure_data_cache()
        if not self._raw_data or not callable(condition_func):
            return -1
        
        last_break_idx = -1
        current_idx = n
        with self.suspend_ensure():
            while current_idx < self._data_length and (current_idx - n) < max_check:
                try:
                    if not condition_func(current_idx):
                        last_break_idx = current_idx
                    current_idx += 1
                except (IndexError, TypeError, ValueError):
                    break
            
        return last_break_idx

    def rise_pct_since_ma_cross_up(self, mp: int = 5, n: int = 0) -> float:
        """가장 최근 MA(mp) 상향 돌파 이후 현재가 상승률(%)
        Args:
            n: 기준 현재 봉 오프셋 (0=현재봉)
            mp: 이동평균 기간 (기본 5)
        Returns:
            float: 돌파 당시 종가 대비 현재가 상승률(%)
        """
        self._ensure_data_cache()
        if not self._raw_data or n >= self._data_length: return 0.0
        def crossed_up(i: int) -> bool:
            if i + 1 >= self._data_length: return False
            with self.suspend_ensure():
                return self.c(i) > self.ma(mp, i) and self.c(i + 1) <= self.ma(mp, i + 1)
        k = self.bars_since(crossed_up)
        if k == self._data_length: return 0.0
        with self.suspend_ensure():
            base = self.c(k)
            curr = self.c(n)
        return ((curr - base) / base * 100.0) if base > 0 else 0.0

    def get_rising_state(self, mas: list, n: int = 0) -> tuple:
        """
        상태 검사 함수 - 반환값: (rise, fall)
        
        Args:
            mas: 이평선 리스트 [기준이평, 이평1, 이평2, ...]
                - mas[0]: 기준 이평선 (SB 판단 기준)
                - mas[1:-1]: 추가 이평선들 (기준 이평선보다 짧은 주기만 사용)
            n: 검사 시작 봉 (기본값: 0, 현재봉부터 검사)
            
        Returns:
            tuple: (rise_dict, fall_dict, below)
                - below: 각 이평선별 이하 종가 인덱스 리스트 딕셔너리
                rise_dict: 상승 시작 봉 정보 딕셔너리 (hc, sb, bars, today_bars, rise_rate, three_rate, max_red, max_blue, tail_count, red_count, blue_count)
                fall_dict: 하락 시작 봉 정보 딕셔너리 (oh, uc, oh_pct, uc_pct)
                below: 각 이평선별 이하 종가 인덱스 리스트 딕셔너리 {5: [7, 12], 10: [5, 7, 15], 20: [5, 7, 12, 15, 18]}
        """
        self._ensure_data_cache()
        
        with self.suspend_ensure():
            if not self._raw_data or len(self._raw_data) < 20: return ({}, {}, {})
            
            # 기준 이평선과 짧은 주기 이평선들 분리
            base_ma = mas[0]  # 기준 이평선
            short_mas = [ma for ma in mas[1:] if ma < base_ma]  # 기준 이평선보다 짧은 주기만
            sb_mas = [base_ma] + short_mas  # SB 판단에 사용할 모든 이평선 (기준이평 + 짧은주기)
            
            # 1. 현재봉 이전 당일 최고 종가봉(HC) 찾기
            hc, today_bars = self._find_highest_close_before(n)
            
            if hc is None: return ({}, {}, {})
            
            # 2. HC부터 과거봉으로 검사하여 기준 이평 아래인 봉(SB) 찾기
            initial_sb = self._find_start_bar(hc, [base_ma])
            
            if initial_sb is None: return ({}, {}, {})
            
            # 3. SB부터 현재봉으로 오면서 모든 이평들 위에 종가가 최초로 형성된 봉의 전봉을 새로운 SB로 설정
            sb = self._refine_start_bar(initial_sb, sb_mas, n)
            
            if sb is None: return ({}, {}, {})
            
            # 4. SB~HC 구간에서 모든 이평선 이하 종가 인덱스 리스트 생성
            below = self._get_ma_below_indices(mas, sb, hc)
            
            # 5. HC부터 SB까지 분석
            max_red, max_blue, tail_count, red_count, blue_count = self._analyze_bars_between(hc, sb, n)
            
            # 6. peak 분석 (SB~HC 구간 전반/후반 상승율 비교)
            peak = self._analyze_peak(hc, sb)
            
            # 7. 현재봉부터 HC전까지 분석
            oh, uc = self._analyze_bars_after_hc(n, hc)
            
            # 8. rise 사전 구성
            rise = self._build_rise_dict(hc, sb, max_red, max_blue, tail_count, peak, today_bars, red_count, blue_count)
            
            # 9. fall 사전 구성
            fall = self._build_fall_dict(oh, uc)
            
            return (rise, fall, below)
    
    def _get_ma_below_indices(self, mas: list, sb: int, hc: int) -> dict:
        """
        SB~HC 구간에서 각 이평선별 이하 종가 인덱스 리스트 반환
        
        Args:
            mas: 이평선 리스트
            sb: 시작 봉 인덱스
            hc: 최고 종가봉 인덱스
            
        Returns:
            dict: 각 이평선별 이하 종가 인덱스 리스트
                예: {5: [7, 12], 10: [5, 7, 15], 20: [5, 7, 12, 15, 18]}
        """
        below = {}
        
        # 각 이평선별로 초기화
        for ma in mas:
            below[ma] = []
        
        # SB 다음부터 HC까지 검사 (SB는 포함하지 않음, HC는 포함)
        for i in range(sb + 1, hc + 1):
            if i >= len(self._raw_data): break
            
            close = self._raw_data[i]['현재가']
            
            # 각 이평선과 비교
            for ma in mas:
                if i >= len(self._raw_data) - ma: continue
                ma_value = self.ma(ma, i)
                if close < ma_value:
                    below[ma].append(i)
        
        return below
    
    def _find_highest_close_before(self, n: int) -> tuple:
        """
        당일 최고 종가봉 인덱스 찾기
        """
        if not self._raw_data or len(self._raw_data) <= n: 
            return None, 0
        
        current_time = self._raw_data[n]['체결시간']
        current_date = current_time[:8]
        hc_idx = None
        hc_close = 0
        today_bars = 0
        
        # 당일 데이터 검색 (n+1부터 시작)
        for i in range(n + 1, len(self._raw_data)):
            if self._raw_data[i]['체결시간'][:8] == current_date:  # 날짜 부분만 비교
                close = self._raw_data[i]['현재가']
                if close >= hc_close:
                    hc_close = close
                    hc_idx = i
                today_bars += 1
            else:
                # 다른 날짜면 종료
                break
        
        # 당일 첫봉인 경우: 현재봉을 HC로 사용
        if hc_idx is None:
            hc_idx = n
            today_bars = 1
        
        return hc_idx, today_bars
    
    def _refine_start_bar(self, initial_sb: int, mas: list, n: int) -> int:
        """SB부터 현재봉으로 오면서 이평들 위에 종가가 최초로 형성된 봉의 전봉을 새로운 SB로 설정"""
        if initial_sb is None or initial_sb <= n + 1:
            return initial_sb
        
        # initial_sb부터 현재봉(n)까지 검사
        for i in range(initial_sb, n + 1, -1):  # 과거에서 현재로
            if i <= 0: break
                
            close = self._raw_data[i]['현재가']
            trend = True
            for ma in mas:
                if close < self.ma(ma, i):
                    trend = False
                    break
            
            if trend:
                return i + 1
            
        # 조건에 맞는 봉이 없으면 기존 SB 반환
        return initial_sb
    
    def _find_start_bar(self, hc: int, mas: list) -> int:
        """HC부터 과거봉으로 검사하여 mas[0]이평 아래인 봉(SB) 찾기 (전일 데이터 포함)"""
        if hc is None or hc >= len(self._raw_data) - mas[0]: 
            return None
        
        # HC부터 과거로 검사하여 처음 만난 기준이평 아래 종가 봉 찾기 (전일 데이터까지 확장)
        for i in range(hc + 1, len(self._raw_data)):
            # 이평선 계산에 필요한 데이터가 충분한지 확인
            if i >= len(self._raw_data) - mas[0]: 
                break
                
            close = self._raw_data[i]['현재가']
            ma_value = self.ma(mas[0], i)
            
            # 기준이평 아래 종가 발견 시 즉시 반환 (당일/전일 구분 없이)
            if close < ma_value: 
                return i
        
        # 조건을 만족하는 봉을 찾지 못한 경우 마지막 사용 가능한 봉 반환
        return len(self._raw_data) - mas[0] - 1
    
    def _analyze_bars_between(self, hc: int, sb: int, n: int = 0) -> tuple:
        """HC부터 SB까지 봉들 분석 (n: 현재봉 인덱스)"""
        max_red = (None, 0.0)
        max_blue = (None, 0.0)
        tail_count = 0  # 최고종가봉(hc)과 전후봉(hc-1, hc+1) 중 윗꼬리 1%이상 개수
        red_count = 0  # 양봉 개수
        blue_count = 0  # 음봉 개수
        
        for i in range(hc, sb):
            if i >= len(self._raw_data):
                break
                
            candle = self._raw_data[i]
            open_price = candle['시가']
            close = candle['현재가']
            high = candle['고가']
            
            # 최대몸통 양봉/음봉 체크
            body_pct = ((close - open_price) / open_price * 100) if open_price > 0 else 0
            
            if body_pct > 0:
                red_count += 1
                if body_pct > max_red[1]:
                    max_red = (i, body_pct)
            elif body_pct < 0:
                blue_count += 1
                if max_blue[0] is None or abs(body_pct) > abs(max_blue[1]):
                    max_blue = (i, body_pct)
            
            # 윗꼬리 1%이상 체크 (최고종가봉과 전후봉만: hc-1, hc, hc+1)
            if hc - 1 <= i <= hc + 1:
                if open_price > 0:
                    tail_rate = ((high - max(open_price, close)) / open_price * 100)
                    if tail_rate >= 1.0:
                        tail_count += 1
        
        return max_red, max_blue, tail_count, red_count, blue_count
    
    def _analyze_peak(self, hc: int, sb: int) -> bool:
        """SB~HC 구간을 전반/후반으로 나누어 상승율 비교"""
        if hc is None or sb is None or hc >= len(self._raw_data) or sb >= len(self._raw_data):
            return False
        
        if sb <= hc:
            return False
        
        # SB~HC 구간의 중간점 계산
        cnt = sb - hc
        if cnt < 2:
            return False
        
        if cnt % 2 == 0:
            # 짝수면 cnt/2로 나누기
            mid_point = hc + (cnt // 2)
        else:
            # 홀수면 과거를 1개 많게
            mid_point = hc + (cnt // 2) + 1
        
        # 전반 구간 상승율 (SB ~ 중간점)
        sb_close = self._raw_data[sb]['현재가']
        mid_close = self._raw_data[mid_point]['현재가']
        front_rise_rate = ((mid_close - sb_close) / sb_close * 100) if sb_close > 0 else 0
        
        # 후반 구간 상승율 (중간점 ~ HC)
        hc_close = self._raw_data[hc]['현재가']
        back_rise_rate = ((hc_close - mid_close) / mid_close * 100) if mid_close > 0 else 0
        
        # 후반 상승율이 전반 상승율보다 크면 True (최근봉의 상승율이 가파름)
        return back_rise_rate > front_rise_rate
    
    def _analyze_bars_after_hc(self, n: int, hc: int) -> tuple:
        """현재봉부터 HC전까지 분석"""
        oh = []
        uc = []
        
        if hc <= 0:
            return oh, uc
        
        hc_high = self._raw_data[hc]['고가']
        
        for i in range(n, hc):
            if i >= len(self._raw_data):
                break
                
            candle = self._raw_data[i]
            high = candle['고가']
            close = candle['현재가']
            ma5 = self.ma(5, i)
            
            # 고가가 최고종가의 고가보다 낮은 봉들
            if high < hc_high:
                oh.append(i)
            
            # 종가가 5이평을 넘은 봉들
            if close > ma5:
                uc.append(i)
        
        return oh, uc
    
    def _build_rise_dict(self, hc: int, sb: int, max_red: tuple, max_blue: tuple, 
                        tail_count: int, peak: bool, today_bars: int, red_count: int, blue_count: int) -> dict:
        """rise 사전 구성"""
        if hc is None or sb is None or hc >= len(self._raw_data) or sb >= len(self._raw_data):
            return {}
        
        hc_close = self._raw_data[hc]['현재가']
        sb_close = self._raw_data[sb]['현재가']
        
        # rise_rate 계산
        rise_rate = ((hc_close - sb_close) / sb_close * 100) if sb_close > 0 else 0
        
        # three_rate, far_rate 계산
        bars = sb - hc
        x = hc + min(3, bars)
        
        three_rate = ((hc_close - self._raw_data[x]['현재가']) / sb_close * 100) if sb_close > 0 else 0 # 최근 3개 상승률
        far_rate = ((self._raw_data[x]['현재가'] - sb_close) / sb_close * 100) if sb_close > 0 else 0  # 시작봉 부터 4봉전 까지 상승률
        
        return {
            'hc': hc,               # 최고종가봉 인덱스
            'sb': sb,               # 시작봉 인덱스
            'bars': bars,           # SB - HC 상승 구간 봉 개수
            'rise_rate': rise_rate, # HC - SB 상승률
            'three_rate': three_rate, # 최근 3개 상승률 
            'far_rate': far_rate,   # 시작봉 부터 4봉전 까지 상승률
            'max_red': max_red,     # 양봉 중 최대 몸통 길이의 시가대비 종가 퍼센트
            'max_blue': max_blue,   # 음봉 중 최대 몸통 길이의 시가대비 종가 퍼센트
            'up_tails': tail_count, # 최고종가봉(hc)과 전후봉(hc-1, hc, hc+1) 중 윗꼬리 1%이상 개수
            'peak': peak,           # SB~HC 구간을 전반/후반으로 나누어 상승율 비교 (최근봉의 상승율이 가파르면 True)
            'today_bars': today_bars,
            'red_count': red_count, # SB~HC 구간 양봉 개수 (SB 제외, HC 포함)
            'blue_count': blue_count # SB~HC 구간 음봉 개수 (SB 제외, HC 포함)
        }
    
    def _build_fall_dict(self, oh: list, uc: list) -> dict:
        """fall 사전 구성"""
        return {
            'oh': oh,
            'uc': uc
        }
    
class ScriptManager:
    """
    스크립트 호출/인수 전파 원칙 요약 (A→B→C 예시)
    
    기본 개념
    - 최상위 실행 시 전달된 kwargs는 "현재 컨텍스트"(context)로 저장됨.
    - 하위 스크립트 호출 시: (현재 컨텍스트) + (호출자가 명시 전달한 인수)를 병합하여 자식의 kwargs를 구성.
        동일 키 충돌 시 "이번 호출에서 명시 전달한 인수"가 우선.
    - is_args() 우선순위: ① 이번 호출에서 명시 전달한 인수(_call_kwargs) → ② 병합된 현재 컨텍스트(context).
    - 컨텍스트는 현재 호출 체인 내부에서만 유효(체인 밖으로 누수 없음).
    
    단계별 예시
    1) A가 시작됨
        - A의 kwargs = { a1, a2, ... } 가 컨텍스트로 저장됨.
        - A 내부에서 is_args('a1')는 A의 kwargs를 읽음.
    
    2) A가 B를 호출 (명시 인수 bX만 전달)
        run_script('B', kwargs={ bX })
        - B의 kwargs = (A의 컨텍스트) ∪ { bX }
        - is_args() in B: ① bX(명시 인수) 우선, 없으면 ② A에서 온 컨텍스트 값 활용
        - B에서 값을 바꿔 전달하면, 그 병합 결과가 이후 단계의 새로운 컨텍스트가 됨.
    
    3) B가 C를 호출 (명시 인수 cY만 전달)
        run_script('C', kwargs={ cY })
        - C의 kwargs = (B 단계 병합 컨텍스트) ∪ { cY }
        - 즉, 최상위 A의 값들은 B에서 덮어쓰지 않았다면 C까지 전파됨.
        - C의 is_args(): ① cY → ② B 병합 컨텍스트(=A의 값 포함 가능)
    
    정리
    - 상위 컨텍스트는 누적 전파되고, 각 단계의 명시 인수가 해당 키를 덮어씀.
    - 동일 키에 대해 가장 최근 호출에서 명시 전달된 인수가 최우선.
    - is_args()는 "이번 호출 명시 인수"를 먼저 보고, 없으면 병합 컨텍스트를 참조.
    """
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
        self.scripts = {}  # {script_name: {script: str, desc: str}}
        self._running_scripts = set()  # 실행 중인 스크립트 추적
        self.chart_data = ChartData()  # 차트 데이터 관리자
        
        # 스레드별 컨텍스트 관리
        self._thread_local = threading.local()
        
        # 성능 최적화를 위한 캐시들
        self._module_cache = {}  # 모듈 캐시
        self._script_wrapper_cache = {}  # 스크립트 래퍼 캐시
        self._compiled_script_cache = {}  # 컴파일된 스크립트 캐시

        # 스크립트 결과 재사용을 위한 캐시
        self._script_result_cache = {}

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

    def _validate_and_execute_script(self, script_name: str, script: str, kwargs: dict, check_only: bool = False) -> dict:
        """스크립트 검증 및 실행을 통합한 메서드"""
        start_time = time.time()
        
        # 결과 초기화
        result_dict = {
            'result': None,     # 스크립트 실행 결과값 (ret()로 설정된 값)
            'error': None,      # 에러 메시지 (None이면 정상, 값이 있으면 실패)
            'logs': [],         # 실행 로그 (성공/실패 관계없이 수집)
        }
        
        # 1. 스크립트 이름 유효성 검사
        if not script_name.isidentifier():
            result_dict['error'] = f"유효하지 않은 스크립트 이름: {script_name}"
            return result_dict
        
        # 2. 구문 검증
        try:
            ast.parse(script)
        except SyntaxError as e:
            script_lines = script.splitlines()
            if e.lineno <= len(script_lines):
                error_line = script_lines[e.lineno-1].strip()
                error_msg = f"구문 오류 (행 {e.lineno}): {e.msg} → 수정: {error_line}"
            else:
                error_msg = f"구문 오류 (행 {e.lineno}): {e.msg}"
            result_dict['error'] = error_msg
            return result_dict
        except Exception as e:
            result_dict['error'] = f"스크립트 준비 오류: {type(e).__name__} - {e}"
            return result_dict
        
        # 3. 보안 검증
        if self._has_forbidden_syntax(script):
            result_dict['error'] = "보안 위반 코드 포함"
            return result_dict
        
        # 4. 실행을 통한 런타임 검증
        code = kwargs.get('code')
        
        # check_only=False일 때만 종목코드 필수 검증
        if not check_only and code is None:
            result_dict['error'] = "종목코드가 지정되지 않았습니다."
            result_dict['logs'].append('ERROR: 종목코드가 지정되지 않았습니다.')
            return result_dict
        
        # 순환 참조 방지 (check_only=True일 때는 건너뛰기)
        if not check_only:
            if self._is_circular_reference(script_name, code):
                current_stack = self._get_call_stack_info()
                result_dict['error'] = f"순환 참조 감지: {script_name} → {current_stack}"
                result_dict['logs'].append(f'ERROR: 순환 참조 감지: {script_name} → {current_stack}')
                return result_dict
            
            # 호출 스택에 추가
            self._add_to_call_stack(script_name, code)
        
        # 현재 컨텍스트 설정
        self._set_current_context(kwargs)
        
        try:
            # 실행 환경 준비
            globals_dict, script_logs = self._prepare_execution_globals(script_name)
            locals_dict = {}
            
            # 스크립트 컴파일 캐싱 - 스크립트 내용만으로 키 생성
            script_key = f"{script_name}:{hash(script)}"
            
            if script_key not in self._compiled_script_cache:
                logging.debug(f"🔄 {script_name} 컴파일 중... (첫 실행)")
                # 스크립트 내용만으로 래퍼 생성 (kwargs 제외)
                wrapped_script = self._make_wrapped_script(script)
                code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                self._compiled_script_cache[script_key] = code_obj
            
            # 캐시된 코드 사용, kwargs는 실행 시점에 전달
            code_obj = self._compiled_script_cache[script_key]
            
            # kwargs 변수 설정 - 실행 시점에 전달
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
            #script_logs.append(f"TRACEBACK: {tb}")
            
            logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}\n{tb}")
            
            result_dict['error'] = detailed_error
            result_dict['logs'] = script_logs
            return result_dict
            
        finally:
            # 실행 완료 후 추적 목록에서 제거 (check_only=True일 때는 건너뛰기)
            if not check_only:
                # 호출 스택에서 제거
                self._remove_from_call_stack(script_name, code)

    def run_script(self, script_name, kwargs=None):
        """검증된 스크립트 실행 (저장된 스크립트만 실행)"""
        if kwargs is None:
            kwargs = {}
        
        # 스크립트 내용 가져오기
        script_data = self.get_script(script_name)
        script_contents = script_data.get('script', '')
        
        if not script_contents:
            return {'result': None, 'error': f"스크립트 없음: {script_name}", 'logs': []}
        
        start_time = time.time()
        script_key = f"{script_name}:{hash(script_contents)}"
        
        # 캐시 체크 및 준비
        if script_key not in self._compiled_script_cache:
            #logging.debug(f"🔄 {script_name} 캐시 없음 - 새로 컴파일")
            # 캐시 없음 - 최초 실행: 검증 후 캐싱
            code = kwargs.get('code')
            if code is None:
                return {'result': None, 'error': "종목코드가 지정되지 않았습니다.", 'logs': []}
            
            if self._is_circular_reference(script_name, code):
                current_stack = self._get_call_stack_info()
                return {'result': None, 'error': f"순환 참조 감지: {script_name} → {current_stack}", 'logs': []}
            
            self._add_to_call_stack(script_name, code)
            need_cleanup = True
            
            # 컴파일 후 캐싱
            wrapped_script = self._make_wrapped_script(script_contents)
            code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
            self._compiled_script_cache[script_key] = code_obj
        else:
            # 캐시 있음 - 바로 실행
            code_obj = self._compiled_script_cache[script_key]
            need_cleanup = False
            #logging.debug(f"⚡ {script_name} 캐시 사용 - 즉시 실행")
        
        # 공통 실행 로직
        try:
            self._set_current_context(kwargs)
            globals_dict, script_logs = self._prepare_execution_globals(script_name)
            globals_dict['kwargs'] = kwargs
            globals_dict['_current_kwargs'] = kwargs
            
            # 실행
            script_result = None
            try:
                exec(code_obj, globals_dict, {})
                script_result = globals_dict.get('_script_result')
            except SystemExit as e:
                if str(e) == 'script_return':
                    script_result = globals_dict.get('_script_result')
                else:
                    raise e
            
            # 실행 시간 체크
            exec_time = time.time() - start_time
            if exec_time > 0.01:
                code = kwargs.get('code', 'UNKNOWN')
                warning_msg = f"스크립트 실행 기준(0.01초) ({script_name}:{code}): {exec_time:.4f}초"
                script_logs.append(f'WARNING: {warning_msg}')
            
            return {'result': script_result, 'error': None, 'logs': script_logs}
            
        except Exception as e:
            tb = traceback.format_exc()
            detailed_error = self._get_script_error_location(tb, script_contents)
            script_logs.append(f"ERROR: {detailed_error}")
            logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}")
            return {'result': None, 'error': detailed_error, 'logs': script_logs}
            
        finally:
            if need_cleanup:
                self._remove_from_call_stack(script_name, kwargs.get('code', ''))

    def set_script(self, script_name: str, script: str, desc: str = '', kwargs: dict = None, save: bool = True):
        """스크립트 검사 및 저장"""
        if kwargs is None:
            kwargs = {}
        
        # 🚀 스크립트 변경 시 캐시 무효화 (강화)
        self._invalidate_script_cache(script_name)
        logging.debug(f"🔄 {script_name} 스크립트 업데이트 - 캐시 무효화 완료")
        
        # 결과 초기화
        result_dict = {
            'result': None,
            'error': None,
            'logs': [],
        }
        
        # 검사 실행 (check_only=True로 런타임 에러까지 검증)
        check_result = self._validate_and_execute_script(script_name, script, kwargs, check_only=True)
        
        # 결과 복사
        result_dict['logs'] = check_result['logs'].copy()
        result_dict['result'] = check_result['result']
        
        if check_result['error'] is not None:
            result_dict['error'] = check_result['error']
            return result_dict
        
        # save=False면 검사까지만 하고 반환
        if not save: return result_dict
        
        # save=True인 경우 저장 진행
        script_data = {
            'script': script,
            'desc': desc
        }
        
        self.scripts[script_name] = script_data
        
        # 🚀 저장 시 즉시 컴파일하여 캐시에 저장 (실행 최적화)
        script_key = f"{script_name}:{hash(script)}"
        wrapped_script = self._make_wrapped_script(script)
        code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
        self._compiled_script_cache[script_key] = code_obj
        
        # 🚀 스크립트 래퍼도 즉시 생성하여 캐시에 저장
        wrapper_code = f"""
def {script_name}(*args, **kwargs):
    return run_script('{script_name}', args, kwargs)
"""
        try:
            compiled_wrapper = compile(wrapper_code, f"<wrapper_{script_name}>", 'exec')
            self._script_wrapper_cache[script_name] = compiled_wrapper
        except Exception as e:
            logging.error(f"스크립트 래퍼 생성 오류 ({script_name}): {e}")
        
        # 파일 저장
        save_result = self._save_scripts()
        if not save_result:
            result_dict['error'] = '파일 저장 실패'
            result_dict['logs'].append('ERROR: 파일 저장 실패')
            return result_dict

        # 성공
        result_dict['logs'].append(f'INFO: 스크립트 저장 완료: {script_name}')
        
        return result_dict

    def _get_script_error_location(self, tb_str, script):
        """스크립트 에러 위치 추출하여 상세한 에러 메시지 반환"""
        try:
            lines = tb_str.splitlines()
            error_line_num = None
            error_msg = "알 수 없는 오류"
            script_name = "스크립트"
            
            # 스크립트 이름 추출
            for line in lines:
                if "File \"<" in line and ">\"" in line:
                    match = re.search(r"File \"<([^>]+)>\"", line)
                    if match:
                        script_name = match.group(1)
                        break
            
            # 에러 라인 번호 추출 - user_script 함수 내부의 라인 찾기
            for line in lines:
                if f"File \"<{script_name}>\"" in line and ", line " in line and "user_script" in line:
                    match = re.search(r", line (\d+)", line)
                    if match:
                        wrapper_line = int(match.group(1))
                        # _make_wrapped_script의 실제 구조 확인:
                        # 사용자 스크립트는 9번째 라인부터 시작 (들여쓰기 포함)
                        if wrapper_line >= 12:
                            error_line_num = wrapper_line - 11  # 9번째 라인이 사용자 스크립트 1번째 라인
                        break
            
            # 에러 메시지 추출
            for line in lines:
                if any(err_type in line for err_type in [
                    "TypeError:", "NameError:", "SyntaxError:", "ValueError:", 
                    "AttributeError:", "IndexError:", "KeyError:", "ZeroDivisionError:",
                    "RuntimeError:", "ImportError:", "ModuleNotFoundError:"
                ]):
                    error_msg = line.strip()
                    break
            
            # 상세한 에러 정보 생성
            if error_line_num and error_line_num > 0:
                script_lines = script.splitlines()
                if error_line_num <= len(script_lines):
                    error_line = script_lines[error_line_num-1].strip()
                    
                    # 에러 라인 주변 컨텍스트 추가 (최대 3줄씩)
                    context_lines = []
                    start_idx = max(0, error_line_num - 4)  # 에러 라인 앞 3줄
                    end_idx = min(len(script_lines), error_line_num + 2)  # 에러 라인 뒤 1줄
                    
                    for i in range(start_idx, end_idx):
                        line_num = i + 1
                        line_content = script_lines[i].rstrip()
                        if line_num == error_line_num:
                            context_lines.append(f"  {line_num:3d}: >>> {line_content} <<< (에러 발생)")
                        else:
                            context_lines.append(f"  {line_num:3d}:    {line_content}")
                    
                    context_str = "\n".join(context_lines)
                    
                    return f"""실행 오류 ({script_name} 라인 {error_line_num}):
에러: {error_msg}
코드:
{context_str}"""
                else:
                    # 라인 번호가 범위를 벗어나면 전체 스택 트레이스 정보 제공
                    return f"""실행 오류 ({script_name}): {error_msg}
스택 트레이스에서 user_script 함수의 라인 {wrapper_line}에서 에러 발생
(계산된 사용자 스크립트 라인: {error_line_num}, 전체 스크립트 라인 수: {len(script.splitlines())})
원본 스택 트레이스를 확인하세요."""
            else:
                return f"실행 오류 ({script_name}): {error_msg}"
                
        except Exception as e:
            logging.error(f"에러 위치 파악 오류: {e}")
            return f"실행 오류: {error_msg}"

    def _safe_loop(self, iterable, func):
        """안전한 루프 실행 함수"""
        results = []
        for item in iterable:
            results.append(func(item))
        return results

    def _add_to_call_stack(self, script_name, code):
        """호출 스택에 추가"""
        if not hasattr(self, '_call_stack'):
            self._call_stack = []
        self._call_stack.append((script_name, code))
    
    def _remove_from_call_stack(self, script_name, code):
        """호출 스택에서 제거 (LIFO 방식)"""
        if hasattr(self, '_call_stack') and self._call_stack:
            # 마지막에 추가된 같은 스크립트:종목 조합 제거
            for i in range(len(self._call_stack) - 1, -1, -1):
                if self._call_stack[i] == (script_name, code):
                    del self._call_stack[i]
                    break
    
    def _is_circular_reference(self, script_name, code):
        """정확한 순환 참조 감지"""
        if not hasattr(self, '_call_stack'):
            return False
        
        # 같은 스크립트:종목 조합의 위치들 찾기
        same_script_positions = []
        for i, (stack_script, stack_code) in enumerate(self._call_stack):
            if stack_script == script_name and stack_code == code:
                same_script_positions.append(i)
        
        # 같은 스크립트가 2번 이상 호출되면 순환 참조 가능성
        if len(same_script_positions) >= 2:
            # 마지막 호출과 첫 호출 사이에 다른 스크립트가 있는지 확인
            first_pos = same_script_positions[0]
            last_pos = same_script_positions[-1]
            
            # 중간에 다른 스크립트가 있으면 순환 참조
            for i in range(first_pos + 1, last_pos):
                if self._call_stack[i][0] != script_name:
                    return True  # 순환 참조!
        
        return False  # 순환 참조 아님
    
    def _get_call_stack_info(self):
        """호출 스택 정보를 문자열로 반환"""
        if not hasattr(self, '_call_stack'):
            return ""
        
        stack_info = []
        for script_name, code in self._call_stack:
            stack_info.append(f"{script_name}({code})")
        
        return " → ".join(stack_info)

    def _invalidate_script_cache(self, script_name: str):
        """스크립트 변경 시 캐시 무효화"""
        # 컴파일된 스크립트 캐시에서 해당 스크립트 제거
        keys_to_remove = [key for key in self._compiled_script_cache.keys() if key.startswith(f"{script_name}:")]
        for key in keys_to_remove:
            del self._compiled_script_cache[key]
            #logging.debug(f"🗑️ 캐시 제거: {key}")
        
        # 스크립트 래퍼 캐시에서도 제거
        if script_name in self._script_wrapper_cache:
            del self._script_wrapper_cache[script_name]
            #logging.debug(f"🗑️ 래퍼 캐시 제거: {script_name}")
        
        # 스크립트 결과 캐시에서도 제거
        if script_name in self._script_result_cache:
            del self._script_result_cache[script_name]
            #logging.debug(f"🗑️ 결과 캐시 제거: {script_name}")
        
        #logging.debug(f"🗑️ {script_name} 캐시 무효화 완료")
    
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
            
            def percent(a, b, c=None, default=0):
                if c is None: c = b
                return safe_div((a - b), c, default) * 100

            def bar_idx(target_time: str, current_time: str=None, tick: int=180, debug: bool=False) -> int:
                """
                target_time이 현재 시간 기준으로 몇 봉 전인지 반환
                
                Args:
                    target_time: 찾을 시간 (매수시간 등, 예: '20250101103000')
                    current_time: 현재 시간 (예: '20250101103300'), None이면 시스템시간 사용
                    tick: 봉 간격 (초) - 60(1분), 180(3분), 600(10분)
                    debug: True면 계산 과정 로그 출력
                    
                Returns:
                    int: target_time이 몇 봉 전인지
                        0: 현재봉과 같은 봉, 1: 1봉전, 2: 2봉전, ...
                        -1: 1봉 후 (미래), -2: 2봉 후, ...
                        None: 다른 날짜
                """
                # current_time이 None이면 시스템 시간 사용
                if current_time is None:
                    from datetime import datetime
                    current_time = datetime.now().strftime('%Y%m%d%H%M%S')
                
                current_date = current_time[:8]
                target_date = target_time[:8]
                
                # 다른 날짜면 None 반환
                if current_date != target_date: return None
                
                # 시간을 초 단위로 변환 (자정 00:00:00 기준)
                current_tick = int(current_time[8:])  # HHMMSS
                target_tick = int(target_time[8:])
                
                current_seconds = (current_tick // 10000) * 3600 + ((current_tick % 10000) // 100) * 60 + (current_tick % 100)
                target_seconds = (target_tick // 10000) * 3600 + ((target_tick % 10000) // 100) * 60 + (target_tick % 100)
                
                # 각 시간이 속한 봉의 시작 시간으로 정규화 (자정 기준)
                current_bar_start = (current_seconds // tick) * tick
                target_bar_start = (target_seconds // tick) * tick
                
                # 정규화된 시간 차이로 봉 인덱스 계산
                bar_index = (current_bar_start - target_bar_start) // tick
                
                # 디버그 모드
                if debug:
                    def sec_to_time(sec):
                        h = sec // 3600
                        m = (sec % 3600) // 60
                        s = sec % 60
                        return f"{h:02d}:{m:02d}:{s:02d}"
                    
                    echo(f"[bar_idx DEBUG]")
                    echo(f"  target_time={target_time}, current_time={current_time}, tick={tick}")
                    echo(f"  target: {target_seconds}초 → {sec_to_time(target_bar_start)} 봉")
                    echo(f"  current: {current_seconds}초 → {sec_to_time(current_bar_start)} 봉")
                    echo(f"  bar_index = ({current_bar_start} - {target_bar_start}) // {tick} = {bar_index}")
                
                return int(bar_index)

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
                'percent': percent,
                'bar_idx': bar_idx,
                'iif': safe_iif,
                'run_script': self._script_caller,
                'is_args': is_args,
                'hoga': lambda x, y: hoga(x, y),
                'echo': echo,
                'ret': script_return,
                'result_cache': self._script_result_cache,  # 전역 캐시 변수 추가
                '_script_logs': script_logs,
                '_current_kwargs': {},
                '_script_result': None,
            }
            
            script_return.caller_globals = globals_dict
            
            # 누락된 스크립트 래퍼 자동 생성
            for script_name, script_data in self.scripts.items():
                if script_name not in self._script_wrapper_cache:
                    wrapper_code = f"""
def {script_name}(*args, **kwargs):
    return run_script('{script_name}', args, kwargs)
"""
                    try:
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
        
        # 프레임 검사 제거 - 컨텍스트만 사용
        
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

    def _make_wrapped_script(self, script):
        """kwargs를 제외한 순수 스크립트 래퍼 생성"""
        indented_script = '\n'.join(' ' * 8 + line if line.strip() else line for line in script.split('\n'))
        
        return f"""
def execute_script():
    def user_script():
        # kwargs는 실행 시점에 globals에서 가져옴
        kwargs = globals().get('kwargs', {{}})
        
        # 모든 kwargs를 globals()에 설정하여 사용자 스크립트에서 접근 가능하게
        for key, value in kwargs.items():
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


    c1 = ct.ma(5) > ct.ma(20) and ct.c > ct.ma(5)
    c2 = ct.ma(5) < ct.ma(5) and ct.ma(20) < ct.ma(20)

    result = c1 and c2

    logging.debug(result)

