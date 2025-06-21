from public import gm, dc, Work,load_json, save_json
from classes import TableManager, TimeLimiter, ThreadSafeDict, CounterTicker
from strategy import Strategy
from worker import SimpleManager
from chart import ChartData, ScriptManager, enhance_script_manager
from tabulate import tabulate
from datetime import datetime
from PyQt5.QtCore import QTimer
import threading
import logging
import pandas as pd
import time
import json

class Admin:
    def __init__(self):
        self.name = 'admin'

    def init(self):
        logging.debug(f'{self.name} init')
        self.get_login_info()
        self.set_globals()
        self.set_script()
        self.get_conditions()
        self.get_strategy_info()
        self.set_real_remove_all()
        self.get_holdings()
        self.json_load_define_sets()
        gm.admin_init = True

    # 준비 작업 -------------------------------------------------------------------------------------------
    def set_connected(self, connected):
        gm.connected = connected

    def set_globals(self):
        gm.counter = CounterTicker()
        gm.dict종목정보 = ThreadSafeDict()
        gm.dict주문대기종목 = ThreadSafeDict() # 주문대기종목 = {종목코드: 전략번호}
        gm.scm = ScriptManager()
        try:
            result = enhance_script_manager(gm.scm)
            logging.debug(f'스크립트 확장 결과={result}')
        except Exception as e:
            logging.error(f'스크립트 확장 오류: {type(e).__name__} - {e}', exc_info=True)
        self.order('dbm', 'set_rate', gm.수수료율, gm.세금율)

    def get_login_info(self):
        accounts = self.answer('api', 'GetLoginInfo', 'ACCNO')
        logging.debug(f'GetLoginInfo Accounts: {accounts}')
        gm.list계좌콤보 = accounts
        gm.config.account = accounts[0]

        gm.config.server = self.answer('api', 'GetLoginInfo', 'GetServerGubun')
        gm.수수료율 = dc.const.fee_sim if gm.config.server == '1' else dc.const.fee_real # 모의투자 0.35%, 실전투자 0.15% 매수, 매도 각각
        gm.세금율 = dc.const.tax_rate # 코스피 거래세 0.03 + 농어촌 특별세 0.12%, 코스닥 거래세 0.15 매도시적용
        logging.debug(f"서버:{gm.config.server}, 수수료율:{gm.수수료율}, 세금율:{gm.세금율}, 계좌:{gm.config.account}")

    def get_conditions(self):
        try:
            loaded = self.answer('api', 'GetConditionLoad')
            if loaded: # sucess=1, fail=0
                gm.list전략튜플 = self.answer('api', 'GetConditionNameList')
                logging.debug(f'전략 로드 : {gm.list전략튜플}')
                gm.list전략콤보 = [condition[0] + ' : ' + condition[1] for condition in gm.list전략튜플]
                logging.info(f'전략 로드 : 총 {len(gm.list전략콤보)}개의 전략이 있습니다.')
            else:
                logging.error(f'전략 로드 실패')
        except Exception as e:
            logging.error(f'전략 로드 오류: {type(e).__name__} - {e}', exc_info=True)

    def get_strategy_info(self):
        self.json_load_strategy_sets()

    def set_script(self):
        scripts = gm.scm.scripts.copy()
        dict_data = []
        for k, v in scripts.items():
            dict_data.append({'스크립트명': k, '스크립트': v.get('script', ''), '변수': json.dumps(v.get('vars', {})), '타입': v.get('type', ''), '설명': v.get('desc', '')})
        gm.스크립트.set(data=dict_data)
        gm.list스크립트 = gm.스크립트.get(column='스크립트명')
        # gm.qwork['gui'].put(Work(order='gui_script_show', job={}))

    def set_real_remove_all(self):
        logging.debug('set_real_remove_all')
        self.order('api', 'SetRealRemove', 'ALL', 'ALL')

    def get_holdings(self):
        logging.info('* get_holdings *')
        gm.dict잔고종목감시 = {}
        self.order('api', 'SetRealRemove', dc.scr.화면['실시간감시'], 'ALL')
        self.pri_fx얻기_잔고합산()
        self.pri_fx얻기_잔고목록()
        self.pri_fx등록_종목감시()

    # 공용 함수 -------------------------------------------------------------------------------------------

    def com_SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno, msg=None):
        #if not self.com_request_time_check(kind='order'): return -308 # 5회 제한 초과

        전략명칭 = gm.실행전략['전략명칭']
        매수전략 = gm.설정전략['매수전략']
        name = self.answer('api', 'GetMasterCodeName', code)
        logging.debug(f'주문 요청 확인: code={code}, name={name}')
        주문유형 = dc.fid.주문유형FID[ordtype]
        kind = msg if msg else 주문유형
        job = {"구분": kind, "전략명칭": 전략명칭, "종목코드": code, "종목명": name, "주문수량": quantity, "주문가격": price}
        self.send_status_msg('주문내용', job)

        rqname = f'{code}_{rqname}_{datetime.now().strftime("%H%M%S")}'
        key = f'{code}_{주문유형.lstrip("신규")}'
        gm.주문목록.set(key=key, data={'상태': '전송', '요청명': rqname})
        cmd = { 'rqname': rqname, 'screen': screen, 'accno': accno, 'ordtype': ordtype, 'code': code, 'hoga': hoga, 'quantity': quantity, 'price': price, 'ordno': ordno }
        if gm.잔고목록.in_key(code):
            gm.잔고목록.set(key=code, data={'주문가능수량': 0})
        dict_data = {'전략명칭': 전략명칭, '주문구분': 주문유형, '주문상태': '주문', '종목코드': code, '종목명': name, \
                     '주문수량': quantity, '주문가격': price, '매매구분': '지정가' if hoga == '00' else '시장가', '원주문번호': ordno, }
        self.order('dbm', 'table_upsert', db='db', table='trades', dict_data=dict_data)
        success = self.answer('api', 'SendOrder', **cmd)
        return success # 0=성공, 나머지 실패 -308 : 5회 제한 초과

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

    def send_status_msg(self, order, args):
        if order=='주문내용':
            msg = f"{args['구분']} : {args['종목코드']} {args['종목명']}"
            if '주문수량' in args:
                msg += f" 주문수량:{args['주문수량']}주 / 주문가격:{args.get('주문가격', 0)}원 주문번호:{args.get('주문번호', '')}"
            job = {'msg': msg}
        elif order=='검색내용':
            job = {'msg': args}
        elif order=='상태바':
            job = {'msg': args}

        if gm.config.gui_on:
            gm.qwork['msg'].put(Work(order=order, job=job))

    # json 파일 사용 메소드 -----------------------------------------------------------------------------------------

    def json_load_define_sets(self):
        try:
            result, data = load_json(dc.fp.define_sets_file, dc.const.DEFAULT_DEFINE_SETS)
            gm.실행전략 = data
            if result:
                logging.debug(f'실행전략 JSON 파일을 로드했습니다. {gm.실행전략}')
            return result
        except Exception as e:
            logging.error(f'실행전략 적용 오류: {type(e).__name__} - {e}', exc_info=True)
            return False

    def json_save_define_sets(self):
        result, data = save_json(dc.fp.define_sets_file, gm.실행전략)
        if result:
            logging.debug(f'실행전략 JSON 파일을 저장했습니다. {data}')
        return result

    def json_load_strategy_sets(self):
        try:
            result, data = load_json(dc.fp.strategy_sets_file, [dc.const.DEFAULT_STRATEGY_SETS])
            if result:
                logging.debug(f'전략정의 JSON 파일을 로드했습니다. data count={len(data)}')
            gm.전략정의.set(data=data)
            gm.basic_strategy = gm.전략정의.get(key=dc.const.BASIC_STRATEGY)
            gm.strategy_row = gm.전략정의.get(key=data[0]['전략명칭'])
            return True
        except Exception as e:
            logging.error(f'전략정의 적용 오류: {type(e).__name__} - {e}', exc_info=True)
            return False

    def json_save_strategy_sets(self):
        try:
            result, data = save_json(dc.fp.strategy_sets_file, gm.전략정의.get())
            gm.basic_strategy = gm.전략정의.get(key=dc.const.BASIC_STRATEGY)
            return result
        except Exception as e:
            logging.error(f'전략정의 쓰기 오류: {type(e).__name__} - {e}', exc_info=True)
            return False

    # api 처리 메소드 -----------------------------------------------------------------------------------------------
    def on_fx실시간_장운영감시(self, code, rtype, dictFID): # 장 운영 상황 감시
        fid215 = dictFID['장운영구분']
        fid20 = dictFID['체결시간']
        fid214 = dictFID['장시작예상잔여시간']
        분 = f' {int(fid214[2:4])} 분' if int(fid214[2:4]) else ''
        초 = f' {int(fid214[4:])} 초' if int(fid214[4:]) else ''
        msg=''
        if fid215 == '0': msg = f'장 시작{분}{초} 전'
        if fid215 == '0': msg = f'장 시작{분}{초} 전'
        elif fid215 == '2': msg = f'장 마감{분}{초} 전'
        elif fid215 == '3': msg = f'장이 시작 되었습니다.'
        elif fid215 == '4': msg = f'장이 마감 되었습니다.'
        if msg:
            self.send_status_msg('상태바', msg)
            logging.debug(f'{rtype} {code} : {fid215}, {fid20}, {fid214} {msg}')

    def on_fx수신_주문결과TR(self, code, name, order_no, screen, rqname):
        if not gm.config.ready: return
        if gm.주문목록.in_column('요청명', rqname):
            if not order_no:
                logging.debug(f'주문 실패로 주문목록 삭제 : {rqname}')
                gm.주문목록.delete(filter={'요청명': rqname})

    def on_fx실시간_주식체결(self, code, rtype, dictFID): # 실시간 시세 감시, 시장 체결데이타 분석 재료, 종목의 누적 거래향
        if not gm.config.ready: return
        #if not gm.config.sim_on: logging.debug(f'실시간 주식체결 처리: API로 부터 받음')

        현재가 = abs(int(dictFID['현재가']))
        updated = gm.dict종목정보.update_if_exists(code, '현재가', 현재가)
        if updated:
            data = gm.dict주문대기종목.get(code, None)
            if data:
                gm.주문목록.set(key=f'{code}_{data["kind"]}', data={'상태': '요청'})
                if data['kind'] == '매수':
                    self.order('stg', 'order_buy', code, '신규매수', 현재가)
                elif data['kind'] == '매도':
                    row = gm.잔고목록.get(key=code)
                    row['현재가'] = 현재가
                    self.order('stg', 'order_sell', row, True) # 조건검색에서 온 것이기 때문에 True
                gm.dict주문대기종목.remove(code)

            job = {'code': code, 'dictFID': dictFID}
            self.order('dmy', 'register_chart_data', job)

        try:
            if gm.잔고목록.in_key(code):
                row = gm.잔고목록.get(key=code)
                if not row: return
                self.pri_fx처리_잔고데이터(code, row, dictFID)
                self.pri_fx검사_매도요건(code)
        except Exception as e:
            logging.error(f'실시간 주식체결 오류: {type(e).__name__} - {e}', exc_info=True)

    # 조회 및 처리  -------------------------------------------------------------------------------------------
    
    def pri_fx얻기_잔고합산(self):
        try:
            gm.잔고합산.delete()
            dict_list = []
            rqname = '잔고합산'
            trcode = 'opw00018'
            input = {'계좌번호':gm.config.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '2'}
            output = gm.tbl.hd잔고합산['컬럼']
            next = '0'
            screen = dc.scr.화면[rqname]
            data, remain = self.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
            dict_list.extend(data)
            if dict_list:
                for i, item in enumerate(dict_list):
                    item.update({'순번':i})
                gm.잔고합산.set(data=dict_list)
                logging.info(f"잔고합산 얻기 완료: data=\n{gm.잔고합산.get(type='df')}")
                gm.l2잔고합산_copy = gm.잔고합산.get(key=0) # dict

            logging.info(f"잔고합산 얻기 완료: data count={gm.잔고합산.len()}")

        except Exception as e:
            logging.error(f'잔고합산 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

    def pri_fx얻기_잔고목록(self):
        try:
            gm.잔고목록.delete()
            dict_list = []
            rqname = '잔고목록'
            trcode = 'opw00018'
            input = {'계좌번호':gm.config.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '2'}
            output = gm.tbl.hd잔고목록['컬럼']
            next = '0'
            screen = dc.scr.화면[rqname]
            while True:
                data, remain = self.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
                logging.debug(f'잔고목록 얻기: data count={len(data)}, remain={remain}')
                dict_list.extend(data)
                if not remain: break
                next = '2'

            def get_preview_data(dict_list):
                # 홀딩스 데이터 로드 (미리 로드)
                success, gm.holdings = load_json(dc.fp.holdings_file, {})
                if not success:
                    logging.error(f'홀딩스 데이터 로드 실패: {dc.fp.holdings_file}')

                dict_list = [{
                    **item,
                    '종목번호': item['종목번호'].lstrip('A'),
                    '상태': 0,
                    '감시': 0,
                    '보존': 0,
                    '매수전략': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수전략', item.get('매수전략', dc.const.NON_STRATEGY)),
                    '전략명칭': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('전략명칭', item.get('전략명칭', dc.const.BASIC_STRATEGY)),
                    '감시시작율': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('감시시작율', item.get('감시시작율', gm.basic_strategy.get('감시시작율', 0.0))),
                    '이익보존율': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('이익보존율', item.get('이익보존율', gm.basic_strategy.get('이익보존율', 0.0))),
                    '감시': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('감시', item.get('감시', 0)),
                    '보존': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('보존', item.get('보존', 0)),
                    '매수일자': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수일자', item.get('매수일자', '')),
                    '매수시간': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수시간', item.get('매수시간', '')),
                    '매수번호': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수번호', item.get('매수번호', '')),
                    '매수수량': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수수량', item.get('보유수량', 0)),
                    '매수가': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수가', item.get('매입가', 0)),
                    '매수금액': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수금액', item.get('매입금액', 0)),
                    '주문가능수량': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수수량', item.get('보유수량', 0)),
                } for item in dict_list]
                return dict_list

            def save_holdings(dict_list):
                dict_list = gm.잔고목록.get()
                gm.holdings = {item['종목번호']:
                            {'종목명': item['종목명'], '매수전략': item['매수전략'], '전략명칭': item['전략명칭'],\
                            '감시시작율': item['감시시작율'], '이익보존율': item['이익보존율'], '감시': item['감시'], '보존': item['보존'],\
                            '매수일자': item['매수일자'], '매수시간': item['매수시간'],\
                            '매수번호': item['매수번호'], '매수수량': item['매수수량'], '매수가': item['매수가'], '매수금액': item['매수금액']} \
                    for item in dict_list}
                save_json(dc.fp.holdings_file, gm.holdings)

            def save_counter(dict_list):
                data = {}
                for item in dict_list:
                    전일가 = self.answer('api', 'GetMasterLastPrice', item['종목번호'])
                    종목정보 = {'종목명': item['종목명'], '전일가': 전일가, "현재가": 0}
                    # 락 획득시간 최소화
                    gm.dict종목정보.set(item['종목번호'], 종목정보)
                    전략정의 = gm.전략정의.get(key=item['전략명칭'])
                    if not 전략정의:
                        # strategy_set.json 에 전략명칭이 없으면 기본전략 적용 (인위적으로 삭제시 발생)
                        logging.warning(f'전략정의 없음: 전략명칭={item["전략명칭"]} 기본전략 적용')
                        item['매수전략'] = ""
                        item['전략명칭'] = "기본전략"
                        gm.잔고목록.set(key=item['종목번호'], data=item)
                        전략정의 = gm.전략정의.get(key="기본전략")

                    data[item['종목번호']] = item['종목명']

                    self.order('ctu', 'register_code', item['종목번호'])
                    gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{item["종목번호"]} {item["종목명"]}'}))
                gm.counter.set_batch(data)

            #logging.debug(f'dict_list ={dict_list}')
            if dict_list:
                dict_list = get_preview_data(dict_list)
                gm.잔고목록.set(data=dict_list)
                save_holdings(dict_list)
                save_counter(dict_list)
            self.order('ctu', 'register_code', '005930')

            logging.info(f"잔고목록 얻기 완료: data count={gm.잔고목록.len()}")

        except Exception as e:
            logging.error(f'pri_fx얻기_잔고목록 오류: {e}', exc_info=True)

    def pri_fx처리_잔고데이터(self, code, row, dictFID):
        try:
            # 잔고목록 업데이트
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
        self.order('stg', 'order_sell', row)

    def pri_fx등록_종목감시(self):
        try:
            gm.set종목감시 = set(gm.잔고목록.get(column='종목번호') or [])
            gm.set종목감시.add('005930')
            for code in gm.set종목감시:
                종목명 = self.answer('api', 'GetMasterCodeName', code)
                전일가 = self.answer('api', 'GetMasterLastPrice', code)
                value = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                # 락 획득시간 최소화
                gm.dict종목정보.set(code, value=value)

            logging.debug(f'실시간 시세 요청: codes={gm.set종목감시}')
            codes = ";".join(gm.set종목감시)
            self.order('api', 'SetRealReg', dc.scr.화면['실시간감시'], codes, "10", 0)
        except Exception as e:
            logging.error(f'실시간 시세 요청 오류: {type(e).__name__} - {e}', exc_info=True)

    def dbm_query_result(self, result, error=None):
        if error is not None:
            logging.debug(f'디비 요청 결과: result={result} error={error}')

class OrderManager:
    def __init__(self):
        pass

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
            #logging.debug(f'체결잔고 : 주문상태={주문상태} order_no={order_no} ' +
            #                f'\n주문목록=\n{tabulate(gm.주문목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')

            self.dbm_trade_upsert(dictFID)
            #self.order('admin', 'dbm_trade_upsert', dictFID)

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
            #self.order('admin', 'dbm_trade_upsert', dictFID)
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



