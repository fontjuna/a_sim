# 표준 라이브러리
import copy
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from queue import Empty, Queue

# 멀티프로세싱
import multiprocessing as mp

# PyQt5 관련
import pythoncom
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication

# 프로젝트 모듈
from public import init_logger

@dataclass
class Order:
    """비동기 요청 객체"""
    receiver: str          # 수신자 이름
    order: str             # 수신자가 실행할 함수명
    args: tuple = ()       # 위치 인자
    kwargs: dict = field(default_factory=dict)  # 키워드 인자

@dataclass
class Answer:
    """동기 요청 객체 (응답 필요)"""
    receiver: str          # 수신자 이름
    order: str             # 수신자가 실행할 함수명
    args: tuple = ()       # 위치 인자
    sender: str = None     # 발신자 이름 (응답 수신용)
    kwargs: dict = field(default_factory=dict)  # 키워드 인자
    qid: str = field(default_factory=lambda: str(uuid.uuid4()))  # 고유 ID

class ThreadDict:
    """쓰레드 안전 딕셔너리"""
    
    def __init__(self):
        self._dict = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        """키에 해당하는 값 반환 (없으면 기본값 반환)"""
        with self._lock:
            return self._dict.get(key, default)

    def set(self, key, value):
        """키-값 쌍 저장"""
        with self._lock:
            self._dict[key] = value

    def remove(self, key):
        """키 삭제 (키가 있는 경우만)"""
        with self._lock:
            if key in self._dict:
                del self._dict[key]
                
    def items(self):
        """현재 모든 항목의 복사본 반환"""
        with self._lock:
            return list(self._dict.items())
            
    def keys(self):
        """현재 모든 키의 복사본 반환"""
        with self._lock:
            return list(self._dict.keys())
            
    def values(self):
        """현재 모든 값의 복사본 반환"""
        with self._lock:
            return list(self._dict.values())
            
    def clear(self):
        """모든 항목 삭제"""
        with self._lock:
            self._dict.clear()

import logging
import time
import threading
from queue import Empty
from PyQt5.QtCore import QThread
import multiprocessing as mp

class Model():
    def __init__(self, name, myq=None):
        """
        기본 초기화
        
        Args:
            name (str): 컴포넌트 이름
            myq (dict): 컴포넌트의 큐 딕셔너리 {'receive', 'request', 'real'}
        """
        self.name = name
        self.myq = myq
        self.is_running = True
        self.is_stopping = False
        
        # 응답 추적을 위한 딕셔너리
        self._response_results = {}
        self._response_callbacks = {}
        self._pending_requests = set()
        
        # 성능 측정용 타이머
        self._perf_timers = {}
        
    def run(self):
        """컴포넌트 메인 루프"""
        logging.debug(f'{self.name} 시작...')
        last_housekeeping = time.time()
        
        while self.is_running:
            now = time.time()
            
            # 메시지 처리
            self.run_loop()
            
            # 1초마다 타임아웃된 응답 정리 (성능 영향 최소화)
            if now - last_housekeeping > 1.0:
                self._cleanup_timeouts(now)
                last_housekeeping = now
                
            # 초고속 루프를 위한 최소 슬립
            time.sleep(0.0001)  # 100 마이크로초 (일반 time.sleep보다 10배 빠름)
            
    def _cleanup_timeouts(self, now):
        """오래된 응답 요청 정리 (성능 최적화)"""
        # 시간 초과된 요청 찾기 (기본 3초)
        timeout_requests = []
        for qid in self._pending_requests:
            start_time = self._perf_timers.get(qid, 0)
            if start_time and now - start_time > 3.0:
                timeout_requests.append(qid)
                
        # 시간 초과된 요청 처리
        for qid in timeout_requests:
            # 콜백이 등록된 경우 실행
            if qid in self._response_callbacks:
                callback = self._response_callbacks.pop(qid)
                if callable(callback):
                    callback(None, "timeout")  # 콜백 인자: (결과, 상태)
            
            # 타이머 및 추적 정보 정리
            self._pending_requests.discard(qid)
            if qid in self._perf_timers:
                del self._perf_timers[qid]
                
    def run_loop(self):
        """메시지 처리 루프"""
        if self.is_stopping:  # 중지 중이면 새 요청 처리 안함
            return
            
        if not self.myq['receive'].empty():
            try:
                data = self.myq['receive'].get()
                if not isinstance(data, (Order, Answer)):
                    logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                    return
                
                # stop 명령이면 중지
                if isinstance(data, Order) and data.order == 'stop':
                    self.is_stopping = True
                    self.stop()
                    return
                
                # 특수 응답 메서드 처리
                if isinstance(data, Order) and data.order == '_response':
                    self._handle_response(data.args[0], data.args[1])
                    return
                
                # 일반 메서드 호출
                method = getattr(self, data.order)
                if isinstance(data, Order):
                    # 비동기 요청 처리
                    method(*data.args, **data.kwargs)
                else:
                    # 동기 요청 처리 및 결과 반환
                    result = method(*data.args, **data.kwargs)
                    # 응답이 필요한 경우 request 큐에 결과 추가
                    if data.sender:
                        response_obj = Order(
                            receiver=data.sender,
                            order='_response',  # 특수 응답 메서드
                            args=(data.qid, result)
                        )
                        self.myq['request'].put(response_obj)
            except Exception as e:
                logging.error(f"{self.name} 메시지 처리 중 오류: {e}", exc_info=True)

    def _handle_response(self, qid, result):
        """응답 처리 내부 메서드 (논블로킹)"""
        # 응답 결과 저장
        self._response_results[qid] = result
        
        # 응답 대기 추적 정보 정리
        self._pending_requests.discard(qid)
        
        # 성능 측정 로깅 (디버그용)
        if qid in self._perf_timers:
            elapsed = time.time() - self._perf_timers[qid]
            if elapsed > 0.001:  # 1밀리초 이상 걸린 경우만 로깅
                logging.debug(f"{self.name}: 응답 수신 (qid={qid}, 응답시간={elapsed:.6f}초)")
            del self._perf_timers[qid]
        
        # 콜백이 등록된 경우 실행
        if qid in self._response_callbacks:
            callback = self._response_callbacks.pop(qid)
            if callable(callback):
                callback(result, "success")  # 콜백 인자: (결과, 상태)

    def stop(self):
        """컴포넌트 중지"""
        logging.debug(f'{self.name} 중지 요청...')
        self.is_stopping = True
        self.is_running = False
        self._clear_queues()
        
        # 대기 중인 모든 응답에 대한 콜백 실행
        for qid in list(self._response_callbacks.keys()):
            callback = self._response_callbacks.pop(qid)
            if callable(callback):
                callback(None, "cancelled")  # 콜백 인자: (결과, 상태)
        
        # 추적 정보 정리
        self._response_results.clear()
        self._pending_requests.clear()
        self._perf_timers.clear()
        
    def _clear_queues(self):
        """큐 비우기"""
        if not self.myq:
            return
            
        try:
            for queue_name in ['receive', 'request', 'real']:
                queue = self.myq.get(queue_name)
                if queue:
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                        except Empty:
                            break
        except Exception as e:
            logging.error(f"{self.name} 큐 비우기 중 오류: {e}", exc_info=True)
    
    # 기존 메서드 유지 (order, send_real)
    def order(self, receiver, method=None, *args, **kwargs):
        """
        비동기 요청 전송
        
        사용 방법:
            order(Order객체)
            order(receiver, method, *args, **kwargs)
        """
        if method is None and isinstance(receiver, Order):
            # Order 객체가 직접 전달된 경우
            order_obj = receiver
        else:
            # 인자로 전달된 경우
            order_obj = Order(receiver=receiver, order=method, args=args, kwargs=kwargs)
        
        self.myq['request'].put(order_obj)
        return True
    
    def send_real(self, receiver, order, *args, **kwargs):
        """
        실시간 데이터 전송 (비동기)
        
        Args:
            receiver (str): 수신자 이름
            order (str): 수신자가 실행할 메서드 이름
            *args: 위치 인자
            **kwargs: 키워드 인자
        """
        order_obj = Order(receiver=receiver, order=order, args=args, kwargs=kwargs)
        self.myq['real'].put(order_obj)
    
    # ======== 초고속 처리를 위한 새로운 응답 메서드 ========
    
    def answer_async(self, receiver, method=None, *args, callback=None, **kwargs):
        """
        비동기 요청 전송 및 콜백 등록 (논블로킹)
        
        사용 방법:
            answer_async(Answer객체, callback=callback_func)
            answer_async(receiver, method, *args, callback=callback_func, **kwargs)
            
        Args:
            receiver: Answer 객체 또는 수신자 이름
            method: 메서드 이름 (Answer 객체 전달 시 None)
            callback: 결과 처리 콜백 함수 callback(result, status)
            *args, **kwargs: 요청 인자
            
        Returns:
            str: 요청 ID
        """
        # Answer 객체 생성
        if method is None and isinstance(receiver, Answer):
            # Answer 객체가 직접 전달된 경우
            answer_obj = receiver
            callback = kwargs.get('callback')
        else:
            # 인자로 전달된 경우 (callback을 kwargs에서 제거)
            if 'callback' in kwargs:
                callback = kwargs.pop('callback')
                
            answer_obj = Answer(
                receiver=receiver, 
                order=method, 
                sender=self.name,
                args=args, 
                kwargs=kwargs
            )
        
        # 요청 추적 정보 설정
        qid = answer_obj.qid
        self._pending_requests.add(qid)
        self._perf_timers[qid] = time.time()  # 타이머 시작
        
        # 콜백 등록
        if callback:
            self._response_callbacks[qid] = callback
        
        # 요청 전송
        self.myq['request'].put(answer_obj)
        return qid
    
    def answer_nonblocking(self, receiver, method=None, *args, **kwargs):
        """
        논블로킹 요청 전송 (요청 ID 반환)
        
        사용 방법:
            qid = answer_nonblocking(Answer객체)
            qid = answer_nonblocking(receiver, method, *args, **kwargs)
            
            # 응답 확인 (논블로킹)
            result = check_response(qid)
            
        Returns:
            str: 요청 ID
        """
        return self.answer_async(receiver, method, *args, **kwargs)
    
    def check_response(self, qid):
        """
        응답 확인 (논블로킹)
        
        Args:
            qid (str): 요청 ID
            
        Returns:
            결과 또는 None (아직 응답이 없는 경우)
        """
        return self._response_results.get(qid)
    
    def answer_poll(self, answer_obj, retry_count=10, retry_interval=0.0001):
        """
        폴링 방식의 응답 확인 (타임아웃까지 주기적으로 확인)
        
        Args:
            answer_obj (Answer): 응답 요청 객체
            retry_count (int): 재시도 횟수
            retry_interval (float): 재시도 간격 (초)
            
        Returns:
            결과 또는 None (타임아웃)
        """
        # 요청 전송
        qid = self.answer_nonblocking(answer_obj)
        
        # 폴링 (재시도 횟수만큼)
        for _ in range(retry_count):
            # 다른 메시지 처리
            if not self.myq['receive'].empty():
                self.run_loop()
                
            # 응답 확인
            result = self.check_response(qid)
            if result is not None:
                return result
                
            # 짧은 대기
            time.sleep(retry_interval)
        
        # 타임아웃 (결과 없음)
        return None
    
    def answer(self, receiver, method=None, *args, timeout=0.001, **kwargs):
        """
        동기 요청 전송 및 응답 대기 (짧은 타임아웃)
        - 호환성을 위해 유지, 고성능 처리에는 answer_async 또는 answer_poll 권장
        
        사용 방법:
            answer(Answer객체, timeout=0.001)
            answer(receiver, method, *args, timeout=0.001, **kwargs)
            
        Args:
            timeout (float): 응답 대기 최대 시간 (초)
            
        Returns:
            응답 결과 또는 None (타임아웃 시)
        """
        # 기존 호환성을 위해 블로킹 방식 유지
        # Answer 객체 생성
        if method is None and isinstance(receiver, Answer):
            # Answer 객체가 직접 전달된 경우
            answer_obj = receiver
            timeout = kwargs.get('timeout', timeout)
        else:
            # 인자로 전달된 경우
            answer_obj = Answer(
                receiver=receiver, 
                order=method, 
                sender=self.name,
                args=args, 
                kwargs={k: v for k, v in kwargs.items() if k != 'timeout'}
            )
        
        # 폴링 방식으로 구현 (매우 짧은 주기로 확인)
        retry_count = max(int(timeout / 0.0001), 1)  # 최소 1회
        return self.answer_poll(answer_obj, retry_count=retry_count, retry_interval=0.0001)
    
class ModelThread(Model, QThread):
    """쓰레드 기반 컴포넌트"""
    
    def __init__(self, name, myq=None, daemon=True):
        Model.__init__(self, name, myq)
        QThread.__init__(self)
        self.daemon = daemon

    def run(self):
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 쓰레드 종료...')
        # 자기 자신에서 wait 호출 방지
        if QThread.currentThread() != self:
            self.quit()
            self.wait()

    def start(self):
        QThread.start(self)
        return self

class ModelProcess(Model, mp.Process):
    """프로세스 기반 컴포넌트"""
    
    def __init__(self, name, myq=None, daemon=True):
        Model.__init__(self, name, myq)
        mp.Process.__init__(self, name=name, daemon=daemon)

    def run(self):
        # 프로세스 시작 시 초기화
        import threading
        threading.current_thread().name = f"{self.name}_main"
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        mp.Process.start(self)
        return self
    
class IPCManager:
    """프로세스/쓰레드 간 통신 관리자"""
    
    def __init__(self):
        # 컴포넌트 관리
        self.qdict = {}  # 컴포넌트별 큐
        self.admin_work = {}  # 메인 쓰레드 컴포넌트
        self.thread_work = {}  # 쓰레드 컴포넌트
        self.process_work = {}  # 프로세스 컴포넌트
        self.instances = {}  # 모든 컴포넌트 인스턴스
        
        # 상태 관리
        self.result_dict = ThreadDict()  # 응답 결과 저장
        self.pending_answers = ThreadDict()  # 대기 중인 응답 추적
        self.stopped_components = set()  # 중지된 컴포넌트
        self.direct_responses = ThreadDict()  # 직접 호출 응답
        
        # 통신 처리 쓰레드
        self.running = True
        self.message_thread = threading.Thread(target=self.message_loop)
        self.message_thread.daemon = True
        self.message_thread.start()
        
    def message_loop(self):
        """
        메시지 처리 루프:
        1. 모든 컴포넌트의 real 큐 처리
        2. 모든 컴포넌트의 request 큐 처리
        3. 메인 쓰레드 컴포넌트의 receive 큐 처리
        """
        while self.running:
            # 1. 모든 컴포넌트의 real 큐 처리
            for name, queues in list(self.qdict.items()):
                if name not in self.stopped_components:
                    self.process_real_queue(name, queues['real'])
            
            # 2. 모든 컴포넌트의 request 큐 처리
            for name, queues in list(self.qdict.items()):
                if name not in self.stopped_components:
                    self.process_request_queue(name, queues['request'])
            
            # 3. 메인 쓰레드 컴포넌트의 receive 큐 처리
            for name, instance in list(self.admin_work.items()):
                if name not in self.stopped_components:
                    self.process_component_receives(name, instance)
            
            time.sleep(0.001)
    
    def process_real_queue(self, sender_name, real_queue):
        """
        실시간 큐 처리: real 큐에서 메시지를 읽어 적절한 receiver로 전달
        """
        try:
            while not real_queue.empty():
                data = real_queue.get_nowait()
                
                # Order 처리
                if isinstance(data, Order):
                    receiver = data.receiver
                    # 중지된 컴포넌트로는 메시지 전달 안함
                    if receiver in self.qdict and receiver not in self.stopped_components:
                        # 수신자의 receive 큐로 전달
                        self.qdict[receiver]['receive'].put(data)
                    else:
                        logging.debug(f"실시간 메시지 전달 불가: {receiver}가 존재하지 않거나 중지됨")
                else:
                    logging.debug(f'{sender_name}의 real 큐에 잘못된 데이터: {data}')
        except Empty:
            pass
        except Exception as e:
            logging.error(f"Real 큐 처리 중 오류: {e}", exc_info=True)
    
    def process_request_queue(self, sender_name, request_queue):
        """
        요청 큐 처리: request 큐에서 메시지를 읽어 적절한 receiver로 전달
        """
        try:
            while not request_queue.empty():
                data = request_queue.get_nowait()
                
                # Order 또는 Answer 처리
                if isinstance(data, (Order, Answer)):
                    receiver = data.receiver
                    # 중지된 컴포넌트로는 메시지 전달 안함
                    if receiver in self.qdict and receiver not in self.stopped_components:
                        # 수신자의 receive 큐로 전달
                        self.qdict[receiver]['receive'].put(data)
                    elif receiver == '_direct_':
                        # 직접 호출 응답 처리
                        if isinstance(data, Order) and len(data.args) >= 2:
                            qid, result = data.args
                            # 대기 중인 직접 호출 응답 처리
                            response_info = self.direct_responses.get(qid)
                            if response_info:
                                event, container = response_info
                                container['value'] = result
                                event.set()
                                self.direct_responses.remove(qid)
                    else:
                        logging.debug(f"요청 전달 불가: {receiver}가 존재하지 않거나 중지됨")
                else:
                    logging.debug(f'{sender_name}의 request 큐에 잘못된 데이터: {data}')
        except Empty:
            pass
        except Exception as e:
            logging.error(f"Request 큐 처리 중 오류: {e}", exc_info=True)
    
    def process_component_receives(self, name, instance):
        """
        메인 쓰레드 컴포넌트의 메시지 처리
        """
        try:
            if name in self.qdict and not self.qdict[name]['receive'].empty():
                # 이 부분은 Model.run_loop와 동일한 로직이지만
                # 메인 쓰레드 컴포넌트는 자체 쓰레드가 없으므로 여기서 처리
                data = self.qdict[name]['receive'].get_nowait()
                if not isinstance(data, (Order, Answer)):
                    logging.debug(f'{name} 에 잘못된 요청: {data}')
                    return
                
                # stop 명령이면 중지 상태로 표시
                if isinstance(data, Order) and data.order == 'stop':
                    self.stopped_components.add(name)
                    if hasattr(instance, 'stop'):
                        instance.stop()
                    return
                
                # 특수 응답 메서드 처리
                if isinstance(data, Order) and data.order == '_response':
                    if hasattr(instance, '_handle_response'):
                        instance._handle_response(data.args[0], data.args[1])
                    return
                
                # 일반 메서드 호출
                method = getattr(instance, data.order)
                if isinstance(data, Order):
                    # 비동기 요청 처리
                    method(*data.args, **data.kwargs)
                else:
                    # 동기 요청 처리 및 결과 반환
                    result = method(*data.args, **data.kwargs)
                    # 응답이 필요한 경우 request 큐에 결과 추가
                    if data.sender:
                        response_obj = Order(
                            receiver=data.sender,
                            order='_response',
                            args=(data.qid, result)
                        )
                        self.qdict[name]['request'].put(response_obj)
        except Empty:
            pass
        except Exception as e:
            logging.error(f"{name} 메시지 처리 중 오류: {e}", exc_info=True)
                    
    def register(self, name, cls, *args, type=None, start=False, **kwargs):
        """
        컴포넌트 등록: 컴포넌트별 큐 생성 및 인스턴스 초기화
        """
        if name in self.qdict: 
            self.unregister(name)

        # 중지된 컴포넌트 목록에서 제거
        if name in self.stopped_components:
            self.stopped_components.remove(name)

        # 큐 타입 결정 (프로세스면 mp.Queue, 아니면 Queue)
        is_process = type == 'process'
        queue_type = mp.Queue if is_process else Queue
        
        # 컴포넌트별 큐 생성
        self.qdict[name] = {
            'receive': queue_type(),  # 외부에서 받는 큐
            'request': queue_type(),  # 외부로 보내는 큐
            'real': queue_type()      # 실시간 데이터 큐
        }
        
        # 타입에 따라 적절한 모델 클래스 상속 및 인스턴스 생성
        if type == 'thread':
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.thread_work[name] = cls_instance
            if start and hasattr(cls_instance, 'start'):
                cls_instance.start()
        elif type == 'process':
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.process_work[name] = cls_instance
            if start and hasattr(cls_instance, 'start'):
                cls_instance.start()
        else:  # type == None (main thread)
            cls_instance = cls(name, self.qdict[name], *args, **kwargs)
            self.admin_work[name] = cls_instance
            if start:
                threading.Thread(target=cls_instance.run).start()
        
        self.instances[name] = cls_instance
        return cls_instance

    def unregister(self, name):
        """
        등록된 컴포넌트 제거
        """
        if name in self.admin_work and name == 'admin': 
            return False  # admin은 제거 불가
            
        if name in self.qdict:
            try:
                # 먼저 중지된 컴포넌트로 표시
                self.stopped_components.add(name)
                
                # 컴포넌트 중지 요청
                self.qdict[name]['receive'].put(Order(receiver=name, order='stop'))
                time.sleep(0.1)  # 중지 요청 처리 시간
                
                # 인스턴스 정리
                if name in self.thread_work:
                    self.thread_work[name].stop()
                    time.sleep(0.1)
                    self.thread_work.pop(name)
                elif name in self.process_work:
                    self.process_work[name].stop()
                    time.sleep(0.1)
                    self.process_work[name].join(timeout=1.0)
                    self.process_work.pop(name)
            except Exception as e:
                logging.error(f"{name} 컴포넌트 제거 중 오류: {e}", exc_info=True)
        else:
            logging.error(f"IPCManager에 없는 이름입니다: {name}")
            return False
            
        # 정리
        if name in self.instances:
            self.instances.pop(name)
        if name in self.qdict:
            self.qdict.pop(name)
        return True

    def start(self, name):
        """
        등록된 컴포넌트 시작
        """
        if name not in self.qdict:
            logging.error(f"존재하지 않는 컴포넌트입니다: {name}")
            return False
        
        # 중지된 컴포넌트 목록에서 제거
        if name in self.stopped_components:
            self.stopped_components.remove(name)
            
        self.qdict[name]['receive'].put(Order(receiver=name, order='start'))
        return True
        
    def stop(self, name):
        """
        등록된 컴포넌트 중지
        """
        if name not in self.qdict:
            logging.error(f"존재하지 않는 컴포넌트입니다: {name}")
            return False
            
        # 중지된 컴포넌트 목록에 추가
        self.stopped_components.add(name)
        self.qdict[name]['receive'].put(Order(receiver=name, order='stop'))
        return True

    def order(self, order_obj):
        """
        Order 객체를 통한 비동기 요청 (직접 호출 및 등록된 컴포넌트 모두 지원)
        """
        if not isinstance(order_obj, Order):
            logging.error(f"order_obj가 잘못된 타입입니다: {order_obj}")
            return False
            
        receiver = order_obj.receiver
        if receiver not in self.qdict:
            logging.error(f"존재하지 않는 receiver입니다: {receiver}")
            return False
            
        # 중지된 컴포넌트로는 요청 안보냄
        if receiver in self.stopped_components:
            logging.debug(f"중지된 컴포넌트로 요청 무시: {receiver}")
            return False
            
        self.qdict[receiver]['receive'].put(order_obj)
        return True

    def answer(self, answer_obj, timeout=10):
        """
        Answer 객체를 통한 동기식 요청/응답 (직접 호출 및 등록된 컴포넌트 모두 지원)
        """
        if not isinstance(answer_obj, Answer):
            logging.error(f"answer_obj가 잘못된 타입입니다: {answer_obj}")
            return None
        
        # 내부 호출인지 직접 호출인지 확인
        is_direct_call = False
        sender = answer_obj.sender
        
        if not sender:
            # 발신자가 없으면 직접 호출로 간주
            is_direct_call = True
            answer_obj = copy.copy(answer_obj)
            answer_obj.sender = '_direct_'
        
        receiver = answer_obj.receiver
        if receiver not in self.qdict:
            logging.error(f"존재하지 않는 receiver입니다: {receiver}")
            return None
            
        # 중지된 컴포넌트로는 요청 안보냄
        if receiver in self.stopped_components:
            logging.debug(f"중지된 컴포넌트로 동기 요청 무시: {receiver}")
            return None
        
        # 직접 호출인 경우 응답 대기 이벤트 설정(등록 되지 않은 컴포넌트에서 호출 되는 경우)
        if is_direct_call:
            # 응답 대기를 위한 준비
            result_container = {'value': None}
            result_event = threading.Event()

            # 응답 추적 설정
            qid = answer_obj.qid
            self.direct_responses.set(qid, (result_event, result_container))
            
            # 요청 전송
            self.qdict[receiver]['receive'].put(answer_obj)

            # 응답 대기
            if result_event.wait(timeout):
                # 정리 후 결과 반환
                self.direct_responses.remove(qid)
                return result_container['value']
            else:
                # 타임아웃 시 리소스 정리
                self.direct_responses.remove(qid)
                logging.error(f"응답 대기 시간 초과: {answer_obj.sender} -> {receiver}.{answer_obj.order}")
                return None
        else:
            # 등록된 컴포넌트에서의 호출
            self.qdict[receiver]['receive'].put(answer_obj)
            return True

    def cleanup(self):
        """
        모든 리소스 정리
        """
        logging.debug('IPCManager 리소스 정리 시작')
        self.running = False
        
        # 모든 컴포넌트 중지
        for name in list(self.qdict.keys()):
            # 중지 상태 표시 및 중지 요청
            self.stopped_components.add(name)
            self.stop(name)
        
        # 대기 중인 모든 응답 취소
        for qid, (event, container) in list(self.direct_responses.items()):
            container['value'] = None
            event.set()
            self.direct_responses.remove(qid)
        
        time.sleep(0.5)  # 정지 요청 처리 대기
        
        # 모든 쓰레드 컴포넌트 제거
        for name in list(self.thread_work.keys()):
            self.unregister(name)
            
        # 모든 프로세스 컴포넌트 제거
        for name in list(self.process_work.keys()):
            self.unregister(name)
        
        # 메인 쓰레드 컴포넌트 정리
        for name in list(self.admin_work.keys()):
            if hasattr(self.admin_work[name], 'stop'):
                self.admin_work[name].stop()
        
        # 메시지 쓰레드 종료
        if hasattr(self, 'message_thread') and self.message_thread.is_alive():
            self.message_thread.join(timeout=1.0)
            
        logging.debug('IPCManager 리소스 정리 완료')

app = QApplication(sys.argv)

class TestClass:
    """기본 테스트 클래스"""
    
    def __init__(self, name, *args, **kwargs):
        self.name = name
    
    def run_method(self, data, *args, **kwargs):
        """테스트용 메서드: 입력 데이터를 로깅하고 결과 반환"""
        logging.info(f"{self.name} 이 호출됨, 데이터:{data}")
        return f"{self.name} 에서 반환: *{data}*"

    def call_async(self, data, *args, **kwargs):
        """비동기 호출 테스트 메서드"""
        logging.info(f"{self.name} 에서 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        """콜백 테스트 메서드"""
        logging.info(f"{self.name} 에서 콜백 결과 수신: {data}")
        return f"{self.name} 에서 콜백 요청 데이타: {data}"

class Strategy(TestClass, ModelThread):
    """쓰레드 기반 전략 클래스"""
    
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelThread.__init__(self, name, myq, daemon)

    def stop(self):
        """전략 중지 및 리소스 정리"""
        ModelThread.stop(self)

class DBM(TestClass, ModelProcess):
    """프로세스 기반 DBM 클래스"""
    
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelProcess.__init__(self, name, myq, daemon)

    def stop(self):
        """DBM 중지 및 리소스 정리"""
        ModelProcess.stop(self)

    def get_name(self, code):
        """종목 코드로 종목명 조회"""
        # API에 종목명 요청
        logging.info(f"DBM: {code} 종목명 조회 요청")
        
        # API 호출 (동기식)
        answer_obj = Answer(
            receiver='api', 
            order='GetMasterCodeName', 
            sender=self.name, 
            args=(code,)
        )
        
        # 요청 전송 및 응답 대기
        result = self.answer(answer_obj)
        logging.info(f"DBM: 종목명 조회 결과: {result}")
        return result

class API(TestClass, ModelProcess):
    """프로세스 기반 API 클래스"""
    
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelProcess.__init__(self, name, myq, daemon)
        self.connected = False
        self.send_real_data_running = False
        self.send_real_data_thread = None
        self.ocx = None

    def init(self):
        """API 초기화"""
        # QAxWidget 초기화 및 콜백 설정
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        logging.info("API 초기화 완료")

    def GetConnectState(self):
        """연결 상태 확인"""
        if self.ocx:
            state = self.ocx.dynamicCall("GetConnectState()")
            logging.info(f"API 연결 상태: {state}")
            return state
        logging.warning("OCX가 초기화되지 않았습니다")
        return 0

    def send_real_data_start(self):
        """실시간 데이터 전송 시작"""
        self.send_real_data_running = True
        self.send_real_data_thread = threading.Thread(target=self.send_real_data)
        self.send_real_data_thread.daemon = True
        self.send_real_data_thread.start()
        logging.info("실시간 데이터 전송 시작")

    def send_real_data_stop(self):
        """실시간 데이터 전송 중지"""
        self.send_real_data_running = False
        if self.send_real_data_thread and self.send_real_data_thread.is_alive():
            self.send_real_data_thread.join(timeout=1.0)
        logging.info("실시간 데이터 전송 중지")

    def send_real_data(self):
        """실시간 데이터 전송 스레드 메서드"""
        while self.send_real_data_running:
            # admin 컴포넌트로 실시간 데이터 전송
            self.send_real('admin', 'real_data_receive', f'real_data {time.strftime("%Y-%m-%d %H:%M:%S")}')
            time.sleep(0.01)

    def stop(self):
        """API 중지 및 리소스 정리"""
        if hasattr(self, 'send_real_data_running') and self.send_real_data_running:
            self.send_real_data_stop()
        ModelProcess.stop(self)

    def is_connected(self):
        """연결 상태 반환"""
        return self.connected

    def OnEventConnect(self, err_code):
        """로그인 이벤트 처리"""
        if err_code == 0:
            self.connected = True
            logging.info("로그인 성공")
        else:
            logging.error(f"로그인 실패: {err_code}")

    def login(self):
        """로그인 요청"""
        if not self.ocx:
            logging.error("OCX가 초기화되지 않았습니다. init()을 먼저 호출하세요.")
            return False
        
        self.connected = False
        self.ocx.dynamicCall("CommConnect()")
        
        # 로그인 완료 대기
        while not self.connected:
            pythoncom.PumpWaitingMessages()
        
        return True

    def GetMasterCodeName(self, code):
        """종목 코드로 종목명 조회"""
        if not self.ocx:
            logging.error("OCX가 초기화되지 않았습니다. init()을 먼저 호출하세요.")
            return ""
            
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
        logging.info(f"GetMasterCodeName 호출: {code} {data}")
        return data

class Admin(TestClass, Model):
    """메인 스레드 관리자 클래스"""
    
    def __init__(self, name, myq=None, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        Model.__init__(self, name, myq)
        self.start_time = time.time()
        self.counter = 0
        self.testing_complete = False

    def real_data_receive(self, data):
        """실시간 데이터 처리"""
        self.counter += 1
        if time.time() - self.start_time > 2:
            logging.info(f"Admin: 2초간 받은 real_data 횟수={self.counter} 마지막 데이터={data}")
            self.start_time = time.time()
            self.counter = 0
    
    def start_test(self):
        """통합 테스트 실행"""
        try:
            logging.info(' === 테스트 코드 === ')

            # 테스트용 쓰레드 등록 (API와 DBM은 Main.init에서 등록됨)
            gm.전략01 = gm.ipc.register('전략01', Strategy, type='thread', start=True)
            gm.전략02 = gm.ipc.register('전략02', Strategy, type='thread', start=True)
                
            # 멀티 쓰레드 호출
            gm.ipc.order(Order(receiver='전략01', order='run_method', args=("admin 에서 order 호출",)))
            
            # 멀티 쓰레드 응답  
            answer = Answer(receiver='전략01', order='run_method', sender='admin', args=("admin 에서 answer 호출",))
            result = gm.ipc.answer(answer)
            logging.info(f"전략01 응답 결과: {result}")
            
            # 멀티 프로세스 api 호출
            answer = Answer(receiver='api', order='GetMasterCodeName', sender='admin', args=("005930",))
            result = gm.ipc.answer(answer)
            logging.info(f"API 호출 결과: {result}")
            
            # 멀티 프로세스 dbm 비동기 호출
            gm.ipc.order(Order(receiver='dbm', order='call_async', args=('async : admin 에서 dbm 호출',)))

            # 멀티 프로세스 dbm 에서 api 호출
            answer = Answer(receiver='dbm', order='get_name', sender='admin', args=("005930",))
            result = gm.ipc.answer(answer)
            logging.info(f"dbm의 get_name 호출 결과: {result}")

            logging.info('--- 전략01 클래스 메소드 내에서 실행 ---')
            # 전략01에서 admin 호출
            gm.ipc.order(Order(receiver='전략01', order='order', args=('admin', 'run_method', '전략01 에서 admin 호출')))
            time.sleep(0.1)  # 비동기 요청 처리 대기

            logging.info('--- 직접 호출 테스트 ---')
            result = gm.ipc.answer(Answer(receiver='api', order='GetMasterCodeName', args=("000660",)))
            logging.info(f"직접 호출 결과: {result}")

            logging.info('--- 실시간 데이터 처리 테스트 ---')
            time.sleep(3)  # 실시간 데이터 카운터 테스트를 위한 대기
            
            # 정리
            logging.info('--- 테스트 정리 ---')
            # 먼저 실시간 데이터 중지
            gm.ipc.order(Order(receiver='api', order='send_real_data_stop'))
            time.sleep(1)
            
            # 테스트 완료 표시
            logging.info(' === 테스트 코드 끝 === ')
            self.testing_complete = True
            
            # 프로그램 종료
            time.sleep(1)
            os._exit(0)
            
        except Exception as e:
            logging.error(f"테스트 실행 중 오류 발생: {e}", exc_info=True)
            os._exit(1)

class GlobalSharedMemory:
    """전역 공유 변수 (메인 프로세스에서만 사용)"""
    def __init__(self):
        self.main = None
        self.admin = None
        self.api = None
        self.gui = None
        self.dbm = None
        self.전략01 = None
        self.전략02 = None
        self.ipc = None
gm = GlobalSharedMemory()

class Main:
    """메인 클래스"""
    def __init__(self):
        self.init()

    def init(self):
        """초기화: IPC 및 기본 컴포넌트 생성"""
        try:
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
            
            # IPC Manager 생성
            gm.ipc = IPCManager()
            
            # 기본 컴포넌트 등록
            gm.admin = gm.ipc.register('admin', Admin, start=True) # 메인 쓰레드 컴포넌트
            
            # API 및 DBM 컴포넌트 등록
            gm.api = gm.ipc.register('api', API, type='process', start=True)
            gm.dbm = gm.ipc.register('dbm', DBM, type='process', start=True)

            # 초기화를 위한 대기
            time.sleep(1)

            logging.info('--- 서버 접속 로그인 실행 ---')
            gm.ipc.order(Order(receiver='api', order='init'))
            
            # 초기화 완료 확인을 위한 대기
            time.sleep(1)
            
            # 로그인 요청
            gm.ipc.order(Order(receiver='api', order='login'))
            
            # 로그인 완료 확인
            con_result = 0
            while con_result == 0:
                con_result = gm.ipc.answer(Answer(receiver='api', order='GetConnectState', sender='admin'))
                if con_result == 1:
                    logging.info("API 로그인 완료")
                    break
                time.sleep(0.1)
            
            # 실시간 데이터 전송 시작
            gm.ipc.order(Order(receiver='api', order='send_real_data_start'))
            
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 종료')

        except Exception as e:
            logging.error(f"초기화 중 오류: {e}", exc_info=True)

    def run_admin(self):
        """Admin 테스트 실행"""
        gm.ipc.order(Order(receiver='admin', order='start_test'))
        
        # 테스트가 완료될 때까지 대기
        for _ in range(300):  # 최대 30초 대기
            if hasattr(gm.admin, 'testing_complete') and gm.admin.testing_complete:
                break
            time.sleep(0.1)

if __name__ == "__main__":
    # 멀티프로세싱 지원
    mp.freeze_support()
    
    # 초기화
    init_logger()
    
    try:
        # 메인 실행
        gm.main = Main()
        gm.main.run_admin()
    except Exception as e:
        logging.error(f"메인 실행 중 오류: {e}", exc_info=True)
    finally:
        # 정리
        if hasattr(gm, 'ipc') and gm.ipc:
            gm.ipc.cleanup() # 모든 쓰레드와 프로세스 정리
        logging.shutdown()
        os._exit(0)


