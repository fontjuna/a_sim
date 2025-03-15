from public import get_path, gm, dc, Work, save_json, load_json
from classes import DataTables as dt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QStatusBar, QLabel, QWidget, QTabWidget, QPushButton, QLineEdit, QCheckBox
from PyQt5.QtWidgets import QTableWidgetItem, QHeaderView, QComboBox, QSpinBox, QDoubleSpinBox, QRadioButton, QTimeEdit, QComboBox
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtCore import QCoreApplication, QEvent, QTimer, QTime, QDate, Qt
from PyQt5 import uic
from datetime import datetime, timedelta
import multiprocessing as mp
import logging
import os

form_class = uic.loadUiType(os.path.join(get_path(dc.fp.RESOURCE_PATH), "aaa.ui"))[0]

class GUI(QMainWindow, form_class):
    lbl0, lbl1, lbl2, lbl3, lbl4 = None, None, None, None, None
    lbl3_update_time = datetime.now()
    def __init__(self):
        super().__init__()
        self.name = 'gui'
        self.queue = mp.Queue()
        self.que = mp.Queue()
        self.setupUi(self)
        self.refresh_data_timer = QTimer()
        self.refresh_data_timer.timeout.connect(self.gui_refresh_data)

    def gui_show(self):
        self.show()

    def gui_close(self):
        close_event = QEvent(QEvent.Close)
        QCoreApplication.sendEvent(self, close_event)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, '종료 확인', '종료하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            logging.debug(f'{self.name} stopping...')
            event.accept()
            self.refresh_data_timer.stop()
            gm.pro.main.cleanup()
        else:
            event.ignore()

    def init(self):
        logging.debug(f'{self.name} init')
        self.set_widgets()
        self.gui_fx채움_계좌콤보()
        def delayed_init():
            self.gui_fx채움_조건콤보()
            self.gui_fx채움_전략정의()
            self.gui_fx전시_전략정의()
            self.set_widget_events()
            if gm.config.log_level == logging.DEBUG:
                self.rbDebug.setChecked(True)
                self.rbInfo.setChecked(False)
            else:
                self.rbInfo.setChecked(True)
                self.rbDebug.setChecked(False)
            self.refresh_data_timer.start(100)
        delayed_init()
        success, gm.json_config =   load_json(os.path.join(get_path(dc.fp.CONFIG_PATH), dc.fp.CONFIG_FILE), {'level': logging.INFO})
        logging.getLogger().setLevel(gm.json_config['level'])
        self.rbDebug.setChecked(gm.json_config['level'] == logging.DEBUG)
        #self.rbInfo.setChecked(gm.json_config['level'] == logging.INFO)
        #QTimer.singleShot(500, delayed_init)

    def gui_fx갱신_계좌정보(self):
        try:
            row = gm.잔고합산.get(key=1)
            if row is None: row = {}
            self.lblBuy.setText(f"{int(row.get('총매입금액', 0)):,}")
            self.lblAmount.setText(f"{int(row.get('총평가금액', 0)):,}")
            self.lblAssets.setText(f"{int(row.get('추정예탁자산', 0)):,}")
            self.gui_set_color(self.lblProfit, int(row.get('총평가손익금액', 0)))
            self.gui_set_color(self.lblFrofitRate, float(row.get('총수익률(%)', 0.0)))
            self.tblBalanceHeld.clearContents()
            gm.잔고목록.update_table_widget(self.tblBalanceHeld, stretch=False)
        except Exception as e:
            logging.error(f'계좌정보 갱신 오류: {type(e).__name__} - {e}', exc_info=True)

    # 화면 갱신 ---------------------------------------------------------------------------------------------
    def gui_refresh_data(self):
        try:
            if not self.queue.empty(): # bus 역할 함
                work = self.queue.get()
                if hasattr(self, work.order):
                    getattr(self, work.order)(**work.job)
            self.gui_update_display()
            self.gui_fx갱신_계좌정보()
            #self.gui_fx갱신_조건정보()
            #self.gui_fx갱신_주문정보()


        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_set_color(self, label, value):
        try:
            if isinstance(value, float):
                label.setText(f"{value:.2f}")
            else:
                label.setText(f"{value:,}")

            if value > 0:
                label.setStyleSheet("color: red;background-color: #F9F9F9;")
            elif value < 0:
                label.setStyleSheet("color: blue;background-color: #F9F9F9;")
            else:
                label.setStyleSheet("color: black;background-color: #F9F9F9;")
        except Exception as e:
            logging.error(f'색상 설정 오류: {type(e).__name__} - {e}', exc_info=True)

    # 화면 설정 ---------------------------------------------------------------------------------------------
    def set_widgets(self):
        logging.debug('')
        try:
            self.setWindowTitle("리베라니모 키움증권 자동매매 프로그램 - AAA v2025.0313")
            self.setWindowIcon(QIcon(os.path.join(get_path(dc.fp.RESOURCE_PATH), "aaa.ico")))

            self.btnSimulation_start.setEnabled(True)
            self.btnSimulation_stop.setEnabled(False)

            today = QDate.currentDate()
            min_date = today.addMonths(-2)

            self.dtDaily.setMinimumDate(min_date)
            self.dtDaily.setMaximumDate(today)
            self.dtDaily.setCalendarPopup(True)
            self.dtDaily.setDate(today)

            self.dtConclusion.setMaximumDate(today)
            self.dtConclusion.setCalendarPopup(True)
            self.dtConclusion.setDate(today)

            statusBar = QStatusBar()
            self.setStatusBar(statusBar)
            self.lbl0 = QLabel(" "*5)
            self.lbl1 = QLabel("2024-11-09 15:30:00")
            self.lbl2 = QLabel("끊어짐")
            self.lbl3 = QLabel("상세 메세지 처리 ......")
            self.lbl4 = QLabel("장 종료")
            statusBar.addWidget(self.lbl0)
            statusBar.addWidget(self.lbl1)
            statusBar.addWidget(self.lbl2)
            statusBar.addWidget(self.lbl3)
            statusBar.addPermanentWidget(self.lbl4)

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def set_widget_events(self):
        logging.debug('')
        try:
            self.btnExit.clicked.connect(self.gui_close)                                # 종료
            self.rbDebug.toggled.connect(lambda: self.gui_log_level_set('DEBUG', self.rbDebug.isChecked()))
            self.rbInfo.toggled.connect(lambda: self.gui_log_level_set('INFO', self.rbInfo.isChecked()))

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_log_level_set(self, key, value):
        if key == 'DEBUG' and value == True:
            level = logging.DEBUG
        else:
            level = logging.INFO
        gm.json_config['level'] = level
        logging.getLogger().setLevel(level)
        #gm.aaa.put('dbm', Work('set_log_level', {'level': level}))
        save_json(os.path.join(get_path(dc.fp.CONFIG_PATH), dc.fp.CONFIG_FILE), gm.json_config)

        logging.info(f'로깅 설정 변경: {key} = {value}')

    def gui_fx채움_계좌콤보(self):
        try:
            self.cbAccounts.clear()
            self.cbAccounts.addItems([account for account in gm.gui.list계좌콤보 if account.strip()])
            self.cbAccounts.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'계좌콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_조건콤보(self):
        try:
            self.cbCondition.clear()
            self.cbCondition.addItem(dc.const.NON_STRATEGY)  # 선택없음 추가
            self.cbCondition.addItems([strategy for strategy in gm.gui.list전략콤보 if strategy.strip()])
            self.cbCondition.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'조건콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_전략정의(self):
        try:
            self.cbTabStrategy.clear()
            self.cbTabStrategy.addItems([name for name in gm.전략정의.get(column='전략명칭') if name.strip()])
            self.cbTabStrategy.setCurrentIndex(0)
            gm.전략정의.update_table_widget(self.tblStrategy)
        except Exception as e:
            logging.error(f'전략정의 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx전시_전략정의(self):
        """전략설정 위젯에 표시"""
        try:
            for key, widget_name in dc.const.WIDGET_MAP.items():
                widget = self.findChild(QWidget, widget_name)
                value = gm.strategy_row.get(key, '')

                if widget_name.startswith('spb'):
                    widget.setValue(value)
                elif widget_name.startswith('ted'):
                    widget.setTime(QTime.fromString(str(value), "HH:mm"))
                elif widget_name.startswith('rb'):
                    widget.setChecked(value)
                elif widget_name.startswith('cb'):
                    widget.setCurrentText(value)
                elif widget_name.startswith('chk'):
                    widget.setChecked(value)
                elif widget_name.startswith('dsb'):
                    widget.setValue(float(value))
                elif widget_name.startswith('led'):
                    widget.setText(str(value))

        except Exception as e:
            logging.error(f'주문설정 표시 오류: {type(e).__name__} - {e}', exc_info=True)

    # 상태 표시 -------------------------------------------------------------------------------------
    def gui_update_display(self):
        try:
            # 기본 상태바 업데이트
            now = datetime.now()
            if now > self.lbl3_update_time + timedelta(seconds=60): self.lbl3.setText('')
            self.lbl1.setText(now.strftime("%Y-%m-%d %H:%M:%S"))
            self.lbl2.setText('연결됨' if gm.pro.api.connected else '끊어짐')
            self.lbl2.setStyleSheet("color: green;" if gm.pro.api.connected else "color: red;")
            #self.lbl4.setText(gm.pro.api.com_market_status())

            # 큐 메시지 처리
            while not self.que.empty():
                data = self.que.get()
                if data.order == '주문내용':
                    self.gui_fx게시_주문내용(data.job['msg'])
                elif data.order == '검색내용':
                    self.gui_fx게시_검색내용(data.job['msg'])
                elif data.order == '상태바':
                    self.lbl3.setText(data.job['msg'])
                    self.lbl3_update_time = now

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx게시_주문내용(self, msg):
        current_time = datetime.now().strftime("%H:%M:%S")
        self.txtOrder.append(f"[{current_time}] {msg}")
        self.txtOrder.moveCursor(QTextCursor.End)

    def gui_fx게시_검색내용(self, msg):
        current_time = datetime.now().strftime("%H:%M:%S")
        self.txtCondition.append(f"[{current_time}] {msg}")
        self.txtCondition.moveCursor(QTextCursor.End)

