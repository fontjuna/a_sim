from public import dc, gm, get_path, save_json, load_json, QData
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal    
from multiprocessing import Process
from PyQt5.QtCore import QThread
import multiprocessing
import pythoncom
import queue
import threading
import copy
import time
import logging
import os

class ThreadSafeList:
    def __init__(self, name='thread_safe_list'):
        self.name = name
        self.list = []
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock) # self.lock으로 wait, notify 를 관리

    def put(self, item):
        with self.lock:
            self.list.append(item)
            self.not_empty.notify() # 대기중인 스레드에게 알림

    def get(self):
        with self.lock:
            if self.empty():
                self.not_empty.wait() # 대기
            return self.list.pop(0)

    def length(self):
        with self.lock:
            return len(self.list)

    def clear(self):
        with self.lock:
            self.list.clear()

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
        self.lock = threading.RLock()

    def set(self, key, value=None, sub_key=None):
        """단일 값 설정"""
        with self.lock:
            if sub_key is None:
                self.dict[key] = copy.deepcopy(value) if value is not None else {}
            else:
                if key not in self.dict:
                    self.dict[key] = {}
                self.dict[key][sub_key] = copy.deepcopy(value) if value is not None else {}

    def get(self, key, sub_key=None):
        """단일 값 조회"""
        with self.lock:
            if sub_key is None:
                value = self.dict.get(key)
                return copy.deepcopy(value) if value is not None else None
            else:
                if key not in self.dict:
                    return None
                value = self.dict[key].get(sub_key)
                return copy.deepcopy(value) if value is not None else None

    def contains(self, key, sub_key=None):
        """키 존재 여부 확인"""
        with self.lock:
            if sub_key is None:
                return key in self.dict
            else:
                return key in self.dict and sub_key in self.dict[key]

    def remove(self, key, sub_key=None):
        """항목 제거"""
        with self.lock:
            if sub_key is None:
                return copy.deepcopy(self.dict.pop(key, None))
            elif key in self.dict:
                return copy.deepcopy(self.dict[key].pop(sub_key, None))
            return None

    def update_if_exists(self, key, sub_key, value):
        """
        존재하는 경우에만 업데이트
        1. 단일 항목 업데이트 (기존 방식)
        thread_safe_dict.update_if_exists("user_001", "age", 31)

        2. 여러 항목 업데이트 (새로운 방식)
        thread_safe_dict.update_if_exists("user_001", {"age": 31, "email": "new@email.com"})

        3. 전체 값 업데이트
        thread_safe_dict.update_if_exists("user_001", None, {"name": "홍길동", "age": 30})
        """
        with self.lock:
            if key in self.dict:
                if sub_key is None:
                    self.dict[key] = copy.deepcopy(value) if value is not None else {}
                    return True
                elif isinstance(sub_key, dict):
                    # 여러 항목 업데이트
                    updated_count = 0
                    for k, v in sub_key.items():
                        if k in self.dict[key]:
                            self.dict[key][k] = copy.deepcopy(v) if v is not None else {}
                            updated_count += 1
                    return updated_count > 0
                else:
                    # 단일 항목 업데이트
                    if sub_key in self.dict[key]:
                        self.dict[key][sub_key] = copy.deepcopy(value) if value is not None else {}
                        return True
            return False

    def items(self):
        with self.lock:
            return list(self.dict.items())

    def keys(self):
        with self.lock:
            return list(self.dict.keys())

    def values(self):
        with self.lock:
            return list(self.dict.values())

    def clear(self):
        """전체 사전 초기화"""
        with self.lock:
            self.dict.clear()

class ThreadSafeSet:
    """쓰레드 안전한 set 클래스"""
    def __init__(self):
        self._set = set()
        self._lock = threading.Lock()
    
    def add(self, item):
        with self._lock:
            self._set.add(item)
    
    def discard(self, item):
        with self._lock:
            self._set.discard(item)
    
    def list(self):
        with self._lock:
            return list(self._set)
    
    def clear(self):
        with self._lock:
            self._set.clear()

    def __contains__(self, item):
        with self._lock:
            return item in self._set

class ThreadSafeQueue:
    def __init__(self, name='thread_safe_queue'):
        self.name = name
        self.q = queue.Queue()
        self.lock = threading.Lock()

    def put(self, item):
        self.q.put(item)

    def get(self, block=True, timeout=None):
        return self.q.get(block=block, timeout=timeout)

    def length(self):
        return self.q.qsize()

    def clear(self):
        with self.lock:
            while not self.q.empty():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break

    def remove(self, item):
        # queue.Queue는 중간 삭제가 불가하므로, 임시 큐로 재구성
        with self.lock:
            temp = queue.Queue()
            removed = False
            while not self.q.empty():
                obj = self.q.get()
                if not removed and obj == item:
                    removed = True
                    continue
                temp.put(obj)
            self.q = temp

    def contains(self, item):
        with self.lock:
            items = list(self.q.queue)
            return item in items

    def empty(self):
        return self.q.empty()

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
    DEFAULT_NAME = ""
    DEFAULT_GROUP_LIMIT = 1000   # 그룹 전체 매수 한도 (저장만 함)
    DEFAULT_TICKER_LIMIT = 10    # 개별 종목 매수 한도 (저장만 함)
    DEFAULT_MAX_RATE = 30.0     # 개별 종목 최대 손실율(%) 한도 (저장만 함)
    DEFAULT_MAX_TIMES = 10     # 개별 종목 최대 손실 횟수 한도 (저장만 함)
    DEFAULT_DATA = { "date": dc.ToDay, "name": DEFAULT_NAME, "group": DEFAULT_GROUP_LIMIT, "count": 0, "ticker": DEFAULT_TICKER_LIMIT, "max_rate": DEFAULT_MAX_RATE, "max_times": DEFAULT_MAX_TIMES, "data": {} }
   
    def __init__(self, file_name="counter_data.json"):
        data_path = get_path('db')
        self.file_path = os.path.join(data_path, file_name)
        self.lock = threading.RLock()
        self.name = self.DEFAULT_NAME
        self.group = self.DEFAULT_GROUP_LIMIT
        self.ticker = self.DEFAULT_TICKER_LIMIT
        self.max_rate = self.DEFAULT_MAX_RATE
        self.max_times = self.DEFAULT_MAX_TIMES
        self.count = 0
        self.data = {}
        self.load_data()
    
    def load_data(self):
        with self.lock:
            success, loaded = load_json(self.file_path, self.DEFAULT_DATA)
            if not success:
                return
            saved_date = loaded.get("date", "")
            self.name = loaded.get("name", self.DEFAULT_NAME)
            self.group = loaded.get("group", self.DEFAULT_GROUP_LIMIT)
            self.ticker = loaded.get("ticker", self.DEFAULT_TICKER_LIMIT)
            self.max_rate = loaded.get("max_rate", self.DEFAULT_MAX_RATE)
            self.max_times = loaded.get("max_times", self.DEFAULT_MAX_TIMES)
            # 날짜가 바뀌면 하루 단위 초기화: data={}, count=0 유지 규칙
            if saved_date != dc.ToDay:
                self.count = 0
                self.data = {}
            else:
                self.count = int(loaded.get("count", 0) or 0)
                self.data = loaded.get("data", {}) or {}
    
    def save_data(self):
        with self.lock:
            save_obj = { "date": dc.ToDay, "name": self.name, "group": self.group, "count": self.count, "ticker": self.ticker, "max_rate": self.max_rate, "max_times": self.max_times, "data": self.data }
            success, _ = save_json(self.file_path, save_obj)
            return success
    
    def set_strategy(self, name, group=None, ticker=None, max_rate=None, max_times=None):
        with self.lock:
            updated = False
            if name is not None and self.name != name:
                self.name = name
                updated = True
            if group is not None and self.group != group:
                self.group = int(group)
                updated = True
            if ticker is not None and self.ticker != ticker:
                self.ticker = int(ticker)
                updated = True
            if max_rate is not None and self.max_rate != max_rate:
                self.max_rate = float(max_rate)
                updated = True
            if max_times is not None and self.max_times != max_times:
                self.max_times = int(max_times)
                updated = True
            if updated:
                self.save_data()
    
    def ensure_ticker(self, code, name=None):
        if code not in self.data:
            if name is None or name == "":
                try:
                    name = gm.prx.answer('api', 'GetMasterCodeName', code)
                except Exception:
                    name = code
            self.data[code] = { "name": name, "rate": 0.0, "times": 0, "count": 0 }
    
    def register_tickers(self, code_to_name: dict):
        with self.lock:
            for code, name in code_to_name.items():
                self.ensure_ticker(code, name)
            self.save_data()

    def record_buy(self, code, name=None):
        with self.lock:
            self.ensure_ticker(code, name)
            self.data[code]["count"] = int(self.data[code].get("count", 0) or 0) + 1
            self.count = int(self.count or 0) + 1
            self.save_data()

    def record_loss(self, code, loss_rate, name=None):
        with self.lock:
            self.ensure_ticker(code, name)
            rate = float(abs(loss_rate) if loss_rate is not None else 0.0)
            current = float(self.data[code].get("rate", 0.0) or 0.0)
            self.data[code]["rate"] = max(current, rate)
            self.data[code]["times"] = int(self.data[code].get("times", 0) or 0) + 1
            self.save_data()

    def update_loss_rate(self, code, loss_rate, name=None):
        with self.lock:
            self.ensure_ticker(code, name)
            rate = float(abs(loss_rate) if loss_rate is not None else 0.0)
            current = float(self.data[code].get("rate", 0.0) or 0.0)
            if rate > current:
                self.data[code]["rate"] = rate
                self.save_data()

    def increment_loss_times(self, code, inc=1, name=None):
        with self.lock:
            self.ensure_ticker(code, name)
            self.data[code]["times"] = int(self.data[code].get("times", 0) or 0) + int(inc)
            self.save_data()

    def get_group_count(self) -> int:
        with self.lock:
            return int(self.count or 0)

    def get_ticker_count(self, code) -> int:
        with self.lock:
            if code not in self.data:
                return 0
            return int(self.data[code].get("count", 0) or 0)

    def can_buy_group(self, limit: int) -> bool:
        with self.lock:
            return int(self.count or 0) < int(limit)

    def can_buy_ticker(self, code: str, limit: int) -> bool:
        with self.lock:
            self.ensure_ticker(code)
            return int(self.data[code].get("count", 0) or 0) < int(limit)

    def can_buy_loss_rate(self, code: str, max_rate=None) -> bool:
        with self.lock:
            self.ensure_ticker(code)
            limit = float(self.max_rate if max_rate is None else max_rate)
            current = float(self.data[code].get("rate", 0.0) or 0.0)
            return current < limit

    def can_buy_loss_times(self, code: str, max_times=None) -> bool:
        with self.lock:
            self.ensure_ticker(code)
            limit = int(self.max_times if max_times is None else max_times)
            current = int(self.data[code].get("times", 0) or 0)
            return current < limit

    def can_buy_ticker_with_constraints(self, code: str, ticker_limit: int, max_rate=None, max_times=None) -> bool:
        with self.lock:
            return self.can_buy_ticker(code, ticker_limit) and self.can_buy_loss_rate(code, max_rate) and self.can_buy_loss_times(code, max_times)

class TimeLimiter:
    def __init__(self, name, second=5, minute=100, hour=1000):
        self.name = name
        self.SEC = second
        self.MIN = minute
        self.HOUR = hour
        self.request_times = []  # 요청 시간 기록 (밀리초)
        self.condition_times = {}  # 조건별 마지막 실행 시간
        self.lock = threading.RLock()

    def _cleanup_old_requests(self, current_time):
        """1시간 이상 된 기록 정리 (락 내부에서 호출)"""
        cutoff = current_time - 3600000
        self.request_times = [t for t in self.request_times if t > cutoff]

    def _count_requests_in_period(self, current_time, period_ms):
        """특정 기간 내 요청 수 계산 (락 내부에서 호출)"""
        cutoff = current_time - period_ms
        return sum(1 for t in self.request_times if t > cutoff)

    def _get_oldest_time_in_period(self, current_time, period_ms):
        """특정 기간 내 가장 오래된 요청 시간 반환"""
        cutoff = current_time - period_ms
        times_in_period = [t for t in self.request_times if t > cutoff]
        return min(times_in_period) if times_in_period else current_time
        
    def check_interval(self) -> int:
        current_time = time.time() * 1000
        
        with self.lock:
            self._cleanup_old_requests(current_time)
            
            recent_1s = self._count_requests_in_period(current_time, 1000)
            recent_1m = self._count_requests_in_period(current_time, 60000)
            recent_60m = self._count_requests_in_period(current_time, 3600000)
            
            # 1초 구간: 4회까지 대기 0, 5회째는 남은 시간 대기
            if recent_1s < self.SEC - 1:
                return 0
            elif recent_1s == self.SEC - 1:
                oldest_1s = self._get_oldest_time_in_period(current_time, 1000)
                return max(0, int(oldest_1s + 1000 - current_time))
            
            # 1분 구간: 0.2초 ~ 1초 누진 (5~99회)
            if recent_1m < self.MIN:
                ratio = (recent_1m - self.SEC) / (self.MIN - self.SEC - 1)
                return int(200 + ratio * 800)
            
            # 1시간 구간: 1초 ~ 6초 누진 (100~999회)
            if recent_60m < self.HOUR:
                ratio = (recent_60m - self.MIN) / (self.HOUR - self.MIN - 1)
                return int(1000 + ratio * 5000)
            
            # 제한 도달: 가장 오래된 요청 빠질 때까지 대기
            oldest_60m = self._get_oldest_time_in_period(current_time, 3600000)
            return min(6000, max(0, int(oldest_60m + 3600000 - current_time)))
                    
    def check_condition_interval(self, condition) -> int:
        current_time = time.time() * 1000
        
        with self.lock:
            last_time = self.condition_times.get(condition, 0)
        
        if current_time - last_time >= 60000:
            with self.lock:
                if condition in self.condition_times:
                    del self.condition_times[condition]
            return 0
        
        return max(0, int(60000 - (current_time - last_time)))

    def update_request_times(self):
        current_time = time.time() * 1000
        with self.lock:
            self.request_times.append(current_time)

    def update_condition_time(self, condition):
        current_time = time.time() * 1000
        with self.lock:
            self.condition_times[condition] = current_time
            self.request_times.append(current_time)

'''
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
'''

import shutil
import os

def get_windows_drive_free_percent():
    """
    현재 스크립트가 실행 중인 드라이브(C:\ 등)의 잔여 공간 비율(%)을 반환합니다.
    Windows 전용입니다.
    """
    # 현재 작업 디렉터리의 드라이브 문자 추출 (예: 'C:')
    drive = os.path.splitdrive(os.getcwd())[0] + '\\'

    total, used, free = shutil.disk_usage(drive)
    percent_free = (free / total) * 100
    return percent_free

class BaseModel:
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        self.name = name
        self.cls = cls
        self.shared_qes = shared_qes
        self.args = args
        self.kwargs = kwargs
        self.instance = None
        self.my_qes = shared_qes[name]
        self.running = False
        self.answer_timeout = 15
        self.queue_timeout = dc.INTERVAL_FAST
        self.pending_requests = {}  # 대기 중인 요청들 관리
        
        # 프로세스/스레드 환경 자동 감지
        if isinstance(self, Process):
            self.pending_lock = multiprocessing.Lock()
            self.is_process = True
        else:
            self.pending_lock = threading.RLock()
            self.is_process = False

    def process_q_data(self, q_data):
        if not isinstance(q_data, QData):
            return None
        if q_data.method == 'stop':
            self.stop()
        if hasattr(self.instance, q_data.method):
            if q_data.answer:
                result = getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
                # 디버깅: 결과 크기 확인
                # result_size = len(result) if isinstance(result, (list, dict)) else 'N/A'
                # logging.debug(f'[{self.name}] 응답 준비: {q_data.method} -> {q_data.sender}, result 크기={result_size}, request_id={q_data.request_id}')
                # 응답에 request_id 포함하여 전송
                response_data = QData(
                    sender=self.name,
                    method='_handle_response',
                    answer=False,
                    args=(q_data.request_id, result),
                    request_id=q_data.request_id
                )
                self.shared_qes[q_data.sender].put_request(response_data)
                # logging.debug(f'[{self.name}] 응답 전송 완료: {q_data.method} -> {q_data.sender}')
            else:
                result = getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
                if q_data.callback:
                    callback_data = QData(
                        sender=self.name, 
                        method=q_data.callback, 
                        answer=False, 
                        args=(result,)
                    )
                    self.shared_qes[q_data.sender].put_request(callback_data)

    def _handle_response(self, request_id, result):
        """응답 처리 전용 메서드"""
        # result_size = len(result) if isinstance(result, (list, dict)) else 'N/A'
        # logging.debug(f'[{self.name}] 응답 수신: request_id={request_id}, result 크기={result_size}')
        with self.pending_lock:
            if request_id in self.pending_requests:
                self.pending_requests[request_id] = result
            #     logging.debug(f'[{self.name}] 응답 저장 완료: request_id={request_id}')
            # else:
            #     logging.warning(f'[{self.name}] 응답 버림 (request_id 없음): request_id={request_id}')

    def _wait_for_response(self, request_id, wait):
        """응답 대기 (폴링 최소화)"""
        start_time = time.time()
        while time.time() - start_time < wait:
            with self.pending_lock:
                result = self.pending_requests.get(request_id)
                if result is not None:
                    return result
            time.sleep(0.001)  # 1ms 대기
        return None

    def _initialize_instance(self):
        """인스턴스 초기화 공통 로직"""
        if hasattr(self.kwargs, 'timeout'):
            self.answer_timeout = self.kwargs.get('timeout')
        self.instance = self.cls(*self.args, **self.kwargs)
        self.instance.order = self.order
        self.instance.answer = self.answer
        if hasattr(self.instance, 'initialize'):
            self.instance.initialize()

    def _process_queues(self):
        """큐 처리 공통 로직 - _handle_response 처리 추가"""
        if not self.my_qes.request.empty():
            q_data = self.my_qes.request.get()

            # 응답 처리 전용 메서드인 경우 직접 처리
            if q_data.method == '_handle_response':
                self._handle_response(*q_data.args)
            else:
                self.process_q_data(q_data)
        else:
            time.sleep(self.queue_timeout)

        if hasattr(self.instance, 'run_main_work'):
            self.instance.run_main_work()

    def _run_loop_iteration(self):
        """각 모델별 특수 처리를 위한 메서드 (오버라이드 가능)"""
        pass

    def _common_run_logic(self):
        """공통 run 로직"""
        self.running = True
        self._initialize_instance()
        
        while self.running:
            try:
                self._process_queues()      # 큐 처리 및 각 컴포넌트의 루프 처리(run_main_work)
                self._run_loop_iteration()
            except (EOFError, ConnectionError, BrokenPipeError):
                break
            except Exception as e:
                logging.debug(f"{self.name}: run() 에러 - {e}", exc_info=True)
                pass

        if hasattr(self.instance, 'cleanup'):
            self.instance.cleanup()

    def run(self):
        self._common_run_logic()

    def stop(self):
        self.running = False

    def order(self, target, method, *args, **kwargs):
        """응답이 필요없는 명령 (answer=False)"""
        callback = kwargs.pop('callback', None)
        q_data = QData(sender=self.name, method=method, answer=False, args=args, kwargs=kwargs, callback=callback)
        self.shared_qes[target].put_request(q_data)

    def answer(self, target, method, *args, **kwargs):
        """응답이 필요한 요청 (answer=True) - 프로세스/스레드 통합 안전 보장"""
        wait = kwargs.pop('wait', self.answer_timeout)
        q_data = QData(sender=self.name, method=method, answer=True, args=args, kwargs=kwargs) # request_id 는 디폴트에의해 자동 생성

        # 디버깅
        #logging.debug(f'[{self.name}] 요청 전송: {self.name} -> {target}.{method}, request_id={q_data.request_id}, wait={wait}초')

        # 요청 ID로 응답 매칭
        with self.pending_lock:
            self.pending_requests[q_data.request_id] = None

        try:
            # 요청 전송
            self.shared_qes[target].put_request(q_data)

            # 응답 대기
            result = self._wait_for_response(q_data.request_id, wait)
            if result is None:
                logging.warning(f'[{self.name}] 응답 타임아웃: {self.name} -> {target}.{method}, wait={wait}초')
            return result
            
        except Exception as e:
            logging.error(f"answer() 오류:{self.name}의 요청 : {target}.{method} - {e}", exc_info=True)
            return None
        finally:
            # 응답 정리
            with self.pending_lock:
                self.pending_requests.pop(q_data.request_id, None)

class MainModel(BaseModel):
    """메인 쓰레드나 키움API 등을 위한 모델 (별도 쓰레드에서 run 실행)"""
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)
        self.thread = None
    
    def start(self):
        """별도 쓰레드에서 run() 실행"""
        if self.thread and self.thread.is_alive(): return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        """쓰레드 정리"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)

class QMainModel(BaseModel, QThread):
    receive_signal = pyqtSignal(object)
    
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        QThread.__init__(self)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)
        self.emit_q = queue.Queue()
        self.queue_timeout = dc.INTERVAL_FAST  # QMainModel은 빠른 반응성 필요

    def _initialize_instance(self):
        """QMainModel 전용 인스턴스 초기화"""
        super()._initialize_instance()
        self.instance.emit_q = self.emit_q

    def _run_loop_iteration(self):
        """QMainModel 전용 emit_q 처리"""
        if not self.emit_q.empty():
            data = self.emit_q.get()
            self.receive_signal.emit(data)
        
    def stop(self):
        self.running = False

class ThreadModel(BaseModel, threading.Thread):
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        threading.Thread.__init__(self)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)

    def stop(self):
        self.running = False

class ProcessModel(BaseModel, Process):
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        Process.__init__(self, name=name)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)

    def stop(self):
        self.running = False

class KiwoomModel(BaseModel, Process):
    def __init__(self, name, cls, shared_qes, *args, **kwargs):
        Process.__init__(self, name=name)
        BaseModel.__init__(self, name, cls, shared_qes, *args, **kwargs)
        self.queue_timeout = dc.INTERVAL_FAST  # 실시간 데이터 처리 위해 빠르게

    def _run_loop_iteration(self):
        """Kiwoom 전용 ActiveX 이벤트 처리"""
        if self.running:
            pythoncom.PumpWaitingMessages()

    def run(self):
        try:
            self._common_run_logic()
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception as e:
                logging.error(f"KiwoomModel stop() 오류: {e}", exc_info=True)

    def stop(self):
        self.running = False



