import os
import json
import win32com.client

OUTPUT_JSON = "apps_mapeados_windows.json"

START_MENU_PATHS = [
    os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu"),
    os.path.join(os.environ["PROGRAMDATA"], r"Microsoft\Windows\Start Menu"),
]

DESKTOP_PATHS = [
    os.path.join(os.environ["USERPROFILE"], "Desktop"),
]

VALID_EXTENSIONS = (".lnk", ".url", ".exe", ".bat", ".cmd", ".ps1")

shell = win32com.client.Dispatch("WScript.Shell")
apps = []


def resolve_lnk(path):
    try:
        # ✅ MÉTODO CORRETO
        sc = shell.CreateShortcut(path)

        target = (sc.Targetpath or "").strip()
        args = (sc.Arguments or "").strip().strip('"')

        full = f"{target} {args}".lower()

        # ---------- STEAM ----------
        if "steam://rungameid/" in full or "-applaunch" in full:
            game_id = None

            if "steam://rungameid/" in full:
                game_id = full.split("steam://rungameid/")[1].split()[0]

            elif "-applaunch" in full:
                game_id = full.split("-applaunch")[1].strip().split()[0]

            if game_id:
                return {
                    "tipo": "jogo",
                    "plataforma": "Steam",
                    "uri": f"steam://rungameid/{game_id}"
                }

        # ---------- EPIC ----------
        if "com.epicgames.launcher://" in full:
            start = full.index("com.epicgames.launcher://")
            uri = full[start:].split()[0]

            return {
                "tipo": "jogo",
                "plataforma": "Epic Games",
                "uri": uri
            }

        # ---------- SCRIPT POR ATALHO ----------
        if target.lower().endswith((".bat", ".cmd", ".ps1")):
            return {
                "tipo": "script",
                "executavel": target
            }

        # ---------- EXECUTÁVEL ----------
        if target:
            return {
                "tipo": "app",
                "executavel": target
            }

        return None

    except Exception as e:
        return None

def resolve_url(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().lower().startswith("url="):
                    url = line.strip()[4:]

                    if url.startswith("steam://"):
                        return {
                            "tipo": "jogo",
                            "plataforma": "Steam",
                            "uri": url
                        }

                    if url.startswith("com.epicgames.launcher://"):
                        return {
                            "tipo": "jogo",
                            "plataforma": "Epic Games",
                            "uri": url
                        }

                    return {
                        "tipo": "url",
                        "uri": url
                    }
    except Exception:
        return None

def scan_directory(base_path, source):
    for root, _, files in os.walk(base_path):
        for file in files:
            if not file.lower().endswith(VALID_EXTENSIONS):
                continue

            full_path = os.path.join(root, file)

            entry = {
                "nome": os.path.splitext(file)[0],
                "origem": source,
                "arquivo": full_path,
                "tipo": "app",
                "executavel": None
            }

            ext = file.lower()

            # ---------- .URL (Steam / Epic) ----------
            if ext.endswith(".url"):
                resolved = resolve_url(full_path)
                if not resolved:
                    continue

                entry["tipo"] = resolved["tipo"]

                if "plataforma" in resolved:
                    entry["plataforma"] = resolved["plataforma"]

                entry["uri"] = resolved["uri"]

            # ---------- .LNK ----------
            elif ext.endswith(".lnk"):
                resolved = resolve_lnk(full_path)
                if not resolved:
                    continue

                entry["tipo"] = resolved["tipo"]

                if "plataforma" in resolved:
                    entry["plataforma"] = resolved["plataforma"]

                if "uri" in resolved:
                    entry["uri"] = resolved["uri"]
                else:
                    entry["executavel"] = resolved.get("executavel")

            # ---------- ARQUIVOS DIRETOS ----------
            else:
                entry["executavel"] = full_path

                if ext.endswith((".bat", ".cmd", ".ps1")):
                    entry["tipo"] = "script"

            apps.append(entry)

def main():
    for path in START_MENU_PATHS:
        if os.path.exists(path):
            scan_directory(path, "StartMenu")

    for path in DESKTOP_PATHS:
        if os.path.exists(path):
            scan_directory(path, "Desktop")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=4, ensure_ascii=False)

    print(f"✅ {len(apps)} itens mapeados")
    print(f"📄 {OUTPUT_JSON}")


if __name__ == "__main__":
    main()