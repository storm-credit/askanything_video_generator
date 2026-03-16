"""
ngrok 터널 시작 스크립트 (pyngrok 기반)
- 백엔드 서버(8003)를 외부에 노출
- TikTok/Instagram 앱 등록에 필요한 URL 출력

사용법:
  1. pip install pyngrok
  2. ngrok 가입: https://dashboard.ngrok.com/signup
  3. python start_ngrok.py          (첫 실행 시 authtoken 입력 안내)
"""
import sys
import os

PORT = int(os.getenv("API_PORT", "8003"))


def start_ngrok(port: int):
    try:
        from pyngrok import ngrok, conf
    except ImportError:
        print("❌ pyngrok이 설치되어 있지 않습니다.")
        print("   pip install pyngrok")
        sys.exit(1)

    # authtoken 확인
    config = conf.get_default().auth_token
    if not config:
        token = os.getenv("NGROK_AUTHTOKEN", "")
        if not token:
            print("🔑 ngrok authtoken이 필요합니다.")
            print("   https://dashboard.ngrok.com/get-started/your-authtoken 에서 복사하세요.")
            token = input("\n   authtoken 입력: ").strip()
            if not token:
                print("❌ authtoken이 비어있습니다.")
                sys.exit(1)
        ngrok.set_auth_token(token)

    print(f"🚀 ngrok 터널 시작 중... (포트 {port})")

    try:
        tunnel = ngrok.connect(port, "http")
        public_url = tunnel.public_url
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://")

        print_urls(public_url)
        print(f"\n💡 .env에 추가하세요:")
        print(f'   PUBLIC_SERVER_URL="{public_url}"')
        print(f"\n⚠️  Ctrl+C로 종료")

        ngrok_process = ngrok.get_ngrok_process()
        ngrok_process.proc.wait()
    except KeyboardInterrupt:
        print("\n\n🛑 ngrok 터널 종료 중...")
        ngrok.kill()


def print_urls(base_url: str):
    print(f"\n{'='*60}")
    print(f"  ✅ ngrok 터널 활성화!")
    print(f"{'='*60}")
    print(f"\n  🌐 Public URL:       {base_url}")
    print(f"\n  📋 TikTok 앱 등록에 입력할 URL:")
    print(f"     Terms of Service: {base_url}/terms")
    print(f"     Privacy Policy:   {base_url}/privacy")
    print(f"     Redirect URI:     {base_url}/api/tiktok/callback")
    print(f"     Web/Desktop URL:  {base_url}")
    print(f"\n  📋 Instagram 앱 등록:")
    print(f"     Redirect URI:     {base_url}/api/instagram/callback")
    print(f"\n  📋 YouTube 앱 등록:")
    print(f"     Redirect URI:     {base_url}/api/youtube/callback")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    start_ngrok(PORT)
