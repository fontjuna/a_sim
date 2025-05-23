from public import dc, get_path, save_json, load_json
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
import multiprocessing as mp
import threading
import copy
import time
import logging
import uuid
import queue
import os
from datetime import datetime

# 워커 쓰레드 클래스
class WorkerThread(QThread):
    taskReceived = pyqtSignal(str, str, object, object)
    
    def __init__(self, name, target):
        super().__init__()
        self.name = name
        self.target = target
        self.running = True
        
        # 이 쓰레드에서 처리할 시그널 연결
        self.taskReceived.connect(self._processTask)
    
    def run(self):
        logging.debug(f"{self.name} 쓰레드 시작")
        self.exec_()  # 이벤트 루프 시작
        logging.debug(f"{self.name} 쓰레드 종료")

    def _get_var(self, var_name):
        """타겟 객체의 변수 값을 가져오는 내부 메서드"""
        try:
            return getattr(self.target, var_name, None)
        except Exception as e:
            logging.error(f"변수 접근 오류: {e}", exc_info=True)
            return None

    def _set_var(self, var_name, value):
        """타겟 객체의 변수 값을 설정하는 내부 메서드"""
        try:
            setattr(self.target, var_name, value)
            return True
        except Exception as e:
            logging.error(f"변수 설정 오류: {e}", exc_info=True)
            return None
            
    @pyqtSlot(str, str, object, object)
    def _processTask(self, task_id, method_name, task_data, callback):
        # 메서드 찾기
        method = getattr(self.target, method_name, None)
        if not method:
            if callback:
                callback(None)
            return
        
        # 메서드 실행
        args, kwargs = task_data
        try:
            result = method(*args, **kwargs)
            if callback:
                callback(result)
        except Exception as e:
            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
            if callback:
                callback(None)

# 워커 관리자
class WorkerManager:
    def __init__(self):
        self.workers = {}  # name -> worker thread
        self.targets = {}  # name -> target object

        self.manager = None
        self.task_queues = {} # name -> manager.list
        self.result_dicts = {} # name -> manager.dict

        self.is_shutting_down = False

    def register(self, name, target_class=None, use_thread=True):
        if use_thread:
            target = target_class() if isinstance(target_class, type) else target_class
            worker = WorkerThread(name, target)
            worker.start()
            self.workers[name] = worker
        else:
            target = target_class() if isinstance(target_class, type) else target_class
            self.targets[name] = target
        return self

    def stop_worker(self, worker_name):
        """워커 중지"""
        # 쓰레드 워커 중지
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            worker.running = False
            worker.quit()  # 이벤트 루프 종료
            worker.wait(1000)  # 최대 1초간 대기
            self.workers.pop(worker_name, None)
            logging.debug(f"워커 종료: {worker_name} (쓰레드)")
            return True
            
        # 메인 쓰레드 워커 제거
        elif worker_name in self.targets:
            self.targets.pop(worker_name, None)
            logging.debug(f"워커 제거: {worker_name} (메인 쓰레드)")
            return True
            
        return False

    def stop_all(self):
        """모든 워커 중지"""
        # 모든 쓰레드 워커 중지
        self.is_shutting_down = True

        logging.info("모든 워커 중지 중...")
        for name in list(self.workers.keys()):
            self.stop_worker(name)
            
        # 모든 메인 쓰레드 워커 제거
        self.targets.clear()
        
        # Manager 종료
        if self.manager is not None:
            try:
                self.manager.shutdown()
            except:
                pass
            self.manager = None

        logging.debug("모든 워커 종료")
        
    def get_var(self, worker_name, var_name):
        """워커의 변수 값을 가져오는 함수"""
        if self.is_shutting_down:
            return None
            
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return None
            
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            try:
                return getattr(target, var_name, None)
            except Exception as e:
                logging.error(f"변수 접근 오류: {e}", exc_info=True)
                return None
                
        # 쓰레드로 실행하는 경우
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            return self.answer(worker_name, '_get_var', var_name)
            
        return None
        
    def set_var(self, worker_name, var_name, value):
        """워커의 변수 값을 설정하는 함수"""
        if self.is_shutting_down:
            return False
            
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return False
            
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            try:
                setattr(target, var_name, value)
                return True
            except Exception as e:
                logging.error(f"변수 설정 오류: {e}", exc_info=True)
                return False
                
        # 쓰레드로 실행하는 경우
        if worker_name in self.workers:
            return self.answer(worker_name, '_set_var', var_name, value) is not None
            
        return False
        
    def answer(self, worker_name, method_name, *args, **kwargs):
        """동기식 함수 호출"""
        if self.is_shutting_down:
            return None
        
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return None
        
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            method = getattr(target, method_name, None)
            if not method:
                return None
            try:
                return method(*args, **kwargs)
            except Exception as e:
                logging.error(f"직접 호출 오류: {e}", exc_info=True)
                return None
        
        # 쓰레드로 실행하는 경우
        worker = self.workers[worker_name]
        result = [None]
        event = threading.Event()
        
        def callback(res):
            result[0] = res
            event.set()
        
        # 시그널로 태스크 전송
        task_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        worker.taskReceived.emit(task_id, method_name, task_data, callback)
        
        # 결과 대기
        if not event.wait(3.0):
            logging.warning(f"호출 타임아웃: {worker_name}.{method_name}")
            return None
        
        return result[0]

    def work(self, worker_name, method_name, *args, callback=None, **kwargs):
        """비동기 함수 호출"""
        if self.is_shutting_down:
            return None
        
        # 워커 찾기
        if worker_name not in self.workers and worker_name not in self.targets:
            logging.error(f"워커 없음: {worker_name}")
            return False
        
        # 메인 쓰레드에서 실행하는 경우
        if worker_name in self.targets:
            target = self.targets[worker_name]
            method = getattr(target, method_name, None)
            if not method:
                return False
            try:
                result = method(*args, **kwargs)
                if callback:
                    callback(result)
                return True
            except Exception as e:
                logging.error(f"직접 호출 오류: {e}", exc_info=True)
                if callback:
                    callback(None)
                return False
        
        # 쓰레드로 실행하는 경우
        worker = self.workers[worker_name]
        task_id = str(uuid.uuid4())
        task_data = (args, kwargs)
        worker.taskReceived.emit(task_id, method_name, task_data, callback)
        return True
la = WorkerManager()

# IPC(프로세스 간 통신) 관리자
class IPCManager:
   def __init__(self):
      self.manager = mp.Manager()
      self.queues = {}  # name -> Queue
      self.result_dict = self.manager.dict()  # id -> result
      self.callbacks = {}  # id -> callback function
      self.dbm_process = None
      self.shutting_down = False
   
   def create_queue(self, name):
      """특정 이름의 큐 생성"""
      if name not in self.queues:
         self.queues[name] = mp.Queue()
      return self.queues[name]
   
   def get_queue(self, name):
      """큐 가져오기"""
      if name not in self.queues:
         self.create_queue(name)
      return self.queues[name]
   
   def prepare_shutdown(self):
      self.shutting_down = True
      logging.info("종료 준비 중 ...")
   
   def start_dbm_process(self, dbm_class):
      """DBM 프로세스 시작"""
      if self.dbm_process is not None:
         logging.warning("DBM 프로세스가 이미 실행 중입니다")
         return
      
      # 필요한 큐 생성
      self.create_queue('admin_to_dbm')
      self.create_queue('dbm_to_admin')
      
      # 프로세스 시작
      self.dbm_process = mp.Process(
         target=dbm_worker,
         args=(dbm_class, self.queues['admin_to_dbm'], 
               self.queues['dbm_to_admin'], self.result_dict),
         daemon=True
      )
      self.dbm_process.start()
      logging.info(f"DBM 프로세스 시작됨 (PID: {self.dbm_process.pid})")
      return self.dbm_process.pid
   
   def stop_dbm_process(self):
      """DBM 프로세스 종료"""
      if self.dbm_process is None:
         return
      
      # 종료 명령 전송
      self.queues['admin_to_dbm'].put({
         'command': 'stop'
      })
      
      # 프로세스 종료 대기
      self.dbm_process.join(2.0)
      if self.dbm_process.is_alive():
         self.dbm_process.terminate()
         self.dbm_process.join(1.0)
      
      self.dbm_process = None
      logging.info("DBM 프로세스 종료됨")
   
   def start_admin_listener(self, admin_instance):
      """Admin의 메시지 리스너 시작"""
      self.admin_listener = threading.Thread(
         target=admin_listener_thread,
         args=(admin_instance, self.queues['dbm_to_admin'], self.result_dict, self.callbacks),
         daemon=True
      )
      self.admin_listener.start()
      logging.info("Admin 리스너 쓰레드 시작")
   
   def admin_to_dbm(self, method, *args, wait_result=True, timeout=10, callback=None, **kwargs):
      """DBM에 요청 전송"""
      if self.shutting_down:
         return None
      
      req_id = str(uuid.uuid4())
      
      # 콜백 등록
      if callback:
         self.callbacks[req_id] = callback
      
      # 요청 전송
      self.queues['admin_to_dbm'].put({
         'id': req_id,
         'method': method,
         'args': args,
         'kwargs': kwargs
      })
      
      # 결과를 기다리지 않으면 바로 반환
      if not wait_result:
         return req_id
      
      # 결과 대기
      start_time = time.time()
      while req_id not in self.result_dict:
         if time.time() - start_time > timeout:
            logging.warning(f"요청 타임아웃: {method}")
            return None
         time.sleep(0.01)
      
      # 결과 반환 및 정리
      result = self.result_dict[req_id]
      del self.result_dict[req_id]
      return result.get('result', None)

# DBM 프로세스 워커
def dbm_worker(dbm_class, input_queue, output_queue, result_dict):
   """DBM 프로세스 메인 함수"""
   try:
      # DBM 인스턴스 생성
      dbm = dbm_class()
      logging.info("DBM 프로세스 초기화 완료")
      
      # Admin으로 요청 보내는 함수
      def dbm_to_admin(method, *args, wait_result=True, timeout=10, **kwargs):
         req_id = str(uuid.uuid4())
         
         # 요청 전송
         output_queue.put({
            'id': req_id,
            'method': method,
            'args': args,
            'kwargs': kwargs
         })
         
         # 결과를 기다리지 않으면 바로 반환
         if not wait_result:
            return req_id
         
         # 결과 대기
         start_time = time.time()
         while req_id not in result_dict:
            if time.time() - start_time > timeout:
               logging.warning(f"요청 타임아웃: {method}")
               return None
            time.sleep(0.01)
         
         # 결과 반환 및 정리
         result = result_dict[req_id]
         del result_dict[req_id]
         return result.get('result', None)
      
      # DBM 인스턴스에 dbm_to_admin 함수 추가
      dbm.dbm_to_admin = dbm_to_admin
      
      shutting_down = False
      # 메시지 처리 루프
      while not shutting_down:
         try:
            # 요청 가져오기 (타임아웃 설정하여 간격적으로 체크)
            try:
               request = input_queue.get(timeout=0.001)
            except queue.Empty:
               continue
            
            # 종료 명령 확인
            if 'command' in request:
                if request['command'] == 'stop':
                    shutting_down = True
                    logging.info("종료 명령 수신")
                    break
                elif request['command'] == 'prepare_shutdown':
                    shutting_down = True
                    continue

            # 요청 정보 파싱
            req_id = request.get('id')
            method_name = request.get('method')
            args = request.get('args', ())
            kwargs = request.get('kwargs', {})
            
            # 메서드 찾기
            method = getattr(dbm, method_name, None)
            if method is None:
               logging.error(f"메서드 없음: {method_name}")
               result_dict[req_id] = {
                  'status': 'error',
                  'error': f"메서드 없음: {method_name}",
                  'result': None
               }
               continue
            
            # 메서드 실행
            try:
               result = method(*args, **kwargs)
               result_dict[req_id] = {
                  'status': 'success',
                  'result': result
               }
               #logging.debug(f"메서드 실행 완료: {method_name}, 결과: {result}")
            except Exception as e:
               logging.error(f"메서드 실행 오류: {e}", exc_info=True)
               result_dict[req_id] = {
                  'status': 'error',
                  'error': str(e),
                  'result': None
               }
         except Exception as e:
            logging.error(f"요청 처리 중 오류: {e}", exc_info=True)
   
   except Exception as e:
      logging.error(f"DBM 프로세스 오류: {e}", exc_info=True)
   
   finally:
      logging.info("DBM 프로세스 종료")

# Admin 리스너 쓰레드
def admin_listener_thread(admin_instance, input_queue, result_dict, callbacks):
   """Admin 메시지 리스너 쓰레드"""
   try:
      logging.info("Admin 리스너 쓰레드 시작")
      
      while True:
         try:
            # 요청 가져오기 (타임아웃 설정하여 간격적으로 체크)
            try:
               request = input_queue.get(timeout=0.001)
            except queue.Empty:
               continue
            
            # 요청 정보 파싱
            req_id = request.get('id')
            method_name = request.get('method')
            args = request.get('args', ())
            kwargs = request.get('kwargs', {})
            
            # 메서드 찾기
            method = getattr(admin_instance, method_name, None)
            if method is None:
               logging.error(f"메서드 없음: {method_name}")
               result_dict[req_id] = {
                  'status': 'error',
                  'error': f"메서드 없음: {method_name}",
                  'result': None
               }
               continue
            
            # 메서드 실행
            try:
               result = method(*args, **kwargs)
               result_dict[req_id] = {
                  'status': 'success',
                  'result': result
               }
               
               # 콜백 실행 (있는 경우)
               if req_id in callbacks:
                  try:
                     callback = callbacks.pop(req_id)
                     callback(result)
                  except Exception as e:
                     logging.error(f"콜백 실행 오류: {e}", exc_info=True)
               
               #logging.debug(f"메서드 실행 완료: {method_name}, 결과: {result}")
            except Exception as e:
               logging.error(f"메서드 실행 오류: {e}", exc_info=True)
               result_dict[req_id] = {
                  'status': 'error',
                  'error': str(e),
                  'result': None
               }
         except Exception as e:
            logging.error(f"요청 처리 중 오류: {e}", exc_info=True)
   
   except Exception as e:
      logging.error(f"Admin 리스너 쓰레드 오류: {e}", exc_info=True)
   
   finally:
      logging.info("Admin 리스너 쓰레드 종료")
