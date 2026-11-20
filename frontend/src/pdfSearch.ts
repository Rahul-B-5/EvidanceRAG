export function normalizePdfText(text: string): string {
  return text.normalize("NFKC").replace(/\s+/gu, " ").trim();
}

export function pdfSearchExcerpt(rawText: string, query: string) {
  const text = normalizePdfText(rawText);
  const needle = normalizePdfText(query);
  if (!needle) return null;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(escaped, "iu").exec(text);
  if (!match) return null;
  const start = Math.max(0, match.index - 52);
  const end = Math.min(text.length, match.index + match[0].length + 82);
  return {
    before: (start ? "…" : "") + text.slice(start, match.index),
    match: match[0],
    after: text.slice(match.index + match[0].length, end) + (end < text.length ? "…" : ""),
  };
}
