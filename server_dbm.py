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

    def upsert_conclusion(self, kind, code, name, qty, price, amount, ordno,  st_no, st_name, st_buy):
        """체결 정보를 데이터베이스에 저장하고 손익 계산"""
        table = dc.ddb.CONC_TABLE_NAME
        record = None
        dt = datetime.now().strftime("%Y%m%d")
        tm = datetime.now().strftime("%H%M%S")
        전략 = f'전략{st_no:02d}'

        def new_record():
            return { '전략': 전략, '종목번호': code, '종목명': name, '매수일자': dt, '매수시간': tm, '매수수량': qty, '매수가': price, '매수금액': amount, \
                '매도수량': 0, '매수전략': st_buy, '전략명칭': st_name, }

        try:
            # 1. 대상 레코드 준비 (기존 레코드 찾기 또는 새 레코드 생성)
            if kind == '매수':
                # 미매도된 레코드 조회
                sql = f"SELECT * FROM {table} WHERE 종목번호 = ? AND 매수수량 > 매도수량 ORDER BY 매수일자 DESC, 매수시간 DESC LIMIT 1"
                result = self.execute_query(sql, db='db', params=(code,))
                
                if result:
                    record = result[0]
                    record.update({'매수수량': qty, '매수가': price, '매수금액': amount})
                else:
                    # 신규 레코드
                    record = new_record()
                    record['매수번호'] = ordno
            
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

            매수수수료 = int(row['매수가'] * row['매도수량'] * row['수수료율'] / 10) * 10 # 매도 수량만큼 제비용 계산
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


    # 3. 특정 날짜의 손익 계산 함수
    def calculate_profit_for_date(self, date, fee_rate=None, tax_rate=None):
        """특정 날짜의 매도건에 대한 손익 계산 및 profit 테이블에 저장"""
        try:
            # 해당 날짜의 매도체결 데이터 조회
            sell_sql = f"""
                SELECT *
                FROM {dc.ddb.MON_TABLE_NAME}
                WHERE DATE(처리일시) = ? AND 구분 = '매도체결'
                ORDER BY 처리일시 ASC
            """
            sells = self.execute_query(sell_sql, db='db', params=(date,))
            
            if not sells:
                logging.info(f"{date} 날짜에 매도체결 데이터가 없습니다.")
                return []
            
            # 이미 처리된 매도 기록인지 확인 및 삭제
            self.execute_query(
                f"DELETE FROM {dc.ddb.PRO_TABLE_NAME} WHERE 매도일자 = ?", 
                db='db', 
                params=(date,)
            )
            
            profit_records = []
            
            for sell in sells:
                # 해당 매도건에 대한 매수 데이터 조회 (동일 전략, 동일 종목)
                buy_sql = f"""
                    SELECT *
                    FROM {dc.ddb.MON_TABLE_NAME}
                    WHERE 전략 = ? AND 종목코드 = ? AND 구분 = '매수체결' AND 매수수량 > 0
                    ORDER BY 처리일시 ASC
                """
                buys = self.execute_query(
                    buy_sql, 
                    db='db', 
                    params=(sell['전략'], sell['종목코드'])
                )
                
                if not buys:
                    logging.warning(f"매도체결(id:{sell['id']})에 대응하는 매수체결 데이터가 없습니다.")
                    continue
                
                # 매수금액과 매수수량 합계 계산
                total_buy_amount = 0
                total_buy_quantity = 0
                
                for buy in buys:
                    # 매수수량이 매도수량을 충족할 때까지만 계산
                    if total_buy_quantity >= sell['매도수량']:
                        break
                    
                    buy_quantity = min(buy['매수수량'], sell['매도수량'] - total_buy_quantity)
                    # 매수가 * 실제 사용되는 매수수량
                    buy_amount = buy['매수가'] * buy_quantity
                    
                    total_buy_quantity += buy_quantity
                    total_buy_amount += buy_amount
                
                # 평균 매수가 계산
                avg_buy_price = total_buy_amount / total_buy_quantity if total_buy_quantity > 0 else 0
                
                # 비용 계산
                sell_amount = sell['매도가'] * sell['매도수량']
                buy_commission = int(total_buy_amount * fee_rate / 10) * 10
                sell_commission = int(sell_amount * fee_rate / 10) * 10
                tax = int(sell_amount * tax_rate)
                total_expense = buy_commission + sell_commission + tax
                
                # 손익 및 손익률 계산
                profit = sell_amount - total_buy_amount - total_expense
                profit_rate = (profit / total_buy_amount) * 100 if total_buy_amount > 0 else 0
                
                # 날짜와 시간 분리
                earliest_buy_time = buys[0]['처리일시'] if buys else ''
                earliest_buy_date = earliest_buy_time.split(' ')[0] if ' ' in earliest_buy_time else ''
                earliest_buy_time_only = earliest_buy_time.split(' ')[1] if ' ' in earliest_buy_time else ''
                
                sell_datetime = sell['처리일시']
                sell_date = sell_datetime.split(' ')[0] if ' ' in sell_datetime else ''
                sell_time_only = sell_datetime.split(' ')[1] if ' ' in sell_datetime else ''
                
                # profit 테이블에 데이터 저장
                profit_data = {
                    '전략': sell['전략'],
                    '전략명칭': sell['전략명칭'],
                    '종목코드': sell['종목코드'],
                    '종목명': sell['종목명'],
                    '매수수량': total_buy_quantity,
                    '매수가': avg_buy_price,
                    '매수금액': total_buy_amount,
                    '매도수량': sell['매도수량'],
                    '매도가': sell['매도가'],
                    '매도금액': sell_amount,
                    '매수수수료': buy_commission,
                    '매도수수료': sell_commission,
                    '거래세': tax,
                    '제비용': total_expense,
                    '손익금액': profit,
                    '손익율': profit_rate,
                    '매수일자': earliest_buy_date,
                    '매수시간': earliest_buy_time_only,
                    '매도일자': sell_date,
                    '매도시간': sell_time_only
                }
                
                self.table_upsert(db='db', table=dc.ddb.PRO_TABLE_NAME, dict_data=profit_data)
                profit_records.append(profit_data)
                
            self.db.commit()
            logging.info(f"{date} 날짜의 손익 계산 완료")
            return profit_records
            
        except Exception as e:
            logging.error(f"손익 계산 중 오류 발생: {e}", exc_info=True)
            self.db.rollback()
            return []

    # 4. 손익 조회 함수
    def get_profit_by_date(self, date):
        """특정 날짜의 손익 데이터 조회"""
        try:
            sql = dc.ddb.PRO_SELECT_DATE
            result = self.execute_query(sql, db='db', params=(date,))
            return result
        except Exception as e:
            logging.error(f"손익 조회 중 오류 발생: {e}", exc_info=True)
            return []

    # 5-1. 날짜별 전체 손익 집계 함수
    def get_profit_total_summary_by_date(self, date):
        """특정 날짜의 전체 손익 집계 데이터 조회"""
        try:
            # 해당 날짜의 전체 집계 조회 - 인덱스를 활용하도록 쿼리 최적화
            sql = f"""
                SELECT 
                    COUNT(*) as 총매매건수,
                    SUM(매수금액) as 총매수금액,
                    SUM(매도금액) as 총매도금액,
                    SUM(제비용) as 총제비용,
                    SUM(손익금액) as 총손익금액,
                    CASE 
                        WHEN SUM(매수금액) > 0 THEN (SUM(손익금액) / SUM(매수금액)) * 100 
                        ELSE 0 
                    END as 총수익율
                FROM {dc.ddb.PRO_TABLE_NAME}
                WHERE 매도일자 = ?
            """
            result = self.execute_query(sql, db='db', params=(date,))
            return result[0] if result else {}
            
        except Exception as e:
            logging.error(f"전체 손익 집계 중 오류 발생: {e}", exc_info=True)
            return {}

    # 5-2. 날짜별 전략별 손익 집계 함수
    def get_profit_strategy_summary_by_date(self, date):
        """특정 날짜의 전략별 손익 집계 데이터 조회"""
        try:
            # 전략별 집계 조회 - 인덱스를 활용하도록 쿼리 최적화
            sql = f"""
                SELECT 
                    전략,
                    전략명칭,
                    COUNT(*) as 매매건수,
                    SUM(매수금액) as 매수금액,
                    SUM(매도금액) as 매도금액,
                    SUM(제비용) as 제비용,
                    SUM(손익금액) as 손익금액,
                    CASE 
                        WHEN SUM(매수금액) > 0 THEN (SUM(손익금액) / SUM(매수금액)) * 100 
                        ELSE 0 
                    END as 수익율
                FROM {dc.ddb.PRO_TABLE_NAME}
                WHERE 매도일자 = ?
                GROUP BY 전략, 전략명칭
                ORDER BY 손익금액 DESC
            """
            result = self.execute_query(sql, db='db', params=(date,))
            return result
            
        except Exception as e:
            logging.error(f"전략별 손익 집계 중 오류 발생: {e}", exc_info=True)
            return []

    # 5-3. 날짜별 종목별 손익 집계 함수
    def get_profit_stock_summary_by_date(self, date):
        """특정 날짜의 종목별 손익 집계 데이터 조회"""
        try:
            # 종목별 집계 조회 - 인덱스를 활용하도록 쿼리 최적화
            sql = f"""
                SELECT 
                    종목코드,
                    종목명,
                    COUNT(*) as 매매건수,
                    SUM(매수금액) as 매수금액,
                    SUM(매도금액) as 매도금액,
                    SUM(제비용) as 제비용,
                    SUM(손익금액) as 손익금액,
                    CASE 
                        WHEN SUM(매수금액) > 0 THEN (SUM(손익금액) / SUM(매수금액)) * 100 
                        ELSE 0 
                    END as 수익율
                FROM {dc.ddb.PRO_TABLE_NAME}
                WHERE 매도일자 = ?
                GROUP BY 종목코드, 종목명
                ORDER BY 손익금액 DESC
            """
            result = self.execute_query(sql, db='db', params=(date,))
            return result
            
        except Exception as e:
            logging.error(f"종목별 손익 집계 중 오류 발생: {e}", exc_info=True)
            return []

    # 5-4. 날짜별 모든 손익 집계 함수 (이전 함수 호환성 유지)
    def get_profit_summary_by_date(self, date):
        """특정 날짜의 모든 손익 집계 데이터 조회 (이전 함수 호환성 유지)"""
        try:
            return {
                'total': self.get_profit_total_summary_by_date(date),
                'by_strategy': self.get_profit_strategy_summary_by_date(date),
                'by_stock': self.get_profit_stock_summary_by_date(date)
            }
        except Exception as e:
            logging.error(f"손익 집계 중 오류 발생: {e}", exc_info=True)
            return {
                'total': {},
                'by_strategy': [],
                'by_stock': []
            }
    