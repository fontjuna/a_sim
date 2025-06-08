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
            # comm_type = None인 경우 4가지 인터페이스 주입
            self._inject_interfaces()
        
        ComponentRegistry.register(name, self.instance)
    
    def _inject_interfaces(self):
        """comm_type = None인 경우 4가지 인터페이스를 인스턴스에 주입"""
        def order(method, *args, **kwargs):
            # comm_type = None인 경우 자기 자신의 메서드 호출 (원본 그대로)
            if hasattr(self.instance, method):
                try:
                    getattr(self.instance, method)(*args, **kwargs)
                    logging.debug(f"[{self.name}] order {method} 완료")
                except Exception as e:
                    logging.error(f"[{self.name}] {method} 실행 오류: {e}")
            else:
                logging.warning(f"[{self.name}] {method} 메서드 없음")
        
        def answer(method, *args, **kwargs):
            # comm_type = None인 경우 자기 자신의 메서드 호출 (원본 그대로)
            if hasattr(self.instance, method):
                try:
                    result = getattr(self.instance, method)(*args, **kwargs)
                    logging.debug(f"[{self.name}] answer {method} 완료")
                    return result
                except Exception as e:
                    logging.error(f"[{self.name}] {method} 실행 오류: {e}")
                    return None
            else:
                logging.warning(f"[{self.name}] {method} 메서드 없음")
                return None
        
        def frq_order(target, method, *args, **kwargs):
            # 타 컴포넌트에게 고빈도 명령
            return self.frq_order(target, method, *args, **kwargs)
        
        def frq_answer(target, method, *args, **kwargs):
            # 타 컴포넌트에게 고빈도 질의
            return self.frq_answer(target, method, *args, **kwargs)
        
        # 인스턴스에 메서드 주입
        self.instance.order = order
        self.instance.answer = answer
        self.instance.frq_order = frq_order
        self.instance.frq_answer = frq_answer
    
    def start(self):
        if self.comm_type in ['thread', 'process']:
            self.instance.start()
        elif hasattr(self.instance, 'initialize'):
            self.instance.initialize()
        logging.info(f"[{self.name}] 시작")
    
    def stop(self):
        if self.comm_type in ['thread', 'process']:
            self.instance.stop()
        elif hasattr(self.instance, 'cleanup'):
            self.instance.cleanup()
        logging.info(f"[{self.name}] 중지")

    """
    모든 인터페이스는 target 파라미터를 가짐
    """
    def order(self, target, method, *args, **kwargs):
        """통일된 order 인터페이스"""
        if hasattr(self.instance, 'order'):
            # thread/process 컴포넌트
            return self.instance.order(target, method, *args, **kwargs)
        else:
            # 직접 실행 컴포넌트는 ComponentRegistry를 통한 라우팅
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, method):
                        getattr(target_component, method)(*args, **kwargs)
                        logging.debug(f"[{self.name}] order {target}.{method} 완료")
                except Exception as e:
                    logging.error(f"[{self.name}] order 오류: {e}")
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")

    def answer(self, target, method, *args, **kwargs):
        """통일된 answer 인터페이스"""
        if hasattr(self.instance, 'answer'):
            # thread/process 컴포넌트
            return self.instance.answer(target, method, *args, **kwargs)
        else:
            # 직접 실행 컴포넌트는 ComponentRegistry를 통한 라우팅
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, method):
                        result = getattr(target_component, method)(*args, **kwargs)
                        logging.debug(f"[{self.name}] answer {target}.{method} 완료")
                        return result
                    else:
                        logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                        return None
                except Exception as e:
                    logging.error(f"[{self.name}] answer 오류: {e}")
                    return None
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")
                return None
    
    def frq_order(self, target, method, *args, **kwargs):
        """통일된 frq_order 인터페이스 - 다른 컴포넌트에게 고빈도 명령"""
        if hasattr(self.instance, 'frq_order'):
            # thread/process 컴포넌트
            return self.instance.frq_order(target, method, *args, **kwargs)
        else:
            # 직접 실행 컴포넌트는 ComponentRegistry를 통한 고빈도 라우팅
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, 'order'):
                        target_component.order(target, method, *args, **kwargs)
                    elif hasattr(target_component, method):
                        getattr(target_component, method)(target, *args, **kwargs)
                except Exception as e:
                    logging.error(f"[{self.name}] frq_order 오류: {e}")
                    return False
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")
                return False
    
    def frq_answer(self, target, method, *args, **kwargs):
        """통일된 frq_answer 인터페이스 - 다른 컴포넌트에게 고빈도 질의"""
        if hasattr(self.instance, 'frq_answer'):
            # thread/process 컴포넌트
            return self.instance.frq_answer(target, method, *args, **kwargs)
        else:
            # 직접 실행 컴포넌트는 ComponentRegistry를 통한 고빈도 라우팅
            if target_component := ComponentRegistry.get(target):
                try:
                    if hasattr(target_component, 'answer'):
                        result = target_component.answer(target, method, *args, **kwargs)
                        logging.debug(f"[{self.name}] frq_answer {target}.{method} 완료")
                        return result
                    elif hasattr(target_component, method):
                        result = getattr(target_component, method)(target, *args, **kwargs)
                        logging.debug(f"[{self.name}] frq_answer {target}.{method} (직접 호출)")
                        return result
                    else:
                        logging.warning(f"[{self.name}] {target}에 {method} 메서드 없음")
                        return None
                except Exception as e:
                    logging.error(f"[{self.name}] frq_answer 오류: {e}")
                    return None
            else:
                logging.warning(f"[{self.name}] 타겟 없음: {target}")
                return None
    
    def __getattr__(self, name):
        # 4가지 인터페이스 메서드들을 우선적으로 체크
        if name in ['order', 'answer', 'frq_order', 'frq_answer']:
            return getattr(self, name)
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
        
        # 고빈도 처리용 별도 큐
        self.frq_queue = Queue(maxsize=1000)
        self.frq_response_queue = Queue(maxsize=1000)
        self.frq_pending_responses = {}
    
    def start(self):
        self.running = True
        QThread.start(self)
        # 초기화 완료 대기
        time.sleep(0.5)
    
    def stop(self):
        self.running = False
        self.quit()
        self.wait(1000)
        if self.isRunning(): 
            self.terminate()
    
    def run(self):
        try:
            self.instance = self.cls(*self.init_args, **self.init_kwargs)
            
            if hasattr(self.instance, 'initialize'): 
                self.instance.initialize()
            logging.info(f"[{self.name}] QThread 시작")
            
            # 고빈도 처리 워커 스레드 시작
            self.frq_worker_thread = threading.Thread(target=self._frq_worker, daemon=True)
            self.frq_worker_thread.start()
            
            if hasattr(self.instance, 'run_main_loop'):
                self.instance.run_main_loop()
            else:
                while self.running: 
                    time.sleep(HIGH_FREQ_TIMEOUT)
            
            if hasattr(self.instance, 'cleanup'): 
                self.instance.cleanup()
            logging.info(f"[{self.name}] QThread 종료")
        except Exception as e:
            logging.error(f"[{self.name}] QThread 실행 오류: {e}")
    
    def _frq_worker(self):
        """고빈도 전용 워커"""
        while self.running:
            try:
                request = self.frq_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                req_type = request.get('type')
                
                if req_type == 'frq_order':
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if self.instance and hasattr(self.instance, method):
                        try:
                            getattr(self.instance, method)(*args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] frq_order {method} 오류: {e}")
                
                elif req_type == 'frq_answer':
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    req_id = request.get('id')
                    
                    result = None
                    if self.instance and hasattr(self.instance, method):
                        try:
                            result = getattr(self.instance, method)(*args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] frq_answer {method} 오류: {e}")
                    
                    # 응답 전송
                    try:
                        self.frq_response_queue.put_nowait({
                            'type': 'frq_answer_response',
                            'id': req_id,
                            'result': result
                        })
                    except:
                        pass
                
                elif req_type == 'order_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'order'):
                                target_component.order(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] order_target 오류: {e}")
                
                elif req_type == 'answer_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'answer'):
                                target_component.answer(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] answer_target 오류: {e}")
                
                elif req_type == 'frq_answer_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'answer'):
                                target_component.answer(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] frq_answer_target 오류: {e}")
                
                elif req_type == 'frq_order_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'frq_order'):
                                target_component.frq_order(target, method, *args, **kwargs)
                            elif hasattr(target_component, 'order'):
                                target_component.order(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{self.name}] frq_order_target 오류: {e}")
                            
            except Empty:
                continue
            except Exception as e:
                logging.error(f"[{self.name}] frq_worker 오류: {e}")
    
    def order(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - order {target}.{method} 요청 거부")
            return
            
        if target == self.name:
            # 자기 자신의 메서드 호출
            if self.instance and hasattr(self.instance, method):
                try: 
                    getattr(self.instance, method)(*args, **kwargs)
                    logging.debug(f"[{self.name}] order {method} 완료")
                except Exception as e: 
                    logging.error(f"[{self.name}] {method} 실행 오류: {e}")
        else:
            # 다른 컴포넌트에게 라우팅
            request = {
                'type': 'order_target',
                'target': target,
                'method': method,
                'args': args,
                'kwargs': kwargs
            }
            
            try:
                self.frq_queue.put_nowait(request)
                logging.debug(f"[{self.name}] order {target}.{method} 전송")
            except:
                logging.debug(f"[{self.name}] order 드롭: {target}.{method}")
    
    def answer(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - answer {target}.{method} 요청 거부")
            return None
            
        if target == self.name:
            # 자기 자신의 메서드 호출
            if self.instance and hasattr(self.instance, method):
                try: 
                    result = getattr(self.instance, method)(*args, **kwargs)
                    logging.debug(f"[{self.name}] answer {method} 완료")
                    return result
                except Exception as e: 
                    logging.error(f"[{self.name}] {method} 실행 오류: {e}")
                    return None
            return None
        else:
            # 다른 컴포넌트에게 라우팅
            request = {
                'type': 'answer_target',
                'target': target,
                'method': method,
                'args': args,
                'kwargs': kwargs
            }
            
            try:
                self.frq_queue.put_nowait(request)
                logging.debug(f"[{self.name}] answer {target}.{method} 전송")
                return None  # thread는 응답 대기 안함
            except:
                logging.debug(f"[{self.name}] answer 드롭: {target}.{method}")
        return None
    
    def frq_order(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_order {target}.{method} 요청 거부")
            return False
            
        request = {
            'type': 'frq_order_target',
            'target': target,
            'method': method,
            'args': args,
            'kwargs': kwargs
        }
        
        try:
            self.frq_queue.put_nowait(request)
            logging.debug(f"[{self.name}] frq_order {target}.{method} 전송")
            return True
        except:
            logging.debug(f"[{self.name}] frq_order 드롭: {target}.{method}")
            return False
    
    def frq_answer(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_answer {target}.{method} 요청 거부")
            return None
        
        request = {
            'type': 'frq_answer_target',
            'target': target,
            'method': method,
            'args': args,
            'kwargs': kwargs
        }
        
        try: 
            self.frq_queue.put_nowait(request)
            logging.debug(f"[{self.name}] frq_answer {target}.{method} 전송")
            return None  # 고빈도는 응답 대기 안함
        except:
            logging.debug(f"[{self.name}] frq_answer 드롭: {target}.{method}")
            return None
    
    def __getattr__(self, name):
        if self.instance and hasattr(self.instance, name): 
            return getattr(self.instance, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

class ProcessComponent:
    """프로세스 래퍼 - 고성능"""
    
    def __init__(self, name, cls, *args, **kwargs):
        self.name, self.cls = name, cls
        self.init_args, self.init_kwargs = args, kwargs
        
        # 일반 처리용 큐
        self.request_queue = mp.Queue(maxsize=1000)
        self.response_queue = mp.Queue(maxsize=1000)
        
        # 고빈도 처리용 별도 큐
        self.frq_request_queue = mp.Queue(maxsize=5000)
        self.frq_response_queue = mp.Queue(maxsize=5000)
        
        self.process, self.running = None, False
        self.response_thread, self.frq_response_thread = None, None
        self.pending_responses, self.frq_pending_responses = {}, {}
        self.init_complete = mp.Event()
    
    def start(self):
        self.running = True
        self.process = mp.Process(
            target=self._process_worker, 
            args=(self.name, self.cls, self.init_args, self.init_kwargs,
                  self.request_queue, self.response_queue, 
                  self.frq_request_queue, self.frq_response_queue, self.init_complete), 
            daemon=False
        )
        self.process.start()
        
        # 초기화 완료 대기 (최대 10초)
        if self.init_complete.wait(10):
            logging.info(f"[{self.name}] 프로세스 초기화 완료")
        else:
            logging.error(f"[{self.name}] 프로세스 초기화 타임아웃")
        
        # 일반 응답 처리 스레드
        self.response_thread = threading.Thread(target=self._response_handler, daemon=True)
        self.response_thread.start()
        
        # 고빈도 응답 처리 스레드  
        self.frq_response_thread = threading.Thread(target=self._frq_response_handler, daemon=True)
        self.frq_response_thread.start()
        
        logging.info(f"[{self.name}] 프로세스 시작")
    
    def stop(self):
        self.running = False
        if self.process and self.process.is_alive():
            try: 
                self.request_queue.put({'command': 'stop'}, timeout=1.0)
                self.frq_request_queue.put({'command': 'stop'}, timeout=1.0)
            except: 
                pass
            self.process.join(timeout=1.0)
            if self.process.is_alive(): 
                self.process.terminate()
        logging.info(f"[{self.name}] 프로세스 중지")
    
    def order(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - order {target}.{method} 요청 거부")
            return
            
        request = {
            'type': 'order_target',
            'target': target,
            'method': method, 
            'args': args,
            'kwargs': kwargs
        }
        try: 
            self.request_queue.put(request, timeout=0.1)
            logging.debug(f"[{self.name}] order {target}.{method} 전송")
        except: 
            logging.error(f"[{self.name}] {target}.{method} 요청 실패")
    
    def answer(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - answer {target}.{method} 요청 거부")
            return None
            
        req_id = str(uuid.uuid4())
        request = {
            'type': 'answer_target',
            'id': req_id, 
            'target': target,
            'method': method, 
            'args': args, 
            'kwargs': kwargs
        }
        
        event = threading.Event()
        self.pending_responses[req_id] = {'result': None, 'ready': event}
        
        try: 
            self.request_queue.put(request, timeout=0.1)
        except Exception as e:
            self.pending_responses.pop(req_id, None)
            logging.error(f"[{self.name}] 요청 실패: {e}")
            return None
        
        if event.wait(WAIT_TIMEOUT):
            result = self.pending_responses.pop(req_id)['result']
            logging.debug(f"[{self.name}] answer {target}.{method} 완료")
            return result
        else:
            self.pending_responses.pop(req_id, None)
            logging.warning(f"[{self.name}] {target}.{method} 타임아웃")
            return None
    
    def frq_order(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_order {target}.{method} 요청 거부")
            return False
            
        request = {
            'type': 'frq_order_target',
            'target': target, 
            'method': method,
            'args': args, 
            'kwargs': kwargs
        }
        try:
            self.frq_request_queue.put_nowait(request)
            logging.debug(f"[{self.name}] frq_order {target}.{method} 전송")
            return True
        except queue.Full:
            logging.debug(f"[{self.name}] frq_order 드롭: {target}.{method}")
            return False
        except: 
            return False
    
    def frq_answer(self, target, method, *args, **kwargs):
        if not self.running:
            logging.warning(f"[{self.name}] 종료 중 - frq_answer {target}.{method} 요청 거부")
            return None
        
        request = {
            'type': 'frq_answer_target',
            'target': target,
            'method': method,
            'args': args,
            'kwargs': kwargs
        }
        
        try: 
            self.frq_request_queue.put_nowait(request)
            logging.debug(f"[{self.name}] frq_answer {target}.{method} 전송")
            return None  # 고빈도는 응답 대기 안함
        except:
            logging.debug(f"[{self.name}] frq_answer 드롭: {target}.{method}")
            return None
    
    def _serialize(self, data):
        if isinstance(data, (str, int, float, bool, type(None))): 
            return data
        elif isinstance(data, (list, tuple)): 
            return [self._serialize(item) for item in data]
        elif isinstance(data, dict): 
            return {k: self._serialize(v) for k, v in data.items()}
        else: 
            return str(data)
    
    def _response_handler(self):
        """일반 응답 처리"""
        while self.running:
            try:
                response = self.response_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                response_type = response.get('type')
                
                if response_type in ['answer']:
                    self._handle_answer_response(response)
                elif response_type == 'outbound_frq_order':
                    self._handle_outbound_frq_order(response)
                elif response_type == 'outbound_answer':
                    self._handle_outbound_answer(response)
                elif response_type == 'outbound_order':
                    self._handle_outbound_order(response)
                    
            except Empty: 
                continue
            except Exception as e: 
                logging.error(f"[{self.name}] 응답 처리 오류: {e}")
    
    def _frq_response_handler(self):
        """고빈도 응답 처리"""
        while self.running:
            try:
                response = self.frq_response_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                response_type = response.get('type')
                
                if response_type == 'frq_answer':
                    self._handle_frq_answer_response(response)
                elif response_type == 'frq_outbound_answer':
                    self._handle_frq_outbound_answer(response)
                elif response_type == 'frq_outbound_order':
                    self._handle_frq_outbound_order(response)
                    
            except Empty: 
                continue
            except Exception as e: 
                logging.error(f"[{self.name}] 고빈도 응답 처리 오류: {e}")
    
    def _handle_outbound_frq_order(self, response):
        """outbound_frq_order 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, 'frq_order'):
                    target_component.frq_order(target, method, *args, **kwargs)
                elif hasattr(target_component, 'order'):
                    target_component.order(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    getattr(target_component, method)(target, *args, **kwargs)
                logging.debug(f"[{self.name}] 라우팅: {target}.{method}")
            except Exception as e: 
                logging.error(f"[{self.name}] 라우팅 오류: {e}")
        else: 
            logging.warning(f"[{self.name}] 타겟 없음: {target}")
    
    def _handle_frq_outbound_order(self, response):
        """고빈도 outbound order 라우팅"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, 'frq_order'):
                    target_component.frq_order(target, method, *args, **kwargs)
                elif hasattr(target_component, 'order'):
                    target_component.order(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    getattr(target_component, method)(target, *args, **kwargs)
                #logging.debug(f"[{self.name}] frq 라우팅: {target}.{method}")
            except Exception as e: 
                logging.error(f"[{self.name}] frq 라우팅 오류: {e}")
        else: 
            logging.warning(f"[{self.name}] frq 타겟 없음: {target}")
    
    def _handle_answer_response(self, response):
        """일반 answer 응답 처리"""
        req_id = response.get('id')
        result = response.get('result')
        
        if req_id and req_id in self.pending_responses:
            self.pending_responses[req_id]['result'] = result
            self.pending_responses[req_id]['ready'].set()
    
    def _handle_frq_answer_response(self, response):
        """고빈도 answer 응답 처리"""
        req_id = response.get('id')
        result = response.get('result')
        
        if req_id and req_id in self.frq_pending_responses:
            self.frq_pending_responses[req_id]['result'] = result
            self.frq_pending_responses[req_id]['ready'].set()
    
    def _handle_outbound_answer(self, response):
        """outbound_answer 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        request_id = response.get('request_id')
        
        result = None
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, 'answer'):
                    result = target_component.answer(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    result = getattr(target_component, method)(target, *args, **kwargs)
                #logging.debug(f"[{self.name}] outbound answer 라우팅: {target}.{method}")
            except Exception as e:
                logging.error(f"[{self.name}] outbound answer 라우팅 오류: {e}")
        else:
            logging.warning(f"[{self.name}] outbound answer 타겟 없음: {target}")
        
        # 응답 전송
        response_msg = {
            'type': 'answer_response',
            'request_id': request_id,
            'result': self._serialize(result)
        }
        try:
            self.request_queue.put(response_msg, timeout=0.1)
        except:
            pass
    
    def _handle_outbound_order(self, response):
        """outbound_order 라우팅 처리"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, 'order'):
                    target_component.order(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    getattr(target_component, method)(target, *args, **kwargs)
                #logging.debug(f"[{self.name}] outbound order 라우팅: {target}.{method}")
            except Exception as e: 
                logging.error(f"[{self.name}] outbound order 라우팅 오류: {e}")
        else: 
            logging.warning(f"[{self.name}] outbound order 타겟 없음: {target}")
    
    def _handle_frq_outbound_answer(self, response):
        """고빈도 outbound answer 라우팅"""
        target = response.get('target')
        method = response.get('method')
        args = response.get('args', ())
        kwargs = response.get('kwargs', {})
        
        if target_component := ComponentRegistry.get(target):
            try:
                if hasattr(target_component, 'answer'):
                    target_component.answer(target, method, *args, **kwargs)
                elif hasattr(target_component, method):
                    getattr(target_component, method)(target, *args, **kwargs)
                #logging.debug(f"[{self.name}] frq 응답 라우팅: {target}.{method}")
            except Exception as e: 
                logging.error(f"[{self.name}] frq 응답 라우팅 오류: {e}")
        else: 
            logging.warning(f"[{self.name}] frq 응답 타겟 없음: {target}")
    
    @staticmethod
    def _process_worker(name, cls, args, kwargs, request_queue, response_queue, 
                       frq_request_queue, frq_response_queue, init_complete):
        """고성능 프로세스 워커"""
        try:
            logging.info(f"[{name}] 프로세스 워커 시작")
            instance = cls(*args, **kwargs)
            
            # 프로세스 내 인터페이스 함수 정의
            def order(target, method, *args, **kwargs):
                """프로세스 내에서 다른 컴포넌트로 order 전송"""
                request = {
                    'type': 'outbound_order',
                    'target': target,
                    'method': method, 
                    'args': args, 
                    'kwargs': kwargs
                }
                try: 
                    response_queue.put(request)
                    #logging.debug(f"[{name}] 내부 order {target}.{method} 전송")
                except: 
                    pass
            
            def frq_order(target, method, *args, **kwargs):
                """프로세스 내에서 다른 컴포넌트로 frq_order 전송"""
                request = {
                    'type': 'frq_outbound_order',
                    'target': target, 
                    'method': method, 
                    'args': args, 
                    'kwargs': kwargs
                }
                try: 
                    frq_response_queue.put_nowait(request)
                    #logging.debug(f"[{name}] 내부 frq_order {target}.{method} 전송")
                except: 
                    pass
            
            def answer(target, method, *args, **kwargs):
                """프로세스 내에서 다른 컴포넌트로 answer 요청"""
                import uuid
                req_id = str(uuid.uuid4())
                request = {
                    'type': 'outbound_answer',
                    'target': target,
                    'method': method,
                    'args': args,
                    'kwargs': kwargs,
                    'request_id': req_id
                }
                
                # 요청 전송
                response_queue.put(request)
                #logging.debug(f"[{name}] 내부 answer {target}.{method} 전송")
                
                # 응답 대기
                timeout = 15  # 15초 타임아웃
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    try:
                        response = request_queue.get(timeout=0.1)
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
            
            # 인스턴스에 인터페이스 주입
            instance.order = order
            instance.frq_order = frq_order
            instance.answer = answer
            
            # 초기화
            if hasattr(instance, 'initialize'):
                init_result = instance.initialize()
                #logging.info(f"[{name}] 프로세스 초기화 완료: {init_result}")
            
            # 초기화 완료 신호
            init_complete.set()
            
            # 고빈도 처리 워커 스레드 시작
            frq_worker_thread = threading.Thread(
                target=ProcessComponent._frq_worker_thread, 
                args=(name, instance, frq_request_queue, frq_response_queue),
                daemon=True
            )
            frq_worker_thread.start()
            
            # 일반 처리 메인 루프
            while True:
                try:
                    request = request_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                    if request.get('command') == 'stop': 
                        break
                    
                    request_type = request.get('type')
                    method_name = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    req_id = request.get('id')
                    
                    if method_name and hasattr(instance, method_name):
                        try:
                            result = getattr(instance, method_name)(*args, **kwargs)
                            #logging.debug(f"[{name}] {method_name} 실행 완료")
                            
                            # 응답이 필요한 요청들
                            if request_type == 'answer' and req_id:
                                response_queue.put({
                                    'type': 'answer',
                                    'id': req_id, 
                                    'result': ProcessComponent._serialize_static(result)
                                })
                        except Exception as e:
                            logging.error(f"[{name}] {method_name} 오류: {e}")
                            if request_type == 'answer' and req_id:
                                response_queue.put({
                                    'type': 'answer',
                                    'id': req_id, 
                                    'result': None
                                })
                    else:
                        if request_type == 'answer' and req_id:
                            response_queue.put({
                                'type': 'answer',
                                'id': req_id, 
                                'result': None
                            })
                
                except Empty: 
                    continue
                except Exception as e: 
                    logging.error(f"[{name}] 처리 오류: {e}")
            
            if hasattr(instance, 'cleanup'): 
                instance.cleanup()
            logging.info(f"[{name}] 프로세스 종료")
            
        except Exception as e: 
            logging.error(f"[{name}] 초기화 오류: {e}")
            init_complete.set()  # 오류 시에도 신호 전송
    
    @staticmethod
    def _frq_worker_thread(name, instance, frq_request_queue, frq_response_queue):
        """고빈도 전용 워커 스레드"""
        while True:
            try:
                request = frq_request_queue.get(timeout=HIGH_FREQ_TIMEOUT)
                if request.get('command') == 'stop':
                    break
                
                request_type = request.get('type')
                
                if request_type == 'frq_answer':
                    method_name = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    req_id = request.get('id')
                    
                    result = None
                    if method_name and hasattr(instance, method_name):
                        try:
                            result = getattr(instance, method_name)(*args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{name}] frq {method_name} 오류: {e}")
                    
                    # 고빈도 응답 전송
                    try:
                        frq_response_queue.put_nowait({
                            'type': 'frq_answer',
                            'id': req_id,
                            'result': ProcessComponent._serialize_static(result)
                        })
                    except:
                        pass
                
                elif request_type == 'order_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'order'):
                                target_component.order(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{name}] order_target 오류: {e}")
                
                elif request_type == 'answer_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'answer'):
                                target_component.answer(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{name}] answer_target 오류: {e}")
                
                elif request_type == 'frq_answer_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'answer'):
                                target_component.answer(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{name}] frq_answer_target 오류: {e}")
                
                elif request_type == 'frq_order_target':
                    target = request.get('target')
                    method = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    
                    if target_component := ComponentRegistry.get(target):
                        try:
                            if hasattr(target_component, 'frq_order'):
                                target_component.frq_order(target, method, *args, **kwargs)
                            elif hasattr(target_component, 'order'):
                                target_component.order(target, method, *args, **kwargs)
                            elif hasattr(target_component, method):
                                getattr(target_component, method)(target, *args, **kwargs)
                        except Exception as e:
                            logging.error(f"[{name}] frq_order_target 오류: {e}")
                            
            except Empty:
                continue
            except Exception as e:
                logging.error(f"[{name}] frq_worker 오류: {e}")
    
    @staticmethod
    def _serialize_static(data):
        if isinstance(data, (str, int, float, bool, type(None))): 
            return data
        elif isinstance(data, (list, tuple)): 
            return [ProcessComponent._serialize_static(item) for item in data]
        elif isinstance(data, dict): 
            return {k: ProcessComponent._serialize_static(v) for k, v in data.items()}
        else: 
            return str(data)


# 이하 테스트용 코드
class GlobalMemory:
    def __init__(self):
        self.admin = None
        self.stg = None
        self.api = None
        self.dbm = None

        self.api_connected = False
        self.account_list = []
        self.account = None

gm = GlobalMemory()

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
        gm.dbm.order('dbm', 'dbm_response', 'dbm call')
        logging.info(f"[{self.name}] -> DBM / dbm_response 요청 완료")

        # answer 테스트
        result = gm.api.answer('api', 'GetMasterCodeName', '005930')
        logging.info(f"[{self.name}] -> API / 종목코드: 005930, 종목명: {result}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령) - 직접 gm 통해서 호출
        gm.dbm.frq_order('dbm', 'dbm_response', 'frq_order test') # 현재가를 계속 보내서 차트 데이타 업데이트
        logging.info(f"[{self.name}] -> DBM frq_order dbm_response 요청 완료")

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의) - 직접 gm 통해서 호출
        result = gm.api.frq_answer('api', 'GetConnectState')
        logging.info(f"[{self.name}] -> API frq_answer GetConnectState 확인 / {result}")

        # 타 쓰레드 테스트 
        result = gm.stg.frq_answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG  / {result}")

        # 컴포넌트 제어 넘김 *****************************************************************************
        logging.info(f"[{self.name}] -> STG 로 제어 넘김")
        gm.stg.order('stg', 'start_stg')
        
        # STG 완료 대기 (플래그 기반)
        if self.wait_for_component('stg'):
            logging.info(f"[{self.name}] STG 완료 확인")
        
        logging.info(f"[{self.name}] -> API 로 제어 넘김")
        gm.api.order('api', 'start_api')
        
        # API 완료 대기 (플래그 기반)
        if self.wait_for_component('api'):
            logging.info(f"[{self.name}] API 완료 확인")

        logging.info(f"[{self.name}] -> DBM 로 제어 넘김")
        gm.dbm.order('dbm', 'start_dbm')
        
        # DBM 완료 대기 (플래그 기반)
        if self.wait_for_component('dbm'):
            logging.info(f"[{self.name}] DBM 완료 확인")

        gm.stg.stop()
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
        gm.admin.order('admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / admin_response 요청 완료")

        gm.dbm.order('dbm_response', 'dbm order test')
        logging.info(f"[{self.name}] -> DBM / dbm_response 요청 완료")

        # answer 테스트
        result = gm.admin.answer('admin_response', 'admin question')
        logging.info(f"[{self.name}] -> Admin / {result}")

        name = gm.api.answer('GetMasterCodeName', '000660')
        last_price = gm.api.answer('GetMasterLastPrice', '000660')
        logging.info(f"[{self.name}] -> API / 종목코드: 000660, 종목명: {name}, 전일가: {last_price}")

        # frq_order 테스트 (다른 컴포넌트에게 고빈도 명령)
        self.frq_order('admin', 'on_receive_real_data', 'stg_frq_order_test')
        logging.info(f"[{self.name}] -> Admin frq_order 테스트 완료")

        # frq_answer 테스트 (다른 컴포넌트에게 고빈도 질의)
        result = self.frq_answer('admin', 'frq_answer test')
        logging.info(f"[{self.name}] -> Admin frq_answer 테스트 / {result}")

        # 작업 완료 플래그 설정
        gm.admin.trading_done = True
        self.trading_done = True
        logging.info(f"[{self.name}] 작업 완료")
        
        # Admin에게 완료 통보
        gm.admin.order('on_component_done', 'stg')

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
        result = self.frq_answer('admin', 'frq_answer test')
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
        result = self.answer('api', 'api_response', 'api call')
        logging.info(f"[{self.name}] -> API / {result}")


        result = self.answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG / {result}")

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
                gm.admin.order('start_admin')
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
        shutdown_order = ['stg', 'api', 'dbm', 'admin']
        
        # 순서대로 종료
        for name in shutdown_order:
            if component := all_components.get(name):
                try:
                    component.stop()
                    logging.info(f"[Main] {name.upper()} 종료")
                except Exception as e:
                    logging.error(f"[Main] {name.upper()} 종료 오류: {e}")
        
        # 혹시 누락된 컴포넌트들 처리
        for name, component in all_components.items():
            if name not in shutdown_order:
                try:
                    component.stop()
                    logging.info(f"[Main] {name.upper()} (추가) 종료")
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

