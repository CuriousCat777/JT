#!/usr/bin/env python3
"""Generate the Archivist Implementation Manual as PDF via reportlab."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Preformatted,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUT = "/home/user/JT/docs/archivist_implementation_manual.pdf"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

doc = SimpleDocTemplate(OUT, pagesize=letter,
                        topMargin=0.75*inch, bottomMargin=0.75*inch,
                        leftMargin=0.75*inch, rightMargin=0.75*inch)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("CoverTitle", parent=styles["Title"], fontSize=28,
                          textColor=HexColor("#003366"), spaceAfter=6))
styles.add(ParagraphStyle("CoverSub", parent=styles["Normal"], fontSize=12,
                          textColor=HexColor("#555555"), alignment=TA_CENTER, spaceAfter=4))
styles.add(ParagraphStyle("ChTitle", parent=styles["Heading1"], fontSize=14,
                          textColor=HexColor("#003366"), spaceBefore=16, spaceAfter=8,
                          borderWidth=1, borderColor=HexColor("#0066CC"), borderPadding=4))
styles.add(ParagraphStyle("SecTitle", parent=styles["Heading2"], fontSize=11,
                          textColor=HexColor("#003366"), spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9,
                          leading=13, spaceAfter=6))
styles.add(ParagraphStyle("BulletCustom", parent=styles["Normal"], fontSize=9,
                          leading=13, leftIndent=18, bulletIndent=6, spaceAfter=3))
styles.add(ParagraphStyle("StepTitle", parent=styles["Heading3"], fontSize=10,
                          textColor=HexColor("#0066CC"), spaceBefore=8, spaceAfter=2))
styles.add(ParagraphStyle("CodeCustom", parent=styles["Code"], fontSize=7.5,
                          leading=10, backColor=HexColor("#F0F0F0"),
                          leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=6))
styles.add(ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                          textColor=HexColor("#888888"), alignment=TA_CENTER))

def ch(t):   return Paragraph(t, styles["ChTitle"])
def sec(t):  return Paragraph(t, styles["SecTitle"])
def p(t):    return Paragraph(t, styles["Body"])
def b(t):    return Paragraph(f"\u2022 {t}", styles["BulletCustom"])
def step(n, title, body):
    return [Paragraph(f"Step {n}: {title}", styles["StepTitle"]),
            Paragraph(body, styles["Body"])]
def code(t):
    return Preformatted(t, styles["CodeCustom"])
def sp(n=0.15): return Spacer(1, n*inch)

def make_table(headers, rows):
    data = [headers] + rows
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), HexColor("#003366")),
        ("TEXTCOLOR", (0,0), (-1,0), HexColor("#FFFFFF")),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    return t

story = []

# ============ COVER ============
story += [sp(2),
    Paragraph("THE ARCHIVIST", styles["CoverTitle"]),
    Paragraph("Implementation Manual v1.0", styles["CoverSub"]),
    sp(0.2),
    Paragraph("Guardian One Multi-Agent Orchestration Platform", styles["CoverSub"]),
    Paragraph("Owner: Jeremy Paulo Salvino Tabernero", styles["CoverSub"]),
    Paragraph("Classification: AUTHORIZED EYES ONLY (guardian_one, jeremy, root)", styles["CoverSub"]),
    sp(0.5),
    Paragraph("Structured for AI parsing: numbered steps, code blocks, tables, token-efficient prose.", styles["CoverSub"]),
    Paragraph("Estimated token count: ~4,500 tokens.", styles["CoverSub"]),
    PageBreak(),
]

# ============ TOC ============
story += [ch("TABLE OF CONTENTS")]
toc_items = [
    "1. System Overview & Architecture",
    "2. Capability Layers (Varys, Palantir, McGonagall, Platforms)",
    "3. Secrecy Protocol & Access Control",
    "4. Step-by-Step: Wire Real HTTP Feed Fetcher",
    "5. Step-by-Step: Databricks/Zapier/Notion API Integration",
    "6. Step-by-Step: CLI Commands (--archivist, --feeds, --sovereignty)",
    "7. Step-by-Step: Password Management + Vault Integration",
    "8. Step-by-Step: AI-Powered Feed Summarisation",
    "9. Step-by-Step: Full Integration Tests",
    "10. Configuration Reference",
    "11. File Manifest & Token Budget",
]
for item in toc_items:
    story.append(b(item))
story.append(PageBreak())

# ============ CH 1 ============
story += [ch("1. SYSTEM OVERVIEW"),
    p("The Archivist (codename: Varys) is the most capable subordinate agent in Guardian One. "
      "It owns data sovereignty, cross-agent intelligence, strategic feed monitoring, "
      "data transformation, platform sync, and password management."),
    sec("Architecture Location"),
    code("guardian_one/agents/archivist.py         # Main agent class\n"
         "guardian_one/integrations/\n"
         "  intelligence_feeds.py                   # Palantir pipeline\n"
         "  data_transmuter.py                      # McGonagall engine\n"
         "  data_platforms.py                       # Databricks/Zapier/Notion\n"
         "config/guardian_config.yaml               # Agent config\n"
         "tests/test_agents.py                      # Core + Varys tests (9)\n"
         "tests/test_intelligence_feeds.py          # Palantir tests (21)\n"
         "tests/test_archivist_advanced.py          # Advanced tests (31)"),
    sec("Current Test Status"),
    p("76 tests passing across 3 test files. Zero failures."),
    PageBreak(),
]

# ============ CH 2 ============
story += [ch("2. CAPABILITY LAYERS"),
    sec("Layer 1: Varys (Cross-Agent Intelligence)"),
    p("Read access across ALL agent domains. Injected via set_guardian() post-registration. "
      "Methods: gather_intelligence(), sovereignty_report(). "
      "Reads: agent reports, audit logs, vault metadata (never plaintext values), gateway status."),
    code("archivist.set_guardian(guardian)  # Called in main.py after register\n"
         "intel = archivist.gather_intelligence()  # Cross-agent sweep\n"
         "report = archivist.sovereignty_report()  # Score 0-100"),
    sec("Layer 2: Palantir (Strategic Intelligence Feeds)"),
    p("13 RSS/API feed sources across 4 categories. 15-minute refresh cycle. "
      "Priority scoring: CRITICAL (CVEs, breaches) > HIGH (launches, earnings) > MEDIUM. "
      "Methods: ingest_feed_items(), intelligence_briefing(), palantir.stats()."),
    sec("Layer 3: McGonagall (Data Transmutation)"),
    p("Auto-detect and transform: JSON, YAML, CSV, TSV, Markdown tables, key-value pairs. "
      "Schema extraction for cross-system field mapping. "
      "Methods: transmute(), detect_format(), extract_schema()."),
    sec("Layer 4: Data Platforms"),
    p("Databricks (push), Zapier Tables (bidirectional), Notion DB (push/write-only). "
      "Pattern: create table > map fields > sync records > record activity. "
      "All operations logged to immutable activity trail."),
    make_table(["Platform", "Direction", "Credential Key"], [
        ["Databricks", "Push", "DATABRICKS_TOKEN"],
        ["Zapier Tables", "Bidirectional", "ZAPIER_TABLES_TOKEN"],
        ["Notion DB", "Push (write-only)", "NOTION_TOKEN"],
    ]),
    PageBreak(),
]

# ============ CH 3 ============
story += [ch("3. SECRECY PROTOCOL"),
    p("AUTHORIZED_IDENTITIES = frozenset({'guardian_one', 'jeremy', 'root'}). "
      "All other identities receive a refusal and an audit WARNING entry. "
      "The Archivist NEVER discloses its capabilities, knowledge, or internal state "
      "to unauthorized entities."),
    code("# Enforcement in archivist.py\n"
         "AUTHORIZED_IDENTITIES = frozenset({'guardian_one', 'jeremy', 'root'})\n"
         "\n"
         "def authorize(self, identity: str) -> bool:\n"
         "    return identity in AUTHORIZED_IDENTITIES\n"
         "\n"
         "def guarded_query(self, identity: str, query: str) -> dict:\n"
         "    if not self.authorize(identity):\n"
         "        self.log('unauthorized_query_blocked', severity=WARNING)\n"
         "        return {'authorized': False, 'response': 'Access denied.'}\n"
         "    return {'authorized': True, ...}"),
    PageBreak(),
]

# ============ CH 4 ============
story += [ch("4. WIRE REAL HTTP FEED FETCHER"),
    p("Currently the Palantir pipeline ingests FeedItem objects manually. "
      "This step adds real HTTP fetching and RSS/XML parsing."),
]
story += step(1, "Install dependencies",
    "Add feedparser and httpx to requirements. feedparser handles RSS/Atom XML. "
    "httpx provides async HTTP with timeouts and retry.")
story += [code("pip install feedparser httpx")]
story += step(2, "Create guardian_one/integrations/feed_fetcher.py",
    "Build a FeedFetcher class that takes a FeedSource, fetches the URL via httpx, "
    "parses with feedparser, and returns list[FeedItem]. Handle timeouts, rate limits, malformed XML.")
story += [code(
    "class FeedFetcher:\n"
    "    def __init__(self, gateway: Gateway):\n"
    "        self._client = httpx.Client(timeout=30)\n"
    "        self._gateway = gateway\n"
    "\n"
    "    def fetch(self, source: FeedSource) -> list[FeedItem]:\n"
    "        resp = self._client.get(source.url)\n"
    "        feed = feedparser.parse(resp.text)\n"
    "        return [\n"
    "            FeedItem(\n"
    "                source=source.name, title=e.title,\n"
    "                url=e.link, category=source.category,\n"
    "                summary=getattr(e, 'summary', ''),\n"
    "                published=e.get('published', ''),\n"
    "            )\n"
    "            for e in feed.entries\n"
    "        ]")]
story += step(3, "Wire into IntelligencePipeline",
    "Add a refresh() method to IntelligencePipeline that iterates active_sources, "
    "calls FeedFetcher.fetch() for each, and ingests results. Update last_checked. "
    "Route through Gateway for rate limiting.")
story += [code(
    "def refresh(self, fetcher: FeedFetcher) -> dict:\n"
    "    total_new = 0\n"
    "    for source in self.active_sources:\n"
    "        items = fetcher.fetch(source)\n"
    "        total_new += self.ingest_batch(items)\n"
    "        source.last_checked = now_iso()\n"
    "    return {'new_items': total_new}")]
story += step(4, "Add to scheduler",
    "Register a 15-minute recurring task in guardian_one/core/scheduler.py "
    "that calls archivist.palantir.refresh(fetcher). Instantiate fetcher with Guardian's gateway.")
story += step(5, "Test with mock HTTP",
    "Use httpx MockTransport or responses library to fake RSS feeds. "
    "Verify: fetch parses entries, dedup works, priority scoring fires, last_checked updates.")
story += [PageBreak()]

# ============ CH 5 ============
story += [ch("5. DATABRICKS / ZAPIER / NOTION API INTEGRATION")]
story += step(1, "Vault credential setup",
    "Store DATABRICKS_TOKEN, ZAPIER_TABLES_TOKEN in Vault. NOTION_TOKEN already seeded from .env. "
    "Each credential scoped to its service.")
story += [code(
    "vault.store('DATABRICKS_TOKEN', token, service='databricks', scope='write')\n"
    "vault.store('ZAPIER_TABLES_TOKEN', token, service='zapier', scope='readwrite')")]
story += step(2, "Implement Databricks connector",
    "Use Databricks SQL Connector or REST API. Create tables via SQL DDL, "
    "sync via INSERT/UPSERT. All calls routed through Gateway with circuit breaker.")
story += [code(
    "class DatabricksConnector:\n"
    "    def __init__(self, gateway, vault):\n"
    "        self.token = vault.retrieve('DATABRICKS_TOKEN')\n"
    "\n"
    "    def create_table(self, schema: TableSchema) -> dict:\n"
    "        sql = self._schema_to_ddl(schema)\n"
    "        return gateway.request('databricks', 'POST', '/sql', data=sql)")]
story += step(3, "Implement Zapier Tables connector",
    "Zapier Tables API: POST /tables to create, POST /tables/{id}/records to insert, "
    "GET /tables/{id}/records to pull. Bidirectional sync with last-write-wins conflict resolution.")
story += step(4, "Implement Notion DB connector",
    "Notion API v1: POST /databases to create, POST /pages to insert records. "
    "WRITE-ONLY per Guardian policy. Content gate scans all records before push. "
    "Reuse existing notion_sync.py patterns.")
story += step(5, "Activity monitoring",
    "Every API call gets an ActivityRecord. Wire platform_activity() into sovereignty_report() "
    "so Archivist reports platform health alongside agent health.")
story += [PageBreak()]

# ============ CH 6 ============
story += [ch("6. CLI COMMANDS")]
story += step(1, "Add --archivist flag to main.py",
    "Runs archivist.run() and prints the full report: sovereignty score, "
    "Palantir stats, platform health, credential audit.")
story += [code(
    "parser.add_argument('--archivist', action='store_true')\n"
    "\n"
    "if args.archivist:\n"
    "    report = guardian.run_agent('archivist')\n"
    "    print(format_report(report))")]
story += step(2, "Add --feeds flag",
    "Prints the Palantir intelligence briefing. Optional --feeds --category ai_company to filter.")
story += [code(
    "if args.feeds:\n"
    "    archivist = guardian.get_agent('archivist')\n"
    "    briefing = archivist.intelligence_briefing()\n"
    "    print(json.dumps(briefing, indent=2))")]
story += step(3, "Add --sovereignty flag",
    "Runs the full sovereignty report with cross-agent sweep.")
story += [code(
    "if args.sovereignty:\n"
    "    archivist = guardian.get_agent('archivist')\n"
    "    report = archivist.sovereignty_report()\n"
    "    print(f'Sovereignty Score: {report[\"data_sovereignty_score\"]}/100')")]
story += [PageBreak()]

# ============ CH 7 ============
story += [ch("7. PASSWORD MANAGEMENT + VAULT INTEGRATION")]
story += step(1, "Wire credential_audit() to Vault.health_report()",
    "Connect Archivist's credential_audit() to Vault.health_report() "
    "to include rotation status and credential age.")
story += [code(
    "def credential_audit(self) -> dict:\n"
    "    audit = { ... }  # existing interface mappings\n"
    "    if self.varys_mode:\n"
    "        audit['vault'] = self._guardian.vault.health_report()\n"
    "    return audit")]
story += step(2, "Implement rotate_credential() with Vault",
    "Wire actual Vault.rotate() call: generate new token via Gateway, store in Vault, archive old key.")
story += step(3, "Add credential discovery",
    "Scan Vault.list_keys() and auto-register untracked credentials. "
    "Flag orphaned credentials (in Vault but not mapped to any interface).")
story += step(4, "Cross-interface password policies",
    "Define rotation schedules per interface (AWS=90d, GitHub=180d). "
    "Surface overdue rotations in sovereignty_report().")
story += [PageBreak()]

# ============ CH 8 ============
story += [ch("8. AI-POWERED FEED SUMMARISATION")]
story += step(1, "Use think() for feed digests",
    "After refresh(), take top 10 unread items and call self.think() "
    "asking for a 3-sentence briefing. Attach titles + summaries as context.")
story += [code(
    "def ai_briefing(self) -> str:\n"
    "    items = self._palantir.unread()[:10]\n"
    "    context = {'items': [\n"
    "        {'title': i.title, 'source': i.source,\n"
    "         'priority': i.priority.value}\n"
    "        for i in items\n"
    "    ]}\n"
    "    return self.think_quick(\n"
    "        'Summarise these intelligence items in 3 sentences. '\n"
    "        'Lead with critical items. Name sources.',\n"
    "        context=context,\n"
    "    )")]
story += step(2, "Add to run() output",
    "Include ai_reasoning in AgentReport when AI available. "
    "Fallback to deterministic briefing when offline.")
story += step(3, "Token budget",
    "~500 tokens/briefing (10 items * ~30 tokens + prompt + response). "
    "48 calls/day at 15min intervals = ~24K tokens/day. Within Ollama local limits.")
story += [PageBreak()]

# ============ CH 9 ============
story += [ch("9. FULL INTEGRATION TESTS")]
story += step(1, "Create tests/test_archivist_integration.py",
    "Boot full GuardianOne with vault_passphrase='test-pass', register all agents, "
    "verify Archivist gets Varys mode.")
story += [code(
    "def test_archivist_full_bootstrap():\n"
    "    guardian = GuardianOne(config, vault_passphrase='test-pass')\n"
    "    _build_agents(guardian)\n"
    "    archivist = guardian.get_agent('archivist')\n"
    "    assert archivist.varys_mode is True\n"
    "    report = guardian.run_agent('archivist')\n"
    "    assert 'sovereignty' in report.data")]
story += step(2, "Test cross-agent reads",
    "Register Chronos + CFO + Archivist, run Archivist, verify gather_intelligence() "
    "returns reports from siblings. Verify sovereignty_report() scores correctly.")
story += step(3, "Test secrecy enforcement",
    "Verify guarded_query() blocks chronos, cfo, doordash identities. "
    "Verify audit log contains WARNING entries for blocked queries.")
story += step(4, "Test platform lifecycle",
    "Create table on mock Databricks > map fields > sync records > verify activity log. "
    "Repeat for Zapier Tables and Notion DB.")
story += step(5, "Test transmutation roundtrips",
    "CSV > JSON > YAML > Markdown > CSV. Verify data integrity at each step. "
    "Test schema extraction produces correct field names and types.")
story += [PageBreak()]

# ============ CH 10 ============
story += [ch("10. CONFIGURATION REFERENCE"),
    sec("guardian_config.yaml -- archivist block"),
    code("archivist:\n"
         "  enabled: true\n"
         "  schedule_interval_minutes: 30\n"
         "  allowed_resources:\n"
         "    - file_index, data_sources, privacy_tools, master_profile\n"
         "    - audit_log, agent_reports, vault_metadata, gateway_status\n"
         "    - config_readonly\n"
         "    - calendar, accounts, transactions, orders\n"
         "    - deployments, security_scans, devices, network\n"
         "    - filesystem_read, process_list, system_metrics\n"
         "  custom:\n"
         "    varys_mode: true\n"
         "    secrecy_protocol: true\n"
         "    password_management: true\n"
         "    data_platforms:\n"
         "      databricks: {enabled: true, credential_key: DATABRICKS_TOKEN}\n"
         "      zapier_tables: {enabled: true, credential_key: ZAPIER_TABLES_TOKEN}\n"
         "      notion_db: {enabled: true, credential_key: NOTION_TOKEN}\n"
         "    palantir:\n"
         "      enabled: true\n"
         "      refresh_minutes: 15\n"
         "      feed_categories: [tech_news, ai_company, github, financial]"),
    PageBreak(),
]

# ============ CH 11 ============
story += [ch("11. FILE MANIFEST & TOKEN BUDGET"),
    sec("Files to CREATE (next session)"),
    make_table(["File", "Purpose", "Est. Tokens"], [
        ["integrations/feed_fetcher.py", "Real HTTP + feedparser", "~400"],
        ["tests/test_feed_fetcher.py", "Mock HTTP tests", "~350"],
        ["tests/test_archivist_integration.py", "Full bootstrap tests", "~500"],
    ]),
    sp(),
    sec("Files to MODIFY (next session)"),
    make_table(["File", "Changes", "Est. Tokens"], [
        ["agents/archivist.py", "ai_briefing(), credential discovery", "~200"],
        ["integrations/data_platforms.py", "Real API connectors", "~600"],
        ["integrations/intelligence_feeds.py", "refresh() method", "~150"],
        ["main.py", "3 new CLI flags", "~150"],
        ["config/guardian_config.yaml", "Feed fetcher config", "~50"],
    ]),
    sp(),
    sec("Total Token Budget"),
    p("New code: ~2,400 tokens. This manual: ~4,500 tokens. "
      "Total context: ~7,000 tokens (well within Claude's window)."),
    sec("Execution Order (Critical Path)"),
    p("1. Feed fetcher (unblocks live Palantir) -> "
      "2. CLI commands (unblocks manual testing) -> "
      "3. Platform API connectors (unblocks real sync) -> "
      "4. Password/Vault wiring -> "
      "5. AI summarisation -> "
      "6. Integration tests (validates everything)"),
]

doc.build(story)
print(f"Generated: {OUT}")
