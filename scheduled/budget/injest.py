import requests
import os
import logging
from embedding import EmbeddingService
import uuid

# Configure logging
logging.basicConfig(filename='budget.log', level=logging.INFO, 
                    format='%(asctime)s - budget - %(levelname)s - %(message)s')

class BudgetInjest:
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

    def fetch_budget(self):
        url = os.getenv("GOOGLE_DOC_URL")
        try:
            response = requests.get(url)
            response.raise_for_status()
            self.insert_document_into_db(response.content, response.text)
            
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Error downloading the file: {e}")

    # Function to create directories if they do not exist
    def make_dirs_if_needed(self, path):
        if not os.path.exists(path):
            os.makedirs(path)
            logging.info(f"Created directories for path: {path}")
        else:
            logging.info(f"Directories for path: {path} already exist")

    # Function to insert the document into the database
    def insert_document_into_db(self, document_bytes, document_text):
        cursor = self.db.cursor()
        try:
            document_name = os.getenv("GOOGLE_DOC_NAME", "Unnamed Document")

            # Check if a document with the same name exists
            cursor.execute("SELECT id FROM documents WHERE name = %s", (document_name,))
            existing_document = cursor.fetchone()
            embedding = self.embedding_service.embed_text([document_text])[0]

            if existing_document:
                # Update the existing document
                sql = """
                UPDATE documents
                SET document_bytes = %s, document_text = %s, embedding = %s, created_at = NOW()
                WHERE id = %s
                """
                values = (document_bytes, document_text, embedding, existing_document[0])
                cursor.execute(sql, values)
                logging.info(f"Document with name '{document_name}' updated in the database with ID: {existing_document[0]}")
            else:
                # Insert a new document
                sql = """
                INSERT INTO documents (id, name, document_bytes, document_text, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """
                document_id = str(uuid.uuid4())
                values = (document_id, document_name, document_bytes, document_text, embedding)
                cursor.execute(sql, values)
                logging.info(f"Document inserted into the database with ID: {document_id}")

            self.db.commit()
        except Exception as e:
            logging.error(f"Error inserting document into the database: {e}")
        finally:
            cursor.close()
