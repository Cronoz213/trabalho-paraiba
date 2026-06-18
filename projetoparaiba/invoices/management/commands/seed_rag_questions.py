from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from invoices.models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


class Command(BaseCommand):
    help = "Insere notas fiscais direcionadas para perguntas especificas do RAG."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._insert_targeted_notes()
        self.stdout.write(self.style.SUCCESS("Notas direcionadas ao RAG inseridas com sucesso."))

    def _insert_targeted_notes(self) -> None:
        self._ensure_question_one_data()
        self._ensure_question_two_data()
        self._ensure_question_three_data()
        self._ensure_question_four_data()

    def _ensure_question_one_data(self) -> None:
        fornecedor_a = self._supplier(
            "MAX AGRO COMBUSTIVEIS LTDA",
            "99.888.777/0001-66",
            "998877665",
            "Rodovia BR 101 KM 22",
            "Joao Pessoa",
            "PB",
        )
        fornecedor_b = self._supplier(
            "NORDESTE FERRAGENS INDUSTRIA LTDA",
            "88.777.666/0001-55",
            "887766554",
            "Avenida das Industrias 450",
            "Campina Grande",
            "PB",
        )
        faturado = self._customer(
            "AGRO VALE CENTRAL LTDA",
            "21.222.333/0001-09",
            "Rua da Safra 120",
            "Patos",
            "PB",
        )

        self._create_note_if_missing(
            note_number="RAG2025001",
            issue_date=date(2025, 3, 18),
            supplier=fornecedor_a,
            customer=faturado,
            items=[
                self._item("Oleo Diesel S10", 4500, "LT", "5.40", "27101921", "5102"),
                self._item("Lubrificante para motor premium", 120, "LT", "28.00", "27101932", "5102"),
            ],
            classifications=[("MANUTENCAO E OPERACAO", "Combustiveis e lubrificantes para operacao de frota e maquinas.")],
            installments=[45, 75],
        )
        self._create_note_if_missing(
            note_number="RAG2025002",
            issue_date=date(2025, 7, 2),
            supplier=fornecedor_b,
            customer=faturado,
            items=[
                self._item("Peca hidraulica reforcada", 18, "UN", "980.00", "84122990", "5102"),
                self._item("Material eletrico industrial", 30, "CX", "210.00", "85369090", "5102"),
            ],
            classifications=[
                ("MANUTENCAO E OPERACAO", "Itens de manutencao tecnica usados na infraestrutura operacional."),
                ("INVESTIMENTOS", "Parte dos itens amplia a capacidade operacional."),
            ],
            installments=[30, 60, 90],
        )
        self._create_note_if_missing(
            note_number="RAG2025003",
            issue_date=date(2025, 11, 11),
            supplier=fornecedor_a,
            customer=faturado,
            items=[
                self._item("Trator implemento agricola", 1, "UN", "92000.00", "87019090", "5102"),
            ],
            classifications=[("INVESTIMENTOS", "A nota representa aquisicao de equipamento de alto valor.")],
            installments=[30, 60, 90, 120],
        )

    def _ensure_question_two_data(self) -> None:
        fornecedor = self._supplier(
            "ALFA SERVICOS OPERACIONAIS LTDA",
            "77.666.555/0001-44",
            "776665554",
            "Rua dos Galpoes 600",
            "Recife",
            "PE",
        )
        faturado = self._customer(
            "BELTRANO DE SOUZA",
            "111.111.111-11",
            "Rua do Centro 80",
            "Sousa",
            "PB",
        )

        self._create_note_if_missing(
            note_number="RAG2025BEL01",
            issue_date=date(2025, 8, 20),
            supplier=fornecedor,
            customer=faturado,
            items=[
                self._item("Servico de manutencao de colheitadeira", 1, "UN", "6800.00", "99871900", "5933"),
                self._item("Peca hidraulica de reposicao", 4, "UN", "720.00", "84122990", "5102"),
            ],
            classifications=[("MANUTENCAO E OPERACAO", "Servicos e pecas ligados a manutencao operacional.")],
            installments=[40, 70, 110],
        )
        self._create_note_if_missing(
            note_number="RAG2025BEL02",
            issue_date=date(2025, 9, 25),
            supplier=fornecedor,
            customer=faturado,
            items=[
                self._item("Software de gestao rural", 1, "UN", "2400.00", "85234910", "5933"),
                self._item("Material de escritorio", 10, "CX", "90.00", "48201000", "5102"),
            ],
            classifications=[("ADMINISTRATIVAS", "Itens administrativos contratados para controle interno.")],
            installments=[30, 60, 95],
        )

    def _ensure_question_three_data(self) -> None:
        fornecedor = self._supplier(
            "CORRETIVOS DO SOLO PARAIBA LTDA",
            "66.555.444/0001-33",
            "665554443",
            "Estrada da Mineracao 150",
            "Cabedelo",
            "PB",
        )
        faturado = self._customer(
            "FAZENDA MODELO SUL",
            "32.444.555/0001-77",
            "Rodovia Municipal KM 5",
            "Itabaiana",
            "PB",
        )

        self._create_note_if_missing(
            note_number="RAGSEM001",
            issue_date=date(2025, 5, 14),
            supplier=fornecedor,
            customer=faturado,
            items=[
                self._item("Corretivo de solo calcario dolomitico", 280, "SC", "42.00", "31039090", "5101"),
                self._item("Neutralizador de acidez para solo", 160, "SC", "58.00", "31039090", "5101"),
            ],
            classifications=[("MANUTENCAO E OPERACAO", "Os itens foram classificados como manutencao por estarem ligados a recuperacao operacional do solo.")],
            installments=[30, 60],
        )

    def _ensure_question_four_data(self) -> None:
        fornecedor = self._supplier(
            "DEFENSIVOS AGRICOLAS SERTAO LTDA",
            "55.444.333/0001-22",
            "554443332",
            "Av. dos Insumos 999",
            "Petrolina",
            "PE",
        )
        faturado = self._customer(
            "FAZENDA ESPERANCA DO AGRESTE",
            "43.555.666/0001-88",
            "Estrada do Algodao 320",
            "Monteiro",
            "PB",
        )

        self._create_note_if_missing(
            note_number="RAGSEM002",
            issue_date=date(2025, 10, 9),
            supplier=fornecedor,
            customer=faturado,
            items=[
                self._item("Fungicida para ferrugem asiatica e oidio da soja", 220, "LT", "315.00", "38089199", "5101"),
                self._item("Inseticida para lagarta e percevejo da lavoura", 180, "LT", "276.00", "38089199", "5101"),
                self._item("Defensivo agricola para controle de pulgao", 140, "LT", "198.00", "38089199", "5101"),
            ],
            classifications=[("INSUMOS AGRICOLAS", "Os itens sao defensivos e fungicidas destinados ao manejo fitossanitario da lavoura.")],
            installments=[35, 70, 105],
        )

    def _create_note_if_missing(
        self,
        *,
        note_number: str,
        issue_date: date,
        supplier: Pessoa,
        customer: Pessoa,
        items: list[dict],
        classifications: list[tuple[str, str]],
        installments: list[int],
    ) -> None:
        if MovimentoContas.all_objects.filter(numero_nota_fiscal=note_number).exists():
            return

        series = "1"
        value_products = sum(item["valor_total"] for item in items)
        discount = Decimal("0.00")
        freight = Decimal("120.00")
        icms = (value_products * Decimal("0.12")).quantize(Decimal("0.01"))
        ipi = (value_products * Decimal("0.04")).quantize(Decimal("0.01"))
        total_value = (value_products - discount + freight + icms + ipi).quantize(Decimal("0.01"))

        parcels = self._build_installments(issue_date, total_value, installments)
        classification_payload = [{"categoria": name, "justificativa": reason} for name, reason in classifications]

        extraction = InvoiceExtraction.objects.create(
            file_name=f"{note_number}.pdf",
            file_size=245000,
            provider="mock",
            status=InvoiceExtraction.Status.SUCCESS,
            result_json={
                "fornecedor": {
                    "razao_social": supplier.razao_social,
                    "fantasia": supplier.razao_social.split(" ")[0],
                    "cnpj": self._format_cnpj(supplier.documento),
                    "inscricao_estadual": supplier.inscricao_estadual,
                    "endereco": supplier.endereco,
                    "cidade": supplier.cidade,
                    "uf": supplier.uf,
                },
                "faturado": {
                    "nome_completo": customer.razao_social,
                    "cpf": self._format_cpf(customer.documento) if len(customer.documento) == 11 else "",
                    "cnpj": self._format_cnpj(customer.documento) if len(customer.documento) == 14 else "",
                    "endereco": customer.endereco,
                    "cidade": customer.cidade,
                    "uf": customer.uf,
                },
                "numero_nota_fiscal": note_number,
                "data_emissao": issue_date.isoformat(),
                "serie": series,
                "chave_acesso": self._build_access_key(note_number),
                "natureza_operacao": "Venda de mercadoria",
                "produtos": [
                    {
                        "descricao": item["descricao"],
                        "quantidade": float(item["quantidade"]),
                        "unidade": item["unidade"],
                        "valor_unitario": float(item["valor_unitario"]),
                        "valor_total": float(item["valor_total"]),
                        "ncm": item["ncm"],
                        "cfop": item["cfop"],
                    }
                    for item in items
                ],
                "parcelas": [
                    {
                        "numero": parcel["numero"],
                        "data_vencimento": parcel["data_vencimento"],
                        "valor": float(parcel["valor"]),
                        "forma_pagamento": parcel["forma_pagamento"],
                    }
                    for parcel in parcels
                ],
                "valor_produtos": float(value_products),
                "valor_desconto": float(discount),
                "valor_frete": float(freight),
                "valor_icms": float(icms),
                "valor_ipi": float(ipi),
                "valor_total": float(total_value),
                "classificacoes_despesa": classification_payload,
            },
        )

        main_classification = self._classification(classifications[0][0])
        movement = MovimentoContas.objects.create(
            tipo=MovimentoContas.Tipo.APAGAR,
            fornecedor=supplier,
            faturado=customer,
            classificacao=main_classification,
            invoice_extraction=extraction,
            numero_nota_fiscal=note_number,
            serie=series,
            data_emissao=issue_date.isoformat(),
            valor_total=total_value,
            observacao=f"Nota criada para cenarios especificos do RAG: {note_number}",
        )
        movement.classificacoes.set([self._classification(name) for name, _reason in classifications])

        for parcel in parcels:
            ParcelaContas.objects.create(
                movimento=movement,
                identificacao=f"{note_number}-{parcel['numero']}",
                numero_parcela=parcel["numero"],
                data_vencimento=parcel["data_vencimento"],
                valor=parcel["valor"],
                forma_pagamento=parcel["forma_pagamento"],
            )

    def _item(self, description: str, quantity: int, unit: str, unit_price: str, ncm: str, cfop: str) -> dict:
        unit_value = Decimal(unit_price).quantize(Decimal("0.01"))
        qty = Decimal(str(quantity))
        return {
            "descricao": description,
            "quantidade": qty,
            "unidade": unit,
            "valor_unitario": unit_value,
            "valor_total": (qty * unit_value).quantize(Decimal("0.01")),
            "ncm": ncm,
            "cfop": cfop,
        }

    def _build_installments(self, issue_date: date, total_value: Decimal, offsets: list[int]) -> list[dict]:
        count = len(offsets)
        base_value = (total_value / Decimal(str(count))).quantize(Decimal("0.01"))
        parcels = []
        accumulated = Decimal("0.00")
        for index, offset in enumerate(offsets, start=1):
            if index == count:
                value = (total_value - accumulated).quantize(Decimal("0.01"))
            else:
                value = base_value
                accumulated += value
            parcels.append(
                {
                    "numero": index,
                    "data_vencimento": (issue_date + timedelta(days=offset)).isoformat(),
                    "valor": value,
                    "forma_pagamento": "Boleto",
                }
            )
        return parcels

    def _supplier(self, name: str, cnpj: str, ie: str, address: str, city: str, uf: str) -> Pessoa:
        person, _ = Pessoa.all_objects.get_or_create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            documento=self._digits(cnpj),
            defaults={
                "razao_social": name,
                "inscricao_estadual": ie,
                "endereco": address,
                "cidade": city,
                "uf": uf,
                "ativo": True,
            },
        )
        if not person.ativo:
            person.reactivate()
        return person

    def _customer(self, name: str, document: str, address: str, city: str, uf: str) -> Pessoa:
        person, _ = Pessoa.all_objects.get_or_create(
            tipo=Pessoa.Tipo.FATURADO,
            documento=self._digits(document),
            defaults={
                "razao_social": name,
                "endereco": address,
                "cidade": city,
                "uf": uf,
                "ativo": True,
            },
        )
        if not person.ativo:
            person.reactivate()
        return person

    def _classification(self, description: str) -> Classificacao:
        item, _ = Classificacao.all_objects.get_or_create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao=description,
            defaults={"ativo": True},
        )
        if not item.ativo:
            item.reactivate()
        return item

    def _build_access_key(self, note_number: str) -> str:
        digits = "".join(char for char in note_number if char.isdigit()) or "1"
        key = f"2525101234567800019055001{digits.zfill(17)}"
        return key[:44].ljust(44, "0")

    def _digits(self, value: str) -> str:
        return "".join(char for char in value if char.isdigit())

    def _format_cnpj(self, value: str) -> str:
        digits = self._digits(value).zfill(14)[:14]
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

    def _format_cpf(self, value: str) -> str:
        digits = self._digits(value).zfill(11)[:11]
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
