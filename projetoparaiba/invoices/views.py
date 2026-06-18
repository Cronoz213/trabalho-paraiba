from __future__ import annotations

import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_http_methods

from .agents import PersistenceAgent
from .models import Classificacao, MovimentoContas, Pessoa
from .rag import DatabaseRagService
from .services import InvoiceExtractionService


# ── Existing views ────────────────────────────────────────────────────────────

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


# ── Page views ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
def pessoas_page(request, tipo):
    labels = {
        "fornecedor": ("FORNECEDOR", "Fornecedores"),
        "cliente": ("CLIENTE", "Clientes"),
        "faturado": ("FATURADO", "Faturados"),
    }
    tipo_model, tipo_label = labels.get(tipo.lower(), ("FORNECEDOR", "Fornecedores"))
    return render(request, "invoices/pessoas.html", {
        "tipo": tipo_model,
        "tipo_label": tipo_label,
        "active_page": "pessoas",
    })


@ensure_csrf_cookie
def classificacao_page(request, tipo):
    labels = {
        "receita": ("RECEITA", "Receitas"),
        "despesa": ("DESPESA", "Despesas"),
    }
    tipo_model, tipo_label = labels.get(tipo.lower(), ("DESPESA", "Despesas"))
    return render(request, "invoices/classificacao.html", {
        "tipo": tipo_model,
        "tipo_label": tipo_label,
        "active_page": "classificacao",
    })


@ensure_csrf_cookie
def contas_page(request):
    return render(request, "invoices/contas.html", {"active_page": "contas"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        return JsonResponse({"error": exc.message_dict}, status=400)
    return JsonResponse({"error": {"__all__": exc.messages}}, status=400)


# ── Pessoas API ───────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_pessoas(request):
    if request.method == "GET":
        tipo = request.GET.get("tipo", "")
        q = request.GET.get("q", "").strip()
        qs = Pessoa.objects.all()
        if tipo == Pessoa.Tipo.FORNECEDOR:
            qs = qs.filter(tipo__in=[Pessoa.Tipo.FORNECEDOR, Pessoa.Tipo.CLIENTE_FORNECEDOR])
        elif tipo == Pessoa.Tipo.FATURADO:
            qs = qs.filter(tipo__in=[Pessoa.Tipo.FATURADO, Pessoa.Tipo.CLIENTE, Pessoa.Tipo.CLIENTE_FORNECEDOR])
        elif tipo:
            qs = qs.filter(tipo=tipo)
        if q:
            qs = qs.filter(
                Q(razao_social__icontains=q) | Q(documento__icontains=q) | Q(cidade__icontains=q)
            )
        data = list(qs.values("id", "tipo", "razao_social", "documento", "inscricao_estadual", "endereco", "cidade", "uf", "ativo"))
        return JsonResponse({"data": data})

    try:
        payload = json.loads(request.body or "{}")
        for f in ("id", "created_at", "updated_at", "ativo"):
            payload.pop(f, None)
        p = Pessoa(**payload)
        p.save()
        return JsonResponse({"id": p.id, "message": "Criado com sucesso."}, status=201)
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_pessoa(request, pk):
    try:
        pessoa = Pessoa.all_objects.get(pk=pk)
    except Pessoa.DoesNotExist:
        return JsonResponse({"error": "Não encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": pessoa.id, "tipo": pessoa.tipo, "razao_social": pessoa.razao_social,
            "documento": pessoa.documento, "inscricao_estadual": pessoa.inscricao_estadual,
            "endereco": pessoa.endereco, "cidade": pessoa.cidade, "uf": pessoa.uf,
            "ativo": pessoa.ativo,
        })

    if request.method == "PUT":
        try:
            payload = json.loads(request.body or "{}")
            for f in ("id", "created_at", "updated_at", "ativo"):
                payload.pop(f, None)
            for k, v in payload.items():
                setattr(pessoa, k, v)
            pessoa.save()
            return JsonResponse({"message": "Atualizado com sucesso."})
        except ValidationError as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    pessoa.delete()
    return JsonResponse({"message": "Excluído com sucesso."})


# ── Classificacao API ─────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_classificacoes(request):
    if request.method == "GET":
        tipo = request.GET.get("tipo", "")
        q = request.GET.get("q", "").strip()
        qs = Classificacao.objects.all()
        if tipo:
            qs = qs.filter(tipo=tipo)
        if q:
            qs = qs.filter(descricao__icontains=q)
        data = list(qs.values("id", "tipo", "descricao", "ativo"))
        return JsonResponse({"data": data})

    try:
        payload = json.loads(request.body or "{}")
        for f in ("id", "created_at", "updated_at", "ativo"):
            payload.pop(f, None)
        c = Classificacao(**payload)
        c.save()
        return JsonResponse({"id": c.id, "message": "Criado com sucesso."}, status=201)
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_classificacao_item(request, pk):
    try:
        c = Classificacao.all_objects.get(pk=pk)
    except Classificacao.DoesNotExist:
        return JsonResponse({"error": "Não encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse({"id": c.id, "tipo": c.tipo, "descricao": c.descricao, "ativo": c.ativo})

    if request.method == "PUT":
        try:
            payload = json.loads(request.body or "{}")
            for f in ("id", "created_at", "updated_at", "ativo"):
                payload.pop(f, None)
            for k, v in payload.items():
                setattr(c, k, v)
            c.save()
            return JsonResponse({"message": "Atualizado com sucesso."})
        except ValidationError as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    c.delete()
    return JsonResponse({"message": "Excluído com sucesso."})


# ── MovimentoContas API ───────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_contas(request):
    if request.method == "GET":
        q = request.GET.get("q", "").strip()
        qs = MovimentoContas.objects.select_related("fornecedor", "faturado", "classificacao")
        if q:
            qs = qs.filter(
                Q(numero_nota_fiscal__icontains=q)
                | Q(fornecedor__razao_social__icontains=q)
                | Q(faturado__razao_social__icontains=q)
                | Q(observacao__icontains=q)
            )
        data = [
            {
                "id": m.id, "tipo": m.tipo,
                "fornecedor_id": m.fornecedor_id, "fornecedor": m.fornecedor.razao_social,
                "faturado_id": m.faturado_id, "faturado": m.faturado.razao_social,
                "classificacao_id": m.classificacao_id, "classificacao": m.classificacao.descricao,
                "numero_nota_fiscal": m.numero_nota_fiscal, "serie": m.serie,
                "data_emissao": m.data_emissao, "valor_total": str(m.valor_total),
                "observacao": m.observacao, "ativo": m.ativo,
            }
            for m in qs
        ]
        return JsonResponse({"data": data})

    try:
        payload = json.loads(request.body or "{}")
        for f in ("id", "created_at", "updated_at", "fornecedor", "faturado", "classificacao"):
            payload.pop(f, None)
        payload.setdefault("ativo", True)
        m = MovimentoContas(**payload)
        m.save()
        return JsonResponse({"id": m.id, "message": "Criado com sucesso."}, status=201)
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_conta(request, pk):
    try:
        m = MovimentoContas.all_objects.select_related("fornecedor", "faturado", "classificacao").get(pk=pk)
    except MovimentoContas.DoesNotExist:
        return JsonResponse({"error": "Não encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": m.id, "tipo": m.tipo,
            "fornecedor_id": m.fornecedor_id, "faturado_id": m.faturado_id,
            "classificacao_id": m.classificacao_id,
            "numero_nota_fiscal": m.numero_nota_fiscal, "serie": m.serie,
            "data_emissao": m.data_emissao, "valor_total": str(m.valor_total),
            "observacao": m.observacao, "ativo": m.ativo,
        })

    if request.method == "PUT":
        try:
            payload = json.loads(request.body or "{}")
            for f in ("id", "created_at", "updated_at", "ativo", "fornecedor", "faturado", "classificacao"):
                payload.pop(f, None)
            for k, v in payload.items():
                setattr(m, k, v)
            m.save()
            return JsonResponse({"message": "Atualizado com sucesso."})
        except ValidationError as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    m.delete()
    return JsonResponse({"message": "Excluído com sucesso."})


# ── Options API (selects para formulários) ────────────────────────────────────

def api_options(request):
    fornecedores = list(
        Pessoa.objects.filter(tipo__in=[Pessoa.Tipo.FORNECEDOR, Pessoa.Tipo.CLIENTE_FORNECEDOR])
        .values("id", "razao_social")
    )
    faturados = list(
        Pessoa.objects.filter(tipo__in=[Pessoa.Tipo.FATURADO, Pessoa.Tipo.CLIENTE_FORNECEDOR, Pessoa.Tipo.CLIENTE])
        .values("id", "razao_social")
    )
    classificacoes = list(Classificacao.objects.all().values("id", "descricao", "tipo"))
    return JsonResponse({
        "fornecedores": fornecedores,
        "faturados": faturados,
        "classificacoes": classificacoes,
    })
