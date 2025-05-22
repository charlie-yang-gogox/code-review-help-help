import os
import json
import logging
from dotenv import load_dotenv
from lib.github_manager import GithubManager
from lib.slack_notifier import SlackNotifier

# load environment variables
load_dotenv()

# setup log level
logging.basicConfig(
    level=logging.INFO,  # or DEBUG for more detail
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def parse_repos():
    """Parse repositories from environment variable"""
    repos_str = os.getenv('GITHUB_REPOS')
    
    try:
        # Try parsing as JSON first
        repos = json.loads(repos_str)
        if isinstance(repos, list):
            # Format: [{"owner": "user1", "repo": "repo1", "icon": "icon"}, {"owner": "user2", "repo": "repo2", "icon": "icon"}]
            return [(r['owner'], r['repo'], r['icon']) for r in repos]
    except json.JSONDecodeError:
        # Try parsing as comma-separated string
        # Format: "user1/repo1,user2/repo2"
        repos = []
        for repo_str in repos_str.split(','):
            if '/' in repo_str:
                owner, repo, icon = repo_str.strip().split('/')
                repos.append((owner, repo, icon))
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
    for owner, repo, icon in repos:
        logging.info(f"Checking repository: {icon} {owner}/{repo}")
        try:
            # Get all open pull requests for this repo
            pull_requests = github.get_pull_requests(owner, repo)
            
            for pr in pull_requests:
                all_prs.append((owner, repo, pr, icon))
            
            # Log to console
            for pr in pull_requests:
                pr_number = pr['number']
                pr_title = pr['title']
                pr_url = pr['html_url']
                pr_state = pr['state']
                
                logging.info(f"PR #{pr_number}: {pr_title} ({pr_url}) - State: {pr_state}")
                
                # Get reviewer status
                reviewer_status, approval_count = github.get_reviewer_status(owner, repo, pr_number)
                requested_reviewers = pr.get('requested_reviewers', [])
                reviewers_text = slack._format_reviewers(requested_reviewers, reviewer_status)
                
                logging.info(f"Reviewers: {reviewers_text}")
                logging.info(f"Approvals: {approval_count}")
                
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