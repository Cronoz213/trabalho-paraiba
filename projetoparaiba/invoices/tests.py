from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from invoices.agents.extraction import ExtractionResult
from invoices.agents import ExpenseClassificationAgent, ValidationAgent
from invoices.agents.extraction import PdfExtractionAgent
from invoices.services import InvoiceExtractionService
from invoices.models import Classificacao, InvoiceExtraction, MovimentoContas, ParcelaContas, Pessoa


MINIMUM_CONTRACT_FIELDS = (
    "fornecedor",
    "faturado",
    "numero_nota_fiscal",
    "data_emissao",
    "produtos",
    "parcelas",
    "valor_total",
    "classificacoes_despesa",
)

FORNECEDOR_REQUIRED_FIELDS = ("razao_social", "fantasia", "cnpj")
FATURADO_REQUIRED_FIELDS = ("nome_completo", "cpf")
PRODUTO_REQUIRED_FIELDS = ("descricao", "quantidade")
PARCELA_REQUIRED_FIELDS = ("numero", "data_vencimento", "valor")
CLASSIFICACAO_REQUIRED_FIELDS = ("categoria", "justificativa")


@override_settings(GEMINI_API_KEY="")
class InvoiceExtractApiTests(TestCase):
    def post_pdf(self, text: str, *, filename: str = "nota_fiscal.pdf") -> dict:
        uploaded_pdf = SimpleUploadedFile(filename, b"%PDF-1.4 mock", content_type="application/pdf")
        with patch("invoices.agents.extraction.PdfExtractionAgent._read_pdf_text", return_value=text):
            response = self.client.post(reverse("invoices:extract_invoice"), {"pdf": uploaded_pdf})
        return response

    def test_extract_without_file_returns_error(self) -> None:
        response = self.client.post(reverse("invoices:extract_invoice"))

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "Arquivo PDF é obrigatório.")
        self.assertIn("Envie o campo 'pdf'", payload["detail"])

    def test_extract_with_non_pdf_file_returns_error(self) -> None:
        response = self.client.post(
            reverse("invoices:extract_invoice"),
            {"pdf": SimpleUploadedFile("nota.txt", b"nao e pdf", content_type="text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "Formato do arquivo inválido.")

    def test_extract_valid_pdf_uses_mock_and_returns_minimum_contract(self) -> None:
        response = self.post_pdf("Compra de Oleo Diesel S10")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "mock")
        data = payload["data"]
        self.assertEqual(payload["provider"], "mock")

        for field in MINIMUM_CONTRACT_FIELDS:
            self.assertIn(field, data)
        self.assertTrue(data["produtos"])
        self.assertTrue(data["parcelas"])
        self.assertTrue(data["classificacoes_despesa"])

        self.assertIsInstance(data["fornecedor"], dict)
        self.assertIsInstance(data["faturado"], dict)
        self.assertIsInstance(data["produtos"], list)
        self.assertIsInstance(data["parcelas"], list)
        self.assertIsInstance(data["classificacoes_despesa"], list)
        self.assertIsInstance(data["valor_total"], (int, float))
        self.assertEqual(data["classificacoes_despesa"][0]["categoria"], "MANUTENCAO E OPERACAO")

    def test_extract_returns_required_contract_fields(self) -> None:
        response = self.post_pdf("Compra de Oleo Diesel S10")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIn("id", payload)
        self.assertIn("provider", payload)
        self.assertIn("data", payload)
        self.assertIsInstance(payload["id"], int)

        data = payload["data"]
        fornecedor = data["fornecedor"]
        faturado = data["faturado"]

        self.assertIsInstance(data, dict)
        self.assertIsInstance(fornecedor, dict)
        self.assertIsInstance(faturado, dict)
        self.assertIsInstance(data["produtos"], list)
        self.assertIsInstance(data["parcelas"], list)
        self.assertIsInstance(data["classificacoes_despesa"], list)
        self.assertTrue(data["produtos"])
        self.assertTrue(data["parcelas"])
        self.assertTrue(data["classificacoes_despesa"])

        for field in MINIMUM_CONTRACT_FIELDS:
            self.assertIn(field, data)

        for field in FORNECEDOR_REQUIRED_FIELDS:
            self.assertIn(field, fornecedor)
            self.assertIsInstance(fornecedor[field], str)

        for field in FATURADO_REQUIRED_FIELDS:
            self.assertIn(field, faturado)
            self.assertIsInstance(faturado[field], str)

        for field in PRODUTO_REQUIRED_FIELDS:
            for product in data["produtos"]:
                self.assertIn(field, product)

        for field in PARCELA_REQUIRED_FIELDS:
            for parcela in data["parcelas"]:
                self.assertIn(field, parcela)

        for field in CLASSIFICACAO_REQUIRED_FIELDS:
            for classificacao in data["classificacoes_despesa"]:
                self.assertIn(field, classificacao)

    def test_extract_valid_pdf_classifies_hydraulic_material(self) -> None:
        response = self.post_pdf("Material hidrÃ¡ulico para tubulaÃ§Ã£o")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["provider"], "mock")
        self.assertEqual(payload["data"]["classificacoes_despesa"][0]["categoria"], "INFRAESTRUTURA E UTILIDADES")

    def test_successful_extraction_is_persisted(self) -> None:
        before_count = InvoiceExtraction.objects.count()
        response = self.post_pdf("Compra de Ã³leo diesel para o trator")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(InvoiceExtraction.objects.count(), before_count + 1)

        record = InvoiceExtraction.objects.order_by("-id").first()
        self.assertIsNotNone(record)
        self.assertEqual(record.file_name, "nota_fiscal.pdf")
        self.assertEqual(record.status, InvoiceExtraction.Status.SUCCESS)
        self.assertEqual(record.provider, "mock")
        self.assertEqual(record.result_json, payload["data"])

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("invoices.agents.extraction.PdfExtractionAgent._extract_with_gemini", side_effect=RuntimeError("indisponivel"))
    def test_extract_with_gemini_key_set_still_uses_mock_fallback(self, _mock_gemini_extract) -> None:
        response = self.post_pdf("Compra de filtro hidrÃ¡ulico")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["provider"], "mock")
        self.assertIn("fallback_reason", payload)
        self.assertIn("Falha ao usar Gemini", payload["fallback_reason"])

    def test_api_returns_success_id_provider_and_data(self) -> None:
        response = self.post_pdf("Compra de Ã³leo diesel")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("success", payload)
        self.assertIn("id", payload)
        self.assertIn("provider", payload)
        self.assertIn("data", payload)
        self.assertTrue(payload["success"])
        self.assertIsInstance(payload["id"], int)

    @patch("invoices.services.PdfExtractionAgent.extract", side_effect=ValueError("Nao foi possivel extrair texto do PDF enviado."))
    def test_extract_pdf_without_readable_text_returns_400(self, _mock_read) -> None:
        response = self.client.post(
            reverse("invoices:extract_invoice"),
            {"pdf": SimpleUploadedFile("nota_vazia.pdf", b"%PDF-1.4 mock", content_type="application/pdf")},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "Falha ao extrair dados do PDF.")
        self.assertEqual(payload["detail"], "Nao foi possivel extrair texto do PDF enviado.")

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDORA MOCK",
                    "fantasia": "FORN MOCK",
                    "cnpj": "11.111.111/0001-11",
                },
                "faturado": {"nome_completo": "CLIENTE MOCK", "cpf": "222.222.222-22"},
                "numero_nota_fiscal": "999",
                "data_emissao": "2024-01-01",
                "produtos": [{"descricao": "Item administrativo sem regra", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                "valor_total": 100.0,
                "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "forca-bruta"}],
            },
            provider="gemini",
        ),
    )
    def test_classification_from_gemini_official_category_is_preserved(self, _mock_extract) -> None:
        response = self.post_pdf("Texto genÃ©rico nÃ£o confiÃ¡vel")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        classifications = payload["data"]["classificacoes_despesa"]
        self.assertEqual(classifications[0]["categoria"], "MANUTENCAO E OPERACAO")
        self.assertEqual(classifications[0]["justificativa"], "forca-bruta")

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDORA MOCK",
                    "fantasia": "FORN MOCK",
                    "cnpj": "11.111.111/0001-11",
                },
                "faturado": {"nome_completo": "CLIENTE MOCK", "cpf": "222.222.222-22"},
                "numero_nota_fiscal": "999",
                "data_emissao": "2024-01-01",
                "produtos": [{"descricao": "Item de escritÃ³rios sem categoria conhecida", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                "valor_total": 100.0,
                "classificacoes_despesa": [{"categoria": "CATEGORIA INESPERADA", "justificativa": "forca-bruta"}],
            },
            provider="gemini",
        ),
    )
    def test_classification_falls_back_to_local_rules_when_gemini_category_is_unknown(self, _mock_extract) -> None:
        response = self.post_pdf("Texto genÃ©rico nÃ£o confiÃ¡vel")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        classifications = payload["data"]["classificacoes_despesa"]
        self.assertEqual(classifications[0]["categoria"], "ADMINISTRATIVAS")
        self.assertEqual(classifications[0]["justificativa"], "Nao foi possivel identificar um padrao de categoria conhecido para os produtos informados.")
        self.assertNotEqual(classifications[0]["categoria"], "CATEGORIA INESPERADA")


class InvoiceExtractionServiceTests(TestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_extract_uses_mock_without_gemini_key(self) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch("invoices.services.PdfExtractionAgent._read_pdf_text", return_value="Nota Fiscal: Oleo Diesel S10"):
            payload = service.extract(file)

        self.assertEqual(payload["provider"], "mock")
        self.assertEqual(payload["fallback_reason"], "GEMINI_API_KEY nao foi configurada.")
        self.assertEqual(payload["data"]["classificacoes_despesa"][0]["categoria"], "MANUTENCAO E OPERACAO")
        self.assertEqual(payload["success"], True)

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDORA GEMINI",
                    "fantasia": "FORNECEDORA",
                    "cnpj": "22.222.222/0002-22",
                },
                "faturado": {"nome_completo": "CLIENTE GEMINI", "cpf": "333.333.333-33"},
                "numero_nota_fiscal": "777",
                "data_emissao": "2024-01-01",
                "produtos": [{"descricao": "Material sem regra", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                "valor_total": 100.0,
                "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "ClassificaÃ§Ã£o oficial do Gemini."}],
            },
            provider="gemini",
        ),
    )
    @override_settings(GEMINI_API_KEY="test-key")
    def test_preserve_official_gemini_category(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch("invoices.services.ExpenseClassificationAgent.classify", side_effect=AssertionError("Fallback nÃ£o deve ser chamado")):
            payload = service.extract(file)

        self.assertEqual(payload["provider"], "gemini")
        self.assertEqual(payload["data"]["classificacoes_despesa"][0]["categoria"], "MANUTENCAO E OPERACAO")
        self.assertEqual(payload["data"]["classificacoes_despesa"][0]["justificativa"], "ClassificaÃ§Ã£o oficial do Gemini.")

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDORA GEMINI",
                    "fantasia": "FORNECEDORA",
                    "cnpj": "22.222.222/0002-22",
                },
                "faturado": {"nome_completo": "CLIENTE GEMINI", "cpf": "333.333.333-33"},
                "numero_nota_fiscal": "777",
                "data_emissao": "2024-01-01",
                "produtos": [{"descricao": "Material sem regra", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                "valor_total": 100.0,
                "classificacoes_despesa": [{"categoria": "CATEGORIA INESPERADA", "justificativa": "Sem padrÃ£o conhecido."}],
            },
            provider="gemini",
        ),
    )
    @override_settings(GEMINI_API_KEY="test-key")
    def test_unknown_gemini_category_falls_back_to_local_rules(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        payload = service.extract(file)

        self.assertEqual(payload["provider"], "gemini")
        self.assertEqual(payload["data"]["classificacoes_despesa"][0]["categoria"], "ADMINISTRATIVAS")
        self.assertEqual(
            payload["data"]["classificacoes_despesa"][0]["justificativa"],
            "Nao foi possivel identificar um padrao de categoria conhecido para os produtos informados.",
        )

    def test_service_orchestrates_agents_in_pptx_cycle(self) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        steps: list[str] = []

        original_normalize = service.validation_agent.normalize
        original_classify = service.classification_agent.classify
        original_save_success = service.persistence_agent.save_success

        def fake_extract(uploaded_file) -> ExtractionResult:
            steps.append("PdfExtractionAgent.extract")
            return ExtractionResult(
                data={
                    "fornecedor": {"razao_social": "FORN", "fantasia": "FORN", "cnpj": "11.111.111/0001-11"},
                    "faturado": {"nome_completo": "CLIENTE", "cpf": "222.222.222-22"},
                    "numero_nota_fiscal": "111",
                    "data_emissao": "2024-01-01",
                    "produtos": [{"descricao": "Material sem regra conhecida", "quantidade": 1}],
                    "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                    "valor_total": 100.0,
                    "classificacoes_despesa": [{"categoria": "CATEGORIA INVISIVEL", "justificativa": "forca-bruta"}],
                },
                provider="gemini",
            )

        def fake_normalize(data):
            steps.append("ValidationAgent.normalize")
            return original_normalize(data)

        def fake_classify(products):
            steps.append("ExpenseClassificationAgent.classify")
            return original_classify(products)

        def fake_save_success(uploaded_file, data, provider):
            steps.append("PersistenceAgent.save_success")
            return original_save_success(uploaded_file, data, provider)

        with patch.object(service.pdf_agent, "extract", side_effect=fake_extract), \
            patch.object(service.validation_agent, "normalize", side_effect=fake_normalize), \
            patch.object(service.classification_agent, "classify", side_effect=fake_classify), \
            patch.object(service.persistence_agent, "save_success", side_effect=fake_save_success):
            payload = service.extract(file)

        self.assertTrue(payload["success"])
        self.assertIsInstance(payload["id"], int)
        self.assertEqual(payload["provider"], "gemini")
        self.assertEqual(
            steps,
            [
                "PdfExtractionAgent.extract",
                "ValidationAgent.normalize",
                "ExpenseClassificationAgent.classify",
                "ValidationAgent.normalize",
                "PersistenceAgent.save_success",
            ],
        )


class PdfExtractionAgentTests(TestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_extract_without_gemini_key_uses_mock_with_missing_key_reason(self) -> None:
        agent = PdfExtractionAgent()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch.object(agent, "_read_pdf_text", return_value="Nota Fiscal: Oleo Diesel S10"):
            result = agent.extract(file)

        self.assertEqual(result.provider, "mock")
        self.assertEqual(result.fallback_reason, "GEMINI_API_KEY nao foi configurada.")
        self.assertIn("fornecedor", result.data)

    @override_settings(GEMINI_API_KEY="test-key")
    def test_extract_with_gemini_key_and_valid_json_uses_gemini_without_fallback_reason(self) -> None:
        agent = PdfExtractionAgent()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        gemini_data = {
            "fornecedor": {"razao_social": "FORNECEDORA GEMINI", "fantasia": "FORNECEDORA", "cnpj": "22.222.222/0002-22"},
            "faturado": {"nome_completo": "CLIENTE GEMINI", "cpf": "333.333.333-33"},
            "numero_nota_fiscal": "777",
            "data_emissao": "2024-01-01",
            "produtos": [{"descricao": "Material sem regra", "quantidade": 1}],
            "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
            "valor_total": 100.0,
            "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Classificacao oficial."}],
        }

        with patch.object(agent, "_read_pdf_text", return_value="Nota Fiscal Gemini"), \
            patch.object(agent, "_extract_with_gemini", return_value=gemini_data) as mock_gemini:
            result = agent.extract(file)

        mock_gemini.assert_called_once_with("Nota Fiscal Gemini")
        self.assertEqual(result.provider, "gemini")
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.data, gemini_data)

    @override_settings(GEMINI_API_KEY="test-key")
    def test_extract_with_gemini_failure_uses_mock_with_safe_fallback_reason(self) -> None:
        agent = PdfExtractionAgent()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch.object(agent, "_read_pdf_text", return_value="Nota Fiscal: filtro hidraulico"), \
            patch.object(agent, "_extract_with_gemini", side_effect=RuntimeError("modelo indisponivel para test-key")):
            result = agent.extract(file)

        self.assertEqual(result.provider, "mock")
        self.assertIsNotNone(result.fallback_reason)
        self.assertIn("Falha ao usar Gemini", result.fallback_reason)
        self.assertIn("modelo indisponivel", result.fallback_reason)
        self.assertNotIn("test-key", result.fallback_reason)
        self.assertIn("fornecedor", result.data)

    def test_read_real_pdf_with_pypdf(self) -> None:
        pdf_path = Path(r"C:\Users\pmgam\Downloads\danfe (beltrano - insumos).pdf")
        if not pdf_path.exists():
            self.skipTest("Arquivo local ausente. Consulte README para validaÃ§Ã£o manual com esse PDF.")

        with pdf_path.open("rb") as file:
            uploaded_pdf = SimpleUploadedFile("danfe (beltrano - insumos).pdf", file.read(), content_type="application/pdf")

        agent = PdfExtractionAgent()
        extracted_text = agent._read_pdf_text(uploaded_pdf)
        self.assertTrue(extracted_text)
        self.assertIsInstance(extracted_text, str)
        self.assertGreater(len(extracted_text.strip()), 0)

    def test_gemini_prompt_targets_danfe_and_official_categories(self) -> None:
        agent = PdfExtractionAgent()
        prompt = agent._prompt("Documento de teste DANFE com produtos de insumos agrÃ­colas")

        self.assertIn("DANFE/NF-e", prompt)
        self.assertIn("fornecedor", prompt)
        self.assertIn("faturado", prompt)
        self.assertIn("numero_nota_fiscal", prompt)
        self.assertIn("classificacoes_despesa", prompt)
        self.assertIn("duplicatas", prompt)
        self.assertIn("INSUMOS AGRICOLAS", prompt)
        self.assertIn("classifique", prompt.lower())
        self.assertIn("somente json", prompt.lower())


class ExpenseClassificationAgentTests(TestCase):
    def setUp(self) -> None:
        self.classifier = ExpenseClassificationAgent()

    def test_classifies_oil_diesel(self) -> None:
        result = self.classifier.classify([{"descricao": "Oleo Diesel S10"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["categoria"], "MANUTENCAO E OPERACAO")
        self.assertIn("Produto relacionado", result[0]["justificativa"])

    def test_classifies_hydraulic_material(self) -> None:
        result = self.classifier.classify([{"descricao": "Material hidraulico para tubulacao"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["categoria"], "INFRAESTRUTURA E UTILIDADES")
        self.assertIn("Produto relacionado", result[0]["justificativa"])

    def test_classifies_fungicida_as_insumos_agricolas(self) -> None:
        result = self.classifier.classify([{"descricao": "VESSARYA BOMBONA 10L FUNGICIDA"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["categoria"], "INSUMOS AGRICOLAS")
        self.assertIn("fungicida", result[0]["justificativa"])

    def test_classifies_agrotecnicos_products_as_insumos_agricolas(self) -> None:
        for term in [
            "herbicida",
            "inseticida",
            "pesticida",
            "defensivo agricola",
            "defensivo agrÃ­cola",
            "fertilizante",
            "adubo",
            "sementes",
        ]:
            with self.subTest(term=term):
                result = self.classifier.classify([{"descricao": f"{term} concentrado"}])
                self.assertEqual(result[0]["categoria"], "INSUMOS AGRICOLAS")


class ValidationAgentTests(TestCase):
    def setUp(self) -> None:
        self.validator = ValidationAgent()

    def test_validation_normalizes_minimum_contract_shape(self) -> None:
        normalized = self.validator.normalize(
            {
                "fornecedor": {"razao_social": "Fornecedor", "fantasia": "Fantasia", "cnpj": "00.000.000/0001-00"},
                "faturado": {"nome": "Cliente Exemplo", "cpf": "123.456.789-00"},
                "numero": "123",
                "dataEmissao": "2024-01-01",
                "itens": [{"item": "PeÃ§as de manutenÃ§Ã£o", "qtd": 2}],
                "parcelas": {"parcela": 1, "vencimento": "2024-01-30", "valor_total": 100},
                "valorTotal": "100.50",
                "tipoDespesa": "MANUTENCAO E OPERACAO",
            }
        )

        self.assertEqual(normalized["numero_nota_fiscal"], "123")
        self.assertEqual(normalized["data_emissao"], "2024-01-01")
        self.assertEqual(normalized["produtos"][0]["descricao"], "PeÃ§as de manutenÃ§Ã£o")
        self.assertIsInstance(normalized["produtos"], list)
        self.assertIsInstance(normalized["parcelas"], list)
        self.assertIsInstance(normalized["classificacoes_despesa"], list)
        self.assertEqual(normalized["classificacoes_despesa"][0]["categoria"], "MANUTENCAO E OPERACAO")

    def test_validation_rejects_invalid_classification_shape(self) -> None:
        invalid_data = {
            "fornecedor": {"razao_social": "Fornecedor", "fantasia": "Fantasia", "cnpj": "00.000.000/0001-00"},
            "faturado": {"nome_completo": "Cliente", "cpf": "123.456.789-00"},
            "numero_nota_fiscal": "123",
            "data_emissao": "2024-01-01",
            "produtos": [{"descricao": "item", "quantidade": 1}],
            "parcelas": [{"numero": 1, "data_vencimento": "2024-01-10", "valor": 10}],
            "valor_total": 10,
            "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO"}],
        }

        with self.assertRaises(ValueError):
            self.validator.validate(invalid_data)

    def test_validation_preserves_important_invoice_details(self) -> None:
        normalized = self.validator.normalize(
            {
                "fornecedor": {
                    "razao_social": "Fornecedor",
                    "fantasia": "Fantasia",
                    "cnpj": "00.000.000/0001-00",
                    "ie": "12345",
                    "endereco": "Rua A",
                    "municipio": "Campina Grande",
                    "uf": "PB",
                },
                "faturado": {
                    "nome_completo": "Cliente",
                    "cpf": "123.456.789-00",
                    "cnpj": "11.111.111/0001-11",
                    "logradouro": "Rua B",
                    "cidade": "Joao Pessoa",
                    "estado": "PB",
                },
                "numero_nota_fiscal": "123",
                "data_emissao": "2024-01-01",
                "serie": "1",
                "chaveAcesso": "ABC123",
                "naturezaOperacao": "Venda",
                "produtos": [
                    {
                        "descricao": "Produto X",
                        "quantidade": 2,
                        "unidade": "UN",
                        "valor_unitario": 10,
                        "valor_total": 20,
                        "ncm": "1234",
                        "cfop": "5102",
                    }
                ],
                "parcelas": [
                    {
                        "numero": 1,
                        "data_vencimento": "2024-02-01",
                        "valor": 20,
                        "forma_pagamento": "Pix",
                    }
                ],
                "valor_produtos": 20,
                "valor_desconto": 1,
                "valor_frete": 2,
                "valor_icms": 3,
                "valor_ipi": 4,
                "valor_total": 25,
                "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
            }
        )

        self.assertEqual(normalized["fornecedor"]["inscricao_estadual"], "12345")
        self.assertEqual(normalized["faturado"]["cnpj"], "11.111.111/0001-11")
        self.assertEqual(normalized["serie"], "1")
        self.assertEqual(normalized["chave_acesso"], "ABC123")
        self.assertEqual(normalized["natureza_operacao"], "Venda")
        self.assertEqual(normalized["produtos"][0]["unidade"], "UN")
        self.assertEqual(normalized["produtos"][0]["ncm"], "1234")
        self.assertEqual(normalized["parcelas"][0]["forma_pagamento"], "Pix")
        self.assertEqual(normalized["valor_icms"], 3.0)


@override_settings(GEMINI_API_KEY="")
class InvoiceRegistrationStageTwoTests(TestCase):
    def test_api_returns_analysis_message_and_created_records(self) -> None:
        uploaded_pdf = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch("invoices.agents.extraction.PdfExtractionAgent._read_pdf_text", return_value="Compra de Oleo Diesel S10"):
            response = self.client.post(reverse("invoices:extract_invoice"), {"pdf": uploaded_pdf})

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["message"], "Dados criados no banco com sucesso.")
        self.assertEqual(payload["analysis"]["fornecedor"]["acao"], "criado")
        self.assertEqual(payload["analysis"]["faturado"]["acao"], "criado")
        self.assertEqual(payload["analysis"]["despesa"]["acao"], "criado")
        self.assertEqual(payload["analysis"]["movimento"]["tipo"], "APAGAR")
        self.assertFalse(payload["analysis"]["movimento"]["duplicado"])
        self.assertTrue(payload["analysis"]["parcelas"])
        self.assertFalse(payload["analysis"]["historico_fornecedor"]["possui_dados"])
        self.assertEqual(Pessoa.objects.filter(tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR).count(), 1)
        self.assertEqual(Pessoa.objects.filter(tipo=Pessoa.Tipo.FATURADO).count(), 1)
        self.assertEqual(Classificacao.objects.filter(tipo=Classificacao.Tipo.DESPESA).count(), 1)
        self.assertEqual(MovimentoContas.objects.count(), 1)
        self.assertEqual(ParcelaContas.objects.count(), 1)

    def test_service_reuses_existing_supplier_billed_and_expense(self) -> None:
        fornecedor = Pessoa.objects.create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            razao_social="EMPRESA FORNECEDORA LTDA",
            documento="12345678000190",
        )
        faturado = Pessoa.objects.create(
            tipo=Pessoa.Tipo.FATURADO,
            razao_social="CLIENTE EXEMPLO",
            documento="12345678900",
        )
        despesa = Classificacao.objects.create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao="MANUTENCAO E OPERACAO",
        )

        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_fiscal.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with patch("invoices.services.PdfExtractionAgent._read_pdf_text", return_value="Nota Fiscal: Oleo Diesel S10"):
            payload = service.extract(file)

        self.assertEqual(payload["analysis"]["fornecedor"]["id"], fornecedor.id)
        self.assertEqual(payload["analysis"]["faturado"]["id"], faturado.id)
        self.assertEqual(payload["analysis"]["despesa"]["id"], despesa.id)
        self.assertEqual(payload["analysis"]["fornecedor"]["acao"], "reutilizado")
        self.assertEqual(payload["analysis"]["faturado"]["acao"], "reutilizado")
        self.assertEqual(payload["analysis"]["despesa"]["acao"], "reutilizado")
        self.assertEqual(Pessoa.objects.filter(tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR).count(), 1)
        self.assertEqual(Pessoa.objects.filter(tipo=Pessoa.Tipo.FATURADO).count(), 1)
        self.assertEqual(Classificacao.objects.filter(tipo=Classificacao.Tipo.DESPESA).count(), 1)

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        side_effect=[
            ExtractionResult(
                data={
                    "fornecedor": {
                        "razao_social": "FORNECEDORA TESTE",
                        "fantasia": "FORNECEDORA TESTE",
                        "cnpj": "11.111.111/0001-11",
                    },
                    "faturado": {"nome_completo": "CLIENTE TESTE", "cpf": "222.222.222-22"},
                    "numero_nota_fiscal": "1001",
                    "serie": "1",
                    "data_emissao": "2024-01-01",
                    "produtos": [{"descricao": "Oleo Diesel S10", "quantidade": 1}],
                    "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                    "valor_total": 100.0,
                    "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
                },
                provider="mock",
            ),
            ExtractionResult(
                data={
                    "fornecedor": {
                        "razao_social": "FORNECEDORA TESTE",
                        "fantasia": "FORNECEDORA TESTE",
                        "cnpj": "11.111.111/0001-11",
                    },
                    "faturado": {"nome_completo": "CLIENTE TESTE", "cpf": "222.222.222-22"},
                    "numero_nota_fiscal": "1001",
                    "serie": "1",
                    "data_emissao": "2024-01-01",
                    "produtos": [{"descricao": "Oleo Diesel S10", "quantidade": 1}],
                    "parcelas": [{"numero": 1, "data_vencimento": "2024-02-01", "valor": 100.0}],
                    "valor_total": 100.0,
                    "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
                },
                provider="mock",
            ),
        ],
    )
    def test_duplicate_invoice_is_not_created_twice(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file_one = SimpleUploadedFile("nota_1.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        file_two = SimpleUploadedFile("nota_2.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        first_payload = service.extract(file_one)
        second_payload = service.extract(file_two)

        self.assertEqual(first_payload["message"], "Dados criados no banco com sucesso.")
        self.assertEqual(second_payload["message"], "Upload dessa nota ja foi realizado anteriormente.")
        self.assertTrue(second_payload["analysis"]["movimento"]["duplicado"])
        self.assertEqual(MovimentoContas.objects.count(), 1)
        self.assertEqual(ParcelaContas.objects.count(), 1)
        self.assertEqual(second_payload["analysis"]["historico_fornecedor"]["quantidade"], 1)

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        side_effect=[
            ExtractionResult(
                data={
                    "fornecedor": {
                        "razao_social": "FORNECEDORA HISTORICO",
                        "fantasia": "FORNECEDORA HISTORICO",
                        "cnpj": "33.333.333/0001-33",
                    },
                    "faturado": {"nome_completo": "CLIENTE HISTORICO", "cpf": "444.444.444-44"},
                    "numero_nota_fiscal": "2001",
                    "serie": "1",
                    "data_emissao": "2024-03-01",
                    "produtos": [{"descricao": "Oleo Diesel S10", "quantidade": 1}],
                    "parcelas": [{"numero": 1, "data_vencimento": "2024-04-01", "valor": 150.0}],
                    "valor_total": 150.0,
                    "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
                },
                provider="mock",
            ),
            ExtractionResult(
                data={
                    "fornecedor": {
                        "razao_social": "FORNECEDORA HISTORICO",
                        "fantasia": "FORNECEDORA HISTORICO",
                        "cnpj": "33.333.333/0001-33",
                    },
                    "faturado": {"nome_completo": "CLIENTE HISTORICO", "cpf": "444.444.444-44"},
                    "numero_nota_fiscal": "2002",
                    "serie": "1",
                    "data_emissao": "2024-03-15",
                    "produtos": [{"descricao": "Peca de manutencao", "quantidade": 2}],
                    "parcelas": [{"numero": 1, "data_vencimento": "2024-04-15", "valor": 275.0}],
                    "valor_total": 275.0,
                    "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
                },
                provider="mock",
            ),
        ],
    )
    def test_second_invoice_from_same_supplier_returns_previous_history(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file_one = SimpleUploadedFile("nota_hist_1.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        file_two = SimpleUploadedFile("nota_hist_2.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        service.extract(file_one)
        second_payload = service.extract(file_two)

        self.assertEqual(second_payload["message"], "Dados criados no banco com sucesso.")
        self.assertFalse(second_payload["analysis"]["movimento"]["duplicado"])
        self.assertEqual(second_payload["analysis"]["historico_fornecedor"]["quantidade"], 1)
        history_item = second_payload["analysis"]["historico_fornecedor"]["itens"][0]
        self.assertEqual(history_item["numero_nota_fiscal"], "2001")
        self.assertEqual(history_item["dados_extraidos"]["numero_nota_fiscal"], "2001")

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDOR INATIVO",
                    "fantasia": "FORNECEDOR INATIVO",
                    "cnpj": "55.555.555/0001-55",
                },
                "faturado": {"nome_completo": "FATURADO INATIVO", "cpf": "555.555.555-55"},
                "numero_nota_fiscal": "3001",
                "serie": "1",
                "data_emissao": "2024-05-01",
                "produtos": [{"descricao": "Produto A", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-06-01", "valor": 90.0}],
                "valor_total": 90.0,
                "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
            },
            provider="mock",
        ),
    )
    def test_inactive_records_are_reactivated_instead_of_duplicated(self, _mock_extract) -> None:
        fornecedor = Pessoa.all_objects.create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            razao_social="FORNECEDOR INATIVO",
            documento="55555555000155",
            ativo=False,
        )
        faturado = Pessoa.all_objects.create(
            tipo=Pessoa.Tipo.FATURADO,
            razao_social="FATURADO INATIVO",
            documento="55555555555",
            ativo=False,
        )
        despesa = Classificacao.all_objects.create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao="MANUTENCAO E OPERACAO",
            ativo=False,
        )

        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_inativa.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        payload = service.extract(file)

        fornecedor.refresh_from_db()
        faturado.refresh_from_db()
        despesa.refresh_from_db()

        self.assertTrue(fornecedor.ativo)
        self.assertTrue(faturado.ativo)
        self.assertTrue(despesa.ativo)
        self.assertEqual(payload["analysis"]["fornecedor"]["id"], fornecedor.id)
        self.assertEqual(payload["analysis"]["faturado"]["id"], faturado.id)
        self.assertEqual(payload["analysis"]["despesa"]["id"], despesa.id)

    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDOR MULTI",
                    "fantasia": "FORNECEDOR MULTI",
                    "cnpj": "66.666.666/0001-66",
                },
                "faturado": {"nome_completo": "FATURADO MULTI", "cpf": "666.666.666-66"},
                "numero_nota_fiscal": "4001",
                "serie": "1",
                "data_emissao": "2024-05-10",
                "produtos": [{"descricao": "Produto B", "quantidade": 1}],
                "parcelas": [{"numero": 1, "data_vencimento": "2024-06-10", "valor": 250.0}],
                "valor_total": 250.0,
                "classificacoes_despesa": [
                    {"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"},
                    {"categoria": "ADMINISTRATIVAS", "justificativa": "Teste"},
                ],
            },
            provider="mock",
        ),
    )
    def test_accounts_payable_can_link_multiple_expense_types(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_multi.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
        payload = service.extract(file)

        movimento = MovimentoContas.objects.get(id=payload["analysis"]["movimento"]["id"])
        self.assertEqual(movimento.classificacoes.count(), 2)
        self.assertEqual(
            set(movimento.classificacoes.values_list("descricao", flat=True)),
            {"MANUTENCAO E OPERACAO", "ADMINISTRATIVAS"},
        )


class ActivableModelTests(TestCase):
    def test_soft_delete_inactivates_person_instead_of_removing_row(self) -> None:
        pessoa = Pessoa.objects.create(
            tipo=Pessoa.Tipo.CLIENTE,
            razao_social="CLIENTE SOFT DELETE",
            documento="12345678901",
        )

        pessoa.delete()

        self.assertFalse(Pessoa.all_objects.get(id=pessoa.id).ativo)
        self.assertFalse(Pessoa.objects.filter(id=pessoa.id).exists())

    def test_queryset_delete_inactivates_classification(self) -> None:
        classificacao = Classificacao.objects.create(
            tipo=Classificacao.Tipo.RECEITA,
            descricao="RECEITA TESTE",
        )

        Classificacao.objects.filter(id=classificacao.id).delete()

        self.assertFalse(Classificacao.all_objects.get(id=classificacao.id).ativo)

    def test_active_person_duplicate_is_blocked(self) -> None:
        Pessoa.objects.create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            razao_social="PESSOA DUPLICADA",
            documento="10101010101",
        )

        with self.assertRaises(ValidationError):
            Pessoa.objects.create(
                tipo=Pessoa.Tipo.FORNECEDOR,
                razao_social="PESSOA DUPLICADA",
                documento="10101010101",
            )

    def test_active_classification_duplicate_is_blocked(self) -> None:
        Classificacao.objects.create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao="DESPESA DUPLICADA",
        )

        with self.assertRaises(ValidationError):
            Classificacao.objects.create(
                tipo=Classificacao.Tipo.DESPESA,
                descricao="despesa duplicada",
            )


class ParcelValidationTests(TestCase):
    @patch(
        "invoices.services.PdfExtractionAgent.extract",
        return_value=ExtractionResult(
            data={
                "fornecedor": {
                    "razao_social": "FORNECEDOR PARCELA",
                    "fantasia": "FORNECEDOR PARCELA",
                    "cnpj": "77.777.777/0001-77",
                },
                "faturado": {"nome_completo": "FATURADO PARCELA", "cpf": "777.777.777-77"},
                "numero_nota_fiscal": "5001",
                "serie": "1",
                "data_emissao": "2024-07-01",
                "produtos": [{"descricao": "Produto C", "quantidade": 1}],
                "parcelas": [
                    {"numero": 1, "data_vencimento": "2024-08-10", "valor": 100.0},
                    {"numero": 2, "data_vencimento": "2024-08-10", "valor": 100.0},
                ],
                "valor_total": 200.0,
                "classificacoes_despesa": [{"categoria": "MANUTENCAO E OPERACAO", "justificativa": "Teste"}],
            },
            provider="mock",
        ),
    )
    def test_multiple_installments_must_have_distinct_due_dates(self, _mock_extract) -> None:
        service = InvoiceExtractionService()
        file = SimpleUploadedFile("nota_parcelas.pdf", b"%PDF-1.4 mock", content_type="application/pdf")

        with self.assertRaisesMessage(ValueError, "Cada parcela deve possuir data de vencimento distinta."):
            service.extract(file)


@override_settings(GEMINI_API_KEY="")
class DatabaseRagApiTests(TestCase):
    def setUp(self) -> None:
        self.fornecedor = Pessoa.objects.create(
            tipo=Pessoa.Tipo.CLIENTE_FORNECEDOR,
            razao_social="EMPRESA FORNECEDORA LTDA",
            documento="12345678000190",
            cidade="Campina Grande",
            uf="PB",
        )
        self.faturado = Pessoa.objects.create(
            tipo=Pessoa.Tipo.FATURADO,
            razao_social="CLIENTE EXEMPLO",
            documento="12345678900",
            cidade="Joao Pessoa",
            uf="PB",
        )
        self.classificacao = Classificacao.objects.create(
            tipo=Classificacao.Tipo.DESPESA,
            descricao="MANUTENCAO E OPERACAO",
        )
        self.extraction = InvoiceExtraction.objects.create(
            file_name="nota_teste.pdf",
            file_size=1234,
            provider="mock",
            status=InvoiceExtraction.Status.SUCCESS,
            result_json={
                "fornecedor": {"razao_social": "EMPRESA FORNECEDORA LTDA"},
                "numero_nota_fiscal": "NF-101",
                "valor_total": 1500.0,
            },
        )
        self.movimento = MovimentoContas.objects.create(
            tipo=MovimentoContas.Tipo.APAGAR,
            fornecedor=self.fornecedor,
            faturado=self.faturado,
            classificacao=self.classificacao,
            invoice_extraction=self.extraction,
            numero_nota_fiscal="NF-101",
            serie="1",
            data_emissao="2024-01-15",
            valor_total=1500.0,
            observacao="Teste de movimento",
        )
        self.movimento.classificacoes.add(self.classificacao)
        ParcelaContas.objects.create(
            movimento=self.movimento,
            identificacao="APAGAR-NF-101-1",
            numero_parcela=1,
            data_vencimento="2024-02-15",
            valor=1500.0,
            forma_pagamento="Boleto",
        )

    def test_rag_simple_query_returns_context_from_database(self) -> None:
        response = self.client.post(
            reverse("invoices:query_database_rag"),
            data='{"question":"Quais movimentos existem para EMPRESA FORNECEDORA LTDA?","mode":"simple"}',
            content_type="application/json",
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["mode"], "simple")
        self.assertTrue(payload["context"])
        self.assertIn("EMPRESA FORNECEDORA LTDA", payload["answer"])
        self.assertEqual(payload["provider"], "mock")

    def test_rag_embeddings_query_returns_ranked_chunks(self) -> None:
        response = self.client.post(
            reverse("invoices:query_database_rag"),
            data='{"question":"Mostre a parcela do movimento NF-101 e a forma de pagamento","mode":"embeddings"}',
            content_type="application/json",
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "embeddings")
        self.assertGreaterEqual(len(payload["context"]), 1)
        self.assertIn(payload["context"][0]["kind"], {"movimento", "parcela", "extracao"})

    def test_rag_requires_question(self) -> None:
        response = self.client.post(
            reverse("invoices:query_database_rag"),
            data='{"question":"   ","mode":"simple"}',
            content_type="application/json",
        )
        payload = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "Falha na consulta RAG.")
