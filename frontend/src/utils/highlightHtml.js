// A deliberately lightweight HTML tokenizer used only for visual syntax
// highlighting in the editor and diff panels. It is not a full parser --
// it classifies line fragments (tags, attribute names/values, comments,
// plain text) well enough to color them, assuming each tag stays on one
// line, which holds for the studio's sample documents.

// Stage 1: split a line into "tag or comment" chunks vs. plain text
// between them.
const CHUNK_PATTERN = /(<!--[\s\S]*?-->|<[^>]*>)/g;

// Stage 2: inside a tag chunk, pull out attribute-name[=value] pairs.
const ATTR_PATTERN = /([a-zA-Z_:][\w:.-]*)(=("[^"]*"|'[^']*'))?/g;

export function tokenizeHtmlLine(line) {
  if (!line) return [];
  const tokens = [];
  let lastIndex = 0;
  CHUNK_PATTERN.lastIndex = 0;
  let match = CHUNK_PATTERN.exec(line);
  while (match !== null) {
    if (match.index > lastIndex) {
      tokens.push({ text: line.slice(lastIndex, match.index), type: "text" });
    }
    const chunk = match[0];
    if (chunk.startsWith("<!--")) {
      tokens.push({ text: chunk, type: "comment" });
    } else if (/^<!DOCTYPE/i.test(chunk)) {
      tokens.push({ text: chunk, type: "doctype" });
    } else {
      tokenizeTag(chunk, tokens);
    }
    lastIndex = CHUNK_PATTERN.lastIndex;
    match = CHUNK_PATTERN.exec(line);
  }
  if (lastIndex < line.length) {
    tokens.push({ text: line.slice(lastIndex), type: "text" });
  }
  return tokens;
}

function tokenizeTag(chunk, tokens) {
  const nameMatch = chunk.match(/^<\/?[a-zA-Z][\w-]*/);
  if (!nameMatch) {
    tokens.push({ text: chunk, type: "text" });
    return;
  }
  tokens.push({ text: nameMatch[0], type: "tag" });

  const rest = chunk.slice(nameMatch[0].length);
  const closeMatch = rest.match(/(\/?>)$/);
  const closeText = closeMatch ? closeMatch[0] : "";
  const attrsPart = closeText ? rest.slice(0, rest.length - closeText.length) : rest;

  ATTR_PATTERN.lastIndex = 0;
  let attrLast = 0;
  let attrMatch = ATTR_PATTERN.exec(attrsPart);
  while (attrMatch !== null) {
    if (attrMatch.index > attrLast) {
      tokens.push({ text: attrsPart.slice(attrLast, attrMatch.index), type: "text" });
    }
    tokens.push({ text: attrMatch[1], type: "attr-name" });
    if (attrMatch[2]) {
      tokens.push({ text: "=", type: "text" });
      tokens.push({ text: attrMatch[3], type: "attr-value" });
    }
    attrLast = ATTR_PATTERN.lastIndex;
    attrMatch = ATTR_PATTERN.exec(attrsPart);
  }
  if (attrLast < attrsPart.length) {
    tokens.push({ text: attrsPart.slice(attrLast), type: "text" });
  }

  if (closeText) {
    tokens.push({ text: closeText, type: "tag" });
  }
}
