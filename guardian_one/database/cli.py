"""Guardian One Database CLI — standalone entry point for --db-* commands.

This module runs without heavy dependencies (cryptography, dotenv, etc.)
so database commands work in minimal environments and Docker containers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from guardian_one.database import GuardianDatabase


def db_main() -> None:
    """Parse --db-* arguments and dispatch."""
    parser = argparse.ArgumentParser(description="Guardian One — database commands")
    parser.add_argument("--db", action="store_true", help="Show database stats")
    parser.add_argument("--db-init", action="store_true", help="Initialize database and import existing data")
    parser.add_argument("--db-logs", nargs="?", const="all", default=None,
                        help="Query database logs (optionally filter by agent name)")
    parser.add_argument("--db-crawls", nargs="?", const="all", default=None,
                        help="Query crawl records (optionally filter by bot name)")
    parser.add_argument("--db-transactions", nargs="?", const="all", default=None,
                        help="Query financial transactions (optionally filter by source)")
    parser.add_argument("--db-accounts", action="store_true", help="Show financial accounts from database")
    parser.add_argument("--db-codes", nargs="?", const="all", default=None,
                        help="Query system codes (optionally filter by type)")
    parser.add_argument("--db-search", type=str, default=None, help="Full-text search across logs and transactions")
    parser.add_argument("--db-spending", action="store_true", help="Spending summary by category")
    parser.add_argument("--db-net-worth", action="store_true", help="Net worth from database accounts")
    parser.add_argument("--db-path", type=str, default=None, help="Custom database path (default: data/guardian.db)")
    args = parser.parse_args()
    _handle_db_commands(args)


def _handle_db_commands(args: argparse.Namespace) -> None:
    """Handle all --db-* CLI commands."""
    # If --db-path is given, honor it; otherwise let GuardianDatabase
    # resolve the default via GUARDIAN_DATA_DIR (or fall back to ./data).
    db_path = Path(args.db_path) if args.db_path else None
    db = GuardianDatabase(db_path)

    if args.db_init:
        print("=" * 60)
        print("  GUARDIAN ONE DATABASE — INITIALIZATION")
        print("=" * 60)
        print(f"  Database: {db_path}")
        print()

        # Import existing audit logs
        audit_path = Path("logs/audit.jsonl")
        if audit_path.exists():
            count = db.import_audit_jsonl(audit_path)
            print(f"  Imported {count} audit log entries from {audit_path}")
        else:
            print(f"  No audit log found at {audit_path} (skipped)")

        # Import existing CFO ledger
        ledger_path = Path("data/cfo_ledger.json")
        if ledger_path.exists():
            count = db.import_cfo_ledger(ledger_path)
            print(f"  Imported {count} financial accounts from {ledger_path}")
        else:
            print(f"  No CFO ledger found at {ledger_path} (skipped)")

        print()
        stats = db.stats()
        print("  Tables initialized:")
        for table, count in stats.items():
            if table not in ("db_path", "db_size_bytes"):
                print(f"    {table:<30} {count:>8} rows")
        print(f"\n  Database size: {stats['db_size_bytes']:,} bytes")
        print("=" * 60)
        return

    if args.db:
        stats = db.stats()
        print("=" * 60)
        print("  GUARDIAN ONE DATABASE — STATUS")
        print("=" * 60)
        print(f"  Path: {stats['db_path']}")
        print(f"  Size: {stats['db_size_bytes']:,} bytes")
        print()
        for table, count in stats.items():
            if table not in ("db_path", "db_size_bytes"):
                print(f"    {table:<30} {count:>8} rows")
        print("=" * 60)
        return

    if args.db_logs is not None:
        agent_filter = args.db_logs if args.db_logs != "all" else None
        logs = db.query_logs(agent=agent_filter, limit=50)
        label = f" (agent={agent_filter})" if agent_filter else ""
        print(f"\n  SYSTEM LOGS{label} — {len(logs)} entries")
        print("  " + "-" * 70)
        for log in logs:
            print(f"  [{log.timestamp}] {log.agent:>14} | {log.severity:>8} | {log.action}")
            if log.message and log.message != log.action:
                print(f"  {'':>14}   {log.message[:80]}")
        return

    if args.db_crawls is not None:
        bot_filter = args.db_crawls if args.db_crawls != "all" else None
        crawls = db.query_crawls(bot_name=bot_filter, limit=50)
        label = f" (bot={bot_filter})" if bot_filter else ""
        print(f"\n  CRAWL RECORDS{label} — {len(crawls)} entries")
        print("  " + "-" * 70)
        for c in crawls:
            print(f"  [{c.crawl_timestamp}] {c.bot_name:>14} | {c.status_code} | {c.target_url[:50]}")
            if c.title:
                print(f"  {'':>14}   {c.title[:80]}")
        return

    if args.db_transactions is not None:
        source_filter = args.db_transactions if args.db_transactions != "all" else None
        txns = db.query_transactions(source=source_filter, limit=50)
        label = f" (source={source_filter})" if source_filter else ""
        print(f"\n  FINANCIAL TRANSACTIONS{label} — {len(txns)} entries")
        print("  " + "-" * 72)
        print(f"  {'Date':<12} {'Description':<30} {'Amount':>10} {'Category':<15}")
        print("  " + "-" * 72)
        for t in txns:
            print(f"  {t.date:<12} {t.description[:28]:<30} ${t.amount:>9,.2f} {t.category:<15}")
        return

    if args.db_accounts:
        accounts = db.get_accounts()
        print(f"\n  FINANCIAL ACCOUNTS — {len(accounts)} accounts")
        print("  " + "-" * 72)
        print(f"  {'Account':<40} {'Type':<12} {'Balance':>12} {'Source':<10}")
        print("  " + "-" * 72)
        total = 0.0
        for a in accounts:
            print(f"  {a.name[:38]:<40} {a.account_type:<12} ${a.balance:>11,.2f} {a.source:<10}")
            total += a.balance
        print("  " + "-" * 72)
        print(f"  {'TOTAL':<40} {'':<12} ${total:>11,.2f}")
        return

    if args.db_codes is not None:
        type_filter = args.db_codes if args.db_codes != "all" else None
        codes = db.query_codes(code_type=type_filter, limit=50)
        label = f" (type={type_filter})" if type_filter else ""
        print(f"\n  SYSTEM CODES{label} — {len(codes)} entries")
        print("  " + "-" * 70)
        for c in codes:
            exp = f" expires={c.expires_at}" if c.expires_at else ""
            print(f"  [{c.issued_at}] {c.code_id:<20} | {c.code_type:<10} | {c.status:<8}{exp}")
            if c.description:
                print(f"  {'':>20}   {c.description[:60]}")
        return

    if args.db_search:
        query = args.db_search
        print(f"\n  SEARCH RESULTS for '{query}'")
        print("  " + "=" * 60)

        logs = db.query_logs(search=query, limit=20)
        if logs:
            print(f"\n  Logs ({len(logs)} matches):")
            for log in logs:
                print(f"    [{log.timestamp}] {log.agent} | {log.action}")

        txns = db.query_transactions(search=query, limit=20)
        if txns:
            print(f"\n  Transactions ({len(txns)} matches):")
            for t in txns:
                print(f"    [{t.date}] {t.description} ${t.amount:,.2f}")

        if not logs and not txns:
            print("  No results found.")
        return

    if args.db_spending:
        summary = db.spending_summary()
        print("\n  SPENDING BY CATEGORY")
        print("  " + "-" * 40)
        total = 0.0
        for category, amount in summary.items():
            print(f"  {category:<25} ${amount:>10,.2f}")
            total += amount
        print("  " + "-" * 40)
        print(f"  {'TOTAL':<25} ${total:>10,.2f}")
        return

    if args.db_net_worth:
        nw = db.net_worth()
        print("\n  NET WORTH (from database)")
        print("  " + "-" * 40)
        for acct_type, total in nw.get("by_type", {}).items():
            print(f"  {acct_type:<20} ${total:>12,.2f}")
        print("  " + "-" * 40)
        print(f"  {'TOTAL':<20} ${nw['total']:>12,.2f}")
        return
