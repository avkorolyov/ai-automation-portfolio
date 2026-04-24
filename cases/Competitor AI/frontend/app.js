const output = document.getElementById("output");
const resultCard = document.getElementById("resultCard");
const dropZone = document.getElementById("dropZone");
const imgFileInput = document.getElementById("imgFile");
const imagePreview = document.getElementById("imagePreview");
const imagePreviewWrap = document.getElementById("imagePreviewWrap");
const pickImageBtn = document.getElementById("pickImageBtn");
const removeImageBtn = document.getElementById("removeImageBtn");
const dropZonePicker = document.getElementById("dropZonePicker");
const dropZoneSubtext = document.getElementById("dropZoneSubtext");
const pdfDropZone = document.getElementById("pdfDropZone");
const pdfFileInput = document.getElementById("pdfFile");
const pickPdfBtn = document.getElementById("pickPdfBtn");
const removePdfBtn = document.getElementById("removePdfBtn");
const pdfDropZonePicker = document.getElementById("pdfDropZonePicker");
const pdfDropZoneSubtext = document.getElementById("pdfDropZoneSubtext");
const pdfPreviewWrap = document.getElementById("pdfPreviewWrap");
const pdfFileName = document.getElementById("pdfFileName");
const historyList = document.getElementById("historyList");
const historyModal = document.getElementById("historyModal");
const modalClose = document.getElementById("modalClose");
const modalTitle = document.getElementById("modalTitle");
const modalRequest = document.getElementById("modalRequest");
const modalResult = document.getElementById("modalResult");
const btnClearHistory = document.getElementById("btnClearHistory");
let historyCache = [];

function renderList(title, items) {
  if (!items || !items.length) return "";
  const normalizeItem = (item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") {
      const point = item.point ? String(item.point).trim() : "";
      const details = item.details ? String(item.details).trim() : "";
      if (point && details) return `${point}: ${details}`;
      if (point) return point;
      if (details) return details;
      return JSON.stringify(item);
    }
    return String(item ?? "");
  };
  return `
    <div class="result-block">
      <h3>${title}</h3>
      <ul class="result-list">
        ${items.map((item) => `<li>${normalizeItem(item)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function formatErrorPayload(payload) {
  if (payload == null) return "Неизвестная ошибка";
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload)) {
    return payload
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const loc = Array.isArray(item.loc) ? item.loc.join(" -> ") : "field";
          const msg = item.msg || JSON.stringify(item);
          return `${loc}: ${msg}`;
        }
        return String(item);
      })
      .join("\n");
  }
  if (typeof payload === "object") return JSON.stringify(payload, null, 2);
  return String(payload);
}

function renderGenericObject(data) {
  if (!data || typeof data !== "object") {
    return `<div class="result-block"><div>${formatErrorPayload(data)}</div></div>`;
  }
  return Object.entries(data)
    .map(([key, value]) => {
      if (Array.isArray(value)) {
        return renderList(key, value);
      }
      if (value && typeof value === "object") {
        return `
          <div class="result-block">
            <h3>${key}</h3>
            <pre>${JSON.stringify(value, null, 2)}</pre>
          </div>
        `;
      }
      return `
        <div class="result-block">
          <h3>${key}</h3>
          <div>${value ?? ""}</div>
        </div>
      `;
    })
    .join("");
}

function renderRequestPayload(source, input) {
  const payload = input || {};
  if (source === "analyze_text") {
    return `
      <div class="result-block">
        <h3>Текст для анализа</h3>
        <div>${payload.text || ""}</div>
      </div>
    `;
  }
  if (source === "analyze_image") {
    const image = payload.image_url
      ? `<img class="modal-image" src="${payload.image_url}" alt="uploaded image" />`
      : `<div class="muted">Изображение отсутствует</div>`;
    return `
      <div class="result-block">
        <h3>Изображение для анализа</h3>
        ${image}
      </div>
    `;
  }
  if (source === "parse_demo") {
    return `
      <div class="result-block">
        <h3>Ссылка на сайт</h3>
        <div>${payload.url || ""}</div>
      </div>
    `;
  }
  if (source === "analyze_pdf") {
    return `
      <div class="result-block">
        <h3>Файл PDF</h3>
        <div>${payload.filename || ""}</div>
      </div>
    `;
  }
  return renderGenericObject(payload);
}

function renderResultPayload(source, result) {
  if (source === "analyze_text" || source === "analyze_pdf") return renderTextAnalysis(result || {});
  if (source === "analyze_image") return renderImageAnalysis(result || {});
  if (source === "parse_demo") return renderParseResult(result || {});
  return renderGenericObject(result || {});
}

function renderTextAnalysis(data) {
  const template = `
    ${renderList("Сильные стороны", data.strengths)}
    ${renderList("Слабые стороны", data.weaknesses)}
    ${renderList("Уникальные предложения", data.unique_offers)}
    ${renderList("Рекомендации", data.recommendations)}
    <div class="result-block">
      <h3>Резюме</h3>
      <div>${data.summary || ""}</div>
    </div>
  `;
  return template.trim() ? template : renderGenericObject(data);
}

function renderImageAnalysis(data) {
  const rawScore = Number(data.visual_style_score ?? 0);
  const score10 = Math.max(0, Math.min(10, (rawScore / 16) * 10));
  const scoreLabel = `${score10.toFixed(1)}/10`;
  const meterWidth = `${(score10 / 10) * 100}%`;
  const template = `
    <div class="result-block">
      <h3>Описание изображения</h3>
      <div>${data.description || ""}</div>
    </div>
    <div class="result-block">
      <h3>Оценка визуального стиля</h3>
      <div class="score-row">
        <strong>${scoreLabel}</strong>
        <div class="score-meter-wrap">
          <div class="score-meter"><div style="width:${meterWidth}"></div></div>
        </div>
      </div>
      <div class="score-analysis-text">${data.visual_style_analysis || ""}</div>
    </div>
    ${renderList("Маркетинговые инсайты", data.marketing_insights)}
    ${renderList("Рекомендации", data.recommendations)}
  `;
  return template.trim() ? template : renderGenericObject(data);
}

function renderParseResult(data) {
  const strengths = Array.isArray(data.strengths) ? data.strengths : [];
  const weaknesses = Array.isArray(data.weaknesses) ? data.weaknesses : [];
  const uniqueOffers = Array.isArray(data.unique_offers) ? data.unique_offers : [];
  const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
  return `
    <div class="result-block">
      <h3>Сайт (карточка страницы)</h3>
      <div><strong>URL:</strong> ${data.url || ""}</div>
      <div><strong>Title:</strong> ${data.title || ""}</div>
      <div><strong>H1:</strong> ${data.h1 || "Не найден"}</div>
      <div><strong>Первый абзац:</strong> ${data.first_paragraph || "Не найден"}</div>
      <div><strong>Проанализировано чанков:</strong> ${data.analyzed_chunks ?? "-"}</div>
    </div>
    ${renderList("Сильные стороны", strengths)}
    ${renderList("Слабые стороны", weaknesses)}
    ${renderList("Уникальные предложения", uniqueOffers)}
    ${renderList("Рекомендации", recommendations)}
    <div class="result-block">
      <h3>Резюме</h3>
      <div>${data.summary || data.analysis_summary || ""}</div>
    </div>
  `;
}

function renderHistory(data) {
  if (!Array.isArray(data) || !data.length) {
    return `<div class="muted">История пока пуста.</div>`;
  }
  return data
    .slice()
    .reverse()
    .map(
      (item) => `
      <div class="result-block">
        <h3>${item.source || "event"}</h3>
        <div class="muted">${item.created_at || ""}</div>
      </div>
    `
    )
    .join("");
}

function showHuman(data, kind) {
  resultCard.classList.remove("hidden");
  if (data?.error || data?.detail) {
    const errorText = formatErrorPayload(data.error || data.detail);
    output.innerHTML = `<div class="result-block"><h3>Ошибка</h3><pre>${errorText}</pre></div>`;
    return;
  }
  if (kind === "text") {
    output.innerHTML = renderTextAnalysis(data);
    return;
  }
  if (kind === "image") {
    output.innerHTML = renderImageAnalysis(data);
    return;
  }
  if (kind === "parse") {
    output.innerHTML = renderParseResult(data);
    return;
  }
  if (kind === "pdf") {
    output.innerHTML = renderTextAnalysis(data);
    return;
  }
  if (kind === "history") {
    output.innerHTML = renderHistory(data);
    return;
  }
  output.innerHTML = renderGenericObject(data);
}

function setButtonLoading(button, loading, loadingText = "Выполняется...") {
  if (!button) return;
  if (loading) {
    button.dataset.originalText = button.textContent;
    button.textContent = loadingText;
    button.classList.add("loading");
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.classList.remove("loading");
    button.disabled = false;
  }
}

function actionLabel(source) {
  const labels = {
    analyze_text: "Анализ текста",
    analyze_image: "Анализ изображения",
    analyze_pdf: "Анализ PDF",
    parse_demo: "Парсинг сайта",
  };
  return labels[source] || source || "Действие";
}

function previewText(item) {
  const input = item?.payload?.input || {};
  if (item.source === "analyze_text") return (input.text || "").slice(0, 140) || "Текстовый запрос";
  if (item.source === "analyze_image") return input.filename || "Изображение";
  if (item.source === "parse_demo") return input.url || "URL не указан";
  if (item.source === "analyze_pdf") return input.filename || "PDF-документ";
  return "Запрос";
}

function renderHistoryList(items) {
  if (!historyList) return;
  if (!items.length) {
    historyList.innerHTML = `<div class="muted">История пока пуста.</div>`;
    return;
  }
  historyList.className = "history-list";
  historyList.innerHTML = items
    .map((item, index) => {
      const input = item?.payload?.input || {};
      const thumb = input.image_url ? `<img class="history-thumb" src="${input.image_url}" alt="history image" />` : "";
      return `
      <article class="history-item" data-index="${index}">
        <div class="history-title">${actionLabel(item.source)}</div>
        <div class="history-meta">${item.created_at || ""}</div>
        <div class="history-preview">${previewText(item)}</div>
        ${thumb}
      </article>
    `;
    })
    .join("");

  historyList.querySelectorAll(".history-item").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.index);
      openHistoryModal(historyCache[idx]);
    });
  });
}

function openHistoryModal(item) {
  if (!item) return;
  modalTitle.textContent = actionLabel(item.source);
  modalRequest.innerHTML = renderRequestPayload(item.source, item.payload?.input || {});
  modalResult.innerHTML = renderResultPayload(item.source, item.payload?.result || {});
  historyModal.classList.remove("hidden");
}

function closeHistoryModal() {
  historyModal.classList.add("hidden");
}

async function parseApiResponse(res) {
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    data = null;
  }
  if (!res.ok) {
    return { error: formatErrorPayload(data?.detail || data?.error || data || `HTTP ${res.status}`) };
  }
  return data;
}

async function loadHistory() {
  try {
    const res = await fetch("/history");
    const data = await parseApiResponse(res);
    if (data?.error) throw new Error(data.error);
    historyCache = Array.isArray(data) ? data.slice().reverse() : [];
    renderHistoryList(historyCache);
  } catch (err) {
    if (historyList) historyList.innerHTML = `<div class="muted">Ошибка загрузки истории.</div>`;
  }
}

document.querySelectorAll(".menu-btn").forEach((btn) => {
  btn.onclick = () => {
    const target = btn.dataset.tab;
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.id !== target);
    });
    document.querySelectorAll(".menu-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    output.innerHTML = "";
    resultCard.classList.add("hidden");
    if (target === "historyTab") {
      loadHistory();
    }
  };
});

if (dropZone && imgFileInput) {
  pickImageBtn?.addEventListener("click", () => imgFileInput.click());

  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragover");
    if (event.dataTransfer?.files?.length) {
      imgFileInput.files = event.dataTransfer.files;
      const [file] = event.dataTransfer.files;
      if (file && imagePreview) {
        imagePreview.src = URL.createObjectURL(file);
        imagePreviewWrap.classList.remove("hidden");
        dropZonePicker.classList.add("hidden");
        dropZoneSubtext?.classList.add("hidden");
      }
    }
  });

  imgFileInput.addEventListener("change", () => {
    const file = imgFileInput.files?.[0];
    if (file && imagePreview) {
      imagePreview.src = URL.createObjectURL(file);
      imagePreviewWrap.classList.remove("hidden");
      dropZonePicker.classList.add("hidden");
      dropZoneSubtext?.classList.add("hidden");
    }
  });

  removeImageBtn?.addEventListener("click", () => {
    imgFileInput.value = "";
    imagePreview.removeAttribute("src");
    imagePreviewWrap.classList.add("hidden");
    dropZonePicker.classList.remove("hidden");
    dropZoneSubtext?.classList.remove("hidden");
  });
}

if (pdfDropZone && pdfFileInput) {
  const showPdfSelection = (file) => {
    if (!file) return;
    if (pdfFileName) pdfFileName.textContent = file.name || "PDF-файл";
    pdfPreviewWrap?.classList.remove("hidden");
    pdfDropZonePicker?.classList.add("hidden");
    pdfDropZoneSubtext?.classList.add("hidden");
  };

  const clearPdfSelection = () => {
    pdfFileInput.value = "";
    if (pdfFileName) pdfFileName.textContent = "";
    pdfPreviewWrap?.classList.add("hidden");
    pdfDropZonePicker?.classList.remove("hidden");
    pdfDropZoneSubtext?.classList.remove("hidden");
  };

  pickPdfBtn?.addEventListener("click", () => pdfFileInput.click());

  pdfDropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    pdfDropZone.classList.add("dragover");
  });
  pdfDropZone.addEventListener("dragleave", () => {
    pdfDropZone.classList.remove("dragover");
  });
  pdfDropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    pdfDropZone.classList.remove("dragover");
    if (event.dataTransfer?.files?.length) {
      const [file] = event.dataTransfer.files;
      if (!file) return;
      if (file.type !== "application/pdf" && !String(file.name || "").toLowerCase().endsWith(".pdf")) {
        showHuman({ error: "Поддерживается только PDF-файл." }, "pdf");
        return;
      }
      pdfFileInput.files = event.dataTransfer.files;
      showPdfSelection(file);
    }
  });

  pdfFileInput.addEventListener("change", () => {
    const file = pdfFileInput.files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf" && !String(file.name || "").toLowerCase().endsWith(".pdf")) {
      showHuman({ error: "Поддерживается только PDF-файл." }, "pdf");
      clearPdfSelection();
      return;
    }
    showPdfSelection(file);
  });

  removePdfBtn?.addEventListener("click", clearPdfSelection);
}

document.getElementById("btnText").onclick = async () => {
  const btn = document.getElementById("btnText");
  try {
    const competitor = "universal";
    const text = document.getElementById("txtInput").value.trim();
    if (text.length < 20) {
      showHuman({ error: "Текст для анализа должен содержать минимум 20 символов." });
      return;
    }
    setButtonLoading(btn, true, "Анализируем...");
    const res = await fetch("/analyze/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ competitor_name: competitor, text }),
    });
    const data = await parseApiResponse(res);
    showHuman(data, "text");
  } catch (err) {
    showHuman({ error: String(err) }, "text");
  } finally {
    setButtonLoading(btn, false);
  }
};

document.getElementById("btnImage").onclick = async () => {
  const btn = document.getElementById("btnImage");
  try {
    const competitor = "universal";
    const file = document.getElementById("imgFile").files[0];
    if (!file) {
      showHuman({ error: "Выберите файл изображения" }, "image");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showHuman({ error: "Размер файла превышает 10MB." }, "image");
      return;
    }
    setButtonLoading(btn, true, "Анализируем...");
    const form = new FormData();
    form.append("competitor_name", competitor);
    form.append("file", file);
    const res = await fetch("/analyze/image", { method: "POST", body: form });
    const data = await parseApiResponse(res);
    showHuman(data, "image");
  } catch (err) {
    showHuman({ error: String(err) }, "image");
  } finally {
    setButtonLoading(btn, false);
  }
};

document.getElementById("btnParse").onclick = async () => {
  const btn = document.getElementById("btnParse");
  try {
    const url = document.getElementById("parseUrl").value.trim();
    setButtonLoading(btn, true, "Парсим...");
    const res = await fetch("/parse/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await parseApiResponse(res);
    showHuman(data, "parse");
  } catch (err) {
    showHuman({ error: String(err) }, "parse");
  } finally {
    setButtonLoading(btn, false);
  }
};

document.getElementById("btnPdf").onclick = async () => {
  const btn = document.getElementById("btnPdf");
  try {
    const competitor = "universal";
    const file = document.getElementById("pdfFile").files[0];
    if (!file) {
      showHuman({ error: "Выберите PDF-файл" }, "pdf");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      showHuman({ error: "Размер PDF превышает 20MB." }, "pdf");
      return;
    }
    setButtonLoading(btn, true, "Анализируем PDF...");
    const form = new FormData();
    form.append("competitor_name", competitor);
    form.append("file", file);
    const res = await fetch("/analyze/pdf", { method: "POST", body: form });
    const data = await parseApiResponse(res);
    showHuman(data, "pdf");
  } catch (err) {
    showHuman({ error: String(err) }, "pdf");
  } finally {
    setButtonLoading(btn, false);
  }
};

btnClearHistory.onclick = async () => {
  try {
    const res = await fetch("/history", { method: "DELETE" });
    const data = await parseApiResponse(res);
    if (data?.error) throw new Error(data.error);
    historyCache = [];
    renderHistoryList(historyCache);
  } catch (err) {
    if (historyList) historyList.innerHTML = `<div class="muted">Ошибка очистки истории.</div>`;
  }
};

modalClose.addEventListener("click", closeHistoryModal);
historyModal.addEventListener("click", (e) => {
  if (e.target?.dataset?.close === "1") closeHistoryModal();
});

if (typeof window !== "undefined" && window.__ENABLE_APP_TEST_HOOKS__) {
  window.__appTestHooks = {
    renderList,
    formatErrorPayload,
    renderGenericObject,
    renderRequestPayload,
    renderResultPayload,
    renderTextAnalysis,
    renderImageAnalysis,
    renderParseResult,
    renderHistory,
    showHuman,
    setButtonLoading,
    actionLabel,
    previewText,
    renderHistoryList,
    openHistoryModal,
    closeHistoryModal,
    parseApiResponse,
    loadHistory
  };
}
