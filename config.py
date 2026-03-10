import os

# ── ВКонтакте ──────────────────────────────────
VK_TOKEN       = os.environ["VK_TOKEN"]
VK_GROUP_ID    = int(os.environ["VK_GROUP_ID"])
VK_API_VERSION = "5.199"

# ── Нейросеть ──────────────────────────────────
# "gemini" — бесплатно (1500 запросов/день)
# "claude" — платно (Anthropic)
# "openai" — платно (OpenAI)
AI_PROVIDER       = os.getenv("AI_PROVIDER", "gemini")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

# ── Поведение бота ─────────────────────────────
AI_SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "Ты — дружелюбный AI ассистент сообщества ВКонтакте. "
    "Отвечай на русском языке, кратко и по делу. "
    "Будь вежливым и полезным. Иногда используй эмодзи."
)
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
