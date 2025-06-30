# -*- coding: utf-8 -*-
import logging
import json
import os
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from trpgbot_ragmd_sentencetr import find_similar_chunks, generate_answer_with_rag
from dotenv import load_dotenv
import time

# 환경 변수 로드 (로컬 개발 환경용)
load_dotenv()

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 플레이어 봇 설정
PLAYER_BOT_TOKEN = os.getenv('PLAYER3_BOT_TOKEN')  # 플레이어 봇 토큰
MASTER_CHAT_ID = os.getenv('MASTER_CHAT_ID')      # 마스터 봇이 있는 채팅 ID

# 플레이어 상태 저장
player_conversations = {}
player_character = {}
player_settings = {}

class PlayerCharacter:
    """플레이어 캐릭터 클래스"""
    
    def __init__(self, character_data=None):
        if character_data:
            self.load_from_data(character_data)
        else:
            # 기본 캐릭터 설정
            self.name = ""
            self.class_type = ""
            self.level = 1
            self.alignment = ""
            self.background = ""
            self.personality = ""
            self.goals = ""
            self.fears = ""
            
            # 능력치
            self.strength = 10
            self.dexterity = 10
            self.constitution = 10
            self.intelligence = 10
            self.wisdom = 10
            self.charisma = 10
            
            # 게임 스탯
            self.hp = 8
            self.max_hp = 8
            self.ac = 10
            self.initiative = 0
            
            # 기능과 장비
            self.skills = []
            self.equipment = []
            self.spells = []
    
    def load_from_data(self, data):
        """JSON 데이터에서 캐릭터 로드"""
        self.name = data.get("이름", "")
        self.class_type = data.get("클래스", "")
        self.level = data.get("레벨", 1)
        self.alignment = data.get("가치관", "")
        self.background = data.get("배경", "")
        self.personality = data.get("성격", "")
        self.goals = data.get("목표", "")
        self.fears = data.get("두려워하는것", "")
        
        # 능력치
        self.strength = data.get("근력", 10)
        self.dexterity = data.get("민첩성", 10)
        self.constitution = data.get("건강", 10)
        self.intelligence = data.get("지능", 10)
        self.wisdom = data.get("지혜", 10)
        self.charisma = data.get("매력", 10)
        
        # 게임 스탯
        self.hp = data.get("HP", 8)
        self.max_hp = data.get("최대HP", 8)
        self.ac = data.get("장갑", 10)
        self.initiative = data.get("행동순서", 0)
        
        # 기타
        self.skills = data.get("기능", [])
        self.equipment = data.get("장비", [])
        self.spells = data.get("주문", [])
    
    def get_personality_prompt(self):
        """캐릭터 성격 기반 프롬프트 생성"""
        return f"""
당신은 '{self.name}'라는 {self.class_type} 캐릭터를 플레이하고 있습니다.

## 캐릭터 정보:
- **이름**: {self.name}
- **클래스**: {self.class_type} (레벨 {self.level})
- **가치관**: {self.alignment}
- **배경**: {self.background}
- **성격**: {self.personality}
- **목표**: {self.goals}
- **두려워하는 것**: {self.fears}

## 능력치:
- 근력: {self.strength}, 민첩성: {self.dexterity}, 건강: {self.constitution}
- 지능: {self.intelligence}, 지혜: {self.wisdom}, 매력: {self.charisma}
- HP: {self.hp}/{self.max_hp}, 장갑: {self.ac}

## 기능: {', '.join(self.skills) if self.skills else '없음'}
## 주요 장비: {', '.join(self.equipment[:3]) if self.equipment else '없음'}

## 플레이 가이드라인:
1. 캐릭터의 성격과 배경에 맞게 행동하세요
2. 가치관에 따라 도덕적 판단을 하세요
3. 목표를 달성하려 노력하고, 두려워하는 것은 피하려 하세요
4. 클래스 특성을 활용한 행동을 제안하세요
5. 파티원들과 협력하되 개성을 유지하세요
6. 상황에 맞는 감정 표현을 하세요

# 당신의 성격은 분석적이지만 온화하고 친절한 것을 좋아합니다. 

항상 '{self.name}' 캐릭터의 시점에서 1인칭으로 대화하세요.
"""

def load_character_from_file(user_id):
    """저장된 캐릭터 파일에서 로드"""
    character_file = f'characters/character_{user_id}.json'
    if os.path.exists(character_file):
        try:
            with open(character_file, 'r', encoding='utf-8') as f:
                character_data = json.load(f)
            return PlayerCharacter(character_data)
        except Exception as e:
            logger.error(f"캐릭터 로드 오류: {e}")
    return None

def save_player_settings(user_id, settings):
    """플레이어 설정 저장"""
    os.makedirs('player_settings', exist_ok=True)
    settings_file = f'player_settings/player_{user_id}.json'
    
    try:
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"플레이어 설정 저장 오류: {e}")
        return False

def load_player_settings(user_id):
    """플레이어 설정 로드"""
    settings_file = f'player_settings/player_{user_id}.json'
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"플레이어 설정 로드 오류: {e}")
    
    return {
        "character_loaded": False,
        "auto_response": False,
        "response_style": "balanced"  # active, balanced, passive
    }

# 명령어 핸들러들
async def start_command(update: Update, context):
    """시작 명령어"""
    user = update.effective_user
    user_id = user.id
    
    # 플레이어 설정 로드
    settings = load_player_settings(user_id)
    player_settings[user_id] = settings
    
    welcome_text = f"""
🎭 **TRPG 플레이어 봇에 오신 것을 환영합니다!**

안녕하세요, {user.first_name}님! 
저는 당신의 캐릭터를 대신해서 TRPG를 플레이해드리는 봇입니다.

## 🎯 주요 기능:
- 캐릭터 로드 및 롤플레이
- 상황에 맞는 행동 제안
- 주사위 굴리기 및 판정
- 다른 플레이어/마스터와 상호작용

## 📋 명령어:
/character - 캐릭터 로드하기
/status - 현재 상태 확인
/settings - 봇 설정 변경
/help - 도움말 보기

시작하려면 먼저 /character 명령어로 캐릭터를 로드해주세요!
"""
    
    await update.message.reply_text(welcome_text)

async def character_command(update: Update, context):
    """캐릭터 로드 명령어"""
    user_id = update.effective_user.id
    
    # 기존 캐릭터 파일에서 로드 시도
    character = load_character_from_file(user_id)
    
    if character and character.name:
        player_character[user_id] = character
        player_settings[user_id]["character_loaded"] = True
        save_player_settings(user_id, player_settings[user_id])
        
        await update.message.reply_text(f"""
✅ **캐릭터가 로드되었습니다!**

🎭 **{character.name}** ({character.class_type})
- 레벨: {character.level}
- 가치관: {character.alignment}
- HP: {character.hp}/{character.max_hp}
- 장갑: {character.ac}

이제 저는 {character.name}이 되어 모험을 함께하겠습니다!
마스터의 상황 설명을 기다리거나, 직접 대화를 시작해보세요.
""")
    else:
        # 캐릭터 생성 안내
        keyboard = [
            [InlineKeyboardButton("🎲 랜덤 캐릭터 생성", callback_data="create_random")],
            [InlineKeyboardButton("✍️ 직접 캐릭터 입력", callback_data="create_manual")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "저장된 캐릭터가 없습니다. 새로운 캐릭터를 만드시겠어요?",
            reply_markup=reply_markup
        )

async def status_command(update: Update, context):
    """상태 확인 명령어"""
    user_id = update.effective_user.id
    
    if user_id not in player_character or not player_character[user_id].name:
        await update.message.reply_text("먼저 /character 명령어로 캐릭터를 로드해주세요.")
        return
    
    character = player_character[user_id]
    settings = player_settings.get(user_id, {})
    
    status_text = f"""
🎭 **현재 플레이 중인 캐릭터**

**{character.name}** - {character.class_type} 레벨 {character.level}
📍 가치관: {character.alignment}
💚 HP: {character.hp}/{character.max_hp}
🛡️ 장갑: {character.ac}

**능력치:**
💪 근력: {character.strength} | 🏃 민첩성: {character.dexterity} | 🏥 건강: {character.constitution}
🧠 지능: {character.intelligence} | 👁️ 지혜: {character.wisdom} | 😊 매력: {character.charisma}

**기능:** {', '.join(character.skills) if character.skills else '없음'}

**주요 장비:** {', '.join(character.equipment[:5]) if character.equipment else '없음'}

**봇 설정:**
- 자동 응답: {'켜짐' if settings.get('auto_response', False) else '꺼짐'}
- 응답 스타일: {settings.get('response_style', 'balanced')}
"""
    
    await update.message.reply_text(status_text)

async def settings_command(update: Update, context):
    """설정 명령어"""
    user_id = update.effective_user.id
    settings = player_settings.get(user_id, load_player_settings(user_id))
    
    keyboard = [
        [InlineKeyboardButton(
            f"🤖 자동 응답: {'켜짐' if settings.get('auto_response', False) else '꺼짐'}",
            callback_data="toggle_auto_response"
        )],
        [InlineKeyboardButton("🎭 응답 스타일 변경", callback_data="change_style")],
        [InlineKeyboardButton("🔄 캐릭터 재로드", callback_data="reload_character")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛠️ **플레이어 봇 설정**\n\n어떤 설정을 변경하시겠어요?",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context):
    """도움말 명령어"""
    help_text = """
🎭 **TRPG 플레이어 봇 사용법**

## 📋 기본 명령어:
/start - 봇 시작
/character - 캐릭터 로드/생성
/status - 현재 상태 확인
/settings - 봇 설정
/roll [주사위] - 주사위 굴리기 (예: /roll 1d20, /roll 3d6)

## 🎯 사용 방법:

**1. 캐릭터 설정**
- `/character`로 캐릭터를 로드하거나 새로 만드세요
- 기존 마스터 봇에서 만든 캐릭터를 자동으로 불러옵니다

**2. 롤플레이**
- 마스터의 상황 설명에 캐릭터답게 반응합니다
- 캐릭터의 성격, 배경, 목표에 맞는 행동을 제안합니다
- 자연스러운 대화로 상호작용하세요

**3. 자동 응답 모드**
- 설정에서 자동 응답을 켜면 상황에 맞게 자동으로 반응합니다
- 응답 스타일을 조절할 수 있습니다 (적극적/균형잡힌/소극적)

**4. 협력 플레이**
- 다른 플레이어들과 협력하여 모험을 진행합니다
- 각자의 특기를 살린 역할 분담을 제안합니다

즐거운 모험 되세요! 🎲✨
"""
    
    await update.message.reply_text(help_text)

async def roll_command(update: Update, context):
    """주사위 굴리기 명령어"""
    user_id = update.effective_user.id
    
    if user_id not in player_character or not player_character[user_id].name:
        await update.message.reply_text("먼저 캐릭터를 로드해주세요.")
        return
    
    character = player_character[user_id]
    
    if not context.args:
        # 기본 주사위 옵션 제공
        keyboard = [
            [InlineKeyboardButton("🎲 1d20", callback_data="roll_1d20"),
             InlineKeyboardButton("🎲 1d6", callback_data="roll_1d6")],
            [InlineKeyboardButton("⚔️ 공격 굴림", callback_data="roll_attack"),
             InlineKeyboardButton("🛡️ 극복 판정", callback_data="roll_save")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎲 **{character.name}의 주사위 굴리기**\n\n어떤 주사위를 굴리시겠어요?",
            reply_markup=reply_markup
        )
        return
    
    # 주사위 파싱 및 굴리기
    dice_notation = context.args[0]
    result = roll_dice(dice_notation)
    
    if result:
        await update.message.reply_text(
            f"🎲 **{character.name}**: {dice_notation} → **{result['total']}**\n"
            f"상세: {result['details']}"
        )
    else:
        await update.message.reply_text(
            "올바른 주사위 표기법을 사용해주세요. (예: 1d20, 3d6+2)"
        )

def roll_dice(notation):
    """주사위 굴리기 함수"""
    import re
    
    # 주사위 표기법 파싱 (예: 2d6+3, 1d20-1)
    pattern = r'(\d+)d(\d+)([+-]\d+)?'
    match = re.match(pattern, notation.lower())
    
    if not match:
        return None
    
    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0
    
    if num_dice > 20 or die_size > 100:  # 제한
        return None
    
    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    
    details = f"[{', '.join(map(str, rolls))}]"
    if modifier != 0:
        details += f" {'+' if modifier > 0 else ''}{modifier}"
    
    return {
        'total': total,
        'details': details,
        'rolls': rolls,
        'modifier': modifier
    }

async def button_callback(update: Update, context):
    """인라인 키보드 버튼 콜백"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    if data == "create_random":
        # 랜덤 캐릭터 생성 (마스터 봇의 랜덤 생성 기능 활용)
        await query.edit_message_text(
            "🎲 랜덤 캐릭터를 생성하려면 마스터 봇에서 먼저 캐릭터를 생성해주세요.\n"
            "생성 후 다시 /character 명령어를 사용하면 자동으로 로드됩니다."
        )
    
    elif data == "create_manual":
        await query.edit_message_text(
            "✍️ 직접 캐릭터를 입력하려면 마스터 봇에서 캐릭터 생성 세션을 진행해주세요.\n"
            "생성 후 다시 /character 명령어를 사용하면 자동으로 로드됩니다."
        )
    
    elif data == "toggle_auto_response":
        settings = player_settings.get(user_id, load_player_settings(user_id))
        settings["auto_response"] = not settings.get("auto_response", False)
        player_settings[user_id] = settings
        save_player_settings(user_id, settings)
        
        status = "켜짐" if settings["auto_response"] else "꺼짐"
        await query.edit_message_text(f"🤖 자동 응답이 {status}되었습니다.")
    
    elif data == "change_style":
        keyboard = [
            [InlineKeyboardButton("🔥 적극적", callback_data="style_active")],
            [InlineKeyboardButton("⚖️ 균형잡힌", callback_data="style_balanced")], 
            [InlineKeyboardButton("🤐 소극적", callback_data="style_passive")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎭 **응답 스타일 선택:**\n\n"
            "🔥 적극적: 항상 먼저 행동을 제안\n"
            "⚖️ 균형잡힌: 상황에 맞게 반응\n"
            "🤐 소극적: 질문받을 때만 대답",
            reply_markup=reply_markup
        )
    
    elif data.startswith("style_"):
        style = data.replace("style_", "")
        settings = player_settings.get(user_id, load_player_settings(user_id))
        settings["response_style"] = style
        player_settings[user_id] = settings
        save_player_settings(user_id, settings)
        
        style_names = {"active": "적극적", "balanced": "균형잡힌", "passive": "소극적"}
        await query.edit_message_text(f"🎭 응답 스타일이 '{style_names[style]}'으로 변경되었습니다.")
    
    elif data.startswith("roll_"):
        character = player_character.get(user_id)
        if not character:
            await query.edit_message_text("먼저 캐릭터를 로드해주세요.")
            return
        
        if data == "roll_1d20":
            result = roll_dice("1d20")
        elif data == "roll_1d6":
            result = roll_dice("1d6")
        elif data == "roll_attack":
            # 공격 굴림 (기본 공격 보너스 포함)
            attack_bonus = character.level  # 간단화
            result = roll_dice(f"1d20+{attack_bonus}")
        elif data == "roll_save":
            # 극복 판정 (레벨 기반)
            save_bonus = character.level // 2
            result = roll_dice(f"1d20+{save_bonus}")
        
        if result:
            await query.edit_message_text(
                f"🎲 **{character.name}**: {data.replace('roll_', '')} → **{result['total']}**\n"
                f"상세: {result['details']}"
            )

async def handle_message(update: Update, context):
    """일반 메시지 처리"""
    user = update.effective_user
    user_id = user.id
    text = update.message.text
    
    # 대화 기록 저장
    if user_id not in player_conversations:
        player_conversations[user_id] = []
    
    player_conversations[user_id].append(f"플레이어: {text}")
    
    # 캐릭터가 로드되지 않은 경우
    if user_id not in player_character or not player_character[user_id].name:
        await update.message.reply_text(
            "먼저 /character 명령어로 캐릭터를 로드해주세요."
        )
        return
    
    character = player_character[user_id]
    settings = player_settings.get(user_id, {})
    
    # 캐릭터 관점에서 응답 생성
    character_prompt = character.get_personality_prompt()
    
    # 상황 분석 및 응답 생성
    situation_context = f"""
상황: {text}

{character_prompt}

위 상황에서 {character.name}이 어떻게 반응하고 행동할지 결정해주세요.

응답 스타일: {settings.get('response_style', 'balanced')}
- active: 적극적으로 행동을 제안하고 주도적으로 나서기
- balanced: 상황에 맞게 적절히 반응하기  
- passive: 조심스럽게 반응하고 다른 이의 의견 먼저 듣기

아래와 같은 메뉴 중에 상황에 맞는 한가지를 선택하여 대화를 하거나 행동을 묘사해주세요:
1. {character.name}의 즉각적인 **행동**/감정 - RolePlaying 에 도움이 되고 시나리오의 흐름을 진전 시키는 **행동**과 반응을 제안해주세요.
2. 취할 행동이나 제안
3. 필요시 주사위 굴림 제안
4. 다른 케릭터와 대화
5. /declare 명령으로 상황 선언, 다른 케릭터들의 행동을 최종 선언

# 항상 다른 설명 없이 캐릭터의 시점에서 1인칭으로 대화하거나 행동을 표현하세요.
 - 예 : 세리나는 아무말 없이 적의 뒤로 돌아가기 위해 살금살금 걸어가겠어요.
"""
    # 다음 형식으로 답변해주세요
    # time.sleep()
    # RAG를 통한 응답 생성
    relevant_chunks = find_similar_chunks(text, match_count=2, match_threshold=0.5)
    response = generate_answer_with_rag(situation_context, relevant_chunks, "플레이어", "")
    
    # 봇 응답 저장
    player_conversations[user_id].append(f"{character.name}: {response}")
    
    # 응답 전송
    await update.message.reply_text(f"🎭 **{character.name}**\n\n{response}")

def main():
    """메인 함수"""
    if not PLAYER_BOT_TOKEN:
        logger.error("PLAYER_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        return
    
    # 애플리케이션 생성
    application = Application.builder().token(PLAYER_BOT_TOKEN).build()
    
    # 핸들러 등록
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("character", character_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("roll", roll_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 봇 실행
    logger.info("플레이어 봇 시작됨")
    application.run_polling()

if __name__ == '__main__':
    main() 