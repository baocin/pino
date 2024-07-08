import json
import os
import random
import time
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Playwright
import asyncio
import requests
import requests

# Load environment variables
load_dotenv()

# Constants
X_URL = "https://x.com"
X_LOGIN_URL = "https://x.com/i/flow/login"
X_LIKES_URL = "https://x.com/baocin/likes"
X_LOGIN_REDIRECT_URL = "https://x.com/home"
X_TWEET_FILE = 'tweets.json'
X_TWEET_FILE_WITH_DATA = 'tweets_with_data.json'

# User agents list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36"
]


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


async def login_x(page):
    await page.goto(X_LOGIN_URL)
    await human_like_typing(page, 'input[name="text"]', os.getenv('X_USERNAME'))
    await page.click('span:has-text("Next")')
    await human_like_typing(page, 'input[name="password"]', os.getenv('X_PASSWORD'))
    await page.click('span:has-text("Log in")')
    await page.wait_for_load_state("networkidle")
    # Wait for redirect after login
    # 30 seconds timeout
    await page.wait_for_url(X_LOGIN_REDIRECT_URL, timeout=30000)
    print("Successfully logged in to X")


async def scrape_tweet(url: str) -> dict:
    """
    Scrape a single tweet page for Tweet thread e.g.:
    https://twitter.com/Scrapfly_dev/status/1667013143904567296
    Return parent tweet, reply tweets and recommended tweets
    """
    _xhr_calls = []

    async def intercept_response(response):
        """capture all background requests and save them"""
        # we can extract details from background requests
        if response.request.resource_type == "xhr":
            _xhr_calls.append(response)
        return response

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 700, "height": 3000}, user_agent="Chrome/90.0.4430.93")
        page = await context.new_page()

        # enable background request intercepting:
        page.on("response", intercept_response)

        # go to url and wait for the page to load
        await page.goto(url)

        # Check if the page doesn't exist

        # Wait for all network requests to finish (images, video, etc)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            return None

        try:
            await page.wait_for_selector("article[data-testid='tweet']", timeout=20000)
        except Exception:
            return {
                "code": 404,
                "message": "Tweet not found"
            }

        # screenshot the page
        tweet_id = url.split("/")[-1]
        screenshot_path = f"img/{tweet_id}.png"
        try:
            os.mkdir("img")
        except FileExistsError:
            pass

        try:
            await page.locator('[data-testid="tweet"]').screenshot(path=screenshot_path)
        except Exception as e:
            print(f"Screenshot failed: {e}")
            return {
                "code": 500,
                "message": "Screenshot failed"
            }
        # Collect background calls and return the result
        tweet_data = await collect_background_calls(_xhr_calls)
        return tweet_data


async def collect_background_calls(_xhr_calls):
    # find all tweet background requests:
    tweet_calls = [f for f in _xhr_calls if "TweetResultByRestId" in f.url]
    for xhr in tweet_calls:
        data = await xhr.json()
        return data['data']['tweetResult']['result']

async def scrape_tweets(page):
    await page.goto(X_LIKES_URL)

    # Wait for network idle, but don't crash if it times out
    try:
        await page.wait_for_load_state("networkidle", timeout=4000)
    except Exception as e:
        print(f"Network idle timeout reached, continuing with scraping: {e}")

    # Inject the JavaScript code
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
    # Load existing tweets from file
    try:
        with open(X_TWEET_FILE, 'r') as f:
            existing_tweets = json.load(f)
    except Exception as e:
        print(f"Error loading existing tweets: {e}")
        existing_tweets = []
    no_new_tweets_count = 0
    while True:
        await page.evaluate("() => scanAndExtract()")
        all_tweets = await page.evaluate("() => getSavedTweets()")
        new_tweets = [tweet for tweet in all_tweets if existing_tweets is None or not any(
            existing_tweet['tweetLink'] == tweet['tweetLink'] for existing_tweet in existing_tweets)]

        if len(new_tweets) == 0:
            no_new_tweets_count += 1
        else:
            no_new_tweets_count = 0

        print(
            f"Found {len(new_tweets)} new tweets. Total tweets: {len(all_tweets)}. No new tweets count: {no_new_tweets_count}")

        if no_new_tweets_count > 50:
            print("No new tweets found for 200 consecutive times. Stopping.")
            break

        existing_tweets.extend(new_tweets)
        with open(X_TWEET_FILE, 'w') as f:
            json.dump(existing_tweets, f, indent=4)

        # Scroll down using the random_scroll function
        await random_scroll(page)

        # Wait for new content to load
        await page.wait_for_timeout(random.randint(50, 300))


async def setup_browser(playwright: Playwright):
    user_agent = random.choice(USER_AGENTS)
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={'width': 1920, 'height': 1080},
        geolocation={'longitude': 40.7128, 'latitude': -74.0060},
        locale='en-US',
        timezone_id='America/New_York',
        permissions=['geolocation']
    )

    # Randomize fingerprint
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


async def main():
    async with async_playwright() as p:
        browser, context = await setup_browser(p)

        x_session_file = "x_session.json"
        if os.path.exists(x_session_file):
            with open(x_session_file, 'r') as f:
                session_data = json.load(f)
            await context.add_cookies(session_data['cookies'])
            print("Session restored from file.")
            page = await context.new_page()
            await page.goto(X_URL)
        else:
            page = await context.new_page()
            await login_x(page)
            await save_session(context, x_session_file)

        await scrape_tweets(page)

        # Load tweets from tweets.json
        with open(X_TWEET_FILE, 'r') as f:
            tweets = json.load(f)
            if not os.path.exists(X_TWEET_FILE_WITH_DATA):
                print("Creating tweets_with_data.json")
                with open(X_TWEET_FILE_WITH_DATA, 'w') as f:
                    json.dump(tweets, f, indent=4)


        with open(X_TWEET_FILE_WITH_DATA, 'r') as f:
            tweets = json.load(f)

        # Calculate total number of tweets
        total_tweets = len(tweets)
        print(f"Total number of tweets: {total_tweets}")
        processed_tweets = 0

        # Scrape individual tweets
        async def scrape_tweet_task(tweet):
            nonlocal processed_tweets
            processed_tweets += 1
            print(f"Processed {processed_tweets} of {total_tweets} tweets")
            tweet_url = tweet['tweetLink']
            if not tweet_url:
                return
            tweet_id = tweet_url.split('/')[-1]

            # Check if the tweet has already been scraped
            # print(tweet)
            if 'scraped_data' in tweet:
                print(f"Tweet {tweet_id} already scraped. Skipping.")
                return

            print(f"Scraping tweet: {tweet_id}")
            tweet_data = await scrape_tweet(tweet_url)

            if tweet_data:
                # Add the scraped data to the tweet dictionary
                tweet['scraped_data'] = tweet_data
                tweet['image_path'] = f"img/{tweet_id}.png"
                print(f"Successfully scraped tweet {tweet_id}")
                async with asyncio.Lock():
                    with open(X_TWEET_FILE_WITH_DATA, 'w') as f:
                        json.dump(tweets, f, indent=4)
            else:
                print(f"Failed to scrape tweet {tweet_id}")

        # Define chunk size for processing tweets
        chunk_size = 10

        # Create a list of tasks to execute concurrently
        # Limit to chunk_size tweets at a time
        tasks = [scrape_tweet_task(tweet) for tweet in tweets[:chunk_size]]

        # Execute tasks concurrently
        await asyncio.gather(*tasks)

        # Process remaining tweets in batches of chunk_size
        for i in range(chunk_size, len(tweets), chunk_size):
            tasks = [scrape_tweet_task(tweet)
                     for tweet in tweets[i:i+chunk_size]]
            await asyncio.gather(*tasks)

        # Add a random delay between batches to avoid rate limiting
        # await asyncio.sleep(random.uniform(5, 10))

        # Save the updated tweets with scraped data back to the JSON file
        with open('out.json', 'w') as f:
            json.dump(tweets, f, indent=4)

        print(
            f"Updated {len(tweets)} tweets with scraped data in tweets_with_data.json")

        await browser.close()

    print(f"Scraped {len(tweets)} tweets and saved to tweets.json")


if __name__ == "__main__":
    asyncio.run(main())
