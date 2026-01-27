from pathlib import Path
import json
import sys
import types
import subprocess

APPS_PATH = Path("./apps.json")


def load_apps(path: Path = APPS_PATH):
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("Error: apps.json contains invalid JSON.", file=sys.stderr)
        sys.exit(1)


def save_apps(apps, path: Path = APPS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2, ensure_ascii=False)


def find_app(apps, name: str):
    key = name.strip().lower()
    for app in apps:
        if app.get("name", "").strip().lower() == key:
            return app
    return None


def cmd_add(args):
    apps = load_apps()
    if find_app(apps, args.name):
        print(f"App '{args.name}' already registered.")
        return 1
    apps.append({"name": args.name, "exec": args.exec})
    save_apps(apps)
    print(f"Added '{args.name}'.")
    return 0


def cmd_list(_args):
    apps = load_apps()
    if not apps:
        print("No apps registered.")
        return 0
    for a in apps:
        print(f"{a.get('name')} -> {a.get('exec')}")
    return 0


def cmd_remove(args):
    apps = load_apps()
    app = find_app(apps, args.name)
    if not app:
        print(f"App '{args.name}' not found.")
        return 1
    apps = [a for a in apps if a.get("name", "").strip().lower() != args.name.strip().lower()]
    save_apps(apps)
    print(f"Removed '{args.name}'.")
    return 0


def main():
    try:
        while True:
            name = input("Nome do app (ou 'exit' para sair): ").strip()
            if not name:
                print("Nome vazio.")
                continue
            if name.lower() in ("exit", "quit", "sair"):
                print("Encerrando.")
                return
            exec_path = input("Exec (path ou URL): ").strip()
            # remove aspas simples ou duplas no começo/fim
            exec_path = exec_path.strip('"\'')
            if not exec_path:
                print("Exec vazio.")
                continue
            ns = types.SimpleNamespace()
            setattr(ns, "name", name)
            setattr(ns, "exec", exec_path)
            cmd_add(ns)
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()