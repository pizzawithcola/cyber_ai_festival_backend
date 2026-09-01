"""
Shared constants for the Ultimate Showdown game.
"""
# The 6 question categories used for the balanced (per-category) draw:
#   4 theme games + general AI + super-hard bonus questions.
GAME_CATEGORIES = [
    "hallucinate",       # AI Hallucination
    "datashadows",       # Data Shadows
    "retaildemolition",  # Retail Demolition
    "phishing",          # Phishing
    "ai",                # General AI
    "bonus",             # Super-hard bonus questions
]

# Display labels for the frontend
GAME_CATEGORY_LABELS = {
    "hallucinate": "AI Hallucination",
    "datashadows": "Data Shadows",
    "retaildemolition": "Retail Demolition",
    "phishing": "Phishing",
    "ai": "AI General",
    "bonus": "Bonus (Hard)",
}
