import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const title = "EvidenceRAG browser fixture";

async function capture(page: Page, name: string) {
  const folder = process.env.EVIDENCERAG_E2E_SCREENSHOTS;
  const original = page.viewportSize()!;
  const scroll = await page.evaluate(() => window.scrollY);
  if (folder) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path:join(folder, `${name}-desktop.png`), animations:"disabled"});
    await page.getByRole("button", {name:"Dark theme", exact:true}).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path:join(folder, `${name}-dark.png`), animations:"disabled"});
    await page.getByRole("button", {name:"Light theme", exact:true}).click();
  }
  await page.setViewportSize({width:390, height:844});
  await page.evaluate(() => window.scrollTo(0, 0));
  expect.soft(await page.evaluate(() => document.documentElement.scrollWidth), `${name} stays within the viewport`).toBeLessThanOrEqual(390);
  if (name === "atlas") {
    await expect.poll(() => page.locator(".atlas-stage").evaluate(stage => {
      const viewport = stage.getBoundingClientRect();
      return [...stage.querySelectorAll(".atlas-node")].every(node => {
        const card = node.getBoundingClientRect();
        return card.left >= viewport.left && card.right <= viewport.right &&
          card.top >= viewport.top && card.bottom <= viewport.bottom;
      });
    })).toBe(true);
  }
  if (name === "reader-table") {
    await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
    if (folder) await page.locator(".indexed-table-row").first().screenshot({path:join(folder, "reader-table-cell-narrow.png"), animations:"disabled"});
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  if (name === "overview") {
    expect(await page.locator(".app-sidebar").evaluate(sidebar => sidebar.getBoundingClientRect().height)).toBeLessThan(125);
  }
  if (folder) await page.screenshot({path:join(folder, `${name}-narrow.png`), animations:"disabled"});
  await page.setViewportSize(original);
  await page.evaluate(top => window.scrollTo(0, top), scroll);
}

test("import, inspect, save, answer and export a real PDF", async ({page, request}) => {
  page.setDefaultTimeout(10_000);
  const fixture = join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-fixture.pdf");
  await page.goto("/");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  const importButton = page.getByRole("button", {name:"Import PDFs", exact:true});
  const files = page.locator("input[type=file]");
  const queue = page.getByRole("region", {name:"PDF import queue"});
  await files.setInputFiles(fixture);
  await expect(queue.getByText("Imported", {exact:true})).toBeVisible();
  await expect(importButton).toBeEnabled();
  await files.setInputFiles(fixture);
  await expect(queue.getByText("Already in library", {exact:true})).toBeVisible();
  await expect(importButton).toBeEnabled();
  await files.setInputFiles({name:"corrupt.pdf", mimeType:"application/pdf", buffer:Buffer.from("%PDF-1.7\ninvalid")});
  await expect(queue.getByText(/^Failed · /)).toBeVisible();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(2);
  await page.reload();
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await expect(queue.getByText("Imported", {exact:true})).toBeVisible();
  await expect(queue.getByText("Already in library", {exact:true})).toBeVisible();
  await expect(queue.getByText(/^Failed · /)).toBeVisible();
  await capture(page, "library");

  await page.getByRole("button", {name:title, exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 1"})).toBeVisible();
  await page.getByRole("searchbox", {name:"Find in PDF"}).fill("37 observations");
  await page.getByRole("button", {name:"Find", exact:true}).click();
  await page.getByRole("list", {name:"PDF search results"}).getByRole("button", {name:/Page 2/}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await page.getByRole("button", {name:"Bookmark page", exact:true}).click();
  await expect(page.getByRole("button", {name:"Remove page bookmark"})).toBeVisible();
  await capture(page, "reader");
  await page.getByRole("button", {name:"Save passage", exact:true}).click();
  await expect(page.getByRole("button", {name:"Saved", exact:true})).toBeVisible();
  const source = await page.getByRole("link", {name:"Open original PDF"}).getAttribute("href");
  expect(source).toMatch(/\/documents\/\d+\/source#page=2$/);
  const pdf = await request.get(source!.split("#")[0], {headers:{Range:"bytes=0-7"}});
  expect(pdf.status()).toBe(206);
  expect(await pdf.body()).toEqual((await readFile(fixture)).subarray(0, 8));
  await page.getByText("Search embeddings", {exact:true}).click();
  await page.getByRole("button", {name:"Rebuild embeddings", exact:true}).click();
  await expect(page.getByText("Embedding rebuild complete.", {exact:true})).toBeVisible();
  await expect(page.getByText("1 of 1 passages match the active embedding profile.", {exact:true})).toBeVisible();
  const reading = page.getByRole("combobox", {name:"Reading status",exact:true});
  await reading.selectOption("finished");
  await expect(reading).toHaveValue("finished");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.getByRole("combobox", {name:"Reading status",exact:true}).selectOption("finished");
  await expect(page.getByRole("table").getByText("Last read · Page 2", {exact:true})).toBeVisible();
  await page.reload();
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.getByRole("button", {name:title,exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await expect(reading).toHaveValue("finished");
  await page.getByRole("button", {name:"Previous",exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 1"})).toBeVisible();

  await page.getByRole("button", {name:"Saved evidence", exact:true}).click();
  await page.getByRole("textbox", {name:"Research note"}).fill("Verify the held-out sample counts.");
  await page.getByRole("button", {name:"Save note", exact:true}).click();
  await expect(page.getByText("Note saved.", {exact:true})).toBeVisible();
  await page.getByRole("textbox", {name:"Tags"}).fill("Calibration, REVIEW");
  await page.getByRole("button", {name:"Save tags",exact:true}).click();
  await expect(page.getByText("Tags saved.", {exact:true})).toBeVisible();
  await page.reload();
  await page.getByRole("button", {name:"Saved evidence", exact:true}).click();
  await page.getByRole("combobox", {name:"Filter by tag"}).selectOption("review");
  await page.getByRole("searchbox", {name:"Search saved evidence"}).fill("Verify counts");
  await expect(page.getByText("1 of 1 passages", {exact:true})).toBeVisible();
  await page.getByRole("searchbox", {name:"Search saved evidence"}).fill("nonexistent term");
  await expect(page.getByText("No passages match these filters.")).toBeVisible();
  const notebook = page.waitForEvent("download");
  await page.getByRole("button", {name:"Export Markdown"}).click();
  const notes = await readFile(await (await notebook).path(), "utf8");
  expect(notes).toContain("Verify the held-out sample counts.");
  expect(notes).toContain("Tags: calibration, review");

  await page.getByRole("button", {name:"Assistant", exact:true}).click();
  await page.getByRole("combobox", {name:"Sources"}).selectOption("selected");
  await page.getByRole("checkbox", {name:title}).check();
  await page.getByRole("textbox", {name:"Question"}).fill("What is the held-out sample size?");
  await page.getByRole("button", {name:"Send question"}).click();
  const citation = page.getByRole("link", {name:/\[E1\].*page 2/i});
  await expect(citation).toContainText("Calibration results");
  await expect(citation).toBeVisible();
  await expect(page.getByText("The held-out sample contains 37 observations [E1].", {exact:true})).toBeVisible();
  await capture(page, "assistant");
  await citation.click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await expect(page.locator(".cited-passage")).toContainText("37 observations");
  await expect(page.getByRole("button", {name:"Remove page bookmark"})).toBeVisible();

  await page.getByRole("button", {name:"Assistant", exact:true}).click();
  await page.getByRole("combobox", {name:"Conversation"}).selectOption({label:"Legacy browser conversation"});
  await expect(page.getByText("Archived calibration summary.", {exact:true})).toBeVisible();
  await page.getByRole("textbox", {name:"Question"}).fill("Did it report the sample size?");
  await expect(page.getByRole("button", {name:"Send question"})).toBeDisabled();
  await page.getByRole("checkbox", {name:title}).check();
  await page.getByRole("button", {name:"Save conversation sources"}).click();
  await expect(page.getByRole("status").filter({hasText:"Sources saved for future replies."})).toBeVisible();
  await page.getByRole("button", {name:"Send question"}).click();
  await expect(page.getByRole("link", {name:/\[E1\].*page 2/i})).toBeVisible();
  await expect(page.getByText("Archived calibration summary.", {exact:true})).toBeVisible();

  await page.getByRole("button", {name:"Evidence packets", exact:true}).click();
  await page.getByRole("textbox", {name:"Packet title"}).fill("Calibration briefing");
  await page.getByRole("combobox", {name:"Briefing template"}).selectOption("question-investigation");
  await page.getByRole("checkbox", {name:/EvidenceRAG browser fixture/}).check();
  await page.getByRole("button", {name:"Create evidence packet"}).click();
  await page.getByRole("textbox", {name:"Briefing text"}).fill("The held-out sample contained 37 observations [E1].");
  await page.getByRole("button", {name:"Save briefing"}).click();
  await expect(page.getByText("Briefing saved.", {exact:true})).toBeVisible();
  await page.getByRole("combobox", {name:"Export format"}).selectOption("html");
  const exportEvent = page.waitForEvent("download");
  await page.getByRole("button", {name:"Export evidence packet"}).click();
  const markup = await readFile(await (await exportEvent).path(), "utf8");
  expect(markup).toContain('<a href="#E1">[E1]</a>');
  expect(markup).toContain("Verify the held-out sample counts.");
  await capture(page, "evidence-packets");
  await page.getByText(/^\[E1\] EvidenceRAG browser fixture · p\. 2$/).click();
  await expect(page.getByRole("link", {name:"Open source",exact:true})).toHaveAttribute("href", /page=2&chunk=\d+/);

  await page.getByRole("button", {name:"Reproducibility", exact:true}).click();
  await expect(page.getByRole("heading", {level:1,name:"Reproducibility"})).toBeVisible();
  await page.getByRole("combobox", {name:"Paper to assess"}).selectOption({label:title});
  await page.getByRole("button", {name:"Assess reproducibility"}).click();
  await expect(page.getByRole("heading", {name:title,exact:true})).toBeVisible();
  await page.getByText("Random seeds", {exact:true}).click();
  await expect(page.getByRole("link", {name:"Open source · p. 2"}).first()).toHaveAttribute("href", /page=2&chunk=\d+/);
  await page.getByLabel("Notes for export").fill("Verify the training run with seed 42.");
  const dossierEvent = page.waitForEvent("download");
  await page.getByRole("button", {name:"Export Reproduction Dossier"}).click();
  const dossier = await readFile(await (await dossierEvent).path(), "utf8");
  expect(dossier).toContain("random seed was 42");
  expect(dossier).toContain("Verify the training run with seed 42.");
  await capture(page, "reproducibility");

  await page.getByRole("button", {name:"Research directions", exact:true}).click();
  await expect(page.getByRole("heading", {name:"Generalization and external validation"})).toBeVisible();
  const panels = await page.locator(".direction-layout > section").evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().top));
  expect(panels[0]).toBe(panels[1]);
  await expect(page.getByRole("link", {name:"Open source · p. 2"}).first()).toHaveAttribute("href", /page=2&chunk=\d+/);
  await page.getByRole("textbox", {name:"Research question",exact:true}).fill("Does StarlingNet generalize to new sites?");
  const planEvent = page.waitForEvent("download");
  await page.getByRole("button", {name:"Export investigation plan"}).click();
  const plan = await readFile(await (await planEvent).path(), "utf8");
  expect(plan).toContain("Does StarlingNet generalize to new sites?");
  expect(plan).toContain("lacked external validation");
  await capture(page, "research-directions");

  await page.getByRole("button", {name:"Overview", exact:true}).click();
  await expect(page.getByRole("heading", {level:1,name:"Overview"})).toBeVisible();
  await capture(page, "overview");
  await page.getByRole("button", {name:"Settings", exact:true}).click();
  await expect(page.getByText("PostgreSQL connected", {exact:true})).toBeVisible();
  await expect(page.getByText("1 of 1 passages", {exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Test provider", exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:/Provider check passed/})).toBeVisible();
});

test("keyboard navigation and responsive layout work on a narrow viewport", async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await page.goto("/");
  await expect(page.getByRole("button", {name:"Refresh library"})).toBeEnabled();
  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog", {name:"Quick open"});
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox").fill("research directions");
  await dialog.getByRole("textbox").press("Enter");
  await expect(page.getByRole("heading", {level:1, name:"Research directions"})).toBeVisible();
  await expect(dialog).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const menu = page.getByRole("button", {name:"Menu", exact:true});
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("navigation", {name:"Research navigation"}).getByRole("button", {name:"Library", exact:true}).click();
  await expect(page.getByRole("heading", {level:1,name:"Library"})).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  const theme = await page.locator("html").getAttribute("data-theme");
  await page.getByRole("button", {name:theme === "dark" ? "Light theme" : "Dark theme", exact:true}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme === "dark" ? "light" : "dark");
});

test("comparison claims stay searchable and assessments survive reopening", async ({page,request}) => {
  await page.goto("/");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.locator("input[type=file]").setInputFiles([
    join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-fixture.pdf"),
    join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-second.pdf"),
  ]);
  await expect(page.getByRole("button", {name:"EvidenceRAG replication fixture",exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Comparison studio",exact:true}).click();
  await page.getByRole("checkbox", {name:title,exact:true}).check();
  await page.getByRole("checkbox", {name:"EvidenceRAG replication fixture",exact:true}).check();
  await page.getByRole("button", {name:"Run structured comparison"}).click();
  await expect(page.getByText("Comparison completed", {exact:true})).toBeVisible({timeout:15000});
  await capture(page, "comparison");
  await page.getByRole("link", {name:"Open claim",exact:true}).first().click();
  const detail = page.getByRole("region", {name:"Claim details"});
  await expect(detail.locator("blockquote").first()).toContainText("The held-out sample size was 37 observations.");
  await detail.getByLabel("Evidence status").selectOption("qualified");
  await detail.getByLabel("Assessment note").fill("The excerpt reports the sample size.");
  await detail.getByRole("button", {name:"Save assessment",exact:true}).click();
  await expect(detail.getByText("Assessment saved.",{exact:true})).toBeVisible();
  await detail.getByRole("button", {name:"Save passage",exact:true}).click();
  await expect(detail.getByRole("button", {name:"Saved",exact:true})).toBeVisible();
  await capture(page, "claims");
  await detail.getByRole("link", {name:"Explore in Atlas"}).click();
  await expect(page.getByRole("heading", {name:"Evidence Atlas",exact:true})).toBeVisible();
  await page.getByLabel("Relationship").selectOption("shared_dataset_metric");
  await expect(page.locator(".atlas-detail").getByText("Shared dataset and metric",{exact:true})).toBeVisible();
  await capture(page, "atlas");
  await page.getByRole("link", {name:"Open claim",exact:true}).click();
  await expect(detail.getByLabel("Evidence status")).toHaveValue("qualified");
  await detail.getByRole("link", {name:/Open source/}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await page.getByText("Related papers", {exact:true}).click();
  await expect(page.getByRole("link", {name:"EvidenceRAG replication fixture",exact:true})).toBeVisible();
  await expect(page.getByRole("link", {name:"Claim in related paper",exact:true})).toHaveAttribute("href", /^#claim=finding:/);
  const original = new URL((await page.getByRole("link", {name:"Open original PDF"}).getAttribute("href"))!);
  const documentURL = original.origin + original.pathname.replace(/\/source$/, "");
  const passages = await (await request.get(documentURL + "/passages?page=2")).json();
  const passage = passages.passages[0];
  const start = passage.text.indexOf("StarlingNet");
  const highlight = await request.post(documentURL + "/reader-highlights", {data:{
    chunk_id:passage.chunk_id,page:2,start_offset:start,end_offset:start+"StarlingNet".length,note:"Graph annotation fixture",
  }});
  expect(highlight.status()).toBe(201);
  await page.getByRole("link", {name:"Explore claims",exact:true}).click();
  await page.getByRole("searchbox", {name:"Search claims",exact:true}).fill("observations");
  await page.getByRole("button", {name:"Search",exact:true}).click();
  const list = page.getByRole("region", {name:"Claim search results"});
  await expect(list.getByRole("button", {name:/37 observations/})).toBeVisible();
  await expect(list.getByRole("button", {name:/42 observations/})).toHaveCount(0);
  await page.getByRole("button", {name:"Evidence Atlas",exact:true}).click();
  const nodes = page.getByRole("region",{name:"Graph node search results"});
  await page.getByLabel("Node type").selectOption("annotation");
  await nodes.getByRole("button",{name:/StarlingNet/}).click();
  await expect(page.getByText("Graph annotation fixture",{exact:true})).toBeVisible();
  await page.getByLabel("Node type").selectOption("saved_evidence");
  await expect(nodes.getByRole("button",{name:/37 observations/})).toBeVisible();
  await page.getByLabel("Node type").selectOption("method");
  await expect(nodes.getByRole("button",{name:/StarlingNet/})).toBeVisible();

  const collections = original.origin + "/collections";
  const included = await request.post(collections, {data:{name:"Calibration notebook"}});
  const empty = await request.post(collections, {data:{name:"Unrelated notebook"}});
  expect(included.status()).toBe(201);
  expect(empty.status()).toBe(201);
  const [{id: collection}, {id: unrelated}] = await Promise.all([included.json(), empty.json()]);
  const documentId = documentURL.split("/").at(-1);
  expect((await request.put(`${collections}/${collection}/documents/${documentId}`)).status()).toBe(204);
  await page.getByRole("button", {name:"Saved evidence",exact:true}).click();
  const scope = page.getByRole("region", {name:"Notebook scope"});
  await scope.getByRole("combobox", {name:"Collection"}).selectOption(String(collection));
  await expect(page.getByText("1 of 1 passages", {exact:true})).toBeVisible();
  await scope.getByRole("button", {name:"Reader highlights",exact:true}).click();
  await page.getByRole("searchbox", {name:"Search highlights"}).fill("graph fixture");
  await page.getByRole("button", {name:"Search",exact:true}).click();
  await expect(page.getByText("Graph annotation fixture",{exact:true})).toBeVisible();
  await scope.getByRole("combobox", {name:"Collection"}).selectOption(String(unrelated));
  await expect(page.getByText("No Reader highlights match this search and scope.")).toBeVisible();
  await scope.getByRole("combobox", {name:"Collection"}).selectOption(String(collection));
  await page.getByRole("link", {name:"Open in Reader · Page 2",exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await expect(page.getByRole("region", {name:"Page highlights"}).getByRole("textbox")).toHaveValue("Graph annotation fixture");
  await page.getByRole("button", {name:"Saved evidence",exact:true}).click();
  await page.getByRole("button", {name:"Reader highlights",exact:true}).click();
  await page.getByRole("link", {name:"Open in Reader · Page 2",exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
});

test("provider settings discover models and switch the running Assistant", async ({page}) => {
  const localProvider = `http://127.0.0.1:${process.env.EVIDENCERAG_E2E_API_PORT}`;
  const fixture = join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-fixture.pdf");
  await page.goto("/");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.locator("input[type=file]").setInputFiles(fixture);
  await expect(page.getByRole("button", {name:title, exact:true})).toBeVisible();
  for (const model of ["fixture:one", "fixture:two"]) {
    await page.getByRole("button", {name:"Settings",exact:true}).click();
    const settings = page.getByRole("region", {name:"AI Providers"});
    await settings.getByText("Advanced connection").click();
    await settings.getByRole("textbox", {name:"Ollama endpoint"}).fill(localProvider);
    const contextSize = settings.getByRole("spinbutton", {name:"Context size in tokens"});
    await expect(settings.getByText("Ollama connected · 2 installed models")).toBeVisible();
    const field = settings.getByRole("combobox", {name:"Model identifier"});
    await field.fill("fixture:missing");
    await settings.getByRole("button", {name:"Test connection"}).click();
    await expect(settings.getByRole("alert")).toContainText(/model or (native )?API route was not found/);
    await field.fill(model);
    if (model === "fixture:two") {
      await contextSize.fill("1000");
      await settings.getByRole("button", {name:"Test connection"}).click();
      await expect(settings.getByRole("alert")).toContainText("Enter a context size from 2,048 to 65,536 tokens.");
      await contextSize.fill("8192");
    }
    await settings.getByRole("button", {name:"Test connection"}).click();
    await expect(settings.getByText("Connection passed.")).toBeVisible();
    await settings.getByRole("button", {name:"Save provider"}).click();
    await expect(settings.getByText(`Active model · ${model}`)).toBeVisible();
    await capture(page, "ai-providers");
    await page.getByRole("button", {name:"Assistant",exact:true}).click();
    await page.getByRole("combobox", {name:"Sources"}).selectOption("selected");
    await page.getByRole("checkbox", {name:title}).check();
    await page.getByRole("textbox", {name:"Question"}).fill("What calibration size was reported?");
    await page.getByRole("button", {name:"Send question"}).click();
    await expect(page.getByText(`Model ${model} reports 37 observations [E1].`, {exact:true})).toBeVisible();
  }
  await page.reload();
  await page.getByRole("button", {name:"Settings", exact:true}).click();
  const settings = page.getByRole("region", {name:"AI Providers"});
  await expect(settings.getByText("Active model · fixture:two")).toBeVisible();
  await settings.getByText("Advanced connection").click();
  await expect(settings.getByRole("spinbutton", {name:"Context size in tokens"})).toHaveValue("8192");
});

test("Reader preserves table cells and separates neighboring measurements", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.locator("input[type=file]").setInputFiles(join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-table.pdf"));
  await page.getByRole("button", {name:"Calibration table fixture", exact:true}).click();
  await page.getByRole("button", {name:"Next", exact:true}).click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  const rows = page.locator(".indexed-table-row");
  await expect(rows).toHaveCount(2);
  const precision = rows.filter({hasText:"Precision"});
  await expect(precision).toContainText("0.84");
  await expect(precision).not.toContainText("0.72");
  await precision.getByText("Indexed text", {exact:true}).click();
  await expect(precision.getByText(/Reconstructed table row/)).toBeVisible();
  await capture(page, "reader-table");
  const question = "What was the Score for Precision without tuning in Table 2?";
  await page.getByRole("button", {name:"Assistant",exact:true}).click();
  await page.getByRole("combobox", {name:"Sources"}).selectOption("selected");
  await page.getByRole("checkbox", {name:"Calibration table fixture"}).check();
  await page.getByRole("textbox", {name:"Question"}).fill(question);
  await page.getByRole("button", {name:"Send question"}).click();
  const cells = page.locator(".citation-measurements");
  await expect(cells).toHaveText("Matched table cellsScore0.84");
  await capture(page, "assistant-table");
  await page.reload();
  await page.getByRole("button", {name:"Assistant",exact:true}).click();
  await page.getByRole("combobox", {name:"Conversation"}).selectOption({label:question});
  await expect(cells).toHaveText("Matched table cellsScore0.84");
  await page.locator(".citation-row a").click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
  await expect(page.locator(".cited-passage")).toContainText("Precision without tuning");
});

test("configured local Ollama models answer with PDF citations", async ({page}) => {
  const models = (process.env.EVIDENCERAG_BROWSER_OLLAMA_MODELS ?? "").split(",").map(model => model.trim()).filter(Boolean);
  test.skip(models.length !== 2, "Provide two installed Ollama models to run the live browser check.");
  test.setTimeout(180_000);
  const fixture = join(process.env.EVIDENCERAG_E2E_TEMP!, "browser-fixture.pdf");
  await page.goto("/");
  await page.getByRole("button", {name:"Library", exact:true}).click();
  await page.locator("input[type=file]").setInputFiles(fixture);
  await expect(page.getByRole("button", {name:title,exact:true})).toBeVisible();

  for (const model of models) {
    await test.step(model, async () => {
      await page.getByRole("button", {name:"Settings",exact:true}).click();
      const settings = page.getByRole("region", {name:"AI Providers"});
      await settings.getByText("Advanced connection").click();
      await settings.getByRole("textbox", {name:"Ollama endpoint"}).fill("http://127.0.0.1:11434");
      await settings.getByRole("spinbutton", {name:"Context size in tokens"}).fill("8192");
      await expect(settings.getByText(/Ollama connected/)).toBeVisible();
      const field = settings.getByRole("combobox", {name:"Model identifier"});
      await field.fill(model);
      await settings.getByRole("button", {name:"Test connection"}).click();
      await expect(settings.getByText("Connection passed.")).toBeVisible({timeout:60_000});
      await settings.getByRole("button", {name:"Save provider"}).click();
      await expect(settings.getByText(`Active model · ${model}`)).toBeVisible();
      await page.getByRole("button", {name:"Assistant",exact:true}).click();
      await page.getByRole("combobox", {name:"Sources"}).selectOption("selected");
      await page.getByRole("checkbox", {name:title}).check();
      const question = page.getByRole("textbox", {name:"Question"});
      await question.fill("How many observations were in the held-out sample? Include the source citation.");
      await page.getByRole("button", {name:"Send question"}).click();
      await expect(question).toBeEnabled({timeout:90_000});
      expect(await page.locator("main [role=alert]").allTextContents()).toEqual([]);
      const reply = page.locator(".assistant-turn.assistant").last();
      await expect(reply).toContainText(/\b37\b/);
      await expect(reply.locator(".citation-row a").first()).toHaveAttribute("href", /page=2&chunk=\d+/);
    });
  }
});
