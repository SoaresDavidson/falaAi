"""Fonte de Newsletters via Gmail API e comando de autorização."""

import base64
import email
import email.policy
import logging
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify

from falaai.domain import Newsletter

log = logging.getLogger(__name__)

ESCOPO = "https://www.googleapis.com/auth/gmail.modify"


def _html_para_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["img", "script", "style"]):
        tag.decompose()
    for a in soup.find_all("a"):
        if not a.get_text(strip=True):
            a.decompose()
    md = markdownify(str(soup), heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _gravar_token(path: Path, conteudo: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(conteudo)


def _data(msg) -> datetime:
    try:
        dt = parsedate_to_datetime(str(msg["Date"]))
    except (TypeError, ValueError, IndexError):
        log.warning("Date ausente ou inválido; usando a hora atual")
        return datetime.now(UTC)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _conteudo(parte) -> str:
    try:
        return parte.get_content()
    except LookupError:
        payload = parte.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def newsletter_de_mime(gmail_id: str, raw: bytes, max_chars: int) -> Newsletter:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        texto = _html_para_markdown(_conteudo(html))
    else:
        plain = msg.get_body(preferencelist=("plain",))
        texto = _conteudo(plain).strip() if plain is not None else ""
    return Newsletter(
        gmail_id=gmail_id,
        remetente=str(msg.get("From", "")),
        assunto=str(msg.get("Subject", "")),
        recebida_em=_data(msg),
        texto=texto[:max_chars],
    )


class GmailFonte:
    def __init__(self, token_path: Path, rotulo: str, max_chars: int, servico=None):
        self.token_path = token_path
        self.rotulo = rotulo
        self.max_chars = max_chars
        self._servico = servico

    def _credenciais(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(self.token_path), [ESCOPO])
        if not creds.valid:
            if not creds.refresh_token:
                raise RuntimeError(
                    "Token do Gmail inválido e sem refresh token: rode `falaai auth`."
                )
            creds.refresh(Request())
            _gravar_token(self.token_path, creds.to_json())
        return creds

    def _svc(self):
        if self._servico is None:
            from googleapiclient.discovery import build

            creds = self._credenciais()
            self._servico = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._servico

    def pendentes(self) -> list[Newsletter]:
        msgs = self._svc().users().messages()
        ids: list[str] = []
        token = None
        while True:
            kw = {"userId": "me", "q": f"label:{self.rotulo} in:inbox"}
            if token:
                kw["pageToken"] = token
            resp = msgs.list(**kw).execute()
            ids += [m["id"] for m in resp.get("messages", [])]
            token = resp.get("nextPageToken")
            if not token:
                break
        out = []
        for i in ids:
            try:
                r = msgs.get(userId="me", id=i, format="raw").execute()
                raw = base64.urlsafe_b64decode(r["raw"] + "=" * (-len(r["raw"]) % 4))
                out.append(newsletter_de_mime(i, raw, self.max_chars))
            except Exception:
                log.exception(
                    "Falha ao processar a mensagem %s; ela continua na caixa de entrada", i
                )
        if ids and not out:
            raise RuntimeError(f"todas as {len(ids)} mensagens falharam ao ser lidas")
        return sorted(out, key=lambda n: n.recebida_em)

    def arquivar(self, gmail_ids: Sequence[str]) -> None:
        if not gmail_ids:
            return
        body = {"ids": list(gmail_ids), "removeLabelIds": ["INBOX"]}
        self._svc().users().messages().batchModify(userId="me", body=body).execute()


def autorizar(client_secret: Path, saida: Path) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), [ESCOPO])
    creds = flow.run_local_server(port=0)
    _gravar_token(saida, creds.to_json())
