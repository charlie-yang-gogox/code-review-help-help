import os
import requests
import logging
import sys
import time
import json
from dotenv import load_dotenv
from typing import List, Dict, Tuple

# Configure logging for Heroku
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Heroku expects logging to stdout
)

# Load environment variables (will work with both .env and Heroku Config Vars)
load_dotenv()

class GithubManager:
    def __init__(self):
        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GitHub token not found in environment variables")
        
        self.headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        # Authorization header
        logging.info(f"Authorization header: {self.headers['Authorization']}")
        
        self.base_url = 'https://api.github.com'
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry mechanism"""
        for attempt in range(self.max_retries):
            try:
                # Print request details
                logging.info(f"Making request to: {url}")
                logging.info(f"Method: {method}")
                logging.info(f"Headers: {self.headers}")
                logging.info(f"Args: {kwargs}")
                
                response = requests.request(method, url, headers=self.headers, **kwargs)
                logging.info(f"Response status: {response.status_code}")
                logging.info(f"Response body: {response.text}")
                
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                logging.warning(f"Request failed, attempt {attempt + 1} of {self.max_retries}: {str(e)}")
                time.sleep(self.retry_delay * (attempt + 1))
        
    def get_pull_requests(self, owner: str, repo: str, state: str = 'open') -> List[Dict]:
        """Get all pull requests from a repository with detailed information"""
        url = f'{self.base_url}/repos/{owner}/{repo}/pulls'
        params = {
            'state': state,
            'sort': 'updated',
            'direction': 'desc'
        }
        response = self._make_request('GET', url, params=params)
        return response.json()
    
    def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Get review status for a specific PR"""
        url = f'{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews'
        response = self._make_request('GET', url)
        return response.json()

    def get_reviewer_status(self, owner: str, repo: str, pr_number: int) -> Dict[str, Dict]:
        """Get review status for each reviewer"""
        reviews = self.get_pr_reviews(owner, repo, pr_number)
        reviewer_status = {}
        approval_count = 0
        
        # Get the latest review for each reviewer
        for review in reviews:
            reviewer = review['user']['login']
            state = review['state']
            
            # Count approvals
            if state == 'APPROVED':
                approval_count += 1
            
            # Only update if this is a newer review or if we haven't seen this reviewer yet
            if reviewer not in reviewer_status or review['submitted_at'] > reviewer_status[reviewer]['submitted_at']:
                reviewer_status[reviewer] = {
                    'state': state,
                    'submitted_at': review['submitted_at']
                }
        
        return reviewer_status, approval_count


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
    
    def send_pr_info(self, prs: List[Tuple[str, str, Dict]], github: 'GithubManager') -> bool:
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
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 PR Status Report ({len(prs)} open PRs)",
                        "emoji": True
                    }
                },
                {
                    "type": "divider"
                }
            ]
            # Group PRs by repository
            repos = {}
            for owner, repo, pr in prs:
                key = f"{owner}/{repo}"
                if key not in repos:
                    repos[key] = []
                repos[key].append((owner, repo, pr))

            # Add PRs for each repository with grouping for ready/pending
            for repo_name, repo_prs in sorted(repos.items()):
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Repository: {repo_name}*"
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
            message = {"blocks": blocks}

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

def parse_repos() -> List[Tuple[str, str]]:
    """Parse repositories from environment variable"""
    repos_str = os.getenv('GITHUB_REPOS')
    if not repos_str:
        # Fallback to single repo format
        owner = os.getenv('GITHUB_OWNER')
        repo = os.getenv('GITHUB_REPO')
        if owner and repo:
            return [(owner, repo)]
        return []
    
    try:
        # Try parsing as JSON first
        repos = json.loads(repos_str)
        if isinstance(repos, list):
            # Format: [{"owner": "user1", "repo": "repo1"}, {"owner": "user2", "repo": "repo2"}]
            return [(r['owner'], r['repo']) for r in repos]
        elif isinstance(repos, dict):
            # Format: {"user1": ["repo1", "repo2"], "user2": ["repo3"]}
            return [(owner, repo) for owner, repos_list in repos.items() for repo in repos_list]
    except json.JSONDecodeError:
        # Try parsing as comma-separated string
        # Format: "user1/repo1,user2/repo2"
        repos = []
        for repo_str in repos_str.split(','):
            if '/' in repo_str:
                owner, repo = repo_str.strip().split('/')
                repos.append((owner, repo))
        return repos
    
    return []

def main():
    # Get repositories to monitor
    repos = parse_repos()
    if not repos:
        logging.error("Please set GITHUB_REPOS environment variable in one of these formats:\n"
                     "1. JSON array: [{\"owner\": \"user1\", \"repo\": \"repo1\"}, {\"owner\": \"user2\", \"repo\": \"repo2\"}]\n"
                     "2. JSON object: {\"user1\": [\"repo1\", \"repo2\"], \"user2\": [\"repo3\"]}\n"
                     "3. Comma-separated: \"user1/repo1,user2/repo2\"\n"
                     "Or use GITHUB_OWNER and GITHUB_REPO for single repository")
        return
    
    github = GithubManager()
    slack = SlackNotifier()
    
    all_prs = []
    for owner, repo in repos:
        logging.info(f"Checking repository: {owner}/{repo}")
        try:
            # Get all open pull requests for this repo
            pull_requests = github.get_pull_requests(owner, repo)
            
            # Filter PRs that need more approvals
            for pr in pull_requests:
                pr_number = pr['number']
                _, approval_count = github.get_reviewer_status(owner, repo, pr_number)
                all_prs.append((owner, repo, pr))
            
            # Log to console
            for pr in pull_requests:
                pr_number = pr['number']
                pr_title = pr['title']
                pr_url = pr['html_url']
                pr_state = pr['state']
                
                # Get reviewer status
                reviewer_status, approval_count = github.get_reviewer_status(owner, repo, pr_number)
                requested_reviewers = pr.get('requested_reviewers', [])
                reviewers_text = slack._format_reviewers(requested_reviewers, reviewer_status)
                
                labels = [label['name'] for label in pr.get('labels', [])]
                
                logging.info(f"Labels: {', '.join(labels) if labels else 'No labels'}")
                logging.info("-" * 80)
            
        except Exception as e:
            logging.error(f"Error processing repository {owner}/{repo}: {str(e)}")
            continue
    
    if all_prs:
        # Send to Slack
        if slack.send_pr_info(all_prs, github):
            logging.info("Successfully sent PR information to Slack")
        else:
            logging.error("Failed to send PR information to Slack")
    else:
        logging.info("No PRs found that need more approvals")

if __name__ == "__main__":
    main()