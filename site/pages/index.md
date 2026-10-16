---
title: Better Bus Baseline
hide_header: true
hide_breadcrumbs: true
hide_toc: true
sidebar: never
---

<script>
  // Every number on this page is read from page-data.json, which scripts/prepare.mjs builds from
  // data/findings.json and the reference files. Nothing here is typed by hand.
  import pd from '../../../../page-data.json';

  const f = pd.findings;
  const H = f.headline;
  const T = H.tiers;
  const P = H.period;
  const R = f.notable_routes.routes;
  const NM = f.near_miss;
  const EQ = f.equity;
  const OTP = f.otp;
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const date = (iso) => MONTHS[+iso.slice(5, 7) - 1] + ' ' + +iso.slice(8, 10) + ', ' + iso.slice(0, 4);
  const mmss = (s) => (s == null ? 'no headway' : String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'));
  const monthYear = (ym) => MONTHS[+ym.slice(5, 7) - 1] + ' ' + ym.slice(0, 4);
  const num = (n) => n.toLocaleString('en-US');
  const signed = (n) => (n > 0 ? '+' : '') + num(n);
  const PERIOD = { am_peak: 'AM peak', midday: 'midday', pm_peak: 'PM peak', weekend_day: 'daytime' };
  const dateBefore = date(P.before);
  const dateAfter = date(P.after);

  // 1. Tier chart: four tiers, before and after, 48 local routes
  const TIERS = [
    { key: '15-min', lines: ['15-min'] },
    { key: '30-min', lines: ['30-min'] },
    { key: 'below standard', lines: ['Below', 'standard'] },
    { key: 'no service', lines: ['No service', 'on date'] }
  ].map((t) => ({ ...t, before: T.before[t.key].count, after: T.after[t.key].count }));
  const CH = { w: 360, h: 262, base: 196, top: 52, slot: 84, left: 12, bar: 32, gap: 4 };
  const peak = Math.max(...TIERS.flatMap((t) => [t.before, t.after]));
  const barH = (v) => (v / peak) * (CH.base - CH.top);
  const slotX = (i) => CH.left + CH.slot * i + CH.slot / 2;

  // 2. Policy quotes
  const SECTIONS = pd.policy.sections;
  const trigger = SECTIONS.find((s) => s.id === '3.3').blocks.join(' ').match(/(\d+) percent or less/)[1];

  // 3. What Oct 5 moved
  const r5 = R['5'];
  const r9 = R['9'];
  const r23 = R['23'];
  const r177 = R['177'];
  const span = (s) => s.start.slice(0, 5) + ' to ' + s.end.slice(0, 5);
  const uniq = (a) => [...new Set(a)];
  const r5before = uniq(r5.flipped_15_min_standard.map((x) => x.median_before_mmss)).join(', ');
  const r5after = uniq(r5.flipped_15_min_standard.map((x) => x.median_after_mmss)).join(', ');
  const thr9 = NM.rows.find((x) => x.route === '9').threshold_s;
  const r9dp = r9.direction_periods.map((d) => ({ ...d, a: d.after.median_s }));
  const r9ok = r9dp.filter((d) => d.a != null && d.a <= thr9).length;
  const r9miss = r9.flipped_15_min_standard[0];
  const thr23 = NM.rows.find((x) => x.route === '23').threshold_s;
  const r23miss = r23.flipped_30_min_standard[0];
  const r177mid = r177.direction_periods.filter((d) => d.period === 'midday').map((d) => d.after.median_mmss);
  const r177am = r177.direction_periods.filter((d) => d.period === 'am_peak').map((d) => d.after.n_departures);
  const WK = f.weekend;
  const dirs = (list, key) => uniq(list.map((d) => d[key])).join(' / ');
  const weekend = ['5', '9'].map((r) => {
    const c = WK.callouts[r];
    const sat = c.schedule_after.saturday;
    const sun = c.schedule_after.sunday;
    return {
      route: r,
      name: R[r].long_name,
      claim: c.claim.text,
      claimUrl: c.claim.url,
      satBefore: dirs(sat, 'median_before_mmss'),
      satAfter: dirs(sat, 'median_after_mmss'),
      sunBefore: dirs(sun, 'median_before_mmss'),
      sunAfter: dirs(sun, 'median_after_mmss'),
      longest: mmss(c.after_longest_gap_s)
    };
  });

  // 4. Route table
  const nearAfter = {};
  for (const x of NM.rows) if (x.date === P.after) (nearAfter[x.route] ||= new Set()).add(x.threshold_s / 60 + '-min');
  const TIER_RANK = ['15-min', '30-min', 'below standard', 'no service on date', 'not scored (express)'];
  const spanMinutes = (r) => {
    const t = (s) => +s.slice(0, 2) * 60 + +s.slice(3, 5);
    return t(r.span_end_after) - t(r.span_start_after);
  };
  const weakest = (r) => {
    if (r.category === 'express') return 'express peak trips: ' + r.express_result_after;
    const where = 'direction ' + r.weakest_direction_after + ', ' + PERIOD[r.weakest_period_after];
    return r.weakest_median_after_s == null ? where + ': no headway (' + r.weakest_note + ')' : where + ', median ' + r.weakest_median_after_mmss;
  };
  const routeRows = f.routes.rows.map((r) => ({
    route: r.route,
    name: r.long_name,
    category: r.category === 'bus' ? 'local' : r.category,
    before: r.tier_before,
    after: r.tier_after,
    change: r.change,
    weakest: weakest(r),
    span: span({ start: r.span_start_after, end: r.span_end_after }) + (r.span_pass_after == null ? ' (not scored)' : r.span_pass_after ? ' (pass)' : ' (fail)'),
    near: nearAfter[r.route] ? [...nearAfter[r.route]].join(', ') + ' near miss' : '',
    k: {
      route: parseInt(r.route, 10) * 2 + (/[a-z]$/.test(r.route) ? 1 : 0),
      name: r.long_name.toLowerCase(),
      category: r.category,
      before: TIER_RANK.indexOf(r.tier_before),
      after: TIER_RANK.indexOf(r.tier_after),
      change: r.change,
      weakest: r.weakest_median_after_s,
      span: spanMinutes(r),
      near: nearAfter[r.route] ? 1 : 0
    }
  }));
  const COLS = [
    ['route', 'Route'],
    ['name', 'Name'],
    ['category', 'Type'],
    ['before', 'Tier before'],
    ['after', 'Tier after'],
    ['change', 'Change'],
    ['weakest', 'Weakest direction and period after'],
    ['span', 'Span after'],
    ['near', 'Near miss']
  ];
  let sortKey = 'route';
  let asc = true;
  function sortBy(k) {
    if (sortKey === k) asc = !asc;
    else {
      sortKey = k;
      asc = true;
    }
  }
  $: view = [...routeRows].sort((x, y) => {
    const a = x.k[sortKey];
    const b = y.k[sortKey];
    if (a == null && b == null) return 0;
    if (a == null) return 1; // a missing value (no headway, not scored) sorts last in both directions
    if (b == null) return -1;
    const c = typeof a === 'string' ? a.localeCompare(b) : a - b;
    return asc ? c : -c;
  });

  // 8. Limits, 9. Method
  const L = f.limits;
  const FEEDS = pd.sources.feeds;
  const CENSUS = pd.sources.census;
  const INPUTS = Object.entries(f.inputs_sha256);
  const GH = 'https://github.com/sr-dotcom/better-bus-baseline';
  const DASH = '–';
</script>

<style>
  :global(body) {
    background: #fff;
  }
  :global(#evidence-main-article),
  :global(#evidence-main-article *) {
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  }
  .page {
    --accent: #0b5cad;
    --ink: #1c2530;
    --muted: #4a5663;
    --line: #d5dbe1;
    --soft: #f3f5f7;
    max-width: 46rem;
    margin: 0 auto;
    padding: 1rem 0 3rem;
    color: var(--ink);
    font-size: 1rem;
    line-height: 1.55;
    overflow-wrap: anywhere;
  }
  :global(h1.title) {
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    font-size: 1.8rem;
    line-height: 1.2;
    font-weight: 700;
    color: #1c2530;
    max-width: 46rem;
    margin: 0.5rem auto 0;
  }
  .page :global(h1) {
    font-size: 1.6rem;
    line-height: 1.2;
    margin: 0.5rem 0 0.5rem;
    color: var(--ink);
  }
  .page :global(h2) {
    font-weight: 700;
    font-size: 1.3rem;
    line-height: 1.25;
    margin: 2.5rem 0 0.5rem;
    padding-top: 0.75rem;
    border-top: 2px solid var(--accent);
    color: var(--ink);
  }
  .page :global(h3) {
    font-weight: 700;
    font-size: 1.05rem;
    margin: 1.25rem 0 0.25rem;
    color: var(--ink);
  }
  .page :global(p),
  .page :global(ul),
  .page :global(ol),
  .page :global(blockquote),
  .page :global(pre) {
    margin: 0.6rem 0;
  }
  .page :global(ul),
  .page :global(ol) {
    padding-left: 1.3rem;
    list-style: revert;
  }
  .page :global(a) {
    color: var(--accent);
    text-decoration: underline;
  }
  .lede {
    font-size: 1.1rem;
    color: var(--muted);
  }
  .contents {
    font-size: 0.95rem;
    columns: 2 14rem;
  }
  .nums {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
    gap: 0.75rem;
    margin: 1rem 0;
  }
  .nums > div {
    border-left: 4px solid var(--accent);
    padding: 0.1rem 0 0.1rem 0.7rem;
  }
  .nums .n {
    display: block;
    font-size: 2.1rem;
    font-weight: 700;
    line-height: 1.1;
    color: var(--accent);
  }
  .nums .l {
    display: block;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .src {
    font-size: 0.85rem;
    color: var(--muted);
  }
  figure {
    margin: 1.25rem 0;
  }
  svg.chart {
    display: block;
    width: 100%;
    max-width: 34rem;
    height: auto;
  }
  svg.chart text {
    fill: var(--ink);
    font-size: 13px;
  }
  svg.chart .val {
    font-size: 16px;
    font-weight: 700;
    text-anchor: middle;
  }
  svg.chart .cat {
    text-anchor: middle;
  }
  svg.chart .before {
    fill: #8b97a3;
  }
  svg.chart .after {
    fill: var(--accent);
  }
  .tablewrap {
    max-width: 100%;
    overflow-x: auto;
    border: 1px solid var(--line);
    margin: 0.75rem 0;
  }
  .page table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.9rem;
  }
  .page th,
  .page td {
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
    overflow-wrap: normal;
    word-break: normal;
  }
  table.routes td,
  table.routes th {
    white-space: nowrap;
  }
  .page th {
    background: var(--soft);
    white-space: nowrap;
  }
  .page th button {
    all: unset;
    cursor: pointer;
    font-weight: 700;
    color: var(--accent);
  }
  .page th button:focus-visible {
    outline: 2px solid var(--accent);
  }
  table.routes {
    min-width: 72rem;
  }
  table.routes th:first-child,
  table.routes td:first-child {
    position: sticky;
    left: 0;
    background: #fff;
    font-weight: 700;
    border-right: 1px solid var(--line);
  }
  table.routes th:first-child {
    background: var(--soft);
  }
  table.plain {
    min-width: 36rem;
  }
  blockquote {
    border-left: 4px solid var(--line);
    padding-left: 0.9rem;
    color: var(--ink);
  }
  blockquote p {
    margin: 0.4rem 0;
  }
  .mover {
    border-left: 4px solid var(--line);
    padding-left: 0.8rem;
    margin: 1rem 0;
  }
  pre {
    background: var(--soft);
    padding: 0.7rem;
    overflow-x: auto;
    font-size: 0.85rem;
    font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
  }
  code,
  .mono {
    font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
    font-size: 0.85em;
    overflow-wrap: anywhere;
  }
  footer {
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
    color: var(--muted);
    font-size: 0.9rem;
  }
</style>

<div class="page">
<p class="lede">{f.question}</p>
<p>A public-data check of the Charlotte Area Transit System (CATS) bus timetable against its own policy, MPTA-04 (formerly MTC-06). It scores the published schedule, not the buses that ran. Version 1 covers one service change.</p>
<ol class="contents">
<li><a href="#headline">Headline numbers</a></li>
<li><a href="#standard">The question and the standard</a></li>
<li><a href="#moved">What Oct 5 moved</a></li>
<li><a href="#routes">All 62 routes</a></li>
<li><a href="#near">Near misses and no morning service</a></li>
<li><a href="#access">Access</a></li>
<li><a href="#otp">On-time context</a></li>
<li><a href="#limits">What public data cannot measure</a></li>
<li><a href="#method">Method and monitoring plan</a></li>
</ol>
<section id="headline">
<h2>1. Headline numbers</h2>
<p>Of the <span data-metric="headline.local_routes">{H.local_routes}</span> local routes, after the Oct 5, 2026 service change (schedule for {H.period.day}, {dateAfter}):</p>
<div class="nums">
<div><span class="n" data-metric="headline.tiers.after.15-min.count">{T.after['15-min'].count}</span><span class="l">at the 15-min standard</span></div>
<div><span class="n" data-metric="headline.tiers.after.30-min.count">{T.after['30-min'].count}</span><span class="l">at the 30-min standard</span></div>
<div><span class="n" data-metric="headline.tiers.after.below standard.count">{T.after['below standard'].count}</span><span class="l">below standard</span></div>
</div>
<p>Before ({H.period.day}, {dateBefore}): <span data-metric="headline.tiers.before.15-min.count">{T.before['15-min'].count}</span> at 15-min, <span data-metric="headline.tiers.before.30-min.count">{T.before['30-min'].count}</span> at 30-min, <span data-metric="headline.tiers.before.below standard.count">{T.before['below standard'].count}</span> below standard and <span data-metric="headline.tiers.before.no service.count">{T.before['no service'].count}</span> with no service on that date (Route {T.before['no service'].routes.join(', ')}, which is new).</p>
<p>Span: <span data-metric="headline.span_local_routes.after.pass.count">{H.span_local_routes.after.pass.count}</span> of {H.local_routes} local routes pass the service span test after the change (before: <span data-metric="headline.span_local_routes.before.pass.count">{H.span_local_routes.before.pass.count}</span>). Express: <span data-metric="headline.express_peak_trips.after.pass.count">{H.express_peak_trips.after.pass.count}</span> of <span data-metric="headline.express_routes">{H.express_routes}</span> express routes pass the peak trip count (before: <span data-metric="headline.express_peak_trips.before.pass.count">{H.express_peak_trips.before.pass.count}</span>).</p>
<figure>
<svg class="chart" viewBox="0 0 {CH.w} {CH.h}" role="img" aria-labelledby="chart-title chart-desc">
<title id="chart-title">Local routes by tier, before and after Oct 5, 2026</title>
<desc id="chart-desc">Grouped bars for {H.local_routes} local routes. {#each TIERS as t}{t.lines.join(' ')}: {t.before} before, {t.after} after. {/each}</desc>
<rect class="before" x="12" y="6" width="14" height="14" />
<text x="32" y="18">Before: {dateBefore}</text>
<rect class="after" x="12" y="28" width="14" height="14" />
<text x="32" y="40">After: {dateAfter}</text>
<line x1="8" x2="352" y1={CH.base} y2={CH.base} stroke="#4a5663" stroke-width="1" />
{#each TIERS as t, i}
<rect class="before" data-series="before" data-tier={t.key} data-value={t.before} x={slotX(i) - CH.bar - CH.gap / 2} y={CH.base - barH(t.before)} width={CH.bar} height={barH(t.before)} />
<text class="val" data-series="before" data-tier={t.key} x={slotX(i) - CH.bar / 2 - CH.gap / 2} y={CH.base - barH(t.before) - 5}>{t.before}</text>
<rect class="after" data-series="after" data-tier={t.key} data-value={t.after} x={slotX(i) + CH.gap / 2} y={CH.base - barH(t.after)} width={CH.bar} height={barH(t.after)} />
<text class="val" data-series="after" data-tier={t.key} x={slotX(i) + CH.bar / 2 + CH.gap / 2} y={CH.base - barH(t.after) - 5}>{t.after}</text>
{#each t.lines as line, j}
<text class="cat" x={slotX(i)} y={CH.base + 18 + j * 16}>{line}</text>
{/each}
{/each}
</svg>
<figcaption class="src">Local routes ({H.local_routes}) by scheduled tier. Data period: weekday {dateBefore} (feed {P.feeds.before}) and weekday {dateAfter} (feed {P.feeds.after}). Source: CATS GTFS schedule feeds, scored in this repository (<a href="{GH}/blob/main/data/findings.json">data/findings.json</a>). Tier means: 15-min, every direction at a median gap of 15 minutes or less in both weekday peaks; 30-min, 30 minutes or less in the AM peak, midday and PM peak; below standard, neither. Express routes are not tiered.</figcaption>
</figure>
<p class="src">This is a schedule audit. A tier describes the published timetable, not delivered service. Limits are in <a href="#limits">section 8</a>.</p>
</section>
<section id="standard">
<h2>2. The question and the standard</h2>
<p>CATS publishes its Transit Service Guidelines as MPTA-04 (formerly MTC-06). The clauses used here are 2.4, 3.3 and 3.7; sections 3.3 and 3.7 were compared with the current text: 3.7 reads the same, and 3.3 has the same definitions and trigger (one typo corrected, one sentence on rail added). Quotes are from the MTC-06 PDF (<a href="{pd.policy.mtc06_url}">MTC-06</a>), word for word. Current text: <a href="{pd.policy.mpta04_url}">MPTA-04</a>.</p>
{#each SECTIONS as s}
<h3>Section {s.id} {s.title} (PDF page {s.page})</h3>
<blockquote>
{#each s.blocks as b}
<p>{b}</p>
{/each}
</blockquote>
{/each}
<p class="src">The policy words its headways as goals ("will strive") and defines no peak hours and no weekend standard. See <a href="#limits">section 8</a>.</p>
</section>
<section id="moved">
<h2>3. What Oct 5 moved</h2>
<p class="src">Data period: weekday {dateBefore} (feed {P.feeds.before}) vs weekday {dateAfter} (feed {P.feeds.after}); weekends as noted. Source: CATS GTFS schedule feeds.</p>
<div class="mover">
<h3>Route 5 {r5.long_name}: up</h3>
<p>From {r5.tier_before} to {r5.tier_after}. {r5.flipped_15_min_standard.length} weekday peak direction-periods moved from failing to passing the 15-minute standard: median gaps of {r5before} became {r5after}. Span {span(r5.span_before)} became {span(r5.span_after)}.</p>
</div>
<div class="mover">
<h3>Route 9 {r9.long_name}: down</h3>
<p>From {r9.tier_before} to {r9.tier_after}, by one direction-period. {r9ok} of {r9dp.length} scored weekday direction-periods have a median gap of {mmss(thr9)} or better. The one that does not is direction {r9miss.direction} in the {PERIOD[r9miss.period]}: median {r9miss.median_after_mmss} (before: {r9miss.median_before_mmss}), {r9miss.n_after} departures, longest gap {mmss(r9miss.max_after_s)}. The 15-minute standard needs every direction in both peaks to pass, so that one decides the tier.</p>
</div>
<div class="mover">
<h3>Route 23 {r23.long_name}: down</h3>
<p>From {r23.tier_before} to {r23.tier_after}. One direction-period flipped: direction {r23miss.direction}, {PERIOD[r23miss.period]}, median {r23miss.median_before_mmss} became {r23miss.median_after_mmss}, which is {r23miss.median_after_s - r23miss.median_before_s} seconds longer and {r23miss.median_after_s - thr23} seconds over the {mmss(thr23)} limit.</p>
</div>
<div class="mover">
<h3>Route 177 {r177.long_name}: new</h3>
<p>No service on {dateBefore}. After: tier {r177.tier_after}, span {span(r177.span_after)}, midday median gap {r177mid.join(' and ')}. AM peak departures by direction: {r177am.join(' and ')}.</p>
</div>
<h3>Weekends: Routes 5 and 9 against CATS published claims</h3>
<p>Weekend headways are reported, never scored: the policy sets no weekend standard. Median gap between departures, 09:00 to 18:00, by direction (shown once when both match).</p>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Route</th><th>CATS claim</th><th>Saturday</th><th>Sunday</th><th>Longest gap after</th></tr></thead>
<tbody>
{#each weekend as w}
<tr><td>{w.route} {w.name}</td><td>{w.claim}</td><td>{w.satBefore} to {w.satAfter}</td><td>{w.sunBefore} to {w.sunAfter}</td><td>{w.longest}</td></tr>
{/each}
</tbody>
</table></div>
<p class="src">Saturday {date(WK.period.saturday.before)} to {date(WK.period.saturday.after)}; Sunday {date(WK.period.sunday.before)} to {date(WK.period.sunday.after)}. Claims: CATS web page "Service Change", retrieved {WK.callouts['5'].claim.retrieved_utc}, <a href="{WK.callouts['5'].claim.url}">source</a>. Schedule source: CATS GTFS feeds.</p>
</section>
<section id="routes">
<h2>4. All {f.routes.rows.length} routes</h2>
<p class="src">Data period: weekday {dateBefore} and {dateAfter}. Source: CATS GTFS schedule feeds (<a href="{GH}/blob/main/data/marts/before_after.csv">before_after.csv</a>, <a href="{GH}/blob/main/data/marts/route_compliance.csv">route_compliance.csv</a>). Select a column heading to sort. Scroll the table sideways on a phone.</p>
<div class="tablewrap">
<table class="routes">
<thead><tr>
{#each COLS as c}
<th aria-sort={sortKey === c[0] ? (asc ? 'ascending' : 'descending') : 'none'}><button type="button" on:click={() => sortBy(c[0])}>{c[1]}{sortKey === c[0] ? (asc ? ' ▲' : ' ▼') : ''}</button></th>
{/each}
</tr></thead>
<tbody>
{#each view as r (r.route)}
<tr data-route={r.route}><td>{r.route}</td><td>{r.name}</td><td>{r.category}</td><td data-col="before">{r.before}</td><td data-col="after">{r.after}</td><td data-col="change">{r.change}</td><td>{r.weakest}</td><td>{r.span}</td><td>{r.near}</td></tr>
{/each}
</tbody>
</table>
</div>
</section>
<section id="near">
<h2>5. Near misses and no morning service</h2>
<h3>Near misses</h3>
<p>{NM.count} readings across the two dates are near misses (rule: {NM.rule}). Status: {NM.status}.</p>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Date</th><th>Route</th><th>Direction</th><th>Period</th><th>Median</th><th>Longest gap</th><th>Limit</th><th>Departures</th></tr></thead>
<tbody>
{#each NM.rows as x}
<tr><td>{date(x.date)}</td><td>{x.route}</td><td>{x.direction}</td><td>{PERIOD[x.period]}</td><td>{x.median_mmss}</td><td>{x.max_mmss}</td><td>{mmss(x.threshold_s)}</td><td>{x.n_departures}</td></tr>
{/each}
</tbody>
</table></div>
<p class="src">Data period: weekday {date(NM.period.dates[0])} and {date(NM.period.dates[1])} (feeds {NM.period.feeds.before} and {NM.period.feeds.after}). Source: CATS GTFS schedule feeds (<a href="{GH}/blob/main/data/marts/route_period_headway.csv">route_period_headway.csv</a>).</p>
<h3>No morning service</h3>
<p><span data-metric="no_morning_service.count">{f.no_morning_service.count}</span> of {f.no_morning_service.route_directions_scored} local route-directions have no headway in the AM peak: {f.no_morning_service.rule}. Gaps are shown, not filled: a route-direction with one trip in the window has no gap to measure.</p>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Route</th><th>Name</th><th>Direction</th><th>AM peak departures</th></tr></thead>
<tbody>
{#each f.no_morning_service.rows as x}
<tr><td>{x.route}</td><td>{x.long_name}</td><td>{x.direction}</td><td>{x.n_am_peak_departures}</td></tr>
{/each}
</tbody>
</table></div>
<p class="src">Data period: weekday {date(f.no_morning_service.period.date)} (feed {f.no_morning_service.period.feed_version}), AM peak {f.no_morning_service.period.am_peak}. Source: CATS GTFS schedule feeds (route_period_headway.csv).</p>
</section>
<section id="access">
<h2>6. Access</h2>
<p>Residents within {EQ.buffer_m} m of 15-min service, before and after. Two rows: the strict tier (routes in the 15-min tier), and the same plus routes with a 15-minute near miss.</p>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Row</th><th>Before: routes</th><th>Before: residents</th><th>After: routes</th><th>After: residents</th><th>Change</th></tr></thead>
<tbody>
{#each EQ.rows as e}
<tr data-equity={e.label}><td>{e.label}</td><td>{e.before.routes.join(', ')}</td><td data-metric="equity.rows.{EQ.rows.indexOf(e)}.before.residents">{num(e.before.residents)}</td><td>{e.after.routes.join(', ')}</td><td data-metric="equity.rows.{EQ.rows.indexOf(e)}.after.residents">{num(e.after.residents)}</td><td data-metric="equity.rows.{EQ.rows.indexOf(e)}.change_residents">{signed(e.change_residents)}</td></tr>
{/each}
</tbody>
</table></div>
<p class="src">Data period: weekday {date(EQ.rows[0].before.date)} and {date(EQ.rows[0].after.date)}. Source: CATS GTFS stops; U.S. Census Bureau ACS {EQ.acs_vintage} total population (B01003) and TIGER/Line {EQ.tiger_vintage} tract shapes (<a href="{GH}/blob/main/data/equity.csv">data/equity.csv</a>).</p>
<h3>Method</h3>
<p>{EQ.method}</p>
<h3>Caveats</h3>
<ul>
{#each EQ.caveats as c}
<li>{c}</li>
{/each}
</ul>
</section>
<section id="otp">
<h2>7. On-time context</h2>
<p>CATS reports bus on-time performance of <span data-metric="otp.value_pct">{OTP.value_pct}</span>% for {monthYear(OTP.month)}, against <span data-metric="otp.same_month_prior_year_pct">{OTP.same_month_prior_year_pct}</span>% a year earlier. This is one figure for all bus routes together ({OTP.scope}).</p>
<p>MPTA-04 (formerly MTC-06) section 3.3 sets a review trigger at {trigger} percent or less, over two service changes, for each bus route. Route-level figure: {OTP.route_level_note}. The trigger cannot be tested from public data, and a system figure above {trigger}% can hide routes below it.</p>
<p>Definition: {OTP.definition}</p>
<p class="src">Data period: {monthYear(OTP.month)}. Source: {OTP.source}, meeting of {date(OTP.meeting_date)}, PDF page {OTP.pdf_page}, <a href="{OTP.url}">packet</a>, retrieved {OTP.retrieved_utc}. It is the agency's own figure and was not verified here. It is context only and feeds no tier.</p>
</section>
<section id="limits">
<h2>8. What public data cannot measure</h2>
<ul>
{#each L.scope as s}
<li>{s}</li>
{/each}
</ul>
<h3>Not measurable from the published schedule</h3>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Item</th><th>Clause</th><th>Why not</th><th>Needs</th></tr></thead>
<tbody>
{#each L.cannot_measure as c}
<tr><td>{c.item}</td><td>{c.clause}</td><td>{c.why}</td><td>{c.needs}</td></tr>
{/each}
</tbody>
</table></div>
<h3>Gaps in the policy</h3>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Gap</th><th>Clauses</th><th>Policy words</th><th>Choice made here</th></tr></thead>
<tbody>
{#each L.policy_gaps as g}
<tr><td>{g.gap}</td><td>{g.clauses}</td><td>"{g.quote}"</td><td>{g.method_choice}</td></tr>
{/each}
</tbody>
</table></div>
</section>
<section id="method">
<h2>9. Method and monitoring plan</h2>
<h3>Reproduce it</h3>
<p>Everything is in the <a href="{GH}">repository</a>. Metrics are defined in <a href="{GH}/blob/main/docs/metrics.md">docs/metrics.md</a>, with hand-calculated answers in <a href="{GH}/blob/main/docs/known-answers.md">docs/known-answers.md</a>.</p>
<pre>uv run python analysis/build.py
uv run python analysis/findings.py
uv run pytest
uv run python analysis/crosscheck.py</pre>
<p>The last command cross-checks the marts against the gtfs-kit library; its report is <a href="{GH}/blob/main/analysis/crosscheck_report.md">analysis/crosscheck_report.md</a>. This page is built from <span class="mono">data/findings.json</span> and the reference files, and a test checks every headline number against it.</p>
<h3>Sources</h3>
<div class="tablewrap"><table class="plain">
<thead><tr><th>File</th><th>Downloaded (UTC)</th><th>SHA-256</th></tr></thead>
<tbody>
{#each FEEDS as s}
<tr><td><a href="{s[1]}">{s[0]}</a></td><td>{s[2]}</td><td class="mono">{s[3]}</td></tr>
{/each}
{#each CENSUS as s}
<tr><td><a href="{s[1].split(' ')[0]}">{s[0]}</a></td><td>{s[3]}</td><td class="mono">{s[4]}</td></tr>
{/each}
</tbody>
</table></div>
<p class="src">Also: CATS bus policy MPTA-04 (<a href="{pd.policy.mpta04_url}">PDF</a>), the MPTA board packet (<a href="{OTP.url}">packet</a>) and the CATS <a href="{pd.policy.mpta04_page_url}">Service Change</a> page. SHA-256 of the data files that produced these numbers:</p>
<ul class="src">
{#each INPUTS as i}
<li><span class="mono">{i[0]}</span> <span class="mono">{i[1]}</span></li>
{/each}
</ul>
<h3>Monitoring plan (proposed)</h3>
<p>Rerun the audit at each service change (February, June and October). Owner: CATS Strategy and Performance Management. The schedule metrics need only the published GTFS feed.</p>
<div class="tablewrap"><table class="plain">
<thead><tr><th>Metric</th><th>Data</th><th>Cadence</th><th>Owner</th></tr></thead>
<tbody>
<tr><td>Tier per local route (15-min, 30-min, below standard)</td><td>Published GTFS</td><td>Each service change</td><td>CATS Strategy and Performance Management</td></tr>
<tr><td>Service span per local route</td><td>Published GTFS</td><td>Each service change</td><td>CATS Strategy and Performance Management</td></tr>
<tr><td>Express peak trip count</td><td>Published GTFS</td><td>Each service change</td><td>CATS Strategy and Performance Management</td></tr>
<tr><td>Near misses and routes with no morning service</td><td>Published GTFS</td><td>Each service change</td><td>CATS Strategy and Performance Management</td></tr>
<tr><td>Residents within {EQ.buffer_m} m of 15-min service</td><td>Published GTFS, ACS, TIGER/Line</td><td>Each service change</td><td>CATS Strategy and Performance Management</td></tr>
</tbody>
</table></div>
<h3>Data needed from inside CATS</h3>
<p>These cannot be measured in public data (section 8). The audit would add them if CATS provides automatic vehicle location (AVL) and automatic passenger count (APC) data:</p>
<ul>
<li>Delivered trips against scheduled trips, from AVL.</li>
<li>Route-level on-time performance, to test the {trigger} percent trigger in section 3.3.</li>
{#each L.cannot_measure.filter((c) => /crowding|ridership/.test(c.item)) as c}
<li>{c.item}: {c.needs}.</li>
{/each}
</ul>
</section>
<footer>
<p>Naga Sathwik Reddy Gona. Built <time datetime={pd.built_utc}>{pd.built_utc}</time>. Repository: <a href="{GH}">{GH}</a>.</p>
</footer>
</div>
