from public import *
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
import threading
import copy
import time
import logging
import uuid

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
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value)
        
        # 기존 아이템 재사용
        existing_item = table_widget.item(row, col)
        if existing_item:
            # 값이 같으면 업데이트 필요 없음
            if existing_item.text() == display_value:
                return
            existing_item.setText(display_value)
            cell_item = existing_item
        else:
            cell_item = QTableWidgetItem(display_value)
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
        self.processes = {} # name -> process info
        self.task_queues = {} # name -> manager.list
        self.result_dicts = {} # name -> manager.dict

        self.is_shutting_down = False

    def register(self, name, target_class=None, use_thread=True, use_process=False):
        if use_process:
            return self._register_process(name, target_class)
        elif use_thread:
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
            
        # 프로세스 워커 중지
        elif worker_name in self.task_queues:
            logging.info(f"프로세스 {worker_name} 종료 중...")
            
            # 종료 명령 전송
            if worker_name in self.task_queues:
                self.task_queues[worker_name].append({'command': 'stop'})
            
            # 프로세스 종료 대기
            process = self.processes[worker_name].get('process')
            if process:
                process.join(2.0)
                if process.is_alive():
                    process.terminate()
            
            # 정리
            if worker_name in self.task_queues:
                del self.task_queues[worker_name]
            if worker_name in self.result_dicts:
                del self.result_dicts[worker_name]
            del self.processes[worker_name]
            
            logging.info(f"프로세스 {worker_name} 종료 완료")
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
            
        # 모든 프로세스 워커 중지
        for name in list(self.processes.keys()):
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
            
        # 프로세스인 경우
        if worker_name in self.processes:
            return self._process_call_sync(worker_name, '_get_var', [var_name], {})
            
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
            
        # 프로세스인 경우
        if worker_name in self.processes:
            return self._process_call_sync(worker_name, '_set_var', [var_name, value], {}) is not None
            
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
        
        # 프로세스인 경우
        if worker_name in self.processes:
            return self._process_call_sync(worker_name, method_name, args, kwargs)
        
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
        
        # 프로세스인 경우
        if worker_name in self.processes:
            return self._process_call_async(worker_name, method_name, args, kwargs, callback)
        
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

    def _register_process(self, name, target_class):
        """프로세스 워커 등록"""
        # 공유 객체 생성
        if not self.manager:
            from multiprocessing import Manager
            self.manager = Manager()

        self.task_queues[name] = self.manager.list()
        self.result_dicts[name] = self.manager.dict()

        # 프로세스 정보 저장
        self.processes[name] = {
            'callbacks': {},  # task_id -> callback
            'events': {},     # task_id -> event
            'status': 'running'  # 프로세스 상태: connecting, running, stopping
        }
        logging.info(f"프로세스 {name} 연결 중...")

        target_module = target_class.__module__
        target_name = target_class.__name__

        # 프로세스 시작
        from multiprocessing import Process
        process = Process(
            target=process_worker_main,
            args=(name, (target_module, target_name), self.task_queues[name], self.result_dicts[name]),
            daemon=True
        )
        process.start()
        
        # 프로세스 정보 저장
        self.processes[name]['process'] = process
        self.processes[name]['status'] = 'running'

        logging.debug(f"프로세스 등록: {name} (PID: {process.pid})")
        return self
        
    def _process_call_sync(self, process_name, method_name, args, kwargs):
        """프로세스 동기식 호출"""
        if self.is_shutting_down:
            return None
        
        process_info = self.processes.get(process_name)
        if not process_info:
            if not self.is_shutting_down:
                logging.error(f"프로세스 없음: {process_name}")
            return None
        
        # 태스크 ID 생성
        task_id = str(uuid.uuid4())
        
        # 작업 전송
        self.task_queues[process_name].append({
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })

        # 결과 대기
        start_time = time.time()
        while task_id not in self.result_dicts[process_name]:
            if time.time() - start_time > 20.0:
                logging.warning(f"프로세스 호출 타임아웃: {process_name}.{method_name}")
                return None
            time.sleep(0.001)
            
        # 결과 처리
        result = self.result_dicts[process_name][task_id]
        del self.result_dicts[process_name][task_id] # 결과 정리

        if result['status'] == 'success':
            return result['result']
        else:
            return None
        
    def _process_call_async(self, process_name, method_name, args, kwargs, callback):
        """프로세스 비동기식 호출"""
        if self.is_shutting_down:
            return None
        
        process_info = self.processes.get(process_name)
        if not process_info:
            if not self.is_shutting_down:
                logging.error(f"프로세스 없음: {process_name}")
            return False
        
        # 큐 크기 확인
        if process_name in self.task_queues and len(self.task_queues[process_name]) > 1000:
            logging.warning(f"프로세스 {process_name} 큐가 가득 찼습니다. 작업 건너뜀.")
            if callback:
                callback(None)
            return False
        
        # 태스크 ID 생성
        task_id = str(uuid.uuid4())
        
        # 콜백 등록 (있는 경우)
        if callback:
            process_info['callbacks'][task_id] = callback
            
            # 콜백 타임스탬프 추가
            if 'callback_times' not in process_info:
                process_info['callback_times'] = {}
            process_info['callback_times'][task_id] = time.time()
            
            # 결과 대기 스레드
            def wait_for_result():
                try:
                    # 결과 대기
                    start_time = time.time()
                    while task_id not in self.result_dicts[process_name]:
                        if time.time() - start_time > 5.0:  # 5초 타임아웃
                            if callback:
                                callback(None)
                            process_info['callbacks'].pop(task_id, None)
                            process_info.get('callback_times', {}).pop(task_id, None)
                            return
                        time.sleep(0.001)
                    
                    # 결과 처리
                    result = self.result_dicts[process_name][task_id]
                    del self.result_dicts[process_name][task_id]  # 결과 정리
                    
                    # 콜백 호출
                    cb = process_info['callbacks'].pop(task_id, None)
                    if cb:
                        process_info.get('callback_times', {}).pop(task_id, None)
                        if result['status'] == 'success':
                            cb(result['result'])
                        else:
                            cb(None)
                except Exception as e:
                    logging.error(f"결과 처리 오류: {e}")
                    cb = process_info['callbacks'].pop(task_id, None)
                    process_info.get('callback_times', {}).pop(task_id, None)
                    if cb:
                        cb(None)
            
            # 결과 대기 스레드 시작
            import threading
            threading.Thread(target=wait_for_result, daemon=True).start()
        
        # 작업 전송
        self.task_queues[process_name].append({
            'task_id': task_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        # 주기적으로 자원 정리 (예: 매 100번째 호출마다)
        if hasattr(self, '_async_call_count'):
            self._async_call_count += 1
            if self._async_call_count % 100 == 0:
                self.cleanup_resources(process_name)
        else:
            self._async_call_count = 1
        
        return True

    # WorkerManager 클래스에 큐 정리 메서드 추가
    def cleanup_resources(self, process_name=None):
        """더 이상 필요하지 않은 자원 정리"""
        if process_name:
            self._cleanup_process_resources(process_name)
        else:
            # 모든 프로세스 자원 정리
            for name in list(self.processes.keys()):
                self._cleanup_process_resources(name)
                
    def _cleanup_process_resources(self, process_name):
        """특정 프로세스의 자원 정리"""
        if process_name not in self.processes:
            return
            
        process_info = self.processes[process_name]
        
        # 오래된 콜백 정리
        current_time = time.time()
        old_callbacks = []
        
        for task_id, callback_time in process_info.get('callback_times', {}).items():
            if current_time - callback_time > 30:  # 30초 이상 된 콜백은 제거
                old_callbacks.append(task_id)
                
        for task_id in old_callbacks:
            process_info['callbacks'].pop(task_id, None)
            process_info.get('callback_times', {}).pop(task_id, None)
            
        # 결과 딕셔너리 정리 (오래된 결과 제거)
        if process_name in self.result_dicts:
            # 복사본 만들어서 순회
            task_ids = list(self.result_dicts[process_name].keys())
            old_results = []
            
            for task_id in task_ids:
                # 필요한 경우 결과의 나이를 추적하는 로직 추가
                if task_id not in process_info['callbacks']:
                    old_results.append(task_id)
                    
            for task_id in old_results:
                if task_id in self.result_dicts[process_name]:
                    self.result_dicts[process_name].pop(task_id, None)
                
        # 큐 크기 확인 및 로깅
        if process_name in self.task_queues and len(self.task_queues[process_name]) > 100:
            logging.warning(f"프로세스 {process_name} 큐 크기: {len(self.task_queues[process_name])}")
            
# 클래스 외부에 독립 함수로 정의 (모듈 레벨)
def process_worker_main(name, target_info, task_queue, result_dict):
    """프로세스 워커 메인 함수"""
    try:
        # 커스텀 로거 초기화
        import logging
        init_logger()
        
        # 타겟 클래스 동적 임포트
        target_module, target_name = target_info
        import importlib
        module = importlib.import_module(target_module)
        target_class = getattr(module, target_name)
        
        # 인스턴스 생성
        target = target_class()
        logging.info(f"프로세스 {name} 시작됨")

        # 변수 접근/설정 메서드 추가
        def _get_var(var_name):
            """타겟 객체의 변수 값을 가져오는 내부 메서드"""
            try:
                return getattr(target, var_name, None)
            except Exception as e:
                logging.error(f"변수 접근 오류: {e}", exc_info=True)
                return None
                
        def _set_var(var_name, value):
            """타겟 객체의 변수 값을 설정하는 내부 메서드"""
            try:
                setattr(target, var_name, value)
                return True
            except Exception as e:
                logging.error(f"변수 설정 오류: {e}", exc_info=True)
                return None
                
        # 특수 메서드 등록
        target._get_var = _get_var
        target._set_var = _set_var
                
        # 작업 처리 루프
        import time
        last_cleanup_time = time.time()
        processed_count = 0
        processed_count_1000 = 0

        while True:
            # 주기적으로 큐 상태 확인 및 로깅
            current_time = time.time()
            if current_time - last_cleanup_time > 300:  # 5분마다 확인
                queue_size = len(task_queue)
                if queue_size > 200:
                    logging.warning(f"프로세스 {name} 큐 크기: {queue_size}")
                last_cleanup_time = current_time

            # 작업이 있는지 확인
            if len(task_queue) == 0:
                time.sleep(0.001)  # 0.01초에서 0.001초로 변경하여 응답성 개선
                continue

            # 큐가 너무 크면 오래된 작업 건너뛰기 (선택적)
            if len(task_queue) > 100:
                # 처리할 수 있는 작업 수 제한
                max_to_process = 50
                old_tasks = len(task_queue) - max_to_process
                if old_tasks > 0:
                    logging.warning(f"프로세스 {name} 큐가 너무 큽니다. {old_tasks}개 작업 건너뜀.")
                    # 가장 오래된 작업들 제거
                    for _ in range(old_tasks):
                        if len(task_queue) > 0:
                            old_task = task_queue.pop(0)
                            # 결과 처리를 위해 오류 상태로 응답
                            task_id = old_task.get('task_id')
                            if task_id:
                                result_dict[task_id] = {'status': 'error', 'error': "큐 과부하로 작업 취소됨"}
                        
            # 작업 가져오기
            task = task_queue.pop(0)
            
            # 종료 명령 확인
            if task.get('command') == 'stop':
                break
                
            # 작업 처리
            task_id = task.get('task_id')
            method_name = task.get('method')
            args = task.get('args', ())
            kwargs = task.get('kwargs', {})
            
            # 메서드 찾기
            method = getattr(target, method_name, None)
            if not method:
                result_dict[task_id] = {'status': 'error', 'error': f"메서드 없음: {method_name}"}
                continue
                
            # 메서드 실행
            try:
                result = method(*args, **kwargs)
                result_dict[task_id] = {'status': 'success', 'result': result}

            except Exception as e:
                logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                result_dict[task_id] = {'status': 'error', 'error': str(e)}

            processed_count += 1
            if processed_count % 5000 == 0:
                import gc
                gc.collect()
                if processed_count % 50000 == 0:
                    logging.info(f"프로세스 {name} 처리 횟수: {processed_count}")
                    processed_count = 0

    except Exception as e:
        logging.error(f"프로세스 {name} 오류: {e}", exc_info=True)
    finally:
        logging.info(f"프로세스 {name} 종료")

# 전역 관리자 인스턴스
la = WorkerManager()

class CounterTicker:
    """
    쓰레드 안전한, 전략별 종목 매수 횟수 카운터 클래스
    날짜가 변경되면 자동으로 카운터를 초기화합니다.
    """
    STRATEGY_CODE = "000000"        # 전략 자체 카운터 코드
    WHOLE_TICKER_CODE = "999999"    # 전체 종목 카운터 코드
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
                self.data[strategy][self.STRATEGY_CODE] = { "name": name, "limit": strategy_limit if strategy_limit is not None else self.DEFAULT_STRATEGY_LIMIT, "count": 0 }
                self.data[strategy][self.WHOLE_TICKER_CODE] = { "name": name, "limit": ticker_limit if ticker_limit is not None else self.DEFAULT_TICKER_LIMIT, "count": 0 }
                update = True
            else:
                if self.data[strategy][self.STRATEGY_CODE]["name"] != name:
                    self.data[strategy][self.STRATEGY_CODE]["name"] = name
                    update = True
                if strategy_limit is not None:
                    if self.data[strategy][self.STRATEGY_CODE]["limit"] != strategy_limit:
                        self.data[strategy][self.STRATEGY_CODE] = { "limit": strategy_limit, "count": 0 }
                        update = True
                if ticker_limit is not None:
                    if self.data[strategy][self.WHOLE_TICKER_CODE]["limit"] != ticker_limit:
                        self.data[strategy][self.WHOLE_TICKER_CODE] = { "limit": ticker_limit, "count": 0 }
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
            self.data[strategy][self.STRATEGY_CODE]["count"] += 1
            self.save_data()
    
    def get(self, strategy, code, name=None):
        with self.lock:
            if code not in self.data[strategy]:
                self.set(strategy, code, name if name is not None else "")
            if self.data[strategy][self.STRATEGY_CODE]["count"] >= self.data[strategy][self.STRATEGY_CODE]["limit"]:
                return False
            ticker_info = self.data[strategy][code]
            ticker_limit = ticker_info["limit"] if ticker_info["limit"] > 0 else self.data[strategy][self.WHOLE_TICKER_CODE]["limit"]
            if ticker_info["count"] >= ticker_limit:
                return False
            return True
    
