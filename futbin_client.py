# futbin_client.py
# Cliente mínimo para login no Futbin e verificação de sessão.

from typing import Dict, Any
import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def login_and_check(username: str, password: str, timeout: int = 25) -> Dict[str, Any]:
    """
    Tenta iniciar sessão no Futbin e retorna um relatório simples.
    - NÃO guarda qualquer credencial; usa apenas a sessão in-memory.
    - Retorna sempre dados de diagnóstico para perceber o que aconteceu.
    """
    base = "https://www.futbin.com"
    login_url = f"{base}/login"
    home_url = f"{base}/"

    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)

    out: Dict[str, Any] = {
        "ok": False,
        "step": "init",
        "login_get_status": None,
        "login_post_status": None,
        "home_status": None,
        "final_url": None,
        "authed_guess": False,
        "has_csrf": False,
        "errors": [],
    }

    try:
        # 1) GET login para obter cookies iniciais
        r1 = s.get(login_url, timeout=timeout)
        out["login_get_status"] = r1.status_code

        # 2) Algumas páginas usam CSRF; se existir, tentamos enviar de volta.
        csrf_token = None
        for name, value in s.cookies.items():
            if "csrf" in name.lower():
                csrf_token = value
                break
        out["has_csrf"] = csrf_token is not None

        # 3) POST credenciais (nomes de campos comuns; Futbin pode mudar)
        payload = {
            "username": username,
            "password": password,
        }
        # Se descobrires os nomes exatos dos campos, adapta aqui:
        # p.ex.: payload = {"email": username, "password": password, "_token": csrf_token}

        r2 = s.post(login_url, data=payload, timeout=timeout, allow_redirects=True)
        out["login_post_status"] = r2.status_code

        # 4) Visita a home para ver se aparenta estar autenticado
        r3 = s.get(home_url, timeout=timeout, allow_redirects=True)
        out["home_status"] = r3.status_code
        out["final_url"] = r3.url

        # Heurística simples: algumas páginas mostram “logout” quando logado.
        text_low = (r3.text or "").lower()
        out["authed_guess"] = ("logout" in text_low) or ("sign out" in text_low)

        out["ok"] = True
        out["step"] = "done"
        return out

    except requests.RequestException as e:
        out["errors"].append(str(e))
        out["step"] = "network_error"
        return out
