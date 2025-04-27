from public import gm, dc
from classes import la
from typing import Dict, List, Any, Union, Optional, Tuple
from datetime import datetime
import json
import logging
from threading import Lock, Thread
import time
import ast
import traceback
import re
import math
import queue
import inspect

class FunctionManager:
    """사용자 정의 함수를 관리하는 클래스"""
    # 허용 모듈 리스트 (클래스 속성)
    ALLOWED_MODULES = ['re', 'math', 'datetime', 'random', 'logging', 'json', 'collections']
    
    def __init__(self, function_file=dc.fp.function_file):
        self.function_file = function_file
        self.functions = {}  # {name: {script: str, vars: dict, type: 'function', params: list, return_type: str}}
        self.chart_manager = None  # 실행 시 주입
        self._running_functions = set()  # 실행 중인 함수 추적
        self._function_cache = {}  # 함수 반환값 캐싱 {name+args: result}
        self._load_functions()
    
    def _load_functions(self):
        """함수 파일에서 함수 로드"""
        try:
            with open(self.function_file, 'r', encoding='utf-8') as f:
                self.functions = json.load(f)
            logging.info(f"함수 {len(self.functions)}개 로드 완료")
        except FileNotFoundError:
            logging.warning(f"함수 파일 없음: {self.function_file}")
            self.functions = {}
        except json.JSONDecodeError as e:
            logging.error(f"함수 파일 형식 오류: {e}")
            self.functions = {}
    
    def _save_functions(self):
        """함수를 파일에 저장"""
        try:
            with open(self.function_file, 'w', encoding='utf-8') as f:
                json.dump(self.functions, f, ensure_ascii=False, indent=4)
            logging.info(f"함수 {len(self.functions)}개 저장 완료")
            return True
        except Exception as e:
            logging.error(f"함수 저장 오류: {e}")
            return False
    
    def set_functions(self, functions: dict):
        """함수 전체 설정 및 저장"""
        # 모든 함수 유효성 검사
        valid_functions = {}
        for name, function_data in functions.items():
            if self.check_function(name, function_data.get('script', '')):
                valid_functions[name] = function_data
            else:
                logging.warning(f"유효하지 않은 함수: {name}")
        
        self.functions = valid_functions
        return self._save_functions()
    
    def get_functions(self):
        """저장된 모든 함수 반환"""
        return self.functions
    
    def set_function(self, name: str, script: str, vars: dict = None, params: list = None, return_type: str = None):
        """단일 함수 설정 및 저장"""
        function_data = {
            'script': script,
            'vars': vars or {},
            'type': 'function',
            'params': params or [],
            'return_type': return_type or 'any'
        }
        
        if not self.check_function(name, function_data):
            logging.warning(f"유효하지 않은 함수: {name}")
            return False
        
        self.functions[name] = function_data
        return self._save_functions()
    
    def get_function(self, name: str):
        """이름으로 함수 가져오기"""
        return self.functions.get(name, {})
    
    def check_function(self, name: str, function_data: dict = None) -> bool:
        """함수 구문 및 실행 유효성 검사"""
        if function_data is None:
            function_data = self.functions.get(name, {})

        script = function_data.get('script', '')
        vars_dict = function_data.get('vars', {})
        params = function_data.get('params', [])

        if not script:
            logging.warning(f"함수가 비어있음: {name}")
            return False
        
        # 1. 구문 분석 검사
        try:
            ast.parse(script)
        except SyntaxError as e:
            line_no = e.lineno
            logging.error(f"구문 오류 ({name} 함수 {line_no}행): {e}")
            return False
        
        # 2. 보안 검증 (금지된 구문 확인)
        if self._has_forbidden_syntax(script):
            logging.error(f"보안 위반 코드 포함 ({name} 함수)")
            return False
        
        # 3. result 값 반환 확인 (함수는 반드시 result 값을 설정해야 함)
        if 'result' not in script:
            logging.error(f"함수에 result 값 설정 없음 ({name})")
            return False
        
        # 4. 파라미터 검증
        for param in params:
            if not isinstance(param, str) or not param.isidentifier():
                logging.error(f"잘못된 파라미터 이름: {param} ({name} 함수)")
                return False
        
        # 5. 가상 실행 테스트
        return self._test_execute_function(name, script, vars_dict, params)
    
    def _has_forbidden_syntax(self, script: str) -> bool:
        """금지된 구문이 있는지 확인"""
        allowed_patterns = '|'.join(self.ALLOWED_MODULES)
        forbidden_patterns = [
            r'import\s+(?!(' + allowed_patterns + ')$)',  # 허용된 모듈만 임포트 가능
            r'open\s*\(',  # 파일 열기 금지
            r'exec\s*\(',  # exec() 사용 금지
            r'eval\s*\(',  # eval() 사용 금지
            r'__import__',  # __import__ 사용 금지
            r'subprocess',  # subprocess 모듈 금지
            r'os\.',  # os 모듈 사용 금지
            r'sys\.',  # sys 모듈 사용 금지
            r'while\s+.*:',  # while 루프 금지 (무한 루프 방지)
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, script):
                return True
        return False
    
    def _safe_loop(self, iterable, func):
        """안전한 루프 실행 함수"""
        results = []
        for item in iterable:
            results.append(func(item))
        return results
    
    def _create_test_chart_manager(self):
        """테스트용 ChartManager 생성 (ScriptManager와 동일)"""
        # ScriptManager의 _create_test_chart_manager와 동일한 구현
        # (코드 중복 방지를 위해 실제 구현시에는 별도 유틸리티로 분리 권장)
        class TestChartManager:
            """테스트용 차트 매니저"""
            def __init__(self):
                self._test_data = {
                    '005930': [  # 삼성전자 가상 데이터
                        {'date': '20240101', 'open': 70000, 'high': 71000, 'low': 69000, 'close': 70500, 'volume': 1000000, 'amount': 70500000000},
                        {'date': '20240102', 'open': 70500, 'high': 72000, 'low': 70000, 'close': 71000, 'volume': 1200000, 'amount': 85200000000},
                        {'date': '20240103', 'open': 71000, 'high': 71500, 'low': 70000, 'close': 71200, 'volume': 900000, 'amount': 64080000000},
                    ]
                }
            
            # ChartManager 메서드들 구현 (생략 - 동일)
            # ...
        
        return TestChartManager()
    
    def _test_execute_function(self, name: str, script: str, vars_dict: dict = None, params: list = None) -> bool:
        """테스트 환경에서 함수 실행 시도"""
        try:
            # 가상 환경에서 안전하게 실행
            # 테스트용 ChartManager 생성
            test_cm = self._create_test_chart_manager()
            
            # 테스트용 글로벌/로컬 환경 설정
            globals_dict = {
                # Python 내장 함수들
                'range': range,
                'len': len,
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs,
                'all': all,
                'any': any,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                
                # 모듈들
                'math': math,
                'logging': logging,
                'datetime': datetime,
                
                # 차트 매니저
                'ChartManager': lambda cycle='dy', tick=1: test_cm,
                
                # 유틸리티 함수
                'loop': self._safe_loop,
                'run_function': lambda sub_name, *args: True
            }
                
            # 변수 추가
            if vars_dict:
                for var_name, var_value in vars_dict.items():
                    globals_dict[var_name] = var_value
            
            # 파라미터 추가 (테스트용 더미 값)
            if params:
                for param in params:
                    globals_dict[param] = 0  # 기본값 (테스트용)
            
            # 컴파일 및 제한된 실행
            code_obj = compile(script, f"<function_{name}>", 'exec')
            
            # 실행 시간 제한
            start_time = time.time()
            locals_dict = {}
            
            try:
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                if exec_time > 0.1:  # 0.1초 초과 실행 시 경고
                    logging.warning(f"함수 실행 시간 초과 ({name}): {exec_time:.4f}초")
                
                # result 값이 설정되었는지 확인
                if 'result' not in locals_dict:
                    logging.error(f"함수 실행 결과 없음 ({name}): result 값이 설정되지 않았습니다")
                    return False
                
                return True
            except Exception as e:
                logging.error(f"함수 실행 오류 ({name}): {type(e).__name__} - {e}")
                return False
        except Exception as e:
            logging.error(f"함수 테스트 중 예상치 못한 오류 ({name}): {e}")
            return False
    
    def run_function(self, name: str, *args):
        """함수 실행
        name: 함수 이름
        *args: 함수 인자들
        
        Returns: Any - 함수 실행 결과 값
        """
        # 순환 참조 방지
        function_key = f"{name}:{','.join(str(arg) for arg in args)}"
        if function_key in self._running_functions:
            logging.warning(f"순환 참조 감지: {function_key}")
            return None
        
        # 캐싱된 결과가 있는지 확인
        if function_key in self._function_cache:
            return self._function_cache[function_key]
        
        # 실행 중인 함수에 추가
        self._running_functions.add(function_key)
        
        try:
            # 함수 가져오기
            function_data = self.get_function(name)
            script = function_data.get('script', '')
            vars_dict = function_data.get('vars', {})
            params = function_data.get('params', [])
            
            if not script:
                logging.warning(f"함수 없음: {name}")
                return None
            
            # 파라미터 개수 확인
            if len(args) != len(params):
                logging.error(f"함수 파라미터 개수 불일치: {name}, 필요: {len(params)}, 제공: {len(args)}")
                return None
            
            # 차트 매니저 생성
            if not self.chart_manager:
                from chart import ChartManager
                self.chart_manager = ChartManager()
            
            # 글로벌 환경 설정
            globals_dict = {
                # Python 내장 함수들
                'range': range,
                'len': len,
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs,
                'all': all,
                'any': any,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                
                # 모듈들
                'math': math,
                'logging': logging,
                'datetime': datetime,
                
                # 차트 매니저
                'ChartManager': ChartManager,
                
                # 유틸리티 함수
                'loop': self._safe_loop,
                'run_function': lambda sub_name, *sub_args: self.run_function(sub_name, *sub_args)
            }
                
            # 변수 추가
            for var_name, var_value in vars_dict.items():
                globals_dict[var_name] = var_value
            
            # 파라미터 추가
            for param_name, param_value in zip(params, args):
                globals_dict[param_name] = param_value
            
            # 컴파일 및 실행
            code_obj = compile(script, f"<function_{name}>", 'exec')
            locals_dict = {}
            
            # 실행 시간 측정
            start_time = time.time()
            
            try:
                exec(code_obj, globals_dict, locals_dict)
                exec_time = time.time() - start_time
                
                # 실행 시간이 너무 오래 걸리면 경고
                if exec_time > 0.05:  # 50ms 이상 걸리면 경고
                    logging.warning(f"함수 실행 시간 초과 ({name}): {exec_time:.4f}초")
                
                # 실행 결과 가져오기 (result 값)
                if 'result' not in locals_dict:
                    logging.error(f"함수 실행 결과 없음 ({name}): result 값이 설정되지 않았습니다")
                    return None
                
                result = locals_dict['result']
                
                # 결과 캐싱 (간단한 타입만)
                if isinstance(result, (int, float, str, bool)) or result is None:
                    self._function_cache[function_key] = result
                
                return result
            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f"함수 실행 오류 ({name}): {type(e).__name__} - {e}\n{tb}")
                return None
        finally:
            # 실행 완료 후 추적 목록에서 제거
            if function_key in self._running_functions:
                self._running_functions.remove(function_key)
    
    def clear_cache(self, name: str = None):
        """함수 캐시 초기화 (특정 함수 또는 전체)"""
        if name:
            # 특정 함수의 캐시만 삭제
            keys_to_remove = [k for k in self._function_cache if k.startswith(f"{name}:")]
            for key in keys_to_remove:
                del self._function_cache[key]
        else:
            # 전체 캐시 삭제
            self._function_cache.clear()
    
    def get_function_metadata(self, name: str) -> dict:
        """함수의 메타데이터 반환 (파라미터, 반환 타입 등)"""
        function_data = self.get_function(name)
        if not function_data:
            return {}
            
        return {
            'name': name,
            'params': function_data.get('params', []),
            'return_type': function_data.get('return_type', 'any'),
            'description': function_data.get('description', '')
        }
    
    def analyze_function(self, name: str) -> dict:
        """함수 분석 결과 반환 (파라미터, 반환값, 성능 등)"""
        function_data = self.get_function(name)
        if not function_data:
            return {}
            
        script = function_data.get('script', '')
        
        # 파싱 및 분석
        try:
            tree = ast.parse(script)
            
            # 함수 사용 분석
            function_calls = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and hasattr(node, 'func') and hasattr(node.func, 'id'):
                    function_calls.append(node.func.id)
            
            # ChartManager 사용 분석
            chart_usage = any('ChartManager' in line for line in script.split('\n'))
            
            # 로깅 사용 분석
            logging_usage = 'logging' in script
            
            return {
                'name': name,
                'size': len(script),
                'function_calls': list(set(function_calls)),
                'uses_chart': chart_usage,
                'uses_logging': logging_usage,
                'params': function_data.get('params', []),
                'return_type': function_data.get('return_type', 'any')
            }
        except Exception as e:
            logging.error(f"함수 분석 오류 ({name}): {e}")
            return {'name': name, 'error': str(e)}
    
    def export_function(self, name: str) -> str:
        """함수를 독립적인 Python 스크립트로 내보내기"""
        function_data = self.get_function(name)
        if not function_data:
            return ""
            
        script = function_data.get('script', '')
        params = function_data.get('params', [])
        
        # 함수 형태로 변환
        param_str = ", ".join(params)
        
        export_code = f"""# 함수: {name}
def {name}({param_str}):
    \"""
    FunctionManager에서 내보낸 함수
    \"""
    # 원본 스크립트 코드
{script.replace('\n', '\n    ')}
    
    return result

# 테스트 코드
if __name__ == "__main__":
    # 테스트 호출
    test_result = {name}({", ".join("0" for _ in params)})
    print(f"테스트 결과: {{{name}}} -> {{test_result}}")
"""
        return export_code
    
    def import_function(self, name: str, python_code: str) -> bool:
        """Python 함수 코드에서 함수 가져오기"""
        try:
            # 코드 파싱
            tree = ast.parse(python_code)
            
            # 함수 정의 찾기
            function_def = None
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    function_def = node
                    break
            
            if not function_def:
                logging.error(f"함수 정의를 찾을 수 없음: {name}")
                return False
            
            # 파라미터 목록 추출
            params = [arg.arg for arg in function_def.args.args]
            
            # 함수 본문 추출 및 변환
            func_body_lines = []
            
            # 소스 코드 라인 가져오기
            source_lines = python_code.split('\n')
            
            # 함수 본문의 시작과 끝 라인 찾기
            start_line = function_def.lineno
            end_line = 0
            
            for node in function_def.body:
                end_line = max(end_line, node.lineno)
                if hasattr(node, 'end_lineno') and node.end_lineno is not None:
                    end_line = max(end_line, node.end_lineno)
            
            # 함수 본문 라인 가져오기 (들여쓰기 제거)
            body_indent = None
            for i in range(start_line, end_line + 1):
                if i - 1 < len(source_lines):
                    line = source_lines[i - 1]
                    if line.strip() and body_indent is None:
                        # 첫 번째 내용이 있는 라인에서 들여쓰기 감지
                        body_indent = len(line) - len(line.lstrip())
                    
                    if body_indent is not None:
                        # 들여쓰기 제거
                        if line.startswith(' ' * body_indent):
                            func_body_lines.append(line[body_indent:])
                        else:
                            func_body_lines.append(line)
            
            # 스크립트 형태로 변환
            script = '\n'.join(func_body_lines)
            
            # 'return' 문을 'result = ' 형태로 변환
            script = re.sub(r'return\s+(.+?)$', r'result = \1', script, flags=re.MULTILINE)
            
            # 함수 저장
            self.set_function(name, script, {}, params)
            return True
            
        except Exception as e:
            logging.error(f"함수 가져오기 오류 ({name}): {e}")
            return False 
        

