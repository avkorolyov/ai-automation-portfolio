import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("frontend/index.html"), "utf-8");

async function bootstrapDom() {
  document.documentElement.innerHTML = html;
  window.__ENABLE_APP_TEST_HOOKS__ = true;
  vi.resetModules();
  await import("./app.js");
}

describe("frontend app", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    globalThis.fetch = vi.fn();
    globalThis.URL.createObjectURL = vi.fn(() => "blob:test");
    await bootstrapDom();
  });

  it("shows validation error for short text", async () => {
    const text = document.getElementById("txtInput");
    text.value = "коротко";

    document.getElementById("btnText").click();
    await Promise.resolve();

    expect(fetch).not.toHaveBeenCalled();
    expect(document.getElementById("output").innerHTML).toContain("минимум 20 символов");
  });

  it("calls parse endpoint and renders parse result", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        url: "https://example.com",
        title: "Example",
        h1: "Example Domain",
        first_paragraph: "Test paragraph",
        analyzed_chunks: 1,
        strengths: [],
        weaknesses: [],
        unique_offers: [],
        recommendations: [],
        summary: "ok"
      })
    });

    document.getElementById("parseUrl").value = "https://example.com";
    await document.getElementById("btnParse").onclick();

    expect(fetch).toHaveBeenCalledWith(
      "/parse/demo",
      expect.objectContaining({ method: "POST" })
    );
    expect(document.getElementById("output").innerHTML).toContain("Сайт (карточка страницы)");
  });

  it("blocks non-pdf selection", async () => {
    const input = document.getElementById("pdfFile");
    const file = new File(["abc"], "bad.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", {
      configurable: true,
      get: () => [file]
    });

    input.dispatchEvent(new Event("change"));
    await Promise.resolve();

    expect(document.getElementById("output").innerHTML).toContain("только PDF-файл");
  });

  it("loads history when history tab clicked", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          source: "analyze_text",
          created_at: "2026-04-22",
          payload: { input: { text: "Длинный тестовый текст для истории" }, result: {} }
        }
      ]
    });

    document.querySelector('[data-tab="historyTab"]').onclick();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fetch).toHaveBeenCalledWith("/history");
    expect(document.getElementById("historyList").innerHTML).toContain("Анализ текста");
  });

  it("covers helper formatters and renderers", () => {
    const hooks = window.__appTestHooks;
    expect(hooks.actionLabel("analyze_pdf")).toContain("PDF");
    expect(hooks.actionLabel("unknown")).toContain("unknown");
    expect(hooks.previewText({ source: "analyze_image", payload: { input: { filename: "pic.png" } } })).toContain(
      "pic.png"
    );
    expect(hooks.formatErrorPayload([{ loc: ["body", "url"], msg: "bad" }])).toContain("body -> url");
    expect(hooks.renderList("A", ["x"])).toContain("<li>x</li>");
    expect(hooks.renderGenericObject({ a: 1, b: [1, 2] })).toContain("result-block");
    expect(hooks.renderRequestPayload("analyze_pdf", { filename: "f.pdf" })).toContain("f.pdf");
    expect(hooks.renderResultPayload("parse_demo", { url: "u", title: "t", strengths: [] })).toContain("Сайт");
    expect(hooks.renderTextAnalysis({ strengths: [], weaknesses: [], unique_offers: [], recommendations: [] })).toContain(
      "Резюме"
    );
    expect(
      hooks.renderImageAnalysis({
        description: "desc",
        visual_style_score: 10,
        visual_style_analysis: "ok",
        marketing_insights: [],
        recommendations: []
      })
    ).toContain("Описание изображения");
    expect(hooks.renderParseResult({ url: "u", title: "t", strengths: [], weaknesses: [], unique_offers: [], recommendations: [] })).toContain("URL:");
    expect(hooks.renderHistory([{ source: "analyze_text", created_at: "d" }])).toContain("analyze_text");
  });

  it("covers showHuman branches and modal open/close", () => {
    const hooks = window.__appTestHooks;
    hooks.showHuman({ error: "boom" }, "text");
    expect(document.getElementById("output").innerHTML).toContain("Ошибка");
    hooks.showHuman({ strengths: [], weaknesses: [], unique_offers: [], recommendations: [], summary: "s" }, "text");
    hooks.showHuman({ description: "d", visual_style_score: 8, visual_style_analysis: "v", marketing_insights: [], recommendations: [] }, "image");
    hooks.showHuman({ url: "u", title: "t", strengths: [], weaknesses: [], unique_offers: [], recommendations: [], summary: "s" }, "parse");
    hooks.showHuman({ strengths: [], weaknesses: [], unique_offers: [], recommendations: [], summary: "s" }, "pdf");
    hooks.showHuman([], "history");
    hooks.renderHistoryList([
      {
        source: "analyze_text",
        created_at: "2026-04-22",
        payload: { input: { text: "long text long text long text" }, result: { summary: "ok" } }
      }
    ]);
    hooks.openHistoryModal({
      source: "analyze_text",
      payload: { input: { text: "long text long text long text" }, result: { summary: "ok" } }
    });
    expect(document.getElementById("historyModal").classList.contains("hidden")).toBe(false);
    hooks.closeHistoryModal();
    expect(document.getElementById("historyModal").classList.contains("hidden")).toBe(true);
  });

  it("covers button loading states and parseApiResponse paths", async () => {
    const hooks = window.__appTestHooks;
    const btn = document.getElementById("btnText");
    hooks.setButtonLoading(btn, true, "wait");
    expect(btn.disabled).toBe(true);
    hooks.setButtonLoading(btn, false);
    expect(btn.disabled).toBe(false);

    const okRes = { ok: true, status: 200, json: async () => ({ a: 1 }) };
    const badRes = { ok: false, status: 500, json: async () => ({ detail: "bad" }) };
    const noJsonRes = { ok: false, status: 500, json: async () => { throw new Error("x"); } };
    expect(await hooks.parseApiResponse(okRes)).toEqual({ a: 1 });
    expect((await hooks.parseApiResponse(badRes)).error).toContain("bad");
    expect((await hooks.parseApiResponse(noJsonRes)).error).toContain("HTTP 500");
  });

  it("covers image and pdf happy paths", async () => {
    const imageFile = new File(["img"], "x.png", { type: "image/png" });
    const imgInput = document.getElementById("imgFile");
    Object.defineProperty(imgInput, "files", { configurable: true, get: () => [imageFile] });

    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ description: "ok", visual_style_score: 8, visual_style_analysis: "v", marketing_insights: [], recommendations: [] })
    });
    await document.getElementById("btnImage").onclick();
    expect(fetch).toHaveBeenCalledWith("/analyze/image", expect.objectContaining({ method: "POST" }));

    const pdfFile = new File(["pdf"], "x.pdf", { type: "application/pdf" });
    const pdfInput = document.getElementById("pdfFile");
    Object.defineProperty(pdfInput, "files", { configurable: true, get: () => [pdfFile] });
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ strengths: [], weaknesses: [], unique_offers: [], recommendations: [], summary: "ok" })
    });
    await document.getElementById("btnPdf").onclick();
    expect(fetch).toHaveBeenCalledWith("/analyze/pdf", expect.objectContaining({ method: "POST" }));
  });

  it("covers pdf validation, error branch and modal backdrop close", async () => {
    const pdfInput = document.getElementById("pdfFile");
    Object.defineProperty(pdfInput, "files", { configurable: true, get: () => [] });
    await document.getElementById("btnPdf").onclick();
    expect(document.getElementById("output").innerHTML).toContain("Выберите PDF-файл");

    const bigPdf = new File([new Uint8Array(21 * 1024 * 1024)], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(pdfInput, "files", { configurable: true, get: () => [bigPdf] });
    await document.getElementById("btnPdf").onclick();
    expect(document.getElementById("output").innerHTML).toContain("превышает 20MB");

    const okPdf = new File(["pdf"], "ok.pdf", { type: "application/pdf" });
    Object.defineProperty(pdfInput, "files", { configurable: true, get: () => [okPdf] });
    fetch.mockRejectedValueOnce(new Error("network-fail"));
    await document.getElementById("btnPdf").onclick();
    expect(document.getElementById("output").innerHTML).toContain("network-fail");

    const hooks = window.__appTestHooks;
    hooks.openHistoryModal({ source: "analyze_text", payload: { input: {}, result: {} } });
    document.querySelector('[data-close="1"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById("historyModal").classList.contains("hidden")).toBe(true);
  });

  it("covers clear history success and error", async () => {
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: "cleared" }) });
    await document.getElementById("btnClearHistory").onclick();
    expect(fetch).toHaveBeenCalledWith("/history", { method: "DELETE" });

    fetch.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: "err" }) });
    await document.getElementById("btnClearHistory").onclick();
    expect(document.getElementById("historyList").innerHTML).toContain("Ошибка очистки истории");
  });
});
