import json
import os
import random
import time
import uuid
from playwright.async_api import async_playwright, Playwright
import asyncio
import requests
import logging
from embedding import EmbeddingService
import psycopg2

# Configure logging
logging.basicConfig(filename='tweet_scrape.log', level=logging.INFO, 
                    format='%(asctime)s - tweets - %(levelname)s - %(message)s')

# Constants
X_URL = "https://x.com"
X_LOGIN_URL = "https://x.com/i/flow/login"
username = os.getenv("X_USERNAME")
X_LIKES_URL = f"https://x.com/{username}/likes"
X_LOGIN_REDIRECT_URL = "https://x.com/home"

# User agents list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36"
]

class TweetInjest:
    def __init__(self, DB):
        db_instance = DB(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        )
        self.db = db_instance.connection
        self.embedding_service = EmbeddingService()

    async def setup(self):
        self.playwright_instance = await async_playwright().start()
        self.browser, self.context = await setup_browser(self.playwright_instance)
        await self.login()


    async def login(self):
        print("Tweet_injest Starting login process")
        x_session_file = "./x_session.json"
        if os.path.exists(x_session_file):
            print("Tweet_injest Session file exists, attempting to restore session")
            with open(x_session_file, 'r') as f:
                session_data = json.load(f)
            await self.context.add_cookies(session_data['cookies'])
            print("Tweet_injest Session restored from file")
            page = await self.context.new_page()
            await page.goto(X_URL)
        else:
            print("Tweet_injest Session file does not exist, performing manual login")
            page = await self.context.new_page()
            await page.goto(X_LOGIN_URL)
            print("Tweet_injest Username input")
            await human_like_typing(page, 'div[aria-labelledby="modal-header"] input[name="text"]', os.getenv('X_USERNAME'))
            await page.click('div[aria-labelledby="modal-header"] span:has-text("Next")')


            await page.wait_for_timeout(5000)
            login_button = await page.query_selector('div[aria-labelledby="modal-header"] span:has-text("Log in")')
            if login_button:
                print("Tweet_injest Login button found, clicking it")
                await human_like_typing(page, 'div[aria-labelledby="modal-header"] input[name="password"]', os.getenv('X_PASSWORD'))
                await page.click('div[aria-labelledby="modal-header"] span:has-text("Log in")')
            else:
                print("Tweet_injest Login button not found, entering phone number and password")
                await human_like_typing(page, 'div[aria-labelledby="modal-header"] input[name="text"]', os.getenv('X_PHONE_NUMBER'))
                await page.click('div[aria-labelledby="modal-header"] span:has-text("Next")')
                await human_like_typing(page, 'div[aria-labelledby="modal-header"] input[name="password"]', os.getenv('X_PASSWORD'))
                await page.click('div[aria-labelledby="modal-header"] span:has-text("Log in")')
         
            try:
                await page.wait_for_load_state("networkidle")
                await page.wait_for_url(X_LOGIN_REDIRECT_URL, timeout=30000)
                print("Tweet_injest Successfully logged in to X")
                await save_session(self.context, x_session_file)
            except Exception as e:
                print(f"Tweet_injest Error during login redirection: {e}")

    def insert_tweet(self, tweet_data):
        try:
            # tweet_data_copy = tweet_data.copy()
            # tweet_data_copy.pop('image_data', None)
            # print(f"Inserting tweet: {tweet_data_copy}")

            tweet_text = tweet_data.get('text', '')
            tweet_url = tweet_data.get('tweetLink', '')
            profile_link = tweet_data.get('profileLink', '')
            timestamp = tweet_data.get('time', None)
            screenshot_data = tweet_data.get('image_data', None)

            # Check if tweet with the same tweet_url already exists
            check_sql = "SELECT id FROM tweets WHERE tweet_url = %s"
            cursor = self.db.cursor()
            cursor.execute(check_sql, (tweet_url,))
            existing_tweet = cursor.fetchone()

            if existing_tweet:
                logging.info(f"Tweet with link {tweet_url} already exists. Skipping insertion.")
                cursor.close()
                return

            # Generate text embedding
            text_embedding = self.embedding_service.embed_text([tweet_text])[0]

            # Insert tweet data into 'tweets' table
            tweet_sql = """
            INSERT INTO tweets (tweet_text, tweet_url, profile_link, timestamp, text_embedding)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """
            tweet_values = (tweet_text, tweet_url, profile_link, timestamp, text_embedding)
            cursor.execute(tweet_sql, tweet_values)
            tweet_id = cursor.fetchone()[0]  # Get the auto-generated tweet ID
            self.db.commit()
            cursor.close()
            logging.info(f"Inserted tweet with ID: {tweet_id}")
        except Exception as e:
            logging.error(f"Error inserting tweet data: {e}")
            self.db.rollback()

    async def scrape_tweet(self, url: str) -> dict:
        _xhr_calls = []

        async def intercept_response(response):
            if response.request.resource_type == "xhr":
                _xhr_calls.append(response)
            return response

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 700, "height": 3000}, user_agent="Chrome/90.0.4430.93")
            page = await context.new_page()
            page.on("response", intercept_response)
            await page.goto(url)

            try:
                await page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                return None
            
            # Check if the page contains the text indicating the tweet doesn't exist
            if await page.locator("text=Hmm...this page doesn’t exist. Try searching for something else.").count() > 0:
                logging.info(f"Tweet does not exist: {url}")
                return None

            tweet_id = url.split("/")[-1]
            try:
                image_data = await page.locator('[data-testid="tweet"]').screenshot(timeout=300)
            except Exception as e:
                logging.error(f"Screenshot failed: {e} - {url}")
                try:
                    image_data = await page.locator('[data-testid="primaryColumn"]').screenshot(timeout=300)
                except Exception as e:
                    logging.error(f"Screenshot of primaryColumn also failed: {e} - {url}")
                    return None

            tweet_data = await self.collect_background_calls(_xhr_calls)
            tweet_data['image_data'] = image_data
            tweet_data['url'] = url
            tweet_data['tweet_id'] = tweet_id
            await self.insert_tweet_extended(tweet_data)
            return tweet_data

    async def insert_tweet_extended(self, tweet_data):
        try:
            # print({k: v for k, v in tweet_data.items() if k != 'image_data'})
            # tweet_id = tweet_data.get('tweet_id')
            url = tweet_data.get('url')
            user_id = tweet_data.get('user', {}).get('id')
            user_name = tweet_data.get('user', {}).get('name')
            user_screen_name = tweet_data.get('user', {}).get('screen_name')
            created_at = tweet_data.get('created_at')
            image_data = tweet_data.get('image_data')


            # Update the existing tweet row in tweets with tweet_json
            tweet_json = json.dumps({k: v for k, v in tweet_data.items() if k != 'image_data'})
            tweet_sql = """
            UPDATE tweets
            SET tweet_json = %s
            WHERE tweet_url = %s
            RETURNING id
            """
            tweet_values = (tweet_json, url)
            cursor = self.db.cursor()
            cursor.execute(tweet_sql, tweet_values)
            tweet_id = cursor.fetchone()[0]
            # Insert image data into the database
            if image_data:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(image_data)
                    temp_file_path = temp_file.name
                    image_embedding = self.embedding_service.embed_image(temp_file_path)[0]

                image_sql = """
                INSERT INTO tweet_images (tweet_id, url, image_data, image_embedding)
                VALUES (%s, %s, %s, %s)
                """
                image_values = (tweet_id, url, image_data, image_embedding)
                cursor.execute(image_sql, image_values)

            # Commit the transaction
            self.db.commit()
        except Exception as e:
            logging.error(f"Failed to insert tweet data: {e}")
            self.db.rollback()


    async def collect_background_calls(self, _xhr_calls):
        tweet_calls = [f for f in _xhr_calls if "TweetResultByRestId" in f.url]
        for xhr in tweet_calls:
            data = await xhr.json()
            return data['data']['tweetResult']['result']

    async def scrape_tweets(self):
        page = await self.context.new_page()
        await page.goto(X_LIKES_URL)

        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception as e:
            logging.warning(f"Network idle timeout reached, continuing with scraping: {e}")

        js_code = """
        let processedTweetBlocks = new Set();
        let savedTweets = [];

        function extractTweetInfo(tweetBlock) {
            const tweetTextElement = tweetBlock.querySelector('[data-testid="tweetText"]');
            const tweetText = tweetTextElement ? tweetTextElement.innerText : "Tweet text not found";

            const profileLinkElement = tweetBlock.querySelector('[role="link"]');
            const profileLink = profileLinkElement ? profileLinkElement.href : "Profile link not found";

            const timeElement = tweetBlock.querySelector('time');
            const tweetLinkElement = timeElement ? timeElement.closest('a') : null;
            const tweetLink = tweetLinkElement ? tweetLinkElement.href : "Tweet link not found";

            const time = timeElement ? timeElement.getAttribute('datetime') : "Time not found";
            
            return { text: tweetText, profileLink, tweetLink, time };
        }

        function saveTweet(tweetInfo) {
            savedTweets.push(tweetInfo);
        }

        function scanAndExtract() {
            const tweetBlocks = document.querySelectorAll('article[data-testid="tweet"]');
            let newTweetsFound = 0;
            tweetBlocks.forEach(tweetBlock => {
                const tweetBlockId = tweetBlock.getAttribute('aria-labelledby');
                const hash = tweetBlockId ? hashString(tweetBlockId) : null;
                if (hash && !processedTweetBlocks.has(hash)) {
                    processedTweetBlocks.add(hash);
                    const tweetInfo = extractTweetInfo(tweetBlock);
                    saveTweet(tweetInfo);
                    newTweetsFound++;
                }
            });
            return newTweetsFound;
        }

        function hashString(str) {
            let hash = 0;
            if (str.length === 0) {
                return hash;
            }
            for (let i = 0; i < str.length; i++) {
                const char = str.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            return hash;
        }
        
        function getSavedTweets() {
            return savedTweets;
        }
        """
        await page.evaluate(js_code)
        no_new_tweets_count = 0
        wait_for_x_tweets = 100
        while True:
            await page.evaluate("() => scanAndExtract()")
            all_tweets = await page.evaluate("() => getSavedTweets()")

            # Fetch existing tweets from the database
            cursor = self.db.cursor()
            cursor.execute("SELECT tweet_url FROM tweets")
            existing_tweets = cursor.fetchall()
            existing_tweets = [tweet[0] for tweet in existing_tweets]

            new_tweets = [tweet for tweet in all_tweets if tweet['tweetLink'] not in existing_tweets]

            if len(new_tweets) == 0:
                no_new_tweets_count += 1
            else:
                no_new_tweets_count = 0

            logging.info(
                f"Found {len(new_tweets)} new tweets. Total tweets: {len(all_tweets)}. No new tweets count: {no_new_tweets_count}")

            if no_new_tweets_count > wait_for_x_tweets:
                logging.info(f"No new tweets found for {wait_for_x_tweets} consecutive times. Stopping.")
                break

            for tweet in new_tweets:
                self.insert_tweet(tweet)

            await random_scroll(page)
            await page.wait_for_timeout(random.randint(50, 200))

    async def screenshot_all_tweets(self):
        # Query for all tweet links from the tweets table
        cursor = self.db.cursor()
        cursor.execute("SELECT id, tweet_url FROM tweets")
        tweets = cursor.fetchall()

        for tweet_id, tweet_url in tweets:
            # Check if there is a corresponding screenshot in the tweet_images table
            cursor.execute("SELECT 1 FROM tweet_images WHERE tweet_id = %s", (tweet_id,))
            if cursor.fetchone() is None:
                # If no corresponding screenshot, download it with scrape_tweet
                tweet_data = await self.scrape_tweet(tweet_url)
                if tweet_data and tweet_data.get('time', False):
                    self.insert_tweet(tweet_data)

        cursor.close()

async def save_session(context, filename):
    storage_state = await context.storage_state()
    with open(filename, "w") as f:
        json.dump(storage_state, f)

async def load_session(context, filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            storage_state = json.load(f)
        await context.add_cookies(storage_state.get('cookies', []))
        await context.add_storage_state(storage_state)
        return True
    return False

async def human_like_typing(page, selector, text):
    for char in text:
        await page.type(selector, char)
        await asyncio.sleep(random.uniform(0.1, 0.24))

async def random_scroll(page):
    await page.evaluate("""
        () => {
            const scrollAmount = Math.floor(Math.random() * 100) + window.innerHeight;
            window.scrollBy(0, scrollAmount);
        }
    """)

async def setup_browser(playwright: Playwright):
    user_agent = random.choice(USER_AGENTS)
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={'width': 1920, 'height': 1080},
        geolocation={'longitude': 40.7128, 'latitude': -74.0060},
        locale='en-US',
        timezone_id='America/New_York',
        permissions=['geolocation']
    )

    await context.add_init_script("""
        () => {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => Math.floor(Math.random() * 8) + 2
            });
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => Math.floor(Math.random() * 8) + 2
            });
        }
    """)

    return browser, context