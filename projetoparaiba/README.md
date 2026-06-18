# Projeto Administrativo-Financeiro N2

Aplicacao web em Django para upload de PDF de nota fiscal, extracao dos dados com Gemini ou mock local, classificacao automatica de despesa e exibicao do JSON na tela.
Agora o projeto tambem possui uma area de consulta ao banco com RAG, permitindo perguntas em linguagem natural com dois modos de recuperacao:

- RAG SIMPLES
- RAG EMBEDDINGS

## Arquitetura com Agents

Esta etapa usa os agents do codigo no fluxo de extracao:

- PdfExtractionAgent: percebe e processa o PDF enviado, com chamada ao Gemini para interpretacao quando houver chave.
- ValidationAgent: valida o JSON extraido e normaliza no contrato esperado.
- ExpenseClassificationAgent: decide as classificacoes de despesa com base nos dados dos produtos.
- PersistenceAgent: persiste o resultado da extracao no banco, seja sucesso ou erro.
- InvoiceExtractionService: orquestra os agents e retorna a estrutura final para a API.

Fluxo operacional:

1. Perceber: usuario envia PDF em `POST /api/invoices/extract/`.
2. Processar e interpretar: `PdfExtractionAgent` interpreta o documento com Gemini ou fallback mock.
3. Decidir: `ValidationAgent` valida o JSON e `ExpenseClassificationAgent` adiciona classificacoes.
4. Agir: `PersistenceAgent` grava no banco e a resposta volta para a interface.

## Como rodar com Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Se quiser usar Gemini de verdade, preencha no `.env`:

```env
GEMINI_API_KEY=sua_chave_aqui
```

Com Docker:

- app: `http://localhost:8000`
- postgres: `localhost:5433`

## Como rodar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Acesse:

`http://127.0.0.1:8000`

Sem `DATABASE_URL`, o Django usa SQLite local.

## Variaveis de ambiente

Exemplo de `.env`:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
DATABASE_URL=
GEMINI_API_KEY=
POSTGRES_PORT=5433
```

Regras:

- Preencha `GEMINI_API_KEY` para usar Gemini.
- Deixe `GEMINI_API_KEY` vazio para usar fallback mock.
- O arquivo `.env` nao deve ser commitado.

## Como usar pela interface

1. Abra `http://127.0.0.1:8000`.
2. Escolha ou arraste um arquivo `.pdf`.
3. Clique em `Extrair Dados`.
4. Veja o resultado em `Visualizacao Formatada` ou `JSON Bruto`.
5. Use `Copiar JSON` se quiser reaproveitar a saida.
6. Na secao `Pergunte ao banco com RAG simples ou RAG embeddings`, digite uma pergunta sobre os dados salvos.
7. Escolha o modo `RAG Simples` ou `RAG Embeddings`.
8. Clique em `Consultar Banco` para receber uma resposta elaborada com base nos registros recuperados.

## Como usar pela API

Endpoint:

`POST /api/invoices/extract/`

Endpoint RAG:

`POST /api/rag/query/`

Exemplo com `curl`:

```bash
curl -X POST http://127.0.0.1:8000/api/invoices/extract/ \
  -F "pdf=@caminho/para/nota.pdf"
```

Exemplo de consulta RAG:

```bash
curl -X POST http://127.0.0.1:8000/api/rag/query/ \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Quais movimentos existem para a EMPRESA FORNECEDORA LTDA?\",\"mode\":\"simple\"}"
```

Exemplo de fallback:

```json
{
  "success": true,
  "id": 1,
  "provider": "mock",
  "fallback_reason": "GEMINI_API_KEY nao foi configurada.",
  "data": {
    "fornecedor": {
      "razao_social": "EMPRESA FORNECEDORA LTDA",
      "fantasia": "FORNECEDORA",
      "cnpj": "12.345.678/0001-90"
    },
    "faturado": {
      "nome_completo": "CLIENTE EXEMPLO",
      "cpf": "123.456.789-00"
    },
    "numero_nota_fiscal": "000123456",
    "data_emissao": "2024-01-15",
    "produtos": [
      {
        "descricao": "Oleo Diesel S10",
        "quantidade": 100
      }
    ],
    "parcelas": [
      {
        "numero": 1,
        "data_vencimento": "2024-02-15",
        "valor": 1500.0
      }
    ],
    "valor_total": 1500.0,
    "classificacoes_despesa": [
      {
        "categoria": "MANUTENCAO E OPERACAO",
        "justificativa": "Produto relacionado a combustiveis e lubrificantes."
      }
    ]
  }
}
```

## Provider retornado

O campo `provider` pode vir como:

- `gemini`: a extracao veio do Gemini
- `mock`: o sistema usou fallback local

## Testes

### Django

```powershell
python manage.py test invoices
```

### Playwright

```powershell
npm install
npx playwright install
npm run test:e2e
```

Os testes usam mocks e nao dependem de chave real do Gemini.

## Problemas comuns

### `GEMINI_API_KEY nao foi configurada.`

Preencha a chave no `.env`:

```env
GEMINI_API_KEY=sua_chave_aqui
```

### PDF sem texto extraivel

O projeto depende de texto extraido por `pypdf`. PDFs apenas com imagem podem falhar.

### Banco local

Para desenvolvimento rapido:

```env
DATABASE_URL=
DJANGO_DEBUG=1
```
