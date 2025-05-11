import logging
import threading
import uuid
import time
import queue
import multiprocessing as mp
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

class IPCManager:
    """
    통합 통신 관리자 클래스
    메인스레드, 멀티스레드, 멀티프로세스 간 통신을 통합적으로 관리
    """
    
    def __init__(self):
        """IPCManager 초기화"""
        # 등록된 객체 관리
        self.instances = {}  # name -> instance
        self.types = {}  # name -> type (None=메인스레드, 'thread'=멀티스레드, 'process'=멀티프로세스)
        
        # 스레드 관리
        self.threads = {}  # name -> thread object
        
        # 프로세스 관리
        self.processes = {}  # name -> process object
        self.manager = mp.Manager() if mp.get_start_method() == 'spawn' else None
        self.queues = {}  # name -> {input: Queue, output: Queue}
        self.result_dict = self.manager.dict() if self.manager else {}
        
        # 콜백 관리
        self.callbacks = {}  # id -> callback function
        
        # 종료 상태
        self.shutting_down = False
        
        # 리스너 스레드
        self.listeners = {}  # name -> listener thread
        
        logging.debug("IPCManager 초기화 완료")
    
    def register(self, name, instance, type_=None, start=False):
        """
        객체 등록
        
        Args:
            name (str): 등록할 객체의 이름
            instance: 등록할 객체 인스턴스
            type_ (str, optional): 객체 유형 (None=메인스레드, 'thread'=멀티스레드, 'process'=멀티프로세스)
            start (bool, optional): 등록 후 바로 시작할지 여부
        
        Returns:
            instance: 등록된 객체 인스턴스
        """
        if name in self.instances:
            logging.warning(f"'{name}'은(는) 이미 등록된 이름입니다. 기존 등록을 덮어씁니다.")
            self.stop(name)
        
        self.types[name] = type_
        
        # 타입에 따라 다르게 처리
        if type_ is None:
            # 메인스레드에서 실행
            self.instances[name] = instance
            logging.debug(f"'{name}' 메인스레드 객체로 등록됨")
        
        elif type_ == 'thread':
            # 멀티스레드로 실행
            self._register_thread(name, instance)
            logging.debug(f"'{name}' 멀티스레드 객체로 등록됨")
        
        elif type_ == 'process':
            # 멀티프로세스로 실행
            self._register_process(name, instance.__class__)
            logging.debug(f"'{name}' 멀티프로세스 객체로 등록됨")
        
        else:
            raise ValueError(f"지원하지 않는 type: {type_}")
        
        # 시작 옵션이 True면 바로 시작
        if start:
            self.start(name)
        
        return instance
    
    def _register_thread(self, name, instance):
        """
        스레드 객체 등록 (내부 메서드)
        
        Args:
            name (str): 등록할 스레드의 이름
            instance: 등록할 객체 인스턴스
        """
        # 워커 스레드 생성
        thread = _WorkerThread(name, instance)
        self.threads[name] = thread
        self.instances[name] = instance
        
        # 워커에 work, answer 메서드 추가
        instance.work = lambda target, method, *args, **kwargs: self.work(target, method, *args, **kwargs)
        instance.answer = lambda target, method, *args, **kwargs: self.answer(target, method, *args, **kwargs)
    
    def _register_process(self, name, class_):
        """
        프로세스 객체 등록 (내부 메서드)
        
        Args:
            name (str): 등록할 프로세스의 이름
            class_: 프로세스에서 실행할 클래스
        """
        # 필요한 큐 생성
        if self.manager is None:
            self.manager = mp.Manager()
            self.result_dict = self.manager.dict()
        
        input_queue = mp.Queue()
        output_queue = mp.Queue()
        
        self.queues[name] = {
            'input': input_queue,
            'output': output_queue
        }
        
        # 프로세스 객체 생성
        process = mp.Process(
            target=_process_worker,
            args=(class_, name, input_queue, output_queue, self.result_dict),
            daemon=True
        )
        
        self.processes[name] = process
        self.instances[name] = None  # 프로세스는 별도 프로세스에서 실행되므로 None으로 설정
    
    def start(self, name):
        """
        등록된 객체 시작
        
        Args:
            name (str): 시작할 객체의 이름
        
        Returns:
            bool: 성공 여부
        """
        if name not in self.types:
            logging.error(f"'{name}'은(는) 등록되지 않은 이름입니다.")
            return False
        
        type_ = self.types[name]
        
        if type_ is None:
            # 메인스레드는 별도 시작 과정 없음
            return True
        
        elif type_ == 'thread':
            # 스레드 시작
            if name in self.threads and not self.threads[name].is_alive():
                self.threads[name].start()
                
                # 리스너 스레드 시작 (결과 처리용)
                if name not in self.listeners:
                    listener = threading.Thread(
                        target=self._thread_listener,
                        args=(name,),
                        daemon=True
                    )
                    self.listeners[name] = listener
                    listener.start()
                
                logging.debug(f"'{name}' 스레드 시작됨")
                return True
        
        elif type_ == 'process':
            # 프로세스 시작
            if name in self.processes and not self.processes[name].is_alive():
                self.processes[name].start()
                
                # 리스너 스레드 시작 (결과 처리용)
                if name not in self.listeners:
                    listener = threading.Thread(
                        target=self._process_listener,
                        args=(name,),
                        daemon=True
                    )
                    self.listeners[name] = listener
                    listener.start()
                
                logging.debug(f"'{name}' 프로세스 시작됨 (PID: {self.processes[name].pid})")
                return True
        
        return False
    
    def stop(self, name):
        """
        등록된 객체 중지
        
        Args:
            name (str): 중지할 객체의 이름
        
        Returns:
            bool: 성공 여부
        """
        if name not in self.types:
            logging.error(f"'{name}'은(는) 등록되지 않은 이름입니다.")
            return False
        
        type_ = self.types[name]
        
        if type_ is None:
            # 메인스레드는 별도 중지 과정 없음
            return True
        
        elif type_ == 'thread':
            # 스레드 중지
            if name in self.threads:
                thread = self.threads[name]
                thread.stop()  # 새로운 stop 메서드 호출
                thread.join(1.0)  # 최대 1초 대기
                
                # 리스너 제거
                if name in self.listeners:
                    self.listeners.pop(name, None)
                
                logging.debug(f"'{name}' 스레드 중지됨")
                return True
        
        elif type_ == 'process':
            # 프로세스 중지
            if name in self.processes:
                process = self.processes[name]
                
                # 종료 명령 전송
                self.queues[name]['input'].put({
                    'command': 'stop'
                })
                
                # 프로세스 종료 대기
                process.join(2.0)
                if process.is_alive():
                    process.terminate()
                    process.join(1.0)
                
                # 리스너 제거
                if name in self.listeners:
                    self.listeners.pop(name, None)
                
                logging.debug(f"'{name}' 프로세스 중지됨")
                return True
        
        return False
    
    def work(self, name, method, *args, **kwargs):
        """
        비동기 작업 요청 (결과를 기다리지 않음)
        
        Args:
            name (str): 작업을 요청할 객체의 이름
            method (str): 호출할 메서드 이름
            *args: 메서드에 전달할 위치 인자
            **kwargs: 메서드에 전달할 키워드 인자
        
        Returns:
            bool: 요청 성공 여부
        """
        if self.shutting_down:
            return False
        
        if name not in self.types:
            logging.error(f"'{name}'은(는) 등록되지 않은 이름입니다.")
            return False
        
        type_ = self.types[name]
        
        if type_ is None:
            # 메인스레드 직접 호출
            return self._call_main_thread(name, method, args, kwargs, wait_result=False)
        
        elif type_ == 'thread':
            # 스레드에 요청
            return self._call_thread(name, method, args, kwargs, wait_result=False)
        
        elif type_ == 'process':
            # 프로세스에 요청
            return self._call_process(name, method, args, kwargs, wait_result=False)
        
        return False
    
    def answer(self, name, method, *args, callback=None, timeout=30, **kwargs):
        """
        동기 작업 요청 (결과를 기다림)
        
        Args:
            name (str): 작업을 요청할 객체의 이름
            method (str): 호출할 메서드 이름
            *args: 메서드에 전달할 위치 인자
            callback (callable, optional): 비동기 결과 처리를 위한 콜백 함수
            timeout (int, optional): 응답 대기 시간 (초)
            **kwargs: 메서드에 전달할 키워드 인자
        
        Returns:
            any: 작업 결과 (callback이 None이 아니면 None 반환)
        """
        if self.shutting_down:
            return None
        
        if name not in self.types:
            logging.error(f"'{name}'은(는) 등록되지 않은 이름입니다.")
            return None
        
        type_ = self.types[name]
        
        # 콜백이 지정되었으면 비동기로 처리
        if callback is not None:
            if type_ is None:
                # 메인스레드 직접 호출 후 콜백 실행
                result = self._call_main_thread(name, method, args, kwargs, wait_result=True)
                callback(result)
                return None
            
            elif type_ == 'thread':
                # 스레드에 요청 (콜백 전달)
                return self._call_thread(name, method, args, kwargs, wait_result=False, callback=callback)
            
            elif type_ == 'process':
                # 프로세스에 요청 (콜백 등록)
                return self._call_process(name, method, args, kwargs, wait_result=False, callback=callback)
        
        # 콜백이 없으면 동기로 처리
        else:
            if type_ is None:
                # 메인스레드 직접 호출
                return self._call_main_thread(name, method, args, kwargs, wait_result=True)
            
            elif type_ == 'thread':
                # 스레드에 요청하고 결과 대기
                return self._call_thread(name, method, args, kwargs, wait_result=True, timeout=timeout)
            
            elif type_ == 'process':
                # 프로세스에 요청하고 결과 대기
                return self._call_process(name, method, args, kwargs, wait_result=True, timeout=timeout)
        
        return None
    
    def _call_main_thread(self, name, method_name, args, kwargs, wait_result=True):
        """
        메인스레드 객체의 메서드 직접 호출 (내부 메서드)
        
        Args:
            name (str): 호출할 객체의 이름
            method_name (str): 호출할 메서드 이름
            args (tuple): 메서드에 전달할 위치 인자
            kwargs (dict): 메서드에 전달할 키워드 인자
            wait_result (bool): 결과를 기다릴지 여부
        
        Returns:
            any: 메서드 호출 결과 (wait_result가 False면 True/False 반환)
        """
        instance = self.instances.get(name)
        if instance is None:
            return None if wait_result else False
        
        method = getattr(instance, method_name, None)
        if method is None:
            logging.error(f"'{name}' 객체에 '{method_name}' 메서드가 없습니다.")
            return None if wait_result else False
        
        try:
            result = method(*args, **kwargs)
            return result if wait_result else True
        except Exception as e:
            logging.error(f"메서드 호출 오류: {e}", exc_info=True)
            return None if wait_result else False
    
    def _call_thread(self, name, method_name, args, kwargs, wait_result=True, timeout=30, callback=None):
        """
        스레드 객체의 메서드 호출 (내부 메서드)
        
        Args:
            name (str): 호출할 객체의 이름
            method_name (str): 호출할 메서드 이름
            args (tuple): 메서드에 전달할 위치 인자
            kwargs (dict): 메서드에 전달할 키워드 인자
            wait_result (bool): 결과를 기다릴지 여부
            timeout (int): 응답 대기 시간 (초)
            callback (callable, optional): 비동기 결과 처리를 위한 콜백 함수
        
        Returns:
            any: 메서드 호출 결과 (wait_result가 False면 True/False 반환)
        """
        thread = self.threads.get(name)
        if thread is None or not thread.is_alive():
            return None if wait_result else False
        
        task_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        
        if wait_result:
            # 동기식 호출
            result = [None]
            event = threading.Event()
            
            def _callback(res):
                result[0] = res
                event.set()
            
            # 태스크 전송
            thread.add_task(task_id, method_name, task_data, _callback)
            
            # 결과 대기
            if not event.wait(timeout):
                logging.warning(f"'{name}.{method_name}' 호출 타임아웃")
                return None
            
            return result[0]
        
        else:
            # 비동기식 호출
            thread.add_task(task_id, method_name, task_data, callback)
            return True
    
    def _call_process(self, name, method_name, args, kwargs, wait_result=True, timeout=30, callback=None):
        """
        프로세스 객체의 메서드 호출 (내부 메서드)
        
        Args:
            name (str): 호출할 객체의 이름
            method_name (str): 호출할 메서드 이름
            args (tuple): 메서드에 전달할 위치 인자
            kwargs (dict): 메서드에 전달할 키워드 인자
            wait_result (bool): 결과를 기다릴지 여부
            timeout (int): 응답 대기 시간 (초)
            callback (callable, optional): 비동기 결과 처리를 위한 콜백 함수
        
        Returns:
            any: 메서드 호출 결과 (wait_result가 False면 True/False 반환)
        """
        process = self.processes.get(name)
        if process is None or not process.is_alive():
            return None if wait_result else False
        
        queues = self.queues.get(name)
        if queues is None:
            return None if wait_result else False
        
        req_id = str(uuid.uuid4())
        
        # 콜백 등록
        if callback is not None:
            self.callbacks[req_id] = callback
        
        # 요청 전송
        queues['input'].put({
            'id': req_id,
            'method': method_name,
            'args': args,
            'kwargs': kwargs
        })
        
        # 결과를 기다리지 않으면 바로 반환
        if not wait_result:
            return True
        
        # 결과 대기
        start_time = time.time()
        while req_id not in self.result_dict:
            if time.time() - start_time > timeout:
                logging.warning(f"'{name}.{method_name}' 호출 타임아웃")
                return None
            time.sleep(0.01)
        
        # 결과 반환 및 정리
        result = self.result_dict[req_id]
        del self.result_dict[req_id]
        return result.get('result', None)
    
    def _process_listener(self, name):
        """
        프로세스 응답 리스너 (내부 메서드)
        
        Args:
            name (str): 리스닝할 프로세스의 이름
        """
        try:
            queues = self.queues.get(name)
            if queues is None:
                return
            
            output_queue = queues['output']
            
            while not self.shutting_down:
                try:
                    # 응답 가져오기 (타임아웃 설정하여 간격적으로 체크)
                    try:
                        response = output_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    
                    # 명령 처리
                    if 'command' in response:
                        cmd = response.get('command')
                        
                        if cmd == 'work':
                            # 비동기 호출 처리
                            res_id = response.get('id')
                            target = response.get('target')
                            method = response.get('method')
                            args = response.get('args', ())
                            kwargs = response.get('kwargs', {})
                            
                            # work 실행하고 완료 상태만 반환
                            success = self.work(target, method, *args, **kwargs)
                            
                            # 결과 저장 (성공/실패 여부만)
                            self.result_dict[res_id] = {
                                'status': 'success' if success else 'error',
                                'result': success
                            }
                            
                        elif cmd == 'answer':
                            # 동기 호출 처리
                            res_id = response.get('id')
                            target = response.get('target')
                            method = response.get('method')
                            args = response.get('args', ())
                            kwargs = response.get('kwargs', {})
                            
                            # answer 실행하고 결과 반환
                            result = self.answer(target, method, *args, **kwargs)
                            
                            # 결과 저장
                            self.result_dict[res_id] = {
                                'status': 'success',
                                'result': result
                            }
                            
                        continue
                    
                    # 응답 처리
                    req_id = response.get('id')
                    if req_id is None:
                        continue
                    
                    # 콜백 실행 (있는 경우)
                    if req_id in self.callbacks:
                        try:
                            callback = self.callbacks.pop(req_id)
                            result = response.get('result')
                            callback(result)
                        except Exception as e:
                            logging.error(f"콜백 실행 오류: {e}", exc_info=True)
                    
                    # 결과 저장
                    else:
                        self.result_dict[req_id] = response
                    
                except Exception as e:
                    logging.error(f"프로세스 응답 처리 오류: {e}", exc_info=True)
                    
        except Exception as e:
            logging.error(f"프로세스 리스너 오류: {e}", exc_info=True)
        
        finally:
            logging.debug(f"'{name}' 프로세스 리스너 종료")
    
    def _thread_listener(self, name):
        """
        스레드 응답 리스너 (내부 메서드)
        현재는 필요 없지만 확장성을 위해 남겨둠
        
        Args:
            name (str): 리스닝할 스레드의 이름
        """
        try:
            while not self.shutting_down:
                time.sleep(0.1)
                
        except Exception as e:
            logging.error(f"스레드 리스너 오류: {e}", exc_info=True)
        
        finally:
            logging.debug(f"'{name}' 스레드 리스너 종료")
    
    def cleanup(self):
        """모든 리소스 정리"""
        self.shutting_down = True
        logging.info("리소스 정리 중...")
        
        # 모든 객체 중지
        for name in list(self.types.keys()):
            self.stop(name)
        
        # 모든 큐 정리
        self.queues.clear()
        
        # Manager 종료
        if self.manager is not None:
            try:
                self.manager.shutdown()
            except:
                pass
            self.manager = None
        
        logging.info("모든 리소스 정리 완료")

class _WorkerThread(threading.Thread):
    """워커 스레드 클래스 (내부용)"""
    
    def __init__(self, name, target):
        super().__init__(daemon=True)
        self.name = name
        self.target = target
        self.running = True
        self.task_queue = queue.Queue()
        self.result_dict = {}
    
    def run(self):
        logging.debug(f"{self.name} 스레드 시작")
        
        while self.running:
            try:
                # 태스크 가져오기
                try:
                    task = self.task_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                task_id = task.get('id')
                method_name = task.get('method')
                task_data = task.get('data')
                callback = task.get('callback')
                
                # 메서드 찾기
                method = getattr(self.target, method_name, None)
                if not method:
                    if callback:
                        callback(None)
                    continue
                
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
            
            except Exception as e:
                logging.error(f"스레드 처리 오류: {e}", exc_info=True)
        
        logging.debug(f"{self.name} 스레드 종료")
    
    def add_task(self, task_id, method_name, task_data, callback=None):
        """태스크 추가"""
        self.task_queue.put({
            'id': task_id,
            'method': method_name,
            'data': task_data,
            'callback': callback
        })
    
    def stop(self):
        """스레드 중지"""
        self.running = False

def _process_worker(class_, name, input_queue, output_queue, result_dict):
    """
    프로세스 워커 함수
    
    Args:
        class_: 인스턴스화할 클래스
        name (str): 프로세스 이름
        input_queue (Queue): 입력 큐
        output_queue (Queue): 출력 큐
        result_dict (dict): 결과 저장용 딕셔너리
    """
    try:
        # 인스턴스 생성
        instance = class_()
        logging.debug(f"{name} 프로세스 초기화 완료")
        
        # 다른 객체로의 통신 메서드 추가
        def work(target, method, *args, **kwargs):
            """비동기 함수 호출"""
            res_id = str(uuid.uuid4())
            
            # 요청 전송
            output_queue.put({
                'id': res_id,
                'target': target,
                'command': 'work',
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            
            return True
        
        def answer(target, method, *args, timeout=10, **kwargs):
            """동기 함수 호출"""
            res_id = str(uuid.uuid4())
            
            # 요청 전송
            output_queue.put({
                'id': res_id,
                'target': target,
                'command': 'answer',
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            
            # 결과 대기
            start_time = time.time()
            while res_id not in result_dict:
                if time.time() - start_time > timeout:
                    logging.warning(f"요청 타임아웃: {target}.{method}")
                    return None
                time.sleep(0.01)
            
            # 결과 반환 및 정리
            result = result_dict[res_id]
            del result_dict[res_id]
            return result.get('result', None)
        
        # 인스턴스에 메서드 추가
        instance.work = work
        instance.answer = answer
        
        shutting_down = False
        # 메시지 처리 루프
        while not shutting_down:
            try:
                # 요청 가져오기
                try:
                    request = input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                # 종료 명령 확인
                if 'command' in request:
                    if request['command'] == 'stop':
                        shutting_down = True
                        logging.info(f"{name} 종료 명령 수신")
                        continue
                
                # 요청 정보 파싱
                req_id = request.get('id')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                
                # 메서드 찾기
                method = getattr(instance, method_name, None)
                if method is None:
                    logging.error(f"메서드 없음: {method_name}")
                    output_queue.put({
                        'id': req_id,
                        'status': 'error',
                        'error': f"메서드 없음: {method_name}",
                        'result': None
                    })
                    continue
                
                # 메서드 실행
                try:
                    result = method(*args, **kwargs)
                    output_queue.put({
                        'id': req_id,
                        'status': 'success',
                        'result': result
                    })
                except Exception as e:
                    logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                    output_queue.put({
                        'id': req_id,
                        'status': 'error',
                        'error': str(e),
                        'result': None
                    })
                
            except Exception as e:
                logging.error(f"메시지 처리 중 오류: {e}", exc_info=True)
    
    except Exception as e:
        logging.error(f"{name} 프로세스 오류: {e}", exc_info=True)
    
    finally:
        logging.info(f"{name} 프로세스 종료")

# 모듈 레벨 IPCManager 인스턴스
_ipc_manager = None

def get_ipc_manager():
    """
    IPCManager 인스턴스를 반환
    
    Returns:
        IPCManager: 전역 IPCManager 인스턴스
    """
    global _ipc_manager
    
    if _ipc_manager is None:
        _ipc_manager = IPCManager()
    
    return _ipc_manager

def register(name, instance, type_=None, start=False):
    """
    객체 등록 (모듈 레벨 함수)
    
    Args:
        name (str): 등록할 객체의 이름
        instance: 등록할 객체 인스턴스
        type_ (str, optional): 객체 유형 (None=메인스레드, 'thread'=멀티스레드, 'process'=멀티프로세스)
        start (bool, optional): 등록 후 바로 시작할지 여부
    
    Returns:
        instance: 등록된 객체 인스턴스
    """
    return get_ipc_manager().register(name, instance, type_, start)

def work(name, method, *args, **kwargs):
    """
    비동기 작업 요청 (모듈 레벨 함수)
    
    Args:
        name (str): 작업을 요청할 객체의 이름
        method (str): 호출할 메서드 이름
        *args: 메서드에 전달할 위치 인자
        **kwargs: 메서드에 전달할 키워드 인자
    
    Returns:
        bool: 요청 성공 여부
    """
    return get_ipc_manager().work(name, method, *args, **kwargs)

def answer(name, method, *args, callback=None, timeout=30, **kwargs):
    """
    동기 작업 요청 (모듈 레벨 함수)
    
    Args:
        name (str): 작업을 요청할 객체의 이름
        method (str): 호출할 메서드 이름
        *args: 메서드에 전달할 위치 인자
        callback (callable, optional): 비동기 결과 처리를 위한 콜백 함수
        timeout (int, optional): 응답 대기 시간 (초)
        **kwargs: 메서드에 전달할 키워드 인자
    
    Returns:
        any: 작업 결과 (callback이 None이 아니면 None 반환)
    """
    return get_ipc_manager().answer(name, method, *args, callback=callback, timeout=timeout, **kwargs)

def start(name):
    """
    등록된 객체 시작 (모듈 레벨 함수)
    
    Args:
        name (str): 시작할 객체의 이름
    
    Returns:
        bool: 성공 여부
    """
    return get_ipc_manager().start(name)

def stop(name):
    """
    등록된 객체 중지 (모듈 레벨 함수)
    
    Args:
        name (str): 중지할 객체의 이름
    
    Returns:
        bool: 성공 여부
    """
    return get_ipc_manager().stop(name)

def cleanup():
    """
    모든 리소스 정리 (모듈 레벨 함수)
    """
    global _ipc_manager
    
    if _ipc_manager is not None:
        _ipc_manager.cleanup()
        _ipc_manager = None

if __name__ == "__main__":
    import multiprocessing

    from worker import MainWorker, ThreadWorker, ProcessWorker, APITest
    from public import init_logger
    
    # 로깅 설정
    init_logger()
    
    # Windows에서는 'spawn'을 기본으로 설정
    multiprocessing.set_start_method('spawn', force=True)
    
    try:
        logging.info("=== IPCManager 테스트 시작 ===")
        
        # 1. 등록 및 시작 테스트
        logging.info("=== 등록 및 시작 테스트 ===")
        
        # 메인스레드 워커 등록
        main_worker = register('main', MainWorker("Main"), start=True)
        logging.info(f"메인스레드 워커 등록: {main_worker is not None}")
        
        # 스레드 워커 등록
        thread_worker = register('thread', ThreadWorker("Thread"), 'thread', start=True)
        logging.info(f"스레드 워커 등록: {thread_worker is not None}")
        
        # 프로세스 워커 등록
        process_worker = register('process', ProcessWorker(), 'process', start=True)
        logging.info(f"프로세스 워커 등록: {process_worker is not None}")
        
        # 추가 스레드 워커 등록 (나중에 사용)
        thread_worker2 = register('thread2', ThreadWorker("Thread2"), 'thread', start=True)
        logging.info(f"추가 스레드 워커 등록: {thread_worker2 is not None}")
        
        # 추가 프로세스 워커 등록 (나중에 사용)
        process_worker2 = register('process2', ProcessWorker(), 'process', start=True)
        logging.info(f"추가 프로세스 워커 등록: {process_worker2 is not None}")
        
        # 잠시 대기
        time.sleep(1)

            # 키움 API 테스트
        logging.info("=== 키움 API 테스트 ===")
        api_server = register('api', APITest(), 'process', start=True)
        work('api', 'kiwoom_login')
        result = answer('api', 'fetch_data', param='005930')
        logging.info(f"API 서버 연결 상태: {result}")
        
        # 2. 메인 → 다른 객체 통신 테스트
        logging.info("=== 메인 → 다른 객체 통신 테스트 ===")
        
        # 메인 → 스레드 (동기)
        start_time = time.time()
        result = answer('thread', 'echo', "메인에서 스레드로 동기 호출")
        elapsed = time.time() - start_time
        logging.info(f"메인 → 스레드 (동기) 결과: {result}, 소요시간: {elapsed:.6f}초")
        
        # 메인 → 스레드 (비동기)
        callback_result = [None]
        callback_event = threading.Event()
        
        def on_result(result):
            callback_result[0] = result
            callback_event.set()
        
        start_time = time.time()
        answer('thread', 'echo', "메인에서 스레드로 비동기 호출", callback=on_result)
        callback_event.wait(timeout=1)
        elapsed = time.time() - start_time
        logging.info(f"메인 → 스레드 (비동기) 결과: {callback_result[0]}, 소요시간: {elapsed:.6f}초")
        
        # 메인 → 프로세스 (동기)
        start_time = time.time()
        result = answer('process', 'echo', "메인에서 프로세스로 동기 호출")
        elapsed = time.time() - start_time
        logging.info(f"메인 → 프로세스 (동기) 결과: {result}, 소요시간: {elapsed:.6f}초")
        
        # 메인 → 프로세스 (비동기)
        callback_result = [None]
        callback_event = threading.Event()
        
        def on_result(result):
            callback_result[0] = result
            callback_event.set()
        
        start_time = time.time()
        answer('process', 'echo', "메인에서 프로세스로 비동기 호출", callback=on_result)
        callback_event.wait(timeout=1)
        elapsed = time.time() - start_time
        logging.info(f"메인 → 프로세스 (비동기) 결과: {callback_result[0]}, 소요시간: {elapsed:.6f}초")
        
        # ID 확인
        main_thread_id = threading.get_ident()
        main_process_id = multiprocessing.current_process().pid
        
        thread_thread_id = answer('thread', 'get_thread_id')
        thread_process_id = answer('thread', 'get_process_id')
        
        process_thread_id = answer('process', 'get_thread_id')
        process_process_id = answer('process', 'get_process_id')
        
        logging.info(f"메인 ID: 스레드={main_thread_id}, 프로세스={main_process_id}")
        logging.info(f"스레드 ID: 스레드={thread_thread_id}, 프로세스={thread_process_id}")
        logging.info(f"프로세스 ID: 스레드={process_thread_id}, 프로세스={process_process_id}")
        
        # 3. 스레드 → 다른 객체 통신 테스트
        logging.info("=== 스레드 → 다른 객체 통신 테스트 ===")
        
        # 스레드 → 메인
        result = answer('thread', 'call_another', 'main', 'echo', "스레드에서 메인으로 호출")
        logging.info(f"스레드 → 메인 결과: {result}")
        
        # 스레드 → 다른 스레드
        result = answer('thread', 'call_another', 'thread2', 'echo', "스레드에서 다른 스레드로 호출")
        logging.info(f"스레드 → 다른 스레드 결과: {result}")
        
        # 스레드 → 프로세스
        result = answer('thread', 'call_another', 'process', 'echo', "스레드에서 프로세스로 호출")
        logging.info(f"스레드 → 프로세스 결과: {result}")
        
        # 4. 프로세스 → 다른 객체 통신 테스트
        logging.info("=== 프로세스 → 다른 객체 통신 테스트 ===")
        
        # 프로세스 → 메인
        result = answer('process', 'call_another', 'main', 'echo', "프로세스에서 메인으로 호출")
        logging.info(f"프로세스 → 메인 결과: {result}")
        
        # 프로세스 → 스레드
        result = answer('process', 'call_another', 'thread', 'echo', "프로세스에서 스레드로 호출")
        logging.info(f"프로세스 → 스레드 결과: {result}")
        
        # 프로세스 → 다른 프로세스
        result = answer('process', 'call_another', 'process2', 'echo', "프로세스에서 다른 프로세스로 호출")
        logging.info(f"프로세스 → 다른 프로세스 결과: {result}")
        
        # 5. 속도 테스트
        logging.info("=== 속도 테스트 ===")
        
        iterations = 100
        total_time_main = 0
        total_time_thread = 0
        total_time_process = 0
        
        # 메인 호출 속도
        for i in range(iterations):
            start_time = time.time()
            answer('main', 'add', i, i+1)
            elapsed = time.time() - start_time
            total_time_main += elapsed
        
        avg_time_main = total_time_main / iterations
        logging.info(f"메인 호출 평균 시간: {avg_time_main:.6f}초")
        
        # 스레드 호출 속도
        for i in range(iterations):
            start_time = time.time()
            answer('thread', 'add', i, i+1)
            elapsed = time.time() - start_time
            total_time_thread += elapsed
        
        avg_time_thread = total_time_thread / iterations
        logging.info(f"스레드 호출 평균 시간: {avg_time_thread:.6f}초")
        
        # 프로세스 호출 속도
        for i in range(iterations):
            start_time = time.time()
            answer('process', 'add', i, i+1)
            elapsed = time.time() - start_time
            total_time_process += elapsed
        
        avg_time_process = total_time_process / iterations
        logging.info(f"프로세스 호출 평균 시간: {avg_time_process:.6f}초")
        
        # 6. 오류 처리 테스트
        logging.info("=== 오류 처리 테스트 ===")
        
        # 존재하지 않는 객체 호출
        result = answer('non_existent', 'echo', "이 호출은 실패해야 함")
        logging.info(f"존재하지 않는 객체 호출 결과: {result}")
        
        # 존재하지 않는 메서드 호출
        result = answer('main', 'non_existent_method', "이 호출은 실패해야 함")
        logging.info(f"존재하지 않는 메서드 호출 결과: {result}")
        
        # 타임아웃 테스트
        start_time = time.time()
        result = answer('thread', 'sleep', 3, timeout=1)
        elapsed = time.time() - start_time
        logging.info(f"타임아웃 테스트 결과: {result}, 소요시간: {elapsed:.6f}초")
        
        # 7. 자원 정리 테스트
        logging.info("=== 자원 정리 테스트 ===")
        
        # 개별 객체 중지
        result = stop('thread2')
        logging.info(f"thread2 중지 결과: {result}")
        
        result = stop('process2')
        logging.info(f"process2 중지 결과: {result}")
        
        # 8. 전체 정리
        logging.info("=== 모든 자원 정리 ===")
        cleanup()
        logging.info("모든 자원 정리 완료")
        
        logging.info("=== IPCManager 테스트 완료 ===")
        
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {e}", exc_info=True)
        
        # 오류 발생 시에도 자원 정리
        cleanup()

