import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
EMAIL_SENDER  = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD= os.getenv("EMAIL_PASSWORD", "")
SMTP_HOST     = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("EMAIL_SMTP_PORT", 587))
COMPANY_NAME  = os.getenv("COMPANY_NAME", "HireIntel AI")

BASE_DIR    = os.path.dirname(__file__)
CHROMA_PATH = os.path.join(BASE_DIR, "data", "chromadb")
RESUME_PATH = os.path.join(BASE_DIR, "data", "resumes")
JD_PATH     = os.path.join(BASE_DIR, "data", "jds")

for _p in [CHROMA_PATH, RESUME_PATH, JD_PATH]:
    os.makedirs(_p, exist_ok=True)

# FIX 3: Updated to current active Groq model (llama3-70b decommissioned)
GROQ_MODEL = "llama-3.3-70b-versatile"

def get_groq_client():
    from groq import Groq
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env file")
    return Groq(api_key=GROQ_API_KEY)
