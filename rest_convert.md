# LIBERANIMO REST API 전환 분석 리포트

## 📋 목차
1. [현재 시스템 분석](#1-현재-시스템-분석)
2. [키움 OpenAPI 의존성 분석](#2-키움-openapi-의존성-분석)
3. [REST API 전환 설계](#3-rest-api-전환-설계)
4. [구현 계획](#4-구현-계획)
5. [예상 작업량 및 난이도](#5-예상-작업량-및-난이도)

---

## 1. 현재 시스템 분석

### 1.1 전체 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                   Main Process                       │
│  - GUI (PyQt5)                                       │
│  - Admin (전략 관리)                                 │
│  - QThread 기반 워커들                                │
│    ├─ ProxyAdmin (prx): API 요청 중개               │
│    ├─ RealReceiver (rcv): 실시간 데이터 수신        │
│    └─ 기타 워커들 (cts, ctu, evl, odc, pri)         │
└─────────────────────────────────────────────────────┘
           ↓ Multiprocessing Queue
┌─────────────────────────────────────────────────────┐
│            Separate Processes                        │
│  ┌───────────────────┐   ┌───────────────────┐     │
│  │  APIServer (api)  │   │  DBMServer (dbm)  │     │
│  │  - 키움 OpenAPI   │   │  - DB 관리        │     │
│  │  - COM 통신       │   │                   │     │
│  └───────────────────┘   └───────────────────┘     │
└─────────────────────────────────────────────────────┘
```

### 1.2 핵심 컴포넌트

#### APIServer (api_server.py)
- **역할**: 키움 OpenAPI와의 모든 통신 담당
- **주요 기능**:
  - 로그인/연결 관리
  - 조건검색 (SendCondition, OnReceiveCondition)
  - 실시간 시세 등록/해제 (SetRealReg/SetRealRemove)
  - TR 데이터 요청 (CommRqData, OnReceiveTRData)
  - 주문 처리 (SendOrder, OnReceiveChejanData)
  - 차트 데이터 조회 (get_chart_data)
  
- **특징**:
  - QAxWidget (ActiveX) 사용
  - 이벤트 기반 (콜백 함수)
  - 별도 Process로 실행 (pythoncom.PumpWaitingMessages)
  - 시뮬레이션 모드 지원 (sim_no: 0=실제, 1=가상, 2/3=키움서버)

#### 통신 구조
```python
# BaseModel을 상속받은 프로세스/스레드 모델
- KiwoomModel: APIServer 실행 (Process + pythoncom)
- ProcessModel: DBMServer 실행
- QMainModel: ProxyAdmin, RealReceiver (QThread)
- ThreadModel: 일반 워커들

# 프로세스 간 통신
shared_qes[name] = {
    'request': multiprocessing.Queue,
    'result': multiprocessing.Queue
}

# 명령 전송
order(target, method, *args)    # 응답 불필요
answer(target, method, *args)   # 응답 필요 (타임아웃 기본 15초)
```

---

## 2. 키움 OpenAPI 의존성 분석

### 2.1 OpenAPI 직접 호출 함수들

| 카테고리 | 함수명 | 용도 | 전환 난이도 |
|---------|--------|------|------------|
| **연결** | CommConnect | 로그인 | ⭐⭐⭐ |
| | GetConnectState | 연결 상태 | ⭐ |
| | GetLoginInfo | 계좌정보 | ⭐ |
| **조회** | CommRqData | TR 요청 | ⭐⭐⭐ |
| | GetCommData | TR 응답 파싱 | ⭐⭐ |
| | GetRepeatCnt | 멀티데이터 개수 | ⭐⭐ |
| | GetCommDataEx | 멀티데이터 | ⭐⭐ |
| **실시간** | SetRealReg | 실시간 등록 | ⭐⭐⭐⭐ |
| | SetRealRemove | 실시간 해제 | ⭐⭐⭐ |
| | GetCommRealData | 실시간 데이터 | ⭐⭐⭐ |
| **주문** | SendOrder | 주문 전송 | ⭐⭐⭐ |
| | GetChejanData | 체결 데이터 | ⭐⭐ |
| **조건검색** | GetConditionLoad | 조건식 로드 | ⭐⭐⭐ |
| | GetConditionNameList | 조건식 목록 | ⭐⭐ |
| | SendCondition | 조건검색 | ⭐⭐⭐⭐ |
| | SendConditionStop | 조건검색 중지 | ⭐⭐⭐ |
| **기타** | GetCodeListByMarket | 종목코드 리스트 | ⭐ |
| | GetMasterCodeName | 종목명 | ⭐ |
| | GetMasterLastPrice | 전일가 | ⭐ |

**난이도 기준**:
- ⭐: 단순 조회, REST API 1:1 매핑 가능
- ⭐⭐: 데이터 변환 필요
- ⭐⭐⭐: 복잡한 요청/응답 처리
- ⭐⭐⭐⭐: 실시간 연결 유지 필요 (WebSocket 등)

### 2.2 이벤트 콜백 함수들

```python
# APIServer 내부 콜백들
OnEventConnect(err_code)              # 로그인 완료
OnReceiveTRData(...)                  # TR 응답
OnReceiveRealData(code, type, data)   # 실시간 데이터
OnReceiveChejanData(gubun, cnt, fid)  # 체결/잔고 데이터
OnReceiveConditionVer(ret, msg)       # 조건식 로드 완료
OnReceiveRealCondition(code, type, cond_name, cond_index)  # 조건검색 실시간
OnReceiveMsg(screen, rqname, trcode, msg)  # 메시지
```

---

## 3. REST API 전환 설계

### 3.1 목표 아키텍처

```
┌─────────────────────────────────────────────────┐
│          LIBERANIMO 메인 프로그램                │
│  - Admin (전략 관리)                             │
│  - 워커 스레드들                                 │
└─────────────────────────────────────────────────┘
           ↓ HTTP/WebSocket (Token 인증)
┌─────────────────────────────────────────────────┐
│         BrokerAPIAdapter (추상 레이어)           │
│  - 증권사 독립적 인터페이스                       │
└─────────────────────────────────────────────────┘
           ↓ 구현체 선택
┌──────────────┬──────────────┬──────────────────┐
│ Kiwoom REST  │ 한투 REST    │ NH 투자 REST     │
│ (KIS API)    │              │                  │
└──────────────┴──────────────┴──────────────────┘
```

### 3.2 추상 인터페이스 설계

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

@dataclass
class BrokerConfig:
    """증권사 설정"""
    broker_name: str
    api_key: str
    api_secret: str
    account_no: str
    base_url: str
    ws_url: Optional[str] = None
    
class BrokerAPIAdapter(ABC):
    """증권사 API 추상 인터페이스"""
    
    # ========== 인증 ==========
    @abstractmethod
    def get_access_token(self) -> str:
        """접근 토큰 발급 (REST API용)"""
        pass
    
    # ========== 계좌/잔고 ==========
    @abstractmethod
    def get_account_info(self) -> Dict:
        """계좌 정보 조회"""
        pass
    
    @abstractmethod
    def get_balance(self) -> List[Dict]:
        """보유 잔고 조회"""
        pass
    
    # ========== 시세 조회 ==========
    @abstractmethod
    def get_current_price(self, code: str) -> Dict:
        """현재가 조회"""
        pass
    
    @abstractmethod
    def get_chart_data(self, code: str, cycle: str, count: int = 100) -> List[Dict]:
        """차트 데이터 조회
        cycle: 'mi'(분), 'dy'(일), 'wk'(주), 'mn'(월)
        """
        pass
    
    # ========== 주문 ==========
    @abstractmethod
    def send_order(self, code: str, order_type: str, qty: int, price: int = 0) -> Dict:
        """주문 전송
        order_type: 'buy_market', 'sell_market', 'buy_limit', 'sell_limit'
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_no: str) -> bool:
        """주문 취소"""
        pass
    
    @abstractmethod
    def modify_order(self, order_no: str, qty: int, price: int) -> bool:
        """주문 정정"""
        pass
    
    @abstractmethod
    def get_orders(self) -> List[Dict]:
        """주문 내역 조회"""
        pass
    
    # ========== 조건검색 (증권사별 지원 여부 상이) ==========
    @abstractmethod
    def get_condition_list(self) -> List[Dict]:
        """조건식 목록"""
        pass
    
    @abstractmethod
    def search_condition(self, condition_name: str) -> List[str]:
        """조건검색 실행 (종목코드 리스트 반환)"""
        pass
    
    # ========== 실시간 데이터 (WebSocket) ==========
    @abstractmethod
    def subscribe_realtime(self, codes: List[str], callback: Callable):
        """실시간 시세 구독"""
        pass
    
    @abstractmethod
    def unsubscribe_realtime(self, codes: List[str]):
        """실시간 시세 구독 해제"""
        pass
    
    @abstractmethod
    def subscribe_order_status(self, callback: Callable):
        """실시간 체결/주문 상태 구독"""
        pass
    
    # ========== 기타 ==========
    @abstractmethod
    def get_market_codes(self, market: str = 'kospi') -> List[str]:
        """시장별 종목코드 리스트
        market: 'kospi', 'kosdaq', 'konex'
        """
        pass
```

### 3.3 키움 REST API (KIS) 구현 예시

```python
import requests
import websocket
import json
from datetime import datetime

class KiwoomRESTAdapter(BrokerAPIAdapter):
    """키움증권 KIS API 구현체"""
    
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.access_token = None
        self.ws_conn = None
        
    def get_access_token(self) -> str:
        """OAuth 토큰 발급"""
        url = f"{self.config.base_url}/oauth2/tokenP"
        data = {
            "grant_type": "client_credentials",
            "appkey": self.config.api_key,
            "appsecret": self.config.api_secret
        }
        response = requests.post(url, json=data)
        result = response.json()
        self.access_token = result['access_token']
        return self.access_token
    
    def _get_headers(self) -> Dict:
        """공통 헤더"""
        if not self.access_token:
            self.get_access_token()
        return {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.config.api_key,
            "appsecret": self.config.api_secret,
            "tr_id": "",  # API별로 설정
        }
    
    def get_balance(self) -> List[Dict]:
        """잔고 조회"""
        url = f"{self.config.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = self._get_headers()
        headers["tr_id"] = "TTTC8434R"  # 실전투자: TTTC8434R, 모의투자: VTTC8434R
        
        params = {
            "CANO": self.config.account_no[:8],
            "ACNT_PRDT_CD": self.config.account_no[8:],
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        # 데이터 변환 (LIBERANIMO 형식으로)
        balance = []
        for item in result.get('output1', []):
            balance.append({
                '종목코드': item['pdno'],
                '종목명': item['prdt_name'],
                '보유수량': int(item['hldg_qty']),
                '매입가': int(item['pchs_avg_pric']),
                '현재가': int(item['prpr']),
                '평가금액': int(item['evlu_amt']),
                '손익금액': int(item['evlu_pfls_amt']),
                '손익률': float(item['evlu_pfls_rt'])
            })
        
        return balance
    
    def send_order(self, code: str, order_type: str, qty: int, price: int = 0) -> Dict:
        """주문 전송"""
        url = f"{self.config.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = self._get_headers()
        
        # 주문 구분 매핑
        order_map = {
            'buy_market': ('TTTC0802U', '01'),  # 시장가 매수
            'buy_limit': ('TTTC0802U', '00'),   # 지정가 매수
            'sell_market': ('TTTC0801U', '01'), # 시장가 매도
            'sell_limit': ('TTTC0801U', '00'),  # 지정가 매도
        }
        
        tr_id, ord_dvsn = order_map[order_type]
        headers["tr_id"] = tr_id
        
        body = {
            "CANO": self.config.account_no[:8],
            "ACNT_PRDT_CD": self.config.account_no[8:],
            "PDNO": code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price) if price > 0 else "0"
        }
        
        response = requests.post(url, headers=headers, json=body)
        result = response.json()
        
        return {
            '주문번호': result['output']['ODNO'],
            '주문시각': result['output']['ORD_TMD'],
            '종목코드': code,
            '주문수량': qty,
            '주문가격': price
        }
    
    def get_chart_data(self, code: str, cycle: str, count: int = 100) -> List[Dict]:
        """차트 데이터 조회"""
        if cycle == 'mi':  # 분봉
            url = f"{self.config.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
            tr_id = "FHKST03010200"
        elif cycle == 'dy':  # 일봉
            url = f"{self.config.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
            tr_id = "FHKST03010100"
        else:
            raise ValueError(f"지원하지 않는 차트 주기: {cycle}")
        
        headers = self._get_headers()
        headers["tr_id"] = tr_id
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": "",
            "FID_INPUT_DATE_2": "",
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        # 데이터 변환
        chart_data = []
        for item in result.get('output2', [])[:count]:
            chart_data.append({
                '종목코드': code,
                '일자' if cycle == 'dy' else '체결시간': item['stck_bsop_date'],
                '시가': int(item['stck_oprc']),
                '고가': int(item['stck_hgpr']),
                '저가': int(item['stck_lwpr']),
                '현재가': int(item['stck_clpr']),
                '거래량': int(item['acml_vol']),
                '거래대금': int(item.get('acml_tr_pbmn', 0))
            })
        
        return chart_data
    
    def subscribe_realtime(self, codes: List[str], callback: Callable):
        """WebSocket 실시간 시세 구독"""
        if not self.ws_conn:
            self.ws_conn = websocket.WebSocketApp(
                self.config.ws_url,
                on_message=lambda ws, msg: self._on_ws_message(msg, callback),
                on_error=lambda ws, err: print(f"WebSocket Error: {err}"),
                on_close=lambda ws: print("WebSocket Closed")
            )
            # 별도 스레드에서 실행
            import threading
            ws_thread = threading.Thread(target=self.ws_conn.run_forever, daemon=True)
            ws_thread.start()
        
        # 구독 메시지 전송
        for code in codes:
            subscribe_msg = {
                "header": {
                    "approval_key": self.access_token,
                    "custtype": "P",
                    "tr_type": "1",
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",  # 주식호가
                        "tr_key": code
                    }
                }
            }
            self.ws_conn.send(json.dumps(subscribe_msg))
    
    def _on_ws_message(self, message, callback):
        """WebSocket 메시지 처리"""
        try:
            data = json.loads(message)
            # 데이터 변환 후 콜백 호출
            parsed_data = self._parse_realtime_data(data)
            callback(parsed_data)
        except Exception as e:
            print(f"WebSocket message parse error: {e}")
    
    def _parse_realtime_data(self, data: Dict) -> Dict:
        """실시간 데이터 파싱"""
        # KIS API 응답을 LIBERANIMO 형식으로 변환
        return {
            '종목코드': data.get('tr_key'),
            '현재가': int(data.get('stck_prpr', 0)),
            '거래량': int(data.get('acml_vol', 0)),
            '체결시간': data.get('stck_cntg_hour'),
            # ... 기타 필드
        }
```

### 3.4 기존 코드 통합 방안

#### 방안 1: 최소 수정 (Adapter 패턴)

```python
# api_server.py 수정 최소화
class APIServer:
    def __init__(self):
        self.sim_no = 0
        self.broker_adapter = None  # 추가
        
    def api_init(self, sim_no, log_level):
        self.sim_no = sim_no
        
        if sim_no == 0:  # REST API 사용
            # 증권사별 Adapter 선택
            broker_config = BrokerConfig(
                broker_name='kiwoom',
                api_key=os.getenv('KIWOOM_API_KEY'),
                api_secret=os.getenv('KIWOOM_API_SECRET'),
                account_no=os.getenv('ACCOUNT_NO'),
                base_url='https://openapi.koreainvestment.com:9443',
                ws_url='ws://ops.koreainvestment.com:21000'
            )
            self.broker_adapter = KiwoomRESTAdapter(broker_config)
            
        elif sim_no == 1:  # 가상 데이터
            self.broker_adapter = SimulationAdapter()
            
        else:  # 기존 OpenAPI (sim_no=2,3)
            self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            # ... 기존 로직
    
    def CommConnect(self, block=True):
        """로그인 - REST와 OpenAPI 모두 지원"""
        if self.sim_no == 0:
            # REST API 로그인
            token = self.broker_adapter.get_access_token()
            self.emit_q.put(QWork(method='on_event_connect', args=(0,)))
        else:
            # 기존 OpenAPI 로직
            self.ocx.dynamicCall("CommConnect()")
            # ...
    
    def api_request(self, rqname, trcode, input_dict, output_list, next='0', screen='0101'):
        """TR 요청 - 통합 인터페이스"""
        if self.sim_no == 0:
            # REST API 변환 로직
            return self._rest_api_request(rqname, trcode, input_dict, output_list)
        else:
            # 기존 OpenAPI 로직
            return self._com_api_request(rqname, trcode, input_dict, output_list, next, screen)
    
    def _rest_api_request(self, rqname, trcode, input_dict, output_list):
        """REST API로 TR 요청 변환"""
        if trcode == 'opt10001':  # 주식기본정보
            code = input_dict['종목코드']
            data = self.broker_adapter.get_current_price(code)
            return ([data], False)
            
        elif trcode == 'opt10080':  # 주식분봉차트
            code = input_dict['종목코드']
            tick = input_dict.get('틱범위', '1')
            data = self.broker_adapter.get_chart_data(code, 'mi', count=900)
            return (data, False)
            
        # ... 기타 TR 매핑
    
    def SendOrder(self, rqname, screen, accno, order_type, code, qty, price, hoga, order_no):
        """주문 - 통합 인터페이스"""
        if self.sim_no == 0:
            # OpenAPI 주문타입을 REST 형식으로 변환
            rest_order_type = self._convert_order_type(order_type, hoga)
            result = self.broker_adapter.send_order(code, rest_order_type, qty, price)
            # 체결 콜백 시뮬레이션
            self._simulate_chejan_callback(result)
        else:
            # 기존 OpenAPI 로직
            self.ocx.dynamicCall("SendOrder(...)")
```

#### 방안 2: 완전 리팩토링

```python
# 새로운 구조
class TradingEngine:
    """매매 엔진 - 증권사 독립적"""
    def __init__(self, broker: BrokerAPIAdapter):
        self.broker = broker
        
    def buy(self, code: str, qty: int, price: int = 0):
        """매수"""
        order_type = 'buy_market' if price == 0 else 'buy_limit'
        return self.broker.send_order(code, order_type, qty, price)
    
    def sell(self, code: str, qty: int, price: int = 0):
        """매도"""
        order_type = 'sell_market' if price == 0 else 'sell_limit'
        return self.broker.send_order(code, order_type, qty, price)
    
    def get_balance(self):
        """잔고 조회"""
        return self.broker.get_balance()

# admin.py 수정
class Admin:
    def __init__(self):
        # 증권사 선택
        broker = self._create_broker_adapter()
        self.engine = TradingEngine(broker)
    
    def _create_broker_adapter(self):
        """설정 파일에서 증권사 선택"""
        config = load_config()
        
        if config['broker'] == 'kiwoom':
            return KiwoomRESTAdapter(config['kiwoom'])
        elif config['broker'] == 'korea_investment':
            return KoreaInvestmentAdapter(config['korea_investment'])
        else:
            raise ValueError(f"지원하지 않는 증권사: {config['broker']}")
```

### 3.5 실시간 데이터 처리

OpenAPI의 실시간 데이터는 **WebSocket**으로 전환이 필요합니다.

```python
class RealtimeManager:
    """실시간 데이터 관리 (증권사 독립적)"""
    
    def __init__(self, broker: BrokerAPIAdapter):
        self.broker = broker
        self.subscriptions = {}  # code -> callback
        
    def subscribe(self, codes: List[str], callback: Callable):
        """실시간 시세 구독"""
        for code in codes:
            self.subscriptions[code] = callback
        
        # 증권사 WebSocket 구독
        self.broker.subscribe_realtime(codes, self._on_realtime_data)
    
    def _on_realtime_data(self, data: Dict):
        """실시간 데이터 수신 콜백"""
        code = data['종목코드']
        if code in self.subscriptions:
            callback = self.subscriptions[code]
            callback(data)
    
    def unsubscribe(self, codes: List[str]):
        """구독 해제"""
        for code in codes:
            self.subscriptions.pop(code, None)
        self.broker.unsubscribe_realtime(codes)
```

---

## 4. 구현 계획

### 4.1 단계별 작업

#### Phase 1: 기반 구축 (1-2주)
- [ ] BrokerAPIAdapter 인터페이스 설계 및 구현
- [ ] 키움 KIS REST API 구현체 개발 (기본 기능)
  - 인증 (OAuth)
  - 잔고 조회
  - 현재가 조회
  - 주문 (매수/매도)
- [ ] 설정 파일 구조 설계 (broker 선택, API 키 관리)
- [ ] 로깅 및 에러 처리

#### Phase 2: 기존 코드 통합 (2-3주)
- [ ] api_server.py Adapter 패턴 적용
- [ ] 주요 TR 요청 매핑
  - opt10001: 주식기본정보
  - opt10080: 주식분봉차트
  - opt10081: 주식일봉차트
  - opw00018: 잔고 조회
- [ ] 주문 로직 통합
  - SendOrder 변환
  - OnReceiveChejanData 콜백 처리
- [ ] 테스트 및 검증

#### Phase 3: 실시간 데이터 (2주)
- [ ] WebSocket 기반 RealtimeManager 구현
- [ ] 기존 SetRealReg/SetRealRemove 로직 변환
- [ ] OnReceiveRealData 콜백 처리
- [ ] 재연결 및 에러 복구 로직

#### Phase 4: 조건검색 (선택사항, 1-2주)
- [ ] 조건검색 API 조사 (증권사별 지원 여부)
- [ ] SendCondition 변환
- [ ] OnReceiveRealCondition 콜백 처리

#### Phase 5: 안정화 및 최적화 (2-3주)
- [ ] 전체 시스템 통합 테스트
- [ ] 성능 최적화 (API 호출 횟수, 응답 시간)
- [ ] 예외 상황 처리 (토큰 만료, API 제한, 네트워크 오류)
- [ ] 시뮬레이션 모드 통합
- [ ] 문서화

#### Phase 6: 다중 증권사 지원 (선택사항, 2-4주)
- [ ] 한국투자증권 Adapter 구현
- [ ] NH투자증권 Adapter 구현
- [ ] 증권사 선택 UI

### 4.2 기술 스택

| 구분 | 현재 (OpenAPI) | 전환 후 (REST) |
|-----|---------------|---------------|
| **통신** | COM/ActiveX | HTTP/WebSocket |
| **인증** | 로그인 세션 | OAuth 2.0 토큰 |
| **요청** | TR + 이벤트 콜백 | REST API |
| **실시간** | SetRealReg 이벤트 | WebSocket |
| **라이브러리** | PyQt5.QAxContainer | requests, websocket-client |
| **프로세스** | pythoncom.PumpWaitingMessages | 표준 Python |

### 4.3 필요 라이브러리

```bash
# 기존
PyQt5
pythoncom
pywin32

# 추가 (REST API용)
requests>=2.31.0
websocket-client>=1.6.0
python-dotenv>=1.0.0  # 환경변수 관리
pydantic>=2.0.0  # 데이터 검증
```

---

## 5. 예상 작업량 및 난이도

### 5.1 작업량 추정

| Phase | 작업 내용 | 예상 기간 | 난이도 |
|-------|---------|----------|--------|
| 1 | 기반 구축 | 1-2주 | ⭐⭐⭐ |
| 2 | 기존 코드 통합 | 2-3주 | ⭐⭐⭐⭐ |
| 3 | 실시간 데이터 | 2주 | ⭐⭐⭐⭐ |
| 4 | 조건검색 | 1-2주 | ⭐⭐⭐ |
| 5 | 안정화 | 2-3주 | ⭐⭐⭐ |
| 6 | 다중 증권사 | 2-4주 | ⭐⭐⭐ |
| **합계** | | **10-16주** | |

### 5.2 주요 난관 및 해결 방안

#### 난관 1: 이벤트 기반 → 요청/응답 기반 전환
**문제**: OpenAPI는 콜백 함수로 비동기 응답을 받지만, REST API는 동기 요청/응답

**해결**:
```python
# 기존 (OpenAPI)
self.ocx.dynamicCall("CommRqData(...)")
# ... 나중에 OnReceiveTRData 콜백에서 처리

# 변경 (REST)
response = self.broker.get_chart_data(code, 'dy')  # 즉시 응답
# 바로 처리 가능
```

#### 난관 2: 실시간 데이터 연결 관리
**문제**: WebSocket 연결 유지, 재연결, 구독 관리

**해결**:
- WebSocket 라이브러리 활용 (자동 재연결 지원)
- 연결 상태 모니터링
- 구독 목록 관리 (연결 끊김 시 자동 재구독)

```python
class WebSocketManager:
    def __init__(self):
        self.ws = None
        self.subscribed_codes = set()
        self.reconnect_delay = 5
        
    def connect(self):
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error
        )
        
    def _on_close(self, ws):
        """연결 끊김 시 재연결"""
        logging.warning("WebSocket closed. Reconnecting...")
        time.sleep(self.reconnect_delay)
        self.connect()
        self._resubscribe_all()  # 구독 복구
```

#### 난관 3: TR 요청 매핑
**문제**: OpenAPI의 수백 개 TR 코드를 REST API로 1:1 매핑 어려움

**해결**:
- 실제 사용하는 TR만 매핑 (우선순위 기반)
- TR 매핑 테이블 작성

```python
TR_MAPPING = {
    'opt10001': 'get_stock_info',      # 주식기본정보
    'opt10080': 'get_minute_chart',    # 분봉
    'opt10081': 'get_daily_chart',     # 일봉
    'opw00018': 'get_balance',         # 잔고
    # ... 실제 사용 TR만 추가
}
```

#### 난관 4: 조건검색 기능
**문제**: 키움의 조건검색은 OpenAPI 고유 기능, REST API 지원 불명확

**해결 방안**:
1. **자체 구현**: DB에 종목 데이터 저장 후 조건 필터링
2. **외부 스크리닝 서비스** 활용
3. **증권사 변경** (조건검색 지원하는 증권사 선택)

### 5.3 리스크 요소

| 리스크 | 확률 | 영향도 | 완화 방안 |
|-------|------|--------|----------|
| API 제한 (Rate Limit) | 높음 | 중간 | TimeLimiter 강화, 캐싱 |
| 실시간 데이터 지연 | 중간 | 높음 | WebSocket 최적화, 모니터링 |
| 조건검색 미지원 | 중간 | 높음 | 대체 방안 준비 |
| 토큰 만료 처리 | 낮음 | 중간 | 자동 갱신 로직 |
| 증권사 API 변경 | 낮음 | 높음 | Adapter 패턴으로 격리 |

---

## 6. 추가 고려사항

### 6.1 성능 비교

| 항목 | OpenAPI | REST API |
|-----|---------|----------|
| **초기 연결** | 느림 (로그인, COM 초기화) | 빠름 (토큰 발급만) |
| **단일 조회** | 중간 | 빠름 |
| **대량 조회** | 제한 많음 | 제한 적음 (증권사 정책에 따름) |
| **실시간 데이터** | 안정적 | WebSocket 연결 관리 필요 |
| **재시작 시간** | 느림 | 빠름 |

### 6.2 보안

```python
# 환경변수로 API 키 관리
# .env 파일
BROKER=kiwoom
KIWOOM_API_KEY=your_app_key
KIWOOM_API_SECRET=your_app_secret
ACCOUNT_NO=12345678-01

# 코드에서 로드
from dotenv import load_dotenv
load_dotenv()

config = {
    'api_key': os.getenv('KIWOOM_API_KEY'),
    'api_secret': os.getenv('KIWOOM_API_SECRET'),
}
```

### 6.3 모니터링 및 로깅

```python
# REST API 호출 로깅
import logging

class BrokerAPILogger:
    @staticmethod
    def log_request(method: str, url: str, params: dict):
        logging.info(f"[API Request] {method} {url} | params={params}")
    
    @staticmethod
    def log_response(status_code: int, data: dict, elapsed: float):
        logging.info(f"[API Response] {status_code} | elapsed={elapsed:.3f}s")
    
    @staticmethod
    def log_error(error: Exception):
        logging.error(f"[API Error] {error}", exc_info=True)
```

### 6.4 비용

| 구분 | OpenAPI | REST API |
|-----|---------|----------|
| **개발비** | - | 컨설팅/외주 시 비용 발생 |
| **API 사용료** | 무료 | 무료 (증권사 계좌 보유 시) |
| **유지보수** | 높음 (이벤트 기반 복잡도) | 낮음 (표준 HTTP) |

---

## 7. 결론 및 권장사항

### 7.1 전환 이점

✅ **안정성 향상**: 이벤트 기반 → 요청/응답, 에러 추적 용이  
✅ **증권사 독립성**: Adapter 패턴으로 증권사 변경 쉬움  
✅ **개발 생산성**: COM 의존성 제거, 표준 Python 라이브러리  
✅ **배포 편의성**: ActiveX 없이 어디서나 실행 가능  
✅ **확장성**: 여러 증권사 동시 사용 가능  

### 7.2 권장 접근 방식

**1단계: 최소 기능 전환 (MVP)**
- 키움 KIS REST API만 지원
- 핵심 기능만 구현 (잔고, 주문, 시세)
- 기존 OpenAPI 코드와 병행 운영 (sim_no로 선택)

**2단계: 안정화**
- 실전 투자로 검증
- 실시간 데이터 최적화
- 예외 처리 강화

**3단계: 확장**
- 다른 증권사 지원
- 조건검색 대체 방안
- 고급 기능 추가

### 7.3 다음 단계

다음 중 선택해주세요:

1. **즉시 구현 시작**: Phase 1부터 코드 작성
2. **상세 설계 먼저**: 특정 증권사 API 선택 후 상세 설계
3. **POC 먼저**: 간단한 기능만 시험 구현 (잔고 조회 + 주문)

어떤 방향으로 진행하시겠습니까?

---

**작성일**: 2025-11-11  
**버전**: 1.0  
**작성자**: Claude
