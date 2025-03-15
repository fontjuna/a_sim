"""
독자적 클래스와 공용 변수 정의
"""

from dataclasses import dataclass, field
import logging
import logging.config
import logging.handlers
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
    DEFINE_SETS_FILE = 'define_sets.json'
    STRATEGY_SETS_FILE = 'strategy_sets.json'
    HODINGS_FILE = 'holdings.json'
    COUNTER_TICKERS_FILE = 'counter_tickers.json'
    COUNTER_STRATEGY_FILE = 'counter_strategy.json'
    CHARTS_FILE = 'charts.json'

    config_file = os.path.join(get_path(CONFIG_PATH), CONFIG_FILE)
    define_sets_file = os.path.join(get_path(CONFIG_PATH), DEFINE_SETS_FILE)
    strategy_sets_file = os.path.join(get_path(CONFIG_PATH), STRATEGY_SETS_FILE)
    holdings_file = os.path.join(get_path(DB_PATH), HODINGS_FILE)
    counter_tickers_file = os.path.join(get_path(DB_PATH), COUNTER_TICKERS_FILE)
    counter_strategy_file = os.path.join(get_path(DB_PATH), COUNTER_STRATEGY_FILE)
    charts_file = os.path.join(get_path(DB_PATH), CHARTS_FILE)

@dataclass
class Constants:
    tax_rate = 0.0015
    fee_real = 0.0015
    fee_sim = 0.0035

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
        '예수금': 'rbDeposit',
        '예수금율': 'dsbDeposit',

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
        '매도도같이적용': False,
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
        '예수금': False,
        '예수금율': 0.0,

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

        '남은횟수': 1000,
    }
    DEFAULT_DEFINE_SETS = [
        {'전략':'전략00', '전략적용': False, '전략명칭': BASIC_STRATEGY},
        *[{'전략':f'전략{seq:02d}', '전략적용': False, '전략명칭': ''}
          for seq in range(1,11)]
    ]

    # 색상정의
    list전일가대비 = ['현재가', '시가', '고가', '저가', '등락율']
    list양음가대비 = ['평가손익', '수익률(%)', '전일대비', '손익율', '당일매도손익', '손익금액', '수익률']

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

@dataclass
class DefineConstants:
    const = Constants()
    fid = FIDs()
    td = TimeDefinition()
    scr = ScreenNumber()
    fp = FilePath()
    log_config = log_config
dc = DefineConstants()

class DefineTbl:
    hd잔고합산 = {
        '키': '순번',
        '정수': ['순번','총매입금액', '총평가금액', '추정예탁자산', '총평가손익금액'],
        '실수': ['총수익률(%)'],
    }
    hd잔고합산.update({
        '컬럼': hd잔고합산['정수'] + hd잔고합산['실수'] # l2잔고합산
    })

    hd잔고목록 = {
        '키': '종목번호',
        '정수': ["보유수량", "매입가", "매입금액", "현재가", "평가금액", "평가손익", '시가', '고가', '저가', '전일대비', \
                        '누적거래량', '거래량', '매도가능수량', '최고가', '감시', '보존', '상태', '매수수량', '매수가', '매수금액'],
        '실수': ["수익률(%)", "등락율", '이익보존율', '감시시작율'],
        '컬럼': ["종목번호", "종목명", "보유수량", "매입가", "매입금액", "현재가", "평가금액", "평가손익", "수익률(%)"],
        '추가': ['시가', '고가', '저가', '전일대비', "등락율", '누적거래량', '거래량', '최고가', '매수수량', '매수가', '매수금액',\
                        '보존', '이익보존율', '감시', '감시시작율', '상태', '전략', '매수전략', '전략명칭', '매수일자', '매수시간', '매수번호'], # 상태: 0-일반, 1-매수, 2-매도
    }
    hd잔고목록.update({
        '헤더': ["전략"] + hd잔고목록['컬럼'] + ["매수일자", "매수시간", '등락율', '전일대비', '누적거래량'],
        '확장': ['전략'] + hd잔고목록['컬럼'] + hd잔고목록['추가'],
    })

    hd조건목록 = {
        '키': '종목코드',
        '정수': ['현재가', '누적거래량', '시가', '고가', '저가', '전략번호', '주문수량', '체결량', '미체결수량'],
        '실수': ['등락율'],
        '추가': ['전송번호', '주문번호', '주문유형', '전략명칭', '주문수량', '체결량', '미체결수량', '원주문번호'],
    }
    hd조건목록.update({
        '컬럼': ['종목코드', '종목명'] + hd조건목록['실수'] + hd조건목록['정수'][:1],
    })
    hd조건목록.update({
        '확장': ['전략', '전략번호'] + hd조건목록['컬럼'] + hd조건목록['추가'],
        '헤더': ['전략', '종목코드', '종목명' ],
    })

    hd손익목록 = {
        '키': '종목코드',
        '정수': ['체결량', '매입단가', '체결가', '당일매도손익', '당일매매수수료', '당일매매세금'],
        '실수': ['손익율'],
    }
    hd손익목록.update({
        '컬럼': ['종목코드', '종목명'] + hd손익목록['정수'][:4] + hd손익목록['실수'] + hd손익목록['정수'][4:], # l2손익목록
    })

    hd접수목록 = hd조건목록.copy()
    hd접수목록.update({'키': '주문번호'})

    hd예수금 = {
        '키': '순번',
        '정수': ['순번', 'd+1추정예수금', 'd+1매도매수정산금', 'd+1미수변제소요금', 'd+1출금가능금액',\
                      'd+2추정예수금', 'd+2매도매수정산금', 'd+2미수변제소요금', 'd+2출금가능금액',\
                      '예수금', '주식증거금현금', '미수확보금', '권리대용금',\
                      '20%종목주문가능금액', '30%종목주문가능금액', '40%종목주문가능금액', '100%종목주문가능금액',\
                      '주문가능금액', '출금가능금액', '현금미수금'],
        '실수': [],
    }
    hd예수금.update({
        '컬럼': hd예수금['정수'],
    })

    hd일지합산 = {
        '키': '순번',
        '정수': ['순번', '총매수금액', '총매도금액', '총수수료_세금', '총정산금액', '총손익금액'],
        '실수': ['총수익률'],
    }
    hd일지합산.update({
        '컬럼': hd일지합산['정수'] + hd일지합산['실수'],
    })

    hd일지목록 = {
        '키': '종목코드',
        '정수': ['매수금액','매도금액', '손익금액', '매수수량', '매수평균가', '매도수량',  '매도평균가', '수수료_제세금'],
        '실수': ['수익률'],
    }
    hd일지목록.update({
        '컬럼': ['종목코드', '종목명'] + hd일지목록['정수'][:3] + hd일지목록['실수'] + hd일지목록['정수'][3:],
    })

    hd체결목록 = {
        '키': '종목번호',
        '정수': ['매수수량', '매수가', '매수금액', '매도수량', '매도가', '매도금액', '손익금액', '제비용'],
        '실수': ['손익율'],
        '컬럼': ['전략', '매수일자', '매수시간', '종목번호', '종목명', '손익금액', '손익율', '매수수량', '매수금액', '매도수량', '매도금액', \
                        '매수가', '매도가', '제비용', '매도일자', '매도시간', '매수번호', '매도번호', '매수전략', '전략명칭'],
    }

    hd전략정의 = {
            '키': '전략명칭',
            '정수': ['체결횟수', '종목제한', '보유제한', '청산호가', '매수지연초', '매도지연초', '매수호가', '투자금액', '매도호가', '남은횟수'],
            '실수': ['예수금율', '이익실현율', '이익보존율', '감시시작율','스탑주문율', '손실제한율'],
            '컬럼': dc.const.WIDGET_MAP.keys(), # 컬럼명
            '헤더': ['전략명칭', '투자금액', '매수적용', '매수전략', '매도적용', '매도전략', '이익실현율', '이익보존율', '손실제한율', '감시적용', '감시시작율', '스탑주문율'],
        }

@dataclass
class GlobalConfig:
    sim_on = True
    gui_on = False
    ready = False
    log_level = logging.DEBUG
    server = '1'
    account = ''
    ready = False
    toast = None
    fee_rate = 0.0
    tax_rate = 0.0

@dataclass
class GuiConfig:
    list계좌콤보 = []
    list전략콤보 = []
    list전략튜플 = []

@dataclass
class Processes:
    main = None
    gui = None
    api = None
    admin = None

@dataclass
class QDict:
    qdict: dict = field(default_factory=lambda: {
        'aaa': Message(),
        's00': Message(),
        's01': Message(),
        's02': Message(),
        's03': Message(),
        's04': Message(),
        's05': Message(),
        'dbm': Message(),
    })

@dataclass
class GlobalMemory:
    toast = None
    json_config = {'level': logging.DEBUG, }
    config = GlobalConfig()
    gui = GuiConfig()
    pro = Processes()
    qdict = QDict().qdict
    tbl = DefineTbl()
    잔고합산 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd잔고합산))
    잔고목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd잔고목록))
    조건목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd조건목록))
    손익목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd손익목록))
    접수목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd접수목록))
    예수금 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd예수금))
    일지합산 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd일지합산))
    일지목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd일지목록))
    체결목록 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd체결목록))
    전략정의 = None # TableManager = field(default_factory=TableManager(gm.tbl.hd전략정의))
    잔고합산_copy = None
    strategy_row = None
    전략설정 = None # json
    전략쓰레드 = None
    # 서버 호출 제한 체크
    req = None # 요청 카운터# TimeLimiter(sec=5, min=100, hour=1000) # 1초당 5회 제한 (CommRqData + CommKwRqData + SendCondition 포함) - 1 초마다 리셋 됨
    ord = None # 주문 카운터# TimeLimiter(sec=5, min=100, hour=1000) # 1초당 5회 제한 (SendOrder + SendOrderFor) - 1 초마다 리셋 됨
    dict잔고종목감시 = {}
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
