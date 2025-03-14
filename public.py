"""
독자적 클래스와 공용 변수 정의
"""

import logging
import logging.config
import logging.handlers
from dataclasses import dataclass, field
import os
import sys
import json
from datetime import datetime
import multiprocessing as mp

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

    if position == 0:
        return current_price

    hoga_unit = get_hoga_unit(current_price)
    new_price = current_price + (hoga_unit * position)

    # 호가 단위가 변경되는 경계값 처리
    if position > 0 and get_hoga_unit(new_price) != hoga_unit:
        return new_price - (new_price % get_hoga_unit(new_price))
    elif position < 0 and get_hoga_unit(new_price) != hoga_unit:
        return new_price + (get_hoga_unit(new_price) - (new_price % get_hoga_unit(new_price)))

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
    job: dict               # 수신자가 실행할 함수에 전달할 데이터

@dataclass
class Answer:
    sender: str             # 송신자 이름
    order: str             # 수신자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    job: dict              # 수신자에게 전달할 데이터
    qid: str = None        # 동기식 요청에 대한 답변

@dataclass
class Reply:
    sender: str             # 송신자 이름
    order: str             # 수신자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    job: dict              # 수신자에게 전달할 데이터
    qid: str = None        # TR 요청에 대한 답변

@dataclass
class Message:
    request: mp.Queue = field(default_factory=mp.Queue)
    answer: mp.Queue = field(default_factory=mp.Queue)
    reply: mp.Queue = field(default_factory=mp.Queue)

@dataclass
class FIDs:
    거래구분: dict = field(default_factory=lambda: {
        '지정가': '00',
        '시장가': '03',
        '조건부지정가': '05',
        '최유리지정가': '06',
        '최우선지정가': '07',
        '지정가IOC': '10',
        '시장가IOC': '13',
        '최유리IOC': '16',
        '지정가FOK': '20',
        '시장가FOK': '23',
        '최유리FOK': '26',
        '장전시간외종가': '61',
        '시간외단일가매매': '62',
        '장후시간외종가': '81',
    })  

    주문유형: dict = field(default_factory=lambda: {
        '신규매수': 1,
        '신규매도': 2,
        '매수취소': 3,
        '매도취소': 4,
        '매수정정': 5,
        '매도정정': 6,
    })

    주식체결: dict = field(default_factory=lambda: {
        '체결시간': 20,
        '현재가': 10,  # 체결가
        '전일대비': 11,
        '등락율': 12,
        # '(최우선)매도호가': 27,
        # '(최우선)매수호가': 28,
        '거래량': 15,  # +는 매수체결 -는 매도체결
        '누적거래량': 13,
        '누적거래대금': 14,
        '시가': 16,
        '고가': 17,
        '저가': 18,
        # '전일대비기호': 25,
        # '전일거래량대비': 26,
        # '거래대금증감': 29,
        # '전일거래량대비': 30,
        # '거래회전율': 31,
        # '거래비용': 32,
        # '체결강도': 228,
        # '시가총액(억)': 311,
        # '장구분': 290,
        # 'KO접근도': 691,
        # '상한가발생시간': 567,
        # '하한가발생시간': 568,
        # '전일 동시간 거래량 비율': 851,
    })

    장시작시간: dict = field(default_factory=lambda: {
        '장운영구분': 215,
        '체결시간': 20,  # (HHMMSS) 현재시간
        '장시작예상잔여시간': 214,
    })

    주문체결: dict = field(default_factory=lambda: {
        '계좌번호': 9201,
        '주문번호': 9203,
        # '관리자사번': 9205,
        '종목코드': 9001,
        # '주문업무분류': 912, #(jj:주식주문)
        '주문상태': 913,  # (접수, 확인, 체결, 거부) (10:원주문, 11:정정주문, 12:취소주문, 20:주문확인, 21:정정확인, 22:취소확인, 90,92:주문거부) #https://bbn.kiwoom.com/bbn.openAPIQnaBbsDetail.do
        '종목명': 302,
        '주문수량': 900,
        '주문가격': 901,
        '미체결수량': 902,
        '체결누계금액': 903,
        '원주문번호': 904,
        '주문구분': 905,  # (+매수, -매도, -매도정정, +매수정정, 매수취소, 매도취소)
        '매매구분': 906,  # (보통, 시장가등)
        '매도수구분': 907,  # 매도(매도정정, 매도취도 포함)인 경우 1, 매수(매수정정, 매수취소 포함)인 경우 2
        '주문/체결시간': 908,  # (HHMMSS)
        '체결번호': 909,
        '체결가': 910,
        '체결량': 911,
        '현재가': 10,
        # '(최우선)매도호가': 27,
        # '(최우선)매수호가': 28,
        '단위체결가': 914,
        '단위체결량': 915,
        # '당일매매수수료': 938,
        # '당일매매세금': 939,
        # '거부사유': 919,
        # '화면번호': 920,
        # '터미널번호': 921,
        # '신용구분(실시간 체결용)': 922,
        # '대출일(실시간 체결용)': 923,
    })

    매도수구분: dict = field(default_factory=lambda: {
        '1': '매도',
        '2': '매수',
        '매도': '1',
        '매수': '2'
    })

    잔고: dict = field(default_factory=lambda: {
        '계좌번호': 9201,
        '종목코드': 9001,
        '종목명': 302,
        '현재가': 10,
        '보유수량': 930,
        '매입단가': 931,
        '총매입가': 932,
        '주문가능수량': 933,
        '당일순매수량': 945,
        '매도매수구분': 946,
        '당일총매도손익': 950,
        '예수금': 951,
        '(최우선)매도호가': 27,
        '(최우선)매수호가': 28,
        '기준가': 307,
        '손익율': 8019,
    })

@dataclass
class TimeDefinition:
    WAIT_SEC: int = 10
    RUN_INTERVAL: int = 0.01
    TODAY: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d'))
    ToDay: str = field(default_factory=lambda: datetime.now().strftime('%Y%m%d'))
    TOAST_TIME: int = 5000  # 밀리초

@dataclass
class ScreenNumber:
    화면: dict = field(default_factory=lambda: {
        '잔고합산': '1020', '잔고목록': '1030', '손익합산': '1040', '손익목록': '1050', '일지합산': '1060', '일지목록': '1070', '예수금': '1080',
        '검색00': '3300', '검색01': '3301', '검색02': '3302', '검색03': '3303', '검색04': '3304',  # 마지막 자리 전략번호
        '검색05': '3305', '검색06': '3306', '검색07': '3307', '검색08': '3308', '검색09': '3309',  # 마지막 자리 전략번호
        '전략01': '4111', '전략02': '4211', '전략03': '4311', '전략04': '4411', '전략05': '4511',  # 두번째 자리 전략번호
        '전략06': '4611', '전략07': '4711', '전략08': '4811', '전략09': '4911', '전략10': '4011',  # 두번째 자리 전략번호
        '신규매수': '8811', '신규매도': '8812', '매수취소': '5511', '매도취소': '5512', '매수정정': '6611', '매도정정': '6612',
        '실시간감시': '5100', '조건감시': '5200', '실시간조회': '5900', '장시작시간': '5910'
    })
    # 화면번호 xx11 매수, xx12 매도 수정금지 및 사용 금지 - OnReceiveTrData() 처리
    # 화면번호 4xxxx 수정금지 screen.startswith('4') = '신규매수'   - OnReceiveTrData() 처리
    화면번호: dict = field(default_factory=lambda: {
        '8811': '신규매수', '8812': '신규매도', '5511': '매수취소', '5512': '매도취소', '6611': '매수정정', '6612': '매도정정'
    })

class FilePath:
    path = get_path()

    LOG_PATH = 'log'
    LOG_FILE = f'log_{datetime.now().strftime("%Y%m%d")}'
    LOG_JSON = 'logging_config.json'
    LOG_MAX_BYTES = 1024 * 1024 * 5

    DB_PATH = 'db'
    CONFIG_PATH = 'config'
    RESOURCE_PATH = 'resources'
    API_PATH = "C:/OpenAPI/data"

    CONFIG_FILE = 'config.json'
    DECASETS_FILE = 'deca_sets.json'
    STRATEGY_FILE = 'strategy_sets.json'
    HODINGS_FILE = 'holdings.json'
    COUNTER_TICKERS_FILE = 'counter_tickers.json'
    COUNTER_STRATEGY_FILE = 'counter_strategy.json'
    CHARTS_FILE = 'charts.json'

    config_file = os.path.join(get_path(CONFIG_PATH), CONFIG_FILE)
    decaset_file = os.path.join(get_path(CONFIG_PATH), DECASETS_FILE)
    strategy_file = os.path.join(get_path(CONFIG_PATH), STRATEGY_FILE)
    holdings_file = os.path.join(get_path(DB_PATH), HODINGS_FILE)
    counter_tickers_file = os.path.join(get_path(DB_PATH), COUNTER_TICKERS_FILE)
    counter_strategy_file = os.path.join(get_path(DB_PATH), COUNTER_STRATEGY_FILE)
    charts_file = os.path.join(get_path(DB_PATH), CHARTS_FILE)

@dataclass
class DefineConstants:
    fid = FIDs()
    td = TimeDefinition()
    scr = ScreenNumber()
    fp = FilePath()
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
                'formatter': 'detailed',
                'level': 'DEBUG'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': "log_yyyymmdd_00.log",
                'formatter': 'detailed',
                'maxBytes': 1024 * 1024 * 5,
                'backupCount': 10,
                'encoding': 'utf-8',
                'level': 'DEBUG'
            }
        },
        'root': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG'
        }
    }
dc = DefineConstants()

@dataclass
class GlobalMemory:
    config = {
        'gui_on': False,
        'ready': False,
        'log_level': logging.DEBUG,
    }
    proc = {
        'main': None,
        'gui': None,
        'msg': None,
    }
    qdict = {}

gm = GlobalMemory()

def init_logger(log_path=dc.fp.LOG_PATH, filename=dc.fp.LOG_FILE, max_bytes=dc.fp.LOG_MAX_BYTES):
    config_path = os.path.join(get_path(log_path), dc.fp.LOG_JSON)
    result, config = load_json(config_path, dc.log_config)
    
    # 현재 로그 파일 번호 확인
    import glob
    pattern = os.path.join(log_path, f"{filename}_??.log")
    files = glob.glob(pattern)
    if not files:
        next_num = 0
    else:
        current_file = max(files)  # 가장 최근 파일
        current_size = os.path.getsize(current_file)
        current_num = int(current_file[-6:-4])
        next_num = current_num if current_size < max_bytes else current_num + 1
    
    config['handlers']['file']['filename'] = os.path.join(log_path, f"{filename}_{next_num:02d}.log")
    config['handlers']['file']['maxBytes'] = max_bytes
    
    logging.config.dictConfig(config)

# 사용 예시
if __name__ == "__main__":
    init_logger()
    logging.debug("This is an info message.")
    try:
        1 / 0  # ZeroDivisionError 예제
    except Exception as e:
        logging.error("An error occurred!", exc_info=True)
