from public import gm, dc
from classes import la
from datetime import datetime
from typing import Set, Optional, Any
from PyQt5.QtCore import QTimer
import json
import numpy as np
import pandas as pd
import logging
import time
import ast
import traceback
import re
import os
import threading
import copy

class ChartDataRegister:
    def __init__(self, name):
        self.name = name
        self.running = False
        self._lock = threading.RLock()
        self.done_code = []
        self.todo_code = {}
        self.loop_interval = 0.3  # 루프 간격 (초)
        
    def start_register(self):
        """루프 시작 - la.work로 호출"""
        if self.running:
            return False
        
        self.running = True
        self._loop_task()  # 첫 루프 실행
        logging.debug(f'{self.name} 시작')
        return True
        
    def stop_register(self):
        """루프 중지 - la.work로 호출"""
        self.running = False
        logging.debug(f'{self.name} 중지')
        return True
        
    def _loop_task(self):
        """한 번의 루프 처리 - 내부에서 호출"""
        if not self.running:
            return
            
        try:
            # 차트 데이터 요청 처리
            if self.todo_code:
                self.request_chart_data()
                
            # 다음 루프 예약
            if self.running:
                QTimer.singleShot(int(self.loop_interval * 1000), self._loop_task)
        except Exception as e:
            logging.error(f'{self.name} 루프 처리 오류: {e}', exc_info=True)
            self.running = False

    def request_chart_data(self):
        codes = copy.deepcopy(self.todo_code)
        for code in codes:
            mi_done = codes[code]['mi']
            if not mi_done:
                dict_data = la.answer('admin', 'com_get_chart_data', code, cycle='mi', tick=1)
                if dict_data:
                    gm.cdt.set_chart_data(code, dict_data, 'mi', 1)
                    with self._lock: self.todo_code[code]['mi'] = True
                    mi_done = True

            dy_done = codes[code]['dy']
            if not dy_done:
                dict_data = la.answer('admin', 'com_get_chart_data', code, cycle='dy')
                if dict_data:
                    gm.cdt.set_chart_data(code, dict_data, 'dy')
                    with self._lock: self.todo_code[code]['dy'] = True
                    dy_done = True

            if mi_done and dy_done:
                with self._lock:
                    self.done_code.append(code)
                    del self.todo_code[code]
                    
    def register_code(self, code):
        """코드 등록 - la.work 또는 la.answer로 호출"""
        if code in self.done_code or code in self.todo_code:
            return False
        
        logging.debug(f'{self.name} 차트관리 종목코드 등록: {code}')
        with self._lock:
            self.todo_code[code] = {'mi': False, 'dy': False}
        return True
    
class ChartData:
    """차트 데이터를 관리하는 최적화된 싱글톤 클래스"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChartData, cls).__new__(cls)
            cls._instance._data = {}  # {code: {cycle: data}}
            cls._instance._index_maps = {}  # {code: {cycle: {time_key: index}}} - 빠른 시간 검색용
            cls._instance._cached_aggregations = {}  # {code: {cycle_tick: (timestamp, data)}} - 집계 캐시
            cls._instance._active_requests = {}  # 활성 요청 추적
            cls._instance._cache_timeout = 300  # 5분 캐시 타임아웃 (초)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
    
    def set_chart_data(self, code: str, data: list, cycle: str, tick: int = None):
        """외부에서 차트 데이터 설정"""
        if not data:
            return
            
        cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
        
        if code not in self._data:
            self._data[code] = {}
            self._index_maps[code] = {}
        
        # 데이터 설정
        self._data[code][cycle_key] = data
        
        # 인덱스 맵 생성 (빠른 검색용)
        self._create_index_map(code, cycle_key)
        
        # 3분봉 데이터 초기화 (1분봉으로부터 생성)
        if cycle == 'mi' and tick == 1 and 'mi3' not in self._data[code]:
            self._data[code]['mi3'] = self._aggregate_minute_data(data, 3)
            self._create_index_map(code, 'mi3')
            
        # 캐시 무효화
        self._invalidate_aggregation_cache(code)
    
    def _create_index_map(self, code: str, cycle_key: str):
        """시간 -> 인덱스 매핑 생성 (빠른 검색용)"""
        if code not in self._index_maps:
            self._index_maps[code] = {}
            
        index_map = {}
        data = self._data[code][cycle_key]
        
        time_key = '체결시간' if cycle_key.startswith('mi') else '일자'
        
        for i, candle in enumerate(data):
            if time_key in candle:
                index_map[candle[time_key]] = i
                
        self._index_maps[code][cycle_key] = index_map
    
    def update_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """실시간 가격 정보로 차트 데이터 업데이트 (최적화 버전)"""
        # 등록되지 않은 코드는 무시
        if code not in self._data or 'mi1' not in self._data[code]:
            return
            
        # 기준 시간 계산 (분 단위로)
        base_time = datetime_str[:12] + '00'  # 분 단위로 맞춤
        
        minute_data = self._data[code]['mi1']
        
        # 데이터가 없는 경우
        if not minute_data:
            new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
            minute_data.insert(0, new_candle)
            if code in self._index_maps and 'mi1' in self._index_maps[code]:
                self._index_maps[code]['mi1'][base_time] = 0
            return
        
        # 최신 봉 시간 확인
        latest_time = minute_data[0]['체결시간']
        
        # 같은 봉 내의 업데이트인 경우
        if latest_time == base_time:
            # 기존 봉 업데이트
            self._update_candle(minute_data[0], price, price, volume, amount)
        else:
            # 새로운 봉 또는 누락된 봉 처리
            # 시간대 차이 확인
            time_diff = self._calculate_time_diff(latest_time, base_time)
            
            # 누락된 봉이 있는 경우
            if time_diff > 1:
                # 직전 봉의 종가
                last_price = minute_data[0]['현재가']
                
                # 누락된 시간대 목록 생성
                missing_times = self._generate_missing_times(latest_time, base_time)
                
                # 누락된 봉 생성
                for missing_time in missing_times:
                    # 누락 봉은 직전 봉의 종가로 OHLC 모두 동일하게 설정
                    missing_candle = self._create_candle(
                        code, missing_time, last_price, last_price, last_price, last_price, 0, 0, True)
                    minute_data.insert(0, missing_candle)
                    self._update_index_map(code, 'mi1', missing_time)
            
            # 현재 시간대의 새 봉 추가
            new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
            minute_data.insert(0, new_candle)
            self._update_index_map(code, 'mi1', base_time)
        
        # 3분봉 업데이트
        self._update_cyclic_chart(code, price, volume, amount, datetime_str, 3)
        
        # 일봉 업데이트 (있는 경우에만)
        if 'dy' in self._data[code]:
            self._update_day_chart(code, price, volume, amount, datetime_str)
        
        # 캐시 무효화
        self._invalidate_aggregation_cache(code)
    
    def _create_candle(self, code, time_str, close, open, high, low, volume, amount, is_missing=False):
        """캔들 객체 생성 헬퍼 함수"""
        candle = {
            '종목코드': code,
            '체결시간': time_str,
            '현재가': close,
            '시가': open,
            '고가': high,
            '저가': low,
            '거래량': volume,
            '거래대금': amount
        }
        if is_missing:
            candle['is_missing'] = True
        return candle
    
    def _update_candle(self, candle, price, open_price=None, volume=None, amount=None):
        """캔들 업데이트 헬퍼 함수"""
        candle['현재가'] = price
        candle['고가'] = max(candle['고가'], price)
        candle['저가'] = min(candle['저가'], price)
        
        if open_price is not None:
            candle['시가'] = open_price
        if volume is not None:
            candle['거래량'] = volume
        if amount is not None:
            candle['거래대금'] = amount
        
        # 누락 표시 제거
        if 'is_missing' in candle:
            del candle['is_missing']
    
    def _update_index_map(self, code, cycle_key, time_key):
        """인덱스 맵 업데이트 (새 캔들 추가 시)"""
        if code in self._index_maps and cycle_key in self._index_maps[code]:
            # 기존 인덱스 시프트
            self._index_maps[code][cycle_key] = {k: v+1 for k, v in self._index_maps[code][cycle_key].items()}
            # 새 캔들 인덱스 추가
            self._index_maps[code][cycle_key][time_key] = 0
    
    def _calculate_time_diff(self, time1, time2, tick=1):
        """두 시간 사이의 차이 계산 (tick 단위)"""
        # 날짜 부분이 다르면 큰 값 반환
        if time1[:8] != time2[:8]:
            return 1000  # 다른 날짜는 큰 차이로 처리
        
        # 시간을 분으로 변환
        minutes1 = int(time1[8:10]) * 60 + int(time1[10:12])
        minutes2 = int(time2[8:10]) * 60 + int(time2[10:12])
        
        # tick 단위로 변환
        period1 = minutes1 // tick
        period2 = minutes2 // tick
        
        # 차이 계산
        return period2 - period1 if period2 > period1 else 1000
    
    def _generate_missing_times(self, start_time, end_time, tick=1):
        """누락된 시간대 목록 생성"""
        result = []
        
        # 날짜 부분이 다르면 빈 목록 반환
        if start_time[:8] != end_time[:8]:
            return result
        
        # 시작/종료 시간을 분으로 변환
        start_minutes = int(start_time[8:10]) * 60 + int(start_time[10:12])
        end_minutes = int(end_time[8:10]) * 60 + int(end_time[10:12])
        
        # tick 단위로 변환
        start_period = (start_minutes // tick)
        end_period = (end_minutes // tick)
        
        # 사이에 있는 모든 시간대 생성
        for period in range(start_period + 1, end_period):
            minutes = period * tick
            hour = minutes // 60
            minute = minutes % 60
            time_str = f"{start_time[:8]}{hour:02d}{minute:02d}00"
            result.append(time_str)
        
        return result
    
    def _update_cyclic_chart(self, code, price, volume, amount, datetime_str, tick):
        """주기적 차트 업데이트 (3분봉 등)"""
        cycle_key = f'mi{tick}'
        
        # 입력 데이터 형식 검증
        if len(datetime_str) < 12:
            return
        
        # 시간 계산
        hour = int(datetime_str[8:10])
        minute = int(datetime_str[10:12])
        total_minutes = hour * 60 + minute
        
        # tick 주기 구간 계산
        tick_start = (total_minutes // tick) * tick
        tick_time = f"{datetime_str[:8]}{tick_start//60:02d}{tick_start%60:02d}00"
        
        # 데이터 없으면 초기화
        if cycle_key not in self._data[code]:
            minute_data = self._data[code].get('mi1', [])
            if minute_data:
                self._data[code][cycle_key] = self._aggregate_minute_data(minute_data, tick)
                self._create_index_map(code, cycle_key)
            else:
                self._data[code][cycle_key] = []
            return
        
        # 주기 데이터 및 인덱스 맵 참조
        cyclic_data = self._data[code][cycle_key]
        index_map = self._index_maps[code].get(cycle_key, {})
        
        # 주기 데이터가 비어있으면 새로 생성
        if not cyclic_data:
            new_candle = self._create_candle(code, tick_time, price, price, price, price, volume, amount)
            cyclic_data.append(new_candle)
            
            # 인덱스 맵 초기화
            if cycle_key not in self._index_maps[code]:
                self._index_maps[code][cycle_key] = {}
            self._index_maps[code][cycle_key][tick_time] = 0
            return
        
        # 현재 주기 시간 확인
        latest_time = cyclic_data[0]['체결시간']
        
        # 같은 주기 내의 업데이트인 경우
        if latest_time == tick_time:
            # 기존 주기 캔들 업데이트
            self._update_candle(cyclic_data[0], price, None, volume, amount)
            return
        
        # 시간 차이 확인
        time_diff = self._calculate_time_diff(latest_time, tick_time, tick)
        
        # 누락된 주기 캔들이 있는 경우
        if time_diff > 1:
            # 직전 주기 캔들의 종가
            last_price = cyclic_data[0]['현재가']
            
            # 누락된 주기 시간대 목록 생성
            missing_times = self._generate_missing_times(latest_time, tick_time, tick)
            
            # 누락된 주기 캔들 생성
            for missing_time in missing_times:
                missing_candle = self._create_candle(
                    code, missing_time, last_price, last_price, last_price, last_price, 0, 0, True)
                cyclic_data.insert(0, missing_candle)
                self._update_index_map(code, cycle_key, missing_time)
        
        # 현재 주기 캔들 추가
        new_candle = self._create_candle(code, tick_time, price, price, price, price, volume, amount)
        cyclic_data.insert(0, new_candle)
        self._update_index_map(code, cycle_key, tick_time)
    
    def _update_day_chart(self, code, price, volume, amount, datetime_str):
        """일봉 데이터 업데이트 (당일) - 최적화 버전"""
        day_data = self._data[code].get('dy', [])
        if not day_data:
            return
            
        today = datetime_str[:8]  # YYYYMMDD
        
        # 인덱스 맵 사용하여 오늘 데이터 빠르게 찾기
        if code in self._index_maps and 'dy' in self._index_maps[code] and today in self._index_maps[code]['dy']:
            idx = self._index_maps[code]['dy'][today]
            if idx < len(day_data):
                current = day_data[idx]
                self._update_candle(current, price, None, volume, amount)
                return
        
        # 당일 데이터가 없는 경우
        # 전일 봉 찾기
        if day_data:
            last_price = day_data[0]['현재가']  # 전일 종가
            
            # 새 일봉 추가
            new_day = {
                '종목코드': code,
                '일자': today,
                '현재가': price,
                '시가': price,  # 첫 체결가가 시가가 됨
                '고가': price,
                '저가': price,
                '거래량': volume,
                '거래대금': amount
            }
            day_data.insert(0, new_day)
            
            # 인덱스 맵 업데이트
            if code not in self._index_maps:
                self._index_maps[code] = {}
            if 'dy' not in self._index_maps[code]:
                self._index_maps[code]['dy'] = {}
            
            # 기존 인덱스 시프트
            self._index_maps[code]['dy'] = {k: v+1 for k, v in self._index_maps[code]['dy'].items()}
            # 새 데이터 인덱스 추가
            self._index_maps[code]['dy'][today] = 0
    
    def _invalidate_aggregation_cache(self, code: str):
        """코드 관련 집계 캐시 무효화"""
        if code in self._cached_aggregations:
            self._cached_aggregations[code] = {}
    
    def get_chart_data(self, code: str, cycle: str, tick: int = None) -> list:
        """특정 종목, 주기의 차트 데이터 반환 (캐시 활용)"""
        # 등록되지 않은 코드면 빈 리스트 반환
        if code not in self._data:
            return []
        
        cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
        
        # 1분봉, 3분봉, 일봉은 있으면 바로 반환
        if cycle_key in ['mi1', 'mi3', 'dy'] and cycle_key in self._data[code]:
            return self._data[code][cycle_key]
        
        # 다른 분봉은 캐시 확인 후 없으면 1분봉에서 생성
        if cycle == 'mi' and 'mi1' in self._data[code]:
            # 캐시 확인
            if code in self._cached_aggregations and cycle_key in self._cached_aggregations[code]:
                cache_time, cached_data = self._cached_aggregations[code][cycle_key]
                # 캐시가 유효하면 사용
                if time.time() - cache_time < self._cache_timeout:
                    return cached_data
            
            # 캐시 없으면 생성하고 캐싱
            aggregated_data = self._aggregate_minute_data(self._data[code]['mi1'], tick)
            if code not in self._cached_aggregations:
                self._cached_aggregations[code] = {}
            self._cached_aggregations[code][cycle_key] = (time.time(), aggregated_data)
            return aggregated_data
        
        # 주봉, 월봉은 없으면 서버에서 가져오기
        if cycle in ['wk', 'mo'] and cycle not in self._data[code]:
            data = self._get_chart_data(code, cycle)
            if data:
                self.set_chart_data(code, data, cycle)
                return data
        
        # 이미 데이터가 있으면 반환
        return self._data.get(code, {}).get(cycle_key, [])
    
    def _aggregate_minute_data(self, minute_data: list, tick: int) -> list:
        """1분봉 데이터를 특정 tick으로 집계 (최적화 버전)"""
        if not minute_data:
            return []
        
        # 그룹별 데이터 저장용 해시맵
        grouped_data = {}
        
        # 분 계산용 룩업 테이블 (캐싱)
        minute_map = {}
        
        for candle in minute_data:
            dt_str = candle['체결시간']
            if len(dt_str) < 12:
                continue
            
            # 시간 계산 최적화
            if dt_str in minute_map:
                group_key = minute_map[dt_str]
            else:
                # 분 단위로 계산
                hour = int(dt_str[8:10])
                minute = int(dt_str[10:12])
                total_minutes = hour * 60 + minute
                # tick 단위로 그룹화
                tick_start = (total_minutes // tick) * tick
                group_hour = tick_start // 60
                group_minute = tick_start % 60
                group_key = f"{dt_str[:8]}{group_hour:02d}{group_minute:02d}00"
                minute_map[dt_str] = group_key
            
            if group_key not in grouped_data:
                # 새 그룹 생성
                grouped_data[group_key] = {
                    '종목코드': candle['종목코드'],
                    '체결시간': group_key,
                    '현재가': candle['현재가'],
                    '시가': candle['시가'],
                    '고가': candle['고가'],
                    '저가': candle['저가'],
                    '거래량': candle['거래량'],
                    '거래대금': candle.get('거래대금', 0)
                }
            else:
                # 기존 그룹 업데이트
                group = grouped_data[group_key]
                group['현재가'] = candle['현재가']  # 마지막 값이 종가가 됨
                group['고가'] = max(group['고가'], candle['고가'])
                group['저가'] = min(group['저가'], candle['저가'])
        
        # 시간 기준 정렬하여 결과 반환 (최신이 먼저)
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['체결시간'], reverse=True)
        return result
    
    def _get_chart_data(self, code, cycle, tick=None):
        """서버에서 차트 데이터 가져오기 (주봉과 월봉만 요청 할 것)"""
        # 이미 요청 중인지 확인하여 데드락 방지
        try:
            request_key = f"{code}_{cycle}_{tick}"
            current_time = time.time()
            
            if request_key in self._active_requests:
                last_request_time = self._active_requests[request_key]
                # 5초 이상 경과한 요청은 타임아웃으로 간주하고 재시도
                if current_time - last_request_time < 5.0:
                    logging.debug(f"이미 요청 중인 데이터: {request_key}")
                    return []
            
            # 요청 시작 시간 기록
            self._active_requests[request_key] = current_time
            dict_list = la.answer('admin', 'com_get_chart_data', code, cycle, tick)
            
            return dict_list
        
        except Exception as e:
            logging.error(f'챠트 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []
        finally:
            # 요청 완료 시 활성 요청 목록에서 제거
            if request_key in self._active_requests:
                del self._active_requests[request_key]

class ChartManager:
    def __init__(self, cycle='dy', tick=1):
        self.cycle = cycle  # 'mo', 'wk', 'dy', 'mi' 중 하나
        self.tick = tick    # 분봉일 경우 주기
        self.chart_data = ChartData()  # 싱글톤 인스턴스
        self._data_cache = {}  # 종목별 데이터 캐시 {code: data}
    
    def _get_data(self, code: str) -> list:
        """해당 종목의 차트 데이터 가져오기 (캐싱)"""
        if code not in self._data_cache:
            # 데이터 가져오기
            self._data_cache[code] = self._load_chart_data(code)
        return self._data_cache[code]
    
    def _load_chart_data(self, code: str) -> list:
        """차트 데이터 로드 및 변환"""
        data = self.chart_data.get_chart_data(code, self.cycle, self.tick)
        
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
    
    def _get_value(self, code: str, n: int, key: str, default=0):
        """지정된 위치(n)의 데이터 값 가져오기"""
        data = self._get_data(code)
        
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
    
    def _get_values(self, code: str, func, n: int, m: int = 0) -> list:
        """지정된 함수를 통해 n개의 값을 배열로 가져오기"""
        values = []
        for i in range(m, m + n):
            if callable(func):
                values.append(func(code, i))
            else:
                # func가 함수가 아니면 그대로 사용 (상수값)
                values.append(func)
        return values
    
    def clear_cache(self, code: str = None):
        """특정 코드 또는 전체 캐시 초기화"""
        if code:
            if code in self._data_cache:
                del self._data_cache[code]
        else:
            self._data_cache.clear()
    
    # 기본 값 반환 함수들 - 기존 코드 유지
    def c(self, code: str, n: int = 0) -> float:
        """종가 반환"""
        return self._get_value(code, n, 'close')
    
    def o(self, code: str, n: int = 0) -> float:
        """시가 반환"""
        return self._get_value(code, n, 'open')
    
    def h(self, code: str, n: int = 0) -> float:
        """고가 반환"""
        return self._get_value(code, n, 'high')
    
    def l(self, code: str, n: int = 0) -> float:
        """저가 반환"""
        return self._get_value(code, n, 'low')
    
    def v(self, code: str, n: int = 0) -> int:
        """거래량 반환"""
        return int(self._get_value(code, n, 'volume', 0))
    
    def a(self, code: str, n: int = 0) -> float:
        """거래금액 반환"""
        return self._get_value(code, n, 'amount')
    
    def time(self, n: int = 0) -> str:
        """시간 반환"""
        if self.cycle != 'mi':
            return ''
        code = "005930"  # 테스트용 코드
        return self._get_value(code, n, 'time', '')
    
    def today(self) -> str:
        """오늘 날짜 반환"""
        return datetime.now().strftime('%Y%m%d')
    
    # 계산 함수들
    def ma(self, code: str, a, n: int, m: int = 0, k: str = 'a') -> float:
        """이동평균 계산"""
        if k == 'a': return self.avg(code, a, n, m)
        elif k == 'e': return self.eavg(code, a, n, m)
        elif k == 'w': return self.wavg(code, a, n, m)
        return 0.0
    
    def avg(self, code: str, a, n: int, m: int = 0) -> float:
        """단순이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return sum(values) / len(values)
    
    def eavg(self, code: str, a, n: int, m: int = 0) -> float:
        """지수이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        
        alpha = 2 / (n + 1)
        result = values[0]
        for i in range(1, len(values)):
            result = alpha * values[i] + (1 - alpha) * result
        return result
    
    def wavg(self, code: str, a, n: int, m: int = 0) -> float:
        """가중이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        
        weights = [i+1 for i in range(len(values))]
        return sum(v * w for v, w in zip(values, weights)) / sum(weights)
    
    def highest(self, code: str, a, n: int, m: int = 0) -> float:
        """가장 높은 값 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return max(values)
    
    def lowest(self, code: str, a, n: int, m: int = 0) -> float:
        """가장 낮은 값 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return min(values)
    
    def stdev(self, code: str, a, n: int, m: int = 0) -> float:
        """표준편차 계산"""
        values = self._get_values(code, a, n, m)
        if not values or len(values) < 2: return 0.0
        return np.std(values)
    
    def sum(self, code: str, a, n: int, m: int = 0) -> float:
        """합계 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return sum(values)
    
    # 신호 함수들
    def cross_down(self, code: str, a, b) -> bool:
        """a가 b를 하향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(code, 1), a(code, 0)
            b_prev, b_curr = b(code, 1), b(code, 0)
            return a_prev >= b_prev and a_curr < b_curr
        return False
    
    def cross_up(self, code: str, a, b) -> bool:
        """a가 b를 상향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(code, 1), a(code, 0)
            b_prev, b_curr = b(code, 1), b(code, 0)
            return a_prev <= b_prev and a_curr > b_curr
        return False
    
    def bars_since(self, code: str, condition) -> int:
        """조건이 만족된 이후 지나간 봉 개수"""
        count = 0
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                return count
            count += 1
        return count
    
    def highest_since(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최고값"""
        condition_met = 0
        highest_val = float('-inf')
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(code, j)
            highest_val = max(highest_val, val)
        
        return highest_val
    
    def lowest_since(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최저값"""
        condition_met = 0
        lowest_val = float('inf')
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(code, j)
            lowest_val = min(lowest_val, val)
        
        return lowest_val
    
    def value_when(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 시점의 data_func 값"""
        condition_met = 0
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    return data_func(code, i)
        
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

    # 보조지표 계산 함수들
    def rsi(self, code: str, period: int = 14, m: int = 0) -> float:
        """상대강도지수(RSI) 계산"""
        values = self._get_values(code, self.c, period + 1, m)
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
    
    def macd(self, code: str, fast: int = 12, slow: int = 26, signal: int = 9, m: int = 0) -> tuple:
        """MACD(Moving Average Convergence Divergence) 계산
        Returns: (MACD 라인, 시그널 라인, 히스토그램)
        """
        # 빠른 EMA
        fast_ema = self.eavg(code, self.c, fast, m)
        # 느린 EMA
        slow_ema = self.eavg(code, self.c, slow, m)
        # MACD 라인
        macd_line = fast_ema - slow_ema
        
        # 시그널 라인
        # 참고: 실제로는 MACD 값의 이력이 필요하나 단순화를 위해 현재 값만 사용
        signal_line = self.eavg(code, self.c, signal, m)
        
        # 히스토그램
        histogram = macd_line - signal_line
        
        return (macd_line, signal_line, histogram)
    
    def bollinger_bands(self, code: str, period: int = 20, std_dev: float = 2, m: int = 0) -> tuple:
        """볼린저 밴드 계산
        Returns: (상단 밴드, 중간 밴드(SMA), 하단 밴드)
        """
        middle_band = self.avg(code, self.c, period, m)
        stdev = self.stdev(code, self.c, period, m)
        
        upper_band = middle_band + (stdev * std_dev)
        lower_band = middle_band - (stdev * std_dev)
        
        return (upper_band, middle_band, lower_band)
    
    def stochastic(self, code: str, k_period: int = 14, d_period: int = 3, m: int = 0) -> tuple:
        """스토캐스틱 오실레이터 계산
        Returns: (%K, %D)
        """
        # 최고가, 최저가 가져오기
        highest_high = self.highest(code, self.h, k_period, m)
        lowest_low = self.lowest(code, self.l, k_period, m)
        
        # 현재 종가
        current_close = self.c(code, m)
        
        # %K 계산
        percent_k = 0
        if highest_high != lowest_low:
            percent_k = 100 * ((current_close - lowest_low) / (highest_high - lowest_low))
        
        # %D 계산 (간단한 이동평균 사용)
        # 참고: 실제로는 %K 값의 이력이 필요하나 단순화를 위해 현재 값으로 대체
        percent_d = self.avg(code, self.c, d_period, m)
        
        return (percent_k, percent_d)
    
    def atr(self, code: str, period: int = 14, m: int = 0) -> float:
        """평균 실제 범위(ATR) 계산"""
        data = self._get_data(code)
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
    def is_doji(self, code: str, n: int = 0, threshold: float = 0.1) -> bool:
        """도지 캔들 확인 (시가와 종가의 차이가 매우 작은 캔들)"""
        o = self.o(code, n)
        c = self.c(code, n)
        h = self.h(code, n)
        l = self.l(code, n)
        
        # 몸통 크기
        body = abs(o - c)
        # 전체 캔들 크기
        candle_range = h - l
        
        if candle_range == 0:
            return False
            
        # 몸통이 전체 캔들의 threshold% 이하이면 도지로 간주
        return body / candle_range <= threshold
    
    def is_hammer(self, code: str, n: int = 0) -> bool:
        """망치형 캔들 확인 (아래 꼬리가 긴 캔들)"""
        o = self.o(code, n)
        c = self.c(code, n)
        h = self.h(code, n)
        l = self.l(code, n)
        
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
    
    def is_engulfing(self, code: str, n: int = 0, bullish: bool = True) -> bool:
        """포괄 패턴 확인 (이전 캔들을 완전히 덮는 형태)
        bullish=True: 상승 포괄 패턴, bullish=False: 하락 포괄 패턴
        """
        if n + 1 >= len(self._get_data(code)):
            return False
            
        curr_o = self.o(code, n)
        curr_c = self.c(code, n)
        prev_o = self.o(code, n + 1)
        prev_c = self.c(code, n + 1)
        
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
    def is_uptrend(self, code: str, period: int = 14, m: int = 0) -> bool:
        """상승 추세 여부 확인 (단순하게 종가가 이동평균보다 높은지 확인)"""
        current_close = self.c(code, m)
        avg_close = self.avg(code, self.c, period, m)
        
        return current_close > avg_close
    
    def is_downtrend(self, code: str, period: int = 14, m: int = 0) -> bool:
        """하락 추세 여부 확인 (단순하게 종가가 이동평균보다 낮은지 확인)"""
        current_close = self.c(code, m)
        avg_close = self.avg(code, self.c, period, m)
        
        return current_close < avg_close
    
    def momentum(self, code: str, period: int = 10, m: int = 0) -> float:
        """모멘텀 계산 (현재 종가와 n기간 이전 종가의 차이)"""
        current = self.c(code, m)
        previous = self.c(code, m + period)
        
        return current - previous

    # 데이터 변환 및 집계 함수들
    def rate_of_change(self, code: str, period: int = 1, m: int = 0) -> float:
        """변화율 계산 (현재 값과 n기간 이전 값의 백분율 변화)"""
        current = self.c(code, m)
        previous = self.c(code, m + period)
        
        if previous == 0:
            return 0
        
        return ((current - previous) / previous) * 100
    
    def normalized_volume(self, code: str, period: int = 20, m: int = 0) -> float:
        """거래량을 평균 거래량 대비 비율로 정규화"""
        current_volume = self.v(code, m)
        avg_volume = self.avg(code, self.v, period, m)
        
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
    
    def streak_count(self, code: str, condition_func) -> int:
        """연속된 조건 만족 횟수 계산"""
        count = 0
        data = self._get_data(code)
        
        for i in range(len(data)):
            if condition_func(code, i):
                count += 1
            else:
                break
                
        return count
    
    def detect_pattern(self, code: str, pattern_func, length: int) -> bool:
        """특정 패턴 감지 (length 길이의 데이터에 pattern_func 적용)"""
        if len(self._get_data(code)) < length:
            return False
            
        # pattern_func에 데이터 전달하여 패턴 확인
        return pattern_func(code, length)
                
class ScriptManager:
    """
    투자 스크립트 관리 및 실행 클래스 (확장 버전)
    
    사용자 스크립트 실행, 검증, 관리하고 사용자 함수를 지원합니다.
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
            user_funcs_file: 사용자 함수 저장 파일 경로
        """
        self.script_file = script_file
        self.scripts = {}  # {name: {script: str, vars: dict, type: str, desc: str}}
        self.user_funcs = {}  # {name: {script: str, vars: dict, type: str, desc: str}}
        self.chart_manager = ChartManager()  # 실행 시 주입
        self._running_scripts = set()  # 실행 중인 스크립트 추적
        self._compiled_scripts = {}  # 컴파일된 스크립트 캐시 {name: code_obj}
        
        import sys
        sys.excepthook = self._global_exception_handler
        # 파일에서 스크립트와 사용자 함수 로드
        self._load_scripts()
    
    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """예상치 못한 예외에 대한 글로벌 핸들러"""
        # 로그에만 기록하고 GUI 팝업 방지
        logging.error("미처리 예외:", exc_info=(exc_type, exc_value, exc_traceback))

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
    
    def get_script(self, name: str):
        """이름으로 스크립트 가져오기"""
        return self.scripts.get(name, {})
    
    def set_scripts(self, scripts: dict):
        """스크립트 전체 설정 및 저장
        
        Args:
            scripts: {name: {script: str, vars: dict}} 형식의 스크립트 사전
        
        Returns:
            bool: 저장 성공 여부
        """
        # 모든 스크립트 유효성 검사
        valid_scripts = {}
        for name, script_data in scripts.items():
            result = self.run_script('005930', name, check_only=True, script_data=script_data)
            if result['success']:   
                script_data['script'] = script_data['script'].replace('\n\n', '\n')
                script_data['type'] = self.get_script_type(result['result'])
                valid_scripts[name] = script_data
            else:
                logging.warning(f"유효하지 않은 스크립트: {name} - {result['error']}")
        
        self.scripts = valid_scripts
        # 컴파일된 스크립트 캐시 초기화
        self._compiled_scripts = {}
        return self._save_scripts()
    
    def get_script_type(self, result):
        if result is None: return 'none'
        elif isinstance(result, bool): return 'bool'
        elif isinstance(result, float): return 'float'
        elif isinstance(result, int): return 'int'
        elif isinstance(result, str): return 'str'
        elif isinstance(result, list): return 'list'
        elif isinstance(result, dict): return 'dict'
        elif isinstance(result, tuple): return 'tuple'
        elif isinstance(result, set): return 'set'
        else: return type(result).__name__
                    
    def set_script(self, name: str, script: str, vars: dict = None, desc: str = ''):
        """단일 스크립트 설정 및 저장
        
        Args:
            name: 스크립트 이름
            script: 스크립트 코드
            type: 스크립트 리턴 타입
            vars: 스크립트에서 사용할 변수 사전
            desc: 스크립트 설명
        
        Returns:
            type: False=실패, str=성공(str=result type)
        """
        script_data = {'script': script, 'vars': vars or {}}
        result = self.run_script('005930', name, check_only=True, script_data=script_data)
        
        if not result['success']:
            logging.warning(f"유효하지 않은 스크립트: {name} - {result['error']}")
            return False
        script_data['script'] = script_data['script'].replace('\n\n', '\n')
        script_data['type'] = self.get_script_type(result['result'])
        script_data['desc'] = desc
        self.scripts[name] = script_data
        # 컴파일된 스크립트 캐시에서 제거 (재컴파일 필요)
        if name in self._compiled_scripts:
            del self._compiled_scripts[name]
        
        ret = self._save_scripts()
        if ret: return script_data['type']
        return False
    
    def delete_script(self, name: str):
        """스크립트 삭제
        
        Args:
            name: 삭제할 스크립트 이름
        
        Returns:
            bool: 삭제 성공 여부
        """
        if name in self.scripts:
            del self.scripts[name]
            # 컴파일된 스크립트 캐시에서도 제거
            if name in self._compiled_scripts:
                del self._compiled_scripts[name]
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
        return name.isidentifier()  # Python 3.x에서는 isidentifier 메서드가 있습니다.
            
    def run_script(self, code: str, name: str, check_only=False, script_data=None, is_sub_call=False, kwargs={}):
        """스크립트 또는 사용자 함수 실행/검사
        
        Args:
            code: 종목코드
            name: 스크립트/함수 이름
            check_only: 실행하지 않고 검사만 할지 여부 (실제로는 실행도 함)
            script_data: 직접 제공하는 스크립트/함수 데이터 (검사용)
            is_sub_call: 다른 스크립트에서 호출된 것인지 여부
            kwargs: 스크립트/함수에 전달할 추가 변수들 (사전 형태)
            
        Returns:
            dict: {
                'success': bool,    # 성공 여부
                'result': Any,      # 스크립트/함수 실행 결과 (성공 시)
                'error': str,       # 오류 메시지 (실패 시)
                'exec_time': float, # 실행 시간 (초)
                'log': str          # 상세 로그 (실패 시)
            }
        """
        start_time = time.time()
        result_dict = {
            'success': False,
            'result': None,  # 스크립트/함수 모두 기본값은 None
            'error': None,
            'exec_time': 0,
            'log': ''
        }
        
        # 엔티티 구분 (로깅용)
        entity_type = "스크립트"
        if not self._is_valid_identifier(name):
            result_dict['error'] = f"유효하지 않은 스크립트 이름: {name}"
            return result_dict
        
        # 순환 참조 방지 (모든 유형에 적용)
        script_key = f"{name}:{code}"
        if script_key in self._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_key}"
            return result_dict
        
        # 실행 중인 스크립트/함수에 추가
        self._running_scripts.add(script_key)
        
        try:
            if check_only: code = '005930'
            # 스크립트/함수 데이터 가져오기
            if script_data is None:
                script_data = self.get_script(name)
            
            script = script_data.get('script', '')
            vars_dict = script_data.get('vars', {}).copy()  # 기본값
            
            # vars_dict를 kwargs로 전달
            combined_kwargs = vars_dict.copy()
            combined_kwargs.update(kwargs)
            
            if not script:
                result_dict['error'] = f"{entity_type} 없음: {name}"
                return result_dict
            
            # 1. 구문 분석 검사
            try:
                # 스크립트/함수를 감싸서 실행하기 위한 코드 생성
                wrapped_script = f"""
def execute_script(ChartManager, code, kwargs):
    try:
{self._indent_script(script, indent=8)}  # 8칸 들여쓰기 적용
        return result if 'result' in locals() else None
    except Exception as e:
        import logging, traceback
        tb = traceback.format_exc()
        logging.error(f"내부 스크립트 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
        raise  # 오류를 전파하여 감지할 수 있도록 함

try:
    result = execute_script(ChartManager, "{code}", {repr(combined_kwargs)})
except Exception as e:
    import logging, traceback
    tb = traceback.format_exc()
    logging.error(f"스크립트 실행 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
    raise  # 오류를 상위로 전파
"""
                #logging.debug(f'스크립트: \n{script}\n변수: {combined_kwargs}')
                try:
                    ast.parse(wrapped_script)
                except SyntaxError as e:
                    result_dict['error'] = f"구문 오류 ({name} {entity_type} {e.lineno}행): {e}"
                    logging.error(result_dict['error'])
                    return result_dict
                    
            except Exception as e:
                # 그 외 모든 예외도 로그로만 처리
                result_dict['error'] = f"스크립트 준비 오류 ({name} {entity_type}): {type(e).__name__} - {e}"
                logging.error(result_dict['error'])
                return result_dict
            
            # 2. 보안 검증 (금지된 구문 확인)
            try:
                if self._has_forbidden_syntax(script):
                    result_dict['error'] = f"보안 위반 코드 포함 ({name} {entity_type})"
                    return result_dict
                
            except Exception as e:
                result_dict['error'] = f"보안 검사 오류: {type(e).__name__} - {e}"
                logging.error(result_dict['error'])
                return result_dict
            
            # 3. 차트 데이터 준비 상태 확인 (실행 모드에서만)
            if not is_sub_call:  # check_only에 관계없이 데이터 준비 (런타임 오류 확인을 위해)
                try:
                    has_data = self._check_chart_data_ready(code)
                    
                    if not has_data:
                        # 데이터 준비 시도
                        self._prepare_chart_data(code)
                        # 다시 확인
                        has_data = self._check_chart_data_ready(code)
                        if not has_data:
                            result_dict['error'] = f"차트 데이터 준비 실패: {code}"
                            return result_dict
                except Exception as e:
                    result_dict['error'] = f"데이터 준비 오류: {type(e).__name__} - {e}"
                    logging.error(result_dict['error'])
                    return result_dict
            
            # 4. 실행 환경 준비
            try:
                globals_dict = self._prepare_execution_globals()
                locals_dict = {}
            except Exception as e:
                result_dict['error'] = f"실행 환경 준비 오류: {type(e).__name__} - {e}"
                logging.error(result_dict['error'])
                return result_dict
            
            # 5. 스크립트/함수 컴파일 또는 캐시에서 가져오기
            try:

                cache_key = f"{script}_{name}"
                if check_only or script_data is not None:  # 테스트용이면 항상 새로 컴파일
                    code_obj = compile(wrapped_script, f"<{cache_key}>", 'exec')
                elif cache_key not in self._compiled_scripts:  # 아니면 캐시 사용
                    self._compiled_scripts[cache_key] = compile(wrapped_script, f"<{cache_key}>", 'exec')
                    code_obj = self._compiled_scripts[cache_key]
                else:
                    code_obj = self._compiled_scripts[cache_key]

            except Exception as e:
                result_dict['error'] = f"컴파일 오류: {type(e).__name__} - {e}"
                logging.error(result_dict['error'])
                return result_dict
            
            # 6. 실행 (check_only 모드에서도 반드시 실행하여 런타임 오류 확인)
            try:
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                
                # 실행 시간이 너무 오래 걸리면 경고
                if exec_time > 0.05:  # 50ms 이상 걸리면 경고
                    logging.warning(f"{entity_type} 실행 시간 초과 ({name}:{code}): {exec_time:.4f}초")
                
                # 실행 결과 가져오기
                script_result = locals_dict.get('result')
                
                result_dict['success'] = True
                result_dict['result'] = script_result
                result_dict['exec_time'] = exec_time
                
                # check_only 모드에서는 결과만 반환하고 실제 작업은 수행하지 않음
                return result_dict
                
            except Exception as e:
                tb = traceback.format_exc()
                error_msg = f"{entity_type} 실행 오류 ({name}:{code}): {type(e).__name__} - {e}"
                
                logging.error(f"{error_msg}\n{tb}")
                result_dict['log'] = tb
                result_dict['error'] = error_msg
                return result_dict
                
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if script_key in self._running_scripts:
                self._running_scripts.remove(script_key)
            
            # 실행 시간 기록
            result_dict['exec_time'] = time.time() - start_time
                
    def _prepare_execution_globals(self):
        """실행 환경의 글로벌 변수 준비"""
        try:
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
            
            # 글로벌 환경 설정
            globals_dict = {
                # Python 내장 함수들 (제한된 목록)
                **restricted_builtins,
                
                # 허용된 모듈들
                **modules,
                
                # 스크립트용 로깅 래퍼 함수들
                'debug': lambda msg, *args, **kwargs: logging.debug(f"[Script] {msg}", *args, **kwargs),
                'info': lambda msg, *args, **kwargs: logging.info(f"[Script] {msg}", *args, **kwargs),
                'warning': lambda msg, *args, **kwargs: logging.warning(f"[Script] {msg}", *args, **kwargs),
                'error': lambda msg, *args, **kwargs: logging.error(f"[Script] {msg}", *args, **kwargs),
                'critical': lambda msg, *args, **kwargs: logging.critical(f"[Script] {msg}", *args, **kwargs),
                
                # 차트 매니저
                'ChartManager': self.chart_manager.__class__,
                
                # 유틸리티 함수
                'loop': self._safe_loop,
            }
            
            # 모든 스크립트 추가 (사용자 함수 포함)
            for script_name, script_data in self.scripts.items():
                # 스크립트가 함수처럼 호출 가능하도록 래퍼 생성
                wrapper_code = f"""
def {script_name}(code, kwargs={{}}):
    # 스크립트를 함수로 실행
    result = run_script(code, '{script_name}', is_sub_call=True, kwargs=kwargs)
    return result['result'] if result['success'] else None
            """
            
                # 스크립트 래퍼 함수 컴파일 및 추가
                try:
                    exec(wrapper_code, globals_dict, globals_dict)
                except Exception as e:
                    logging.error(f"스크립트 래퍼 생성 오류 ({script_name}): {e}")
            
            # run_script 함수 추가
            globals_dict['run_script'] = lambda code, name, kwargs: self.run_script(code, name, is_sub_call=True, kwargs=kwargs)
            
            return globals_dict
        except Exception as e:
            logging.error(f"실행 환경 준비 오류: {e}")
            # 기본 환경 반환
            return {'ChartManager': self.chart_manager.__class__}
                        
    def _check_chart_data_ready(self, code):
        """차트 데이터가 준비되었는지 확인
        
        Args:
            code: 종목코드
        
        Returns:
            bool: 데이터가 준비되었으면 True
        """
        # 실제 구현에서는 ChartData 클래스를 사용해야 함
        # 예시 구현
        try:
            if not hasattr(self, '_chart_data_cache'):
                self._chart_data_cache = {}
            
            return code in self._chart_data_cache and self._chart_data_cache[code].get('ready', False)
        except Exception as e:
            logging.error(f"차트 데이터 확인 오류: {e}")
            return False
    
    def _prepare_chart_data(self, code):
        """차트 데이터 준비
        
        Args:
            code: 종목코드
        
        Returns:
            bool: 준비 성공 여부
        """
        # 실제 구현에서는 ChartData 클래스를 사용해야 함
        # 예시 구현
        try:
            if not hasattr(self, '_chart_data_cache'):
                self._chart_data_cache = {}
            
            # 데이터 준비 요청 로직
            self._chart_data_cache[code] = {'ready': True}
            return True
        except Exception as e:
            logging.error(f"차트 데이터 준비 오류: {e}")
            return False
        
    # ===== 스크립트 최적화 및 DLL 컴파일 관련 메서드 =====
    
    def export_compiled_script(self, name: str, output_dir='.'):
        """스크립트를 DLL 또는 pyc 형태로 컴파일 후 내보내기
        
        Args:
            name: 스크립트 이름
            output_dir: 출력 디렉토리
        
        Returns:
            dict: {
                'success': bool,  # 내보내기 성공 여부
                'path': str,      # 저장된 파일 경로 (성공 시)
                'error': str,     # 오류 메시지 (실패 시)
            }
        """
        result = {'success': False, 'path': None, 'error': None}
        
        try:
            # 스크립트 가져오기
            script_data = self.get_script(name)
            script = script_data.get('script', '')
            
            if not script:
                result['error'] = f"스크립트 없음: {name}"
                return result
            
            # .pyc 형태로 컴파일
            output_file = os.path.join(output_dir, f"{name}.pyc")
            
            # 컴파일
            code_obj = compile(script, f"<script_{name}>", 'exec')
            
            # .pyc 파일로 저장
            import marshal
            import struct
            import sys
            
            with open(output_file, 'wb') as fc:
                # 매직 넘버 (Python 버전별로 다름)
                fc.write(struct.pack('<I', int(sys.hexversion)))
                # 타임스탬프 (0으로 설정)
                fc.write(struct.pack('<I', 0))
                # 소스 크기 (0으로 설정)
                fc.write(struct.pack('<I', 0))
                # 컴파일된 코드 객체 저장
                marshal.dump(code_obj, fc)
            
            result['success'] = True
            result['path'] = output_file
            return result
        
        except Exception as e:
            result['error'] = f"컴파일 오류: {type(e).__name__} - {e}"
            return result
    
    def import_compiled_script(self, file_path, name=None):
        """컴파일된 스크립트 가져오기
        
        Args:
            file_path: 컴파일된 파일 경로
            name: 스크립트 이름 (None이면 파일명 사용)
        
        Returns:
            dict: {
                'success': bool,  # 가져오기 성공 여부
                'name': str,      # 스크립트 이름 (성공 시)
                'error': str,     # 오류 메시지 (실패 시)
            }
        """
        result = {'success': False, 'name': None, 'error': None}
        
        try:
            # 파일 이름에서 스크립트 이름 추출
            if name is None:
                name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 이미 존재하는지 확인
            if name in self.scripts:
                result['error'] = f"이미 존재하는 스크립트 이름: {name}"
                return result
            
            # .pyc 파일 로드
            import marshal
            import struct
            
            with open(file_path, 'rb') as fc:
                # 헤더 스킵 (매직 넘버, 타임스탬프, 소스 크기)
                fc.read(12)
                # 코드 객체 로드
                code_obj = marshal.load(fc)
            
            # 코드 객체 캐시에 저장
            self._compiled_scripts[name] = code_obj
            
            # 비어있는 스크립트로 등록 (런타임에만 사용)
            self.scripts[name] = {
                'script': '# 컴파일된 스크립트',
                'vars': {}
            }
            
            result['success'] = True
            result['name'] = name
            return result
        
        except Exception as e:
            result['error'] = f"가져오기 오류: {type(e).__name__} - {e}"
            return result
   
import os
import time
import hashlib
import marshal
import pickle
import importlib.util
import sys
import traceback
import ast
import re
import logging
from types import ModuleType, FunctionType
from typing import Dict, Set, Any, Tuple, Optional, Callable

class CompiledScriptCache:
    """컴파일된 스크립트 관리 클래스"""
    
    def __init__(self, cache_dir: str = dc.fp.cache_path):
        """초기화
        
        Args:
            cache_dir: 컴파일된 스크립트 캐시 디렉토리
        """
        self.cache_dir = cache_dir
        self.compiled_cache = {}  # 메모리 내 캐시 {name: code_obj}
        self.dependency_map = {}  # 의존성 맵 {name: set(dependencies)}
        self.hash_map = {}  # 스크립트 해시 맵 {name: hash_value}
        self.modules_cache = {}  # 로드된 모듈 캐시 {name: module}
        
        # # 캐시 디렉토리 생성
        # os.makedirs(cache_dir, exist_ok=True)

        # # ScriptManagerExtension.__init__ 메서드에서:
        # scripts_dir = os.path.dirname(dc.fp.scripts_file)
        # cache_dir = os.path.join(scripts_dir, "compiled_scripts")
    
    def get_script_hash(self, script: str) -> str:
        """스크립트의 해시값 계산
        
        Args:
            script: 스크립트 코드
            
        Returns:
            str: 해시값
        """
        return hashlib.md5(script.encode('utf-8')).hexdigest()
    
    def get_cache_path(self, name: str) -> str:
        """캐시 파일 경로 생성
        
        Args:
            name: 스크립트 이름
            
        Returns:
            str: 캐시 파일 경로
        """
        return os.path.join(self.cache_dir, f"{name}.pyc")
    
    def get_dependency_path(self, name: str) -> str:
        """의존성 파일 경로 생성
        
        Args:
            name: 스크립트 이름
            
        Returns:
            str: 의존성 파일 경로
        """
        return os.path.join(self.cache_dir, f"{name}.dep")
    
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
            
    def compile_script(self, name: str, script: str, script_names: Set[str]) -> bool:
        """스크립트 컴파일 및 캐싱
        
        Args:
            name: 스크립트 이름
            script: 스크립트 코드
            script_names: 시스템에 등록된 모든 스크립트 이름 집합
            
        Returns:
            bool: 컴파일 성공 여부
        """
        try:
            # 해시값 계산
            script_hash = self.get_script_hash(script)
            self.hash_map[name] = script_hash
            
            # 의존성 분석
            dependencies = self.analyze_dependencies(script, script_names)
            self.dependency_map[name] = dependencies
            
            # 스크립트 컴파일
            wrapped_script = f"""
def execute_script(ChartManager, code, kwargs):
{self._indent_script(script, indent=4)}
    return result if 'result' in locals() else None
"""
            code_obj = compile(wrapped_script, f"<{name}>", 'exec')
            
            # 메모리 캐시에 저장
            self.compiled_cache[name] = code_obj
            
            # 파일에 저장
            cache_path = self.get_cache_path(name)
            with open(cache_path, 'wb') as f:
                f.write(importlib.util.MAGIC_NUMBER)  # Python 매직 넘버
                f.write(b'\x00\x00\x00\x00')  # 타임스탬프 (0)
                f.write(b'\x00\x00\x00\x00')  # 소스 크기 (0)
                marshal.dump(code_obj, f)  # 코드 객체 저장
            
            # 의존성 정보 저장
            dep_path = self.get_dependency_path(name)
            with open(dep_path, 'wb') as f:
                pickle.dump({
                    'hash': script_hash,
                    'dependencies': dependencies
                }, f)
            
            return True
            
        except Exception as e:
            logging.error(f"스크립트 컴파일 오류: {e}", exc_info=True)
            return False
    
    def load_compiled_script(self, name: str) -> Optional[Any]:
        """컴파일된 스크립트 로드
        
        Args:
            name: 스크립트 이름
            
        Returns:
            Any: 컴파일된 코드 객체 또는 None (실패 시)
        """
        # 이미 메모리에 있으면 바로 반환
        if name in self.compiled_cache:
            return self.compiled_cache[name]
        
        # 파일에서 로드
        cache_path = self.get_cache_path(name)
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                # 매직 넘버, 타임스탬프, 소스 크기 스킵
                f.read(12)
                code_obj = marshal.load(f)
                
                # 메모리 캐시에 저장
                self.compiled_cache[name] = code_obj
                return code_obj
                
        except Exception as e:
            logging.error(f"컴파일된 스크립트 로드 오류: {e}")
            return None
    
    def get_affected_scripts(self, name: str) -> Set[str]:
        """특정 스크립트에 의존하는 모든 스크립트 찾기
        
        Args:
            name: 스크립트 이름
            
        Returns:
            Set[str]: 의존하는 스크립트 집합
        """
        affected = set()
        
        for script_name, deps in self.dependency_map.items():
            if name in deps:
                affected.add(script_name)
                # 재귀적으로 의존성 체크 (간접 의존성)
                affected.update(self.get_affected_scripts(script_name))
        
        return affected
    
    def invalidate_script(self, name: str) -> Set[str]:
        """스크립트 및 의존하는 모든 스크립트의 캐시 무효화
        
        Args:
            name: 스크립트 이름
            
        Returns:
            Set[str]: 무효화된 스크립트 집합
        """
        # 이 스크립트에 의존하는 모든 스크립트 찾기
        affected_scripts = self.get_affected_scripts(name)
        affected_scripts.add(name)  # 자기 자신도 포함
        
        # 메모리 캐시에서 제거
        for script_name in affected_scripts:
            if script_name in self.compiled_cache:
                del self.compiled_cache[script_name]
            if script_name in self.modules_cache:
                del self.modules_cache[script_name]
        
        return affected_scripts
    
    def clear_cache(self):
        """모든 캐시 초기화"""
        self.compiled_cache.clear()
        self.dependency_map.clear()
        self.hash_map.clear()
        self.modules_cache.clear()

# ScriptManager 클래스 확장 (기존 클래스에 통합)
class ScriptManagerExtension:
    """ScriptManager 클래스를 위한 확장 메서드"""
    
    def __init__(self):
        """초기화"""
        self.script_cache = CompiledScriptCache()
        self._precompiled_modules = {}  # 사전 컴파일된 모듈
    
    def init_script_compiler(self, script_manager):
        """스크립트 컴파일러 초기화
        
        Args:
            script_manager: ScriptManager 인스턴스
            
        Returns:
            bool: 초기화 성공 여부
        """
        try:
            # 모든 스크립트 컴파일
            all_scripts = script_manager.scripts
            script_names = set(all_scripts.keys())
            
            for name, script_data in all_scripts.items():
                script = script_data.get('script', '')
                self.script_cache.compile_script(name, script, script_names)
            
            logging.info(f"스크립트 컴파일러 초기화 완료: {len(all_scripts)}개 스크립트")
            return True
            
        except Exception as e:
            logging.error(f"스크립트 컴파일러 초기화 오류: {e}")
            return False
    
    def set_script_compiled(self, script_manager, name, script, vars=None, desc=''):
        """스크립트 설정 및 컴파일
        
        Args:
            script_manager: ScriptManager 인스턴스
            name: 스크립트 이름
            script: 스크립트 코드
            vars: 스크립트 변수
            desc: 스크립트 설명
            
        Returns:
            bool or str: 성공 시 스크립트 타입, 실패 시 False
        """
        # 기존 set_script 메서드 호출
        result = script_manager.set_script(name, script, vars, desc)
        
        if result:
            # 컴파일 및 캐싱
            script_names = set(script_manager.scripts.keys())
            self.script_cache.compile_script(name, script, script_names)
            
            # 의존하는 스크립트들 재컴파일
            affected = self.script_cache.invalidate_script(name)
            for affected_name in affected:
                if affected_name != name and affected_name in script_manager.scripts:
                    affected_script = script_manager.scripts[affected_name]['script']
                    self.script_cache.compile_script(affected_name, affected_script, script_names)
            
            logging.info(f"스크립트 컴파일 완료: {name} (영향받은 스크립트: {len(affected)-1}개)")
        
        return result
    
    def delete_script_compiled(self, script_manager, name):
        """컴파일된 스크립트 삭제
        
        Args:
            script_manager: ScriptManager 인스턴스
            name: 스크립트 이름
            
        Returns:
            bool: 삭제 성공 여부
        """
        # 의존하는 스크립트들 확인
        affected = self.script_cache.get_affected_scripts(name)
        if affected:
            logging.warning(f"'{name}' 스크립트를 삭제하면 다음 스크립트들에 영향: {', '.join(affected)}")
        
        # 기존 delete_script 메서드 호출
        result = script_manager.delete_script(name)
        
        if result:
            # 캐시 무효화
            self.script_cache.invalidate_script(name)
            
            # 캐시 파일 삭제
            try:
                cache_path = self.script_cache.get_cache_path(name)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                
                dep_path = self.script_cache.get_dependency_path(name)
                if os.path.exists(dep_path):
                    os.remove(dep_path)
            except Exception as e:
                logging.error(f"캐시 파일 삭제 오류: {e}")
        
        return result
    
    def run_script_compiled(self, script_manager, code, name, check_only=False, script_data=None, is_sub_call=False, kwargs={}):
        """컴파일된 스크립트 실행
        
        Args:
            script_manager: ScriptManager 인스턴스
            code: 종목코드
            name: 스크립트 이름
            check_only: 검사만 수행
            script_data: 직접 제공하는 스크립트 데이터
            is_sub_call: 다른 스크립트에서 호출 여부
            kwargs: 추가 매개변수
            
        Returns:
            dict: 실행 결과
        """
        start_time = time.time()
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'exec_time': 0,
            'log': ''
        }
        
        # 순환 참조 방지
        script_key = f"{name}:{code}"
        if script_key in script_manager._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_key}"
            return result_dict
        
        # 실행 중인 스크립트에 추가
        script_manager._running_scripts.add(script_key)
        
        try:
            if check_only: 
                code = '005930'
            
            # 스크립트 데이터 가져오기
            if script_data is None:
                script_data = script_manager.get_script(name)
            
            script = script_data.get('script', '')
            vars_dict = script_data.get('vars', {}).copy()
            
            combined_kwargs = vars_dict.copy()
            combined_kwargs.update(kwargs)
            
            if not script:
                result_dict['error'] = f"스크립트 없음: {name}"
                return result_dict
            
            # 1. 구문 분석 및 보안 검사는 기존 메서드와 동일
            if check_only or script_data is not None:
                # 새 스크립트나 수정된 스크립트 검사
                try:
                    # 구문 분석
                    ast.parse(script)
                    
                    # 보안 검사
                    if script_manager._has_forbidden_syntax(script):
                        result_dict['error'] = f"보안 위반 코드 포함: {name}"
                        return result_dict
                except SyntaxError as e:
                    result_dict['error'] = f"구문 오류: {e}"
                    return result_dict
            
            # 2. 차트 데이터 준비
            if not is_sub_call:
                try:
                    has_data = script_manager._check_chart_data_ready(code)
                    
                    if not has_data:
                        script_manager._prepare_chart_data(code)
                        has_data = script_manager._check_chart_data_ready(code)
                        if not has_data:
                            result_dict['error'] = f"차트 데이터 준비 실패: {code}"
                            return result_dict
                except Exception as e:
                    result_dict['error'] = f"데이터 준비 오류: {e}"
                    return result_dict
            
            # 3. 실행 환경 준비
            try:
                globals_dict = script_manager._prepare_execution_globals()
                locals_dict = {}
            except Exception as e:
                result_dict['error'] = f"실행 환경 준비 오류: {e}"
                return result_dict
            
            # 4. 컴파일된 스크립트 실행 (여기서 최적화)
            try:
                # 테스트 모드이거나 직접 제공된 스크립트인 경우
                if check_only or script_data is not None:
                    # 런타임 테스트를 위해 새로 컴파일
                    wrapped_script = f"""
def execute_script(ChartManager, code, kwargs):
    try:
{script_manager._indent_script(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import logging, traceback
        tb = traceback.format_exc()
        logging.error(f"내부 스크립트 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
        raise

try:
    result = execute_script(ChartManager, "{code}", {repr(combined_kwargs)})
except Exception as e:
    import logging, traceback
    tb = traceback.format_exc()
    logging.error(f"스크립트 실행 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
    raise
"""
                    code_obj = compile(wrapped_script, f"<{name}_test>", 'exec')
                else:
                    # 캐시된 컴파일 코드 사용
                    code_obj = self.script_cache.load_compiled_script(name)
                    
                    # 캐시에 없으면 새로 컴파일
                    if code_obj is None:
                        script_names = set(script_manager.scripts.keys())
                        self.script_cache.compile_script(name, script, script_names)
                        code_obj = self.script_cache.load_compiled_script(name)
                        
                        if code_obj is None:
                            # 여전히 로드 실패 시 일반 컴파일 사용
                            wrapped_script = f"""
def execute_script(ChartManager, code, kwargs):
    try:
{script_manager._indent_script(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import logging, traceback
        tb = traceback.format_exc()
        logging.error(f"내부 스크립트 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
        raise

try:
    result = execute_script(ChartManager, "{code}", {repr(combined_kwargs)})
except Exception as e:
    import logging, traceback
    tb = traceback.format_exc()
    logging.error(f"스크립트 실행 오류: {{type(e).__name__}} - {{e}}\\n{{tb}}")
    raise
"""
                            code_obj = compile(wrapped_script, f"<{name}>", 'exec')
                
                # 코드 실행
                exec(code_obj, globals_dict, locals_dict)
                
                # 실행 결과 가져오기
                script_result = locals_dict.get('result')
                
                result_dict['success'] = True
                result_dict['result'] = script_result
                result_dict['exec_time'] = time.time() - start_time
                
                return result_dict
                
            except Exception as e:
                tb = traceback.format_exc()
                error_msg = f"스크립트 실행 오류 ({name}:{code}): {type(e).__name__} - {e}"
                
                logging.error(f"{error_msg}\n{tb}")
                result_dict['log'] = tb
                result_dict['error'] = error_msg
                return result_dict
                
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if script_key in script_manager._running_scripts:
                script_manager._running_scripts.remove(script_key)
            
            # 실행 시간 기록
            result_dict['exec_time'] = time.time() - start_time


# ScriptManager 클래스를 확장하는 메서드
def enhance_script_manager(script_manager):
    """기존 ScriptManager 클래스를 확장하여 컴파일 기능 추가
    
    Args:
        script_manager: 확장할 ScriptManager 인스턴스
        
    Returns:
        bool: 확장 성공 여부
    """
    try:
        # 확장 클래스 인스턴스 생성
        extension = ScriptManagerExtension()
        
        # 메서드 연결
        script_manager.init_script_compiler = lambda: extension.init_script_compiler(script_manager)
        script_manager.set_script_compiled = lambda name, script, vars=None, desc='': extension.set_script_compiled(script_manager, name, script, vars, desc)
        script_manager.delete_script_compiled = lambda name: extension.delete_script_compiled(script_manager, name)
        script_manager.run_script_compiled = lambda code, name, check_only=False, script_data=None, is_sub_call=False, kwargs={}: extension.run_script_compiled(script_manager, code, name, check_only, script_data, is_sub_call, kwargs)
        
        # 스크립트 캐시 참조 추가
        script_manager.script_cache = extension.script_cache
        
        # 초기화
        script_manager.init_script_compiler()
        
        logging.info("ScriptManager 컴파일 기능 확장 완료")
        return True
        
    except Exception as e:
        logging.error(f"ScriptManager 확장 오류: {e}", exc_info=True)
        return False


# 사용 예시
"""
# ScriptManager 인스턴스 생성 후 확장 적용
script_manager = ScriptManager()
enhance_script_manager(script_manager)

# 컴파일된 스크립트 실행 (기존 run_script 대신 사용)
result = script_manager.run_script_compiled('005930', 'my_script')

# 스크립트 추가/수정 (컴파일 포함)
script_manager.set_script_compiled('my_script', 'result = dy.c(code) > 50000')

# 스크립트 삭제 (컴파일 캐시도 함께 삭제)
script_manager.delete_script_compiled('my_script')
"""

