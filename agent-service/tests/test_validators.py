"""Validação de CNPJ e e-mail (puro, sempre roda)."""
from app.validators import cnpj_formatado, cnpj_valido, email_valido


def test_cnpj_valido():
    # CNPJs com dígitos verificadores corretos.
    assert cnpj_valido("11.222.333/0001-81")
    assert cnpj_valido("11222333000181")


def test_cnpj_invalido():
    assert not cnpj_valido("11.222.333/0001-80")  # DV errado
    assert not cnpj_valido("00000000000000")      # todos iguais
    assert not cnpj_valido("123")                 # tamanho errado
    assert not cnpj_valido("")


def test_cnpj_formatado():
    assert cnpj_formatado("11222333000181") == "11.222.333/0001-81"


def test_email():
    assert email_valido("contato@empresa.com.br")
    assert not email_valido("contato@empresa")
    assert not email_valido("sem-arroba.com")
    assert not email_valido("")
