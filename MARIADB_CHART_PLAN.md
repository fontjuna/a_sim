# MariaDB 차트 데이터 저장/활용 시스템 구축 계획

## 1. 목표 및 배경

### 현재 상황
- **데이터 소스**: 키움증권 OpenAPI에서 실시간 차트 데이터 요청 (OPT10080~OPT10083)
- **저장소**: SQLite (로컬 파일, `C:/Liberanimo/db`)
- **테이블**:
  - `tick_chart`: 틱/분/일/주/월봉 차트 데이터
  - `real_data`: 실시간 틱 데이터 (체결시간, 현재가, 거래량 등)
  - `real_condition`: 조건검색 결과
- **문제점**:
  - API 요청 제한 (초당 5회, 분당 100회, 시간당 1000회)
  - 과거 데이터 반복 요청 시 비효율
  - 로컬 DB만 사용으로 데이터 공유 불가

### 개선 목표
1. **MariaDB(Synology NAS) 활용**: 중앙 집중식 데이터 저장소
2. **자동 데이터 수집**: 장 마감 후 당일 데이터 자동 저장
3. **sim3 모드 개선**: 키움 API 대신 MariaDB 데이터 활용
4. **API 요청 최소화**: 과거 데이터는 DB에서 조회

---

## 2. 시스템 아키텍처

```
[키움 OpenAPI]
    ↓ (장중 실시간)
[api_server.py] ─┬─→ [로컬 SQLite] (당일 데이터 임시 저장)
                 │
                 └─→ [실시간 거래 처리]

[장 마감 후 15:40]
    ↓
[auto_save_daily_data()]
    ↓
[MariaDB on Synology NAS]
    ├─ chart_tick      (틱 데이터)
    ├─ chart_minute    (분봉 데이터)
    ├─ chart_day       (일봉 데이터)
    ├─ real_data       (실시간 틱 데이터)
    └─ real_condition  (조건검색 결과)

[sim3 모드 실행]
    ↓
[MariaDB에서 데이터 로드]
    ↓
[시뮬레이션 재생]
```

---

## 3. MariaDB 테이블 설계

### 3.1 차트 데이터 테이블

#### `chart_minute` - 분봉 데이터
```sql
CREATE TABLE chart_minute (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    종목코드 VARCHAR(10) NOT NULL,
    체결시간 VARCHAR(14) NOT NULL COMMENT 'YYYYMMDDHHMMSS',
    시가 INT NOT NULL DEFAULT 0,
    고가 INT NOT NULL DEFAULT 0,
    저가 INT NOT NULL DEFAULT 0,
    종가 INT NOT NULL DEFAULT 0,
    거래량 BIGINT NOT NULL DEFAULT 0,
    거래대금 BIGINT NOT NULL DEFAULT 0,
    주기 VARCHAR(10) NOT NULL DEFAULT 'mi' COMMENT 'mi=분봉',
    틱 INT NOT NULL DEFAULT 1 COMMENT '1,3,5,10,15,30,60분',
    처리일시 DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),

    UNIQUE KEY uk_code_time_tick (종목코드, 체결시간, 주기, 틱),
    INDEX idx_code_date (종목코드, 체결시간),
    INDEX idx_date (체결시간)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='분봉 차트 데이터';
```

#### `chart_day` - 일봉 데이터
```sql
CREATE TABLE chart_day (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    종목코드 VARCHAR(10) NOT NULL,
    일자 VARCHAR(8) NOT NULL COMMENT 'YYYYMMDD',
    시가 INT NOT NULL DEFAULT 0,
    고가 INT NOT NULL DEFAULT 0,
    저가 INT NOT NULL DEFAULT 0,
    종가 INT NOT NULL DEFAULT 0,
    거래량 BIGINT NOT NULL DEFAULT 0,
    거래대금 BIGINT NOT NULL DEFAULT 0,
    주기 VARCHAR(10) NOT NULL DEFAULT 'dy' COMMENT 'dy=일봉',
    처리일시 DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),

    UNIQUE KEY uk_code_date (종목코드, 일자),
    INDEX idx_code (종목코드),
    INDEX idx_date (일자)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='일봉 차트 데이터';
```

#### `chart_tick` - 틱 데이터 (고빈도)
```sql
CREATE TABLE chart_tick (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    종목코드 VARCHAR(10) NOT NULL,
    체결시간 VARCHAR(14) NOT NULL COMMENT 'YYYYMMDDHHMMSS',
    현재가 INT NOT NULL DEFAULT 0,
    거래량 INT NOT NULL DEFAULT 0,
    거래대금 BIGINT NOT NULL DEFAULT 0,
    주기 VARCHAR(10) NOT NULL DEFAULT 'tk',
    틱 INT NOT NULL DEFAULT 1 COMMENT '1,5,10틱',
    처리일시 DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_code_time (종목코드, 체결시간),
    INDEX idx_date (체결시간)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='틱 차트 데이터 (파티셔닝 권장)';

-- 파티셔닝 (일자별, 성능 최적화)
ALTER TABLE chart_tick PARTITION BY RANGE COLUMNS(체결시간) (
    PARTITION p202501 VALUES LESS THAN ('20250201'),
    PARTITION p202502 VALUES LESS THAN ('20250301'),
    -- ... 월별 파티션
);
```

### 3.2 실시간 데이터 테이블

#### `real_data` - 실시간 체결 데이터
```sql
CREATE TABLE real_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    체결시간 VARCHAR(14) NOT NULL COMMENT 'YYYYMMDDHHMMSS',
    종목코드 VARCHAR(10) NOT NULL,
    현재가 INT NOT NULL DEFAULT 0,
    거래량 INT NOT NULL DEFAULT 0,
    거래대금 BIGINT NOT NULL DEFAULT 0,
    누적거래량 BIGINT NOT NULL DEFAULT 0,
    누적거래대금 BIGINT NOT NULL DEFAULT 0,
    처리일시 DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    sim_no INT NOT NULL DEFAULT 0 COMMENT '0=실제, 1=sim1, 2=sim2, 3=sim3',

    INDEX idx_code_time (종목코드, 체결시간),
    INDEX idx_time (체결시간),
    INDEX idx_sim (sim_no, 체결시간)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='실시간 체결 데이터 (조건검색 종목)';
```

#### `real_condition` - 조건검색 결과
```sql
CREATE TABLE real_condition (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    일자 VARCHAR(8) NOT NULL,
    시간 VARCHAR(6) NOT NULL COMMENT 'HHMMSS',
    종목코드 VARCHAR(10) NOT NULL,
    종목명 VARCHAR(50) DEFAULT '',
    조건구분 CHAR(1) NOT NULL COMMENT 'I=편입, D=이탈',
    조건번호 VARCHAR(10) NOT NULL,
    조건식명 VARCHAR(100) DEFAULT '',
    처리일시 DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    sim_no INT NOT NULL DEFAULT 0,

    INDEX idx_date_time (일자, 시간),
    INDEX idx_code (종목코드),
    INDEX idx_condition (조건번호, 일자)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='조건검색 편입/이탈 이력';
```

---

## 4. 구현 단계

### 4.1 단계 1: MariaDB 연결 모듈 개발

**파일**: `mariadb_connector.py` (신규)

```python
import pymysql
from pymysql.cursors import DictCursor
import logging
from contextlib import contextmanager
from typing import List, Dict, Any

class MariaDBConnector:
    """MariaDB 연결 및 쿼리 실행"""

    def __init__(self, host, port, user, password, database):
        self.config = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            'charset': 'utf8mb4',
            'cursorclass': DictCursor,
            'autocommit': False
        }
        self.connection = None

    def connect(self):
        """DB 연결"""
        try:
            self.connection = pymysql.connect(**self.config)
            logging.info(f"MariaDB 연결 성공: {self.config['host']}:{self.config['port']}")
            return True
        except Exception as e:
            logging.error(f"MariaDB 연결 실패: {e}")
            return False

    def disconnect(self):
        """DB 연결 해제"""
        if self.connection:
            self.connection.close()
            logging.info("MariaDB 연결 해제")

    @contextmanager
    def get_cursor(self):
        """커서 컨텍스트 매니저"""
        cursor = self.connection.cursor()
        try:
            yield cursor
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logging.error(f"MariaDB 쿼리 오류: {e}")
            raise
        finally:
            cursor.close()

    def execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """SELECT 쿼리 실행"""
        with self.get_cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()

    def execute_insert(self, sql: str, params: tuple = None) -> int:
        """INSERT 쿼리 실행 (lastrowid 반환)"""
        with self.get_cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.lastrowid

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        """INSERT MANY 실행 (affected rows 반환)"""
        with self.get_cursor() as cursor:
            affected = cursor.executemany(sql, params_list)
            return affected

    def bulk_insert_ignore(self, table: str, columns: List[str], data: List[Dict]) -> int:
        """대량 INSERT IGNORE (중복 무시)"""
        if not data:
            return 0

        cols = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        sql = f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})"

        params_list = [
            tuple(row.get(col, None) for col in columns)
            for row in data
        ]

        return self.execute_many(sql, params_list)
```

**설정 파일**: `config/mariadb_config.json` (신규)

```json
{
    "host": "synology-nas.local",
    "port": 3306,
    "user": "stock_user",
    "password": "your_password",
    "database": "stock_trading"
}
```

---

### 4.2 단계 2: 자동 저장 모듈 개발

**파일**: `auto_save_daily_data.py` (신규)

```python
from mariadb_connector import MariaDBConnector
from dbm_server import DBMServer
import json
import logging
from datetime import datetime

class AutoSaveDailyData:
    """장 마감 후 당일 데이터를 MariaDB에 자동 저장"""

    def __init__(self, sqlite_db_path, mariadb_config_path):
        self.sqlite_db = DBMServer(sqlite_db_path)

        with open(mariadb_config_path) as f:
            config = json.load(f)
        self.mariadb = MariaDBConnector(**config)
        self.mariadb.connect()

    def save_chart_data(self, date: str):
        """차트 데이터 저장 (분봉, 일봉)"""
        logging.info(f"[자동저장] {date} 차트 데이터 저장 시작")

        # SQLite에서 당일 차트 데이터 조회
        sql = """
        SELECT 종목코드, 체결시간, 시가, 고가, 저가, 현재가 as 종가,
               거래량, 거래대금, 주기, 틱
        FROM tick_chart
        WHERE substr(체결시간, 1, 8) = ?
        ORDER BY 체결시간
        """
        date_param = date.replace('-', '')  # '2025-01-15' → '20250115'
        data = self.sqlite_db.execute_query(sql, (date_param,))

        if not data:
            logging.warning(f"[자동저장] {date} 차트 데이터 없음")
            return

        # 분봉/일봉 분리
        minute_data = [row for row in data if row['주기'] == 'mi']
        day_data = [row for row in data if row['주기'] == 'dy']

        # MariaDB에 저장
        if minute_data:
            columns = ['종목코드', '체결시간', '시가', '고가', '저가', '종가',
                      '거래량', '거래대금', '주기', '틱']
            count = self.mariadb.bulk_insert_ignore('chart_minute', columns, minute_data)
            logging.info(f"[자동저장] 분봉 {count}건 저장 완료")

        if day_data:
            # 일봉은 일자 필드 추가
            for row in day_data:
                row['일자'] = row['체결시간'][:8]
            columns = ['종목코드', '일자', '시가', '고가', '저가', '종가',
                      '거래량', '거래대금', '주기']
            count = self.mariadb.bulk_insert_ignore('chart_day', columns, day_data)
            logging.info(f"[자동저장] 일봉 {count}건 저장 완료")

    def save_real_data(self, date: str):
        """실시간 체결 데이터 저장"""
        logging.info(f"[자동저장] {date} 실시간 데이터 저장 시작")

        # SQLite에서 조회
        sql = """
        SELECT 체결시간, 종목코드, 현재가, 거래량, 거래대금,
               누적거래량, 누적거래대금, sim_no
        FROM real_data
        WHERE substr(체결시간, 1, 8) = ? AND sim_no = 0
        ORDER BY 체결시간
        """
        date_param = date.replace('-', '')
        data = self.sqlite_db.execute_query(sql, (date_param,))

        if not data:
            logging.warning(f"[자동저장] {date} 실시간 데이터 없음")
            return

        # MariaDB에 저장
        columns = ['체결시간', '종목코드', '현재가', '거래량', '거래대금',
                  '누적거래량', '누적거래대금', 'sim_no']
        count = self.mariadb.bulk_insert_ignore('real_data', columns, data)
        logging.info(f"[자동저장] 실시간 데이터 {count}건 저장 완료")

    def save_real_condition(self, date: str):
        """조건검색 결과 저장"""
        logging.info(f"[자동저장] {date} 조건검색 데이터 저장 시작")

        sql = """
        SELECT 일자, 시간, 종목코드, 종목명, 조건구분,
               조건번호, 조건식명, sim_no
        FROM real_condition
        WHERE 일자 = ? AND sim_no = 0
        ORDER BY 처리일시
        """
        date_param = date.replace('-', '')
        data = self.sqlite_db.execute_query(sql, (date_param,))

        if not data:
            logging.warning(f"[자동저장] {date} 조건검색 데이터 없음")
            return

        columns = ['일자', '시간', '종목코드', '종목명', '조건구분',
                  '조건번호', '조건식명', 'sim_no']
        count = self.mariadb.bulk_insert_ignore('real_condition', columns, data)
        logging.info(f"[자동저장] 조건검색 데이터 {count}건 저장 완료")

    def run(self, date: str = None):
        """전체 저장 프로세스 실행"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        logging.info(f"========== {date} 데이터 자동 저장 시작 ==========")

        try:
            self.save_chart_data(date)
            self.save_real_data(date)
            self.save_real_condition(date)
            logging.info(f"========== {date} 데이터 자동 저장 완료 ==========")
            return True
        except Exception as e:
            logging.error(f"[자동저장] 오류: {e}", exc_info=True)
            return False
        finally:
            self.mariadb.disconnect()

if __name__ == '__main__':
    # 테스트 실행
    saver = AutoSaveDailyData(
        sqlite_db_path='C:/Liberanimo/db/counter_data.db',
        mariadb_config_path='config/mariadb_config.json'
    )
    saver.run()
```

---

### 4.3 단계 3: 스케줄러 통합

**파일**: `scheduler.py` (기존 파일 수정 또는 신규)

```python
import schedule
import time
from auto_save_daily_data import AutoSaveDailyData
import logging

def job_save_daily_data():
    """매일 15:40에 자동 저장 (장 마감 후)"""
    saver = AutoSaveDailyData(
        sqlite_db_path='C:/Liberanimo/db/counter_data.db',
        mariadb_config_path='config/mariadb_config.json'
    )
    saver.run()

# 스케줄 등록
schedule.every().monday.at("15:40").do(job_save_daily_data)
schedule.every().tuesday.at("15:40").do(job_save_daily_data)
schedule.every().wednesday.at("15:40").do(job_save_daily_data)
schedule.every().thursday.at("15:40").do(job_save_daily_data)
schedule.every().friday.at("15:40").do(job_save_daily_data)

def run_scheduler():
    """스케줄러 실행 (백그라운드 스레드)"""
    logging.info("데이터 자동 저장 스케줄러 시작")
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 체크
```

**api_server.py에 통합** (APIServer.__init__):

```python
# 스케줄러 시작 (백그라운드 스레드)
from scheduler import run_scheduler
import threading

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
```

---

### 4.4 단계 4: sim3 모드에서 MariaDB 데이터 로드

**파일**: `api_server.py` - `get_simulation_data()` 수정

```python
def get_simulation_data(self, use_mariadb=True):
    """시뮬레이션 3번 데이터 로드 (MariaDB 우선)"""
    try:
        date_param = sim.sim3_date  # 'YYYY-MM-DD'

        if use_mariadb:
            # MariaDB에서 로드
            from mariadb_connector import MariaDBConnector
            import json

            with open('config/mariadb_config.json') as f:
                config = json.load(f)
            mariadb = MariaDBConnector(**config)
            mariadb.connect()

            # 조건검색 데이터
            cond_sql = """
            SELECT 일자, 시간, 종목코드, 조건구분, 조건번호, 조건식명,
                   CONCAT(일자, ' ', 시간) as 처리일시
            FROM real_condition
            WHERE 일자 = %s AND sim_no = 0
            ORDER BY 처리일시
            """
            condition_data = mariadb.execute_query(cond_sql, (date_param.replace('-', ''),))

            # 실시간 데이터 (조건검색 종목만)
            real_sql = """
            SELECT 체결시간, 종목코드, 현재가, 거래량, 거래대금,
                   누적거래량, 누적거래대금
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
            date_only = date_param.replace('-', '')
            real_data = mariadb.execute_query(real_sql, (date_only, date_only))

            mariadb.disconnect()

            logging.info(f"[MariaDB] 데이터 로드: 조건검색={len(condition_data)}, 실시간={len(real_data)}")

        else:
            # 기존 SQLite 로드 (fallback)
            from dbm_server import db_columns
            condition_data = self.answer('dbm', 'execute_query',
                                        sql=db_columns.COND_SELECT_DATE,
                                        db='db', params=(date_param,))
            real_data = self.answer('dbm', 'execute_query',
                                   sql=db_columns.REAL_SELECT_DATE,
                                   db='db', params=(date_only, date_param))

        # 이하 동일 (정렬, 중복 제거, 종목별 분류)
        # ... (기존 코드)

    except Exception as e:
        logging.error(f"시뮬레이션 3번 데이터 로드 오류: {e}")
        return [], [], {}
```

**설정 추가**: `config/define_sets.json`

```json
{
    "use_mariadb_for_sim3": true
}
```

---

## 5. 테스트 계획

### 5.1 단위 테스트

1. **MariaDB 연결 테스트**
   ```python
   python -c "from mariadb_connector import MariaDBConnector; \
              import json; \
              config = json.load(open('config/mariadb_config.json')); \
              db = MariaDBConnector(**config); \
              print('연결:', db.connect())"
   ```

2. **데이터 저장 테스트**
   ```python
   python auto_save_daily_data.py
   # 특정 날짜 테스트
   # saver.run('2025-01-15')
   ```

3. **데이터 로드 테스트** (sim3)
   - GUI에서 sim3 모드 선택
   - Memory Load 버튼 클릭
   - 로그 확인: `[MariaDB] 데이터 로드...`

### 5.2 통합 테스트

1. **전체 플로우 테스트**
   - 장중: 실시간 거래 + SQLite 저장
   - 15:40: 자동 저장 실행
   - MariaDB 데이터 확인
   - sim3 모드로 재생 테스트

2. **성능 테스트**
   - 대량 데이터 로드 시간 측정 (10만건+)
   - 메모리 사용량 모니터링
   - 네트워크 지연 시간 체크

3. **Fallback 테스트**
   - MariaDB 연결 실패 시 SQLite로 전환 확인
   - 오류 로그 확인

---

## 6. 배포 및 운영

### 6.1 필요 패키지 설치

```bash
pip install pymysql schedule
```

### 6.2 Synology NAS MariaDB 설정

1. **패키지 센터**에서 MariaDB 10 설치
2. **데이터베이스** 생성: `stock_trading`
3. **사용자** 생성: `stock_user` (비밀번호 설정)
4. **권한** 부여: `stock_trading` DB에 대한 모든 권한
5. **원격 접속** 허용: 방화벽 3306 포트 오픈

### 6.3 MariaDB 최적화

```sql
-- 인덱스 최적화
ANALYZE TABLE chart_minute, chart_day, real_data, real_condition;

-- 오래된 데이터 정리 (6개월 이상)
DELETE FROM real_data WHERE 체결시간 < DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 6 MONTH), '%Y%m%d');

-- 파티션 추가 (매월)
ALTER TABLE chart_tick ADD PARTITION (
    PARTITION p202506 VALUES LESS THAN ('20250701')
);
```

### 6.4 모니터링

- **저장 성공 여부**: 로그 파일 확인 (`log/log_message.log`)
- **데이터 건수**: MariaDB 쿼리
  ```sql
  SELECT DATE(처리일시) as 날짜, COUNT(*) as 건수
  FROM real_data
  WHERE sim_no = 0
  GROUP BY 날짜
  ORDER BY 날짜 DESC
  LIMIT 30;
  ```

---

## 7. 예상 효과

### 7.1 API 요청 절감
- **현재**: sim3 실행마다 과거 데이터 요청 (분당 100회 제한)
- **개선**: MariaDB에서 즉시 로드 (제한 없음)
- **절감률**: 약 80~90% (과거 데이터 재사용)

### 7.2 데이터 관리
- **중앙 집중식**: 여러 PC에서 동일 데이터 공유
- **백업**: NAS 자동 백업 기능 활용
- **분석**: SQL 쿼리로 다양한 분석 가능

### 7.3 sim3 성능
- **로딩 속도**: SQLite보다 빠른 네트워크 DB (인덱싱 최적화)
- **안정성**: NAS 고가용성

---

## 8. 향후 확장

1. **실시간 동기화**: 장중에도 실시간으로 MariaDB 저장 (옵션)
2. **웹 대시보드**: MariaDB 데이터 기반 웹 분석 도구
3. **백테스팅 엔진**: 과거 데이터 대량 분석
4. **알림 시스템**: 특정 조건 만족 시 알림 (MariaDB 트리거)

---

## 9. 리스크 및 대응

| 리스크 | 발생 확률 | 영향도 | 대응 방안 |
|--------|----------|--------|----------|
| MariaDB 연결 실패 | 중 | 중 | SQLite fallback, 재연결 로직 |
| 네트워크 지연 | 저 | 저 | LAN 환경, 인덱싱 최적화 |
| 데이터 중복 저장 | 중 | 저 | INSERT IGNORE, UNIQUE KEY |
| 디스크 용량 부족 | 저 | 고 | 파티셔닝, 오래된 데이터 정리 |

---

## 10. 일정

| 단계 | 작업 | 예상 기간 | 담당 |
|------|------|----------|------|
| 1 | MariaDB 설치 및 테이블 생성 | 1일 | 개발자 |
| 2 | mariadb_connector.py 개발 | 1일 | 개발자 |
| 3 | auto_save_daily_data.py 개발 | 2일 | 개발자 |
| 4 | 스케줄러 통합 | 0.5일 | 개발자 |
| 5 | sim3 모드 수정 | 1일 | 개발자 |
| 6 | 테스트 (단위/통합) | 2일 | 개발자 |
| 7 | 운영 배포 | 0.5일 | 개발자 |
| **합계** | | **8일** | |

---

## 부록: SQL 스크립트

### 테이블 생성 스크립트 (전체)
```sql
-- stock_trading 데이터베이스 생성
CREATE DATABASE IF NOT EXISTS stock_trading
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE stock_trading;

-- 분봉 테이블
CREATE TABLE chart_minute (...);  -- 위 참조

-- 일봉 테이블
CREATE TABLE chart_day (...);     -- 위 참조

-- 틱 테이블
CREATE TABLE chart_tick (...);    -- 위 참조

-- 실시간 데이터 테이블
CREATE TABLE real_data (...);     -- 위 참조

-- 조건검색 테이블
CREATE TABLE real_condition (...);-- 위 참조
```

---

**작성일**: 2025-01-18
**작성자**: Claude
**버전**: 1.0
