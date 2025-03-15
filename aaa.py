from public import init_logger, dc, gm
from classes import Toast
from gui import GUI
from admin import Admin
from server_sim import SIMServer
from server_api import APIServer
from PyQt5.QtWidgets import QApplication
import logging
import time
import sys

init_logger()
class Main:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
        gm.config.gui_on = 'off' not in args
        logging.info(f"### {'GUI' if gm.config.gui_on else 'CONSOLE'} Mode 로 시작 합니다. ###")

    def set_proc(self):
        gm.toast = Toast()
        gm.pro.api = SIMServer(name='sim', qdict=gm.qdict, cls='sim') if gm.config.sim_on else APIServer(name='api', qdict=gm.qdict, cls='api')
        gm.pro.api.api_login(block=True)
        gm.pro.main = self
        gm.pro.admin = Admin()
        gm.pro.gui = GUI() if gm.config.gui_on else None

    def show(self):
        if not gm.config.gui_on: return
        gm.pro.gui.gui_show()

    def prepare(self):
        while not gm.pro.api.connected:
            time.sleep(0.01)
        logging.debug(f'{gm.pro.api.name} connected')
        gm.pro.admin.init()
        gm.pro.gui.init()

    def run(self):
        gm.config.ready = True
        return self.app.exec_() if gm.config.gui_on else self.console_run()

    def ask_use_sim(self):
        confirm = input("시뮬레이션을 사용 하시겠습니까? (y/n): ").strip().lower()
        gm.config.sim_on = True if confirm == 'y' else False

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
        self.ask_use_sim()
        self.init()
        self.set_proc()
        self.show()
        self.prepare()
        self.run()

    def cleanup(self):
        self.app.quit()
        self.cleanup_flag = True
        logging.info("cleanup")

if __name__ == "__main__":
    try:
        logging.info(f"start {'*'*100}")
        main = Main()
        exit_code = main.main()
    except Exception as e:
        logging.error(str(e), exc_info=e)
        exit_code = 1
    finally:
        if not main.cleanup_flag: main.cleanup()
        logging.info(f"### System Shutdown ###")
        logging.shutdown()
        exit(exit_code)
