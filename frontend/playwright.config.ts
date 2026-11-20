import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

const {EVIDENCERAG_E2E_PYTHON, EVIDENCERAG_E2E_TEMP, EVIDENCERAG_E2E_API_PORT, EVIDENCERAG_E2E_WEB_PORT,
  PLAYWRIGHT_CHANNEL} = process.env;
if (!EVIDENCERAG_E2E_PYTHON || !EVIDENCERAG_E2E_TEMP ||
    !/^\d{1,5}$/.test(EVIDENCERAG_E2E_API_PORT ?? "") || !/^\d{1,5}$/.test(EVIDENCERAG_E2E_WEB_PORT ?? "")) {
  throw new Error("Start the isolated browser suite with .venv/bin/python -m evaluation.browser.");
}
const api = `http://127.0.0.1:${EVIDENCERAG_E2E_API_PORT}`;
const web = `http://127.0.0.1:${EVIDENCERAG_E2E_WEB_PORT}`;
const python = "'" + EVIDENCERAG_E2E_PYTHON.replaceAll("'", "'\\''") + "'";

export default defineConfig({
  testDir:"./e2e",
  outputDir:resolve(EVIDENCERAG_E2E_TEMP, "results"),
  reporter:"list",
  timeout:45_000,
  workers:1,
  use:{
    baseURL:web, browserName:"chromium", channel:PLAYWRIGHT_CHANNEL,
    viewport:{width:1280, height:900},
  },
  webServer:[
    {name:"Isolated EvidenceRAG API", cwd:resolve(".."),
      command:`${python} -m evaluation.browser_server`, url:`${api}/health`, timeout:60_000, reuseExistingServer:false},
    {name:"EvidenceRAG frontend", command:`npm run dev -- --host 127.0.0.1 --port ${EVIDENCERAG_E2E_WEB_PORT} --strictPort`,
      url:web, env:{VITE_API_URL:api}, reuseExistingServer:false},
  ],
});
