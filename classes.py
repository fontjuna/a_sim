from public import dc, gm, get_path, save_json, load_json, QData, SharedQueue
from dataclasses import dataclass, field
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread
from multiprocessing import Process
import threading
import copy
import time
import logging
import os

class ThreadSafeList:
    def __init__(self):
        self.list = []
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock) # self.lock으로 wait, notify 를 관리

    def put(self, item):
        with self.lock:
            if isinstance(item, dict):
                logging.debug('put', len(self.list))
            self.list.append(item)
            self.not_empty.notify() # 대기중인 스레드에게 알림

    def get(self):
        # 리스트가 비어있으면 여기에서 대기
        with self.lock:
            if self.empty():
                self.not_empty.wait() # 대기
            if isinstance(self.list[0], dict):
                logging.debug('get', len(self.list))
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
    DEFAULT_STRATEGY_LIMIT = 1000   # 전략 자체 기본 제한
    DEFAULT_TICKER_LIMIT = 10       # 종목 기본 제한
    DEFAULT_DATA = { "date": dc.td.ToDay, "data": {} } # data = { code: { name: "", limit: 0, count: 0 }, ... } 
   
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
    
    def set_strategy(self, name, strategy_limit=None, ticker_limit=None):
        with self.lock:
            update = False
            if "000000" not in self.data: 
                self.data["000000"] = { 
                    "name": name, 
                    "all": ticker_limit if ticker_limit is not None else self.DEFAULT_TICKER_LIMIT, 
                    "limit": strategy_limit if strategy_limit is not None else self.DEFAULT_STRATEGY_LIMIT, 
                    "count": 0 }
                update = True

            if self.data["000000"]["name"] != name:
                self.data["000000"]["name"] = name
                update = True

            if strategy_limit is not None:
                if self.data["000000"]["limit"] != strategy_limit:
                    self.data["000000"].update({ "limit": strategy_limit, "count": 0 })
                    update = True

            if ticker_limit is not None:
                if self.data["000000"]["all"] != ticker_limit:
                    self.data["000000"].update({ "all": ticker_limit, "count": 0 })
                    update = True

            if update: self.save_data()
    
    def set_batch(self, data):
        with self.lock:
            for code, name in data.items():
                self.set(code, name)
            self.save_data()

    def set(self, code, name, limit=0):
        with self.lock:
            self.data[code] = { "name": name, "limit": limit, "count": 0 }
            self.save_data()

    def set_add(self, code):
        with self.lock:
            self.data[code]["count"] += 1
            self.data["000000"]["count"] += 1
            self.save_data()
    
    def get(self, code, name=""):
        with self.lock:
            if code not in self.data:
                self.set(code, name)
            if self.data["000000"]["count"] >= self.data["000000"]["limit"]:
                return False
            ticker_info = self.data[code]
            ticker_limit = ticker_info["limit"] if ticker_info["limit"] > 0 else self.data["000000"]["all"]
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
        self.lock = threading.RLock()  # RLock으로 변경

    def check_interval(self) -> int:
        current_time = time.time() * 1000
        
        # 락을 최소한으로 잡아서 데이터만 읽기
        with self.lock:
            req_counts = self.request_count.copy()
            first_times = self.first_request_time.copy()
        
        # 시간 계산은 락 밖에서 수행
        need_reset = {
            'second': current_time - first_times['second'] >= 1000,
            'minute': current_time - first_times['minute'] >= 60000,
            'hour': current_time - first_times['hour'] >= 3600000
        }
        
        wait_time = 0
        if req_counts['second'] >= self.SEC and not need_reset['second']:
            wait_time = max(wait_time, 1000 - (current_time - first_times['second']))
        elif req_counts['minute'] >= self.MIN and not need_reset['minute']:
            wait_time = max(wait_time, 60000 - (current_time - first_times['minute']))
        elif req_counts['hour'] >= self.HOUR and not need_reset['hour']:
            wait_time = max(wait_time, 3600000 - (current_time - first_times['hour']))
        
        # 리셋이 필요한 경우만 락을 다시 잡아서 업데이트
        if any(need_reset.values()):
            with self.lock:
                if need_reset['second']:
                    self.request_count['second'] = 0
                    self.first_request_time['second'] = 0
                if need_reset['minute']:
                    self.request_count['minute'] = 0
                    self.first_request_time['minute'] = 0
                if need_reset['hour']:
                    self.request_count['hour'] = 0
                    self.first_request_time['hour'] = 0
        
        return max(0, wait_time)

    def check_condition_interval(self, condition) -> int:
        current_time = time.time() * 1000
        
        # 락을 최소한으로 잡아서 데이터만 읽기
        with self.lock:
            last_time = self.condition_times.get(condition, 0)
        
        # 시간 계산은 락 밖에서 수행
        if current_time - last_time >= 60000:  # 1분(60000ms) 체크
            # 삭제가 필요한 경우만 락을 다시 잡음
            with self.lock:
                if condition in self.condition_times:
                    del self.condition_times[condition]
            return 0
        
        wait_time = int(60000 - (current_time - last_time))
        return max(0, wait_time)

    def _update_request_times_unsafe(self, current_time):
        """락 없이 실행되는 내부 메서드"""
        if self.request_count['second'] == 0:
            self.first_request_time['second'] = current_time
        if self.request_count['minute'] == 0:
            self.first_request_time['minute'] = current_time
        if self.request_count['hour'] == 0:
            self.first_request_time['hour'] = current_time

        self.request_count['second'] += 1
        self.request_count['minute'] += 1
        self.request_count['hour'] += 1

    def update_request_times(self):
        current_time = time.time() * 1000
        with self.lock:
            self._update_request_times_unsafe(current_time)

    def update_condition_time(self, condition):
        current_time = time.time() * 1000
        with self.lock:
            self.condition_times[condition] = current_time
            self._update_request_times_unsafe(current_time)

class TableManager:
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

def set_tables():
    gm.잔고합산 = TableManager(gm.tbl.hd잔고합산)
    gm.잔고목록 = TableManager(gm.tbl.hd잔고목록)
    gm.매수조건목록 = TableManager(gm.tbl.hd조건목록)
    gm.매도조건목록 = TableManager(gm.tbl.hd조건목록)
    gm.손익목록 = TableManager(gm.tbl.hd손익목록)
    gm.매매목록 = TableManager(gm.tbl.hd매매목록)
    gm.예수금 = TableManager(gm.tbl.hd예수금)
    gm.일지합산 = TableManager(gm.tbl.hd일지합산)
    gm.일지목록 = TableManager(gm.tbl.hd일지목록)
    gm.체결목록 = TableManager(gm.tbl.hd체결목록)
    gm.전략정의 = TableManager(gm.tbl.hd전략정의)
    gm.주문목록 = TableManager(gm.tbl.hd주문목록)
    gm.스크립트 = TableManager(gm.tbl.hd스크립트)
    gm.스크립트변수 = TableManager(gm.tbl.hd스크립트변수)
    gm.차트자료 = TableManager(gm.tbl.hd차트자료)
    gm.당일종목 = TableManager(gm.tbl.hd당일종목)
    gm.수동종목 = TableManager(gm.tbl.hd수동종목)

from PyQt5.QtCore import QThread
from multiprocessing import Process
from dataclasses import dataclass, field
import time
import threading

@dataclass
class QData:
    sender : str = None
    method : str = None
    answer : bool = False
    args : tuple = field(default_factory=tuple)
    kwargs : dict = field(default_factory=dict)

class SharedQueue:
    def __init__(self):
        # 모든 경우에 multiprocessing.Queue 사용 (쓰레드와 프로세스 모두 호환)
        import multiprocessing as mp
        self.request = mp.Queue()
        self.result = mp.Queue()
        self.stream = mp.Queue()
        self.payback = mp.Queue()

class BaseModel:
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        self.name = name
        self.cls = cls
        self.shared_qes = shared_qes
        self.args = args
        self.kwargs = kwargs
        self.instance = self.cls(*self.args, **self.kwargs)
        self.my_qes = shared_qes[name]
        self.running = False
        self.timeout = 15
        self.process_stats = {'request': 0, 'stream': 0}  # 처리 통계
        
    def process_q_data(self, q_data, queue_type='request'):
        if not isinstance(q_data, QData):
            return None
        if hasattr(self.instance, q_data.method):
            if q_data.answer:
                result = getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
                if queue_type == 'request':
                    self.shared_qes[q_data.sender].result.put(result)
                elif queue_type == 'stream':
                    self.shared_qes[q_data.sender].payback.put(result)
            else:
                getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
            
            # 처리 통계 업데이트
            #self.process_stats[queue_type] += 1

    def run(self):
        self.running = True
        if hasattr(self.kwargs, 'timeout'):
            self.timeout = self.kwargs.get('timeout')
        #self.instance = self.cls(*self.args, **self.kwargs)
        self.instance.order = self.order
        self.instance.answer = self.answer
        self.instance.frq_order = self.frq_order
        self.instance.frq_answer = self.frq_answer
        if hasattr(self.instance, 'initialize'):
            self.instance.initialize()
        while self.running:
            try:
                # 어떤 곳에서든 올 수 있는 request 처리
                if not self.my_qes.request.empty():
                    q_data = self.my_qes.request.get()
                    self.process_q_data(q_data, 'request')
                    #logging.debug(f"{self.name}: request 처리됨 - {q_data.method}")
                
                # 어떤 곳에서든 올 수 있는 stream 처리 (고빈도 가능)
                if not self.shared_qes[self.name].stream.empty():
                    q_data = self.shared_qes[self.name].stream.get()
                    self.process_q_data(q_data, 'stream')
                    #logging.debug(f"{self.name}: stream 처리됨 - {q_data.method}")
                
                if hasattr(self.instance, 'run_main_work'):
                    self.instance.run_main_work()

                time.sleep(0.01)
            except (EOFError, ConnectionError, BrokenPipeError):
                # 프로세스 종료 시 발생할 수 있는 예외들
                break
            except Exception as e:
                logging.debug(f"{self.name}: run() 에러 - {e}", exc_info=True)
                pass

    def stop(self):
        self.running = False
        if hasattr(self.instance, 'cleanup'):
            self.instance.cleanup()
        if hasattr(self, 'wait'):
            self.wait()

    def get_stats(self):
        """처리 통계 반환"""
        return f"{self.name}: request={self.process_stats['request']}, stream={self.process_stats['stream']}"

    # 인터페이스 메서드들
    def order(self, target, method, *args, **kwargs):
        """응답이 필요없는 명령 (answer=False)"""
        q_data = QData(sender=self.name, method=method, answer=False, args=args, kwargs=kwargs)
        self.shared_qes[target].request.put(q_data)

    def answer(self, target, method, *args, **kwargs):
        """응답이 필요한 요청 (answer=True)"""
        q_data = QData(sender=self.name, method=method, answer=True, args=args, kwargs=kwargs)
        self.shared_qes[target].request.put(q_data)
        try:
            return self.my_qes.result.get(timeout=self.timeout)
        except TimeoutError:
            logging.error(f"answer() 타임아웃:{self.name}의 요청 : {target}.{method}", exc_info=True)
            return None
        except Exception as e:
            logging.error(f"answer() 오류:{self.name}의 요청 : {target}.{method} - {e}", exc_info=True)
            return None

    def frq_order(self, target, method, *args, **kwargs):
        """스트림 명령 (answer=False)"""
        q_data = QData(sender=self.name, method=method, answer=False, args=args, kwargs=kwargs)
        self.shared_qes[target].stream.put(q_data)

    def frq_answer(self, target, method, *args, **kwargs):
        """스트림 요청/응답 (answer=True)"""
        q_data = QData(sender=self.name, method=method, answer=True, args=args, kwargs=kwargs)
        self.shared_qes[target].stream.put(q_data)
        try:
            return self.my_qes.payback.get(timeout=self.timeout)
        except TimeoutError:
            logging.error(f"frq_answer() 타임아웃:{self.name}의 요청 : {target}.{method}", exc_info=True)
            return None
        except Exception as e:
            logging.error(f"frq_answer() 오류:{self.name}의 요청 : {target}.{method} - {e}", exc_info=True)
            return None

class MainModel(BaseModel):
    """메인 쓰레드나 키움API 등을 위한 모델 (별도 쓰레드에서 run 실행)"""
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)
        self.thread = None
    
    def start(self):
        """별도 쓰레드에서 run() 실행"""
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        """쓰레드 정리"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)

class ThreadModel(BaseModel, threading.Thread):
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        threading.Thread.__init__(self)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)

class ProcessModel(BaseModel, Process):
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        Process.__init__(self, name=name)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)

# 테스트용 워커 (모든 기능 통합)
class TestWorker:
    def __init__(self):
        self.stream_count = 0
    
    def test_method(self, x, y=0):
        return x + y
    
    def handle_stream_data(self, data):
        self.stream_count += 1
        logging.debug(f"스트림 데이터 처리: {data}, 총 처리 횟수: {self.stream_count}")
        return f"처리완료-{data}"

if __name__ == "__main__":
    import multiprocessing as mp
    import time
    from public import init_logger
    mp.freeze_support()
    init_logger()
    # 모든 큐를 multiprocessing.Queue로 통일
    shared_qes = {
        'admin': SharedQueue(),
        'test': SharedQueue(),
        'main1': SharedQueue(),
        'main2': SharedQueue(),
        'thread1': SharedQueue(),
        'thread2': SharedQueue(),
        'proc1': SharedQueue()
    }

    logging.debug("--- 다양한 조합의 고빈도 스트림 테스트 ---")
    
    # 다양한 타입의 워커들 생성 (TestWorker로 통일)
    workers = {
        'main1': MainModel('main1', TestWorker, shared_qes),
        'main2': MainModel('main2', TestWorker, shared_qes), 
        'thread1': ThreadModel('thread1', TestWorker, shared_qes),
        'thread2': ThreadModel('thread2', TestWorker, shared_qes),
        'proc1': ProcessModel('proc1', TestWorker, shared_qes)
    }
    
    # 모든 워커 시작 (이제 MainModel도 동일하게 start()만 호출)
    for name, worker in workers.items():
        worker.start()
        logging.debug(f"{name} 시작됨")
    
    time.sleep(0.5)  # 모든 워커가 준비될 시간
    
    # 다양한 조합으로 고빈도 스트림 테스트
    test_combinations = [
        ('thread1', 'main1'),    # Thread → Main
        ('proc1', 'thread2'),    # Process → Thread  
        ('main2', 'proc1'),      # Main → Process
        ('thread2', 'thread1'),  # Thread → Thread
    ]
    
    def send_stream(sender_name, target_name, data_prefix):
        sender = workers[sender_name]
        for i in range(5):
            try:
                sender.frq_order(target_name, 'handle_stream_data', f"{data_prefix}-{i}")
                time.sleep(0.02)  # 50Hz 고빈도
            except Exception as e:
                logging.debug(f"{sender_name}→{target_name} 스트림 에러: {e}")
    
    # 동시에 여러 스트림 전송
    threads = []
    for sender, target in test_combinations:
        thread = threading.Thread(
            target=send_stream, 
            args=(sender, target, f"{sender}→{target}")
        )
        threads.append(thread)
        thread.start()
        logging.debug(f"스트림 시작: {sender} → {target}")
    
    # 모든 스트림 완료 대기
    for thread in threads:
        thread.join()
    
    time.sleep(1)  # 처리 완료 대기
    
    # 각 워커의 처리 통계 출력
    logging.debug("\n=== 처리 통계 ===")
    for name, worker in workers.items():
        if hasattr(worker, 'get_stats'):
            logging.debug(worker.get_stats())
    
    # 모든 워커 정리
    for worker in workers.values():
        worker.stop()
    
    logging.debug("--- 기존 테스트들 ---")
    main_worker = MainModel('admin', TestWorker, shared_qes)
    thread_worker = ThreadModel('test', TestWorker, shared_qes)
    
    main_worker.start()
    thread_worker.start()
    
    logging.debug("1. MainModel.order() 테스트 (응답 없음)")
    main_worker.order('test', 'test_method', 1, y=2)
    logging.debug("order 완료")
    
    logging.debug("2. MainModel.answer() 테스트 (응답 있음)")
    try:
        result = main_worker.answer('test', 'test_method', 7, y=8)
        logging.debug(f"answer 결과: {result}")
    except TimeoutError as e:
        logging.debug(f"answer 에러: {e}")
    
    logging.debug("3. MainModel.frq_order() 테스트 (스트림 명령)")
    main_worker.frq_order('test', 'test_method', 5, y=6)
    logging.debug("frq_order 완료")
    
    logging.debug("4. MainModel.frq_answer() 테스트 (스트림 응답)")
    try:
        result = main_worker.frq_answer('test', 'test_method', 10, y=5)
        logging.debug(f"frq_answer 결과: {result}")
    except TimeoutError as e:
        logging.debug(f"frq_answer 에러: {e}")
    
    thread_worker.stop()
    
    logging.debug("--- 기존 테스트들 ---")
    worker = ThreadModel('test', TestWorker, shared_qes)
    worker.start()
    
    logging.debug("--- MainModel 테스트 ---")
    main_worker = MainModel('admin', TestWorker, shared_qes)
    main_worker.start()
    
    # 메인에서 test로 요청 (test 워커가 실행 중이어야 함)
    try:
        result = main_worker.answer('test', 'test_method', 7, y=8)  # timeout=5초
        logging.debug(f"MainModel Result: {result}")
    except TimeoutError as e:
        logging.debug(f"MainModel Error: {e}")
    
    # 기존 방식
    shared_qes['test'].request.put(QData('admin', 'test_method', True, args=(1,), kwargs={'y': 2}))
    result = shared_qes['admin'].result.get(timeout=5)
    logging.debug(f"ThreadModel Result (기존): {result}")
    
    # 새로운 인터페이스 방식
    try:
        result = main_worker.answer('test', 'test_method', 5, y=3)  # timeout=3초
        logging.debug(f"ThreadModel Result (인터페이스): {result}")
    except TimeoutError as e:
        logging.debug(f"ThreadModel Error: {e}")
    
    worker.running = False
    worker.wait()

    logging.debug("--- ProcessModel 테스트 ---")
    proc_worker = ProcessModel('test', TestWorker, shared_qes)
    proc_worker.start()
    
    # 잠시 대기 (프로세스가 시작될 시간)
    time.sleep(0.1)
    
    # 새로운 인터페이스 방식
    try:
        result = main_worker.answer('test', 'test_method', 10, y=5)  # timeout=3초
        logging.debug(f"ProcessModel Result (인터페이스): {result}")
    except TimeoutError as e:
        logging.debug(f"ProcessModel Error: {e}")
    proc_worker.stop()
    time.sleep(0.1)

    # 강제 종료
    proc_worker.terminate()
    proc_worker.join(timeout=2)  # 2초 대기
    if proc_worker.is_alive():
        logging.debug("proc_worker 강제 종료")
        proc_worker.kill()

    workers['proc1'].terminate()
    workers['proc1'].join(timeout=2)  # 2초 대기
    if workers['proc1'].is_alive():
        logging.debug("proc1 강제 종료")
        workers['proc1'].kill()
