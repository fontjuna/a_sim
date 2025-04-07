"""
독자적 클래스와 공용 변수 정의 
스레드 안전하게 구현된 버전 (2025-03-30)
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
import logging.config
import logging.handlers
import os
import sys
import json
import threading
import copy
from enum import Enum
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple, Union

def hoga(current_price, position=0):
    # logging.debug(f'hoga : current_price={current_price}, position={position}')
    def get_hoga_unit(price):
        if price < 2000: return 1
        elif price < 5000: return 5
        elif price < 20000: return 10
        elif price < 50000: return 50
        elif price < 200000: return 100
        elif price < 500000: return 500
        else: return 1000

    # 현재 가격이 호가 단위에 맞지 않으면 가까운 호가 단위로 조정
    hoga_unit = get_hoga_unit(current_price)
    remainder = current_price % hoga_unit
    
    if remainder != 0:
        # 가까운 호가 단위로 조정
        if remainder >= hoga_unit / 2:
            current_price = current_price + (hoga_unit - remainder)  # 올림
        else:
            current_price = current_price - remainder  # 내림
    
    if position == 0:
        return current_price

    # 호가 단위에 맞게 조정된 가격에 position 적용
    hoga_unit = get_hoga_unit(current_price)
    new_price = current_price + (hoga_unit * position)

    # 호가 단위가 변경되는 경계값 처리
    new_hoga_unit = get_hoga_unit(new_price)
    if new_hoga_unit != hoga_unit:
        if position > 0:
            return new_price - (new_price % new_hoga_unit)
        elif position < 0:
            return new_price + (new_hoga_unit - (new_price % new_hoga_unit)) if new_price % new_hoga_unit != 0 else new_price

    return new_price

def get_path(subdir=None):
    """경로 반환
    subdir=None: 기본 경로
    subdir='resources': 리소스 폴더 abc.ui, abc.ico
    subdir='data': 데이터 폴더 등
    실행 파일 또는 스크립트가 있는 폴더 경로 반환"""
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False)
                         else os.path.abspath(__file__))
    if subdir:
        if getattr(sys, 'frozen', False):
            path = os.path.join(base, '_internal', subdir)
        else:
            path = os.path.join(base, subdir)
        if not os.path.exists(path):
            os.makedirs(path)
        return path
    return base

def load_json(file_path, default_data):
    try:
        if not os.path.exists(file_path):
            logging.warning(f'파일이 없어 기본값을 저장한 후 사용 합니다. {os.path.basename(file_path)}')
            logging.debug(f'기본값: {default_data}')
            result, data = save_json(file_path, default_data)
            return result, data

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return True, data

    except json.JSONDecodeError as e:
        result, data = save_json(file_path, default_data)
        return result, data
    
    except Exception as e:
        logging.error(f'파일 로드 오류: {os.path.basename(file_path)} {type(e).__name__} - {e}', exc_info=True)
        return False, e

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True, data

    except Exception as e:
        logging.error(f'파일 저장 오류: {os.path.basename(file_path)} {type(e).__name__} - {e}', exc_info=True)
        return False, e

@dataclass
class Work:
    order: str              # 수신자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    job: dict = field(default_factory=lambda: {})  # 수신자가 실행할 함수에 전달할 데이터

class CallType(Enum):
    DIRECT = 1    # 직접 호출 (동기)
    ASYNC = 2     # 비동기 호출 (결과 기다리지 않음)
    RPC = 3       # 원격 호출 (결과 필요)

class ThreadSafeDict:
    """스레드 안전한 딕셔너리 구현"""
    def __init__(self, initial_data=None):
        self._lock = threading.RLock()
        self._data = initial_data or {}
    
    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            return value
    
    def delete(self, key):
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def items(self):
        with self._lock:
            return list(self._data.items())
    
    def keys(self):
        with self._lock:
            return list(self._data.keys())
    
    def values(self):
        with self._lock:
            return list(self._data.values())
    
    def clear(self):
        with self._lock:
            self._data.clear()
    
    def update(self, new_data):
        with self._lock:
            self._data.update(new_data)
            
    def __contains__(self, key):
        with self._lock:
            return key in self._data
            
    def copy(self):
        with self._lock:
            return self._data.copy()

class ThreadSafeList:
    """스레드 안전한 리스트 구현"""
    def __init__(self, initial_data=None):
        self._lock = threading.RLock()
        self._data = list(initial_data) if initial_data else []
    
    def get(self, index):
        with self._lock:
            if 0 <= index < len(self._data):
                return self._data[index]
            return None
    
    def set(self, index, value):
        with self._lock:
            if 0 <= index < len(self._data):
                self._data[index] = value
                return True
            return False
    
    def append(self, value):
        with self._lock:
            self._data.append(value)
    
    def extend(self, values):
        with self._lock:
            self._data.extend(values)
    
    def remove(self, value):
        with self._lock:
            if value in self._data:
                self._data.remove(value)
                return True
            return False
    
    def pop(self, index=-1):
        with self._lock:
            return self._data.pop(index)
    
    def clear(self):
        with self._lock:
            self._data.clear()
    
    def __len__(self):
        with self._lock:
            return len(self._data)
    
    def __getitem__(self, index):
        return self.get(index)
    
    def __setitem__(self, index, value):
        self.set(index, value)
    
    def __iter__(self):
        with self._lock:
            # 복사본 반환하여 순회 중 변경 방지
            return iter(self._data.copy())
    
    def copy(self):
        with self._lock:
            return self._data.copy()

class ModuleAccessLayer:
    """모듈 간 통신을 위한 접근 계층"""
    def __init__(self):
        self._modules = {}
        self._queue_map = {}
        self._lock = threading.RLock()
        self._semaphores = {}
        self._results = {}
        self._timeout = 10  # 기본 타임아웃 초
    
    def register_module(self, module_name, module_instance):
        """모듈 등록"""
        with self._lock:
            self._modules[module_name] = module_instance
            self._queue_map[module_name] = Queue()
            self._semaphores[module_name] = {}
            self._results[module_name] = {}
    
    def work(self, module_name, function_name, **kwargs):
        """비동기 작업 요청 - 결과를 기다리지 않음"""
        if module_name not in self._queue_map:
            logging.error(f"등록되지 않은 모듈 {module_name}에 작업 요청 시도")
            return False
        
        # 작업 큐에 넣기
        self._queue_map[module_name].put(Work(order=function_name, job=kwargs))
        return True
    
    def answer(self, module_name, function_name, **kwargs):
        """동기적 작업 요청 - 결과를 기다림"""
        if module_name not in self._modules:
            logging.error(f"등록되지 않은 모듈 {module_name}에 응답 요청 시도")
            return None
        
        # 고유 ID 생성
        request_id = f"{function_name}_{threading.get_ident()}_{datetime.now().timestamp()}"
        
        # 세마포어 생성
        with self._lock:
            self._semaphores[module_name][request_id] = threading.Semaphore(0)
            self._results[module_name][request_id] = None
        
        # 작업 큐에 넣기 (request_id 포함)
        kwargs['_request_id'] = request_id
        self._queue_map[module_name].put(Work(order=function_name, job=kwargs))
        
        # 결과 기다리기
        if self._semaphores[module_name][request_id].acquire(timeout=self._timeout):
            # 결과 가져오기
            with self._lock:
                result = self._results[module_name][request_id]
                del self._results[module_name][request_id]
                del self._semaphores[module_name][request_id]
            return result
        else:
            # 타임아웃
            logging.warning(f"{module_name}.{function_name} 호출 타임아웃")
            with self._lock:
                if request_id in self._semaphores[module_name]:
                    del self._semaphores[module_name][request_id]
                if request_id in self._results[module_name]:
                    del self._results[module_name][request_id]
            return None
    
    def set_result(self, module_name, request_id, result):
        """작업 결과 설정"""
        with self._lock:
            if module_name in self._semaphores and request_id in self._semaphores[module_name]:
                self._results[module_name][request_id] = result
                self._semaphores[module_name][request_id].release()
                return True
        return False
    
    def get_queue(self, module_name):
        """모듈의 작업 큐 가져오기"""
        return self._queue_map.get(module_name, None)

# 모듈 간 통신을 위한 전역 객체
la = ModuleAccessLayer()

## Define Constants *************************************************************************
@dataclass
class FieldsAttributes: # 데이터베이스 필드 정의
    name: str
    type: str
    default: any = None
    primary: bool = False
    autoincrement: bool = False
    unique: bool = False
    not_null: bool = False
    index: any = False
    foreign_key: dict = None
    check: str = None

@dataclass
class DataBaseFields:
    id = FieldsAttributes(name='id', type='INTEGER', primary=True, autoincrement=True)
    계좌번호 = FieldsAttributes(name='계좌번호', type='TEXT', not_null=True, default="''")
    당일매매세금 = FieldsAttributes(name='당일매매세금', type='INTEGER', not_null=True, default=0)
    당일매매수수료 = FieldsAttributes(name='당일매매수수료', type='INTEGER', not_null=True, default=0)
    단위체결가 = FieldsAttributes(name='단위체결가', type='INTEGER', not_null=True, default=0)
    단위체결량 = FieldsAttributes(name='단위체결량', type='INTEGER', not_null=True, default=0)
    매도가 = FieldsAttributes(name='매도가', type='INTEGER', not_null=True, default=0)
    매도금액 = FieldsAttributes(name='매도금액', type='INTEGER', not_null=True, default=0)
    매도번호 = FieldsAttributes(name='매도번호', type='TEXT', not_null=True, default="''")
    매도수구분 = FieldsAttributes(name='매도수구분', type='TEXT', not_null=True, default="''")
    매도수량 = FieldsAttributes(name='매도수량', type='INTEGER', not_null=True, default=0)
    매도시간 = FieldsAttributes(name='매도시간', type='TEXT', not_null=True, default="(strftime('%H:%M:%S', 'now', 'localtime'))")
    매도일자 = FieldsAttributes(name='매도일자', type='TEXT', not_null=True, default="(strftime('%Y%m%d', 'now', 'localtime'))")
    매수가 = FieldsAttributes(name='매수가', type='INTEGER', not_null=True, default=0)
    매수금액 = FieldsAttributes(name='매수금액', type='INTEGER', not_null=True, default=0)
    매수번호 = FieldsAttributes(name='매수번호', type='TEXT', not_null=True, default="''")
    매수수량 = FieldsAttributes(name='매수수량', type='INTEGER', not_null=True, default=0)
    매수시간 = FieldsAttributes(name='매수시간', type='TEXT', not_null=True, default="(strftime('%H:%M:%S', 'now', 'localtime'))")
    매수일자 = FieldsAttributes(name='매수일자', type='TEXT', not_null=True, default="(strftime('%Y%m%d', 'now', 'localtime'))")
    매수전략 = FieldsAttributes(name='매수전략', type='TEXT', not_null=True, default="''")
    매입단가 = FieldsAttributes(name='매입단가', type='INTEGER', not_null=True, default=0)
    매매구분 = FieldsAttributes(name='매매구분', type='TEXT', not_null=True, default="''")
    미체결수량 = FieldsAttributes(name='미체결수량', type='INTEGER', not_null=True, default=0)
    보유수량 = FieldsAttributes(name='보유수량', type='INTEGER', not_null=True, default=0)
    손익금액 = FieldsAttributes(name='손익금액', type='INTEGER', not_null=True, default=0)
    손익율 = FieldsAttributes(name='손익율', type='REAL', not_null=True, default=0.0)
    요청명 = FieldsAttributes(name='요청명', type='TEXT', not_null=True, default="''")
    원주문번호 = FieldsAttributes(name='원주문번호', type='TEXT', not_null=True, default="''")
    전략 = FieldsAttributes(name='전략', type='TEXT', not_null=True, default="''")
    전략명칭 = FieldsAttributes(name='전략명칭', type='TEXT', not_null=True, default="''")
    전략번호 = FieldsAttributes(name='전략번호', type='INTEGER', not_null=True, default=0)
    제비용 = FieldsAttributes(name='제비용', type='INTEGER', not_null=True, default=0)
    종목명 = FieldsAttributes(name='종목명', type='TEXT', not_null=True, default="''")
    종목번호 = FieldsAttributes(name='종목번호', type='TEXT', not_null=True, default="''")
    종목코드 = FieldsAttributes(name='종목코드', type='TEXT', not_null=True, default="''")
    주문가격 = FieldsAttributes(name='주문가격', type='INTEGER', not_null=True, default=0)
    주문가능수량 = FieldsAttributes(name='주문가능수량', type='INTEGER', not_null=True, default=0)
    주문구분 = FieldsAttributes(name='주문구분', type='TEXT', not_null=True, default="''")
    주문번호 = FieldsAttributes(name='주문번호', type='TEXT', not_null=True, default="''")
    주문상태 = FieldsAttributes(name='주문상태', type='TEXT', not_null=True, default="''")
    주문수량 = FieldsAttributes(name='주문수량', type='INTEGER', not_null=True, default=0)
    주문유형 = FieldsAttributes(name='주문유형', type='TEXT', not_null=True, default="''")
    총매입가 = FieldsAttributes(name='총매입가', type='INTEGER', not_null=True, default=0)
    체결가 = FieldsAttributes(name='체결가', type='INTEGER', not_null=True, default=0)
    체결누계금액 = FieldsAttributes(name='체결누계금액', type='INTEGER', not_null=True, default=0)
    체결량 = FieldsAttributes(name='체결량', type='INTEGER', not_null=True, default=0)
    체결번호 = FieldsAttributes(name='체결번호', type='TEXT', not_null=True, default="''")
    체결시간 = FieldsAttributes(name='체결시간', type='TEXT', not_null=True, default="''")
    처리일시 = FieldsAttributes(name='처리일시', type='TEXT', not_null=True, default="(strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))")
    현재가 = FieldsAttributes(name='현재가', type='INTEGER', not_null=True, default=0)
    호가구분 = FieldsAttributes(name='호가구분', type='TEXT', not_null=True, default="''")
    화면번호 = FieldsAttributes(name='화면번호', type='TEXT', not_null=True, default="''")

# 나머지 코드 (DataBaseColumns, FIDs 등)는 다음 파트에서 이어집니다... 

class ThreadSafeGlobalMemory:
    """스레드 안전한 글로벌 메모리 클래스"""
    def __init__(self):
        self._lock = threading.RLock()
        self._data = {}
        self._initialized = False
        
        # 모듈 레퍼런스들
        self.main = None
        self.gui = None
        self.api = None
        self.dbm = None
        self.admin = None
        self.aaa = None
        self.odr = None
        self.toast = None
        
        # 설정과 상태 데이터
        self.json_config = None
        self.config = None
        self.tbl = None
        
        # 테이블 관리자들
        self.잔고합산 = None
        self.잔고목록 = None 
        self.매수조건목록 = None
        self.매도조건목록 = None
        self.예수금 = None
        self.일지합산 = None
        self.일지목록 = None
        self.체결목록 = None
        self.손익목록 = None
        self.전략정의 = None
        self.주문목록 = None
        
        # 기타 값들
        self.l2잔고합산_copy = None
        self.l2손익합산 = 0
        
        # 요청 제한 체크
        self.req = None
        self.ord = None
        
        # 전략 관련
        self.strategy_row = None
        self.basic_strategy = None
        self.전략설정 = None
        self.전략쓰레드 = None
        
        # 스레드 안전 컬렉션들
        self.qwork = {}
        self.qanswer = {}
        self.매수문자열들 = ThreadSafeList([''] * 6)
        self.매도문자열들 = ThreadSafeList([''] * 6)
        self.dict잔고종목감시 = ThreadSafeDict()
        self.dict조건종목감시 = ThreadSafeDict()
        self.dict종목정보 = ThreadSafeDict()
        self.dict주문대기종목 = ThreadSafeDict()
        
        # JSON 데이터
        self.json_counter_tickers = {}
        self.json_counter_strategy = {}
        self.holdings = {}
        
        # 수수료 관련
        self.수수료율 = 0.0
        self.세금율 = 0.0
    
    def initialize(self):
        """글로벌 메모리 초기화 - 스레드 안전하게 딱 한번만 실행됨"""
        with self._lock:
            if self._initialized:
                return False
            
            # 각종 초기화 작업
            self._initialized = True
            return True
    
    def get(self, key, default=None):
        """임의의 키-값 쌍 가져오기"""
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key, value):
        """임의의 키-값 쌍 설정하기"""
        with self._lock:
            self._data[key] = value
            return True
    
    def update_매수문자열(self, index, value):
        """매수문자열 안전하게 업데이트"""
        if 0 <= index < len(self.매수문자열들):
            self.매수문자열들[index] = value
            return True
        return False
    
    def update_매도문자열(self, index, value):
        """매도문자열 안전하게 업데이트"""
        if 0 <= index < len(self.매도문자열들):
            self.매도문자열들[index] = value
            return True
        return False
    
    def send_status_msg(self, order, args):
        """GUI에 상태 메시지 전송"""
        try:
            if order == '주문내용':
                job = {'msg': f"{args['kind']} : {args['전략']} {args['code']} {args['name']} 주문수량:{args['quantity']}주 / 주문가:{args['price']}원 주문번호:{args.get('ordno', '')}"}
            elif order == '검색내용':
                job = {'msg': f"{args['kind']} : {args['전략']} {args['code']} {args['name']}"}
            elif order == '상태바':
                job = {'msg': args}
            else:
                return False
                
            if hasattr(self, 'config') and hasattr(self.config, 'gui_on') and self.config.gui_on:
                if 'msg' in self.qwork and self.qwork['msg'] is not None:
                    self.qwork['msg'].put(Work(order=order, job=job))
                    return True
            return False
        except Exception as e:
            logging.error(f"상태 메시지 전송 오류: {type(e).__name__} - {e}", exc_info=True)
            return False
    
    def safe_copy(self, obj):
        """객체의 안전한 복사본 생성"""
        with self._lock:
            try:
                return copy.deepcopy(obj)
            except:
                return obj

# 글로벌 메모리 싱글턴 인스턴스 생성
gm = ThreadSafeGlobalMemory()

def init_logger(log_path='log', filename='log_message'):
    """로거 초기화 함수"""
    try:
        full_path = get_path(log_path)
        
        # 설정 파일 읽기 또는 기본값 저장
        config_file = os.path.join(full_path, 'logging_config.json')
        success, config = load_json(config_file, log_config)
        
        if success:
            gm.json_config = config
            
            # 로그 파일 설정
            message_file = os.path.join(full_path, filename)
            gm.json_config['handlers']['file']['filename'] = message_file
            
            # 외부 라이브러리 활용 가능 여부 확인 및 적용
            try:
                from concurrent_log_handler import ConcurrentRotatingFileHandler
                gm.json_config['handlers']['file']['class'] = "concurrent_log_handler.ConcurrentRotatingFileHandler"
            except ImportError:
                # 외부 라이브러리가 없으면 기본 RotatingFileHandler 사용
                gm.json_config['handlers']['file']['class'] = "logging.handlers.RotatingFileHandler"
                
            # 업데이트된 설정 저장
            save_json(config_file, gm.json_config)
            
            # 로깅 설정 적용
            logging.config.dictConfig(gm.json_config)
            
            # 문제 방지를 위한 핸들러 닫기 및 정리
            logger = logging.getLogger()
            for handler in logger.handlers:
                if hasattr(handler, "close"):
                    handler.close()
                    
            return True
    except Exception as e:
        print(f"로거 초기화 오류: {type(e).__name__} - {e}")
        return False

# 기본 로그 설정
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
            'filename': "log_message",
            'formatter': 'detailed',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 9,
            'encoding': 'utf-8'
        }
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG'
    }
}

# 테스트 코드
if __name__ == "__main__":
    init_logger()
    logging.debug("ThreadSafe GlobalMemory 테스트 메시지")
    
    # 스레드 안전한 데이터 처리 테스트
    def test_thread(thread_id):
        for i in range(100):
            gm.set(f"thread_{thread_id}_{i}", i)
            logging.debug(f"스레드 {thread_id}: 키 thread_{thread_id}_{i}에 {i} 저장")
            
    threads = []
    for i in range(5):
        t = threading.Thread(target=test_thread, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    logging.debug("모든 스레드 작업 완료")
    
    try:
        1 / 0  # 예외 처리 테스트
    except Exception as e:
        logging.error("오류 발생!", exc_info=True) 