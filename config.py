import os

# ── ВКонтакте ──────────────────────────────────
VK_TOKEN       = os.environ["VK_TOKEN"]
VK_GROUP_ID    = int(os.environ["VK_GROUP_ID"])
VK_API_VERSION = "5.199"

# ── Groq (бесплатно) ───────────────────────────
# Ключ: https://console.groq.com → API Keys → Create API Key
AI_PROVIDER  = os.getenv("AI_PROVIDER", "groq")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Поведение бота ─────────────────────────────
AI_SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "Ты — дружелюбный AI ассистент сообщества ВКонтакте. "
    "Отвечай на русском языке, кратко и по делу. "
    "Будь вежливым и полезным. Иногда используй эмодзи."
)
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
