from classes import *
from public import *
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
from PyQt5.QAxContainer import QAxWidget
import multiprocessing as mp
import pandas as pd
import logging
import sys
import time
import random
import math
import numpy as np


real_thread = {}
cond_thread = {}
chejan_thread = []
cond_data_list =  [('079', '전고돌파3분5억-매수'), ('080', '전고돌파3분5억-매도'), ('024', '1분10억'), ('076', '1분10억-매도')]
send_cond_dict = {}
price_dict = {}

#init_logger() #멀티프로세스에서는 정의 해야함
class SimData:
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
        "314930": { "종목명": "바이오다인", "전일가": 15580 }
    }

    def __init__(self):
        self.price_data = {}
        self.type_groups = {}
        self.highest_rate = 1.3
        self.high_rate = 1.1
        self.change_time = 180
        self.low_rate = 0.97
        self.lowest_rate = 0.95
        self.start_time = time.time()
        self._initialize_data()

    def _initialize_data(self):
        """데이터 초기화"""
        codes = list(self.ticker.keys())
        random.shuffle(codes)

        # 타입별 종목 할당
        n = len(codes)
        self.type_groups = {
            'type_a': codes[:n//5],
            'type_b': codes[n//5:2*n//5],
            'type_c': codes[2*n//5:3*n//5],
            'type_d': codes[3*n//5:4*n//5],
            'type_e': codes[4*n//5:]
        }

        # 가격 데이터 초기화
        for code in self.ticker:
            base_price = self.ticker[code]["전일가"]
            self.price_data[code] = {
                "base_price": base_price,
                "current_price": base_price,
                "type_change_time": None,
                "last_update_time": time.time()
            }

    def update_price(self, code):
        """종목별 가격 업데이트"""
        price_info = self.price_data[code]

        # 새로운 가격 계산
        new_price = self.get_next_price(code)

        # 가격 반영
        price_info["last_price"] = price_info["current_price"]
        price_info["current_price"] = new_price

        return new_price

    def get_next_price(self, code):
        """다음 가격 계산"""
        current_type = next((type_name for type_name, codes in self.type_groups.items()
                           if code in codes), None)
        if not current_type:
            return self.price_data[code]["current_price"]

        current_price = self.price_data[code]["current_price"]
        base_price = self.price_data[code]["base_price"]

        # 타입별 확률과 방향 설정
        if current_type == 'type_c':
            direction = -1 if current_price > base_price else 1
            prob = min(90, 50 + abs(current_price - base_price) / base_price * 100)
        else:
            prob = 85 if current_type in ['type_b', 'type_e'] else 60
            direction = 1 if current_type in ['type_a', 'type_b'] else -1

        # 가격 변동
        new_price = hoga(current_price, direction if random.randint(1, 100) <= prob else -direction)
        self.price_data[code]["current_price"] = new_price

        # 타입 전환 체크
        self._check_transition(code, new_price)

        return new_price

    def _check_transition(self, code, new_price):
        """타입 전환 체크"""
        current_type = next((type_name for type_name, codes in self.type_groups.items()
                           if code in codes), None)
        if not current_type:
            return

        price_info = self.price_data[code]
        price_ratio = new_price / price_info["base_price"]

        # 타입별 전환 조건
        if current_type == 'type_a' and price_ratio >= self.high_rate:  # 10% 상승
            self._move_type(code, current_type, 'type_b')
        elif current_type == 'type_b' and price_ratio >= self.highest_rate:  # 30% 상승
            self._move_type(code, current_type, 'type_c')
            price_info["type_change_time"] = time.time()
        elif current_type == 'type_c' and price_info["type_change_time"]:
            if time.time() - price_info["type_change_time"] >= self.change_time:  # 3분 후
                self._move_type(code, current_type, 'type_d')
                price_info["type_change_time"] = None
        elif current_type == 'type_d' and price_ratio <= self.low_rate:  # -3% 하락
            self._move_type(code, current_type, 'type_e')
        elif current_type == 'type_e' and price_ratio <= self.lowest_rate:  # -5% 하락
            self._move_type(code, current_type, 'type_a')

    def _move_type(self, code, from_type, to_type):
        """종목 타입 이동"""
        if code in self.type_groups[from_type]:
            self.type_groups[from_type].remove(code)
            self.type_groups[to_type].append(code)

sim = SimData()

class PortfolioManager:
    def __init__(self):
        # 보유종목 리스트
        self.holdings = {}

        # 계좌 합산 정보
        self.summary = {
            '총매입금액': 0,
            '총평가금액': 0,
            '추정예탁자산': 4000000,  # 초기 예탁금 10억원으로 설정
            '총평가손익금액': 0,
            '총수익률(%)': 0.0
        }

    def process_order(self, dictFID):
        """주문 처리 후 포트폴리오 업데이트"""
        code = dictFID.get('종목코드')
        name = dictFID.get('종목명')
        price = int(dictFID.get('체결가', 0))
        quantity = int(dictFID.get('체결량', 0))
        ordtype = dictFID.get('매도수구분')

        # 매수인 경우
        if ordtype == '2':
            self._process_buy(code, name, price, quantity)
        # 매도인 경우
        elif ordtype == '1':
            self._process_sell(code, name, price, quantity)

        # 업데이트 후 합산 데이터 계산
        self._update_summary()

    def _process_buy(self, code, name, price, quantity):
        """매수 처리"""
        if not price or not quantity:
            return

        # 기존 보유 여부 확인
        if code in self.holdings:
            # 기존 보유 종목인 경우 평균단가 계산
            current = self.holdings[code]
            current_quantity = current['보유수량']
            current_price = current['매입가']

            # 새로운 보유수량
            new_quantity = current_quantity + quantity
            # 새로운 평균단가
            new_price = int((current_quantity * current_price + quantity * price) / new_quantity)

            # 업데이트
            current['보유수량'] = new_quantity
            current['매입가'] = new_price
            current['매입금액'] = new_price * new_quantity
        else:
            # 신규 종목 추가
            self.holdings[code] = {
                '종목명': name,
                '보유수량': quantity,
                '매입가': price,
                '매입금액': price * quantity,
                '현재가': price,
                '평가금액': price * quantity,
                '평가손익': 0,
                '수익률(%)': 0.0
            }

        # 자산 업데이트
        self.summary['추정예탁자산'] -= price * quantity

    def _process_sell(self, code, name, price, quantity):
        """매도 처리"""
        if not price or not quantity or code not in self.holdings:
            return

        current = self.holdings[code]
        current_quantity = current['보유수량']

        # 보유수량보다 적게 매도하는 경우
        if quantity < current_quantity:
            current['보유수량'] = current_quantity - quantity
            current['매입금액'] = current['매입가'] * current['보유수량']
        # 전량 매도하는 경우
        else:
            del self.holdings[code]

        # 자산 업데이트
        self.summary['추정예탁자산'] += price * quantity

    def update_stock_price(self, code, current_price):
        """종목 현재가 업데이트"""
        if code in self.holdings:
            holdings = self.holdings[code]
            holdings['현재가'] = current_price
            holdings['평가금액'] = current_price * holdings['보유수량']
            holdings['평가손익'] = holdings['평가금액'] - holdings['매입금액']

            # 수익률 계산 (매입금액이 0이 아닌 경우에만)
            if holdings['매입금액'] > 0:
                holdings['수익률(%)'] = round(holdings['평가손익'] / holdings['매입금액'] * 100, 2)

            # 합산 데이터 업데이트
            self._update_summary()

    def _update_summary(self):
        """합산 데이터 업데이트"""
        total_purchase = 0
        total_evaluation = 0

        for holdings in self.holdings.values():
            total_purchase += holdings['매입금액']
            total_evaluation += holdings['평가금액']

        self.summary['총매입금액'] = total_purchase
        self.summary['총평가금액'] = total_evaluation
        self.summary['총평가손익금액'] = total_evaluation - total_purchase

        # 총수익률 계산 (총매입금액이 0이 아닌 경우에만)
        if total_purchase > 0:
            self.summary['총수익률(%)'] = round(self.summary['총평가손익금액'] / total_purchase * 100, 2)

    def get_holdings_list(self):
        """보유종목 리스트 조회"""
        return list(self.holdings.values())

    def get_summary(self):
        """합산 데이터 조회"""
        return self.summary

portfolio = PortfolioManager()

class OnReceiveChejanData(QThread):
    def __init__(self, qdict, code, orderno, order):
        super().__init__()
        self.qdict = qdict
        self.code = code
        self.orderno = orderno
        self.order = order

    def run(self):
        for cnt in range(3):
            if cnt == 2:
                dictFID = {}
                dictFID['종목코드'] = self.code
                dictFID['종목명'] = sim.ticker.get(self.code, {}).get('종목명', '')
                dictFID['보유수량'] = 0 if self.order['ordtype'] == 2 else self.order['quantity'] # 주문결과 수량 적용
                dictFID['매입단가'] = 0 if self.order['ordtype'] == 2 else self.order['price'] # 주문결과 매입가 적용
                self.qdict['aaa'].request.put(Work('odr_fx처리_잔고변경', {'dictFID': dictFID}))
            else:
                dictFID = {}
                dictFID['계좌번호'] = self.order['accno']
                dictFID['주문번호'] = self.orderno
                dictFID['종목코드'] = self.code
                dictFID['종목명'] = sim.ticker.get(self.code, {}).get('종목명', '')
                dictFID['주문수량'] = self.order['quantity']
                dictFID['주문가격'] = self.order['price']
                dictFID['원주문번호'] = self.order['ordno']
                dictFID['주문구분'] = '+매수' if self.order['ordtype'] == 1 else '-매도'
                dictFID['매매구분'] = '보통' if self.order['hoga'] == '00' else '시장가'
                dictFID['매도수구분'] = '2' if self.order['ordtype'] == 1 else '1'
                dictFID['주문/체결시간'] = time.strftime('%H%M%S', time.localtime())
                dictFID['현재가'] = price_dict.get(self.code, 0)
                if cnt == 0:
                    dictFID['주문상태'] = '접수'
                    dictFID['체결가'] = ''
                    dictFID['체결량'] = ''
                    dictFID['체결번호'] = ''
                    dictFID['미체결수량'] = self.order['quantity']
                    dictFID['체결누계금액'] = ''
                    dictFID['단위체결가'] = ''
                    dictFID['단위체결량'] = ''
                    dictFID['주문가능수량'] = 0
                else:
                    dictFID['주문상태'] = '체결'
                    dictFID['체결가'] = self.order['price']
                    dictFID['체결량'] = self.order['quantity']
                    dictFID['체결번호'] = f'{random.randint(1000000, 9999999):07d}' # 임의의 7자리 숫자형 문자
                    dictFID['미체결수량'] = 0
                    dictFID['체결누계금액'] = self.order['price'] * self.order['quantity']
                    dictFID['단위체결가'] = self.order['price']
                    dictFID['단위체결량'] = self.order['quantity']
                    dictFID['주문가능수량'] = 0 if self.order['ordtype'] == 2 else self.order['quantity'] # 주문결과 주문가능수량 적용

                    portfolio.process_order(dictFID)

                self.qdict['aaa'].request.put(Work('odr_fx처리_접수체결', {'dictFID': dictFID}))
            time.sleep(1)
        global chejan_thread
        if self in chejan_thread:
            chejan_thread.remove(self)
        self.quit()
        self.wait()

class OnReceiveRealCondition(QThread):
    def __init__(self, qdict, cond_name, cond_index):
        super().__init__()
        self.qdict = qdict
        self.cond_name = cond_name
        self.cond_index = cond_index
        self.is_running = True
        self.current_stocks = set()

    def run(self):
        while self.is_running:
            code = random.choice(list(sim.ticker.keys()))
            type = random.choice(['D', 'I'])

            current_count = len(self.current_stocks)

            if not (type == 'D' and current_count == 0 or type == 'I' and current_count == 4):
                cond = f'{self.cond_index} : {self.cond_name}'
                if cond not in send_cond_dict:
                    send_cond_dict[cond] = code
                data = {
                    'code': code,
                    'type': type,
                    'cond_name': self.cond_name,
                    'cond_index': int(self.cond_index),
                }
                self.qdict['aaa'].request.put(Work('on_fx실시간_조건검색', data))
                if type == 'I':
                    self.current_stocks.add(code)
                else:
                    if code in self.current_stocks:
                        self.current_stocks.remove(code)

            interval = random.uniform(3, 15)
            time.sleep(interval)

    def stop(self):
        self.is_running = False

class OnReceiveRealData(QThread):
    def __init__(self, qdict=None):
        super().__init__()
        self.is_running = True
        self.qdict = qdict

    def run(self):
        cnt = len(sim.ticker.keys())
        while self.is_running:
            # 모든 종목에 대해 가격 업데이트
            for code in sim.ticker.keys():
                # 시뮬레이터에서 현재가 계산
                current_price = sim.update_price(code)
                price_dict[code] = current_price

                # 실시간 데이터 전송
                dictFID = {
                    '종목코드': code,
                    '종목명': sim.ticker.get(code, {}).get('종목명', ''),
                    '현재가': current_price,
                    '등락율': round((current_price - sim.ticker[code]['전일가']) / sim.ticker[code]['전일가'] * 100, 2),
                }

                # 포트폴리오 업데이트
                portfolio.update_stock_price(code, current_price)

                # 실시간 데이터 전송
                if self.qdict and hasattr(self.qdict['aaa'], 'request'):
                    job = {
                        'code': code,
                        'rtype': '주식체결',
                        'dictFID': dictFID
                    }
                    self.qdict['aaa'].request.put(Work('on_fx실시간_주식체결', job))

                time.sleep(1/cnt)

    def stop(self):
        self.is_running = False

class SIMServer:
    def __init__(self, name, qdict, cls=None):
        self.name = name
        self.qdict = qdict
        self.cls = cls

        self.ocx = None
        self.connected = False

        self.strategy_loaded = False        # GetConditionLoad에서 대기 플래그로 사용 ConditionVer에서 조건 로드 완료 플래그로 사용
        self.strategy_list = None           # GetConditionNameList에서 리스트 담기

        self.tr_result_format = 'dict_list' # OnReceiveTrData에서 포맷 설정
        self.tr_received = False            # OnReceiveTrData에서 자료를 받았다는 수신 플래그로 사용
        self.tr_result = None               # OnReceiveTrData에서 자료 수신 결과 데이타
        self.tr_remained = False            # OnReceiveTrData에서 데이타 수신 완료 후 후속 데이타 있는지 확인 플래그
        self.tr_coulmns = None              # OnReceiveTrData에서 컬럼 리스트 담기

        self.tr_condition_loaded = False    # SendCondition에서 대기 플래그로 사용 OnReceiveTrCondition에서 조건 로드 완료 플래그로 사용
        self.tr_condition_list = None       # OnReceiveTrCondition에서 리스트 담기

        self.order_no = int(time.strftime('%Y%m%d', time.localtime())) + random.randint(0, 100000)

    def put(self, target, work):
        if hasattr(gm.admin, work.order):
            getattr(gm.admin, work.order)(**work.job)

    def stop(self):
        for thread in real_thread.values():
            thread.stop()
            thread.wait()
        for thread in cond_thread.values():
            thread.stop()
            thread.wait()
        for thread in chejan_thread:
            thread.stop()
            thread.wait()
        real_thread.clear()
        cond_thread.clear()
        chejan_thread.clear()

    def api_login(self, block=True):
        logging.debug(f'login: block={block}')
        self.CommConnect(block)

    def api_connected(self):
        return self.connected

    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', timeout=5):
        self.tr_result = []
        self.tr_remained = False
        if rqname == '잔고합산':
            summary = portfolio.get_summary()
            self.tr_result = [summary]
        elif rqname == '잔고목록':
            holdings = portfolio.get_holdings_list()
            self.tr_result = holdings
        return self.tr_result, self.tr_remained

    def CommConnect(self, block=True):
        logging.debug(f'CommConnect: block={block}')
        self.connected = True

    # 추가 메서드 --------------------------------------------------------------------------------------------------
    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'API 로그 레벨 설정: {level}')

    # 실시간 데이터 관련 메서드 --------------------------------------------------------------------------------------------------
    def DisconnectRealData(self, screen):
        logging.debug(f'screen={screen}')
        real_thread[screen].stop()

    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        thread = OnReceiveRealData(self.qdict)
        real_thread[screen] = thread
        thread.start()
        return 0

    def SetRealRemove(self, screen, del_code):
        logging.debug(f'screen={screen}, del_code={del_code}')
        if not real_thread: return
        if screen == 'ALL':
            for screen in real_thread:
                real_thread[screen].stop()
        else:
            if screen in real_thread:
                real_thread[screen].stop()

    # 조건 관련 메서드 --------------------------------------------------------------------------------------------------
    def GetConditionLoad(self, block=True):
        self.strategy_loaded = True
        return self.strategy_loaded

    def GetConditionNameList(self):
        logging.debug('')
        return cond_data_list

    def SendCondition(self, screen, cond_name, cond_index, search, block=True):
        self.tr_condition_loaded = True
        self.tr_condition_list = []
        cond = OnReceiveRealCondition(self.qdict, cond_name, cond_index)
        cond.start()
        cond_thread[screen] = cond
        return self.tr_condition_list

    def SendConditionStop(self, screen, cond_name, index):
        cond_thread[screen].stop()
        return 0

    # 주문 관련 메서드 --------------------------------------------------------------------------------------------------
    def SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno):
        self.order_no += 1
        orderno = f'{self.order_no:07d}'
        order = {
            'rqname': rqname,
            'screen': screen,
            'accno': accno,
            'ordtype': ordtype,
            'code': code,
            'quantity': quantity,
            'price': price,
            'hoga': hoga,
            'ordno': '',
        }
        result = {
            'code': code,
            'name': sim.ticker.get(code, {}).get('종목명', ''),
            'order_no': orderno,
            'screen': screen,
            'rqname': rqname,
        }
        self.put('aaa', Work('on_fx수신_주문결과TR', result))

        global chejan_thread
        chejan = OnReceiveChejanData(self.qdict, code, orderno, order)
        chejan_thread.append(chejan)
        chejan.start()
        return 0

    # 즉답 관련 메서드 --------------------------------------------------------------------------------------------------
    def GetLoginInfo(self, kind):
        logging.debug(f'******GetLoginInfo: kind={kind}')
        if kind == "ACCNO":
            return ['8095802711']
        else:
            return '1'
    def GetMasterCodeName(self, code):
        data = sim.ticker.get(code, {}).get('종목명', '')
        return data
    def GetMasterLastPrice(self, code):
        data = sim.ticker.get(code, {}).get('전일가', 0)
        return data


