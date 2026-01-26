import tkinter as tk
from tkinter import scrolledtext
import subprocess
import webbrowser
import pyautogui
import threading
import requests
import json
import time
import os
import difflib
import urllib.parse
import re
try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    Image = None
    ImageDraw = None
    PYSTRAY_AVAILABLE = False

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
    if not text:
        return ""
    # se contém URL, não force lowercase — remova palavras de forma case-insensitive preservando o restante
    if re.search(r"https?://\S+|www\.\S+|youtu\.be/\S+", text):
        q = text
        for w in remove_words:
            q = re.sub(re.escape(w), "", q, flags=re.IGNORECASE)
        return q.strip()
    # caso normal, mantém comportamento anterior
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
        # verifica rapidamente se o serviço local está acessível
        self.available = False
        try:
            # payload leve apenas para checar disponibilidade
            payload = {
                "model": self.model,
                "messages": [{"role": "system", "content": "health check"}],
                "stream": False,
                "options": {"temperature": 0}
            }
            r = requests.post(self.url, json=payload, timeout=2)
            r.raise_for_status()
            self.available = True
        except Exception:
            self.available = False

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

        # preserve original (sem o leading '/') para repassar sem lowercase
        orig = text[1:].strip()
        cmd = orig.lower()

        if cmd.startswith("abrir ") or cmd.startswith("abra "):
            if cmd.startswith("abrir "):
                self._open(orig[6:])
            else:
                self._open(orig[5:])
        elif cmd.startswith("pesquisar ") or cmd.startswith("pesquise "):
            if cmd.startswith("pesquisar "):
                self._search(orig[10:])
            else:
                self._search(orig[9:])
        elif cmd.startswith("youtube ") or cmd.startswith("yt "):
            if cmd.startswith("youtube "):
                self._youtube(orig[8:])
            else:
                self._youtube(orig[3:])
        elif cmd.startswith("ytvideo ") or cmd.startswith("ytv "):
            if cmd.startswith("ytvideo "):
                self._ytvideo(orig[8:])
            else:
                self._ytvideo(orig[4:])
        elif cmd.startswith("digitar ") or cmd.startswith("digite "):
            if cmd.startswith("digitar "):
                self._type(orig[8:])
            else:
                self._type(orig[7:])
        elif cmd == "limpar" or cmd == "cls":
            self.app.clear()
        elif cmd == "ajuda" or cmd == "help" or cmd == "?":
            self._helpcmd(cmd)
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
        elif action == "ytvideo":
            # AI may put query in different fields; try common ones
            q = data.get("query") or data.get("target") or data.get("text") or ""
            self._ytvideo(q)
        elif action == "type":
            self._type(data.get("text", ""))
        elif action == "clear":
            self.app.clear()
        else:
            self.app.say("Ação não reconhecida.")

    def _helpcmd(self, cmd):
        help_text = (
                "Comandos disponíveis:\n"
                "  /abrir [alvo] - Abre um aplicativo ou URL\n"
                "  /pesquisar [consulta] - Pesquisa no Google\n"
                "  /youtube [consulta] - Pesquisa no YouTube (suporta links)\n"
                "  /digitar [texto] - Digita o texto na janela alvo\n"
                "  /limpar ou /cls - Limpa o chat\n"
                "  /ytvideo [consulta] - Pesquisa avançada de vídeos no YouTube\n"
                "  '/' só é necessário caso modelo IA esteja ativo.\n"
            )
        self.app.say(help_text)
    
    def _open(self, target):
        if not target:
            self.app.say("Nada para abrir.")
            return

        # novo: listar opções do apps.json quando usado "-?"
        if target.strip() == "-?":
            apps_path = os.path.join(os.path.dirname(__file__), "apps.json")
            try:
                with open(apps_path, "r", encoding="utf-8") as f:
                    apps = json.load(f)
            except Exception:
                apps = []

            if not apps:
                self.app.say("Nenhuma entrada encontrada em apps.json.")
                return

            lines = ["Opções disponíveis em apps.json:"]
            if isinstance(apps, dict):
                for k in apps.keys():
                    lines.append(f"- {k}")
            else:
                for a in apps:
                    name = a.get("name", "<sem nome>")
                    lines.append(f"- {name}")

            self.app.say("\n".join(lines))
            return

        # tenta carregar lista de apps de apps.json (mesmo diretório)
        apps_path = os.path.join(os.path.dirname(__file__), "apps.json")
        try:
            with open(apps_path, "r", encoding="utf-8") as f:
                apps = json.load(f)
        except Exception:
            apps = []

        target_clean = target.strip().lower()

        match = None
        if isinstance(apps, list) and apps:
            names = [a.get("name", "").lower() for a in apps]
            # procura correspondência exata / substring
            for a in apps:
                name = a.get("name", "").lower()
                if not name:
                    continue
                if target_clean == name or target_clean in name or name in target_clean:
                    match = a
                    break
            # tentativa fuzzy se nada encontrado
            if not match:
                close = difflib.get_close_matches(target_clean, names, n=1, cutoff=0.6)
                if close:
                    idx = names.index(close[0])
                    match = apps[idx]

        if match:
            exec_cmd = match.get("exec") or match.get("command") or match.get("path") or ""
            if not exec_cmd:
                self.app.say(f"Entrada inválida no apps.json para {match.get('name')}")
                return

            # se for URL, abre no navegador
            if exec_cmd.startswith("http://") or exec_cmd.startswith("https://"):
                webbrowser.open(exec_cmd)
            else:
                # se o caminho existir, usa os.startfile em Windows
                try:
                    if os.path.exists(exec_cmd):
                        try:
                            os.startfile(exec_cmd)
                        except Exception:
                            subprocess.Popen(exec_cmd, shell=True)
                    else:
                        # usa start para permitir .lnk ou associações
                        subprocess.Popen(f'start "" {exec_cmd}', shell=True)
                except Exception:
                    # fallback final: tenta abrir como comando direto
                    try:
                        subprocess.Popen(exec_cmd, shell=True)
                    except Exception as e:
                        self.app.say(f"Erro ao executar entrada do apps.json: {e}")
                        return

            self.app.say(f"Abrindo: {match.get('name')}")
            return

        # fallback: comportamento atual (tenta abrir o target diretamente)
        try:
            subprocess.Popen(f'start "" {target}', shell=True)
            self.app.say(f"Abrindo: {target}")
        except Exception as e:
            # se falhar, tenta abrir como URL
            try:
                webbrowser.open(target)
                self.app.say(f"Abrindo URL: {target}")
            except Exception:
                self.app.say(f"Erro abrindo: {e}")

    def _search(self, query):
        webbrowser.open(f"https://www.google.com/search?q={query}")
        self.app.say(f"Pesquisando no Google: {query}")

    def _youtube(self, query):
        if not query:
            self.app.say("Nada para pesquisar no YouTube.")
            return

        q = query.strip()

        # Detecta URL do YouTube (https://, http://, www., youtu.be)
        m = re.search(r"(https?://\S+|www\.\S+|youtu\.be/\S+)", q)
        if m:
            url = m.group(0)
            if not url.startswith("http"):
                url = "https://" + url

            try:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)

                # Playlist detectada por parâmetro list= ou path /playlist
                if "list" in qs or "/playlist" in parsed.path:
                    webbrowser.open(url)
                    self.app.say(f"Abrindo playlist do YouTube: {url}")
                    return

                # Vídeo direto (watch?v=... ou youtu.be/...)
                webbrowser.open(url)
                self.app.say(f"Abrindo YouTube: {url}")
                return
            except Exception as e:
                self.app.say(f"Erro ao abrir link do YouTube: {e}")
                return

        # Se não for link, faz busca normal (usa quote_plus)
        qenc = urllib.parse.quote_plus(q)
        webbrowser.open(f"https://www.youtube.com/results?search_query={qenc}")
        self.app.say(f"Pesquisando no YouTube: {q}")

    def _ytvideo(self, query):
        if not query:
            self.app.say("Nada para pesquisar no YouTube.")
            return

        q = query.strip()
        op_mode = False
        # suporta prefixo -op para abrir direto o primeiro resultado
        if q.startswith("-op"):
            op_mode = True
            q = q[3:].strip()
        if not q:
            self.app.say("Nada para pesquisar no YouTube.")
            return

        try:
            qenc = urllib.parse.quote_plus(q)
            url = f"https://www.youtube.com/results?search_query={qenc}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            html = r.text

            # extrai até 4 ids de vídeo únicos
            ids = []
            idx = 0
            while len(ids) < 4:
                idx = html.find("/watch?v=", idx)
                if idx == -1:
                    break
                start = idx + len("/watch?v=")
                vid_chars = []
                while start < len(html):
                    ch = html[start]
                    if ch.isalnum() or ch in ("-", "_"):
                        vid_chars.append(ch)
                        start += 1
                    else:
                        break
                vid = "".join(vid_chars)
                if vid and vid not in ids:
                    ids.append(vid)
                idx = start

            if not ids:
                self.app.say("Nenhum vídeo encontrado.")
                return

            # modo -op: abre direto o primeiro vídeo
            if op_mode:
                first_url = f"https://www.youtube.com/watch?v={ids[0]}"
                webbrowser.open(first_url)
                self.app.say(f"Abrindo primeiro vídeo: {q}")
                return

            # caso normal: exibe até 4 opções clicáveis
            chat = self.app.chat
            chat.config(state="normal")
            chat.insert("end", f"Jarvis > Resultados para: {q}\n")
            for i, vid in enumerate(ids, start=1):
                video_url = f"https://www.youtube.com/watch?v={vid}"
                # tenta obter título via oEmbed
                title = vid
                try:
                    ourl = f"https://www.youtube.com/oembed?url={urllib.parse.quote_plus(video_url)}&format=json"
                    orr = requests.get(ourl, timeout=5)
                    if orr.status_code == 200:
                        title = orr.json().get("title", vid)
                except Exception:
                    pass

                tag = f"yt_{vid}"
                start_idx = chat.index("end-1c")
                chat.insert("end", f"{i}- {title}\n")
                end_idx = chat.index("end-1c")
                chat.tag_add(tag, start_idx, end_idx)
                chat.tag_config(tag, foreground=FG_COLOR, underline=True)
                chat.tag_bind(tag, "<Button-1>", lambda e, u=video_url: webbrowser.open(u))

            chat.insert("end", f"Jarvis > Clique no vídeo que desejar.\n")
            chat.see("end")
            chat.config(state="disabled")
        except Exception as e:
            self.app.say(f"Erro ao buscar vídeo: {e}")

    def _type(self, text):
        self.app.say("Posicione o cursor sobre a janela alvo e mantenha-o parado por 1s (tempo limite 20s)...")
        timeout = 20.0
        idle_required = 1.0
        start_time = time.time()
        last_pos = pyautogui.position()
        idle_start = None

        while True:
            time.sleep(0.15)
            pos = pyautogui.position()
            if pos == last_pos:
                if idle_start is None:
                    idle_start = time.time()
                elif time.time() - idle_start >= idle_required:
                    # verifica se o cursor está sobre a janela do Jarvis; se sim, solicita nova seleção
                    try:
                        root = self.app.root
                        x0 = root.winfo_rootx()
                        y0 = root.winfo_rooty()
                        x1 = x0 + root.winfo_width()
                        y1 = y0 + root.winfo_height()
                        if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                            self.app.say("Cursor sobre a janela do Jarvis — posicione em outra janela.")
                            # reinicia contagem para nova seleção
                            start_time = time.time()
                            last_pos = pyautogui.position()
                            idle_start = None
                            continue
                    except Exception:
                        # se falhar ao obter geometria do Tk, prossegue normalmente
                        pass
                    break
            else:
                idle_start = None
                last_pos = pos

            if time.time() - start_time > timeout:
                self.app.say("Tempo esgotado. Digitação cancelada.")
                return

        # traz foco para a janela sob o cursor e digita
        try:
            pyautogui.click(last_pos)
            self.app.say("Digitando em 0.5 segundos...")
            time.sleep(0.5)
            pyautogui.write(text, interval=0.02)
            self.app.say("Texto digitado.")
        except Exception as e:
            self.app.say(f"Erro ao digitar: {e}")

# =========================
# GUI
# =========================
class JarvisApp:
    def __init__(self):
        self.ai = AIEngine()
        self.router = CommandRouter(self)

        # log estado inicial da IA
        try:
            print(f"[JARVIS][AI] inicializado. available={self.ai.available}")
        except Exception:
            pass
 
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("560x380")
        self.root.configure(bg=BG_COLOR)

        # Remove native title bar and provide custom one
        self.root.overrideredirect(True)
        # enquanto não estiver na bandeja, fica sempre on-top
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass

        # minimize -> send to system tray (pystray) or fallback to iconify
        def _quit_from_tray():
            try:
                if hasattr(self, "_tray_icon") and self._tray_icon:
                    try:
                        self._tray_icon.stop()
                    except Exception:
                        pass
                self.root.destroy()
            except Exception:
                pass

        def _restore_from_tray():
            try:
                # restaura estado do AI
                if hasattr(self, "_ai_was_available"):
                    try:
                        self.ai.available = self._ai_was_available
                    except Exception:
                        pass
                    delattr = hasattr(self, "_ai_was_available")
                    if delattr:
                        try:
                            del self._ai_was_available
                        except Exception:
                            pass
                # log retorno da bandeja
                try:
                    print(f"[JARVIS][AI] retornando da bandeja. available={self.ai.available}")
                except Exception:
                    pass

                try:
                    if hasattr(self, "_tray_icon") and self._tray_icon:
                        try:
                            self._tray_icon.stop()
                        except Exception:
                            pass
                        self._tray_icon = None
                    self.root.deiconify()
                    # volta a ficar on-top ao restaurar
                    try:
                        self.root.attributes("-topmost", True)
                    except Exception:
                        pass
                    self.root.overrideredirect(True)
                    self.root.lift()
                    self.root.focus_force()
                    try:
                        self.entry.focus_set()
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        def _minimize_to_tray():
            # store AI availability and disable while in tray
            try:
                self._ai_was_available = getattr(self.ai, "available", False)
                self.ai.available = False
                try:
                    print(f"[JARVIS][AI] indo para a bandeja. previous_available={self._ai_was_available} -> disabled")
                except Exception:
                    pass
            except Exception:
                pass

            # withdraw main window
            try:
                # desativa on-top quando for bandeja
                try:
                    self.root.attributes("-topmost", False)
                except Exception:
                    pass
                self.root.withdraw()
            except Exception:
                pass

            # start tray icon if available
            if PYSTRAY_AVAILABLE and Image is not None:
                try:
                    # simple circular icon using theme color
                    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    draw.ellipse((6, 6, 58, 58), fill=(0, 245, 255, 255))
                    # make "Restaurar" default action (left click)
                    menu = pystray.Menu(
                        pystray.MenuItem("Restaurar", lambda icon, item: self.root.after(0, _restore_from_tray), default=True),
                        pystray.MenuItem("Sair", lambda icon, item: self.root.after(0, _quit_from_tray))
                    )
                    self._tray_icon = pystray.Icon("jarvis", img, APP_NAME, menu)
                    threading.Thread(target=self._tray_icon.run, daemon=True).start()
                except Exception:
                    # fallback: keep window withdrawn (user can restore via taskbar)
                    pass
            else:
                # fallback: iconify (temporarily disable override to allow iconify)
                try:
                    self.root.overrideredirect(False)
                    self.root.iconify()
                except Exception:
                    pass

        # restore custom frame when window is mapped/deiconified
        def _on_map(event=None):
            try:
                self.root.overrideredirect(True)
                # se mapeado enquanto estava na bandeja/icone, restaura AI também
                if hasattr(self, "_tray_icon") and self._tray_icon:
                    # mapa vindo de pystray; acionamos restauração segura na thread do Tk
                    self.root.after(0, _restore_from_tray)
                else:
                    # se foi iconify fallback (taskbar), reativa AI se havíamos desativado
                    if hasattr(self, "_ai_was_available"):
                        try:
                            self.ai.available = self._ai_was_available
                            print(f"[JARVIS][AI] restaurado via taskbar. available={self.ai.available}")
                            del self._ai_was_available
                        except Exception:
                            pass
                    # garantir que volte a ficar on-top quando mapeado
                    try:
                        self.root.attributes("-topmost", True)
                    except Exception:
                        pass
            except Exception:
                pass

        self.root.bind("<Map>", _on_map)
        
        # -------------------------
        # presença mínima / presença ativa
        # -------------------------
        self._presence_minimal = False
        self._last_interaction = time.time()

        def _reset_presence_timer_event(event=None):
            try:
                # atualiza timer de interação; NÃO sai da presença mínima aqui
                self._last_interaction = time.time()
            except Exception:
                pass

        # (removido binding global de clique para evitar conflito com botões/top_bar)

        def _enter_minimal_presence():
             if self._presence_minimal:
                 return
             self._presence_minimal = True
             try:
                 # guarda geometria atual para restaurar depois
                 try:
                     self._prev_geom = self.root.geometry()
                 except Exception:
                     self._prev_geom = None

                 # esconde todo o conteúdo (mantém apenas top_bar)
                 try:
                     self.content.pack_forget()
                 except Exception:
                     pass

                 # reduzir opacidade e forçar on-top
                 try:
                     self.root.attributes("-alpha", 0.65)
                     self.root.attributes("-topmost", True)
                 except Exception:
                     pass

                 # reduzir tamanho da janela para mostrar apenas o título
                 try:
                     self.root.update_idletasks()
                     w = max(self.top_bar.winfo_reqwidth() + 8, 200)
                     h = self.top_bar.winfo_reqheight() + 4
                     self.root.geometry(f"{w}x{h}")
                 except Exception:
                     pass

                # durante presença mínima: o clique no título (title_label) restaura
                # (não fazemos bind global para não atrapalhar botões)
             except Exception:
                 pass

        def _exit_minimal_presence():
             if not self._presence_minimal:
                 return
             self._presence_minimal = False
             try:
                 # restaura conteúdo principal
                 try:
                     self.content.pack(fill="both", expand=True, padx=12, pady=(8,12))
                 except Exception:
                     pass

                 # restaura opacidade e on-top
                 try:
                     self.root.attributes("-alpha", 1.0)
                     self.root.attributes("-topmost", True)
                 except Exception:
                     pass

                 # restaura geometria previamente salva quando possível
                 try:
                     if getattr(self, "_prev_geom", None):
                         self.root.geometry(self._prev_geom)
                         del self._prev_geom
                 except Exception:
                     try:
                         self.root.geometry("560x380")
                     except Exception:
                         pass

                # não removemos bindings do top_bar/title_label aqui
                 try:
                     self.entry.focus_set()
                 except Exception:
                     pass
             except Exception:
                 pass

        def _presence_check():
             try:
                 # não faz nada enquanto estiver na bandeja
                 if getattr(self, "_tray_icon", None):
                     self.root.after(1000, _presence_check)
                     return
                 idle = time.time() - getattr(self, "_last_interaction", time.time())
                 if idle > 30 and not self._presence_minimal:
                     _enter_minimal_presence()
                 # não forçamos saída da presença mínima por movimento/tecla; só por clique
             except Exception:
                 pass
             finally:
                 self.root.after(1000, _presence_check)

         # binds que resetam o timer de presença (NÃO saem da presença mínima)
        for ev in ("<Motion>", "<KeyPress>", "<Enter>", "<FocusIn>"):
             try:
                 self.root.bind(ev, _reset_presence_timer_event)
             except Exception:
                 pass
        try:
             self.entry.bind("<Key>", _reset_presence_timer_event)
        except Exception:
             pass

        # => não bindamos clique globalmente; usaremos o título para entrar/sair do modo mínimo

        # inicia checagem periódica de presença
        self.root.after(1000, _presence_check)

        # --- drag support for custom titlebar ---
        def _start_move(event):
            self._drag_x = event.x
            self._drag_y = event.y

        def _do_move(event):
            x = event.x_root - getattr(self, "_drag_x", 0)
            y = event.y_root - getattr(self, "_drag_y", 0)
            self.root.geometry(f"+{x}+{y}")

        def _on_title_release(event):
             try:
                # considera clique se pouco movimento entre press/release
                dx = abs(event.x - getattr(self, "_drag_x", event.x))
                dy = abs(event.y - getattr(self, "_drag_y", event.y))
                if dx <= 5 and dy <= 5:
                    # alterna: se já está em presença mínima, sai; caso contrário, entra
                    if self._presence_minimal:
                        _exit_minimal_presence()
                    else:
                        _enter_minimal_presence()
             except Exception:
                 pass

        # top custom title bar
        self.top_bar = tk.Frame(self.root, bg=BG_COLOR, height=34)
        self.top_bar.pack(fill="x", side="top")
        self.top_bar.bind("<ButtonPress-1>", _start_move)
        self.top_bar.bind("<B1-Motion>", _do_move)

        title_label = tk.Label(
            self.top_bar,
            text=APP_NAME,
            fg=FG_COLOR,
            bg=BG_COLOR,
            font=FONT_TITLE
        )
        title_label.pack(side="left", padx=10)
        title_label.bind("<ButtonPress-1>", _start_move)
        title_label.bind("<B1-Motion>", _do_move)
        title_label.bind("<ButtonRelease-1>", _on_title_release)

        # buttons (minimize, close) on top-right
        btn_frame = tk.Frame(self.top_bar, bg=BG_COLOR)
        btn_frame.pack(side="right", padx=6)

        def _on_hover_enter(btn, color="#2b2b2b"):
            btn.configure(bg=color)
        def _on_hover_leave(btn, color=BG_COLOR):
            btn.configure(bg=color)

        min_btn = tk.Button(
            btn_frame, text="—", command=_minimize_to_tray,
            bg=BG_COLOR, fg=FG_COLOR, bd=0, relief="flat",
            activebackground="#1a1a1a", padx=10, pady=2
        )
        min_btn.pack(side="left", padx=(0,6))
        min_btn.bind("<Enter>", lambda e, b=min_btn: _on_hover_enter(b, "#12343a"))
        min_btn.bind("<Leave>", lambda e, b=min_btn: _on_hover_leave(b))

        close_btn = tk.Button(btn_frame, text="✕", command=self.root.destroy,
                              bg=BG_COLOR, fg=FG_COLOR, bd=0, relief="flat",
                              activebackground="#5a0000", padx=10, pady=2)
        close_btn.pack(side="left")
        close_btn.bind("<Enter>", lambda e, b=close_btn: _on_hover_enter(b, "#5a0000"))
        close_btn.bind("<Leave>", lambda e, b=close_btn: _on_hover_leave(b))

        # content area
        self.content = tk.Frame(self.root, bg=BG_COLOR)
        self.content.pack(fill="both", expand=True, padx=12, pady=(8,12))

        # helper to draw rounded rect on a canvas
        def _draw_rounded_rect(canvas, x1, y1, x2, y2, r=14, **kwargs):
            # arcs
            canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, style="pieslice", **kwargs)
            # rectangles to fill edges
            canvas.create_rectangle(x1+r, y1, x2-r, y2, **kwargs)
            canvas.create_rectangle(x1, y1+r, x2, y2-r, **kwargs)

        # Chat area with rounded background
        self.chat_canvas = tk.Canvas(self.content, bg=BG_COLOR, highlightthickness=0)
        self.chat_canvas.pack(fill="both", expand=True, side="top", pady=(0,8))

        # ScrolledText overlay (styled to blend with rounded background)
        # use a frame + Text + custom thin Scrollbar to better match the UI
        self._chat_frame = tk.Frame(self.chat_canvas, bg=BG_COLOR)
        self.chat = tk.Text(
            self._chat_frame,
            bg="#071025",
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            font=FONT_MAIN,
            wrap="word",
            state="disabled",
            bd=0,
            highlightthickness=0
        )
        # Custom thin scrollbar implemented with a Canvas to match the UI
        class CustomScrollbar(tk.Canvas):
            def __init__(self, parent, command=None, width=10, track="#071025", thumb=FG_COLOR, **kw):
                super().__init__(parent, width=width, bg=parent["bg"], highlightthickness=0, bd=0, **kw)
                self.command = command
                self.track_color = track
                self.thumb_color = thumb
                self.width_val = width
                self.thumb = None
                self._drag = False
                self._yoff = 0
                self.bind("<Configure>", self._redraw)
                self.bind("<Button-1>", self._click)
                self.bind("<B1-Motion>", self._drag_move)
                self.bind("<ButtonRelease-1>", self._end_drag)

            def _redraw(self, event=None):
                self.delete("all")
                h = self.winfo_height()
                w = self.winfo_width()
                # track
                self.create_rectangle(0, 0, w, h, fill=self.track_color, outline=self.track_color)
                # ensure thumb exists
                if self.thumb is None:
                    # default small thumb until set() is called
                    th = max(24, int(h*0.1))
                    self.thumb = self.create_rectangle(2, 2, w-2, th, fill=self.thumb_color, outline=self.thumb_color, tags="thumb")

            def set(self, first, last):
                try:
                    f = float(first)
                    l = float(last)
                except Exception:
                    return
                h = max(1, self.winfo_height())
                th = max(16, int((l - f) * h))
                th = min(h, th)
                # map document fraction -> canvas position (use full height for correct bottom)
                y1 = int(f * h)
                y1 = max(0, min(h - th, y1))
                y2 = y1 + th
                self.delete("thumb")
                self.thumb = self.create_rectangle(2, y1, self.winfo_width()-2, y2, fill=self.thumb_color, outline=self.thumb_color, tags="thumb")

            def _click(self, event):
                # if clicked on thumb, start drag; else jump to position
                items = self.find_withtag("current")
                if items and "thumb" in self.gettags(items[0]):
                    self._drag = True
                    bx1, by1, bx2, by2 = self.bbox(self.thumb)
                    self._yoff = event.y - by1
                else:
                    h = self.winfo_height()
                    th = max(1, self.bbox(self.thumb)[3] - self.bbox(self.thumb)[1]) if self.thumb else max(1, int(0.1*h))
                    # place thumb center at click and convert to document fraction using full height
                    y = event.y - th/2
                    y = max(0, min(h - th, y))
                    frac = y / max(1, h)
                    if self.command:
                        try:
                            self.command("moveto", str(frac))
                        except Exception:
                            # fallback to moveto callable if bound differently
                            try:
                                self.command(frac)
                            except Exception:
                                pass

            def _drag_move(self, event):
                if not self._drag:
                    return
                h = self.winfo_height()
                bx1, by1, bx2, by2 = self.bbox(self.thumb)
                th = by2 - by1
                # compute top position from mouse, clamp to track, then map to document fraction by dividing by full height
                y = event.y - self._yoff
                y = max(0, min(h - th, y))
                frac = y / max(1, h)
                frac = max(0.0, min(1.0, frac))
                if self.command:
                    try:
                        self.command("moveto", str(frac))
                    except Exception:
                        try:
                            self.command(frac)
                        except Exception:
                            pass

            def _end_drag(self, event):
                self._drag = False

        # instantiate custom scrollbar and wire it to the Text widget
        self._chat_scroll = CustomScrollbar(self._chat_frame, command=self.chat.yview, width=10, track="#071025", thumb=FG_COLOR)
        self.chat.config(yscrollcommand=self._chat_scroll.set)
        # pack inside the frame so the create_window placement still works
        self._chat_scroll.pack(side="right", fill="y", padx=(6,0))
        self.chat.pack(side="left", fill="both", expand=True)

        # Entry area with rounded background (increased height)
        self.entry_canvas = tk.Canvas(self.content, bg=BG_COLOR, height=48, highlightthickness=0)
        self.entry_canvas.pack(fill="x", side="bottom")

        self.entry = tk.Entry(
            self.entry_canvas,
            bg=ENTRY_BG,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            font=FONT_MAIN,
            bd=0,
            highlightthickness=0,
            relief="flat"
        )

        # place widgets inside canvases using create_window and redraw shapes on resize
        def _layout_chat(event=None):
            w = self.chat_canvas.winfo_width()
            h = self.chat_canvas.winfo_height()
            if w <= 0 or h <= 0:
                return
            self.chat_canvas.delete("bg_round")
            pad = 8
            _draw_rounded_rect(self.chat_canvas, pad, pad, w - pad, h - pad, r=14, fill="#071025", tags="bg_round", outline="")
            # ensure bg sits under the scrolledtext window (fix cover-on-resize bug)
            if hasattr(self, "_chat_window_id"):
                self.chat_canvas.tag_lower("bg_round", self._chat_window_id)
            # place the frame (which contains Text + Scrollbar)
            frame_w = w - 2*(pad+6)
            frame_h = h - 2*(pad+6)
            if not hasattr(self, "_chat_window_id"):
                self._chat_window_id = self.chat_canvas.create_window(pad+6, pad+6, anchor="nw", window=self._chat_frame, width=frame_w, height=frame_h)
            else:
                self.chat_canvas.coords(self._chat_window_id, pad+6, pad+6)
                self.chat_canvas.itemconfigure(self._chat_window_id, width=frame_w, height=frame_h)

        def _layout_entry(event=None):
            w = self.entry_canvas.winfo_width()
            h = self.entry_canvas.winfo_height()
            if w <= 0 or h <= 0:
                return
            self.entry_canvas.delete("bg_round")
            pad = 6
            _draw_rounded_rect(self.entry_canvas, pad, pad, w - pad, h - pad, r=12, fill=ENTRY_BG, tags="bg_round", outline="")
            # ensure bg sits under the entry window (fix cover-on-resize bug)
            if hasattr(self, "_entry_window_id"):
                self.entry_canvas.tag_lower("bg_round", self._entry_window_id)
            if not hasattr(self, "_entry_window_id"):
                # place entry centered vertically with a left margin
                self._entry_window_id = self.entry_canvas.create_window(12, h//2, anchor="w", window=self.entry, width=w - 24, height=h - 12)
            else:
                self.entry_canvas.coords(self._entry_window_id, 12, h//2)
                self.entry_canvas.itemconfigure(self._entry_window_id, width=w - 24, height=h - 12)

        self.chat_canvas.bind("<Configure>", _layout_chat)
        self.entry_canvas.bind("<Configure>", _layout_entry)

        # ensure layout is created immediately and entry is focused
        self.root.update_idletasks()
        _layout_chat()
        _layout_entry()
        try:
            self.entry.focus_set()
        except Exception:
            pass

        # keep previous bindings/behavior
        self.entry.bind("<Return>", self.send)

        # initial messages
        if self.ai.available == True:
            self.say("JARVIS online. Digite um comando ou mensagem.")
        else:
            self.say("JARVIS online. Apenas comandos.")

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

        text_lower = text.lower()
        direct_keywords = (
            "abrir ", "abra ", "pesquisar ", "pesquise ",
            "youtube ", "yt ", "digitar ", "digite ", "ajuda", "help", "?",
            "ytvideo ", "ytv "
        )

        # Trata comandos diretos mesmo se o modelo IA estiver disponível
        if text.startswith("/") or text_lower.startswith(direct_keywords) or text_lower in ("limpar", "cls"):
            # se já começar com '/', encaminha tal qual; senão adiciona '/' para compatibilidade com handle_direct
            if text.startswith("/"):
                self.router.handle_direct(text)
            else:
                self.router.handle_direct("/" + text)
            return

        # se o modelo local não estiver disponível, informa e sai
        if not self.ai.available:
            self.say("Modelo local indisponível. Para comandos, comece por: abrir, pesquisar, youtube, digitar, limpar.")
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