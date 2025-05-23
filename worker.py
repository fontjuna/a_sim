
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
def init_logger():
    logging.basicConfig(
        level=logging.DEBUG,  # DEBUG 레벨로 설정
        format='%(asctime)s.%(msecs)03d-%(levelname)s-[%(filename)s(%(lineno)d) / %(funcName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

# 초기화
init_logger()
app = QApplication(sys.argv)

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
    
    def clear(self):
        with self._lock:
            self._dict.clear()
    
    def keys(self):
        with self._lock:
            return list(self._dict.keys())

@dataclass
class Order:
    receiver: str
    order: str
    sender: str = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    qid: str = None

@dataclass
class Answer:
    receiver: str
    order: str
    sender: str = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    qid: str = None
    result: any = None

class IPCManager:
    def __init__(self):
        self.qdict = {}
        self.admin_work = {}
        self.thread_work = {}
        self.process_work = {}
        self.instances = {}
        self.stoped_cls = set()
        self.shut_down = False
        
        self.running = True
        self.router_thread = threading.Thread(target=self.message_router, daemon=True)
        self.router_thread.start()
    
    def message_router(self):
        while self.running:
            for name, queues in list(self.qdict.items()):
                if name not in self.stoped_cls:
                    try:
                        while not queues['output_q'].empty():
                            msg = queues['output_q'].get_nowait()
                            target = msg.receiver
                            
                            if target in self.qdict and target not in self.stoped_cls:
                                self.qdict[target]['input_q'].put(msg)
                    except Exception as e:
                        logging.error(f"메시지 라우팅 오류: {e}")
            time.sleep(0.001)
    
    def register(self, name, cls, type=None, start=False, *args, **kwargs):
        if name in self.qdict:
            self.unregister(name)
        
        is_process = type == 'process'
        queue_type = mp.Queue if is_process else Queue
        
        self.qdict[name] = {
            'input_q': queue_type(),
            'output_q': queue_type()
        }
        
        if type == 'thread':
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.thread_work[name] = cls_instance
        elif type == 'process':
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.process_work[name] = cls_instance
        else:
            cls_instance = cls(name, self.qdict[name], *args, **kwargs)
            self.admin_work[name] = cls_instance
            threading.Thread(target=cls_instance.run, daemon=True).start()
        
        self.instances[name] = cls_instance
        
        if start and type is not None:
            self.start(name)
        
        return cls_instance
    
    def start(self, name):
        if name not in self.qdict:
            return False
        if name in self.admin_work:
            return True
        self.instances[name].start()
        self.stoped_cls.discard(name)
        return True
    
    def stop(self, name):
        if name not in self.qdict:
            return False
        if name in self.admin_work:
            return True
        self.instances[name].stop()
        self.stoped_cls.add(name)
        return True
    
    def unregister(self, name):
        if name in self.admin_work:
            return False
        
        if name in self.qdict:
            try:
                if name in self.thread_work:
                    self.thread_work[name].stop()
                    self.thread_work.pop(name)
                elif name in self.process_work:
                    self.process_work[name].stop()
                    self.process_work[name].join(timeout=1.0)
                    self.process_work.pop(name)
                
                while not self.qdict[name]['input_q'].empty():
                    self.qdict[name]['input_q'].get_nowait()
                while not self.qdict[name]['output_q'].empty():
                    self.qdict[name]['output_q'].get_nowait()
                    
            except Exception as e:
                logging.error(f"{name} 컴포넌트 제거 중 오류: {e}")
        
        if name in self.instances:
            self.instances.pop(name)
        if name in self.qdict:
            self.qdict.pop(name)
        
        return True
    
    def cleanup(self):
        self.shut_down = True
        self.running = False
        
        for name in list(self.thread_work.keys()):
            self.unregister(name)
        for name in list(self.process_work.keys()):
            self.unregister(name)
        for name in list(self.admin_work.keys()):
            if hasattr(self.admin_work[name], 'stop'):
                self.admin_work[name].stop()

class Model:
    def __init__(self, name, myq=None):
        self.name = name
        self.myq = myq
        self.is_running = True
        self.pending_calls = {}
    
    def run(self):
        logging.debug(f'{self.name} 시작...')
        self.is_running = True
        while self.is_running:
            self.run_loop()
            time.sleep(0.001)
    
    def run_loop(self):
        if not self.myq['input_q'].empty():
            try:
                msg = self.myq['input_q'].get_nowait()
                
                if isinstance(msg, Order):
                    self.handle_order(msg)
                elif isinstance(msg, Answer):
                    if msg.qid and msg.qid in self.pending_calls:
                        self.pending_calls[msg.qid] = msg.result
                    else:
                        self.handle_answer_request(msg)
            except Exception as e:
                logging.error(f"{self.name} 메시지 처리 중 오류: {e}")
    
    def handle_order(self, order_msg):
        try:
            method = getattr(self, order_msg.order)
            method(*order_msg.args, **order_msg.kwargs)
        except Exception as e:
            logging.error(f"{self.name}.{order_msg.order} 실행 중 오류: {e}")
    
    def handle_answer_request(self, answer_msg):
        try:
            method = getattr(self, answer_msg.order)
            result = method(*answer_msg.args, **answer_msg.kwargs)
            
            response = Answer(
                receiver=answer_msg.sender,
                order=answer_msg.order,
                sender=self.name,
                qid=answer_msg.qid,
                result=result
            )
            self.myq['output_q'].put(response)
            
        except Exception as e:
            logging.error(f"{self.name}.{answer_msg.order} 실행 중 오류: {e}")
            response = Answer(
                receiver=answer_msg.sender,
                qid=answer_msg.qid,
                result=None
            )
            self.myq['output_q'].put(response)
    
    def call(self, target, func, *args, **kwargs):
        qid = str(uuid.uuid4())
        answer_obj = Answer(
            receiver=target,
            order=func,
            sender=self.name,
            args=args,
            kwargs=kwargs,
            qid=qid
        )
        
        self.pending_calls[qid] = None
        self.myq['output_q'].put(answer_obj)
        
        start_time = time.time()
        while time.time() - start_time < 10:
            if qid in self.pending_calls and self.pending_calls[qid] is not None:
                result = self.pending_calls[qid]
                del self.pending_calls[qid]
                return result
            time.sleep(0.001)
        
        if qid in self.pending_calls:
            del self.pending_calls[qid]
        return None
    
    def send(self, target, func, *args, **kwargs):
        order_obj = Order(
            receiver=target,
            order=func,
            sender=self.name,
            args=args,
            kwargs=kwargs
        )
        self.myq['output_q'].put(order_obj)
        return True
    
    def on_real_data(self, data):
        logging.info(f"{self.name} 실시간 데이터 수신: {data}")
    
    def stop(self):
        self.is_running = False

class ModelThread(Model, QThread):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        Model.__init__(self, name, myq)
        QThread.__init__(self)
        self.daemon = daemon
    
    def run(self):
        Model.run(self)
    
    def stop(self):
        Model.stop(self)
        logging.debug(f'{self.name} 쓰레드 종료...')
    
    def start(self):
        QThread.start(self)
        return self

class ModelProcess(Model, mp.Process):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
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

class TestClass:
    def __init__(self, name, myq=None):
        self.name = name
        self.myq = myq
    
    def run_method(self, data, *args, **kwargs):
        logging.info(f"{self.name} 이 호출됨, 데이터:{data}")
        return f"{self.name} 에서 반환: *{data}*"
    
    def call_async(self, data, *args, **kwargs):
        logging.info(f"{self.name} 에서 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        logging.info(f"{self.name} 에서 콜백 결과 수신: {data}")
        return f"{self.name} 에서 콜백 요청 데이타: {data}"

class TestThread(TestClass, ModelThread):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, myq)
        ModelThread.__init__(self, name, myq, daemon)

class TestProcess(TestClass, ModelProcess):
    def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
        TestClass.__init__(self, name, myq)
        ModelProcess.__init__(self, name, myq, daemon)

class Strategy(TestThread):
    def __init__(self, name, myq=None, daemon=True):
        super().__init__(name, myq, daemon)
    
    def stop(self):
        ModelThread.stop(self)

class DBM(TestProcess):
    def __init__(self, name, myq=None, daemon=True):
        super().__init__(name, myq, daemon)
    
    def stop(self):
        ModelProcess.stop(self)
    
    def get_name(self, code):
        """새로운 방식으로 API 호출"""
        result = self.call('api', 'GetMasterCodeName', code)
        logging.info(f"dbm: GetMasterCodeName 결과: {result}")
        return result

class API(TestProcess):
    def __init__(self, name, myq=None, daemon=True):
        super().__init__(name, myq, daemon)
        self.connected = False
        self.send_real_data_running = False
        self.send_real_data_thread = None
        self.ocx = None
    
    def send_real_data(self):
        while self.send_real_data_running:
            data = f'real_data {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}'
            self.send('admin', 'on_real_data', data)
            time.sleep(0.01)
    
    def send_real_data_start(self):
        self.send_real_data_running = True
        self.send_real_data_thread = threading.Thread(target=self.send_real_data, daemon=True)
        self.send_real_data_thread.start()
    
    def send_real_data_stop(self):
        self.send_real_data_running = False
        if self.send_real_data_thread and self.send_real_data_thread.is_alive():
            self.send_real_data_thread.join(timeout=1.0)
    
    def init(self):
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
    
    def GetConnectState(self):
        if self.ocx:
            return self.ocx.dynamicCall("GetConnectState()")
        return 0
    
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
            logging.error("OCX가 초기화되지 않았습니다.")
            return False
        
        self.connected = False
        self.ocx.dynamicCall("CommConnect()")
        while not self.connected:
            pythoncom.PumpWaitingMessages()
        return True
    
    def GetMasterCodeName(self, code):
        if not self.ocx:
            logging.error("OCX가 초기화되지 않았습니다.")
            return ""
        
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
        logging.info(f"GetMasterCodeName 호출: {code} {data}")
        return data
    
    def stop(self):
        if hasattr(self, 'send_real_data_running') and self.send_real_data_running:
            self.send_real_data_stop()
        ModelProcess.stop(self)

class Admin(TestClass, Model):
    def __init__(self, name, myq=None):
        TestClass.__init__(self, name, myq)
        Model.__init__(self, name, myq)
        self.start_time = time.time()
        self.counter = 0
        self.testing_complete = False
    
    def on_real_data(self, data):
        self.counter += 1
        if time.time() - self.start_time > 2:
            logging.info(f"Admin: 2초간 받은 real_data 횟수={self.counter} 마지막 데이터={data}")
            self.start_time = time.time()
            self.counter = 0
    
    def start_test(self):
        try:
            logging.info(' === 테스트 코드 === ')
            
            gm.전략01 = gm.ipc.register('전략01', Strategy, type='thread', start=True)
            gm.전략02 = gm.ipc.register('전략02', Strategy, type='thread', start=True)
            
            self.send('api', 'send_real_data_start')
            
            logging.info('--- 메인 쓰레드에서 실행 ---')
            self.send('전략01', 'run_method', "admin 에서 order 호출")
            
            result = self.call('전략01', 'run_method', "admin 에서 answer 호출")
            logging.info(f"전략01 응답 결과: {result}")
            
            result = self.call('api', 'GetMasterCodeName', "005930")
            logging.info(f"API 호출 결과: {result}")
            
            self.send('dbm', 'call_async', 'async : admin 에서 dbm 호출')
            
            result = self.call('dbm', 'get_name', '005930')
            logging.info(f"dbm 에서 api 호출 결과: {result}")
            
            logging.info('--- 전략01 클래스 메소드 내에서 실행 ---')
            result = self.call('전략01', 'call', 'admin', 'run_method', '전략01 에서 admin 호출')
            logging.info(f"전략01에서 admin 호출 결과: {result}")
            
            logging.info('--- 실시간 데이터 처리 테스트 ---')
            time.sleep(3)
            
            logging.info('--- 테스트 정리 ---')
            self.send('api', 'send_real_data_stop')
            time.sleep(1)
            
            logging.info(' === 테스트 코드 끝 === ')
            self.testing_complete = True
            
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
            gm.admin = gm.ipc.register('admin', Admin, start=True)
            
            # 프로세스는 별도 큐 사용
            gm.api = gm.ipc.register('api', API, type='process', start=True)
            gm.dbm = gm.ipc.register('dbm', DBM, type='process', start=True)
            
            # 초기화를 위한 대기
            time.sleep(1)
            
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 종료')
            logging.info('--- 서버 접속 로그인 실행 ---')
            gm.ipc.instances['api'].send('api', 'init')
            
            time.sleep(1)
            gm.ipc.instances['api'].send('api', 'login')
            
            # 로그인 완료 확인
            con_result = 0
            retry_count = 0
            while con_result == 0 and retry_count < 30:
                logging.info(f"API 로그인 완료 확인 대기 중: {con_result}")
                con_result = gm.ipc.instances['admin'].call('api', 'GetConnectState')
                if con_result == 1:
                    logging.info("API 로그인 완료")
                    break
                time.sleep(0.1)
                retry_count += 1
            
            if con_result != 1:
                logging.error("API 로그인 실패 또는 시간 초과")
                
        except Exception as e:
            logging.error(str(e), exc_info=True)
    
    def run_admin(self):
        gm.ipc.instances['admin'].send('admin', 'start_test')
        
        # 테스트가 완료될 때까지 대기
        for _ in range(300):  # 최대 30초 대기
            if hasattr(gm.admin, 'testing_complete') and gm.admin.testing_complete:
                break
            time.sleep(0.1)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    try:
        gm.main = Main()
        gm.main.run_admin()
    except Exception as e:
        logging.error(str(e), exc_info=True)
    finally:
        if hasattr(gm, 'ipc') and gm.ipc:
            gm.ipc.cleanup()
        logging.shutdown()
        os._exit(0)



