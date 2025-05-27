import os
import logging
from dotenv import load_dotenv
from lib.github_manager import GithubManager
from lib.slack_notifier import SlackNotifier

# load environment variables
load_dotenv()

# setup log level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def main():
    # Get environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    github_repos = os.getenv('GITHUB_REPOS')
    
    if not github_token:
        logging.error("GITHUB_TOKEN environment variable is not set")
        return
    
    if not slack_webhook_url:
        logging.error("SLACK_WEBHOOK_URL environment variable is not set")
        return
    
    if not github_repos:
        logging.error("GITHUB_REPOS environment variable is not set")
        return
    
    try:
        github = GithubManager(github_token, github_repos)
        slack = SlackNotifier(slack_webhook_url)
        
        all_prs = []
        for owner, repo, icon in github.repos:
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
            
    except ValueError as e:
        logging.error(str(e))
        return

if __name__ == "__main__":
    main()