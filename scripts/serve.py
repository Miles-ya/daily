from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path

root = Path(__file__).parents[1] / "site-output"
print("Daily local preview: http://127.0.0.1:8000/")
handler = partial(SimpleHTTPRequestHandler, directory=str(root))
ThreadingHTTPServer(("127.0.0.1", 8000), handler).serve_forever()
