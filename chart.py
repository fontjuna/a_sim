from public import gm, dc
from classes import la
from typing import Dict, List, Any, Union, Optional, Tuple
from datetime import datetime
import json
import numpy as np
import pandas as pd
import logging

class ChartData:
    """차트 데이터를 관리하는 싱글톤 클래스"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChartData, cls).__new__(cls)
            cls._instance._data = {}
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._data = {}
        self.types = {'mi': 'mi', 'dy': 'dy', 'wk': 'wk', 'mo': 'mo'}
        self._loading_states = {}
        import threading
        self._lock = threading.Lock()
    
    def _init_code_data(self, code: str):
        """코드별 데이터 초기화 - 1분봉만 초기화"""
        # 데이터 구조 초기화
        if code not in self._data:
            self._data[code] = {'mi': {1: []}, 'dy': [], 'wk': [], 'mo': []}
        
        # 1분봉 데이터만 로드
        if self._data[code]['mi'][1] == []:
            self._load_minute_data(code, 1)

    def _is_loading(self, code: str, chart_type: str, cycle: int = None):
        """특정 차트 데이터가 현재 로딩 중인지 확인"""
        key = f"{code}:{chart_type}"
        if cycle is not None:
            key += f":{cycle}"
        return self._loading_states.get(key, False)

    def _set_loading_state(self, code: str, chart_type: str, cycle: int = None, state: bool = True):
        """차트 데이터 로딩 상태 설정"""
        key = f"{code}:{chart_type}"
        if cycle is not None:
            key += f":{cycle}"
        self._loading_states[key] = state

    def _load_minute_data(self, code: str, cycle: int):
        """분봉 데이터 로드 (로딩 상태 관리 추가)"""
        # 이미 로딩 중이면 건너뜀
        if self._is_loading(code, 'mi', cycle):
            logging.debug(f'분봉 차트 데이터 이미 로딩 중: {code} {cycle}')
            return
        
        # 로딩 상태 설정
        with self._lock:
            if self._is_loading(code, 'mi', cycle):  # 더블 체크
                return
            self._set_loading_state(code, 'mi', cycle, True)
        
        try:
            data = self._get_chart_data(code, 'mi', cycle)
            for item in data:
                datetime_str = item.get('체결시간', '')
                self._data[code]['mi'][cycle].append(self._create_candle(
                    date=datetime_str[:8],
                    time=datetime_str[8:14],
                    item=item
                ))
            if self._data[code]['mi'][cycle]:
                logging.debug(f'분봉 차트 데이터 로드 완료: {code} {cycle} \n{pd.DataFrame(self._data[code]["mi"][cycle])}')
        except Exception as e:
            logging.error(f'분봉 차트 데이터 로드 오류: {code} {cycle} - {e}')
            # 오류 발생 시 데이터 초기화
            self._data[code]['mi'][cycle] = []
        finally:
            # 로딩 상태 해제
            self._set_loading_state(code, 'mi', cycle, False)

    def _load_period_data(self, code: str, chart_type: str):
        """일/주/월봉 데이터 로드 (로딩 상태 관리 추가)"""
        if chart_type not in ['dy', 'wk', 'mo']:
            return
        
        # 이미 데이터가 로드되어 있거나 로딩 중이면 건너뜀
        if self._data[code][chart_type] or self._is_loading(code, chart_type):
            return
        
        # 로딩 상태 설정
        with self._lock:
            if self._data[code][chart_type] or self._is_loading(code, chart_type):  # 더블 체크
                return
            self._set_loading_state(code, chart_type, state=True)
        
        try:
            data = self._get_chart_data(code, chart_type)
            for item in data:
                self._data[code][chart_type].append(self._create_candle(
                    date=item.get('일자', ''),
                    time='',
                    item=item
                ))
            if self._data[code][chart_type]:
                logging.debug(f'차트 데이터 로드 완료: {code} {chart_type}\n{pd.DataFrame(self._data[code][chart_type])}')
        except Exception as e:
            logging.error(f'차트 데이터 로드 오류: {code} {chart_type} - {e}')
            # 오류 발생 시 데이터 초기화
            self._data[code][chart_type] = []
        finally:
            # 로딩 상태 해제
            self._set_loading_state(code, chart_type, state=False)

    def _create_candle(self, date, time, item):
        """캔들 데이터 생성"""
        return {
            'date': date,
            'time': time,
            'open': abs(int(item.get('시가', '0'))),
            'high': abs(int(item.get('고가', '0'))),
            'low': abs(int(item.get('저가', '0'))),
            'close': abs(int(item.get('현재가', '0'))),
            'volume': abs(int(item.get('거래량', '0'))),
            'amount': abs(int(item.get('거래대금', '0')))
        }
    
    def update_price(self, code: str, price: int, volume: int, amount: int, datetime_str: str):
        """현재가, 거래량, 거래금액 업데이트"""
        #if code not in self._data:
        self._init_code_data(code)
        
        # 날짜와 시간 추출
        date = datetime_str[:8]  # yyyymmdd
        time = datetime_str[8:14]  # hhmmss
        
        self._update_minute_data(code, time, date, price, volume, amount)
        self._update_daily_data(code, date, price, volume, amount)
    
    def _update_minute_data(self, code: str, time: str, date: str, price: int, volume: int, amount: int):
        """1분봉 데이터 업데이트"""
        if 1 not in self._data[code]['mi']:
            self._data[code]['mi'][1] = []
        
        # 새 분봉 또는 기존 분봉 업데이트
        if not self._data[code]['mi'][1] or self._is_new_minute(time, self._data[code]['mi'][1][0]['time']):
            # 새 분봉 추가
            new_candle = {
                'date': date, 'time': time,
                'open': price, 'high': price, 'low': price, 'close': price,
                'volume': volume, 'amount': amount
            }
            self._data[code]['mi'][1].insert(0, new_candle)
        else:
            # 현재 분봉 업데이트
            current = self._data[code]['mi'][1][0]
            current['high'] = max(current['high'], price)
            current['low'] = min(current['low'], price)
            current['close'] = price
            current['volume'] = volume
            current['amount'] = amount
    
    def _is_new_minute(self, current_time: str, last_time: str) -> bool:
        return current_time[:4] != last_time[:4]
    
    def _update_daily_data(self, code: str, date: str, price: int, volume: int, amount: int):
        """일봉 데이터 업데이트"""
        if not self._data[code]['dy'] or self._data[code]['dy'][0]['date'] != date:
            # 새 일봉 추가
            new_day = {
                'date': date, 'time': '',
                'open': price, 'high': price, 'low': price, 'close': price,
                'volume': volume, 'amount': amount
            }
            self._data[code]['dy'].insert(0, new_day)
        else:
            # 현재 일봉 업데이트
            current = self._data[code]['dy'][0]
            current['high'] = max(current['high'], price)
            current['low'] = min(current['low'], price)
            current['close'] = price
            current['volume'] = volume
            current['amount'] = amount
    
    def get_data(self, code: str, chart_type: str, cycle: int = 1) -> List[Dict]:
        """차트 데이터 가져오기 (로딩 상태 관리 추가)"""
        # 코드가 없으면 초기화
        if code not in self._data:
            with self._lock:
                if code not in self._data:  # 더블 체크
                    self._init_code_data(code)
        
        if chart_type == 'mi':
            # 분봉 데이터
            if cycle not in self._data[code]['mi']:
                with self._lock:
                    if cycle not in self._data[code]['mi']:  # 더블 체크
                        self._data[code]['mi'][cycle] = []
                        if cycle > 1 and self._data[code]['mi'][1]:
                            # 1분봉 데이터가 있으면 계산
                            self._calculate_cycle_data(code, cycle)
                        else:
                            # 없으면 서버에서 로드
                            self._load_minute_data(code, cycle)
                            
            return self._data[code]['mi'].get(cycle, [])
        else:
            # 일/주/월봉 데이터
            if not self._data[code][chart_type]:
                # 서버에서 데이터 로드 (이미 로딩 중이면 _load_period_data 내에서 처리)
                self._load_period_data(code, chart_type)
                
                # 당일 데이터가 있고 1분봉 데이터가 있으면 당일 데이터 보정
                if self._data[code]['mi'][1] and self._data[code][chart_type]:
                    today = datetime.now().strftime('%Y%m%d')
                    if self._data[code][chart_type][0]['date'] == today:
                        # 당일 데이터 보정
                        self._update_today_data(code, chart_type)
            
            return self._data[code].get(chart_type, [])
        
    def _update_today_data(self, code: str, chart_type: str):
        """1분봉 데이터를 이용해 당일 일/주/월봉 데이터 보정"""
        if not self._data[code]['mi'][1] or not self._data[code][chart_type]:
            return
            
        today = datetime.now().strftime('%Y%m%d')
        day_data = self._data[code][chart_type][0]
        
        # 당일 데이터인지 확인
        if day_data['date'] != today:
            return
            
        # 1분봉 데이터로 당일 데이터 보정
        minute_data = [d for d in self._data[code]['mi'][1] if d['date'] == today]
        if minute_data:
            day_data['high'] = max(day_data['high'], max(d['high'] for d in minute_data))
            day_data['low'] = min(day_data['low'], min(d['low'] for d in minute_data))
            day_data['close'] = minute_data[0]['close']
            day_data['volume'] = sum(d['volume'] for d in minute_data)
            day_data['amount'] = sum(d['amount'] for d in minute_data)

    def _calculate_cycle_data(self, code: str, cycle: int):
        """다른 주기의 분봉 데이터 계산"""
        if 1 not in self._data[code]['mi'] or cycle <= 1:
            return
        
        mi_1 = self._data[code]['mi'][1]
        result = []
        
        for i in range(0, len(mi_1), cycle):
            chunk = mi_1[i:i+cycle]
            if not chunk:
                continue
            
            new_candle = {
                'date': chunk[0]['date'],
                'time': chunk[0]['time'],
                'open': chunk[0]['open'],
                'high': max(c['high'] for c in chunk),
                'low': min(c['low'] for c in chunk),
                'close': chunk[-1]['close'] if len(chunk) > 1 else chunk[0]['close'],
                'volume': sum(c['volume'] for c in chunk),
                'amount': sum(c['amount'] for c in chunk)
            }
            result.insert(0, new_candle)
        
        self._data[code]['mi'][cycle] = result
    
    def _get_chart_data(self, code, chart_type, cycle=None):
        """차트 데이터 가져오기 (외부에서 구현되는 함수)"""
        try:
            rqname = f'{dc.scr.차트종류[chart_type]}챠트'
            trcode = dc.scr.차트TR[chart_type]
            screen = dc.scr.화면[rqname]
            date = datetime.now().strftime('%Y%m%d')

            if chart_type == 'mi':
                input = {'종목코드':code, '틱범위': cycle, '수정주가구분': 1}
                output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
            else:
                if chart_type == 'dy':
                    input = {'종목코드':code, '기준일자': date, '수정주가구분': 1}
                else:
                    input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': 1}
                output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

            next = '0'
            all = False #if chart_type in ['mi', 'dy'] else True
            dict_list = []
            while True:
                data, remain = la.answer('admin', 'com_SendRequest', rqname, trcode, input, output, next, screen, 'dict_list', 5)
                if data is None or len(data) == 0: break
                dict_list.extend(data)
                if not (remain and all): break
                next = '2'
            
            if not dict_list:
                logging.warning(f'챠트 데이타 얻기 실패: code:{code}, chart_type:{chart_type}, cycle:{cycle}, dict_list:"{dict_list}"')
                return []
            
            if chart_type == 'mi':
                #logging.debug(f'분봉 챠트 데이타 얻기: code:{code}, chart_type:{chart_type}, cycle:{cycle}, dict_list:"{dict_list[-1:]}"')
                dict_list = [{
                    '종목코드': code,
                    '체결시간': item['체결시간'],
                    '현재가': abs(int(item['현재가'])),
                    '시가': abs(int(item['시가'])),
                    '고가': abs(int(item['고가'])),
                    '저가': abs(int(item['저가'])),
                    '거래량': abs(int(item['거래량'])),
                    '거래대금': 0#abs(int(item['거래대금'])),
                } for item in dict_list]
            else:
                dict_list = [{
                    '종목코드': code,
                    '일자': item['일자'],
                    '현재가': abs(int(item['현재가'])),
                    '시가': abs(int(item['시가'])),
                    '고가': abs(int(item['고가'])),
                    '저가': abs(int(item['저가'])),
                    '거래량': abs(int(item['거래량'])),
                    '거래대금': abs(int(item['거래대금'])),
                } for item in dict_list]
            return dict_list
        
        except Exception as e:
            logging.error(f'챠트 데이타 얻기 오류: {type(e).__name__} - {e}', exc_info=True)
            return []

class ChartManager:
    """차트 매니저 클래스, 수식관리자 기본함수 구현"""
    
    def __init__(self, chart='dy', cycle=1):
        self.chart = chart  # 'mo', 'wk', 'dy', 'mi' 중 하나
        self.cycle = cycle  # 분봉일 경우 주기
    
    def _get_data(self, code: str) -> List[Dict]:
        """해당 코드의 차트 데이터 반환"""
        #return self.chart_data.get_data(code, self.chart, self.cycle)
        return la.answer('cdt', 'get_data', code, self.chart, self.cycle)
    
    def _get_value(self, code: str, n: int, field: str, default=0.0):
        """특정 필드 값 반환"""
        data = self._get_data(code)
        if not data or len(data) <= n:
            return default
        return data[n][field]
    
    # 기본 값 반환 함수들
    def c(self, code: str, n: int = 0) -> float:
        """종가 반환"""
        return self._get_value(code, n, 'close')
    
    def o(self, code: str, n: int = 0) -> float:
        """시가 반환"""
        return self._get_value(code, n, 'open')
    
    def h(self, code: str, n: int = 0) -> float:
        """고가 반환"""
        return self._get_value(code, n, 'high')
    
    def l(self, code: str, n: int = 0) -> float:
        """저가 반환"""
        return self._get_value(code, n, 'low')
    
    def v(self, code: str, n: int = 0) -> int:
        """거래량 반환"""
        return int(self._get_value(code, n, 'volume', 0))
    
    def a(self, code: str, n: int = 0) -> float:
        """거래금액 반환"""
        return self._get_value(code, n, 'amount')
    
    def time(self, n: int = 0) -> str:
        """시간 반환"""
        if self.chart != 'mi':
            return ''
        code = "005930"  # 테스트용 코드
        return self._get_value(code, n, 'time', '')
    
    def today(self) -> str:
        """오늘 날짜 반환"""
        return datetime.now().strftime('%Y%m%d')
    
    # 계산 함수들
    def _get_values(self, code: str, a, n: int, m: int = 0) -> List:
        """지정된 값들 반환"""
        data = self._get_data(code)
        if not data or len(data) < n + m:
            return []
        
        values = []
        if callable(a):
            values = [a(code, i + m) for i in range(n)]
        else:
            values = [data[i+m].get(a, 0) for i in range(n) if i+m < len(data)]
        
        return values
    
    def ma(self, code: str, a, n: int, m: int = 0, k: str = 'a') -> float:
        """이동평균 계산"""
        if k == 'a': return self.avg(code, a, n, m)
        elif k == 'e': return self.eavg(code, a, n, m)
        elif k == 'w': return self.wavg(code, a, n, m)
        return 0.0
    
    def avg(self, code: str, a, n: int, m: int = 0) -> float:
        """단순이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return sum(values) / len(values)
    
    def eavg(self, code: str, a, n: int, m: int = 0) -> float:
        """지수이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        
        alpha = 2 / (n + 1)
        result = values[0]
        for i in range(1, len(values)):
            result = alpha * values[i] + (1 - alpha) * result
        return result
    
    def wavg(self, code: str, a, n: int, m: int = 0) -> float:
        """가중이동평균 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        
        weights = [i+1 for i in range(len(values))]
        return sum(v * w for v, w in zip(values, weights)) / sum(weights)
    
    def highest(self, code: str, a, n: int, m: int = 0) -> float:
        """가장 높은 값 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return max(values)
    
    def lowest(self, code: str, a, n: int, m: int = 0) -> float:
        """가장 낮은 값 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return min(values)
    
    def stdev(self, code: str, a, n: int, m: int = 0) -> float:
        """표준편차 계산"""
        values = self._get_values(code, a, n, m)
        if not values or len(values) < 2: return 0.0
        return np.std(values)
    
    def sum(self, code: str, a, n: int, m: int = 0) -> float:
        """합계 계산"""
        values = self._get_values(code, a, n, m)
        if not values: return 0.0
        return sum(values)
    
    # 신호 함수들
    def cross_down(self, code: str, a, b) -> bool:
        """a가 b를 하향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(code, 1), a(code, 0)
            b_prev, b_curr = b(code, 1), b(code, 0)
            return a_prev >= b_prev and a_curr < b_curr
        return False
    
    def cross_up(self, code: str, a, b) -> bool:
        """a가 b를 상향돌파하는지 확인"""
        if callable(a) and callable(b):
            a_prev, a_curr = a(code, 1), a(code, 0)
            b_prev, b_curr = b(code, 1), b(code, 0)
            return a_prev <= b_prev and a_curr > b_curr
        return False
    
    def bars_since(self, code: str, condition) -> int:
        """조건이 만족된 이후 지나간 봉 개수"""
        count = 0
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                return count
            count += 1
        return count
    
    def highest_since(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최고값"""
        condition_met = 0
        highest_val = float('-inf')
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(code, j)
            highest_val = max(highest_val, val)
        
        return highest_val
    
    def lowest_since(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 이후 data_func의 최저값"""
        condition_met = 0
        lowest_val = float('inf')
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    break
        
        if condition_met < nth:
            return 0.0
        
        for j in range(i, -1, -1):
            val = data_func(code, j)
            lowest_val = min(lowest_val, val)
        
        return lowest_val
    
    def value_when(self, code: str, nth: int, condition, data_func) -> float:
        """조건이 nth번째 만족된 시점의 data_func 값"""
        condition_met = 0
        
        for i in range(len(self._get_data(code))):
            if condition(code, i):
                condition_met += 1
                if condition_met == nth:
                    return data_func(code, i)
        
        return 0.0

    # 추가할 수학 함수들
    def min_value(self, a, b):
        """두 값 중 최소값 반환"""
        return min(a, b)
    
    def max_value(self, a, b):
        """두 값 중 최대값 반환"""
        return max(a, b)
    
    def pow(self, a, n):
        """a의 n제곱 반환"""
        return a ** n
    
    def sqrt(self, a):
        """제곱근 반환"""
        return a ** 0.5 if a >= 0 else 0
    
    def log(self, a, base=10):
        """로그 값 반환"""
        import math
        try:
            return math.log(a, base) if a > 0 else 0
        except:
            return 0
    
    def exp(self, a):
        """지수 함수 값 반환"""
        import math
        try:
            return math.exp(a)
        except:
            return 0
    
    def safe_div(self, a, b, default=0):
        """안전한 나눗셈 (0으로 나누기 방지)"""
        return a / b if b != 0 else default
    
    # 논리 함수들
    def iif(self, condition, true_value, false_value):
        """조건에 따른 값 선택 (조건부 삼항 연산자)"""
        return true_value if condition else false_value
    
    def all_true(self, condition_list):
        """모든 조건이 참인지 확인"""
        return all(condition_list)
    
    def any_true(self, condition_list):
        """하나라도 조건이 참인지 확인"""
        return any(condition_list)

    # 보조지표 계산 함수들
    def rsi(self, code: str, period: int = 14, m: int = 0) -> float:
        """상대강도지수(RSI) 계산"""
        values = self._get_values(code, self.c, period + 1, m)
        if len(values) < period + 1:
            return 50  # 기본값
        
        gains = []
        losses = []
        for i in range(1, len(values)):
            change = values[i-1] - values[i]  # 이전 값 - 현재 값 (역순이므로)
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        else:
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))
    
    def macd(self, code: str, fast: int = 12, slow: int = 26, signal: int = 9, m: int = 0) -> tuple:
        """MACD(Moving Average Convergence Divergence) 계산
        Returns: (MACD 라인, 시그널 라인, 히스토그램)
        """
        # 빠른 EMA
        fast_ema = self.eavg(code, self.c, fast, m)
        # 느린 EMA
        slow_ema = self.eavg(code, self.c, slow, m)
        # MACD 라인
        macd_line = fast_ema - slow_ema
        
        # 시그널 라인
        # 참고: 실제로는 MACD 값의 이력이 필요하나 단순화를 위해 현재 값만 사용
        signal_line = self.eavg(code, self.c, signal, m)
        
        # 히스토그램
        histogram = macd_line - signal_line
        
        return (macd_line, signal_line, histogram)
    
    def bollinger_bands(self, code: str, period: int = 20, std_dev: float = 2, m: int = 0) -> tuple:
        """볼린저 밴드 계산
        Returns: (상단 밴드, 중간 밴드(SMA), 하단 밴드)
        """
        middle_band = self.avg(code, self.c, period, m)
        stdev = self.stdev(code, self.c, period, m)
        
        upper_band = middle_band + (stdev * std_dev)
        lower_band = middle_band - (stdev * std_dev)
        
        return (upper_band, middle_band, lower_band)
    
    def stochastic(self, code: str, k_period: int = 14, d_period: int = 3, m: int = 0) -> tuple:
        """스토캐스틱 오실레이터 계산
        Returns: (%K, %D)
        """
        # 최고가, 최저가 가져오기
        highest_high = self.highest(code, self.h, k_period, m)
        lowest_low = self.lowest(code, self.l, k_period, m)
        
        # 현재 종가
        current_close = self.c(code, m)
        
        # %K 계산
        percent_k = 0
        if highest_high != lowest_low:
            percent_k = 100 * ((current_close - lowest_low) / (highest_high - lowest_low))
        
        # %D 계산 (간단한 이동평균 사용)
        # 참고: 실제로는 %K 값의 이력이 필요하나 단순화를 위해 현재 값으로 대체
        percent_d = self.avg(code, self.c, d_period, m)
        
        return (percent_k, percent_d)
    
    def atr(self, code: str, period: int = 14, m: int = 0) -> float:
        """평균 실제 범위(ATR) 계산"""
        data = self._get_data(code)
        if len(data) < period + 1 + m:
            return 0
        
        tr_values = []
        for i in range(m, m + period):
            if i + 1 >= len(data):
                break
                
            # 실제 범위 계산
            high = data[i]['high']
            low = data[i]['low']
            prev_close = data[i+1]['close']
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        # ATR 계산
        if not tr_values:
            return 0
        return sum(tr_values) / len(tr_values)

    # 캔들패턴 인식 함수들
    def is_doji(self, code: str, n: int = 0, threshold: float = 0.1) -> bool:
        """도지 캔들 확인 (시가와 종가의 차이가 매우 작은 캔들)"""
        o = self.o(code, n)
        c = self.c(code, n)
        h = self.h(code, n)
        l = self.l(code, n)
        
        # 몸통 크기
        body = abs(o - c)
        # 전체 캔들 크기
        candle_range = h - l
        
        if candle_range == 0:
            return False
            
        # 몸통이 전체 캔들의 threshold% 이하이면 도지로 간주
        return body / candle_range <= threshold
    
    def is_hammer(self, code: str, n: int = 0) -> bool:
        """망치형 캔들 확인 (아래 꼬리가 긴 캔들)"""
        o = self.o(code, n)
        c = self.c(code, n)
        h = self.h(code, n)
        l = self.l(code, n)
        
        # 시가/종가 중 낮은 값
        lower_val = min(o, c)
        # 몸통 크기
        body = abs(o - c)
        # 아래 꼬리 크기
        lower_shadow = lower_val - l
        
        # 전체 캔들 크기
        candle_range = h - l
        
        if candle_range == 0 or body == 0:
            return False
            
        # 아래 꼬리가 몸통의 2배 이상이고, 전체 캔들의 1/3 이상이면 망치형으로 간주
        return (lower_shadow >= 2 * body) and (lower_shadow / candle_range >= 0.33)
    
    def is_engulfing(self, code: str, n: int = 0, bullish: bool = True) -> bool:
        """포괄 패턴 확인 (이전 캔들을 완전히 덮는 형태)
        bullish=True: 상승 포괄 패턴, bullish=False: 하락 포괄 패턴
        """
        if n + 1 >= len(self._get_data(code)):
            return False
            
        curr_o = self.o(code, n)
        curr_c = self.c(code, n)
        prev_o = self.o(code, n + 1)
        prev_c = self.c(code, n + 1)
        
        if bullish:
            # 상승 포괄 패턴: 현재 캔들이 상승이고, 이전 캔들은 하락이며
            # 현재 캔들이 이전 캔들의 시가/종가 범위를 모두 포함
            return (curr_c > curr_o and  # 현재 캔들이 상승
                    prev_c < prev_o and  # 이전 캔들이 하락
                    curr_o <= prev_c and  # 현재 시가가 이전 종가보다 낮거나 같음
                    curr_c >= prev_o)     # 현재 종가가 이전 시가보다 높거나 같음
        else:
            # 하락 포괄 패턴: 현재 캔들이 하락이고, 이전 캔들은 상승이며
            # 현재 캔들이 이전 캔들의 시가/종가 범위를 모두 포함
            return (curr_c < curr_o and   # 현재 캔들이 하락
                    prev_c > prev_o and   # 이전 캔들이 상승
                    curr_o >= prev_c and   # 현재 시가가 이전 종가보다 높거나 같음
                    curr_c <= prev_o)      # 현재 종가가 이전 시가보다 낮거나 같음
    
    # 추세 분석 함수들
    def is_uptrend(self, code: str, period: int = 14, m: int = 0) -> bool:
        """상승 추세 여부 확인 (단순하게 종가가 이동평균보다 높은지 확인)"""
        current_close = self.c(code, m)
        avg_close = self.avg(code, self.c, period, m)
        
        return current_close > avg_close
    
    def is_downtrend(self, code: str, period: int = 14, m: int = 0) -> bool:
        """하락 추세 여부 확인 (단순하게 종가가 이동평균보다 낮은지 확인)"""
        current_close = self.c(code, m)
        avg_close = self.avg(code, self.c, period, m)
        
        return current_close < avg_close
    
    def momentum(self, code: str, period: int = 10, m: int = 0) -> float:
        """모멘텀 계산 (현재 종가와 n기간 이전 종가의 차이)"""
        current = self.c(code, m)
        previous = self.c(code, m + period)
        
        return current - previous

    # 데이터 변환 및 집계 함수들
    def rate_of_change(self, code: str, period: int = 1, m: int = 0) -> float:
        """변화율 계산 (현재 값과 n기간 이전 값의 백분율 변화)"""
        current = self.c(code, m)
        previous = self.c(code, m + period)
        
        if previous == 0:
            return 0
        
        return ((current - previous) / previous) * 100
    
    def normalized_volume(self, code: str, period: int = 20, m: int = 0) -> float:
        """거래량을 평균 거래량 대비 비율로 정규화"""
        current_volume = self.v(code, m)
        avg_volume = self.avg(code, self.v, period, m)
        
        if avg_volume == 0:
            return 0
        
        return current_volume / avg_volume
    
    def accumulation(self, values: list) -> list:
        """값의 누적 합계 계산"""
        result = []
        total = 0
        
        for val in values:
            total += val
            result.append(total)
            
        return result
    
    def streak_count(self, code: str, condition_func) -> int:
        """연속된 조건 만족 횟수 계산"""
        count = 0
        data = self._get_data(code)
        
        for i in range(len(data)):
            if condition_func(code, i):
                count += 1
            else:
                break
                
        return count
    
    def detect_pattern(self, code: str, pattern_func, length: int) -> bool:
        """특정 패턴 감지 (length 길이의 데이터에 pattern_func 적용)"""
        if len(self._get_data(code)) < length:
            return False
            
        # pattern_func에 데이터 전달하여 패턴 확인
        return pattern_func(code, length)
                
class ScriptManager:
    """스크립트 관리 및 실행 클래스 (개선 버전)
    
    스크립트 작성 제한 사항:
    1. 스크립트에서는 외부 모듈 임포트 지원하지 않음 (np와 ChartManager만 기본 제공)
    2. 스크립트의 마지막에 'result = 불리언_값'으로 결과 저장 필요
    3. ChartManager 객체는 스크립트 내에서 직접 생성해야 함 (예: ct_dy = ChartManager('dy'))
    4. 다른 스크립트 호출 시 get_script_result('스크립트명', 코드) 함수 사용
    5. get_var('변수명')을 통해 현재 스크립트 변수에 접근 가능
    """
    
    def __init__(self, script_file=dc.fp.script_file):
        self.script_file = script_file
        self.scripts = {}  # {name: {script: str, vars: dict}}
        self.load_script()
        
        # 스크립트 실행 준비
        self.script_code = ""
        self.current_script = ""
        self.execution_stack = []  # 스크립트 실행 스택 (순환 참조 방지)
        self.result_cache = {}  # {(script_name, code): result} 형태의 캐시
        
        # 허용된 함수 및 패턴 목록
        self._allowed_functions = self._get_allowed_functions()
        self._allowed_patterns = [
            r'[\+\-\*/<%=>&\|\^~!]',  # 기본 연산자
            r'if\s+.*\s+else',         # 조건문
            r'and|or|not',             # 논리 연산자
            r'True|False|None',        # 상수
            r'[\[\]{}(),.:;]',         # 구두점 및 기호
            r'==|!=|<=|>=|<|>',        # 비교 연산자
            r'"[^"]*"|\'[^\']*\'',     # 문자열
            r'result\s*=',             # 결과 할당
            r'[\d.]+',                 # 숫자
            r'ct_\w+',                 # ChartManager 인스턴스
            r'get_script_result',      # 스크립트 결과 가져오기
            r'get_var',                # 변수 가져오기
            r'ChartManager',           # ChartManager 클래스
            r'np\.(?:array|mean|std|max|min|abs)',  # 허용된 numpy 함수
        ]
    
    def _get_allowed_functions(self):
        """허용된 함수 목록 반환"""
        # ChartManager의 메소드명 추출
        chartmgr_methods = [method for method in dir(ChartManager) if not method.startswith('_') and callable(getattr(ChartManager, method))]
        # 추가 허용 함수들
        extra_functions = [ 'get_script_result', 'get_var' ]
        # numpy 허용 함수들
        numpy_functions = [ 'np.mean', 'np.std', 'np.max', 'np.min', 'np.abs', 'np.array', 'np.sum' ]
        
        return set(chartmgr_methods + extra_functions + numpy_functions)
    
    def set_script(self, name: str, script: str, vars: dict = None):
        """스크립트 저장"""
        if not self.check_script(name, script):
            return False
            
        self.scripts[name] = {
            'script': script,
            'vars': vars or {}
        }
        self.save_script()
        return True
    
    def get_script(self, name: str = None):
        """스크립트 가져오기"""
        if name:
            return self.scripts.get(name, {}).get('script', "")
        else:
            return self.scripts
        
    def delete_script(self, name: str):
        """스크립트 삭제"""
        if name in self.scripts:
            del self.scripts[name]
            self.save_script()
            return True
        return False
    
    def get_vars(self, name: str = None):
        """스크립트 변수 가져오기"""
        if name is None:
            name = self.current_script
        return self.scripts.get(name, {}).get('vars', {})
    
    def set_vars(self, name: str, vars: dict):
        """스크립트 변수 설정"""
        if name in self.scripts:
            self.scripts[name]['vars'] = vars
            self.save_script()
            return True
        return False
    
    def get_var(self, var_name, default=None):
        """현재 실행 중인 스크립트의 특정 변수 가져오기"""
        vars_dict = self.get_vars(self.current_script)
        return vars_dict.get(var_name, default)
    
    def save_script(self):
        """스크립트를 JSON 파일로 저장"""
        with open(self.script_file, 'w', encoding='utf-8') as f:
            json.dump(self.scripts, f, ensure_ascii=False, indent=2)
    
    def load_script(self):
        """JSON 파일에서 스크립트 로드"""
        try:
            with open(self.script_file, 'r', encoding='utf-8') as f:
                self.scripts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.scripts = {}
    
    def check_script(self, name: str, script: str = None) -> bool:
        """
        스크립트 기본 안전 검사 및 모의 환경에서의 실행 테스트
        
        모의 ChartManager를 사용하여, 실제 차트 데이터 의존성 없이 스크립트 검증
        타임아웃 설정으로 데드락 방지
        """
        if script is None:
            if name not in self.scripts:
                return False
            script = self.scripts[name]['script']
        
        # 기본 문법 검사
        try:
            compile(script, "<string>", "exec")
        except SyntaxError as e:
            logging.debug(f"문법 오류: {e}")
            return False
        except Exception as e:
            logging.debug(f"스크립트 오류 발생: {e}")
            return False
        
        # 결과 변수 사용 여부 확인
        if "result = " not in script and "result=" not in script:
            logging.debug("오류: 스크립트의 마지막에 'result = 불리언_값'으로 결과를 저장해야 합니다.")
            return False
        
        # 허용되지 않은 패턴 검사
        import re
        script_without_comments = re.sub(r'#.*$', '', script, flags=re.MULTILINE)
        
        # 금지된 모듈 임포트 패턴 검사
        if re.search(r'import\s+', script_without_comments):
            logging.debug("오류: 스크립트 내에서 모듈 임포트가 허용되지 않습니다.")
            return False
        
        # 금지된 패턴 (eval, exec, globals 등) 검사
        dangerous_patterns = [
            r'eval\s*\(',
            r'exec\s*\(',
            r'globals\s*\(',
            r'locals\s*\(',
            r'__import__\s*\(',
            r'open\s*\(',
            r'file\s*\(',
            r'compile\s*\(',
            r'os\.',
            r'sys\.',
            r'subprocess\.',
            r'importlib\.',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, script_without_comments):
                logging.debug(f"오류: 금지된 패턴 발견: {pattern}")
                return False
        
        # 함수 호출 검사 - 스크립트에서 ChartManager와 허용된 함수만 사용하는지 확인
        func_calls = re.findall(r'(\w+)\s*\(', script_without_comments)
        allowed_names = list(self._allowed_functions) + ['self', 'ChartManager']
        
        for func in func_calls:
            if func not in allowed_names:
                logging.debug(f"오류: 허용되지 않은 함수 호출: {func}")
                return False
        
        # 모의 환경에서 실행 테스트 (스크립트 로직 검증)
        return self._test_script_with_mock(name, script)
        
    def _test_script_with_mock(self, name: str, script: str) -> bool:
        """
        모의 환경에서 스크립트 실행 테스트 (타임아웃 적용)
        """
        import threading
        import time
        
        # 테스트 결과 저장용 딕셔너리
        test_result = {'success': False, 'error': None}
        
        # 모의 ChartManager 클래스 정의 (실제 데이터 접근 없이 기본값 반환)
        class MockChartManager:
            def __init__(self, chart='dy', cycle=1):
                self.chart = chart
                self.cycle = cycle
            
            # 기본 값 반환 함수들
            def c(self, code, n=0): return 10000.0
            def o(self, code, n=0): return 9900.0
            def h(self, code, n=0): return 10100.0
            def l(self, code, n=0): return 9800.0
            def v(self, code, n=0): return 10000
            def a(self, code, n=0): return 100000000.0
            def time(self, n=0): return '090000' if self.chart == 'mi' else ''
            def today(self): return '20240423'
            
            # 계산 함수들
            def avg(self, code, a, n, m=0): return 10000.0
            def eavg(self, code, a, n, m=0): return 10000.0
            def wavg(self, code, a, n, m=0): return 10000.0
            def highest(self, code, a, n, m=0): return 10100.0
            def lowest(self, code, a, n, m=0): return 9800.0
            def stdev(self, code, a, n, m=0): return 100.0
            def sum(self, code, a, n, m=0): return 100000.0
            
            # 신호 함수들
            def cross_down(self, code, a, b): return False
            def cross_up(self, code, a, b): return True
            def bars_since(self, code, condition): return 5
            
            # 추가 함수들 (모두 기본값 반환)
            def min_value(self, a, b): return min(a, b)
            def max_value(self, a, b): return max(a, b)
            def pow(self, a, n): return a ** n
            def sqrt(self, a): return a ** 0.5 if a >= 0 else 0
            def log(self, a, base=10): return 1.0
            def exp(self, a): return 2.7
            def safe_div(self, a, b, default=0): return a / b if b != 0 else default
            def iif(self, condition, true_value, false_value): return true_value if condition else false_value
            def all_true(self, condition_list): return all(condition_list)
            def any_true(self, condition_list): return any(condition_list)
            
            # 보조지표 함수들
            def rsi(self, code, period=14, m=0): return 50.0
            def macd(self, code, fast=12, slow=26, signal=9, m=0): return (0.0, 0.0, 0.0)
            def bollinger_bands(self, code, period=20, std_dev=2, m=0): return (10200.0, 10000.0, 9800.0)
            def stochastic(self, code, k_period=14, d_period=3, m=0): return (50.0, 50.0)
            def atr(self, code, period=14, m=0): return 100.0
            
            # 캔들패턴 인식 함수들
            def is_doji(self, code, n=0, threshold=0.1): return False
            def is_hammer(self, code, n=0): return True
            def is_engulfing(self, code, n=0, bullish=True): return bullish
            
            # 추세 분석 함수들
            def is_uptrend(self, code, period=14, m=0): return True
            def is_downtrend(self, code, period=14, m=0): return False
            def momentum(self, code, period=10, m=0): return 100.0
            
            # 데이터 변환 함수들
            def rate_of_change(self, code, period=1, m=0): return 1.0
            def normalized_volume(self, code, period=20, m=0): return 1.0
            def accumulation(self, values): return [sum(values[:i+1]) for i in range(len(values))]
            def streak_count(self, code, condition_func): return 3
            def detect_pattern(self, code, pattern_func, length): return True
        
        # 테스트 실행 함수
        def run_test():
            try:
                # 글로벌 환경 준비 (모의 ChartManager 사용)
                globals_dict = {
                    'ChartManager': MockChartManager,
                    'np': np,
                    'self': self,
                    'get_script_result': lambda script_name, code: True,  # 항상 True 반환
                    'get_var': lambda var_name, default=None: default
                }
                
                # 스크립트 실행
                local_vars = {}
                exec(script, globals_dict, local_vars)
                
                # 반환값 확인
                if 'result' not in local_vars:
                    test_result['error'] = "스크립트에 'result' 변수가 없습니다"
                    return
                
                # 결과가 불리언 타입인지 확인
                result = local_vars.get('result')
                if not isinstance(result, bool):
                    test_result['error'] = f"'result' 변수가 불리언 타입이 아닙니다: {type(result)}"
                    return
                    
                # 테스트 성공
                test_result['success'] = True
                
            except Exception as e:
                test_result['error'] = f"테스트 실행 오류: {type(e).__name__} - {e}"
        
        # 타임아웃 설정 (초 단위)
        timeout = 3
        
        # 스레드 생성 및 실행
        test_thread = threading.Thread(target=run_test)
        test_thread.daemon = True
        test_thread.start()
        
        # 타임아웃 대기
        test_thread.join(timeout)
        
        # 타임아웃 발생 확인
        if test_thread.is_alive():
            logging.debug(f"스크립트 테스트 타임아웃 (>{timeout}초)")
            return False
        
        # 테스트 결과 확인
        if not test_result['success']:
            logging.debug(f"모의 환경 테스트 실패: {test_result['error']}")
            return False
        
        # 모든 검사 통과
        return True
        
    def run_script(self, name: str, code: str, is_sub_call: bool = False):
        """
        스크립트 실행 (개선 버전)
        
        Parameters:
        - name: 실행할 스크립트 이름
        - code: 종목 코드
        - is_sub_call: 다른 스크립트에서 호출한 것인지 여부
        
        Returns:
        - tuple: (성공 여부, 오류 유형, 결과값 또는 오류 메시지)
            - 성공 여부: True/False
            - 오류 유형: "success", "script_not_found", "circular_reference", "no_result_var", "syntax_error", "name_error", "runtime_error", "type_error"
            - 결과값/메시지: 성공 시 불리언 결과값, 실패 시 오류 메시지
        """
        if name not in self.scripts:
            return (False, "script_not_found", f"스크립트 '{name}'을 찾을 수 없습니다")
            
        # 이미 실행 중인 스크립트라면 순환 참조로 간주
        if name in self.execution_stack:
            return (False, "circular_reference", f"순환 참조 감지: {' -> '.join(self.execution_stack)} -> {name}")
            
        # 이전 상태 저장
        prev_script = self.current_script
        prev_code = self.script_code
        
        # 실행 환경 설정
        self.current_script = name
        self.script_code = code
        self.execution_stack.append(name)
        
        # 글로벌 실행 환경 준비 (최소한의 필요한 함수만 제공)
        globals_dict = {
            'ChartManager': ChartManager,
            'np': np,
            'self': self,
            'get_script_result': self.get_script_result,
            'get_var': self.get_var
        }
        
        try:
            # 스크립트 실행
            local_vars = {}
            exec(self.scripts[name]['script'], globals_dict, local_vars)
            
            # 반환값 확인 (result 변수 값)
            if 'result' not in local_vars:
                # 결과 변수가 없음
                self.execution_stack.pop()
                self.current_script = prev_script
                self.script_code = prev_code
                return (False, "no_result_var", f"스크립트에 'result' 변수가 없습니다")
            
            result = local_vars.get('result', None)
            
            # 결과가 불리언 타입인지 확인
            if not isinstance(result, bool):
                self.execution_stack.pop()
                self.current_script = prev_script
                self.script_code = prev_code
                return (False, "type_error", f"'result' 변수가 불리언 타입이 아닙니다: {type(result)}")
                
            # 실행 상태 복원
            if not is_sub_call:
                self.result_cache = {}  # 최상위 호출이 끝나면 캐시 초기화
                
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            
            # 성공 여부와 결과를 함께 반환
            return (True, "success", result)
            
        except SyntaxError as e:
            # 문법 오류
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            return (False, "syntax_error", f"문법 오류: {e}")
            
        except NameError as e:
            # 변수나 함수를 찾을 수 없음
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            return (False, "name_error", f"변수 또는 함수 오류: {e}")
            
        except Exception as e:
            # 기타 오류
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            
            logging.debug(f"스크립트 '{name}' 실행 오류: {e}")
            return (False, "runtime_error", f"실행 오류: {type(e).__name__} - {e}")
                    
    def get_script_result(self, script_name: str, code: str):
        """
        다른 스크립트의 결과 가져오기
        (스크립트 내에서 다른 스크립트 호출 시 사용)
        
        Returns:
        - boolean: 스크립트 실행 결과 (실패 시 False)
        """
        # 순환 참조 검사
        if script_name in self.execution_stack:
            logging.debug(f"순환 참조 감지: {' -> '.join(self.execution_stack)} -> {script_name}")
            return False
            
        # 캐시 확인
        cache_key = (script_name, code)
        if cache_key in self.result_cache:
            return self.result_cache[cache_key]
            
        # 스크립트 실행
        success, error_type, result = self.run_script(script_name, code, is_sub_call=True)
        
        if not success:
            logging.debug(f"서브스크립트 '{script_name}' 실행 실패: {error_type} - {result}")
            return False
        
        # 결과 캐싱
        self.result_cache[cache_key] = result
        return result

"""
# 스크립트 실행을 위한 기본 설정
# 'self.script_code'를 통해 종목 코드에 접근 가능
# 'get_var(변수명, 기본값)'을 통해 변수에 접근 가능
# 'get_script_result(스크립트명, 코드)'를 통해 다른 스크립트 결과 사용 가능

# ChartManager 인스턴스 생성 (필요한 차트 타입에 맞게 설정)
ct_dy = ChartManager('dy')  # 일봉 차트
ct_3m = ChartManager('mi', 3)  # 3분봉 차트

# 변수 가져오기
code = self.script_code

# 기본 지표 계산
ma5 = ct_dy.avg(code, ct_dy.c, 5)  # 5일 이동평균
ma20 = ct_dy.avg(code, ct_dy.c, 20)  # 20일 이동평균
current_price = ct_dy.c(code)  # 현재가

# 추가 기술 지표 계산
rsi_value = ct_dy.rsi(code, 14)  # 14일 RSI
bb_upper, bb_middle, bb_lower = ct_dy.bollinger_bands(code, 20, 2)  # 볼린저 밴드

# 추세 확인
uptrend = ct_dy.is_uptrend(code, 20)  # 20일 기준 상승 추세 여부
downtrend = ct_dy.is_downtrend(code, 20)  # 20일 기준 하락 추세 여부

# 캔들 패턴 확인
hammer_detected = ct_dy.is_hammer(code)  # 망치형 캔들 확인
doji_detected = ct_dy.is_doji(code)  # 도지 캔들 확인
engulfing_bullish = ct_dy.is_engulfing(code, 0, True)  # 상승 포괄 패턴 확인

# 추가 조건 계산
price_above_ma20 = current_price > ma20  # 현재가가 20일 이평선 위에 있는지
golden_cross = ct_dy.cross_up(ct_dy.c, lambda code, n: ct_dy.avg(code, ct_dy.c, 5, n), 
                             lambda code, n: ct_dy.avg(code, ct_dy.c, 20, n))  # 5일선이 20일선 상향돌파

# 다른 스크립트 결과 사용 예시
# macd_signal = get_script_result('macd_signal', code)

# 최종 매매 신호 결정 (예시)
buy_signal = (uptrend and price_above_ma20 and (rsi_value < 70) and 
              (hammer_detected or engulfing_bullish or golden_cross))
sell_signal = downtrend and (rsi_value > 30) and current_price < bb_lower

# 결과 저장 (반드시 불리언 값을 result 변수에 저장해야 함)
result = buy_signal  # 매수 신호를 반환하는 경우
"""

# 골든 크로스 확인 스크립트
"""
# 골든 크로스 감지 스크립트 (단기 이평선이 장기 이평선을 상향돌파)
ct_dy = ChartManager('dy')
code = self.script_code

# 변수 가져오기
short_period = get_var('short_period', 5)  # 기본값 5일
long_period = get_var('long_period', 20)  # 기본값 20일

# 단기, 장기 이동평균 계산
short_ma = ct_dy.avg(code, ct_dy.c, short_period)
long_ma = ct_dy.avg(code, ct_dy.c, long_period)
prev_short_ma = ct_dy.avg(code, ct_dy.c, short_period, 1)
prev_long_ma = ct_dy.avg(code, ct_dy.c, long_period, 1)

# 골든 크로스 조건: 이전에는 단기선이 장기선보다 낮았고, 현재는 높음
golden_cross = (prev_short_ma < prev_long_ma) and (short_ma > long_ma)

result = golden_cross
"""

# RSI 과매수/과매도 판단 스크립트
"""
# RSI 기반 매매 신호 스크립트
ct_dy = ChartManager('dy')
code = self.script_code

# 변수 가져오기
rsi_period = get_var('rsi_period', 14)  # RSI 기간
oversold = get_var('oversold', 30)      # 과매도 기준값
overbought = get_var('overbought', 70)  # 과매수 기준값
signal_type = get_var('signal_type', 'buy')  # 신호 타입 (buy 또는 sell)

# RSI 계산
rsi_value = ct_dy.rsi(code, rsi_period)

# 신호 판단
buy_signal = rsi_value < oversold   # 과매도 상태 (매수 신호)
sell_signal = rsi_value > overbought  # 과매수 상태 (매도 신호)

# 결과 반환 (signal_type에 따라 반환값 결정)
if signal_type == 'buy':
    result = buy_signal
else:
    result = sell_signal
"""

# 볼린저 밴드 돌파 스크립트
"""
# 볼린저 밴드 돌파 감지 스크립트
ct_dy = ChartManager('dy')
code = self.script_code

# 변수 가져오기
period = get_var('period', 20)       # 기간
std_dev = get_var('std_dev', 2)      # 표준편차 배수
signal_type = get_var('signal_type', 'breakthrough')  # 신호 타입

# 볼린저 밴드 계산
upper_band, middle_band, lower_band = ct_dy.bollinger_bands(code, period, std_dev)
current_price = ct_dy.c(code)

# 신호 판단
upper_breakthrough = current_price > upper_band  # 상단 돌파
lower_breakthrough = current_price < lower_band  # 하단 돌파
prev_price = ct_dy.c(code, 1)
reversal_up = (prev_price < lower_band) and (current_price > prev_price)  # 하단에서 반등
reversal_down = (prev_price > upper_band) and (current_price < prev_price)  # 상단에서 반락

# 결과 반환 (signal_type에 따라 반환값 결정)
if signal_type == 'breakthrough_upper':
    result = upper_breakthrough
elif signal_type == 'breakthrough_lower':
    result = lower_breakthrough
elif signal_type == 'reversal_up':
    result = reversal_up
elif signal_type == 'reversal_down':
    result = reversal_down
else:  # 기본값: 아무 밴드든 돌파
    result = upper_breakthrough or lower_breakthrough
"""

# MACD 신호 스크립트
"""
# MACD 신호선 교차 감지 스크립트
ct_dy = ChartManager('dy')
code = self.script_code

# 변수 가져오기
fast_period = get_var('fast_period', 12)
slow_period = get_var('slow_period', 26)
signal_period = get_var('signal_period', 9)
signal_type = get_var('signal_type', 'buy')  # 'buy' 또는 'sell'

# 현재 MACD 값 계산
macd_line, signal_line, histogram = ct_dy.macd(code, fast_period, slow_period, signal_period)

# 이전 MACD 값 계산
prev_macd_line, prev_signal_line, prev_histogram = ct_dy.macd(code, fast_period, slow_period, signal_period, 1)

# 신호 판단
buy_signal = (prev_macd_line < prev_signal_line) and (macd_line > signal_line)  # 상향 교차 (매수)
sell_signal = (prev_macd_line > prev_signal_line) and (macd_line < signal_line)  # 하향 교차 (매도)

# 결과 반환
if signal_type == 'buy':
    result = buy_signal
else:
    result = sell_signal
"""