# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 세션 종류 정의
SESSION_TYPES = [
    "캐릭터_생성",
    "시나리오_생성",
    "모험_생성",
    "던전_생성",
    "파티_생성",
    "파티_결성",
    "모험_준비",
    "모험_진행",
    "던전_탐험",
    "증거수집",
    "의뢰_해결",
    "모험_정리"
]

# 로그 관련 상수
MAX_LOG_CONTENT_LENGTH = 200  # 로그에 기록할 최대 내용 길이
MAX_LOG_FILE_SIZE = 1024 * 1024  # 로그 파일 최대 크기 (1MB)
MAX_LOG_LINES = 1000  # 로그 파일 최대 라인 수

def truncate_log_content(content: str, max_length: int = MAX_LOG_CONTENT_LENGTH) -> str:
    """
    로그 내용을 적절한 길이로 자르는 함수
    
    Args:
        content (str): 원본 내용
        max_length (int): 최대 길이
    
    Returns:
        str: 잘린 내용
    """
    if len(content) <= max_length:
        return content
    
    # 줄바꿈 문자 제거 후 자르기
    content_clean = content.replace('\n', ' ').replace('\r', ' ')
    
    if len(content_clean) <= max_length:
        return content_clean
    
    # 적절한 위치에서 자르기 (단어 경계 고려)
    truncated = content_clean[:max_length-3]
    
    # 마지막 공백에서 자르기 (단어 중간에서 자르지 않도록)
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:  # 80% 이상 위치에 공백이 있으면
        truncated = truncated[:last_space]
    
    return truncated + "..."

def manage_log_file_size(log_file: str):
    """
    로그 파일 크기를 관리하는 함수
    
    Args:
        log_file (str): 로그 파일 경로
    """
    if not os.path.exists(log_file):
        return
    
    try:
        # 파일 크기 확인
        file_size = os.path.getsize(log_file)
        
        if file_size > MAX_LOG_FILE_SIZE:
            logger.info(f"로그 파일 크기 초과 ({file_size} bytes), 정리 중: {log_file}")
            
            # 파일 내용 읽기
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 최근 절반만 유지
            keep_lines = len(lines) // 2
            if keep_lines < 100:  # 최소 100줄은 유지
                keep_lines = min(100, len(lines))
            
            recent_lines = lines[-keep_lines:]
            
            # 파일 다시 쓰기
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"# 로그 파일 정리됨 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.writelines(recent_lines)
            
            logger.info(f"로그 파일 정리 완료: {len(lines)} -> {len(recent_lines)} 줄")
            
    except Exception as e:
        logger.error(f"로그 파일 크기 관리 오류: {e}")

class SessionManager:
    """
    TRPG 세션을 관리하는 클래스
    - 세션 로그 기록
    - 현재 세션 상태 추적
    - 세션 이력 조회
    """
    
    def __init__(self):
        # 세션 로그 디렉토리 생성
        os.makedirs('sessions', exist_ok=True)
        
    def log_session(self, user_id, session_type, content, session_id=None):
        """
        세션 정보를 로그에 기록합니다.
        
        Args:
            user_id (str): 사용자 ID
            session_type (str): 세션 종류 (SESSION_TYPES 중 하나)
            content (str): 주요 내용
            session_id (str, optional): 세션 ID (없으면 자동 생성)
            
        Returns:
            str: 생성된 세션 ID
        """
        # 세션 종류 검증
        if session_type not in SESSION_TYPES:
            session_type = "기타"
            
        # 현재 시간
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 세션 ID 생성 (없으면)
        if not session_id:
            session_id = f"session_{user_id}_{timestamp}"
            
        # 로그 파일 경로
        log_file = f"sessions/session_log_{user_id}.txt"
        
        # 🚨 긴 내용을 적절히 자르기
        truncated_content = truncate_log_content(content)
        
        # 로그 형식: 년월일시분초-세션-주요내용
        log_entry = f"{formatted_time}-{session_type}-{truncated_content}\n"
        
        # 로그 파일 크기 관리 (추가하기 전에)
        manage_log_file_size(log_file)
        
        # 로그 파일에 추가
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"로그 파일 쓰기 오류: {e}")
            
        # 현재 세션 상태 업데이트
        self._update_current_session(user_id, session_id, session_type, timestamp)
            
        # 로그 메시지도 적절히 자르기
        log_display_content = truncate_log_content(content, 30)
        logger.info(f"세션 로그 추가: {user_id}, {session_type}, {log_display_content}")
        return session_id
    
    def _update_current_session(self, user_id, session_id, session_type, timestamp):
        """현재 세션 상태를 JSON 파일로 저장합니다."""
        status_file = f"sessions/session_status_{user_id}.json"
        
        # 현재 상태 데이터
        status_data = {
            'user_id': user_id,
            'current_session_id': session_id,
            'current_session_type': session_type,
            'timestamp': timestamp,
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # JSON 파일로 저장
        try:
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"세션 상태 파일 저장 오류: {e}")
    
    def get_current_session(self, user_id):
        """
        사용자의 현재 세션 상태를 조회합니다.
        
        Args:
            user_id (str): 사용자 ID
            
        Returns:
            dict: 현재 세션 상태 정보 (없으면 None)
        """
        status_file = f"sessions/session_status_{user_id}.json"
        
        if not os.path.exists(status_file):
            return None
            
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"세션 상태 파일 읽기 오류: {e}")
            return None
    
    def get_session_history(self, user_id, limit=10):
        """
        사용자의 세션 이력을 최근 순으로 조회합니다.
        
        Args:
            user_id (str): 사용자 ID
            limit (int, optional): 최대 조회 개수
            
        Returns:
            list: 세션 이력 목록 (각 항목은 딕셔너리)
        """
        log_file = f"sessions/session_log_{user_id}.txt"
        
        if not os.path.exists(log_file):
            return []
            
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 최근 순으로 정렬 (파일의 마지막 라인부터)
            lines.reverse()
            
            history = []
            for i, line in enumerate(lines):
                if i >= limit:
                    break
                    
                # 형식: 년월일시분초-세션-주요내용
                parts = line.strip().split('-', 2)
                if len(parts) >= 3:
                    history.append({
                        'timestamp': parts[0],
                        'session_type': parts[1],
                        'content': parts[2]
                    })
                
            return history
        except Exception as e:
            logger.error(f"세션 이력 조회 오류: {e}")
            return []
    
    def clean_old_logs(self, user_id, days_to_keep=30):
        """
        오래된 로그를 정리하는 함수
        
        Args:
            user_id (str): 사용자 ID
            days_to_keep (int): 유지할 일수
        """
        log_file = f"sessions/session_log_{user_id}.txt"
        
        if not os.path.exists(log_file):
            return
            
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 유지할 라인들 필터링
            keep_lines = []
            for line in lines:
                try:
                    # 타임스탬프 추출
                    timestamp_str = line.split('-')[0]
                    log_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    
                    if log_date >= cutoff_date:
                        keep_lines.append(line)
                except:
                    # 파싱 실패한 라인은 유지
                    keep_lines.append(line)
            
            # 변경사항이 있으면 파일 다시 쓰기
            if len(keep_lines) < len(lines):
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.writelines(keep_lines)
                
                logger.info(f"오래된 로그 정리: {len(lines)} -> {len(keep_lines)} 줄")
                
        except Exception as e:
            logger.error(f"오래된 로그 정리 오류: {e}")
            
# 세션 매니저 인스턴스 생성 (싱글톤)
session_manager = SessionManager() 