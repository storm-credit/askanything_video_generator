import subprocess

try:
    result = subprocess.run(["python", "-c", "import api_server"], capture_output=True, text=True, check=True)
    with open("syntax_check.txt", "w", encoding="utf-8") as f:
        f.write("OK\n")
        f.write(result.stdout)
except subprocess.CalledProcessError as e:
    with open("syntax_check.txt", "w", encoding="utf-8") as f:
        f.write("ERROR\n")
        f.write(e.stderr)
