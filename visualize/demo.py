import matplotlib.pyplot as plt
import numpy as np
import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

def fetch_embeddings():
    try:
        # Connect to your postgres DB using environment variables
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )

        # Open a cursor to perform database operations
        cur = conn.cursor()

        # Execute a query to fetch embeddings
        cur.execute("SELECT embedding FROM public.emails")

        # Retrieve query results
        embeddings = cur.fetchall()

        # Close communication with the database
        cur.close()
        conn.close()

        return np.array([np.array(e[0]) for e in embeddings])

    except Exception as e:
        print(f"Error fetching embeddings: {e}")
        return None

def visualize_embeddings(embeddings):
    if embeddings is None or len(embeddings) == 0:
        print("No embeddings to visualize.")
        return

    # Assuming embeddings are 2D for simplicity. If not, you might need to use dimensionality reduction techniques like PCA or t-SNE.
    if embeddings.shape[1] != 2:
        print("Embeddings are not 2D. Please use dimensionality reduction techniques.")
        return

    plt.scatter(embeddings[:, 0], embeddings[:, 1])
    plt.title("Email Embeddings Visualization")
    plt.xlabel("Dimension 1")
    plt.ylabel("Dimension 2")
    plt.show()

if __name__ == "__main__":
    embeddings = fetch_embeddings()
    visualize_embeddings(embeddings)

