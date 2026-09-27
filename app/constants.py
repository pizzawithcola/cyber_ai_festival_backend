"""
Shared constants for the Ultimate Showdown game.
"""
# The 7 question categories used for the balanced (per-category) draw:
#   5 theme categories + super-hard bonus + UAE (Stargate UAE news).
GAME_CATEGORIES = [
    "ai",                # General AI (the 5 simple AI questions)
    "hallucination",     # AI Hallucination
    "data",              # Data Privacy / Data Shadows
    "agent",             # Agentic AI & Online Shopping
    "phishing",          # Phishing
    "bonus",             # Super-hard bonus questions (×2)
    "uae",               # UAE / Stargate UAE news (×3)
]

# Display labels for the frontend
GAME_CATEGORY_LABELS = {
    "ai": "AI General",
    "hallucination": "Hallucination",
    "data": "Data",
    "agent": "Agent",
    "phishing": "Phishing",
    "bonus": "Bonus (Hard)",
    "uae": "UAE",
}
