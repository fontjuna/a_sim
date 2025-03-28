from public import *
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, QMutex, QWaitCondition, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from queue import Empty, Queue
import sys
import threading
import copy
import multiprocessing as mp
from multiprocessing.connection import Listener, Client
import time
import logging
import uuid
import weakref
import traceback

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

class WorkModel():
    def __init__(self, name, cls=None):
        self.name = name
        self.cls = cls
        self.work_q = Queue()
        self.daemon = True
        self.is_running = True

        gm.qwork[self.name] = self.work_q

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

class WorkThread(WorkModel, QThread):
    def __init__(self, name, cls=None):
        WorkModel.__init__(self, name, cls)
        QThread.__init__(self)

    def run(self):
        WorkModel.run(self)

    def stop(self):
        WorkModel.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        QThread.start(self)
        return self

class AnswerModel:
    def __init__(self, name, cls=None, work_q=None, answer_q=None):
        self.name = name
        self.work_q = work_q if work_q is not None else Queue()
        self.answer_q = answer_q if answer_q is not None else Queue()
        self.cls = cls
        self.is_running = True

        gm.qwork[self.name] = self.work_q
        gm.qanswer[self.name] = self.answer_q

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
            if obj == None or not isinstance(data, (Work, Answer)):
                logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                return
            method = getattr(obj, data.order)
            if isinstance(data, Work):
                method(**data.job)
            else:
                logging.debug(f'{self.name} run_loop: executing {data.order}')
                result = method(**data.job)
                logging.debug(f'{self.name} run_loop: got result {result}')
                self.answer_q.put(result)

class AnswerThread(AnswerModel, QThread):
    def __init__(self, name, cls=None, work_q=None, answer_q=None):
        AnswerModel.__init__(self, name, cls, work_q, answer_q)
        QThread.__init__(self)

    def run(self):
        AnswerModel.run(self)

    def stop(self):
        AnswerModel.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        QThread.start(self)
        return self

class AnswerProcess(AnswerModel, mp.Process):
    def __init__(self, name, cls=None, work_q=None, answer_q=None):
        AnswerModel.__init__(self, name, cls, work_q, answer_q)
        mp.Process.__init__(self)

    def run(self):
        AnswerModel.run(self)

    def stop(self):
        AnswerModel.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        mp.Process.start(self)
        return self

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
        self.processes = {} # name -> process info
        self.process_connections = {} # name -> connection 

        self.address = ('localhost', 6000) # 기본주소
        self.authkey = b'worker_manager'
        self.listener = None
        self.connection_thread = None

        self.is_shutting_down = False

        # 프로세스 통신 리스너 시작
        self._start_listener()

    def _start_listener(self):
        """프로세스 간 통신을 위한 리스너 시작"""
        try:
            self.listener = Listener(self.address, authkey=self.authkey)
            self.connection_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.connection_thread.start()
        except Exception as e:
            logging.error(f"리스너 시작 오류: {e}")
    
    def _accept_connections(self):
        """프로세스 연결 수락 쓰레드"""
        while True:
            try:
                conn = self.listener.accept()
                # 프로세스 이름 수신
                msg = conn.recv()
                if isinstance(msg, dict) and 'register' in msg:
                    process_name = msg['register']
                    self.process_connections[process_name] = conn
                    
                    # 프로세스 상태 업데이트
                    if process_name in self.processes:
                        self.processes[process_name]['status'] = 'running'
                        
                    logging.info(f"프로세스 {process_name} 연결 완료")
                    
                    # 응답 처리 쓰레드 시작
                    thread = threading.Thread(
                        target=self._process_responses, 
                        args=(process_name, conn),
                        daemon=True
                    )
                    thread.start()
            except Exception as e:
                # 여기서는 연결 중 오류는 DEBUG 레벨로 낮춤
                logging.debug(f"연결 수락 오류: {e}")
                time.sleep(1)

    def _process_responses(self, process_name, connection):
        """프로세스 응답 처리 쓰레드"""
        while True:
            try:
                if not connection:
                    break
                    
                msg = connection.recv()
                if not msg:
                    continue
                    
                if 'result' in msg:
                    task_id = msg['task_id']
                    result = msg['result']
                    callback = self.processes.get(process_name, {}).get('callbacks', {}).pop(task_id, None)
                    if callback:
                        callback(result)
            except EOFError:
                logging.warning(f"프로세스 연결 종료: {process_name}")
                connection.close()
                break
            except Exception as e:
                if not self.is_shutting_down:   
                    logging.error(f"응답 처리 오류: {e}")
                time.sleep(0.1)
            
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
        elif worker_name in self.processes:
            process_info = self.processes[worker_name]
            process_info['status'] = 'stopping'
            logging.info(f"프로세스 {worker_name} 종료 중...")
            process = process_info.get('process')
            connection = self.process_connections.get(worker_name)
            
            if connection:
                try:
                    connection.send({'command': 'stop'})
                    connection.close()
                    self.process_connections.pop(worker_name, None)
                except:
                    pass
                
            if process and process.is_alive():
                process.terminate()
                process.join(1.0)
                if process.is_alive():
                    process.kill()  # 강제 종료
                    
            self.processes.pop(worker_name, None)
            logging.debug(f"워커 종료: {worker_name} (프로세스)")
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
        
        # 리스너 종료
        if self.listener:
            self.listener.close()
            self.listener = None
            
        logging.debug("모든 워커 종료")
        
    def _register_process(self, name, target_class):
        """프로세스 워커 등록"""
        # 프로세스 정보 저장
        self.processes[name] = {
            'callbacks': {},  # task_id -> callback
            'events': {},     # task_id -> event
            'results': {},     # task_id -> result
            'status': 'connecting'  # 프로세스 상태: connecting, running, stopping
        }
        logging.info(f"프로세스 {name} 연결 중...")
        # 프로세스 시작
        process = mp.Process(
            target=process_worker_main,
            args=(name, target_class, self.address, self.authkey),
            daemon=True
        )
        process.start()
        
        # 프로세스 정보 저장
        self.processes[name]['process'] = process
        logging.debug(f"프로세스 등록: {name} (PID: {process.pid})")
        return self
        
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

    def _process_call_sync(self, process_name, method_name, args, kwargs):
        """프로세스 동기식 호출"""
        process_info = self.processes.get(process_name)
        if not process_info:
            logging.error(f"프로세스 없음: {process_name}")
            return None
        
        # 프로세스 상태 확인
        status = process_info['status']
        if status == 'connecting':
            logging.error(f"프로세스 {process_name} 연결 대기 중...")
            return None
        elif status == 'stopping':
            logging.error(f"프로세스 {process_name} 종료 중...")
            return None
        
        # 연결 확인
        connection = self.process_connections.get(process_name)
        if not connection:
            if status == 'running':
                logging.error(f"프로세스 {process_name} 연결 끊김...")
            return None
            
        # 태스크 ID 생성
        task_id = str(uuid.uuid4())
        
        # 이벤트 생성
        event = threading.Event()
        result_container = [None]
        
        # 콜백 등록
        def callback(result):
            result_container[0] = result
            event.set()
            
        process_info['callbacks'][task_id] = callback
        
        # 명령 전송
        try:
            connection.send({
                'task_id': task_id,
                'method': method_name,
                'args': args,
                'kwargs': kwargs
            })
        except Exception as e:
            logging.error(f"프로세스 명령 전송 오류: {e}")
            process_info['callbacks'].pop(task_id, None)
            return None
            
        # 결과 대기
        if not event.wait(10.0):
            logging.warning(f"프로세스 호출 타임아웃: {process_name}.{method_name}")
            process_info['callbacks'].pop(task_id, None)
            return None
            
        return result_container[0]
        
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

    def _process_call_async(self, process_name, method_name, args, kwargs, callback):
        """프로세스 비동기식 호출"""
        if self.is_shutting_down:
            return None
        
        process_info = self.processes.get(process_name)
        if not process_info:
            logging.error(f"프로세스 없음: {process_name}")
            return False
            
        # 프로세스 상태 확인
        status = process_info.get('status')
        if status == 'connecting':
            #logging.debug(f"프로세스 {process_name} 연결 대기 중...")
            return False
        elif status == 'stopping':
            logging.debug(f"프로세스 {process_name} 종료 중...")
            return False
            
        # 연결 확인
        connection = self.process_connections.get(process_name)
        if not connection:
            if status == 'running':
                logging.error(f"프로세스 {process_name} 연결 끊김")
            return False
        
        # 태스크 ID 생성
        task_id = str(uuid.uuid4())
        
        # 콜백 등록 (있는 경우)
        if callback:
            process_info['callbacks'][task_id] = callback
            
        # 명령 전송
        try:
            connection.send({
                'task_id': task_id,
                'method': method_name,
                'args': args,
                'kwargs': kwargs
            })
            return True
        except Exception as e:
            logging.error(f"프로세스 명령 전송 오류: {e}")
            if callback:
                process_info['callbacks'].pop(task_id, None)
            return False

# 프로세스 워커 메인 함수
def process_worker_main(name, target_class, address, authkey):
    """프로세스 워커 메인 함수"""
    try:
        # 메인 프로세스에 연결
        connection = Client(address, authkey=authkey)
        
        # 등록 메시지 전송
        connection.send({'register': name})
        
        # 타겟 객체 생성
        target = target_class()
        
        # 명령 처리 루프
        while True:
            try:
                # 명령 수신
                msg = connection.recv()
                if not msg:
                    continue

                # 종료 명령 처리
                if msg.get('command') == 'stop':
                    logging.info(f"프로세스 {name} 종료 명령 수신")
                    break
                                        
                # 명령 파싱
                task_id = msg.get('task_id')
                method_name = msg.get('method')
                args = msg.get('args', ())
                kwargs = msg.get('kwargs', {})
                
                # 메서드 찾기
                method = getattr(target, method_name, None)
                if not method:
                    connection.send({
                        'task_id': task_id,
                        'result': None
                    })
                    continue
                    
                # 메서드 실행
                try:
                    result = method(*args, **kwargs)
                    connection.send({
                        'task_id': task_id,
                        'result': result
                    })
                except Exception as e:
                    logging.error(f"프로세스 {name} 메서드 실행 오류: {e}")
                    connection.send({
                        'task_id': task_id,
                        'result': None
                    })
            except EOFError:
                logging.warning(f"프로세스 {name} 연결 종료")
                break
            except Exception as e:
                logging.error(f"프로세스 {name} 명령 처리 오류: {e}")
    except Exception as e:
        logging.error(f"프로세스 {name} 시작 오류: {e}")
    finally:
        if hasattr(target, 'close') and callable(target.close):
            try:
                target.close()
            except:
                pass
        logging.info(f"프로세스 {name} 종료")

# 전역 관리자 인스턴스
la = WorkerManager()

class TableManager_old:
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
        with self.lock:
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
                self.data_dict = {}
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
        with self.lock:
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
            return key in self.data_dict
    
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
        with self.lock:
            if not self.data:
                table_widget.setRowCount(0)
                return
                
            data_copy = copy.deepcopy(self.data)
            columns = self.display_columns or self.all_columns
            resize_needed = self._resize
            
            if resize_needed:
                self._resize = False
        
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

class DataManager:
    def __init__(self, config):
        """쓰레드 안전한 데이터 관리 클래스 초기화"""
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        self.lock = threading.RLock()
        self.lock_timeout = 0.5  # 락 타임아웃 (초)
        
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
        """락 없이 테이블 위젯 업데이트 - 더 빠르지만 일시적 불일치 가능성 있음"""
        try:
            # 데이터 스냅샷 생성 (락 없이)
            data_snapshot = copy.deepcopy(self.data)
            columns = self.display_columns or self.all_columns
            
            if not data_snapshot:
                table_widget.setRowCount(0)
                return
                
            # 테이블 업데이트
            table_widget.setUpdatesEnabled(False)
            
            # 행/열 수 확인 및 조정
            if table_widget.rowCount() != len(data_snapshot) or table_widget.columnCount() != len(columns):
                table_widget.setRowCount(len(data_snapshot))
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
                resize_needed = True
            else:
                resize_needed = False
                
            # 데이터 표시 (예외 처리 추가)
            for row, item in enumerate(data_snapshot):
                for col, column in enumerate(columns):
                    try:
                        if column in item:
                            self._set_table_cell(table_widget, row, col, column, item[column])
                    except Exception as e:
                        # 셀 업데이트 중 오류 발생 - 무시하고 계속 진행
                        logging.debug(f"셀 업데이트 오류(무시됨): {e}")
                        
            # 필요시 크기 조정
            if resize_needed:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                if stretch:
                    table_widget.horizontalHeader().setStretchLastSection(stretch)
                    
        except Exception as e:
            logging.error(f'테이블 업데이트 오류: {e}', exc_info=True)
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

import threading
import traceback
import sys
import signal

# 모든 스레드의 스택 트레이스를 출력하는 함수
def print_thread_stacks(signum=None, frame=None):
    logging.debug("\n--- 스레드 스택 트레이스 ---")
    current_thread_id = threading.current_thread().ident
    
    for thread_id, frame in sys._current_frames().items():
        if thread_id == current_thread_id and signum is not None:
            continue  # 시그널 핸들러를 호출한 현재 스레드는 건너뜀
        
        stack = traceback.extract_stack(frame)
        logging.debug(f"\nThread {thread_id} (이름: {get_thread_name(thread_id)}):")
        for filename, lineno, name, line in stack:
            logging.debug(f'  파일 "{filename}", 라인 {lineno}, in {name}')
            if line:
                logging.debug(f'    {line.strip()}')

# 스레드 ID로 스레드 이름 가져오기
def get_thread_name(thread_id):
    for thread in threading.enumerate():
        if thread.ident == thread_id:
            return thread.name
    return "Unknown"

# 주기적으로 스레드 스택 출력 (예: 30초마다)
def start_thread_monitoring(interval=30):
    def monitor():
        while True:
            time.sleep(interval)
            print_thread_stacks()
    
    monitor_thread = threading.Thread(target=monitor, name="ThreadMonitor")
    monitor_thread.daemon = True
    monitor_thread.start()

