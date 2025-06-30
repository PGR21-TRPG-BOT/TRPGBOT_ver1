# -*- coding: utf-8 -*-
import os
import json
import logging
import traceback
import re
import random
from datetime import datetime
from copy import deepcopy
import google.generativeai as genai
from config import (
    CHARACTER_DIR, CHARACTER_TEMPLATE, CLASS_DEFAULTS, 
    CREATION_SEQUENCE, user_characters
)
from random_character_generator import RandomCharacterGenerator
from trpgbot_ragmd_sentencetr import GENERATION_MODEL

logger = logging.getLogger(__name__)

class CharacterManager:
    """캐릭터 정보를 관리하는 클래스"""
    
    @classmethod
    def initialize(cls):
        """캐릭터 저장 디렉토리 생성"""
        os.makedirs(CHARACTER_DIR, exist_ok=True)
        cls.load_all_characters()
    
    @classmethod
    def load_all_characters(cls):
        """모든 캐릭터 정보 로드"""
        global user_characters
        if not os.path.exists(CHARACTER_DIR):
            return
            
        for filename in os.listdir(CHARACTER_DIR):
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
        return os.path.join(CHARACTER_DIR, f"character_{user_id}.json")
    
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
        character_data = deepcopy(CHARACTER_TEMPLATE)
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
            if field == "클래스" and value in CLASS_DEFAULTS:
                cls_defaults = CLASS_DEFAULTS[value]
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
            cls_bonus = CLASS_DEFAULTS[character_data["클래스"]]["행동순서_보너스"]
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
        if character_data["클래스"] in CLASS_DEFAULTS:
            cls_defaults = CLASS_DEFAULTS[character_data["클래스"]]
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
                if char["클래스"] in CLASS_DEFAULTS:
                    cls_defaults = CLASS_DEFAULTS[char["클래스"]]
                    
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
        for field in CREATION_SEQUENCE:
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
                sheet.append(f"🧙 캐릭터 {i}: {char['이름']} ({char['클래스']}){player_info}")
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
        """랜덤 캐릭터 생성 (RandomCharacterGenerator 사용)"""
        # 현재 캐릭터 데이터 로드
        character_data = cls.load_character(user_id)
        if not character_data:
            character_data = cls.init_character_creation(user_id)
        
        # RandomCharacterGenerator를 사용하여 랜덤 캐릭터 생성
        random_char = RandomCharacterGenerator.create_full_random_character(assigned_player)
        
        # 세션 정보 유지
        if "세션_정보" in character_data:
            random_char["세션_정보"] = character_data["세션_정보"]
        
        # 완성된 캐릭터들 목록 유지
        if "완성된_캐릭터들" in character_data:
            random_char["완성된_캐릭터들"] = character_data["완성된_캐릭터들"]
        
        # 캐릭터 데이터 저장
        cls.save_character(user_id, random_char)
        
        return random_char 