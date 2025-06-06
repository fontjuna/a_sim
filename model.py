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

        

WAIT_TIMEOUT = 15
POLLING_TIMEOUT = 0.001  # 1ms 고빈도 처리

class CommManager:
    def __init__(self, cls_name, cls, cls_type, *args, **kwargs):
        self.cls_name = cls_name
        self.cls = cls
        self.cls_type = cls_type
        self.args = args
        self.kwargs = kwargs
        self.cls_instance = self.cls(*self.args, **self.kwargs)

    def order(self, method_name, *args, **kwargs):
        # method_name 메서드 호출
        self.cls_instance.method_name(*args, **kwargs)

    def answer(self, method_name, *args, **kwargs):
        # method_name 메서드 호출하여 결과 반환
        return self.cls_instance.method_name(*args, **kwargs)

    def frq_order(self, target, method_name, *args, **kwargs):
        # target 컴퍼넌트의 method_name 메서드로 고빈도 데이터 전송
        pass

    def frq_answer(self, method_name, *args, **kwargs):
        # 고빈도 요청시 이 호출 사용 method_name 메서드 호출하여 결과 반환
        return self.cls_instance.method_name(*args, **kwargs)    

    def start(self):
        # 컴퍼넌트 실행
        pass

    def stop(self):
        # 컴퍼넌트 중지 
        pass

    def shutdown(self):
        # 컴퍼넌트 정리 후 삭제
        pass

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
        pass

class Strategy:
    def __init__(self):
        self.name = 'stg'
        pass

class Api:
    def __init__(self):
        self.name = 'api'
        self.app = None
        self.kiwoom = None


        init_logger()

    def initialize(self):
        logging.info(f"[{self.name}] 프로세스 내 키움 API 초기화 시작")
        self.app = QApplication(sys.argv)
        self.set_component()
        self.set_signal_slot()
        
    def set_component(self):
        try:
            pythoncom.CoInitialize()
            self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            logging.info(f"[{self.name}] QAxWidget 객체 생성 완료")

        except Exception as e:
            logging.error(f"[{self.name}] 초기화 오류: {e}")

    def set_signal_slot(self):
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)

    def login(self):
        logging.info(f"[{self.name}] 로그인 시도 시작")
        self.kiwoom.dynamicCall("CommConnect()")
        start_time = time.time()
        while not gm.api_connected:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.1)
            if time.time() - start_time > WAIT_TIMEOUT:
                logging.error(f"[{self.name}] 로그인 실패: 타임아웃 초과")
                break

    def OnEventConnect(self, err_code):
        if err_code == 0:
            gm.api_connected = True
            logging.info(f"[{self.name}] 키움서버 연결 성공 (이벤트)")
        else:
            gm.api_connected = False
            error_msg = {
                -100: "사용자 정보교환 실패",
                -101: "서버접속 실패", 
                -102: "버전처리 실패"
            }.get(err_code, f"알 수 없는 오류: {err_code}")
            logging.error(f"[{self.name}] 키움서버 연결 실패: {error_msg}")
    
    def OnReceiveTrData(self, screen_no, rqname, trcode, record_name, next, *args):
        logging.info(f"[{self.name}] TR 데이터 수신: {rqname} ({trcode})")
    
    def OnReceiveRealData(self, code, real_type, real_data):
        if gm.api_connected:
            real_data_info = {
                'code': code,
                'real_type': real_type,
                'timestamp': time.time()
            }
            # frq_order로 Admin에게 실시간 데이터 전송
            if gm.admin.frq_order:
                gm.admin.frq_order('admin', 'real_data_procedure', real_data_info)
    
    def GetConnectState(self):
        return self.kiwoom.dynamicCall("GetConnectState()")

class Dbm:
    def __init__(self):
        self.name = 'dbm'
        pass

class Main:
    def __init__(self):
        pass

    def run(self):
        gm.admin = CommManager('admin', Admin, None)    # 메인 쓰레드 실행
        gm.api = CommManager('api', Api, 'process')     # 별도 프로세스
        gm.dbm = CommManager('dbm', Dbm, 'process')     # 별도 프로세스

        gm.api.order('login')
        connect = gm.api.answer('GetConnectState')
        if connect == 1:
            gm.admin.order('start_trading')

        self.cleanup()
        return

    def cleanup(self):
        gm.api.stop()
        gm.dbm.stop()
        gm.admin.stop()

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    from public import init_logger
    init_logger()
    logging.info("트레이딩 시스템 시작")
    main = Main()
    main.run()
