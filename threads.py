from PyQt5.QtCore import QThread, pyqtSignal
from classes import TimeLimiter
from public import gm, dc, Work,load_json, save_json, hoga
from tabulate import tabulate
from chart import ChartData
from datetime import datetime
import pandas as pd
import threading
import logging
import time

class ProxyAdmin():
    def __init__(self):
        self.name = 'prx'

    def set_connected(self, connected):
        gm.connected = connected

    def on_fx실시간_장운영감시(self, code, rtype, dictFID): # 장 운영 상황 감시
        gm.admin.on_fx실시간_장운영감시(code, rtype, dictFID)

    def on_fx수신_주문결과TR(self, code, name, order_no, screen, rqname):
        if not gm.config.ready: return
        if gm.주문목록.in_column('요청명', rqname):
            if not order_no:
                logging.debug(f'주문 실패로 주문목록 삭제 : {rqname}')
                gm.주문목록.delete(filter={'요청명': rqname})

    def on_fx실시간_조건검색(self, code, type, cond_name, cond_index): # 조건검색 결과 수신
        if not gm.config.ready: return
        if not gm.config.sim_on and time.time() < 90000: return
        try:
            condition = f'{int(cond_index):03d} : {cond_name.strip()}'
            if condition == gm.매수문자열:
                kind = '매수'
            elif condition == gm.매도문자열:
                kind = '매도'
            else:
                logging.warning(f"조건식 서버 해제 안 됨 : type={type}, condition={condition}")
                return

            job = (kind, code, type, cond_name, cond_index,)
            if type == 'I':
                gm.admin.stg_fx편입_실시간조건감시(*job)  
            elif type == 'D':
                gm.admin.stg_fx이탈_실시간조건감시(*job)
        except Exception as e:
            logging.error(f"쓰레드 찾기오류 {code} {type} {cond_name} {cond_index}: {type(e).__name__} - {e}", exc_info=True)

    def on_fx실시간_주식체결(self, code, rtype, dictFID):
        if not gm.config.ready: return
        try:
            현재가 = abs(int(dictFID['현재가']))
            updated = gm.dict종목정보.update_if_exists(code, '현재가', 현재가)
            if updated:
                data = gm.dict주문대기종목.get(code, None)
                if data:
                    gm.주문목록.set(key=f'{code}_{data["kind"]}', data={'상태': '요청'})
                    if data['kind'] == '매수':
                        gm.admin.eval_q.put({'buy': {'code': code, 'rqname': '신규매수', 'price': 현재가}})
                    elif data['kind'] == '매도':
                        row = gm.잔고목록.get(key=code)
                        row['현재가'] = 현재가
                        gm.admin.eval_q.put({'sell': {'row': row, 'sell_condition': True}})
                    gm.dict주문대기종목.remove(code)

                job = {'code': code, 'dictFID': dictFID}
                gm.admin.chart_q.put(job) # ChartUpdater
            if gm.잔고목록.in_key(code):
                job = {'code': code, 'dictFID': dictFID}
                gm.admin.price_q.put(job) # PriceUpdater
        except Exception as e:
            logging.error(f'실시간 주식체결 처리 오류: {type(e).__name__} - {e}', exc_info=True)

class PriceUpdater(QThread):
    def __init__(self, prx, price_q):
        super().__init__()
        self.prx = prx
        self.price_q = price_q
        self.running = False

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            job = self.price_q.get()
            code = job['code']
            dictFID = job['dictFID']
            self.pri_fx처리_잔고데이터(code, dictFID)
            self.pri_fx검사_매도요건(code)

    def pri_fx처리_잔고데이터(self, code, dictFID):
        try:
            row = gm.잔고목록.get(key=code)
            if not row: return

            현재가 = abs(int(dictFID['현재가']))
            최고가 = row.get('최고가', 0)
            감시율 = row.get('감시시작율', 0.0) / 100
            보존율 = row.get('이익보존율', 0.0) / 100
            감시 = row.get('감시', 0)
            보존 = row.get('보존', 0)
            새감시 = 감시 or ((1 if 현재가 > row['매입가'] * (1 + 감시율) else 0) if 감시율 else 0)
            새보존 = 보존 or ((1 if 현재가 > row['매입가'] * (1 + 보존율) else 0) if 보존율 else 0)

            if 새감시 != 감시 or 새보존 != 보존:
                gm.holdings[code]['감시'] = 새감시
                gm.holdings[code]['보존'] = 새보존
                save_json(dc.fp.holdings_file, gm.holdings)

            보유수량 = int(row['보유수량'])
            매입금액 = int(row['매입금액'])

            매수수수료 = int(매입금액 * gm.수수료율 / 10) * 10            # 매수시 10원 미만 절사
            매도수수료 = int(보유수량 * 현재가 * gm.수수료율 / 10) * 10   # 매도시 10원 미만 절사
            거래세 = int(보유수량 * 현재가 * gm.세금율)                   # 매도시 거래세 0.18% 원미만 절사

            평가금액 = 현재가 * 보유수량 - 매수수수료 - 매도수수료 - 거래세
            평가손익 = 평가금액 - 매입금액
            수익률 = (평가손익 / 매입금액) * 100 if 매입금액 > 0 else 0

            dictFID.update({
                '현재가': 현재가,
                '평가금액': 평가금액,
                '평가손익': 평가손익,
                '수익률(%)': round(수익률, 2),
                '최고가': 현재가 if 현재가 > 최고가 else 최고가,
                '보존': 새보존,
                '감시': 새감시,
                '상태': 1,
            })
            gm.잔고목록.set(key=code, data=dictFID)

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

        except Exception as e:
            logging.error(f'실시간 배치 오류: {type(e).__name__} - {e}', exc_info=True)

    def pri_fx검사_매도요건(self, code):
        if not gm.stg_run: return
        row = gm.잔고목록.get(key=code)
        if not row: return
        if row['주문가능수량'] == 0: return
        if row['보유수량'] == 0: return
        if row['현재가'] == 0: return
        if row['상태'] == 0: return
        key = f'{code}_매도'
        data={'키': key, '구분': '매도', '상태': '요청', '종목코드': code, '종목명': row['종목명'], '전략매도': False, '비고': 'pri'}
        if gm.주문목록.in_key(key): return
        gm.주문목록.set(key=key, data=data)
        gm.잔고목록.set(key=code, data={'주문가능수량': 0})
        row.update({'rqname': '신규매도', 'account': gm.config.account})
        gm.admin.eval_q.put({'sell': {'row': row}})

class OrderCommander(QThread):
    def __init__(self, prx, order_q):
        super().__init__()
        self.prx = prx
        self.order_q = order_q
        self.ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
        self.running = False

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            self.send_order()
            time.sleep(0.01)

    def send_order(self):
        if not self.com_order_time_check(): return -308 # 5회 제한 초과
        order = self.order_q.get()
        self.com_SendOrder(**order)

    def com_order_time_check(self):
        wait_time = self.ord.check_interval()
        if wait_time > 1666: # 1.666초 이내 주문 제한
            msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {float(wait_time/1000)} 초'
            gm.toast.toast(msg, duration=dc.td.TOAST_TIME)
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
        logging.debug(f'주문 요청 확인: code={code}, name={name}')
        주문유형 = dc.fid.주문유형FID[ordtype]
        kind = msg if msg else 주문유형
        job = {"구분": kind, "전략명칭": 전략명칭, "종목코드": code, "종목명": name, "주문수량": quantity, "주문가격": price}
        gm.admin.send_status_msg('주문내용', job)

        rqname = f'{code}_{rqname}_{datetime.now().strftime("%H%M%S")}'
        key = f'{code}_{주문유형.lstrip("신규")}'
        gm.주문목록.set(key=key, data={'상태': '전송', '요청명': rqname})
        cmd = { 'rqname': rqname, 'screen': screen, 'accno': accno, 'ordtype': ordtype, 'code': code, 'hoga': hoga, 'quantity': quantity, 'price': price, 'ordno': ordno }
        if gm.잔고목록.in_key(code):
            gm.잔고목록.set(key=code, data={'주문가능수량': 0})
        dict_data = {'전략명칭': 전략명칭, '주문구분': 주문유형, '주문상태': '주문', '종목코드': code, '종목명': name, \
                     '주문수량': quantity, '주문가격': price, '매매구분': '지정가' if hoga == '00' else '시장가', '원주문번호': ordno, }
        self.prx.order('dbm', 'table_upsert', db='db', table='trades', dict_data=dict_data)
        self.prx.order('api', 'SendOrder', **cmd)

class OrderManager():
    def __init__(self):
        self.name = 'odr'

    def odr_timeout(self, idx, kind, origin_row, dictFID):
        if gm.주문목록.len() == 0: return
        try:
            code = origin_row['종목코드']
            key = f'{code}_{kind}'
            if not gm.주문목록.in_key(key): return

            order_no = origin_row['주문번호']
            name = origin_row['종목명']
            주문수량 = dictFID['주문수량']
            미체결수량 = dictFID['미체결수량']

            data={'키': f'{key}', '구분': kind, '상태': '취소요청', '종목코드': code, '종목명': name}
            gm.주문목록.set(key=key, data=data)
            self.order('stg', 'order_cancel', kind, order_no, code)

            logging.info(f'{kind}\n주문 타임아웃: {code} {name} 주문번호={order_no} 주문수량={주문수량} 미체결수량={미체결수량}')

        except Exception as e:
            logging.error(f"주문 타임아웃 오류: code={code} name={name} {type(e).__name__} - {e}", exc_info=True)

    def odr_recieve_chegyeol_data(self, dictFID):
        if not gm.config.ready: return
        try:
            dictFID['주문구분'] = dictFID['주문구분'].lstrip('+-')
            code = dictFID['종목코드'].lstrip('A')
            key = f'{code}_{dictFID["주문구분"]}'
            order_no = dictFID['주문번호']
            row = gm.주문목록.get(key=key)
            전략명칭 = gm.실행전략['전략명칭']
            전략정의 = gm.설정전략
            주문상태 = dictFID.get('주문상태', '')
            주문수량 = int(dictFID.get('주문수량', 0) or 0)
            주문가격 = int(dictFID.get('주문가격', 0) or 0)
            미체결수량 = int(dictFID.get('미체결수량', 0) or 0)

            if gm.주문목록.in_key(key): # 정상 주문 처리 상태
                gm.주문목록.set(key=key, data={'상태': 주문상태})
            else: # 외부 처리 또는 취소주문 처리 상태
                pass

            dictFID['종목코드'] = code
            dictFID['종목명'] = dictFID['종목명'].strip()
            dictFID['전략명칭'] = 전략명칭
            dictFID['매수전략'] = 전략정의.get('매수전략', '')
            dictFID['전략정의'] = 전략정의
            dictFID['주문수량'] = 주문수량
            dictFID['주문가격'] = 주문가격
            dictFID['미체결수량'] = 미체결수량
            dictFID['체결시간'] = dictFID.get('주문/체결시간', '')

            self.dbm_trade_upsert(dictFID)

            if '접수' in 주문상태:
                self.odr_redeipt_data(dictFID)
            elif '체결' in 주문상태:
                self.odr_conclution_data(dictFID)
            elif '확인' in 주문상태:
                row = gm.주문목록.get(key=key)
                #if row and 주문수량 != 0 and 미체결수량 == 0: # 주문 취소주문 클리어
                logging.debug(f'주문체결 취소확인: key={key} {code} {dictFID["종목명"]} order_no = {order_no} \n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
                #    gm.주문목록.delete(key=key) 
                gm.주문목록.delete(filter={'키': '취소'})

        except Exception as e:
            logging.error(f"접수체결 오류: {type(e).__name__} - {e}", exc_info=True)

    def odr_redeipt_data(self, dictFID):
        try:
            qty = int(dictFID.get('주문수량', 0) or 0)
            remain_qty = int(dictFID.get('미체결수량', 0) or 0)

            if qty != 0 and remain_qty == 0: # 주문취소 원 주문 클리어(체결 없음) / 처음 접수시 qty = remain_qty
                gm.주문목록.delete(key=f'{dictFID["종목코드"]}_{dictFID["주문구분"]}')
                return
            
            kind = '매수' if dictFID['매도수구분']=='2' else '매도'
            code = dictFID['종목코드']
            name = dictFID['종목명']
            key = f'{code}_{dictFID["주문구분"]}'
            order_no = dictFID['주문번호']
            price = int(dictFID.get('주문가격', 0) or 0)

            row = gm.주문목록.get(key=key)
            if row:
                row.update({'상태': '접수', '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price})
                gm.주문목록.set(key=key, data=row)
                logging.debug(f'{kind}주문 정상 접수: order_no={order_no} \n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
            else: # 취소주문, 외부주문
                origin_no = dictFID['원주문번호'].strip('0')
                if origin_no: # 취소주문
                    origin_key = f'{code}_{dictFID["주문구분"][:2]}'
                    origin_row = gm.주문목록.get(filter={'키': origin_key, '주문번호': origin_no})
                    if origin_row:
                        origin_row[0].update({'상태': '취소접수', '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price})
                        gm.주문목록.set(key=origin_key, data=origin_row[0]) # 취소주문 접수 바로 다음 확인에서 삭제처리
                        return
                    else:
                        pass
                    logging.debug(f'취소주문 접수: origin_no={origin_no} \n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
                else: # 외부주문
                    row = {'키': key, '구분': kind, '상태': '외부접수', '종목코드': code, '종목명': name, '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price}
                    gm.주문목록.set(key=key, data=row)
                    logging.debug(f'외부주문 접수: order_no={order_no} \n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')

            row = gm.주문목록.get(key=key)
            try:
                if row['구분'] in ['매수', '매도']:
                    sec = 0
                    if row['구분'] == '매수':
                        if gm.설정전략['매수취소']: sec = gm.설정전략['매수지연초']
                    elif row['구분'] == '매도':
                        if gm.설정전략['매도취소']: sec = gm.설정전략['매도지연초']

                    if sec > 0:
                        #QTimer.singleShot(int(sec * 1000), lambda kind=kind, origin_row=row, dictFID=dictFID: self.odr_timeout(kind, origin_row, dictFID))
                        threading.Timer(int(sec * 1000), lambda kind=kind, origin_row=row, dictFID=dictFID: self.odr_timeout(kind, origin_row, dictFID)).start()
            except Exception as e:
                logging.debug(f'전략 처리 오류: {row}')
                logging.error(f"전략 처리 오류: {type(e).__name__} - {e}", exc_info=True)

        except Exception as e:
            logging.error(f"접수 오류: {type(e).__name__} - {e}", exc_info=True)

    def odr_conclution_data(self, dictFID):
        try:
            qty = int(dictFID.get('체결량', 0) or 0)
            remain_qty = int(dictFID.get('미체결수량', 0) or 0)

            if qty == 0 and remain_qty == 0: 
                gm.주문목록.delete(key=f'{dictFID["종목코드"]}_{dictFID["주문구분"]}')
                return # 주문취소 클리어

            kind = dictFID.get('주문구분', '')
            code = dictFID['종목코드']
            key = f'{code}_{kind}'
            name = dictFID['종목명']
            price = int(dictFID.get('체결가', 0) or 0)
            amount = price * qty
            order_no = dictFID.get('주문번호', '')

            order_row = gm.주문목록.get(key=key)
            if not order_row:
                logging.error(f"주문목록이 None 입니다. {code} {name} 매도 체결처리 디비 저장 실패 ***")
            전략명칭 = gm.실행전략['전략명칭']
            전략정의 = gm.설정전략
            매매시간 = datetime.now().strftime('%H:%M:%S')
            단위체결량 = int(dictFID.setdefault('단위체결량', 0) or 0)
            단위체결가 = int(dictFID.setdefault('단위체결가', 0) or 0)
        except Exception as e:
            logging.error(f"주문 체결 오류: {kind} {type(e).__name__} - {e}", exc_info=True)

        def buy_conclution():
            try:
                data = {'종목번호': code, '종목명': name, '보유수량': qty, '매입가': price, '매입금액': amount, '주문가능수량': qty, \
                            '매수전략': 전략정의['매수전략'], '전략명칭': 전략정의['전략명칭'], '감시시작율': 전략정의['감시시작율'], '이익보존율': 전략정의['이익보존율'],\
                            '감시': 0, '보존': 0, '매수일자': dc.td.ToDay, '매수시간': 매매시간, '매수번호': order_no, '매수수량': qty, '매수가': price, '매수금액': amount}
                if not gm.잔고목록.in_key(code):
                    gm.holdings[code] = data
                    save_json(dc.fp.holdings_file, gm.holdings)

                    # 매수 제한 기록
                    gm.counter.set_add(code)

                    logging.info(f'잔고목록 추가: {code} {name} 보유수량={qty} 매입가={price} 매입금액={amount} 미체결수량={dictFID.get("미체결수량", 0)}')

                gm.잔고목록.set(key=code, data=data)

            except Exception as e:
                logging.error(f"매수 처리중 오류 발생: {code} {name} ***")

        try:
            msg = {'구분': f'{kind}체결', '전략명칭': 전략명칭, '종목코드': code, '종목명': name,\
                    '주문수량': dictFID.get('주문수량', 0), '주문가격': dictFID.get('주문가격', 0), '주문번호': order_no}
            if kind == '매수':
                buy_conclution()
                msg.update({'매수수량': 단위체결량, '매수가': 단위체결가, '매수금액': 단위체결가 * 단위체결량})
            elif kind == '매도':
                msg.update({'매도수량': 단위체결량, '매도가': 단위체결가, '매도금액': 단위체결가 * 단위체결량})

            #self.send_status_msg('주문내용', msg)
            self.order('admin', 'send_status_msg', '주문내용', msg)
            logging.info(msg)

            if remain_qty == 0:
                gm.주문목록.delete(key=f'{code}_{kind}') # 정상 주문 완료 또는 주문취소 원 주문 클리어(일부체결 있음)

        except Exception as e:
            logging.error(f"주문 체결 오류: {kind} {type(e).__name__} - {e}", exc_info=True)

    def odr_recieve_balance_data(self, dictFID):
        if not gm.config.ready: return
        try:
            현재가 = abs(int(dictFID.get('현재가', 0) or 0))
            보유수량 = int(dictFID.get('보유수량', 0) or 0)
            매입단가 = abs(int(dictFID.get('매입단가', 0) or 0))
            주문가능수량 = int(dictFID.get('주문가능수량', 0) or 0)
            gm.l2손익합산 = int(dictFID.get('당일총매도손익', 0) or 0)
            code = dictFID['종목코드'].lstrip('A')
            dictFID['종목코드'] = code
            if 보유수량 == 0: 
                if not gm.잔고목록.delete(key=code):
                    logging.warning(f'잔고목록 삭제 실패: {code}\n잔고목록=\n{tabulate(gm.잔고목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
                gm.holdings.pop(code, None)
                save_json(dc.fp.holdings_file, gm.holdings)
            else:
                if gm.잔고목록.in_key(code):
                    gm.잔고목록.set(key=code, data={'보유수량': 보유수량, '매입가': 매입단가, '매입금액': 매입단가 * 보유수량, '주문가능수량': 주문가능수량, '현재가': 현재가})
            dictFID['주문상태'] = '잔고'
            self.dbm_trade_upsert(dictFID)
            msg = f"잔고변경 : {code} {dictFID['종목명']} 보유수량:{보유수량}주 매입단가:{매입단가}원 매입금액:{보유수량 * 매입단가}원 주문가능수량:{주문가능수량}주"
            logging.info(msg)
            logging.debug(f'잔고 dictFID:\n{tabulate(pd.DataFrame([dictFID]), headers="keys", showindex=True, numalign="right")}')
        except Exception as e:
            logging.error(f"잔고 변경 오류: {type(e).__name__} - {e}", exc_info=True)

    def dbm_trade_upsert(self, dictFID):
        try:
            dict_data = {key: dictFID[key] for key in dc.ddb.TRD_COLUMN_NAMES if key in dictFID}
            self.order('dbm', 'table_upsert', db='db', table='trades', dict_data=dict_data)

            if dictFID['주문상태'] == '체결':
                kind = dictFID['주문구분']
                code = dictFID['종목코드']
                name = dictFID['종목명']
                qty = abs(int(dictFID['체결량'] or 0))
                price = abs(int(dictFID['체결가'] or 0))
                amount = abs(int(dictFID['체결누계금액'] or 0))
                st_name = dictFID['전략명칭']
                ordno = dictFID['주문번호']
                st_buy = dictFID['매수전략']

                self.order('dbm', 'upsert_conclusion', kind, code, name, qty, price, amount, ordno, st_name, st_buy)
        except Exception as e:
            logging.error(f"dbm_trade_upsert 오류: {type(e).__name__} - {e}", exc_info=True)

class ChartUpdater(QThread):
    def __init__(self, prx, chart_q):
        super().__init__()
        self.name = 'ctu'
        self.prx = prx
        self.chart_q = chart_q
        self.cht_dt = ChartData()
        self.running = False

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            data = self.chart_q.get()
            code = data.get('code')
            job = data.get('dictFID')
            self.cht_dt.update_chart(
                code, 
                abs(int(job['현재가'])) if job['현재가'] else 0,
                abs(int(job['누적거래량'])) if job['누적거래량'] else 0,
                abs(int(job['누적거래대금'])) if job['누적거래대금'] else 0,
                job['체결시간']
            )

class ChartSetter(QThread):
    def __init__(self, prx, todo_q):
        super().__init__()
        self.name = 'cts'
        self.prx = prx
        self.todo_q = todo_q
        self.running = False
        self.cht_dt = ChartData()

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            code = self.todo_q.get()
            self.request_chart_data(code)

    def request_chart_data(self, code):
        logging.debug(f"get_first_chart_data 요청: {code}")
        self.get_first_chart_data(code, cycle='mi', tick=1)
        self.get_first_chart_data(code, cycle='dy')

    def get_first_chart_data(self, code, cycle, tick=1, times=1):
        """차트 데이터 조회"""
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
                output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if cycle == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': "1"}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': "1"}
                output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            dict_list = self._fetch_chart_data(rqname, trcode, input, output, screen, times)
            
            if not dict_list:
                logging.warning(f'{rqname} 데이타 얻기 실패: code:{code}, cycle:{cycle}, tick:{tick}')
                return dict_list
            
            logging.debug(f'{rqname}: code:{code}, cycle:{cycle}, tick:{tick}, count:{len(dict_list)} {dict_list[:1]}')
            
            # 데이터 변환
            dict_list = self._convert_chart_data(dict_list, code, cycle)
            
            if cycle in ['dy', 'mi']:
                self.cht_dt.set_chart_data(code, dict_list, cycle, int(tick))
                self.prx.order('dbm', 'upsert_chart', dict_list, cycle, tick)
            
            return dict_list
        
        except Exception as e:
            logging.error(f'{rqname} 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []

    def _fetch_chart_data(self, rqname, trcode, input, output, screen, times):
        """차트 데이터 fetch"""
        next = '0'
        dict_list = []
        
        while True:
            result = self.prx.answer('api', 'api_request', rqname, trcode, input, output, next=next, screen=screen)
            if result is None:
                break
            
            data, remain = result
            if data is None or len(data) == 0: 
                break
                
            dict_list.extend(data)
            times -= 1
            if not remain or times <= 0: 
                break
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

class EvalStrategy(QThread):
    def __init__(self, prx, eval_q):
        super().__init__()
        self.name = 'evl'
        self.prx = prx
        self.eval_q = eval_q
        self.clear_timer = None
        self.start_time = '09:00' # 매수시간 시작
        self.stop_time = '15:18'  # 매수시간 종료
        self.start_timer = None
        self.end_timer = None
        self.running = False
        self.cht_dt = ChartData()

    def set_dict(self, new_dict: dict) -> None:
        """딕셔너리 업데이트 및 인스턴스 변수 동기화"""
        try:
            for key, value in new_dict.items():
                setattr(self, key, value)
        except Exception as e:
            logging.error(f'딕셔너리 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            self.eval_order()
            time.sleep(0.01)

    def eval_order(self):
        order = self.eval_q.get()
        if 'buy' in order:
            self.order_buy(**order['buy'])
        elif 'sell' in order:
            self.order_sell(**order['sell'])
        elif 'cancel' in order:
            self.order_cancel(**order['cancel'])

    def is_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        """매수 조건 충족 여부를 확인하는 메소드"""
        name = gm.dict종목정보.get(code, next='종목명')

        if self.매수스크립트적용:
            if self.cht_dt.is_code_registered(code):
                try:
                    result = gm.scm.run_script_compiled(self.매수스크립트, kwargs={'code': code, 'name': name, 'qty': 0, 'price': price})
                    if result['error']: logging.error(f'스크립트 실행 에러: {result["error"]}')
                    if self.매수스크립트AND and not result.get('result', False): return False, {}, f"매수스크립트 조건 불충족: {code} {name}"
                    logging.info(f">>> 매수스크립트 조건 충족: {code} {name}")
                except Exception as e:
                    logging.error(f'매수스크립트 검사 오류: {code} {name} - {type(e).__name__} - {e}', exc_info=True)

        if not gm.config.sim_on:
            status_market = self.com_market_status()
            if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

        if gm.counter.get("000000", name) >= self.체결횟수: 
            return False, {}, f"전략별 매수 횟수 제한 {code} {name} 매수횟수={self.체결횟수} 회 초과"

        if gm.counter.get(code, name) >= self.종목제한: 
            return False, {}, f"종목별 매수 횟수 제한 {code} {name} 종목제한{self.종목제한} 회 초과"

        if self.중복매수금지 and gm.잔고목록.in_key(code): return False, {}, f"보유 종목 재매수 금지 ({code} {name})"

        if gm.잔고목록.len() >= self.보유제한:
            return False, {}, f"보유 종목수 제한 {code} {name} \
            보유종목={gm.잔고목록.len()}종목/보유제한={self.보유제한} 종목 초과" # 전략별 보유로 계산

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
                'screen': dc.scr.화면['신규매수'],
                'accno': gm.config.account,
                'ordtype': 1,  # 매수
                'code': code,
                'quantity': 0,
                'price': price,
                'hoga': '03' if self.매수시장가 else '00',
                'ordno': '',
            }

            # 호가구분과 가격 설정
            if self.매수지정가:
                price = hoga(price, self.매수호가)
                send_data['price'] = price

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
            logging.error(f'매수조건 확인 중 오류: {type(e).__name__} - {e}', exc_info=True)
            return False, send_data, "검사오류"

    def order_buy(self, code, rqname, price=0) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_buy(code, rqname, price) # rqname : 전략
        if is_ok:
            logging.info(f'매수결정: {reason}\nsend_data={send_data}')
            gm.admin.order_q.put(send_data)
        else:
            logging.info(f'매수안함: {reason} send_data={send_data}')
            key = f'{code}_매수'
            if gm.주문목록.in_key(key):
                gm.주문목록.delete(key=key)

        return is_ok, send_data, reason

    def is_sell(self, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        try:
            if not gm.config.sim_on:
                status_market = self.com_market_status()
                if status_market not in dc.ms.장운영시간: return False, {}, "장 운영시간이 아님"

            code = row.get('종목번호', '')          # 종목번호 ='999999' 일 때 당일청산 매도
            rqname = row.get('rqname', '신규매도')  # 매도 조건 검사 신호 이름
            종목명 = row.get('종목명', '')          # 종목번호 = '999999' 일 때 '당일청산 매도'
            매입가 = int(row['매입가'])             # 종목번호 = '999999' 일 때 9
            현재가 = int(row['현재가'])             # 종목번호 = '999999' 일 때 9
            보유수량 = int(row['보유수량'])         # 종목번호 = '999999' 일 때 9

            수익률 = float(row.get('수익률(%)', 0))

            if not code:
                logging.warning(f'종목번호가 없습니다. 매도 조건 검사 중단: {rqname} {종목명}')
                return False, {}, "종목번호없음"

            send_data = {
                'rqname': rqname,
                'screen': dc.scr.화면['신규매도'],
                'accno': gm.config.account,
                'ordtype': 2,  # 매도
                'code': code,
                'quantity': row.get('보유수량', 0), #row.get('주문가능수량', row.get('보유수량', 0)),
                'price': 현재가,
                'hoga': '03' if self.매도시장가 else '00',
                'ordno': '',
            }

            # 호가구분과 가격 설정
            if self.매도지정가:
                send_data['price'] = hoga(현재가, self.매도호가)
                send_data['msg'] = '매도지정'

            if self.매도스크립트적용:
                if self.cht_dt.is_code_registered(code):
                    result = gm.scm.run_script_compiled(self.매도스크립트, kwargs={'code': code, 'name': 종목명, 'price': 매입가, 'qty': 보유수량})
                    if result['error']: logging.error(f'스크립트 실행 에러: {result["error"]}')
                    if self.매도스크립트OR and result.get('result', False): 
                        logging.info(f">>> 매도스크립트 조건 충족: {code} {종목명} {매입가} {보유수량}")
                        send_data['msg'] = '전략매도'
                        return True, send_data, f"전략매도: {code} {종목명}"

            if self.매도적용 and sell_condition: # 검색 종목이므로 그냥 매도
                if self.매도스크립트적용 and self.매도스크립트AND and not result.get('result', False): return False, {}, f"매도스크립트 조건 불충족: {code} {종목명}"
                send_data['msg'] = '검색매도'
                return True, send_data,  f"검색매도: {code} {종목명}"

            if gm.config.sim_on and (수익률 > 30 or 수익률 < -30):
                return False, {}, f"시뮬레이션 비정상 수익률: {code} {종목명} 매입가={매입가} 현재가={현재가} 수익률={수익률}"

            if self.로스컷 and self.로스컷율 != 0:
                send_list = []
                매입금액, 평가손익 = gm.잔고목록.sum(columns=['매입금액', '평가손익'])
                수익율 = (평가손익 / 매입금액) * 100 if 매입금액 > 0 else 0

                if self.로스컷율 > 0 and 수익율 <= self.로스컷율 or self.로스컷율 < 0 and 수익율 >= self.로스컷율: 
                    return False, {}, f"로스컷: 수익율={수익율} 로스컷율={self.로스컷율}"
                
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

            if not gm.config.sim_on:
                if self.당일청산 and datetime.now().strftime('%H:%M') >= self.청산시간:
                    send_list = []
                    rows = gm.잔고목록.get()
                    if self.청산시장가:

                        send_list = [{**send_data, 'code': code, 'price': 0, 'quantity': row['보유수량'], 'msg': '청산시장'} for row in rows]
                    else:
                        send_list = [{**send_data, 'code': code, 'price': hoga(현재가, self.청산호가), 'quantity': row['보유수량'], 'hoga': '01', 'msg': '청산지정'} for row in rows]

                    if send_list:
                        return True, send_list, f"당일청산: 청산시간={self.청산시간}"

                    return True, send_data, f"당일청산: 청산시간={self.청산시간}, {code} {종목명}"

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

            if self.감시적용:
                if row.get('감시', 0):  # 감시 시작점 설정
                    최고가 = row.get('최고가', 0)
                    고점대비하락률 = ((현재가 - 최고가) / 최고가) * 100
                    if 고점대비하락률 + self.스탑주문율 <= 0:
                        send_data['msg'] = '스탑주문'
                        return True, send_data, f"스탑주문율: 스탑주문율율={self.스탑주문율} 수익률={수익률}  {code} {종목명}"

            return False, {}, "조건없음"

        except Exception as e:
            logging.error(f'매도조건 확인 중 오류: {type(e).__name__} - {e}', exc_info=True)
            return False, {}, "검사오류"

    def order_sell(self, row: dict, sell_condition=False) -> tuple[bool, dict, str]:
        is_ok, send_data, reason = self.is_sell(row, sell_condition)
        if reason not in ["조건없음", "장 운영시간이 아님"]:
            logging.info(f'매도결정: {reason}\nsend_data={send_data}')
        if is_ok:
            if not self.매도적용:
                gm.admin.send_status_msg('주문내용', {'구분': f'매도편입', '전략명칭': self.전략명칭, '종목코드': row['종목번호'], '종목명': row['종목명']})
            if isinstance(send_data, list):
                logging.debug(f'** 복수 매도 주문목록 **: {send_data}')
                for data in send_data:
                    gm.admin.order_q.put(data)
            else:
                gm.admin.order_q.put(send_data)
        else:
            key = f'{row["종목번호"]}_매도'
            if gm.주문목록.in_key(key):
                gm.주문목록.delete(key=key)
            gm.잔고목록.set(key=row['종목번호'], data={'주문가능수량': row['보유수량']})

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
            logging.debug(f'주문취소: {order_no} {send_data}')
            gm.admin.order_q.put(send_data)
        except Exception as e:
            logging.error(f'주문취소 오류: {type(e).__name__} - {e}', exc_info=True)

    def set_timer(self):
        now = datetime.now()
        current = now.strftime('%H:%M')
        if self.당일청산:
            if self.clear_timer is not None:
                self.clear_timer = None
            row = {'종목번호': '999999', '종목명': '당일청산매도', '현재가': 0, '매수가': 0, '수익률(%)': 0 }
            start_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.청산시간}", '%Y-%m-%d %H:%M')
            delay_secs = max(0, (start_time - now).total_seconds())
            threading.Timer(delay_secs, lambda: self.order_sell(row)).start()

        if not gm.config.sim_on:
            now = datetime.now()
            current = now.strftime('%H:%M')
            if "15:30" > current > self.stop_time:
                msg = f'전략 종료시간 지났습니다. {self.stop_time} {current}'
                return msg
            else:
                end_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.stop_time}", '%Y-%m-%d %H:%M')
                remain_secs = max(0, (end_time - now).total_seconds())
                threading.Timer(remain_secs, lambda: self.stg_fx실행_매매종료(sell_stop=self.매도도같이적용)).start()
            if current < self.start_time:
                start_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.start_time}", '%Y-%m-%d %H:%M')
                delay_secs = max(0, (start_time - now).total_seconds())
                threading.Timer(delay_secs, lambda: gm.toast.toast(f'전략을 시작합니다. {self.start_time} {current}')).start()

    def com_market_status(self):
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

