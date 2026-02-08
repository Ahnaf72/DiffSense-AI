import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

class FaissIndex:
    def __init__(self):
        self.index = faiss.IndexFlatL2(384)
        self.sentences = []
        self.sources = []

    def add(self, sentences, source_name):
        embeddings = model.encode(sentences)
        self.index.add(np.array(embeddings))
        self.sentences.extend(sentences)
        self.sources.extend([source_name]*len(sentences))

    def search(self, query, k=3):
        q_emb = model.encode([query])
        D, I = self.index.search(np.array(q_emb), k)
        results = []
        for idx in I[0]:
            results.append((self.sentences[idx], self.sources[idx]))
        return results
