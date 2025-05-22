import os
import requests
import logging
from typing import List, Dict
from datetime import datetime

def get_review_status_emoji(state: str) -> str:
    """Get emoji for review status"""
    status_map = {
        'APPROVED': ':white_check_mark:',
        'CHANGES_REQUESTED': ':x:',
        'COMMENTED': ':speech_balloon:',
        'PENDING': ':hourglass:',
        'DISMISSED': ':no_entry:'
    }
    return status_map.get(state, ':white_circle:')

class SlackNotifier:
    def __init__(self):
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if not self.webhook_url:
            raise ValueError("Slack Webhook URL not found in environment variables")
    
    def _format_reviewers(self, requested_reviewers: List[Dict], reviewer_status: Dict[str, Dict]) -> str:
        """Format reviewers list with their review status"""
        reviewer_texts = []
        
        # Get all reviewers (both requested and those who have reviewed)
        all_reviewers = set()
        for reviewer in requested_reviewers:
            all_reviewers.add(reviewer['login'])
        all_reviewers.update(reviewer_status.keys())
        
        # Sort reviewers: requested reviewers first, then others
        requested_names = {r['login'] for r in requested_reviewers}
        sorted_reviewers = sorted(
            all_reviewers,
            key=lambda x: (0 if x in requested_names else 1, x)
        )
        
        # Format each reviewer with their status
        for reviewer_name in sorted_reviewers:
            status = reviewer_status.get(reviewer_name, {}).get('state', 'PENDING')
            emoji = get_review_status_emoji(status)
            reviewer_texts.append(f"• {reviewer_name} {emoji}")
        
        return '\n'.join(reviewer_texts) if reviewer_texts else 'No reviewers assigned'
    
    def _create_pr_block(self, owner: str, repo: str, pr: Dict, github: 'GithubManager') -> Dict:
        """Create a formatted PR block for Slack message"""
        pr_number = pr['number']
        pr_title = pr['title']
        pr_url = pr['html_url']
        requested_reviewers = pr.get('requested_reviewers', [])
        labels = [label['name'] for label in pr.get('labels', [])]

        # Get reviewer status and approval count
        reviewer_status, approval_count = github.get_reviewer_status(owner, repo, pr_number)
        ready_for_merge = approval_count >= 2

        reviewers_text = self._format_reviewers(requested_reviewers, reviewer_status)

        if ready_for_merge:
            text = (
                f"*<{pr_url}|PR #{pr_number}: {pr_title}>*"
            )
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            }
        else:
            text = (
                f"*<{pr_url}|PR #{pr_number}: {pr_title}>*\n"
                f"> *Reviewers:*\n"
                f"> {reviewers_text.replace(chr(10), chr(10) + '> ')}\n"
                f"> *Labels:* {', '.join(labels) if labels else 'No labels'}"
            )

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        }
    
    def send_pr_info(self, prs: List[tuple], github: 'GithubManager') -> bool:
        """Send PR information to Slack channel"""
        if not prs:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*No open PRs found in any repository*"
                        }
                    }
                ]
            }
        else:
            today_str = datetime.now().strftime("%Y-%m-%d")
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 PR Status Report ({today_str}) - {len(prs)} open PRs",
                        "emoji": True
                    }
                },
                {
                    "type": "divider"
                }
            ]
            # Group PRs by repository
            repos = {}
            for owner, repo, pr, icon in prs:
                key = f"{owner}/{repo}"
                if key not in repos:
                    repos[key] = {"icon": icon, "prs": []}
                repos[key]["prs"].append((owner, repo, pr))

            # Add PRs for each repository with grouping for ready/pending
            for repo_name, repo_info in sorted(repos.items()):
                icon = repo_info["icon"]
                repo_prs = repo_info["prs"]
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{icon} *Repository: {repo_name}*"
                    }
                })
                # Split into ready and pending
                ready_prs = []
                pending_prs = []
                for owner, repo, pr in repo_prs:
                    _, approval_count = github.get_reviewer_status(owner, repo, pr['number'])
                    if approval_count >= 2:
                        ready_prs.append((owner, repo, pr))
                    else:
                        pending_prs.append((owner, repo, pr))
                # Add heading and blocks for ready PRs
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*✅ Ready for Merge*"}
                })
                if ready_prs:
                    for owner, repo, pr in ready_prs:
                        blocks.append(self._create_pr_block(owner, repo, pr, github))
                else:
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "_None_"}
                    })
                # Add heading and blocks for pending PRs
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*🕐 Pending Reviews*"}
                })
                if pending_prs:
                    for owner, repo, pr in pending_prs:
                        blocks.append(self._create_pr_block(owner, repo, pr, github))
                else:
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "_None_"}
                    })
                blocks.append({"type": "divider"})
            message = {
                "username": "PR help help",
                "icon_emoji": ":robot_face:",
                "blocks": blocks
            }

        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            logging.info("Successfully sent message to Slack")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send message to Slack: {str(e)}")
            return False
