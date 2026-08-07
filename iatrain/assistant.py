from core.assistant import AssistantContext


AVATAR_MESSAGES = {
    "iatrain_welcome": {
        "id": "iatrain_welcome",
        "title": "Assistent IA Train",
        "avatar": "avatar/explaining/explaining_2.png",
        "variant": "intro",
        "steps": [
            {
                "text": (
                    "Soc l’assistent d’IA Train. T’acompanyaré per organitzar grups, "
                    "gimnastes, gimnasos i el context de cada entrenament."
                )
            },
            {
                "text": (
                    "El commutador superior separa completament l’espai d’entrenador "
                    "de l’espai de gimnasta."
                )
            },
        ],
        "actions": [],
    },
    "training_context": {
        "id": "training_context",
        "title": "Assistent IA Train",
        "avatar": "avatar/checking.png",
        "variant": "context",
        "steps": [
            {
                "text": (
                    "Abans d’entrar al motor, comprovo que l’organització, el grup, "
                    "els gimnastes i el gimnàs siguin compatibles."
                )
            }
        ],
        "actions": [],
    },
}


def iatrain_assistant_provider(request):
    path = str(getattr(request, "path", "") or "")
    if not path.startswith("/iatrain/"):
        return None
    initial_topic = "training_context" if path.startswith("/iatrain/engine/") else "iatrain_welcome"
    return AssistantContext(
        module="iatrain",
        messages=AVATAR_MESSAGES,
        initial_topic=initial_topic,
    )
