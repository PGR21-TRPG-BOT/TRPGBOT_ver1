import os
import google.generativeai as genai
from supabase import create_client, Client
# PDF 관련 라이브러리 제거: from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
import traceback # 오류 추적을 위해 추가
from sentence_transformers import SentenceTransformer  # 추가: Sentence Transformer 임포트

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 설정 ---
# Supabase 설정 (환경 변수 사용 권장)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") # 서버 환경에서는 service_role 키 사용 가능
# Google AI 설정 (환경 변수 사용 권장)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Supabase 테이블 및 함수 이름 변경
TABLE_NAME = "sentencetransformermdrules" # 테이블 이름 변경
MATCH_FUNCTION_NAME = "match_sentencetransformermdrules_documents" # 오류 힌트에 따라 함수 이름 수정

# Supabase 테이블 및 함수 이름 변경
# TABLE_NAME = "mdrules" # 테이블 이름 변경
# MATCH_FUNCTION_NAME = "match_mdrules_documents" # 검색 함수 이름 변경

# 임베딩 모델 설정 (all-mpnet-base-v2는 768차원 벡터를 생성하는 모델)
SENTENCE_TRANSFORMER_MODEL = "all-mpnet-base-v2"  # 차원 문제 해결을 위해 768차원 모델로 변경
GENERATION_MODEL = "gemini-2.5-flash-preview-05-20" #"gemini-2.5-pro-preview-06-05"

# LLM 생성 설정
LLM_TEMPERATURE = 1.3  # 창의성 수준 (0.0=결정적, 1.0=매우창의적)
LLM_TOP_P = 0.8        # 토큰 선택 다양성
LLM_TOP_K = 40         # 후보 토큰 수
LLM_MAX_TOKENS = 8192  # 최대 출력 토큰 수

# --- 초기화 ---
try:
    # Supabase 클라이언트 초기화
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase 클라이언트 초기화 성공")

    # Google AI 클라이언트 초기화 (LLM용으로만 사용)
    genai.configure(api_key=GOOGLE_API_KEY)
    print(f"Google AI (LLM: {GENERATION_MODEL}) 클라이언트 초기화 성공")
    
    # Sentence Transformer 모델 초기화
    sentence_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
    embed_dim = sentence_model.get_sentence_embedding_dimension()
    print(f"Sentence Transformer 모델 ({SENTENCE_TRANSFORMER_MODEL}) 초기화 성공")
    print(f"모델 벡터 차원: {embed_dim}")

except Exception as e:
    print(f"초기화 중 오류 발생: {e}")
    print(traceback.format_exc()) # 상세 오류 출력
    exit()

# --- 함수 정의 ---

def read_markdown_file(md_path: str) -> str:
    """마크다운 파일에서 텍스트를 읽어옵니다."""
    try:
        # UTF-8 인코딩으로 파일 읽기 (마크다운 파일에 일반적)
        with open(md_path, 'r', encoding='utf-8') as f:
            text = f.read()
        print(f"'{md_path}'에서 텍스트 읽기 완료 (길이: {len(text)})")
        return text
    except FileNotFoundError:
        print(f"오류: 파일 '{md_path}'를 찾을 수 없습니다.")
        return ""
    except Exception as e:
        print(f"마크다운 파일 읽기 중 오류 발생: {e}")
        print(traceback.format_exc()) # 상세 오류 출력
        return ""

# split_text 함수는 변경 없음 (텍스트 분할 로직 동일)
def split_text(text: str, chunk_size: int = 1500, chunk_overlap: int = 400) -> list[str]:
    """텍스트를 지정된 크기의 청크로 분할합니다."""
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False, # Markdown 특수 문자를 분리자로 간주하지 않도록 False 유지
        )
        chunks = text_splitter.split_text(text)
        # 빈 청크 제거 (파일 시작/끝의 공백 등으로 인해 발생 가능)
        chunks = [chunk for chunk in chunks if chunk.strip()]
        print(f"텍스트를 {len(chunks)}개의 유효한 청크로 분할 완료")
        return chunks
    except Exception as e:
        print(f"텍스트 분할 중 오류 발생: {e}")
        print(traceback.format_exc()) # 상세 오류 출력
        return []

# get_embedding 함수 변경 (Sentence Transformer 사용)
def get_embedding(text: str) -> list[float] | None:
    """주어진 텍스트의 임베딩 벡터를 Sentence Transformer를 사용하여 생성합니다."""
    # 매우 짧은 텍스트나 공백만 있는 텍스트는 임베딩 요청하지 않음
    if not text or text.isspace():
        print("  경고: 비어 있거나 공백만 있는 텍스트는 임베딩을 건너뜁니다.")
        return None
    try:
        # Sentence Transformer로 임베딩 생성
        embedding = sentence_model.encode(text)
        # 리스트로 변환하여 반환 (Supabase에 저장 가능한 형태)
        return embedding.tolist()
    except Exception as e:
        error_message = f"임베딩 생성 중 오류 발생: {e}"
        print(error_message)
        print(traceback.format_exc()) # 상세 오류 출력을 활성화
        return None

# store_chunks_in_supabase 함수는 테이블 이름(TABLE_NAME) 변수를 사용하므로 내부 로직 변경 불필요
def store_chunks_in_supabase(chunks: list[str]):
    """텍스트 청크와 임베딩을 Supabase에 저장합니다."""
    print(f"총 {len(chunks)}개의 청크를 Supabase '{TABLE_NAME}' 테이블에 저장 시작...")
    stored_count = 0
    skipped_count = 0
    for i, chunk in enumerate(chunks):
        # 청크 내용 앞뒤 공백 제거
        cleaned_chunk = chunk.strip()
        if not cleaned_chunk: # 공백 제거 후 내용이 없으면 건너뜀
            print(f"  청크 {i+1}/{len(chunks)} 건너뜀 (내용 없음).")
            skipped_count += 1
            continue

        embedding = get_embedding(cleaned_chunk) # 정제된 청크로 임베딩 생성
        if embedding:
            # 임베딩 차원 확인
            print(f"  임베딩 차원: {len(embedding)}")
            try:
                # 테이블 이름 변수 사용
                data, count = supabase.table(TABLE_NAME).insert({
                    "content": cleaned_chunk, # 정제된 청크 저장
                    "embedding": embedding
                }).execute()
                # data나 count 대신 실제 응답 상태 확인이 더 정확할 수 있음
                stored_count += 1
                print(f"  청크 {i+1}/{len(chunks)} 저장 성공.")
            except Exception as e:
                print(f"  청크 {i+1}/{len(chunks)} 저장 중 오류 발생: {e}")
                print(traceback.format_exc()) # 상세 오류 출력
                skipped_count += 1
        else:
            print(f"  청크 {i+1}/{len(chunks)} 저장 실패 (임베딩 생성 실패).")
            skipped_count += 1

    print(f"총 {stored_count}개 청크 저장 완료, {skipped_count}개 건너뜀/실패.")


# find_similar_chunks 함수 변경 (Sentence Transformer 사용)
def find_similar_chunks(query: str, match_count: int = 3, match_threshold: float = 0.7) -> list[tuple[float, str]]:
    """사용자 질문과 유사한 텍스트 청크를 Supabase에서 검색합니다."""
    try:
        # Sentence Transformer를 사용하여 질문 임베딩 생성
        query_embedding = sentence_model.encode(query).tolist()
        print(f"쿼리 임베딩 차원: {len(query_embedding)}")

        # 🚨 NEW: 타임아웃 추가
        import threading
        import time
        
        # 타임아웃을 위한 결과 저장 변수
        search_result = {"response": None, "error": None, "completed": False}
        
        def supabase_search_with_timeout():
            """타임아웃이 있는 Supabase 검색"""
            try:
                start_time = time.time()
                print(f"🔍 Supabase RPC 호출 시작: {MATCH_FUNCTION_NAME}")
                
                # Supabase 함수 호출 (함수 이름 변수 사용)
                response = supabase.rpc(MATCH_FUNCTION_NAME, {
                    'query_embedding': query_embedding,
                    'match_threshold': match_threshold,
                    'match_count': match_count
                }).execute()
                
                end_time = time.time()
                search_result["response"] = response
                search_result["completed"] = True
                print(f"✅ Supabase RPC 응답 완료 (소요시간: {end_time - start_time:.1f}초)")
                
            except Exception as e:
                search_result["error"] = str(e)
                search_result["completed"] = True
                print(f"❌ Supabase RPC 호출 중 오류: {e}")
        
        # 별도 스레드에서 Supabase 검색 실행
        search_thread = threading.Thread(target=supabase_search_with_timeout)
        search_thread.daemon = True
        search_thread.start()
        
        # 타임아웃 대기 (15초)
        timeout_seconds = 15
        wait_time = 0
        
        while wait_time < timeout_seconds and not search_result["completed"]:
            time.sleep(1)
            wait_time += 1
            
            # 3초마다 진행 상황 로깅
            if wait_time % 3 == 0:
                print(f"⏳ Supabase 검색 대기 중... ({wait_time}/{timeout_seconds}초)")
        
        # 타임아웃 체크
        if not search_result["completed"]:
            print(f"⏰ Supabase 검색 타임아웃 ({timeout_seconds}초) - 빈 결과 반환")
            return []
        
        # 검색 오류 체크
        if search_result["error"]:
            print(f"❌ Supabase 검색 오류: {search_result['error']}")
            return []
        
        # 정상 응답 처리
        response = search_result["response"]
        if response and response.data:
            # (유사도 점수, 내용) 튜플 리스트로 반환
            similar_chunks = [(item.get('similarity', 0.0), item['content']) for item in response.data]
            print(f"'{query}'와(과) 유사한 청크 {len(similar_chunks)}개 검색 완료 (테이블: {TABLE_NAME}).")
            # for i in range(len(similar_chunks)):
            #     print(f"similar_chunks[{i}]: ", similar_chunks[i],"\n") # 테스트용 : 어떤 청크들을 가지고 왔는가?
            return similar_chunks
        else:
            print(f"유사한 청크를 찾지 못했습니다 (테이블: {TABLE_NAME}, 임계값: {match_threshold}).")
            return []
            
    except Exception as e:
        print(f"유사성 검색 중 오류 발생: {e}")
        print(traceback.format_exc()) # 상세 오류 출력
        return []

def generate_answer_without_rag(query, session_type="기타", character_context=""):
    """RAG 없이 순수 LLM만으로 답변 생성"""
    try:
        # 세션 유형에 따른 프롬프트 조정
        session_guidance = ""
        if session_type == "캐릭터_생성":
            session_guidance = """
당신은 지금 캐릭터 생성 세션에 있습니다. 플레이어가 캐릭터를 만드는 것을 돕고 있으니, 
캐릭터 생성에 필요한 조언을 제공하세요. 만약 플레이어가 랜덤 캐릭터나 무작위 캐릭터를 만들어달라고 하면, 
캐릭터가 생성될 것이라고 안내해 주세요.
"""
        elif session_type == "시나리오_생성":
            session_guidance = """
당신은 지금 시나리오 생성 세션에 있습니다. 흥미로운 모험 시나리오를 만들고 있으니,
플레이어의 질문에 맞게 이야기, 장소, 비밀, 보물, NPC 등에 대한 정보를 제공하세요.
"""
        elif session_type == "모험_진행" or session_type == "던전_탐험":
            session_guidance = """
당신은 지금 모험/던전 탐험 세션에 있습니다. 게임마스터로서 플레이어의 행동에 반응하고,
주변 환경과 상황에 대한 생생한 설명을 제공하세요. 도전과 위험을 관리하고 플레이어가 선택할 수 있는 옵션을 제시하세요.
"""
        
        # 프롬프트 구성 (RAG 없이 순수 LLM 생성)
        prompt = f"""
당신은 텍스트 기반 TRPG(테이블톱 롤플레잉 게임)의 게임마스터입니다. 

## 세션 정보
현재 세션: {session_type}
{session_guidance}

## 캐릭터 정보
{character_context}

## 사용자 질문
"{query}"

## 지침
1. 게임마스터로서 적절한 어조와 스타일로 대답하세요.
2. TRPG의 일반적인 지식과 창의성을 바탕으로 답변하세요.
3. 답변은 명확하고 간결하게 제공하고, 필요한 경우 플레이어가 취할 수 있는 다음 행동을 제안하세요.
4. 캐릭터 정보가 제공되었다면 캐릭터의 특성과 능력을 고려하여 응답하세요.
5. 사용자가 '랜덤 캐릭터' 또는 '무작위 캐릭터'를 요청하는 경우 창의적으로 캐릭터를 생성해주세요.
6. 상황에 맞는 흥미로운 스토리텔링과 몰입감 있는 설명을 제공하세요.

## 응답:
"""
        
        # 응답 생성 (높은 temperature로 창의적인 응답 생성)
        model = genai.GenerativeModel(GENERATION_MODEL)
        generation_config = genai.types.GenerationConfig(
            temperature=LLM_TEMPERATURE,      # 창의성 수준
            top_p=LLM_TOP_P,                  # 토큰 선택 다양성
            top_k=LLM_TOP_K,                  # 후보 토큰 수
            max_output_tokens=LLM_MAX_TOKENS, # 최대 출력 토큰 수
        )
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # 🚨 CRITICAL FIX: LLM 응답 안전성 검사
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            
            # finish_reason 확인
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason != 1:  # 1 = STOP (정상 완료)
                print(f"⚠️ LLM 응답 finish_reason: {candidate.finish_reason}")
                
                if candidate.finish_reason == 2:  # MAX_TOKENS
                    return "응답이 너무 길어서 중단되었습니다. 더 간단한 질문을 해주세요."
                elif candidate.finish_reason == 3:  # SAFETY
                    return "안전 정책에 의해 응답이 차단되었습니다. 다른 방식으로 질문해주세요."
                elif candidate.finish_reason == 4:  # RECITATION
                    return "저작권 문제로 응답이 차단되었습니다. 다른 방식으로 질문해주세요."
                else:
                    return "응답 생성 중 문제가 발생했습니다. 다시 시도해주세요."
            
            # 응답 텍스트 추출
            if hasattr(candidate, 'content') and candidate.content.parts:
                return candidate.content.parts[0].text
            else:
                return response.text  # 폴백
        else:
            return "응답을 생성할 수 없습니다. 다시 시도해주세요."
            
    except Exception as e:
        print(f"LLM 답변 생성 중 오류 발생: {e}")
        print(traceback.format_exc())
        return "죄송합니다, 응답을 생성하는 중에 오류가 발생했습니다. 다시 시도해주세요."

# generate_answer_with_rag 함수는 변경 없음 (LLM 호출 로직 동일)
def generate_answer_with_rag(query, similar_chunks, session_type="기타", character_context=""):
    """유사한 청크들을 기반으로 RAG로 답변 생성"""
    try:
        # 문맥 구성
        context = ""
        for i, (score, text) in enumerate(similar_chunks, 1):
            context += f"--- 청크 {i} (관련도: {score:.3f}) ---\n{text}\n\n"
        
        # 세션 유형에 따른 프롬프트 조정
        session_guidance = ""
        if session_type == "캐릭터_생성":
            session_guidance = """
당신은 지금 캐릭터 생성 세션에 있습니다. 플레이어가 캐릭터를 만드는 것을 돕고 있으니, 
캐릭터 생성에 필요한 조언을 제공하세요. 만약 플레이어가 랜덤 캐릭터나 무작위 캐릭터를 만들어달라고 하면, 
캐릭터가 생성될 것이라고 안내해 주세요.
"""
        elif session_type == "시나리오_생성":
            session_guidance = """
당신은 지금 시나리오 생성 세션에 있습니다. 흥미로운 모험 시나리오를 만들고 있으니,
플레이어의 질문에 맞게 이야기, 장소, 비밀, 보물, NPC 등에 대한 정보를 제공하세요.
"""
        elif session_type == "모험_진행" or session_type == "던전_탐험":
            session_guidance = """
당신은 지금 모험/던전 탐험 세션에 있습니다. 게임마스터로서 플레이어의 행동에 반응하고,
주변 환경과 상황에 대한 생생한 설명을 제공하세요. 도전과 위험을 관리하고 플레이어가 선택할 수 있는 옵션을 제시하세요.
"""
        
        # 프롬프트 구성
        prompt = f"""
당신은 텍스트 기반 TRPG(테이블톱 롤플레잉 게임)의 게임마스터입니다. 

## 세션 정보
현재 세션: {session_type}
{session_guidance}

## 캐릭터 정보
{character_context}

## 데이터베이스 조회 결과
{context}

## 사용자 질문
"{query}"

## 지침
1. 게임마스터로서 적절한 어조와 스타일로 대답하세요.
2. 데이터베이스 조회 결과 내에서 관련 정보를 찾아 답변에 활용하세요.
3. 데이터베이스에 없는 정보는 TRPG 맥락에 맞게 창의적으로 대답하세요.
4. 답변은 명확하고 간결하게 제공하고, 필요한 경우 플레이어가 취할 수 있는 다음 행동을 제안하세요.
5. 캐릭터 정보가 제공되었다면 캐릭터의 특성과 능력을 고려하여 응답하세요.
6. 사용자가 '랜덤 캐릭터' 또는 '무작위 캐릭터'를 요청하는 경우 캐릭터가 생성될 것이라고 안내해주세요.

## 응답:
"""
        
        # 응답 생성 (높은 temperature로 창의적인 응답 생성)
        model = genai.GenerativeModel(GENERATION_MODEL)
        generation_config = genai.types.GenerationConfig(
            temperature=LLM_TEMPERATURE,      # 창의성 수준
            top_p=LLM_TOP_P,                  # 토큰 선택 다양성
            top_k=LLM_TOP_K,                  # 후보 토큰 수
            max_output_tokens=LLM_MAX_TOKENS, # 최대 출력 토큰 수
        )
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # 🚨 CRITICAL FIX: LLM 응답 안전성 검사
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            
            # finish_reason 확인
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason != 1:  # 1 = STOP (정상 완료)
                print(f"⚠️ RAG LLM 응답 finish_reason: {candidate.finish_reason}")
                
                if candidate.finish_reason == 2:  # MAX_TOKENS
                    return "응답이 너무 길어서 중단되었습니다. 더 간단한 질문을 해주세요."
                elif candidate.finish_reason == 3:  # SAFETY
                    return "안전 정책에 의해 응답이 차단되었습니다. 다른 방식으로 질문해주세요."
                elif candidate.finish_reason == 4:  # RECITATION
                    return "저작권 문제로 응답이 차단되었습니다. 다른 방식으로 질문해주세요."
                else:
                    return "응답 생성 중 문제가 발생했습니다. 다시 시도해주세요."
            
            # 응답 텍스트 추출
            if hasattr(candidate, 'content') and candidate.content.parts:
                return candidate.content.parts[0].text
            else:
                return response.text  # 폴백
        else:
            return "응답을 생성할 수 없습니다. 다시 시도해주세요."
            
    except Exception as e:
        print(f"RAG 답변 생성 중 오류 발생: {e}")
        print(traceback.format_exc())
        return "죄송합니다, 응답을 생성하는 중에 오류가 발생했습니다. 다시 시도해주세요."

# --- 실행 흐름 ---
if __name__ == "__main__":
    # 1. 처리할 마크다운 파일 경로 지정
    md_file_path = "울타리 너머 - 또 다른 모험으로 RAG 소스 데이터.md" # 여기에 실제 마크다운 파일 경로를 입력하세요.

    # 마크다운 파일 존재 여부 확인
    if not os.path.exists(md_file_path):
        print(f"오류: 마크다운 파일 '{md_file_path}'를 찾을 수 없습니다.")
    else:
        # --- 데이터 준비 (마크다운 처리 및 Supabase 저장) ---
        # 이 부분은 파일 내용이 변경될 때만 실행하거나,
        # 이미 데이터가 저장되어 있다면 주석 처리하고 검색/답변 부분만 실행할 수 있습니다.

        print("\n=== 마크다운 처리 및 임베딩 저장 시작 ===")
        # 마크다운 텍스트 읽기
        md_text = read_markdown_file(md_file_path)

        if md_text:
            # 텍스트 분할
            text_chunks = split_text(md_text)

            if text_chunks:
                # Supabase에 청크 및 임베딩 저장
                # 기존 데이터 삭제 시도
                print(f"기존 '{TABLE_NAME}' 테이블 데이터 삭제 중...")
                try:
                    supabase.table(TABLE_NAME).delete().neq('id', 0).execute() # 모든 데이터 삭제
                    print("기존 데이터 삭제 완료.")
                except Exception as e:
                    print(f"데이터 삭제 중 오류 발생: {e}, 계속 진행합니다.")
                
                store_chunks_in_supabase(text_chunks)
            else:
                print("텍스트를 청크로 분할하지 못했습니다.")
        else:
            print("마크다운 파일에서 텍스트를 읽지 못했습니다.")
        print("=== 마크다운 처리 및 임베딩 저장 완료 ===\n")


        # --- RAG 실행 (질문 -> 검색 -> 답변 생성) ---
        print("\n=== RAG 질문 응답 시작 ===")
        # 사용자 질문 예시
        user_question = "마크다운 문서의 주요 내용 요약해줘." # 여기에 질문을 입력하세요.

        # 1. 유사성 검색 (임계값 낮춤)
        similar_chunks = find_similar_chunks(user_question, match_count=3, match_threshold=0.5)

        # 2. 답변 생성
        final_answer = generate_answer_with_rag(user_question, similar_chunks, "캐릭터_생성")

        # 3. 최종 답변 출력
        print("\n--- 최종 답변 ---")
        print(final_answer)
        print("=================\n")