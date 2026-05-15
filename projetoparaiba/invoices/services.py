from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import re
import unicodedata
from uuid import uuid4

from django.db import transaction

from .agents import (
    ExpenseClassificationAgent,
    PdfExtractionAgent,
    PersistenceAgent,
    ValidationAgent,
)
from .models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


class InvoiceExtractionService:
    def __init__(self) -> None:
        self.pdf_agent = PdfExtractionAgent()
        self.classification_agent = ExpenseClassificationAgent()
        self.validation_agent = ValidationAgent()
        self.persistence_agent = PersistenceAgent()
        self.registration_service = InvoiceRegistrationService()

    def extract(self, uploaded_file) -> dict:
        extraction = self.pdf_agent.extract(uploaded_file)
        data = self.validation_agent.normalize(extraction.data)

        if not self._should_preserve_gemini_classification(extraction.data):
            data["classificacoes_despesa"] = self.classification_agent.classify(data["produtos"])

        data = self.validation_agent.normalize(data)
        record = self.persistence_agent.save_success(uploaded_file, data, extraction.provider)
        registration = self.registration_service.processar_lancamento(record, data)

        payload = {
            "success": True,
            "id": record.id,
            "provider": extraction.provider,
            "data": data,
            "analysis": registration,
            "message": registration["mensagem"],
        }
        if extraction.fallback_reason:
            payload["fallback_reason"] = extraction.fallback_reason
        return payload

    def _should_preserve_gemini_classification(self, raw_data: object) -> bool:
        if not isinstance(raw_data, Mapping):
            return False

        classification = raw_data.get("classificacoes_despesa")
        if not isinstance(classification, list) or not classification:
            return False

        for item in classification:
            if not isinstance(item, Mapping):
                return False
            categoria = str(item.get("categoria", "")).strip()
            justificativa = str(item.get("justificativa", "")).strip()
            if not categoria or not justificativa:
                return False
            if not self.classification_agent.is_official_category(categoria):
                return False

        return True


class InvoiceRegistrationService:
    @transaction.atomic
    def processar_lancamento(self, extraction_record: InvoiceExtraction, data: dict) -> dict:
        fornecedor_match = self.consultar_fornecedor(data)
        fornecedor = fornecedor_match or self.criar_fornecedor(data)
        historico_fornecedor = self.listar_historico_fornecedor(fornecedor)
        movimento_existente = self.consultar_movimento_existente(fornecedor, data, historico_fornecedor)
        self.validar_parcelas(data)

        if movimento_existente:
            return {
                "fornecedor": self.exibir_resultado_consulta_fornecedor(data, fornecedor, fornecedor),
                "faturado": self._build_analysis_result(
                    titulo="FATURADO",
                    nome=movimento_existente.faturado.razao_social,
                    documento=movimento_existente.faturado.documento,
                    existente=movimento_existente.faturado,
                    final=movimento_existente.faturado,
                ),
                "despesa": self.exibir_resultado_consulta_despesa_existente(movimento_existente.classificacao),
                "movimento": {
                    "id": movimento_existente.id,
                    "tipo": movimento_existente.tipo,
                    "duplicado": True,
                    "status_texto": f"UPLOAD JA REALIZADO - movimento existente ID: {movimento_existente.id}",
                },
                "parcelas": [
                    {
                        "id": parcela.id,
                        "identificacao": parcela.identificacao,
                        "numero_parcela": parcela.numero_parcela,
                        "valor": float(parcela.valor),
                        "data_vencimento": parcela.data_vencimento,
                    }
                    for parcela in movimento_existente.parcelas.all()
                ],
                "historico_fornecedor": self._build_supplier_history(historico_fornecedor),
                "mensagem": "Upload dessa nota ja foi realizado anteriormente.",
            }

        faturado_match = self.consultar_faturado(data)
        faturado = faturado_match or self.criar_faturado(data)

        despesas_info = self.consultar_ou_criar_classificacoes(data, Classificacao.Tipo.DESPESA)
        despesa_match = despesas_info["existentes"][0] if despesas_info["existentes"] else None
        despesa = despesas_info["classificacoes"][0]

        movimento = self.criar_movimento(extraction_record, data, fornecedor, faturado, despesa)
        self.vincular_classificacoes(movimento, despesas_info["classificacoes"])
        parcelas = [self.criar_parcela(movimento, parcela, data) for parcela in data.get("parcelas", [])]

        return {
            "fornecedor": self.exibir_resultado_consulta_fornecedor(data, fornecedor_match, fornecedor),
            "faturado": self.exibir_resultado_consulta_faturado(data, faturado_match, faturado),
            "despesa": self.exibir_resultado_consulta_despesa(data, despesa_match, despesa),
            "despesas": [
                self._build_classificacao_analysis(item["descricao"], item["existente"], item["final"])
                for item in despesas_info["itens"]
            ],
            "movimento": {
                "id": movimento.id,
                "tipo": movimento.tipo,
                "duplicado": False,
                "status_texto": f"MOVIMENTO APAGAR criado - ID: {movimento.id}",
            },
            "parcelas": [
                {
                    "id": parcela.id,
                    "identificacao": parcela.identificacao,
                    "numero_parcela": parcela.numero_parcela,
                    "valor": float(parcela.valor),
                    "data_vencimento": parcela.data_vencimento,
                }
                for parcela in parcelas
            ],
            "historico_fornecedor": self._build_supplier_history(historico_fornecedor),
            "mensagem": "Dados criados no banco com sucesso.",
        }

    def consultar_fornecedor(self, data: dict) -> Pessoa | None:
        fornecedor = data.get("fornecedor", {})
        return self._consultar_pessoa(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            documento=fornecedor.get("cnpj") or fornecedor.get("cpf"),
            razao_social=fornecedor.get("razao_social"),
        )

    def consultar_faturado(self, data: dict) -> Pessoa | None:
        faturado = data.get("faturado", {})
        return self._consultar_pessoa(
            tipo=Pessoa.Tipo.FATURADO,
            documento=faturado.get("cpf") or faturado.get("cnpj"),
            razao_social=faturado.get("nome_completo"),
        )

    def consultar_despesa(self, data: dict) -> Classificacao | None:
        descricao = self._descricao_despesa(data)
        if not descricao:
            return None
        return self._consultar_classificacao_por_descricao(descricao, Classificacao.Tipo.DESPESA)

    def consultar_ou_criar_classificacoes(self, data: dict, tipo: str) -> dict:
        descricoes = self._descricoes_classificacao(data)
        classificacoes: list[Classificacao] = []
        existentes: list[Classificacao] = []
        itens: list[dict] = []

        for descricao in descricoes:
            existente = self._consultar_classificacao_por_descricao(descricao, tipo)
            final = existente or self.criar_classificacao(descricao, tipo)
            classificacoes.append(final)
            if existente:
                existentes.append(existente)
            itens.append({"descricao": descricao, "existente": existente, "final": final})

        if not classificacoes:
            final = self.criar_classificacao("DESPESA NAO INFORMADA", tipo)
            classificacoes.append(final)
            itens.append({"descricao": final.descricao, "existente": None, "final": final})

        return {"classificacoes": classificacoes, "existentes": existentes, "itens": itens}

    def _consultar_classificacao_por_descricao(self, descricao: str, tipo: str) -> Classificacao | None:
        classificacao = (
            Classificacao.all_objects.filter(tipo=tipo)
            .filter(descricao__iexact=descricao.strip())
            .order_by("id")
            .first()
        )
        return self._reativar_se_inativo(classificacao)

    def criar_fornecedor(self, data: dict) -> Pessoa:
        fornecedor = data.get("fornecedor", {})
        return Pessoa.objects.create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            razao_social=self._coalesce(fornecedor.get("razao_social"), "FORNECEDOR NAO INFORMADO"),
            documento=self._clean_document(fornecedor.get("cnpj") or fornecedor.get("cpf")),
            inscricao_estadual=self._string(fornecedor.get("inscricao_estadual")),
            endereco=self._string(fornecedor.get("endereco")),
            cidade=self._string(fornecedor.get("cidade")),
            uf=self._string(fornecedor.get("uf"))[:2],
        )

    def criar_faturado(self, data: dict) -> Pessoa:
        faturado = data.get("faturado", {})
        return Pessoa.objects.create(
            tipo=Pessoa.Tipo.FATURADO,
            razao_social=self._coalesce(faturado.get("nome_completo"), "FATURADO NAO INFORMADO"),
            documento=self._clean_document(faturado.get("cpf") or faturado.get("cnpj")),
            endereco=self._string(faturado.get("endereco")),
            cidade=self._string(faturado.get("cidade")),
            uf=self._string(faturado.get("uf"))[:2],
        )

    def criar_despesa(self, data: dict) -> Classificacao:
        return self.criar_classificacao(self._coalesce(self._descricao_despesa(data), "DESPESA NAO INFORMADA"), Classificacao.Tipo.DESPESA)

    def criar_classificacao(self, descricao: str, tipo: str) -> Classificacao:
        return Classificacao.all_objects.create(
            tipo=tipo,
            descricao=self._coalesce(descricao, "CLASSIFICACAO NAO INFORMADA"),
        )

    def criar_movimento(
        self,
        extraction_record: InvoiceExtraction,
        data: dict,
        fornecedor: Pessoa,
        faturado: Pessoa,
        despesa: Classificacao,
    ) -> MovimentoContas:
        return MovimentoContas.objects.create(
            tipo=MovimentoContas.Tipo.APAGAR,
            fornecedor=fornecedor,
            faturado=faturado,
            classificacao=despesa,
            invoice_extraction=extraction_record,
            numero_nota_fiscal=self._string(data.get("numero_nota_fiscal")),
            serie=self._string(data.get("serie")),
            data_emissao=self._string(data.get("data_emissao")),
            valor_total=self._decimal(data.get("valor_total")),
            observacao=self._build_observacao(data),
        )

    def vincular_classificacoes(self, movimento: MovimentoContas, classificacoes: list[Classificacao]) -> None:
        if classificacoes:
            movimento.classificacoes.set(classificacoes)

    def criar_parcela(self, movimento: MovimentoContas, parcela_data: dict, data: dict) -> ParcelaContas:
        return ParcelaContas.objects.create(
            movimento=movimento,
            identificacao=self._gerar_identificacao_parcela(data, parcela_data),
            numero_parcela=int(parcela_data.get("numero") or 1),
            data_vencimento=self._string(parcela_data.get("data_vencimento")),
            valor=self._decimal(parcela_data.get("valor")),
            forma_pagamento=self._string(parcela_data.get("forma_pagamento")),
        )

    def validar_parcelas(self, data: dict) -> None:
        datas = [self._string(item.get("data_vencimento")) for item in data.get("parcelas", []) if isinstance(item, dict)]
        datas_preenchidas = [data_vencimento for data_vencimento in datas if data_vencimento]
        if len(datas_preenchidas) > 1 and len(set(datas_preenchidas)) != len(datas_preenchidas):
            raise ValueError("Cada parcela deve possuir data de vencimento distinta.")

    def exibir_resultado_consulta_fornecedor(self, data: dict, existente: Pessoa | None, final: Pessoa) -> dict:
        fornecedor = data.get("fornecedor", {})
        return self._build_analysis_result(
            titulo="FORNECEDOR",
            nome=self._coalesce(fornecedor.get("razao_social"), final.razao_social),
            documento=fornecedor.get("cnpj") or fornecedor.get("cpf") or final.documento,
            existente=existente,
            final=final,
        )

    def exibir_resultado_consulta_faturado(self, data: dict, existente: Pessoa | None, final: Pessoa) -> dict:
        faturado = data.get("faturado", {})
        return self._build_analysis_result(
            titulo="FATURADO",
            nome=self._coalesce(faturado.get("nome_completo"), final.razao_social),
            documento=faturado.get("cpf") or faturado.get("cnpj") or final.documento,
            existente=existente,
            final=final,
        )

    def exibir_resultado_consulta_despesa(self, data: dict, existente: Classificacao | None, final: Classificacao) -> dict:
        descricao = self._coalesce(self._descricao_despesa(data), final.descricao)
        return self._build_classificacao_analysis(descricao, existente, final)

    def exibir_resultado_consulta_despesa_existente(self, classificacao: Classificacao) -> dict:
        return self._build_classificacao_analysis(classificacao.descricao, classificacao, classificacao)

    def listar_historico_fornecedor(self, fornecedor: Pessoa) -> list[MovimentoContas]:
        return list(
            MovimentoContas.all_objects.filter(fornecedor=fornecedor, ativo=True)
            .select_related("faturado", "classificacao", "invoice_extraction")
            .prefetch_related("parcelas")
            .order_by("-created_at", "-id")
        )

    def consultar_movimento_existente(
        self,
        fornecedor: Pessoa,
        data: dict,
        historico: list[MovimentoContas] | None = None,
    ) -> MovimentoContas | None:
        numero_nota = self._string(data.get("numero_nota_fiscal"))
        serie = self._string(data.get("serie"))
        chave_acesso = self._string(data.get("chave_acesso"))
        movimentos = historico if historico is not None else self.listar_historico_fornecedor(fornecedor)

        if not numero_nota and not chave_acesso:
            return None

        for movimento in movimentos:
            self._reativar_movimento_com_parcelas(movimento)
            dados_salvos = movimento.invoice_extraction.result_json if movimento.invoice_extraction else {}
            chave_salva = self._string(dados_salvos.get("chave_acesso"))
            if chave_acesso and chave_salva and chave_acesso == chave_salva:
                return movimento

            if numero_nota and numero_nota == self._string(movimento.numero_nota_fiscal):
                serie_salva = self._string(movimento.serie)
                if not serie or not serie_salva or serie == serie_salva:
                    return movimento

        return None

    def _consultar_pessoa(self, *, tipo: str, documento: object, razao_social: object) -> Pessoa | None:
        documento_limpo = self._clean_document(documento)
        tipos_validos = self._tipos_pessoa_consulta(tipo)
        if documento_limpo:
            pessoa = (
                Pessoa.all_objects.filter(tipo__in=tipos_validos, documento=documento_limpo)
                .order_by("id")
                .first()
            )
            if pessoa:
                return self._reativar_se_inativo(pessoa)

        nome_normalizado = self._normalize_text(razao_social)
        if nome_normalizado:
            for pessoa in Pessoa.all_objects.filter(tipo__in=tipos_validos).order_by("id"):
                if self._normalize_text(pessoa.razao_social) == nome_normalizado:
                    return self._reativar_se_inativo(pessoa)
        return None

    def _build_analysis_result(self, *, titulo: str, nome: str, documento: object, existente, final) -> dict:
        documento_str = self._string(documento)
        return {
            "titulo": titulo,
            "nome": nome,
            "documento_label": self._document_label(documento_str),
            "documento": documento_str,
            "existe": existente is not None,
            "id": final.id,
            "acao": "reutilizado" if existente else "criado",
            "status_texto": f"EXISTE - ID: {final.id}" if existente else f"NAO EXISTE - criado ID: {final.id}",
        }

    def _build_classificacao_analysis(self, descricao: str, existente: Classificacao | None, final: Classificacao) -> dict:
        existe = existente is not None
        return {
            "titulo": "DESPESA" if final.tipo == Classificacao.Tipo.DESPESA else "RECEITA",
            "nome": descricao,
            "documento_label": "Tipo",
            "documento": final.tipo,
            "existe": existe,
            "id": final.id,
            "acao": "reutilizado" if existe else "criado",
            "status_texto": f"EXISTE - ID: {final.id}" if existe else f"NAO EXISTE - criado ID: {final.id}",
        }

    def _build_supplier_history(self, movimentos: list[MovimentoContas]) -> dict:
        itens = [self._serialize_supplier_history_item(movimento) for movimento in movimentos]
        return {
            "titulo": "Historico do fornecedor",
            "possui_dados": bool(itens),
            "quantidade": len(itens),
            "itens": itens,
        }

    def _serialize_supplier_history_item(self, movimento: MovimentoContas) -> dict:
        dados_salvos = movimento.invoice_extraction.result_json if movimento.invoice_extraction else {}
        return {
            "movimento_id": movimento.id,
            "numero_nota_fiscal": movimento.numero_nota_fiscal,
            "serie": movimento.serie,
            "data_emissao": movimento.data_emissao,
            "valor_total": float(movimento.valor_total),
            "classificacao": movimento.classificacao.descricao,
            "faturado": movimento.faturado.razao_social,
            "arquivo": movimento.invoice_extraction.file_name if movimento.invoice_extraction else "",
            "provider": movimento.invoice_extraction.provider if movimento.invoice_extraction else "",
            "criado_em": movimento.created_at.strftime("%d/%m/%Y %H:%M"),
            "parcelas": [
                {
                    "id": parcela.id,
                    "identificacao": parcela.identificacao,
                    "numero_parcela": parcela.numero_parcela,
                    "data_vencimento": parcela.data_vencimento,
                    "valor": float(parcela.valor),
                }
                for parcela in movimento.parcelas.all()
            ],
            "dados_extraidos": dados_salvos,
        }

    def _descricao_despesa(self, data: dict) -> str:
        classificacoes = data.get("classificacoes_despesa") or []
        if not classificacoes:
            return ""
        primeira = classificacoes[0] if isinstance(classificacoes[0], dict) else {}
        return self._string(primeira.get("categoria"))

    def _descricoes_classificacao(self, data: dict) -> list[str]:
        descricoes: list[str] = []
        for item in data.get("classificacoes_despesa") or []:
            if isinstance(item, dict):
                descricao = self._string(item.get("categoria"))
                if descricao and descricao not in descricoes:
                    descricoes.append(descricao)
        return descricoes

    def _build_observacao(self, data: dict) -> str:
        partes = []
        natureza = self._string(data.get("natureza_operacao"))
        if natureza:
            partes.append(f"Natureza da operacao: {natureza}")
        chave = self._string(data.get("chave_acesso"))
        if chave:
            partes.append(f"Chave de acesso: {chave}")
        if not partes:
            partes.append("Lancamento gerado automaticamente a partir da extracao da nota fiscal.")
        return " | ".join(partes)

    def _gerar_identificacao_parcela(self, data: dict, parcela_data: dict) -> str:
        numero_nota = self._slug(self._string(data.get("numero_nota_fiscal")) or "sem-nota")
        numero_parcela = int(parcela_data.get("numero") or 1)
        base = f"APAGAR-{numero_nota}-{numero_parcela}"
        identificacao = base
        while ParcelaContas.objects.filter(identificacao=identificacao).exists():
            identificacao = f"{base}-{uuid4().hex[:6].upper()}"
        return identificacao

    def _document_label(self, documento: str) -> str:
        digits = self._clean_document(documento)
        if len(digits) == 11:
            return "CPF"
        if len(digits) == 14:
            return "CNPJ"
        return "Documento"

    def _clean_document(self, value: object) -> str:
        return re.sub(r"\D", "", self._string(value))

    def _tipos_pessoa_consulta(self, tipo: str) -> list[str]:
        if tipo == Pessoa.Tipo.CLIENTE_FORNECEDOR:
            return [Pessoa.Tipo.CLIENTE_FORNECEDOR, Pessoa.Tipo.FORNECEDOR]
        if tipo == Pessoa.Tipo.FATURADO:
            return [Pessoa.Tipo.FATURADO, Pessoa.Tipo.CLIENTE]
        return [tipo]

    def _reativar_se_inativo(self, registro):
        if registro is not None and hasattr(registro, "ativo") and not registro.ativo:
            registro.reactivate()
        return registro

    def _reativar_movimento_com_parcelas(self, movimento: MovimentoContas) -> MovimentoContas:
        self._reativar_se_inativo(movimento)
        for parcela in movimento.parcelas.all():
            self._reativar_se_inativo(parcela)
        return movimento

    def _normalize_text(self, value: object) -> str:
        text = self._string(value).lower()
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(char for char in normalized if not unicodedata.combining(char)).strip()

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
        return slug or "SEM-VALOR"

    def _string(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _coalesce(self, value: object, fallback: str) -> str:
        return self._string(value) or fallback

    def _decimal(self, value: object) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")
