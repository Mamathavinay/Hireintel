# 🧠 HireIntel AI — Multi-Agent Hiring Platform

Built for HCLTech OpenAI Hackathon | Track 2: Enterprise Operations

---

## ⚡ Quick Start (3 steps)

### Step 1 — Install dependencies
```bash
cd hireintel
pip install -r requirements.txt
```

### Step 2 — Configure your API keys
```bash
# Copy the example env file
copy .env.example .env        # Windows
cp .env.example .env          # Mac/Linux

# Edit .env and add your keys:
# GROQ_API_KEY=your_groq_api_key_here
# EMAIL_SENDER=your_email@gmail.com
# EMAIL_PASSWORD=your_gmail_app_password
# COMPANY_NAME=HCLTech
```

### Step 3 — Run the app
```bash
streamlit run app.py
```
Open http://localhost:8501 in your browser.

---

## 🗺️ How to Use the App

| Step | Page | What to do |
|------|------|-----------|
| 1 | **Upload JD** | Paste or upload a Job Description → AI analyzes it |
| 2 | **Upload Resumes** | Upload PDF/DOCX files OR give a folder path |
| 3 | **Screen & Match** | Run AI screening → see shortlisted candidates |
| 4 | **Interview** | Select a candidate → AI generates questions → conduct interview with AI assist |
| 5 | **Decision** | See AI verdict → Manager Agent final decision |
| 6 | **Schedule & Email** | Send interview invite with slots → send confirmation |
| 7 | **Analytics** | Trend analysis + team sync summary |
| 8 | **Human Review** | Review borderline candidates flagged by AI |

---

## 📧 Gmail Email Setup

1. Enable 2-Factor Authentication on your Google Account
2. Go to: Google Account → Security → 2-Step Verification → **App Passwords**
3. Create App Password for "Mail"
4. Use that 16-character password as `EMAIL_PASSWORD` in `.env`

---

## 🤖 12 Agents Implemented

| Agent | Role |
|-------|------|
| Manager Agent | Orchestrates all agents, final decision |
| JD Analyzer | Extracts skills & criteria from JD |
| Skill Matcher | Scores candidate fit against JD |
| Question Generator | Creates Conceptual/Coding/Scenario questions |
| Rubric Agent | Standardised evaluation rubric |
| Candidate Evaluator | Scores interview responses |
| Real-Time Assist | Live hints to interviewer |
| Communication Agent | Scores verbal clarity |
| Feedback Analyzer | Synthesizes all scores into verdict |
| Trend Analysis | Spots patterns across all candidates |
| Knowledge Management | RAG: stores JDs + resumes for re-use |
| Collaboration Agent | Team sync + best practice sharing |

---

## 🛠️ Tech Stack

- **LLM:** Groq API (llama3-70b-8192)
- **Frontend:** Streamlit
- **RAG / Vector DB:** ChromaDB (local, no API key needed)
- **Embeddings:** ChromaDB default (sentence-transformers, runs locally)
- **Email:** SMTP (Gmail)
- **Charts:** Plotly
- **Resume Parsing:** pypdf + python-docx

---

## 📁 Project Structure

```
hireintel/
├── app.py                  # Main Streamlit app (all 10 pages)
├── config.py               # Groq client + env config
├── requirements.txt
├── .env.example            # Copy to .env and fill keys
├── agents/
│   └── all_agents.py       # All 12 agents
├── rag/
│   └── rag_engine.py       # ChromaDB RAG engine
├── utils/
│   ├── resume_parser.py    # PDF/DOCX/TXT parser
│   └── email_sender.py     # Email sender
└── data/
    ├── resumes/            # Optional: put resumes here
    ├── jds/                # Optional: put JDs here
    └── chromadb/           # Auto-created vector DB
```
