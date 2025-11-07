from PyQt5.QtCore import QThread, QTimer
from classes import TimeLimiter, QData
from public import gm, dc, Work,QWork, save_json, hoga, com_market_status, profile_operation
from chart import ChartData
from datetime import datetime, timedelta
import queue
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import threading

class ProxyAdmin():
    def __init__(self):
        self.name = 'prx'
        self.daemon = True

    def initialize(self):
        logging.debug('prx_init completed')

    def set_connected(self, connected):
        gm.connected = connected

    def proxy_method(self, qwork):
        self.emit_q.put(qwork) # qwork = QWork()

class RealReceiver():
    def __init__(self):
        self.name = 'rcv'
        self.daemon = True

    def initialize(self):
        logging.debug('rcv_init completed')

    def proxy_method(self, qwork):
        self.emit_q.put(qwork) # qwork = QWork()

class PriceUpdater(QThread):
    def __init__(self, prx, price_q):
        super().__init__()
        self.daemon = True
        self.prx = prx
        self.price_q = price_q
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=4)

    def stop(self):
        self.running = False
        self.price_q.put(None)
        self.executor.shutdown(wait=True)
    
    def run(self):
        self.running = True
        while self.running:
            batch = set()
            start_time = time.time()
            while time.time() - start_time < dc.INTERVAL_BATCH:
                data = self.price_q.get()
                if data is None: 
                    self.running = False
                    return
                batch.add(data)

            if batch: self.update_batch(batch)

            q_len = self.price_q.length()
            if q_len > 30: logging.warning(f'price_q 대기 큐 len={q_len}')
            
    """
    # 예전 코드
    def run(self):
        self.running = True
        while self.running:
            data = self.price_q.get()
            if data is None: 
                self.running = False
                return
            self.update_current_price(data)

            q_len = self.price_q.length()
            if q_len > 30: logging.warning(f'price_q 대기 큐 len={q_len}')
    """
    def update_batch(self, batch):
        for code in batch:
            self.update_current_price(code)
    
    def update_current_price(self, code):
        try:
            row = gm.잔고목록.get(key=code)
            if not row: return
            
            현재가 = row['현재가']
            최고가 = row.get('최고가', 0)
            감시율 = row.get('감시시작율', 0.0) / 100
            보존율 = row.get('이익보존율', 0.0) / 100
            감시 = row.get('감시', 0)
            보존 = row.get('보존', 0)
            새감시 = 감시 or ((1 if 현재가 > row['매입가'] * (1 + 감시율) else 0) if 감시율 else 0)
            새보존 = 보존 or ((1 if 현재가 > row['매입가'] * (1 + 보존율) else 0) if 보존율 else 0)

            보유수량 = int(row['보유수량'])
            매입금액 = int(row['매입금액'])

            매수수수료 = int(매입금액 * gm.수수료율 / 10) * 10            # 매수시 10원 미만 절사
            매도수수료 = int(보유수량 * 현재가 * gm.수수료율 / 10) * 10   # 매도시 10원 미만 절사
            거래세 = int(보유수량 * 현재가 * gm.세금율)                   # 매도시 거래세 0.18% 원미만 절사

            평가금액 = 현재가 * 보유수량 - 매수수수료 - 매도수수료 - 거래세
            평가손익 = 평가금액 - 매입금액
            수익률 = (평가손익 / 매입금액) * 100 if 매입금액 > 0 else 0

            row.update({
                '현재가': 현재가,
                '평가금액': 평가금액,
                '평가손익': 평가손익,
                '수익률(%)': round(수익률, 2),
                '최고가': 현재가 if 현재가 > 최고가 else 최고가,
                '보존': 새보존,
                '감시': 새감시,
                '등락율': row.get('등락율', 0),
                '누적거래량': row.get('누적거래량', 0),
            })


            if not (gm.주문진행목록.in_key((code, '매수')) or gm.주문진행목록.in_key((code, '매도'))) and gm.잔고목록.get(key=code, column='보유수량') > 0:
                data={'구분': '매도', '상태': '요청', '종목코드': code, '종목명': row['종목명'], '전략매도': False, '비고': 'pri'}
                row.update({'rqname': '신규매도', 'account': gm.account})
                gm.주문진행목록.set(key=(code, '매도'), data=data)
                gm.eval_q.put((code, 'sell', {'row': row}))

            gm.잔고목록.set(key=code, data=row)

            # 잔고합산 업데이트
            총매입금액, 총평가금액 = gm.잔고목록.sum(column=['매입금액', '평가금액'])
            총평가손익금액 = 총평가금액 - 총매입금액
            총수익률 = (총평가손익금액 / 총매입금액 * 100) if 총매입금액 else 0

            # 추정예탁자산 = 이전추정예탁자산 + (현재총평가금액 - 이전총평가금액)
            이전총평가금액 = gm.l2잔고합산_copy['총평가금액'] or 0
            이전추정예탁자산 = gm.l2잔고합산_copy['추정예탁자산'] or 0
            추정예탁자산 = 이전추정예탁자산 + 총평가금액 - 이전총평가금액

            gm.잔고합산.set(data={
                '총매입금액': 총매입금액,
                '총평가금액': 총평가금액,
                '추정예탁자산': 추정예탁자산,
                '총평가손익금액': 총평가손익금액,
                '총수익률(%)': round(총수익률, 2),
            }, key=0)
            gm.l2잔고합산_copy = gm.잔고합산.get(key=0)

            if 새감시 != 감시 or 새보존 != 보존:
                gm.holdings[code]['감시'] = 새감시
                gm.holdings[code]['보존'] = 새보존
                save_json(dc.fp.holdings_file, gm.holdings)

        except Exception as e:
            logging.error(f'실시간 배치 오류: {type(e).__name__} - {e}', exc_info=True)

class ChartUpdater(QThread):
    def __init__(self, prx, chart_q):
        super().__init__()
        self.daemon = True
        self.name = 'ctu'
        self.prx = prx
        self.chart_q = chart_q
        self.cht_dt = ChartData()
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)

    def stop(self):
        self.running = False
        self.chart_q.put(None)
        self.executor.shutdown(wait=True)

    """
    def run(self):
        self.running = True
        while self.running:
            batch = {}
            start_time = time.time()
            while time.time() - start_time < dc.INTERVAL_BATCH:
                data = self.chart_q.get()
                if data is None: 
                    self.running = False
                    return
                batch.update(data)
            if batch: self.update_batch(batch)

            q_len = self.chart_q.length()
            if q_len > 30: logging.warning(f'chart_q 대기 큐 len={q_len}')

    """
    def run(self):
        self.running = True
        while self.running:
            data = self.chart_q.get()
            if data is None: 
                self.running = False
                return
            for code, fid in data.items():
                self.executor.submit(self.update_chart, code, fid)

            q_len = self.chart_q.length()
            if q_len > 30: logging.warning(f'chart_q 대기 큐 len={q_len}')

    def update_batch(self, batch):
        for code, fid in batch.items():
            self.executor.submit(self.update_chart, code, fid)

    def update_chart(self, code, fid):
        self.cht_dt.update_chart(
            code, 
            abs(int(fid['현재가'])) if fid['현재가'] else 0,
            abs(int(fid['누적거래량'])) if fid['누적거래량'] else 0,
            abs(int(fid['누적거래대금'])) if fid['누적거래대금'] else 0,
            dc.ToDay+fid['체결시간']
        )

class ChartSetter(QThread):
    def __init__(self, prx, setter_q):
        super().__init__()
        self.daemon = True
        self.name = 'cts'
        self.prx = prx
        self.setter_q = setter_q
        self.running = False
        self.cht_dt = ChartData()

    def stop(self):
        self.running = False
        self.setter_q.put(None)

    def run(self):
        self.running = True
        while self.running:
            code = self.setter_q.get()
            if code is None: 
                self.running = False
                break
            if isinstance(code, str):
                self.request_chart_data(code)
            elif isinstance(code, set):
                self.request_tick_chart(code)

    #@profile_operation
    def request_chart_data(self, code):
        if self.cht_dt.is_code_registered(code): return
        logging.debug(f"get_first_chart_data 요청: {code}")
        dict_tuple = self.prx.answer('api', 'get_first_chart_data', code)
        if not all(dict_tuple): return
        if dict_tuple[0]:
            self.cht_dt.set_chart_data(code, dict_tuple[0], 'mi', 1)
        if dict_tuple[1]:
            self.cht_dt.set_chart_data(code, dict_tuple[1], 'dy', 1)

    def request_tick_chart(self, tickers_set):
        logging.debug(f"request_tick_chart 요청: {tickers_set}")
        for code in tickers_set:
            self.request_first_chart_data(code, cycle='tk', tick=30, times=99, wt=1.667, dt=dc.ToDay)
    
    def request_first_chart_data(self, code, cycle, tick=1, times=1, wt=None, dt=None):
        dict_list = self.prx.answer('api', 'get_chart_data', code, cycle, tick, times, wt, dt)
        if not dict_list: return
        self.prx.order('dbm', 'upsert_chart', dict_list, cycle, tick)

class OrderCommander(QThread):
    def __init__(self, prx, order_q):
        super().__init__()
        self.daemon = True
        self.prx = prx
        self.order_q = order_q
        self.ord = TimeLimiter(name='ord', second=5, minute=100, hour=1000)
        self.running = False

    def stop(self):
        self.running = False
        self.order_q.put(None)

    def run(self):
        self.running = True
        while self.running:
            self.send_order()

    def send_order(self):
        if not self.com_order_time_check(): return -308 # 5회 제한 초과
        order = self.order_q.get()
        if order is None: 
            self.running = False
            return
        self.com_SendOrder(**order)

    def com_order_time_check(self):
        wait_time = self.ord.check_interval()
        if wait_time > 1666: # 1.666초 이내 주문 제한
            msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {float(wait_time/1000)} 초'
            gm.toast.toast(msg, duration=dc.TOAST_TIME)
            logging.warning(msg)
            return False
       
        elif wait_time > 1000:
            msg = f'빈번한 요청은 시간 제한을 받습니다. 잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
            gm.toast.toast(msg, duration=wait_time)
            time.sleep((wait_time-10)/1000) 
            wait_time = 0
            logging.info(msg)
        elif wait_time > 0:
            msg = f'잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
            gm.toast.toast(msg, duration=wait_time)
            logging.info(msg)

        time.sleep((wait_time+100)/1000) 
        self.ord.update_request_times()
        return True

    def com_SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno, msg=None):

        전략명칭 = gm.실행전략['전략명칭']
        매수전략 = gm.설정전략['매수전략']

        name = self.prx.answer('api', 'GetMasterCodeName', code)
        #logging.debug(f'주문 요청 확인: code={code}, name={name}')
        주문유형 = dc.fid.주문유형FID[ordtype]

        kind = msg if msg else 주문유형
        job = {"구분": kind, "전략명칭": 전략명칭, "종목코드": code, "종목명": name, "주문수량": quantity, "주문가격": price}
        gm.admin.send_status_msg('주문내용', job)

        rqname = f'{rqname}_{code}_{name}_{datetime.now().strftime("%H%M%S.%f")}'
        key = (code, 주문유형.lstrip("신규"))
        gm.주문진행목록.set(key=key, data={'상태': '전송', '요청명': rqname})
        logging.debug(f'{kind}주문 전송: key={key}, rqname={rqname}')

        cmd = { 'rqname': rqname, 'screen': screen, 'accno': accno, 'ordtype': ordtype, 'code': code, 'hoga': hoga, 'quantity': quantity, 'price': price, 'ordno': ordno }
        self.prx.order('api', 'SendOrder', **cmd)

        dict_data = {'전략명칭': 전략명칭, '주문구분': 주문유형, '주문상태': '주문', '종목코드': code, '종목명': name, \
                     '주문수량': quantity, '주문가격': price, '매매구분': '지정가' if hoga == '00' else '시장가', '원주문번호': ordno, 'sim_no': gm.sim_no}
        self.prx.order('dbm', 'table_upsert', db='db', table='trades', dict_data=dict_data)

class EvalStrategy(QThread):
    def __init__(self, prx, eval_q):
        super().__init__()
        self.daemon = True
        self.name = 'evl'
        self.prx = prx
        self.eval_q = eval_q
        self.clear_timer = None
        self.start_time = '09:00' # 매수시간 시작
        self.stop_time = '15:18'  # 매수시간 종료
        self.running = False
        self.cht_dt = ChartData()
        self.sell_executor = ThreadPoolExecutor(max_workers=3)
        self.buy_executor = ThreadPoolExecutor(max_workers=1)

    def set_dict(self, new_dict: dict) -> None:
        """딕셔너리 업데이트 및 인스턴스 변수 동기화"""
        try:
            for key, value in new_dict.items():
                setattr(self, key, value)
            self.set_clear_timer()
        except Exception as e:
            logging.error(f'딕셔너리 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stop(self):
        self.running = False
        if self.clear_timer:
            self.clear_timer.cancel()
            self.clear_timer = None
        self.eval_q.put(None)
        self.sell_executor.shutdown(wait=True)
        self.buy_executor.shutdown(wait=True)

    def run(self):
        self.running = True
        while self.running:
            data = self.eval_q.get()
            if data is None:
                self.running = False
                break
            self.eval_order(data)

    def eval_order(self, data):
        if 'time' in data[2]:
            if data[2]['time'] > datetime.now() - timedelta(seconds=0.4):
                time.sleep(0.005)
                self.eval_q.put(data)
                return
        if data[1] == 'buy': 
            self.buy_executor.submit(self.order_buy, data[0], data[2].get('rqname', '신규매수'), data[2].get('price', 0))
        elif data[1] == 'sell': 
            self.sell_executor.submit(self.order_sell, data[0], data[2].get('row', {}), data[2].get('sell_condition', False))
        elif data[1] == 'cancel': 
            self.buy_executor.submit(self.order_cancel, data[0], data[2].get('kind', ''), data[2].get('order_no', ''))

    def is_buy_callback(self, future, data):
        try:
            is_ok, send_data, reason = future.result()
            if is_ok:
                logging.info(f'매수결정: {reason}\nsend_data={send_data}')
                gm.order_q.put(send_data)
                return
            
            if 'time' in data:
                if data['time'] < datetime.now() - timedelta(seconds=0.1):
                    time.sleep(0.005)
                    self.eval_q.put((data['code'], 'buy', data))
                    return
                else:
                    data.pop('time')

            if 'script' in data:
                if '차트미비' not in reason: 
                    logging.info(f'매수안함: {reason} send_data={send_data}')
                key = (data[0], '매수')
                if gm.주문진행목록.in_key(key):
                    gm.주문진행목록.delete(key=key)
        except Exception as e:
            logging.error(f'주문 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    def is_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        """매수 조건 충족 여부를 확인하는 메소드"""
        name = gm.dict종목정보.get(code, sub_key='종목명')

        if not gm.sim_on:
            status_market = com_market_status()
            if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

        if not gm.counter.can_buy_group(self.체결횟수): 
            return False, {}, f"전략별 매수 횟수 제한 {code} {name} 매수횟수={self.체결횟수} 회 초과"

        if not gm.counter.can_buy_ticker(code, self.종목제한): 
            return False, {}, f"종목별 매수 횟수 제한 {code} {name} 종목제한{self.종목제한} 회 초과"

        if self.금지율적용:
            if not gm.counter.can_buy_loss_rate(code, self.금지율):
                ticker_info = gm.counter.data.get(code, {})
                return False, {}, f"손실율 제한 초과 {code} {name} 최대손실율={ticker_info.get('rate', 0):.2f}% > 제한={self.금지율}%"

        if self.금지횟수적용:
            if not gm.counter.can_buy_loss_times(code, self.금지횟수):
                ticker_info = gm.counter.data.get(code, {})
                return False, {}, f"손실횟수 제한 초과 {code} {name} 손실횟수={ticker_info.get('times', 0)}회 > 제한={self.금지횟수}회"

        if self.중복매수금지 and gm.잔고목록.in_key(code):
            return False, {}, f"보유 종목 재매수 금지 ({code} {name})"

        if gm.잔고목록.len() >= self.보유제한:
            return False, {}, f"보유 종목수 제한 {code} {name} \
            보유종목={gm.잔고목록.len()}종목/보유제한={self.보유제한} 종목 초과" # 전략별 보유로 계산

        if gm.sim_no == 0:
            now = datetime.now().time()
            if self.운영시간:
                start_time = datetime.strptime('09:00', '%H:%M').time()
                stop_time = datetime.strptime('15:18', '%H:%M').time()
                if not start_time <= now <= stop_time: return False, {}, f"운영시간 아님 {start_time} ~ {stop_time} ({code} {name})"
            if self.설정시간:
                start_time = datetime.strptime(self.시작시간, '%H:%M').time()
                stop_time = datetime.strptime(self.종료시간, '%H:%M').time()
                if not start_time <= now <= stop_time: return False, {}, f"설정시간 아님 {start_time} ~ {stop_time} ({code} {name})"
            if self.당일청산:
                sell_time = datetime.strptime(self.청산시간, '%H:%M').time()
                if now >= sell_time: return False, {}, f"청산시간 이후 매수 취소 {sell_time} ({code} {name})"

        try:
            send_data = {
                'rqname': rqname,
                'screen': dc.scr.화면['신규매수'],
                'accno': gm.account,
                'ordtype': 1,  # 매수
                'code': code,
                'quantity': 0,
                'price': price,
                'hoga': '03' if self.매수시장가 else '00',
                'ordno': '',
            }

            if gm.sim_no != 1 and self.매수스크립트적용: # 다시 넣기 때문에 hoga()계산 전에 (price가 변경 됨)
                if self.cht_dt.is_code_registered(code):
                    try:
                        매수일시 = datetime.now().strftime('%Y%m%d%H%M%S')
                        result = gm.scm.run_script(self.매수스크립트, kwargs={'code': code, 'name': name, 'price': price, 'qty': send_data['quantity'], 'buy_dt': ''})
                        gm.qwork['msg'].put(Work('스크립트', job={'msg': result['logs']}))
                        if result.get('error') or not result.get('result', False):
                            msg = f"스크립트 : {code} {name} 매수취소 {result['error'] if result.get('error') else ''}"
                            gm.qwork['msg'].put(Work('주문내용', job={'msg': msg}))
                            return False, {}, msg
                        logging.info(f">>> 매수스크립트 조건 충족: {code} {name}")

                    except Exception as e:
                        logging.error(f'매수스크립트 검사 오류: {code} {name} - {type(e).__name__} - {e}', exc_info=True)
                else:
                    # 다시 넣음 최대 0.1초 동안 차트데이타 준비될 때까지 반복함
                    logging.error(f'차트데이터 준비 안 됨: 매수 {code} {name} {price}')
                    gm.eval_q.put((code, 'buy', {'rqname': '신규매수', 'price': price, 'time': datetime.now()}))
                    return False, {}, f"차트미비: {code} {name}"

            # 호가구분과 가격 설정
            if self.매수지정가:
                price = hoga(price, self.매수호가)
                send_data['price'] = price

            # 수량 계산
            if self.투자금:
                if self.투자금액 > 0 and price > 0:
                    send_data['quantity'] = int((self.투자금액 + price) / price) # 최소 1주 매수는 int((투자금액 + price) / price)
            else: # self.매수량:
                send_data['quantity'] = self.매수수량

            if send_data['quantity'] > 0:
                return True, send_data, f"매수신호 : {code} {name} quantity={send_data['quantity']} price={send_data['price']}"

            return False, send_data, f"수량없음 : {code} {name} quantity={send_data['quantity']} price={send_data['price']}"

        except Exception as e:
            logging.error(f'매수조건 확인 중 오류: {type(e).__name__} - {e}', exc_info=True)
            return False, send_data, "검사오류"

    def order_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_buy(code, rqname, price) # rqname : 전략
        if is_ok:
            logging.info(f'매수결정: {reason}')
            logging.debug(f'send_data={send_data}')
            gm.order_q.put(send_data)
        else:
            if '차트미비' not in reason: 
                logging.info(f'매수안함: {reason}')
            key = (code, '매수')
            if gm.주문진행목록.in_key(key):
                gm.주문진행목록.delete(key=key)

        return is_ok, send_data, reason

    def is_sell(self, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        try:
            if gm.sim_no == 0:
                status_market = com_market_status()
                if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

            code = row.get('종목번호', '')          # 종목번호 ='999999' 일 때 당일청산 매도
            rqname = row.get('rqname', '신규매도')  # 매도 조건 검사 신호 이름
            종목명 = row.get('종목명', '')          # 종목번호 = '999999' 일 때 '당일청산 매도'
            매입가 = row.get('매입가', 0)           # 종목번호 = '999999' 일 때 0
            현재가 = row.get('현재가', 0)           # 종목번호 = '999999' 일 때 0
            보유수량 = row.get('보유수량', 0)       # gm.잔고목록.get(key=code, column='보유수량')
            수익율 = float(row.get('수익률(%)', 0))
            매수일시 = row.get('매수일자', '')+row.get('매수시간', '').replace(':', '')

            send_data = {
                'rqname': rqname,
                'screen': dc.scr.화면['신규매도'],
                'accno': gm.account,
                'ordtype': 2,  # 매도
                'code': code,
                'quantity': 보유수량,
                'price': 0, # 지정가 경우 아래에서 적용 함
                'hoga': '03' if self.매도시장가 else '00',
                'ordno': '',
            }

            script_or = self.매도스크립트적용 and self.매도스크립트OR

            if code == '999999' and gm.sim_no == 0:
                #if self.당일청산 and datetime.now().strftime('%H:%M') >= self.청산시간:
                    send_list = []
                    rows = gm.잔고목록.get()
                    logging.info(f'당일청산: {rows}')
                    if not rows: return False, {}, "당일청산 종목 없음"

                    if self.청산시장가:
                        send_list = [{**send_data, 'code': row['종목번호'], 'price': 0, 'quantity': row['보유수량'], 'msg': '청산시장'} for row in rows]
                    elif self.청산지정가:
                        send_list = [{**send_data, 'code': row['종목번호'], 'price': hoga(row['현재가'], self.청산호가), 'quantity': row['보유수량'], 'hoga': '01', 'msg': '청산지정'} for row in rows]

                    gm.admin.매도취소 = False
                    return True, send_list, f"당일청산: 청산시간={self.청산시간}, {code} {종목명}"

            if self.매도지정가:
                send_data['price'] = hoga(현재가, self.매도호가)
                send_data['msg'] = '매도지정'

            if sell_condition and script_or: # self.매도적용 조건
                    send_data['msg'] = '검색매도'
                    return True, send_data,  f"검색매도: {code} {종목명}"
            
            # not sell_condition or not script_or
            elif self.매도스크립트적용 and gm.sim_no != 1:
                if self.cht_dt.is_code_registered(code):
                    result = gm.scm.run_script(self.매도스크립트, kwargs={'code': code, 'name': 종목명, 'price': 매입가, 'qty': 보유수량, 'buy_dt': 매수일시})
                    if not result['error']:
                        if result.get('result', False): # self.매도스크립트AND 조건
                            send_data['msg'] = '전략매도'
                            gm.qwork['msg'].put(Work('스크립트', job={'msg': result['logs']}))
                            logging.info(f">>> 매도스크립트 조건 충족: {code} {종목명} {매입가} {보유수량}")
                            return True, send_data, f"전략매도: {code} {종목명}"
                    else:
                        logging.error(f'스크립트 실행 에러: {result["error"]}')
                        gm.qwork['msg'].put(Work('스크립트', job={'msg': result['logs']}))
                else:
                    # 다시 넣음 최대 0.1초 동안 차트데이타 준비될 때까지 반복함
                    logging.error(f'차트데이터 준비 안 됨: 매도 {code} {종목명} {매입가} {보유수량}')
                    gm.eval_q.put((code, 'sell', {'code': code, 'row': row, 'sell_condition': sell_condition, 'time': datetime.now()}))
                    return False, {}, f"차트미비: {code} {종목명}"

            if self.로스컷 and self.로스컷율 != 0:
                send_list = []
                매입금액, 평가손익 = gm.잔고목록.sum(columns=['매입금액', '평가손익'])
                수익율 = (평가손익 / 매입금액) * 100 if 매입금액 > 0 else 0

                if self.로스컷율 > 0 and 수익율 <= self.로스컷율 or self.로스컷율 < 0 and 수익율 >= self.로스컷율: 
                    return False, {}, f"로스컷: 수익율={수익율} 로스컷율={self.로스컷율}"
                
                gm.admin.매도취소 = False

                rows = gm.잔고목록.get()
                if self.로스컷시장가:
                    send_list = [{**send_data, 'code': row['종목번호'], 'price': 0, 'quantity': row['보유수량'], 'msg': '로스컷장'} for row in rows]
                else:
                    if self.로스컷상하 == '이상':
                        send_list = [{**send_data, 'code': row['종목번호'], 'price': 0, 'quantity': row['보유수량'], 'msg': '로스컷상'} for row in rows if row['수익률(%)'] >= self.로스컷지정가율]
                    else:
                        send_list = [{**send_data, 'code': row['종목번호'], 'price': 0, 'quantity': row['보유수량'], 'msg': '로스컷하'} for row in rows if row['수익률(%)'] <= self.로스컷지정가율]

                if send_list:
                    return True, send_list, f"로스컷 : 로스컷율={self.로스컷율}"

                return True, send_data, f"로스컷 : {code} {종목명}"

            if self.손실제한:
                send_data['msg'] = '손실제한'
                if 수익율 + self.손실제한율 <= 0:
                    return True, send_data, f"손실제한: 손실제한율={self.손실제한율} 수익율={수익율}  {code} {종목명}"

            if self.이익보존:
                send_data['msg'] = '이익보존'
                if row.get('보존', 0):
                    if 수익율 <= self.이익보존율:
                        return True, send_data, f"이익보존: 이익보존율={self.이익보존율} 수익율={수익율}  {code} {종목명}"

            if self.이익실현:
                if 수익율 >= self.이익실현율:
                    send_data['msg'] = '이익실현'
                    return True, send_data, f"이익실현: 이익실현율={self.이익실현율} 수익율={수익율}  {code} {종목명}"

            if self.감시적용:
                if row.get('감시', 0):  # 감시 시작점 설정
                    최고가 = row.get('최고가', 0)
                    고점대비하락률 = ((현재가 - 최고가) / 최고가) * 100
                    if 고점대비하락률 + self.스탑주문율 <= 0:
                        send_data['msg'] = '스탑주문'
                        return True, send_data, f"스탑주문율: 스탑주문율율={self.스탑주문율} 수익율={수익율}  {code} {종목명}"

            return False, {}, "조건없음"

        except Exception as e:
            logging.error(f'매도조건 확인 중 오류: {type(e).__name__} - {e}', exc_info=True)
            return False, {}, "검사오류"

    def order_sell(self, code, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_sell(row, sell_condition)
        if reason not in ["조건없음", "장 운영시간이 아님"]:
            logging.info(f'매도결정: {reason}')
            logging.debug(f'send_data={send_data}')
        if is_ok:
            # 매도 상태 저장 (같은 봉에서 재매수 방지)
            from chart import ChartManager
            try:
                m3 = ChartManager(code, 'mi', 3)
                현재가 = row.get('현재가', 0)
                gm.scm.set_trade_state(code, 'sell', {
                    'bar_time': m3.bar_time(),
                    'sell_price': 현재가,
                    'reason': reason
                })
            except Exception as e:
                logging.error(f'매도 상태 저장 오류: {type(e).__name__} - {e}')
            
            if not self.매도적용:
                gm.admin.send_status_msg('주문내용', {'구분': f'매도편입', '종목코드': code, '종목명': row['종목명'], '메시지': '/ 검사결과'})
            if isinstance(send_data, list):
                logging.debug(f'** 복수 매도 주문진행목록 **: {send_data}')
                for data in send_data:
                    gm.order_q.put(data)
            else:
                gm.order_q.put(send_data)
        else:
            key = (code, '매도')
            if gm.주문진행목록.in_key(key):
                gm.주문진행목록.delete(key=key)

        return is_ok, send_data, reason

    def order_cancel(self, code, kind, order_no):
        try:
            send_data = {
                'rqname': kind+'xx',
                'screen': dc.scr.화면[kind+'취소'],
                'accno': gm.account,
                'ordtype': 3 if kind == '매수' else 4,
                'code': code,
                'quantity': 0,
                'price': 0,
                'hoga': '',
                'ordno': order_no
            }
            logging.debug(f'주문취소: {order_no} {send_data}')
            gm.order_q.put(send_data)
        except Exception as e:
            logging.error(f'주문취소 오류: {type(e).__name__} - {e}', exc_info=True)

    def set_clear_timer(self):
        now = datetime.now()
        if self.당일청산 and gm.sim_no == 0:
            if self.clear_timer is not None:
                self.clear_timer.cancel()
                self.clear_timer = None
            start_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.청산시간}", '%Y-%m-%d %H:%M')
            delay_sec = max(0, (start_time - now).total_seconds() - 0.1)  # stop()전 실행해야 함
            self.clear_timer = threading.Timer(delay_sec, self.on_clear_timer)
            self.clear_timer.start()
            logging.info(f"당일청산 타이머 설정: {self.청산시간}, {delay_sec}초 후 실행")

    def on_clear_timer(self):
        try:
            # is_sell을 부르기 위해 더미 데이터로 콜 하고 실제 청산 루틴에서 실 데이터를 처리 함
            row = {'종목번호': '999999', '종목명': '당일청산매도', '현재가': 9, '매입가': 9, '보유수량': 9, '수익률(%)': 0}
            self.order_sell('999999', row)
            #gm.eval_q.put(('999999', 'sell', {'row': row}))
            logging.info("당일청산 타이머 실행")
        except Exception as e:
            logging.error(f'당일청산 타이머 콜백 오류: {type(e).__name__} - {e}', exc_info=True)

