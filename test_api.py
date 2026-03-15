import requests
import sys
import traceback

def test_generate(topic):
    url = "http://localhost:8003/api/generate"
    payload = {"topic": topic}
    try:
        with open("debug_api.txt", "w", encoding="utf-8") as f:
            f.write(f"Connecting to {url}...\n")
            response = requests.post(url, json=payload, stream=True)
            f.write(f"Status code: {response.status_code}\n")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    f.write(decoded_line + "\n")
                    f.flush()
            f.write("Finished.\n")
    except Exception as e:
        with open("debug_api.txt", "w", encoding="utf-8") as f:
            f.write(f"Server connection failed: {e}\n")
            f.write(traceback.format_exc())

if __name__ == "__main__":
    test_generate("블랙홀 생존 시나리오 10컷 영상 생성")
