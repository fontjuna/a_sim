"""
IPCManager의 answer 메소드 코드

이 코드를 worker.py 파일의 IPCManager 클래스의 order 메소드 바로 뒤에 추가해야 합니다:
"""

def answer(self, answer):
    """
    Answer 객체를 받아 처리
    """
    if not isinstance(answer, Answer):
        logging.error(f"answer가 잘못된 타입입니다. {answer}")
        return None
    
    sender = answer.sender
    receiver = answer.receiver
    
    if sender is None:
        logging.error(f"sender가 없습니다. {answer}")
        return None
    
    qid = str(uuid.uuid4())
    answer.qid = qid
    self.qdict[receiver]['order'].put(answer)

    end_time = time.time() + 10  # 기본 타임아웃 10초
    while time.time() < end_time:
        result = self.result_dict.get(qid)
        if result:
            self.result_dict.remove(qid)
            return result
        try:
            while not self.qdict[sender]['answer'].empty():
                result_qid, result_value = self.qdict[sender]['answer'].get_nowait()
                if result_qid == qid:
                    return result_value
                else:
                    self.result_dict.set(result_qid, result_value)
            time.sleep(0.001)
        except Empty:
            pass
    
    logging.error(f"answer 요청 시간 초과: {sender} -> {receiver}: {answer.order} (qid: {qid})")
    return None 