"""
Seed script: populate the questions table with AI/Cyber security quiz questions.

Usage:
    cd /Users/jamie/Documents/Work/MENAT_AI/cyber_ai_festival_be
    python scripts/seed_questions.py
"""
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.room import Question  # noqa: E402 — triggers table creation

# Ensure tables exist
Base.metadata.create_all(bind=engine)

QUESTIONS = [
    {
        "text": "What does GAN stand for in AI?",
        "option_a": "General Adaptive Network",
        "option_b": "Generative Adversarial Network",
        "option_c": "Graphical Analysis Node",
        "option_d": "Gradient Adjusted Neuron",
        "correct_option": "B",
        "time_limit": 20,
        "category": "AI Basics",
    },
    {
        "text": "Which type of AI attack tricks a model by feeding it slightly altered input data?",
        "option_a": "Phishing attack",
        "option_b": "Adversarial attack",
        "option_c": "Brute force attack",
        "option_d": "Man-in-the-middle attack",
        "correct_option": "B",
        "time_limit": 20,
        "category": "AI Security",
    },
    {
        "text": "What is a deepfake?",
        "option_a": "A very realistic AI-generated fake image or video",
        "option_b": "A type of blockchain transaction",
        "option_c": "A deep-learning training technique",
        "option_d": "A type of firewall",
        "correct_option": "A",
        "time_limit": 20,
        "category": "DeepFake",
    },
    {
        "text": "What is the primary risk of AI hallucination?",
        "option_a": "AI models become too fast",
        "option_b": "AI generates false but convincing information",
        "option_c": "AI deletes its training data",
        "option_d": "AI refuses to answer questions",
        "correct_option": "B",
        "time_limit": 20,
        "category": "AI Risks",
    },
    {
        "text": "Which company developed ChatGPT?",
        "option_a": "Google",
        "option_b": "Meta",
        "option_c": "OpenAI",
        "option_d": "Microsoft",
        "correct_option": "C",
        "time_limit": 15,
        "category": "AI Industry",
    },
    {
        "text": "What does the term 'training data' refer to in machine learning?",
        "option_a": "Data used to test the model's accuracy",
        "option_b": "Data used to teach the model patterns and relationships",
        "option_c": "Data the model has never seen before",
        "option_d": "Data that is manually curated by humans only",
        "correct_option": "B",
        "time_limit": 20,
        "category": "AI Basics",
    },
    {
        "text": "Which of these is a real cybersecurity concern with AI models?",
        "option_a": "Model inversion attacks that reveal training data",
        "option_b": "AI models developing consciousness",
        "option_c": "AI models needing food and water",
        "option_d": "AI models refusing to process numbers",
        "correct_option": "A",
        "time_limit": 20,
        "category": "AI Security",
    },
    {
        "text": "What is 'prompt injection' in the context of LLMs?",
        "option_a": "A method to speed up AI responses",
        "option_b": "A technique where malicious input overrides the model's system instructions",
        "option_c": "A way to install software on the model",
        "option_d": "A type of hardware attack",
        "correct_option": "B",
        "time_limit": 25,
        "category": "AI Security",
    },
    {
        "text": "Which of these is NOT a common type of phishing attack?",
        "option_a": "Spear phishing",
        "option_b": "Whaling",
        "option_c": "Neural phishing",
        "option_d": "Clone phishing",
        "correct_option": "C",
        "time_limit": 20,
        "category": "Phishing",
    },
    {
        "text": "What is the purpose of a CAPTCHA?",
        "option_a": "To encrypt user passwords",
        "option_b": "To distinguish humans from bots",
        "option_c": "To compress web page data",
        "option_d": "To track user location",
        "correct_option": "B",
        "time_limit": 15,
        "category": "Web Security",
    },
    {
        "text": "What is zero-trust security architecture?",
        "option_a": "Trust no one, verify nothing",
        "option_b": "Never trust, always verify every access request",
        "option_c": "Only trust internal network traffic",
        "option_d": "Disable all security measures",
        "correct_option": "B",
        "time_limit": 25,
        "category": "Cyber Security",
    },
    {
        "text": "What does NLP stand for in AI?",
        "option_a": "Neural Learning Protocol",
        "option_b": "Natural Language Processing",
        "option_c": "Network Layer Protection",
        "option_d": "Non-Linear Programming",
        "correct_option": "B",
        "time_limit": 15,
        "category": "AI Basics",
    },
    {
        "text": "What is the biggest risk of using public AI models with sensitive data?",
        "option_a": "The model might run out of memory",
        "option_b": "Data could be used to train future versions of the model",
        "option_c": "The model becomes slower over time",
        "option_d": "The model requires a faster internet connection",
        "correct_option": "B",
        "time_limit": 20,
        "category": "AI Risks",
    },
    {
        "text": "What is social engineering in cybersecurity?",
        "option_a": "Building social networks for engineers",
        "option_b": "Manipulating people into revealing confidential information",
        "option_c": "Using social media for marketing",
        "option_d": "A type of software engineering methodology",
        "correct_option": "B",
        "time_limit": 15,
        "category": "Cyber Security",
    },
    {
        "text": "What is RAG (Retrieval-Augmented Generation)?",
        "option_a": "A technique that combines retrieval of external data with text generation",
        "option_b": "A method to delete old AI models",
        "option_c": "A type of computer hardware",
        "option_d": "A programming language for AI",
        "correct_option": "A",
        "time_limit": 25,
        "category": "AI Techniques",
    },
]


def seed(db):
    existing = db.query(Question).count()
    if existing > 0:
        print(f"Question bank already has {existing} questions. Skipping seed.")
        return

    for q in QUESTIONS:
        db.add(Question(**q))
    db.commit()
    print(f"Seeded {len(QUESTIONS)} questions into the question bank.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
