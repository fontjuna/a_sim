from classes import la
from public import hoga, dc, gm, init_logger
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
import logging
import time
import random
import threading
import pythoncom
import pandas as pd
import copy
import datetime

init_logger()

real_thread = {}
cond_thread = {}
cond_data_list =  [('079', '전고돌파3분5억-매수'), ('080', '전고돌파3분5억-매도'), ('073', '3분30억전고돌파-매수'), ('077', '3분30억전고돌파-매도'), ('075', '장시작3분-매수'),\
                  ('074', '장시작3분-매도'), ('024', '1분10억'), ('076', '1분10억-매도'), ('004', '돌파4시간3분5억-매수'), ('006', '돌파4시간3분5억-매도')]
price_dict = {}
real_tickers = set()
ready_tickers = False

class ChartDataSimulator:
   def __init__(self):
      self.chart_data = []
      self.current_index = 0
      self.start_time = None
      self.base_chart_time = None
      self.ticker_info = {}
      
   def load_chart_data(self, api):
      """차트 데이터 로드"""
      self.chart_data = api.ipc.answer('dbm', 'get_simulation_data')
      
      if not self.chart_data:
         logging.error("차트 데이터가 로드되지 않았습니다.")
         return False
      
      # 종목 정보 추출
      self.extract_ticker_info()
      
      return True
   
   def extract_ticker_info(self):
      """차트 데이터에서 종목 정보 추출"""
      self.ticker_info = {}
      for data in self.chart_data:
         code = data.get('종목코드')
         if code and code not in self.ticker_info:
            self.ticker_info[code] = {
               '종목명': data.get('종목명', ''),
               '전일가': 0  # 필요시 설정
            }
   
   def get_tick_data(self, current_time=None):
      """현재 시간에 해당하는 틱 데이터 반환"""
      if not self.chart_data:
         return []
      
      if not current_time:
         current_time = datetime.datetime.now().time()
      
      if not self.start_time:
         self.start_time = datetime.datetime.now()
         # 첫 차트 데이터의 시간 찾기
         self.base_chart_time = self.extract_time_from_chart(self.chart_data[0]['체결시간'])
      
      # 현재 경과 시간 계산 (초 단위)
      elapsed_seconds = (datetime.datetime.now() - self.start_time).total_seconds()
      
      # 현재 차트 시간 계산
      current_chart_seconds = self.base_chart_time.hour * 3600 + self.base_chart_time.minute * 60 + self.base_chart_time.second
      target_chart_seconds = current_chart_seconds + int(elapsed_seconds)
      target_hour = (target_chart_seconds // 3600) % 24
      target_minute = (target_chart_seconds % 3600) // 60
      target_second = target_chart_seconds % 60
      target_chart_time = datetime.time(target_hour, target_minute, target_second)
      
      # 해당 시간의 데이터 찾기
      result_data = []
      for i in range(self.current_index, len(self.chart_data)):
         chart_time = self.extract_time_from_chart(self.chart_data[i]['체결시간'])
         chart_seconds = chart_time.hour * 3600 + chart_time.minute * 60 + chart_time.second
         
         if chart_seconds <= target_chart_seconds:
            result_data.append(self.chart_data[i])
            self.current_index = i + 1
         else:
            break
      
      return result_data
   
   def extract_time_from_chart(self, time_str):
      """차트 데이터의 체결시간에서 시간 정보 추출"""
      # '20250505090000' 형식에서 시간 추출 (뒤 6자리)
      time_part = time_str[-6:]
      hour = int(time_part[:2])
      minute = int(time_part[2:4])
      second = int(time_part[4:])
      return datetime.time(hour, minute, second)
   
   def get_next_data_delay(self):
      """다음 데이터까지의 지연 시간 계산 (초 단위)"""
      if self.current_index >= len(self.chart_data) - 1:
         return None  # 더 이상 데이터가 없음
      
      current_time = self.extract_time_from_chart(self.chart_data[self.current_index-1]['체결시간'])
      next_time = self.extract_time_from_chart(self.chart_data[self.current_index]['체결시간'])
      
      current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
      next_seconds = next_time.hour * 3600 + next_time.minute * 60 + next_time.second
      
      delay = next_seconds - current_seconds
      return max(0, delay)  # 음수면 0 반환 (같은 시간이거나 역전된 경우)

sim = ChartDataSimulator()

class PortfolioManager:
   def __init__(self):
      # 보유종목 리스트
      self.holdings = {}

      # 계좌 합산 정보
      self.summary = {
         '총매입금액': 0,
         '총평가금액': 0,
         '추정예탁자산': 400000000,  # 초기 예탁금 4억원으로 설정
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
      if not price or not quantity: return

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
      if not price or not quantity or code not in self.holdings: return

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
      holdings_list = []
      for code, data in self.holdings.items():
         holding = data.copy()
         holding['종목번호'] = code
         holdings_list.append(holding)
      return holdings_list

   def get_summary(self):
      """합산 데이터 조회"""
      return self.summary

portfolio = PortfolioManager()

class OnReceiveRealCondition(QThread):
   def __init__(self, cond_name, cond_index):
      super().__init__()
      self.daemon = True
      self.cond_name = cond_name
      self.cond_index = cond_index
      self.is_running = True
      self.current_stocks = set()
      self._stop_event = threading.Event()

   def run(self):
      while self.is_running:
         if not gm.config.ready:
            time.sleep(0.01)
            continue
         code = random.choice(list(sim.ticker_info.keys()))
         type = random.choice(['D', 'I'])

         current_count = len(self.current_stocks)
         if current_count >= 3 and type == 'I': continue

         data = {
            'code': code,
            'type': type,
            'cond_name': self.cond_name,
            'cond_index': int(self.cond_index),
         }
         gm.admin.on_fx실시간_조건검색(**data)

         if type == 'I':
            self.current_stocks.add(code)
         else:
            if code in self.current_stocks:
               self.current_stocks.remove(code)

         interval = random.uniform(0.3, 3)
         if self._stop_event.wait(timeout=interval): break

   def stop(self):
      self.is_running = False
      self._stop_event.set()

class OnReceiveRealData(QThread):
   def __init__(self):
      super().__init__()
      self.daemon = True
      self.is_running = True
      self._stop_event = threading.Event()
      self.last_check_time = time.time()

   def run(self):
      while self.is_running:
         if not gm.config.ready or not ready_tickers:
            time.sleep(0.01)
            continue
         
         # 현재 시간에 해당하는 차트 데이터 가져오기
         tick_data_list = sim.get_tick_data()
         
         # 데이터가 있으면 처리
         if tick_data_list:
            for tick_data in tick_data_list:
               if not self.is_running:
                  break
                  
               code = tick_data['종목코드']
               current_price = int(tick_data['현재가'])
               price_dict[code] = current_price
               
               # 실시간 데이터 전송
               dictFID = {
                  '종목코드': code,
                  '종목명': tick_data.get('종목명', ''),
                  '현재가': current_price,
                  '등락율': float(tick_data.get('등락율', 0)),
                  '누적거래량': int(tick_data.get('누적거래량', 0)),
                  '누적거래대금': int(tick_data.get('누적거래대금', 0)),
                  '체결시간': tick_data.get('체결시간', ''),
               }
               
               # 포트폴리오 업데이트
               portfolio.update_stock_price(code, current_price)
               
               # 실시간 데이터 전송
               job = {
                  'code': code,
                  'rtype': '주식체결',
                  'dictFID': dictFID
               }
               gm.admin.on_fx실시간_주식체결(**job)
         
         # 다음 데이터까지 대기
         delay = sim.get_next_data_delay()
         if delay is None:
            # 모든 데이터를 처리한 경우
            if self._stop_event.wait(timeout=1):  # 1초마다 체크
               break
         elif delay > 0:
            # 다음 데이터까지 지연
            if self._stop_event.wait(timeout=delay):
               break
         else:
            # 같은 시간대 데이터는 즉시 처리
            continue

   def stop(self):
      self.is_running = False
      self._stop_event.set()

class SIMServer():
    app = QApplication([])
    def __init__(self):
        self.name = 'api'
        self.ocx = None
        self.connected = False
        self.ipc = None

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

    def api_init(self):
        try:
            logging.debug(f'{self.name} api_init start')
            self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            self._set_signal_slots()
            logging.debug(f'{self.name} api_init success: ocx={self.ocx}')
            
            # 차트 데이터 로드
            sim.load_chart_data(self)
            global ready_tickers
            ready_tickers = True
        except Exception as e:
            logging.error(f"API 초기화 오류: {type(e).__name__} - {e}")

    # 각 클래스(Admin, API, DBM)에 추가할 메서드
    def get_var(self, var_name, default=None):
        """인스턴스 변수 가져오기"""
        return getattr(self, var_name, default)

    def set_var(self, var_name, value):
        """인스턴스 변수 설정하기"""
        setattr(self, var_name, value)
        return True

    def set_tickers(self):
        # 차트 데이터에서 종목 정보 추출
        if not sim.chart_data:
            sim.load_chart_data(self)
        
        global ready_tickers
        ready_tickers = True

    def _set_signal_slots(self):
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.ocx.OnReceiveConditionVer.connect(self.OnReceiveConditionVer)
        self.ocx.OnReceiveTrCondition.connect(self.OnReceiveTrCondition)
        self.ocx.OnReceiveTrData.connect(self.OnReceiveTrData)
        self.ocx.OnReceiveMsg.connect(self.OnReceiveMsg)

    def api_to_admin(self, func_name, *args, **kwargs):
        """Admin 클래스의 메서드 호출"""
        if hasattr(gm.admin, func_name):
            return getattr(gm.admin, func_name)(*args, **kwargs)
        return None

    def api_connected(self):
        while not self.connected:
            pythoncom.PumpWaitingMessages()
        return self.connected

    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', timeout=5):
        return self.sim_request(rqname, trcode, input, output, next, screen, form, timeout)

    def sim_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', timeout=5):
        self.tr_result = []
        self.tr_remained = False
        if rqname == '잔고합산':
            summary = portfolio.get_summary()
            self.tr_result = [summary]
        elif rqname == '잔고목록':
            holdings = portfolio.get_holdings_list()
            self.tr_result = holdings
        return self.tr_result, self.tr_remained

    def SetInputValue(self, id, value):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    def OnReceiveTrData(self, screen, rqname, trcode, record, next):
        if screen.startswith('4') or screen.startswith('55'):
            try:
                data = rqname.split('_')
                code = data[1]
                order_no = self.GetCommData(trcode, rqname, 0, '주문번호')
                result = {
                'code': code,
                'name': self.GetMasterCodeName(code),
                'order_no': order_no,
                'screen': screen,
                'rqname': rqname,
                }
                gm.admin.on_fx수신_주문결과TR(**result)

            except Exception as e:
                logging.error(f'TR 수신 오류: {type(e).__name__} - {e}', exc_info=True)

        else:
            try:
                self.tr_remained = next == '2'
                rows = self.GetRepeatCnt(trcode, rqname)
                if rows == 0: rows = 1

                data_list = []
                is_dict = self.tr_result_format == 'dict_list'
                for row in range(rows):
                    row_data = {} if is_dict else []
                    for column in self.tr_coulmns:
                        data = self.GetCommData(trcode, rqname, row, column)
                        if is_dict: row_data[column] = data
                        else: row_data.append(data)
                # [{}] 또는 [[]]로 되는것 방지 - 이것은 []로 리턴되어야 검사시 False 가 됨
                if any(row_data.values() if is_dict else row_data):
                    data_list.append(row_data)

                if is_dict:
                    self.tr_result = copy.deepcopy(data_list)
                else:
                    df = pd.DataFrame(data=data_list, columns=self.tr_coulmns)
                    self.tr_result = df

                self.tr_received = True

            except Exception as e:
                logging.error(f"TR 수신 오류: {type(e).__name__} - {e}")

    def OnEventConnect(self, code):
        logging.debug(f'OnEventConnect: code={code}')
        self.connected = code == 0
        self.api_to_admin('set_connected', self.connected)
        logging.debug(f'Login {"Success" if self.connected else "Failed"}')

    def CommConnect(self, block=True):
        logging.debug(f'CommConnect: block={block}')
        self.ocx.dynamicCall("CommConnect()")
        if block:
            while not self.connected:
                pythoncom.PumpWaitingMessages()

    # 추가 메서드 --------------------------------------------------------------------------------------------------
    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'API 로그 레벨 설정: {level}')

    # 실시간 데이터 관련 메서드 --------------------------------------------------------------------------------------------------
    def DisconnectRealData(self, screen):
        logging.debug(f'screen={screen}')
        real_thread[screen].stop()

    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        global real_thread
        if screen not in real_thread:
            thread = OnReceiveRealData()
            real_thread[screen] = thread
            thread.start()
        codes = code_list.split(';')[:-1]
        real_tickers.update(codes)
        return 0

    def SetRealRemove(self, screen, del_code):
        global real_thread
        logging.debug(f'screen={screen}, del_code={del_code}')
        if not real_thread: return
        if screen == 'ALL':
            for screen in real_thread:
                real_thread[screen].stop()
                del real_thread[screen]
        else:
            if screen in real_thread:
                real_thread[screen].stop()
                del real_thread[screen]

    # 조건 관련 메서드 --------------------------------------------------------------------------------------------------
    def OnReceiveConditionVer(self, ret, msg):
        logging.debug(f'ret={ret}, msg={msg}')
        self.strategy_loaded = ret == 1

    def OnReceiveTrCondition(self, screen, code_list, cond_name, cond_index, next):
        codes = code_list.split(';')[:-1]
        self.tr_condition_list = codes
        self.tr_condition_loaded = True

    def GetConditionLoad(self, block=True):
        self.strategy_loaded = False
        result = self.ocx.dynamicCall("GetConditionLoad()")  # result = ling 1: 성공, 0: 실패
        logging.debug(f'전략 요청 : {"성공" if result==1 else "실패"}')
        if block:
            while not self.strategy_loaded:
                pythoncom.PumpWaitingMessages()
        return self.strategy_loaded

    def GetConditionNameList(self):
        logging.debug('')
        data = self.ocx.dynamicCall("GetConditionNameList()")
        conditions = data.split(";")[:-1]
        cond_data_list = []
        for condition in conditions:
            cond_index, cond_name = condition.split('^')
            cond_data_list.append((cond_index, cond_name))
        return cond_data_list

    def SendCondition(self, screen, cond_name, cond_index, search, block=True):
        global cond_thread
        self.tr_condition_loaded = True
        self.tr_condition_list = []
        cond_thread[screen] = OnReceiveRealCondition(cond_name, cond_index)
        cond_thread[screen].start()
        logging.debug(f'추가후: {cond_thread}')
        return self.tr_condition_list

    def SendConditionStop(self, screen, cond_name, cond_index):
        global cond_thread
        cond_thread[screen].stop()
        logging.debug(f'삭제전: {cond_thread}')
        del cond_thread[screen]
        logging.debug(f'삭제후: {cond_thread}')
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

        self.OnReceiveChejanData(code, orderno, order)
        return 0

    def OnReceiveChejanData(self, code, orderno, order):
        global price_dict
        for cnt in range(3):
            if cnt == 2:
                dictFID = {}
                dictFID['종목코드'] = code
                dictFID['종목명'] = sim.ticker_info.get(code, {}).get('종목명', '')
                dictFID['보유수량'] = 0 if order['ordtype'] == 2 else order['quantity'] # 주문결과 수량 적용
                dictFID['매입단가'] = 0 if order['ordtype'] == 2 else order['price'] # 주문결과 매입가 적용
                dictFID['주문가능수량'] = 0 if order['ordtype'] == 2 else order['quantity'] # 주문결과 주문가능수량 적용
                gm.admin.odr_recieve_balance_data(dictFID)
            else:
                dictFID = {}
                dictFID['계좌번호'] = order['accno']
                dictFID['주문번호'] = orderno
                dictFID['종목코드'] = code
                dictFID['종목명'] = sim.ticker_info.get(code, {}).get('종목명', '')
                dictFID['주문수량'] = order['quantity']
                dictFID['주문가격'] = order['price']
                dictFID['원주문번호'] = order['ordno']
                dictFID['주문구분'] = '+매수' if order['ordtype'] == 1 else '-매도'
                dictFID['매매구분'] = '보통' if order['hoga'] == '00' else '시장가'
                dictFID['매도수구분'] = '2' if order['ordtype'] == 1 else '1'
                dictFID['주문/체결시간'] = time.strftime('%H%M%S', time.localtime())
                dictFID['현재가'] = price_dict.get(code, 0)
                if cnt == 0:
                    dictFID['주문상태'] = '접수'
                    dictFID['체결가'] = ''
                    dictFID['체결량'] = ''
                    dictFID['체결번호'] = ''
                    dictFID['미체결수량'] = order['quantity']
                    dictFID['체결누계금액'] = ''
                    dictFID['단위체결가'] = ''
                    dictFID['단위체결량'] = ''
                    dictFID['주문가능수량'] = 0
                else:
                    dictFID['주문상태'] = '체결'
                    dictFID['체결가'] = order['price']
                    dictFID['체결량'] = order['quantity']
                    dictFID['체결번호'] = f'{random.randint(1000000, 9999999):07d}' # 임의의 7자리 숫자형 문자
                    dictFID['미체결수량'] = 0
                    dictFID['체결누계금액'] = order['price'] * order['quantity']
                    dictFID['단위체결가'] = order['price']
                    dictFID['단위체결량'] = order['quantity']
                    dictFID['주문가능수량'] = 0 if order['ordtype'] == 2 else order['quantity'] # 주문결과 주문가능수량 적용

                    portfolio.process_order(dictFID)

                gm.admin.odr_recieve_chegyeol_data(dictFID)
            time.sleep(0.1)

    # 즉답 관련 메서드 --------------------------------------------------------------------------------------------------
    def GetLoginInfo(self, kind):
        logging.debug(f'GetLoginInfo: kind={kind}')
        if kind == "ACCNO":
            return ['8095802711']
        else:
            return '1'

    def GetMasterCodeName(self, code):
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code) if hasattr(self, 'ocx') and self.ocx else sim.ticker_info.get(code, {}).get('종목명', '')
        return data
    
    def GetMasterLastPrice(self, code):
        data = self.ocx.dynamicCall("GetMasterLastPrice(QString)", code) if hasattr(self, 'ocx') and self.ocx else sim.ticker_info.get(code, {}).get('전일가', 0)
        data = int(data) if data else 0
        return data

    def OnReceiveMsg(self, screen, rqname, trcode, msg):
        logging.info(f'screen={screen}, rqname={rqname}, trcode={trcode}, msg={msg}')

    def CommRqData(self, rqname, trcode, next, screen):
        ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen)
        return ret

    def GetCommData(self, trcode, rqname, index, item):
        data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, index, item)
        data = data.strip() if type(data) == str else data
        return data

    def GetRepeatCnt(self, trcode, rqname):
        count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
        return count

    def GetCodeListByMarket(self, market):
        """
        시장별 상장된 종목코드를 반환하는 메서드
        :param market: str 
                    0: 코스피, 3: ELW, 4: 뮤추얼펀드 5: 신주인수권 6: 리츠
                    8: ETF, 9: 하이일드펀드, 10: 코스닥, 30: K-OTC, 50: 코넥스(KONEX)
        :return: 종목코드 리스트 예: ["000020", "000040", ...]
        """
        if hasattr(self, 'ocx') and self.ocx:
            data = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market)
            tokens = data.split(';')[:-1]
        else:
            tokens = list(sim.ticker_info.keys())
        return tokens