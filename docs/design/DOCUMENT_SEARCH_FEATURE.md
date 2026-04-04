# SMH JTMDAI Website — Document Search Feature
## User Research Plan + Design Specification

**Date:** 2026-03-31
**Project:** Guardian One / SMH JTMDAI Website (New Build)
**Feature:** Document Search
**Primary Users:** Internal team (hospitalists, clinical informaticists, care transition leads, operations)
**Document Types:** PDFs & reports, web pages & articles, legal/compliance docs, mixed content

---

## Part 1: User Research Plan

### 1.1 Research Objectives

The document search feature must serve an internal team working with clinical, regulatory, and operational documents. Research should answer:

1. What documents does the internal team search for most frequently, and in what context?
2. What metadata matters most when filtering results (date, author, document type, clinical category, compliance status)?
3. How do team members currently find documents — and where does that process break down?
4. What does "good enough" search look like vs. what would be transformative?
5. What are the compliance and audit implications of search (access control, logging, versioning)?

### 1.2 Recommended Methods

**Method 1: Stakeholder Interviews (5-8 participants, 1 week)**

Target roles: hospitalist, clinical informaticist, care transition lead, compliance officer, operations lead.

Interview guide:

- Warm-up (5 min): Role, how long on the team, daily workflow overview.
- Context (10 min): "Walk me through the last time you needed to find a specific document. What were you looking for? Where did you go? How long did it take?"
- Deep dive (20 min): Document types used most, current pain points, workarounds, frequency of search, situations where they couldn't find what they needed. Probe on: compliance docs vs. clinical protocols vs. internal reports — are these searched differently?
- Reaction (10 min): Show wireframe concepts (see Part 2). Gather reactions on search bar placement, filter options, result preview.
- Wrap-up (5 min): "If you could change one thing about how you find documents today, what would it be?"

**Method 2: Card Sort (10-15 participants, remote async, 3 days)**

Purpose: Determine the right taxonomy for document categories and filters.

- Open card sort: Give participants 30-40 document titles (mix of PDFs, compliance docs, clinical protocols, meeting notes, articles) and ask them to group and label.
- Output: Category structure for filters and navigation.

**Method 3: Search Log Analysis (if migrating from existing system)**

If any existing document repository or intranet is in use, pull search query logs to understand top searches, zero-result queries, and abandoned searches.

### 1.3 Research Timeline

| Week | Activity | Deliverable |
|------|----------|-------------|
| 1 | Recruit participants, finalize interview guide, set up card sort | Recruitment list, guide, card sort tool |
| 2 | Conduct 5-8 interviews, launch card sort | Raw interview notes, card sort data |
| 3 | Synthesize findings, affinity mapping | Themes report, taxonomy recommendation |
| 3 | Validate findings against design spec, iterate | Updated feature spec |

### 1.4 Success Metrics for the Feature (Define During Research)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Time to find document | < 30 seconds for known-item search | Task-based usability test |
| Search success rate | > 90% of searches return relevant result in top 5 | Search analytics |
| Zero-result rate | < 5% of queries | Search analytics |
| Filter usage rate | > 40% of searches use at least one filter | Search analytics |
| User satisfaction | > 4.0 / 5.0 | Post-launch survey |

---

## Part 2: Document Search Feature Specification

### 2.1 Core Functionality

**Search Types Supported:**

- Full-text search: Search within document content, not just titles and metadata.
- Metadata search: Filter by author, date range, document type, category, compliance status.
- Faceted search: Combine multiple filters with a text query.
- Fuzzy matching: Handle typos and partial terms (critical for clinical terminology like medication names).

**Document Corpus:**

| Type | Examples | Indexing Needs |
|------|----------|---------------|
| PDFs & reports | Discharge protocols, readmission analyses, SHM presentation decks | Full-text OCR extraction, preserve tables |
| Web pages & articles | Published content on the JTMDAI site, blog posts, knowledge base | HTML content indexing, link preservation |
| Legal/compliance docs | BAAs, HIPAA policies, IRB approvals, data use agreements | Version tracking, expiration date metadata, access control |
| Mixed content | Spreadsheets, slide decks, internal memos | Title + metadata indexing, content extraction where possible |

### 2.2 Information Architecture

**Proposed Category Taxonomy (to be validated by card sort):**

- Clinical Protocols & Guidelines
- Compliance & Legal
- Research & Publications
- Operations & Internal
- Financial & Billing
- Training & Onboarding

**Metadata Schema per Document:**

- Title
- Author(s)
- Date created / Date modified
- Document type (PDF, DOCX, web page, XLSX, PPTX)
- Category (from taxonomy above)
- Tags (free-form, e.g., "HRRP", "medication reconciliation", "Epic integration")
- Compliance status (active, expired, under review, N/A)
- Access level (all team, clinical only, leadership only, compliance only)
- Version number

### 2.3 UX Design Recommendations

**Search Bar:**

- Persistent in the site header — available from every page.
- Placeholder text: "Search documents, protocols, and policies..."
- Auto-suggest as user types (recent searches, popular queries, document titles).
- Keyboard shortcut: Cmd/Ctrl + K to focus search from anywhere.

**Results Page Layout:**

- Left sidebar: Faceted filters (category, document type, date range, author, compliance status).
- Main area: Results list with title, snippet showing matched text in context, document type icon, date, author, category tag.
- Right panel (optional, desktop): Document preview on hover or click — show first page of PDF, summary of web page.
- Sorting options: Relevance (default), date (newest first), date (oldest first), alphabetical.

**Result Card Design:**

Each result should display:
- Document type icon (PDF, web, legal shield, spreadsheet)
- Title (linked to document)
- Highlighted snippet showing search term in context (2-3 lines)
- Metadata line: Author | Date modified | Category
- Compliance badge (if applicable): "Active", "Expired", "Under Review"
- Quick actions: Open, Download, Copy link, Add to favorites

**Empty and Error States:**

- Zero results: "No documents found for [query]. Try broadening your search or removing filters." Suggest related terms.
- Error state: "Search is temporarily unavailable. Your documents are safe — please try again shortly."
- Loading state: Skeleton cards to indicate results are loading.

### 2.4 Technical Recommendations

**Search Engine Options (ranked by defensibility and fit):**

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| Elasticsearch / OpenSearch | Industry standard, full-text + fuzzy + faceted, self-hosted = full data control | Requires infrastructure management, heavier setup | Best fit for compliance-sensitive clinical data |
| Typesense | Fast, easy setup, typo tolerance built in, open source | Smaller ecosystem, fewer enterprise features | Good alternative for MVP |
| Algolia | Excellent UX out of the box, hosted | Data leaves your infrastructure, cost scales with volume | Lower regulatory defensibility for PHI-adjacent data |
| PostgreSQL full-text | Already in most stacks, no new dependency | Limited relevance ranking, no fuzzy matching, no facets | Acceptable only for very early prototype |

**Recommended approach:** Elasticsearch or OpenSearch deployed within the same infrastructure boundary as the Guardian One system. This keeps document content within the compliance perimeter and supports HIPAA-aligned access controls.

**Indexing Pipeline:**

1. Document upload triggers content extraction (Apache Tika or similar for PDF/DOCX/PPTX).
2. Extracted text + metadata pushed to search index.
3. Access control tags applied at index time.
4. Index refreshes on document update or new upload.
5. Search queries filtered by user's access level before results are returned.

**Access Control:**

- Role-based access control (RBAC) on search results — users only see documents they have permission to view.
- Audit log: Every search query and document access logged with timestamp and user ID.
- Compliance documents should show version history and expiration warnings.

### 2.5 MVP Scope vs. Full Feature

**MVP (Launch):**

- Full-text search across all indexed documents
- Basic filters: document type, category, date range
- Results list with title, snippet, metadata
- Keyboard shortcut to open search
- RBAC on results

**Phase 2 (Post-Launch, Informed by Research):**

- Auto-suggest and recent searches
- Document preview panel
- Saved searches and favorites
- Advanced filters: compliance status, author, tags
- Search analytics dashboard for admins (top queries, zero-result queries)

**Phase 3 (Future):**

- AI-powered semantic search ("find documents about reducing readmissions for heart failure patients")
- Cross-reference suggestions ("users who viewed this also viewed...")
- Natural language query support via Guardian One's agent layer

---

## Part 3: Research-to-Design Feedback Loop

After conducting the interviews and card sort, update this spec:

1. **Taxonomy:** Replace proposed categories with card sort results.
2. **Filters:** Prioritize filters based on what interview participants said they search by most.
3. **Result display:** Adjust what metadata shows on result cards based on what users said matters most.
4. **MVP scope:** Add or cut features based on frequency and urgency of reported needs.
5. **Access model:** Refine roles and permissions based on actual team structure surfaced in interviews.

---

## Appendix: Interview Recruitment Screener

Target 5-8 participants across these roles:

| Role | Why Include | # Needed |
|------|------------|----------|
| Hospitalist / Physician | Primary clinical document consumer | 1-2 |
| Clinical Informaticist | Heaviest document power user, understands data structures | 1-2 |
| Care Transition Lead | Needs protocols and discharge docs quickly | 1 |
| Compliance Officer | Searches legal/regulatory docs, cares about versioning and audit | 1 |
| Operations / Admin | Searches across all types, represents the broadest use case | 1 |

**Scheduling:** 45-minute sessions, remote (Zoom/Teams), recorded with consent.
