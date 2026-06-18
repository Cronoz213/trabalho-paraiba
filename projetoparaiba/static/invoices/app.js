const form = document.querySelector("#upload-form");
const ragForm = document.querySelector("#rag-form");
const dropzone = document.querySelector("#dropzone");
const fileInput = document.querySelector("#pdf-input");
const selectedFile = document.querySelector("#selected-file");
const selectedFileName = document.querySelector("#selected-file-name");
const selectedFileSize = document.querySelector("#selected-file-size");
const extractButton = document.querySelector("#extract-button");
const resultPanel = document.querySelector("#result-panel");
const providerBadge = document.querySelector("#provider-badge");
const formattedView = document.querySelector("#formatted-view");
const jsonView = document.querySelector("#json-view");
const jsonOutput = document.querySelector("#json-output");
const copyButton = document.querySelector("#copy-button");
const toast = document.querySelector("#toast");
const ragQuestion = document.querySelector("#rag-question");
const ragMode = document.querySelector("#rag-mode");
const ragSubmit = document.querySelector("#rag-submit");
const ragResult = document.querySelector("#rag-result");
const ragProvider = document.querySelector("#rag-provider");
const ragAnswer = document.querySelector("#rag-answer");
const ragContext = document.querySelector("#rag-context");
const ragExamples = document.querySelectorAll(".rag-example");

let latestJson = null;

copyButton.disabled = true;

const EXTRACT_BUTTON_STATE = {
  EMPTY: "empty",
  READY: "ready",
  LOADING: "loading",
};

function setExtractButtonState(state) {
  switch (state) {
    case EXTRACT_BUTTON_STATE.READY:
      extractButton.disabled = false;
      extractButton.querySelector("span").textContent = "Extrair Dados";
      break;
    case EXTRACT_BUTTON_STATE.LOADING:
      extractButton.disabled = true;
      extractButton.querySelector("span").textContent = "Extraindo...";
      break;
    case EXTRACT_BUTTON_STATE.EMPTY:
    default:
      extractButton.disabled = true;
      extractButton.querySelector("span").textContent = "Extrair Dados";
      break;
  }
}

function setNoFileState() {
  selectedFile.hidden = true;
  selectedFileName.textContent = "";
  selectedFileSize.textContent = "";
  setExtractButtonState(EXTRACT_BUTTON_STATE.EMPTY);
  copyButton.disabled = !latestJson;
}

function setFileState(file) {
  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = formatBytes(file.size);
  selectedFile.hidden = false;
  setExtractButtonState(EXTRACT_BUTTON_STATE.READY);
  copyButton.disabled = !latestJson;
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) {
    setNoFileState();
    return;
  }

  setFileState(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});

dropzone.addEventListener("drop", (event) => {
  const file = Array.from(event.dataTransfer.files).find((item) => item.type === "application/pdf" || item.name.toLowerCase().endsWith(".pdf"));
  if (!file) {
    showToast("Envie um arquivo PDF.");
    return;
  }

  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  setFileState(file);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    showToast("Selecione um arquivo PDF.");
    return;
  }

  const formData = new FormData();
  formData.append("pdf", file);

  setExtractButtonState(EXTRACT_BUTTON_STATE.LOADING);

  try {
    const response = await fetch("/api/invoices/extract/", {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Falha ao extrair dados.");
    }

    const extractedData = payload.data || payload;
    latestJson = payload;

    renderFormatted(extractedData, payload.analysis || {}, payload.message || "");
    renderProvider(payload.provider || payload.source || payload.fallback || "", payload.fallback_reason);
    jsonOutput.textContent = JSON.stringify(payload, null, 2);
    resultPanel.hidden = false;
    showTab("formatted");
    copyButton.disabled = false;
    showToast(payload.message || (payload.provider ? `Dados extraidos via ${payload.provider}.` : "Dados extraidos."));
  } catch (error) {
    showToast(error.message);
  } finally {
    const currentFile = fileInput.files[0];
    if (currentFile) {
      setExtractButtonState(EXTRACT_BUTTON_STATE.READY);
    } else {
      setNoFileState();
    }
  }
});

ragForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = ragQuestion.value.trim();
  if (!question) {
    showToast("Digite uma pergunta para consultar o banco.");
    ragQuestion.focus();
    return;
  }

  setRagLoading(true);

  try {
    const response = await fetch("/api/rag/query/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        question,
        mode: ragMode.value,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Falha ao consultar o banco.");
    }

    renderRagResult(payload);
    showToast(`Consulta ${payload.mode} concluida.`);
  } catch (error) {
    showToast(error.message);
  } finally {
    setRagLoading(false);
  }
});

ragExamples.forEach((button) => {
  button.addEventListener("click", () => {
    ragQuestion.value = button.dataset.question || "";
    ragQuestion.focus();
  });
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});

formattedView.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-history-toggle]");
  if (!toggle) {
    return;
  }

  const panel = formattedView.querySelector("[data-history-panel]");
  if (!panel) {
    return;
  }

  const shouldShow = panel.hidden;
  panel.hidden = !shouldShow;
  toggle.textContent = shouldShow ? "Ocultar dados ja salvos" : `Mostrar dados ja salvos (${toggle.dataset.historyCount || 0})`;
});

copyButton.addEventListener("click", async () => {
  if (!latestJson) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(latestJson, null, 2));
    showToast("JSON copiado.");
  } catch {
    showToast("Nao foi possivel copiar o JSON.");
  }
});

function showTab(name) {
  const isJson = name === "json";
  document.querySelectorAll(".tab").forEach((tab) => {
    const selected = tab.dataset.tab === name;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
  });

  formattedView.hidden = isJson;
  jsonView.hidden = !isJson;
}

function renderProvider(provider, fallbackReason = "") {
  if (!provider && !fallbackReason) {
    providerBadge.hidden = true;
    providerBadge.textContent = "";
    return;
  }

  providerBadge.textContent = fallbackReason ? `Origem: ${provider || "mock"} - ${fallbackReason}` : `Origem: ${provider}`;
  providerBadge.hidden = false;
}

function renderRagResult(payload) {
  ragAnswer.textContent = payload.answer || "Nenhuma resposta gerada.";
  ragProvider.textContent = `Origem: ${payload.provider} - modo ${payload.mode}`;
  ragProvider.hidden = false;
  ragContext.innerHTML = renderRagContext(payload.context || [], payload.stats || {});
  ragResult.hidden = false;
}

function renderRagContext(context, stats) {
  const cards = context.length
    ? context.map((item) => `
      <article class="data-card invoice">
        <div class="data-card-header">
          <h3>${escapeHtml(item.title || `${item.kind} ${item.id}`)}</h3>
        </div>
        <div class="data-card-body">
          <dl class="data-grid">
            ${dataRow("Tipo", item.kind)}
            ${dataRow("ID", item.id)}
            ${dataRow("Score", item.score)}
            ${dataRow("Trecho recuperado", item.text)}
          </dl>
        </div>
      </article>
    `).join("")
    : `
      <article class="data-card invoice">
        <div class="data-card-header"><h3>Contexto recuperado</h3></div>
        <div class="data-card-body">
          <p class="history-copy">Nenhum registro relevante foi recuperado nesta consulta.</p>
        </div>
      </article>
    `;

  return `
    <div class="rag-stats">
      <strong>Base indexada:</strong> ${escapeHtml(stats.total_registros_indexados ?? 0)} registros
    </div>
    <div class="formatted-view">
      ${cards}
    </div>
  `;
}

function setRagLoading(isLoading) {
  ragSubmit.disabled = isLoading;
  ragSubmit.querySelector("span").textContent = isLoading ? "Consultando..." : "Consultar Banco";
}

function renderFormatted(data, analysis = {}, successMessage = "") {
  const fornecedor = data.fornecedor || {};
  const faturado = data.faturado || {};
  const produtos = Array.isArray(data.produtos) ? data.produtos : [];
  const parcelas = Array.isArray(data.parcelas) ? data.parcelas : [];
  const classificacoes = Array.isArray(data.classificacoes_despesa) ? data.classificacoes_despesa : [];
  const lancamentoParcelas = Array.isArray(analysis.parcelas) ? analysis.parcelas : [];

  formattedView.innerHTML = [
    launchMessageCard(successMessage, analysis.movimento),
    supplierHistoryCard(analysis.historico_fornecedor),
    analysisCard(analysis.fornecedor),
    analysisCard(analysis.faturado),
    analysisCard(analysis.despesa),
    card("Fornecedor", compactRows([
      ["Razao Social", fornecedor.razao_social],
      ["Nome Fantasia", fornecedor.fantasia],
      ["CNPJ", fornecedor.cnpj],
      ["Inscricao Estadual", fornecedor.inscricao_estadual],
      ["Endereco", fornecedor.endereco],
      ["Cidade", fornecedor.cidade],
      ["UF", fornecedor.uf],
    ]), "supplier"),
    card("Faturado", compactRows([
      ["Nome Completo", faturado.nome_completo],
      ["CPF", faturado.cpf],
      ["CNPJ", faturado.cnpj],
      ["Endereco", faturado.endereco],
      ["Cidade", faturado.cidade],
      ["UF", faturado.uf],
    ]), "billed", "yellow"),
    card("Identificacao da Nota", compactRows([
      ["Numero", data.numero_nota_fiscal],
      ["Serie", data.serie],
      ["Data de Emissao", data.data_emissao],
      ["Chave de Acesso", data.chave_acesso],
      ["Natureza da Operacao", data.natureza_operacao],
    ]), "invoice"),
    card("Resumo Financeiro", compactRows([
      ["Valor dos Produtos", currency(data.valor_produtos)],
      ["Valor do Frete", currency(data.valor_frete)],
      ["Valor do Desconto", currency(data.valor_desconto)],
      ["Valor do ICMS", currency(data.valor_icms)],
      ["Valor do IPI", currency(data.valor_ipi)],
      ["Valor Total", currency(data.valor_total)],
    ]), "invoice"),
    productsCard(produtos),
    installmentsCard(parcelas),
    classificationCard(classificacoes),
    launchParcelsCard(lancamentoParcelas),
  ].join("");
}

function compactRows(rows) {
  return rows.filter(([, value]) => hasValue(value) && value !== "-");
}

function card(title, rows, className = "", bar = "") {
  const renderedRows = rows.length
    ? rows.map(([label, value]) => dataRow(label, value)).join("")
    : dataRow("Informacao", "Nenhum dado encontrado.");
  const style = bar === "yellow" ? ' style="--card-bar: var(--yellow-bar)"' : "";

  return `
    <article class="data-card ${escapeHtml(className)}"${style}>
      <div class="data-card-header"><h3>${escapeHtml(title)}</h3></div>
      <div class="data-card-body"><dl class="data-grid">${renderedRows}</dl></div>
    </article>
  `;
}

function analysisCard(section) {
  if (!section || !section.titulo) {
    return "";
  }

  return card(section.titulo, compactRows([
    ["Nome", section.nome],
    [section.documento_label || "Documento", section.documento],
    ["Resultado da Consulta", section.status_texto],
    ["ID Final", section.id],
  ]), "invoice");
}

function launchMessageCard(message, movimento) {
  if (!message && !movimento) {
    return "";
  }

  return card("Resultado do Lancamento", compactRows([
    ["Mensagem", message],
    ["Movimento", movimento?.status_texto],
  ]), "classification");
}

function supplierHistoryCard(history) {
  if (!history || !Array.isArray(history.itens) || !history.itens.length) {
    return "";
  }

  const count = Number(history.quantidade || history.itens.length);
  const items = history.itens.map((item) => `
    <details class="history-entry">
      <summary>
        Nota ${escapeHtml(item.numero_nota_fiscal || "-")} • Movimento ${escapeHtml(item.movimento_id || "-")} • ${escapeHtml(currency(item.valor_total))}
      </summary>
      <div class="history-entry-body">
        <dl class="data-grid">
          ${dataRow("Numero da Nota", item.numero_nota_fiscal || "-")}
          ${dataRow("Serie", item.serie || "-")}
          ${dataRow("Data de Emissao", item.data_emissao || "-")}
          ${dataRow("Faturado", item.faturado || "-")}
          ${dataRow("Classificacao", item.classificacao || "-")}
          ${dataRow("Arquivo", item.arquivo || "-")}
          ${dataRow("Origem", item.provider || "-")}
          ${dataRow("Criado em", item.criado_em || "-")}
        </dl>
        <pre class="history-json">${escapeHtml(JSON.stringify(item.dados_extraidos || {}, null, 2))}</pre>
      </div>
    </details>
  `).join("");

  return `
    <article class="data-card classification">
      <div class="data-card-header">
        <h3>${escapeHtml(history.titulo || "Historico do fornecedor")}</h3>
      </div>
      <div class="data-card-body history-card-body">
        <p class="history-copy">Encontramos ${escapeHtml(count)} registro(s) anterior(es) desse fornecedor no banco.</p>
        <button class="history-toggle-button" type="button" data-history-toggle data-history-count="${escapeHtml(count)}">
          Mostrar dados ja salvos (${escapeHtml(count)})
        </button>
        <div class="history-panel" data-history-panel hidden>
          ${items}
        </div>
      </div>
    </article>
  `;
}

function productsCard(produtos) {
  const rows = produtos.map((item, index) => `
    <tr>
      <td>${escapeHtml(index + 1)}</td>
      <td>${escapeHtml(item.descricao || item.nome || "-")}</td>
      <td>${escapeHtml(item.quantidade ?? "-")}</td>
      <td>${escapeHtml(item.unidade || "-")}</td>
      <td>${escapeHtml(item.ncm || "-")}</td>
      <td>${escapeHtml(item.cfop || "-")}</td>
      <td>${escapeHtml(currency(item.valor_unitario))}</td>
      <td>${escapeHtml(currency(item.valor_total ?? item.total))}</td>
    </tr>
  `).join("");

  return tableCard("Produtos e Servicos", "products", ["#", "Descricao", "Qtd.", "Unidade", "NCM", "CFOP", "Valor Unit.", "Total"], rows);
}

function installmentsCard(parcelas) {
  const rows = parcelas.map((item) => `
    <tr>
      <td>${escapeHtml(item.numero ?? "-")}</td>
      <td>${escapeHtml(item.data_vencimento || "-")}</td>
      <td>${escapeHtml(item.forma_pagamento || "-")}</td>
      <td>${escapeHtml(currency(item.valor))}</td>
    </tr>
  `).join("");

  return tableCard("Parcelas", "installments", ["Parcela", "Vencimento", "Forma de Pagamento", "Valor"], rows);
}

function classificationCard(classificacoes) {
  const rows = classificacoes.map((item) => `
    <tr>
      <td>${escapeHtml(item.categoria || "-")}</td>
      <td>${escapeHtml(item.justificativa || "-")}</td>
    </tr>
  `).join("");

  return tableCard("Classificacao de Despesa", "classification", ["Categoria", "Justificativa"], rows);
}

function launchParcelsCard(parcelas) {
  const rows = parcelas.map((item) => `
    <tr>
      <td>${escapeHtml(item.id ?? "-")}</td>
      <td>${escapeHtml(item.identificacao || "-")}</td>
      <td>${escapeHtml(item.numero_parcela ?? "-")}</td>
      <td>${escapeHtml(item.data_vencimento || "-")}</td>
      <td>${escapeHtml(currency(item.valor))}</td>
    </tr>
  `).join("");

  return tableCard("Parcelas Lancadas", "installments", ["ID", "Identificacao", "Parcela", "Vencimento", "Valor"], rows);
}

function tableCard(title, className, headers, rows) {
  const headerCells = headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join("");
  const body = rows || `<tr><td colspan="${headers.length}">Nenhum dado encontrado.</td></tr>`;

  return `
    <article class="data-card ${escapeHtml(className)}">
      <div class="data-card-header"><h3>${escapeHtml(title)}</h3></div>
      <div class="data-card-body">
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>${headerCells}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>
    </article>
  `;
}

function dataRow(label, value) {
  return `
    <div class="data-row">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(hasValue(value) ? value : "-")}</dd>
    </div>
  `;
}

function getCsrfToken() {
  return document.querySelector("input[name='csrfmiddlewaretoken']").value;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function currency(value) {
  if (!hasValue(value) || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => {
    toast.hidden = true;
  }, 3600);
}

setNoFileState();
