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
  if (folder) await page.screenshot({path:join(folder, `${name}-narrow.png`), animations:"disabled"});
  await page.setViewportSize(original);
  await page.evaluate(top => window.scrollTo(0, top), scroll);
}

test("import, inspect, save, answer and export a real PDF", async ({page, request}) => {
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
  await expect(citation).toBeVisible();
  await expect(page.getByText("The held-out sample contains 37 observations [E1].", {exact:true})).toBeVisible();
  await capture(page, "assistant");
  await citation.click();
  await expect(page.getByRole("img", {name:"PDF page 2"})).toBeVisible();
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
});
