from public import gm, dc, Work,load_json, save_json
from classes import TableManager, TimeLimiter, ThreadSafeDict, CounterTicker, ThreadSafeList
from threads import OrderCommander, EvalStrategy, ChartSetter, ChartUpdater, PriceUpdater
from chart import ChartData, ScriptManager, enhance_script_manager
from tabulate import tabulate
from datetime import datetime
from PyQt5.QtCore import QThread, QTimer
import logging
import json
import pandas as pd
import time
import threading

class Admin:
    def __init__(self):
        self.name = 'admin'
        self.price_q = ThreadSafeList()
        self.eval_q = ThreadSafeList()
        self.order_q = ThreadSafeList()
        self.setter_q = ThreadSafeList()
        self.chart_q = ThreadSafeList()

        self.cts = None # ChartSetter
        self.ctu = None # ChartUpdater
        self.evl = None # EvalStrategy
        self.odc = None # OrderCommander
        self.pri = None # PriceUpdater

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
        # 쓰레드 준비
        self.set_threads()
        self.start_threads()
        gm.admin_init = True

    # 준비 작업 -------------------------------------------------------------------------------------------
    def get_login_info(self):
        accounts = gm.prx.answer('api', 'GetLoginInfo', 'ACCNO')
        logging.debug(f'GetLoginInfo Accounts: {accounts}')
        gm.list계좌콤보 = accounts
        gm.config.account = accounts[0]

        gm.config.server = gm.prx.answer('api', 'GetLoginInfo', 'GetServerGubun')
        gm.수수료율 = dc.const.fee_sim if gm.config.server == '1' else dc.const.fee_real # 모의투자 0.35%, 실전투자 0.15% 매수, 매도 각각
        gm.세금율 = dc.const.tax_rate # 코스피 거래세 0.03 + 농어촌 특별세 0.12%, 코스닥 거래세 0.15 매도시적용
        logging.debug(f"서버:{gm.config.server}, 수수료율:{gm.수수료율}, 세금율:{gm.세금율}, 계좌:{gm.config.account}")

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
            dict_data.append({'스크립트명': k, '스크립트': v.get('script', ''), '변수': json.dumps(v.get('vars', {})), '타입': v.get('type', ''), '설명': v.get('desc', '')})
        gm.스크립트.set(data=dict_data)
        gm.list스크립트 = gm.스크립트.get(column='스크립트명')
        # gm.qwork['gui'].put(Work(order='gui_script_show', job={}))

    def set_real_remove_all(self):
        logging.debug('set_real_remove_all')
        gm.prx.order('api', 'SetRealRemove', 'ALL', 'ALL')

    def get_holdings(self):
        logging.info('* get_holdings *')
        gm.dict잔고종목감시 = {}
        gm.prx.order('api', 'SetRealRemove', dc.scr.화면['실시간감시'], 'ALL')
        self.pri_fx얻기_잔고합산()
        self.pri_fx얻기_잔고목록()
        self.pri_fx등록_종목감시()

    # 쓰레드 준비 -------------------------------------------------------------------------------------------
    def start_threads(self):
        self.prx.real_condition.connect(self.run_recesive_signals)
        self.cts.start()
        self.ctu.start()
        self.evl.start()
        self.odc.start()
        self.pri.start()

    def stop_threads(self):
        self.cts.stop()
        self.ctu.stop()
        self.evl.stop()
        self.odc.stop()
        self.pri.stop()

    def set_threads(self):
        self.cts = ChartSetter(gm.prx, self.setter_q)
        self.ctu = ChartUpdater(gm.prx, self.chart_q)
        self.evl = EvalStrategy(gm.prx, self.eval_q)
        self.odc = OrderCommander(gm.prx, self.order_q)
        self.pri = PriceUpdater(gm.prx, self.price_q)

    def run_recesive_signals(self, method, *args, **kwargs):
        if hasattr(self, method):
            getattr(self, method)(*args, **kwargs)
        else:
            logging.error(f'실시간 신호 처리 오류: method={method}')

    # 공용 함수 -------------------------------------------------------------------------------------------
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
            data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
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
                data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
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

                    #self.order('cts', 'register_code', item['종목번호'])
                    self.setter_q.put(item['종목번호'])
                    gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{item["종목번호"]} {item["종목명"]}'}))
                gm.counter.set_batch(data)

            #logging.debug(f'dict_list ={dict_list}')
            if dict_list:
                dict_list = get_preview_data(dict_list)
                gm.잔고목록.set(data=dict_list)
                save_holdings(dict_list)
                save_counter(dict_list)
            #self.order('cts', 'register_code', '005930')
            self.setter_q.put('005930')

            logging.info(f"잔고목록 얻기 완료: data count={gm.잔고목록.len()}")

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
                gm.dict종목정보.set(code, value=value)

            logging.debug(f'실시간 시세 요청: codes={gm.set종목감시}')
            codes = ";".join(gm.set종목감시)
            gm.prx.order('api', 'SetRealReg', dc.scr.화면['실시간감시'], codes, "10", 0)
        except Exception as e:
            logging.error(f'실시간 시세 요청 오류: {type(e).__name__} - {e}', exc_info=True)

    def dbm_query_result(self, result, error=None):
        if error is not None:
            logging.debug(f'디비 요청 결과: result={result} error={error}')

    # 매매전략 처리  -------------------------------------------------------------------------------------------
    def stg_start(self):
        try:
            gm.매수문자열 = "" 
            gm.매도문자열 = "" 
            self.json_load_strategy_sets() # 전략 정의 리스트 로드
            _, gm.실행전략 = load_json(dc.fp.define_sets_file, dc.const.DEFAULT_DEFINE_SETS) # 실행 전략 로드
            gm.설정전략 = gm.전략정의.get(key=gm.실행전략['전략명칭']) # 실행 전략 설정 정보
            for key, value in gm.설정전략.items():
                setattr(self, key, value)
            logging.debug(f'전략명칭={gm.실행전략["전략명칭"]}')

            self.stg_fx실행_전략매매()
        except Exception as e:  
            logging.error(f'전략 매매 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_stop(self):
        try:
            self.stg_fx실행_매매종료()
            gm.매수조건목록.delete()
            gm.매도조건목록.delete()
            gm.주문목록.delete()
            self.send_status_msg('검색내용', args='')
        except Exception as e:  
            logging.error(f'전략 매매 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx실행_전략매매(self):
        try:
            msg = self.stg_fx체크_전략매매()
            if msg: 
                logging.warning(f'전략 실행 실패 - 전략명칭={self.전략명칭} {msg}')
                return
            
            self.evl.start()
            self.evl.set_dict(gm.설정전략)
            self.ready = True
            self.stg_fx실행_매매시작()

            gm.counter.set_strategy(self.매수전략, strategy_limit=self.체결횟수, ticker_limit=self.종목제한) # 종목별 매수 횟수 제한 전략별로 초기화 해야 함

            if gm.config.gui_on: 
                gm.qwork['gui'].put(Work('set_strategy_toggle', {'run': any([gm.매수문자열, gm.매도문자열])}))

        except Exception as e:
            logging.error(f'전략 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx실행_매매시작(self):
        try:
            def run_trade(trade_type):
                condition = self.매수전략 if trade_type == '매수' else self.매도전략
                cond_name = condition.split(' : ')[1]
                cond_index = int(condition.split(' : ')[0])
                condition_list, bool_ok = self.stg_fx등록_조건검색(trade_type, cond_name, cond_index) #-------------------- 조건 검색 실행
                if bool_ok:
                    if trade_type == '매수':
                        self.stg_fx등록_종목감시(condition_list, 0) # ------------------------------- 조건 만족 종목 실시간 감시
                        gm.매수문자열 = condition
                        for code in condition_list:
                            self.stg_fx편입_실시간조건감시(trade_type, code, 'I', cond_name, cond_index)
                    elif trade_type == '매도':
                        gm.매도문자열 = condition
                    logging.info(f'전략 실행 - {self.전략명칭} {trade_type}전략={condition}')
                    self.send_status_msg('검색내용', f'{trade_type} {condition}')
                else:
                    logging.warning(f'전략 실행 실패 - 전략명칭={self.전략명칭} {trade_type}전략={condition}') # 같은 조건 1분 제한 조건 위반

            if self.매수적용: run_trade('매수')
            if self.매도적용: run_trade('매도')

        except Exception as e:
            logging.error(f'전략 매매 실행 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx실행_매매종료(self, buy_stop=True, sell_stop=True):
        try:
            if not (gm.매수문자열 or  gm.매도문자열): return
            if self.end_timer:
                self.end_timer.cancel()
                self.end_timer = None
            if self.start_timer:
                self.start_timer.cancel()
                self.start_timer = None

            self.stg_fx중지_전략매매(buy_stop, sell_stop)
            self.evl.stop()
            self.ready = False
            if buy_stop: gm.매수문자열 = ""
            if sell_stop: gm.매도문자열 = ""

        except Exception as e:
            logging.error(f'전략 마무리 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx중지_전략매매(self, buy_stop=True, sell_stop=True):
        try:
            def stop_trade(trade_type):
                condition = self.매수전략 if trade_type == '매수' else self.매도전략
                cond_name = condition.split(' : ')[1]
                cond_index = int(condition.split(' : ')[0])
                if cond_name:
                    screen = f'2{"1" if trade_type == "매수" else "2"}00'
                    gm.prx.order('api', 'SendConditionStop', screen, cond_name, cond_index)
                else:
                    raise Exception(f'{trade_type} 조건이 없습니다.')
                logging.info(f'{trade_type} 전략 중지 - {cond_index:03d} : {cond_name}')
            if buy_stop and self.매수적용: stop_trade('매수')
            if sell_stop and self.매도적용: stop_trade('매도')

        except Exception as e:
            logging.error(f'전략 중지 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx등록_조건검색(self, trade_type, cond_name, cond_index):
        screen = f'2{"1" if trade_type == "매수" else "2"}00'
        logging.debug(f'조건 검색 요청: 화면={screen} 인덱스={cond_index:03d} 수식명={cond_name} 구분={trade_type}')
        condition_list = []
        try:
            job = {'screen': screen, 'cond_name': cond_name, 'cond_index': cond_index, 'search': 1}
            condition_list = gm.prx.answer('api', 'SendCondition', **job)
            if not isinstance(condition_list, list):
                return [], False
            return condition_list, True
        except Exception as e:
            logging.error(f'조건 검색 요청 오류: {type(e).__name__} - {e}', exc_info=True)
            return [], False

    def stg_fx편입_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            종목명 = gm.prx.answer('api', 'GetMasterCodeName', code)
            if not gm.dict종목정보.contains(code):
                전일가 = gm.prx.answer('api', 'GetMasterLastPrice', code)
                value={'종목명': 종목명, '전일가': 전일가, '현재가': 0}
                gm.dict종목정보.set(code, value=value)

            if gm.dict주문대기종목.contains(code):
                logging.debug(f'주문 대기 종목: {code} {종목명}')
                return

            key = f'{code}_{kind}'
            if kind == '매도':
                if not gm.잔고목록.in_key(code): 
                    #logging.debug(f'매도 할 종목 없음: {code} {종목명}')
                    return # 매도 할 종목 없음 - 매도조건목록에도 추가 하지도 않고 있지도 않음
                if gm.잔고목록.get(key=code, column='주문가능수량') == 0: 
                    logging.debug(f'매도 가능 수량 없음: {code} {종목명}')
                    return # 매도 가능 수량 없음

                if gm.주문목록.in_key(key): 
                    logging.debug(f'매도 주문 처리 중: {code} {종목명}')
                    return # 주문 처리 중 - 여기에 있어야 메세지 생략 안 함

                if not gm.매도조건목록.in_key(code):
                    gm.매도조건목록.set(key=code, data={'종목명': 종목명})
                    self.send_status_msg('주문내용', {'구분': f'{kind}편입', '전략명칭': self.전략명칭, '종목코드': code, '종목명': 종목명})
                    if not gm.잔고목록.in_key(code): 
                        #self.order('cts', 'register_code', code)
                        self.setter_q.put(code)
                    gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{code} {종목명}'}))

                if code not in gm.set조건감시:
                    self.stg_fx등록_종목감시([code], 1) # ----------------------------- 조건 만족 종목 실시간 감시 추가

            else: # if kind == '매수':
                if gm.잔고목록.in_key(code): 
                    #logging.debug(f'기 보유종목: {code} {종목명}')
                    return # 기 보유종목
                if gm.주문목록.in_key(key): 
                    logging.debug(f'매수 주문 처리 중: {code} {종목명}')
                    return # 주문 처리 중 - 여기에 있어야 메세지 생략 안 함     
                
                if not gm.매수조건목록.in_key(code): 
                    gm.매수조건목록.set(key=code, data={'종목명': 종목명})
                    self.send_status_msg('주문내용', {'구분': f'{kind}편입', '전략명칭': self.전략명칭, '종목코드': code, '종목명': 종목명})
                    #self.order('cts', 'register_code', code)
                    self.setter_q.put(code)
                    gm.qwork['gui'].put(Work('gui_chart_combo_add', {'item': f'{code} {종목명}'}))

                if code not in gm.set조건감시:
                    self.stg_fx등록_종목감시([code], 1) # ----------------------------- 조건 만족 종목 실시간 감시 추가

            logging.info(f'{kind}편입 : {self.전략명칭} {code} {종목명}')
           
            data={'키': key, '구분': kind, '상태': '대기', '종목코드': code, '종목명': 종목명, '전략매도': True}
            gm.주문목록.set(key=key, data=data) # 아래 보다 먼저 실행 해야 함

            if kind == '매수' and self.매수시장가:
                price = int((gm.dict종목정보.get(code, '현재가') or gm.dict종목정보.get(code, '전일가')) * 1.3)
                logging.debug(f'매수 시장가: {code} {종목명} {price}')
                #self.order_buy(code, '신규매수', price)
                gm.list검사목록.put({'buy': {'code': code, 'rqname': '신규매수', 'price': price}})
            elif kind == '매도' and self.매도시장가:
                row = gm.잔고목록.get(key=code)
                #self.order_sell(row, True)
                gm.list검사목록.put({'sell': {'row': row, 'sell_condition': True}})
            else:
                gm.dict주문대기종목.set(key=code, value={'kind': kind})
  
        except Exception as e:
            logging.error(f'{kind}조건 편입 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx이탈_실시간조건감시(self, kind, code, type, cond_name, cond_index):
        try:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            if kind == '매도':
                if gm.매도조건목록.in_key(code):
                    logging.info(f'{kind}이탈 : {self.전략명칭} {code} {name}')
                    success = gm.매도조건목록.delete(key=code)
                return

            if gm.매수조건목록.in_key(code):
                logging.info(f'{kind}이탈 : {self.전략명칭} {code} {name}')
                success = gm.매수조건목록.delete(key=code)

            # 실시간 감시 해지하지 않는다.
            if len(gm.set조건감시) > 90 and code in gm.set조건감시:
                gm.prx.order('api', 'SetRealRemove', dc.scr.화면['조건감시'], code)
                gm.set조건감시.remove(code)
                logging.debug(f'실시간 감시 해지: {gm.set조건감시}')

        except Exception as e:
            logging.error(f'{kind}조건 이탈 처리 오류: {type(e).__name__} - {e}', exc_info=True)

    def stg_fx등록_종목감시(self, condition_list, search_flag):
        try:
            # 종목 실시간 감시 요청
            if len(condition_list) == 1 and search_flag == 1:
                if condition_list[0] in gm.set조건감시: return

            codes = ",".join(condition_list)
            fids = "10"  # 현재가
            gm.prx.order('api', 'SetRealReg', dc.scr.화면['조건감시'], codes, fids, search_flag)
            gm.set조건감시.update(condition_list)
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
            if self.예수금:
                if self.예수금율 == 0.0:
                    return f'예수금율이 0.0 입니다.'
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

        except Exception as e:
            logging.error(f'전략매매 체크 오류: {type(e).__name__} - {e}', exc_info=True)

