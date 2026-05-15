from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(ativo=True)

    def inactive(self):
        return self.filter(ativo=False)

    def delete(self):
        return super().update(ativo=False)

    def hard_delete(self):
        return super().delete()

    def reactivate(self):
        return super().update(ativo=True)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return ActiveQuerySet(self.model, using=self._db).filter(ativo=True)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return ActiveQuerySet(self.model, using=self._db)


class ActivableModel(models.Model):
    ativo = models.BooleanField(default=True, db_index=True)

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.ativo = False
        self.save(update_fields=["ativo"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def reactivate(self):
        if not self.ativo:
            self.ativo = True
            self.save(update_fields=["ativo"])

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields != ["ativo"] and update_fields != {"ativo"}:
            self.full_clean()
        return super().save(*args, **kwargs)


class InvoiceExtraction(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Sucesso"
        ERROR = "error", "Erro"

    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=32, default="mock")
    status = models.CharField(max_length=16, choices=Status.choices)
    result_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.file_name} ({self.status})"


class Pessoa(ActivableModel):
    class Tipo(models.TextChoices):
        CLIENTE_FORNECEDOR = "CLIENTE-FORNECEDOR", "Cliente-Fornecedor"
        FORNECEDOR = "FORNECEDOR", "Fornecedor"
        CLIENTE = "CLIENTE", "Cliente"
        FATURADO = "FATURADO", "Faturado"

    tipo = models.CharField(max_length=32, choices=Tipo.choices)
    razao_social = models.CharField(max_length=255)
    documento = models.CharField(max_length=32, blank=True, db_index=True)
    inscricao_estadual = models.CharField(max_length=32, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PESSOAS"
        ordering = ["razao_social", "id"]

    def __str__(self) -> str:
        return f"{self.razao_social} ({self.tipo})"

    def clean(self):
        tipos_consulta = [self.tipo]
        if self.tipo in {self.Tipo.CLIENTE_FORNECEDOR, self.Tipo.FORNECEDOR}:
            tipos_consulta = [self.Tipo.CLIENTE_FORNECEDOR, self.Tipo.FORNECEDOR]

        conflito = Pessoa.all_objects.filter(tipo__in=tipos_consulta, ativo=True)
        if self.pk:
            conflito = conflito.exclude(pk=self.pk)

        documento = self.documento.strip()
        if documento and conflito.filter(documento=documento).exists():
            raise ValidationError({"documento": "Ja existe uma pessoa ativa cadastrada com este documento."})

        razao_social = self.razao_social.strip()
        if razao_social and conflito.filter(razao_social__iexact=razao_social).exists():
            raise ValidationError({"razao_social": "Ja existe uma pessoa ativa cadastrada com esta razao social."})


class Classificacao(ActivableModel):
    class Tipo(models.TextChoices):
        DESPESA = "DESPESA", "Despesa"
        RECEITA = "RECEITA", "Receita"

    tipo = models.CharField(max_length=32, choices=Tipo.choices)
    descricao = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "CLASSIFICACAO"
        ordering = ["descricao", "id"]

    def __str__(self) -> str:
        return f"{self.descricao} ({self.tipo})"

    def clean(self):
        conflito = Classificacao.all_objects.filter(tipo=self.tipo, descricao__iexact=self.descricao.strip(), ativo=True)
        if self.pk:
            conflito = conflito.exclude(pk=self.pk)
        if conflito.exists():
            raise ValidationError({"descricao": "Ja existe uma classificacao ativa com esta descricao para este tipo."})


class MovimentoContas(ActivableModel):
    class Tipo(models.TextChoices):
        APAGAR = "APAGAR", "A Pagar"
        ARECEBER = "ARECEBER", "A Receber"

    tipo = models.CharField(max_length=16, choices=Tipo.choices, default=Tipo.APAGAR)
    fornecedor = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="movimentos_fornecedor")
    faturado = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="movimentos_faturado")
    classificacao = models.ForeignKey(Classificacao, on_delete=models.PROTECT, related_name="movimentos")
    classificacoes = models.ManyToManyField(Classificacao, related_name="movimentos_vinculados", blank=True)
    invoice_extraction = models.ForeignKey(InvoiceExtraction, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentos")
    numero_nota_fiscal = models.CharField(max_length=64, blank=True)
    serie = models.CharField(max_length=32, blank=True)
    data_emissao = models.CharField(max_length=32, blank=True)
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "MOVIMENTOCONTAS"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Movimento {self.id} - {self.tipo}"


class ParcelaContas(ActivableModel):
    movimento = models.ForeignKey(MovimentoContas, on_delete=models.CASCADE, related_name="parcelas")
    identificacao = models.CharField(max_length=64, unique=True)
    numero_parcela = models.PositiveIntegerField(default=1)
    data_vencimento = models.CharField(max_length=32, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PARCELACONTAS"
        ordering = ["movimento_id", "numero_parcela", "id"]

    def __str__(self) -> str:
        return self.identificacao

    def clean(self):
        if not self.movimento_id or not self.data_vencimento:
            return

        conflito = ParcelaContas.all_objects.filter(
            movimento_id=self.movimento_id,
            data_vencimento=self.data_vencimento,
            ativo=True,
        )
        if self.pk:
            conflito = conflito.exclude(pk=self.pk)
        if conflito.exists():
            raise ValidationError({"data_vencimento": "Cada parcela ativa do movimento deve possuir data de vencimento distinta."})
