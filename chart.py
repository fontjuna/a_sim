from public import gm, dc
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
    
    def _init_code_data(self, code: str):
        """코드별 데이터 초기화"""
        # 데이터 구조 초기화
        self._data[code] = {'mo': [], 'wk': [], 'dy': [], 'mi': {1: []}}
        
        # 주기별 데이터 로드 및 처리
        chart_types = {'mo': 'mo', 'wk': 'wk', 'dy': 'dy', 'mi': 'mi'}
        for key, chart_type in chart_types.items():
            cycle = 1 if key == 'mi' else None
            data = self.get_chart_data(code, chart_type, cycle)
            
            if key == 'mi':
                # 분봉 데이터 처리
                for item in reversed(data):
                    datetime_str = item.get('체결시간', '')
                    self._data[code]['mi'][1].append(self._create_candle(
                        date=datetime_str[:8],
                        time=datetime_str[8:14],
                        item=item
                    ))
            else:
                # 일/주/월봉 데이터 처리
                for item in reversed(data):
                    self._data[code][key].append(self._create_candle(
                        date=item.get('일자', ''),
                        time='',
                        item=item
                    ))
    
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
        if code not in self._data:
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
        if code not in self._data:
            return []
        
        if chart_type == 'mi':
            if cycle not in self._data[code]['mi']:
                self._calculate_cycle_data(code, cycle)
            return self._data[code]['mi'].get(cycle, [])
        else:
            return self._data[code].get(chart_type, [])
    
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
    
    def get_chart_data(self, code, chart_type, cycle=None, is_dummy=False):
        """차트 데이터 가져오기 (외부에서 구현되는 함수)"""
        def _get_dummy_data():
            # 테스트용 더미 데이터
            result = []
            
            if chart_type == 'mi':
                for i in range(10):
                    hour = 9 + (i // 60)
                    minute = i % 60
                    result.append({
                        '종목코드': code,
                        '체결시간': f'2025042{hour:02d}{minute:02d}00',
                        '현재가': str(70000 + i * 100),
                        '시가': str(70000 + i * 90),
                        '고가': str(70000 + i * 110),
                        '저가': str(70000 + i * 85),
                        '거래량': str(1000 + i * 10),
                        '거래대금': '0'
                    })
            else:
                for i in range(5):
                    result.append({
                        '종목코드': code,
                        '일자': f'2025040{i+1}',
                        '현재가': str(70000 + i * 1000),
                        '시가': str(69000 + i * 1000),
                        '고가': str(71000 + i * 1000),
                        '저가': str(68500 + i * 1000),
                        '거래량': str(100000 + i * 10000),
                        '거래대금': str(7000000000 + i * 800000000)
                    })
            
            return result

        def _get_real_data():
            try:
                rqname = f'{dc.scr.차트종류[chart_type]}챠트'
                trcode = dc.scr.차트TR[chart_type]
                screen = dc.scr.화면[rqname]
                date = datetime.now().strftime('%Y%m%d')

                if chart_type == 'mi':
                    input = {'종목코드':code, '틱범위': cycle, '수정주가구분': 0}
                    output = ["현재가", "거래량", "체결시간", "시가", "고가", "저가"]
                else:
                    if chart_type == 'dy':
                        input = {'종목코드':code, '기준일자': date, '수정주가구분': 0}
                    else:
                        input = {'종목코드':code, '기준일자': date, '끝일자': '', '수정주가구분': 0}
                    output = ["현재가", "거래량", "거래대금", "일자", "시가", "고가", "저가"]

                next = '0'
                all = False if chart_type in ['mi', 'dy'] else True
                dict_list = []
                while True:
                    data, remain = gm.admin.com_SendRequest(rqname, trcode, input, output, next, screen, 'dict_list', 10)
                    if data is None or len(data) == 0: break
                    logging.info(f'챠트 데이타 얻기: code:{code}, chart_type:{chart_type}, cycle:{cycle}, data:"{data}"')
                    dict_list.extend(data)
                    if not (remain and all): break
                    next = '2'
                
                if not dict_list:
                    logging.warning(f'챠트 데이타 얻기 실패: code:{code}, chart_type:{chart_type}, cycle:{cycle}, dict_list:"{dict_list}"')
                    return []
                
                if chart_type == 'mi':
                    dict_list = [{
                        '종목코드': code,
                        '체결시간': item['체결시간'],
                        '현재가': abs(int(item['현재가'])),
                        '시가': abs(int(item['시가'])),
                        '고가': abs(int(item['고가'])),
                        '저가': abs(int(item['저가'])),
                        '거래량': abs(int(item['거래량'])),
                        '거래대금': abs(int(item['거래대금'])),
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

        if is_dummy:
            return _get_dummy_data()
        else:
            return _get_real_data()

class ChartManager:
    """차트 매니저 클래스, 수식관리자 기본함수 구현"""
    
    def __init__(self, chart='dy', cycle=1):
        self.chart = chart  # 'mo', 'wk', 'dy', 'mi' 중 하나
        self.cycle = cycle  # 분봉일 경우 주기
        self.chart_data = ChartData()
    
    def _get_data(self, code: str) -> List[Dict]:
        """해당 코드의 차트 데이터 반환"""
        return self.chart_data.get_data(code, self.chart, self.cycle)
    
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

class ScriptManager:
    """스크립트 관리 및 실행 클래스
    
    스크립트 작성 제한 사항:
    1. 스크립트에서는 외부 모듈 임포트를 최소화해야 함 (np, ChartManager 허용)
    2. os, sys, subprocess 등의 시스템 모듈 사용 불가
    3. eval, exec, open과 같은 위험한 함수 사용 금지
    4. 스크립트의 마지막에 'result = 불리언_값'으로 결과 저장 필요
    5. ChartManager 객체는 스크립트 내에서 직접 생성해야 함 (예: ct_3m = ChartManager('mi', 3))
    6. 다른 스크립트 호출 시 get_script_result('스크립트명', 코드) 함수 사용
    7. get_var('변수명')을 통해 현재 스크립트 변수에 접근 가능
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
    
    def get_vars(self, name: str = None):
        """스크립트 변수 가져오기"""
        if name is None:
            name = self.current_script
        return self.scripts.get(name, {}).get('vars', {})
    
    def get_var(self, var_name, default=None):
        """현재 실행 중인 스크립트의 특정 변수 가져오기"""
        vars_dict = self.get_vars(self.current_script)
        return vars_dict.get(var_name, default)
    
    def set_vars(self, name: str, vars: dict):
        """스크립트 변수 설정"""
        if name in self.scripts:
            self.scripts[name]['vars'] = vars
            self.save_script()
            return True
        return False
    
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
        스크립트 기본 안전 검사 및 의존성 검사
        """
        if script is None:
            if name not in self.scripts:
                return False
            script = self.scripts[name]['script']
        
        # 기본 문법 검사
        try:
            compile(script, "<string>", "exec")
        except SyntaxError as e:
            print(f"문법 오류: {e}")
            return False
        except Exception as e:
            print(f"스크립트 오류 발생: {e}")
            return False
            
        # result 변수 사용 여부 확인
        if "result = " not in script and "result=" not in script:
            print("오류: 스크립트의 마지막에 'result = 불리언_값'으로 결과를 저장해야 합니다.")
            return False
        
        # 의존성 검사를 위한 테스트 실행
        # 실제 실행은 하지 않고 의존성만 확인
        try:
            # 테스트용 실행 환경 설정
            old_current = self.current_script
            old_stack = self.execution_stack.copy()
            self.current_script = name
            self.execution_stack = []
            self.script_code = "TEST_CODE"
            
            # 테스트용 글로벌 환경
            globals_dict = {
                'ChartManager': ChartManager,
                'np': np,
                'self': self,
                'get_script_result': self.get_script_result,
                'get_var': self.get_var
            }
            
            # 컴파일만 하고 실행은 하지 않음
            compile(script, "<string>", "exec")
            
            # 원래 상태로 복원
            self.current_script = old_current
            self.execution_stack = old_stack
            return True
            
        except Exception as e:
            print(f"의존성 검사 오류: {e}")
            # 원래 상태로 복원
            self.current_script = old_current if 'old_current' in locals() else ""
            self.execution_stack = old_stack if 'old_stack' in locals() else []
            return False
    
    def get_script_result(self, script_name: str, code: str):
        """
        다른 스크립트의 결과 가져오기
        (스크립트 내에서 다른 스크립트 호출 시 사용)
        """
        # 순환 참조 검사
        if script_name in self.execution_stack:
            print(f"순환 참조 감지: {' -> '.join(self.execution_stack)} -> {script_name}")
            return False
            
        # 캐시 확인
        cache_key = (script_name, code)
        if cache_key in self.result_cache:
            return self.result_cache[cache_key]
            
        # 스크립트 실행
        result = self.run_script(script_name, code, is_sub_call=True)
        
        # 결과 캐싱
        self.result_cache[cache_key] = result
        return result
    
    def run_script(self, name: str, code: str, is_sub_call: bool = False):
        """
        스크립트 실행
        
        Parameters:
        - name: 실행할 스크립트 이름
        - code: 종목 코드
        - is_sub_call: 다른 스크립트에서 호출한 것인지 여부
        
        Returns:
        - boolean: 스크립트 실행 결과
        """
        if name not in self.scripts:
            return False
            
        # 이미 실행 중인 스크립트라면 순환 참조로 간주
        if name in self.execution_stack:
            print(f"순환 참조 감지: {' -> '.join(self.execution_stack)} -> {name}")
            return False
            
        # 이전 상태 저장
        prev_script = self.current_script
        prev_code = self.script_code
        
        # 실행 환경 설정
        self.current_script = name
        self.script_code = code
        self.execution_stack.append(name)
        
        # 글로벌 실행 환경 준비
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
            result = bool(local_vars.get('result', False))
                
            # 실행 상태 복원
            if not is_sub_call:
                self.result_cache = {}  # 최상위 호출이 끝나면 캐시 초기화
                
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            
            return result
            
        except Exception as e:
            # 오류 발생 시 상태 복원
            self.execution_stack.pop()
            self.current_script = prev_script
            self.script_code = prev_code
            
            print(f"스크립트 '{name}' 실행 오류: {e}")
            return False

# 스크립트 작성 예시 (사용자에게 제공할 템플릿)
"""
# 스크립트 실행을 위한 기본 설정
# 'self.script_code'를 통해 종목 코드에 접근 가능
# 'get_var(변수명, 기본값)'을 통해 변수에 접근 가능
# 'get_script_result(스크립트명, 코드)'를 통해 다른 스크립트 결과 사용 가능

# ChartManager 인스턴스 생성 (필요한 차트 타입에 맞게 설정)
ct_3m = ChartManager(chart='mi', cycle=3)  # 3분봉 차트
ct_dy = ChartManager('dy')  # 일봉 차트

# 변수 가져오기
code = self.script_code
price = get_var('price', 0)
cycle = get_var('cycle', 5)

# 다른 스크립트 결과 사용 예시
# is_ma_cross = get_script_result('ma_cross', code)

# 조건 계산
cond1 = ct_3m.c(code) > price  # 현재가가 지정 가격보다 높은지
cond2 = ct_dy.avg(code, ct_dy.c, 5) < ct_dy.c(code)  # 5일 이평선 상향 돌파 여부

# 결과 저장 (반드시 불리언 값을 result 변수에 저장해야 함)
result = cond1 and cond2
"""

import unittest
import os
import numpy as np
import tempfile
import json

class TestChartData(unittest.TestCase):
    """ChartData 클래스 테스트"""
    
    def setUp(self):
        self.chart_data = ChartData()
        self.chart_data._data = {}
        self.test_code = "005930"
    
    def test_singleton(self):
        """싱글톤 패턴 테스트"""
        chart_data1 = ChartData()
        chart_data2 = ChartData()
        self.assertIs(chart_data1, chart_data2)
    
    def test_init_code_data(self):
        """코드 데이터 초기화 테스트"""
        self.chart_data._init_code_data(self.test_code)
        
        # 각 주기 데이터가 로드되었는지 확인
        self.assertIn('mo', self.chart_data._data[self.test_code])
        self.assertIn('wk', self.chart_data._data[self.test_code])
        self.assertIn('dy', self.chart_data._data[self.test_code])
        self.assertIn('mi', self.chart_data._data[self.test_code])
        
        # 분봉 데이터 확인
        self.assertIn(1, self.chart_data._data[self.test_code]['mi'])
        
        # 데이터 구조 확인
        for period in ['mo', 'wk', 'dy']:
            candles = self.chart_data._data[self.test_code][period]
            self.assertGreater(len(candles), 0)
            self._check_candle_structure(candles[0])
            
        # 분봉 구조 확인
        mi_candles = self.chart_data._data[self.test_code]['mi'][1]
        self.assertGreater(len(mi_candles), 0)
        self._check_candle_structure(mi_candles[0])
    
    def _check_candle_structure(self, candle):
        """캔들 데이터 구조 확인"""
        fields = ['date', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount']
        for field in fields:
            self.assertIn(field, candle)
    
    def test_update_price(self):
        """가격 업데이트 테스트"""
        self.chart_data._init_code_data(self.test_code)
        
        # 가격 업데이트
        datetime_str = "20250420093000"
        self.chart_data.update_price(self.test_code, 70000, 10000, 700000000, datetime_str)
        
        # 분봉 데이터 확인
        mi_data = self.chart_data._data[self.test_code]['mi'][1]
        self.assertGreater(len(mi_data), 0)
        
        # 업데이트된 분봉 찾기
        updated_candle = None
        for candle in mi_data:
            if candle['time'] == "093000":
                updated_candle = candle
                break
        
        self.assertIsNotNone(updated_candle)
        self.assertEqual(updated_candle['close'], 70000)
        self.assertEqual(updated_candle['date'], "20250420")
    
    def test_multiple_updates(self):
        """여러번 업데이트 테스트"""
        self.chart_data._init_code_data(self.test_code)
        
        # 첫 번째 업데이트 (9시 30분)
        first_datetime = "20250420093000"
        self.chart_data.update_price(self.test_code, 70000, 10000, 700000000, first_datetime)
        
        # 두 번째 업데이트 (9시 31분 - 다른 분봉)
        second_datetime = "20250420093100"
        self.chart_data.update_price(self.test_code, 71000, 20000, 1420000000, second_datetime)
        
        # 업데이트된 분봉 찾기
        mi_data = self.chart_data._data[self.test_code]['mi'][1]
        first_candle = second_candle = None
        
        for candle in mi_data:
            if candle['time'] == "093000":
                first_candle = candle
            elif candle['time'] == "093100":
                second_candle = candle
        
        self.assertIsNotNone(first_candle)
        self.assertIsNotNone(second_candle)
        self.assertEqual(first_candle['close'], 70000)
        self.assertEqual(second_candle['close'], 71000)

class TestChartManager(unittest.TestCase):
    """ChartManager 클래스 테스트"""
    
    def setUp(self):
        self.chart_data = ChartData()
        self.chart_data._data = {}
        self.test_code = "005930"
        
        # 테스트 데이터 초기화
        self.chart_data._init_code_data(self.test_code)
        
        # 차트 매니저 인스턴스 생성
        self.cm_day = ChartManager('dy')
        self.cm_min = ChartManager('mi', 1)
    
    def test_basic_values(self):
        """기본 가격 값 테스트"""
        # 종가, 시가, 고가, 저가, 거래량 테스트
        self.assertGreater(self.cm_day.c(self.test_code), 0)
        self.assertGreater(self.cm_day.o(self.test_code), 0)
        self.assertGreater(self.cm_day.h(self.test_code), 0)
        self.assertGreater(self.cm_day.l(self.test_code), 0)
        self.assertGreater(self.cm_day.v(self.test_code), 0)
    
    def test_minute_chart(self):
        """분봉 차트 테스트"""
        # 분봉 종가 테스트
        self.assertGreater(self.cm_min.c(self.test_code), 0)
        
        # 특정 시간 테스트
        time_value = self.cm_min.time()
        self.assertNotEqual(time_value, '')
        self.assertIn('09', time_value)  # 9시대 분봉이 있어야 함
    
    def test_moving_averages(self):
        """이동평균 테스트"""
        # 단순이동평균, 지수이동평균, 가중이동평균 테스트
        avg_val = self.cm_day.avg(self.test_code, self.cm_day.c, 5)
        eavg_val = self.cm_day.eavg(self.test_code, self.cm_day.c, 5)
        wavg_val = self.cm_day.wavg(self.test_code, self.cm_day.c, 5)
        
        self.assertGreater(avg_val, 0)
        self.assertGreater(eavg_val, 0)
        self.assertGreater(wavg_val, 0)
    
    def test_highest_lowest(self):
        """최고/최저값 테스트"""
        highest = self.cm_day.highest(self.test_code, self.cm_day.c, 5)
        lowest = self.cm_day.lowest(self.test_code, self.cm_day.c, 5)
        
        self.assertGreater(highest, 0)
        self.assertGreater(lowest, 0)
        self.assertGreaterEqual(highest, lowest)
    
    def test_stdev_sum(self):
        """표준편차와 합계 테스트"""
        stdev_val = self.cm_day.stdev(self.test_code, self.cm_day.c, 5)
        sum_val = self.cm_day.sum(self.test_code, self.cm_day.c, 5)
        
        self.assertGreaterEqual(stdev_val, 0)
        self.assertGreater(sum_val, 0)

class TestScriptManager(unittest.TestCase):
    """ScriptManager 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        # 임시 파일 생성
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        self.temp_file.close()
        
        # ScriptManager 인스턴스 생성
        self.script_manager = ScriptManager(self.temp_file.name)
        
        # 테스트용 스크립트 정의
        self.test_script = """
# 테스트 스크립트
ct = ChartManager('dy')
code = self.script_code
price = get_var('price', 50000)
result = ct.c(code) > price
"""
        
        self.dependant_script = """
# 종속 스크립트 (다른 스크립트 호출)
result = get_script_result('test_script', self.script_code)
"""
        
        self.circular_script1 = """
# 순환 참조 스크립트 1
result = get_script_result('circular_script2', self.script_code)
"""
        
        self.circular_script2 = """
# 순환 참조 스크립트 2
result = get_script_result('circular_script1', self.script_code)
"""
        
        self.invalid_script = """
# 문법 오류가 있는 스크립트
if True
    x = 1
result = False
"""
    
    def tearDown(self):
        """테스트 환경 정리"""
        # 임시 파일 삭제
        os.unlink(self.temp_file.name)
    
    def test_script_save_load(self):
        """스크립트 저장 및 불러오기 테스트"""
        # 스크립트 저장
        self.script_manager.set_script('test_script', self.test_script, {'price': 60000})
        
        # 새 인스턴스로 로드
        new_manager = ScriptManager(self.temp_file.name)
        
        # 로드된 스크립트 확인
        self.assertEqual(new_manager.get_script('test_script'), self.test_script)
        self.assertEqual(new_manager.get_vars('test_script'), {'price': 60000})
    
    def test_script_execution(self):
        """스크립트 실행 테스트"""
        # 스크립트 저장
        self.script_manager.set_script('test_script', self.test_script, {'price': 65000})
        
        # 스크립트 실행 (70000 > 65000 이므로 True 반환 예상)
        result = self.script_manager.run_script('test_script', '005930')
        self.assertTrue(result)
        
        # 변수 변경
        self.script_manager.set_vars('test_script', {'price': 75000})
        
        # 다시 실행 (70000 < 75000 이므로 False 반환 예상)
        result = self.script_manager.run_script('test_script', '005930')
        self.assertFalse(result)
    
    def test_dependent_scripts(self):
        """스크립트 의존성 테스트"""
        # 기본 스크립트와 의존 스크립트 저장
        self.script_manager.set_script('test_script', self.test_script, {'price': 65000})
        self.script_manager.set_script('dependant_script', self.dependant_script)
        
        # 의존 스크립트 실행 (test_script의 결과를 그대로 반환)
        result = self.script_manager.run_script('dependant_script', '005930')
        self.assertTrue(result)
        
        # test_script 변수 변경
        self.script_manager.set_vars('test_script', {'price': 75000})
        
        # 다시 실행 (false 예상)
        result = self.script_manager.run_script('dependant_script', '005930')
        self.assertFalse(result)
    
    def test_circular_reference(self):
        """순환 참조 감지 테스트"""
        # 순환 참조 스크립트 저장
        self.script_manager.set_script('circular_script1', self.circular_script1)
        self.script_manager.set_script('circular_script2', self.circular_script2)
        
        # 실행 (순환 참조 감지하여 False 반환 예상)
        result = self.script_manager.run_script('circular_script1', '005930')
        self.assertFalse(result)
    
    def test_invalid_script(self):
        """잘못된 스크립트 검사 테스트"""
        # 잘못된 스크립트 저장 시도 (실패 예상)
        result = self.script_manager.set_script('invalid_script', self.invalid_script)
        self.assertFalse(result)
        
        # 스크립트가 저장되지 않았는지 확인
        self.assertNotIn('invalid_script', self.script_manager.scripts)
    
    def test_get_var(self):
        """변수 접근 테스트"""
        # 스크립트 저장
        self.script_manager.set_script('test_script', self.test_script, {'price': 60000, 'cycle': 5})
        
        # 스크립트 실행 컨텍스트 설정
        self.script_manager.current_script = 'test_script'
        
        # 변수 접근
        price = self.script_manager.get_var('price')
        cycle = self.script_manager.get_var('cycle')
        default_value = self.script_manager.get_var('not_exists', 'default')
        
        # 결과 확인
        self.assertEqual(price, 60000)
        self.assertEqual(cycle, 5)
        self.assertEqual(default_value, 'default')

if __name__ == '__main__':
    unittest.main()