"""Hermes-facing board management CLI. It never authorizes a retry."""
import argparse
import json
import os
import sys
from pathlib import Path

from github_api import GitHub


class PartialCreate(RuntimeError):
    def __init__(self, url, message):
        super().__init__(message)
        self.url = url


def dedicated_github_environment():
    os.environ.pop("GH_TOKEN", None)
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ["GH_CONFIG_DIR"] = "/etc/sigma-team/github"


def create(board, args):
    issue = board.create_issue(args.title, Path(args.body_file).read_text())
    try:
        item = board.add_issue_to_project(issue)
        board.set_text(item, "Инициатор", args.initiator)
        for field, value in (("Area", args.area), ("Исполнитель", args.executor), ("Status", args.status)):
            board.set_select(item, field, value)
    except Exception as exc:
        raise PartialCreate(issue["url"], str(exc)) from exc
    return item


def find(board, number):
    value = next((x for x in board.list_items() if x["number"] == number), None)
    if not value:
        raise RuntimeError("issue is not present in project: " + str(number))
    return value


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--body-file", required=True)
    create_parser.add_argument("--area", required=True)
    create_parser.add_argument("--initiator", required=True)
    create_parser.add_argument("--executor", required=True)
    create_parser.add_argument("--status", required=True)
    set_parser = sub.add_parser("set")
    set_parser.add_argument("number", type=int)
    set_parser.add_argument("--status")
    set_parser.add_argument("--executor")
    comment_parser = sub.add_parser("comment")
    comment_parser.add_argument("number", type=int)
    comment_parser.add_argument("--file", required=True)
    return parser


def run(args, board):
    if args.action == "list":
        return board.list_items()
    if args.action == "create":
        return create(board, args)
    item = find(board, args.number)
    if args.action == "comment":
        board.comment(item, Path(args.file).read_text())
        return {"number": item["number"], "url": item["url"], "commented": True}
    if not args.status and not args.executor:
        raise RuntimeError("set requires --status and/or --executor")
    if args.executor:
        board.set_select(item, "Исполнитель", args.executor)
    if args.status:
        board.set_select(item, "Status", args.status)
    return {"number": item["number"], "url": item["url"], "updated": True}


def main():
    dedicated_github_environment()
    args = build_parser().parse_args()
    try:
        print(json.dumps(run(args, GitHub()), ensure_ascii=False, indent=2))
    except PartialCreate as exc:
        print("sigma-task partial create; issue already exists and must not be recreated: " + exc.url
              + "; " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("sigma-task failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
