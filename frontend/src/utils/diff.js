const VOID_TAGS = new Set([
  "area",
  "base",
  "br",
  "col",
  "embed",
  "hr",
  "img",
  "input",
  "link",
  "meta",
  "param",
  "source",
  "track",
  "wbr",
]);

const RAW_TEXT_PATTERN =
  /(<(?:script|style|pre|textarea)\b[^>]*>[\s\S]*?<\/(?:script|style|pre|textarea)>|<!--[\s\S]*?-->|<!DOCTYPE[^>]*>|<\/?[a-zA-Z][^>]*>)/gi;

function parseTagInfo(token) {
  if (token.startsWith("<!--") || /^<!DOCTYPE/i.test(token)) {
    return { kind: "special", name: "", raw: token };
  }
  const rawBlockMatch = token.match(/^<(script|style|pre|textarea)\b/i);
  if (rawBlockMatch && token.toLowerCase().endsWith(`</${rawBlockMatch[1].toLowerCase()}>`)) {
    return { kind: "raw", name: rawBlockMatch[1].toLowerCase(), raw: token };
  }
  const closeMatch = token.match(/^<\/([a-zA-Z][\w:-]*)\s*>$/);
  if (closeMatch) {
    return { kind: "close", name: closeMatch[1].toLowerCase(), raw: `</${closeMatch[1].toLowerCase()}>` };
  }
  const openMatch = token.match(/^<([a-zA-Z][\w:-]*)([\s\S]*?)(\/?)>$/);
  if (openMatch) {
    const name = openMatch[1].toLowerCase();
    const attrs = openMatch[2] || "";
    const selfClosing = Boolean(openMatch[3]) || VOID_TAGS.has(name);
    // Normalize void tags to omit trailing slash so BeautifulSoup output matches original HTML
    const normalizedRaw = VOID_TAGS.has(name)
      ? `<${name}${attrs.replace(/\s+$/, "")}>`
      : `<${name}${attrs}${openMatch[3] ? " /" : ""}>`;
    return {
      kind: selfClosing ? "void" : "open",
      name,
      raw: normalizedRaw,
    };
  }
  return { kind: "text", name: "", raw: token };
}

/**
 * Deterministically formats an HTML string so structural tags and leaf elements
 * align cleanly for side-by-side / inline diffing without false whitespace diffs.
 */
export function formatHtmlForDiff(html) {
  if (!html || typeof html !== "string") return "";

  const tokens = [];
  let lastIndex = 0;
  RAW_TEXT_PATTERN.lastIndex = 0;
  let match = RAW_TEXT_PATTERN.exec(html);

  while (match !== null) {
    if (match.index > lastIndex) {
      const text = html.slice(lastIndex, match.index).replace(/\s+/g, " ").trim();
      if (text) {
        tokens.push({ kind: "text", name: "", raw: text });
      }
    }
    tokens.push(parseTagInfo(match[0]));
    lastIndex = RAW_TEXT_PATTERN.lastIndex;
    match = RAW_TEXT_PATTERN.exec(html);
  }

  if (lastIndex < html.length) {
    const tail = html.slice(lastIndex).replace(/\s+/g, " ").trim();
    if (tail) {
      tokens.push({ kind: "text", name: "", raw: tail });
    }
  }

  const lines = [];
  let depth = 0;
  let i = 0;

  while (i < tokens.length) {
    const curr = tokens[i];
    const indent = "  ".repeat(Math.max(0, depth));

    // Collapse <tag>short text</tag> or <tag></tag> onto a single line
    if (curr.kind === "open") {
      const next = tokens[i + 1];
      const afterNext = tokens[i + 2];
      if (next && next.kind === "close" && next.name === curr.name) {
        lines.push(`${indent}${curr.raw}${next.raw}`);
        i += 2;
        continue;
      }
      if (
        next &&
        next.kind === "text" &&
        next.raw.length <= 100 &&
        afterNext &&
        afterNext.kind === "close" &&
        afterNext.name === curr.name
      ) {
        lines.push(`${indent}${curr.raw}${next.raw}${afterNext.raw}`);
        i += 3;
        continue;
      }

      lines.push(`${indent}${curr.raw}`);
      depth += 1;
      i += 1;
      continue;
    }

    if (curr.kind === "close") {
      depth = Math.max(0, depth - 1);
      const closeIndent = "  ".repeat(depth);
      lines.push(`${closeIndent}${curr.raw}`);
      i += 1;
      continue;
    }

    lines.push(`${indent}${curr.raw}`);
    i += 1;
  }

  return lines.join("\n");
}
