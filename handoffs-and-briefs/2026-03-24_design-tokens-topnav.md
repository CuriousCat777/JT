# Handoff: Design Tokens + Global TopNav

**Date:** 2026-03-24
**Branch:** (prior session — files to be merged)
**Status:** Delivered, 903 tests pass, zero regressions

---

## Deliverables

### New: `guardian_one/web/static/tokens.css`
- 65+ CSS custom properties in the `--g1-*` namespace (Sentinel Cartography dark palette)
- Surface hierarchy, semantic colors, typography, radii, shadows, transitions
- Global nav bar component (`.g1-topnav`) with ARIA roles
- Shared button/card/badge classes
- `focus-visible` outlines and dark scrollbar styling

### Updated: `panel.html`
- `:root` variables now alias the shared `--g1-*` tokens (dark theme)
- `<link>` to `tokens.css` added
- Global topnav inserted with `aria-current="page"` on Command Center
- Map overlay background fixed from white to dark
- Grid heights adjusted for the new topnav

### Updated: `chat.html`
- All 30+ hardcoded hex values replaced with `var(--g1-*)` tokens
- Global topnav added with `aria-current="page"` on Chat
- ARIA attributes: `role="log"`, `aria-live="polite"`, `aria-label`, `aria-describedby`
- Screen-reader-only label for input field
- `focus-visible` style on toggle switch
- Removed inline-style nav link (now in topnav)

---

## Test Results
- **903 tests pass, zero regressions**
