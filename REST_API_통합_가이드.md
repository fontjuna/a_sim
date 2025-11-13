# 키움증권 REST API 통합 가이드

## 1. 파일 구성

생성된 파일들을 프로젝트 디렉토리에 복사:
```
프로젝트 폴더/
├─ rest_api_config.py          (신규)
├─ rest_api_client.py          (신규)
├─ rest_api_websocket.py       (신규)
├─ rest_api_integration.py     (신규)
└─ api_server.py               (수정 필요)
```

## 2. 필수 라이브러리 설치

```bash
pip install requests websocket-client --break-system-packages
```

## 3. api_server.py 수정 방법

### 3-1. import 추가 (파일 상단)

```python
from rest_api_integration import RestAPIIntegration
```

### 3-2. APIServer 클래스 __init__ 메서드 수정

기존 코드에 추가:
```python
def __init__(self):
    # ... 기존 코드 ...
    
    # REST API 통합 (추가)
    self.use_rest = False  # REST API 사용 여부
    self.rest = None  # REST API 통합 객체
    self.rest_appkey = None
    self.rest_secretkey = None
```

### 3-3. api_init 메서드 수정

```python
def api_init(self, sim_no=0, log_level=logging.DEBUG, use_rest=False, appkey=None, secretkey=None):
    try:
        # ... 기존 코드 ...
        
        # REST API 초기화 (추가)
        self.use_rest = use_rest
        if self.use_rest:
            self.rest_appkey = appkey
            self.rest_secretkey = secretkey
            self.rest = RestAPIIntegration(
                is_mock=(sim_no != 0),  # sim_no가 0이 아니면 모의투자
                appkey=appkey,
                secretkey=secretkey
            )
            logging.info('REST API 통합 모드 활성화')
        
        # ... 기존 코드 ...
```

### 3-4. CommConnect 메서드 수정

```python
def CommConnect(self, block=True):
    logging.debug(f'CommConnect: block={block}')
    
    # REST API 사용시 (추가)
    if self.use_rest:
        success = self.rest.connect()
        if success:
            self.connected = True
            self.order('prx', 'set_connected', self.connected)
            logging.info("REST API 로그인 성공")
        return
    
    # 기존 OCX 코드
    if self.sim_no == 1:  
        self.connected = True
        self.order('prx', 'set_connected', self.connected)
    else:
        self.ocx.dynamicCall("CommConnect()")
        if block:
            while not self.connected:
                pythoncom.PumpWaitingMessages()
```

### 3-5. SendOrder 메서드 수정

```python
def SendOrder(self, rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno):
    # REST API 사용시 (추가)
    if self.use_rest:
        return self.rest.send_order(rqname, screen, accno, ordtype, code, quantity, price, hoga, ordno)
    
    # 기존 코드
    if self.sim_no == 0:
        ret = self.ocx.dynamicCall("SendOrder(...)", [...])
        return ret
    else:
        # 시뮬레이션 코드
        ...
```

### 3-6. SetRealReg 메서드 수정

```python
def SetRealReg(self, screen, code_list, fid_list, opt_type):
    # REST API 사용시 (추가)
    if self.use_rest:
        # 콜백 설정 (최초 1회)
        if self.rest.on_real_data_callback is None:
            self.rest.set_callbacks(
                on_real_data=self._on_rest_real_data,
                on_real_condition=self._on_rest_real_condition,
                on_chejan_data=self._on_rest_chejan_data
            )
        return self.rest.set_real_reg(screen, code_list, fid_list, opt_type)
    
    # 기존 코드
    global real_thread, real_tickers
    ...
```

### 3-7. REST API 콜백 메서드 추가

```python
def _on_rest_real_data(self, code, rtype, dictFID):
    """REST API 실시간 시세 콜백"""
    try:
        # 기존 OnReceiveRealData와 동일하게 처리
        self.order('rcv', 'proxy_method', QWork(method='on_receive_real_data', args=(code, rtype, dictFID)))
    except Exception as e:
        logging.error(f"REST 실시간 데이터 처리 오류: {e}")

def _on_rest_real_condition(self, code, id_type, cond_name, cond_index):
    """REST API 실시간 조건검색 콜백"""
    try:
        # 기존 OnReceiveRealCondition과 동일하게 처리
        self.order('rcv', 'proxy_method', QWork(method='on_receive_real_condition', args=(code, id_type, cond_name, cond_index)))
    except Exception as e:
        logging.error(f"REST 조건검색 처리 오류: {e}")

def _on_rest_chejan_data(self, gubun, dictFID):
    """REST API 주문체결/잔고 콜백"""
    try:
        # 기존 OnReceiveChejanData와 동일하게 처리
        self.order('prx', 'proxy_method', QWork(method='on_receive_chejan_data', args=(gubun, dictFID)))
    except Exception as e:
        logging.error(f"REST 체결/잔고 처리 오류: {e}")
```

### 3-8. SendCondition 메서드 수정

```python
def SendCondition(self, screen, cond_name, cond_index, search, block=True, wait=15):
    global cond_thread, real_tickers
    cond_text = f'{cond_index:03d} : {cond_name.strip()}'
    if not com_request_time_check(kind='request', cond_text=cond_text): 
        return False
    
    # REST API 사용시 (추가)
    if self.use_rest:
        return self.rest.send_condition(screen, cond_name, cond_index, search)
    
    # 기존 OCX 코드
    if self.sim_no == 0:
        ...
```

### 3-9. cleanup 메서드 수정

```python
def cleanup(self):
    # REST API 정리 (추가)
    if self.use_rest and self.rest:
        self.rest.disconnect()
    
    # 기존 코드
    if self.sim_no > 0:
        self.thread_cleanup()
    self.connected = False
    logging.info("APIServer 종료")
```

## 4. 사용 예시

### 4-1. GUI에서 REST API 활성화

```python
# gui.py 또는 main 실행 부분

# 앱키와 시크릿키 설정
appkey = "당신의_앱키"
secretkey = "당신의_시크릿키"

# REST API 모드로 초기화
gm.prx.order('api', 'api_init', 
    sim_no=0,  # 0=운영, 1,2,3=시뮬
    log_level=logging.DEBUG,
    use_rest=True,  # REST API 사용
    appkey=appkey,
    secretkey=secretkey
)

# 로그인
gm.prx.order('api', 'CommConnect', block=True)
```

### 4-2. OCX와 REST 전환

```python
# OCX 사용 (기존)
gm.prx.order('api', 'api_init', sim_no=0, use_rest=False)

# REST API 사용 (신규)
gm.prx.order('api', 'api_init', sim_no=0, use_rest=True, appkey='...', secretkey='...')
```

## 5. 주의사항

### 5-1. API ID 매핑 확인

REST API 문서의 API ID와 엔드포인트를 확인하여 `rest_api_config.py`의 `RestAPIEndpoints`에 정확히 매핑해야 합니다.

예시:
- kt00018 → 계좌평가잔고내역
- ka10080 → 분봉차트조회
- kt10000 → 매수주문

### 5-2. 응답 데이터 구조

REST API의 응답 데이터 구조는 OCX와 다를 수 있으므로, 실제 API 문서를 참고하여 `rest_api_integration.py`의 각 메서드에서 응답 파싱 부분을 조정해야 합니다.

### 5-3. 시뮬레이션 모드

- `sim_no=0`: 운영 환경
- `sim_no=1,2,3`: 시뮬레이션 (REST API에서는 모의투자 도메인 사용)

REST API를 사용할 때는 `is_mock` 파라미터가 자동으로 설정됩니다.

### 5-4. 토큰 만료

토큰은 자동으로 갱신됩니다. 만료 5분 전에 자동으로 재발급을 시도합니다.

### 5-5. WebSocket 재연결

WebSocket 연결이 끊어지면 자동으로 재연결을 시도합니다 (최대 10회).

## 6. 테스트 방법

### 6-1. 단계별 테스트

1. **인증 테스트**
   ```python
   # 토큰 발급 확인
   api.api_init(use_rest=True, appkey='...', secretkey='...')
   api.CommConnect()
   ```

2. **조회 테스트**
   ```python
   # 잔고 조회
   success, data = api.rest.get_balance(accno='계좌번호')
   print(f"잔고: {data}")
   ```

3. **실시간 테스트**
   ```python
   # 실시간 시세 등록
   api.SetRealReg('5100', ['005930'], [], '0')
   ```

4. **주문 테스트**
   ```python
   # 매수 주문
   order_no = api.SendOrder('매수', '5511', '계좌번호', 1, '005930', 1, 60000, '00', '')
   print(f"주문번호: {order_no}")
   ```

### 6-2. 로그 확인

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

DEBUG 레벨로 설정하면 모든 REST API 요청/응답을 확인할 수 있습니다.

## 7. 문제 해결

### 7-1. 토큰 발급 실패
- appkey, secretkey 확인
- 도메인 확인 (운영/모의투자)
- 네트워크 연결 확인

### 7-2. WebSocket 연결 실패
- 먼저 HTTP 토큰 발급이 성공했는지 확인
- 방화벽 설정 확인 (포트 10000)

### 7-3. API 요청 실패
- API ID가 정확한지 확인
- 요청 바디 구조 확인
- return_code와 return_msg 확인

## 8. 추가 개발 필요 사항

다음 기능들은 필요시 추가 개발:

1. **추가 조회 API**
   - ka10001 (주식기본정보)
   - kt00001 (예수금상세)
   - 기타 조회 API

2. **응답 데이터 파싱**
   - 각 API의 실제 응답 구조에 맞게 파싱 로직 조정

3. **에러 처리 강화**
   - API 오류 코드별 세부 처리
   - 재시도 로직 개선

4. **성능 최적화**
   - 연속 조회 최적화
   - WebSocket 메시지 처리 최적화

## 9. 참고 문서

- 키움 REST API 문서: `Kiwoom_REST_API_DOC.pdf`
- 프로젝트 내 파일:
  - `rest_api_config.py`: 설정
  - `rest_api_client.py`: HTTP 클라이언트
  - `rest_api_websocket.py`: WebSocket 클라이언트
  - `rest_api_integration.py`: 통합 레이어
