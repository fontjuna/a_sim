# A_Back_A 프로젝트

## 프로젝트 개요
한국 주식 거래 자동화 시스템입니다. PyQt5와 키움증권 API(QAxContainer)를 사용하여 실시간 주식 거래, 차트 분석, 조건 검색 등을 수행합니다.

## 기술 스택
- **언어**: Python
- **GUI 프레임워크**: PyQt5
- **증권 API**: 키움증권 OpenAPI (QAxContainer)
- **데이터 처리**: pandas
- **멀티스레딩**: threading, multiprocessing

## 프로젝트 구조

```
a_back_a/
├── api_server.py       # API 서버 메인 (키움 API 연동)
├── dbm_server.py       # 데이터베이스 관리 서버
├── gui.py              # GUI 인터페이스
├── chart.py            # 차트 분석 및 표시
├── admin.py            # 관리자 기능
├── tables.py           # 테이블 데이터 관리
├── threads.py          # 스레드 관리
├── classes.py          # 공통 클래스 (TimeLimiter, Toast, ThreadSafeList 등)
├── public.py           # 공통 함수 및 유틸리티
├── aaa.py              # 보조 스크립트
├── script_volume.py    # 거래량 관련 스크립트
├── config/             # 설정 파일
│   ├── define_sets.json
│   └── strategy_sets.json
├── db/                 # 데이터베이스 파일
│   └── counter_data.json
├── script/             # 스크립트 저장소
│   └── scripts.json
├── images/             # 이미지 리소스
└── resources/          # 기타 리소스
```

## 주요 컴포넌트

### 1. API Server (api_server.py)
- 키움증권 OpenAPI와의 통신 담당
- 실시간 호가, 체결 데이터 수신
- 주문 및 조회 요청 처리
- API 요청 제한 관리 (TimeLimiter)

### 2. Database Server (dbm_server.py)
- 거래 데이터 저장 및 조회
- 데이터베이스 관리

### 3. GUI (gui.py)
- 사용자 인터페이스
- 실시간 데이터 표시
- 사용자 입력 처리

### 4. Chart (chart.py)
- 주가 차트 분석
- 기술적 지표 계산 및 표시
- 차트 시각화

### 5. Classes (classes.py)
주요 유틸리티 클래스:
- **ThreadSafeList**: 스레드 안전 리스트
- **TimeLimiter**: API 요청 빈도 제한
- **Toast**: 알림 메시지

### 6. Public (public.py)
- 공통 함수 및 유틸리티
- 데이터 클래스 (dc, gm)
- 프로파일링 함수
- 로깅 초기화

## 중요한 개발 규칙

### 코딩 규칙
- 코드 작성시 들여쓰기는 3단계 이내로 하고, 들여쓰기 시 탭 대신 공백 4개로 할것.
- 모듈 함수는 첫번째 열, 클래스 함수는 다섯번째 열에서 def 을 시작 한다.
- 기능에 따라 함수로 분리 할 것 (나열식 코딩을 해서 비슷한 코드가 반복해서 나타나지 않도록 함수로 만들어 재사용 할 것)
- **수정/코딩 시 먼저 검토받고 승인 후 작업한다.**

### API 요청 제한
```python
# api_server.py에서 구현됨
ord = TimeLimiter(name='ord', second=5, minute=300, hour=18000)
req = TimeLimiter(name='req', second=5, minute=100, hour=1000)
```
- **주문(order)**: 초당 5회, 분당 300회, 시간당 18000회 제한
- **조회(request)**: 초당 5회, 분당 100회, 시간당 1000회 제한
- 1.666초 이내 반복 요청 시 자동 취소
- 빈번한 요청 시 자동 대기

### 멀티스레딩
- `pythoncom.CoInitialize()` 필수 (COM 객체 사용 시)
- ThreadSafeList를 사용하여 스레드 간 데이터 공유
- QThread를 사용한 비동기 작업

### 설정 파일
- **config/define_sets.json**: 기본 설정
- **config/strategy_sets.json**: 거래 전략 설정
- **db/counter_data.json**: 카운터 데이터
- **script/scripts.json**: 스크립트 저장소

## 코딩 스타일
- Python 표준 스타일 가이드(PEP 8) 준수
- 한글 주석 및 로그 메시지 사용
- 로깅 레벨: INFO, WARNING, ERROR 적절히 사용
- 예외 처리 필수

## 주의사항
1. **키움증권 API 제약**:
   - Windows 환경에서만 실행 가능 (ActiveX 사용)
   - 계좌 정보 및 실시간 데이터는 로그인 필요

2. **API 호출 제한**:
   - 빈번한 요청 시 제재 가능
   - com_request_time_check() 함수로 자동 관리

3. **데이터 무결성**:
   - ThreadSafeList 사용으로 동시성 문제 방지
   - 데이터베이스 작업 시 트랜잭션 고려

4. **실시간 처리**:
   - 이벤트 기반 아키텍처
   - 콜백 함수에서 긴 작업 금지

## 개발 작업
### 본 프로그램(sim_no = 0)

### 모의 프로그램(시뮬레이션 : sim_no = 1, 2, 3)
1. **sim_no = 1**:

2. **sim_no = 2**:
   > 현재 수정 중
   - dtSimDate 위젯에 기준일 설정, btnSimStart 클릭시 시뮬레이션 시작
   - 실매매시 기록 해둔 real_condition, real_data 테이블에서 기준일자의 데이타를 가져온다.
     - real_data(rd) : 체결시간='20251117090000', 처리일시='2025-11-17 09:00:00.000'
     - real_condition(rc) : 일자='20251117', 시간='090000', 처리일시='2025-11-17 09:00:00.000'
     - 데이타를 처리일시를 이용 오름차순으로 정렬하여 시간에 맞게 내보낼 준비를 한다.
     - rc 데이타가 먼저 출발 하므로 이 시간을 데이타 시간과 동기화 한다. 현재시간이 15:00:00이고 첫 데이타 시간이 09:00:00 이라면 이 두 시간을 같은 시간이라고 본다.
   - SendCondition으로 트리거 되면 OnReceiveRealConditionSim을 통해서 rc 데이타를 동기화 된 시간에 맞춰 내보낸다.
   - rc 데이타가 실매매 로직에의해 SetRealReg로 등록 되면서 OnReceiveRealDataSim1And2 를 통해 rd 데이타를 동기화 된 시간에 맞춰 내보낸다.
   - rc 데이타로 rd 데이타가 송출 되기 시작하면 매매로직을 타게되며 이때 차트데이타를 가져오게 된다. 이 차트데이타는 기준일 이전 것만 가져와야 한다. 기준일 데이타는는 rd 데이타로 만들기 때문이다.

3. **sim_no = 3**:
   > 현재 것 무시하고 다음으로 변경 예정  
   > mariaDB 사용 (Synology NAS)  
   > 장 후 키움서버에서 1분봉과 일봉을 전종목 받는다.  
   - Maria 클래스  
     - get_chart_data() : 
        - 1시간 1000번 요청이내 시간조절
        - 전종목 다운로드 하여 디비에 저장
        - 차트종류, 종목코드, 종목명, 받은 행수, 진행완료종목/전체종목 등 현재 상황 표시
     - sim3_start() :
        - 시뮬레이션 실행행
        - 실매매(sim_no=0)시 저장 되었던 실시간 현재가와 검색종목 사용
        - 차트데이타는 mariaDB 에 저장된 차트 사용
        - 다양한 배속 지원
        - 처음으로, 중지, 다시시작 지원
  
## 개발 시 참고사항
- 새로운 API 호출 추가 시 TimeLimiter 고려
- 스레드 생성 시 반드시 pythoncom.CoInitialize() 호출
- 로깅을 통한 디버깅 정보 기록
- 설정 변경 시 JSON 파일 업데이트

## 테스트
- 실제 거래 전 모의투자 계좌로 테스트 필수
- API 제한에 걸리지 않도록 주의
- 로그 파일 확인으로 동작 검증

## 배포
- Windows 환경 필수
- 키움증권 OpenAPI 설치 필요
- Python 의존성 설치 후 실행
