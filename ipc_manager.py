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
                    logging.debug(f"Process {pid}: Creating multiprocessing.Manager")
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
        
        # 추가: 메인 프로세스일 경우 manager가 없으면 생성 (중복 방지를 위한 락 사용)
        if self._is_main_process and IPCManager._manager is None:
            with IPCManager._lock:
                if IPCManager._manager is None:
                    logging.debug(f"Process {self._pid}: Creating multiprocessing.Manager in __init__")
                    IPCManager._manager = multiprocessing.Manager()
        
        # 로컬 객체 저장소 (현재 프로세스 내 객체 참조)
        self._objects = {}  # name -> (object, type)
        
        # 공유 상태 설정
        self._shared_registry = shared_registry if shared_registry is not None else {}
        if self._is_main_process and IPCManager._manager is not None and not self._shared_registry:
            self._shared_registry = IPCManager._manager.dict()
            
        self._shared_queues = shared_queues if shared_queues is not None else {}
        if self._is_main_process and IPCManager._manager is not None and not self._shared_queues:
            self._shared_queues = IPCManager._manager.dict()
        
        # 로컬 통신 채널 캐시
        self._request_queues = {}   # name -> Queue
        self._response_queues = {}  # name -> Queue
        self._events = {}           # name -> Event (스레드 간 동기화용)
        
        # 비동기 콜백 저장
        self._callbacks = {}        # msg_id -> callback
        self._callback_timeouts = {}  # msg_id -> timeout timestamp
        
        # 종료 플래그
        self._running = {}          # name -> running flag
        
        # 워커 스레드/프로세스
        self._workers = {}          # name -> worker thread/process
        
        # 청크 수신 임시 저장소 
        self._chunk_buffers = {}    # msg_id -> {chunks, total_chunks, data}
        
        # 응답 체커 스레드
        self._response_checker_running = False
        self._response_checker_thread = None
        
        # 디버그 정보
        self._stats = {
            'sent_messages': 0,
            'received_messages': 0,
            'errors': 0,
            'timeouts': 0
        }
        
        logging.debug(f"Process {self._pid}: IPCManager initialized")

    def _get_queue(self, name: str, queue_type: str):
        """
        요청/응답 큐 가져오기 (통합 메서드)
        
        Args:
            name: 객체 이름
            queue_type: 'req' 또는 'resp'
        
        Returns:
            해당 큐 객체
        """
        queue_cache = self._request_queues if queue_type == 'req' else self._response_queues
        
        # 로컬 캐시 확인
        if name in queue_cache and queue_cache[name] is not None:
            return queue_cache[name]
        
        # 공유 큐 확인 및 캐싱
        key = f"{name}_{queue_type}"
        if self._shared_queues is not None and key in self._shared_queues:
            queue_cache[name] = self._shared_queues[key]
            logging.debug(f"Process {self._pid}: Loaded {queue_type} queue for {name} from shared queues")
            return queue_cache[name]
        
        logging.error(f"Process {self._pid}: {queue_type.capitalize()} queue for {name} not found" + 
                    f" (keys: {list(self._shared_queues.keys()) if self._shared_queues else 'None'})")
        return None
        
    def _get_request_queue(self, name: str):
        """요청 큐 가져오기"""
        return self._get_queue(name, 'req')
        
    def _get_response_queue(self, name: str):
        """응답 큐 가져오기"""
        return self._get_queue(name, 'resp')
    
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
                    # Manager가 없을 경우 생성 시도
                    if IPCManager._manager is None:
                        logging.debug(f"Process {self._pid}: Creating Manager on-demand during register")
                        IPCManager._manager = multiprocessing.Manager()
                    
                    self._shared_queues[req_key] = IPCManager._manager.Queue()
                if resp_key not in self._shared_queues:
                    self._shared_queues[resp_key] = IPCManager._manager.Queue()
                
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
                daemon=True,
                name="ResponseCheckerThread"
            )
            self._response_checker_thread.start()
            logging.debug(f"Process {self._pid}: Response checker thread started")
    
    def _receive_from_queue(self, queue_obj, timeout=0.01):
        """큐에서 데이터 가져오기 (예외 처리 통합)"""
        try:
            if isinstance(queue_obj, queue.Queue):  # 일반 Queue
                return queue_obj.get(block=False)
            else:  # multiprocessing.Queue
                return queue_obj.get(block=False)
        except (queue.Empty, Exception):
            raise queue.Empty()
    
    def _check_responses(self):
        """비동기 응답을 주기적으로 확인하는 스레드"""
        while self._response_checker_running:
            try:
                # 공유 레지스트리가 없으면 건너뛰기
                if self._shared_registry is None:
                    time.sleep(0.1)
                    continue
                
                # 콜백 타임아웃 체크
                current_time = time.time()
                timed_out_callbacks = []
                for msg_id, timeout_time in list(self._callback_timeouts.items()):
                    if current_time > timeout_time:
                        timed_out_callbacks.append(msg_id)
                
                # 타임아웃된 콜백 처리
                for msg_id in timed_out_callbacks:
                    if msg_id in self._callbacks:
                        callback = self._callbacks.pop(msg_id)
                        self._callback_timeouts.pop(msg_id, None)
                        try:
                            callback(None, "Timeout waiting for response")
                            self._stats['timeouts'] += 1
                        except Exception as e:
                            logging.error(f"Process {self._pid}: Error executing timeout callback for {msg_id}: {e}")
                
                # 응답 큐가 있는 객체만 처리
                for name in list(self._response_queues.keys()):
                    try:
                        # 응답 큐 가져오기
                        response_queue = self._response_queues.get(name)
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
                            
                        self._stats['received_messages'] += 1
                        msg_id = response.get('id', '')
                        
                        # 청크 응답 처리
                        if 'chunk_info' in response:
                            self._process_chunk_response(response)
                            continue
                        
                        # 등록된 콜백이 있는지 확인
                        if msg_id in self._callbacks:
                            callback = self._callbacks.pop(msg_id)
                            self._callback_timeouts.pop(msg_id, None)
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
                                self._stats['errors'] += 1
                        else:
                            # 콜백이 없으면 다시 큐에 넣음
                            response_queue.put(response)
                    except Exception as e:
                        logging.error(f"Process {self._pid}: Error checking responses for {name}: {e}")
            except Exception as e:
                logging.error(f"Process {self._pid}: Error in check_responses: {e}")
            
            # 잠시 대기
            time.sleep(0.01)    
    
    def _process_chunk_response(self, response):
        """청크 응답 처리"""
        msg_id = response.get('id', '')
        chunk_info = response.get('chunk_info', {})
        chunk_index = chunk_info.get('index', 0)
        total_chunks = chunk_info.get('total', 1)
        chunk_data = response.get('data', None)
        
        # 새 메시지면 버퍼 초기화
        if msg_id not in self._chunk_buffers:
            self._chunk_buffers[msg_id] = {
                'chunks': {},
                'total_chunks': total_chunks,
                'data': None
            }
        
        # 청크 저장
        buffer = self._chunk_buffers[msg_id]
        buffer['chunks'][chunk_index] = chunk_data
        
        # 모든 청크가 도착했는지 확인
        if len(buffer['chunks']) == buffer['total_chunks']:
            # 모든 청크를 순서대로 합침
            combined_data = b''
            for i in range(buffer['total_chunks']):
                combined_data += buffer['chunks'][i]
            
            # 압축 해제
            try:
                decompressed_data = zlib.decompress(combined_data)
                result = pickle.loads(decompressed_data)
                
                # 콜백 실행
                if msg_id in self._callbacks:
                    callback = self._callbacks.pop(msg_id)
                    self._callback_timeouts.pop(msg_id, None)
                    try:
                        callback(result)
                    except Exception as e:
                        logging.error(f"Process {self._pid}: Error executing chunk callback for {msg_id}: {e}")
                        self._stats['errors'] += 1
            except Exception as e:
                logging.error(f"Process {self._pid}: Error decompressing/unpickling chunks for {msg_id}: {e}")
                self._stats['errors'] += 1
                
                # 콜백에 에러 전달
                if msg_id in self._callbacks:
                    callback = self._callbacks.pop(msg_id)
                    self._callback_timeouts.pop(msg_id, None)
                    try:
                        callback(None, f"Error processing chunked data: {str(e)}")
                    except Exception as e2:
                        logging.error(f"Process {self._pid}: Error executing error callback for {msg_id}: {e2}")
            
            # 버퍼 삭제
            del self._chunk_buffers[msg_id]

    def work(self, name, function, *args, **kwargs):
        """일반 함수 호출 방식의 래퍼"""
        return self.do_work(name, function, list(args), kwargs)
    
    def answer(self, name, function, *args, **kwargs):
        """일반 함수 호출 방식의 래퍼"""
        callback = kwargs.pop('callback', None)
        return self.do_answer(name, function, list(args), kwargs, callback)

    def _prepare_request(self, name, function, args, kwargs):
        """요청 메시지 준비 및 유효성 검증 (중복 코드 제거)"""
        # 대상 객체가 등록되어 있는지 확인
        if self._shared_registry is None or name not in self._shared_registry:
            raise ValueError(f"Object {name} not registered in any process")
        
        obj_info = self._shared_registry[name]
        target_pid = obj_info.get('pid')
        obj_type = obj_info.get('type')
        
        # 로컬 객체 참조 가져오기
        local_obj = None
        if target_pid == self._pid and name in self._objects:
            local_obj, _ = self._objects[name]
            
            # 메인 스레드 객체면 직접 호출 가능
            if obj_type is None:
                return {
                    'local_obj': local_obj,
                    'is_direct_call': True,
                    'target_pid': target_pid,
                    'obj_type': obj_type
                }
        
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
            
        return {
            'local_obj': local_obj,
            'is_direct_call': False,
            'target_pid': target_pid,
            'obj_type': obj_type,
            'msg_id': msg_id,
            'request': request,
            'request_queue': request_queue
        }

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
            
        # 요청 준비
        try:
            req_data = self._prepare_request(name, function, args, kwargs)
        except Exception as e:
            logging.error(f"Process {self._pid}: Error preparing request for {name}.{function}: {e}")
            raise
        
        # 직접 호출 가능하면 로컬 호출
        if req_data['is_direct_call']:
            local_obj = req_data['local_obj']
            try:
                func = getattr(local_obj, function)
                func(*args, **kwargs)
                logging.debug(f"Process {self._pid}: Direct call to {name}.{function} completed")
                return
            except Exception as e:
                logging.error(f"Process {self._pid}: Error executing {function} on {name}: {e}")
                self._stats['errors'] += 1
                return
        
        # 요청 전송
        req_data['request_queue'].put(req_data['request'])
        self._stats['sent_messages'] += 1
        logging.debug(f"Process {self._pid}: Sent work request to {name} (pid {req_data['target_pid']}): {function}")
    
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
            
        # 요청 준비
        try:
            req_data = self._prepare_request(name, function, args, kwargs)
        except Exception as e:
            logging.error(f"Process {self._pid}: Error preparing request for {name}.{function}: {e}")
            if callback:
                callback(None, str(e))
            raise
        
        # 직접 호출 가능하면 로컬 호출
        if req_data['is_direct_call']:
            local_obj = req_data['local_obj']
            try:
                func = getattr(local_obj, function)
                result = func(*args, **kwargs)
                logging.debug(f"Process {self._pid}: Direct call to {name}.{function} completed")
                if callback:
                    callback(result)
                return result
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Process {self._pid}: Error executing {function} on {name}: {error_msg}")
                self._stats['errors'] += 1
                if callback:
                    callback(None, error_msg)
                raise
        
        msg_id = req_data['msg_id']
        request = req_data['request']
        request_queue = req_data['request_queue']
        
        # 비동기 호출 시 콜백 등록
        if callback:
            self._callbacks[msg_id] = callback
            # 타임아웃 설정 (30초)
            self._callback_timeouts[msg_id] = time.time() + 30.0
            
            # 요청 전송
            request_queue.put(request)
            self._stats['sent_messages'] += 1
            logging.debug(f"Process {self._pid}: Sent async request to {name} (pid {req_data['target_pid']}): {function}")
            return None
            
        # 동기 호출 처리
        # 응답 큐 가져오기
        response_queue = self._get_response_queue(name)
        if response_queue is None:
            raise RuntimeError(f"Response queue for {name} not found")
        
        # 요청 전송
        request_queue.put(request)
        self._stats['sent_messages'] += 1
        logging.debug(f"Process {self._pid}: Sent sync request to {name} (pid {req_data['target_pid']}): {function}")
        
        # 응답 대기 (타임아웃 설정)
        timeout = 30.0  # 30초 타임아웃
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 응답 대기
                response = self._receive_from_queue(response_queue, timeout=0.1)
                
                # 청크 응답 처리
                if 'chunk_info' in response:
                    # 동기 호출에서는 청크를 직접 처리하지 않음 (미구현)
                    logging.warning(f"Process {self._pid}: Received chunked response in sync call - not supported yet")
                    continue
                
                # 응답 ID 확인
                if response.get('id') == msg_id:
                    self._stats['received_messages'] += 1
                    error = response.get('error')
                    if error:
                        logging.error(f"Process {self._pid}: Error from {name}.{function}: {error}")
                        self._stats['errors'] += 1
                        raise RuntimeError(f"Error from {name}.{function}: {error}")
                    return response.get('result')
                else:
                    # 다른 요청의 응답이면 다시 큐에 넣음
                    response_queue.put(response)
            except queue.Empty:
                continue
        
        # 타임아웃
        self._stats['timeouts'] += 1
        raise TimeoutError(f"Timeout waiting for response from {name}.{function}")
    
    def _send_large_data(self, data, response_queue, msg_id, max_chunk_size=1024*1024):
        """대용량 데이터를 청크로 나누어 전송"""
        try:
            # 데이터 직렬화 및 압축
            serialized_data = pickle.dumps(data)
            compressed_data = zlib.compress(serialized_data)
            
            # 청크로 나누기
            chunks = []
            for i in range(0, len(compressed_data), max_chunk_size):
                chunks.append(compressed_data[i:i+max_chunk_size])
            
            total_chunks = len(chunks)
            
            # 청크 전송
            for i, chunk in enumerate(chunks):
                chunk_response = {
                    'id': msg_id,
                    'chunk_info': {
                        'index': i,
                        'total': total_chunks
                    },
                    'data': chunk
                }
                response_queue.put(chunk_response)
            
            logging.debug(f"Process {self._pid}: Sent large data in {total_chunks} chunks for {msg_id}")
            return True
        except Exception as e:
            logging.error(f"Process {self._pid}: Error sending large data for {msg_id}: {e}")
            self._stats['errors'] += 1
            return False
        
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
                target=self._worker_loop,
                args=(name, obj, self._get_request_queue(name), self._get_response_queue(name), False),
                daemon=True,
                name=f"Worker-{name}"
            )
            self._workers[name] = worker
            self._running[name] = True
            worker.start()
            logging.debug(f"Process {self._pid}: Started worker thread for main thread object {name}")
        elif type_ == 'thread':  # 멀티 스레드
            worker = threading.Thread(
                target=self._worker_loop,
                args=(name, obj, self._request_queues[name], self._response_queues[name], False),
                daemon=True,
                name=f"Worker-{name}"
            )
            self._workers[name] = worker
            self._running[name] = True
            worker.start()
            logging.debug(f"Process {self._pid}: Started thread worker for {name}")
        elif type_ == 'process':  # 멀티 프로세스
            worker = threading.Thread(
                target=self._worker_loop,
                args=(name, obj, self._get_request_queue(name), self._get_response_queue(name), True),
                daemon=True,
                name=f"Worker-{name}"
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
            try:
                obj.stop()
            except Exception as e:
                logging.error(f"Process {self._pid}: Error calling stop() on {name}: {e}")
        
        self._running[name] = False
        
        # 프로세스 종료 시그널 전송
        if type_ == 'process':
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
                    logging.warning(f"Process {self._pid}: Worker thread for {name} did not terminate")
        
        logging.debug(f"Process {self._pid}: Stopped worker for {name}")
    
    def cleanup(self) -> None:
        """모든 워커 종료 및 자원 정리"""
        logging.debug(f"Process {self._pid}: Cleaning up IPCManager")
        
        # 응답 체커 중지
        self._response_checker_running = False
        if self._response_checker_thread and self._response_checker_thread.is_alive():
            try:
                self._response_checker_thread.join(timeout=2.0)
            except Exception as e:
                logging.error(f"Process {self._pid}: Error stopping response checker thread: {e}")
        
        # 모든 워커 종료
        for name in list(self._objects.keys()):
            if self._running.get(name, False):
                try:
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
        
        # 통계 정보 출력
        logging.debug(f"Process {self._pid}: IPC Stats: {self._stats}")
        logging.debug(f"Process {self._pid}: IPCManager cleanup complete")

    def _worker_loop(self, name: str, obj: Any, request_queue, response_queue, is_process: bool = False) -> None:
        """
        통합된 워커 루프 (스레드/프로세스)
        
        Args:
            name: 워커 이름
            obj: 대상 객체
            request_queue: 요청 큐
            response_queue: 응답 큐
            is_process: 프로세스 워커 여부
        """
        logging.debug(f"Process {self._pid}: Worker loop for {name} started (is_process={is_process})")
        
        # 객체에 IPCManager 참조 설정
        if is_process and hasattr(obj, 'ipc') and obj.ipc is None:
            obj.ipc = self
        
        retry_count = 0
        max_retries = 3  # 최대 재시도 횟수
        
        while self._running.get(name, False):
            try:
                # 요청 대기 (최대 1초)
                try:
                    request = request_queue.get(timeout=1.0)
                except (queue.Empty, Exception):
                    continue
                
                # 종료 요청 확인
                if request.get('function') == '_terminate_':
                    logging.debug(f"Process {self._pid}: Worker {name} received terminate signal")
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
                    
                    # 프로세스 워커면 결과를 pickle 가능한지 확인
                    if is_process:
                        try:
                            # 먼저 pickle 시도
                            pickle.dumps(result)
                        except Exception as e:
                            # pickle 불가능한 경우 안전한 형태로 변환
                            logging.warning(f"Process {self._pid}: Result of {func_name} is not pickle-able: {e}")
                            result = self._make_pickle_safe(result)
                            
                    # 대용량 데이터인지 확인하여 청크 전송
                    large_data = False
                    try:
                        if result is not None:
                            # 크기 측정을 위한 시도
                            serialized = pickle.dumps(result)
                            if len(serialized) > 1024 * 1024:  # 1MB 이상이면 청크 전송
                                large_data = True
                                self._send_large_data(result, response_queue, msg_id)
                    except Exception as e:
                        logging.error(f"Process {self._pid}: Error checking result size: {e}")
                    
                    if not large_data:
                        # 일반 응답 생성
                        response = {
                            'result': result,
                            'error': None,
                            'id': msg_id
                        }
                        
                        # 응답 전송
                        response_queue.put(response)
                        
                except Exception as e:
                    error = str(e)
                    logging.error(f"Process {self._pid}: Error executing {func_name} on {name}: {e}")
                    
                    # 응답 생성
                    response = {
                        'result': None,
                        'error': error,
                        'id': msg_id
                    }
                    
                    # 응답 전송
                    response_queue.put(response)
                
                logging.debug(f"Process {self._pid}: Worker {name} sent response for {func_name}")
                retry_count = 0  # 성공 시 재시도 카운트 초기화
                
            except Exception as e:
                logging.error(f"Process {self._pid}: Error in worker loop for {name}: {e}")
                retry_count += 1
                
                # 연속 오류 발생 시 잠시 대기
                if retry_count > max_retries:
                    logging.error(f"Process {self._pid}: Too many errors in worker loop for {name}, sleeping...")
                    time.sleep(1.0)
                    retry_count = 0

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

    def get_stats(self):
        """통계 정보 가져오기"""
        return self._stats.copy()

# 싱글톤 인스턴스 초기화 (올바른 방법으로)
ipc = None #IPCManager.get_instance()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    from public import init_logger
    from worker import AdminTest, APITest, DBMTest

    init_logger()
   
    def test_cross_communication():
        ipc = IPCManager()
        admin = AdminTest()
        api = APITest()
        dbm = DBMTest()

        admin.ipc = ipc
        api.ipc = ipc
        dbm.ipc = ipc

        ipc.register("admin", admin)
        ipc.register("api", api, 'process')
        ipc.register("dbm", dbm, 'process')

        # 프로세스 시작
        admin.ipc.start("admin")
        api.ipc.start("api")
        dbm.ipc.start("dbm")
        
        # 잠시 대기하여 모든 프로세스가 초기화될 시간 제공
        logging.debug("메인 프로세스: 모든 프로세스 초기화 대기 중...")
        time.sleep(2)  # 고정 대기 시간 대신 초기화 완료 확인
        
        try:
            # 다양한 통신 경로 테스트
            print("\n=== Admin -> API -> DBM 통신 경로 테스트 ===")
            result1 = ipc.answer("admin", "test_function", "test_key")
            print(f"결과: {result1}")
            
            print("\n=== DBM -> Admin 통신 테스트 ===")
            result2 = ipc.answer("dbm", "request_admin_action", "urgent_action")
            print(f"결과: {result2}")
            
            print("\n=== DBM -> API 통신 테스트 ===")
            result3 = ipc.answer("dbm", "store_data", "from_dbm_test")
            print(f"결과: {result3}")
            
            print("\n=== API -> Admin 통신 테스트 ===")
            result4 = ipc.answer("api", "send_notification", "system_event")
            print(f"결과: {result4}")
            
            # 대용량 데이터 전송 테스트
            print("\n=== 대용량 데이터 전송 테스트 ===")
            large_data = "X" * (1 * 1024 * 1024)  # 1MB 문자열
            ipc.work("api", "send_notification", large_data[:20] + "... (잘림)")
            print("대용량 데이터 전송 완료")
            
            # 키움증권 로그인 테스트
            print("\n=== 키움증권 로그인 테스트 ===")
            try:
                result5 = ipc.answer("admin", "test_kiwoom_login")
                print(f"결과: {result5}")
                
                # 키움증권 상태 확인
                result6 = ipc.answer("api", "get_kiwoom_status")
                print(f"키움증권 상태: {result6}")
            except Exception as e:
                print(f"키움증권 테스트 중 오류 발생: {str(e)}")
                print("키움증권 API가 설치되어 있지 않거나 PyQt5가 설치되지 않았을 수 있습니다.")
            
        except Exception as e:
            logging.error(f"테스트 중 오류 발생: {e}")
        finally:
            # 정리
            logging.debug("자원 정리 중...")
            ipc.cleanup()
            
            print("모든 테스트 완료!")
    
    # 테스트 실행
    test_cross_communication()


