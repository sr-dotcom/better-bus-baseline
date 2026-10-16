// Build step 1: read the repository data files and write site/page-data.json, the only file the page imports.
// Nothing is typed by hand: numbers come from data/findings.json, quotes from data/reference/mtc06.md,
// links from data/reference/mpta04.md, SHA-256 values from data/sources.md.
import { readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const data = join(site, '..', 'data');
const read = (p) => readFileSync(join(data, p), 'utf8').replace(/\r\n/g, '\n');

// a stale build keeps old hashed files; start clean
rmSync(join(site, 'build'), { recursive: true, force: true });

const findings = JSON.parse(read('findings.json'));

// Section quotes from mtc06.md: heading "## Section N.N Title (page P)", quote lines start with ">".
function section(md, id) {
  const m = md.match(new RegExp(`^## Section ${id.replace('.', '\\.')} (.+?) \\(page (\\d+)\\)\\n([\\s\\S]*?)(?=^## |$(?![\\s\\S]))`, 'm'));
  if (!m) throw new Error(`section ${id} not found in mtc06.md`);
  const blocks = [];
  let para = [];
  const flush = () => {
    // a line that ends in "-" is a hyphen broken across lines ("off-" + "peak"): join without a space
    if (para.length) blocks.push(para.reduce((a, b) => (a.endsWith('-') ? a + b : `${a} ${b}`)));
    para = [];
  };
  for (const line of m[3].split('\n')) {
    if (!line.startsWith('>')) continue;
    const text = line.replace(/^> ?/, '').trim();
    if (text === '') flush();
    else para.push(text);
  }
  flush();
  return { id, title: m[1], page: Number(m[2]), blocks };
}

const mtc06 = read('reference/mtc06.md');
const mpta04 = read('reference/mpta04.md');
const urlOf = (md, label) => {
  const m = md.match(new RegExp(`^\\| ${label} \\| \`([^\`]+)\``, 'm'));
  if (!m) throw new Error(`${label} not found`);
  return m[1];
};

// Markdown tables of data/sources.md, as arrays of cell strings (header row dropped).
function tables(md) {
  const out = [];
  let cur = null;
  for (const line of md.split('\n')) {
    if (line.startsWith('|')) {
      if (!cur) out.push((cur = []));
      cur.push(line.split('|').slice(1, -1).map((c) => c.trim().replace(/`/g, '')));
    } else cur = null;
  }
  return out.map((t) => t.slice(2));
}
const [feeds, census] = tables(read('sources.md'));

const pageData = {
  built_utc: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
  findings,
  policy: {
    sections: ['2.4', '3.3', '3.7'].map((id) => section(mtc06, id)),
    mpta04_url: urlOf(mpta04, 'URL of the PDF'),
    mpta04_page_url: urlOf(mpta04, 'Named on'),
    mtc06_url: urlOf(mtc06, 'URL')
  },
  sources: { feeds, census }
};
writeFileSync(join(site, 'page-data.json'), JSON.stringify(pageData));
console.log(`page-data.json written (built ${pageData.built_utc})`);
