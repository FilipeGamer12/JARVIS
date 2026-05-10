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
import sys
import importlib.util
import traceback
import unicodedata
from typing import Dict, List, Any, Optional
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
    import platform
    if platform.system() == "Windows":
        import winsound
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

ADDON_DIRECT_KEYWORDS = {}

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
# SISTEMA DE ADDONS
# =========================
class AddonManager:
    """Gerencia o carregamento e execução de addons"""
    
    def __init__(self, jarvis_app):
        self.jarvis = jarvis_app
        self.addons: Dict[str, Any] = {}
        self.loaded_addons: List[str] = []
        self.failed_addons: List[Dict[str, str]] = []
        self.addon_direct_keywords = []
        self.direct_keyword_handlers = {}
        
        try:
            from PYbrowser import TerminalSearchBrowser
            self.browser = TerminalSearchBrowser(max_results=5)
        except Exception as e:
            print(f"[JARVIS] PYbrowser indisponível: {e}")
            self.browser = None
        
        # Hooks disponíveis para os addons
        self.hooks = {
            'pre_init': [],      # Executado antes da inicialização do Jarvis
            'post_init': [],     # Executado após a inicialização do Jarvis
            'pre_command': [],   # Executado antes de processar um comando
            'post_command': [],  # Executado após processar um comando
            'pre_send': [],      # Executado antes de enviar mensagem para IA
            'post_send': [],     # Executado após enviar mensagem para IA
            'pre_say': [],       # Executado antes de exibir mensagem no chat
            'post_say': [],      # Executado após exibir mensagem no chat
        }
        
        # Comandos registrados pelos addons
        self.custom_commands: Dict[str, Dict] = {}
        
    def scan_addons(self) -> List[str]:
        """Escaneia a pasta atual por arquivos addon_*.py"""
        addon_files = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        for filename in os.listdir(current_dir):
            if filename.startswith("addon_") and filename.endswith(".py"):
                addon_path = os.path.join(current_dir, filename)
                addon_files.append(addon_path)
                
        return addon_files
    
    def load_addon(self, addon_path: str) -> bool:
        """Carrega um addon específico"""
        try:
            # Extrai nome do addon do arquivo
            filename = os.path.basename(addon_path)
            addon_name = filename[6:-3]  # Remove "addon_" e ".py"
            
            self.log(f"Carregando addon: {addon_name}")
            
            # Carrega o módulo
            spec = importlib.util.spec_from_file_location(f"addon_{addon_name}", addon_path)
            if spec is None:
                raise ImportError(f"Não foi possível criar spec para {addon_name}")
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"addon_{addon_name}"] = module
            
            # Define variáveis globais disponíveis para o addon
            module.jarvis = self.jarvis
            module.addon_manager = self
            module.register_command = self.register_command
            module.register_hook = self.register_hook
            module.log = self.log
            module.APP_NAME = APP_NAME
            module.BG_COLOR = BG_COLOR
            module.FG_COLOR = FG_COLOR
            
            # Executa o módulo
            spec.loader.exec_module(module)
            
            # Verifica se o addon tem função setup
            if hasattr(module, 'setup'):
                module.setup(self.jarvis, self)
                self.loaded_addons.append(addon_name)
                self.addons[addon_name] = module
                self.log(f"Addon '{addon_name}' carregado com sucesso!")
                return True
            else:
                raise ImportError(f"Addon '{addon_name}' não tem função setup()")
                
        except Exception as e:
            error_msg = f"Erro ao carregar addon {addon_path}: {str(e)}"
            self.failed_addons.append({
                'addon': os.path.basename(addon_path),
                'error': str(e),
                'traceback': traceback.format_exc()
            })
            self.log(f"Falha ao carregar addon: {error_msg}", error=True)
            return False
    
    def load_all_addons(self):
        """Carrega todos os addons disponíveis"""
        addon_files = self.scan_addons()
        self.log(f"Encontrados {len(addon_files)} arquivos de addon")
        
        for addon_file in addon_files:
            self.load_addon(addon_file)
        
        # Reporta status
        if self.loaded_addons:
            self.log(f"Addons carregados: {', '.join(self.loaded_addons)}")
            # NOVO: Log dos comandos registrados
            self.log_commands_status()
        
        if self.failed_addons:
            for failed in self.failed_addons:
                self.log(f"Falha no addon {failed['addon']}: {failed['error']}", error=True)
    
    def register_command(self, command: str, handler: callable, description: str = ""):
        """Registra um novo comando para ser usado com /"""
        if command in self.custom_commands:
            self.log(f"Aviso: Comando '{command}' já registrado, substituindo")
        
        self.custom_commands[command] = {
            'handler': handler,
            'description': description
        }
        self.log(f"Comando '/{command}' registrado")
    
    def register_direct_keyword(self, keyword, handler):
        """Registra uma nova direct keyword (sem barra)"""
        if keyword in self.direct_keyword_handlers:
            self.log(f"Aviso: Direct keyword '{keyword}' já registrada, substituindo")
        
        self.direct_keyword_handlers[keyword] = handler
        self.log(f"Direct keyword '{keyword}' registrada")
        
    def process_direct_keyword(self, text):
        """Processa uma direct keyword (comando sem barra)"""
        # Converte para minúsculas para comparação
        text_lower = text.lower().strip()
        
        # Procura por direct keywords registradas
        for keyword, handler in self.direct_keyword_handlers.items():
            # Verifica se o texto começa com a keyword
            if text_lower == keyword or text_lower.startswith(keyword + " "):
                try:
                    # Chama o handler com o texto completo
                    handler(text)
                    return True  # Indica que processou com sucesso
                except Exception as e:
                    self.log(f"Erro ao processar direct keyword '{keyword}': {str(e)}", error=True)
                    return False
        
        return False  # Nenhuma direct keyword encontrada
    
    def register_hook(self, hook_name: str, handler: callable):
        """Registra um handler para um hook específico"""
        if hook_name in self.hooks:
            self.hooks[hook_name].append(handler)
            self.log(f"Hook '{hook_name}' registrado")
        else:
            self.log(f"Aviso: Hook '{hook_name}' não existe")
    
    def execute_hooks(self, hook_name: str, *args, **kwargs) -> Any:
        """Executa todos os handlers registrados para um hook"""
        if hook_name not in self.hooks:
            return None
            
        results = []
        for handler in self.hooks[hook_name]:
            try:
                result = handler(*args, **kwargs)
                if result is not None:
                    results.append(result)
            except Exception as e:
                self.log(f"Erro no hook '{hook_name}': {str(e)}", error=True)
        
        return results
    
    def log(self, message: str, error: bool = False):
        """Loga mensagens do addon manager"""
        prefix = "[AddonManager] " if not error else "[AddonManager ERRO] "
        print(f"{prefix}{message}")
    
    def log_commands_status(self):
        """Loga o status dos comandos registrados"""
        self.log(f"Comandos com barra registrados: {list(self.custom_commands.keys())}")
        if hasattr(self, 'direct_keyword_handlers'):
            self.log(f"Direct keywords registradas: {list(self.direct_keyword_handlers.keys())}")

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
        self.silence_threshold = 0.001
        self.silence_duration = 3.0
        self.min_recording_time = 1.0
        
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
    
    def _play_start_sound(self):
        """Toca um som curto padrão do sistema para indicar início da gravação."""
        try:
            if platform.system() == "Windows":
                # Toca o som "SystemAsterisk" (sino suave do Windows)
                # SND_ASYNC garante que não bloqueie a gravação
                import winsound
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:  # Linux e outros
                # Tenta usar o beep do terminal ou o comando 'paplay' (PulseAudio)
                subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
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
        
        self._play_start_sound()
        
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
            # Transcreve (com tratamento de erros explícito; tenta fallback sem ffmpeg)
            try:
                result = self.model.transcribe(
                    temp_filename,
                    language="pt",
                    fp16=False,
                    task="transcribe"
                )
                texto = result.get("text", "").strip()
            except FileNotFoundError as e:
                # Provavelmente o executável ffmpeg não foi encontrado.
                print(f"Erro ao transcrever (arquivo não encontrado): {e}")
                traceback.print_exc()
                # Tenta fallback: passar o array numpy diretamente ao modelo (evita chamada ao ffmpeg)
                try:
                    print("Tentando fallback passando numpy array diretamente para o modelo...")
                    audio_arg = audio_data.flatten()
                    result = self.model.transcribe(
                        audio_arg,
                        language="pt",
                        fp16=False,
                        task="transcribe"
                    )
                    texto = result.get("text", "").strip()
                    print("Fallback de transcrição bem-sucedido.")
                except Exception as e2:
                    print(f"Fallback falhou: {e2}")
                    traceback.print_exc()
                    self.jarvis.say("Executável necessário não encontrado (ex: ffmpeg). Instale o ffmpeg e tente novamente.")
                    try:
                        os.unlink(temp_filename)
                    except Exception:
                        pass
                    return
            except Exception as e:
                print(f"Erro ao transcrever: {e}")
                traceback.print_exc()
                self.jarvis.say(f"Erro ao transcrever: {type(e).__name__}: {e}")
                try:
                    os.unlink(temp_filename)
                except Exception:
                    pass
                return

            # REMOVER apenas ! ? , mantendo acentos
            texto = re.sub(r'[!,]', '', texto)

            # Remove arquivo temporário
            try:
                os.unlink(temp_filename)
            except Exception:
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


# =========================
# PYBROWSER / CONHECIMENTO
# =========================
try:
    from PYbrowser import TerminalSearchBrowser
    PYBROWSER_AVAILABLE = True
except Exception:
    TerminalSearchBrowser = None
    PYBROWSER_AVAILABLE = False


def _normalize_for_match(value: str) -> str:
    value = value.lower().strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


class BrowserKnowledgeProvider:
    """Integra o PYbrowser para buscar contexto textual na Wikipédia."""

    def __init__(self):
        self.available = bool(PYBROWSER_AVAILABLE and TerminalSearchBrowser is not None)
        self.browser = None
        self.cache: Dict[str, Dict[str, str]] = {}

        if self.available:
            try:
                self.browser = TerminalSearchBrowser(max_results=5)
                print("[PYbrowser] Instância criada com sucesso.")
            except Exception as e:
                print(f"[PYbrowser] Falha ao inicializar: {e}")
                self.available = False
                self.browser = None

    def _search(self, query: str) -> List:
        """Realiza a busca usando o PYbrowser, com idioma pt-BR."""
        if not self.browser:
            print("[PYbrowser] Browser não disponível para busca.")
            return []

        try:
            print(f"[PYbrowser] Buscando: {query}")
            # O PYbrowser aceita idioma como parâmetro; usamos pt-BR
            results = self.browser.search(query, language="pt-BR")
            if results:
                print(f"[PYbrowser] Resultados obtidos: {len(results)}")
                for i, r in enumerate(results):
                    print(f"  [{i+1}] {r.title} - {r.url}")
            else:
                print("[PYbrowser] Nenhum resultado retornado.")
            return results
        except Exception as e:
            print(f"[PYbrowser] Erro na busca: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _extract_text(self, url: str) -> str:
        if not self.browser:
            return ""

        try:
            print(f"[PYbrowser] Extraindo texto de: {url}")
            text = self.browser.export_text(url)

            # se o texto vier vazio, tenta inferir a URL limpa da Wikipédia a partir do termo
            if not text and "uddg=" in url:
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                uddg = qs.get("uddg", [""])[0]
                if uddg and "wikipedia.org" in uddg:
                    clean_url = uddg  # URL real já está no parâmetro uddg
                    print(f"[PYbrowser] Tentando URL limpa: {clean_url}")
                    text = self.browser.export_text(clean_url)

            if not text:
                print("[PYbrowser] export_text retornou string vazia.")
            else:
                print(f"[PYbrowser] Texto extraído: {len(text)} caracteres")
            return text
        except Exception as e:
            print(f"[PYbrowser] Erro ao extrair texto: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def find_wikipedia_context(self, query: str, max_chars: int = 8000) -> Dict[str, str]:
        """
        Busca por "{termo} wikipedia", abre o primeiro resultado e extrai texto.
        Retorna um dicionário com texto bruto, url e termo usado.
        """
        normalized = query.strip()
        cache_key = _normalize_for_match(normalized)

        if cache_key in self.cache:
            cached = self.cache[cache_key]
            print(f"[PYbrowser] Cache hit para: {normalized}")
            return {
                "query": normalized,
                "search_term": cached.get("search_term", normalized),
                "url": cached.get("url", ""),
                "text": cached.get("text", ""),
                "title": cached.get("title", ""),
                "cached": True,
            }

        search_term = f"{normalized} wikipedia"
        results = self._search(search_term)

        if not results:
            data = {
                "query": normalized,
                "search_term": search_term,
                "url": "",
                "text": "",
                "title": "",
                "cached": False,
            }
            self.cache[cache_key] = data
            return data

        # Prioriza resultado com 'wikipedia' na URL ou título
        chosen = None
        for item in results:
            if "wikipedia" in item.url.lower() or "wikipedia" in item.title.lower():
                chosen = item
                print(f"[PYbrowser] Selecionado Wikipedia: {item.url}")
                break

        if chosen is None:
            print("[PYbrowser] Nenhum resultado Wikipedia exato, usando primeiro.")
            chosen = results[0]

        url = chosen.url
        title = chosen.title
        text_value = self._extract_text(url)

        if text_value:
            # Limpeza básica: reduz quebras excessivas
            text_value = re.sub(r"\n{3,}", "\n\n", text_value).strip()
            # Trunca se necessário
            if len(text_value) > max_chars:
                text_value = text_value[:max_chars].rsplit(" ", 1)[0].strip()
                print(f"[PYbrowser] Texto truncado para {max_chars} caracteres")
        else:
            print("[PYbrowser] Texto extraído vazio.")

        data = {
            "query": normalized,
            "search_term": search_term,
            "url": url,
            "text": text_value,
            "title": title,
            "cached": False,
        }
        self.cache[cache_key] = data
        return data

    def has_context(self) -> bool:
        return self.available and self.browser is not None

# =========================
# IA (OLLAMA)
# =========================

class AIEngine:
    def __init__(self, url: str = None, model: str = None):
        base_url = url or os.getenv("OLLAMA_URL") or "http://localhost:11434/api/chat"
        self.model = model or os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"

        parsed = urllib.parse.urlparse(base_url)
        scheme = parsed.scheme or "http"
        netloc = parsed.netloc or parsed.path
        base = f"{scheme}://{netloc}"
        candidates = [base_url]
        candidates.extend([
            urllib.parse.urljoin(base, "/api/chat"),
            urllib.parse.urljoin(base, "/api/status"),
            urllib.parse.urljoin(base, "/api/health"),
            urllib.parse.urljoin(base, "/v1/chat"),
            urllib.parse.urljoin(base, "/")
        ])

        self.url = base_url
        self.available = False

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

                if r is not None and r.status_code < 500:
                    self.available = True
                    if ep.endswith("/chat"):
                        self.url = ep
                    break
            except Exception:
                continue

    def _build_messages(self, user_text: str, context: str = ""):
        system = JARVIS_PERSONALITY
        if context:
            system += (
                "\n\nUse o contexto fornecido como base principal para responder."
                "\nSe o contexto não for suficiente, diga isso de forma direta."
            )

        user_payload = user_text
        if context:
            user_payload = (
                "Contexto extraído da Wikipédia:\n"
                f"{context}\n\n"
                f"Pergunta do usuário:\n{user_text}"
            )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_payload}
        ]

    def _post_chat(self, messages, stream: bool = False, temperature: float = 0.7, timeout: int = 60):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature}
        }
        return requests.post(self.url, json=payload, stream=stream, timeout=timeout)

    def plan(self, user_text: str) -> dict:
        planner_prompt = (
            "Você é o planejador de ações do JARVIS. "
            "Responda SOMENTE com JSON válido, sem markdown e sem texto extra.\n\n"
            "Formato obrigatório:\n"
            "{\n"
            '  "action": "chat|research|open|search|youtube|ytvideo|type|clear",\n'
            '  "target": "",\n'
            '  "query": "",\n'
            '  "text": "",\n'
            '  "context_query": ""\n'
            "}\n\n"
            "Regras:\n"
            "- Se o usuário pedir para pesquisar informação, explicar um tema, ou responder algo que exija conhecimento externo, use action=\"research\" e preencha query com o termo principal.\n"
            "- Se pedir para abrir algo, use action=\"open\" e target com o nome do app/arquivo.\n"
            "- Se pedir pesquisa no Google, use action=\"search\" e query.\n"
            "- Se pedir YouTube, use action=\"youtube\" ou \"ytvideo\".\n"
            "- Se pedir para digitar, use action=\"type\" e text.\n"
            "- Se pedir para limpar, use action=\"clear\".\n"
            "- Caso contrário, use action=\"chat\".\n"
        )

        messages = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": user_text}
        ]

        try:
            r = self._post_chat(messages, stream=False, temperature=0, timeout=30)
            r.raise_for_status()
            try:
                resp = r.json()
                content = resp.get("message", {}).get("content", "") or r.text
            except Exception:
                content = r.text
            data = extract_json(content)
            if not isinstance(data, dict):
                return {"action": "chat", "response": content or "Não consegui planejar a ação."}
            if not data.get("action"):
                data["action"] = "chat"
            return data
        except Exception as e:
            print(f"[JARVIS][AI] Falha no planner: {e}")
            return {"action": "chat", "response": "Não consegui interpretar sua solicitação."}

    def decide(self, user_text):
        messages = self._build_messages(user_text)

        try:
            r = self._post_chat(messages, stream=False, temperature=0.7, timeout=60)
            r.raise_for_status()

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

    def stream_chat(self, user_text, on_token, context: str = ""):
        messages = self._build_messages(user_text, context=context)

        try:
            with self._post_chat(messages, stream=True, temperature=0.7, timeout=60) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        token = json.loads(line).get("message", {}).get("content", "")
                    except Exception:
                        token = ""
                    if token:
                        on_token(token)
        except Exception as e:
            on_token(f"\n[Erro IA: {e}]")

# =========================
# COMMAND ROUTER (MODIFICADO PARA ADDONS)
# =========================


class CommandRouter:
    KNOWN_FILE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.ico',   # imagens
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', # documentos
        '.txt', '.csv', '.json', '.xml', '.md', '.py', '.js',      # texto/código
        '.zip', '.rar', '.7z', '.tar', '.gz',                      # compactados
        '.mp3', '.wav', '.ogg', '.flac',                           # áudio
        '.mp4', '.avi', '.mkv', '.mov',                            # vídeo
    }
    
    def __init__(self, app):
        self.app = app
        self.addon_manager = app.addon_manager

    def handle_direct(self, text: str) -> bool:
        if not is_safe_command(text):
            self.app.say("Comando bloqueado por segurança.")
            return True

        orig = text[1:].strip()
        cmd = orig.lower()

        hook_results = self.addon_manager.execute_hooks('pre_command', text)
        for result in hook_results:
            if result is True:
                return True

        if cmd in ["cancelar", "parar"]:
            self.app.cancel_ai_response()
            return True

        cmd_parts = cmd.split()
        if cmd_parts and cmd_parts[0] in self.addon_manager.custom_commands:
            addon_cmd = self.addon_manager.custom_commands[cmd_parts[0]]
            try:
                if len(cmd_parts) > 1:
                    addon_cmd['handler'](' '.join(cmd_parts[1:]))
                else:
                    addon_cmd['handler']('')
                return True
            except Exception as e:
                self.app.say(f"Erro ao executar comando do addon: {str(e)}")
                return True

        if cmd.startswith("abrir ") or cmd.startswith("abra "):
            self._open(orig[6:] if cmd.startswith("abrir ") else orig[5:])
        elif cmd.startswith("pesquisar ") or cmd.startswith("pesquise "):
            self._search(orig[10:] if cmd.startswith("pesquisar ") else orig[9:])
        elif cmd.startswith("youtube ") or cmd.startswith("yt "):
            self._youtube(orig[8:] if cmd.startswith("youtube ") else orig[3:])
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
            self._type(orig[8:] if cmd.startswith("digitar ") else orig[7:])
        elif cmd == "limpar" or cmd == "cls":
            self.app.clear()
        elif cmd == "ajuda" or cmd == "help" or cmd == "?":
            self._helpcmd(cmd)
        else:
            self.app.say("Comando direto não reconhecido.")

        self.addon_manager.execute_hooks('post_command', text)
        return True

    def execute(self, data: dict):
        action = data.get("action")

        if action == "chat":
            self.app.say(data.get("response", ""))
            return

        if action == "open":
            # Decisão da IA → permite abrir qualquer tipo de arquivo
            self._open(data.get("target", ""), is_ai_driven=True)
            return

        if action == "search":
            self._search(data.get("query", ""))
        elif action == "youtube":
            self._youtube(data.get("query", ""))
        elif action == "ytvideo":
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
            "  /abrir [alvo] - Abre um aplicativo, arquivo ou URL\n"
            "  /pesquisar [consulta] - Pesquisa no Google\n"
            "  /youtube [consulta] - Pesquisa no YouTube (suporta links)\n"
            "  /digitar [texto] - Digita o texto na janela alvo\n"
            "  /limpar ou /cls - Limpa o chat\n"
            "  /ytvideo [consulta] - Pesquisa avançada de vídeos no YouTube\n"
            "  /cancelar ou /parar - Cancela a resposta da IA\n"
            "  '/' só é necessário caso modelo IA esteja ativo.\n"
        )

        if self.addon_manager.custom_commands:
            help_text += "\nComandos dos addons:\n"
            for cmd_name, cmd_info in self.addon_manager.custom_commands.items():
                desc = cmd_info['description'] or "Sem descrição"
                help_text += f"  /{cmd_name} - {desc}\n"

        self.app.say(help_text)

    def _normalize(self, value: str) -> str:
        return _normalize_for_match(value)

    def _candidate_desktop_dirs(self):
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Área de Trabalho"),
            os.path.join(home, "OneDrive", "Desktop"),
            os.path.join(home, "OneDrive", "Área de Trabalho"),
        ]

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if os.path.isdir(candidate):
                yield candidate

    def _read_shortcut_target(self, path: str) -> str:
        """
        Tenta ler o alvo de um atalho .lnk.
        Se o módulo necessário não existir, apenas retorna string vazia.
        """
        if not path.lower().endswith(".lnk"):
            return ""

        try:
            import win32com.client  # type: ignore
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(path)
            return shortcut.Targetpath or ""
        except Exception:
            return ""

    def _entry_display_names(self, full_path: str):
        """
        Retorna nomes que podem ser usados para bater com a busca:
        - nome do arquivo sem extensão
        - nome completo
        - nome do alvo do atalho .lnk, quando possível
        """
        names = []

        base = os.path.basename(full_path)
        stem, ext = os.path.splitext(base)

        if stem:
            names.append(stem)

        names.append(base)

        if ext.lower() == ".lnk":
            target = self._read_shortcut_target(full_path)
            if target:
                target_base = os.path.basename(target)
                target_stem, _ = os.path.splitext(target_base)
                if target_stem:
                    names.append(target_stem)
                if target_base:
                    names.append(target_base)

        return names
    
    def _desktop_entry_priority(self, path: str) -> int:
        lower = path.lower()

        # prioridade máxima: atalhos e executáveis
        if lower.endswith(".lnk"):
            return 0
        if lower.endswith(".exe"):
            return 1

        # depois, outros arquivos
        if os.path.isfile(path):
            return 2

        # por último, pastas
        if os.path.isdir(path):
            return 3

        return 4


    def _search_desktop_entries(self, target: str, allow_all_types: bool = False):
        """
        Busca entradas na área de trabalho.
        Se allow_all_types=False: apenas .lnk e .exe (threshold padrão 0.65).
        Se allow_all_types=True: primeiro tenta apenas .lnk/.exe com threshold relaxado (0.5);
        se não encontrar, busca em todos os arquivos (imagens, docs etc.) com threshold normal.
        """
        target_norm = self._normalize(target)
        if not target_norm:
            return None

        # Fase 1: sempre busca .lnk/.exe primeiro, com threshold adaptável
        threshold_strict = 0.65
        threshold_relaxed = 0.5
        best_lnk_exe = None
        best_lnk_exe_score = 0.0

        for desktop in self._candidate_desktop_dirs():
            for root, dirs, files in os.walk(desktop):
                rel = os.path.relpath(root, desktop)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth > 2:
                    dirs[:] = []
                    continue

                # Avalia apenas .lnk e .exe
                for entry in files:
                    full_path = os.path.join(root, entry)
                    ext = os.path.splitext(entry)[1].lower()
                    if ext not in ('.lnk', '.exe'):
                        continue

                    candidates = self._entry_display_names(full_path)
                    for candidate_name in candidates:
                        candidate_norm = self._normalize(candidate_name)
                        if not candidate_norm:
                            continue

                        # match exato ou substring => score máximo
                        if target_norm == candidate_norm:
                            score = 1.0
                        elif target_norm in candidate_norm or candidate_norm in target_norm:
                            score = 1.0
                        else:
                            score = difflib.SequenceMatcher(None, target_norm, candidate_norm).ratio()

                        if score > best_lnk_exe_score:
                            best_lnk_exe_score = score
                            best_lnk_exe = full_path

        # Se encontrou um .lnk/.exe com score aceitável (dependendo do modo)
        if best_lnk_exe is not None:
            threshold = threshold_relaxed if allow_all_types else threshold_strict
            if best_lnk_exe_score >= threshold:
                return best_lnk_exe
            # Se allow_all_types=True e score abaixo do relaxado, não serve, continuamos para fallback amplo
            if not allow_all_types:
                # No modo restrito, se não atingiu threshold estrito, não retorna nada
                return None

        # Fase 2: fallback amplo, apenas se allow_all_types=True e não encontrou .lnk/.exe satisfatório
        if not allow_all_types:
            return None

        # Busca em todos os arquivos e pastas, agora incluindo imagens, docs etc.
        best_other = None
        best_other_score = 0.0
        best_other_priority = 99  # menor número = melhor

        for desktop in self._candidate_desktop_dirs():
            for root, dirs, files in os.walk(desktop):
                rel = os.path.relpath(root, desktop)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth > 2:
                    dirs[:] = []
                    continue

                # Ordena entradas: atalhos/exe primeiro (mas agora é fallback, eles já foram testados), depois outros
                ordered_entries = []
                for entry in files:
                    full_path = os.path.join(root, entry)
                    ext = os.path.splitext(entry)[1].lower()
                    if ext in ('.lnk', '.exe'):
                        ordered_entries.append((0, full_path))
                    else:
                        ordered_entries.append((2, full_path))
                for entry in dirs:
                    full_path = os.path.join(root, entry)
                    ordered_entries.append((3, full_path))

                ordered_entries.sort(key=lambda x: x[0])

                for priority, entry_path in ordered_entries:
                    candidates = self._entry_display_names(entry_path)
                    for candidate_name in candidates:
                        candidate_norm = self._normalize(candidate_name)
                        if not candidate_norm:
                            continue

                        if target_norm == candidate_norm:
                            score = 1.0
                        elif target_norm in candidate_norm or candidate_norm in target_norm:
                            score = 1.0
                        else:
                            score = difflib.SequenceMatcher(None, target_norm, candidate_norm).ratio()

                        # Prioridade menor é melhor; para mesma prioridade, maior score
                        if priority < best_other_priority or (priority == best_other_priority and score > best_other_score):
                            best_other_priority = priority
                            best_other_score = score
                            best_other = entry_path

        # Threshold para arquivos não executáveis: mantemos 0.65
        if best_other and best_other_score >= 0.65:
            return best_other
        return None

    def _open_local_target(self, resolved_path: str) -> bool:
        try:
            if resolved_path.startswith(("http://", "https://")):
                webbrowser.open(resolved_path)
                return True

            if os.path.exists(resolved_path):
                try:
                    os.startfile(resolved_path)
                except Exception:
                    subprocess.Popen(resolved_path, shell=True)
                return True

            subprocess.Popen(f'start "" {resolved_path}', shell=True)
            return True
        except Exception:
            try:
                webbrowser.open(resolved_path)
                return True
            except Exception:
                return False

    def _open(self, target, is_ai_driven: bool = False):
        """
        Abre um alvo (arquivo, atalho, URL).
        - is_ai_driven=True: decisão veio da IA interpretando linguagem natural → permite qualquer tipo de arquivo.
        - is_ai_driven=False (ex.: /abrir): só permite .lnk, .exe ou se extensão estiver em KNOWN_FILE_EXTENSIONS.
        """
        if not target:
            self.app.say("Nada para abrir.")
            return

        # Suporte ao comando "/abrir -?"
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

        target_clean = target.strip()

        # Determina se o usuário incluiu uma extensão conhecida (pedido explícito de arquivo)
        _, ext = os.path.splitext(target_clean)
        ext = ext.lower()
        explicit_file_request = ext in self.KNOWN_FILE_EXTENSIONS

        # Permite todos os tipos se for decisão da IA ou solicitação explícita por extensão
        allow_all = is_ai_driven or explicit_file_request

        # 1) Tenta encontrar na área de trabalho com o filtro apropriado
        desktop_match = self._search_desktop_entries(target_clean, allow_all_types=allow_all)
        if desktop_match:
            if self._open_local_target(desktop_match):
                display_name = os.path.basename(desktop_match)
                self.app.say(f"Abrindo da área de trabalho: {display_name}")
                return
            else:
                self.app.say(f"Erro ao abrir: {os.path.basename(desktop_match)}")
                return

        # 2) Tenta abrir via apps.json (apenas para atalhos/programas, sem restrições)
        apps_path = os.path.join(os.path.dirname(__file__), "apps.json")
        try:
            with open(apps_path, "r", encoding="utf-8") as f:
                apps = json.load(f)
        except Exception:
            apps = []

        target_lower = target_clean.lower()
        match = None

        if isinstance(apps, list) and apps:
            names = [a.get("name", "").lower() for a in apps]
            for a in apps:
                name = a.get("name", "").lower()
                if not name:
                    continue
                if target_lower == name or target_lower in name or name in target_lower:
                    match = a
                    break
            if not match:
                close = difflib.get_close_matches(target_lower, names, n=1, cutoff=0.6)
                if close:
                    idx = names.index(close[0])
                    match = apps[idx]

        if match:
            exec_cmd = match.get("exec") or match.get("command") or match.get("path") or ""
            if not exec_cmd:
                self.app.say(f"Entrada inválida no apps.json para {match.get('name')}")
                return

            if not self._open_local_target(exec_cmd):
                self.app.say(f"Erro ao executar entrada do apps.json: {match.get('name')}")
                return

            self.app.say(f"Abrindo: {match.get('name')}")
            return

        # 3) Tenta abrir diretamente o alvo como caminho/URL
        #    Se allow_all for True, aceita qualquer coisa; se False, só tenta se parecer executável ou atalho
        if allow_all:
            if self._open_local_target(target_clean):
                self.app.say(f"Abrindo: {target_clean}")
                return
            else:
                self.app.say(f"Erro ao abrir: {target_clean}")
                return
        else:
            # Sem permissão ampla, só tenta se for .lnk ou .exe detectado no nome
            if ext in ('.lnk', '.exe'):
                if self._open_local_target(target_clean):
                    self.app.say(f"Abrindo: {target_clean}")
                    return
                else:
                    self.app.say(f"Erro ao abrir: {target_clean}")
                    return
            else:
                self.app.say(
                    f"Não encontrei um programa ou atalho correspondente. "
                    f"Para abrir outros arquivos, especifique a extensão (ex.: 'foto.jpg') ou peça diretamente ao JARVIS."
                )
                return

    def _search(self, query):
        webbrowser.open(f"https://www.google.com/search?q={query}")
        self.app.say(f"Pesquisando no Google: {query}")

    def _youtube(self, query):
        if not query:
            self.app.say("Nada para pesquisar no YouTube.")
            return

        q = query.strip()
        m = re.search(r"(https?://\S+|www\.\S+|youtu\.be/\S+)", q)
        if m:
            url = m.group(0)
            if not url.startswith("http"):
                url = "https://" + url

            try:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if "list" in qs or "/playlist" in parsed.path:
                    webbrowser.open(url)
                    self.app.say(f"Abrindo playlist do YouTube: {url}")
                    return
                webbrowser.open(url)
                self.app.say(f"Abrindo YouTube: {url}")
                return
            except Exception as e:
                self.app.say(f"Erro ao abrir link do YouTube: {e}")
                return

        qenc = urllib.parse.quote_plus(q)
        webbrowser.open(f"https://www.youtube.com/results?search_query={qenc}")
        self.app.say(f"Pesquisando no YouTube: {q}")

    def _ytvideo(self, query):
        if not query:
            self.app.say("Nada para pesquisar no YouTube.")
            return

        q = query.strip()
        op_mode = False
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

            if op_mode:
                first_url = f"https://www.youtube.com/watch?v={ids[0]}"
                webbrowser.open(first_url)
                self.app.say(f"Abrindo primeiro vídeo: {q}")
                return

            chat = self.app.chat
            chat.config(state="normal")
            chat.insert("end", f"Jarvis > Resultados para: {q}\n")
            for i, vid in enumerate(ids, start=1):
                video_url = f"https://www.youtube.com/watch?v={vid}"
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

            chat.insert("end", "Jarvis > Clique no vídeo que desejar.\n")
            chat.see("end")
            chat.config(state="disabled")
        except Exception as e:
            self.app.say(f"Erro ao buscar vídeo: {e}")

    def _type(self, text):
        self.app.say("Posicione o cursor sobre a janela alvo e mantenha-o parado por 1s (tempo limite 20s).")
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
                    try:
                        root = self.app.root
                        x0 = root.winfo_rootx()
                        y0 = root.winfo_rooty()
                        x1 = x0 + root.winfo_width()
                        y1 = y0 + root.winfo_height()
                        if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                            self.app.say("Cursor sobre a janela do Jarvis — posicione em outra janela.")
                            start_time = time.time()
                            last_pos = pyautogui.position()
                            idle_start = None
                            continue
                    except Exception:
                        pass
                    break
            else:
                idle_start = None
                last_pos = pos

            if time.time() - start_time > timeout:
                self.app.say("Tempo esgotado. Digitação cancelada.")
                return

        try:
            pyautogui.click(last_pos)
            self.app.say("Digitando em 0.5 segundos...")
            time.sleep(0.5)
            pyautogui.write(text, interval=0.02)
            self.app.say("Texto digitado.")
        except Exception as e:
            self.app.say(f"Erro ao digitar: {e}")

# =========================
# GUI (MODIFICADA PARA ADDONS)
# =========================

class JarvisApp:
    def __init__(self):
        # Inicializa o gerenciador de addons primeiro (sem carregar ainda)
        self.addon_manager = AddonManager(self)
        
        # Executa hooks de pré-inicialização
        self.addon_manager.execute_hooks('pre_init')
        
        self.ai = AIEngine()
        self.knowledge_provider = BrowserKnowledgeProvider()
        self.router = None  # Será inicializado depois
        
        # Inicializa sistema de voz
        self.voice_system = None
        if VOICE_AVAILABLE:
            self.voice_system = VoiceSystem(self)

        # CRÍTICO: Salvar se a IA estava disponível NO INÍCIO
        self._ai_initially_available = self.ai.available
        
        # Intervalo de checagem de presença
        self._presence_interval = 60 if not self.ai.available else 1
        self._paused = False
        self._presence_job = None
        
        # Flag para controlar cancelamento da IA
        self._ai_cancelled = False
        self._current_ai_thread = None
        
        # Flag para controlar se a IA está pensando
        self._ai_thinking = False

        print(f"[JARVIS][AI] inicializado. available={self.ai.available}, initially_available={self._ai_initially_available}")

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
        
        
        def research_with_context(self, query: str) -> str:
            if not self.browser:
                return ""

            search_term = f"{query.strip()} wikipedia"
            try:
                results = self.browser.search(search_term, language="pt-BR")
                if not results:
                    return ""

                # prioriza resultado da Wikipédia
                selected = next(
                    (r for r in results if "wikipedia.org" in r.url.lower()),
                    results[0]
                )

                text = self.browser.export_text(selected.url)
                return text.strip()
            except Exception as e:
                print(f"[JARVIS] Erro ao pesquisar com PYbrowser: {e}")
                return ""
        
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
                # Restaura estado da IA APENAS se ela estava disponível inicialmente
                if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
                    # SÓ reativa se a IA estava disponível inicialmente
                    if self._ai_initially_available:
                        try:
                            self.ai.available = self._ai_was_available
                            # Tenta reconectar com o Ollama
                            self._reconnect_ollama()
                        except Exception:
                            pass
                    try:
                        del self._ai_was_available
                    except Exception:
                        pass
                
                print(f"[JARVIS][AI] retornando da bandeja. available={self.ai.available}, initially_available={self._ai_initially_available}")

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
            # Salva disponibilidade da IA APENAS se ela estava disponível inicialmente
            try:
                if self._ai_initially_available:
                    self._ai_was_available = getattr(self.ai, "available", False)
                    # NÃO desativa a IA completamente, apenas salva o estado
                    print(f"[JARVIS][AI] indo para a bandeja. previous_available={self._ai_was_available}")
                else:
                    # Se não estava disponível inicialmente, não salva nada
                    print(f"[JARVIS][AI] indo para a bandeja (IA não estava disponível inicialmente)")
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
                        # SÓ reativa se a IA estava disponível inicialmente
                        if self._ai_initially_available:
                            try:
                                self.ai.available = self._ai_was_available
                                self._reconnect_ollama()
                                print(f"[JARVIS][AI] restaurado via taskbar. available={self.ai.available}")
                            except Exception:
                                pass
                        try:
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
        
        # AGORA inicializa o router (depois que a interface foi construída)
        self.router = CommandRouter(self)
        
        # AGORA carrega os addons (depois que a interface foi completamente construída)
        self.addon_manager.load_all_addons()
        
        # Executa hooks de pós-inicialização
        self.addon_manager.execute_hooks('post_init')

        # initial messages
        if self.ai.available == True:
            self.say("JARVIS online. Digite um comando, peça uma pesquisa ou faça uma solicitação.")
            if VOICE_AVAILABLE and self.voice_system:
                self.say("Pressione CTRL+ALT+V para falar.")
        else:
            self.say("JARVIS online. Apenas comandos.")
            if VOICE_AVAILABLE and self.voice_system:
                self.say("Pressione CTRL+ALT+V para comandos por voz.")

    # NOVO MÉTODO: Verifica se pode tentar reativar a IA
    def _should_try_reactivate_ai(self):
        """Retorna True apenas se a IA estava disponível inicialmente e agora não está"""
        return self._ai_initially_available and not self.ai.available

    def _reconnect_ollama(self):
        """Tenta reconectar com o Ollama quando a janela é restaurada"""
        # SÓ tenta reconectar se a IA estava disponível inicialmente
        if not self._ai_initially_available:
            print(f"[JARVIS][AI] IA não estava disponível inicialmente, ignorando reconexão")
            return False
            
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
        """Reativa a IA se estiver desativada - APENAS se estava disponível inicialmente"""
        # SÓ reativa se a IA estava disponível inicialmente
        if not self._ai_initially_available:
            print(f"[JARVIS][AI] Ignorando reativação: IA não estava disponível inicialmente")
            return
            
        # Se a IA foi marcada como desativada (na bandeja), reativa
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            self.ai.available = self._ai_was_available
            try:
                del self._ai_was_available
            except:
                pass
            print(f"[JARVIS][AI] IA reativada. available={self.ai.available}")
        
        # Tenta reconectar quando a janela é restaurada (apenas se estava disponível inicialmente)
        if self._ai_initially_available:
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
                
                # IMPORTANTE: Reconecta com o Ollama APENAS se estava disponível inicialmente
                if self._ai_initially_available:
                    self._reconnect_ollama()
                
                print("[JARVIS] Janela restaurada da bandeja.")
                
            except Exception as e:
                print(f"[JARVIS] Erro ao restaurar da bandeja: {e}")
                try:
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                    self.root.lift()
                    self.root.focus_force()
                    if self._ai_initially_available:
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
        # Primeiro, ativar a IA se necessário - APENAS se estava disponível inicialmente
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            # SÓ tenta reativar se a IA estava disponível inicialmente
            if self._ai_initially_available:
                self.ai.available = self._ai_was_available
                try:
                    del self._ai_was_available
                except:
                    pass
                print(f"[JARVIS][AI] IA reativada por voz (ainda na bandeja). available={self.ai.available}")
            else:
                print(f"[JARVIS][AI] Ignorando reativação por voz: IA não estava disponível inicialmente")
        
        # Corrige o texto se for um comando de voz mal interpretado
        corrected_text = self.correct_voice_command(text)
        
        # Coloca o texto no campo de entrada
        self.entry.delete(0, tk.END)
        self.entry.insert(0, corrected_text)
        
        # Simula pressionar Enter para enviar
        self.send()

    def correct_voice_command(self, text):
        """Corrige um comando de voz mal interpretado usando similaridade"""
        if not text:
            return text
        
        # Lista de comandos disponíveis para comparação
        available_commands = []
        
        # 1. Comandos diretos (sem barra)
        direct_commands = [
            "limpar", "cls", "ajuda", "help", "?", "cancelar", "parar",
            "abrir", "abra", "pesquisar", "pesquise", "youtube", "yt",
            "digitar", "digite", "ytvideo", "ytv", "vídeo"
        ]
        
        # 2. Comandos com barra (sem a barra)
        slash_commands = [
            "abrir", "pesquisar", "youtube", "digitar", "limpar", 
            "ajuda", "ytvideo", "cancelar", "parar"
        ]
        
        # 3. Adiciona comandos dos addons
        if self.addon_manager.custom_commands:
            slash_commands.extend(list(self.addon_manager.custom_commands.keys()))
        
        # 4. Adiciona direct keywords dos addons
        if hasattr(self.addon_manager, 'direct_keyword_handlers'):
            direct_commands.extend(list(self.addon_manager.direct_keyword_handlers.keys()))
        
        # Verifica se o texto já é um comando válido
        text_lower = text.lower().strip()
        
        # Primeiro verifica se é um comando com barra
        if text_lower.startswith("/"):
            cmd = text_lower[1:].split()[0] if len(text_lower[1:].split()) > 0 else text_lower[1:]
            if cmd in slash_commands:
                return text  # Já é um comando válido
        else:
            # Verifica comandos diretos
            first_word = text_lower.split()[0] if len(text_lower.split()) > 0 else text_lower
            if first_word in direct_commands:
                return text  # Já é um comando válido
        
        # Se não for um comando válido, procura o mais parecido
        # Determina qual lista usar para comparação
        if text_lower.startswith("/"):
            # Comando com barra
            cmd = text_lower[1:].split()[0] if len(text_lower[1:].split()) > 0 else text_lower[1:]
            target_list = slash_commands
            prefix = "/"
        else:
            # Comando direto
            cmd = text_lower.split()[0] if len(text_lower.split()) > 0 else text_lower
            target_list = direct_commands
            prefix = ""
        
        # Encontra o comando mais parecido
        closest = difflib.get_close_matches(cmd, target_list, n=1, cutoff=0.6)
        
        if closest:
            closest_cmd = closest[0]
            # Substitui o comando no texto
            if text_lower.startswith("/"):
                # Para comandos com barra
                corrected = f"/{closest_cmd}" + text[len(prefix + cmd):]
            else:
                # Para comandos diretos
                corrected = closest_cmd + text[len(cmd):]
            
            # Informa ao usuário sobre a correção
            if text != corrected:
                self.say(f"Comando corrigido: '{text}' -> '{corrected}'")
            
            return corrected
        
        return text  # Retorna o texto original se não encontrar correção

    def say(self, text):
        """Exibe uma mensagem no chat (com suporte a hooks)"""
        # Executa hooks pre_say
        self.addon_manager.execute_hooks('pre_say', text)
        
        self.chat.config(state="normal")
        self.chat.insert("end", f"Jarvis > {text}\n")
        self.chat.see("end")
        self.chat.config(state="disabled")
        
        # Executa hooks post_say
        self.addon_manager.execute_hooks('post_say', text)

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

        text_lower = text.lower().strip()

        # ============================================
        # 1. PRIMEIRO: comandos com /
        # ============================================
        if text.startswith("/"):
            self.router.handle_direct(text)
            self.addon_manager.execute_hooks("post_send", text)
            return

        # ============================================
        # 2. SEGUNDO: direct keywords dos addons
        # ============================================
        if self.addon_manager.process_direct_keyword(text):
            self.addon_manager.execute_hooks("post_send", text)
            return

        # ============================================
        # 3. TERCEIRO: comandos locais que não devem ir para a IA
        # ============================================
        if text_lower in ("limpar", "cls"):
            self.clear()
            self.addon_manager.execute_hooks("post_send", text)
            return

        if text_lower in ("cancelar", "parar"):
            self.cancel_ai_response()
            self.addon_manager.execute_hooks("post_send", text)
            return

        if text_lower in ("ajuda", "help", "?"):
            self.router._helpcmd(text_lower)
            self.addon_manager.execute_hooks("post_send", text)
            return

        # ============================================
        # 4. QUARTO: TUDO O RESTO VAI PARA A IA
        #    A IA decide se vai:
        #    - pesquisar via PYbrowser
        #    - abrir app
        #    - digitar
        #    - responder normalmente
        # ============================================
        if hasattr(self, "_ai_was_available") and self._ai_was_available and not self.ai.available:
            if self._ai_initially_available:
                self.ai.available = self._ai_was_available
                try:
                    del self._ai_was_available
                except Exception:
                    pass
                print(f"[JARVIS][AI] IA reativada (ainda na bandeja). available={self.ai.available}")
            else:
                print("[JARVIS][AI] Ignorando reativação: IA não estava disponível inicialmente")

        if not self.ai.available:
            if self._ai_initially_available:
                if self._reconnect_ollama():
                    print("[JARVIS][AI] Reconexão bem-sucedida!")
                else:
                    mensagem_comandos = (
                        "Modelo local indisponível. "
                        "Para comandos, use: /abrir, /pesquisar, /youtube, /digitar, /limpar, /ajuda"
                    )

                    if self.addon_manager.custom_commands:
                        addon_cmds = ", ".join([f"/{cmd}" for cmd in self.addon_manager.custom_commands.keys()])
                        mensagem_comandos += f". Comandos dos addons: {addon_cmds}"

                    if hasattr(self.addon_manager, "direct_keyword_handlers") and self.addon_manager.direct_keyword_handlers:
                        direct_keys = list(self.addon_manager.direct_keyword_handlers.keys())
                        if direct_keys:
                            mensagem_comandos += f". Direct keywords: {', '.join(direct_keys)}"

                    self.say(mensagem_comandos)
                    self.addon_manager.execute_hooks("post_send", text)
                    return
            else:
                mensagem_comandos = (
                    "Modelo local indisponível. "
                    "Para comandos, use: /abrir, /pesquisar, /youtube, /digitar, /limpar, /ajuda"
                )

                if self.addon_manager.custom_commands:
                    addon_cmds = ", ".join([f"/{cmd}" for cmd in self.addon_manager.custom_commands.keys()])
                    mensagem_comandos += f". Comandos dos addons: {addon_cmds}"

                if hasattr(self.addon_manager, "direct_keyword_handlers") and self.addon_manager.direct_keyword_handlers:
                    direct_keys = list(self.addon_manager.direct_keyword_handlers.keys())
                    if direct_keys:
                        mensagem_comandos += f". Direct keywords: {', '.join(direct_keys)}"

                self.say(mensagem_comandos)
                self.addon_manager.execute_hooks("post_send", text)
                return

        # Reseta flag de cancelamento antes de iniciar nova resposta
        self._ai_cancelled = False

        threading.Thread(
            target=self._handle_ai,
            args=(text,),
            daemon=True
        ).start()

        self.addon_manager.execute_hooks("post_send", text)


    def _handle_ai(self, text):
        streamed = False
        cancelled = False

        try:
            if not self.ai.available:
                print(f"[JARVIS][AI] ERRO: IA não disponível para processar: '{text}'")
                self.root.after(0, lambda: self.say("IA não disponível no momento. Tente novamente."))
                return

            print(f"[JARVIS][AI] Processando pergunta: '{text}'")
            plan = self.ai.plan(text)
            action = (plan.get("action") or "chat").lower().strip()

            if action in {"open", "search", "youtube", "ytvideo", "type", "clear"}:
                print(f"[JARVIS][AI] Plano de ação: {action} -> {plan}")
                self.root.after(0, lambda p=plan: self.router.execute(p))
                return

            context = ""
            if action == "research":
                query = (plan.get("query") or plan.get("context_query") or text).strip()
                self.root.after(0, self.start_thinking)
                self.root.after(0, self.restore_from_tray_or_minimal)
                time.sleep(0.3)
                self.root.after(0, self.start_response_stream)

                def on_token(token):
                    if getattr(self, "_ai_cancelled", False):
                        return False
                    try:
                        self.root.after(0, lambda t=token: self.append_response_token(t))
                    except Exception:
                        pass
                    return True

                try:
                    if self.knowledge_provider and self.knowledge_provider.has_context():
                        kb = self.knowledge_provider.find_wikipedia_context(query)
                        context = kb.get("text", "") or ""
                        source_title = kb.get("title", "") or query
                        source_url = kb.get("url", "") or ""
                        if context:
                            print(f"[JARVIS][PYbrowser] Contexto obtido de: {source_url}")
                            context = (
                                f"Título da fonte: {source_title}\n"
                                f"URL: {source_url}\n\n"
                                f"{context}"
                            )
                        else:
                            print(f"[JARVIS][PYbrowser] Nenhum contexto extraído para: {query}")
                    else:
                        context = ""
                except Exception as e:
                    print(f"[JARVIS][PYbrowser] Falha ao buscar contexto: {e}")
                    context = ""

                try:
                    self.ai.stream_chat(text, on_token, context=context)
                    streamed = True
                except Exception as e:
                    print(f"[JARVIS][AI] Erro ao responder com contexto: {e}")
                    streamed = False
                finally:
                    try:
                        self.root.after(0, self.end_response_stream)
                    except Exception:
                        pass
                    try:
                        self.root.after(0, self.stop_thinking)
                    except Exception:
                        pass
                return

            self.root.after(0, self.start_thinking)
            self.root.after(0, self.restore_from_tray_or_minimal)
            time.sleep(0.3)
            self.root.after(0, self.start_response_stream)

            def on_token(token):
                if getattr(self, "_ai_cancelled", False):
                    return False
                try:
                    self.root.after(0, lambda t=token: self.append_response_token(t))
                except Exception:
                    pass
                return True

            try:
                print(f"[JARVIS][AI] Iniciando streaming para: '{text}'")
                print(f"[JARVIS][AI] URL: {self.ai.url}, Modelo: {self.ai.model}")
                self.ai.stream_chat(text, on_token)
                streamed = True
                print(f"[JARVIS][AI] Streaming concluído com sucesso")
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