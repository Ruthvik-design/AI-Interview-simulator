from http.server import ThreadingHTTPServer
from config import HOST, PORT, MODEL, OLLAMA_URL
from database import init_db, get_setting
from routes import Handler

if __name__ == "__main__":
    init_db()
    print(f"AI Interview Simulator: http://{HOST}:{PORT}")
    print(f"Ollama model: {get_setting('model', MODEL)} | endpoint: {OLLAMA_URL}")
    print("Press Ctrl+C to stop.")
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
