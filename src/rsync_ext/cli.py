from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rsync_ext.cleanup import purge_user_data
from rsync_ext.config import ConnectionStore
from rsync_ext.transfer import (
    build_transfer_plan,
    map_command_error,
    run_command,
    should_retry_with_inplace,
    test_connection,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsync-ext")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("app", help="Open the connections manager")
    subparsers.add_parser("purge-user-data", help="Remove saved config, logs, and stored secrets for the current user")

    send_parser = subparsers.add_parser("send", help="Open the send dialog")
    send_parser.add_argument("--connection", required=True)
    send_parser.add_argument("--dest-path")
    send_parser.add_argument("sources", nargs="+")

    transfer_parser = subparsers.add_parser("transfer", help="Run a transfer")
    transfer_parser.add_argument("--connection", required=True)
    transfer_parser.add_argument("--dest-path", required=True)
    transfer_parser.add_argument("--accept-new-hostkey", action="store_true")
    transfer_parser.add_argument(
        "--preserve-unix-attrs",
        action="store_true",
        help="Preserve owner/group/permission metadata instead of disabling it",
    )
    transfer_parser.add_argument("sources", nargs="+")

    test_parser = subparsers.add_parser("test-connection", help="Test a saved connection")
    test_parser.add_argument("--connection", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ConnectionStore()

    if args.command == "app":
        from rsync_ext.app import launch_app

        return launch_app(mode="app")

    if args.command == "send":
        from rsync_ext.app import launch_app

        return launch_app(
            mode="send",
            connection_id=args.connection,
            dest_path=args.dest_path,
            sources=[str(Path(item)) for item in args.sources],
        )

    if args.command == "purge-user-data":
        try:
            purge_user_data()
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("User data purged")
        return 0

    connection = store.get(args.connection)

    if args.command == "transfer":
        plan = build_transfer_plan(
            connection,
            args.sources,
            args.dest_path,
            accept_new_hostkey=args.accept_new_hostkey,
            preserve_unix_attrs=args.preserve_unix_attrs,
        )
        result = run_command(plan.command, plan.env)
        if should_retry_with_inplace(result):
            print(
                "Destination rejected temporary rsync files; retrying with in-place writes...",
                file=sys.stderr,
            )
            plan = build_transfer_plan(
                connection,
                args.sources,
                args.dest_path,
                accept_new_hostkey=args.accept_new_hostkey,
                use_inplace=True,
                preserve_unix_attrs=args.preserve_unix_attrs,
            )
            result = run_command(plan.command, plan.env)
        if result.returncode != 0:
            error = map_command_error(result)
            print(error, file=sys.stderr)
            if error.details:
                print(error.details, file=sys.stderr)
            return result.returncode or 1
        if result.stdout:
            print(result.stdout, end="")
        return 0

    if args.command == "test-connection":
        try:
            test_connection(connection)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            details = getattr(exc, "details", "")
            if details:
                print(details, file=sys.stderr)
            return 1
        print("Connection OK")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
