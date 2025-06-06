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

class SimpleManager:
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

        result = gm.api.answer('GetMasterCodeName', '005930')
        logging.info(f"[{self.name}] -> API / 종목코드: 005930, 종목명: {result}")

        result = gm.dbm.answer('dbm_response', 'dbm call')
        logging.info(f"[{self.name}] -> DBM / {result}")

        gm.stg = SimpleManager('stg', Strategy, 'thread')
        gm.stg.start()
        time.sleep(1.0)  # STG 시작 대기만 유지

        result = gm.stg.answer('stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG  / {result}")

        logging.info(f"[{self.name}] -> STG 로 제어 넘김")
        gm.stg.order('start_stg')
        
        # STG 완료 대기 (플래그 기반)
        if self.wait_for_component('stg'):
            logging.info(f"[{self.name}] STG 완료 확인")
        
        logging.info(f"[{self.name}] -> API 로 제어 넘김")
        gm.api.order('start_api')
        
        # API 완료 대기 (플래그 기반)
        if self.wait_for_component('api'):
            logging.info(f"[{self.name}] API 완료 확인")

        logging.info(f"[{self.name}] -> DBM 로 제어 넘김")
        gm.dbm.order('start_dbm')
        
        # DBM 완료 대기 (플래그 기반)
        if self.wait_for_component('dbm'):
            logging.info(f"[{self.name}] DBM 완료 확인")

        gm.stg.stop()
        logging.info(f"[{self.name}] 모든 작업 완료")

    def on_receive_real_data(self, data):
        logging.info(f"[{self.name}] -> 실시간 데이터 수신: {data}")

    def admin_response(self, data):
        return f"[{self.name}] 응답: {data}"

    def order(self, method, *args, **kwargs):
        result = None
        if hasattr(self, method):
            try:
                result = getattr(self, method)(*args, **kwargs)
                logging.debug(f"[{self.name}] order {method} 완료")
            except Exception as e:
                logging.error(f"[{self.name}] {method} 실행 오류: {e}")
        else:
            logging.warning(f"[{self.name}] {method} 메서드 없음")
        return result

    def answer(self, method, *args, **kwargs):
        return self.order(method, *args, **kwargs)

    def shutdown(self):
        pass

class Strategy:
    def __init__(self):
        self.name = 'stg'
        self.trading_done = False
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def start_stg(self):
        logging.info(f"\n[{self.name}] 시작 {'*' * 10}")

        result = gm.admin.answer('admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / {result}")

        name = gm.api.answer('GetMasterCodeName', '000660')
        last_price = gm.api.answer('GetMasterLastPrice', '000660')
        logging.info(f"[{self.name}] -> API / 종목코드: 000660, 종목명: {name}, 전일가: {last_price}")

        result = gm.dbm.answer('dbm_response', 'dbm call')
        logging.info(f"[{self.name}] -> DBM / {result}")

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

        result = self.answer('admin', 'admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / {result}")

        result = self.answer('dbm', 'dbm_response', 'dbm call')
        logging.info(f"[{self.name}] -> DBM / {result}")

        result = self.answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG / {result}")

        logging.info(f"[{self.name}] 실시간 데이터 전송 시작")
        for i in range(10):
            self.frq_order('admin', 'on_receive_real_data', f'real_data_info_{i}')
        
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

        result = self.answer('admin', 'admin_response', 'admin call')
        logging.info(f"[{self.name}] -> Admin / {result}")

        result = self.answer('api', 'api_response', 'api call')
        logging.info(f"[{self.name}] -> API / {result}")

        result = self.answer('stg', 'stg_response', 'stg call')
        logging.info(f"[{self.name}] -> STG / {result}")

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
            gm.api.order('login')
            # 연결 확인 (1이면 연결됨)
            timeout_count = 0
            while not gm.api.answer('is_connected') and timeout_count < 100:
                time.sleep(0.1)
                timeout_count += 1
            
            if gm.api.answer('is_connected'):
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
        try:
            if hasattr(gm, 'stg') and gm.stg:
                gm.stg.stop()
                logging.info(f"[Main] STG 종료")
        except Exception as e:
            logging.error(f"[Main] STG 종료 오류: {e}")
        
        try:
            if hasattr(gm, 'api') and gm.api:
                gm.api.stop()
                logging.info(f"[Main] API 종료")
        except Exception as e:
            logging.error(f"[Main] API 종료 오류: {e}")
        
        try:
            if hasattr(gm, 'dbm') and gm.dbm:
                gm.dbm.stop()
                logging.info(f"[Main] DBM 종료")
        except Exception as e:
            logging.error(f"[Main] DBM 종료 오류: {e}")
        
        try:
            if hasattr(gm, 'admin') and gm.admin:
                gm.admin.stop()
                logging.info(f"[Main] Admin 종료")
        except Exception as e:
            logging.error(f"[Main] Admin 종료 오류: {e}")
        
        # 프로세스 강제 종료
        import os
        import signal
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

