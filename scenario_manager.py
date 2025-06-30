# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime
from enum import Enum

# NPC 매니저 임포트 추가
try:
    from npc_manager import npc_manager
except ImportError:
    logger.warning("⚠️ NPC 매니저를 임포트할 수 없습니다. NPC 기능이 제한됩니다.")
    npc_manager = None

logger = logging.getLogger(__name__)

class ScenarioStage(Enum):
    """시나리오 생성 단계"""
    OVERVIEW = "개요"
    EPISODES = "에피소드"
    NPCS = "NPC"
    HINTS = "힌트"
    DUNGEONS = "던전"
    COMPLETED = "완료"

class ScenarioProgress(Enum):
    """시나리오 진행 상태"""
    NOT_STARTED = "시작_전"
    IN_PROGRESS = "진행_중"
    COMPLETED = "완료"
    PAUSED = "일시정지"

class ScenarioManager:
    """
    TRPG 시나리오 생성 및 진척도 관리 클래스
    """
    
    def __init__(self):
        """ScenarioManager 초기화"""
        self.ensure_directories()
        
    def ensure_directories(self):
        """필요한 디렉토리 생성"""
        os.makedirs('scenarios', exist_ok=True)
        
    def get_scenario_file_path(self, user_id):
        """시나리오 파일 경로 반환"""
        return f'scenarios/scenario_{user_id}.json'
        
    def init_scenario_creation(self, user_id):
        """시나리오 생성 초기화"""
        scenario_data = {
            "user_id": user_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_stage": ScenarioStage.OVERVIEW.value,
            "progress": ScenarioProgress.NOT_STARTED.value,
            "scenario": {
                "title": "",
                "overview": {
                    "theme": "",
                    "setting": "",
                    "main_conflict": "",
                    "objective": "",
                    "rewards": ""
                },
                "episodes": [],
                "npcs": [],
                "hints": [],
                "dungeons": [],
                "sessions": []
            }
        }
        
        self.save_scenario(user_id, scenario_data)
        logger.info(f"사용자 {user_id}의 시나리오 생성 초기화")
        return scenario_data
        
    def load_scenario(self, user_id):
        """시나리오 데이터 로드"""
        file_path = self.get_scenario_file_path(user_id)
        
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"시나리오 파일 로드 오류: {e}")
            return None
            
    def save_scenario(self, user_id, scenario_data):
        """시나리오 데이터 저장"""
        file_path = self.get_scenario_file_path(user_id)
        
        try:
            scenario_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(scenario_data, f, ensure_ascii=False, indent=2)
            logger.info(f"시나리오 데이터 저장 완료: {file_path}")
            return True
        except Exception as e:
            logger.error(f"시나리오 데이터 저장 오류: {e}")
            return False
            
    def get_current_stage(self, user_id):
        """현재 시나리오 생성 단계 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return ScenarioStage.OVERVIEW.value
        return scenario_data.get("current_stage", ScenarioStage.OVERVIEW.value)
        
    def set_current_stage(self, user_id, stage):
        """현재 시나리오 생성 단계 설정"""
        scenario_data = self.load_scenario(user_id)
        if scenario_data:
            scenario_data["current_stage"] = stage
            self.save_scenario(user_id, scenario_data)
            
    def get_next_stage(self, current_stage):
        """다음 시나리오 생성 단계 반환"""
        stage_flow = {
            ScenarioStage.OVERVIEW.value: ScenarioStage.EPISODES.value,
            ScenarioStage.EPISODES.value: ScenarioStage.NPCS.value,
            ScenarioStage.NPCS.value: ScenarioStage.HINTS.value,
            ScenarioStage.HINTS.value: ScenarioStage.DUNGEONS.value,
            ScenarioStage.DUNGEONS.value: ScenarioStage.COMPLETED.value
        }
        return stage_flow.get(current_stage, ScenarioStage.COMPLETED.value)
        
    def is_stage_complete(self, user_id, stage):
        """특정 단계가 완료되었는지 확인"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return False
            
        scenario = scenario_data.get("scenario", {})
        
        if stage == ScenarioStage.OVERVIEW.value:
            overview = scenario.get("overview", {})
            return all([
                overview.get("theme"),
                overview.get("setting"),
                overview.get("main_conflict"),
                overview.get("objective")
            ])
        elif stage == ScenarioStage.EPISODES.value:
            return len(scenario.get("episodes", [])) >= 3
        elif stage == ScenarioStage.NPCS.value:
            if npc_manager:
                return self.is_npc_stage_complete(user_id)
            else:
                return len(scenario.get("npcs", [])) >= 3
        elif stage == ScenarioStage.HINTS.value:
            return len(scenario.get("hints", [])) >= 3
        elif stage == ScenarioStage.DUNGEONS.value:
            return len(scenario.get("dungeons", [])) >= 1
            
        return False
        
    def update_scenario_overview(self, user_id, overview_data):
        """시나리오 개요 업데이트"""
        scenario_data = self.load_scenario(user_id) or self.init_scenario_creation(user_id)
        scenario_data["scenario"]["overview"].update(overview_data)
        scenario_data["progress"] = ScenarioProgress.IN_PROGRESS.value
        self.save_scenario(user_id, scenario_data)
        
    def add_episode(self, user_id, episode_data):
        """에피소드 추가"""
        scenario_data = self.load_scenario(user_id)
        if scenario_data:
            episode_data["id"] = len(scenario_data["scenario"]["episodes"]) + 1
            scenario_data["scenario"]["episodes"].append(episode_data)
            self.save_scenario(user_id, scenario_data)
            
    def add_npc(self, user_id, npc_data):
        """NPC 추가"""
        scenario_data = self.load_scenario(user_id)
        if scenario_data:
            npc_data["id"] = len(scenario_data["scenario"]["npcs"]) + 1
            scenario_data["scenario"]["npcs"].append(npc_data)
            self.save_scenario(user_id, scenario_data)
            
    def add_hint(self, user_id, hint_data):
        """힌트 추가"""
        scenario_data = self.load_scenario(user_id)
        if scenario_data:
            hint_data["id"] = len(scenario_data["scenario"]["hints"]) + 1
            scenario_data["scenario"]["hints"].append(hint_data)
            self.save_scenario(user_id, scenario_data)
            
    def add_dungeon(self, user_id, dungeon_data):
        """던전 추가"""
        scenario_data = self.load_scenario(user_id)
        if scenario_data:
            dungeon_data["id"] = len(scenario_data["scenario"]["dungeons"]) + 1
            scenario_data["scenario"]["dungeons"].append(dungeon_data)
            self.save_scenario(user_id, scenario_data)
            
    def get_stage_prompt(self, stage):
        """단계별 프롬프트 반환"""
        prompts = {
            ScenarioStage.OVERVIEW.value: """
🎭 **시나리오 개요 생성 단계**

다음 요소들을 포함한 시나리오 개요를 만들어보겠습니다:

1. **테마**: 어떤 종류의 모험인가요? (미스터리, 탐험, 구출, 조사 등)
2. **배경**: 언제, 어디서 일어나는 이야기인가요?
3. **주요 갈등**: 해결해야 할 핵심 문제는 무엇인가요?
4. **목표**: 플레이어들이 달성해야 할 것은 무엇인가요?
5. **보상**: 성공 시 얻을 수 있는 것은 무엇인가요?

원하시는 시나리오의 테마나 아이디어를 알려주세요!
""",
            ScenarioStage.EPISODES.value: """
📖 **에피소드 구성 단계**

시나리오를 3-5개의 주요 에피소드로 나누어 구성하겠습니다:

각 에피소드마다 다음을 포함합니다:
- 에피소드 제목과 목표
- 주요 사건들
- 플레이어 행동 옵션
- 성공/실패 결과

어떤 흐름으로 이야기를 전개하고 싶으신가요?
""",
            ScenarioStage.NPCS.value: """
👥 **NPC 설정 단계**

시나리오에 등장할 주요 NPC들을 만들어보겠습니다:

각 NPC마다 다음을 설정합니다:
- 이름과 외모
- 성격과 동기
- 플레이어와의 관계 (적, 동료, 중립)
- 가진 정보나 능력
- 대화 스타일

어떤 NPC들이 필요할까요?
""",
            ScenarioStage.HINTS.value: """
🔍 **힌트 시스템 설정**

플레이어들이 발견할 수 있는 단서와 힌트들을 설정하겠습니다:

각 힌트마다 다음을 포함합니다:
- 힌트 내용
- 발견 방법 (조사, 대화, 관찰 등)
- 연결되는 정보
- 난이도

어떤 종류의 힌트들이 필요할까요?
""",
            ScenarioStage.DUNGEONS.value: """
🏰 **던전/탐험지 설정**

플레이어들이 탐험할 장소들을 설계하겠습니다:

각 장소마다 다음을 포함합니다:
- 장소 설명과 분위기
- 주요 방/구역들
- 함정이나 퍼즐
- 몬스터나 수호자
- 숨겨진 보물이나 정보

어떤 장소를 탐험하게 하고 싶으신가요?
"""
        }
        return prompts.get(stage, "알 수 없는 단계입니다.")
        
    def get_scenario_context_for_mastering(self, user_id, current_session_type):
        """마스터링용 시나리오 컨텍스트 생성"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return ""
            
        # 현재 세션에 맞는 진척도 업데이트
        self.update_session_progress(user_id, current_session_type)
        
        scenario = scenario_data.get("scenario", {})
        context_parts = []
        
        # 사용자 선호도 정보 (시나리오 생성에 활용)
        user_preferences = scenario_data.get("user_preferences")
        if user_preferences and user_preferences.get("preferences_detected"):
            context_parts.append(f"""
🎯 **사용자 선호도**
사용자 요청: "{user_preferences.get('user_input', '')}"
이 요청을 바탕으로 시나리오 생성 및 마스터링을 진행해주세요.
""")
        
        # 시나리오 개요
        overview = scenario.get("overview", {})
        if overview.get("theme"):
            context_parts.append(f"""
🎭 **현재 진행중인 시나리오**
- 제목: {overview.get('title', '제목 미정')}
- 테마: {overview.get('theme', '')}
- 배경: {overview.get('setting', '')}
- 주요 갈등: {overview.get('main_conflict', '')}
- 목표: {overview.get('objective', '')}
""")
        
        # 에피소드 정보
        episodes = scenario.get("episodes", [])
        if episodes:
            context_parts.append("📖 **에피소드 구성**")
            for i, episode in enumerate(episodes, 1):
                status = self.get_episode_status(user_id, episode.get("id"))
                context_parts.append(f"{i}. {episode.get('title', f'에피소드 {i}')} [{status}]")
        
        # NPC 정보
        npcs = scenario.get("npcs", [])
        if npcs:
            context_parts.append("\n👥 **주요 NPC들**")
            for npc in npcs:
                relationship = npc.get('relationship', npc.get('role', '역할미정'))
                context_parts.append(f"- {npc.get('name', '이름없음')}: {relationship}")
                if npc.get('personality'):
                    context_parts.append(f"  └ 성격: {npc.get('personality')}")
                if npc.get('information'):
                    context_parts.append(f"  └ 정보: {npc.get('information')}")
        
        # 현재 세션 관련 힌트
        hints = scenario.get("hints", [])
        relevant_hints = [h for h in hints if current_session_type in h.get("relevant_sessions", [])]
        if relevant_hints:
            context_parts.append(f"\n🔍 **{current_session_type} 관련 힌트들**")
            for hint in relevant_hints:
                context_parts.append(f"- {hint.get('content', '')}")
                if hint.get('discovery_method'):
                    context_parts.append(f"  └ 발견방법: {hint.get('discovery_method')}")
        
        # 던전 정보 (해당 세션에서 필요한 경우)
        dungeons = scenario.get("dungeons", [])
        if dungeons and current_session_type in ["던전_탐험", "모험_진행"]:
            context_parts.append("\n🏰 **탐험 가능한 장소들**")
            for dungeon in dungeons:
                context_parts.append(f"- {dungeon.get('name', '이름없음')}: {dungeon.get('type', '유형미정')}")
                if dungeon.get('description'):
                    context_parts.append(f"  └ {dungeon.get('description')}")
        
        return "\n".join(context_parts)
        
    def update_session_progress(self, user_id, session_type):
        """세션 진행도 업데이트"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return
            
        sessions = scenario_data["scenario"].get("sessions", [])
        session_found = False
        
        for session in sessions:
            if session.get("type") == session_type:
                session["last_played"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                session["play_count"] = session.get("play_count", 0) + 1
                session_found = True
                break
                
        if not session_found:
            sessions.append({
                "type": session_type,
                "first_played": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_played": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "play_count": 1,
                "status": "진행중"
            })
            
        self.save_scenario(user_id, scenario_data)
        
    def get_episode_status(self, user_id, episode_id):
        """에피소드 진행 상태 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return "미시작"
            
        # 에피소드별 진행 상태 추적
        episode_progress = scenario_data.get("episode_progress", {})
        episode_key = f"episode_{episode_id}"
        
        if episode_key in episode_progress:
            return episode_progress[episode_key].get("status", "미시작")
        
        # 세션 기록을 바탕으로 진행도 판단
        sessions = scenario_data["scenario"].get("sessions", [])
        if not sessions:
            return "미시작"
            
        # 간단한 진행도 판단 로직 (실제로는 더 복잡할 수 있음)
        adventure_sessions = [s for s in sessions if s.get("type") in ["모험_진행", "던전_탐험"]]
        if adventure_sessions:
            return "진행중"
        else:
            return "준비중"
    
    def update_episode_progress(self, user_id, episode_id, status, location=None):
        """에피소드 진행 상태 업데이트"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return False
            
        if "episode_progress" not in scenario_data:
            scenario_data["episode_progress"] = {}
        
        episode_key = f"episode_{episode_id}"
        scenario_data["episode_progress"][episode_key] = {
            "status": status,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "location": location
        }
        
        self.save_scenario(user_id, scenario_data)
        logger.info(f"에피소드 {episode_id} 진행 상태 업데이트: {status}")
        return True
    
    def get_current_episode(self, user_id):
        """현재 진행중인 에피소드 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return None
            
        episodes = scenario_data.get("scenario", {}).get("episodes", [])
        if not episodes:
            return None
        
        episode_progress = scenario_data.get("episode_progress", {})
        
        # 진행중인 에피소드 찾기
        for i, episode in enumerate(episodes):
            episode_key = f"episode_{i+1}"
            status = episode_progress.get(episode_key, {}).get("status", "미시작")
            
            if status == "진행중":
                return {"index": i, "episode": episode, "id": i+1}
        
        # 진행중인 에피소드가 없으면 첫 번째 미시작 에피소드 반환
        for i, episode in enumerate(episodes):
            episode_key = f"episode_{i+1}"
            status = episode_progress.get(episode_key, {}).get("status", "미시작")
            
            if status == "미시작":
                return {"index": i, "episode": episode, "id": i+1}
        
        # 모든 에피소드가 완료되었으면 마지막 에피소드 반환
        return {"index": len(episodes)-1, "episode": episodes[-1], "id": len(episodes)}
    
    def advance_to_next_episode(self, user_id):
        """다음 에피소드로 진행"""
        current_episode = self.get_current_episode(user_id)
        if not current_episode:
            return False
            
        # 현재 에피소드를 완료로 표시
        self.update_episode_progress(user_id, current_episode["id"], "완료")
        
        # 다음 에피소드를 진행중으로 표시
        next_episode_id = current_episode["id"] + 1
        scenario_data = self.load_scenario(user_id)
        episodes = scenario_data.get("scenario", {}).get("episodes", [])
        
        if next_episode_id <= len(episodes):
            self.update_episode_progress(user_id, next_episode_id, "진행중")
            logger.info(f"에피소드 {next_episode_id}로 진행")
            return True
        else:
            logger.info("모든 에피소드가 완료되었습니다")
            return False
    
    def find_empty_fields(self, user_id):
        """시나리오에서 빈 필드들을 찾아서 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return {}
            
        scenario = scenario_data.get("scenario", {})
        empty_fields = {}
        
        # 개요 빈 필드 검사
        overview = scenario.get("overview", {})
        empty_overview = {}
        for field in ["title", "theme", "setting", "main_conflict", "objective", "rewards"]:
            if not overview.get(field) or overview.get(field).strip() == "":
                empty_overview[field] = field
        if empty_overview:
            empty_fields["overview"] = empty_overview
        
        # 에피소드 빈 필드 검사
        episodes = scenario.get("episodes", [])
        incomplete_episodes = []
        for i, episode in enumerate(episodes):
            empty_episode = {}
            for field in ["title", "objective", "events", "player_options", "success_result", "failure_result"]:
                if not episode.get(field) or (isinstance(episode.get(field), list) and len(episode.get(field)) == 0):
                    empty_episode[field] = field
            if empty_episode:
                incomplete_episodes.append({"index": i, "empty_fields": empty_episode})
        if incomplete_episodes:
            empty_fields["episodes"] = incomplete_episodes
        
        # NPC 빈 필드 검사
        npcs = scenario.get("npcs", [])
        incomplete_npcs = []
        for i, npc in enumerate(npcs):
            empty_npc = {}
            for field in ["name", "appearance", "personality", "motivation", "relationship", "information", "abilities"]:
                if not npc.get(field) or npc.get(field).strip() == "":
                    empty_npc[field] = field
            if empty_npc:
                incomplete_npcs.append({"index": i, "name": npc.get("name", f"NPC {i+1}"), "empty_fields": empty_npc})
        if incomplete_npcs:
            empty_fields["npcs"] = incomplete_npcs
        
        # 힌트 빈 필드 검사
        hints = scenario.get("hints", [])
        incomplete_hints = []
        for i, hint in enumerate(hints):
            empty_hint = {}
            for field in ["content", "discovery_method", "connected_info", "difficulty", "relevant_sessions"]:
                if not hint.get(field) or (isinstance(hint.get(field), list) and len(hint.get(field)) == 0):
                    empty_hint[field] = field
            if empty_hint:
                incomplete_hints.append({"index": i, "empty_fields": empty_hint})
        if incomplete_hints:
            empty_fields["hints"] = incomplete_hints
        
        # 던전 빈 필드 검사
        dungeons = scenario.get("dungeons", [])
        incomplete_dungeons = []
        for i, dungeon in enumerate(dungeons):
            empty_dungeon = {}
            for field in ["name", "type", "description", "atmosphere", "rooms", "traps", "puzzles", "monsters", "treasures"]:
                if not dungeon.get(field) or (isinstance(dungeon.get(field), list) and len(dungeon.get(field)) == 0):
                    empty_dungeon[field] = field
            if empty_dungeon:
                incomplete_dungeons.append({"index": i, "name": dungeon.get("name", f"던전 {i+1}"), "empty_fields": empty_dungeon})
        if incomplete_dungeons:
            empty_fields["dungeons"] = incomplete_dungeons
        
        return empty_fields
    
    def generate_fill_missing_prompt(self, user_id, empty_fields):
        """빈 필드를 채우기 위한 프롬프트 생성"""
        if not empty_fields:
            return None
            
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return None
            
        scenario = scenario_data.get("scenario", {})
        prompt_parts = []
        
        prompt_parts.append("현재 시나리오에서 일부 정보가 누락되어 있습니다. 누락된 부분만 채워주세요.")
        
        # 기존 시나리오 정보 제공
        overview = scenario.get("overview", {})
        if overview.get("title"):
            prompt_parts.append(f"\n**현재 시나리오**: {overview.get('title')}")
            prompt_parts.append(f"테마: {overview.get('theme', '')}, 배경: {overview.get('setting', '')}")
        
        # 빈 필드별 요청 생성
        if "overview" in empty_fields:
            prompt_parts.append(f"\n**누락된 시나리오 개요 정보:**")
            for field in empty_fields["overview"]:
                field_names = {
                    "title": "제목", "theme": "테마", "setting": "배경", 
                    "main_conflict": "주요 갈등", "objective": "목표", "rewards": "보상"
                }
                prompt_parts.append(f"- {field_names.get(field, field)}")
        
        if "episodes" in empty_fields:
            prompt_parts.append(f"\n**불완전한 에피소드들:**")
            for episode_info in empty_fields["episodes"]:
                episode_index = episode_info["index"]
                episode = scenario.get("episodes", [])[episode_index]
                prompt_parts.append(f"에피소드 {episode_index + 1}: {episode.get('title', '제목없음')}")
                field_names = {
                    "title": "제목", "objective": "목표", "events": "주요 사건들",
                    "player_options": "플레이어 선택지", "success_result": "성공 결과", "failure_result": "실패 결과"
                }
                for field in episode_info["empty_fields"]:
                    prompt_parts.append(f"  - 누락: {field_names.get(field, field)}")
        
        if "npcs" in empty_fields:
            prompt_parts.append(f"\n**불완전한 NPC들:**")
            for npc_info in empty_fields["npcs"]:
                prompt_parts.append(f"NPC: {npc_info['name']}")
                field_names = {
                    "name": "이름", "appearance": "외모", "personality": "성격",
                    "motivation": "동기", "relationship": "관계", "information": "정보", "abilities": "능력"
                }
                for field in npc_info["empty_fields"]:
                    prompt_parts.append(f"  - 누락: {field_names.get(field, field)}")
        
        if "hints" in empty_fields:
            prompt_parts.append(f"\n**불완전한 힌트들:**")
            for hint_info in empty_fields["hints"]:
                hint_index = hint_info["index"]
                hint = scenario.get("hints", [])[hint_index]
                prompt_parts.append(f"힌트 {hint_index + 1}: {hint.get('content', '내용없음')[:30]}...")
                field_names = {
                    "content": "내용", "discovery_method": "발견 방법", "connected_info": "연결 정보",
                    "difficulty": "난이도", "relevant_sessions": "관련 세션"
                }
                for field in hint_info["empty_fields"]:
                    prompt_parts.append(f"  - 누락: {field_names.get(field, field)}")
        
        if "dungeons" in empty_fields:
            prompt_parts.append(f"\n**불완전한 던전들:**")
            for dungeon_info in empty_fields["dungeons"]:
                prompt_parts.append(f"던전: {dungeon_info['name']}")
                field_names = {
                    "name": "이름", "type": "유형", "description": "설명", "atmosphere": "분위기",
                    "rooms": "방/구역", "traps": "함정", "puzzles": "퍼즐", "monsters": "몬스터", "treasures": "보물"
                }
                for field in dungeon_info["empty_fields"]:
                    prompt_parts.append(f"  - 누락: {field_names.get(field, field)}")
        
        prompt_parts.append(f"\n**요청사항:** 위에서 누락된 정보들만 적절하게 채워서 JSON 형식으로 제공해주세요. 기존 정보는 그대로 유지하고 빈 부분만 추가해주세요.")
        
        return "\n".join(prompt_parts)
    
    def update_missing_fields(self, user_id, extracted_data, empty_fields):
        """누락된 필드만 업데이트"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return False
            
        scenario = scenario_data.get("scenario", {})
        updated = False
        
        # 개요 업데이트
        if "overview" in empty_fields and "overview" in extracted_data:
            overview = scenario.get("overview", {})
            new_overview = extracted_data["overview"]
            for field in empty_fields["overview"]:
                if field in new_overview and new_overview[field]:
                    overview[field] = new_overview[field]
                    updated = True
        
        # 에피소드 업데이트
        if "episodes" in empty_fields and "episodes" in extracted_data:
            episodes = scenario.get("episodes", [])
            for episode_info in empty_fields["episodes"]:
                episode_index = episode_info["index"]
                if episode_index < len(episodes) and episode_index < len(extracted_data["episodes"]):
                    episode = episodes[episode_index]
                    new_episode = extracted_data["episodes"][episode_index]
                    for field in episode_info["empty_fields"]:
                        if field in new_episode and new_episode[field]:
                            episode[field] = new_episode[field]
                            updated = True
        
        # NPC 업데이트
        if "npcs" in empty_fields and "npcs" in extracted_data:
            npcs = scenario.get("npcs", [])
            for npc_info in empty_fields["npcs"]:
                npc_index = npc_info["index"]
                if npc_index < len(npcs) and npc_index < len(extracted_data["npcs"]):
                    npc = npcs[npc_index]
                    new_npc = extracted_data["npcs"][npc_index]
                    for field in npc_info["empty_fields"]:
                        if field in new_npc and new_npc[field]:
                            npc[field] = new_npc[field]
                            updated = True
        
        # 힌트 업데이트
        if "hints" in empty_fields and "hints" in extracted_data:
            hints = scenario.get("hints", [])
            for hint_info in empty_fields["hints"]:
                hint_index = hint_info["index"]
                if hint_index < len(hints) and hint_index < len(extracted_data["hints"]):
                    hint = hints[hint_index]
                    new_hint = extracted_data["hints"][hint_index]
                    for field in hint_info["empty_fields"]:
                        if field in new_hint and new_hint[field]:
                            hint[field] = new_hint[field]
                            updated = True
        
        # 던전 업데이트
        if "dungeons" in empty_fields and "dungeons" in extracted_data:
            dungeons = scenario.get("dungeons", [])
            for dungeon_info in empty_fields["dungeons"]:
                dungeon_index = dungeon_info["index"]
                if dungeon_index < len(dungeons) and dungeon_index < len(extracted_data["dungeons"]):
                    dungeon = dungeons[dungeon_index]
                    new_dungeon = extracted_data["dungeons"][dungeon_index]
                    for field in dungeon_info["empty_fields"]:
                        if field in new_dungeon and new_dungeon[field]:
                            dungeon[field] = new_dungeon[field]
                            updated = True
        
        if updated:
            self.save_scenario(user_id, scenario_data)
            logger.info(f"사용자 {user_id}의 시나리오 누락 필드 업데이트 완료")
        
        return updated
    
    def ensure_scenario_npcs(self, user_id):
        """시나리오에 필요한 NPC들이 생성되어 있는지 확인하고 없으면 생성"""
        if not npc_manager:
            logger.warning("⚠️ NPC 매니저를 사용할 수 없습니다.")
            return False
            
        try:
            # 현재 시나리오 데이터 로드
            scenario_data = self.load_scenario(user_id)
            if not scenario_data:
                logger.warning("⚠️ 시나리오 데이터가 없어 NPC를 생성할 수 없습니다.")
                return False
            
            # NPC 생성 또는 확인
            logger.info(f"🎭 사용자 {user_id}의 시나리오 NPC 확인/생성 중...")
            npc_success = npc_manager.ensure_npcs_exist(user_id, scenario_data)
            
            if npc_success:
                logger.info(f"✅ 사용자 {user_id}의 시나리오 NPC 준비 완료")
                
                # 시나리오에 NPC 정보 추가 (참조만 저장)
                scenario_data["npc_generated"] = True
                scenario_data["npc_generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save_scenario(user_id, scenario_data)
                
                return True
            else:
                logger.error(f"❌ 사용자 {user_id}의 시나리오 NPC 생성 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ 시나리오 NPC 확인/생성 중 오류: {e}")
            return False
    
    def generate_npcs_for_current_scenario(self, user_id, force_regenerate=False):
        """현재 시나리오에 맞는 NPC 강제 생성"""
        if not npc_manager:
            logger.warning("⚠️ NPC 매니저를 사용할 수 없습니다.")
            return False
            
        try:
            # 현재 시나리오 데이터 로드
            scenario_data = self.load_scenario(user_id)
            if not scenario_data:
                logger.warning("⚠️ 시나리오 데이터가 없어 NPC를 생성할 수 없습니다.")
                return False
            
            # 기존 NPC가 있고 강제 재생성이 아니면 스킵
            if not force_regenerate:
                existing_npcs = npc_manager.load_npcs(user_id)
                if existing_npcs and len(existing_npcs) >= 3:
                    logger.info(f"✅ 기존 NPC가 충분히 있습니다: {len(existing_npcs)}명")
                    return True
            
            logger.info(f"🎭 사용자 {user_id}의 시나리오 기반 NPC 생성 시작...")
            
            # NPC 생성
            npc_success = npc_manager.create_npcs_for_scenario(user_id, scenario_data, npc_count=5)
            
            if npc_success:
                # 시나리오에 NPC 생성 기록
                scenario_data["npc_generated"] = True
                scenario_data["npc_generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                scenario_data["npc_force_regenerated"] = force_regenerate
                self.save_scenario(user_id, scenario_data)
                
                logger.info(f"✅ 사용자 {user_id}의 NPC 생성 완료")
                return True
            else:
                logger.error(f"❌ 사용자 {user_id}의 NPC 생성 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ NPC 생성 중 오류: {e}")
            return False
    
    def get_npc_summary_for_scenario(self, user_id):
        """시나리오용 NPC 요약 정보 반환"""
        if not npc_manager:
            return "NPC 매니저를 사용할 수 없습니다."
            
        try:
            return npc_manager.get_npc_summary(user_id)
        except Exception as e:
            logger.error(f"❌ NPC 요약 정보 조회 오류: {e}")
            return "NPC 정보를 조회할 수 없습니다."
    
    def is_npc_stage_complete(self, user_id):
        """NPC 단계가 완료되었는지 확인"""
        if not npc_manager:
            return False
            
        try:
            # NPC 매니저에서 NPC 존재 여부 확인
            existing_npcs = npc_manager.load_npcs(user_id)
            
            # 최소 3명의 NPC가 있어야 완료로 간주
            if existing_npcs and len(existing_npcs) >= 3:
                logger.info(f"✅ NPC 단계 완료 확인: {len(existing_npcs)}명")
                return True
            else:
                logger.info(f"⚠️ NPC 단계 미완료: {len(existing_npcs) if existing_npcs else 0}명")
                return False
                
        except Exception as e:
            logger.error(f"❌ NPC 단계 완료 확인 중 오류: {e}")
            return False

    def get_current_episode(self, user_id):
        """현재 진행중인 에피소드 정보 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return None
            
        episode_progress = scenario_data.get("episode_progress", {})
        
        # 진행중인 에피소드 찾기
        for episode_key, progress in episode_progress.items():
            if progress.get("status") == "진행중":
                # episode_key에서 ID 추출 (episode_1 -> 1)
                episode_id = episode_key.replace("episode_", "")
                episodes = scenario_data.get("scenario", {}).get("episodes", [])
                for episode in episodes:
                    if str(episode.get("id", "")) == episode_id:
                        return episode
        
        # 진행중인 에피소드가 없으면 첫 번째 에피소드 반환
        episodes = scenario_data.get("scenario", {}).get("episodes", [])
        return episodes[0] if episodes else None
    
    def get_next_episode_info(self, user_id):
        """다음 에피소드 정보 반환"""
        scenario_data = self.load_scenario(user_id)
        if not scenario_data:
            return None
            
        episodes = scenario_data.get("scenario", {}).get("episodes", [])
        if not episodes:
            return None
        
        episode_progress = scenario_data.get("episode_progress", {})
        
        # 현재 진행중인 에피소드 다음 에피소드 찾기
        current_episode_index = -1
        for i, episode in enumerate(episodes):
            episode_key = f"episode_{episode.get('id', i + 1)}"
            if episode_progress.get(episode_key, {}).get("status") == "진행중":
                current_episode_index = i
                break
        
        # 다음 에피소드가 있으면 반환
        if current_episode_index >= 0 and current_episode_index + 1 < len(episodes):
            return episodes[current_episode_index + 1]
        
        return None
    
    def advance_to_next_episode(self, user_id):
        """다음 에피소드로 진행"""
        try:
            scenario_data = self.load_scenario(user_id)
            if not scenario_data:
                return False
            
            episodes = scenario_data.get("scenario", {}).get("episodes", [])
            if not episodes:
                return False
            
            if "episode_progress" not in scenario_data:
                scenario_data["episode_progress"] = {}
            
            episode_progress = scenario_data["episode_progress"]
            
            # 현재 에피소드를 완료로 변경
            current_episode_index = -1
            for i, episode in enumerate(episodes):
                episode_key = f"episode_{episode.get('id', i + 1)}"
                if episode_progress.get(episode_key, {}).get("status") == "진행중":
                    episode_progress[episode_key]["status"] = "완료"
                    current_episode_index = i
                    break
            
            # 다음 에피소드를 진행중으로 설정
            if current_episode_index >= 0 and current_episode_index + 1 < len(episodes):
                next_episode = episodes[current_episode_index + 1]
                next_episode_key = f"episode_{next_episode.get('id', current_episode_index + 2)}"
                episode_progress[next_episode_key] = {
                    "status": "진행중",
                    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "round_count": 0
                }
                
                # 진행 상태 저장
                self.save_scenario(user_id, scenario_data)
                
                logger.info(f"에피소드 진행: 사용자 {user_id}, {current_episode_index + 1}번째 → {current_episode_index + 2}번째 에피소드")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"에피소드 진행 오류: {e}")
            return False

# 전역 인스턴스
scenario_manager = ScenarioManager() 