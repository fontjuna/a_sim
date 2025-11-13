# -*- coding: utf-8 -*-
"""
키움증권 REST API HTTP 클라이언트
"""

import requests
import json
import time
import logging
from datetime import datetime, timedelta
from rest_api_config import RestAPIConfig, RestAPIEndpoints

class TokenManager:
    """토큰 관리 클래스"""
    
    def __init__(self, config):
        """
        초기화
        
        Args:
            config: RestAPIConfig 인스턴스
        """
        self.config = config
        self.token = None
        self.token_type = None
        self.expires_dt = None
    
    def issue_token(self):
        """토큰 발급"""
        try:
            url = self.config.get_auth_url(RestAPIEndpoints.TOKEN_ISSUE)
            
            headers = {
                "Content-Type": "application/json;charset=UTF-8"
            }
            
            body = {
                "grant_type": "client_credentials",
                "appkey": self.config.appkey,
                "secretkey": self.config.secretkey
            }
            
            logging.info("토큰 발급 요청")
            response = requests.post(url, headers=headers, json=body, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('return_code') == 0:
                    self.token = data.get('token')
                    self.token_type = data.get('token_type', 'bearer')
                    self.expires_dt = data.get('expires_dt')
                    
                    logging.info(f"토큰 발급 성공: 만료일시={self.expires_dt}")
                    return True
                else:
                    logging.error(f"토큰 발급 실패: {data.get('return_msg')}")
                    return False
            else:
                logging.error(f"토큰 발급 요청 실패: status={response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"토큰 발급 오류: {type(e).__name__} - {e}", exc_info=True)
            return False
    
    def revoke_token(self):
        """토큰 폐기"""
        try:
            if not self.token:
                return True
            
            url = self.config.get_auth_url(RestAPIEndpoints.TOKEN_REVOKE)
            
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "authorization": f"Bearer {self.token}"
            }
            
            body = {
                "token": self.token
            }
            
            logging.info("토큰 폐기 요청")
            response = requests.post(url, headers=headers, json=body, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('return_code') == 0:
                    logging.info("토큰 폐기 성공")
                    self.token = None
                    self.token_type = None
                    self.expires_dt = None
                    return True
                else:
                    logging.error(f"토큰 폐기 실패: {data.get('return_msg')}")
                    return False
            else:
                logging.error(f"토큰 폐기 요청 실패: status={response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"토큰 폐기 오류: {type(e).__name__} - {e}", exc_info=True)
            return False
    
    def is_token_valid(self):
        """토큰 유효성 확인"""
        if not self.token or not self.expires_dt:
            return False
        
        try:
            # 만료시간 파싱 (YYYYMMDDHHMMSS)
            expire_time = datetime.strptime(self.expires_dt, '%Y%m%d%H%M%S')
            
            # 현재 시간
            now = datetime.now()
            
            # 여유시간 확인 (만료 5분 전)
            margin = timedelta(seconds=self.config.TOKEN_REFRESH_MARGIN)
            
            return (expire_time - now) > margin
            
        except Exception as e:
            logging.error(f"토큰 유효성 확인 오류: {e}")
            return False
    
    def get_authorization_header(self):
        """Authorization 헤더 값 반환"""
        if not self.token:
            return None
        return f"Bearer {self.token}"


class RestAPIClient:
    """REST API HTTP 클라이언트"""
    
    def __init__(self, config):
        """
        초기화
        
        Args:
            config: RestAPIConfig 인스턴스
        """
        self.config = config
        self.token_manager = TokenManager(config)
        self.session = requests.Session()
    
    def connect(self):
        """연결 (토큰 발급)"""
        return self.token_manager.issue_token()
    
    def disconnect(self):
        """연결 해제 (토큰 폐기)"""
        return self.token_manager.revoke_token()
    
    def _check_token(self):
        """토큰 확인 및 갱신"""
        if not self.token_manager.is_token_valid():
            logging.info("토큰 만료 또는 없음, 재발급 시도")
            return self.token_manager.issue_token()
        return True
    
    def request(self, api_id, endpoint, body=None, cont_yn=None, next_key=None):
        """
        API 요청
        
        Args:
            api_id: API ID (예: "ka10001")
            endpoint: API 엔드포인트
            body: 요청 바디 (dict)
            cont_yn: 연속조회여부 (Y/N)
            next_key: 연속조회키
            
        Returns:
            (success: bool, data: dict, remained: bool, next_key: str)
        """
        try:
            # 토큰 확인
            if not self._check_token():
                return False, None, False, None
            
            # URL 생성
            url = self.config.get_api_url(endpoint)
            
            # 헤더 생성
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "api-id": api_id,
                "authorization": self.token_manager.get_authorization_header()
            }
            
            if cont_yn:
                headers["cont-yn"] = cont_yn
            if next_key:
                headers["next-key"] = next_key
            
            # 요청
            logging.debug(f"API 요청: api_id={api_id}, url={url}")
            response = self.session.post(url, headers=headers, json=body, timeout=self.config.REQUEST_TIMEOUT)
            
            # 응답 처리
            if response.status_code == 200:
                data = response.json()
                
                # 응답 헤더에서 연속조회 정보 추출
                resp_cont_yn = response.headers.get('cont-yn', 'N')
                resp_next_key = response.headers.get('next-key', '')
                
                remained = (resp_cont_yn == 'Y')
                
                # 리턴 코드 확인
                return_code = data.get('return_code')
                if return_code == 0:
                    logging.debug(f"API 요청 성공: api_id={api_id}")
                    return True, data, remained, resp_next_key
                else:
                    logging.error(f"API 오류: api_id={api_id}, code={return_code}, msg={data.get('return_msg')}")
                    return False, data, False, None
            else:
                logging.error(f"API 요청 실패: api_id={api_id}, status={response.status_code}")
                return False, None, False, None
                
        except Exception as e:
            logging.error(f"API 요청 오류: api_id={api_id}, {type(e).__name__} - {e}", exc_info=True)
            return False, None, False, None
    
    def request_with_retry(self, api_id, endpoint, body=None, max_retry=None):
        """
        재시도 로직이 포함된 API 요청
        
        Args:
            api_id: API ID
            endpoint: API 엔드포인트
            body: 요청 바디
            max_retry: 최대 재시도 횟수
            
        Returns:
            (success: bool, data: dict)
        """
        if max_retry is None:
            max_retry = self.config.MAX_RETRY
        
        for attempt in range(max_retry):
            success, data, remained, next_key = self.request(api_id, endpoint, body)
            
            if success:
                return True, data
            
            if attempt < max_retry - 1:
                logging.info(f"재시도 {attempt + 1}/{max_retry}")
                time.sleep(self.config.RETRY_DELAY)
        
        return False, None
    
    def request_continuous(self, api_id, endpoint, body=None, max_count=None):
        """
        연속조회 API 요청
        
        Args:
            api_id: API ID
            endpoint: API 엔드포인트
            body: 요청 바디
            max_count: 최대 조회 횟수
            
        Returns:
            (success: bool, all_data: list)
        """
        all_data = []
        cont_yn = None
        next_key = None
        count = 0
        
        while True:
            success, data, remained, next_key = self.request(api_id, endpoint, body, cont_yn, next_key)
            
            if not success:
                return False, all_data
            
            # 데이터 추가
            all_data.append(data)
            count += 1
            
            # 연속조회 종료 조건
            if not remained:
                break
            
            if max_count and count >= max_count:
                logging.warning(f"연속조회 최대 횟수 도달: {max_count}")
                break
            
            # 다음 요청 준비
            cont_yn = 'Y'
            time.sleep(0.2)  # TR 제한 대응
        
        return True, all_data
