from public import hoga, dc, init_logger, profile_operation, QWork
from classes import TimeLimiter, Toast
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
from datetime import datetime
import pandas as pd
import logging
import time
import random
import threading
import pythoncom
import copy
import sys

toast = None #Toast()
ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
req = TimeLimiter(name='req', second=5, minute=100, hour=1000)
def com_request_time_check(kind='order', cond_text = None):
    if kind == 'order':
        wait_time = ord.check_interval()
    elif kind == 'request':
        wait_time = max(req.check_interval(), req.check_condition_interval(cond_text) if cond_text else 0)
    if wait_time > 1666: # 1.666초 이내 주문 제한
        msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {float(wait_time/1000)} 초' \
            if cond_text is None else f'{cond_text} 1분 이내에 같은 조건 호출 불가 합니다. 대기시간: {float(wait_time/1000)} 초'
        #toast.toast(msg, duration=dc.TOAST_TIME)
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
    return True

real_thread = {}
cond_thread = {}
cond_data_list =  [('100', '돌파매수'), ('200', '조건매도')]
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

      # 시뮬레이션 3번 전용 속성들
      self.sim3_date = None  # 시뮬레이션 날짜
      self.sim3_speed = 1.0  # 배속 (0.2, 0.5, 1, 2, 5, 10)
      self.sim3_start_time = None  # 실제 시작 시간 (datetime.now() 기준)
      self.sim3_base_data_time = 0  # 기준 데이터 시간 (초) - 현재 인덱스의 데이터 시간
      self.sim3_condition_data = []  # real_condition 테이블 데이터
      self.sim3_real_data = []  # real_data 테이블 데이터
      self.sim3_condition_index = 0  # 현재 조건검색 데이터 인덱스
      self.sim3_real_index = {}  # 종목별 실시간 데이터 인덱스
      self.sim3_registered_codes = set()  # 등록된 종목 코드들
      
      # 시뮬레이션 3번 컨트롤 상태 변수들
      self.sim3_is_paused = False  # 일시정지 상태
      self.sim3_is_running = False  # 실행 상태
      self.sim3_is_stopped = True  # 정지 상태
      self.sim3_condition_thread = None  # 조건검색 스레드 참조
      self.sim3_real_threads = {}  # 실시간 데이터 스레드들 참조
      
      # 차트 데이터 기반 패턴 분석 결과 (시뮬레이션 2번용)
      self.chart_patterns = {}  # 종목별 차트 패턴 정보

   def _initialize_data(self):
      """데이터 초기화 (시뮬레이션 1,2번용)"""
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
      """차트 데이터에서 종목 정보 추출 (시뮬레이션 1,2번용)"""
      self.ticker = {}
      for data in self.chart_data:
         code = data.get('종목코드')
         if code and code not in self.ticker:
            self.ticker[code] = {
               '종목명': data.get('종목명', ''),
               '전일가': 0  # 필요시 설정
            }

   def extract_ticker_info_from_db(self):
        """데이터베이스 데이터에서 종목 정보 추출 (시뮬레이션 3번용)"""
        self.ticker = {}
        
        # 조건검색 데이터에서 종목 정보 추출
        for data in self.sim3_condition_data:
            code = data.get('종목코드')
            if code and code not in self.ticker:
                self.ticker[code] = {
                '종목명': data.get('종목명', ''),
                '전일가': 0  # 필요시 실시간 데이터에서 추출
                }
        
        # 실시간 데이터에서 종목 정보 보완
        for data in self.sim3_real_data:
            code = data.get('종목코드')
            if code and code not in self.ticker:
                self.ticker[code] = {
                '종목명': '',  # 실시간 데이터에는 종목명이 없을 수 있음
                '전일가': 0
                }

   def sim3_reset_to_start(self):
        """시뮬레이션 3번을 처음으로 리셋"""
        logging.info("시뮬레이션 3번 처음으로 리셋")
        self.sim3_condition_index = 0
        self.sim3_real_index = {}
        self.sim3_registered_codes = set()
        self.sim3_start_time = None
        self.sim3_base_data_time = 0
        self.sim3_is_paused = False
        self.sim3_is_running = False
        self.sim3_is_stopped = True

   def sim3_pause(self):
        """시뮬레이션 3번 일시정지"""
        if not self.sim3_is_running or self.sim3_is_paused:
            return
        logging.info("시뮬레이션 3번 일시정지")
        self.sim3_is_paused = True
        # 인덱스는 그대로 유지됨

   def sim3_start(self):
        """시뮬레이션 3번 시작 (일시정지된 위치부터 재시작)"""
        if not self.sim3_is_paused:
            # 처음 시작하는 경우
            logging.info("시뮬레이션 3번 처음 시작")
            self.sim3_is_running = True
            self.sim3_is_stopped = False
            self.sim3_is_paused = False
        else:
            # 일시정지된 위치부터 재시작 - 다음 데이터와 시작 시간 동기화
            logging.info("시뮬레이션 3번 재시작")
            self.sim3_is_paused = False
            
            # 다음 처리할 데이터의 시간으로 기준 시간 재설정
            if self.sim3_condition_data and self.sim3_condition_index < len(self.sim3_condition_data):
                next_data = self.sim3_condition_data[self.sim3_condition_index]
                time_full = next_data.get('처리일시', '090000')
                time_str = time_full[-6:] if len(time_full) >= 6 else time_full  # HHMMSS 추출
                hour = int(time_str[:2])
                minute = int(time_str[2:4])
                second = int(time_str[4:6]) if len(time_str) >= 6 else 0
                self.sim3_base_data_time = hour * 3600 + minute * 60 + second
                logging.debug(f"재시작: 다음 데이터 처리일시={time_full}, 시간={time_str}, 기준시간={self.sim3_base_data_time}초")
        
        # 실제 시작 시간 설정
        self.sim3_start_time = datetime.now()

   def sim3_stop(self):
        """시뮬레이션 3번 정지 (완전 종료)"""
        logging.info("시뮬레이션 3번 정지")
        self.sim3_is_running = False
        self.sim3_is_stopped = True
        self.sim3_is_paused = False
        self.sim3_start_time = None

   def update_price(self, code):
      """종목별 가격 업데이트 (시뮬레이션 1,2번용)"""
      price_info = self.price_data[code]

      # 새로운 가격 계산
      new_price = self.get_next_price(code)

      # 가격 반영
      price_info["last_price"] = price_info["current_price"]
      price_info["current_price"] = new_price

      return new_price

   def get_next_price(self, code):
      """다음 가격 계산 (시뮬레이션 1,2번용)"""
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
      """타입 전환 체크 (시뮬레이션 1,2번용)"""
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
      """종목 타입 이동 (시뮬레이션 1,2번용)"""
      if code in self.type_groups[from_type]:
         self.type_groups[from_type].remove(code)
         self.type_groups[to_type].append(code)

   def analyze_chart_pattern(self, chart_data, code):
      """차트 데이터에서 가격/거래량 패턴 분석 (시뮬레이션 2번용)"""
      try:
         if not chart_data or len(chart_data) < 10:
            return None
         
         prices = []
         volumes = []
         price_changes = []
         
         for i, bar in enumerate(chart_data[:100]):  # 최근 100봉 분석
            price = int(bar.get('현재가', 0))
            volume = int(bar.get('거래량', 0))
            
            if price > 0:
               prices.append(price)
               if volumes:
                  volumes.append(volume)
            
            if i > 0 and len(prices) >= 2:
               change = abs(prices[-1] - prices[-2])
               if prices[-2] > 0:
                  change_pct = (change / prices[-2]) * 100
                  price_changes.append(change_pct)
         
         if not prices or not volumes:
            return None
         
         import statistics
         
         # 가격 변동성 분석
         avg_price = statistics.mean(prices)
         price_std = statistics.stdev(prices) if len(prices) > 1 else 0
         avg_change_pct = statistics.mean(price_changes) if price_changes else 0
         max_change_pct = max(price_changes) if price_changes else 0
         
         # 거래량 분석
         avg_volume = statistics.mean(volumes)
         max_volume = max(volumes)
         volume_std = statistics.stdev(volumes) if len(volumes) > 1 else 0
         
         # 급등락 감지 (변동폭이 큰 경우)
         spike_threshold = avg_change_pct * 2 if avg_change_pct > 0 else 1.0
         spike_indices = [i for i, change in enumerate(price_changes) if change > spike_threshold]
         
         # 급등락시 거래량 배율 계산
         spike_volume_ratio = 1.0
         if spike_indices and len(spike_indices) < len(volumes):
            spike_volumes = [volumes[i] for i in spike_indices if i < len(volumes)]
            if spike_volumes:
               spike_volume_ratio = statistics.mean(spike_volumes) / avg_volume if avg_volume > 0 else 2.0
         
         pattern = {
            'avg_price': avg_price,
            'price_std': price_std,
            'avg_change_pct': avg_change_pct,
            'max_change_pct': max_change_pct,
            'avg_volume': avg_volume,
            'max_volume': max_volume,
            'volume_std': volume_std,
            'spike_volume_ratio': max(spike_volume_ratio, 1.5),  # 최소 1.5배
            'price_trend': 1 if prices[-1] > prices[0] else -1,  # 추세 방향
         }
         
         return pattern
         
      except Exception as e:
         logging.error(f"차트 패턴 분석 오류 {code}: {e}")
         return None

   def get_next_price_from_chart(self, code):
      """차트 패턴 기반 다음 가격 계산 (시뮬레이션 2번용)"""
      try:
         if code not in self.chart_patterns or not self.chart_patterns[code]:
            # 패턴 정보 없으면 기존 방식 사용
            return self.get_next_price(code)
         
         pattern = self.chart_patterns[code]
         price_info = self.price_data[code]
         current_price = price_info["current_price"]
         base_price = price_info["base_price"]
         
         # 차트 변동성 기반 변동폭 결정
         change_pct = random.gauss(pattern['avg_change_pct'], pattern['avg_change_pct'] * 0.5)
         change_pct = abs(change_pct)
         
         # 급등락 확률 (5% 확률로 큰 변동)
         if random.random() < 0.05:
            change_pct = random.uniform(pattern['avg_change_pct'] * 2, pattern['max_change_pct'])
            price_info['is_spike'] = True
         else:
            price_info['is_spike'] = False
         
         # 추세 반영 (70% 추세 방향, 30% 역방향)
         current_trend = 1 if current_price > base_price else -1
         if random.random() < 0.7:
            direction = pattern['price_trend']
         else:
            direction = -pattern['price_trend']
         
         # 가격 계산
         change_amount = int(current_price * (change_pct / 100))
         new_price = current_price + (change_amount * direction)
         
         # 호가 단위로 조정
         new_price = hoga(new_price, 0)  # 호가 단위로 반올림
         
         # 가격 제한 (전일가 대비 ±30%)
         min_price = int(base_price * 0.7)
         max_price = int(base_price * 1.3)
         new_price = max(min_price, min(max_price, new_price))
         
         price_info["current_price"] = new_price
         
         return new_price
         
      except Exception as e:
         logging.error(f"차트 기반 가격 생성 오류 {code}: {e}")
         return self.get_next_price(code)

   def get_volume_based_on_price_change(self, code, current_price, last_price):
      """가격 변동폭에 따른 거래량 생성 (시뮬레이션 2번용)"""
      try:
         if code not in self.chart_patterns or not self.chart_patterns[code]:
            # 패턴 정보 없으면 기본 거래량
            return random.randint(50, 200)
         
         pattern = self.chart_patterns[code]
         price_info = self.price_data.get(code, {})
         
         # 기본 거래량 (평균 거래량 기반)
         base_volume = max(int(pattern['avg_volume'] * 0.001), 50)  # 스케일 다운
         
         # 가격 변동폭 계산
         if last_price > 0:
            change_pct = abs((current_price - last_price) / last_price * 100)
         else:
            change_pct = 0
         
         # 급등락 여부 확인
         is_spike = price_info.get('is_spike', False)
         
         if is_spike or change_pct > pattern['avg_change_pct'] * 1.5:
            # 급등락시 거래량 증가
            volume_multiplier = pattern['spike_volume_ratio']
            volume = int(base_volume * volume_multiplier * random.uniform(1.5, 3.0))
         else:
            # 일반 변동
            volume_ratio = 1.0 + (change_pct / pattern['avg_change_pct']) if pattern['avg_change_pct'] > 0 else 1.0
            volume = int(base_volume * volume_ratio * random.uniform(0.5, 1.5))
         
         # 거래량 제한
         volume = max(10, min(volume, int(pattern['max_volume'] * 0.01)))
         
         return volume
         
      except Exception as e:
         logging.error(f"거래량 생성 오류 {code}: {e}")
         return random.randint(50, 200)

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

   def load_chart_and_analyze(self, code):
      """종목 발생시 차트 데이터 로드 및 패턴 분석 (sim_no==2용)"""
      try:
         if self.api.sim_no != 2:
            return
         
         if code in sim.chart_patterns:
            return  # 이미 분석된 종목
         
         # 종목 정보 추가
         if code not in sim.ticker:
            sim.ticker[code] = {
               '종목명': self.api.GetMasterCodeName(code),
               '전일가': self.api.GetMasterLastPrice(code),
            }
            
            # 가격 데이터 초기화
            base_price = sim.ticker[code]["전일가"]
            sim.price_data[code] = {
               "base_price": base_price,
               "current_price": base_price,
               "type_change_time": None,
               "last_update_time": time.time()
            }
         
         # 차트 데이터 로드 및 패턴 분석
         logging.info(f'조건검색 종목 발생 - 차트 데이터 로드: {code} {sim.ticker[code]["종목명"]}')
         chart_data = self.api.get_chart_data(code, 'mi', tick=3, times=1)
         
         if chart_data:
            pattern = sim.analyze_chart_pattern(chart_data, code)
            if pattern:
               sim.chart_patterns[code] = pattern
               logging.info(f'패턴 분석 완료 {code}: avg_vol={pattern["avg_volume"]:.0f}, avg_change={pattern["avg_change_pct"]:.2f}%')
            else:
               logging.warning(f'패턴 분석 실패 {code}')
         else:
            logging.warning(f'차트 데이터 로드 실패 {code}')
            
      except Exception as e:
         logging.error(f'차트 데이터 로드 오류 {code}: {e}')

   def run(self):
      while self.is_running:
         if not self.api.connected:
            time.sleep(0.01)
            continue
         code = random.choice(list(sim.ticker.keys()))
         type = random.choice(['D', 'I'])

         current_count = len(self.current_stocks)
         if current_count >= 3 and type == 'I': continue

         # 편입(I) 발생시 차트 데이터 로드 및 패턴 분석
         if type == 'I':
            self.load_chart_and_analyze(code)

         self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, type, self.cond_name, int(self.cond_index))))

         if type == 'I':
            self.current_stocks.add(code)
         else:
            if code in self.current_stocks:
               self.current_stocks.remove(code)

         interval = random.uniform(0.3, 3)
         if self.is_running:
            time.sleep(interval)

   def stop(self):
      self.is_running = False

class OnReceiveRealDataSim1And2(QThread):
   """시뮬레이션 1, 2번용 실시간 데이터 쓰레드"""
   def __init__(self, api):
      super().__init__()
      self.daemon = True
      self.is_running = True
      self.api = api
      self.order = api.order
      self.code_tot = {}
      self.start_time = time.time()

   def run(self):
      self.start_time = time.time()
      batch = {}
      while self.is_running:
         if not self.api.connected or not ready_tickers:
            time.sleep(0.01)
            continue
         
         # SetRealReg로 등록된 종목만 처리 (실제 흐름과 동일)
         global real_tickers
         if not real_tickers:
            time.sleep(0.01)
            continue
         
         for code in list(real_tickers):
            if not self.is_running:
               break
            
            # 종목 정보가 없으면 스킵
            if code not in sim.ticker:
               continue
            
            # sim_no==2인 경우 조건검색으로 발생한 종목(price_data에 있는)만 처리
            if self.api.sim_no == 2 and code not in sim.price_data:
               continue
            
            # sim_no==1인 경우 price_data 초기화 확인
            if self.api.sim_no == 1 and code not in sim.price_data:
               continue
            
            # 이전 가격 저장
            last_price = price_dict.get(code, sim.ticker[code]["전일가"])
            
            # 시뮬레이터에서 현재가 계산
            if self.api.sim_no == 2 and code in sim.chart_patterns:
               # 차트 패턴 기반 가격 생성
               current_price = sim.get_next_price_from_chart(code)
            else:
               # 기존 방식 (sim_no==1)
               current_price = sim.update_price(code)
            price_dict[code] = current_price

            # 거래량 계산
            if self.api.sim_no == 2 and code in sim.chart_patterns:
               # 가격 변동폭 기반 거래량 생성
               qty = sim.get_volume_based_on_price_change(code, current_price, last_price)
            else:
               # 기존 방식
               qty = random.randint(0, 50)
            
            if code not in self.code_tot:
               self.code_tot[code] = {'totoal_qty': 50000, 'total_price': current_price * 50000}
            self.code_tot[code]['totoal_qty'] += qty
            self.code_tot[code]['total_price'] += qty * current_price

            # 실시간 데이터 전송
            dictFID = {
               '종목코드': code,
               '종목명': sim.ticker.get(code, {}).get('종목명', ''),
               '현재가': f'{current_price:15d}',
               '등락율': f'{round((current_price - sim.ticker[code]["전일가"]) / sim.ticker[code]["전일가"] * 100, 2):12.2f}',
               '거래량': f'{qty:15d}',
               '누적거래량': f'{self.code_tot[code]["totoal_qty"]:15d}',
               '누적거래대금': f'{self.code_tot[code]["total_price"]:15d}',
               '체결시간': time.strftime('%H%M%S', time.localtime()),
            }

            # 포트폴리오 업데이트
            portfolio.update_stock_price(code, current_price)

            # 실시간 데이터 전송
            job = { 'code': code, 'rtype': '주식체결', 'dictFID': dictFID }
            self.order('rcv', 'proxy_method', QWork(method='on_receive_real_data', args=(code, '주식체결', dictFID)))
            #self.order('rcv', 'on_receive_real_data', **job)
            time.sleep(0.005)

   def stop(self):
      self.is_running = False

class OnReceiveRealConditionSim3(QThread):
   """시뮬레이션 3번용 실시간 조건검색 쓰레드"""
   def __init__(self, cond_name, cond_index, api):
      super().__init__()
      self.daemon = True
      self.cond_name = cond_name
      self.cond_index = cond_index
      self.is_running = True
      self.api = api
      self.order = api.order

   def run(self):
      """실시간 조건검색 데이터를 시간 순서대로 배속에 따라 전송"""
      if not sim.sim3_condition_data:
         logging.warning("시뮬레이션 3번: 조건검색 데이터가 없습니다.")
         return
      
      # 첫 시작 시 기준 시간 설정
      if sim.sim3_base_data_time == 0:
         first_data = sim.sim3_condition_data[0]
         # 처리일시에서 시간 추출 (YYYYMMDDHHMMSS 형식 또는 HHMMSS 형식)
         time_full = first_data.get('처리일시', '090000')
         time_str = time_full[-6:] if len(time_full) >= 6 else time_full  # HHMMSS 부분 추출
         hour = int(time_str[:2])
         minute = int(time_str[2:4])
         second = int(time_str[4:6]) if len(time_str) >= 6 else 0
         sim.sim3_base_data_time = hour * 3600 + minute * 60 + second
      
      # 실제 시작 시간 설정
      if not sim.sim3_start_time:
         sim.sim3_start_time = datetime.now()
      
      while self.is_running and sim.sim3_condition_index < len(sim.sim3_condition_data):
         if not self.api.connected:
            time.sleep(0.01)
            continue
            
         # 정지 상태 확인 (최우선)
         if sim.sim3_is_stopped:
            break
            
         # 일시정지 상태 확인
         if sim.sim3_is_paused:
            time.sleep(0.1)
            continue
            
         # 현재 처리할 데이터
         current_data = sim.sim3_condition_data[sim.sim3_condition_index]
         
         # 현재 데이터 시간 (초) - 처리일시에서 HHMMSS 추출
         data_time_full = current_data.get('처리일시', '090000')
         data_time_str = data_time_full[-6:] if len(data_time_full) >= 6 else data_time_full
         data_hour = int(data_time_str[:2])
         data_minute = int(data_time_str[2:4]) 
         data_second = int(data_time_str[4:6]) if len(data_time_str) >= 6 else 0
         data_time_seconds = data_hour * 3600 + data_minute * 60 + data_second
         
         # 실제 경과 시간 (초)
         elapsed_real = (datetime.now() - sim.sim3_start_time).total_seconds()
         # 시뮬레이션 현재 시간 = 기준 시간 + (경과 시간 × 배속)
         sim_current_time = sim.sim3_base_data_time + (elapsed_real * sim.sim3_speed)
         
         # 현재 데이터 시간이 되면 전송
         if data_time_seconds <= sim_current_time:
            # 조건검색 데이터 전송
            code = current_data.get('종목코드', '')
            type = current_data.get('조건구분', 'I')  # I: 편입, D: 이탈
            
            if code:
               self.order('rcv', 'proxy_method', QWork(
                  method='on_receive_real_condition', 
                  args=(code, type, self.cond_name, int(self.cond_index))
               ))
               
               # 등록된 종목 코드 추가
               if type == 'I':
                  sim.sim3_registered_codes.add(code)
               elif type == 'D' and code in sim.sim3_registered_codes:
                  sim.sim3_registered_codes.discard(code)
            
            sim.sim3_condition_index += 1
         else:
            # 아직 시간이 안 됨 - 짧은 대기
            time.sleep(0.01)

   def stop(self):
      self.is_running = False

class OnReceiveRealDataSim3(QThread):
   """시뮬레이션 3번용 실시간 데이터 쓰레드"""
   def __init__(self, api, code_list):
      super().__init__()
      self.daemon = True
      self.is_running = True
      self.api = api
      self.order = api.order
      self.code_list = code_list if code_list else []

   def run(self):
      """등록된 종목들의 실시간 데이터를 시간 순서대로 배속에 따라 전송"""
      if not sim.sim3_real_data:
         logging.warning("시뮬레이션 3번: 실시간 데이터가 없습니다.")
         return
      
      # 종목별 실시간 데이터 인덱스 초기화
      for code in self.code_list:
         if code not in sim.sim3_real_index:
            sim.sim3_real_index[code] = 0
      
      while self.is_running:
         if not self.api.connected:
            time.sleep(0.01)
            continue
            
         # 정지 상태 확인 (최우선)
         if sim.sim3_is_stopped:
            break
            
         # 일시정지 상태 확인
         if sim.sim3_is_paused:
            time.sleep(0.1)
            continue
            
         # 기준 시간과 시작 시간 확인
         if not sim.sim3_start_time or sim.sim3_base_data_time == 0:
            time.sleep(0.01)
            continue
            
         # 실제 경과 시간 (초)
         elapsed_real = (datetime.now() - sim.sim3_start_time).total_seconds()
         # 시뮬레이션 현재 시간 = 기준 시간 + (경과 시간 × 배속)
         sim_current_time_seconds = sim.sim3_base_data_time + (elapsed_real * sim.sim3_speed)
         
         # 등록된 종목들의 실시간 데이터 처리
         for code in list(sim.sim3_registered_codes):
            # 정지 상태 확인 (최우선)
            if not self.is_running or sim.sim3_is_stopped:
               break
               
            # 일시정지 상태 확인
            if sim.sim3_is_paused:
               time.sleep(0.1)
               continue
               
            # 해당 종목의 데이터 찾기
            code_data = [d for d in sim.sim3_real_data if d.get('종목코드') == code]
            if not code_data:
               continue
               
            current_index = sim.sim3_real_index.get(code, 0)
            if current_index >= len(code_data):
               continue
               
            data = code_data[current_index]
            # 체결시간에서 HHMMSS 추출
            data_time_str = data.get('체결시간', '090000')[-6:]
            data_hour = int(data_time_str[:2])
            data_minute = int(data_time_str[2:4])
            data_second = int(data_time_str[4:6]) if len(data_time_str) >= 6 else 0
            data_time_seconds = data_hour * 3600 + data_minute * 60 + data_second
            
            # 현재 시뮬레이션 시간과 비교
            if data_time_seconds <= sim_current_time_seconds:
               # 실시간 데이터 전송
               dictFID = {
                  '종목코드': code,
                  '종목명': self.api.GetMasterCodeName(code),
                  '현재가': f"{int(data.get('현재가', 0)):15d}",
                  '거래량': f"{int(data.get('거래량', 0)):15d}",
                  '거래대금': f"{int(data.get('거래대금', 0)):15d}",
                  '누적거래량': f"{int(data.get('누적거래량', 0)):15d}",
                  '누적거래대금': f"{int(data.get('누적거래대금', 0)):15d}",
                  '체결시간': data.get('체결시간', ''),
               }
               
               # 포트폴리오 업데이트
               portfolio.update_stock_price(code, int(data.get('현재가', 0)))
               
               # 실시간 데이터 전송
               self.order('rcv', 'proxy_method', QWork(
                  method='on_receive_real_data', 
                  args=(code, '주식체결', dictFID)
               ))
               
               # 인덱스 증가
               sim.sim3_real_index[code] = current_index + 1
         
         # 짧은 대기 (너무 빠른 처리 방지)
         time.sleep(0.01)

   def stop(self):
      self.is_running = False

class APIServer:
    def __init__(self):
        self.name = 'api'
        self.sim_no = 0
        self.app = None
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

    def cleanup(self):
        if self.sim_no > 0:
            self.thread_cleanup()
        self.connected = False
        logging.info("APIServer 종료")

    def initialize(self):
        init_logger()

    def api_init(self, sim_no=0, log_level=logging.DEBUG):
        try:
            import os
            pid = os.getpid()
            self.sim_no = sim_no
            self.set_log_level(log_level)
            
            if self.app is None:
                self.app = QApplication(sys.argv)
            
            if self.sim_no != 1 and self.ocx is None:
                logging.debug(f"ActiveX 컨트롤 생성 시작: KHOPENAPI.KHOpenAPICtrl.1")
                self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
                self._set_signal_slots()

            logging.info(f'api_init completed: pid={pid} (Sim mode {self.sim_no}) ocx={self.ocx}')
            
        except Exception as e:
            logging.error(f"API 초기화 오류: {type(e).__name__} - {e}", exc_info=True)

    def set_tickers(self, speed=None, dt=None):
        if self.sim_no == 0:  # 실제 API 서버는 별도 처리 필요 없음
            pass
        elif self.sim_no == 1:  # 키움서버 없이 가상 데이터 사용
            sim.ticker = dc.sim.ticker
            sim._initialize_data()
        elif self.sim_no == 2:  # 키움서버 사용, 실시간 데이터 가상 생성
            # 조건검색으로 종목 발생시 차트 데이터 로드하므로 초기 종목 풀만 준비
            codes = self.GetCodeListByMarket('NXT')
            if codes:
                # 조건검색에서 랜덤 선택할 종목 풀 준비 (100개)
                selected_codes = random.sample(codes, min(100, len(codes)))
                logging.info(f'sim_no=2 종목 풀 준비: {len(selected_codes)}개')
                sim.ticker = {}
                sim.chart_patterns = {}
                
                # 종목 풀만 등록 (차트 데이터는 조건검색 발생시 로드)
                for code in selected_codes:
                    sim.ticker[code] = {
                        '종목명': self.GetMasterCodeName(code),
                        '전일가': self.GetMasterLastPrice(code),
                    }
                
                logging.info(f'sim_no=2 초기화 완료: 종목 풀 {len(sim.ticker)}개 준비됨 (차트는 조건검색 발생시 로드)')
            else:
                logging.warning('GetCodeListByMarket 결과 없음 *************')
                logging.warning('시뮬레이션 모드 1로 변경 *************')
                self.sim_no = 1
                sim.ticker = dc.sim.ticker
                sim._initialize_data()
        elif self.sim_no == 3:  # 키움서버 사용, 데이터베이스 데이터 이용
            # 기본값 설정 (나중에 start 버튼에서 실제 값으로 변경)
            # sim.sim3_speed = speed if speed else 1.0
            # sim.sim3_date = dt if dt else datetime.now().strftime('%Y-%m-%d')
            
            # # 데이터 로드
            # sim.sim3_condition_data, sim.sim3_real_data = self.get_simulation_data()
            # sim.extract_ticker_info_from_db()
            
            # logging.info(f"시뮬레이션 3번 초기 설정: 배속={sim.sim3_speed}, 날짜={sim.sim3_date}")
            return
        
        global ready_tickers
        ready_tickers = True

    def get_simulation_data(self):
        """데이터베이스에서 시뮬레이션 3번 데이터 로드"""
        try:
            from dbm_server import db_columns
            
            # DBM 서버에서 데이터 가져오기
            condition_sql = db_columns.COND_SELECT_DATE
            real_sql = db_columns.REAL_SELECT_DATE
            
            # 날짜 형식 변환 (YYYY-MM-DD -> YYYY-MM-DD)
            date_param = sim.sim3_date
            
            # 조건검색 데이터 로드
            condition_data = self.answer('dbm', 'execute_query', sql=condition_sql, db='db', params=(date_param,))
            logging.info(f"조건검색 데이터 로드 완료: {condition_data}")
            
            # 실시간 데이터 로드  
            real_data = self.answer('dbm', 'execute_query', sql=real_sql, db='db', params=(date_param[:8],))  # YYYYMMDD 형식
            logging.info(f"실시간 데이터 로드 완료: {real_data}")

            if condition_data is None: condition_data = []
            if real_data is None: real_data = []
                
            # 시간 순으로 정렬
            # real_condition: 처리일시 사용 (중복 없음)
            # real_data: 체결시간 사용 (중복 있음 - 나중 데이터만 사용)
            condition_data.sort(key=lambda x: x.get('처리일시', ''))
            real_data.sort(key=lambda x: x.get('체결시간', ''))
            
            # real_data만 중복 제거 (같은 시간, 같은 종목코드의 나중 데이터 우선)
            real_unique = {}
            for data in real_data:
                key = f"{data.get('체결시간', '')}_{data.get('종목코드', '')}"
                real_unique[key] = data
            real_data = list(real_unique.values())
            
            logging.info(f"시뮬레이션 3번 데이터 로드 완료: 조건검색={len(condition_data)}, 실시간={len(real_data)}")
            return condition_data, real_data
            
        except Exception as e:
            logging.error(f"시뮬레이션 3번 데이터 로드 오류: {type(e).__name__} - {e}")
            return [], []

    def sim3_memory_load(self):
        """시뮬레이션 3번 메모리 로드"""
        sim.sim3_condition_data, sim.sim3_real_data = self.get_simulation_data()
        sim.extract_ticker_info_from_db()
        logging.info("시뮬레이션 3번 메모리 로드 완료")

        global ready_tickers
        ready_tickers = True
        return True

    def sim3_control_reset(self):
        """시뮬레이션 3번 처음으로 리셋 (모든 상태 초기화)"""
        sim.sim3_reset_to_start()
        logging.info("시뮬레이션 3번 처음으로 리셋 완료")
        return True

    def sim3_control_pause(self):
        """시뮬레이션 3번 일시정지 (현재 위치에서 멈춤)"""
        if not sim.sim3_is_running:
            logging.warning("시뮬레이션이 실행 중이 아닙니다.")
            return False
        sim.sim3_pause()
        logging.info("시뮬레이션 3번 일시정지 완료")
        return True

    def sim3_control_start(self, speed=None, dt=None):
        """시뮬레이션 3번 시작 (현재 위치에서 재생, 배속/날짜 설정 가능)"""
        if not ready_tickers:
            logging.warning("시뮬레이션 3번 데이터 로드 전 입니다.")
            return False
        
        # 배속/날짜 변경 (GUI에서 전달된 경우)
        if speed is not None: self.sim3_control_set_speed(speed)
        if dt is not None: self.sim3_control_set_date(dt)
        
        # 시작 (일시정지 상태든 아니든 상관없이)
        sim.sim3_start()
        logging.info("시뮬레이션 3번 시작 완료")
        
        return True

    def sim3_control_stop(self):
        """시뮬레이션 3번 정지 (처음으로 리셋, 스레드는 유지)"""
        # 처음으로 리셋
        sim.sim3_reset_to_start()
        logging.info("시뮬레이션 3번 정지 완료 (스레드 유지, 처음으로 리셋)")
        return True

    def sim3_control_set_speed(self, speed):
        """시뮬레이션 3번 배속 변경"""
        if self.sim_no != 3:
            logging.warning("시뮬레이션 3번이 아닙니다.")
            return False
        
        if speed not in [0.2, 0.5, 1, 2, 5, 10]:
            logging.warning(f"지원하지 않는 배속입니다: {speed}")
            return False
            
        sim.sim3_speed = speed
        logging.info(f"시뮬레이션 3번 배속 변경: {speed}")
        return True

    def sim3_control_set_date(self, dt):
        """시뮬레이션 3번 기준일자 변경"""
        if self.sim_no != 3:
            logging.warning("시뮬레이션 3번이 아닙니다.")
            return False
        
        # 날짜 형식 검증 (YYYY-MM-DD)
        try:
            from datetime import datetime
            datetime.strptime(dt, '%Y-%m-%d')
        except ValueError:
            logging.warning(f"잘못된 날짜 형식입니다: {dt}")
            return False
        
        sim.sim3_date = dt
        
        # 새로운 날짜의 데이터 로드
        try:
            sim.sim3_condition_data, sim.sim3_real_data = self.get_simulation_data()
            sim.extract_ticker_info_from_db()
            logging.info(f"시뮬레이션 3번 기준일자 변경 및 데이터 로드 완료: {dt}")
            return True
        except Exception as e:
            logging.error(f"데이터 로드 오류: {e}")
            return False

    def sim3_get_status(self):
        """시뮬레이션 3번 상태 조회"""
        if self.sim_no != 3:
            return None
        return {
            'is_running': sim.sim3_is_running,
            'is_paused': sim.sim3_is_paused,
            'is_stopped': sim.sim3_is_stopped,
            'condition_index': sim.sim3_condition_index,
            'total_conditions': len(sim.sim3_condition_data),
            'registered_codes': len(sim.sim3_registered_codes),
            'real_data_index': dict(sim.sim3_real_index),
            'speed': sim.sim3_speed,
            'date': sim.sim3_date
        }
    
    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'API 로그 레벨 설정: {level}')

    def thread_cleanup(self):
        # 실시간 데이터 스레드 정리
        global real_tickers, real_thread, cond_thread   
        real_tickers.clear()    
        logging.debug(f'실시간 데이터 스레드 삭제전: {real_thread}')
        for screen in list(real_thread.keys()):
            if real_thread[screen]:
                try:
                    real_thread[screen].stop()
                    real_thread[screen].quit()
                    finish = real_thread[screen].wait(5000)  # 최대 1초 대기
                    if not finish:
                        logging.error(f"API 실시간 스레드 정리 오류: {screen}")
                    else:
                        logging.debug(f"API 실시간 데이터 스레드 정리: {screen}")
                    del real_thread[screen]
                except Exception as e:
                    logging.error(f"실시간 스레드 정리 오류: {e}")
        
        # 조건검색 스레드 정리
        logging.debug(f'조건검색 스레드 삭제전: {cond_thread}')
        for screen in list(cond_thread.keys()):
            if cond_thread[screen]:
                try:
                    cond_thread[screen].stop()
                    cond_thread[screen].quit()
                    finish = cond_thread[screen].wait(5000)  # 최대 1초 대기
                    if not finish:
                        logging.error(f"API 조건검색 스레드 정리 오류: {screen}")
                    else:
                        logging.debug(f"API 조건검색 스레드 정리: {screen}")
                    del cond_thread[screen]
                except Exception as e:
                    logging.error(f"조건검색 스레드 정리 오류: {e}")
        
        # 시뮬레이션 3번 전용 스레드 정리
        if self.sim_no == 3:
            logging.debug(f'시뮬레이션 3번 스레드 정리 시작')
            
            # 조건검색 스레드 정리
            if sim.sim3_condition_thread:
                try:
                    sim.sim3_condition_thread.stop()
                    sim.sim3_condition_thread.quit()
                    finish = sim.sim3_condition_thread.wait(5000)
                    if not finish:
                        logging.error("시뮬레이션 3번 조건검색 스레드 정리 오류")
                    else:
                        logging.debug("시뮬레이션 3번 조건검색 스레드 정리 완료")
                    sim.sim3_condition_thread = None
                except Exception as e:
                    logging.error(f"시뮬레이션 3번 조건검색 스레드 정리 오류: {e}")
            
            # 실시간 데이터 스레드들 정리
            logging.debug(f'시뮬레이션 3번 실시간 스레드 정리전: {sim.sim3_real_threads}')
            for screen in list(sim.sim3_real_threads.keys()):
                thread = sim.sim3_real_threads[screen]
                if thread:
                    try:
                        thread.stop()
                        thread.quit()
                        finish = thread.wait(5000)
                        if not finish:
                            logging.error(f"시뮬레이션 3번 실시간 스레드 정리 오류: {screen}")
                        else:
                            logging.debug(f"시뮬레이션 3번 실시간 스레드 정리 완료: {screen}")
                        del sim.sim3_real_threads[screen]
                    except Exception as e:
                        logging.error(f"시뮬레이션 3번 실시간 스레드 정리 오류: {e}")
            
            # 시뮬레이션 3번 상태 초기화
            sim.sim3_reset_to_start()
            logging.debug("시뮬레이션 3번 상태 초기화 완료")

    # 추가 메서드 --------------------------------------------------------------------------------------------------
    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', wait=5):
        #logging.debug(f'api_request: rqname={rqname}, trcode={trcode}, input={input}, next={next}, screen={screen}, form={form}, wait={wait}')
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
                if time.time() - start_time > wait:
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

    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        global real_thread, real_tickers
        if isinstance(code_list, str):
            code_list = [code_list]
        
        logging.debug(f'SetRealReg: screen={screen}, codes={code_list}, fids={fid_list}, opt={opt_type}')
        
        if self.sim_no == 0:  # 실제 API 서버
            codes_str = ';'.join(code_list) if isinstance(code_list, list) else code_list
            fids_str = ';'.join(map(str, fid_list)) if isinstance(fid_list, list) else fid_list
            
            try:
                result = self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen, codes_str, fids_str, opt_type)
                logging.debug(f'SetRealReg 결과: {result}')
                return result
            except Exception as e:
                logging.error(f"SetRealReg 오류: {type(e).__name__} - {e}")
                return 0
        elif self.sim_no == 3:  # 시뮬레이션 3번
            for code in code_list:
                real_tickers.add(code)
            
            # 시뮬레이션 3번용 실시간 데이터 쓰레드 시작
            if screen not in real_thread:
                real_thread[screen] = OnReceiveRealDataSim3(self, code_list)
                sim.sim3_real_threads[screen] = real_thread[screen]  # 스레드 참조 저장
                real_thread[screen].start()
                logging.debug(f'시뮬레이션 3번 실시간 데이터 쓰레드 시작: {screen} {code_list}')
            return 1
        else:  # 시뮬레이션 1, 2번
            for code in code_list:
                real_tickers.add(code)
            
            if screen not in real_thread:
                real_thread[screen] = OnReceiveRealDataSim1And2(self)
                real_thread[screen].start()
                logging.debug(f'시뮬레이션 1,2번 실시간 데이터 쓰레드 시작: {screen}')
            return 1

    def SetRealRemove(self, screen, del_code):
        global real_thread, real_tickers
        logging.debug(f'SetRealRemove: screen={screen}, del_code={del_code}')
        if self.sim_no == 0:  # 실제 API 서버
            ret = self.ocx.dynamicCall("SetRealRemove(QString, QString)", screen, del_code)
            return ret
        else:  # 시뮬레이션 모드
            # real_tickers에서 종목 제거 (실제 흐름과 동일)
            if del_code == 'ALL':
                real_tickers.clear()
                logging.debug(f'모든 실시간 종목 제거')
            elif del_code:
                if del_code in real_tickers:
                    real_tickers.discard(del_code)
                    logging.debug(f'실시간 종목 제거: {del_code}')
            
            # 스레드 정리
            if not real_thread: return
            if screen == 'ALL':
                for s in list(real_thread.keys()):
                    if real_thread[s]:
                        real_thread[s].stop()
                        real_thread[s].quit()
                        finish = real_thread[s].wait(5000)  # 최대 1초 대기
                        if not finish:
                            logging.error(f"실시간 데이터 스레드 정리 오류: {s}")
                        else:
                            logging.debug(f"실시간 데이터 스레드 정리: {s}")
                        del real_thread[s]
            else:
                if screen in real_thread and real_thread[screen]:
                    real_thread[screen].stop()
                    real_thread[screen].quit()
                    finish = real_thread[screen].wait(5000)  # 최대 1초 대기
                    if not finish:
                        logging.error(f"실시간 데이터 스레드 정리 오류: {screen}")
                    else:
                        logging.debug(f"실시간 데이터 스레드 정리: {screen}")
                    del real_thread[screen]
            logging.debug(f'실시간 데이터 스레드 삭제후: {real_thread}, real_tickers 수: {len(real_tickers)}')
               
    def SetInputValue(self, id, value):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    def SendCondition(self, screen, cond_name, cond_index, search, block=True, wait=15):
        global cond_thread, real_tickers
        cond_text = f'{cond_index:03d} : {cond_name.strip()}'
        if not com_request_time_check(kind='request', cond_text=cond_text): return False

        if self.sim_no == 0:  # 실제 API 서버
            try:
                if block is True:
                    self.tr_condition_loaded = False

                success = self.ocx.dynamicCall("SendCondition(QString, QString, int, int)", screen, cond_name, cond_index, search) # 1: 성공, 0: 실패
                logging.debug(f'전략 요청: screen={screen}, name={cond_name}, index={cond_index}, search={search}, 결과={"성공" if success else "실패"}')
                if not success: return False
                
                data = False
                if block is True:
                    start_time = time.time()
                    while not self.tr_condition_loaded:
                        pythoncom.PumpWaitingMessages()
                        if time.time() - start_time > wait:
                            logging.warning(f'조건 검색 시간 초과: {screen} {cond_name} {cond_index} {search}')
                            return False
                    data = self.tr_condition_list
                return data
            except Exception as e:
                logging.error(f"SendCondition 오류: {type(e).__name__} - {e}")
                return False
        elif self.sim_no == 3:  # 시뮬레이션 3번
            self.tr_condition_loaded = True
            self.tr_condition_list = []
            cond_thread[screen] = OnReceiveRealConditionSim3(cond_name, cond_index, self)
            sim.sim3_condition_thread = cond_thread[screen]  # 스레드 참조 저장
            cond_thread[screen].start()
            sim.sim3_start()  # 시뮬레이션 시작
            sim.sim3_pause()  # 첫 데이터 내보내기 전에 일시정지 상태로 설정
            logging.debug(f'시뮬레이션 3번 조건검색 쓰레드 시작 (일시정지 상태): {screen} {cond_name} {cond_index}')
            return self.tr_condition_list
        else:  # 시뮬레이션 1, 2번
            self.tr_condition_loaded = True
            self.tr_condition_list = []
            cond_thread[screen] = OnReceiveRealConditionSim(cond_name, cond_index, self)
            cond_thread[screen].start()
            logging.debug(f'시뮬레이션 1,2번 조건검색 쓰레드 시작: {screen} {cond_name} {cond_index}')
            return self.tr_condition_list
        
    def SendConditionStop(self, screen, cond_name, cond_index):
        global cond_thread
        #logging.debug(f'전략 중지: screen={screen}, cond_name={cond_name}, cond_index={cond_index} {"*"*50}')
        if self.sim_no == 0:  # 실제 API 서버
            self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", screen, cond_name, cond_index)
        else:
            # 모든 모드 공통 - 시뮬레이션용 조건검색 쓰레드 종료
            if screen in cond_thread and cond_thread[screen]:
                cond_thread[screen].stop()
                cond_thread[screen].quit()
                finish = cond_thread[screen].wait(5000)  # 최대 1초 대기
                if not finish:
                    logging.error(f"API 조건검색 스레드 정리 오류: {screen}")
                else:
                    logging.debug(f"API 조건검색 스레드 정리: {screen}")
                #logging.debug(f'삭제전: {cond_thread}')
                del cond_thread[screen]
                logging.debug(f'조건검색 스레드 삭제후: {cond_thread}')
        return 0

    # 요청 메서드(일회성 콜백 발생 ) ---------------------------------------------------------------------------------
    @profile_operation
    def CommConnect(self, block=True):
        logging.debug(f'CommConnect: block={block}')
        if self.sim_no == 1:  
            self.connected = True
            self.order('prx', 'set_connected', self.connected) # OnEventConnect를 안 거치므로 여기서 처리
        else:
            self.ocx.dynamicCall("CommConnect()")
            if block:
                while not self.connected:
                    pythoncom.PumpWaitingMessages()

    def GetConnectState(self):
        if self.sim_no != 1:
            return self.ocx.dynamicCall("GetConnectState()")
        else:
            return 1

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
        #if not com_request_time_check(kind='order'): return -308 # 5회 제한 초과
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

            self.OnReceiveChejanDataSim(code, orderno, order)
            return 0

    def CommRqData(self, rqname, trcode, next, screen):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen)
            return ret
        return 0

    # 응답 메서드 --------------------------------------------------------------------------------------------------
    def OnEventConnect(self, code):
        logging.debug(f'OnEventConnect: code={code}')
        self.connected = code == 0
        self.order('prx', 'set_connected', self.connected)
        logging.info(f'Login {"Success" if self.connected else "Failed"}')

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
                name = data[2]  
                order_no = self.GetCommData(trcode, rqname, 0, '주문번호')
                self.order('prx', 'proxy_method', QWork(method='on_receive_tr_data', args=(code, name, order_no, screen, rqname, trcode)))

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
        # data = {
        #     'code': code,
        #     'type': id_type,
        #     'cond_name': cond_name,
        #     'cond_index': cond_index
        # }
        #logging.debug(f"Condition: API 서버에서 보냄 {code} {id_type} ({cond_index} : {cond_name})")
        self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, id_type, cond_name, cond_index)))

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

                if rtype == '주식체결': 
                    self.order('rcv', 'proxy_method', QWork(method='on_receive_real_data', args=(code, rtype, dictFID)))
                elif rtype == '장시작시간': 
                    self.order('rcv', 'proxy_method', QWork(method='on_receive_market_status', args=(code, rtype, dictFID)))
        except Exception as e:
            logging.error(f"OnReceiveRealData error: {e}", exc_info=True)
            
    def OnReceiveChejanData(self, gubun, item_cnt, fid_list):
        try:
            dictFID = {}
            if gubun == '0': dict_tmp = dc.fid.주문체결
            elif gubun == '1': dict_tmp = dc.fid.잔고

            for key, value in dict_tmp.items():
                data = self.GetChejanData(value)
                dictFID[key] = data.strip() if type(data) == str else data

            self.order('rcv', 'proxy_method', QWork(method='on_receive_chejan_data', args=(gubun, dictFID)))
            #self.order('rcv', 'on_receive_chejan_data', gubun, dictFID)

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
                dictFID['매도/매수구분'] = '1' if order['ordtype'] == 2 else '2'
                self.order('rcv', 'proxy_method', QWork(method='on_receive_chejan_data', args=('1', dictFID)))
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

                self.order('rcv', 'proxy_method', QWork(method='on_receive_chejan_data', args=('0', dictFID)))
                #self.order('rcv', 'on_receive_chejan_data', '0', dictFID)

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
        data = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market)
        tokens = data.split(';')[:-1]
        return tokens
        
    # 기타 함수 ----------------------------------------------------------------------------------------------------
    def GetCommDataEx(self, trcode, rqname):
        if self.sim_no == 0:  # 실제 API 서버
            data = self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trcode, rqname)
            return data
        return None

    def GetConditionInterval(self, cond_text):
        return req.check_condition_interval(cond_text)

    #@profile_operation
    def get_first_chart_data(self, code, times=1, wt=None, dt=None):
        dict_mi = self.get_chart_data(code, 'mi', 1, times, wt, dt)
        dict_dy = self.get_chart_data(code, 'dy', 1, times, wt, dt)
        return (dict_mi, dict_dy)
    
    def get_chart_data(self, code, cycle, tick=1, times=1, wt=None, dt=None):
        """
            차트 데이터 조회
            times: 차트 데이터 조회 반복 횟수 (기본 1회)
            wt: 차트 데이터 조회 대기 시간 (기본 0초) 서버 시간 제한 회피
            dt: 차트 데이터 비교 기준 일자 (같거나 이전 데이타 까지 받으면 종료)
        """
        try:
            rqname = f'{dc.scr.차트종류[cycle]}차트'
            trcode = dc.scr.차트TR[cycle]
            screen = dc.scr.화면[rqname]
            date = datetime.now().strftime('%Y%m%d')
            dict_list = []
            
            if cycle in ['mi', 'tk']:
                if tick == None:
                    tick = '1'
                elif isinstance(tick, int):
                    tick = str(tick)
                input = {'종목코드':code, '틱범위': tick, '수정주가구분': "1"}
                output = dc.const.MI_OUTPUT #["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if cycle == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': "1"}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': "1"}
                output = dc.const.DY_OUTPUT #["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            dict_list = self._fetch_chart_data(rqname, trcode, input, output, screen, times, wt, dt)
            
            if not dict_list:
                logging.warning(f'{rqname} 데이타 얻기 실패: code:{code}, cycle:{cycle}, tick:{tick}')
                return dict_list
            
            logging.debug(f'{rqname}: code:{code}, cycle:{cycle}, tick:{tick}, count:{len(dict_list)} {dict_list[:1]}')
            
            # 데이터 변환
            dict_list = self._convert_chart_data(dict_list, code, cycle)
            
            return dict_list
        
        except Exception as e:
            logging.error(f'{rqname} 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []

    def _fetch_chart_data(self, rqname, trcode, input, output, screen, times, wt, dt):
        """차트 데이터 fetch"""
        next = '0'
        dict_list = []
        
        while True:
            if wt is not None: time.sleep(wt)
            result = self.api_request(rqname, trcode, input, output, next=next, screen=screen)
            if result is None: break
            
            data, remain = result
            if data is None or len(data) == 0: break
                
            dict_list.extend(data)
            if trcode == dc.scr.차트TR['tk'] and dt is not None and data[-1]['체결시간'] < dt: times = 0
            
            times -= 1
            if not remain or times <= 0: break
            next = '2'
        
        return dict_list

    def _convert_chart_data(self, dict_list, code, cycle):
        """차트 데이터 변환"""
        if cycle in ['mi', 'tk']:
            return [{
                '종목코드': code,
                '체결시간': item['체결시간'] if item['체결시간'] else datetime.now().strftime('%Y%m%d%H%M%S'),
                '시가': abs(int(item['시가'])) if item['시가'] else 0,
                '고가': abs(int(item['고가'])) if item['고가'] else 0,
                '저가': abs(int(item['저가'])) if item['저가'] else 0,
                '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                '거래대금': 0,
            } for item in dict_list]
        else:
            return [{
                '종목코드': code,
                '일자': item['일자'] if item['일자'] else datetime.now().strftime('%Y%m%d'),
                '시가': abs(int(item['시가'])) if item['시가'] else 0,
                '고가': abs(int(item['고가'])) if item['고가'] else 0,
                '저가': abs(int(item['저가'])) if item['저가'] else 0,
                '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                '거래대금': abs(int(item['거래대금'])) if item['거래대금'] else 0,
            } for item in dict_list]


