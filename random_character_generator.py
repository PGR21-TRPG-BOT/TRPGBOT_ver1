# -*- coding: utf-8 -*-
import random
from copy import deepcopy
from datetime import datetime
from config import CLASS_DEFAULTS

class RandomCharacterGenerator:
    """랜덤 캐릭터 생성을 담당하는 클래스"""
    
    # 랜덤 이름 목록
    FIRST_NAMES = ["아서", "리안", "엘더린", "소린", "타니아", "밀라", "카이", "제이드", 
                   "로칸", "테오", "아이리스", "샤이나", "덱스터", "케일럽", "엠버", "페이"]
    
    LAST_NAMES = ["스톰블레이드", "라이트우드", "다크섀도우", "윈드워커", "스톤하트", 
                  "문글로우", "선워치", "스타가저", "블레이드", "실버", "골드", "아이언"]
    
    # 클래스 목록
    CLASSES = ["전사", "도적", "마법사"]
    
    # 가치관 목록
    ALIGNMENTS = ["질서", "중립", "혼돈"]
    
    # 기능 목록
    SKILLS = ["운동", "곡예", "은신", "손재주", "아케인", "역사", "조사", "자연", 
              "종교", "동물조련", "통찰", "의학", "지각", "생존", "설득", "속임수", "위협"]
    
    @classmethod
    def generate_random_name(cls):
        """랜덤 이름 생성"""
        first_name = random.choice(cls.FIRST_NAMES)
        last_name = random.choice(cls.LAST_NAMES)
        return f"{first_name} {last_name}"
    
    @classmethod
    def generate_random_class(cls):
        """랜덤 클래스 선택"""
        return random.choice(cls.CLASSES)
    
    @classmethod
    def generate_random_alignment(cls):
        """랜덤 가치관 선택"""
        return random.choice(cls.ALIGNMENTS)
    
    @classmethod
    def generate_random_abilities(cls):
        """랜덤 능력치 생성 (4d6 중 최저값 제외 방식)"""
        abilities = {}
        ability_names = ["근력", "민첩성", "건강", "지능", "지혜", "매력"]
        
        for ability in ability_names:
            # 4d6 굴리고 가장 낮은 값 제외
            rolls = [random.randint(1, 6) for _ in range(4)]
            rolls.sort()
            abilities[ability] = sum(rolls[1:])  # 최저값 제외하고 합산
        
        return abilities
    
    @classmethod
    def generate_random_skills(cls, num_skills=None):
        """랜덤 기능 선택"""
        if num_skills is None:
            num_skills = random.randint(2, 3)  # 2~3개의 기능
        
        return random.sample(cls.SKILLS, min(num_skills, len(cls.SKILLS)))
    
    @classmethod
    def generate_class_equipment(cls, character_class):
        """클래스에 따른 랜덤 장비 생성"""
        if character_class == "전사":
            weapons = random.choice([
                ["롱소드", "방패"], 
                ["배틀액스"], 
                ["그레이트소드"], 
                ["할버드"]
            ])
            armor = random.choice(["사슬 갑옷", "판금 갑옷"])
        elif character_class == "도적":
            weapons = random.choice([
                ["단검", "단검"], 
                ["숏소드", "단검"], 
                ["라이트 크로스보우", "단검"]
            ])
            armor = "가죽 갑옷"
        else:  # 마법사
            weapons = random.choice([
                ["쿼터스태프"], 
                ["단검"], 
                ["라이트 크로스보우"]
            ])
            armor = "없음"
        
        return weapons, armor
    
    @classmethod
    def generate_random_money(cls):
        """랜덤 소지금 생성"""
        return {
            "동화": 0,
            "은화": sum([random.randint(1, 6) for _ in range(4)]),  # 4d6
            "금화": 0
        }
    
    @classmethod
    def create_full_random_character(cls, assigned_player=None):
        """완전한 랜덤 캐릭터 생성"""
        # 기본 정보 생성
        name = cls.generate_random_name()
        character_class = cls.generate_random_class()
        alignment = cls.generate_random_alignment()
        abilities = cls.generate_random_abilities()
        skills = cls.generate_random_skills()
        weapons, armor = cls.generate_class_equipment(character_class)
        money = cls.generate_random_money()
        
        # 능력치 수정치 계산
        modifiers = cls.calculate_modifiers(abilities)
        
        # 파생 능력치 계산
        derived_stats = cls.calculate_derived_stats(character_class, modifiers)
        
        # 현재 시간
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 캐릭터 데이터 구성
        character_data = {
            "세션_정보": {
                "플레이어_수": 1,
                "완성된_캐릭터_수": 0,
                "현재_캐릭터_인덱스": 0
            },
            "완성된_캐릭터들": [],
            "이름": name,
            "클래스": character_class,
            "레벨": 1,
            "경험치": 0,
            "가치관": alignment,
            "플레이어": assigned_player or "미지정",
            "능력치": abilities,
            "수정치": modifiers,
            "체력": derived_stats["체력"],
            "장갑클래스": derived_stats["장갑클래스"],
            "기본공격보너스": derived_stats["기본공격보너스"],
            "행동순서": derived_stats["행동순서"],
            "기능": skills,
            "언어": derived_stats["언어"],
            "행운점수": derived_stats["행운점수"],
            "장비": {
                "착용가능갑옷": CLASS_DEFAULTS[character_class]["착용가능갑옷"],
                "소지품": ["간편한 옷", "모험 장비"],
                "무기": weapons,
                "갑옷": armor,
                "소지금": money
            },
            "생성일": now,
            "마지막수정일": now
        }
        
        return character_data
    
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
    def calculate_derived_stats(cls, character_class, modifiers):
        """파생 능력치 계산"""
        cls_defaults = CLASS_DEFAULTS[character_class]
        
        # 체력 계산
        hit_dice = cls_defaults["체력주사위"]
        max_hp = {"d6": 6, "d8": 8, "d10": 10}.get(hit_dice, 8)
        max_hp += modifiers.get("건강", 0)
        max_hp = max(max_hp, 1)  # 최소 1
        
        # AC 계산
        ac = 10 + modifiers.get("민첩성", 0)
        
        # 행동순서 계산
        initiative = 1 + modifiers.get("민첩성", 0) + cls_defaults["행동순서_보너스"]
        
        # 추가 언어 처리
        languages = ["공용어"]
        int_bonus = modifiers.get("지능", 0)
        if int_bonus > 0:
            languages.append(f"추가 언어 {int_bonus}개 선택 가능")
        
        return {
            "체력": {
                "최대": max_hp,
                "현재": max_hp,
                "체력주사위": hit_dice
            },
            "장갑클래스": ac,
            "기본공격보너스": cls_defaults["기본공격보너스"],
            "행동순서": initiative,
            "언어": languages,
            "행운점수": {
                "최대": cls_defaults["행운점수"],
                "현재": cls_defaults["행운점수"]
            }
        }
    
    @classmethod
    def roll_abilities(cls):
        """능력치 굴리기만 (배정하지 않음)"""
        ability_scores = []
        for _ in range(6):  # 6개 능력치
            # 4d6 굴리고 가장 낮은 주사위 제외
            rolls = [random.randint(1, 6) for _ in range(4)]
            total = sum(sorted(rolls)[1:])  # 가장 낮은 주사위 제외하고 합산
            ability_scores.append(total)
        
        return ability_scores 