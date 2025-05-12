import logging
import time

# 테스트용 클래스 정의
class Admin:
    def echo_test(self, msg, extra=None):
        logging.info(f"[Admin] echo_test 호출됨: {msg}")
        return f"Admin 응답: {msg}", True

class Strategy:
    def echo_test(self, msg, extra=None):
        logging.info(f"[Strategy] echo_test 호출됨: {msg}")
        return f"Strategy 응답: {msg}", True

class DBManager:
    def echo_test(self, msg, extra=None):
        logging.info(f"[DBManager] echo_test 호출됨: {msg}")
        return f"DBManager 응답: {msg}", True
    
    def call_api(self):
        logging.info("[DBManager] API 호출 시도")
        try:
            result = self.answer('api', 'echo_test', "DBM에서 API로 요청", extra=123)
            if result is None:
                logging.error("[DBManager] API 호출 실패 (타임아웃 또는 오류)")
                return "호출 실패", False
            data, success = result
            logging.info(f"[DBManager] API 응답: {data}, {success}")
            return data, success
        except Exception as e:
            logging.error(f"[DBManager] API 호출 중 예외 발생: {e}", exc_info=True)
            return f"예외 발생: {str(e)}", False

    def call_cht(self):
        logging.info("[DBManager] CHT 호출 시도")
        try:
            result = self.answer('cht', 'echo_test', "DBM에서 CHT로 요청")
            if result is None:
                logging.error("[DBManager] CHT 호출 실패 (타임아웃 또는 오류)")
                return "호출 실패", False
            data, success = result
            logging.info(f"[DBManager] CHT 응답: {data}, {success}")
            return data, success
        except Exception as e:
            logging.error(f"[DBManager] CHT 호출 중 예외 발생: {e}", exc_info=True)
            return f"예외 발생: {str(e)}", False

class APIModule:
    def echo_test(self, msg, extra=None):
        logging.info(f"[APIModule] echo_test 호출됨: {msg}, extra={extra}")
        return f"API 응답: {msg}", True
    
    def api_request(self, param1, param2=None):
        logging.info(f"[APIModule] api_request 호출됨: {param1}, {param2}")
        # 큰 사전 리스트 생성 (테스트용)
        data = [{'id': i, 'value': f'test_{i}'} for i in range(10)]  # 테스트용으로 10개만
        return data, True

    def init_chart_thread(self):
        """API 프로세스 내에서 Chart 스레드 초기화"""
        # from ipc_manager import IPCManager  # 필요시 동적 임포트
        
        # 로컬 IPCManager 생성 (프로세스 내부용)
        # self.local_ipc = IPCManager()
        
        # Chart 매니저 생성 및 스레드로 등록
        from worker import ChartManager  # ChartManager 클래스 임포트
        cht = ChartManager()
        self.register('cht', cht, 'thread', start=True)
        
        logging.info("[APIModule] ChartManager 스레드 초기화 완료")
        return True

    def call_chart(self, method, *args, **kwargs):
        """API 프로세스 내 Chart 스레드 호출"""
        if not hasattr(self, 'local_ipc'):
            logging.error("[APIModule] ChartManager가 초기화되지 않았습니다.")
            return None
        
        logging.info(f"[APIModule] Chart 호출: {method}")
        return self.answer('cht', method, *args, **kwargs)

class ChartManager:
    def echo_test(self, msg, extra=None):
        logging.info(f"[ChartManager] echo_test 호출됨: {msg}")
        return f"Chart 응답: {msg}", True

# 스레드에서 실행할 테스트 함수들
def test_stg_to_api(stg):
    """스레드에서 API 호출 테스트"""
    stg.work('api', 'echo_test', "STG에서 API로 work")
    data, success = stg.answer('api', 'api_request', "STG에서 API로 요청", "파라미터")
    logging.info(f"STG->API 결과 타입: {type(data)}, 성공: {success}")
    if isinstance(data, list):
        logging.info(f"STG->API 리스트 길이: {len(data)}")
    return data, success

def test_stg_to_cht(stg):
    """스레드에서 CHT 호출 테스트"""
    stg.work('cht', 'echo_test', "STG에서 CHT로 work")
    data, success = stg.answer('cht', 'echo_test', "STG에서 CHT로 answer")
    logging.info(f"STG->CHT 결과: {data}, {success}")
    return data, success

# 테스트 클래스들
class ADM:
    def __init__(self):
        logging.info("Admin 초기화 완료")
    
    def admin_method(self, data):
        logging.info(f"Admin: admin_method 호출됨, 데이터: {data}")
        return f"Admin 처리 결과: {data}"
    
    def call_strategy(self, stg_name, data):
        logging.info(f"Admin: {stg_name}의 process_data 메서드 호출")
        return self.answer(stg_name, 'process_data', data)
    
    def call_strategy_async(self, stg_name, data):
        logging.info(f"Admin: {stg_name}의 process_data 메서드 비동기 호출")
        
        def callback(result):
            logging.info(f"Admin: {stg_name}로부터 콜백 결과 수신: {result}")
        
        self.work(stg_name, 'process_data', data, callback=callback)
        return "비동기 호출 완료"

class STG:
    def __init__(self, name="unknown"):
        self.name = name
        logging.info(f"Strategy({name}) 초기화 완료")
    
    def process_data(self, data):
        logging.info(f"Strategy({self.name}): process_data 호출됨, 데이터: {data[:1]}")
        # 시간이 걸리는 작업 시뮬레이션
        time.sleep(0.1)
        return f"Strategy({self.name}) 처리 결과: {data[:1]}"
    
    def call_admin(self, data):
        logging.info(f"Strategy({self.name}): Admin의 admin_method 호출")
        return self.answer('admin', 'admin_method', data)
    
    def call_api(self, data):
        logging.info(f"Strategy({self.name}): APIServer의 api_method 호출")
        return self.answer('api', 'api_method', data)
    
    def call_other_strategy(self, other_stg, data):
        logging.info(f"Strategy({self.name}): {other_stg}의 process_data 호출")
        return self.answer(other_stg, 'process_data', data)

class API:
    def __init__(self):
        logging.info("APIServer 초기화 완료")
    
    def api_method(self, data):
        logging.info(f"APIServer: api_method 호출됨, 데이터: {data}")
        return f"APIServer 처리 결과: {data}"
    
    def call_dbm(self, data):
        logging.info(f"APIServer: DBManager의 db_query 메서드 호출")
        return self.answer('dbm', 'db_query', data)
    
    def call_dbm_async(self, data):
        logging.info(f"APIServer: DBManager의 db_query 메서드 비동기 호출")
        
        def callback(result):
            logging.info(f"APIServer: DBManager로부터 콜백 결과 수신: {result[:1]}")
        
        self.work('dbm', 'db_query', data, callback=callback)
        return "비동기 호출 완료"

class DBM:
    def __init__(self):
        logging.info("DBManager 초기화 완료")
    
    def db_query(self, query):
        logging.info(f"DBManager: db_query 호출됨, 쿼리: {query[:1]}")
        # 데이터베이스 쿼리 시뮬레이션
        time.sleep(0.2)
        return f"DBManager 쿼리 결과: {query}"
    
    def call_strategy(self, stg_name, data):
        logging.info(f"DBManager: {stg_name}의 process_data 메서드 호출")
        return self.answer(stg_name, 'process_data', data)
    
    def call_api(self, data):
        logging.info(f"DBManager: APIServer의 api_method 호출")
        return self.answer('api', 'api_method', data)
    
    def call_api_async(self, data):
        logging.info(f"DBManager: APIServer의 api_method 비동기 호출")
        
        def callback(result):
            logging.info(f"DBManager: APIServer로부터 콜백 결과 수신: {result[:1]}")
        
        self.work('api', 'api_method', data, callback=callback)
        return "비동기 호출 완료"
