from public import dc, get_path, profile_operation
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

@dataclass
class FieldsAttributes: # 데이터베이스 필드 속성
    name: str
    type: str
    default: any = None
    primary: bool = False
    autoincrement: bool = False
    unique: bool = False
    not_null: bool = False
    index: any = False
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
    상태 = FieldsAttributes(name='상태', type='TEXT', not_null=True, default="'보유중'")
    손익금액 = FieldsAttributes(name='손익금액', type='INTEGER', not_null=True, default=0)
    손익율 = FieldsAttributes(name='손익율', type='REAL', not_null=True, default=0.0)
    수수료율 = FieldsAttributes(name='수수료율', type='REAL', not_null=True, default=0.0)
    요청명 = FieldsAttributes(name='요청명', type='TEXT', not_null=True, default="''")
    원주문번호 = FieldsAttributes(name='원주문번호', type='TEXT', not_null=True, default="''")
    전략명칭 = FieldsAttributes(name='전략명칭', type='TEXT', not_null=True, default="''")
    제비용 = FieldsAttributes(name='제비용', type='INTEGER', not_null=True, default=0)
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
    시가 = FieldsAttributes(name='시가', type='INTEGER', not_null=True, default=0)
    고가 = FieldsAttributes(name='고가', type='INTEGER', not_null=True, default=0)
    저가 = FieldsAttributes(name='저가', type='INTEGER', not_null=True, default=0)
    현재가 = FieldsAttributes(name='현재가', type='INTEGER', not_null=True, default=0)
    거래량 = FieldsAttributes(name='거래량', type='INTEGER', not_null=True, default=0)
    거래대금 = FieldsAttributes(name='거래대금', type='INTEGER', not_null=True, default=0)
    주기 = FieldsAttributes(name='주기', type='TEXT', not_null=True, default="''")
    틱 = FieldsAttributes(name='틱', type='INTEGER', not_null=True, default=1)

class DataBaseColumns:  # 데이터베이스 테이블 정의
    f = DataBaseFields()

    TRD_TABLE_NAME = 'trades'
    TRD_SELECT_COLUMNS = "substr(처리일시, 12, 8) AS 처리시간, 주문구분, 주문상태, 종목코드, 종목명, 주문수량, 주문가격, 미체결수량,\
          체결량, 체결가, 체결누계금액, 매매구분, 주문번호, 원주문번호, 전략명칭, 처리일시"
    TRD_SELECT_DATE = f"SELECT substr(처리일시, 12, 12) AS 처리시간, * FROM {TRD_TABLE_NAME} WHERE DATE(처리일시) = ? ORDER BY 처리일시 ASC"
    TRD_COLUMNS = [f.id, f.전략명칭, f.주문구분, f.주문상태, f.주문번호, f.종목코드, f.종목명, f.현재가, f.주문수량, f.주문가격, \
                    f.미체결수량, f.매매구분, f.체결량, f.체결가, f.체결누계금액, f.체결번호, f.체결시간, f.단위체결가, f.단위체결량, f.당일매매수수료, \
                        f.당일매매세금, f.원주문번호, f.처리일시]
    TRD_COLUMN_NAMES = [col.name for col in TRD_COLUMNS]
    TRD_INDEXES = {
        'idx_ordno': f"CREATE INDEX IF NOT EXISTS idx_ordno ON {TRD_TABLE_NAME}(주문번호)",
        'idx_strategy': f"CREATE INDEX IF NOT EXISTS idx_strategy ON {TRD_TABLE_NAME}(전략명칭, 종목코드)",
        'idx_kind_code': f"CREATE INDEX IF NOT EXISTS idx_kind_code ON {TRD_TABLE_NAME}(주문구분, 종목코드)"
    }

    CONC_TABLE_NAME = 'conclusion'
    CONC_SELECT_DATE = f"SELECT * FROM {CONC_TABLE_NAME} WHERE 매도일자 = ? AND 매도수량 > 0 ORDER BY 매수일자, 매수시간 ASC"
    CONC_COLUMNS = [f.id, f.종목번호, f.종목명, f.손익금액, f.손익율, f.매수일자, f.매수시간,\
                    f.매수수량, f.매수가, f.매수금액, f.매수번호, f.매도일자, f.매도시간, f.매도수량,\
                    f.매도가, f.매도금액, f.매도번호, f.제비용, f.매수전략, f.전략명칭]
    CONC_COLUMN_NAMES = [col.name for col in CONC_COLUMNS]
    CONC_INDEXES = {
        'idx_buyorder': f"CREATE UNIQUE INDEX IF NOT EXISTS idx_buyorder ON {CONC_TABLE_NAME}(매수일자, 매수번호)",
        'idx_sellorder': f"CREATE INDEX IF NOT EXISTS idx_sellorder ON {CONC_TABLE_NAME}(매도일자, 매도번호)"
    }
    
    MIN_TABLE_NAME = 'minute_n_tick'
    MIN_SELECT_SAMPLE = f"SELECT * FROM {MIN_TABLE_NAME} WHERE 종목코드 = ? ORDER BY 체결시간 DESC LIMIT 1"
    MIN_SELECT_DATE = f"SELECT * FROM {MIN_TABLE_NAME} WHERE substr(체결시간, 1, 8) >= ? AND 주기 = ? AND 틱 = ? AND 종목코드 = ? ORDER BY 체결시간 DESC"
    MIN_COLUMNS = [f.id, f.종목코드, f.체결시간, f.시가, f.고가, f.저가, f.현재가, f.거래량, f.거래대금, f.주기, f.틱]
    MIN_COLUMN_NAMES = [col.name for col in MIN_COLUMNS]
    MIN_INDEXES = {
        'idx_cycle_tick_code_time': f"CREATE UNIQUE INDEX IF NOT EXISTS idx_cycle_tick_code_time ON {MIN_TABLE_NAME}(주기, 틱, 종목코드, 체결시간)",
        'idx_time_cycle_tick_code': f"CREATE INDEX IF NOT EXISTS idx_time_cycle_tick_code ON {MIN_TABLE_NAME}(체결시간, 주기, 틱, 종목코드)",
    }

    DAY_TABLE_NAME = 'day_week_month'
    DAY_SELECT_SAMPLE = f"SELECT * FROM {DAY_TABLE_NAME} WHERE 종목코드 = ? ORDER BY 일자 DESC LIMIT 1"
    DAY_SELECT_DATE = f"SELECT * FROM {DAY_TABLE_NAME} WHERE 일자 = ? AND 주기 = ?"
    DAY_COLUMNS = [f.id, f.종목코드, f.일자, f.시가, f.고가, f.저가, f.현재가, f.거래량, f.거래대금, f.주기, f.틱]
    DAY_COLUMN_NAMES = [col.name for col in DAY_COLUMNS]
    DAY_INDEXES = {
        'idx_cycle_tick_code_date': f"CREATE UNIQUE INDEX IF NOT EXISTS idx_cycle_tick_code_date ON {DAY_TABLE_NAME}(주기, 틱, 종목코드, 일자)",
        'idx_date_cycle_tick_code': f"CREATE INDEX IF NOT EXISTS idx_date_cycle_tick_code ON {DAY_TABLE_NAME}(일자, 주기, 틱, 종목코드)",
    }

db_columns = DataBaseColumns()

class DBMServer:
    def __init__(self):
        self.name = 'dbm'
        self.fee_rate = 0.00015
        self.tax_rate = 0.0015
        self.thread_local = None
        
    def initialize(self):
        self.thread_local = threading.local()
        self.init_dbm()

    def cleanup(self):
        try:
            for db_type in ['chart', 'db']:
                if hasattr(self.thread_local, db_type):
                    conn = getattr(self.thread_local, db_type)
                    try:
                        conn.commit()
                    except Exception as e:
                        logging.warning(f"{db_type} 커밋 실패, 롤백 시도: {e}")
                        try:
                            conn.rollback()
                        except Exception as e2:
                            logging.error(f"{db_type} 롤백 실패: {e2}")
                    finally:
                        conn.close()

            self.thread_local = None
            logging.info(f"DBMServer 종료")

        except Exception as e:
            logging.error(f"Error in cleanup: {e}", exc_info=True)

    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'DBM 로그 레벨 설정: {level}')

    def set_rate(self, fee_rate, tax_rate):
        """요율 설정 (락 프리)"""
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate    

    def get_connection(self, db_type='chart'):
        """스레드별 데이터베이스 연결 반환"""
        if not hasattr(self.thread_local, db_type):
            if db_type == 'chart':
                db_name = 'abc_chart.db'
            else:
                db_name = 'abc.db'
            path = os.path.join(get_path(dc.fp.DB_PATH), db_name)
            conn = sqlite3.connect(path)
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            setattr(self.thread_local, db_type, conn)
        return getattr(self.thread_local, db_type)

    def get_cursor(self, db_type='chart'):
        """스레드별 커서 반환"""
        conn = self.get_connection(db_type)
        return conn.cursor()

    def init_dbm(self):
        """DB 초기화"""
        logging.debug('dbm_init_db')

        # 통합 디비
        db_conn = self.get_connection('db')
        db_cursor = db_conn.cursor()
        
        # trades 테이블
        sql = self.create_table_sql(db_columns.TRD_TABLE_NAME, db_columns.TRD_COLUMNS)
        db_cursor.execute(sql)
        for index in db_columns.TRD_INDEXES.values():
            db_cursor.execute(index)

        # Conclusion Table
        sql = self.create_table_sql(db_columns.CONC_TABLE_NAME, db_columns.CONC_COLUMNS)
        db_cursor.execute(sql)
        for index in db_columns.CONC_INDEXES.values():
            db_cursor.execute(index)

        db_conn.commit()

        # 차트 디비
        chart_conn = self.get_connection('chart')
        chart_cursor = chart_conn.cursor()
        
        # 차트 테이블 (틱, 분)
        sql = self.create_table_sql(db_columns.MIN_TABLE_NAME, db_columns.MIN_COLUMNS)
        chart_cursor.execute(sql)
        for index in db_columns.MIN_INDEXES.values():
            chart_cursor.execute(index)

        # 차트 테이블 (일, 주, 월)
        sql = self.create_table_sql(db_columns.DAY_TABLE_NAME, db_columns.DAY_COLUMNS)
        chart_cursor.execute(sql)
        for index in db_columns.DAY_INDEXES.values():
            chart_cursor.execute(index)

        chart_conn.commit()

    def create_table_sql(self, table_name, fields, pk_columns=None):
        """테이블 생성 SQL문 생성"""
        field_definitions = []
        for field in fields:
            definition = f"{field.name} {field.type}"
            if field.not_null:
                definition += " NOT NULL"
            if field.unique:
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
                definition += f" REFERENCES {fk['table']}({fk['column']})"
            field_definitions.append(definition)
        if pk_columns:
            field_definitions.append(f"PRIMARY KEY ({', '.join(pk_columns)})")
        return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(field_definitions)});"

    def cleanup_old_data(self):
        """오래된 데이터 정리"""
        try:
            three_months_ago = datetime.now() - timedelta(days=90)
            date_str = three_months_ago.strftime('%Y-%m-%d')
            
            sql = f"DELETE FROM {db_columns.MON_TABLE_NAME} WHERE DATE(처리일시) < ?"
            self.execute_query(sql, db='db', params=(date_str,))
            
            cursor = self.get_cursor('db')
            deleted_rows = cursor.rowcount
            logging.info(f"monitor 테이블에서 {date_str} 이전 데이터 {deleted_rows}건 삭제 완료")
            
            self.execute_query("VACUUM", db='db')
            
        except Exception as e:
            logging.error(f"오래된 데이터 정리 중 오류 발생: {e}", exc_info=True)

    def send_result(self, result, error=None):
        """결과 전송"""
        order = 'dbm_query_result'
        job = {
            'result': result,
            'error': error
        }
        self.order('admin', order, **job)

    def execute_query(self, sql, db='chart', params=None):
        """SQL 실행"""
        try:
            cursor = self.get_cursor(db)
            conn = self.get_connection(db)
            
            if isinstance(params, list) and params and isinstance(params[0], tuple):
                #logging.debug(f'execute_many: {sql}')
                cursor.executemany(sql, params)
            else:
                #logging.debug(f'execute_query: {sql}')
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
            self.send_result(None, e)

    def table_upsert(self, db, table, dict_data):
        """테이블 업서트"""
        try:
            is_list = isinstance(dict_data, list)   
            temp = dict_data[0] if is_list else dict_data
            columns = ','.join(temp.keys())
            column_str = ', '.join(['?'] * len(temp))
            params = [tuple(item.values()) for item in dict_data] if is_list else [tuple(dict_data.values())]
            sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({column_str})"
            #logging.debug(f'table_upsert: {sql}')
            self.execute_query(sql, db=db, params=params)
        except Exception as e:
            logging.error(f"table_upsert error: {e}", exc_info=True)

    def upsert_conclusion(self, kind, code, name, qty, price, amount, ordno, st_name, st_buy):
        """체결 정보 저장 및 손익 계산"""
        table = db_columns.CONC_TABLE_NAME
        record = None
        dt = datetime.now().strftime("%Y%m%d")
        tm = datetime.now().strftime("%H%M%S")

        def new_record():
            return { 
                '종목번호': code, '종목명': name, '매수일자': dt, '매수시간': tm, 
                '매수수량': qty, '매수가': price, '매수금액': amount, '매수번호': ordno, 
                '매도수량': 0, '매수전략': st_buy, '전략명칭': st_name, 
            }

        try:
            if kind == '매수':
                sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수일자 = ? AND 매수번호 = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(code, dt, ordno))
                
                if result:
                    record = result[0]
                    record.update({'매수수량': qty, '매수가': price, '매수금액': amount})
                else:
                    record = new_record()
            
            elif kind == '매도':
                sql = f"SELECT * FROM {table} WHERE 매도일자 = ? AND 매도번호 = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(dt, ordno))
                
                if result:
                    record = result[0]
                else:
                    sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수수량 > 매도수량 ORDER BY 매수일자 ASC, 매수시간 ASC LIMIT 1"
                    result = self.execute_query(sql, db='db', params=(code,))
                    
                    if result:
                        record = result[0]
                    else:
                        record = new_record()

                buy_price = record.get('매수가', price)
                
                record.update({
                    '매도번호': ordno, '매도일자': dt, '매도시간': tm,
                    '매도수량': qty, '매도가': price, '매도금액': amount
                })
                
                # 손익 계산
                buy_amount = qty * buy_price
                buy_fee = int(buy_amount * self.fee_rate / 10) * 10
                sell_fee = int(amount * self.fee_rate / 10) * 10
                tax = int(amount * self.tax_rate)
                total_fee = buy_fee + sell_fee + tax
                profit = amount - buy_amount - total_fee
                profit_rate = (profit / buy_amount) * 100 if buy_amount > 0 else 0
                
                record.update({
                    '제비용': total_fee,
                    '손익금액': profit,
                    '손익율': round(profit_rate, 2)
                })
                
                if record.get('매수수량', 0) < qty:
                    record.update({
                        '매수수량': qty, '매수가': price, '매수금액': amount
                    })
            
            self.table_upsert('db', table, record)
            return True
            
        except Exception as e:
            logging.error(f"upsert_conclusion error: {e}", exc_info=True)
            return False

    def upsert_chart(self, dict_data, cycle, tick=1):
        """차트 데이터 저장"""
        table = db_columns.MIN_TABLE_NAME if cycle in ['mi', 'tk'] else db_columns.DAY_TABLE_NAME
        #logging.debug(f'upsert_chart: {cycle}, {tick}, len={len(dict_data)}')
        dict_data = [{**item, '주기': cycle, '틱': tick} for item in dict_data]
        self.table_upsert('chart', table, dict_data)

