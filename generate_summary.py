#!/usr/bin/env python3
"""Generate PDF + TXT summary of the Amidala scaffold project, then zip them."""

import os
import zipfile
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Preformatted
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

BASE = "/home/user/JT/amidala_company"
OUT_DIR = "/home/user/JT"


# ── Collect all source files ──────────────────────────────────────────
def collect_files():
    """Walk the project tree and return list of (rel_path, content)."""
    results = []
    skip = {".venv", "__pycache__", ".git", "amidala.db"}
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in sorted(dirs) if d not in skip]
        for f in sorted(files):
            if f.endswith((".pyc", ".pyo", ".db")):
                continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, BASE)
            try:
                content = open(fp, "r", encoding="utf-8").read()
            except Exception:
                content = "(binary or unreadable)"
            results.append((rel, content))
    return results


# ── Notepad (TXT) ────────────────────────────────────────────────────
def generate_txt(files):
    lines = []
    lines.append("=" * 72)
    lines.append("  AMIDALA COMPANY SCAFFOLD — CODE PRESENTATION SUMMARY")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  Author: drjeremytabernero.com")
    lines.append("=" * 72)
    lines.append("")

    # Overview
    lines.append("PROJECT OVERVIEW")
    lines.append("-" * 40)
    lines.append("A deployable consulting-company website scaffold built with:")
    lines.append("  - FastAPI (Python async web framework)")
    lines.append("  - SQLAlchemy (ORM / database layer)")
    lines.append("  - Pydantic Settings (env-based configuration)")
    lines.append("  - Jinja2 (HTML templating)")
    lines.append("  - SQLite (default database, swappable)")
    lines.append("  - Stripe (payment placeholder)")
    lines.append("")

    # Architecture
    lines.append("ARCHITECTURE")
    lines.append("-" * 40)
    lines.append("Routers:  /contact, /booking, /payment, /admin")
    lines.append("Models:   Lead, BookingRequest (SQLAlchemy)")
    lines.append("Auth:     Cookie-based admin sessions, constant-time password compare")
    lines.append("Email:    Optional SMTP (no-op if unconfigured)")
    lines.append("Debug:    debug_preview.py (dry-run + live /debug endpoint)")
    lines.append("")

    # Routes table
    lines.append("ROUTES")
    lines.append("-" * 40)
    routes = [
        ("GET",  "/",                "Homepage"),
        ("GET",  "/contact/",        "Contact form"),
        ("POST", "/contact/",        "Submit contact"),
        ("GET",  "/booking/",        "Booking form"),
        ("POST", "/booking/",        "Submit booking"),
        ("GET",  "/payment/",        "Payment page (Stripe placeholder)"),
        ("GET",  "/payment/success", "Payment success"),
        ("GET",  "/payment/cancel",  "Payment cancelled"),
        ("GET",  "/admin/login",     "Admin login form"),
        ("POST", "/admin/login",     "Admin authenticate"),
        ("GET",  "/admin/dashboard", "Admin dashboard (protected)"),
        ("GET",  "/admin/logout",    "Admin logout"),
    ]
    for method, path, desc in routes:
        lines.append(f"  {method:6s} {path:25s} {desc}")
    lines.append("")

    # Bug fixes applied
    lines.append("BUGS FIXED FROM ORIGINAL CODE")
    lines.append("-" * 40)
    fixes = [
        ("CRITICAL", "app/init.py -> app/__init__.py (missing dunder)"),
        ("CRITICAL", "tablename -> __tablename__ in SQLAlchemy models"),
        ("CRITICAL", "No indentation in Settings class body (SyntaxError)"),
        ("CRITICAL", "No indentation in get_db() body (SyntaxError)"),
        ("WARNING",  "README.md unclosed markdown code block"),
        ("SECURITY", "Admin password hardcoded in .env.example"),
        ("MISSING",  "app/main.py entry point did not exist"),
        ("MISSING",  ".gitignore not present"),
        ("MISSING",  "templates/ directory not created"),
    ]
    for sev, desc in fixes:
        lines.append(f"  [{sev:8s}] {desc}")
    lines.append("")

    # Dependencies
    lines.append("DEPENDENCIES (requirements.txt)")
    lines.append("-" * 40)
    lines.append("  fastapi==0.115.5")
    lines.append("  uvicorn[standard]==0.32.0")
    lines.append("  jinja2==3.1.4")
    lines.append("  python-multipart==0.0.12")
    lines.append("  pydantic==2.9.2")
    lines.append("  pydantic-settings==2.6.1")
    lines.append("  SQLAlchemy==2.0.36")
    lines.append("  python-dotenv==1.0.1")
    lines.append("")

    # File inventory
    lines.append("FILE INVENTORY")
    lines.append("-" * 40)
    for rel, content in files:
        size = len(content.encode("utf-8"))
        lines.append(f"  {rel:50s} ({size:>6,} bytes)")
    lines.append(f"  {'TOTAL':50s} {len(files)} files")
    lines.append("")

    # Full source code
    lines.append("=" * 72)
    lines.append("  FULL SOURCE CODE LISTING")
    lines.append("=" * 72)
    for rel, content in files:
        lines.append("")
        lines.append(f"{'─' * 72}")
        lines.append(f"FILE: {rel}")
        lines.append(f"{'─' * 72}")
        if content.strip():
            lines.append(content.rstrip())
        else:
            lines.append("(empty file)")
        lines.append("")

    lines.append("=" * 72)
    lines.append("  END OF CODE PRESENTATION SUMMARY")
    lines.append("=" * 72)

    txt_path = os.path.join(OUT_DIR, "amidala_code_summary.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"TXT created: {txt_path} ({os.path.getsize(txt_path):,} bytes)")
    return txt_path


# ── PDF ───────────────────────────────────────────────────────────────
def generate_pdf(files):
    pdf_path = os.path.join(OUT_DIR, "amidala_code_summary.pdf")
    doc = SimpleDocTemplate(
        pdf_path, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=22, spaceAfter=6, textColor=HexColor("#222222"),
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=11, textColor=HexColor("#666666"), alignment=TA_CENTER,
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "SectionHead", parent=styles["Heading2"],
        fontSize=14, spaceBefore=16, spaceAfter=8,
        textColor=HexColor("#333333"),
    )
    body_style = ParagraphStyle(
        "BodyText2", parent=styles["BodyText"],
        fontSize=10, leading=14,
    )
    code_style = ParagraphStyle(
        "CodeBlock", parent=styles["Code"],
        fontSize=7.5, leading=9.5, leftIndent=12,
        fontName="Courier", backColor=HexColor("#f5f5f5"),
        borderColor=HexColor("#dddddd"), borderWidth=0.5,
        borderPadding=6, spaceBefore=4, spaceAfter=8,
    )
    file_header_style = ParagraphStyle(
        "FileHeader", parent=styles["Heading3"],
        fontSize=10, spaceBefore=14, spaceAfter=4,
        textColor=HexColor("#0055aa"), fontName="Courier-Bold",
    )

    story = []

    # Title page
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("Amidala Company Scaffold", title_style))
    story.append(Paragraph("Code Presentation Summary", subtitle_style))
    story.append(Paragraph(
        f"drjeremytabernero.com &mdash; Generated {datetime.now().strftime('%Y-%m-%d')}",
        subtitle_style
    ))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(
        "A deployable consulting-company website scaffold with contact intake, "
        "booking requests, Stripe payment placeholder, admin dashboard, "
        "and legal template pack.",
        body_style
    ))
    story.append(PageBreak())

    # Architecture overview
    story.append(Paragraph("Architecture Overview", heading_style))
    arch_items = [
        "<b>Framework:</b> FastAPI (Python async web framework)",
        "<b>Database:</b> SQLAlchemy ORM with SQLite (swappable)",
        "<b>Config:</b> Pydantic Settings loading from .env",
        "<b>Templates:</b> Jinja2 HTML templating",
        "<b>Auth:</b> Cookie-based admin sessions, constant-time password compare",
        "<b>Email:</b> Optional SMTP notifier (no-op if unconfigured)",
        "<b>Payment:</b> Stripe placeholder (add keys to activate)",
        "<b>Debug:</b> Protected preview tool (debug_preview.py)",
    ]
    for item in arch_items:
        story.append(Paragraph(f"&bull; {item}", body_style))
    story.append(Spacer(1, 0.3*inch))

    # Routes
    story.append(Paragraph("API Routes", heading_style))
    route_data = [
        ["Method", "Path", "Description"],
        ["GET",  "/",                "Homepage"],
        ["GET",  "/contact/",        "Contact form"],
        ["POST", "/contact/",        "Submit contact lead"],
        ["GET",  "/booking/",        "Booking form"],
        ["POST", "/booking/",        "Submit booking request"],
        ["GET",  "/payment/",        "Payment page"],
        ["GET",  "/payment/success", "Payment success callback"],
        ["GET",  "/payment/cancel",  "Payment cancel callback"],
        ["GET",  "/admin/login",     "Admin login form"],
        ["POST", "/admin/login",     "Admin authenticate"],
        ["GET",  "/admin/dashboard", "Dashboard (protected)"],
        ["GET",  "/admin/logout",    "Admin logout"],
    ]
    t = Table(route_data, colWidths=[0.7*inch, 2*inch, 3*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f9f9f9"), HexColor("#ffffff")]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*inch))

    # Bugs fixed
    story.append(Paragraph("Bugs Fixed from Original Code", heading_style))
    fix_data = [
        ["Severity", "Issue"],
        ["CRITICAL", "app/init.py should be app/__init__.py"],
        ["CRITICAL", "tablename should be __tablename__ in models"],
        ["CRITICAL", "Settings class body had no indentation"],
        ["CRITICAL", "get_db() function body had no indentation"],
        ["WARNING",  "README.md unclosed markdown code block"],
        ["SECURITY", "Admin password hardcoded in .env.example"],
        ["MISSING",  "app/main.py entry point did not exist"],
        ["MISSING",  ".gitignore not present"],
        ["MISSING",  "templates/ directory not created"],
    ]
    ft = Table(fix_data, colWidths=[1.2*inch, 5*inch])
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f9f9f9"), HexColor("#ffffff")]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ft)
    story.append(PageBreak())

    # Full source listing
    story.append(Paragraph("Full Source Code Listing", heading_style))
    for rel, content in files:
        story.append(file_header_style and Paragraph(f"<b>{rel}</b>", file_header_style))
        if content.strip():
            # Escape XML entities and use Preformatted for code
            safe = (content.rstrip()
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
            story.append(Preformatted(safe, code_style))
        else:
            story.append(Paragraph("<i>(empty file)</i>", body_style))

    # Footer
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(
        "End of Code Presentation Summary &mdash; "
        "Licensed under Apache 2.0 &mdash; drjeremytabernero.com",
        subtitle_style
    ))

    doc.build(story)
    print(f"PDF created: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")
    return pdf_path


# ── Zip ───────────────────────────────────────────────────────────────
def create_zip(txt_path, pdf_path):
    zip_path = os.path.join(OUT_DIR, "amidala_code_summary.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(txt_path, os.path.basename(txt_path))
        zf.write(pdf_path, os.path.basename(pdf_path))
    print(f"ZIP created: {zip_path} ({os.path.getsize(zip_path):,} bytes)")
    return zip_path


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    files = collect_files()
    txt_path = generate_txt(files)
    pdf_path = generate_pdf(files)
    zip_path = create_zip(txt_path, pdf_path)
    print(f"\nDone! Deliverables at:\n  {zip_path}")
