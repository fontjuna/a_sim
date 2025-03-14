import sys
import threading
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class DataManager:
    def __init__(self, config):
        """
        쓰레드 안전한 데이터 관리 클래스 초기화
        
        Parameters:
        config (dict): 설정 정보 딕셔너리
            - '키': 고유 키로 사용할 컬럼명
            - '정수': 정수형으로 변환할 컬럼 리스트
            - '실수': 실수형으로 변환할 컬럼 리스트
            - '컬럼': 전체 컬럼 리스트
            - '헤더': 화면용 컬럼 리스트
        """
        self.data = []
        self.lock = threading.RLock()
        
        # 설정 정보 저장
        self.key_column = config.get('키', '')
        self.int_columns = config.get('정수', [])
        self.float_columns = config.get('실수', [])
        self.all_columns = config.get('컬럼', [])
        self.display_columns = config.get('헤더', [])
        
        if not self.key_column:
            raise ValueError("'키' 컬럼을 지정해야 합니다.")
        
        if not self.all_columns:
            raise ValueError("'컬럼' 리스트를 지정해야 합니다.")
    
    def _convert_value(self, column, value):
        """
        값을 적절한 타입으로 변환
        
        Parameters:
        column (str): 컬럼명
        value: 변환할 값
        
        Returns:
        변환된 값
        """
        # 문자열이면 공백 제거
        if isinstance(value, str):
            value = value.strip()
            
            # 쉼표가 포함된 문자열 처리
            if any(c.isdigit() for c in value):
                value = value.replace(',', '')
        
        # None이나 빈 문자열은 기본값으로
        if value is None or value == "":
            if column in self.int_columns:
                return 0
            elif column in self.float_columns:
                return 0.0
            else:
                return ""
        
        # 타입별 변환        
        try:
            if column in self.int_columns:
                return int(float(value))  # float으로 변환 후 int로 변환해 소수점이 있어도 처리
            elif column in self.float_columns:
                return float(value)
            else:
                return str(value)
        except (ValueError, TypeError):
            # 변환 실패 시 기본값 반환
            if column in self.int_columns:
                return 0
            elif column in self.float_columns:
                return 0.0
            else:
                return str(value)
    
    def load_data(self, data_list):
        """
        외부에서 받은 사전 리스트를 로드
        
        Parameters:
        data_list (list): 사전 리스트 데이터
        """
        if not data_list:
            return
        
        with self.lock:
            self.data = [self._process_item(item) for item in data_list]
    
    def _process_item(self, item):
        """
        항목의 각 값을 적절한 타입으로 변환
        
        Parameters:
        item (dict): 변환할 항목
        
        Returns:
        dict: 변환된 항목
        """
        processed_item = {}
        for column in self.all_columns:
            if column in item:
                processed_item[column] = self._convert_value(column, item.get(column, ''))
        return processed_item
    
    def display_data_in_table(self, table_widget, stretch_last_column=True):
        """
        저장된 데이터를 테이블 위젯에 표시
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        stretch_last_column (bool): 마지막 열을 테이블 너비에 맞게 늘릴지 여부
        """
        with self.lock:
            if not self.data:
                table_widget.setRowCount(0)
                return
            
            columns = self.display_columns or self.all_columns
            
            table_widget.setRowCount(len(self.data))
            table_widget.setColumnCount(len(columns))
            table_widget.setHorizontalHeaderLabels(columns)
            
            # 손익 관련 컬럼 식별
            profit_columns = ["손익금액", "손익률"]
            
            for row, item in enumerate(self.data):
                for col, column in enumerate(columns):
                    if column in item:
                        self._set_table_cell(table_widget, row, col, column, item[column], profit_columns)
            
            # 컬럼 너비 조정
            table_widget.resizeColumnsToContents()
            
            # 마지막 컬럼 늘이기 설정
            header = table_widget.horizontalHeader()
            if stretch_last_column and columns:
                header.setStretchLastSection(stretch_last_column)
    
    def _set_table_cell(self, table_widget, row, col, column, value, profit_columns):
        """
        테이블의 특정 셀에 값 설정
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        row (int): 행 인덱스
        col (int): 열 인덱스
        column (str): 컬럼명
        value: 표시할 값
        profit_columns (list): 손익 관련 컬럼 리스트
        """
        # 숫자 형식화
        if column in self.int_columns and isinstance(value, int):
            display_value = f"{value:,}"
        elif column in self.float_columns and isinstance(value, float):
            display_value = f"{value:,.2f}"
        else:
            display_value = str(value)
        
        cell_item = QTableWidgetItem(display_value)
        
        # 정렬 설정
        if column in self.int_columns or column in self.float_columns:
            cell_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else:
            cell_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # 손익 관련 컬럼 색상 설정
        if column in profit_columns:
            if isinstance(value, (int, float)):
                if value < 0:
                    cell_item.setForeground(QColor(0, 0, 255))  # 음수는 청색
                elif value > 0:
                    cell_item.setForeground(QColor(255, 0, 0))  # 양수는 적색
                # 0은 기본 색상(검정)
        
        table_widget.setItem(row, col, cell_item)
    
    def update_cell(self, table_widget, key_value, column, value):
        """
        특정 셀만 업데이트
        
        Parameters:
        table_widget (QTableWidget): 데이터를 표시할 테이블 위젯
        key_value: 행을 식별할 키 값
        column (str): 업데이트할 컬럼명
        value: 새 값
        
        Returns:
        bool: 업데이트 성공 여부
        """
        with self.lock:
            # 해당 키를 가진 행 찾기
            idx = self._find_item_by_key(key_value)
            if idx is None:
                return False
            
            # 컬럼 인덱스 찾기
            columns = self.display_columns or self.all_columns
            try:
                col_idx = columns.index(column)
            except ValueError:
                return False
            
            # 데이터 업데이트 (타입 변환 수행)
            self.data[idx][column] = self._convert_value(column, value)
            
            # 테이블 셀 업데이트
            row_idx = -1
            for i in range(table_widget.rowCount()):
                item = table_widget.item(i, columns.index(self.key_column))
                if item and item.text() == str(key_value):
                    row_idx = i
                    break
            
            if row_idx != -1:
                profit_columns = ["손익금액", "손익률"]
                self._set_table_cell(table_widget, row_idx, col_idx, column, self.data[idx][column], profit_columns)
                return True
                
            return False
    
    def add_item(self, **kwargs):
        """
        데이터에 새 항목 추가
        
        Parameters:
        **kwargs: 키-값 쌍으로 항목 데이터 (예: 종목코드="005930", 종목명="삼성전자")
        
        Returns:
        bool: 추가 성공 여부
        """
        if not kwargs.get(self.key_column):
            return False
        
        with self.lock:
            key_value = kwargs.get(self.key_column)
            if self._find_item_by_key(key_value) is not None:
                return False
            
            # 모든 컬럼에 대해 값 설정 (없는 컬럼은 기본값으로)
            item = {}
            for column in self.all_columns:
                value = kwargs.get(column, '')
                item[column] = self._convert_value(column, value)
                
            self.data.append(item)
            return True
    
    def _find_item_by_key(self, key_value):
        """
        키 값으로 항목의 인덱스 찾기 (내부용)
        
        Parameters:
        key_value: 찾을 항목의 키 값
        
        Returns:
        int or None: 찾은 항목의 인덱스 (찾지 못한 경우 None)
        """
        for i, item in enumerate(self.data):
            if item.get(self.key_column) == key_value:
                return i
        return None
    
    def remove_item(self, key_value):
        """
        키 값으로 데이터에서 항목 삭제
        
        Parameters:
        key_value: 삭제할 항목의 키 값
        
        Returns:
        bool: 삭제 성공 여부
        """
        with self.lock:
            idx = self._find_item_by_key(key_value)
            if idx is not None:
                del self.data[idx]
                return True
            return False
    
    def update_item(self, key_value, **kwargs):
        """
        키 값으로 항목을 찾아 데이터 수정
        
        Parameters:
        key_value: 수정할 항목의 키 값
        **kwargs: 수정할 키-값 쌍 (예: 현재가=70000, 보유수량=10)
        
        Returns:
        bool: 수정 성공 여부
        """
        with self.lock:
            idx = self._find_item_by_key(key_value)
            if idx is None:
                return False
            
            for column, value in kwargs.items():
                if column in self.all_columns and column != self.key_column:
                    self.data[idx][column] = self._convert_value(column, value)
            
            return True
    
    def get_item(self, key_value):
        """
        키 값으로 항목 찾기
        
        Parameters:
        key_value: 찾을 항목의 키 값
        
        Returns:
        dict: 찾은 항목 (찾지 못한 경우 None)
        """
        with self.lock:
            idx = self._find_item_by_key(key_value)
            if idx is not None:
                return dict(self.data[idx])  # 복사본 반환
            return None
    
    def get_all_data(self):
        """
        현재 저장된 모든 데이터 가져오기 (복사본)
        
        Returns:
        list: 데이터 복사본 리스트
        """
        with self.lock:
            return [dict(item) for item in self.data]  # 각 항목의 복사본을 포함한 리스트 반환
    
    def clear_data(self):
        """
        데이터 모두 지우기
        """
        with self.lock:
            self.data = []
    
    def filter_data(self, **conditions):
        """
        조건에 맞는 데이터만 필터링
        
        Parameters:
        **conditions: 키-값 쌍으로 필터 조건 (예: 종목명="삼성")
        
        Returns:
        list: 필터링된 데이터 리스트
        """
        with self.lock:
            result = []
            for item in self.data:
                if self._match_conditions(item, conditions):
                    result.append(dict(item))  # 복사본 추가
            return result
    
    def _match_conditions(self, item, conditions):
        """
        항목이 조건에 맞는지 확인
        
        Parameters:
        item (dict): 검사할 항목
        conditions (dict): 검사 조건
        
        Returns:
        bool: 조건 일치 여부
        """
        for column, value in conditions.items():
            if column not in item:
                return False
                
            item_value = item[column]
            
            # 문자열인 경우 포함 여부 확인
            if isinstance(item_value, str) and isinstance(value, str):
                if value not in item_value:
                    return False
            # 숫자형인 경우 대소 비교 지원
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                op, compare_value = value
                if not self._compare_values(item_value, op, compare_value):
                    return False
            # 그 외의 경우 정확히 일치하는지 확인
            elif item_value != value:
                return False
                
        return True
    
    def _compare_values(self, item_value, operator, compare_value):
        """
        숫자형 값 비교 연산
        
        Parameters:
        item_value: 항목 값
        operator (str): 비교 연산자
        compare_value: 비교할 값
        
        Returns:
        bool: 비교 결과
        """
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
    
    def sort_data(self, column, reverse=False):
        """
        특정 컬럼을 기준으로 데이터 정렬
        
        Parameters:
        column (str): 정렬 기준 컬럼명
        reverse (bool): 역순 정렬 여부
        """
        with self.lock:
            if not self.data or column not in self.all_columns:
                return
            
            self.data.sort(key=lambda x: x.get(column, ''), reverse=reverse)


# 사용 예시
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 설정 정보
    config = {
        '키': '종목코드',
        '정수': ['보유수량', '현재가', '매입가', '평가금액', '손익금액'],
        '실수': ['손익률'],
        '컬럼': ['종목코드', '종목명', '현재가', '매입가', '보유수량', '평가금액', '손익금액', '손익률'],
        '헤더': ['종목코드', '종목명', '현재가', '매입가', '보유수량', '평가금액', '손익금액', '손익률']
    }
    
    # 샘플 데이터 (타입 혼합됨)
    sample_data = [
        {"종목코드": "005930", "종목명": "삼성전자", "현재가": "72000", "매입가": "68000", "보유수량": "10", "평가금액": "720000", "손익금액": "40000", "손익률": "5.88"},
        {"종목코드": "035720", "종목명": "카카오", "현재가": "48000", "매입가": "50000", "보유수량": "5", "평가금액": "240000", "손익금액": "-10000", "손익률": "-2.00"},
        {"종목코드": "051910", "종목명": "LG화학", "현재가": "675000", "매입가": "650000", "보유수량": "2", "평가금액": "1350000", "손익금액": "50000", "손익률": "3.85"}
    ]
    
    # 관리 클래스 생성 및 데이터 로드
    manager = DataManager(config)
    manager.load_data(sample_data)
    
    # 메인 윈도우 설정
    main_window = QMainWindow()
    main_window.setWindowTitle("종목 데이터 관리")
    main_window.setGeometry(100, 100, 800, 400)
    
    # 중앙 위젯 설정
    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # 테이블 위젯 생성 및 데이터 표시
    table = QTableWidget()
    layout.addWidget(table)
    manager.display_data_in_table(table)
    
    # 개별 셀 업데이트 예시
    # 삼성전자의 현재가만 업데이트
    manager.update_cell(table, "005930", "현재가", 73000)
    
    # 추가, 수정, 삭제 예시
    manager.add_item(종목코드="000660", 종목명="SK하이닉스", 현재가="123000", 매입가="115000", 보유수량="3", 평가금액="369000", 손익금액="-24000", 손익률="-8.00")
    manager.update_item("005930", 현재가=74000, 평가금액=740000, 손익금액=60000, 손익률=8.82)
    manager.remove_item("035720")
    
    # 전체 테이블 갱신
    manager.display_data_in_table(table)
    
    # 필터링 예시 (고급 비교 연산 지원)
    # 현재가가 100000 이상이고 종목명에 "SK"가 포함된 항목
    filtered_data = manager.filter_data(현재가=('>=', 100000), 종목명="SK")
    print("조건에 맞는 종목:", [item["종목명"] for item in filtered_data])
    
    # 데이터 정렬 및 테이블 갱신
    manager.sort_data("손익률", reverse=True)
    manager.display_data_in_table(table)
    
    main_window.show()
    sys.exit(app.exec_())