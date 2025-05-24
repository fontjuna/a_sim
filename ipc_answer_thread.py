"""
IPCManager의 answer 메소드 쓰레드 구현 버전

이 코드를 worker.py 파일의 IPCManager 클래스의 answer 메소드와 _process_answer_request 메소드로 교체하세요.
"""

def answer(self, answer_obj, timeout=10):
    """
    Answer 객체를 받아 처리하는 쓰레드를 생성하여 응답을 기다립니다.
    """
    if not isinstance(answer_obj, Answer):
        logging.error(f"answer_obj가 잘못된 타입입니다. {answer_obj}")
        return None
    
    sender = answer_obj.sender
    receiver = answer_obj.receiver
    
    if sender is None:
        logging.error(f"sender가 없습니다. {answer_obj}")
        return None
    
    if receiver not in self.qdict:
        logging.error(f"존재하지 않는 receiver입니다: {receiver}")
        return None
    
    # 응답을 저장할 공간과 이벤트 생성
    result_container = {'value': None}
    result_event = threading.Event()
    
    # 응답을 처리할 쓰레드 생성
    answer_thread = threading.Thread(
        target=self._process_answer_request,
        args=(answer_obj, result_container, result_event, timeout)
    )
    answer_thread.daemon = True
    answer_thread.start()
    
    # 결과 대기
    if result_event.wait(timeout):
        return result_container['value']
    else:
        logging.error(f"answer 요청 시간 초과: {sender} -> {receiver}: {answer_obj.order}")
        return None

def _process_answer_request(self, answer_obj, result_container, result_event, timeout):
    """
    쓰레드에서 실행되는 answer 처리 함수
    """
    sender = answer_obj.sender
    receiver = answer_obj.receiver
    
    # 고유 ID 생성
    qid = str(uuid.uuid4())
    answer_obj.qid = qid
    
    # 응답 요청 전송
    self.qdict[receiver]['order'].put(answer_obj)
    
    end_time = time.time() + timeout
    while time.time() < end_time:
        # 결과 확인
        result = self.result_dict.get(qid)
        if result:
            self.result_dict.remove(qid)
            result_container['value'] = result
            result_event.set()
            return
        
        # 응답 큐 확인
        try:
            while not self.qdict[sender]['answer'].empty():
                result_qid, result_value = self.qdict[sender]['answer'].get_nowait()
                if result_qid == qid:
                    result_container['value'] = result_value
                    result_event.set()
                    return
                else:
                    # 다른 응답은 저장
                    self.result_dict.set(result_qid, result_value)
        except Empty:
            pass
        
        time.sleep(0.001)
    
    # 타임아웃
    result_event.set() 