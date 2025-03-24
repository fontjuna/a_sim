from public import *
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread
from PyQt5.QtGui import QColor
from queue import Empty, Queue
import sys
import threading
import copy
import multiprocessing as mp
import uuid
import time
import logging
from tabulate import tabulate

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
            return self.dict.items()

    def keys(self):
        with self.lock:
            return self.dict.keys()

    def values(self):
        with self.lock:
            return self.dict.values()

    def set(self, key, value):
        with self.lock:
            self.dict[key] = value

    def get(self, key):
        with self.lock:
            return self.dict.get(key, None)

    def contains(self, item):
        with self.lock:
            return item in self.dict

    def remove(self, key):
        with self.lock:
            return self.dict.pop(key, None)

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

class ModelThread(QThread):
    def __init__(self, name, cls=None):
        QThread.__init__(self)
        self.name = name
        self.cls = cls
        self.work_q = Queue()
        self.daemon = True
        self.is_running = True

        gm.qdict[self.name] = self.work_q

    def run(self):
        logging.debug(f'{self.name} 시작...')
        while self.is_running:
            self.run_loop()
            time.sleep(0.01)

    def stop(self):
        self.is_running = False

    def run_loop(self):
        if not self.work_q.empty():
            data = self.work_q.get()
            if self.cls:
                obj = next((obj for obj in [self, self.cls] if hasattr(obj, data.order)), None)
            else:
                obj = self
            if obj == None or not isinstance(data, Work):
                logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                return
            method = getattr(obj, data.order)
            if isinstance(data, Work):
                method(**data.job)

class AnswerModel:
    result_dict = ThreadSafeDict()
    def __init__(self, name, work_q, answer_q):
        self.name = name
        self.work_q = work_q
        self.answer_q = answer_q
        self.is_running = True

    def logging_setup(self):
        pass

    def run(self):
        self.logging_setup()
        logging.debug(f'{self.name} 시작...')
        while self.is_running:
            self.run_loop()
            time.sleep(0.01)

    def stop(self):
        self.is_running = False

    def run_loop(self):
        if not self.work_q.empty():
            data = self.work_q.get()
            if data == None or not isinstance(data, (Work, Answer)):
                logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                return
            method = getattr(self, data.order)
            if isinstance(data, Work):
                method(**data.job)
            else:
                result = method(**data.job)
                self.answer_q.put(result)

class ModelProcess(AnswerModel, mp.Process):
    def __init__(self, name, work_q, answer_q, daemon=True):
        AnswerModel.__init__(self, name, work_q, answer_q)
        mp.Process.__init__(self, name=name, daemon=daemon)

    def run(self):
        AnswerModel.run(self)

    def stop(self):
        AnswerModel.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        mp.Process.start(self)
        return self

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
        self.data_dict = {}
        self.lock = threading.RLock()
        
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
        self._resize =  True
    
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
        with self.lock:
            # 0. 키가 정수형인 경우
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return  None
            
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
            with self.lock:
                # 키 필드 검증
                for item in data:
                    if self.key_column not in item:
                        raise ValueError(f"모든 항목에 키 컬럼('{self.key_column}')이 필요합니다.")
                
                # 데이터 대체
                self.data = []
                for item in data:
                    key_value = item[self.key_column]
                    self._set_item_by_key(key_value, item)
                return True
            
        # 딕셔너리 타입 체크 (업데이트 모드)
        if isinstance(data, dict):
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data:
                return False
                
            with self.lock:
                # 1. 특정 키 업데이트/추가
                if key is not None:
                    return self._set_item_by_key(key, valid_data)
                
                # 2. 필터링된 항목 업데이트
                if filter is not None:
                    return self._update_filtered_items(filter, valid_data)
                
                # 3. 전체 항목 업데이트
                return self._update_all_items(valid_data)
                
        return False
    
    def _set_item_by_key(self, key, data):
        """키로 항목 추가/업데이트"""
        # 기존 항목이 있으면 업데이트
        item = self.data_dict.get(key)
        
        if item is not None:
            # 기존 항목 업데이트
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
        
        self.data.append(item)  # 리스트에 추가
        self.data_dict[key] = item  # 딕셔너리에 추가
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
        with self.lock:
            # 1. 특정 키 삭제
            if key is not None:
                item = self.data_dict.pop(key, None)
                if item is not None:
                    self.data.remove(item)  # 리스트에서도 삭제
                    self._resize = True
                    return True
                return False
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                # 삭제할 항목들을 미리 찾음
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if items_to_delete:
                    for item in items_to_delete:
                        key_val = item.get(self.key_column)
                        self.data_dict.pop(key_val, None)
                        self.data.remove(item)
                    self._resize = True
                    return True
                return False
            
            # 3. 전체 데이터 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            return True

    def _delete_filtered_items(self, filter):
        """필터링된 항목 삭제"""
        original_len = len(self.data)
        self.data = [item for item in self.data if not self._match_conditions(item, filter)]
        return len(self.data) < original_len
    
    def len(self, filter=None):
        """
        len() -> int                      # 전체 행 수 반환
        len(filter={}) -> int             # 조건 만족 행 수 반환
        """
        with self.lock:
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
    
    def in_key(self, key):
        """
        in_key('key') -> bool             # 키 존재 여부
        """
        with self.lock:
            return self._find_index_by_key(key) is not None
    
    def in_column(self, column, value):
        """
        in_column('col', 값) -> bool      # 컬럼에 값 존재 여부
        """
        with self.lock:
            if column not in self.all_columns:
                return False
            
            # 타입 변환
            converted_value = self._convert_value(column, value)
            
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
    
    def sum(self, column=None, filter=None):
        """
        sum(column=['c1', 'c2']) -> (합1, 합2, ...)  # 지정 컬럼 합계 튜플 반환
        sum(column=[], filter={}) -> (합1, 합2, ...)  # 조건 만족 행들의 합계 반환
        """
        with self.lock:
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
    
    def _find_index_by_key(self, key):
        """키 값으로 항목의 인덱스 찾기"""
        item = self.data_dict.get(key)
        if item is not None:
            try:
                return self.data.index(item)
            except ValueError:
                return None
        return None

    def _find_item_by_key(self, key):
        """키 값으로 항목 찾기"""
        return self.data_dict.get(key)
    
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
        # 데이터 복사본 생성 (락 내부에서 최소한의 작업만 수행)
        data_copy = None
        resize_needed = False
        with self.lock:
            data_copy = copy.deepcopy(self.data)
            resize_needed = self._resize
            if resize_needed:
                self._resize = False  # 락 내부에서 상태 업데이트
        
        if not data_copy:
            table_widget.setRowCount(0)
            return
        
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        columns = self.display_columns or self.all_columns
        
        if resize_needed:
            table_widget.setRowCount(len(data_copy))
            table_widget.setColumnCount(len(columns))
            table_widget.setHorizontalHeaderLabels(columns)
        
        try:
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column], self.profit_columns)
            
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
            
    def _set_table_cell(self, table_widget, row, col, column, value, profit_columns):
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
    
    def update_cell(self, table_widget, key_value, column, value):
        """
        특정 셀만 업데이트
        """
        # 데이터 업데이트
        with self.lock:
            idx = self._find_index_by_key(key_value)
            if idx is None:
                return False
            
            # 데이터 업데이트 (타입 변환 수행)
            self.data[idx][column] = self._convert_value(column, value)
        
        # UI 갱신
        columns = self.display_columns or self.all_columns
        try:
            col_idx = columns.index(column)
        except ValueError:
            return False
        
        # 테이블에서 해당 행 찾기
        row_idx = -1
        for i in range(table_widget.rowCount()):
            item = table_widget.item(i, columns.index(self.key_column))
            if item and item.text() == str(key_value):
                row_idx = i
                break
        
        if row_idx != -1:
            with self.lock:
                value = self.data[idx][column]
            
            self._set_table_cell(table_widget, row_idx, col_idx, column, value, self.profit_columns)
            return True
                
        return False

class TableManager:
    def __init__(self, config):
        """쓰레드 안전한 데이터 관리 클래스 초기화"""
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        self.lock = threading.RLock()
        self.lock_timeout = 1.0  # 락 타임아웃 (초)
        
        # 설정 정보 저장
        self.key_column = config.get('키', '')
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('확장', config.get('컬럼', []))
        self.display_columns = config.get('헤더', [])
        
        if not self.key_column: raise ValueError("'키' 컬럼을 지정해야 합니다.")
        if not self.all_columns: raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
        
        # UI 관련 상수
        self.align_right = Qt.AlignRight | Qt.AlignVCenter
        self.align_left = Qt.AlignLeft | Qt.AlignVCenter
        self.align_center = Qt.AlignCenter
        
        self.color_positive = QColor(255, 0, 0)  # 적색 (손익 양수)
        self.color_negative = QColor(0, 0, 255)  # 청색 (손익 음수)
        self.color_zero = QColor(0, 0, 0)        # 검정색 (손익 0)
        
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률", "등락율"]
        self._resize = True  # 테이블 크기 조정 필요 여부
        self._sync_version = 0  # 데이터 변경 추적용 버전 카운터
    
    def _with_lock(self, func, default_value=None):
        """락을 획득하고 함수를 실행한 후 락을 해제하는 헬퍼 메서드"""
        if not self.lock.acquire(timeout=self.lock_timeout):
            logging.warning(f"TableManager: {func.__name__} 메서드에서 락 획득 실패")
            return default_value
        try:
            return func()
        finally:
            self.lock.release()
    
    def _convert_value(self, column, value):
        """값을 적절한 타입으로 변환"""
        # 기본값 정의
        default_values = {
            'int': 0, 'float': 0.0, 'str': ""
        }
        
        # 문자열 처리
        if isinstance(value, str):
            value = value.strip()
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
                return value
        except (ValueError, TypeError):
            return default_values['int'] if column in self.int_columns else \
                   default_values['float'] if column in self.float_columns else \
                   str(value)
    
    def _process_item(self, item):
        """항목의 각 값을 적절한 타입으로 변환"""
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
        """데이터 조회 함수"""
        def _get():
            # 인덱스로 행 조회
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return None
            
            # 키와 컬럼으로 조회
            if key is not None and column is not None:
                item = self.data_dict.get(key)
                if item is None:
                    return None
                
                if isinstance(column, (list, tuple)):
                    return item.get(column[0]) if len(column) == 1 else \
                           tuple(item.get(col) for col in column)
                elif isinstance(column, str):
                    return item.get(column)
                return None
            
            # 전체 데이터와 특정 컬럼 조회
            if column is not None:
                if isinstance(column, (list, tuple)):
                    result = []
                    for item in self.data:
                        filtered_item = {col: item.get(col) for col in column if col in item}
                        result.append(filtered_item)
                    return copy.deepcopy(result)
                elif isinstance(column, str):
                    return [item.get(column) for item in self.data]
            
            # 키로 행 조회
            if key is not None:
                item = self.data_dict.get(key)
                return copy.deepcopy(item) if item else None
            
            # 필터로 조회
            if filter is not None:
                return self._filter_data(filter)
            
            # 전체 데이터 조회
            data_copy = copy.deepcopy(self.data)
            
            # DataFrame 반환
            if type == 'df':
                try:
                    import pandas as pd
                    return pd.DataFrame(data_copy)
                except ImportError:
                    raise ImportError("pandas 라이브러리가 필요합니다.")
            
            return data_copy
        
        default_value = [] if filter is not None or column is not None else None
        return self._with_lock(_get, default_value)
    
    def set(self, key=None, filter=None, data=None):
        """데이터 추가/수정 함수"""
        if data is None:
            return False
        
        def _set():
            # 리스트로 전체 데이터 대체
            if isinstance(data, list):
                for item in data:
                    if self.key_column not in item:
                        raise ValueError(f"모든 항목에 키 컬럼('{self.key_column}')이 필요합니다.")
                
                self.data = []
                self.data_dict = {}
                for item in data:
                    key_value = item[self.key_column]
                    self._set_item_by_key(key_value, item)
                
                self._sync_version += 1  # 버전 증가
                return True
            
            # 딕셔너리로 업데이트
            if isinstance(data, dict):
                valid_data = {k: v for k, v in data.items() if k in self.all_columns}
                if not valid_data:
                    return False
                
                result = False
                # 키로 업데이트
                if key is not None:
                    result = self._set_item_by_key(key, valid_data)
                # 필터로 업데이트
                elif filter is not None:
                    result = self._update_filtered_items(filter, valid_data)
                # 전체 업데이트
                else:
                    result = self._update_all_items(valid_data)
                
                if result:
                    self._sync_version += 1  # 버전 증가
                return result
            
            return False
        
        return self._with_lock(_set, False)
    
    def _set_item_by_key(self, key, data):
        """키로 항목 추가/업데이트"""
        # 기존 항목 업데이트
        item = self.data_dict.get(key)
        if item is not None:
            for column, value in data.items():
                if column in self.all_columns and column != self.key_column:
                    item[column] = self._convert_value(column, value)
            return True
        
        # 신규 항목 추가
        item = {}
        for column in self.all_columns:
            if column == self.key_column:
                item[column] = key
            else:
                item[column] = 0 if column in self.int_columns else \
                              0.0 if column in self.float_columns else ""
        
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
        """데이터 삭제 함수"""
        def _delete():
            # 키로 삭제
            if key is not None:
                item = self.data_dict.pop(key, None)
                if item is not None and item in self.data:
                    self.data.remove(item)
                    self._resize = True
                    self._sync_version += 1
                    return True
                return False
            
            # 필터로 삭제
            if filter is not None:
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if not items_to_delete:
                    return False
                
                for item in items_to_delete:
                    key_val = item.get(self.key_column)
                    self.data_dict.pop(key_val, None)
                    if item in self.data:
                        self.data.remove(item)
                
                self._resize = True
                self._sync_version += 1
                return True
            
            # 전체 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            self._sync_version += 1
            return True
        
        return self._with_lock(_delete, False)
    
    def len(self, filter=None):
        """행 수 반환 함수"""
        def _len():
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
        
        return self._with_lock(_len, 0)
    
    def in_key(self, key):
        """키 존재 여부 확인 함수"""
        def _in_key():
            return key in self.data_dict
        
        return self._with_lock(_in_key, False)
    
    def in_column(self, column, value):
        """컬럼에 값 존재 여부 확인 함수"""
        def _in_column():
            if column not in self.all_columns:
                return False
            
            converted_value = self._convert_value(column, value)
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
        
        return self._with_lock(_in_column, False)
    
    def sum(self, column=None, filter=None):
        """컬럼 합계 계산 함수"""
        def _sum():
            if not column:
                return ()
            
            data_to_sum = self.data
            if filter is not None:
                data_to_sum = self._filter_data(filter)
            
            result = []
            col_list = [column] if isinstance(column, str) else column
            for col in col_list:
                if col in self.int_columns or col in self.float_columns:
                    total = sum(item.get(col, 0) for item in data_to_sum)
                    result.append(total)
                else:
                    result.append(0)
            
            return tuple(result)
        
        return self._with_lock(_sum, ())
    
    def _filter_data(self, conditions):
        """조건에 맞는 데이터 필터링"""
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
            
            # 문자열 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 컬럼 간 비교
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                # '@'로 시작하는 문자열은 다른 컬럼 참조
                if isinstance(compare_value, str) and compare_value.startswith('@'):
                    other_column = compare_value[1:]
                    if other_column not in row:
                        return False
                    other_value = row[other_column]
                    if not self._compare_values(item_value, op, other_value):
                        return False
                # 일반 비교
                elif not self._compare_values(item_value, op, compare_value):
                    return False
            # 값 일치 여부
            elif item_value != value:
                return False
        
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """값 비교 연산"""
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
        """테이블 위젯 업데이트 - 락 사용 최소화"""
        # 데이터 스냅샷 생성
        data_snapshot = None
        columns = None
        resize_needed = False
        version = 0
        
        # 데이터 스냅샷만 빠르게 생성
        def _get_snapshot():
            nonlocal data_snapshot, columns, resize_needed, version
            
            if not self.data:
                return False
            
            data_snapshot = copy.deepcopy(self.data)
            columns = self.display_columns or self.all_columns
            resize_needed = self._resize
            version = self._sync_version
            
            if resize_needed:
                self._resize = False
            
            return True
        
        # 스냅샷 생성 실패시 종료
        if not self._with_lock(_get_snapshot, False):
            table_widget.setRowCount(0)
            return
        
        # 락 없이 UI 업데이트
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        
        try:
            row_count = len(data_snapshot)
            col_count = len(columns)
            
            # 기존 테이블 크기와 다르면 리사이즈 필요
            if table_widget.rowCount() != row_count or table_widget.columnCount() != col_count:
                resize_needed = True
            
            # 테이블 크기 조정
            if resize_needed:
                table_widget.setRowCount(row_count)
                table_widget.setColumnCount(col_count)
                table_widget.setHorizontalHeaderLabels(columns)
            
            # 데이터 표시
            for row, item in enumerate(data_snapshot):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column])
            
            # 행/열 크기 조정
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
        """테이블 셀 설정"""
        # 값 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value)
        
        # 셀 아이템 설정
        cell_item = table_widget.item(row, col)
        if cell_item:
            if cell_item.text() == display_value:
                return
            cell_item.setText(display_value)
        else:
            cell_item = QTableWidgetItem(display_value)
            table_widget.setItem(row, col, cell_item)
        
        # 정렬 및 색상 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(self.align_right)
        else:
            cell_item.setTextAlignment(self.align_left)
        
        # 손익 컬럼 색상 설정
        if column in self.profit_columns and isinstance(value, (int, float)):
            if value < 0:
                cell_item.setForeground(self.color_negative)
            elif value > 0:
                cell_item.setForeground(self.color_positive)
            else:
                cell_item.setForeground(self.color_zero)
                
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

def request_time_check(kind='order', cond_text = None):
    if kind == 'order':
        wait_time = gm.ord.check_interval()
    elif kind == 'request':
        wait_time = max(gm.req.check_interval(), gm.req.check_condition_interval(cond_text) if cond_text else 0)

    #logging.debug(f'대기시간: {wait_time} ms kind={kind} cond_text={cond_text}')
    if wait_time > 1666: # 1.666초 이내 주문 제한
        msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {int(wait_time/1000)} 초' \
            if cond_text is None else f'{cond_text} 1분 이내에 같은 조건 호출 불가 합니다. 대기시간: {int(wait_time/1000)} 초'
        gm.toast.toast(msg, duration=dc.td.TOAST_TIME)
        logging.warning(msg)
        return False
    elif wait_time > 0:
        msg = f'빈번한 요청은 시간 제한을 받습니다. 대기시간: {int(wait_time/1000)} 초'
        gm.toast.toast(msg, duration=wait_time)
        logging.info(msg)

    time.sleep((wait_time + 100)/1000) # gm.ord.put_request(Work('com_SendOrder', job=job)) 사용 대신

    if kind == 'order':
        gm.ord.update_request_times()
    elif kind == 'request':
        if cond_text: gm.req.update_condition_time(cond_text)
        else: gm.req.update_request_times()

    return True

@dataclass
class DataTables:
    잔고합산: TableManager = field(default_factory=TableManager(gm.tbl.hd잔고합산))
    잔고목록: TableManager = field(default_factory=TableManager(gm.tbl.hd잔고목록))
    조건목록: TableManager = field(default_factory=TableManager(gm.tbl.hd조건목록))
    손익목록: TableManager = field(default_factory=TableManager(gm.tbl.hd손익목록))
    접수목록: TableManager = field(default_factory=TableManager(gm.tbl.hd접수목록))
    예수금: TableManager = field(default_factory=TableManager(gm.tbl.hd예수금))
    일지합산: TableManager = field(default_factory=TableManager(gm.tbl.hd일지합산))
    일지목록: TableManager = field(default_factory=TableManager(gm.tbl.hd일지목록))
    체결목록: TableManager = field(default_factory=TableManager(gm.tbl.hd체결목록))
    전략정의: TableManager = field(default_factory=TableManager(gm.tbl.hd전략정의))

class OrderManager(QThread):
    def __init__(self, cmd_list):
        super().__init__()
        self.is_running = True
        self.cmd_list = cmd_list

    def run(self):
        while self.is_running:
            order = self.cmd_list.get() # order : SendOrder parameters
            if not request_time_check(kind='order', cond_text=order['rqname']): continue

            code = order['code']
            kind = ['', '매수', '매도', '매수취소', '매도취소', '매수정정', '매도정정'][order['ordtype']]
            key = f'{code}_{kind}'
            row = gm.주문목록.get(key=key)
            if not row: 
                # 자동 취소, 외부주문은 이곳으로 오지 않는다. 그 외는 직접 만들어 줘야 한다. order_buy, order_sell을 이용
                logging.error(f'********* 주문목록에 없는 종목입니다. {key} *********') 
                continue

            gm.주문목록.set(key=key, data={'상태': '전송'})
            #logging.debug(f'주문목록 키 확인 :\n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
            reason = order.pop('msg', None)
            if reason is None: reason = dc.fid.주문유형FID[f'{order["ordtype"]:01d}']
            gm.pro.api.SendOrder(**order)

            msg = f"{reason} : {row['전략']} {code} {row['종목명']} 주문수량:{order['quantity']}주 / 주문가:{order['price']}원"
            if gm.config.gui_on: gm.qdict['msg'].put(Work('주문내용', {'msg': msg}))
            #self.dbm_order_upsert(idx, code, name, quantity, price, ordtype, hoga, screen, rqname, accno, ordno)
            idx = int(row['전략'][-2:])
            gm.pro.admin.dbm_order_upsert(idx, code, row['종목명'], order['quantity'], order['price'], order['ordtype'], order['hoga'], order['screen'], order['rqname'], order['accno'], order['ordno'])

            logging.info(f'주문전송: {key} {order}')

    def stop(self):
        self.is_running = False
