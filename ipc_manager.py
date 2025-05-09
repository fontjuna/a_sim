# ipc_manager.py
import pickle
import msgpack
import time
import uuid
import threading
import multiprocessing
from multiprocessing import shared_memory
import traceback
import queue
import signal
import sys
import os
from typing import Any, Dict, Tuple, List, Callable, Optional, Union

# 전역 IPC 인스턴스
_ipc_instance = None

class IPCError(Exception):
    """IPC 관련 예외 클래스"""
    pass

class IPCTimeoutError(IPCError):
    """IPC 통신 타임아웃 예외 클래스"""
    pass

class IPCMessage:
    """IPC 메시지 포맷 클래스"""
    
    def __init__(self, 
                msg_id: str = None, 
                src: str = None, 
                dst: str = None, 
                func: str = None, 
                args: tuple = None, 
                kwargs: dict = None, 
                result: Any = None, 
                error: str = None, 
                is_async: bool = False, 
                callback_id: str = None,
                shared_refs: list = None):
        """
        IPC 메시지 초기화
        
        Args:
            msg_id: 메시지 고유 ID
            src: 발신 컴포넌트 이름
            dst: 수신 컴포넌트 이름
            func: 호출할 함수명
            args: 함수 위치 인자
            kwargs: 함수 키워드 인자
            result: 반환 결과
            error: 오류 메시지
            is_async: 비동기 여부
            callback_id: 콜백 ID
            shared_refs: 공유 메모리 참조 ID 목록
        """
        self.msg_id = msg_id or str(uuid.uuid4())
        self.src = src
        self.dst = dst
        self.func = func
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.result = result
        self.error = error
        self.is_async = is_async
        self.callback_id = callback_id
        self.timestamp = time.time()
        self.shared_refs = shared_refs or []
    
    def to_dict(self) -> dict:
        """메시지를 딕셔너리로 변환"""
        return {
            'msg_id': self.msg_id,
            'src': self.src,
            'dst': self.dst,
            'func': self.func,
            'args': self.args,
            'kwargs': self.kwargs,
            'result': self.result,
            'error': self.error,
            'is_async': self.is_async,
            'callback_id': self.callback_id,
            'timestamp': self.timestamp,
            'shared_refs': self.shared_refs
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'IPCMessage':
        """딕셔너리에서 메시지 객체 생성"""
        msg = cls()
        msg.msg_id = data.get('msg_id')
        msg.src = data.get('src')
        msg.dst = data.get('dst')
        msg.func = data.get('func')
        msg.args = data.get('args', ())
        msg.kwargs = data.get('kwargs', {})
        msg.result = data.get('result')
        msg.error = data.get('error')
        msg.is_async = data.get('is_async', False)
        msg.callback_id = data.get('callback_id')
        msg.timestamp = data.get('timestamp', time.time())
        msg.shared_refs = data.get('shared_refs', [])
        return msg
        
    def serialize(self) -> bytes:
        """메시지 직렬화"""
        try:
            return msgpack.packb(self.to_dict(), use_bin_type=True)
        except (TypeError, msgpack.exceptions.PackException):
            # msgpack으로 직렬화 실패시 pickle 사용 (더 느리지만 호환성 높음)
            return pickle.dumps(self.to_dict())
    
    @classmethod
    def deserialize(cls, data: bytes) -> 'IPCMessage':
        """메시지 역직렬화"""
        try:
            return cls.from_dict(msgpack.unpackb(data, raw=False))
        except (msgpack.exceptions.UnpackException, ValueError):
            # msgpack으로 역직렬화 실패시 pickle 사용
            return cls.from_dict(pickle.loads(data))
        
class SharedMemoryManager:
    """대용량 데이터 공유 메모리 관리 클래스"""
    
    def __init__(self):
        self.memories = {}  # 공유 메모리 객체 저장소
        self.lock = threading.Lock()  # 스레드 안전 락
        self.max_size_for_direct = 1024 * 100  # 직접 전송 최대 크기 (100KB)
    
    def put_data(self, data: Any) -> Tuple[str, bool]:
        """
        데이터를 공유 메모리에 저장 또는 직접 전송
        
        Returns:
            (데이터 ID 또는 직렬화된 데이터, 공유메모리 사용 여부)
        """
        # 데이터 직렬화
        try:
            serialized = msgpack.packb(data, use_bin_type=True)
        except (TypeError, msgpack.exceptions.PackException):
            serialized = pickle.dumps(data)
        
        # 작은 데이터는 직접 반환
        if len(serialized) <= self.max_size_for_direct:
            return serialized, False
        
        # 큰 데이터는 공유 메모리 사용
        data_id = str(uuid.uuid4())
        
        try:
            shm = shared_memory.SharedMemory(
                name=data_id, 
                create=True, 
                size=len(serialized) + 4
            )
            
            # 데이터 길이를 처음 4바이트에 저장
            length_bytes = len(serialized).to_bytes(4, byteorder='little')
            shm.buf[:4] = length_bytes
            
            # 실제 데이터 복사
            shm.buf[4:4+len(serialized)] = serialized
            
            with self.lock:
                self.memories[data_id] = shm
                
            return data_id, True
            
        except Exception as e:
            raise IPCError(f"공유 메모리 할당 실패: {str(e)}")
    
    def get_data(self, data_ref: Union[str, bytes], is_shared: bool) -> Any:
        """공유 메모리 또는 직렬화 데이터에서 데이터 가져오기"""
        if not is_shared:
            # 직접 전송된 데이터 역직렬화
            try:
                return msgpack.unpackb(data_ref, raw=False)
            except (msgpack.exceptions.UnpackException, ValueError):
                return pickle.loads(data_ref)
        
        # 공유 메모리에서 데이터 가져오기
        data_id = data_ref
        try:
            shm = shared_memory.SharedMemory(name=data_id, create=False)
            
            # 데이터 길이 읽기
            length = int.from_bytes(shm.buf[:4], byteorder='little')
            
            # 데이터 읽기
            serialized = bytes(shm.buf[4:4+length])
            
            # 역직렬화
            try:
                data = msgpack.unpackb(serialized, raw=False)
            except (msgpack.exceptions.UnpackException, ValueError):
                data = pickle.loads(serialized)
                
            return data
            
        except Exception as e:
            raise IPCError(f"공유 메모리 데이터 접근 실패: {str(e)}")
    
    def free_memory(self, data_id: str) -> None:
        """공유 메모리 해제"""
        with self.lock:
            if data_id in self.memories:
                try:
                    self.memories[data_id].close()
                    self.memories[data_id].unlink()
                    del self.memories[data_id]
                except Exception as e:
                    print(f"공유 메모리 해제 실패: {str(e)}")
    
    def cleanup(self) -> None:
        """모든 공유 메모리 해제"""
        with self.lock:
            for data_id, shm in list(self.memories.items()):
                try:
                    shm.close()
                    shm.unlink()
                except Exception:
                    pass
            self.memories.clear()

class IPCComponent:
    """통신 컴포넌트 정보를 저장하는 클래스"""
    
    def __init__(self, name: str, cls: object, comp_type: Optional[str] = None):
        """
        통신 컴포넌트 초기화
        
        Args:
            name: 컴포넌트 이름
            cls: 컴포넌트 클래스 객체
            comp_type: 컴포넌트 타입 (None=메인스레드, 'thread'=스레드, 'process'=프로세스)
        """
        self.name = name
        self.cls = cls
        self.type = comp_type
        self.parent_conn = None  # 부모 연결
        self.child_conn = None   # 자식 연결
        self.is_running = False  # 실행 상태
        self.callbacks = {}      # 비동기 콜백 저장소
        self.callback_lock = threading.Lock()  # 콜백 딕셔너리 락
        self.shared_data = {}    # 공유 메모리 데이터
        self.msg_queue = None    # 메시지 큐
        self.listener = None     # 리스너 스레드
        self.process = None      # 프로세스 객체 (프로세스인 경우)

class IPCManagerProxy:
    """자식 프로세스에서 사용하는 IPC 프록시 클래스"""
    
    def __init__(self, conn, name: str):
        """
        IPC 프록시 초기화
        
        Args:
            conn: 부모 프로세스와의 연결 파이프
            name: 현재 프로세스 이름
        """
        self.conn = conn
        self.name = name
        self.shared_mem_manager = SharedMemoryManager()
        self.callbacks = {}
        self.callback_lock = threading.Lock()
        self.is_running = True
        self.listener_thread = None

        # 클래스 인스턴스 저장소 - 이름으로 인스턴스 매핑
        self._instances = {}
        
        # 리스너 스레드 시작
        self._start_listener()
    
    def _start_listener(self):
        """메시지 리스너 스레드 시작"""
        self.listener_thread = threading.Thread(
            target=self._listen_for_messages,
            daemon=True
        )
        self.listener_thread.start()
    
    def _listen_for_messages(self):
        """메시지 리스너 함수"""
        while self.is_running:
            try:
                if self.conn.poll(0.01):  # 10ms 타임아웃으로 폴링
                    # 메시지 수신
                    data = self.conn.recv()
                    msg = IPCMessage.deserialize(data)
                    
                    # 종료 메시지 확인
                    if msg.func == "__stop__":
                        self.is_running = False
                        break
                    
                    # 비동기 응답 처리
                    if msg.callback_id:
                        with self.callback_lock:
                            if msg.callback_id in self.callbacks:
                                callback_func = self.callbacks[msg.callback_id]
                                # 콜백 함수 호출
                                try:
                                    # 공유 메모리 결과 처리
                                    if isinstance(msg.result, tuple) and len(msg.result) == 2 and msg.result[1] is True:
                                        result = self.shared_mem_manager.get_data(msg.result[0], True)
                                    else:
                                        result = msg.result
                                    
                                    callback_func(result)
                                except Exception as e:
                                    print(f"콜백 함수 실행 오류: {str(e)}")
                                finally:
                                    # 일회성 콜백은 삭제
                                    del self.callbacks[msg.callback_id]
                    
                    # 함수 호출 요청 처리
                    elif msg.func:
                        self._handle_function_call(msg)
            except Exception as e:
                print(f"리스너 스레드 오류: {str(e)}")
            
            # CPU 과부하 방지
            time.sleep(0.001)
    
    def register_instance(self, name: str, instance: object) -> None:
        """클래스 인스턴스 등록"""
        self._instances[name] = instance
    
    def _handle_function_call(self, msg: IPCMessage):
        """함수 호출 처리"""
        result = None
        error = None
        
        try:
            obj_name = msg.dst
            func_name = msg.func
            
            # 종료 메시지 처리
            if func_name == "__stop__":
                self.is_running = False
                return
                
            # 호출할 인스턴스 가져오기
            if obj_name != self.name or obj_name not in self._instances:
                # 인스턴스 등록이 안된 경우 동적 생성 시도
                try:
                    # 모듈 이름은 인스턴스 이름과 동일하다고 가정
                    module_name = obj_name
                    # 모듈 동적 임포트
                    module = __import__(module_name)
                    # 클래스 이름은 CamelCase로 변환
                    class_name = ''.join(word.capitalize() for word in obj_name.split('_'))
                    # 클래스 가져오기
                    cls = getattr(module, class_name)
                    # 인스턴스 생성 및 등록
                    instance = cls()
                    self._instances[obj_name] = instance
                except Exception as e:
                    error = f"인스턴스 생성 실패: {str(e)}"
                    raise
            
            # 인스턴스 가져오기
            instance = self._instances.get(obj_name)
            if not instance:
                raise IPCError(f"인스턴스를 찾을 수 없음: {obj_name}")
            
            # 함수 가져오기
            func = getattr(instance, func_name)
            
            # 인자 처리
            processed_args = []
            for arg in msg.args:
                if isinstance(arg, tuple) and len(arg) == 2 and arg[1] is True:
                    # 공유 메모리 데이터 가져오기
                    processed_args.append(self.shared_mem_manager.get_data(arg[0], True))
                else:
                    processed_args.append(arg)
            
            processed_kwargs = {}
            for key, value in msg.kwargs.items():
                if isinstance(value, tuple) and len(value) == 2 and value[1] is True:
                    # 공유 메모리 데이터 가져오기
                    processed_kwargs[key] = self.shared_mem_manager.get_data(value[0], True)
                else:
                    processed_kwargs[key] = value
            
            # 함수 실행
            result = func(*processed_args, **processed_kwargs)
        except Exception as e:
            error = f"{str(e)}\n{traceback.format_exc()}"
    
    def work(self, name: str, func: str, args: tuple = None, kwargs: dict = None) -> None:
        """
        비반환 작업 실행 (결과를 기다리지 않음)
        
        Args:
            name: 대상 컴포넌트 이름
            func: 실행할 함수 이름
            args: 함수 위치 인자
            kwargs: 함수 키워드 인자
        """
        # 인자 처리 (큰 데이터는 공유 메모리 사용)
        processed_args = []
        shared_refs = []
        
        if args:
            for arg in args:
                data_ref, is_shared = self.shared_mem_manager.put_data(arg)
                if is_shared:
                    processed_args.append((data_ref, True))
                    shared_refs.append(data_ref)
                else:
                    processed_args.append(arg)
        
        processed_kwargs = {}
        if kwargs:
            for key, value in kwargs.items():
                data_ref, is_shared = self.shared_mem_manager.put_data(value)
                if is_shared:
                    processed_kwargs[key] = (data_ref, True)
                    shared_refs.append(data_ref)
                else:
                    processed_kwargs[key] = value
        
        # 메시지 생성
        msg = IPCMessage(
            src=self.name,
            dst=name,
            func=func,
            args=tuple(processed_args),
            kwargs=processed_kwargs,
            is_async=True,
            shared_refs=shared_refs
        )
        
        # 메시지 전송
        self.conn.send(msg.serialize())
    
    def answer(self, name: str, func: str, args: tuple = None, 
              kwargs: dict = None, callback: Callable = None) -> Any:
        """
        동기/비동기 작업 실행
        
        Args:
            name: 대상 컴포넌트 이름
            func: 실행할 함수 이름
            args: 함수 위치 인자
            kwargs: 함수 키워드 인자
            callback: 비동기 콜백 함수 (None인 경우 동기 호출)
            
        Returns:
            함수 실행 결과 (동기 호출인 경우)
        """
        # 인자 처리 (큰 데이터는 공유 메모리 사용)
        processed_args = []
        shared_refs = []
        
        if args:
            for arg in args:
                data_ref, is_shared = self.shared_mem_manager.put_data(arg)
                if is_shared:
                    processed_args.append((data_ref, True))
                    shared_refs.append(data_ref)
                else:
                    processed_args.append(arg)
        
        processed_kwargs = {}
        if kwargs:
            for key, value in kwargs.items():
                data_ref, is_shared = self.shared_mem_manager.put_data(value)
                if is_shared:
                    processed_kwargs[key] = (data_ref, True)
                    shared_refs.append(data_ref)
                else:
                    processed_kwargs[key] = value
        
        # 메시지 ID 생성
        msg_id = f"{os.getpid()}-{threading.get_ident()}-{time.time()}"
        
        # 메시지 생성
        msg = IPCMessage(
            msg_id=msg_id,
            src=self.name,
            dst=name,
            func=func,
            args=tuple(processed_args),
            kwargs=processed_kwargs,
            is_async=callback is not None,
            shared_refs=shared_refs
        )
        
        # 비동기 호출 (콜백 사용)
        if callback:
            with self.callback_lock:
                self.callbacks[msg_id] = callback
            
            self.conn.send(msg.serialize())
            return None
        
        # 동기 호출 (결과 대기)
        self.conn.send(msg.serialize())
        
        # 응답 대기
        start_time = time.time()
        timeout = 5.0  # 기본 타임아웃 5초
        
        while time.time() - start_time < timeout:
            if self.conn.poll(0.001):  # 1ms 타임아웃으로 폴링
                # 응답 수신
                data = self.conn.recv()
                response = IPCMessage.deserialize(data)
                
                # 콜백 ID 확인
                if response.callback_id == msg_id:
                    # 오류 처리
                    if response.error:
                        raise IPCError(f"원격 함수 호출 실패: {response.error}")
                    
                    # 공유 메모리 결과 처리
                    if isinstance(response.result, tuple) and len(response.result) == 2 and response.result[1] is True:
                        result = self.shared_mem_manager.get_data(response.result[0], True)
                        # 공유 메모리 해제
                        self.shared_mem_manager.free_memory(response.result[0])
                    else:
                        result = response.result
                    
                    # 다른 공유 메모리 참조 해제
                    for ref in response.shared_refs:
                        if isinstance(response.result, tuple) and len(response.result) == 2:
                            if ref != response.result[0]:
                                self.shared_mem_manager.free_memory(ref)
                        else:
                            self.shared_mem_manager.free_memory(ref)
                    
                    return result
            
            # CPU 과부하 방지
            time.sleep(0.001)
        
        raise IPCTimeoutError(f"함수 호출 타임아웃: {name}.{func}")
    
    def cleanup(self):
        """리소스 정리"""
        self.is_running = False
        self.shared_mem_manager.cleanup()

class IPCManager:
    """다자간 초고속 대용량 통신 관리자 클래스"""
    
    def __init__(self, timeout: float = 5.0):
        """
        IPC 관리자 초기화
        
        Args:
            timeout: 기본 통신 타임아웃 (초)
        """
        self.components = {}  # 등록된 컴포넌트 저장소
        self.shared_mem_manager = SharedMemoryManager()  # 공유 메모리 관리자
        self.timeout = timeout  # 기본 타임아웃
        self.msg_count = 0  # 메시지 카운터
        self.lock = threading.Lock()  # 스레드 안전 락
        self.is_running = True  # 전체 실행 상태
        
        # 시그널 핸들러 등록 (프로세스 종료시 정리 작업)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 컴포넌트 클래스 저장소
        self.component_classes = {}
        
        # 메인 컴포넌트 (자기 자신) 등록
        self._register_self()
        
        # 전역 IPC 인스턴스 설정
        global _ipc_instance
        _ipc_instance = self
    
    def _register_self(self):
        """자기 자신을 메인 컴포넌트로 등록"""
        self_component = IPCComponent("ipc_manager", self, None)
        self_component.is_running = True
        self.components["ipc_manager"] = self_component
        self.component_classes["ipc_manager"] = self
    
    def _signal_handler(self, sig, frame):
        """시그널 핸들러"""
        self.cleanup()
        sys.exit(0)
    
    def register(self, name: str, cls: object, comp_type: Optional[str] = None) -> None:
        """
        컴포넌트 등록
        
        Args:
            name: 컴포넌트 이름
            cls: 컴포넌트 클래스 객체
            comp_type: 컴포넌트 타입 (None=메인스레드, 'thread'=스레드, 'process'=프로세스)
        """
        if name in self.components:
            raise IPCError(f"컴포넌트 이름 '{name}'이 이미 등록되어 있습니다.")
        
        # 허용된 타입 확인
        if comp_type not in (None, 'thread', 'process'):
            raise IPCError(f"지원하지 않는 컴포넌트 타입: {comp_type}")
        
        component = IPCComponent(name, cls, comp_type)
        
        # 컴포넌트 클래스 저장 - 프로세스인 경우 클래스 자체를 저장하지 않음
        if comp_type != 'process':
            self.component_classes[name] = cls
        
        # 통신 파이프 생성
        if comp_type:  # 스레드나 프로세스인 경우
            parent_conn, child_conn = multiprocessing.Pipe(duplex=True)
            component.parent_conn = parent_conn
            component.child_conn = child_conn
            
            # 메시지 큐 생성 (비동기 통신용)
            component.msg_queue = queue.Queue() if comp_type == 'thread' else multiprocessing.Queue()
        else:
            # 메인 스레드인 경우 컴포넌트 실행 상태 설정
            component.is_running = True

        # 컴포넌트 등록
        self.components[name] = component
        
        # 메인 스레드가 아닌 경우 리스너 시작
        if comp_type == 'thread':
            self._start_thread_listener(name)
    
    def _start_thread_listener(self, name: str) -> None:
        """스레드 컴포넌트의 메시지 리스너 시작"""
        component = self.components[name]
        
        # 스레드 리스너 생성
        component.listener = threading.Thread(
            target=self._listen_thread,
            args=(name,),
            daemon=True
        )
        component.listener.start()
    
    def _listen_thread(self, name: str) -> None:
        """스레드 메시지 리스너"""
        component = self.components[name]
        
        while self.is_running and component.is_running:
            try:
                if component.parent_conn.poll(0.01):  # 10ms 타임아웃으로 폴링
                    # 메시지 수신
                    data = component.parent_conn.recv()
                    msg = IPCMessage.deserialize(data)
                    
                    # 비동기 응답 처리
                    if msg.callback_id:
                        with component.callback_lock:
                            if msg.callback_id in component.callbacks:
                                callback_func = component.callbacks[msg.callback_id]
                                # 콜백 함수 호출
                                try:
                                    callback_func(msg.result)
                                except Exception as e:
                                    print(f"콜백 함수 실행 오류: {str(e)}")
                                finally:
                                    # 일회성 콜백은 삭제
                                    del component.callbacks[msg.callback_id]
                    
                    # 함수 호출 요청 처리
                    elif msg.func:
                        self._handle_function_call(msg)
            except Exception as e:
                print(f"리스너 스레드 오류 ({name}): {str(e)}")
            
            # CPU 과부하 방지
            time.sleep(0.001)
    
    def _process_worker(self, name: str, conn, cls_module, cls_name) -> None:
        """프로세스 워커 함수"""
        # 프로세스의 시그널 핸들러 설정
        def process_signal_handler(sig, frame):
            sys.exit(0)
        
        signal.signal(signal.SIGINT, process_signal_handler)
        signal.signal(signal.SIGTERM, process_signal_handler)
        
        try:
            # 모듈에서 클래스 동적 로드
            module = __import__(cls_module, fromlist=[cls_name])
            cls = getattr(module, cls_name)
            
            # 컴포넌트 객체 생성
            component_obj = cls()
            
            # 전역 변수 설정
            global _component_class
            _component_class = component_obj
            
            # 프록시 생성 및 전역 설정
            global _ipc_instance
            _ipc_instance = IPCManagerProxy(conn, name)
            
            # 메시지 루프 (프로세스가 종료될 때까지 실행)
            while _ipc_instance.is_running:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"프로세스 워커 오류 ({name}): {str(e)}\n{traceback.format_exc()}")
            sys.exit(1)
    
    def _handle_function_call(self, msg: IPCMessage) -> None:
        """함수 호출 처리"""
        result = None
        error = None
        
        try:
            # 목적지 컴포넌트 가져오기
            component = self.components[msg.dst]
            
            # 함수 호출
            func = getattr(component.cls, msg.func)
            
            # 공유 메모리 참조 처리
            processed_args = []
            for arg in msg.args:
                if isinstance(arg, tuple) and len(arg) == 2 and arg[1] is True:
                    # 공유 메모리 데이터 가져오기
                    processed_args.append(self.shared_mem_manager.get_data(arg[0], True))
                else:
                    processed_args.append(arg)
            
            processed_kwargs = {}
            for key, value in msg.kwargs.items():
                if isinstance(value, tuple) and len(value) == 2 and value[1] is True:
                    # 공유 메모리 데이터 가져오기
                    processed_kwargs[key] = self.shared_mem_manager.get_data(value[0], True)
                else:
                    processed_kwargs[key] = value
            
            # 함수 실행
            result = func(*processed_args, **processed_kwargs)
        except Exception as e:
            error = f"{str(e)}\n{traceback.format_exc()}"
        
        # 공유 메모리 참조 해제
        for ref in msg.shared_refs:
            self.shared_mem_manager.free_memory(ref)
        
        # 응답 메시지 생성 (비동기가 아닌 경우만)
        if not msg.is_async:
            response = IPCMessage(
                msg_id=str(uuid.uuid4()),
                src=msg.dst,
                dst=msg.src,
                result=result,
                error=error,
                callback_id=msg.msg_id
            )
            
            # 결과가 큰 경우 공유 메모리 사용
            if result is not None:
                data_ref, is_shared = self.shared_mem_manager.put_data(result)
                if is_shared:
                    response.result = (data_ref, True)
                    response.shared_refs.append(data_ref)
                else:
                    response.result = result
            
            # 응답 전송
            src_component = self.components[msg.src]
            if src_component.parent_conn:  # 스레드나 프로세스인 경우
                try:
                    src_component.parent_conn.send(response.serialize())
                except Exception as e:
                    print(f"응답 전송 실패: {str(e)}")   
                    
    def start(self, name: str) -> None:
        """컴포넌트 시작"""
        if name not in self.components:
            raise IPCError(f"등록되지 않은 컴포넌트: {name}")
        
        component = self.components[name]
        
        if component.is_running:
            return  # 이미 실행 중
        
        component.is_running = True
        
        if component.type == 'process':
            # 프로세스 시작 - 별도의 진입점 함수 사용
            process = multiprocessing.Process(
                target=_process_entry_point,
                args=(name, component.child_conn),
                daemon=True
            )
            component.process = process
            try:
                process.start()
            except Exception as e:
                component.is_running = False
                raise IPCError(f"프로세스 시작 실패: {str(e)}")
        elif component.type == 'thread' and (not component.listener or not component.listener.is_alive()):
            # 리스너 스레드 재시작
            self._start_thread_listener(name)
    
    def stop(self, name: str) -> None:
        """컴포넌트 중지"""
        if name not in self.components:
            raise IPCError(f"등록되지 않은 컴포넌트: {name}")
        
        component = self.components[name]
        component.is_running = False
        
        if component.type == 'process' and hasattr(component, 'process') and component.process:
            # 프로세스 종료 메시지 전송
            try:
                stop_msg = IPCMessage(
                    src="ipc_manager",
                    dst=name,
                    func="__stop__"
                )
                component.parent_conn.send(stop_msg.serialize())
                
                # 프로세스 종료 대기 (최대 3초)
                component.process.join(3)
                
                # 강제 종료
                if component.process.is_alive():
                    component.process.terminate()
            except Exception as e:
                print(f"컴포넌트 중지 오류 ({name}): {str(e)}")
    
    def work(self, name: str, func: str, args: tuple = None, kwargs: dict = None) -> None:
        """
        비반환 작업 실행 (결과를 기다리지 않음)
        
        Args:
            name: 대상 컴포넌트 이름
            func: 실행할 함수 이름
            args: 함수 위치 인자
            kwargs: 함수 키워드 인자
        """
        if name not in self.components:
            raise IPCError(f"등록되지 않은 컴포넌트: {name}")
        
        component = self.components[name]
        
        if not component.is_running:
            raise IPCError(f"컴포넌트가 실행 중이 아닙니다: {name}")
        
        # 메인 스레드 컴포넌트 직접 호출
        if not component.type:
            try:
                # 함수 호출
                getattr(component.cls, func)(*args or (), **kwargs or {})
                return
            except Exception as e:
                raise IPCError(f"함수 호출 실패: {str(e)}")
        
        # 인자 처리 (큰 데이터는 공유 메모리 사용)
        processed_args = []
        shared_refs = []
        
        if args:
            for arg in args:
                data_ref, is_shared = self.shared_mem_manager.put_data(arg)
                if is_shared:
                    processed_args.append((data_ref, True))
                    shared_refs.append(data_ref)
                else:
                    processed_args.append(arg)
        
        processed_kwargs = {}
        if kwargs:
            for key, value in kwargs.items():
                data_ref, is_shared = self.shared_mem_manager.put_data(value)
                if is_shared:
                    processed_kwargs[key] = (data_ref, True)
                    shared_refs.append(data_ref)
                else:
                    processed_kwargs[key] = value
        
        # 메시지 생성
        msg = IPCMessage(
            src="ipc_manager",
            dst=name,
            func=func,
            args=tuple(processed_args),
            kwargs=processed_kwargs,
            is_async=True,
            shared_refs=shared_refs
        )
        
        # 메시지 전송
        component.parent_conn.send(msg.serialize())
    
    def answer(self, name: str, func: str, args: tuple = None, 
              kwargs: dict = None, callback: Callable = None) -> Any:
        """
        동기/비동기 작업 실행
        
        Args:
            name: 대상 컴포넌트 이름
            func: 실행할 함수 이름
            args: 함수 위치 인자
            kwargs: 함수 키워드 인자
            callback: 비동기 콜백 함수 (None인 경우 동기 호출)
            
        Returns:
            함수 실행 결과 (동기 호출인 경우)
        """
        if name not in self.components:
            raise IPCError(f"등록되지 않은 컴포넌트: {name}")
        
        component = self.components[name]
        
        if not component.is_running:
            raise IPCError(f"컴포넌트가 실행 중이 아닙니다: {name}")
        
        # 메인 스레드 컴포넌트 직접 호출
        if not component.type:
            try:
                # 함수 호출
                result = getattr(component.cls, func)(*args or (), **kwargs or {})
                return result
            except Exception as e:
                raise IPCError(f"함수 호출 실패: {str(e)}")
        
        # 인자 처리 (큰 데이터는 공유 메모리 사용)
        processed_args = []
        shared_refs = []
        
        if args:
            for arg in args:
                data_ref, is_shared = self.shared_mem_manager.put_data(arg)
                if is_shared:
                    processed_args.append((data_ref, True))
                    shared_refs.append(data_ref)
                else:
                    processed_args.append(arg)
        
        processed_kwargs = {}
        if kwargs:
            for key, value in kwargs.items():
                data_ref, is_shared = self.shared_mem_manager.put_data(value)
                if is_shared:
                    processed_kwargs[key] = (data_ref, True)
                    shared_refs.append(data_ref)
                else:
                    processed_kwargs[key] = value
        
        # 메시지 ID 생성
        with self.lock:
            self.msg_count += 1
            msg_id = f"{os.getpid()}-{threading.get_ident()}-{self.msg_count}"
        
        # 메시지 생성
        msg = IPCMessage(
            msg_id=msg_id,
            src="ipc_manager",
            dst=name,
            func=func,
            args=tuple(processed_args),
            kwargs=processed_kwargs,
            is_async=callback is not None,
            shared_refs=shared_refs
        )
        
        # 비동기 호출 (콜백 사용)
        if callback:
            with component.callback_lock:
                component.callbacks[msg_id] = callback
            
            component.parent_conn.send(msg.serialize())
            return None

        # 동기 호출 (결과 대기)
        component.parent_conn.send(msg.serialize())
        
        # 응답 대기
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if component.parent_conn.poll(0.001):  # 1ms 타임아웃으로 폴링
                # 응답 수신
                data = component.parent_conn.recv()
                response = IPCMessage.deserialize(data)
                
                # 콜백 ID 확인
                if response.callback_id == msg_id:
                    # 오류 처리
                    if response.error:
                        raise IPCError(f"원격 함수 호출 실패: {response.error}")
                    
                    # 공유 메모리 결과 처리
                    if isinstance(response.result, tuple) and len(response.result) == 2 and response.result[1] is True:
                        result = self.shared_mem_manager.get_data(response.result[0], True)
                        # 공유 메모리 해제
                        self.shared_mem_manager.free_memory(response.result[0])
                    else:
                        result = response.result
                    
                    # 다른 공유 메모리 참조 해제
                    for ref in response.shared_refs:
                        if isinstance(response.result, tuple) and len(response.result) == 2:
                            if ref != response.result[0]:
                                self.shared_mem_manager.free_memory(ref)
                        else:
                            self.shared_mem_manager.free_memory(ref)
                    
                    return result
            
            # CPU 과부하 방지
            time.sleep(0.001)
        
        raise IPCTimeoutError(f"함수 호출 타임아웃: {name}.{func}")
    
    def cleanup(self) -> None:
        """모든 리소스 정리"""
        self.is_running = False
        
        # 모든 컴포넌트 중지
        for name, component in list(self.components.items()):
            if name != "ipc_manager":
                try:
                    self.stop(name)
                except Exception as e:
                    print(f"컴포넌트 정리 오류 ({name}): {str(e)}")
        
        # 공유 메모리 정리
        self.shared_mem_manager.cleanup()
        
        # 파이프 연결 닫기
        for component in self.components.values():
            if component.parent_conn:
                component.parent_conn.close()
            if component.child_conn:
                component.child_conn.close()
        
        print("IPC 관리자 정리 완료")

# 전역 변수 - 현재 프로세스/스레드의 컴포넌트 클래스
_component_class = None

# 프로세스 시작을 위한 진입점 함수 (모듈 수준)
def _process_entry_point(name, conn):
    """
    자식 프로세스 진입점 함수
    
    Args:
        name: 프로세스 이름
        conn: 통신용 파이프 연결
    """
    try:
        # 시그널 핸들러 설정
        def signal_handler(sig, frame):
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 프록시 생성 및 전역 변수로 설정
        proxy = IPCManagerProxy(conn, name)
        global _ipc_instance
        _ipc_instance = proxy
        
        # 메시지 루프 - 프로세스가 종료될 때까지 실행
        while proxy.is_running:
            time.sleep(0.1)
            
    except Exception as e:
        print(f"프로세스 {name} 오류: {e}\n{traceback.format_exc()}")
    finally:
        sys.exit()

def get_component_class(name: str) -> object:
    """현재 프로세스/스레드의 컴포넌트 클래스 반환"""
    global _component_class
    return _component_class

def init(timeout: float = 5.0) -> IPCManager:
    """
    IPCManager 초기화 (메인 프로세스에서 호출)
    
    Args:
        timeout: 기본 통신 타임아웃 (초)
        
    Returns:
        IPCManager 인스턴스
    """
    global _ipc_instance
    if _ipc_instance is None:
        _ipc_instance = IPCManager(timeout)
    return _ipc_instance

def get_instance() -> Union[IPCManager, IPCManagerProxy]:
    """
    현재 IPCManager 인스턴스 반환
    
    Returns:
        IPCManager 또는 IPCManagerProxy 인스턴스
    """
    global _ipc_instance
    if _ipc_instance is None:
        raise IPCError("IPCManager가 초기화되지 않았습니다. init()을 먼저 호출하세요.")
    return _ipc_instance

def register(name: str, cls: object, comp_type: Optional[str] = None) -> None:
    """
    컴포넌트 등록 (모듈 함수)
    
    Args:
        name: 컴포넌트 이름
        cls: 컴포넌트 클래스 객체
        comp_type: 컴포넌트 타입 (None=메인스레드, 'thread'=스레드, 'process'=프로세스)
    """
    return get_instance().register(name, cls, comp_type)

def work(name: str, func: str, args: tuple = None, kwargs: dict = None) -> None:
    """
    비반환 작업 실행 (모듈 함수)
    
    Args:
        name: 대상 컴포넌트 이름
        func: 실행할 함수 이름
        args: 함수 위치 인자
        kwargs: 함수 키워드 인자
    """
    return get_instance().work(name, func, args, kwargs)

def answer(name: str, func: str, args: tuple = None, 
          kwargs: dict = None, callback: Callable = None) -> Any:
    """
    동기/비동기 작업 실행 (모듈 함수)
    
    Args:
        name: 대상 컴포넌트 이름
        func: 실행할 함수 이름
        args: 함수 위치 인자
        kwargs: 함수 키워드 인자
        callback: 비동기 콜백 함수 (None인 경우 동기 호출)
        
    Returns:
        함수 실행 결과 (동기 호출인 경우)
    """
    return get_instance().answer(name, func, args, kwargs, callback)

def start(name: str) -> None:
    """
    컴포넌트 시작 (모듈 함수)
    
    Args:
        name: 컴포넌트 이름
    """
    return get_instance().start(name)

def stop(name: str) -> None:
    """
    컴포넌트 중지 (모듈 함수)
    
    Args:
        name: 컴포넌트 이름
    """
    return get_instance().stop(name)

def cleanup() -> None:
    """모든 리소스 정리 (모듈 함수)"""
    if _ipc_instance:
        return _ipc_instance.cleanup()
    
# 모듈 직접 실행 시 간단한 테스트
if __name__ == "__main__":
    # 간단한 테스트 코드
    import time
    
    class TestMain:
        def test_func(self, data):
            print(f"메인 스레드 함수 호출됨: {data}")
            return f"결과: {data}"
    
    class TestThread:
        def test_func(self, data):
            print(f"스레드 함수 호출됨: {data}")
            time.sleep(0.1)  # 작업 시뮬레이션
            return f"스레드 결과: {data}"
        
        def call_others(self, target, data):
            """다른 컴포넌트 호출 테스트"""
            print(f"스레드에서 {target} 호출: {data}")
            # 모듈 함수 사용
            result = answer(target, "test_func", args=(f"스레드에서 호출: {data}",))
            return f"스레드에서 {target} 호출 결과: {result}"
    
    class TestProcess:
        def test_func(self, data):
            print(f"프로세스 함수 호출됨: {data}")
            time.sleep(0.1)  # 작업 시뮬레이션
            return f"프로세스 결과: {data}"
        
        def call_others(self, target, data):
            """다른 컴포넌트 호출 테스트"""
            print(f"프로세스에서 {target} 호출: {data}")
            # 모듈 함수 사용
            result = answer(target, "test_func", args=(f"프로세스에서 호출: {data}",))
            return f"프로세스에서 {target} 호출 결과: {result}"
    
    def test_callback(result):
        print(f"비동기 콜백 결과: {result}")
    
    # IPC 관리자 생성
    ipc = init()
    
    # 컴포넌트 등록
    main_obj = TestMain()
    thread_obj = TestThread()
    process_obj = TestProcess()
    
    register("main", main_obj)
    register("thread", thread_obj, "thread")
    register("process", process_obj, "process")
    
    # 컴포넌트 시작
    start("thread")
    start("process")
    
    # 동기 호출 테스트
    print("=== 동기 호출 테스트 ===")
    result1 = answer("main", "test_func", args=("메인 테스트",))
    print(f"메인 결과: {result1}")
    
    result2 = answer("thread", "test_func", args=("스레드 테스트",))
    print(f"스레드 결과: {result2}")
    
    result3 = answer("process", "test_func", args=("프로세스 테스트",))
    print(f"프로세스 결과: {result3}")
    
    # 비동기 호출 테스트
    print("\n=== 비동기 호출 테스트 ===")
    answer("thread", "test_func", args=("비동기 스레드 테스트",), callback=test_callback)
    answer("process", "test_func", args=("비동기 프로세스 테스트",), callback=test_callback)
    
    # 대용량 데이터 테스트
    print("\n=== 대용량 데이터 테스트 ===")
    large_data = {f"key_{i}": f"value_{i}" * 1000 for i in range(1000)}  # 약 10MB 데이터
    result_large = answer("process", "test_func", args=(large_data,))
    print(f"대용량 데이터 결과 크기: {len(str(result_large))}")
    
    # 컴포넌트 간 호출 테스트
    print("\n=== 컴포넌트 간 호출 테스트 ===")
    # 스레드 -> 프로세스 호출
    thread_to_process = answer("thread", "call_others", args=("process", "스레드->프로세스 테스트"))
    print(f"스레드->프로세스 결과: {thread_to_process}")
    
    # 프로세스 -> 스레드 호출
    process_to_thread = answer("process", "call_others", args=("thread", "프로세스->스레드 테스트"))
    print(f"프로세스->스레드 결과: {process_to_thread}")
    
    # 성능 테스트
    print("\n=== 성능 테스트 ===")
    start_time = time.time()
    count = 1000
    
    for i in range(count):
        work("thread", "test_func", args=(f"성능 테스트 {i}",))
    
    elapsed = time.time() - start_time
    print(f"{count}개 요청 처리 시간: {elapsed:.6f}초")
    print(f"초당 요청 처리량: {count/elapsed:.2f}개/초")
    
    # 작업 완료 대기
    print("\n작업 완료 대기 중...")
    time.sleep(2)
    
    # 정리
    cleanup()
    print("테스트 완료")




