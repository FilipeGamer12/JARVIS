# J.A.R.V.I.S

Assistente pessoal em Python com interface gráfica, integração com IA local via Ollama, suporte a voz, TTS, pesquisa com contexto, comandos diretos e sistema de addons.

## Visão geral

Este projeto implementa um assistente estilo J.A.R.V.I.S. com foco em uso local. A aplicação possui:

- interface gráfica em **Tkinter**
- integração com **Ollama** para chat com IA local
- roteamento de ações por IA para tarefas como abrir arquivos, pesquisar, digitar e calcular
- sistema de **voz opcional** com gravação por hotkey e transcrição automática
- sistema de **TTS** para o Jarvis responder em voz alta
- pesquisa com **contexto da Wikipédia** usando PYbrowser
- comandos diretos com `/`
- suporte a **addons** carregados automaticamente
- segurança básica contra comandos destrutivos

## Funcionalidades

### Chat com IA
O JARVIS se conecta a um servidor Ollama local e usa um modelo configurável para responder perguntas, manter conversa e decidir ações quando apropriado.

A IA pode:

- conversar normalmente
- responder com streaming
- cancelar respostas em andamento
- usar contexto externo quando necessário
- reativar a conexão com o Ollama quando a janela é restaurada, se a IA estava disponível no início

### Planejador de ações
Antes de responder, a IA pode gerar um plano estruturado para escolher entre:

- `chat`
- `research`
- `open`
- `search`
- `youtube`
- `ytvideo`
- `type`
- `clear`
- `math`

Isso permite que o Jarvis execute tarefas sem depender apenas de comandos manuais.

### Pesquisa e automação
O assistente consegue:

- pesquisar no Google
- pesquisar no YouTube
- abrir aplicativos, arquivos, atalhos e URLs
- abrir arquivos a partir da área de trabalho
- digitar texto na janela ativa
- limpar a conversa
- cancelar a resposta da IA
- executar cálculos com expressões matemáticas seguras

### Pesquisa com contexto
Quando a ação é classificada como pesquisa, o Jarvis usa o **PYbrowser** para buscar contexto na Wikipédia, extrair o texto principal e responder com base nesse conteúdo.

Esse modo inclui:

- busca em pt-BR
- cache de consultas
- extração e limpeza do texto
- resposta em streaming com o contexto carregado

### Voz
Quando as dependências de voz estão instaladas, o programa permite gravação por atalho de teclado e transcrição automática do áudio.

Atalho padrão:

- `Ctrl + Alt + V`

A gravação usa detecção de silêncio para parar automaticamente quando você termina de falar.

### TTS
O Jarvis também pode falar as respostas em voz alta.

O sistema de voz sintetizada usa:

- `edge-tts`
- `pygame`
- `pydub`

### Sistema de addons
O projeto procura automaticamente arquivos com o padrão:

- `addon_*.py`

Esses addons podem registrar:

- comandos personalizados
- hooks de eventos
- palavras-chave diretas sem `/`
- lógica extra para estender o comportamento do assistente

### Segurança
O código bloqueia alguns comandos com palavras potencialmente destrutivas, como:

- `format`
- `del`
- `rm`
- `shutdown`
- `reboot`
- `poweroff`

## Requisitos

### Obrigatórios
- Python 3.10+ recomendado
- Um servidor **Ollama** ativo localmente
- Um modelo disponível no Ollama

O modelo padrão definido no código é:

- `qwen2.5-coder:3b`

### Dependências principais
Instale com:

```bash
pip install requests pyautogui pygame pydub
```

### Dependências opcionais
Estas bibliotecas habilitam recursos adicionais:

```bash
pip install pystray pillow sounddevice numpy scipy keyboard whisper pywin32
```

Para o módulo de voz e transcrição:

```bash
pip install openai-whisper sounddevice numpy scipy keyboard
```

Para o TTS em voz alta, também é necessário:

```bash
pip install edge-tts
```

No Windows, para leitura de atalhos `.lnk`, pode ser necessário:

```bash
pip install pywin32
```

Para melhorar as respostas da IA, recomenda-se ter o **PYbrowser** disponível no mesmo diretório do projeto:

```text
https://github.com/FilipeGamer12/PYbrowser/blob/main/PYbrowser.py
```

## Dependências do sistema

### Ollama
O aplicativo tenta se conectar ao endpoint padrão:

- `http://localhost:11434/api/chat`

Se o Ollama estiver em outro endereço, ajuste a variável de ambiente `OLLAMA_URL`.

### ffmpeg
A transcrição de voz e a conversão de áudio podem precisar do `ffmpeg` instalado no sistema. O fallback existe, mas o `ffmpeg` continua sendo altamente recomendado para garantir compatibilidade.

## Instalação

1. Clone o repositório:

```bash
git clone https://github.com/FilipeGamer12/JARVIS.git
cd JARVIS
```

2. Instale as dependências principais:

```bash
pip install requests pyautogui pygame pydub
```

3. Instale os recursos opcionais, se desejar voz, tray system e transcrição:

```bash
pip install pystray pillow sounddevice numpy scipy keyboard whisper pywin32 edge-tts
```

4. Adicione `PYbrowser.py` na pasta do projeto, se quiser habilitar pesquisa com contexto.

5. Inicie o Ollama e carregue o modelo desejado.

Exemplo:

```bash
ollama run qwen2.5-coder:3b
```

6. Execute a aplicação:

```bash
python main.py
```

## Configuração

Você pode ajustar o comportamento do assistente por variáveis de ambiente:

- `OLLAMA_URL`: endpoint do servidor Ollama
- `OLLAMA_MODEL`: modelo a ser usado

Exemplo:

```bash
set OLLAMA_URL=http://localhost:11434/api/chat
set OLLAMA_MODEL=qwen2.5-coder:3b
python main.py
```

No Linux/macOS:

```bash
export OLLAMA_URL=http://localhost:11434/api/chat
export OLLAMA_MODEL=qwen2.5-coder:3b
python3 main.py
```

## Comandos disponíveis

Os comandos abaixo são reconhecidos pelo roteador do projeto.

### Comandos diretos
Use com `/` quando a IA estiver ativa:

- `/abrir [alvo]` — abre aplicativo, arquivo ou URL
- `/pesquisar [consulta]` — pesquisa no Google
- `/youtube [consulta]` — pesquisa no YouTube ou abre um link informado
- `/ytvideo [consulta]` — busca vídeos e mostra links clicáveis
- `/digitar [texto]` — digita o texto na janela ativa
- `/limpar` ou `/cls` — limpa o chat
- `/cancelar` ou `/parar` — cancela a resposta da IA
- `/ajuda` — mostra ajuda e comandos dos addons

### Exemplos
```text
/abrir bloco de notas
/pesquisar segunda guerra mundial
/youtube música lo-fi
/digitar Olá, mundo!
/ytvideo python tutorial
/math 2 + 2
```

## Sistema de addons

O aplicativo carrega automaticamente arquivos `addon_*.py` presentes na mesma pasta do `main.py`.

Um addon precisa expor uma função `setup(...)` para ser carregado corretamente.

### O que um addon pode fazer
- registrar comandos novos
- registrar hooks
- reagir antes e depois de ações do assistente
- adicionar palavras-chave diretas sem barra
- adicionar comportamento personalizado

## Estrutura esperada do projeto

```text
JARVIS/
├── main.py
├── apps.json
├── addon_*.py
├── PYbrowser.py
└── README.md
```

## Observações importantes

- O sistema de voz só funciona quando as bibliotecas necessárias estiverem instaladas.
- O TTS depende de `edge-tts`, `pygame` e `pydub`.
- O comportamento de abrir arquivos na área de trabalho prioriza atalhos `.lnk` e executáveis `.exe`.
- O comando `/abrir -?` lista as entradas disponíveis em `apps.json`, caso esse arquivo exista.
- Se a IA estiver disponível, o Jarvis pode interpretar a intenção do usuário e executar ações automaticamente.
- Quando o resultado é um vídeo do YouTube, os links são inseridos no chat para clique direto.
- O projeto usa janela sem barra nativa do sistema e mantém a interface em primeiro plano quando possível.

## Autor

Projeto de JARVIS em Python por FilipeGamer12.
