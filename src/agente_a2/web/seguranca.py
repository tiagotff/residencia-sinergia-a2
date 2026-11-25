"""Blindagem do Console A2: só a própria máquina acessa, e só pela própria página.

Camadas (todas ativas sempre, sem configuração):

1. **Somente loopback** — requisição cujo IP de origem não seja 127.0.0.1/::1 recebe 403,
   mesmo que alguém suba o servidor com ``--host 0.0.0.0``.
2. **Host fixo** — só aceita ``Host: 127.0.0.1`` ou ``localhost`` (bloqueia *DNS rebinding*,
   em que um site malicioso aponta o próprio domínio para 127.0.0.1).
3. **Token de sessão** — gerado aleatoriamente a cada inicialização e entregue só à página
   do console (``GET /api/sessao``, legível apenas pela mesma origem). Toda chamada a ``/api``
   exige o cabeçalho ``X-A2-Token``. Um site aberto em outra aba não consegue ler o token nem
   enviar o cabeçalho (sem CORS, o navegador bloqueia), então não dispara nada no A2.
4. **Origem** — se o navegador informar ``Origin``, ela precisa ser a do próprio console.
5. **Cabeçalhos de segurança** — CSP restrita a ``'self'`` (nenhum recurso externo),
   sem *framing*, sem *sniffing*, sem *referrer* e sem cache nas respostas da API.

Não existe mais API pública: sem ``/executar``, sem ``/docs``, sem ``/openapi.json``.
"""

from __future__ import annotations

import ipaddress
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

HOSTS_PERMITIDOS = {"127.0.0.1", "localhost", "[::1]"}
CABECALHO_TOKEN = "X-A2-Token"
ROTA_SESSAO = "/api/sessao"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'none'")


def novo_token() -> str:
    return secrets.token_urlsafe(32)


def _loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _host_ok(valor: str | None) -> bool:
    if not valor:
        return False
    nome = valor.rsplit(":", 1)[0] if not valor.startswith("[") else valor.split("]")[0] + "]"
    return nome.lower() in HOSTS_PERMITIDOS


def _origem_ok(origem: str | None) -> bool:
    if not origem or origem == "null":
        return origem is None
    for prefixo in ("http://", "https://"):
        if origem.startswith(prefixo):
            return _host_ok(origem[len(prefixo):].split("/")[0])
    return False


class Blindagem(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next) -> Response:
        cliente = request.client.host if request.client else None
        if not _loopback(cliente):
            return JSONResponse({"detail": "Acesso permitido apenas a partir deste computador."}, status_code=403)
        if not _host_ok(request.headers.get("host")):
            return JSONResponse({"detail": "Host não permitido."}, status_code=400)
        caminho = request.url.path
        if caminho.startswith("/api/"):
            if not _origem_ok(request.headers.get("origin")):
                return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
            if caminho != ROTA_SESSAO and not secrets.compare_digest(
                    request.headers.get(CABECALHO_TOKEN, ""), self.token):
                return JSONResponse({"detail": "Sessão inválida. Recarregue a página."}, status_code=401)

        resposta = await call_next(request)
        resposta.headers["Content-Security-Policy"] = CSP
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if caminho.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta
