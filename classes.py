from public import dc, gm, get_path, save_json, load_json, QData, SharedQueue
from dataclasses import dataclass, field
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal    
from multiprocessing import Process
from multiprocessing.queues import Empty
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
            if next is None:
                value = self.dict.get(key)
                return copy.deepcopy(value) if value is not None else None
            else:
                if key not in self.dict:
                    return None
                value = self.dict[key].get(next)
                return copy.deepcopy(value) if value is not None else None

    def contains(self, item):
        with self.lock:
            return item in self.dict

    def remove(self, key, next=None):
        with self.lock:
            if next is None:
                return copy.deepcopy(self.dict.pop(key, None))
            elif key in self.dict:
                return copy.deepcopy(self.dict[key].pop(next, None))
            return None
            
    def items(self):
        with self.lock:
            return list(self.dict.items())  # 복사본 반환

    def keys(self):
        with self.lock:
            return list(self.dict.keys())  # 복사본 반환

    def values(self):
        with self.lock:
            return list(self.dict.values())  # 복사본 반환

    def update_if_exists(self, key, next, value):
        """존재하는 경우에만 업데이트 (contains + set을 원자적으로 수행)"""
        with self.lock:
            if key in self.dict:
                if next is None:
                    self.dict[key] = copy.deepcopy(value) if value is not None else {}
                    return True
                else:
                    self.dict[key][next] = copy.deepcopy(value) if value is not None else {}
                    return True
            return False

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
    DEFAULT_DATA = { "date": dc.ToDay, "data": {} } # data = { code: { name: "", limit: 0, count: 0 }, ... } 
   
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
                if saved_date != dc.ToDay: self.data = {}
    
    def save_data(self):
        with self.lock:
            save_obj = { "date": dc.ToDay, "data": self.data }
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

    def set(self, code, name, limit=0, count=0):
        with self.lock:
            self.data[code] = { "name": name, "limit": limit, "count": count }
            self.save_data()

    def set_add(self, code):
        try:
            with self.lock:
                self.data[code]["count"] += 1
                self.data["000000"]["count"] += 1
                self.save_data()
        except KeyError:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            self.set(code, name, 0, 1)
        except Exception as e:
            logging.error(f"CounterTicker set_add 오류: {code} {e}", exc_info=True)
    
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
    callback : str = None

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
        self.instance = None #self.cls(*self.args, **self.kwargs)
        self.my_qes = shared_qes[name]
        self.running = False
        self.timeout = 15
        
    def process_q_data(self, q_data, queue_type='request'):
        if not isinstance(q_data, QData): return None
        if q_data.method == 'stop': self.stop()
        if hasattr(self.instance, q_data.method):
            if q_data.answer:
                result = getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
                if queue_type == 'request':
                    self.shared_qes[q_data.sender].result.put(result)
                elif queue_type == 'stream':
                    self.shared_qes[q_data.sender].payback.put(result)
            else:
                result = getattr(self.instance, q_data.method)(*q_data.args, **q_data.kwargs)
                if q_data.callback:
                    callback_data = QData(sender=self.name, method=q_data.callback, answer=False, args=(result,))
                    if queue_type == 'request':
                        self.shared_qes[q_data.sender].request.put(callback_data)
                    elif queue_type == 'stream':
                        self.shared_qes[q_data.sender].stream.put(callback_data)

    def _initialize_instance(self):
        """인스턴스 초기화 공통 로직"""
        if hasattr(self.kwargs, 'timeout'):
            self.timeout = self.kwargs.get('timeout')
        self.instance = self.cls(*self.args, **self.kwargs)
        self.instance.order = self.order
        self.instance.answer = self.answer
        self.instance.frq_order = self.frq_order
        self.instance.frq_answer = self.frq_answer
        if hasattr(self.instance, 'initialize'):
            self.instance.initialize()

    def _process_queues(self):
        """큐 처리 공통 로직"""
        # 어떤 곳에서든 올 수 있는 request 처리
        if not self.my_qes.request.empty():
            q_data = self.my_qes.request.get()
            self.process_q_data(q_data, 'request')
            
        # 어떤 곳에서든 올 수 있는 stream 처리 (고빈도 가능)
        if not self.shared_qes[self.name].stream.empty():
            q_data = self.shared_qes[self.name].stream.get()
            self.process_q_data(q_data, 'stream')
            
        if hasattr(self.instance, 'run_main_work'):
            self.instance.run_main_work()

    def _run_loop_iteration(self):
        """각 모델별 특수 처리를 위한 메서드 (오버라이드 가능)"""
        pass

    def _sleep(self):
        """각 모델별 sleep 구현 (오버라이드 가능)"""
        time.sleep(dc.INTERVAL_NORMAL)

    def _common_run_logic(self):
        """공통 run 로직"""
        self.running = True
        self._initialize_instance()
        
        while self.running:
            try:
                self._process_queues()
                self._run_loop_iteration()  # 각 모델별 특수 처리
                self._sleep()
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
        q_data = QData(sender=self.name, method=method, answer=False, args=args, kwargs=kwargs)
        self.shared_qes[target].request.put(q_data)

    def answer(self, target, method, *args, **kwargs):
        """응답이 필요한 요청 (answer=True)"""
        q_data = QData(sender=self.name, method=method, answer=True, args=args, kwargs=kwargs)
        self.shared_qes[target].request.put(q_data)
        try:
            return self.my_qes.result.get(timeout=self.timeout)
        except Empty:
            pass
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
        except Empty:
            pass
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
        self.emit_q = queue.Queue()  # (signal, args) 형태로 사용

    def _initialize_instance(self):
        """QMainModel 전용 인스턴스 초기화"""
        super()._initialize_instance()
        self.instance.emit_q = self.emit_q

    def _run_loop_iteration(self):
        """QMainModel 전용 emit_q 처리"""
        while not self.emit_q.empty():
            data = self.emit_q.get()
            self.receive_signal.emit(data)

    def _sleep(self):
        """QThread용 sleep"""
        QThread.msleep(5) # 0.005 seconds

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