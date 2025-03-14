from public import init_logger, dc, gm
from gui import GUI
from manager import Manager
from PyQt5.QtWidgets import QApplication
import logging
import time
import sys

init_logger()
class AAA:
    def __init__(self):
        self.app = None
        self.cleanup_flag = False

    def init(self):
        self.app = QApplication(sys.argv)
        args = [arg.lower() for arg in sys.argv]
        gm.config['gui_on'] = 'off' not in args
        logging.info(f"### {'GUI' if gm.config['gui_on'] else 'CONSOLE'} Mode 로 시작 합니다. ###")

    def set_proc(self):
        gm.proc['main'] = self
        gm.proc['man'] = Manager()
        gm.proc['gui'] = GUI() if gm.config['gui_on'] else None

    def show(self):
        if not gm.config['gui_on']: return
        gm.proc['gui'].gui_show()

    def run(self):
        gm.config['ready'] = True
        return self.app.exec_() if gm.config['gui_on'] else self.console_run()

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
        self.set_proc()
        self.show()
        self.run()

    def cleanup(self):
        self.app.quit()
        self.cleanup_flag = True
        logging.info("cleanup")

if __name__ == "__main__":
    try:
        logging.info(f"start {'*'*100}")
        aaa = AAA()
        exit_code = aaa.main()
    except Exception as e:
        logging.error(str(e), exc_info=e)
        exit_code = 1
    finally:
        if not aaa.cleanup_flag: aaa.cleanup()
        logging.info(f"### System Shutdown ###")
        logging.shutdown()
        exit(exit_code)
