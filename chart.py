from public import gm, dc
from classes import la
from typing import Dict, List, Any, Union, Optional, Tuple
from datetime import datetime
import json
import numpy as np
import pandas as pd
import logging
from threading import Lock, Thread
import time
import ast
import traceback
import re
import math
import queue
class ChartData:

    """차트 데이터를 관리하는 싱글톤 클래스"""
    _instance = None
    _lock = Lock()  # 멀티스레드 환경을 위한 락
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChartData, cls).__new__(cls)
            cls._instance._data = {}  # {code: {cycle: data}}
            cls._instance._requests = {}  # {code: timestamp} - 요청 중복 방지용
            cls._instance._is_working = False
            cls._instance._update_queue = queue.Queue()  # 가격 업데이트 큐
            cls._instance._worker_thread = None #threading.Thread(target=cls._worker_process)
            cls._instance._running = False
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._start_worker()

    def _start_worker(self):
        """업데이트 워커 스레드 시작"""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return  # 이미 실행 중이면 무시
        
        self._running = True
        self._worker_thread = Thread(target=self._update_worker, daemon=True)
        self._worker_thread.start()
        logging.info("차트 데이터 업데이트 워커 스레드 시작")
    
    def _stop_worker(self):
        """업데이트 워커 스레드 중지"""
        self._running = False
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)  # 최대 2초 대기
            if self._worker_thread.is_alive():
                logging.warning("업데이트 워커 스레드 종료 대기 시간 초과")
            self._worker_thread = None
    
    def _update_worker(self):
        """업데이트 큐에서 요청을 읽어 처리하는 워커 스레드"""
        while self._running:
            try:
                # 큐에서 요청 가져오기 (최대 0.1초 대기)
                try:
                    if self._is_working: 
                        time.sleep(0.01)
                        continue
                    update_params = self._update_queue.get(timeout=0.1)
                except queue.Empty:
                    continue  # 큐가 비어있으면 다음 반복으로
                
                # 업데이트 요청 처리
                try:
                    code, price, volume, amount, datetime_str = update_params
                    self.update_price(code, price, volume, amount, datetime_str)
                except Exception as e:
                    logging.error(f"차트 데이터 업데이트 오류: {e}", exc_info=True)
                finally:
                    # 작업 완료 표시
                    self._update_queue.task_done()
            
            except Exception as e:
                logging.error(f"업데이트 워커 스레드 오류: {e}", exc_info=True)
                time.sleep(0.01)  # 오류 발생 시 잠시 대기
    
    def queue_update(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """가격 업데이트 요청을 큐에 추가 (외부에서 호출하는 메서드)"""
        self._update_queue.put((code, price, volume, amount, datetime_str))
        
        # 워커 스레드가 실행 중이 아니면 시작
        if not self._running or self._worker_thread is None or not self._worker_thread.is_alive():
            self._start_worker()

    def update_price(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """실시간 가격 정보 업데이트 (사용 빈도 최적화 버전)"""
        try:
            self._is_working = True
            # 해당 종목 차트 데이터가 없으면 초기화 (1분봉과 일봉 함께 로드)
            if code not in self._data:
                self._init_chart_data(code)
            
            # 1분봉 업데이트
            minute_data = self._data[code].get('mi1', [])
            
            datetime_str = datetime.now().strftime('%Y%m%d%H%M%S')

            # 데이터가 없거나 새로운 분에 진입한 경우 새 봉 생성
            if not minute_data or self._is_new_minute(minute_data[0]['체결시간'], datetime_str):
                # 새로운 1분봉 추가
                new_candle = {
                    '종목코드': code,
                    '체결시간': datetime_str[:12] + '00',  # 분 단위로 맞춤
                    '현재가': price,
                    '시가': price,
                    '고가': price,
                    '저가': price,
                    '거래량': volume,
                    '거래대금': amount
                }
                minute_data.insert(0, new_candle)
            else:
                # 기존 1분봉 업데이트
                current = minute_data[0]
                current['현재가'] = price
                current['고가'] = max(current['고가'], price)
                current['저가'] = min(current['저가'], price)
                current['거래량'] = volume
                current['거래대금'] = amount
            
            # 업데이트된 데이터 저장
            self._data[code]['mi1'] = minute_data
            
            # 가장 많이 사용하는 3분봉과 일부 다른 주기 업데이트
            # 사용 빈도에 따라 선택적으로 업데이트
            # 3분봉은 항상 업데이트 (80% 사용 빈도)
            self._update_minute_chart(code, 3, datetime_str)
            
            # 다른 주기 분봉 업데이트 (필요한 경우에만)
            current_minute = int(datetime_str[8:10]) * 60 + int(datetime_str[10:12])
            # 5분이 시작될 때만 5분봉 업데이트 (리소스 최적화)
            if current_minute % 5 == 0 and 'mi5' in self._data.get(code, {}):
                self._update_minute_chart(code, 5, datetime_str)
            # 10분이 시작될 때만 10분봉 업데이트
            if current_minute % 10 == 0 and 'mi10' in self._data.get(code, {}):
                self._update_minute_chart(code, 10, datetime_str)
            # 15분이 시작될 때만 15분봉 업데이트
            if current_minute % 15 == 0 and 'mi15' in self._data.get(code, {}):
                self._update_minute_chart(code, 15, datetime_str)
            # 30분이 시작될 때만 30분봉 업데이트
            if current_minute % 30 == 0 and 'mi30' in self._data.get(code, {}):
                self._update_minute_chart(code, 30, datetime_str)
            # 60분이 시작될 때만 60분봉 업데이트
            if current_minute % 60 == 0 and 'mi60' in self._data.get(code, {}):
                self._update_minute_chart(code, 60, datetime_str)
            # 일봉 업데이트 (당일 데이터) - 19% 사용 빈도
            if 'dy' in self._data.get(code, {}):
                self._update_day_chart(code, price, volume, amount, datetime_str)
        except Exception as e:
            logging.error(f"차트 데이터 업데이트 오류: {e}", exc_info=True)
        finally:
            self._is_working = False

    def _init_chart_data(self, code: str):
        """종목코드에 대한 차트 데이터 초기화 (1분봉과 일봉 함께 요청)"""
        self._data[code] = {}
        
        # 서버에서 기본 데이터 가져오기 (중복 요청 방지)
        current_time = time.time()
        if code in self._requests and current_time - self._requests[code] < 1.0:
            # 최근 1초 내에 요청된 경우 중복 요청 방지
            logging.debug(f"중복 요청 방지: {code}")
            return
        
        self._requests[code] = current_time
        
        # 1분봉과 일봉 데이터를 동시에 가져오기
        minute_data = self._get_chart_data(code, 'mi', 1)
        day_data = self._get_chart_data(code, 'dy')
        
        # 데이터 저장
        if minute_data:
            self._data[code]['mi1'] = minute_data
            # 1분봉 데이터로부터 3분봉 즉시 생성 (가장 많이 사용하는 주기)
            self._data[code]['mi3'] = self._aggregate_minute_data(minute_data, 3)
            
        if day_data:
            self._data[code]['dy'] = day_data
    
    def _is_new_minute(self, last_time: str, current_time: str) -> bool:
        """새로운 분봉이 시작되었는지 확인"""
        # 시간 형식: YYYYMMDDHHmm
        if len(last_time) >= 12 and len(current_time) >= 12:
            return last_time[:12] != current_time[:12]
        return True
    
    def _update_minute_chart(self, code: str, tick: int, datetime_str: str):
        """특정 tick 주기의 분봉 업데이트 (항상 1분봉 데이터로부터 생성)"""
        # 1분봉 데이터 필요
        minute_data = self._data[code].get('mi1', [])
        if not minute_data:
            return
        
        tick_key = f'mi{tick}'
        
        # 새 틱 차트 생성 필요 여부 확인
        if not datetime_str:
            datetime_str = datetime.now().strftime('%Y%m%d%H%M%S')

        current_minute = int(datetime_str[8:10]) * 60 + int(datetime_str[10:12])
        is_new_tick = current_minute % tick == 0
        
        # 3분봉 특별 처리 (가장 많이 사용하는 주기)
        is_three_minute = (tick == 3)
        
        # 해당 틱 데이터가 없으면 1분봉으로부터 생성 (서버 요청 최소화)
        if tick_key not in self._data[code]:
            self._data[code][tick_key] = self._aggregate_minute_data(minute_data, tick)
        elif is_new_tick and datetime_str[12:14] == '00':  # 정확히 틱 시작점
            # 기존 데이터 있고 새 틱 시작이면 새 봉 추가
            current = minute_data[0]
            tick_data = self._data[code][tick_key]
            
            new_candle = {
                '종목코드': code,
                '체결시간': datetime_str[:12] + '00',
                '현재가': current['현재가'],
                '시가': current['시가'],
                '고가': current['고가'],
                '저가': current['저가'],
                '거래량': current['거래량'],
                '거래대금': current['거래대금']
            }
            tick_data.insert(0, new_candle)
            self._data[code][tick_key] = tick_data
        else:
            # 현재 진행 중인 틱 업데이트
            if self._data[code][tick_key]:
                current_minute = int(datetime_str[8:10]) * 60 + int(datetime_str[10:12])
                tick_start = (current_minute // tick) * tick
                tick_time = datetime_str[:8] + f"{tick_start//60:02d}{tick_start%60:02d}00"
                
                # 최신 틱 찾기
                for i, candle in enumerate(self._data[code][tick_key]):
                    if candle['체결시간'] == tick_time:
                        # 현재 틱 업데이트
                        current = minute_data[0]
                        candle['현재가'] = current['현재가']
                        candle['고가'] = max(candle['고가'], current['현재가'])
                        candle['저가'] = min(candle['저가'], current['현재가'])
                        # 거래량은 누적값이므로 정확한 업데이트가 필요
                        if is_three_minute:  # 3분봉은 중요하므로 정확한 거래량 계산
                            # 1분봉 데이터에서 현재 틱에 해당하는 기간의 거래량 합산
                            total_volume = 0
                            for j in range(min(tick, len(minute_data))):
                                m_time = minute_data[j]['체결시간']
                                m_minute = int(m_time[8:10]) * 60 + int(m_time[10:12])
                                if tick_start <= m_minute < tick_start + tick:
                                    total_volume += minute_data[j]['거래량']
                            candle['거래량'] = total_volume
                        break
    
    def _update_day_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """일봉 데이터 업데이트 (당일)"""
        day_key = 'dy'
        today = datetime_str[:8]  # YYYYMMDD
        
        # 일봉 데이터 확인
        if day_key not in self._data[code] or not self._data[code][day_key]:
            # 서버에서 일봉 데이터 가져오기
            day_data = self._get_chart_data(code, 'dy')
            if day_data:
                self._data[code][day_key] = day_data
            else:
                return
        
        # 당일 데이터 업데이트
        day_data = self._data[code][day_key]
        
        # 최신 일봉이 당일인지 확인
        if day_data and day_data[0]['일자'] == today:
            current = day_data[0]
            current['현재가'] = price
            current['고가'] = max(current['고가'], price)
            current['저가'] = min(current['저가'], price)
            current['거래량'] = volume
            current['거래대금'] = amount
        elif day_data:
            # 당일 데이터 없으면 추가
            new_day = {
                '종목코드': code,
                '일자': today,
                '현재가': price,
                '시가': price,
                '고가': price,
                '저가': price,
                '거래량': volume,
                '거래대금': amount
            }
            day_data.insert(0, new_day)
    
    def _aggregate_minute_data(self, minute_data: list, tick: int) -> list:
        """1분봉 데이터를 특정 tick으로 집계"""
        if not minute_data:
            return []
        
        result = []
        # 최근 데이터부터 처리 (인덱스 0이 최신)
        grouped_data = {}
        
        for candle in minute_data:
            dt_str = candle['체결시간']
            if len(dt_str) < 12:
                continue
                
            dt = datetime.strptime(dt_str[:12], '%Y%m%d%H%M')
            # tick 단위로 그룹화 (예: 5분봉이면 5의 배수 시간대로)
            minute = dt.hour * 60 + dt.minute
            tick_start = (minute // tick) * tick
            group_dt = dt.replace(hour=tick_start // 60, minute=tick_start % 60)
            group_key = group_dt.strftime('%Y%m%d%H%M')
            
            if group_key not in grouped_data:
                grouped_data[group_key] = {
                    '종목코드': candle['종목코드'],
                    '체결시간': group_key + '00',
                    '현재가': candle['현재가'],
                    '시가': candle['현재가'],
                    '고가': candle['현재가'],
                    '저가': candle['현재가'],
                    '거래량': candle['거래량'],
                    '거래대금': candle.get('거래대금', 0)
                }
            else:
                group = grouped_data[group_key]
                group['현재가'] = candle['현재가']  # 마지막 값이 종가
                group['고가'] = max(group['고가'], candle['고가'])
                group['저가'] = min(group['저가'], candle['저가'])
                # 첫 값을 시가로 유지 (이미 설정됨)
        
        # 정렬하여 결과 반환 (최신이 먼저)
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['체결시간'], reverse=True)
        return result
    
    def get_chart_data(self, code: str, cycle: str, tick: int = None) -> list:
        """특정 종목, 주기의 차트 데이터 반환 (외부용)
        사용 빈도를 고려한 최적화:
        - 분봉(mi)은 1분봉에서 파생 (서버 요청 최소화)
        - 일봉(dy)은 1분봉 요청 시 함께 처리
        - 주봉(wk)과 월봉(mo)은 요청 시에만 서버에 요청
        """
        with self._lock:
            # 분봉의 경우 특별 처리
            if cycle == 'mi':
                cycle_key = f'mi{tick}'
                
                # 데이터가 없으면 기본 데이터 먼저 가져옴
                if code not in self._data:
                    self._init_chart_data(code)  # 1분봉과 일봉 데이터 함께 가져옴
                
                # 1분봉 데이터는 있지만 요청한 tick의 분봉이 없는 경우
                if code in self._data and 'mi1' in self._data[code] and cycle_key not in self._data[code]:
                    # 분봉 데이터는 1분봉으로부터 생성 (서버 요청 없음)
                    minute_data = self._data[code]['mi1']
                    self._data[code][cycle_key] = self._aggregate_minute_data(minute_data, tick)
            
            # 일봉의 경우
            elif cycle == 'dy':
                # 데이터가 없으면 기본 데이터 가져옴
                if code not in self._data:
                    self._init_chart_data(code)
                
                # 일봉 데이터가 없으면 개별 요청
                if code in self._data and 'dy' not in self._data[code]:
                    day_data = self._get_chart_data(code, 'dy')
                    if day_data:
                        self._data[code]['dy'] = day_data
            
            # 주봉/월봉은 요청 시에만 서버에 요청 (드물게 사용됨)
            elif cycle in ['wk', 'mo']:
                if code not in self._data:
                    self._data[code] = {}
                
                if cycle not in self._data[code]:
                    data = self._get_chart_data(code, cycle)
                    if data:
                        self._data[code][cycle] = data
            
            # 데이터 반환 (cycle_key가 없을 경우 빈 리스트 반환)
            cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
            return self._data.get(code, {}).get(cycle_key, [])
    
    def _get_chart_data(self, code, cycle, tick=None):
        """서버에서 차트 데이터 가져오기 (기존 코드 유지, 데드락 방지 추가)"""
        #dict_list = la.answer('admin', 'com_get_chart_data', code, cycle, tick)
        dict_list = gm.admin.com_get_chart_data(code, cycle, tick)
        return dict_list
        # 이미 요청 중인지 확인하여 데드락 방지
        request_key = f"{code}_{cycle}_{tick}"
        try:
            current_time = time.time()
            
            if hasattr(self, '_active_requests') and request_key in self._active_requests:
                last_request_time = self._active_requests[request_key]
                # 5초 이상 경과한 요청은 타임아웃으로 간주하고 재시도
                if current_time - last_request_time < 5.0:
                    logging.debug(f"이미 요청 중인 데이터: {request_key}")
                    return []
            
            # 요청 시작 시간 기록
            if not hasattr(self, '_active_requests'):
                self._active_requests = {}
            self._active_requests[request_key] = current_time
            
            # 이하 원래 코드
            rqname = f'{dc.scr.차트종류[cycle]}챠트'
            trcode = dc.scr.챠트TR[cycle]
            screen = dc.scr.화면[rqname]
            date = datetime.now().strftime('%Y%m%d')

            if cycle == 'mi':
                input = {'종목코드':code, '틱범위': tick, '수정주가구분': 1}
                output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if cycle == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': 1}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': 1}
                output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            logging.debug(f'분봉 챠트 데이타 얻기: code:{code}, cycle:{cycle}, tick:{tick}')
            next = '0'
            all = False #if cycle in ['mi', 'dy'] else True
            dict_list = []
            while True:
                data, remain = gm.admin.com_SendRequest(rqname, trcode, input, output, next, screen, 'dict_list', 5)
                if data is None or len(data) == 0: break
                dict_list.extend(data)
                if not (remain and all): break
                next = '2'
            
            if not dict_list:
                logging.warning(f'챠트 데이타 얻기 실패: code:{code}, cycle:{cycle}, tick:{tick}, dict_list:"{dict_list}"')
                return []
            
            if cycle == 'mi':
                dict_list = [{
                    '종목코드': code,
                    '체결시간': item['체결시간'],
                    '현재가': abs(int(item['현재가'])),
                    '시가': abs(int(item['시가'])),
                    '고가': abs(int(item['고가'])),
                    '저가': abs(int(item['저가'])),
                    '거래량': abs(int(item['거래량'])),
                    '거래대금': 0#abs(int(item['거래대금'])),
                } for item in dict_list]
            else:
                dict_list = [{
                    '종목코드': code,
                    '일자': item['일자'],
                    '현재가': abs(int(item['현재가'])),
                    '시가': abs(int(item['시가'])),
                    '고가': abs(int(item['고가'])),
                    '저가': abs(int(item['저가'])),
                    '거래량': abs(int(item['거래량'])),
                    '거래대금': abs(int(item['거래대금'])),
                } for item in dict_list]
            
            return dict_list
            
        except Exception as e:
            logging.error(f'챠트 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []
        finally:
            # 요청 완료 시 활성 요청 목록에서 제거
            if hasattr(self, '_active_requests') and request_key in self._active_requests:
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
    # 허용 모듈 리스트 (클래스 속성)
    ALLOWED_MODULES = ['re', 'math', 'datetime', 'random', 'logging', 'json', 'collections']
    def __init__(self, script_file=dc.fp.script_file):
        self.script_file = script_file
        self.scripts = {}  # {name: {script: str, vars: dict}}
        self.chart_manager = None  # 실행 시 주입
        self._load_scripts()
        self._running_scripts = set()  # 실행 중인 스크립트 추적
    
    def _load_scripts(self):
        """스크립트 파일에서 스크립트 로드"""
        try:
            with open(self.script_file, 'r', encoding='utf-8') as f:
                self.scripts = json.load(f)
            logging.info(f"스크립트 {len(self.scripts)}개 로드 완료")
        except FileNotFoundError:
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
    
    def set_scripts(self, scripts: dict):
        """스크립트 전체 설정 및 저장"""
        # 모든 스크립트 유효성 검사
        valid_scripts = {}
        for name, script_data in scripts.items():
            if self.check_script(name, script_data.get('script', '')):
                valid_scripts[name] = script_data
            else:
                logging.warning(f"유효하지 않은 스크립트: {name}")
        
        self.scripts = valid_scripts
        return self._save_scripts()
    
    def get_scripts(self):
        """저장된 모든 스크립트 반환"""
        return self.scripts
    
    def set_script(self, name: str, script: str, vars: dict = None):
        """단일 스크립트 설정 및 저장"""
        if not self.check_script(name, {'script': script, 'vars': vars}):
            logging.warning(f"유효하지 않은 스크립트: {name}")
            return False
        
        self.scripts[name] = {
            'script': script,
            'vars': vars or {}
        }
        return self._save_scripts()
    
    def get_script(self, name: str):
        """이름으로 스크립트 가져오기"""
        return self.scripts.get(name, {})
    
    def check_script(self, name: str, script_data: dict = None) -> bool:
        """스크립트 구문 및 실행 유효성 검사"""
        if script_data is None:
            script_data = self.scripts.get(name, {})

        script = script_data.get('script', '')
        vars_dict = script_data.get('vars', {})

        if not script:
            logging.warning(f"스크립트가 비어있음: {name}")
            return False
        
        # 1. 구문 분석 검사
        try:
            ast.parse(script)
        except SyntaxError as e:
            line_no = e.lineno
            logging.error(f"구문 오류 ({name} 스크립트 {line_no}행): {e}")
            return False
        
        # 2. 보안 검증 (금지된 구문 확인)
        if self._has_forbidden_syntax(script):
            logging.error(f"보안 위반 코드 포함 ({name} 스크립트)")
            return False
        
        # 3. 가상 실행 테스트
        return self._test_execute_script(name, script, vars_dict)
    
    def _has_forbidden_syntax(self, script: str) -> bool:
        """금지된 구문이 있는지 확인"""
        allowed_patterns = '|'.join(self.ALLOWED_MODULES)
        forbidden_patterns = [
            r'import\s+(?!(' + allowed_patterns + ')$)',  # 허용된 모듈만 임포트 가능
            r'open\s*\(',  # 파일 열기 금지
            r'exec\s*\(',  # exec() 사용 금지
            r'eval\s*\(',  # eval() 사용 금지
            r'__import__',  # __import__ 사용 금지
            r'subprocess',  # subprocess 모듈 금지
            r'os\.',  # os 모듈 사용 금지
            r'sys\.',  # sys 모듈 사용 금지
            r'while\s+.*:',  # while 루프 금지 (무한 루프 방지)
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, script):
                return True
        return False
    
    def _safe_loop(self, iterable, func):
        """안전한 루프 실행 함수"""
        results = []
        for item in iterable:
            results.append(func(item))
        return results
    
    def _create_test_chart_manager(self):
        """테스트용 ChartManager 생성"""
        class TestChartManager:
            """테스트용 차트 매니저"""
            def __init__(self):
                self._test_data = {
                    '005930': [  # 삼성전자 가상 데이터
                        {'date': '20240101', 'open': 70000, 'high': 71000, 'low': 69000, 'close': 70500, 'volume': 1000000, 'amount': 70500000000},
                        {'date': '20240102', 'open': 70500, 'high': 72000, 'low': 70000, 'close': 71000, 'volume': 1200000, 'amount': 85200000000},
                        {'date': '20240103', 'open': 71000, 'high': 71500, 'low': 70000, 'close': 71200, 'volume': 900000, 'amount': 64080000000},
                    ]
                }
            
            # ChartManager 메서드들 구현
            def c(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('close', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def o(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('open', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def h(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('high', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def l(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('low', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def v(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('volume', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def a(self, code, n=0): return self._test_data.get(code, [{}])[min(n, len(self._test_data.get(code, [])) - 1)].get('amount', 0) if code in self._test_data and len(self._test_data[code]) > n else 0
            def time(self, n=0): return '090000' if n == 0 else f"{90000 + n * 100:06d}"  # 테스트용 시간값
            def today(self): return datetime.now().strftime('%Y%m%d')
            
            # 계산 함수들
            def ma(self, code, a, n, m=0, k='a'): return 10000.0
            def avg(self, code, a, n, m=0): return 10000.0
            def eavg(self, code, a, n, m=0): return 10000.0
            def wavg(self, code, a, n, m=0): return 10000.0
            def highest(self, code, a, n, m=0): return 10100.0
            def lowest(self, code, a, n, m=0): return 9800.0
            def stdev(self, code, a, n, m=0): return 100.0
            def sum(self, code, a, n, m=0): return 100000.0
            
            # 신호 함수들
            def cross_down(self, code, a, b): return False
            def cross_up(self, code, a, b): return True
            def bars_since(self, code, condition): return 5
            
            # 추가 함수들 (모두 기본값 반환)
            def min_value(self, a, b): return min(a, b)
            def max_value(self, a, b): return max(a, b)
            def pow(self, a, n): return a ** n
            def sqrt(self, a): return a ** 0.5 if a >= 0 else 0
            def log(self, a, base=10): return 1.0
            def exp(self, a): return 2.7
            def safe_div(self, a, b, default=0): return a / b if b != 0 else default
            def iif(self, condition, true_value, false_value): return true_value if condition else false_value
            def all_true(self, condition_list): return all(condition_list)
            def any_true(self, condition_list): return any(condition_list)
            
            # 보조지표 함수들
            def rsi(self, code, period=14, m=0): return 50.0
            def macd(self, code, fast=12, slow=26, signal=9, m=0): return (0.0, 0.0, 0.0)
            def bollinger_bands(self, code, period=20, std_dev=2, m=0): return (10200.0, 10000.0, 9800.0)
            def stochastic(self, code, k_period=14, d_period=3, m=0): return (50.0, 50.0)
            def atr(self, code, period=14, m=0): return 100.0
            
            # 캔들패턴 인식 함수들
            def is_doji(self, code, n=0, threshold=0.1): return False
            def is_hammer(self, code, n=0): return True
            def is_engulfing(self, code, n=0, bullish=True): return bullish
            
            # 추세 분석 함수들
            def is_uptrend(self, code, period=14, m=0): return True
            def is_downtrend(self, code, period=14, m=0): return False
            def momentum(self, code, period=10, m=0): return 100.0
            
            # 데이터 변환 함수들
            def rate_of_change(self, code, period=1, m=0): return 1.0
            def normalized_volume(self, code, period=20, m=0): return 1.0
            def accumulation(self, values): return [sum(values[:i+1]) for i in range(len(values))]
            def streak_count(self, code, condition_func): return 3
            def detect_pattern(self, code, pattern_func, length): return True
        
        return TestChartManager()
    
    def _test_execute_script(self, name: str, script: str, vars_dict: dict = None) -> bool:
        """테스트 환경에서 스크립트 실행 시도"""
        try:
            # 가상 환경에서 안전하게 실행
            # 테스트용 ChartManager 생성
            test_cm = self._create_test_chart_manager()
            
            # 테스트용 글로벌/로컬 환경 설정
            globals_dict = {
                # Python 내장 함수들
                'range': range,
                'len': len,
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs,
                'all': all,
                'any': any,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                
                # 모듈들
                'math': math,
                'logging': logging,
                'datetime': datetime,
                
                # 차트 매니저
                'ChartManager': lambda cycle='dy', tick=1: test_cm,
                
                'code': '005930',

                # 유틸리티 함수
                'loop': self._safe_loop,
                'run_script': lambda sub_name: True
            }
                
            # 변수 추가
            for var_name, var_value in vars_dict.items():
                globals_dict[var_name] = var_value
            
            
            # 컴파일 및 제한된 실행
            code_obj = compile(script, f"<script_{name}>", 'exec')
            
            # 실행 시간 제한
            start_time = time.time()
            locals_dict = {}
            
            try:
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                if exec_time > 0.1:  # 0.1초 초과 실행 시 경고
                    logging.warning(f"스크립트 실행 시간 초과 ({name}): {exec_time:.4f}초")
                return True
            except Exception as e:
                logging.error(f"스크립트 실행 오류 ({name}): {type(e).__name__} - {e}")
                return False
        except Exception as e:
            logging.error(f"스크립트 테스트 중 예상치 못한 오류 ({name}): {e}")
            return False
    
    def run_script(self, name: str, code: str, is_sub_call: bool = False):
        """스크립트 실행
        name: 스크립트 이름
        code: 종목코드
        is_sub_call: 다른 스크립트에서 호출된 것인지 여부
        
        Returns: bool - 스크립트 실행 결과 (성공/실패)
        """
        # 순환 참조 방지
        script_key = f"{name}:{code}"
        if script_key in self._running_scripts:
            logging.warning(f"순환 참조 감지: {script_key}")
            return False
        
        # 실행 중인 스크립트에 추가
        self._running_scripts.add(script_key)
        
        try:
            # 스크립트 가져오기
            script_data = self.get_script(name)
            script = script_data.get('script', '')
            vars_dict = script_data.get('vars', {})
            
            if not script:
                logging.warning(f"스크립트 없음: {name}")
                self._running_scripts.remove(script_key)
                return False
            
            # 차트 매니저 생성 및 데이터 준비 상태 확인
            if not self.chart_manager:
                self.chart_manager = ChartManager()
            
            # 차트 데이터 준비 상태 확인 (3분봉과 일봉 데이터가 있는지 확인)
            chart_data = ChartData()  # 싱글톤이므로 항상 동일 인스턴스 반환
            has_data = self._check_chart_data_ready(chart_data, code)
            
            if not has_data and not is_sub_call:
                logging.warning(f"차트 데이터 준비되지 않음: {code}")
                # 데이터 준비 시도
                self._prepare_chart_data(chart_data, code)
                # 다시 확인
                has_data = self._check_chart_data_ready(chart_data, code)
                if not has_data:
                    logging.error(f"차트 데이터 준비 실패: {code}")
                    self._running_scripts.remove(script_key)
                    return False
            
            # 글로벌 환경 설정
            globals_dict = {
                # Python 내장 함수들
                'range': range,
                'len': len,
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs,
                'all': all,
                'any': any,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                
                # 모듈들
                'math': math,
                'logging': logging,
                'datetime': datetime,
                
                # 차트 매니저
                'ChartManager': ChartManager,
                
                # 유틸리티 함수
                'loop': self._safe_loop,
                'run_script': lambda sub_name: self.run_script(sub_name, code, True)
            }
                
            # 변수 추가
            for var_name, var_value in vars_dict.items():
                globals_dict[var_name] = var_value
            
            # 컴파일 및 실행
            code_obj = compile(script, f"<script_{name}>", 'exec')
            locals_dict = {}
            
            # 실행 시간 측정
            start_time = time.time()
            
            try:
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                
                # 실행 시간이 너무 오래 걸리면 경고
                if exec_time > 0.05:  # 50ms 이상 걸리면 경고
                    logging.warning(f"스크립트 실행 시간 초과 ({name}:{code}): {exec_time:.4f}초")
                
                # 실행 결과 가져오기 (return 값)
                result = locals_dict.get('result', True)
                return bool(result)
            except Exception as e:
                if not is_sub_call:  # 하위 호출이 아닐 때만 상세 로깅
                    tb = traceback.format_exc()
                    logging.error(f"스크립트 실행 오류 ({name}:{code}): {type(e).__name__} - {e}\n{tb}")
                else:
                    logging.error(f"서브스크립트 실행 오류 ({name}:{code}): {type(e).__name__} - {e}")
                return False
        finally:
            # 실행 완료 후 추적 목록에서 제거
            self._running_scripts.remove(script_key)
    
    def _check_chart_data_ready(self, chart_data, code):
        """차트 데이터가 준비되었는지 확인"""
        if code not in chart_data._data:
            return False
        
        # 3분봉과 일봉 데이터가 모두 있는지 확인 (가장 많이 사용하는 주기)
        if 'mi3' not in chart_data._data[code] or 'dy' not in chart_data._data[code]:
            return False
        
        # 데이터가 충분한지 확인 (빈 배열이 아닌지)
        if not chart_data._data[code]['mi3'] or not chart_data._data[code]['dy']:
            return False
        
        return True
    
    def _prepare_chart_data(self, chart_data, code):
        """차트 데이터 준비"""
        try:
            # 1분봉과 일봉을 함께 가져오기 (내부적으로 3분봉도 생성됨)
            chart_data.get_chart_data(code, 'mi', 1)
            # 준비 완료까지 최대 1초 대기
            max_wait = 1.0  # 1초
            start_time = time.time()
            while time.time() - start_time < max_wait:
                if self._check_chart_data_ready(chart_data, code):
                    return True
                time.sleep(0.1)  # 100ms 대기
        except Exception as e:
            logging.error(f"차트 데이터 준비 오류: {e}")
        return False

"""        
GOLDEN_CROSS_SCRIPT =
# 차트 매니저 인스턴스 생성
dy = ChartManager('dy')  # 일봉

# 단기 이동평균 계산
short_ma = dy.ma(code, dy.c, short_period, 0, 'a')  # 5일 단순이동평균
# 장기 이동평균 계산
long_ma = dy.ma(code, dy.c, long_period, 0, 'a')   # 20일 단순이동평균

# 골든 크로스 확인 (단기 이동평균이 장기 이동평균을 상향 돌파)
is_golden_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, short_period, n, 'a'), 
    lambda c, n: dy.ma(c, dy.c, long_period, n, 'a'))

# 결과 기록
logging.debug(f"종목코드: {code}, 단기이평: {short_ma:.2f}, 장기이평: {long_ma:.2f}, 골든크로스: {is_golden_cross}")

# 결과 반환 (True이면 매수 신호)
result = is_golden_cross
"""

