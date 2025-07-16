from public import get_path, gm, dc, save_json, load_json, hoga, com_market_status
from dbm_server import db_columns
from tables import tbl
from chart import ChartData
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QLabel, QWidget, QTabWidget, QPushButton, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtCore import QCoreApplication, QEvent, QTimer, QTime, QDate, Qt
from PyQt5 import uic
from datetime import datetime, timedelta
from queue import Queue
import logging
import os
import json
import time

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
        self.cht_dt = ChartData()

        gm.qwork['gui'] = Queue()
        gm.qwork['msg'] = Queue()

    # 화면 설정 ---------------------------------------------------------------------------------------------
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

            self.dtSimDate.setMaximumDate(today)
            self.dtSimDate.setCalendarPopup(True)
            self.dtSimDate.setDate(today)

            self.tblScript.setColumnCount(3)
            self.tblScript.setHorizontalHeaderLabels(['스크립트명', '타입', '스크립트', '설명'])

            self.cbChartCycle.setCurrentText('분봉')
            self.cbChartTick.clear()
            self.cbChartTick.addItems(dc.ticks.get('분봉',[]))
            self.cbChartTick.setCurrentText('3')
            self.cbChartCode.addItem('005930 삼성전자')

            # 폼 초기화 시
            self.txtScript.setAcceptRichText(False)  # 서식 있는 텍스트 거부            

            # 조건목록 그룹박스 체크
            gm.gbx_buy_checked = self.gbxBuyCheck.isChecked()
            gm.gbx_sell_checked = self.gbxSellCheck.isChecked()

            if gm.sim_no == 0: self.rbReal.setChecked(True)
            elif gm.sim_no == 1: self.rbSim1.setChecked(True)
            elif gm.sim_no == 2: self.rbSim2.setChecked(True)
            elif gm.sim_no == 3: self.rbSim3.setChecked(True)

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

            self.tblStrategy.clicked.connect(lambda x: self.gui_set_strategy(x.row()))  # 실행전략 선택
            self.btnLoadCondition.clicked.connect(self.gui_strategy_reload)             # 검색식 재로드
            self.btnTabLoadStrategy.clicked.connect(self.gui_strategy_load)             # 실행전략 로드
            self.btnConditionBuy.clicked.connect(lambda: self.gui_strategy_get(kind='buy')) # 매수전략 선택
            self.btnConditionSell.clicked.connect(lambda: self.gui_strategy_get(kind='sell'))# 매도전략 선택
            self.btnBuyClear.clicked.connect(lambda: self.gui_strategy_get(clear='buy'))    # 매수전략 클리어
            self.btnSellClear.clicked.connect(lambda: self.gui_strategy_get(clear='sell'))  # 매도전략 클리어
            self.btnStrategySave.clicked.connect(self.gui_strategy_save)                # 실행전략 저장
            self.btnStrategyDelete.clicked.connect(self.gui_strategy_delete)            # 실행전략 삭제

            self.btnRestartAll.clicked.connect(self.gui_strategy_restart)                 # 전략매매 재시작
            self.btnStartAll.clicked.connect(self.gui_strategy_start)                       # 전략매매 시작
            self.btnStopAll.clicked.connect(self.gui_strategy_stop)                         # 전략매매 중지
            self.btnLoadDaily.clicked.connect(self.gui_daily_load)                      # 매매일지 로드
            self.btnDeposit.clicked.connect(self.gui_deposit_load)                      # 예수금 로드
            self.btnLoadConclusion.clicked.connect(self.gui_conclusion_load)            # 체결목록 로드
            self.btnLoadMonitor.clicked.connect(self.gui_monitor_load)                  # 당일 매매 목록 로드

            # 차트자료
            self.cbChartCycle.currentIndexChanged.connect(lambda idx: self.gui_chart_cycle_changed(self.cbChartCycle.itemText(idx))) # 차트 주기 변경 선택
            #self.btnChartLoad.clicked.connect(self.gui_chart_load)                      # 차트 로드 (db)
            self.btnChartLoad.clicked.connect(self.gui_chart_data_load)                  # 차트 로드 (ChartData)

            # 로깅 레벨
            self.rbInfo.toggled.connect(lambda: self.gui_log_level_set('INFO', self.rbInfo.isChecked()))
            self.rbDebug.toggled.connect(lambda: self.gui_log_level_set('DEBUG', self.rbDebug.isChecked()))

            # 수동 주문 / 주문 취소
            self.btnTrOrder.clicked.connect(self.gui_tr_order)                          # 매매 주문 
            self.btnTrCancel.clicked.connect(self.gui_tr_cancel)                        # 매매 취소 
            self.leTrCode.editingFinished.connect(lambda: self.gui_tr_code_changed(kind='tr'))             # 종목코드 변경
            self.tblBalanceHeld.cellClicked.connect(self.gui_balance_held_select)       # 잔고목록 선택
            self.tblReceiptList.cellClicked.connect(self.gui_receipt_list_select)       # 주문목록 선택

            #그룹박스 체크
            self.gbxBuyCheck.toggled.connect(lambda: self.gui_gbx_check(self.gbxBuyCheck.isChecked(), 'buy'))
            self.gbxSellCheck.toggled.connect(lambda: self.gui_gbx_check(self.gbxSellCheck.isChecked(), 'sell'))

            # 시뮬레이션 재시작
            self.btnSimStart.clicked.connect(self.gui_simulation_restart) # 시뮬레이션 재시작

            # 시뮬레이션 실행일자 데이타 가져오기
            self.btnSimReadDay.clicked.connect(self.gui_sim_read_day)

            # 시뮬레이션 차트데이타
            self.btnSimAddDay.clicked.connect(self.gui_sim_add_day)
            self.btnSimDelDay.clicked.connect(self.gui_sim_del_day)
            self.btnSimClearDay.clicked.connect(self.gui_sim_clear_day)
            self.leSimCodeDay.editingFinished.connect(lambda: self.gui_tr_code_changed(kind='day'))             # 종목코드 변경
            self.tblSimDaily.clicked.connect(lambda x: self.gui_sim_daily_select(x.row()))  

            # 시뮬레이션 수동데이타
            self.btnSimAddMan.clicked.connect(self.gui_sim_add_manual)
            self.btnSimDelMan.clicked.connect(self.gui_sim_del_manual)
            self.btnSimClearMan.clicked.connect(self.gui_sim_clear_manual)
            self.leSimCode.editingFinished.connect(lambda: self.gui_tr_code_changed(kind='man'))             # 종목코드 변경
            self.tblSimManual.clicked.connect(lambda x: self.gui_sim_manual_select(x.row()))  # 수동데이타 선택

            # 스크립트
            self.tblScript.clicked.connect(lambda x: self.gui_script_select(x.row()))  # 스크립트 선택
            self.btnScriptNew.clicked.connect(self.gui_script_new)
            self.btnScriptDel.clicked.connect(self.gui_script_delete)
            self.btnScriptChk.clicked.connect(lambda: self.gui_script_check(save=False))
            self.btnScriptSave.clicked.connect(lambda: self.gui_script_check(save=True))
            self.txtScript.textChanged.connect(lambda: setattr(self, 'script_edited', True))

            # 전략정의 에서 스크립트
            self.btnScriptBuy.clicked.connect(lambda: self.gui_script_get(kind='buy'))
            self.btnScriptSell.clicked.connect(lambda: self.gui_script_get(kind='sell'))
            self.btnScriptBuyClear.clicked.connect(lambda: self.gui_script_get(clear='buy'))
            self.btnScriptSellClear.clicked.connect(lambda: self.gui_script_get(clear='sell'))

            self.gui_tabs_init()

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    # 메인화면 시작 및 종료 ---------------------------------------------------------------------------------------------
    def gui_show(self):
        self.show()

    def gui_close(self):
        close_event = QEvent(QEvent.Close)
        QCoreApplication.sendEvent(self, close_event)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, '종료 확인', '종료하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
            gm.ready = False
            self.refresh_data_timer.stop()
            self.refresh_data_timer.deleteLater()
            self.refresh_data_timer = None
            logging.debug(f'GUI 종료')
            gm.main.cleanup()
        else:
            event.ignore()

    def init(self):
        self.set_widgets()
        self.gui_fx채움_계좌콤보()
        self.gui_fx채움_조건콤보()
        self.gui_fx채움_스크립트콤보()
        self.gui_fx채움_전략정의()
        self.gui_fx전시_전략정의()
        self.set_widget_events()
        if gm.log_level == logging.DEBUG:
            self.rbDebug.setChecked(True)
            self.rbInfo.setChecked(False)
        else:
            self.rbInfo.setChecked(True)
            self.rbDebug.setChecked(False)

        self.refresh_data_timer.start(dc.INTERVAL_GUI)

        success, gm.json_config = load_json(os.path.join(get_path(dc.fp.LOG_PATH), dc.fp.LOG_JSON), dc.log_config)
        logging.getLogger().setLevel(gm.json_config['root']['level'])
        self.rbDebug.setChecked(gm.json_config['root']['level'] == logging.DEBUG)
        #logging.debug('prepare : gui 초기화 완료')

    # 화면 갱신 ---------------------------------------------------------------------------------------------
    def gui_refresh_data(self):
        try:
            if not gm.qwork['gui'].empty():
                data = gm.qwork['gui'].get()
                getattr(self, data.order)(**data.job)

            self.gui_display_status()
            self.gui_fx갱신_목록테이블()

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def set_strategy_toggle(self, run=True):
        self.btnStartAll.setEnabled(not run)
        self.btnStopAll.setEnabled(run)

    def gui_table_update(self):
        gm.잔고목록.update_table_widget(self.tblBalanceHeld)
        gm.매수조건목록.update_table_widget(self.tblConditionBuy)
        gm.매도조건목록.update_table_widget(self.tblConditionSell)
        gm.주문목록.update_table_widget(self.tblReceiptList)

    # QWidget 이벤트 -------------------------------------------------------------------------------------
    def gui_account_reload(self):
        gm.admin.get_holdings()
        gm.toast.toast(f'계좌를 다시 읽어 왔습니다.', duration=1000)
        logging.debug('계좌를 다시 읽어 왔습니다.')

    def gui_account_changed(self):
        logging.debug('')
        if self.cbAccounts.currentText():
            gm.account = self.cbAccounts.currentText()
            gm.admin.get_holdings()
            logging.debug('계좌를 다시 읽어 왔습니다.')
        else:
            logging.warning('계좌를 선택하세요')

    def gui_monitor_load(self):
        self.btnLoadMonitor.setEnabled(False)
        date_text = self.dtMonitor.date().toString("yyyy-MM-dd")
        try:
            gm.매매목록.delete()
            dict_list = gm.prx.answer('dbm', 'execute_query', sql=db_columns.TRD_SELECT_DATE, db='db', params=(date_text,))
            if dict_list is not None and len(dict_list) > 0:
                gm.매매목록.set(data=dict_list)
                logging.info(f"매매목록 얻기 완료: data count={gm.매매목록.len()}")
            else:
                logging.warning(f'매매목록 얻기 실패: date:{date_text}, dict_list:{dict_list}')
        except Exception as e:
            logging.error(f'매매목록 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        gm.매매목록.update_table_widget(self.tblMonitor, stretch=True)
        self.btnLoadMonitor.setEnabled(True)

    def gui_daily_load(self):
        self.btnLoadDaily.setEnabled(False)
        date_text = self.dtDaily.date().toString("yyyyMMdd")
        try:
            gm.일지합산.delete()
            gm.일지목록.delete()
            data = []
            input = {'계좌번호':gm.account, '비밀번호': '', '기준일자': date_text, '단주구분': 2, '현금신용구분': 0}
            rqname = '일지합산'
            trcode = 'opt10170'
            output = tbl.hd일지합산['컬럼']
            next = '0'
            screen = dc.scr.화면['일지합산']
            data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
            if data:
                for i, item in enumerate(data):
                    item.update({'순번':i})
                gm.일지합산.set(data=data)
                logging.info(f'매매일지 합산 얻기 완료: date:{date_text}, data:\n{data}')
            else:
                logging.warning(f'매매일지 합산 얻기 실패: date:{date_text}, data:{data}')

            dict_list = []
            input = {'계좌번호':gm.account, '비밀번호': '', '기준일자': date_text, '단주구분': 2, '현금신용구분': 0} # 단주구분:2=당일매도전체. 1=당일매수에대한매도
            rqname = '일지목록'
            trcode = 'opt10170'
            output = tbl.hd일지목록['컬럼']
            screen = dc.scr.화면['일지목록']
            next = '0'
            while True:
                data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
                logging.debug(f'일지목록 얻기: data count={len(data)}, remain={remain}')
                dict_list.extend(data)
                if not remain: break
                next = '2'
            if not data:
                logging.warning(f'매매일지 목록 얻기 실패: date:{date_text}, dict_list:{dict_list}')
                return

            dict_list = [{**item, '종목코드': item['종목코드'][1:]} for item in dict_list]
            gm.일지목록.set(data=dict_list)
            logging.info(f"일지목록 얻기 완료: date:{date_text}, data count={gm.일지목록.len()}")

        except Exception as e:
            logging.error(f'매매일지 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        self.gui_fx갱신_일지정보()
        self.btnLoadDaily.setEnabled(True)

    def gui_deposit_load(self):
        self.btnDeposit.setEnabled(False)
        try:
            dict_list = []
            rqname = '예수금'
            trcode = 'opw00001'
            input = {'계좌번호':gm.account, '비밀번호': '', '비밀번호입력매체구분': '00', '조회구분': '3'}
            output = tbl.hd예수금['컬럼']
            next = '0'
            screen = dc.scr.화면['예수금']
            data, remain = gm.prx.answer('api', 'api_request', rqname=rqname, trcode=trcode, input=input, output=output, next=next, screen=screen)
            if data:
                for i, item in enumerate(data):
                    item.update({'순번':i})
                gm.예수금.set(data=data)
                row = gm.예수금.get(key=0)
                logging.info(f'예수금 얻기 완료: 예수금={row["예수금"]:,}원 출금가능금액={row["출금가능금액"]:,}원 주문가능금액={row["주문가능금액"]:,}원')
            else:
                logging.warning(f'예수금 얻기 실패: dict_list={dict_list}')

        except Exception as e:
            logging.error(f'예수금 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        self.gui_fx갱신_예수금정보()
        self.btnDeposit.setEnabled(True)

    def gui_conclusion_load(self):
        self.btnLoadConclusion.setEnabled(False)
        date_text = self.dtConclusion.date().toString("yyyyMMdd")
        try:
            gm.체결목록.delete()
            dict_list = gm.prx.answer('dbm', 'execute_query', sql=db_columns.CONC_SELECT_DATE, db='db', params=(date_text,))
            if dict_list is not None and len(dict_list) > 0:
                gm.체결목록.set(data=dict_list)
                손익금액, 매수금액 = gm.체결목록.sum(column=['손익금액', '매수금액'], filter={'매도수량': ('==', '@매수수량')})
                손익율 = round(손익금액 / 매수금액 * 100, 2) if 매수금액 else 0
                logging.info(f"체결목록 얻기 완료: data count={gm.체결목록.len()}, 손익금액={손익금액:,}원, 손익율={손익율:,.2f}%")
            else:
                logging.warning(f'체결목록 얻기 실패: date:{date_text}, dict_list:{dict_list}')

        except Exception as e:
            logging.error(f'체결목록 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        self.gui_fx갱신_체결정보()
        self.btnLoadConclusion.setEnabled(True)

    def gui_chart_combo_add(self, item):
        if item not in [self.cbChartCode.itemText(i) for i in range(self.cbChartCode.count())]:
            self.cbChartCode.addItem(item)

    def gui_chart_load(self):
        self.btnChartLoad.setEnabled(False)
        date_text = self.dtChartDate.date().toString("yyyyMMdd")
        item = self.cbChartCycle.currentText()
        cycle = dc.scr.차트종류[item]
        tick = int(self.cbChartTick.currentText()) if item in ('분봉', '틱봉') else 1
        code = self.cbChartCode.currentText().split()[0]
        name = self.cbChartCode.currentText().split()[1]
        try:
            logging.debug(f'차트자료 얻기: date:{date_text}, code:{code}, cycle:{cycle}, tick:{tick}')
            gm.차트자료.delete()
            min_check = cycle in ('mi', 'tk')
            if min_check: params = (date_text, cycle, tick, code,)
            else: params = (date_text, cycle,)
            selected_sql = db_columns.MIN_SELECT_DATE if min_check else db_columns.DAY_SELECT_DATE
            dict_list = gm.prx.answer('dbm', 'execute_query', sql=selected_sql, db='chart', params=params)
            if dict_list:
                if isinstance(dict_list, list) and len(dict_list) > 0:
                    if min_check:
                        dict_list = [{ **item, '일자': item['체결시간'][:8], '시간': item['체결시간'][8:], } for item in dict_list]
                    else:
                        dict_list = [{ **item, '일자': item['일자'], '시간': '', '종목명': gm.prx.answer('api', 'GetMasterCodeName', item['종목코드']), } for item in dict_list]

                gm.차트자료.set(data=dict_list)
                logging.info(f"차트자료 얻기 완료: data count={gm.차트자료.len()}")
            else:
                logging.warning(f'차트자료 얻기 실패: date:{date_text}, dict_list:{dict_list}')

        except Exception as e:
            logging.error(f'차트자료 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        gm.차트자료.update_table_widget(self.tblChart, header=0 if cycle in ('mi', 'tk') else 1) # 헤더 선택 (리스트에서)
        gm.toast.toast(f'차트자료를 갱신했습니다.', duration=1000)
        self.btnChartLoad.setEnabled(True)

    def gui_chart_data_load(self):
        self.btnChartLoad.setEnabled(False)
        date_text = self.dtChartDate.date().toString("yyyyMMdd")
        item = self.cbChartCycle.currentText()
        cycle = dc.scr.차트종류[item]
        tick = int(self.cbChartTick.currentText()) if item in ('분봉', '틱봉') else 1
        code = self.cbChartCode.currentText().split()[0]
        name = self.cbChartCode.currentText().split()[1]
        try:
            logging.debug(f'차트자료 얻기: date:{date_text}, code:{code}, cycle:{cycle}, tick:{tick}')
            gm.차트자료.delete()
            min_check = cycle in ('mi', 'tk')
            dict_list = self.cht_dt.get_chart_data(code, cycle, tick)
            if dict_list:
                if isinstance(dict_list, list) and len(dict_list) > 0:
                    if min_check:
                        dict_list = [{ **item, '일자': item['체결시간'][:8], '시간': item['체결시간'][8:], } for item in dict_list]
                    else:
                        dict_list = [{ **item, '시간': '' } for item in dict_list]

                gm.차트자료.set(data=dict_list)
                logging.info(f"차트자료 얻기 완료: data count={gm.차트자료.len()}")
            else:
                logging.warning(f'차트자료 얻기 실패: date:{date_text}, dict_list:{dict_list}')
            self.lblSelected.setText(f'{tick} {item} / {code} {name}')
        except Exception as e:
            logging.error(f'차트자료 얻기 오류: {type(e).__name__} - {e}', exc_info=True)

        gm.차트자료.update_table_widget(self.tblChart, header=2)
        #gm.toast.toast(f'차트자료를 갱신했습니다.', duration=1000)
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
            gm.admin.stg_start()
            if not all([gm.매수문자열, gm.매도문자열]):
                gm.toast.toast('실행된 전략매매가 없습니다. 1분 이내에 재실행 됐거나, 실행될 전략이 없습니다.', duration=3000)
                return
            gm.toast.toast('전략매매를 실행했습니다.', duration=3000)
            self.set_strategy_toggle(run=True)
        else:
            logging.debug('전략매매 시작 취소')
            
    def gui_strategy_stop(self, question=True):
        response = True
        if question:
            response = QMessageBox.question(None, '전략매매 중지', '전략매매를 중지하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        if response:
            gm.admin.stg_stop()
            self.set_strategy_toggle(run=False)
            gm.toast.toast('전략매매를 중지했습니다.', duration=3000)
        else:
            logging.debug('전략매매 중지 취소')

    def gui_simulation_restart(self):
        self.gui_simulation_stop()
        self.gui_simulation_start()

    def gui_simulation_start(self):
        gm.sim_no = 0 if self.rbReal.isChecked() else 1 if self.rbSim1.isChecked() else 2 if self.rbSim2.isChecked() else 3
        gm.sim_on = gm.sim_no > 0
        gm.prx.order('api', 'api_init', sim_no=gm.sim_no)
        gm.prx.order('api', 'set_tickers')
        gm.prx.order('dbm', 'dbm_init', gm.sim_no, gm.log_level)
        gm.admin.restart()
        gm.admin.stg_start()
        if not all([gm.매수문자열, gm.매도문자열]):
            gm.toast.toast('실행된 전략매매가 없습니다. 1분 이내에 재실행 됐거나, 실행될 전략이 없습니다.', duration=3000)
            return
        gm.toast.toast('전략매매를 실행했습니다.', duration=3000)
        self.set_strategy_toggle(run=True)
            
    def gui_simulation_stop(self):
        gm.admin.stg_stop()
        gm.prx.order('api', 'thread_cleanup')
        self.set_strategy_toggle(run=False)
        gm.toast.toast('전략매매를 중지했습니다.', duration=3000)

    def gui_strategy_changed(self):
        pass

    def gui_strategy_reload(self):
        logging.debug('get_conditions: 요청_서버전략')
        gm.admin.get_conditions()
        self.gui_fx채움_조건콤보()
        gm.toast.toast('매매전략을 다시 읽어 왔습니다.', duration=3000)

    def gui_chart_cycle_changed(self, item):
        self.cbChartTick.clear()
        if item in ['틱봉', '분봉']: 
            self.cbChartTick.addItems(dc.ticks.get(item,[]))

    def gui_log_level_set(self, key, value):
        if value:
            if key == 'DEBUG':
                level = logging.DEBUG
            else:
                level = logging.INFO
            
            gm.json_config['root']['level'] = level
            gm.log_level = level
            logging.getLogger().setLevel(level)
            gm.prx.order('api', 'set_log_level', level)
            gm.prx.order('dbm', 'set_log_level', level)
            save_json(os.path.join(get_path(dc.fp.LOG_PATH), dc.fp.LOG_JSON), gm.json_config)

            logging.info(f'Main 로그 레벨 설정: {level}')

    def gui_gbx_check(self, value, kind):
        if kind == 'buy':
            gm.gbx_buy_checked = value
            if value:
                gm.매수조건목록.delete(filter={'이탈': '⊙'})
            else:
                self.tblConditionBuy.setEnabled(True)
        else:
            gm.gbx_sell_checked = value
            if value:
                gm.매도조건목록.delete(filter={'이탈': '⊙'})
            else:
                self.tblConditionSell.setEnabled(True)

    def gui_balance_held_select(self, row_index, col_index):
        code = self.tblBalanceHeld.item(row_index, 0).text()
        logging.debug(f'cell = [{row_index:02d}:{col_index:02d}] code = {code}')
        row = gm.잔고목록.get(key=code)
        if row:
            self.leTrCode.setText(row['종목번호'])
            self.leTrName.setText(row['종목명'])
            self.spbTrPrice.setValue(row['현재가'])
            self.spbTrQty.setValue(row['보유수량'])
            self.rbTrSell.setChecked(True)
            # self.leTrStrategy.setText(row['전략'])
        #self.tblBalanceHeld.clearSelection()  

    def gui_receipt_list_select(self, row_index, col_index):
        code = self.tblReceiptList.item(row_index, 2).text()
        kind = self.tblReceiptList.item(row_index, 0).text()
        key = f'{code}_{kind}'
        logging.debug(f'cell = [{row_index:02d}:{col_index:02d}] code = {code} kind = {kind} key = {key}')
        row = gm.주문목록.get(key=key)
        if row:
            self.leTrCode.setText(row['종목코드'])
            self.leTrName.setText(row['종목명'])
            self.spbTrPrice.setValue(row['주문가격'])
            self.spbTrQty.setValue(row['주문수량'])
            self.rbTrSell.setChecked(True if row['구분'] == '매도' else False)
            # self.leTrStrategy.setText(row['전략'])
            self.leTrCancelKey.setText(row['키'])

    # 수동 주문 ---------------------------------------------------------------------------------------------
    def gui_tr_code_changed(self, kind='tr'):
        code = self.leTrCode.text() if kind == 'tr' else self.leSimCodeDay.text() if kind == 'day' else self.leSimCode.text() if kind == 'man' else None
        if code:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            if kind == 'tr': self.leTrName.setText(name)
            elif kind == 'day': self.leSimNameDay.setText(name)
            elif kind == 'man': self.leSimName.setText(name)
            
    def gui_tr_order(self):
        kind = '매수' if self.rbTrBuy.isChecked() else '매도'
        code = self.leTrCode.text()
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
            'accno': gm.account,
            'ordtype': 1 if self.rbTrBuy.isChecked() else 2,
            'code': code,
            'quantity': qty,
            'price': price if self.rbTrLimit.isChecked() else 0,
            'hoga': '00' if self.rbTrLimit.isChecked() else '03',
            'ordno': ''
        }
        if kind == '매수':
            gm.prx.order('api', 'SetRealReg', dc.scr.화면['실시간감시'], code, '10', '1')
        else:
            if row['주문가능수량'] == 0:
                QMessageBox.warning(self, '알림', '주문가능수량이 없습니다.')
                return
            row['주문가능수량'] -= qty if row['주문가능수량'] >= qty else row['주문가능수량']
            gm.잔고목록.set(key=code, data=row)

        key = f'{code}_{kind}'
        data={'키': key, '구분': kind, '상태': '요청', '전략': '전략00', '종목코드': code, '종목명': self.leTrName.text(), '전략매도': False}
        gm.주문목록.set(key=key, data=data) 
        # 주문 전송
        gm.order_q.put(send_data)

    def gui_tr_cancel(self):
        key = self.leTrCancelKey.text()
        row = gm.주문목록.get(key=key)
        if not row:
            QMessageBox.warning(self, '알림', '주문접수목록에서 취소할 항목을 선택하세요.')
            return
        if row['상태'] != '접수':
            gm.주문목록.delete(key=key)
            return
        
        odrerno = row['주문번호']
        code = row['종목코드']

        kind = '매수' if self.rbTrBuy.isChecked() else '매도'
        rqname = f'수취{kind}'
        send_data = {
            'rqname': rqname,
            'screen': dc.scr.화면[rqname],
            'accno': gm.account,
            'ordtype': 3 if kind == '매수' else 4,
            'code': code,
            'quantity': 0,
            'price': 0,
            'hoga': '03',
            'ordno': odrerno
        }

        # 주문 전송
        gm.order_q.put(send_data)
        
    # 스크립트 표시 ---------------------------------------------------------------------------------------------
    def gui_script_show(self):
        try:
            gm.스크립트.update_table_widget(self.tblScript)
        except Exception as e:
            logging.error(f'스크립트 표시 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_select(self, row_index):
        try:
            name = self.tblScript.item(row_index, 0).text()

            script, desc = gm.스크립트.get(key=name, column=['스크립트', '설명'])

            self.ledScriptName.setText(name)
            self.txtScript.setText(script)
            self.txtScriptDesc.setText(desc)
            #self.txtScriptMsg.clear()
            self.script_edited = False

        except Exception as e:
            logging.error(f'스크립트 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_new(self):
        self.ledScriptName.setText('')
        self.txtScript.setText('')
        self.txtScriptDesc.setText('')
        #self.txtScriptMsg.clear()

    def gui_script_delete(self):
        try:
            name = self.ledScriptName.text()
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
                    gm.scm.delete_script(name)
                    #self.txtScriptMsg.clear()
                    gm.list스크립트 = gm.스크립트.get(column='스크립트명')
                    self.gui_fx채움_스크립트콤보()

        except Exception as e:
            logging.error(f'스크립트 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_script_check(self, save=False):
        try:
            script_name = self.ledScriptName.text()
            script = self.txtScript.toPlainText()
            desc = self.txtScriptDesc.toPlainText() #
            if len(script_name) == 0 or len(script) == 0:
                QMessageBox.information(self, '알림', '스크립트명과 스크립트를 입력하세요.')
                return
            if save and gm.스크립트.in_key(script_name):
                reply = QMessageBox.question(self, '확인',
                                            f'({script_name})는 이미 존재하는 스크립트입니다.\n같은 이름으로 스크립트를 저장 하시겠습니까?',
                                            QMessageBox.Yes | QMessageBox.No,
                                            QMessageBox.No)

                if reply != QMessageBox.Yes: return

            start_time = time.time()
            result = gm.scm.set_script(script_name, script, desc, kwargs={'code': '005930'}, save=save)
            exec_time = time.time() - start_time

            if result['logs']: self.txtScriptMsg.append('<검사결과>\n' + '\n'.join(result['logs'])+'\n')
            self.txtScriptMsg.verticalScrollBar().setValue(self.txtScriptMsg.verticalScrollBar().maximum())
            self.txtScriptMsg.horizontalScrollBar().setValue(0)

            if not result['error']:
                save_msg = ""
                if save:
                    save_msg = "검사 후 저장 되었습니다.\n"
                    gm.스크립트.set(key=script_name, data={'스크립트': script, '타입': result['type'], '설명': desc})
                    gm.스크립트.update_table_widget(self.tblScript)
                    gm.list스크립트 = gm.스크립트.get(column='스크립트명')
                    self.gui_fx채움_스크립트콤보()
                    self.script_edited = False
                QMessageBox.information(self, '알림', f'스크립트에 이상이 없습니다.\n{save_msg}(걸린시간={exec_time:.5f}초)\n반환값={result["result"]}')
            else:
                QMessageBox.critical(self, '에러', result['error'])
                #self.txtScriptMsg.append(result['error'])
                #self.txtScriptMsg.moveCursor(QTextCursor.End)
        except Exception as e:
            logging.error(f'스크립트 확인 오류: {type(e).__name__} - {e}', exc_info=True)

    # 실행전략 탭 ----------------------------------------------------------------------------------------
    def gui_tabs_init(self):
        try:
            전략명칭 = gm.실행전략.get('전략명칭', '') if gm.실행전략 else ''
            self.btnClearStrategy.clicked.connect(self.gui_tabs_clear)
            self.btnGetStrategy.clicked.connect(self.gui_tabs_get)
            self.btnSaveStrategy.clicked.connect(self.gui_tabs_save)
            self.ledCurrStrategy.setText(전략명칭)

        except Exception as e:
            logging.error(f'전략탭 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_clear(self):
        try:
            self.ledCurrStrategy.setText('')
        except Exception as e:
            logging.error(f'전략 초기화 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_get(self):
        try:
            condition_text = self.cbTabStrategy.currentText()
            self.ledCurrStrategy.setText(condition_text)
        except Exception as e:
            logging.error(f'전략 선택 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_tabs_save(self):
        try:
            전략명칭 = self.ledCurrStrategy.text()

            if not 전략명칭:
                QMessageBox.warning(None, '경고', '전략명칭이 입력되지 않았습니다.')
                logging.warning(f'전략명칭이 입력되지 않았습니다.')
                return

            gm.실행전략 = {
                '전략명칭': 전략명칭,
            }

            gm.admin.json_save_define_sets()
            gm.toast.toast(f'전략00 전략명칭={전략명칭} 저장 완료', duration=4000)

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
            name = self.ledStrategyName.text()
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
            name = self.ledStrategyName.text()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 전략명칭을 확인 하세요.')
                return
            if name == dc.const.BASIC_STRATEGY:
                QMessageBox.warning(self, '알림', f'{dc.const.BASIC_STRATEGY}은 삭제할 수 없습니다.')
                return
            if any([gm.매수문자열, gm.매도문자열]):
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
                    if gm.실행전략['전략명칭'] == name:
                        gm.실행전략['전략명칭'] = ''
                        self.gui_tabs_clear()
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

    # 화면 갱신 -----------------------------------------------------------------------------------------------------------------
    def gui_fx채움_계좌콤보(self):
        try:
            cb_list = [account for account in gm.list계좌콤보 if account] if gm.list계좌콤보 else []
            self.cbAccounts.clear()
            self.cbAccounts.addItems(cb_list)
            self.cbAccounts.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'계좌콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_조건콤보(self):
        try:
            cb_list = [strategy for strategy in gm.list전략콤보 if strategy] if gm.list전략콤보 else []
            self.cbCondition.clear()
            self.cbCondition.addItem(dc.const.NON_STRATEGY)  # 선택없음 추가
            self.cbCondition.addItems(cb_list)
            self.cbCondition.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'조건콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_스크립트콤보(self):
        try:
            cb_list = [script for script in gm.list스크립트 if script] if gm.list스크립트 else []
            self.cbScript.clear()
            self.cbScript.addItems(cb_list)
            self.cbScript.setCurrentIndex(0)
        except Exception as e:
            logging.error(f'스크립트콤보 채움 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_fx채움_전략정의(self):
        try:
            cb_list = [name for name in gm.전략정의.get(column='전략명칭') if name] if gm.전략정의 else []
            self.cbTabStrategy.clear()
            self.cbTabStrategy.addItems(cb_list)
            self.cbTabStrategy.setCurrentIndex(0)
            if gm.전략정의:
                gm.전략정의.update_table_widget(self.tblStrategy)
        except Exception as e:
            logging.error(f'전략정의 채움 오류: {type(e).__name__} - {e}', exc_info=True)

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
            if gm.l2손익합산:
                self.gui_set_color(self.lblProfitLoss, gm.l2손익합산)
            else:
                self.lblProfitLoss.setText('0')
            if gm.잔고합산:
                row = gm.잔고합산.get(key=0)
            else:
                row = {}
            self.lblBuy.setText(f"{int(row.get('총매입금액', 0)):,}")
            self.lblAmount.setText(f"{int(row.get('총평가금액', 0)):,}")
            self.lblAssets.setText(f"{int(row.get('추정예탁자산', 0)):,}")
            self.gui_set_color(self.lblProfit, int(row.get('총평가손익금액', 0)))
            self.gui_set_color(self.lblFrofitRate, float(row.get('총수익률(%)', 0.0)))
            if gm.잔고목록:
                gm.잔고목록.update_table_widget(self.tblBalanceHeld, stretch=False)
            else:
                self.tblBalanceHeld.setColumnCount(len(dc.const.hd잔고목록['헤더']))
                self.tblBalanceHeld.setHeaderLabels(dc.const.hd잔고목록['헤더'])

            if gm.매수조건목록:
                gm.매수조건목록.update_table_widget(self.tblConditionBuy)
            else:
                self.tblConditionBuy.setColumnCount(len(dc.const.hd조건목록['헤더']))
                self.tblConditionBuy.setHeaderLabels(dc.const.hd조건목록['헤더'])

            if gm.매도조건목록:
                gm.매도조건목록.update_table_widget(self.tblConditionSell)
            else:
                self.tblConditionSell.setColumnCount(len(dc.const.hd조건목록['헤더']))
                self.tblConditionSell.setHeaderLabels(dc.const.hd조건목록['헤더'])

            if gm.주문목록:
                gm.주문목록.update_table_widget(self.tblReceiptList)    
            else:
                self.tblReceiptList.setColumnCount(len(dc.const.hd주문목록['헤더']))
                self.tblReceiptList.setHeaderLabels(dc.const.hd주문목록['헤더'])

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
        """실행전략 위젯에 표시"""
        try:
            if not gm.strategy_row: return
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

    # 시뮬레이션 데이타 ---------------------------------------------------------------------------------------------
    def gui_sim_read_day(self):
        pass

    def gui_sim_add_day(self):
        code = self.leSimCodeDay.text()
        name = self.leSimNameDay.text()
        if code:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            if name:
                self.leSimNameDay.setText(name)
        if name:
            gm.당일종목.set(key='종목코드', data={'종목코드':code, '종목명':name})
            gm.당일종목.update_table_widget(self.tblSimDaily)

    def gui_sim_del_day(self):
        try:
            code = self.leSimCodeDay.text()
            name = self.leSimNameDay.text()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 종목을 확인 하세요.')
                return
            
            if not gm.당일종목.in_key(code):
                QMessageBox.warning(self, '알림', f'{code} {name} 종목이 존재하지 않습니다.')
                return

            reply = QMessageBox.question(self, '삭제 확인',
                                        f'{code} {name} 종목을 삭제하시겠습니까?',
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 설정 삭제
                result = gm.당일종목.delete(key=code)
                if result:
                    gm.당일종목.update_table_widget(self.tblSimDaily)
                    self.gui_sim_clear_day()

        except Exception as e:
            logging.error(f'당일종목 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_sim_clear_day(self):
        self.leSimCodeDay.setText('')
        self.leSimNameDay.setText('')

    def gui_sim_daily_select(self, row_index):
        if row_index >= 0:
            data = gm.당일종목.get(row_index)
            if data:
                self.leSimCodeDay.setText(data['종목코드'])
                self.leSimNameDay.setText(data['종목명'])

    def gui_sim_add_manual(self):
        code = self.leSimCode.text()
        name = self.leSimName.text()
        if code:
            name = gm.prx.answer('api', 'GetMasterCodeName', code)
            if name:
                self.leSimName.setText(name)
        if name:
            gm.수동종목.set(key='종목코드', data={'종목코드':code, '종목명':name})
            gm.수동종목.update_table_widget(self.tblSimManual)

    def gui_sim_del_manual(self):
        try:
            code = self.leSimCode.text()
            name = self.leSimName.text()
            if not name:
                QMessageBox.warning(self, '알림', '삭제할 종목을 확인 하세요.')
                return
            
            if not gm.수동종목.in_key(code):
                QMessageBox.warning(self, '알림', f'{code} {name} 종목이 존재하지 않습니다.')
                return

            reply = QMessageBox.question(self, '삭제 확인',
                                        f'{code} {name} 종목을 삭제하시겠습니까?',
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 설정 삭제
                result = gm.수동종목.delete(key=code)
                if result:
                    gm.수동종목.update_table_widget(self.tblSimManual)
                    self.gui_sim_clear_manual()

        except Exception as e:
            logging.error(f'수동종목 삭제 오류: {type(e).__name__} - {e}', exc_info=True)

    def gui_sim_clear_manual(self):
        self.leSimCode.setText('')
        self.leSimName.setText('')

    def gui_sim_manual_select(self, row_index):
        if row_index >= 0:
            data = gm.수동종목.get(row_index)
            if data:
                self.leSimCode.setText(data['종목코드'])
                self.leSimName.setText(data['종목명'])

    # 상태 표시 -------------------------------------------------------------------------------------
    def gui_display_status(self, data=None):
        try:
            # 기본 상태바 업데이트
            now = datetime.now()
            if now > self.lbl3_update_time + timedelta(seconds=60): self.lbl3.setText('')
            self.lbl1.setText(now.strftime("%Y-%m-%d %H:%M:%S"))
            self.lbl2.setText('연결됨' if gm.connected else '끊어짐')
            self.lbl2.setStyleSheet("color: green;" if gm.connected else "color: red;")
            self.lbl4.setText(com_market_status())

            # 큐 메시지 처리
            while not gm.qwork['msg'].empty():
                data = gm.qwork['msg'].get()
                if data.order in ['주문내용', '체결내용']:
                    self.gui_display_conclusion(data.job['msg'])
                elif data.order == '검색내용':
                    self.gui_display_strategy(data.job['msg'])
                elif data.order == '스크립트':
                    self.gui_display_script(data.job['msg'])
                elif data.order == '상태바':
                    self.lbl3.setText(data.job['msg'])
                    self.lbl3_update_time = now

        except Exception as e:
            logging.error(f'{self.name} error: {type(e).__name__} - {e}', exc_info=True)

    def gui_display_script(self, msgs):
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if isinstance(msgs, list):
            for msg in msgs:
                self.txtScriptMsg.append(f"[{current_time}] {msg}")
        else:
            self.txtScriptMsg.append(f"[{current_time}] {msgs}")
        self.txtScriptMsg.moveCursor(QTextCursor.End)

    def gui_display_conclusion(self, msg):
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.txtOrder.append(f"[{current_time}] {msg}")
        self.txtOrder.moveCursor(QTextCursor.End)

    def gui_display_strategy(self, msg):
        if msg == '':
            self.txtCondition.clear()
            return
        current_time = datetime.now().strftime("%H:%M:%S")
        self.txtCondition.append(f"{current_time} {msg}")
        self.txtCondition.moveCursor(QTextCursor.End)

