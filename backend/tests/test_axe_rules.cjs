// Run with Node; no browser or network access is needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const directory = path.resolve(__dirname, '../app/services/detection');
const axe = require(path.join(directory, 'axe.min.js'));
const source = fs.readFileSync(path.join(directory, 'detect.py'), 'utf8');
const block = source.match(/RELEVANT_RULES = \(([\s\S]*?)\n\)/)[1];
const selected = Array.from(block.matchAll(/"([^"]+)"/g), match => match[1]);
const rules = new Map(axe.getRules().map(rule => [rule.ruleId, rule]));
const readme = fs.readFileSync(path.join(directory, 'README.md'), 'utf8');
const documented = Array.from(readme.matchAll(/^\| `([^`]+)` \| .* \| (?:WCAG|Best practice) \|/gm), match => match[1]);

assert.equal(axe.version, '4.10.3');
assert.equal(selected.length, 39);
assert.equal(new Set(selected).size, selected.length);
for (const id of selected) {
  assert(rules.has(id), `Unknown selected rule: ${id}`);
  // Inspect this pinned bundle's configuration without running a page scan.
  assert.equal(axe._audit.rules.find(rule => rule.id === id).enabled, true, `Disabled rule: ${id}`);
  const metadata = rules.get(id);
  const classification = metadata.tags.includes('best-practice') ? 'Best practice' : 'WCAG';
  const row = readme.split('\n').find(line => line.startsWith(`| \`${id}\` |`));
  assert(row?.includes(`| ${classification} |`), `Incorrect classification: ${id}`);
  for (const tag of metadata.tags.filter(tag => tag.startsWith('wcag'))) {
    assert(row.includes(`\`${tag}\``), `Missing tag for ${id}: ${tag}`);
  }
}
assert.deepEqual(documented, selected);
console.log(`Verified Axe ${axe.version}: all ${selected.length} selected rules exist, are enabled, and match the documented inventory.`);
