# accounts/ai/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.ai.local_nlp import parse_intent_and_entities
from accounts.ai.engine import run_ai_query


@csrf_exempt
@require_POST
def ask_ai(request):
    q = (request.POST.get("question") or "").strip()
    if not q:
        return JsonResponse({"type": "error", "error": "Empty question."}, status=400)

    parsed = parse_intent_and_entities(q)  # {"intent": "...", "entities": {...}}
    intent = parsed.get("intent", "unknown")
    entities = parsed.get("entities", {})

    answer = run_ai_query(intent, entities)
    return JsonResponse(answer)