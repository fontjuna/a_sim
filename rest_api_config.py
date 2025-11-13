# -*- coding: utf-8 -*-
"""
키움증권 REST API 설정 파일
"""

class RestAPIConfig:
    """REST API 설정"""
    
    # 운영 도메인
    PROD_BASE_URL = "https://api.kiwoom.com"
    PROD_WS_URL = "wss://api.kiwoom.com:10000"
    
    # 모의투자 도메인
    MOCK_BASE_URL = "https://mockapi.kiwoom.com"
    MOCK_WS_URL = "wss://mockapi.kiwoom.com:10000"
    
    # API 경로
    AUTH_TOKEN_URL = "/oauth2/token"
    AUTH_REVOKE_URL = "/oauth2/revoke"
    STOCK_API_URL = "/api/dostk"
    WEBSOCKET_URL = "/api/dostk/websocket"
    
    # 요청 설정
    REQUEST_TIMEOUT = 30  # 초
    MAX_RETRY = 3
    RETRY_DELAY = 1  # 초
    
    # 토큰 관리
    TOKEN_REFRESH_MARGIN = 300  # 만료 5분 전 갱신
    TOKEN_FILE = "rest_api_token.json"
    
    # 연속조회 설정
    CONT_YES = "Y"
    CONT_NO = "N"
    
    # WebSocket 설정
    WS_PING_INTERVAL = 30  # 초
    WS_RECONNECT_DELAY = 5  # 초
    WS_MAX_RECONNECT = 10
    
    def __init__(self, is_mock=True, appkey=None, secretkey=None):
        """
        초기화
        
        Args:
            is_mock: 모의투자 여부 (True=모의, False=운영)
            appkey: 앱키
            secretkey: 시크릿키
        """
        self.is_mock = is_mock
        self.appkey = appkey
        self.secretkey = secretkey
        
        # 도메인 설정
        if is_mock:
            self.base_url = self.MOCK_BASE_URL
            self.ws_url = self.MOCK_WS_URL
        else:
            self.base_url = self.PROD_BASE_URL
            self.ws_url = self.PROD_WS_URL
    
    def get_auth_url(self, endpoint):
        """인증 URL 생성"""
        return f"{self.base_url}{endpoint}"
    
    def get_api_url(self, endpoint):
        """API URL 생성"""
        return f"{self.base_url}{endpoint}"
    
    def get_ws_url(self):
        """WebSocket URL 생성"""
        return f"{self.ws_url}{self.WEBSOCKET_URL}"


class RestAPIEndpoints:
    """REST API 엔드포인트 정의"""
    
    # 인증
    TOKEN_ISSUE = "/oauth2/token"
    TOKEN_REVOKE = "/oauth2/revoke"
    
    # 계좌/잔고
    BALANCE_DETAIL = "/api/dostk/opt10085"  # kt00018 계좌평가잔고내역
    DEPOSIT_DETAIL = "/api/dostk/opw00001"  # kt00001 예수금상세현황
    
    # 시세/조회
    STOCK_INFO = "/api/dostk/opt10001"  # ka10001 주식기본정보
    STOCK_QUOTE = "/api/dostk/opt10004"  # ka10004 주식호가
    
    # 차트
    CHART_TICK = "/api/dostk/opt10079"  # ka10079 틱차트
    CHART_MIN = "/api/dostk/opt10080"  # ka10080 분봉차트
    CHART_DAY = "/api/dostk/opt10081"  # ka10081 일봉차트
    CHART_WEEK = "/api/dostk/opt10082"  # ka10082 주봉차트
    CHART_MONTH = "/api/dostk/opt10083"  # ka10083 월봉차트
    
    # 주문
    ORDER_BUY = "/api/dostk/order"  # kt10000 매수주문
    ORDER_SELL = "/api/dostk/order"  # kt10001 매도주문
    ORDER_MODIFY = "/api/dostk/order"  # kt10002 정정주문
    ORDER_CANCEL = "/api/dostk/order"  # kt10003 취소주문
    
    # 조건검색
    CONDITION_LIST = "/api/dostk/condition"  # ka10171 조건검색 목록조회
    CONDITION_SEARCH = "/api/dostk/condition"  # ka10172 조건검색 요청


class RestAPIFieldID:
    """REST API 응답 필드 ID 매핑"""
    
    # 실시간 시세 (0B)
    REAL_STOCK = {
        '20': '체결시간',
        '10': '현재가',
        '11': '전일대비',
        '12': '등락율',
        '25': '전일대비기호',
        '26': '전일거래량대비',
        '27': '매도호가',
        '28': '매수호가',
        '13': '누적거래량',
        '14': '누적거래대금',
        '15': '시가',
        '16': '고가',
        '17': '저가',
    }
    
    # 주문체결 (00)
    REAL_ORDER = {
        '9201': '계좌번호',
        '9001': '종목코드',
        '913': '주문상태',
        '302': '종목명',
        '900': '주문수량',
        '901': '주문가격',
        '902': '미체결수량',
        '903': '체결누계금액',
        '904': '원주문번호',
        '905': '주문구분',
        '908': '주문체결시간',
        '909': '체결번호',
        '910': '체결가',
        '911': '체결량',
    }
    
    # 잔고 (04)
    REAL_BALANCE = {
        '9201': '계좌번호',
        '9001': '종목코드',
        '302': '종목명',
        '10': '현재가',
        '930': '보유수량',
        '931': '매입단가',
        '932': '총매입가',
        '933': '주문가능수량',
        '945': '당일순매수량',
        '946': '매도매수구분',
        '950': '당일총매도손익',
        '8019': '손익율',
    }
    
    # 조건검색 실시간
    REAL_CONDITION = {
        '841': '일련번호',
        '9001': '종목코드',
        '843': '삽입삭제구분',  # I:편입, D:이탈
        '20': '체결시간',
        '907': '매도수구분',
    }
