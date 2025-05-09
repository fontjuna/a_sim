# ipc_manager.py
import pickle
import queue
import logging
import threading
import multiprocessing
import zlib
import time
import uuid
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

class IPCManager:
    """
    프로세스/스레드 간 통신을 관리하는 매니저 클래스
    메인 스레드, 멀티 스레드, 멀티 프로세스 간 통신을 지원
    """
    _instances = {}  # 프로세스별 인스턴스 저장
    _lock = threading.Lock()
    _manager = None
    
    @classmethod
    def get_instance(cls, shared_registry=None, shared_queues=None):
        """싱글톤 인스턴스 가져오기 (프로세스별)"""
        pid = multiprocessing.current_process().pid
        
        with cls._lock:
            if pid not in cls._instances:
                # 메인 프로세스면 Manager 생성
                parent_process = multiprocessing.parent_process()
                is_main_process = parent_process is None
                
                if is_main_process and cls._manager is None:
                    cls._manager = multiprocessing.Manager()
                    
                    # 초기 공유 자원 생성
                    if shared_registry is None:
                        shared_registry = cls._manager.dict()
                    if shared_queues is None:
                        shared_queues = cls._manager.dict()
                
                cls._instances[pid] = cls(shared_registry, shared_queues)
            
            return cls._instances[pid]
    
    def __init__(self, shared_registry=None, shared_queues=None):
        """
        IPCManager 초기화
        
        Args:
            shared_registry: 프로세스 간 공유 레지스트리
            shared_queues: 프로세스 간 공유 큐 딕셔너리
        """

        # 현재 프로세스 ID
        self._pid = multiprocessing.current_process().pid
        
        # 메인 프로세스인지 확인
        self._parent_process = multiprocessing.parent_process()
        self._is_main_process = self._parent_process is None
        
        # 로컬 객체 저장소 (현재 프로세스 내 객체 참조)
        self._objects = {}  # name -> (object, type)
        
        # 공유 상태 설정
        self._shared_registry = shared_registry
        self._shared_queues = shared_queues if shared_queues is not None else {}
        
        # 로컬 통신 채널 캐시
        self._request_queues = {}   # name -> Queue
        self._response_queues = {}  # name -> Queue
        self._events = {}           # name -> Event (스레드 간 동기화용)
        
        # 비동기 콜백 저장
        self._callbacks = {}  # msg_id -> callback
        
        # 종료 플래그
        self._running = {}  # name -> running flag
        
        # 워커 스레드/프로세스
        self._workers = {}  # name -> worker thread/process
        
        # 청크 수신 임시 저장소
        self._chunk_buffers = {}  # msg_id -> {chunks, total_chunks}
        
        # 응답 체커 스레드
        self._response_checker_running = False
        self._response_checker_thread = None
        
        logging.debug(f"Process {self._pid}: IPCManager initialized")
    
    def register(self, name: str, obj: Any, type_: Optional[str] = None) -> None:
        """
        통신 객체 등록
        
        Args:
            name: 등록할 객체 이름
            obj: 등록할 객체
            type_: 객체 유형 (None=메인스레드, 'thread'=멀티스레드, 'process'=멀티프로세스)
        """
        logging.debug(f"Process {self._pid}: Registering {name} as {type_}")
        
        # 로컬 등록
        self._objects[name] = (obj, type_)
        self._running[name] = False
        
        # 글로벌 등록
        if self._shared_registry is not None:
            self._shared_registry[name] = {
                'pid': self._pid,
                'type': type_
            }
        
        # 통신 채널 생성 - 모든 객체 타입에 대해 공유 큐 생성
        req_key = f"{name}_req"
        resp_key = f"{name}_resp"
        
        # 메인 프로세스에서만 공유 큐 생성
        if self._is_main_process:
            if self._shared_queues is not None:
                # 큐가 없으면 생성
                if req_key not in self._shared_queues:
                    self._shared_queues[req_key] = multiprocessing.Manager().Queue()
                if resp_key not in self._shared_queues:
                    self._shared_queues[resp_key] = multiprocessing.Manager().Queue()
                
                # 로그 출력
                logging.debug(f"Process {self._pid}: Created shared queues for {name}")
                logging.debug(f"Process {self._pid}: Shared queues: {list(self._shared_queues.keys())}")
        
        # 로컬 큐 캐시에 저장 (무조건 로컬 캐싱 시도)
        if self._shared_queues is not None:
            if req_key in self._shared_queues:
                self._request_queues[name] = self._shared_queues[req_key]
                logging.debug(f"Process {self._pid}: Cached request queue for {name}")
            else:
                logging.error(f"Process {self._pid}: Shared request queue for {name} not found")
                
            if resp_key in self._shared_queues:
                self._response_queues[name] = self._shared_queues[resp_key]
                logging.debug(f"Process {self._pid}: Cached response queue for {name}")
            else:
                logging.error(f"Process {self._pid}: Shared response queue for {name} not found")
        
        # 추가: 스레드 객체용 로컬 큐 생성 (항상, 앞의 과정과 무관하게)
        if type_ == 'thread':
            # 스레드는 프로세스 내 로컬 큐 사용
            self._request_queues[name] = queue.Queue()
            self._response_queues[name] = queue.Queue()
            self._events[name] = threading.Event()
        
        # 응답 체커 스레드 시작
        self._start_response_checker()

    def _start_response_checker(self):
        """응답 체커 스레드 시작 (한 번만)"""
        if not self._response_checker_running:
            self._response_checker_running = True
            self._response_checker_thread = threading.Thread(
                target=self._check_responses, 
                daemon=True
            )
            self._response_checker_thread.start()
            logging.debug(f"Process {self._pid}: Response checker thread started")
    
    def _check_responses(self):
        """비동기 응답을 주기적으로 확인하는 스레드"""
        while self._response_checker_running:
            try:
                # 공유 레지스트리가 없으면 건너뛰기
                if self._shared_registry is None:
                    time.sleep(0.1)
                    continue
                
                # 모든 객체 확인
                for name in list(self._shared_registry.keys()):
                    try:
                        # 응답 큐 가져오기
                        response_queue = self._get_response_queue(name)
                        if response_queue is None:
                            continue
                        
                        # 큐가 비어있지 않은지 확인
                        try:
                            response = self._receive_from_queue(response_queue)
                        except queue.Empty:
                            continue
                        except Exception as e:
                            logging.error(f"Process {self._pid}: Error getting response: {e}")
                            continue
                            
                        msg_id = response.get('id', '')
                        
                        # 등록된 콜백이 있는지 확인
                        if msg_id in self._callbacks:
                            callback = self._callbacks.pop(msg_id)
                            result = response.get('result')
                            error = response.get('error')
                            
                            # 콜백 실행
                            try:
                                if error:
                                    callback(None, error)
                                else:
                                    callback(result)
                            except Exception as e:
                                logging.error(f"Process {self._pid}: Error executing callback for {msg_id}: {e}")
                        else:
                            # 콜백이 없으면 다시 큐에 넣음
                            response_queue.put(response)
                    except Exception as e:
                        logging.error(f"Process {self._pid}: Error checking responses for {name}: {e}")
            except Exception as e:
                logging.error(f"Process {self._pid}: Error in check_responses: {e}")
            
            # 잠시 대기
            time.sleep(0.01)    

    def _get_request_queue(self, name: str):
        """요청 큐 가져오기"""
        # 로컬 캐시 확인
        if name in self._request_queues and self._request_queues[name] is not None:
            return self._request_queues[name]
        
        # 공유 큐 확인 및 캐싱
        req_key = f"{name}_req"
        if self._shared_queues is not None and req_key in self._shared_queues:
            self._request_queues[name] = self._shared_queues[req_key]
            logging.debug(f"Process {self._pid}: Loaded request queue for {name} from shared queues")
            return self._request_queues[name]
        
        logging.error(f"Process {self._pid}: Request queue for {name} not found (keys: {list(self._shared_queues.keys()) if self._shared_queues else 'None'})")
        return None
    
    def _get_response_queue(self, name: str):
        """응답 큐 가져오기"""
        # 로컬 캐시 확인
        if name in self._response_queues and self._response_queues[name] is not None:
            return self._response_queues[name]
        
        # 공유 큐 확인 및 캐싱
        resp_key = f"{name}_resp"
        if self._shared_queues is not None and resp_key in self._shared_queues:
            self._response_queues[name] = self._shared_queues[resp_key]
            logging.debug(f"Process {self._pid}: Loaded response queue for {name} from shared queues")
            return self._response_queues[name]
        
        logging.error(f"Process {self._pid}: Response queue for {name} not found (keys: {list(self._shared_queues.keys()) if self._shared_queues else 'None'})")
        return None
    
    def _receive_from_queue(self, queue_obj, timeout=0.01):
        """큐에서 데이터 가져오기 (예외 처리 통합)"""
        try:
            return queue_obj.get(block=False)
        except (queue.Empty, Exception):
            raise queue.Empty()

    def work(self, name, function, *args, **kwargs):
        """일반 함수 호출 방식의 래퍼"""
        return self.do_work(name, function, list(args), kwargs)
    
    def answer(self, name, function, *args, **kwargs):
        """일반 함수 호출 방식의 래퍼"""
        callback = kwargs.pop('callback', None)
        return self.do_answer(name, function, list(args), kwargs, callback)

    def do_work(self, name: str, function: str, args: List = None, kwargs: Dict = None) -> None:
        """
        다른 객체에게 작업 요청 (결과 기다리지 않음)
        
        Args:
            name: 대상 객체 이름
            function: 호출할 함수 이름
            args: 위치 인자
            kwargs: 키워드 인자
        """
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
            
        # 대상 객체가 등록되어 있는지 확인
        if self._shared_registry is None or name not in self._shared_registry:
            raise ValueError(f"Object {name} not registered in any process")
        
        obj_info = self._shared_registry[name]
        target_pid = obj_info.get('pid')
        obj_type = obj_info.get('type')
        
        # 로컬 객체이면 직접 호출
        if target_pid == self._pid and name in self._objects:
            obj, _ = self._objects[name]
            
            if obj_type is None:  # 메인 스레드
                # 직접 함수 호출
                try:
                    func = getattr(obj, function)
                    func(*args, **kwargs)
                    return
                except Exception as e:
                    logging.error(f"Process {self._pid}: Error executing {function} on {name}: {e}")
                    return
        
        # 메시지 ID 생성
        msg_id = str(uuid.uuid4())
        
        # 요청 메시지 생성
        request = {
            'sender': f"{self._pid}:{uuid.uuid4()}",
            'function': function,
            'args': args,
            'kwargs': kwargs,
            'id': msg_id
        }
        
        # 요청 큐 가져오기
        request_queue = self._get_request_queue(name)
        if request_queue is None:
            raise RuntimeError(f"Request queue for {name} not found")
            
        # 요청 전송
        request_queue.put(request)
        logging.debug(f"Process {self._pid}: Sent work request to {name} (pid {target_pid}): {function}")
    
    def do_answer(self, name: str, function: str, args: List = None, kwargs: Dict = None, 
              callback: Callable = None) -> Any:
        """
        다른 객체에게 작업 요청하고 결과를 기다림/받음
        
        Args:
            name: 대상 객체 이름
            function: 호출할 함수 이름
            args: 위치 인자
            kwargs: 키워드 인자
            callback: 비동기 콜백 함수 (지정 시 비동기로 처리)
            
        Returns:
            함수 호출 결과 (동기 호출 시)
        """
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
            
        # 대상 객체가 등록되어 있는지 확인
        if self._shared_registry is None or name not in self._shared_registry:
            raise ValueError(f"Object {name} not registered in any process")
        
        obj_info = self._shared_registry[name]
        target_pid = obj_info.get('pid')
        obj_type = obj_info.get('type')
        
        # 로컬 객체이면 직접 호출 가능한지 확인
        if target_pid == self._pid and name in self._objects:
            obj, _ = self._objects[name]
            
            if obj_type is None:  # 메인 스레드
                # 직접 함수 호출
                try:
                    func = getattr(obj, function)
                    result = func(*args, **kwargs)
                    if callback:
                        callback(result)
                    return result
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Process {self._pid}: Error executing {function} on {name}: {error_msg}")
                    if callback:
                        callback(None, error_msg)
                    raise
        
        # 메시지 ID 생성
        msg_id = str(uuid.uuid4())
        
        # 요청 메시지 생성
        request = {
            'sender': f"{self._pid}:{uuid.uuid4()}",
            'function': function,
            'args': args,
            'kwargs': kwargs,
            'id': msg_id
        }
        
        # 요청 큐 가져오기
        request_queue = self._get_request_queue(name)
        if request_queue is None:
            raise RuntimeError(f"Request queue for {name} not found")
        
        # 비동기 호출 시 콜백 등록
        if callback:
            self._callbacks[msg_id] = callback
            
            # 요청 전송
            request_queue.put(request)
            logging.debug(f"Process {self._pid}: Sent async request to {name} (pid {target_pid}): {function}")
            return None
            
        # 동기 호출 처리
        # 응답 큐 가져오기
        response_queue = self._get_response_queue(name)
        if response_queue is None:
            raise RuntimeError(f"Response queue for {name} not found")
        
        # 요청 전송
        request_queue.put(request)
        logging.debug(f"Process {self._pid}: Sent sync request to {name} (pid {target_pid}): {function}")
        
        # 응답 대기 (타임아웃 설정)
        timeout = 30  # 30초 타임아웃
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 응답 대기
                response = self._receive_from_queue(response_queue, timeout=0.1)
                
                # 응답 ID 확인
                if response.get('id') == msg_id:
                    error = response.get('error')
                    if error:
                        logging.error(f"Process {self._pid}: Error from {name}.{function}: {error}")
                        raise RuntimeError(f"Error from {name}.{function}: {error}")
                    return response.get('result')
                else:
                    # 다른 요청의 응답이면 다시 큐에 넣음
                    response_queue.put(response)
            except queue.Empty:
                continue
        
        # 타임아웃
        raise TimeoutError(f"Timeout waiting for response from {name}.{function}")
    
    def start(self, name: str) -> None:
        """
        등록된 객체의 워커 시작
        
        Args:
            name: 시작할 객체 이름
        """
        if name not in self._objects:
            raise ValueError(f"Object {name} not registered in this process")
        
        if self._running.get(name, False):
            logging.warning(f"Process {self._pid}: {name} worker already running")
            return
        
        obj, type_ = self._objects[name]
        
        if type_ is None:  # 메인 스레드
            # 메인 스레드 객체도 큐 기반 워커 시작
            worker = threading.Thread(
                target=self._worker_loop_process,  # process 워커와 동일한 로직 사용
                args=(name, obj, self._get_request_queue(name), self._get_response_queue(name)),
                daemon=True
            )
            self._workers[name] = worker
            self._running[name] = True
            worker.start()
            logging.debug(f"Process {self._pid}: Started worker thread for main thread object {name}")
        elif type_ == 'thread':  # 멀티 스레드
            worker = threading.Thread(
                target=self._worker_loop_thread,
                args=(name, obj, self._request_queues[name], self._response_queues[name]),
                daemon=True
            )
            self._workers[name] = worker
            self._running[name] = True
            worker.start()
            logging.debug(f"Process {self._pid}: Started thread worker for {name}")
        elif type_ == 'process':  # 멀티 프로세스
            worker = threading.Thread(
                target=self._worker_loop_process,
                args=(name, obj, self._get_request_queue(name), self._get_response_queue(name)),
                daemon=True
            )
            self._workers[name] = worker
            self._running[name] = True
            worker.start()
            logging.debug(f"Process {self._pid}: Started process worker thread for {name}")
    
    def stop(self, name: str) -> None:
        """
        워커 중지
        
        Args:
            name: 중지할 워커 이름
        """
        if name not in self._objects:
            raise ValueError(f"Object {name} not registered in this process")
        
        if not self._running.get(name, False):
            logging.warning(f"Process {self._pid}: {name} worker already stopped")
            return
        
        obj, type_ = self._objects[name]
        if hasattr(obj, 'stop') and callable(obj.stop):
            obj.stop()
        
        if type_ is None:  # 메인 스레드
            self._running[name] = False
        elif type_ == 'thread':  # 멀티 스레드
            self._running[name] = False
            # 스레드는 타임아웃으로 종료됨
            if name in self._workers:
                worker = self._workers[name]
                if worker.is_alive():
                    worker.join(timeout=2.0)
                    if worker.is_alive():
                        logging.warning(f"Process {self._pid}: Thread worker for {name} did not terminate")
        elif type_ == 'process':  # 멀티 프로세스
            self._running[name] = False
            # 종료 요청 전송
            request_queue = self._get_request_queue(name)
            if request_queue:
                request_queue.put({
                    'function': '_terminate_',
                    'id': str(uuid.uuid4())
                })
            
            # 워커 스레드 종료 대기
            if name in self._workers:
                worker = self._workers[name]
                if worker.is_alive():
                    worker.join(timeout=2.0)
                    if worker.is_alive():
                        logging.warning(f"Process {self._pid}: Process worker thread for {name} did not terminate")
        
        logging.debug(f"Process {self._pid}: Stopped worker for {name}")
    
    def cleanup(self) -> None:
        """모든 워커 종료 및 자원 정리"""
        logging.debug(f"Process {self._pid}: Cleaning up IPCManager")
        
        # 응답 체커 중지
        self._response_checker_running = False
        if self._response_checker_thread and self._response_checker_thread.is_alive():
            self._response_checker_thread.join(timeout=2.0)
        
        # 모든 워커 종료
        for name in list(self._objects.keys()):
            if self._running.get(name, False):
                try:
                    obj, _ = self._objects[name]
                    if hasattr(obj, 'stop') and callable(obj.stop):
                        obj.stop()
                    
                    self.stop(name)
                except Exception as e:
                    logging.error(f"Process {self._pid}: Error stopping worker {name}: {e}")
        
        # 큐 정리
        for q in list(self._request_queues.values()) + list(self._response_queues.values()):
            try:
                # 큐 비우기
                while True:
                    try:
                        q.get(block=False)
                    except Exception:
                        break
            except Exception:
                pass
        
        logging.debug(f"Process {self._pid}: IPCManager cleanup complete")

    def _worker_loop_thread(self, name: str, obj: Any, request_queue: queue.Queue, response_queue: queue.Queue) -> None:
        """
        스레드 워커 루프
        
        Args:
            name: 워커 이름
            obj: 대상 객체
            request_queue: 요청 큐
            response_queue: 응답 큐
        """
        logging.debug(f"Process {self._pid}: Thread worker loop for {name} started")
        
        while self._running.get(name, False):
            try:
                # 요청 대기 (최대 1초)
                try:
                    request = request_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # 요청 처리
                sender = request.get('sender', 'unknown')
                func_name = request.get('function', '')
                args = request.get('args', [])
                kwargs = request.get('kwargs', {})
                msg_id = request.get('id', '')
                
                logging.debug(f"Process {self._pid}: Worker {name} received request: {func_name} from {sender}")
                
                # 결과 및 오류 초기화
                result = None
                error = None
                
                # 함수 실행
                try:
                    func = getattr(obj, func_name)
                    result = func(*args, **kwargs)
                except Exception as e:
                    error = str(e)
                    logging.error(f"Process {self._pid}: Error executing {func_name} on {name}: {e}")
                
                # 응답 생성
                response = {
                    'result': result,
                    'error': error,
                    'id': msg_id
                }
                
                # 응답 전송
                response_queue.put(response)
                logging.debug(f"Process {self._pid}: Worker {name} sent response for {func_name}")
                
            except Exception as e:
                logging.error(f"Process {self._pid}: Error in worker loop for {name}: {e}")
    
    def _worker_loop_process(self, name: str, obj: Any, request_queue, response_queue) -> None:
        """
        프로세스 워커 루프 - pickle 오류 방지 처리 추가
        
        Args:
            name: 워커 이름
            obj: 대상 객체
            request_queue: 요청 큐
            response_queue: 응답 큐
        """
        logging.debug(f"Process {self._pid}: Process worker loop for {name} started")
        
        # 객체에 IPCManager 참조 설정
        if hasattr(obj, 'ipc') and obj.ipc is None:
            obj.ipc = self
        
        while self._running.get(name, False):
            try:
                # 요청 대기 (최대 1초)
                try:
                    request = request_queue.get(timeout=1.0)
                except Exception:
                    continue
                
                # 종료 요청 확인
                if request.get('function') == '_terminate_':
                    logging.debug(f"Process {self._pid}: Process worker {name} received terminate signal")
                    break
                
                # 요청 처리
                sender = request.get('sender', 'unknown')
                func_name = request.get('function', '')
                args = request.get('args', [])
                kwargs = request.get('kwargs', {})
                msg_id = request.get('id', '')
                
                logging.debug(f"Process {self._pid}: Worker {name} received request: {func_name} from {sender}")
                
                # 결과 및 오류 초기화
                result = None
                error = None
                
                # 함수 실행
                try:
                    func = getattr(obj, func_name)
                    result = func(*args, **kwargs)
                    
                    # 결과를 pickle 가능한지 확인 (멀티프로세스 직렬화 오류 방지)
                    try:
                        pickle.dumps(result)
                    except Exception as e:
                        # pickle 불가능한 경우 안전한 형태로 변환
                        logging.warning(f"Process {self._pid}: Result of {func_name} is not pickle-able: {e}")
                        result = self._make_pickle_safe(result)
                        
                except Exception as e:
                    error = str(e)
                    logging.error(f"Process {self._pid}: Error executing {func_name} on {name}: {e}")
                
                # 응답 생성
                response = {
                    'result': result,
                    'error': error,
                    'id': msg_id
                }
                
                # 응답 전송
                response_queue.put(response)
                logging.debug(f"Process {self._pid}: Worker {name} sent response for {func_name}")
                
            except Exception as e:
                logging.error(f"Process {self._pid}: Error in process worker loop for {name}: {e}")

    def _make_pickle_safe(self, obj: Any) -> Any:
        """
        Pickle로 직렬화 불가능한 객체를 안전한 형태로 변환
        
        Args:
            obj: 변환할 객체
            
        Returns:
            변환된 객체
        """
        # 기본 자료형은 그대로 반환
        if obj is None or isinstance(obj, (bool, int, float, str, bytes)):
            return obj
            
        # 리스트/튜플: 각 항목을 재귀적으로 변환
        if isinstance(obj, (list, tuple)):
            return type(obj)(self._make_pickle_safe(x) for x in obj)
            
        # 딕셔너리: 키와 값을 재귀적으로 변환
        if isinstance(obj, dict):
            return {str(k): self._make_pickle_safe(v) for k, v in obj.items()}
            
        # 세트: 각 항목을 재귀적으로 변환
        if isinstance(obj, set):
            return {self._make_pickle_safe(x) for x in obj}
            
        # 객체의 문자열 표현 반환 (마지막 수단)
        try:
            return str(obj)
        except Exception:
            return "Unpickleable object"
ipc = None
#ipc = IPCManager.get_instance()

# 유틸리티 함수
def create_shared_resources():
    """공유 자원 생성 (메인 프로세스에서 사용)"""
    manager = multiprocessing.Manager()
    shared_registry = manager.dict()
    # 명시적인 dict() 대신 manager.dict() 사용 
    shared_queues = manager.dict()
    
    return manager, shared_registry, shared_queues

# 테스트 코드 (ipc_manager.py 파일 하단에 추가)
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Windows에서 멀티프로세싱을 위한 코드
    multiprocessing.freeze_support()
    
    # 공유 자원 생성 (메인 프로세스에서)
    
    # worker.py에서 클래스와 함수 가져오기
    from worker import AdminTest, initialize_worker
    
    # 테스트 코드
    def test_cross_communication():
        manager, shared_registry, shared_queues = create_shared_resources()

        # 필요한 모든 큐를 시작 시 미리 생성 (중요)
        for name in ["admin", "api", "dbm"]:
            shared_queues[f"{name}_req"] = manager.Queue()
            shared_queues[f"{name}_resp"] = manager.Queue()
        
        logging.debug(f"All queues created at startup: {list(shared_queues.keys())}")
            
        #IPCManager._manager = manager

        # IPCManager 인스턴스 생성 (공유 자원 전달)
        ipc = IPCManager.get_instance(shared_registry, shared_queues)
        
        # Admin 객체 생성 및 등록 (메인 스레드)
        admin = AdminTest()
        admin.ipc = ipc
        ipc.register("admin", admin)
        logging.debug(f"Shared queues after admin register: {list(shared_queues.keys())}")

        # API 및 DBM 서버를 별도 프로세스로 시작
        api_process = multiprocessing.Process(
            target=initialize_worker, 
            args=("api", "api", shared_registry, shared_queues),
            daemon=True
        )
        
        dbm_process = multiprocessing.Process(
            target=initialize_worker,
            args=("dbm", "dbm", shared_registry, shared_queues),
            daemon=True
        )
        
        # 프로세스 시작
        admin.ipc.start("admin")
        api_process.start()
        dbm_process.start()
        
        # 잠시 대기하여 모든 프로세스가 초기화될 시간 제공
        logging.debug("메인 프로세스: 모든 프로세스 초기화 대기 중...")
        time.sleep(2)
        
        try:
            # 다양한 통신 경로 테스트
            print("\n=== Admin -> API -> DBM 통신 경로 테스트 ===")
            result1 = ipc.answer("admin", "test_function", ["test_key"])
            print(f"결과: {result1}")
            
            print("\n=== DBM -> Admin 통신 테스트 ===")
            result2 = ipc.answer("dbm", "request_admin_action", ["urgent_action"])
            print(f"결과: {result2}")
            
            print("\n=== DBM -> API 통신 테스트 ===")
            result3 = ipc.answer("dbm", "store_data", ["from_dbm_test"])
            print(f"결과: {result3}")
            
            print("\n=== API -> Admin 통신 테스트 ===")
            result4 = ipc.answer("api", "send_notification", ["system_event"])
            print(f"결과: {result4}")
            
            # 대용량 데이터 전송 테스트
            print("\n=== 대용량 데이터 전송 테스트 ===")
            large_data = "X" * (1 * 1024 * 1024)  # 1MB 문자열
            ipc.work("api", "send_notification", [large_data[:20] + "... (잘림)"])
            print("대용량 데이터 전송 완료")
            
        except Exception as e:
            logging.error(f"테스트 중 오류 발생: {e}")
        finally:
            # 정리
            logging.debug("자원 정리 중...")
            ipc.cleanup()
            
            # 프로세스 종료
            logging.debug("프로세스 종료 중...")
            api_process.terminate()
            dbm_process.terminate()
            api_process.join()
            dbm_process.join()
            
            print("모든 테스트 완료!")
    
    # 테스트 실행
    test_cross_communication()


