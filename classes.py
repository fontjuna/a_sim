from public import *
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread
from PyQt5.QtGui import QColor
from queue import Empty
import sys
import threading
import copy
import multiprocessing as mp
import uuid
import time
import logging

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

class Model:
    result_dict = ThreadSafeDict()
    def __init__(self, name, qdict, cls=None):
        self.name = name
        self.qdict = qdict
        self.cls = cls
        self.myq = self.qdict[self.name]
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
        if not self.myq.request.empty():
            data = self.myq.request.get()
            if self.cls:
                obj = next((obj for obj in [self, self.cls] if hasattr(obj, data.order)), None)
            else:
                obj = self
            if obj == None or not isinstance(data, (Work, Answer, Reply)):
                logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                return
            method = getattr(obj, data.order)
            if isinstance(data, Work):
                method(**data.job)
            else:
                sender = data.sender
                for k, q in self.qdict.items():
                    if k == sender:
                        if isinstance(data, Answer):
                            result_q = q.answer
                        else:
                            result_q = q.reply
                        break
                qid = data.qid
                result = method(**data.job)
                result_q.put((qid, result))

    def put(self, target, work): # bus 대신 사용
        if not isinstance(work, Work):
            raise ValueError('Work 객체가 필요합니다.')

        target_q = self.qdict.get(target, None)
        if target_q == None:
            logging.debug(f"{self.name}: Target '{target}' not found in qlist")
            return
        target_q.request.put(work)
        return True

    def get(self, target, request, timeout=dc.td.WAIT_SEC, check_interval=dc.td.RUN_INTERVAL):
        """
        대상에게 요청을 보내고 응답을 기다립니다.

        Args:
            target_name: 대상 프로세스/쓰레드 이름
            request: Answer 또는 Reply 객체
            timeout: 응답 대기 시간(초)
            check_interval: 결과 확인 간격(초)

        Returns:
            응답 결과 또는 타임아웃시 None
        """
        # 대상 큐 찾기
        target_q = self.qdict[target]

        if not target_q:
            logging.debug(f"{self.name}: Target '{target}' not found in qlist")
            return None

        # 응답 큐 선택
        if isinstance(request, Answer):
            result_queue = self.myq.answer
        else:
            result_queue = self.myq.reply

        # qid 생성
        qid = str(uuid.uuid4())
        request.qid = qid
        request.sender = self.name

        # 요청 전송
        #logging.debug(f"{self.name}: Sending {type(request).__name__} to {target} (qid: {qid})")
        target_q.request.put(request)

        # 응답 대기
        end_time = time.time() + timeout
        while time.time() < end_time:
            # 결과 딕셔너리 확인
            result = self.result_dict.get(qid)
            if result:
                self.result_dict.remove(qid)
                return result

            # 응답 큐 확인
            try:
                while not result_queue.empty():
                    result_qid, result_value = result_queue.get_nowait()
                    if result_qid == qid:
                        return result_value
                    else:
                        # 다른 요청의 결과 저장
                        self.result_dict.set(result_qid, result_value)
            except Empty:
                pass

            time.sleep(check_interval)

        #logging.debug(f"{self.name}: Request to {target} timed out after {timeout}s")
        return None

class ModelThread(Model, QThread):
    def __init__(self, name, qdict, cls=None):
        Model.__init__(self, name, qdict, cls)
        QThread.__init__(self)
        self.daemon = True

    def run(self):
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 쓰레드 종료...')

    def start(self):
        QThread.start(self)
        return self

class ModelProcess(Model, mp.Process):
    def __init__(self, name, qdict, cls=None, daemon=True):
        Model.__init__(self, name, qdict, cls)
        mp.Process.__init__(self, name=name, daemon=True)

    def run(self):
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        mp.Process.start(self)
        return self

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
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률" ]

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
                    return self.data[key]
                return  None
            
            # 1. 특정 키 + 특정 컬럼 조회
            if key is not None and column is not None:
                item = self._find_item_by_key(key)
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
                item = self._find_item_by_key(key)
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
        idx = self._find_index_by_key(key)
        
        # 기존 항목이 있으면 업데이트
        if idx is not None:
            for column, value in data.items():
                if column in self.all_columns and column != self.key_column:
                    self.data[idx][column] = self._convert_value(column, value)
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
                idx = self._find_index_by_key(key)
                if idx is not None:
                    del self.data[idx]
                    self._resize = True
                    return True
                return False
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                deleted = self._delete_filtered_items(filter)
                self._resize = deleted
                return deleted
            
            # 3. 전체 데이터 삭제
            self.data = []
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
        for i, item in enumerate(self.data):
            if item.get(self.key_column) == key:
                return i
        return None
    
    def _find_item_by_key(self, key):
        """키 값으로 항목 찾기"""
        idx = self._find_index_by_key(key)
        if idx is not None:
            return self.data[idx]
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
        # 화면 표시만 하므로 락 불필요, 데이터 복사본 생성
        with self.lock:
            data_copy = copy.deepcopy(self.data)
        
        if not data_copy:
            table_widget.setRowCount(0)
            return
        
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        columns = self.display_columns or self.all_columns
        if self._resize:
            table_widget.setRowCount(len(data_copy))
            table_widget.setColumnCount(len(columns))
            table_widget.setHorizontalHeaderLabels(columns)
        
        try:
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column], self.profit_columns)
            
            if self._resize:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                self._resize = False

                if stretch: table_widget.horizontalHeader().setStretchLastSection(stretch)

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
    
class TimeLimiter:
    def __init__(self, name, second=5, minute=100, hour=1000):
        self.name = name
        self.SEC = second
        self.MIN = minute
        self.HOUR = hour
        self.json_file = os.path.join(get_path(dc.fp.CONFIG_PATH), f'{name}_time_limiter.json')
        self.request_count = { 'second': 0, 'minute': 0, 'hour': 0 }
        self.first_request_time = { 'second': 0, 'minute': 0, 'hour': 0 }
        self.condition_times = {}  # 조건별 마지막 실행 시간
        self.lock = threading.Lock()

        self._load_from_json()

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
        self._save_to_json()

    def update_condition_time(self, condition):
        with self.lock:
            self.condition_times[condition] = time.time() * 1000
        self.update_request_times()

    def _save_to_json(self):
        data = {
            'date': time.strftime("%Y%m%d"),
            'last_update': time.time() * 1000,
            'request_count': self.request_count,
            'first_request_time': self.first_request_time,
            'condition_times': self.condition_times
        }
        threading.Thread(target=self._async_save, args=(data,), daemon=True).start()

    def _async_save(self, data):
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f'time_limiter 저장 오류: {type(e).__name__} - {e}', exc_info=True)

    def _load_from_json(self):
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                current_time = time.time() * 1000
                today = time.strftime("%Y%m%d")

                # 날짜가 다르면 초기화
                if data.get('date') != today:
                    self.request_count = {'second': 0, 'minute': 0, 'hour': 0}
                    self.first_request_time = {'second': 0, 'minute': 0, 'hour': 0}
                    self.condition_times = {}
                    self._save_to_json()
                    return

                # 카운트 로드
                self.request_count = data.get('request_count', {'second': 0, 'minute': 0, 'hour': 0})
                self.first_request_time = data.get('first_request_time', {'second': 0, 'minute': 0, 'hour': 0})
                # 1분 이내의 condition만 로드
                self.condition_times = { k: v for k, v in data.get('condition_times', {}).items() if current_time - v <= 60000 }

        except FileNotFoundError:
            self.request_count = {'second': 0, 'minute': 0, 'hour': 0}
            self.first_request_time = {'second': 0, 'minute': 0, 'hour': 0}
            self.condition_times = {}
            self._save_to_json()

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

# 사용 예시
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 설정 정보
    config = {
        '키': '종목코드',
        '정수': ['보유수량'],
        '실수': ['현재가', '매입가', '평가금액', '손익금액', '손익률'],
        '컬럼': ['종목코드', '종목명', '현재가', '매입가', '보유수량', '평가금액', '손익금액', '손익률'],
        '헤더': ['종목코드', '종목명', '현재가', '매입가', '보유수량', '평가금액', '손익금액', '손익률']
    }
    
    # 샘플 데이터 (타입 혼합됨)
    sample_data = [
        {"종목코드": "005930", "종목명": "삼성전자", "현재가": "72000", "매입가": "68000", "보유수량": "10", "평가금액": "720000", "손익금액": "40000", "손익률": "5.88"},
        {"종목코드": "035720", "종목명": "카카오", "현재가": "48000", "매입가": "50000", "보유수량": "5", "평가금액": "240000", "손익금액": "-10000", "손익률": "-2.00"},
        {"종목코드": "051910", "종목명": "LG화학", "현재가": "675000", "매입가": "650000", "보유수량": "2", "평가금액": "1350000", "손익금액": "50000", "손익률": "3.85"}
    ]
    
    # 관리 클래스 생성
    manager = TableManager(config)
    
    # 데이터 로드 (기존 방식)
    # manager.load_data(sample_data)
    
    # 새로운 API로 데이터 설정
    for item in sample_data:
        manager.set(key=item["종목코드"], data=item)
    
    # 메인 윈도우 설정
    main_window = QMainWindow()
    main_window.setWindowTitle("범용 데이터 관리")
    main_window.setGeometry(100, 100, 800, 400)
    
    # 중앙 위젯 설정
    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # 테이블 위젯 생성 및 데이터 표시
    table = QTableWidget()
    layout.addWidget(table)
    manager.display_data_in_table(table)
    
    # 개별 셀 업데이트 예시
    manager.update_cell(table, "005930", "현재가", 73000)
    
    # 새 API 사용 예시
    # 항목 추가/업데이트
    manager.set(key="000660", data={"종목명": "SK하이닉스", "현재가": 123000, "매입가": 115000, "보유수량": 3})
    
    # 특정 항목 조회
    samsung = manager.get(key="005930")
    print("삼성전자 정보:", samsung)
    
    # 데이터 필터링
    high_price = manager.get(filter={"현재가": ('>=', 100000)})
    print("고가 종목:", [(item["종목코드"], item["종목명"]) for item in high_price])
    
    # 특정 조건 항목 업데이트
    manager.set(filter={"종목명": "삼성"}, data={"현재가": 74000})
    
    # 합계 계산
    total_quantity, total_value = manager.sum(column=["보유수량", "평가금액"])
    print(f"총 보유수량: {total_quantity}주, 총 평가금액: {total_value:,.0f}원")
    
    # 항목 삭제
    manager.delete(key="035720")
    
    # 데이터 길이 확인
    count = manager.len()
    print(f"보유종목 수: {count}")
    
    # 키 존재 확인
    if manager.in_key("000660"):
        print("SK하이닉스 종목이 존재합니다.")
    
    # 컬럼 값 존재 확인
    if manager.in_column("종목명", "삼성전자"):
        print("삼성전자 종목이 존재합니다.")
    
    # 테이블 갱신
    manager.display_data_in_table(table)
    
    main_window.show()
    sys.exit(app.exec_())