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
            gm.pro.dbm.init_db()
            gm.pro.admin.init()
            logging.debug('prepare : admin 초기화 완료')
            if gm.config.gui_on: gm.pro.gui.init()
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

    def clear_queue(self, q):
        try:
            # 큐를 비우기 전에 put 작업 중단
            q.mutex.acquire()
            q.queue.clear()
            q.all_tasks_done.notify_all()
            q.unfinished_tasks = 0
            q.mutex.release()
        except:
            pass

    def cleanup_worker(self, worker, timeout=3):
        """
        쓰레드나 프로세스를 안전하게 종료
        worker: Thread 또는 Process 객체
        timeout: 종료 대기 시간 (초)
        """
        try:
            # 프로세스인 경우
            if hasattr(worker, 'terminate'):
                try:
                    worker.terminate()  # 종료 신호 보내기
                    worker.join(timeout)  # 정상 종료 대기
                    if worker.is_alive():  # 여전히 살아있으면
                        worker.kill()  # 강제 종료
                except:
                    pass
                    
            # 쓰레드인 경우
            else:
                try:
                    if worker.is_alive():
                        worker.join(timeout)  # 정상 종료 대기
                        if worker.is_alive() and hasattr(worker, '_stop'):
                            worker._stop()  # 쓰레드 강제 종료
                except:
                    pass
        except:
            pass
        
    def cleanup(self):
        try:
            # 1. 전략 쓰레드 종료
            for t in gm.전략쓰레드: t.stop()
            for t in gm.전략쓰레드: self.cleanup_worker(t)

            # 2. API/SIM 서버 종료
            if hasattr(gm.pro, 'api'): 
                gm.pro.api.stop()
                self.cleanup_worker(gm.pro.api)

            # 3. AAA 쓰레드 종료
            if hasattr(gm.pro, 'aaa'): 
                gm.pro.aaa.stop()
                self.cleanup_worker(gm.pro.aaa)

            # 4. DBM 서버 종료
            if hasattr(gm.pro, 'dbm'): 
                gm.pro.dbm.stop()
                self.cleanup_worker(gm.pro.dbm)

            # 5. 큐 정리 (모든 쓰레드가 종료된 후)
            if hasattr(gm, 'qdict'):
                for q in gm.qdict.values():
                    if hasattr(q, 'request'): self.clear_queue(q.request)
                    if hasattr(q, 'answer'): self.clear_queue(q.answer)
                    if hasattr(q, 'reply'): self.clear_queue(q.reply)

        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            if hasattr(self, 'app'): self.app.quit()
            logging.info("cleanup completed")
            
import psutil
import threading

def force_cleanup():
    # 1. 모든 쓰레드 강제 종료
    for thread in threading.enumerate():
        if thread.name != 'MainThread':
            if hasattr(thread, '_stop'):
                thread._stop()
    
    # 2. 모든 열린 파일 닫기
    current_process = psutil.Process()
    for file in current_process.open_files():
        try:
            import os
            os.close(file.fd)
        except:
            pass
    
    # 3. 남은 프로세스 정리
    for child in current_process.children(recursive=True):
        try:
            child.terminate()
            child.wait(timeout=3)
        except:
            child.kill()
    
    # 4. 메모리 정리
    import gc
    gc.collect()

def show_detailed_threads():
    try:
        active_threads = threading.enumerate()
        logging.debug("\n=== 쓰레드 상세 정보 ===")
        
        for thread in active_threads:
            try:
                logging.debug(f"\n쓰레드 이름: {thread.name}")
                logging.debug(f"쓰레드 ID: {thread.ident}")
                logging.debug(f"데몬 여부: {thread.daemon}")
                logging.debug(f"활성 상태: {thread.is_alive()}")
                
                # 타겟 함수 정보
                try:
                    if hasattr(thread, '_target'):
                        target = thread._target
                        target_name = target.__name__ if target and hasattr(target, '__name__') else str(target)
                        logging.debug(f"타겟 함수: {target_name}")
                except:
                    logging.debug("타겟 함수: 확인 불가")
                
                # 인자 정보
                try:
                    if hasattr(thread, '_args'):
                        logging.debug(f"인자: {repr(thread._args)}")
                except:
                    logging.debug("인자: 확인 불가")
                
                # 키워드 인자 정보
                try:
                    if hasattr(thread, '_kwargs'):
                        logging.debug(f"키워드 인자: {repr(thread._kwargs)}")
                except:
                    logging.debug("키워드 인자: 확인 불가")
                
            except Exception as e:
                logging.debug(f"쓰레드 정보 수집 중 오류: {str(e)}")
                
    except Exception as e:
        logging.debug(f"쓰레드 분석 중 오류 발생: {str(e)}")

def show_remaining_resources():
    # 현재 프로세스 정보
    current_process = psutil.Process()
    
    # 활성 쓰레드 
    active_threads = threading.enumerate()
    logging.debug("\n=== 남아있는 쓰레드 ===")
    for thread in active_threads:
        logging.debug(f"쓰레드: {thread.name}, 상태: {'alive' if thread.is_alive() else 'dead'}")
    
    # 자식 프로세스
    children = current_process.children(recursive=True)
    logging.debug("\n=== 남아있는 프로세스 ===")
    for child in children:
        logging.debug(f"프로세스: {child.name()}, PID: {child.pid}")
    
    # 현재 프로세스의 열린 파일들
    logging.debug("\n=== 열린 파일 ===")
    for file in current_process.open_files():
        logging.debug(f"파일: {file.path}")
    
    # 메모리 사용량
    logging.debug(f"\n=== 메모리 사용량 ===")
    logging.debug(f"메모리: {current_process.memory_info().rss / 1024 / 1024:.2f} MB")

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
        show_remaining_resources()
        show_detailed_threads()
        logging.info(f"{'#'*10} LIBERANIMO End {'#'*10}")
        logging.shutdown()
        print("sys.exit(exit_code) 직전")
        sys.exit(exit_code)
