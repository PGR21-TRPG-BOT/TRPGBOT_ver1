# -*- coding: utf-8 -*-
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import BOT_TOKEN
from character_manager import CharacterManager
from telegram_handlers import (
    start, help_command, declare, character, scenario, session, 
    show_session_history, roll_dice_command, button_callback, fill_scenario, reset_scenario
)
from message_processor import handle_message

# 로깅 설정: 봇의 활동 및 오류를 콘솔에 출력하기 위함
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # 로그 형식 지정
    level=logging.INFO # 정보 수준 이상의 로그만 출력
)
logger = logging.getLogger(__name__) # 로거 객체 생성

# 초기화 함수
def initialize_bot():
    """봇 초기화 작업 수행"""
    # 캐릭터 관리자 초기화
    CharacterManager.initialize()

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
    application.add_handler(CommandHandler("scenario", scenario))  # 시나리오
    application.add_handler(CommandHandler("fill_scenario", fill_scenario))  # 시나리오 빈 부분 보완
    application.add_handler(CommandHandler("reset_scenario", reset_scenario))  # 시나리오 초기화
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