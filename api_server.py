from public import hoga, dc, gm, init_logger, profile_operation, QWork, Work
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

req = TimeLimiter(name='req', second=5, minute=100, hour=1000)
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
      self.data_loaded = False

      # 시뮬레이션 2번 전용 속성들
      self.sim2_date = None  # 시뮬레이션 기준 날짜 (YYYY-MM-DD)
      self.sim2_speed = 1.0  # 배속 (기본 1배속)

      # 시뮬레이션 3번 전용 속성들
      self.sim3_date = None  # 시뮬레이션 날짜
      self.sim3_speed = 1.0  # 배속 (0.2, 0.5, 1, 2, 5, 10)
      self.sim3_start_time = None  # 실제 시작 시간 (datetime.now() 기준)
      self.sim3_base_data_time = 0  # 기준 데이터 시간 (초) - 현재 인덱스의 데이터 시간
      self.sim3_paused_sim_time = 0  # 일시정지 시점의 시뮬레이션 시간 (초)
      self.sim3_condition_data = []  # real_condition 테이블 데이터
      self.sim3_real_data = []  # real_data 테이블 데이터 (전체, 하위호환용)
      self.sim3_real_data_by_code = {}  # 종목별로 미리 분류된 real_data {code: [data1, data2, ...]}
      self.sim3_condition_index = 0  # 현재 조건검색 데이터 인덱스
      self.sim3_real_index = {}  # 종목별 실시간 데이터 인덱스
      self.sim3_registered_codes = set()  # 등록된 종목 코드들
      
      # 시뮬레이션 3번 컨트롤 상태 변수들
      self.sim3_is_paused = False  # 일시정지 상태
      self.sim3_is_running = False  # 실행 상태
      self.sim3_is_stopped = True  # 정지 상태
      self.sim3_condition_thread = None  # 조건검색 스레드 참조
      self.sim3_real_threads = {}  # 실시간 데이터 스레드들 참조

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

   def sim2_reset(self):
        """시뮬레이션 2번 초기화"""
        logging.info("시뮬레이션 2번 초기화")
        self.sim2_date = None
        self.sim2_speed = 1.0
        self.ticker = {}
        self.data_loaded = False
        self.rc_queue = []
        self.rd_queue = []

   def sim3_reset_to_start(self):
        """시뮬레이션 3번을 처음으로 리셋"""
        logging.info("시뮬레이션 3번 처음으로 리셋")
        self.sim3_condition_index = 0
        self.sim3_real_index = {}
        self.sim3_registered_codes = set()
        self.sim3_start_time = None
        self.sim3_base_data_time = 0
        self.sim3_paused_sim_time = 0
        self.sim3_is_paused = False
        self.sim3_is_running = False
        self.sim3_is_stopped = True

   def sim3_pause(self):
        """시뮬레이션 3번 일시정지"""
        if not self.sim3_is_running or self.sim3_is_paused:
            return

        # 현재 시뮬레이션 시간 저장 (재시작 시 이 시간부터 계속)
        if self.sim3_start_time:
            elapsed_real = (datetime.now() - self.sim3_start_time).total_seconds()
            self.sim3_paused_sim_time = self.sim3_base_data_time + (elapsed_real * self.sim3_speed)
            logging.info(f"시뮬레이션 3번 일시정지 (시뮬레이션 시간: {self.sim3_paused_sim_time:.1f}초)")
        else:
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
            # 일시정지된 위치부터 재시작 - 일시정지된 시뮬레이션 시간부터 계속
            logging.info(f"시뮬레이션 3번 재시작 (시뮬레이션 시간: {self.sim3_paused_sim_time:.1f}초부터)")
            self.sim3_is_paused = False

            # 일시정지된 시뮬레이션 시간을 기준 시간으로 설정
            self.sim3_base_data_time = self.sim3_paused_sim_time
        
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
      self.sim2_base_time = None
      self.sim2_data_base = None

   def run(self):
      if self.api.sim_no == 2:
         # sim2: DB 데이터 재생
         self._run_sim2()
      else:
         # sim1: 랜덤 데이터 생성
         self._run_sim1()

   def _run_sim1(self):
      """sim1: 랜덤 조건검색 데이터 생성"""
      while self.is_running:
         if not self.api.connected:
            time.sleep(0.01)
            continue
         code = random.choice(list(sim.ticker.keys()))
         type = random.choice(['D', 'I'])

         current_count = len(self.current_stocks)
         if current_count >= 3 and type == 'I': continue

         self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, type, self.cond_name, int(self.cond_index))))

         if type == 'I':
            self.current_stocks.add(code)
         else:
            if code in self.current_stocks:
               self.current_stocks.remove(code)

         interval = random.uniform(0.3, 3)
         if self.is_running:
            time.sleep(interval)

   def _run_sim2(self):
      """sim2: DB 실매매 조건검색 데이터 재생"""
      if not hasattr(sim, 'rc_queue') or not sim.rc_queue:
         logging.warning('[OnReceiveRealConditionSim] sim2: rc_queue 없음')
         return

      logging.info(f'[OnReceiveRealConditionSim] sim2 재생 시작: {len(sim.rc_queue)}건')

      # 데이터 시간순 정렬 확인 (이미 DB에서 정렬되어 오지만 보험용)
      try:
         sim.rc_queue = sorted(sim.rc_queue, key=lambda x: x.get('처리일시', x.get('시간', '000000')))
         logging.debug(f'[OnReceiveRealConditionSim] rc_queue 정렬 완료')
      except Exception as e:
         logging.warning(f'[OnReceiveRealConditionSim] rc_queue 정렬 실패: {e}')

      for idx, row in enumerate(sim.rc_queue):
         if not self.is_running:
            break

         # 시간 동기화 (sim2_speed 배속)
         # 처리일시(YYYYMMDDHHMMSS) 또는 시간(HHMMSS) 사용
         time_str = row.get('처리일시', row.get('시간', '000000'))
         wait_time = self._calculate_wait_time(time_str)
         if wait_time > 0:
            time.sleep(wait_time)

         # admin으로 전송
         code = row['종목코드']
         type = row.get('조건구분', 'I')  # 기본값 'I' (편입)

         self.order('rcv', 'proxy_method', QWork(
            method='on_receive_real_condition',
            args=(code, type, self.cond_name, int(self.cond_index))
         ))

         if idx % 100 == 0:
            logging.debug(f'[OnReceiveRealConditionSim] sim2 진행: {idx}/{len(sim.rc_queue)}, 처리일시: {time_str}')
            if idx == 0:
               logging.debug(f'[OnReceiveRealConditionSim] 첫 데이터 - code:{code}, type:{type}, 처리일시:{time_str}')

      logging.info('[OnReceiveRealConditionSim] sim2 재생 완료')

   def _calculate_wait_time(self, time_str):
      """실시간 동기화된 대기시간 계산"""
      # 첫 데이터: 현재시간과 데이터 시간 동기화
      if self.sim2_base_time is None:
         self.sim2_base_time = time.time()  # 실제 시작 시간
         self.sim2_data_base = time_str     # 데이터 시작 시간
         logging.info(f'[Sim2 동기화] 시작 - 현재={datetime.now().strftime("%H:%M:%S")}, 데이터={time_str[-6:]}')
         return 0

      # 데이터 경과 시간 (첫 데이터 대비)
      data_elapsed = self._time_diff_seconds(self.sim2_data_base, time_str)

      # 실제 경과 시간
      real_elapsed = time.time() - self.sim2_base_time

      # 배속 적용된 데이터 시간
      speed = getattr(sim, 'sim2_speed', 1.0)
      data_time_scaled = data_elapsed / speed if speed > 0 else data_elapsed

      # 대기 시간 = 데이터 시간 - 실제 경과 시간
      wait = data_time_scaled - real_elapsed

      return max(0, wait)

   def _time_diff_seconds(self, time1_str, time2_str):
      """HHMMSS 형식 두 시간의 초 단위 차이"""
      try:
         from datetime import datetime
         fmt = '%H%M%S'

         def extract_time(time_str):
            """시간 문자열에서 HHMMSS 추출"""
            time_str = str(time_str).strip()

            # "YYYY-MM-DD HH:MM:SS.mmm" 형식이면 시간 부분만 추출
            if ' ' in time_str:
               parts = time_str.split()
               # 시간 부분 (HH:MM:SS 또는 HH:MM:SS.mmm)
               time_str = parts[1] if len(parts) > 1 else parts[0]

            # 소수점 이하 제거 (밀리초 제거)
            if '.' in time_str:
               time_str = time_str.split('.')[0]

            # 콜론 제거
            time_str = time_str.replace(':', '')

            # 숫자만 추출
            time_str = ''.join(filter(str.isdigit, time_str))

            # HHMMSS 형식 보장 (6자리)
            if len(time_str) >= 6:
               return time_str[:6]
            else:
               return time_str.zfill(6)

         t1_str = extract_time(time1_str)
         t2_str = extract_time(time2_str)

         t1 = datetime.strptime(t1_str, fmt)
         t2 = datetime.strptime(t2_str, fmt)
         return (t2 - t1).total_seconds()
      except Exception as e:
         logging.error(f'시간 차이 계산 오류: {e}, time1={time1_str}, time2={time2_str}')
         return 0

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
      self.sim2_base_time = None
      self.sim2_data_base = None

   def run(self):
      if self.api.sim_no == 2:
         # sim2: DB 데이터 재생
         self._run_sim2()
      else:
         # sim1: 랜덤 데이터 생성
         self._run_sim1()

   def _run_sim1(self):
      """sim1: 랜덤 실시간 체결 데이터 생성"""
      self.start_time = time.time()
      batch = {}
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

   def _run_sim2(self):
      """sim2: DB 실매매 실시간 체결 데이터 재생"""
      if not hasattr(sim, 'rd_queue') or not sim.rd_queue:
         logging.warning('[OnReceiveRealDataSim1And2] sim2: rd_queue 없음')
         return

      logging.info(f'[OnReceiveRealDataSim1And2] sim2 재생 시작: {len(sim.rd_queue)}건')

      # 첫 데이터 샘플 확인 (정렬 전)
      if sim.rd_queue:
         first_row = sim.rd_queue[0]
         last_row = sim.rd_queue[-1]
         체결시간_샘플 = first_row.get('체결시간', None)
         logging.debug(f'[OnReceiveRealDataSim1And2] 정렬 전 - 첫:{체결시간_샘플}, 끝:{last_row.get("체결시간", None)} (타입:{type(체결시간_샘플).__name__})')

      # 데이터 시간순 정렬 (체결시간 기준 - 숫자형 변환)
      try:
         def get_sort_key(row):
            체결시간 = row.get('체결시간', 0)
            # 숫자형으로 변환 (문자열이면 int로)
            try:
               return int(체결시간) if 체결시간 else 0
            except (ValueError, TypeError):
               return 0

         sim.rd_queue = sorted(sim.rd_queue, key=get_sort_key)

         # 정렬 후 확인
         if sim.rd_queue:
            first_row_sorted = sim.rd_queue[0]
            last_row_sorted = sim.rd_queue[-1]
            logging.debug(f'[OnReceiveRealDataSim1And2] rd_queue 정렬 완료 (체결시간 기준) - 첫:{first_row_sorted.get("체결시간", None)}, 끝:{last_row_sorted.get("체결시간", None)}')
      except Exception as e:
         logging.warning(f'[OnReceiveRealDataSim1And2] rd_queue 정렬 실패: {e}')

      for idx, row in enumerate(sim.rd_queue):
         if not self.is_running:
            break

         # 체결시간 추출 및 형식 변환 (숫자 또는 문자열 → 14자리 문자열)
         체결시간_원본 = row.get('체결시간', '00000000000000')
         try:
            # 숫자형(int, float)이면 문자열로 변환
            if isinstance(체결시간_원본, (int, float)):
               체결시간 = str(int(체결시간_원본))  # float이면 int로 변환 후 문자열
            else:
               체결시간 = str(체결시간_원본).strip()

            # 14자리 맞추기 (부족하면 앞에 0 채우기)
            체결시간 = 체결시간.zfill(14)
         except Exception as e:
            logging.warning(f'[OnReceiveRealDataSim1And2] 체결시간 변환 오류: {e}, 원본={체결시간_원본}')
            체결시간 = '00000000000000'

         # 시간 동기화 (sim2_speed 배속)
         wait_time = self._calculate_wait_time(체결시간)
         if idx < 10:  # 처음 10개만 디버그
            logging.debug(f'[OnReceiveRealDataSim1And2] idx={idx}, 체결시간={체결시간}, wait_time={wait_time:.3f}초')
         if wait_time > 0:
            time.sleep(wait_time)

         # dictFID 구성
         code = row['종목코드']

         # 현재가 형식 변환 (문자열 또는 숫자 → 정수)
         현재가_원본 = row.get('현재가', 0)
         try:
            if isinstance(현재가_원본, str):
               현재가_원본 = 현재가_원본.strip()
               if 현재가_원본.startswith('-') or 현재가_원본.startswith('+'):
                  현재가_원본 = 현재가_원본[1:]  # 부호 제거
            현재가 = abs(int(현재가_원본)) if 현재가_원본 else 0
         except (ValueError, TypeError):
            현재가 = 0
            logging.warning(f'[OnReceiveRealDataSim1And2] 현재가 변환 오류: code={code}, 현재가_원본={현재가_원본}')

         # 누적거래량 형식 변환
         누적거래량 = row.get('누적거래량', row.get('거래량', 0))
         try:
            누적거래량 = abs(int(누적거래량)) if 누적거래량 else 0
         except (ValueError, TypeError):
            누적거래량 = 0

         # 누적거래대금 형식 변환
         누적거래대금 = row.get('누적거래대금', row.get('거래대금', 0))
         try:
            누적거래대금 = abs(int(누적거래대금)) if 누적거래대금 else 0
         except (ValueError, TypeError):
            누적거래대금 = 0

         # 종목명 가져오기 (ticker 또는 API)
         종목명 = sim.ticker.get(code, {}).get('종목명', '')
         if not 종목명:
            종목명 = self.api.GetMasterCodeName(code) if hasattr(self.api, 'GetMasterCodeName') else ''

         # 등락율 계산
         전일가 = sim.ticker.get(code, {}).get('전일가', 0)
         if 전일가 and 현재가:
            등락율 = round((현재가 - 전일가) / 전일가 * 100, 2)
         else:
            등락율 = 0.0

         # 체결시간 6자리 추출 (HHMMSS)
         체결시간_6자리 = 체결시간[-6:] if len(체결시간) >= 6 else 체결시간.zfill(6)

         dictFID = {
            '종목코드': code,
            '종목명': 종목명,
            '현재가': f'{현재가:15d}',
            '등락율': f'{등락율:12.2f}',
            '누적거래량': f'{누적거래량:15d}',
            '누적거래대금': f'{누적거래대금:15d}',
            '체결시간': 체결시간_6자리,
         }

         # 포트폴리오 업데이트
         portfolio.update_stock_price(code, 현재가)

         # price_dict 업데이트
         price_dict[code] = 현재가

         # admin으로 전송
         self.order('rcv', 'proxy_method', QWork(
            method='on_receive_real_data',
            args=(code, '주식체결', dictFID)
         ))

         if idx < 10 or idx % 1000 == 0:
            logging.debug(f'[실시간재생] sim2 진행: {idx}/{len(sim.rd_queue)}, code={code}, 현재가={현재가}, 체결시간={체결시간_6자리}')

      logging.info('[OnReceiveRealDataSim1And2] sim2 재생 완료')

   def _calculate_wait_time(self, time_str):
      """실시간 동기화된 대기시간 계산"""
      # 첫 데이터: 현재시간과 데이터 시간 동기화
      if self.sim2_base_time is None:
         self.sim2_base_time = time.time()  # 실제 시작 시간
         self.sim2_data_base = time_str     # 데이터 시작 시간
         logging.info(f'[Sim2 동기화] 시작 - 현재={datetime.now().strftime("%H:%M:%S")}, 데이터={time_str[-6:]}')
         return 0

      # 데이터 경과 시간 (첫 데이터 대비)
      data_elapsed = self._time_diff_seconds(self.sim2_data_base, time_str)

      # 실제 경과 시간
      real_elapsed = time.time() - self.sim2_base_time

      # 배속 적용된 데이터 시간
      speed = getattr(sim, 'sim2_speed', 1.0)
      data_time_scaled = data_elapsed / speed if speed > 0 else data_elapsed

      # 대기 시간 = 데이터 시간 - 실제 경과 시간
      wait = data_time_scaled - real_elapsed

      return max(0, wait)

   def _time_diff_seconds(self, time1_str, time2_str):
      """HHMMSS 형식 두 시간의 초 단위 차이"""
      try:
         from datetime import datetime
         fmt = '%H%M%S'

         def extract_time(time_str):
            """시간 문자열에서 HHMMSS 추출"""
            time_str = str(time_str).strip()

            # "YYYY-MM-DD HH:MM:SS.mmm" 형식이면 시간 부분만 추출
            if ' ' in time_str:
               parts = time_str.split()
               # 시간 부분 (HH:MM:SS 또는 HH:MM:SS.mmm)
               time_str = parts[1] if len(parts) > 1 else parts[0]

            # 소수점 이하 제거 (밀리초 제거)
            if '.' in time_str:
               time_str = time_str.split('.')[0]

            # 콜론 제거
            time_str = time_str.replace(':', '')

            # 숫자만 추출
            time_str = ''.join(filter(str.isdigit, time_str))

            # HHMMSS 형식 보장 (6자리)
            if len(time_str) >= 6:
               return time_str[:6]
            else:
               return time_str.zfill(6)

         t1_str = extract_time(time1_str)
         t2_str = extract_time(time2_str)

         t1 = datetime.strptime(t1_str, fmt)
         t2 = datetime.strptime(t2_str, fmt)
         return (t2 - t1).total_seconds()
      except Exception as e:
         logging.error(f'시간 차이 계산 오류: {e}, time1={time1_str}, time2={time2_str}')
         return 0

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
      
      # 첫 시작 시에만 기준 시간 설정 (리셋 후 처음 시작)
      # 재시작이나 일시정지 후에는 sim3_start()에서 이미 설정됨
      if sim.sim3_base_data_time == 0 and sim.sim3_condition_index == 0:
         first_data = sim.sim3_condition_data[0]
         # 처리일시에서 시간 추출 (YYYYMMDDHHMMSS 형식 또는 HHMMSS 형식)
         time_full = first_data.get('처리일시', '090000')
         time_str = time_full[-6:] if len(time_full) >= 6 else time_full  # HHMMSS 부분 추출
         hour = int(time_str[:2])
         minute = int(time_str[2:4])
         second = int(time_str[4:6]) if len(time_str) >= 6 else 0
         sim.sim3_base_data_time = hour * 3600 + minute * 60 + second
         logging.debug(f"[조건검색 스레드] 기준 시간 초기화: {sim.sim3_base_data_time}초 (처음 시작)")

      # 실제 시작 시간 설정 (sim3_start()에서 이미 설정되었을 수 있음)
      if not sim.sim3_start_time:
         sim.sim3_start_time = datetime.now()
         logging.debug(f"[조건검색 스레드] 실제 시작 시간 초기화")
      
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
                  # 실시간 데이터 인덱스 초기화 (명시적)
                  if code not in sim.sim3_real_index:
                     sim.sim3_real_index[code] = 0
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

            # 해당 종목의 데이터 가져오기 (미리 분류된 데이터 사용)
            code_data = sim.sim3_real_data_by_code.get(code, [])
            if not code_data:
               continue

            current_index = sim.sim3_real_index.get(code, 0)

            # 현재 시간보다 작거나 같은 모든 데이터 처리 (한 종목에 여러 데이터가 있을 수 있음)
            while current_index < len(code_data):
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
                  current_index += 1
                  sim.sim3_real_index[code] = current_index
               else:
                  # 현재 시간보다 크면 더 이상 처리 안 함
                  break
         
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
        if self.sim_no == 0:
            # 실제 API 서버는 별도 처리 필요 없음
            logging.info('[API] sim0 set_tickers 완료')
            # 완료 신호 - proxy_method를 통해 admin.on_tickers_ready() 호출
            self.order('prx', 'proxy_method', QWork(method='on_tickers_ready', kwargs={'sim_no': 0}))

        elif self.sim_no == 1:  # 키움서버 없이 가상 데이터 사용
            sim.ticker = dc.sim.ticker
            sim._initialize_data()
            logging.info('[API] sim1 set_tickers 완료')
            # 완료 신호 - proxy_method를 통해 admin.on_tickers_ready() 호출
            self.order('prx', 'proxy_method', QWork(method='on_tickers_ready', kwargs={'sim_no': 1}))

        elif self.sim_no == 2:
            import threading
            if speed:
                sim.sim2_speed = speed
            thread = threading.Thread(target=self._load_sim2_data, args=(dt,), daemon=True)
            thread.start()
            logging.info(f'[API] sim2 데이터 로드 스레드 시작 (배속={sim.sim2_speed})')
            return

        elif self.sim_no == 3:
            import threading
            if not dt:
                dt = datetime.now().strftime('%Y-%m-%d')
            sim.sim3_date = dt
            if speed:
                sim.sim3_speed = speed
            thread = threading.Thread(target=self._load_sim_data, args=(3, dt), daemon=True)
            thread.start()
            logging.info(f'[API] sim3 데이터 로드 스레드 시작')
            return

        global ready_tickers
        ready_tickers = True

    def _load_sim_data(self, sim_no, dt):
        """sim2/sim3 데이터 로드 공통 함수 (스레드에서 실행)"""
        try:
            import time
            if not dt:
                logging.error(f'[API] sim{sim_no}: 날짜 파라미터 필요')
                return
            logging.info(f'[API] sim{sim_no} 데이터 로드 시작: {dt}')

            if sim_no == 2:
                sim.sim2_date = dt
                self.order('dbm', 'delete_sim2_results')
                self.order('prx', 'proxy_method', QWork(method='update_sim2_progress_text', kwargs={'text': '데이터 작성 중...'}))
            elif sim_no == 3:
                sim.sim3_date = dt

            sim.data_loaded = False
            sim.load_start_time = time.time()

            self.order('dbm', 'load_real_condition', date=dt, callback='_on_sim_condition_loaded')

            timeout = 120
            while not sim.data_loaded:
                if time.time() - sim.load_start_time > timeout:
                    logging.error(f'[API] sim{sim_no} 데이터 로드 타임아웃 ({timeout}초)')
                    return
                time.sleep(0.01)

            elapsed = time.time() - sim.load_start_time
            logging.info(f'[API] sim{sim_no} 데이터 로드 완료: {elapsed:.2f}초')

            global ready_tickers
            ready_tickers = True

            logging.debug(f'[API] sim{sim_no} on_tickers_ready 호출 준비 중...')
            if sim_no == 2:
                logging.info(f'[API] sim2 on_tickers_ready 호출: ticker={len(sim.ticker)}개')
                self.order('prx', 'proxy_method', QWork(method='on_tickers_ready', kwargs={'sim_no': 2, 'success': True, 'message': f'로드 완료 ({elapsed:.2f}초)', 'ticker': sim.ticker}))
            elif sim_no == 3:
                logging.info(f'[API] sim3 on_tickers_ready 호출')
                self.order('prx', 'proxy_method', QWork(method='on_tickers_ready', kwargs={'sim_no': 3}))
            logging.debug(f'[API] sim{sim_no} on_tickers_ready 호출 완료')
        except Exception as e:
            logging.error(f'[API] sim{sim_no} 데이터 로드 오류: {e}', exc_info=True)

    def _load_sim2_data(self, dt):
        """sim2 데이터 로드 (하위 호환용)"""
        self._load_sim_data(2, dt)

    def _on_sim_condition_loaded(self, rc_data):
        """sim2/sim3 조건검색 로드 완료 콜백"""
        try:
            if self.sim_no == 2:
                # sim2: rc_data로 rc_queue 설정 (이벤트 재생용)
                if not rc_data:
                    logging.error(f'[API] sim2: real_condition 데이터 없음 ({sim.sim2_date}) - 종료')
                    sim.data_loaded = True
                    self.order('prx', 'proxy_method',
                              QWork(method='on_tickers_ready',
                                    kwargs={'sim_no': 2, 'success': False,
                                           'message': f'real_condition 데이터 없음: {sim.sim2_date}'}))
                    return

                # rc_queue 설정 (조건검색 이벤트 재생용)
                sim.rc_queue = rc_data
                logging.info(f'[API] sim2 rc_queue 설정: {len(sim.rc_queue)}건')

                # daily_sim에서 ticker 로드 (중복 제거된 종목 목록)
                self.order('dbm', 'load_daily_sim', date=sim.sim2_date, sim_no=2,
                          callback='_on_sim2_ticker_loaded')

            elif self.sim_no == 3:
                # sim3: real_condition에서 ticker 추출
                logging.debug(f'[API] rc_data 타입: {type(rc_data)}, 값: {rc_data[:2] if rc_data else None}')
                if not rc_data:
                    logging.warning(f'[API] sim3: real_condition 데이터 없음')
                    return

                sim.ticker = {}
                for row in rc_data:
                    code = row['종목코드']
                    if code not in sim.ticker:
                        sim.ticker[code] = {
                            '종목명': row.get('종목명', self.GetMasterCodeName(code)),
                            '전일가': self.GetMasterLastPrice(code),
                        }
                logging.info(f'[API] sim3 ticker 설정 완료: {len(sim.ticker)}개 종목')

                sim.sim3_condition_data = rc_data
                self.order('dbm', 'load_real_data', date=sim.sim3_date, callback='_on_sim3_real_loaded')
        except Exception as e:
            logging.error(f'[API] _on_sim_condition_loaded 오류: {e}', exc_info=True)

    def _on_real_condition_loaded(self, rc_data):
        """하위 호환용 - _on_sim_condition_loaded 호출"""
        self._on_sim_condition_loaded(rc_data)

    def _on_sim2_ticker_loaded(self, daily_sim_data):
        """sim2 daily_sim 종목 로드 완료 콜백"""
        try:
            if not daily_sim_data:
                logging.error(f'[API] sim2: daily_sim 데이터 없음 ({sim.sim2_date}) - 종료')
                sim.data_loaded = True
                self.order('prx', 'proxy_method',
                          QWork(method='on_tickers_ready',
                                kwargs={'sim_no': 2, 'success': False,
                                       'message': f'데이터 없음: {sim.sim2_date}'}))
                return

            # ticker 설정 (daily_sim의 전일가 사용, 중복 제거된 종목 목록)
            sim.ticker = {}
            for row in daily_sim_data:
                code = row['종목코드']
                if code not in sim.ticker:
                    sim.ticker[code] = {
                        '종목명': row.get('종목명', ''),
                        '전일가': row.get('전일가', 0),
                    }
            logging.info(f'[API] sim2 ticker 설정 완료: {len(sim.ticker)}개 종목')

            # tblSimDaily 표시용 admin을 통해 GUI에 전달
            self.order('prx', 'proxy_method',
                      QWork(method='gui_update_sim_daily_table',
                            kwargs={'data': daily_sim_data}))

            # real_data 로드 계속
            self.order('dbm', 'load_real_data', date=sim.sim2_date, callback='_on_real_data_loaded')
        except Exception as e:
            logging.error(f'[API] _on_sim2_ticker_loaded 오류: {e}', exc_info=True)
            sim.data_loaded = True

    def _on_real_data_loaded(self, rd_data):
        """sim2 real_data 로드 완료 콜백"""
        try:
            logging.debug(f'[API] rd_queue 타입: {type(rd_data)}, 개수: {len(rd_data) if rd_data else 0}')
            sim.rd_queue = rd_data
            sim.sim2_base_time = None
            sim.sim2_data_base = None
            logging.info(f'[API] sim2 데이터 준비 완료: rc={len(sim.rc_queue)}건, rd={len(sim.rd_queue) if sim.rd_queue else 0}건, 배속={sim.sim2_speed}')
            self.order('prx', 'proxy_method', QWork(method='update_sim2_progress_text', kwargs={'text': '준비 완료'}))
            sim.data_loaded = True
        except Exception as e:
            logging.error(f'[API] _on_real_data_loaded 오류: {e}', exc_info=True)
            sim.data_loaded = True

    def _on_sim3_real_loaded(self, rd_data):
        """sim3 real_data 로드 완료 콜백"""
        try:
            if rd_data is None: rd_data = []
            rd_data.sort(key=lambda x: x.get('체결시간', ''))

            real_unique = {}
            for data in rd_data:
                key = f"{data.get('체결시간', '')}_{data.get('종목코드', '')}"
                real_unique[key] = data
            rd_data = list(real_unique.values())

            real_data_by_code = {}
            for data in rd_data:
                code = data.get('종목코드', '')
                if code:
                    if code not in real_data_by_code:
                        real_data_by_code[code] = []
                    real_data_by_code[code].append(data)

            for code in real_data_by_code:
                real_data_by_code[code].sort(key=lambda x: x.get('체결시간', ''))

            sim.sim3_real_data = rd_data
            sim.sim3_real_data_by_code = real_data_by_code
            sim.extract_ticker_info_from_db()

            logging.info(f'[API] sim3 데이터 준비 완료: rc={len(sim.sim3_condition_data)}건, rd={len(rd_data)}건, 종목수={len(real_data_by_code)}')
            sim.data_loaded = True
        except Exception as e:
            logging.error(f'[API] _on_sim3_real_loaded 오류: {e}', exc_info=True)
            sim.data_loaded = True

    def sim3_memory_load(self, dt=None):
        """시뮬레이션 3번 메모리 로드 (스레드에서 실행)"""
        import threading
        if dt:
            sim.sim3_date = dt
        if not sim.sim3_date:
            logging.error('[API] sim3: 날짜 설정 필요')
            return False
        thread = threading.Thread(target=self._load_sim_data, args=(3, sim.sim3_date), daemon=True)
        thread.start()
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

        # 실행 중이면 현재 시뮬레이션 시간 계산 후 재동기화
        if sim.sim3_is_running and sim.sim3_start_time:
            elapsed_real = (datetime.now() - sim.sim3_start_time).total_seconds()
            current_sim_time = sim.sim3_base_data_time + (elapsed_real * sim.sim3_speed)

            # 새 배속으로 재설정 (현재 시뮬레이션 시간을 기준으로)
            sim.sim3_base_data_time = current_sim_time
            sim.sim3_start_time = datetime.now()

            logging.info(f"시뮬레이션 3번 배속 변경: {sim.sim3_speed}x → {speed}x (시뮬레이션 시간: {current_sim_time:.1f}초)")
        else:
            logging.info(f"시뮬레이션 3번 배속 설정: {speed}x")

        sim.sim3_speed = speed
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
            sim.sim3_condition_data, sim.sim3_real_data, sim.sim3_real_data_by_code = self.get_simulation_data()
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
        global real_tickers, real_thread, cond_thread, ready_tickers
        real_tickers.clear()
        ready_tickers = False

        # sim 상태 초기화
        if self.sim_no == 2:
            sim.sim2_reset()
        elif self.sim_no == 3:
            sim.sim3_reset_to_start()

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
            wait_time = req.check_interval()
            if wait_time > 999:
                msg = f'빈번한 요청으로 인하여 {float(wait_time/1000)} 초 대기 합니다.'
                logging.warning(msg)
                self.order('prx', 'proxy_method', QWork(method='toast', kwargs={'msg': msg, 'duration': wait_time}))

            time.sleep((wait_time + 50) / 1000)
            req.update_request_times()

            self.tr_remained = False
            self.tr_result = []
            # 잔고 관련 요청이면 sim1, sim2는 portfolio에서 처리 (서버 조회 X)
            if rqname == '잔고합산':
                if self.sim_no in [1, 2]:
                    summary = portfolio.get_summary()
                    self.tr_result = [summary]
                    return self.tr_result, self.tr_remained
            elif rqname == '잔고목록':
                if self.sim_no in [1, 2]:
                    holdings = portfolio.get_holdings_list()
                    self.tr_result = holdings
                    return self.tr_result, self.tr_remained

            # 차트 요청 등은 아래로 계속 진행 (키움 서버 호출)
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

        logging.debug(f'[SetRealReg] sim_no={self.sim_no}, screen={screen}, codes={len(code_list)}개, fids={fid_list}, opt={opt_type}')
        
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
                logging.info(f'[실시간스레드] sim{self.sim_no} OnReceiveRealDataSim1And2 시작: screen={screen}, codes={len(code_list)}개')
            else:
                logging.debug(f'[실시간스레드] sim{self.sim_no} 이미 실행 중: screen={screen}')
            return 1

    def SetRealRemove(self, screen, del_code):
        global real_thread, real_tickers
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
            logging.debug(f'실시간 데이터 스레드 삭제후: {real_thread}')
               
    def SetInputValue(self, id, value):
        if self.sim_no != 1:  # 실제 API 서버 또는 키움서버 사용 (sim_no=2, 3)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    def SendCondition(self, screen, cond_name, cond_index, search, block=True, wait=15):
        global cond_thread, real_tickers
        cond_text = f'{cond_index:03d} : {cond_name.strip()}'
        wait_time = req.check_condition_interval(cond_text)
        if wait_time > 1200:
            msg = f'{cond_text} 1분 이내에 같은 조건 호출 불가 합니다. 대기시간: {float(wait_time/1000)} 초'
            logging.warning(msg)
            self.order('prx', 'proxy_method', QWork(method='toast', kwargs={'msg': msg, 'duration': wait_time}))
            return False
        
        time.sleep((wait_time + 50) / 1000)
        req.update_condition_time(cond_text)

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

            self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=(gubun, dictFID)))

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
                self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=('1', dictFID)))
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

                self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=('0', dictFID)))

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

            # sim_no==2일 때 기준 날짜로 필터링
            logging.debug(f'[차트필터] sim_no={self.sim_no}, sim2_date={getattr(sim, "sim2_date", None)}, cycle={cycle}, 데이터={len(dict_list)}개')
            if self.sim_no == 2 and sim.sim2_date:
                dict_list = self._filter_chart_data_by_date(dict_list, sim.sim2_date, cycle)

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

            # sim_no==2: 처음과 마지막 둘 다 기준일보다 작으면 중단
            if self.sim_no == 2 and sim.sim2_date and remain and data:
                base_date_str = sim.sim2_date.replace('-', '')
                first_item = data[0]
                last_item = data[-1]

                # 처음과 마지막 날짜 추출
                if trcode in [dc.scr.차트TR['mi'], dc.scr.차트TR['tk']]:
                    first_date = str(first_item.get('체결시간', ''))[:8]
                    last_date = str(last_item.get('체결시간', ''))[:8]
                else:
                    first_date = str(first_item.get('일자', ''))
                    last_date = str(last_item.get('일자', ''))

                # 처음과 마지막 둘 다 기준일 미만이면 중단
                if first_date and last_date and first_date < base_date_str and last_date < base_date_str:
                    logging.debug(f'[sim2] 기준일 이전까지 수신 완료 → 요청 중단: {rqname}, 총 {len(dict_list)}건, 첫날짜={first_date}, 끝날짜={last_date}')
                    break
                else:
                    logging.debug(f'[sim2] 추가 요청: {rqname}, 현재 {len(dict_list)}건, 첫날짜={first_date}, 끝날짜={last_date}')
                    next = '2'
                    continue

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

    def _filter_chart_data_by_date(self, dict_list, base_date, cycle):
        """sim2: 기준 날짜보다 작은 데이터만 필터링

        Args:
            dict_list: 차트 데이터 리스트
            base_date: 기준 날짜 (YYYY-MM-DD 형식)
            cycle: 차트 주기 ('mi', 'tk', 'dy', 'wk', 'mo')

        Returns:
            필터링된 차트 데이터 리스트
        """
        try:
            # 기준 날짜를 YYYYMMDD 형식으로 변환
            base_date_str = base_date.replace('-', '')

            filtered_list = []
            for item in dict_list:
                if cycle in ['mi', 'tk']:
                    # 분봉/틱: 체결시간의 앞 8자리(날짜 부분)와 비교
                    item_date = str(item.get('체결시간', ''))[:8]
                else:
                    # 일봉/주봉/월봉: 일자 필드와 비교
                    item_date = str(item.get('일자', ''))

                # 기준 날짜보다 작은(이전) 데이터만 포함
                if item_date and item_date < base_date_str:
                    filtered_list.append(item)

            original_count = len(dict_list)
            filtered_count = len(filtered_list)
            if original_count != filtered_count:
                logging.info(f'[sim2 필터링] {cycle} 차트: {original_count}개 → {filtered_count}개 (기준일: {base_date})')
            else:
                logging.debug(f'[sim2 필터링] {cycle} 차트: 필터링 없음 ({original_count}개)')

            return filtered_list
        except Exception as e:
            logging.error(f'차트 데이터 필터링 오류: {type(e).__name__} - {e}', exc_info=True)
            return dict_list  # 오류 시 원본 반환


