import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# read all txt files in this folder
student_files = [doc for doc in os.listdir() if doc.endswith('.txt')]
student_notes = [open(file, encoding='utf-8').read() for file in student_files]

def vectorize(texts):
    return TfidfVectorizer().fit_transform(texts).toarray()

def similarity(vec1, vec2):
    return cosine_similarity([vec1, vec2])[0][1]

vectors = vectorize(student_notes)
file_vectors = list(zip(student_files, vectors))

def check_plagiarism():
    results = []
    for i in range(len(file_vectors)):
        for j in range(i + 1, len(file_vectors)):
            file1, vec1 = file_vectors[i]
            file2, vec2 = file_vectors[j]
            score = similarity(vec1, vec2)
            results.append((file1, file2, score))
    return results

for result in check_plagiarism():
    print(result)
