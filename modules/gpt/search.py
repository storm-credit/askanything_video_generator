import os


def get_fact_check_context(topic: str) -> str:
    """
    Tavily Search API를 사용하여 주제에 대한 최신/팩트 정보를 실시간으로 검색하여
    GPT 컨텍스트로 주입할 문자열을 반환합니다.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("[Tavily 오류] TAVILY_API_KEY가 설정되지 않아 팩트체크 검색을 건너뜁니다.")
        return ""

    try:
        from tavily import TavilyClient
    except ImportError:
        print("[Tavily 오류] tavily 패키지가 설치되지 않아 팩트체크 검색을 건너뜁니다. (pip install tavily-python)")
        return ""

    try:
        print(f"-> [팩트체크 엔진] '{topic}'에 대한 실시간 논문/웹 검색 중 (Tavily Search API)...")
        client = TavilyClient(api_key=api_key)

        # 검색 수행 (최신 정보 포함, 최대 3개의 핵심 정보만 가져옴)
        response = client.search(
            query=topic,
            search_depth="advanced",
            include_answer=True,
            max_results=3,
        )

        # GPT에게 전달할 요약 컨텍스트 생성
        context = "### [실시간 웹 검색 팩트체크 자료 (Tavily Search API)] ###\n"
        context += "아래의 검색된 팩트 자료를 100% 신뢰할 수 있는 사실로 취급하여 대본의 'Climax'나 'Context'를 작성하는 데 참고하십시오.\n\n"

        if "answer" in response and response["answer"]:
            context += f"💡 [AI 요약 답변]: {response['answer']}\n\n"

        context += "🔍 [상세 검색 결과 (교차 검증 자료)]:\n"
        for i, result in enumerate(response.get("results", [])):
            context += f"{i+1}. 제목: {result.get('title')}\n"
            context += f"   출처: {result.get('url')}\n"
            context += f"   내용: {result.get('content')}\n\n"

        print("OK [팩트체크 엔진] 실시간 정보 검색 완료! (대본 기획에 RAG 주입 대기)")
        return context
    except Exception as e:
        print(f"[Tavily 오류] 실시간 검색 중 예외 발생: {e}")
        return ""
