# futbin_client.py
import os
import httpx
from bs4 import BeautifulSoup

LOGIN_URL = "https://www.futbin.com/login"
TEST_URL = "https://www.futbin.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

async def login_and_check():
    """
    Tenta fazer login no Futbin e devolve um resumo (para debug).
    Nota: Futbin pode alterar o fluxo/CSRF e bloquear bots; isto é só um smoke test.
    """
    user = os.environ.get("FUTBIN_USER", "")
    pwd = os.environ.get("FUTBIN_PASS", "")
    if not user or not pwd:
        return {"ok": False, "error": "FUTBIN_USER/FUTBIN_PASS em falta"}

    headers = {
        "User-Agent": UA,
        "Referer": LOGIN_URL,
        "Origin": "https://www.futbin.com",
    }

    async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=30) as client:
        # 1) Ler página de login para tentar obter CSRF (se existir)
        r_login = await client.get(LOGIN_URL)
        token = None
        if r_login.status_code == 200:
            soup = BeautifulSoup(r_login.text, "html.parser")
            el = soup.find("input", {"name": "_token"}) or soup.find("input", {"name": "csrf_token"})
            if el:
                token = el.get("value")

        # 2) Submeter credenciais
        data = {
            "username": user,
            "password": pwd,
        }
        if token:
            data["_token"] = token

        r_post = await client.post(LOGIN_URL, data=data)

        # 3) Heurística simples: se já não estamos na /login e conseguimos abrir a homepage autenticados
        # (isto é frágil, mas serve para debug)
        authed = (r_post.status_code in (200, 302, 303)) and ("/login" not in str(r_post.url))

        # Verificar acesso a uma página pública como teste adicional
        r_home = await client.get(TEST_URL)

        return {
            "ok": True,
            "login_post_status": r_post.status_code,
            "final_url": str(r_post.url),
            "authed_guess": authed,
            "test_home_status": r_home.status_code,
            "has_csrf": bool(token),
        }
