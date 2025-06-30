# -*- coding: utf-8 -*-
import logging
import re
import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import user_conversations, user_characters
from character_manager import CharacterManager
from session_manager import session_manager, SESSION_TYPES
from scenario_manager import scenario_manager, ScenarioStage
from trpgbot_ragmd_sentencetr import find_similar_chunks, generate_answer_with_rag, generate_answer_without_rag
import time

# NPC 매니저 임포트 추가
try:
    from npc_manager import npc_manager
except ImportError:
    logger.warning("⚠️ NPC 매니저를 임포트할 수 없습니다. NPC 기능이 제한됩니다.")
    npc_manager = None

logger = logging.getLogger(__name__)

# 텔레그램 메시지 길이 제한 상수
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
SAFE_MESSAGE_LENGTH = 4000  # 안전 마진을 둔 길이

# LLM 컨텍스트 길이 제한 상수 추가
LLM_MAX_CONTEXT_LENGTH = 8000  # LLM에게 보낼 수 있는 최대 컨텍스트 길이
LLM_SAFE_CONTEXT_LENGTH = 7000  # 안전 마진을 둔 컨텍스트 길이

def truncate_text_safely(text: str, max_length: int = LLM_SAFE_CONTEXT_LENGTH, preserve_end: bool = False) -> str:
    """
    텍스트를 안전하게 자르는 함수
    
    Args:
        text (str): 자를 텍스트
        max_length (int): 최대 길이
        preserve_end (bool): True면 끝부분 보존, False면 앞부분 보존
    
    Returns:
        str: 잘린 텍스트
    """
    if len(text) <= max_length:
        return text
    
    if preserve_end:
        # 끝부분 보존 (최근 대화 등)
        truncated = text[-max_length:]
        return f"...(이전 내용 생략)...\n{truncated}"
    else:
        # 앞부분 보존 (시스템 프롬프트 등)
        truncated = text[:max_length]
        return f"{truncated}\n...(이후 내용 생략)..."

def check_context_size(context_parts: list, max_total_length: int = LLM_SAFE_CONTEXT_LENGTH) -> dict:
    """
    컨텍스트 부분들의 총 크기를 체크하고 정보를 반환
    
    Args:
        context_parts (list): 컨텍스트 부분들의 리스트
        max_total_length (int): 최대 총 길이
    
    Returns:
        dict: 크기 정보와 권장사항
    """
    total_length = sum(len(str(part)) for part in context_parts)
    
    return {
        "total_length": total_length,
        "max_length": max_total_length,
        "is_oversized": total_length > max_total_length,
        "parts_count": len(context_parts),
        "average_part_size": total_length // len(context_parts) if context_parts else 0,
        "reduction_needed": max(0, total_length - max_total_length),
        "status": "크기 초과" if total_length > max_total_length else "정상"
    }

def optimize_context_parts(context_parts: list, max_total_length: int = LLM_SAFE_CONTEXT_LENGTH) -> list:
    """
    컨텍스트 부분들을 최적화하여 크기를 줄이는 함수
    
    Args:
        context_parts (list): 원본 컨텍스트 부분들
        max_total_length (int): 최대 총 길이
    
    Returns:
        list: 최적화된 컨텍스트 부분들
    """
    if not context_parts:
        return []
    
    # 현재 크기 체크
    size_info = check_context_size(context_parts, max_total_length)
    
    if not size_info["is_oversized"]:
        return context_parts  # 이미 적절한 크기
    
    logger.warning(f"⚠️ 컨텍스트 크기 초과: {size_info['total_length']}자 > {max_total_length}자")
    logger.info(f"🔧 컨텍스트 최적화 시작: {size_info['reduction_needed']}자 줄여야 함")
    
    optimized_parts = []
    remaining_length = max_total_length
    
    # 우선순위에 따라 컨텍스트 부분들을 처리
    # 1. 캐릭터 정보 (가장 중요)
    # 2. 시나리오 정보 (중요)
    # 3. 세션 요약 (보통)
    # 4. 세션 파일들 (덜 중요)
    # 5. 세션 프롬프트 (가장 덜 중요)
    
    priority_keywords = [
        ("플레이어 캐릭터 정보", 0.3),  # 30% 할당
        ("시나리오", 0.25),  # 25% 할당
        ("상황 요약", 0.2),   # 20% 할당
        ("설정", 0.15),       # 15% 할당
        ("세션 안내", 0.1)    # 10% 할당
    ]
    
    for part in context_parts:
        part_str = str(part)
        
        # 우선순위 결정
        allocated_length = max_total_length // len(context_parts)  # 기본 할당
        
        for keyword, ratio in priority_keywords:
            if keyword in part_str:
                allocated_length = int(max_total_length * ratio)
                break
        
        # 남은 길이 확인
        if remaining_length <= 0:
            logger.warning(f"⚠️ 컨텍스트 길이 한계 도달, 나머지 부분 생략")
            break
        
        # 할당된 길이로 제한
        actual_length = min(allocated_length, remaining_length, len(part_str))
        
        if len(part_str) > actual_length:
            # 텍스트 종류에 따라 다른 자르기 방식 적용
            if "대화 내용" in part_str or "상황 요약" in part_str:
                # 대화나 요약은 끝부분 보존
                truncated_part = truncate_text_safely(part_str, actual_length, preserve_end=True)
            else:
                # 설정이나 프롬프트는 앞부분 보존
                truncated_part = truncate_text_safely(part_str, actual_length, preserve_end=False)
            
            optimized_parts.append(truncated_part)
            logger.info(f"📝 컨텍스트 부분 축소: {len(part_str)}자 → {len(truncated_part)}자")
        else:
            optimized_parts.append(part_str)
        
        remaining_length -= len(optimized_parts[-1])
    
    # 최종 크기 확인
    final_size_info = check_context_size(optimized_parts, max_total_length)
    logger.info(f"✅ 컨텍스트 최적화 완료: {final_size_info['total_length']}자 ({final_size_info['status']})")
    
    return optimized_parts

def split_long_message(text: str, max_length: int = SAFE_MESSAGE_LENGTH) -> list:
    """
    긴 메시지를 텔레그램 길이 제한에 맞게 분할하는 함수
    
    Args:
        text (str): 분할할 텍스트
        max_length (int): 최대 길이 (기본값: 4000)
    
    Returns:
        list: 분할된 메시지 리스트
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # 줄 단위로 분할 시도
    lines = text.split('\n')
    
    for line in lines:
        # 현재 줄을 추가했을 때 길이 초과하는지 확인
        if len(current_chunk) + len(line) + 1 <= max_length:  # +1은 개행문자
            if current_chunk:
                current_chunk += '\n' + line
            else:
                current_chunk = line
        else:
            # 현재 청크가 있으면 저장
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = line
            else:
                # 한 줄이 너무 긴 경우 강제로 분할
                while len(line) > max_length:
                    chunks.append(line[:max_length])
                    line = line[max_length:]
                current_chunk = line
    
    # 마지막 청크 추가
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

async def send_long_message(message, text: str, prefix: str = "[마스터]"):
    """
    긴 메시지를 분할해서 전송하는 함수
    
    Args:
        message: 텔레그램 메시지 객체
        text (str): 전송할 텍스트
        prefix (str): 메시지 앞에 붙일 접두사
    """
    try:
        chunks = split_long_message(text)
        
        if len(chunks) == 1:
            # 분할이 필요 없는 경우
            await message.reply_text(f"{prefix}\n\n{text}")
        else:
            # 분할이 필요한 경우
            for i, chunk in enumerate(chunks):
                if i == 0:
                    # 첫 번째 메시지
                    await message.reply_text(f"{prefix}\n\n{chunk}")
                else:
                    # 연속 메시지
                    await message.reply_text(f"[계속]\n\n{chunk}")
                
                # 메시지 간 짧은 지연 (스팸 방지)
                if i < len(chunks) - 1:  # 마지막 메시지가 아닌 경우만
                    import asyncio
                    await asyncio.sleep(0.5)
                    
    except Exception as e:
        logger.error(f"긴 메시지 전송 중 오류: {e}")
        # 오류 발생 시 기본 방식으로 전송 시도
        try:
            await message.reply_text(f"{prefix}\n\n{text[:SAFE_MESSAGE_LENGTH]}...")
        except Exception as fallback_error:
            logger.error(f"폴백 메시지 전송도 실패: {fallback_error}")
            await message.reply_text("❌ 메시지가 너무 길어 전송할 수 없습니다. 더 짧은 요청을 해주세요.")

def get_json_format_for_stage(stage):
    """각 단계별 JSON 형식 반환"""
    formats = {
        "개요": '''```json
{
    "title": "시나리오 제목",
    "theme": "테마 (미스터리, 탐험, 구출 등)",
    "setting": "배경 설정",
    "main_conflict": "주요 갈등",
    "objective": "목표",
    "rewards": "보상"
}
```''',
        "에피소드": '''```json
{
    "title": "에피소드 제목",
    "objective": "에피소드 목표",
    "events": ["주요 사건1", "주요 사건2"],
    "player_options": ["플레이어 선택지1", "플레이어 선택지2"],
    "success_result": "성공 시 결과",
    "failure_result": "실패 시 결과"
}
```''',
        "NPC": '''```json
{
    "name": "NPC 이름",
    "appearance": "외모 설명",
    "personality": "성격",
    "motivation": "동기",
    "relationship": "플레이어와의 관계 (적, 동료, 중립)",
    "information": "가진 정보",
    "abilities": "특별한 능력",
    "dialogue_style": "대화 스타일"
}
```''',
        "힌트": '''```json
{
    "content": "힌트 내용",
    "discovery_method": "발견 방법 (조사, 대화, 관찰 등)",
    "connected_info": "연결되는 정보",
    "difficulty": "난이도 (쉬움, 보통, 어려움)",
    "relevant_sessions": ["관련 세션1", "관련 세션2"]
}
```''',
        "던전": '''```json
{
    "name": "장소 이름",
    "type": "장소 유형 (고대 유적, 폐성, 지하 동굴 등)",
    "description": "장소 설명",
    "atmosphere": "분위기",
    "rooms": ["주요 방/구역1", "주요 방/구역2"],
    "traps": ["함정1", "함정2"],
    "puzzles": ["퍼즐1", "퍼즐2"],
    "monsters": ["몬스터1", "몬스터2"],
    "treasures": ["보물1", "보물2"]
}
```'''
    }
    return formats.get(stage, "올바른 JSON 형식")

def load_session_files_context(user_id):
    """세션별로 생성된 파일들을 컨텍스트로 로드 (요약 형태)"""
    context_parts = []
    
    # 세션 파일들 디렉토리 생성
    os.makedirs(f'sessions/user_{user_id}', exist_ok=True)
    
    # 🆕 시나리오 매니저 데이터 로드 (간소화 - 메모리 안전)
    try:
        from scenario_manager import scenario_manager
        scenario_data = scenario_manager.load_scenario(user_id)
        if scenario_data:
            scenario_context = "📋 **시나리오:**\n"
            
            # 기본 정보만 로드
            overview = scenario_data.get("scenario", {}).get("overview", {})
            if overview.get("theme"):
                scenario_context += f"🎭 {overview['theme']}\n"
            if overview.get("objective"):
                scenario_context += f"🎯 {overview['objective'][:100]}...\n"
            
            # 🆕 반복 상황 감지만 유지
            sessions = scenario_data.get("scenario", {}).get("sessions", [])
            if sessions:
                play_count = sessions[-1].get('play_count', 0)
                if play_count > 50:
                    scenario_context += f"🚨 {play_count}라운드 진행됨 - 상황 전개 필요\n"
            
            context_parts.append(scenario_context[:500])  # 크기 제한
            
    except Exception as e:
        logger.error(f"시나리오 데이터 로드 오류: {e}")
        # 오류 발생 시 빈 컨텍스트로 진행
    
    # 🆕 NPC 정보 로드 (시나리오와 연동)
    if npc_manager:
        try:
            npcs = npc_manager.load_npcs(user_id)
            if npcs:
                npc_context = "👥 **현재 NPC들:**\n"
                for npc in npcs[:5]:  # 최대 5명만 표시
                    name = npc.get('name', '이름없음')
                    personality = npc.get('personality', '성격 없음')
                    relationship = npc.get('relationship', '관계 없음')
                    npc_context += f"  • {name}: {personality[:80]}... (관계: {relationship})\n"
                
                context_parts.append(truncate_text_safely(npc_context, 600))
        except Exception as e:
            logger.error(f"NPC 정보 로드 오류: {e}")
    
    # 기존 세션 파일들 (보조적으로)
    session_files = [
        ('scenario.json', '시나리오'),
        ('adventure.json', '모험'),
        ('dungeon.json', '던전'),
        ('party.json', '파티')
    ]
    
    for filename, label in session_files:
        file_path = f'sessions/user_{user_id}/{filename}'
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                summary = f"📄 **{label} 파일:**\n"
                if 'session_type' in data:
                    summary += f"- 타입: {data['session_type']}\n"
                if 'completed_at' in data:
                    summary += f"- 완료: {data['completed_at']}\n"
                if 'conversation' in data and data['conversation']:
                    recent_conv = data['conversation'][-2:] if len(data['conversation']) > 2 else data['conversation']
                    summary += f"- 최근 대화: {len(recent_conv)}개\n"
                
                context_parts.append(truncate_text_safely(summary, 300))
            except Exception as e:
                logger.error(f"{label} 파일 로드 오류: {e}")
    
    # 컨텍스트 최적화 적용
    if context_parts:
        optimized_parts = optimize_context_parts(context_parts, max_total_length=3000)  # 증가된 제한
        return "\n\n".join(optimized_parts)
    
    return ""

def get_session_prompt(session_type, user_id):
    """세션별 LLM 프롬프트 생성"""
    base_context = """당신은 '울타리 너머 - 또 다른 모험으로' TRPG의 마스터입니다. 
다음 규칙을 따라 플레이어를 도와주세요:

- 로우 판타지 세팅으로 젊은 영웅들의 성장기
- 마법은 신비롭고 희귀하며 위험함
- 위험과 취약성을 강조하되 절망적이지 않게
- 마을을 소중한 고향으로 묘사

"""
    
    if session_type == "시나리오_생성":
        # 시나리오 생성 단계별 프롬프트 반환
        current_stage = scenario_manager.get_current_stage(user_id)
        stage_prompt = scenario_manager.get_stage_prompt(current_stage)
        
        # 단계별 구체적인 가이드라인과 예시 제공
        stage_examples = {
            "개요": """
**구체적인 가이드라인:**
- **테마 선택**: 미스터리, 탐험, 구출, 복수, 수사, 전투, 정치 음모 중 선택
- **배경 설정**: 특정 지역을 선택 (마을, 도시, 숲, 던전, 성, 폐허 등)
- **규모**: 소규모(1-2세션), 중간(3-5세션), 대규모(6+세션) 중 선택

**예시 템플릿:**
"[지역명]에서 시작하는 [테마] 시나리오를 만들어주세요. 
제목: '[흥미로운 제목]', 테마: [선택한 테마], 배경: [구체적 배경], 
주요 갈등: [핵심 문제], 목표: [플레이어가 달성해야 할 것], 예상 진행: [대략적 흐름]"

**참고 예시:** 
"그린필드 마을에서 시작하는 미스터리 시나리오를 만들어주세요. 
제목: '그린필드 마을의 수수께끼', 테마: 미스터리, 배경: 중세 판타지 작은 마을, 
주요 갈등: 마을의 이상한 사건들과 숨겨진 음모, 목표: 사건의 진상 규명과 원흉 처단"
""",
            "에피소드": """
**구체적인 가이드라인:**
- **3-5개의 주요 에피소드**로 구성 (너무 많으면 복잡함)
- **각 에피소드는 명확한 목표**를 가져야 함
- **난이도 상승 구조**: 쉬운 것부터 어려운 것 순서로
- **다양한 활동**: 조사→전투→퍼즐→탐험→클라이맥스 등 균형

**참고 예시:**
"이 시나리오를 3-4개의 주요 에피소드로 나누어 구성해주세요.
에피소드 1: [초기 사건 조사와 단서 발견]
에피소드 2: [중간 전개와 갈등 심화] 
에피소드 3: [핵심 장소 탐험이나 결정적 전투]
에피소드 4: [클라이맥스와 해결] (선택적)"
""",
            "NPC": """
**구체적인 가이드라인:**
- **핵심 NPC 3-5명**: 시나리오의 중심인물들 (의뢰인, 조력자, 적대자, 중요 증인 등)
- **보조 NPC 5-10명**: 정보 제공자, 상인, 경비, 마을 사람들
- **각 NPC별 역할**: 명확한 목적과 플레이어와의 관계 설정
- **대화 스타일**: 각자의 개성과 말투

**참고 예시:**
"주요 NPC들을 만들어주세요:
- 핵심 NPC: 의뢰인(촌장 윌리엄), 조력자(경비대장 마리아), 적대자(신비한 방문자), 증인(노인 상인)
- 보조 NPC: 여관 주인, 대장간 주인, 마을 아이들, 수상한 상인, 은둔 현자 등
각 NPC의 성격, 동기, 비밀을 설정해주세요."
""",
            "힌트": """
**구체적인 가이드라인:**
- **물리적 단서**: 발자국, 찢어진 천, 떨어진 물건, 혈흔 등
- **정보적 단서**: 목격담, 소문, 기록, 편지 등  
- **환경적 단서**: 이상한 냄새, 소음, 온도 변화, 분위기 등
- **난이도별 분류**: 쉽게 찾을 수 있는 것 vs 조사/굴림이 필요한 것

**참고 예시:**
"플레이어들이 발견할 수 있는 힌트들을 설정해주세요:
- 명백한 단서: 이상한 발자국, 사라진 물건들, 밤중의 괴상한 소음
- 조사 필요: 숨겨진 편지, 증인의 모순된 증언, 현장의 미묘한 흔적  
- 고급 단서: 마법적 잔재, 고대 문양, 암호화된 메시지
각 힌트가 어떤 정보로 이어지는지 연결고리도 설정해주세요."
""",
            "던전": """
**구체적인 가이드라인:**
- **던전 유형**: 고대 유적, 폐성, 지하 동굴, 마법사 탑, 숨겨진 지하실 등
- **규모**: 소형(3-5개 방), 중형(6-10개 방), 대형(10+개 방)
- **테마 일관성**: 던전의 역사와 분위기가 시나리오와 연결되어야 함
- **균형잡힌 요소**: 전투, 함정, 퍼즐, 탐험을 적절히 배치

**참고 예시:**
"탐험할 수 있는 던전을 만들어주세요:
- 장소: 버려진 폐가의 지하실 or 고대 신전 or 마법사의 숨겨진 실험실
- 구조: 입구→전실→중앙홀→비밀방→최종방 등 논리적 배치
- 요소들: 가디언 몬스터, 마법 함정, 고대 퍼즐, 숨겨진 보물
- 스토리 연결: 던전이 시나리오의 핵심 비밀과 어떻게 연결되는지"
"""
        }
        
        current_example = stage_examples.get(current_stage, "")
        
        # JSON 형식으로 응답하도록 유도하는 추가 안내
        json_guidance = f"""

**🔥 중요 - 반드시 읽어주세요 🔥**

당신은 지금 **TRPG 시나리오를 창작**하고 있습니다. 실제 게임에서 사용할 콘텐츠를 만들어주세요.

**절대 하지 마세요:**
- "정보를 추출할 수 없습니다" 같은 메타 메시지
- "오류 메시지" 또는 "시스템 메시지" 언급
- "제공된 대화 내용이..." 같은 표현

**반드시 해주세요:**
- 창의적이고 구체적인 시나리오 요소 창작
- 실제 게임에서 사용 가능한 콘텐츠 제작
- 다음 JSON 형식으로 응답:

{get_json_format_for_stage(current_stage)}

**예시처럼 구체적인 내용을 직접 창작해주세요!**
"""
        
        # 사용자 요청 기반 커스터마이징 추가
        user_customization = f"""

**🎯 시나리오 작성 지침:**
당신은 TRPG 시나리오를 **직접 창작**하고 있습니다. 다음을 명심하세요:

✅ DO (해야 할 것):
- 구체적이고 흥미로운 시나리오 요소 창작
- 플레이어블한 실제 게임 콘텐츠 제작
- 창의적이고 독창적인 아이디어 제안
- JSON 형식으로 명확한 정보 제공

❌ DON'T (하지 말 것):
- "정보를 추출할 수 없습니다" 같은 메타 메시지
- "제공된 대화 내용이..." 같은 시스템 오류 언급
- "해당 없음" 또는 빈 값 제공
- 오류 메시지나 시스템 메시지 생성

**🎮 실제 게임에서 사용할 수 있는 콘텐츠를 만들어주세요!**
"""
        
        return base_context + f"""
현재 시나리오 생성 세션입니다. 단계별로 체계적인 시나리오를 만들어보겠습니다.

**현재 단계: {current_stage}**

{stage_prompt}

{current_example}

{user_customization}

{json_guidance}
"""
    
    elif session_type == "모험_생성":
        return base_context + """
현재 모험 생성 세션입니다. 시나리오를 바탕으로 구체적인 모험을 계획하겠습니다:

1. **시작점**: 모험이 시작되는 상황과 장소
2. **단서와 정보**: 플레이어가 수집할 수 있는 정보들
3. **중요 장소**: 방문하게 될 핵심 위치들
4. **만날 인물들**: 도움을 주거나 방해할 NPC들
5. **예상 사건들**: 일어날 수 있는 주요 사건들
6. **클라이맥스**: 모험의 절정과 최종 대결

어떤 방향으로 모험을 진행하고 싶은지 알려주세요.
"""
    
    elif session_type == "던전_생성":
        return base_context + """
현재 던전 생성 세션입니다. 탐험할 던전을 함께 만들어보겠습니다:

1. **던전 유형**: 고대 유적, 폐성, 지하 동굴, 마법사 탑 등
2. **던전 배경**: 만들어진 이유와 역사
3. **구조**: 방의 배치와 연결
4. **주요 방들**: 특별한 의미가 있는 장소들
5. **함정과 퍼즐**: 플레이어를 막는 장애물들
6. **괴물과 수호자**: 던전을 지키는 존재들
7. **보물**: 숨겨진 재화와 마법 물품들

어떤 던전을 탐험하고 싶은지 설명해주세요.
"""
    
    elif session_type == "파티_생성" or session_type == "파티_결성":
        return base_context + """
현재 파티 결성 세션입니다. 모험을 함께할 동료들을 구성하겠습니다:

1. **파티 구성원**: 각자의 역할과 특기
2. **파티 결성 계기**: 어떻게 만나게 되었는지
3. **공통 목표**: 함께 추구하는 바
4. **팀워크**: 서로 어떻게 협력할지
5. **갈등 요소**: 흥미로운 내부 갈등이나 차이점
6. **파티 이름**: 팀의 정체성

파티원들의 배경이나 관계에 대해 알려주세요.
"""
    
    elif session_type == "모험_준비":
        return base_context + """
현재 모험 준비 세션입니다. 본격적인 모험 전 준비를 하겠습니다:

1. **장비 점검**: 필요한 무기, 방어구, 도구들
2. **정보 수집**: 목적지나 적에 대한 사전 조사
3. **계획 수립**: 접근 방법과 전략
4. **역할 분담**: 각자가 맡을 임무
5. **비상 계획**: 위험 상황 대비책
6. **출발 준비**: 마지막 점검 사항들

어떤 준비를 하고 싶은지 알려주세요.
"""

    elif session_type == "모험_진행":
        return base_context + """
현재 모험 진행 세션입니다. 시나리오를 적극적으로 진행하겠습니다:

**🎯 세션 운영 방침:**
- 이전 상황에 대한 묘사는 하지 않습니다. 플레이어의 행동으로 인한 결과만 묘사합니다.
- 플레이어의 행동 선언에 따라 즉시 상황을 전개합니다
- **과거 대화**나 **NPC 대화**를 반복하지 않고 새로운 상황에 집중합니다
- 주변 묘사가 이미 되었다면 묘사하지 않습니다
- 플레이어 행동에 진전이 있도록 대화를 진행합니다
- 전투, 던전 탐험, 상호작용을 통해 시나리오를 역동적으로 진행합니다
- 전투 비중을 다소 높여 새로운 장소에 가면 70% 확률로 전투가 벌어질 수 있도록 합니다.
- 미스터리시나리오에는 상호작용을 중점적으로 하고 전투에는 반드시 이유가 있는 전투로 전투가 끝난뒤 힌트를 얻도록 합니다. 
- 여러명의 플레이어의 개별 행동을 인정하되 하나의 그룹으로 공통된 방향으로 시나리오를 인도합니다.

**⚔️ 행동 처리:**
1. **즉각적 결과**: 플레이어 행동에 대한 구체적인 결과 묘사
2. **상황 전개**: 새로운 위험이나 기회 제시
3. **능동적 진행**: 대기 없이 다음 상황으로 자연스럽게 연결
4. **긴장감 유지**: 지속적인 도전과 선택의 기회 제공
5. **🆕 반복 방지**: 같은 장소나 상황이 반복되면 자동으로 새로운 지역이나 에피소드로 진행

**🚨 반복 상황 감지 시 자동 전환:**
- 5라운드 이상 같은 상황이 지속되면 다음 에피소드로 자동 진행
- 플레이어가 같은 행동을 반복하면 상황을 적극적으로 변화시킴

**🎲 적극적 요소:**
- 전투 시: 구체적인 액션과 주사위 굴림 요청
- 탐험 시: 새로운 발견과 숨겨진 요소들
- 상호작용 시: NPC의 즉각 반응과 상황 변화
- 갈등 시: 긴박한 선택과 결과

**🔄 에피소드 진행 우선순위:**
시나리오의 각 에피소드를 순차적으로 진행하되, 현재 에피소드가 충분히 진행되었다면 자연스럽게 다음 에피소드로 전환해주세요.

플레이어의 다음 행동에 따라 상황을 전개하겠습니다!
"""
    
    else:
        return base_context + f"""
현재 {session_type} 세션입니다. 이 세션에서 무엇을 하고 싶은지 알려주세요.
"""

def save_session_data(user_id, session_type, data):
    """세션 데이터를 파일로 저장 - 강화된 버전"""
    logger.info(f"💾 save_session_data 시작: 사용자 {user_id}, 세션 {session_type}")
    
    try:
        # 사용자 ID와 데이터 유효성 검사
        if not user_id or not session_type or not data:
            logger.error(f"❌ 유효하지 않은 매개변수: user_id={user_id}, session_type={session_type}, data_exists={bool(data)}")
            return False
        
        # 절대 경로 생성 (더 안전)
        import os.path
        base_dir = os.path.abspath("sessions")
        user_dir = os.path.join(base_dir, f"user_{user_id}")
        
        logger.info(f"📁 절대 경로로 디렉토리 생성 시도: {user_dir}")
        
        # 단계별 디렉토리 생성
        try:
            os.makedirs(base_dir, exist_ok=True)
            logger.info(f"✅ 기본 디렉토리 생성: {base_dir}")
            
            os.makedirs(user_dir, exist_ok=True)
            logger.info(f"✅ 사용자 디렉토리 생성: {user_dir}")
        except PermissionError as pe:
            logger.error(f"❌ 권한 오류: {pe}")
            return False
        except OSError as oe:
            logger.error(f"❌ OS 오류: {oe}")
            return False
        
        # 디렉토리 접근 권한 확인
        if not os.access(user_dir, os.W_OK):
            logger.error(f"❌ 디렉토리 쓰기 권한 없음: {user_dir}")
            return False
    
        filename_map = {
            "시나리오_생성": "scenario.json",
            "모험_생성": "adventure.json", 
            "던전_생성": "dungeon.json",
            "파티_생성": "party.json",
            "파티_결성": "party.json",
            "모험_준비": "preparation.json"
        }
        
        filename = filename_map.get(session_type, f"{session_type.replace('_', '-')}.json")
        filepath = os.path.join(user_dir, filename)
        
        logger.info(f"💾 파일 저장 시도: {filepath}")
        
        # 데이터 검증
        try:
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            logger.info(f"📄 저장할 데이터 크기: {len(data_str)} 문자")
            
            # 데이터가 너무 작으면 문제 있음
            if len(data_str) < 20:
                logger.warning(f"⚠️ 데이터가 너무 작음: {data_str}")
                
        except (TypeError, ValueError) as je:
            logger.error(f"❌ 데이터 JSON 직렬화 실패: {je}")
            return False
        
        # 임시 파일에 먼저 저장 후 이동 (원자적 쓰기)
        temp_filepath = f"{filepath}.tmp"
        
        try:
            # 임시 파일에 저장
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()  # 버퍼 강제 플러시
                os.fsync(f.fileno())  # OS 레벨 동기화
            
            # 임시 파일이 제대로 생성되었는지 확인
            if os.path.exists(temp_filepath):
                temp_size = os.path.getsize(temp_filepath)
                logger.info(f"✅ 임시 파일 생성 성공: {temp_size} bytes")
                
                # 임시 파일을 최종 파일로 이동 (원자적 연산)
                if os.path.exists(filepath):
                    os.remove(filepath)  # 기존 파일 삭제
                
                os.rename(temp_filepath, filepath)
                logger.info(f"✅ 파일 이동 완료: {filepath}")
            else:
                logger.error(f"❌ 임시 파일이 생성되지 않음: {temp_filepath}")
                return False
            
            # 최종 파일 확인
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"🎉 {session_type} 데이터 저장 완료: {filepath} (크기: {file_size} bytes)")
                
                # 파일 내용 검증
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                    logger.info(f"✅ 저장된 파일 검증 성공: {len(str(loaded_data))} 문자")
                    return True
                except Exception as ve:
                    logger.error(f"❌ 저장된 파일 검증 실패: {ve}")
                    return False
            else:
                logger.error(f"❌ 최종 파일이 생성되지 않음: {filepath}")
                return False
                
        except PermissionError as pe:
            logger.error(f"❌ 파일 쓰기 권한 오류: {pe}")
            # 임시 파일 정리
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except:
                    pass
            return False
        except Exception as write_error:
            logger.error(f"❌ 파일 쓰기 오류: {write_error}")
            # 임시 파일 정리
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except:
                    pass
            return False
            
    except Exception as e:
        logger.error(f"❌ {session_type} 데이터 저장 중 예상치 못한 오류: {e}")
        logger.error(f"❌ 오류 상세: {str(e)}")
        import traceback
        logger.error(f"❌ 스택 트레이스: {traceback.format_exc()}")
        return False

def test_save_session_data(user_id, session_type="모험_생성"):
    """save_session_data 함수 테스트용 - 강화된 버전"""
    logger.info(f"🧪 save_session_data 강화 테스트 시작")
    
    # 더 큰 테스트 데이터로 실제 사용 시뮬레이션
    test_data = {
        "session_type": session_type,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conversation": [
            "사용자: 안녕하세요", 
            "마스터: 안녕하세요! TRPG를 시작해볼까요?",
            "사용자: 네, 모험을 생성하고 싶어요",
            "마스터: 좋습니다! 어떤 테마의 모험을 원하시나요?",
            "사용자: 미스터리 테마로 해주세요"
        ],
        "user_input": "테스트 완료",
        "test": True,
        "metadata": {
            "test_version": "2.0",
            "test_timestamp": datetime.now().isoformat(),
            "user_agent": "테스트 봇"
        }
    }
    
    logger.info(f"🧪 테스트 데이터 크기: {len(str(test_data))} 문자")
    
    # 여러 타입의 세션으로 테스트
    test_sessions = [session_type, "시나리오_생성", "던전_생성", "파티_생성"]
    
    all_success = True
    
    for test_session in test_sessions:
        logger.info(f"🧪 테스트 중: {test_session}")
        
        # 세션별로 다른 데이터
        session_test_data = test_data.copy()
        session_test_data["session_type"] = test_session
        session_test_data["test_session_name"] = f"테스트_{test_session}"
        
        result = save_session_data(user_id, test_session, session_test_data)
        logger.info(f"🧪 {test_session} 테스트 결과: {result}")
        
        if not result:
            all_success = False
            logger.error(f"❌ {test_session} 테스트 실패")
        else:
            # 생성된 파일 확인
            filename_map = {
                "시나리오_생성": "scenario.json",
                "모험_생성": "adventure.json", 
                "던전_생성": "dungeon.json",
                "파티_생성": "party.json",
                "파티_결성": "party.json",
                "모험_준비": "preparation.json"
            }
            
            filename = filename_map.get(test_session, f"{test_session.replace('_', '-')}.json")
            filepath = f'sessions/user_{user_id}/{filename}'
            
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"✅ {test_session} 파일 확인됨: {filepath} (크기: {file_size} bytes)")
                
                # 파일 내용 검증
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                    logger.info(f"✅ {test_session} 파일 내용 로드 성공: {len(str(loaded_data))} 문자")
                    
                    # 데이터 무결성 검증
                    if loaded_data.get("session_type") == test_session:
                        logger.info(f"✅ {test_session} 데이터 무결성 검증 통과")
                    else:
                        logger.error(f"❌ {test_session} 데이터 무결성 검증 실패")
                        all_success = False
                        
                except Exception as e:
                    logger.error(f"❌ {test_session} 파일 내용 로드 실패: {e}")
                    all_success = False
            else:
                logger.error(f"❌ {test_session} 파일이 생성되지 않음: {filepath}")
                all_success = False
    
    # 전체 결과 요약
    if all_success:
        logger.info(f"🎉 모든 테스트 통과! sessions/user_{user_id} 폴더 확인")
        
        # 폴더 전체 상황 리포트
        user_dir = f'sessions/user_{user_id}'
        if os.path.exists(user_dir):
            files = os.listdir(user_dir)
            logger.info(f"📁 사용자 폴더 내 파일 목록 ({len(files)}개):")
            for file in files:
                file_path = os.path.join(user_dir, file)
                file_size = os.path.getsize(file_path)
                logger.info(f"   📄 {file} ({file_size} bytes)")
        
        return True
    else:
        logger.error(f"❌ 일부 테스트 실패. 로그를 확인해주세요.")
        return False

def extract_session_completion_info(text, session_type, conversation_history):
    """LLM을 사용하여 세션 완료 정보 추출"""
    from trpgbot_ragmd_sentencetr import generate_answer_with_rag, generate_answer_without_rag
    
    # 간단한 키워드 체크 먼저 수행
    completion_keywords = {
        "시나리오_생성": ["시나리오 완성", "시나리오 확정", "이제 모험", "모험으로 넘어", "모험 생성", "다음", "완료"],
        "모험_생성": ["모험 완성", "모험 확정", "던전으로", "던전 생성", "파티 결성", "다음", "완료"],
        "던전_생성": ["던전 완성", "던전 확정", "파티로", "파티 결성", "모험 시작", "다음", "완료"],
        "파티_생성": ["파티 완성", "파티 확정", "모험 준비", "준비 시작", "다음", "완료"],
        "파티_결성": ["결성 완료", "파티 완성", "모험 준비", "준비 시작", "다음", "완료"],
        "모험_준비": ["준비 완료", "준비 끝", "모험 시작", "출발", "다음", "완료"]
    }
    
    keywords = completion_keywords.get(session_type, [])
    for keyword in keywords:
        if keyword in text:
            return True
    
    # LLM을 사용한 세션 완료 판단
    session_descriptions = {
        "시나리오_생성": "시나리오의 주요 갈등, 핵심 NPC, 배경 설정, 목표가 충분히 정해졌는지",
        "모험_생성": "모험의 시작점, 단서, 중요 장소, 예상 사건들이 충분히 계획되었는지",
        "던전_생성": "던전의 유형, 구조, 주요 방들, 함정과 괴물들이 충분히 설계되었는지",
        "파티_생성": "파티 구성원들과 그들의 역할, 관계가 충분히 정해졌는지",
        "파티_결성": "파티 결성 과정과 팀워크가 충분히 논의되었는지",
        "모험_준비": "모험을 위한 장비, 계획, 역할 분담이 충분히 준비되었는지"
    }
    
    if session_type in session_descriptions:
        # 최근 대화 내용 요약
        recent_conversation = conversation_history[-5:] if len(conversation_history) >= 5 else conversation_history
        conversation_text = "\n".join(recent_conversation)
        
        completion_prompt = f"""
다음 대화를 보고 현재 {session_type} 세션이 완료되었는지 판단해주세요.

세션 완료 기준: {session_descriptions[session_type]}

최근 대화:
{conversation_text}

사용자의 마지막 메시지: {text}

위 대화를 보았을 때 {session_type} 세션이 완료되었다고 판단되면 "완료"라고 답하고, 
아직 더 논의가 필요하다면 "진행중"이라고 답해주세요.

답변은 "완료" 또는 "진행중" 중 하나만 해주세요.
"""
        
        try:
            completion_result = generate_answer_without_rag(completion_prompt, [], "기타", "")
            return "완료" in completion_result
        except Exception as e:
            logger.error(f"세션 완료 판단 오류: {e}")
            return False
    
    return False

def get_next_session(current_session):
    """다음 세션 결정"""
    session_flow = {
        "캐릭터_생성": "시나리오_생성",
        "시나리오_생성": "모험_생성", 
        "모험_생성": "던전_생성",
        "던전_생성": "파티_생성",
        "파티_생성": "모험_준비",
        "파티_결성": "모험_준비",
        "모험_준비": "모험_진행"
    }
    return session_flow.get(current_session, "모험_진행")

def update_session_summary(user_id, session_type, conversation_history):
    """세션 진행 상황을 요약하여 파일로 저장 (최적화된 버전)"""
    from trpgbot_ragmd_sentencetr import generate_answer_with_rag, generate_answer_without_rag
    
    try:
        # 최근 대화 내용 (최대 10개로 줄임)
        recent_conversation = conversation_history[-10:] if len(conversation_history) >= 10 else conversation_history
        conversation_text = "\n".join(recent_conversation)
        
        # 대화 내용이 너무 길면 자르기
        conversation_text = truncate_text_safely(conversation_text, max_length=2000, preserve_end=True)
        
        summary_prompt = f"""
다음은 TRPG '{session_type}' 세션의 최근 대화 내용입니다. 
현재까지의 진행 상황을 간결하고 명확하게 요약해주세요.

최근 대화 내용:
{conversation_text}

다음 형식으로 간단히 요약해주세요:

## {session_type} 진행 상황 요약

### 주요 결정사항
- 

### 설정된 내용
- 

### 현재 상태
현재 {session_type} 세션이 [진행중/거의완료/완료] 상태입니다.
"""
        
        # 프롬프트 크기 체크
        prompt_size = len(summary_prompt)
        if prompt_size > LLM_SAFE_CONTEXT_LENGTH:
            logger.warning(f"⚠️ 요약 프롬프트가 너무 큼: {prompt_size}자")
            # 대화 내용을 더 줄임
            conversation_text = truncate_text_safely(conversation_text, max_length=1000, preserve_end=True)
            summary_prompt = f"""
TRPG '{session_type}' 세션의 최근 대화를 간단히 요약해주세요.

최근 대화:
{conversation_text}

간단한 요약:
- 주요 결정사항: 
- 설정된 내용: 
- 현재 상태: {session_type} 세션이 [진행중/완료] 상태
"""
        
        summary = generate_answer_without_rag(summary_prompt, "기타", "")
        
        # 요약 파일 저장
        summary_file = f'sessions/user_{user_id}/session_summary.md'
        os.makedirs(f'sessions/user_{user_id}', exist_ok=True)
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"# TRPG 세션 진행 상황 요약\n\n")
            f.write(f"**마지막 업데이트**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**현재 세션**: {session_type}\n\n")
            f.write(summary)
        
        logger.info(f"세션 요약 업데이트 완료: {summary_file}")
        return summary
        
    except Exception as e:
        logger.error(f"세션 요약 생성 오류: {e}")
        return ""

def load_session_summary(user_id):
    """세션 요약 파일 로드"""
    summary_file = f'sessions/user_{user_id}/session_summary.md'
    
    if os.path.exists(summary_file):
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"세션 요약 로드 오류: {e}")
    
    return ""

def extract_missing_scenario_info(user_id, text, conversation_history):
    """빈 필드만 채우기 위한 LLM 정보 추출"""
    from trpgbot_ragmd_sentencetr import generate_answer_with_rag, generate_answer_without_rag
    
    try:
        # 빈 필드 찾기
        empty_fields = scenario_manager.find_empty_fields(user_id)
        if not empty_fields:
            return False
            
        # 빈 필드 보완 프롬프트 생성
        fill_prompt = scenario_manager.generate_fill_missing_prompt(user_id, empty_fields)
        if not fill_prompt:
            return False
            
        logger.info(f"사용자 {user_id}의 빈 필드 보완 요청: {list(empty_fields.keys())}")
        
        # 프롬프트 크기 체크 및 최적화
        prompt_size = len(fill_prompt)
        if prompt_size > LLM_SAFE_CONTEXT_LENGTH:
            logger.warning(f"⚠️ 빈 필드 보완 프롬프트가 너무 큼: {prompt_size}자")
            fill_prompt = truncate_text_safely(fill_prompt, max_length=LLM_SAFE_CONTEXT_LENGTH, preserve_end=False)
        
        # LLM으로 빈 필드 보완 요청
        completed_info = generate_answer_without_rag(fill_prompt, "시나리오_생성", "")
        
        # JSON 파싱 시도
        try:
            import json
            # JSON 부분만 추출
            if "```json" in completed_info:
                json_start = completed_info.find("```json") + 7
                json_end = completed_info.find("```", json_start)
                json_str = completed_info[json_start:json_end].strip()
            elif "{" in completed_info and "}" in completed_info:
                json_start = completed_info.find("{")
                json_end = completed_info.rfind("}") + 1
                json_str = completed_info[json_start:json_end]
            else:
                return False
                
            parsed_data = json.loads(json_str)
            
            # 빈 필드만 업데이트
            updated = scenario_manager.update_missing_fields(user_id, parsed_data, empty_fields)
            
            if updated:
                logger.info(f"사용자 {user_id}의 빈 필드 보완 완료")
                return True
            else:
                logger.warning(f"사용자 {user_id}의 빈 필드 보완 실패: 데이터 업데이트 안됨")
                return False
                
        except json.JSONDecodeError as e:
            logger.error(f"빈 필드 보완 JSON 파싱 오류: {e}, 추출된 내용: {completed_info}")
            return False
            
    except Exception as e:
        logger.error(f"빈 필드 보완 오류: {e}")
        return False

def extract_and_save_scenario_info(user_id, text, conversation_history):
    """LLM을 사용하여 시나리오 정보를 추출하고 저장"""
    from trpgbot_ragmd_sentencetr import generate_answer_with_rag, generate_answer_without_rag
    
    try:
        current_stage = scenario_manager.get_current_stage(user_id)
        
        # 현재 단계에 맞는 정보 추출 프롬프트
        extraction_prompts = {
            ScenarioStage.OVERVIEW.value: """
다음 대화에서 시나리오 개요 정보를 추출해주세요.

대화 내용: {text}

다음 형식의 JSON으로 답해주세요:
{{
    "title": "시나리오 제목",
    "theme": "테마 (미스터리, 탐험, 구출 등)",
    "setting": "배경 설정",
    "main_conflict": "주요 갈등",
    "objective": "목표",
    "rewards": "보상"
}}

정보가 명확하지 않은 항목은 빈 문자열로 두세요.
""",
            ScenarioStage.EPISODES.value: """
다음 대화에서 에피소드 정보를 추출해주세요.

대화 내용: {text}

다음 형식의 JSON으로 답해주세요:
{{
    "title": "에피소드 제목",
    "objective": "에피소드 목표",
    "events": ["주요 사건1", "주요 사건2"],
    "player_options": ["플레이어 선택지1", "플레이어 선택지2"],
    "success_result": "성공 시 결과",
    "failure_result": "실패 시 결과"
}}
""",
            ScenarioStage.NPCS.value: """
다음 대화에서 NPC 정보를 추출해주세요.

대화 내용: {text}

다음 형식의 JSON으로 답해주세요:
{{
    "name": "NPC 이름",
    "appearance": "외모 설명",
    "personality": "성격",
    "motivation": "동기",
    "relationship": "플레이어와의 관계 (적, 동료, 중립)",
    "information": "가진 정보",
    "abilities": "특별한 능력",
    "dialogue_style": "대화 스타일"
}}
""",
            ScenarioStage.HINTS.value: """
다음 대화에서 힌트 정보를 추출해주세요.

대화 내용: {text}

다음 형식의 JSON으로 답해주세요:
{{
    "content": "힌트 내용",
    "discovery_method": "발견 방법 (조사, 대화, 관찰 등)",
    "connected_info": "연결되는 정보",
    "difficulty": "난이도 (쉬움, 보통, 어려움)",
    "relevant_sessions": ["관련 세션1", "관련 세션2"]
}}
""",
            ScenarioStage.DUNGEONS.value: """
다음 대화에서 던전/탐험지 정보를 추출해주세요.

대화 내용: {text}

다음 형식의 JSON으로 답해주세요:
{{
    "name": "장소 이름",
    "type": "장소 유형 (고대 유적, 폐성, 지하 동굴 등)",
    "description": "장소 설명",
    "atmosphere": "분위기",
    "rooms": ["주요 방/구역1", "주요 방/구역2"],
    "traps": ["함정1", "함정2"],
    "puzzles": ["퍼즐1", "퍼즐2"],
    "monsters": ["몬스터1", "몬스터2"],
    "treasures": ["보물1", "보물2"]
}}
"""
        }
        
        if current_stage not in extraction_prompts:
            return False
            
        prompt = extraction_prompts[current_stage].format(text=text)
        
        # 프롬프트 크기 체크 및 최적화
        prompt_size = len(prompt)
        if prompt_size > LLM_SAFE_CONTEXT_LENGTH:
            logger.warning(f"⚠️ 시나리오 정보 추출 프롬프트가 너무 큼: {prompt_size}자")
            prompt = truncate_text_safely(prompt, max_length=LLM_SAFE_CONTEXT_LENGTH, preserve_end=False)
        
        # LLM으로 정보 추출
        extracted_info = generate_answer_without_rag(prompt, "기타", "")
        
        # JSON 파싱 시도
        try:
            import json
            # JSON 부분만 추출 (```json과 ``` 사이의 내용)
            if "```json" in extracted_info:
                json_start = extracted_info.find("```json") + 7
                json_end = extracted_info.find("```", json_start)
                json_str = extracted_info[json_start:json_end].strip()
            elif "{" in extracted_info and "}" in extracted_info:
                json_start = extracted_info.find("{")
                json_end = extracted_info.rfind("}") + 1
                json_str = extracted_info[json_start:json_end]
            else:
                return False
                
            parsed_data = json.loads(json_str)
            
            # 추출된 정보가 유효한지 확인
            if isinstance(parsed_data, dict):
                if not any(parsed_data.values()):
                    return False
                    
                # 오류 메시지나 메타 메시지 필터링
                error_keywords = [
                    "추출할 수 없", "오류 메시지", "시스템 오류", "제공된 대화", 
                    "해당 없음", "정보를 파악", "죄송합니다", "메시지 감지",
                    "시스템 응답", "게임 세션의 대화가 아닌"
                ]
                
                # 모든 값에서 오류 키워드 확인
                for key, value in parsed_data.items():
                    if isinstance(value, str):
                        for keyword in error_keywords:
                            if keyword in value:
                                logger.warning(f"오류 메시지 감지됨: {key} = {value[:50]}...")
                                return False
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                for keyword in error_keywords:
                                    if keyword in item:
                                        logger.warning(f"오류 메시지 감지됨: {key} 리스트 항목 = {item[:50]}...")
                                        return False
                        
            elif isinstance(parsed_data, list):
                if not parsed_data:
                    return False
            else:
                return False
                
            # 시나리오 매니저를 통해 정보 저장
            if current_stage == ScenarioStage.OVERVIEW.value:
                scenario_manager.update_scenario_overview(user_id, parsed_data)
            elif current_stage == ScenarioStage.EPISODES.value:
                scenario_manager.add_episode(user_id, parsed_data)
            elif current_stage == ScenarioStage.NPCS.value:
                scenario_manager.add_npc(user_id, parsed_data)
            elif current_stage == ScenarioStage.HINTS.value:
                scenario_manager.add_hint(user_id, parsed_data)
            elif current_stage == ScenarioStage.DUNGEONS.value:
                scenario_manager.add_dungeon(user_id, parsed_data)
                
            logger.info(f"시나리오 {current_stage} 정보 추출 및 저장 완료: {user_id}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}, 추출된 내용: {extracted_info}")
            return False
            
    except Exception as e:
        logger.error(f"시나리오 정보 추출 오류: {e}")
        return False

def check_message_length(text: str) -> dict:
    """
    메시지 길이를 체크하고 정보를 반환하는 함수
    
    Args:
        text (str): 체크할 텍스트
    
    Returns:
        dict: 길이 정보와 분할 필요 여부
    """
    length = len(text)
    needs_split = length > SAFE_MESSAGE_LENGTH
    
    return {
        "length": length,
        "safe_length": SAFE_MESSAGE_LENGTH,
        "max_length": TELEGRAM_MAX_MESSAGE_LENGTH,
        "needs_split": needs_split,
        "chunks_needed": (length // SAFE_MESSAGE_LENGTH) + 1 if needs_split else 1,
        "status": "길이 초과" if needs_split else "정상"
    }

def test_message_splitting():
    """메시지 분할 기능 테스트"""
    # 테스트 메시지들
    test_messages = [
        "짧은 메시지",
        "중간 길이의 메시지입니다. " * 50,  # 약 1000자
        "긴 메시지입니다. " * 300,  # 약 4500자 (분할 필요)
        "매우 긴 메시지입니다. " * 600,  # 약 9000자 (여러 번 분할 필요)
    ]
    
    print("📊 메시지 분할 테스트 결과:")
    print("=" * 50)
    
    for i, msg in enumerate(test_messages, 1):
        info = check_message_length(msg)
        chunks = split_long_message(msg)
        
        print(f"\n테스트 {i}:")
        print(f"  원본 길이: {info['length']}자")
        print(f"  상태: {info['status']}")
        print(f"  분할 필요: {'예' if info['needs_split'] else '아니오'}")
        print(f"  예상 청크 수: {info['chunks_needed']}")
        print(f"  실제 청크 수: {len(chunks)}")
        
        if len(chunks) > 1:
            print(f"  청크 길이들: {[len(chunk) for chunk in chunks]}")
    
    print("\n✅ 테스트 완료!")

def check_repetitive_situation_in_context(scenario_context, conversation_history):
    """시나리오 컨텍스트와 대화 기록에서 반복 상황 감지"""
    try:
        # 반복 키워드 패턴 확인
        repetitive_keywords = [
            "지하실", "끈적", "상자", "자물쇠", "쇠사슬", "녹슨",
            "어둠", "곰팡이", "습기", "버려진", "폐가", "던전",
            "같은 방", "다시", "또다시", "계속", "반복"
        ]
        
        # 최근 대화에서 반복 키워드 빈도 확인
        recent_conversations = conversation_history[-10:] if len(conversation_history) >= 10 else conversation_history
        recent_text = "\n".join(recent_conversations).lower()
        
        keyword_count = {}
        for keyword in repetitive_keywords:
            count = recent_text.count(keyword)
            if count > 0:
                keyword_count[keyword] = count
        
        # 같은 키워드가 3번 이상 나타나면 반복 상황으로 판단
        high_frequency_keywords = [k for k, v in keyword_count.items() if v >= 3]
        
        if high_frequency_keywords:
            logger.info(f"🔄 반복 키워드 감지: {high_frequency_keywords}")
            return True
        
        # 시나리오 컨텍스트에서 현재 에피소드 진행도 확인
        if "에피소드" in scenario_context:
            # 현재 에피소드가 5라운드 이상 진행되었는지 확인
            if "라운드" in recent_text:
                import re
                round_matches = re.findall(r'라운드\s*(\d+)', recent_text)
                if round_matches:
                    latest_round = max(int(r) for r in round_matches)
                    if latest_round >= 5:
                        logger.info(f"🔄 라운드 반복 감지: {latest_round}라운드")
                        return True
        
        return False
        
    except Exception as e:
        logger.error(f"반복 상황 감지 중 오류: {e}")
        return False

def force_episode_progression_context(user_id, scenario_context):
    """에피소드 강제 진행을 위한 컨텍스트 생성"""
    try:
        # 현재 에피소드 정보 확인
        current_episode = scenario_manager.get_current_episode(user_id)
        next_episode_info = scenario_manager.get_next_episode_info(user_id)
        
        if not next_episode_info:
            # 다음 에피소드가 없으면 새로운 장소로 전환
            progression_prompts = [
                """
🚪 **새로운 발견**

현재 상황을 마무리하고 새로운 발견을 하게 됩니다:
- 숨겨진 통로나 문이 나타남
- 새로운 지역으로 이어지는 길 발견
- 완전히 다른 환경으로 자연스럽게 전환
- 새로운 NPC나 상황과의 만남

플레이어들에게 새로운 선택지와 도전을 제시해주세요.
""",
                """
⭐ **상황 전환**

현재 진행중인 상황에서 예상치 못한 전환이 일어납니다:
- 갑작스러운 사건이나 방해물 등장
- 새로운 정보나 단서의 발견
- 다른 장소로의 이동 필요성 발생
- 시간이나 상황의 급격한 변화

흥미진진한 새로운 전개로 이어가주세요.
""",
                """
🗺️ **장소 이동**

현재 탐험을 마무리하고 다음 목적지로 향합니다:
- 새로운 마을이나 지역으로 이동
- 다른 던전이나 탐험지 발견
- 중요한 인물이나 의뢰인과의 만남
- 완전히 새로운 모험의 시작

새로운 환경과 도전을 제공해주세요.
"""
            ]
            
            import random
            return random.choice(progression_prompts)
        else:
            # 다음 에피소드 정보를 활용한 진행
            episode_title = next_episode_info.get("title", "다음 에피소드")
            episode_objective = next_episode_info.get("objective", "새로운 목표")
            
            progression_context = f"""
🎬 **다음 에피소드 진행**

현재 에피소드를 마무리하고 다음 에피소드로 자연스럽게 전환합니다:

**다음 에피소드**: {episode_title}
**목표**: {episode_objective}

{scenario_context}

위 시나리오 정보를 바탕으로:
- 현재 상황을 마무리하되 갑작스럽지 않게 전환
- 다음 에피소드의 목표와 상황을 자연스럽게 도입
- 플레이어들에게 새로운 행동 방향 제시
- 흥미로운 새로운 요소나 도전 과제 제공

새로운 에피소드의 시작에 맞는 상황을 연출해주세요.
"""
            
            # 에피소드 진행 상태 업데이트
            scenario_manager.advance_to_next_episode(user_id)
            
            return progression_context
            
    except Exception as e:
        logger.error(f"에피소드 강제 진행 컨텍스트 생성 오류: {e}")
        return None

# 일반 텍스트 메시지 처리 함수
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 텍스트 메시지 (명령어 제외)를 보냈을 때 호출되는 함수입니다.
    받은 메시지에 응답합니다.
    """
    message = update.message # 수신된 메시지 객체
    user = update.effective_user # 메시지를 보낸 사용자 정보
    text = message.text # 메시지 내용
    user_id = user.id
    
    # 사용자 대화 기록 저장
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    # 현재 메시지 저장 - 'user: text' 형식으로 저장
    user_conversations[user_id].append(f"{user.username or user.first_name}: {text}")
    
    # 현재 세션 상태 확인
    current_session = session_manager.get_current_session(user_id)
    session_type = current_session["current_session_type"] if current_session else "기타"
    
    # 세션 로그에 사용자 메시지 기록 (길이 제한)
    user_message_log = f"사용자 메시지: {text[:100]}" + ("..." if len(text) > 100 else "")
    session_manager.log_session(
        user_id, 
        session_type, 
        user_message_log
    )
    
    # 🧪 디버깅용: save_session_data 테스트
    if "테스트 세션 저장" in text or "test session save" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 세션 저장 테스트 요청")
        test_result = test_save_session_data(user_id, session_type)
        
        if test_result:
            await message.reply_text(f"✅ **세션 저장 테스트 성공!**\n\n세션 타입: `{session_type}`\n파일이 `sessions/user_{user_id}/` 폴더에 생성되었습니다.")
        else:
            await message.reply_text(f"❌ **세션 저장 테스트 실패**\n\n세션 타입: `{session_type}`\n로그를 확인해주세요.")
        return
    
    # 🧪 디버깅용: 메시지 길이 테스트
    if "테스트 메시지 길이" in text or "test message length" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 메시지 길이 테스트 요청")
        
        # 테스트 메시지 생성 (긴 메시지)
        test_long_message = "이것은 텔레그램 메시지 길이 제한 테스트입니다. " * 200  # 약 5000자
        
        # 길이 정보 체크
        length_info = check_message_length(test_long_message)
        
        info_message = f"""📊 **메시지 길이 테스트 결과**

🔍 **길이 정보:**
• 원본 길이: {length_info['length']:,}자
• 안전 길이: {length_info['safe_length']:,}자
• 최대 길이: {length_info['max_length']:,}자
• 상태: {length_info['status']}
• 분할 필요: {'예' if length_info['needs_split'] else '아니오'}
• 예상 청크 수: {length_info['chunks_needed']}개

🧪 **실제 긴 메시지를 전송해보겠습니다...**"""
        
        await message.reply_text(info_message)
        
        # 실제 긴 메시지 전송 테스트
        await send_long_message(message, test_long_message, "🧪 [테스트 긴 메시지]")
        return
    
    # 🧪 디버깅용: LLM 컨텍스트 크기 테스트
    if "테스트 컨텍스트 크기" in text or "test context size" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 LLM 컨텍스트 크기 테스트 요청")
        
        # 현재 컨텍스트 부분들 수집 (실제 처리와 동일)
        test_context_parts = []
        
        # 캐릭터 정보
        character_data = user_characters.get(user_id) or CharacterManager.load_character(user_id)
        if character_data:
            character_sheet = CharacterManager.format_character_sheet(character_data)
            test_context_parts.append(f"플레이어 캐릭터 정보:\n{character_sheet}")
        
        # 시나리오 컨텍스트
        scenario_context = scenario_manager.get_scenario_context_for_mastering(user_id, session_type)
        if scenario_context:
            test_context_parts.append(scenario_context)
        
        # 세션 파일들
        session_files_context = load_session_files_context(user_id)
        if session_files_context:
            test_context_parts.append(session_files_context)
        
        # 세션 요약
        session_summary = load_session_summary(user_id)
        if session_summary:
            test_context_parts.append(f"지금까지의 상황 요약:\n{session_summary}")
        
        # 세션 프롬프트
        if session_type != "캐릭터_생성" and session_type != "기타":
            session_prompt_context = get_session_prompt(session_type, user_id)
            test_context_parts.append(f"현재 세션 안내:\n{session_prompt_context}")
        
        # 크기 분석
        size_info = check_context_size(test_context_parts, LLM_SAFE_CONTEXT_LENGTH)
        
        # 최적화 테스트
        optimized_parts = optimize_context_parts(test_context_parts, LLM_SAFE_CONTEXT_LENGTH)
        optimized_size_info = check_context_size(optimized_parts, LLM_SAFE_CONTEXT_LENGTH)
        
        result_message = f"""📊 **LLM 컨텍스트 크기 분석 결과**

🔍 **원본 컨텍스트:**
• 총 길이: {size_info['total_length']:,}자
• 부분 수: {size_info['parts_count']}개
• 평균 부분 크기: {size_info['average_part_size']:,}자
• 상태: {size_info['status']}
• 줄여야 할 크기: {size_info['reduction_needed']:,}자

✅ **최적화 후:**
• 총 길이: {optimized_size_info['total_length']:,}자
• 부분 수: {optimized_size_info['parts_count']}개
• 상태: {optimized_size_info['status']}
• 절약된 크기: {size_info['total_length'] - optimized_size_info['total_length']:,}자

📏 **제한 기준:**
• 안전 길이: {LLM_SAFE_CONTEXT_LENGTH:,}자
• 최대 길이: {LLM_MAX_CONTEXT_LENGTH:,}자"""
        
        await message.reply_text(result_message)
        return
    
    # 🧪 디버깅용: 세션 로그 정리 테스트
    if "테스트 로그 정리" in text or "test log cleanup" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 로그 정리 테스트 요청")
        
        # 현재 로그 파일 상태 확인
        log_file = f'sessions/session_log_{user_id}.txt'
        
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file)
            
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            before_info = f"""📊 **로그 정리 전 상태:**
• 파일 크기: {file_size:,} bytes
• 총 라인 수: {len(lines):,}개
• 파일 경로: {log_file}"""
            
            await message.reply_text(before_info)
            
            # 로그 정리 실행
            session_manager.clean_old_logs(user_id, days_to_keep=7)  # 7일 이상 된 로그 정리
            
            # 정리 후 상태 확인
            if os.path.exists(log_file):
                new_file_size = os.path.getsize(log_file)
                
                with open(log_file, 'r', encoding='utf-8') as f:
                    new_lines = f.readlines()
                
                after_info = f"""✅ **로그 정리 후 상태:**
• 파일 크기: {new_file_size:,} bytes (변화: {new_file_size - file_size:+,} bytes)
• 총 라인 수: {len(new_lines):,}개 (변화: {len(new_lines) - len(lines):+,}개)
• 정리 효과: {((file_size - new_file_size) / file_size * 100) if file_size > 0 else 0:.1f}% 감소"""
                
                await message.reply_text(after_info)
            else:
                await message.reply_text("⚠️ 로그 파일이 삭제되었습니다.")
        else:
            await message.reply_text("📝 로그 파일이 아직 생성되지 않았습니다.")
        
        return
    
    # 캐릭터 생성 세션 특별 처리
    if session_type == "캐릭터_생성":
        # 플레이어 수 확인
        if not CharacterManager.is_player_count_set(user_id):
            # 플레이어 수 질문에 대한 응답인지 확인
            if text.isdigit() and 1 <= int(text) <= 10:
                player_count = int(text)
                CharacterManager.set_player_count(user_id, player_count)
                await message.reply_text(f"플레이어 수를 {player_count}명으로 설정했습니다. 이제 첫 번째 캐릭터를 생성해 보겠습니다.\n\n캐릭터의 이름, 클래스, 가치관, 능력치 등을 알려주세요.")
                return
            elif "캐릭터" in text and ("생성" in text or "만들" in text):
                # 캐릭터 생성 요청이면 플레이어 수 물어보기
                await message.reply_text("몇 명의 플레이어가 함께 할지 알려주세요? (1~10)")
                return
        else:
            # 플레이어 수와 생성된 캐릭터 수 확인
            player_count, completed_count = CharacterManager.get_player_count_and_completed(user_id)
            current_index = CharacterManager.get_current_character_index(user_id)
            
            # 랜덤 캐릭터 생성 요청 확인
            if ("랜덤" in text or "무작위" in text) and ("생성" in text or "만들" in text or "생성해줘" in text or "만들어줘" in text):
                # 랜덤 캐릭터 생성
                character_data = CharacterManager.generate_random_character(user_id)
                
                # 플레이어 정보가 설정되지 않은 경우 물어보기
                if not character_data.get("플레이어"):
                    # 임시 상태 저장
                    context.user_data['awaiting_player_for_char'] = True
                    
                    # 캐릭터 정보 표시
                    character_sheet = CharacterManager.format_character_sheet(character_data)
                    
                    await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n이 캐릭터를 누가 플레이할지 알려주세요. (예: '이 캐릭터는 철수가 플레이합니다')")
                    return
                
                # 캐릭터 정보 표시
                character_sheet = CharacterManager.format_character_sheet(character_data)
                
                # 완료된 캐릭터 수 증가 및 다음 캐릭터 준비
                CharacterManager.increment_completed_character(user_id)
                completed_count += 1
                
                if player_count > completed_count:
                    # 아직 생성할 캐릭터가 남아있음
                    await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n{current_index + 1}번째 캐릭터 생성이 완료되었습니다!\n이제 {current_index + 2}번째 캐릭터를 생성해 보겠습니다.\n다음 캐릭터의 이름, 클래스, 가치관, 능력치 등을 알려주세요.")
                    return
                else:
                    # 모든 캐릭터 생성 완료 - 자동으로 다음 세션으로 이동
                    next_session = get_next_session("캐릭터_생성")
                    session_manager.log_session(user_id, next_session, "자동 세션 전환: 캐릭터 생성 완료")
                    
                    session_prompt = get_session_prompt(next_session, user_id)
                    await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n🎉 축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다.\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                    return
            # 플레이어 지정 응답 확인
            elif 'awaiting_player_for_char' in context.user_data and context.user_data['awaiting_player_for_char']:
                # 사용자 응답에서 플레이어 정보 추출
                player_name = None
                
                # 간단한 패턴 매칭으로 플레이어 이름 추출 시도
                if "플레이" in text:
                    # '철수가 플레이' 같은 패턴 찾기
                    match = re.search(r'([가-힣a-zA-Z0-9_]+)[이가]\s*플레이', text)
                    if match:
                        player_name = match.group(1)
                    else:
                        # '플레이어는 철수' 같은 패턴 찾기
                        match = re.search(r'플레이어[는은]\s*([가-힣a-zA-Z0-9_]+)', text)
                        if match:
                            player_name = match.group(1)
                
                # 패턴 매칭으로 찾지 못했다면 전체 텍스트 사용
                if not player_name:
                    player_name = text.strip()
                
                # 캐릭터 데이터 로드 및 플레이어 정보 업데이트
                character_data = CharacterManager.load_character(user_id)
                if character_data:
                    character_data["플레이어"] = player_name
                    CharacterManager.save_character(user_id, character_data)
                    
                    # 모든 랜덤 생성 모드인지 확인
                    generating_all_random = context.user_data.get('generating_all_random', False)
                    
                    # 임시 상태 제거
                    del context.user_data['awaiting_player_for_char']
                    
                    # 캐릭터 정보 표시
                    character_sheet = CharacterManager.format_character_sheet(character_data)
                    
                    # 완료된 캐릭터 수 증가 및 다음 캐릭터 준비
                    CharacterManager.increment_completed_character(user_id)
                    completed_count += 1
                    
                    if player_count > completed_count:
                        # 아직 생성할 캐릭터가 남아있음
                        if generating_all_random:
                            # 다음 랜덤 캐릭터 자동 생성
                            await message.reply_text(f"플레이어 정보를 '{player_name}'(으)로 업데이트했습니다!\n\n{character_sheet}\n\n이제 다음 캐릭터를 생성합니다.")
                            
                            # 다음 랜덤 캐릭터 생성
                            next_character_data = CharacterManager.generate_random_character(user_id)
                            
                            # 임시 상태 저장
                            context.user_data['awaiting_player_for_char'] = True
                            context.user_data['generating_all_random'] = True
                            
                            # 다음 캐릭터 정보 표시
                            next_character_sheet = CharacterManager.format_character_sheet(next_character_data)
                            
                            # 다음 플레이어 정보 요청
                            await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{next_character_sheet}\n\n이 캐릭터를 누가 플레이할지 알려주세요.")
                            return
                        else:
                            await message.reply_text(f"플레이어 정보를 '{player_name}'(으)로 업데이트했습니다!\n\n{character_sheet}\n\n{current_index + 1}번째 캐릭터 생성이 완료되었습니다!\n이제 {current_index + 2}번째 캐릭터를 생성해 보겠습니다.\n다음 캐릭터의 이름, 클래스, 가치관, 능력치 등을 알려주세요.")
                            return
                    else:
                        # 모든 캐릭터 생성 완료 - 자동으로 다음 세션으로 이동
                        if 'generating_all_random' in context.user_data:
                            del context.user_data['generating_all_random']
                        
                        next_session = get_next_session("캐릭터_생성")
                        session_manager.log_session(user_id, next_session, "자동 세션 전환: 캐릭터 생성 완료")
                        
                        session_prompt = get_session_prompt(next_session, user_id)
                        await message.reply_text(f"플레이어 정보를 '{player_name}'(으)로 업데이트했습니다!\n\n{character_sheet}\n\n🎉 축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다.\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                        return

            elif "모두" in text and ("랜덤" in text or "무작위" in text):
                # 플레이어들에게 각각 캐릭터를 할당해야 함을 안내
                await message.reply_text(f"알겠습니다! {player_count - completed_count}명의 캐릭터를 랜덤으로 생성하겠습니다. 각 캐릭터를 누가 플레이할지 차례대로 알려주세요.")
                
                # 한 명씩 생성하기
                if completed_count < player_count:
                    # 랜덤 캐릭터 생성
                    character_data = CharacterManager.generate_random_character(user_id)
                    
                    # 임시 상태 저장 (모두 랜덤 생성 모드)
                    context.user_data['awaiting_player_for_char'] = True
                    context.user_data['generating_all_random'] = True
                    
                    # 캐릭터 정보 표시
                    character_sheet = CharacterManager.format_character_sheet(character_data)
                    
                    # 플레이어 정보 요청
                    await message.reply_text(f"첫 번째 랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n이 캐릭터를 누가 플레이할지 알려주세요. (예: '이 캐릭터는 철수가 플레이합니다')")
                    return
                else:
                    # 모든 캐릭터가 이미 완료됨
                    await message.reply_text(f"모든 캐릭터({player_count}명)가 이미 생성되었습니다. 새로운 캐릭터를 만들려면 '/session 캐릭터_생성'으로 세션을 재시작해주세요.")
                    return
    
    # 시나리오 생성 세션 특별 처리
    elif session_type == "시나리오_생성":
        logger.info(f"🎭 시나리오 생성 세션 - 사용자 {user_id}의 요청 처리 중")
        
        # 시나리오 생성 시작 시 사용자 선호도 확인
        current_stage = scenario_manager.get_current_stage(user_id)
        if current_stage == "개요" and not scenario_manager.load_scenario(user_id):
            # 첫 시나리오 생성 시 사용자 선호도 파악
            preference_keywords = ["테마", "배경", "난이도", "스타일", "분위기", "선호"]
            if any(keyword in text for keyword in preference_keywords):
                # 사용자가 선호도를 명시적으로 표현한 경우 이를 기록
                user_preferences = {
                    "user_input": text,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "preferences_detected": True
                }
                # 시나리오 데이터에 사용자 선호도 저장
                scenario_manager.init_scenario_creation(user_id)
                scenario_data = scenario_manager.load_scenario(user_id)
                if scenario_data:
                    scenario_data["user_preferences"] = user_preferences
                    scenario_manager.save_scenario(user_id, scenario_data)
        
        # 빈 필드 보완 요청 확인
        fill_keywords = ["빈 부분", "누락된", "완성해줘", "채워줘", "보완해줘", "전체 빈 부분"]
        if any(keyword in text for keyword in fill_keywords):
            # 빈 필드 보완 처리
            missing_filled = extract_missing_scenario_info(user_id, text, user_conversations[user_id])
            if missing_filled:
                await message.reply_text("✅ **누락된 정보를 성공적으로 보완했습니다!**\n\n'/scenario' 명령어로 업데이트된 시나리오를 확인해보세요.")
                return
            else:
                await message.reply_text("⚠️ 보완할 정보를 찾지 못했거나 이미 모든 정보가 완성되어 있습니다.")
                return
        
        # 시나리오 정보 추출 및 저장
        scenario_updated = extract_and_save_scenario_info(user_id, text, user_conversations[user_id])
        logger.info(f"📋 시나리오 정보 추출 결과: {scenario_updated}")
        
        # 현재 단계 완료 확인 및 다음 단계로 진행
        current_stage = scenario_manager.get_current_stage(user_id)
        logger.info(f"🎯 현재 시나리오 단계: {current_stage}")
        
        # 현재 단계 완료 확인
        stage_complete = scenario_manager.is_stage_complete(user_id, current_stage)
        
        # 단계 완료 전에 빈 필드 확인 및 보완 요청
        if not stage_complete:
            # 빈 필드 확인
            empty_fields = scenario_manager.find_empty_fields(user_id)
            
            # 현재 단계와 관련된 빈 필드가 있는지 확인
            current_stage_fields = {
                "개요": ["overview"],
                "에피소드": ["episodes"], 
                "NPC": ["npcs"],
                "힌트": ["hints"],
                "던전": ["dungeons"]
            }
            
            relevant_empty_fields = {}
            stage_field_types = current_stage_fields.get(current_stage, [])
            for field_type in stage_field_types:
                if field_type in empty_fields:
                    relevant_empty_fields[field_type] = empty_fields[field_type]
            
            if relevant_empty_fields:
                # 자동으로 빈 필드 보완 시도
                logger.info(f"🔧 {current_stage} 단계에서 빈 필드 감지, 자동 보완 시도 중...")
                await message.reply_text(f"⚠️ **{current_stage} 단계에서 일부 정보가 누락되었습니다.**\n\n🤖 자동으로 누락된 정보를 보완하고 있습니다...")
                
                missing_filled = extract_missing_scenario_info(user_id, f"{current_stage} 단계의 누락된 정보를 보완해주세요", user_conversations[user_id])
                if missing_filled:
                    await message.reply_text("✅ **누락된 정보를 자동으로 보완했습니다!**\n\n'/scenario' 명령어로 업데이트된 시나리오를 확인하거나 계속 진행해주세요.")
                    return
                else:
                    await message.reply_text(f"⚠️ **자동 보완에 실패했습니다.**\n\n직접 추가 정보를 제공하거나 '빈 부분 채워줘'라고 말씀해주세요.")
                    return
        
        if stage_complete:
            next_stage = scenario_manager.get_next_stage(current_stage)
            
            if next_stage == ScenarioStage.COMPLETED.value:
                # 전체 시나리오의 빈 필드 최종 확인 및 자동 보완
                final_empty_fields = scenario_manager.find_empty_fields(user_id)
                if final_empty_fields:
                    await message.reply_text(f"✅ {current_stage} 단계가 완료되었습니다!\n\n⚠️ **시나리오에 일부 누락된 정보가 있습니다.**\n\n🤖 자동으로 모든 누락된 정보를 보완하고 있습니다...")
                    
                    missing_filled = extract_missing_scenario_info(user_id, "전체 시나리오의 모든 누락된 정보를 보완해주세요", user_conversations[user_id])
                    if missing_filled:
                        await message.reply_text("✅ **모든 누락된 정보를 자동으로 보완했습니다!**\n\n시나리오 생성이 완료되었습니다.")
                        # 보완 후 다음 세션으로 자동 진행
                        next_session = get_next_session(session_type)
                        session_manager.log_session(user_id, next_session, f"자동 세션 전환: {session_type} 완료 (자동 보완 완료)")
                        
                        session_prompt = get_session_prompt(next_session, user_id)
                        await message.reply_text(f"🎉 자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                        return
                    else:
                        await message.reply_text(f"⚠️ **자동 보완에 실패했습니다.**\n\n'전체 빈 부분 채워줘'라고 말씀해주시거나 '완료'라고 말씀해주시면 다음 세션으로 진행합니다.")
                        return
                else:
                    # 시나리오 생성 완료 - 다음 세션으로 이동
                    next_session = get_next_session(session_type)
                    session_manager.log_session(user_id, next_session, f"자동 세션 전환: {session_type} 완료")
                    
                    session_prompt = get_session_prompt(next_session, user_id)
                    await message.reply_text(f"🎉 시나리오 생성이 완료되었습니다!\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                    return
            else:
                # 다음 단계로 진행
                scenario_manager.set_current_stage(user_id, next_stage)
                stage_prompt = scenario_manager.get_stage_prompt(next_stage)
                
                await message.reply_text(f"✅ {current_stage} 단계가 완료되었습니다!\n\n**다음 단계: {next_stage}**\n\n{stage_prompt}")
                return
    
    # 기타 세션별 처리
    elif session_type in ["모험_생성", "던전_생성", "파티_생성", "파티_결성", "모험_준비"]:
        logger.info(f"🔍 {session_type} 세션 처리 시작 - 사용자 {user_id}")
        
        # 세션 완료 확인 (LLM 기반 판단)
        completion_check = extract_session_completion_info(text, session_type, user_conversations[user_id])
        logger.info(f"🎯 {session_type} 세션 완료 확인 결과: {completion_check}")
        
        if completion_check:
            logger.info(f"✅ {session_type} 세션 완료 감지 - 데이터 저장 시작")
            
            # 현재 세션의 대화 내용을 데이터로 저장
            session_data = {
                "session_type": session_type,
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "conversation": user_conversations[user_id][-10:],  # 최근 10개 대화
                "user_input": text
            }
            
            logger.info(f"💾 {session_type} 세션 데이터 준비 완료: {len(session_data['conversation'])}개 대화 포함")
            
            save_result = save_session_data(user_id, session_type, session_data)
            logger.info(f"📁 save_session_data 호출 결과: {save_result}")
            
            if save_result:
                logger.info(f"✅ {session_type} 데이터 저장 성공 - 세션 요약 업데이트 시작")
                
                # 세션 요약 업데이트
                update_session_summary(user_id, session_type, user_conversations[user_id])
                
                # 다음 세션으로 자동 이동
                next_session = get_next_session(session_type)
                session_manager.log_session(user_id, next_session, f"자동 세션 전환: {session_type} 완료")
                
                # 🆕 모험_진행 세션 시작 시 첫 번째 에피소드 자동 활성화
                if next_session == "모험_진행":
                    scenario_manager.update_episode_progress(user_id, 1, "진행중")
                    logger.info(f"첫 번째 에피소드 활성화: 사용자 {user_id}")
                
                session_prompt = get_session_prompt(next_session, user_id)
                await message.reply_text(f"✅ {session_type} 세션이 완료되었습니다!\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                return
            else:
                logger.error(f"❌ {session_type} 데이터 저장 실패")
        else:
            logger.info(f"🔄 {session_type} 세션 계속 진행 중")
    
    # LLM을 사용하여 캐릭터 정보 추출 (세션 타입이 캐릭터_생성인 경우)
    updated_fields = []
    if session_type == "캐릭터_생성":
        # LLM 기반 캐릭터 정보 추출
        updated_fields = CharacterManager.extract_info_using_llm(text, user_id)
        
        # LLM이 랜덤 캐릭터를 생성했는지 확인
        if "랜덤 캐릭터 생성" in updated_fields:
            # 현재 캐릭터 데이터 로드
            character_data = CharacterManager.load_character(user_id)
            player_count, completed_count = CharacterManager.get_player_count_and_completed(user_id)
            current_index = CharacterManager.get_current_character_index(user_id)
            
            # 캐릭터 정보 표시
            character_sheet = CharacterManager.format_character_sheet(character_data)
            
            # 완료된 캐릭터 수 증가 및 다음 캐릭터 준비
            CharacterManager.increment_completed_character(user_id)
            completed_count += 1
            
            if player_count > completed_count:
                # 아직 생성할 캐릭터가 남아있음
                await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n{current_index + 1}번째 캐릭터 생성이 완료되었습니다!\n이제 {current_index + 2}번째 캐릭터를 생성해 보겠습니다.\n\n캐릭터의 이름, 클래스, 가치관, 능력치 등을 알려주세요.")
                return
            else:
                # 모든 캐릭터 생성 완료 - 자동으로 다음 세션으로 이동
                next_session = get_next_session("캐릭터_생성")
                session_manager.log_session(user_id, next_session, "자동 세션 전환: 캐릭터 생성 완료")
                
                session_prompt = get_session_prompt(next_session, user_id)
                await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n🎉 축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다.\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
                return
        
        # 모든 플레이어의 캐릭터 생성 완료 확인
        if CharacterManager.is_character_creation_complete_for_all(user_id):
            player_count, _ = CharacterManager.get_player_count_and_completed(user_id)
            
            # 자동으로 다음 세션으로 이동
            next_session = get_next_session("캐릭터_생성")
            session_manager.log_session(user_id, next_session, "자동 세션 전환: 캐릭터 생성 완료")
            
            session_prompt = get_session_prompt(next_session, user_id)
            await message.reply_text(f"🎉 축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다.\n\n자동으로 '{next_session}' 세션으로 이동합니다.\n\n{session_prompt}")
            return
            
    # 🚨 컨텍스트 최적화: 각 부분을 개별적으로 수집한 후 최적화
    context_parts = []
    
    # 1. 캐릭터 정보 (가장 중요)
    character_data = user_characters.get(user_id) or CharacterManager.load_character(user_id)
    if character_data:
        character_sheet = CharacterManager.format_character_sheet(character_data)
        context_parts.append(f"플레이어 캐릭터 정보:\n{character_sheet}")
    
    # 2. 시나리오 컨텍스트 (중요) - 🆕 반복 상황 감지 및 처리 추가
    scenario_context = scenario_manager.get_scenario_context_for_mastering(user_id, session_type)
    if scenario_context:
        context_parts.append(scenario_context)
        
        # 🆕 모험 진행 세션에서 반복 상황 감지
        if session_type == "모험_진행":
            repetitive_detected = check_repetitive_situation_in_context(scenario_context, user_conversations[user_id])
            if repetitive_detected:
                logger.warning(f"⚠️ 사용자 {user_id}에서 반복 상황 감지됨, 에피소드 진행 강제 시작")
                forced_progression = force_episode_progression_context(user_id, scenario_context)
                if forced_progression:
                    context_parts.append(forced_progression)
    
    # 3. 세션별 생성 파일들 (보통 중요도)
    session_files_context = load_session_files_context(user_id)
    if session_files_context:
        context_parts.append(session_files_context)
    
    # 4. 세션 진행 상황 요약 (보통 중요도)
    session_summary = load_session_summary(user_id)
    if session_summary:
        # 요약도 너무 길면 자르기
        truncated_summary = truncate_text_safely(session_summary, max_length=1000, preserve_end=True)
        context_parts.append(f"지금까지의 상황 요약:\n{truncated_summary}")
    
    # 5. 현재 세션별 프롬프트 (덜 중요)
    if session_type != "캐릭터_생성" and session_type != "기타":
        session_prompt_context = get_session_prompt(session_type, user_id)
        # 세션 프롬프트는 크기를 많이 줄임
        truncated_prompt = truncate_text_safely(session_prompt_context, max_length=1500, preserve_end=False)
        context_parts.append(f"현재 세션 안내:\n{truncated_prompt}")
    
    # 컨텍스트 최적화 적용
    logger.info(f"🔍 컨텍스트 최적화 전: {len(context_parts)}개 부분")
    optimized_context_parts = optimize_context_parts(context_parts, max_total_length=LLM_SAFE_CONTEXT_LENGTH)
    character_context = "\n\n".join(optimized_context_parts)
    
    # 최종 컨텍스트 크기 로깅
    final_context_size = len(character_context)
    logger.info(f"📊 최종 컨텍스트 크기: {final_context_size}자 ({'✅ 적정' if final_context_size <= LLM_SAFE_CONTEXT_LENGTH else '⚠️ 초과'})")
    
    # rag 질문 응답 시작
    # 시나리오 생성은 창작 과정이므로 RAG 우회 (메모리 절약)
    if session_type == "시나리오_생성":
        # 🚨 CRITICAL FIX: 시나리오 생성 시 RAG 우회하여 메모리 과부하 방지
        logger.info(f"🎭 시나리오 생성 - RAG 우회 모드 (Sentence Transformer 메모리 절약)")
        final_answer = generate_answer_without_rag(text, session_type, character_context)
    else:
        # 1. 유사성 검색 (시나리오 생성 외의 세션만) - 타임아웃 및 오류 처리 강화
        try:
            logger.info(f"🔍 RAG 검색 시작: {text[:50]}...")
            relevant_chunks = find_similar_chunks(text, match_count=3, match_threshold=0.5) # 상위 3개 청크 검색
            
            # 검색 결과가 없거나 빈 경우 RAG 없이 답변 생성
            if not relevant_chunks:
                logger.warning(f"⚠️ RAG 검색 결과 없음 - RAG 없이 답변 생성")
                final_answer = generate_answer_without_rag(text, session_type, character_context)
            else:
                logger.info(f"✅ RAG 검색 완료: {len(relevant_chunks)}개 청크")
                # 2. 답변 생성 (캐릭터 정보 및 세션 컨텍스트 포함)
                final_answer = generate_answer_with_rag(text, relevant_chunks, session_type, character_context)
                
        except Exception as e:
            logger.error(f"❌ RAG 검색 중 오류 발생: {e}")
            logger.info(f"🔄 RAG 없이 답변 생성으로 폴백")
            final_answer = generate_answer_without_rag(text, session_type, character_context)
    
    # 시나리오 생성 세션에서는 LLM 응답에서도 추가로 정보 추출 시도
    if session_type == "시나리오_생성":
        logger.info(f"🎭 LLM 응답에서 시나리오 정보 추가 추출 시도")
        llm_extraction_success = extract_and_save_scenario_info(user_id, final_answer, user_conversations[user_id])
        logger.info(f"📋 LLM 응답 시나리오 정보 추출 결과: {llm_extraction_success}")
        
        if llm_extraction_success:
            # 시나리오 저장 상태 확인
            scenario_data = scenario_manager.load_scenario(user_id)
            if scenario_data:
                current_stage = scenario_manager.get_current_stage(user_id)
                scenario = scenario_data.get("scenario", {})
                overview = scenario.get("overview", {})
                episodes = scenario.get("episodes", [])
                npcs = scenario.get("npcs", [])
                hints = scenario.get("hints", [])
                dungeons = scenario.get("dungeons", [])
                logger.info(f"✅ 시나리오 저장 확인 - 단계: {current_stage}, 개요: {bool(overview.get('theme'))}, 에피소드: {len(episodes)}, NPC: {len(npcs)}, 힌트: {len(hints)}, 던전: {len(dungeons)}")
                
                # 현재 단계 완료 확인
                if scenario_manager.is_stage_complete(user_id, current_stage):
                    next_stage = scenario_manager.get_next_stage(current_stage)
                    if next_stage != ScenarioStage.COMPLETED.value:
                        scenario_manager.set_current_stage(user_id, next_stage)
                        stage_prompt = scenario_manager.get_stage_prompt(next_stage)
                        final_answer += f"\n\n✅ {current_stage} 단계가 완료되었습니다!\n\n**다음 단계: {next_stage}**\n\n{stage_prompt}"
    
    # 캐릭터 정보가 업데이트되었다면 알림 추가
    if updated_fields:
        fields_str = ", ".join(updated_fields)
        info_message = f"📝 캐릭터 시트에 '{fields_str}' 정보가 추가되었습니다.\n\n"
        final_answer = info_message + final_answer
        
        # 현재 캐릭터 완료 확인 및 안내
        character_data = CharacterManager.load_character(user_id)
        if CharacterManager.is_character_creation_complete(character_data):
            player_count, completed_count = CharacterManager.get_player_count_and_completed(user_id)
            current_index = CharacterManager.get_current_character_index(user_id)
            
            if player_count > completed_count:
                final_answer += f"\n\n{current_index + 1}번째 캐릭터의 기본 정보가 모두 입력되었습니다! '/character' 명령어로 확인해보세요."
    
    # 봇의 응답도 세션 로그에 기록 (길이 제한)
    master_response_log = f"마스터 응답: {final_answer[:100]}" + ("..." if len(final_answer) > 100 else "")
    session_manager.log_session(
        user_id, 
        session_type, 
        master_response_log
    )
    
    # 봇의 응답도 대화 기록에 저장
    user_conversations[user_id].append(f"마스터: {final_answer}")
    
    # 세션별 대화가 진행 중일 때마다 요약 업데이트 (캐릭터 생성과 기타 제외)
    if session_type in ["시나리오_생성", "모험_생성", "던전_생성", "파티_생성", "파티_결성", "모험_준비"]:
        # 3번의 대화마다 요약 업데이트 (너무 자주 업데이트하지 않도록)
        conversation_count = len(user_conversations[user_id])
        if conversation_count % 6 == 0:  # 사용자 메시지 + 봇 응답이 한 세트이므로 6번마다 (3세트마다)
            update_session_summary(user_id, session_type, user_conversations[user_id])

    # 메시지에 대한 응답
    await send_long_message(message, final_answer, "[마스터]") 

    # 🧪 디버깅용: NPC 생성 테스트
    if "테스트 NPC 생성" in text or "test npc generation" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 NPC 생성 테스트 요청")
        
        try:
            from npc_manager import NPCManager
            npc_manager = NPCManager()
            
            # 테스트용 시나리오 정보
            test_scenario = {
                "scenario": {
                    "overview": {
                        "theme": "미스터리",
                        "setting": "중세 판타지"
                    }
                }
            }
            
            await message.reply_text("🧪 **NPC 생성 테스트 시작**\n\n테스트 시나리오: 미스터리 / 중세 판타지\n생성할 NPC 수: 2명\n최대 재시도: 2회")
            
            # 1명씩 생성 테스트
            success = npc_manager.create_npcs_for_scenario(user_id, test_scenario, npc_count=2, max_retries=2)
            
            if success:
                # 생성된 NPC 파일 확인
                npc_file = f'sessions/user_{user_id}/npcs.json'
                if os.path.exists(npc_file):
                    with open(npc_file, 'r', encoding='utf-8') as f:
                        npc_data = json.load(f)
                    
                    npc_count = len(npc_data.get('npcs', []))
                    npc_names = [npc.get('name', '이름 없음') for npc in npc_data.get('npcs', [])]
                    
                    result_message = f"""✅ **NPC 생성 테스트 성공!**

📊 **결과:**
• 생성된 NPC 수: {npc_count}명
• NPC 이름: {', '.join(npc_names)}
• 파일 위치: {npc_file}

🔍 **로그를 확인하여 생성 과정의 세부사항을 확인하세요.**"""
                else:
                    result_message = "✅ **NPC 생성 테스트 성공!**\n\n하지만 NPC 파일을 찾을 수 없습니다. 로그를 확인해주세요."
            else:
                result_message = """❌ **NPC 생성 테스트 실패**

🔍 **확인사항:**
• 로그에서 finish_reason: 2 오류 확인
• JSON 파싱 오류 메시지 확인
• 폴백 NPC 사용 여부 확인

💡 **해결방법:**
• LLM 프롬프트가 너무 길 수 있습니다
• 네트워크 연결 상태를 확인하세요
• API 키 설정을 확인하세요"""
            
            await message.reply_text(result_message)
            return
            
        except Exception as e:
            logger.error(f"❌ NPC 생성 테스트 중 오류: {e}")
            error_message = f"""❌ **NPC 생성 테스트 중 오류 발생**

🚨 **오류 내용:**
```
{str(e)}
```

🔍 **확인사항:**
• npc_manager.py 파일 존재 여부
• 필요한 모듈 import 상태
• 파일 권한 설정"""
            
            await message.reply_text(error_message)
            return
    
    # 🧪 디버깅용: RAG 검색 테스트
    if "테스트 RAG 검색" in text or "test rag search" in text.lower():
        logger.info(f"🧪 사용자 {user_id}가 RAG 검색 테스트 요청")
        
        try:
            await message.reply_text("🧪 **RAG 검색 테스트 시작**\\n\\n테스트 쿼리: '캐릭터 생성 방법'\\n타임아웃: 15초")
            
            # 테스트 검색 실행
            test_query = "캐릭터 생성 방법"
            start_time = time.time()
            
            relevant_chunks = find_similar_chunks(test_query, match_count=2, match_threshold=0.6)
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            if relevant_chunks:
                response = f"✅ **RAG 검색 테스트 성공**\\n\\n"
                response += f"• 검색 시간: {elapsed_time:.1f}초\\n"
                response += f"• 검색된 청크 수: {len(relevant_chunks)}개\\n"
                response += f"• 첫 번째 청크 미리보기: {relevant_chunks[0][1][:100]}..."
            else:
                response = f"⚠️ **RAG 검색 결과 없음**\\n\\n"
                response += f"• 검색 시간: {elapsed_time:.1f}초\\n"
                response += f"• 검색된 청크 수: 0개\\n"
                response += f"• 임계값을 낮춰보세요 (현재: 0.3)"
            
            await message.reply_text(response)
            
        except Exception as e:
            await message.reply_text(f"❌ **RAG 검색 테스트 실패**\\n\\n오류: {str(e)}")
        
        return
    
    # 캐릭터 생성 세션 특별 처리