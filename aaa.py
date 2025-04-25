from public import init_logger, dc, gm
from admin import Admin
from gui import GUI
from server_api import APIServer
from server_sim import SIMServer
from server_dbm import DBMServer
from classes import Toast, la, ProcessManager
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap, QGuiApplication
import logging
import time
import sys
import pythoncom
from datetime import datetime
import os

init_logger()

class Main:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False
        self.time_over = False

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
        gm.config.gui_on = 'off' not in args
        gm.config.sim_on = 'sim' in args            # 시뮬레이션 (전체)
        gm.config.sim_real_only = 'sim2' in args    # 시뮬레이션 (실시간처리만)
        if gm.config.sim_real_only:
            gm.config.sim_on = True
        logging.info(f"### {'GUI' if gm.config.gui_on else 'CONSOLE'} Mode 로 시작 합니다. ###")

    def show_splash(self):
        if not gm.config.gui_on: return
        #splash_pix = QPixmap(400, 200)
        #splash_pix.fill(Qt.blue)          
        #self.splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        #self.splash.showMessage("로딩 중... 잠시만 기다려 주세요", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
        #self.splash.show()
        if datetime.now() < datetime(2025, 4, 30):
            splash_pix = QPixmap(dc.fp.image_file)
            screen_width = 800
            screen_height = 400
            resized_pixmap = splash_pix.scaled(screen_width, screen_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.splash = QSplashScreen(resized_pixmap, Qt.WindowStaysOnTopHint)
            self.splash.showMessage("로딩 중... 잠시만 기다려 주세요...", Qt.AlignCenter | Qt.AlignBottom, Qt.red)
            self.splash.setStyleSheet("color: rgba(255, 0, 0, 0); font-size: 20px; font-weight: bold;")
            self.splash.show()
        else:
            # 모니터 해상도 가져오기
            screen = QGuiApplication.primaryScreen()
            screen_size = screen.size()
            screen_width = screen_size.width()
            screen_height = screen_width / 2 # screen_size.height()

            # PNG 파일 로드 및 크기 맞추기
            pixmap = QPixmap(dc.fp.image_file)
            resized_pixmap = pixmap.scaled(screen_width, screen_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 스플래시 화면 설정
            self.splash = QSplashScreen(resized_pixmap, Qt.WindowStaysOnTopHint)
            self.splash.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)
            self.splash.showMessage("로딩 중... 잠시만 기다려 주세요", Qt.AlignCenter | Qt.AlignBottom, Qt.red)
            self.splash.setStyleSheet("color: rgba(255, 0, 0, 0); font-size: 30px; font-weight: bold;")
            self.splash.show() # showFullScreen()  # 화면 전체로 표시
            self.time_over = True

    def set_proc(self):
        try:
            gm.pm = ProcessManager()
            gm.toast = Toast()
            gm.main = self
            gm.admin = Admin()
            gm.api = APIServer('api') if not gm.config.sim_on else SIMServer('api')
            gm.gui = GUI() if gm.config.gui_on else None
            la.register('api', gm.api, use_thread=False)
            la.work('api', 'CommConnect', block=False)
            la.register('admin', gm.admin, use_thread=False)
            gm.admin_proxy = gm.pm.register_process('admin', gm.admin)
            gm.dbm_proxy = gm.pm.register_process('dbm', DBMServer)
            gm.dbm_proxy.set_admin_proxy()
            #la.register('dbm', DBMServer, use_process=True) # 직렬화 문제로 인스턴스를 넘기지 못함, 클래스를 넘겨서 프로세스내에서 인스턴스 생성
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
            if gm.config.sim_real_only:
                la.work('api', 'set_tickers')
            la.work('admin', 'init')
            logging.debug('prepare : admin 초기화 완료')
            if gm.config.gui_on: gm.gui.init()
            logging.debug('prepare : gui 초기화 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def run(self):
        if gm.config.gui_on: 
            self.splash.close()
        if self.time_over:
            QTimer.singleShot(15000, self.cleanup)
        else:   
            la.work('admin', 'trade_start')
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
            #la.stop_worker('dbm')
            gm.pm.stop_process('dbm')
            for t in gm.전략쓰레드:
                la.stop_worker(t.name)
            la.stop_worker('api')
        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            if hasattr(self, 'app'): self.app.quit()
            logging.info("cleanup completed")
            
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    #from classes import init_process_manager
    #pm = init_process_manager()
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
