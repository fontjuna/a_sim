# -*- coding: utf-8 -*-
"""
키움증권 REST API Server
- 기존 APIServer 클래스에서 시뮬레이션 제거
- REST API 통합
- OCX와 REST API 병행 지원
"""

from public import hoga, dc, init_logger, profile_operation, QWork
from classes import TimeLimiter
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication
from datetime import datetime
import pandas as pd
import logging
import time
import random
import pythoncom
import copy
import sys

# REST API 모듈 import
try:
    from rest_api_integration import RestAPIIntegration
    REST_API_AVAILABLE = True
except ImportError:
    REST_API_AVAILABLE = False
    logging.warning("REST API 모듈을 찾을 수 없습니다. OCX 모드만 사용 가능합니다.")

# 시간 제한 체크
ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
req = TimeLimiter(name='req', second=5, minute=100, hour=1000)

def com_request_time_check(kind='order', cond_text=None):
    """API 요청 시간 제한 체크"""
    if kind == 'order':
        wait_time = ord.check_interval()
    elif kind == 'request':
        wait_time = max(req.check_interval(), req.check_condition_interval(cond_text) if cond_text else 0)
    
    if wait_time > 1666:
        msg = f'빈번한 요청으로 인하여 긴 대기 시간이 필요 하므로 요청을 취소합니다. 대기시간: {float(wait_time/1000)} 초'
        logging.warning(msg)
        return False
    elif wait_time > 1000:
        msg = f'빈번한 요청은 시간 제한을 받습니다. 잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
        time.sleep((wait_time-10)/1000)
        wait_time = 0
        logging.info(msg)
    elif wait_time > 0:
        msg = f'잠시 대기 후 실행 합니다. 대기시간: {float(wait_time/1000)} 초'
        logging.info(msg)
    
    time.sleep((wait_time+100)/1000)
    
    if kind == 'order':
        ord.update_request_times()
    elif kind == 'request':
        if cond_text:
            req.update_condition_time(cond_text)
        else:
            req.update_request_times()
    
    return True


class APIServer:
    """키움증권 API 서버 (OCX + REST API 통합)"""
    
    def __init__(self):
        self.name = 'api'
        self.app = None
        
        # OCX 관련
        self.ocx = None
        self.use_ocx = False
        
        # REST API 관련
        self.rest = None
        self.use_rest = False
        self.rest_appkey = None
        self.rest_secretkey = None
        
        # 공통
        self.connected = False
        self.order = None  # proxy order 함수
        
        # 전략/조건 관련
        self.strategy_loaded = False
        self.strategy_list = None
        
        # TR 관련
        self.tr_result_format = 'dict_list'
        self.tr_received = False
        self.tr_result = None
        self.tr_remained = False
        self.tr_coulmns = None
        
        # 조건검색 관련
        self.tr_condition_loaded = False
        self.tr_condition_list = None
        
        # 주문번호
        self.order_no = int(time.strftime('%Y%m%d', time.localtime())) + random.randint(0, 100000)
    
    def cleanup(self):
        """정리"""
        if self.use_rest and self.rest:
            self.rest.disconnect()
        
        self.connected = False
        logging.info("APIServer 종료")
    
    def initialize(self):
        """초기화"""
        init_logger()
    
    def api_init(self, mode='rest', is_mock=True, appkey=None, secretkey=None, log_level=logging.DEBUG):
        """
        API 초기화
        
        Args:
            mode: 'rest' 또는 'ocx'
            is_mock: 모의투자 여부 (True=모의, False=운영)
            appkey: REST API 앱키
            secretkey: REST API 시크릿키
            log_level: 로그 레벨
        """
        try:
            import os
            pid = os.getpid()
            self.set_log_level(log_level)
            
            if mode == 'rest':
                # REST API 모드
                if not REST_API_AVAILABLE:
                    logging.error("REST API 모듈이 없습니다. rest_api_*.py 파일들을 확인하세요.")
                    return False
                
                if not appkey or not secretkey:
                    logging.error("REST API 사용시 appkey와 secretkey가 필요합니다.")
                    return False
                
                self.use_rest = True
                self.use_ocx = False
                self.rest_appkey = appkey
                self.rest_secretkey = secretkey
                
                self.rest = RestAPIIntegration(
                    is_mock=is_mock,
                    appkey=appkey,
                    secretkey=secretkey
                )
                
                # 콜백 설정
                self.rest.set_callbacks(
                    on_real_data=self._on_rest_real_data,
                    on_real_condition=self._on_rest_real_condition,
                    on_chejan_data=self._on_rest_chejan_data
                )
                
                logging.info(f'REST API 초기화 완료: pid={pid}, is_mock={is_mock}')
                
            else:
                # OCX 모드
                self.use_rest = False
                self.use_ocx = True
                
                if self.app is None:
                    self.app = QApplication(sys.argv)
                
                if self.ocx is None:
                    logging.debug("ActiveX 컨트롤 생성 시작: KHOPENAPI.KHOpenAPICtrl.1")
                    self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
                    self._set_signal_slots()
                
                logging.info(f'OCX 초기화 완료: pid={pid}')
            
            return True
            
        except Exception as e:
            logging.error(f"API 초기화 오류: {type(e).__name__} - {e}", exc_info=True)
            return False
    
    def set_log_level(self, level):
        """로그 레벨 설정"""
        logging.getLogger().setLevel(level)
    
    # ========== REST API 콜백 메서드 ==========
    
    def _on_rest_real_data(self, code, rtype, dictFID):
        """REST API 실시간 시세 콜백"""
        try:
            if self.order:
                self.order('rcv', 'proxy_method', QWork(method='on_receive_real_data', args=(code, rtype, dictFID)))
        except Exception as e:
            logging.error(f"REST 실시간 데이터 처리 오류: {e}", exc_info=True)
    
    def _on_rest_real_condition(self, code, id_type, cond_name, cond_index):
        """REST API 실시간 조건검색 콜백"""
        try:
            if self.order:
                self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, id_type, cond_name, cond_index)))
        except Exception as e:
            logging.error(f"REST 조건검색 처리 오류: {e}", exc_info=True)
    
    def _on_rest_chejan_data(self, gubun, dictFID):
        """REST API 주문체결/잔고 콜백"""
        try:
            if self.order:
                self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=(gubun, dictFID)))
        except Exception as e:
            logging.error(f"REST 체결/잔고 처리 오류: {e}", exc_info=True)
    
    # ========== OCX Signal Slots ==========
    
    def _set_signal_slots(self):
        """OCX 시그널 슬롯 연결"""
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.ocx.OnReceiveConditionVer.connect(self.OnReceiveConditionVer)
        self.ocx.OnReceiveTrCondition.connect(self.OnReceiveTrCondition)
        self.ocx.OnReceiveTrData.connect(self.OnReceiveTrData)
        self.ocx.OnReceiveRealData.connect(self.OnReceiveRealData)
        self.ocx.OnReceiveChejanData.connect(self.OnReceiveChejanData)
        self.ocx.OnReceiveRealCondition.connect(self.OnReceiveRealCondition)
        self.ocx.OnReceiveMsg.connect(self.OnReceiveMsg)
    
    # ========== 로그인/연결 ==========
    
    @profile_operation
    def CommConnect(self, block=True):
        """로그인/연결"""
        logging.debug(f'CommConnect: block={block}')
        
        if self.use_rest:
            # REST API 연결
            success = self.rest.connect()
            if success:
                self.connected = True
                if self.order:
                    self.order('prx', 'set_connected', self.connected)
                logging.info("REST API 로그인 성공")
            else:
                logging.error("REST API 로그인 실패")
            return
        
        # OCX 연결
        self.ocx.dynamicCall("CommConnect()")
        if block:
            while not self.connected:
                pythoncom.PumpWaitingMessages()
    
    def GetConnectState(self):
        """연결 상태 조회"""
        if self.use_rest:
            return 1 if self.connected else 0
        else:
            return self.ocx.dynamicCall("GetConnectState()")
    
    # ========== 조건검색 ==========
    
    def GetConditionLoad(self, block=True):
        """조건검색 목록 로드"""
        if self.use_rest:
            success, cond_list = self.rest.get_condition_list()
            if success:
                self.strategy_loaded = True
                self.strategy_list = cond_list
                return 1
            return 0
        else:
            self.strategy_loaded = False
            result = self.ocx.dynamicCall("GetConditionLoad()")
            logging.debug(f'전략 요청 : {"성공" if result==1 else "실패"}')
            if block:
                while not self.strategy_loaded:
                    pythoncom.PumpWaitingMessages()
            return result
    
    def GetConditionNameList(self):
        """조건검색 목록 조회"""
        logging.debug('')
        
        if self.use_rest:
            return self.strategy_list if self.strategy_list else []
        else:
            data = self.ocx.dynamicCall("GetConditionNameList()")
            conditions = data.split(";")[:-1]
            cond_data_list = []
            for condition in conditions:
                cond_index, cond_name = condition.split('^')
                cond_data_list.append((cond_index, cond_name))
            return cond_data_list
    
    def SendCondition(self, screen, cond_name, cond_index, search, block=True, wait=15):
        """조건검색 요청"""
        cond_text = f'{cond_index:03d} : {cond_name.strip()}'
        if not com_request_time_check(kind='request', cond_text=cond_text):
            return False
        
        if self.use_rest:
            # REST API 조건검색
            result = self.rest.send_condition(screen, cond_name, cond_index, search)
            return result == 1
        else:
            # OCX 조건검색
            try:
                if block is True:
                    self.tr_condition_loaded = False
                
                logging.info(f'조건검색 요청: screen={screen} index={cond_index:03d} 수식명={cond_name} 구분={search}')
                result = self.ocx.dynamicCall("SendCondition(QString, QString, int, int)", screen, cond_name, cond_index, search)
                
                if result != 1:
                    logging.error(f'조건검색 요청 실패: {cond_name}')
                    return False
                
                if block:
                    start_time = time.time()
                    while not self.tr_condition_loaded:
                        pythoncom.PumpWaitingMessages()
                        if time.time() - start_time > wait:
                            logging.warning(f'조건검색 타임아웃: {cond_name}')
                            return False
                    return True
                else:
                    return True
                    
            except Exception as e:
                logging.error(f'조건검색 요청 오류: {type(e).__name__} - {e}', exc_info=True)
                return False
    
    def SendConditionStop(self, screen, cond_name, cond_index):
        """조건검색 중지"""
        if self.use_rest:
            self.rest.send_condition_stop(screen, cond_name, cond_index)
        else:
            logging.debug(f'screen={screen}, cond_name={cond_name}, cond_index={cond_index}')
            self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", screen, cond_name, cond_index)
    
    # ========== 주문 ==========
    
    def SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno):
        """주문 전송"""
        if self.use_rest:
            # REST API 주문
            return self.rest.send_order(rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno)
        else:
            # OCX 주문
            ret = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                [rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno]
            )
            return ret
    
    # ========== 실시간 등록/해제 ==========
    
    def SetRealReg(self, screen, code_list, fid_list, opt_type):
        """실시간 시세 등록"""
        if isinstance(code_list, str):
            code_list_str = code_list
            code_list = [c for c in code_list.split(';') if c]
        else:
            code_list_str = ';'.join(code_list)
        
        logging.debug(f'SetRealReg: screen={screen}, codes={code_list}, fids={fid_list}, opt={opt_type}')
        
        if self.use_rest:
            # REST API 실시간 등록
            return self.rest.set_real_reg(screen, code_list, fid_list, opt_type)
        else:
            # OCX 실시간 등록
            fids_str = ';'.join(map(str, fid_list)) if isinstance(fid_list, list) else fid_list
            
            try:
                result = self.ocx.dynamicCall(
                    "SetRealReg(QString, QString, QString, QString)", 
                    screen, code_list_str, fids_str, opt_type
                )
                logging.debug(f'SetRealReg 결과: {result}')
                return result
            except Exception as e:
                logging.error(f"SetRealReg 오류: {type(e).__name__} - {e}")
                return 0
    
    def SetRealRemove(self, screen, del_code):
        """실시간 해제"""
        logging.debug(f'screen={screen}, del_code={del_code}')
        
        if self.use_rest:
            return self.rest.set_real_remove(screen, del_code)
        else:
            ret = self.ocx.dynamicCall("SetRealRemove(QString, QString)", screen, del_code)
            return ret
    
    def DisconnectRealData(self, screen):
        """실시간 연결 해제"""
        logging.debug(f'screen={screen}')
        
        if self.use_rest:
            self.rest.set_real_remove(screen, 'ALL')
        else:
            self.ocx.dynamicCall("DisconnectRealData(QString)", screen)
    
    # ========== TR 조회 ==========
    
    def SetInputValue(self, id, value):
        """입력값 설정"""
        if not self.use_rest:
            self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)
    
    def CommRqData(self, rqname, trcode, next, screen):
        """TR 요청"""
        if not self.use_rest:
            ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rqname, trcode, next, screen)
            return ret
        return 0
    
    def api_request(self, rqname, trcode, input, output, next=0, screen=None, form='dict_list', wait=5):
        """API 요청 (통합)"""
        try:
            if not com_request_time_check(kind='request'):
                return [], False
            
            # REST API 모드에서는 직접 구현 필요
            if self.use_rest:
                logging.warning("REST API 모드에서는 api_request 직접 구현 필요")
                return [], False
            
            # OCX 모드
            self.tr_remained = False
            self.tr_result = []
            self.tr_coulmns = output
            self.tr_result_format = form
            self.tr_received = False
            
            screen = dc.화면[rqname] if not screen else screen
            for key, value in input.items():
                self.SetInputValue(key, value)
            
            ret = self.CommRqData(rqname, trcode, next, screen)
            
            start_time = time.time()
            while not self.tr_received:
                pythoncom.PumpWaitingMessages()
                if time.time() - start_time > wait:
                    logging.warning(f"Timeout while waiting for {rqname} data")
                    return [], False
            
            return self.tr_result, self.tr_remained
            
        except Exception as e:
            logging.error(f"TR 요청 오류: {type(e).__name__} - {e}")
            return [], False
    
    # ========== OCX 이벤트 핸들러 ==========
    
    def OnEventConnect(self, code):
        """연결 이벤트"""
        logging.debug(f'OnEventConnect: code={code}')
        self.connected = code == 0
        if self.order:
            self.order('prx', 'set_connected', self.connected)
        logging.info(f'Login {"Success" if self.connected else "Failed"}')
    
    def OnReceiveConditionVer(self, ret, msg):
        """조건검색 로드 완료"""
        logging.debug(f'ret={ret}, msg={msg}')
        self.strategy_loaded = ret == 1
    
    def OnReceiveTrCondition(self, screen, code_list, cond_name, cond_index, next):
        """조건검색 결과"""
        codes = code_list.split(';')[:-1]
        self.tr_condition_list = codes
        self.tr_condition_loaded = True
    
    def OnReceiveTrData(self, screen, rqname, trcode, record, next):
        """TR 데이터 수신"""
        try:
            self.tr_remained = next == '2'
            rows = self.GetRepeatCnt(trcode, rqname)
            if rows == 0:
                rows = 1
            
            data_list = []
            is_dict = self.tr_result_format == 'dict_list'
            
            for row in range(rows):
                row_data = {} if is_dict else []
                for column in self.tr_coulmns:
                    data = self.GetCommData(trcode, rqname, row, column)
                    if is_dict:
                        row_data[column] = data
                    else:
                        row_data.append(data)
                
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
    
    def OnReceiveRealCondition(self, code, id_type, cond_name, cond_index):
        """실시간 조건검색"""
        if self.order:
            self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, id_type, cond_name, cond_index)))
    
    def OnReceiveRealData(self, code, rtype, data):
        """실시간 시세"""
        try:
            dictFID = {}
            if rtype in ['주식체결', '장시작시간']:
                if rtype == '주식체결':
                    dict_temp = dc.fid.주식체결
                elif rtype == '장시작시간':
                    dict_temp = dc.fid.장시작시간
                
                for key, value in dict_temp.items():
                    data = self.GetCommRealData(code, value)
                    dictFID[key] = data.strip() if type(data) == str else data
                
                if rtype == '주식체결':
                    if self.order:
                        self.order('rcv', 'proxy_method', QWork(method='on_receive_real_data', args=(code, rtype, dictFID)))
                elif rtype == '장시작시간':
                    if self.order:
                        self.order('rcv', 'proxy_method', QWork(method='on_receive_market_status', args=(code, rtype, dictFID)))
        except Exception as e:
            logging.error(f"OnReceiveRealData error: {e}", exc_info=True)
    
    def OnReceiveChejanData(self, gubun, item_cnt, fid_list):
        """주문체결/잔고"""
        try:
            dictFID = {}
            fids = fid_list.split(';')
            
            for fid in fids:
                if not fid:
                    continue
                fid_int = int(fid)
                data = self.GetChejanData(fid_int)
                
                # FID -> 필드명 매핑
                for field_name, field_id in dc.fid.접수체결.items():
                    if field_id == fid_int:
                        dictFID[field_name] = data.strip() if isinstance(data, str) else data
                        break
            
            if self.order:
                self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=(gubun, dictFID)))
                
        except Exception as e:
            logging.error(f"OnReceiveChejanData error: {e}", exc_info=True)
    
    def OnReceiveMsg(self, screen, rqname, trcode, msg):
        """메시지 수신"""
        logging.info(f'screen={screen}, rqname={rqname}, trcode={trcode}, msg={msg}')
    
    # ========== 기타 OCX 메서드 ==========
    
    def GetCommData(self, trcode, rqname, index, item):
        """TR 데이터 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, index, item)
            data = data.strip() if type(data) == str else data
            return data
        return ""
    
    def GetRepeatCnt(self, trcode, rqname):
        """반복 데이터 개수"""
        if not self.use_rest:
            count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
            return count
        return 0
    
    def GetChejanData(self, fid):
        """체결 데이터 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetChejanData(int)", fid)
            return data
        return ""
    
    def GetCommRealData(self, code, fid):
        """실시간 데이터 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
            return data
        return ""
    
    def GetMasterCodeName(self, code):
        """종목명 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
            return data
        return ""
    
    def GetMasterLastPrice(self, code):
        """전일가 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetMasterLastPrice(QString)", code)
        else:
            data = 0
        data = int(data) if data else 0
        return data
    
    def GetLoginInfo(self, kind):
        """로그인 정보 조회"""
        logging.debug(f'GetLoginInfo: kind={kind}')
        
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetLoginInfo(QString)", kind)
            if kind == "ACCNO":
                return data.split(';')[:-1]
            else:
                return data
        else:
            # REST API는 계좌번호를 별도로 관리 필요
            if kind == "ACCNO":
                return []
            else:
                return '1'
    
    def GetCodeListByMarket(self, market):
        """시장별 종목코드 조회"""
        if not self.use_rest:
            data = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market)
            tokens = data.split(';')[:-1]
            return tokens
        return []
