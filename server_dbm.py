from public import dc, get_path
from classes import la
from datetime import datetime
import logging
import sqlite3
import os

class DBMServer:
    def __init__(self):
        self.daily_db = None
        self.daily_cursor = None
        self.db = None
        self.cursor = None

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

        # Conclusion Table
        sql = self.create_table_sql('conclusion', dc.ddb.CONC_COLUMNS)
        self.cursor.execute(sql)
        for index in dc.ddb.CONC_INDEXES.values():
            self.cursor.execute(index)

        # 모니터 테이블
        sql = self.create_table_sql('monitor', dc.ddb.MON_COLUMNS)
        self.cursor.execute(sql)
        for index in dc.ddb.MON_INDEXES.values():
            self.cursor.execute(index)
        self.db.commit()

        # 매일 생성 디비
        db_daily = f'abc_{datetime.now().strftime("%Y%m%d")}.db'
        path_daily = os.path.join(get_path(dc.fp.DB_PATH), db_daily)
        self.daily_db = sqlite3.connect(path_daily)
        # 아래 람다식은 튜플로 받은 레코드를 딕셔너리로 변환하는 함수
        self.daily_db.row_factory = lambda cursor, row: { col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        # self.daily_db.row_factory = sqlite3.Row # 직렬화 에러
        self.daily_cursor = self.daily_db.cursor()

        # 주문 테이블
        sql = self.create_table_sql('orders', dc.ddb.ORD_COLUMNS)
        self.daily_cursor.execute(sql)
        for index in dc.ddb.ORD_INDEXES.values():
            self.daily_cursor.execute(index)

        # 체결 테이블
        sql = self.create_table_sql('trades', dc.ddb.TRD_COLUMNS)
        self.daily_cursor.execute(sql)
        for index in dc.ddb.TRD_INDEXES.values():
            self.daily_cursor.execute(index)
        self.daily_db.commit()

    # 테이블 생성 SQL문 생성 함수
    def create_table_sql(self, table_name, fields):
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
        return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(field_definitions)});"

    def send_result(self, result, error=None):
        order = 'dbm_query_result'
        work = {
            'result': result,
            'error': error
        }
        la.work('aaa', order, **work)

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

    def conclusion_upsert_buy(self, row):
        try:
            columns = ','.join(row.keys())
            column_str = ', '.join(['?'] * len(row))
            params = tuple(row.values())
            sql = f"INSERT OR REPLACE INTO conclusion ({columns}) VALUES ({column_str})"
            self.execute_query(sql, db='db', params=params)
        except Exception as e:
            logging.error(f"conclusion_upsert_buy error: {e}", exc_info=True)

    def conclusion_upsert_sell(self, row):
        try:
            query = "SELECT * FROM conclusion WHERE 매수일자=? AND 매수번호=?"
            cursor = self.db.cursor()
            cursor.execute(query, (row['매수일자'], row['매수번호']))
            db_row = cursor.fetchone()
            if not db_row:
                logging.error(f"conclusion_upsert_sell error: 매수일자={row['매수일자']} 매수번호={row['매수번호']} not found")
                return
            if row['체결량'] == db_row['매수수량']:
                row['매도수량'] = row['체결량']
                row['매도가'] = row['체결가']
                row['매도금액'] = row['체결누계금액']
            else:
                row['매도수량'] = db_row['매도수량'] + int(row['단위체결량'])
                row['매도가'] = row['체결가']
                row['매도금액'] = db_row['매도금액'] + int(row['단위체결량']) * int(row['단위체결가'])

            all_trade = row['매도수량'] == db_row['매수수량']

            매수수수료 = int(row['매수가'] * row['매도수량'] * row['수수료율'] / 10) * 10
            매도수수료 = int(row['매도금액'] * row['수수료율'] / 10) * 10
            거래세 = int(row['매도금액'] * row['거래세율'])

            row['제비용'] = 매수수수료 + 매도수수료 + 거래세 if all_trade else 0
            row['손익금액'] = row['매도금액'] - row['매수금액'] - row['제비용'] if all_trade else 0
            row['손익율'] = round(row['손익금액'] / row['매수금액'] * 100, 2) if all_trade else 0

            col_list = []
            val_list = []
            for k, v in row.items():
                if k in db_row.keys():
                    val_list.append(v)
                    col_list.append(k)
            columns = ','.join(col_list)
            column_str = ', '.join(['?'] * len(col_list))
            params = tuple(val_list)
            sql = f"INSERT OR REPLACE INTO conclusion ({columns}) VALUES ({column_str})"
            self.execute_query(sql, db='db', params=params)
        except Exception as e:
            logging.error(f"conclusion_upsert_sell error: {e}", exc_info=True)

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
