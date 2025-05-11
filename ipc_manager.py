import logging
import threading
import uuid
import time
import queue
import multiprocessing as mp

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
        
        # 이벤트 기반 결과 처리를 위한 딕셔너리
        self.results = {}  # id -> (event, result)
        
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
        
        input_queue = mp.Queue()
        output_queue = mp.Queue()
        
        self.queues[name] = {
            'input': input_queue,
            'output': output_queue
        }
        
        # 프로세스 객체 생성
        process = mp.Process(
            target=_process_worker,
            args=(class_, name, input_queue, output_queue),
            daemon=True
        )
        
        self.processes[name] = process
        self.instances[name] = None  # 프로세스는 별도 프로세스에서 실행되므로 None으로 설정

    # IPCManager 클래스 내에서 work 메소드 재정의
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

    # IPCManager 클래스 내에서 answer 메소드 재정의
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
                
                # # 리스너 스레드 시작 (결과 처리용)
                # if name not in self.listeners:
                #     listener = threading.Thread(
                #         target=self._thread_listener,
                #         args=(name,),
                #         daemon=True
                #     )
                #     self.listeners[name] = listener
                #     listener.start()
                
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
            event = threading.Event()
            result_container = [None]
            
            def _callback(res):
                result_container[0] = res
                event.set()
            
            # 태스크 전송
            thread.add_task(task_id, method_name, task_data, _callback)
            
            # 결과 대기 (이벤트 기반)
            if not event.wait(timeout):
                logging.warning(f"'{name}.{method_name}' 호출 타임아웃")
                return None
            
            return result_container[0]
        
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
        
        # 콜백 또는 이벤트 등록
        if wait_result:
            event = threading.Event()
            self.results[req_id] = (event, None)
        elif callback is not None:
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
        
        # 결과 대기 (이벤트 기반)
        if not event.wait(timeout):
            # 타임아웃 시 리소스 정리
            if req_id in self.results:
                del self.results[req_id]
            logging.warning(f"'{name}.{method_name}' 호출 타임아웃")
            return None
        
        # 결과 반환 및 정리
        _, result = self.results.pop(req_id)
        return result
    
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
            input_queue = queues['input']
            
            while not self.shutting_down:
                try:
                    # 응답 가져오기 (논블로킹 방식)
                    try:
                        response = output_queue.get(block=False)
                    except queue.Empty:
                        # 거의 대기하지 않고 바로 다음 반복으로 (CPU 부하 줄이기 위해 최소 sleep)
                        time.sleep(0.0001)
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
                            
                            # work 실행
                            success = self.work(target, method, *args, **kwargs)
                            input_queue.put({
                                'id': res_id,
                                'status': 'success' if success else 'error',
                                'result': success
                            })
                        
                        elif cmd == 'answer':
                            # 동기 호출 처리
                            res_id = response.get('id')
                            target = response.get('target')
                            method = response.get('method')
                            args = response.get('args', ())
                            kwargs = response.get('kwargs', {})
                            
                            logging.debug(f"[{name}_listener] answer 명령 수신: {target}.{method}, res_id={res_id}")
                            
                            # 메인 프로세스를 통해 다른 객체 호출 (self.answer 대신 직접 호출)
                            result = None
                            try:
                                # 이 부분을 수정: 명령 라우팅을 위해 올바른 큐에 메시지 전달
                                # 메인 프로세스에 전달하기 위해 output_queue 사용
                                output_queue.put({
                                    'command': 'route_request',
                                    'id': res_id,
                                    'target': target,
                                    'method': method,
                                    'args': args,
                                    'kwargs': kwargs,
                                    'source': name  # 출처 추가
                                })
                                
                                # 결과 대기
                                logging.debug(f"[{name}_listener] 대상 객체 호출 후 결과 대기: {target}.{method}")
                                wait_start = time.time()
                                wait_timeout = 10  # 10초 타임아웃
                                
                                while time.time() - wait_start < wait_timeout:
                                    try:
                                        # 입력 큐에서 결과 확인
                                        resp = input_queue.get(block=False)
                                        
                                        # 우리가 기다리는 응답인지 확인
                                        if resp.get('response_for') == res_id:
                                            result = resp.get('result')
                                            logging.debug(f"[{name}_listener] 응답 수신 성공: {target}.{method}")
                                            break
                                        else:
                                            # 다른 응답은 다시 큐에 넣음
                                            input_queue.put(resp)
                                    except queue.Empty:
                                        time.sleep(0.0001)
                                
                                if result is None:
                                    logging.warning(f"[{name}_listener] 응답 대기 타임아웃: {target}.{method}")
                            
                            except Exception as e:
                                logging.error(f"[{name}_listener] 호출 중 오류: {e}", exc_info=True)
                            
                            # 결과를 원래 요청 프로세스에 전달
                            logging.debug(f"[{name}_listener] 호출 결과 전송: {res_id}, 결과 타입={type(result)}")
                            output_queue.put({  # output_queue로 수정
                                'id': res_id,
                                'status': 'success' if result is not None else 'error',
                                'result': result
                            })
                        # 'route_request' 명령 처리 추가
                        elif cmd == 'route_request':
                            req_id = response.get('id')
                            target = response.get('target')
                            method = response.get('method')
                            args = response.get('args', ())
                            kwargs = response.get('kwargs', {})
                            source = response.get('source')
                            
                            logging.debug(f"라우팅 요청 수신: {source} -> {target}.{method}, req_id={req_id}")
                            
                            # 목표 객체의 type 확인
                            if target not in self.types:
                                logging.error(f"타겟 '{target}'이 등록되지 않았습니다. req_id={req_id}")
                                if source in self.queues:
                                    self.queues[source]['input'].put({
                                        'response_for': req_id,
                                        'result': None
                                    })
                                continue
                                
                            target_type = self.types[target]
                            
                            # 타겟이 프로세스인 경우 해당 프로세스의 큐로 직접 전달
                            if target_type == 'process' and target in self.queues:
                                logging.debug(f"프로세스간 직접 라우팅: {source} -> {target}.{method}, req_id={req_id}")
                                # 목표 프로세스의 입력 큐로 요청 전달
                                target_req_id = str(uuid.uuid4())
                                self.queues[target]['input'].put({
                                    'id': target_req_id,
                                    'method': method,
                                    'args': args,
                                    'kwargs': kwargs
                                })
                                
                                # 결과 기다리기
                                wait_start = time.time()
                                wait_timeout = 5
                                result = None
                                
                                while time.time() - wait_start < wait_timeout:
                                    try:
                                        # 목표 프로세스의 출력 큐에서 결과 확인
                                        resp = self.queues[target]['output'].get(block=False)
                                        if resp.get('id') == target_req_id:
                                            result = resp.get('result')
                                            break
                                        else:
                                            # 다른 응답은 큐에 다시 넣기
                                            self.queues[target]['output'].put(resp)
                                    except queue.Empty:
                                        time.sleep(0.001)
                            # 다른 모든 경우(메인스레드, 멀티스레드)는 메인스레드에서 처리
                            else:
                                # 안전하게 메인스레드에서 실행
                                result = self.answer(target, method, *args, **kwargs)
                            
                            # 결과를 출처 프로세스로 다시 보냄
                            if source in self.queues:
                                logging.debug(f"라우팅 결과 전송: {target}.{method} -> {source}, req_id={req_id}, result={result}")
                                self.queues[source]['input'].put({
                                    'response_for': req_id,
                                    'result': result
                                })
                            else:
                                logging.error(f"출처 프로세스 큐를 찾을 수 없음: {source}")   
                        elif cmd == 'process_call':
                            # 프로세스에서 발생한 호출 처리 (단순화된 버전)
                            req_id = response.get('id')
                            target = response.get('target')
                            method = response.get('method')
                            args = response.get('args', ())
                            kwargs = response.get('kwargs', {})
                            
                            #logging.debug(f"프로세스 호출 처리: {name} -> {target}.{method}, req_id={req_id}")
                            
                            # 목표 객체 메서드 호출 (IPCManager가 직접 처리)
                            result = None
                            try:
                                result = self.answer(target, method, *args, **kwargs)
                            except Exception as e:
                                logging.error(f"메서드 호출 오류: {e}", exc_info=True)
                            
                            # 결과를 요청 프로세스로 다시 보냄
                            #logging.debug(f"프로세스 호출 결과 전송: {target}.{method}, req_id={req_id}")
                            input_queue.put({
                                'id': req_id,
                                'status': 'success',
                                'result': result
                            })                                              
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
                    
                    # 이벤트 기반 결과 처리
                    elif req_id in self.results:
                        event, _ = self.results[req_id]
                        self.results[req_id] = (event, response.get('result'))
                        event.set()
                    
                except Exception as e:
                    logging.error(f"프로세스 응답 처리 오류: {e}", exc_info=True)
                    time.sleep(0.0001)  # 오류 발생 시 짧은 대기
        
        except Exception as e:
            logging.error(f"프로세스 리스너 오류: {e}", exc_info=True)
        
        finally:
            logging.debug(f"'{name}' 프로세스 리스너 종료")
    
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
        
        # 결과 컨테이너 정리
        self.results.clear()
        self.callbacks.clear()
        
        logging.info("모든 리소스 정리 완료")

class _WorkerThread(threading.Thread):
    """워커 스레드 클래스 (내부용)"""
    
    def __init__(self, name, target):
        super().__init__(daemon=True)
        self.name = name
        self.target = target
        self.running = True
        self.task_queue = queue.Queue()
    
    def run(self):
        #logging.debug(f"{self.name} 스레드 시작")
        
        while self.running:
            try:
                # 태스크 가져오기 (논블로킹 방식)
                try:
                    task = self.task_queue.get(block=False)
                except queue.Empty:
                    # 최소 대기 후 다음 반복
                    time.sleep(0.0001)
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
                time.sleep(0.0001)  # 오류 발생 시 짧은 대기
        
        #logging.debug(f"{self.name} 스레드 종료")
    
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

def _process_worker(class_, name, input_queue, output_queue):
    """
    프로세스 워커 함수
    
    Args:
        class_: 인스턴스화할 클래스
        name (str): 프로세스 이름
        input_queue (Queue): 입력 큐
        output_queue (Queue): 출력 큐
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
                'command': 'work',
                'target': target,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            
            # 결과를 기다리지 않고 성공 여부만 반환
            return True
        
        def answer(target, method, *args, timeout=10, **kwargs):
            """동기 함수 호출"""
            res_id = str(uuid.uuid4())

            # 요청 전송 로그 추가
            #logging.debug(f"[{name}] answer 요청 전송: {target}.{method}, req_id={res_id}")
                        
            # 요청 전송
            output_queue.put({
                'id': res_id,
                'command': 'process_call',
                'target': target,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })

            # 응답 대기 시작 로그 추가
            #logging.debug(f"[{name}] answer 응답 대기 시작: {target}.{method}, req_id={res_id}")
                
            # 응답 대기
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = input_queue.get(block=False)
                    if response.get('id') == res_id:
                        # 응답 수신 로그 추가
                        #logging.debug(f"[{name}] answer 응답 수신: {target}.{method}, req_id={res_id}")
                        return response.get('result')
                    else:
                        # 다른 응답은 다시 큐에 넣음
                        input_queue.put(response)
                except queue.Empty:
                    time.sleep(0.0001)
            
            #logging.warning(f"[{name}] 요청 타임아웃: {target}.{method}, req_id={res_id}")
            return None
        
        # 인스턴스에 메서드 추가
        instance.work = work
        instance.answer = answer
        
        shutting_down = False
        # 메시지 처리 루프
        while not shutting_down:
            try:
                # 요청 가져오기 (논블로킹 방식)
                try:
                    request = input_queue.get(block=False)
                except queue.Empty:
                    time.sleep(0.0001)  # 최소 대기
                    continue

                # 응답 메시지와 요청 메시지 구분
                if 'status' in request and 'id' in request and 'method' not in request:
                    # 이것은 응답 메시지임 - 다른 처리 로직으로 라우팅
                    try:
                        # 여기서는 프로세스 내 응답 처리 로직을 구현
                        # 예: 콜백 호출 또는 비동기 작업 완료 처리
                        #logging.debug(f"[{name}] 응답 메시지 처리: {request}")
                        continue  # 다음 메시지로 진행
                    except Exception as e:
                        logging.error(f"응답 처리 오류: {e}", exc_info=True)
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

                # 필수 필드 검증
                if req_id is None:
                    logging.error(f"요청 ID가 없는 잘못된 메시지 무시: {request}")
                    continue

                # method_name이 문자열인지 확인
                if not isinstance(method_name, str):
                    logging.error(f"메서드 이름이 문자열이 아닙니다: {type(method_name)}, 요청: {request}")
                    output_queue.put({
                        'id': req_id,
                        'status': 'error',
                        'error': f"메서드 이름이 문자열이 아닙니다: {type(method_name)}",
                        'result': None
                    })
                    continue

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
                time.sleep(0.0001)  # 오류 발생 시 짧은 대기
    
    except Exception as e:
        logging.error(f"{name} 프로세스 오류: {e}", exc_info=True)
    
    finally:
        logging.info(f"{name} 프로세스 종료")

if __name__ == "__main__":
    import logging
    import threading
    import time
    from worker import Admin, Strategy, DBManager, APIModule, ChartManager
    from worker import test_stg_to_api, test_stg_to_cht
    
    # 로깅 설정
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # 글로벌 매니저 생성
    class GlobalManager:
        def __init__(self):
            self.ipc = IPCManager()
    
    gm = GlobalManager()
    
    # 객체 생성 및 등록
    admin = Admin()
    gm.ipc.register('admin', admin)
    
    stg = Strategy()
    gm.ipc.register('stg', stg, 'thread', start=True)
    
    dbm = DBManager()
    gm.ipc.register('dbm', dbm, 'process', start=True)
    
    api = APIModule()
    gm.ipc.register('api', api, 'process', start=True)
    
    # 원래 의도는 api 프로세스에서 초기화 하는 것이었음 에러 때문에 그냥 둠
    # 여기서 생성하면 stg와 같은 것이 됨
    # 멀티 프로세스 내의 쓰레드는 프로세스내에서 간접적으로 연결 해야 함
    cht = ChartManager() 
    gm.ipc.register('cht', cht, 'thread', start=True) 
    
    # 모든 객체가 시작될 때까지 잠시 대기
    time.sleep(1)

    # cht 초기화
    #gm.ipc.work('api', 'init_chart_thread')
    
    # 테스트 시작
    logging.info("===== 테스트 시작 =====")
    
    # 1. admin -> dbm (work & answer)
    logging.info("\n----- admin -> dbm 테스트 -----")
    gm.ipc.work('dbm', 'echo_test', "Admin에서 DBM으로 work")
    data, success = gm.ipc.answer('dbm', 'echo_test', "Admin에서 DBM으로 answer")
    logging.info(f"결과: {data}, {success}")
    
    # 2. admin -> api (work & answer)
    logging.info("\n----- admin -> api 테스트 -----")
    gm.ipc.work('api', 'echo_test', "Admin에서 API로 work")
    data, success = gm.ipc.answer('api', 'api_request', "파라미터1", "파라미터2")
    logging.info(f"결과 타입: {type(data)}, 성공: {success}")
    if isinstance(data, list):
        logging.info(f"리스트 길이: {len(data)}")
    
    # 3. admin -> cht (work & answer)
    logging.info("\n----- admin -> cht 테스트 -----")
    gm.ipc.work('cht', 'echo_test', "Admin에서 CHT로 work")
    data, success = gm.ipc.answer('cht', 'echo_test', "Admin에서 CHT로 answer")
    logging.info(f"결과: {data}, {success}")
    
    # 4. stg -> api (work & answer)
    logging.info("\n----- stg -> api 테스트 -----")
    stg_test_thread = threading.Thread(target=test_stg_to_api, args=(stg,))
    stg_test_thread.start()
    stg_test_thread.join()
    
    # 5. stg -> cht (work & answer)
    logging.info("\n----- stg -> cht 테스트 -----")
    stg_to_cht_thread = threading.Thread(target=test_stg_to_cht, args=(stg,))
    stg_to_cht_thread.start()
    stg_to_cht_thread.join()
    
    # 6. dbm -> api (work & answer)
    logging.info("\n----- dbm -> api 테스트 -----")
    result = gm.ipc.answer('dbm', 'call_api')
    logging.info(f"DBM->API 결과: {result}")
    
    # 7. dbm -> cht (work & answer)
    logging.info("\n----- dbm -> cht 테스트 -----")
    result = gm.ipc.answer('dbm', 'call_cht')
    logging.info(f"DBM->CHT 결과: {result}")
    
    # 테스트 종료
    logging.info("\n===== 테스트 완료 =====")
    
    # 모든 리소스 정리
    gm.ipc.cleanup()