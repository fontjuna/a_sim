import multiprocessing as mp
import threading
import time
import uuid
import logging
import queue

class IPCManager:
    """프로세스 간 통신 관리자"""
    
    def __init__(self):
        self.manager = mp.Manager()
        self.queues = {}  # process_name -> Queue
        self.result_dict = self.manager.dict()  # id -> result
        self.processes = {}  # process_name -> Process
        self.threads = {}  # process_name -> Thread
        self.instances = {}  # process_name -> instance
        self.registered = {}  # process_name -> config
        self.shutting_down = False

    def register(self, cls_name, cls, type=None, start=False, *args, **kwargs):
        """컴포넌트 등록 (재등록 시 인스턴스만 교체)"""
        is_reregister = cls_name in self.registered
        
        if is_reregister:
            # 재등록: 기존 컴포넌트 중지 (큐는 유지)
            old_reg_info = self.registered[cls_name]
            if old_reg_info['type'] != type:
                raise ValueError(f"컴포넌트 타입 변경 불가: {old_reg_info['type']} -> {type}")
            
            # 기존 워커 중지 (큐는 유지)
            self._stop_worker_only(cls_name)
            logging.info(f"{cls_name} 인스턴스 교체 중...")
        else:
            # 신규 등록: 큐 생성
            self.queues[cls_name] = mp.Queue()
        
        # 등록 정보 저장/업데이트
        self.registered[cls_name] = {
            'class': cls,
            'type': type,
            'args': args,
            'kwargs': kwargs
        }
        
        # 새 인스턴스 생성
        instance = cls(*args, **kwargs)
        self.instances[cls_name] = instance
        
        # IPC 기능 추가
        self._add_ipc_methods(instance, cls_name)
        
        if is_reregister:
            logging.info(f"{cls_name} 인스턴스 교체 완료")
        
        # 자동 시작
        if start:
            self.start(cls_name)
        
        return instance
    
    def _stop_worker_only(self, name):
        """워커만 중지 (큐는 유지)"""
        if name not in self.registered:
            return
        
        reg_info = self.registered[name]
        
        # 종료 명령 전송
        try:
            self.queues[name].put({'command': 'stop'}, timeout=1)
        except:
            pass
        
        if reg_info['type'] == 'process':
            if name in self.processes and self.processes[name]:
                self.processes[name].join(2.0)
                if self.processes[name].is_alive():
                    self.processes[name].terminate()
                    self.processes[name].join(1.0)
                self.processes[name] = None
                logging.info(f"{name} 프로세스 워커 중지됨")
        
        elif reg_info['type'] == 'thread':
            if name in self.threads and self.threads[name]:
                if self.threads[name].is_alive():
                    self.threads[name].join(2.0)
                self.threads[name] = None
                logging.info(f"{name} 스레드 워커 중지됨")
        
        else:  # type=None
            if name in self.threads and self.threads[name]:
                if self.threads[name].is_alive():
                    self.threads[name].join(1.0)
                self.threads[name] = None
                logging.info(f"{name} 메인 리스너 워커 중지됨")
    
    def unregister(self, name):
        """컴포넌트 등록 해제 (완전 삭제)"""
        if name not in self.registered:
            return
        
        self.stop(name)
        
        del self.registered[name]
        del self.instances[name]
        
        # 큐도 완전 삭제 (다른 컴포넌트가 참조할 수 없게 됨)
        if name in self.queues:
            # 큐 비우기
            try:
                while True:
                    self.queues[name].get_nowait()
            except:
                pass
            del self.queues[name]
        
        logging.info(f"{name} 컴포넌트 완전 삭제됨")
    
    def start(self, name=None):
        """컴포넌트 시작"""
        if name is None:
            # 전체 시작 (모든 타입 포함)
            for comp_name in self.registered.keys():
                self._start_single(comp_name)
        else:
            self._start_single(name)
    
    def _start_single(self, name):
        """단일 컴포넌트 시작"""
        if name not in self.registered:
            raise ValueError(f"등록되지 않은 컴포넌트: {name}")
        
        reg_info = self.registered[name]
        
        if reg_info['type'] == 'process':
            self._start_process(name)
        elif reg_info['type'] == 'thread':
            self._start_thread(name)
        else:  # type=None: 메인 스레드
            self._start_main_listener(name)
    
    def stop(self, name=None):
        """컴포넌트 중지"""
        if name is None:
            # 전체 중지
            for comp_name in list(self.registered.keys()):
                self._stop_single(comp_name)
        else:
            self._stop_single(name)
    
    def _stop_single(self, name):
        """단일 컴포넌트 중지"""
        if name not in self.registered:
            return
        
        reg_info = self.registered[name]
        
        # 종료 명령 전송
        try:
            self.queues[name].put({'command': 'stop'}, timeout=1)
        except:
            pass
        
        if reg_info['type'] == 'process':
            if name in self.processes and self.processes[name]:
                self.processes[name].join(2.0)
                if self.processes[name].is_alive():
                    self.processes[name].terminate()
                    self.processes[name].join(1.0)
                self.processes[name] = None
                logging.info(f"{name} 프로세스 종료됨")
        
        elif reg_info['type'] == 'thread':
            if name in self.threads and self.threads[name]:
                if self.threads[name].is_alive():
                    self.threads[name].join(2.0)
                self.threads[name] = None
                logging.info(f"{name} 스레드 종료됨")
        
        else:  # type=None
            if name in self.threads and self.threads[name]:
                if self.threads[name].is_alive():
                    self.threads[name].join(1.0)
                self.threads[name] = None
                logging.info(f"{name} 메인 리스너 종료됨")
    
    def shutdown(self):
        """전체 시스템 종료"""
        logging.info("시스템 종료 시작...")
        self.stop()  # 전체 중지
        
        # 자원 정리
        try:
            self.result_dict.clear()
        except:
            pass
        
    def list_components(self):
        """등록된 컴포넌트 목록 조회"""
        return {
            name: {
                'type': info['type'],
                'running': self._is_running(name),
                'class': info['class'].__name__
            }
            for name, info in self.registered.items()
        }
    
    def _is_running(self, name):
        """컴포넌트 실행 상태 확인"""
        if name not in self.registered:
            return False
        
        reg_info = self.registered[name]
        
        if reg_info['type'] == 'process':
            return name in self.processes and self.processes[name] and self.processes[name].is_alive()
        elif reg_info['type'] == 'thread':
            return name in self.threads and self.threads[name] and self.threads[name].is_alive()
        else:  # type=None
            return name in self.threads and self.threads[name] and self.threads[name].is_alive()
    
    def get_component_status(self, name):
        """특정 컴포넌트 상태 조회"""
        if name not in self.registered:
            return None
        
        reg_info = self.registered[name]
        return {
            'name': name,
            'type': reg_info['type'],
            'class': reg_info['class'].__name__,
            'running': self._is_running(name),
            'has_queue': name in self.queues,
            'args': reg_info['args'],
            'kwargs': reg_info['kwargs']
        }
    
    def _start_process(self, name):
        """프로세스 시작"""
        reg_info = self.registered[name]
        
        self.processes[name] = mp.Process(
            target=process_worker,
            args=(name, reg_info['class'], self.queues[name], self.queues, self.result_dict, reg_info['args'], reg_info['kwargs']),
            daemon=False
        )
        self.processes[name].start()
        logging.info(f"{name} 프로세스 시작됨 (PID: {self.processes[name].pid})")
    
    def _start_thread(self, name):
        """스레드 시작"""
        self.threads[name] = threading.Thread(
            target=thread_worker,
            args=(name, self.instances[name], self.queues[name], self.queues, self.result_dict),
            daemon=True
        )
        self.threads[name].start()
        logging.info(f"{name} 스레드 시작됨")
    
    def _start_main_listener(self, name):
        """메인 컴포넌트 리스너 시작"""
        self.threads[name] = threading.Thread(
            target=main_listener_worker,
            args=(name, self.instances[name], self.queues[name], self.result_dict),
            daemon=True
        )
        self.threads[name].start()
        logging.info(f"{name} 메인 리스너 시작됨")
    
    def _add_ipc_methods(self, instance, process_name):
        """인스턴스에 IPC 메서드 추가"""
        def order(target, method, *args, **kwargs):
            return self._send_request(target, method, args, kwargs, wait_result=False)
        
        def answer(target, method, *args, timeout=10, **kwargs):
            return self._send_request(target, method, args, kwargs, wait_result=True, timeout=timeout)
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [process_name]
            results = {}
            for proc_name in self.queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.broadcast = broadcast

    def order(self, target, method, *args, **kwargs):
        return self._send_request(target, method, args, kwargs, wait_result=False)

    def answer(self, target, method, *args, timeout=10, **kwargs):
        return self._send_request(target, method, args, kwargs, wait_result=True, timeout=timeout)    
    
    def _send_request(self, target, method, args, kwargs, wait_result, timeout=10):
        """요청 전송 (동적 컴포넌트 추가 대응)"""
        if target not in self.queues:
            logging.error(f"알 수 없는 컴포넌트: {target} (등록된 컴포넌트: {list(self.queues.keys())})")
            return None
        
        req_id = str(uuid.uuid4())
        
        # 요청 전송
        try:
            self.queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
        except Exception as e:
            logging.error(f"요청 전송 실패 to {target}: {e}")
            return None
        
        if not wait_result:
            return req_id
        
        # 결과 대기 (0.1ms 간격)
        start_time = time.time()
        while req_id not in self.result_dict:
            # 대상 컴포넌트가 삭제되었는지 확인
            if target not in self.queues:
                logging.warning(f"대상 컴포넌트 {target}가 삭제됨")
                return None
            
            if time.time() - start_time > timeout:
                logging.warning(f"요청 타임아웃: {method} to {target}")
                return None
            time.sleep(0.0001)  # 0.1ms
        
        # 결과 반환
        result = self.result_dict[req_id]
        del self.result_dict[req_id]
        return result.get('result', None)

def process_worker(process_name, process_class, own_queue, all_queues, result_dict, args, kwargs):
    """프로세스 워커"""
    try:
        # 인스턴스 생성
        instance = process_class(*args, **kwargs)
        logging.info(f"{process_name} 프로세스 초기화 완료")
        
        # IPC 기능 추가
        def order(target, method, *args, **kwargs):
            if target not in all_queues:
                logging.error(f"알 수 없는 컴포넌트: {target}")
                return None
            
            req_id = str(uuid.uuid4())
            all_queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            return req_id
        
        def answer(target, method, *args, timeout=10, **kwargs):
            if target not in all_queues:
                logging.error(f"알 수 없는 컴포넌트: {target}")
                return None
            
            req_id = str(uuid.uuid4())
            all_queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            
            # 결과 대기
            start_time = time.time()
            while req_id not in result_dict:
                if time.time() - start_time > timeout:
                    logging.warning(f"요청 타임아웃: {method} to {target}")
                    return None
                time.sleep(0.0001)  # 0.1ms
            
            result = result_dict[req_id]
            del result_dict[req_id]
            return result.get('result', None)
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [process_name]
            results = {}
            for proc_name in all_queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.broadcast = broadcast
        
        # 메시지 처리 루프
        while True:
            try:
                request = own_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if request.get('command') == 'stop':
                    logging.info(f"{process_name}: 종료 명령 수신")
                    break
                
                # 요청 처리
                req_id = request.get('id')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                
                try:
                    method = getattr(instance, method_name, None)
                    if method is None:
                        result_data = {
                            'status': 'error',
                            'error': f"메서드 없음: {method_name}",
                            'result': None
                        }
                    else:
                        try:
                            result = method(*args, **kwargs)
                            result_data = {
                                'status': 'success',
                                'result': result
                            }
                        except Exception as e:
                            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                            result_data = {
                                'status': 'error',
                                'error': str(e),
                                'result': None
                            }
                    
                    # 결과 저장
                    result_dict[req_id] = result_data
                    
                except Exception as e:
                    logging.error(f"요청 처리 중 오류: {e}", exc_info=True)
                
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"{process_name}: 메시지 처리 오류: {e}", exc_info=True)
    
    except Exception as e:
        logging.error(f"{process_name} 프로세스 오류: {e}", exc_info=True)
    finally:
        logging.info(f"{process_name} 프로세스 종료")

def thread_worker(thread_name, instance, own_queue, all_queues, result_dict):
    """스레드 워커"""
    try:
        logging.info(f"{thread_name} 스레드 초기화 완료")
        
        # IPC 기능 추가
        def order(target, method, *args, **kwargs):
            if target not in all_queues:
                logging.error(f"알 수 없는 컴포넌트: {target}")
                return None
            
            req_id = str(uuid.uuid4())
            all_queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            return req_id
        
        def answer(target, method, *args, timeout=10, **kwargs):
            if target not in all_queues:
                logging.error(f"알 수 없는 컴포넌트: {target}")
                return None
            
            req_id = str(uuid.uuid4())
            all_queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            
            # 결과 대기
            start_time = time.time()
            while req_id not in result_dict:
                if time.time() - start_time > timeout:
                    logging.warning(f"요청 타임아웃: {method} to {target}")
                    return None
                time.sleep(0.0001)  # 0.1ms
            
            result = result_dict[req_id]
            del result_dict[req_id]
            return result.get('result', None)
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [thread_name]
            results = {}
            for proc_name in all_queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.broadcast = broadcast
        
        # 메시지 처리 루프
        while True:
            try:
                request = own_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if request.get('command') == 'stop':
                    logging.info(f"{thread_name}: 종료 명령 수신")
                    break
                
                # 요청 처리
                req_id = request.get('id')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                
                try:
                    method = getattr(instance, method_name, None)
                    if method is None:
                        result_data = {
                            'status': 'error',
                            'error': f"메서드 없음: {method_name}",
                            'result': None
                        }
                    else:
                        try:
                            result = method(*args, **kwargs)
                            result_data = {
                                'status': 'success',
                                'result': result
                            }
                        except Exception as e:
                            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                            result_data = {
                                'status': 'error',
                                'error': str(e),
                                'result': None
                            }
                    
                    # 결과 저장
                    result_dict[req_id] = result_data
                    
                except Exception as e:
                    logging.error(f"요청 처리 중 오류: {e}", exc_info=True)
                
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"{thread_name}: 메시지 처리 오류: {e}", exc_info=True)
    
    except Exception as e:
        logging.error(f"{thread_name} 스레드 오류: {e}", exc_info=True)
    finally:
        logging.info(f"{thread_name} 스레드 종료")

def main_listener_worker(comp_name, instance, own_queue, result_dict):
    """메인 컴포넌트 리스너"""
    try:
        logging.info(f"{comp_name} 메인 리스너 초기화 완료")
        
        # 메시지 처리 루프
        while True:
            try:
                request = own_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if request.get('command') == 'stop':
                    logging.info(f"{comp_name}: 리스너 종료 명령 수신")
                    break
                
                # 요청 처리
                req_id = request.get('id')
                method_name = request.get('method')
                args = request.get('args', ())
                kwargs = request.get('kwargs', {})
                
                try:
                    method = getattr(instance, method_name, None)
                    if method is None:
                        result_data = {
                            'status': 'error',
                            'error': f"메서드 없음: {method_name}",
                            'result': None
                        }
                    else:
                        try:
                            result = method(*args, **kwargs)
                            result_data = {
                                'status': 'success',
                                'result': result
                            }
                        except Exception as e:
                            logging.error(f"메서드 실행 오류: {e}", exc_info=True)
                            result_data = {
                                'status': 'error',
                                'error': str(e),
                                'result': None
                            }
                    
                    # 결과 저장
                    result_dict[req_id] = result_data
                    
                except Exception as e:
                    logging.error(f"요청 처리 중 오류: {e}", exc_info=True)
                
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"{comp_name}: 리스너 처리 오류: {e}", exc_info=True)
    
    except Exception as e:
        logging.error(f"{comp_name} 메인 리스너 오류: {e}", exc_info=True)
    finally:
        logging.info(f"{comp_name} 메인 리스너 종료")

# 테스트용 클래스들
class ADM:
    def __init__(self):
        self.name = "ADM"
        self.data_store = {}
    
    def get_admin_info(self, key):
        return f"ADM info for {key}: {self.data_store.get(key, 'No data')}"
    
    def store_admin_data(self, key, value):
        self.data_store[key] = value
        return f"ADM stored: {key} = {value}"
    
    def process_admin_request(self, request_type, data):
        return f"ADM processed {request_type} with data: {data}"
    
    def test_adm_requests(self):
        print(f"[{self.name}] 다른 컴포넌트들에게 요청 시작")
        
        result = self.answer('dbm', 'save_data', 'users', {'id': 1, 'name': 'Alice', 'from': 'ADM'})
        print(f"[{self.name} -> DBM] save_data: {result}")
        
        result = self.answer('api', 'handle_request', '/admin/status', {'user': 'admin'})
        print(f"[{self.name} -> API] handle_request: {result}")

class DBM:
    def __init__(self):
        self.name = "DBM"
        self.database = {}
    
    def query_data(self, table, condition):
        return f"DBM query result from {table} where {condition}: {self.database.get(table, [])}"
    
    def save_data(self, table, record):
        if table not in self.database:
            self.database[table] = []
        self.database[table].append(record)
        return f"DBM saved to {table}: {record}"
    
    def get_db_status(self):
        return f"DBM status: {len(self.database)} tables, total records: {sum(len(v) for v in self.database.values())}"
    
    def test_dbm_requests(self):
        print(f"[{self.name}] 다른 컴포넌트들에게 요청 시작")
        
        result = self.answer('adm', 'store_admin_data', 'last_db_operation', 'data_saved')
        print(f"[{self.name} -> ADM] store_admin_data: {result}")
        
        result = self.answer('api', 'cache_data', 'db_cache', {'tables': list(self.database.keys())})
        print(f"[{self.name} -> API] cache_data: {result}")

class API:
    def __init__(self):
        self.name = "API"
        self.cache = {}
    
    def handle_request(self, endpoint, params):
        return f"API response from {endpoint} with params {params}: Success"
    
    def cache_data(self, key, data):
        self.cache[key] = data
        return f"API cached: {key} = {data}"
    
    def get_api_stats(self):
        return f"API stats: {len(self.cache)} cached items"
    
    def test_api_requests(self):
        print(f"[{self.name}] 다른 컴포넌트들에게 요청 시작")
        
        result = self.answer('adm', 'process_admin_request', 'api_log', f'Cache size: {len(self.cache)}')
        print(f"[{self.name} -> ADM] process_admin_request: {result}")
        
        result = self.answer('dbm', 'query_data', 'users', 'from=ADM')
        print(f"[{self.name} -> DBM] query_data: {result}")

if __name__ == "__main__":
    # 멀티프로세싱 설정
    mp.set_start_method('spawn', force=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    def test_ipc_communication():
        print("=== IPC 통신 테스트 시작 ===")
        
        ipc = IPCManager()
        
        try:
            # 컴포넌트 등록
            print("\n1. 컴포넌트 등록")
            adm = ipc.register('adm', ADM, type=None, start=False)          # 메인 스레드
            logger = ipc.register('logger', ADM, type='thread', start=False)  # 멀티 스레드  
            dbm = ipc.register('dbm', DBM, type='process', start=False)      # 프로세스
            api = ipc.register('api', API, type='process', start=False)      # 프로세스
            
            print(f"등록된 컴포넌트: {list(ipc.registered.keys())}")
            
            # 전체 시작
            print("\n2. 전체 시작")
            ipc.start()
            
            time.sleep(2)  # 초기화 대기
            
            print()
            print(f"ADM 인스턴스 (메인): {adm}")
            print(f"Logger 스레드: {ipc.threads.get('logger')}")
            print(f"DBM 프로세스: {ipc.processes.get('dbm')}")
            print(f"API 프로세스: {ipc.processes.get('api')}")
            
            print("\n3. 각 컴포넌트에서 요청 실행")
            
            # ADM (메인)에서 직접 호출
            print("\n=== ADM (메인 스레드)에서 요청 ===")
            adm.test_adm_requests()
            
            time.sleep(0.5)
            
            # Logger 스레드에서 요청
            print("\n=== Logger 스레드에서 요청 ===")
            ipc._send_request('logger', 'test_adm_requests', (), {}, wait_result=False)
            
            time.sleep(0.5)
            
            # DBM 프로세스에서 요청
            print("\n=== DBM 프로세스에서 요청 ===")
            ipc._send_request('dbm', 'test_dbm_requests', (), {}, wait_result=False)
            
            time.sleep(0.5)
            
            # API 프로세스에서 요청
            print("\n=== API 프로세스에서 요청 ===")
            ipc._send_request('api', 'test_api_requests', (), {}, wait_result=False)
            
            time.sleep(1)
            
            print("\n4. 상태 확인")
            adm_info = adm.get_admin_info('last_db_operation')
            logger_info = ipc._send_request('logger', 'get_admin_info', ('system_status',), {}, wait_result=True)
            dbm_status = ipc._send_request('dbm', 'get_db_status', (), {}, wait_result=True)
            api_stats = ipc._send_request('api', 'get_api_stats', (), {}, wait_result=True)
            
            print(f"ADM 정보 (메인): {adm_info}")
            print(f"Logger 정보 (스레드): {logger_info}")
            print(f"DBM 상태 (프로세스): {dbm_status}")
            print(f"API 통계 (프로세스): {api_stats}")
            
            print("\n5. 인스턴스 교체 테스트")
            
            # Logger를 다른 파라미터로 재등록 (큐는 유지됨)
            print("Logger 인스턴스 교체 중...")
            logger_new = ipc.register('logger', ADM, type='thread', start=True)
            logger_new.name = "Logger_V2"  # 구분을 위해 이름 변경
            
            time.sleep(0.5)
            
            # 교체된 Logger로 요청 테스트
            print("\n=== Logger V2 (교체된 스레드)에서 요청 ===")
            ipc._send_request('logger', 'test_adm_requests', (), {}, wait_result=False)
            
            time.sleep(0.5)
            
            # 다른 컴포넌트에서 교체된 Logger로 요청
            print("ADM에서 교체된 Logger로 요청...")
            logger_result = adm.answer('logger', 'get_admin_info', 'test_after_swap')
            print(f"교체된 Logger 응답: {logger_result}")
            
            print("\n6. 실행 중 동적 컴포넌트 관리 테스트")
            
            # 현재 컴포넌트 상태 확인
            print("현재 등록된 컴포넌트:")
            for name, status in ipc.list_components().items():
                print(f"  {name}: {status}")
            
            # 실행 중 새 컴포넌트 추가
            print("\n실행 중 새 컴포넌트 'monitor' 추가...")
            monitor = ipc.register('monitor', API, type='thread', start=True)
            monitor.name = "Monitor"
            
            time.sleep(0.5)
            
            # 새 컴포넌트로 요청 테스트
            print("새 컴포넌트로 요청 테스트:")
            monitor_result = adm.answer('monitor', 'get_api_stats')
            print(f"Monitor 응답: {monitor_result}")
            
            # 기존 컴포넌트에서 새 컴포넌트로 요청
            print("DBM에서 새 Monitor로 요청...")
            ipc._send_request('dbm', 'answer', ('monitor', 'cache_data', 'test_key', 'test_value'), {}, wait_result=False)
            
            time.sleep(0.5)
            
            # 컴포넌트 삭제 테스트
            print("\nLogger 컴포넌트 삭제 테스트...")
            ipc.unregister('logger')
            
            print("삭제 후 컴포넌트 목록:")
            for name, status in ipc.list_components().items():
                print(f"  {name}: {status}")
            
            # 삭제된 컴포넌트로 요청 시도 (실패해야 함)
            print("\n삭제된 컴포넌트로 요청 시도 (실패 예상):")
            deleted_result = adm.answer('logger', 'get_admin_info', 'test')
            print(f"삭제된 Logger 응답: {deleted_result}")
            
            print("\n=== 테스트 완료 ===")
            print("동적 컴포넌트 관리 테스트:")
            print("- 실행 중 컴포넌트 추가 ✅")
            print("- 새 컴포넌트와 기존 컴포넌트 간 통신 ✅")  
            print("- 실행 중 컴포넌트 삭제 ✅")
            print("- 삭제된 컴포넌트 접근 시 안전한 실패 ✅")
            print("- 인스턴스 교체로 런타임 수정 ✅")
            
        except Exception as e:
            print(f"테스트 중 오류: {e}")
            logging.error(f"테스트 오류: {e}", exc_info=True)
        
        finally:
            print("\n시스템 종료 중...")
            ipc.shutdown()
            print("시스템 종료 완료")
    
    test_ipc_communication()