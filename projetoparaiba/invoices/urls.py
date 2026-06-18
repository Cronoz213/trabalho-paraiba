from django.urls import path

from . import views

app_name = "invoices"

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),

    # ── Existing ──────────────────────────────────────────────────────────────
    path("", views.index, name="index"),
    path("api/invoices/extract/", views.extract_invoice, name="extract_invoice"),
    path("api/rag/query/", views.query_database_rag, name="query_database_rag"),

    # ── Pages ─────────────────────────────────────────────────────────────────
    path("pessoas/<str:tipo>/", views.pessoas_page, name="pessoas"),
    path("classificacao/<str:tipo>/", views.classificacao_page, name="classificacao"),
    path("contas/", views.contas_page, name="contas"),

    # ── Pessoas API ───────────────────────────────────────────────────────────
    path("api/pessoas/", views.api_pessoas, name="api_pessoas"),
    path("api/pessoas/<int:pk>/", views.api_pessoa, name="api_pessoa"),

    # ── Classificacao API ─────────────────────────────────────────────────────
    path("api/classificacoes/", views.api_classificacoes, name="api_classificacoes"),
    path("api/classificacoes/<int:pk>/", views.api_classificacao_item, name="api_classificacao_item"),

    # ── Contas API ────────────────────────────────────────────────────────────
    path("api/contas/", views.api_contas, name="api_contas"),
    path("api/contas/<int:pk>/", views.api_conta, name="api_conta"),

    # ── Options (selects) ─────────────────────────────────────────────────────
    path("api/options/", views.api_options, name="api_options"),
]
