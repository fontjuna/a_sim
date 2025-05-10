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

# ipc_manager.py 모듈 시작 부분에 추가

def process_worker_wrapper(name, cls, shared_registry, shared_queues):
    """프로세스 워커 함수"""
    import os, sys, logging
    pid = os.getpid()
    print(f"Process {pid}: Started for {name}")
    sys.stdout.flush()
    
    try:
        # IPCManager 인스턴스 얻기
        from ipc_manager import IPCManager
        ipc = IPCManager.get_instance(shared_registry, shared_queues)
        
        # 클래스에서 인스턴스 생성
        obj = cls()
        obj.ipc = ipc
        
        # 통신 큐 가져오기
        req_queue = ipc._get_request_queue(name)
        resp_queue = ipc._get_response_queue(name)
        
        # 워커 루프 실행
        ipc._worker_loop(name, obj, req_queue, resp_queue, True)
    except Exception as e:
        logging.error(f"Process {pid}: Error in {name}: {e}", exc_info=True)

"""
프로세스 간 통신 관리 모듈
초고속 대용량 데이터 전송을 지원하는 IPC 매니저
"""
import pickle
import zlib
import queue
import logging
import threading
import multiprocessing
import time
import uuid
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# 전역 매니저 (프로세스 간 공유 객체용)
_global_manager = None

def get_manager():
    """프로세스 간 공유 객체 관리자 가져오기"""
    global _global_manager
    if _global_manager is None:
        _global_manager = multiprocessing.Manager()
    return _global_manager

def process_worker(name, cls, shared_registry, shared_queues):
    """프로세스 워커 함수"""
    pid = os.getpid()
    print(f"Process {pid}: Started for {name}")
    
    try:
        # IPC 매니저 인스턴스 가져오기
        ipc = IPCManager(shared_registry, shared_queues)
        
        # 클래스에서 인스턴스 생성
        obj = cls()
        obj.ipc = ipc
        
        # 요청/응답 큐 가져오기
        req_queue = shared_queues.get(f"{name}_req")
        resp_queue = shared_queues.get(f"{name}_resp")
        
        if req_queue is None or resp_queue is None:
            print(f"Process {pid}: Queue not found for {name}")
            return
            
        print(f"Process {pid}: Worker loop starting for {name}")
        
        # 워커 루프 실행
        running = True
        while running:
            try:
                # 요청 대기
                try:
                    request = req_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # 종료 요청 확인
                if request.get('command') == '_terminate_':
                    print(f"Process {pid}: Terminating {name}")
                    running = False
                    break
                
                # 요청 처리
                func_name = request.get('function', '')
                args = request.get('args', [])
                kwargs = request.get('kwargs', {})
                msg_id = request.get('id', '')
                
                print(f"Process {pid}: Processing {func_name} for {name}")
                
                try:
                    # 함수 호출
                    if not hasattr(obj, func_name):
                        raise AttributeError(f"Object {name} has no attribute '{func_name}'")
                    
                    func = getattr(obj, func_name)
                    result = func(*args, **kwargs)
                    
                    # 결과 직렬화 확인
                    try:
                        pickle.dumps(result)
                    except Exception as e:
                        result = f"Error: Result cannot be pickled - {str(e)}"
                    
                    # 응답 전송
                    response = {'result': result, 'error': None, 'id': msg_id}
                    resp_queue.put(response)
                    
                except Exception as e:
                    # 오류 응답 전송
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    response = {'result': None, 'error': error_msg, 'id': msg_id}
                    resp_queue.put(response)
                    print(f"Process {pid}: Error in {func_name}: {error_msg}")
            
            except Exception as e:
                print(f"Process {pid}: Error in worker loop: {str(e)}")
                time.sleep(0.1)
        
        print(f"Process {pid}: Worker loop ended for {name}")
        
    except Exception as e:
        print(f"Process {pid}: Fatal error in {name}: {str(e)}")


class IPCManager:
    """프로세스 간 통신 관리 클래스"""
    
    def __init__(self, shared_registry=None, shared_queues=None):
        """초기화"""
        self.pid = os.getpid()
        
        # 공유 레지스트리 (프로세스 간 객체 등록 정보)
        if shared_registry is None:
            self.shared_registry = get_manager().dict()
        else:
            self.shared_registry = shared_registry
            
        # 공유 큐 (프로세스 간 메시지 전달)
        if shared_queues is None:
            self.shared_queues = get_manager().dict()
        else:
            self.shared_queues = shared_queues
            
        # 로컬 객체 참조
        self.objects = {}  # name -> (obj, type)
        
        # 워커 관리
        self.workers = {}  # name -> worker
        self.running = {}  # name -> running flag
        
        # 콜백 관리
        self.callbacks = {}  # msg_id -> callback
        self.timeouts = {}  # msg_id -> timeout
        
        # 청크 버퍼 (대용량 데이터용)
        self.chunks = {}  # msg_id -> chunks
        
        # 응답 체커 스레드
        self.checker_thread = None
        self.checker_running = False
        self._start_checker()
    
    def register(self, name, obj, type_=None, start=False, shared=False):
        """
        객체 등록
        
        Args:
            name: 등록할 객체 이름
            obj: 등록할 객체 (프로세스의 경우 클래스 또는 인스턴스)
            type_: 등록 유형 (None=메인스레드, 'thread'=멀티스레드, 'process'=멀티프로세스)
            start: 등록 후 즉시 시작 여부
            shared: 스레드 공유 여부 (지금은 무시)
            
        Returns:
            등록된 객체
        """
        print(f"PID {self.pid}: Registering {name} as {type_}")
        
        if type_ == 'process':
            # 클래스 또는 인스턴스에서 클래스 추출
            cls = obj if isinstance(obj, type) else obj.__class__
            self.objects[name] = (cls, type_)
            
            # 공유 레지스트리에 등록
            self.shared_registry[name] = {'pid': self.pid, 'type': type_}
            
            # 공유 큐 생성
            if f"{name}_req" not in self.shared_queues:
                self.shared_queues[f"{name}_req"] = get_manager().Queue()
            if f"{name}_resp" not in self.shared_queues:
                self.shared_queues[f"{name}_resp"] = get_manager().Queue()
        else:
            # 현재는 프로세스만 처리
            raise ValueError(f"Only 'process' type is supported, got: {type_}")
        
        # 실행 상태 초기화
        self.running[name] = False
        
        # 즉시 시작 옵션
        if start:
            self.start(name)
            
        return obj
    
    def start(self, name):
        """
        객체 시작
        
        Args:
            name: 시작할 객체 이름
        """
        if name not in self.objects:
            raise ValueError(f"Object {name} not registered")
            
        if self.running.get(name, False):
            print(f"PID {self.pid}: Object {name} already running")
            return
            
        obj, type_ = self.objects[name]
        
        if type_ == 'process':
            # 프로세스 생성 및 시작
            process = multiprocessing.Process(
                target=process_worker,
                args=(name, obj, self.shared_registry, self.shared_queues),
                daemon=True
            )
            
            try:
                process.start()
                self.workers[name] = process
                self.running[name] = True
                print(f"PID {self.pid}: Started process {name} (PID: {process.pid})")
            except Exception as e:
                print(f"PID {self.pid}: Failed to start process {name}: {str(e)}")
                raise
        else:
            raise ValueError(f"Only 'process' type is supported, got: {type_}")
    
    def stop(self, name):
        """
        객체 중지
        
        Args:
            name: 중지할 객체 이름
        """
        if name not in self.objects:
            raise ValueError(f"Object {name} not registered")
            
        if not self.running.get(name, False):
            print(f"PID {self.pid}: Object {name} not running")
            return
            
        obj, type_ = self.objects[name]
        
        if type_ == 'process':
            # 종료 요청 전송
            req_queue = self.shared_queues.get(f"{name}_req")
            if req_queue:
                req_queue.put({'command': '_terminate_', 'id': str(uuid.uuid4())})
            
            # 프로세스 종료 대기
            process = self.workers.get(name)
            if process and process.is_alive():
                process.join(timeout=3.0)
                if process.is_alive():
                    print(f"PID {self.pid}: Force terminating {name}")
                    process.terminate()
            
            self.running[name] = False
            print(f"PID {self.pid}: Stopped {name}")
        else:
            raise ValueError(f"Only 'process' type is supported, got: {type_}")
    
    def work(self, name, function, *args, **kwargs):
        """
        비동기 작업 요청
        
        Args:
            name: 대상 객체 이름
            function: 호출할 함수 이름
            *args: 위치 인자
            **kwargs: 키워드 인자
        """
        # 대상 객체 확인
        if name not in self.shared_registry:
            raise ValueError(f"Object {name} not registered")
            
        # 요청 메시지 생성
        msg_id = str(uuid.uuid4())
        request = {
            'function': function,
            'args': args,
            'kwargs': kwargs,
            'id': msg_id
        }
        
        # 요청 큐 가져오기
        req_queue = self.shared_queues.get(f"{name}_req")
        if req_queue is None:
            raise RuntimeError(f"Request queue for {name} not found")
            
        # 요청 전송
        req_queue.put(request)
        print(f"PID {self.pid}: Sent work request to {name}: {function}")
    
    def answer(self, name, function, *args, callback=None, **kwargs):
        """
        동기/비동기 응답 요청
        
        Args:
            name: 대상 객체 이름
            function: 호출할 함수 이름
            *args: 위치 인자
            callback: 비동기 콜백 함수 (없으면 동기 호출)
            **kwargs: 키워드 인자
            
        Returns:
            함수 호출 결과 (동기 호출 시)
        """
        # 대상 객체 확인
        if name not in self.shared_registry:
            raise ValueError(f"Object {name} not registered")
            
        # 요청 메시지 생성
        msg_id = str(uuid.uuid4())
        request = {
            'function': function,
            'args': args,
            'kwargs': kwargs,
            'id': msg_id
        }
        
        # 요청 큐 가져오기
        req_queue = self.shared_queues.get(f"{name}_req")
        if req_queue is None:
            raise RuntimeError(f"Request queue for {name} not found")
            
        # 응답 큐 가져오기
        resp_queue = self.shared_queues.get(f"{name}_resp")
        if resp_queue is None:
            raise RuntimeError(f"Response queue for {name} not found")
            
        # 비동기 호출 (콜백 있음)
        if callback:
            # 콜백 등록
            self.callbacks[msg_id] = callback
            self.timeouts[msg_id] = time.time() + 30.0  # 30초 타임아웃
            
            # 요청 전송
            req_queue.put(request)
            print(f"PID {self.pid}: Sent async request to {name}: {function}")
            return None
            
        # 동기 호출 (응답 대기)
        req_queue.put(request)
        print(f"PID {self.pid}: Sent sync request to {name}: {function}")
        
        # 응답 대기
        timeout = 30.0  # 30초 타임아웃
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 응답 확인
                response = resp_queue.get(timeout=0.1)
                
                # 응답 ID 확인
                if response.get('id') == msg_id:
                    # 오류 확인
                    error = response.get('error')
                    if error:
                        raise RuntimeError(f"Error from {name}.{function}: {error}")
                    
                    # 결과 반환
                    return response.get('result')
                else:
                    # 다른 요청의 응답이면 다시 큐에 넣음
                    resp_queue.put(response)
            except queue.Empty:
                continue
                
        # 타임아웃
        raise TimeoutError(f"Timeout waiting for response from {name}.{function}")
    
    def _start_checker(self):
        """응답 체커 스레드 시작"""
        if not self.checker_running:
            self.checker_running = True
            self.checker_thread = threading.Thread(
                target=self._check_responses,
                daemon=True
            )
            self.checker_thread.start()
    
    def _check_responses(self):
        """비동기 응답 체크 루프"""
        while self.checker_running:
            try:
                # 타임아웃 체크
                current_time = time.time()
                for msg_id, timeout_time in list(self.timeouts.items()):
                    if current_time > timeout_time:
                        callback = self.callbacks.pop(msg_id, None)
                        self.timeouts.pop(msg_id, None)
                        if callback:
                            try:
                                callback(None, "Timeout")
                            except Exception as e:
                                print(f"PID {self.pid}: Callback error: {str(e)}")
                
                # 모든, 객체의 응답 확인
                for name, info in list(self.shared_registry.items()):
                    # 응답 큐 가져오기
                    resp_queue = self.shared_queues.get(f"{name}_resp")
                    if resp_queue is None:
                        continue
                        
                    # 응답 확인
                    try:
                        response = resp_queue.get(block=False)
                    except queue.Empty:
                        continue
                        
                    # 응답 처리
                    msg_id = response.get('id', '')
                    if msg_id in self.callbacks:
                        callback = self.callbacks.pop(msg_id)
                        self.timeouts.pop(msg_id, None)
                        
                        # 콜백 실행
                        try:
                            error = response.get('error')
                            if error:
                                callback(None, error)
                            else:
                                callback(response.get('result'))
                        except Exception as e:
                            print(f"PID {self.pid}: Callback error: {str(e)}")
                    else:
                        # 콜백이 없으면 다시 큐에 넣음
                        resp_queue.put(response)
            except Exception as e:
                print(f"PID {self.pid}: Checker error: {str(e)}")
                
            # 잠시 대기
            time.sleep(0.01)
    
    def cleanup(self):
        """모든 리소스 정리"""
        print(f"PID {self.pid}: Cleaning up resources")
        
        # 모든 워커 종료
        for name in list(self.running.keys()):
            if self.running[name]:
                try:
                    self.stop(name)
                except Exception as e:
                    print(f"PID {self.pid}: Error stopping {name}: {str(e)}")
        
        # 체커 스레드 종료
        self.checker_running = False
        if self.checker_thread and self.checker_thread.is_alive():
            try:
                self.checker_thread.join(timeout=1.0)
            except Exception as e:
                print(f"PID {self.pid}: Error stopping checker thread: {str(e)}")
        
        print(f"PID {self.pid}: Cleanup complete")


# 글로벌 인스턴스
ipc = None

# 사용 예시
if __name__ == "__main__":
    # IPC 매니저 생성
    ipc = IPCManager()
    
    # 테스트 클래스
    class TestProcess:
        def __init__(self):
            self.ipc = None
            
        def echo(self, message):
            print(f"Echo: {message}")
            return f"Echo: {message}"
            
    # 프로세스 등록 및 시작
    ipc.register("test", TestProcess(), "process", start=True)
    
    # 잠시 대기
    time.sleep(1)
    
    # 동기 호출
    result = ipc.answer("test", "echo", "Hello, World!")
    print(f"Result: {result}")
    
    # 비동기 호출
    def on_result(result, error=None):
        if error:
            print(f"Error: {error}")
        else:
            print(f"Async result: {result}")
            
    ipc.answer("test", "echo", "Async Hello!", callback=on_result)
    
    # 대기
    time.sleep(1)
    
    # 정리
    ipc.cleanup()

