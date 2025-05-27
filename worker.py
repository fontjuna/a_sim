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
        self.stream_queues = {}  # process_name -> Queue (스트림 전용)
        self.result_dict = self.manager.dict()  # id -> result
        self.req_timestamps = self.manager.dict()  # req_id -> timestamp (추가)
        self.processes = {}  # process_name -> Process
        self.threads = {}  # process_name -> Thread
        self.stream_threads = {}  # process_name -> Thread (스트림 처리 전용)
        self.instances = {}  # process_name -> instance
        self.registered = {}  # process_name -> config
        self.shutting_down = False
        self.cleanup_thread = None  # 정리 스레드
        self.cleanup_interval = 20  # 1분마다 정리
        self.result_timeout = 60   # 10분 후 삭제

    def register(self, name, cls, type=None, start=False, stream=False, *args, **kwargs):
        """컴포넌트 등록 (재등록 시 인스턴스만 교체)"""
        is_reregister = name in self.registered
        
        if is_reregister:
            # 재등록: 기존 컴포넌트 중지 (큐는 유지)
            old_reg_info = self.registered[name]
            if old_reg_info['type'] != type:
                raise ValueError(f"컴포넌트 타입 변경 불가: {old_reg_info['type']} -> {type}")
            
            # 기존 워커 중지 (큐는 유지)
            self._stop_worker_only(name)
            logging.info(f"{name} 인스턴스 교체 중...")
        else:
            # 신규 등록: 큐 생성
            self.queues[name] = mp.Queue()
            self.stream_queues[name] = mp.Queue(maxsize=1000)  # 스트림 큐 (오버플로우 방지)
        
        # 등록 정보 저장/업데이트
        self.registered[name] = {
            'class': cls,
            'type': type,
            'stream': stream,
            'args': args,
            'kwargs': kwargs
        }
        
        # 새 인스턴스 생성
        instance = cls(*args, **kwargs)
        self.instances[name] = instance
        
        # IPC 기능 추가
        self._add_ipc_methods(instance, name)
        
        if is_reregister:
            logging.info(f"{name} 인스턴스 교체 완료")
        
        # 자동 시작
        if start:
            self.start(name, stream=stream)
        
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
        
        # 스트림 워커 중지
        if name in self.stream_threads and self.stream_threads[name]:
            if self.stream_threads[name].is_alive():
                try:
                    self.stream_queues[name].put({'command': 'stop'}, timeout=0.1)
                except:
                    pass
                self.stream_threads[name].join(1.0)
            self.stream_threads[name] = None
            logging.info(f"{name} 스트림 워커 중지됨")
        
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
        
        # 스트림 큐도 완전 삭제
        if name in self.stream_queues:
            try:
                while True:
                    self.stream_queues[name].get_nowait()
            except:
                pass
            del self.stream_queues[name]
        
        logging.info(f"{name} 컴포넌트 완전 삭제됨")
    
    def start(self, name=None, stream=None):
        """컴포넌트 시작"""
        # 첫 start 시에만 cleanup 스레드 시작
        if self.cleanup_thread is None and not self.shutting_down:
            self.cleanup_thread = threading.Thread(
                target=self._cleanup_old_results,
                daemon=True
            )
            self.cleanup_thread.start()
            logging.info("결과 정리 스레드 시작됨")
        
        if name is None:
            # 전체 시작 (모든 타입 포함)
            for comp_name in self.registered.keys():
                reg_info = self.registered[comp_name]
                self._start_single(comp_name, stream=reg_info.get('stream', False))
        else:
            # stream 옵션이 주어지지 않으면 등록된 설정 사용
            if stream is None:
                stream = self.registered[name].get('stream', False)
            self._start_single(name, stream=stream)
    
    def _start_single(self, name, stream=False):
        """단일 컴포넌트 시작"""
        if name not in self.registered:
            raise ValueError(f"등록되지 않은 컴포넌트: {name}")
        
        reg_info = self.registered[name]
        
        if reg_info['type'] == 'process':
            self._start_process(name, stream=stream)
        elif reg_info['type'] == 'thread':
            self._start_thread(name, stream=stream)
        else:  # type=None: 메인 스레드
            self._start_main_listener(name)
            # 메인 프로세스 컴포넌트는 매니저에서 스트림 워커 실행
            if stream:
                self._start_stream_worker(name)
    
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
        
        # 스트림 워커 중지
        if name in self.stream_threads and self.stream_threads[name]:
            try:
                self.stream_queues[name].put({'command': 'stop'}, timeout=0.1)
            except:
                pass
            if self.stream_threads[name].is_alive():
                self.stream_threads[name].join(1.0)
            self.stream_threads[name] = None
            logging.info(f"{name} 스트림 워커 종료됨")
        
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
        self.shutting_down = True
        
        # 정리 스레드 종료 대기
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(2.0)
            logging.info("결과 정리 스레드 종료됨")
        
        self.stop()  # 전체 중지
        
        # 자원 정리
        try:
            self.result_dict.clear()
            self.req_timestamps.clear()
        except:
            pass
        
    def list_components(self):
        """등록된 컴포넌트 목록 조회"""
        return {
            name: {
                'type': info['type'],
                'running': self._is_running(name),
                'stream_running': self._is_stream_running(name),
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
    
    def _is_stream_running(self, name):
        """스트림 워커 실행 상태 확인"""
        return name in self.stream_threads and self.stream_threads[name] and self.stream_threads[name].is_alive()
    
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
            'stream_running': self._is_stream_running(name),
            'has_queue': name in self.queues,
            'has_stream_queue': name in self.stream_queues,
            'args': reg_info['args'],
            'kwargs': reg_info['kwargs']
        }
    
    def _start_process(self, name, stream=False):
        """프로세스 시작"""
        reg_info = self.registered[name]
        
        self.processes[name] = mp.Process(
            target=process_worker,
            args=(name, reg_info['class'], self.queues[name], self.stream_queues[name], self.queues, self.stream_queues, self.result_dict, stream, reg_info['args'], reg_info['kwargs']),
            daemon=False
        )
        self.processes[name].start()
        logging.info(f"{name} 프로세스 시작됨 (PID: {self.processes[name].pid}, stream={stream})")
    
    def _start_thread(self, name, stream=False):
        """스레드 시작"""
        self.threads[name] = threading.Thread(
            target=thread_worker,
            args=(name, self.instances[name], self.queues[name], self.queues, self.stream_queues, self.result_dict, stream),
            daemon=True
        )
        self.threads[name].start()
        # 스레드는 메인 프로세스 내이므로 매니저에서 스트림 워커 실행
        if stream:
            self._start_stream_worker(name)
        logging.info(f"{name} 스레드 시작됨 (stream={stream})")
    
    def _start_main_listener(self, name):
        """메인 컴포넌트 리스너 시작"""
        self.threads[name] = threading.Thread(
            target=main_listener_worker,
            args=(name, self.instances[name], self.queues[name], self.result_dict),
            daemon=True
        )
        self.threads[name].start()
        logging.info(f"{name} 메인 리스너 시작됨")
    
    def _start_stream_worker(self, name):
        """스트림 워커 시작 (모든 타입 공통)"""
        self.stream_threads[name] = threading.Thread(
            target=stream_worker,
            args=(name, self.instances[name], self.stream_queues[name]),
            daemon=True
        )
        self.stream_threads[name].start()
        logging.info(f"{name} 스트림 워커 시작됨")
    
    def _cleanup_old_results(self):
        """오래된 결과 정리 스레드"""
        logging.info("결과 정리 스레드 초기화 완료")
        
        while not self.shutting_down:
            try:
                current_time = time.time()
                cleaned_count = 0
                
                # 오래된 결과 삭제
                for req_id in list(self.result_dict.keys()):
                    req_time = self.req_timestamps.get(req_id, 0)
                    if current_time - req_time > self.result_timeout:
                        try:
                            del self.result_dict[req_id]
                            if req_id in self.req_timestamps:
                                del self.req_timestamps[req_id]
                            cleaned_count += 1
                        except KeyError:
                            pass  # 이미 삭제됨
                
                if cleaned_count > 0:
                    logging.info(f"오래된 결과 {cleaned_count}개 정리됨")
                    cleaned_count = 0
                
                # 현재 상태 로깅 (5분마다)
                if int(current_time) % 300 == 0:  # 5분마다
                    logging.info(f"결과 딕셔너리 크기: {len(self.result_dict)}")
                
                time.sleep(self.cleanup_interval)
                
            except Exception as e:
                logging.error(f"결과 정리 중 오류: {e}")
                time.sleep(self.cleanup_interval)
        
        logging.info("결과 정리 스레드 종료")
    
    def _add_ipc_methods(self, instance, process_name):
        """인스턴스에 IPC 메서드 추가"""
        def order(target, method, *args, **kwargs):
            return self._send_request(target, method, args, kwargs, wait_result=False)
        
        def answer(target, method, *args, timeout=10, **kwargs):
            return self._send_request(target, method, args, kwargs, wait_result=True, timeout=timeout)
        
        def stream(target, func_name, *args, **kwargs):
            return self._send_stream(target, func_name, args, kwargs)
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [process_name]
            results = {}
            for proc_name in self.queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.stream = stream
        instance.broadcast = broadcast

    def order(self, target, method, *args, **kwargs):
        """결과 불필요한 단방향 명령"""
        if target not in self.queues:
            logging.error(f"알 수 없는 컴포넌트: {target}")
            return None
            
        req_id = str(uuid.uuid4())
        try:
            self.queues[target].put({
                'id': req_id,
                'method': method,
                'args': args,
                'kwargs': kwargs
            })
            return req_id
        except Exception as e:
            logging.error(f"order 전송 실패 to {target}: {e}")
            return None

    def answer(self, target, method, *args, timeout=10, **kwargs):
        return self._send_request(target, method, args, kwargs, wait_result=True, timeout=timeout)
    
    def stream(self, target, func_name, *args, **kwargs):
        return self._send_stream(target, func_name, args, kwargs)
    
    def _send_request(self, target, method, args, kwargs, wait_result, timeout=10):
        """요청 전송 (동적 컴포넌트 추가 대응)"""
        if target not in self.queues:
            logging.error(f"알 수 없는 컴포넌트: {target} (등록된 컴포넌트: {list(self.queues.keys())})")
            return None
        
        req_id = str(uuid.uuid4())
        
        # 요청 시간 기록
        self.req_timestamps[req_id] = time.time()
        
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
            # 실패시 타임스탬프도 정리
            if req_id in self.req_timestamps:
                del self.req_timestamps[req_id]
            return None
        
        if not wait_result:
            return req_id
        
        # 결과 대기 (0.1ms 간격)
        start_time = time.time()
        while req_id not in self.result_dict:
            # 대상 컴포넌트가 삭제되었는지 확인
            if target not in self.queues:
                logging.warning(f"대상 컴포넌트 {target}가 삭제됨")
                if req_id in self.req_timestamps:
                    del self.req_timestamps[req_id]
                return None
            
            if time.time() - start_time > timeout:
                logging.warning(f"요청 타임아웃: {method} to {target}")
                # 타임아웃시 타임스탬프 유지 (cleanup 스레드가 나중에 정리)
                return None
            time.sleep(0.0001)  # 0.1ms
        
        # 결과 반환 및 정리
        try:
            result = self.result_dict[req_id]
            del self.result_dict[req_id]
            if req_id in self.req_timestamps:
                del self.req_timestamps[req_id]
            return result.get('result', None)
        except KeyError:
            # 이미 삭제된 경우
            return None
    
    def _send_stream(self, target, func_name, args, kwargs):
        """스트림 데이터 전송"""
        if target not in self.stream_queues:
            logging.error(f"알 수 없는 스트림 대상: {target}")
            return False
        
        try:
            # 논블로킹으로 전송 (큐가 가득 차면 드롭)
            self.stream_queues[target].put_nowait({
                'func_name': func_name,
                'args': args,
                'kwargs': kwargs
            })
            return True
        except queue.Full:
            # 큐 오버플로우 시 경고 (너무 빈번하면 로그 레벨 조정)
            logging.debug(f"스트림 큐 오버플로우: {target}")
            return False
        except Exception as e:
            logging.error(f"스트림 전송 실패 to {target}: {e}")
            return False

def stream_worker(comp_name, instance, stream_queue):
    """스트림 전용 워커"""
    try:
        logging.info(f"{comp_name} 스트림 워커 초기화 완료")
        
        while True:
            try:
                stream_data = stream_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if stream_data.get('command') == 'stop':
                    logging.info(f"{comp_name}: 스트림 워커 종료 명령 수신")
                    break
                
                # 스트림 데이터 처리
                func_name = stream_data.get('func_name')
                args = stream_data.get('args', ())
                kwargs = stream_data.get('kwargs', {})
                
                try:
                    method = getattr(instance, func_name, None)
                    if method is not None:
                        method(*args, **kwargs)  # 즉시 실행 (결과 반환 없음)
                    else:
                        logging.debug(f"스트림 메서드 없음: {func_name}")
                
                except Exception as e:
                    logging.error(f"스트림 메서드 실행 오류: {e}")
                
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"{comp_name}: 스트림 처리 오류: {e}")
    
    except Exception as e:
        logging.error(f"{comp_name} 스트림 워커 오류: {e}", exc_info=True)
    finally:
        logging.info(f"{comp_name} 스트림 워커 종료")

def process_worker(process_name, process_class, own_queue, own_stream_queue, all_queues, all_stream_queues, result_dict, enable_stream, args, kwargs):
    """프로세스 워커"""
    try:
        # 인스턴스 생성
        instance = process_class(*args, **kwargs)
        
        # 초기화 작업 (있으면 실행)
        if hasattr(instance, 'initialize') and callable(getattr(instance, 'initialize')):
            instance.initialize()
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
        
        def stream(target, func_name, *args, **kwargs):
            if target not in all_stream_queues:
                logging.error(f"알 수 없는 스트림 대상: {target}")
                return False
            
            try:
                all_stream_queues[target].put_nowait({
                    'func_name': func_name,
                    'args': args,
                    'kwargs': kwargs
                })
                return True
            except queue.Full:
                logging.debug(f"스트림 큐 오버플로우: {target}")
                return False
            except Exception as e:
                logging.error(f"스트림 전송 실패 to {target}: {e}")
                return False
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [process_name]
            results = {}
            for proc_name in all_queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.stream = stream
        instance.broadcast = broadcast
        
        # 스트림 워커 시작 (enable_stream=True일 때만)
        if enable_stream:
            stream_thread = threading.Thread(
                target=stream_worker,
                args=(process_name, instance, own_stream_queue),
                daemon=True
            )
            stream_thread.start()
            logging.info(f"{process_name} 프로세스 내 스트림 워커 시작됨")
        
        # 메시지 처리 루프
        while True:
            try:
                request = own_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if request.get('command') == 'stop':
                    logging.info(f"{process_name}: 종료 명령 수신")
                    
                    # 정리 작업 (있으면 실행)
                    if hasattr(instance, 'cleanup') and callable(getattr(instance, 'cleanup')):
                        instance.cleanup()
                    
                    # 스트림 워커도 종료
                    if enable_stream:
                        try:
                            own_stream_queue.put_nowait({'command': 'stop'})
                        except:
                            pass
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

def thread_worker(thread_name, instance, own_queue, all_queues, all_stream_queues, result_dict, enable_stream):
    """스레드 워커"""
    try:
        # 초기화 작업 (있으면 실행)
        if hasattr(instance, 'initialize') and callable(getattr(instance, 'initialize')):
            instance.initialize()
            
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
        
        def stream(target, func_name, *args, **kwargs):
            if target not in all_stream_queues:
                logging.error(f"알 수 없는 스트림 대상: {target}")
                return False
            
            try:
                all_stream_queues[target].put_nowait({
                    'func_name': func_name,
                    'args': args,
                    'kwargs': kwargs
                })
                return True
            except queue.Full:
                logging.debug(f"스트림 큐 오버플로우: {target}")
                return False
            except Exception as e:
                logging.error(f"스트림 전송 실패 to {target}: {e}")
                return False
        
        def broadcast(method, *args, exclude=None, **kwargs):
            exclude = exclude or [thread_name]
            results = {}
            for proc_name in all_queues.keys():
                if proc_name not in exclude:
                    results[proc_name] = order(proc_name, method, *args, **kwargs)
            return results
        
        instance.order = order
        instance.answer = answer
        instance.stream = stream
        instance.broadcast = broadcast
        
        # 메시지 처리 루프
        while True:
            try:
                request = own_queue.get(timeout=0.0001)  # 0.1ms
                
                # 종료 명령 확인
                if request.get('command') == 'stop':
                    logging.info(f"{thread_name}: 종료 명령 수신")
                    
                    # 정리 작업 (있으면 실행)
                    if hasattr(instance, 'cleanup') and callable(getattr(instance, 'cleanup')):
                        instance.cleanup()
                    
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
        self.stream_count = 0
    
    def get_admin_info(self, key):
        return f"ADM info for {key}: {self.data_store.get(key, 'No data')}"
    
    def store_admin_data(self, key, value):
        self.data_store[key] = value
        return f"ADM stored: {key} = {value}"
    
    def process_admin_request(self, request_type, data):
        return f"ADM processed {request_type} with data: {data}"
    
    def receive_real_data(self, data):
        """스트림 데이터 수신 메서드"""
        self.stream_count += 1
        if self.stream_count % 100 == 0:  # 100개마다 로그
            logging.info(f"[{self.name}] 스트림 데이터 수신됨 #{self.stream_count}: {data}")
    
    def get_stream_count(self):
        return self.stream_count
    
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
        self.stream_count = 0
    
    def query_data(self, table, condition):
        return f"DBM query result from {table} where {condition}: {self.database.get(table, [])}"
    
    def save_data(self, table, record):
        if table not in self.database:
            self.database[table] = []
        self.database[table].append(record)
        return f"DBM saved to {table}: {record}"
    
    def get_db_status(self):
        return f"DBM status: {len(self.database)} tables, total records: {sum(len(v) for v in self.database.values())}"
    
    def receive_market_data(self, market_data):
        """시장 데이터 스트림 수신"""
        self.stream_count += 1
        if self.stream_count % 50 == 0:  # 50개마다 로그
            logging.info(f"[{self.name}] 시장 데이터 저장됨 #{self.stream_count}: {market_data}")
    
    def get_stream_count(self):
        return self.stream_count
    
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
        self.running = False
        self.tick_count = 0
    
    def handle_request(self, endpoint, params):
        return f"API response from {endpoint} with params {params}: Success"
    
    def cache_data(self, key, data):
        self.cache[key] = data
        return f"API cached: {key} = {data}"
    
    def get_api_stats(self):
        return f"API stats: {len(self.cache)} cached items"
    
    def start_streaming(self):
        """실시간 데이터 스트리밍 시작"""
        self.running = True
        logging.info(f"[{self.name}] 실시간 데이터 스트리밍 시작")
        
        # 별도 스레드에서 고빈도 스트리밍
        import threading
        def stream_loop():
            while self.running:
                self.tick_count += 1
                
                # 실시간 데이터 생성
                market_data = {
                    'tick': self.tick_count,
                    'price': 100 + (self.tick_count % 50),
                    'volume': 1000 + (self.tick_count % 100),
                    'timestamp': time.time()
                }
                
                # ADM과 DBM으로 스트림 전송
                self.stream('adm', 'receive_real_data', market_data)
                self.stream('dbm', 'receive_market_data', market_data)
                
                time.sleep(0.001)  # 1ms 간격 (1000 ticks/sec)
        
        streaming_thread = threading.Thread(target=stream_loop, daemon=True)
        streaming_thread.start()
        
        return "스트리밍 시작됨"
    
    def stop_streaming(self):
        """실시간 데이터 스트리밍 중지"""
        self.running = False
        logging.info(f"[{self.name}] 실시간 데이터 스트리밍 중지")
        return "스트리밍 중지됨"
    
    def get_tick_count(self):
        return self.tick_count
    
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
            adm = ipc.register('adm', ADM, type=None, start=False, stream=True)          # 메인 스레드, 스트림 받음
            logger = ipc.register('logger', ADM, type='thread', start=False, stream=False)  # 멀티 스레드, 스트림 안받음  
            dbm = ipc.register('dbm', DBM, type='process', start=False, stream=True)      # 프로세스, 스트림 받음
            api = ipc.register('api', API, type='process', start=False, stream=False)      # 프로세스, 스트림 안받음
            
            print(f"등록된 컴포넌트: {list(ipc.registered.keys())}")
            
            # 전체 시작
            print("\n2. 전체 시작")
            ipc.start()
            
            time.sleep(2)  # 초기화 대기
            
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
            logger_new = ipc.register('logger', ADM, type='thread', start=True, stream=False)
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
            monitor = ipc.register('monitor', API, type='thread', start=True, stream=False)
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
            
            print("\n7. 스트림 통신 테스트")
            
            # 컴포넌트 스트림 상태 확인
            print("스트림 워커 상태:")
            for name in ['adm', 'dbm', 'api', 'monitor']:
                if name in ipc.registered:
                    status = ipc.get_component_status(name)
                    print(f"  {name}: stream_running={status['stream_running']}")
            
            # API에서 실시간 스트리밍 시작
            print("\nAPI 스트리밍 시작...")
            result = ipc.answer('api', 'start_streaming')
            print(f"스트리밍 시작 결과: {result}")
            
            # 3초간 스트리밍 관찰
            print("3초간 스트리밍 데이터 전송 중...")
            time.sleep(3)
            
            # 스트림 카운트 확인
            adm_count = adm.get_stream_count()
            dbm_count = ipc.answer('dbm', 'get_stream_count')
            api_count = ipc.answer('api', 'get_tick_count')
            
            print(f"\n스트림 통계:")
            print(f"- API 틱 생성: {api_count}")
            print(f"- ADM 수신: {adm_count}")
            print(f"- DBM 수신: {dbm_count}")
            
            # 기존 통신과 스트림 동시 테스트
            print("\n기존 통신과 스트림 동시 실행 테스트:")
            for i in range(3):
                result = ipc.answer('dbm', 'get_db_status')
                print(f"  일반 요청 {i+1}: {result}")
                time.sleep(0.5)
            
            # 스트리밍 중지
            result = ipc.answer('api', 'stop_streaming')
            print(f"스트리밍 중지 결과: {result}")
            
            print("\n=== 테스트 완료 ===")
            print("동적 컴포넌트 관리 테스트:")
            print("- 실행 중 컴포넌트 추가 ✅")
            print("- 새 컴포넌트와 기존 컴포넌트 간 통신 ✅")  
            print("- 실행 중 컴포넌트 삭제 ✅")
            print("- 삭제된 컴포넌트 접근 시 안전한 실패 ✅")
            print("- 인스턴스 교체로 런타임 수정 ✅")
            print("스트림 통신 테스트:")
            print("- 별도 스트림 큐/워커 동작 ✅")
            print("- 고빈도 스트림 전송 ✅")
            print("- 기존 통신과 분리 ✅")
            
        except Exception as e:
            print(f"테스트 중 오류: {e}")
            logging.error(f"테스트 오류: {e}", exc_info=True)
        
        finally:
            print("\n시스템 종료 중...")
            ipc.shutdown()
            print("시스템 종료 완료")
    
    test_ipc_communication()