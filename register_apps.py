#!/usr/bin/env python3
"""
Simple assistant to register applications in apps.json
Usage:
  python register_apps.py add "name" "exec"
  python register_apps.py list
  python register_apps.py remove "name"
"""
from pathlib import Path
import json
import argparse
import sys

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
    parser = argparse.ArgumentParser(description="Register apps in apps.json")
    sub = parser.add_subparsers(dest="command")
    p_add = sub.add_parser("add", help="Add a new app")
    p_add.add_argument("name", help="Application name")
    p_add.add_argument("exec", help="Executable path or URL")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List registered apps")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="Remove an app by name")
    p_remove.add_argument("name", help="Application name to remove")
    p_remove.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    if not args.command:
        name = input("Nome do app: ").strip()
        if not name:
            parser.print_help()
            return sys.exit(1)
        exec_path = input("Exec (path ou URL): ").strip()
        if not exec_path:
            print("Exec vazio.")
            return sys.exit(1)
        ns = argparse.Namespace(name=name, exec=exec_path)
        return sys.exit(cmd_add(ns))

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()