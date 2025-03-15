from public import gm, dc, load_json, save_json, get_path
from classes import ModelThread, TableManager, DataTables as dt, request_time_check, TimeLimiter
from strategy import Strategy
import logging
import os

class Admin:
    def __init__(self):
        self.name = 'admin'

    def init(self):
        logging.debug(f'{self.name} init')
        self.aaa = ModelThread(name='aaa', qdict=gm.qdict, cls=self)
        self.aaa.start()

        gm.req = TimeLimiter(name='req', second=5, minute=100, hour=1000)
        gm.ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
        self.get_login_info()
        self.set_tables()
        self.get_conditions()
        self.get_strategy_info()
        self.set_real_remove_all()
        self.get_holdings()
        self.set_strategies()

    # 준비 작업 -------------------------------------------------------------------------------------------
    def get_login_info(self):
        accounts = gm.pro.api.GetLoginInfo('ACCNO')
        logging.debug(f'GetLoginInfo Accounts: {accounts}')
        gm.gui.list계좌콤보 = accounts
        gm.config.account = accounts[0]

        gm.config.server = gm.pro.api.GetLoginInfo('GetServerGubun')
        gm.config.fee_rate = dc.const.fee_sim if gm.config.server == '1' else dc.const.fee_real # 모의투자 0.35%, 실전투자 0.15% 매수, 매도 각각
        gm.config.tax_rate = dc.const.tax_rate # 코스피 거래세 0.03 + 농어촌 특별세 0.12%, 코스닥 거래세 0.15 매도시적용
        logging.debug(f"서버:{gm.config.server}, 수수료율:{gm.config.fee_rate}, 세금율:{gm.config.tax_rate}, 계좌:{gm.config.account}")

    def set_tables(self):
        gm.잔고합산 = TableManager(gm.tbl.hd잔고합산)
        gm.잔고목록 = TableManager(gm.tbl.hd잔고목록)
        gm.조건목록 = TableManager(gm.tbl.hd조건목록)
        gm.손익목록 = TableManager(gm.tbl.hd손익목록)
        gm.접수목록 = TableManager(gm.tbl.hd접수목록)
        gm.예수금 = TableManager(gm.tbl.hd예수금)
        gm.일지합산 = TableManager(gm.tbl.hd일지합산)
        gm.일지목록 = TableManager(gm.tbl.hd일지목록)
        gm.체결목록 = TableManager(gm.tbl.hd체결목록)
        gm.전략정의 = TableManager(gm.tbl.hd전략정의)
        
    def get_conditions(self):
        try:
            loaded = gm.pro.api.GetConditionLoad()
            if loaded: # sucess=1, fail=0
                gm.gui.list전략튜플 = gm.pro.api.GetConditionNameList()
                logging.debug(f'전략 로드 : {gm.gui.list전략튜플}')
                gm.gui.list전략콤보 = [condition[0] + ' : ' + condition[1] for condition in gm.gui.list전략튜플]
                logging.info(f'전략 로드 : 총 {len(gm.gui.list전략콤보)}개의 전략이 있습니다.')
            else:
                logging.error(f'전략 로드 실패')
        except Exception as e:
            logging.error(f'전략 로드 오류: {type(e).__name__} - {e}', exc_info=True)

    def get_strategy_info(self):
        try:
            success, data = load_json(dc.fp.strategy_sets_file, [dc.const.DEFAULT_STRATEGY_SETS])
            logging.debug(f'전략정의 JSON 파일을 로드했습니다. data count={len(data)}')
            gm.전략정의.set(data=data)
            gm.basic_strategy = next((item for item in data if item['전략명칭'] == dc.const.BASIC_STRATEGY), None)
            gm.strategy_row = data[0]
            return True
        except Exception as e:
            logging.error(f'전략정의 JSON 파일 읽기 에러: {type(e).__name__} - {e}', exc_info=True)
            return False

    def set_real_remove_all(self):
        logging.debug('set_real_remove_all')
        gm.pro.api.SetRealRemove(screen='ALL', del_code='ALL')

    def get_holdings(self):
        logging.info('* get_holdings *')
        gm.dict잔고종목감시 = {}
        gm.pro.api.SetRealRemove(screen=dc.scr.화면['실시간감시'], del_code='ALL')
        self.pri_fx얻기_잔고합산()
        self.pri_fx얻기_잔고목록()
        self.pri_fx등록_종목감시()

    def set_strategies(self):
        self.cdn_fx준비_전략매매()

    # 매매 개시 -------------------------------------------------------------------------------------------
    def trade_start(self):
        pass

    # 공용 함수 -------------------------------------------------------------------------------------------
    def com_SendRequest(self, rqname, trcode, input, output, next='0', screen=None, form='dict_list', timeout=5):
        if not request_time_check(kind='request'): return [], 0
        try:
            logging.debug(f'com_SendRequest: rqname={rqname} trcode={trcode} input={input} output={output} next={next} screen={screen} form={form} timeout={timeout}')
            args = {
                'rqname': rqname,
                'trcode': trcode,
                'input': input,
                'output': output,
                'next': next if next else '0',
                'screen': screen if screen else dc.화면[rqname],
                'form': form if form else 'dict_list',
                'timeout': timeout if timeout else 5
            }
            result = gm.pro.api.api_request(**args)
            data, remain = result
            # logging.debug(f'com_SendRequest 결과: {result}')
            return data, remain
        except Exception as e:
            logging.error(f'com_SendRequest 오류: {e}')
            return [], False

    # 업데이트  -------------------------------------------------------------------------------------------
    def pri_fx얻기_잔고합산(self):
        try:
            gm.잔고합산.delete()
            dict_list = []
            rqname = '잔고합산'
            trcode = 'opw00018'
            input = {'계좌번호':gm.config.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '2'}
            output = gm.tbl.hd잔고합산['컬럼']
            next = '0'
            screen = dc.scr.화면['잔고합산']
            data, remain = self.com_SendRequest(rqname, trcode, input, output, next, screen)
            dict_list.extend(data)
            if dict_list:
                for i, item in enumerate(dict_list):
                    item.update({'순번':i+1})
                gm.잔고합산.set(data=dict_list)
                logging.info(f"잔고합산 얻기 완료: data=\n{gm.잔고합산.get(type='df')}")
                gm.잔고합산_copy = gm.잔고합산.get() # copy

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
            screen = dc.scr.화면['잔고목록']
            data, remain = self.com_SendRequest(rqname, trcode, input, output, next, screen)
            logging.debug(f'잔고목록 얻기: data count={len(data)}, remain={remain}')
            dict_list.extend(data)
            while remain:
                next = '2'
                data, remain = self.com_SendRequest(rqname, trcode, input, output, next, screen)
                logging.debug(f'잔고목록 얻기 2: data count={len(data)}, remain={remain}')
                dict_list.extend(data)
            if dict_list:
                dict_list =[{**item, '종목번호':item['종목번호'].lstrip('A')} for item in dict_list]
                gm.잔고목록.set(data=dict_list)
                logging.info(f"잔고목록 얻기 완료: data=\n{gm.잔고목록.get(type='df')}")

        except Exception as e:
            logging.error(f'pri_fx얻기_잔고목록 오류: {e}', exc_info=True)

    def pri_fx등록_종목감시(self):
        try:
            codes = gm.잔고목록.get(column='종목번호')
            if not codes: return
            codes = ";".join(codes)
            gm.pro.api.SetRealReg(screen=dc.scr.화면['실시간감시'], code_list=codes, fid_list="10", opt_type=0)
        except Exception as e:
            logging.error(f'실시간 시세 요청 오류: {type(e).__name__} - {e}', exc_info=True)

    # 전략 매매  -------------------------------------------------------------------------------------------
    def cdn_fx준비_전략매매(self):
        try:
            success, gm.전략설정 = load_json(dc.fp.define_sets_file, [dc.const.DEFAULT_DEFINE_SETS])
            gm.전략쓰레드 = [None] * 6
            gm.전략쓰레드[0] = Strategy(name='전략00', qdict=gm.qdict, cls=self, 전략정의=gm.basic_strategy)
            for i in range(1, 6):
                if not gm.전략설정[i].get('전략적용', False): continue
                전략 = f'전략{i:02d}'
                전략정의 = gm.전략정의.get(key=gm.전략설정[i]['전략명칭'])
                gm.전략쓰레드[i] = Strategy(name=전략, qdict=gm.qdict, cls=self, 전략정의=전략정의)
        except Exception as e:
            logging.error(f'전략 매매 설정 오류: {type(e).__name__} - {e}', exc_info=True)





