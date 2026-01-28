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
# IMPORTAÇÕES PARA VOZ
# =========================
try:
    import sounddevice as sd
    import numpy as np
    from scipy.io.wavfile import write
    import whisper
    import tempfile
    import keyboard
    VOICE_AVAILABLE = True
except Exception:
    sd = None
    np = None
    write = None
    whisper = None
    tempfile = None
    keyboard = None
    VOICE_AVAILABLE = False

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

Você pode responder uma Conversa normal.

Sua personalidade é baseada na do JARVIS, do filme homem de ferro.

O nome do seu mestre é Filipe

Responda somente em português brasileiro

Não utilize emogis

Seja educado, formal e objetivo nas respostas, evite pensar demais sem necessidade real
"""

# =========================
# SISTEMA DE VOZ
# =========================
class VoiceSystem:
    def __init__(self, jarvis_app):
        self.jarvis = jarvis_app
        self.is_recording = False
        self.frames = []
        self.stream = None
        self.model = None
        
        # Configurações de gravação
        self.sample_rate = 16000
        self.channels = 1
        self.blocksize = 1024
        
        # Configurações de detecção de silêncio
        self.silence_threshold = 0.01
        self.silence_duration = 1.5
        self.min_recording_time = 0.5
        
        # Controle de silêncio
        self.last_sound_time = None
        self.silence_counter = 0
        
        # Carregar modelo whisper em thread separada
        self.model_loaded = False
        self.loading_thread = None
        
        if VOICE_AVAILABLE:
            self.setup_voice()
    
    def setup_voice(self):
        """Configura o sistema de voz"""
        try:
            # Inicia carregamento do modelo em thread separada
            self.loading_thread = threading.Thread(target=self.load_model, daemon=True)
            self.loading_thread.start()
            
            # Configura hotkey
            keyboard.add_hotkey('ctrl+alt+v', self.toggle_recording)
            
            print("Sistema de voz inicializado. Pressione CTRL+ALT+V para falar.")
        except Exception as e:
            print(f"Erro ao configurar sistema de voz: {e}")
    
    def load_model(self):
        """Carrega o modelo whisper"""
        try:
            print("🧠 Carregando modelo de voz...")
            self.model = whisper.load_model("small")
            self.model_loaded = True
            print("Modelo de voz carregado com sucesso!")
        except Exception as e:
            print(f"Erro ao carregar modelo de voz: {e}")
            self.model_loaded = False
    
    def toggle_recording(self):
        """Alterna entre iniciar e parar gravação"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """Inicia a gravação do áudio"""
        if self.is_recording:
            return
            
        if not self.model_loaded and VOICE_AVAILABLE:
            # Tenta carregar modelo se ainda não estiver carregado
            self.load_model()
            if not self.model_loaded:
                self.jarvis.say("Modelo de voz ainda não carregado. Aguarde...")
                return
        
        # Restaura janela se estiver minimizada e reativa IA se necessário
        self.jarvis.restore_and_activate_ai()
        
        # Inicia gravação
        self.is_recording = True
        self.frames = []
        self.last_sound_time = time.time()
        self.silence_counter = 0
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.blocksize,
                callback=self.audio_callback
            )
            self.stream.start()
            
            # Inicia thread para verificar silêncio
            self.silence_thread = threading.Thread(target=self.check_silence, daemon=True)
            self.silence_thread.start()
            
            # Feedback visual
            self.jarvis.root.after(0, self.jarvis.show_recording_status, True)
            
        except Exception as e:
            self.jarvis.say(f"Erro ao iniciar gravação: {e}")
            self.is_recording = False
    
    def audio_callback(self, indata, frames, time_info, status):
        """Callback para processar dados de áudio"""
        if status:
            print(f"Status da gravação: {status}")
        
        # Adiciona os dados ao buffer
        self.frames.append(indata.copy())
        
        # Calcula o volume atual (RMS)
        volume = np.sqrt(np.mean(indata**2))
        
        # Atualiza o tempo do último som ouvido
        if volume > self.silence_threshold:
            self.last_sound_time = time.time()
            self.silence_counter = 0
        else:
            self.silence_counter += 1
    
    def check_silence(self):
        """Verifica continuamente se houve silêncio prolongado"""
        while self.is_recording:
            if self.last_sound_time and len(self.frames) > 0:
                # Calcula tempo desde o último som
                time_since_sound = time.time() - self.last_sound_time
                
                # Calcula duração atual da gravação
                current_duration = len(self.frames) * self.blocksize / self.sample_rate
                
                # Condições para parar:
                # 1. Silêncio prolongado E gravação tem duração mínima
                # 2. Ou tempo máximo de segurança (30 segundos)
                if (time_since_sound > self.silence_duration and 
                    current_duration > self.min_recording_time):
                    self.stop_recording()
                    break
                elif current_duration > 30:  # Segurança: máximo 30 segundos
                    self.stop_recording()
                    break
            
            time.sleep(0.1)
    
    def stop_recording(self):
        """Para a gravação e processa o áudio"""
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        # Para e fecha o stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        # Aguarda um pouco para garantir que tudo parou
        time.sleep(0.1)
        
        # Remove feedback visual
        self.jarvis.root.after(0, self.jarvis.show_recording_status, False)
        
        # Processa o áudio se houver dados suficientes
        if self.frames and len(self.frames) > 10:
            threading.Thread(target=self.process_audio, daemon=True).start()
        else:
            self.jarvis.say("Áudio muito curto ou nenhum áudio gravado")
    
    def process_audio(self):
        """Processa o áudio gravado e transcreve"""
        try:
            # Combina todos os frames
            audio_data = np.concatenate(self.frames, axis=0)
            
            # Calcula duração
            duration = len(audio_data) / self.sample_rate
            print(f"⏱️  Duração do áudio: {duration:.2f} segundos")
            
            # Verifica se há áudio válido
            if duration < self.min_recording_time:
                self.jarvis.say(f"Áudio muito curto ({duration:.2f}s)")
                return
            
            # Normaliza o áudio
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val
            else:
                self.jarvis.say("Áudio muito silencioso, fale mais alto")
                return
            
            # Cria arquivo temporário
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_filename = temp_file.name
            temp_file.close()
            
            # Salva o áudio
            write(temp_filename, self.sample_rate, (audio_data * 32767).astype(np.int16))

            # Transcreve
            result = self.model.transcribe(
                temp_filename,
                language="pt",
                fp16=False,
                task="transcribe"
            )
            
            texto = result["text"].strip()
            # REMOVER apenas ! ? , mantendo acentos
            texto = re.sub(r'[!,]', '', texto)
            
            # Remove arquivo temporário
            try:
                os.unlink(temp_filename)
            except:
                pass
            
            # Envia texto para o chat
            if texto:
                self.jarvis.root.after(0, self.jarvis.process_voice_input, texto)
            else:
                self.jarvis.say("Não foi possível transcrever o áudio")
            
        except Exception as e:
            print(f"Erro ao processar áudio: {e}")
            self.jarvis.say("Erro ao processar áudio")

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
    def __init__(self, url: str = None, model: str = None):
        base_url = url or os.getenv("OLLAMA_URL") or "http://localhost:11434/api/chat"
        self.model = model or os.getenv("OLLAMA_MODEL") or "deepseek-r1:8b"

        parsed = urllib.parse.urlparse(base_url)
        scheme = parsed.scheme or "http"
        netloc = parsed.netloc or parsed.path  # fallback if only host provided
        base = f"{scheme}://{netloc}"
        candidates = []
        # keep the provided URL first
        candidates.append(base_url)
        # common alternate endpoints
        candidates.extend([
            urllib.parse.urljoin(base, "/api/chat"),
            urllib.parse.urljoin(base, "/api/status"),
            urllib.parse.urljoin(base, "/api/health"),
            urllib.parse.urljoin(base, "/v1/chat"),
            urllib.parse.urljoin(base, "/")
        ])

        self.url = base_url
        self.available = False

        # tenta detectar serviço de forma robusta (aceita GET ou POST chat)
        for ep in candidates:
            try:
                if ep.endswith("/chat"):
                    payload = {
                        "model": self.model,
                        "messages": [{"role": "system", "content": "health check"}],
                        "stream": False,
                        "options": {"temperature": 0}
                    }
                    r = requests.post(ep, json=payload, timeout=2)
                else:
                    r = requests.get(ep, timeout=2)
                # considera disponível qualquer resposta não-5xx (proximal check)
                if r is not None and r.status_code < 500:
                    self.available = True
                    # prefer usar um endpoint /chat se foi bem sucedido
                    if ep.endswith("/chat"):
                        self.url = ep
                    break
            except Exception:
                continue

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

            # Sempre tratar resposta como conversa (chat). Não interpretar/retornar comandos.
            try:
                resp = r.json()
                content = resp.get("message", {}).get("content")
            except Exception:
                content = r.text

            if not content:
                content = "Resposta vazia do modelo."

            return {"action": "chat", "response": content}

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

        # Comando para cancelar resposta da IA
        if cmd in ["cancelar", "parar"]:
            self.app.cancel_ai_response()
            return True

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
        elif cmd.startswith("ytvideo ") or cmd.startswith("ytv ") or cmd.startswith("vídeo ") or cmd.startswith("o vídeo "):
            if cmd.startswith("ytvideo "):
                self._ytvideo(orig[8:])
            elif cmd.startswith("ytv "):
                self._ytvideo(orig[4:])
            elif cmd.startswith("vídeo "):
                self._ytvideo(orig[6:])
            else:
                self._ytvideo(orig[8:])
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
                "  /cancelar ou /parar - Cancela a resposta da IA\n"
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
        # suporta prefixo para abrir direto o primeiro resultado
        if q.startswith("-op"):
            op_mode = True
            q = q[3:].strip()
        elif q.startswith("abrir"):
            op_mode = True
            q = q[5:].strip()
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
        
        # Inicializa sistema de voz
        self.voice_system = None
        if VOICE_AVAILABLE:
            self.voice_system = VoiceSystem(self)

        # Intervalo de checagem de presença
        self._presence_interval = 60 if not self.ai.available else 1
        self._paused = False
        self._presence_job = None
        
        # Flag para controlar cancelamento da IA
        self._ai_cancelled = False
        self._current_ai_thread = None
        
        # Flag para controlar se a IA está pensando
        self._ai_thinking = False

        print(f"[JARVIS][AI] inicializado. available={self.ai.available}")
 
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("560x380")
        self.root.configure(bg=BG_COLOR)

        # Remove native title bar and provide custom one
        self.root.overrideredirect(True)
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
                # Restaura estado da IA
                if hasattr(self, "_ai_was_available"):
                    try:
                        self.ai.available = self._ai_was_available
                        # TENTA RECONECTAR COM O OLLAMA
                        self._reconnect_ollama()
                    except Exception:
                        pass
                    try:
                        del self._ai_was_available
                    except Exception:
                        pass
                
                print(f"[JARVIS][AI] retornando da bandeja. available={self.ai.available}")

                try:
                    if hasattr(self, "_tray_icon") and self._tray_icon:
                        try:
                            self._tray_icon.stop()
                        except Exception:
                            pass
                        self._tray_icon = None
                    self.root.deiconify()
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
                    # Retoma tarefas de background
                    try:
                        self.resume_background_tasks()
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        def _minimize_to_tray():
            # Salva disponibilidade da IA
            try:
                self._ai_was_available = getattr(self.ai, "available", False)
                # NÃO DESATIVA A IA COMPLETAMENTE, APENAS MARCA COMO DISPONÍVEL
                # Isso evita problemas de reconexão
                print(f"[JARVIS][AI] indo para a bandeja. previous_available={self._ai_was_available}")
            except Exception:
                pass

            # withdraw main window
            try:
                try:
                    self.root.attributes("-topmost", False)
                except Exception:
                    pass
                self.root.withdraw()
            except Exception:
                pass

            # pause background activity
            try:
                if hasattr(self, "pause_background_tasks"):
                    self.pause_background_tasks()
            except Exception:
                pass

            # start tray icon if available
            if PYSTRAY_AVAILABLE and Image is not None:
                try:
                    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    draw.ellipse((6, 6, 58, 58), fill=(0, 245, 255, 255))
                    menu = pystray.Menu(
                        pystray.MenuItem("Restaurar", lambda icon, item: self.root.after(0, _restore_from_tray), default=True),
                        pystray.MenuItem("Sair", lambda icon, item: self.root.after(0, _quit_from_tray))
                    )
                    self._tray_icon = pystray.Icon("jarvis", img, APP_NAME, menu)
                    threading.Thread(target=self._tray_icon.run, daemon=True).start()
                except Exception:
                    pass
            else:
                try:
                    self.root.overrideredirect(False)
                    self.root.iconify()
                except Exception:
                    pass

        # restore custom frame when window is mapped/deiconified
        def _on_map(event=None):
            try:
                self.root.overrideredirect(True)
                if hasattr(self, "_tray_icon") and self._tray_icon:
                    self.root.after(0, _restore_from_tray)
                else:
                    if hasattr(self, "_ai_was_available"):
                        try:
                            self.ai.available = self._ai_was_available
                            self._reconnect_ollama()
                            print(f"[JARVIS][AI] restaurado via taskbar. available={self.ai.available}")
                            del self._ai_was_available
                        except Exception:
                            pass
                    try:
                        if hasattr(self, "resume_background_tasks"):
                            self.resume_background_tasks()
                    except Exception:
                        pass
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
                if getattr(self, "_tray_icon", None) or getattr(self, "_paused", False):
                    # se estivermos na bandeja ou pausados, agendamos checagem mais tarde
                    try:
                        self._presence_job = self.root.after(max(1000, int(self._presence_interval * 1000)), _presence_check)
                    except Exception:
                        pass
                    return
                idle = time.time() - getattr(self, "_last_interaction", time.time())
                if idle > 30 and not self._presence_minimal:
                     _enter_minimal_presence()
                 # não forçamos saída da presença mínima por movimento/tecla; só por clique
             except Exception:
                 pass
             finally:
                 try:
                     # armazena id do job para possibilitar cancelamento quando for para bandeja
                     self._presence_job = self.root.after(int(self._presence_interval * 1000), _presence_check)
                 except Exception:
                     pass

        # pause/resume helpers para reduzir uso de CPU quando em bandeja/standby
        def pause_background_tasks():
            if getattr(self, "_paused", False):
                return
            self._paused = True
            try:
                if getattr(self, "_presence_job", None):
                    try:
                        self.root.after_cancel(self._presence_job)
                    except Exception:
                        pass
                    self._presence_job = None
            except Exception:
                pass
            try:
                # cancelar animação de "pensando"
                if getattr(self, "_thinking_job", None):
                    try:
                        self.root.after_cancel(self._thinking_job)
                    except Exception:
                        pass
                    self._thinking_job = None
            except Exception:
                pass
            try:
                self.status_label.config(text="")
            except Exception:
                pass

        def resume_background_tasks():
            if not getattr(self, "_paused", False):
                return
            self._paused = False
            # ajustar intervalo baseado na disponibilidade da IA
            try:
                self._presence_interval = 1 if getattr(self.ai, "available", False) else 60
            except Exception:
                self._presence_interval = 60
            try:
                # agendar próxima checagem usando o intervalo atual
                self._presence_job = self.root.after(int(self._presence_interval * 1000), _presence_check)
            except Exception:
                pass

        # expose pause/resume como métodos da instância
        self.pause_background_tasks = pause_background_tasks
        self.resume_background_tasks = resume_background_tasks

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
        try:
            self._presence_job = self.root.after(int(self._presence_interval * 1000), _presence_check)
        except Exception:
            try:
                self._presence_job = self.root.after(1000, _presence_check)
            except Exception:
                pass

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
        # keep reference to title and add a small status label for "pensando" animation
        self.title_label = title_label
        self.title_label.pack(side="left", padx=10)
        self.title_label.bind("<ButtonPress-1>", _start_move)
        self.title_label.bind("<B1-Motion>", _do_move)
        self.title_label.bind("<ButtonRelease-1>", _on_title_release)

        self.status_label = tk.Label(
            self.top_bar,
            text="",
            fg=FG_COLOR,
            bg=BG_COLOR,
            font=("Consolas", 10)
        )
        self.status_label.pack(side="left", padx=8)

        # Novo label para status de gravação
        self.recording_label = tk.Label(
            self.top_bar,
            text="",
            fg="#ff5555",  # Vermelho para indicar gravação
            bg=BG_COLOR,
            font=("Consolas", 10)
        )
        self.recording_label.pack(side="left", padx=8)

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
            if VOICE_AVAILABLE and self.voice_system:
                self.say("Pressione CTRL+ALT+V para falar.")
        else:
            self.say("JARVIS online. Apenas comandos.")
            if VOICE_AVAILABLE and self.voice_system:
                self.say("Pressione CTRL+ALT+V para comandos por voz.")

    def _reconnect_ollama(self):
        """Tenta reconectar com o Ollama quando a janela é restaurada"""
        try:
            print(f"[JARVIS][AI] Tentando reconectar com Ollama...")
            # Testa a conexão com o Ollama
            test_url = self.ai.url if hasattr(self.ai, 'url') else "http://localhost:11434/api/chat"
            try:
                # Tenta uma requisição simples de saúde
                r = requests.get(test_url.replace('/api/chat', '/api/version'), timeout=2)
                if r.status_code < 500:
                    print(f"[JARVIS][AI] Conexão com Ollama estabelecida. available=True")
                    self.ai.available = True
                    return True
            except Exception:
                pass
            
            # Tenta endpoints alternativos
            endpoints = [
                test_url,
                test_url.replace('/api/chat', '/api/tags'),
                test_url.replace('/api/chat', '/api/version'),
                "http://localhost:11434/api/version",
                "http://localhost:11434/api/tags",
                "http://localhost:11434/api/chat"
            ]
            
            for ep in endpoints:
                try:
                    r = requests.get(ep, timeout=2)
                    if r.status_code < 500:
                        if '/api/chat' in ep:
                            self.ai.url = ep
                        print(f"[JARVIS][AI] Ollama encontrado em {ep}")
                        self.ai.available = True
                        return True
                except Exception:
                    continue
            
            print(f"[JARVIS][AI] Não foi possível conectar ao Ollama")
            self.ai.available = False
            return False
            
        except Exception as e:
            print(f"[JARVIS][AI] Erro ao reconectar: {e}")
            self.ai.available = False
            return False

    def restore_and_activate_ai(self):
        """Reativa a IA se estiver desativada E tenta reconectar com Ollama"""
        # Se a IA foi marcada como desativada (na bandeja), reativa
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            self.ai.available = self._ai_was_available
            try:
                del self._ai_was_available
            except:
                pass
            print(f"[JARVIS][AI] IA reativada. available={self.ai.available}")
        
        # SEMPRE tenta reconectar quando a janela é restaurada
        self._reconnect_ollama()

    def cancel_ai_response(self):
        """Cancela a resposta da IA em andamento"""
        self._ai_cancelled = True
        self.stop_thinking()
        self.say("Resposta cancelada.")
        
        # Reseta a flag
        self._ai_cancelled = False

    def restore_from_tray_or_minimal(self):
        """Restaura a janela se estiver na bandeja ou em presença mínima"""
        # Se estiver na bandeja, restaura
        if hasattr(self, "_tray_icon") and self._tray_icon:
            try:
                # Primeiro, para o ícone da bandeja
                try:
                    self._tray_icon.stop()
                except:
                    pass
                self._tray_icon = None
                
                # Restaura a janela
                self.root.deiconify()
                self.root.attributes("-topmost", True)
                self.root.overrideredirect(True)
                self.root.lift()
                self.root.focus_force()
                
                # Retoma tarefas de background
                self.resume_background_tasks()
                
                # IMPORTANTE: Reconecta com o Ollama
                self._reconnect_ollama()
                
                print("[JARVIS] Janela restaurada da bandeja.")
                
            except Exception as e:
                print(f"[JARVIS] Erro ao restaurar da bandeja: {e}")
                try:
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                    self.root.lift()
                    self.root.focus_force()
                    self._reconnect_ollama()
                except:
                    pass
        
        # Se estiver em presença mínima, sai
        if self._presence_minimal:
            try:
                self._exit_minimal_presence()
                print("[JARVIS] Saindo do modo presença mínima.")
            except Exception as e:
                print(f"[JARVIS] Erro ao sair do modo presença mínima: {e}")
        
        # Traz para frente e foca
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.focus_force()
            self.entry.focus_set()
            print("[JARVIS] Janela focada.")
        except Exception as e:
            print(f"[JARVIS] Erro ao focar janela: {e}")

    def show_recording_status(self, recording):
        """Mostra ou esconde o status de gravação"""
        if recording:
            self.recording_label.config(text="● GRAVANDO")
        else:
            self.recording_label.config(text="")

    def process_voice_input(self, text):
        """Processa texto de entrada por voz"""
        # Primeiro, ativar a IA se necessário (antes de colocar no campo)
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            self.ai.available = self._ai_was_available
            try:
                del self._ai_was_available
            except:
                pass
            print(f"[JARVIS][AI] IA reativada por voz (ainda na bandeja). available={self.ai.available}")
        
        # Coloca o texto no campo de entrada
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        
        # Simula pressionar Enter para enviar
        self.send()

    def say(self, text):
        self.chat.config(state="normal")
        self.chat.insert("end", f"Jarvis > {text}\n")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def _print_user(self, text):
        self.chat.config(state="normal")
        self.chat.insert("end", f"Você > {text}\n")
        self.chat.config(state="disabled")
    
    # -- thinking / streaming helpers --
    def start_thinking(self):
        if getattr(self, "_thinking", False):
            return
        # do not start thinking animation while paused (tray/low-power)
        if getattr(self, "_paused", False):
            return
        self._thinking = True
        self._think_dots = 0
        
        # Pausa o timer de presença enquanto a IA está pensando
        if hasattr(self, "_presence_job") and self._presence_job:
            try:
                self.root.after_cancel(self._presence_job)
                self._presence_job = None
            except:
                pass
        
        def _tick():
            if not getattr(self, "_thinking", False):
                return
            dots = "." * (self._think_dots % 4)
            try:
                self.status_label.config(text=f"Pensando{dots}")
            except Exception:
                pass
            self._think_dots += 1
            self._thinking_job = self.root.after(500, _tick)
        _tick()

    def stop_thinking(self):
        self._thinking = False
        try:
            if getattr(self, "_thinking_job", None):
                self.root.after_cancel(self._thinking_job)
        except Exception:
            pass
        try:
            self.status_label.config(text="")
        except Exception:
            pass
        
        # Retoma o timer de presença após a IA parar de pensar
        if not getattr(self, "_paused", False) and not getattr(self, "_tray_icon", None):
            try:
                self._presence_job = self.root.after(int(self._presence_interval * 1000), self._presence_check)
            except:
                pass

    def start_response_stream(self):
        self.chat.config(state="normal")
        self.chat.insert("end", "Jarvis > ")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def append_response_token(self, token):
        self.chat.config(state="normal")
        self.chat.insert("end", token)
        self.chat.see("end")
        self.chat.config(state="disabled")

    def end_response_stream(self):
        self.chat.config(state="normal")
        self.chat.insert("end", "\n")
        self.chat.see("end")
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
            "ytvideo ", "ytv ", "vídeo ", "o vídeo "
        )

        # Comandos de cancelamento
        if text_lower in ["cancelar", "parar"]:
            self.cancel_ai_response()
            return

        # Trata comandos diretos
        if text.startswith("/") or text_lower.startswith(direct_keywords) or text_lower in ("limpar", "cls"):
            if text.startswith("/"):
                self.router.handle_direct(text)
            else:
                self.router.handle_direct("/" + text)
            return

        # ATENÇÃO: Agora ativamos a IA mesmo estando na bandeja
        # Mas primeiro garantimos que a IA está realmente conectada
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            self.ai.available = self._ai_was_available
            try:
                del self._ai_was_available
            except:
                pass
            print(f"[JARVIS][AI] IA reativada (ainda na bandeja). available={self.ai.available}")
        
        # AGORA: Sempre verifica a conexão antes de tentar usar a IA
        if not self.ai.available:
            # Tenta reconectar uma última vez
            if self._reconnect_ollama():
                print(f"[JARVIS][AI] Reconexão bem-sucedida!")
            else:
                self.say("Modelo local indisponível. Para comandos, comece por: abrir, pesquisar, youtube, digitar, limpar.")
                return

        # Reseta flag de cancelamento antes de iniciar nova resposta
        self._ai_cancelled = False
        
        threading.Thread(
            target=self._handle_ai,
            args=(text,),
            daemon=True
        ).start()

    def _handle_ai(self, text):
        streamed = False
        cancelled = False
        
        try:
            # VERIFICAÇÃO CRÍTICA: A IA deve estar disponível
            if not self.ai.available:
                print(f"[JARVIS][AI] ERRO: IA não disponível para processar: '{text}'")
                self.root.after(0, lambda: self.say("IA não disponível no momento. Tente novamente."))
                return
            
            print(f"[JARVIS][AI] Processando pergunta: '{text}'")
            
            # Prepara a UI para streaming
            self.root.after(0, self.start_thinking)
            
            # Restaura a janela ANTES de fazer qualquer requisição
            self.root.after(0, self.restore_from_tray_or_minimal)
            
            # Pequena pausa para garantir que a janela foi restaurada
            time.sleep(0.3)
            
            # Inicia a resposta
            self.root.after(0, self.start_response_stream)

            def on_token(token):
                if getattr(self, "_ai_cancelled", False):
                    return False
                try:
                    self.root.after(0, lambda t=token: self.append_response_token(t))
                except Exception:
                    pass
                return True

            # Tenta streaming primeiro
            try:
                print(f"[JARVIS][AI] Iniciando streaming para: '{text}'")
                print(f"[JARVIS][AI] URL: {self.ai.url}, Modelo: {self.ai.model}")
                
                messages = [
                    {"role": "system", "content": JARVIS_PERSONALITY},
                    {"role": "user", "content": text}
                ]

                payload = {
                    "model": self.ai.model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.7
                    }
                }

                print(f"[JARVIS][AI] Enviando requisição...")
                with requests.post(self.ai.url, json=payload, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    print(f"[JARVIS][AI] Resposta recebida, status: {r.status_code}")
                    
                    for line in r.iter_lines():
                        if not line:
                            continue
                        if self._ai_cancelled:
                            cancelled = True
                            break
                        
                        line_str = line.decode('utf-8')
                        try:
                            data = json.loads(line_str)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                if not on_token(token):
                                    cancelled = True
                                    break
                        except json.JSONDecodeError as e:
                            print(f"[JARVIS][AI] Erro ao decodificar JSON: {e}, linha: {line_str}")
                            continue
                
                streamed = True
                print(f"[JARVIS][AI] Streaming concluído com sucesso")
                
            except requests.exceptions.ConnectionError as e:
                print(f"[JARVIS][AI] Erro de conexão: {e}")
                # Marca IA como indisponível
                self.ai.available = False
                streamed = False
            except requests.exceptions.Timeout as e:
                print(f"[JARVIS][AI] Timeout: {e}")
                streamed = False
            except Exception as e:
                print(f"[JARVIS][AI] Erro no streaming: {type(e).__name__}: {e}")
                if not self._ai_cancelled:
                    streamed = False
                else:
                    cancelled = True
                    
        except Exception as e:
            print(f"[JARVIS][AI] Erro geral no _handle_ai: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            streamed = False
            
        finally:
            if streamed and not cancelled:
                try:
                    self.root.after(0, self.end_response_stream)
                    print(f"[JARVIS][AI] Resposta finalizada via streaming")
                except Exception:
                    pass
                try:
                    self.root.after(0, self.stop_thinking)
                except Exception:
                    pass
                return
            elif cancelled:
                try:
                    self.root.after(0, lambda: self.say("Resposta cancelada."))
                except Exception:
                    pass
                try:
                    self.root.after(0, self.stop_thinking)
                except Exception:
                    pass
                return

        # Fallback: método síncrono (sem streaming)
        print(f"[JARVIS][AI] Tentando fallback síncrono...")
        
        if self._ai_cancelled:
            self.root.after(0, lambda: self.say("Resposta cancelada."))
            self.root.after(0, self.stop_thinking)
            return
            
        try:
            print(f"[JARVIS][AI] Chamando ai.decide()...")
            decision = self.ai.decide(text)
            print(f"[JARVIS][AI] Resposta do decide(): {decision}")
            
            if not self._ai_cancelled:
                if decision.get("action") == "chat":
                    response = decision.get("response", "")
                    if response:
                        self.root.after(0, lambda: self.say(response))
                        print(f"[JARVIS][AI] Resposta exibida via fallback")
                    else:
                        self.root.after(0, lambda: self.say("Desculpe, não consegui gerar uma resposta."))
                        print(f"[JARVIS][AI] Resposta vazia do fallback")
                else:
                    self.root.after(0, lambda: self.router.execute(decision))
            else:
                self.root.after(0, lambda: self.say("Resposta cancelada."))
        except Exception as e:
            print(f"[JARVIS][AI] Erro no fallback: {type(e).__name__}: {e}")
            if not self._ai_cancelled:
                self.root.after(0, lambda: self.say(f"Erro ao processar sua solicitação: {type(e).__name__}"))
            else:
                self.root.after(0, lambda: self.say("Resposta cancelada."))       
        finally:
            try:
                self.root.after(0, self.stop_thinking)
            except Exception:
                pass

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
    # Verificar dependências de voz
    if not VOICE_AVAILABLE:
        print("⚠️  Bibliotecas de voz não disponíveis. Instale com:")
        print("   pip install sounddevice numpy scipy openai-whisper keyboard")
        print("   A funcionalidade de voz será desativada.")
    
    JarvisApp().run()