from public import init_logger, dc, gm
from classes import Toast, AnswerThread
from server_api import APIServer
from server_sim import SIMServer
from gui import GUI
from admin import Admin
from server_dbm import DBMServer
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
import multiprocessing as mp
import logging
import time
import sys
import pythoncom
import queue
import signal
import threading
import traceback

init_logger()

class Main:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
        gm.main = self
        gm.admin = Admin()
        gm.config.gui_on = 'off' not in args
        gm.config.sim_on = 'sim' in args    
        logging.info(f"### {'GUI' if gm.config.gui_on else 'CONSOLE'} Mode 로 시작 합니다. ###")

    def show_splash(self):
        if not gm.config.gui_on: return
        splash_pix = QPixmap(400, 200)
        splash_pix.fill(Qt.blue)          
        self.splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        self.splash.showMessage("로딩 중... 잠시만 기다려 주세요", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
        self.splash.show()

    def set_proc(self):
        try:
            gm.api = APIServer('api') if not gm.config.sim_on else SIMServer('sim')
            gm.api.CommConnect(block=False)
            gm.toast = Toast()
            gm.work_aaaq = queue.Queue()
            gm.answer_aaaq = queue.Queue()
            gm.aaa = AnswerThread(name='aaa', work_q=gm.work_aaaq, answer_q=gm.answer_aaaq, cls=gm.admin)
            gm.aaa.start()
            logging.debug('aaa 쓰레드 시작')
            gm.gui = GUI() if gm.config.gui_on else None
            gm.work_dbmq = mp.Queue()
            gm.answer_dbmq = mp.Queue()
            #gm.dbm = DBMServer('dbm', gm.work_dbmq, gm.answer_dbmq)
            logging.debug('api 쓰레드 생성 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def show(self):
        if not gm.config.gui_on: return
        gm.gui.gui_show()

    def prepare(self):
        try:
            logging.debug('prepare : 로그인 대기 시작')
            while not gm.api.connected:
                pythoncom.PumpWaitingMessages()
                time.sleep(1)
            logging.debug(f'***** {gm.api.name.upper()} connected *****')
            #gm.dbm.start()
            #gm.dbm.init_db()
            gm.admin.init()
            logging.debug('prepare : admin 초기화 완료')
            if gm.config.gui_on: gm.gui.init()
            logging.debug('prepare : gui 초기화 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def run(self):
        if gm.config.gui_on: self.splash.close()
        gm.admin.trade_start()
        return self.app.exec_() if gm.config.gui_on else self.console_run()

    def console_run(self):
        while True:
            try:
                cmd = input().strip().lower()
                if cmd == 'q':
                    confirm = input("정말 종료하시겠습니까? (y/n): ").strip().lower()
                    if confirm == 'y':
                        break
            except KeyboardInterrupt:
                continue
            time.sleep(0.01)
        return 0
    
    def main(self):
        self.init()
        self.show_splash()
        self.set_proc()
        self.show()
        self.prepare()
        self.run()

    def cleanup(self):
        try:
            # 1. 전략 쓰레드 종료
            for t in gm.전략쓰레드: t.stop()

            # 2. API/SIM 서버 종료
            if hasattr(gm.pro, 'api'): 
                gm.api.stop()

            # 3. AAA 쓰레드 종료
            if hasattr(gm.pro, 'aaa'): 
                gm.aaa.stop()

            # 4. DBM 서버 종료
            # if hasattr(gm.pro, 'dbm'): 
            #     gm.dbm.stop()
            #     self.cleanup_worker(gm.dbm)

        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            if hasattr(self, 'app'): self.app.quit()
            logging.info("cleanup completed")
            
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    try:
        logging.info(f"{'#'*10} LIBERANIMO logiacl intelligence enhanced robo aotonomic investment management operations START {'#'*10}")
        main = Main()
        exit_code = main.main()
        logging.info(f"{'#'*10} System Shutdown {'#'*10}")
    except Exception as e:
        logging.error(str(e), exc_info=e)
        exit_code = 1
    finally:
        if not main.cleanup_flag: main.cleanup()
        logging.info(f"{'#'*10} LIBERANIMO End {'#'*10}")
        logging.shutdown()
        sys.exit(exit_code)
