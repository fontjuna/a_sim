from public import get_path, gm, dc, Work
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
        self.init()

    def gui_close(self):
        close_event = QEvent(QEvent.Close)
        QCoreApplication.sendEvent(self, close_event)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, '종료 확인', '종료하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            logging.debug(f'{self.name} stopping...')
            event.accept()
            self.refresh_data_timer.stop()
            gm.proc['main'].cleanup()
        else:
            event.ignore()

    def init(self):
        logging.debug(f'{self.name} init')
        self.set_widgets()
        def delayed_init():
            self.set_widget_events()
            if gm.config['log_level'] == logging.DEBUG:
                self.rbDebug.setChecked(True)
                self.rbInfo.setChecked(False)
            else:
                self.rbInfo.setChecked(True)
                self.rbDebug.setChecked(False)
            self.refresh_data_timer.start(100)
        delayed_init()
        #QTimer.singleShot(500, delayed_init)

    # 화면 갱신 ---------------------------------------------------------------------------------------------
    def gui_refresh_data(self):
        try:
            if not self.queue.empty(): # bus 역할 함
                work = self.queue.get()
                if hasattr(self, work.order):
                    getattr(self, work.order)(**work.job)

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    # 화면 설정 ---------------------------------------------------------------------------------------------
    def set_widgets(self):
        logging.debug('')
        try:
            self.setWindowTitle("리베라니모 키움증권 자동매매 프로그램 - AAA v2025.0313")
            self.setWindowIcon(QIcon(os.path.join(get_path(dc.fp.RESOURCE_PATH), "aaa.ico")))

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def set_widget_events(self):
        logging.debug('')
        try:
            self.btnExit.clicked.connect(self.gui_close)                                # 종료

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)
