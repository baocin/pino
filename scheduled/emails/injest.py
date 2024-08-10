import imaplib
import email
from email.header import decode_header
import os
from datetime import datetime
import logging
import psycopg2
from embedding import EmbeddingService

# Configure logging
logging.basicConfig(filename='mail.log', level=logging.INFO, 
                    format='%(asctime)s - emails - %(levelname)s - %(message)s')

class EmailInjest:
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
        all_accounts = [
            {"email": os.getenv("EMAIL_1"), "password": os.getenv("PASSWORD_1"), "imap_server": os.getenv("IMAP_SERVER_1"), "port": int(os.getenv("PORT_1")), "disabled": os.getenv("DISABLED_1")},
            {"email": os.getenv("EMAIL_2"), "password": os.getenv("PASSWORD_2"), "imap_server": os.getenv("IMAP_SERVER_2"), "port": int(os.getenv("PORT_2")), "disabled": os.getenv("DISABLED_2")},
            {"email": os.getenv("EMAIL_3"), "password": os.getenv("PASSWORD_3"), "imap_server": os.getenv("IMAP_SERVER_3"), "port": int(os.getenv("PORT_3")), "disabled": os.getenv("DISABLED_3")},
        ]
        self.accounts = [account for account in all_accounts if account["disabled"] != "true"]

    def fetch_all_emails(self):
        for account in self.accounts:
            self.fetch_mail(account)

    def fetch_mail(self, account):
        try:
            # Connect to the server
            mail = imaplib.IMAP4_SSL(account["imap_server"])
            # Login to the account
            mail.login(account["email"], account["password"])
            # Select the mailbox you want to check
            mail.select("inbox")

            # Search for all unseen emails in the inbox first
            status, unseen_messages = mail.search(None, "UNSEEN")

            # Search for all emails in the inbox
            status, all_messages = mail.search(None, "ALL")

            if unseen_messages[0] != b'':
                logging.info(f"unseen_messages: {unseen_messages}")
            # if all_messages[0] != b'':
            #     logging.info(f"all_messages: {all_messages}")

            # Combine and deduplicate email IDs
            combined_messages = list(set(unseen_messages[0].split() + all_messages[0].split()))
            messages = (status, combined_messages)

            # logging.info(f"combined_messages: {combined_messages}")
            
            # Convert messages to a list of email IDs
            email_ids = unseen_messages[0].split()
            logging.info(f"email_ids len: {len(email_ids)}")

            # Query for the highest pull_id
            pull_id = self.get_last_pull_id() + 1

            for email_id in email_ids:
                email_id_str = email_id.decode()

                # Check if the email already exists in the database
                if self.email_exists(email_id_str):
                    # logging.info(f"Email {email_id_str} already exists in the database. Skipping download.")
                    continue

                # Fetch the email by ID
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        try:
                            # Parse the email content
                            msg = email.message_from_bytes(response_part[1])
                            # Decode the email subject
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                try:
                                    subject = subject.decode(encoding if encoding else "utf-8")
                                except UnicodeDecodeError:
                                    subject = subject.decode(encoding if encoding else "latin1")
                            # Decode the email sender
                            from_ = msg.get("From")
                            # logging.info(f"Subject: {subject}")
                            # logging.info(f"From: {from_}")

                            # Get the date of receive
                            date_tuple = email.utils.parsedate_tz(msg["Date"])
                            if date_tuple:
                                local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                                date_str = local_date.strftime("%Y-%m-%d")

                            # Initialize the email body and attachments
                            email_body = ""
                            attachments = []

                            # If the email message is multipart
                            if msg.is_multipart():
                                for part in msg.walk():
                                    # Extract content type of email
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))

                                    try:
                                        # Get the email body
                                        body = part.get_payload(decode=True).decode()
                                    except:
                                        pass

                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        # Append text/plain emails to email body
                                        email_body += f"{body}\n\n"
                                    elif "attachment" in content_disposition:
                                        # Download attachment
                                        filename = part.get_filename()
                                        if filename:
                                            attachments.append(psycopg2.Binary(part.get_payload(decode=True)))
                            else:
                                # Extract content type of email
                                content_type = msg.get_content_type()

                                # Get the email body
                                body = msg.get_payload(decode=True).decode()
                                if content_type == "text/plain":
                                    # Append text email parts to email body
                                    email_body += f"{body}\n\n"

                            # Get the read status and timestamp
                            seen = False
                            status, flags_data = mail.fetch(email_id, "(FLAGS)")
                            # logging.info(f"Status: {status}")
                            # logging.info(f"Flags Data: {flags_data}")
                            if status == "OK":
                                flags = flags_data[0].decode()
                                if "\\Seen" in flags:
                                    seen = True

                            # Define receiver as the person who received the email
                            receiver = account["email"]

                            # Generate embedding for the email body
                            embedding = self.embedding_service.embed_text([f"Subject: {subject} From: {from_} To: {receiver} Body: {email_body}"])[0]
                            # Insert the email data into the database
                            self.insert_email_data(email_id_str, subject, from_, local_date, email_body, attachments, seen, receiver, pull_id, embedding)
                        except Exception as e:
                            logging.error(f"Error parsing email {email_id_str}: {e}")
                            continue
            # Close the connection and logout
            mail.close()
            mail.logout()
        except Exception as e:
            logging.error(f"Error fetching mail for {account['email']}: {e}")

    def get_last_pull_id(self):
        sql = "SELECT COALESCE(MAX(pull_id), 0) FROM emails"
        cursor = self.db.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else 0

    def insert_email_data(self, email_id, subject, sender, date_received, body, attachments, seen, receiver, pull_id, embedding):
        sql = """
        INSERT INTO emails (email_id, subject, sender, date_received, body, attachments, seen, receiver, pull_id, source_email_address, embedding, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, DEFAULT)
        """
        values = (
            email_id,
            subject,
            sender,
            date_received,
            body,
            attachments,
            seen,
            receiver,
            pull_id,
            receiver,  # Assuming source_email_address is the same as receiver
            embedding  # Convert embedding to list for vector type
        )
        cursor = self.db.cursor()
        cursor.execute(sql, values)
        self.db.commit()
        cursor.close()

    def email_exists(self, email_id):
        sql = "SELECT 1 FROM emails WHERE email_id = %s"
        cursor = self.db.cursor()
        cursor.execute(sql, (email_id,))
        result = cursor.fetchone()
        cursor.close()
        return result is not None
