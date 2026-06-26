"""
HireIntel AI — Complete Streamlit App
All 6 fixes applied:
1. Excel JD upload
2. Schedule & Email page BEFORE Interview
3. Model updated to llama-3.3-70b-versatile
4. Resumes reusable across sessions (persist in ChromaDB)
5. Duplicate resume detection — warns and skips re-storage
6. Delete resume option from knowledge base
"""
import os, sys, json, tempfile, hashlib
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from streamlit_option_menu import option_menu
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(
    page_title="HireIntel AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config import GROQ_API_KEY, COMPANY_NAME, GROQ_MODEL
from auth import verify_login, get_allowed_pages, get_page_icons, get_default_page, ROLE_PAGES
from utils.resume_parser import extract_text, load_resumes_from_folder, nice_name
from utils.excel_parser import extract_text_from_excel, parse_excel_jd
from utils.email_sender import send_interview_invite, send_confirmation, send_rejection
from rag.rag_engine import (
    upsert_resume, upsert_jd,
    search_resumes_for_jd, search_jds_for_candidate,
    get_all_resumes, get_all_jds,
    resume_count, jd_count,
    delete_resume, delete_jd,
    resume_exists,
)
from agents.all_agents import (
    analyze_jd, match_candidate, generate_rubric, generate_questions,
    evaluate_response, realtime_assist, assess_communication,
    analyze_feedback, analyze_trends, find_alternative_jd_match,
    generate_team_sync_summary, manager_final_decision,
    enrich_excel_questions,
    extract_answers_from_transcript, parse_vtt_transcript,
    evaluate_full_transcript,
    get_interview_coach_guidance,
    detect_fake_resume,
)

# ── session defaults ───────────────────────────────────────────────────────
DEFAULTS = {
    "jd_text": "", "jd_analysis": None, "rubric": None,
    "match_results": [], "selected_candidate": None,
    "questions": None, "interview_answers": [],
    "feedback_analysis": None, "comm_assessment": None,
    "rubric_result": None, "final_decision": None,
    "notifications": [], "best_practices": [],
    "human_review_queue": [], "email_log": [],
    "all_match_history": [],
    "upload_log": [],
    "excel_question_bank": [],
    "excel_jd_criteria": {},
    "selected_resume_ids": set(),
    "resumes_to_screen": [],
    "interview_mode": "question",
    "transcript_answers": {},
    # ── auth ──
    "logged_in":   False,
    "username":    "",
    "role":        "",
    "user_name":   "",
    "user_color":  "#7F77DD",
    "user_icon":   "👤",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"]{background:#1a1d2e}
.mcard{background:#1e2235;border:1px solid #2d3250;border-radius:10px;
       padding:16px 20px;margin-bottom:10px}
.mval{font-size:28px;font-weight:600}
.mlbl{font-size:12px;color:#9099b0;margin-top:2px}
.pill{display:inline-block;padding:2px 10px;border-radius:20px;
      font-size:11px;margin:2px}
.rcard{background:#1e2235;border:1px solid #2d3250;border-radius:8px;
       padding:10px;margin-bottom:8px}
.dup-box{background:#2a2010;border:1px solid #EF9F27;border-radius:8px;
         padding:10px 14px;margin-bottom:6px}
.new-box{background:#1a2a20;border:1px solid #1D9E75;border-radius:8px;
         padding:10px 14px;margin-bottom:6px}
</style>
""", unsafe_allow_html=True)

# ── helpers ────────────────────────────────────────────────────────────────
def gauge(val, title=""):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=val,
        title={"text": title, "font": {"size": 13, "color": "#9099b0"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#9099b0"},
            "bar":  {"color": "#7F77DD"},
            "steps": [
                {"range": [0,  55], "color": "#2a1f2f"},
                {"range": [55, 75], "color": "#2a2820"},
                {"range": [75,100], "color": "#1a2820"},
            ],
            "threshold": {"line": {"color": "#1D9E75", "width": 2}, "value": 75},
        },
        number={"suffix": "%", "font": {"color": "#e0e0e0"}},
    ))
    fig.update_layout(height=190, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def notify(msg, kind="info"):
    st.session_state.notifications.append({"msg": msg, "kind": kind})

def show_notifs():
    for n in st.session_state.notifications[-3:]:
        getattr(st, n["kind"])(n["msg"])
    if st.session_state.notifications:
        if st.button("Clear notifications", key="clrn"):
            st.session_state.notifications = []

def score_color(s):
    return "#1D9E75" if s >= 75 else "#EF9F27" if s >= 55 else "#D85A30"

# ── LOGIN GATE ──────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    # centre the login card
    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 24px'>
          <div style='font-size:48px'>🧠</div>
          <div style='font-size:26px;font-weight:600;color:#e0e0e0;margin-top:8px'>HireIntel AI</div>
          <div style='font-size:13px;color:#7F77DD;margin-top:4px'>Multi-Agent Hiring Platform</div>
        </div>""", unsafe_allow_html=True)

        st.markdown(
            '<div style="background:#1e2235;border:1px solid #2d3250;border-radius:12px;'
            'padding:28px 28px 24px">', unsafe_allow_html=True)

        st.markdown("#### 🔐 Sign In")

        username = st.text_input("Username", placeholder="admin / delivery / panel",
                                  key="login_username")
        password = st.text_input("Password", type="password",
                                  placeholder="Enter your password",
                                  key="login_password")

        if st.button("Sign In", type="primary", use_container_width=True, key="login_btn"):
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                user = verify_login(username, password)
                if user:
                    st.session_state.logged_in  = True
                    st.session_state.username   = username.lower().strip()
                    st.session_state.role       = user["role"]
                    st.session_state.user_name  = user["name"]
                    st.session_state.user_color = user["color"]
                    st.session_state.user_icon  = user["icon"]
                    notify(f"Welcome, {user['name']}! Logged in as {user['role']}.", "success")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password.")

        st.markdown('</div>', unsafe_allow_html=True)

        # role legend
        st.markdown("---")
        st.markdown(
            '<div style="background:#1e2235;border:1px solid #2d3250;border-radius:10px;'
            'padding:14px 18px">'
            '<div style="font-size:12px;font-weight:500;color:#9099b0;margin-bottom:10px">'
            'Available Roles</div>'
            '<div style="display:flex;flex-direction:column;gap:8px">'
            '<div style="display:flex;align-items:center;gap:10px">'
            '<div style="font-size:18px">🛡️</div>'
            '<div><div style="font-size:13px;color:#7F77DD;font-weight:500">Admin</div>'
            '<div style="font-size:11px;color:#9099b0">Full access to all sections</div></div></div>'
            '<div style="display:flex;align-items:center;gap:10px">'
            '<div style="font-size:18px">📦</div>'
            '<div><div style="font-size:13px;color:#1D9E75;font-weight:500">Delivery</div>'
            '<div style="font-size:11px;color:#9099b0">Dashboard · JD · Resumes · Screening · '
            'Schedule · Feedback · Analytics · Review</div></div></div>'
            '<div style="display:flex;align-items:center;gap:10px">'
            '<div style="font-size:18px">🎥</div>'
            '<div><div style="font-size:13px;color:#EF9F27;font-weight:500">Interview Panel</div>'
            '<div style="font-size:11px;color:#9099b0">Interview · Feedback & Decision · '
            'Analytics · Human Review</div></div></div>'
            '</div></div>',
            unsafe_allow_html=True)

    st.stop()  # stop rendering anything else until logged in

# ── sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── user badge ──────────────────────────────────────────────────────────
    role       = st.session_state.role
    user_icon  = st.session_state.user_icon
    user_name  = st.session_state.user_name
    user_color = st.session_state.user_color

    st.markdown(f"""
    <div style='text-align:center;padding:14px 0 6px'>
      <div style='font-size:30px'>🧠</div>
      <div style='font-size:17px;font-weight:600;color:#e0e0e0'>HireIntel AI</div>
      <div style='font-size:11px;color:#7F77DD'>Multi-Agent Hiring Platform</div>
    </div>
    <div style='background:#1e2235;border:1px solid {user_color};border-radius:8px;
    padding:8px 12px;margin:8px 4px;text-align:center'>
      <div style='font-size:18px'>{user_icon}</div>
      <div style='font-size:13px;font-weight:500;color:{user_color}'>{user_name}</div>
      <div style='font-size:10px;color:#9099b0;margin-top:2px'>{role.upper()}</div>
    </div>""", unsafe_allow_html=True)

    # ── role-based nav ──────────────────────────────────────────────────────
    allowed_pages = get_allowed_pages(role)
    page_icons_map = {
        "Dashboard":          "speedometer2",
        "Upload JD":          "file-earmark-text",
        "Upload Resumes":     "people",
        "Screen & Match":     "search",
        "Schedule & Email":   "envelope",
        "Interview":          "camera-video",
        "Feedback & Decision":"check-circle",
        "Analytics":          "bar-chart",
        "Human Review":       "person-check",
        "Settings":           "gear",
    }
    nav_icons = [page_icons_map.get(p, "circle") for p in allowed_pages]

    page = option_menu(
        menu_title=None,
        options=allowed_pages,
        icons=nav_icons,
        default_index=0,
        styles={
            "container":         {"background-color": "#1a1d2e"},
            "icon":              {"color": user_color, "font-size": "14px"},
            "nav-link":          {"font-size": "13px", "color": "#9099b0", "padding": "8px 16px"},
            "nav-link-selected": {"background-color": "#2d3250", "color": "#e0e0e0"},
        },
    )

    st.markdown("---")
    st.markdown(f"""
    <div style='font-size:11px;color:#555;padding:0 8px'>
    <b style='color:#7F77DD'>Live Status</b><br>
    Resumes in RAG : <b style='color:#1D9E75'>{resume_count()}</b><br>
    JDs stored     : <b style='color:#1D9E75'>{jd_count()}</b><br>
    Matches run    : <b style='color:#1D9E75'>{len(st.session_state.all_match_history)}</b><br>
    Review queue   : <b style='color:#EF9F27'>{len(st.session_state.human_review_queue)}</b><br>
    Model          : <b style='color:#7F77DD;font-size:10px'>{GROQ_MODEL}</b>
    </div>""", unsafe_allow_html=True)

    st.markdown("")
    if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
        # clear only auth keys, keep RAG data
        for k in ["logged_in","username","role","user_name","user_color","user_icon"]:
            st.session_state[k] = DEFAULTS.get(k, "")
        st.session_state.logged_in = False
        st.rerun()

    if not GROQ_API_KEY:
        st.error("⚠️ GROQ_API_KEY missing in .env")


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    st.title("🧠 HireIntel AI — Dashboard")
    st.caption(f"{COMPANY_NAME}  ·  Model: {GROQ_MODEL}")
    show_notifs()

    total = len(st.session_state.all_match_history)
    sl    = sum(1 for r in st.session_state.all_match_history if r.get("shortlist"))
    avg   = (sum(r.get("overall_fit_score", 0) for r in st.session_state.all_match_history) / total
             if total else 0)

    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        (c1, resume_count(), "Resumes in RAG",    "#7F77DD"),
        (c2, sl,             "Shortlisted",        "#1D9E75"),
        (c3, f"{avg:.1f}%",  "Avg Fit Score",      "#EF9F27"),
        (c4, len(st.session_state.human_review_queue), "Pending Review", "#D85A30"),
    ]
    for col, val, lbl, clr in metrics:
        with col:
            st.markdown(
                f'<div class="mcard"><div class="mval" style="color:{clr}">{val}</div>'
                f'<div class="mlbl">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    cl, cr = st.columns([2, 1])

    with cl:
        st.subheader("⚡ 12 Active Agents")
        agents = [
            ("🎯","Manager Agent",    "Orchestrating","#7F77DD"),
            ("📄","JD Analyzer",      "Ready",        "#1D9E75"),
            ("🔍","Skill Matcher",    "Ready",        "#1D9E75"),
            ("❓","Q Generator",      "Ready",        "#378ADD"),
            ("📋","Rubric Agent",     "Always On",    "#EF9F27"),
            ("🤝","Evaluator",        "Ready",        "#D85A30"),
            ("⚡","Real-Time Assist", "Always On",    "#EF9F27"),
            ("💬","Communication",    "Always On",    "#D4537E"),
            ("💾","Knowledge Mgmt",   "Always On",    "#EF9F27"),
            ("📈","Trend Analysis",   "Always On",    "#1D9E75"),
            ("👥","Collaboration",    "Always On",    "#7F77DD"),
            ("📊","Feedback Analyzer","Ready",        "#378ADD"),
        ]
        for row in [agents[i:i+4] for i in range(0, 12, 4)]:
            cols = st.columns(4)
            for j, (icon, name, status, color) in enumerate(row):
                with cols[j]:
                    st.markdown(
                        f'<div class="rcard" style="text-align:center">'
                        f'<div style="font-size:20px">{icon}</div>'
                        f'<div style="font-size:11px;font-weight:500;color:#e0e0e0">{name}</div>'
                        f'<div style="font-size:10px;color:{color};margin-top:2px">● {status}</div>'
                        f'</div>', unsafe_allow_html=True)

    with cr:
        st.subheader("📋 Recent Matches")
        if st.session_state.all_match_history:
            for r in st.session_state.all_match_history[-6:][::-1]:
                sv  = r.get("overall_fit_score", 0)
                col = score_color(sv)
                st.markdown(
                    f'<div class="rcard" style="display:flex;justify-content:space-between;align-items:center">'
                    f'<div><div style="font-size:13px;color:#e0e0e0;font-weight:500">{r.get("candidate_name","?")}</div>'
                    f'<div style="font-size:11px;color:#9099b0">{r.get("recommendation","")}</div></div>'
                    f'<div style="font-size:18px;font-weight:600;color:{col}">{sv}%</div></div>',
                    unsafe_allow_html=True)
        else:
            st.info("No matches yet. Upload a JD and resumes to start.")

    if st.session_state.all_match_history:
        st.markdown("---")
        fig = px.histogram(
            x=[r.get("overall_fit_score", 0) for r in st.session_state.all_match_history],
            nbins=10, color_discrete_sequence=["#7F77DD"])
        fig.update_layout(height=220, margin=dict(t=10, b=20, l=20, r=20),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis_title="Fit Score (%)", yaxis_title="Count",
                          font=dict(color="#9099b0"))
        st.plotly_chart(fig, use_container_width=True, key="dash_histogram")
# UPLOAD JD  — FIX 1 (Excel) + FIX 4 (reuse stored JDs)
# ════════════════════════════════════════════════════════════════════════════
elif page == "Upload JD":
    st.title("📄 Job Description Analyzer")
    st.caption("Supports: Paste · PDF · DOCX · TXT · Excel  |  Agents: JD Analyzer → Rubric")

    # ── Reuse stored JD ──
    stored_jds = get_all_jds()
    if stored_jds:
        with st.expander(f"📂 Previously stored JDs  ({len(stored_jds)} in knowledge base)  — click to reuse"):
            st.markdown(
                '<div style="background:#2a2010;border:1px solid #EF9F27;border-radius:6px;'
                'padding:8px 14px;font-size:12px;color:#EF9F27;margin-bottom:10px">'
                '⚠️ Stored JDs are <b>NOT loaded by default</b>. '
                'Select one below and click <b>Load & Re-analyze</b> to use it.'
                '</div>', unsafe_allow_html=True)

            # FIX 5: build rich dropdown labels showing Client | JD Name | SR#
            def _jd_label(j):
                m   = j["metadata"]
                parts = []
                if m.get("client_name"): parts.append(m["client_name"])
                if m.get("jd_name"):     parts.append(m["jd_name"])
                elif m.get("role_title"):parts.append(m["role_title"])
                elif m.get("title"):     parts.append(m["title"])
                if m.get("sr_number"):   parts.append(f"SR#{m['sr_number']}")
                return " | ".join(parts) if parts else m.get("title","Untitled")

            jd_labels = [_jd_label(j) for j in stored_jds]

            sel_label = st.selectbox(
                "Select stored JD  (Client | JD Name | SR Number):",
                jd_labels, key="sjd_sel")

            # show metadata chips for selected JD
            sel_jd_obj = stored_jds[jd_labels.index(sel_label)]
            sm = sel_jd_obj["metadata"]
            chips = ""
            if sm.get("client_name"):
                chips += (f'<span style="background:#2d1f5e;color:#AFA9EC;padding:2px 10px;'
                          f'border-radius:20px;font-size:11px;margin-right:6px">'
                          f'🏢 {sm["client_name"]}</span>')
            if sm.get("jd_name") or sm.get("role_title"):
                chips += (f'<span style="background:#1a2a20;color:#5DCAA5;padding:2px 10px;'
                          f'border-radius:20px;font-size:11px;margin-right:6px">'
                          f'💼 {sm.get("jd_name") or sm.get("role_title","")}</span>')
            if sm.get("sr_number"):
                chips += (f'<span style="background:#2a2010;color:#EF9F27;padding:2px 10px;'
                          f'border-radius:20px;font-size:11px;margin-right:6px">'
                          f'🔢 SR#{sm["sr_number"]}</span>')
            if chips:
                st.markdown(chips, unsafe_allow_html=True)
                st.markdown("")

            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button("⬆️ Load & Re-analyze", type="primary"):
                    sj = stored_jds[jd_labels.index(sel_label)]
                    st.session_state.jd_text = sj["text"]
                    with st.spinner("Re-analyzing JD..."):
                        st.session_state.jd_analysis = analyze_jd(sj["text"])
                        st.session_state.rubric = generate_rubric(st.session_state.jd_analysis)
                    for k in ["match_results","selected_candidate","questions",
                              "interview_answers","feedback_analysis","final_decision"]:
                        st.session_state[k] = [] if k in ["match_results","interview_answers"] else None
                    st.session_state.excel_question_bank = []
                    st.session_state.excel_jd_criteria   = {}
                    notify(f"✅ Loaded JD: {sel_label}", "success")
                    st.rerun()
            with col_b:
                if st.button("🗑️ Delete this JD from knowledge base", key="del_jd"):
                    sj = stored_jds[jd_labels.index(sel_label)]
                    delete_jd(sj["id"])
                    notify(f"🗑️ Deleted JD: {sel_label}", "warning")
                    st.rerun()

    # ── Input tabs ──
    jd_input = ""
    t1, t2, t3 = st.tabs(["✏️ Paste / Type", "📁 Upload PDF / DOCX / TXT", "📊 Upload Excel"])

    with t1:
        jd_input = st.text_area(
            "Paste Job Description here", height=280,
            value=st.session_state.jd_text,
            placeholder="Paste the full JD text here...")

    with t2:
        jf = st.file_uploader("Upload JD file", type=["txt", "pdf", "docx"])
        if jf:
            with tempfile.NamedTemporaryFile(delete=False,
                    suffix=os.path.splitext(jf.name)[1]) as tmp:
                tmp.write(jf.read())
                jd_input = extract_text(tmp.name)
            st.success(f"✅ Loaded: {jf.name}")
            st.text_area("Preview", jd_input[:700] + "...", height=120, disabled=True)

    with t3:
        st.info(
            "**Sheet 1** — JD criteria (must-have skills, good-to-have, experience, role etc.)  \n"
            "**Sheet 2+** — Interview questions captured from past candidates "
            "→ auto-loaded into the Interview section as your question bank."
        )
        xf = st.file_uploader("Upload JD Excel file", type=["xlsx", "xls"])
        if xf:
            with tempfile.NamedTemporaryFile(delete=False,
                    suffix=os.path.splitext(xf.name)[1]) as tmp:
                tmp.write(xf.read())
                tmp_path = tmp.name

            parsed = parse_excel_jd(tmp_path)

            if "error" in parsed:
                st.error(f"❌ {parsed['error']}")
                if "pip install" in parsed["error"]:
                    st.code(parsed["error"].split("\n")[1])
            else:
                jd_input = parsed["jd_text"]
                st.session_state.excel_question_bank = parsed.get("question_bank", [])
                st.session_state.excel_jd_criteria   = parsed.get("jd_criteria", {})

                # summary
                col_a, col_b = st.columns(2)
                with col_a:
                    st.success(f"✅ Loaded: {xf.name}")
                    st.markdown(f"**Sheets found:** {parsed.get('sheet_count', 1)}")
                    st.markdown(f"**Questions extracted:** {parsed.get('q_count', 0)} "
                                f"from sheets 2+")
                with col_b:
                    crit = parsed.get("jd_criteria", {})
                    if crit.get("role_title"):
                        st.markdown(f"**Role:** {crit['role_title']}")
                    if crit.get("experience"):
                        st.markdown(f"**Experience:** {crit['experience']}")
                    if crit.get("must_have"):
                        st.markdown(f"**Must Have:** {', '.join(crit['must_have'][:5])}")
                    if crit.get("good_to_have"):
                        st.markdown(f"**Good to Have:** {', '.join(crit['good_to_have'][:5])}")

                # sheet previews
                for sheet_name, sheet_text in parsed.get("raw_sheets", {}).items():
                    with st.expander(f"📄 Preview: {sheet_name}"):
                        st.text(sheet_text[:600] + ("..." if len(sheet_text) > 600 else ""))

                # question bank preview
                qb = parsed.get("question_bank", [])
                if qb:
                    with st.expander(f"❓ Question Bank from Excel ({len(qb)} questions) — will auto-load in Interview"):
                        for cat in ["Conceptual", "Coding", "Scenario"]:
                            cat_qs = [q for q in qb if q["category"] == cat]
                            if cat_qs:
                                st.markdown(f"**{cat} ({len(cat_qs)})**")
                                for i, q in enumerate(cat_qs[:5]):
                                    st.markdown(
                                        f"&nbsp;&nbsp;{i+1}. {q['question'][:120]}"
                                        f"{'...' if len(q['question']) > 120 else ''}",
                                        unsafe_allow_html=True)
                                if len(cat_qs) > 5:
                                    st.caption(f"  ...and {len(cat_qs)-5} more")
                else:
                    st.info("No questions found in sheets 2+. "
                            "Questions will be AI-generated in the Interview section.")

    st.markdown("---")
    st.markdown("#### 📌 JD Reference Details *(optional but recommended)*")
    st.caption("These help identify JDs in the knowledge base dropdown.")
    jd_meta_c1, jd_meta_c2, jd_meta_c3 = st.columns(3)
    with jd_meta_c1:
        jd_client_name = st.text_input("Client Name",
                                        key="jd_client_name",
                                        placeholder="e.g. Accenture, TCS, Infosys")
    with jd_meta_c2:
        jd_name = st.text_input("JD Name / Role",
                                 key="jd_name_field",
                                 placeholder="e.g. Senior Python Developer")
    with jd_meta_c3:
        jd_sr_number = st.text_input("SR Number",
                                      key="jd_sr_number",
                                      placeholder="e.g. SR-2024-0042")

    if st.button("🔍 Analyze JD", type="primary", use_container_width=True):
        txt = jd_input.strip() or st.session_state.jd_text
        if not txt:
            st.error("Please provide a JD first.")
        else:
            with st.spinner("🤖 JD Analyzer Agent working..."):
                result = analyze_jd(txt)
            if result.get("error") == "parse_failed":
                st.error("Parse failed. Check your GROQ_API_KEY in .env")
            else:
                st.session_state.jd_text     = txt
                st.session_state.jd_analysis = result
                with st.spinner("📋 Rubric Agent creating scoring guide..."):
                    st.session_state.rubric = generate_rubric(result)

                # Build rich display title for dropdown
                role_title = result.get("role_title", "JD")
                display_parts = []
                if jd_client_name.strip(): display_parts.append(jd_client_name.strip())
                if jd_name.strip():        display_parts.append(jd_name.strip())
                elif role_title:           display_parts.append(role_title)
                if jd_sr_number.strip():   display_parts.append(f"SR#{jd_sr_number.strip()}")
                display_title = " | ".join(display_parts) if display_parts else role_title

                upsert_jd(display_title, txt, extra_meta={
                    "client_name": jd_client_name.strip(),
                    "jd_name":     jd_name.strip() or role_title,
                    "sr_number":   jd_sr_number.strip(),
                    "role_title":  role_title,
                })
                # store meta in jd_analysis for display
                result["_client_name"] = jd_client_name.strip()
                result["_sr_number"]   = jd_sr_number.strip()
                result["_display_title"] = display_title

                for k in ["match_results","selected_candidate","questions",
                          "interview_answers","feedback_analysis","final_decision"]:
                    st.session_state[k] = [] if k in ["match_results","interview_answers"] else None
                st.session_state.excel_question_bank = []
                st.session_state.excel_jd_criteria   = {}
                notify(f"✅ JD analyzed: {display_title}", "success")
                st.rerun()

    # ── Results ──
    if st.session_state.jd_analysis:
        jd = st.session_state.jd_analysis
        st.markdown("---")
        st.subheader(f"✅ {jd.get('role_title','N/A')}")
        st.info(f"📝 {jd.get('jd_summary','')}")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🔑 Primary Skills**")
            for s in jd.get("primary_skills", []):
                st.markdown(f'<span class="pill" style="background:#2d1f5e;color:#AFA9EC">{s}</span>',
                            unsafe_allow_html=True)
        with c2:
            st.markdown("**📌 Secondary Skills**")
            for s in jd.get("secondary_skills", []):
                st.markdown(f'<span class="pill" style="background:#1a2a20;color:#5DCAA5">{s}</span>',
                            unsafe_allow_html=True)
        with c3:
            st.markdown("**✅ Must Have**")
            for s in jd.get("must_have", []):
                st.markdown(f'<span class="pill" style="background:#2a2010;color:#EF9F27">{s}</span>',
                            unsafe_allow_html=True)

        st.markdown(f"**Domain:** {jd.get('domain','N/A')}  |  **Experience:** {jd.get('experience_years','N/A')}")
        # show reference metadata if available
        ref_parts = []
        if jd.get("_client_name"): ref_parts.append(f"🏢 Client: **{jd['_client_name']}**")
        if jd.get("_sr_number"):   ref_parts.append(f"🔢 SR#: **{jd['_sr_number']}**")
        if ref_parts:
            st.markdown("  |  ".join(ref_parts))

        if st.session_state.rubric:
            with st.expander("📋 View Evaluation Rubric"):
                rb   = st.session_state.rubric
                dims = rb.get("rubric_dimensions", [])
                st.markdown(f"**Pass Threshold:** {rb.get('minimum_pass_score', 60)}%")
                if dims:
                    st.dataframe(pd.DataFrame([{
                        "Dimension": d.get("dimension",""),
                        "Weight %":  d.get("weight_percent",""),
                        "Score 5":   d.get("score_5_desc",""),
                        "Score 3":   d.get("score_3_desc",""),
                        "Score 1":   d.get("score_1_desc",""),
                    } for d in dims]), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# UPLOAD RESUMES
# ════════════════════════════════════════════════════════════════════════════
elif page == "Upload Resumes":
    st.title("👥 Resume Upload & Knowledge Base")
    st.caption("Step 2 — Upload new resumes first, then select from knowledge base to screen together")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 1 — UPLOAD NEW RESUMES  (shown first per Enhancement 1)
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("⬆️ Step 2a — Upload New Resumes")
    st.markdown("Upload PDF, DOCX, or TXT files. They are stored in the knowledge base and "
                "auto-selected for screening.")

    t1, t2 = st.tabs(["📁 Upload Files", "📂 Load from Folder Path"])

    newly_stored = []   # names of resumes stored in this action

    with t1:
        st.markdown("**Supported:** PDF · DOCX · DOC · TXT  ·  Multiple files allowed")
        uploaded = st.file_uploader(
            "Select resume files",
            type=["pdf","docx","doc","txt"],
            accept_multiple_files=True,
            key="resume_uploader",
        )
        if uploaded and st.button("⬆️ Store in Knowledge Base",
                                   type="primary", use_container_width=True):
            prog = st.progress(0)
            new_list, dup_list = [], []
            for i, f in enumerate(uploaded):
                with tempfile.NamedTemporaryFile(
                        delete=False, suffix=os.path.splitext(f.name)[1]) as tmp:
                    tmp.write(f.read())
                    text = extract_text(tmp.name)
                name   = nice_name(f.name)
                result = upsert_resume(f.name, text, {"candidate_name": name})
                if result["duplicate"]:
                    dup_list.append(name)
                    # duplicates are NOT auto-selected — user already saw them before
                else:
                    new_list.append(name)
                    # FIX 1: ONLY newly stored resumes get auto-selected
                    st.session_state.selected_resume_ids.add(result["id"])
                st.session_state.upload_log.append(result)
                prog.progress((i + 1) / len(uploaded))

            if new_list:
                st.success(f"✅ {len(new_list)} new resume(s) stored & auto-selected for screening: "
                           f"{', '.join(new_list)}")
            if dup_list:
                st.warning(f"⚠️ {len(dup_list)} duplicate(s) already in knowledge base — "
                           f"NOT auto-selected (select manually below if needed): "
                           f"{', '.join(dup_list)}")
            notify(f"Upload: {len(new_list)} new auto-selected, {len(dup_list)} duplicates", "info")
            st.rerun()

    with t2:
        st.info("Enter the full folder path on your machine containing resume files.")
        folder_path = st.text_input(
            "📂 Folder path",
            placeholder=r"e.g. C:\Users\YourName\Resumes  or  /home/user/resumes")
        if st.button("📂 Load from Folder", type="primary", use_container_width=True):
            if not folder_path:
                st.error("Enter a folder path.")
            elif not os.path.isdir(folder_path):
                st.error(f"Folder not found: {folder_path}")
            else:
                with st.spinner("Reading files..."):
                    resumes = load_resumes_from_folder(folder_path)
                if not resumes:
                    st.warning("No supported files found (PDF, DOCX, TXT).")
                else:
                    prog = st.progress(0)
                    new_list, dup_list = [], []
                    for i, r in enumerate(resumes):
                        result = upsert_resume(
                            r["filename"], r["text"], {"candidate_name": r["name"]})
                        if result["duplicate"]:
                            dup_list.append(r["name"])
                            # FIX 1: duplicates NOT auto-selected
                        else:
                            new_list.append(r["name"])
                            # FIX 1: only new ones auto-selected
                            st.session_state.selected_resume_ids.add(result["id"])
                        prog.progress((i + 1) / len(resumes))
                    if new_list:
                        st.success(f"✅ {len(new_list)} new resume(s) stored & auto-selected.")
                    if dup_list:
                        st.warning(f"⚠️ {len(dup_list)} duplicates already in DB — "
                                   f"NOT auto-selected: {', '.join(dup_list)}")
                    notify(f"Folder: {len(new_list)} new, {len(dup_list)} duplicates", "info")
                    st.rerun()

    # upload history
    if st.session_state.upload_log:
        with st.expander("📋 Upload history (this session)"):
            rows = [{"Filename": r.get("filename",""),
                     "Status": "⚠️ Duplicate — already in DB" if r.get("duplicate")
                               else "✅ New — stored"}
                    for r in st.session_state.upload_log]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 2 — KNOWLEDGE BASE: SELECT / DELETE  (Enhancement 1: shown after upload)
    # ─────────────────────────────────────────────────────────────────────────
    all_res   = get_all_resumes()
    res_by_id = {r["id"]: r for r in all_res}

    st.subheader(f"📂 Step 2b — Select from Knowledge Base  ({len(all_res)} stored)")
    st.markdown(
        "**Newly uploaded resumes are auto-selected** (green). "
        "**Existing resumes in the knowledge base are unselected by default** — "
        "tick the ones you want to include in screening.")

    if all_res:
        h1, h2, h3, h4 = st.columns([3, 1, 1, 1])
        with h1:
            sel_count = len(st.session_state.selected_resume_ids)
            st.markdown(
                f'<div style="background:#1e2235;border:1px solid #2d3250;'
                f'border-radius:8px;padding:10px 16px;font-size:13px;color:#e0e0e0">'
                f'📦 <b>{len(all_res)}</b> in knowledge base &nbsp;|&nbsp; '
                f'<span style="color:#1D9E75"><b>{sel_count}</b> selected</span>'
                f'</div>', unsafe_allow_html=True)
        with h2:
            if st.button("✅ Select All", use_container_width=True, key="selall"):
                st.session_state.selected_resume_ids = {r["id"] for r in all_res}
                st.rerun()
        with h3:
            if st.button("☐ Clear All", use_container_width=True, key="clrall"):
                st.session_state.selected_resume_ids = set()
                st.rerun()
        with h4:
            if st.button("🗑️ Delete ALL", use_container_width=True, key="delall",
                         help="Remove ALL resumes from knowledge base permanently"):
                for r in all_res:
                    delete_resume(r["id"])
                st.session_state.selected_resume_ids = set()
                notify("🗑️ All resumes deleted", "warning")
                st.rerun()

        cols = st.columns(3)
        for i, r in enumerate(all_res):
            with cols[i % 3]:
                name   = r["metadata"].get("candidate_name",
                          nice_name(r["metadata"].get("filename","?")))
                fname  = r["metadata"].get("filename","")
                cid    = r["id"]
                is_sel = cid in st.session_state.selected_resume_ids
                border = "#1D9E75" if is_sel else "#2d3250"
                bg     = "#1a2a20" if is_sel else "#1e2235"
                tick   = "✅" if is_sel else "⬜"

                st.markdown(
                    f'<div style="background:{bg};border:1px solid {border};'
                    f'border-radius:8px;padding:10px 12px;margin-bottom:6px">'
                    f'<div style="font-size:13px;font-weight:500;color:#e0e0e0">'
                    f'{tick} 👤 {name}</div>'
                    f'<div style="font-size:10px;color:#555;margin-top:2px">{fname}</div>'
                    f'<div style="font-size:11px;color:#7F77DD;margin-top:3px">'
                    f'{len(r["text"])} chars</div></div>',
                    unsafe_allow_html=True)

                ba, bb = st.columns(2)
                with ba:
                    lbl = "☐ Deselect" if is_sel else "☑ Select"
                    if st.button(lbl, key=f"sel_{cid}", use_container_width=True):
                        if is_sel:
                            st.session_state.selected_resume_ids.discard(cid)
                        else:
                            st.session_state.selected_resume_ids.add(cid)
                        st.rerun()
                with bb:
                    if st.button("🗑️ Delete", key=f"del_{cid}",
                                 use_container_width=True):
                        delete_resume(cid)
                        st.session_state.selected_resume_ids.discard(cid)
                        notify(f"🗑️ Deleted: {name}", "warning")
                        st.rerun()
    else:
        st.info("Knowledge base is empty. Upload resumes above to get started.")

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 3 — PROCEED TO SCREEN & MATCH  (Enhancement 2)
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("🚀 Step 2c — Proceed to Screen & Match")

    selected_ids = st.session_state.selected_resume_ids
    all_res_now  = get_all_resumes()           # refresh after any deletes
    res_by_id2   = {r["id"]: r for r in all_res_now}
    selected_res = [res_by_id2[cid] for cid in selected_ids if cid in res_by_id2]
    active_jd    = st.session_state.jd_analysis

    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        clr = "#1D9E75" if selected_res else "#D85A30"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr}">'
            f'<div style="font-size:22px;font-weight:700;color:{clr}">{len(selected_res)}</div>'
            f'<div style="font-size:12px;color:#9099b0">Resumes Selected</div></div>',
            unsafe_allow_html=True)
    with cs2:
        clr2  = "#1D9E75" if active_jd else "#D85A30"
        jdnm  = active_jd.get("role_title","None") if active_jd else "None"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr2}">'
            f'<div style="font-size:13px;font-weight:600;color:{clr2}">{jdnm}</div>'
            f'<div style="font-size:12px;color:#9099b0">Active JD</div></div>',
            unsafe_allow_html=True)
    with cs3:
        ready = bool(selected_res) and active_jd is not None
        clr3  = "#1D9E75" if ready else "#D85A30"
        lbl3  = "✅ Ready to Screen" if ready else "❌ Not Ready"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr3}">'
            f'<div style="font-size:14px;font-weight:600;color:{clr3}">{lbl3}</div>'
            f'<div style="font-size:12px;color:#9099b0">Status</div></div>',
            unsafe_allow_html=True)

    if not active_jd:
        st.warning("⚠️ No JD analyzed yet. Go to **Upload JD** first, then come back here.")
    if not selected_res:
        st.warning("⚠️ No resumes selected. Upload new ones or tick existing ones above.")

    if selected_res and active_jd:
        names_sel = [
            r["metadata"].get("candidate_name",
            nice_name(r["metadata"].get("filename","?")))
            for r in selected_res
        ]
        st.success(
            f"✅ **{len(selected_res)} resume(s)** ready to screen against "
            f"**{active_jd.get('role_title','')}**")
        st.markdown("  ·  ".join(f"`{n}`" for n in names_sel))

        if st.button(
            f"➡️ Proceed to Screen & Match with {len(selected_res)} resume(s)",
            type="primary", use_container_width=True,
        ):
            st.session_state.resumes_to_screen = list(selected_ids)
            notify(
                f"✅ {len(selected_res)} resume(s) queued. "
                "Go to Screen & Match in the sidebar.", "success")
            st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# SCREEN & MATCH
# ════════════════════════════════════════════════════════════════════════════
elif page == "Screen & Match":
    st.title("🔍 AI Screening & Skill Matching")
    st.caption("Agents: Skill Matcher → RAG Engine → Knowledge Management")

    if not st.session_state.jd_analysis:
        st.warning("⚠️ Please analyze a JD first (Upload JD page).")
        st.stop()

    jd = st.session_state.jd_analysis
    rc = resume_count()

    if rc == 0:
        st.error("No resumes in knowledge base. Upload resumes first.")
        st.stop()

    # ── FIX: detect resumes coming from Upload Resumes page ──────────────────
    queued_ids   = st.session_state.get("resumes_to_screen", [])
    all_stored   = get_all_resumes()
    id_to_resume = {r["id"]: r for r in all_stored}

    # Build the list of resumes to screen
    if queued_ids:
        # user came from Upload Resumes with a specific selection
        selected_resumes = [id_to_resume[cid] for cid in queued_ids if cid in id_to_resume]
        screen_mode = "selected"
    else:
        # fallback: all resumes in RAG
        selected_resumes = all_stored
        screen_mode = "all"

    # ── top info bar ──────────────────────────────────────────────────────────
    i1, i2, i3 = st.columns(3)
    with i1:
        st.markdown(
            f'<div class="rcard" style="text-align:center">'
            f'<div style="font-size:20px;font-weight:600;color:#7F77DD">'
            f'{jd.get("role_title","N/A")}</div>'
            f'<div style="font-size:11px;color:#9099b0">Active JD</div></div>',
            unsafe_allow_html=True)
    with i2:
        clr = "#1D9E75" if len(selected_resumes) > 0 else "#D85A30"
        lbl = (f"{len(selected_resumes)} selected from Upload Resumes"
               if screen_mode == "selected"
               else f"{len(selected_resumes)} total in knowledge base")
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr}">'
            f'<div style="font-size:20px;font-weight:600;color:{clr}">'
            f'{len(selected_resumes)}</div>'
            f'<div style="font-size:11px;color:#9099b0">{lbl}</div></div>',
            unsafe_allow_html=True)
    with i3:
        exp = jd.get("experience_years", "N/A")
        st.markdown(
            f'<div class="rcard" style="text-align:center">'
            f'<div style="font-size:16px;font-weight:600;color:#EF9F27">{exp}</div>'
            f'<div style="font-size:11px;color:#9099b0">Experience Required</div></div>',
            unsafe_allow_html=True)

    # ── if came with selection, show who is queued ────────────────────────────
    if screen_mode == "selected" and selected_resumes:
        names_q = [r["metadata"].get("candidate_name",
                   nice_name(r["metadata"].get("filename","?")))
                   for r in selected_resumes]
        with st.expander(
                f"📋 {len(selected_resumes)} resume(s) queued from Upload Resumes page"):
            cols = st.columns(4)
            for i, nm in enumerate(names_q):
                with cols[i % 4]:
                    st.markdown(
                        f'<div style="background:#1a2a20;border:1px solid #1D9E75;'
                        f'border-radius:6px;padding:6px 10px;margin-bottom:4px;'
                        f'font-size:12px;color:#5DCAA5">✅ {nm}</div>',
                        unsafe_allow_html=True)
        ca, cb = st.columns(2)
        with cb:
            if st.button("🔄 Switch to All Resumes Instead",
                         help="Ignore selection and screen all stored resumes"):
                st.session_state.resumes_to_screen = []
                st.rerun()

    elif screen_mode == "all":
        st.info(
            f"No specific selection found. Screening all **{len(all_stored)}** "
            f"resumes in knowledge base.  "
            f"To screen specific ones, go to **Upload Resumes** → select → Proceed.")

    st.markdown("---")

    # ── screening controls ────────────────────────────────────────────────────
    c1, c2 = st.columns([1, 3])
    with c1:
        threshold = st.slider("Min fit score to shortlist (%)", 40, 90, 65)
        top_n     = st.number_input("Max candidates", 5, 200,
                                     min(50, max(5, len(selected_resumes))))

    with c2:
        btn_label = (
            f"🚀 Screen {len(selected_resumes)} Selected Resume(s)"
            if screen_mode == "selected"
            else f"🚀 Screen All {len(selected_resumes)} Resumes"
        )
        if st.button(btn_label, type="primary", use_container_width=True):
            if not selected_resumes:
                st.error("No resumes to screen.")
                st.stop()

            with st.spinner("RAG Engine ranking resumes..."):
                jd_query = st.session_state.jd_text or jd.get("jd_summary", "")
                if screen_mode == "selected":
                    # Only rank within the selected set
                    rag_results = []
                    from rag.rag_engine import search_resumes_for_jd as _search
                    all_rag = _search(jd_query, top_k=rc)
                    # filter to only selected IDs
                    sel_id_set = set(queued_ids) if queued_ids else {r["id"] for r in all_stored}
                    for rr in all_rag:
                        fname  = rr["metadata"].get("filename","")
                        rid    = rr["metadata"].get("id",
                                 hashlib.md5(fname.encode()).hexdigest()
                                 if fname else "")
                        # match by filename since RAG doesn't store id in metadata
                        matched = next(
                            (sr for sr in selected_resumes
                             if sr["metadata"].get("filename","") == fname), None)
                        if matched:
                            rr["text"] = matched["text"]
                            rag_results.append(rr)
                    # also add any selected resumes not found by RAG search
                    found_fnames = {r["metadata"].get("filename","") for r in rag_results}
                    for sr in selected_resumes:
                        if sr["metadata"].get("filename","") not in found_fnames:
                            rag_results.append({
                                "text":     sr["text"],
                                "metadata": sr["metadata"],
                                "score":    50.0,
                            })
                else:
                    rag_results = search_resumes_for_jd(jd_query, top_k=int(top_n))

            if not rag_results:
                st.error("No matches found.")
                st.stop()

            results  = []
            prog     = st.progress(0)
            status_p = st.empty()
            total_r  = len(rag_results)

            for i, r in enumerate(rag_results[:int(top_n)]):
                name = r["metadata"].get("candidate_name",
                        nice_name(r["metadata"].get("filename", "Unknown")))
                status_p.text(
                    f"Skill Matcher Agent: evaluating {name} ({i+1}/{total_r})...")
                m = match_candidate(r["text"], jd, name, r.get("score", 50.0))
                m["filename"]    = r["metadata"].get("filename", "")
                m["resume_text"] = r["text"]
                # ensure score is int
                try:
                    m["overall_fit_score"] = int(float(m.get("overall_fit_score", 0)))
                except Exception:
                    m["overall_fit_score"] = 0
                results.append(m)
                prog.progress((i + 1) / total_r)

            status_p.empty()
            prog.empty()

            # apply threshold
            for r in results:
                try:
                    r["shortlist"] = int(float(r.get("overall_fit_score", 0))) >= threshold
                except Exception:
                    r["shortlist"] = False

            # sort: shortlisted first, then by score desc
            results.sort(key=lambda x: (
                -int(x.get("shortlist", False)),
                -int(float(x.get("overall_fit_score", 0)))
            ))

            # Knowledge agent: find alt JD for non-shortlisted
            for nm in [r for r in results if not r.get("shortlist")][:5]:
                past = search_jds_for_candidate(nm.get("resume_text", ""), top_k=5)
                if past:
                    nm["alternative_jd"] = find_alternative_jd_match(
                        nm.get("resume_text",""), past, nm.get("candidate_name",""))

            st.session_state.match_results   = results
            st.session_state.all_match_history.extend(results)
            # clear the queue after screening
            st.session_state.resumes_to_screen = []

            sl_count = sum(1 for r in results if r.get("shortlist"))
            notify(
                f"✅ Screened {len(results)} resumes — "
                f"{sl_count} shortlisted, "
                f"{len(results)-sl_count} below threshold", "success")
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTS — FIX: clean, reliable shortlist display
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.match_results:
        results = st.session_state.match_results
        sl      = [r for r in results if r.get("shortlist") is True]
        oth     = [r for r in results if not r.get("shortlist")]

        # ── summary scorecard ─────────────────────────────────────────────────
        st.markdown("---")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.markdown(
                f'<div class="rcard" style="text-align:center">'
                f'<div style="font-size:24px;font-weight:700;color:#e0e0e0">{len(results)}</div>'
                f'<div style="font-size:11px;color:#9099b0">Total Screened</div></div>',
                unsafe_allow_html=True)
        with s2:
            st.markdown(
                f'<div class="rcard" style="text-align:center;border-color:#1D9E75">'
                f'<div style="font-size:24px;font-weight:700;color:#1D9E75">{len(sl)}</div>'
                f'<div style="font-size:11px;color:#9099b0">Shortlisted</div></div>',
                unsafe_allow_html=True)
        with s3:
            st.markdown(
                f'<div class="rcard" style="text-align:center;border-color:#D85A30">'
                f'<div style="font-size:24px;font-weight:700;color:#D85A30">{len(oth)}</div>'
                f'<div style="font-size:11px;color:#9099b0">Below Threshold</div></div>',
                unsafe_allow_html=True)
        with s4:
            avg = (sum(int(float(r.get("overall_fit_score",0))) for r in results)
                   / len(results)) if results else 0
            st.markdown(
                f'<div class="rcard" style="text-align:center;border-color:#7F77DD">'
                f'<div style="font-size:24px;font-weight:700;color:#7F77DD">{avg:.0f}%</div>'
                f'<div style="font-size:11px;color:#9099b0">Avg Fit Score</div></div>',
                unsafe_allow_html=True)

        # ── SHORTLISTED ───────────────────────────────────────────────────────
        if sl:
            st.markdown(f"### ✅ Shortlisted Candidates — {len(sl)}")
            for ridx, r in enumerate(sl):
                sv   = int(float(r.get("overall_fit_score", 0)))
                name = r.get("candidate_name", "Unknown")
                rec  = r.get("recommendation", "")
                col  = score_color(sv)

                with st.expander(
                        f"👤  {name}   —   {sv}%   |   {rec}",
                        expanded=False):

                    row1, row2, row3 = st.columns([1, 1, 1])

                    with row1:
                        st.plotly_chart(gauge(sv, "Fit Score"),
                                        use_container_width=True,
                                        key=f"gauge_sl_{ridx}_{name}")

                    with row2:
                        st.markdown("##### Skills Assessment")
                        mhm = r.get("must_have_met", [])
                        mhx = r.get("must_have_missing", [])
                        gaps = r.get("skill_gaps", [])

                        if mhm:
                            st.markdown("**✅ Must-Have Met**")
                            for s in mhm:
                                st.markdown(
                                    f'<span class="pill" style="background:#1a2a20;'
                                    f'color:#5DCAA5">✓ {s}</span>',
                                    unsafe_allow_html=True)
                        if mhx:
                            st.markdown("**❌ Missing**")
                            for s in mhx:
                                st.markdown(
                                    f'<span class="pill" style="background:#2a1a1a;'
                                    f'color:#D85A30">✗ {s}</span>',
                                    unsafe_allow_html=True)
                        if gaps:
                            st.markdown("**⚠️ Skill Gaps**")
                            for s in gaps:
                                st.markdown(
                                    f'<span class="pill" style="background:#2a2010;'
                                    f'color:#EF9F27">~ {s}</span>',
                                    unsafe_allow_html=True)

                    with row3:
                        st.markdown("##### Candidate Details")
                        strengths = r.get("strengths", [])
                        if strengths:
                            st.markdown("**💪 Strengths**")
                            for s in strengths:
                                st.markdown(f"• {s}")

                        em  = r.get("candidate_email", "")
                        exp = r.get("years_experience", "N/A")
                        p_m = r.get("primary_skill_match", 0)
                        s_m = r.get("secondary_skill_match", 0)
                        e_m = r.get("experience_match", 0)

                        st.markdown(
                            f"**Email:** {em if em else '⚠️ Not found in resume'}  \n"
                            f"**Experience:** {exp}  \n"
                            f"**Primary skills:** {p_m}%  \n"
                            f"**Secondary skills:** {s_m}%  \n"
                            f"**Exp match:** {e_m}%")

                    st.markdown(f"> 💬 *{r.get('match_reason','')}*")
                    st.markdown("---")

                    btn_col, fake_col, _ = st.columns([1, 1, 1])
                    with btn_col:
                        if st.button("🎯 Select for Interview",
                                     key=f"sel_{ridx}_{name}_{sv}",
                                     type="primary",
                                     use_container_width=True):
                            st.session_state.selected_candidate  = r
                            st.session_state.questions           = None
                            st.session_state.interview_answers   = []
                            st.session_state.feedback_analysis   = None
                            st.session_state.final_decision      = None
                            notify(f"✅ {name} selected for interview", "success")
                            st.rerun()
                    with fake_col:
                        if st.button("🔍 Check Resume Authenticity",
                                     key=f"fake_{ridx}_{name}",
                                     use_container_width=True,
                                     help="AI scans for fake or inflated resume patterns"):
                            with st.spinner(f"Scanning {name}'s resume for authenticity..."):
                                fake_result = detect_fake_resume(
                                    r.get("resume_text",""),
                                    name, jd)
                            st.session_state[f"fake_result_{ridx}"] = fake_result

                    # show fake detection result
                    fake_key = f"fake_result_{ridx}"
                    if st.session_state.get(fake_key):
                        fr = st.session_state[fake_key]
                        risk = fr.get("risk_level","Unknown")
                        score = fr.get("risk_score",0)
                        verdict = fr.get("authenticity_verdict","Unknown")
                        risk_color = {
                            "Low":      "#1D9E75",
                            "Medium":   "#EF9F27",
                            "High":     "#D85A30",
                            "Critical": "#8B0000",
                        }.get(risk, "#9099b0")

                        st.markdown(
                            f'<div style="background:#1a1d2e;border:2px solid {risk_color};'
                            f'border-radius:10px;padding:14px 16px;margin-top:8px">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;margin-bottom:10px">'
                            f'<div style="font-size:13px;font-weight:600;color:{risk_color}">'
                            f'🔍 Resume Authenticity Check</div>'
                            f'<div style="display:flex;gap:10px;align-items:center">'
                            f'<span style="background:{risk_color};color:#fff;padding:3px 12px;'
                            f'border-radius:20px;font-size:12px;font-weight:600">'
                            f'Risk: {risk}</span>'
                            f'<span style="font-size:18px;font-weight:700;color:{risk_color}">'
                            f'{score}/100</span></div></div>'
                            f'<div style="font-size:12px;color:#e0e0e0;margin-bottom:8px">'
                            f'<b>Verdict:</b> {verdict}</div>'
                            f'<div style="font-size:12px;color:#9099b0">{fr.get("summary","")}</div>'
                            f'</div>', unsafe_allow_html=True)

                        # Red flags
                        red_flags = fr.get("red_flags",[])
                        if red_flags:
                            with st.expander(f"🚩 {len(red_flags)} Red Flag(s) Found"):
                                for rf in red_flags:
                                    sev = rf.get("severity","Medium")
                                    sev_col = {"High":"#D85A30","Medium":"#EF9F27",
                                               "Low":"#1D9E75"}.get(sev,"#EF9F27")
                                    st.markdown(
                                        f'<div style="background:#1e2235;border-left:3px solid '
                                        f'{sev_col};padding:6px 12px;border-radius:0 6px 6px 0;'
                                        f'margin-bottom:4px;font-size:12px;color:#e0e0e0">'
                                        f'<span style="color:{sev_col};font-weight:500">'
                                        f'[{sev}]</span> {rf.get("flag","")}</div>',
                                        unsafe_allow_html=True)

                        # What to verify
                        recs = fr.get("recommendations",[])
                        if recs:
                            with st.expander("✅ What to verify in the interview"):
                                for rec in recs:
                                    st.markdown(f"• {rec}")

                        if st.button("✕ Close", key=f"close_fake_{ridx}",
                                     use_container_width=False):
                            del st.session_state[fake_key]
                            st.rerun()

        else:
            st.warning(
                "⚠️ No candidates met the shortlist threshold. "
                "Try lowering the Min fit score slider and re-running.")

        # ── BELOW THRESHOLD ───────────────────────────────────────────────────
        if oth:
            st.markdown(f"### ⚠️ Below Threshold — {len(oth)} candidates")
            for r in oth:
                sv   = int(float(r.get("overall_fit_score", 0)))
                name = r.get("candidate_name", "Unknown")
                alt  = r.get("alternative_jd", {})

                header = f"👤  {name}   —   {sv}%   |   {r.get('recommendation','')}"
                if alt and alt.get("alternative_found"):
                    header += f"   |   🔄 Alt: {alt.get('best_match_role','')}"

                with st.expander(header, expanded=False):
                    st.markdown(
                        f"**Recommendation:** {r.get('recommendation','')}  \n"
                        f"**Skill Gaps:** {', '.join(r.get('skill_gaps',[])) or 'None identified'}  \n"
                        f"**Experience:** {r.get('years_experience','N/A')}")

                    if alt and alt.get("alternative_found"):
                        st.info(
                            f"🔄 **Knowledge Agent:** This candidate may suit "
                            f"**{alt.get('best_match_role','')}** "
                            f"({alt.get('match_score',0)}% match).  \n"
                            f"{alt.get('match_reason','')}")

                    st.markdown(f"> *{r.get('match_reason','')}*")


# ════════════════════════════════════════════════════════════════════════════
# SCHEDULE & EMAIL  — FIX 2 (before Interview)
# ════════════════════════════════════════════════════════════════════════════
elif page == "Schedule & Email":
    st.title("📧 Schedule Interview & Send Emails")
    st.caption("Step 4 of 6 — Pick dates from calendar, choose time slots, send invite to candidate")

    cand = st.session_state.selected_candidate or {}
    jd   = st.session_state.jd_analysis or {}

    if not cand:
        st.warning("⚠️ No candidate selected yet. "
                   "Go to Screen & Match → select a candidate → come back here.")

    t1, t2, t3 = st.tabs(["📨 Interview Invite", "✅ Confirmation", "📋 Email Log"])

    # ── shared helper: format a slot string from date + time ─────────────────
    def fmt_slot(d, t):
        if d and t:
            return f"{d.strftime('%A, %d %B %Y')} at {t.strftime('%I:%M %p')} IST"
        return ""

    with t1:
        st.subheader("Send Interview Invitation")
        st.markdown("Fill in the candidate details and pick **2–3 date/time slots** to offer.")

        # ── candidate info ──
        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            cname  = st.text_input("Candidate Name",  cand.get("candidate_name",""))
        with ci2:
            cemail = st.text_input("Candidate Email",  cand.get("candidate_email",""),
                                    placeholder="candidate@email.com")
        with ci3:
            role   = st.text_input("Role",             jd.get("role_title",""))

        st.markdown("---")
        st.markdown("#### 📅 Interview Slot Options")
        st.caption("Pick at least 2 slots. The candidate will choose their preferred one.")

        from datetime import date, time as dtime, timedelta
        today   = date.today()
        min_day = today + timedelta(days=1)

        # time options — every 30 min from 08:00 to 19:00
        time_options = []
        for h in range(8, 20):
            for m in (0, 30):
                time_options.append(dtime(h, m))
        time_labels  = [t.strftime("%I:%M %p") for t in time_options]
        default_idx1 = time_options.index(dtime(10, 0))
        default_idx2 = time_options.index(dtime(14, 0))
        default_idx3 = time_options.index(dtime(11, 0))

        # ── Slot 1 ──
        st.markdown("**Slot Option 1 ✱**")
        sc1a, sc1b = st.columns(2)
        with sc1a:
            slot1_date = st.date_input("Date", value=min_day,
                                        min_value=min_day, key="s1d",
                                        label_visibility="collapsed")
        with sc1b:
            slot1_time_lbl = st.selectbox("Time", time_labels,
                                           index=default_idx1, key="s1t",
                                           label_visibility="collapsed")
            slot1_time = time_options[time_labels.index(slot1_time_lbl)]
        slot1_str  = fmt_slot(slot1_date, slot1_time)
        if slot1_str:
            st.caption(f"📌 {slot1_str}")

        st.markdown("**Slot Option 2 ✱**")
        sc2a, sc2b = st.columns(2)
        with sc2a:
            slot2_date = st.date_input("Date", value=min_day + timedelta(days=1),
                                        min_value=min_day, key="s2d",
                                        label_visibility="collapsed")
        with sc2b:
            slot2_time_lbl = st.selectbox("Time", time_labels,
                                           index=default_idx2, key="s2t",
                                           label_visibility="collapsed")
            slot2_time = time_options[time_labels.index(slot2_time_lbl)]
        slot2_str  = fmt_slot(slot2_date, slot2_time)
        if slot2_str:
            st.caption(f"📌 {slot2_str}")

        st.markdown("**Slot Option 3 (optional)**")
        add_slot3 = st.checkbox("Add a third slot option", value=False, key="add3")
        slot3_str = ""
        if add_slot3:
            sc3a, sc3b = st.columns(2)
            with sc3a:
                slot3_date = st.date_input("Date", value=min_day + timedelta(days=2),
                                            min_value=min_day, key="s3d",
                                            label_visibility="collapsed")
            with sc3b:
                slot3_time_lbl = st.selectbox("Time", time_labels,
                                               index=default_idx3, key="s3t",
                                               label_visibility="collapsed")
                slot3_time = time_options[time_labels.index(slot3_time_lbl)]
            slot3_str  = fmt_slot(slot3_date, slot3_time)
            if slot3_str:
                st.caption(f"📌 {slot3_str}")

        # ── preview ──
        preview_slots = [s for s in [slot1_str, slot2_str, slot3_str] if s]
        if preview_slots:
            st.markdown("---")
            st.markdown("**📬 Slots that will appear in the email:**")
            for i, s in enumerate(preview_slots, 1):
                st.markdown(
                    f'<div style="background:#1a2a20;border-left:4px solid #1D9E75;'
                    f'border-radius:0 6px 6px 0;padding:8px 14px;margin-bottom:6px;'
                    f'font-size:13px;color:#5DCAA5">'
                    f'<b>Option {i}:</b> {s}</div>',
                    unsafe_allow_html=True)

        inc = st.checkbox("Include JD summary in email", value=True)

        st.markdown("---")
        if st.button("📨 Send Invitation Email", type="primary", use_container_width=True):
            slots = [s for s in [slot1_str, slot2_str, slot3_str] if s]
            if not all([cname, cemail, role]) or len(slots) < 2:
                st.error("Fill Candidate Name, Email, Role and select at least 2 slot dates/times.")
            else:
                with st.spinner("Sending invitation email..."):
                    res = send_interview_invite(
                        cemail, cname, role, slots,
                        jd.get("jd_summary","") if inc else "")
                if res["success"]:
                    st.success(f"✅ Invitation sent to {cemail}")
                    st.session_state.email_log.append({
                        "Type": "Invitation", "To": cemail,
                        "Candidate": cname, "Role": role,
                        "Slots": " | ".join(slots), "Status": "Sent ✅"})
                    notify(f"📧 Invite sent to {cname}", "success")
                else:
                    st.error(f"❌ {res.get('error','')}")
                    st.warning(
                        "Gmail tip: Use an App Password, not your regular password.  \n"
                        "Google Account → Security → 2-Step Verification → App Passwords")

    # ── TAB 2: Confirmation ───────────────────────────────────────────────────
    with t2:
        st.subheader("Send Interview Confirmation")
        st.markdown("Once the candidate replies with their preferred slot, confirm it here.")

        ci1, ci2 = st.columns(2)
        with ci1:
            cn2  = st.text_input("Candidate Name ",  cand.get("candidate_name",""))
            ce2  = st.text_input("Candidate Email ", cand.get("candidate_email",""))
            ro2  = st.text_input("Role ",            jd.get("role_title",""))

        with ci2:
            pan = st.text_input("Panel Members (comma-separated)",
                                 placeholder="Priya Sharma, Rahul Verma")
            mlk = st.text_input("Meeting Link (optional)",
                                 placeholder="https://meet.google.com/...")

        st.markdown("#### 📅 Confirmed Interview Date & Time")
        conf1, conf2 = st.columns(2)
        with conf1:
            from datetime import date as _date, timedelta as _td
            conf_date = st.date_input("Interview Date",
                                       value=date.today() + timedelta(days=1),
                                       min_value=date.today(),
                                       key="conf_date")
        with conf2:
            conf_time_lbl = st.selectbox("Interview Time", time_labels,
                                          index=default_idx1, key="conf_time")
            conf_time_val = time_options[time_labels.index(conf_time_lbl)]

        csl = fmt_slot(conf_date, conf_time_val)
        if csl:
            st.caption(f"📌 Confirmed: **{csl}**")

        if st.button("✅ Send Confirmation Email", type="primary", use_container_width=True):
            panel = [p.strip() for p in pan.split(",") if p.strip()]
            if not all([cn2, ce2, ro2, csl]):
                st.error("Fill all required fields.")
            else:
                with st.spinner("Sending confirmation..."):
                    res = send_confirmation(ce2, cn2, ro2, csl, panel, mlk)
                if res["success"]:
                    st.success(f"✅ Confirmation sent to {ce2}")
                    st.session_state.email_log.append({
                        "Type": "Confirmation", "To": ce2,
                        "Candidate": cn2, "Role": ro2,
                        "Slot": csl, "Status": "Sent ✅"})
                    notify(f"✅ Confirmed {cn2}", "success")
                else:
                    st.error(f"❌ {res.get('error','')}")

    # ── TAB 3: Email Log ──────────────────────────────────────────────────────
    with t3:
        st.subheader("Email Activity Log")
        if st.session_state.email_log:
            st.dataframe(pd.DataFrame(st.session_state.email_log),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No emails sent this session.")


# ════════════════════════════════════════════════════════════════════════════
# INTERVIEW — Redesigned practical UI
# ════════════════════════════════════════════════════════════════════════════
elif page == "Interview":
    st.title("🎥 Interview Panel")
    st.caption("Step 5 of 6  ·  Set up questions before interview  ·  Paste transcript after")

    if not st.session_state.selected_candidate:
        st.warning("⚠️ No candidate selected. Go to Screen & Match first.")
        sl_names = [r.get("candidate_name","?")
                    for r in st.session_state.match_results if r.get("shortlist")]
        if sl_names:
            pick = st.selectbox("Quick-select shortlisted candidate:", sl_names)
            if st.button("Select this candidate"):
                found = [r for r in st.session_state.match_results
                         if r.get("candidate_name") == pick]
                if found:
                    st.session_state.selected_candidate = found[0]
                    st.rerun()
        st.stop()

    cand        = st.session_state.selected_candidate
    jd          = st.session_state.jd_analysis
    resume_text = cand.get("resume_text","")

    # candidate banner
    st.markdown(
        f'<div class="rcard" style="border-color:#7F77DD;margin-bottom:16px">'
        f'<span style="font-size:16px;font-weight:600;color:#e0e0e0">👤 {cand.get("candidate_name","?")}</span>'
        f'&nbsp;&nbsp;<span style="color:#7F77DD;font-size:13px">{jd.get("role_title","N/A") if jd else "N/A"}</span>'
        f'&nbsp;&nbsp;<span style="color:#9099b0;font-size:12px">'
        f'Fit: <b>{cand.get("overall_fit_score",0)}%</b>&nbsp;|&nbsp;'
        f'Email: <b>{cand.get("candidate_email","N/A")}</b></span></div>',
        unsafe_allow_html=True)

    # ── WORKFLOW STEPS ────────────────────────────────────────────────────────
    # Show 3 clear steps so panel knows exactly what to do
    w1, w2, w3 = st.columns(3)
    qs_ready  = st.session_state.questions is not None
    tr_done   = bool(st.session_state.get("transcript_answers"))
    eval_done = len(st.session_state.interview_answers) > 0

    with w1:
        clr = "#1D9E75" if qs_ready else "#7F77DD"
        ico = "✅" if qs_ready else "1️⃣"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr}">'
            f'<div style="font-size:20px">{ico}</div>'
            f'<div style="font-size:13px;font-weight:500;color:#e0e0e0;margin-top:4px">Generate Questions</div>'
            f'<div style="font-size:11px;color:#9099b0">Before the interview</div></div>',
            unsafe_allow_html=True)
    with w2:
        clr = "#1D9E75" if tr_done else "#EF9F27"
        ico = "✅" if tr_done else "2️⃣"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr}">'
            f'<div style="font-size:20px">{ico}</div>'
            f'<div style="font-size:13px;font-weight:500;color:#e0e0e0;margin-top:4px">Paste Transcript</div>'
            f'<div style="font-size:11px;color:#9099b0">After the interview</div></div>',
            unsafe_allow_html=True)
    with w3:
        clr = "#1D9E75" if eval_done else "#9099b0"
        ico = "✅" if eval_done else "3️⃣"
        st.markdown(
            f'<div class="rcard" style="text-align:center;border-color:{clr}">'
            f'<div style="font-size:20px">{ico}</div>'
            f'<div style="font-size:13px;font-weight:500;color:#e0e0e0;margin-top:4px">Get Evaluation</div>'
            f'<div style="font-size:11px;color:#9099b0">AI scores all answers</div></div>',
            unsafe_allow_html=True)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1 — GENERATE QUESTIONS (before the interview)
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander(
            f"{'✅ STEP 1 DONE' if qs_ready else '📝 STEP 1'} — Generate Interview Questions (do this BEFORE the call)",
            expanded=not qs_ready):

        if qs_ready:
            qs = st.session_state.questions
            # build flat list
            all_flat = []
            for q in qs.get("conceptual_questions",   []): all_flat.append({**q,"category":"Conceptual"})
            for q in qs.get("coding_questions",        []): all_flat.append({**q,"category":"Coding"})
            for q in qs.get("scenario_questions",      []): all_flat.append({**q,"category":"Scenario"})
            for q in qs.get("resume_based_questions",  []): all_flat.append({**q,"category":"Resume"})

            c_con = len([q for q in all_flat if q["category"]=="Conceptual"])
            c_cod = len([q for q in all_flat if q["category"]=="Coding"])
            c_sce = len([q for q in all_flat if q["category"]=="Scenario"])
            c_res = len([q for q in all_flat if q["category"]=="Resume"])

            st.success(
                f"✅ {len(all_flat)} questions ready — "
                f"Conceptual: {c_con} · Coding: {c_cod} · Scenario: {c_sce} · Resume: {c_res}")

            # show questions as a printable list for the panel
            cat_colors = {"Conceptual":"#7F77DD","Coding":"#378ADD",
                          "Scenario":"#1D9E75","Resume":"#D4537E"}

            tab_labels = [
                f"💡 Conceptual ({c_con})",
                f"💻 Coding ({c_cod})",
                f"🎭 Scenario ({c_sce})",
                f"📄 Resume ({c_res})",
            ]
            qtabs = st.tabs(tab_labels)
            for cat, qtab in zip(["Conceptual","Coding","Scenario","Resume"], qtabs):
                with qtab:
                    cat_qs = [q for q in all_flat if q["category"]==cat]
                    if not cat_qs:
                        st.info(f"No {cat} questions.")
                        continue

                    # ── Coach tip banner ──────────────────────────────────
                    st.markdown(
                        f'<div style="background:#1e2235;border:1px solid #EF9F27;'
                        f'border-radius:8px;padding:8px 14px;margin-bottom:10px;'
                        f'font-size:12px;color:#EF9F27">'
                        f'💡 <b>Live Interview Coach</b> — Click the '
                        f'<b>⚡ Real-Time Assist</b> button on any question BEFORE asking it. '
                        f'Get what to listen for, red flags, follow-up questions and scoring guide.'
                        f'</div>', unsafe_allow_html=True)

                    for i, q in enumerate(cat_qs):
                        q_global_idx = all_flat.index(q)
                        dc = {"Easy":"#1D9E75","Medium":"#EF9F27","Hard":"#D85A30"}.get(
                             q.get("difficulty","Medium"),"#EF9F27")
                        st.markdown(
                            f'<div style="background:#1e2235;border-left:4px solid '
                            f'{cat_colors[cat]};border-radius:0 8px 8px 0;'
                            f'padding:10px 14px;margin-bottom:6px">'
                            f'<div style="font-size:13px;font-weight:500;color:#e0e0e0">'
                            f'Q{i+1}: {q.get("question","")}</div>'
                            f'<div style="font-size:11px;color:#9099b0;margin-top:3px">'
                            f'Skill: {q.get("skill_tested","")} &nbsp;|&nbsp;'
                            f'<span style="color:{dc}">{q.get("difficulty","")}</span>'
                            f'{"&nbsp;|&nbsp;⏱ "+str(q.get("time_minutes",""))+" min" if q.get("time_minutes") else ""}'
                            f'</div></div>', unsafe_allow_html=True)

                        hint_col, coach_col = st.columns(2)
                        with hint_col:
                            hints = q.get("expected_hints","")
                            if hints:
                                with st.expander(f"💡 Expected Answer Hints (Q{i+1})"):
                                    st.markdown(hints)
                        with coach_col:
                            if st.button(
                                f"⚡ Real-Time Assist — Q{i+1}",
                                key=f"rta_{cat}_{i}",
                                use_container_width=True,
                                help="Get real-time coaching before asking this question"):
                                with st.spinner(f"Interview Coach preparing guidance for Q{i+1}..."):
                                    coaching = get_interview_coach_guidance(
                                        question=q.get("question",""),
                                        category=cat,
                                        jd_analysis=jd,
                                        candidate_profile=cand,
                                        question_index=i)

                                if isinstance(coaching, dict) and "error" not in coaching:
                                    st.session_state[f"rta_result_{cat}_{i}"] = coaching
                                else:
                                    st.error("Coach guidance failed. Check API.")

                        # show coach result if available
                        coach_key = f"rta_result_{cat}_{i}"
                        if st.session_state.get(coach_key):
                            c = st.session_state[coach_key]
                            st.markdown(
                                f'<div style="background:#1a1d2e;border:1px solid #EF9F27;'
                                f'border-radius:10px;padding:14px 16px;margin:6px 0 12px">'
                                f'<div style="font-size:12px;font-weight:500;color:#EF9F27;'
                                f'margin-bottom:10px">🎯 ⚡ REAL-TIME ASSIST — Q{i+1}</div>'

                                # What to listen for
                                f'<div style="margin-bottom:10px">'
                                f'<div style="font-size:11px;font-weight:500;color:#5DCAA5;'
                                f'text-transform:uppercase;letter-spacing:.04em">✅ What to listen for</div>'
                                f'<ul style="margin:4px 0 0 16px;padding:0">'
                                + "".join(f'<li style="font-size:12px;color:#e0e0e0;margin-bottom:2px">{p}</li>'
                                          for p in c.get("what_to_listen_for",[])) +
                                f'</ul></div>'

                                # Red flags
                                f'<div style="margin-bottom:10px">'
                                f'<div style="font-size:11px;font-weight:500;color:#D85A30;'
                                f'text-transform:uppercase;letter-spacing:.04em">🚩 Red flags</div>'
                                f'<ul style="margin:4px 0 0 16px;padding:0">'
                                + "".join(f'<li style="font-size:12px;color:#e0e0e0;margin-bottom:2px">{p}</li>'
                                          for p in c.get("red_flags",[])) +
                                f'</ul></div>'

                                # Follow-up questions
                                f'<div style="margin-bottom:10px">'
                                f'<div style="font-size:11px;font-weight:500;color:#7F77DD;'
                                f'text-transform:uppercase;letter-spacing:.04em">❓ Follow-up questions</div>'
                                f'<ol style="margin:4px 0 0 16px;padding:0">'
                                + "".join(f'<li style="font-size:12px;color:#e0e0e0;margin-bottom:4px">{p}</li>'
                                          for p in c.get("follow_up_questions",[])) +
                                f'</ol></div>'

                                # Scoring guide
                                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px">'
                                f'<div style="background:#1a2a20;border-radius:6px;padding:8px">'
                                f'<div style="font-size:10px;color:#5DCAA5;font-weight:500">⭐⭐⭐⭐⭐ Score 5</div>'
                                f'<div style="font-size:11px;color:#e0e0e0;margin-top:3px">{c.get("score_5_looks_like","")}</div></div>'
                                f'<div style="background:#2a2010;border-radius:6px;padding:8px">'
                                f'<div style="font-size:10px;color:#EF9F27;font-weight:500">⭐⭐⭐ Score 3</div>'
                                f'<div style="font-size:11px;color:#e0e0e0;margin-top:3px">{c.get("score_3_looks_like","")}</div></div>'
                                f'<div style="background:#2a1a1a;border-radius:6px;padding:8px">'
                                f'<div style="font-size:10px;color:#D85A30;font-weight:500">⭐ Score 1</div>'
                                f'<div style="font-size:11px;color:#e0e0e0;margin-top:3px">{c.get("score_1_looks_like","")}</div></div>'
                                f'</div>'

                                # Tip + timing
                                f'<div style="background:#2d3250;border-radius:6px;padding:8px;'
                                f'font-size:12px;color:#AFA9EC">'
                                f'💬 <b>Tip:</b> {c.get("interviewer_tip","")} &nbsp;|&nbsp; '
                                f'⏱ <b>Let them speak:</b> {c.get("time_suggestion","")}'
                                f'</div></div>',
                                unsafe_allow_html=True)

                            if st.button(f"✕ ✕ Close Assist", key=f"close_rta_{cat}_{i}",
                                         use_container_width=False):
                                del st.session_state[coach_key]
                                st.rerun()

            if st.button("🔄 Regenerate Questions", key="regen_qs"):
                st.session_state.questions         = None
                st.session_state.interview_answers = []
                st.session_state.transcript_answers= {}
                st.rerun()

            # FIX 2: allow switching between Excel and AI even after questions generated
            source = st.session_state.questions.get("source","ai") if st.session_state.questions else "ai"
            excel_qb_sw = st.session_state.get("excel_question_bank",[])
            sw1, sw2 = st.columns(2)
            with sw1:
                if source == "excel" and excel_qb_sw:
                    st.markdown(
                        '<div style="background:#1a2a20;border:1px solid #1D9E75;'
                        'border-radius:6px;padding:6px 12px;font-size:12px;'
                        'color:#5DCAA5">📊 Currently using Excel questions</div>',
                        unsafe_allow_html=True)
                elif source == "ai":
                    st.markdown(
                        '<div style="background:#1e2235;border:1px solid #7F77DD;'
                        'border-radius:6px;padding:6px 12px;font-size:12px;'
                        'color:#AFA9EC">🤖 Currently using AI questions</div>',
                        unsafe_allow_html=True)
            with sw2:
                if source == "excel" and excel_qb_sw:
                    if st.button("🤖 Switch to AI Questions",
                                 key="switch_to_ai", use_container_width=True):
                        with st.spinner("Generating AI questions..."):
                            qs_ai = generate_questions(jd, cand, 10, 5, 5, 3, resume_text)
                        qs_ai["source"] = "ai"
                        st.session_state.questions         = qs_ai
                        st.session_state.interview_answers = []
                        st.session_state.transcript_answers= {}
                        notify("✅ Switched to AI-generated questions", "success")
                        st.rerun()
                elif source == "ai" and excel_qb_sw:
                    if st.button("📊 Switch to Excel Questions",
                                 key="switch_to_excel", use_container_width=True):
                        st.session_state.questions         = None
                        st.session_state.interview_answers = []
                        st.session_state.transcript_answers= {}
                        notify("Switched back — select Excel Bank below", "info")
                        st.rerun()

        else:
            # question source
            excel_qb = st.session_state.get("excel_question_bank",[])
            if excel_qb:
                st.markdown(
                    f'<div style="background:#1a2a20;border:1px solid #1D9E75;'
                    f'border-radius:8px;padding:12px 16px;margin-bottom:12px">'
                    f'<div style="font-size:13px;font-weight:500;color:#5DCAA5">'
                    f'📊 Excel Question Bank — {len(excel_qb)} questions detected</div>'
                    f'<div style="font-size:12px;color:#9099b0;margin-top:4px">'
                    f'Conceptual: <b>{len([q for q in excel_qb if q["category"]=="Conceptual"])}</b>'
                    f' &nbsp;|&nbsp; Coding: <b>{len([q for q in excel_qb if q["category"]=="Coding"])}</b>'
                    f' &nbsp;|&nbsp; Scenario: <b>{len([q for q in excel_qb if q["category"]=="Scenario"])}</b>'
                    f'</div></div>', unsafe_allow_html=True)

                ea, eb = st.columns(2)
                with ea:
                    enrich = st.checkbox("✨ Enrich with AI hints & better categories", value=True)
                    n_res  = st.number_input("Resume-Based Qs to add", 1, 5, 3, key="xl_nr")
                    if st.button("📊 Use Excel Bank + Resume Questions",
                                 type="primary", use_container_width=True):
                        with st.spinner("Preparing questions..."):
                            bank = list(excel_qb)
                            if enrich and jd:
                                with st.spinner("✨ Enriching..."):
                                    bank = enrich_excel_questions(bank, jd)
                            rqs = []
                            if jd and resume_text:
                                with st.spinner("Generating resume questions..."):
                                    rr = generate_questions(jd, cand, 0, 0, 0,
                                                            int(n_res), resume_text)
                                    rqs = rr.get("resume_based_questions",[])
                        qs = {
                            "role": jd.get("role_title","") if jd else "",
                            "conceptual_questions": [
                                {"question":q["question"],"skill_tested":q.get("skill_tested",""),
                                 "difficulty":q.get("difficulty","Medium"),
                                 "expected_hints":q.get("expected_hints",""),"source":"Excel"}
                                for q in bank if q["category"]=="Conceptual"],
                            "coding_questions": [
                                {"question":q["question"],"skill_tested":q.get("skill_tested",""),
                                 "difficulty":q.get("difficulty","Medium"),
                                 "expected_hints":q.get("expected_hints",""),
                                 "time_minutes":q.get("time_minutes",10),"source":"Excel"}
                                for q in bank if q["category"]=="Coding"],
                            "scenario_questions": [
                                {"question":q["question"],"skill_tested":q.get("skill_tested",""),
                                 "difficulty":q.get("difficulty","Medium"),
                                 "expected_hints":q.get("expected_hints",""),"source":"Excel"}
                                for q in bank if q["category"]=="Scenario"],
                            "resume_based_questions": rqs,
                            "evaluation_tips": [
                                "Conceptual: probe depth of understanding.",
                                "Coding: look for optimal approach and edge cases.",
                                "Scenario: assess decision-making under pressure.",
                                "Resume-based: verify claims with specific outcomes.",
                            ],
                            "source":"excel",
                        }
                        st.session_state.questions         = qs
                        st.session_state.interview_answers = []
                        notify("✅ Questions ready. Conduct the interview, then paste transcript.", "success")
                        st.rerun()
                with eb:
                    st.markdown("**Or generate fully AI questions:**")
                    gc1,gc2,gc3,gc4 = st.columns(4)
                    with gc1: gnc = st.number_input("Conceptual",2,15,10,key="gnc")
                    with gc2: gnk = st.number_input("Coding",1,8,5,key="gnk")
                    with gc3: gns = st.number_input("Scenario",1,8,5,key="gns")
                    with gc4: gnr = st.number_input("Resume",1,5,3,key="gnr")
                    if st.button("🤖 Generate AI Questions", use_container_width=True, key="gen_ai_xl"):
                        with st.spinner("Generating..."):
                            qs = generate_questions(jd, cand, int(gnc), int(gnk),
                                                    int(gns), int(gnr), resume_text)
                        qs["source"] = "ai"
                        st.session_state.questions         = qs
                        st.session_state.interview_answers = []
                        notify("✅ Questions ready. Conduct the interview, then paste transcript.", "success")
                        st.rerun()
            else:
                st.info("AI will generate tailored questions based on the JD and candidate's resume.")
                gc1,gc2,gc3,gc4 = st.columns(4)
                with gc1: gnc = st.number_input("Conceptual",2,15,10)
                with gc2: gnk = st.number_input("Coding",1,8,5)
                with gc3: gns = st.number_input("Scenario",1,8,5)
                with gc4: gnr = st.number_input("Resume-Based",1,5,3)
                if st.button("🎯 Generate Interview Questions",
                             type="primary", use_container_width=True):
                    with st.spinner("Question Generator Agent creating questions..."):
                        qs = generate_questions(jd, cand, int(gnc), int(gnk),
                                               int(gns), int(gnr), resume_text)
                    qs["source"] = "ai"
                    st.session_state.questions         = qs
                    st.session_state.interview_answers = []
                    notify("✅ Questions ready. Conduct the interview, then come back to paste transcript.", "success")
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2 — PASTE / UPLOAD TRANSCRIPT (after the interview)
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander(
            f"{'✅ STEP 2 DONE' if tr_done else '📋 STEP 2'} — Paste or Upload Meeting Transcript (do this AFTER the call)",
            expanded=qs_ready and not tr_done):

        if not qs_ready:
            st.warning("⚠️ Complete Step 1 first — generate questions before the interview.")
        else:
            st.markdown(
                "After the interview call ends, paste the full transcript below "
                "or upload the exported file. **No need to separate answers per question** — "
                "AI reads the entire transcript and evaluates everything automatically.")

            st.markdown(
                '<div style="background:#1e2235;border:1px solid #2d3250;'
                'border-radius:8px;padding:12px 16px;margin-bottom:14px;font-size:12px;color:#9099b0">'
                '<b style="color:#e0e0e0">How to get the transcript:</b><br>'
                '🔵 <b>Microsoft Teams</b> → Meeting chat → three dots (...) → Transcript → Copy all&nbsp;&nbsp;'
                'OR&nbsp;&nbsp;Download as .docx<br>'
                '🟣 <b>Zoom</b> → Recordings → Transcript → Copy text&nbsp;&nbsp;'
                'OR&nbsp;&nbsp;Download .vtt<br>'
                '🟢 <b>Google Meet</b> → Google Docs summary → Copy text&nbsp;&nbsp;'
                'OR&nbsp;&nbsp;Download .txt<br>'
                '🤖 <b>Teams Copilot / Zoom AI</b> → Copy the AI-generated meeting summary'
                '</div>', unsafe_allow_html=True)

            tr_input_tab1, tr_input_tab2 = st.tabs([
                "✏️ Paste transcript / AI summary",
                "📁 Upload file (.docx / .txt / .vtt)",
            ])

            raw_transcript = st.session_state.get("_raw_transcript","")

            with tr_input_tab1:
                pasted = st.text_area(
                    "Paste full meeting transcript or AI meeting summary here",
                    height=300, key="transcript_paste_v2",
                    placeholder=(
                        "Example — Microsoft Teams transcript:\n\n"
                        "[10:02] Interviewer: Can you explain how you handle database migrations in production?\n"
                        "[10:03] Vinay: Sure. We use Alembic with SQLAlchemy. I always create a backup first, "
                        "then run the migration in a staging environment...\n\n"
                        "--- OR paste Zoom AI summary / Teams Copilot summary ---\n\n"
                        "Meeting Summary:\n"
                        "The candidate demonstrated strong Python knowledge. "
                        "When asked about async programming they explained asyncio clearly..."
                    ))
                if pasted.strip():
                    st.session_state["_raw_transcript"] = pasted.strip()
                    raw_transcript = pasted.strip()

            with tr_input_tab2:
                tr_file = st.file_uploader(
                    "Upload transcript file",
                    type=["txt","docx","vtt"],
                    key="tr_file_v2")
                if tr_file:
                    ext = os.path.splitext(tr_file.name)[1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(tr_file.read())
                        tmp_path = tmp.name
                    if ext == ".vtt":
                        raw = open(tmp_path, encoding="utf-8", errors="ignore").read()
                        raw_transcript = parse_vtt_transcript(raw)
                    elif ext in (".docx",".doc"):
                        raw_transcript = extract_text(tmp_path)
                    else:
                        raw_transcript = open(tmp_path, encoding="utf-8", errors="ignore").read().strip()
                    os.unlink(tmp_path)
                    st.session_state["_raw_transcript"] = raw_transcript
                    st.success(f"✅ {tr_file.name} loaded — {len(raw_transcript)} chars")
                    with st.expander("👁️ Preview (first 600 chars)"):
                        st.text(raw_transcript[:600] + ("..." if len(raw_transcript)>600 else ""))

            st.markdown("---")

            if raw_transcript:
                char_count = len(raw_transcript)
                word_count = len(raw_transcript.split())
                st.markdown(
                    f'<div style="background:#1a2a20;border:1px solid #1D9E75;'
                    f'border-radius:8px;padding:10px 16px;font-size:12px;color:#5DCAA5">'
                    f'✅ Transcript ready — {char_count:,} characters · ~{word_count:,} words</div>',
                    unsafe_allow_html=True)
                st.markdown("")

                # build flat questions for count display
                qs_now = st.session_state.questions or {}
                all_flat_now = []
                for q in qs_now.get("conceptual_questions",  []): all_flat_now.append({**q,"category":"Conceptual"})
                for q in qs_now.get("coding_questions",      []): all_flat_now.append({**q,"category":"Coding"})
                for q in qs_now.get("scenario_questions",    []): all_flat_now.append({**q,"category":"Scenario"})
                for q in qs_now.get("resume_based_questions",[]): all_flat_now.append({**q,"category":"Resume"})

                st.info(
                    f"AI will now evaluate **{len(all_flat_now)} questions** against this transcript in one shot. "
                    f"No per-question answer pasting needed.")

                if st.button(
                    "🤖 Evaluate All Questions from Transcript",
                    type="primary", use_container_width=True,
                    key="full_eval_btn"):

                    with st.spinner(
                        f"AI reading transcript and evaluating all "
                        f"{len(all_flat_now)} questions... (1 API call)"):
                        full_result = evaluate_full_transcript(
                            raw_transcript, all_flat_now, jd,
                            cand.get("candidate_name","Candidate"))

                    if "error" in full_result:
                        st.error(f"Evaluation failed: {full_result.get('raw','')[:200]}")
                    else:
                        # store transcript_answers for display
                        tr_ans = {}
                        interview_answers = []
                        for pq in full_result.get("per_question",[]):
                            idx = pq.get("q_index",0)
                            tr_ans[idx] = pq.get("answer_extracted","")
                            if pq.get("score",0) > 0:
                                interview_answers.append({
                                    "q_index":   idx,
                                    "question":  pq.get("question",""),
                                    "category":  pq.get("category",""),
                                    "answer":    pq.get("answer_extracted",""),
                                    "evaluation": {
                                        "score":             pq.get("score",0),
                                        "score_label":       pq.get("score_label",""),
                                        "what_was_good":     pq.get("what_was_good",""),
                                        "what_was_missing":  pq.get("what_was_missing",""),
                                        "follow_up_question":pq.get("follow_up_question",""),
                                        "red_flags":         [],
                                    }
                                })

                        st.session_state.transcript_answers  = tr_ans
                        st.session_state.interview_answers   = interview_answers

                        # auto-build feedback analysis from full_result
                        fb = {
                            "candidate_name":       cand.get("candidate_name",""),
                            "final_score":          full_result.get("final_score",0),
                            "verdict":              full_result.get("verdict","Hold for Review"),
                            "overall_summary":      full_result.get("overall_summary",""),
                            "top_strengths":        full_result.get("top_strengths",[]),
                            "key_concerns":         full_result.get("key_concerns",[]),
                            "risk_level":           "Medium",
                            "requires_human_review":full_result.get("requires_human_review",False),
                            "human_review_reason":  full_result.get("human_review_reason",""),
                        }
                        st.session_state.feedback_analysis = fb

                        # auto-build comm assessment
                        comm = {
                            "candidate_name":             cand.get("candidate_name",""),
                            "overall_communication_score":full_result.get("overall_communication_score",0),
                            "clarity_score":              full_result.get("clarity_score",3),
                            "structure_score":            full_result.get("structure_score",3),
                            "confidence_score":           full_result.get("confidence_score",3),
                            "technical_vocabulary_score": 3,
                            "communication_strengths":    full_result.get("communication_strengths",[]),
                            "communication_gaps":         full_result.get("communication_gaps",[]),
                            "communication_summary":      full_result.get("communication_summary",""),
                        }
                        st.session_state.comm_assessment = comm

                        # rubric scoring
                        rubric = st.session_state.rubric or {}
                        dims   = rubric.get("rubric_dimensions",[])
                        total, bd = 0, []
                        for d in dims:
                            nm = d["dimension"]; w = d.get("weight_percent",20)
                            raw_sc = 3
                            for a in interview_answers:
                                if a["q_index"] < len(dims) and dims[interview_answers.index(a)%len(dims)]["dimension"] == nm:
                                    raw_sc = a["evaluation"].get("score",3); break
                            wt = (raw_sc/5)*w; total += wt
                            bd.append({"dimension":nm,"raw_score":raw_sc,"weight":w,"weighted_score":round(wt,1)})
                        st.session_state.rubric_result = {
                            "total_score":    round(total,1),
                            "pass_threshold": rubric.get("minimum_pass_score",60),
                            "passed":         total >= rubric.get("minimum_pass_score",60),
                            "breakdown":      bd,
                        }

                        if fb.get("requires_human_review"):
                            st.session_state.human_review_queue.append({
                                "candidate": cand.get("candidate_name",""),
                                "reason":    fb.get("human_review_reason","Borderline score"),
                                "feedback":  fb, "status": "Pending",
                            })

                        scored = len(interview_answers)
                        notify(
                            f"✅ Evaluation complete — {scored} answers scored. "
                            f"See results in Step 3 below and in Feedback & Decision.",
                            "success")
                        st.rerun()
            else:
                st.info("👆 Paste the transcript above or upload a file to continue.")

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3 — EVALUATION RESULTS (shown after transcript evaluation)
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander(
            f"{'✅ STEP 3 DONE' if eval_done else '📊 STEP 3'} — Evaluation Results",
            expanded=eval_done):

        if not eval_done:
            st.info("Results will appear here after Step 2 is complete.")
        else:
            answers = st.session_state.interview_answers
            fb      = st.session_state.feedback_analysis or {}
            comm    = st.session_state.comm_assessment   or {}

            # top summary row
            fs  = fb.get("final_score",0)
            cs  = comm.get("overall_communication_score",0)
            v   = fb.get("verdict","")
            vc  = {"Strong Hire":"#1D9E75","Hire":"#5DCAA5",
                   "Hold for Review":"#EF9F27","Reject":"#D85A30"}.get(v,"#9099b0")

            s1,s2,s3,s4 = st.columns(4)
            with s1:
                st.plotly_chart(gauge(fs,"Final Score"),
                                use_container_width=True,
                                key="tr_gauge_final")
            with s2:
                st.plotly_chart(gauge(cs,"Communication"),
                                use_container_width=True,
                                key="tr_gauge_comm")
            with s3:
                scored_cnt = len(answers)
                avg_sc = (sum(a.get("evaluation",{}).get("score",0) for a in answers)/scored_cnt
                          if scored_cnt else 0)
                st.plotly_chart(gauge(int(avg_sc/5*100),"Avg Answer Score"),
                                use_container_width=True,
                                key="tr_gauge_avg")
            with s4:
                st.markdown(
                    f'<div style="background:#1e2235;border:2px solid {vc};'
                    f'border-radius:10px;padding:20px 10px;text-align:center;margin-top:16px">'
                    f'<div style="font-size:11px;color:#9099b0">AI Verdict</div>'
                    f'<div style="font-size:16px;font-weight:700;color:{vc};margin-top:4px">{v}</div>'
                    f'</div>', unsafe_allow_html=True)

            st.markdown(f"**Summary:** {fb.get('overall_summary','')}")

            # per-question results
            st.markdown("#### 📋 Per-Question Evaluation")
            cat_colors = {"Conceptual":"#7F77DD","Coding":"#378ADD",
                          "Scenario":"#1D9E75","Resume":"#D4537E"}

            for a in sorted(answers, key=lambda x: x.get("q_index",0)):
                ev  = a.get("evaluation",{})
                sv  = ev.get("score",0)
                cat = a.get("category","Conceptual")
                col = "#1D9E75" if sv>=4 else "#EF9F27" if sv==3 else "#D85A30"
                cat_color = cat_colors.get(cat,"#7F77DD")

                with st.expander(
                    f"Q{a['q_index']+1} [{cat}] — Score: {sv}/5 — {ev.get('score_label','')}",
                    expanded=False):

                    st.markdown(
                        f'<div style="background:#1e2235;border-left:4px solid {cat_color};'
                        f'border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px">'
                        f'<b style="color:#e0e0e0">{a.get("question","")}</b></div>',
                        unsafe_allow_html=True)

                    if a.get("answer","").strip():
                        st.markdown("**📝 What candidate said (extracted from transcript):**")
                        st.markdown(
                            f'<div style="background:#161b26;border:1px solid #2d3250;'
                            f'border-radius:6px;padding:10px 14px;font-size:13px;'
                            f'color:#c0c8d8;font-style:italic">'
                            f'{a["answer"]}</div>', unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ Answer not found in transcript.")

                    st.markdown("---")
                    ra, rb, rc = st.columns(3)
                    with ra:
                        st.markdown(
                            f'<div style="background:#1a2a20;border-radius:6px;padding:10px">'
                            f'<div style="font-size:11px;color:#5DCAA5;font-weight:500">✅ WHAT WAS GOOD</div>'
                            f'<div style="font-size:12px;color:#e0e0e0;margin-top:4px">'
                            f'{ev.get("what_was_good","—")}</div></div>', unsafe_allow_html=True)
                    with rb:
                        st.markdown(
                            f'<div style="background:#2a2010;border-radius:6px;padding:10px">'
                            f'<div style="font-size:11px;color:#EF9F27;font-weight:500">⚠️ WHAT WAS MISSING</div>'
                            f'<div style="font-size:12px;color:#e0e0e0;margin-top:4px">'
                            f'{ev.get("what_was_missing","—")}</div></div>', unsafe_allow_html=True)
                    with rc:
                        st.markdown(
                            f'<div style="background:#1e2235;border-radius:6px;padding:10px">'
                            f'<div style="font-size:11px;color:#378ADD;font-weight:500">❓ FOLLOW-UP</div>'
                            f'<div style="font-size:12px;color:#e0e0e0;margin-top:4px">'
                            f'{ev.get("follow_up_question","—")}</div></div>', unsafe_allow_html=True)

            # strengths and concerns
            st.markdown("---")
            sc1, sc2 = st.columns(2)
            with sc1:
                st.markdown("**💪 Top Strengths**")
                for s in fb.get("top_strengths",[]): st.markdown(f"✅ {s}")
                st.markdown("**💬 Communication**")
                for s in comm.get("communication_strengths",[]): st.markdown(f"✅ {s}")
            with sc2:
                st.markdown("**⚠️ Key Concerns**")
                for s in fb.get("key_concerns",[]): st.markdown(f"⚠️ {s}")
                if comm.get("communication_gaps"):
                    st.markdown("**💬 Communication Gaps**")
                    for s in comm["communication_gaps"]: st.markdown(f"⚠️ {s}")

            st.markdown("---")
            if st.button("➡️ Go to Feedback & Decision for final verdict",
                         type="primary", use_container_width=True,
                         key="goto_fd"):
                notify("✅ Evaluation done. Head to Feedback & Decision in the sidebar.", "success")
                st.rerun()


elif page == "Feedback & Decision":
    st.title("📋 Feedback & Decision")
    st.caption("Step 6 of 6  ·  Agents: Feedback Analyzer → Manager Agent → Final Decision")

    if not st.session_state.feedback_analysis:
        st.warning("⚠️ Complete an interview first.")
        st.stop()

    fb   = st.session_state.feedback_analysis
    cand = st.session_state.selected_candidate or {}
    comm = st.session_state.comm_assessment    or {}
    rr   = st.session_state.rubric_result      or {}

    st.subheader(f"Candidate: {fb.get('candidate_name', cand.get('candidate_name','?'))}")

    c1, c2, c3 = st.columns(3)
    with c1: st.plotly_chart(gauge(fb.get("final_score",0),     "Final Score"),   use_container_width=True, key="gauge_final_score")
    with c2: st.plotly_chart(gauge(comm.get("overall_communication_score",0),"Communication"), use_container_width=True, key="gauge_comm_score")
    with c3: st.plotly_chart(gauge(rr.get("total_score",0),     "Rubric Score"),  use_container_width=True, key="gauge_rubric_score")

    v  = fb.get("verdict","")
    vc = {"Strong Hire":"#1D9E75","Hire":"#5DCAA5",
          "Hold for Review":"#EF9F27","Reject":"#D85A30"}.get(v,"#9099b0")
    st.markdown(
        f'<div style="text-align:center;padding:20px;background:#1e2235;'
        f'border-radius:12px;border:2px solid {vc};margin:14px 0">'
        f'<div style="font-size:13px;color:#9099b0">Feedback Analyzer Verdict</div>'
        f'<div style="font-size:28px;font-weight:700;color:{vc}">{v}</div>'
        f'<div style="font-size:12px;color:#9099b0">Risk: {fb.get("risk_level","N/A")}</div>'
        f'</div>', unsafe_allow_html=True)

    st.markdown(f"**Summary:** {fb.get('overall_summary','')}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**💪 Top Strengths**")
        for s in fb.get("top_strengths",[]): st.markdown(f"✅ {s}")
    with c2:
        st.markdown("**⚠️ Key Concerns**")
        for s in fb.get("key_concerns",[]):  st.markdown(f"⚠️ {s}")

    if fb.get("requires_human_review"):
        st.warning(f"🧑 **Human Review Required:** {fb.get('human_review_reason','')}")

    st.markdown("---")
    human_approved = None
    if fb.get("requires_human_review"):
        ch = st.radio("Human Reviewer Decision:",
                      ["Pending","Approved ✅","Rejected ❌"], horizontal=True)
        human_approved = None if ch=="Pending" else (ch=="Approved ✅")

    if st.button("🤖 Get Manager Agent Final Decision",
                 type="primary", use_container_width=True):
        with st.spinner("Manager Agent making final decision..."):
            dec = manager_final_decision(fb, comm, rr, human_approved)
        st.session_state.final_decision = dec
        notify("✅ Final decision ready.","success")
        st.rerun()

    if st.session_state.final_decision:
        d  = st.session_state.final_decision
        dc = {"HIRE":"#1D9E75","HOLD":"#EF9F27","REJECT":"#D85A30"}.get(
             d.get("final_decision",""),"#9099b0")
        st.markdown(
            f'<div style="text-align:center;padding:24px;background:#1e2235;'
            f'border-radius:12px;border:3px solid {dc};margin:14px 0">'
            f'<div style="font-size:13px;color:#9099b0">Manager Agent Final Decision</div>'
            f'<div style="font-size:36px;font-weight:700;color:{dc}">⚡ {d.get("final_decision","")}</div>'
            f'<div style="font-size:13px;color:#9099b0">'
            f'Confidence: <b style="color:{dc}">{d.get("decision_confidence","")}</b>'
            f'&nbsp;|&nbsp;Composite Score: <b>{d.get("composite_score",0)}%</b>'
            f'</div></div>', unsafe_allow_html=True)

        st.markdown(f"**Reason:** {d.get('decision_reason','')}")
        for s in d.get("next_steps",[]): st.markdown(f"→ {s}")

        if d.get("final_decision") == "REJECT" and cand.get("candidate_email",""):
            st.markdown("---")
            if st.button("📧 Send Rejection Email to Candidate"):
                res = send_rejection(
                    cand.get("candidate_email",""),
                    cand.get("candidate_name",""),
                    st.session_state.jd_analysis.get("role_title","")
                        if st.session_state.jd_analysis else "",
                    d.get("rejection_feedback_to_send",""))
                st.success("Rejection email sent.") if res["success"] \
                    else st.error(res.get("error",""))


# ════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Analytics":
    st.title("📊 Analytics & Trends")
    st.caption("Agents: Trend Analysis · Collaboration Facilitator")

    data = st.session_state.all_match_history
    c1, c2 = st.columns(2)

    with c1:
        if st.button("🔄 Run Trend Analysis", type="primary", use_container_width=True):
            if not data: st.warning("No match data yet.")
            else:
                with st.spinner("Trend Agent analyzing..."):
                    st.session_state["trend_results"] = analyze_trends(data)
        if st.session_state.get("trend_results"):
            t = st.session_state["trend_results"]
            st.markdown(
                f"**Processed:** {t.get('total_processed',0)}  |  "
                f"**Avg Score:** {t.get('avg_fit_score',0):.1f}%  |  "
                f"**Shortlist Rate:** {t.get('shortlist_rate','N/A')}")
            for i in t.get("insights",[]): st.markdown(f"• {i}")
            if t.get("common_skill_gaps"):
                st.markdown("**Common Gaps:**")
                for g in t["common_skill_gaps"]: st.markdown(f"• {g}")
            if t.get("prediction"): st.info(f"🔮 {t['prediction']}")

    with c2:
        if st.button("👥 Generate Team Sync", type="primary", use_container_width=True):
            if not data: st.warning("No data yet.")
            else:
                with st.spinner("Collaboration Agent..."):
                    st.session_state["sync_summary"] = generate_team_sync_summary(
                        data, st.session_state.best_practices)
        if st.session_state.get("sync_summary"):
            sy = st.session_state["sync_summary"]
            st.markdown(f"**{sy.get('sync_title','')}**")
            for h in sy.get("key_highlights",[]): st.markdown(f"• {h}")
            for bp in sy.get("new_best_practices",[]):
                if bp not in st.session_state.best_practices:
                    st.session_state.best_practices.append(bp)
            if sy.get("new_best_practices"):
                st.success("✅ Best practices updated in library.")

    if data:
        st.markdown("---")
        fig = go.Figure(go.Bar(
            x=[r.get("candidate_name","?") for r in data],
            y=[r.get("overall_fit_score",0) for r in data],
            marker_color=["#1D9E75" if r.get("shortlist") else "#D85A30" for r in data],
            text=[r.get("overall_fit_score",0) for r in data],
            textposition="outside"))
        fig.update_layout(height=300,margin=dict(t=10,b=60,l=20,r=20),
                          paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                          xaxis=dict(tickangle=-30,tickfont=dict(size=10,color="#9099b0")),
                          yaxis=dict(range=[0,110],tickfont=dict(color="#9099b0")),
                          font=dict(color="#9099b0"))
        st.plotly_chart(fig, use_container_width=True, key="analytics_bar")

        recs = {}
        for r in data:
            k = r.get("recommendation","Unknown")
            recs[k] = recs.get(k,0)+1
        if recs:
            fig2 = go.Figure(go.Pie(
                labels=list(recs.keys()), values=list(recs.values()),
                marker_colors=["#1D9E75","#5DCAA5","#EF9F27","#D85A30"], hole=0.5))
            fig2.update_layout(height=280,margin=dict(t=10,b=10,l=10,r=10),
                                paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#9099b0"))
            st.plotly_chart(fig2, use_container_width=True, key="analytics_pie")


# ════════════════════════════════════════════════════════════════════════════
# HUMAN REVIEW
# ════════════════════════════════════════════════════════════════════════════
elif page == "Human Review":
    st.title("🧑 Human-in-the-Loop Review")
    st.caption("Borderline candidates (55–70%) are auto-flagged here by Feedback Analyzer")

    queue = st.session_state.human_review_queue
    if not queue:
        st.success("✅ No candidates pending human review.")
        st.info("Candidates with borderline scores or red flags are automatically added here.")
    else:
        st.warning(f"⚠️ {len(queue)} candidate(s) awaiting your review")
        for i, item in enumerate(queue):
            fb = item.get("feedback",{})
            with st.expander(
                    f"👤 {item['candidate']}  —  Status: {item['status']}"):
                st.markdown(
                    f"**AI Verdict:** {fb.get('verdict','N/A')}  |  "
                    f"**Score:** {fb.get('final_score',0)}%  |  "
                    f"**Risk:** {fb.get('risk_level','N/A')}")
                st.markdown(f"**Summary:** {fb.get('overall_summary','')}")
                st.markdown(f"**Reason flagged:** {item['reason']}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("✅ Approve — Move Forward",
                                 key=f"ap{i}", type="primary"):
                        st.session_state.human_review_queue[i]["status"] = "Approved ✅"
                        notify(f"✅ {item['candidate']} approved by human","success")
                        st.rerun()
                with c2:
                    if st.button("❌ Reject", key=f"rj{i}"):
                        st.session_state.human_review_queue[i]["status"] = "Rejected ❌"
                        notify(f"❌ {item['candidate']} rejected","warning")
                        st.rerun()
                with c3:
                    notes = st.text_input("Reviewer notes", key=f"nt{i}",
                                          placeholder="Add comments...")
                    if notes:
                        st.session_state.human_review_queue[i]["notes"] = notes


# ════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Settings":
    st.title("⚙️ Settings & Configuration")

    # only admin sees full settings
    if st.session_state.role != "admin":
        st.warning("⚠️ Only Admin can access full settings.")
        st.info(f"You are logged in as **{st.session_state.user_name}** ({st.session_state.role})")
        st.stop()

    st.subheader("🔑 API Status")
    if GROQ_API_KEY:
        st.success(f"✅ Groq API Key loaded  ({GROQ_API_KEY[:8]}...)")
    else:
        st.error("❌ GROQ_API_KEY not found. Add it to your .env file.")
    st.info(f"**Active Model:** `{GROQ_MODEL}`  ← updated (llama3-70b-8192 was decommissioned)")

    # User management section
    st.markdown("---")
    st.subheader("👥 User Accounts & Access Control")
    st.markdown(
        "Change credentials in your `.env` file. Restart the app after changes.")

    role_data = [
        {"Role": "🛡️ Admin",          "Username": "admin (default)",
         "Pages": "All 10 sections"},
        {"Role": "📦 Delivery",        "Username": "delivery (default)",
         "Pages": "Dashboard · Upload JD · Upload Resumes · Screen & Match · "
                  "Schedule & Email · Feedback & Decision · Analytics · Human Review"},
        {"Role": "🎥 Interview Panel", "Username": "panel (default)",
         "Pages": "Interview · Feedback & Decision · Analytics · Human Review"},
    ]
    import pandas as pd
    st.dataframe(pd.DataFrame(role_data), use_container_width=True, hide_index=True)

    st.code("""# In your .env file:
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

DELIVERY_USERNAME=delivery
DELIVERY_PASSWORD=delivery123

PANEL_USERNAME=panel
PANEL_PASSWORD=panel123""", language="bash")

    st.subheader("📁 .env file template")
    st.code("""GROQ_API_KEY=your_groq_api_key_here
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_16char_app_password_here
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
COMPANY_NAME=HCLTech""", language="bash")

    st.subheader("📧 Gmail App Password setup")
    st.markdown("""
1. Enable **2-Factor Authentication** on your Google Account
2. Go to: **Google Account → Security → 2-Step Verification → App Passwords**
3. App name: type `HireIntel` → click **Create**
4. Copy the 16-character password shown (remove spaces)
5. Paste as `EMAIL_PASSWORD` in your `.env` file
""")

    st.subheader("🗄️ RAG Knowledge Base")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Resumes in DB", resume_count())
        st.metric("JDs in DB",     jd_count())
    with c2:
        if st.button("🗑️ Clear Session State (DB preserved)", type="secondary"):
            for k, v in DEFAULTS.items():
                st.session_state[k] = v
            st.success("Session cleared. ChromaDB resumes and JDs are still intact.")

    st.subheader("📋 Correct Workflow Order")
    st.markdown("""
| Step | Page | What to do |
|------|------|-----------|
| 1 | Upload JD | Paste / upload JD → AI analyzes |
| 2 | Upload Resumes | Upload files or folder path |
| 3 | Screen & Match | AI screens all stored resumes |
| 4 | **Schedule & Email** | Send invite with slot options |
| 5 | **Interview** | Conduct interview after candidate confirms |
| 6 | Feedback & Decision | Feedback Analyzer + Manager Agent final verdict |
""")

    st.subheader("📋 Best Practices Library")
    if st.session_state.best_practices:
        for bp in st.session_state.best_practices:
            st.markdown(f"✅ {bp}")
    else:
        st.info("Auto-generated by Collaboration Agent in Analytics page.")
    new_bp = st.text_input("Add a best practice manually")
    if st.button("➕ Add") and new_bp:
        st.session_state.best_practices.append(new_bp)
        st.success("Added!")
        st.rerun()
