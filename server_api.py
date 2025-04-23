from public import dc, gm
from classes import la
from PyQt5.QAxContainer import QAxWidget
import pandas as pd
import logging
import pythoncom
import time
import copy

class APIServer():
    def __init__(self, name):
        self.name = name

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

        self.api_init()  # 초기화 바로 실행

    def stop(self):
        pass

    def api_init(self):
        try:
            logging.debug(f'{self.name} api_init start')
            self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            self._set_signal_slots()
            logging.debug(f'{self.name} api_init end: ocx={self.ocx}')
        except Exception as e:
            logging.error(f"API 초기화 오류: {type(e).__name__} - {e}")

    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'API 로그 레벨 설정: {level}')

    # 추가 메서드 --------------------------------------------------------------------------------------------------
    def api_login(self, block=True):
        logging.debug(f'login: block={block}')
        self.CommConnect(block)

    def api_connected(self):
        return self.connected

    def api_get_condition_lists(self):
        return self.strategy_list

    def api_get_tr_result(self):
        return self.tr_result

    def api_get_tr_remained(self):
        return self.tr_remained

    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', timeout=5):
        try:
            self.tr_coulmns = output   # []
            self.tr_result_format = form # 'df' or 'dict_list'
            self.tr_received = False
            self.tr_remained = False
            self.tr_result = []

            screen = dc.화면[rqname] if not screen else screen
            for key, value in input.items(): self.SetInputValue(key, value)
            ret = self.CommRqData(rqname, trcode, next, screen)
            #logging.warning(f"** TR 요청 결과 **: {rqname} {trcode} {screen} ret={ret}/ret_type={type(ret)}")

            start_time = time.time()
            while not self.tr_received:
                for _ in range(10):
                    pythoncom.PumpWaitingMessages()
                    if self.tr_received: break
                time.sleep(0.01)
                if time.time() - start_time > timeout:
                    logging.warning(f"Timeout while waiting for {rqname} data")
                    return None, False

            return self.tr_result, self.tr_remained

        except Exception as e:
            logging.error(f"TR 요청 오류: {type(e).__name__} - {e}")
            return None, False

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
        self.ocx.dynamicCall("DisconnectRealData(QString)", screen)

    def SetRealRemove(self, screen, del_code):
        logging.debug(f'screen={screen}, del_code={del_code}')
        ret = self.ocx.dynamicCall("SetRealRemove(QString, QString)", screen, del_code)
        return ret

    def SendConditionStop(self, screen, cond_name, cond_index):
        logging.debug(f'전략 중지: screen={screen}, name={cond_name}, index={cond_index}')
        self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", screen, cond_name, cond_index)

    def SetInputValue(self, id, value):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    # 요청 메서드(일회성 콜백 발생 ) ---------------------------------------------------------------------------------
    def CommConnect(self, block=True):
        logging.debug(f'CommConnect: block={block}')
        self.ocx.dynamicCall("CommConnect()")
        if block:
            while not self.connected:
                pythoncom.PumpWaitingMessages()

    def GetConditionLoad(self, block=True):
        self.strategy_loaded = False
        result = self.ocx.dynamicCall("GetConditionLoad()")  # result = ling 1: 성공, 0: 실패
        logging.debug(f'전략 요청 : {"성공" if result==1 else "실패"}')
        if block:
            while not self.strategy_loaded:
                pythoncom.PumpWaitingMessages()
        return self.strategy_loaded

    def SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno):
        # 1초당 5회 이내 제한 (조회와 별개)
        ret = self.ocx.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                                   [rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno])
        return ret

    def CommRqData(self, rqname, trcode, next, screen):
        ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen)
        return ret

    # 요청 메서드(실시간 콜백 발생 ) ---------------------------------------------------------------------------------
    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        ret = self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen, code_list, fid_list, opt_type)
        return ret

    def SendCondition(self, screen, cond_name, cond_index, search, block=True, timeout=5):
        try:
            if block is True:
                self.tr_condition_loaded = False

            success = self.ocx.dynamicCall("SendCondition(QString, QString, int, int)", screen, cond_name, cond_index, search)
            logging.debug(f'전략 요청: screen={screen}, name={cond_name}, index={cond_index}, search={search}, 결과={"성공" if success else "실패"}')

            if success: # 1: 성공, 0: 실패
                if block is True:
                    start_time = time.time()
                    while not self.tr_condition_loaded:
                        pythoncom.PumpWaitingMessages()
                        if time.time() - start_time > timeout:
                            logging.warning(f'조건 검색 시간 초과: {screen} {cond_name} {cond_index} {search}')
                            return False
                    data = self.tr_condition_list # 성공시 리스트
                else:
                    data = False # 비동기 요청 시
            else:
                data = success # 실패시 해당 값

        except Exception as e:
            logging.error(f"SendCondition 오류: {type(e).__name__} - {e}")

        finally:
            return data

    # 응답 메서드 --------------------------------------------------------------------------------------------------
    def OnEventConnect(self, code):
        logging.debug(f'OnEventConnect: code={code}')
        self.connected = code == 0
        logging.debug(f'Login {"Success" if self.connected else "Failed"}')

    def OnReceiveConditionVer(self, ret, msg):
        logging.debug(f'ret={ret}, msg={msg}')
        self.strategy_loaded = ret == 1

    def OnReceiveTrCondition(self, screen, code_list, cond_name, cond_index, next):
        #logging.debug(f'screen={screen}, code_list={code_list}, cond_name={cond_name}, cond_index={cond_index}, next={next}')
        codes = code_list.split(';')[:-1]
        self.tr_condition_list = codes
        self.tr_condition_loaded = True

    def OnReceiveTrData(self, screen, rqname, trcode, record, next):
        if screen.startswith('4') or screen.startswith('55'):
            pass
            try:
                #logging.debug(f'OnReceiveTrData: screen={screen}, rqname={rqname}, trcode={trcode}, record={record}, next={next}')
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
                gm.admin.on_fx수신_주문결과TR(**result)

            except Exception as e:
                logging.error(f'TR 수신 오류: {type(e).__name__} - {e}', exc_info=True)

        else:
            try:
                self.tr_remained = next == '2'
                rows = self.GetRepeatCnt(trcode, rqname)
                if rows == 0: rows = 1

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

                #logging.debug(f'TR 수신 데이타: {self.tr_result}')
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
        gm.admin.on_fx실시간_조건검색(**data)

    def OnReceiveRealData(self, code, rtype, data):
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
                    gm.admin.on_fx실시간_주식체결(**job)
                elif rtype == '장시작시간': gm.admin.on_fx실시간_장운영감시(**job)

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

            if gubun == '0': gm.admin.odr_recieve_chegyeol_data(dictFID)
            elif gubun == '1': gm.admin.odr_recieve_balance_data(dictFID)

        except Exception as e:
            logging.error(f"OnReceiveChejanData error: {e}", exc_info=True)

    # 응답 메세지 --------------------------------------------------------------------------------------------------
    def OnReceiveMsg(self, screen, rqname, trcode, msg):
        logging.info(f'screen={screen}, rqname={rqname}, trcode={trcode}, msg={msg}')

    # 즉답 관련 메소드 ---------------------------------------------------------------------------------------------
    def GetLoginInfo(self, kind):
        data = self.ocx.dynamicCall("GetLoginInfo(QString)", kind)
        #logging.debug(f'kind={kind}, data={data}')
        if kind == "ACCNO":
            return data.split(';')[:-1]
        else:
            return data

    def GetConditionNameList(self):
        logging.debug('')
        data = self.ocx.dynamicCall("GetConditionNameList()")
        conditions = data.split(";")[:-1]
        result = []
        for condition in conditions:
            cond_index, cond_name = condition.split('^')
            result.append((cond_index, cond_name))
        return result

    def GetCommData(self, trcode, rqname, index, item):
        data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, index, item)
        data = data.strip() if type(data) == str else data
        return data

    def GetRepeatCnt(self, trcode, rqname):
        count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
        return count

    def GetChejanData(self, fid):
        data = self.ocx.dynamicCall("GetChejanData(int)", fid)
        return data

    def GetMasterCodeName(self, code):
        data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
        return data

    def GetMasterLastPrice(self, code):
        data = self.ocx.dynamicCall("GetMasterLastPrice(QString)", code)
        data = int(data) if data else 0
        return data

    def GetCommRealData(self, code, fid):
        data = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
        return data

    # 기타 함수 ----------------------------------------------------------------------------------------------------
    def GetCommDataEx(self, trcode, rqname):
        data = self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trcode, rqname)
        return data

