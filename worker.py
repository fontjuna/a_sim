from dataclasses import dataclass, field
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from queue import Queue, Empty
import threading
import pythoncom
import multiprocessing as mp
import logging
import logging.config
import time
import uuid
import sys
import os
import copy
from dataclasses import dataclass, field

def init_logger():
    # 로깅 초기화 코드 (간단하게 표준 로거 사용)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)03d-%(levelname)s-[%(filename)s(%(lineno)d) / %(funcName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

init_logger()
app = QApplication(sys.argv)

@dataclass
class Order:
    receiver: str          # 응답자 이름
    order: str             # 응답자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

@dataclass
class Answer:
    receiver: str          # 응답자 이름
    order: str             # 응답자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    args: tuple = ()
    sender: str = None     # 요청자 이름
    kwargs: dict = field(default_factory=dict)
    qid: str = None        # 동기식 요청에 대한 답변 식별자
    
class ThreadDict:
    def __init__(self):
        self._dict = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._dict[key] = value

    def remove(self, key):
        with self._lock:
            if key in self._dict:
                del self._dict[key]

"""
## 호출 패턴 정리 (올바른 문법)

1. **등록되지 않은 클래스(위치)에서 호출**:
   - `ipc.direct_order(Order객체)` - 비동기 요청 (응답 필요 없음)
   - `ipc.direct_answer(Answer객체)` - 동기 요청 (응답 필요)

2. **메인 쓰레드에서 호출** (IPCManager에 등록된 컴포넌트):
   - `ipc.order(Order객체)` - 비동기 요청
   - `ipc.answer(Answer객체)` - 동기 요청

3. **멀티 쓰레드, 멀티 프로세스에서 호출**:
   - `self.proxy_order(target, method, *args, **kwargs)` - 비동기 요청 (내부적으로 특수 명령 처리)
   - `self.proxy_answer(target, method, *args, **kwargs)` - 동기 요청 (내부적으로 특수 명령 처리)
"""

class Model():
    def __init__(self, name, myq=None):
        super().__init__()
        self.name = name
        self.myq = myq
        self.is_running = True
        self.is_stopping = False  # 중지 중 플래그 추가

    def run(self):
        logging.debug(f'{self.name} 시작...')
        while self.is_running:
            self.run_loop()
            time.sleep(0.001)
            
    def run_loop(self):
        if self.is_stopping:  # 중지 중이면 새 요청 처리 안함
            return
            
        if not self.myq['order'].empty():
            try:
                data = self.myq['order'].get()
                if not isinstance(data, (Order, Answer)):
                    logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                    return
                
                # stop 명령이면 is_stopping 플래그 설정
                if isinstance(data, Order) and data.order == 'stop':
                    self.is_stopping = True
                    self.stop()
                    return
                
                # 프록시 요청 처리 (프로세스 간 통신용)
                if data.order.startswith('_proxy_request_'):
                    parts = data.order.split('_', 3)  # _proxy_request_TARGET_METHOD
                    if len(parts) >= 4:
                        target = parts[2]
                        method = parts[3]
                        # 메인 프로세스에 요청 전달을 위해 real 큐 사용
                        self.myq['real'].put(Order(
                            receiver=target,
                            order=method,
                            args=data.args,
                            kwargs=data.kwargs
                        ))
                    else:
                        logging.error(f"잘못된 프록시 요청 형식: {data.order}")
                    return
                elif data.order.startswith('_proxy_answer_'):
                    parts = data.order.split('_', 3)  # _proxy_answer_TARGET_METHOD
                    if len(parts) >= 4:
                        target = parts[2]
                        method = parts[3]
                        
                        # 요청 ID 추출
                        req_id = data.kwargs.pop('_proxy_req_id', str(uuid.uuid4()))
                        
                        # 메인 프로세스에 요청 전달을 위해 real 큐 사용
                        self.myq['real'].put(Answer(
                            receiver=target,
                            order=method,
                            sender=self.name,
                            args=data.args,
                            kwargs=data.kwargs,
                            qid=req_id  # 요청 ID를 qid로 사용
                        ))
                    else:
                        logging.error(f"잘못된 프록시 응답 요청 형식: {data.order}")
                    return
                
                method = getattr(self, data.order)
                if isinstance(data, Order):
                    method(*data.args, **data.kwargs)
                else:
                    result = method(*data.args, **data.kwargs)
                    # Answer 응답은 자신의 answer 큐에 반환
                    self.myq['answer'].put((data.qid, result))
            except Exception as e:
                logging.error(f"{self.name} 메시지 처리 중 오류: {e}", exc_info=True)

    def stop(self):
        logging.debug(f'{self.name} 중지 요청...')
        self.is_stopping = True  # 중지 중 플래그 설정
        self.is_running = False
        # 큐 비우기
        self._clear_queues()
        
    def _clear_queues(self):
        """큐 비우기"""
        if not self.myq:
            return
            
        try:
            # 남은 order 큐 비우기
            while not self.myq['order'].empty():
                try:
                    self.myq['order'].get_nowait()
                except Empty:
                    break
                    
            # 남은 answer 큐 비우기 (응답 대기 중인 요청에 대해 None 응답 반환)
            while not self.myq['answer'].empty():
                try:
                    self.myq['answer'].get_nowait()
                except Empty:
                    break
        except Exception as e:
            logging.error(f"{self.name} 큐 비우기 중 오류: {e}", exc_info=True)
    
    # Model.proxy_order
    def proxy_order(self, target, method, *args, **kwargs):
        """
        다른 컴포넌트에 비동기 요청을 보내는 프록시 메서드
        """
        # 특수 명령 형식: _proxy_request_TARGET_METHOD
        special_order = f"_proxy_request_{target}_{method}"
        self.myq['order'].put(Order(
            receiver=self.name,  # 자신에게 요청
            order=special_order,
            args=args,
            kwargs=kwargs
        ))
        return True

    def proxy_answer(self, target, method, *args, timeout=10, **kwargs):
        """
        다른 컴포넌트에 동기 요청을 보내고 응답을 받는 프록시 메서드
        프로세스 간 통신에 적합
        """
        answer_obj = Answer(
            receiver=self.name,  # 자신을 수신자로
            order="_proxy_answer_" + target + "_" + method,  # 특수 명령 형식
            args=args,
            kwargs=kwargs,
            sender=self.name  # 자신을 발신자로
        )
        
        # 요청 전송
        self.myq['order'].put(answer_obj)
        
        # 응답 대기
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if not self.myq['answer'].empty():
                    qid, result = self.myq['answer'].get_nowait()
                    return result
            except Empty:
                pass
            time.sleep(0.001)
        
        logging.error(f"proxy_answer 요청 시간 초과: {self.name} -> {target}.{method}")
        return None
    
    def proxy_answer_internal(self, answer_obj, timeout=10):
        """
        내부 응답 처리용 메서드
        """
        try:
            # 메서드 직접 호출
            if hasattr(self, answer_obj.order):
                method = getattr(self, answer_obj.order)
                return method(*answer_obj.args, **answer_obj.kwargs)
            else:
                logging.error(f"{self.name}에 메서드 없음: {answer_obj.order}")
                return None
        except Exception as e:
            logging.error(f"proxy_answer_internal 오류: {e}", exc_info=True)
            return None

class ModelThread(Model, QThread):
    def __init__(self, name, myq=None, daemon=True):
        Model.__init__(self, name, myq)
        QThread.__init__(self)
        self.daemon = daemon

    def run(self):
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 쓰레드 종료...')
        self.quit()
        self.wait()

    def start(self):
        QThread.start(self)
        return self

class ModelProcess(Model, mp.Process):
    def __init__(self, name, myq=None, daemon=True):
        Model.__init__(self, name, myq)
        mp.Process.__init__(self, name=name, daemon=daemon)

    def run(self):
        Model.run(self)

    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 프로세스 종료...')

    def start(self):
        mp.Process.start(self)
        return self

class IPCManager():
    def __init__(self):
        self.qdict = {}
        self.admin_work = {}
        self.thread_work = {}
        self.process_work = {}
        self.instances = {}
        self.result_dict = ThreadDict()  # IPCManager에만 ThreadDict
        self.pending_answers = ThreadDict()  # 대기 중인 응답 추적
        self.stopped_components = set()  # 중지된 컴포넌트 추적
        self.global_responses = ThreadDict()  # 글로벌 응답 메커니즘 (등록되지 않은 위치를 위한)
        
        # 메시지 처리 및 프록시 스레드
        self.running = True
        self.message_thread = threading.Thread(target=self.message_loop)
        self.message_thread.daemon = True
        self.message_thread.start()
        
    def message_loop(self):
        """
        메시지 처리 루프: 
        1. 모든 컴포넌트의 real 큐에서 메시지를 읽어 적절한 receiver로 전달
        2. 모든 컴포넌트의 answer 큐를 확인하고 응답 처리
        3. type=None 컴포넌트(메인 스레드)의 메시지 처리
        """
        while self.running:
            # 1. 모든 컴포넌트의 real 큐 처리
            for name, queues in list(self.qdict.items()):
                if name not in self.stopped_components:  # 중지되지 않은 컴포넌트만 처리
                    self.process_real_queue(name, queues['real'])
            
            # 2. 모든 컴포넌트의 answer 큐 처리 (핵심 개선 부분)
            for name, queues in list(self.qdict.items()):
                if name not in self.stopped_components:  # 중지되지 않은 컴포넌트만 처리
                    self.process_answer_queue(name, queues['answer'])
            
            # 3. type=None인 컴포넌트(메인 스레드)의 메시지 처리
            for name, instance in list(self.admin_work.items()):
                if name not in self.stopped_components:  # 중지되지 않은 컴포넌트만 처리
                    self.process_component_messages(name, instance)
            
            time.sleep(0.001)
    
    def process_real_queue(self, sender_name, real_queue):
        """
        real 큐에서 메시지를 읽어 적절한 receiver로 전달
        """
        try:
            while not real_queue.empty():
                data = real_queue.get_nowait()
                if not isinstance(data, Order):
                    logging.debug(f'{sender_name}의 real 큐에 잘못된 데이터: {data}')
                    continue
                
                receiver = data.receiver
                # 중지된 컴포넌트로는 메시지 전달 안함
                if receiver in self.qdict and receiver not in self.stopped_components:
                    # 실시간 데이터는 receiver의 order 큐로 전달
                    self.qdict[receiver]['order'].put(data)
                else:
                    logging.debug(f"메시지 전달 불가: {receiver}가 존재하지 않거나 중지됨, 데이터 무시")
        except Empty:
            pass
        except Exception as e:
            logging.error(f"Real 큐 처리 중 오류: {e}", exc_info=True)
    
    def process_answer_queue(self, sender_name, answer_queue):
        """
        answer 큐에서 응답을 읽어 적절한 대상에게 전달 (새로 추가된 함수)
        """
        try:
            while not answer_queue.empty():
                data = answer_queue.get_nowait()
                if not isinstance(data, tuple) or len(data) != 2:
                    logging.debug(f'{sender_name}의 answer 큐에 잘못된 데이터: {data}')
                    continue
                
                qid, result = data
                # 결과를 저장하여 원래 요청자가 사용할 수 있도록 함
                self.result_dict.set(qid, result)
                
                # 1. 대기 중인 응답 정보가 있으면 처리
                pending_info = self.pending_answers.get(qid)
                if pending_info:
                    self.pending_answers.remove(qid)
                    sender, receiver, result_event, result_container = pending_info
                    result_container['value'] = result
                    result_event.set()
                    logging.debug(f"응답 처리 완료: {sender} -> {receiver}, qid={qid}")
                    continue
                
                # 2. 글로벌 응답 처리 (등록되지 않은 위치에서의 요청)
                global_info = self.global_responses.get(qid)
                if global_info:
                    self.global_responses.remove(qid)
                    result_event, result_container = global_info
                    result_container['value'] = result
                    result_event.set()
                    logging.debug(f"글로벌 응답 처리 완료: direct -> {sender_name}, qid={qid}")
        except Empty:
            pass
        except Exception as e:
            logging.error(f"Answer 큐 처리 중 오류: {e}", exc_info=True)
    
    def process_component_messages(self, name, instance):
        """
        메인 스레드에서 실행되는 컴포넌트의 큐 메시지 처리
        """
        if name in self.qdict and not self.qdict[name]['order'].empty():
            try:
                data = self.qdict[name]['order'].get_nowait()
                if not isinstance(data, (Order, Answer)):
                    logging.debug(f'{name} 에 잘못된 요청: {data}')
                    return
                
                # stop 명령이면 중지된 컴포넌트 목록에 추가
                if isinstance(data, Order) and data.order == 'stop':
                    self.stopped_components.add(name)
                
                method = getattr(instance, data.order)
                if isinstance(data, Order):
                    method(*data.args, **data.kwargs)
                else:  # Answer인 경우
                    result = method(*data.args, **data.kwargs)
                    
                    # 특수 sender 'direct'인 경우 글로벌 응답으로 처리
                    if data.sender == 'direct':
                        self.qdict[name]['answer'].put((data.qid, result))
                    # 등록된 컴포넌트로의 응답
                    elif data.sender in self.qdict and data.sender not in self.stopped_components:
                        self.qdict[data.sender]['answer'].put((data.qid, result))
                    else:
                        # 요청자가 없으면 결과를 저장
                        self.result_dict.set(data.qid, result)
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

        is_process = type == 'process'
        queue_type = mp.Queue if is_process else Queue
        
        # 컴포넌트별 큐 생성
        self.qdict[name] = {
            'order': queue_type(),
            'answer': queue_type(),
            'real': queue_type()
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
        if name in self.admin_work: 
            return False
            
        if name in self.qdict:
            try:
                # 먼저 중지된 컴포넌트로 표시
                self.stopped_components.add(name)
                
                # 이 컴포넌트를 대상으로 하는 모든 대기 중인 응답 처리 취소
                for qid, info in list(self.pending_answers._dict.items()):
                    sender, receiver, result_event, result_container = info
                    if receiver == name or sender == name:
                        self.pending_answers.remove(qid)
                        result_container['value'] = None
                        result_event.set()
                
                self.qdict[name]['order'].put(Order(receiver=name, order='stop'))
                time.sleep(0.1)  # 메시지 처리 확인 시간
                
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
            
        self.qdict[name]['order'].put(Order(receiver=name, order='start'))
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
        self.qdict[name]['order'].put(Order(receiver=name, order='stop'))
        return True

    def order(self, order_obj):
        """
        Order 객체를 통한 비동기 요청
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
            
        self.qdict[receiver]['order'].put(order_obj)
        return True

    def answer(self, answer_obj, timeout=10):
        """
        Answer 객체를 통한 동기식 요청/응답
        """
        if not isinstance(answer_obj, Answer):
            logging.error(f"answer_obj가 잘못된 타입입니다. {answer_obj}")
            return None
        
        sender = answer_obj.sender
        receiver = answer_obj.receiver
        
        if sender is None:
            logging.error(f"sender가 없습니다. {answer_obj}")
            return None
        
        if receiver not in self.qdict:
            logging.error(f"존재하지 않는 receiver입니다: {receiver}")
            return None
            
        # 중지된 컴포넌트로는 요청 안보냄
        if receiver in self.stopped_components:
            logging.debug(f"중지된 컴포넌트로 answer 요청 무시: {receiver}")
            return None
        
        # 응답을 저장할 공간과 이벤트 생성
        result_container = {'value': None}
        result_event = threading.Event()
        
        # 요청 전송 및 응답 대기
        qid = str(uuid.uuid4())
        answer_obj.qid = qid
        
        # 응답 추적 정보 저장
        self.pending_answers.set(qid, (sender, receiver, result_event, result_container))
        
        # 요청 전송
        self.qdict[receiver]['order'].put(answer_obj)
        
        # 결과 대기
        if result_event.wait(timeout):
            # 응답이 왔으면 pending_answers에서 제거 (이미 처리됐을 수도 있음)
            if self.pending_answers.get(qid):
                self.pending_answers.remove(qid)
            return result_container['value']
        else:
            # 타임아웃 시 추적 정보 제거
            self.pending_answers.remove(qid)
            logging.error(f"answer 요청 시간 초과: {sender} -> {receiver}: {answer_obj.order}")
            return None
            
    def direct_order(self, order_obj):
        """
        등록되지 않은 위치에서 사용할 수 있는 직접 호출 메서드
        비동기 요청만 가능 (응답 받지 않음)
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
            logging.debug(f"중지된 컴포넌트로 direct_order 요청 무시: {receiver}")
            return False
            
        self.qdict[receiver]['order'].put(order_obj)
        return True

    def direct_answer(self, answer_obj, timeout=10):
        """
        등록되지 않은 위치에서 사용할 수 있는 직접 응답 호출 메서드
        동기식 요청/응답, sender는 'direct'로 설정됨
        """
        if not isinstance(answer_obj, Answer):
            logging.error(f"answer_obj가 잘못된 타입입니다: {answer_obj}")
            return None
        
        receiver = answer_obj.receiver
        if receiver not in self.qdict:
            logging.error(f"존재하지 않는 receiver입니다: {receiver}")
            return None
            
        # 중지된 컴포넌트로는 요청 안보냄
        if receiver in self.stopped_components:
            logging.debug(f"중지된 컴포넌트로 direct_answer 요청 무시: {receiver}")
            return None
        
        # sender가 없으면 'direct'로 설정
        if not answer_obj.sender:
            answer_obj = copy.copy(answer_obj)
            answer_obj.sender = 'direct'
        
        # 고유 ID 생성
        qid = str(uuid.uuid4())
        answer_obj.qid = qid
        
        # 응답을 저장할 이벤트와 컨테이너 생성
        result_container = {'value': None}
        result_event = threading.Event()
        
        # 글로벌 응답 저장소에 이벤트와 컨테이너 등록
        self.global_responses.set(qid, (result_event, result_container))
        
        # 요청 전송
        self.qdict[receiver]['order'].put(answer_obj)
        
        # 결과 대기
        if result_event.wait(timeout):
            # 응답이 왔으면 global_responses에서 제거
            self.global_responses.remove(qid)
            return result_container['value']
        else:
            # 타임아웃 시 정보 제거
            self.global_responses.remove(qid)
            logging.error(f"direct_answer 요청 시간 초과: {answer_obj.sender} -> {receiver}: {answer_obj.order}")
            return None

    def cleanup(self):
        """
        모든 리소스 정리
        """
        logging.debug('IPCManager 리소스 정리 시작')
        self.running = False
        
        # 먼저 모든 대기 중인 요청 취소
        for name in list(self.qdict.keys()):
            # 모든 컴포넌트를 중지 상태로 표시
            self.stopped_components.add(name)
            self.stop(name)
        
        # 모든 대기 중인 응답에 None 반환하여 대기 상태 해제
        for qid, info in list(self.pending_answers._dict.items()):
            _, _, result_event, result_container = info
            result_container['value'] = None
            result_event.set()
            self.pending_answers.remove(qid)
        
        # 모든 대기 중인 글로벌 응답에 None 반환
        for qid, info in list(self.global_responses._dict.items()):
            result_event, result_container = info
            result_container['value'] = None
            result_event.set()
            self.global_responses.remove(qid)
        
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

# 이하 테스트 코드 *********************************************************
class GlobalSharedMemory:
    def __init__(self):
        # 여기에 일반 공유변수 추가 (메인 프로세스 내에서 공유)
        self.main = None
        self.admin = None
        self.api = None
        self.gui = None
        self.dbm = None
        self.전략01 = None
        self.전략02 = None
        self.ipc = None
gm = GlobalSharedMemory()

# 테스트 클래스들
class TestClass:
    def __init__(self, name, *args, **kwargs):
        self.name = name
    
    def run_method(self, data, *args, **kwargs):
        logging.info(f"{self.name} 이 호출됨, 데이터:{data}")
        return f"{self.name} 에서 반환: *{data}*"

    def call_other(self, target, func, *args, **kwargs):
        """
        다른 컴포넌트 호출
        프로세스 간 통신인 경우 proxy_order/proxy_answer 사용
        """
        logging.info(f"{self.name}에서 {target}.{func} 호출 시도")
        
        # 프로세스 간 통신이면 프록시 메서드 사용
        if hasattr(self, 'proxy_order') and isinstance(self, ModelProcess):
            logging.debug(f"프로세스 간 통신: {self.name} -> {target}")
            if kwargs.get('need_answer', False):
                return self.proxy_answer(target, func, *args, **{k: v for k, v in kwargs.items() if k != 'need_answer'})
            else:
                return self.proxy_order(target, func, *args, **{k: v for k, v in kwargs.items() if k != 'need_answer'})
        
        # 같은 프로세스 내 통신은 gm.ipc 사용
        order_obj = Order(receiver=target, order=func, args=args, kwargs=kwargs)
        result = gm.ipc.order(order_obj)
        logging.info(f"{self.name} 에서 {target} {func} 메서드 호출 결과: {result}")
        return result
    
    def call_async(self, data, *args, **kwargs):
        logging.info(f"{self.name} 에서 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        logging.info(f"{self.name} 에서 콜백 결과 수신: {data}")
        return f"{self.name} 에서 콜백 요청 데이타: {data}"

class TestThread(TestClass, ModelThread):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelThread.__init__(self, name, myq, daemon)

class TestProcess(TestClass, ModelProcess):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelProcess.__init__(self, name, myq, daemon)

class Strategy(TestThread):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        super().__init__(name, myq, daemon, *args, **kwargs)

    def stop(self):
        # 뒷정리
        ModelThread.stop(self)

class DBM(TestProcess):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        super().__init__(name, myq, daemon, *args, **kwargs)

    def stop(self):
        # 뒷정리
        ModelProcess.stop(self)

    def get_name(self, code):
        # API 호출은 gm.ipc를 통해서만 가능
        answer_obj = Answer(receiver='api', order='GetMasterCodeName', sender=self.name, args=(code,))
        name = gm.ipc.answer(answer_obj)
        logging.info(f"dbm: GetMasterCodeName 결과: {name}")
        return name

class API(TestProcess):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        super().__init__(name, myq, daemon, *args, **kwargs)
        self.connected = False
        self.send_real_data_running = False
        self.send_real_data_thread = None
        self.ocx = None

    def init(self):
        # QAxWidget 초기화 및 콜백 설정
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)

    def GetConnectState(self):
        if self.ocx:
            return self.ocx.dynamicCall("GetConnectState()")
        return 0

    def send_real_data_start(self):
        self.send_real_data_running = True
        self.send_real_data_thread = threading.Thread(target=self.send_real_data)
        self.send_real_data_thread.daemon = True
        self.send_real_data_thread.start()

    def send_real_data_stop(self):
        self.send_real_data_running = False
        if self.send_real_data_thread and self.send_real_data_thread.is_alive():
            self.send_real_data_thread.join(timeout=1.0)

    def send_real_data(self):
        # real 데이터는 자신의 real 큐로 전송, IPCManager가 이를 분배
        while self.send_real_data_running:
            # admin 컴포넌트로 실시간 데이터 전송
            self.myq['real'].put(Order(receiver='admin', order='real_data_receive', args=(f'real_data {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}',)))
            time.sleep(0.01)

    def stop(self):
        if hasattr(self, 'send_real_data_running') and self.send_real_data_running:
            self.send_real_data_stop()
        ModelProcess.stop(self)

    def is_connected(self):
        return self.connected

    def OnEventConnect(self, err_code):
        if err_code == 0:
            self.connected = True
            logging.info("로그인 성공")
        else:
            logging.error(f"로그인 실패: {err_code}")

    def login(self):
        if not self.ocx:
            logging.error("OCX가 초기화되지 않았습니다. init()을 먼저 호출하세요.")
            return False
        
        self.connected = False
        self.ocx.dynamicCall("CommConnect()")
        while not self.connected:
            pythoncom.PumpWaitingMessages()
        return True

    def GetMasterCodeName(self, code):
        if not self.ocx:
            logging.error("OCX가 초기화되지 않았습니다. init()을 먼저 호출하세요.")
            return ""
            
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
        logging.info(f"GetMasterCodeName 호출: {code} {data}")
        return data

class Admin(TestClass, Model):
    def __init__(self, name, myq=None, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        Model.__init__(self, name, myq)
        self.start_time = time.time()
        self.counter = 0
        self.testing_complete = False

    def real_data_receive(self, data):
        self.counter += 1
        if time.time() - self.start_time > 2:
            logging.info(f"Admin: 2초간 받은 real_data 횟수={self.counter} 마지막 데이터={data}")
            self.start_time = time.time()
            self.counter = 0
    
    def start_test(self):
        try:
            logging.info(' === 테스트 코드 === ')

            # 테스트용 쓰레드 및 프로세스 등록
            gm.전략01 = gm.ipc.register('전략01', Strategy, type='thread', start=True)
            gm.전략02 = gm.ipc.register('전략02', Strategy, type='thread', start=True)
            
            gm.ipc.order(Order(receiver='api', order='send_real_data_start'))

            logging.info('--- 메인 쓰레드에서 실행 ---')
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
            answer = Answer(receiver='dbm', order='call_other', sender='admin', args=('api', 'GetMasterCodeName', '005930'))
            result = gm.ipc.answer(answer)
            logging.info(f"dbm 에서 api 호출 결과: {result}")

            logging.info('--- 전략01 클래스 메소드 내에서 실행 ---')
            # 전략01에서 admin 호출
            answer = Answer(receiver='전략01', order='call_other', sender='admin', args=('admin', 'run_method', '전략01 에서 admin 호출'))
            result = gm.ipc.answer(answer)
            logging.info(f"전략01에서 admin 호출 결과: {result}")

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
            
            # 프로그램 종료 (모든 테스트 완료 후)
            time.sleep(1)
            os._exit(0)
        except Exception as e:
            logging.error(f"테스트 실행 중 오류 발생: {e}", exc_info=True)
            os._exit(1)

class Main:
    def __init__(self):
        self.init()

    def init(self):
        try:
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
            gm.ipc = IPCManager()
            gm.admin = gm.ipc.register('admin', Admin, start=True) # type=None이면 메인 쓰레드에서 실행 start=True이면 등록하고 바로 start() 실행

            # 프로세스는 별도 큐 사용
            gm.api = gm.ipc.register('api', API, type='process', start=True)
            gm.dbm = gm.ipc.register('dbm', DBM, type='process', start=True)

            # 초기화를 위한 대기
            time.sleep(1)

            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 종료')
            logging.info('--- 서버 접속 로그인 실행 ---')
            gm.ipc.direct_order(Order(receiver='api', order='init'))
            
            # 초기화 완료 확인을 위한 대기
            time.sleep(1)
            
            gm.ipc.direct_order(Order(receiver='api', order='login'))
            
            # 로그인 완료 확인
            con_result = 0
            while con_result == 0:  # 최대 3초 대기
                logging.info(f"API 로그인 완료 확인 대기 중: {con_result}")
                con_result = gm.ipc.direct_answer(Answer(receiver='api', order='GetConnectState', sender='admin'))
                if con_result == 1:
                    logging.info("API 로그인 완료")
                    break
                time.sleep(0.1)
            
            if con_result != 1:
                logging.error("API 로그인 실패 또는 시간 초과")
      
        except Exception as e:
            logging.error(str(e), exc_info=True)

    def run_admin(self):
        gm.ipc.order(Order(receiver='admin', order='start_test'))
        # 테스트가 완료될 때까지 대기
        for _ in range(300):  # 최대 30초 대기
            if hasattr(gm.admin, 'testing_complete') and gm.admin.testing_complete:
                break
            time.sleep(0.1)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    try:
        gm.main = Main()
        gm.main.run_admin()
    except Exception as e:
        logging.error(str(e), exc_info=True)

    finally:
        if hasattr(gm, 'ipc') and gm.ipc:
            gm.ipc.cleanup() # 모든 쓰레드와 프로세스 정리
        logging.shutdown()
        os._exit(0)