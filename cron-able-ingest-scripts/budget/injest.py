import requests
import os
import logging
from dotenv import load_dotenv
from embedding import EmbeddingService
import uuid

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='budget.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

class BudgetInjest:
    def __init__(self,db_interface):
        self.db = db_interface
        self.embedding_service = EmbeddingService()

    def fetch_budget(self):
        url = os.getenv("GOOGLE_DOC_URL")
        # self.make_dirs_if_needed(os.path.dirname(save_path))
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
            sql = """
            INSERT INTO documents (id, name, document_bytes, document_text, embedding, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (name) DO UPDATE SET
                document_bytes = EXCLUDED.document_bytes,
                document_text = EXCLUDED.document_text,
                embedding = EXCLUDED.embedding,
                created_at = NOW()
            """
            document_id = str(uuid.uuid4())
            document_name = os.getenv("GOOGLE_DOC_NAME", "Unnamed Document")
            embedding = self.embedding_service.embed_text([document_text])[0]
            values = (document_id, document_name, document_bytes, document_text, embedding)
            cursor.execute(sql, values)
            self.db.commit()
            logging.info(f"Document inserted or updated in the database with name: {document_name}")
        except Exception as e:
            logging.error(f"Error inserting or updating document in the database: {e}")
        finally:
            cursor.close()
            self.db.close()
