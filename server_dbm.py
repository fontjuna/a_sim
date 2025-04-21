from public import dc, get_path
from classes import la
from datetime import datetime, timedelta
import logging
import sqlite3
import os

class DBMServer:
    def __init__(self):
        self.db = None
        self.cursor = None
        self.daily_db = None
        self.daily_cursor = None
        self.fee_rate = 0.00015
        self.tax_rate = 0.0015

        self.init_db()

    def stop(self):
        if self.daily_db is not None:
            if self.daily_cursor is not None:
                self.daily_cursor.close()
                self.daily_cursor = None
            self.daily_db.commit()
            self.daily_db.close()
            self.daily_db = None
        if self.db is not None:
            if self.cursor is not None:
                self.cursor.close()
                self.cursor = None
            self.db.commit()
            self.db.close()
            self.db = None

    def set_log_level(self, level):
        logging.getLogger().setLevel(level)
        logging.debug(f'DBM 로그 레벨 설정: {level}')

    # 디비 초기화 --------------------------------------------------------------------------------------------------
    def init_db(self):
        logging.debug('dbm_init_db')

        # 통합 디비
        db = 'abc.db'
        path = os.path.join(get_path(dc.fp.DB_PATH), db)
        self.db = sqlite3.connect(path)
        # 아래 람다식은 튜플로 받은 레코드를 딕셔너리로 변환하는 함수
        self.db.row_factory = lambda cursor, row: { col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        # self.daily_db.row_factory = sqlite3.Row # 직렬화 에러
        self.cursor = self.db.cursor()

        # trades 테이블
        sql = self.create_table_sql(dc.ddb.TRD_TABLE_NAME, dc.ddb.TRD_COLUMNS)
        self.cursor.execute(sql)
        for index in dc.ddb.TRD_INDEXES.values():
            self.cursor.execute(index)

        # Conclusion Table
        sql = self.create_table_sql(dc.ddb.CONC_TABLE_NAME, dc.ddb.CONC_COLUMNS)
        self.cursor.execute(sql)
        for index in dc.ddb.CONC_INDEXES.values():
            self.cursor.execute(index)

        #self.cleanup_old_data()

        self.db.commit()

        # # 매일 생성 디비
        # db_daily = f'abc_{datetime.now().strftime("%Y%m%d")}.db'
        # path_daily = os.path.join(get_path(dc.fp.DB_PATH), db_daily)
        # self.daily_db = sqlite3.connect(path_daily)
        # # 아래 람다식은 튜플로 받은 레코드를 딕셔너리로 변환하는 함수
        # self.daily_db.row_factory = lambda cursor, row: { col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        # # self.daily_db.row_factory = sqlite3.Row # 직렬화 에러
        # self.daily_cursor = self.daily_db.cursor()

        # # 주문 테이블
        # sql = self.create_table_sql(dc.ddb.ORD_TABLE_NAME, dc.ddb.ORD_COLUMNS)
        # self.daily_cursor.execute(sql)
        # for index in dc.ddb.ORD_INDEXES.values():
        #     self.daily_cursor.execute(index)

        # self.daily_db.commit()

    # 테이블 생성 SQL문 생성 함수
    def create_table_sql(self, table_name, fields, pk_columns=None):
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

    def send_result(self, result, error=None):
        order = 'dbm_query_result'
        work = {
            'result': result,
            'error': error
        }
        la.work('admin', order, **work)

    def execute_query(self, sql, db='daily', params=None):
        try:
            cursor = self.daily_db.cursor() if db == 'daily' else self.db.cursor()
            if params: cursor.execute(sql, params)
            else: cursor.execute(sql)

            if sql.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
                return result
            else:
                self.daily_db.commit() if db == 'daily' else self.db.commit()
                return cursor.rowcount

        except Exception as e:
            logging.error(f"Database error: {e}", exc_info=True)
            self.daily_db.rollback() if db == 'daily' else self.db.rollback()
            self.send_result(None, e)

    def table_upsert(self, db, table, dict_data):
        try:
            columns = ','.join(dict_data.keys())
            column_str = ', '.join(['?'] * len(dict_data))
            params = tuple(dict_data.values())
            sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({column_str})"
            self.execute_query(sql, db=db, params=params)
        except Exception as e:
            logging.error(f"table_upsert error: {e}", exc_info=True)

    def upsert_conclusion(self, kind, code, name, qty, price, amount, ordno,  st_no, st_name, st_buy):
        """체결 정보를 데이터베이스에 저장하고 손익 계산"""
        table = dc.ddb.CONC_TABLE_NAME
        record = None
        dt = datetime.now().strftime("%Y%m%d")
        tm = datetime.now().strftime("%H%M%S")
        전략 = f'전략{st_no:02d}'

        def new_record():
            return { '전략': 전략, '종목번호': code, '종목명': name, '매수일자': dt, '매수시간': tm, '매수수량': qty, '매수가': price, '매수금액': amount, \
                '매수번호': ordno, '매도수량': 0, '매수전략': st_buy, '전략명칭': st_name, }

        try:
            # 1. 대상 레코드 준비 (기존 레코드 찾기 또는 새 레코드 생성)
            if kind == '매수':
                # 미매도된 레코드 조회
                sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수일자 = ? AND 매수번호 = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(code, dt, ordno))
                
                if result:
                    record = result[0]
                    record.update({'매수수량': qty, '매수가': price, '매수금액': amount})
                else:
                    # 신규 레코드
                    record = new_record()
            
            elif kind == '매도':
                # 매도 기록 확인
                sql = f"SELECT * FROM {table} WHERE 매도일자 = ? AND 매도번호 = ? LIMIT 1"
                result = self.execute_query(sql, db='db', params=(dt, ordno))
                
                if result:
                    record = result[0]
                else:
                    # 미매도 매수 레코드 확인
                    sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수수량 > 매도수량 ORDER BY 매수일자 ASC, 매수시간 ASC LIMIT 1"
                    result = self.execute_query(sql, db='db', params=(code,))
                    
                    if result:
                        record = result[0]
                    else:
                        # 신규 레코드 (매수 기록 없는 경우 자동 생성)
                        record = new_record()

                # 매도 처리용 기존 매수가 결정
                buy_price = record.get('매수가', price)
                
                # v. 매도 정보 업데이트
                record['매도번호'] = ordno
                record['매도일자'] = dt
                record['매도시간'] = tm
                
                # z. 매도 금액, 손익 정보 업데이트
                record['매도수량'] = qty
                record['매도가'] = price
                record['매도금액'] = amount
                
                # 손익 계산
                buy_amount = qty * buy_price  # 매도수량 * 매수가
                buy_fee = int(buy_amount * self.fee_rate / 10) * 10
                sell_fee = int(amount * self.fee_rate / 10) * 10
                tax = int(amount * self.tax_rate)
                total_fee = buy_fee + sell_fee + tax
                profit = amount - buy_amount - total_fee
                profit_rate = (profit / buy_amount) * 100 if buy_amount > 0 else 0
                
                record['제비용'] = total_fee
                record['손익금액'] = profit
                record['손익율'] = round(profit_rate, 2)
                
                # 매수 수량보다 매도 수량이 많은 경우 매수 수량도 갱신
                # 이경우는 해당 매수가 없었던 경우
                if record.get('매수수량', 0) < qty:
                    record['매수수량'] = qty
                    record['매수가'] = price
                    record['매수금액'] = amount
            
            # 3. 최종 데이터베이스 업데이트 (한 번만 수행)
            self.table_upsert('db', table, record)
            
            return True
        except Exception as e:
            logging.error(f"upsert_conclusion error: {e}", exc_info=True)
            return False
        
    def update_charts(self, params):
        def make_time_frames(code, price, volume, timestamp, periods=[1,3,5]):
            for period in periods:
                period_key = timestamp.minute // period

                query = "SELECT * FROM charts WHERE code=? AND period=? ORDER BY timestamp DESC LIMIT 1"
                self.cursor.execute(query, (code, period_key))
                last_data = self.cursor.fetchone()

                if not last_data:
                    data = {
                        'code': code,
                        'period': period_key,
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': volume,
                        'timestamp': timestamp
                    }
                else:
                    data = last_data.copy()
                    data.update({
                        'high': max(last_data['high'], price),
                        'low': min(last_data['low'], price),
                        'close': price,
                        'volume': last_data['volume'] + volume
                    })

                sql = "INSERT OR REPLACE INTO charts VALUES (?,?,?,?,?,?,?,?)"
                self.execute_query(sql, 'daily', tuple(data.values()))
        make_time_frames(params['code'], params['price'], params['volume'], params['stamp'])

    def check_ma_down(self, params):
        code, tick, ma = params['code'], params['tick'], params['ma']

        query = """
        SELECT * FROM charts
        WHERE code=? AND period=?
        ORDER BY timestamp DESC LIMIT 4
        """
        self.cursor.execute(query, (code, tick))
        candles = self.cursor.fetchall()

        if len(candles) < 4:
            return False

        last_prices = [c['close'] for c in candles]
        is_three_up = all(last_prices[i] > last_prices[i-1] for i in range(1, 3))
        is_current_down = last_prices[3] < last_prices[2]

        return is_three_up and is_current_down

    def receive_current_price(self, code, dictFID):
        pass

    # 2. 오래된 데이터 정리 함수
    def cleanup_old_data(self):
        """monitor 테이블에서 3개월 이상 지난 데이터 삭제"""
        try:
            # 현재 날짜로부터 3개월 이전 날짜 계산
            three_months_ago = datetime.now() - timedelta(days=90)
            date_str = three_months_ago.strftime('%Y-%m-%d')
            
            # 3개월 이전 데이터 삭제
            sql = f"DELETE FROM {dc.ddb.MON_TABLE_NAME} WHERE DATE(처리일시) < ?"
            self.execute_query(sql, db='db', params=(date_str,))
            
            deleted_rows = self.cursor.rowcount
            logging.info(f"monitor 테이블에서 {date_str} 이전 데이터 {deleted_rows}건 삭제 완료")
            
            # 데이터베이스 최적화 (VACUUM)
            self.execute_query("VACUUM", db='db')
            
        except Exception as e:
            logging.error(f"오래된 데이터 정리 중 오류 발생: {e}", exc_info=True)

    def get_minute_data(self, code, tick=3, all=False):
        df = la.answer('admin', 'dbm_get_minute_data', code=code, tick=tick, all=all)
        return df

