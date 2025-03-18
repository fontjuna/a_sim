from public import init_logger, dc, gm
from classes import Toast, Work, ModelThread
from gui import GUI
from admin import Admin
from server_sim import SIMServer
from server_api import APIServer
from server_dbm import DBMServer
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
        gm.pro.main = self
        gm.pro.admin = Admin()
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
            gm.pro.aaa = ModelThread(name='aaa', qdict=gm.qdict, cls=gm.pro.admin)
            gm.pro.aaa.start()
            logging.debug('aaa 쓰레드 시작')
            gm.pro.gui = GUI() if gm.config.gui_on else None
            gm.pro.dbm = DBMServer(name='dbm', qdict=gm.qdict)
            gm.pro.api = APIServer(name='api', qdict=gm.qdict, cls=gm.pro.admin) if not gm.config.sim_on else SIMServer(name='sim', qdict=gm.qdict, cls=gm.pro.admin)
            logging.debug('api 쓰레드 생성 완료')
            gm.pro.api.CommConnect(block=False)
            logging.debug('CommConnect 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def show(self):
        if not gm.config.gui_on: return
        gm.pro.gui.gui_show()

    def prepare(self):
        try:
            logging.debug('prepare : 로그인 대기 시작')
            while not gm.pro.api.connected: pythoncom.PumpWaitingMessages()
            logging.debug(f'***** {gm.pro.api.name.upper()} connected *****')
            gm.pro.dbm.start()
            gm.pro.admin.init()
            logging.debug('prepare : admin 초기화 완료')
            gm.pro.gui.init()
            logging.debug('prepare : gui 초기화 완료')
        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def run(self):
        if gm.config.gui_on: self.splash.close()
        gm.pro.admin.trade_start()
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
        gm.pro.api.stop()
        gm.pro.dbm.stop()
        gm.pro.dbm.join(timeout=1)        
        gm.pro.aaa.stop()
        gm.pro.aaa.wait()
        gm.pro.admin.cdn_fx중지_전략매매()

        # Python의 Queue는 내부적으로 데몬 쓰레드인 QueueFeederThread를 사용합니다. 
        # 큐에 데이터가 남아있으면 이 쓰레드가 계속 실행 상태로 남아있어 프로그램이 완전히 종료되지 않습니다.
        for q in gm.qdict.values():
            while not q.request.empty():
                q.request.get()
            while not q.answer.empty():
                q.answer.get()
            while not q.reply.empty():
                q.reply.get()

        self.cleanup_flag = True 
        self.app.quit()
        logging.info("cleanup")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    try:
        logging.info(f"{'*'*10} LIBERANIMO logiacl intelligence enhanced robo aotonomic investment management operations START{'*'*10}")
        main = Main()
        exit_code = main.main()
        logging.info("{'*'*10} LIBERANIMO End {'*'*10}")
    except Exception as e:
        logging.error(str(e), exc_info=e)
        exit_code = 1
    finally:
        if not main.cleanup_flag: main.cleanup()
        logging.info(f"### System Shutdown ###")
        logging.shutdown()
        exit(exit_code)
