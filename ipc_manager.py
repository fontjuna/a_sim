from api_server import APIServer
from dbm_server import DBMServer
from admin import Admin
from public import dc, init_logger
from classes import ThreadSafeDict
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

@dataclass
class Order:
    receiver: str          # 응답자 이름
    order: str              # 응답자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

@dataclass
class Answer:
    receiver: str          # 응답자 이름
    order: str              # 응답자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    args: tuple = ()
    sender: str = None      # 요청자 이름
    kwargs: dict = field(default_factory=dict)
    qid: str = None        # 동기식 요청에 대한 답변 식별자
    
init_logger()

class Model():
    result_dict = ThreadSafeDict()
    def __init__(self, name, myq=None):
        super().__init__()
        self.name = name
        self.myq = myq
        self.is_running = True

    def set_all_queues(self, qdict):
        self.qdict = qdict

    def run(self):
        logging.debug(f'{self.name} 시작...')
        while self.is_running:
            self.run_loop()
            time.sleep(0.001)

    def run_loop(self):
        if not self.myq['order'].empty():
            data = self.myq['order'].get()

            if not isinstance(data, (Order, Answer)):
                logging.debug(f'{self.name} 에 잘못된 요청: {data}')
                return
            
            method = getattr(self, data.order)
            if isinstance(data, Order):
                method(*data.args, **data.kwargs)
            else:
                receiver = data.sender # 요청자 이름 추출
                for k, q in self.qdict.items():
                    if k == receiver:
                        result_q = q['answer']
                        break
                qid = data.qid
                result = method(*data.args, **data.kwargs)
                result_q.put((qid, result))

    def stop(self):
        self.is_running = False

    def put(self, receiver, order): # bus 대신 사용
        if not isinstance(order, Order):
            raise ValueError('Order 객체가 필요합니다.')

        receiver_q = self.qdict.get(receiver, None)
        if receiver_q == None:
            logging.debug(f"{self.name}: Target '{receiver}' not found in qdict")
            return
        receiver_q['order'].put(order)
        return True

    def get(self, sender, answer, timeout=10, check_interval=0.001):
        """
        대상에게 요청을 보내고 응답을 기다립니다.

        Args:
            sender: 요청자 이름
            answer: Answer 객체
            timeout: 응답 대기 시간(초)
            check_interval: 결과 확인 간격(초)

        Returns:
            응답 결과 또는 타임아웃시 None
        """
        # 요청자 큐 찾기
        sender_q = self.qdict[sender]

        if not sender_q:
            logging.debug(f"{self.name}: Target '{sender}' not found in qdict")
            return None

        # 응답 큐 선택
        if isinstance(answer, Answer):
            result_queue = sender_q['answer']
        else:
            logging.error(f"Answer 객체가 필요합니다. {answer}")
            return None

        # qid 생성
        qid = str(uuid.uuid4())
        answer.qid = qid
        answer.sender = self.name

        # 요청 전송
        #logging.debug(f"{self.name}: Sending {type(answer).__name__} to {target} (qid: {qid})")
        sender_q['order'].put(answer)

        # 응답 대기
        end_time = time.time() + timeout
        while time.time() < end_time:
            # 결과 딕셔너리 확인
            result = self.result_dict.get(qid)
            if result:
                self.result_dict.remove(qid)
                return result

            # 응답 큐 확인
            try:
                while not result_queue.empty():
                    result_qid, result_value = result_queue.get_nowait()
                    if result_qid == qid:
                        return result_value
                    else:
                        # 다른 요청의 결과 저장
                        self.result_dict.set(result_qid, result_value)
            except Empty:
                pass

            time.sleep(check_interval)

        #logging.debug(f"{self.name}: answer to {target} timed out after {timeout}s")
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

    def register(self, name, cls, *args, type=None, start=False, **kwargs):
        if name in self.qdict: self.unregister(name)

        is_process = type == 'process'
        self.qdict[name] = {
            'order': mp.Queue() if is_process else Queue(),
            'answer': mp.Queue() if is_process else Queue(),
            'real': mp.Queue() if is_process else Queue()
        }
        
        # 타입에 따라 적절한 모델 클래스 상속
        if type == 'thread':
            # class ThreadModel(ModelThread, cls):
            #     def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
            #         ModelThread.__init__(self, name, myq, daemon)
            #         cls.__init__(self, name, *args, **kwargs)
            
            # cls_instance = ThreadModel(name, self.qdict[name], True, *args, **kwargs)
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.thread_work[name] = cls_instance
        elif type == 'process':
            # class ProcessModel(ModelProcess, cls):
            #     def __init__(self, name, myq=None, daemon=True, *args, **kwargs):
            #         ModelProcess.__init__(self, name, myq, daemon)
            #         cls.__init__(self, name, *args, **kwargs)
            
            # cls_instance = ProcessModel(name, self.qdict[name], True, *args, **kwargs)
            cls_instance = cls(name, self.qdict[name], True, *args, **kwargs)
            self.process_work[name] = cls_instance
        else:  # type == None (main thread)
            cls_instance = cls(name, self.qdict[name], *args, **kwargs)
            self.admin_work[name] = cls_instance
        
        self.instances[name] = cls_instance
        
        if start and hasattr(cls_instance, 'start'):
            cls_instance.start()

        return cls_instance

    def unregister(self, name):
        if name in self.admin_work: return False
        if name in self.qdict:
            self.qdict[name]['order'].put(Order(receiver=name, order='stop'))
            if name in self.thread_work:
                self.thread_work[name].stop()
                time.sleep(0.1)
                self.thread_work.pop(name)
            elif name in self.process_work:
                self.process_work[name].stop()
                self.process_work[name].join()
                self.process_work.pop(name)
        else:
            logging.error(f"IPCManager에 없는 이름입니다. {name}")
            return False
        self.instances.pop(name)
        self.qdict.pop(name)
        for name in self.qdict.keys():
            self.qdict[name]['order'].put(Order(receiver=name, order='set_all_queues', args=(self.qdict,)))
        return True

    def start(self, name):
        self.qdict[name]['order'].put(Order(receiver=name, order='start'))
        for name in self.qdict.keys():
            self.qdict[name]['order'].put(Order(receiver=name, order='set_all_queues', args=(self.qdict,)))
        
    def stop(self, name):
        self.qdict[name]['order'].put(Order(receiver=name, order='stop'))

    def order(self, receiver, order, *args, **kwargs):
        self.qdict[receiver]['order'].put(Order(receiver=receiver, order=order, *args, **kwargs))

    def answer(self, receiver, order, *args, **kwargs):
        sender = kwargs.get('sender', None)
        if sender == None:
            logging.error(f"sender가 없습니다. {kwargs}")
            return
        result = self.instances[receiver].get(sender, Answer(receiver=receiver, order=order, *args, **kwargs))
        return result

    def cleanup(self):
        for name in self.thread_work:
            self.unregister(name)
        for name in self.process_work:
            self.unregister(name)

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
        result = self.qdict[target]['order'].put(Order(receiver=target, order=func, *args, **kwargs))
        logging.info(f"{self.name} 에서 {target} {func} 메서드 호출 결과: {result}")
        return result
    
    def call_async(self, data, *args, callback=None, **kwargs):
        logging.info(f"{self.name} 에서 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        logging.info(f"{self.name} 에서 콜백 결과 수신: {data}")
        return f"{self.name} 에서 콜백 요청 데이타: {data}"

class TestThread(TestClass, ModelThread):
    def __init__(self, name, myq=None, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelThread.__init__(self, name, myq, True)

class TestProcess(TestClass, ModelProcess):
    def __init__(self, name, myq=None, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        ModelProcess.__init__(self, name, myq, True)

class Strategy(TestThread):
    def __init__(self, name, myq=None, *args, **kwargs):
        super().__init__(name, myq, *args, **kwargs)

    def stop(self):
        # 뒷정리
        Model.stop(self)

class DBM(TestProcess):
    def __init__(self, name, myq=None, *args, **kwargs):
        super().__init__(name, myq, *args, **kwargs)

    def stop(self):
        # 뒷정리
        Model.stop(self)

    def get_name(self, code):
        name = self.answer('api', 'GetMasterCodeName', code)
        logging.info(f"dbm: GetMasterCodeName 결과: {name}")
        return name

class API(TestProcess):
    def __init__(self, name, myq=None, *args, **kwargs):
        super().__init__(name, myq, *args, **kwargs)
        self.connected = False
        self.send_real_data_running = False
        self.send_real_data_thread = threading.Thread(target=self.send_real_data)

    def init(self):
        app = QApplication(sys.argv)
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.stg3 = gm.ipc.register('stg3', Strategy, type='thread', start=True)

    def send_real_data_start(self):
        self.send_real_data_running = True
        self.send_real_data_thread.start()

    def send_real_data_stop(self):
        self.send_real_data_running = False
        self.send_real_data_thread.join()

    def send_real_data(self):
        while self.send_real_data_running:
            self.qdict['admin']['real'].put(Order(receiver='admin', order='real_data_receive', data=f'real_data {time.time()}'))
            time.sleep(0.01)

    def stop(self):
        Model.stop(self)

    def is_connected(self):
        return self.connected

    def OnEventConnect(self, err_code):
        if err_code == 0:
            logging.info("로그인 성공")
        else:
            logging.error(f"로그인 실패: {err_code}")

    def login(self):
        self.connected = False
        self.ocx.dynamicCall("CommConnect()")
        start_time = time.time()
        while not self.connected:
            pythoncom.PumpWaitingMessages()
            if time.time() - start_time > 20:
                logging.error("로그인 실패: 20초 초과")
                break

    def GetMasterCodeName(self, code):
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
        logging.info(f"GetMasterCodeName 호출: {code} {data}")
        return data

class Admin(TestClass, Model):
    def __init__(self, name, myq=None, *args, **kwargs):
        TestClass.__init__(self, name, *args, **kwargs)
        Model.__init__(self, name, myq)
        self.start_time = time.time()
        self.counter = 0

    def real_data_receive(self, data):
        self.counter += 1
        if time.time() - self.start_time > 2:
            logging.info(f"Admin: 2초간 받은 real_data 횟수={self.counter} 마지막 데이터={data}")
            self.start_time = time.time()
            self.counter = 0
    
    # Admin이 전체 프로그램을 관리하는 클래스
    def start_test(self):
        
        logging.info(' === 테스트 코드 === ')

        gm.전략01 = gm.ipc.register('전략01', Strategy, type='thread', start=True)
        gm.전략02 = gm.ipc.register('전략02', Strategy, type='thread', start=True)

        logging.info('--- 서버 접속 로그인 실행 ---')
        gm.ipc.order(Order(receiver='api', order='init'))
        gm.ipc.order(Order(receiver='api', order='login'))
        gm.ipc.order(Order(receiver='api', order='send_real_data_start'))

        logging.info('\n--- 메인 쓰레드에서 실행 ---')
        # 멀티 쓰레드 호출
        gm.ipc.order(Order(receiver='전략01', order='run_method', sender='admin', args=("admin 에서 order 호출",)))
        # 멀티 쓰레드 응답  
        answer = Answer(receiver='전략01', order='run_method', sender='admin', args=("admin 에서 answer 호출",))
        result = gm.ipc.answer(answer)
        logging.info(result)
        # 멀티 프로세스 api 호출
        answer = Answer(receiver='api', order='GetMasterCodeName', sender='admin', args=("005930",))
        result = gm.ipc.answer(answer)
        logging.info(result)
        # 멀티 프로세스 dbm 비동기 호출
        gm.ipc.order(Order(receiver='dbm', order='call_async', sender='admin', args=('async : admin 에서 dbm 호출',), callback=('dbm', 'receive_callback')))

        logging.info('\n--- 전략01 클래스 메소드 내에서 실행 ---')
        # 멀티 쓰레드 전략01에서 멀티 프로세스 api 호출
        answer = Answer(receiver='전략01', order='call_other', sender='admin', args=('api', 'GetMasterCodeName', '005930'))
        result = gm.ipc.answer('전략01', answer)
        logging.info(f"전략01: result = gm.ipc.answer('전략01', 'call_other', 'api', 'GetMasterCodeName', '005930') 결과: {result}")

        logging.info('\n--- 멀티 프로세스 api 클래스 매소드 내에서 실행 ---')
        # 멀티 프로세스 api에서 dbm 멀티프로세스 호출
        answer = Answer(receiver='api', order='call_other', sender='admin', args=('dbm', 'run_method', 'api 에서 dbm 호출'))
        result = gm.ipc.answer(answer)
        logging.info(f"api: result = gm.ipc.answer('api', 'call_other', 'dbm', 'run_method', 'api 에서 dbm 호출') 결과: {result}")

        time.sleep(3)
        logging.info(' === 테스트 코드 끝 === ')

class Main:
    def __init__(self):
        self.init()

    def init(self):
        try:
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
            gm.ipc = IPCManager()
            gm.admin = gm.ipc.register('admin', Admin, start=True) # type=None이면 메인 쓰레드에서 실행 start=True이면 등록하고 바로 start() 실행
            gm.api = gm.ipc.register('api', API, type='process', start=True) # type='process'이면 멀티 프로세스에서 실행 
            gm.dbm = gm.ipc.register('dbm', DBM, type='process', start=True) # type='process'이면 멀티 프로세스에서 실행 
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 종료')

        except Exception as e:
            logging.error(str(e), exc_info=e)

    def run_admin(self):
        gm.ipc.order('admin', 'start_test')

if __name__ == "__main__":
    import multiprocessing
    app = QApplication(sys.argv)
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    init_logger()
    try:
        gm.main = Main()
        gm.main.run_admin()

    except Exception as e:
        logging.error(str(e), exc_info=e)

    finally:
        gm.ipc.cleanup() # 
        logging.shutdown()