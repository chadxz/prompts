"""Shared Night Watch visual system for the report and evidence pages."""

REPORT_CSS = """
:root {
  color-scheme: dark;
  --bg: #0d0d0f; --panel: #151518; --ink: #eee8df; --muted: #b4ada7;
  --line: #393335; --accent: #ed9c96; --blood: #992d36; --gold: #dfb47c;
  --serif: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  --body: "Avenir Next", "Segoe UI", sans-serif;
  --mono: "SFMono-Regular", Consolas, monospace;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.7 var(--body); }
body::before { content: ""; position: fixed; inset: 0; pointer-events: none;
  background: linear-gradient(90deg, transparent 49.9%, #ffffff03 50%,
    transparent 50.1%); background-size: 128px 100%; z-index: -1; }
a { color: var(--accent); text-decoration-thickness: 1px;
  text-underline-offset: 4px; overflow-wrap: anywhere; }
a:hover { color: #fff; }
:focus-visible { outline: 2px solid var(--gold); outline-offset: 6px; }
.skip-link { position: fixed; left: 20px; top: -100px; z-index: 10;
  padding: 12px 20px; background: var(--ink); color: var(--bg); }
.skip-link:focus { top: 16px; }
.shell { max-width: 1180px; margin: auto; padding: 0 44px 64px; }
.masthead { display: flex; justify-content: space-between; align-items: center;
  gap: 20px; min-height: 92px; border-bottom: 1px solid var(--line);
  font: 11px/1.6 var(--mono); text-transform: uppercase; letter-spacing: .15em; }
.masthead .edition { color: var(--muted); text-align: right; }
.brand { display: flex; align-items: center; gap: 16px; }
.brand-mark { display: grid; place-items: center; width: 38px; height: 38px;
  border: 1px solid var(--blood); color: var(--accent); letter-spacing: 0; }
.hero { position: relative; display: grid; grid-template-columns: 1.6fr 1fr;
  gap: 20px; align-items: center; padding: 78px 0 52px; }
.hero-content { position: relative; z-index: 1; }
.eyebrow, .work-kicker, .tag, .section-no {
  font: 11px/1.6 var(--mono); text-transform: uppercase; letter-spacing: .15em;
  color: var(--muted); }
.eyebrow { color: var(--accent); }
h1, h2, h3, h4, p { margin-top: 0; }
h1, h2, h3 { font-family: var(--serif); font-weight: 400; line-height: 1.1; }
h1 { margin: 20px -80px 24px 0; font-size: clamp(46px, 5.8vw, 78px);
  letter-spacing: -.05em; }
h1 span { color: var(--accent); }
.lede { max-width: 630px; margin-bottom: 0; color: #d0c7be; font-size: 17px; }
.eclipse { width: 100%; max-width: 380px; justify-self: end; }
.metric-strip { display: grid; grid-template-columns: repeat(4, 1fr);
  border-top: 1px solid var(--blood); border-bottom: 1px solid var(--line);
  margin-bottom: 30px; }
.metric { padding: 24px 24px 22px; border-right: 1px solid var(--line); }
.metric:first-child { padding-left: 0; }
.metric:last-child { border: 0; }
.metric strong { display: block; font: 42px/1.2 var(--serif); color: var(--ink); }
.metric span { display: block; margin-top: 8px; color: var(--muted);
  font: 11px/1.6 var(--mono); }
.sticky-nav { display: flex; flex-wrap: wrap; gap: 12px 28px;
  padding: 0 0 28px; border-bottom: 1px solid var(--line);
  font: 11px/1.6 var(--mono); text-transform: uppercase; letter-spacing: .08em; }
.sticky-nav a { color: var(--muted); text-decoration: none; }
.sticky-nav a:hover { color: var(--accent); }
section { margin-top: 56px; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between;
  gap: 20px; margin-bottom: 24px; }
.section-heading h2 { margin: 0; font-size: 36px; letter-spacing: -.025em; }
.section-heading .section-no { margin-right: 14px; color: var(--accent); }
.tag { flex-shrink: 0; }
.discussion-card { border-left: 2px solid var(--blood); background: var(--panel);
  padding: 30px 34px; position: relative; }
.discussion-card h3 { font-size: 29px; max-width: 760px; margin: 12px 0 18px; }
.discussion-card p { color: #cfc7c1; }
.discussion-badge { font: 11px var(--mono); color: var(--gold); }
.body-grid { display: grid; gap: 0; }
.body-card { display: grid; grid-template-columns: 70px 1fr;
  padding: 32px 0; border-top: 1px solid var(--line); position: relative; }
.body-card:last-child { border-bottom: 1px solid var(--line); }
.body-index { color: var(--blood); font: 30px/1 var(--serif); padding-top: 8px; }
.work-kicker { margin-bottom: 10px; }
.body-card h3 { font-size: 32px; max-width: 850px; margin-bottom: 16px; }
.body-card p { max-width: 870px; color: #d0c7bf; }
.proof-line { font-size: 13px; color: var(--muted) !important;
  border-left: 1px solid var(--line); padding-left: 16px; }
.evidence-links { display: flex; gap: 10px 24px; flex-wrap: wrap;
  font: 12px/1.6 var(--mono); margin-top: 16px; }
.evidence-link { display: inline-block; }
.demo-ribbon { color: var(--gold); position: absolute; right: 0; top: 8px;
  font: 10px var(--mono); text-transform: uppercase; letter-spacing: .1em; }
.demo-line { color: var(--gold) !important; font-size: 14px; }
.lowlight-grid, .highlight-grid { display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.lowlight-card, .highlight-card { padding: 24px; border: 1px solid var(--line);
  background: var(--panel); min-width: 0; }
.lowlight-card h4, .highlight-card h4 { font-size: 17px; font-weight: 600;
  line-height: 1.5; margin-bottom: 12px; }
.lowlight-card p, .highlight-card p, .highlight-card li { color: #c7bfb8;
  font-size: 14px; }
.highlight-head { display: flex; flex-wrap: wrap; gap: 12px;
  justify-content: space-between; }
.highlight-meta { font: 11px var(--mono); color: var(--muted); }
.mute-button { cursor: pointer; font: 10px var(--mono); color: var(--muted);
  background: none; border: 1px solid var(--line); padding: 8px; }
.mute-button:hover { border-color: var(--accent); color: var(--ink); }
.archive-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px; background: var(--line); border: 1px solid var(--line); margin-bottom: 24px; }
.archive-links a { padding: 18px; background: var(--panel); font: 12px/1.6 var(--mono); }
details { border: 1px solid var(--line); padding: 18px 22px; }
summary { cursor: pointer; font: 12px/1.6 var(--mono); color: var(--ink); }
.evidence-panel { margin-top: 24px; }
.table-wrap { overflow-x: auto; margin-top: 16px; }
.metric-table { width: 100%; border-collapse: collapse; text-align: left;
  font-size: 13px; min-width: 620px; }
.metric-table th { font: 10px/1.6 var(--mono); color: var(--muted);
  text-transform: uppercase; letter-spacing: .06em; }
.metric-table th, .metric-table td { padding: 12px 14px;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.metric-table tbody tr:hover { background: #ffffff03; }
.metric-table caption { text-align: left; font: 23px var(--serif); padding-bottom: 16px; }
.table-section { margin-bottom: 28px; }
.method-list { padding: 0; list-style: none; display: grid;
  grid-template-columns: 1fr 1fr; gap: 18px 36px; }
.method-list li { padding-top: 14px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 12px; }
.footer { display: flex; flex-wrap: wrap; justify-content: space-between;
  gap: 12px; margin-top: 48px; padding-top: 22px; border-top: 1px solid var(--blood);
  color: var(--muted); font: 10px/1.6 var(--mono); }
.detail-hero { padding: 56px 0 24px; border-bottom: 1px solid var(--blood); }
.detail-hero h1 { margin-right: 0; font-size: clamp(38px, 5vw, 64px); }
.detail-hero p { max-width: 760px; color: var(--muted); }
.mute-feedback { display: block; color: var(--gold); font-size: 12px; min-height: 24px; }
@media (max-width: 760px) {
  .shell { padding: 0 22px 42px; }
  .masthead { min-height: 78px; font-size: 9px; letter-spacing: .07em; }
  .brand { gap: 10px; } .brand-mark { width: 30px; height: 30px; }
  .hero { grid-template-columns: 1fr; padding: 46px 0 30px; }
  .eclipse { position: absolute; right: -8px; top: 22px; width: 220px; opacity: .24; }
  h1 { margin-right: 0; font-size: 54px; max-width: 500px; }
  .lede { font-size: 16px; }
  .metric-strip { grid-template-columns: 1fr 1fr; }
  .metric { padding: 18px 14px !important; }
  .metric:nth-child(2) { border-right: 0; }
  .metric:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .metric strong { font-size: 36px; }
  .sticky-nav { gap: 14px 20px; }
  section { margin-top: 40px; }
  .section-heading { display: block; }
  .section-heading h2 { font-size: 31px; margin-bottom: 8px; }
  .discussion-card { padding: 22px; }
  .body-card { grid-template-columns: 36px 1fr; padding: 26px 0; }
  .body-index { font-size: 24px; } .body-card h3 { font-size: 28px; }
  .lowlight-grid, .highlight-grid, .method-list { grid-template-columns: 1fr; }
  .archive-links { grid-template-columns: 1fr 1fr; }
  .tag { font-size: 10px; }
}
@media (max-width: 370px) {
  .shell { padding-left: 16px; padding-right: 16px; }
  h1 { font-size: 46px; }
  .edition { max-width: 120px; }
  .brand > span:last-child { max-width: 110px; }
  .archive-links { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""
