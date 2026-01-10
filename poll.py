import os, requests

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]

question = "Hast du heute 100 Liegestütze gemacht?"
options = ["Ja 💪", "Nein ❌"]

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendPoll",
    json={
        "chat_id": CHAT_ID,
        "question": question,
        "options": options,
        "is_anonymous": False,
        "allows_multiple_answers": False
    }
)
