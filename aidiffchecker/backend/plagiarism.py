from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("all-MiniLM-L6-v2")

def similarity_score(a, b):
    e1 = model.encode([a])
    e2 = model.encode([b])
    return cosine_similarity(e1, e2)[0][0]

def classify(score):
    if score > 0.9:
        return "Copied"
    elif score > 0.75:
        return "Paraphrased"
    return "Original"
