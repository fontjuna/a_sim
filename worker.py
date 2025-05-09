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
        result = self.ipc.answer("api", "fetch_data", [param])
        return f"Admin processed: {result}"
    
    def process_request(self, data):
        logging.info(f"AdminTest.process_request called with {data}")
        return f"Request processed: {data}"
    
    def notify(self, message):
        logging.info(f"AdminTest received notification: {message}")
        return "Notification received"

class APITest:
    def __init__(self):
        self.ipc = None
    
    def fetch_data(self, param):
        logging.info(f"APITest.fetch_data called with {param}")
        # DBM 서버 함수 호출 테스트
        result = self.ipc.answer("dbm", "get_data", [param])
        return f"API fetched: {param}, DB had: {result}"
    
    # worker.py (계속)
    def send_notification(self, message):
        logging.info(f"APITest.send_notification: {message}")
        # Admin에 알림 전송 테스트
        self.ipc.work("admin", "notify", [f"API notification: {message}"])
        return "Notification sent"

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
        result = self.ipc.answer("api", "send_notification", [f"New data stored: {key}"])
        return f"Stored as {key}, notification: {result}"
    
    def request_admin_action(self, action):
        logging.info(f"DBMTest.request_admin_action: {action}")
        # Admin에 액션 요청 테스트
        result = self.ipc.answer("admin", "process_request", [action])
        return f"Admin result: {result}"

# 워커 초기화 함수
def initialize_worker(name, worker_type, shared_registry, shared_queues):
    """각 프로세스에서 호출되는 초기화 함수
    
    Args:
        name: 워커 이름 (api, dbm 등)
        worker_type: 워커 클래스 유형 (문자열: 'api', 'dbm' 등)
        shared_registry: 공유 레지스트리
        shared_queues: 공유 큐 딕셔너리
    """
    # 로깅 설정
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    pid = multiprocessing.current_process().pid
    logging.debug(f"Process {pid}: Initializing worker for {name}")
    
    # IPCManager 가져오기
    from ipc_manager import IPCManager
    
    # IPCManager 인스턴스 생성 (공유 자원 전달)
    ipc = IPCManager.get_instance(shared_registry, shared_queues)
    
    # worker_type에 따라 올바른 클래스 인스턴스 생성
    if worker_type == 'api':
        obj = APITest()
    elif worker_type == 'dbm':
        obj = DBMTest()
    elif worker_type == 'admin':
        obj = AdminTest()
    else:
        raise ValueError(f"Unknown worker type: {worker_type}")
    
    # 객체에 ipc 속성 설정
    obj.ipc = ipc
    
    # 등록
    ipc.register(name, obj, 'process')
    
    # 워커 시작
    ipc.start(name)
    
    # 메인 루프 (종료 신호 대기)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.debug(f"Process {pid}: Worker for {name} terminated by keyboard interrupt")
        ipc.cleanup()

