import argparse
import os
import tempfile
import unittest
from pathlib import Path

from github_api import GitHub
from sigma_task import PartialCreate, create, dedicated_github_environment, run


class Board:
    def __init__(self):
        self.item = {"id": "ISSUE", "item_id": "ITEM", "number": 7, "url": "https://example/7",
                     "title": "Task", "fields": {}}
        self.updates, self.comments = [], []
        self.fail_add = False

    def list_items(self): return [self.item]
    def create_issue(self, title, body): return {**self.item, "title": title, "body": body}
    def add_issue_to_project(self, issue):
        if self.fail_add: raise RuntimeError("project unavailable")
        return issue
    def set_select(self, item, field, value): self.updates.append((field, value))
    def set_text(self, item, field, value): self.updates.append((field, value))
    def comment(self, item, body): self.comments.append(body)


class SigmaTaskTest(unittest.TestCase):
    def test_review_evidence_uses_exact_commit_and_returns_pr_snapshot(self):
        class API(GitHub):
            def __init__(self):
                super().__init__(); self.variables = None
            def graphql(self, query, variables=None):
                self.variables = variables
                return {"repository": {"object": {"oid": "abc123", "associatedPullRequests": {"nodes": [
                    {"number": 9, "url": "https://example/pr/9", "isDraft": True, "state": "OPEN",
                     "merged": False, "headRefOid": "abc123", "baseRefName": "main", "body": "criteria"}
                ]}}}}
        api = API()
        evidence = api.review_evidence("abc123")
        self.assertEqual(api.variables["sha"], "abc123")
        self.assertEqual(evidence["pull_requests"][0]["baseRefName"], "main")

    def test_dynamic_single_select_resolution(self):
        class API(GitHub):
            def __init__(self): self.variables = None
            def verify_write_identity(self): pass
            def project(self):
                return {"id": "PROJECT", "fields": {"Исполнитель": {"id": "FIELD", "options": [
                    {"id": "OPTION", "name": "Команда Sigma"}]}}}
            def graphql(self, query, variables=None): self.variables = variables; return {}
        api = API()
        api.set_select({"item_id": "ITEM"}, "Исполнитель", "Команда Sigma")
        self.assertEqual(api.variables, {"p": "PROJECT", "i": "ITEM", "f": "FIELD", "o": "OPTION"})

    def test_project_discovery_keeps_real_union_shapes(self):
        class API(GitHub):
            def __init__(self): super().__init__()
            def graphql(self, query, variables=None):
                return {"user": {"projectV2": {"id": "PROJECT", "fields": {"nodes": [
                    {"__typename": "ProjectV2SingleSelectField", "id": "AREA", "name": "Area",
                     "options": [{"id": "INFRA", "name": "Infra"}]},
                    {"__typename": "ProjectV2Field", "id": "INIT", "name": "Инициатор", "dataType": "TEXT"},
                    {"__typename": "ProjectV2RepositoryField"}
                ]}}}}
        fields = API().project()["fields"]
        self.assertEqual(fields["Area"]["options"][0]["name"], "Infra")
        self.assertEqual(fields["Инициатор"]["dataType"], "TEXT")

    def test_create_sets_all_dynamic_fields(self):
        board = Board()
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.md"; body.write_text("criteria")
            args = argparse.Namespace(title="New", body_file=str(body), area="BE", initiator="Макс",
                                      executor="Команда Sigma", status="Backlog")
            result = create(board, args)
        self.assertEqual(result["title"], "New")
        # Publish the runnable status only after metadata and assignment exist.
        self.assertEqual(board.updates, [("Инициатор", "Макс"), ("Area", "BE"),
                                         ("Исполнитель", "Команда Sigma"), ("Status", "Backlog")])

    def test_partial_create_preserves_issue_url(self):
        board = Board(); board.fail_add = True
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.md"; body.write_text("criteria")
            args = argparse.Namespace(title="New", body_file=str(body), area="BE", initiator="Макс",
                                      executor="Команда Sigma", status="Backlog")
            with self.assertRaises(PartialCreate) as raised: create(board, args)
        self.assertEqual(raised.exception.url, "https://example/7")

    def test_set_and_comment_do_not_authorize_retry(self):
        board = Board()
        run(argparse.Namespace(action="set", number=7, status="Backlog", executor="Команда Sigma"), board)
        self.assertEqual(board.updates, [("Исполнитель", "Команда Sigma"), ("Status", "Backlog")])
        with tempfile.TemporaryDirectory() as directory:
            note = Path(directory) / "note"; note.write_text("hello")
            run(argparse.Namespace(action="comment", number=7, file=str(note)), board)
        self.assertEqual(board.comments, ["hello"])

    def test_dedicated_environment_discards_token(self):
        os.environ["GH_TOKEN"] = "do-not-use"
        os.environ["GITHUB_TOKEN"] = "do-not-use"
        dedicated_github_environment()
        self.assertNotIn("GH_TOKEN", os.environ)
        self.assertNotIn("GITHUB_TOKEN", os.environ)
        self.assertEqual(os.environ["GH_CONFIG_DIR"], "/etc/sigma-team/github")


if __name__ == "__main__":
    unittest.main()
