import os
import random
import time
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Playwright
import asyncio
import logging
import psycopg2
from embedding import EmbeddingService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='github_scrape.log', level=logging.INFO, 
                    format='%(asctime)s - github - %(levelname)s - %(message)s')

# Constants
GITHUB_URL = "https://github.com"
GITHUB_API_URL = "https://api.github.com"

class GitHubScrape:
    def __init__(self, DB):
        load_dotenv()
        db_instance = DB()
        self.db = db_instance.connection
        self.embedding_service = EmbeddingService()

    async def setup(self):
        self.playwright_instance = await async_playwright().start()
        self.browser, self.context = await self.setup_browser(self.playwright_instance)
        await self.login()

    async def login(self):
        page = await self.context.new_page()
        await page.goto(GITHUB_URL + "/login")
        await self.human_like_typing(page, 'input[name="login"]', os.getenv('GITHUB_USERNAME'))
        await self.human_like_typing(page, 'input[name="password"]', os.getenv('GITHUB_PASSWORD'))
        await page.click('input[name="commit"]')
        await page.wait_for_load_state("networkidle")
        logging.info("Successfully logged in to GitHub")

    async def fetch_github_stars(self):
        username = os.getenv('GITHUB_USERNAME')
        auth_token = os.getenv('GITHUB_TOKEN')
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
            await asyncio.sleep(random.uniform(1, 3))  # Random wait between API calls

        for repo in all_stars:
            await self.save_repo_data(repo)

        return all_stars

    async def save_repo_data(self, repo_data):
        try:
            repo_id = repo_data.get('id')
            repo_name = repo_data.get('name')
            repo_url = repo_data.get('html_url')
            owner_login = repo_data.get('owner', {}).get('login')
            owner_url = repo_data.get('owner', {}).get('html_url')
            description = repo_data.get('description', '')
            readme_data = await self.fetch_readme(repo_name, owner_login)

            # Generate text embedding for the description and readme
            description_embedding = self.embedding_service.embed_text([description])[0]
            readme_embedding = self.embedding_service.embed_text([readme_data])[0] if readme_data else None

            # Insert repo data into 'repos' table
            repo_sql = """
            INSERT INTO github_stars (repo_id, repo_name, repo_url, owner_login, owner_url, description, description_embedding, readme_data, readme_embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (repo_id) DO NOTHING
            """
            repo_values = (repo_id, repo_name, repo_url, owner_login, owner_url, description, description_embedding, readme_data, readme_embedding)
            cursor = self.db.cursor()
            cursor.execute(repo_sql, repo_values)
            self.db.commit()
            cursor.close()
            logging.info(f"Inserted repo with ID: {repo_id}")
        except Exception as e:
            logging.error(f"Error inserting repo data: {e}")
            self.db.rollback()

    async def fetch_readme(self, repo_name, owner_login):
        url = f"{GITHUB_API_URL}/repos/{owner_login}/{repo_name}/readme"
        headers = {"Accept": "application/vnd.github.v3.raw"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None

    async def human_like_typing(self, page, selector, text):
        for char in text:
            await page.type(selector, char)
            await asyncio.sleep(random.uniform(0.1, 0.24))

    async def setup_browser(self, playwright: Playwright):
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        return browser, context
