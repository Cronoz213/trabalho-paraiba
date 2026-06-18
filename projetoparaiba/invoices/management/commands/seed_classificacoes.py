from __future__ import annotations

from django.core.management.base import BaseCommand

from invoices.models import Classificacao


RECEITAS = [
    "VENDA DE PRODUTOS AGRICOLAS",
    "PRESTACAO DE SERVICOS",
    "RECEITA DE ARRENDAMENTO",
    "VENDA DE ANIMAIS",
    "SUBVENCOES E INCENTIVOS",
    "OUTRAS RECEITAS OPERACIONAIS",
]

DESPESAS = [
    "INSUMOS AGRICOLAS",
    "MANUTENCAO E OPERACAO",
    "RECURSOS HUMANOS",
    "SERVICOS OPERACIONAIS",
    "INFRAESTRUTURA E UTILIDADES",
    "ADMINISTRATIVAS",
    "SEGUROS E PROTECAO",
    "IMPOSTOS E TAXAS",
    "INVESTIMENTOS",
]


class Command(BaseCommand):
    help = "Garante que todas as classificacoes padrao (DESPESA e RECEITA) existem no banco."

    def handle(self, *args, **options):
        criadas = 0
        for descricao in DESPESAS:
            _, created = Classificacao.all_objects.get_or_create(
                tipo=Classificacao.Tipo.DESPESA,
                descricao=descricao,
                defaults={"ativo": True},
            )
            if created:
                criadas += 1

        for descricao in RECEITAS:
            _, created = Classificacao.all_objects.get_or_create(
                tipo=Classificacao.Tipo.RECEITA,
                descricao=descricao,
                defaults={"ativo": True},
            )
            if created:
                criadas += 1

        self.stdout.write(self.style.SUCCESS(f"{criadas} classificacao(oes) criada(s)."))
