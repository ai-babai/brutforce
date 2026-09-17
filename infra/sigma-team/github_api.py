"""Small GitHub Project v2 adapter. Field and option IDs are discovered by name."""
import json
import os
import subprocess
import urllib.request

STATUS_ALIASES = {
    "running": ("running", "В работе"),
    "sigma_verification": ("Sigma verification", "sigma_verification"),
    "human_verification": ("Human verification", "human_verification"),
    "pending": ("Pending",),
}


class GitHub:
    def __init__(self, owner="ai-babai", project_number=2, repository="ai-babai/brutforce"):
        self.owner, self.project_number, self.repository = owner, project_number, repository
        self._project = None
        self._identity_verified = False

    def _token(self):
        token = os.environ.get("GH_TOKEN")
        if token:
            return token
        result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError("GitHub credential unavailable")
        return result.stdout.strip()

    def graphql(self, query, variables=None):
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": variables or {}}).encode(),
            headers={"Authorization": "Bearer " + self._token(), "Content-Type": "application/json",
                     "User-Agent": "sigma-team/1"})
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.load(response)
        if data.get("errors"):
            raise RuntimeError("GitHub API rejected request")
        return data["data"]

    def project(self):
        if self._project is None:
            q = """query($owner:String!,$number:Int!){user(login:$owner){projectV2(number:$number){id fields(first:50){nodes{__typename ... on ProjectV2Field{id name dataType} ... on ProjectV2SingleSelectField{id name options{id name}}}}}}}"""
            raw = self.graphql(q, {"owner": self.owner, "number": self.project_number})["user"]["projectV2"]
            fields = {x["name"]: x for x in raw["fields"]["nodes"] if x and x.get("name")}
            self._project = {"id": raw["id"], "fields": fields}
        return self._project

    def verify_write_identity(self):
        if not self._identity_verified:
            login = self.graphql("query{viewer{login}}")['viewer']['login']
            if login != "aika-ai-agent":
                raise RuntimeError("GitHub write identity is not aika-ai-agent")
            self._identity_verified = True

    def list_items(self):
        q = """query($owner:String!,$number:Int!,$cursor:String){user(login:$owner){projectV2(number:$number){items(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{id fieldValues(first:30){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{name}}}}} content{... on Issue{id number title body url state repository{nameWithOwner} comments(last:100){nodes{body createdAt author{login}}}}}}}}}}"""
        cursor, result = None, []
        while True:
            page = self.graphql(q, {"owner": self.owner, "number": self.project_number, "cursor": cursor})["user"]["projectV2"]["items"]
            for raw in page["nodes"]:
                issue = raw.get("content") or {}
                if issue.get("repository", {}).get("nameWithOwner") != self.repository:
                    continue
                fields = {v["field"]["name"]: v["name"] for v in raw["fieldValues"]["nodes"] if v.get("field")}
                result.append({**issue, "item_id": raw["id"], "fields": fields})
            if not page["pageInfo"]["hasNextPage"]:
                return result
            cursor = page["pageInfo"]["endCursor"]

    def set_status(self, item, status):
        self.set_select(item, "Status", status)

    def set_select(self, item, field_name, value):
        self.verify_write_identity()
        field = self.project()["fields"].get(field_name)
        if not field:
            raise RuntimeError(field_name + " field missing")
        names = STATUS_ALIASES.get(value.casefold(), (value,)) if field_name == "Status" else (value,)
        option = next((x for x in field["options"] if any(x["name"].casefold() == name.casefold() for name in names)), None)
        if not option:
            raise RuntimeError(field_name + " option missing: " + value)
        q = """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){projectV2Item{id}}}"""
        self.graphql(q, {"p": self.project()["id"], "i": item["item_id"], "f": field["id"], "o": option["id"]})

    def set_text(self, item, field_name, value):
        self.verify_write_identity()
        field = self.project()["fields"].get(field_name)
        if not field:
            raise RuntimeError(field_name + " field missing")
        if field.get("dataType") not in {None, "TEXT"}:
            raise RuntimeError(field_name + " is not a text field")
        q = """mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{text:$v}}){projectV2Item{id}}}"""
        self.graphql(q, {"p": self.project()["id"], "i": item["item_id"], "f": field["id"], "v": value})

    def create_issue(self, title, body):
        self.verify_write_identity()
        owner, name = self.repository.split("/", 1)
        repository = self.graphql("query($o:String!,$n:String!){repository(owner:$o,name:$n){id}}",
                                  {"o": owner, "n": name})["repository"]
        q = """mutation($r:ID!,$t:String!,$b:String!){createIssue(input:{repositoryId:$r,title:$t,body:$b}){issue{id number title body url state repository{nameWithOwner} comments(last:100){nodes{body createdAt author{login}}}}}}"""
        return self.graphql(q, {"r": repository["id"], "t": title, "b": body})["createIssue"]["issue"]

    def add_issue_to_project(self, issue):
        self.verify_write_identity()
        q = """mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}"""
        item_id = self.graphql(q, {"p": self.project()["id"], "c": issue["id"]})["addProjectV2ItemById"]["item"]["id"]
        return {**issue, "item_id": item_id, "fields": {}}

    def review_evidence(self, commit):
        """Read commit/PR evidence with dispatcher credentials; reviewer gets only JSON."""
        owner, name = self.repository.split("/", 1)
        q = """query($o:String!,$n:String!,$sha:String!){repository(owner:$o,name:$n){object(expression:$sha){... on Commit{oid associatedPullRequests(first:10){nodes{number url isDraft state merged headRefOid baseRefName body}}}}}}"""
        value = self.graphql(q, {"o": owner, "n": name, "sha": commit})["repository"]["object"]
        if not value:
            raise RuntimeError("commit not found in GitHub repository")
        return {"oid": value["oid"], "pull_requests": value["associatedPullRequests"]["nodes"]}

    def comment(self, item, body):
        self.verify_write_identity()
        q = """mutation($id:ID!,$body:String!){addComment(input:{subjectId:$id,body:$body}){commentEdge{node{id}}}}"""
        self.graphql(q, {"id": item["id"], "body": body})
