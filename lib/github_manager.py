import os
import requests
import logging
import time
from typing import List, Dict

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
        logging.debug(f"Authorization header: {self.headers['Authorization']}")
        
        self.base_url = 'https://api.github.com'
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
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
