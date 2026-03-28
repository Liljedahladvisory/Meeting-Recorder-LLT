#!/usr/bin/env python3
"""
Meeting Recorder LLT — License Revocation Tool
================================================
Spärra en kunds licens (t.ex. vid utebliven betalning).

Spärra:
    python revoke_license.py add "kund@example.com"

Häv spärr (kund har betalat):
    python revoke_license.py remove "kund@example.com"

Visa alla spärrade:
    python revoke_license.py list

Appen kontrollerar revoked.json i GitHub-repot vid varje start.
Efter ändring pushas filen automatiskt till GitHub.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Path to revoked.json in the repo
REPO_DIR = Path(__file__).parent
REVOKED_FILE = REPO_DIR / "revoked.json"


def _load_revoked() -> list:
    if REVOKED_FILE.exists():
        data = json.loads(REVOKED_FILE.read_text())
        return data.get("revoked", [])
    return []


def _save_revoked(emails: list):
    data = {"revoked": sorted(set(emails))}
    REVOKED_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _git_push(message: str):
    """Commit and push revoked.json to GitHub."""
    try:
        os.chdir(REPO_DIR)
        subprocess.run(["git", "add", "revoked.json"], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅  Ändringen är pushad till GitHub.")
        print("    Spärren träder i kraft vid kundens nästa appstart.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git-push misslyckades: {e}")
        print("    Kör manuellt: git add revoked.json && git commit && git push")


def cmd_add(email: str):
    emails = _load_revoked()
    email_lower = email.lower().strip()
    if email_lower in [e.lower() for e in emails]:
        print(f"⚠️  {email} är redan spärrad.")
        return
    emails.append(email_lower)
    _save_revoked(emails)
    print(f"🚫  {email} har spärrats.")
    _git_push(f"Revoke license: {email}")


def cmd_remove(email: str):
    emails = _load_revoked()
    email_lower = email.lower().strip()
    original = [e for e in emails if e.lower() != email_lower]
    if len(original) == len(emails):
        print(f"⚠️  {email} finns inte i spärrlistan.")
        return
    _save_revoked(original)
    print(f"✅  Spärren för {email} har hävts.")
    _git_push(f"Unrevoke license: {email}")


def cmd_list():
    emails = _load_revoked()
    if not emails:
        print("Inga spärrade licenser.")
        return
    print(f"\nSpärrade e-postadresser ({len(emails)} st):")
    print("─" * 40)
    for e in sorted(emails):
        print(f"  🚫  {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Meeting Recorder LLT — Spärra/häv licenser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Spärra en licens")
    p_add.add_argument("email", help="E-postadressen att spärra")

    p_rm = sub.add_parser("remove", help="Häv en spärr")
    p_rm.add_argument("email", help="E-postadressen att häva spärr för")

    sub.add_parser("list", help="Visa alla spärrade")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.email)
    elif args.command == "remove":
        cmd_remove(args.email)
    elif args.command == "list":
        cmd_list()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
