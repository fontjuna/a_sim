from public import dc, get_path, profile_operation
from datetime import datetime, timedelta
import logging
import sqlite3
import os
import threading
import copy
import time
import multiprocessing as mp
from collections import defaultdict

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
        sql = self.create_table_sql(dc.ddb.TRD_TABLE_NAME, dc.ddb.TRD_COLUMNS)
        db_cursor.execute(sql)
        for index in dc.ddb.TRD_INDEXES.values():
            db_cursor.execute(index)

        # Conclusion Table
        sql = self.create_table_sql(dc.ddb.CONC_TABLE_NAME, dc.ddb.CONC_COLUMNS)
        db_cursor.execute(sql)
        for index in dc.ddb.CONC_INDEXES.values():
            db_cursor.execute(index)

        db_conn.commit()

        # 차트 디비
        chart_conn = self.get_connection('chart')
        chart_cursor = chart_conn.cursor()
        
        # 차트 테이블 (틱, 분)
        sql = self.create_table_sql(dc.ddb.MIN_TABLE_NAME, dc.ddb.MIN_COLUMNS)
        chart_cursor.execute(sql)
        for index in dc.ddb.MIN_INDEXES.values():
            chart_cursor.execute(index)

        # 차트 테이블 (일, 주, 월)
        sql = self.create_table_sql(dc.ddb.DAY_TABLE_NAME, dc.ddb.DAY_COLUMNS)
        chart_cursor.execute(sql)
        for index in dc.ddb.DAY_INDEXES.values():
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
            
            sql = f"DELETE FROM {dc.ddb.MON_TABLE_NAME} WHERE DATE(처리일시) < ?"
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
        table = dc.ddb.CONC_TABLE_NAME
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
        table = dc.ddb.MIN_TABLE_NAME if cycle in ['mi', 'tk'] else dc.ddb.DAY_TABLE_NAME
        #logging.debug(f'upsert_chart: {cycle}, {tick}, len={len(dict_data)}')
        dict_data = [{**item, '주기': cycle, '틱': tick} for item in dict_data]
        self.table_upsert('chart', table, dict_data)

