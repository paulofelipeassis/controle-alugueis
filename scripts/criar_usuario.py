"""Cria um usuário do sistema novo, ou troca a senha de quem esqueceu. Cada pessoa digita a própria senha.

Uso (no servidor): docker compose exec web python -m scripts.criar_usuario
"""
from getpass import getpass

from sistema import consultas, servicos
from sistema.regras import ErroDeNegocio


def main():
    login = input("Login (ex.: paulo): ").strip().lower()
    existente = any(u["login"] == login for u in consultas.listar_usuarios())
    if existente:
        if input(f"Já existe o usuário '{login}'. Trocar a senha dele? (s/n): ").strip().lower() != "s":
            return
    nome = "" if existente else input("Nome: ").strip()
    senha = getpass("Senha nova (mínimo 8 caracteres): ")
    if senha != getpass("Repita a senha: "):
        print("As senhas não conferem.")
        return
    try:
        if existente:
            servicos.alterar_senha("sistema", login, senha)
            print(f"Senha de '{login}' trocada.")
        else:
            servicos.criar_usuario(login, nome, senha)
            print(f"Usuário '{login}' criado.")
    except ErroDeNegocio as erro:
        print(f"Erro: {erro}")


if __name__ == "__main__":
    main()
