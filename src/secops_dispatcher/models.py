from pydantic import BaseModel, ConfigDict, Field


class GitHubLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str


class GitHubIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    state: str
    html_url: str
    body: str | None = None
    labels: list[GitHubLabel] = Field(default_factory=list)

    @property
    def label_names(self) -> list[str]:
        return [label.name for label in self.labels]


class IssueEvent(BaseModel):
    """The subset of GitHub's `issues` webhook payload the dispatcher relies on."""

    model_config = ConfigDict(extra="ignore")

    action: str
    issue: GitHubIssue
    repository: GitHubRepository
    label: GitHubLabel | None = None


class VulnerabilityIssue(BaseModel):
    """A dispatchable issue, decoupled from GitHub's payload shape."""

    repo: str
    number: int
    title: str
    url: str
    body: str = ""

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"
