from admin import Admin
from gui import GUI
from server_api import APIServer
from server_sim import SIMServer
from server_dbm import DBMServer
from public import init_logger, gm
from classes import Toast, la
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
import logging
import time
import sys
import pythoncom

init_logger()

class Main:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
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
            gm.toast = Toast()
            gm.main = self
            gm.admin = Admin()
            gm.api = APIServer('api') if not gm.config.sim_on else SIMServer('api')
            gm.gui = GUI() if gm.config.gui_on else None
            la.register('api', gm.api, use_thread=False)
            la.work('api', 'CommConnect', block=False)
            la.register('aaa', gm.admin, use_thread=False)
            la.register('dbm', DBMServer, use_process=True) # 직렬화 문제로 인스턴스를 넘기지 못함, 클래스를 넘겨서 프로세스내에서 인스턴스 생성
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def show(self):
        if not gm.config.gui_on: return
        gm.gui.gui_show()

    def prepare(self):
        try:
            logging.debug('prepare : 로그인 대기 시작')
            while True:
                pythoncom.PumpWaitingMessages()
                if la.answer('api', 'api_connected'): break
                time.sleep(0.1)
            logging.debug(f'***** {gm.api.name.upper()} connected *****')
            la.work('aaa', 'init')
            logging.debug('prepare : admin 초기화 완료')
            if gm.config.gui_on: gm.gui.init()
            logging.debug('prepare : gui 초기화 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def run(self):
        if gm.config.gui_on: self.splash.close()
        la.work('aaa', 'trade_start')
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
            la.is_shutting_down = True
            for t in gm.전략쓰레드:
                la.stop_worker(t.name)
            la.stop_worker('api')
            la.stop_worker('dbm')
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
