# Manual de Acesso – Projeto Administrativo-Financeiro
**Universidade de Rio Verde – UniRV | N3 – 4ª Etapa**

---

## 1. Credenciais de Acesso

| Campo    | Valor              |
|----------|--------------------|
| Usuário  | `admin`            |
| Senha    | `Admin@2026`       |
| E-mail   | admin@projeto.com  |

---

## 2. Acesso ao Sistema (PythonAnywhere)

1. Abra o navegador e acesse a URL do servidor:
   ```
   https://SEUUSUARIO.pythonanywhere.com/
   ```
2. Clique em **Entrar** ou navegue para `/admin/` para o painel Django.
3. Informe as credenciais acima.

---

## 3. Navegação no Sistema

O menu lateral (sidebar) dá acesso a todas as seções:

| Seção              | URL                             | Descrição                        |
|--------------------|----------------------------------|----------------------------------|
| Início             | `/`                             | Dashboard principal              |
| Fornecedores       | `/pessoas/FORNECEDOR/`          | CRUD de fornecedores             |
| Clientes           | `/pessoas/CLIENTE/`             | CRUD de clientes                 |
| Faturados          | `/pessoas/FATURADO/`            | CRUD de faturados                |
| Receitas           | `/classificacao/RECEITA/`       | Classificações de receita        |
| Despesas           | `/classificacao/DESPESA/`       | Classificações de despesa        |
| Contas             | `/contas/`                      | Movimentos de contas a P/R       |
| Admin Django       | `/admin/`                       | Painel administrativo Django     |

---

## 4. Como usar cada tela CRUD

### Carregar registros
- Clique em **"Todos"** para listar todos os registros ativos (status = ATIVO).
- Digite no campo de busca e clique em **"Buscar"** para filtrar.

### Criar registro
- Clique em **"+ Inserir Novo"** (ou "Inserir Nova Conta").
- Preencha os campos obrigatórios (marcados com *).
- O campo STATUS é definido automaticamente como ATIVO ao criar.
- Clique em **"Salvar"**.

### Editar registro
- Clique no botão **"Editar"** na linha desejada.
- Altere os campos (STATUS não é exibido — não é alterável por aqui).
- Clique em **"Salvar"**.

### Excluir registro (exclusão lógica)
- Clique no botão **"Excluir"** na linha desejada.
- Confirme a exclusão. O registro muda para STATUS = INATIVO.
- Registros inativos não aparecem nas listagens normais.

### Ordenar colunas
- Clique no cabeçalho de qualquer coluna para ordenar.
- Clique novamente para inverter a ordem.

---

## 5. Deploy no PythonAnywhere (passo a passo)

### 5.1 Criar conta
1. Acesse https://www.pythonanywhere.com e crie uma conta gratuita.
2. Anote seu **username** (ex: `meuusuario`).

### 5.2 Abrir Bash console
No dashboard do PythonAnywhere, clique em **"Bash"** em "New console".

### 5.3 Clonar o repositório
```bash
git clone https://github.com/Cronoz213/trabalho-paraiba.git
cd trabalho-paraiba/projetoparaiba
```

### 5.4 Criar virtualenv Python 3.13
```bash
mkvirtualenv --python=/usr/bin/python3.13 venv-paraiba
pip install -r requirements.txt
```
> Se Python 3.13 não estiver disponível, use 3.12 ou 3.11.

### 5.5 Criar arquivo .env
```bash
cp .env.example .env
nano .env
```
Edite os campos:
```
DJANGO_SECRET_KEY=uma-chave-secreta-longa
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=meuusuario.pythonanywhere.com
DATABASE_URL=
```
Salve com `Ctrl+X → Y → Enter`.

### 5.6 Preparar o banco e arquivos estáticos
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

### 5.7 Criar superusuário
```bash
python manage.py shell < .tmp/mkadmin.py
```

### 5.8 Popular o banco (200 registros)
```bash
python manage.py seed_invoices
```

### 5.9 Configurar Web App
1. No dashboard PythonAnywhere, vá em **"Web"** → **"Add a new web app"**.
2. Escolha **"Manual configuration"** → **Python 3.13** (ou 3.12).
3. Em **"Virtualenv"**, informe: `/home/meuusuario/.virtualenvs/venv-paraiba`
4. Em **"Code"**, defina **"Source code"**: `/home/meuusuario/trabalho-paraiba/projetoparaiba`

### 5.10 Configurar WSGI
Clique no link do arquivo WSGI (ex: `/var/www/meuusuario_pythonanywhere_com_wsgi.py`) e substitua o conteúdo por:

```python
import os
import sys

path = '/home/meuusuario/trabalho-paraiba/projetoparaiba'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

### 5.11 Configurar arquivos estáticos
Em **"Web"** → **"Static files"**, adicione:

| URL      | Directory                                                     |
|----------|---------------------------------------------------------------|
| /static/ | /home/meuusuario/trabalho-paraiba/projetoparaiba/staticfiles  |

### 5.12 Reiniciar
Clique em **"Reload"** no topo da página Web.

Acesse: `https://meuusuario.pythonanywhere.com/`

---

## 6. Segurança — Chave Gemini

Conforme orientação do PDF do projeto:
> "CUIDADO ao colocar a key das LLM's, pois irá subir para o servidor.  
> RECOMENDÁVEL: Ao abrir, solicitar a(s) chave(s)"

A chave `GEMINI_API_KEY` **não deve** ser commitada no repositório.  
Configure-a apenas no arquivo `.env` do servidor, ou informe em tempo de execução.

---

## 7. Dados de demonstração

O seed script cria **200 contas de movimento** com fornecedores, faturados e classificações variados.  
Após login, clique em **"Contas"** → **"Todos"** para visualizar os registros.
