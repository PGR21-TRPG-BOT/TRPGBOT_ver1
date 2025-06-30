# -*- coding: utf-8 -*-
import logging # 로깅 모듈 임포트
import os # 환경 변수 사용을 위한 os 모듈 임포트
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # 텔레그램 업데이트 객체 (메시지 등 포함)
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler # 봇 애플리케이션, 핸들러 등 관련 클래스 임포트
from dotenv import load_dotenv # .env 파일에서 환경 변수 로드
from trpgbot_ragmd_sentencetr import find_similar_chunks, generate_answer_with_rag, GENERATION_MODEL
import json # JSON 처리를 위한 모듈
from datetime import datetime # 날짜/시간 처리
from session_manager import session_manager, SESSION_TYPES # 세션 관리자 임포트
import random # 주사위 굴리기 기능을 위한 랜덤 모듈 추가
from copy import deepcopy # 깊은 복사를 위한 copy 모듈 임포트
import re # 정규 표현식을 위한 re 모듈 임포트
import traceback # 예외 처리를 위한 traceback 모듈 임포트
import google.generativeai as genai # Google Generative AI 모듈 임포트

# 로깅 설정: 봇의 활동 및 오류를 콘솔에 출력하기 위함
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # 로그 형식 지정
    level=logging.INFO # 정보 수준 이상의 로그만 출력
)
logger = logging.getLogger(__name__) # 로거 객체 생성

# 환경 변수 로드 (로컬 개발 환경용)
load_dotenv()

# Vercel에 배포할 때는 환경 변수에서 토큰을 가져옵니다
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Vercel 배포 URL (예: https://your-app.vercel.app/api/webhook)

# 사용자별 대화 기록을 저장할 딕셔너리
user_conversations = {}
# 사용자별 마지막 선언 시간 저장
last_declaration_time = {}
# 사용자별 캐릭터 정보 저장
user_characters = {}

# 캐릭터 관리 기능
class CharacterManager:
    """캐릭터 정보를 관리하는 클래스"""
    
    CHARACTER_DIR = 'characters'
    
    # 캐릭터 시트 템플릿 - 필수 항목 정의
    CHARACTER_TEMPLATE = {
        "세션_정보": {
            "플레이어_수": 1,
            "완성된_캐릭터_수": 0,
            "현재_캐릭터_인덱스": 0
        },
        "완성된_캐릭터들": [],  # 완성된 모든 캐릭터 정보를 저장할 배열
        "이름": None,
        "클래스": None,
        "레벨": 1,
        "경험치": 0,
        "가치관": None,
        "플레이어": None,  # 플레이어 정보 (user_id 또는 이름)
        "능력치": {
            "근력": None,
            "민첩성": None,
            "건강": None,
            "지능": None,
            "지혜": None,
            "매력": None
        },
        "수정치": {},  # 능력치에 따라 자동 계산됨
        "체력": {
            "최대": None,  # 클래스와 건강 수정치에 따라 자동 계산됨
            "현재": None,
            "체력주사위": None  # 클래스에 따라 자동 설정됨
        },
        "장갑클래스": None,  # 계산됨
        "기본공격보너스": None,  # 클래스에 따라 자동 설정됨
        "행동순서": None,  # 계산됨
        "기능": [],
        "언어": ["공용어"],  # 추가 언어는 지능 수정치에 따라 추가됨
        "행운점수": {
            "최대": None,  # 클래스에 따라 자동 설정됨
            "현재": None
        },
        "장비": {
            "착용가능갑옷": [],  # 클래스에 따라 자동 설정됨
            "소지품": ["간편한 옷", "모험 장비"],
            "무기": [],
            "갑옷": "없음",
            "소지금": {
                "동화": 0,
                "은화": None,  # 랜덤 생성됨 (4d6)
                "금화": 0
            }
        },
        "생성일": None,
        "마지막수정일": None
    }
    
    # 클래스별 기본 설정값
    CLASS_DEFAULTS = {
        "전사": {
            "체력주사위": "d10",
            "행운점수": 3,
            "기본공격보너스": 1,
            "행동순서_보너스": 1,
            "착용가능갑옷": ["가죽 갑옷", "사슬 갑옷", "사슬+흉판", "전신 판금"]
        },
        "도적": {
            "체력주사위": "d8",
            "행운점수": 5,
            "기본공격보너스": 0,
            "행동순서_보너스": 2,
            "착용가능갑옷": ["가죽 갑옷", "사슬 갑옷"]
        },
        "마법사": {
            "체력주사위": "d6",
            "행운점수": 3,
            "기본공격보너스": 0,
            "행동순서_보너스": 0,
            "착용가능갑옷": []
        }
    }
    
    # 다음에 물어볼 항목 순서
    CREATION_SEQUENCE = [
        "이름", "클래스", "가치관", "능력치", "기능"
    ]
    
    @classmethod
    def initialize(cls):
        """캐릭터 저장 디렉토리 생성"""
        os.makedirs(cls.CHARACTER_DIR, exist_ok=True)
        cls.load_all_characters()
    
    @classmethod
    def load_all_characters(cls):
        """모든 캐릭터 정보 로드"""
        global user_characters
        if not os.path.exists(cls.CHARACTER_DIR):
            return
            
        for filename in os.listdir(cls.CHARACTER_DIR):
            if filename.endswith('.json'):
                try:
                    user_id = int(filename.split('_')[1].split('.')[0])
                    character_data = cls.load_character(user_id)
                    if character_data:
                        user_characters[user_id] = character_data
                except (ValueError, IndexError):
                    continue
    
    @classmethod
    def get_character_file_path(cls, user_id):
        """사용자 ID에 해당하는 캐릭터 파일 경로 반환"""
        return os.path.join(cls.CHARACTER_DIR, f"character_{user_id}.json")
    
    @classmethod
    def save_character(cls, user_id, character_data):
        """캐릭터 정보 저장"""
        global user_characters
        user_characters[user_id] = character_data
        
        with open(cls.get_character_file_path(user_id), 'w', encoding='utf-8') as f:
            json.dump(character_data, f, ensure_ascii=False, indent=2)
        
        # 캐릭터 저장 후 자동으로 null 값 채우기
        return cls.fix_null_values_in_characters(user_id)
    
    @classmethod
    def load_character(cls, user_id):
        """캐릭터 정보 로드"""
        character_path = cls.get_character_file_path(user_id)
        if not os.path.exists(character_path):
            return None
            
        try:
            with open(character_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"캐릭터 파일 로드 오류: {character_path}")
            return None
    
    @classmethod
    def init_character_creation(cls, user_id):
        """캐릭터 생성 초기화"""
        # 현재 시간 기록
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 템플릿 복사
        character_data = deepcopy(cls.CHARACTER_TEMPLATE)
        character_data["생성일"] = now
        character_data["마지막수정일"] = now
        
        # 소지금 기본값 설정
        character_data["장비"]["소지금"]["은화"] = sum([random.randint(1, 6) for _ in range(4)])  # 4d6
        
        # 저장
        return cls.save_character(user_id, character_data)
    
    @classmethod
    def update_character_field(cls, user_id, field, value):
        """캐릭터 필드 업데이트"""
        character_data = cls.load_character(user_id)
        if not character_data:
            return None
        
        # 필드 업데이트
        if field == "능력치":
            # 능력치는 딕셔너리
            character_data["능력치"] = value
            # 능력치 수정치 계산
            character_data["수정치"] = cls.calculate_modifiers(value)
            # 파생 능력치 업데이트
            character_data = cls.update_derived_attributes(character_data)
        elif "." in field:
            # 중첩 필드 (예: "체력.최대")
            parts = field.split(".")
            target = character_data
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
        else:
            character_data[field] = value
            
            # 클래스가 설정된 경우 클래스 기본값 적용
            if field == "클래스" and value in cls.CLASS_DEFAULTS:
                cls_defaults = cls.CLASS_DEFAULTS[value]
                character_data["체력"]["체력주사위"] = cls_defaults["체력주사위"]
                character_data["행운점수"]["최대"] = cls_defaults["행운점수"]
                character_data["행운점수"]["현재"] = cls_defaults["행운점수"]
                character_data["기본공격보너스"] = cls_defaults["기본공격보너스"]
                character_data["장비"]["착용가능갑옷"] = cls_defaults["착용가능갑옷"]
        
        # 마지막 수정 시간 업데이트
        character_data["마지막수정일"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 저장
        return cls.save_character(user_id, character_data)
    
    @classmethod
    def calculate_modifiers(cls, attributes):
        """능력치 수정치 계산"""
        modifiers = {}
        for attr, value in attributes.items():
            value = int(value) if isinstance(value, str) else value
            if value is None:
                modifiers[attr] = None
            elif value <= 3:
                modifiers[attr] = -3
            elif value <= 5:
                modifiers[attr] = -2
            elif value <= 8:
                modifiers[attr] = -1
            elif value <= 12:
                modifiers[attr] = 0
            elif value <= 15:
                modifiers[attr] = 1
            elif value <= 17:
                modifiers[attr] = 2
            else:
                modifiers[attr] = 3
        return modifiers
    
    @classmethod
    def update_derived_attributes(cls, character_data):
        """파생 능력치 업데이트"""
        # 클래스와 능력치가 설정되어 있어야 함
        if not character_data["클래스"] or "건강" not in character_data["수정치"] or character_data["수정치"]["건강"] is None:
            return character_data
        
        # 체력 계산 (1레벨 기준: 체력 주사위 최댓값 + 건강 보너스)
        hit_dice = character_data["체력"]["체력주사위"]
        max_hp = {"d6": 6, "d8": 8, "d10": 10}.get(hit_dice, 8)
        max_hp += character_data["수정치"]["건강"]
        max_hp = max(max_hp, 1)  # 최소 1
        character_data["체력"]["최대"] = max_hp
        character_data["체력"]["현재"] = max_hp
        
        # 민첩성이 설정되어 있는 경우
        if "민첩성" in character_data["수정치"] and character_data["수정치"]["민첩성"] is not None:
            # AC 계산 (기본 10 + 민첩성 보너스)
            character_data["장갑클래스"] = 10 + character_data["수정치"]["민첩성"]
            
            # 행동 순서 계산
            cls_bonus = cls.CLASS_DEFAULTS[character_data["클래스"]]["행동순서_보너스"]
            character_data["행동순서"] = 1 + character_data["수정치"]["민첩성"] + cls_bonus
        
        # 지능이 설정되어 있는 경우, 추가 언어 처리
        if "지능" in character_data["수정치"] and character_data["수정치"]["지능"] is not None:
            int_bonus = character_data["수정치"]["지능"]
            languages = ["공용어"]
            if int_bonus > 0:
                languages.append(f"추가 언어 {int_bonus}개 선택 가능")
            character_data["언어"] = languages
        
        return character_data
    
    @classmethod
    def fix_null_values_in_characters(cls, user_id):
        """캐릭터 데이터의 null 값을 채웁니다."""
        character_data = cls.load_character(user_id)
        if not character_data:
            return None
        
        # 메인 캐릭터 데이터의 수정치 계산
        if "능력치" in character_data and all(character_data["능력치"].values()):
            character_data["수정치"] = cls.calculate_modifiers(character_data["능력치"])
        
        # 캐릭터 클래스 기본값 적용
        if character_data["클래스"] in cls.CLASS_DEFAULTS:
            cls_defaults = cls.CLASS_DEFAULTS[character_data["클래스"]]
            if not character_data["체력"]["체력주사위"]:
                character_data["체력"]["체력주사위"] = cls_defaults["체력주사위"]
            if not character_data["행운점수"]["최대"]:
                character_data["행운점수"]["최대"] = cls_defaults["행운점수"]
                character_data["행운점수"]["현재"] = cls_defaults["행운점수"]
            if not character_data["기본공격보너스"]:
                character_data["기본공격보너스"] = cls_defaults["기본공격보너스"]
            if not character_data["장비"]["착용가능갑옷"]:
                character_data["장비"]["착용가능갑옷"] = cls_defaults["착용가능갑옷"]
        
        # 파생 능력치 업데이트
        character_data = cls.update_derived_attributes(character_data)
        
        # 완성된 캐릭터들의 null 값 채우기
        if "완성된_캐릭터들" in character_data and character_data["완성된_캐릭터들"]:
            updated_characters = []
            for char in character_data["완성된_캐릭터들"]:
                # 수정치 계산
                if "능력치" in char and all(char["능력치"].values()) and (not char["수정치"] or not any(char["수정치"].values())):
                    char["수정치"] = cls.calculate_modifiers(char["능력치"])
                
                # 클래스 기본값 적용
                if char["클래스"] in cls.CLASS_DEFAULTS:
                    cls_defaults = cls.CLASS_DEFAULTS[char["클래스"]]
                    
                    # 체력 관련
                    if not char["체력"]["체력주사위"]:
                        char["체력"]["체력주사위"] = cls_defaults["체력주사위"]
                    
                    # 체력 계산
                    hit_dice = char["체력"]["체력주사위"]
                    max_hp = {"d6": 6, "d8": 8, "d10": 10}.get(hit_dice, 8)
                    health_mod = char["수정치"].get("건강", 0)
                    max_hp += health_mod
                    max_hp = max(max_hp, 1)  # 최소 1
                    char["체력"]["최대"] = max_hp
                    char["체력"]["현재"] = max_hp
                    
                    # 행운점수
                    if not char["행운점수"]["최대"]:
                        char["행운점수"]["최대"] = cls_defaults["행운점수"]
                        char["행운점수"]["현재"] = cls_defaults["행운점수"]
                    
                    # 기본공격보너스
                    if not char["기본공격보너스"]:
                        char["기본공격보너스"] = cls_defaults["기본공격보너스"]
                    
                    # 착용가능갑옷
                    if not char["장비"]["착용가능갑옷"]:
                        char["장비"]["착용가능갑옷"] = cls_defaults["착용가능갑옷"]
                    
                    # AC 계산
                    dex_mod = char["수정치"].get("민첩성", 0)
                    char["장갑클래스"] = 10 + dex_mod
                    
                    # 행동순서 계산
                    cls_bonus = cls_defaults["행동순서_보너스"]
                    char["행동순서"] = 1 + dex_mod + cls_bonus
                
                updated_characters.append(char)
            
            # 업데이트된 캐릭터 목록 저장
            character_data["완성된_캐릭터들"] = updated_characters
        
        # 저장
        return cls.save_character(user_id, character_data)
    
    @classmethod
    def is_character_creation_complete(cls, character_data):
        """캐릭터 생성이 완료되었는지 확인"""
        if not character_data:
            return False
        
        # 필수 필드 확인
        if not character_data["이름"] or not character_data["클래스"] or not character_data["가치관"]:
            return False
        
        # 능력치 확인 (모든 능력치가 설정되어 있어야 함)
        abilities = character_data["능력치"]
        if (not abilities["근력"] or not abilities["민첩성"] or not abilities["건강"] or 
            not abilities["지능"] or not abilities["지혜"] or not abilities["매력"]):
            return False
        
        # 이름, 클래스, 가치관, 능력치가 모두 설정되어 있으면 완료
        return True
    
    @classmethod
    def get_next_empty_field(cls, character_data):
        """다음에 채울 필요가 있는 빈 필드를 반환"""
        for field in cls.CREATION_SEQUENCE:
            if field == "능력치":
                # 능력치는 하위 필드를 검사
                if not character_data["능력치"]["근력"] or not character_data["능력치"]["민첩성"] or \
                   not character_data["능력치"]["건강"] or not character_data["능력치"]["지능"] or \
                   not character_data["능력치"]["지혜"] or not character_data["능력치"]["매력"]:
                    return field
            elif not character_data[field]:
                return field
        return None  # 모든 필수 필드가 채워짐
    
    @classmethod
    def parse_attributes_input(cls, input_text):
        """능력치 입력 파싱"""
        attributes = {}
        for attr_str in input_text.split(','):
            try:
                key, value = attr_str.strip().split(':', 1)
                key = key.strip()
                value = int(value.strip())
                attributes[key] = value
            except (ValueError, AttributeError):
                continue
        return attributes
    
    @classmethod
    def format_character_sheet(cls, character_data):
        """캐릭터 정보를 읽기 좋게 포맷팅"""
        if not character_data:
            return "캐릭터 정보가 없습니다."
        
        # 완성된 캐릭터들이 있을 경우 목록 표시
        if "완성된_캐릭터들" in character_data and character_data["완성된_캐릭터들"]:
            completed_characters = character_data["완성된_캐릭터들"]
            player_count = character_data["세션_정보"]["플레이어_수"]
            completed_count = character_data["세션_정보"]["완성된_캐릭터_수"]
            current_index = character_data["세션_정보"]["현재_캐릭터_인덱스"]
            
            # 헤더 정보
            sheet = [
                f"📋 캐릭터 목록 (총 {player_count}명 중 {completed_count}명 완성)",
                ""
            ]
            
            # 각 캐릭터 정보 표시
            for i, char in enumerate(completed_characters, 1):
                player_info = f" (플레이어: {char.get('플레이어', '미지정')})"
                sheet.append(f"🧙 캐릭터 {i+1}: {char['이름']} ({char['클래스']}){player_info}")
                sheet.append(f"가치관: {char['가치관']}")
                
                # 능력치
                sheet.append("능력치:")
                for attr, value in char["능력치"].items():
                    mod = char["수정치"].get(attr, 0) if "수정치" in char else 0
                    mod_str = f"+{mod}" if mod > 0 else str(mod) if mod < 0 else ""
                    sheet.append(f"  {attr}: {value} {mod_str}")
                
                # 기능
                if char["기능"]:
                    sheet.append(f"기능: {', '.join(char['기능'])}")
                
                # 무기 및 갑옷
                weapons = char["장비"]["무기"] if "장비" in char and "무기" in char["장비"] else []
                armor = char["장비"].get("갑옷", "없음") if "장비" in char else "없음"
                
                sheet.append(f"무기: {', '.join(weapons) if weapons else '없음'}")
                sheet.append(f"갑옷: {armor}")
                sheet.append("")
            
            # 현재 작업 중인 캐릭터가 있으면 추가
            if completed_count < player_count:
                sheet.append(f"🚧 현재 작업 중인 캐릭터 ({current_index+1}번째):")
                sheet.append(f"이름: {character_data.get('이름', '미설정')}")
                sheet.append(f"클래스: {character_data.get('클래스', '미설정')}")
                sheet.append(f"가치관: {character_data.get('가치관', '미설정')}")
                sheet.append(f"플레이어: {character_data.get('플레이어', '미지정')}")
                sheet.append("")
                
                # 다음에 설정할 항목 안내
                next_field = cls.get_next_empty_field(character_data)
                if next_field:
                    sheet.append(f"⚠️ 다음 설정할 항목: '{next_field}'")
            
            return "\n".join(sheet)
        
        # 기본 정보
        sheet = [
            f"📝 캐릭터 시트",
            f"이름: {character_data.get('이름', '이름 없음')}",
            f"클래스: {character_data.get('클래스', '없음')} {character_data.get('레벨', 1)}레벨",
            f"가치관: {character_data.get('가치관', '중립')}",
            f"플레이어: {character_data.get('플레이어', '미지정')}",
            f"경험치: {character_data.get('경험치', 0)}",
            ""
        ]
        
        # 능력치 및 수정치
        sheet.append("🎯 능력치:")
        attributes = character_data.get('능력치', {})
        modifiers = character_data.get('수정치', {})
        
        for attr in ["근력", "민첩성", "건강", "지능", "지혜", "매력"]:
            value = attributes.get(attr, '미설정')
            mod = modifiers.get(attr)
            mod_str = f"+{mod}" if mod and mod > 0 else str(mod) if mod else ''
            sheet.append(f"  {attr}: {value} {f'({mod_str})' if mod else ''}")
        
        sheet.append("")
        
        # 전투 관련 수치
        hp = character_data.get('체력', {})
        sheet.append("⚔️ 전투 능력:")
        sheet.append(f"  HP: {hp.get('현재', '미설정')}/{hp.get('최대', '미설정')} ({hp.get('체력주사위', '미설정')})")
        sheet.append(f"  AC(장갑): {character_data.get('장갑클래스', '미설정')}")
        sheet.append(f"  기본공격보너스: +{character_data.get('기본공격보너스', '미설정')}")
        sheet.append(f"  행동순서: +{character_data.get('행동순서', '미설정')}")
        sheet.append(f"  행운점수: {character_data.get('행운점수', {}).get('현재', '미설정')}/{character_data.get('행운점수', {}).get('최대', '미설정')}")
        sheet.append("")
        
        # 기능
        skills = character_data.get('기능', [])
        sheet.append("🧠 기능:")
        if skills:
            for skill in skills:
                sheet.append(f"  - {skill}")
        else:
            sheet.append("  (없음)")
        sheet.append("")
        
        # 언어
        languages = character_data.get('언어', ["공용어"])
        sheet.append("🗣️ 언어:")
        for lang in languages:
            sheet.append(f"  - {lang}")
        sheet.append("")
        
        # 장비
        equipment = character_data.get('장비', {})
        sheet.append("🎒 장비:")
        
        # 갑옷
        sheet.append(f"  갑옷: {equipment.get('갑옷', '없음')}")
        
        # 무기
        weapons = equipment.get('무기', [])
        if weapons:
            sheet.append("  무기:")
            for weapon in weapons:
                sheet.append(f"    - {weapon}")
        else:
            sheet.append("  무기: (없음)")
        
        # 소지품
        items = equipment.get('소지품', [])
        if items:
            sheet.append("  소지품:")
            for item in items:
                sheet.append(f"    - {item}")
        
        # 소지금
        money = equipment.get('소지금', {})
        sheet.append(f"  소지금: 금화 {money.get('금화', 0)}냥, 은화 {money.get('은화', 0)}냥, 동화 {money.get('동화', 0)}냥")
        
        # 생성 및 수정 정보
        sheet.append("")
        sheet.append(f"캐릭터 생성일: {character_data.get('생성일', '-')}")
        sheet.append(f"마지막 수정일: {character_data.get('마지막수정일', '-')}")
        
        # 생성 상태 표시
        if not cls.is_character_creation_complete(character_data):
            next_field = cls.get_next_empty_field(character_data)
            sheet.append("")
            sheet.append(f"⚠️ 캐릭터 생성 진행 중: '{next_field}' 항목을 설정해주세요.")
        
        return "\n".join(sheet)

    @classmethod
    def extract_info_using_llm(cls, text, user_id):
        """LLM을 활용하여 대화에서 캐릭터 정보를 추출합니다."""
        try:
            # 현재 캐릭터 데이터 로드
            character_data = cls.load_character(user_id)
            if not character_data:
                # 캐릭터가 없으면 새로 생성
                character_data = cls.init_character_creation(user_id)
            
            # 플레이어 수 및 현재 캐릭터 인덱스 확인
            player_count = 1
            current_index = 0
            if "세션_정보" in character_data:
                player_count = character_data["세션_정보"]["플레이어_수"]
                current_index = character_data["세션_정보"]["현재_캐릭터_인덱스"]
            
            # LLM에 보낼 프롬프트 작성
            character_sheet = cls.format_character_sheet(character_data)
            
            prompt = """
# 지시사항
당신은 TRPG 캐릭터 시트 관리를 돕는 AI입니다. 플레이어의 대화에서 캐릭터 정보를 추출해 주세요.
이 세션에는 여러 플레이어가 있을 수 있으며, 현재는 {} 중 {}번째 캐릭터의 정보를 생성하고 있습니다.

## 현재 캐릭터 시트
""".format(player_count, current_index + 1) + character_sheet + """

## 플레이어 대화
\"""" + text + """\"

## 작업
1. 위 대화에서 캐릭터 시트에 추가할 수 있는 정보가 있는지 분석하세요.
2. 다음 카테고리에 맞는 정보만 추출하세요: 이름, 클래스, 레벨, 가치관, 능력치(근력/민첩성/건강/지능/지혜/매력), 기능, 무기, 갑옷, 소지품
3. 특히 자연어로 표현된 능력치를 식별하세요. 예: "힘은 15야", "민첩이 18이고", "지능 능력치는 12입니다" 등
4. 정보가 있으면 JSON 형식으로 반환하세요. 정보가 없으면 빈 JSON을 반환하세요.
5. 플레이어 수가 언급된 경우 이를 포함하세요. 예: "플레이어는 3명이야", "3명의 캐릭터를 만들자" 등
6. 추측하지 말고 명확하게 언급된 정보만 추출하세요.
7. "랜덤 캐릭터" 또는 "무작위 캐릭터" 생성 요청이 있으면 다음과 같이 반환하세요:

```json
{
  "랜덤_캐릭터": true
}
```

## 반환 형식 예시
```json
{
  "플레이어_수": 3,
  "이름": "아서스",
  "클래스": "전사",
  "가치관": "질서",
  "능력치": {
    "근력": 16,
    "민첩성": 12,
    "건강": 14,
    "지능": 10,
    "지혜": 8,
    "매력": 13
  },
  "기능": ["운동", "위협"],
  "장비": {
    "무기": ["롱소드", "단검"],
    "갑옷": "판금갑옷",
    "소지품": ["배낭", "양초"]
  }
}
```

만약 추출할 정보가 없다면: 
```json
{}
```

만약 "다른 캐릭터를 랜덤으로 만들어줘" 같은 요청이 있다면 다음 캐릭터로 넘어간다는 의미입니다:
```json
{
  "완료_요청": true
}
```

## 응답:
"""
            
            # LLM 모델 호출
            model = genai.GenerativeModel(GENERATION_MODEL)
            response = model.generate_content(prompt)
            
            # JSON 부분 추출
            response_text = response.text
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                extracted_info = json.loads(json_str)
                
                # 빈 JSON이면 변경사항 없음
                if not extracted_info:
                    return []
                
                # 랜덤 캐릭터 생성 요청 확인
                if "랜덤_캐릭터" in extracted_info and extracted_info["랜덤_캐릭터"]:
                    # 랜덤 캐릭터 생성
                    cls.generate_random_character(user_id)
                    return ["랜덤 캐릭터 생성"]
                
                # 완료 요청이 있으면 현재 캐릭터 완료 처리
                if "완료_요청" in extracted_info and extracted_info["완료_요청"]:
                    # 현재 캐릭터가 완성되었는지 확인
                    if cls.is_character_creation_complete(character_data):
                        # 완료된 캐릭터 수 증가 및 다음 캐릭터 준비
                        cls.increment_completed_character(user_id)
                        return ["캐릭터 생성 완료"]
                    else:
                        # 완성되지 않았으면 무시
                        return []
                
                # 플레이어 수 설정 확인
                if "플레이어_수" in extracted_info and 1 <= extracted_info["플레이어_수"] <= 10:
                    cls.set_player_count(user_id, extracted_info["플레이어_수"])
                    player_count = extracted_info["플레이어_수"]
                
                # 업데이트된 필드 추적
                updated_fields = []
                
                # 기본 필드 업데이트
                basic_fields = ["이름", "클래스", "레벨", "가치관"]
                for field in basic_fields:
                    if field in extracted_info and extracted_info[field] and not character_data[field]:
                        cls.update_character_field(user_id, field, extracted_info[field])
                        updated_fields.append(field)
                
                # 능력치 업데이트
                if "능력치" in extracted_info and extracted_info["능력치"]:
                    # 현재 능력치 가져오기
                    current_abilities = character_data["능력치"]
                    has_updates = False
                    
                    # 추출된 능력치로 업데이트
                    for ability, value in extracted_info["능력치"].items():
                        if not current_abilities[ability]:
                            current_abilities[ability] = value
                            has_updates = True
                    
                    # 업데이트된 능력치가 있으면 저장
                    if has_updates:
                        cls.update_character_field(user_id, "능력치", current_abilities)
                        updated_fields.append("능력치")
                
                # 기능 업데이트
                if "기능" in extracted_info and extracted_info["기능"] and not character_data["기능"]:
                    cls.update_character_field(user_id, "기능", extracted_info["기능"])
                    updated_fields.append("기능")
                
                # 장비 업데이트
                if "장비" in extracted_info:
                    equipment = extracted_info["장비"]
                    
                    # 무기 업데이트
                    if "무기" in equipment and equipment["무기"] and not character_data["장비"]["무기"]:
                        character_data["장비"]["무기"] = equipment["무기"]
                        updated_fields.append("무기")
                    
                    # 갑옷 업데이트
                    if "갑옷" in equipment and equipment["갑옷"] and character_data["장비"]["갑옷"] == "없음":
                        character_data["장비"]["갑옷"] = equipment["갑옷"]
                        updated_fields.append("갑옷")
                    
                    # 소지품 업데이트
                    if "소지품" in equipment and equipment["소지품"]:
                        # 기존 소지품에 없는 아이템만 추가
                        new_items = [item for item in equipment["소지품"] 
                                    if item not in character_data["장비"]["소지품"]]
                        if new_items:
                            character_data["장비"]["소지품"].extend(new_items)
                            updated_fields.append("소지품")
                    
                    # 장비가 업데이트되었으면 저장
                    if "무기" in updated_fields or "갑옷" in updated_fields or "소지품" in updated_fields:
                        cls.save_character(user_id, character_data)
                
                return updated_fields
                
            else:
                logger.warning("LLM 응답에서 JSON을 찾을 수 없습니다.")
                return []
                
        except Exception as e:
            logger.error(f"LLM을 통한 캐릭터 정보 추출 중 오류 발생: {e}")
            logger.error(traceback.format_exc())
            return []

    @classmethod
    def is_player_count_set(cls, user_id):
        """플레이어 수가 설정되었는지 확인"""
        character_data = cls.load_character(user_id)
        return character_data and "세션_정보" in character_data and character_data["세션_정보"]["플레이어_수"] > 0

    @classmethod
    def set_player_count(cls, user_id, count):
        """플레이어 수 설정"""
        character_data = cls.load_character(user_id)
        if not character_data:
            character_data = cls.init_character_creation(user_id)
        
        # 이미 세션_정보가 없다면 추가
        if "세션_정보" not in character_data:
            character_data["세션_정보"] = {
                "플레이어_수": 1,
                "완성된_캐릭터_수": 0,
                "현재_캐릭터_인덱스": 0
            }
        
        # 플레이어 수 설정
        character_data["세션_정보"]["플레이어_수"] = int(count)
        return cls.save_character(user_id, character_data)

    @classmethod
    def is_character_creation_complete_for_all(cls, user_id):
        """모든 플레이어의 캐릭터 생성이 완료되었는지 확인"""
        character_data = cls.load_character(user_id)
        if not character_data or "세션_정보" not in character_data:
            return False
        
        return character_data["세션_정보"]["완성된_캐릭터_수"] >= character_data["세션_정보"]["플레이어_수"]

    @classmethod
    def increment_completed_character(cls, user_id):
        """완성된 캐릭터 수 증가"""
        character_data = cls.load_character(user_id)
        if not character_data or "세션_정보" not in character_data:
            return False
        
        # 완성된 캐릭터 정보 저장
        if cls.is_character_creation_complete(character_data):
            # 현재 캐릭터의 복사본 생성
            current_character = {
                "이름": character_data["이름"],
                "클래스": character_data["클래스"],
                "레벨": character_data["레벨"],
                "경험치": character_data["경험치"],
                "가치관": character_data["가치관"],
                "플레이어": character_data.get("플레이어", "미지정"),  # 플레이어 정보 포함
                "능력치": deepcopy(character_data["능력치"]),
                "수정치": deepcopy(character_data["수정치"]),
                "체력": deepcopy(character_data["체력"]),
                "장갑클래스": character_data["장갑클래스"],
                "기본공격보너스": character_data["기본공격보너스"],
                "행동순서": character_data["행동순서"],
                "기능": deepcopy(character_data["기능"]),
                "언어": deepcopy(character_data["언어"]),
                "행운점수": deepcopy(character_data["행운점수"]),
                "장비": deepcopy(character_data["장비"])
            }
            
            # 완성된 캐릭터 목록이 없으면 생성
            if "완성된_캐릭터들" not in character_data:
                character_data["완성된_캐릭터들"] = []
                
            # 목록에 현재 캐릭터 추가
            character_data["완성된_캐릭터들"].append(current_character)
        
        # 완성된 캐릭터 수 증가
        character_data["세션_정보"]["완성된_캐릭터_수"] += 1
        
        # 현재 캐릭터 정보 초기화 (다음 캐릭터 준비)
        if character_data["세션_정보"]["완성된_캐릭터_수"] < character_data["세션_정보"]["플레이어_수"]:
            character_data["이름"] = None
            character_data["클래스"] = None
            character_data["가치관"] = None
            character_data["능력치"] = {
                "근력": None,
                "민첩성": None,
                "건강": None,
                "지능": None, 
                "지혜": None,
                "매력": None
            }
            character_data["기능"] = []
            character_data["세션_정보"]["현재_캐릭터_인덱스"] += 1
        
        return cls.save_character(user_id, character_data)

    @classmethod
    def get_current_character_index(cls, user_id):
        """현재 생성 중인 캐릭터 인덱스 조회"""
        character_data = cls.load_character(user_id)
        if not character_data or "세션_정보" not in character_data:
            return 0
        
        return character_data["세션_정보"]["현재_캐릭터_인덱스"]

    @classmethod
    def get_player_count_and_completed(cls, user_id):
        """플레이어 수와 완료된 캐릭터 수 반환"""
        character_data = cls.load_character(user_id)
        if not character_data or "세션_정보" not in character_data:
            return 1, 0
        
        return character_data["세션_정보"]["플레이어_수"], character_data["세션_정보"]["완성된_캐릭터_수"]

    @classmethod
    def generate_random_character(cls, user_id, assigned_player=None):
        """랜덤 캐릭터 생성"""
        character_data = cls.load_character(user_id)
        if not character_data:
            character_data = cls.init_character_creation(user_id)
        
        # 플레이어 정보 설정
        if assigned_player:
            character_data["플레이어"] = assigned_player
        
        # 무작위 이름 생성
        names = ["아서", "리안", "엘더린", "소린", "타니아", "밀라", "카이", "제이드", 
                 "로칸", "테오", "아이리스", "샤이나", "덱스터", "케일럽", "엠버", "페이"]
        surnames = ["스톰블레이드", "라이트우드", "다크섀도우", "윈드워커", "스톤하트", 
                    "문글로우", "선워치", "스타가저", "블레이드", "실버", "골드", "아이언"]
        
        # 무작위 클래스
        classes = ["전사", "도적", "마법사"]
        
        # 무작위 가치관
        alignments = ["질서", "중립", "혼돈"]
        
        # 능력치 랜덤 생성 (4d6 중 최저값 제외 방식)
        abilities = {}
        ability_names = ["근력", "민첩성", "건강", "지능", "지혜", "매력"]
        for ability in ability_names:
            # 4d6 굴리고 가장 낮은 값 제외
            rolls = [random.randint(1, 6) for _ in range(4)]
            rolls.sort()
            abilities[ability] = sum(rolls[1:])  # 최저값 제외하고 합산
        
        # 무작위 기능
        skills_list = ["운동", "곡예", "은신", "손재주", "아케인", "역사", "조사", "자연", 
                      "종교", "동물조련", "통찰", "의학", "지각", "생존", "설득", "속임수", "위협"]
        # 2~3개의 무작위 기능 선택
        num_skills = random.randint(2, 3)
        skills = random.sample(skills_list, num_skills)
        
        # 캐릭터 정보 업데이트
        character_data["이름"] = f"{random.choice(names)} {random.choice(surnames)}"
        character_data["클래스"] = random.choice(classes)
        character_data["가치관"] = random.choice(alignments)
        character_data["능력치"] = abilities
        character_data["기능"] = skills
        
        # 클래스에 따른 무기 배정
        if character_data["클래스"] == "전사":
            weapons = random.choice([["롱소드", "방패"], ["배틀액스"], ["그레이트소드"], ["할버드"]])
            armor = random.choice(["사슬 갑옷", "판금 갑옷"])
        elif character_data["클래스"] == "도적":
            weapons = random.choice([["단검", "단검"], ["숏소드", "단검"], ["라이트 크로스보우", "단검"]])
            armor = "가죽 갑옷"
        else:  # 마법사
            weapons = random.choice([["쿼터스태프"], ["단검"], ["라이트 크로스보우"]])
            armor = "없음"
        
        character_data["장비"]["무기"] = weapons
        character_data["장비"]["갑옷"] = armor
        
        # 파생 능력치 및 세부 정보 업데이트
        cls.update_character_field(user_id, "능력치", abilities)
        
        # 캐릭터 완료 상태로 설정
        if cls.is_character_creation_complete(character_data):
            # 현재 캐릭터의 복사본 생성
            current_character = {
                "이름": character_data["이름"],
                "클래스": character_data["클래스"],
                "레벨": character_data["레벨"],
                "경험치": character_data["경험치"],
                "가치관": character_data["가치관"],
                "플레이어": character_data.get("플레이어", "미지정"),  # 플레이어 정보 포함
                "능력치": deepcopy(character_data["능력치"]),
                "수정치": deepcopy(character_data["수정치"]),
                "체력": deepcopy(character_data["체력"]),
                "장갑클래스": character_data["장갑클래스"],
                "기본공격보너스": character_data["기본공격보너스"],
                "행동순서": character_data["행동순서"],
                "기능": deepcopy(character_data["기능"]),
                "언어": deepcopy(character_data["언어"]),
                "행운점수": deepcopy(character_data["행운점수"]),
                "장비": deepcopy(character_data["장비"])
            }
            
            # 완성된 캐릭터 목록이 없으면 생성
            if "완성된_캐릭터들" not in character_data:
                character_data["완성된_캐릭터들"] = []
                
            # 목록에 현재 캐릭터 추가
            character_data["완성된_캐릭터들"].append(current_character)
        
        # 캐릭터 데이터 저장
        cls.save_character(user_id, character_data)
        
        return character_data

# 초기화 함수
def initialize_bot():
    """봇 초기화 작업 수행"""
    # 캐릭터 관리자 초기화
    CharacterManager.initialize()

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
/session - 현재 세션 확인 및 변경하기
/history - 세션 이력 보기
/roll - 주사위 굴리기
"""

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
            ability_scores = []
            for _ in range(6):  # 6개 능력치
                # 4d6 굴리고 가장 낮은 주사위 제외
                rolls = [random.randint(1, 6) for _ in range(4)]
                total = sum(sorted(rolls)[1:])  # 가장 낮은 주사위 제외하고 합산
                ability_scores.append(total)
            
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
    
    # 세션 로그에 사용자 메시지 기록
    session_manager.log_session(
        user_id, 
        session_type, 
        f"사용자 메시지: {text[:]}" # + ("..." if len(text) > 50 else "")
    )
    
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
                    # 모든 캐릭터 생성 완료
                    await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다. 이제 '/session' 명령어로 원하는 세션으로 변경할 수 있습니다.")
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
                        # 모든 캐릭터 생성 완료
                        if 'generating_all_random' in context.user_data:
                            del context.user_data['generating_all_random']
                        
                        await message.reply_text(f"플레이어 정보를 '{player_name}'(으)로 업데이트했습니다!\n\n{character_sheet}\n\n축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다. 이제 '/session' 명령어로 원하는 세션으로 변경할 수 있습니다.")
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
                # 모든 캐릭터 생성 완료
                await message.reply_text(f"랜덤 캐릭터를 생성했습니다!\n\n{character_sheet}\n\n축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다. 이제 '/session' 명령어로 원하는 세션으로 변경할 수 있습니다.")
                return
        
        # 모든 플레이어의 캐릭터 생성 완료 확인
        if CharacterManager.is_character_creation_complete_for_all(user_id):
            player_count, _ = CharacterManager.get_player_count_and_completed(user_id)
            final_answer = f"축하합니다! 모든 캐릭터({player_count}명)의 생성이 완료되었습니다. 이제 '/session' 명령어로 원하는 세션으로 변경할 수 있습니다."
            await message.reply_text(final_answer)
            return
            
    # 캐릭터 정보를 RAG 컨텍스트에 추가
    character_data = user_characters.get(user_id) or CharacterManager.load_character(user_id)
    character_context = ""
    if character_data:
        character_context = f"플레이어 캐릭터 정보:\n{CharacterManager.format_character_sheet(character_data)}\n\n"
    
    # rag 질문 응답 시작
    # 1. 유사성 검색
    relevant_chunks = find_similar_chunks(text, match_count=3, match_threshold=0.5) # 상위 3개 청크 검색

    # 2. 답변 생성 (캐릭터 정보 포함)
    final_answer = generate_answer_with_rag(text, relevant_chunks, session_type, character_context)
    
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
    
    # 봇의 응답도 세션 로그에 기록
    session_manager.log_session(
        user_id, 
        session_type, 
        f"마스터 응답: {final_answer}"
    )
    
    # 봇의 응답도 대화 기록에 저장
    user_conversations[user_id].append(f"마스터: {final_answer}")

    # 메시지에 대한 응답
    await message.reply_text(f"[마스터]\n\n{final_answer}")

# 텔레그램 봇 애플리케이션 생성 함수
def create_application():
    """봇 애플리케이션을 생성하고 핸들러를 등록하는 함수입니다."""
    # 초기화
    initialize_bot()
    
    # Application 객체 생성 (봇 토큰 사용)
    application = Application.builder().token(BOT_TOKEN).build()

    # 명령어 핸들러 등록 (영문 명령어 사용)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("declare", declare))  # 선언
    application.add_handler(CommandHandler("character", character))  # 캐릭터
    application.add_handler(CommandHandler("session", session))  # 세션
    application.add_handler(CommandHandler("hist", show_session_history))  # 세션이력
    application.add_handler(CommandHandler("roll", roll_dice_command))  # 주사위 굴리기
    
    # 인라인 버튼 콜백 핸들러 등록
    application.add_handler(CallbackQueryHandler(button_callback))

    # 일반 텍스트 메시지 핸들러 등록
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application

# 전역 애플리케이션 인스턴스 생성
application = create_application()

# 메인 함수: 전통적인 방식으로 봇 실행
def main() -> None:
    """봇을 시작하고 실행하는 메인 함수입니다."""
    # 폴링 모드로 실행 (로컬 개발용)
    logger.info("봇을 폴링 모드로 시작합니다...")
    application.run_polling()

# 파이썬 스크립트가 직접 실행될 때 main 함수 호출
if __name__ == '__main__':
    main()
else:
    # Vercel Functions에서 실행될 때 로그
    logger.info("서버리스 모드로 실행됩니다.")