import multiprocessing as mp
from typing import Any, Dict, Optional, Union

class ProcessSafeDict:
    """업무용 다중 프로세스 안전 딕셔너리"""
    
    def __init__(self, shared_dict, lock, lock_timeout: float = 10.0):
        """
        Args:
            shared_dict: Manager().dict() 객체
            lock: Manager().RLock() 객체
            lock_timeout: 락 획득 타임아웃 (초)
        """
        self.data = shared_dict
        self.lock = lock
        self.lock_timeout = lock_timeout
    
    def _acquire_lock(self):
        """락 획득"""
        if not self.lock.acquire(timeout=self.lock_timeout):
            raise TimeoutError(f"Lock timeout after {self.lock_timeout}s")
    
    def _release_lock(self):
        """락 해제"""
        self.lock.release()
    
    def get(self, key: str, default: Any = None) -> Any:
        """값 조회"""
        self._acquire_lock()
        try:
            return self.data.get(key, default)
        finally:
            self._release_lock()
    
    def set(self, key: str, value: Any) -> None:
        """값 설정"""
        self._acquire_lock()
        try:
            self.data[key] = value
        finally:
            self._release_lock()
    
    def update(self, updates: Dict[str, Any]) -> None:
        """여러 값 한번에 업데이트"""
        self._acquire_lock()
        try:
            self.data.update(updates)
        finally:
            self._release_lock()
    
    def increment(self, key: str, step: Union[int, float] = 1, default: Union[int, float] = 0) -> Union[int, float]:
        """원자적 증가"""
        self._acquire_lock()
        try:
            current = self.data.get(key, default)
            new_value = current + step
            self.data[key] = new_value
            return new_value
        finally:
            self._release_lock()
    
    def append(self, key: str, value: Any, max_length: Optional[int] = None) -> None:
        """리스트에 추가"""
        self._acquire_lock()
        try:
            current = self.data.get(key, [])
            if not isinstance(current, list):
                current = []
            current.append(value)
            if max_length and len(current) > max_length:
                current = current[-max_length:]
            self.data[key] = current
        finally:
            self._release_lock()
    
    def pop(self, key: str, default: Any = None) -> Any:
        """리스트에서 제거"""
        self._acquire_lock()
        try:
            current = self.data.get(key, [])
            if isinstance(current, list) and current:
                value = current.pop()
                self.data[key] = current
                return value
            return default
        finally:
            self._release_lock()
    
    def delete(self, key: str) -> bool:
        """키 삭제"""
        self._acquire_lock()
        try:
            if key in self.data:
                del self.data[key]
                return True
            return False
        finally:
            self._release_lock()
    
    def keys(self) -> list:
        """모든 키"""
        self._acquire_lock()
        try:
            return list(self.data.keys())
        finally:
            self._release_lock()
    
    def items(self) -> list:
        """모든 아이템"""
        self._acquire_lock()
        try:
            return list(self.data.items())
        finally:
            self._release_lock()
    
    def size(self) -> int:
        """키 개수"""
        self._acquire_lock()
        try:
            return len(self.data)
        finally:
            self._release_lock()
    
    def clear(self) -> None:
        """모든 데이터 삭제"""
        self._acquire_lock()
        try:
            self.data.clear()
        finally:
            self._release_lock()

def create_shared_dict(lock_timeout=10.0):
    """공유 딕셔너리 생성 함수"""
    manager = mp.Manager()
    shared_dict = manager.dict()
    lock = manager.RLock()
    return ProcessSafeDict(shared_dict, lock, lock_timeout)
gm_dict = None
def init_gm_dict():
    global gm_dict
    gm_dict = create_shared_dict() # 공유 딕셔너리 생성
    gm_dict.update({
        'all_ready': False, 
        'log_level': 10,
        'sim_no': 0,
        'connected': False,
        'fee_rate': 0.0015,
        'tax_rate': 0.0015,
        })