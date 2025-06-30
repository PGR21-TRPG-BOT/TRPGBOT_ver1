# -*- coding: utf-8 -*-
import logging
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import user_conversations, last_declaration_time, user_characters
from character_manager import CharacterManager
from session_manager import session_manager
from scenario_manager import scenario_manager
from random_character_generator import RandomCharacterGenerator
from message_processor import send_long_message

logger = logging.getLogger(__name__)

# 명령어 설명을 반환하는 함수
def get_commands_info():
    """사용 가능한 명령어와 설명을 반환합니다."""
    return """📋 사용 가능한 명령어:
/start - 봇 시작하기
/help - 도움말 보기
/declare - 대화 내용 저장하기 (선언)
/character - 캐릭터 정보 보기
/character 생성 - 새 캐릭터 생성 시작
/character 능력치 - 능력치 랜덤 생성 (4d6 중 최저값 제외)
/character 수정 - 캐릭터 데이터의 누락된 값 자동 채우기
/scenario - 현재 시나리오 정보 보기
/fill_scenario - 시나리오 빈 부분 자동 보완
/reset_scenario - 시나리오 초기화 및 새로 생성
/session - 현재 세션 확인 및 변경하기
/history - 세션 이력 보기
/roll - 주사위 굴리기
"""

# '/start' 명령어 처리 함수
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/start' 명령어를 입력했을 때 호출되는 함수입니다.
    봇이 시작되었음을 알리는 환영 메시지를 보냅니다.
    """
    user = update.effective_user # 메시지를 보낸 사용자 정보
    user_id = user.id
    
    # 대화 기록 초기화
    user_conversations[user_id] = []
    # 마지막 선언 시간 초기화
    last_declaration_time[user_id] = datetime.now()
    
    # 초기 세션을 '캐릭터_생성'으로 설정
    session_manager.log_session(user_id, "캐릭터_생성", "봇 시작 및 초기 세션 설정")
    
    # 환영 메시지와 사용 가능한 명령어 안내
    commands_info = get_commands_info()
    
    await update.message.reply_html(
        f"안녕하세요, 플레이어님 {user.mention_html()}!\n저는 TRPG 게임의 진행을 맡은 게임마스터입니다. 마스터라고 불러주세요.\n\n{commands_info}"
    )

# '/help' 명령어 처리 함수
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/help' 명령어를 입력했을 때 호출되는 함수입니다.
    봇의 사용 방법과 명령어를 안내합니다.
    """
    user_id = update.effective_user.id
    
    # 명령어 설명
    commands_info = get_commands_info()
    
    # 사용 방법 안내
    usage_guide = """
🎮 TRPG 봇 사용 방법:
1. 봇과 자유롭게 대화하세요. 모든 대화는 저장됩니다.
2. `/declare` 명령어를 사용하여 케릭터들의 대화 내용을 마스터에게 최종 결정 요청할 수 있습니다.
3. `/session` 명령어로 현재 게임 세션 상태를 확인하고 변경할 수 있습니다.
4. `/history` 명령어로 세션 이력을 확인할 수 있습니다.
5. 향후 `/character` 명령어로 캐릭터 관리가 가능해질 예정입니다.
    """
    
    await update.message.reply_text(f"{commands_info}\n{usage_guide}")

# '/declare' 명령어 처리 함수 (선언)
async def declare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/declare' 명령어를 입력했을 때 호출되는 함수입니다.
    이전 대화 내용을 저장합니다.
    """
    import os
    
    user_id = update.effective_user.id
    current_time = datetime.now()
    
    # 사용자의 대화 기록이 있는지 확인
    if user_id in user_conversations and user_conversations[user_id]:
        # 대화 기록을 저장할 디렉토리 확인 및 생성
        os.makedirs('conversations', exist_ok=True)
        
        # 고정 파일명 사용 (사용자 ID 기반)
        filename = f"conversations/conversation_{user_id}.txt"
        
        # 선언 시간 형식
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 대화 내용을 파일에 추가 (append 모드)
        with open(filename, 'a', encoding='utf-8') as f:
            # 이전 선언 시간과 현재 선언 시간 사이의 대화 저장 메시지 표시
            last_time = "시작" if user_id not in last_declaration_time else last_declaration_time[user_id].strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n======== {last_time} ~ {timestamp} 까지의 대화 ========\n\n")
            
            # 대화 내용 저장
            for message in user_conversations[user_id]:
                f.write(f"{message}\n")
        
        # 저장 완료 메시지
        await update.message.reply_text(f"이전 대화 내용이 '{filename}'에 저장되었습니다. (/declare 명령어 실행)")
        
        # 대화 기록 초기화하고 마지막 선언 시간 업데이트
        user_conversations[user_id] = []
        last_declaration_time[user_id] = current_time
    else:
        # 이전 선언 내역이 없으면 현재 시간 기록
        if user_id not in last_declaration_time:
            last_declaration_time[user_id] = current_time
        await update.message.reply_text("저장할 대화 내용이 없습니다. (/declare 명령어)")

# '/character' 명령어 처리 함수
async def character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/character' 명령어를 입력했을 때 호출되는 함수입니다.
    봇이 캐릭터 정보를 보냅니다.
    """
    user = update.effective_user # 메시지를 보낸 사용자 정보
    user_id = user.id
    
    # 인자 확인
    args = context.args
    
    # 캐릭터 정보 로드
    character_data = user_characters.get(user_id) or CharacterManager.load_character(user_id)
    
    # 부가 명령어 확인
    if args and len(args) > 0:
        command = args[0].lower()
        
        # null 값 수정 기능
        if command == "수정" or command == "fix":
            # null 값을 채우는 함수 호출
            updated_data = CharacterManager.fix_null_values_in_characters(user_id)
            if updated_data:
                await update.message.reply_text("캐릭터 데이터의 누락된 값을 업데이트했습니다. '/character' 명령어로 확인해보세요.")
            else:
                await update.message.reply_text("캐릭터 데이터를 업데이트하는 중 오류가 발생했습니다.")
            return
        
        # 캐릭터 목록 보기
        if command == "목록" or command == "list":
            # 캐릭터 목록 표시
            formatted_sheet = CharacterManager.format_character_sheet(character_data)
            await update.message.reply_text(formatted_sheet)
            return
        
        # 캐릭터 생성 모드
        if command == "생성" or command == "create":
            # 현재 세션 확인
            current_session = session_manager.get_current_session(user_id)
            session_type = current_session["current_session_type"] if current_session else "기타"
            
            if session_type != "캐릭터_생성" and character_data and CharacterManager.is_character_creation_complete(character_data):
                await update.message.reply_text(
                    "이미 생성된 캐릭터가 있습니다. 새 캐릭터를 만들려면 '/session' 명령어로 '캐릭터_생성' 세션으로 변경하세요."
                )
                return
            
            # 캐릭터 생성 초기화
            character_data = CharacterManager.init_character_creation(user_id)
            
            # 세션에 캐릭터 생성 중임을 표시
            context.user_data['creating_character'] = True
            
            # 첫 단계 안내 (이름 입력 요청)
            await update.message.reply_text(
                "새 캐릭터 생성을 시작합니다.\n\n"
                "캐릭터의 이름을 입력해주세요:"
            )
            return
        
        # 능력치 굴리기
        if command == "능력치" or command == "roll":
            ability_scores = RandomCharacterGenerator.roll_abilities()
            
            # 결과 메시지
            message = "능력치 굴림 결과 (4d6 중 최소값 제외):\n"
            for i, score in enumerate(ability_scores, 1):
                message += f"{i}. {score}\n"
            message += "\n이 값들을 원하는 능력치에 배정하세요."
            
            # 세션에 결과 저장
            context.user_data['ability_rolls'] = ability_scores
            
            await update.message.reply_text(message)
            return
    
    # 기본 캐릭터 정보 표시
    if character_data:
        formatted_sheet = CharacterManager.format_character_sheet(character_data)
        
        # 캐릭터 생성 진행 중인 경우 다음 항목 입력 안내
        next_field = CharacterManager.get_next_empty_field(character_data)
        
        if next_field and session_manager.get_current_session(user_id)["current_session_type"] == "캐릭터_생성":
            if next_field == "이름":
                formatted_sheet += "\n\n캐릭터의 이름을 입력해주세요:"
            elif next_field == "클래스":
                keyboard = [
                    [InlineKeyboardButton("전사", callback_data="charclass:전사")],
                    [InlineKeyboardButton("도적", callback_data="charclass:도적")],
                    [InlineKeyboardButton("마법사", callback_data="charclass:마법사")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    formatted_sheet + "\n\n클래스를 선택하세요:",
                    reply_markup=reply_markup
                )
                return
            elif next_field == "가치관":
                keyboard = [
                    [InlineKeyboardButton("질서", callback_data="charalign:질서")],
                    [InlineKeyboardButton("중립", callback_data="charalign:중립")],
                    [InlineKeyboardButton("혼돈", callback_data="charalign:혼돈")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    formatted_sheet + "\n\n가치관을 선택하세요:",
                    reply_markup=reply_markup
                )
                return
            elif next_field == "능력치":
                # 능력치 굴림 결과가 있는지 확인
                ability_rolls = context.user_data.get('ability_rolls', [])
                
                if ability_rolls:
                    ability_guide = "\n\n능력치를 배정해주세요. 다음과 같은 형식으로 입력해주세요:\n"
                    ability_guide += "근력:15, 민첩성:12, 건강:14, 지능:10, 지혜:8, 매력:13\n\n"
                    ability_guide += "능력치 굴림 결과 (참고):\n"
                    
                    for i, score in enumerate(ability_rolls, 1):
                        ability_guide += f"{i}. {score}\n"
                    
                    formatted_sheet += ability_guide
                else:
                    formatted_sheet += "\n\n능력치를 배정하기 전에 '/character 능력치' 명령어로 능력치를 굴려주세요."
            elif next_field == "기능":
                formatted_sheet += "\n\n기능을 선택해주세요. 2가지 기능을 선택할 수 있습니다.\n"
                formatted_sheet += "예: 운동, 은신\n\n"
                formatted_sheet += "같은 기능을 두 번 선택하면 +4 보너스를 받습니다."
        
        await update.message.reply_text(formatted_sheet)
    else:
        help_text = (
            "캐릭터가 없습니다. 다음 명령어를 사용해 캐릭터를 관리할 수 있습니다:\n"
            "/character 생성 - 새 캐릭터 생성 시작\n"
            "/character 능력치 - 능력치 랜덤 생성 (4d6 중 최저값 제외)\n"
            "\n먼저 '/session' 명령어로 '캐릭터_생성' 세션으로 변경하세요."
        )
        await update.message.reply_text(help_text)

# '/scenario' 명령어 처리 함수
async def scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/scenario' 명령어를 입력했을 때 호출되는 함수입니다.
    현재 시나리오 정보를 보여줍니다.
    """
    user_id = update.effective_user.id
    
    # 시나리오 데이터 로드
    scenario_data = scenario_manager.load_scenario(user_id)
    
    if not scenario_data:
        await update.message.reply_text(
            "생성된 시나리오가 없습니다.\n"
            "'/session' 명령어로 '시나리오_생성' 세션으로 변경하여 시나리오를 만들어보세요."
        )
        return
    
    # 시나리오 정보 포맷팅
    scenario = scenario_data.get("scenario", {})
    current_stage = scenario_data.get("current_stage", "개요")
    progress = scenario_data.get("progress", "시작_전")
    
    message_parts = []
    
    # 기본 정보
    message_parts.append(f"🎭 **현재 시나리오 상태**")
    message_parts.append(f"📊 진행도: {progress}")
    message_parts.append(f"🔄 현재 단계: {current_stage}")
    message_parts.append("")
    
    # 시나리오 개요
    overview = scenario.get("overview", {})
    if overview.get("theme"):
        message_parts.append("📋 **시나리오 개요**")
        if overview.get("title"):
            message_parts.append(f"제목: {overview['title']}")
        message_parts.append(f"테마: {overview.get('theme', '미정')}")
        message_parts.append(f"배경: {overview.get('setting', '미정')}")
        message_parts.append(f"주요 갈등: {overview.get('main_conflict', '미정')}")
        message_parts.append(f"목표: {overview.get('objective', '미정')}")
        if overview.get("rewards"):
            message_parts.append(f"보상: {overview['rewards']}")
        message_parts.append("")
    
    # 에피소드 정보
    episodes = scenario.get("episodes", [])
    if episodes:
        message_parts.append("📖 **에피소드 구성**")
        for i, episode in enumerate(episodes, 1):
            message_parts.append(f"{i}. {episode.get('title', f'에피소드 {i}')}")
            if episode.get("objective"):
                message_parts.append(f"   목표: {episode['objective']}")
        message_parts.append("")
    
    # NPC 정보
    npcs = scenario.get("npcs", [])
    if npcs:
        message_parts.append("👥 **주요 NPC**")
        for npc in npcs:
            name = npc.get("name", "이름없음")
            relationship = npc.get("relationship", "역할미정")
            message_parts.append(f"• {name} ({relationship})")
            if npc.get("personality"):
                message_parts.append(f"  성격: {npc['personality']}")
        message_parts.append("")
    
    # 힌트 정보
    hints = scenario.get("hints", [])
    if hints:
        message_parts.append("🔍 **힌트 시스템**")
        for i, hint in enumerate(hints, 1):
            content = hint.get("content", "내용없음")
            method = hint.get("discovery_method", "방법미정")
            message_parts.append(f"{i}. {content}")
            message_parts.append(f"   발견방법: {method}")
        message_parts.append("")
    
    # 던전/탐험지 정보
    dungeons = scenario.get("dungeons", [])
    if dungeons:
        message_parts.append("🏰 **던전/탐험지**")
        for dungeon in dungeons:
            name = dungeon.get("name", "이름없음")
            type_info = dungeon.get("type", "유형미정")
            message_parts.append(f"• {name} ({type_info})")
            if dungeon.get("description"):
                message_parts.append(f"  설명: {dungeon['description']}")
        message_parts.append("")
    
    # 세션 진행 기록
    sessions = scenario.get("sessions", [])
    if sessions:
        message_parts.append("📊 **세션 진행 기록**")
        for session in sessions:
            session_type = session.get("type", "알 수 없음")
            play_count = session.get("play_count", 0)
            last_played = session.get("last_played", "없음")
            message_parts.append(f"• {session_type}: {play_count}회 진행 (마지막: {last_played})")
    
    final_message = "\n".join(message_parts)
    
    # 긴 메시지 처리
    await send_long_message(update.message, final_message, "📋 [시나리오 정보]")

# '/session' 명령어 처리 함수
async def session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/session' 명령어를 입력했을 때 호출되는 함수입니다.
    세션을 생성하거나 기존 세션 정보를 확인합니다.
    """
    user = update.effective_user
    user_id = user.id
    
    # 세션 종류 버튼 생성 (인라인 키보드)
    keyboard = [
        [InlineKeyboardButton("캐릭터_생성", callback_data="session:캐릭터_생성")],
        [InlineKeyboardButton("시나리오_생성", callback_data="session:시나리오_생성")],
        [InlineKeyboardButton("파티_결성", callback_data="session:파티_결성")],
        [InlineKeyboardButton("모험_준비", callback_data="session:모험_준비")],
        [InlineKeyboardButton("모험_진행", callback_data="session:모험_진행")],
        [InlineKeyboardButton("던전_탐험", callback_data="session:던전_탐험")],
        [InlineKeyboardButton("증거_수집", callback_data="session:증거_수집")],
        [InlineKeyboardButton("의뢰_해결", callback_data="session:의뢰_해결")],
        [InlineKeyboardButton("모험_정리", callback_data="session:모험_정리")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 현재 세션 정보 가져오기
    current_session = session_manager.get_current_session(user_id)
    
    # 현재 세션 종류 표시
    if current_session:
        current_type = current_session["current_session_type"]
        session_id = current_session.get("session_id", current_session.get("current_session_id", "새로운 세션"))
        await update.message.reply_text(
            f"현재 세션 정보:\n\n"
            f"세션 종류: {current_type}\n"
            f"세션 ID: {session_id}\n\n"
            f"세션 종류를 변경하려면 아래 버튼을 누르세요:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "현재 활성화된 세션이 없습니다.\n"
            "세션 종류를 선택하세요:",
            reply_markup=reply_markup
        )

# '/history' 명령어 처리 함수 (세션이력)
async def show_session_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/history' 명령어를 입력했을 때 호출되는 함수입니다.
    세션 이력을 보여줍니다.
    """
    user_id = update.effective_user.id
    
    # 세션 이력 조회 (최근 10개)
    history = session_manager.get_session_history(user_id, 10)
    
    if not history:
        await update.message.reply_text("세션 이력이 없습니다. (/history 명령어)")
        return
        
    # 이력 메시지 구성
    message = "📜 세션 이력 (최근 10개): (/history 명령어)\n\n"
    for i, entry in enumerate(history, 1):
        message += f"{i}. {entry['timestamp']} - {entry['session_type']}\n"
        message += f"   {entry['content'][:]}...\n\n"
        
    await update.message.reply_text(message)

# '/roll' 명령어 처리 함수
async def roll_dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/roll' 명령어를 입력했을 때 호출되는 함수입니다.
    주사위를 굴려 결과를 보여줍니다.
    기본적으로 1d6(6면체 주사위 1개)를 굴립니다.
    매개변수 형식: NdM (N: 주사위 개수, M: 주사위 면 수)
    예시: /roll 2d20 -> 20면체 주사위 2개를 굴립니다.
    """
    user = update.effective_user
    user_id = user.id
    
    # 기본값 설정: 1d6 (6면체 주사위 1개)
    dice_count = 1
    dice_faces = 6
    
    # 메시지에서 인자 추출 (주사위 형식: NdM)
    args = context.args
    if args and len(args) > 0:
        dice_format = args[0].lower()
        try:
            # NdM 형식으로 입력된 경우 파싱
            if 'd' in dice_format:
                parts = dice_format.split('d')
                if len(parts) == 2:
                    # 주사위 개수와 면 수 추출
                    if parts[0]:  # 주사위 개수가 입력된 경우
                        dice_count = int(parts[0])
                    # 주사위 면 수 추출
                    if parts[1]:  # 주사위 면 수가 입력된 경우
                        dice_faces = int(parts[1])
                    
                    # 값 검증 및 제한
                    dice_count = min(max(1, dice_count), 10)  # 1~10개 제한
                    dice_faces = min(max(2, dice_faces), 100)  # 2~100면 제한
        except ValueError:
            # 파싱 오류 시 기본값 사용
            dice_count = 1
            dice_faces = 6
    
    # 주사위 굴리기
    dice_results = [random.randint(1, dice_faces) for _ in range(dice_count)]
    total_result = sum(dice_results)
    
    # 주사위 모양 이모지
    dice_emoji = "🎲"
    
    # 결과 메시지
    if dice_count == 1:
        message = f"{dice_emoji} {dice_count}d{dice_faces} 주사위 결과: {dice_results[0]}"
    else:
        message = f"{dice_emoji} {dice_count}d{dice_faces} 주사위 결과: {dice_results} = {total_result}"
    
    # 현재 세션 상태 확인 및 로그 기록
    current_session = session_manager.get_current_session(user_id)
    session_type = current_session["current_session_type"] if current_session else "기타"
    
    # 세션 로그에 주사위 결과 기록
    session_manager.log_session(
        user_id, 
        session_type, 
        f"주사위 결과: {dice_count}d{dice_faces} = {dice_results if dice_count > 1 else dice_results[0]}"
    )
    
    # 대화 기록에 주사위 굴리기 결과 저장
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    dice_log_message = f"{dice_count}d{dice_faces} = {dice_results if dice_count > 1 else dice_results[0]}"
    if dice_count > 1:
        dice_log_message += f" (합계: {total_result})"
    
    user_conversations[user_id].append(f"시스템: {user.username or user.first_name}님이 주사위를 굴렸습니다. {dice_log_message}")
        
    await update.message.reply_text(message)

# 인라인 버튼 콜백 처리
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """인라인 버튼 콜백 처리"""
    query = update.callback_query
    await query.answer()
    
    # 콜백 데이터 처리
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("session:"):
        # 세션 변경 처리
        session_type = data.split(":", 1)[1]
        session_id = session_manager.log_session(
            user_id, 
            session_type, 
            f"세션 시작: {session_type}"
        )
        
        await query.edit_message_text(
            f"세션이 변경되었습니다!\n\n"
            f"현재 세션: {session_type}\n"
            f"세션 ID: {session_id}"
        )
    elif data.startswith("charclass:"):
        # 캐릭터 클래스 선택 처리
        selected_class = data.split(":", 1)[1]
        
        # 캐릭터 정보에 클래스 저장
        CharacterManager.update_character_field(user_id, "클래스", selected_class)
        
        # 가치관 선택 화면으로 자동 진행
        character_data = CharacterManager.load_character(user_id)
        formatted_sheet = CharacterManager.format_character_sheet(character_data)
        
        keyboard = [
            [InlineKeyboardButton("질서", callback_data="charalign:질서")],
            [InlineKeyboardButton("중립", callback_data="charalign:중립")],
            [InlineKeyboardButton("혼돈", callback_data="charalign:혼돈")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{formatted_sheet}\n\n"
            f"가치관을 선택하세요:",
            reply_markup=reply_markup
        )
    elif data.startswith("charalign:"):
        # 가치관 선택 처리
        selected_alignment = data.split(":", 1)[1]
        
        # 캐릭터 정보에 가치관 저장
        CharacterManager.update_character_field(user_id, "가치관", selected_alignment)
        
        # 능력치 생성 안내
        character_data = CharacterManager.load_character(user_id)
        formatted_sheet = CharacterManager.format_character_sheet(character_data)
        
        await query.edit_message_text(
            f"{formatted_sheet}\n\n"
            f"이제 능력치를 생성하세요. '/character 능력치' 명령어를 사용하여 능력치를 굴려주세요."
        )
    elif data.startswith("charconfirm:"):
        # 캐릭터 생성 확정
        confirm = data.split(":", 1)[1]
        
        if confirm == "yes":
            character_data = CharacterManager.load_character(user_id)
            if character_data and CharacterManager.is_character_creation_complete(character_data):
                # 캐릭터 생성 완료 메시지
                formatted_sheet = CharacterManager.format_character_sheet(character_data)
                await query.edit_message_text(
                    f"캐릭터 생성이 완료되었습니다!\n\n{formatted_sheet}"
                )
                
                # 세션 로그 기록
                current_session = session_manager.get_current_session(user_id)
                session_type = current_session["current_session_type"] if current_session else "기타"
                session_manager.log_session(
                    user_id, 
                    session_type, 
                    f"캐릭터 생성 완료: {character_data['이름']} ({character_data['클래스']})"
                )
                
                # 임시 데이터 삭제
                if 'creating_character' in context.user_data:
                    del context.user_data['creating_character']
                if 'ability_rolls' in context.user_data:
                    del context.user_data['ability_rolls']
            else:
                await query.edit_message_text(
                    "캐릭터 생성에 필요한 정보가 부족합니다. 다시 시도해주세요."
                )
        elif confirm == "no":
            await query.edit_message_text(
                "캐릭터 생성이 취소되었습니다."
            )
            # 임시 데이터 삭제
            if 'creating_character' in context.user_data:
                del context.user_data['creating_character']
            if 'ability_rolls' in context.user_data:
                del context.user_data['ability_rolls']

# '/fill_scenario' 명령어 처리 함수  
async def fill_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/fill_scenario' 명령어를 입력했을 때 호출되는 함수입니다.
    시나리오의 빈 필드를 자동으로 보완합니다.
    """
    from message_processor import extract_missing_scenario_info
    from scenario_manager import scenario_manager
    
    user_id = update.effective_user.id
    
    # 빈 필드 찾기 및 보완
    missing_filled = extract_missing_scenario_info(user_id, "전체 빈 부분 채워줘", [])
    
    if missing_filled:
        await update.message.reply_text(
            "✅ **시나리오의 누락된 정보를 성공적으로 보완했습니다!**\n\n"
            "'/scenario' 명령어로 업데이트된 시나리오를 확인해보세요."
        )
    else:
        # 빈 필드 확인
        empty_fields = scenario_manager.find_empty_fields(user_id)
        if empty_fields:
            missing_info = []
            for section, fields in empty_fields.items():
                if section == "overview":
                    missing_info.append(f"📋 개요: {len(fields)}개 필드 누락")
                elif section == "episodes":
                    missing_info.append(f"📖 에피소드: {len(fields)}개 에피소드 불완전")
                elif section == "npcs":
                    missing_info.append(f"👥 NPC: {len(fields)}개 NPC 불완전")
                elif section == "hints":
                    missing_info.append(f"🔍 힌트: {len(fields)}개 힌트 불완전") 
                elif section == "dungeons":
                    missing_info.append(f"🏰 던전: {len(fields)}개 던전 불완전")
            
            await update.message.reply_text(
                "⚠️ **시나리오에 누락된 정보가 있지만 자동 보완에 실패했습니다.**\n\n"
                f"**누락된 정보:**\n" + "\n".join(missing_info) + "\n\n"
                "'/session 시나리오_생성'으로 수동으로 정보를 추가해주세요."
            )
        else:
            await update.message.reply_text(
                "✅ **시나리오가 이미 완성되어 있습니다!**\n\n"
                "모든 필요한 정보가 채워져 있습니다."
            ) 

# '/reset_scenario' 명령어 처리 함수  
async def reset_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    사용자가 '/reset_scenario' 명령어를 입력했을 때 호출되는 함수입니다.
    시나리오를 초기화하고 새로 생성합니다.
    """
    from scenario_manager import scenario_manager
    
    user_id = update.effective_user.id
    
    # 기존 시나리오 삭제
    import os
    scenario_file = f'scenarios/scenario_{user_id}.json'
    if os.path.exists(scenario_file):
        try:
            os.remove(scenario_file)
            await update.message.reply_text(
                "🗑️ **기존 시나리오 파일을 삭제했습니다.**\n\n"
                "새로운 시나리오를 생성하려면 '/session 시나리오_생성'으로 시작하세요."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 시나리오 파일 삭제 중 오류: {e}")
    else:
        await update.message.reply_text(
            "ℹ️ **삭제할 시나리오 파일이 없습니다.**\n\n"
            "새로운 시나리오를 생성하려면 '/session 시나리오_생성'으로 시작하세요."
        ) 