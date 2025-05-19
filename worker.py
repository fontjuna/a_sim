from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
import time
import logging
import sys
import pythoncom
import os
from ipc_manager import IPCManager

def init_logger(log_path='', filename='log_message'):
    import logging.config
    log_config = {
        'version': 1,
        'formatters': {
            'detailed': {
                'format': '%(asctime)s.%(msecs)03d-%(levelname)s-[%(filename)s(%(lineno)d) / %(funcName)s] %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'detailed'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': filename,
                'formatter': 'detailed',
                'maxBytes': 1024 * 1024 * 1,
                'backupCount': 9,
                'encoding': 'utf-8'
            }
        },
        'root': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG'
        }
    }
    full_path = os.path.abspath(log_path)
    
    message_file = os.path.join(full_path, filename)
    log_config['handlers']['file']['filename'] = message_file
    log_config['handlers']['file']['class'] = "logging.handlers.RotatingFileHandler"
    logging.config.dictConfig(log_config)

    # 문제 방지를 위한 핸들러 닫기 및 정리
    logger = logging.getLogger()
    for handler in logger.handlers:
        if hasattr(handler, "close"):
            handler.close()

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
        self.qdict = {}
    
    def run_method(self, data):
        logging.info(f"호출됨, 데이터:{data}")
        return f"처리 후 리턴: {data}"
    
    def call_other(self, target, func, *args, **kwargs):
        result = self.order(target, func, *args, **kwargs)
        logging.info(f"{self.name} 에서 {target} {func} 메서드 호출 결과: {result}")
        return result
    
    def call_async(self, data, callback=None):
        logging.info(f"{self.name} 에서 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        logging.info(f"{self.name} 에서 콜백 결과 수신: {data}")
        return f"{self.name} 에서 콜백 요청 데이타: {data}"

class Strategy(TestClass):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

    def stop(self):
        # 뒷정리
        pass

class DBM(TestClass):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

    def stop(self):
        # 뒷정리
        pass

    def get_name(self, code):
        name = self.answer('api', 'GetMasterCodeName', code)
        logging.info(f"dbm: GetMasterCodeName 결과: {name}")
        return name

class API(TestClass):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.connected = False

    def init(self):
        app = QApplication(sys.argv)
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.stg3 = gm.ipc.register('stg3', Strategy, type='thread', start=True)

    def stop(self):
        gm.ipc.stop('stg3')
        gm.ipc.unregister('stg3')

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

class Admin(TestClass):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

    # Admin이 전체 프로그램을 관리하는 클래스
    def start_test(self):
        
        logging.info(' === 테스트 코드 === ')

        gm.전략01 = gm.ipc.register('전략01', Strategy, type='thread', start=True)
        gm.전략02 = gm.ipc.register('전략02', Strategy, type='thread', start=True)

        logging.info('--- 서버 접속 로그인 실행 ---')
        gm.ipc.order('api', 'init')
        gm.ipc.order('api', 'login')

        logging.info('\n--- 메인 쓰레드에서 실행 ---')
        gm.ipc.order('전략01', 'run_method', "gm.ipc.order('전략01', 'run_method', 'work :test-1')")
        result = gm.ipc.answer('전략01', 'call_other', '전략02', 'run_method', 'answer : test-2')
        logging.info(f"전략01: result = gm.ipc.answer('전략01', 'call_other', '전략02', 'run_method', 'answer : test-2') 결과: {result}")
        result = gm.ipc.answer('전략01', 'call_other', 'api', 'run_method', 'answer : test-3')
        logging.info(f"전략01: result = gm.ipc.answer('전략01', 'call_other', 'api', 'run_method', 'answer : test-3') 결과: {result}")
        gm.ipc.order('전략01', 'call_async', 'async : test-4', callback=('전략01', 'receive_callback'))

        logging.info('\n--- 멀티 쓰레드 전략01 클래스 메소드 내에서 실행 ---')
        result = gm.ipc.answer('전략01', 'call_other', '전략02', 'run_method', 'answer : test-6')
        logging.info(f"전략01: result = gm.ipc.answer('전략01', 'call_other', '전략02', 'run_method', 'answer : test-6') 결과: {result}")
        result = gm.ipc.answer('전략01', 'call_other', 'api', 'GetMasterCodeName', '005930')
        logging.info(f"전략01: result = gm.ipc.answer('전략01', 'call_other', 'api', 'GetMasterCodeName', '005930') 결과: {result}")
        gm.ipc.stop('전략01')
        gm.ipc.stop('전략02')

        logging.info('\n--- 멀티 프로세스 api 클래스 매소드 내에서 실행 ---')
        result = gm.ipc.answer('dbm', 'get_name', '005930')
        logging.info(f"dbm: result = gm.ipc.answer('dbm', 'get_name', '005930') 결과: {result}")
        result = gm.ipc.answer('api', 'call_other', 'stg3', 'run_method', 'answer : test-9')
        logging.info(f"api: result = gm.ipc.answer('api', 'call_other', 'stg3', 'run_method', 'answer : test-9') 결과: {result}")
        result = gm.ipc.answer('api', 'call_other', 'dbm', 'run_method', 'answer : test-10')
        logging.info(f"api: result = gm.ipc.answer('api', 'call_other', 'dbm', 'run_method', 'answer : test-10') 결과: {result}")
        gm.ipc.order('api', 'call_async', 'async : test-11', callback=('api', 'receive_callback'))

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