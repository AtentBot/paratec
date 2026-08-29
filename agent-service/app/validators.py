"""Validações de dados de cadastro (CNPJ, e-mail)."""
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def cnpj_valido(cnpj: str) -> bool:
    """Valida CNPJ pelos dígitos verificadores (14 dígitos)."""
    n = so_digitos(cnpj)
    if len(n) != 14 or n == n[0] * 14:
        return False

    def dv(base: str, pesos: list[int]) -> str:
        s = sum(int(d) * p for d, p in zip(base, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)

    d1 = dv(n[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(n[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return n[12:] == d1 + d2


def cnpj_formatado(cnpj: str) -> str:
    """00.000.000/0000-00 (assume já validado)."""
    n = so_digitos(cnpj)
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def email_valido(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))
