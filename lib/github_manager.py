import requests
import logging
import time
import json
from typing import List, Dict, Tuple

class GithubManager:
    def __init__(self, github_token: str, repos_str: str):
        if not github_token:
            raise ValueError("GitHub token is required")
        
        self.headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        self.base_url = 'https://api.github.com'
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        # Parse repositories
        self.repos = self._parse_repos(repos_str)
        if not self.repos:
            raise ValueError("No valid repositories found in GITHUB_REPOS")
    
    def _parse_repos(self, repos_str: str) -> List[Tuple[str, str, str]]:
        """Parse repositories from environment variable"""
        if not repos_str:
            logging.error("repos_str is empty")
            return []
            
        # Clean the string
        repos_str = repos_str.strip()
        
        try:
            # Try parsing as JSON first
            # Remove any potential BOM or special characters
            repos_str = repos_str.encode('utf-8').decode('utf-8-sig')
            repos = json.loads(repos_str)
            
            if isinstance(repos, list):
                # Format: [{"owner": "user1", "repo": "repo1", "icon": "icon"}, {"owner": "user2", "repo": "repo2", "icon": "icon"}]
                result = []
                for r in repos:
                    if not isinstance(r, dict):
                        logging.error(f"Invalid repository format: {r}")
                        continue
                    if not all(k in r for k in ['owner', 'repo', 'icon']):
                        logging.error(f"Missing required fields in repository: {r}")
                        continue
                    result.append((r['owner'], r['repo'], r['icon']))
                return result
            else:
                logging.error(f"Expected list but got {type(repos)}")
                return []
                
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse as JSON: {str(e)}")
            # Try parsing as comma-separated string
            # Format: "user1/repo1,user2/repo2"
            repos = []
            for repo_str in repos_str.split(','):
                if '/' in repo_str:
                    try:
                        owner, repo, icon = repo_str.strip().split('/')
                        repos.append((owner, repo, icon))
                    except ValueError:
                        logging.error(f"Invalid repository format: {repo_str}")
                        continue
            return repos
        
        logging.error("Failed to parse repositories in any format")
        return []
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry mechanism"""
        for attempt in range(self.max_retries):
            try:
                # Print request details
                logging.debug(f"Making request to: {url}")
                logging.debug(f"Method: {method}")
                logging.debug(f"Headers: {self.headers}")
                logging.debug(f"Args: {kwargs}")
                
                response = requests.request(method, url, headers=self.headers, **kwargs)
                logging.debug(f"Response status: {response.status_code}")
                logging.debug(f"Response body: {response.text}")
                
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
