from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os

root = Path(__file__).parents[1] / "site-output"
os.chdir(root)
print("Daily local preview: http://127.0.0.1:8000/")
ThreadingHTTPServer(("127.0.0.1", 8000), SimpleHTTPRequestHandler).serve_forever()
