from classes import ModelThread
from public import *
from PyQt5.QtCore import QTimer
from tabulate import tabulate
from datetime import datetime
from typing import Any
import logging
import threading

class Strategy(ModelThread):
    def __init__(self, name, qdict, cls=None, 전략정의=None):
        super().__init__(name, qdict, cls)
        self.name = name
        self.전략 = name
        self.전략번호 = int(name[-2:])
        self.전략정의 = 전략정의 if 전략정의 else dc.const.DEFAULT_STRATEGY_SETS
        self.buy_cond_idx = 0
        self.buy_cond_name = ''
        self.sell_cond_idx = 0
        self.sell_cond_name = ''
        self.loss_cut_timer = None
        self.clear_timer = None
        self.start_time = '09:00'
        self.stop_time = '15:18'
        self.end_timer = None
        self.start_timer = None
        self.lock = threading.Lock()

        self.init()

    def init(self):
        for key, value in self.전략정의.items():
            setattr(self, key, value)
        self.set_index_name()
        self._move_to_dict()
        return self

    def set_index_name(self) -> None:
        if self.매수전략:
            self.buy_cond_idx = int(self.매수전략.split(' : ')[0])
            self.buy_cond_name = self.매수전략.split(' : ')[1]
        if self.매도전략:
            self.sell_cond_idx = int(self.매도전략.split(' : ')[0])
            self.sell_cond_name = self.매도전략.split(' : ')[1]

    def set_dict(self, new_dict: dict) -> None:
        """딕셔너리 업데이트 및 인스턴스 변수 동기화"""
        try:
            전략 = new_dict.get('전략', '')
            if 전략:
                if self.전략 != 전략: raise Exception(f'전략명칭이 변경 될 수 없습니다. {self.전략} -> {전략}')
            self.전략정의.update(new_dict)
            self._move_to_var(new_dict)
            self.set_index_name()
            # self.set_timer()
        except Exception as e:
            logging.error(f'딕셔너리 설정 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)

    def get_dict(self) -> dict:
        """현재 설정된 딕셔너리 반환"""
        try:
            self._move_to_dict()  # dict 업데이트 후 반환
            return self.전략정의
        except Exception as e:
            logging.error(f'딕셔너리 조회 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return {}

    def set(self, key: str, value: Any) -> bool:
        """인스턴스 변수 설정"""
        try:
            if hasattr(self, key):
                setattr(self, key, value)
                self.전략정의[key] = value
                return True
            else:
                logging.warning(f'존재하지 않는 키 설정 시도: {self.전략} - {key}', exc_info=True)
                return False
        except Exception as e:
            logging.error(f'변수 설정 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return False

    def get(self, key: str) -> Any:
        """인스턴스 변수 조회"""
        try:
            if hasattr(self, key):
                return getattr(self, key)
            else:
                logging.warning(f'존재하지 않는 키 조회 시도: {self.전략} - {key}', exc_info=True)
                return None
        except Exception as e:
            logging.error(f'변수 조회 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return None

    def _move_to_var(self, input_dict: dict) -> None:
        """딕셔너리의 값을 인스턴스 변수로 설정"""
        try:
            for key, value in input_dict.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                else:
                    logging.warning(f'알 수 없는 키 무시됨: {self.전략} - {key}')
        except Exception as e:
            logging.error(f'변수 변환 오류: {self.전략} - { type(e).__name__} - {e}', exc_info=True)

    def _move_to_dict(self) -> None:
        """인스턴스 변수를 딕셔너리로 변환"""
        try:
            # self.전략정의에 정의된 인스턴스 변수들만 딕셔너리에 포함
            for key in self.전략정의.keys():
                if hasattr(self, key):
                    self.전략정의[key] = getattr(self, key)
        except Exception as e:
            logging.error(f'딕셔너리 변환 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)

    def get_ticker_remain_count(self, code, name):
        try:
            gm.json_counter_tickers.setdefault(self.전략, {})
            dict종목 = gm.json_counter_tickers[self.전략].setdefault(code, {'종목명': name, '종목제한': self.종목제한, '종목잔회': self.종목제한})
            if self.종목제한 != dict종목.get('종목제한', 0):
                dict종목['종목제한'] = self.종목제한
                dict종목['종목잔회'] = self.종목제한
                gm.json_counter_tickers[self.전략][code].update({'종목제한': self.종목제한, '종목잔회': self.종목제한})
            return dict종목.get('종목잔회', 0)

        except Exception as e:
            logging.error(f'종목잔회 조회 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return 0

    def get_strategy_remain_count(self):
        try:
            dict전략 = gm.json_counter_strategy.setdefault(self.전략, {'전략명칭': self.전략명칭, '체결횟수': self.체결횟수, '남은횟수': self.체결횟수})
            체결횟수 = dict전략.get('체결횟수', 0)
            if self.체결횟수 != 체결횟수 or self.전략명칭 != dict전략.get('전략명칭', ''):
                gm.json_counter_strategy[self.전략].update({'전략명칭': self.전략명칭, '체결횟수': self.체결횟수, '남은횟수': self.체결횟수})
            return gm.json_counter_strategy.get(self.전략, {}).get('남은횟수', 0)
        except Exception as e:
            logging.error(f'남은횟수 조회 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return 0

    def is_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        """매수 조건 충족 여부를 확인하는 메소드"""
        if not gm.config.sim_on:
            status_market = gm.pro.admin.com_market_status()
            if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

        if not code:
            logging.warning(f'종목코드가 없습니다. 매수 조건 검사 실패: {self.전략} - {rqname}')
            return False, {}, f"종목코드없음 : {code} "
        name = gm.dict종목정보[code].get('종목명', '')

        logging.debug(f'매수조건 확인 시작: rqname={rqname} code={code} name={name} price={price}')

        남은횟수 = self.get_strategy_remain_count()
        if 남은횟수 <= 0: return False, {}, f"전략별 매수 횟수 제한 {code} {name} 남은횟수={남은횟수}회/매수횟수={self.체결횟수} 회 초과"

        if self.중복매수금지 and gm.잔고목록.in_key(code): return False, {}, f"보유 종목 재매수 금지 ({code} {name})"

        종목잔회 = self.get_ticker_remain_count(code, name)
        if 종목잔회 <= 0: return False, {}, f"종목별 매수 횟수 제한 {code} {name} 남은횟수={종목잔회}회/종목제한{self.종목제한} 회 초과"

        if gm.잔고목록.len(filter={'전략': self.전략}) >= self.보유제한:
            return False, {}, f"보유 종목수 제한 {code} {name} \
            보유종목={gm.잔고목록.len(filter={'전략': self.전략})}종목/보유제한={self.보유제한} 종목 초과" # 전략별 보유로 계산

        if not gm.config.sim_on:
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
                'screen': dc.scr.화면[rqname],
                'accno': gm.config.account,
                'ordtype': 1,  # 매수
                'code': code,
                'quantity': 0,
                'price': price,
                'hoga': '03' if self.매수시장가 else '00',
                'ordno': ''
            }

            # 호가구분과 가격 설정
            if self.매수지정가:
                send_data['price'] = hoga(price, self.매수호가)

            # 수량 계산
            if self.투자금:
                if self.투자금액 > 0 and price > 0:
                    send_data['quantity'] = int((self.투자금액 + price)/ price) # 최소 1주 매수
            elif self.예수금:
                pass
                #예수금액 = self.예수금 * (self.예수금율 / 100)
                #if 예수금액 > 0 and price > 0:
                #    send_data['quantity'] = int(예수금액 / price)

            if send_data['quantity'] > 0:
                return True, send_data, f"매수신호 : {code} {name} quantity={send_data['quantity']} price={send_data['price']}"

            return False, send_data, f"수량없음 : {code} {name} quantity={send_data['quantity']} price={send_data['price']}"

        except Exception as e:
            logging.error(f'매수조건 확인 중 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return False, send_data, "검사오류"

    def order_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_buy(code, rqname, price) # rqname : 전략
        logging.info(f'매수: {self.전략} - {reason}\nsend_data={send_data}')
        if is_ok:
            gm.pro.admin.com_SendOrder(self.전략번호, **send_data)
        else:
            if code in gm.dict매수요청목록:
                del gm.dict매수요청목록[code]
        return is_ok, send_data, reason

    def is_sell(self, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        """매도 조건 충족 여부를 확인하는 메소드"""
        try:
            if not gm.config.sim_on:
                status_market = gm.pro.admin.com_market_status()
                if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

            code = row.get('종목번호', '')          # 종목번호 ='999999' 일 때 당일청산 매도
            rqname = row.get('rqname', '신규매도')  # 매도 조건 검사 신호 이름
            종목명 = row.get('종목명', '')          # 종목번호 = '999999' 일 때 '당일청산 매도'
            매입가 = int(row['매입가'])             # 종목번호 = '999999' 일 때 9
            현재가 = int(row['현재가'])             # 종목번호 = '999999' 일 때 9

            수익률 = float(row.get('수익률(%)', 0))

            if not code:
                logging.warning(f'종목번호가 없습니다. 매도 조건 검사 중단: {self.전략} - {rqname} {종목명}')
                return False, {}, "종목번호없음"

            send_data = {
                'rqname': rqname,
                'screen': dc.scr.화면[rqname],
                'accno': gm.config.account,
                'ordtype': 2,  # 매도
                'code': code,
                'quantity': row.get('보유수량', 0), #row.get('매도가능수량', row.get('보유수량', 0)),
                'price': 현재가,
                'hoga': '03' if self.매도시장가 else '00',
                'ordno': ''
            }

            # 호가구분과 가격 설정
            if self.매도지정가:
                send_data['price'] = hoga(현재가, self.매도호가)
                send_data['msg'] = '매도지정'

            if self.매도적용 and sell_condition: # 매도수식 검색 종목이므로 그냥 매도
                send_data['msg'] = '매도수식'
                return True, send_data,  f"매도수식:  {code} {종목명}"

            if gm.config.sim_on and (수익률 > 30 or 수익률 < -30):
                return False, {}, f"시뮬레이션 비정상 수익률: {code} {종목명} 매입가={매입가} 현재가={현재가} 수익률={수익률}"

            if self.로스컷 and self.로스컷율 + gm.잔고목록.sum(filter={'전략': self.전략}, columns='수익률(%)') <= 0:
                send_list = []
                rows = gm.잔고목록.get(filter={'전략': self.전략})
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

            if not gm.config.sim_on:
                if self.당일청산 and datetime.now().strftime('%H:%M') >= self.청산시간:
                    send_list = []
                    rows = gm.잔고목록.get(filter={'전략': self.전략})
                    if self.청산시장가:

                        send_list = [{**send_data, 'code': code, 'price': 0, 'quantity': row['보유수량'], 'msg': '청산시장'} for row in rows]
                    else:
                        send_list = [{**send_data, 'code': code, 'price': hoga(현재가, self.청산호가), 'quantity': row['보유수량'], 'hoga': '01', 'msg': '청산지정'} for row in rows]

                    if send_list:
                        return True, send_list, f"당일청산: 청산시간={self.청산시간}"

                    return True, send_data, f"당일청산: 청산시간={self.청산시간}, {code} {종목명}"

            # 손실제한 확인
            if self.손실제한:
                send_data['msg'] = '손실제한'
                if 수익률 + self.손실제한율 <= 0:
                    return True, send_data, f"손실제한: 손실제한율={self.손실제한율} 수익률={수익률}  {code} {종목명}"

            if self.이익보존:
                send_data['msg'] = '이익보존'
                if row.get('보존', 0):
                    if 수익률 <= self.이익보존율:
                        return True, send_data, f"이익보존: 이익보존율={self.이익보존율} 수익률={수익률}  {code} {종목명}"

            if self.이익실현:
                if 수익률 >= self.이익실현율:
                    send_data['msg'] = '이익실현'
                    return True, send_data, f"이익실현: 이익실현율={self.이익실현율} 수익률={수익률}  {code} {종목명}"

            # 감시적용 확인
            if self.감시적용:
                if row.get('감시', 0):  # 감시 시작점 설정
                    최고가 = row.get('최고가', 0)
                    고점대비하락률 = ((현재가 - 최고가) / 최고가) * 100
                    if 고점대비하락률 + self.스탑주문율 <= 0:
                        send_data['msg'] = '스탑주문'
                        return True, send_data, f"스탑주문율: 스탑주문율율={self.스탑주문율} 수익률={수익률}  {code} {종목명}"

            return False, {}, "조건없음"

        except Exception as e:
            logging.error(f'매도조건 확인 중 오류: {self.전략} - {type(e).__name__} - {e}', exc_info=True)
            return False, {}, "검사오류"

    def order_sell(self, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_sell(row, sell_condition)
        if reason not in ["조건없음", "장 운영시간이 아님"]:
            logging.info(f'매도: {self.전략} - {reason}\nsend_data={send_data}')
        if is_ok:
            if isinstance(send_data, list):
                for data in send_data:
                    gm.pro.admin.com_SendOrder(self.전략번호, **data)
            else:
                gm.pro.admin.com_SendOrder(self.전략번호, **send_data)
        else:
            if row['종목번호'] in gm.dict매도요청목록:
                del gm.dict매도요청목록[row['종목번호']]
        return is_ok, send_data, reason

    def order_cancel(self, kind, order_no, code):
        try:
            rqname = '매수취소' if kind == '매수' else '매도취소'

            send_data = {
                'rqname': rqname,
                'screen': dc.scr.화면[rqname],
                'accno': gm.config.account,
                'ordtype': 3 if rqname == '매수취소' else 4,
                'code': code,
                'quantity': 0,
                'price': 0,
                'hoga': '',
                'ordno': order_no
            }
            logging.debug(f'주문취소: {self.전략} - {order_no} {send_data}')
            gm.pro.admin.com_SendOrder(self.전략번호, **send_data)
        except Exception as e:
            logging.error(f'주문취소 오류: {type(e).__name__} - {e}', exc_info=True)

    def set_timer(self):
        now = datetime.now()
        current = now.strftime('%H:%M')
        if self.당일청산:
            if self.clear_timer is None:
                self.clear_timer = QTimer()
                row = {'종목번호': '999999', '종목명': '당일청산매도', '현재가': 0, '매수가': 0, '수익률(%)': 0 }
                self.clear_timer.timeout.connect(lambda: self.order_sell(row))
            if self.clear_timer.isActive():
                self.clear_timer.stop()
            start_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.청산시간}", '%Y-%m-%d %H:%M')
            delay_ms = int((start_time - now).total_seconds() * 1000)
            self.clear_timer.setSingleShot(True)
            self.clear_timer.start(delay_ms)

    def cdn_fx실행_전략초기화(self):
        try:
            msg = self.cdn_fx체크_전략매매()
            if msg: return msg
            self.cdn_fx실행_전략매매()
            gm.json_counter_strategy.setdefault(self.전략, {'전략명칭': self.전략명칭, '체결횟수': self.체결횟수, '남은횟수': self.체결횟수})
            if gm.json_counter_strategy[self.전략]['전략명칭'] == self.전략명칭:
                gm.json_counter_strategy[self.전략] = {'전략명칭': self.전략명칭, '체결횟수': self.체결횟수, '남은횟수': self.체결횟수}

            if gm.config.gui_on: 
                self.put('gui', Work('set_strategy_toggle', {'run': any(gm.매수문자열들) or any(gm.매도문자열들)}))

        except Exception as e:
            logging.error(f'전략 초기화 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx실행_전략매매(self):
        try:
            def run_trade(cond_idx, cond_name, trade_type):
                condition = f'{int(cond_idx):03d} : {cond_name.strip()}'
                condition_list, bool_ok = self.cdn_fx등록_조건검색(cond_name, cond_idx) #-------------------- 조건 검색 실행
                if bool_ok:
                    if trade_type == '매수':
                        self.cdn_fx등록_종목감시(condition_list, 0) # ------------------------------- 조건 만족 종목 실시간 감시
                        gm.매수문자열들[self.전략번호] = condition
                        self.cdn_fx매수_검색종목(condition_list) # ----------------------------------------- 조건 만족 종목 매수
                    elif trade_type == '매도':
                        gm.매도문자열들[self.전략번호] = condition
                        self.cdn_fx매도_검색종목(condition_list) # ----------------------------------------- 조건 만족 종목 매도
                    logging.info(f'전략 실행 - {self.전략} : {self.전략명칭} {trade_type}전략={condition}')
                else:
                    logging.warning(f'전략 실행 실패 - 전략={self.전략} 전략명칭={self.전략명칭} {trade_type}전략={condition}') # 같은 조건 1분 제한 조건 위반

            if self.매수적용: run_trade(self.buy_cond_idx, self.buy_cond_name, '매수')
            if self.매도적용: run_trade(self.sell_cond_idx, self.sell_cond_name, '매도')

        except Exception as e:
            logging.error(f'전략 매매 실행 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx실행_전략마무리(self, buy_stop=True, sell_stop=True):
        try:
            if not (gm.매수문자열들[self.전략번호] or  gm.매도문자열들[self.전략번호]): return
            if self.end_timer:
                self.end_timer.stop()
                self.end_timer = None
            if self.start_timer:
                self.start_timer.stop()
                self.start_timer = None
            self.cdn_fx중지_전략매매(buy_stop, sell_stop)

            if buy_stop:
                gm.매수문자열들[self.전략번호] = None
            if sell_stop:
                gm.매도문자열들[self.전략번호] = None

            if buy_stop and sell_stop:
                gm.전략쓰레드[self.전략번호] = None
                self.stop()

            if buy_stop and not sell_stop:
                gm.toast.toast(f'{self.전략} 매수전략 {gm.매수문자열들[self.전략번호]}이 종료되었습니다.')


        except Exception as e:
            logging.error(f'전략 마무리 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx중지_전략매매(self, buy_stop=True, sell_stop=True):
        try:
            def stop_trade(cond_idx, cond_name, trade_type):
                if cond_name:
                    gm.pro.api.SendConditionStop(screen=dc.scr.화면[self.전략], cond_name=cond_name, index=cond_idx)
                else:
                    raise Exception(f'{trade_type} 조건이 없습니다.')
                logging.info(f'{trade_type} 전략 중지 - {self.전략} : {cond_idx:03d} : {cond_name}')
            if buy_stop and self.매수적용: stop_trade(self.buy_cond_idx, self.buy_cond_name, '매수')
            if sell_stop and self.매도적용: stop_trade(self.sell_cond_idx, self.sell_cond_name, '매도')

        except Exception as e:
            logging.error(f'전략 중지 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx등록_조건검색(self, cond_name, cond_idx):
        screen = dc.scr.화면[self.전략]
        logging.debug(f'조건 검색 요청: 전략={self.전략} 화면={screen} 인덱스={cond_idx:03d} 수식명={cond_name}')
        condition_list = []
        try:
            condition_list, bool_ok = gm.pro.admin.com_SendCondition(screen, cond_name, cond_idx, 1) # +++++++ SendCondition
            return condition_list, bool_ok
        except Exception as e:
            logging.error(f'조건 검색 요청 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)
            return [], False

    def cdn_fx매수_검색종목(self, condition_list):
        try:
            for code in condition_list:
                if gm.잔고목록.in_key(code): continue # 기 보유종목
                if gm.매수대기목록.in_key(code) or gm.전송목록.in_key(code) or gm.접수목록.in_column('종목코드', code): continue # 매수중

                종목명 = gm.pro.api.GetMasterCodeName(code=code)
                if code not in gm.dict종목정보:
                    전일가 = gm.pro.api.GetMasterLastPrice(code=code)
                    gm.dict종목정보[code] = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}

                # DataFrame에 새로운 행 추가
                gm.매수대기목록.set(key=code, data={'전략': self.전략, '전략번호': self.전략번호, '종목명': 종목명})
                gm.매수조건목록.set(key=code, data={'전략': self.전략, '종목명': 종목명})

            logging.info(f'매수 종목 검색 결과: {self.전략} result count={len(condition_list)}')
            logging.debug(f'매수 대기 목록 =\n{gm.매수대기목록.get(column=["전략", "종목코드","종목명"])}')
        except Exception as e:
            logging.error(f'매수 종목 검색 요청 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx매도_검색종목(self, condition_list):
        try:
            for code in condition_list:
                if not gm.잔고목록.in_key(code): continue # 매도 할 종목 없음
                if gm.매도대기목록.in_key(code) or gm.전송목록.in_key(code) or gm.접수목록.in_column('종목코드', code): continue # 매도중
                if self.전략 != gm.잔고목록.get(key=code, column='전략'): continue # 전략 다름

                종목명 = gm.pro.api.GetMasterCodeName(code=code)
                if code not in gm.dict종목정보:
                    전일가 = gm.pro.api.GetMasterLastPrice(code=code)
                    gm.dict종목정보[code] = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}

                # DataFrame에 새로운 행 추가
                gm.매도대기목록.set(key=code, data={'전략': self.전략, '전략번호': self.전략번호, '종목명': 종목명})

            logging.info(f'매도 종목 검색 결과: {self.전략} result count={len(condition_list)}')
            logging.debug(f'매도 대기 목록 =\n{gm.매도대기목록.get(column=["전략", "종목코드","종목명"])}')
        except Exception as e:
            logging.error(f'매도 종목 검색 요청 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx편입_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            종목명 = gm.pro.api.GetMasterCodeName(code=code)
            if code not in gm.dict종목정보:
                전일가 = gm.pro.api.GetMasterLastPrice(code=code)
                gm.dict종목정보[code] = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}

            if kind == '매도':
                gm.매도조건목록.set(key=code, data={'전략': self.전략, '종목명': 종목명})
                if not gm.잔고목록.in_key(code): return # 매도 할 종목 없음
                if gm.매도대기목록.in_key(code) or code in gm.dict매도요청목록 or gm.전송목록.in_key(code) or gm.접수목록.in_key(code): return # 매도중
                if self.전략 != gm.잔고목록.get(key=code, column='전략'): return
                gm.매도대기목록.set(key=code, data={'전략': self.전략, '전략번호': self.전략번호, '종목명': 종목명})
                logging.debug(f'매도 대기 목록 =\n{gm.매도대기목록.get(column=["전략", "종목코드", "종목명"])}')
                return

            if not gm.매수조건목록.in_key(code):
                if gm.매수대기목록.in_key(code) or code in gm.dict매수요청목록 or gm.전송목록.in_key(code) or gm.접수목록.in_key(code): return # 매수중
                if gm.잔고목록.in_key(code): return # 기 보유종목
                if code not in gm.dict조건종목감시:
                    self.cdn_fx등록_종목감시([code], 1) # ----------------------------- 조건 만족 종목 실시간 감시 추가

                gm.매수조건목록.set(key=code, data={'전략': self.전략, '종목명': 종목명})
                gm.매수대기목록.set(key=code, data={'전략': self.전략, '전략번호': self.전략번호, '종목명': 종목명})
                logging.debug(f'매수 대기 목록 =\n{gm.매수대기목록.get(column=["전략", "종목코드","종목명"])}')
                if gm.config.gui_on: gm.qdict['msg'].request.put(Work('검색내용', {'msg': f'{kind}편입 : {self.전략} {code} {종목명}'}))
                logging.info(f'{kind}편입 : {self.전략} {self.전략명칭} {code} {종목명}')

        except Exception as e:
            logging.error(f'{kind}조건 편입 처리 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx이탈_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            name = gm.pro.api.GetMasterCodeName(code)
            if kind == '매도':
                if gm.매도조건목록.in_key(code):
                    gm.매도조건목록.delete(key=code)
                return

            if gm.매수조건목록.in_key(code):
                logging.info(f'{kind} 이탈: {self.전략} {self.전략명칭} {code} {name}')
                if gm.config.gui_on: gm.qdict['msg'].request.put(Work('검색내용', {'msg': f'{kind}이탈 : {self.전략} {code} {name}'}))
                gm.매수조건목록.delete(key=code)

            # 실시간 감시 해지하지 않는다.
            if len(gm.dict조건종목감시) > 90:  # 최대 100개 종목 실시간 감시
                gm.pro.api.SetRealRemove(screen=dc.scr.화면[self.전략], del_code=code)
                del gm.dict조건종목감시[code]


        except Exception as e:
            logging.error(f'{kind}조건 이탈 처리 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx등록_종목감시(self, condition_list, search_flag):
        try:
            # 종목 실시간 감시 요청
            if len(condition_list) == 1 and search_flag == 1:
                if condition_list[0] in gm.dict조건종목감시: return

            codes = ",".join(condition_list)
            fids = "10"  # 현재가
            gm.pro.api.SetRealReg(screen=dc.scr.화면[self.전략], code_list=codes, fid_list=fids, opt_type=search_flag)
            gm.dict조건종목감시.update({code: fids for code in condition_list})
            logging.debug(f'실시간 감시 요청: {gm.dict조건종목감시.keys()}')
        except Exception as e:
            logging.error(f'종목 검색 요청 오류: {self.전략} {type(e).__name__} - {e}', exc_info=True)

    def cdn_fx체크_전략매매(self):
        try:
            if self.매수적용:
                매수전략 = self.매수전략.strip()
                if 매수전략 == '' or 매수전략 == dc.const.NON_STRATEGY:
                    return f'{self.전략} 매수전략이 "{dc.const.NON_STRATEGY}" 이거나 없습니다.'
            if self.매도적용:
                매도전략 = self.매도전략.strip()
                if 매도전략 == '' or 매도전략 == dc.const.NON_STRATEGY:
                    return f'{self.전략} 매도전략이 "{dc.const.NON_STRATEGY}" 이거나 없습니다.'
            if self.투자금:
                if self.투자금액 == 0:
                    return f'{self.전략} 투자금액이 0 입니다.'
            if self.예수금:
                if self.예수금율 == 0.0:
                    return f'{self.전략} 예수금율이 0.0 입니다.'
            if self.이익실현:
                if self.이익실현율 == 0.0:
                    return f'{self.전략} 이익실현율이 0.0 입니다.'
            if self.이익보존:
                if self.이익보존율 == 0.0:
                    return f'{self.전략} 이익보존율이 0.0 입니다.'
            if self.손실제한:
                if self.손실제한율 == 0.0:
                    return f'{self.전략} 손실제한율이 0.0 입니다.'
            if self.감시적용:
                if self.감시시작율 == 0.0 and self.스탑주문율 == 0.0:
                    return f'{self.전략} 감시시작율과 스탑주문율이 둘 다 0.0 입니다.'

            if self.설정시간:
                self.start_time = self.시작시간.strip()
                self.stop_time = self.종료시간.strip()

            now = datetime.now()
            current = now.strftime('%H:%M')
            if "15:30" > current > self.stop_time:
                msg = f'{self.전략} 전략 종료시간 지났습니다. {self.stop_time} {current}'
                return msg
            else:
                end_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.stop_time}", '%Y-%m-%d %H:%M')
                remain_ms = int((end_time - now).total_seconds() * 1000)
                self.end_timer = QTimer()
                self.end_timer.timeout.connect(lambda: self.cdn_fx실행_전략마무리(sell_stop=self.매도도같이적용))
                self.end_timer.setSingleShot(True)
                self.end_timer.start(remain_ms)

            if current < self.start_time:
                start_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.start_time}", '%Y-%m-%d %H:%M')
                delay_ms = int((start_time - now).total_seconds() * 1000)
                self.start_timer = QTimer()
                self.start_timer.timeout.connect(lambda: self.cdn_fx실행_전략초기화())
                self.start_timer.setSingleShot(True)
                self.start_timer.start(delay_ms)

        except Exception as e:
            logging.error(f'전략매매 체크 오류: {type(e).__name__} - {e}', exc_info=True)


