from public import dc, get_path, profile_operation
from chart import cht_dt
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
        self.running = False
        self.fee_rate = 0.00015
        self.tax_rate = 0.0015
        
        # 락-프리 최적화: 읽기 전용 데이터를 분리
        self.done_code = set()  # list -> set 변경 (O(1) 조회)
        self.todo_code = {}
        
        # 읽기-쓰기 락 분리
        self._write_lock = None  # 쓰기 전용 락 (최소화)
        self._done_lock = threading.RLock()  # done_code 전용 락 (재진입 가능)
        
        self.thread_local = None
        self.thread_run = False
        self.thread_chart = None    
        self.database = {}  # 테스트용
        
        # 성능 최적화: 백그라운드 등록 큐
        self._pending_registrations = []
        self._pending_lock = threading.Lock()

    def initialize(self):
        self._write_lock = threading.Lock()
        self.thread_local = threading.local()
        self.running = True
        self.init_dbm()
        # self.start_request_chart_data()

    def cleanup(self):
        try:
            print(f"{self.__class__.__name__} 중지 중...")
            self.running = False
            # self.stop_request_chart_data()
            
            # 스레드 종료 대기
            if self.thread_chart:
                self.thread_chart.join(timeout=2.0)
                self.thread_chart = None
            
            # 연결 정리
            if hasattr(self.thread_local, 'chart'):
                self.thread_local.chart.close()
            if hasattr(self.thread_local, 'db'):
                self.thread_local.db.close()
                
            self.thread_local = None
            self._write_lock = None
            self._done_lock = None
            
        except Exception as e:
            logging.error(f"Error in cleanup: {e}", exc_info=True)

    def get_status(self):
        """상태 확인 (락 프리)"""
        return {
            "name": self.__class__.__name__,
            "running": self.running,
            "done_count": len(self.done_code),
            "todo_count": len(self.todo_code),
        }
    
    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'DBM 로그 레벨 설정: {level}')

    def get_var(self, var_name, default=None):
        """인스턴스 변수 가져오기 (락 프리)"""
        return getattr(self, var_name, default)

    def set_var(self, var_name, value):
        """인스턴스 변수 설정하기 (락 프리)"""
        setattr(self, var_name, value)
        return True

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
            
            self.execute_query(sql, db=db, params=params)
        except Exception as e:
            logging.error(f"table_upsert error: {e}", exc_info=True)

    @profile_operation        
    def upsert_chart(self, dict_data, cycle, tick=1):
        """차트 데이터 저장"""
        table = dc.ddb.MIN_TABLE_NAME if cycle in ['mi', 'tk'] else dc.ddb.DAY_TABLE_NAME
        logging.debug(f'upsert_chart: {cycle}, {tick}, len={len(dict_data)} {dict_data[:1]}')
        dict_data = [{**item, '주기': cycle, '틱': tick} for item in dict_data]
        self.table_upsert('chart', table, dict_data)

    def upsert_conclusion(self, kind, code, name, qty, price, amount, ordno, st_no, st_name, st_buy):
        """체결 정보 저장 및 손익 계산"""
        table = dc.ddb.CONC_TABLE_NAME
        record = None
        dt = datetime.now().strftime("%Y%m%d")
        tm = datetime.now().strftime("%H%M%S")
        전략 = f'전략{st_no:02d}'

        def new_record():
            return { 
                '전략': 전략, '종목번호': code, '종목명': name, '매수일자': dt, '매수시간': tm, 
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

    def dbm_get_chart_data(self, code, cycle, tick=1, times=1):
        """차트 데이터 조회"""
        try:
            if not code: 
                return []
                
            rqname = f'{dc.scr.차트종류[cycle]}차트'
            trcode = dc.scr.차트TR[cycle]
            screen = dc.scr.화면[rqname]
            date = datetime.now().strftime('%Y%m%d')
            
            if cycle in ['mi', 'tk']:
                if tick == None:
                    tick = '1'
                elif isinstance(tick, int):
                    tick = str(tick)
                input = {'종목코드':code, '틱범위': tick, '수정주가구분': "1"}
                output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if cycle == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': "1"}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': "1"}
                output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            next = '0'
            dict_list = []
            while True:
                data, remain = self.answer('api', 'api_request', rqname, trcode, input, output, next=next, screen=screen)
                if data is None or len(data) == 0: 
                    break
                dict_list.extend(data)
                times -= 1
                if not remain or times <= 0: 
                    break
                next = '2' 
            
            if not dict_list:
                logging.warning(f'{rqname} 데이타 얻기 실패: code:{code}, cycle:{cycle}, tick:{tick}')
                return dict_list
            
            logging.debug(f'{rqname} 데이타 얻기: times:{times}, code:{code}, cycle:{cycle}, tick:{tick}, count:{len(dict_list)}')
            
            # 데이터 변환
            if cycle in ['mi', 'tk']:
                dict_list = [{
                    '종목코드': code,
                    '체결시간': item['체결시간'] if item['체결시간'] else datetime.now().strftime('%Y%m%d%H%M%S'),
                    '시가': abs(int(item['시가'])) if item['시가'] else 0,
                    '고가': abs(int(item['고가'])) if item['고가'] else 0,
                    '저가': abs(int(item['저가'])) if item['저가'] else 0,
                    '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                    '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                    '거래대금': 0,
                } for item in dict_list]
            else:
                dict_list = [{
                    '종목코드': code,
                    '일자': item['일자'] if item['일자'] else datetime.now().strftime('%Y%m%d'),
                    '시가': abs(int(item['시가'])) if item['시가'] else 0,
                    '고가': abs(int(item['고가'])) if item['고가'] else 0,
                    '저가': abs(int(item['저가'])) if item['저가'] else 0,
                    '현재가': abs(int(item['현재가'])) if item['현재가'] else 0,
                    '거래량': abs(int(item['거래량'])) if item['거래량'] else 0,
                    '거래대금': abs(int(item['거래대금'])) if item['거래대금'] else 0,
                } for item in dict_list]
            
            if cycle in ['dy', 'mi']:
                self.upsert_chart(dict_list, cycle, tick)
                self._mark_done_safe(code, cycle)
                #cht_dt.set_chart_data(code, dict_list, cycle, int(tick))
            
            return dict_list
        
        except Exception as e:
            logging.error(f'{rqname} 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []

    def start_request_chart_data(self):
        """차트 데이터 요청 스레드 시작"""
        if self.thread_run: 
            return
        self.thread_run = True
        self.thread_chart = threading.Thread(target=self.request_chart_data, daemon=True)
        self.thread_chart.start()
        logging.debug('차트 데이터 요청 스레드 시작')

    def stop_request_chart_data(self):
        """차트 데이터 요청 스레드 중지"""
        self.thread_run = False
        if self.thread_chart:
            self.thread_chart.join(timeout=2.0)
            self.thread_chart = None

    def request_chart_data(self):
        """차트 데이터 요청 메인 루프"""
        while self.thread_run:
            # 백그라운드 등록 처리
            self._process_pending_registrations()
            
            # 처리할 코드 복사 (락 최소화)
            codes_to_process = []
            if self._write_lock and self._write_lock.acquire(timeout=0.01):
                try:
                    for code, status in list(self.todo_code.items()):
                        if not status['mi'] or not status['dy']:
                            codes_to_process.append((code, status.copy()))
                finally:
                    self._write_lock.release()
            
            if not codes_to_process:
                time.sleep(0.001)
                continue

            # 락 밖에서 API 호출
            for code, status in codes_to_process:
                if not self.thread_run:  # 조기 종료 체크
                    break
                if not status['mi']: 
                    self.dbm_get_chart_data(code, cycle='mi', tick=1)
                if not status['dy']: 
                    self.dbm_get_chart_data(code, cycle='dy')

            time.sleep(0.001)

    def _process_pending_registrations(self):
        """백그라운드 등록 처리"""
        if not self._pending_lock.acquire(timeout=0.01):
            return
            
        try:
            if not self._pending_registrations:
                return
                
            codes_to_register = self._pending_registrations[:]
            self._pending_registrations.clear()
        finally:
            self._pending_lock.release()
        
        # 실제 등록
        for code in codes_to_register:
            self._register_code_internal(code)

    def _mark_done_safe(self, code, cycle):
        """안전한 완료 표시"""
        if not self._write_lock:
            return
            
        if self._write_lock.acquire(timeout=0.01):
            try:
                if code in self.todo_code:
                    self.todo_code[code][cycle] = True
                    if all(self.todo_code[code].values()):
                        # done_code는 별도 락으로 보호
                        with self._done_lock:
                            self.done_code.add(code)
                        del self.todo_code[code]
            finally:
                self._write_lock.release()

    def register_code(self, code):
        """종목 코드 등록 (최적화됨)"""
        if not self.thread_run:
            return False
        
        # 빠른 중복 체크 (락 프리)
        with self._done_lock:
            if code in self.done_code:
                return False
        
        # 즉시 등록 시도
        if self._register_code_internal(code):
            return True
        
        # 실패 시 백그라운드 등록
        with self._pending_lock:
            if code not in self._pending_registrations:
                self._pending_registrations.append(code)
                logging.debug(f"백그라운드 등록 예약: {code}")
        
        return True

    def _register_code_internal(self, code):
        """내부 등록 로직"""
        if not self._write_lock:
            return False
            
        if self._write_lock.acquire(timeout=0.01):
            try:
                # 중복 체크
                with self._done_lock:
                    if code in self.done_code:
                        return False
                
                if code in self.todo_code:
                    return False

                logging.debug(f'차트관리 종목코드 등록: {code}')
                self.todo_code[code] = {'mi': False, 'dy': False}
                return True
            finally:
                self._write_lock.release()
        
        return False

    def is_done(self, code):
        return True
        return code in self.done_code

    def update_script_chart(self, job):
        """실시간 차트 업데이트"""
        code = job['code']
        dictFID = job['dictFID']
        
        # 관리 대상 코드인지 빠른 체크
        is_managed = False
        with self._done_lock:
            is_managed = code in self.done_code
        
        if not is_managed and self._write_lock:
            # todo_code도 체크 (짧은 타임아웃)
            if self._write_lock.acquire(timeout=0.001):
                try:
                    is_managed = code in self.todo_code
                finally:
                    self._write_lock.release()
        if is_managed:
            cht_dt.update_chart(
                code, 
                abs(int(dictFID['현재가'])) if dictFID['현재가'] else 0,
                abs(int(dictFID['누적거래량'])) if dictFID['누적거래량'] else 0,
                abs(int(dictFID['누적거래대금'])) if dictFID['누적거래대금'] else 0,
                dictFID['체결시간']
            )