import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings


MAX_MESSAGE_CHARS = 1200
MAX_HISTORY_ITEMS = 10


class AvatarConversationError(Exception):
    pass


def clean_user_text(value: Any, *, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = str(value or "").strip()
    return text[:limit]


def clean_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    clean: list[dict[str, str]] = []
    for item in value[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        content = clean_user_text(item.get("content"))
        if content:
            clean.append({"role": role, "content": content})
    return clean


def build_program_context(request, payload: dict[str, Any], competicio=None) -> str:
    user = getattr(request, "user", None)
    pieces = [
        "Usuari autenticat: " + (getattr(user, "username", "") or "usuari"),
        "Pagina: " + clean_user_text(payload.get("page_title"), limit=180),
        "Ruta UI: " + clean_user_text(payload.get("path"), limit=220),
        "Tema avatar: " + clean_user_text(payload.get("topic"), limit=120),
    ]
    if competicio is not None:
        pieces.append(f"Competicio actual: #{competicio.id} {competicio.nom}")
        pieces.append(f"Tipus competicio: {competicio.tipus}")
    return "\n".join(piece for piece in pieces if piece.strip())


def build_instructions(context: str) -> str:
    return (
        "Ets l'assistent conversacional d'IA Score dins el programa de competicions de trampoli.\n"
        "Respon sempre en catala, amb un to clar, proper i practic.\n"
        "La teva feina es ajudar l'usuari a entendre i utilitzar el programa: competicions, "
        "inscripcions, equips, grups, series, multimedia, aparells, fases, rotacions, puntuacio, "
        "classificacions, notes, QRs i suport a jutges.\n"
        "No pots modificar dades, no pots canviar codi, no pots executar accions i no pots prometre "
        "que ho has fet. Si l'usuari demana una accio, explica els passos o indica quin boto o pantalla "
        "ha de fer servir.\n"
        "No inventis dades concretes que no apareguin al context. Si no ho saps, digues-ho i demana "
        "una mica mes de context.\n"
        "Mantingues les respostes curtes: normalment 2-5 frases, o una llista breu si ajuda.\n\n"
        "Context actual de la UI:\n"
        f"{context}"
    )


def response_output_text(response: dict[str, Any]) -> str:
    direct = str(response.get("output_text") or "").strip()
    if direct:
        return direct

    fragments: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
    return "\n".join(fragments).strip()


def call_openai_responses(*, message: str, history: list[dict[str, str]], context: str) -> str:
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise AvatarConversationError(
            "L'assistent conversacional encara no te configurada la clau OPENAI_API_KEY."
        )

    input_items = [*history, {"role": "user", "content": message}]
    payload = {
        "model": getattr(settings, "OPENAI_AVATAR_MODEL", "gpt-5.5"),
        "instructions": build_instructions(context),
        "input": input_items,
        "store": False,
        "max_output_tokens": 500,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=getattr(settings, "OPENAI_AVATAR_TIMEOUT_SECONDS", 30),
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AvatarConversationError("OpenAI ha retornat un error: " + detail[:300]) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AvatarConversationError("No s'ha pogut contactar amb l'assistent d'IA.") from exc

    text = response_output_text(data)
    if not text:
        raise AvatarConversationError("L'assistent no ha retornat cap resposta.")
    return text
