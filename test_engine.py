import sys, os
os.chdir(r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')
sys.path.insert(0, r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')

import fitz

# Create reference PDF
ref_dir = 'backend/data/reference_pdfs'
os.makedirs(ref_dir, exist_ok=True)

doc = fitz.open()
page = doc.new_page()
text_blocks = [
    'The quick brown fox jumps over the lazy dog. This is a sample paragraph that contains unique content about artificial intelligence and machine learning algorithms.',
    'Neural networks are computational models inspired by the human brain. They consist of layers of interconnected nodes that process information using connectionist approaches.',
    'Deep learning has revolutionized natural language processing. Transformer architectures like BERT and GPT have achieved remarkable results on various benchmarks.',
    'The gradient descent optimization algorithm is fundamental to training machine learning models. It iteratively adjusts parameters to minimize the loss function.',
    'Convolutional neural networks are particularly effective for image recognition tasks. They use filters to detect features such as edges, textures and patterns.',
]
page.insert_text((72, 72), '\n'.join(text_blocks), fontsize=11)
ref_path = os.path.join(ref_dir, 'reference_paper.pdf')
doc.save(ref_path)
doc.close()

# Create student PDF with various types of plagiarism
doc2 = fitz.open()
page2 = doc2.new_page()
student_text = [
    'The quick brown fox jumps over the lazy dog. This is a sample paragraph that contains unique content about artificial intelligence and machine learning algorithms.',
    'Neural networks serve as computing frameworks modeled after the human mind. These systems feature tiers of linked processing units that handle data through connectionist methods.',
    'Modern language understanding has been transformed by advanced neural approaches. Large-scale pre-trained models now dominate performance across numerous evaluation datasets.',
    'Quantum computing leverages quantum mechanical phenomena such as superposition and entanglement to perform computations that would be intractable for classical computers.',
    'The gradient descent optimization algorithm is fundamental to training machine learning models. It iteratively adjusts parameters to minimize the loss function.',
]
page2.insert_text((72, 72), '\n'.join(student_text), fontsize=11)
student_path = os.path.join('data', 'user_uploads', 'test_student.pdf')
os.makedirs(os.path.dirname(student_path), exist_ok=True)
doc2.save(student_path)
doc2.close()
print('Test PDFs created')

from backend.engine import check_plagiarism

results, details, user_chunks, uncited_mask = check_plagiarism(student_path, [ref_path])

print(f'Total chunks: {len(user_chunks)}')
print(f'Uncited chunks: {sum(uncited_mask)}')
print(f'Match details: {len(details)}')
for d in details:
    mt = d["match_type"]
    sim = d["similarity"]
    ci = d["user_chunk_idx"]
    print(f'  [{mt}] sim={sim:.1f}% chunk={ci}')
print()
for r in results:
    mtypes = r['match_types']
    print(f'Reference: {r["reference"]}')
    print(f'  Similarity: {r["similarity"]}%')
    print(f'  Direct: {mtypes["direct"]}, Paraphrase: {mtypes["paraphrase"]}, Semantic: {mtypes["semantic"]}')
    print(f'  Tables: {r["table_matches"]}, Images: {r["image_matches"]}')
