from public import dc, gm, get_path, save_json, load_json
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from typing import Dict, Any, List, Callable, Optional, Tuple, Union
from PyQt5.QtGui import QColor
from datetime import datetime
import multiprocessing as mp
from multiprocessing import shared_memory
import threading
import queue
import copy
import time
import logging
import uuid
import os
import numpy as np
import json
import pickle
import msgpack
    
import logging
import uuid
import time
import threading
import multiprocessing as mp
import queue

class ThreadSafeList:
    def __init__(self):
        self.list = []
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock) # self.lock으로 wait, notify 를 관리

    def put(self, item):
        with self.lock:
            if isinstance(item, dict):
                print('put', len(self.list))
            self.list.append(item)
            self.not_empty.notify() # 대기중인 스레드에게 알림

    def get(self):
        # 리스트가 비어있으면 여기에서 대기
        with self.lock:
            if self.empty():
                self.not_empty.wait() # 대기
            if isinstance(self.list[0], dict):
                print('get', len(self.list))
            return self.list.pop(0)

    def remove(self, item):
        with self.lock:
            if item in self.list:
                self.list.remove(item)

    def contains(self, item):
        with self.lock:
            return item in self.list

    def empty(self):
        return len(self.list) == 0

class ThreadSafeDict:
    def __init__(self):
        self.dict = {}
        # 읽기-쓰기 락 사용 (여러 스레드가 동시에 읽을 수 있음)
        from PyQt5.QtCore import QReadWriteLock
        self.lock = QReadWriteLock()

    def items(self):
        self.lock.lockForRead()
        try:
            return list(self.dict.items())  # 복사본 반환
        finally:
            self.lock.unlock()

    def keys(self):
        self.lock.lockForRead()
        try:
            return list(self.dict.keys())  # 복사본 반환
        finally:
            self.lock.unlock()

    def values(self):
        self.lock.lockForRead()
        try:
            return list(self.dict.values())  # 복사본 반환
        finally:
            self.lock.unlock()

    def set(self, key, value=None, next=None):
        self.lock.lockForWrite()
        try:
            if next is None:
                self.dict[key] = copy.deepcopy(value) if value is not None else {}
            else:
                if key not in self.dict:
                    self.dict[key] = {}
                self.dict[key][next] = copy.deepcopy(value) if value is not None else {}
        finally:
            self.lock.unlock()

    def get(self, key, next=None):
        self.lock.lockForRead()
        try:
            if next is None:
                value = self.dict.get(key)
                return copy.deepcopy(value) if value is not None else None
            else:
                if key not in self.dict:
                    return None
                value = self.dict[key].get(next)
                return copy.deepcopy(value) if value is not None else None
        except Exception as e:
            logging.error(f"ThreadSafeDict get 오류: {e}")
            return None
        finally:
            self.lock.unlock()

    def contains(self, item):
        self.lock.lockForRead()
        try:
            return item in self.dict
        finally:
            self.lock.unlock()

    def remove(self, key, next=None):
        self.lock.lockForWrite()
        try:
            if next is None:
                return copy.deepcopy(self.dict.pop(key, None))
            elif key in self.dict:
                return copy.deepcopy(self.dict[key].pop(next, None))
            return None
        except Exception as e:
            logging.error(f"ThreadSafeDict remove 오류: {e}")
            return None
        finally:
            self.lock.unlock()
            
    # 원자적 작업을 위한 새 메서드
    def update_if_exists(self, key, next, value):
        """존재하는 경우에만 업데이트 (contains + set을 원자적으로 수행)"""
        self.lock.lockForWrite()
        try:
            if key in self.dict:
                if next is None:
                    self.dict[key] = copy.deepcopy(value) if value is not None else {}
                    return True
                else:
                    self.dict[key][next] = copy.deepcopy(value) if value is not None else {}
                    return True
            return False
        finally:
            self.lock.unlock()

class Toast(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.label = QLabel(self)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 180);
                border-radius: 10px;
                padding: 10px 20px;
                font: 12px;
            }
        """)

    def toast(self, message, duration=2000):
        self.label.setText(message)
        self.label.adjustSize()
        self.adjustSize()

        # 활성화된 창의 중앙에 위치
        active_window = QApplication.activeWindow()
        if active_window:
            rect = active_window.geometry()
            x = rect.center().x() - self.width() / 2
            y = rect.center().y() - self.height() / 2
            self.move(x, y)

        self.show()
        QTimer.singleShot(duration, self.hide)

    def mousePressEvent(self, event):
        self.hide()

class CounterTicker:
    """
    쓰레드 안전한, 전략별 종목 매수 횟수 카운터 클래스
    날짜가 변경되면 자동으로 카운터를 초기화합니다.
    """
    DEFAULT_STRATEGY_LIMIT = 1000   # 전략 자체 기본 제한
    DEFAULT_TICKER_LIMIT = 10       # 종목 기본 제한
    DEFAULT_DATA = { "date": dc.td.ToDay, "data": {} } # data = { strategy: {code: { name: "", limit: 0, count: 0 }, ... } } 
   
    def __init__(self, file_name="counter_data.json"):
        data_path = get_path('db')
        self.file_path = os.path.join(data_path, file_name)
        self.lock = threading.RLock()
        self.data = {}
        self.whole_count = self.DEFAULT_STRATEGY_LIMIT
        self.load_data()
    
    def load_data(self):
        with self.lock:
            success, loaded_data = load_json(self.file_path, self.DEFAULT_DATA)
            if success:
                saved_date = loaded_data.get("date", "")
                self.data = loaded_data.get("data", {})
                if saved_date != dc.td.ToDay: self.data = {}
    
    def save_data(self):
        with self.lock:
            save_obj = { "date": dc.td.ToDay, "data": self.data }
            success, _ = save_json(self.file_path, save_obj)
            return success
    
    def set_strategy(self, strategy, name, strategy_limit=None, ticker_limit=None):
        with self.lock:
            update = False
            if strategy not in self.data: 
                self.data[strategy] = {}
                self.data[strategy]["000000"] = { 
                    "name": name, 
                    "all": ticker_limit if ticker_limit is not None else self.DEFAULT_TICKER_LIMIT, 
                    "limit": strategy_limit if strategy_limit is not None else self.DEFAULT_STRATEGY_LIMIT, 
                    "count": 0 }
                update = True
            else:
                if self.data[strategy]["000000"]["name"] != name:
                    self.data[strategy]["000000"]["name"] = name
                    update = True
                if strategy_limit is not None:
                    if self.data[strategy]["000000"]["limit"] != strategy_limit:
                        self.data[strategy]["000000"].update({ "limit": strategy_limit, "count": 0 })
                        update = True
                if ticker_limit is not None:
                    if self.data[strategy]["000000"]["all"] != ticker_limit:
                        self.data[strategy]["000000"].update({ "all": ticker_limit, "count": 0 })
                        update = True
            if update: self.save_data()
    
    def set_batch(self, data):
        with self.lock:
            for strategy, codes in data.items(): 
                for code, name in codes.items():
                    self.set(strategy, code, name)
            self.save_data()

    def set(self, strategy, code, name, limit=0):
        if strategy not in self.data:
            self.set_strategy(strategy, name)
        with self.lock:
            self.data[strategy][code] = { "name": name, "limit": limit, "count": 0 }
            self.save_data()

    def set_add(self, strategy, code):
        with self.lock:
            self.data[strategy][code]["count"] += 1
            self.data[strategy]["000000"]["count"] += 1
            self.save_data()
    
    def get(self, strategy, code, name=None):
        with self.lock:
            if code not in self.data[strategy]:
                self.set(strategy, code, name if name is not None else "")
            if self.data[strategy]["000000"]["count"] >= self.data[strategy]["000000"]["limit"]:
                return False
            ticker_info = self.data[strategy][code]
            ticker_limit = ticker_info["limit"] if ticker_info["limit"] > 0 else self.data[strategy]["000000"]["all"]
            return ticker_info["count"] < ticker_limit

class TimeLimiter:
    def __init__(self, name, second=5, minute=100, hour=1000):
        self.name = name
        self.SEC = second
        self.MIN = minute
        self.HOUR = hour
        self.request_count = { 'second': 0, 'minute': 0, 'hour': 0 }
        self.first_request_time = { 'second': 0, 'minute': 0, 'hour': 0 }
        self.condition_times = {}  # 조건별 마지막 실행 시간
        self.lock = threading.Lock()

    def check_interval(self) -> int:
        current_time = time.time() * 1000
        with self.lock:
            if current_time - self.first_request_time['second'] >= 1000:
                self.request_count['second'] = 0
                self.first_request_time['second'] = 0
            if current_time - self.first_request_time['minute'] >= 60000:
                self.request_count['minute'] = 0
                self.first_request_time['minute'] = 0
            if current_time - self.first_request_time['hour'] >= 3600000:
                self.request_count['hour'] = 0
                self.first_request_time['hour'] = 0

            wait_time = 0
            if self.request_count['second'] >= self.SEC:
                wait_time = max(wait_time, 1000 - (current_time - self.first_request_time['second']))
            elif self.request_count['minute'] >= self.MIN:
                wait_time = max(wait_time, 60000 - (current_time - self.first_request_time['minute']))
            elif self.request_count['hour'] >= self.HOUR:
                wait_time = max(wait_time, 3600000 - (current_time - self.first_request_time['hour']))
            return max(0, wait_time)

    def check_condition_interval(self, condition) -> int:
        current_time = time.time() * 1000
        with self.lock:
            last_time = self.condition_times.get(condition, 0)

            if current_time - last_time >= 60000:  # 1분(60000ms) 체크
                if condition in self.condition_times:
                    del self.condition_times[condition]
                return 0
            wait_time = int(60000 - (current_time - last_time))
            return max(0, wait_time)

    def update_request_times(self):
        current_time = time.time() * 1000
        with self.lock:
            if self.request_count['second'] == 0:
                self.first_request_time['second'] = current_time
            if self.request_count['minute'] == 0:
                self.first_request_time['minute'] = current_time
            if self.request_count['hour'] == 0:
                self.first_request_time['hour'] = current_time

            self.request_count['second'] += 1
            self.request_count['minute'] += 1
            self.request_count['hour'] += 1

    def update_condition_time(self, condition):
        with self.lock:
            self.condition_times[condition] = time.time() * 1000
        self.update_request_times()

class DataManager:
    def __init__(self, config):
        """
        쓰레드 안전한 데이터 관리 클래스 초기화
        
        Parameters:
        config (dict): 설정 정보 딕셔너리
            - '키': 고유 키로 사용할 컬럼명
            - '정수': 정수형으로 변환할 컬럼 리스트
            - '실수': 실수형으로 변환할 컬럼 리스트
            - '컬럼': 전체 컬럼 리스트
            - '헤더': 화면용 컬럼 리스트
        """
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        
        # RLock 대신 QReadWriteLock 사용
        from PyQt5.QtCore import QReadWriteLock
        self.lock = QReadWriteLock()
        
        # 설정 정보 저장
        self.key_column = config.get('키', '')
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('확장', config.get('컬럼', []))
        self.display_columns = config.get('헤더', [])
        
        if not self.key_column: raise ValueError("'키' 컬럼을 지정해야 합니다.")
        if not self.all_columns: raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
        
        # 자주 사용하는 상수와 객체 미리 정의
        # 정렬 상수
        self.align_right = Qt.AlignRight | Qt.AlignVCenter
        self.align_left = Qt.AlignLeft | Qt.AlignVCenter
        self.align_center = Qt.AlignCenter
        
        # 색상 객체
        self.color_positive = QColor(255, 0, 0)  # 적색 (손익 양수)
        self.color_negative = QColor(0, 0, 255)  # 청색 (손익 음수)
        self.color_zero = QColor(0, 0, 0)        # 검정색 (손익 0)
        
        # 손익 관련 컬럼
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률", "등락율"]

        # 리사이즈
        self._resize = True
    
    def _convert_value(self, column, value):
        """
        값을 적절한 타입으로 변환
        
        Parameters:
        column (str): 컬럼명
        value: 변환할 값
        
        Returns:
        변환된 값
        """
        # 기본값 정의
        default_values = {
            'int': 0,
            'float': 0.0,
            'str': ""
        }
        
        # 문자열 처리
        if isinstance(value, str):
            value = value.strip()
            if column not in self.int_columns + self.float_columns:
                return value
            
            # 쉼표가 포함된 숫자 문자열 처리
            if any(c.isdigit() for c in value):
                value = value.replace(',', '')
        
        # None이나 빈 문자열은 기본값으로
        if value is None or value == "":
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                default_values['str']
        
        # 타입별 변환
        try:
            if column in self.int_columns:
                return int(float(value))
            elif column in self.float_columns:
                return float(value)
            else:
                # 불리언 및 기타 타입은 그대로 유지
                return value
        except (ValueError, TypeError):
            # 변환 실패 시 기본값 반환
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                str(value)
            
    def _process_item(self, item):
        """
        항목의 각 값을 적절한 타입으로 변환
        
        Parameters:
        item (dict): 변환할 항목
        
        Returns:
        dict: 변환된 항목
        """
        processed_item = {}
        # 모든 컬럼을 기본값으로 먼저 초기화
        for column in self.all_columns:
            if column in self.int_columns:
                processed_item[column] = 0
            elif column in self.float_columns:
                processed_item[column] = 0.0
            else:
                processed_item[column] = ""
                
        # 주어진 값으로 업데이트
        for column in self.all_columns:
            if column in item:
                processed_item[column] = self._convert_value(column, item.get(column, ''))
        
        return processed_item
    
    def get(self, key=None, filter=None, type=None, column=None):
        """
        get() -> [{}]                     # 전체 데이터 사전 리스트 반환
        get(type='df') -> DataFrame       # DataFrame으로 반환
        get(key='key') -> {}              # 'key'로 찾은 행 반환
        get(key=숫자) -> {}               # 인덱스로 행 반환
        get(filter={}) -> [{}]            # 조건에 맞는 행들 반환
        get(filter={}, column='col') -> []  # 조건에 맞는 행들의 특정 컬럼 값들 리스트 반환
        get(column='col') -> []           # 특정 컬럼 값들 리스트 반환
        get(column=['c1','c2']) -> [{}]   # 지정 컬럼만 포함한 사전 리스트 반환
        get(key='key', column='col') -> 값  # 특정 행의 특정 컬럼 값 반환
        get(key='key', column=['c1','c2']) -> (값1, 값2, ...)  # 특정 행의 여러 컬럼 값 튜플 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            # 0. 키가 정수형인 경우
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return None
            
            # 1. 특정 키 + 특정 컬럼 조회
            if key is not None and column is not None:
                item = self.data_dict.get(key)
                if item is None:
                    return None
                
                # 컬럼이 리스트인 경우 (여러 컬럼 조회)
                if isinstance(column, (list, tuple)):
                    if len(column) == 1:
                        # 단일 컬럼이면 값만 반환
                        return item.get(column[0])
                    else:
                        # 여러 컬럼이면 튜플로 반환
                        return tuple(item.get(col) for col in column)
                # 컬럼이 문자열인 경우 (단일 컬럼 조회)
                elif isinstance(column, str):
                    return item.get(column)
                return None
            
            # 2. 전체 데이터 + 특정 컬럼 조회
            if column is not None:
                # 컬럼이 리스트인 경우
                if isinstance(column, (list, tuple)):
                    result = []
                    for item in self.data:
                        filtered_item = {col: item.get(col) for col in column if col in item}
                        result.append(filtered_item)
                    return copy.deepcopy(result)
                # 컬럼이 문자열인 경우
                elif isinstance(column, str):
                    # 단일 컬럼이면 값만 추출하여 리스트로 반환
                    return [item.get(column) for item in self.data]
            
            # 3. 특정 키 조회
            if key is not None:
                item = self.data_dict.get(key)
                return copy.deepcopy(item) if item else None
            
            # 4. 필터링 조회
            if filter is not None:
                return self._filter_data(filter)
            
            # 5. 전체 데이터 조회
            data_copy = copy.deepcopy(self.data)
            
            # 6. DataFrame 반환 요청인 경우
            if type == 'df':
                try:
                    import pandas as pd
                    return pd.DataFrame(data_copy)
                except ImportError:
                    raise ImportError("pandas 라이브러리가 필요합니다. 'pip install pandas'로 설치하세요.")
            
            # 기본적으로 리스트 반환
            return data_copy
        finally:
            self.lock.unlock()
    
    def set(self, key=None, filter=None, data=None):
        """
        set(key='key', data={}) -> bool   # 특정 키 행 추가/업데이트
        set(filter={}, data={}) -> bool   # 조건 만족 행들 업데이트
        set(data={}) -> bool              # 모든 행의 지정 컬럼 업데이트
        set(data=[{}, {}]) -> bool        # 전체 데이터 대체
        """
        if data is None:
            return False
            
        # 리스트 타입 체크 (데이터 대체 모드)
        if isinstance(data, list):
            # 쓰기 락 사용
            self.lock.lockForWrite()
            try:
                # 키 필드 검증
                for item in data:
                    if self.key_column not in item:
                        raise ValueError(f"모든 항목에 키 컬럼('{self.key_column}')이 필요합니다.")
                
                # 데이터 대체
                self.data = []
                self.data_dict = {}
                for item in data:
                    key_value = item[self.key_column]
                    self._set_item_by_key(key_value, item)
                return True
            finally:
                self.lock.unlock()
            
        # 딕셔너리 타입 체크 (업데이트 모드)
        if isinstance(data, dict):
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data:
                return False
            
            # 쓰기 락 사용    
            self.lock.lockForWrite()
            try:
                # 1. 특정 키 업데이트/추가
                if key is not None:
                    return self._set_item_by_key(key, valid_data)
                
                # 2. 필터링된 항목 업데이트
                if filter is not None:
                    return self._update_filtered_items(filter, valid_data)
                
                # 3. 전체 항목 업데이트
                return self._update_all_items(valid_data)
            finally:
                self.lock.unlock()
                
        return False
    
    def _set_item_by_key(self, key, data):
        """키로 항목 추가/업데이트"""
        # 기존 항목이 있으면 업데이트
        item = self.data_dict.get(key)
        
        if item is not None:
            for column, value in data.items():
                if column in self.all_columns and column != self.key_column:
                    item[column] = self._convert_value(column, value)
            return True
        
        # 신규 항목 추가
        # 모든 컬럼 기본값으로 초기화
        item = {}
        for column in self.all_columns:
            if column == self.key_column:
                item[column] = key  # 키 값 설정
            else:
                # 기본값 설정
                if column in self.int_columns:
                    item[column] = 0
                elif column in self.float_columns:
                    item[column] = 0.0
                else:
                    item[column] = ""
        
        # 데이터 채우기
        for column, value in data.items():
            if column in self.all_columns:
                item[column] = self._convert_value(column, value)
        
        self.data.append(item)
        self.data_dict[key] = item
        self._resize = True
        return True
    
    def _update_filtered_items(self, filter, data):
        """필터링된 항목 업데이트"""
        updated = False
        for item in self.data:
            if self._match_conditions(item, filter):
                for column, value in data.items():
                    if column in self.all_columns and column != self.key_column:
                        item[column] = self._convert_value(column, value)
                updated = True
        return updated
    
    def _update_all_items(self, data):
        """모든 항목 업데이트"""
        if not self.data:
            return False
        
        for item in self.data:
            for column, value in data.items():
                if column in self.all_columns and column != self.key_column:
                    item[column] = self._convert_value(column, value)
        return True
    
    def delete(self, key=None, filter=None):
        """
        delete() -> bool                  # 모든 데이터 삭제
        delete(key='key') -> bool         # 특정 키 행 삭제
        delete(filter={}) -> bool         # 조건 만족 행들 삭제
        """
        # 쓰기 락 사용
        self.lock.lockForWrite()
        try:
            # 1. 특정 키 삭제
            if key is not None:
                item = self.data_dict.pop(key, None)
                if item is not None and item in self.data:
                    self.data.remove(item)
                    self._resize = True
                    return True
                return False
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if not items_to_delete:
                    return False
                    
                for item in items_to_delete:
                    key_val = item.get(self.key_column)
                    self.data_dict.pop(key_val, None)
                    if item in self.data:
                        self.data.remove(item)
                
                if items_to_delete:
                    self._resize = True
                    
                return bool(items_to_delete)
            
            # 3. 전체 데이터 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            return True
        finally:
            self.lock.unlock()
    
    def len(self, filter=None):
        """
        len() -> int                      # 전체 행 수 반환
        len(filter={}) -> int             # 조건 만족 행 수 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
        finally:
            self.lock.unlock()
    
    def in_key(self, key):
        """
        in_key('key') -> bool             # 키 존재 여부
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            return key in self.data_dict
        finally:
            self.lock.unlock()
    
    def in_column(self, column, value):
        """
        in_column('col', 값) -> bool      # 컬럼에 값 존재 여부
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if column not in self.all_columns:
                return False
            
            # 타입 변환
            converted_value = self._convert_value(column, value)
            
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
        finally:
            self.lock.unlock()
    
    def sum(self, column=None, filter=None):
        """
        sum(column=['c1', 'c2']) -> (합1, 합2, ...)  # 지정 컬럼 합계 튜플 반환
        sum(column=[], filter={}) -> (합1, 합2, ...)  # 조건 만족 행들의 합계 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if not column:
                return ()
            
            # 합계 계산할 데이터 선택
            data_to_sum = self.data
            if filter is not None:
                data_to_sum = self._filter_data(filter)
            
            # 각 컬럼별 합계 계산
            result = []
            if isinstance(column, str):
                column = [column]
            for col in column:
                if col in self.int_columns or col in self.float_columns:
                    total = sum(item.get(col, 0) for item in data_to_sum)
                    result.append(total)
                else:
                    # 숫자형이 아닌 컬럼은 0 반환
                    result.append(0)
            
            return tuple(result)
        finally:
            self.lock.unlock()
    
    def _find_item_by_key(self, key):
        """키 값으로 항목 찾기 - 딕셔너리 사용으로 O(1) 성능"""
        return self.data_dict.get(key)
    
    def _find_index_by_key(self, key):
        """키 값으로 인덱스 찾기"""
        item = self.data_dict.get(key)
        if item is not None:
            try:
                return self.data.index(item)
            except ValueError:
                pass
        return None
    
    def _filter_data(self, conditions):
        """
        # conditions : {컬럼: 값} 컬럼과 값 비교
        {'col': 값}
        # conditions : {컬럼: (연산자, 값)}
        {'col': ('>', 값)}                # col > 값
        {'col': ('<', 값)}                # col < 값
        {'col': ('>=', 값)}               # col >= 값
        {'col': ('<=', 값)}               # col <= 값
        {'col': ('==', 값)}               # col == 값
        {'col': ('!=', 값)}               # col != 값
        {'col': ('>', '@other_col')}      # col > other_col (컬럼 간 비교)
        """
        result = []
        for row in self.data:
            if self._match_conditions(row, conditions):
                result.append(copy.deepcopy(row))
        return result
    
    def _match_conditions(self, row, conditions):
        """항목이 조건에 맞는지 확인"""
        for column, value in conditions.items():
            if column not in row:
                return False
                
            item_value = row[column]
            
            # 문자열인 경우 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 컬럼 간 비교인 경우 ('컬럼' 또는 '@컬럼')
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                # '@'로 시작하는 문자열은 다른 컬럼을 참조
                if isinstance(compare_value, str) and compare_value.startswith('@'):
                    other_column = compare_value[1:]  # '@' 제거
                    if other_column not in row:
                        return False
                    other_value = row[other_column]
                    if not self._compare_values(item_value, op, other_value):
                        return False
                # 일반 비교값
                else:
                    if not self._compare_values(item_value, op, compare_value):
                        return False
            # 그 외의 경우 정확히 일치하는지 확인
            elif item_value != value:
                return False
                
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """숫자형 값 비교 연산"""
        ops = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y,
            '!=': lambda x, y: x != y
        }
        
        if operator in ops:
            try:
                return ops[operator](item_value, compare_value)
            except (TypeError, ValueError):
                return False
        return False

    def update_table_widget(self, table_widget, stretch=True):
        """
        저장된 데이터를 테이블 위젯에 표시
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        stretch (bool): 마지막 열을 테이블 너비에 맞게 늘릴지 여부
        """
        # 락 사용 최소화 - 데이터 스냅샷만 빠르게 복사
        self.lock.lockForRead()
        try:
            if not self.data:
                table_widget.setRowCount(0)
                return
                
            data_copy = copy.deepcopy(self.data)
            columns = self.display_columns or self.all_columns
            resize_needed = self._resize
            
            if resize_needed:
                self._resize = False
        finally:
            self.lock.unlock()
        
        # UI 업데이트는 락 없이 수행
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        
        try:
            # 테이블 크기 확인 및 조정
            if table_widget.rowCount() != len(data_copy) or table_widget.columnCount() != len(columns):
                resize_needed = True
                
            if resize_needed:
                table_widget.setRowCount(len(data_copy))
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
            
            # 데이터 표시
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column])
            
            # 테이블 크기 조정
            if resize_needed:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                
                if stretch:
                    table_widget.horizontalHeader().setStretchLastSection(stretch)
        except Exception as e:
            logging.error(f'update_table_widget 오류: {type(e).__name__} - {e}', exc_info=True)
        finally:
            table_widget.setUpdatesEnabled(True)
            table_widget.setSortingEnabled(True)

    def _set_table_cell(self, table_widget, row, col, column, value):
        """테이블의 특정 셀에 값 설정"""
        original_value = str(value)
        
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value)
            # "스크립트" 컬럼의 경우 마지막 줄만 표시
            if column == '스크립트' and '\n' in display_value:
                lines = display_value.split('\n')
                # 마지막 줄이 비어있으면 그 전 줄을 사용
                last_line = lines[-1] if lines[-1].strip() else lines[-2] if len(lines) > 1 else lines[0]
                display_value = last_line if last_line.strip() else "(빈 줄)"
                
        # 기존 아이템 재사용
        existing_item = table_widget.item(row, col)
        if existing_item:
            # 값이 같으면 업데이트 필요 없음
            if existing_item.text() == display_value:
                return
            existing_item.setText(display_value)
            existing_item.setData(Qt.UserRole, original_value)
            cell_item = existing_item
        else:
            cell_item = QTableWidgetItem(display_value)
            cell_item.setData(Qt.UserRole, original_value)
            table_widget.setItem(row, col, cell_item)
        
        # 정렬 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(self.align_right)
        else:
            cell_item.setTextAlignment(self.align_left)
        
        # 손익 관련 컬럼 색상 설정
        if column in self.profit_columns:
            if isinstance(value, (int, float)):
                if value < 0:
                    cell_item.setForeground(self.color_negative)  # 음수는 청색
                elif value > 0:
                    cell_item.setForeground(self.color_positive)  # 양수는 적색
                else:
                    cell_item.setForeground(self.color_zero)      # 0은 검정색

class TableManager:
    def __init__(self, config):
        """
        쓰레드 안전한 데이터 관리 클래스 초기화
        
        Parameters:
        config (dict): 설정 정보 딕셔너리
            - '키': 고유 키로 사용할 컬럼명 또는 컬럼명 리스트 (복합 키)
                    None이면 키 없는 모드로 동작
            - '키중복': True면 동일 키 값을 갖는 여러 행 허용 (기본값: False)
            - '정수': 정수형으로 변환할 컬럼 리스트
            - '실수': 실수형으로 변환할 컬럼 리스트
            - '컬럼': 전체 컬럼 리스트
            - '헤더': 화면용 컬럼 리스트 또는 리스트의 리스트 (여러 헤더 셋)
        """
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        
        # RLock 대신 QReadWriteLock 사용
        from PyQt5.QtCore import QReadWriteLock
        self.lock = QReadWriteLock()
        
        # 설정 정보 저장
        self.key_columns = config.get('키', None)
        
        # key_columns가 문자열이면 리스트로 변환
        if isinstance(self.key_columns, str):
            self.key_columns = [self.key_columns]
            
        # 키 중복 허용 여부
        self.allow_duplicate_keys = config.get('키중복', False)
        
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('확장', config.get('컬럼', []))
        
        # 헤더 설정 - 리스트의 리스트로 처리
        header_config = config.get('헤더', [])
        if header_config and not isinstance(header_config[0], list):
            # 단일 리스트인 경우, 리스트의 리스트로 변환
            self.display_columns = [header_config]
        else:
            self.display_columns = header_config
            
        # 헤더가 없는 경우 all_columns 사용
        if not self.display_columns:
            self.display_columns = [self.all_columns]

        # 키가 있는 경우 키 컬럼이 all_columns에 있는지 확인
        if self.key_columns:
            for key_col in self.key_columns:
                if key_col not in self.all_columns:
                    raise ValueError(f"키 컬럼 '{key_col}'이 '컬럼' 리스트에 없습니다.")
        
        if not self.all_columns:
            raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
        
        # 자주 사용하는 상수와 객체 미리 정의
        # 정렬 상수
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor
        
        self.align_right = Qt.AlignRight | Qt.AlignVCenter
        self.align_left = Qt.AlignLeft | Qt.AlignVCenter
        self.align_center = Qt.AlignCenter
        
        # 색상 객체
        self.color_positive = QColor(255, 0, 0)  # 적색 (손익 양수)
        self.color_negative = QColor(0, 0, 255)  # 청색 (손익 음수)
        self.color_zero = QColor(0, 0, 0)        # 검정색 (손익 0)
        
        # 손익 관련 컬럼
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률", "등락율"]

        # 리사이즈
        self._resize = True
        
        # 키 없는 모드인지 여부
        self.no_key_mode = self.key_columns is None
    
    def _get_key_for_item(self, item):
        """
        항목에서 키 값을 추출
        
        Parameters:
        item (dict): 키 값을 추출할 항목
        
        Returns:
        키 없는 모드면 None, 단일 키면 값, 복합 키면 튜플
        """
        if self.no_key_mode:
            return None
            
        if len(self.key_columns) == 1:
            return item.get(self.key_columns[0])
        else:
            # 복합 키는 튜플로 반환
            return tuple(item.get(key_col) for key_col in self.key_columns)
    
    def _convert_value(self, column, value):
        """
        값을 적절한 타입으로 변환
        
        Parameters:
        column (str): 컬럼명
        value: 변환할 값
        
        Returns:
        변환된 값
        """
        # 기본값 정의
        default_values = {
            'int': 0,
            'float': 0.0,
            'str': ""
        }
        
        # 문자열 처리
        if isinstance(value, str):
            value = value.strip()
            if column not in self.int_columns + self.float_columns:
                return value
            
            # 쉼표가 포함된 숫자 문자열 처리
            if any(c.isdigit() for c in value):
                value = value.replace(',', '')
        
        # None이나 빈 문자열은 기본값으로
        if value is None or value == "":
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                default_values['str']
        
        # 타입별 변환
        try:
            if column in self.int_columns:
                return int(float(value))
            elif column in self.float_columns:
                return float(value)
            else:
                # 불리언 및 기타 타입은 그대로 유지
                return value
        except (ValueError, TypeError):
            # 변환 실패 시 기본값 반환
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                str(value)
            
    def _process_item(self, item):
        """
        항목의 각 값을 적절한 타입으로 변환
        
        Parameters:
        item (dict): 변환할 항목
        
        Returns:
        dict: 변환된 항목
        """
        processed_item = {}
        # 모든 컬럼을 기본값으로 먼저 초기화
        for column in self.all_columns:
            if column in self.int_columns:
                processed_item[column] = 0
            elif column in self.float_columns:
                processed_item[column] = 0.0
            else:
                processed_item[column] = ""
                
        # 주어진 값으로 업데이트
        for column in self.all_columns:
            if column in item:
                processed_item[column] = self._convert_value(column, item.get(column, ''))
        
        return processed_item

    def get(self, key=None, filter=None, type=None, column=None):
        """
        get() -> [{}]                     # 전체 데이터 사전 리스트 반환
        get(type='df') -> DataFrame       # DataFrame으로 반환
        get(key='key') -> {}              # 'key'로 찾은 행 반환
        get(key=숫자) -> {}               # 인덱스로 행 반환
        get(key=(값1,값2)) -> [{}]        # 복합 키로 찾은 행(들) 반환
        get(filter={}) -> [{}]            # 조건에 맞는 행들 반환
        get(filter={}, column='col') -> []  # 조건에 맞는 행들의 특정 컬럼 값들 리스트 반환
        get(column='col') -> []           # 특정 컬럼 값들 리스트 반환
        get(column=['c1','c2']) -> [{}]   # 지정 컬럼만 포함한 사전 리스트 반환
        get(key='key', column='col') -> 값  # 특정 행의 특정 컬럼 값 반환
        get(key='key', column=['c1','c2']) -> (값1, 값2, ...)  # 특정 행의 여러 컬럼 값 튜플 반환
        """
        import copy
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            # 0. 키가 정수형인 경우 (인덱스로 접근)
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return None
            
            # 1. 특정 키 + 특정 컬럼 조회
            if key is not None and column is not None:
                items = self._find_items_by_key(key)
                if not items:
                    return None
                
                # 키 중복 허용이 아닌 경우 첫 번째 항목만 사용
                item = items[0] if isinstance(items, list) else items
                
                # 컬럼이 리스트인 경우 (여러 컬럼 조회)
                if isinstance(column, (list, tuple)):
                    if len(column) == 1:
                        # 단일 컬럼이면 값만 반환
                        return item.get(column[0])
                    else:
                        # 여러 컬럼이면 튜플로 반환
                        return tuple(item.get(col) for col in column)
                # 컬럼이 문자열인 경우 (단일 컬럼 조회)
                elif isinstance(column, str):
                    return item.get(column)
                return None
            
            # 2. 전체 데이터 + 특정 컬럼 조회
            if column is not None:
                # 컬럼이 리스트인 경우
                if isinstance(column, (list, tuple)):
                    result = []
                    for item in self.data:
                        filtered_item = {col: item.get(col) for col in column if col in item}
                        result.append(filtered_item)
                    return copy.deepcopy(result)
                # 컬럼이 문자열인 경우
                elif isinstance(column, str):
                    # 단일 컬럼이면 값만 추출하여 리스트로 반환
                    return [item.get(column) for item in self.data]
                
            # 3. 특정 키 조회
            if key is not None:
                items = self._find_items_by_key(key)
                if not items: return None

                # 키 중복 허용이면 여러 항목 반환 가능
                if self.allow_duplicate_keys and isinstance(items, list):
                    return copy.deepcopy(items)
                else:
                    # 중복 허용 아니면 첫 번째 항목만 반환
                    return copy.deepcopy(items)
            
            # 4. 필터링 조회
            if filter is not None:
                return self._filter_data(filter)
            
            # 5. 전체 데이터 조회
            data_copy = copy.deepcopy(self.data)
            
            # 6. DataFrame 반환 요청인 경우
            if type == 'df':
                try:
                    import pandas as pd
                    return pd.DataFrame(data_copy)
                except ImportError:
                    raise ImportError("pandas 라이브러리가 필요합니다. 'pip install pandas'로 설치하세요.")
            
            # 기본적으로 리스트 반환
            return data_copy
        finally:
            self.lock.unlock()
    
    def _find_items_by_key(self, key):
        """
        키 값으로 항목 찾기
        
        Parameters:
        key: 찾을 키 값
        
        Returns:
        중복 키 허용이면 항목 리스트, 아니면 단일 항목
        """
        if self.no_key_mode:
            return None
        
        if key not in self.data_dict:
            return None
        
        return self.data_dict.get(key)
    
    def _add_to_dict(self, key_value, item):
        """
        딕셔너리에 항목 추가
        
        Parameters:
        key_value: 키 값 (문자열, 숫자 또는 튜플)
        item (dict): 추가할 항목
        """
        if self.allow_duplicate_keys:
            # 중복 키 허용 모드: 리스트로 항목 저장
            if key_value in self.data_dict:
                self.data_dict[key_value].append(item)
            else:
                self.data_dict[key_value] = [item]
        else:
            # 중복 키 비허용 모드: 단일 항목 저장
            self.data_dict[key_value] = item

    def set(self, key=None, filter=None, data=None):
        """
        set(key='key', data={}) -> bool   # 특정 키 행 추가/업데이트
        set(key=(값1,값2), data={}) -> bool # 복합 키 행 추가/업데이트
        set(filter={}, data={}) -> bool   # 조건 만족 행들 업데이트
        set(data={}) -> bool              # 모든 행의 지정 컬럼 업데이트
        set(data=[{}, {}]) -> bool        # 전체 데이터 대체
        """
        if data is None:
            return False
                
        # 리스트 타입 체크 (데이터 대체 모드)
        if isinstance(data, list):
            # 쓰기 락 사용
            self.lock.lockForWrite()
            try:
                # 키 모드일 때 키 필드 검증
                if not self.no_key_mode:
                    for item in data:
                        for key_col in self.key_columns:
                            if key_col not in item:
                                raise ValueError(f"모든 항목에 키 컬럼('{key_col}')이 필요합니다.")
                
                # 데이터 대체
                self.data = []
                self.data_dict = {}
                for item in data:
                    processed_item = self._process_item(item)
                    self.data.append(processed_item)
                
                    # 키 모드일 때 딕셔너리에 추가
                    if not self.no_key_mode:
                        key_value = self._get_key_for_item(processed_item)
                        self._add_to_dict(key_value, processed_item)
                
                return True
            finally:
                self.lock.unlock()
            
        # 딕셔너리 타입 체크 (업데이트 모드)
        if isinstance(data, dict):
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data:
                return False
            
            # 쓰기 락 사용    
            self.lock.lockForWrite()
            try:
                # 1. 특정 키 업데이트/추가
                if key is not None:
                    return self._set_item_by_key(key, valid_data)
                
                # 2. 필터링된 항목 업데이트
                if filter is not None:
                    return self._update_filtered_items(filter, valid_data)
                
                # 3. 전체 항목 업데이트
                return self._update_all_items(valid_data)
            finally:
                self.lock.unlock()
                
        return False
    
    def _set_item_by_key(self, key, data):
        """
        키로 항목 추가/업데이트
        
        Parameters:
        key: 키 값 (단일 값 또는 복합 키 튜플)
        data (dict): 업데이트할 데이터
        
        Returns:
        bool: 성공 여부
        """
        if self.no_key_mode:
            # 키 없는 모드에서는 인덱스로 처리
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    for column, value in data.items():
                        if column in self.all_columns:
                            self.data[key][column] = self._convert_value(column, value)
                    return True
            return False
        
        # 기존 항목 찾기
        items = self._find_items_by_key(key)
        
        # 중복 허용 모드일 때
        if self.allow_duplicate_keys:
            if items:
                # 첫 번째 항목만 업데이트
                for column, value in data.items():
                    if column in self.all_columns and column not in self.key_columns:
                        items[0][column] = self._convert_value(column, value)
                return True
        elif items:
            # 중복 비허용 모드일 때 항목 업데이트
            for column, value in data.items():
                if column in self.all_columns and column not in self.key_columns:
                    items[column] = self._convert_value(column, value)
            return True
        
        # 신규 항목 추가
        # 모든 컬럼 기본값으로 초기화
        item = {}
        for column in self.all_columns:
            # 기본값 설정
            if column in self.int_columns:
                item[column] = 0
            elif column in self.float_columns:
                item[column] = 0.0
            else:
                item[column] = ""
        
        # 키 컬럼 설정
        if isinstance(key, tuple) and len(key) == len(self.key_columns):
            # 복합 키 처리
            for i, key_col in enumerate(self.key_columns):
                item[key_col] = key[i]
        elif len(self.key_columns) == 1:
            # 단일 키 처리
            item[self.key_columns[0]] = key
        
        # 데이터 채우기
        for column, value in data.items():
            if column in self.all_columns:
                item[column] = self._convert_value(column, value)
        
        # 데이터 추가
        self.data.append(item)
        self._add_to_dict(key, item)
        self._resize = True
        return True
    
    def _update_filtered_items(self, filter, data):
        """필터링된 항목 업데이트"""
        updated = False
        for item in self.data:
            if self._match_conditions(item, filter):
                # 키 컬럼은 업데이트하지 않음
                for column, value in data.items():
                    if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                        item[column] = self._convert_value(column, value)
                updated = True
        return updated
    
    def _update_all_items(self, data):
        """모든 항목 업데이트"""
        if not self.data:
            return False
        
        for item in self.data:
            for column, value in data.items():
                if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                    item[column] = self._convert_value(column, value)
        return True
    
    def delete(self, key=None, filter=None):
        """
        delete() -> bool                  # 모든 데이터 삭제
        delete(key='key') -> bool         # 특정 키 행 삭제
        delete(key=(값1,값2)) -> bool     # 복합 키 행 삭제
        delete(filter={}) -> bool         # 조건 만족 행들 삭제
        """
        # 쓰기 락 사용
        self.lock.lockForWrite()
        try:
            # 1. 특정 키 삭제
            if key is not None:
                # 키 없는 모드에서는 인덱스로 처리
                if self.no_key_mode:
                    if isinstance(key, int) and 0 <= key < len(self.data):
                        del self.data[key]
                        self._resize = True
                        return True
                    return False
                    
                # 키 모드에서는 키로 처리
                items = self._find_items_by_key(key)
                if not items:
                    return False
                
                if self.allow_duplicate_keys:
                    # 중복 키 허용 모드: 모든 항목 삭제
                    for item in items[:]:  # 복사본으로 반복
                        if item in self.data:
                            self.data.remove(item)
                    # 딕셔너리에서 키 삭제
                    self.data_dict.pop(key, None)
                else:
                    # 중복 키 비허용 모드: 단일 항목 삭제
                    if items in self.data:
                        self.data.remove(items)
                    self.data_dict.pop(key, None)
                    
                self._resize = True
                return True
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if not items_to_delete:
                    return False
                
                for item in items_to_delete:
                    # 키 모드일 때 딕셔너리에서도 삭제
                    if not self.no_key_mode:
                        key_val = self._get_key_for_item(item)
                        
                        if self.allow_duplicate_keys:
                            # 중복 키 허용 모드: 리스트에서 항목 제거
                            if key_val in self.data_dict:
                                items_list = self.data_dict[key_val]
                                if item in items_list:
                                    items_list.remove(item)
                                # 리스트가 비었으면 키 삭제
                                if not items_list:
                                    self.data_dict.pop(key_val, None)
                        else:
                            # 중복 키 비허용 모드: 키 삭제
                            self.data_dict.pop(key_val, None)
                
                if item in self.data:
                    self.data.remove(item)
                
                if items_to_delete:
                    self._resize = True
                
                return bool(items_to_delete)
            
            # 3. 전체 데이터 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            return True
        finally:
            self.lock.unlock()
    
    def _filter_data(self, conditions):
        """
        # conditions : {컬럼: 값} 컬럼과 값 비교
        {'col': 값}
        # conditions : {컬럼: (연산자, 값)}
        {'col': ('>', 값)}                # col > 값
        {'col': ('<', 값)}                # col < 값
        {'col': ('>=', 값)}               # col >= 값
        {'col': ('<=', 값)}               # col <= 값
        {'col': ('==', 값)}               # col == 값
        {'col': ('!=', 값)}               # col != 값
        {'col': ('>', '@other_col')}      # col > other_col (컬럼 간 비교)
        """
        import copy
        result = []
        for row in self.data:
            if self._match_conditions(row, conditions):
                result.append(copy.deepcopy(row))
        return result
    
    def _match_conditions(self, row, conditions):
        """항목이 조건에 맞는지 확인"""
        for column, value in conditions.items():
            if column not in row:
                return False
                
            item_value = row[column]
            
            # 문자열인 경우 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 컬럼 간 비교인 경우 ('컬럼' 또는 '@컬럼')
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                # '@'로 시작하는 문자열은 다른 컬럼을 참조
                if isinstance(compare_value, str) and compare_value.startswith('@'):
                    other_column = compare_value[1:]  # '@' 제거
                    if other_column not in row:
                        return False
                    other_value = row[other_column]
                    if not self._compare_values(item_value, op, other_value):
                        return False
                # 일반 비교값
                else:
                    if not self._compare_values(item_value, op, compare_value):
                        return False
            # 그 외의 경우 정확히 일치하는지 확인
            elif item_value != value:
                return False
                
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """숫자형 값 비교 연산"""
        ops = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y,
            '!=': lambda x, y: x != y
        }
        
        if operator in ops:
            try:
                return ops[operator](item_value, compare_value)
            except (TypeError, ValueError):
                return False
        return False

    def len(self, filter=None):
        """
        len() -> int                      # 전체 행 수 반환
        len(filter={}) -> int             # 조건 만족 행 수 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
        finally:
            self.lock.unlock()
    
    def in_key(self, key):
        """
        in_key('key') -> bool             # 키 존재 여부
        in_key((값1, 값2)) -> bool        # 복합 키 존재 여부
        """
        # 키 없는 모드에서는 항상 False
        if self.no_key_mode:
            return False
            
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            return key in self.data_dict
        finally:
            self.lock.unlock()
    
    def in_column(self, column, value):
        """
        in_column('col', 값) -> bool      # 컬럼에 값 존재 여부
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if column not in self.all_columns:
                return False
            
            # 타입 변환
            converted_value = self._convert_value(column, value)
            
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
        finally:
            self.lock.unlock()
    
    def sum(self, column=None, filter=None):
        """
        sum(column=['c1', 'c2']) -> (합1, 합2, ...)  # 지정 컬럼 합계 튜플 반환
        sum(column=[], filter={}) -> (합1, 합2, ...)  # 조건 만족 행들의 합계 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if not column:
                return ()
            
            # 합계 계산할 데이터 선택
            data_to_sum = self.data
            if filter is not None:
                data_to_sum = self._filter_data(filter)
            
            # 각 컬럼별 합계 계산
            result = []
            if isinstance(column, str):
                column = [column]
            for col in column:
                if col in self.int_columns or col in self.float_columns:
                    total = sum(item.get(col, 0) for item in data_to_sum)
                    result.append(total)
                else:
                    # 숫자형이 아닌 컬럼은 0 반환
                    result.append(0)
            
            return tuple(result)
        finally:
            self.lock.unlock()
    
    def update_table_widget(self, table_widget, stretch=True, header=0):
        """
        저장된 데이터를 테이블 위젯에 표시
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        stretch (bool): 마지막 열을 테이블 너비에 맞게 늘릴지 여부
        header (int): 사용할 헤더 세트의 인덱스 (기본값: 0)
        """
        import copy
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        # 락 사용 최소화 - 데이터 스냅샷만 빠르게 복사
        self.lock.lockForRead()
        try:
            if not self.data:
                table_widget.setRowCount(0)
                return
                
            data_copy = copy.deepcopy(self.data)
            if header < 0 or header >= len(self.display_columns):
                header = 0

            columns = self.display_columns[header]
            resize_needed = self._resize
            
            if resize_needed:
                self._resize = False
        finally:
            self.lock.unlock()
        
        # UI 업데이트는 락 없이 수행
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        
        try:
            # 테이블 크기 확인 및 조정
            if table_widget.rowCount() != len(data_copy) or table_widget.columnCount() != len(columns):
                resize_needed = True
                
            if resize_needed:
                table_widget.setRowCount(len(data_copy))
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
            
            # 데이터 표시
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column])
            
            # 테이블 크기 조정
            if resize_needed:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                
                if stretch:
                    table_widget.horizontalHeader().setStretchLastSection(stretch)
        except Exception as e:
            import logging
            logging.error(f'update_table_widget 오류: {type(e).__name__} - {e}', exc_info=True)
        finally:
            table_widget.setUpdatesEnabled(True)
            table_widget.setSortingEnabled(True)
            
    def _set_table_cell(self, table_widget, row, col, column, value):
        """테이블의 특정 셀에 값 설정"""
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        original_value = str(value)
        
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value)
            # "스크립트" 컬럼의 경우 마지막 줄만 표시
            if column == '스크립트' and '\n' in display_value:
                lines = display_value.split('\n')
                # 마지막 줄이 비어있으면 그 전 줄을 사용
                last_line = lines[-1] if lines[-1].strip() else lines[-2] if len(lines) > 1 else lines[0]
                display_value = last_line if last_line.strip() else "(빈 줄)"
                
        # 기존 아이템 재사용
        existing_item = table_widget.item(row, col)
        if existing_item:
            # 값이 같으면 업데이트 필요 없음
            if existing_item.text() == display_value:
                return
            existing_item.setText(display_value)
            existing_item.setData(Qt.UserRole, original_value)
            cell_item = existing_item
        else:
            cell_item = QTableWidgetItem(display_value)
            cell_item.setData(Qt.UserRole, original_value)
            table_widget.setItem(row, col, cell_item)
        
        # 정렬 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(self.align_right)
        else:
            cell_item.setTextAlignment(self.align_left)
        
        # 손익 관련 컬럼 색상 설정
        if column in self.profit_columns:
            if isinstance(value, (int, float)):
                if value < 0:
                    cell_item.setForeground(self.color_negative)  # 음수는 청색
                elif value > 0:
                    cell_item.setForeground(self.color_positive)  # 양수는 적색
                else:
                    cell_item.setForeground(self.color_zero)      # 0은 검정색

"""
# 1. 단일 키 사용 (기존 방식)
config = {
    '키': '종목코드',
    '정수': ['수량', '매수금액'],
    '실수': ['현재가', '평가손익'],
    '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
}
table = TableManager(config)

# 2. 복합 키 사용
config = {
    '키': ['종목코드', '매수일자'],  # 두 컬럼을 합쳐서 키로 사용
    '정수': ['수량', '매수금액'],
    '실수': ['현재가', '평가손익'],
    '컬럼': ['종목코드', '종목명', '매수일자', '수량', '매수금액', '현재가', '평가손익']
}
table = TableManager(config)

# 3. 키 없는 모드
config = {
    '키': None,  # 키 사용 안 함
    '정수': ['수량', '매수금액'],
    '실수': ['현재가', '평가손익'],
    '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
}
table = TableManager(config)

# 4. 중복 키 허용
config = {
    '키': '종목코드',
    '키중복': True,  # 같은 종목코드가 여러 행에 있을 수 있음
    '정수': ['수량', '매수금액'],
    '실수': ['현재가', '평가손익'],
    '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
}
table = TableManager(config)
"""
import logging
import threading
import multiprocessing as mp
import queue
import time
import uuid
import types
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

# 쓰레드 워커 클래스 - 기존과 동일
class TRDThread(QThread):
    taskReceived = pyqtSignal(str, str, object, object)
    
    def __init__(self, name, target):
        super().__init__()
        self.name = name
        self.target = target
        self.running = True
        self.taskReceived.connect(self._processTask)
    
    def run(self):
        logging.debug(f"{self.name} 쓰레드 시작")
        self.exec_()
        logging.debug(f"{self.name} 쓰레드 종료")

    @pyqtSlot(str, str, object, object)
    def _processTask(self, task_id, method_name, task_data, callback):
        method = getattr(self.target, method_name, None)
        if not method:
            logging.error(f"메서드 없음: {method_name}")
            if callback: callback(None)
            return
        
        args, kwargs = task_data
        try:
            result = method(*args, **kwargs)
            if callback: callback(result)
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            if callback: callback(None)

# 프로세스 워커 함수
def process_worker(name, target_class_name, input_queue, output_queue, shared_dict):
    try:
        # 타겟 클래스 동적 임포트
        import importlib
        module_name, class_name = target_class_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        target_class = getattr(module, class_name)
        
        # 타겟 인스턴스 생성
        target = target_class()
        logging.info(f"프로세스 워커 초기화 완료: {name} ({target_class.__name__})")
        
        # answer, work 메서드 바인딩 (프로세스 내에서도 필요함)
        def answer_method(self, target_name, method_name, *args, **kwargs):
            """다른 워커에게 동기 작업 요청 (결과 대기)"""
            req_id = str(uuid.uuid4())
            
            # 메인 프로세스에 프록시 요청 전송
            output_queue.put({
                'command': 'relay_answer',
                'id': req_id,
                'target': target_name,
                'method': method_name,
                'args': args,
                'kwargs': kwargs
            })
            
            # 결과 대기
            start_time = time.time()
            timeout = 5.0
            while req_id not in shared_dict:
                if time.time() - start_time > timeout:
                    logging.warning(f"동기 호출 타임아웃: {target_name}.{method_name}")
                    return None
                time.sleep(0.001)
            
            # 결과 반환
            result = shared_dict[req_id]
            del shared_dict[req_id]
            return result.get('result')
        
        def work_method(self, target_name, method_name, *args, callback=None, **kwargs):
            """다른 워커에게 비동기 작업 요청"""
            req_id = str(uuid.uuid4())
            need_callback = callback is not None
            
            # 메인 프로세스에 프록시 요청 전송
            output_queue.put({
                'command': 'relay_work',
                'id': req_id,
                'target': target_name,
                'method': method_name,
                'args': args,
                'kwargs': kwargs,
                'need_callback': need_callback
            })
            
            # 비동기 요청은 즉시 반환
            return True
        
        # 메서드 바인딩
        import types
        target.answer = types.MethodType(answer_method, target)
        target.work = types.MethodType(work_method, target)
        
        # 메시지 처리 루프
        while True:
            try:
                request = input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
                
            # 종료 명령 처리
            if request.get('cmd') == 'stop':
                break
                
            # 작업 처리
            req_id = request.get('id', '')
            
            # 중계 명령 처리
            if 'relay' in request:
                relay_type = request.get('relay')
                target_name = request.get('target')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                need_callback = request.get('need_callback', False)
                
                logging.debug(f"[{name}] 중계 요청 처리: {relay_type} - {target_name}.{method_name}")
                
                # 다른 프로세스/쓰레드 접근 처리
                if relay_type == 'answer':
                    # 동기 중계 (결과 반환)
                    try:
                        result = target.answer(target_name, method_name, *args, **kwargs)
                        output_queue.put({'id': req_id, 'result': result})
                    except Exception as e:
                        logging.error(f"중계 오류: {e}", exc_info=True)
                        output_queue.put({'id': req_id, 'result': None, 'error': str(e)})
                
                elif relay_type == 'work':
                    # 비동기 중계
                    try:
                        if need_callback:
                            def relay_callback(result):
                                output_queue.put({'id': req_id, 'result': result})
                            callback = relay_callback
                        else:
                            callback = None
                            
                        success = target.work(target_name, method_name, *args, callback=callback, **kwargs)
                        
                        # 콜백이 없는 경우 즉시 결과 반환
                        if not need_callback:
                            output_queue.put({'id': req_id, 'result': success})
                    except Exception as e:
                        logging.error(f"중계 오류: {e}", exc_info=True)
                        output_queue.put({'id': req_id, 'result': None, 'error': str(e)})
                
                continue
                
            # 일반 메서드 호출 처리
            method_name = request.get('method', '')
            args = request.get('args', ())
            kwargs = request.get('kwargs', {})
            
            # 메서드 찾기 및 실행
            method = getattr(target, method_name, None)
            if not method:
                output_queue.put({'id': req_id, 'result': None, 'error': f"메서드 없음: {method_name}"})
                continue
                
            try:
                result = method(*args, **kwargs)
                output_queue.put({'id': req_id, 'result': result})
            except Exception as e:
                logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                output_queue.put({'id': req_id, 'result': None, 'error': str(e)})
    
    except Exception as e:
        logging.error(f"프로세스 워커 초기화 오류: {e}", exc_info=True)
    
    finally:
        logging.info(f"프로세스 워커 종료: {name}")

# 통합 IPC 매니저
class IPCM:
    def __init__(self):
        self.workers = {}  # name -> {type, instance, handle, process}
        self.is_shutting_down = False
        
        # 프로세스 통신용
        self.manager = mp.Manager()
        self.shared_dict = self.manager.dict()
        self.queues = {}  # name -> (input_queue, output_queue)
        self.callbacks = {}  # id -> callback
        self.listeners = {}  # name -> thread
        
        # 현재 프로세스 이름 (메인 프로세스면 'main')
        self.current_process = mp.current_process().name
        if self.current_process == 'MainProcess':
            self.current_process = 'main'
        
        # 글로벌 레퍼런스 설정
        try:
            import sys
            main_module = sys.modules['__main__']
            setattr(main_module, 'ipc', self)
        except Exception as e:
            logging.error(f"글로벌 레퍼런스 설정 오류: {e}")
    
    def register(self, name, target_instance, type=None, start=True, process=None):
        """워커 등록"""
        # 이미 등록된 경우 제거
        if name in self.workers:
            self.unregister(name)
            
        # 소속 프로세스 정보
        process = process or self.current_process
            
        # 타입에 따른 다른 처리
        if type == 'thread':
            # 쓰레드 워커
            thread = TRDThread(name, target_instance)
            self.workers[name] = {
                'type': 'thread',
                'instance': target_instance,
                'handle': thread,
                'process': process
            }
            
            # work, answer 메서드 바인딩
            self._bind_methods(target_instance)
            
            # 시작
            if start:
                thread.start()
                logging.info(f"쓰레드 워커 시작: {name}")
                
        elif type == 'process':
            # 프로세스 워커
            input_queue = mp.Queue()
            output_queue = mp.Queue()
            self.queues[name] = (input_queue, output_queue)
            
            # 타겟 클래스 이름
            target_path = f"{target_instance.__class__.__module__}.{target_instance.__class__.__name__}"
            
            # 프로세스 생성
            process_obj = mp.Process(
                name=name,
                target=process_worker,
                args=(name, target_path, input_queue, output_queue, self.shared_dict),
                daemon=True
            )
            
            self.workers[name] = {
                'type': 'process',
                'instance': target_instance,
                'handle': process_obj,
                'process': name  # 프로세스는 자신이 자신의 소속
            }
            
            # work, answer 메서드 바인딩
            self._bind_methods(target_instance)
            
            # 시작
            if start:
                process_obj.start()
                logging.info(f"프로세스 워커 시작: {name} (PID: {process_obj.pid})")
                self._start_listener(name)
                
        else:
            # 일반 객체 워커
            self.workers[name] = {
                'type': 'main',
                'instance': target_instance,
                'handle': None,
                'process': process
            }
            
            # work, answer 메서드 바인딩
            self._bind_methods(target_instance)
            logging.info(f"메인 워커 등록: {name}")
            
        return target_instance
        
    def _bind_methods(self, target):
        """work, answer 메서드 바인딩"""
        ipcm = self  # self 캡처
        
        def work_method(self, target_name, method_name, *args, callback=None, **kwargs):
            return ipcm.work(target_name, method_name, *args, callback=callback, **kwargs)
            
        def answer_method(self, target_name, method_name, *args, **kwargs):
            return ipcm.answer(target_name, method_name, *args, **kwargs)
            
        target.work = types.MethodType(work_method, target)
        target.answer = types.MethodType(answer_method, target)
    
    def _start_listener(self, name):
        """프로세스 응답 리스너 시작"""
        if name not in self.queues:
            return False
            
        _, output_queue = self.queues[name]
        listener = threading.Thread(
            target=self._listener_thread,
            args=(name, output_queue),
            daemon=True
        )
        listener.start()
        self.listeners[name] = listener
        return True
        
    def _listener_thread(self, name, output_queue):
        """프로세스 응답 처리 쓰레드"""
        logging.info(f"{name} 리스너 쓰레드 시작")
        
        while not self.is_shutting_down:
            try:
                # 응답 가져오기
                try:
                    response = output_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                    
                # 중계 명령 처리
                if 'command' in response:
                    command = response.get('command')
                    req_id = response.get('id')
                    
                    if command == 'relay_answer':
                        # 동기 중계 요청 처리
                        target_name = response.get('target')
                        method_name = response.get('method')
                        args = response.get('args', ())
                        kwargs = response.get('kwargs', {})
                        
                        logging.debug(f"[{name}] relay_answer 요청 처리: {target_name}.{method_name}")
                        
                        # 타겟 호출 
                        try:
                            result = self.answer(target_name, method_name, *args, **kwargs)
                            self.shared_dict[req_id] = {'result': result}
                        except Exception as e:
                            logging.error(f"[{name}] relay_answer 처리 중 오류: {e}", exc_info=True)
                            self.shared_dict[req_id] = {'result': None, 'error': str(e)}
                        continue
                        
                    elif command == 'relay_work':
                        # 비동기 중계 요청 처리
                        target_name = response.get('target')
                        method_name = response.get('method')
                        args = response.get('args', ())
                        kwargs = response.get('kwargs', {})
                        need_callback = response.get('need_callback', False)
                        
                        logging.debug(f"[{name}] relay_work 요청 처리: {target_name}.{method_name}")
                        
                        # 콜백 설정
                        if need_callback:
                            def relay_callback(result):
                                self.shared_dict[req_id] = {'result': result}
                            callback = relay_callback
                        else:
                            callback = None
                        
                        # 타겟 호출
                        try:
                            success = self.work(target_name, method_name, *args, callback=callback, **kwargs)
                            if not need_callback:
                                self.shared_dict[req_id] = {'result': success}
                        except Exception as e:
                            logging.error(f"[{name}] relay_work 처리 중 오류: {e}", exc_info=True)
                            if not need_callback:
                                self.shared_dict[req_id] = {'result': False, 'error': str(e)}
                        continue
                    
                # 응답 처리
                req_id = response.get('id', '')
                result = response.get('result')
                
                # 콜백 실행
                if req_id in self.callbacks:
                    callback = self.callbacks.pop(req_id)
                    callback(result)
                
                # 공유 딕셔너리에 결과 저장
                self.shared_dict[req_id] = response
                
            except Exception as e:
                logging.error(f"응답 처리 중 오류: {e}", exc_info=True)
                
        logging.info(f"{name} 리스너 쓰레드 종료")
    
    def unregister(self, name):
        """워커 등록 해제"""
        if self.is_shutting_down or name not in self.workers:
            return False
            
        worker = self.workers[name]
        type = worker['type']
        handle = worker['handle']
        
        if type == 'thread' and handle:
            # 쓰레드 종료
            handle.running = False
            handle.quit()
            handle.wait(1000)
            
        elif type == 'process' and handle:
            # 프로세스 종료
            if handle.is_alive():
                # 종료 명령 전송
                input_queue, _ = self.queues[name]
                input_queue.put({'cmd': 'stop'})
                
                # 종료 대기
                handle.join(2.0)
                if handle.is_alive():
                    handle.terminate()
                    handle.join(1.0)
            
            # 리소스 정리
            self.queues.pop(name, None)
            if name in self.listeners:
                self.listeners.pop(name, None)
                
        # 워커 제거
        self.workers.pop(name, None)
        logging.info(f"워커 등록 해제: {name}")
        return True
        
    def work(self, worker_name, method_name, *args, callback=None, **kwargs):
        """비동기 메서드 호출"""
        if self.is_shutting_down:
            return False
            
        # 워커 확인
        if worker_name not in self.workers:
            logging.error(f"워커 없음: {worker_name}")
            if callback: callback(None)
            return False
            
        worker = self.workers[worker_name]
        type = worker['type']
        worker_process = worker['process']
        
        # 다른 프로세스 접근 처리 (프로세스 간 통신)
        if worker_process != self.current_process:
            # 다른 프로세스에 있는 경우 중계
            if worker_process == 'main':
                # 메인 프로세스에 있는 경우 (쓰레드/메인 워커)
                return self._relay_to_main(worker_name, method_name, args, kwargs, callback)
            else:
                # 다른 프로세스에 있는 경우
                return self._relay_to_process(worker_process, worker_name, method_name, args, kwargs, callback)
        
        # 동일 프로세스 내 호출
        if type == 'main':
            # 메인 워커 호출
            return self._call_main(worker_name, method_name, args, kwargs, callback)
            
        elif type == 'thread':
            # 쓰레드 워커 호출
            return self._call_thread(worker_name, method_name, args, kwargs, callback)
            
        elif type == 'process':
            # 프로세스 워커 호출
            return self._call_process(worker_name, method_name, args, kwargs, callback)
    
    def answer(self, worker_name, method_name, *args, **kwargs):
        """동기 메서드 호출"""
        if self.is_shutting_down:
            return None
            
        # 워커 확인
        if worker_name not in self.workers:
            logging.error(f"워커 없음: {worker_name}")
            return None
            
        worker = self.workers[worker_name]
        type = worker['type']
        worker_process = worker['process']
        
        # 다른 프로세스 접근 처리 (프로세스 간 통신)
        if worker_process != self.current_process:
            # 다른 프로세스에 있는 경우 중계
            if worker_process == 'main':
                # 메인 프로세스에 있는 경우 (쓰레드/메인 워커)
                return self._relay_to_main_sync(worker_name, method_name, args, kwargs)
            else:
                # 다른 프로세스에 있는 경우
                return self._relay_to_process_sync(worker_process, worker_name, method_name, args, kwargs)
        
        # 동일 프로세스 내 호출
        if type == 'main':
            # 메인 워커 호출
            return self._call_main_sync(worker_name, method_name, args, kwargs)
            
        elif type == 'thread':
            # 쓰레드 워커 호출
            return self._call_thread_sync(worker_name, method_name, args, kwargs)
            
        elif type == 'process':
            # 프로세스 워커 호출
            return self._call_process_sync(worker_name, method_name, args, kwargs)
    
    def _relay_to_main(self, target_name, method_name, args, kwargs, callback):
        """메인 프로세스에 비동기 중계 요청"""
        # 현재 메인 프로세스에서 호출한 경우는 처리하지 않음
        if self.current_process == 'main':
            logging.error("메인 프로세스에서 자신에게 중계할 수 없음")
            if callback: callback(None)
            return False
            
        # 메인 프로세스에 대한 큐가 없는 경우 (직접 통신 불가)
        if 'main' not in self.queues:
            logging.error("메인 프로세스에 대한 큐 없음")
            if callback: callback(None)
            return False
            
        # 메인 프로세스에 중계 요청
        input_queue, _ = self.queues['main']
        req_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback:
            self.callbacks[req_id] = callback
            
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'relay': 'work',
            'target': target_name,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'need_callback': callback is not None
        })
        
        return True
    
    def _relay_to_main_sync(self, target_name, method_name, args, kwargs):
        """메인 프로세스에 동기 중계 요청"""
        # 현재 메인 프로세스에서 호출한 경우는 처리하지 않음
        if self.current_process == 'main':
            logging.error("메인 프로세스에서 자신에게 중계할 수 없음")
            return None
            
        # 메인 프로세스에 대한 큐가 없는 경우 (직접 통신 불가)
        if 'main' not in self.queues:
            logging.error("메인 프로세스에 대한 큐 없음")
            return None
            
        # 메인 프로세스에 중계 요청
        input_queue, _ = self.queues['main']
        req_id = str(uuid.uuid4())
        
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'relay': 'answer',
            'target': target_name,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        # 결과 대기
        start_time = time.time()
        timeout = 5.0
        
        while req_id not in self.shared_dict:
            if time.time() - start_time > timeout:
                logging.warning(f"메인 프로세스 중계 타임아웃: {target_name}.{method_name}")
                return None
            time.sleep(0.001)
            
        # 결과 반환
        response = self.shared_dict.pop(req_id)
        return response.get('result')
    
    def _relay_to_process(self, process_name, target_name, method_name, args, kwargs, callback):
        """다른 프로세스에 비동기 중계 요청"""
        # 프로세스에 대한 큐가 없는 경우
        if process_name not in self.queues:
            logging.error(f"프로세스 큐 없음: {process_name}")
            if callback: callback(None)
            return False
            
        # 프로세스에 중계 요청
        input_queue, _ = self.queues[process_name]
        req_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback:
            self.callbacks[req_id] = callback
            
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'relay': 'work',
            'target': target_name,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'need_callback': callback is not None
        })
        
        return True
    
    def _relay_to_process_sync(self, process_name, target_name, method_name, args, kwargs):
        """다른 프로세스에 동기 중계 요청"""
        # 프로세스에 대한 큐가 없는 경우
        if process_name not in self.queues:
            logging.error(f"프로세스 큐 없음: {process_name}")
            return None
            
        # 프로세스에 중계 요청
        input_queue, _ = self.queues[process_name]
        req_id = str(uuid.uuid4())
        
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'relay': 'answer',
            'target': target_name,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        # 결과 대기
        start_time = time.time()
        timeout = 5.0
        
        while req_id not in self.shared_dict:
            if time.time() - start_time > timeout:
                logging.warning(f"프로세스 중계 타임아웃: {process_name}.{target_name}.{method_name}")
                return None
            time.sleep(0.001)
            
        # 결과 반환
        response = self.shared_dict.pop(req_id)
        return response.get('result')
    
    def _call_main(self, name, method_name, args, kwargs, callback):
        """메인 워커 비동기 호출"""
        target = self.workers[name]['instance']
        method = getattr(target, method_name, None)
        
        if not method:
            logging.error(f"메서드 없음: {name}.{method_name}")
            if callback: callback(None)
            return False
            
        try:
            result = method(*args, **kwargs)
            if callback: callback(result)
            return True
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            if callback: callback(None)
            return False
    
    def _call_main_sync(self, name, method_name, args, kwargs):
        """메인 워커 동기 호출"""
        target = self.workers[name]['instance']
        method = getattr(target, method_name, None)
        
        if not method:
            logging.error(f"메서드 없음: {name}.{method_name}")
            return None
            
        try:
            return method(*args, **kwargs)
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            return None
    
    def _call_thread(self, name, method_name, args, kwargs, callback):
        """쓰레드 워커 비동기 호출"""
        thread = self.workers[name]['handle']
        req_id = str(uuid.uuid4())
        thread.taskReceived.emit(req_id, method_name, (args, kwargs), callback)
        return True
    
    def _call_thread_sync(self, name, method_name, args, kwargs):
        """쓰레드 워커 동기 호출"""
        thread = self.workers[name]['handle']
        
        # 결과 기다림
        result = [None]
        event = threading.Event()
        
        def callback(res):
            result[0] = res
            event.set()
            
        # 요청 전송
        req_id = str(uuid.uuid4())
        thread.taskReceived.emit(req_id, method_name, (args, kwargs), callback)
        
        # 결과 대기
        if not event.wait(5.0):
            logging.warning(f"쓰레드 호출 타임아웃: {name}.{method_name}")
            return None
            
        return result[0]
    
    def _call_process(self, name, method_name, args, kwargs, callback):
        """프로세스 워커 비동기 호출"""
        if name not in self.queues:
            logging.error(f"프로세스 큐 없음: {name}")
            if callback: callback(None)
            return False
            
        input_queue, _ = self.queues[name]
        req_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback:
            self.callbacks[req_id] = callback
            
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        return True
    
    def _call_process_sync(self, name, method_name, args, kwargs):
        """프로세스 워커 동기 호출"""
        if name not in self.queues:
            logging.error(f"프로세스 큐 없음: {name}")
            return None
            
        input_queue, _ = self.queues[name]
        req_id = str(uuid.uuid4())
        
        # 요청 전송
        input_queue.put({
            'id': req_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        # 결과 대기
        start_time = time.time()
        timeout = 5.0
        
        while req_id not in self.shared_dict:
            if time.time() - start_time > timeout:
                logging.warning(f"프로세스 호출 타임아웃: {name}.{method_name}")
                return None
            time.sleep(0.001)
            
        # 결과 반환
        response = self.shared_dict.pop(req_id)
        return response.get('result')
    
    def start(self, name):
        """워커 시작"""
        if name not in self.workers:
            return False
            
        worker = self.workers[name]
        handle = worker['handle']
        
        if worker['type'] == 'thread':
            if not handle.isRunning():
                handle.start()
                return True
        elif worker['type'] == 'process':
            if not handle.is_alive():
                handle.start()
                self._start_listener(name)
                return True
                
        return False
    
    def stop(self, name):
        """워커 중지"""
        return self.unregister(name)
    
    def cleanup(self):
        """모든 워커 정리"""
        self.is_shutting_down = True
        
        # 모든 워커 등록 해제
        for name in list(self.workers.keys()):
            self.unregister(name)
            
        # 자원 정리
        if hasattr(self, 'manager') and self.manager:
            try:
                self.manager.shutdown()
            except Exception:
                pass
            self.manager = None
            
        logging.info("모든 자원 정리 완료")

# 메인 테스트 코드
if __name__ == "__main__":
    try:
        # 로깅 초기화
        import logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s-%(levelname)s-[%(filename)s(%(lineno)d) / %(funcName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # PyQt5 애플리케이션 생성
        from PyQt5.QtWidgets import QApplication
        app = QApplication([])
        
        # 워커 클래스 정의
        from worker import ADM, STG, API, DBM
        
        # IPCM 초기화
        ipc = IPCM()
        
        logging.info("=== 매니저 초기화 완료 ===")
        
        # 워커 등록
        admin = ipc.register('admin', ADM())
        stg01 = ipc.register('stg01', STG("stg01"), type='thread', start=True)
        stg02 = ipc.register('stg02', STG("stg02"), type='thread', start=True)
        api = ipc.register('api', API(), type='process', start=True)
        dbm = ipc.register('dbm', DBM(), type='process', start=True)
        
        logging.info("=== 모든 워커 등록 완료 ===")
        
        # 테스트 시작 전 잠시 대기
        time.sleep(1)
        logging.info("\n\n=== 테스트 시작 ===\n")
        
        # 테스트 수행
        # Admin -> Strategy01 테스트
        logging.info("\n--- Admin -> Strategy01 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('admin', 'call_strategy', 'stg01', '관리자에서 전략01 호출 테스트')
        logging.info(f"결과: {result}")
        
        # Strategy01 -> Admin 테스트
        logging.info("\n--- Strategy01 -> Admin 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('stg01', 'call_admin', '전략01에서 관리자 호출 테스트')
        logging.info(f"결과: {result}")
        
        # Strategy01 -> Strategy02 테스트
        logging.info("\n--- Strategy01 -> Strategy02 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('stg01', 'call_other_strategy', 'stg02', '전략01에서 전략02 호출 테스트')
        logging.info(f"결과: {result}")
        
        # DBM -> Strategy01 테스트 (프로세스 -> 쓰레드)
        logging.info("\n--- DBM -> Strategy01 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('dbm', 'call_strategy', 'stg01', 'DBM에서 전략01 호출 테스트')
        logging.info(f"결과: {result}")
        
        # Strategy01 -> API 테스트 (쓰레드 -> 프로세스)
        logging.info("\n--- Strategy01 -> API 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('stg01', 'call_api', '전략01에서 API 호출 테스트')
        logging.info(f"결과: {result}")
        
        # API -> DBM 테스트 (프로세스 -> 프로세스)
        logging.info("\n--- API -> DBM 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('api', 'call_dbm', 'API에서 DBM 호출 테스트')
        logging.info(f"결과: {result}")
        
        # 비동기 호출 테스트
        logging.info("\n--- Admin -> Strategy02 비동기 호출 테스트 ---")
        input("Press Enter to continue...")
        result = ipc.answer('admin', 'call_strategy_async', 'stg02', '관리자에서 전략02 비동기 호출 테스트')
        logging.info(f"비동기 호출 시작: {result}")
        
        # 콜백 완료를 위한 대기
        logging.info("\n비동기 콜백 대기 중...")
        time.sleep(2)
        
        # 종료
        logging.info("\n=== 테스트 종료, 모든 워커 정리 중 ===")
        input("Press Enter to continue...")
        ipc.cleanup()
        logging.info("모든 워커 정리 완료")
    
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {e}", exc_info=True)
        try:
            ipc.cleanup()
        except:
            pass







