"""
Shared constants for the Ultimate Showdown game.
"""
# The 6 question categories used for the balanced (per-category) draw:
#   general AI + 4 theme categories (from the curated quiz doc) + super-hard bonus.
GAME_CATEGORIES = [
    "ai",                # General AI (the 5 simple AI questions)
    "hallucination",     # AI Hallucination
    "data",              # Data Privacy / Data Shadows
    "agent",             # Agentic AI & Online Shopping
    "phishing",          # Phishing
    "bonus",             # Super-hard bonus questions (added later)
]

# Display labels for the frontend
GAME_CATEGORY_LABELS = {
    "ai": "AI General",
    "hallucination": "Hallucination",
    "data": "Data",
    "agent": "Agent",
    "phishing": "Phishing",
    "bonus": "Bonus (Hard)",
}
