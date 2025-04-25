from public import *
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from datetime import datetime
import threading
import copy
import time
import logging
import uuid
import pandas as pd
import numpy as np

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
        self.lock = threading.Lock()

    def items(self):
        with self.lock:
            return list(self.dict.items())  # 복사본 반환

    def keys(self):
        with self.lock:
            return list(self.dict.keys())  # 복사본 반환

    def values(self):
        with self.lock:
            return list(self.dict.values())  # 복사본 반환

    def set(self, key, value=None, next=None):
        with self.lock:
            if next is None:
                self.dict[key] = copy.deepcopy(value) if value is not None else {}
            else:
                if key not in self.dict:
                    self.dict[key] = {}
                self.dict[key][next] = copy.deepcopy(value) if value is not None else {}

    def get(self, key, next=None):
        with self.lock:
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

    def contains(self, item):
        with self.lock:
            return item in self.dict

    def remove(self, key, next=None):
        with self.lock:
            try:
                if next is None:
                    return copy.deepcopy(self.dict.pop(key, None))
                elif key in self.dict:
                    return copy.deepcopy(self.dict[key].pop(next, None))
                return None
            except Exception as e:
                logging.error(f"ThreadSafeDict remove 오류: {e}")
                return None

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

#QReadWriteLock 사용
class TableManager:
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
                
# 워커 쓰레드 클래스
class WorkerThread(QThread):
    taskReceived = pyqtSignal(str, str, object, object)
    
    def __init__(self, name, target):
        super().__init__()
        self.name = name
        self.target = target
        self.running = True
        
        # 이 쓰레드에서 처리할 시그널 연결
        self.taskReceived.connect(self._processTask)
    
    def run(self):
        logging.debug(f"{self.name} 쓰레드 시작")
        self.exec_()  # 이벤트 루프 시작
        logging.debug(f"{self.name} 쓰레드 종료")

    def _get_var(self, var_name):
        """타겟 객체의 변수 값을 가져오는 내부 메서드"""
        try:
            return getattr(self.target, var_name, None)
        except Exception as e:
            logging.error(f"변수 접근 오류: {e}", exc_info=True)
            return None

    def _set_var(self, var_name, value):
        """타겟 객체의 변수 값을 설정하는 내부 메서드"""
        try:
            setattr(self.target, var_name, value)
            return True
        except Exception as e:
            logging.error(f"변수 설정 오류: {e}", exc_info=True)
            return None
            
    @pyqtSlot(str, str, object, object)
    def _processTask(self, task_id, method_name, task_data, callback):
        # 메서드 찾기
        method = getattr(self.target, method_name, None)
        if not method:
            if callback:
                callback(None)
            return
        
        # 메서드 실행
        args, kwargs = task_data
        try:
            result = method(*args, **kwargs)
            if callback:
                callback(result)
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            if callback:
                callback(None)

# 워커 관리자
class WorkerManager:
    def __init__(self):
        self.workers = {}  # name -> worker thread
        self.targets = {}  # name -> target object

        self.manager = None
        self.task_queues = {} # name -> manager.list
        self.result_dicts = {} # name -> manager.dict

        self.is_shutting_down = False

    def register(self, name, target_class=None, use_thread=True):
        if use_thread:
            target = target_class() if isinstance(target_class, type) else target_class
            worker = WorkerThread(name, target)
            worker.start()
            self.workers[name] = worker
        else:
            target = target_class() if isinstance(target_class, type) else target_class
            self.targets[name] = target
        return self

    def stop_worker(self, worker_name):
        """워커 중지"""
        # 쓰레드 워커 중지
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            worker.running = False
            worker.quit()  # 이벤트 루프 종료
            worker.wait(1000)  # 최대 1초간 대기
            self.workers.pop(worker_name, None)
            logging.debug(f"워커 종료: {worker_name} (쓰레드)")
            return True
            
        # 메인 쓰레드 워커 제거
        elif worker_name in self.targets:
            self.targets.pop(worker_name, None)
            logging.debug(f"워커 제거: {worker_name} (메인 쓰레드)")
            return True
            
        return False

    def stop_all(self):
        """모든 워커 중지"""
        # 모든 쓰레드 워커 중지
        self.is_shutting_down = True

        logging.info("모든 워커 중지 중...")
        for name in list(self.workers.keys()):
            self.stop_worker(name)
            
        # 모든 메인 쓰레드 워커 제거
        self.targets.clear()
        
        # Manager 종료
        if self.manager is not None:
            try:
                self.manager.shutdown()
            except:
                pass
            self.manager = None

        logging.debug("모든 워커 종료")
        
    def get_var(self, worker_name, var_name):
        """워커의 변수 값을 가져오는 함수"""
        if self.is_shutting_down:
            return None
            
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return None
            
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            try:
                return getattr(target, var_name, None)
            except Exception as e:
                logging.error(f"변수 접근 오류: {e}", exc_info=True)
                return None
                
        # 쓰레드로 실행하는 경우
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            return self.answer(worker_name, '_get_var', var_name)
            
        return None
        
    def set_var(self, worker_name, var_name, value):
        """워커의 변수 값을 설정하는 함수"""
        if self.is_shutting_down:
            return False
            
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return False
            
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            try:
                setattr(target, var_name, value)
                return True
            except Exception as e:
                logging.error(f"변수 설정 오류: {e}", exc_info=True)
                return False
                
        # 쓰레드로 실행하는 경우
        if worker_name in self.workers:
            return self.answer(worker_name, '_set_var', var_name, value) is not None
            
        return False
        
    def answer(self, worker_name, method_name, *args, **kwargs):
        """동기식 함수 호출"""
        if self.is_shutting_down:
            return None
        
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return None
        
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            method = getattr(target, method_name, None)
            if not method:
                return None
            try:
                return method(*args, **kwargs)
            except Exception as e:
                logging.error(f"직접 호출 오류: {e}", exc_info=True)
                return None
        
        # 쓰레드로 실행하는 경우
        worker = self.workers[worker_name]
        result = [None]
        event = threading.Event()
        
        def callback(res):
            result[0] = res
            event.set()
        
        # 시그널로 태스크 전송
        task_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        worker.taskReceived.emit(task_id, method_name, task_data, callback)
        
        # 결과 대기
        if not event.wait(3.0):
            logging.warning(f"호출 타임아웃: {worker_name}.{method_name}")
            return None
        
        return result[0]

    def work(self, worker_name, method_name, *args, callback=None, **kwargs):
        """비동기 함수 호출"""
        if self.is_shutting_down:
            return None
        
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return False
        
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            method = getattr(target, method_name, None)
            if not method:
                return False
            try:
                result = method(*args, **kwargs)
                if callback:
                    callback(result)
                return True
            except Exception as e:
                logging.error(f"직접 호출 오류: {e}", exc_info=True)
                if callback:
                    callback(None)
                return False
        
        # 쓰레드로 실행하는 경우
        worker = self.workers[worker_name]
        task_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        worker.taskReceived.emit(task_id, method_name, task_data, callback)
        return True
la = WorkerManager()

import multiprocessing as mp
import uuid
import time
import pickle
import logging
import inspect
import threading
import importlib
from functools import wraps

class ProcessProxy:
    """
    원격 프로세스 호출을 위한 프록시 클래스
    일반 클래스의 메서드 호출을 프로세스 간 통신으로 변환
    """
    def __init__(self, process_id, pm):
        self.process_id = process_id
        self.pm = pm
        self._methods_cache = {}

    def __getattr__(self, name):
        """동적으로 메서드 호출을 가로채서 RPC로 변환"""
        if name in self._methods_cache:
            return self._methods_cache[name]
        
        # 동기 메서드 생성
        def sync_method(*args, **kwargs):
            return self.pm.call_sync(self.process_id, name, args, kwargs)
        
        # 비동기 메서드 생성
        def async_method(*args, **kwargs):
            callback = kwargs.pop('callback', None)
            return self.pm.call_async(self.process_id, name, args, kwargs, callback)
        
        # 메서드 캐싱
        self._methods_cache[name] = sync_method
        self._methods_cache[f"{name}_async"] = async_method
        
        return sync_method
    
    def get_var(self, var_name):
        """변수 값 가져오기"""
        return self.pm.call_sync(self.process_id, '_get_var', [var_name], {})
    
    def set_var(self, var_name, value):
        """변수 값 설정하기"""
        return self.pm.call_sync(self.process_id, '_set_var', [var_name, value], {})

def worker_process(
    process_id, 
    target_info, 
    request_queue, 
    response_dict, 
    process_registry, 
    callbacks_dict
):
    """
    워커 프로세스 메인 함수
    프로세스가 독립적으로 실행되며 request_queue를 통해 요청 처리
    """
    try:
        # 대상 클래스 인스턴스화
        if isinstance(target_info, tuple):
            # 모듈과 클래스 이름으로 부터 클래스 로드
            module_name, class_name = target_info
            module = importlib.import_module(module_name)
            target_class = getattr(module, class_name)
            target = target_class()
        else:
            # 직접 객체 전달 (피클링 가능한 객체여야 함)
            target = target_info
        
        logging.info(f"프로세스 {process_id} 시작됨 ({type(target).__name__})")
        
        # 헬퍼 메서드 추가
        def _get_var(var_name):
            """변수 값 가져오기"""
            try:
                return getattr(target, var_name, None)
            except Exception as e:
                logging.error(f"변수 접근 오류: {e}", exc_info=True)
                return None
        
        def _set_var(var_name, value):
            """변수 값 설정하기"""
            try:
                setattr(target, var_name, value)
                return True
            except Exception as e:
                logging.error(f"변수 설정 오류: {e}", exc_info=True)
                return False
        
        # 특수 메서드 등록
        target._get_var = _get_var
        target._set_var = _set_var
        
        # 프로세스 매니저 참조 생성
        target._pm = ProcessManagerClient(
            process_id, 
            process_registry, 
            request_queue, 
            response_dict, 
            callbacks_dict
        )
        
        # 메시지 처리 루프
        while True:
            # 요청 대기
            if len(request_queue) == 0:
                time.sleep(0.001)
                continue
            
            # 요청 처리
            request = request_queue.pop(0)
            
            # 종료 명령 확인
            if request.get('command') == 'stop':
                logging.info(f"프로세스 {process_id} 종료 요청 받음")
                break
            
            # 요청 데이터 파싱
            task_id = request.get('task_id')
            method_name = request.get('method')
            args = request.get('args', ())
            kwargs = request.get('kwargs', {})
            caller_id = request.get('caller_id')
            
            # 응답 처리용 함수
            def send_response(status, result=None, error=None):
                response_dict[task_id] = {
                    'status': status,
                    'result': result,
                    'error': error,
                    'caller_id': caller_id
                }
            
            # 메서드 찾기 및 실행
            method = getattr(target, method_name, None)
            if not method:
                send_response('error', error=f"메서드 없음: {method_name}")
                continue
            
            # 메서드 실행
            try:
                result = method(*args, **kwargs)
                send_response('success', result=result)
            except Exception as e:
                logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                send_response('error', error=str(e))
    
    except Exception as e:
        logging.error(f"프로세스 {process_id} 실행 오류: {e}", exc_info=True)
    
    finally:
        logging.info(f"프로세스 {process_id} 종료됨")

class ProcessManagerClient:
    """
    프로세스 내에서 다른 프로세스의 메서드를 호출하기 위한 클라이언트
    각 워커 프로세스 내부에서 사용됨
    """
    def __init__(self, process_id, process_registry, request_queue, response_dict, callbacks_dict):
        self.process_id = process_id
        self.process_registry = process_registry
        self.request_queue = request_queue
        self.response_dict = response_dict
        self.callbacks_dict = callbacks_dict
        self.proxies = {}  # 프로세스 ID -> 프록시 객체
    
    def get_proxy(self, process_id):
        """다른 프로세스에 대한 프록시 가져오기"""
        if process_id not in self.proxies:
            # 프로세스가 존재하는지 확인
            if process_id not in self.process_registry:
                logging.error(f"프로세스 없음: {process_id}")
                return None
            
            class RemoteProcessProxy:
                def __init__(self, pid, client):
                    self.pid = pid
                    self.client = client
                    self._methods_cache = {}
                
                def __getattr__(self, name):
                    if name in self._methods_cache:
                        return self._methods_cache[name]
                    
                    # 동기 메서드
                    def sync_method(*args, **kwargs):
                        return self.client.call_sync(self.pid, name, args, kwargs)
                    
                    # 비동기 메서드
                    def async_method(*args, **kwargs):
                        callback = kwargs.pop('callback', None)
                        return self.client.call_async(self.pid, name, args, kwargs, callback)
                    
                    # 메서드 캐싱
                    self._methods_cache[name] = sync_method
                    self._methods_cache[f"{name}_async"] = async_method
                    
                    return sync_method
                
                def get_var(self, var_name):
                    return self.client.call_sync(self.pid, '_get_var', [var_name], {})
                
                def set_var(self, var_name, value):
                    return self.client.call_sync(self.pid, '_set_var', [var_name, value], {})
            
            self.proxies[process_id] = RemoteProcessProxy(process_id, self)
        
        return self.proxies[process_id]
    
    def call_sync(self, target_id, method_name, args, kwargs):
        """동기식 원격 호출"""
        # 대상 프로세스 확인
        if target_id not in self.process_registry:
            logging.error(f"프로세스 없음: {target_id}")
            return None
        
        # 작업 ID 생성
        task_id = str(uuid.uuid4())
        
        # 요청 데이터 생성
        request = {
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'caller_id': self.process_id
        }
        
        # 요청 전송 (대상 프로세스의 요청 큐에 추가)
        target_request_queue = self.process_registry[target_id]['request_queue']
        target_request_queue.append(request)
        
        # 응답 대기
        target_response_dict = self.process_registry[target_id]['response_dict']
        start_time = time.time()
        while task_id not in target_response_dict:
            if time.time() - start_time > 10.0:  # 10초 타임아웃
                logging.warning(f"호출 타임아웃: {target_id}.{method_name}")
                return None
            time.sleep(0.001)
        
        # 응답 처리
        response = target_response_dict[task_id]
        del target_response_dict[task_id]  # 응답 제거
        
        if response['status'] == 'success':
            return response['result']
        else:
            logging.error(f"원격 호출 오류: {response.get('error')}")
            return None
    
    def call_async(self, target_id, method_name, args, kwargs, callback=None):
        """비동기식 원격 호출"""
        # 대상 프로세스 확인
        if target_id not in self.process_registry:
            logging.error(f"프로세스 없음: {target_id}")
            return False
        
        # 작업 ID 생성
        task_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback:
            self.callbacks_dict[task_id] = callback
        
        # 요청 데이터 생성
        request = {
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'caller_id': self.process_id
        }
        
        # 요청 전송
        target_request_queue = self.process_registry[target_id]['request_queue']
        target_request_queue.append(request)
        
        # 비동기 응답 처리를 위한 스레드 시작
        if callback:
            def wait_for_response():
                target_response_dict = self.process_registry[target_id]['response_dict']
                start_time = time.time()
                while task_id not in target_response_dict:
                    if time.time() - start_time > 10.0:  # 10초 타임아웃
                        logging.warning(f"비동기 호출 타임아웃: {target_id}.{method_name}")
                        cb = self.callbacks_dict.pop(task_id, None)
                        if cb:
                            cb(None)
                        return
                    time.sleep(0.001)
                
                # 응답 처리
                response = target_response_dict[task_id]
                del target_response_dict[task_id]  # 응답 제거
                
                # 콜백 실행
                cb = self.callbacks_dict.pop(task_id, None)
                if cb:
                    if response['status'] == 'success':
                        cb(response['result'])
                    else:
                        logging.error(f"비동기 호출 오류: {response.get('error')}")
                        cb(None)
            
            # 응답 대기 스레드 시작
            threading.Thread(target=wait_for_response, daemon=True).start()
        
        return True

class ProcessManager:
    """
    멀티프로세스 관리자
    프로세스 생성, 종료 및 프로세스 간 통신 관리
    """
    def __init__(self):
        self.manager = mp.Manager()
        self.processes = {}  # 프로세스 ID -> 프로세스 정보
        self.process_registry = self.manager.dict()  # 프로세스 ID -> 프로세스 정보 (공유 객체)
        self.main_process_id = "main"  # 메인 프로세스 ID
        self.callbacks = {}  # 태스크 ID -> 콜백 함수
        
        # 메인 프로세스 요청 큐 및 응답 딕셔너리 생성
        self.request_queue = self.manager.list()
        self.response_dict = self.manager.dict()
        self.callbacks_dict = self.manager.dict()  # 콜백 공유 딕셔너리
        
        # 메인 프로세스 정보 등록
        self.process_registry[self.main_process_id] = {
            'request_queue': self.request_queue,
            'response_dict': self.response_dict,
            'status': 'running'
        }
        
        # 요청 처리 스레드 시작
        self.running = True
        self.request_thread = threading.Thread(target=self._process_requests, daemon=True)
        self.request_thread.start()
        
        logging.info("프로세스 매니저 초기화 완료")
    
    def _process_requests(self):
        """메인 프로세스 요청 처리 스레드"""
        while self.running:
            # 요청이 있는지 확인
            if len(self.request_queue) == 0:
                time.sleep(0.001)
                continue
            
            # 요청 처리
            request = self.request_queue.pop(0)
            
            # 요청 정보 파싱
            task_id = request.get('task_id')
            method_name = request.get('method')
            args = request.get('args', ())
            kwargs = request.get('kwargs', {})
            caller_id = request.get('caller_id')
            
            # 메서드 매핑 및 실행
            if method_name == '_get_process_list':
                # 프로세스 목록 반환
                result = list(self.processes.keys())
                self.response_dict[task_id] = {
                    'status': 'success',
                    'result': result,
                    'caller_id': caller_id
                }
            elif method_name == '_get_process_info':
                # 프로세스 정보 반환
                process_id = args[0] if args else None
                if process_id in self.processes:
                    info = {
                        'status': self.processes[process_id].get('status', 'unknown'),
                        'pid': self.processes[process_id].get('process_obj').pid if self.processes[process_id].get('process_obj') else None
                    }
                    self.response_dict[task_id] = {
                        'status': 'success',
                        'result': info,
                        'caller_id': caller_id
                    }
                else:
                    self.response_dict[task_id] = {
                        'status': 'error',
                        'error': f"프로세스 없음: {process_id}",
                        'caller_id': caller_id
                    }
            elif method_name == '_call_process':
                # 다른 프로세스 호출 (브릿지)
                target_id = args[0] if len(args) > 0 else None
                target_method = args[1] if len(args) > 1 else None
                target_args = args[2] if len(args) > 2 else ()
                target_kwargs = args[3] if len(args) > 3 else {}
                
                if not target_id or not target_method:
                    self.response_dict[task_id] = {
                        'status': 'error',
                        'error': "대상 프로세스나 메서드가 지정되지 않았습니다",
                        'caller_id': caller_id
                    }
                elif target_id not in self.process_registry:
                    self.response_dict[task_id] = {
                        'status': 'error',
                        'error': f"프로세스 없음: {target_id}",
                        'caller_id': caller_id
                    }
                else:
                    # 콜백 함수 생성
                    def bridge_callback(result):
                        self.response_dict[task_id] = {
                            'status': 'success',
                            'result': result,
                            'caller_id': caller_id
                        }
                    
                    # 대상 프로세스에 요청 전달
                    self.call_async(target_id, target_method, target_args, target_kwargs, bridge_callback)
            else:
                # 알 수 없는 메서드
                self.response_dict[task_id] = {
                    'status': 'error',
                    'error': f"알 수 없는 메서드: {method_name}",
                    'caller_id': caller_id
                }
            
            # 응답 콜백 처리
            self._check_callbacks()
    
    def _check_callbacks(self):
        """응답 콜백 처리"""
        for task_id in list(self.callbacks.keys()):
            # 응답이 있는지 확인
            if task_id in self.response_dict:
                response = self.response_dict[task_id]
                del self.response_dict[task_id]
                
                # 콜백 실행
                callback = self.callbacks.pop(task_id)
                if callback:
                    if response['status'] == 'success':
                        callback(response['result'])
                    else:
                        callback(None)
    
    def register_process(self, process_id, target_class_or_object):
        """새 프로세스 등록 및 시작"""
        if process_id in self.processes:
            logging.warning(f"프로세스 {process_id}가 이미 존재합니다")
            return None
        
        # 공유 객체 생성
        request_queue = self.manager.list()
        response_dict = self.manager.dict()
        
        # 프로세스 정보 등록
        self.process_registry[process_id] = {
            'request_queue': request_queue,
            'response_dict': response_dict,
            'status': 'starting'
        }
        
        # 대상 클래스 정보 준비
        if inspect.isclass(target_class_or_object):
            target_info = (target_class_or_object.__module__, target_class_or_object.__name__)
        else:
            target_info = target_class_or_object
        
        # 프로세스 시작
        process = mp.Process(
            target=worker_process,
            args=(process_id, target_info, request_queue, response_dict, 
                self.process_registry, self.callbacks_dict),
            daemon=True
        )
        process.start()
        
        # 프로세스 정보 저장
        self.processes[process_id] = {
            'process_obj': process,
            'request_queue': request_queue,
            'response_dict': response_dict,
            'status': 'running'
        }
        
        logging.info(f"프로세스 {process_id} 등록 완료 (PID: {process.pid})")
        
        # 프록시 객체 생성 및 반환
        return ProcessProxy(process_id, self)
    
    def get_proxy(self, process_id):
        """기존 프로세스에 대한 프록시 가져오기"""
        if process_id not in self.processes and process_id != self.main_process_id:
            logging.error(f"프로세스 없음: {process_id}")
            return None
        
        return ProcessProxy(process_id, self)
    
    def stop_process(self, process_id):
        """프로세스 중지"""
        if process_id not in self.processes:
            logging.warning(f"프로세스 없음: {process_id}")
            return False
        
        # 프로세스에 종료 명령 전송
        self.processes[process_id]['request_queue'].append({'command': 'stop'})
        
        # 프로세스 종료 대기
        process = self.processes[process_id]['process_obj']
        process.join(2.0)
        if process.is_alive():
            process.terminate()
            process.join(1.0)
        
        # 프로세스 정보 제거
        del self.process_registry[process_id]
        del self.processes[process_id]
        
        logging.info(f"프로세스 {process_id} 종료 완료")
        return True
    
    def stop_all(self):
        """모든 프로세스 중지"""
        self.running = False
        
        # 모든 프로세스 중지
        for process_id in list(self.processes.keys()):
            self.stop_process(process_id)
        
        # 요청 처리 스레드 종료 대기
        if self.request_thread.is_alive():
            self.request_thread.join(2.0)
        
        # 메인 프로세스 정보 제거
        if self.main_process_id in self.process_registry:
            del self.process_registry[self.main_process_id]
        
        # Manager 종료
        try:
            self.manager.shutdown()
        except:
            pass
        
        logging.info("모든 프로세스 종료 완료")
    
    def call_sync(self, process_id, method_name, args, kwargs):
        """동기식 원격 호출"""
        # 대상 프로세스 확인
        if process_id not in self.process_registry:
            logging.error(f"프로세스 없음: {process_id}")
            return None
        
        # 작업 ID 생성
        task_id = str(uuid.uuid4())
        
        # 요청 데이터 생성
        request = {
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'caller_id': self.main_process_id
        }
        
        # 요청 전송
        self.process_registry[process_id]['request_queue'].append(request)
        
        # 응답 대기
        target_response_dict = self.process_registry[process_id]['response_dict']
        start_time = time.time()
        while task_id not in target_response_dict:
            if time.time() - start_time > 10.0:  # 10초 타임아웃
                logging.warning(f"호출 타임아웃: {process_id}.{method_name}")
                return None
            time.sleep(0.001)
        
        # 응답 처리
        response = target_response_dict[task_id]
        del target_response_dict[task_id]  # 응답 제거
        
        if response['status'] == 'success':
            return response['result']
        else:
            logging.error(f"원격 호출 오류: {response.get('error')}")
            return None
    
    def call_async(self, process_id, method_name, args, kwargs, callback=None):
        """비동기식 원격 호출"""
        # 대상 프로세스 확인
        if process_id not in self.process_registry:
            logging.error(f"프로세스 없음: {process_id}")
            return False
        
        # 작업 ID 생성
        task_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback:
            self.callbacks[task_id] = callback
        
        # 요청 데이터 생성
        request = {
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs,
            'caller_id': self.main_process_id
        }
        
        # 요청 전송
        self.process_registry[process_id]['request_queue'].append(request)
        return True

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
    
    def set_batch(self, strategy, data):
        with self.lock:
            for code, name in data.items():
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
    
