"""Cria um usuário do sistema novo. Cada pessoa digita a própria senha.

Uso: python -m scripts.criar_usuario
"""
from getpass import getpass

from sistema import servicos
from sistema.regras import ErroDeNegocio


def main():
    login = input("Login (ex.: paulo): ").strip()
    nome = input("Nome: ").strip()
    senha = getpass("Senha (mínimo 8 caracteres): ")
    if senha != getpass("Repita a senha: "):
        print("As senhas não conferem.")
        return
    try:
        servicos.criar_usuario(login, nome, senha)
        print(f"Usuário '{login}' criado.")
    except ErroDeNegocio as erro:
        print(f"Erro: {erro}")


if __name__ == "__main__":
    main()
