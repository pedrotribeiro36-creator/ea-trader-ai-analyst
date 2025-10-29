# futbin_client.py
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
import cloudscraper


class FutbinClient:
    """
    Cliente simples para autenticar no Futbin e fazer pedidos autenticados.
    - Tenta login com user/password (guardados em env vars).
    - Se existir FUTBIN_PHPSESSID nas envs, usa diretamente esse cookie.
    """

    BASE = "https://www.futbin.com"

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, phpsessid: Optional[str] = None):
        self.username = username
        self.password = password
        self.phpsessid = phpsessid
        self.scraper = cloudscraper.create_scraper(browser={"custom": "firefox"})
        self.logged = False

        # Se já vier um cookie válido, configura-o
        if self.phpsessid:
            self.scraper.cookies.set("PHPSESSID", self.phpsessid, domain="www.futbin.com")
            self.logged = True

    def _get_hidden_inputs(self, html: str) -> Dict[str, str]:
        soup = BeautifulSoup(html, "lxml")
        inputs = {}
        for inp in soup.select("form input[type=hidden]"):
            name = inp.get("name")
            val = inp.get("value", "")
            if name:
                inputs[name] = val
        return inputs

    def login(self) -> Dict:
        """
        Faz login no Futbin e guarda o cookie na sessão.
        Retorna dict com status e info útil para debugging.
        """
        if self.logged and self.scraper.cookies.get("PHPSESSID", domain="www.futbin.com"):
            return {"ok": True, "already_logged": True}

        if not self.username or not self.password:
            return {"ok": False, "error": "MISSING_CREDENTIALS"}

        # 1) Vai à página de login para apanhar tokens
        login_url = f"{self.BASE}/login"
        r = self.scraper.get(login_url, timeout=30)
        if r.status_code != 200:
            return {"ok": False, "step": "GET_LOGIN", "status": r.status_code}

        hidden = self._get_hidden_inputs(r.text)

        # 2) Monta payload do formulário
        # Campos mais comuns: username / email / password / csrf
        payload = {
            "username": self.username,
            "password": self.password,
            # muitos sites usam "remember" (se existir não faz mal enviar)
            "remember": "on",
        }
        payload.update(hidden)

        # 3) Faz POST do login
        post = self.scraper.post(login_url, data=payload, timeout=30, allow_redirects=True)

        # 4) Confirma cookie e estado autenticado
        phpsessid = self.scraper.cookies.get("PHPSESSID", domain="www.futbin.com")
        home = self.scraper.get(self.BASE, timeout=30)

        ok_home = home.status_code == 200
        self.logged = bool(phpsessid and ok_home)

        return {
            "ok": self.logged,
            "login_post_status": post.status_code,
            "test_home_status": home.status_code if ok_home else home.status_code,
            "has_csrf": bool(hidden),
            "cookie_set": bool(phpsessid),
            "final_url": str(post.url),
            "authed_guess": self.logged,
        }

    def get(self, path: str, params: Optional[Dict] = None):
        """
        GET autenticado (ou guest, se sem login). Path pode ser '/something' ou URL completo.
        """
        if path.startswith("http"):
            url = path
        else:
            url = self.BASE + path
        r = self.scraper.get(url, params=params or {}, timeout=30)
        return r

    # Exemplo de método para ir buscar alguma página de preços (ajusta ao que precisas)
    def get_player_page(self, player_id: str):
        """
        Vai buscar a página de um jogador.
        """
        return self.get(f"/{player_id}")
