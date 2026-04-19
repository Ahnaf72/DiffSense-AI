import sys, os
os.chdir(r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')
sys.path.insert(0, r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')

import fitz

# Create a comprehensive reference PDF with longer text
ref_dir = 'backend/data/reference_pdfs'
os.makedirs(ref_dir, exist_ok=True)

doc = fitz.open()
page = doc.new_page()
ref_paragraphs = [
    "The quick brown fox jumps over the lazy dog. This is a sample paragraph that contains unique content about artificial intelligence and machine learning algorithms. These technologies have transformed how we approach complex problems in computer science and data analysis.",
    "Neural networks are computational models inspired by the human brain. They consist of layers of interconnected nodes that process information using connectionist approaches. The architecture includes input layers, hidden layers, and output layers that work together to learn patterns from training data.",
    "Deep learning has revolutionized natural language processing. Transformer architectures like BERT and GPT have achieved remarkable results on various benchmarks. These models use self-attention mechanisms to capture long-range dependencies in text, enabling more accurate understanding of context and meaning.",
    "The gradient descent optimization algorithm is fundamental to training machine learning models. It iteratively adjusts parameters to minimize the loss function. Stochastic gradient descent and its variants like Adam and RMSProp are commonly used in practice to efficiently navigate the optimization landscape.",
    "Convolutional neural networks are particularly effective for image recognition tasks. They use filters to detect features such as edges, textures and patterns. The hierarchical structure of convolutional layers allows the network to learn increasingly complex features, from simple edges in early layers to complex objects in deeper layers.",
    "Reinforcement learning is a paradigm where an agent learns to make decisions by interacting with an environment. The agent receives rewards or penalties based on its actions and learns to maximize cumulative reward over time. Applications include game playing, robotics, and autonomous vehicle navigation.",
    "Transfer learning allows models trained on one task to be adapted for related tasks. This approach significantly reduces the amount of labeled data needed for new applications. Pre-trained models like ResNet, BERT, and GPT serve as powerful starting points that can be fine-tuned for specific domains.",
    "Generative adversarial networks consist of two neural networks, a generator and a discriminator, that are trained together in a competitive setting. The generator creates synthetic data samples while the discriminator tries to distinguish between real and generated samples, leading to increasingly realistic outputs.",
]
page.insert_text((72, 72), '\n\n'.join(ref_paragraphs), fontsize=10)
ref_path = os.path.join(ref_dir, 'reference_paper.pdf')
doc.save(ref_path)
doc.close()

# Create student PDF with all 4 types of plagiarism
doc2 = fitz.open()
page2 = doc2.new_page()
student_paragraphs = [
    # DIRECT COPY - verbatim from reference paragraph 1
    "The quick brown fox jumps over the lazy dog. This is a sample paragraph that contains unique content about artificial intelligence and machine learning algorithms. These technologies have transformed how we approach complex problems in computer science and data analysis.",
    # PARAPHRASE - same meaning, different words (from reference paragraph 2)
    "Neural networks serve as computing frameworks modeled after the human mind. These systems feature tiers of linked processing units that handle data through connectionist methods. The design encompasses input tiers, intermediate tiers, and output tiers collaborating to identify patterns from training examples.",
    # SEMANTIC - same topic, different expression (from reference paragraph 3)
    "Advanced language models have fundamentally changed how computers understand text. Modern architectures employing attention mechanisms can now capture the relationships between distant words in a document, resulting in superior performance on language understanding tasks and benchmarks.",
    # ORIGINAL - no match
    "Quantum computing leverages quantum mechanical phenomena such as superposition and entanglement to perform computations that would be intractable for classical computers. Quantum algorithms like Shor's algorithm and Grover's algorithm offer exponential speedups for specific problem classes.",
    # DIRECT COPY - verbatim from reference paragraph 4
    "The gradient descent optimization algorithm is fundamental to training machine learning models. It iteratively adjusts parameters to minimize the loss function. Stochastic gradient descent and its variants like Adam and RMSProp are commonly used in practice to efficiently navigate the optimization landscape.",
    # PARAPHRASE - from reference paragraph 5
    "CNNs excel at visual recognition challenges by employing convolutional filters that identify characteristics including boundaries, surface qualities, and recurring motifs. The layered design enables progressive feature discovery, moving from basic edge detection in initial layers to sophisticated object recognition in deeper ones.",
    # SEMANTIC - from reference paragraph 6
    "In the reinforcement learning framework, an autonomous agent discovers optimal behavior through trial-and-error interaction with its surroundings. By receiving feedback in the form of numerical rewards, the agent gradually improves its decision-making strategy to achieve long-term objectives.",
    # ORIGINAL - no match
    "Blockchain technology provides a decentralized and immutable ledger for recording transactions across a network of computers. Consensus mechanisms like proof-of-work and proof-of-stake ensure the integrity of the blockchain without requiring a trusted central authority.",
]
page2.insert_text((72, 72), '\n\n'.join(student_paragraphs), fontsize=10)
student_path = os.path.join('data', 'user_uploads', 'test_student.pdf')
os.makedirs(os.path.dirname(student_path), exist_ok=True)
doc2.save(student_path)
doc2.close()
print('Test PDFs created')

from backend.engine import check_plagiarism

results, details, user_chunks, uncited_mask = check_plagiarism(student_path, [ref_path])

print(f'\nTotal chunks: {len(user_chunks)}')
print(f'Uncited chunks: {sum(uncited_mask)}')
print(f'Match details: {len(details)}')
for d in sorted(details, key=lambda x: x["user_chunk_idx"]):
    mt = d["match_type"]
    sim = d["similarity"]
    ci = d["user_chunk_idx"]
    chunk_preview = d.get("user_chunk", "")[:60]
    print(f'  chunk {ci}: [{mt}] sim={sim:.1f}% | {chunk_preview}...')

print()
for r in results:
    mtypes = r['match_types']
    print(f'Reference: {r["reference"]}')
    print(f'  Overall Similarity: {r["similarity"]}%')
    print(f'  Direct: {mtypes["direct"]}, Paraphrase: {mtypes["paraphrase"]}, Semantic: {mtypes["semantic"]}')
    print(f'  Tables: {r["table_matches"]}, Images: {r["image_matches"]}')

# Verify all 4 types
has_direct = any(d["match_type"] == "direct" for d in details)
has_paraphrase = any(d["match_type"] == "paraphrase" for d in details)
has_semantic = any(d["match_type"] == "semantic" for d in details)
print(f'\nDetection Summary:')
print(f'  Direct Copy:   {"PASS" if has_direct else "FAIL"}')
print(f'  Paraphrase:    {"PASS" if has_paraphrase else "FAIL"}')
print(f'  Semantic:      {"PASS" if has_semantic else "FAIL"}')
print(f'  Image/Table:   N/A (no images/tables in test)')
