import os
import requests
import psycopg2
import json

GOTIFY_URL = os.getenv("GOTIFY_URL")
GOTIFY_AUTH_TOKEN = os.getenv("GOTIFY_AUTH_TOKEN")

# Extras can open url on notification click
# https://gotify.net/docs/msgextras
def send_gotify_message(title, message, priority=5, extras=None):
    url = f"{GOTIFY_URL}/message?token={GOTIFY_AUTH_TOKEN}"
    
    if extras and "client::notification" in extras and "click" in extras["client::notification"]:
        click_url = extras["client::notification"]["click"].get("url")
        if click_url:
            extras["client::notification"]["click"]["url"] = f"{os.getenv('GOTIFY_CLICK_DESTINATION_BASE_URL')}{click_url}"
    
    data = {
        'title': title,
        'message': message,
        'priority': priority,
        'extras': extras or {}
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, data=json.dumps(data), headers=headers)
    except requests.RequestException as e:
        print(f"Error sending Gotify message: {e}")
        return None
    
    log_gotify_message(title, message, priority, response.status_code, extras)
    
    return response

def log_gotify_message(title, message, priority, status_code, extras):
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO public.gotify_message_log (message, sent_at, parameters, device_id)
        VALUES (%s, CURRENT_TIMESTAMP, %s, NULL)
        """
        parameters = {
            'title': title,
            'message': message,
            'priority': priority,
            'status_code': status_code,
            'extras': extras
        }
        cursor.execute(insert_query, (message, json.dumps(parameters)))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Error logging gotify message: {e}")
    finally:
        if conn is not None:
            conn.close()

# Example usage
if __name__ == "__main__":
    extras = {
        "client::display": {
            "contentType": "text/plain"
        },
        "client::notification": {
            "click": { "url": "https://gotify.net" }
        }
    }
    response = send_gotify_message("Test Title", "Test Message", extras=extras)
    print(response.status_code, response.text)
