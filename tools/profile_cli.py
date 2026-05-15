"""
User profile and memo history CLI.

Usage:
  uv run python -m tools.profile_cli show
  uv run python -m tools.profile_cli set [--risk LEVEL] [--sectors a,b] [--holdings X,Y] [--notes "..."]
  uv run python -m tools.profile_cli history TICKER [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.store import build_store, get_memo_history, get_user_profile, update_user_profile

_MEM_PATH = Path(__file__).parent.parent / "data" / "memory.db"


def _get_store():
    _MEM_PATH.parent.mkdir(exist_ok=True)
    return build_store(_MEM_PATH)


def cmd_show(_args) -> None:
    store = _get_store()
    profile = get_user_profile(store)
    print("User Profile")
    print("-" * 40)
    print(f"  Risk tolerance     : {profile.risk_tolerance}")
    print(f"  Sectors of interest: {', '.join(profile.sectors_of_interest) or '(none)'}")
    print(f"  Holdings           : {', '.join(profile.holdings) or '(none)'}")
    print(f"  Notes              : {profile.notes or '(none)'}")


def cmd_set(args) -> None:
    store = _get_store()
    fields: dict = {}
    if args.risk:
        fields["risk_tolerance"] = args.risk
    if args.sectors:
        fields["sectors_of_interest"] = [s.strip() for s in args.sectors.split(",") if s.strip()]
    if args.holdings:
        fields["holdings"] = [h.strip().upper() for h in args.holdings.split(",") if h.strip()]
    if args.notes is not None:
        fields["notes"] = args.notes

    if not fields:
        print("Nothing to update — provide at least one of --risk, --sectors, --holdings, --notes")
        sys.exit(1)

    updated = update_user_profile(store, **fields)
    print("Profile updated.")
    print("-" * 40)
    print(f"  Risk tolerance     : {updated.risk_tolerance}")
    print(f"  Sectors of interest: {', '.join(updated.sectors_of_interest) or '(none)'}")
    print(f"  Holdings           : {', '.join(updated.holdings) or '(none)'}")
    print(f"  Notes              : {updated.notes or '(none)'}")


def cmd_history(args) -> None:
    store = _get_store()
    ticker = args.ticker.upper()
    limit = args.limit
    memos = get_memo_history(store, ticker, limit=limit)

    if not memos:
        print(f"No memo history found for {ticker}.")
        return

    print(f"Memo history for {ticker}  ({len(memos)} record(s))")
    print("=" * 60)
    for memo in memos:
        bar = "*" * memo.conviction + "-" * (5 - memo.conviction)
        print(f"\n  {memo.recommendation}  conviction {memo.conviction}/5 [{bar}]  horizon: {memo.time_horizon}")
        print(f"  Thesis: {memo.thesis}")
        if memo.key_risks:
            print(f"  Top risk: {memo.key_risks[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="profile_cli", description="Manage user profile and memo history.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="Print current user profile.")

    p_set = sub.add_parser("set", help="Update user profile fields.")
    p_set.add_argument("--risk", choices=["conservative", "moderate", "aggressive"],
                       help="Risk tolerance level.")
    p_set.add_argument("--sectors", metavar="SECTOR,...",
                       help="Comma-separated sectors of interest (e.g. tech,energy).")
    p_set.add_argument("--holdings", metavar="TICKER,...",
                       help="Comma-separated tickers the user holds (e.g. AAPL,MSFT).")
    p_set.add_argument("--notes", metavar="TEXT",
                       help="Free-form preference notes.")

    p_hist = sub.add_parser("history", help="Print memo history for a ticker.")
    p_hist.add_argument("ticker", metavar="TICKER")
    p_hist.add_argument("--limit", type=int, default=5, metavar="N",
                        help="Max number of records to show (default 5).")

    args = parser.parse_args()
    {"show": cmd_show, "set": cmd_set, "history": cmd_history}[args.command](args)


if __name__ == "__main__":
    main()
