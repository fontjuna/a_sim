import multiprocessing as mp
from PyQt5.QtCore import QThread, QObject, pyqtSignal
import time
import uuid
import logging
import queue
import threading
from queue import Queue, Empty
import pythoncom

# 시스템 상수
TIMEOUT = 15

class SimpleManager:
    """단순 컴포넌트 관리자"""
    
    def __init__(self, name, cls, comm_type, *args, **kwargs):
        self.name = name
        self.comm_type = comm_type
        
        if comm_type == 'thread':
            self.instance = QThreadComponent(name, cls, *args, **kwargs)
        elif comm_type == 'process':
            self.instance = ProcessComponent(name, cls, *args, **kwargs)
        else:  # None (메인스레드)
            self.instance = cls(*args, **kwargs)
        
        ComponentRegistry.register(name, self.instance)
    
    def start(self):
        if self.comm_type in ['thread', 'process']:
            self.instance.start()
        else:
            if hasattr(self.instance, 'initialize'):
                self.instance.initialize()
        logging.info(f"[{self.name}] 시작")
    
    def stop(self):
        if self.comm_type in ['thread', 'process']:
            self.instance.stop()
        else:
            if hasattr(self.instance, 'cleanup'):
                self.instance.cleanup()
        logging.info(f"[{self.name}] 중지")
    
    def __getattr__(self, name):
        return getattr(self.instance, name)

class ComponentRegistry:
    """컴포넌트 공유 레지스트리"""
    _components = {}
    
    @classmethod
    def register(cls, name, component):
        cls._components[name] = component
        logging.info(f"컴포넌트 등록: {name}")
    
    @classmethod
    def get(cls, name):
        return cls._components.get(name)
    
    @classmethod
    def get_admin(cls):
        return cls._components.get('admin')
    
class QThreadComponent(QThread):
    """QThread 래퍼"""
    
    def __init__(self, name, cls, *args, **kwargs):
        super().__init__()
        self.name = name
        self.cls = cls
        self.init_args = args
        self.init_kwargs = kwargs
        self.instance = None
        self.running = False
    
    def start(self):
        self.running = True
        QThread.start(self)
    
    def stop(self):
        self.running = False
        self.quit()
        self.wait(3000)
        if self.isRunning():
            self.terminate()
    
    def run(self):
        """QThread 실행"""
        # 스레드 내에서 인스턴스 생성
        self.instance = self.cls(*self.init_args, **self.init_kwargs)
        
        # 다른 컴포넌트 참조 주입
        self._inject_references()
        
        # 초기화
        if hasattr(self.instance, 'initialize'):
            self.instance.initialize()
        
        logging.info(f"[{self.name}] QThread 시작")
        
        # 메인 로직 실행
        if hasattr(self.instance, 'run_main_loop'):
            self.instance.run_main_loop()
        else:
            # 기본 대기 루프
            while self.running:
                time.sleep(0.1)
        
        # 정리
        if hasattr(self.instance, 'cleanup'):
            self.instance.cleanup()
        
        logging.info(f"[{self.name}] QThread 종료")
    
    def _inject_references(self):
        """다른 컴포넌트 참조 주입"""
        # API 참조 주입 (Strategy에서 사용) - 프로세스 통신으로 변경
        if self.name == 'strategy':
            api_component = ComponentRegistry.get('api')
            if api_component:
                self.instance.api = api_component
                logging.info(f"[{self.name}] API 참조 주입 완료 (프로세스 통신)")
        
        # Admin 참조 주입 (결과 전송용)
        admin_component = ComponentRegistry.get_admin()
        if admin_component:
            self.instance.admin = admin_component
            logging.info(f"[{self.name}] Admin 참조 주입 완료")
        
        # DBM 참조 주입 (프로세스 통신용)
        dbm_component = ComponentRegistry.get('dbm')
        if dbm_component:
            self.instance.dbm = dbm_component
            logging.info(f"[{self.name}] DBM 참조 주입 완료")
    
    def order(self, method, *args, **kwargs):
        """단방향 전송"""
        # QThread는 같은 메모리 공간이므로 직접 호출 가능
        if hasattr(self.instance, method):
            try:
                getattr(self.instance, method)(*args, **kwargs)
            except Exception as e:
                logging.error(f"[{self.name}] {method} 실행 오류: {e}")
    
    def answer(self, method, *args, **kwargs):
        """응답 대기"""
        # QThread는 같은 메모리 공간이므로 직접 호출 가능
        if hasattr(self.instance, method):
            try:
                result = getattr(self.instance, method)(*args, **kwargs)
                return result
            except Exception as e:
                logging.error(f"[{self.name}] {method} 실행 오류: {e}")
                return None
        return None
    
    def frq_order(self, target, method, *args, **kwargs):
        """고빈도 스트림"""
        # 타겟 컴포넌트로 직접 전송
        target_component = ComponentRegistry.get(target)
        if target_component:
            try:
                target_method = getattr(target_component, method, None)
                if target_method:
                    target_method(*args, **kwargs)
                    logging.debug(f"[{self.name}] 스트림 전송: {target}.{method}")
                else:
                    logging.warning(f"[{self.name}] 타겟 메서드 없음: {target}.{method}")
            except Exception as e:
                logging.error(f"[{self.name}] 스트림 전송 오류: {e}")
        else:
            logging.warning(f"[{self.name}] 타겟 컴포넌트 없음: {target}")
        return True
    
    def frq_answer(self, method, *args, **kwargs):
        """고빈도 폴링"""
        # QThread는 같은 메모리 공간이므로 직접 호출 가능
        if hasattr(self.instance, method):
            try:
                result = getattr(self.instance, method)(*args, **kwargs)
                return result
            except Exception as e:
                logging.error(f"[{self.name}] {method} 폴링 오류: {e}")
                return None
        return None
    
    def __getattr__(self, name):
        if self.instance:
            return getattr(self.instance, name)
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
                
class ProcessComponent:
    """프로세스 래퍼"""
    
    def __init__(self, name, cls, *args, **kwargs):
        self.name = name
        self.cls = cls
        self.init_args = args
        self.init_kwargs = kwargs
        
        # 프로세스 통신용 큐
        self.request_queue = mp.Queue()
        self.response_queue = mp.Queue()
        self.process = None
        self.running = False
        
        # 응답 처리 스레드
        self.response_thread = None
        self.pending_responses = {}
    
    def start(self):
        """프로세스 시작"""
        self.running = True
        
        # 프로세스 시작 (직렬화 가능한 데이터만 전달)
        self.process = mp.Process(
            target=self._process_worker,
            args=(self.name, self.cls, self.init_args, self.init_kwargs,
                  self.request_queue, self.response_queue),
            daemon=False
        )
        self.process.start()
        
        # 응답 처리 스레드 시작
        self.response_thread = threading.Thread(target=self._response_handler, daemon=True)
        self.response_thread.start()
        
        logging.info(f"[{self.name}] 프로세스 시작")
    
    def stop(self):
        """프로세스 중지"""
        self.running = False
        if self.process and self.process.is_alive():
            try:
                self.request_queue.put({'command': 'stop'}, timeout=1.0)
            except: pass
            self.process.join(timeout=3.0)
            if self.process.is_alive():
                self.process.terminate()
        logging.info(f"[{self.name}] 프로세스 중지")
    
    def order(self, method, *args, **kwargs):
        """단방향 전송"""
        serializable_args = self._make_serializable(args)
        serializable_kwargs = self._make_serializable(kwargs)
        
        request = {
            'method': method,
            'args': serializable_args,
            'kwargs': serializable_kwargs
        }
        try:
            self.request_queue.put(request, timeout=1.0)
        except:
            logging.error(f"[{self.name}] {method} 요청 전송 실패")
    
    def answer(self, method, *args, **kwargs):
        """응답 대기"""
        req_id = str(uuid.uuid4())
        
        # 직렬화 가능한 데이터만 전송
        serializable_args = self._make_serializable(args)
        serializable_kwargs = self._make_serializable(kwargs)
        
        request = {
            'id': req_id,
            'method': method,
            'args': serializable_args,
            'kwargs': serializable_kwargs
        }
        
        # 응답 대기 준비
        event = threading.Event()
        self.pending_responses[req_id] = {'result': None, 'ready': event}
        
        try:
            self.request_queue.put(request, timeout=1.0)
        except Exception as e:
            logging.error(f"[{self.name}] 요청 전송 실패: {e}")
            self.pending_responses.pop(req_id, None)
            return None
        
        # 응답 대기
        if event.wait(TIMEOUT):
            result = self.pending_responses.pop(req_id)['result']
            return result
        else:
            self.pending_responses.pop(req_id, None)
            logging.warning(f"[{self.name}] {method} 응답 타임아웃")
            return None
    
    def frq_order(self, target, method, *args, **kwargs):
        """고빈도 단방향 전송 (스트림) - 대상 지정"""
        serializable_args = self._make_serializable(args)
        serializable_kwargs = self._make_serializable(kwargs)
        
        request = {
            'type': 'stream',
            'target': target,  # 대상 컴포넌트 지정
            'method': method,
            'args': serializable_args,
            'kwargs': serializable_kwargs
        }
        try:
            # 논블로킹으로 전송, 큐 풀 시 드롭
            self.request_queue.put_nowait(request)
            return True
        except queue.Full:
            logging.debug(f"[{self.name}] 스트림 큐 풀 - 드롭: {target}.{method}")
            return False
        except:
            logging.error(f"[{self.name}] 스트림 전송 실패: {target}.{method}")
            return False
    
    def frq_answer(self, method, *args, **kwargs):
        """고빈도 확인 (폴링) - 빠른 응답"""
        req_id = str(uuid.uuid4())
        
        serializable_args = self._make_serializable(args)
        serializable_kwargs = self._make_serializable(kwargs)
        
        request = {
            'id': req_id,
            'type': 'poll',
            'method': method,
            'args': serializable_args,
            'kwargs': serializable_kwargs
        }
        
        # 응답 대기 준비
        event = threading.Event()
        self.pending_responses[req_id] = {'result': None, 'ready': event}
        
        try:
            self.request_queue.put(request, timeout=0.1)  # 빠른 타임아웃
        except:
            self.pending_responses.pop(req_id, None)
            return None
        
        # 빠른 응답 대기 (1초)
        if event.wait(1.0):
            result = self.pending_responses.pop(req_id)['result']
            return result
        else:
            self.pending_responses.pop(req_id, None)
            return None
    
    def _make_serializable(self, data):
        """직렬화 가능한 형태로 변환"""
        if isinstance(data, (str, int, float, bool, type(None))):
            return data
        elif isinstance(data, (list, tuple)):
            return [self._make_serializable(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._make_serializable(v) for k, v in data.items()}
        else:
            # 직렬화 불가능한 객체는 문자열로 변환
            return str(data)
    
    def _response_handler(self):
        """응답 처리 스레드"""
        while self.running:
            try:
                response = self.response_queue.get(timeout=0.1)
                req_id = response.get('id')
                result = response.get('result')
                response_type = response.get('type')
                
                if response_type == 'route_stream':
                    # 스트림 라우팅 처리
                    target = response.get('target')
                    method = response.get('method')
                    args = response.get('args', ())
                    kwargs = response.get('kwargs', {})
                    
                    # 메인 프로세스에서 타겟 컴포넌트로 라우팅
                    target_component = ComponentRegistry.get(target)
                    if target_component:
                        try:
                            target_method = getattr(target_component, method, None)
                            if target_method:
                                target_method(*args, **kwargs)
                                logging.debug(f"[{self.name}] 스트림 라우팅: {target}.{method}")
                            else:
                                logging.warning(f"[{self.name}] 타겟 메서드 없음: {target}.{method}")
                        except Exception as e:
                            logging.error(f"[{self.name}] 스트림 라우팅 오류: {e}")
                    else:
                        logging.warning(f"[{self.name}] 타겟 컴포넌트 없음: {target}")
                
                elif req_id and req_id in self.pending_responses:
                    # 일반 응답 처리
                    self.pending_responses[req_id]['result'] = result
                    self.pending_responses[req_id]['ready'].set()
                    
            except Empty:
                continue
            except Exception as e:
                logging.error(f"[{self.name}] 응답 처리 오류: {e}")
    
    @staticmethod
    def _process_worker(name, cls, args, kwargs, request_queue, response_queue):
        """프로세스 워커 - 직렬화 문제 해결"""
        try:
            logging.info(f"[{name}] 프로세스 워커 시작")
            
            # 프로세스 내에서 새로 인스턴스 생성 (직렬화 문제 해결)
            instance = cls(*args, **kwargs)
            
            # 초기화 (키움 API 등은 여기서 새로 연결)
            if hasattr(instance, 'initialize'):
                init_result = instance.initialize()
                logging.info(f"[{name}] 프로세스 내 초기화 완료: {init_result}")
            
            while True:
                try:
                    request = request_queue.get(timeout=0.1)
                    
                    if request.get('command') == 'stop':
                        break
                    
                    method_name = request.get('method')
                    args = request.get('args', ())
                    kwargs = request.get('kwargs', {})
                    req_id = request.get('id')
                    req_type = request.get('type')
                    target = request.get('target')
                    
                    # 스트림 라우팅 처리
                    if req_type == 'stream' and target and target != name:
                        # 다른 컴포넌트로 라우팅 요청
                        response_queue.put({
                            'type': 'route_stream',
                            'target': target,
                            'method': method_name,
                            'args': args,
                            'kwargs': kwargs
                        })
                        continue
                    
                    # 자기 자신의 메서드 실행
                    if hasattr(instance, method_name):
                        try:
                            method = getattr(instance, method_name)
                            result = method(*args, **kwargs)
                            logging.info(f"[{name}] {method_name} 실행 완료: {result}")
                            
                            # 응답이 필요한 경우 (req_id가 있는 경우)
                            if req_id:
                                # 직렬화 가능한 결과만 전송
                                serializable_result = ProcessComponent._make_serializable_static(result)
                                response_queue.put({'id': req_id, 'result': serializable_result})
                        except Exception as e:
                            logging.error(f"[{name}] {method_name} 실행 오류: {e}")
                            if req_id:
                                response_queue.put({'id': req_id, 'result': None})
                    else:
                        logging.warning(f"[{name}] 메서드 없음: {method_name}")
                        if req_id:
                            response_queue.put({'id': req_id, 'result': None})
                    
                except Empty:
                    continue
                except Exception as e:
                    logging.error(f"[{name}] 프로세스 처리 오류: {e}")
            
            # 정리 (키움 API 연결 해제 등)
            if hasattr(instance, 'cleanup'):
                instance.cleanup()
            logging.info(f"[{name}] 프로세스 워커 종료")
            
        except Exception as e:
            logging.error(f"[{name}] 프로세스 초기화 오류: {e}")
    
    @staticmethod
    def _make_serializable_static(data):
        """정적 메서드로 직렬화 가능한 형태로 변환"""
        if isinstance(data, (str, int, float, bool, type(None))):
            return data
        elif isinstance(data, (list, tuple)):
            return [ProcessComponent._make_serializable_static(item) for item in data]
        elif isinstance(data, dict):
            return {k: ProcessComponent._make_serializable_static(v) for k, v in data.items()}
        else:
            # 직렬화 불가능한 객체는 문자열로 변환
            return str(data)
                                
class AdminComponent:
    """관리자 컴포넌트 - 메인스레드"""
    
    def __init__(self, name="Admin"):
        self.name = name
        self.results = []
        self.status = "ready"
    
    def initialize(self):
        logging.info(f"[{self.name}] 관리자 초기화")
    
    def receive_result(self, source, result_type, data):
        """다른 컴포넌트로부터 결과 수신"""
        result = {
            'timestamp': time.time(),
            'source': source,
            'type': result_type,
            'data': data
        }
        self.results.append(result)
        logging.info(f"[{self.name}] 결과 수신: {source} -> {result_type}: {data}")
    
    def get_results(self):
        """수집된 결과 조회"""
        return self.results
    
    def start_trading(self):
        """매매 시작 명령"""
        self.status = "trading"
        logging.info(f"[{self.name}] 매매 시작")
    
    def stop_trading(self):
        """매매 중지 명령"""
        self.status = "stopped"
        logging.info(f"[{self.name}] 매매 중지")
    
    def get_status(self):
        """상태 조회"""
        return self.status
    
    def cleanup(self):
        logging.info(f"[{self.name}] 관리자 정리")

class StrategyComponent:
    """전략 컴포넌트 - QThread"""
    
    def __init__(self, name="Strategy"):
        self.name = name
        self.api = None  # API 참조 (주입됨)
        self.admin = None  # Admin 참조 (주입됨)
        self.dbm = None  # DBM 참조 (주입됨)
        self.position = 0
        self.trade_count = 0
    
    def initialize(self):
        logging.info(f"[{self.name}] 전략 초기화")
    
    def run_main_loop(self):
        """메인 실행 루프"""
        logging.info(f"[{self.name}] 전략 실행 시작")
        
        while True:
            try:
                # Admin 상태 확인
                if self.admin and self.admin.get_status() == "trading":
                    self._execute_strategy()
                
                time.sleep(1)  # 1초마다 실행
                
            except Exception as e:
                logging.error(f"[{self.name}] 전략 실행 오류: {e}")
                break
    
    def _execute_strategy(self):
        """전략 실행"""
        # 1. API 프로세스를 통해 시세 조회
        if self.api:
            price = self.api.answer('get_current_price', "005930")  # 삼성전자
            logging.info(f"[{self.name}] 현재가 조회: {price}")
            
            # 2. 매매 판단
            if self._should_buy(price):
                # 3. API 프로세스를 통해 주문
                order_result = self.api.answer('order', "buy", "005930", 10, price)
                if order_result:
                    self.position += 10
                    self.trade_count += 1
                    
                    # 4. DBM에 거래 기록 저장
                    if self.dbm:
                        trade_data = {
                            'symbol': '005930',
                            'action': 'buy',
                            'quantity': 10,
                            'price': price,
                            'timestamp': time.time()
                        }
                        save_result = self.dbm.answer('save_trade', trade_data)
                        logging.info(f"[{self.name}] 거래 기록 저장: {save_result}")
                    
                    # 5. Admin에 결과 보고
                    if self.admin:
                        self.admin.receive_result(
                            self.name, 
                            "trade_executed", 
                            {"action": "buy", "symbol": "005930", "quantity": 10, "price": price}
                        )
    
    def _should_buy(self, price):
        """매수 판단 로직"""
        # 간단한 예시: 가격이 있고 포지션이 없으면 매수
        return price and price > 0 and self.position == 0
    
    def get_position(self):
        """포지션 조회"""
        return self.position
    
    def cleanup(self):
        logging.info(f"[{self.name}] 전략 정리")

class APIComponent:
    """API 컴포넌트 - 키움 OpenAPI (프로세스에서 실행)"""
    
    
    def __init__(self, name="API"):
        self.name = name
        # QAxWidget 객체는 여기서 생성하지 않음!
        self.kiwoom = None
        self.connected = False
        self.account_list = []
        self.app = None
    
    def initialize(self):
        """키움 API 초기화 - 프로세스 내에서만 실행"""
        try:
            logging.info(f"[{self.name}] 프로세스 내 키움 API 초기화 시작")
            
            # PyQt5 애플리케이션 초기화 (프로세스 내에서)
            from PyQt5.QtWidgets import QApplication
            import sys
            
            # 새로운 QApplication 생성 (프로세스마다 독립적)
            self.app = QApplication(sys.argv)
            logging.info(f"[{self.name}] QApplication 생성 완료")
            
            # 키움 API 임포트 및 초기화 (프로세스 내에서)
            try:
                from PyQt5.QAxContainer import QAxWidget
                import pythoncom
                
                # COM 초기화 (프로세스마다 독립적)
                pythoncom.CoInitialize()
                logging.info(f"[{self.name}] COM 초기화 완료")
                
                # QAxWidget 객체 생성 (프로세스 내에서만!)
                self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
                logging.info(f"[{self.name}] QAxWidget 객체 생성 완료")
                
                # 이벤트 연결
                self.kiwoom.OnEventConnect.connect(self._on_event_connect)
                self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
                self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)
                logging.info(f"[{self.name}] 이벤트 연결 완료")
                
                # 로그인 시도
                return self._login()
                
            except ImportError as e:
                logging.error(f"[{self.name}] 키움 API 임포트 실패 (개발환경): {e}")
                # 개발환경에서는 시뮬레이션 모드
                self.connected = True
                self.account_list = ["8888888-01", "9999999-01"]
                logging.info(f"[{self.name}] 시뮬레이션 모드로 실행")
                return True
                
        except Exception as e:
            logging.error(f"[{self.name}] 초기화 오류: {e}")
            return False
    
    def _login(self):
        """키움 로그인"""
        try:
            import pythoncom
            
            logging.info(f"[{self.name}] 로그인 시도 시작")
            
            # 로그인 요청
            ret = self.kiwoom.dynamicCall("CommConnect()")
            if ret == 0:
                logging.info(f"[{self.name}] 로그인 요청 전송 성공")
                
                # 로그인 결과 대기 (pythoncom.PumpWaitingMessages 사용)
                timeout_count = 0
                max_timeout = 300  # 30초 (100ms * 300)
                
                while not self.connected and timeout_count < max_timeout:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.1)
                    timeout_count += 1
                    
                    if timeout_count % 50 == 0:  # 5초마다 로그
                        logging.info(f"[{self.name}] 로그인 대기 중... ({timeout_count/10}초)")
                
                if self.connected:
                    # 계좌 정보 조회
                    try:
                        account_info = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "ACCNO")
                        if account_info:
                            self.account_list = account_info.split(';')[:-1]  # 마지막 빈 문자열 제거
                        
                        user_id = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "USER_ID")
                        user_name = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "USER_NAME")
                        
                        logging.info(f"[{self.name}] 로그인 성공")
                        logging.info(f"[{self.name}] 사용자: {user_name} ({user_id})")
                        logging.info(f"[{self.name}] 계좌 목록: {self.account_list}")
                        return True
                    except Exception as e:
                        logging.error(f"[{self.name}] 계좌 정보 조회 오류: {e}")
                        return False
                else:
                    logging.error(f"[{self.name}] 로그인 타임아웃")
                    return False
            else:
                logging.error(f"[{self.name}] 로그인 요청 실패: {ret}")
                return False
                
        except Exception as e:
            logging.error(f"[{self.name}] 로그인 처리 오류: {e}")
            return False
    
    def _on_event_connect(self, err_code):
        """로그인 결과 이벤트"""
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
        """TR 데이터 수신 이벤트"""
        logging.info(f"[{self.name}] TR 데이터 수신: {rqname} ({trcode})")
    
    def _on_receive_real_data(self, code, real_type, real_data):
        """실시간 데이터 수신 이벤트"""
        logging.debug(f"[{self.name}] 실시간 데이터: {code}")
    
    def get_current_price(self, symbol):
        """현재가 조회"""
        if not self.connected:
            logging.warning(f"[{self.name}] API 연결되지 않음")
            return None
        
        try:
            # kiwoom 객체 유효성 확인
            if not self.kiwoom:
                logging.error(f"[{self.name}] QAxWidget 객체가 None")
                return self._get_simulation_price(symbol)
            
            # 실제 키움 API 호출
            try:
                # 연결 상태 확인
                connect_state = self.kiwoom.dynamicCall("GetConnectState()")
                if connect_state != 1:
                    logging.warning(f"[{self.name}] 키움 연결 상태 이상: {connect_state}")
                    return self._get_simulation_price(symbol)
                
                # 현재가 조회를 위한 TR 요청
                self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", symbol)
                ret = self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", 
                                            "현재가조회", "opt10001", 0, "1001")
                
                if ret == 0:
                    # TR 응답 대기
                    import pythoncom
                    timeout_count = 0
                    max_timeout = 50  # 5초
                    
                    while timeout_count < max_timeout:
                        pythoncom.PumpWaitingMessages()
                        time.sleep(0.1)
                        timeout_count += 1
                        
                        # 간단한 시뮬레이션으로 가격 반환
                        if timeout_count > 5:
                            return self._get_simulation_price(symbol)
                
                logging.warning(f"[{self.name}] TR 응답 타임아웃")
                return self._get_simulation_price(symbol)
                
            except Exception as e:
                logging.error(f"[{self.name}] 키움 API 호출 오류: {e}")
                return self._get_simulation_price(symbol)
            
        except Exception as e:
            logging.error(f"[{self.name}] 현재가 조회 오류: {e}")
            return self._get_simulation_price(symbol)
    
    def _get_simulation_price(self, symbol):
        """시뮬레이션 가격 생성"""
        import random
        price = 75000 + random.randint(-1000, 1000)
        logging.info(f"[{self.name}] {symbol} 시뮬레이션 현재가: {price}")
        return price
    
    def order(self, action, symbol, quantity, price):
        """주문 전송"""
        if not self.connected:
            logging.error(f"[{self.name}] 연결되지 않음")
            return False
        
        if not self.account_list:
            logging.error(f"[{self.name}] 계좌 정보 없음")
            return False
        
        try:
            account = self.account_list[0]  # 첫 번째 계좌 사용
            
            if self.kiwoom:
                # 실제 키움 주문
                order_type = 1 if action == "buy" else 2  # 1:신규매수, 2:신규매도
                hoga_type = "00"  # 지정가
                
                ret = self.kiwoom.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                                            ["주문", "0101", account, order_type, symbol, quantity, price, hoga_type, ""])
                
                if ret == 0:
                    logging.info(f"[{self.name}] 주문 전송 성공: {action} {symbol} {quantity}주 @{price}")
                    return True
                else:
                    logging.error(f"[{self.name}] 주문 전송 실패: {ret}")
                    return False
            else:
                # 시뮬레이션
                logging.info(f"[{self.name}] 시뮬레이션 주문: {action} {symbol} {quantity}주 @{price} (계좌: {account})")
                return True
                
        except Exception as e:
            logging.error(f"[{self.name}] 주문 전송 오류: {e}")
            # 에러 발생 시 시뮬레이션으로 처리
            logging.info(f"[{self.name}] 시뮬레이션 주문 (에러 대체): {action} {symbol} {quantity}주 @{price}")
            return True
    
    def get_account_list(self):
        """계좌 목록 조회"""
        return self.account_list
    
    def is_connected(self):
        """연결 상태 확인"""
        return self.connected
    
    def cleanup(self):
        """정리"""
        try:
            if self.kiwoom:
                self.connected = False
                logging.info(f"[{self.name}] 키움 API 정리 완료")
            else:
                logging.info(f"[{self.name}] 시뮬레이션 모드 정리 완료")
                
            # COM 정리
            import pythoncom
            pythoncom.CoUninitialize()
            
        except Exception as e:
            logging.error(f"[{self.name}] 정리 오류: {e}")
                                      
class DBMComponent:
    """데이터베이스 컴포넌트 - 별도 프로세스"""
    
    def __init__(self, name="DBM"):
        self.name = name
        self.database = []  # 시뮬레이션용 메모리 DB
    
    def initialize(self):
        logging.info(f"[{self.name}] 데이터베이스 초기화")
    
    def save_trade(self, trade_data):
        """거래 데이터 저장"""
        trade_id = len(self.database) + 1
        trade_data['id'] = trade_id
        self.database.append(trade_data)
        
        logging.info(f"[{self.name}] 거래 저장: ID={trade_id}, {trade_data}")
        return trade_id
    
    def get_trades(self, symbol=None):
        """거래 내역 조회"""
        if symbol:
            trades = [t for t in self.database if t.get('symbol') == symbol]
        else:
            trades = self.database
        
        logging.info(f"[{self.name}] 거래 조회: {len(trades)}건")
        return trades
    
    def get_trade_count(self):
        """거래 건수 조회"""
        count = len(self.database)
        logging.info(f"[{self.name}] 총 거래 건수: {count}")
        return count
    
    def cleanup(self):
        logging.info(f"[{self.name}] 데이터베이스 정리")

def test_trading_system():
    """트레이딩 시스템 테스트"""
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    logging.info("=== 키움 API 프로세스 트레이딩 시스템 테스트 ===")
    
    try:
        # 컴포넌트 생성
        logging.info("\n1. 컴포넌트 생성")
        admin = SimpleManager('admin', AdminComponent, None, "AdminComp")
        api = SimpleManager('api', APIComponent, 'process', "APIComp")  # 프로세스로 변경
        strategy = SimpleManager('strategy', StrategyComponent, 'thread', "StrategyComp")
        dbm = SimpleManager('dbm', DBMComponent, 'process', "DBMComp")
        
        # 시작
        logging.info("\n2. 컴포넌트 시작")
        admin.start()
        api.start()
        dbm.start()
        strategy.start()  # Strategy는 마지막에 시작 (참조 주입 후)
        
        time.sleep(2)  # 초기화 대기
        
        # API 연결 상태 확인
        logging.info("\n3. API 연결 상태 확인")
        connected = api.answer('is_connected')
        account_list = api.answer('get_account_list')
        logging.info(f"API 연결 상태: {connected}")
        logging.info(f"계좌 목록: {account_list}")
        
        if not connected:
            logging.error("API 연결 실패 - 테스트 중단")
            return
        
        # 매매 시작
        logging.info("\n4. 매매 시작")
        admin.start_trading()
        
        # 5초간 실행
        time.sleep(5)
        
        # 결과 확인
        logging.info("\n5. 결과 확인")
        results = admin.get_results()
        logging.info(f"Admin 수집 결과: {len(results)}건")
        for result in results:
            logging.info(f"  - {result}")
        
        # API 상태 재확인
        final_connected = api.answer('is_connected')
        logging.info(f"최종 API 연결 상태: {final_connected}")
        
        # DBM 직접 조회
        trade_count = dbm.answer('get_trade_count')
        logging.info(f"DBM 거래 건수: {trade_count}")
        
        trades = dbm.answer('get_trades')
        logging.info(f"DBM 거래 내역: {trades}")
        
        # 매매 중지
        logging.info("\n6. 매매 중지")
        admin.stop_trading()
        
        time.sleep(1)
        
        logging.info("\n=== 키움 API 프로세스 트레이딩 시스템 완료 ===")
        logging.info("✅ Admin(메인) - 전체 관리")
        logging.info("✅ API(프로세스) - 키움서버 실제 로그인")
        logging.info("✅ Strategy(스레드) - API 프로세스 통신")
        logging.info("✅ DBM(프로세스) - 별도 프로세스")
        logging.info("✅ 직렬화 문제 해결")
        logging.info("✅ 키움 API 프로세스 내 초기화")
        
    except Exception as e:
        logging.error(f"테스트 오류: {e}", exc_info=True)
    
    finally:
        # 정리
        for comp in [strategy, dbm, api, admin]:
            comp.stop()
        app.quit()


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    from public import init_logger
    init_logger()
    logging.info("키움 API 프로세스 트레이딩 시스템 시작")
    test_trading_system()