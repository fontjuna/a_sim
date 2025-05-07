from public import init_logger, dc, gm
from admin import Admin
from gui import GUI
from chart import ctdt
from api_server import APIServer
from dbm_server import DBMServer
from classes import Toast, la, IPCManager
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap, QGuiApplication
import logging
import time
import sys
import pythoncom
from datetime import datetime

init_logger()
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """예상치 못한 예외에 대한 글로벌 핸들러"""
    # 로그에만 기록하고 GUI 팝업 방지
    logging.error("미처리 예외:", exc_info=(exc_type, exc_value, exc_traceback))

class Main:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False
        self.time_over = False
        sys.excepthook = _global_exception_handler

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
        gm.config.gui_on = 'off' not in args
        gm.config.sim_no = 1 if 'sim1' in args else 2 if 'sim2' in args else 3 if 'sim3' in args else 0
        if 'sim' in args and gm.config.sim_no == 0: gm.config.sim_no = 1
        gm.config.sim_on = gm.config.sim_no > 0
        logging.info(f"### {'GUI' if gm.config.gui_on else 'CONSOLE'} Mode 로 시작 합니다. ###")
        logging.info(f"### {f'시뮬레이션 {gm.config.sim_no}번' if gm.config.sim_on else '실제 API'} 모드로 시작 합니다. ###")

    def show_splash(self):
        if not gm.config.gui_on: return
        #splash_pix = QPixmap(400, 200)
        #splash_pix.fill(Qt.blue)          
        #self.splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        #self.splash.showMessage("로딩 중... 잠시만 기다려 주세요", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
        #self.splash.show()
        if datetime.now() < datetime(2025, 5, 30):
            splash_pix = QPixmap(dc.fp.image_file)
            screen_width = 800
            screen_height = 400
            resized_pixmap = splash_pix.scaled(screen_width, screen_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.splash = QSplashScreen(resized_pixmap, Qt.WindowStaysOnTopHint)
            #self.splash.showMessage("로딩 중... 잠시만 기다려 주세요...", Qt.AlignCenter | Qt.AlignBottom, Qt.red)
            #self.splash.setStyleSheet("color: rgba(255, 0, 0, 0); font-size: 20px; font-weight: bold;")
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
            #self.splash.showMessage("로딩 중... 잠시만 기다려 주세요", Qt.AlignCenter | Qt.AlignBottom, Qt.red)
            #self.splash.setStyleSheet("color: rgba(255, 0, 0, 0); font-size: 30px; font-weight: bold;")
            self.splash.show() # showFullScreen()  # 화면 전체로 표시
            self.time_over = True

    def set_proc(self):
        try:
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
            gm.toast = Toast()
            gm.ipc = IPCManager()
            gm.main = self
            gm.admin = Admin()
            la.register('admin', gm.admin, use_thread=False)
            gm.gui = GUI() if gm.config.gui_on else None

            gm.ipc.start_api_process(APIServer) # if not gm.config.sim_on else SIMServer)
            gm.ipc.start_dbm_process(DBMServer)
            gm.ipc.start_admin_listener(gm.admin) # 위에 두개 먼저 실행 후 이 코드 실행
            gm.ipc.work('api', 'api_init')

        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def login(self):
        # 모든 설정이 완료된 후 CommConnect 호출
        gm.ipc.work('api', 'CommConnect', block=False, sim_no=gm.config.sim_no)

    def show(self):
        if not gm.config.gui_on: return
        gm.gui.gui_show()
        #time.sleep(1)

    def prepare(self):
        try:
            logging.debug('prepare : 로그인 대기 시작')
            while True:
                # api_connected는 여기 외에 사용 금지
                if not gm.ipc.answer('api', 'api_connected'): time.sleep(0.5)
                else: break

            if gm.config.sim_on: gm.ipc.work('api', 'set_tickers', gm.config.sim_no)

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
        self.login()
        self.prepare()
        self.show()
        self.run()

    def cleanup(self):
        try:
            la.is_shutting_down = True
            if hasattr(gm, 'ipc') and gm.ipc:
                gm.ipc.prepare_shutdown()
                try:
                    gm.ipc.queues['admin_to_api'].put({ 'command': 'prepare_shutdown' })
                    gm.ipc.queues['admin_to_dbm'].put({ 'command': 'prepare_shutdown' })
                    gm.ipc.queues['admin_to_api'].put({ 'command': 'stop' })
                    gm.ipc.queues['admin_to_dbm'].put({ 'command': 'stop' })
                except Exception as e:
                    pass
                finally:
                    time.sleep(0.5)
            
            for t in gm.전략쓰레드:
                la.stop_worker(t.name)
            # la.stop_worker('api')
            if hasattr(gm, 'ipc') and gm.ipc:
                gm.ipc.stop_api_process()
                gm.ipc.stop_dbm_process()
        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            ctdt.clean_up()
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
        # 로깅 종료는 가장 마지막에 수행
        logging.shutdown()
        sys.exit(exit_code)
