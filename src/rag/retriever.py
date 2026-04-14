import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

RAG_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db")
POLICY_TXT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "expense_policies.txt")

def init_retriever():
    """Initializes the Chroma Vector Database retriever."""
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    if not os.path.exists(POLICY_TXT_FILE):
        print(f"Warning: Policy file not found at {POLICY_TXT_FILE}. Returning empty Chroma DB.")
        return Chroma(collection_name="policies", embedding_function=embeddings, persist_directory=RAG_DB_DIR).as_retriever()

    vectorstore = Chroma(
        collection_name="policies",
        embedding_function=embeddings,
        persist_directory=RAG_DB_DIR
    )

    # Check if empty, then populate
    try:
        col_data = vectorstore.get()
        if len(col_data['ids']) == 0:
            print("Chroma DB empty. Indexing policies...")
            loader = TextLoader(POLICY_TXT_FILE)
            documents = loader.load()
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
            docs = text_splitter.split_documents(documents)
            vectorstore.add_documents(docs)
            print("Policies successfully indexed into Vector DB.")
    except Exception as e:
        print(f"Error initializing vector store: {e}")

    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
    return retriever

# Single ton instance
policy_retriever = None
try:
    policy_retriever = init_retriever()
except Exception as e:
    print(f"Error configuring explicit retriever: {e}")

def get_policy_retriever():
    global policy_retriever
    if policy_retriever is None:
        policy_retriever = init_retriever()
    return policy_retriever
