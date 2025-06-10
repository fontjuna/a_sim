import multiprocessing as mp
from PyQt5.QtCore import QThread
import time
import uuid
import logging
import queue
import threading
from queue import Queue, Empty
from PyQt5.QtWidgets import QApplication
import sys
from PyQt5.QAxContainer import QAxWidget
import pythoncom
from public import init_logger

WAIT_TIMEOUT = 15
HIGH_FREQ_TIMEOUT = 0.001  # 1ms 고빈도 처리

class SimpleManager:
   """컴포넌트 관리자"""
   
   def __init__(self, name, cls, comm_type, *args, **kwargs):
       self.name, self.comm_type = name, comm_type
       
       if comm_type == 'thread':
           self.instance = QThreadComponent(name, cls, *args, **kwargs)
       elif comm_type == 'process':
           self.instance = ProcessComponent(name, cls, *args, **kwargs)
       else:
           self.instance = cls(*args, **kwargs)
       
       ComponentRegistry.register(name, self.instance)
   
   def start(self):
       """컴포넌트 시작"""
       if self.comm_type in ['thread', 'process']:
           self.instance.start()
       elif hasattr(self.instance, 'initialize'):
           self.instance.initialize()
       
       # None type도 인터페이스 주입
       if self.comm_type is None:
           self._inject_interfaces_for_none()
       
       logging.info(f"[{self.name}] 시작")
   
   def stop(self):
       """컴포넌트 중지"""
       if self.comm_type in ['thread', 'process']:
           self.instance.stop()
       elif hasattr(self.instance, 'cleanup'):
           self.instance.cleanup()
       logging.info(f"[{self.name}] 중지")

   def order(self, target, method, *args, **kwargs):
       """통일된 order 인터페이스 - target 필수"""
       if hasattr(self.instance, 'order'):
           return self.instance.order(target, method, *args, **kwargs)
       else:
           return self._direct_call_with_target(target, method, *args, **kwargs)
   
   def answer(self, target, method, *args, **kwargs):
       """통일된 answer 인터페이스 - target 필수"""
       if hasattr(self.instance, 'answer'):
           return self.instance.answer(target, method, *args, **kwargs)
       else:
           return self._direct_call_with_target(target, method, *args, **kwargs)
   
   def frq_order(self, target, method, *args, **kwargs):
       """고빈도 order 인터페이스 - target 필수"""
       if hasattr(self.instance, 'frq_order'):
           return self.instance.frq_order(target, method, *args, **kwargs)
       else:
           return self._direct_call_with_target(target, method, *args, **kwargs)
   
   def frq_answer(self, target, method, *args, **kwargs):
       """고빈도 answer 인터페이스 - target 필수"""
       if hasattr(self.instance, 'frq_answer'):
           return self.instance.frq_answer(target, method, *args, **kwargs)
       else:
           return self._direct_call_with_target(target, method, *args, **kwargs)
   
   def _inject_interfaces_for_none(self):
       """None type 인터페이스 주입"""
       def order(target, method, *args, **kwargs):
           if target == self.name:  # 자기 자신 호출
               if hasattr(self.instance, method):
                   getattr(self.instance, method)(*args, **kwargs)
           else:  # 다른 컴포넌트 호출
               if target_component := ComponentRegistry.get(target):
                   if hasattr(target_component, 'order'):
                       target_component.order(target, method, *args, **kwargs)
                   elif hasattr(target_component, method):
                       getattr(target_component, method)(*args, **kwargs)
       
       def answer(target, method, *args, **kwargs):
           if target == self.name:  # 자기 자신 호출
               if hasattr(self.instance, method):
                   return getattr(self.instance, method)(*args, **kwargs)
           else:  # 다른 컴포넌트 호출
               if target_component := ComponentRegistry.get(target):
                   if hasattr(target_component, 'answer'):
                       return target_component.answer(target, method, *args, **kwargs)
                   elif hasattr(target_component, method):
                       return getattr(target_component, method)(*args, **kwargs)
           return None
       
       def frq_order(target, method, *args, **kwargs):
           if target == self.name:  # 자기 자신 호출
               if hasattr(self.instance, method):
                   getattr(self.instance, method)(*args, **kwargs)
           else:  # 다른 컴포넌트 호출
               if target_component := ComponentRegistry.get(target):
                   if hasattr(target_component, 'frq_order'):
                       target_component.frq_order(target, method, *args, **kwargs)
                   elif hasattr(target_component, method):
                       getattr(target_component, method)(*args, **kwargs)
       
       def frq_answer(target, method, *args, **kwargs):
           if target == self.name:  # 자기 자신 호출
               if hasattr(self.instance, method):
                   return getattr(self.instance, method)(*args, **kwargs)
           else:  # 다른 컴포넌트 호출
               if target_component := ComponentRegistry.get(target):
                   if hasattr(target_component, 'frq_answer'):
                       return target_component.frq_answer(target, method, *args, **kwargs)
                   elif hasattr(target_component, method):
                       return getattr(target_component, method)(*args, **kwargs)
           return None
       
       self.instance.order = order
       self.instance.answer = answer
       self.instance.frq_order = frq_order
       self.instance.frq_answer = frq_answer
   
   def _direct_call_with_target(self, target, method, *args, **kwargs):
       """None type용 - target 파라미터 포함"""
       if target == self.name:  # 자기 자신 호출
           if hasattr(self.instance, method):
               return getattr(self.instance, method)(*args, **kwargs)
       else:  # 다른 컴포넌트 호출
           if target_component := ComponentRegistry.get(target):
               if hasattr(target_component, method):
                   return getattr(target_component, method)(*args, **kwargs)
       return None
       
   def __getattr__(self, name):
       return getattr(self.instance, name)
   
class ComponentRegistry:
    """컴포넌트 레지스트리"""
    _components = {}
    
    @classmethod
    def register(cls, name, component):
        cls._components[name] = component
        logging.info(f"컴포넌트 등록: {name}")
    
    @classmethod
    def get(cls, name):
        return cls._components.get(name)

class QThreadComponent(QThread):
    """QThread 래퍼 - 고성능"""
    
    def __init__(self, name, cls, *args, **kwargs):
        super().__init__()
        self.name, self.cls = name, cls
        self.init_args, self.init_kwargs = args, kwargs
        self.instance, self.running = None, False
    
    def start(self):
        """QThread 시작"""
        self.running = True
        QThread.start(self)
        time.sleep(0.5)
    
    def stop(self):
        """QThread 중지"""
        self.running = False
        self.quit()
        self.wait(1000)
        if self.isRunning(): 
            self.terminate()
    
    def run(self):
        """QThread 메인 루프"""
        try:
            self.instance = self.cls(*self.init_args, **self.init_kwargs)
            self._inject_interfaces()
            self._initialize_instance()
            self._run_main_loop()
            self._cleanup_instance()
        except Exception as e:
            logging.error(f"[{self.name}] QThread 실행 오류: {e}")
    
    def _inject_interfaces(self):
        """QThread 인터페이스 주입"""
        def order(target, method, *args, **kwargs):
            self.frq_order(target, method, *args, **kwargs)
        
        def answer(target, method, *args, **kwargs):
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, 'answer'):
                        result = target_component.answer(target, method, *args, **kwargs)
                    elif hasattr(target_component, method):
                        result = getattr(target_component, method)(*args, **kwargs)
                    else:
                        logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                        return None
                    logging.debug(f"[{self.name}] answer {target}.{method} 완료")
                    return result
                except Exception as e:
                    logging.error(f"[{self.name}] answer {target}.{method} 오류: {e}")
                    return None
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")
                return None
        
        def frq_order(target, method, *args, **kwargs):
            return self.frq_order(target, method, *args, **kwargs)
        
        def frq_answer(target, method, *args, **kwargs):
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, 'frq_answer'):
                        result = target_component.frq_answer(target, method, *args, **kwargs)
                    elif hasattr(target_component, method):
                        result = getattr(target_component, method)(*args, **kwargs)
                    else:
                        logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                        return None
                    logging.debug(f"[{self.name}] frq_answer {target}.{method} 완료")
                    return result
                except Exception as e:
                    logging.error(f"[{self.name}] frq_answer {target}.{method} 오류: {e}")
                    return None
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")
                return None
        
        self.instance.order = order
        self.instance.answer = answer
        self.instance.frq_order = frq_order
        self.instance.frq_answer = frq_answer
    
    def _initialize_instance(self):
        """인스턴스 초기화"""
        if hasattr(self.instance, 'initialize'): 
            self.instance.initialize()
        logging.info(f"[{self.name}] QThread 시작")
    
    def _run_main_loop(self):
        """메인 루프 실행"""
        if hasattr(self.instance, 'run_main_loop'):
            self.instance.run_main_loop()
        else:
            while self.running:
                if hasattr(self.instance, 'run_main_work'):
                    self.instance.run_main_work()
                time.sleep(HIGH_FREQ_TIMEOUT)
    
    def _cleanup_instance(self):
        """인스턴스 정리"""
        if hasattr(self.instance, 'cleanup'): 
            self.instance.cleanup()
        logging.info(f"[{self.name}] QThread 종료")
    
    def order(self, target, method, *args, **kwargs):
        """order 인터페이스"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - order {method} 요청 거부")
            return
            
        if self.instance and hasattr(self.instance, method):
            try: 
                getattr(self.instance, method)(*args, **kwargs)
            except Exception as e: 
                logging.error(f"[{self.name}] {method} 실행 오류: {e}")
    
    def answer(self, target, method, *args, **kwargs):
        """answer 인터페이스"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - answer {method} 요청 거부")
            return None
            
        if self.instance and hasattr(self.instance, method):
            try: 
                result = getattr(self.instance, method)(*args, **kwargs)
                logging.debug(f"[{self.name}] answer {method} 완료")
                return result
            except Exception as e: 
                logging.error(f"[{self.name}] {method} 실행 오류: {e}")
                return None
        return None
    
    def frq_order(self, target, method, *args, **kwargs):
        """고빈도 order 인터페이스"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_order {target}.{method} 요청 거부")
            return False
            
        return self._route_to_target(target, 'order', method, *args, **kwargs)
    
    def frq_answer(self, target, method, *args, **kwargs):
        """고빈도 answer 인터페이스"""
        return self.answer(target, method, *args, **kwargs)
    
    def _route_to_target(self, target, interface_type, method, *args, **kwargs):
        """타겟 컴포넌트로 라우팅"""
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, interface_type):
                    getattr(target_component, interface_type)(target, method, *args, **kwargs)
                    #logging.debug(f"[{self.name}] {interface_type} {target}.{method} (via {interface_type})")
                elif hasattr(target_component, method):
                    getattr(target_component, method)(*args, **kwargs)
                    #logging.debug(f"[{self.name}] {interface_type} {target}.{method} (직접 호출)")
                else:
                    logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                    return False
                return True
            except Exception as e: 
                logging.error(f"[{self.name}] {interface_type} 오류: {e}")
                return False
        else: 
            logging.warning(f"[{self.name}] 타겟 없음: {target}")
            return False
    
    def __getattr__(self, name):
        if self.instance and hasattr(self.instance, name): 
            return getattr(self.instance, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
class ProcessComponent:
    """프로세스 래퍼 - 고성능"""
    
    def __init__(self, name, cls, *args, **kwargs):
        self.name, self.cls = name, cls
        self.init_args, self.init_kwargs = args, kwargs
        self._init_queues()
        self.process, self.running = None, False
        self.response_thread, self.pending_responses = None, {}
        self.init_complete = mp.Event()
    
    def _init_queues(self):
        """5개 큐로 3채널 구현"""
        # 1. 일반채널 (order/answer 공용)
        self.normal_request_queue = mp.Queue(maxsize=1000)
        self.normal_response_queue = mp.Queue(maxsize=1000)
        
        # 2. 고빈도 요청 채널 (frq_order 전용)
        self.frq_order_queue = mp.Queue(maxsize=5000)
        
        # 3. 고빈도 요청및 응답 채널 (frq_answer 전용)
        self.frq_answer_request_queue = mp.Queue(maxsize=5000)
        self.frq_answer_response_queue = mp.Queue(maxsize=5000)
    
    def start(self):
        """프로세스 시작"""
        self.running = True
        self._start_process()
        self._wait_for_initialization()
        self._start_response_handler()
        logging.info(f"[{self.name}] 프로세스 시작")
    
    def _start_process(self):
        """프로세스 워커 시작"""
        self.process = mp.Process(
            target=self._process_worker, 
            args=(self.name, self.cls, self.init_args, self.init_kwargs,
                  self.normal_request_queue, self.normal_response_queue,
                  self.frq_order_queue,
                  self.frq_answer_request_queue, self.frq_answer_response_queue,
                  self.init_complete), 
            daemon=False
        )
        self.process.start()
    
    def _wait_for_initialization(self):
        """초기화 완료 대기"""
        if self.init_complete.wait(10):
            logging.info(f"[{self.name}] 프로세스 초기화 완료")
        else:
            logging.error(f"[{self.name}] 프로세스 초기화 타임아웃")
    
    def _start_response_handler(self):
        """응답 처리 스레드 시작"""
        self.response_thread = threading.Thread(target=self._response_handler, daemon=True)
        self.response_thread.start()
    
    def stop(self):
        """프로세스 중지"""
        self.running = False
        if self.process and self.process.is_alive():
            try: 
                self.normal_request_queue.put({'command': 'stop'}, timeout=1.0)
            except: 
                pass
            self.process.join(timeout=1.0)
            if self.process.is_alive(): 
                self.process.terminate()
        logging.info(f"[{self.name}] 프로세스 중지")
    
    def order(self, target, method, *args, **kwargs):
        """order 인터페이스 - 일반채널 사용"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - order {method} 요청 거부")
            return
            
        request = self._create_request('process_order', method, args, kwargs)
        self._send_normal_request(request, method)
    
    def answer(self, target, method, *args, **kwargs):
        """answer 인터페이스 - 일반채널 사용"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - answer {method} 요청 거부")
            return None
            
        return self._send_answer_request('inbound_answer', method, args, kwargs, WAIT_TIMEOUT)
    
    def frq_order(self, target, method, *args, **kwargs):
        """고빈도 order 인터페이스 - 고빈도 요청채널 사용"""
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_order {target}.{method} 요청 거부")
            return False
            
        request = {
            'type': 'outbound_frq_order',
            'target': target, 
            'method': method,
            'args': args, 
            'kwargs': kwargs
        }
        return self._send_frq_order_request(request, f"{target}.{method}")
    
    def frq_answer(self, target, method, *args, **kwargs):
        """고빈도 answer 인터페이스 - 고빈도 응답채널 사용"""
        return self._send_frq_answer_request('inbound_frq_answer', method, args, kwargs, 0.1)
    
    def _create_request(self, request_type, method, args, kwargs, req_id=None):
        """요청 메시지 생성"""
        request = {
            'type': request_type,
            'method': method, 
            'args': self._serialize(args), 
            'kwargs': self._serialize(kwargs)
        }
        if req_id:
            request['id'] = req_id
        return request
    
    def _send_normal_request(self, request, method_name):
        """일반채널 요청 전송"""
        try: 
            self.normal_request_queue.put(request, timeout=0.1)
            #logging.debug(f"[{self.name}] order {method_name} 전송")
        except: 
            logging.error(f"[{self.name}] {method_name} 요청 실패")
    
    def _send_frq_order_request(self, request, method_name):
        """고빈도 요청채널 전송"""
        try:
            self.frq_order_queue.put_nowait(request)
            logging.debug(f"[{self.name}] frq_order {method_name} 전송")
            return True
        except queue.Full:
            logging.debug(f"[{self.name}] frq_order 드롭: {method_name}")
            return False
        except: 
            return False
    
    def _send_answer_request(self, request_type, method, args, kwargs, timeout):
        """일반채널 answer 요청 전송 및 응답 대기"""
        req_id = str(uuid.uuid4())
        request = self._create_request(request_type, method, args, kwargs, req_id)
        
        event = threading.Event()
        self.pending_responses[req_id] = {'result': None, 'ready': event}
        
        try: 
            self.normal_request_queue.put(request, timeout=HIGH_FREQ_TIMEOUT)
        except:
            self.pending_responses.pop(req_id, None)
            return None
        
        if event.wait(timeout):
            result = self.pending_responses.pop(req_id)['result']
            #logging.debug(f"[{self.name}] {request_type} {method} 완료")
            return result
        else:
            self.pending_responses.pop(req_id, None)
            return None
    
    def _send_frq_answer_request(self, request_type, method, args, kwargs, timeout):
        """고빈도 응답채널 answer 요청 전송 및 응답 대기"""
        req_id = str(uuid.uuid4())
        request = self._create_request(request_type, method, args, kwargs, req_id)
        
        event = threading.Event()
        self.pending_responses[req_id] = {'result': None, 'ready': event}
        
        try: 
            self.frq_answer_request_queue.put(request, timeout=HIGH_FREQ_TIMEOUT)
        except:
            self.pending_responses.pop(req_id, None)
            return None
        
        if event.wait(timeout):
            result = self.pending_responses.pop(req_id)['result']
            logging.debug(f"[{self.name}] {request_type} {method} 완료")
            return result
        else:
            self.pending_responses.pop(req_id, None)
            return None
    
    def _serialize(self, data):
        """데이터 직렬화"""
        if isinstance(data, (str, int, float, bool, type(None))): 
            return data
        elif isinstance(data, (list, tuple)): 
            return [self._serialize(item) for item in data]
        elif isinstance(data, dict): 
            return {k: self._serialize(v) for k, v in data.items()}
        else: 
            return str(data)
    
    def _response_handler(self):
        """5채널 응답 처리"""
        while self.running:
            try:
                # 일반채널 응답 처리
                try:
                    response = self.normal_response_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                    self._handle_response(response)
                    continue
                except Empty:
                    pass
                
                # 고빈도 요청채널 응답 처리 (frq_order로부터)
                try:
                    response = self.frq_order_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                    self._handle_response(response)
                    continue
                except Empty:
                    pass
                
                # 고빈도 응답채널 응답 처리
                try:
                    response = self.frq_answer_response_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                    self._handle_response(response)
                    continue
                except Empty:
                    pass
                    
            except Exception as e: 
                logging.error(f"[{self.name}] 응답 처리 오류: {e}")
    
    def _handle_response(self, response):
        """응답 타입별 처리"""
        response_type = response.get('type')
        
        if response_type == 'outbound_frq_order':
            self._handle_outbound_frq_order(response)
        elif response_type == 'process_order':
            self._handle_process_order(response)
        elif response_type == 'process_answer':
            self._handle_process_answer(response)
        elif response_type in ['answer', 'inbound_answer', 'inbound_frq_answer']:
            self._handle_answer_response(response)
        elif response_type == 'answer_response':
            self._handle_answer_response(response)
    
    def _handle_process_order(self, response):
        """프로세스 내부 order 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        self._route_to_component(target, 'order', method, args, kwargs)
    
    def _handle_process_answer(self, response):
        """프로세스 내부 answer 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        request_id = response.get('request_id')
        
        result = self._route_to_component(target, 'answer', method, args, kwargs)
        
        response_msg = {
            'type': 'answer_response',
            'request_id': request_id,
            'result': self._serialize(result)
        }
        self.normal_request_queue.put(response_msg)
    
    def _handle_outbound_frq_order(self, response):
        """outbound_frq_order 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        self._route_to_component(target, 'order', method, args, kwargs)
    
    def _handle_answer_response(self, response):
        """answer 응답 처리"""
        req_id = response.get('id') or response.get('request_id')
        result = response.get('result')
        
        if req_id and req_id in self.pending_responses:
            self.pending_responses[req_id]['result'] = result
            self.pending_responses[req_id]['ready'].set()
    
    def _route_to_component(self, target, interface_type, method, args, kwargs):
        """컴포넌트로 라우팅"""
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, interface_type):
                    result = getattr(target_component, interface_type)(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    result = getattr(target_component, method)(*args, **kwargs)
                else:
                    logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                    return None
                #logging.debug(f"[{self.name}] 라우팅 {interface_type}: {target}.{method}")
                return result
            except Exception as e:
                logging.error(f"[{self.name}] 라우팅 {interface_type} 오류: {e}")
                return None
        else:
            logging.warning(f"[{self.name}] 타겟 없음: {target}")
            return None
    
    @staticmethod
    def _process_worker(name, cls, args, kwargs, normal_req_q, normal_resp_q, 
                       frq_order_q, frq_ans_req_q, frq_ans_resp_q, init_complete):
        """5채널 프로세스 워커"""
        try:
            logging.info(f"[{name}] 프로세스 워커 시작")
            instance = cls(*args, **kwargs)
            
            ProcessComponent._inject_interfaces(instance, name, normal_req_q, normal_resp_q, 
                                              frq_order_q, frq_ans_req_q, frq_ans_resp_q)
            ProcessComponent._initialize_worker(instance, name, init_complete)
            ProcessComponent._run_worker_loop(instance, name, normal_req_q, normal_resp_q, 
                                            frq_order_q, frq_ans_req_q, frq_ans_resp_q)
            ProcessComponent._cleanup_worker(instance, name)
            
        except Exception as e: 
            logging.error(f"[{name}] 초기화 오류: {e}")
            init_complete.set()
    
    @staticmethod
    def _inject_interfaces(instance, name, normal_req_q, normal_resp_q, 
                          frq_order_q, frq_ans_req_q, frq_ans_resp_q):
       """인터페이스 주입 - 5채널 사용"""
       def order(target, method, *args, **kwargs):
            request = {
                'type': 'process_order',
                'target': target,
                'method': method, 
                'args': args, 
                'kwargs': kwargs
            }
            try: 
                normal_resp_q.put(request)
                #logging.debug(f"[{name}] 내부 order {target}.{method} 전송")
            except: 
                pass
        
       def frq_order(target, method, *args, **kwargs):
            request = {
                'type': 'outbound_frq_order',
                'target': target, 
                'method': method, 
                'args': args, 
                'kwargs': kwargs
            }
            try: 
                frq_order_q.put(request)
                #logging.debug(f"[{name}] 내부 frq_order {target}.{method} 전송")
            except: 
               pass
       
       def answer(target, method, *args, **kwargs):
           import uuid
           req_id = str(uuid.uuid4())
           request = {
               'type': 'process_answer',
               'target': target,
               'method': method,
               'args': args,
               'kwargs': kwargs,
               'request_id': req_id
           }
           
           normal_resp_q.put(request)
           #logging.debug(f"[{name}] 내부 answer {target}.{method} 전송")
           
           timeout = 15
           start_time = time.time()
           
           while time.time() - start_time < timeout:
               try:
                   response = normal_req_q.get(timeout=0.1)
                   if (response.get('type') == 'answer_response' and 
                       response.get('request_id') == req_id):
                       result = response.get('result')
                       #logging.debug(f"[{name}] answer {target}.{method} 응답 수신")
                       return result
               except:
                   continue
               time.sleep(0.01)
           
           logging.warning(f"[{name}] answer {target}.{method} 타임아웃")
           return None
       
       def frq_answer(target, method, *args, **kwargs):
           import uuid
           req_id = str(uuid.uuid4())
           request = {
               'type': 'inbound_frq_answer',
               'id': req_id,
               'method': method,
               'args': args,
               'kwargs': kwargs
           }
           
           try:
               frq_ans_resp_q.put(request, timeout=0.01)
           except:
               return None
           
           timeout = 0.1
           start_time = time.time()
           
           while time.time() - start_time < timeout:
               try:
                   response = frq_ans_req_q.get(timeout=0.01)
                   if (response.get('type') == 'inbound_frq_answer' and 
                       response.get('id') == req_id):
                       result = response.get('result')
                       #logging.debug(f"[{name}] frq_answer {target}.{method} 응답 수신")
                       return result
               except:
                   continue
               time.sleep(0.001)
           
           return None
       
       instance.order = order
       instance.frq_order = frq_order
       instance.answer = answer
       instance.frq_answer = frq_answer
   
    @staticmethod
    def _initialize_worker(instance, name, init_complete):
        """워커 초기화"""
        if hasattr(instance, 'initialize'):
            init_result = instance.initialize()
            logging.info(f"[{name}] 프로세스 초기화 완료: {init_result}")
        
        init_complete.set()
    
    @staticmethod
    def _run_worker_loop(instance, name, normal_req_q, normal_resp_q, 
                        frq_order_q, frq_ans_req_q, frq_ans_resp_q):
        """5채널 워커 메인 루프"""
        while True:
            try:
                # 일반채널 처리
                try:
                    request = normal_req_q.get(timeout=HIGH_FREQ_TIMEOUT)
                    if request.get('command') == 'stop': 
                        break
                    ProcessComponent._handle_worker_request(instance, name, request, normal_resp_q)
                except Empty:
                    pass
                
                # 고빈도 응답채널 처리
                try:
                    request = frq_ans_req_q.get(timeout=HIGH_FREQ_TIMEOUT)
                    ProcessComponent._handle_worker_request(instance, name, request, frq_ans_resp_q)
                except Empty:
                    pass
                
                # 사용자 정의 반복 작업
                if hasattr(instance, 'run_main_work'):
                    instance.run_main_work()
            
            except Exception as e: 
                logging.error(f"[{name}] 처리 오류: {e}")
    
    @staticmethod
    def _handle_worker_request(instance, name, request, response_queue):
        """워커 요청 처리"""
        request_type = request.get('type')
        method_name = request.get('method')
        args = request.get('args', ())
        kwargs = request.get('kwargs', {})
        req_id = request.get('id')
        
        if method_name and hasattr(instance, method_name):
            try:
                result = getattr(instance, method_name)(*args, **kwargs)
                #logging.debug(f"[{name}] {method_name} 실행 완료")
                
                if request_type in ['answer', 'inbound_answer', 'inbound_frq_answer'] and req_id:
                    response_queue.put({
                        'type': request_type,
                        'id': req_id, 
                        'result': ProcessComponent._serialize_static(result)
                    })
            except Exception as e:
                logging.error(f"[{name}] {method_name} 오류: {e}")
                if request_type in ['answer', 'inbound_answer', 'inbound_frq_answer'] and req_id:
                    response_queue.put({
                        'type': request_type,
                        'id': req_id, 
                        'result': None
                    })
        else:
            if request_type in ['answer', 'inbound_answer', 'inbound_frq_answer'] and req_id:
                response_queue.put({
                    'type': request_type,
                    'id': req_id, 
                    'result': None
                })
    
    @staticmethod
    def _cleanup_worker(instance, name):
        """워커 정리"""
        if hasattr(instance, 'cleanup'): 
            instance.cleanup()
        logging.info(f"[{name}] 프로세스 종료")
    
    @staticmethod
    def _serialize_static(data):
        """정적 직렬화 메서드"""
        if isinstance(data, (str, int, float, bool, type(None))): 
            return data
        elif isinstance(data, (list, tuple)): 
            return [ProcessComponent._serialize_static(item) for item in data]
        elif isinstance(data, dict): 
            return {k: ProcessComponent._serialize_static(v) for k, v in data.items()}
        else: 
            return str(data)

class GlobalComponent:
    """글로벌 컴포넌트 관리자 - target 중복 해결"""
    
    def __init__(self):
        self.admin = None
        self.api = None
        self.dbm = None
        self.stg = None
        self.api_connected = False
    
gm = GlobalComponent()

class Admin:
    def __init__(self):
        self.name = 'admin'
        self.trading_done = False
        
        # 각 컴포넌트 완료 플래그
        self.stg_done = False
        self.api_done = False
        self.dbm_done = False
        
    def on_component_done(self, component_name):
        """컴포넌트 완료 통보 수신"""
        if component_name == 'stg':
            self.stg_done = True
            logging.info(f"[{self.name}] STG 완료 통보 수신")
        elif component_name == 'api':
            self.api_done = True
            logging.info(f"[{self.name}] API 완료 통보 수신")
        elif component_name == 'dbm':
            self.dbm_done = True
            logging.info(f"[{self.name}] DBM 완료 통보 수신")
    
    def wait_for_component(self, component_name, timeout=30):
        """특정 컴포넌트 완료 대기"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if component_name == 'stg' and self.stg_done:
                return True
            elif component_name == 'api' and self.api_done:
                return True  
            elif component_name == 'dbm' and self.dbm_done:
                return True
            time.sleep(0.1)  # 짧은 폴링 간격
        
        logging.warning(f"[{self.name}] {component_name} 완료 대기 타임아웃")
        return False

    def start_admin(self):
        logging.info(f"\n[{self.name}] 시작 {'*' * 10}")

        gm.stg = SimpleManager('stg', Strategy, 'thread', 'arg_1', 'kwarg_1')
        gm.stg.start()
        time.sleep(1.0)  # STG 시작 대기만 유지

        # Admin 컴포넌트 테스트 *****************************************************************************
        # order 테스트
        self.order('dbm', 'dbm_response', 'dbm call')
        logging.info(f"[{self.name}] -> DBM / dbm_response 요청 완료")

        # answer 테스트
        result = self.answer('api', 'GetMasterCodeName', '005930')
        logging.info(f"[{self.name}] -> API / 종목코드: 005930, 종목명: {result}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령) - 직접 gm 통해서 호출
        self.frq_order('dbm', 'dbm_response', 'frq_order test') # 현재가를 계속 보내서 차트 데이타 업데이트
        logging.info(f"[{self.name}] -> DBM frq_order dbm_response 요청 완료")

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의) - 직접 gm 통해서 호출
        result = self.frq_answer('api', 'GetConnectState')
        logging.info(f"[{self.name}] -> API frq_answer GetConnectState 확인 / {result}")

        # 타 쓰레드 테스트 
        result = self.frq_answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG  / {result}")

        # 컴포넌트 제어 넘김 *****************************************************************************
        logging.info(f"[{self.name}] -> STG 로 제어 넘김")
        self.order('stg', 'start_stg')
        
        # STG 완료 대기 (플래그 기반)
        if self.wait_for_component('stg'):
            logging.info(f"[{self.name}] STG 완료 확인")
        
        logging.info(f"[{self.name}] -> API 로 제어 넘김")
        self.order('api', 'start_api')
        
        # API 완료 대기 (플래그 기반)
        if self.wait_for_component('api'):
            logging.info(f"[{self.name}] API 완료 확인")

        logging.info(f"[{self.name}] -> DBM 로 제어 넘김")
        self.order('dbm', 'start_dbm')
        
        # DBM 완료 대기 (플래그 기반)
        if self.wait_for_component('dbm'):
            logging.info(f"[{self.name}] DBM 완료 확인")

        self.order('stg', 'stop')
        logging.info(f"[{self.name}] 모든 작업 완료")

    def on_receive_real_data(self, data):
        logging.info(f"[{self.name}] -> 실시간 데이터 수신: {data}")

    def admin_response(self, data):
        return f"[{self.name}] 응답: {data}"

    def shutdown(self):
        pass

class Strategy:
    def __init__(self, arg, kwarg):
        self.name = 'stg'
        self.trading_done = False
        self.initialized = False
        logging.info(f"[{self.name}] 초기화 완료: {arg}, {kwarg}")

    def initialize(self):
        self.initialized = True

    def start_stg(self):
        logging.info(f"\n[{self.name}] 시작 {'*' * 10}")

        # order 테스트
        self.order('admin', 'admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / admin_response 요청 완료")

        self.order('dbm', 'dbm_response', 'dbm order test')
        logging.info(f"[{self.name}] -> DBM / dbm_response 요청 완료")

        # answer 테스트
        result = self.answer('admin', 'admin_response', 'admin question')
        logging.info(f"[{self.name}] -> Admin / {result}")

        name = self.answer('api', 'GetMasterCodeName', '000660')
        last_price = self.answer('api', 'GetMasterLastPrice', '000660')
        logging.info(f"[{self.name}] -> API / 종목코드: 000660, 종목명: {name}, 전일가: {last_price} type={type(last_price)}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령)
        self.frq_order('admin', 'on_receive_real_data', 'stg_frq_order_test')
        logging.info(f"[{self.name}] -> Admin frq_order 테스트 완료")

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의)
        result = self.frq_answer('admin', 'admin_response', 'frq_answer test')
        logging.info(f"[{self.name}] -> Admin frq_answer 테스트 / {result}")

        # 작업 완료 플래그 설정
        gm.admin.trading_done = True
        self.trading_done = True
        logging.info(f"[{self.name}] 작업 완료")
        
        # Admin에게 완료 통보
        self.order('admin', 'on_component_done', 'stg')

    def stg_response(self, data):
        return f"[{self.name}] 응답: {data}"
    
    def stg_done(self):
        return self.trading_done
    
    def cleanup(self):
        pass

class Api:
    def __init__(self):
        self.name = 'api'
        self.app = None
        self.kiwoom = None
        self.connected = False
        self.trading_done = False

    def initialize(self):
        from public import init_logger
        init_logger()
        logging.info(f"[{self.name}] 프로세스 내 키움 API 초기화 시작")
        
        from PyQt5.QtWidgets import QApplication
        import sys
        self.app = QApplication(sys.argv)
        self.set_component()
        self.set_signal_slot()

    def set_component(self):
        try:
            from PyQt5.QAxContainer import QAxWidget
            import pythoncom
            pythoncom.CoInitialize()
            self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            logging.info(f"[{self.name}] QAxWidget 객체 생성 완료")

        except Exception as e:
            logging.error(f"[{self.name}] 초기화 오류: {e}")

    def set_signal_slot(self):
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)

    def _on_event_connect(self, err_code):
        if err_code == 0:
            self.connected = True
            logging.info(f"[{self.name}] 키움서버 연결 성공 (이벤트)")
        else:
            self.connected = False
            error_msg = {
                -100: "사용자 정보교환 실패",
                -101: "서버접속 실패", 
                -102: "버전처리 실패"
            }.get(err_code, f"알 수 없는 오류: {err_code}")
            logging.error(f"[{self.name}] 키움서버 연결 실패: {error_msg}")
    
    def _on_receive_tr_data(self, screen_no, rqname, trcode, record_name, next, *args):
        logging.info(f"[{self.name}] TR 데이터 수신: {rqname} ({trcode})")
    
    def _on_receive_real_data(self, code, real_type, real_data):
        if gm.api_connected:
            real_data_info = {
                'code': code,
                'real_type': real_type,
                'timestamp': time.time()
            }
            # admin에게 실시간 데이터 전송 (order 사용)
            if hasattr(gm.admin, 'order'):
                gm.admin.order('on_receive_real_data', real_data_info)

    def login(self):
        import pythoncom
        WAIT_TIMEOUT = 30  # 30초 타임아웃
        
        logging.info(f"[{self.name}] 로그인 시도 시작")
        self.kiwoom.dynamicCall("CommConnect()")
        start_time = time.time()
        self.connected = False
        while not self.connected:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.1)
            if time.time() - start_time > WAIT_TIMEOUT:
                logging.error(f"[{self.name}] 로그인 실패: 타임아웃 초과")
                break
        return self.connected
    
    def is_connected(self):
        return self.connected
    
    def GetConnectState(self):
        return self.kiwoom.dynamicCall("GetConnectState()")

    def GetMasterCodeName(self, code):
        data = self.kiwoom.dynamicCall("GetMasterCodeName(QString)", code)
        return data

    def GetMasterLastPrice(self, code):
        data = self.kiwoom.dynamicCall("GetMasterLastPrice(QString)", code)
        data = int(data) if data else 0
        return data

    def start_api(self):
        logging.info(f"\n[{self.name}] 시작 {'*' * 10}")

        # order 테스트
        self.order('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG / stg_response 요청 완료")

        # answer 테스트
        result = self.answer('admin', 'admin_response', 'admin question')
        logging.info(f"[{self.name}] -> Admin / {result}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령)
        logging.info(f"[{self.name}] 실시간 데이터 전송 시작")
        for i in range(10):
            self.frq_order('admin', 'on_receive_real_data', f'real_data_info_{i}')
            time.sleep(0.001)

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의)
        result = self.frq_answer('admin', 'admin_response', 'frq_answer test')
        logging.info(f"[{self.name}] -> Admin frq_answer 테스트 / {result}")
        
        self.trading_done = True
        logging.info(f"[{self.name}] 작업 완료")
        
        # Admin에게 완료 통보
        self.order('admin', 'on_component_done', 'api')

    def api_response(self, data):
        return f"[{self.name}] 응답: {data}"

    def api_done(self):
        return self.trading_done

class Dbm:
    def __init__(self):
        self.name = 'dbm'
        self.initialized = False
        self.trading_done = False

    def initialize(self):
        from public import init_logger
        init_logger()
        self.initialized = True
        logging.info(f"[{self.name}] 데이터베이스 초기화 완료")

    def start_dbm(self):
        logging.info(f"\n[{self.name}] 작업 시작 {'*' * 10}")

        # order 테스트
        self.order('admin', 'admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / admin_response 요청 완료")

        # answer 테스트
        result = self.answer('api', 'api_response', 'api request')
        logging.info(f"[{self.name}] -> API / {result}")


        result = self.answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG / {result}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령)
        result = self.answer('admin', 'admin_response', 'admin request')
        logging.info(f"[{self.name}] -> Admin / {result} **********")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령)
        self.frq_order('admin', 'on_receive_real_data', 'dbm_frq_order_test')
        logging.info(f"[{self.name}] -> Admin frq_order 테스트 완료")

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의)
        result = self.frq_answer('stg', 'stg_response', 'stg frq_answer test')
        logging.info(f"[{self.name}] -> STG frq_answer 테스트 / {result}")

        self.trading_done = True
        logging.info(f"[{self.name}] 작업 완료")
        
        # Admin에게 완료 통보
        self.order('admin', 'on_component_done', 'dbm')

    def dbm_response(self, data):
        return f"[{self.name}] 응답: {data}"

    def dbm_done(self):
        return self.trading_done

class Main:
    def __init__(self):
        pass

    def run(self):
        try:
            gm.admin = SimpleManager('admin', Admin, None)    # 메인 쓰레드 실행
            gm.api = SimpleManager('api', Api, 'process')     # 별도 프로세스
            gm.dbm = SimpleManager('dbm', Dbm, 'process')     # 별도 프로세스

            gm.admin.start()
            gm.api.start() 
            gm.dbm.start()

            # API 로그인
            gm.api.order('api', 'login')
            # 연결 확인 (1이면 연결됨)
            timeout_count = 0
            while not gm.api.answer('api', 'is_connected') and timeout_count < 100:
                time.sleep(0.1)
                timeout_count += 1
            
            if gm.api.answer('api', 'is_connected'):
                gm.api_connected = True
                logging.info(f"[Main] API 연결 완료")
                gm.admin.order('admin', 'start_admin')
            else:
                logging.error(f"[Main] API 연결 실패")

        except Exception as e:
            logging.error(f"[Main] 실행 오류: {e}", exc_info=True)
        
        finally:
            logging.info(f"[Main] 시스템 종료 시작")
            self.cleanup()
            logging.info(f"[Main] 시스템 종료 완료")
        
        return

    def cleanup(self):
        """강제 종료 포함한 정리"""
        # ComponentRegistry에서 모든 컴포넌트 가져오기
        all_components = ComponentRegistry._components.copy()
        
        # 종료 순서 정의 (중요: 의존성 역순)
        shutdown_order = ['stg', 'api', 'dbm']
        
        # 순서대로 종료
        for name in shutdown_order:
            if component := all_components.get(name):
                try:
                    component.stop()
                    #logging.info(f"[Main] {name.upper()} 종료")
                except Exception as e:
                    logging.error(f"[Main] {name.upper()} 종료 오류: {e}")
        
        # 혹시 누락된 컴포넌트들 처리
        for name, component in all_components.items():
            if name not in shutdown_order:
                try:
                    component.stop()
                    #logging.info(f"[Main] {name.upper()} (추가) 종료")
                except Exception as e:
                    logging.error(f"[Main] {name.upper()} (추가) 종료 오류: {e}")
        
        # 프로세스 강제 종료
        self._force_exit()

    def _force_exit(self):
        """프로세스 강제 종료"""
        import os
        import signal
        import time
        
        try:
            # 1초 후 강제 종료
            time.sleep(1)
            logging.info(f"[Main] 프로세스 강제 종료")
            os.kill(os.getpid(), signal.SIGTERM)
        except:
            pass

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    from public import init_logger
    init_logger()
    logging.info("트레이딩 시스템 시작")
    main = Main()
    main.run()

    