from api_server import APIServer
from dbm_server import DBMServer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import multiprocessing as mp
import threading
import types
import queue
import time
import logging
import uuid

class TRDThread(QThread):
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
                
class TRDManager:
    def __init__(self):
        self.workers = {}  # name -> worker thread
        self.targets = {}  # name -> target object
        self.is_shutting_down = False
        self.lock = threading.RLock()  # 재진입 가능한 락 사용
        self.response_events = {}  # request_id -> Event
    
    def register(self, name, target_class=None, type=None, start=None):
        """컴포넌트 등록
        
        Args:
            name: 컴포넌트 이름
            target_class: 대상 클래스 또는 인스턴스
            type: None(메인 쓰레드) 또는 'thread'(멀티 쓰레드)
            start: True이면 등록과 동시에 시작
        """
        # 인스턴스 생성 또는 인스턴스 사용 - 타입 체크 없이 처리
        if target_class is None:
            logging.error(f"대상 클래스/인스턴스가 None입니다: {name}")
            return None
        
        try:
            # 단순하게 처리: callable이면 호출, 아니면 그대로 사용
            if callable(target_class) and not hasattr(target_class, '__dict__'):
                target = target_class()
            else:
                target = target_class
        except Exception as e:
            logging.error(f"인스턴스 생성 오류: {e}")
            return None
        
        # work, answer 메서드 심기
        self._inject_methods(target)
        
        if type == 'thread':
            worker = TRDThread(name, target)
            self.workers[name] = worker
            if start:
                worker.start()
        else:
            self.targets[name] = target
            
        return target

    def _inject_methods(self, target):
        """타겟 객체에 work, answer 메서드 주입"""
        def work_method(self, cls_name, method_name, *args, callback=None, **kwargs):
            # 현재 매니저 찾기
            for manager in [trd, ipc]:  # 전역 변수 참조 필요
                if self in manager.targets.values() or any(self == worker.target for worker in manager.workers.values()):
                    return manager.work(cls_name, method_name, *args, callback=callback, **kwargs)
            return False
        
        def answer_method(self, cls_name, method_name, *args, **kwargs):
            # 현재 매니저 찾기
            for manager in [trd, ipc]:  # 전역 변수 참조 필요
                if self in manager.targets.values() or any(self == worker.target for worker in manager.workers.values()):
                    return manager.answer(cls_name, method_name, *args, **kwargs)
            return None
            
        # 메서드 주입
        target.work = types.MethodType(work_method, target)
        target.answer = types.MethodType(answer_method, target)

    def unregister(self, worker_name):
        """워커 제거"""
        if worker_name in self.workers:
            self.stop(worker_name)
            self.workers.pop(worker_name, None)
            logging.debug(f"워커 제거: {worker_name} (쓰레드)")
            return True
        elif worker_name in self.targets:
            self.targets.pop(worker_name, None)
            logging.debug(f"워커 제거: {worker_name} (메인 쓰레드)")
            return True
        return False
            
    def start(self, worker_name):
        """워커 시작"""
        if worker_name in self.workers:
            self.workers[worker_name].start()
            return True
        return False

    def stop(self, worker_name):
        """워커 중지"""
        # 쓰레드 워커 중지
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            worker.running = False
            worker.quit()  # 이벤트 루프 종료
            worker.wait(100)  # 최대 0.1초간 대기 (성능 향상)
            self.workers.pop(worker_name, None)
            logging.debug(f"워커 종료: {worker_name} (쓰레드)")
            return True
        # 메인 쓰레드 워커 제거
        elif worker_name in self.targets:
            self.targets.pop(worker_name, None)
            logging.debug(f"워커 제거: {worker_name} (메인 쓰레드)")
            return True
        return False

    def answer(self, cls_name, method_name, *args, **kwargs):
        """동기식 함수 호출"""
        if self.is_shutting_down:
            return None
        
        # 워커 찾기
        with self.lock:
            if cls_name not in self.workers and cls_name not in self.targets:
                logging.error(f"워커 없음: {cls_name}")
                return None
        
        # 메인 쓰레드에서 실행하는 경우
        if cls_name in self.targets:
            target = self.targets[cls_name]
            method = getattr(target, method_name, None)
            if not method:
                return None
            try:
                return method(*args, **kwargs)
            except Exception as e:
                logging.error(f"직접 호출 오류: {e}", exc_info=True)
                return None
        
        # 쓰레드로 실행하는 경우
        worker = self.workers[cls_name]
        
        # 고유 요청 ID 생성 및 이벤트 설정
        req_id = str(uuid.uuid4())
        event = threading.Event()
        result = [None]
        
        with self.lock:
            self.response_events[req_id] = (event, result)
        
        def callback(res):
            result[0] = res
            event.set()
        
        # 시그널로 태스크 전송
        task_data = (args, kwargs)
        worker.taskReceived.emit(req_id, method_name, task_data, callback)
        
        # 결과 대기 (Event 사용으로 CPU 사용률 개선)
        if not event.wait(1.0):
            with self.lock:
                self.response_events.pop(req_id, None)
            logging.warning(f"호출 타임아웃: {cls_name}.{method_name}")
            return None
        
        with self.lock:
            self.response_events.pop(req_id, None)
        
        return result[0]

    def work(self, cls_name, method_name, *args, callback=None, **kwargs):
        """비동기 함수 호출"""
        if self.is_shutting_down:
            return False
        
        # 워커 찾기
        with self.lock:
            if cls_name not in self.workers and cls_name not in self.targets:
                logging.error(f"워커 없음: {cls_name}")
                return False
        
        # 메인 쓰레드에서 실행하는 경우
        if cls_name in self.targets:
            target = self.targets[cls_name]
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
        worker = self.workers[cls_name]
        req_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        worker.taskReceived.emit(req_id, method_name, task_data, callback)
        return True

    def cleanup(self):
        """모든 워커 중지"""
        self.is_shutting_down = True
        logging.info("모든 워커 중지 중...")
        
        # 모든 쓰레드 워커 중지
        for name in list(self.workers.keys()):
            self.stop(name)
            
        # 모든 메인 쓰레드 워커 제거
        self.targets.clear()
        
        logging.debug("모든 워커 종료")
        
class IPCManager:
    def __init__(self):
        self.manager = mp.Manager()
        self.result_dict = self.manager.dict()
        self.response_events = {}
        self.ipc_process = None
        self.is_shutting_down = False
        self.lock = threading.RLock()
        
        # 큐 생성
        self.admin_to_ipc = mp.Queue()
        self.ipc_to_admin = mp.Queue()
    
    def register(self, name=None, target_class=None, type=None, start=None):
        return None  # IPC_Process는 자동 등록
    
    def unregister(self, worker_name=None):
        self.stop()
        return True
    
    def start(self, worker_name=None):
        if self.ipc_process is not None:
            return False
        
        # 프로세스 시작
        self.is_shutting_down = False
        self.ipc_process = mp.Process(
            target=ipc_worker,
            args=(self.admin_to_ipc, self.ipc_to_admin, self.result_dict),
            daemon=True
        )
        self.ipc_process.start()
        
        # 리스너 시작
        threading.Thread(
            target=ipc_listener,
            args=(self, self.ipc_to_admin, self.result_dict),
            daemon=True
        ).start()
        
        return True
    
    def stop(self, worker_name=None):
        if self.ipc_process is None:
            return False
        
        # 종료 명령 전송
        try:
            self.admin_to_ipc.put({'command': 'stop'}, block=False)
        except:
            pass
        
        # 프로세스 종료
        try:
            self.ipc_process.join(0.5)
            if self.ipc_process.is_alive():
                self.ipc_process.terminate()
        except:
            pass
        
        self.ipc_process = None
        return True
    
    def answer(self, cls_name, method_name, *args, timeout=10.0, **kwargs):
        if self.is_shutting_down or self.ipc_process is None:
            return None
        
        req_id = str(uuid.uuid4())
        method_fullname = f"{cls_name}.{method_name}"
        event = threading.Event()
        result = [None]
        
        # 이벤트 등록
        with self.lock:
            self.response_events[req_id] = (event, result)
        
        # 요청 전송
        try:
            self.admin_to_ipc.put({
                'id': req_id,
                'method': method_fullname,
                'args': args,
                'kwargs': kwargs
            }, block=False)
        except:
            with self.lock:
                self.response_events.pop(req_id, None)
            return None
        
        # 결과 대기
        if not event.wait(timeout):
            with self.lock:
                self.response_events.pop(req_id, None)
            return None
        
        with self.lock:
            self.response_events.pop(req_id, None)
        
        return result[0]

    def work(self, cls_name, method_name, *args, callback=None, **kwargs):
        if self.is_shutting_down or self.ipc_process is None:
            if callback:
                callback(None)
            return False
        
        req_id = str(uuid.uuid4())
        method_fullname = f"{cls_name}.{method_name}"
        
        # 콜백 설정
        if callback:
            event = threading.Event()
            result = [None]
            
            with self.lock:
                self.response_events[req_id] = (event, result)
                
            def check_result():
                timeout = kwargs.get('timeout', 10.0)
                if not event.wait(timeout):
                    with self.lock:
                        self.response_events.pop(req_id, None)
                    callback(None)
                    return
                
                with self.lock:
                    self.response_events.pop(req_id, None)
                callback(result[0])
            
            threading.Thread(target=check_result, daemon=True).start()
        
        # 요청 전송
        try:
            self.admin_to_ipc.put({
                'id': req_id,
                'method': method_fullname,
                'args': args,
                'kwargs': kwargs
            }, block=False)
            return True
        except:
            if callback:
                with self.lock:
                    self.response_events.pop(req_id, None)
                callback(None)
            return False

    def cleanup(self):
        self.is_shutting_down = True
        self.stop()
        
        # 이벤트 모두 해제
        with self.lock:
            for event, _ in self.response_events.values():
                event.set()
            self.response_events.clear()
        
        # 매니저 종료
        try:
            self.manager.shutdown()
        except:
            pass
        self.manager = None

def ipc_worker(input_queue, output_queue, result_dict):
    # 인스턴스 생성
    ipc = IPC_Process()
    
    # Admin에 요청 보내는 함수
    def request_to_admin(method, *args, wait_result=True, timeout=10.0, **kwargs):
        req_id = str(uuid.uuid4())
        output_queue.put({
            'id': req_id,
            'method': method,
            'args': args,
            'kwargs': kwargs
        })
        
        if not wait_result:
            return None
        
        # 결과 대기
        start_time = time.time()
        while req_id not in result_dict:
            if time.time() - start_time > timeout:
                return None
            time.sleep(0.001)
        
        result = result_dict.pop(req_id, {})
        return result.get('result')
    
    # 함수 등록 및 초기화
    ipc.request_to_admin = request_to_admin
    ipc.init()
    
    # 메시지 처리 루프
    try:
        while True:
            try:
                request = input_queue.get(timeout=0.001)
            except queue.Empty:
                continue
            except:
                break
            
            # 종료 명령 확인
            if 'command' in request and request['command'] == 'stop':
                break
            
            # 요청 처리
            try:
                req_id = request.get('id')
                method_fullname = request.get('method')
                cls_name, method_name = method_fullname.split('.')
                
                # 함수 호출
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                result = ipc.call_function(cls_name, method_name, *args, **kwargs)
                
                # 결과 저장
                result_dict[req_id] = {'result': result}
            except:
                # 오류 발생 시 None 결과
                if 'id' in request:
                    result_dict[request['id']] = {'result': None}
    except:
        pass

def ipc_listener(admin_instance, input_queue, result_dict):
    try:
        while True:
            # 종료 확인
            if hasattr(admin_instance, 'is_shutting_down') and admin_instance.is_shutting_down:
                break
            
            # 요청 처리
            try:
                request = input_queue.get(timeout=0.001)
            except queue.Empty:
                # 결과 처리 (저장된 결과 확인)
                if hasattr(admin_instance, 'response_events'):
                    with admin_instance.lock:
                        # 응답 처리
                        for req_id in list(result_dict.keys()):
                            if req_id in admin_instance.response_events:
                                event, result_container = admin_instance.response_events[req_id]
                                result_container[0] = result_dict.pop(req_id, {}).get('result')
                                event.set()
                continue
            except:
                break
            
            # 요청 처리
            try:
                req_id = request.get('id')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                
                # 메서드 실행
                method = getattr(admin_instance, method_name, None)
                if method:
                    result = method(*args, **kwargs)
                    result_dict[req_id] = {'result': result}
                    
                    # 이벤트 설정
                    if hasattr(admin_instance, 'response_events'):
                        with admin_instance.lock:
                            if req_id in admin_instance.response_events:
                                event, result_container = admin_instance.response_events[req_id]
                                result_container[0] = result
                                event.set()
                else:
                    result_dict[req_id] = {'result': None}
            except:
                # 오류 발생 시 None 결과
                if 'id' in request:
                    result_dict[request['id']] = {'result': None}
    except:
        pass

class IPC_Process:
    def __init__(self):
        self.api = None
        self.dbm = None
        self.request_to_admin = None  # 런타임에 설정됨
    
    def init(self):
        # 컴포넌트 초기화
        self.api = APIServer()
        self.dbm = DBMServer()
        
        # 컴포넌트에 work, answer 메서드 주입
        self._inject_methods(self.api)
        self._inject_methods(self.dbm)
    
    def _inject_methods(self, target):
        """컴포넌트에 work, answer 메서드 주입"""
        def work_method(self, cls_name, method_name, *args, callback=None, **kwargs):
            if callback:
                result = self.parent.request_to_admin(f"{cls_name}.{method_name}", 
                                                      *args, wait_result=False, **kwargs)
                # 비동기 콜백 처리 로직은 여기에 추가 필요
                return True
            else:
                return self.parent.request_to_admin(f"{cls_name}.{method_name}", 
                                                   *args, wait_result=False, **kwargs)
        
        def answer_method(self, cls_name, method_name, *args, **kwargs):
            return self.parent.request_to_admin(f"{cls_name}.{method_name}", 
                                               *args, wait_result=True, **kwargs)
        
        # 메서드 주입 및 부모 참조 설정
        target.parent = self
        target.work = types.MethodType(work_method, target)
        target.answer = types.MethodType(answer_method, target)
    
    def call_function(self, cls_name, method_name, *args, **kwargs):
        """클래스와 메서드 이름으로 함수 호출"""
        if cls_name == 'api' and self.api:
            target = self.api
        elif cls_name == 'dbm' and self.dbm:
            target = self.dbm
        else:
            logging.error(f"알 수 없는 클래스: {cls_name}")
            return None
        
        # 메서드 찾기
        method = getattr(target, method_name, None)
        if not method:
            logging.error(f"메서드 없음: {cls_name}.{method_name}")
            return None
        
        # 메서드 실행
        try:
            result = method(*args, **kwargs)
            logging.debug(f"메서드 실행 결과: {result}")
            return result
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            return None

if __name__ == "__main__":
    import sys
    import time
    import logging
    import multiprocessing as mp
    import threading
    import queue
    import uuid
    
    #from public import init_logger

    # 로깅 설정
    #init_logger()

    # 테스트용 클래스 정의
    class TestComponent:
        def __init__(self):
            self.data = {}
            logging.info("TestComponent 초기화됨")
        
        def set_value(self, key, value):
            self.data[key] = value
            logging.info(f"값 설정: {key}={value}")
            return True
        
        def get_value(self, key):
            logging.info(f"값 조회: {key}")
            return self.data.get(key)
        
        def process_data(self, data, factor=1):
            logging.info(f"데이터 처리: {data} (factor={factor})")
            if isinstance(data, (int, float)):
                return data * factor
            return None
        
        def test_request_to_main(self, test_value):
            """메인으로 요청 테스트"""
            if hasattr(self, 'work'):
                result = self.answer("main_handler", "", test_value)
                return f"메인에서 받은 응답: {result}"
            return "요청 실패: work 메서드 없음"
    
    # QApplication 인스턴스 생성 (PyQt 사용 시 필요)
    app = QApplication(sys.argv)
    
    # 전역 매니저 인스턴스 생성
    trd_manager = TRDManager()  # _inject_methods에서 사용할 전역 변수
    ipc_manager = IPCManager()
    
    # 나중에 사용하기 위해 전역 변수에 할당
    trd = trd_manager
    ipc = ipc_manager
    
    try:
        '''
        # TRDManager 테스트
        logging.info("===== TRDManager 테스트 시작 =====")
        
        # 컴포넌트 등록 - 명시적으로 인스턴스 생성 후 전달
        main_comp = TestComponent()
        thread_comp = TestComponent()
        
        main_component = trd.register("main", main_comp, type=None)
        thread_component = trd.register("thread", thread_comp, type="thread", start=True)
        # 동기 호출 테스트
        logging.info("동기 호출 테스트:")
        trd.answer("main", "set_value", "test_key", "test_value")
        result = trd.answer("main", "get_value", "test_key")
        logging.info(f"메인 쓰레드 결과: {result}")
        
        trd.answer("thread", "set_value", "thread_key", "thread_value")
        result = trd.answer("thread", "get_value", "thread_key")
        logging.info(f"쓰레드 결과: {result}")
        
        # 비동기 호출 테스트
        logging.info("비동기 호출 테스트:")
        def callback(result):
            logging.info(f"콜백 결과: {result}")
        
        trd.work("thread", "process_data", 10, factor=2, callback=callback)
        
        # 컴포넌트에서 다른 컴포넌트 호출 테스트
        logging.info("컴포넌트 간 호출 테스트:")
        main_component.answer("thread", "set_value", "from_main", "called_by_main")
        result = main_component.answer("thread", "get_value", "from_main")
        logging.info(f"컴포넌트 간 호출 결과: {result}")
        
        # 1초간 대기 (쓰레드 작업 완료 대기)
        time.sleep(1)
'''        
        # IPCManager 테스트
        logging.info("\n===== IPCManager 테스트 시작 =====")
        
        # IPC 프로세스 시작
        ipc.start()
        time.sleep(1)  # 시작 대기
        
        # 동기 호출 테스트
        logging.info("IPC 동기 호출 테스트:")
        ipc.work("api", "api_init", sim_no=0)
        ipc.work("api", "CommConnect", block=False)
        
        logging.info("로그인 대기 시작")
        while True:
            logging.info("api_connected 대기 중")
            if not ipc.answer('api', 'api_connected'): time.sleep(0.5)
            else: break
        
        result = ipc.answer("api", "GetLoginInfo", kind="ACCNO")
        logging.info(f"IPC GetLoginInfo 결과: {result}")
        
        result = ipc.answer("api", "GetMasterCodeName", code="005930")
        logging.info(f"IPC GetMasterCodeName 결과: {result}")

        # 정리
        logging.info("\n===== 테스트 종료 =====")
        trd.cleanup()
        ipc.cleanup()
        
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {e}", exc_info=True)
        
    finally:
        # 종료 전 정리
        trd.cleanup()
        ipc.cleanup()
        
    # 종료
    sys.exit(0)





