import requests
from typing import List, Dict

class NotionManager:
    """Placeholder Notion manager.

    In a real implementation this class would communicate with the Notion API
    to retrieve task information. The ``get_tasks`` method is expected to
    return a list of dictionaries with the following keys:

    - ``ticket``: The Jira ticket identifier.
    - ``url``: URL pointing to the Jira issue.
    - ``title``: Title of the Jira issue.
    - ``status``: Either ``"Ongoing"`` or ``"Completed"``.
    """

    def get_tasks(self) -> List[Dict]:
        """Return task information from Notion.

        This is a stub implementation and should be replaced with actual logic
        that fetches tasks from Notion.
        """
        raise NotImplementedError("NotionManager.get_tasks must be implemented")


class SlackManager:
    """Minimal Slack manager used to send messages to users."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Slack token is required")
        self.token = token

    def send_message(self, user: str, text: str) -> bool:
        """Send a message to a user using the Slack API."""
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"channel": user, "text": text},
            timeout=10,
        )
        data = response.json()
        return data.get("ok", False)


class NotionTaskReporter:
    """Generate task summaries and send them via Slack."""

    def __init__(self, notion_manager: NotionManager, slack_manager: SlackManager) -> None:
        self.notion_manager = notion_manager
        self.slack_manager = slack_manager

    def _format_section(self, title: str, tasks: List[Dict]) -> str:
        lines = [f"{title}:"]
        for task in tasks:
            ticket = task.get("ticket", "")
            url = task.get("url", "")
            jira_title = task.get("title", "")
            lines.append(f"[{ticket}]({url}): {jira_title}")
        lines.append("")  # Blank line after section
        return "\n".join(lines)

    def build_report(self) -> str:
        """Create a formatted task report."""
        tasks = self.notion_manager.get_tasks()
        ongoing = [t for t in tasks if t.get("status") == "Ongoing"]
        completed = [t for t in tasks if t.get("status") == "Completed"]

        report = (
            self._format_section("Ongoing", ongoing)
            + self._format_section("Completed", completed)
            + "Summary:\n\n"
        )
        return report

    def send(self, user: str) -> bool:
        """Build the report and send it to a user via Slack."""
        message = self.build_report()
        return self.slack_manager.send_message(user, message)
