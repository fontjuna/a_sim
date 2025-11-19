# MariaDB 현재 시스템 통합 방안

## 1. 현재 시스템 구조 분석

### 1.1 DBMServer 아키텍처

```python
# dbm_server.py
class DBMServer:
    def __init__(self):
        self.thread_local = threading.local()  # 스레드별 커넥션

    def get_connection(self, db_type='chart'):
        """SQLite 커넥션 반환"""
        # db_type: 'chart' → chart.db
        #         'db' → db.db

    def load_real_condition(self, date):
        """SQLite에서 조건검색 데이터 로드"""

    def load_real_data(self, date):
        """SQLite에서 실시간 데이터 로드"""
```

**문제점:**
- 모든 데이터를 로컬 SQLite에서만 조회
- 과거 데이터 조회 시에도 SQLite만 사용
- MariaDB 연동 구조 없음

---

## 2. 통합 전략: Hybrid 방식

### 2.1 핵심 아이디어

```
┌─────────────────────────────────────────────┐
│ DBMServer (기존 클래스 확장)                │
├─────────────────────────────────────────────┤
│  ┌─────────────┐      ┌──────────────┐     │
│  │ SQLite      │      │ MariaDB      │     │
│  │ (당일 데이터)│      │ (과거 데이터)│     │
│  └─────────────┘      └──────────────┘     │
│         ↓                     ↓              │
│  get_data(date) ───→ [날짜 판단] ──→ 선택   │
│                          ↓                   │
│                    오늘: SQLite              │
│                    과거: MariaDB             │
└─────────────────────────────────────────────┘
```

**장점:**
✅ 기존 코드 최소 수정
✅ SQLite와 MariaDB 동시 사용
✅ 점진적 전환 가능
✅ fallback 자동 처리

---

## 3. 구체적인 통합 단계

### 3.1 단계 1: MariaDB 연결 모듈 추가

**파일**: `dbm_server.py` (기존 파일 수정)

```python
import pymysql
from pymysql.cursors import DictCursor
import json
from datetime import datetime, date as dt_date

class DBMServer:
    def __init__(self):
        self.name = 'dbm'
        self.daemon = True
        self.sim_no = 0
        self.fee_rate = 0.00015
        self.tax_rate = 0.0015
        self.thread_local = None

        # ===== MariaDB 추가 =====
        self.use_mariadb = False
        self.mariadb_config = None
        self.mariadb_conn = None
        # ======================

    def initialize(self):
        init_logger()
        self.thread_local = threading.local()
        self.db_initialize()

        # ===== MariaDB 초기화 =====
        self.mariadb_initialize()
        # =========================

    def mariadb_initialize(self):
        """MariaDB 연결 초기화 (선택적)"""
        try:
            config_path = os.path.join(get_path('config'), 'mariadb_config.json')

            if not os.path.exists(config_path):
                logging.info("[DBM] MariaDB 설정 파일 없음 - SQLite만 사용")
                return

            with open(config_path) as f:
                self.mariadb_config = json.load(f)

            # 활성화 여부 확인
            if not self.mariadb_config.get('enabled', False):
                logging.info("[DBM] MariaDB 비활성화 - SQLite만 사용")
                return

            # 연결 테스트
            self.mariadb_conn = pymysql.connect(
                host=self.mariadb_config['host'],
                port=self.mariadb_config.get('port', 3306),
                user=self.mariadb_config['user'],
                password=self.mariadb_config['password'],
                database=self.mariadb_config['database'],
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=5
            )

            self.use_mariadb = True
            logging.info(f"[DBM] MariaDB 연결 성공: {self.mariadb_config['host']}")

        except FileNotFoundError:
            logging.info("[DBM] MariaDB 설정 파일 없음 - SQLite만 사용")
        except Exception as e:
            logging.warning(f"[DBM] MariaDB 연결 실패, SQLite 사용: {e}")
            self.use_mariadb = False

    def get_mariadb_cursor(self):
        """MariaDB 커서 반환"""
        if not self.use_mariadb or not self.mariadb_conn:
            raise Exception("MariaDB 연결 없음")

        # 연결 확인 및 재연결
        try:
            self.mariadb_conn.ping(reconnect=True)
        except:
            self.mariadb_initialize()

        return self.mariadb_conn.cursor()

    def is_today(self, date_str):
        """날짜가 오늘인지 확인"""
        # date_str 형식: 'YYYY-MM-DD' 또는 'YYYYMMDD'
        if len(date_str) == 8:  # YYYYMMDD
            check_date = datetime.strptime(date_str, '%Y%m%d').date()
        else:  # YYYY-MM-DD
            check_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        return check_date == dt_date.today()
```

---

### 3.2 단계 2: 데이터 로드 메서드 수정

**기존 메서드를 확장하여 MariaDB 지원 추가**

```python
class DBMServer:

    def load_real_condition(self, date, callback=None):
        """조건검색 데이터 로드 (SQLite 또는 MariaDB)"""
        try:
            # 오늘 데이터는 무조건 SQLite
            if self.is_today(date):
                return self._load_real_condition_sqlite(date, callback)

            # 과거 데이터는 MariaDB 우선, 없으면 SQLite
            if self.use_mariadb:
                try:
                    return self._load_real_condition_mariadb(date, callback)
                except Exception as e:
                    logging.warning(f"[DBM] MariaDB 조회 실패, SQLite 사용: {e}")
                    return self._load_real_condition_sqlite(date, callback)
            else:
                return self._load_real_condition_sqlite(date, callback)

        except Exception as e:
            logging.error(f'real_condition 로드 오류: {e}', exc_info=True)
            if callback:
                callback([])
            return []

    def _load_real_condition_sqlite(self, date, callback=None):
        """SQLite에서 조건검색 데이터 로드 (기존 로직)"""
        sql = db_columns.COND_SELECT_DATE
        cursor = self.get_cursor('db')
        cursor.execute(sql, (date,))
        result = cursor.fetchall()

        logging.info(f'[DBM-SQLite] real_condition 로드: {date}, {len(result)}건')

        if callback:
            callback(result)
        return result

    def _load_real_condition_mariadb(self, date, callback=None):
        """MariaDB에서 조건검색 데이터 로드 (신규)"""
        date_param = date.replace('-', '')  # YYYYMMDD

        sql = """
        SELECT 일자, 시간, 종목코드, 조건구분, 조건번호, 조건식명,
               CONCAT(일자, ' ', 시간) as 처리일시
        FROM real_condition
        WHERE 일자 = %s AND sim_no = 0
        ORDER BY 처리일시
        """

        cursor = self.get_mariadb_cursor()
        cursor.execute(sql, (date_param,))
        result = cursor.fetchall()
        cursor.close()

        logging.info(f'[DBM-MariaDB] real_condition 로드: {date}, {len(result)}건')

        if callback:
            callback(result)
        return result

    def load_real_data(self, date, callback=None):
        """실시간 데이터 로드 (SQLite 또는 MariaDB)"""
        try:
            # 오늘 데이터는 무조건 SQLite
            if self.is_today(date):
                return self._load_real_data_sqlite(date, callback)

            # 과거 데이터는 MariaDB 우선
            if self.use_mariadb:
                try:
                    return self._load_real_data_mariadb(date, callback)
                except Exception as e:
                    logging.warning(f"[DBM] MariaDB 조회 실패, SQLite 사용: {e}")
                    return self._load_real_data_sqlite(date, callback)
            else:
                return self._load_real_data_sqlite(date, callback)

        except Exception as e:
            logging.error(f'real_data 로드 오류: {e}', exc_info=True)
            if callback:
                callback([])
            return []

    def _load_real_data_sqlite(self, date, callback=None):
        """SQLite에서 실시간 데이터 로드 (기존 로직)"""
        date_param = date.replace('-', '')
        sql = db_columns.REAL_SELECT_DATE
        cursor = self.get_cursor('db')
        cursor.execute(sql, (date_param, date))
        result = cursor.fetchall()

        logging.info(f'[DBM-SQLite] real_data 로드: {date}, {len(result)}건')

        if callback:
            callback(result)
        return result

    def _load_real_data_mariadb(self, date, callback=None):
        """MariaDB에서 실시간 데이터 로드 (신규)"""
        date_param = date.replace('-', '')  # YYYYMMDD

        sql = """
        SELECT 체결시간, 종목코드, 현재가, 거래량, 거래대금,
               누적거래량, 누적거래대금, 처리일시, sim_no
        FROM real_data
        WHERE substr(체결시간, 1, 8) = %s
          AND sim_no = 0
          AND 종목코드 IN (
              SELECT DISTINCT 종목코드
              FROM real_condition
              WHERE 일자 = %s AND sim_no = 0
          )
        ORDER BY 체결시간
        """

        cursor = self.get_mariadb_cursor()
        cursor.execute(sql, (date_param, date_param))
        result = cursor.fetchall()
        cursor.close()

        logging.info(f'[DBM-MariaDB] real_data 로드: {date}, {len(result)}건')

        if callback:
            callback(result)
        return result
```

---

### 3.3 단계 3: 자동 저장 메서드 추가

**장 마감 후 SQLite → MariaDB 저장**

```python
class DBMServer:

    def save_to_mariadb(self, date):
        """당일 데이터를 MariaDB에 저장 (장 마감 후 실행)"""
        if not self.use_mariadb:
            logging.warning("[DBM] MariaDB 비활성화 - 저장 불가")
            return False

        try:
            logging.info(f"[DBM] {date} 데이터 MariaDB 저장 시작")

            # 1. real_condition 저장
            count_cond = self._save_real_condition_to_mariadb(date)

            # 2. real_data 저장
            count_real = self._save_real_data_to_mariadb(date)

            # 3. chart_data 저장 (선택적)
            # count_chart = self._save_chart_data_to_mariadb(date)

            logging.info(f"[DBM] MariaDB 저장 완료: 조건검색={count_cond}, 실시간={count_real}")
            return True

        except Exception as e:
            logging.error(f"[DBM] MariaDB 저장 오류: {e}", exc_info=True)
            return False

    def _save_real_condition_to_mariadb(self, date):
        """real_condition 데이터 저장"""
        # SQLite에서 조회
        sqlite_data = self._load_real_condition_sqlite(date)

        if not sqlite_data:
            return 0

        # MariaDB에 INSERT IGNORE
        sql = """
        INSERT IGNORE INTO real_condition
        (일자, 시간, 종목코드, 조건구분, 조건번호, 조건식명, sim_no)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor = self.get_mariadb_cursor()
        params_list = [
            (row['일자'], row['시간'], row['종목코드'], row['조건구분'],
             row['조건번호'], row.get('조건식명', ''), row.get('sim_no', 0))
            for row in sqlite_data
        ]

        cursor.executemany(sql, params_list)
        count = cursor.rowcount
        cursor.close()

        return count

    def _save_real_data_to_mariadb(self, date):
        """real_data 저장"""
        # SQLite에서 조회
        sqlite_data = self._load_real_data_sqlite(date)

        if not sqlite_data:
            return 0

        # MariaDB에 INSERT IGNORE
        sql = """
        INSERT IGNORE INTO real_data
        (체결시간, 종목코드, 현재가, 거래량, 거래대금, 누적거래량, 누적거래대금, sim_no)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor = self.get_mariadb_cursor()
        params_list = [
            (row['체결시간'], row['종목코드'], row['현재가'], row['거래량'],
             row['거래대금'], row['누적거래량'], row['누적거래대금'], row.get('sim_no', 0))
            for row in sqlite_data
        ]

        cursor.executemany(sql, params_list)
        count = cursor.rowcount
        cursor.close()

        return count
```

---

### 3.4 단계 4: api_server.py 연동 (기존 코드 그대로 사용)

**변경 필요 없음!** DBMServer의 `load_real_condition()`, `load_real_data()` 메서드가 내부적으로 MariaDB를 사용하므로 기존 코드 수정 불필요.

```python
# api_server.py - 수정 없음
def get_simulation_data(self):
    """시뮬레이션 3번 데이터 로드"""
    # 기존 코드 그대로 사용
    condition_data = self.answer('dbm', 'execute_query',
                                 sql=condition_sql, db='db', params=(date_param,))

    # DBMServer가 알아서 MariaDB/SQLite 선택
```

---

## 4. 설정 파일

### 4.1 MariaDB 설정

**파일**: `config/mariadb_config.json` (신규 생성)

```json
{
    "enabled": true,
    "host": "192.168.1.100",
    "port": 3306,
    "user": "stock_user",
    "password": "your_password",
    "database": "stock_trading",
    "connection_pool": {
        "max_connections": 5,
        "timeout": 30
    }
}
```

**비활성화 방법**: `"enabled": false` 설정 → SQLite만 사용

---

## 5. 스케줄러 통합

### 5.1 admin.py 수정 (장 마감 후 자동 저장)

```python
# admin.py
class AdminModel:

    def on_market_closed(self):
        """장 마감 후 처리 (15:40)"""
        # 기존 로직...

        # MariaDB 자동 저장 추가
        if self.use_mariadb:
            today = datetime.now().strftime('%Y-%m-%d')
            self.answer('dbm', 'save_to_mariadb', date=today)
```

### 5.2 수동 저장 (GUI 버튼 추가 - 선택적)

```python
# gui.py - 관리자 탭에 버튼 추가
def on_save_to_mariadb_clicked(self):
    """MariaDB 저장 버튼"""
    date = self.deDate.date().toString('yyyy-MM-dd')
    result = gm.answer('dbm', 'save_to_mariadb', date=date)

    if result:
        self.show_message(f"{date} 데이터 MariaDB 저장 완료")
    else:
        self.show_message(f"MariaDB 저장 실패")
```

---

## 6. 마이그레이션 전략

### 6.1 점진적 전환

**1주차: 준비**
- MariaDB 설치 (Synology NAS)
- 테이블 생성
- `mariadb_config.json` 생성 (enabled=false)

**2주차: 테스트**
- `enabled=true` 설정
- 과거 데이터 1일치 수동 저장
- sim3 로드 테스트

**3주차: 자동화**
- 스케줄러 활성화 (장 마감 후 자동 저장)
- 1주일 모니터링

**4주차: 전환 완료**
- 과거 1개월 데이터 마이그레이션
- SQLite는 당일 데이터만 유지

---

## 7. 데이터 흐름도

### 7.1 sim3 데이터 로드

```
api_server.py
    ↓
  get_simulation_data(date='2025-01-10')
    ↓
  DBMServer.load_real_condition('2025-01-10')
    ↓
  is_today('2025-01-10')?
    ├─ YES → SQLite
    └─ NO  → MariaDB (fallback: SQLite)
    ↓
  return data
```

### 7.2 장 마감 후 저장

```
15:40 장 마감
    ↓
admin.on_market_closed()
    ↓
DBMServer.save_to_mariadb(today)
    ├─ _save_real_condition_to_mariadb()
    │   ├─ SQLite 조회
    │   └─ MariaDB INSERT IGNORE
    │
    └─ _save_real_data_to_mariadb()
        ├─ SQLite 조회
        └─ MariaDB INSERT IGNORE
```

---

## 8. 장점 및 이점

### 8.1 최소 수정

✅ **api_server.py**: 수정 없음
✅ **기존 로직**: 그대로 유지
✅ **점진적 전환**: 언제든 비활성화 가능

### 8.2 자동 Fallback

```python
try:
    return mariadb_load()
except:
    return sqlite_load()  # 자동 대체
```

### 8.3 투명성

- 호출하는 쪽에서는 MariaDB/SQLite 구분 불필요
- `load_real_data(date)` 한 번 호출로 자동 처리

---

## 9. 테스트 계획

### 9.1 단위 테스트

```bash
# 1. MariaDB 연결 테스트
python -c "from dbm_server import DBMServer; \
           dbm = DBMServer(); \
           dbm.initialize(); \
           print('MariaDB:', dbm.use_mariadb)"

# 2. 데이터 로드 테스트
python -c "from dbm_server import DBMServer; \
           dbm = DBMServer(); \
           dbm.initialize(); \
           data = dbm.load_real_condition('2025-01-15'); \
           print('건수:', len(data))"

# 3. 저장 테스트
python -c "from dbm_server import DBMServer; \
           dbm = DBMServer(); \
           dbm.initialize(); \
           result = dbm.save_to_mariadb('2025-01-15'); \
           print('저장:', result)"
```

### 9.2 통합 테스트

1. **sim2 모드**: 과거 날짜 데이터 로드 확인
2. **sim3 모드**: MariaDB 데이터로 시뮬레이션 실행
3. **성능 측정**: 로드 시간 비교 (SQLite vs MariaDB)

---

## 10. 필요 패키지

```bash
pip install pymysql
```

**requirements.txt 추가**:
```
pymysql>=1.1.0
```

---

## 부록: 전체 수정 파일 요약

| 파일 | 수정 내용 | 라인 수 |
|------|----------|---------|
| `dbm_server.py` | MariaDB 연동 코드 추가 | +300줄 |
| `config/mariadb_config.json` | 설정 파일 생성 | 신규 |
| `admin.py` | 자동 저장 로직 추가 | +5줄 |
| `api_server.py` | **수정 없음** | 0줄 |

**총 수정량**: 약 350줄 (대부분 DBMServer 확장)

---

**작성일**: 2025-01-18
**버전**: 1.0
