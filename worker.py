# 수정된 worker.py
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
import time
import logging
import sys
import pythoncom
import os
from ipc_manager import IPCManager, init_ipc_manager, cleanup_ipc_manager

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
    # 이 곳에 shared_memory.SharedMemory로 공유 할 변수 선언(단순히 선언 위치로 변수 용도를 파악하기 위함)
    _shared_vars = {}
    
    def __init__(self):
        # 여기에 일반 공유변수 추가 (메인 프로세스 내에서 공유)
        self.main = None
        self.admin = None
        self.api = None
        self.gui = None
        self.dbm = None
        self.stg1 = None
        self.stg2 = None
        self.ipc = None

    def get_shm(self, var_name):
        return self._shared_vars[var_name]

    def set_shm(self, var_name, value):
        self._shared_vars[var_name] = value

gm = GlobalSharedMemory()

# 테스트 클래스들
class TestClass:
    def __init__(self, name="Admin"):
        self.name = name
        logging.info(f"{self.name} 초기화 완료")
    
    def get_shm(self, var_name):
        return gm.get_shm(var_name)

    def set_shm(self, var_name, value):
        gm.set_shm(var_name, value)

    def run_method(self, data):
        logging.info(f"{self.name}: 호출됨, 데이터:{data}")
        return f"{self.name}에서 처리 후 리턴: {data}"
    
    def call_other(self, target, data):
        logging.info(f"{self.name}: {target} 메서드 호출")
        return (target, data)
    
    def call_async(self, data, callback=None):
        logging.info(f"{self.name}: 비동기 receive_callback 호출 완료")
        self.receive_callback(data)
        return "비동기 호출 완료"
    
    def receive_callback(self, data):
        logging.info(f"{self.name}: 콜백 결과 수신: {data}")
        return f"{self.name}에서 처리 후 리턴: {data}"

class API(TestClass):
    app = QApplication(sys.argv)
    def __init__(self, name="api"):
        super().__init__(name)
        self.connected = False
        self.init()

    def init(self):
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)

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
            if time.time() - start_time > 10:
                logging.error("로그인 실패: 10초 초과")
                break

# IPCManager 클래스는 ipc_manager.py에서 가져옴

class Main:
    def __init__(self):
        self.init()

    def init(self):
        try:
            gm.ipc = IPCManager()
            gm.admin = gm.ipc.register('admin', TestClass('admin'), start=True) # type=None이면 메인 쓰레드에서 실행 start=True이면 등록하고 바로 start() 실행
            gm.api = gm.ipc.register('api', API('api'), type='process', start=True) # type='process'이면 멀티 프로세스에서 실행 
            gm.dbm = gm.ipc.register('dbm', TestClass('dbm'), type='process', start=False) # type='process'이면 멀티 프로세스에서 실행 
            gm.stg1 = gm.ipc.register('stg1', TestClass('stg1'), type='thread', start=True) # type='thread'이면 멀티 쓰레드에서 실행 admin 클래스 내에서 생성 했다고 가정함
            gm.stg2 = gm.ipc.register('stg2', TestClass('stg2'), type='thread', start=False) # type='thread'이면 멀티 쓰레드에서 실행 dbm 클래스 내에서 생성 했다고 가정함
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
        except Exception as e:
            logging.error(str(e), exc_info=e)

if __name__ == "__main__":
    import multiprocessing
    app = QApplication(sys.argv)
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    init_logger()
    try:
        # IPC 관리자 초기화
        init_ipc_manager()

        gm.main = Main()
        logging.info(' === 테스트 코드 === ')
        gm.ipc.start('dbm')
        gm.ipc.start('stg2') # 실제는 dbm 클래스 내에서 생성 하고 시작 함

        logging.info('--- 메인 쓰레드에서 실행 ---')
        # gm.admin.set_shm('test_var', '공유변수 저장 admin') # 메인 쓰레드이면 gm.ipc.set_shm('test_var', 'admin')로 바꾸고 기타 멀티 쓰레드나 프로세스면 self.set_shm('test_var', 'admin')로 바꾸어야 함.
        gm.ipc.set_shm('test_var', '공유변수 저장 admin')
        
        # gm.admin.call_other('api', 'test') # 이게 api 클래스의 메서드 호출이라면 gm.ipc.work('api', 'call_other', 'test')로 바꿔야 함.
        gm.ipc.work('api', 'call_other', 'api', 'test')
        
        # gm.admin.run_method('test') # 이게 dbm 클래스의 메서드 호출이라면 gm.ipc.work('dbm', 'run_method', 'test')로 바꿔야 함.
        gm.ipc.work('dbm', 'run_method', 'test')
        
        # result = gm.admin.run_method('test') # 이게 api 클래스의 메서드 호출이라면 gm.ipc.answer('api', 'run_method', 'test')로 바꿔야 함.
        result = gm.ipc.answer('api', 'run_method', 'test')
        
        # gm.admin.call_async('stg1', 'test') # 이게 stg1 클래스의 메서드 호출이라면 gm.ipc.work('stg1', 'call_async', 'test', callback=receive_callback)로 바꿔야 함.
        gm.ipc.work('stg1', 'call_async', 'test', callback=('admin', 'receive_callback'))

        logging.info('--- 멀티 쓰레드 stg1 클래스 메소드 내에서 실행 ---')
        # 다음 코드는 stg1 클래스 내부에서 실행되는 것으로 가정한 테스트 코드입니다.
        # logging.info(gm.stg1.get_shm('test_var')) # 멀티 쓰레드 stg1 에서 실행이므로 self.get_shm('test_var')로 바꾸어야 함.
        logging.info("stg1에서 실행 시: " + str(gm.ipc.get_shm('test_var')))
        
        # gm.stg1.call_other('api', 'test') # 이게 api 클래스의 메서드 호출이라면 self.ipc.work('api', 'call_other', 'test')로 바꿔야 함.
        gm.ipc.work('api', 'call_other', 'api', 'test')
        
        # gm.stg1.run_method('test') # 이게 dbm 클래스의 메서드 호출이라면 self.ipc.work('dbm', 'run_method', 'test')로 바꿔야 함.
        gm.ipc.work('dbm', 'run_method', 'test')
        gm.ipc.work('api', 'login')
        
        # result = gm.stg1.run_method('test') # 이게 api 클래스의 메서드 호출이라면 self.ipc.answer('api', 'run_method', 'test')로 바꿔야 함.
        result = gm.ipc.answer('api', 'run_method', 'test')
        
        # gm.stg1.call_async('stg2', 'test') # 이게 dbm클래스의 stg2 쓰레드 호출이라면 self.ipc.work('stg2', 'call_async', 'test', callback=receive_callback)로 바꿔야 함.
        gm.ipc.work('stg2', 'call_async', 'test', callback=('stg1', 'receive_callback'))
        
        # gm.stg1.set_shm('test_var', '공유변수 저장 stg1') # self.set_shm('test_var', 'stg1')로 바꾸어야 함.
        gm.ipc.set_shm('test_var', '공유변수 저장 stg1')

        logging.info('--- 멀티 프로세스 api 클래스 매소드 내에서 실행 ---')
        # 다음 코드는 api 클래스 내부에서 실행되는 것으로 가정한 테스트 코드입니다.
        # logging.info(gm.api.get_shm('test_var')) # 멀티 프로세스 api 에서 실행이므로 self.get_shm('test_var')로 바꾸어야 함.
        logging.info("api에서 실행 시: " + str(gm.ipc.get_shm('test_var')))
        
        # gm.api.run_method('test') # 이게 admin 클래스의 메서드 호출이라면 self.work('admin', 'run_method', 'test')로 바꿔야 함.
        gm.ipc.work('admin', 'run_method', 'test')
        
        # result = gm.api.run_method('test') # 이게 admin 클래스의 메서드 호출이라면 self.answer('admin', 'run_method', 'test')로 바꿔야 함.
        result = gm.ipc.answer('admin', 'run_method', 'test')
        
        # gm.api.call_other('stg2', 'test') # 이게 dbm클래스의 stg2 쓰레드 호출이라면 self.work('stg2', 'call_other', 'test')로 바꿔야 함.
        gm.ipc.work('stg2', 'call_other', 'api', 'test')
        
        # gm.api.call_async('dbm', 'test') # 이게 dbm 클래스의 메서드 호출이라면 self.work('dbm', 'call_async', 'test', callback=receive_callback)로 바꿔야 함.
        gm.ipc.work('dbm', 'call_async', 'test', callback=('api', 'receive_callback'))

        logging.info(' === 테스트 코드 끝 === ')

        gm.ipc.stop('stg2')
        gm.ipc.stop('dbm')
        gm.ipc.unregister('stg2')
        gm.ipc.unregister('dbm')

    except Exception as e:
        logging.error(str(e), exc_info=e)

    finally:
        cleanup_ipc_manager()
        gm.ipc.cleanup() # 
        logging.shutdown()