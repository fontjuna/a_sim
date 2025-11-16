from public import dc, get_path, profile_operation, init_logger, QWork
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
import sqlite3
import os
import threading
import copy
import time
import multiprocessing as mp
from collections import defaultdict
from typing import Union

@dataclass
class FieldsAttributes: # 데이터베이스 필드 속성
    name: str
    type: str
    default: any = None
    primary: bool = False
    autoincrement: bool = False
    unique: bool = False
    not_null: bool = False
    index: Union[bool, str] = False #index=True 시 자동 생성, index='custom_index_name'이면 특정 이름으로 생성
    foreign_key: dict = None
    check: str = None

@dataclass
class DataBaseFields:   # 데이터베이스 컬럼 속성 정의
    id = FieldsAttributes(name='id', type='INTEGER', primary=True, autoincrement=True)
    거래세 = FieldsAttributes(name='거래세', type='INTEGER', not_null=True, default=0)
    거래세율 = FieldsAttributes(name='거래세율', type='REAL', not_null=True, default=0.0)
    계좌번호 = FieldsAttributes(name='계좌번호', type='TEXT', not_null=True, default="''")
    구분 = FieldsAttributes(name='구분', type='TEXT', not_null=True, default="''")
    당일매매세금 = FieldsAttributes(name='당일매매세금', type='INTEGER', not_null=True, default=0)
    당일매매수수료 = FieldsAttributes(name='당일매매수수료', type='INTEGER', not_null=True, default=0)
    단위체결가 = FieldsAttributes(name='단위체결가', type='INTEGER', not_null=True, default=0)
    단위체결량 = FieldsAttributes(name='단위체결량', type='INTEGER', not_null=True, default=0)
    매도가 = FieldsAttributes(name='매도가', type='INTEGER', not_null=True, default=0)
    매도금액 = FieldsAttributes(name='매도금액', type='INTEGER', not_null=True, default=0)
    매도번호 = FieldsAttributes(name='매도번호', type='TEXT', not_null=True, default="''")
    매도수구분 = FieldsAttributes(name='매도수구분', type='TEXT', not_null=True, default="''")
    매도수량 = FieldsAttributes(name='매도수량', type='INTEGER', not_null=True, default=0)
    매도수수료 = FieldsAttributes(name='매도수수료', type='INTEGER', not_null=True, default=0)
    매도시간 = FieldsAttributes(name='매도시간', type='TEXT', not_null=True, default="(strftime('%H:%M:%S', 'now', 'localtime'))")
    매도일시 = FieldsAttributes(name='매도일시', type='TEXT', not_null=True, default="(strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))")
    매도일자 = FieldsAttributes(name='매도일자', type='TEXT', not_null=True, default="(strftime('%Y%m%d', 'now', 'localtime'))")
    매도주문번호 = FieldsAttributes(name='매도주문번호', type='TEXT', not_null=True, default="''")
    매수가 = FieldsAttributes(name='매수가', type='INTEGER', not_null=True, default=0)
    매수금액 = FieldsAttributes(name='매수금액', type='INTEGER', not_null=True, default=0)
    매수번호 = FieldsAttributes(name='매수번호', type='TEXT', not_null=True, default="''")
    매수수량 = FieldsAttributes(name='매수수량', type='INTEGER', not_null=True, default=0)
    매수수수료 = FieldsAttributes(name='매수수수료', type='INTEGER', not_null=True, default=0)
    매수시간 = FieldsAttributes(name='매수시간', type='TEXT', not_null=True, default="(strftime('%H:%M:%S', 'now', 'localtime'))")
    매수일시 = FieldsAttributes(name='매수일시', type='TEXT', not_null=True, default="(strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))")
    매수일자 = FieldsAttributes(name='매수일자', type='TEXT', not_null=True, default="(strftime('%Y%m%d', 'now', 'localtime'))")
    매수전략 = FieldsAttributes(name='매수전략', type='TEXT', not_null=True, default="''")
    매수주문번호 = FieldsAttributes(name='매수주문번호', type='TEXT', not_null=True, default="''")
    매입단가 = FieldsAttributes(name='매입단가', type='INTEGER', not_null=True, default=0)
    매매구분 = FieldsAttributes(name='매매구분', type='TEXT', not_null=True, default="''")
    미체결수량 = FieldsAttributes(name='미체결수량', type='INTEGER', not_null=True, default=0)
    보유수량 = FieldsAttributes(name='보유수량', type='INTEGER', not_null=True, default=0)
    상태 = FieldsAttributes(name='상태', type='TEXT', not_null=True, default="''")
    손익금액 = FieldsAttributes(name='손익금액', type='INTEGER', not_null=True, default=0)
    손익율 = FieldsAttributes(name='손익율', type='REAL', not_null=True, default=0.0)
    수수료율 = FieldsAttributes(name='수수료율', type='REAL', not_null=True, default=0.0)
    요청명 = FieldsAttributes(name='요청명', type='TEXT', not_null=True, default="''")
    원주문번호 = FieldsAttributes(name='원주문번호', type='TEXT', not_null=True, default="''")
    전략명칭 = FieldsAttributes(name='전략명칭', type='TEXT', not_null=True, default="''")
    제비용 = FieldsAttributes(name='제비용', type='INTEGER', not_null=True, default=0)
    조건구분 = FieldsAttributes(name='조건구분', type='TEXT', not_null=True, default="''")
    조건번호 = FieldsAttributes(name='조건번호', type='TEXT', not_null=True, default="''")
    조건식명 = FieldsAttributes(name='조건식명', type='TEXT', not_null=True, default="''")
    종목명 = FieldsAttributes(name='종목명', type='TEXT', not_null=True, default="''")
    종목번호 = FieldsAttributes(name='종목번호', type='TEXT', not_null=True, default="''")
    종목코드 = FieldsAttributes(name='종목코드', type='TEXT', not_null=True, default="''")
    주문가격 = FieldsAttributes(name='주문가격', type='INTEGER', not_null=True, default=0)
    주문가능수량 = FieldsAttributes(name='주문가능수량', type='INTEGER', not_null=True, default=0)
    주문구분 = FieldsAttributes(name='주문구분', type='TEXT', not_null=True, default="''")
    주문번호 = FieldsAttributes(name='주문번호', type='TEXT', not_null=True, default="''")
    주문상태 = FieldsAttributes(name='주문상태', type='TEXT', not_null=True, default="''")
    주문수량 = FieldsAttributes(name='주문수량', type='INTEGER', not_null=True, default=0)
    주문유형 = FieldsAttributes(name='주문유형', type='TEXT', not_null=True, default="''")
    총매입가 = FieldsAttributes(name='총매입가', type='INTEGER', not_null=True, default=0)
    체결가 = FieldsAttributes(name='체결가', type='INTEGER', not_null=True, default=0)
    체결누계금액 = FieldsAttributes(name='체결누계금액', type='INTEGER', not_null=True, default=0)
    체결량 = FieldsAttributes(name='체결량', type='INTEGER', not_null=True, default=0)
    체결번호 = FieldsAttributes(name='체결번호', type='TEXT', not_null=True, default="''")
    체결시간 = FieldsAttributes(name='체결시간', type='TEXT', not_null=True, default="''")
    처리일시 = FieldsAttributes(name='처리일시', type='TEXT', not_null=True, default="(strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))")
    현재가 = FieldsAttributes(name='현재가', type='INTEGER', not_null=True, default=0)
    호가구분 = FieldsAttributes(name='호가구분', type='TEXT', not_null=True, default="''")
    화면번호 = FieldsAttributes(name='화면번호', type='TEXT', not_null=True, default="''")
    일자 = FieldsAttributes(name='일자', type='TEXT', not_null=True, default="''")
    시간 = FieldsAttributes(name='시간', type='TEXT', not_null=True, default="''")
    시가 = FieldsAttributes(name='시가', type='INTEGER', not_null=True, default=0)
    고가 = FieldsAttributes(name='고가', type='INTEGER', not_null=True, default=0)
    저가 = FieldsAttributes(name='저가', type='INTEGER', not_null=True, default=0)
    현재가 = FieldsAttributes(name='현재가', type='INTEGER', not_null=True, default=0)
    거래량 = FieldsAttributes(name='거래량', type='INTEGER', not_null=True, default=0)
    거래대금 = FieldsAttributes(name='거래대금', type='INTEGER', not_null=True, default=0)
    누적거래량 = FieldsAttributes(name='누적거래량', type='INTEGER', not_null=True, default=0)
    누적거래대금 = FieldsAttributes(name='누적거래대금', type='INTEGER', not_null=True, default=0)
    주기 = FieldsAttributes(name='주기', type='TEXT', not_null=True, default="''")
    틱 = FieldsAttributes(name='틱', type='INTEGER', not_null=True, default=1)
    sim_no = FieldsAttributes(name='sim_no', type='INTEGER', not_null=True, default=0)

class DataBaseColumns:  # 데이터베이스 테이블 정의
    f = DataBaseFields()

    # 통합 디비 ***************************************************************************************************************************************
    TRD_TABLE_NAME = 'trades' ## 주문 및 체결 데이터
    TRD_SELECT_DATE = f"SELECT substr(처리일시, 12, 12) AS 처리시간, * FROM {TRD_TABLE_NAME} WHERE DATE(처리일시) = ? AND sim_no = ? ORDER BY 처리일시"
    TRD_FIELDS = [f.id, f.전략명칭, f.주문구분, f.주문상태, f.주문번호, f.종목코드, f.종목명, f.현재가, f.주문수량, f.주문가격, \
                    f.미체결수량, f.매매구분, f.체결량, f.체결가, f.체결누계금액, f.체결번호, f.체결시간, f.단위체결가, f.단위체결량, f.당일매매수수료, \
                        f.당일매매세금, f.원주문번호, f.처리일시, f.sim_no]
    TRD_COLUMNS = [col.name for col in TRD_FIELDS]
    TRD_INDEXES = {
        'idx_ordno': f"CREATE INDEX IF NOT EXISTS idx_ordno ON {TRD_TABLE_NAME}(주문번호)",
        'idx_strategy': f"CREATE INDEX IF NOT EXISTS idx_strategy ON {TRD_TABLE_NAME}(전략명칭, 종목코드)",
        'idx_kind_code': f"CREATE INDEX IF NOT EXISTS idx_kind_code ON {TRD_TABLE_NAME}(주문구분, 종목코드)"
    }

    CONC_TABLE_NAME = 'conclusion' ## 체결 및 손익  
    CONC_SELECT_DATE = f"SELECT * FROM {CONC_TABLE_NAME} WHERE 매수일자 = ? AND sim_no = ? AND 매도수량 > 0 ORDER BY 매수시간 DESC"
    CONC_SELECT_SIM = f"SELECT DISTINCT 종목번호, 종목명 FROM {CONC_TABLE_NAME} WHERE 매수일자 = ? AND sim_no = ?"
    CONC_FIELDS = [f.id, f.종목번호, f.종목명, f.손익금액, f.손익율, f.매수일자, f.매수시간,\
                    f.매수수량, f.매수가, f.매수금액, f.매수번호, f.매도일자, f.매도시간, f.매도수량,\
                    f.매도가, f.매도금액, f.매도번호, f.제비용, f.매수전략, f.전략명칭, f.처리일시, f.sim_no]
    CONC_COLUMNS = [col.name for col in CONC_FIELDS]
    CONC_KEYS = ['매수일자', '매수번호']
    CONC_INDEXES = {
        'idx_sellorder': f"CREATE INDEX IF NOT EXISTS idx_sellorder ON {CONC_TABLE_NAME}(매도일자, 매도번호)"
    }
    
    COND_TABLE_NAME = 'real_condition' ## 실시간 조건 검색 종목
    COND_SELECT_DATE = f"SELECT * FROM {COND_TABLE_NAME} WHERE substr(처리일시, 1, 10) = ? AND sim_no = 0 ORDER BY 처리일시"
    COND_FIELDS = [f.id, f.일자, f.시간, f.종목코드, f.조건구분, f.조건번호, f.조건식명, f.처리일시, f.sim_no]
    COND_COLUMNS = [col.name for col in COND_FIELDS]
    COND_KEYS = ['처리일시']
    COND_INDEXES = {
        'idx_date': f"CREATE INDEX IF NOT EXISTS idx_date ON {COND_TABLE_NAME}(일자, 시간)"
    }
    
    REAL_TABLE_NAME = 'real_data' ## 실시간 현재가 데이타 : 당일 매수종목들의 틱 데이타
    REAL_SELECT_DATE = f"SELECT * FROM {REAL_TABLE_NAME} WHERE substr(체결시간, 1, 8) = ? AND sim_no = 0"
    REAL_FIELDS = [f.id, f.체결시간, f.종목코드, f.현재가, f.거래량, f.거래대금, f.누적거래량, f.누적거래대금, f.처리일시, f.sim_no]
    REAL_COLUMNS = [col.name for col in REAL_FIELDS]
    REAL_KEYS = ['체결시간', '종목코드']
    REAL_INDEXES = {
        'idx_code_time': f"CREATE INDEX IF NOT EXISTS idx_code_time ON {REAL_TABLE_NAME}(종목코드, 체결시간)"
    }
    
    SIM_TABLE_NAME = 'daily_sim' ## 시뮬레이션 종목 : 당일 매수 종목
    SIM_SELECT_DATE = f"SELECT * FROM {SIM_TABLE_NAME} WHERE 일자 = ? AND sim_no = ?"
    SIM_SELECT_GUBUN = f"SELECT * FROM {SIM_TABLE_NAME} WHERE 일자 = ? AND sim_no = ? AND 구분 <> '읽음'"
    SIM_FIELDS = [f.id, f.일자, f.종목코드, f.종목명, f.구분, f.상태, f.처리일시, f.sim_no]
    SIM_COLUMNS = [col.name for col in SIM_FIELDS]
    SIM_KEYS = ['일자', '종목코드']
    SIM_INDEXES = {}
    
    # 차트 테이블 ***************************************************************************************************************************************
    TICK_TABLE_NAME = 'tick_chart' ## 틱 차트
    TICK_SELECT_SAMPLE = f"SELECT * FROM {TICK_TABLE_NAME} WHERE 종목코드 = ? ORDER BY 체결시간 DESC LIMIT 1"
    TICK_SELECT_DATE = f"SELECT * FROM {TICK_TABLE_NAME} WHERE substr(체결시간, 1, 8) >= ? AND 주기 = ? AND 틱 = ? AND 종목코드 = ? ORDER BY 체결시간 DESC"
    TICK_SELECT_SIM = f"SELECT * FROM {TICK_TABLE_NAME} WHERE substr(체결시간, 1, 8) >= ? AND 주기 = ? AND 틱 = ? ORDER BY 체결시간"
    TICK_FIELDS = [f.id, f.종목코드, f.체결시간, f.시가, f.고가, f.저가, f.현재가, f.거래량, f.거래대금, f.주기, f.틱, f.처리일시]
    TICK_COLUMNS = [col.name for col in TICK_FIELDS]
    TICK_KEYS = ['주기', '틱', '종목코드', '체결시간']
    TICK_INDEXES = {}

    MIN_TABLE_NAME = 'minute_chart' ## 분 차트
    MIN_SELECT_SAMPLE = f"SELECT * FROM {MIN_TABLE_NAME} WHERE 종목코드 = ? ORDER BY 체결시간 DESC LIMIT 1"
    MIN_SELECT_DATE = f"SELECT * FROM {MIN_TABLE_NAME} WHERE substr(체결시간, 1, 8) >= ? AND 주기 = ? AND 틱 = ? AND 종목코드 = ? ORDER BY 체결시간 DESC"
    MIN_SELECT_SIM = f"SELECT * FROM {MIN_TABLE_NAME} WHERE substr(체결시간, 1, 8) >= ? AND 주기 = ? AND 틱 = ? ORDER BY 체결시간"
    MIN_FIELDS = [f.id, f.종목코드, f.체결시간, f.시가, f.고가, f.저가, f.현재가, f.거래량, f.거래대금, f.주기, f.틱, f.처리일시]
    MIN_COLUMNS = [col.name for col in MIN_FIELDS]
    MIN_KEYS = ['주기', '틱', '종목코드', '체결시간']
    MIN_INDEXES = {
        'idx_time_cycle_tick_code': f"CREATE INDEX IF NOT EXISTS idx_time_cycle_tick_code ON {MIN_TABLE_NAME}(체결시간, 주기, 틱, 종목코드)",
    }

    DAY_TABLE_NAME = 'dwm_chart' ## 일.주.월 차트
    DAY_SELECT_SAMPLE = f"SELECT * FROM {DAY_TABLE_NAME} WHERE 종목코드 = ? ORDER BY 일자 DESC LIMIT 1"
    DAY_SELECT_DATE = f"SELECT * FROM {DAY_TABLE_NAME} WHERE 일자 = ? AND 주기 = ?"
    DAY_FIELDS = [f.id, f.종목코드, f.일자, f.시가, f.고가, f.저가, f.현재가, f.거래량, f.거래대금, f.주기, f.틱, f.처리일시]
    DAY_COLUMNS = [col.name for col in DAY_FIELDS]
    DAY_KEYS = ['주기', '틱', '종목코드', '일자']
    DAY_INDEXES = {
        'idx_date_cycle_tick_code': f"CREATE INDEX IF NOT EXISTS idx_date_cycle_tick_code ON {DAY_TABLE_NAME}(일자, 주기, 틱, 종목코드)",
    }

db_columns = DataBaseColumns()

class DBMServer:
    def __init__(self):
        self.name = 'dbm'
        self.daemon = True
        self.sim_no = 0
        self.fee_rate = 0.00015
        self.tax_rate = 0.0015
        self.thread_local = None
        self.real_data_buffer = {}
        self.last_flush_time = time.time()
        self.buffer_lock = threading.Lock()
        
    def initialize(self):
        init_logger()
        self.thread_local = threading.local()
        self.db_initialize()

    def cleanup(self):
        try:
            with self.buffer_lock:
                if self.real_data_buffer:
                    buffer_data = list(self.real_data_buffer.values())
                    self.real_data_buffer.clear()
                    self.table_upsert('db', db_columns.REAL_TABLE_NAME, buffer_data, key=db_columns.REAL_KEYS)
                    logging.info(f"종료 시 실시간 데이터 버퍼 플러시: {len(buffer_data)}건")
            
            db_tables = [db_columns.TRD_TABLE_NAME, db_columns.CONC_TABLE_NAME, db_columns.COND_TABLE_NAME, db_columns.REAL_TABLE_NAME, db_columns.SIM_TABLE_NAME]
            chart_tables = [db_columns.TICK_TABLE_NAME, db_columns.MIN_TABLE_NAME, db_columns.DAY_TABLE_NAME]
            for table in db_tables:
                self.cleanup_old_data(db='db', table=table)
            for table in chart_tables:
                self.cleanup_old_data(db='chart', table=table)

            for db_type in ['chart', 'db']:
                if hasattr(self.thread_local, db_type):
                    conn = getattr(self.thread_local, db_type)
                    conn.close()

            self.thread_local = None
            logging.info(f"DBMServer 종료")

        except Exception as e:
            logging.error(f"Error in cleanup: {e}", exc_info=True)

    def set_rate(self, fee_rate, tax_rate):
        """요율 설정 (락 프리)"""
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate    

    def get_connection(self, db_type='chart'):
        """스레드별 데이터베이스 연결 반환"""
        if not hasattr(self.thread_local, db_type):
            if db_type == 'chart':
                db_name = 'chart.db'
            else:
                db_name = 'db.db'
            path = os.path.join(get_path(dc.fp.DB_PATH), db_name)
            conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL')  # WAL 모드 활성화
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            setattr(self.thread_local, db_type, conn)
        return getattr(self.thread_local, db_type)

    def get_cursor(self, db_type='chart'):
        """스레드별 커서 반환"""
        conn = self.get_connection(db_type)
        return conn.cursor()

    def dbm_init(self, sim_no, log_level=logging.DEBUG):
        self.sim_no = sim_no
        self.set_log_level(log_level)

    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'DBM 로그 레벨 설정: {level}')

    def db_initialize(self):
        """DB 초기화"""

        # 통합 디비
        db_conn = self.get_connection('db')
        db_cursor = db_conn.cursor()
        
        # trades 테이블
        sql = self.create_table_sql(db_columns.TRD_TABLE_NAME, db_columns.TRD_FIELDS)
        db_cursor.execute(sql)
        for index in db_columns.TRD_INDEXES.values():
            db_cursor.execute(index)

        # Conclusion Table
        sql = self.create_table_sql(db_columns.CONC_TABLE_NAME, db_columns.CONC_FIELDS, key=db_columns.CONC_KEYS)
        db_cursor.execute(sql)
        for index in db_columns.CONC_INDEXES.values():
            db_cursor.execute(index)

        # 시뮬레이션 할 조건검색된 종목 테이블
        sql = self.create_table_sql(db_columns.COND_TABLE_NAME, db_columns.COND_FIELDS, key=db_columns.COND_KEYS)
        db_cursor.execute(sql)
        for index in db_columns.COND_INDEXES.values():
            db_cursor.execute(index)

        # 실시간 현재가 데이타
        sql = self.create_table_sql(db_columns.REAL_TABLE_NAME, db_columns.REAL_FIELDS, key=db_columns.REAL_KEYS)
        db_cursor.execute(sql)
        for index in db_columns.REAL_INDEXES.values():
            db_cursor.execute(index)

        # 시뮬레이션 할 종목 테이블
        sql = self.create_table_sql(db_columns.SIM_TABLE_NAME, db_columns.SIM_FIELDS, key=db_columns.SIM_KEYS)
        db_cursor.execute(sql)
        for index in db_columns.SIM_INDEXES.values():
            db_cursor.execute(index)

        db_conn.commit()

        # 차트 디비
        chart_conn = self.get_connection('chart')
        chart_cursor = chart_conn.cursor()
        
        # 차트 테이블 (틱)
        sql = self.create_table_sql(db_columns.TICK_TABLE_NAME, db_columns.TICK_FIELDS, key=db_columns.TICK_KEYS)
        chart_cursor.execute(sql)
        for index in db_columns.TICK_INDEXES.values():
            chart_cursor.execute(index)

        # 차트 테이블 (분)
        sql = self.create_table_sql(db_columns.MIN_TABLE_NAME, db_columns.MIN_FIELDS, key=db_columns.MIN_KEYS)
        chart_cursor.execute(sql)
        for index in db_columns.MIN_INDEXES.values():
            chart_cursor.execute(index)

        # 차트 테이블 (일, 주, 월)
        sql = self.create_table_sql(db_columns.DAY_TABLE_NAME, db_columns.DAY_FIELDS, key=db_columns.DAY_KEYS)
        chart_cursor.execute(sql)
        for index in db_columns.DAY_INDEXES.values():
            chart_cursor.execute(index)

        chart_conn.commit()

        logging.debug('dbm_initialize completed')

    def create_table_sql(self, table_name, fields, key=None):
        """테이블 생성 SQL문 생성"""
        field_definitions = []
        for field in fields:
            definition = f"{field.name} {field.type}"
            if field.not_null:
                definition += " NOT NULL"
            if field.unique and (not key or field.name not in key):
                definition += " UNIQUE"
            if field.primary:
                definition += " PRIMARY KEY"
            if field.autoincrement:
                definition += " AUTOINCREMENT"
            if field.default is not None:
                definition += f" DEFAULT {field.default}"
            if field.check:
                definition += f" CHECK({field.check})"
            if field.foreign_key:
                fk = field.foreign_key
                columns = fk['columns'] if 'columns' in fk else [fk['column']] # columns=['id', 'user_id']  또는 단일 컬럼 ['id']
                joined_columns = ', '.join(columns)
                definition += f" REFERENCES {fk['table']}({joined_columns})"                
            field_definitions.append(definition)
        # 복합 UPSRERT키 설정
        if key:
            field_definitions.append(f"UNIQUE ({', '.join(key)})")
        return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(field_definitions)});"

    def cleanup_old_data(self, db='db', table=db_columns.TRD_TABLE_NAME):
        """오래된 데이터 정리"""
        try:
            three_months_ago = datetime.now() - timedelta(days=90)
            date_str = three_months_ago.strftime('%Y-%m-%d')
            
            sql = f"DELETE FROM {table} WHERE DATE(처리일시) < ?"
            self.execute_query(sql, db=db, params=(date_str,))
            
            cursor = self.get_cursor('db')
            deleted_rows = cursor.rowcount
            logging.info(f"{table} 테이블에서 {date_str} 이전 데이터 {deleted_rows}건 삭제 완료")
            
            # 디스크 정리는 수동으로 하는것이 좋다
            #self.execute_query("VACUUM", db=db)
            
        except Exception as e:
            logging.error(f"오래된 데이터 정리 중 오류 발생: {e}", exc_info=True)

    def execute_query(self, sql, db='chart', params=None):
        """SQL 실행"""
        try:
            cursor = self.get_cursor(db)
            conn = self.get_connection(db)
            
            if isinstance(params, list) and params and isinstance(params[0], tuple):
                cursor.executemany(sql, params)
            else:
                cursor.execute(sql, params if params else ())
            
            if sql.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
                return result
            else:
                conn.commit()
                return cursor.rowcount

        except Exception as e:
            logging.error(f"Database error: {e}", exc_info=True)
            conn.rollback()
            return None

    def table_upsert(self, db, table, dict_data, key=None):
        """테이블 업서트"""
        try:
            is_list = isinstance(dict_data, list)   
            temp = dict_data[0] if is_list else dict_data

            columns = ','.join(temp.keys())
            column_str = ', '.join(['?'] * len(temp))
            params = [tuple(item.values()) for item in dict_data] if is_list else [tuple(dict_data.values())]

            if key:
                # UPDATE 대상 컬럼 정의 (conflict 컬럼 제외)
                update_columns = [col for col in temp.keys() if col not in key]
                update_expr = ', '.join([f"{col}=excluded.{col}" for col in update_columns])
                conflict_target = ', '.join(key)

                sql = f"""
                INSERT INTO {table} ({columns})
                VALUES ({column_str})
                ON CONFLICT({conflict_target}) DO UPDATE SET {update_expr}
                """
            else:
                sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({column_str})"
            self.execute_query(sql, db=db, params=params)
        except Exception as e:
            logging.error(f"table_upsert error: {e}", exc_info=True)

    def upsert_conclusion(self, kind, code, name, qty, price, amount, ordno, tm, st_name, st_buy, sim_no):
        """체결 정보 저장 및 손익 계산"""
        table = db_columns.CONC_TABLE_NAME
        record = None
        is_update = False

        def new_record():
            return { 
                '종목번호': code, '종목명': name, '매수일자': dc.ToDay, '매수시간': tm, 
                '매수수량': qty, '매수가': price, '매수금액': amount, '매수번호': ordno, 
                '매도수량': 0, '매수전략': st_buy, '전략명칭': st_name, 'sim_no': sim_no
            }
        
        def calculate_profit(sell_qty, sell_amount, buy_price):
            """손익 계산"""
            buy_amount = sell_qty * buy_price
            buy_fee = int(buy_amount * self.fee_rate / 10) * 10
            sell_fee = int(sell_amount * self.fee_rate / 10) * 10
            tax = int(sell_amount * self.tax_rate)
            total_fee = buy_fee + sell_fee + tax
            profit = sell_amount - buy_amount - total_fee
            profit_rate = (profit / buy_amount) * 100 if buy_amount > 0 else 0
            return total_fee, profit, profit_rate

        try:
            if kind == '매수':
                sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수일자 = ? AND 매수번호 = ? AND sim_no = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(code, dc.ToDay, ordno, sim_no))
                
                if result:
                    logging.info(f"체결디비에 매수정보 추가갱신: [{kind}] {code} {name} 수량:{qty} 단가:{price} 금액:{amount} 주문번호:{ordno} 시간:{tm}")
                    record = result[0]
                    record.update({'매수수량': qty, '매수가': price, '매수금액': amount})
                else:
                    logging.info(f"체결디비에 매수정보 신규작성: [{kind}] {code} {name} 수량:{qty} 단가:{price} 금액:{amount} 주문번호:{ordno} 시간:{tm}")
                    record = new_record()
            
            elif kind == '매도':
                # 같은 매도번호로 이미 처리 중인지 확인
                sql = f"SELECT * FROM {table} WHERE 매도일자 = ? AND 매도번호 = ? AND sim_no = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(dc.ToDay, ordno, sim_no))
                
                if result:
                    is_update = True
                    # 분할 매도의 추가 체결
                    logging.info(f"체결디비에 매도정보 추가갱신: [{kind}] {code} {name} 수량:{qty} 단가:{price} 금액:{amount} 주문번호:{ordno}")
                    record = result[0]
                    
                    buy_price = record.get('매수가', price)
                    total_fee, profit, profit_rate = calculate_profit(qty, amount, buy_price)
                    
                    record.update({
                        '매도번호': ordno, '매도일자': dc.ToDay, '매도시간': tm,
                        '매도수량': qty, '매도가': price, '매도금액': amount,
                        '제비용': total_fee, '손익금액': profit, '손익율': round(profit_rate, 2)
                    })
                else:
                    # 새로운 매도: FIFO로 미매도 레코드들 처리
                    remaining_qty = qty
                    remaining_amount = amount
                    total_profit_rate = 0
                    processed_records = []
                    
                    while remaining_qty > 0:
                        sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND sim_no = ? AND 매수수량 > 매도수량 ORDER BY 매수일자 ASC, 매수시간 ASC LIMIT 1"
                        result = self.execute_query(sql, db='db', params=(code, sim_no))
                        
                        if not result:
                            logging.error(f"체결디비 비정상: 미매도 레코드 부족 [{kind}] {code} {name} 남은수량:{remaining_qty} 매도번호:{ordno}")
                            return False
                        
                        record = result[0]
                        buy_qty = record.get('매수수량', 0)
                        sold_qty = record.get('매도수량', 0)
                        available_qty = buy_qty - sold_qty
                        
                        # 이번 레코드에서 처리할 수량
                        process_qty = min(available_qty, remaining_qty)
                        new_sold_qty = sold_qty + process_qty
                        
                        # 매도 금액 비율 계산
                        process_amount = int(amount * process_qty / qty) if qty > 0 else 0
                        buy_price = record.get('매수가', price)
                        total_fee, profit, profit_rate = calculate_profit(process_qty, process_amount, buy_price)
                        
                        record.update({
                            '매도번호': ordno, '매도일자': dc.ToDay, '매도시간': tm,
                            '매도수량': new_sold_qty, '매도가': price, '매도금액': process_amount,
                            '제비용': total_fee, '손익금액': profit, '손익율': round(profit_rate, 2)
                        })
                        
                        self.table_upsert('db', table, record, key=db_columns.CONC_KEYS)
                        processed_records.append({'profit_rate': profit_rate, 'qty': process_qty})
                        
                        logging.info(f"매도 레코드 처리: {code} {name} 매수번호:{record.get('매수번호')} 처리수량:{process_qty}/{buy_qty} 손익율:{profit_rate:.2f}%")
                        
                        remaining_qty -= process_qty
                        remaining_amount -= process_amount
                    
                    # 전체 평균 손익율 계산
                    total_buy_amount = sum(rec['qty'] * buy_price for rec in processed_records)
                    total_profit_rate = (sum(rec['profit_rate'] * rec['qty'] for rec in processed_records) / qty) if qty > 0 else 0
                    
                    # 매도 완료 시 손익율 반환
                    return {'code': code, 'name': name, 'profit_rate': round(total_profit_rate, 2)}
            else:
                logging.warning(f"체결디비 처리 불가: [{kind}] {code} {name} 수량:{qty} 단가:{price} 금액:{amount} 주문번호:{ordno} 시간:{tm}")
                return False

            # 분할 매도 추가갱신의 경우만 저장 (새로운 매도는 이미 while문에서 처리됨)
            if kind == '매도' and is_update:
                self.table_upsert('db', table, record, key=db_columns.CONC_KEYS)
                
                # 매도 완료 시 손익율 반환
                if record.get('매수수량', 0) == record.get('매도수량', 0):
                    return {'code': code, 'name': name, 'profit_rate': round(profit_rate, 2)}
            elif kind == '매수':
                self.table_upsert('db', table, record, key=db_columns.CONC_KEYS)

            return True
            
        except Exception as e:
            logging.error(f"체결디비 처리 에러: {e}", exc_info=True)
            return False

    def upsert_chart(self, dict_data, cycle, tick=1):
        """차트 데이터 저장"""
        table = db_columns.TICK_TABLE_NAME if cycle=='tk' else db_columns.MIN_TABLE_NAME if cycle=='mi' else db_columns.DAY_TABLE_NAME
        dict_data = [{**item, '주기': cycle, '틱': tick} for item in dict_data]
        self.table_upsert('chart', table, dict_data, key=db_columns.TICK_KEYS if cycle=='tk' else db_columns.MIN_KEYS if cycle=='mi' else db_columns.DAY_KEYS)

    def upsert_real_data(self, code, dictFID, sim_no):
        with self.buffer_lock:
            b = self.real_data_buffer
            b[code] = b[code].update({'체결시간': dc.ToDay+dictFID['체결시간'], '현재가': abs(int(dictFID['현재가'])), '거래량': b[code]['거래량'] + abs(int(dictFID['거래량'])), 
                                      '누적거래량': abs(int(dictFID['누적거래량'])), '누적거래대금': abs(int(dictFID['누적거래대금']))})\
                                    or b[code] if code in b else \
                                     {'체결시간': dc.ToDay+dictFID['체결시간'], '현재가': abs(int(dictFID['현재가'])), '거래량': abs(int(dictFID['거래량'])), '누적거래량': abs(int(dictFID['누적거래량'])),
                                       '누적거래대금': abs(int(dictFID['누적거래대금'])), '종목코드': code, 'sim_no': sim_no}
            if time.time() - self.last_flush_time >= 10.0 and b:
                self.table_upsert('db', db_columns.REAL_TABLE_NAME, list(b.values()), key=db_columns.REAL_KEYS)
                b.clear()
                self.last_flush_time = time.time()

    def insert_real_condition(self, code, type, cond_name, cond_index, sim_no):
        처리일시 = datetime.now().strftime("%Y%m%d%H%M%S")
        record = {'일자': 처리일시[:8], '시간': 처리일시[8:], '종목코드': code, '조건구분': type, '조건번호': cond_index, '조건식명': cond_name, 'sim_no': sim_no}
        self.table_upsert('db', db_columns.COND_TABLE_NAME, record, key=db_columns.COND_KEYS)
