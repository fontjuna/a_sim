from public import get_path, gm, dc, save_json, load_json, hoga
from ipc_manager import work, answer, send_large_data
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QLabel, QWidget, QTabWidget, QPushButton, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtCore import QCoreApplication, QEvent, QTimer, QTime, QDate, Qt
from PyQt5 import uic
from datetime import datetime, timedelta
from queue import Queue
import logging
import os
import json

form_class = uic.loadUiType(os.path.join(get_path(dc.fp.RESOURCE_PATH), "aaa.ui"))[0]

class GUI(QMainWindow, form_class):
    lbl0, lbl1, lbl2, lbl3, lbl4 = None, None, None, None, None
    lbl3_update_time = datetime.now()
    def __init__(self):
        super().__init__()
        self.name = 'gui'
        self.setupUi(self)
        self.refresh_data_timer = QTimer()
        self.refresh_data_timer.timeout.connect(self.gui_refresh_data)
        self.script_edited = False

        gm.qwork['gui'] = Queue()
        gm.qwork['msg'] = Queue()

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
            gm.main.cleanup()
        else:
            event.ignore()

    def init(self):
        logging.debug(f'{self.name} init')
        self.set_widgets()
        self.gui_fx채움_계좌콤보()
        self.gui_fx채움_조건콤보()
        self.gui_fx채움_스크립트콤보()
        self.gui_fx채움_전략정의()
        self.gui_fx전시_전략정의()
        self.set_widget_events()
        if gm.config.log_level == logging.DEBUG:
            self.rbDebug.setChecked(True)
            self.rbInfo.setChecked(False)
        else:
            self.rbInfo.setChecked(True)
            self.rbDebug.setChecked(False)
        self.refresh_data_timer.start(200)
        success, gm.json_config = load_json(os.path.join(get_path(dc.fp.LOG_PATH), dc.fp.LOG_JSON), dc.log_config)
        logging.getLogger().setLevel(gm.json_config['root']['level'])
        self.rbDebug.setChecked(gm.json_config['root']['level'] == logging.DEBUG)

    # 화면 갱신 ---------------------------------------------------------------------------------------------
    def gui_refresh_data(self):
        try:
            if not gm.qwork['gui'].empty():
                data = gm.qwork['gui'].get()
                getattr(self, data.order)(**data.job)

            self.gui_update_status()
            self.gui_fx갱신_목록테이블()

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    # 화면 설정 ---------------------------------------------------------------------------------------------
    def set_strategy_toggle(self, run=True):
        self.btnStartAll.setEnabled(not run)
        self.btnStopAll.setEnabled(run)

    def set_widgets(self):
        logging.debug('')
        try:
            self.setWindowTitle("리베라니모 키움증권 자동매매 프로그램 - v2025.0404.1122")
            self.setWindowIcon(QIcon(os.path.join(get_path(dc.fp.RESOURCE_PATH), "aaa.ico")))

            today = QDate.currentDate()
            min_date = today.addMonths(-2)

            self.dtDaily.setMinimumDate(min_date)
            self.dtDaily.setMaximumDate(today)
            self.dtDaily.setCalendarPopup(True)
            self.dtDaily.setDate(today)

            self.dtConclusion.setMaximumDate(today)
            self.dtConclusion.setCalendarPopup(True)
            self.dtConclusion.setDate(today)

            self.dtChartDate.setMaximumDate(today)
            self.dtChartDate.setCalendarPopup(True)
            self.dtChartDate.setDate(today)

            self.dtMonitor.setMaximumDate(today)
            self.dtMonitor.setCalendarPopup(True)
            self.dtMonitor.setDate(today)

            self.tblScript.setColumnCount(3)
            self.tblScript.setHorizontalHeaderLabels(['이름', '스크립트', '변수'])
            self.btnScriptSave.setEnabled(False)

            self.tblScriptVar.setColumnCount(2)
            self.tblScriptVar.setHorizontalHeaderLabels(['변수명', '값'])

            self.cbChartTick.addItems(dc.ticks.get('틱봉',[]))
            self.cbChartCode.addItem('005930 삼성전자')

            # 폼 초기화 시
            self.txtScript.setAcceptRichText(False)  # 서식 있는 텍스트 거부            

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
            self.cbAccounts.currentIndexChanged.connect(self.gui_account_changed)       # 계좌 변경 선택
            self.cbCondition.currentIndexChanged.connect(self.gui_strategy_changed)     # 검색식 변경 선택
            self.btnReloadAccount.clicked.connect(self.gui_account_reload)              # 계좌 재로드
            self.cbChartCycle.currentIndexChanged.connect(lambda idx: self.gui_chart_cycle_changed(self.cbChartCycle.itemText(idx))) # 차트 주기 변경 선택

            self.tblStrategy.clicked.connect(lambda x: self.gui_set_strategy(x.row()))  # 전략설정 선택
            self.btnLoadCondition.clicked.connect(self.gui_strategy_reload)             # 검색식 재로드
            self.btnTabLoadStrategy.clicked.connect(self.gui_strategy_load)             # 전략설정 로드
            self.btnConditionBuy.clicked.connect(lambda: self.gui_strategy_get(kind='buy')) # 매수전략 선택
            self.btnConditionSell.clicked.connect(lambda: self.gui_strategy_get(kind='sell'))# 매도전략 선택
            self.btnBuyClear.clicked.connect(lambda: self.gui_strategy_get(clear='buy'))    # 매수전략 클리어
            self.btnSellClear.clicked.connect(lambda: self.gui_strategy_get(clear='sell'))  # 매도전략 클리어
            self.btnStrategySave.clicked.connect(self.gui_strategy_save)                # 전략설정 저장
            self.btnStrategyDelete.clicked.connect(self.gui_strategy_delete)            # 전략설정 삭제

            self.btnRestartAll.clicked.connect(self.gui_strategy_restart)                 # 전략매매 재시작
            self.btnStartAll.clicked.connect(lambda: self.gui_strategy_start(question=True))                   # 전략매매 시작
            self.btnStopAll.clicked.connect(lambda: self.gui_strategy_stop(question=True))                     # 전략매매 중지
            self.btnLoadDaily.clicked.connect(self.gui_daily_load)                      # 매매일지 로드
            self.btnDeposit.clicked.connect(self.gui_deposit_load)                      # 예수금 로드
            self.btnLoadConclusion.clicked.connect(self.gui_conclusion_load)            # 체결목록 로드
            self.btnLoadMonitor.clicked.connect(self.gui_monitor_load)                  # 당일 매매 목록 로드
            self.btnChartLoad.clicked.connect(self.gui_chart_load)                      # 차트 로드
            
            self.rbInfo.toggled.connect(lambda: self.gui_log_level_set('INFO', self.rbInfo.isChecked()))
            self.rbDebug.toggled.connect(lambda: self.gui_log_level_set('DEBUG', self.rbDebug.isChecked()))

            # 수동 주문 / 주문 취소
            self.btnTrOrder.clicked.connect(self.gui_tr_order)                          # 매매 주문 
            self.btnTrCancel.clicked.connect(self.gui_tr_cancel)                        # 매매 취소 
            self.leTrCode.editingFinished.connect(self.gui_tr_code_changed)             # 종목코드 변경
            self.tblBalanceHeld.cellClicked.connect(self.gui_balance_held_select)       # 잔고목록 선택
            self.tblReceiptList.cellClicked.connect(self.gui_receipt_list_select)       # 주문목록 선택

            # 스크립트
            self.tblScript.clicked.connect(lambda x: self.gui_script_select(x.row()))  # 스크립트 선택
            self.btnScriptNew.clicked.connect(self.gui_script_new)
            self.btnScriptDel.clicked.connect(self.gui_script_delete)
            self.btnScriptChk.clicked.connect(self.gui_script_check)
            self.btnScriptSave.clicked.connect(self.gui_script_save)
            self.txtScript.textChanged.connect(lambda: (setattr(self, 'script_edited', True), self.btnScriptSave.setDisabled(True)))
            self.tblScriptVar.clicked.connect(lambda x: self.gui_var_select(x.row()))  # 변수 선택
            self.btnVarDel.clicked.connect(self.gui_var_delete)
            self.btnVarSave.clicked.connect(self.gui_var_save)

            # 전략정의 에서 스크립트
            self.btnScriptBuy.clicked.connect(lambda: self.gui_script_get(kind='buy'))
            self.btnScriptSell.clicked.connect(lambda: self.gui_script_get(kind='sell'))
            self.btnScriptBuyClear.clicked.connect(lambda: self.gui_script_get(clear='buy'))
            self.btnScriptSellClear.clicked.connect(lambda: self.gui_script_get(clear='sell'))

            self.gui_tabs_init()

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    # 전략설정 탭 ----------------------------------------------------------------------------------------
    def gui_tabs_init(self):
        """10개의 전략탭 초기화"""
        try:
            tab_widget = self.findChild(QTabWidget, "tabDeca")
            for i in range(1, 6):
                seq = f'{i:02d}'
                current_tab = tab_widget.widget(i-1)

                btn_get_strategy = current_tab.findChild(QPushButton, f'btnTabGetStrategy_{seq}')
                btn_clear = current_tab.findChild(QPushButton, f'btnTabClear_{seq}')
                btn_save = current_tab.findChild(QPushButton, f'btnTabSave_{seq}')

                btn_clear.clicked.connect(lambda _, tab=seq: self.gui_tabs_clear(tab))
                btn_get_strategy.clicked.connect(lambda _, tab=seq: self.gui_tabs_get(tab))
                btn_save.clicked.connect(lambda _, tab=seq: self.gui_tabs_save(tab))

                chk_run = current_tab.findChild(QCheckBox, f'chkRun_{seq}')
                led_condition = current_tab.findChild(QLineEdit, f'ledTabStrategy_{seq}')
                chk_run.setChecked(gm.전략설정[i]['전략적용'])
                led_condition.setText(gm.전략설정[i]['전략명칭'])

        except Exception as e:
            logging.error(f'전략탭 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_clear(self, seq):
        """10개 전략탭 설정 초기화"""
        try:
            tab = self.findChild(QTabWidget, "tabDeca")
            chk_run = tab.findChild(QCheckBox, f'chkRun_{seq}')
            led_condition = tab.findChild(QLineEdit, f'ledTabStrategy_{seq}')
            chk_run.setChecked(False)
            led_condition.setText('')
        except Exception as e:
            logging.error(f'전략 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_get(self, seq):
        try:
            condition_text = self.cbTabStrategy.currentText()
            led_condition = self.findChild(QLineEdit, f'ledTabStrategy_{seq}')
            led_condition.setText(condition_text)
        except Exception as e:
            logging.error(f'전략 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_save(self, seq):
        try:
            tab = self.findChild(QTabWidget, "tabDeca")
            chk_run = tab.findChild(QCheckBox, f'chkRun_{seq}')
            led_condition = tab.findChild(QLineEdit, f'ledTabStrategy_{seq}')
            전략명칭 = led_condition.text().strip()

            if chk_run.isChecked() and not 전략명칭:
                QMessageBox.warning(None, '경고', '전략명칭이 입력되지 않았습니다.')
                logging.warning(f'전략명칭이 입력되지 않았습니다.')
                return

            if 전략명칭 == dc.const.BASIC_STRATEGY:
                QMessageBox.warning(None, '경고', f'{dc.const.BASIC_STRATEGY}은 사용할 수 없습니다.')
                logging.warning(f'{dc.const.BASIC_STRATEGY}은 사용할 수 없습니다.')
                return

            gm.전략설정[int(seq)] = {
                '전략': f'전략{seq}',
                '전략적용': chk_run.isChecked(),
                '전략명칭': 전략명칭,
            }

            # 전략명칭 중복 검사 - 빈 문자열 제외
            strategy_names = [
                d['전략명칭'].strip()
                for d in gm.전략설정
                if '전략명칭' in d and d['전략명칭'].strip()
            ]
            if len(strategy_names) != len(set(strategy_names)):
                QMessageBox.warning(None, '경고', f'전략명칭 {전략명칭}이 중복되었습니다.')
                logging.warning(f'전략명칭 {전략명칭}이 중복되었습니다.')
                return

            # 매수전략 중복 검사 - 빈 문자열과 None 제외
            buy_strategies = [
                gm.전략정의.get(key=strategy.get('전략명칭', '').strip(), column='매수전략')
                for strategy in gm.전략설정
                if strategy.get('전략명칭', '').strip() and
                   gm.전략정의.get(key=strategy.get('전략명칭', '').strip(), column='매수전략') not in ['', 'None', None]
            ]
            if len(buy_strategies) != len(set(buy_strategies)):
                QMessageBox.warning(None, '경고', f'{전략명칭}의 매수전략이 중복되었습니다.')
                logging.warning(f'{전략명칭}의 매수전략이 중복되었습니다.')
                return

            # 매도전략 중복 검사 - 빈 문자열과 None 제외
            sell_strategies = [
                gm.전략정의.get(key=strategy.get('전략명칭', '').strip(), column='매도전략')
                for strategy in gm.전략설정
                if strategy.get('전략명칭', '').strip() and
                   gm.전략정의.get(key=strategy.get('전략명칭', '').strip(), column='매도전략') not in ['', 'None', None]
            ]
            if len(sell_strategies) != len(set(sell_strategies)):
                QMessageBox.warning(None, '경고', f'{전략명칭}의 매도전략이 중복되었습니다.')
                logging.warning(f'{전략명칭}의 매도전략이 중복되었습니다.')
                return

            gm.admin.json_save_define_sets()
            gm.toast.toast(f'전략{seq} 전략적용={chk_run.isChecked()} 전략명칭={전략명칭} 저장 완료', duration=4000)

        except Exception as e:
           logging.error(f'전략 설정 저장 오류: {type(e).__name__} - {e}', exc_info=True)

    # 전략정의 탭 ----------------------------------------------------------------------------------------
    def gui_set_strategy(self, row_index):
        """전략정의 테이블 행 클릭시"""
        try:
            gm.strategy_row = gm.전략정의.get(key=row_index) # 화면표시 디폴트값 저장
            self.gui_fx전시_전략정의()
        except Exception as e:
            logging.error(f'전략정의 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_strategy_buy(self, key, value):
        if key == '검색식':
            if value == dc.const.NON_STRATEGY:
                QMessageBox.warning(None, '검색식', f'"{value}"을 선택할 수 없습니다.')
                return
            else:
                self.ledBuyCondition.setText(value)
        logging.info(f'매수전략 설정 변경: {key} = {value}')

    def gui_strategy_sell(self, key, value):
        if key == '매도선택':
            self.ledSellCondition.setText(value)
        logging.info(f'전략 설정 변경: {key} = {value}')

    def gui_strategy_load(self):
        logging.debug('메세지 발행: cdn Work(json_load_strategy_defines, {})')
        gm.admin.json_load_define_sets()
        self.gui_fx전시_전략정의()

    def gui_strategy_save(self):
        """현재 위젯값을 dict주문설정에 옮기기"""
        try:
            name = self.ledStrategyName.text().strip()
            if not name:
                QMessageBox.warning(self, '알림', '설정 이름을 입력하세요.')
                return
            
            if self.chkScriptBuy.isChecked():
                if not self.ledScriptBuy.text():
                    QMessageBox.warning(self, '알림', '매수 스크립트를 입력하세요.')
                    return
            if self.chkScriptSell.isChecked():
                if not self.ledScriptSell.text():
                    QMessageBox.warning(self, '알림', '매도 스크립트를 입력하세요.')
                    return
            if self.chkConditionBuy.isChecked():
                if not self.ledConditionBuy.text():
                    QMessageBox.warning(self, '알림', '매수 조건식을 입력하세요.')
                    return
            if self.chkConditionSell.isChecked():
                if not self.ledConditionSell.text():
                    QMessageBox.warning(self, '알림', '매도 조건식을 입력하세요.')
                    return
                
            dict설정 = dc.const.DEFAULT_STRATEGY_SETS
            dict설정['전략명칭'] = name

            for key, widget_name in dc.const.WIDGET_MAP.items():
                widget = self.findChild(QWidget, widget_name)
                if not widget: continue

                if widget_name.startswith('spb'):
                    dict설정[key] = widget.value()
                elif widget_name.startswith('ted'):
                    dict설정[key] = widget.time().toString("HH:mm")
                elif widget_name.startswith('rb'):
                    dict설정[key] = widget.isChecked()
                elif widget_name.startswith('cb'):
                    dict설정[key] = widget.currentText()
                elif widget_name.startswith('chk'):
                    dict설정[key] = widget.isChecked()
                elif widget_name.startswith('dsb'):
                    dict설정[key] = widget.value()
                elif widget_name.startswith('led'):
                    dict설정[key] = widget.text()

            dict설정['남은횟수'] = dict설정['체결횟수']
            gm.전략정의.set(key=name, data=dict설정)
            gm.admin.json_save_strategy_sets()
            self.gui_fx채움_전략정의()
            #logging.debug(f'전략정의 {gm.전략정의.get()}')
            gm.toast.toast(f'주문설정 "{name}"을 저장 했습니다.', duration=4000)
            # return dict주문설정

        except Exception as e:
            logging.error(f'주문설정 저장 오류: {type(e).__name__} - {e}', exc_info=True)
            # return None

    def gui_strategy_delete(self):
        """설정 삭제 버튼 클릭시"""
        try:
            name = self.ledStrategyName.text().strip()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 전략명칭을 확인 하세요.')
                return
            if name == dc.const.BASIC_STRATEGY:
                QMessageBox.warning(self, '알림', f'{dc.const.BASIC_STRATEGY}은 삭제할 수 없습니다.')
                return
            if (any(gm.매수문자열들) or any(gm.매도문자열들)):
                QMessageBox.warning(self, '알림', f'전략매매가 실행중입니다. 중지 후 삭제 하세요.')
                return

            reply = QMessageBox.question(self, '삭제 확인',
                                        f'{name} 설정을 삭제하시겠습니까?',
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 설정 삭제
                result = gm.전략정의.delete(key=name)
                if result:
                    msg = '설정이 삭제되었습니다.'
                    for i in range(1, 11):
                        if gm.전략설정[i]['전략명칭'] == name:
                            gm.전략설정[i]['전략명칭'] = ''
                            gm.전략설정[i]['전략적용'] = False
                            self.gui_tabs_clear(f'{i:02d}')
                            break
                    gm.admin.json_save_strategy_sets()
                    gm.admin.json_save_define_sets()

                else: msg = '설정이 삭제되지 않았습니다.'
                self.gui_fx채움_전략정의()
                QMessageBox.information(self, '알림', msg)

        except Exception as e:
            logging.error(f'설정 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_strategy_get(self, kind=None, clear=None):
        """전략 선택 가져오기 버튼 클릭"""
        try:
            # 현재 선택된 전략과 전략명칭 가져오기
            condition_text = self.cbCondition.currentText()

            if condition_text == dc.const.NON_STRATEGY and kind != None:
                QMessageBox.warning(None, '경고', f'검색식을 {dc.const.NON_STRATEGY} 이 아닌 것을 선택하세요.')
                return
            if kind:
                if kind == 'buy':
                    self.ledConditionBuy.setText(condition_text)
                elif kind == 'sell':
                    self.ledConditionSell.setText(condition_text)
            elif clear:
                if clear == 'buy':
                    self.ledConditionBuy.setText('')
                    self.chkConditionBuy.setChecked(False)
                elif clear == 'sell':
                    self.ledConditionSell.setText('')
                    self.chkConditionSell.setChecked(False)

        except Exception as e:
            logging.error(f'전략 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_get(self, kind=None, clear=None):
        """스크립트 선택 가져오기 버튼 클릭"""
        try:
            # 현재 선택된 스크립트 가져오기
            script_text = self.cbScript.currentText()

            if kind:
                if kind == 'buy':
                    self.ledScriptBuy.setText(script_text)
                elif kind == 'sell':
                    self.ledScriptSell.setText(script_text)
            elif clear:
                if clear == 'buy':
                    self.ledScriptBuy.setText('')
                    self.chkScriptBuy.setChecked(False)
                elif clear == 'sell':
                    self.ledScriptSell.setText('')
                    self.chkScriptSell.setChecked(False)

        except Exception as e:
            logging.error(f'스크립트 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    # QWidget 이벤트 -------------------------------------------------------------------------------------
    def gui_account_reload(self):
        gm.admin.get_holdings()
        gm.toast.toast(f'계좌를 다시 읽어 왔습니다.', duration=1000)
        logging.debug('메세지 발행: Work(pri_first_job, {})')

    def gui_account_changed(self):
        logging.debug('')
        if self.cbAccounts.currentText():
            gm.account = self.cbAccounts.currentText()
            gm.admin.get_holdings()
            logging.debug('메세지 발행: Work(pri_first_job, {})')
        else:
            logging.warning('계좌를 선택하세요')

    def gui_monitor_load(self):
        self.btnLoadMonitor.setEnabled(False)
        gm.admin.pri_fx얻기_매매목록(self.dtMonitor.date().toString("yyyy-MM-dd"))
        self.gui_fx갱신_매매정보()
        self.btnLoadMonitor.setEnabled(True)

    def gui_daily_load(self):
        self.btnLoadDaily.setEnabled(False)
        gm.admin.pri_fx얻기_매매일지(self.dtDaily.date().toString("yyyyMMdd"))
        self.gui_fx갱신_일지정보()
        self.btnLoadDaily.setEnabled(True)

    def gui_deposit_load(self):
        self.btnDeposit.setEnabled(False)
        gm.admin.pri_fx얻기_예수금()
        self.gui_fx갱신_예수금정보()
        self.btnDeposit.setEnabled(True)

    def gui_conclusion_load(self):
        self.btnLoadConclusion.setEnabled(False)
        gm.admin.pri_fx얻기_체결목록(self.dtConclusion.date().toString("yyyyMMdd"))
        self.gui_fx갱신_체결정보()
        self.btnLoadConclusion.setEnabled(True)

    def gui_chart_combo_add(self, item):
        self.cbChartCode.addItem(item)

    def gui_chart_load(self):
        self.btnChartLoad.setEnabled(False)
        date_text = self.dtChartDate.date().toString("yyyyMMdd")
        item = self.cbChartCycle.currentText()
        cycle = dc.scr.차트종류[item]
        tick = int(self.cbChartTick.currentText()) if item in ('분봉', '틱봉') else 1
        code = self.cbChartCode.currentText().split()[0]
        name = self.cbChartCode.currentText().split()[1]
        gm.admin.pri_fx얻기_차트자료(date_text, code, cycle, tick)
        gm.차트자료.update_table_widget(self.tblChart, header=0 if cycle in ('mi', 'tk') else 1)
        gm.toast.toast(f'차트자료를 갱신했습니다.', duration=1000)
        self.btnChartLoad.setEnabled(True)

    def gui_strategy_restart(self):
        self.gui_strategy_stop(question=False)
        self.gui_strategy_reload()
        self.gui_strategy_start(question=False)

    def gui_strategy_start(self, question=True):
        if question:
            response = QMessageBox.question(None, '전략매매 실행', '전략매매를 실행하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        else:
            response = True
        if response:
            gm.admin.cdn_fx실행_전략매매()
            if not any(gm.매수문자열들) and not any(gm.매도문자열들):
                gm.toast.toast('실행된 전략매매가 없습니다. 1분 이내에 재실행 됐거나, 실행될 전략이 없습니다.', duration=3000)
                return
            gm.toast.toast('전략매매를 실행했습니다.', duration=3000)
            self.set_strategy_toggle(run=True)
        else:
            logging.debug('전략매매 시작 취소')

    def gui_strategy_stop(self, question=True):
        if question:
            response = QMessageBox.question(None, '전략매매 중지', '전략매매를 중지하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        else:
            response = True
        if response:
            gm.admin.cdn_fx중지_전략매매()
            self.set_strategy_toggle(run=False)
            gm.toast.toast('전략매매를 중지했습니다.', duration=3000)
        else:
            logging.debug('전략매매 중지 취소')

    def gui_strategy_changed(self):
        logging.debug('')
        pass

    def gui_strategy_reload(self):
        logging.debug('메세지 발행: Work(cdn_fx요청_서버전략, {})')
        gm.admin.get_conditions()
        self.gui_fx채움_조건콤보()
        gm.toast.toast('전략매매를 다시 읽어 왔습니다.', duration=3000)

    def gui_chart_cycle_changed(self, item):
        self.cbChartTick.clear()
        if item in ['틱봉', '분봉']: 
            self.cbChartTick.addItems(dc.ticks.get(item,[]))

    def gui_log_level_set(self, key, value):
        if key == 'DEBUG' and value == True:
            level = logging.DEBUG
        else:
            level = logging.INFO
        gm.json_config['root']['level'] = level
        logging.getLogger().setLevel(level)
        save_json(os.path.join(get_path(dc.fp.LOG_PATH), dc.fp.LOG_JSON), gm.json_config)

        logging.info(f'로깅 설정 변경: {key} = {value}')

    def gui_balance_held_select(self, row_index, col_index):
        code = self.tblBalanceHeld.item(row_index, 1).text()
        logging.debug(f'cell = [{row_index:02d}:{col_index:02d}] code = {code}')
        row = gm.잔고목록.get(key=code)
        if row:
            self.leTrCode.setText(row['종목번호'])
            self.leTrName.setText(row['종목명'])
            self.spbTrPrice.setValue(row['현재가'])
            self.spbTrQty.setValue(row['보유수량'])
            self.rbTrSell.setChecked(True)
            self.leTrStrategy.setText(row['전략'])
        #self.tblBalanceHeld.clearSelection()  

    def gui_receipt_list_select(self, row_index, col_index):
        code = self.tblReceiptList.item(row_index, 3).text()
        kind = self.tblReceiptList.item(row_index, 1).text()
        key = f'{code}_{kind}'
        logging.debug(f'cell = [{row_index:02d}:{col_index:02d}] code = {code} kind = {kind} key = {key}')
        row = gm.주문목록.get(key=key)
        if row:
            self.leTrCode.setText(row['종목코드'])
            self.leTrName.setText(row['종목명'])
            self.spbTrPrice.setValue(row['주문가격'])
            self.spbTrQty.setValue(row['주문수량'])
            self.rbTrSell.setChecked(True if row['구분'] == '매도' else False)
            self.leTrStrategy.setText(row['전략'])
            self.leTrCancelKey.setText(row['키'])

    def gui_tr_code_changed(self):
        code = self.leTrCode.text().strip()
        if code:
            self.leTrName.setText(answer('api', 'GetMasterCodeName', code).strip())

    def gui_tr_order(self):
        kind = '매수' if self.rbTrBuy.isChecked() else '매도'
        if kind == '매수':
            전략 = '전략00'
        else:
            전략 = self.leTrStrategy.text().strip()
            if 전략: 
                if 전략 not in workers.keys():
                    logging.warning(f'전략이 실행중이지 않습니다. {전략}')
                    return
            
        전략번호 = int(전략[-2:])
        code = self.leTrCode.text().strip()
        price = self.spbTrPrice.value()
        qty = self.spbTrQty.value()
        row = gm.잔고목록.get(key=code)

        price = int(price) if price != '' else 0
        qty = int(qty) if qty != '' else 0

        if not code:
            QMessageBox.warning(self, '알림', '종목코드를 입력하세요.')
            return

        if self.rbTrLimit.isChecked() and price == 0:
            QMessageBox.warning(self, '알림', '지정가 매수시 주문가격을 입력하세요.')
            return
        else:
            price = hoga(price, int(self.spbTrHoga.value()))

        if qty == 0:
            QMessageBox.warning(self, '알림', '수량을 입력하세요.')
            return

        if self.rbTrBuy.isChecked():
            if row:
                QMessageBox.warning(self, '알림', '이미 보유 중인 종목입니다.')
                response = QMessageBox.question(None, '알림', '이미 보유 중인 종목입니다. 매수 하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
                if not response:
                    return
        else:
            if not row:
                QMessageBox.warning(self, '알림', '보유 중인 종목이 없습니다.')
                return
            
        rqname = f'수동{kind}'
        send_data = {
            'rqname': rqname,
            'screen': dc.scr.화면[rqname],
            'accno': gm.config.account,
            'ordtype': 1 if self.rbTrBuy.isChecked() else 2,
            'code': code,
            'quantity': qty,
            'price': price if self.rbTrLimit.isChecked() else 0,
            'hoga': '00' if self.rbTrLimit.isChecked() else '03',
            'ordno': ''
        }
        if kind == '매수':
            work('api', 'SetRealReg', dc.scr.화면['실시간감시'], code, '10', '1')
        else:
            if row['주문가능수량'] == 0:
                QMessageBox.warning(self, '알림', '주문가능수량이 없습니다.')
                return
            row['주문가능수량'] -= qty if row['주문가능수량'] >= qty else row['주문가능수량']
            gm.잔고목록.set(key=code, data=row)

        key = f'{code}_{kind}'
        data={'키': key, '구분': kind, '상태': '요청', '전략': 전략, '종목코드': code, '종목명': self.leTrName.text(), '전략매도': False}
        gm.주문목록.set(key=key, data=data) 
        # 주문 전송
        gm.admin.com_SendOrder(전략번호, **send_data)

    def gui_tr_cancel(self):
        key = self.leTrCancelKey.text().strip()
        row = gm.주문목록.get(key=key)
        if not row:
            QMessageBox.warning(self, '알림', '주문접수목록에서 취소할 항목을 선택하세요.')
            return
        if row['상태'] != '접수':
            gm.주문목록.delete(key=key)
            return
        
        전략 = row['전략']
        전략번호 = int(전략[-2:])
        odrerno = row['주문번호']
        code = row['종목코드']

        kind = '매수' if self.rbTrBuy.isChecked() else '매도'
        rqname = f'수취{kind}'
        send_data = {
            'rqname': rqname,
            'screen': dc.scr.화면[rqname],
            'accno': gm.config.account,
            'ordtype': 3 if kind == '매수' else 4,
            'code': code,
            'quantity': 0,
            'price': 0,
            'hoga': '03',
            'ordno': odrerno
        }

        # 주문 전송
        gm.admin.com_SendOrder(전략번호, **send_data)

    def gui_script_show(self):
        try:
            gm.스크립트.update_table_widget(self.tblScript)
        except Exception as e:
            logging.error(f'스크립트 표시 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_select(self, row_index):
        try:
            self.btnScriptSave.setEnabled(False)
            name = self.tblScript.item(row_index, 0).text()

            script = gm.스크립트.get(key=name, column='스크립트')
            vars = self.tblScript.item(row_index, 3)
            desc = self.tblScript.item(row_index, 4).text()

            self.ledScriptName.setText(name)
            self.txtScript.setText(script)
            self.txtScriptDesc.setText(desc)
            try:
                vars_dict = json.loads(vars.text())
            except Exception as e:
                vars_dict = {}
                logging.error(f'스크립트 변수 파싱 오류: {type(e).__name__} - {e}', exc_info=True)
            self.tblScriptVar.setRowCount(len(vars_dict))
            dict_list = []
            for i, (key, value) in enumerate(vars_dict.items()) :
              dict_list.append({'변수명': key, '값': value})
            self.tblScriptVar.setRowCount(len(dict_list))
            gm.스크립트변수.set(data=dict_list)
            gm.스크립트변수.update_table_widget(self.tblScriptVar)
            self.script_edited = False
            self.ledVarName.setText('')
            self.ledVarValue.setText('')

        except Exception as e:
            logging.error(f'스크립트 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_new(self):
        self.btnScriptSave.setEnabled(False)
        self.ledScriptName.setText('')
        self.txtScript.setText('')
        self.txtScriptDesc.setText('')
        self.tblScriptVar.setRowCount(0)
        self.txtScriptMsg.clear()

    def gui_script_delete(self):
        try:
            name = self.ledScriptName.text().strip()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 스크립트명을 확인 하세요.')
                return
            
            if not gm.스크립트.in_key(name):
                QMessageBox.warning(self, '알림', '스크립트가 존재하지 않습니다.')
                return

            reply = QMessageBox.question(self, '삭제 확인',
                                        f'{name} 스크립트를 삭제하시겠습니까?',
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 설정 삭제
                result = gm.스크립트.delete(key=name)
                if result:
                    gm.스크립트.update_table_widget(self.tblScript)
                    self.ledScriptName.setText('')
                    self.txtScript.setText('')
                    self.txtScriptDesc.setText('')
                    self.tblScriptVar.clearContents()
                    gm.스크립트변수.delete()
                    gm.스크립트변수.update_table_widget(self.tblScriptVar)
                    self.ledVarName.setText('')
                    self.ledVarValue.setText('')
                    gm.scm.delete_script_compiled(name)
                    self.txtScriptMsg.clear()
                    gm.list스크립트 = gm.스크립트.get(column='스크립트명')
                    self.gui_fx채움_스크립트콤보()

        except Exception as e:
            logging.error(f'스크립트 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_check(self):
        try:
            script_name = self.ledScriptName.text().strip()
            script = self.txtScript.toPlainText()
            if len(script_name.strip()) == 0 or len(script.strip()) == 0:
                QMessageBox.information(self, '알림', '스크립트명과 스크립트를 입력하세요.')
                return
            vars_dict = {}
            for row in range(self.tblScriptVar.rowCount()):
                key = self.tblScriptVar.item(row, 0).text().strip()
                value = self.tblScriptVar.item(row, 1).text()
                vars_dict[key] = float(value) if value else 0.0
            result = gm.scm.run_script(script_name, check_only=True, script_data={'script': script, 'vars': vars_dict}, kwargs={'code': '005930'})
            if result['success']:
                QMessageBox.information(self, '알림', f'스크립트에 이상이 없습니다.\n\n반환값={result["result"]}')
                self.btnScriptSave.setEnabled(True)
                self.txtScriptMsg.clear()
            else:
                QMessageBox.critical(self, '에러', result['error'])
                self.txtScriptMsg.append(result['error'])
                self.txtScriptMsg.moveCursor(QTextCursor.End)
                self.btnScriptSave.setEnabled(False)
        except Exception as e:
            logging.error(f'스크립트 확인 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_save(self):
        try:
            script_name = self.ledScriptName.text() #.strip()
            script = self.txtScript.toPlainText() #.strip()
            desc = self.txtScriptDesc.toPlainText() #.strip()
            vars = {}
            kwargs = {'code': '005930', 'name': '', 'price': 0, 'qty': 0}
            for row in range(self.tblScriptVar.rowCount()):
                key = self.tblScriptVar.item(row, 0).text().strip()
                value = self.tblScriptVar.item(row, 1).text()
                vars[key] = float(value) if value else 0.0
            script_type = gm.scm.set_script_compiled(script_name, script, vars, desc, kwargs) # 실패시 False, 성공시 스크립트 타입 반환
            if script_type:
                gm.스크립트.set(key=script_name, data={'스크립트': script, '변수': json.dumps(vars), '타입': script_type, '설명': desc})
                gm.스크립트.update_table_widget(self.tblScript)
                gm.list스크립트 = gm.스크립트.get(column='스크립트명')
                self.gui_fx채움_스크립트콤보()
                self.txtScriptMsg.clear()
                self.script_edited = False
            else:
                logging.error(f'스크립트 저장 오류: script_type={script_type}')
        except Exception as e:
            logging.error(f'스크립트 저장 오류: {type(e).__name__} - {e}', exc_info=True)
        finally:
            self.btnScriptSave.setEnabled(False)
    
    def gui_var_select(self, row_index):
        try:
            name = self.tblScriptVar.item(row_index, 0).text()
            value = self.tblScriptVar.item(row_index, 1).text()
            self.ledVarName.setText(name)
            self.ledVarValue.setText(value)
        except Exception as e:
            logging.error(f'변수 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_var_delete(self):
        try:
            name = self.ledVarName.text().strip()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 변수명을 확인 하세요.')
                return

            reply = QMessageBox.question(self, '삭제 확인',
                                        f'{name} 변수를 삭제하시겠습니까?',
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 설정 삭제
                result = gm.스크립트변수.delete(key=name)
                if result:
                    gm.스크립트변수.update_table_widget(self.tblScriptVar)
                    self.ledVarName.setText('')
                    self.ledVarValue.setText('')
                
        except Exception as e:
            logging.error(f'변수 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_var_save(self):
        try:
            name = self.ledVarName.text().strip()
            value = self.ledVarValue.text().strip()
            gm.스크립트변수.set(key=name, data={'변수명': name, '값': value})
            gm.스크립트변수.update_table_widget(self.tblScriptVar)
            self.ledVarName.setText('')
            self.ledVarValue.setText('')
        
        except Exception as e:
            logging.error(f'변수 저장 오류: {type(e).__name__} - {e}', exc_info=True)
    
    # 화면 갱신 -----------------------------------------------------------------------------------------------------------------
    def gui_fx채움_계좌콤보(self):
        try:
            self.cbAccounts.clear()
            self.cbAccounts.addItems([account for account in gm.list계좌콤보 if account.strip()])
            self.cbAccounts.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'계좌콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_조건콤보(self):
        try:
            self.cbCondition.clear()
            self.cbCondition.addItem(dc.const.NON_STRATEGY)  # 선택없음 추가
            self.cbCondition.addItems([strategy for strategy in gm.list전략콤보 if strategy.strip()])
            self.cbCondition.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'조건콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_스크립트콤보(self):
        try:
            self.cbScript.clear()
            self.cbScript.addItems([script for script in gm.list스크립트 if script.strip()])
            self.cbScript.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'스크립트콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_전략정의(self):
        try:
            self.cbTabStrategy.clear()
            self.cbTabStrategy.addItems([name for name in gm.전략정의.get(column='전략명칭') if name.strip()])
            self.cbTabStrategy.setCurrentIndex(0)
            gm.전략정의.update_table_widget(self.tblStrategy)
        except Exception as e:
            logging.error(f'전략정의 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx갱신_매매정보(self):
        try:
            gm.매매목록.update_table_widget(self.tblMonitor, stretch=True)

        except Exception as e:
            logging.error(f'매매정보 갱신 오류: {type(e).__name__} - {e}', exc_info=True)

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

    def gui_fx갱신_목록테이블(self):
        try:
            self.gui_set_color(self.lblProfitLoss, gm.l2손익합산)
            row = gm.잔고합산.get(key=0)
            if row is None: row = {}
            self.lblBuy.setText(f"{int(row.get('총매입금액', 0)):,}")
            self.lblAmount.setText(f"{int(row.get('총평가금액', 0)):,}")
            self.lblAssets.setText(f"{int(row.get('추정예탁자산', 0)):,}")
            self.gui_set_color(self.lblProfit, int(row.get('총평가손익금액', 0)))
            self.gui_set_color(self.lblFrofitRate, float(row.get('총수익률(%)', 0.0)))
            gm.잔고목록.update_table_widget(self.tblBalanceHeld, stretch=False)

            gm.매수조건목록.update_table_widget(self.tblConditionBuy)
            gm.매도조건목록.update_table_widget(self.tblConditionSell)
            gm.주문목록.update_table_widget(self.tblReceiptList)

        except Exception as e:
            logging.error(f'목록테이블 갱신 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx갱신_전략정의(self):
        try:
            #self.cbTabStrategy.clearContents()
            gm.전략정의.update_table_widget(self.tblStrategy)
        except Exception as e:
            logging.error(f'전략정의 갱신 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx갱신_일지정보(self):
        try:
            row = gm.일지합산.get(key=0)
            self.lblDailyBuy.setText(f"{int(row['총매수금액']):,}" if row else '0')
            self.lblDailySell.setText(f"{int(row['총매도금액']):,}" if row else '0')
            self.lblDailyFee.setText(f"{int(row['총수수료_세금']):,}" if row else '0')
            self.lblDailyAmount.setText(f"{int(row['총정산금액']):,}" if row else '0')
            #self.lblDailyProfit.setText(f"{int(row['총손익금액']):,}" if row else '0')
            #self.lblDailyProfitRate.setText(f"{float(row['총수익률']):.2f}%" if row else '0.0')
            self.gui_set_color(self.lblDailyProfit, int(row['총손익금액']) if row else 0)
            self.gui_set_color(self.lblDailyProfitRate, float(row['총수익률']) if row else 0.0)
            #self.tblDaily.clearContents()
            gm.일지목록.update_table_widget(self.tblDaily)
            gm.toast.toast(f'일지를 갱신했습니다.', duration=1000)
        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx갱신_예수금정보(self):
        try:
            row = gm.예수금.get(key=0)
            self.lblDeposit11.setText(f"{int(row['d+1추정예수금']):,}" if row else '0')
            self.lblDeposit12.setText(f"{int(row['d+1매도매수정산금']):,}" if row else '0')
            self.lblDeposit13.setText(f"{int(row['d+1미수변제소요금']):,}" if row else '0')
            self.lblDeposit14.setText(f"{int(row['d+1출금가능금액']):,}" if row else '0')
            self.lblDeposit21.setText(f"{int(row['d+2추정예수금']):,}" if row else '0')
            self.lblDeposit22.setText(f"{int(row['d+2매도매수정산금']):,}" if row else '0')
            self.lblDeposit23.setText(f"{int(row['d+2미수변제소요금']):,}" if row else '0')
            self.lblDeposit24.setText(f"{int(row['d+2출금가능금액']):,}" if row else '0')
            self.lblDeposit31.setText(f"{int(row['예수금']):,}" if row else '0')
            self.lblDeposit32.setText(f"{int(row['주식증거금현금']):,}" if row else '0')
            self.lblDeposit33.setText(f"{int(row['미수확보금']):,}" if row else '0')
            self.lblDeposit34.setText(f"{int(row['권리대용금']):,}" if row else '0')
            self.lblDeposit51.setText(f"{int(row['20%종목주문가능금액']):,}" if row else '0')
            self.lblDeposit52.setText(f"{int(row['30%종목주문가능금액']):,}" if row else '0')
            self.lblDeposit53.setText(f"{int(row['40%종목주문가능금액']):,}" if row else '0')
            self.lblDeposit54.setText(f"{int(row['100%종목주문가능금액']):,}" if row else '0')
            self.lblDeposit61.setText(f"{int(row['주문가능금액']):,}" if row else '0')
            self.lblDeposit62.setText(f"{int(row['출금가능금액']):,}" if row else '0')
            self.lblDeposit63.setText(f"{int(row['현금미수금']):,}" if row else '0')
            gm.toast.toast(f'예수금을 갱신했습니다.', duration=1000)
        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx갱신_체결정보(self):
        try:
            매수금액, 매도금액, 손익금액, 제비용 = gm.체결목록.sum(filter={'매도수량': ('==', '@매수수량')}, column=['매수금액', '매도금액', '손익금액', '제비용'])
            self.lblConcBuy.setText(f"{매수금액:,}")
            self.lblConcSell.setText(f"{매도금액:,}")
            self.lblConcFee.setText(f"{제비용:,}")
            #self.lblConcCount.setText(f"{gm.체결목록.len(filter={'매도수량': ('==', '@매수수량')})}") # 다른 컬럼과 비교시 @ 를 앞에 붙인다.
            self.lblConcCount.setText(f"{gm.체결목록.len(filter={'매도수량': ('>', 0)})}") # 다른 컬럼과 비교시 @ 를 다른 컬럼명 앞에 붙인다. @매수수량
            손익율 = round(손익금액 / 매수금액 * 100, 2) if 매수금액 else 0
            self.gui_set_color(self.lblConcProfit, 손익금액)
            self.gui_set_color(self.lblConcProfitRate, 손익율)
            logging.debug(f"체결목록 합산: 매수금액={매수금액}, 매도금액={매도금액}, 손익금액={손익금액}, 제비용={제비용}")
            # if gm.체결목록.len(filter={'매도수량': ('!=', '@매수수량')}) > 0:
            #     gm.체결목록.set(filter={'매도수량': ('!=', '@매수수량')}, data={'손익금액': 0, '손익율': 0})

            #self.tblConclusion.clearContents()
            gm.체결목록.update_table_widget(self.tblConclusion)
            gm.toast.toast(f'체결목록을 갱신했습니다.', duration=1000)
        except Exception as e:
            logging.error(f'체결정보 갱신 오류: {type(e).__name__} - {e}', exc_info=True)

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
    def gui_update_status(self, data=None):
        try:
            # 기본 상태바 업데이트
            now = datetime.now()
            if now > self.lbl3_update_time + timedelta(seconds=60): self.lbl3.setText('')
            self.lbl1.setText(now.strftime("%Y-%m-%d %H:%M:%S"))
            self.lbl2.setText('연결됨' if gm.connected else '끊어짐')
            self.lbl2.setStyleSheet("color: green;" if gm.connected else "color: red;")
            self.lbl4.setText(answer('admin', 'com_market_status'))

            # 큐 메시지 처리
            while not gm.qwork['msg'].empty():
                data = gm.qwork['msg'].get()
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
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.txtOrder.append(f"[{current_time}] {msg}")
        self.txtOrder.moveCursor(QTextCursor.End)

    def gui_fx게시_검색내용(self, msg):
        if msg == '':
            self.txtCondition.clear()
            return
        current_time = datetime.now().strftime("%H:%M:%S")
        self.txtCondition.append(f"{current_time} {msg}")
        self.txtCondition.moveCursor(QTextCursor.End)

