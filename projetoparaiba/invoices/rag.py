from __future__ import annotations

from collections import Counter
import math
import re
from typing import Iterable

from django.conf import settings

from .models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


class DatabaseRagService:
    SIMPLE_MODE = "simple"
    EMBEDDINGS_MODE = "embeddings"
    VALID_MODES = {SIMPLE_MODE, EMBEDDINGS_MODE}
    EMBEDDING_SIZE = 96

    def ask(self, question: str, mode: str) -> dict:
        normalized_question = self._clean_text(question)
        if not normalized_question:
            raise ValueError("Digite uma pergunta para consultar o banco de dados.")

        normalized_mode = self._normalize_mode(mode)
        chunks = self._build_chunks()
        ranked_chunks = self._rank_chunks(normalized_question, normalized_mode, chunks)
        selected_chunks = ranked_chunks[:6]
        provider, answer = self._generate_answer(normalized_question, normalized_mode, selected_chunks)

        return {
            "success": True,
            "question": question.strip(),
            "mode": normalized_mode,
            "provider": provider,
            "answer": answer,
            "context": [self._serialize_chunk(chunk) for chunk in selected_chunks],
            "stats": self._build_stats(chunks),
        }

    def _normalize_mode(self, mode: str) -> str:
        normalized = self._clean_text(mode)
        if normalized in {"rag simples", "simples", "simple"}:
            return self.SIMPLE_MODE
        if normalized in {"rag embeddings", "embeddings", "embedding"}:
            return self.EMBEDDINGS_MODE
        raise ValueError("Modo de consulta invalido. Use 'simple' ou 'embeddings'.")

    def _build_chunks(self) -> list[dict]:
        chunks: list[dict] = []

        for pessoa in Pessoa.all_objects.order_by("id"):
            text = (
                f"Pessoa {pessoa.id} tipo {pessoa.tipo}. "
                f"Razao social: {pessoa.razao_social}. Documento: {pessoa.documento or 'nao informado'}. "
                f"Cidade: {pessoa.cidade or 'nao informada'}. UF: {pessoa.uf or 'nao informada'}. "
                f"Status: {'ativa' if pessoa.ativo else 'inativa'}."
            )
            chunks.append(self._make_chunk("pessoa", pessoa.id, pessoa.razao_social, text))

        for classificacao in Classificacao.all_objects.order_by("id"):
            text = (
                f"Classificacao {classificacao.id} tipo {classificacao.tipo}. "
                f"Descricao: {classificacao.descricao}. "
                f"Status: {'ativa' if classificacao.ativo else 'inativa'}."
            )
            chunks.append(self._make_chunk("classificacao", classificacao.id, classificacao.descricao, text))

        movimentos = (
            MovimentoContas.all_objects.select_related("fornecedor", "faturado", "classificacao", "invoice_extraction")
            .prefetch_related("parcelas", "classificacoes")
            .order_by("id")
        )
        for movimento in movimentos:
            classificacoes = ", ".join(
                movimento.classificacoes.order_by("id").values_list("descricao", flat=True)
            ) or movimento.classificacao.descricao
            extracted = movimento.invoice_extraction.result_json if movimento.invoice_extraction else {}
            products = extracted.get("produtos") or []
            product_descriptions = ", ".join(
                str(item.get("descricao", "")).strip() for item in products if isinstance(item, dict) and str(item.get("descricao", "")).strip()
            ) or "nenhum item detalhado"
            parcelas = extracted.get("parcelas") or []
            installments_summary = ", ".join(
                f"parcela {item.get('numero')} vence em {item.get('data_vencimento')} no valor de {item.get('valor')}"
                for item in parcelas
                if isinstance(item, dict)
            ) or "sem parcelas detalhadas"
            text = (
                f"Movimento {movimento.id} tipo {movimento.tipo}. "
                f"Fornecedor: {movimento.fornecedor.razao_social}. "
                f"Faturado: {movimento.faturado.razao_social}. "
                f"Nota fiscal: {movimento.numero_nota_fiscal or 'nao informada'}. "
                f"Serie: {movimento.serie or 'nao informada'}. "
                f"Data de emissao: {movimento.data_emissao or 'nao informada'}. "
                f"Valor total: {movimento.valor_total}. "
                f"Classificacoes: {classificacoes}. "
                f"Itens da nota: {product_descriptions}. "
                f"Parcelas: {installments_summary}. "
                f"Status: {'ativo' if movimento.ativo else 'inativo'}."
            )
            chunks.append(self._make_chunk("movimento", movimento.id, f"Movimento {movimento.id}", text))

        for parcela in ParcelaContas.all_objects.select_related("movimento").order_by("id"):
            text = (
                f"Parcela {parcela.id} do movimento {parcela.movimento_id}. "
                f"Identificacao: {parcela.identificacao}. "
                f"Numero da parcela: {parcela.numero_parcela}. "
                f"Vencimento: {parcela.data_vencimento or 'nao informado'}. "
                f"Valor: {parcela.valor}. "
                f"Forma de pagamento: {parcela.forma_pagamento or 'nao informada'}. "
                f"Status: {'ativa' if parcela.ativo else 'inativa'}."
            )
            chunks.append(self._make_chunk("parcela", parcela.id, parcela.identificacao, text))

        for extraction in InvoiceExtraction.objects.order_by("id"):
            fornecedores = extraction.result_json.get("fornecedor", {})
            faturado = extraction.result_json.get("faturado", {})
            products = extraction.result_json.get("produtos") or []
            classifications = extraction.result_json.get("classificacoes_despesa") or []
            title = extraction.file_name
            text = (
                f"Extracao {extraction.id} do arquivo {extraction.file_name}. "
                f"Provider: {extraction.provider}. Status: {extraction.status}. "
                f"Fornecedor extraido: {fornecedores.get('razao_social') or 'nao informado'}. "
                f"Faturado extraido: {faturado.get('nome_completo') or faturado.get('cnpj') or 'nao informado'}. "
                f"Numero da nota fiscal: {extraction.result_json.get('numero_nota_fiscal') or 'nao informado'}. "
                f"Data de emissao: {extraction.result_json.get('data_emissao') or 'nao informada'}. "
                f"Valor total extraido: {extraction.result_json.get('valor_total') or 0}. "
                f"Itens extraidos: {', '.join(str(item.get('descricao', '')).strip() for item in products if isinstance(item, dict) and str(item.get('descricao', '')).strip()) or 'nenhum item detalhado'}. "
                f"Classificacoes extraidas: {', '.join(str(item.get('categoria', '')).strip() for item in classifications if isinstance(item, dict) and str(item.get('categoria', '')).strip()) or 'nenhuma classificacao'}. "
                f"Data de criacao: {extraction.created_at.strftime('%Y-%m-%d %H:%M')}."
            )
            chunks.append(self._make_chunk("extracao", extraction.id, title, text))

        return chunks

    def _rank_chunks(self, question: str, mode: str, chunks: Iterable[dict]) -> list[dict]:
        if mode == self.EMBEDDINGS_MODE:
            question_vector = self._embedding(question)
            scored = []
            for chunk in chunks:
                score = self._cosine_similarity(question_vector, chunk["embedding"])
                if score > 0:
                    scored.append({**chunk, "score": score})
            return sorted(scored, key=lambda item: item["score"], reverse=True)

        question_tokens = set(self._tokenize(question))
        scored = []
        for chunk in chunks:
            overlap = len(question_tokens.intersection(chunk["tokens"]))
            if overlap == 0:
                continue
            scored.append({**chunk, "score": overlap / max(len(chunk["tokens"]), 1)})
        return sorted(scored, key=lambda item: item["score"], reverse=True)

    def _generate_answer(self, question: str, mode: str, chunks: list[dict]) -> tuple[str, str]:
        gemini_api_key = str(getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        if gemini_api_key and chunks:
            try:
                return "gemini", self._answer_with_gemini(question, mode, chunks)
            except Exception:
                pass
        return "mock", self._answer_with_local_summary(question, mode, chunks)

    def _answer_with_gemini(self, question: str, mode: str, chunks: list[dict]) -> str:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        context = "\n".join(
            f"- [{chunk['kind']} #{chunk['id']}] {chunk['text']}" for chunk in chunks
        )
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=(
                "Voce e um assistente de consulta ao banco administrativo-financeiro.\n"
                f"Modo de recuperacao: {mode}.\n"
                "Responda em portugues do Brasil, com base apenas no contexto recuperado. "
                "Se o contexto nao for suficiente, diga isso claramente.\n\n"
                f"Pergunta: {question}\n\n"
                f"Contexto recuperado:\n{context}"
            ),
        )
        return (response.text or "").strip() or self._answer_with_local_summary(question, mode, chunks)

    def _answer_with_local_summary(self, question: str, mode: str, chunks: list[dict]) -> str:
        if not chunks:
            return (
                f"Nao encontrei registros suficientes no banco para responder com seguranca em modo {mode}. "
                "Cadastre notas, pessoas ou movimentos e tente novamente com uma pergunta mais especifica."
            )

        lines = [
            f"Consulta executada em modo {mode}.",
            f"Pergunta analisada: {question}.",
            f"Foram recuperados {len(chunks)} registro(s) mais proximos do banco.",
        ]
        for chunk in chunks[:3]:
            lines.append(
                f"Fonte {chunk['kind']} #{chunk['id']}: {chunk['text']}"
            )
        lines.append(
            "Com base nesses registros, a resposta deve considerar apenas os dados listados acima."
        )
        return " ".join(lines)

    def _build_stats(self, chunks: list[dict]) -> dict:
        counts = Counter(chunk["kind"] for chunk in chunks)
        return {
            "total_registros_indexados": len(chunks),
            "por_tipo": dict(counts),
        }

    def _make_chunk(self, kind: str, record_id: int, title: str, text: str) -> dict:
        clean_text = self._clean_text(text)
        return {
            "kind": kind,
            "id": record_id,
            "title": title,
            "text": text.strip(),
            "tokens": set(self._tokenize(clean_text)),
            "embedding": self._embedding(clean_text),
        }

    def _serialize_chunk(self, chunk: dict) -> dict:
        return {
            "kind": chunk["kind"],
            "id": chunk["id"],
            "title": chunk["title"],
            "score": round(float(chunk["score"]), 4),
            "text": chunk["text"],
        }

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]

    def _embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.EMBEDDING_SIZE
        for token in self._tokenize(text):
            index = hash(token) % self.EMBEDDING_SIZE
            vector[index] += 1.0
        return vector

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()
