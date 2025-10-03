"""
독자적 클래스와 공용 변수 정의
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import logging.config
import logging.handlers
import os
import sys
import json
import time
import uuid

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

    def adjust_to_hoga_unit(price, round_up=None):
        hoga_unit = get_hoga_unit(price)
        remainder = price % hoga_unit
        if remainder != 0:
            if round_up is True:
                return price + (hoga_unit - remainder)
            elif round_up is False:
                return price - remainder
            else:  # 반올림
                if remainder >= hoga_unit / 2:
                    return price + (hoga_unit - remainder)
                else:
                    return price - remainder
        return price

    # 상한가/하한가 계산
    upper_limit = adjust_to_hoga_unit(current_price * 1.3, round_up=False)
    lower_limit = adjust_to_hoga_unit(current_price * 0.7, round_up=True)

    # 상한가/하한가 처리
    if position == 99:
        return int(upper_limit)
    elif position == -99:
        return int(lower_limit)

    # 현재 가격을 호가 단위에 맞게 조정
    adjusted_price = adjust_to_hoga_unit(current_price)
    
    if position == 0:
        return adjusted_price

    # 호가 단위에 맞게 조정된 가격에 position 적용
    hoga_unit = get_hoga_unit(adjusted_price)
    new_price = adjusted_price + (hoga_unit * position)

    # 상한가/하한가 범위 제한
    if new_price > upper_limit:
        new_price = upper_limit
    elif new_price < lower_limit:
        new_price = lower_limit

    # 호가 단위가 변경되는 경계값 처리
    new_hoga_unit = get_hoga_unit(new_price)
    if new_hoga_unit != hoga_unit:
        if position > 0:
            new_price = new_price - (new_price % new_hoga_unit)
        elif position < 0:
            new_price = new_price + (new_hoga_unit - (new_price % new_hoga_unit)) if new_price % new_hoga_unit != 0 else new_price

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

def profile_operation(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        if elapsed > 0.01:  # 10ms 이상 걸리는 작업 로깅
            logging.debug(f"[PROFILE] {func.__name__} took {elapsed:.3f} seconds {'*'*5}")
        return result
    return wrapper

# 주요 함수에 적용
@profile_operation
def some_critical_function():
    # 기존 코드
    pass

@dataclass
class Work:
    order: str              # 수신자가 실행할 함수명 또는 메세지(루프에서 인식할 조건)
    job: dict = field(default_factory={})              # 수신자가 실행할 함수에 전달할 데이터

@dataclass
class QWork:
    method: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    callback: str = None

@dataclass
class QData:
    sender : str = None
    method : str = None
    answer : bool = False
    args : tuple = field(default_factory=tuple)
    kwargs : dict = field(default_factory=dict)
    callback : str = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 고유 요청 ID

class SharedQueue:
    def __init__(self):
        import multiprocessing as mp
        self.request = mp.Queue()
        self.result = mp.Queue()
        #self.stream = mp.Queue()
        #self.payback = mp.Queue()

class FIDs:             # 실시간 조회 필드 아이디
    거래구분 = {
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
    }
    주문유형 = {
        '신규매수': 1,
        '신규매도': 2,
        '매수취소': 3,
        '매도취소': 4,
        '매수정정': 5,
        '매도정정': 6,
    }
    주문유형FID = {
        1: '신규매수',
        2: '신규매도',
        3: '매수취소',
        4: '매도취소',
        5: '매수정정',
        6: '매도정정'
    }
    주문구분list = [
        '매수',
        '매도',
        '매수취소',
        '매도취소',
        '매수정정',
        '매도정정'
    ]
    주식체결 = {
        '체결시간': 20,
        '현재가': 10,  # 체결가
        '전일대비': 11,
        '등락율': 12,
        '매도호가': 27, # (최우선)매도호가
        '매수호가': 28, # (최우선)매수호가
        '거래량': 15,  # +는 매수체결 -는 매도체결
        '누적거래량': 13,
        '누적거래대금': 14,
        '시가': 16,
        '고가': 17,
        '저가': 18,
    }
    장시작시간 = {
        '장운영구분': 215,
        '체결시간': 20,  # (HHMMSS) 현재시간
        '장시작예상잔여시간': 214,
    }
    주문체결 = {
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
        '매도수구분': 907,  # 매도(매도정정, 매도취소 포함)인 경우 1, 매수(매수정정, 매수취소 포함)인 경우 2
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
    }
    매도수구분 = {
        '1': '매도',
        '2': '매수',
        '매도': '1',
        '매수': '2'
    }
    잔고 = {
        '계좌번호': 9201,
        '종목코드': 9001,
        '종목명': 302,
        '현재가': 10,
        '보유수량': 930,
        '매입단가': 931,
        '총매입가': 932,
        '주문가능수량': 933,
        '당일순매수량': 945,
        '매도/매수구분': 946, 
        '당일총매도손익': 950,
        '(최우선)매도호가': 27,
        '(최우선)매수호가': 28,
        '기준가': 307,
        '손익율': 8019,
    }

class ScreenNumber:     # 화면번호
    화면 = {
        '잔고합산': '1020', '잔고목록': '1030', '손익합산': '1040', '손익목록': '1050', '일지합산': '1060', '일지목록': '1070', '예수금': '1080',
        '검색00': '3300', '검색01': '3301', '검색02': '3302', '검색03': '3303', '검색04': '3304',  # 마지막 자리 전략번호
        '검색05': '3305', '검색06': '3306', '검색07': '3307', '검색08': '3308', '검색09': '3309',  # 마지막 자리 전략번호
        '전략01': '4111', '전략02': '4211', '전략03': '4311', '전략04': '4411', '전략05': '4511',  # 두번째 자리 전략번호
        '전략06': '4611', '전략07': '4711', '전략08': '4811', '전략09': '4911', '전략00': '4011',  # 두번째 자리 전략번호
        '신규매수': '5511', '신규매도': '5512', '매수취소': '6611', '매도취소': '6612', '매수정정': '7711', '매도정정': '7712', 
        '수동매수': '8811', '수동매도': '8812', '수취매수': '9911', '수취매도': '9912',
        '실시간감시': '5100', '조건감시': '5200', '실시간조회': '5900', '장시작시간': '5910',
        '틱봉차트': '9110', '분봉차트': '9120', '일봉차트': '9130', '주봉차트': '9140', '월봉차트': '9150', '년봉차트': '9160',
    }
    # 화면번호 xx11 매수, xx12 매도 수정금지 및 사용 금지 - OnReceiveTrData() 처리
    # 화면번호 4xxxx 수정금지 screen.startswith('4') = '신규매수'   - OnReceiveTrData() 처리
    화면번호 = {
        '8811': '신규매수', '8812': '신규매도', '5511': '매수취소', '5512': '매도취소', '6611': '매수정정', '6612': '매도정정', '7711': '수동매수', '7712': '수동매도'
    }
    차트종류 = {
        'mo': '월봉', 'wk': '주봉', 'dy': '일봉', 'mi': '분봉', 'tk': '틱봉',
        '틱봉': 'tk', '분봉': 'mi', '일봉': 'dy', '주봉': 'wk', '월봉': 'mo'
    }
    차트TR = {
        'mo': 'OPT10083', 'wk': 'OPT10082', 'dy': 'OPT10081', 'mi': 'OPT10080', 'tk': 'OPT10079',
        '월봉차트': 'OPT10083', '주봉차트': 'OPT10082', '일봉차트': 'OPT10081', '분봉차트': 'OPT10080', '틱봉차트': 'OPT10079',
    }

class MarketStatus:     # 장 상태
    장종료 = '장 종료'
    장전시간외종가 = '장전 시간외 종가'
    장전동시호가 = '장전 동시호가'
    장운영중 = '장 운영 중'
    장마감동시호가 = '장마감 동시호가'
    장마감 = '장 마감'
    장후시간외종가 = '장후 시간외 종가'
    시간외단일가 = '시간외 단일가'
    장운영시간 = [장운영중, 장마감동시호가]
    주문가능시간 = [장전동시호가, 장운영중, 장마감동시호가]

class FilePath:         # 파일 경로
    path = get_path()

    LOG_PATH = 'log'
    LOG_FILE = f'log_message'
    LOG_JSON = 'logging_config.json'
    LOG_MAX_BYTES = 1024 * 1024 * 5

    DB_PATH = 'db'
    SCRIPT_PATH = 'script'
    CACHE_PATH = 'script/compiled_scripts'
    CONFIG_PATH = 'config'
    RESOURCE_PATH = 'resources'
    API_PATH = "C:/OpenAPI/data"
    IMAGE_PATH = "images"

    CONFIG_FILE = 'config.json'
    DEFINE_SETS_FILE = 'define_sets.json'
    STRATEGY_SETS_FILE = 'strategy_sets.json'
    HODINGS_FILE = 'holdings.json'
    COUNTER_TICKERS_FILE = 'counter_tickers.json'
    COUNTER_STRATEGY_FILE = 'counter_strategy.json'
    CHARTS_FILE = 'charts.json'
    SCRIPTS_FILE = 'scripts.json'
    FUNCTIONS_FILE = 'functions.json'

    config_file = os.path.join(get_path(CONFIG_PATH), CONFIG_FILE)
    define_sets_file = os.path.join(get_path(CONFIG_PATH), DEFINE_SETS_FILE)
    strategy_sets_file = os.path.join(get_path(CONFIG_PATH), STRATEGY_SETS_FILE)
    holdings_file = os.path.join(get_path(DB_PATH), HODINGS_FILE)
    counter_tickers_file = os.path.join(get_path(DB_PATH), COUNTER_TICKERS_FILE)
    counter_strategy_file = os.path.join(get_path(DB_PATH), COUNTER_STRATEGY_FILE)
    charts_file = os.path.join(get_path(DB_PATH), CHARTS_FILE)
    scripts_file = os.path.join(get_path(SCRIPT_PATH), SCRIPTS_FILE)
    functions_file = os.path.join(get_path(SCRIPT_PATH), FUNCTIONS_FILE)
    image_file = os.path.join(get_path(IMAGE_PATH), "Liberanimo_only.png")
    cache_path = os.path.join(get_path(CACHE_PATH))

class Constants:        # 상수 정의
    tax_rate = 0.0015   # 0.15%
    fee_real = 0.00015  # 0.03% 매도+매수 함 = 0.18%
    fee_sim = 0.0035    # 0.7% 매도+매수  합 = 0.85$

    NON_STRATEGY = '000 : 선택없음'
    BASIC_STRATEGY = '기본전략'
    WIDGET_MAP = {
        # 기본 설정
        '전략명칭': 'ledStrategyName',
        '매수적용': 'chkConditionBuy',
        '매수전략': 'ledConditionBuy',
        '매도적용': 'chkConditionSell',
        '매도전략': 'ledConditionSell',

        '체결횟수': 'spbTrade',
        '종목제한': 'spbStock',
        '보유제한': 'spbHold',
        '운영시간': 'rbUseTime',
        '설정시간': 'rbPeriod',
        '시작시간': 'tedStart',
        '종료시간': 'tedStop',
        '매도도같이적용': 'chkSellSame',
        '로스컷': 'chkLossCut',
        '로스컷율': 'dsbLossCut',
        '로스컷시장가': 'rbLossCutMarket',
        '로스컷지정가': 'rbLossCutLimit',
        '로스컷지정가율': 'dsbLossCutLimit',
        '로스컷상하': 'cbLossCutUpDown',
        '당일청산': 'chkClear',
        '청산시간': 'tedClear',
        '청산시장가': 'rbClearMarket',
        '청산지정가': 'rbClearLimit',
        '청산호가': 'spbClearHoga',

        # 매수/매도 제한
        '중복매수금지': 'chkNoDup',
        '매수취소': 'chkBuyCancel',
        '매수지연초': 'spbBuyCancel',
        '매도취소': 'chkSellCancel',
        '매도지연초': 'spbSellCancel',

        # 매수 설정
        '매수시장가': 'rbBuyMarket',
        '매수지정가': 'rbBuyLimit',
        '매수호가': 'spbBuyHoga',
        '투자금': 'rbMoney',
        '투자금액': 'spbMoney',
        '매수량': 'rbQuantity',
        '매수수량': 'spbQuantity',

        # 매도 설정
        '매도시장가': 'rbSellMarket',
        '매도지정가': 'rbSellLimit',
        '매도호가': 'spbSellHoga',
        '이익실현': 'chkProfit',
        '이익실현율': 'dsbProfit',
        '이익보존': 'chkKeep',
        '이익보존율': 'dsbKeep',
        '감시적용': 'chkWatchOn',
        '감시시작율': 'dsbTrailingStart',
        '스탑주문율': 'dsbTrailingStop',
        '손실제한': 'chkLossLimit',
        '손실제한율': 'dsbLossLimit',

        # 스크립트 전략
        '매수스크립트적용': 'chkScriptBuy',
        '매수스크립트': 'ledScriptBuy',
        '매수스크립트AND': 'rbScriptBuyAnd',
        '매수스크립트OR': 'rbScriptBuyOr',
        '매도스크립트적용': 'chkScriptSell',
        '매도스크립트': 'ledScriptSell',
        '매도스크립트AND': 'rbScriptSellAnd',
        '매도스크립트OR': 'rbScriptSellOr',

        '남은횟수': 'xxremain',
    }
    DEFAULT_STRATEGY_SETS = {
        '전략명칭': BASIC_STRATEGY,
        '매수적용': False,
        '매수전략': '',
        '매도적용': False,
        '매도전략': '',

        '체결횟수': 1000,
        '종목제한': 10,
        '보유제한': 10,
        '운영시간': True,
        '설정시간': False,
        '시작시간': '09:00',
        '종료시간': '15:00',
        '매도도같이적용': True,
        '로스컷': False,
        '로스컷율': 0.0,
        '로스컷시장가': True,
        '로스컷지정가': False,
        '로스컷지정가율': 0.0,
        '로스컷상하': '이상',
        '당일청산': False,
        '청산시간': '15:18',
        '청산시장가': True,
        '청산지정가': False,
        '청산호가': 0,
        '중복매수금지': True,
        '매수취소': False,
        '매수지연초': 0,
        '매도취소': False,
        '매도지연초': 0,

        '매수시장가': True,
        '매수지정가': False,
        '매수호가': 0,
        '투자금': True,
        '투자금액': 100000,
        '매수량': False,
        '매수수량': 1,

        '매도시장가': True,
        '매도지정가': False,
        '매도호가': 0,
        '이익실현': True,
        '이익실현율': 3.0,
        '이익보존': False,
        '이익보존율': 0.0,
        '감시적용': False,
        '감시시작율': 0.0,
        '스탑주문율': 0.0,
        '손실제한': True,
        '손실제한율': 3.0,

        '매수스크립트적용': False,
        '매수스크립트': '',
        '매수스크립트AND': True,
        '매수스크립트OR': False,
        '매도스크립트적용': False,
        '매도스크립트': '', '매도스크립트AND': True,
        '매도스크립트OR': False,

        '남은횟수': 1000,
    }
    DEFAULT_DEFINE_SETS = {'전략명칭': BASIC_STRATEGY}

    # 색상정의
    list전일가대비 = ['현재가', '시가', '고가', '저가', '등락율']
    list양음가대비 = ['평가손익', '수익률(%)', '전일대비', '손익율', '당일매도손익', '손익금액', '수익률']

    # TR OUTPUT 정의
    MI_OUTPUT = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
    DY_OUTPUT = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

class SimTicker:
    ticker = {
        "000100": { "종목명": "유한양행", "전일가": 131600 },
        "000660": { "종목명": "SK하이닉스", "전일가": 192400 },
        "003670": { "종목명": "포스코퓨처엠", "전일가": 142900 },
        "004020": { "종목명": "현대제철", "전일가": 31900 },
        "005010": { "종목명": "휴스틸", "전일가": 5670 },
        "005490": { "종목명": "POSCO홀딩스", "전일가": 319250 },
        "005930": { "종목명": "삼성전자", "전일가": 54300 },
        "006880": { "종목명": "신송홀딩스", "전일가": 8200 },
        "008970": { "종목명": "동양철관", "전일가": 1065 },
        "009520": { "종목명": "포스코엠텍", "전일가": 14561 },
        "009540": { "종목명": "HD한국조선해양", "전일가": 251000 },
        "010140": { "종목명": "삼성중공업", "전일가": 15010 },
        "012450": { "종목명": "한화에어로스페이스", "전일가": 717000 },
        "022100": { "종목명": "포스코DX", "전일가": 26441 },
        "036460": { "종목명": "한국가스공사", "전일가": 40100 },
        "042660": { "종목명": "한화오션", "전일가": 84600 },
        "047050": { "종목명": "포스코인터내셔널", "전일가": 61000 },
        "047810": { "종목명": "한국항공우주", "전일가": 75800 },
        "051910": { "종목명": "LG화학", "전일가": 254000 },
        "058430": { "종목명": "포스코스틸리온", "전일가": 47050 },
        "071090": { "종목명": "하이스틸", "전일가": 4650 },
        "071280": { "종목명": "로체시스템즈", "전일가": 16060 },
        "079550": { "종목명": "LIG넥스원", "전일가": 320500 },
        "092790": { "종목명": "넥스틸", "전일가": 14430 },
        "097230": { "종목명": "HJ중공업", "전일가": 7793 },
        "103140": { "종목명": "풍산", "전일가": 66400 },
        "163280": { "종목명": "에어레인", "전일가": 15160 },
        "170920": { "종목명": "엘티씨", "전일가": 10790 },
        "189300": { "종목명": "인텔리안테크", "전일가": 42500 },
        "267270": { "종목명": "HD현대건설기계", "전일가": 77000 },
        "272210": { "종목명": "한화시스템", "전일가": 35250 },
        "310210": { "종목명": "보로노이", "전일가": 127800 },
        "314930": { "종목명": "바이오다인", "전일가": 15580 },
    }

## Define Global Constants **********************************************************************
class DefineConstants:  # 글로벌 상수 정의
    def __init__(self):
        self.WAIT_SEC = 10
        self.INTERVAL_NORMAL = 0.01
        self.INTERVAL_FAST = 0.005
        self.INTERVAL_VERY_FAST = 0.001
        self.INTERVAL_SLOW = 0.05
        self.INTERVAL_BATCH = 0.011
        self.INTERVAL_GUI = 199 #milliseconds
        self.TODAY = datetime.now().strftime('%Y-%m-%d')
        self.ToDay = datetime.now().strftime('%Y%m%d')
        self.BEFORE_TEN_YEARS = (datetime.now() - timedelta(days=3650)).strftime('%Y-%m-%d')
        self.BEFORE_ONE_MONTH = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        self.TOAST_TIME = 5000  # 밀리초

        self.const = Constants()
        self.fid = FIDs()
        self.scr = ScreenNumber()
        self.fp = FilePath()
        self.ms = MarketStatus()
        self.sim = SimTicker()
        self.ticks = {
            '틱봉': ['30'],
            '분봉': ['1', '3', '5', '10', '15', '30', '60'],
            '일봉': [],
            '주봉': [],
            '월봉': [],
        }
        self.log_config = {
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
dc = DefineConstants()

## Define Global memory *************************************************************************
class GlobalMemory:      # 글로벌 메모리 정의
    def __init__(self):
        self.connected = False
        self.sim_on = True
        self.sim_no = 0
        self.gui_on = False
        self.ready = False
        self.log_level = logging.DEBUG
        self.server = '1'
        self.account = ''

        self.main = None
        self.admin = None
        self.prx = None
        self.rcv = None # RealDataUpdater
        self.gui = None
        self.pri = None # PriceUpdater
        self.api = None
        self.dbm = None
        self.cts = None
        self.ctu = None
        self.evl = None
        self.odc = None
        self.odr = None # 주문 결과 처리
        self.scm = None # 스크립트 매니저

        self.price_q = None    # ThreadSafeQueue()
        self.eval_q = None # ThreadSafeQueue()
        self.order_q = None # ThreadSafeQueue()
        self.setter_q = None # ThreadSafeQueue()
        self.chart_q = None # ThreadSafeQueue()

        self.tickers_set = set() # 틱차트 가져오기

        self.toast = None
        self.json_config = dc.log_config

        self.list계좌콤보 = []
        self.list전략콤보 = []
        self.list전략튜플 = []
        self.list스크립트 = []
        self.dict종목정보 = None     # ThreadSafeDict() # 종목정보 = {종목코드: {'종목명': 종목명, '현재가': 현재가, '전일가': 전일가}}
        #self.dict주문대기종목 = None # ThreadSafeDict() # 주문대기종목 = {종목코드: {'idx': 전략번호, 'kind': 구분}}

        self.qwork = {} # {'gui': Queue(), 'msg': Queue()}
    
        self.shared_qes = {
            'api': SharedQueue(),
            'dbm': SharedQueue(),
            'prx': SharedQueue(),
            'rcv': SharedQueue(),
        }

        self.잔고합산 = None # TableManager
        self.잔고목록 = None # TableManager
        self.매수검색목록 = None # TableManager
        self.매도검색목록 = None # TableManager
        self.주문진행목록 = None # TableManager
        self.예수금 = None # TableManager
        self.일지합산 = None # TableManager
        self.일지목록 = None # TableManager
        self.체결목록 = None # TableManager
        self.손익목록 = None # TableManager
        self.전략정의 = None # TableManager
        self.매매목록 = None # TableManager
        self.스크립트 = None # TableManager
        self.차트자료 = None # TableManager
        self.당일종목 = None # TableManager
        self.수동종목 = None # TableManager
        self.l2잔고합산_copy = None
        self.l2손익합산 = 0

        # 조건목록 그룹박스 체크상태 (종목 자동 삭제 역할)
        self.gbx_buy_checked = False
        self.gbx_sell_checked = False
            
        # 서버 호출 제한 체크
        self.req = None # 요청 카운터# TimeLimiter(sec=5, min=100, hour=1000) # 1초당 5회 제한 (CommRqData + CommKwRqData + SendCondition 포함) - 1 초마다 리셋 됨
        self.ord = None # 주문 카운터# TimeLimiter(sec=5, min=100, hour=1000) # 1초당 5회 제한 (SendOrder + SendOrderFor) - 1 초마다 리셋 됨
        self.counter = None # 카운터 전략별, 종목별 매수 횟수 제한
    
        self.strategy_row = None
        self.basic_strategy = None
        self.실행전략 = None # json
        self.설정전략 = None # json
        self.매수문자열 = ''
        self.매도문자열 = ''
        self.set종목감시 = set()
        self.set조건감시 = set() 
        #self.set주문종목 = None # ThreadSafeSet()
        self.수수료율 = 0.0
        self.세금율 = 0.0
        self.holdings = {}
        self.admin_init = False
        self.stg_run = True
gm = GlobalMemory()

def init_logger(log_path=dc.fp.LOG_PATH, filename=dc.fp.LOG_FILE):
    full_path = get_path(log_path)
    
    # 설정 파일 읽기 또는 기본값 저장
    config_file = os.path.join(full_path, dc.fp.LOG_JSON)
    _, gm.json_config = load_json(config_file, dc.log_config)

    # 로그 파일 설정
    message_file = os.path.join(full_path, dc.fp.LOG_FILE)
    gm.json_config['handlers']['file']['filename'] = message_file

    # 외부 라이브러리 활용 가능 여부 확인 및 적용 및 공통 클래스 선택
    try:
        from concurrent_log_handler import ConcurrentRotatingFileHandler # pip install concurrent-log-handler
        selected_handler_class = "concurrent_log_handler.ConcurrentRotatingFileHandler"
    except ImportError:
        # 외부 라이브러리가 없으면 기본 RotatingFileHandler 사용
        selected_handler_class = "logging.handlers.RotatingFileHandler"

    gm.json_config['handlers']['file']['class'] = selected_handler_class

    # 전략복기 전용 핸들러/로거 보장 및 설정
    gm.json_config.setdefault('handlers', {})
    gm.json_config.setdefault('loggers', {})

    if 'replay_file' not in gm.json_config['handlers']:
        gm.json_config['handlers']['replay_file'] = {
            'class': selected_handler_class,
            'filename': "",
            'formatter': 'detailed',
            'maxBytes': gm.json_config['handlers']['file'].get('maxBytes', 1024 * 1024 * 1),
            'backupCount': gm.json_config['handlers']['file'].get('backupCount', 9),
            'encoding': 'utf-8'
        }

    replay_file = os.path.join(full_path, "script_log")
    gm.json_config['handlers']['replay_file']['filename'] = replay_file
    gm.json_config['handlers']['replay_file']['class'] = selected_handler_class

    if 'replay' not in gm.json_config['loggers']:
        gm.json_config['loggers']['replay'] = {
            'handlers': ['replay_file'],
            'level': 'INFO',
            'propagate': False
        }

    # 업데이트된 설정 저장
    save_json(config_file, gm.json_config)
    
    # 로깅 설정 적용
    logging.config.dictConfig(gm.json_config)

    # 문제 방지를 위한 핸들러 닫기 및 정리
    logger = logging.getLogger()
    for handler in logger.handlers:
        if hasattr(handler, "close"):
            handler.close()

def com_market_status():
    now = datetime.now()
    time = int(now.strftime("%H%M%S"))
    if time < 83000: return dc.ms.장종료
    elif time < 84000: return dc.ms.장전시간외종가
    elif time < 90000: return dc.ms.장전동시호가
    elif time < 152000: return dc.ms.장운영중
    elif time < 153000: return dc.ms.장마감동시호가
    elif time < 154000: return dc.ms.장마감
    elif time < 160000: return dc.ms.장후시간외종가
    elif time < 180000: return dc.ms.시간외단일가
    else: return dc.ms.장종료

# init_logger 사용 예시
if __name__ == "__main__":
    init_logger()
    logging.debug("This is an info message.")
    try:
        1 / 0  # ZeroDivisionError 예제
    except Exception as e:
        logging.error("An error occurred!", exc_info=True)
