from gui import GUI
from admin import Admin, OrderManager, ProxyAdmin, OrderCommander, DummyClass, ChartSetter, ChartUpdater
from strategy import EvalStrategy
from public import init_logger, dc, gm, Work
from classes import Toast, set_tables, MainModel, ThreadModel, ProcessModel, QData
from dbm_server import DBMServer
from api_server import APIServer
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap, QGuiApplication
import logging
import time
import sys
from datetime import datetime
from strategy import Strategy

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
        gm.gui = GUI()
        if datetime.now() < datetime(2025, 6, 30):
            splash_pix = QPixmap(dc.fp.image_file)
            screen_width = 800
            screen_height = 400
            resized_pixmap = splash_pix.scaled(screen_width, screen_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.splash = QSplashScreen(resized_pixmap, Qt.WindowStaysOnTopHint)
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
            self.splash.show() # showFullScreen()  # 화면 전체로 표시
            self.time_over = True

    def set_tables(self):
        set_tables()

    def show(self):
        if not gm.config.gui_on: return
        gm.gui.gui_show()
        time.sleep(0.1)

    def set_proc(self):
        try:
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작 ...')
            gm.main = self
            gm.toast = Toast()
            gm.dmy = MainModel('dmy', DummyClass, gm.shared_qes)
            gm.dmy.start()
            gm.admin = MainModel('admin', Admin, gm.shared_qes)
            gm.admin.start()
            gm.api = ProcessModel('api', APIServer, gm.shared_qes)
            gm.api.start()
            gm.dmy.order('api', 'api_init', gm.config.sim_no)
            gm.dmy.order('api', 'CommConnect', False)
            gm.dbm = ProcessModel('dbm', DBMServer, gm.shared_qes)
            gm.dbm.start()
            gm.ctu = ThreadModel('ctu', ChartUpdater, gm.shared_qes)
            gm.ctu.start()
            gm.cts = ThreadModel('cts', ChartSetter, gm.shared_qes)
            gm.cts.start()
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def prepare(self):
        try:
            if gm.config.sim_no != 1:
                logging.debug('prepare : 로그인 대기 시작')
                while True:
                    # api_connected는 여기 외에 사용 금지
                    connected = gm.dmy.answer('api', 'api_connected')
                    if connected: break
                    logging.debug(f"로그인 대기 중: {connected}")
                    time.sleep(0.5)
            gm.dmy.order('api', 'set_tickers')
            gm.dmy.order('admin', 'init')
            while not gm.admin_init: time.sleep(0.1)
            
            logging.debug('prepare : admin 초기화 완료')
            if gm.config.gui_on: gm.gui.init()
            logging.debug('prepare : gui 초기화 완료')

        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def trade_start(self):
        logging.debug('trade_start')
        gm.odr = ThreadModel('odr', OrderManager, gm.shared_qes)
        gm.odc = ThreadModel('odc', OrderCommander, gm.shared_qes)
        gm.stg = ThreadModel('stg', Strategy, gm.shared_qes)
        gm.evl = ThreadModel('evl', EvalStrategy, gm.shared_qes)
        gm.prx = MainModel('prx', ProxyAdmin, gm.shared_qes)
        gm.qwork['gui'].put(Work(order='gui_script_show', job={}))
        gm.prx.start()
        gm.odr.start()
        gm.odc.start()
        gm.stg.start()
        gm.config.ready = True
        gm.dmy.order('cts', 'latch_off')
        gm.dmy.order('ctu', 'latch_off')
        gm.dmy.order('odc', 'latch_off')

    def run(self):
        if gm.config.gui_on: 
            self.splash.close()
        if self.time_over:
            QTimer.singleShot(15000, self.cleanup)
        else:   
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
        self.set_tables()
        self.set_proc()
        self.prepare()
        self.show()
        self.trade_start()
        self.run()

    def cleanup(self):
        try:
            if hasattr(gm, 'admin') and gm.admin:
                gm.dmy.order('admin', 'cdn_fx중지_전략매매')
                
            shutdown_list = ['cts', 'api', 'dbm']
            for name in shutdown_list:
                gm.shared_qes[name].request.put(QData(sender=name, method='stop'))
            
            # 프로세스 강제 종료
            self._force_exit()
            
        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            if hasattr(self, 'app'): self.app.quit()
            logging.info("cleanup completed")

    def _force_exit(self):
        """프로세스 강제 종료"""
        import os
        import signal
        import time
        
        try:
            # 1초 후 강제 종료
            time.sleep(1)
            logging.info(f"[Main] 프로세스 강제 종료")
            os.kill(os.getpid(), signal.SIGTERM)
        except:
            pass

if __name__ == "__main__":
    import multiprocessing
    from public import gm
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    try:
        logging.info(f"{'#'*10} LIBERANIMO logiacl intelligence enhanced robo aotonomic investment management operations START {'#'*50}")
        main = Main()
        exit_code = main.main()
        logging.info(f"{'#'*10} System Shutdown {'#'*10}")

    except Exception as e:
        logging.error(str(e), exc_info=e)
        exit_code = 1
    finally:
        if not main.cleanup_flag: main.cleanup()
        logging.info(f"{'#'*10} LIBERANIMO End {'#'*50}")
        # 로깅 종료는 가장 마지막에 수행
        logging.shutdown()
        sys.exit(exit_code)
