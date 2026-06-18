from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from invoices.models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


@dataclass(frozen=True)
class SupplierTemplate:
    razao_social: str
    fantasia: str
    cnpj: str
    inscricao_estadual: str
    endereco: str
    cidade: str
    uf: str


@dataclass(frozen=True)
class CustomerTemplate:
    nome: str
    documento: str
    tipo_documento: str
    endereco: str
    cidade: str
    uf: str


@dataclass(frozen=True)
class ProductTemplate:
    descricao: str
    unidade: str
    ncm: str
    cfop: str
    min_qtd: int
    max_qtd: int
    min_price: str
    max_price: str
    categories: tuple[str, ...]
    natureza: str


class Command(BaseCommand):
    help = "Insere 200 notas fiscais sinteticas diretamente no banco."

    expense_categories = (
        "INSUMOS AGRICOLAS",
        "MANUTENCAO E OPERACAO",
        "RECURSOS HUMANOS",
        "SERVICOS OPERACIONAIS",
        "INFRAESTRUTURA E UTILIDADES",
        "ADMINISTRATIVAS",
        "SEGUROS E PROTECAO",
        "IMPOSTOS E TAXAS",
        "INVESTIMENTOS",
    )

    payment_methods = ("Boleto", "Pix", "Transferencia", "Cartao", "Dinheiro")
    series = ("1", "2", "3", "4", "5")
    providers = ("mock", "gemini")

    def handle(self, *args, **options):
        rng = random.Random(20260611)
        with transaction.atomic():
            summary = self._seed(rng)

        self.stdout.write(self.style.SUCCESS("Carga concluida com sucesso."))
        self.stdout.write(str(summary))

    def _seed(self, rng: random.Random) -> dict:
        suppliers = self._suppliers()
        customers = self._customers()
        products = self._products()

        created_extractions = 0
        created_movements = 0
        created_installments = 0

        for index in range(1, 201):
            supplier = self._get_or_create_supplier(rng.choice(suppliers))
            customer = self._get_or_create_customer(rng.choice(customers))
            product_items = self._build_products(rng, products)
            classifications_payload = self._build_classifications(product_items)
            main_classification = self._get_or_create_classification(classifications_payload[0]["categoria"])
            extra_classifications = [
                self._get_or_create_classification(item["categoria"]) for item in classifications_payload
            ]

            issue_date = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1210))
            note_number = f"{700000 + index}"
            serie = rng.choice(self.series)
            product_total = sum(item["valor_total"] for item in product_items)
            discount = self._random_money(rng, "0", "180")
            freight = self._random_money(rng, "0", "320")
            icms = (product_total * Decimal("0.12")).quantize(Decimal("0.01"))
            ipi = (product_total * Decimal("0.04")).quantize(Decimal("0.01"))
            total_value = (product_total - discount + freight + icms + ipi).quantize(Decimal("0.01"))
            installments = self._build_installments(rng, issue_date, total_value, note_number)
            natureza = product_items[0]["natureza_operacao"]
            chave = self._build_access_key(index)

            result_json = {
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
                "serie": serie,
                "chave_acesso": chave,
                "natureza_operacao": natureza,
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
                    for item in product_items
                ],
                "parcelas": [
                    {
                        "numero": item["numero"],
                        "data_vencimento": item["data_vencimento"],
                        "valor": float(item["valor"]),
                        "forma_pagamento": item["forma_pagamento"],
                    }
                    for item in installments
                ],
                "valor_produtos": float(product_total),
                "valor_desconto": float(discount),
                "valor_frete": float(freight),
                "valor_icms": float(icms),
                "valor_ipi": float(ipi),
                "valor_total": float(total_value),
                "classificacoes_despesa": classifications_payload,
            }

            extraction = InvoiceExtraction.objects.create(
                file_name=f"nota_seed_{note_number}.pdf",
                file_size=rng.randint(120_000, 760_000),
                provider=rng.choice(self.providers),
                status=InvoiceExtraction.Status.SUCCESS,
                result_json=result_json,
            )
            created_extractions += 1

            movement = MovimentoContas.objects.create(
                tipo=MovimentoContas.Tipo.APAGAR,
                fornecedor=supplier,
                faturado=customer,
                classificacao=main_classification,
                invoice_extraction=extraction,
                numero_nota_fiscal=note_number,
                serie=serie,
                data_emissao=issue_date.isoformat(),
                valor_total=total_value,
                observacao=f"Movimento gerado por seed automatica. Chave de acesso: {chave}",
            )
            movement.classificacoes.set(extra_classifications)
            created_movements += 1

            for installment in installments:
                ParcelaContas.objects.create(
                    movimento=movement,
                    identificacao=f"SEED-{note_number}-{installment['numero']}",
                    numero_parcela=installment["numero"],
                    data_vencimento=installment["data_vencimento"],
                    valor=installment["valor"],
                    forma_pagamento=installment["forma_pagamento"],
                )
                created_installments += 1

        return {
            "extracoes_criadas": created_extractions,
            "movimentos_criados": created_movements,
            "parcelas_criadas": created_installments,
        }

    def _get_or_create_supplier(self, template: SupplierTemplate) -> Pessoa:
        defaults = {
            "razao_social": template.razao_social,
            "inscricao_estadual": template.inscricao_estadual,
            "endereco": template.endereco,
            "cidade": template.cidade,
            "uf": template.uf,
            "ativo": True,
        }
        person, _ = Pessoa.all_objects.get_or_create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            documento=self._digits(template.cnpj),
            defaults=defaults,
        )
        if not person.ativo:
            person.reactivate()
        return person

    def _get_or_create_customer(self, template: CustomerTemplate) -> Pessoa:
        defaults = {
            "razao_social": template.nome,
            "endereco": template.endereco,
            "cidade": template.cidade,
            "uf": template.uf,
            "ativo": True,
        }
        person, _ = Pessoa.all_objects.get_or_create(
            tipo=Pessoa.Tipo.FATURADO,
            documento=self._digits(template.documento),
            defaults=defaults,
        )
        if not person.ativo:
            person.reactivate()
        return person

    def _get_or_create_classification(self, description: str) -> Classificacao:
        classification, _ = Classificacao.all_objects.get_or_create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao=description,
            defaults={"ativo": True},
        )
        if not classification.ativo:
            classification.reactivate()
        return classification

    def _build_products(self, rng: random.Random, products: list[ProductTemplate]) -> list[dict]:
        quantity = rng.randint(1, 5)
        selected = [rng.choice(products) for _ in range(quantity)]
        items = []
        for template in selected:
            qtd = Decimal(str(rng.randint(template.min_qtd, template.max_qtd)))
            unit_price = self._random_money(rng, template.min_price, template.max_price)
            total = (qtd * unit_price).quantize(Decimal("0.01"))
            items.append(
                {
                    "descricao": template.descricao,
                    "quantidade": qtd,
                    "unidade": template.unidade,
                    "valor_unitario": unit_price,
                    "valor_total": total,
                    "ncm": template.ncm,
                    "cfop": template.cfop,
                    "categorias": template.categories,
                    "natureza_operacao": template.natureza,
                }
            )
        return items

    def _build_classifications(self, product_items: list[dict]) -> list[dict]:
        seen: list[str] = []
        payload: list[dict] = []
        for item in product_items:
            for category in item["categorias"]:
                if category in seen:
                    continue
                seen.append(category)
                payload.append(
                    {
                        "categoria": category,
                        "justificativa": f"A nota possui item '{item['descricao']}', associado a {category.lower()}.",
                    }
                )
        return payload[:2] or [
            {
                "categoria": "ADMINISTRATIVAS",
                "justificativa": "A nota foi inserida com contexto administrativo padrao.",
            }
        ]

    def _build_installments(
        self,
        rng: random.Random,
        issue_date: date,
        total_value: Decimal,
        note_number: str,
    ) -> list[dict]:
        count = rng.randint(1, 4)
        installments: list[dict] = []
        accumulated = Decimal("0.00")
        for number in range(1, count + 1):
            due_date = issue_date + timedelta(days=30 * number)
            if number == count:
                value = (total_value - accumulated).quantize(Decimal("0.01"))
            else:
                remaining = count - number + 1
                average = (total_value / Decimal(str(remaining))).quantize(Decimal("0.01"))
                value = min(
                    (total_value - accumulated).quantize(Decimal("0.01")),
                    self._random_money(rng, str(max(average * Decimal("0.75"), Decimal("50.00"))), str(max(average * Decimal("1.25"), Decimal("80.00")))),
                )
                accumulated += value
            installments.append(
                {
                    "numero": number,
                    "data_vencimento": due_date.isoformat(),
                    "valor": value,
                    "forma_pagamento": rng.choice(self.payment_methods),
                }
            )
        difference = total_value - sum(item["valor"] for item in installments)
        installments[-1]["valor"] = (installments[-1]["valor"] + difference).quantize(Decimal("0.01"))
        return installments

    def _build_access_key(self, index: int) -> str:
        prefix = f"25{(23 + (index % 4)):02d}01"
        body = f"{12345678000190 + index:014d}{550010000000000 + index:015d}"
        key = f"{prefix}{body}"
        return key[:44].ljust(44, "0")

    def _random_money(self, rng: random.Random, low: str, high: str) -> Decimal:
        cents = rng.randint(int(Decimal(low) * 100), int(Decimal(high) * 100))
        return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))

    def _digits(self, value: str) -> str:
        return "".join(char for char in value if char.isdigit())

    def _format_cnpj(self, value: str) -> str:
        digits = self._digits(value).zfill(14)[:14]
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

    def _format_cpf(self, value: str) -> str:
        digits = self._digits(value).zfill(11)[:11]
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"

    def _suppliers(self) -> list[SupplierTemplate]:
        return [
            SupplierTemplate("AGRO CAMPO NORDESTE LTDA", "AGRO CAMPO", "12.345.678/0001-90", "123456789", "BR 230 KM 12", "Campina Grande", "PB"),
            SupplierTemplate("PARAIBA DIESEL DISTRIBUIDORA LTDA", "PB DIESEL", "23.456.789/0001-01", "223344556", "Av. Industrial 450", "Joao Pessoa", "PB"),
            SupplierTemplate("SERTAO PECAS E MAQUINAS LTDA", "SERTAO PECAS", "34.567.890/0001-12", "334455667", "Rua das Oficinas 88", "Patos", "PB"),
            SupplierTemplate("HIDRO SOLUCOES TECNICAS LTDA", "HIDRO SOLUCOES", "45.678.901/0001-23", "445566778", "Rua do Comercio 210", "Recife", "PE"),
            SupplierTemplate("LUZ E FORCA UTILIDADES SA", "LUZ E FORCA", "56.789.012/0001-34", "556677889", "Avenida Central 1500", "Fortaleza", "CE"),
            SupplierTemplate("SEGURO RURAL BRASIL SA", "SEGURO RURAL", "67.890.123/0001-45", "667788990", "Av. Seguradora 900", "Salvador", "BA"),
            SupplierTemplate("ADMIN OFFICE SUPRIMENTOS LTDA", "ADMIN OFFICE", "78.901.234/0001-56", "778899001", "Rua das Empresas 33", "Natal", "RN"),
            SupplierTemplate("VERDE INSUMOS AGRICOLAS LTDA", "VERDE INSUMOS", "89.012.345/0001-67", "889900112", "Rodovia do Agro 500", "Luis Eduardo Magalhaes", "BA"),
            SupplierTemplate("SERVICOS OPERACIONAIS DO NORDESTE LTDA", "SON OPERACOES", "90.123.456/0001-78", "990011223", "Rua do Porto 120", "Maceio", "AL"),
            SupplierTemplate("EQUIPAMENTOS E INVESTIMENTOS DO BRASIL LTDA", "INVEST BR", "11.234.567/0001-89", "101112131", "Av. Tecnologica 300", "Goiania", "GO"),
        ]

    def _customers(self) -> list[CustomerTemplate]:
        return [
            CustomerTemplate("FAZENDA BOA ESPERANCA", "123.456.789-00", "cpf", "Sitio Boa Esperanca", "Pombal", "PB"),
            CustomerTemplate("GRUPO SAO MIGUEL AGROPECUARIA", "12.111.222/0001-33", "cnpj", "Rodovia PB 100 KM 4", "Sousa", "PB"),
            CustomerTemplate("USINA VALE VERDE LTDA", "23.222.333/0001-44", "cnpj", "Distrito Industrial 2", "Santa Rita", "PB"),
            CustomerTemplate("COOPERATIVA RURAL DO SERTAO", "34.333.444/0001-55", "cnpj", "Rua do Campo 500", "Patos", "PB"),
            CustomerTemplate("MARIA DAS DORES SILVA", "234.567.890-11", "cpf", "Rua Jose Amaro 45", "Cajazeiras", "PB"),
            CustomerTemplate("JOSE ROBERTO ALVES", "345.678.901-22", "cpf", "Sitio Lagoa Nova", "Monteiro", "PB"),
            CustomerTemplate("AGROPECUARIA SANTA HELENA LTDA", "45.444.555/0001-66", "cnpj", "BR 101 KM 88", "Mamanguape", "PB"),
            CustomerTemplate("TRANSPORTES E LOGISTICA CARIRI LTDA", "56.555.666/0001-77", "cnpj", "Rua do Transporte 98", "Campina Grande", "PB"),
            CustomerTemplate("LUCIANA FERREIRA COSTA", "456.789.012-33", "cpf", "Rua Nova 19", "Guarabira", "PB"),
            CustomerTemplate("NORTE GRAOS COMERCIAL LTDA", "67.666.777/0001-88", "cnpj", "Avenida dos Graos 77", "Petrolina", "PE"),
        ]

    def _products(self) -> list[ProductTemplate]:
        return [
            ProductTemplate("Oleo Diesel S10", "LT", "27101921", "5102", 200, 1500, "4.80", "6.90", ("MANUTENCAO E OPERACAO",), "Venda de mercadoria"),
            ProductTemplate("Lubrificante para motor", "LT", "27101932", "5102", 10, 120, "14.00", "32.00", ("MANUTENCAO E OPERACAO",), "Manutencao operacional"),
            ProductTemplate("Peca hidraulica", "UN", "84122990", "5102", 1, 20, "180.00", "1200.00", ("MANUTENCAO E OPERACAO", "INVESTIMENTOS"), "Manutencao operacional"),
            ProductTemplate("Material eletrico", "CX", "85369090", "5102", 1, 12, "80.00", "650.00", ("INFRAESTRUTURA E UTILIDADES",), "Compra para uso e consumo"),
            ProductTemplate("Material de escritorio", "CX", "48201000", "5102", 1, 15, "25.00", "180.00", ("ADMINISTRATIVAS",), "Despesa administrativa"),
            ProductTemplate("Servico de manutencao", "UN", "99871900", "5933", 1, 6, "350.00", "2400.00", ("SERVICOS OPERACIONAIS", "MANUTENCAO E OPERACAO"), "Prestacao de servico"),
            ProductTemplate("Fertilizante", "SC", "31052000", "5101", 20, 200, "110.00", "240.00", ("INSUMOS AGRICOLAS",), "Aquisição de insumos"),
            ProductTemplate("Defensivo agricola", "LT", "38089199", "5101", 5, 60, "95.00", "420.00", ("INSUMOS AGRICOLAS",), "Aquisição de insumos"),
            ProductTemplate("Semente de milho", "SC", "10051000", "5101", 10, 120, "90.00", "210.00", ("INSUMOS AGRICOLAS",), "Aquisição de insumos"),
            ProductTemplate("Racao animal", "KG", "23099090", "5102", 100, 1200, "2.10", "5.80", ("SERVICOS OPERACIONAIS",), "Venda de mercadoria"),
            ProductTemplate("Equipamento de protecao", "UN", "62113300", "5102", 2, 40, "35.00", "280.00", ("SEGUROS E PROTECAO", "RECURSOS HUMANOS"), "Compra para uso e consumo"),
            ProductTemplate("Conta de energia", "UN", "27160000", "5258", 1, 1, "450.00", "5800.00", ("INFRAESTRUTURA E UTILIDADES",), "Despesa administrativa"),
            ProductTemplate("Conta de agua", "UN", "22019000", "5258", 1, 1, "120.00", "1600.00", ("INFRAESTRUTURA E UTILIDADES",), "Despesa administrativa"),
            ProductTemplate("Software de gestao", "UN", "85234910", "5933", 1, 4, "280.00", "1800.00", ("ADMINISTRATIVAS", "INVESTIMENTOS"), "Prestacao de servico"),
            ProductTemplate("Seguro patrimonial", "UN", "99710100", "5949", 1, 2, "600.00", "4500.00", ("SEGUROS E PROTECAO",), "Prestacao de servico"),
            ProductTemplate("Taxa de licenciamento", "UN", "00000000", "5949", 1, 3, "180.00", "1200.00", ("IMPOSTOS E TAXAS",), "Despesa administrativa"),
            ProductTemplate("Trator implemento agricola", "UN", "87019090", "5102", 1, 2, "18000.00", "85000.00", ("INVESTIMENTOS",), "Venda de mercadoria"),
        ]
