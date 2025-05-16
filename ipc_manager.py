# ipc_manager.py
import multiprocessing as mp
from multiprocessing import Manager, Process, Queue, shared_memory
import threading
import queue
import logging
import time
import pickle
import uuid
import sys
import traceback
import numpy as np
from typing import Dict, Any, Callable, Union, Optional, Tuple, List
from PyQt5.QtCore import QMetaObject, Qt

class SharedMemoryManager:
    """공유 메모리를 관리하는 클래스"""
    
    def __init__(self):
        self._shared_memories = {}
        self._shared_buffers = {}
        self._locks = {}
        self.timeout_0 = 0
        self.timeout_1 = 5
        self.timeout_2 = 10
        self._lock = threading.RLock()
    
    def create_shared_memory(self, name: str, data: Any, timeout: int = None) -> bool:
        """공유 메모리 생성"""
        try:
            with self._lock:
                # 직렬화
                try:
                    data_bytes = pickle.dumps(data)
                except Exception as e:
                    logging.error(f"직렬화 실패: {name} - {str(e)}")
                    return False
                
                # 메모리 할당
                shm = shared_memory.SharedMemory(
                    name=name, create=True, size=len(data_bytes)
                )
                # 데이터 복사
                shm.buf[:len(data_bytes)] = data_bytes
                self._shared_memories[name] = shm
                self._locks[name] = threading.RLock()
                return True
        except Exception as e:
            logging.error(f"공유 메모리 생성 실패: {name}", exc_info=True)
            return False
    
    def update_shared_memory(self, name: str, data: Any, timeout: int = None) -> bool:
        """공유 메모리 업데이트"""
        try:
            with self._lock:
                if name not in self._shared_memories:
                    return self.create_shared_memory(name, data, timeout)
                
                with self._locks[name]:
                    # 직렬화
                    try:
                        data_bytes = pickle.dumps(data)
                    except Exception as e:
                        logging.error(f"직렬화 실패: {name} - {str(e)}")
                        return False
                        
                    shm = self._shared_memories[name]
                    
                    # 새 데이터가 더 크면 새로운 공유 메모리 생성
                    if len(data_bytes) > shm.size:
                        shm.close()
                        try:
                            shm.unlink()
                        except:
                            pass
                        shm = shared_memory.SharedMemory(
                            name=name, create=True, size=len(data_bytes)
                        )
                        self._shared_memories[name] = shm
                    
                    # 데이터 복사
                    shm.buf[:len(data_bytes)] = data_bytes
                    return True
        except Exception as e:
            logging.error(f"공유 메모리 업데이트 실패: {name}", exc_info=True)
            return False
    
    def get_shared_memory(self, name: str, timeout: int = None) -> Any:
        """공유 메모리에서 데이터 가져오기"""
        try:
            # 타임아웃 설정
            if timeout == 0:
                actual_timeout = self.timeout_0
            elif timeout == 1:
                actual_timeout = self.timeout_1
            elif timeout == 2:
                actual_timeout = self.timeout_2
            else:
                actual_timeout = self.timeout_1
            
            # 시도 횟수 계산
            max_tries = 3
            retry_delay = actual_timeout / max_tries
            
            for attempt in range(max_tries):
                try:
                    if name in self._shared_memories:
                        with self._locks[name]:
                            shm = self._shared_memories[name]
                            data_bytes = bytes(shm.buf[:shm.size])
                            # 실제 데이터 길이 확인 (패딩 제거)
                            try:
                                # pickle 데이터 끝 찾기
                                return pickle.loads(data_bytes)
                            except:
                                # 부분 로드 실패, 더 기다려야 함
                                pass
                    else:
                        # 다른 프로세스에서 생성한 공유 메모리 접근
                        try:
                            shm = shared_memory.SharedMemory(name=name, create=False)
                            self._shared_memories[name] = shm
                            self._locks[name] = threading.RLock()
                            data_bytes = bytes(shm.buf[:shm.size])
                            return pickle.loads(data_bytes)
                        except:
                            pass
                    
                    if attempt < max_tries - 1:
                        time.sleep(retry_delay)
                
                except Exception as inner_e:
                    if attempt < max_tries - 1:
                        time.sleep(retry_delay)
                    else:
                        raise inner_e
            
            raise TimeoutError(f"공유 메모리 접근 타임아웃: {name}")
        
        except Exception as e:
            logging.error(f"공유 메모리 접근 실패: {name}", exc_info=True)
            return None
    
    def delete_shared_memory(self, name: str) -> bool:
        """공유 메모리 삭제"""
        try:
            with self._lock:
                if name in self._shared_memories:
                    shm = self._shared_memories[name]
                    shm.close()
                    try:
                        shm.unlink()
                    except:
                        pass  # 이미 언링크 됐을 수 있음
                    del self._shared_memories[name]
                    del self._locks[name]
                return True
        except Exception as e:
            logging.error(f"공유 메모리 삭제 실패: {name}", exc_info=True)
            return False
    
    def cleanup(self):
        """모든 공유 메모리 정리"""
        with self._lock:
            for name, shm in list(self._shared_memories.items()):
                try:
                    shm.close()
                    try:
                        shm.unlink()
                    except:
                        pass
                except:
                    pass
            self._shared_memories.clear()
            self._locks.clear()

from PyQt5.QtCore import QThread, QTimer, QObject, pyqtSignal, pyqtSlot

class QtThreadWorker(QThread):
    """Qt 기반 스레드 작업자 클래스"""
    
    result_ready = pyqtSignal(tuple)  # 결과 준비 시그널
    
    def __init__(self, cls_name, obj, task_queue, result_queue):
        super().__init__()
        self.cls_name = cls_name
        self.obj = obj
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.running = False
        
        # 결과 시그널 연결
        self.result_ready.connect(self.send_result)
    
    # QThread에서는 isRunning() 메서드를 사용
    def is_alive(self):
        """스레드가 살아있는지 확인 (threading.Thread와 호환)"""
        return self.isRunning()
    
    def stop(self):
        """스레드 종료"""
        # 실행 플래그 해제
        self.running = False
        
        # 타이머 중지 (같은 스레드에서 수행)
        if hasattr(self, 'timer') and self.timer.isActive():
            # 메인 스레드에서 호출된 경우 시그널을 통해 타이머 중지
            if QThread.currentThread() != self:
                QMetaObject.invokeMethod(self, "stop_timer", Qt.QueuedConnection)
            else:
                self.stop_timer()
        
        # 스레드 종료 요청
        self.quit()
        
        # 스레드가 즉시 종료되지 않으면 종료될 때까지 대기
        if not self.wait(5000):  # 5초 타임아웃
            # 여전히 실행 중이면 강제 종료
            self.terminate()
    
    @pyqtSlot()
    def stop_timer(self):
        """타이머 중지 (스레드 내에서 호출)"""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()

    def run(self):
        """스레드 실행"""
        self.running = True
        logging.info(f"Qt Thread Worker '{self.cls_name}' 시작")
        
        # 공유 메모리 관리자 초기화
        shm_mgr = SharedMemoryManager()
        
        # 작업 확인용 타이머 설정
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_tasks)
        self.timer.start(10)  # 10ms마다 확인
        
        # Qt 이벤트 루프 실행
        self.exec_()
        
        # 종료 정리
        if self.timer.isActive():
            self.timer.stop()
        logging.info(f"Qt Thread Worker '{self.cls_name}' 종료")
    
    @pyqtSlot()
    def check_tasks(self):
        """작업 확인"""
        try:
            # 큐가 비어있지 않은지 확인
            if not self.task_queue.empty():
                try:
                    # 작업 가져오기
                    task = self.task_queue.get_nowait()
                    
                    if task is None:  # 종료 신호
                        self.running = False
                        self.quit()
                        return
                    
                    # 작업 실행
                    self.process_task(task)
                    
                except queue.Empty:
                    pass
        except Exception as e:
            logging.error(f"Qt Thread Worker '{self.cls_name}' 작업 확인 오류", exc_info=True)
    
    def process_task(self, task):
        """작업 처리"""
        task_id, method_name, args, kwargs, has_callback = task
        
        # 콜백 분리
        callback_info = None
        if has_callback and 'callback' in kwargs:
            callback_info = kwargs.pop('callback')
        
        result = None
        error = None
        
        try:
            # 메서드 찾기
            method = getattr(self.obj, method_name)
            
            # 메서드 호출
            result = method(*args, **kwargs)
            
        except Exception as e:
            error = {
                'type': type(e).__name__,
                'message': str(e),
                'traceback': traceback.format_exc()
            }
            logging.error(f"Qt Thread '{self.cls_name}' 메서드 '{method_name}' 실행 오류", 
                        exc_info=True)
        
        # 결과 또는 에러 반환
        if callback_info:
            # 콜백 정보가 있으면 콜백을 호출
            callback_cls, callback_method = callback_info
            callback_data = {
                'task_id': task_id,
                'result': result,
                'error': error,
                'source': {
                    'cls_name': self.cls_name,
                    'method_name': method_name
                },
                'execution_mode': 'thread'
            }
            # 시그널을 통해 결과 전송
            self.result_ready.emit((task_id, callback_cls, callback_method, callback_data))
        else:
            # 시그널을 통해 결과 전송
            self.result_ready.emit((task_id, result, error, self.cls_name, method_name, 'thread'))
    
    @pyqtSlot(tuple)
    def send_result(self, result_data):
        """결과 전송"""
        try:
            # 명확한 로깅 추가
            if isinstance(result_data, tuple) and len(result_data) >= 3:
                task_id = result_data[0]
                logging.info(f"[DEBUG] 결과 전송: {self.cls_name}, task_id={task_id}")
            
            # 결과 큐에 추가
            self.result_queue.put(result_data)
        except Exception as e:
            logging.error(f"결과 전송 오류: {e}", exc_info=True)

class ThreadWorker(threading.Thread):
    """스레드 작업자 클래스"""
    
    def __init__(self, cls_name, obj, task_queue, result_queue):
        super().__init__(name=cls_name)
        self.cls_name = cls_name
        self.obj = obj
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.running = False
        self.daemon = True
    
    def run(self):
        """스레드 실행"""
        self.running = True
        logging.info(f"Thread Worker '{self.cls_name}' 시작")
        
        # 공유 메모리 관리자 초기화
        shm_mgr = SharedMemoryManager()
        
        while self.running:
            try:
                try:
                    # 요청 대기 (1초 타임아웃)
                    task = self.task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                if task is None:  # 종료 신호
                    self.running = False
                    break
                
                # 작업 실행
                task_id, method_name, args, kwargs, has_callback = task
                
                # 콜백 분리
                callback_info = None
                if has_callback and 'callback' in kwargs:
                    callback_info = kwargs.pop('callback')
                
                result = None
                error = None
                
                try:
                    # 메서드 찾기
                    method = getattr(self.obj, method_name)
                    
                    # 여기서 get_shm과 set_shm 메서드를 IPC 기능으로 연결
                    if method_name == 'get_shm':
                        result = shm_mgr.get_shared_memory(*args, **kwargs)
                    elif method_name == 'set_shm':
                        var_name, value = args[0], args[1]
                        result = shm_mgr.update_shared_memory(var_name, value, 
                                                            kwargs.get('timeout', None))
                    else:
                        # 일반 메서드 호출
                        result = method(*args, **kwargs)
                    
                except Exception as e:
                    error = {
                        'type': type(e).__name__,
                        'message': str(e),
                        'traceback': traceback.format_exc()
                    }
                    logging.error(f"Thread '{self.cls_name}' 메서드 '{method_name}' 실행 오류", 
                                exc_info=True)
                
                # 결과 또는 에러 반환
                if callback_info:
                    # 콜백 정보가 있으면 콜백을 호출
                    callback_cls, callback_method = callback_info
                    callback_data = {
                        'task_id': task_id,
                        'result': result,
                        'error': error,
                        'source': {
                            'cls_name': self.cls_name,
                            'method_name': method_name
                        },
                        'execution_mode': 'thread'
                    }
                    # 콜백 요청 큐에 전송
                    self.result_queue.put((task_id, callback_cls, callback_method, callback_data))
                else:
                    # 결과 큐에 전송
                    self.result_queue.put((task_id, result, error, self.cls_name, method_name, 'thread'))
            
            except Exception as e:
                logging.error(f"Thread Worker '{self.cls_name}' 오류", exc_info=True)
        
        # 종료 정리
        logging.info(f"Thread Worker '{self.cls_name}' 종료")

class MessageHandler:
    """메인 프로세스에서 프로세스 간 메시지 처리를 담당하는 클래스"""
    
    def __init__(self, manager, object_registry):
        self.manager = manager
        self.object_registry = object_registry
        self.shm_manager = SharedMemoryManager()
        self.handlers = {}
        self._register_handlers()
    
    def _register_handlers(self):
        """메시지 핸들러 등록"""
        self.handlers['method_call'] = self._handle_method_call
        self.handlers['get_shm'] = self._handle_get_shm
        self.handlers['set_shm'] = self._handle_set_shm
    
    def handle_message(self, message):
        """메시지 처리"""
        message_type = message.get('type')
        if message_type in self.handlers:
            return self.handlers[message_type](message)
        else:
            logging.error(f"알 수 없는 메시지 유형: {message_type}")
            return {
                'error': f"알 수 없는 메시지 유형: {message_type}"
            }
    
    def _handle_method_call(self, message):
        """메서드 호출 처리"""
        cls_name = message.get('cls_name')
        method_name = message.get('method_name')
        args = message.get('args', [])
        kwargs = message.get('kwargs', {})
        task_id = message.get('task_id')
        
        obj = self.object_registry.get(cls_name)
        if obj is None:
            return {
                'task_id': task_id,
                'error': f"객체를 찾을 수 없음: {cls_name}",
                'result': None,
                'source': {'cls_name': cls_name, 'method_name': method_name},
                'execution_mode': 'main'
            }
        
        try:
            # 메서드 찾기
            method = getattr(obj, method_name, None)
            if method is None:
                return {
                    'task_id': task_id,
                    'error': f"메서드를 찾을 수 없음: {cls_name}.{method_name}",
                    'result': None,
                    'source': {'cls_name': cls_name, 'method_name': method_name},
                    'execution_mode': 'main'
                }
            
            # 메서드 호출
            result = method(*args, **kwargs)
            
            return {
                'task_id': task_id,
                'result': result,
                'error': None,
                'source': {'cls_name': cls_name, 'method_name': method_name},
                'execution_mode': 'main'
            }
            
        except Exception as e:
            return {
                'task_id': task_id,
                'error': {
                    'type': type(e).__name__,
                    'message': str(e),
                    'traceback': traceback.format_exc()
                },
                'result': None,
                'source': {'cls_name': cls_name, 'method_name': method_name},
                'execution_mode': 'main'
            }
    
    def _handle_get_shm(self, message):
        """공유 메모리 가져오기 처리"""
        var_name = message.get('var_name')
        timeout = message.get('timeout')
        task_id = message.get('task_id')
        
        try:
            result = self.shm_manager.get_shared_memory(var_name, timeout)
            return {
                'task_id': task_id,
                'result': result,
                'error': None,
                'source': {'cls_name': 'SharedMemoryManager', 'method_name': 'get_shared_memory'},
                'execution_mode': 'main'
            }
        except Exception as e:
            return {
                'task_id': task_id,
                'error': {
                    'type': type(e).__name__,
                    'message': str(e),
                    'traceback': traceback.format_exc()
                },
                'result': None,
                'source': {'cls_name': 'SharedMemoryManager', 'method_name': 'get_shared_memory'},
                'execution_mode': 'main'
            }
    
    def _handle_set_shm(self, message):
        """공유 메모리 설정 처리"""
        var_name = message.get('var_name')
        value = message.get('value')
        timeout = message.get('timeout')
        task_id = message.get('task_id')
        
        try:
            result = self.shm_manager.update_shared_memory(var_name, value, timeout)
            return {
                'task_id': task_id,
                'result': result,
                'error': None,
                'source': {'cls_name': 'SharedMemoryManager', 'method_name': 'update_shared_memory'},
                'execution_mode': 'main'
            }
        except Exception as e:
            return {
                'task_id': task_id,
                'error': {
                    'type': type(e).__name__,
                    'message': str(e),
                    'traceback': traceback.format_exc()
                },
                'result': None,
                'source': {'cls_name': 'SharedMemoryManager', 'method_name': 'update_shared_memory'},
                'execution_mode': 'main'
            }

class MainProcessProxy:
    """메인 프로세스에서 실행되는 객체를 위한 프록시"""
    
    def __init__(self, cls_name, message_queue, result_queue):
        self.cls_name = cls_name
        self.message_queue = message_queue
        self.result_queue = result_queue
        self._pending_results = {}
        self._result_lock = threading.RLock()
        
        # 결과 처리 스레드
        self._running = True
        self._result_thread = threading.Thread(target=self._process_results, daemon=True)
        self._result_thread.start()
    
    def __getattr__(self, name):
        """동적 메서드 호출"""
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' 객체에 '{name}' 속성이 없습니다.")
        
        def proxy_method(*args, **kwargs):
            """프록시 메서드"""
            # 비동기/동기 여부 확인
            is_async = False
            callback = None
            
            if 'callback' in kwargs:
                is_async = True
                callback = kwargs.pop('callback')
            
            # 작업 ID 생성
            task_id = str(uuid.uuid4())
            
            # 메시지 생성
            if name == 'get_shm':
                message = {
                    'type': 'get_shm',
                    'var_name': args[0] if args else kwargs.get('var_name'),
                    'timeout': kwargs.get('timeout'),
                    'task_id': task_id
                }
            elif name == 'set_shm':
                message = {
                    'type': 'set_shm',
                    'var_name': args[0] if len(args) > 0 else kwargs.get('var_name'),
                    'value': args[1] if len(args) > 1 else kwargs.get('value'),
                    'timeout': kwargs.get('timeout'),
                    'task_id': task_id
                }
            else:
                message = {
                    'type': 'method_call',
                    'cls_name': self.cls_name,
                    'method_name': name,
                    'args': args,
                    'kwargs': kwargs,
                    'task_id': task_id
                }
            
            if is_async:
                # 비동기 호출
                # 콜백 정보 추가
                message['callback'] = callback
                # 메시지 전송
                self.message_queue.put(message)
                return True
            else:
                # 동기 호출
                # 결과 대기 이벤트 생성
                with self._result_lock:
                    result_event = threading.Event()
                    self._pending_results[task_id] = {
                        'event': result_event,
                        'result': None,
                        'error': None
                    }
                
                # 메시지 전송
                self.message_queue.put(message)
                
                # 결과 대기
                if result_event.wait(timeout=5):  # 5초 타임아웃
                    with self._result_lock:
                        result_data = self._pending_results.pop(task_id, {})
                    
                    result = result_data.get('result')
                    error = result_data.get('error')
                    
                    if error:
                        logging.error(f"메서드 실행 오류: {self.cls_name}.{name} - {error}")
                        return None
                    else:
                        return result
                else:
                    # 타임아웃
                    with self._result_lock:
                        self._pending_results.pop(task_id, None)
                    logging.error(f"메서드 실행 타임아웃: {self.cls_name}.{name}")
                    return None
        
        return proxy_method
    
    def _process_results(self):
        """결과 처리 스레드"""
        while self._running:
            try:
                try:
                    # 결과 대기
                    result_data = self.result_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # 결과 처리
                task_id = result_data.get('task_id')
                
                with self._result_lock:
                    if task_id in self._pending_results:
                        self._pending_results[task_id]['result'] = result_data.get('result')
                        self._pending_results[task_id]['error'] = result_data.get('error')
                        self._pending_results[task_id]['event'].set()
            
            except Exception as e:
                logging.error(f"결과 처리 오류: {e}", exc_info=True)
        
        logging.info(f"결과 처리 스레드 종료: {self.cls_name}")
    
    def cleanup(self):
        """자원 정리"""
        self._running = False
        if self._result_thread.is_alive():
            self._result_thread.join(5)

def process_worker_func(cls_name, task_queue, result_queue):
    """프로세스 작업자 함수"""
    try:
        logging.info(f"Process Worker '{cls_name}' 시작")
        
        # 메시지 핸들러 생성
        message_handler = MessageHandler(None, {})
        
        # 공유 메모리 관리자 초기화
        shm_mgr = SharedMemoryManager()
        
        running = True
        while running:
            try:
                try:
                    # 요청 대기 (1초 타임아웃)
                    message = task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                if message is None:  # 종료 신호
                    running = False
                    break
                
                # 메시지 처리
                response = message_handler.handle_message(message)
                
                # 응답 전송
                response['execution_mode'] = 'process'
                result_queue.put(response)
            
            except Exception as e:
                logging.error(f"Process Worker '{cls_name}' 오류", exc_info=True)
        
        # 종료 정리
        logging.info(f"Process Worker '{cls_name}' 종료")
        shm_mgr.cleanup()
        
    except Exception as e:
        logging.error(f"Process Worker '{cls_name}' 초기화 오류", exc_info=True)

class IPCManager:
    """IPC(Inter-Process Communication) 관리자"""
    
    def __init__(self):
        # 프로세스 간 통신을 위한 매니저
        self.mp_manager = mp.Manager()

        # 요청 수신 플래그
        self.accept_requests = True
        
        # 객체 저장소
        self.workers = {}  # 워커 객체
        self.objects = {}  # 메인 프로세스 객체
        self.proxies = {}  # 프록시 객체
        
        # 큐 저장소
        self.task_queues = {}
        self.result_queues = {}
        
        # 타입 저장소 (process, thread, None)
        self.worker_types = {}
        
        # 결과 대기
        self.pending_results = {}
        
        # 공유 메모리 관리자
        self.shm_manager = SharedMemoryManager()
        
        # 메시지 핸들러
        self.message_handler = MessageHandler(self, self.objects)
        
        # 결과 처리 스레드
        self.result_thread = threading.Thread(target=self._process_results, daemon=True)
        self.result_thread_running = False
        
        # 메시지 처리 스레드
        self.message_thread = threading.Thread(target=self._process_messages, daemon=True)
        self.message_thread_running = False
        
        # 메시지 큐
        self.message_queue = queue.Queue()
        self.main_result_queue = queue.Queue()
        
        # 시작
        self._start_threads()
        
        logging.info("IPCManager 초기화 완료")
    
    def register(self, cls_name: str, obj: Any, start: bool = False, type: str = None) -> Any:
        """객체 등록"""
        try:
            if cls_name in self.workers or cls_name in self.objects or cls_name in self.proxies:
                logging.warning(f"'{cls_name}'이(가) 이미 등록되어 있습니다.")
                return obj
            
            ipc_manager = self
            def obj_work(target_cls, target_method, *args, **kwargs):
                return ipc_manager.work(target_cls, target_method, *args, **kwargs)
            
            def obj_answer(target_cls, target_method, *args, **kwargs):
                return ipc_manager.answer(target_cls, target_method, *args, **kwargs)
            
            # 메서드 추가 (기존 메서드가 있으면 덮어쓰지 않음)
            if not hasattr(obj, 'work') or obj.work is None:
                obj.work = obj_work
                
            if not hasattr(obj, 'answer') or obj.answer is None:
                obj.answer = obj_answer
                        
            # 타입 저장
            self.worker_types[cls_name] = type
            
            if type == 'process':
                # 직렬화 가능 여부 확인
                is_picklable = self._check_picklable(obj)
                
                if is_picklable:
                    # 프로세스에서 메시지 큐 사용
                    task_queue = self.mp_manager.Queue()
                    result_queue = self.mp_manager.Queue()
                    
                    # 객체 등록
                    self.objects[cls_name] = obj
                    
                    # 프로세스 시작
                    worker = mp.Process(
                        target=process_worker_func,
                        args=(cls_name, task_queue, result_queue),
                        name=cls_name,
                        daemon=True
                    )
                    
                    self.workers[cls_name] = worker
                    self.task_queues[cls_name] = task_queue
                    self.result_queues[cls_name] = result_queue
                    
                    if start:
                        try:
                            worker.start()
                        except Exception as e:
                            logging.error(f"프로세스 시작 실패: {cls_name}", exc_info=True)
                            # 실패 시 메인 프로세스 프록시로 전환
                            del self.workers[cls_name]
                            self._create_main_proxy(cls_name, obj)
                else:
                    # 직렬화 불가능한 경우 메인 프로세스 프록시 사용
                    logging.warning(f"'{cls_name}' 객체는 직렬화가 불가능하여 메인 프로세스에서 실행됩니다.")
                    self._create_main_proxy(cls_name, obj)
                
            elif type in ('thread', 'qthread'):
                # 스레드로 실행
                task_queue = queue.Queue()
                result_queue = queue.Queue()
                
                worker = ThreadWorker(cls_name, obj, task_queue, result_queue) if type == 'thread' else QtThreadWorker(cls_name, obj, task_queue, result_queue)
                
                self.workers[cls_name] = worker
                self.task_queues[cls_name] = task_queue
                self.result_queues[cls_name] = result_queue
                
                if start:
                    worker.start()
                
            else:
                # 메인 스레드에서 실행 (별도 워커 없음)
                self.objects[cls_name] = obj
            
            return obj
            
        except Exception as e:
            logging.error(f"객체 등록 실패: {cls_name}", exc_info=True)
            # 실패 시 메인 스레드에서 실행
            self.objects[cls_name] = obj
            self.worker_types[cls_name] = None
            return obj
    
    def _check_picklable(self, obj):
        """객체가 직렬화 가능한지 확인"""
        try:
            pickle.dumps(obj)
            return True
        except:
            return False
    
    def _create_main_proxy(self, cls_name, obj):
        """메인 프로세스 프록시 생성"""
        # 객체 저장
        self.objects[cls_name] = obj
        
        # 프록시 생성
        proxy = MainProcessProxy(cls_name, self.message_queue, self.main_result_queue)
        self.proxies[cls_name] = proxy
        
        # 타입 변경
        self.worker_types[cls_name] = 'main_proxy'
    
    def unregister(self, cls_name: str) -> str:
        """객체 등록 해제"""
        try:
            if (cls_name not in self.workers and cls_name not in self.objects 
                    and cls_name not in self.proxies):
                logging.warning(f"'{cls_name}'이(가) 등록되어 있지 않습니다.")
                return cls_name
            
            if cls_name in self.workers:
                worker_type = self.worker_types.get(cls_name)
                
                # 워커 정지
                if worker_type in ('process', 'thread'):
                    self.stop(cls_name)
                
                # 큐 정리
                if cls_name in self.task_queues:
                    del self.task_queues[cls_name]
                
                if cls_name in self.result_queues:
                    del self.result_queues[cls_name]
                
                # 워커 삭제
                del self.workers[cls_name]
                
            elif cls_name in self.proxies:
                # 프록시 정리
                proxy = self.proxies.pop(cls_name)
                proxy.cleanup()
                
                # 객체 삭제
                if cls_name in self.objects:
                    del self.objects[cls_name]
            
            elif cls_name in self.objects:
                # 객체 삭제
                del self.objects[cls_name]
            
            if cls_name in self.worker_types:
                del self.worker_types[cls_name]
            
            return cls_name
            
        except Exception as e:
            logging.error(f"객체 등록 해제 실패: {cls_name}", exc_info=True)
            return cls_name
    
    def start(self, cls_name: str) -> bool:
        """워커 시작"""
        self.accept_requests = True
        try:
            if cls_name not in self.workers and cls_name not in self.proxies:
                logging.warning(f"'{cls_name}'이(가) 등록되어 있지 않습니다.")
                return False
            
            if cls_name in self.workers:
                worker = self.workers[cls_name]
                
                if not worker.is_alive():
                    worker.start()
            
            return True
            
        except Exception as e:
            logging.error(f"워커 시작 실패: {cls_name}", exc_info=True)
            return False
        
    def stop(self, cls_name: str) -> bool:
        """워커 정지"""
        # 요청 수신 비활성화
        self.accept_requests = False
        
        try:
            if cls_name not in self.workers and cls_name not in self.proxies:
                logging.warning(f"'{cls_name}'이(가) 등록되어 있지 않습니다.")
                return False
            
            if cls_name in self.workers:
                worker = self.workers[cls_name]
                
                # Qt 스레드와 일반 스레드를 구분하여 처리
                is_qt_thread = isinstance(worker, QThread)
                
                # 실행 중인지 확인
                is_running = False
                if is_qt_thread:
                    is_running = worker.isRunning()
                elif hasattr(worker, 'is_alive'):
                    is_running = worker.is_alive()
                
                # 실행 중이 아니면 무시
                if not is_running:
                    logging.info(f"'{cls_name}'이(가) 이미 정지되었습니다.")
                    return True
                
                # 실행 플래그 해제
                if hasattr(worker, 'running'):
                    worker.running = False
                
                # Qt 스레드는 별도의 방식으로 종료
                if is_qt_thread:
                    if hasattr(worker, 'stop') and callable(worker.stop):
                        worker.stop()
                    else:
                        # 종료 시그널 전송 후 대기
                        worker.quit()
                        if not worker.wait(5000):  # 5초 타임아웃
                            worker.terminate()
                else:
                    # 일반 스레드/프로세스 종료
                    task_queue = self.task_queues.get(cls_name)
                    if task_queue:
                        try:
                            task_queue.put(None)
                        except:
                            pass
                    
                    # 종료 대기
                    worker.join(5)
                    
                    # 프로세스면 강제 종료 추가
                    if worker.is_alive() and isinstance(worker, Process):
                        try:
                            worker.terminate()
                        except:
                            pass
                
                logging.info(f"'{cls_name}' 워커가 정지되었습니다.")
            
            return True
            
        except Exception as e:
            logging.error(f"워커 정지 실패: {cls_name}", exc_info=True)
            return False
    
    def work(self, cls_name: str, method_name: str, *args, callback=None, **kwargs) -> bool:
        """비동기 작업 요청 (결과를 기다리지 않음)"""
        if not self.accept_requests: return False
        try:
            # 작업 ID 생성
            task_id = str(uuid.uuid4())
            
            # 콜백 정보 추출
            has_callback = callback is not None
            if has_callback:
                kwargs['callback'] = callback
            
            # 대상 확인
            if cls_name in self.objects:
                # 메인 프로세스 객체
                obj = self.objects[cls_name]
                
                try:
                    # 직접 메서드 호출
                    method = getattr(obj, method_name)
                    
                    if method_name == 'get_shm':
                        result = self.shm_manager.get_shared_memory(*args, **kwargs)
                    elif method_name == 'set_shm':
                        var_name, value = args[0], args[1]
                        result = self.shm_manager.update_shared_memory(
                            var_name, value, kwargs.get('timeout', None)
                        )
                    else:
                        # 콜백이 있는 경우
                        if has_callback:
                            cb = kwargs.pop('callback')
                            # 스레드에서 메서드 실행
                            threading.Thread(
                                target=self._run_with_callback,
                                args=(obj, method_name, args, kwargs, cb, cls_name),
                                daemon=True
                            ).start()
                            return True
                        else:
                            # 동기 실행
                            result = method(*args, **kwargs)
                    
                    return True
                    
                except Exception as e:
                    logging.error(
                        f"메서드 실행 실패: {cls_name}.{method_name}", exc_info=True
                    )
                    return False
            
            elif cls_name in self.workers:
                # 워커 프로세스/스레드
                task_queue = self.task_queues.get(cls_name)
                if task_queue:
                    task = (task_id, method_name, args, kwargs, has_callback)
                    try:
                        task_queue.put(task)
                        return True
                    except Exception as e:
                        logging.error(f"작업 전송 실패: {cls_name}.{method_name}", exc_info=True)
                        return False
                else:
                    logging.error(f"'{cls_name}'의 작업 큐를 찾을 수 없습니다.")
                    return False
            
            elif cls_name in self.proxies:
                # 메인 프로세스 프록시
                proxy = self.proxies[cls_name]
                
                try:
                    # 프록시 메서드 호출
                    proxy_method = getattr(proxy, method_name)
                    result = proxy_method(*args, **kwargs)
                    return True
                except Exception as e:
                    logging.error(f"프록시 메서드 실행 실패: {cls_name}.{method_name}", exc_info=True)
                    return False
            
            else:
                logging.error(f"'{cls_name}'을(를) 찾을 수 없습니다.")
                return False
                
        except Exception as e:
            logging.error(f"작업 요청 실패: {cls_name}.{method_name}", exc_info=True)
            return False
    
    def answer(self, cls_name: str, method_name: str, *args, timeout=None, **kwargs) -> Any:
        """동기 작업 요청 (결과를 기다림)"""
        if not self.accept_requests: return None
        try:
            # 타임아웃 설정
            if timeout == 0:
                actual_timeout = self.shm_manager.timeout_0
            elif timeout == 1:
                actual_timeout = self.shm_manager.timeout_1
            elif timeout == 2:
                actual_timeout = self.shm_manager.timeout_2
            else:
                actual_timeout = self.shm_manager.timeout_2
            
            # 대상 확인
            if cls_name in self.objects:
                # 메인 프로세스 객체
                obj = self.objects[cls_name]
                
                try:
                    # 직접 메서드 호출
                    method = getattr(obj, method_name)
                    
                    if method_name == 'get_shm':
                        return self.shm_manager.get_shared_memory(*args, **kwargs)
                    elif method_name == 'set_shm':
                        var_name, value = args[0], args[1]
                        return self.shm_manager.update_shared_memory(
                            var_name, value, kwargs.get('timeout', None)
                        )
                    else:
                        return method(*args, **kwargs)
                    
                except Exception as e:
                    logging.error(
                        f"메서드 실행 실패: {cls_name}.{method_name}", exc_info=True
                    )
                    return None
            
            elif cls_name in self.workers:
                # 워커 프로세스/스레드
                # 작업 ID 생성
                task_id = str(uuid.uuid4())
                
                # 결과 대기 동기화 객체 생성
                result_event = threading.Event()
                self.pending_results[task_id] = {
                    'event': result_event,
                    'result': None,
                    'error': None
                }
                
                # 작업 전송
                task_queue = self.task_queues.get(cls_name)
                if task_queue:
                    task = (task_id, method_name, args, kwargs, False)
                    try:
                        task_queue.put(task)
                        
                        # 결과 대기
                        if result_event.wait(timeout=actual_timeout):
                            # 결과 가져오기
                            result_data = self.pending_results.pop(task_id, {})
                            result = result_data.get('result')
                            error = result_data.get('error')
                            
                            if error:
                                # 에러 로깅
                                logging.error(
                                    f"원격 실행 오류: {cls_name}.{method_name} - {error}"
                                )
                                return None
                            else:
                                return result
                        else:
                            # 타임아웃
                            self.pending_results.pop(task_id, None)
                            logging.error( f"실행 타임아웃: {cls_name}.{method_name} ({actual_timeout}초)" )
                            return None
                    except Exception as e:
                        logging.error(f"작업 전송 실패: {cls_name}.{method_name}", exc_info=True)
                        self.pending_results.pop(task_id, None)
                        return None
                else:
                    logging.error(f"'{cls_name}'의 작업 큐를 찾을 수 없습니다.")
                    return None
            
            elif cls_name in self.proxies:
                # 메인 프로세스 프록시
                proxy = self.proxies[cls_name]
                
                try:
                    # 프록시 메서드 호출
                    proxy_method = getattr(proxy, method_name)
                    return proxy_method(*args, **kwargs)
                except Exception as e:
                    logging.error(f"프록시 메서드 실행 실패: {cls_name}.{method_name}", exc_info=True)
                    return None
            
            else:
                logging.error(f"'{cls_name}'을(를) 찾을 수 없습니다.")
                return None
                
        except Exception as e:
            logging.error(f"작업 요청 실패: {cls_name}.{method_name}", exc_info=True)
            return None
    
    def _start_threads(self):
        """스레드 시작"""
        if not self.result_thread_running:
            self.result_thread_running = True
            self.result_thread.start()
        
        if not self.message_thread_running:
            self.message_thread_running = True
            self.message_thread.start()
    
    def _process_results(self):
        """결과 처리 스레드 함수"""
        while self.result_thread_running:
            try:
                # 모든 결과 큐에서 결과 확인
                for cls_name, result_queue in list(self.result_queues.items()):
                    try:
                        # 비차단 방식으로 결과 확인
                        try:
                            # 큐에서 결과 가져오기 시도
                            if hasattr(result_queue, 'get_nowait'):
                                result_data = result_queue.get_nowait()
                            else:
                                # mp.Queue는 Empty 예외로 처리
                                result_data = result_queue.get(block=False)
                            
                            # 결과 형식에 따라 처리
                            if isinstance(result_data, tuple) and len(result_data) >= 3:
                                # 콜백 요청인 경우
                                if len(result_data) == 4:
                                    task_id, callback_cls, callback_method, callback_data = result_data
                                    self._handle_callback(callback_cls, callback_method, callback_data)
                                # 일반 결과인 경우
                                else:
                                    task_id, result, error = result_data[:3]
                                    source_cls = cls_name
                                    source_method = "unknown"
                                    mode = "unknown"
                                    
                                    if len(result_data) > 3:
                                        source_cls = result_data[3]
                                    if len(result_data) > 4:
                                        source_method = result_data[4]
                                    if len(result_data) > 5:
                                        mode = result_data[5]
                                    
                                    self._handle_result(task_id, result, error)
                            # 딕셔너리 형식의 결과인 경우
                            elif isinstance(result_data, dict):
                                task_id = result_data.get('task_id')
                                result = result_data.get('result')
                                error = result_data.get('error')
                                
                                if 'callback' in result_data:
                                    # 콜백 데이터가 있는 경우
                                    callback_cls, callback_method = result_data['callback']
                                    self._handle_callback(callback_cls, callback_method, result_data)
                                else:
                                    # 일반 결과인 경우
                                    self._handle_result(task_id, result, error)
                        
                        except (queue.Empty, Exception) as qe:
                            # 큐가 비어 있음 또는 기타 큐 관련 예외
                            pass
                        
                    except Exception as e:
                        logging.error(f"결과 처리 중 오류: {cls_name}", exc_info=True)
                
                # 메인 프로세스 프록시 결과 처리
                try:
                    result_data = self.main_result_queue.get_nowait()
                    
                    if isinstance(result_data, dict):
                        task_id = result_data.get('task_id')
                        result = result_data.get('result')
                        error = result_data.get('error')
                        
                        if 'callback' in result_data:
                            # 콜백 데이터가 있는 경우
                            callback_cls, callback_method = result_data['callback']
                            self._handle_callback(callback_cls, callback_method, result_data)
                        else:
                            # 일반 결과인 경우
                            self._handle_result(task_id, result, error)
                except queue.Empty:
                    pass
                except Exception as e:
                    logging.error("메인 프로세스 프록시 결과 처리 오류", exc_info=True)
                
                # 잠시 대기
                time.sleep(0.001)  # 1ms 대기 (CPU 사용 최소화)
                
            except Exception as e:
                logging.error("결과 처리 스레드 오류", exc_info=True)
        
        logging.info("결과 처리 스레드 종료")
    
    def _process_messages(self):
        """메시지 처리 스레드 함수"""
        while self.message_thread_running:
            try:
                try:
                    # 메시지 대기
                    message = self.message_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # 메시지 처리
                response = self.message_handler.handle_message(message)
                
                # 콜백 처리
                if 'callback' in message:
                    callback_cls, callback_method = message['callback']
                    response['callback'] = (callback_cls, callback_method)
                    self._handle_callback(callback_cls, callback_method, response)
                else:
                    # 결과 큐에 전송
                    self.main_result_queue.put(response)
            
            except Exception as e:
                logging.error("메시지 처리 스레드 오류", exc_info=True)
        
        logging.info("메시지 처리 스레드 종료")
    
    def _handle_result(self, task_id, result, error):
        """결과 처리"""
        if task_id in self.pending_results:
            # 결과 저장
            self.pending_results[task_id]['result'] = result
            self.pending_results[task_id]['error'] = error
            # 이벤트 설정
            self.pending_results[task_id]['event'].set()
    
    def _handle_callback(self, callback_cls, callback_method, callback_data):
        """콜백 처리"""
        try:
            # 콜백 클래스 찾기
            if callback_cls in self.objects:
                obj = self.objects[callback_cls]
                
                # 콜백 메서드 찾기
                method = getattr(obj, callback_method, None)
                if method:
                    # 콜백 호출
                    method(callback_data)
                else:
                    logging.error(f"콜백 메서드를 찾을 수 없음: {callback_cls}.{callback_method}")
            
            elif callback_cls in self.workers:
                # 워커에게 콜백 작업 전달
                task_queue = self.task_queues.get(callback_cls)
                if task_queue:
                    task_id = str(uuid.uuid4())
                    task = (task_id, callback_method, (callback_data,), {}, False)
                    task_queue.put(task)
                else:
                    logging.error(f"'{callback_cls}'의 작업 큐를 찾을 수 없습니다.")
            
            elif callback_cls in self.proxies:
                # 프록시에게 콜백 작업 전달
                proxy = self.proxies[callback_cls]
                proxy_method = getattr(proxy, callback_method)
                proxy_method(callback_data)
            
            else:
                logging.error(f"콜백 클래스를 찾을 수 없음: {callback_cls}")
            
        except Exception as e:
            logging.error(f"콜백 처리 오류: {callback_cls}.{callback_method}", exc_info=True)
    
    def _run_with_callback(self, obj, method_name, args, kwargs, callback, cls_name):
        """콜백이 있는 메서드 실행 (스레드에서)"""
        try:
            # 메서드 찾기
            method = getattr(obj, method_name)
            
            # 결과
            result = None
            error = None
            
            try:
                # 메서드 실행
                result = method(*args, **kwargs)
            except Exception as e:
                error = {
                    'type': type(e).__name__,
                    'message': str(e),
                    'traceback': traceback.format_exc()
                }
                logging.error(f"메서드 실행 오류: {cls_name}.{method_name}", exc_info=True)
            
            # 콜백 정보 분리
            if isinstance(callback, tuple) and len(callback) == 2:
                callback_cls, callback_method = callback
                
                # 콜백 데이터 생성
                callback_data = {
                    'task_id': str(uuid.uuid4()),
                    'result': result,
                    'error': error,
                    'source': {'cls_name': cls_name, 'method_name': method_name},
                    'execution_mode': 'main'
                }
                
                # 콜백 처리
                self._handle_callback(callback_cls, callback_method, callback_data)
            
        except Exception as e:
            logging.error(f"콜백 실행 오류: {cls_name}.{method_name}", exc_info=True)
    
    def set_shm(self, var_name: str, value: Any, timeout: int = None) -> bool:
        """공유 메모리 변수 설정"""
        return self.shm_manager.update_shared_memory(var_name, value, timeout)
    
    def get_shm(self, var_name: str, timeout: int = None) -> Any:
        """공유 메모리 변수 가져오기"""
        return self.shm_manager.get_shared_memory(var_name, timeout)
    
    def delete_shm(self, var_name: str) -> bool:
        """공유 메모리 변수 삭제"""
        return self.shm_manager.delete_shared_memory(var_name)
    
    def cleanup(self):
        """모든 자원 정리"""
        # 요청 수신 비활성화
        self.accept_requests = False
        
        # 1. 결과 처리 스레드 종료 신호 설정 (먼저 설정)
        self.result_thread_running = False
        self.message_thread_running = False
        
        # 2. 모든 워커 정지
        for cls_name in list(self.workers.keys()):
            try:
                logging.info(f"IPCManager: '{cls_name}' 정지 중...")
                self.stop(cls_name)
            except Exception as e:
                logging.error(f"IPCManager: '{cls_name}' 정지 실패", exc_info=True)
        
        # 3. 모든 객체 stop 메서드 호출
        for cls_name in list(self.objects.keys()):
            try:
                obj = self.objects[cls_name]
                # 객체에 stop 메서드가 있으면 호출
                if hasattr(obj, 'stop') and callable(obj.stop):
                    logging.info(f"IPCManager: '{cls_name}' 객체 stop 메서드 호출")
                    obj.stop()
            except Exception as e:
                logging.error(f"IPCManager: '{cls_name}' 객체 stop 호출 실패", exc_info=True)
        
        # 4. 결과 처리 스레드 종료 대기
        if self.result_thread.is_alive():
            self.result_thread.join(5)
        
        if self.message_thread.is_alive():
            self.message_thread.join(5)
        
        # 5. 모든 프록시 정리
        for cls_name, proxy in list(self.proxies.items()):
            try:
                logging.info(f"IPCManager: '{cls_name}' 프록시 정리 중...")
                proxy.cleanup()
            except Exception as e:
                logging.error(f"IPCManager: '{cls_name}' 프록시 정리 실패", exc_info=True)
        
        # 6. 모든 워커 등록 해제
        for cls_name in list(self.workers.keys()):
            try:
                logging.info(f"IPCManager: '{cls_name}' 등록 해제 중...")
                self.unregister(cls_name)
            except Exception as e:
                logging.error(f"IPCManager: '{cls_name}' 등록 해제 실패", exc_info=True)
        
        # 7. 공유 메모리 정리
        logging.info("IPCManager: 공유 메모리 정리 중...")
        self.shm_manager.cleanup()
        
        # 8. 메모리 관리자 중지
        try:
            logging.info("IPCManager: 멀티프로세싱 매니저 종료 중...")
            self.mp_manager.shutdown()
        except Exception as e:
            logging.error("IPCManager: 멀티프로세싱 매니저 종료 실패", exc_info=True)
        
        logging.info("IPCManager 정리 완료")

# 대용량 데이터 처리를 위한 클래스
class LargeDataHandler:
   """대용량 데이터 처리 클래스"""
   
   def __init__(self):
       self.data_map = {}
       self._lock = threading.RLock()
   
   def store_large_data(self, data: Any) -> str:
       """대용량 데이터 저장 및 참조 ID 반환"""
       with self._lock:
           # 고유 ID 생성
           data_id = str(uuid.uuid4())
           # 데이터 저장
           self.data_map[data_id] = data
           return data_id
   
   def get_large_data(self, data_id: str) -> Any:
       """참조 ID로 대용량 데이터 가져오기"""
       with self._lock:
           return self.data_map.get(data_id)
   
   def remove_large_data(self, data_id: str) -> bool:
       """대용량 데이터 삭제"""
       with self._lock:
           if data_id in self.data_map:
               del self.data_map[data_id]
               return True
           return False
   
   def cleanup(self):
       """모든 데이터 정리"""
       with self._lock:
           self.data_map.clear()

# NumPy 배열 처리를 위한 클래스
class NumpyArrayHandler:
   """NumPy 배열 데이터 처리 클래스"""
   
   def __init__(self):
       self.array_memories = {}
       self.array_shapes = {}
       self.array_dtypes = {}
       self._lock = threading.RLock()
   
   def store_array(self, name: str, array: np.ndarray) -> bool:
       """NumPy 배열을 공유 메모리에 저장"""
       try:
           with self._lock:
               # 기존 메모리 정리
               self.remove_array(name)
               
               # 배열 정보 저장
               self.array_shapes[name] = array.shape
               self.array_dtypes[name] = array.dtype
               
               # 바이트 길이 계산
               nbytes = array.nbytes
               
               # 공유 메모리 생성
               shm = shared_memory.SharedMemory(name=name, create=True, size=nbytes)
               
               # 공유 메모리에 NumPy 배열 생성
               shared_array = np.ndarray(
                   array.shape, dtype=array.dtype, buffer=shm.buf
               )
               
               # 데이터 복사
               shared_array[:] = array[:]
               
               # 메모리 참조 저장
               self.array_memories[name] = shm
               
               # 메타데이터 저장 (다른 프로세스에서 접근 가능하도록)
               meta_name = f"{name}_meta"
               meta_data = {
                   'shape': array.shape,
                   'dtype': array.dtype
               }
               meta_bytes = pickle.dumps(meta_data)
               meta_shm = shared_memory.SharedMemory(
                   name=meta_name, create=True, size=len(meta_bytes)
               )
               meta_shm.buf[:len(meta_bytes)] = meta_bytes
               
               return True
               
       except Exception as e:
           logging.error(f"NumPy 배열 저장 실패: {name}", exc_info=True)
           return False
   
   def get_array(self, name: str) -> np.ndarray:
       """공유 메모리에서 NumPy 배열 가져오기"""
       try:
           with self._lock:
               # 이미 접근한 적이 있는 경우
               if name in self.array_memories:
                   # 공유 메모리 접근
                   shm = self.array_memories[name]
                   
                   # 배열 정보 가져오기
                   shape = self.array_shapes[name]
                   dtype = self.array_dtypes[name]
                   
                   # 공유 메모리에서 배열 생성
                   array = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
                   return array
               
               # 다른 프로세스에서 생성한 공유 메모리 접근
               try:
                   # 정보를 모르는 경우 메타데이터 가져오기
                   meta_name = f"{name}_meta"
                   try:
                       meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)
                       meta_data = pickle.loads(bytes(meta_shm.buf))
                       shape = meta_data['shape']
                       dtype = meta_data['dtype']
                       meta_shm.close()
                   except:
                       # 메타데이터가 없으면 실패
                       raise ValueError(f"배열 메타데이터를 찾을 수 없음: {name}")
                   
                   # 공유 메모리 접근
                   shm = shared_memory.SharedMemory(name=name, create=False)
                   
                   # 정보 저장
                   self.array_memories[name] = shm
                   self.array_shapes[name] = shape
                   self.array_dtypes[name] = dtype
                   
                   # 공유 메모리에서 배열 생성
                   array = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
                   return array
                   
               except Exception as inner_e:
                   logging.error(f"공유 메모리 배열 접근 실패: {name}", exc_info=True)
                   raise inner_e
           
       except Exception as e:
           logging.error(f"NumPy 배열 가져오기 실패: {name}", exc_info=True)
           return None
   
   def remove_array(self, name: str) -> bool:
       """NumPy 배열 공유 메모리 제거"""
       try:
           with self._lock:
               # 기존 공유 메모리 정리
               if name in self.array_memories:
                   shm = self.array_memories[name]
                   shm.close()
                   try:
                       shm.unlink()
                   except:
                       pass  # 이미 언링크 됐을 수 있음
                   
                   del self.array_memories[name]
                   
                   # 메타데이터 정리
                   if name in self.array_shapes:
                       del self.array_shapes[name]
                   
                   if name in self.array_dtypes:
                       del self.array_dtypes[name]
                   
                   # 메타데이터 공유 메모리 정리
                   meta_name = f"{name}_meta"
                   try:
                       meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)
                       meta_shm.close()
                       meta_shm.unlink()
                   except:
                       pass
               
               return True
               
       except Exception as e:
           logging.error(f"NumPy 배열 제거 실패: {name}", exc_info=True)
           return False
   
   def cleanup(self):
       """모든 NumPy 배열 공유 메모리 정리"""
       with self._lock:
           for name, shm in list(self.array_memories.items()):
               try:
                   shm.close()
                   try:
                       shm.unlink()
                   except:
                       pass
               except:
                   pass
           
           self.array_memories.clear()
           self.array_shapes.clear()
           self.array_dtypes.clear()

# 전역 변수 및 초기화 함수
shm_manager = None
large_data_handler = None
numpy_array_handler = None

def init_ipc_manager():
   """IPC 관리자 및 관련 핸들러 초기화"""
   global shm_manager, large_data_handler, numpy_array_handler
   
   # 이미 초기화되었는지 확인
   if shm_manager is not None:
       return
   
   # 공유 메모리 관리자 초기화
   shm_manager = SharedMemoryManager()
   
   # 대용량 데이터 핸들러 초기화
   large_data_handler = LargeDataHandler()
   
   # NumPy 배열 핸들러 초기화
   numpy_array_handler = NumpyArrayHandler()
   
   logging.info("IPC 관리자 및 핸들러 초기화 완료")

def cleanup_ipc_manager():
   """IPC 관리자 및 관련 핸들러 정리"""
   global shm_manager, large_data_handler, numpy_array_handler
   
   # 정리
   if numpy_array_handler is not None:
       numpy_array_handler.cleanup()
       numpy_array_handler = None
   
   if large_data_handler is not None:
       large_data_handler.cleanup()
       large_data_handler = None
   
   if shm_manager is not None:
       shm_manager.cleanup()
       shm_manager = None
   
   logging.info("IPC 관리자 및 핸들러 정리 완료")

# 스크립트가 직접 실행될 때만 실행
if __name__ == "__main__":
   # 로깅 초기화
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s.%(msecs)03d-%(levelname)s-[%(filename)s(%(lineno)d) / %(funcName)s] %(message)s',
       datefmt='%Y-%m-%d %H:%M:%S'
   )
   
   try:
       # IPC 관리자 초기화
       init_ipc_manager()
       
   except Exception as e:
       logging.error("IPC 관리자 오류", exc_info=True)
   
   finally:
       # 정리
       cleanup_ipc_manager()