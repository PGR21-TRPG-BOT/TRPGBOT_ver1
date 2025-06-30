# -*- coding: utf-8 -*-
"""
NPC 생성 및 관리 시스템

TRPG 시나리오에서 사용할 NPC들을 LLM을 통해 생성하고 관리하는 모듈입니다.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class NPCManager:
    """NPC 생성 및 관리 클래스"""
    
    def __init__(self):
        """NPCManager 초기화"""
        self.ensure_directories()
        
    def ensure_directories(self, user_id=None):
        """필요한 디렉토리 생성"""
        if user_id:
            # 사용자별 디렉토리 생성
            user_dir = f'sessions/user_{user_id}'
            directories = [user_dir, f'{user_dir}/npcs']
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"📁 디렉토리 생성: {directory}")
        else:
            # 기본 디렉토리 생성 (하위 호환성)
            directories = ['npcs', 'npcs/characters', 'npcs/templates']
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
            
    def get_npc_file_path(self, user_id):
        """사용자별 NPC 파일 경로 반환 (user_{user_id} 폴더 내부)"""
        self.ensure_directories(user_id)
        return f'sessions/user_{user_id}/npcs.json'
        
    def get_character_file_path(self, user_id, npc_id):
        """개별 NPC 캐릭터 파일 경로 반환 (user_{user_id} 폴더 내부)"""
        self.ensure_directories(user_id)
        return f'sessions/user_{user_id}/npc_{npc_id}.json'
    
    def generate_npc_creation_prompt(self, scenario_info: Dict, npc_count: int = 5) -> str:
        """시나리오 정보를 바탕으로 NPC 생성 프롬프트 생성 (최대한 간소화)"""
        
        # 시나리오 정보 추출
        overview = scenario_info.get("scenario", {}).get("overview", {})
        theme = overview.get("theme", "모험")
        setting = overview.get("setting", "판타지")
        
        # 🚨 ULTRA SIMPLIFIED: 토큰 제한 문제 해결을 위한 극도로 간소화된 프롬프트
        prompt = f"""NPC {npc_count}명 생성. 테마: {theme}, 배경: {setting}

JSON 형식으로만 응답:

{{
  "npcs": [
    {{
      "name": "이름",
      "role": "역할",
      "race": "종족", 
      "gender": "성별",
      "age": "나이",
      "appearance": "외모",
      "personality": "성격",
      "background": "배경",
      "motivation": "동기",
      "relationship_to_party": "관계",
      "important_information": "정보",
      "abilities": "능력",
      "dialogue_style": "말투",
      "location": "위치",
      "plot_relevance": "역할"
    }}
  ]
}}

{npc_count}명 생성. JSON만 응답."""
        
        return prompt
    
    def generate_npcs_with_llm(self, scenario_info: Dict, npc_count: int = 5) -> Optional[List[Dict]]:
        """LLM을 사용하여 NPC 생성 (강화된 오류 처리)"""
        from trpgbot_ragmd_sentencetr import generate_answer_without_rag
        
        try:
            # NPC 생성 프롬프트 생성
            prompt = self.generate_npc_creation_prompt(scenario_info, npc_count)
            
            logger.info(f"🎭 LLM을 통한 NPC 생성 시작 ({npc_count}명)")
            logger.info(f"📝 프롬프트 길이: {len(prompt)} 문자")
            
            # LLM으로 NPC 생성 요청
            llm_response = generate_answer_without_rag(prompt, "NPC_생성", "")
            
            logger.info(f"📥 LLM 응답 수신: {len(llm_response)} 문자")
            
            # 응답 유효성 검사
            if self.is_llm_response_valid(llm_response):
                # JSON 파싱 시도
                npc_data = self.parse_npc_response(llm_response)
                
                if npc_data and len(npc_data) > 0:
                    logger.info(f"✅ NPC 생성 성공: {len(npc_data)}명")
                    return npc_data
                else:
                    logger.warning("⚠️ NPC 데이터 파싱 실패 - 폴백 NPC 사용")
                    return self.create_fallback_npc()
            else:
                logger.warning("⚠️ LLM 응답이 유효하지 않음 - 폴백 NPC 사용")
                return self.create_fallback_npc()
                
        except Exception as e:
            logger.error(f"❌ LLM NPC 생성 중 오류: {e}")
            return self.create_fallback_npc()
    
    def is_llm_response_valid(self, llm_response: str) -> bool:
        """LLM 응답의 유효성을 검사"""
        try:
            # 기본 검사
            if not llm_response or len(llm_response.strip()) < 20:
                logger.warning("⚠️ 응답이 너무 짧음")
                return False
            
            # finish_reason 오류 검사
            error_indicators = [
                "finish_reason: 2",
                "finish_reason: 3", 
                "finish_reason: 4",
                "응답이 너무 길어서 중단",
                "안전 정책에 의해 응답이 차단",
                "저작권 문제로 응답이 차단",
                "응답 생성 중 문제가 발생"
            ]
            
            for indicator in error_indicators:
                if indicator in llm_response:
                    logger.warning(f"⚠️ 오류 지시자 감지: {indicator}")
                    return False
            
            # JSON 형식 존재 여부 검사
            if not ("{" in llm_response and "}" in llm_response):
                logger.warning("⚠️ JSON 형식이 없음")
                return False
            
            # 최소 필수 키워드 검사
            required_keywords = ["name", "role"]
            keyword_count = sum(1 for keyword in required_keywords if keyword in llm_response)
            
            if keyword_count < len(required_keywords):
                logger.warning(f"⚠️ 필수 키워드 부족: {keyword_count}/{len(required_keywords)}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 응답 유효성 검사 중 오류: {e}")
            return False
    
    def parse_npc_response(self, llm_response: str) -> Optional[List[Dict]]:
        """LLM 응답에서 NPC 데이터를 파싱 (강화된 오류 처리)"""
        try:
            logger.info(f"📝 LLM 응답 파싱 시작: {len(llm_response)} 문자")
            
            # 응답이 너무 짧거나 비어있는 경우
            if not llm_response or len(llm_response.strip()) < 10:
                logger.error("❌ LLM 응답이 너무 짧거나 비어있음")
                return self.create_fallback_npc()
            
            # finish_reason: 2 (길이 제한) 오류 감지
            if "finish_reason: 2" in llm_response or len(llm_response) < 100:
                logger.warning("⚠️ LLM 응답이 중단되었거나 너무 짧음 - 폴백 NPC 생성")
                return self.create_fallback_npc()
            
            # 다양한 JSON 형식 시도
            json_candidates = []
            
            # 1. ```json 형태 찾기
            if "```json" in llm_response:
                json_start = llm_response.find("```json") + 7
                json_end = llm_response.find("```", json_start)
                if json_end > json_start:
                    json_candidates.append(llm_response[json_start:json_end].strip())
            
            # 2. 단순 { } 형태 찾기 (가장 큰 JSON 블록)
            if "{" in llm_response and "}" in llm_response:
                json_start = llm_response.find("{")
                json_end = llm_response.rfind("}") + 1
                if json_end > json_start:
                    json_candidates.append(llm_response[json_start:json_end].strip())
            
            # 3. 여러 개의 { } 블록 찾기
            import re
            json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', llm_response, re.DOTALL)
            json_candidates.extend(json_blocks)
            
            # 4. "npcs"를 포함한 블록 우선 선택
            priority_candidates = []
            for candidate in json_candidates:
                if "npcs" in candidate or "name" in candidate:
                    priority_candidates.append(candidate)
            
            # 우선순위 후보가 있으면 사용, 없으면 전체 후보 사용
            candidates_to_try = priority_candidates if priority_candidates else json_candidates
            
            if not candidates_to_try:
                logger.error("❌ JSON 형식을 찾을 수 없음 - 폴백 NPC 생성")
                return self.create_fallback_npc()
            
            # 각 후보에 대해 파싱 시도
            for i, json_str in enumerate(candidates_to_try):
                try:
                    logger.info(f"📄 JSON 후보 {i+1} 파싱 시도: {len(json_str)} 문자")
                    
                    # JSON 파싱
                    parsed_data = json.loads(json_str)
                    
                    # NPCs 배열 추출
                    npcs = None
                    if "npcs" in parsed_data:
                        npcs = parsed_data["npcs"]
                    elif isinstance(parsed_data, list):
                        npcs = parsed_data
                    elif isinstance(parsed_data, dict):
                        # 단일 NPC 객체인 경우
                        if "name" in parsed_data:
                            npcs = [parsed_data]
                    
                    if not npcs:
                        logger.warning(f"⚠️ JSON 후보 {i+1}에서 NPCs 배열을 찾을 수 없음")
                        continue
                    
                    # 데이터 유효성 검증
                    validated_npcs = []
                    for j, npc in enumerate(npcs):
                        if self.validate_npc_data(npc, j+1):
                            validated_npcs.append(npc)
                        else:
                            logger.warning(f"⚠️ NPC {j+1} 데이터 유효성 검증 실패")
                    
                    if validated_npcs:
                        logger.info(f"✅ 유효한 NPC 데이터 파싱 성공: {len(validated_npcs)}명")
                        return validated_npcs
                    else:
                        logger.warning(f"⚠️ JSON 후보 {i+1}에서 유효한 NPC를 찾을 수 없음")
                        continue
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ JSON 후보 {i+1} 파싱 실패: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ JSON 후보 {i+1} 처리 중 오류: {e}")
                    continue
            
            # 모든 후보 파싱 실패 시 폴백
            logger.error("❌ 모든 JSON 후보 파싱 실패 - 폴백 NPC 생성")
            logger.error(f"❌ 원본 응답 샘플: {llm_response[:300]}...")
            return self.create_fallback_npc()
            
        except Exception as e:
            logger.error(f"❌ NPC 응답 파싱 중 예상치 못한 오류: {e}")
            return self.create_fallback_npc()
    
    def create_fallback_npc(self) -> List[Dict]:
        """JSON 파싱 실패 시 사용할 기본 NPC 생성 (다양한 유형)"""
        logger.info("🔧 폴백 NPC 생성 중...")
        
        # 다양한 기본 NPC 템플릿
        fallback_npc_templates = [
            {
                "name": "마을 촌장",
                "role": "의뢰인",
                "race": "인간",
                "gender": "남성",
                "age": "중년",
                "appearance": "회색 머리와 친근한 미소를 가진 중년 남성",
                "personality": "친절하고 책임감이 강함",
                "background": "오랫동안 마을을 이끌어온 경험 많은 촌장",
                "motivation": "마을의 평화와 안전을 지키고 싶어함",
                "relationship_to_party": "우호적",
                "important_information": "마을에서 일어나는 이상한 사건들에 대한 정보",
                "abilities": "마을 사람들을 설득하고 조직하는 능력",
                "dialogue_style": "정중하고 진중한 말투",
                "location": "마을 회관",
                "plot_relevance": "모험의 시작점을 제공하는 핵심 인물"
            },
            {
                "name": "여관 주인 마리아",
                "role": "정보제공자",
                "race": "인간",
                "gender": "여성",
                "age": "중년",
                "appearance": "활기찬 눈빛과 따뜻한 미소를 가진 여성",
                "personality": "수다스럽고 친근하며 호기심이 많음",
                "background": "여행자들을 상대로 여관을 운영하며 많은 소식을 들음",
                "motivation": "손님들을 잘 대접하고 흥미로운 이야기를 듣고 싶어함",
                "relationship_to_party": "우호적",
                "important_information": "최근 마을에 온 이상한 방문자들과 소문들",
                "abilities": "뛰어난 기억력과 사교 능력",
                "dialogue_style": "친근하고 수다스러운 말투",
                "location": "황금 말굽 여관",
                "plot_relevance": "중요한 정보와 소문을 제공하는 인물"
            },
            {
                "name": "경비대장 토마스",
                "role": "조력자",
                "race": "인간",
                "gender": "남성",
                "age": "장년",
                "appearance": "상처가 있는 얼굴과 단단한 체격의 베테랑 전사",
                "personality": "진지하고 의무감이 강하며 신중함",
                "background": "오랜 경험을 가진 전직 모험가 출신 경비대장",
                "motivation": "마을과 주민들을 보호하고 질서를 유지하고 싶어함",
                "relationship_to_party": "우호적",
                "important_information": "최근 발생한 사건들과 보안 상황",
                "abilities": "전투 경험과 수사 능력",
                "dialogue_style": "간결하고 직설적인 군인 말투",
                "location": "경비대 본부",
                "plot_relevance": "전투 지원과 공식적인 도움을 제공하는 인물"
            },
            {
                "name": "신비한 상인 엘리아스",
                "role": "중립",
                "race": "엘프",
                "gender": "남성",
                "age": "불명",
                "appearance": "후드를 쓴 채 신비로운 분위기를 풍기는 엘프",
                "personality": "신중하고 신비로우며 거래를 좋아함",
                "background": "각지를 돌아다니며 희귀한 물건을 거래하는 상인",
                "motivation": "이익과 흥미로운 거래를 추구함",
                "relationship_to_party": "중립",
                "important_information": "다른 지역의 소식과 희귀한 물건들",
                "abilities": "마법 물품 감정과 거래 기술",
                "dialogue_style": "신중하고 암시적인 말투",
                "location": "시장 광장",
                "plot_relevance": "유용한 물품과 정보를 제공할 수 있는 인물"
            },
            {
                "name": "수상한 방문자",
                "role": "적대자",
                "race": "인간",
                "gender": "남성",
                "age": "청년",
                "appearance": "검은 옷을 입고 항상 경계하는 듯한 눈빛",
                "personality": "의심스럽고 비밀스러우며 공격적임",
                "background": "정체불명의 목적으로 마을에 나타난 인물",
                "motivation": "숨겨진 목적을 달성하려 함",
                "relationship_to_party": "적대적",
                "important_information": "마을에서 일어나는 사건들과 연관된 비밀",
                "abilities": "은밀한 행동과 전투 기술",
                "dialogue_style": "차갑고 위협적인 말투",
                "location": "마을 외곽",
                "plot_relevance": "주요 갈등의 원인이 되는 인물"
            }
        ]
        
        # 랜덤하게 하나 선택하거나 첫 번째 사용
        import random
        selected_npc = random.choice(fallback_npc_templates)
        selected_npc["id"] = 1  # ID 추가
        
        logger.info(f"✅ 폴백 NPC 생성 완료: {selected_npc['name']} ({selected_npc['role']})")
        return [selected_npc]
    
    def validate_npc_data(self, npc: Dict, npc_number: int) -> bool:
        """NPC 데이터 유효성 검증"""
        required_fields = [
            "name", "role", "race", "gender", "age", "appearance", 
            "personality", "background", "motivation", "relationship_to_party",
            "important_information", "abilities", "dialogue_style", "location"
        ]
        
        for field in required_fields:
            if field not in npc or not npc[field] or str(npc[field]).strip() == "":
                logger.warning(f"⚠️ NPC {npc_number}: '{field}' 필드가 비어있음")
                return False
        
        # 오류 키워드 체크
        error_keywords = [
            "추출할 수 없", "오류 메시지", "시스템 오류", "제공된 대화",
            "해당 없음", "정보를 파악", "죄송합니다", "메시지 감지"
        ]
        
        for field, value in npc.items():
            if isinstance(value, str):
                for keyword in error_keywords:
                    if keyword in value:
                        logger.warning(f"⚠️ NPC {npc_number}: '{field}'에서 오류 키워드 감지: {keyword}")
                        return False
        
        return True
    
    def save_npcs(self, user_id: int, npcs: List[Dict], scenario_info: Dict = None) -> bool:
        """NPC 데이터를 파일로 저장"""
        try:
            # 컬렉션 파일 데이터 구성
            collection_data = {
                "user_id": user_id,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scenario_info": scenario_info,
                "npc_count": len(npcs),
                "npcs": npcs
            }
            
            # 메인 컬렉션 파일 저장
            collection_file = self.get_npc_file_path(user_id)
            with open(collection_file, 'w', encoding='utf-8') as f:
                json.dump(collection_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ NPC 컬렉션 저장 완료: {collection_file}")
            
            # 개별 NPC 파일들 저장
            for i, npc in enumerate(npcs):
                npc_id = npc.get("id", i+1)
                character_file = self.get_character_file_path(user_id, npc_id)
                
                # 개별 NPC 데이터에 메타정보 추가
                character_data = {
                    "user_id": user_id,
                    "npc_id": npc_id,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "character_data": npc
                }
                
                with open(character_file, 'w', encoding='utf-8') as f:
                    json.dump(character_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"✅ 개별 NPC 저장 완료: {npc.get('name', f'NPC{npc_id}')} -> {character_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ NPC 데이터 저장 오류: {e}")
            return False
    
    def load_npcs(self, user_id: int) -> Optional[List[Dict]]:
        """저장된 NPC 데이터 로드"""
        collection_file = self.get_npc_file_path(user_id)
        
        if not os.path.exists(collection_file):
            logger.info(f"ℹ️ NPC 파일이 존재하지 않음: {collection_file}")
            return None
        
        try:
            with open(collection_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            npcs = data.get("npcs", [])
            logger.info(f"✅ NPC 데이터 로드 성공: {len(npcs)}명")
            return npcs
            
        except Exception as e:
            logger.error(f"❌ NPC 데이터 로드 오류: {e}")
            return None
    
    def get_npc_summary(self, user_id: int) -> str:
        """NPC 요약 정보 반환"""
        npcs = self.load_npcs(user_id)
        
        if not npcs:
            return "생성된 NPC가 없습니다."
        
        summary_parts = [f"📊 **생성된 NPC 목록 ({len(npcs)}명)**\n"]
        
        for i, npc in enumerate(npcs, 1):
            name = npc.get("name", f"NPC {i}")
            role = npc.get("role", "역할 미정")
            race = npc.get("race", "종족 미정")
            relationship = npc.get("relationship_to_party", "관계 미정")
            
            summary_parts.append(f"{i}. **{name}** ({race})")
            summary_parts.append(f"   └ 역할: {role}")
            summary_parts.append(f"   └ 관계: {relationship}")
        
        return "\n".join(summary_parts)
    
    def create_npcs_for_scenario(self, user_id: int, scenario_info: Dict, npc_count: int = 5, max_retries: int = 3) -> bool:
        """시나리오에 맞는 NPC를 한 명씩 생성 및 저장 (append 방식) - 강화된 오류 처리"""
        logger.info(f"🎭 시나리오 기반 NPC 생성 시작(1명씩): 사용자 {user_id}")
        success_count = 0
        
        for idx in range(npc_count):
            npc_created = False
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 NPC {idx+1}/{npc_count} 생성 시도 {attempt + 1}/{max_retries}")
                    
                    # 한 명만 생성하도록 프롬프트 (더 간단하게)
                    prompt = self.generate_npc_creation_prompt(scenario_info, npc_count=1)
                    logger.info(f"📝 프롬프트 길이: {len(prompt)} 문자")
                    
                    # LLM 호출
                    from trpgbot_ragmd_sentencetr import generate_answer_without_rag
                    logger.info(f"🤖 LLM 호출 시작 (NPC {idx+1}, 시도 {attempt + 1})")
                    
                    llm_response = generate_answer_without_rag(prompt, "NPC_생성", "")
                    
                    logger.info(f"📥 LLM 응답 수신: {len(llm_response)} 문자")
                    
                    # finish_reason 체크
                    if "finish_reason: 2" in str(llm_response):
                        logger.warning(f"⚠️ LLM 응답 중단 감지 (finish_reason: 2) - NPC {idx+1}, 시도 {attempt + 1}")
                        if attempt < max_retries - 1:
                            logger.info(f"🔄 재시도 예정 (NPC {idx+1}, 시도 {attempt + 2})")
                            import time
                            time.sleep(3)  # 더 긴 대기 시간
                            continue
                        else:
                            logger.warning(f"⚠️ 최대 재시도 도달 - 폴백 NPC 사용 (NPC {idx+1})")
                            # 폴백 NPC 직접 생성
                            fallback_npc = self.create_fallback_npc()[0]
                            fallback_npc["name"] = f"기본 NPC {idx+1}"
                            fallback_npc["id"] = idx + 1
                            
                            if self.save_npc_append(user_id, fallback_npc, scenario_info):
                                logger.info(f"✅ 폴백 NPC {idx+1} 저장 완료")
                                success_count += 1
                                npc_created = True
                                break
                            else:
                                logger.error(f"❌ 폴백 NPC {idx+1} 저장 실패")
                                break
                    
                    # 응답 파싱 시도
                    npc_list = self.parse_npc_response(llm_response)
                    
                    if npc_list and len(npc_list) > 0:
                        npc = npc_list[0]
                        
                        # ID 설정 (없으면 자동 부여)
                        if "id" not in npc:
                            npc["id"] = idx + 1
                        
                        logger.info(f"📋 NPC {idx+1} 파싱 성공: {npc.get('name', '이름 없음')}")
                        
                        # 저장 시도
                        if self.save_npc_append(user_id, npc, scenario_info):
                            logger.info(f"✅ NPC {idx+1} 생성 및 저장 완료: {npc.get('name', '이름 없음')}")
                            success_count += 1
                            npc_created = True
                            break
                        else:
                            logger.error(f"❌ NPC {idx+1} 저장 실패 (시도 {attempt + 1})")
                    else:
                        logger.error(f"❌ NPC {idx+1} 파싱 실패 (시도 {attempt + 1})")
                        logger.error(f"❌ 응답 샘플: {llm_response[:200]}...")
                    
                    # 재시도 전 대기
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ {2 * (attempt + 1)}초 대기 후 재시도...")
                        import time
                        time.sleep(2 * (attempt + 1))  # 점진적으로 대기 시간 증가
                        
                except Exception as e:
                    logger.error(f"❌ NPC {idx+1} 생성 시도 {attempt + 1} 중 예상치 못한 오류: {e}")
                    logger.error(f"❌ 오류 상세: {str(e)}")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ 오류 후 {3 * (attempt + 1)}초 대기 후 재시도...")
                        import time
                        time.sleep(3 * (attempt + 1))
                    else:
                        logger.error(f"❌ NPC {idx+1} 모든 시도 실패 - 폴백 NPC 사용")
                        # 최종 폴백
                        try:
                            fallback_npc = self.create_fallback_npc()[0]
                            fallback_npc["name"] = f"기본 NPC {idx+1}"
                            fallback_npc["id"] = idx + 1
                            
                            if self.save_npc_append(user_id, fallback_npc, scenario_info):
                                logger.info(f"✅ 최종 폴백 NPC {idx+1} 저장 완료")
                                success_count += 1
                                npc_created = True
                            else:
                                logger.error(f"❌ 최종 폴백 NPC {idx+1} 저장도 실패")
                        except Exception as fallback_error:
                            logger.error(f"❌ 폴백 NPC 생성 중 오류: {fallback_error}")
            
            if not npc_created:
                logger.error(f"❌ NPC {idx+1} 생성 완전 실패")
        
        # 결과 요약
        logger.info(f"📊 NPC 생성 결과: {success_count}/{npc_count}명 성공")
        
        if success_count == npc_count:
            logger.info(f"🎉 모든 NPC 생성 성공!")
            return True
        elif success_count > 0:
            logger.warning(f"⚠️ 부분 성공: {npc_count}명 중 {success_count}명 생성됨")
            return True  # 부분 성공도 성공으로 간주
        else:
            logger.error(f"❌ 모든 NPC 생성 실패")
            return False
    
    def ensure_npcs_exist(self, user_id: int, scenario_info: Dict) -> bool:
        """NPC가 존재하는지 확인하고 없으면 생성"""
        existing_npcs = self.load_npcs(user_id)
        
        if existing_npcs and len(existing_npcs) >= 3:
            logger.info(f"✅ 기존 NPC 발견: {len(existing_npcs)}명")
            return True
        
        logger.info("🎭 기존 NPC가 부족합니다. 새로 생성합니다...")
        return self.create_npcs_for_scenario(user_id, scenario_info)

    def save_npc_append(self, user_id: int, npc: Dict, scenario_info: Dict = None) -> bool:
        """NPC 한 명을 파일에 append 저장"""
        try:
            collection_file = self.get_npc_file_path(user_id)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 기존 파일이 있으면 불러오기
            if os.path.exists(collection_file):
                with open(collection_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                npcs = data.get("npcs", [])
                scenario_info = data.get("scenario_info", scenario_info)
                created_at = data.get("created_at", now)
            else:
                npcs = []
                created_at = now
            # id 자동 부여
            npc["id"] = len(npcs) + 1
            npcs.append(npc)
            # 파일 저장
            collection_data = {
                "user_id": user_id,
                "created_at": created_at,
                "updated_at": now,
                "scenario_info": scenario_info,
                "npc_count": len(npcs),
                "npcs": npcs
            }
            with open(collection_file, 'w', encoding='utf-8') as f:
                json.dump(collection_data, f, ensure_ascii=False, indent=2)
            # 개별 NPC 파일도 저장
            character_file = self.get_character_file_path(user_id, npc["id"])
            character_data = {
                "user_id": user_id,
                "npc_id": npc["id"],
                "created_at": now,
                "character_data": npc
            }
            with open(character_file, 'w', encoding='utf-8') as f:
                json.dump(character_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ NPC append 저장 완료: {npc.get('name', f'NPC{npc['id']}')} -> {collection_file}")
            return True
        except Exception as e:
            logger.error(f"❌ NPC append 저장 오류: {e}")
            return False

# 전역 인스턴스
npc_manager = NPCManager() 