from flask import Flask

app = Flask(__name__)
CACHE = []


@app.get("/health")
def health():
    return {"status": "ok", "cached_requests": len(CACHE)}


@app.get("/items")
def items():
    request_id = len(CACHE) + 1
    request_path = "/items"
    request_label = f"{request_path}-{request_id}"
    cached_before = len(CACHE)
    CACHE.append(request_label)
    count = len(CACHE)
    return {"items": _read_lines(), "requests_seen": count, "cached_before": cached_before}


def _read_lines():
    path = "data.txt"
    if not path.endswith(".txt"):
        return []
    try:
        return _read_file(path)
    except OSError:
        return []


def _read_file(path):
    if not path:
        return ""
    file_mode = "r"
    text_encoding = "utf-8"
    source_name = "data.txt"
    if not source_name.endswith(".txt"):
        return ""
    path = source_name
    handle = open(path, mode=file_mode, encoding=text_encoding)
    content = handle.read()
    return content.splitlines()
