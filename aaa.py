from gui import GUI
from admin import Admin
from threads import ProxyAdmin, RealReceiver
from public import init_logger, dc, gm, Work
from classes import Toast, ProcessModel, QMainModel, KiwoomModel
from tables import set_tables
from dbm_server import DBMServer
from api_server import APIServer
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap, QGuiApplication
from datetime import datetime
import logging
import time
import sys
import threading

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
        gm.gui_on = 'off' not in args
        gm.sim_no = 1 if 'sim1' in args else 2 if 'sim2' in args else 3 if 'sim3' in args else 0
        if 'sim' in args and gm.sim_no == 0: gm.sim_no = 1
        gm.sim_on = gm.sim_no > 0
        logging.info(f"### {'GUI' if gm.gui_on else 'CONSOLE'} Mode 로 시작 합니다. ###")
        logging.info(f"### {f'시뮬레이션 {gm.sim_no}번' if gm.sim_on else '실제 API'} 모드로 시작 합니다. ###")

    def show_splash(self):
        if not gm.gui_on: return
        gm.gui = GUI()
        if datetime.now() < datetime(2025, 12, 1):
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
        if not gm.gui_on: return
        gm.gui.gui_show()
        time.sleep(0.1)

    def ready(self):
        try:
            # 1. 프로세스 생성 및 시작
            logging.debug('메인 및 쓰레드/프로세스 생성 및 시작')
            gm.toast = Toast()
            gm.main = self
            gm.admin = Admin()
            gm.prx = QMainModel('prx', ProxyAdmin, gm.shared_qes)
            gm.prx.start()
            gm.rcv = QMainModel('rcv', RealReceiver, gm.shared_qes)
            gm.rcv.start()
            gm.api = KiwoomModel('api', APIServer, gm.shared_qes)
            gm.api.start()
            gm.dbm = ProcessModel('dbm', DBMServer, gm.shared_qes)
            gm.dbm.start()

            # 2. API/DBM 초기화
            gm.prx.order('api', 'api_init', sim_no=gm.sim_no, log_level=gm.log_level)
            gm.prx.order('dbm', 'dbm_init', gm.sim_no, gm.log_level)
            gm.prx.order('api', 'CommConnect', False)
            self.wait_login()

            # 3. GUI 초기화 먼저 (Admin 초기화 전에)
            if gm.gui_on:
                gm.gui.init()
                logging.debug('gui 초기화 완료')
                gm.qwork['gui'].put(Work(order='gui_script_show', job={}))

            # 4. Admin 초기화를 백그라운드 스레드로 실행
            def admin_init_background():
                try:
                    logging.info('[Background] Admin 초기화 시작')
                    gm.admin.init()
                    logging.info('[Background] Admin 초기화 완료')

                    # Admin 초기화 완료 후 mode_start 호출
                    gm.admin.mode_start(is_startup=True)
                    logging.info('[Background] mode_start 완료')

                except Exception as e:
                    logging.error(f'[Background] Admin 초기화 오류: {e}', exc_info=True)

            init_thread = threading.Thread(target=admin_init_background, daemon=True)
            init_thread.start()
            logging.info('Admin 초기화 백그라운드 스레드 시작')

        except Exception as e:
            logging.error(str(e), exc_info=e)
            exit(1)

    def go(self):
        if gm.gui_on: self.splash.close()
        self.show()
        if self.time_over: QTimer.singleShot(15000, self.cleanup)
        else: return self.app.exec_() if gm.gui_on else self.console_run()

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
    
    def wait_login(self):
        """로그인 대기 (aaa.py에서 이동)"""
        if gm.sim_no != 1:
            logging.debug('로그인 대기 시작')
            start_time = time.time()
            while True:
                connected = gm.prx.answer('api', 'GetConnectState') == 1
                if connected: break
                if time.time() - start_time > 90:
                    logging.error('로그인 대기 시간 초과. 종료 합니다.')
                    exit('로그인 대기 시간 초과. 종료 합니다.')
                time.sleep(0.5)
            logging.info('로그인 완료')

    def main(self):
        self.init()
        self.show_splash()
        self.set_tables()
        self.ready()
        self.go()

    def cleanup(self):
        try:
            logging.info('cleanup: 전략/스레드/프로세스 종료 시작')
            gm.admin.stg_stop() 

            # 3. 큐 정리 
            while not gm.qwork['gui'].empty(): gm.qwork['gui'].get_nowait()
            while not gm.qwork['msg'].empty(): gm.qwork['msg'].get_nowait()
            gm.qwork = None

            def close_queue(name):
                if name in gm.shared_qes:
                    for q in [gm.shared_qes[name].request, gm.shared_qes[name].result]:
                        try:
                            q.close()
                            q.join_thread()
                            #logging.debug(f'{name} {q.__class__.__name__} 큐 닫기/종료.')
                        except Exception as e:
                            logging.debug(f'큐 닫기/종료 실패 : {name} {e}')

            # 1. QThread 기반 워커들 종료 (stop/quit/wait)
            qthreads = ['rcv', 'cts', 'ctu', 'evl', 'odc', 'pri', 'prx']
            for name in qthreads:
                obj = getattr(gm, name, None)
                if obj is not None:
                    try:
                        if hasattr(obj, 'stop'): obj.stop()
                        if name == 'prx' or name == 'rcv': close_queue(name)
                        if hasattr(obj, 'quit'): obj.quit()
                        if hasattr(obj, 'wait'): obj.wait(1000)
                        logging.debug(f'{name} QThread 종료.')
                    except Exception as e:
                        logging.debug(f'{name} QThread 종료 실패: {e}')

            # 2. Process 기반 모델 종료 (stop/join)
            processes = ['dbm', 'api']
            for name in processes:
                obj = getattr(gm, name, None)
                if obj is not None:
                    try:
                        if hasattr(obj, 'stop'): obj.stop()
                        close_queue(name)
                        if hasattr(obj, 'join'): obj.join(timeout=2)
                        if obj.is_alive():
                            obj.terminate()
                            obj.join(timeout=1)
                            logging.debug(f'{name} Process 종료.')
                        else:
                            logging.debug(f'{name} Process 정상 종료.')
                    except Exception as e:
                        logging.debug(f'{name} Process 종료 실패: {e}')

            #self.collect_thread_info()
            #self._force_exit()

        except Exception as e:
            logging.error(f"Cleanup 중 에러: {str(e)}")
        finally:
            self.cleanup_flag = True
            if hasattr(self, 'app') and gm.gui_on: self.app.quit()
            logging.info("cleanup completed")

    def collect_thread_info(self):
        qthread_objs = []
        try:
            # 4. 상태 상세 출력
            logging.debug(f'cleanup : {threading.enumerate()}')
            logging.debug('==== [Thread/Timer 상태 상세 출력] ====')
            for t in threading.enumerate():
                logging.debug(f'Thread: {repr(t)} is_alive={t.is_alive()}')
            qthread_objs = []
            try:
                qthread_objs += [getattr(gm, name, None) for name in ['rcv','cts','ctu','evl','odc','pri','prx','api','dbm']]
                qthread_objs += [getattr(gm.admin, name, None) for name in ['cancel_timer','start_timer','end_timer']]
            except Exception as e:
                logging.debug(f'QThread/Timer 객체 수집 오류: {e}')

            for obj in qthread_objs:
                if obj is None: continue
                try:
                    info = f'{repr(obj)}'
                    if hasattr(obj, 'isRunning'):
                        info += f' isRunning={obj.isRunning()}'
                    if hasattr(obj, 'isFinished'):
                        info += f' isFinished={obj.isFinished()}'
                    if hasattr(obj, 'isActive'):
                        info += f' isActive={obj.isActive()}'
                    if hasattr(obj, 'is_alive'):
                        info += f' is_alive={obj.is_alive()}'
                    if hasattr(obj, 'timerId'):
                        info += f' timerId={obj.timerId()}'
                    logging.debug(info)
                except Exception as e:
                    logging.debug(f'QThread/Timer 상태 출력 오류: {e}')
            logging.debug('==== [Thread/Timer 상태 상세 출력 끝] ====')
        except Exception as e:
            logging.debug(f'QThread/Timer 객체 수집 오류: {e}')

    def _force_exit(self):
        """프로세스 강제 종료"""
        import os
        import signal
        import time
        
        try:
            # 1초 후 강제 종료
            time.sleep(3)
            logging.info(f"[Main] 프로세스 종료")
            os.kill(os.getpid(), signal.SIGTERM)
        except:
            pass

if __name__ == "__main__":
    import multiprocessing
    from public import gm
    multiprocessing.freeze_support() # 없으면 실행파일(exe)로 실행시 DBMServer멀티프로세스 생성시 프로그램 리셋되어 시작 반복 하는 것 방지
    exit_code = 0
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
