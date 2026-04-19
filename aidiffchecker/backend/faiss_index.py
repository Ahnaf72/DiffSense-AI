import faiss
import numpy as np

index = None
documents = []

def build_index(embeddings, docs):
    global index, documents
    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings))
    documents = docs


def search(query_embedding, k=5):
    D, I = index.search(np.array([query_embedding]), k)
    return [documents[i] for i in I[0]]