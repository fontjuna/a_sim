from public import gm, dc, Work, hoga, load_json, save_json
from classes import ThreadSafeDict, CounterTicker, ThreadSafeQueue, ThreadSafeSet
from threads import OrderCommander, EvalStrategy, ChartSetter, ChartUpdater, PriceUpdater
from chart import ScriptManager
from tables import tbl
from dbm_server import db_columns
from tabulate import tabulate
from datetime import datetime
from PyQt5.QtCore import QThread, QTimer, QObject
import logging
import json
import time
import threading

class Admin:
    def __init__(self):
        self.name = 'admin'
        self.stg_ready = False
        self.stg_buy_timeout = False
        self.cancel_timer = None
        self.start_timer = None
        self.end_timer = None
        self.start_time = '09:00' # 매수시간 시작
        self.stop_time = '15:18'  # 매수시간 종료
        self.wait_running = False

    def init(self):
        logging.info(f'{self.name} init')
        # 3. 로그인 정보 조회 (계좌, 수수료율, 세금율 설정)
        self.get_login_info()
        # 4. 글로벌 변수 설정 (수수료율/세금율 사용)
        self.set_globals()
        self.set_script()
        self.get_conditions()
        self.get_strategy_info()
        self.set_real_remove_all()
        self.get_holdings()
        self.json_load_define_sets()
        # 쓰레드 준비
        self.set_threads()
        self.start_threads()
        gm.admin_init = True

        # GUI 업데이트 (admin.init 후 데이터 로드 완료되었으므로)
        if gm.gui_on:
            gm.qwork['gui'].put(Work(order='gui_fx채움_조건콤보', job={}))
            gm.qwork['gui'].put(Work(order='gui_fx채움_스크립트콤보', job={}))
            gm.qwork['gui'].put(Work(order='gui_fx채움_전략정의', job={}))
            gm.qwork['gui'].put(Work(order='gui_fx전시_전략정의', job={}))
            logging.debug('GUI 업데이트 요청 완료')

    # 준비 작업 -------------------------------------------------------------------------------------------
    def get_login_info(self):
        accounts = gm.prx.answer('api', 'GetLoginInfo', 'ACCNO')
        logging.debug(f'GetLoginInfo Accounts: {accounts}')
        gm.list계좌콤보 = accounts
        gm.account = accounts[0]
        gm.server = gm.prx.answer('api', 'GetLoginInfo', 'GetServerGubun')
        gm.수수료율 = dc.const.fee_sim if gm.server == '1' else dc.const.fee_real # 모의투자 0.35%, 실전투자 0.015% 매수, 매도 각각
        gm.세금율 = dc.const.tax_rate # 코스피 거래세 0.03 + 농어촌 특별세 0.12%, 코스닥 거래세 0.15 매도시적용
        logging.debug(f"서버: {'모의서버' if gm.server == '1' else '실서버'}, 수수료율: {gm.수수료율}, 세금율: {gm.세금율}, 계좌: {gm.account}")

    def set_globals(self):
        gm.price_q = ThreadSafeQueue('price_q')
        gm.eval_q = ThreadSafeQueue('eval_q')
        gm.order_q = ThreadSafeQueue('order_q')
        gm.setter_q = ThreadSafeQueue('setter_q')
        gm.chart_q = ThreadSafeQueue('chart_q')
        gm.counter = CounterTicker()
        gm.dict종목정보 = ThreadSafeDict()
        gm.scm = ScriptManager()
        gm.prx.order('dbm', 'set_rate', gm.수수료율, gm.세금율)

    def get_conditions(self):
        try:
            loaded = gm.prx.answer('api', 'GetConditionLoad')
            if loaded: # sucess=1, fail=0
                gm.list전략튜플 = gm.prx.answer('api', 'GetConditionNameList')
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
            dict_data.append({'스크립트명': k, '타입': v.get('type', ''), '스크립트': v.get('script', ''), '설명': v.get('desc', '')})
        gm.스크립트.set(data=dict_data)
        gm.list스크립트 = gm.스크립트.get(column='스크립트명')

    def set_real_remove_all(self):
        logging.debug('set_real_remove_all')
        gm.prx.order('api', 'SetRealRemove', 'ALL', 'ALL')

    def get_holdings(self):
        logging.info('* get_holdings *')
        gm.set종목감시 = set()
        gm.prx.order('api', 'SetRealRemove', dc.scr.화면['실시간감시'], 'ALL')
        self.pri_fx얻기_잔고합산()
        self.pri_fx얻기_잔고목록()
        self.pri_fx등록_종목감시()

    # 쓰레드 준비 -------------------------------------------------------------------------------------------
    def start_threads(self):
        gm.prx.receive_signal.connect(self.run_receive_signals)
        gm.rcv.receive_signal.connect(self.run_receive_real_signals)
        gm.cts.start()
        gm.ctu.start()
        gm.odc.start()
        gm.pri.start()

    def stop_threads(self):
        gm.cts.stop()
        gm.cts.quit()
        gm.cts.wait(2000)
        gm.ctu.stop()
        gm.ctu.quit()
        gm.ctu.wait(2000)
        gm.odc.stop()
        gm.odc.quit()
        gm.odc.wait(2000)
        gm.pri.stop()
        gm.pri.wait(2000)

    def set_threads(self):
        gm.cts = ChartSetter(gm.prx, gm.setter_q)
        gm.ctu = ChartUpdater(gm.prx, gm.chart_q)
        gm.odc = OrderCommander(gm.prx, gm.order_q)
        gm.pri = PriceUpdater(gm.prx, gm.price_q)

    def run_receive_signals(self, data):
        if hasattr(self, data.method):
            getattr(self, data.method)(*data.args, **data.kwargs)
        else:
            logging.error(f'시그널 처리 오류: method={data.method}')

    def run_receive_real_signals(self, data):
        if hasattr(self, data.method):
            getattr(self, data.method)(*data.args, **data.kwargs)
        else:
            logging.error(f'시그널 처리 오류: method={data.method}')

    # 공용 함수 -------------------------------------------------------------------------------------------
    def send_status_msg(self, order, args):
        if order=='주문내용':
            msg = f"{args['구분']} : {args['종목코드']} {args['종목명']}"
            if '주문수량' in args:
                msg += f" 주문수량:{args['주문수량']}주 - 주문가:{args.get('주문가격', 0)}원 / 주문번호:{args.get('주문번호', '')}"
            if '메시지' in args:
                msg += f" {args['메시지']}"
            job = {'msg': msg}
        elif order=='체결내용':
            msg = f"{args['구분']} : {args['종목코드']} {args['종목명']}"
            msg += f" 체결수량:{args['체결수량']}주 - 체결가:{args.get('체결가', 0)}원 / 주문번호:{args.get('주문번호', '')}"
            job = {'msg': msg}
        elif order=='검색내용':
            job = {'msg': args}
        elif order=='상태바':
            job = {'msg': args}

        if gm.gui_on:
            gm.qwork['msg'].put(Work(order=order, job=job))

    def toast(self, msg, duration=dc.TOAST_TIME):
        if gm.gui_on: gm.toast.toast(msg, duration)

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
    def on_receive_market_status(self, code, rtype, dictFID): # 장 운영 상황 감시
        fid215 = dictFID['장운영구분']
        fid20 = dictFID['체결시간']
        fid214 = dictFID['장시작예상잔여시간']
        분 = f' {int(fid214[2:4])} 분' if int(fid214[2:4]) else ''
        초 = f' {int(fid214[4:])} 초' if int(fid214[4:]) else ''
        msg=''
        if fid215 == '0': msg = f'장 시작{분}{초} 전'
        if fid215 == '0': msg = f'장 시작{분}{초} 전'
        elif fid215 == '2': msg = f'장 마감{분}{초} 전'
        elif fid215 == '3': 
            msg = f'장이 시작 되었습니다.'
            if gm.gui_on: gm.qwork['gui'].put(Work('gui_write_replay', {'msg': '*' * 150}))
        elif fid215 == '4':
            msg = f'장이 마감 되었습니다.'
            # 장 마감 후 MariaDB 자동 저장 (sim_no == 0일 때만)
            if gm.sim_no == 0:
                from datetime import datetime
                today = datetime.now().strftime('%Y-%m-%d')
                logging.info(f"[Admin] 장 마감 - MariaDB 자동 저장 시작: {today}")
                try:
                    result = gm.prx.answer('dbm', 'save_to_mariadb', date=today)
                    if result:
                        logging.info(f"[Admin] MariaDB 자동 저장 성공: {today}")
                    else:
                        logging.warning(f"[Admin] MariaDB 자동 저장 실패: {today}")
                except Exception as e:
                    logging.error(f"[Admin] MariaDB 자동 저장 오류: {e}", exc_info=True)

        if msg:
            self.toast(msg, 3000)
            self.send_status_msg('상태바', msg)
            logging.debug(f'{rtype} {code} : {fid215}, {fid20}, {fid214} {msg}')

    def on_receive_tr_data(self, code, name, order_no, screen, rqname, trcode):
        if not gm.ready: return
        if gm.주문진행목록.in_column('요청명', rqname):
            if not order_no:
                logging.debug(f'주문 실패로 주문진행목록 삭제 : {code} {name} {rqname} {screen} {trcode}')
                gm.주문진행목록.delete(filter={'요청명': rqname})

    def on_receive_real_condition(self, code, type, cond_name, cond_index): # 조건검색 결과 수신
        if not gm.ready or not self.stg_ready:
            logging.debug(f"조건검색 수신 무시: ready={gm.ready}, stg_ready={self.stg_ready}")
            return
        if gm.sim_no == 0 and time.time() < 90000: return
        try:
            if gm.sim_no == 0: gm.prx.order('dbm', 'insert_real_condition', code, type, cond_name, cond_index, 2)

            condition = f'{int(cond_index):03d} : {cond_name.strip()}'
            if condition == gm.매수문자열:
                kind = '매수'
            elif condition == gm.매도문자열:
                kind = '매도'
            else:
                logging.warning(f"조건식 불일치: type={type}, condition='{condition}', 매수='{gm.매수문자열}', 매도='{gm.매도문자열}'")
                return

            job = (kind, code, type, cond_name, cond_index,)
            if type == 'I':
                self.stg_fx편입_실시간조건감시(*job)
            elif type == 'D':
                self.stg_fx이탈_실시간조건감시(*job)
        except Exception as e:
            logging.error(f"쓰레드 찾기오류 {code} {type} {cond_name} {cond_index}: {type(e).__name__} - {e}", exc_info=True)

    def on_receive_real_data(self, code, rtype, dictFID):
        if not gm.ready: return
        try:
            # sim2 진행 시간 표시
            if gm.sim_no == 2 and gm.gui_on:
                체결시간 = str(dictFID.get('체결시간', '')).strip()
                if len(체결시간) >= 6:
                    시간표시 = f"{체결시간[:2]}:{체결시간[2:4]}:{체결시간[4:6]}"
                    gm.qwork['gui'].put(Work(order='update_sim2_progress', job={'text': 시간표시}))

            현재가 = abs(int(dictFID.get('현재가')))
            updated = gm.dict종목정보.update_if_exists(code, '현재가', 현재가)

            if updated:
                주문 = gm.주문진행목록.get(filter={'종목코드': code, '상태': '대기'})
                if 주문:
                    gm.주문진행목록.set(key=(code, 주문[0]["구분"]), data={'상태': '요청'})
                    logging.debug(f'종목 가격 업데이트와 주문 처리: {code} {주문[0]["종목명"]} {현재가}')
                    if 주문[0]['구분'] == '매수':
                        gm.eval_q.put((code, 'buy', {'rqname': '신규매수', 'price': 현재가}))
                    elif 주문[0]['구분'] == '매도':
                        row = gm.잔고목록.get(key=code)
                        row['현재가'] = 현재가
                        gm.eval_q.put((code, 'sell', {'row': row, 'sell_condition': True}))

                gm.chart_q.put({code: dictFID}) # ChartUpdater
                if gm.sim_no == 0: gm.prx.order('dbm', 'upsert_real_data', code, dictFID, 2)
            
            if gm.잔고목록.in_key(code) and self.stg_ready:
                gm.잔고목록.set(key=code, data={'현재가': 현재가, '등락율': float(dictFID.get('등락율', 0)), '누적거래량': int(dictFID.get('누적거래량', 0))})
                gm.price_q.put(code) # PriceUpdater

        except Exception as e:
            logging.error(f'실시간 주식체결 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    # 조회 및 처리  -------------------------------------------------------------------------------------------
    def pri_fx얻기_잔고합산(self):
        try:
            gm.잔고합산.delete()
            dict_list = []
            rqname = '잔고합산'
            trcode = 'opw00018'
            input = {'계좌번호':gm.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '2'}
            output = tbl.hd잔고합산['컬럼']
            next = '0'
            screen = dc.scr.화면[rqname]
            data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
            dict_list.extend(data)
            if dict_list:
                for i, item in enumerate(dict_list):
                    item.update({'순번':i})
                gm.잔고합산.set(data=dict_list)
                logging.info(f"잔고합산 얻기 완료: data=\n{tabulate(gm.잔고합산.get(type='df'), headers='keys', numalign='right')}")
                gm.l2잔고합산_copy = gm.잔고합산.get(key=0) # dict
            else:
                logging.info(f"잔고합산 얻기 실패")

        except Exception as e:
            logging.error(f'잔고합산 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

    def pri_fx얻기_잔고목록(self):
        try:
            전일가 = gm.prx.answer('api', 'GetMasterLastPrice', '005930')
            종목정보 = {'종목명': '삼성전자', '전일가': 전일가, "현재가": 0}
            gm.dict종목정보.set('005930', 종목정보)
            logging.info(f'삼성전자(005930) 차트 데이터 요청 큐 추가')
            gm.setter_q.put('005930')

            def get_preview_data(dict_list):
                # 홀딩스 데이터 로드 (미리 로드)
                success, gm.holdings = load_json(dc.fp.holdings_file, {})
                if not success:
                    logging.error(f'홀딩스 데이터 로드 실패: {dc.fp.holdings_file}')

                dict_list = [{
                    **item,
                    '종목번호': item['종목번호'].lstrip('A'),
                    '감시시작율': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('감시시작율', item.get('감시시작율', gm.basic_strategy.get('감시시작율', 0.0))),
                    '이익보존율': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('이익보존율', item.get('이익보존율', gm.basic_strategy.get('이익보존율', 0.0))),
                    '감시': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('감시', item.get('감시', 0)),
                    '보존': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('보존', item.get('보존', 0)),
                    '전략명칭': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('전략명칭', item.get('전략명칭', dc.const.BASIC_STRATEGY)),
                    '매수전략': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수전략', item.get('매수전략', dc.const.NON_STRATEGY)),
                    '매수일자': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수일자', item.get('매수일자', '')),
                    '매수시간': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수시간', item.get('매수시간', '')),
                    '매수번호': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수번호', item.get('매수번호', '')),
                    '매수수량': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수수량', item.get('보유수량', 0)),
                    '매수가': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수가', item.get('매입가', 0)),
                    '매수금액': gm.holdings.get(item['종목번호'].lstrip('A'), {}).get('매수금액', item.get('매입금액', 0)),
                    '주문가능수량': item.get('보유수량', 0),
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
                    전일가 = gm.prx.answer('api', 'GetMasterLastPrice', item['종목번호'])
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

                    gm.setter_q.put(item['종목번호'])
                    gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{item["종목번호"]} {item["종목명"]}'}))
                gm.counter.register_tickers(data)
            
            def create_conclusion_records(dict_list):
                """잔고목록 기반 conclusion 매수 레코드 동기화"""
                # 미매도 레코드 전체 삭제
                sql_del = f"DELETE FROM {db_columns.CONC_TABLE_NAME} WHERE sim_no = ? AND 매수수량 > 매도수량"
                gm.prx.order('dbm', 'execute_query', sql=sql_del, db='db', params=(gm.sim_no,))
                
                # 잔고목록 기반으로 레코드 생성
                for item in dict_list:
                    conc_record = {
                        '종목번호': item['종목번호'],
                        '종목명': item['종목명'],
                        '매수일자': item.get('매수일자', dc.ToDay),
                        '매수시간': item.get('매수시간', '000000'),
                        '매수번호': item.get('매수번호', ''),
                        '매수수량': item.get('매수수량', item.get('보유수량', 0)),
                        '매수가': item.get('매수가', item.get('매입가', 0)),
                        '매수금액': item.get('매수금액', item.get('매입금액', 0)),
                        '매도수량': 0,
                        '매수전략': item.get('매수전략', ''),
                        '전략명칭': item.get('전략명칭', dc.const.BASIC_STRATEGY),
                        'sim_no': gm.sim_no
                    }
                    gm.prx.order('dbm', 'table_upsert', 'db', db_columns.CONC_TABLE_NAME, conc_record, db_columns.CONC_KEYS)
                
                logging.info(f"잔고목록 기반 매수 레코드 동기화 완료: {len(dict_list)}건")

            gm.잔고목록.delete()
            dict_list = []
            rqname = '잔고목록'
            trcode = 'opw00018'
            input = {'계좌번호':gm.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '2'}
            output = tbl.hd잔고목록['컬럼']
            next = '0'
            screen = dc.scr.화면[rqname]
            while True:
                data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
                #logging.debug(f'잔고목록 얻기: data count={len(data)}, remain={remain}')
                dict_list.extend(data)
                if not remain: break
                next = '2'
                
            #logging.debug(f'dict_list ={dict_list}')
            if dict_list:
                dict_list = get_preview_data(dict_list)
                gm.잔고목록.set(data=dict_list)
                save_holdings(dict_list)
                save_counter(dict_list)
                create_conclusion_records(dict_list)

            logging.info(f"잔고목록 얻기 완료: data count={gm.잔고목록.len()}")
            logging.debug(f'잔고목록: \n{tabulate(gm.잔고목록.get(type="df"), headers="keys", numalign="right")}')

        except Exception as e:
            logging.error(f'pri_fx얻기_잔고목록 오류: {e}', exc_info=True)

    def pri_fx등록_종목감시(self):
        try:
            gm.set종목감시 = set(gm.잔고목록.get(column='종목번호') or [])
            gm.set종목감시.add('005930')
            for code in gm.set종목감시:
                종목명 = gm.prx.answer('api', 'GetMasterCodeName', code)
                전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                value = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                # 락 획득시간 최소화
                gm.dict종목정보.set(code, value)

            logging.debug(f'실시간 시세 요청: codes={gm.set종목감시}')
            codes = ";".join(gm.set종목감시)
            gm.prx.order('api', 'SetRealReg', dc.scr.화면['실시간감시'], codes, "10", 0)
        except Exception as e:
            logging.error(f'실시간 시세 요청 오류: {type(e).__name__} - {e}', exc_info=True)

    # 매매전략 처리  -------------------------------------------------------------------------------------------

    # 모드별 실행 로직 ---------------------------------------------------------------
    def gui_update_sim_daily_table(self, data):
        """sim2 daily_sim 테이블 데이터를 GUI에 전달"""
        if gm.gui_on:
            gm.qwork['gui'].put(Work(order='update_sim_daily_table', job={'data': data}))

    def update_sim2_progress_text(self, text):
        """sim2 진행 메시지 표시"""
        if gm.gui_on:
            gm.qwork['gui'].put(Work(order='update_sim2_progress', job={'text': text}))

    def on_tickers_ready(self, sim_no, success=True, message='', ticker=None):
        """콜백 완료 신호 받음"""
        logging.info(f'[Mode] sim_no={sim_no} → 콜백 완료 신호 받음')
        if success:
            # sim2 모드일 때 ticker 정보를 gm.dict종목정보에 등록
            if sim_no == 2 and ticker:
                logging.info(f'[Mode] sim2 ticker 등록 시작: {len(ticker)}개 종목')
                for code, info in ticker.items():
                    종목명 = info.get('종목명', '')
                    전일가 = info.get('전일가', 0)
                    value = {'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                    gm.dict종목정보.set(code, value)
                logging.info(f'[Mode] sim2 ticker 등록 완료: {len(ticker)}개 종목')

            logging.info(f'[Mode] sim_no={sim_no} → 전략 시작')
            self.stg_start()

            run_strategy = any([gm.매수문자열, gm.매도문자열])
            if not run_strategy:
                self.toast('실행된 전략매매가 없습니다. 1분 이내에 재실행 됐거나, 실행될 전략이 없습니다.', duration=2000)
            else:
                self.toast('전략매매를 실행했습니다.', duration=2000)
                gm.qwork['gui'].put(Work('set_strategy_toggle', {'run': run_strategy}))
        else:
            logging.error(f'[Mode] sim_no={sim_no} → 콜백 실패 신호 받음: {message}')

    def mode_start(self, new_sim_no=None, is_startup=False):
        """모드별 진입점 (프로그램 시작 / 버튼 클릭)

        Args:
            new_sim_no (int, optional): 변경할 sim_no. None이면 현재 sim_no 유지
            is_startup (bool): True=프로그램 시작, False=버튼 클릭
        """
        try:
            gm.ready = True
            
            # 1. 모드 변경이 있으면 재초기화
            if new_sim_no is not None and new_sim_no != gm.sim_no:
                logging.info(f'[Mode Start] sim_no 변경: {gm.sim_no} → {new_sim_no}')
                gm.sim_no = new_sim_no
                gm.sim_on = gm.sim_no > 0
                gm.prx.order('api', 'api_init', sim_no=gm.sim_no, log_level=gm.log_level)
                gm.prx.order('dbm', 'dbm_init', gm.sim_no, gm.log_level)
                time.sleep(1)
                self.set_real_remove_all()
                self.get_holdings()
                gm.admin_init = True

            # if gm.sim_no == 0: 
            #     self.on_tickers_ready(0)
            #     return
            
            # 2. 실행 여부 판단
            should_run = (gm.sim_no == 0) if is_startup else (gm.sim_no in [0, 1, 2])

            if not should_run:
                logging.info(f'[Mode] sim_no={gm.sim_no} → 대기')
                return

            # 3. set_tickers (모든 sim_no가 콜백으로 완료 신호 받음)
            # sim2: gm.set조건감시 초기화 (SetRealReg가 호출되도록)
            if gm.sim_no == 2:
                gm.set조건감시 = set()
                logging.debug('[Mode Start] sim2: gm.set조건감시 초기화 완료')

            if gm.sim_no == 2 and gm.gui_on:
                speed, date = gm.gui.gui_get_sim3_sets()
                gm.prx.order('api', 'set_tickers', speed=speed, dt=date)
            else:
                gm.prx.order('api', 'set_tickers')

            # 콜백 대기 (stg_start()는 on_tickers_ready()에서 호출)
            logging.info(f'[Mode] sim_no={gm.sim_no} → set_tickers 완료 대기... (완료 시 전략 자동 시작)')

        except Exception as e:
            logging.error(f'모드 시작 오류: {type(e).__name__} - {e}', exc_info=True)

    def mode_sim3_load(self):
        """Sim3 전용: 메모리 로드 후 전략 시작"""
        try:
            logging.info('[Mode Sim3 Load] 데이터 로드 + 전략 시작')
            self.stg_start()
        except Exception as e:
            logging.error(f'Sim3 로드 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_start(self):
        try:
            gm.매수문자열 = "" 
            gm.매도문자열 = "" 
            gm.evl = EvalStrategy(gm.prx, gm.eval_q)
            self.json_load_strategy_sets() # 전략 정의 리스트 로드
            _, gm.실행전략 = load_json(dc.fp.define_sets_file, dc.const.DEFAULT_DEFINE_SETS) # 실행 전략 로드
            gm.설정전략 = gm.전략정의.get(key=gm.실행전략['전략명칭']) # 실행 전략 설정 정보
            for key, value in gm.설정전략.items(): setattr(self, key, value)
            logging.debug(f'전략명칭={gm.실행전략["전략명칭"]}')
            self.stg_fx실행_전략매매()
        except Exception as e:  
            logging.error(f'전략 매매 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_stop(self, timeout=None):
        try:
            if not (gm.매수문자열 or  gm.매도문자열): return
            gm.매수문자열 = ""
            gm.매도문자열 = ""
            self.stg_fx중지_전략매매()
            gm.매수검색목록.delete()
            gm.매도검색목록.delete()
            gm.주문진행목록.delete()
            gm.dict종목정보.delete()
            if gm.sim_no in [1, 2, 3]:
                gm.잔고목록.delete()
            self.send_status_msg('검색내용', args='')
        except Exception as e:
            logging.error(f'전략 매매 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_run_trade(self, trade_type, recall=False):
        try:
            if recall and trade_type=='매도': # trade_type == '매도' 경우만 사용해야 함(조건검색식 적용을 보유종목을 대상으로 할 경우 신규종목은 재실행해야 적용 됨)
                if self.wait_running: return
                wait_time = gm.prx.answer('api', 'GetConditionInterval', self.매도전략)
                if wait_time > 1666:
                    QTimer.singleShot(wait_time, lambda x=trade_type: self.stg_run_trade(x))
                    self.wait_running = True
                    return
            
            self.wait_running = False
            condition = self.매수전략 if trade_type == '매수' else self.매도전략
            cond_name = condition.split(' : ')[1]
            cond_index = int(condition.split(' : ')[0])
            condition_list, bool_ok = self.stg_fx등록_조건검색(trade_type, cond_name, cond_index) #-------------------- 조건 검색 실행
            if bool_ok:
                if trade_type == '매수': gm.매수문자열 = condition
                elif trade_type == '매도': gm.매도문자열 = condition
                for code in condition_list:
                    self.stg_fx편입_실시간조건감시(trade_type, code, 'I', cond_name, cond_index)
                logging.info(f'전략 실행 - {self.전략명칭} {trade_type}전략={condition}')
                if not recall: self.send_status_msg('검색내용', f'{trade_type} {condition}')
            else:
                logging.warning(f'전략 실행 실패 - 전략명칭={self.전략명칭} {trade_type}전략={condition}') # 같은 조건 1분 제한 조건 위반

        except Exception as e:
            logging.error(f'전략 매매 실행 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_stop_trade(self, trade_type):
        try:
            condition = self.매수전략 if trade_type == '매수' else self.매도전략
            cond_name = condition.split(' : ')[1]
            cond_index = int(condition.split(' : ')[0])
            if cond_name:
                screen = f'2{"1" if trade_type == "매수" else "2"}00'
                gm.prx.order('api', 'SendConditionStop', screen, cond_name, cond_index)
            else:
                raise Exception(f'{trade_type} 조건이 없습니다.')
            logging.info(f'{trade_type} 전략 중지 - {cond_index:03d} : {cond_name}')
        except Exception as e:
            logging.error(f'전략 매매 중지 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_timeout_trade(self):
        self.stg_buy_timeout = True

    def stg_fx실행_전략매매(self):
        try:
            msg = self.stg_fx체크_전략매매()
            if msg: 
                logging.warning(f'전략 실행 실패 - 전략명칭={self.전략명칭} {msg}')
                return
            
            gm.evl.start()
            gm.evl.set_dict(gm.설정전략)
            if self.매수적용: self.stg_run_trade('매수')
            if self.매도적용: self.stg_run_trade('매도')
            self.stg_ready = True
            gm.counter.set_strategy(self.매수전략, group=self.체결횟수, ticker=self.종목제한,
                                   max_rate=self.금지율 if self.금지율적용 else None,
                                   max_times=self.금지횟수 if self.금지횟수적용 else None) # 종목별 매수 횟수 제한 전략별로 초기화 해야 함

            if gm.gui_on: 
                gm.qwork['gui'].put(Work('set_strategy_toggle', {'run': any([gm.매수문자열, gm.매도문자열])}))

        except Exception as e:
            logging.error(f'전략 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx중지_전략매매(self):
        try:
            self.stg_ready = False # 현재가 업데이트 후 매도조건 검사 중지

            if self.end_timer is not None:
                self.end_timer.stop()
                self.end_timer.deleteLater()
                self.end_timer = None

            if self.매수적용: self.stg_stop_trade('매수')
            if self.매도적용: self.stg_stop_trade('매도')
            gm.evl.stop()
            gm.evl.wait(2000)
            gm.evl.deleteLater()
            gm.evl = None
            gm.eval_q.clear()

        except Exception as e:
            logging.error(f'전략 중지 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx등록_조건검색(self, trade_type, cond_name, cond_index):
        screen = f'2{"1" if trade_type == "매수" else "2"}00'
        logging.debug(f'조건 검색 요청: 화면={screen} 인덱스={cond_index:03d} 수식명={cond_name} 구분={trade_type}')
        condition_list = []
        try:
            job = {'screen': screen, 'cond_name': cond_name, 'cond_index': cond_index, 'search': 1}
            condition_list = gm.prx.answer('api', 'SendCondition', **job)
            if isinstance(condition_list, list): return condition_list, True
                
            return [], False
        except Exception as e:
            logging.error(f'조건 검색 요청 오류: {type(e).__name__} - {e}', exc_info=True)
            return [], False

    def stg_fx편입_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            종목명 = gm.prx.answer('api', 'GetMasterCodeName', code)

            if not gm.dict종목정보.contains(code):
                전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                value={'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                gm.dict종목정보.set(code, value)

            # 주문진행목록 추가는 이렇게 바로 해야 갭 간격을 줄여 그 사이에 이중 주문이 방지 된다.
            if not (gm.주문진행목록.in_key((code, '매수')) or gm.주문진행목록.in_key((code, '매도'))):
                if kind == '매수':
                    if gm.잔고목록.in_key(code): return # 기 보유종목
                    if self.stg_buy_timeout: return # 매수 전략 실행 중지 되었음
                    gm.매수검색목록.set(key=code, data={'종목명': 종목명, '이탈': ''})
                    gm.setter_q.put(code)
                elif kind == '매도':
                    if not gm.잔고목록.in_key(code): return # 매도 할 종목 없음 - 매도검색목록에도 추가 하지도 않고 있지도 않음
                    gm.매도검색목록.set(key=code, data={'종목명': 종목명, '이탈': ''})
                key = (code, kind)
                data={'구분': kind, '상태': '요청', '종목코드': code, '종목명': 종목명, '전략매도': True}
                gm.주문진행목록.set(key=key, data=data)
            else:
                logging.debug(f'주문 처리 중인 종목: {kind} {code} {종목명}')
                return
            
            # 메세지 순서상 여기에 위치 해야 함
            self.send_status_msg('주문내용', {'구분': f'{kind}편입', '종목코드': code, '종목명': 종목명, '메시지': '/ 조건검색'})

            # 주문 처리
            if kind == '매수' and self.매수시장가:
                price = int((gm.dict종목정보.get(code, '현재가') or hoga(gm.dict종목정보.get(code, '전일가'), 99)))
                gm.eval_q.put((code, 'buy', {'rqname': '신규매수', 'price': price}))
                logging.info(f'{kind} 시장가 주문: {self.전략명칭} {code} {종목명} {price}')
            elif kind == '매도' and self.매도시장가:
                row = gm.잔고목록.get(key=code)
                gm.eval_q.put((code, 'sell', {'row': row, 'sell_condition': True}))
                logging.info(f'{kind} 시장가 주문: {self.전략명칭} {code} {종목명} price={row["현재가"]} qty={row["보유수량"]}')
            else:
                gm.주문진행목록.set(key=key, data={'상태': '대기'})
                logging.info(f'{kind} 지정가 주문: {self.전략명칭} {code} {종목명}')

            if gm.sim_no == 0 and kind == '매수':
                전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                sim_record = {'일자': dc.ToDay, '종목코드': code, '종목명': 종목명, '전일가': 전일가, 'sim_no': 2}
                gm.prx.order('dbm', 'table_upsert', 'db', db_columns.SIM_TABLE_NAME, sim_record, key=db_columns.SIM_KEYS)

            # 차트 콤보에 추가 하고, 실시간 감시에 추가
            gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{code} {종목명}'}))
            if code not in gm.set조건감시: self.stg_fx등록_종목감시([code], 1) # 조건 만족 종목 실시간 감시 추가
           
        except Exception as e:
            logging.error(f'{kind}조건 편입 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx이탈_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            if kind == '매도':
                if gm.매도검색목록.in_key(code):
                    logging.info(f'{kind}이탈 : {self.전략명칭} {code} {name}')
                    if gm.gbx_sell_checked:
                        success = gm.매도검색목록.delete(key=code)
                    else:
                        gm.매도검색목록.set(key=code, data={'이탈': '⊙'})
                return

            if gm.매수검색목록.in_key(code):
                logging.info(f'{kind}이탈 : {self.전략명칭} {code} {name}')
                if gm.gbx_buy_checked:
                    success = gm.매수검색목록.delete(key=code)
                else:
                    gm.매수검색목록.set(key=code, data={'이탈': '⊙'})

            # 실시간 감시 해지하지 않는다.
            if len(gm.set조건감시) > 90 and code in gm.set조건감시:
                gm.prx.order('api', 'SetRealRemove', dc.scr.화면['조건감시'], code)
                gm.set조건감시.remove(code)
                logging.debug(f'실시간 감시 해지: {gm.set조건감시}')

        except Exception as e:
            logging.error(f'{kind}조건 이탈 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx등록_종목감시(self, condition_list, search_flag):
        try:
            if len(gm.set조건감시) < 1: search_flag = 0

            # 종목 실시간 감시 요청
            if len(condition_list) == 1 and search_flag == 1:
                if condition_list[0] in gm.set조건감시: return

            codes = ",".join(condition_list)
            fids = "10"  # 현재가
            gm.prx.order('api', 'SetRealReg', dc.scr.화면['조건감시'], codes, fids, search_flag)
            gm.set조건감시.update(condition_list)

            # if len(condition_list) == 1: 
            #     if condition_list[0] in gm.set조건감시: return
            # gm.set조건감시.update(condition_list)
            # codes = ",".join(list(gm.set조건감시))
            # gm.prx.order('api', 'SetRealReg', dc.scr.화면['조건감시'], codes, '10', 0)
            
            logging.debug(f'실시간 감시 요청: {gm.set조건감시}')

        except Exception as e:
            logging.error(f'종목 검색 요청 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx체크_전략매매(self):
        try:
            #logging.debug(f'전략 체크 시작: {self.전략명칭}')
            if self.매수적용:
                매수전략 = self.매수전략.strip()
                if 매수전략 == '':
                    return f'매수전략이 없습니다.'
            if self.매도적용:
                매도전략 = self.매도전략.strip()
                if 매도전략 == '':
                    return f'매도전략이 없습니다.'
            if self.투자금:
                if self.투자금액 == 0:
                    return f'투자금액이 0 입니다.'
            if self.매수량:
                if self.매수수량 == 0:
                    return f'매수수량이 0 입니다.'
            if self.이익실현:
                if self.이익실현율 == 0.0:
                    return f'이익실현율이 0.0 입니다.'
            if self.이익보존:
                if self.이익보존율 == 0.0:
                    return f'이익보존율이 0.0 입니다.'
            if self.손실제한:
                if self.손실제한율 == 0.0:
                    return f'손실제한율이 0.0 입니다.'
            if self.감시적용:
                if self.감시시작율 == 0.0 and self.스탑주문율 == 0.0:
                    return f'감시시작율과 스탑주문율이 둘 다 0.0 입니다.'

            if self.설정시간:
                self.start_time = self.시작시간.strip()
                self.stop_time = self.종료시간.strip()

            if gm.sim_no == 0: # 시뮬레이션 모드 아니면 시간 체크
                now = datetime.now()
                current = now.strftime('%H:%M')
                if "15:30" > current > self.stop_time:
                    msg = f'전략 종료시간 지났습니다. {self.stop_time} {current}'
                    return msg
                else:
                    end_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.stop_time}", '%Y-%m-%d %H:%M')
                    remain_secs = max(0, (end_time - now).total_seconds())
                    if self.end_timer is not None:
                        self.end_timer.stop()
                        self.end_timer.deleteLater()
                    self.stg_buy_timeout = False
                    self.end_timer = QTimer()
                    self.end_timer.setSingleShot(True)
                    self.end_timer.setInterval(int(remain_secs*1000))
                    self.end_timer.timeout.connect(self.stg_timeout_trade)
                    self.end_timer.start()

        except Exception as e:
            logging.error(f'전략매매 체크 오류: {type(e).__name__} - {e}', exc_info=True)

    # 주문 처리  -------------------------------------------------------------------------------------------
    def on_receive_chejan_data(self, gubun, dictFID):
        if not gm.ready: return
        try:

            전략명칭 = gm.실행전략['전략명칭']
            전략정의 = gm.설정전략
            dictFID['전략명칭'] = 전략명칭
            dictFID['매수전략'] = 전략정의.get('매수전략', '')
            dictFID['전략정의'] = 전략정의
            dictFID['sim_no'] = gm.sim_no
            dictFID['종목코드'] = dictFID['종목코드'].lstrip('A')
            if gubun == '1':
                dictFID['주문구분'] = '매수' if dictFID.get('매도/매수구분', '') == '2' else '매도'
                dictFID['주문상태'] = '잔고'
                self.odr_recieve_balance_data(dictFID)
            else:
                code =dictFID['종목코드']
                kind = dictFID['주문구분'].lstrip('+-') # +매수, -매도, +매수정정, -매도정정, 매수취소, 매도취소
                order_no = dictFID['주문번호']
                주문상태 = dictFID.get('주문상태', '')
                dictFID['주문수량'] = int(dictFID.get('주문수량', 0))
                dictFID['주문가격'] = int(dictFID.get('주문가격', 0))
                dictFID['미체결수량'] = int(dictFID.get('미체결수량', 0))

                dictFID['종목코드'] = code
                dictFID['주문구분'] = kind
                dictFID['종목명'] = dictFID['종목명'].strip()
                dictFID['체결시간'] = dictFID.get('주문/체결시간', '')

                key = (code, kind)
                #row = gm.주문진행목록.get(key=key)
                if gm.주문진행목록.in_key(key): # 정상 주문 처리 상태
                    gm.주문진행목록.set(key=key, data={'상태': 주문상태})
                else: # 외부 처리 또는 취소주문 처리 상태
                    pass

                if '접수' in 주문상태:
                    self.odr_redeipt_data(dictFID)
                elif '체결' in 주문상태:
                    self.odr_conclution_data(dictFID)
                elif '확인' in 주문상태:
                    # row = gm.주문진행목록.get(key=key)
                    #if row and 주문수량 != 0 and 미체결수량 == 0: # 주문 취소주문 클리어
                    logging.info(f'{kind}주문 취소 확인: order_no = {order_no} {code} {dictFID["종목명"]}')
                    if gm.주문진행목록.len() == 0: logging.debug(f'주문진행목록=없음')
                    else: logging.debug(f'주문진행목록=\n{tabulate(gm.주문진행목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
                    gm.주문진행목록.delete(filter={'구분': '취소'})
                    if gm.주문진행목록.len() == 0: logging.debug(f'주문진행목록=없음')
                    else: logging.debug(f'주문진행목록=\n{tabulate(gm.주문진행목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')

            self.dbm_trade_upsert(dictFID)

        except Exception as e:
            logging.error(f"접수체결 오류: {type(e).__name__} - {e}", exc_info=True)

    def odr_timeout(self, kind, origin_row, dictFID):
        if gm.주문진행목록.len() == 0: return
        try:
            code = origin_row['종목코드']
            key = (code, kind)
            if not gm.주문진행목록.in_key(key): return

            rqname = kind + 'xx' # '매수xx' or '매도xx'
            order_no = origin_row['주문번호']
            name = origin_row['종목명']
            주문수량 = dictFID['주문수량']
            미체결수량 = dictFID['미체결수량']

            data={'구분': rqname, '상태': '취소요청', '종목코드': code, '종목명': name}
            gm.주문진행목록.set(key=key, data=data)

            gm.eval_q.put((code, 'cancel', {'kind': kind, 'order_no': order_no}))

            logging.info(f'{kind}주문 타임 아웃: {code} {name} 주문번호={order_no} 주문수량={주문수량} 미체결수량={미체결수량}')

        except Exception as e:
            logging.error(f"주문 타임아웃 오류: code={code} name={name} {type(e).__name__} - {e}", exc_info=True)

    def odr_redeipt_data(self, dictFID):
        try:
            qty = int(dictFID.get('주문수량', 0) or 0)
            remain_qty = int(dictFID.get('미체결수량', 0) or 0)
            kind = '매수' if dictFID['매도수구분']=='2' else '매도'
            code = dictFID['종목코드']
            name = dictFID['종목명']
            order_no = dictFID['주문번호']
            price = int(dictFID.get('주문가격', 0) or 0)
            key = (code, kind)

            if qty != 0 and remain_qty == 0: # 주문취소 원 주문 클리어(체결 없음) / 처음 접수시 qty = remain_qty
                logging.info(f'{kind}주문 취소 클리어(접수):{code} {name}  order_no={order_no}')
                if not gm.주문진행목록.delete(key=key):
                    logging.warning(f'{kind}주문 취소 클리어: 주문진행목록 삭제 실패 {kind} {code} {name} order_no={order_no}')
                return
            
            row = gm.주문진행목록.get(key=key)
            if row:
                row.update({'상태': '접수', '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price})
                gm.주문진행목록.set(key=key, data=row)
                logging.info(f'{kind}주문 정상 접수: order_no={order_no} {code} {name} 주문수량={qty} 미체결수량={remain_qty} 주문가격={price}')
            else: # 취소주문, 외부주문
                origin_no = dictFID['원주문번호'].strip('0')
                if origin_no: # 취소주문
                    구분 = dictFID["주문구분"][:2]
                    origin_row = gm.주문진행목록.get(filter={'종목코드': code, '구분': 구분, '주문번호': origin_no})
                    if origin_row:
                        origin_row[0].update({'상태': '취소접수', '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price})
                        gm.주문진행목록.set(key=(code, 구분), data=origin_row[0]) # 취소주문 접수 바로 다음 확인에서 삭제처리
                        return
                    else:
                        pass
                    logging.info(f'{구분}주문 취소 접수: origin_no={origin_no} {code} {name} 주문수량={qty} 미체결수량={remain_qty} 주문가격={price}')

                else: # 외부주문
                    종목명 = gm.prx.answer('api', 'GetMasterCodeName', code)
                    if not gm.dict종목정보.contains(code):
                        전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                        value={'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                        gm.dict종목정보.set(code, value)

                    gm.setter_q.put(code)
                    if code not in gm.set조건감시: self.stg_fx등록_종목감시([code], 1)

                    row = {'구분': kind, '상태': '외부접수', '종목코드': code, '종목명': name, '주문번호': order_no, '주문수량': qty, '미체결수량': remain_qty, '주문가격': price}
                    gm.주문진행목록.set(key=key, data=row)
                    logging.info(f'{kind}주문 외부 접수: order_no={order_no} {code} {name} 주문수량={qty} 미체결수량={remain_qty} 주문가격={price}')

            logging.debug(f'주문진행목록=\n{tabulate(gm.주문진행목록.get(type="df"), headers="keys", showindex=True, numalign="right")}')
            row = gm.주문진행목록.get(key=key)
            try:
                if row and row['구분'] in ['매수', '매도']:
                    sec = 0
                    if row['구분'] == '매수':
                        if gm.설정전략['매수취소']: sec = gm.설정전략['매수지연초']
                    elif row['구분'] == '매도':
                        if gm.설정전략['매도취소']: sec = gm.설정전략['매도지연초']

                    if sec > 0:
                        QTimer.singleShot(int(sec * 1000), lambda kind=kind, origin_row=row, dictFID=dictFID: self.odr_timeout(kind, origin_row, dictFID))
                        #threading.Timer(int(sec * 1000), lambda kind=kind, origin_row=row, dictFID=dictFID: self.odr_timeout(kind, origin_row, dictFID)).start()
            except Exception as e:
                logging.debug(f'전략 처리 오류: {row}')
                logging.error(f"전략 처리 오류: {type(e).__name__} - {e}", exc_info=True)

        except Exception as e:
            logging.error(f"접수 오류: {type(e).__name__} - {e}", exc_info=True)

    def odr_conclution_data(self, dictFID):
        try:
            qty = int(dictFID.get('체결량', 0) or 0)
            remain_qty = int(dictFID.get('미체결수량', 0) or 0)
            kind = dictFID.get('주문구분', '')
            code = dictFID['종목코드']
            name = dictFID['종목명']
            price = int(dictFID.get('체결가', 0) or 0)
            amount = price * qty
            order_no = dictFID.get('주문번호', '')
            key = (code, kind)

            if qty == 0 and remain_qty == 0: 
                logging.info(f'{kind}주문 취소 클리어(체결): {code} {name} order_no={order_no}')
                gm.주문진행목록.delete(key=key)
                return # 주문취소 클리어

            order_row = gm.주문진행목록.get(key=key)
            if not order_row:
                # 주문실패로 주문진행목록 삭제 됨.
                logging.error(f"주문진행목록이 None 입니다. key={key} {code} {name} order_no={order_no} {kind}주문 처리 실패 ***")
                return

            전략명칭 = gm.실행전략['전략명칭']
            전략정의 = gm.설정전략
            매매시간 = datetime.now().strftime('%H:%M:%S')
            단위체결량 = int(dictFID.get('단위체결량', 0) or 0)
            단위체결가 = int(dictFID.get('단위체결가', 0) or 0)

            def buy_conclution():
                try:
                    data = {'종목번호': code, '종목명': name, '보유수량': qty, '매입가': price, '매입금액': amount, \
                                '매수전략': 전략정의['매수전략'], '전략명칭': 전략정의['전략명칭'], '감시시작율': 전략정의['감시시작율'], '이익보존율': 전략정의['이익보존율'],\
                                '감시': 0, '보존': 0, '매수일자': dc.ToDay, '매수시간': 매매시간, '매수번호': order_no, '매수수량': qty, '매수가': price, '매수금액': amount}
                    if not gm.잔고목록.in_key(code):
                        if gm.sim_no == 0:
                            전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                            sim_record = {'일자': dc.ToDay, '종목코드': code, '종목명': name, '전일가': 전일가, '상태': '매수', 'sim_no': 2}
                            gm.prx.order('dbm', 'table_upsert', 'db', db_columns.SIM_TABLE_NAME, sim_record, key=db_columns.SIM_KEYS)
                        gm.holdings[code] = data
                        save_json(dc.fp.holdings_file, gm.holdings)
                        gm.counter.record_buy(code) # 매수 제한 기록
                        logging.debug(f'잔고목록 추가: {code} {name} 보유수량={qty} 매입가={price} 매입금액={amount} 미체결수량={dictFID.get("미체결수량", 0)}')

                        if self.매도적용: self.stg_run_trade('매도', recall=True) # 실매매시 보유종목이 없는경우 보유종목에서 조건검색시 실패 함. 매도 전략 실행

                    gm.잔고목록.set(key=code, data=data)

                except Exception as e:
                    logging.error(f"매수 처리중 오류 발생: {code} {name} ***", exc_info=True)

            if kind == '매수': buy_conclution()

            msg = {'구분': f'{kind}체결', '전략명칭': 전략명칭, '종목코드': code, '종목명': name,\
                    '주문수량': dictFID.get('주문수량', 0), '주문가격': dictFID.get('주문가격', 0), '주문번호': order_no}
            msg.update({'체결수량': 단위체결량, '체결가': 단위체결가, '체결금액': 단위체결가 * 단위체결량})
            self.send_status_msg('체결내용', msg)
            logging.info(f'{kind}주문 정상 체결: order_no={order_no} {code} {name} 체결수량={단위체결량} 체결가={단위체결가} 체결금액={단위체결가 * 단위체결량}')

            if remain_qty == 0:
                if kind == '매도':
                    if not gm.잔고목록.delete(key=code):
                        logging.warning(f'잔고목록 삭제 실패: {code} {dictFID["종목명"]}')

                    gm.holdings.pop(code, None)
                    save_json(dc.fp.holdings_file, gm.holdings)
                    if gm.잔고목록.len() == 0: 
                        # sql = 'DELETE FROM conclusion WHERE 매수수량<>매도수량'
                        # gm.prx.order('dbm', 'execute_query', sql=sql, db='db')
                        self.pri_fx얻기_잔고합산()

                gm.주문진행목록.delete(key=(code, kind)) # 정상 주문 완료 또는 주문취소 원 주문 클리어(일부체결 있음)

        except Exception as e:
            logging.error(f"주문 체결 오류: {kind} {type(e).__name__} - {e}", exc_info=True)

    def odr_recieve_balance_data(self, dictFID):
        if not gm.ready: return
        try:
            현재가 = abs(int(dictFID.get('현재가', 0) or 0))
            보유수량 = int(dictFID.get('보유수량', 0) or 0)
            매입단가 = abs(int(dictFID.get('매입단가', 0) or 0))
            주문가능수량 = int(dictFID.get('주문가능수량', 0) or 0)
            gm.l2손익합산 = int(dictFID.get('당일총매도손익', 0) or 0)
            code = dictFID['종목코드']
            name = dictFID['종목명']
            kind = '매수' if dictFID.get('매도/매수구분', '') == '2' else '매도'
            key = (code, kind)
            주문수량 = gm.주문진행목록.get(key=key, column='주문수량')
            data = {'보유수량': 보유수량, '매입단가': 매입단가, '매입금액': 보유수량 * 매입단가, '주문가능수량': 주문가능수량}
            msg = f'{code} {name} 주문수량={주문수량} 보유수량={보유수량} 매입단가={매입단가} 매입금액={보유수량 * 매입단가} 주문가능수량={주문가능수량}'
            if gm.잔고목록.in_key(key=code):
                logging.debug(f'잔고목록 업데이트 진행 ***: {msg}')
                gm.잔고목록.set(key=code, data=data)
            else:
                logging.warning(f'잔고목록 업데이트 삭제 ***: {msg}')

        except Exception as e:
            logging.error(f"잔고 변경 오류: {type(e).__name__} - {e}", exc_info=True)

    def dbm_trade_upsert(self, dictFID):
        try:
            dict_data = {key: dictFID[key] for key in db_columns.TRD_COLUMNS if key in dictFID}
            gm.prx.order('dbm', 'table_upsert', db='db', table='trades', dict_data=dict_data)

            if dictFID['주문상태'] == '체결':
                kind = dictFID['주문구분'] # 매수, 매도, 매수정정, 매도정정, 매수취소, 매도취소
                code = dictFID['종목코드']
                name = dictFID['종목명']
                qty = abs(int(dictFID['체결량'] or 0))
                price = abs(int(dictFID['체결가'] or 0))
                amount = abs(int(dictFID['체결누계금액'] or 0))
                tm = ':'.join(dictFID['주문/체결시간'][i:i+2] for i in range(0, 6, 2))
                st_name = dictFID['전략명칭']
                ordno = dictFID['주문번호']
                st_buy = dictFID['매수전략']
                
                result = gm.prx.answer('dbm', 'upsert_conclusion', kind, code, name, qty, price, amount, ordno, tm, st_name, st_buy, gm.sim_no)
                
                # 매도 완료 시 손실 기록
                if isinstance(result, dict) and result.get('profit_rate', 0) < 0:
                    gm.counter.record_loss(result['code'], abs(result['profit_rate']), result['name'])
                    logging.info(f"손실 기록: {result['code']} {result['name']} 손익율={result['profit_rate']:.2f}%")
                
        except Exception as e:
            logging.error(f"dbm_trade_upsert 오류: {type(e).__name__} - {e}", exc_info=True)

