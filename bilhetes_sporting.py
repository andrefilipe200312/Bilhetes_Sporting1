# sporting_tickets_watch.py
import json
import os
import re
import smtplib
import sys
import time
from email.message import EmailMessage

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

URL = "https://www.sporting.pt/pt/bilhetes-e-gamebox/bilhetes"
STATE_FILE = "state.json"

# SMTP config via env
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")  # pode ser lista separada por vírgulas
USE_STARTTLS = os.environ.get("SMTP_STARTTLS", "1") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TicketWatch/1.0"
}

DATE_RE = re.compile(r"\b\d{1,2}\s+\w+\s+\d{2}:\d{2}\b", re.IGNORECASE)

def fetch_text():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines

def extract_games(lines):
    # Heurística: localizar blocos que terminam em "Comprar Bilhetes"
    # e que contenham uma data.
    games = []
    for i, ln in enumerate(lines):
        if ln.lower() == "comprar bilhetes":
            # pega umas linhas antes
            window = lines[max(0, i - 8): i + 1]
            window_text = " | ".join(window)

            # filtra só blocos com data
            if not any(DATE_RE.search(x) for x in window):
                continue

            # tenta compor título mais legível
            date = next((x for x in window if DATE_RE.search(x)), "")
            # tenta achar duas equipas
            teams = [x for x in window if x.upper() == x and len(x) <= 30]
            competition = next((x for x in window if " - " in x or "Liga" in x or "Taça" in x), "")

            # ID estável
            game_id = "|".join([competition, " vs ".join(teams[:2]), date]).strip("|")
            if not game_id:
                game_id = window_text

            games.append({
                "id": game_id,
                "competition": competition,
                "teams": teams[:2],
                "date": date,
                "raw": window_text,
            })
    # remove duplicados mantendo ordem
    seen = set()
    unique = []
    for g in games:
        if g["id"] in seen:
            continue
        seen.add(g["id"])
        unique.append(g)
    return unique

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen_ids": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_email(new_games):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and EMAIL_TO):
        raise RuntimeError("Config SMTP incompleta (ver variáveis de ambiente).")

    msg = EmailMessage()
    msg["Subject"] = f"[Sporting] Novo(s) jogo(s) à venda: {len(new_games)}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    lines = []
    for g in new_games:
        title = " vs ".join(g["teams"]) if g["teams"] else "(equipas não detectadas)"
        lines.append(f"- {title} | {g['competition']} | {g['date']}")
    lines.append("")
    lines.append(f"Fonte: {URL}")

    msg.set_content("\n".join(lines))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        if USE_STARTTLS:
            smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)

def run_once(notify_on_first_run=False):
    lines = fetch_text()
    games = extract_games(lines)

    state = load_state()
    seen = set(state.get("seen_ids", []))
    current_ids = [g["id"] for g in games]

    new_games = [g for g in games if g["id"] not in seen]

    if new_games and (notify_on_first_run or seen):
        send_email(new_games)

    state["seen_ids"] = list(set(seen).union(current_ids))
    save_state(state)

def main():
    notify_on_first_run = "--notify-on-first-run" in sys.argv
    run_once(notify_on_first_run=notify_on_first_run)

if __name__ == "__main__":
    main()
