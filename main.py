import tkinter as tk
from tkinter import scrolledtext
import subprocess
import webbrowser
import pyautogui
import threading
import requests
import json

# =========================
# CONFIG
# =========================
APP_NAME = "J.A.R.V.I.S"
BG_COLOR = "#05070d"
FG_COLOR = "#00f5ff"
ENTRY_BG = "#0b1020"
FONT_MAIN = ("Consolas", 11)
FONT_TITLE = ("Consolas", 16, "bold")

# =========================
# SEGURANÇA
# =========================
BLOCKED = ["format", "del ", "rm ", "shutdown", "reboot", "poweroff"]

def is_safe_command(text: str) -> bool:
    t = text.lower()
    return not any(b in t for b in BLOCKED)

# =========================
# PERSONALIDADE
# =========================
JARVIS_PERSONALITY = """
Você é um assistente pessoal estilo J.A.R.V.I.S.

Você pode responder de duas formas APENAS:
1) Conversa normal
2) Comando do sistema

Quando for um comando, responda EXCLUSIVAMENTE em JSON puro.
Sem markdown. Sem texto fora do JSON.

Formato:

{
  "action": "open | search | youtube | type | clear | chat",
  "target": "string opcional",
  "query": "string opcional",
  "text": "string opcional",
  "response": "string opcional"
}

Nunca invente ações fora da lista.
Nunca explique comandos.
"""

# =========================
# UTIL
# =========================
def extract_json(text: str):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return None

def clean_query(text: str, remove_words):
    q = text.lower()
    for w in remove_words:
        q = q.replace(w, "")
    return q.strip()

# =========================
# IA (OLLAMA)
# =========================
class AIEngine:
    def __init__(self):
        self.url = "http://localhost:11434/api/chat"
        self.model = "llama3.2:1b"

    def decide(self, user_text):
        messages = [
            {"role": "system", "content": JARVIS_PERSONALITY},
            {"role": "user", "content": user_text}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0
            }
        }

        try:
            r = requests.post(self.url, json=payload, timeout=60)
            r.raise_for_status()

            content = r.json()["message"]["content"]
            data = extract_json(content)

            if not data:
                raise ValueError("JSON inválido")

            return data

        except Exception:
            return {
                "action": "chat",
                "response": "Não consegui interpretar sua solicitação."
            }

    def stream_chat(self, user_text, on_token):
        messages = [
            {"role": "system", "content": JARVIS_PERSONALITY},
            {"role": "user", "content": user_text}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7
            }
        }

        try:
            with requests.post(self.url, json=payload, stream=True, timeout=60) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    token = json.loads(line).get("message", {}).get("content", "")
                    if token:
                        on_token(token)
        except Exception as e:
            on_token(f"\n[Erro IA: {e}]")

# =========================
# COMMAND ROUTER
# =========================
class CommandRouter:
    def __init__(self, app):
        self.app = app

    def handle_direct(self, text: str) -> bool:
        if not is_safe_command(text):
            self.app.say("Comando bloqueado por segurança.")
            return True

        cmd = text[1:].strip().lower()

        if cmd.startswith("abrir "):
            self._open(cmd[6:])
        elif cmd.startswith("pesquisar "):
            self._search(cmd[10:])
        elif cmd.startswith("youtube "):
            self._youtube(cmd[8:])
        elif cmd.startswith("digitar "):
            self._type(cmd[8:])
        elif cmd == "limpar":
            self.app.clear()
        else:
            self.app.say("Comando direto não reconhecido.")
        return True

    def execute(self, data: dict):
        action = data.get("action")

        if action == "chat":
            self.app.say(data.get("response", ""))
            return

        if action == "open":
            self._open(data.get("target", ""))
        elif action == "search":
            self._search(data.get("query", ""))
        elif action == "youtube":
            self._youtube(data.get("query", ""))
        elif action == "type":
            self._type(data.get("text", ""))
        elif action == "clear":
            self.app.clear()
        else:
            self.app.say("Ação não reconhecida.")

    def _open(self, target):
        if not target:
            self.app.say("Nada para abrir.")
            return
        subprocess.Popen(f'start "" {target}', shell=True)
        self.app.say(f"Abrindo: {target}")

    def _search(self, query):
        webbrowser.open(f"https://www.google.com/search?q={query}")
        self.app.say(f"Pesquisando no Google: {query}")

    def _youtube(self, query):
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        self.app.say(f"Pesquisando no YouTube: {query}")

    def _type(self, text):
        pyautogui.write(text, interval=0.02)
        self.app.say("Texto digitado.")

# =========================
# GUI
# =========================
class JarvisApp:
    def __init__(self):
        self.ai = AIEngine()
        self.router = CommandRouter(self)

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("500x300")
        self.root.configure(bg=BG_COLOR)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        tk.Label(
            self.root,
            text=APP_NAME,
            fg=FG_COLOR,
            bg=BG_COLOR,
            font=FONT_TITLE
        ).grid(row=0, column=0, pady=8)

        self.chat = scrolledtext.ScrolledText(
            self.root,
            bg=BG_COLOR,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            font=FONT_MAIN,
            wrap="word",
            state="disabled"
        )
        self.chat.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.entry = tk.Entry(
            self.root,
            bg=ENTRY_BG,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            font=FONT_MAIN
        )
        self.entry.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        self.entry.bind("<Return>", self.send)

        self.say("Jarvis online. Digite um comando ou mensagem.")

    def say(self, text):
        self.chat.config(state="normal")
        self.chat.insert("end", f"Jarvis > {text}\n")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def _print_user(self, text):
        self.chat.config(state="normal")
        self.chat.insert("end", f"Você > {text}\n")
        self.chat.config(state="disabled")

    def send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return

        self.entry.delete(0, "end")
        self._print_user(text)

        if text.startswith("/"):
            self.router.handle_direct(text)
            return

        threading.Thread(
            target=self._handle_ai,
            args=(text,),
            daemon=True
        ).start()

    def _handle_ai(self, text):
        decision = self.ai.decide(text)
        text_lower = text.lower()

        # Correção semântica definitiva
        if "youtube" in text_lower:
            decision["action"] = "youtube"
            decision["query"] = clean_query(
                decision.get("query") or text,
                ["youtube", "pesquise", "pesquisar", "no", "na"]
            )

        if decision.get("action") == "chat":
            self.say(decision.get("response", ""))
        else:
            self.router.execute(decision)

    def clear(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")

    def run(self):
        self.root.mainloop()

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    JarvisApp().run()