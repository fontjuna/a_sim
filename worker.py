# worker.py
import logging
import multiprocessing
import time
import sys
import os

# 테스트 클래스 정의
class AdminTest:
    def __init__(self):
        self.ipc = None
    
    def test_function(self, param):
        logging.info(f"AdminTest.test_function called with {param}")
        # API 서버 함수 호출 테스트
        result = self.ipc.answer("api", "fetch_data", param)
        return f"Admin processed: {result}"
    
    def process_request(self, data):
        logging.info(f"AdminTest.process_request called with {data}")
        return f"Request processed: {data}"
    
    def notify(self, message):
        logging.info(f"AdminTest received notification: {message}")
        return "Notification received"
    
    def test_kiwoom_login(self):
        logging.info("AdminTest.test_kiwoom_login: 키움증권 로그인 테스트 시작")
        result = self.ipc.answer("api", "kiwoom_login")
        return f"키움증권 로그인 결과: {result}"

class APITest:
    def __init__(self):
        self.ipc = None
        self.kiwoom = None
        self.is_connected = False
        self.account_number = None
    
    def initialize_kiwoom(self):
        """키움증권 API 초기화"""
        try:
            logging.info("키움증권 API 초기화 시작")
            
            # PyQt5 모듈 임포트 시도
            try:
                from PyQt5.QtWidgets import QApplication
                from PyQt5.QAxContainer import QAxWidget
            except ImportError:
                logging.error("PyQt5 모듈을 찾을 수 없습니다. 'pip install pyqt5 pyqt5-tools' 명령으로 설치하세요.")
                return False
            
            # QApplication 인스턴스 생성
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()
            
            # QAxWidget 인스턴스 생성
            self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            
            # 이벤트 연결
            self.kiwoom.OnEventConnect.connect(self._on_event_connect)
            
            logging.info("키움증권 API 초기화 완료")
            return True
        
        except Exception as e:
            logging.error(f"키움증권 API 초기화 실패: {str(e)}")
            return False
    
    def _on_event_connect(self, err_code):
        """로그인 이벤트 처리"""
        if err_code == 0:
            self.is_connected = True
            # 계좌 정보 가져오기
            self.account_number = self.kiwoom.dynamicCall("GetLoginInfo(QString)", ["ACCNO"]).split(';')[0]
            logging.info(f"키움증권 로그인 성공. 계좌번호: {self.account_number}")
        else:
            self.is_connected = False
            logging.error(f"키움증권 로그인 실패. 에러 코드: {err_code}")
    
    def kiwoom_login(self):
        """키움증권 로그인"""
        try:
            # API가 초기화되지 않았으면 초기화
            if self.kiwoom is None:
                if not self.initialize_kiwoom():
                    return "키움증권 API 초기화 실패"
            
            # 로그인 요청
            logging.info("키움증권 로그인 시도")
            self.kiwoom.dynamicCall("CommConnect()")
            
            # 로그인 완료 대기 (최대 10초)
            timeout = 10
            start_time = time.time()
            while not self.is_connected and time.time() - start_time < timeout:
                self.app.processEvents()  # GUI 이벤트 처리
                time.sleep(0.1)
            
            if self.is_connected:
                return f"로그인 성공. 계좌번호: {self.account_number}"
            else:
                return "로그인 실패 또는 타임아웃"
                
        except Exception as e:
            logging.error(f"키움증권 로그인 중 오류 발생: {str(e)}")
            return f"로그인 오류: {str(e)}"
    
    def fetch_data(self, param):
        logging.info(f"APITest.fetch_data called with {param}")
        # DBM 서버 함수 호출 테스트
        result = self.ipc.answer("dbm", "get_data", param)
        return f"API fetched: {param}, DB had: {result}"
    
    # worker.py (계속)
    def send_notification(self, message):
        logging.info(f"APITest.send_notification: {message}")
        # Admin에 알림 전송 테스트
        self.ipc.work("admin", "notify", f"API notification: {message}")
        return "Notification sent"
    
    def get_kiwoom_status(self):
        """키움증권 연결 상태 확인"""
        if self.kiwoom is None:
            return "키움증권 API 초기화되지 않음"
        
        if self.is_connected:
            return f"키움증권 연결됨. 계좌번호: {self.account_number}"
        else:
            return "키움증권 연결되지 않음"
        
    def test_shared_thread_access(self, message):
        """공유 스레드 접근 테스트"""
        try:
            logging.info(f"APITest.test_shared_thread_access: 공유 스레드 접근 시도")
            result = self.ipc.answer("shared_thread", "echo", message)
            return f"API -> 공유 스레드 접근 성공: {result}"
        except Exception as e:
            logging.error(f"공유 스레드 접근 실패: {str(e)}")
            return f"API -> 공유 스레드 접근 실패: {str(e)}"
        
class DBMTest:
    def __init__(self):
        self.ipc = None
        self.db = {}
    
    def get_data(self, key):
        logging.info(f"DBMTest.get_data called with {key}")
        return self.db.get(key, "no data")
    
    def store_data(self, data):
        logging.info(f"DBMTest.store_data called with {data}")
        key = f"key_{len(self.db)}"
        self.db[key] = data
        # API에 알림 테스트
        result = self.ipc.answer("api", "send_notification", f"New data stored: {key}")
        return f"Stored as {key}, notification: {result}"
    
    def request_admin_action(self, action):
        logging.info(f"DBMTest.request_admin_action: {action}")
        # Admin에 액션 요청 테스트
        result = self.ipc.answer("admin", "process_request", action)
        return f"Admin result: {result}"


    # DBMTest 클래스에 스레드 생성 및 테스트 메서드 추가
    def create_internal_thread(self):
        """내부 스레드 생성 및 등록"""
        try:
            self.thread_worker = DBMThreadTest(self.ipc)
            # 로컬 등록 (DBM 프로세스 내부 IPC에 등록)
            self.internal_thread = self.ipc.register("dbm_internal_thread", self.thread_worker, 'thread', start=True)
            return "DBM 내부 스레드 생성 성공"
        except Exception as e:
            logging.error(f"DBM 내부 스레드 생성 오류: {e}")
            return f"오류: {str(e)}"

    def test_thread_to_admin(self, message):
        """내부 스레드에서 Admin 접근 테스트"""
        try:
            return self.ipc.answer("dbm_internal_thread", "connect_to_admin", message)
        except Exception as e:
            logging.error(f"스레드->Admin 테스트 오류: {e}")
            return f"오류: {str(e)}"

    def test_thread_to_api(self, message):
        """내부 스레드에서 API 접근 테스트"""
        try:
            return self.ipc.answer("dbm_internal_thread", "connect_to_api", message)
        except Exception as e:
            logging.error(f"스레드->API 테스트 오류: {e}")
            return f"오류: {str(e)}"
    
    
class DBMThreadTest:
    """DBM 내부에서 생성되는 테스트 스레드"""
    def __init__(self, parent_ipc=None):
        self.ipc = parent_ipc  # 부모 프로세스의 IPC 인스턴스 공유
        self.name = "dbm_thread"
    
    def connect_to_admin(self, message):
        """Admin 프로세스에 접근 테스트"""
        try:
            logging.info(f"DBMThreadTest.connect_to_admin: {message}")
            result = self.ipc.answer("admin", "process_request", f"From DBM Thread: {message}")
            return f"Admin 응답: {result}"
        except Exception as e:
            logging.error(f"Admin 접근 오류: {e}")
            return f"오류: {str(e)}"
    
    def connect_to_api(self, message):
        """API 프로세스에 접근 테스트"""
        try:
            logging.info(f"DBMThreadTest.connect_to_api: {message}")
            result = self.ipc.answer("api", "send_notification", f"From DBM Thread: {message}")
            return f"API 응답: {result}"
        except Exception as e:
            logging.error(f"API 접근 오류: {e}")
            return f"오류: {str(e)}"

    
class SharedThreadWorker:
    """프로세스 간 공유되는 스레드 워커"""
    def __init__(self):
        self.ipc = None
        self.data = {}
        self.counter = 0
    
    def set_data(self, key, value):
        """데이터 설정"""
        logging.info(f"SharedThreadWorker.set_data: {key}={value}")
        self.data[key] = value
        self.counter += 1
        return True
    
    def get_data(self, key=None):
        """데이터 가져오기"""
        if key is None:
            logging.info(f"SharedThreadWorker.get_data: 전체 데이터 요청, counter={self.counter}")
            return {'data': self.data, 'counter': self.counter}
        logging.info(f"SharedThreadWorker.get_data: {key} 요청")
        return self.data.get(key, None)
    
    def echo(self, message):
        """메시지 에코"""
        logging.info(f"SharedThreadWorker.echo: {message}")
        return f"Echo from SharedThreadWorker: {message}"

class LocalThreadWorker:
    """프로세스 내부에서만 접근 가능한 스레드 워커"""
    def __init__(self):
        self.ipc = None
        self.data = {}
        self.counter = 0
    
    def set_data(self, key, value):
        """데이터 설정"""
        logging.info(f"LocalThreadWorker.set_data: {key}={value}")
        self.data[key] = value
        self.counter += 1
        return True
    
    def get_data(self, key=None):
        """데이터 가져오기"""
        if key is None:
            logging.info(f"LocalThreadWorker.get_data: 전체 데이터 요청, counter={self.counter}")
            return {'data': self.data, 'counter': self.counter}
        logging.info(f"LocalThreadWorker.get_data: {key} 요청")
        return self.data.get(key, None)
    
    def echo(self, message):
        """메시지 에코"""
        logging.info(f"LocalThreadWorker.echo: {message}")
        return f"Echo from LocalThreadWorker: {message}"

# DBMTest 클래스에 스레드 연동 메서드 추가
def call_thread(self, thread_name, method, *args, **kwargs):
    """스레드 메서드 호출"""
    logging.info(f"DBMTest.call_thread: {thread_name}.{method} 호출")
    return self.ipc.answer(thread_name, method, *args, **kwargs)