// Formatting helpers shared by app screens.

export function relativeTime(input: string | null | undefined): string {
  if (!input) return "–";
  const d = new Date(input.length === 10 ? `${input}T00:00:00Z` : input.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(input) ? "" : "Z"));
  if (isNaN(+d)) return input;
  const s = Math.round((Date.now() - +d) / 1000);
  if (input.length === 10) {
    const days = Math.floor(s / 86400);
    return days <= 0 ? "Today" : days === 1 ? "Yesterday" : `${days}d ago`;
  }
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function host(u: string): string {
  try {
    return new URL(u).host;
  } catch {
    return u;
  }
}

export function path(u: string): string {
  try {
    const x = new URL(u);
    return x.pathname + x.search;
  } catch {
    return "";
  }
}

const PLATFORM_NAMES: Record<string, string> = {
  gist: "GitHub Gist",
  github: "GitHub",
  pastebin: "Pastebin",
  notion: "Notion",
  trello: "Trello",
  google_docs: "Google Docs",
  google_drive: "Google Drive",
  airtable: "Airtable",
  miro: "Miro",
  figma: "Figma",
  gitlab: "GitLab",
  bitbucket: "Bitbucket",
  codeberg: "Codeberg",
  huggingface: "Hugging Face",
  postman: "Postman",
  atlassian: "Confluence & Jira",
  gitbook: "GitBook",
  coda: "Coda",
  rentry: "Rentry",
  paste_ee: "Paste.ee",
  dpaste: "dpaste",
  justpaste: "JustPaste.it",
  replit: "Replit",
  codepen: "CodePen",
  jsfiddle: "JSFiddle",
  pypi: "PyPI",
  npm: "npm",
  docker_hub: "Docker Hub",
  s3: "Amazon S3",
  gcs: "Google Cloud Storage",
  azure_blob: "Azure Blob Storage",
  wayback: "Wayback Machine",
  common_crawl: "Common Crawl",
  telegram: "Telegram",
};

export function platformName(p: string): string {
  return PLATFORM_NAMES[p] ?? p.charAt(0).toUpperCase() + p.slice(1);
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return "–";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** "lines 5–7" or "paragraph p12" from an engine location. */
export function where(loc: { line_start: number | null; line_end: number | null; paragraph_id: string | null }): string {
  if (loc.line_start != null)
    return loc.line_end != null && loc.line_end !== loc.line_start ? `lines ${loc.line_start}–${loc.line_end}` : `line ${loc.line_start}`;
  if (loc.paragraph_id) return `paragraph ${loc.paragraph_id}`;
  return "";
}

export function shortId(id: string): string {
  const [prefix, rest] = id.split("_");
  return rest ? `${prefix}_${rest.slice(0, 6)}` : id.slice(0, 10);
}
