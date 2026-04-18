import os
import dotenv
from langchain_experimental.text_splitter import SemanticChunker
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from langchain_chroma import Chroma
from chromadb.config import Settings
from csv_process import loader

dotenv.load_dotenv(dotenv_path=".env")
VECTOR_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vector_store")

CHROMA_SETTINGS = Settings(
    anonymized_telemetry=False,
    chroma_product_telemetry_impl="chroma_telemetry_noop.NoOpProductTelemetryClient",
    is_persistent=True,
    persist_directory=VECTOR_STORE_DIR,
)


def create_vector_store(documents, batch_size=100):
    import time

    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    total_batches = (len(documents) - 1) // batch_size + 1

    # Check if a store already exists (resume support)
    chroma_db = os.path.join(VECTOR_STORE_DIR, "chroma.sqlite3")
    if os.path.exists(chroma_db):
        vector_store = Chroma(
            embedding_function=embeddings,
            collection_name="default",
            collection_metadata={"hnsw:space": "cosine"},
            client_settings=CHROMA_SETTINGS,
        )
        existing = vector_store._collection.count()
        print(f"  Resuming — {existing} docs already in store")
    else:
        # Create with the first batch
        first_batch = documents[:batch_size]
        vector_store = Chroma.from_documents(
            documents=first_batch,
            embedding=embeddings,
            collection_metadata={"hnsw:space": "cosine"},
            client_settings=CHROMA_SETTINGS,
        )
        existing = len(first_batch)
        print(f"  Batch 1/{total_batches} — {len(first_batch)} docs embedded")

    # Figure out which batch to start from
    start_index = existing
    for i in range(start_index, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        batch_num = i // batch_size + 1

        # Retry loop for transient API errors
        for attempt in range(1, 4):
            try:
                vector_store.add_documents(batch)
                print(f"  Batch {batch_num}/{total_batches} — {len(batch)} docs embedded")
                break
            except Exception as e:
                if attempt < 3:
                    wait = 5 * attempt
                    print(f"  Batch {batch_num} failed (attempt {attempt}/3): {e}")
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  Batch {batch_num} failed after 3 attempts: {e}")
                    raise

    print(f"Total documents in store: {vector_store._collection.count()}")
    return vector_store

def main():
    print("Starting vector store creation...")
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
    chroma_db = os.path.join(VECTOR_STORE_DIR, "chroma.sqlite3")
    if not os.path.exists(chroma_db):
        print("Vector store not found. Creating...")
        documents = loader.load()
        print(f"Loaded {len(documents)} documents.")
        vector_store = create_vector_store(documents)
    else:
        retriever = Chroma(
            embedding_function=GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001"),
            collection_name="default",
            client_settings=CHROMA_SETTINGS,
        ).as_retriever()

if __name__ == "__main__":
    main()