import os
import random
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
GITHUB_URL = "https://github.com"
GITHUB_API_URL = "https://api.github.com"


def login_github(page):
    page.goto(GITHUB_URL + "/login")
    human_like_typing(page, 'input[name="login"]',
                      os.getenv('GITHUB_USERNAME'))
    human_like_typing(page, 'input[name="password"]',
                      os.getenv('GITHUB_PASSWORD'))
    page.click('input[name="commit"]')
    page.wait_for_load_state("networkidle")


def fetch_github_stars(username, auth_token=None):
    headers = {"Accept": "application/vnd.github.v3.star+json"}
    if auth_token:
        headers["Authorization"] = f"token {auth_token}"

    all_stars = []
    page = 1
    while True:
        url = f"{GITHUB_API_URL}/users/{username}/starred?per_page=100&page={page}"
        response = requests.get(url, headers=headers)
        data = response.json()
        if not data:
            break
        all_stars.extend(data)
        page += 1
        time.sleep(random.uniform(1, 3))  # Random wait between API calls

    return all_stars

# Note: The following functions are referenced but not defined in the GitHub-specific code
# They should be imported or defined elsewhere in your project
# human_like_typing()
