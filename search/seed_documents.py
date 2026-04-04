#!/usr/bin/env python3
"""Seed both Typesense and Meilisearch with sample Guardian One documents.

Usage:
    python seed_documents.py [--typesense] [--meilisearch] [--both]

Requires:
    pip install typesense meilisearch
"""

import argparse
import json
import sys
import time

# ── Sample document corpus ─────────────────────────────────────
DOCUMENTS = [
    {
        "id": "1",
        "title": "Discharge Protocol — Heart Failure",
        "author": "Dr. Sarah Chen",
        "category": "Clinical Protocols & Guidelines",
        "doc_type": "PDF",
        "tags": ["heart failure", "discharge", "HF", "readmission"],
        "compliance_status": "active",
        "access_level": "all_team",
        "content": "This protocol outlines the standardized discharge process for heart failure patients. Key steps include medication reconciliation with emphasis on ACE inhibitors and beta-blockers, patient education using teach-back method, follow-up appointment scheduling within 7 days, and home health referral criteria. Reduces 30-day readmission rate by targeting modifiable risk factors identified during index hospitalization.",
        "date_created": "2025-11-15",
        "date_modified": "2026-02-20",
        "version": 3,
    },
    {
        "id": "2",
        "title": "HIPAA Business Associate Agreement Template",
        "author": "Legal Department",
        "category": "Compliance & Legal",
        "doc_type": "DOCX",
        "tags": ["HIPAA", "BAA", "compliance", "data sharing"],
        "compliance_status": "active",
        "access_level": "compliance_only",
        "content": "Standard Business Associate Agreement for third-party vendors accessing Protected Health Information (PHI). Includes data breach notification requirements within 60 days, minimum necessary standard provisions, de-identification requirements per Safe Harbor method, and annual risk assessment obligations. Approved by General Counsel, effective January 2026.",
        "date_created": "2026-01-10",
        "date_modified": "2026-01-10",
        "version": 1,
    },
    {
        "id": "3",
        "title": "Hospital Readmission Reduction Program (HRRP) Analysis Q4 2025",
        "author": "Dr. James Morton",
        "category": "Research & Publications",
        "doc_type": "PDF",
        "tags": ["HRRP", "readmission", "CMS", "penalty", "quality"],
        "compliance_status": "N/A",
        "access_level": "all_team",
        "content": "Quarterly analysis of HRRP performance metrics. Overall 30-day readmission rate decreased from 18.2% to 15.7% compared to prior quarter. Heart failure readmissions down 22%, pneumonia down 15%, AMI stable. Key interventions: enhanced discharge planning, pharmacist-led medication reconciliation, and post-discharge phone call program. Estimated CMS penalty reduction of $340,000 annually.",
        "date_created": "2026-01-30",
        "date_modified": "2026-02-05",
        "version": 2,
    },
    {
        "id": "4",
        "title": "Epic EHR Integration — Care Transition Module",
        "author": "IT Systems Team",
        "category": "Operations & Internal",
        "doc_type": "PPTX",
        "tags": ["Epic", "EHR", "integration", "care transitions", "ADT"],
        "compliance_status": "under_review",
        "access_level": "all_team",
        "content": "Technical specification for integrating the Guardian One care transition workflow with Epic EHR via FHIR R4 APIs. Covers ADT event subscription, patient matching logic, CCD document parsing, and real-time notification routing. Phase 1 targets admission and discharge events. Phase 2 adds transfer events and outpatient encounters. Requires Epic App Orchard approval.",
        "date_created": "2025-12-01",
        "date_modified": "2026-03-10",
        "version": 4,
    },
    {
        "id": "5",
        "title": "Medication Reconciliation Best Practices",
        "author": "Dr. Angela Rodriguez",
        "category": "Clinical Protocols & Guidelines",
        "doc_type": "PDF",
        "tags": ["medication reconciliation", "patient safety", "pharmacy"],
        "compliance_status": "active",
        "access_level": "clinical_only",
        "content": "Evidence-based guidelines for medication reconciliation at care transitions. Includes step-by-step process for obtaining best possible medication history (BPMH), identifying discrepancies, and communicating changes to patients and providers. Special sections on high-risk medications (anticoagulants, insulin, opioids) and polypharmacy in elderly patients. References Joint Commission NPSG.03.06.01.",
        "date_created": "2025-09-20",
        "date_modified": "2026-01-15",
        "version": 2,
    },
    {
        "id": "6",
        "title": "SHM Converge 2026 — Presentation Deck",
        "author": "Dr. James Morton",
        "category": "Research & Publications",
        "doc_type": "PPTX",
        "tags": ["SHM", "conference", "presentation", "hospital medicine"],
        "compliance_status": "N/A",
        "access_level": "all_team",
        "content": "Slide deck for Society of Hospital Medicine Converge 2026 presentation. Topic: Leveraging AI-Assisted Care Transitions to Reduce Readmissions. Covers Guardian One platform overview, pilot results showing 22% readmission reduction, implementation lessons learned, and future roadmap including predictive risk stratification and automated post-discharge follow-up.",
        "date_created": "2026-02-01",
        "date_modified": "2026-03-15",
        "version": 5,
    },
    {
        "id": "7",
        "title": "IRB Approval — Guardian One Outcomes Study",
        "author": "Research Compliance",
        "category": "Compliance & Legal",
        "doc_type": "PDF",
        "tags": ["IRB", "research", "ethics", "outcomes study"],
        "compliance_status": "active",
        "access_level": "leadership_only",
        "content": "Institutional Review Board approval letter for the prospective outcomes study evaluating Guardian One impact on 30-day readmission rates, patient satisfaction, and care transition quality metrics. Study protocol #2025-GO-0042. Approved for 200-patient enrollment over 12 months. Annual renewal required by December 2026. PI: Dr. James Morton.",
        "date_created": "2025-10-15",
        "date_modified": "2025-10-15",
        "version": 1,
    },
    {
        "id": "8",
        "title": "New Hire Onboarding — Clinical Informaticist",
        "author": "HR Department",
        "category": "Training & Onboarding",
        "doc_type": "DOCX",
        "tags": ["onboarding", "training", "informaticist", "new hire"],
        "compliance_status": "N/A",
        "access_level": "all_team",
        "content": "Onboarding checklist and training plan for new clinical informaticist hires. Week 1: System access provisioning, HIPAA training, Guardian One platform orientation. Week 2: Shadow existing team, Epic training modules. Week 3-4: Hands-on projects with mentor oversight. Includes links to key reference documents, team directory, and meeting schedule.",
        "date_created": "2026-01-05",
        "date_modified": "2026-03-01",
        "version": 3,
    },
    {
        "id": "9",
        "title": "Monthly Financial Report — February 2026",
        "author": "CFO Office",
        "category": "Financial & Billing",
        "doc_type": "XLSX",
        "tags": ["financial", "budget", "revenue", "monthly report"],
        "compliance_status": "N/A",
        "access_level": "leadership_only",
        "content": "February 2026 financial summary. Total revenue: $2.4M. Operating expenses: $1.8M. Net margin: 25%. Key variances: consulting revenue exceeded forecast by 12%, travel costs under budget by 8%. Guardian One platform licensing revenue: $180K (up 15% MoM). Pending: Q1 billing reconciliation for three hospital system clients.",
        "date_created": "2026-03-05",
        "date_modified": "2026-03-05",
        "version": 1,
    },
    {
        "id": "10",
        "title": "Data Use Agreement — State Health Department",
        "author": "Legal Department",
        "category": "Compliance & Legal",
        "doc_type": "PDF",
        "tags": ["DUA", "data sharing", "state health", "public health"],
        "compliance_status": "expired",
        "access_level": "compliance_only",
        "content": "Data Use Agreement with the State Department of Health for sharing de-identified readmission data for public health surveillance. Covers data elements, permitted uses, re-identification prohibitions, data destruction timeline (90 days post-analysis), and breach notification procedures. Agreement expired March 1, 2026 — renewal pending legal review.",
        "date_created": "2025-03-01",
        "date_modified": "2025-03-01",
        "version": 1,
    },
]


def seed_typesense(host: str = "http://localhost:8108", api_key: str = "guardian-search-key"):
    """Create collection and index documents in Typesense."""
    import typesense

    from urllib.parse import urlparse
    parsed = urlparse(host if "://" in host else f"http://{host}")
    ts_host = parsed.hostname or "localhost"
    ts_port = str(parsed.port or 8108)
    ts_protocol = parsed.scheme or "http"

    client = typesense.Client({
        "api_key": api_key,
        "nodes": [{"host": ts_host, "port": ts_port, "protocol": ts_protocol}],
        "connection_timeout_seconds": 10,
    })

    schema = {
        "name": "documents",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "author", "type": "string", "facet": True},
            {"name": "category", "type": "string", "facet": True},
            {"name": "doc_type", "type": "string", "facet": True},
            {"name": "tags", "type": "string[]", "facet": True},
            {"name": "compliance_status", "type": "string", "facet": True},
            {"name": "access_level", "type": "string", "facet": True},
            {"name": "content", "type": "string"},
            {"name": "date_created", "type": "string", "sort": True},
            {"name": "date_modified", "type": "string", "sort": True},
            {"name": "version", "type": "int32"},
        ],
        "default_sorting_field": "version",
    }

    # Drop existing collection if present
    try:
        client.collections["documents"].delete()
        print("[Typesense] Dropped existing 'documents' collection.")
    except Exception:
        pass

    client.collections.create(schema)
    print("[Typesense] Created 'documents' collection.")

    for doc in DOCUMENTS:
        client.collections["documents"].documents.create(doc)
    print(f"[Typesense] Indexed {len(DOCUMENTS)} documents.")


def seed_meilisearch(host: str = "http://localhost:7700", api_key: str = "guardian-meili-key"):
    """Create index and add documents in Meilisearch."""
    import meilisearch

    client = meilisearch.Client(host, api_key)

    # Delete existing index if present
    try:
        client.index("documents").delete()
        print("[Meilisearch] Deleted existing 'documents' index.")
    except Exception:
        pass

    time.sleep(1)

    index = client.create_index("documents", {"primaryKey": "id"})
    print("[Meilisearch] Created 'documents' index.")

    # Wait for index to be ready
    time.sleep(2)

    idx = client.index("documents")

    # Configure searchable and filterable attributes
    idx.update_searchable_attributes(["title", "content", "author", "tags"])
    idx.update_filterable_attributes(["category", "doc_type", "compliance_status", "access_level", "author", "date_created", "date_modified"])
    idx.update_sortable_attributes(["date_created", "date_modified", "title"])
    idx.update_displayed_attributes(["id", "title", "author", "category", "doc_type", "tags", "compliance_status", "access_level", "content", "date_created", "date_modified", "version"])

    # Add documents
    task = idx.add_documents(DOCUMENTS)
    print(f"[Meilisearch] Indexed {len(DOCUMENTS)} documents. Task UID: {task.task_uid}")
    print("[Meilisearch] Waiting for indexing to complete...")

    # Wait for task completion
    client.wait_for_task(task.task_uid, timeout_in_ms=30000)
    print("[Meilisearch] Indexing complete.")


def main():
    parser = argparse.ArgumentParser(description="Seed search engines with sample documents")
    parser.add_argument("--typesense", action="store_true", help="Seed Typesense only")
    parser.add_argument("--meilisearch", action="store_true", help="Seed Meilisearch only")
    parser.add_argument("--both", action="store_true", help="Seed both engines (default)")
    args = parser.parse_args()

    do_both = args.both or (not args.typesense and not args.meilisearch)

    if args.typesense or do_both:
        try:
            seed_typesense()
        except Exception as e:
            print(f"[Typesense] Error: {e}", file=sys.stderr)
            if not do_both:
                sys.exit(1)

    if args.meilisearch or do_both:
        try:
            seed_meilisearch()
        except Exception as e:
            print(f"[Meilisearch] Error: {e}", file=sys.stderr)
            if not do_both:
                sys.exit(1)


if __name__ == "__main__":
    main()
