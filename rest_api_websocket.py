# -*- coding: utf-8 -*-
"""
키움증권 REST API WebSocket 클라이언트
"""

import websocket
import json
import logging
import threading
import time
from rest_api_config import RestAPIConfig, RestAPIFieldID

class RestAPIWebSocket:
    """REST API WebSocket 클라이언트"""
    
    def __init__(self, config, token_manager):
        """
        초기화
        
        Args:
            config: RestAPIConfig 인스턴스
            token_manager: TokenManager 인스턴스
        """
        self.config = config
        self.token_manager = token_manager
        self.ws = None
        self.ws_thread = None
        self.is_running = False
        self.is_connected = False
        
        # 콜백 함수들
        self.on_message_callback = None
        self.on_error_callback = None
        self.on_close_callback = None
        
        # 재연결 설정
        self.reconnect_count = 0
        self.max_reconnect = config.WS_MAX_RECONNECT
        
    def connect(self):
        """WebSocket 연결"""
        try:
            if self.is_connected:
                logging.warning("이미 WebSocket 연결됨")
                return True
            
            # 토큰 확인
            if not self.token_manager.is_token_valid():
                logging.error("유효한 토큰 없음")
                return False
            
            # WebSocket URL
            ws_url = self.config.get_ws_url()
            
            # WebSocket 생성
            self.ws = websocket.WebSocketApp(
                ws_url,
                header={
                    "authorization": self.token_manager.get_authorization_header()
                },
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # 별도 스레드에서 실행
            self.is_running = True
            self.ws_thread = threading.Thread(target=self._run_forever, daemon=True)
            self.ws_thread.start()
            
            # 연결 대기
            for _ in range(50):  # 5초 대기
                if self.is_connected:
                    return True
                time.sleep(0.1)
            
            logging.error("WebSocket 연결 타임아웃")
            return False
            
        except Exception as e:
            logging.error(f"WebSocket 연결 오류: {type(e).__name__} - {e}", exc_info=True)
            return False
    
    def disconnect(self):
        """WebSocket 연결 해제"""
        try:
            self.is_running = False
            
            if self.ws:
                self.ws.close()
                self.ws = None
            
            self.is_connected = False
            logging.info("WebSocket 연결 해제")
            return True
            
        except Exception as e:
            logging.error(f"WebSocket 연결 해제 오류: {e}")
            return False
    
    def _run_forever(self):
        """WebSocket 실행 (별도 스레드)"""
        while self.is_running:
            try:
                self.ws.run_forever(
                    ping_interval=self.config.WS_PING_INTERVAL,
                    ping_timeout=10
                )
                
                # 연결이 끊긴 경우 재연결 시도
                if self.is_running and self.reconnect_count < self.max_reconnect:
                    self.reconnect_count += 1
                    logging.info(f"WebSocket 재연결 시도 {self.reconnect_count}/{self.max_reconnect}")
                    time.sleep(self.config.WS_RECONNECT_DELAY)
                else:
                    break
                    
            except Exception as e:
                logging.error(f"WebSocket 실행 오류: {e}")
                break
    
    def _on_open(self, ws):
        """WebSocket 연결 성공"""
        self.is_connected = True
        self.reconnect_count = 0
        logging.info("WebSocket 연결 성공")
    
    def _on_message(self, ws, message):
        """WebSocket 메시지 수신"""
        try:
            data = json.loads(message)
            
            # 콜백 호출
            if self.on_message_callback:
                self.on_message_callback(data)
                
        except Exception as e:
            logging.error(f"WebSocket 메시지 처리 오류: {e}")
    
    def _on_error(self, ws, error):
        """WebSocket 에러"""
        logging.error(f"WebSocket 에러: {error}")
        
        if self.on_error_callback:
            self.on_error_callback(error)
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 연결 종료"""
        self.is_connected = False
        logging.info(f"WebSocket 연결 종료: code={close_status_code}, msg={close_msg}")
        
        if self.on_close_callback:
            self.on_close_callback(close_status_code, close_msg)
    
    def send(self, data):
        """데이터 전송"""
        try:
            if not self.is_connected:
                logging.error("WebSocket 연결 안됨")
                return False
            
            if isinstance(data, dict):
                data = json.dumps(data)
            
            self.ws.send(data)
            return True
            
        except Exception as e:
            logging.error(f"WebSocket 전송 오류: {e}")
            return False
    
    def set_callbacks(self, on_message=None, on_error=None, on_close=None):
        """콜백 함수 설정"""
        if on_message:
            self.on_message_callback = on_message
        if on_error:
            self.on_error_callback = on_error
        if on_close:
            self.on_close_callback = on_close


class RealTimeManager:
    """실시간 데이터 관리"""
    
    def __init__(self, websocket_client):
        """
        초기화
        
        Args:
            websocket_client: RestAPIWebSocket 인스턴스
        """
        self.ws = websocket_client
        self.registered_items = {}  # {grp_no: {item: [types]}}
        
    def register_real(self, grp_no, item_list, type_list, refresh=1):
        """
        실시간 등록
        
        Args:
            grp_no: 그룹번호 (4자리 문자열)
            item_list: 종목코드 리스트 (예: ["005930"])
            type_list: 실시간 항목 리스트 (예: ["0B"])
            refresh: 기존등록유지여부 (0:기존유지안함, 1:기존유지)
            
        Returns:
            bool: 성공 여부
        """
        try:
            request = {
                "trnm": "REG",
                "grp_no": grp_no,
                "refresh": str(refresh),
                "data": [
                    {
                        "item": item_list,
                        "type": type_list
                    }
                ]
            }
            
            success = self.ws.send(request)
            
            if success:
                # 등록 정보 저장
                if grp_no not in self.registered_items:
                    self.registered_items[grp_no] = {}
                
                for item in item_list:
                    if item not in self.registered_items[grp_no]:
                        self.registered_items[grp_no][item] = []
                    self.registered_items[grp_no][item].extend(type_list)
                
                logging.info(f"실시간 등록: grp={grp_no}, items={item_list}, types={type_list}")
            
            return success
            
        except Exception as e:
            logging.error(f"실시간 등록 오류: {e}")
            return False
    
    def unregister_real(self, grp_no):
        """
        실시간 해제
        
        Args:
            grp_no: 그룹번호
            
        Returns:
            bool: 성공 여부
        """
        try:
            request = {
                "trnm": "REMOVE",
                "grp_no": grp_no,
                "refresh": "0",
                "data": []
            }
            
            success = self.ws.send(request)
            
            if success:
                # 등록 정보 삭제
                if grp_no in self.registered_items:
                    del self.registered_items[grp_no]
                
                logging.info(f"실시간 해제: grp={grp_no}")
            
            return success
            
        except Exception as e:
            logging.error(f"실시간 해제 오류: {e}")
            return False
    
    def register_condition(self, seq, search_type=1, stex_tp='K'):
        """
        조건검색 실시간 등록 (ka10173)
        
        Args:
            seq: 조건검색식 일련번호 (3자리 문자열)
            search_type: 조회타입 (1: 조건검색+실시간조건검색)
            stex_tp: 거래소구분 (K:KRX)
            
        Returns:
            bool: 성공 여부
        """
        try:
            request = {
                "trnm": "CNSRREQ",
                "seq": str(seq).zfill(3),
                "search_type": str(search_type),
                "stex_tp": stex_tp
            }
            
            success = self.ws.send(request)
            
            if success:
                logging.info(f"조건검색 실시간 등록: seq={seq}")
            
            return success
            
        except Exception as e:
            logging.error(f"조건검색 실시간 등록 오류: {e}")
            return False
    
    def unregister_condition(self, seq):
        """
        조건검색 실시간 해제 (ka10174)
        
        Args:
            seq: 조건검색식 일련번호
            
        Returns:
            bool: 성공 여부
        """
        try:
            request = {
                "trnm": "CNSRCLR",
                "seq": str(seq).zfill(3)
            }
            
            success = self.ws.send(request)
            
            if success:
                logging.info(f"조건검색 실시간 해제: seq={seq}")
            
            return success
            
        except Exception as e:
            logging.error(f"조건검색 실시간 해제 오류: {e}")
            return False


class RealTimeParser:
    """실시간 데이터 파싱"""
    
    @staticmethod
    def parse_real_data(data):
        """
        실시간 데이터 파싱
        
        Args:
            data: WebSocket으로 수신한 데이터
            
        Returns:
            (trnm: str, parsed_data: list)
        """
        try:
            trnm = data.get('trnm', '')
            
            if trnm == 'REAL':
                # 실시간 데이터
                real_list = []
                
                for item in data.get('data', []):
                    parsed = {
                        'type': item.get('type'),
                        'name': item.get('name'),
                        'item': item.get('item'),
                        'values': item.get('values', {})
                    }
                    real_list.append(parsed)
                
                return trnm, real_list
                
            elif trnm in ['REG', 'REMOVE']:
                # 등록/해제 응답
                return trnm, {
                    'return_code': data.get('return_code'),
                    'return_msg': data.get('return_msg', '')
                }
                
            elif trnm == 'CNSRREQ':
                # 조건검색 조회 데이터
                return trnm, {
                    'seq': data.get('seq'),
                    'return_code': data.get('return_code'),
                    'return_msg': data.get('return_msg', ''),
                    'data': data.get('data', [])
                }
                
            elif trnm == 'CNSRCLR':
                # 조건검색 해제 응답
                return trnm, {
                    'seq': data.get('seq'),
                    'return_code': data.get('return_code'),
                    'return_msg': data.get('return_msg', '')
                }
            
            else:
                return trnm, data
                
        except Exception as e:
            logging.error(f"실시간 데이터 파싱 오류: {e}")
            return None, None
    
    @staticmethod
    def convert_to_ocx_format(real_type, values):
        """
        실시간 데이터를 OCX 형식으로 변환
        
        Args:
            real_type: 실시간 타입 (예: "0B", "00", "04")
            values: 실시간 값 dict
            
        Returns:
            dict: OCX 형식의 FID 딕셔너리
        """
        try:
            dictFID = {}
            
            # 타입별 필드 매핑
            if real_type == '0B':
                field_map = RestAPIFieldID.REAL_STOCK
            elif real_type == '00':
                field_map = RestAPIFieldID.REAL_ORDER
            elif real_type == '04':
                field_map = RestAPIFieldID.REAL_BALANCE
            elif real_type == '02':
                field_map = RestAPIFieldID.REAL_CONDITION
            else:
                field_map = {}
            
            # 값 변환
            for fid, field_name in field_map.items():
                if fid in values:
                    dictFID[field_name] = values[fid]
            
            return dictFID
            
        except Exception as e:
            logging.error(f"OCX 형식 변환 오류: {e}")
            return {}
