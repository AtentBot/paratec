#!/usr/bin/env python
"""Promove (ou revoga) um usuário como STAFF — acesso à central admin da Dew.

O usuário precisa existir (crie antes com signup ou seed_owner.py). Ex.:
    .venv/bin/python make_staff.py --email suporte@dewconsultoria.com.br
    .venv/bin/python make_staff.py --email x@y.com --revogar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Define/retira o papel de staff (admin da plataforma).")
    ap.add_argument("--email", required=True, help="e-mail do usuário")
    ap.add_argument("--revogar", action="store_true", help="retira o papel de staff")
    args = ap.parse_args()

    store.ensure_schema()
    if not store.set_user_staff(args.email, not args.revogar):
        print(f"usuário não encontrado: {args.email}", file=sys.stderr)
        return 3
    print(f"{'revogado' if args.revogar else 'promovido a staff'}: {args.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
