# -*- coding: utf-8 -*-
"""
api_server.py에 추가할 REST API 통합 코드

사용법:
1. api_server.py 파일 상단에 아래 import 추가:
   from rest_api_integration import RestAPIIntegration

2. APIServer 클래스의 __init__ 메서드에 추가:
   self.use_rest = False  # REST API 사용 여부
   self.rest = None  # REST API 통합 객체

3. api_init 메서드에서 REST API 초기화:
   if self.use_rest:
       self.rest = RestAPIIntegration(is_mock=True, appkey='...', secretkey='...')
       self.rest.connect()

4. 각 메서드에서 REST/OCX 분기:
   if self.use_rest:
       return self.rest.method_name(...)
   else:
       return self.ocx.dynamicCall(...)
"""

import logging
from rest_api_config import RestAPIConfig, RestAPIEndpoints
from rest_api_client import RestAPIClient
from rest_api_websocket import RestAPIWebSocket, RealTimeManager, RealTimeParser

class RestAPIIntegration:
    """REST API 통합 클래스"""
    
    def __init__(self, is_mock=True, appkey=None, secretkey=None):
        """
        초기화
        
        Args:
            is_mock: 모의투자 여부
            appkey: 앱키
            secretkey: 시크릿키
        """
        self.config = RestAPIConfig(is_mock=is_mock, appkey=appkey, secretkey=secretkey)
        self.client = RestAPIClient(self.config)
        self.ws = RestAPIWebSocket(self.config, self.client.token_manager)
        self.realtime = RealTimeManager(self.ws)
        
        self.connected = False
        self.ws_connected = False
        
        # 콜백 저장
        self.on_real_data_callback = None
        self.on_real_condition_callback = None
        self.on_chejan_data_callback = None
        
    def connect(self):
        """연결 (토큰 발급)"""
        success = self.client.connect()
        if success:
            self.connected = True
            logging.info("REST API 연결 성공")
        return success
    
    def disconnect(self):
        """연결 해제"""
        if self.ws_connected:
            self.ws.disconnect()
            self.ws_connected = False
        
        if self.connected:
            self.client.disconnect()
            self.connected = False
        
        logging.info("REST API 연결 해제")
    
    def connect_websocket(self):
        """WebSocket 연결"""
        if not self.connected:
            logging.error("먼저 REST API 연결 필요")
            return False
        
        # 콜백 설정
        self.ws.set_callbacks(on_message=self._on_ws_message)
        
        success = self.ws.connect()
        if success:
            self.ws_connected = True
            logging.info("WebSocket 연결 성공")
        return success
    
    def _on_ws_message(self, data):
        """WebSocket 메시지 처리"""
        try:
            trnm, parsed_data = RealTimeParser.parse_real_data(data)
            
            if trnm == 'REAL':
                # 실시간 데이터
                for item in parsed_data:
                    real_type = item['type']
                    code = item['item']
                    values = item['values']
                    
                    # OCX 형식으로 변환
                    dictFID = RealTimeParser.convert_to_ocx_format(real_type, values)
                    
                    if real_type == '02':
                        # 조건검색 실시간
                        if self.on_real_condition_callback:
                            insert_del = dictFID.get('삽입삭제구분', 'I')
                            seq = dictFID.get('일련번호', '')
                            self.on_real_condition_callback(code, insert_del, '', seq)
                    
                    elif real_type in ['00', '04']:
                        # 주문체결, 잔고
                        if self.on_chejan_data_callback:
                            gubun = '0' if real_type == '00' else '1'
                            self.on_chejan_data_callback(gubun, dictFID)
                    
                    else:
                        # 일반 실시간 시세
                        if self.on_real_data_callback:
                            self.on_real_data_callback(code, real_type, dictFID)
            
            elif trnm == 'CNSRREQ':
                # 조건검색 조회 결과
                if parsed_data.get('return_code') == 0:
                    codes = [item.get('jmcode', '').replace('A', '') for item in parsed_data.get('data', [])]
                    logging.info(f"조건검색 결과: {len(codes)}개 종목")
                    # 여기서 초기 조회 결과 처리 필요시 추가
                    
        except Exception as e:
            logging.error(f"WebSocket 메시지 처리 오류: {e}", exc_info=True)
    
    def set_callbacks(self, on_real_data=None, on_real_condition=None, on_chejan_data=None):
        """콜백 함수 설정"""
        if on_real_data:
            self.on_real_data_callback = on_real_data
        if on_real_condition:
            self.on_real_condition_callback = on_real_condition
        if on_chejan_data:
            self.on_chejan_data_callback = on_chejan_data
    
    # ========== 조회 API ==========
    
    def get_balance(self, accno):
        """
        잔고 조회 (kt00018)
        
        Args:
            accno: 계좌번호
            
        Returns:
            (success, data_list)
        """
        try:
            body = {
                "accno": accno,
                "pswd": "",
                "pswd_input": "00",
                "search_gb": "2"
            }
            
            success, all_data = self.client.request_continuous(
                api_id="kt00018",
                endpoint="/api/dostk/opw00018",
                body=body
            )
            
            if success:
                # 데이터 변환
                result_list = []
                for data in all_data:
                    # 응답 데이터 파싱 (실제 키 이름은 문서 확인 필요)
                    items = data.get('output', [])
                    result_list.extend(items)
                
                return True, result_list
            
            return False, []
            
        except Exception as e:
            logging.error(f"잔고 조회 오류: {e}", exc_info=True)
            return False, []
    
    def get_chart_data(self, code, cycle, tick='1', count=600):
        """
        차트 조회
        
        Args:
            code: 종목코드
            cycle: 주기 (mi=분봉, dy=일봉, wk=주봉, mo=월봉, tk=틱봉)
            tick: 틱/분 (분봉일 경우 1,3,5,10,15,30,45,60)
            count: 조회 개수
            
        Returns:
            (success, data_list)
        """
        try:
            # API 엔드포인트 매핑
            endpoint_map = {
                'tk': RestAPIEndpoints.CHART_TICK,
                'mi': RestAPIEndpoints.CHART_MIN,
                'dy': RestAPIEndpoints.CHART_DAY,
                'wk': RestAPIEndpoints.CHART_WEEK,
                'mo': RestAPIEndpoints.CHART_MONTH
            }
            
            api_id_map = {
                'tk': 'ka10079',
                'mi': 'ka10080',
                'dy': 'ka10081',
                'wk': 'ka10082',
                'mo': 'ka10083'
            }
            
            endpoint = endpoint_map.get(cycle)
            api_id = api_id_map.get(cycle)
            
            if not endpoint:
                logging.error(f"잘못된 차트 주기: {cycle}")
                return False, []
            
            # 요청 바디 구성
            if cycle in ['mi', 'tk']:
                body = {
                    "stk_cd": code,
                    "tick_rng": tick,
                    "fix_stk_pr_gb": "1"
                }
            else:
                from datetime import datetime
                today = datetime.now().strftime('%Y%m%d')
                body = {
                    "stk_cd": code,
                    "base_dt": today,
                    "fix_stk_pr_gb": "1"
                }
            
            success, data = self.client.request_with_retry(api_id, endpoint, body)
            
            if success:
                # 응답 데이터 파싱
                chart_data = data.get('output', [])
                return True, chart_data
            
            return False, []
            
        except Exception as e:
            logging.error(f"차트 조회 오류: {e}", exc_info=True)
            return False, []
    
    def get_condition_list(self):
        """
        조건검색 목록 조회 (ka10171)
        
        Returns:
            (success, condition_list)
        """
        try:
            success, data = self.client.request_with_retry(
                api_id="ka10171",
                endpoint="/api/dostk/condition"
            )
            
            if success:
                # 조건 목록 파싱
                conditions = data.get('output', [])
                # [(index, name), ...] 형식으로 변환
                result = [(item.get('seq'), item.get('name')) for item in conditions]
                return True, result
            
            return False, []
            
        except Exception as e:
            logging.error(f"조건검색 목록 조회 오류: {e}", exc_info=True)
            return False, []
    
    # ========== 주문 API ==========
    
    def send_order(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno=''):
        """
        주문 전송
        
        Args:
            rqname: 요청명
            screen: 화면번호
            accno: 계좌번호
            ordtype: 주문유형 (1=신규매수, 2=신규매도, 3=매수취소, 4=매도취소, 5=매수정정, 6=매도정정)
            code: 종목코드
            quantity: 수량
            price: 가격
            hoga: 호가구분 (00=지정가, 03=시장가)
            ordno: 원주문번호
            
        Returns:
            int: 주문번호 (0=실패)
        """
        try:
            # 주문 유형별 API ID 매핑
            api_id_map = {
                1: 'kt10000',  # 매수
                2: 'kt10001',  # 매도
                3: 'kt10003',  # 매수취소
                4: 'kt10003',  # 매도취소
                5: 'kt10002',  # 매수정정
                6: 'kt10002',  # 매도정정
            }
            
            api_id = api_id_map.get(ordtype)
            if not api_id:
                logging.error(f"잘못된 주문유형: {ordtype}")
                return 0
            
            # 요청 바디 구성
            body = {
                "accno": accno,
                "stk_cd": code,
                "qty": quantity,
                "prc": price if hoga == '00' else 0,
                "hoga_gb": hoga,
            }
            
            # 취소/정정인 경우 원주문번호 추가
            if ordtype in [3, 4, 5, 6]:
                body["org_ord_no"] = ordno
            
            success, data = self.client.request_with_retry(api_id, "/api/dostk/order", body)
            
            if success:
                # 주문번호 추출
                order_no = data.get('ord_no', '0')
                logging.info(f"주문 성공: order_no={order_no}")
                return int(order_no) if order_no.isdigit() else 0
            
            return 0
            
        except Exception as e:
            logging.error(f"주문 전송 오류: {e}", exc_info=True)
            return 0
    
    # ========== 실시간 API ==========
    
    def set_real_reg(self, screen, code_list, fid_list, opt_type):
        """
        실시간 시세 등록
        
        Args:
            screen: 화면번호 (그룹번호로 사용)
            code_list: 종목코드 리스트 또는 세미콜론 구분 문자열
            fid_list: FID 리스트 (무시됨, REST는 type으로 결정)
            opt_type: 옵션 (0=기존 유지, 1=기존 삭제)
            
        Returns:
            int: 성공=1, 실패=0
        """
        try:
            if not self.ws_connected:
                if not self.connect_websocket():
                    return 0
            
            # 코드 리스트 변환
            if isinstance(code_list, str):
                codes = code_list.split(';')
                codes = [c for c in codes if c]
            else:
                codes = code_list
            
            # 실시간 타입 (주식체결)
            types = ['0B']
            
            # 등록
            refresh = 0 if opt_type == '1' else 1
            success = self.realtime.register_real(screen, codes, types, refresh)
            
            return 1 if success else 0
            
        except Exception as e:
            logging.error(f"실시간 등록 오류: {e}", exc_info=True)
            return 0
    
    def set_real_remove(self, screen, del_code):
        """
        실시간 해제
        
        Args:
            screen: 화면번호
            del_code: 삭제할 종목코드 (ALL=전체)
            
        Returns:
            int: 성공=1, 실패=0
        """
        try:
            if screen == 'ALL':
                # 모든 그룹 해제
                for grp_no in list(self.realtime.registered_items.keys()):
                    self.realtime.unregister_real(grp_no)
            else:
                # 특정 그룹 해제
                success = self.realtime.unregister_real(screen)
                return 1 if success else 0
            
            return 1
            
        except Exception as e:
            logging.error(f"실시간 해제 오류: {e}", exc_info=True)
            return 0
    
    def send_condition(self, screen, cond_name, cond_index, search):
        """
        조건검색 실시간 등록
        
        Args:
            screen: 화면번호
            cond_name: 조건명
            cond_index: 조건 인덱스
            search: 검색 구분 (0=조건검색만, 1=조건검색+실시간)
            
        Returns:
            int: 성공=1, 실패=0
        """
        try:
            if not self.ws_connected:
                if not self.connect_websocket():
                    return 0
            
            # 실시간 등록
            success = self.realtime.register_condition(
                seq=cond_index,
                search_type=search
            )
            
            return 1 if success else 0
            
        except Exception as e:
            logging.error(f"조건검색 등록 오류: {e}", exc_info=True)
            return 0
    
    def send_condition_stop(self, screen, cond_name, cond_index):
        """
        조건검색 실시간 해제
        
        Args:
            screen: 화면번호
            cond_name: 조건명
            cond_index: 조건 인덱스
        """
        try:
            success = self.realtime.unregister_condition(cond_index)
            logging.info(f"조건검색 해제: {cond_name} ({cond_index})")
            
        except Exception as e:
            logging.error(f"조건검색 해제 오류: {e}", exc_info=True)
