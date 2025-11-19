# sim_no=3 시뮬레이션 상세 보고서

## 1. 개요

### 1.1 정의
**sim3 (시뮬레이션 3번)**은 실매매 DB 데이터를 메모리에 로드하여 **배속 조절 가능한** 시간 기반 시뮬레이션을 제공하는 모드입니다.

### 1.2 sim2와의 주요 차이점

| 구분 | sim2 | sim3 |
|------|------|------|
| **데이터 로드** | 자동 로드 (set_tickers) | 수동 로드 (Memory Load 버튼) |
| **실행 방식** | 자동 시작 | GUI 컨트롤 (시작/정지/일시정지) |
| **배속 조절** | 고정 1배속 | 0.2x ~ 10x 조절 가능 |
| **제어** | 없음 | 시작/정지/일시정지/리셋 |
| **스레드** | 즉시 시작 | 조건검색 시 시작, 일시정지 가능 |
| **용도** | 자동 백테스팅 | 수동 제어 시뮬레이션 |

---

## 2. 핵심 데이터 구조 (SimData 클래스)

### 2.1 sim3 전용 속성 (api_server.py:76-91)

```python
class SimData:
    # 시뮬레이션 3번 전용 속성들
    self.sim3_date = None                    # 시뮬레이션 날짜 (YYYY-MM-DD)
    self.sim3_speed = 1.0                    # 배속 (0.2, 0.5, 1, 2, 5, 10)
    self.sim3_start_time = None              # 실제 시작 시간 (datetime.now())
    self.sim3_base_data_time = 0             # 기준 데이터 시간 (초)

    # 데이터
    self.sim3_condition_data = []            # real_condition 테이블 데이터
    self.sim3_real_data = []                 # real_data 테이블 데이터

    # 인덱스
    self.sim3_condition_index = 0            # 현재 조건검색 데이터 인덱스
    self.sim3_real_index = {}                # 종목별 실시간 데이터 인덱스 {code: index}
    self.sim3_registered_codes = set()       # 등록된 종목 코드들

    # 컨트롤 상태
    self.sim3_is_paused = False              # 일시정지 상태
    self.sim3_is_running = False             # 실행 상태
    self.sim3_is_stopped = True              # 정지 상태

    # 스레드 참조
    self.sim3_condition_thread = None        # 조건검색 스레드
    self.sim3_real_threads = {}              # 실시간 데이터 스레드들 {screen: thread}
```

### 2.2 상태 플래그 의미

| 상태 | is_stopped | is_running | is_paused | 의미 |
|------|-----------|-----------|-----------|------|
| **정지** | True | False | False | 초기 상태, 데이터 인덱스 0 |
| **실행** | False | True | False | 정상 재생 중 |
| **일시정지** | False | True | True | 현재 위치에서 멈춤 |

---

## 3. 실행 흐름

### 3.1 전체 프로세스

```
1. GUI에서 rbSim3 선택
   ↓
2. Memory Load 버튼 클릭
   ├─ api_server.sim3_memory_load()
   ├─ DB에서 condition_data, real_data 로드
   ├─ sim.ticker 추출
   └─ admin.mode_sim3_load() → stg_start()
   ↓
3. 조건검색 실행 (SendCondition)
   ├─ cond_thread 생성 (OnReceiveRealConditionSim3)
   ├─ sim3_pause() 호출 (일시정지 상태)
   └─ 스레드 시작 대기
   ↓
4. GUI 컨트롤
   ├─ Start: sim3_start() → 재생
   ├─ Pause: sim3_pause() → 일시정지
   ├─ Stop: sim3_reset_to_start() → 처음으로
   └─ Reset: 인덱스 0으로 초기화
   ↓
5. 데이터 재생
   ├─ OnReceiveRealConditionSim3: 조건검색 데이터 전송
   └─ OnReceiveRealDataSim3: 실시간 체결 데이터 전송
```

### 3.2 Memory Load 상세 (api_server.py:1229-1237)

```python
def sim3_memory_load(self):
    """시뮬레이션 3번 메모리 로드"""
    # 1. DB에서 데이터 로드
    sim.sim3_condition_data, sim.sim3_real_data = self.get_simulation_data()

    # 2. ticker 정보 추출
    sim.extract_ticker_info_from_db()

    # 3. ready 플래그 설정
    global ready_tickers
    ready_tickers = True
```

**get_simulation_data() 로직 (api_server.py:1184-1227):**
```python
def get_simulation_data(self):
    # 1. SQL 쿼리 실행
    condition_data = dbm.execute_query(COND_SELECT_DATE)
    real_data = dbm.execute_query(REAL_SELECT_DATE)

    # 2. 시간순 정렬
    condition_data.sort(key=lambda x: x['처리일시'])
    real_data.sort(key=lambda x: x['체결시간'])

    # 3. real_data 중복 제거 (같은 시간+종목코드의 마지막 데이터만)
    real_unique = {}
    for data in real_data:
        key = f"{data['체결시간']}_{data['종목코드']}"
        real_unique[key] = data
    real_data = list(real_unique.values())

    return condition_data, real_data
```

---

## 4. 스레드 구조

### 4.1 조건검색 스레드 (OnReceiveRealConditionSim3)

**위치:** api_server.py:802-888

**역할:**
- real_condition 데이터를 시간 순서대로 전송
- 조건편입(I)/이탈(D) 이벤트 발생
- sim3_registered_codes 관리

**핵심 로직:**

```python
def run(self):
    # 1. 기준 시간 설정 (첫 데이터의 시간)
    first_data = sim.sim3_condition_data[0]
    time_str = first_data['처리일시'][-6:]  # HHMMSS
    sim.sim3_base_data_time = hour*3600 + minute*60 + second

    # 2. 시작 시간 설정
    sim.sim3_start_time = datetime.now()

    # 3. 루프
    while sim.sim3_condition_index < len(sim.sim3_condition_data):
        # 상태 체크
        if sim.sim3_is_stopped: break
        if sim.sim3_is_paused: continue

        # 현재 데이터
        current_data = sim.sim3_condition_data[sim.sim3_condition_index]
        data_time_seconds = 데이터_시간을_초로_변환(current_data['처리일시'])

        # 현재 시뮬레이션 시간 계산
        elapsed_real = (datetime.now() - sim.sim3_start_time).total_seconds()
        sim_current_time = sim.sim3_base_data_time + (elapsed_real * sim.sim3_speed)

        # 시간 도달 시 전송
        if data_time_seconds <= sim_current_time:
            # 조건검색 데이터 전송
            self.order('rcv', 'proxy_method', QWork(
                method='on_receive_real_condition',
                args=(code, type, cond_name, cond_index)
            ))

            # 종목 등록/해제
            if type == 'I':
                sim.sim3_registered_codes.add(code)
            elif type == 'D':
                sim.sim3_registered_codes.discard(code)

            sim.sim3_condition_index += 1
```

**배속 계산 공식:**
```
실제_경과시간 = datetime.now() - sim3_start_time
시뮬레이션_현재시간 = 기준시간 + (실제_경과시간 × 배속)

예: 배속 10배, 실제 1초 경과
→ 시뮬레이션에서는 10초 진행
```

### 4.2 실시간 데이터 스레드 (OnReceiveRealDataSim3)

**위치:** api_server.py:890-993

**역할:**
- SetRealReg로 등록된 종목의 실시간 체결 데이터 전송
- 각 종목별 인덱스 관리 (sim3_real_index)

**핵심 로직:**

```python
def run(self):
    # 1. 종목별 인덱스 초기화
    for code in self.code_list:
        if code not in sim.sim3_real_index:
            sim.sim3_real_index[code] = 0

    # 2. 루프
    while self.is_running:
        # 상태 체크
        if sim.sim3_is_stopped: break
        if sim.sim3_is_paused: continue

        # 현재 시뮬레이션 시간 계산
        elapsed_real = (datetime.now() - sim.sim3_start_time).total_seconds()
        sim_current_time = sim.sim3_base_data_time + (elapsed_real * sim.sim3_speed)

        # 등록된 종목들 처리
        for code in sim.sim3_registered_codes:
            # 해당 종목의 데이터 필터링
            code_data = [d for d in sim.sim3_real_data if d['종목코드'] == code]
            current_index = sim.sim3_real_index[code]

            if current_index >= len(code_data): continue

            data = code_data[current_index]
            data_time_seconds = 데이터_시간을_초로_변환(data['체결시간'])

            # 시간 도달 시 전송
            if data_time_seconds <= sim_current_time:
                dictFID = {
                    '종목코드': code,
                    '현재가': data['현재가'],
                    '체결시간': data['체결시간'],
                    ...
                }

                self.order('rcv', 'proxy_method', QWork(
                    method='on_receive_real_data',
                    args=(code, '주식체결', dictFID)
                ))

                # 인덱스 증가
                sim.sim3_real_index[code] = current_index + 1
```

---

## 5. GUI 컨트롤

### 5.1 컨트롤 버튼 (gui.py:153-160)

| 버튼 | 메서드 | API 호출 | 설명 |
|------|--------|----------|------|
| **Upload** | gui_sim3_memory_load | sim3_memory_load | DB 데이터 메모리 로드 |
| **First** | gui_sim3_control_reset | sim3_control_reset | 처음으로 (인덱스 0) |
| **Start** | gui_sim3_control_start | sim3_control_start | 시작/재시작 |
| **Pause** | gui_sim3_control_pause | sim3_control_pause | 일시정지 |
| **Stop** | gui_sim3_control_stop | sim3_control_stop | 정지 (리셋) |

### 5.2 배속 설정 (gui.py:1236-1242)

```python
def gui_get_sim3_sets(self):
    speed = 1
    if self.rbSpeed2.isChecked(): speed = 2
    elif self.rbSpeed5.isChecked(): speed = 5
    elif self.rbSpeed10.isChecked(): speed = 10
    elif self.rbSpeed02.isChecked(): speed = 0.2
    elif self.rbSpeed05.isChecked(): speed = 0.5

    dt = self.dtSimDate.date().toString("yyyy-MM-dd")
    return speed, dt
```

### 5.3 컨트롤 API (api_server.py:1239-1301)

#### sim3_control_reset()
```python
def sim3_control_reset(self):
    """처음으로 리셋 (모든 상태 초기화)"""
    sim.sim3_reset_to_start()
    # ├─ condition_index = 0
    # ├─ real_index = {}
    # ├─ registered_codes = set()
    # ├─ start_time = None
    # ├─ base_data_time = 0
    # └─ is_paused/running/stopped 초기화
```

#### sim3_control_start(speed, dt)
```python
def sim3_control_start(self, speed=None, dt=None):
    """시작 (현재 위치에서 재생)"""
    # 1. 배속/날짜 변경
    if speed: sim.sim3_speed = speed
    if dt: sim.sim3_date = dt

    # 2. 시작
    sim.sim3_start()
    # ├─ is_paused = False
    # ├─ is_running = True
    # ├─ is_stopped = False
    # └─ start_time = datetime.now() (재시작 시 기준 시간 재조정)
```

#### sim3_control_pause()
```python
def sim3_control_pause(self):
    """일시정지 (현재 위치 유지)"""
    sim.sim3_pause()
    # └─ is_paused = True (인덱스 유지)
```

#### sim3_control_stop()
```python
def sim3_control_stop(self):
    """정지 (처음으로 리셋)"""
    sim.sim3_reset_to_start()
    # └─ reset과 동일 (스레드는 유지)
```

---

## 6. 일시정지/재시작 메커니즘

### 6.1 일시정지 시

```python
# Pause 버튼 클릭
sim.sim3_is_paused = True

# 스레드 동작
while True:
    if sim.sim3_is_paused:
        time.sleep(0.1)  # 대기만 하고 인덱스 유지
        continue
```

**핵심:** 인덱스를 증가시키지 않고 현재 위치 유지

### 6.2 재시작 시 (중요!)

```python
# Start 버튼 클릭
if sim.sim3_is_paused:
    # 일시정지 상태에서 재시작
    sim.sim3_is_paused = False

    # 다음 처리할 데이터의 시간으로 기준 시간 재설정
    next_data = sim.sim3_condition_data[sim.sim3_condition_index]
    time_str = next_data['처리일시'][-6:]
    sim.sim3_base_data_time = 시간을_초로_변환(time_str)

    # 실제 시작 시간 재설정
    sim.sim3_start_time = datetime.now()
```

**핵심:**
- `base_data_time`을 다음 데이터 시간으로 재설정
- `start_time`을 현재 시각으로 재설정
- → 시간 간격이 정확히 유지됨

**예시:**
```
1. 09:00:10에 일시정지
2. 실제 시간으로 10분 경과
3. 재시작 클릭
   - base_data_time = 09:00:10 (다음 데이터 시간)
   - start_time = 현재 시각
   → 09:00:10부터 다시 재생 (10분 경과 무시)
```

---

## 7. SetRealReg/SendCondition에서 sim3 처리

### 7.1 SetRealReg (api_server.py:1485-1495)

```python
def SetRealReg(self, screen, code_list, fid_list, opt_type):
    if self.sim_no == 3:
        for code in code_list:
            real_tickers.add(code)

        # 시뮬레이션 3번용 실시간 데이터 쓰레드 시작
        if screen not in real_thread:
            real_thread[screen] = OnReceiveRealDataSim3(self, code_list)
            sim.sim3_real_threads[screen] = real_thread[screen]
            real_thread[screen].start()
            logging.debug(f'시뮬레이션 3번 실시간 데이터 쓰레드 시작: {screen}')
        return 1
```

**특징:**
- 종목별이 아닌 화면번호별로 스레드 생성
- sim3_real_threads에 참조 저장 (cleanup 시 사용)

### 7.2 SendCondition (api_server.py:1568-1577)

```python
def SendCondition(self, screen, cond_name, cond_index, search, block=True, wait=15):
    if self.sim_no == 3:
        self.tr_condition_loaded = True
        self.tr_condition_list = []

        cond_thread[screen] = OnReceiveRealConditionSim3(cond_name, cond_index, self)
        sim.sim3_condition_thread = cond_thread[screen]
        cond_thread[screen].start()

        sim.sim3_start()   # 시뮬레이션 시작
        sim.sim3_pause()   # 첫 데이터 내보내기 전 일시정지

        return self.tr_condition_list
```

**특징:**
- 즉시 시작 후 일시정지 → GUI에서 Start 버튼으로 재생
- 조건검색 스레드는 1개만 생성

---

## 8. 스레드 정리 (thread_cleanup)

**위치:** api_server.py:1323-1407

```python
def thread_cleanup(self):
    if self.sim_no == 3:
        # 실시간 데이터 스레드들 정리
        for screen in list(sim.sim3_real_threads.keys()):
            thread = sim.sim3_real_threads[screen]
            if thread:
                thread.stop()
                thread.quit()
                thread.wait(5000)
                del sim.sim3_real_threads[screen]

        # 시뮬레이션 3번 상태 초기화
        sim.sim3_reset_to_start()
```

---

## 9. 주요 차이점 요약

### 9.1 sim1, sim2, sim3 비교

| 구분 | sim1 | sim2 | sim3 |
|------|------|------|------|
| **데이터 소스** | 랜덤 생성 | DB (자동 로드) | DB (수동 로드) |
| **조건검색** | 랜덤 | DB (rc_queue) | DB (condition_data) |
| **실시간** | 랜덤 | DB (rd_queue) | DB (real_data) |
| **시간 동기화** | 랜덤 간격 | 1배속 고정 | 배속 조절 |
| **제어** | 없음 | 없음 | 시작/정지/일시정지 |
| **스레드 시작** | 자동 | 자동 | SendCondition 시 |
| **GUI 의존성** | 낮음 | 중간 | 높음 |

### 9.2 시간 계산 비교

#### sim2:
```python
wait_time = _calculate_wait_time(체결시간)
time.sleep(wait_time)  # 고정 대기
```

#### sim3:
```python
elapsed_real = (now - start_time).total_seconds()
sim_time = base_time + (elapsed_real × speed)

if data_time <= sim_time:
    전송()  # 조건부 전송
```

---

## 10. 사용 시나리오

### 10.1 정상 사용 흐름

```
1. GUI에서 Sim3 라디오 버튼 선택
2. "Upload" 버튼 클릭
   → DB 데이터 메모리 로드
   → 전략 시작 (일시정지 상태)
3. 배속 선택 (0.2x ~ 10x)
4. "Start" 버튼 클릭
   → 시뮬레이션 재생 시작
5. 필요 시:
   - "Pause": 현재 위치에서 일시정지
   - "Start": 재시작
   - "Stop": 처음으로 리셋
   - "First": 처음으로 리셋
```

### 10.2 배속별 소요 시간 예상

**데이터:** 09:00:00 ~ 15:30:00 (6시간 30분 = 23,400초)

| 배속 | 소요 시간 |
|------|----------|
| 0.2x | 32시간 30분 (느리게) |
| 0.5x | 13시간 |
| 1.0x | 6시간 30분 (실시간) |
| 2.0x | 3시간 15분 |
| 5.0x | 1시간 18분 |
| 10.0x | 39분 |

---

## 11. 주의사항 및 제약사항

### 11.1 주의사항

1. **메모리 사용량**
   - 하루치 데이터를 전부 메모리에 로드
   - 종목 수 × 틱 수에 비례
   - 대용량 데이터 시 메모리 부족 가능

2. **배속과 API 제한**
   - 고배속(5x, 10x) 사용 시 API 제한 주의
   - TimeLimiter가 자동 제어하지만 과도한 요청 가능

3. **일시정지/재시작**
   - 재시작 시 시간 동기화 정확함
   - 하지만 외부 상태(주문 등)는 복원 안 됨

4. **스레드 정리**
   - 모드 전환 시 thread_cleanup 필수
   - sim3_real_threads 참조 유지 필요

### 11.2 제약사항

1. **데이터 수정 불가**
   - 메모리 로드 후 데이터 변경 불가
   - 날짜 변경 시 재로드 필요

2. **종목별 인덱스**
   - sim3_real_index는 종목별로 관리
   - 조건이탈 후 재편입 시 인덱스 연속성 문제 가능

3. **GUI 의존성**
   - GUI 없이는 컨트롤 어려움
   - API 직접 호출 가능하지만 권장 안 함

---

## 12. 코드 위치 참조

### 12.1 주요 파일

| 파일 | 관련 코드 |
|------|----------|
| **api_server.py** | 56-204: SimData 클래스<br>802-888: OnReceiveRealConditionSim3<br>890-993: OnReceiveRealDataSim3<br>1184-1301: sim3 메서드들 |
| **gui.py** | 153-160: 버튼 연결<br>522-540: sim3 컨트롤 메서드<br>1229-1244: sim3 설정 |
| **admin.py** | 503-509: mode_sim3_load |

### 12.2 핵심 메서드 목록

```python
# SimData (api_server.py)
- extract_ticker_info_from_db()  # 130-149
- sim3_reset_to_start()          # 151-161
- sim3_pause()                    # 163-169
- sim3_start()                    # 171-196
- sim3_stop()                     # 198-204

# APIServer (api_server.py)
- get_simulation_data()           # 1184-1227
- sim3_memory_load()              # 1229-1237
- sim3_control_reset()            # 1239-1243
- sim3_control_pause()            # 1245-1252
- sim3_control_start()            # 1254-1268
- sim3_control_stop()             # 1270-1275
- sim3_control_set_speed()        # 1277-1289
- sim3_control_set_date()         # 1291-1301

# GUI (gui.py)
- gui_sim3_memory_load()          # 522-527
- gui_sim3_control_start()        # 529-531
- gui_sim3_control_stop()         # 533-534
- gui_sim3_control_pause()        # 536-537
- gui_sim3_control_reset()        # 539-540
- gui_get_sim3_sets()             # 1236-1244
```

---

## 13. 개선 제안

### 13.1 현재 한계

1. **인덱스 관리 복잡성**
   - 조건이탈 후 재편입 시 실시간 데이터 인덱스 문제
   - 해결: 시간 기반으로 재탐색

2. **메모리 효율**
   - 전체 데이터를 메모리에 로드
   - 해결: 청크 단위 로딩

3. **진행률 표시 없음**
   - 현재 몇 %진행인지 표시 없음
   - 해결: GUI에 진행률 바 추가

### 13.2 제안 사항

1. **Progress Bar 추가**
```python
# GUI에 추가
progress = (sim.sim3_condition_index / len(sim.sim3_condition_data)) * 100
self.progressBar.setValue(progress)
```

2. **현재 시간 표시**
```python
# 현재 시뮬레이션 시간 표시
current_sim_time = HH:MM:SS 형식으로 변환
self.lbCurrentTime.setText(current_sim_time)
```

3. **속도 변경 시 실시간 적용**
```python
# 재시작 없이 배속 변경
def change_speed_on_the_fly(self, new_speed):
    sim.sim3_speed = new_speed
    # 기준 시간 재조정 필요
```

---

## 14. 결론

**sim3**는 실매매 데이터를 활용한 **고급 시뮬레이션 모드**로:

✅ **장점:**
- 배속 조절로 빠른 백테스팅 가능
- 일시정지/재시작으로 세밀한 분석 가능
- 실제 시간 흐름과 동일한 경험

⚠️ **단점:**
- 메모리 사용량 높음
- GUI 의존성 높음
- 설정 복잡성

**권장 사용:**
- 전략 검증 시 빠른 피드백이 필요할 때
- 특정 구간을 반복 분석할 때
- 실시간과 유사한 경험이 필요할 때

**비권장:**
- 자동화된 대량 백테스팅 (→ sim2 사용)
- GUI 없는 환경 (→ sim2 사용)
- 메모리 제약이 있는 환경

---

**작성일:** 2025-11-18
**버전:** v1.0
**작성자:** Claude (AI Assistant)
