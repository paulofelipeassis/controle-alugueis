import bcrypt
import streamlit as st

st.set_page_config(page_title="Gerador de Hashes", page_icon="🔑")

st.title("🔑 Gerador de Hashes de Senha")
st.warning(
    "Use esta página apenas uma vez para gerar as senhas criptografadas para o seu arquivo `config.yaml`. Depois, você pode apagar este arquivo.")

passwords_to_hash = st.text_area("Digite as senhas que deseja criptografar (uma por linha)")

if st.button("Gerar Hashes"):
    if passwords_to_hash:
        passwords = passwords_to_hash.strip().split('\n')
        hashed_passwords = []

        st.info("Copie os hashes gerados abaixo e cole no seu arquivo `config.yaml`:")

        for password in passwords:
            # Codifica a senha para bytes
            password_bytes = password.encode('utf-8')
            # Gera o hash
            hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
            # Decodifica de volta para string para exibição/armazenamento
            hashed_password_str = hashed_password.decode('utf-8')

            hashed_passwords.append(hashed_password_str)

            st.code(f"'{hashed_password_str}'")

    else:
        st.error("Por favor, digite pelo menos uma senha.")