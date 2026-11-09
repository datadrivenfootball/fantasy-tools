# JEG-1586 group B (part 1): stale harnesses and anchors after the JEG-1539 shell move (2026-11-09)

No product or published-number change. Each assertion changed was stale (the rule it pinned was changed by Jeremy or by an
earlier ticket), not a code defect.

- `test_v2_phone_layout_collapse_render`, `test_v2_phone_safe_area_render`, `test_v2_phone_target_size_render`: they served
  `dist/` and opened `v2/` (the JEG-1539 redirect stub, so `#v2Show` and the tab elements were null). They now use
  `tests._dist_server.serve()` and open the build-only shell at `/v2-app.html`, as #1386 did for six other harnesses.
- `test_v2_states_render` guard: the mutation anchor (the hide-every-tab line in v2.js) grew with Find, Waivers, Home and
  Simplified. The anchor now matches v2.js; the guard still requires the render checks to catch the mutation.
- `test_v2_manifesto_render`: the landing tab is the Value chart (Jeremy, 2026-10-25, JEG-1106; the test still said Trade
  targets, 2026-10-08). The menu has no single "Writing" tab since JEG-1106; it links to Writing sections, so the check is
  one Manifesto entry at `#writing/manifesto` among the Writing entries. The landing mutation anchor follows v2.js.
- `test_v2_assist` and `test_v2_assist_render`: the footer link is relative (`connect/`) since JEG-1539, so it is no longer
  the absolute CONNECT_URL / contains `/connect/`.
- `test_espn_zeroed_staleness`: the built `dist/modules/dashboard.html` has `{{DDF_SITE_URL}}` and
  `{{DDF_GITHUB_REPOSITORY}}` filled by `sync_dashboard_artifacts.module_dashboard_html`; the copy must equal the source
  with exactly those filled.

Still open in group B: `live_page_synthetic` (its tab-list expectations predate the root pages), `v2_weight`,
`v2_group_weight`, `v2_player_tags`, `v2_values_math_tip` (60 s wait; `v2_disagree` fixed in #1386).
