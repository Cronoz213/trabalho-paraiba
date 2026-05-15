from django.contrib import admin

from .models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


class ActivableAdmin(admin.ModelAdmin):
    actions = ("inativar_registros", "reativar_registros")

    def get_queryset(self, request):
        if hasattr(self.model, "all_objects"):
            return self.model.all_objects.all()
        return super().get_queryset(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="Inativar registros selecionados")
    def inativar_registros(self, request, queryset):
        queryset.update(ativo=False)

    @admin.action(description="Reativar registros selecionados")
    def reativar_registros(self, request, queryset):
        queryset.update(ativo=True)


@admin.register(InvoiceExtraction)
class InvoiceExtractionAdmin(admin.ModelAdmin):
    list_display = ("file_name", "status", "provider", "created_at")
    list_filter = ("status", "provider", "created_at")
    search_fields = ("file_name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Pessoa)
class PessoaAdmin(ActivableAdmin):
    list_display = ("id", "razao_social", "tipo", "documento", "cidade", "uf", "ativo")
    list_filter = ("tipo", "uf", "ativo")
    search_fields = ("razao_social", "documento")


@admin.register(Classificacao)
class ClassificacaoAdmin(ActivableAdmin):
    list_display = ("id", "descricao", "tipo", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("descricao",)


@admin.register(MovimentoContas)
class MovimentoContasAdmin(ActivableAdmin):
    list_display = ("id", "tipo", "fornecedor", "faturado", "classificacao", "valor_total", "ativo", "created_at")
    list_filter = ("tipo", "ativo", "created_at")
    search_fields = ("numero_nota_fiscal", "fornecedor__razao_social", "faturado__razao_social")
    filter_horizontal = ("classificacoes",)


@admin.register(ParcelaContas)
class ParcelaContasAdmin(ActivableAdmin):
    list_display = ("id", "identificacao", "movimento", "numero_parcela", "valor", "data_vencimento", "ativo")
    search_fields = ("identificacao",)
