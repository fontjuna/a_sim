from public import hoga, dc, init_logger, profile_operation
from classes import TimeLimiter, Toast
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
import sys

init_logger()
toast = None #Toast()
ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
req = TimeLimiter(name='req', second=5, minute=100, hour=1000)
def com_request_time_check(kind='order', cond_text = None):
    start_time = time.time()
    #logging.debug(f'com_request_time_check: Start')
    if kind == 'order':
        wait_time = ord.check_interval()
    elif kind == 'request':
        wait_time = max(req.check_interval(), req.check_condition_interval(cond_text) if cond_text else 0)

    #logging.debug(f'대기시간: {wait_time} ms kind={kind} cond_text={cond_text}')
    if wait_time > 1666: # 1.666초 이내 주문 제한
        msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {float(wait_time/1000)} 초' \
            if cond_text is None else f'{cond_text} 1분 이내에 같은 조건 호출 불가 합니다. 대기시간: {float(wait_time/1000)} 초'
        #toast.toast(msg, duration=dc.td.TOAST_TIME)
        logging.warning(msg)
        return False
    
    elif wait_time > 1000:
        msg = f'빈번한 요청은 시간 제한을 받습니다. 잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
        #toast.toast(msg, duration=wait_time)
        time.sleep((wait_time-10)/1000) 
        wait_time = 0
        logging.info(msg)

    elif wait_time > 0:
        msg = f'잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
        #toast.toast(msg, duration=wait_time)
        logging.info(msg)

    time.sleep((wait_time+100)/1000) 

    if kind == 'order':
        ord.update_request_times()
    elif kind == 'request':
        if cond_text: req.update_condition_time(cond_text)
        else: req.update_request_times()

    #logging.debug(f'com_request_time_check:Start ~ End: {time.time() - start_time} ms')
    return True

real_thread = {}
cond_thread = {}
cond_data_list =  [('079', '전고돌파3분5억-매수'), ('080', '전고돌파3분5억-매도'), ('073', '3분30억전고돌파-매수'), ('077', '3분30억전고돌파-매도'), ('075', '장시작3분-매수'),\
                  ('074', '장시작3분-매도'), ('024', '1분10억'), ('076', '1분10억-매도'), ('004', '돌파4시간3분5억-매수'), ('006', '돌파4시간3분5억-매도'), ('005', '스크립트만')]
price_dict = {}
real_tickers = set()
ready_tickers = False

class SimData:
   def __init__(self):
      self.ticker = {}
      self.price_data = {}
      self.type_groups = {}
      self.highest_rate = 1.3
      self.high_rate = 1.1
      self.change_time = 180
      self.low_rate = 0.97
      self.lowest_rate = 0.95
      self.start_time = time.time()
      self.chart_data = []
      self.current_index = 0
      self.base_chart_time = None
      self.sim_no = 1  # 기본값 1

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

   def extract_ticker_info(self):
      """차트 데이터에서 종목 정보 추출"""
      self.ticker = {}
      for data in self.chart_data:
         code = data.get('종목코드')
         if code and code not in self.ticker:
            self.ticker[code] = {
               '종목명': data.get('종목명', ''),
               '전일가': 0  # 필요시 설정
            }

   def update_price(self, code):
      """종목별 가격 업데이트 (sim_no=1,2용)"""
      price_info = self.price_data[code]

      # 새로운 가격 계산
      new_price = self.get_next_price(code)

      # 가격 반영
      price_info["last_price"] = price_info["current_price"]
      price_info["current_price"] = new_price

      return new_price

   def get_next_price(self, code):
      """다음 가격 계산 (sim_no=1,2용)"""
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
      """타입 전환 체크 (sim_no=1,2용)"""
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
      """종목 타입 이동 (sim_no=1,2용)"""
      if code in self.type_groups[from_type]:
         self.type_groups[from_type].remove(code)
         self.type_groups[to_type].append(code)

   # 차트 데이터 관련 메서드 (sim_no=3용)
   def get_tick_data(self):
      """현재 시간에 해당하는 틱 데이터 반환 (sim_no=3용)"""
      if not self.chart_data:
         return []
      
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
      """차트 데이터의 체결시간에서 시간 정보 추출 (sim_no=3용)"""
      # '20250505090000' 형식에서 시간 추출 (뒤 6자리)
      time_part = time_str[-6:]
      hour = int(time_part[:2])
      minute = int(time_part[2:4])
      second = int(time_part[4:])
      return datetime.time(hour, minute, second)
   
   def get_next_data_delay(self):
      """다음 데이터까지의 지연 시간 계산 (초 단위) (sim_no=3용)"""
      if self.current_index >= len(self.chart_data) - 1:
         return None  # 더 이상 데이터가 없음
      
      current_time = self.extract_time_from_chart(self.chart_data[self.current_index-1]['체결시간'])
      next_time = self.extract_time_from_chart(self.chart_data[self.current_index]['체결시간'])
      
      current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
      next_seconds = next_time.hour * 3600 + next_time.minute * 60 + next_time.second
      
      delay = next_seconds - current_seconds
      return max(0, delay)  # 음수면 0 반환 (같은 시간이거나 역전된 경우)

sim = SimData()

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

class OnReceiveRealConditionSim(QThread):
   def __init__(self, cond_name, cond_index, api):
      super().__init__()
      self.daemon = True
      self.cond_name = cond_name
      self.cond_index = cond_index
      self.is_running = True
      self.current_stocks = set()
      self.api = api
      self.order = api.order
      self._stop_event = threading.Event()

   def run(self):
      while self.is_running:
         if not self.api.connected:
            time.sleep(0.01)
            continue
         code = random.choice(list(sim.ticker.keys()))
         type = random.choice(['D', 'I'])

         current_count = len(self.current_stocks)
         if current_count >= 3 and type == 'I': continue

         data = {
            'code': code,
            'type': type,
            'cond_name': self.cond_name,
            'cond_index': int(self.cond_index),
         }
         self.order('admin', 'on_fx실시간_조건검색', **data)

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

class OnReceiveRealDataSim1And2(QThread):
   """시뮬레이션 1, 2번용 실시간 데이터 쓰레드"""
   def __init__(self, api):
      super().__init__()
      self.daemon = True
      self.is_running = True
      self._stop_event = threading.Event()
      self.api = api
      self.frq_order = api.frq_order

   def run(self):
      while self.is_running:
         if not self.api.connected or not ready_tickers:
            time.sleep(0.01)
            continue
         # 모든 종목에 대해 가격 업데이트
         for code in list(sim.ticker.keys()): 
            if not self.is_running:
               break
            # 시뮬레이터에서 현재가 계산
            current_price = sim.update_price(code)
            price_dict[code] = current_price

            # 실시간 데이터 전송
            dictFID = {
               '종목코드': code,
               '종목명': sim.ticker.get(code, {}).get('종목명', ''),
               '현재가': f'{current_price:15d}',
               '등락율': f'{round((current_price - sim.ticker[code]["전일가"]) / sim.ticker[code]["전일가"] * 100, 2):12.2f}',
               '누적거래량': f'{500000:15d}',
               '누적거래대금': f'{78452100:15d}',
               '체결시간': time.strftime('%Y%m%d%H%M%S', time.localtime()),
            }

            # 포트폴리오 업데이트
            portfolio.update_stock_price(code, current_price)

            # 실시간 데이터 전송
            job = {
               'code': code,
               'rtype': '주식체결',
               'dictFID': dictFID
            }
            self.frq_order('admin', 'on_fx실시간_주식체결', **job)

            if self._stop_event.wait(timeout=0.2/len(sim.ticker)):
               return

   def stop(self):
      self.is_running = False
      self._stop_event.set()

class OnReceiveRealDataSim3(QThread):
   """시뮬레이션 3번용 실시간 데이터 쓰레드"""
   def __init__(self, api):
      super().__init__()
      self.daemon = True
      self.is_running = True
      self._stop_event = threading.Event()
      self.api = api
      self.frq_order = api.frq_order

   def run(self):
      while self.is_running:
         if not self.api.connected or not ready_tickers:
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
                  '현재가': f'{current_price:15d}',
                  '등락율': f'{float(tick_data.get("등락율", 0)):15.2f}',
                  '누적거래량': f'{int(tick_data.get("누적거래량", 0)):15d}',
                  '누적거래대금': f'{int(tick_data.get("누적거래대금", 0)):15d}',
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
               self.frq_order('admin', 'on_fx실시간_주식체결', **job)
         
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

class APIServer:
    app = QApplication(sys.argv)
    def __init__(self):
        self.name = 'api'
        self.sim_no = 0
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

        self.counter = 0 # 테스트용

    def api_stop(self):
        """APIServer 종료 시 실행되는 메서드"""
        logging.info(f"APIServer 종료 시작 (sim_no={self.sim_no})")
        print(f"{self.__class__.__name__} 중지 중...")
        self.running = False     
   
        # 시뮬레이션 모드에서만 추가 정리 필요
        if self.sim_no > 0:
            # 실시간 데이터 스레드 정리
            global real_thread
            for screen in list(real_thread.keys()):
                if real_thread[screen]:
                    try:
                        logging.debug(f"실시간 데이터 스레드 정리: {screen}")
                        real_thread[screen].stop()
                        real_thread[screen].wait(1000)  # 최대 1초 대기
                        del real_thread[screen]
                    except Exception as e:
                        logging.error(f"실시간 스레드 정리 오류: {e}")
            
            # 조건검색 스레드 정리
            global cond_thread
            for screen in list(cond_thread.keys()):
                if cond_thread[screen]:
                    try:
                        logging.debug(f"조건검색 스레드 정리: {screen}")
                        cond_thread[screen].stop()
                        cond_thread[screen].wait(1000)  # 최대 1초 대기
                        del cond_thread[screen]
                    except Exception as e:
                        logging.error(f"조건검색 스레드 정리 오류: {e}")
        try:
            pythoncom.CoUninitialize()
        except Exception as e:
            logging.error(f"CoUninitialize 오류: {e}")
        # 연결 상태 변경
        self.connected = False
        logging.info("APIServer 종료 완료")

        return {"status": "stopped"}

    def api_start(self):
        """컴포넌트 시작"""
        print(f"{self.__class__.__name__} 시작 중...")
        self.running = True
        # 시작 관련 코드
        return {"status": "started"}
        
    def get_status(self):
        """상태 확인"""
        return {
            "name": self.__class__.__name__,
            "running": self.running,
            # 추가 상태 정보
        }
    
    def api_init(self, sim_no=0):
        try:
            #global toast
            #toast = Toast()
            import os
            pid = os.getpid()
            #logging.debug(f'{self.name} api_init start (sim_no={sim_no}, pid={pid})')
            self.sim_no = sim_no
            
            if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용
                # ActiveX 컨트롤 생성
                logging.debug(f"ActiveX 컨트롤 생성 시작: KHOPENAPI.KHOpenAPICtrl.1")
                self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
                #logging.debug(f"ActiveX 컨트롤 생성 완료: {self.ocx}")
                
                # logging.debug(f"시그널 슬롯 연결 시작")
                self._set_signal_slots()
                # logging.debug(f"시그널 슬롯 연결 완료")
                
                logging.debug(f'{self.name} api_init success: pid={pid} (Sim mode {self.sim_no}) ocx={self.ocx}')
            
            # self.set_tickers()
        except Exception as e:
            logging.error(f"API 초기화 오류: {type(e).__name__} - {e}", exc_info=True)

    def set_tickers(self):
        """종목 정보 설정 및 시뮬레이션 모드 변경"""
        if self.sim_no is not None:
            self.sim_no = self.sim_no
            logging.info(f"시뮬레이션 모드 변경: {self.sim_no}")
            
            # 기존 쓰레드 정리
            for screen in list(real_thread.keys()):
                if real_thread[screen]:
                    real_thread[screen].stop()
                    del real_thread[screen]
        
        if self.sim_no == 0:  # 실제 API 서버는 별도 처리 필요 없음
            pass
        elif self.sim_no == 1:  # 키움서버 없이 가상 데이터 사용
            sim.ticker = dc.sim.ticker
            sim._initialize_data()
        elif self.sim_no == 2:  # 키움서버 사용, 실시간 데이터 가상 생성
            codes = self.GetCodeListByMarket('NXT')
            if codes:
                selected_codes = random.sample(codes, 30)
                logging.debug(f'len={len(selected_codes)} codes={selected_codes}')
            else:
                logging.warning('GetCodeListByMarket 결과 없음 *************')
                raise

            sim.ticker = {}
            for code in selected_codes:
                sim.ticker[code] = {
                '종목명': self.GetMasterCodeName(code),
                '전일가': self.GetMasterLastPrice(code),
                }
            sim._initialize_data()
        elif self.sim_no == 3:  # 키움서버 사용, 차트 데이터 이용
            sim.chart_data = self.get_simulation_data()
            sim.extract_ticker_info()
        
        global ready_tickers
        ready_tickers = True

    def get_simulation_data(self):
        """차트 데이터 로드 - 외부에서 구현 예정"""
        # 이 함수는 외부에서 구현 예정
        return []
    
    def get_var(self, var_name, default=None):
        return getattr(self, var_name, default)

    def set_var(self, var_name, value):
        setattr(self, var_name, value)
        return True

    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'API 로그 레벨 설정: {level}')

    def waiting_in_loop(self, wait_boolean, failed_msg, timeout=10):
        start_time = time.time()
        while not wait_boolean:
            pythoncom.PumpWaitingMessages()
            if time.time() - start_time > timeout:
                logging.warning(f"Timeout while waiting for {failed_msg}")
                return False
        return True

    # 추가 메서드 --------------------------------------------------------------------------------------------------
    def api_connected(self):
        if self.sim_no == 1: return True
        else: 
            start_time = time.time()
            while not self.connected:
                pythoncom.PumpWaitingMessages()
                if time.time() - start_time > 15:
                    logging.warning(f"Timeout while waiting for API 연결")
                    return False
            logging.debug(f"API 연결 완료: {self.connected}")
            return self.connected

    def GetConnectState(self):
        if self.sim_no != 1:
            return self.ocx.dynamicCall("GetConnectState()")
        else:
            return 1

    #@profile_operation        
    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', timeout=5):
        #logging.debug(f'api_request: rqname={rqname}, trcode={trcode}, input={input}, next={next}, screen={screen}, form={form}, timeout={timeout}')
        try:
            if not com_request_time_check(kind='request'): return [], False

            self.tr_remained = False
            self.tr_result = []
            if self.sim_no == 1:
                if rqname == '잔고합산':
                    summary = portfolio.get_summary()
                    self.tr_result = [summary]
                elif rqname == '잔고목록':
                    holdings = portfolio.get_holdings_list()
                    self.tr_result = holdings
                return self.tr_result, self.tr_remained

            self.tr_coulmns = output
            self.tr_result_format = form
            self.tr_received = False

            screen = dc.화면[rqname] if not screen else screen
            for key, value in input.items(): self.SetInputValue(key, value)
            ret = self.CommRqData(rqname, trcode, next, screen)

            start_time = time.time()
            while not self.tr_received:
                pythoncom.PumpWaitingMessages()
                if time.time() - start_time > timeout:
                    logging.warning(f"Timeout while waiting for {rqname} data")
                    return [], False

            #logging.debug(f'{rqname} 요청 결과: {self.tr_result}')
            return self.tr_result, self.tr_remained

        except Exception as e:
            logging.error(f"TR 요청 오류: {type(e).__name__} - {e}")
            return [], False

    # 설정 관련 메소드 ---------------------------------------------------------------------------------------------
    def _set_signal_slots(self):
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.ocx.OnReceiveConditionVer.connect(self.OnReceiveConditionVer)
        self.ocx.OnReceiveTrCondition.connect(self.OnReceiveTrCondition)
        self.ocx.OnReceiveTrData.connect(self.OnReceiveTrData)
        self.ocx.OnReceiveRealData.connect(self.OnReceiveRealData)
        self.ocx.OnReceiveChejanData.connect(self.OnReceiveChejanData)
        self.ocx.OnReceiveRealCondition.connect(self.OnReceiveRealCondition)
        self.ocx.OnReceiveMsg.connect(self.OnReceiveMsg)

    def DisconnectRealData(self, screen):
        logging.debug(f'screen={screen}')
        if self.sim_no == 0:  # 실제 API 서버
            self.ocx.dynamicCall("DisconnectRealData(QString)", screen)
        else:  # 시뮬레이션 모드
            if screen in real_thread and real_thread[screen]:
                real_thread[screen].stop()

    def SetRealRemove(self, screen, del_code):
        logging.debug(f'screen={screen}, del_code={del_code}')
        if self.sim_no == 0:  # 실제 API 서버
            ret = self.ocx.dynamicCall("SetRealRemove(QString, QString)", screen, del_code)
            return ret
        else:  # 시뮬레이션 모드
            if not real_thread: return
            if screen == 'ALL':
                for s in list(real_thread.keys()):
                    if real_thread[s]:
                        real_thread[s].stop()
                        del real_thread[s]
            else:
                if screen in real_thread and real_thread[screen]:
                    real_thread[screen].stop()
                    del real_thread[screen]
               
    def SendConditionStop(self, screen, cond_name, cond_index):
        global cond_thread
        #logging.debug(f'전략 중지: screen={screen}, cond_name={cond_name}, cond_index={cond_index} {"*"*50}')
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", screen, cond_name, cond_index)
        
        # 모든 모드 공통 - 시뮬레이션용 조건검색 쓰레드 종료
        if screen in cond_thread and cond_thread[screen]:
            cond_thread[screen].stop()
            logging.debug(f'삭제전: {cond_thread}')
            del cond_thread[screen]
            logging.debug(f'삭제후: {cond_thread}')
        return 0

    def SetInputValue(self, id, value):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    # 요청 메서드(일회성 콜백 발생 ) ---------------------------------------------------------------------------------
    @profile_operation
    def CommConnect(self, block=True):
        logging.debug(f'CommConnect: block={block}')
        if self.sim_no == 1:  
            self.connected = True
            self.order('admin', 'set_connected', self.connected) # OnEventConnect를 안 거치므로 여기서 처리
        else:
            self.ocx.dynamicCall("CommConnect()")
            if block:
                while not self.connected:
                    pythoncom.PumpWaitingMessages()

    def GetConditionLoad(self, block=True):
        if self.sim_no == 1:  
            self.strategy_loaded = True
            result = 1
        else:  
            self.strategy_loaded = False
            result = self.ocx.dynamicCall("GetConditionLoad()")
            logging.debug(f'전략 요청 : {"성공" if result==1 else "실패"}')
            if block:
                while not self.strategy_loaded:
                    pythoncom.PumpWaitingMessages()
        return result

    def SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno):
        if not com_request_time_check(kind='order'): return -308 # 5회 제한 초과
        if self.sim_no == 0:  # 실제 API 서버
            #logging.debug(f'api 내부 SendOrder 호출전')
            ret = self.ocx.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                                    [rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno])
            #logging.debug(f'api 내부 SendOrder 호출후')
            return ret
        else:  # 시뮬레이션 모드
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

    def CommRqData(self, rqname, trcode, next, screen):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen)
            return ret
        return 0

    # 요청 메서드(실시간 콜백 발생 ) ---------------------------------------------------------------------------------
    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        if self.sim_no == 0:  # 실제 API 서버
            ret = self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen, code_list, fid_list, opt_type)
            #logging.debug(f'SetRealReg{"**성공**" if ret==0 else "**실패**"}: screen={screen}, code_list={code_list}, fid_list={fid_list}, opt_type={opt_type}')
            return ret
        else:  # 시뮬레이션 모드
            global real_thread
            if screen not in real_thread:
                if self.sim_no in [1, 2]:  # sim_no=1,2일 때
                    thread = OnReceiveRealDataSim1And2(self)
                else:  # sim_no=3일 때
                    thread = OnReceiveRealDataSim3(self)
                real_thread[screen] = thread
                thread.start()
            codes = code_list.split(';')[:-1]
            real_tickers.update(codes)
            return 0

    def SendCondition(self, screen, cond_name, cond_index, search, block=True, timeout=15):
        cond_text = f'{cond_index:03d} : {cond_name.strip()}'
        if not com_request_time_check(kind='request', cond_text=cond_text): return [], False

        if self.sim_no > 0:  # (sim_no=1, 2, 3)
            global cond_thread
            # 모든 모드 공통 - 시뮬레이션용 조건검색 쓰레드 시작
            self.tr_condition_loaded = True
            self.tr_condition_list = []
            cond_thread[screen] = OnReceiveRealConditionSim(cond_name, cond_index, self)
            cond_thread[screen].start()
            logging.debug(f'추가후: {cond_thread}')
            return self.tr_condition_list
        else:        
            try:
                data = False
                if block is True:
                    self.tr_condition_loaded = False

                success = self.ocx.dynamicCall("SendCondition(QString, QString, int, int)", screen, cond_name, cond_index, search)
                logging.debug(f'전략 요청: screen={screen}, name={cond_name}, index={cond_index}, search={search}, 결과={"성공" if success else "실패"}')

                if not success:
                    return False
                
                if block is True:
                    start_time = time.time()
                    while not self.tr_condition_loaded:
                        pythoncom.PumpWaitingMessages()
                        if time.time() - start_time > timeout:
                            logging.warning(f'조건 검색 시간 초과: {screen} {cond_name} {cond_index} {search}')
                            return False
                    data = self.tr_condition_list
                return data
            except Exception as e:
                logging.error(f"SendCondition 오류: {type(e).__name__} - {e}")
                return False
        
    # 응답 메서드 --------------------------------------------------------------------------------------------------
    def OnEventConnect(self, code):
        logging.debug(f'OnEventConnect: code={code}')
        self.connected = code == 0
        self.order('admin', 'set_connected', self.connected)
        logging.debug(f'Login {"Success" if self.connected else "Failed"}')

    def OnReceiveConditionVer(self, ret, msg):
        logging.debug(f'ret={ret}, msg={msg}')
        self.strategy_loaded = ret == 1

    def OnReceiveTrCondition(self, screen, code_list, cond_name, cond_index, next):
        codes = code_list.split(';')[:-1]
        self.tr_condition_list = codes
        self.tr_condition_loaded = True

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
                self.order('admin', 'on_fx수신_주문결과TR', **result)

            except Exception as e:
                logging.error(f'TR 수신 오류: {type(e).__name__} - {e}', exc_info=True)
        else:
            try:
                self.tr_remained = next == '2'
                rows = self.GetRepeatCnt(trcode, rqname)
                if rows == 0: rows = 1

                #if trcode in [dc.scr.차트TR['mi'], dc.scr.차트TR['dy']]:
                #logging.debug(f'api_request 콜백 수신: {rqname} {trcode} {record} {next}')

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

    # 응답 실시간 --------------------------------------------------------------------------------------------------
    def OnReceiveRealCondition(self, code, id_type, cond_name, cond_index):
        data = {
            'code': code,
            'type': id_type,
            'cond_name': cond_name,
            'cond_index': cond_index
        }
        #logging.debug(f"Condition: API 서버에서 보냄 {code} {id_type} ({cond_index} : {cond_name})")
        self.order('admin', 'on_fx실시간_조건검색', **data)

    def OnReceiveRealData(self, code, rtype, data):
        # sim_no = 0일 때만 사용 (실제 API 서버)
        if self.sim_no != 0: return
        try:
            dictFID = {}
            if rtype in ['주식체결', '장시작시간']:
                if rtype == '주식체결': dict_temp = dc.fid.주식체결
                elif rtype == '장시작시간': dict_temp = dc.fid.장시작시간
                for key, value in dict_temp.items():
                    data = self.GetCommRealData(code, value)
                    dictFID[key] = data.strip() if type(data) == str else data

                job = { 'code': code, 'rtype': rtype, 'dictFID': dictFID }
                if rtype == '주식체결': 
                    self.frq_order('admin', 'on_fx실시간_주식체결', **job)
                elif rtype == '장시작시간': 
                    self.frq_order('admin', 'on_fx실시간_장운영감시', **job)
                #logging.debug(f"RealData: API 서버에서 보냄 {rtype} {code}")
        except Exception as e:
            logging.error(f"OnReceiveRealData error: {e}", exc_info=True)
            
    def OnReceiveChejanData(self, gubun, item_cnt, fid_list):
        if self.sim_no != 0: 
            self.OnReceiveChejanDataSim(gubun, item_cnt, fid_list)
            return
        
        try:
            dictFID = {}
            if gubun == '0': dict_tmp = dc.fid.주문체결
            elif gubun == '1': dict_tmp = dc.fid.잔고

            for key, value in dict_tmp.items():
                data = self.GetChejanData(value)
                dictFID[key] = data.strip() if type(data) == str else data

            if gubun == '0': self.order('admin', 'odr_recieve_chegyeol_data', dictFID)
            elif gubun == '1': self.order('admin', 'odr_recieve_balance_data', dictFID)
            #logging.debug(f"ChejanData: API 서버에서 보냄 {gubun} {dictFID['종목코드']} {dictFID['종목명']}")

        except Exception as e:
            logging.error(f"OnReceiveChejanData error: {e}", exc_info=True)

    def OnReceiveChejanDataSim(self, code, orderno, order):
        global price_dict
        for cnt in range(3):
            if cnt == 2:
                dictFID = {}
                dictFID['종목코드'] = code
                dictFID['종목명'] = sim.ticker.get(code, {}).get('종목명', '')
                dictFID['보유수량'] = 0 if order['ordtype'] == 2 else order['quantity']
                dictFID['매입단가'] = 0 if order['ordtype'] == 2 else order['price']
                dictFID['주문가능수량'] = 0 if order['ordtype'] == 2 else order['quantity']
                self.order('admin', 'odr_recieve_balance_data', dictFID)
            else:
                dictFID = {}
                dictFID['계좌번호'] = order['accno']
                dictFID['주문번호'] = orderno
                dictFID['종목코드'] = code
                dictFID['종목명'] = sim.ticker.get(code, {}).get('종목명', '')
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
                    dictFID['체결번호'] = f'{random.randint(1000000, 9999999):07d}'
                    dictFID['미체결수량'] = 0
                    dictFID['체결누계금액'] = order['price'] * order['quantity']
                    dictFID['단위체결가'] = order['price']
                    dictFID['단위체결량'] = order['quantity']
                    dictFID['주문가능수량'] = 0 if order['ordtype'] == 2 else order['quantity']

                    portfolio.process_order(dictFID)

                self.order('admin', 'odr_recieve_chegyeol_data', dictFID)
            time.sleep(0.1)
            
    # 응답 메세지 --------------------------------------------------------------------------------------------------
    def OnReceiveMsg(self, screen, rqname, trcode, msg):
        logging.info(f'screen={screen}, rqname={rqname}, trcode={trcode}, msg={msg}')

    # 즉답 관련 메소드 ---------------------------------------------------------------------------------------------
    def GetLoginInfo(self, kind):
        logging.debug(f'GetLoginInfo: kind={kind}')
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            data = self.ocx.dynamicCall("GetLoginInfo(QString)", kind)
            if kind == "ACCNO":
                return data.split(';')[:-1]
            else:
                return data
        else:  # 키움서버 없이 가상 데이터 사용 (sim_no=1)
            if kind == "ACCNO":
                return ['8095802711']
            else:
                return '1'

    def GetConditionNameList(self):
        logging.debug('')
        global cond_data_list
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            data = self.ocx.dynamicCall("GetConditionNameList()")
            conditions = data.split(";")[:-1]
            cond_data_list = []
            for condition in conditions:
                cond_index, cond_name = condition.split('^')
                cond_data_list.append((cond_index, cond_name))
            return cond_data_list
        else:
            return cond_data_list

    def GetCommData(self, trcode, rqname, index, item):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, index, item)
            data = data.strip() if type(data) == str else data
            return data
        return ""

    def GetRepeatCnt(self, trcode, rqname):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
            return count
        return 0

    def GetChejanData(self, fid):
        if self.sim_no == 0:  # 실제 API 서버
            data = self.ocx.dynamicCall("GetChejanData(int)", fid)
            return data
        return ""

    def GetMasterCodeName(self, code):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
            return data
        else:  # 키움서버 없이 가상 데이터 사용 (sim_no=1)
            return sim.ticker.get(code, {}).get('종목명', '')
    
    def GetMasterLastPrice(self, code):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            data = self.ocx.dynamicCall("GetMasterLastPrice(QString)", code)
        else:  # 키움서버 없이 가상 데이터 사용 (sim_no=1)
            data = sim.ticker.get(code, {}).get('전일가', 0)
        data = int(data) if data else 0
        return data

    def GetCommRealData(self, code, fid):
        if self.sim_no == 0:  # 실제 API 서버
            data = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
            return data
        return ""

    def GetCodeListByMarket(self, market):
        """
        시장별 상장된 종목코드를 반환하는 메서드
        :param market: str 
                    0: 코스피, 3: ELW, 4: 뮤추얼펀드 5: 신주인수권 6: 리츠
                    8: ETF, 9: 하이일드펀드, 10: 코스닥, 30: K-OTC, 50: 코넥스(KONEX)
        :return: 종목코드 리스트 예: ["000020", "000040", ...]
        """
        if self.sim_no == 1:
            return list(sim.ticker.keys())
        else:
            data = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market)
            tokens = data.split(';')[:-1]
            return tokens
        
    # 기타 함수 ----------------------------------------------------------------------------------------------------
    def GetCommDataEx(self, trcode, rqname):
        if self.sim_no == 0:  # 실제 API 서버
            data = self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trcode, rqname)
            return data
        return None
    
