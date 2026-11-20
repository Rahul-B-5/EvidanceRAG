import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { getDocument, GlobalWorkerOptions, TextLayer, type PDFDocumentProxy, type RenderTask } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "pdfjs-dist/web/pdf_viewer.css";
import { normalizePdfText, pdfSearchExcerpt } from "./pdfSearch";

GlobalWorkerOptions.workerSrc = workerUrl;

const files = import.meta.glob<string>(
  ["../node_modules/pdfjs-dist/cmaps/*.bcmap", "../node_modules/pdfjs-dist/standard_fonts/*.{pfb,ttf}",
   "../node_modules/pdfjs-dist/wasm/{jbig2,openjpeg}.wasm"],
  {eager:true, import:"default", query:"?url&no-inline"},
);
const urls = new Map(Object.entries(files).map(([path, url]) => [path.split("/").at(-1), url]));

class PdfAssets {
  async fetch({filename}: {filename: string}) {
    const url = urls.get(filename);
    if (!url) throw new Error("PDF asset is unavailable.");
    const response = await fetch(url);
    if (!response.ok) throw new Error("PDF asset could not be loaded.");
    return new Uint8Array(await response.arrayBuffer());
  }
}

const MIN_ZOOM = 50;
const MAX_ZOOM = 300;
const MAX_CANVAS_PIXELS = 12_000_000;

export default function PdfViewer({url, page, go, onPageCount}: {
  url: string; page: number; go: (page: number) => void; onPageCount: (count: number) => void;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [loadError, setLoadError] = useState("");
  const [renderState, setRenderState] = useState<"loading" | "ready" | "error">("loading");
  const [zoom, setZoom] = useState(100);
  const [availableWidth, setAvailableWidth] = useState(0);
  const [size, setSize] = useState({width:0, height:0, scale:1, userUnit:1});
  const surface = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);
  const pageCountCallback = useRef(onPageCount);
  pageCountCallback.current = onPageCount;

  useEffect(() => {
    const task = getDocument({
      url, maxImageSize: 20_000_000, canvasMaxAreaInBytes: 48_000_000,
      BinaryDataFactory: PdfAssets, useWorkerFetch: false,
    });
    let cancelled = false;
    task.promise.then(opened => {
      if (cancelled) return;
      setPdf(opened);
      pageCountCallback.current(opened.numPages);
    }).catch(() => {
      if (!cancelled) setLoadError("Unable to open the PDF preview.");
    });
    return () => {cancelled = true; void task.destroy().catch(() => {});};
  }, [url]);

  useEffect(() => {
    if (!surface.current) return;
    const observer = new ResizeObserver(([entry]) => setAvailableWidth(Math.floor(entry.contentRect.width)));
    observer.observe(surface.current);
    return () => observer.disconnect();
  }, [loadError]);

  useEffect(() => {
    if (!pdf || !availableWidth || page > pdf.numPages) return;
    const target = canvas.current;
    const overlay = textLayer.current;
    if (!target || !overlay) return;
    let cancelled = false;
    let task: RenderTask | undefined;
    let layer: TextLayer | undefined;
    setRenderState("loading");
    overlay.replaceChildren();
    pdf.getPage(page).then(opened => {
      if (cancelled) return;
      const base = opened.getViewport({scale:1});
      const scale = Math.min(availableWidth / base.width * zoom / 100, 5);
      const viewport = opened.getViewport({scale});
      const output = Math.min(window.devicePixelRatio || 1, 2, 8192 / viewport.width, 8192 / viewport.height,
        Math.sqrt(MAX_CANVAS_PIXELS / (viewport.width * viewport.height)));
      target.width = Math.max(1, Math.floor(viewport.width * output));
      target.height = Math.max(1, Math.floor(viewport.height * output));
      setSize({width:viewport.width, height:viewport.height, scale, userUnit:opened.userUnit});
      task = opened.render({canvas:target, viewport, transform:[output, 0, 0, output, 0, 0]});
      layer = new TextLayer({textContentSource:opened.streamTextContent(), container:overlay, viewport});
      void layer.render().catch(() => {});
      return task.promise.then(() => {if (!cancelled) setRenderState("ready");});
    }).catch(() => {
      if (!cancelled) setRenderState("error");
    });
    return () => { cancelled = true; task?.cancel(); layer?.cancel(); };
  }, [pdf, page, availableWidth, zoom]);

  if (loadError) return <p role="alert">{loadError} Use the original PDF link to try your browser’s viewer.</p>;
  return <>
    <div className="pdf-controls" aria-label="PDF zoom">
      <button type="button" className="secondary" aria-label="Zoom out" disabled={!pdf || zoom <= MIN_ZOOM}
        onClick={() => setZoom(value => value - 25)}>−</button>
      <button type="button" className="secondary" disabled={!pdf || zoom === 100}
        onClick={() => setZoom(100)} aria-label="Fit page width">Fit width</button>
      <button type="button" className="secondary" aria-label="Zoom in" disabled={!pdf || zoom >= MAX_ZOOM}
        onClick={() => setZoom(value => value + 25)}>+</button>
      <output aria-label="Zoom level">{zoom}%</output>
    </div>
    {pdf && <PdfFind pdf={pdf} go={go} />}
    <div className="pdf-surface" ref={surface} aria-label="PDF page preview" tabIndex={0}>
      {renderState === "loading" && <p role="status">Rendering PDF page…</p>}
      {renderState === "error" && <p role="alert">Unable to render this page. Open the original PDF to view it.</p>}
      <div className="pdf-sheet" hidden={renderState !== "ready"} style={{
        width:size.width, height:size.height, "--scale-factor":size.scale, "--user-unit":size.userUnit,
        "--total-scale-factor":size.scale * size.userUnit,
      } as CSSProperties}>
        <canvas ref={canvas} aria-label={`PDF page ${page}`} role="img" />
        <div ref={textLayer} className="textLayer" aria-label={`Text on PDF page ${page}`} />
      </div>
    </div>
  </>;
}

type PageResult = NonNullable<ReturnType<typeof pdfSearchExcerpt>> & {page: number};
const RESULT_LIMIT = 60;

function PdfFind({pdf, go}: {pdf: PDFDocumentProxy; go: (page: number) => void}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PageResult[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const needle = normalizePdfText(query);
    if (needle.length < 2 || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setResults([]);
    setStatus("Searching PDF…");
    setBusy(true);
    const hits: PageResult[] = [];
    let failed = 0;
    let scanned = 0;
    try {
      for (let page = 1; page <= pdf.numPages && hits.length < RESULT_LIMIT; page++) {
        if (controller.signal.aborted) return;
        try {
          const source = await pdf.getPage(page);
          const content = await source.getTextContent();
          if (controller.signal.aborted) return;
          const text = content.items.map(item => "str" in item ? item.str + (item.hasEOL ? " " : "") : "").join("");
          const excerpt = pdfSearchExcerpt(text, needle);
          if (excerpt) hits.push({page, ...excerpt});
        } catch {
          if (controller.signal.aborted) return;
          failed++;
        }
        scanned = page;
        if (page % 10 === 0) setStatus(`Searching PDF · ${page} of ${pdf.numPages} pages`);
      }
      setStatus(`${hits.length} matching ${hits.length === 1 ? "page" : "pages"}${scanned < pdf.numPages ? ` in the first ${scanned} pages` : ""}.${
        failed ? ` Could not read text from ${failed} pages.` : ""}`);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setResults(hits);
        setBusy(false);
      }
    }
  }

  function cancel() {
    request.current?.abort();
    setStatus("Search cancelled.");
  }

  return <div className="pdf-find">
    <form onSubmit={search}>
      <label>Find in PDF<input type="search" value={query} maxLength={120} onChange={e => setQuery(e.target.value)} /></label>
      <button type="submit" className="secondary" disabled={busy || normalizePdfText(query).length < 2}>Find</button>
      {busy && <button type="button" className="secondary" onClick={cancel}>Cancel search</button>}
    </form>
    {status && <p role="status">{status}</p>}
    {!!results.length && <ol aria-label="PDF search results">
      {results.map(result => <li key={result.page}>
        <button className="secondary" type="button" onClick={() => go(result.page)}>
          <strong>Page {result.page}</strong><span>{result.before}<mark>{result.match}</mark>{result.after}</span>
        </button>
      </li>)}
    </ol>}
  </div>;
}
