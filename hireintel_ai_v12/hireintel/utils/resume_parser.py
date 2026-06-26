import os, re
from pypdf import PdfReader
from docx import Document as DocxDoc


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            r = PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in r.pages).strip()
        elif ext in (".docx", ".doc"):
            d = DocxDoc(path)
            return "\n".join(p.text for p in d.paragraphs if p.text.strip()).strip()
        elif ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
    except Exception as e:
        return f"[Parse error: {e}]"
    return "[Unsupported format]"


def load_resumes_from_folder(folder: str) -> list:
    supported = {".pdf", ".docx", ".doc", ".txt"}
    out = []
    if not os.path.isdir(folder):
        return out
    for fname in os.listdir(folder):
        if os.path.splitext(fname)[1].lower() not in supported:
            continue
        path = os.path.join(folder, fname)
        text = extract_text(path)
        name = nice_name(fname)
        out.append({"filename": fname, "path": path, "text": text, "name": name})
    return out


def nice_name(filename: str) -> str:
    return re.sub(r"[_\-]", " ", os.path.splitext(filename)[0]).strip().title()
