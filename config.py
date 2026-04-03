import os
from dotenv import load_dotenv

load_dotenv()

# ── Required ──────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "@dealdhamaka22")  # e.g. @mychannel
CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "-1002395739644"))                     # e.g. -1001234567890

# ── Giveaway Settings ─────────────────────────────────────
REQUIRED_REFERRALS: int = int(os.getenv("REQUIRED_REFERRALS", "2"))

# ── Owner (highest privilege, set only one) ───────────────
OWNER_ID: int = int(os.getenv("OWNER_ID", "8420494874"))

# ── Admin IDs (comma-separated in .env) ───────────────────
# Admins can use /all, /broadcast, /listallpart, /winners, /stats
# Owner can also use /addadmin, /removeadmin, /admins
_raw_admins = os.getenv("ADMIN_IDS", "6948106932")
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]

# ── Flask Math API ────────────────────────────────────────
# Internal URL when running with Docker Compose; change for external deploys
FLASK_API_URL: str = os.getenv("FLASK_API_URL", "http://math-api:5000")

# ── Validation ────────────────────────────────────────────
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables.")
if CHANNEL_ID == 0:
    raise ValueError("CHANNEL_ID is not set in environment variables.")
if OWNER_ID == 0:
    raise ValueError("OWNER_ID is not set in environment variables.")
