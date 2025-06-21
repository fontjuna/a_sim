from public import dc, gm, profile_operation
from datetime import datetime
from typing import Set, Optional, Any
from multiprocessing import shared_memory
import json
import numpy as np
import logging
import time
import ast
import traceback
import re
import os
import threading
import copy
import hashlib
import marshal
import pickle
import importlib.util
import msgpack
import struct
import multiprocessing as mp
from datetime import timedelta

class ChartData:
    """
    차트 데이터를 관리하는 최적화된 공유 메모리 기반 싱글톤 클래스
    데드락 방지를 위한 락 계층구조 적용
    """
    _instance = None
    _creation_lock = threading.Lock()  # 인스턴스 생성용 락 (가장 상위)

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
                # 락 계층구조 설정
                # Level 1: 전역 락 (공유 메모리 생성/삭제만)
                self._global_lock = threading.RLock()
                # Level 2: 코드별 락 관리용
                self._code_locks_lock = threading.RLock()
                
                # 코드별 데이터 저장
                self._shm_map = {}          # 코드 -> shared_memory 맵핑
                self._code_locks = {}       # 코드별 락
                self._data_cache = {}       # 코드별 데이터 캐시
                self._cache_timestamps = {} # 캐시 타임스탬프 별도 관리
                self._registered_code_cache = set() # 등록된 코드 캐시 (성능 최적화용)
                
                # 기본 설정
                self._shm_prefix = "chart_data_"
                self._default_size = 1024 * 1024  # 1MB
                self._lock_timeout = 1.0  # 1초 타임아웃
                
                self._initialized = True
                logging.debug(f"[{datetime.now()}] ChartData initialized in PID: {os.getpid()}")
    
    def _get_code_lock(self, code):
        """코드별 락 가져오기 (타임아웃 적용)"""
        # 코드별 락 생성은 별도 락으로 보호
        try:
            if not self._code_locks_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Lock timeout for code locks creation: {code}")
                return None
            
            try:
                if code not in self._code_locks:
                    self._code_locks[code] = threading.RLock()
                return self._code_locks[code]
            finally:
                self._code_locks_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error getting code lock for {code}: {str(e)}")
            return None
        
    def _get_shared_memory_safe(self, code):
        """코드별 공유 메모리 가져오기 (데드락 안전)"""
        # 먼저 기존 메모리 확인 (락 없이)
        if code in self._shm_map:
            return self._shm_map[code]
        
        # 메모리 생성이 필요한 경우만 전역 락 사용
        try:
            if not self._global_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Global lock timeout for memory creation: {code}")
                return None
            
            try:
                # 이중 체크
                if code in self._shm_map:
                    return self._shm_map[code]
                
                # 공유 메모리 생성
                return self._create_shared_memory(code)
            finally:
                self._global_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in shared memory access for {code}: {str(e)}")
            return None
    
    def _create_shared_memory(self, code):
        """공유 메모리 생성 (전역 락 내에서만 호출)"""
        shm_name = f"{self._shm_prefix}{code}"
        
        try:
            # 기존 공유 메모리 연결 시도
            shm = shared_memory.SharedMemory(name=shm_name)
            self._shm_map[code] = shm
            self._registered_code_cache.add(code) # 캐시에 추가
            return shm
        except FileNotFoundError:
            # 없으면 새로 생성
            try:
                shm = shared_memory.SharedMemory(
                    name=shm_name,
                    create=True,
                    size=self._default_size
                )
                self._shm_map[code] = shm
                self._registered_code_cache.add(code) # 캐시에 추가
                
                # 헤더 초기화
                t_stamp = int(time.time()) & 0xFFFFFFFF
                struct.pack_into('!IIII', shm.buf, 0, 0, t_stamp, 0, 0)
                
                return shm
            except Exception as e:
                logging.error(f"[{datetime.now()}] Error creating shared memory for {code}: {str(e)}")
                return None
    
    def _expand_shared_memory_safe(self, code, required_size):
        """공유 메모리 확장 (데드락 안전)"""
        old_shm = self._shm_map.get(code)
        if not old_shm:
            return None
        
        new_size = max(self._default_size * 2, required_size + 1024)
        new_shm_name = f"{self._shm_prefix}{code}_new"
        
        try:
            # 새 메모리 생성
            new_shm = shared_memory.SharedMemory(
                name=new_shm_name, 
                create=True, 
                size=new_size
            )
            
            # 기존 데이터 복사
            copy_size = min(len(old_shm.buf), len(new_shm.buf))
            new_shm.buf[:copy_size] = old_shm.buf[:copy_size]
            
            # 원자적 교체
            self._shm_map[code] = new_shm
            
            # 이전 메모리 정리
            try:
                old_shm.close()
                old_shm.unlink()
            except:
                pass  # 정리 실패는 무시
            
            self._default_size = new_size
            logging.debug(f"[{datetime.now()}] Expanded memory for {code} to {new_size} bytes")
            return new_shm
            
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error expanding memory for {code}: {str(e)}")
            return old_shm
        
    def _save_code_data_safe(self, code, data):
        """코드별 데이터 저장 (데드락 안전)"""
        shm = self._get_shared_memory_safe(code)
        if not shm:
            return False
        
        try:
            # 데이터 직렬화
            packed_data = msgpack.packb(data, use_bin_type=True)
            data_size = len(packed_data)
            
            # 최신 캔들 정보
            last_candle_offset = 0
            last_candle_size = 0
            
            if 'mi1' in data and data['mi1']:
                last_candle_offset = 16 + data_size
                candle_data = msgpack.packb(data['mi1'][0], use_bin_type=True)
                last_candle_size = len(candle_data)
                total_size = last_candle_offset + last_candle_size
            else:
                total_size = 16 + data_size
            
            # 메모리 크기 확인 및 확장
            if total_size > len(shm.buf):
                # 전역 락으로 메모리 확장
                try:
                    if not self._global_lock.acquire(timeout=self._lock_timeout):
                        logging.warning(f"[{datetime.now()}] Memory expansion timeout for {code}")
                        return False
                    
                    try:
                        shm = self._expand_shared_memory_safe(code, total_size)
                        if not shm:
                            return False
                    finally:
                        self._global_lock.release()
                except Exception as e:
                    logging.error(f"[{datetime.now()}] Memory expansion error for {code}: {str(e)}")
                    return False
            
            # 데이터 저장
            t_stamp = int(time.time()) & 0xFFFFFFFF
            struct.pack_into('!IIII', shm.buf, 0, data_size, t_stamp, last_candle_offset, last_candle_size)
            shm.buf[16:16+data_size] = packed_data
            
            # 최신 캔들 저장
            if last_candle_offset > 0 and last_candle_size > 0:
                shm.buf[last_candle_offset:last_candle_offset+last_candle_size] = candle_data
            
            # 캐시 원자적 업데이트
            cache_time = time.time()
            self._data_cache[code] = data
            self._cache_timestamps[code] = cache_time
            
            return True
            
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error saving data for {code}: {str(e)}")
            return False
    
    def _load_code_data_safe(self, code):
        """코드별 데이터 로드 (데드락 안전)"""
        # 캐시 확인 (락 없이)
        if code in self._data_cache and code in self._cache_timestamps:
            if time.time() - self._cache_timestamps[code] < 0.1:  # 100ms 캐시
                return self._data_cache[code].copy()
        
        shm = self._get_shared_memory_safe(code)
        if not shm:
            return {'mi1': [], 'mi3': [], 'dy': [], 'wk': [], 'mo': [], 'index_maps': {}}
        
        try:
            # 헤더 읽기
            data_size = struct.unpack_from('!I', shm.buf, 0)[0]
            
            if data_size == 0 or data_size > len(shm.buf) - 16:
                return {'mi1': [], 'mi3': [], 'dy': [], 'wk': [], 'mo': [], 'index_maps': {}}
            
            # 데이터 역직렬화
            packed_data = bytes(shm.buf[16:16+data_size])
            data = msgpack.unpackb(packed_data, raw=False)
            
            # 캐시 원자적 업데이트
            cache_time = time.time()
            self._data_cache[code] = data
            self._cache_timestamps[code] = cache_time
            
            return data.copy()
            
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error loading data for {code}: {str(e)}")
            return {'mi1': [], 'mi3': [], 'dy': [], 'wk': [], 'mo': [], 'index_maps': {}}
        
    @profile_operation        
    def set_chart_data(self, code: str, data: list, cycle: str, tick: int = None):
        """외부에서 차트 데이터 설정 - 데드락 안전 버전"""
        if not data:
            return
        
        # 1분봉과 일봉만 허용
        if cycle == 'mi' and tick != 1:
            logging.warning(f"[{datetime.now()}] Only 1-minute data allowed. Rejected: {cycle}, tick={tick}")
            return
        elif cycle not in ['mi', 'dy']:
            logging.warning(f"[{datetime.now()}] Only 'mi'(tick=1) and 'dy' cycles allowed. Rejected: {cycle}")
            return
        
        # 코드별 락 획득
        code_lock = self._get_code_lock(code)
        if not code_lock:
            return
        
        try:
            if not code_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Code lock timeout for set_chart_data: {code}")
                return
            
            try:
                # 데이터 로드
                chart_data = self._load_code_data_safe(code)
                
                if cycle == 'mi' and tick == 1:
                    # 1분봉 설정
                    chart_data['mi1'] = data
                    self._create_index_map_safe(chart_data, code, 'mi1')
                    
                    # 3분봉 자동 생성
                    chart_data['mi3'] = self._aggregate_minute_data(data, 3)
                    self._create_index_map_safe(chart_data, code, 'mi3')
                    
                elif cycle == 'dy':
                    # 일봉 설정
                    chart_data['dy'] = data
                    self._create_index_map_safe(chart_data, code, 'dy')
                    
                    # 주봉, 월봉 자동 생성
                    chart_data['wk'] = self._aggregate_day_data(data, 'week')
                    self._create_index_map_safe(chart_data, code, 'wk')
                    
                    chart_data['mo'] = self._aggregate_day_data(data, 'month')
                    self._create_index_map_safe(chart_data, code, 'mo')
                
                # 데이터 저장
                self._save_code_data_safe(code, chart_data)
                
            finally:
                code_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in set_chart_data for {code}: {str(e)}")
    
    def get_chart_data(self, code: str, cycle: str, tick: int = None) -> list:
        """특정 종목, 주기의 차트 데이터 반환 - 데드락 안전 버전"""
        # 코드별 락 획득 (읽기용)
        code_lock = self._get_code_lock(code)
        if not code_lock:
            return []
        
        try:
            if not code_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Code lock timeout for get_chart_data: {code}")
                return []
            
            try:
                # 데이터 로드
                chart_data = self._load_code_data_safe(code)
                if not chart_data:
                    return []
                
                cycle_key = cycle if cycle != 'mi' else f'mi{tick}'
                
                # 저장된 데이터가 있으면 바로 반환
                if cycle_key in chart_data and chart_data[cycle_key]:
                    return chart_data[cycle_key].copy()
                
                # 분봉 집계 처리 (1분봉에서)
                if cycle == 'mi' and 'mi1' in chart_data and chart_data['mi1']:
                    aggregated_data = self._aggregate_minute_data(chart_data['mi1'], tick)
                    
                    # 집계 데이터 저장
                    chart_data[cycle_key] = aggregated_data
                    self._save_code_data_safe(code, chart_data)
                    
                    return aggregated_data.copy()
                
                return []
                
            finally:
                code_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in get_chart_data for {code}: {str(e)}")
            return []
    
    def update_chart(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """실시간 가격 정보로 차트 데이터 업데이트 - 데드락 안전 버전"""
        # 공유 메모리 존재 여부만 먼저 확인 (락 없이)
        if not self._get_shared_memory_safe(code):
            #logging.warning(f"[{datetime.now()}] No shared memory found for code: {code}")
            return
            
        # 코드별 락 획득
        code_lock = self._get_code_lock(code)
        if not code_lock: return
        
        try:
            if not code_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Code lock timeout for update_chart: {code}")
                return
            
            try:
                # 데이터 로드
                chart_data = self._load_code_data_safe(code)
                
                # 1분봉 업데이트
                self._update_minute_chart_safe(chart_data, code, price, volume, amount, datetime_str)
                
                # 3분봉 업데이트
                self._update_cyclic_chart_safe(chart_data, code, price, volume, amount, datetime_str, 3)
                
                # 일봉 업데이트 (있는 경우에만)
                if 'dy' in chart_data and chart_data['dy']:
                    self._update_day_chart_safe(chart_data, code, price, volume, amount, datetime_str)
                    # 주봉/월봉 업데이트
                    self._update_week_month_chart_safe(chart_data, code, price, volume, amount, datetime_str)
                
                # 데이터 저장
                self._save_code_data_safe(code, chart_data)
                
            finally:
                code_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in update_chart for {code}: {str(e)}")

    def is_code_registered(self, code: str) -> bool:
        """
        특정 종목 코드의 공유 메모리가 시스템에 생성되었는지 확인 (프로세스 독립적, 캐싱 적용)
        """
        # 1. 로컬 캐시에서 먼저 확인 (매우 빠름)
        if code in self._registered_code_cache:
            return True

        # 2. 캐시에 없으면 시스템 콜로 확인 (비용 발생)
        shm_name = f"{self._shm_prefix}{code}"
        try:
            # 연결만 시도해보고, 성공하면 바로 닫음
            shm = shared_memory.SharedMemory(name=shm_name)
            shm.close()

            # 3. 확인되면 캐시에 추가
            self._registered_code_cache.add(code)
            return True
        except FileNotFoundError:
            # 파일이 없으면 등록되지 않은 것
            return False
        except Exception as e:
            # 그 외의 오류는 로깅
            logging.error(f"[{datetime.now()}] Error checking shared memory for {code}: {str(e)}")
            return False
            
    def _create_index_map_safe(self, chart_data, code: str, cycle_key: str):
        """시간 -> 인덱스 매핑 생성 (데드락 안전)"""
        if 'index_maps' not in chart_data:
            chart_data['index_maps'] = {}
        if cycle_key not in chart_data['index_maps']:
            chart_data['index_maps'][cycle_key] = {}
        
        index_map = {}
        data = chart_data.get(cycle_key, [])
        
        time_key = '체결시간' if cycle_key.startswith('mi') else '일자'
        
        for i, candle in enumerate(data):
            if time_key in candle:
                index_map[candle[time_key]] = i
        
        chart_data['index_maps'][cycle_key] = index_map
    
    def _update_minute_chart_safe(self, chart_data, code, price, volume, amount, datetime_str):
        """1분봉 업데이트 (데드락 안전)"""
        base_time = datetime_str[:12] + '00'
        
        if 'mi1' not in chart_data:
            chart_data['mi1'] = []
        
        minute_data = chart_data['mi1']
        
        # 데이터가 없는 경우
        if not minute_data:
            new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
            minute_data.insert(0, new_candle)
            
            if 'index_maps' not in chart_data:
                chart_data['index_maps'] = {}
            if 'mi1' not in chart_data['index_maps']:
                chart_data['index_maps']['mi1'] = {}
            chart_data['index_maps']['mi1'][base_time] = 0
            return
        
        # 최신 봉 시간 확인
        latest_time = minute_data[0]['체결시간']
        
        # 같은 봉 내의 업데이트
        if latest_time == base_time:
            self._update_candle(minute_data[0], price, price, volume, amount)
            return
        
        # 새로운 봉 처리
        time_diff = self._calculate_time_diff(latest_time, base_time)
        
        # 누락된 봉이 있는 경우
        if time_diff > 1:
            last_price = minute_data[0]['현재가']
            missing_times = self._generate_missing_times(latest_time, base_time)
            
            for missing_time in missing_times:
                missing_candle = self._create_candle(
                    code, missing_time, last_price, last_price, last_price, last_price, 0, 0, True)
                minute_data.insert(0, missing_candle)
                self._update_index_map_safe(chart_data, 'mi1', missing_time)
        
        # 현재 시간대의 새 봉 추가
        new_candle = self._create_candle(code, base_time, price, price, price, price, volume, amount)
        minute_data.insert(0, new_candle)
        self._update_index_map_safe(chart_data, 'mi1', base_time)
    
    def _update_index_map_safe(self, chart_data, cycle_key, time_key):
        """인덱스 맵 업데이트 (데드락 안전)"""
        if 'index_maps' not in chart_data:
            chart_data['index_maps'] = {}
        if cycle_key not in chart_data['index_maps']:
            chart_data['index_maps'][cycle_key] = {}
        
        # 기존 인덱스 시프트
        chart_data['index_maps'][cycle_key] = {k: v+1 for k, v in chart_data['index_maps'][cycle_key].items()}
        # 새 캔들 인덱스 추가
        chart_data['index_maps'][cycle_key][time_key] = 0
    
    def _update_cyclic_chart_safe(self, chart_data, code, price, volume, amount, datetime_str, tick):
        """주기적 차트 업데이트 (데드락 안전)"""
        cycle_key = f'mi{tick}'
        
        if len(datetime_str) < 12:
            return
        
        # 시간 계산
        hour = int(datetime_str[8:10])
        minute = int(datetime_str[10:12])
        total_minutes = hour * 60 + minute
        
        tick_start = (total_minutes // tick) * tick
        tick_time = f"{datetime_str[:8]}{tick_start//60:02d}{tick_start%60:02d}00"
        
        # 데이터 초기화
        if cycle_key not in chart_data:
            chart_data[cycle_key] = []
        
        cyclic_data = chart_data[cycle_key]
        
        if not cyclic_data:
            new_candle = self._create_candle(code, tick_time, price, price, price, price, volume, amount)
            cyclic_data.append(new_candle)
            self._update_index_map_safe(chart_data, cycle_key, tick_time)
            return
        
        latest_time = cyclic_data[0]['체결시간']
        
        if latest_time == tick_time:
            self._update_candle(cyclic_data[0], price, None, volume, amount)
            return
        
        # 새로운 주기 처리
        time_diff = self._calculate_time_diff(latest_time, tick_time, tick)
        
        if time_diff > 1:
            last_price = cyclic_data[0]['현재가']
            missing_times = self._generate_missing_times(latest_time, tick_time, tick)
            
            for missing_time in missing_times:
                missing_candle = self._create_candle(
                    code, missing_time, last_price, last_price, last_price, last_price, 0, 0, True)
                cyclic_data.insert(0, missing_candle)
                self._update_index_map_safe(chart_data, cycle_key, missing_time)
        
        new_candle = self._create_candle(code, tick_time, price, price, price, price, volume, amount)
        cyclic_data.insert(0, new_candle)
        self._update_index_map_safe(chart_data, cycle_key, tick_time)

    def _update_day_chart_safe(self, chart_data, code, price, volume, amount, datetime_str):
        """일봉 데이터 업데이트 (데드락 안전)"""
        day_data = chart_data.get('dy', [])
        if not day_data:
            return
        
        today = datetime_str[:8]
        
        # 인덱스 맵 사용하여 오늘 데이터 찾기
        if ('index_maps' in chart_data and 'dy' in chart_data['index_maps'] and 
            today in chart_data['index_maps']['dy']):
            idx = chart_data['index_maps']['dy'][today]
            if idx < len(day_data):
                current = day_data[idx]
                self._update_candle(current, price, None, volume, amount)
                return
        
        # 당일 데이터가 없는 경우 새로 추가
        new_day = {
            '종목코드': code,
            '일자': today,
            '시가': price,
            '고가': price,
            '저가': price,
            '현재가': price,
            '거래량': volume,
            '거래대금': amount
        }
        day_data.insert(0, new_day)
        self._update_index_map_safe(chart_data, 'dy', today)
    
    def _update_week_month_chart_safe(self, chart_data, code, price, volume, amount, datetime_str):
        """주봉/월봉 업데이트 (데드락 안전)"""
        today = datetime_str[:8]
        
        try:
            year = int(today[:4])
            month = int(today[4:6])
            day = int(today[6:8])
            date_obj = datetime(year, month, day)
        except ValueError:
            return
        
        # 주봉 업데이트
        self._update_period_chart_safe(chart_data, code, price, volume, amount, date_obj, 'wk', 'week')
        
        # 월봉 업데이트
        self._update_period_chart_safe(chart_data, code, price, volume, amount, date_obj, 'mo', 'month')
    
    def _update_period_chart_safe(self, chart_data, code, price, volume, amount, date_obj, cycle_key, period_type):
        """주봉/월봉 공통 업데이트 로직 (데드락 안전)"""
        period_data = chart_data.get(cycle_key, [])
        if not period_data:
            return
        
        # 현재 주기 키 계산
        if period_type == 'week':
            days_since_monday = date_obj.weekday()
            monday = date_obj - timedelta(days=days_since_monday)
            current_period_key = monday.strftime('%Y%m%d')
        else:  # month
            current_period_key = date_obj.strftime('%Y%m01')
        
        # 인덱스 맵 사용하여 현재 주기 데이터 찾기
        if ('index_maps' in chart_data and cycle_key in chart_data['index_maps'] and 
            current_period_key in chart_data['index_maps'][cycle_key]):
            idx = chart_data['index_maps'][cycle_key][current_period_key]
            if idx < len(period_data):
                current = period_data[idx]
                self._update_candle(current, price, None, volume, amount)
                return
        
        # 현재 주기 데이터가 없는 경우 새로 추가
        new_period = {
            '종목코드': code,
            '일자': current_period_key,
            '시가': price,
            '고가': price,
            '저가': price,
            '현재가': price,
            '거래량': volume,
            '거래대금': amount
        }
        period_data.insert(0, new_period)
        self._update_index_map_safe(chart_data, cycle_key, current_period_key)
    
    def clean_up_safe(self):
        """공유 메모리 정리 - 데드락 안전 버전"""
        try:
            if not self._global_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Global lock timeout for cleanup")
                return
            
            try:
                # 모든 공유 메모리 해제
                for code, shm in list(self._shm_map.items()):
                    try:
                        shm.close()
                        shm.unlink()
                        logging.debug(f"[{datetime.now()}] Cleaned up shared memory for {code}")
                    except Exception as e:
                        logging.warning(f"[{datetime.now()}] Error cleaning up memory for {code}: {str(e)}")
                
                # 맵 초기화
                self._shm_map.clear()
                self._data_cache.clear()
                self._cache_timestamps.clear()
                self._registered_code_cache.clear() # 등록된 코드 캐시도 초기화
                
            finally:
                self._global_lock.release()
                
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error in cleanup: {str(e)}")
        
        # 코드별 락 정리
        try:
            if not self._code_locks_lock.acquire(timeout=self._lock_timeout):
                logging.warning(f"[{datetime.now()}] Code locks cleanup timeout")
                return
            
            try:
                self._code_locks.clear()
            finally:
                self._code_locks_lock.release()
        except Exception as e:
            logging.error(f"[{datetime.now()}] Error cleaning up code locks: {str(e)}")
        
        logging.debug(f"[{datetime.now()}] All resources cleaned up in PID: {os.getpid()}")
    
    def _create_candle(self, code, time_str, close, open, high, low, volume, amount, is_missing=False):
        """캔들 객체 생성 헬퍼 함수"""
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
        
        if 'is_missing' in candle:
            del candle['is_missing']

    def _calculate_time_diff(self, time1, time2, tick=1):
        """두 시간 사이의 차이 계산 (tick 단위)"""
        if time1[:8] != time2[:8]:
            return 1000
        
        minutes1 = int(time1[8:10]) * 60 + int(time1[10:12])
        minutes2 = int(time2[8:10]) * 60 + int(time2[10:12])
        
        period1 = minutes1 // tick
        period2 = minutes2 // tick
        
        return period2 - period1 if period2 > period1 else 1000

    def _generate_missing_times(self, start_time, end_time, tick=1):
        """누락된 시간대 목록 생성"""
        result = []
        
        if start_time[:8] != end_time[:8]:
            return result
        
        start_minutes = int(start_time[8:10]) * 60 + int(start_time[10:12])
        end_minutes = int(end_time[8:10]) * 60 + int(end_time[10:12])
        
        start_period = (start_minutes // tick)
        end_period = (end_minutes // tick)
        
        for period in range(start_period + 1, end_period):
            minutes = period * tick
            hour = minutes // 60
            minute = minutes % 60
            time_str = f"{start_time[:8]}{hour:02d}{minute:02d}00"
            result.append(time_str)
        
        return result
    
    def _aggregate_minute_data(self, minute_data, tick):
        """1분봉 데이터를 특정 tick으로 집계"""
        if not minute_data:
            return []
        
        grouped_data = {}
        minute_map = {}
        
        for candle in minute_data:
            dt_str = candle['체결시간']
            if len(dt_str) < 12:
                continue
            
            if dt_str in minute_map:
                group_key = minute_map[dt_str]
            else:
                hour = int(dt_str[8:10])
                minute = int(dt_str[10:12])
                total_minutes = hour * 60 + minute
                tick_start = (total_minutes // tick) * tick
                group_hour = tick_start // 60
                group_minute = tick_start % 60
                group_key = f"{dt_str[:8]}{group_hour:02d}{group_minute:02d}00"
                minute_map[dt_str] = group_key
            
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
        """일봉 데이터를 주봉/월봉으로 집계"""
        if not day_data:
            return []
        
        grouped_data = {}
        period_map = {}
        
        for candle in day_data:
            date_str = candle['일자']
            if len(date_str) != 8:
                continue
            
            if date_str in period_map:
                group_key = period_map[date_str]
            else:
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
                    
                    period_map[date_str] = group_key
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
        result.sort(key=lambda x: x['일자'], reverse=True)
        return result

cht_dt = ChartData()

class ChartManager:
    def __init__(self, code, cycle='mi', tick=3):
        self.cycle = cycle  # 'mo', 'wk', 'dy', 'mi' 중 하나
        self.tick = tick    # 분봉일 경우 주기
        self._data_cache = {}  # 종목별 데이터 캐시 {code: data}
        self.code = code    # 종목코드 (없으면 컨텍스트에서 가져옴)

    def _get_data(self) -> list:
        """현재 종목의 차트 데이터 가져오기 (캐싱)"""
        if self.code not in self._data_cache:
            # 데이터 가져오기
            self._data_cache[self.code] = self._load_chart_data(self.code)
        return self._data_cache[self.code]
    
    def _load_chart_data(self, code: str) -> list:
        """차트 데이터 로드 및 변환"""
        data = cht_dt.get_chart_data(code, self.cycle, self.tick)
        
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
        if self.cycle != 'mi':
            return ''
        return self._get_value(n, 'time', '')
    
    def today(self) -> str:
        """오늘 날짜 반환"""
        return datetime.now().strftime('%Y%m%d')

# 계산 함수들
    def ma(self, a, n: int, m: int = 0, k: str = 'a') -> float:
        """이동평균 계산"""
        if k == 'a': return self.avg(a, n, m)
        elif k == 'e': return self.eavg(a, n, m)
        elif k == 'w': return self.wavg(a, n, m)
        return 0.0
    
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
    투자 스크립트 관리 및 실행 클래스 (확장 버전)
    
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
        
        # 파일에서 스크립트와 사용자 함수 로드
        self._load_scripts()
    
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
    
    def set_scripts(self, scripts: dict, kwargs: dict = None):
        """스크립트 전체 설정 및 저장
        
        Args:
            scripts: {script_name: {script: str, vars: dict}} 형식의 스크립트 사전
        
        Returns:
            bool: 저장 성공 여부
        """
        # 모든 스크립트 유효성 검사
        valid_scripts = {}
        for script_name, script_data in scripts.items():
            result = self.run_script(script_name, check_only=True, script_data=script_data, kwargs=kwargs)
            if result['success']:   
                #script_data['script'] = script_data['script'] # .replace('\n\n', '\n')
                script_data['type'] = self.get_script_type(result['result'])
                valid_scripts[script_name] = script_data
            else:
                logging.warning(f"유효하지 않은 스크립트: {script_name} - {result['error']}")
        
        self.scripts = valid_scripts
        # 컴파일된 스크립트 캐시 초기화
        self._compiled_scripts = {}
        return self._save_scripts()
    
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
                    
    def set_script(self, script_name: str, script: str, vars: dict = None, desc: str = '', kwargs: dict = None):
        """단일 스크립트 설정 및 저장
        
        Args:
            script_name: 스크립트 이름
            script: 스크립트 코드
            vars: 스크립트에서 사용할 변수 사전
            desc: 스크립트 설명
        
        Returns:
            type: False=실패, str=성공(str=result type)
        """
        script_data = {'script': script, 'vars': vars or {}}
        result = self.run_script(script_name, check_only=True, script_data=script_data, kwargs=kwargs)
        
        if not result['success'] or self.get_script_type(result['result']) == 'error':
            logging.warning(f"유효하지 않은 스크립트: {script_name} - {result['error'] or 'result가 None입니다.'}")
            return False
            
        #script_data['script'] = script_data['script'] #.replace('\n\n', '\n')
        script_data['type'] = self.get_script_type(result['result'])
        script_data['desc'] = desc
        self.scripts[script_name] = script_data
        
        # 컴파일된 스크립트 캐시에서 제거 (재컴파일 필요)
        if script_name in self._compiled_scripts:
            del self._compiled_scripts[script_name]
        
        ret = self._save_scripts()
        if ret: 
            return script_data['type']
        return False
    
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
            if script_name in self._compiled_scripts:
                del self._compiled_scripts[script_name]
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
        """스크립트 에러 위치 추출
        
        Args:
            tb_str: 트레이스백 문자열
            script: 스크립트 코드
            
        Returns:
            tuple: (line_num, error_line, error_msg)
        """
        try:
            # 에러 라인 번호 찾기
            lines = tb_str.splitlines()
            error_line_num = None
            error_msg = "알 수 없는 오류"
            
            for line in lines:
                if "File \"<string>\"" in line and ", line " in line:
                    match = re.search(r", line (\d+)", line)
                    if match:
                        error_line_num = int(match.group(1))
                elif "TypeError:" in line or "NameError:" in line or "SyntaxError:" in line:
                    error_msg = line.strip()
            
            if error_line_num:
                script_lines = script.splitlines()
                if 1 <= error_line_num <= len(script_lines):
                    # 실제 스크립트에서의 해당 라인
                    error_line = script_lines[error_line_num-1]
                    return (error_line_num, error_line, error_msg)
            
            return (None, "", error_msg)
        except Exception as e:
            logging.error(f"에러 위치 파악 오류: {e}")
            return (None, "", "에러 위치 파악 실패")
            
    def run_script(self, script_name: str, script_data=None, check_only=False, kwargs=None):
        """스크립트 또는 사용자 함수 실행/검사
        
        Args:
            script_name: 스크립트/함수 이름
            script_data: 직접 제공하는 스크립트/함수 데이터 (검사용)
            check_only: 실행하지 않고 검사만 할지 여부
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
        # 결과 초기화
        result_dict = {
            'success': False,
            'result': None,
            'error': None,
            'exec_time': 0,
            'log': ''
        }
        
        # kwargs 초기화 (None이면 빈 딕셔너리)
        if kwargs is None:
            kwargs = {}
        
        # 종목코드 가져오기 (없으면 기본값)
        code = kwargs.get('code')  # 기본값 삼성전자
        if code is None:
            result_dict['error'] = f"종목코드가 지정되지 않았습니다."
            return result_dict
        
        # 스크립트 이름 유효성 검사
        if not self._is_valid_identifier(script_name):
            result_dict['error'] = f"유효하지 않은 스크립트 이름: {script_name}"
            return result_dict
        
        # 순환 참조 방지
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_name}"
            return result_dict
        
        # 실행 중인 스크립트에 추가
        self._running_scripts.add(script_key)
        
        try:
            # 스크립트 데이터 가져오기
            if script_data is None:
                script_data = self.get_script(script_name)
            
            script = script_data.get('script', '')
            vars_dict = script_data.get('vars', {}).copy()  # 사용자 지정 변수
            
            if not script:
                result_dict['error'] = f"스크립트 없음: {script_name}"
                return result_dict
            
            # 사용자 지정 변수(vars) 병합
            combined_kwargs = kwargs.copy()
            combined_kwargs.update(vars_dict)
            
            # 1. 스크립트 유효성 검사
            try:
                # 스크립트를 감싸서 실행하기 위한 코드 생성
                wrapped_script = f"""
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
{self._indent_script(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise  # 오류를 전파하여 감지할 수 있도록 함

# 스크립트 실행
result = execute_script({repr(combined_kwargs)})
"""
                # 구문 분석 검사
                try:
                    ast.parse(wrapped_script)
                except SyntaxError as e:
                    line_num = e.lineno - 12  # 래퍼 함수의 오프셋 고려
                    if line_num < 1:
                        line_num = 1
                    result_dict['error'] = f"구문 오류 (행 {line_num}): {e}"
                    return result_dict
                        
            except Exception as e:
                result_dict['error'] = f"스크립트 준비 오류: {type(e).__name__} - {e}"
                return result_dict
            
            # 2. 보안 검증 (금지된 구문 확인)
            if self._has_forbidden_syntax(script):
                result_dict['error'] = f"보안 위반 코드 포함"
                return result_dict
                
            # 3. 차트 데이터 준비 상태 확인
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
                return result_dict
            
            # 4. 실행 환경 준비
            globals_dict = self._prepare_execution_globals()
            locals_dict = {}
            
            # 5. 스크립트 컴파일 또는 캐시에서 가져오기
            try:
                cache_key = f"{script_name}_{code}"
                
                # 테스트용이면 항상 새로 컴파일
                if check_only or script_data is not None:  
                    code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                elif cache_key not in self._compiled_scripts:  # 캐시 확인
                    self._compiled_scripts[cache_key] = compile(wrapped_script, f"<{script_name}>", 'exec')
                    code_obj = self._compiled_scripts[cache_key]
                else:
                    code_obj = self._compiled_scripts[cache_key]
            except Exception as e:
                result_dict['error'] = f"컴파일 오류: {type(e).__name__} - {e}"
                return result_dict
            
            # 6. 실행
            try:
                # kwargs 변수 설정 (스크립트에서 접근 가능하도록)
                locals_dict['kwargs'] = combined_kwargs
                
                # 코드 실행
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                
                # 실행 시간이 너무 오래 걸리면 경고
                if exec_time > 0.05:  # 50ms 이상 걸리면 경고
                    logging.warning(f"스크립트 실행 시간 초과 ({script_name}:{code}): {exec_time:.4f}초")
                
                # 실행 결과 가져오기
                script_result = locals_dict.get('result')
                
                # 'result' 변수가 없는 경우 에러 처리 (check_only 모드에서만)
                if check_only and script_result is None:
                    result_dict['error'] = "스크립트에 'result' 변수가 정의되지 않았습니다."
                    return result_dict
        
                result_dict['success'] = True
                result_dict['result'] = script_result
                result_dict['exec_time'] = exec_time
                
                return result_dict
                    
            except Exception as e:
                tb = traceback.format_exc()
                
                # 사용자 친화적인 에러 메시지 생성
                line_num, error_line, error_msg = self._get_script_error_location(tb, script)
                
                if line_num:
                    user_error = f"실행 오류 (행 {line_num}): {error_msg}\n코드: {error_line.strip()}"
                else:
                    user_error = f"실행 오류: {type(e).__name__} - {e}"
                
                # 시스템 로깅용 상세 오류
                logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}\n{tb}")
                
                result_dict['log'] = tb
                result_dict['error'] = user_error
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
                
                # 차트 매니저 및 단축 변수들
                'ChartManager': ChartManager,
                'CM': ChartManager,
                # 'mi1': ChartManager(code, 'mi', 1),
                # 'mi3': ChartManager(code, 'mi', 3),
                # 'mi5': ChartManager(code, 'mi', 5),
                # 'mi10': ChartManager(code, 'mi', 10),
                # 'mi15': ChartManager(code, 'mi', 15),
                # 'mi30': ChartManager(code, 'mi', 30),
                # 'mi60': ChartManager(code, 'mi', 60),
                # 'mi240': ChartManager(code, 'mi', 240),
                # 'dy': ChartManager(code, 'dy'),
                # 'wk': ChartManager(code, 'wk'),
                # 'mo': ChartManager(code, 'mo'),
                
                # 유틸리티 함수
                'loop': self._safe_loop,
            }
            
            # 모든 스크립트를 함수로 등록
            for script_name, script_data in self.scripts.items():
                # 스크립트가 함수처럼 호출 가능하도록 래퍼 생성
                wrapper_code = f"""
def {script_name}(**user_kwargs):
    # 스크립트 호출 함수 - 결과값만 반환
    return run_script('{script_name}', user_kwargs)
"""
                
                # 스크립트 래퍼 함수 컴파일 및 추가
                try:
                    exec(wrapper_code, globals_dict, globals_dict)
                except Exception as e:
                    logging.error(f"스크립트 래퍼 생성 오류 ({script_name}): {e}")
            
            # run_script 함수 추가 (스크립트 내에서 다른 스크립트 호출용)
            globals_dict['run_script'] = self._script_caller
            
            return globals_dict
        except Exception as e:
            logging.error(f"실행 환경 준비 오류: {e}")
            # 기본 환경 반환
            return {'ChartManager': ChartManager}
                        
    def _script_caller(self, script_name, user_kwargs=None):
        """스크립트 내에서 다른 스크립트를 호출하기 위한 함수
        
        Args:
            script_name: 호출할 스크립트 이름
            user_kwargs: 사용자가 전달한 추가 변수들
            
        Returns:
            Any: 스크립트 실행 결과값 (성공 시) 또는 None (실패 시)
        """
        # 컨텍스트의 기존 kwargs 가져오기 (프레임 검사)
        try:
            import inspect
            frame = inspect.currentframe().f_back
            context_kwargs = frame.f_locals.get('kwargs', {})
        except:
            context_kwargs = {}
        
        # 새 kwargs 생성 (기존 컨텍스트 유지)
        new_kwargs = context_kwargs.copy()
        
        # 사용자가 전달한 추가 매개변수 병합
        if user_kwargs:
            new_kwargs.update(user_kwargs)
        
        # 현재 실행 중인 스크립트 목록에서 순환 참조 검사
        code = new_kwargs.get('code')
        if code is None:
            logging.error(f"{script_name} 에서 code 가 지정되지 않았습니다.")
            return None
        
        script_key = f"{script_name}:{code}"
        if script_key in self._running_scripts:
            # 순환 참조 발견 - 오류 반환
            logging.error(f"순환 참조 감지: {script_name}")
            return None
        
        # 스크립트 실행 - 결과값만 반환
        result = self.run_script(script_name, kwargs=new_kwargs)
        return result['result'] if result['success'] else None

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
                wrapped_script = f"""
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
{self._indent_script(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise  # 오류를 전파하여 감지할 수 있도록 함

# 스크립트 실행
result = execute_script(kwargs)
"""
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
            
class ScriptManagerExtension:
    """ScriptManager 클래스를 위한 확장 메서드"""
    
    def __init__(self, cache_dir=dc.fp.cache_path):
        """초기화"""
        self.script_cache = CompiledScriptCache(cache_dir=cache_dir)
        
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
            
            for script_name, script_data in all_scripts.items():
                script = script_data.get('script', '')
                self.script_cache.compile_script(script_name, script, script_names)
            
            logging.info(f"스크립트 컴파일러 초기화 완료: {len(all_scripts)}개 스크립트")
            return True
            
        except Exception as e:
            logging.error(f"스크립트 컴파일러 초기화 오류: {e}")
            return False
    
    def set_script_compiled(self, script_manager, script_name, script, vars=None, desc='', kwargs=None):
        """스크립트 설정 및 컴파일
        
        Args:
            script_manager: ScriptManager 인스턴스
            script_name: 스크립트 이름
            script: 스크립트 코드
            vars: 스크립트 변수
            desc: 스크립트 설명
            kwargs: 스크립트 검사에 사용할 추가 변수 (code 포함)
            
        Returns:
            bool or str: 성공 시 스크립트 타입, 실패 시 False
        """
        # 기존 set_script 메서드 호출
        result = script_manager.set_script(script_name, script, vars, desc, kwargs)
        
        if result:
            # 컴파일 및 캐싱
            script_names = set(script_manager.scripts.keys())
            self.script_cache.compile_script(script_name, script, script_names)
            
            # 의존하는 스크립트들 재컴파일
            affected = self.script_cache.invalidate_script(script_name)
            for affected_name in affected:
                if affected_name != script_name and affected_name in script_manager.scripts:
                    affected_script = script_manager.scripts[affected_name]['script']
                    self.script_cache.compile_script(affected_name, affected_script, script_names)
            
            if len(affected) > 1:
                logging.info(f"스크립트 컴파일 완료: {script_name} (영향받은 스크립트: {len(affected)-1}개)")
            else:
                logging.info(f"스크립트 컴파일 완료: {script_name}")
        
        return result
    
    def delete_script_compiled(self, script_manager, script_name):
        """컴파일된 스크립트 삭제
        
        Args:
            script_manager: ScriptManager 인스턴스
            script_name: 스크립트 이름
            
        Returns:
            bool: 삭제 성공 여부
        """
        # 의존하는 스크립트들 확인
        affected = self.script_cache.get_affected_scripts(script_name)
        if affected:
            logging.warning(f"'{script_name}' 스크립트를 삭제하면 다음 스크립트들에 영향: {', '.join(affected)}")
        
        # 기존 delete_script 메서드 호출
        result = script_manager.delete_script(script_name)
        
        if result:
            # 캐시 무효화
            self.script_cache.invalidate_script(script_name)
            
            # 캐시 파일 삭제
            try:
                cache_path = self.script_cache.get_cache_path(script_name)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                
                dep_path = self.script_cache.get_dependency_path(script_name)
                if os.path.exists(dep_path):
                    os.remove(dep_path)
            except Exception as e:
                logging.error(f"캐시 파일 삭제 오류: {e}")
        
        return result
    
    def run_script_compiled(self, script_manager, script_name, script_data=None, check_only=False, kwargs=None):
        """컴파일된 스크립트 실행
        
        Args:
            script_manager: ScriptManager 인스턴스
            script_name: 스크립트 이름
            script_data: 직접 제공하는 스크립트 데이터
            check_only: 검사만 수행
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
        
        # kwargs 초기화 (None이면 빈 딕셔너리)
        if kwargs is None:
            kwargs = {}
        
        # 종목코드 가져오기
        code = kwargs.get('code')  # 기본값 삼성전자
        if code is None:
            result_dict['error'] = f"{script_name} 에서 code 가 지정되지 않았습니다."
            return result_dict

        # 순환 참조 방지
        script_key = f"{script_name}:{code}"
        if script_key in script_manager._running_scripts:
            result_dict['error'] = f"순환 참조 감지: {script_name}"
            return result_dict
        
        # 실행 중인 스크립트에 추가
        script_manager._running_scripts.add(script_key)
        
        try:
            # 테스트 모드면 기본 종목코드 사용
            # if check_only:
            #     kwargs['code'] = '005930'
            #     code = '005930'
            
            # 스크립트 데이터 가져오기
            if script_data is None:
                script_data = script_manager.get_script(script_name)
            
            script = script_data.get('script', '')
            vars_dict = script_data.get('vars', {}).copy()
            
            # 사용자 지정 변수(vars) 병합
            combined_kwargs = kwargs.copy()
            combined_kwargs.update(vars_dict)
            
            if not script:
                result_dict['error'] = f"스크립트 없음: {script_name}"
                return result_dict
            
            # 1. 구문 분석 및 보안 검사 (새 스크립트나 수정된 스크립트)
            if check_only or script_data is not None:
                try:
                    # 구문 분석
                    ast.parse(script)
                    
                    # 보안 검사
                    if script_manager._has_forbidden_syntax(script):
                        result_dict['error'] = f"보안 위반 코드 포함: {script_name}"
                        return result_dict
                except SyntaxError as e:
                    line_num = e.lineno
                    result_dict['error'] = f"구문 오류 (행 {line_num}): {e}"
                    return result_dict
            
            # 2. 차트 데이터 준비
            try:
                has_data = script_manager._check_chart_data_ready(code)
                
                if not has_data:
                    script_manager._prepare_chart_data(code)
                    has_data = script_manager._check_chart_data_ready(code)
                    if not has_data:
                        result_dict['error'] = f"차트 데이터 준비 실패: {code}"
                        return result_dict
            except Exception as e:
                result_dict['error'] = f"데이터 준비 오류: {type(e).__name__} - {e}"
                return result_dict
            
            # 3. 실행 환경 준비
            try:
                globals_dict = script_manager._prepare_execution_globals()
                locals_dict = {}
            except Exception as e:
                result_dict['error'] = f"실행 환경 준비 오류: {type(e).__name__} - {e}"
                return result_dict
            
            # 4. 컴파일된 스크립트 실행
            try:
                # 테스트 모드이거나 직접 제공된 스크립트인 경우
                if check_only or script_data is not None:
                    # 런타임 테스트를 위해 새로 컴파일
                    wrapped_script = f"""
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
{script_manager._indent_script(script, indent=8)}
        return result if 'result' in locals() else None
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise

# 스크립트 실행
result = execute_script({repr(combined_kwargs)})
"""
                    code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                else:
                    # 캐시된 컴파일 코드 사용
                    code_obj = self.script_cache.load_compiled_script(script_name)
                    
                    # 캐시에 없으면 새로 컴파일
                    if code_obj is None:
                        script_names = set(script_manager.scripts.keys())
                        self.script_cache.compile_script(script_name, script, script_names)
                        code_obj = self.script_cache.load_compiled_script(script_name)
                        
                        if code_obj is None:
                            # 여전히 로드 실패 시 일반 컴파일 사용
                            wrapped_script = f"""
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
    {script_manager._indent_script(script, indent=8)}
            return result if 'result' in locals() else None
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            raise

    # 스크립트 실행
    result = execute_script({repr(combined_kwargs)})
    """
                            code_obj = compile(wrapped_script, f"<{script_name}>", 'exec')
                
                # 스크립트 실행 전에 kwargs 변수 설정
                locals_dict['kwargs'] = combined_kwargs
                
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
                
                # 사용자 친화적인 에러 메시지 생성
                line_num, error_line, error_msg = script_manager._get_script_error_location(tb, script)
                
                if line_num:
                    user_error = f"실행 오류 (행 {line_num}): {error_msg}\n코드: {error_line.strip()}"
                else:
                    user_error = f"실행 오류: {type(e).__name__} - {e}"
                
                logging.error(f"{script_name} 스크립트 오류: {type(e).__name__} - {e}\n{tb}")
                
                result_dict['log'] = tb
                result_dict['error'] = user_error
                return result_dict
                
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if script_key in script_manager._running_scripts:
                script_manager._running_scripts.remove(script_key)
            
            # 실행 시간 기록
            result_dict['exec_time'] = time.time() - start_time
                        
def enhance_script_manager(script_manager, cache_dir=dc.fp.cache_path):
    """기존 ScriptManager 클래스를 확장하여 컴파일 기능 추가
    
    Args:
        script_manager: 확장할 ScriptManager 인스턴스
        cache_dir: 캐시 디렉토리
        
    Returns:
        bool: 확장 성공 여부
    """
    try:
        # 확장 클래스 인스턴스 생성
        extension = ScriptManagerExtension(cache_dir=cache_dir)
        
        # 메서드 연결
        script_manager.init_script_compiler = lambda: extension.init_script_compiler(script_manager)
        script_manager.set_script_compiled = lambda script_name, script, vars=None, desc='', kwargs=None: extension.set_script_compiled(script_manager, script_name, script, vars, desc, kwargs)
        script_manager.delete_script_compiled = lambda script_name: extension.delete_script_compiled(script_manager, script_name)
        script_manager.run_script_compiled = lambda script_name, script_data=None, check_only=False, kwargs=None: extension.run_script_compiled(script_manager, script_name, script_data, check_only, kwargs)
        
        # 스크립트 캐시 참조 추가
        script_manager.script_cache = extension.script_cache
        
        # 초기화
        script_manager.init_script_compiler()
        
        logging.info("ScriptManager 컴파일 기능 확장 완료")
        return True
        
    except Exception as e:
        logging.error(f"ScriptManager 확장 오류: {e}", exc_info=True)
        return False
    
class ChartUpdater:
    def __init__(self):
        self.name = 'ctu'
        self.running = False
        self.done_code = set()
        self.todo_code = {}
        self.cht_updater = {}
        self.latch_on = True
        self.lock = None

    def initialize(self):
        self.running = True
        self.latch_on = True
        self.lock = threading.Lock()

    def latch_off(self):
        self.latch_on = False

    def get_first_chart_data(self, code, cycle, tick=1, times=1):
        """차트 데이터 조회"""
        try:
            rqname = f'{dc.scr.차트종류[cycle]}차트'
            trcode = dc.scr.차트TR[cycle]
            screen = dc.scr.화면[rqname]
            date = datetime.now().strftime('%Y%m%d')
            dict_list = []
            
            if cycle in ['mi', 'tk']:
                if tick == None:
                    tick = '1'
                elif isinstance(tick, int):
                    tick = str(tick)
                input = {'종목코드':code, '틱범위': tick, '수정주가구분': "1"}
                output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if cycle == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': "1"}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': "1"}
                output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            dict_list = self._fetch_chart_data(rqname, trcode, input, output, screen, times)
            
            if not dict_list:
                logging.warning(f'{rqname} 데이타 얻기 실패: code:{code}, cycle:{cycle}, tick:{tick}')
                return dict_list
            
            logging.debug(f'{rqname}: code:{code}, cycle:{cycle}, tick:{tick}, count:{len(dict_list)} {dict_list[:1]}')
            
            # 데이터 변환
            dict_list = self._convert_chart_data(dict_list, code, cycle)
            
            if cycle in ['dy', 'mi']:
                cht_dt.set_chart_data(code, dict_list, cycle, int(tick))
                self.order('dbm', 'upsert_chart', dict_list, cycle, tick)
                self._mark_done(code, cycle)
            
            return dict_list
        
        except Exception as e:
            logging.error(f'{rqname} 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []

    def _fetch_chart_data(self, rqname, trcode, input, output, screen, times):
        """차트 데이터 fetch"""
        next = '0'
        dict_list = []
        
        while True:
            result = self.answer('api', 'api_request', rqname, trcode, input, output, next=next, screen=screen)
            if result is None:
                break
            
            data, remain = result
            if data is None or len(data) == 0: 
                break
                
            dict_list.extend(data)
            times -= 1
            if not remain or times <= 0: 
                break
            next = '2'
        
        return dict_list

    def _convert_chart_data(self, dict_list, code, cycle):
        """차트 데이터 변환"""
        if cycle in ['mi', 'tk']:
            return [{
                '종목코드': code,
                '체결시간': item['체결시간'] if item['체결시간'] else datetime.now().strftime('%Y%m%d%H%M%S'),
                '시가': abs(int(item['시가'])) if item['시가'] else 0,
                '고가': abs(int(item['고가'])) if item['고가'] else 0,
                '저가': abs(int(item['저가'])) if item['저가'] else 0,
                '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                '거래대금': 0,
            } for item in dict_list]
        else:
            return [{
                '종목코드': code,
                '일자': item['일자'] if item['일자'] else datetime.now().strftime('%Y%m%d'),
                '시가': abs(int(item['시가'])) if item['시가'] else 0,
                '고가': abs(int(item['고가'])) if item['고가'] else 0,
                '저가': abs(int(item['저가'])) if item['저가'] else 0,
                '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                '거래대금': abs(int(item['거래대금'])) if item['거래대금'] else 0,
            } for item in dict_list]

    def run_main_work(self):
        if self.latch_on: return
        self.latch_on = True
        self.request_chart_data()
        self.latch_on = False

    def request_chart_data(self):
        if not self.todo_code: return
        with self.lock:
            code, status = list(self.todo_code.items())[0]
        
        logging.debug(f"get_first_chart_data 요청: {code}")
        if not status['mi']: 
            self.get_first_chart_data(code, cycle='mi', tick=1)
            #self._mark_done(code, 'mi')
            return
        
        if not status['dy']: 
            self.get_first_chart_data(code, cycle='dy')
            #self._mark_done(code, 'dy')

    def _mark_done(self, code, cycle):
        with self.lock:
            if code in self.todo_code:
                self.todo_code[code][cycle] = True
                if all(self.todo_code[code].values()):
                    self.done_code.add(code)
                    del self.todo_code[code]

    def register_code(self, code):
        if not code: return False
        with self.lock:
            if not code or code in self.done_code or code in self.todo_code:
                return False
            
            logging.debug(f'차트관리 종목코드 등록: {code}')
            self.todo_code[code] = {'mi': False, 'dy': False}
            return True

    def is_done(self, code):
        return code in self.done_code

class DummyClass:
    def __init__(self):
        self.lock = threading.Lock()
        self.cht_updater = {}
        self.latch_on = True

    def latch_off(self):
        self.latch_on = False

    def run_main_work(self):
        if self.latch_on: return
        self.latch_on = True
        self.chart_data_updater()
        self.latch_on = False

    def register_chart_data(self, job):
        code = job['code']
        dictFID = job['dictFID']
        if cht_dt.is_code_registered(code):
            with self.lock: 
                self.cht_updater[code] = dictFID

    def chart_data_updater(self):
        with self.lock:
            cht_updater_items = list(self.cht_updater.items())
        for code, job in cht_updater_items:
            cht_dt.update_chart(
                code, 
                abs(int(job['현재가'])) if job['현재가'] else 0,
                abs(int(job['누적거래량'])) if job['누적거래량'] else 0,
                abs(int(job['누적거래대금'])) if job['누적거래대금'] else 0,
                job['체결시간']
            )
            with self.lock: 
                del self.cht_updater[code]

# 예제 실행
if __name__ == '__main__':
    mi3 = ChartManager('005930', 'mi', 3)

    ma5 = mi3.indicator(mi3.ma, mi3.c, 5)
    ma20 = mi3.indicator(mi3.ma, mi3.c, 20)

    c1 = ma5() > ma20() and mi3.c > ma5()
    c2 = ma5(1) < ma5() and ma20(1) < ma20()

    result = ma5(1)

    print(result)