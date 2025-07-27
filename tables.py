from public import dc, gm
import threading
import copy

class TableColumns:     # 테이블 데이타 컬럼 정의
    hd잔고합산 = {
        '키': '순번',
        '정수': ['순번', '총매입금액', '총평가금액', '추정예탁자산', '총평가손익금액'],
        '실수': ['총수익률(%)'],
    }
    hd잔고합산.update({
        '컬럼': hd잔고합산['정수'] + hd잔고합산['실수'] # l2잔고합산
    })

    hd잔고목록 = {
        '키': '종목번호',
        '정수': ["보유수량", "매입가", "매입금액", "현재가", "평가금액", "평가손익", '전일대비', \
                        '누적거래량', '거래량', '주문가능수량', '최고가', '감시', '보존', '상태', '매수수량', '매수가', '매수금액'],
        '실수': ["수익률(%)", "등락율", '이익보존율', '감시시작율'],
        '컬럼': ["종목번호", "종목명", "보유수량", "매입가", "매입금액", "현재가", "평가금액", "평가손익", "수익률(%)"],
        '추가': ['주문가능수량', '전일대비', "등락율", '누적거래량', '거래량', '최고가', '매수수량', '매수가', '매수금액',\
                        '보존', '이익보존율', '감시', '감시시작율', '매수전략', '전략명칭', '매수일자', '매수시간', '매수번호'], 
    }
    hd잔고목록.update({
        '헤더': hd잔고목록['컬럼'] + ["매수일자", "매수시간", '등락율', '누적거래량', '주문가능수량'],
        '확장': hd잔고목록['컬럼'] + hd잔고목록['추가'],
    })

    hd조건목록 = {
        '키': '종목코드',
        '정수': [],
        '실수': [],
        '컬럼': ['이탈', '종목코드', '종목명'],
    }

    hd손익목록 = {
        '키': '매수시간',
        '정수': ['매수수량', '매수금액', '매도수량', '매도금액', '제비용', '손익금액'],
        '실수': ['손익율'],
    }
    hd손익목록.update({
        '컬럼': ['매수시간', '종목코드', '종목명'] + hd손익목록['정수'] + ['손익율', '전략명칭']
    })

    # hd주문목록 = {
    #     '키': '키', # 종목코드_구분 : 005930_매수
    #     '정수': ['주문수량', '주문가격', '미체결수량'],
    #     '실수': [],
    #     '컬럼': ['키', '구분', '상태', '종목코드', '종목명', '주문번호', '주문수량', '주문가격', '미체결수량', '요청명', '비고'],
    #     '헤더': ['구분', '상태', '종목코드', '종목명', '주문수량', '주문가격', '미체결수량', '비고'],
    # }

    hd주문목록 = {
        '키': ['종목코드', '구분'], # 종목코드_구분 : 005930_매수
        '정수': ['주문수량', '주문가격', '미체결수량'],
        '실수': [],
        '컬럼': ['종목코드', '구분', '상태', '종목명', '주문번호', '주문수량', '주문가격', '미체결수량', '요청명', '비고'],
        '헤더': ['구분', '상태', '종목코드', '종목명', '주문수량', '주문가격', '미체결수량', '비고'],
    }

    hd매매목록 = {
        '키': '처리시간',
        '정수': ['현재가', '주문수량', '주문가격', '미체결수량', '체결량', '체결가', '체결누계금액'],
        '실수': [],
        '컬럼': [ '처리시간', '주문구분', '주문상태', '종목코드', '종목명', '주문수량', '주문가격', '미체결수량', '체결량', '체결가', '체결누계금액',\
                '매매구분', '주문번호', '원주문번호', '전략명칭']
    }

    hd예수금 = {
        '키': '순번',
        '정수': ['순번', 'd+1추정예수금', 'd+1매도매수정산금', 'd+1미수변제소요금', 'd+1출금가능금액',\
                      'd+2추정예수금', 'd+2매도매수정산금', 'd+2미수변제소요금', 'd+2출금가능금액',\
                      '예수금', '주식증거금현금', '미수확보금', '권리대용금',\
                      '20%종목주문가능금액', '30%종목주문가능금액', '40%종목주문가능금액', '100%종목주문가능금액',\
                      '주문가능금액', '출금가능금액', '현금미수금'],
        '실수': [],
    }
    hd예수금.update({
        '컬럼': hd예수금['정수'],
    })

    hd일지합산 = {
        '키': '순번',
        '정수': ['순번', '총매수금액', '총매도금액', '총수수료_세금', '총정산금액', '총손익금액'],
        '실수': ['총수익률'],
    }
    hd일지합산.update({
        '컬럼': hd일지합산['정수'] + hd일지합산['실수'],
    })

    hd일지목록 = {
        '키': '종목코드',
        '정수': ['매수금액','매도금액', '손익금액', '매수수량', '매수평균가', '매도수량',  '매도평균가', '수수료_제세금'],
        '실수': ['수익률'],
    }
    hd일지목록.update({
        '컬럼': ['종목코드', '종목명'] + hd일지목록['정수'][:3] + hd일지목록['실수'] + hd일지목록['정수'][3:],
    })

    hd체결목록 = {
        '키': '매수번호',
        '정수': ['매수수량', '매수가', '매수금액', '매도수량', '매도가', '매도금액', '손익금액', '제비용'],
        '실수': ['손익율'],
        '컬럼': ['매수일자', '매수시간', '종목번호', '종목명', '손익금액', '손익율', '매수수량', '매수금액', '매도수량', '매도금액', \
                        '매수가', '매도가', '제비용', '매도일자', '매도시간', '매수번호', '매도번호', '매수전략', '전략명칭'],
    }

    hd전략정의 = {
            '키': '전략명칭',
            '정수': ['체결횟수', '종목제한', '보유제한', '청산호가', '매수지연초', '매도지연초', '매수호가', '투자금액', '매도호가', '남은횟수'],
            '실수': ['예수금율', '이익실현율', '이익보존율', '감시시작율','스탑주문율', '손실제한율'],
            '컬럼': dc.const.WIDGET_MAP.keys(), # 컬럼명
            '헤더': ['전략명칭', '투자금액', '매수적용', '매수전략', '매도적용', '매도전략', '이익실현율', '이익보존율', '손실제한율', '감시적용', '감시시작율', '스탑주문율'],
        }

    hd차트자료 = {
        '키': ['종목코드', '일자', '시간'],
        '중복키': False,
        '정수': ['시가', '고가', '저가', '현재가', '거래량', '거래대금'],
        '실수': [],
        '컬럼': ['종목코드', '종목명', '일자', '시간', '시가', '고가', '저가', '현재가', '거래량', '거래대금', '비고'],
        '헤더': [
            ['종목코드', '시간', '시가', '고가', '저가', '현재가', '거래량', '거래대금', '비고'],
            ['종목코드', '종목명', '시가', '고가', '저가', '현재가', '거래량', '거래대금', '비고'],
            ['종목코드', '일자', '시간', '시가', '고가', '저가', '현재가', '거래량', '거래대금', '비고'],
        ]
    }

    hd스크립트 = {
        '키': '스크립트명',
        '정수': [],
        '실수': [],
        '컬럼': ['스크립트명', '타입', '스크립트', '설명'],
    }

    hd당일종목 = {
        '키': '종목코드',
        '정수': [],
        '실수': [],
        '컬럼': ['종목코드', '종목명', '확인', '비고'],
    }

    hd수동종목 = hd당일종목.copy()

tbl = TableColumns()

# QReadWriteLock 사용
class QTableManager:
    """
    # 1. 단일 키 사용 (기존 방식)
    config = {
        '키': '종목코드',
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 2. 복합 키 사용
    config = {
        '키': ['종목코드', '매수일자'],  # 두 컬럼을 합쳐서 키로 사용
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '매수일자', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 3. 키 없는 모드
    config = {
        '키': None,  # 키 사용 안 함
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 4. 중복 키 허용
    config = {
        '키': '종목코드',
        '중복키': True,  # 같은 종목코드가 여러 행에 있을 수 있음
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)
    """

    def __init__(self, config):
        """
        쓰레드 안전한 데이터 관리 클래스 초기화
        
        Parameters:
        config (dict): 설정 정보 딕셔너리
            - '키': 고유 키로 사용할 컬럼명 또는 컬럼명 리스트 (복합 키), None이면 키 없는 모드로 동작
            - '중복키': True면 동일 키 값을 갖는 여러 행 허용 (기본값: False)
            - '정수': 정수형으로 변환할 컬럼 리스트
            - '실수': 실수형으로 변환할 컬럼 리스트
            - '컬럼': 전체 컬럼 리스트
            - '헤더': 화면용 컬럼 리스트 또는 리스트의 리스트 (여러 헤더 셋)
        """
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        
        # RLock 대신 QReadWriteLock 사용
        from PyQt5.QtCore import QReadWriteLock
        self.lock = QReadWriteLock()
        
        # 설정 정보 저장
        self.key_columns = config.get('키', None)
        
        # key_columns가 문자열이면 리스트로 변환
        if isinstance(self.key_columns, str):
            self.key_columns = [self.key_columns]
            
        # 키 중복 허용 여부
        self.allow_duplicate_keys = config.get('중복키', False)
        
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('확장', config.get('컬럼', []))
        
        # 헤더 설정 - 리스트의 리스트로 처리
        header_config = config.get('헤더', [])
        if header_config and not isinstance(header_config[0], list):
            # 단일 리스트인 경우, 리스트의 리스트로 변환
            self.display_columns = [header_config]
        else:
            self.display_columns = header_config
            
        # 헤더가 없는 경우 all_columns 사용
        if not self.display_columns:
            self.display_columns = [self.all_columns]

        # 키가 있는 경우 키 컬럼이 all_columns에 있는지 확인
        if self.key_columns:
            for key_col in self.key_columns:
                if key_col not in self.all_columns:
                    raise ValueError(f"키 컬럼 '{key_col}'이 '컬럼' 리스트에 없습니다.")
        
        if not self.all_columns:
            raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
        
        # 자주 사용하는 상수와 객체 미리 정의
        # 정렬 상수
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor
        
        self.align_right = Qt.AlignRight | Qt.AlignVCenter
        self.align_left = Qt.AlignLeft | Qt.AlignVCenter
        self.align_center = Qt.AlignCenter
        
        # 색상 객체
        self.color_positive = QColor(255, 0, 0)  # 적색 (손익 양수)
        self.color_negative = QColor(0, 0, 255)  # 청색 (손익 음수)
        self.color_zero = QColor(0, 0, 0)        # 검정색 (손익 0)
        
        # 손익 관련 컬럼
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률", "등락율"]

        # 리사이즈
        self._resize = True
        
        # 키 없는 모드인지 여부
        self.no_key_mode = self.key_columns is None
    
    def _get_key_for_item(self, item):
        """
        항목에서 키 값을 추출
        
        Parameters:
        item (dict): 키 값을 추출할 항목
        
        Returns:
        키 없는 모드면 None, 단일 키면 값, 복합 키면 튜플
        """
        if self.no_key_mode:
            return None
            
        if len(self.key_columns) == 1:
            return item.get(self.key_columns[0])
        else:
            # 복합 키는 튜플로 반환
            return tuple(item.get(key_col) for key_col in self.key_columns)
    
    def _convert_value(self, column, value):
        """
        값을 적절한 타입으로 변환
        
        Parameters:
        column (str): 컬럼명
        value: 변환할 값
        
        Returns:
        변환된 값
        """
        # 기본값 정의
        default_values = {
            'int': 0,
            'float': 0.0,
            'str': ""
        }
        
        # 문자열 처리
        if isinstance(value, str):
            value = value.strip()
            if column not in self.int_columns + self.float_columns:
                return value
            
            # 쉼표가 포함된 숫자 문자열 처리
            if any(c.isdigit() for c in value):
                value = value.replace(',', '')
        
        # None이나 빈 문자열은 기본값으로
        if value is None or value == "":
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                default_values['str']
        
        # 타입별 변환
        try:
            if column in self.int_columns:
                return int(float(value))
            elif column in self.float_columns:
                return float(value)
            else:
                # 불리언 및 기타 타입은 그대로 유지
                return value
        except (ValueError, TypeError):
            # 변환 실패 시 기본값 반환
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                str(value)
            
    def _process_item(self, item):
        """
        항목의 각 값을 적절한 타입으로 변환
        
        Parameters:
        item (dict): 변환할 항목
        
        Returns:
        dict: 변환된 항목
        """
        processed_item = {}
        # 모든 컬럼을 기본값으로 먼저 초기화
        for column in self.all_columns:
            if column in self.int_columns:
                processed_item[column] = 0
            elif column in self.float_columns:
                processed_item[column] = 0.0
            else:
                processed_item[column] = ""
                
        # 주어진 값으로 업데이트
        for column in self.all_columns:
            if column in item:
                processed_item[column] = self._convert_value(column, item.get(column, ''))
        
        return processed_item

    def get(self, key=None, filter=None, type=None, column=None):
        """
        get() -> [{}]                     # 전체 데이터 사전 리스트 반환
        get(type='df') -> DataFrame       # DataFrame으로 반환
        get(key='key') -> {}              # 'key'로 찾은 행 반환
        get(key=숫자) -> {}               # 인덱스로 행 반환
        get(key=(값1,값2)) -> [{}]        # 복합 키로 찾은 행(들) 반환
        get(filter={}) -> [{}]            # 조건에 맞는 행들 반환
        get(filter={}, column='col') -> []  # 조건에 맞는 행들의 특정 컬럼 값들 리스트 반환
        get(column='col') -> []           # 특정 컬럼 값들 리스트 반환
        get(column=['c1','c2']) -> [{}]   # 지정 컬럼만 포함한 사전 리스트 반환
        get(key='key', column='col') -> 값  # 특정 행의 특정 컬럼 값 반환
        get(key='key', column=['c1','c2']) -> (값1, 값2, ...)  # 특정 행의 여러 컬럼 값 튜플 반환
        """
        import copy
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            # 0. 키가 정수형인 경우 (인덱스로 접근)
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return None
            
            # 1. 특정 키 + 특정 컬럼 조회
            if key is not None and column is not None:
                items = self._find_items_by_key(key)
                if not items:
                    return None
                
                # 키 중복 허용이 아닌 경우 첫 번째 항목만 사용
                item = items[0] if isinstance(items, list) else items
                
                # 컬럼이 리스트인 경우 (여러 컬럼 조회)
                if isinstance(column, (list, tuple)):
                    if len(column) == 1:
                        # 단일 컬럼이면 값만 반환
                        return item.get(column[0])
                    else:
                        # 여러 컬럼이면 튜플로 반환
                        return tuple(item.get(col) for col in column)
                # 컬럼이 문자열인 경우 (단일 컬럼 조회)
                elif isinstance(column, str):
                    return item.get(column)
                return None
            
            # 2. 전체 데이터 + 특정 컬럼 조회
            if column is not None:
                # 컬럼이 리스트인 경우
                if isinstance(column, (list, tuple)):
                    result = []
                    for item in self.data:
                        filtered_item = {col: item.get(col) for col in column if col in item}
                        result.append(filtered_item)
                    return copy.deepcopy(result)
                # 컬럼이 문자열인 경우
                elif isinstance(column, str):
                    # 단일 컬럼이면 값만 추출하여 리스트로 반환
                    return [item.get(column) for item in self.data]
                
            # 3. 특정 키 조회
            if key is not None:
                items = self._find_items_by_key(key)
                if not items: return None

                # 키 중복 허용이면 여러 항목 반환 가능
                if self.allow_duplicate_keys and isinstance(items, list):
                    return copy.deepcopy(items)
                else:
                    # 중복 허용 아니면 첫 번째 항목만 반환
                    return copy.deepcopy(items)
            
            # 4. 필터링 조회
            if filter is not None:
                return self._filter_data(filter)
            
            # 5. 전체 데이터 조회
            data_copy = copy.deepcopy(self.data)
            
            # 6. DataFrame 반환 요청인 경우
            if type == 'df':
                try:
                    import pandas as pd
                    return pd.DataFrame(data_copy)
                except ImportError:
                    raise ImportError("pandas 라이브러리가 필요합니다. 'pip install pandas'로 설치하세요.")
            
            # 기본적으로 리스트 반환
            return data_copy
        finally:
            self.lock.unlock()
    
    def _find_items_by_key(self, key):
        """
        키 값으로 항목 찾기
        
        Parameters:
        key: 찾을 키 값
        
        Returns:
        중복 키 허용이면 항목 리스트, 아니면 단일 항목
        """
        if self.no_key_mode:
            return None
        
        if key not in self.data_dict:
            return None
        
        return self.data_dict.get(key)
    
    def _add_to_dict(self, key_value, item):
        """
        딕셔너리에 항목 추가
        
        Parameters:
        key_value: 키 값 (문자열, 숫자 또는 튜플)
        item (dict): 추가할 항목
        """
        if self.allow_duplicate_keys:
            # 중복 키 허용 모드: 리스트로 항목 저장
            if key_value in self.data_dict:
                self.data_dict[key_value].append(item)
            else:
                self.data_dict[key_value] = [item]
        else:
            # 중복 키 비허용 모드: 단일 항목 저장
            self.data_dict[key_value] = item

    def set(self, key=None, filter=None, data=None):
        """
        set(key='key', data={}) -> bool   # 특정 키 행 추가/업데이트
        set(key=(값1,값2), data={}) -> bool # 복합 키 행 추가/업데이트
        set(filter={}, data={}) -> bool   # 조건 만족 행들 업데이트
        set(data={}) -> bool              # 모든 행의 지정 컬럼 업데이트
        set(data=[{}, {}]) -> bool        # 전체 데이터 대체
        """
        if data is None:
            return False
                
        # 리스트 타입 체크 (데이터 대체 모드)
        if isinstance(data, list):
            # 쓰기 락 사용
            self.lock.lockForWrite()
            try:
                # 키 모드일 때 키 필드 검증
                if not self.no_key_mode:
                    for item in data:
                        for key_col in self.key_columns:
                            if key_col not in item:
                                raise ValueError(f"모든 항목에 키 컬럼('{key_col}')이 필요합니다.")
                
                # 데이터 대체
                self.data = []
                self.data_dict = {}
                for item in data:
                    processed_item = self._process_item(item)
                    self.data.append(processed_item)
                
                    # 키 모드일 때 딕셔너리에 추가
                    if not self.no_key_mode:
                        key_value = self._get_key_for_item(processed_item)
                        self._add_to_dict(key_value, processed_item)
                
                return True
            finally:
                self.lock.unlock()
            
        # 딕셔너리 타입 체크 (업데이트 모드)
        if isinstance(data, dict):
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data:
                return False
            
            # 쓰기 락 사용    
            self.lock.lockForWrite()
            try:
                # 1. 특정 키 업데이트/추가
                if key is not None:
                    return self._set_item_by_key(key, valid_data)
                
                # 2. 필터링된 항목 업데이트
                if filter is not None:
                    return self._update_filtered_items(filter, valid_data)
                
                # 3. 전체 항목 업데이트
                return self._update_all_items(valid_data)
            finally:
                self.lock.unlock()
                
        return False
    
    def _set_item_by_key(self, key, data):
        """
        키로 항목 추가/업데이트
        
        Parameters:
        key: 키 값 (단일 값 또는 복합 키 튜플)
        data (dict): 업데이트할 데이터
        
        Returns:
        bool: 성공 여부
        """
        if self.no_key_mode:
            # 키 없는 모드에서는 인덱스로 처리
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    for column, value in data.items():
                        if column in self.all_columns:
                            self.data[key][column] = self._convert_value(column, value)
                    return True
            return False
        
        # 기존 항목 찾기
        items = self._find_items_by_key(key)
        
        # 중복 허용 모드일 때
        if self.allow_duplicate_keys:
            if items:
                # 첫 번째 항목만 업데이트
                for column, value in data.items():
                    if column in self.all_columns and column not in self.key_columns:
                        items[0][column] = self._convert_value(column, value)
                return True
        elif items:
            # 중복 비허용 모드일 때 항목 업데이트
            for column, value in data.items():
                if column in self.all_columns and column not in self.key_columns:
                    items[column] = self._convert_value(column, value)
            return True
        
        # 신규 항목 추가
        # 모든 컬럼 기본값으로 초기화
        item = {}
        for column in self.all_columns:
            # 기본값 설정
            if column in self.int_columns:
                item[column] = 0
            elif column in self.float_columns:
                item[column] = 0.0
            else:
                item[column] = ""
        
        # 키 컬럼 설정
        if isinstance(key, tuple) and len(key) == len(self.key_columns):
            # 복합 키 처리
            for i, key_col in enumerate(self.key_columns):
                item[key_col] = key[i]
        elif len(self.key_columns) == 1:
            # 단일 키 처리
            item[self.key_columns[0]] = key
        
        # 데이터 채우기
        for column, value in data.items():
            if column in self.all_columns:
                item[column] = self._convert_value(column, value)
        
        # 데이터 추가
        self.data.append(item)
        self._add_to_dict(key, item)
        self._resize = True
        return True
    
    def _update_filtered_items(self, filter, data):
        """필터링된 항목 업데이트"""
        updated = False
        for item in self.data:
            if self._match_conditions(item, filter):
                # 키 컬럼은 업데이트하지 않음
                for column, value in data.items():
                    if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                        item[column] = self._convert_value(column, value)
                updated = True
        return updated
    
    def _update_all_items(self, data):
        """모든 항목 업데이트"""
        if not self.data:
            return False
        
        for item in self.data:
            for column, value in data.items():
                if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                    item[column] = self._convert_value(column, value)
        return True
    
    def delete(self, key=None, filter=None):
        """
        delete() -> bool                  # 모든 데이터 삭제
        delete(key='key') -> bool         # 특정 키 행 삭제
        delete(key=(값1,값2)) -> bool     # 복합 키 행 삭제
        delete(filter={}) -> bool         # 조건 만족 행들 삭제
        """
        # 쓰기 락 사용
        self.lock.lockForWrite()
        try:
            # 1. 특정 키 삭제
            if key is not None:
                # 키 없는 모드에서는 인덱스로 처리
                if self.no_key_mode:
                    if isinstance(key, int) and 0 <= key < len(self.data):
                        del self.data[key]
                        self._resize = True
                        return True
                    return False
                    
                # 키 모드에서는 키로 처리
                items = self._find_items_by_key(key)
                if not items:
                    return False
                
                if self.allow_duplicate_keys:
                    # 중복 키 허용 모드: 모든 항목 삭제
                    for item in items[:]:  # 복사본으로 반복
                        if item in self.data:
                            self.data.remove(item)
                    # 딕셔너리에서 키 삭제
                    self.data_dict.pop(key, None)
                else:
                    # 중복 키 비허용 모드: 단일 항목 삭제
                    if items in self.data:
                        self.data.remove(items)
                    self.data_dict.pop(key, None)
                    
                self._resize = True
                return True
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if not items_to_delete:
                    return False
                
                for item in items_to_delete:
                    # 키 모드일 때 딕셔너리에서도 삭제
                    if not self.no_key_mode:
                        key_val = self._get_key_for_item(item)
                        
                        if self.allow_duplicate_keys:
                            # 중복 키 허용 모드: 리스트에서 항목 제거
                            if key_val in self.data_dict:
                                items_list = self.data_dict[key_val]
                                if item in items_list:
                                    items_list.remove(item)
                                # 리스트가 비었으면 키 삭제
                                if not items_list:
                                    self.data_dict.pop(key_val, None)
                        else:
                            # 중복 키 비허용 모드: 키 삭제
                            self.data_dict.pop(key_val, None)
                
                    if item in self.data:
                        self.data.remove(item)
                    
                    if items_to_delete:
                        self._resize = True
                
                return bool(items_to_delete)
            
            # 3. 전체 데이터 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            return True
        finally:
            self.lock.unlock()
    
    def _filter_data(self, conditions):
        """
        # conditions : {컬럼: 값} 컬럼과 값 비교
        {'col': 값}
        # conditions : {컬럼: (연산자, 값)}
        {'col': ('>', 값)}                # col > 값
        {'col': ('<', 값)}                # col < 값
        {'col': ('>=', 값)}               # col >= 값
        {'col': ('<=', 값)}               # col <= 값
        {'col': ('==', 값)}               # col == 값
        {'col': ('!=', 값)}               # col != 값
        {'col': ('>', '@other_col')}      # col > other_col (컬럼 간 비교)
        """
        import copy
        result = []
        for row in self.data:
            if self._match_conditions(row, conditions):
                result.append(copy.deepcopy(row))
        return result
    
    def _match_conditions(self, row, conditions):
        """항목이 조건에 맞는지 확인"""
        for column, value in conditions.items():
            if column not in row:
                return False
                
            item_value = row[column]
            
            # 문자열인 경우 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 컬럼 간 비교인 경우 ('컬럼' 또는 '@컬럼')
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                # '@'로 시작하는 문자열은 다른 컬럼을 참조
                if isinstance(compare_value, str) and compare_value.startswith('@'):
                    other_column = compare_value[1:]  # '@' 제거
                    if other_column not in row:
                        return False
                    other_value = row[other_column]
                    if not self._compare_values(item_value, op, other_value):
                        return False
                # 일반 비교값
                else:
                    if not self._compare_values(item_value, op, compare_value):
                        return False
            # 그 외의 경우 정확히 일치하는지 확인
            elif item_value != value:
                return False
                
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """숫자형 값 비교 연산"""
        ops = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y,
            '!=': lambda x, y: x != y
        }
        
        if operator in ops:
            try:
                return ops[operator](item_value, compare_value)
            except (TypeError, ValueError):
                return False
        return False

    def len(self, filter=None):
        """
        len() -> int                      # 전체 행 수 반환
        len(filter={}) -> int             # 조건 만족 행 수 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
        finally:
            self.lock.unlock()
    
    def in_key(self, key):
        """
        in_key('key') -> bool             # 키 존재 여부
        in_key((값1, 값2)) -> bool        # 복합 키 존재 여부
        """
        # 키 없는 모드에서는 항상 False
        if self.no_key_mode:
            return False
            
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            return key in self.data_dict
        finally:
            self.lock.unlock()
    
    def in_column(self, column, value):
        """
        in_column('col', 값) -> bool      # 컬럼에 값 존재 여부
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if column not in self.all_columns:
                return False
            
            # 타입 변환
            converted_value = self._convert_value(column, value)
            
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
        finally:
            self.lock.unlock()
    
    def sum(self, column=None, filter=None):
        """
        sum(column=['c1', 'c2']) -> (합1, 합2, ...)  # 지정 컬럼 합계 튜플 반환
        sum(column=[], filter={}) -> (합1, 합2, ...)  # 조건 만족 행들의 합계 반환
        """
        # 읽기 락 사용
        self.lock.lockForRead()
        try:
            if not column:
                return ()
            
            # 합계 계산할 데이터 선택
            data_to_sum = self.data
            if filter is not None:
                data_to_sum = self._filter_data(filter)
            
            # 각 컬럼별 합계 계산
            result = []
            if isinstance(column, str):
                column = [column]
            for col in column:
                if col in self.int_columns or col in self.float_columns:
                    total = sum(item.get(col, 0) for item in data_to_sum)
                    result.append(total)
                else:
                    # 숫자형이 아닌 컬럼은 0 반환
                    result.append(0)
            
            return tuple(result)
        finally:
            self.lock.unlock()
    
    def update_table_widget(self, table_widget, stretch=True, header=0):
        """
        저장된 데이터를 테이블 위젯에 표시
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        stretch (bool): 마지막 열을 테이블 너비에 맞게 늘릴지 여부
        header (int): 사용할 헤더 세트의 인덱스 (기본값: 0)
        """
        import copy
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        # 락 사용 최소화 - 데이터 스냅샷만 빠르게 복사
        self.lock.lockForRead()
        try:
            if not self.data:
                table_widget.setRowCount(0)
                return
                
            data_copy = copy.deepcopy(self.data)
            if header < 0 or header >= len(self.display_columns):
                header = 0

            columns = self.display_columns[header]
            resize_needed = self._resize
            
            if resize_needed:
                self._resize = False
        finally:
            self.lock.unlock()
        
        # UI 업데이트는 락 없이 수행
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        
        try:
            # 테이블 크기 확인 및 조정
            if table_widget.rowCount() != len(data_copy) or table_widget.columnCount() != len(columns):
                resize_needed = True
                
            if resize_needed:
                table_widget.setRowCount(len(data_copy))
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
            
            # 데이터 표시
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column])
            
            # 테이블 크기 조정
            if resize_needed:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                
                if stretch:
                    table_widget.horizontalHeader().setStretchLastSection(stretch)
        except Exception as e:
            import logging
            logging.error(f'update_table_widget 오류: {type(e).__name__} - {e}', exc_info=True)
        finally:
            table_widget.setUpdatesEnabled(True)
            table_widget.setSortingEnabled(True)
            
    def _set_table_cell(self, table_widget, row, col, column, value):
        """테이블의 특정 셀에 값 설정"""
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        original_value = str(value)
        
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value).rstrip() # 빈 줄 제거
            # "스크립트" 컬럼의 경우 마지막 줄만 표시
            if column in ['스크립트', '설명'] and '\n' in display_value:
                lines = display_value.split('\n')
                # 마지막 줄이 비어있으면 그 전 줄을 사용
                last_line = lines[-1] if lines[-1].strip() else lines[-2] if len(lines) > 1 else lines[0]
                display_value = last_line[:35]
                #display_value = last_line if last_line.strip() else "(빈 줄)"
                
        # 기존 아이템 재사용
        existing_item = table_widget.item(row, col)
        if existing_item:
            # 값이 같으면 업데이트 필요 없음
            if existing_item.text() == display_value:
                return
            existing_item.setText(display_value)
            existing_item.setData(Qt.UserRole, original_value)
            cell_item = existing_item
        else:
            cell_item = QTableWidgetItem(display_value)
            cell_item.setData(Qt.UserRole, original_value)
            table_widget.setItem(row, col, cell_item)
        
        # 정렬 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(self.align_right)
        else:
            cell_item.setTextAlignment(self.align_left)
        
        # 손익 관련 컬럼 색상 설정
        if column in self.profit_columns:
            if isinstance(value, (int, float)):
                if value < 0:
                    cell_item.setForeground(self.color_negative)  # 음수는 청색
                elif value > 0:
                    cell_item.setForeground(self.color_positive)  # 양수는 적색
                else:
                    cell_item.setForeground(self.color_zero)      # 0은 검정색

# 표준 threading.RLock 사용
class TableManager:
    """
    # 1. 단일 키 사용 (기존 방식)
    config = {
        '키': '종목코드',
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 2. 복합 키 사용
    config = {
        '키': ['종목코드', '매수일자'],  # 두 컬럼을 합쳐서 키로 사용
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '매수일자', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 3. 키 없는 모드
    config = {
        '키': None,  # 키 사용 안 함
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)

    # 4. 중복 키 허용
    config = {
        '키': '종목코드',
        '중복키': True,  # 같은 종목코드가 여러 행에 있을 수 있음
        '정수': ['수량', '매수금액'],
        '실수': ['현재가', '평가손익'],
        '컬럼': ['종목코드', '종목명', '수량', '매수금액', '현재가', '평가손익']
    }
    table = TableManager(config)
    """

    def __init__(self, config):
        """
        쓰레드 안전한 데이터 관리 클래스 초기화
        
        Parameters:
        config (dict): 설정 정보 딕셔너리
            - '키': 고유 키로 사용할 컬럼명 또는 컬럼명 리스트 (복합 키), None이면 키 없는 모드로 동작
            - '중복키': True면 동일 키 값을 갖는 여러 행 허용 (기본값: False)
            - '정수': 정수형으로 변환할 컬럼 리스트
            - '실수': 실수형으로 변환할 컬럼 리스트
            - '컬럼': 전체 컬럼 리스트
            - '헤더': 화면용 컬럼 리스트 또는 리스트의 리스트 (여러 헤더 셋)
        """
        self.data = []
        self.data_dict = {}  # 키 기반 검색을 위한 딕셔너리
        
        # 표준 threading.RLock 사용 (재진입 가능한 락)
        self.lock = threading.RLock()
        
        # 설정 정보 저장
        self.key_columns = config.get('키', None)
        
        # key_columns가 문자열이면 리스트로 변환
        if isinstance(self.key_columns, str):
            self.key_columns = [self.key_columns]
            
        # 키 중복 허용 여부
        self.allow_duplicate_keys = config.get('중복키', False)
        
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('확장', config.get('컬럼', []))
        
        # 헤더 설정 - 리스트의 리스트로 처리
        header_config = config.get('헤더', [])
        if header_config and not isinstance(header_config[0], list):
            # 단일 리스트인 경우, 리스트의 리스트로 변환
            self.display_columns = [header_config]
        else:
            self.display_columns = header_config
            
        # 헤더가 없는 경우 all_columns 사용
        if not self.display_columns:
            self.display_columns = [self.all_columns]

        # 키가 있는 경우 키 컬럼이 all_columns에 있는지 확인
        if self.key_columns:
            for key_col in self.key_columns:
                if key_col not in self.all_columns:
                    raise ValueError(f"키 컬럼 '{key_col}'이 '컬럼' 리스트에 없습니다.")
        
        if not self.all_columns:
            raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
        
        # 자주 사용하는 상수와 객체 미리 정의
        # 정렬 상수
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor
        
        self.align_right = Qt.AlignRight | Qt.AlignVCenter
        self.align_left = Qt.AlignLeft | Qt.AlignVCenter
        self.align_center = Qt.AlignCenter
        
        # 색상 객체
        self.color_positive = QColor(255, 0, 0)  # 적색 (손익 양수)
        self.color_negative = QColor(0, 0, 255)  # 청색 (손익 음수)
        self.color_zero = QColor(0, 0, 0)        # 검정색 (손익 0)
        
        # 손익 관련 컬럼
        self.profit_columns = ["평가손익", "수익률(%)", "당일매도손익", "손익율", "손익금액", "수익률", "등락율"]

        # 리사이즈
        self._resize = True
        
        # 키 없는 모드인지 여부
        self.no_key_mode = self.key_columns is None
    
    def _get_key_for_item(self, item):
        """
        항목에서 키 값을 추출
        
        Parameters:
        item (dict): 키 값을 추출할 항목
        
        Returns:
        키 없는 모드면 None, 단일 키면 값, 복합 키면 튜플
        """
        if self.no_key_mode:
            return None
            
        if len(self.key_columns) == 1:
            return item.get(self.key_columns[0])
        else:
            # 복합 키는 튜플로 반환
            return tuple(item.get(key_col) for key_col in self.key_columns)
    
    def _convert_value(self, column, value):
        """
        값을 적절한 타입으로 변환
        
        Parameters:
        column (str): 컬럼명
        value: 변환할 값
        
        Returns:
        변환된 값
        """
        # 기본값 정의
        default_values = {
            'int': 0,
            'float': 0.0,
            'str': ""
        }
        
        # 문자열 처리
        if isinstance(value, str):
            value = value.strip()
            if column not in self.int_columns + self.float_columns:
                return value
            
            # 쉼표가 포함된 숫자 문자열 처리
            if any(c.isdigit() for c in value):
                value = value.replace(',', '')
        
        # None이나 빈 문자열은 기본값으로
        if value is None or value == "":
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                default_values['str']
        
        # 타입별 변환
        try:
            if column in self.int_columns:
                return int(float(value))
            elif column in self.float_columns:
                return float(value)
            else:
                # 불리언 및 기타 타입은 그대로 유지
                return value
        except (ValueError, TypeError):
            # 변환 실패 시 기본값 반환
            return default_values['int'] if column in self.int_columns else \
                default_values['float'] if column in self.float_columns else \
                str(value)
            
    def _process_item(self, item):
        """
        항목의 각 값을 적절한 타입으로 변환
        
        Parameters:
        item (dict): 변환할 항목
        
        Returns:
        dict: 변환된 항목
        """
        processed_item = {}
        # 모든 컬럼을 기본값으로 먼저 초기화
        for column in self.all_columns:
            if column in self.int_columns:
                processed_item[column] = 0
            elif column in self.float_columns:
                processed_item[column] = 0.0
            else:
                processed_item[column] = ""
                
        # 주어진 값으로 업데이트
        for column in self.all_columns:
            if column in item:
                processed_item[column] = self._convert_value(column, item.get(column, ''))
        
        return processed_item

    def get(self, key=None, filter=None, type=None, column=None):
        """
        get() -> [{}]                     # 전체 데이터 사전 리스트 반환
        get(type='df') -> DataFrame       # DataFrame으로 반환
        get(key='key') -> {}              # 'key'로 찾은 행 반환
        get(key=숫자) -> {}               # 인덱스로 행 반환
        get(key=(값1,값2)) -> [{}]        # 복합 키로 찾은 행(들) 반환
        get(filter={}) -> [{}]            # 조건에 맞는 행들 반환
        get(filter={}, column='col') -> []  # 조건에 맞는 행들의 특정 컬럼 값들 리스트 반환
        get(column='col') -> []           # 특정 컬럼 값들 리스트 반환
        get(column=['c1','c2']) -> [{}]   # 지정 컬럼만 포함한 사전 리스트 반환
        get(key='key', column='col') -> 값  # 특정 행의 특정 컬럼 값 반환
        get(key='key', column=['c1','c2']) -> (값1, 값2, ...)  # 특정 행의 여러 컬럼 값 튜플 반환
        """
        with self.lock:
            # 0. 키가 정수형인 경우 (인덱스로 접근)
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    return copy.deepcopy(self.data[key])
                return None
            
            # 1. 특정 키 + 특정 컬럼 조회
            if key is not None and column is not None:
                items = self._find_items_by_key(key)
                if not items:
                    return None
                
                # 키 중복 허용이 아닌 경우 첫 번째 항목만 사용
                item = items[0] if isinstance(items, list) else items
                
                # 컬럼이 리스트인 경우 (여러 컬럼 조회)
                if isinstance(column, (list, tuple)):
                    if len(column) == 1:
                        # 단일 컬럼이면 값만 반환
                        return item.get(column[0])
                    else:
                        # 여러 컬럼이면 튜플로 반환
                        return tuple(item.get(col) for col in column)
                # 컬럼이 문자열인 경우 (단일 컬럼 조회)
                elif isinstance(column, str):
                    return item.get(column)
                return None
            
            # 2. 전체 데이터 + 특정 컬럼 조회
            if column is not None:
                # 컬럼이 리스트인 경우
                if isinstance(column, (list, tuple)):
                    result = []
                    for item in self.data:
                        filtered_item = {col: item.get(col) for col in column if col in item}
                        result.append(filtered_item)
                    return copy.deepcopy(result)
                # 컬럼이 문자열인 경우
                elif isinstance(column, str):
                    # 단일 컬럼이면 값만 추출하여 리스트로 반환
                    return [item.get(column) for item in self.data]
                
            # 3. 특정 키 조회
            if key is not None:
                items = self._find_items_by_key(key)
                if not items: return None

                # 키 중복 허용이면 여러 항목 반환 가능
                if self.allow_duplicate_keys and isinstance(items, list):
                    return copy.deepcopy(items)
                else:
                    # 중복 허용 아니면 첫 번째 항목만 반환
                    return copy.deepcopy(items)
            
            # 4. 필터링 조회
            if filter is not None:
                return self._filter_data(filter)
            
            # 5. 전체 데이터 조회
            data_copy = copy.deepcopy(self.data)
            
            # 6. DataFrame 반환 요청인 경우
            if type == 'df':
                try:
                    import pandas as pd
                    return pd.DataFrame(data_copy)
                except ImportError:
                    raise ImportError("pandas 라이브러리가 필요합니다. 'pip install pandas'로 설치하세요.")
            
            # 기본적으로 리스트 반환
            return data_copy
    
    def _find_items_by_key(self, key):
        """
        키 값으로 항목 찾기
        
        Parameters:
        key: 찾을 키 값
        
        Returns:
        중복 키 허용이면 항목 리스트, 아니면 단일 항목
        """
        if self.no_key_mode:
            return None
        
        if key not in self.data_dict:
            return None
        
        return self.data_dict.get(key)
    
    def _add_to_dict(self, key_value, item):
        """
        딕셔너리에 항목 추가
        
        Parameters:
        key_value: 키 값 (문자열, 숫자 또는 튜플)
        item (dict): 추가할 항목
        """
        if self.allow_duplicate_keys:
            # 중복 키 허용 모드: 리스트로 항목 저장
            if key_value in self.data_dict:
                self.data_dict[key_value].append(item)
            else:
                self.data_dict[key_value] = [item]
        else:
            # 중복 키 비허용 모드: 단일 항목 저장
            self.data_dict[key_value] = item

    def set(self, key=None, filter=None, data=None):
        """
        set(key='key', data={}) -> bool   # 특정 키 행 추가/업데이트
        set(key=(값1,값2), data={}) -> bool # 복합 키 행 추가/업데이트
        set(filter={}, data={}) -> bool   # 조건 만족 행들 업데이트
        set(data={}) -> bool              # 모든 행의 지정 컬럼 업데이트
        set(data=[{}, {}]) -> bool        # 전체 데이터 대체
        """
        if data is None:
            return False
                
        # 리스트 타입 체크 (데이터 대체 모드)
        if isinstance(data, list):
            with self.lock:
                # 키 모드일 때 키 필드 검증
                if not self.no_key_mode:
                    for item in data:
                        for key_col in self.key_columns:
                            if key_col not in item:
                                raise ValueError(f"모든 항목에 키 컬럼('{key_col}')이 필요합니다.")
                
                # 데이터 대체
                self.data = []
                self.data_dict = {}
                for item in data:
                    processed_item = self._process_item(item)
                    self.data.append(processed_item)
                
                    # 키 모드일 때 딕셔너리에 추가
                    if not self.no_key_mode:
                        key_value = self._get_key_for_item(processed_item)
                        self._add_to_dict(key_value, processed_item)
                
                return True
            
        # 딕셔너리 타입 체크 (업데이트 모드)
        if isinstance(data, dict):
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data: return False
            
            with self.lock:
                # 1. 특정 키 업데이트/추가
                if key is not None:
                    return self._set_item_by_key(key, valid_data)
                
                # 2. 필터링된 항목 업데이트
                if filter is not None:
                    return self._update_filtered_items(filter, valid_data)
                
                # 3. 전체 항목 업데이트
                return self._update_all_items(valid_data)
                
        return False
    
    def _set_item_by_key(self, key, data):
        """
        키로 항목 추가/업데이트
        
        Parameters:
        key: 키 값 (단일 값 또는 복합 키 튜플)
        data (dict): 업데이트할 데이터
        
        Returns:
        bool: 성공 여부
        """
        if self.no_key_mode:
            # 키 없는 모드에서는 인덱스로 처리
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    for column, value in data.items():
                        if column in self.all_columns:
                            self.data[key][column] = self._convert_value(column, value)
                    return True
            return False
        
        # 기존 항목 찾기
        items = self._find_items_by_key(key)
        
        # 중복 허용 모드일 때
        if self.allow_duplicate_keys:
            if items:
                # 첫 번째 항목만 업데이트
                for column, value in data.items():
                    if column in self.all_columns and column not in self.key_columns:
                        items[0][column] = self._convert_value(column, value)
                return True
        elif items:
            # 중복 비허용 모드일 때 항목 업데이트
            for column, value in data.items():
                if column in self.all_columns and column not in self.key_columns:
                    items[column] = self._convert_value(column, value)
            return True
        
        # 신규 항목 추가
        # 모든 컬럼 기본값으로 초기화
        item = {}
        for column in self.all_columns:
            # 기본값 설정
            if column in self.int_columns:
                item[column] = 0
            elif column in self.float_columns:
                item[column] = 0.0
            else:
                item[column] = ""
        
        # 키 컬럼 설정
        if isinstance(key, tuple) and len(key) == len(self.key_columns):
            # 복합 키 처리
            for i, key_col in enumerate(self.key_columns):
                item[key_col] = key[i]
        elif len(self.key_columns) == 1:
            # 단일 키 처리
            item[self.key_columns[0]] = key
        
        # 데이터 채우기
        for column, value in data.items():
            if column in self.all_columns:
                item[column] = self._convert_value(column, value)
        
        # 데이터 추가
        self.data.append(item)
        self._add_to_dict(key, item)
        self._resize = True
        return True
    
    def _update_filtered_items(self, filter, data):
        """필터링된 항목 업데이트"""
        updated = False
        for item in self.data:
            if self._match_conditions(item, filter):
                # 키 컬럼은 업데이트하지 않음
                for column, value in data.items():
                    if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                        item[column] = self._convert_value(column, value)
                updated = True
        return updated
    
    def _update_all_items(self, data):
        """모든 항목 업데이트"""
        if not self.data:
            return False
        
        for item in self.data:
            for column, value in data.items():
                if column in self.all_columns and (self.no_key_mode or column not in self.key_columns):
                    item[column] = self._convert_value(column, value)
        return True
    
    def delete(self, key=None, filter=None):
        """
        delete() -> bool                  # 모든 데이터 삭제
        delete(key='key') -> bool         # 특정 키 행 삭제
        delete(key=(값1,값2)) -> bool     # 복합 키 행 삭제
        delete(filter={}) -> bool         # 조건 만족 행들 삭제
        """
        with self.lock:
            # 1. 특정 키 삭제
            if key is not None:
                # 키 없는 모드에서는 인덱스로 처리
                if self.no_key_mode:
                    if isinstance(key, int) and 0 <= key < len(self.data):
                        del self.data[key]
                        self._resize = True
                        return True
                    return False
                    
                # 키 모드에서는 키로 처리
                items = self._find_items_by_key(key)
                if not items:
                    return False
                
                if self.allow_duplicate_keys:
                    # 중복 키 허용 모드: 모든 항목 삭제
                    for item in items[:]:  # 복사본으로 반복
                        if item in self.data:
                            self.data.remove(item)
                    # 딕셔너리에서 키 삭제
                    self.data_dict.pop(key, None)
                else:
                    # 중복 키 비허용 모드: 단일 항목 삭제
                    if items in self.data:
                        self.data.remove(items)
                    self.data_dict.pop(key, None)
                    
                self._resize = True
                return True
            
            # 2. 필터링된 항목 삭제
            if filter is not None:
                items_to_delete = [item for item in self.data if self._match_conditions(item, filter)]
                if not items_to_delete:
                    return False
                
                for item in items_to_delete:
                    # 키 모드일 때 딕셔너리에서도 삭제
                    if not self.no_key_mode:
                        key_val = self._get_key_for_item(item)
                        
                        if self.allow_duplicate_keys:
                            # 중복 키 허용 모드: 리스트에서 항목 제거
                            if key_val in self.data_dict:
                                items_list = self.data_dict[key_val]
                                if item in items_list:
                                    items_list.remove(item)
                                # 리스트가 비었으면 키 삭제
                                if not items_list:
                                    self.data_dict.pop(key_val, None)
                        else:
                            # 중복 키 비허용 모드: 키 삭제
                            self.data_dict.pop(key_val, None)
                
                    if item in self.data:
                        self.data.remove(item)
                    
                    if items_to_delete:
                        self._resize = True
                
                return bool(items_to_delete)
            
            # 3. 전체 데이터 삭제
            self.data = []
            self.data_dict = {}
            self._resize = True
            return True
    
    def _filter_data(self, conditions):
        """
        # conditions : {컬럼: 값} 컬럼과 값 비교
        {'col': 값}
        # conditions : {컬럼: (연산자, 값)}
        {'col': ('>', 값)}                # col > 값
        {'col': ('<', 값)}                # col < 값
        {'col': ('>=', 값)}               # col >= 값
        {'col': ('<=', 값)}               # col <= 값
        {'col': ('==', 값)}               # col == 값
        {'col': ('!=', 값)}               # col != 값
        {'col': ('>', '@other_col')}      # col > other_col (컬럼 간 비교)
        """
        result = []
        for row in self.data:
            if self._match_conditions(row, conditions):
                result.append(copy.deepcopy(row))
        return result
    
    def _match_conditions(self, row, conditions):
        """항목이 조건에 맞는지 확인"""
        for column, value in conditions.items():
            if column not in row:
                return False
                
            item_value = row[column]
            
            # 문자열인 경우 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 컬럼 간 비교인 경우 ('컬럼' 또는 '@컬럼')
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                # '@'로 시작하는 문자열은 다른 컬럼을 참조
                if isinstance(compare_value, str) and compare_value.startswith('@'):
                    other_column = compare_value[1:]  # '@' 제거
                    if other_column not in row:
                        return False
                    other_value = row[other_column]
                    if not self._compare_values(item_value, op, other_value):
                        return False
                # 일반 비교값
                else:
                    if not self._compare_values(item_value, op, compare_value):
                        return False
            # 그 외의 경우 정확히 일치하는지 확인
            elif item_value != value:
                return False
                
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """숫자형 값 비교 연산"""
        ops = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y,
            '!=': lambda x, y: x != y
        }
        
        if operator in ops:
            try:
                return ops[operator](item_value, compare_value)
            except (TypeError, ValueError):
                return False
        return False

    def len(self, filter=None):
        """
        len() -> int                      # 전체 행 수 반환
        len(filter={}) -> int             # 조건 만족 행 수 반환
        """
        with self.lock:
            if filter is not None:
                return len(self._filter_data(filter))
            return len(self.data)
    
    def in_key(self, key):
        """
        in_key('key') -> bool             # 키 존재 여부
        in_key((값1, 값2)) -> bool        # 복합 키 존재 여부
        """
        # 키 없는 모드에서는 항상 False
        if self.no_key_mode: return False
        with self.lock: return key in self.data_dict
    
    def in_key_set(self, key, data):
        """
        원자적 업데이트(키가 존재하는 경우 데이터 업데이트)
        """
        # 키 없는 모드에서는 항상 False
        if self.no_key_mode: return False
            
        with self.lock:
            if key not in self.data_dict: return False
            # 빈 데이터 필드 제거
            valid_data = {k: v for k, v in data.items() if k in self.all_columns}
            if not valid_data: return False
            
            return self._set_item_by_key(key, valid_data)
            
    def in_column(self, column, value):
        """
        in_column('col', 값) -> bool      # 컬럼에 값 존재 여부
        """
        with self.lock:
            if column not in self.all_columns:
                return False
            
            # 타입 변환
            converted_value = self._convert_value(column, value)
            
            for item in self.data:
                if item.get(column) == converted_value:
                    return True
            return False
    
    def sum(self, column=None, filter=None):
        """
        sum(column=['c1', 'c2']) -> (합1, 합2, ...)  # 지정 컬럼 합계 튜플 반환
        sum(column=[], filter={}) -> (합1, 합2, ...)  # 조건 만족 행들의 합계 반환
        """
        with self.lock:
            if not column:
                return ()
            
            # 합계 계산할 데이터 선택
            data_to_sum = self.data
            if filter is not None:
                data_to_sum = self._filter_data(filter)
            
            # 각 컬럼별 합계 계산
            result = []
            if isinstance(column, str):
                column = [column]
            for col in column:
                if col in self.int_columns or col in self.float_columns:
                    total = sum(item.get(col, 0) for item in data_to_sum)
                    result.append(total)
                else:
                    # 숫자형이 아닌 컬럼은 0 반환
                    result.append(0)
            
            return tuple(result)
    
    def update_table_widget(self, table_widget, stretch=True, header=0):
        """
        저장된 데이터를 테이블 위젯에 표시
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        stretch (bool): 마지막 열을 테이블 너비에 맞게 늘릴지 여부
        header (int): 사용할 헤더 세트의 인덱스 (기본값: 0)
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        # 락 사용 최소화 - 데이터 스냅샷만 빠르게 복사
        with self.lock:
            if not self.data:
                table_widget.setRowCount(0)
                return
                
            data_copy = copy.deepcopy(self.data)
            if header < 0 or header >= len(self.display_columns):
                header = 0

            columns = self.display_columns[header]
            resize_needed = self._resize
            
            if resize_needed:
                self._resize = False
        
        # UI 업데이트는 락 없이 수행
        table_widget.setUpdatesEnabled(False)
        table_widget.setSortingEnabled(False)
        
        try:
            # 테이블 크기 확인 및 조정
            if table_widget.rowCount() != len(data_copy) or table_widget.columnCount() != len(columns):
                resize_needed = True
                
            if resize_needed:
                table_widget.setRowCount(len(data_copy))
                table_widget.setColumnCount(len(columns))
                table_widget.setHorizontalHeaderLabels(columns)
            
            # 데이터 표시
            for row, item in enumerate(data_copy):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column])
            
            # 테이블 크기 조정
            if resize_needed:
                table_widget.resizeColumnsToContents()
                table_widget.resizeRowsToContents()
                
                if stretch:
                    table_widget.horizontalHeader().setStretchLastSection(stretch)
        except Exception as e:
            import logging
            logging.error(f'update_table_widget 오류: {type(e).__name__} - {e}', exc_info=True)
        finally:
            table_widget.setUpdatesEnabled(True)
            table_widget.setSortingEnabled(True)
            
    def _set_table_cell(self, table_widget, row, col, column, value):
        """테이블의 특정 셀에 값 설정"""
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        
        original_value = str(value)
        
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value).rstrip() # 빈 줄 제거
            # "스크립트" 컬럼의 경우 마지막 줄만 표시
            if column in ['스크립트', '설명'] and '\n' in display_value:
                lines = display_value.split('\n')
                # 마지막 줄이 비어있으면 그 전 줄을 사용
                last_line = lines[-1] if lines[-1].strip() else lines[-2] if len(lines) > 1 else lines[0]
                display_value = last_line[:35]
                #display_value = last_line if last_line.strip() else "(빈 줄)"
                
        # 기존 아이템 재사용
        existing_item = table_widget.item(row, col)
        if existing_item:
            # 값이 같으면 업데이트 필요 없음
            if existing_item.text() == display_value:
                return
            existing_item.setText(display_value)
            existing_item.setData(Qt.UserRole, original_value)
            cell_item = existing_item
        else:
            cell_item = QTableWidgetItem(display_value)
            cell_item.setData(Qt.UserRole, original_value)
            table_widget.setItem(row, col, cell_item)
        
        # 정렬 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(self.align_right)
        else:
            cell_item.setTextAlignment(self.align_left)
        
        # 손익 관련 컬럼 색상 설정
        if column in self.profit_columns:
            if isinstance(value, (int, float)):
                if value < 0:
                    cell_item.setForeground(self.color_negative)  # 음수는 청색
                elif value > 0:
                    cell_item.setForeground(self.color_positive)  # 양수는 적색
                else:
                    cell_item.setForeground(self.color_zero)      # 0은 검정색

def set_tables():
    gm.잔고합산 = TableManager(tbl.hd잔고합산)
    gm.잔고목록 = TableManager(tbl.hd잔고목록)
    gm.매수조건목록 = TableManager(tbl.hd조건목록)
    gm.매도조건목록 = TableManager(tbl.hd조건목록)
    gm.손익목록 = TableManager(tbl.hd손익목록)
    gm.예수금 = TableManager(tbl.hd예수금)
    gm.일지합산 = TableManager(tbl.hd일지합산)
    gm.일지목록 = TableManager(tbl.hd일지목록)
    gm.체결목록 = TableManager(tbl.hd체결목록)
    gm.전략정의 = TableManager(tbl.hd전략정의)
    gm.주문목록 = TableManager(tbl.hd주문목록)
    gm.매매목록 = TableManager(tbl.hd매매목록)
    gm.스크립트 = TableManager(tbl.hd스크립트)
    gm.차트자료 = TableManager(tbl.hd차트자료)
    gm.당일종목 = TableManager(tbl.hd당일종목)
    gm.수동종목 = TableManager(tbl.hd수동종목)

