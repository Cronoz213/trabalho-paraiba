from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
import json

from .agents import PersistenceAgent
from .rag import DatabaseRagService
from .services import InvoiceExtractionService


def index(request):
    return render(request, "invoices/index.html")


@require_POST
def extract_invoice(request):
    uploaded_file = request.FILES.get("pdf")
    if not uploaded_file:
        return JsonResponse({"error": "Arquivo PDF é obrigatório.", "detail": "Envie o campo 'pdf' no multipart/form-data."}, status=400)

    is_pdf_by_name = uploaded_file.name.lower().endswith(".pdf")
    allowed_content_types = {"application/pdf", "application/x-pdf", "application/octet-stream"}
    is_pdf_by_type = not uploaded_file.content_type or uploaded_file.content_type in allowed_content_types

    if not is_pdf_by_name or not is_pdf_by_type:
        return JsonResponse({"error": "Formato do arquivo inválido.", "detail": "Envie somente arquivos PDF (.pdf)."}, status=400)

    if uploaded_file.size > settings.MAX_UPLOAD_SIZE:
        return JsonResponse(
            {"error": "Arquivo muito grande.", "detail": "O tamanho máximo permitido é 10 MB."},
            status=400,
        )

    service = InvoiceExtractionService()
    try:
        return JsonResponse(service.extract(uploaded_file))
    except Exception as exc:
        PersistenceAgent().save_error(uploaded_file, str(exc))
        if isinstance(exc, ValueError):
            return JsonResponse({"error": "Falha ao extrair dados do PDF.", "detail": str(exc)}, status=400)
        return JsonResponse({"error": "Erro interno ao processar o PDF.", "detail": str(exc)}, status=500)


@require_POST
def query_database_rag(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Corpo JSON invalido.", "detail": "Envie a pergunta em formato JSON."}, status=400)

    question = payload.get("question", "")
    mode = payload.get("mode", "simple")

    try:
        data = DatabaseRagService().ask(question, mode)
    except ValueError as exc:
        return JsonResponse({"error": "Falha na consulta RAG.", "detail": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": "Erro interno ao consultar o banco.", "detail": str(exc)}, status=500)

    return JsonResponse(data)
