# VARYS — React Security Dashboard

## Plan Handoff Document

**Status**: Design Complete — Ready for Implementation
**Owner**: JT repo
**Parent Design**: See `docs/design/VARYS_SECURITY_SYSTEM.md`
**Date**: 2026-04-03

---

## Overview

A real-time React dashboard for VARYS security operations. Served as a Vite+React SPA alongside the existing Flask dev panel. This is the **visual interface** for the VARYS sentinel — all computation happens server-side.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 19 + TypeScript |
| Build | Vite 6 |
| Styling | Tailwind CSS 4 |
| Charts | Recharts |
| Real-time | WebSocket (native) |
| State | React Context (no Redux needed) |
| HTTP | fetch (no axios needed) |

---

## File Structure

```
guardian_one/varys/dashboard/
├── package.json
├── vite.config.ts            # Proxy /api to Flask:5100
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── src/
│   ├── main.tsx              # React root + providers
│   ├── App.tsx               # Router + layout
│   ├── types/
│   │   └── varys.ts          # TypeScript interfaces for all VARYS data
│   ├── api/
│   │   └── client.ts         # Typed fetch wrapper for VARYS API
│   ├── hooks/
│   │   ├── useAlerts.ts      # Polling/WebSocket alert feed
│   │   ├── useRiskScore.ts   # Composite risk score
│   │   └── useMetrics.ts     # Detection stats
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── StatusBar.tsx # System health indicators
│   │   ├── dashboard/
│   │   │   ├── AlertFeed.tsx       # Live alert stream with severity badges
│   │   │   ├── RiskGauge.tsx       # Radial gauge for composite risk score
│   │   │   ├── DetectionStats.tsx  # Rule hits, anomalies, LLM triages
│   │   │   ├── IncidentTimeline.tsx # Chronological incident view
│   │   │   └── ThreatMap.tsx       # Geographic threat origin plot
│   │   ├── alerts/
│   │   │   ├── AlertDetail.tsx     # Single alert deep dive
│   │   │   ├── AlertActions.tsx    # Acknowledge, escalate, dismiss
│   │   │   └── AlertFilters.tsx    # Severity, source, time range
│   │   ├── rules/
│   │   │   ├── RuleList.tsx        # Sigma rule browser
│   │   │   └── RuleEditor.tsx      # YAML rule viewer
│   │   ├── threat-intel/
│   │   │   ├── IOCSearch.tsx       # Search IOCs (calls Ryzen API)
│   │   │   └── CVEFeed.tsx         # Recent CVE viewer
│   │   └── settings/
│   │       ├── Thresholds.tsx      # Alert threshold configuration
│   │       └── Integrations.tsx    # Connected data sources status
│   └── styles/
│       └── globals.css       # Tailwind base + dark theme
└── public/
    └── favicon.svg
```

---

## API Contract

The dashboard consumes these VARYS API endpoints (served by Flask):

### Alerts
```
GET  /api/varys/alerts?severity=<level>&page=<n>&limit=<n>
GET  /api/varys/alerts/<id>
POST /api/varys/alerts/<id>/acknowledge
POST /api/varys/alerts/<id>/escalate
POST /api/varys/alerts/<id>/dismiss
```

### Metrics
```
GET  /api/varys/metrics/risk-score        # Current composite risk
GET  /api/varys/metrics/detection-stats   # Rule hits, anomalies, triages
GET  /api/varys/metrics/timeline          # Events over time (24h/7d/30d)
```

### Rules
```
GET  /api/varys/rules                     # List all Sigma rules
GET  /api/varys/rules/<id>                # Rule detail (YAML)
```

### Threat Intel (proxied to Ryzen search)
```
GET  /api/varys/threat-intel/search?q=<query>
GET  /api/varys/threat-intel/ioc/<value>
GET  /api/varys/threat-intel/cve?keyword=<term>
```

### WebSocket
```
WS   /ws/varys/alerts                     # Real-time alert stream
```

---

## TypeScript Interfaces

```typescript
interface Alert {
  id: string;
  timestamp: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  source: string;
  title: string;
  description: string;
  mitre_technique?: string;
  affected_host?: string;
  affected_user?: string;
  status: 'new' | 'acknowledged' | 'escalated' | 'dismissed';
  llm_triage?: {
    recommended_action: string;
    confidence: number;
    attack_type: string;
  };
}

interface RiskScore {
  overall: number;        // 0-100
  categories: {
    endpoint: number;
    network: number;
    identity: number;
    data: number;
  };
  trend: 'rising' | 'stable' | 'declining';
  last_updated: string;
}

interface DetectionStats {
  total_events_24h: number;
  rule_hits: number;
  anomalies_detected: number;
  llm_triages: number;
  false_positive_rate: number;
}
```

---

## UI Design Principles

1. **Dark theme by default** — security dashboards are monitored in SOCs
2. **Red/orange/yellow/green severity palette** — instant visual triage
3. **Information density** — dashboard shows everything at a glance, detail views on click
4. **No auto-refresh jank** — WebSocket for new alerts, polling for metrics (30s interval)
5. **Responsive** — works on desktop (primary) and tablet (secondary)

---

## Vite Config

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5100',
      '/ws': {
        target: 'ws://localhost:5100',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../../web/static/varys',
    emptyOutDir: true,
  },
});
```

---

## Build + Deploy

```bash
# Development
cd guardian_one/varys/dashboard
npm install
npm run dev                    # Vite dev server on :5173, proxies to Flask :5100

# Production build
npm run build                  # Outputs to guardian_one/web/static/varys/

# Flask serves the built app
# Add route in guardian_one/web/app.py:
#   @app.route('/varys/dashboard')
#   @app.route('/varys/dashboard/<path:path>')
#   def varys_dashboard(path=''):
#       return send_from_directory('static/varys', 'index.html')
```

---

## Hook Update Required

Update `.claude/hooks/session-start.sh` to install Node.js deps:

```bash
# React dashboard dependencies (only if dashboard exists)
if [ -f "$CLAUDE_PROJECT_DIR/guardian_one/varys/dashboard/package.json" ]; then
  cd "$CLAUDE_PROJECT_DIR/guardian_one/varys/dashboard"
  npm install 2>/dev/null || true
  cd "$CLAUDE_PROJECT_DIR"
fi
```

---

## Session Pickup Instructions

Future Claude Code sessions should:

1. Read this document and the parent design at `docs/design/VARYS_SECURITY_SYSTEM.md`
2. Implement the VARYS API routes (Phase 1) BEFORE building the dashboard
3. Use `npm create vite@latest` to scaffold, then apply the structure above
4. Start with `AlertFeed` + `RiskGauge` components — these provide immediate value
5. Test with mock data first, wire to real API once VARYS agent is operational
6. Run `npm run build` and verify Flask serves the built app at `/varys/dashboard`
