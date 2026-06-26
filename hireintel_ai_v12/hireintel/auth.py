"""
HireIntel AI — Authentication module
3 roles: admin, delivery, panel
Credentials stored in .env (or fallback defaults for demo)
"""
import os
import hashlib
from dotenv import load_dotenv

load_dotenv()

# ── credentials (set in .env or use defaults for demo) ─────────────────────
# Format in .env:
#   ADMIN_USERNAME=admin   ADMIN_PASSWORD=admin123
#   DELIVERY_USERNAME=delivery  DELIVERY_PASSWORD=delivery123
#   PANEL_USERNAME=panel   PANEL_PASSWORD=panel123

USERS = {
    os.getenv("ADMIN_USERNAME",    "admin"): {
        "password": os.getenv("ADMIN_PASSWORD",    "admin123"),
        "role":     "admin",
        "name":     "Admin",
        "color":    "#7F77DD",
        "icon":     "🛡️",
    },
    os.getenv("DELIVERY_USERNAME", "delivery"): {
        "password": os.getenv("DELIVERY_PASSWORD", "delivery123"),
        "role":     "delivery",
        "name":     "Delivery",
        "color":    "#1D9E75",
        "icon":     "📦",
    },
    os.getenv("PANEL_USERNAME",    "panel"): {
        "password": os.getenv("PANEL_PASSWORD",    "panel123"),
        "role":     "panel",
        "name":     "Interview Panel",
        "color":    "#EF9F27",
        "icon":     "🎥",
    },
}

# ── page access per role ────────────────────────────────────────────────────
ROLE_PAGES = {
    "admin": [
        "Dashboard", "Upload JD", "Upload Resumes",
        "Screen & Match", "Schedule & Email",
        "Interview", "Feedback & Decision",
        "Analytics", "Human Review", "Settings",
    ],
    "delivery": [
        "Dashboard", "Upload JD", "Upload Resumes",
        "Screen & Match", "Schedule & Email",
        "Feedback & Decision", "Analytics", "Human Review",
    ],
    "panel": [
        "Interview", "Feedback & Decision",
        "Analytics", "Human Review",
    ],
}

ROLE_DEFAULT_PAGE = {
    "admin":    "Dashboard",
    "delivery": "Dashboard",
    "panel":    "Interview",
}

ROLE_ICONS = {
    "admin":    ["speedometer2","file-earmark-text","people","search",
                 "envelope","camera-video","check-circle","bar-chart",
                 "person-check","gear"],
    "delivery": ["speedometer2","file-earmark-text","people","search",
                 "envelope","check-circle","bar-chart","person-check"],
    "panel":    ["camera-video","check-circle","bar-chart","person-check"],
}


def verify_login(username: str, password: str):
    """Returns user dict if valid, None otherwise."""
    user = USERS.get(username.strip().lower())
    if user and user["password"] == password:
        return user
    return None


def get_allowed_pages(role: str) -> list:
    return ROLE_PAGES.get(role, [])


def get_page_icons(role: str) -> list:
    return ROLE_ICONS.get(role, [])


def get_default_page(role: str) -> str:
    return ROLE_DEFAULT_PAGE.get(role, "Dashboard")
