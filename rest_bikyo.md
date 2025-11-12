# LIBERANIMO 시스템 변경 전후 비교 문서

## 📋 목차
1. [개요](#1-개요)
2. [전체 아키텍처 비교](#2-전체-아키텍처-비교)
3. [컴포넌트별 상세 비교](#3-컴포넌트별-상세-비교)
4. [코드 구조 비교](#4-코드-구조-비교)
5. [실행 흐름 비교](#5-실행-흐름-비교)
6. [기술 스택 비교](#6-기술-스택-비교)
7. [장단점 비교](#7-장단점-비교)
8. [마이그레이션 계획](#8-마이그레이션-계획)

---

## 1. 개요

### 1.1 변경 목적
- 키움 OpenAPI(ActiveX) → REST API 전환
- 안정성 향상 (이벤트 기반 → 요청/응답 기반)
- 증권사 독립성 확보 (Adapter 패턴)
- 에러 추적 및 디버깅 용이성 개선

### 1.2 변경 범위
| 구분 | 변경 여부 | 비고 |
|-----|----------|------|
| **조건검색** | 유지 (별도 모듈) | OpenAPI 사용 유지 |
| **주문/조회** | 전환 | REST API로 변경 |
| **실시간 시세** | 전환 | WebSocket으로 변경 |
| **전략 로직** | 유지 | Strategy 클래스 재사용 |
| **잔고 관리** | 부분 유지 | Portfolio 로직 재사용 |
| **데이터베이스** | 유지 | DBMServer 재사용 |
| **GUI** | 부분 수정 | 이벤트 연결만 수정 |

---

## 2. 전체 아키텍처 비교

### 2.1 변경 전 (Current)

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Process (QThread)                    │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │   GUI    │  Admin   │   prx    │   rcv    │  기타    │  │
│  │ (PyQt5)  │ (전략관리)│ (Proxy)  │(Receiver)│ (cts등)  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│         ↓ multiprocessing.Queue                             │
└─────────────────────────────────────────────────────────────┘
         ↓                                    ↓
┌────────────────────────┐    ┌────────────────────────┐
│   APIServer Process    │    │   DBMServer Process    │
│  ┌──────────────────┐  │    │  ┌──────────────────┐  │
│  │ QAxWidget        │  │    │  │ Database         │  │
│  │ (ActiveX COM)    │  │    │  │ Operations       │  │
│  │                  │  │    │  └──────────────────┘  │
│  │ - CommConnect    │  │    └────────────────────────┘
│  │ - CommRqData     │  │
│  │ - SendOrder      │  │
│  │ - SendCondition  │  │    ┌────────────────────────┐
│  │ - SetRealReg     │  │    │   키움 OpenAPI 서버    │
│  │                  │◄─┼────┤   (COM 통신)          │
│  │ OnReceiveTRData  │  │    └────────────────────────┘
│  │ OnReceiveReal    │  │
│  │ OnReceiveChejan  │  │
│  │ OnReceiveCond... │  │
│  └──────────────────┘  │
└────────────────────────┘

특징:
- Multiprocessing + QThread 혼합
- 이벤트 기반 콜백 시스템
- COM/ActiveX 의존성
- pythoncom.PumpWaitingMessages 필요
- Windows 전용
```

### 2.2 변경 후 (New)

```
┌────────────────────────────────────────────────────────────┐
│              ConditionSearchModule (별도 프로세스)          │
│  ┌───────────────────────────────────────────────────┐    │
│  │ QAxWidget (조건검색만 사용)                        │    │
│  │ - SendCondition (실시간 조건검색)                  │    │
│  │ - OnReceiveRealCondition                          │    │
│  └───────────────────────────────────────────────────┘    │
│         ↓ Redis Pub/Sub (종목코드만 전달)                  │
└────────────────────────────────────────────────────────────┘
         ↓ {'code': '005930', 'event': 'I', 'condition': '돌파'}
┌────────────────────────────────────────────────────────────┐
│                   Main Application                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ TradingEngine                                        │  │
│  │  - Redis 구독 (조건 시그널 수신)                     │  │
│  │  - BrokerAPI (REST) 사용                            │  │
│  │  - Portfolio 관리                                    │  │
│  │  - Strategy 실행                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│         ↓ HTTP/WebSocket                                   │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│         BrokerAPI (추상 인터페이스)                         │
│  ┌──────────────┬──────────────┬──────────────┐          │
│  │ KiwoomAPI    │ KoreaInvAPI  │ NHAPI        │          │
│  │ (REST)       │ (REST)       │ (REST)       │          │
│  └──────────────┴──────────────┴──────────────┘          │
└────────────────────────────────────────────────────────────┘
         ↓ HTTPS / WebSocket
┌────────────────────────────────────────────────────────────┐
│              증권사 REST API 서버                           │
│  - 키움 KIS / 한투 / NH 등                                 │
└────────────────────────────────────────────────────────────┘

특징:
- 단순한 Thread 기반
- 요청/응답 기반 (명확한 흐름)
- REST API + WebSocket
- 증권사 독립적 (Adapter 패턴)
- 크로스 플랫폼 가능
```

---

## 3. 컴포넌트별 상세 비교

### 3.1 API 통신 계층

#### 변경 전: APIServer (api_server.py)

```python
class APIServer:
    """OpenAPI 전체 기능 담당"""
    
    def __init__(self):
        # ActiveX 초기화
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        
        # 이벤트 연결 (40+ 콜백)
        self.ocx.OnEventConnect.connect(self._on_connect)
        self.ocx.OnReceiveTRData.connect(self._on_receive_tr)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real)
        self.ocx.OnReceiveChejanData.connect(self._on_chejan)
        self.ocx.OnReceiveConditionVer.connect(self._on_cond_ver)
        self.ocx.OnReceiveRealCondition.connect(self._on_real_cond)
        self.ocx.OnReceiveTrCondition.connect(self._on_tr_cond)
        self.ocx.OnReceiveMsg.connect(self._on_msg)
        # ... 더 많은 콜백
        
        self.tr_request_queue = {}  # 요청 추적
        self.screen_no = 0
    
    def CommConnect(self, block=True):
        """로그인 요청"""
        self.ocx.dynamicCall("CommConnect()")
        # 응답은 나중에 _on_connect 콜백으로
    
    def _on_connect(self, err_code):
        """로그인 응답 (비동기 콜백)"""
        if err_code == 0:
            logging.info("로그인 성공")
            # emit signal로 메인에 알림
        else:
            logging.error(f"로그인 실패: {err_code}")
    
    def CommRqData(self, rqname, trcode, next, screen):
        """TR 요청"""
        self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            rqname, trcode, next, screen
        )
        # 응답은 나중에 _on_receive_tr 콜백으로
    
    def _on_receive_tr(self, screen, rqname, trcode, 
                       record, prev_next, data_len, err_code, msg, splm_msg):
        """TR 응답 (비동기 콜백)"""
        # 어떤 요청에 대한 응답인지 screen으로 매칭
        # 데이터 파싱
        # emit signal로 결과 전달
    
    def SendOrder(self, rqname, screen, accno, order_type, 
                  code, qty, price, hoga, order_no):
        """주문 요청"""
        ret = self.ocx.dynamicCall(
            "SendOrder(...)",
            rqname, screen, accno, order_type, 
            code, qty, price, hoga, order_no
        )
        # 체결 결과는 _on_chejan 콜백으로
    
    def _on_chejan(self, gubun, item_cnt, fid_list):
        """체결 응답 (비동기 콜백)"""
        # FID 값 파싱
        # emit signal로 결과 전달
    
    def SendCondition(self, screen, cond_name, cond_index, search_type):
        """조건검색 요청"""
        ret = self.ocx.dynamicCall(
            "SendCondition(QString, QString, int, int)",
            screen, cond_name, cond_index, search_type
        )
        # 결과는 _on_real_cond 콜백으로
    
    def _on_real_cond(self, code, type, cond_name, cond_index):
        """실시간 조건검색 응답 (비동기 콜백)"""
        # emit signal로 결과 전달

# 사용 예시 (복잡!)
gm.prx.order('api', 'CommRqData', 'opt10001', {...})
# → ProxyAdmin → Queue → APIServer → 키움서버
# ← _on_receive_tr ← Queue ← ProxyAdmin ← emit signal
# → Admin에서 처리
```

**문제점**:
- ❌ 이벤트 기반 비동기 처리 (추적 어려움)
- ❌ 요청과 응답 매칭 복잡 (screen 번호 관리)
- ❌ 에러 처리 불명확 (어디서 실패했는지 모름)
- ❌ 멀티프로세스 큐 통신 오버헤드
- ❌ COM 스레드 관리 (pythoncom.PumpWaitingMessages)

#### 변경 후: BrokerAPI

```python
# broker/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class Balance:
    code: str
    name: str
    quantity: int
    avg_price: int
    current_price: int

@dataclass
class Order:
    order_no: str
    code: str
    quantity: int
    price: int
    status: str

class BrokerAPI(ABC):
    """증권사 독립적 인터페이스"""
    
    @abstractmethod
    def get_balance(self) -> List[Balance]:
        """잔고 조회 - 동기 호출, 즉시 결과 리턴"""
        pass
    
    @abstractmethod
    def send_order(self, code: str, order_type: str, 
                   qty: int, price: int = 0) -> Order:
        """주문 - 동기 호출, 즉시 결과 리턴"""
        pass
    
    @abstractmethod
    def get_current_price(self, code: str) -> dict:
        """현재가 조회 - 동기 호출, 즉시 결과 리턴"""
        pass


# broker/kiwoom.py
import requests
from typing import List

class KiwoomAPI(BrokerAPI):
    """키움증권 REST API 구현"""
    
    def __init__(self, app_key: str, app_secret: str, account: str):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = app_key
        self.app_secret = app_secret
        self.account = account
        self.token = None
        
        # 인증 (생성자에서 즉시)
        self._authenticate()
    
    def _authenticate(self):
        """OAuth 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        response = requests.post(url, json={
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        })
        
        if response.status_code == 200:
            self.token = response.json()['access_token']
            logging.info("인증 성공")
        else:
            raise Exception(f"인증 실패: {response.text}")
    
    def get_balance(self) -> List[Balance]:
        """잔고 조회 - 동기 호출"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        
        headers = {
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R"
        }
        
        params = {
            "CANO": self.account[:8],
            "ACNT_PRDT_CD": self.account[8:],
            "AFHR_FLPR_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        # 에러 처리 명확
        if response.status_code != 200:
            raise Exception(f"잔고 조회 실패: {response.text}")
        
        data = response.json()
        
        # 즉시 결과 리턴
        return [
            Balance(
                code=item['pdno'],
                name=item['prdt_name'],
                quantity=int(item['hldg_qty']),
                avg_price=int(item['pchs_avg_pric']),
                current_price=int(item['prpr'])
            )
            for item in data['output1']
        ]
    
    def send_order(self, code: str, order_type: str, 
                   qty: int, price: int = 0) -> Order:
        """주문 - 동기 호출"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        headers = self._get_headers("TTTC0802U")  # 매수
        
        body = {
            "CANO": self.account[:8],
            "ACNT_PRDT_CD": self.account[8:],
            "PDNO": code,
            "ORD_DVSN": "01" if price == 0 else "00",  # 시장가/지정가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price)
        }
        
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code != 200:
            raise Exception(f"주문 실패: {response.text}")
        
        result = response.json()
        
        # 즉시 결과 리턴
        return Order(
            order_no=result['output']['ODNO'],
            code=code,
            quantity=qty,
            price=price,
            status='접수'
        )

# 사용 예시 (단순!)
broker = KiwoomAPI(app_key, app_secret, account)

# 잔고 조회 - 바로 결과 받음!
balance = broker.get_balance()
for item in balance:
    print(f"{item.code}: {item.quantity}주")

# 주문 - 바로 결과 받음!
try:
    order = broker.send_order('005930', 'buy', 10, 0)
    print(f"주문 성공: {order.order_no}")
except Exception as e:
    print(f"주문 실패: {e}")  # 명확한 에러 메시지
```

**개선점**:
- ✅ 동기 요청/응답 (명확한 흐름)
- ✅ 에러 처리 명확 (try/except)
- ✅ 요청과 응답 매칭 불필요
- ✅ 큐 통신 제거 (직접 호출)
- ✅ COM 스레드 제거

---

### 3.2 조건검색 모듈

#### 변경 전: APIServer 내부 기능

```python
# api_server.py 내부
class APIServer:
    def __init__(self):
        self.ocx = QAxWidget(...)
        self.ocx.OnReceiveRealCondition.connect(self._on_real_cond)
        # 다른 40+ 기능과 섞여있음
    
    def SendCondition(...):
        # 조건검색
        pass
    
    def _on_real_cond(self, code, type, cond_name, cond_index):
        # 조건 만족 종목
        # → emit signal → Queue → ProxyAdmin → Admin → Strategy
        pass

# admin.py에서 사용
class Admin:
    def init(self):
        # 복잡한 큐 통신
        gm.prx.order('api', 'SendCondition', ...)
```

**문제점**:
- ❌ 다른 기능과 섞여 있음
- ❌ 복잡한 큐 통신
- ❌ 재시작 시 전체 영향

#### 변경 후: 독립 모듈

```python
# condition_search_module.py (완전 독립)
import redis
import json

class ConditionSearchModule:
    """조건검색 전용 - 완전 독립"""
    
    def __init__(self, redis_host='localhost'):
        # Redis 연결만
        self.redis_client = redis.Redis(host=redis_host)
        
        # OpenAPI (조건검색만)
        self.app = QApplication(sys.argv)
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnReceiveRealCondition.connect(self._on_condition_hit)
    
    def start_condition(self, condition_index: str):
        """조건검색 시작"""
        self.ocx.dynamicCall("SendCondition(...)")
    
    def _on_condition_hit(self, code, event_type, cond_name, cond_index):
        """조건 만족 시 Redis로 발행"""
        message = {
            'code': code,
            'event_type': event_type,
            'condition_name': cond_name
        }
        
        # Redis Pub/Sub으로 발행 (단순!)
        self.redis_client.publish(
            f"condition:{cond_index}", 
            json.dumps(message)
        )
    
    def run(self):
        """독립 실행"""
        sys.exit(self.app.exec_())

# 독립 실행
if __name__ == "__main__":
    module = ConditionSearchModule()
    module.start_condition("100")
    module.run()
```

```python
# trading_engine.py (수신측)
class TradingEngine:
    def __init__(self, broker: BrokerAPI):
        self.broker = broker
        
        # Redis 구독 (단순!)
        self.redis_client = redis.Redis()
        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe('condition:100')
        
        # 구독 스레드
        threading.Thread(target=self._listen, daemon=True).start()
    
    def _listen(self):
        """조건 결과 수신"""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                self._handle_signal(data)
    
    def _handle_signal(self, signal):
        """시그널 처리"""
        code = signal['code']
        
        # REST로 현재가 조회 (단순!)
        price = self.broker.get_current_price(code)
        
        # REST로 주문 (단순!)
        if self._should_buy(code, price):
            order = self.broker.send_order(code, 'buy', 10)
```

**개선점**:
- ✅ 완전 독립 모듈
- ✅ 단순한 통신 (Redis Pub/Sub)
- ✅ 독립 재시작 가능
- ✅ 매매 로직과 분리

---

### 3.3 전략 실행

#### 변경 전: Admin 클래스

```python
# admin.py (복잡!)
class Admin:
    def __init__(self):
        self.strategies = []
        self.portfolio = {}
        self.real_data = {}
        # 많은 전역 상태
    
    def stg_start(self):
        """전략 시작"""
        for strategy in self.strategies:
            # 큐로 API 서버에 요청
            gm.prx.order('api', 'SetRealReg', ...)
    
    def on_receive_real_data(self, code, data):
        """실시간 데이터 수신 (emit signal)"""
        # 복잡한 이벤트 처리
        self.real_data[code] = data
        
        # 전략 평가
        for strategy in self.strategies:
            signal = strategy.evaluate(code, data)
            if signal:
                # 큐로 주문 요청
                gm.prx.order('api', 'SendOrder', ...)
```

#### 변경 후: TradingEngine

```python
# trading_engine.py (단순!)
class TradingEngine:
    def __init__(self, broker: BrokerAPI):
        self.broker = broker  # 직접 호출
        self.portfolio = Portfolio()
        self.strategies = []
        
        # Redis 구독 (조건검색 결과)
        self.pubsub = redis.Redis().pubsub()
        self.pubsub.subscribe('condition:100')
        
        threading.Thread(target=self._listen, daemon=True).start()
    
    def add_strategy(self, strategy):
        """전략 추가"""
        self.strategies.append(strategy)
    
    def _listen(self):
        """조건검색 결과 수신"""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                self._handle_condition_signal(data)
    
    def _handle_condition_signal(self, signal):
        """조건 시그널 처리"""
        code = signal['code']
        
        # 1. 현재가 조회 (직접 호출!)
        price = self.broker.get_current_price(code)
        
        # 2. 전략 평가
        for strategy in self.strategies:
            action = strategy.should_trade(code, price)
            
            if action == 'buy':
                # 3. 주문 (직접 호출!)
                try:
                    order = self.broker.send_order(
                        code=code,
                        order_type='buy_market',
                        quantity=10
                    )
                    logging.info(f"매수 성공: {order}")
                except Exception as e:
                    logging.error(f"매수 실패: {e}")
    
    def run(self):
        """메인 루프"""
        while True:
            # 주기적 작업
            self.update_portfolio()
            time.sleep(10)
    
    def update_portfolio(self):
        """잔고 업데이트"""
        balance = self.broker.get_balance()  # 직접 호출!
        self.portfolio.update(balance)
```

**개선점**:
- ✅ 명확한 실행 흐름 (한 파일에서 추적 가능)
- ✅ 직접 호출 (큐 제거)
- ✅ 명확한 에러 처리
- ✅ 단순한 구조

---

## 4. 코드 구조 비교

### 4.1 파일 구조

#### 변경 전
```
liberanimo/
├── aaa.py                 # 메인 진입점 (복잡한 초기화)
├── admin.py              # 전략 관리 (56KB, 1500+ 줄)
├── api_server.py         # OpenAPI 전체 (72KB, 1600+ 줄)
├── classes.py            # 복잡한 모델 클래스들
├── threads.py            # 다양한 워커 스레드
├── gui.py                # GUI (복잡한 시그널 처리)
├── public.py             # 공용 변수/함수
├── tables.py             # DB 테이블
├── dbm_server.py         # DB 서버
└── chart.py              # 차트 관련

특징:
- 거대한 파일들 (api_server.py 1600줄)
- 기능이 여러 파일에 분산
- 복잡한 의존성
```

#### 변경 후
```
liberanimo/
├── main.py                              # 메인 진입점 (단순)
│
├── condition_search_module.py           # 조건검색 모듈 (독립)
│
├── trading_engine.py                    # 매매 엔진 (핵심)
│
├── broker/                              # 증권사 API (독립)
│   ├── __init__.py
│   ├── base.py                         # 인터페이스
│   ├── kiwoom.py                       # 키움 구현
│   ├── korea_investment.py             # 한투 구현
│   └── factory.py                      # 팩토리
│
├── portfolio.py                         # 잔고 관리 (기존 활용)
│
├── strategies/                          # 전략들 (기존 활용)
│   ├── __init__.py
│   ├── base.py
│   ├── breakout_strategy.py
│   └── trend_strategy.py
│
├── database/                            # DB (기존 활용)
│   ├── __init__.py
│   ├── dbm_server.py
│   └── tables.py
│
├── gui/                                 # GUI (부분 수정)
│   ├── __init__.py
│   ├── main_window.py
│   └── widgets.py
│
├── utils/                               # 유틸리티
│   ├── __init__.py
│   ├── logger.py
│   └── config.py
│
├── config.yaml                          # 설정 파일
└── requirements.txt

특징:
- 명확한 모듈 분리
- 작은 파일들 (200-300줄)
- 단순한 의존성
- 증권사 독립적
```

### 4.2 실행 방법 비교

#### 변경 전
```bash
# 한 번에 실행 (모든 기능 포함)
python aaa.py

# 또는 시뮬레이션
python aaa.py sim1
python aaa.py sim2 off

# 문제점:
# - 전체가 하나의 덩어리
# - 부분 재시작 불가
# - GUI 없이 실행 어려움
```

#### 변경 후
```bash
# 1. Redis 실행 (한 번만)
redis-server

# 2. 조건검색 모듈 (독립 실행)
python condition_search_module.py

# 3. 매매 엔진 (독립 실행)
python trading_engine.py --config config.yaml

# 4. GUI (선택적)
python gui/main_window.py

# 장점:
# - 모듈별 독립 실행
# - 부분 재시작 가능
# - GUI 없이 실행 가능
# - 여러 매매 엔진 동시 실행 가능
```

---

## 5. 실행 흐름 비교

### 5.1 잔고 조회 시나리오

#### 변경 전
```
[Admin]
  ↓ gm.prx.order('api', 'opw00018', {...})
[ProxyAdmin QThread]
  ↓ multiprocessing.Queue.put(QData(...))
[APIServer Process]
  ↓ ocx.dynamicCall("CommRqData", "opw00018", ...)
[키움 OpenAPI 서버]
  ... (네트워크 통신)
  ↓ OnReceiveTRData (비동기 콜백)
[APIServer Process]
  ↓ 데이터 파싱
  ↓ multiprocessing.Queue.put(result)
[ProxyAdmin QThread]
  ↓ emit_q.put(QWork(...))
  ↓ receive_signal.emit(...)
[Admin]
  ↓ on_receive_signal(...)
  ↓ 데이터 처리

총 8단계, 3개 프로세스/스레드, 2개 큐
소요 시간: ~500ms
```

#### 변경 후
```
[TradingEngine]
  ↓ balance = broker.get_balance()
[KiwoomAPI]
  ↓ requests.get(url, headers, params)
[키움 REST API 서버]
  ... (네트워크 통신)
  ↓ HTTP 200 응답
[KiwoomAPI]
  ↓ 데이터 파싱 및 리턴
[TradingEngine]
  ↓ 데이터 처리

총 3단계, 1개 스레드, 0개 큐
소요 시간: ~100ms
```

**개선**:
- ⚡ 5배 빠름 (큐 오버헤드 제거)
- 🔍 추적 용이 (단순한 스택 트레이스)
- 🐛 디버깅 쉬움 (한 곳에서 중단점)

### 5.2 주문 실행 시나리오

#### 변경 전
```python
# admin.py
def execute_order(self, code, qty):
    # 1. API 서버에 주문 요청
    gm.prx.order('api', 'SendOrder', 
                 rqname, screen, accno, order_type,
                 code, qty, price, hoga, order_no)
    
    # ... (여기서는 아무 응답 없음)
    
    # 2. 나중에 체결 콜백
    def on_receive_chejan(self, gubun, data):
        # 어떤 주문인지 매칭 필요
        if gubun == '0':  # 주문체결
            # 데이터 파싱
            # 처리
        pass

# 문제:
# - 요청과 응답이 분리
# - 중간에 실패해도 모름
# - 어떤 주문의 체결인지 추적 어려움
```

#### 변경 후
```python
# trading_engine.py
def execute_order(self, code, qty):
    try:
        # 1. 주문 실행 (바로 결과)
        order = self.broker.send_order(
            code=code,
            order_type='buy_market',
            quantity=qty
        )
        
        # 2. 주문번호 받음 (즉시)
        logging.info(f"주문 접수: {order.order_no}")
        
        # 3. 체결 확인은 별도 WebSocket
        self.broker.subscribe_order_status(
            callback=lambda status: self._on_order_status(order.order_no, status)
        )
        
        return order
        
    except Exception as e:
        # 명확한 에러 처리
        logging.error(f"주문 실패: {code} {qty}주 - {e}")
        return None

# 장점:
# - 요청과 응답이 연결됨
# - 즉시 에러 확인 가능
# - 주문 추적 명확
```

### 5.3 조건검색 시나리오

#### 변경 전
```
[APIServer]
  ↓ SendCondition("돌파매수", 100, 1)
  ↓ (실시간 모니터링 시작)
  ...
  ↓ OnReceiveRealCondition (종목 편입/이탈)
[APIServer]
  ↓ emit_q.put(...)
[ProxyAdmin]
  ↓ receive_signal.emit(...)
[Admin]
  ↓ on_receive_real_condition(...)
  ↓ gm.prx.order('api', 'GetCommData', ...)  # 현재가 조회
  ...
  ↓ OnReceiveTRData
  ↓ 다시 큐 통신
  ↓ 주문

복잡한 큐 통신, 여러 단계
```

#### 변경 후
```
[ConditionSearchModule]
  ↓ SendCondition("돌파매수", 100, 1)
  ↓ (실시간 모니터링 시작)
  ...
  ↓ OnReceiveRealCondition (종목 편입/이탈)
[ConditionSearchModule]
  ↓ redis.publish("condition:100", {"code": "005930", "event": "I"})

[TradingEngine] (완전 별도)
  ↓ redis message 수신
  ↓ broker.get_current_price("005930")  # REST 직접 호출
  ↓ broker.send_order("005930", "buy", 10)  # REST 직접 호출

완전 분리, 단순한 통신
```

---

## 6. 기술 스택 비교

### 6.1 의존성

#### 변경 전
```python
# requirements.txt
PyQt5==5.15.9
pywin32==306         # Windows 전용
pythoncom            # Windows 전용
QAxContainer         # Windows 전용 ActiveX
pandas
numpy
sqlalchemy

# 특징:
# - Windows 전용
# - ActiveX/COM 의존
# - PyQt5 필수
```

#### 변경 후
```python
# requirements.txt
requests>=2.31.0
websocket-client>=1.6.0
redis>=5.0.0
python-dotenv>=1.0.0
pydantic>=2.5.0
pandas
numpy
sqlalchemy

# 선택적:
PyQt5>=5.15.9        # GUI 사용 시만

# 특징:
# - 크로스 플랫폼
# - 표준 HTTP/WebSocket
# - GUI 선택적
```

### 6.2 실행 환경

| 항목 | 변경 전 | 변경 후 |
|-----|---------|---------|
| **OS** | Windows만 | Windows / Linux / Mac |
| **Python** | 3.8+ | 3.8+ |
| **GUI** | 필수 (PyQt5) | 선택적 |
| **추가 서비스** | 없음 | Redis |
| **배포** | exe (PyInstaller) | Docker / 바이너리 |
| **원격 실행** | 어려움 | 쉬움 (SSH) |

### 6.3 프로세스 모델

#### 변경 전
```
Main Process (PyQt5)
├── GUI Thread
├── Admin Thread
├── ProxyAdmin QThread
├── RealReceiver QThread
├── 기타 QThread들 (5+)
└── Multiprocessing
    ├── APIServer Process (pythoncom)
    └── DBMServer Process

복잡도: ⭐⭐⭐⭐⭐
```

#### 변경 후
```
ConditionSearch Process (독립)
└── PyQt5 Thread (조건검색만)

Main Process
├── TradingEngine Thread
├── Redis Subscribe Thread
└── WebSocket Thread (선택)

DBM Process (기존 활용)

복잡도: ⭐⭐
```

---

## 7. 장단점 비교

### 7.1 변경 전 장점
| 장점 | 설명 |
|-----|------|
| ✅ 완성도 | 이미 구축되어 운영 중 |
| ✅ 조건검색 | HTS 조건식 그대로 사용 가능 |
| ✅ 안정성 | 오랜 검증 기간 |
| ✅ 시뮬레이션 | sim1/2/3 모드 지원 |

### 7.2 변경 전 단점
| 단점 | 설명 | 영향도 |
|-----|------|--------|
| ❌ 복잡도 | 이벤트 기반, 멀티프로세스/스레드 | 높음 |
| ❌ 디버깅 | 큐 통신, 비동기 콜백 추적 어려움 | 높음 |
| ❌ 에러 추적 | 어디서 실패했는지 불명확 | 높음 |
| ❌ 증권사 종속 | 키움 전용, 변경 불가 | 중간 |
| ❌ Windows 전용 | ActiveX/COM | 중간 |
| ❌ 재시작 | 전체 재시작 필요 | 중간 |
| ❌ 확장성 | 새 기능 추가 어려움 | 중간 |

### 7.3 변경 후 장점
| 장점 | 설명 | 영향도 |
|-----|------|--------|
| ✅ 단순성 | 요청/응답, 직접 호출 | 높음 |
| ✅ 디버깅 | 명확한 스택 트레이스 | 높음 |
| ✅ 에러 추적 | try/except 명확 | 높음 |
| ✅ 증권사 독립 | Adapter 패턴, 전환 쉬움 | 높음 |
| ✅ 크로스 플랫폼 | Linux/Mac 가능 | 중간 |
| ✅ 모듈 재시작 | 부분 재시작 가능 | 중간 |
| ✅ 확장성 | 새 증권사 추가 쉬움 | 중간 |
| ✅ 테스트 | Mock 사용 가능 | 중간 |

### 7.4 변경 후 단점
| 단점 | 설명 | 완화 방안 |
|-----|------|----------|
| ⚠️ 조건검색 | OpenAPI 여전히 필요 | 별도 모듈로 격리 |
| ⚠️ 구현 시간 | 새로 작성 필요 | 단계별 전환 |
| ⚠️ Redis 의존 | 추가 서비스 필요 | Docker로 간단히 |
| ⚠️ 학습 곡선 | REST API 학습 | 문서화 충실 |

---

## 8. 마이그레이션 계획

### 8.1 전환 전략

**접근법**: **점진적 전환** (Big Bang X)

```
Phase 1: 기반 구축 (2주)
└── BrokerAPI 인터페이스 + KiwoomAPI 구현

Phase 2: 조건검색 분리 (1주)
└── ConditionSearchModule 독립 실행

Phase 3: 매매 엔진 전환 (2주)
└── TradingEngine REST 기반 재작성

Phase 4: 전략 연결 (1주)
└── 기존 Strategy 클래스 연결

Phase 5: 병행 운영 (2주)
├── 기존 시스템 (검증용)
└── 새 시스템 (소액 운영)

Phase 6: 완전 전환 (1주)
└── 기존 시스템 종료
```

### 8.2 단계별 작업

#### Phase 1: 기반 구축

```python
# 목표: REST API 기본 기능 구현

작업:
1. broker/base.py - BrokerAPI 인터페이스 작성
2. broker/kiwoom.py - 키움 REST 구현
   - 인증 (OAuth)
   - 잔고 조회
   - 현재가 조회
   - 주문 (매수/매도)
3. 테스트 코드 작성
4. 로깅 및 에러 처리

검증:
- 잔고 조회 성공
- 주문 실행 성공
- 에러 처리 동작 확인
```

#### Phase 2: 조건검색 분리

```python
# 목표: 조건검색을 독립 모듈로

작업:
1. condition_search_module.py 작성
2. Redis Pub/Sub 연결
3. 기존 조건식 로드 및 실행
4. 독립 실행 테스트

검증:
- 조건 편입 시 Redis 메시지 발행 확인
- 기존 조건식 정상 동작
```

#### Phase 3: 매매 엔진 전환

```python
# 목표: TradingEngine REST 기반 구현

작업:
1. trading_engine.py 작성
2. Redis 구독 및 시그널 처리
3. Portfolio 통합
4. 주문 실행 로직

검증:
- 조건검색 → 매매 연결 확인
- 주문 실행 정상 동작
```

#### Phase 4: 전략 연결

```python
# 목표: 기존 Strategy 클래스 재사용

작업:
1. 기존 Strategy 인터페이스 분석
2. TradingEngine과 연결
3. 전략별 테스트

검증:
- 기존 전략 정상 동작
- 신규 전략 추가 가능
```

#### Phase 5: 병행 운영

```
목표: 안정성 검증

작업:
1. 기존 시스템 + 새 시스템 동시 실행
2. 소액으로 실거래 테스트
3. 로그 비교 및 이상 징후 모니터링

기간: 2주

검증 기준:
- 주문 실행률 >95%
- 에러율 <1%
- 조건검색 일치율 100%
```

#### Phase 6: 완전 전환

```
목표: 기존 시스템 종료

작업:
1. 새 시스템으로 완전 전환
2. 기존 코드 백업
3. 문서화 완료

검증:
- 1주일 안정 운영
- 모든 기능 정상 동작
```

### 8.3 롤백 계획

만약 문제 발생 시:

```
Level 1: 소프트 롤백 (1시간 이내)
└── 기존 시스템으로 즉시 전환
    새 시스템 중지

Level 2: 하드 롤백 (1일 이내)
└── 새 시스템 제거
    기존 시스템 재배포

Level 3: 부분 롤백
└── 조건검색만 기존 시스템 사용
    매매는 새 시스템 유지
```

### 8.4 데이터 마이그레이션

```
기존 데이터베이스:
- tables.py의 테이블 구조 유지
- 데이터 그대로 사용

추가 테이블:
- broker_config: 증권사 설정
- api_logs: REST API 호출 로그
- order_history: 주문 이력 (상세)
```

### 8.5 테스트 계획

```python
# 1. 단위 테스트
tests/
├── test_broker_api.py
├── test_trading_engine.py
├── test_portfolio.py
└── test_strategies.py

# 2. 통합 테스트
tests/integration/
├── test_condition_to_order.py
├── test_order_flow.py
└── test_realtime_data.py

# 3. 시뮬레이션 테스트
- 과거 데이터로 백테스트
- 가상 주문 실행
- 성능 측정

# 4. 실전 테스트
- 소액 실거래 (1주씩)
- 로그 비교
- 이상 징후 모니터링
```

---

## 9. 리스크 및 대응

### 9.1 주요 리스크

| 리스크 | 확률 | 영향도 | 대응 방안 |
|-------|------|--------|----------|
| REST API 기능 부족 | 중 | 높음 | 하이브리드 방식 유지 |
| 전환 중 버그 | 높음 | 중 | 병행 운영 기간 충분히 |
| 성능 저하 | 낮음 | 중 | 성능 테스트 선행 |
| 조건검색 불안정 | 중 | 높음 | 독립 모듈로 격리 |
| 증권사 API 변경 | 낮음 | 중 | Adapter 패턴으로 격리 |

### 9.2 성공 기준

```
필수 (Must Have):
✅ 기존 기능 100% 동작
✅ 주문 실행률 >95%
✅ 에러율 <1%
✅ 조건검색 정확도 100%

권장 (Should Have):
✅ 응답 속도 <200ms
✅ 코드 가독성 향상
✅ 증권사 전환 <1일

선택 (Nice to Have):
✅ 크로스 플랫폼 지원
✅ GUI 현대화
✅ API 문서화
```

---

## 10. 결론

### 10.1 핵심 개선사항

1. **아키텍처**: 복잡한 이벤트 기반 → 단순한 요청/응답
2. **통신**: Multiprocessing Queue → Redis Pub/Sub + REST
3. **에러 처리**: 불명확한 콜백 → 명확한 try/except
4. **증권사**: 키움 종속 → Adapter 패턴 (전환 용이)
5. **개발성**: 복잡한 디버깅 → 단순한 스택 트레이스

### 10.2 투자 대비 효과

**투자**: 
- 개발 시간: 8-10주
- 인력: 1명
- 리스크: 중간

**효과**:
- 안정성: ⬆⬆⬆ (에러 추적 명확)
- 유지보수성: ⬆⬆⬆ (코드 단순화)
- 확장성: ⬆⬆ (증권사 전환 용이)
- 생산성: ⬆⬆ (개발 속도 향상)

### 10.3 권장 사항

**즉시 시작 권장!**

이유:
1. 기존 시스템 복잡도 지속 증가 중
2. REST API 전환은 필수 트렌드
3. 조기 전환이 리스크 낮음
4. 점진적 전환으로 안전성 확보

**시작 순서**:
```
1주차: BrokerAPI 인터페이스 설계 및 기본 구현
2-3주차: 조건검색 모듈 분리 및 테스트
4-6주차: TradingEngine REST 전환
7-8주차: 병행 운영 및 검증
9주차: 완전 전환
```

---

**문서 작성일**: 2025-11-11  
**작성자**: Claude  
**버전**: 1.0
