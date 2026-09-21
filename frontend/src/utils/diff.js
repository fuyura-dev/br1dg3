// Computes a line-level diff between two HTML documents using an LCS
// alignment. The result is a flat list of rows suited to a side-by-side
// viewer: unchanged lines occupy both columns, a removed line occupies
// only the left column, and an added line occupies only the right column
// at the same row index (so the two panels stay visually aligned).
export function diffLines(originalText, revisedText) {
  const a = (originalText ?? "").split("\n");
  const b = (revisedText ?? "").split("\n");
  const n = a.length;
  const m = b.length;

  const lengths = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        a[i] === b[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }

  const rows = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ type: "unchanged", originalLine: i + 1, revisedLine: j + 1, originalText: a[i], revisedText: b[j] });
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      rows.push({ type: "removed", originalLine: i + 1, revisedLine: null, originalText: a[i], revisedText: null });
      i += 1;
    } else {
      rows.push({ type: "added", originalLine: null, revisedLine: j + 1, originalText: null, revisedText: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    rows.push({ type: "removed", originalLine: i + 1, revisedLine: null, originalText: a[i], revisedText: null });
    i += 1;
  }
  while (j < m) {
    rows.push({ type: "added", originalLine: null, revisedLine: j + 1, originalText: null, revisedText: b[j] });
    j += 1;
  }
  return rows;
}
