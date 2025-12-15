"""CLI entry point for Glass Pane administrative commands.

Usage:
    python -m src.cli provision-bq --dataset chat_analytics
    python -m src.cli provision-bq --dataset chat_analytics --dry-run
"""

import argparse
import sys

from src.cli.provision_bq import provision_chat_analytics, DEFAULT_DATASET, DEFAULT_PROJECT, DEFAULT_LOCATION


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="glass-pane-cli",
        description="Glass Pane CLI for administrative tasks"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # provision-bq command
    provision_parser = subparsers.add_parser(
        "provision-bq",
        help="Provision BigQuery datasets and tables"
    )
    provision_parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"Dataset name (default: {DEFAULT_DATASET})",
    )
    provision_parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project ID (default: {DEFAULT_PROJECT})",
    )
    provision_parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"BigQuery location (default: {DEFAULT_LOCATION})",
    )
    provision_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )

    args = parser.parse_args()

    if args.command == "provision-bq":
        success = provision_chat_analytics(
            project_id=args.project,
            dataset_id=args.dataset,
            location=args.location,
            dry_run=args.dry_run,
        )
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
