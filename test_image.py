import sys, os
os.chdir(r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')
sys.path.insert(0, r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')

import fitz
import numpy as np

# Create a reference PDF with an image
ref_dir = 'backend/data/reference_pdfs'
os.makedirs(ref_dir, exist_ok=True)

# Create a simple test image (red rectangle)
img = np.zeros((200, 200, 3), dtype=np.uint8)
img[50:150, 50:150] = [255, 0, 0]  # Red square
img_path = os.path.join('data', 'test_ref_img.png')

try:
    from PIL import Image as PILImage
    PILImage.fromarray(img).save(img_path)
except ImportError:
    # Fallback: create a simple PNG manually
    import struct, zlib
    def create_png(arr, path):
        h, w, c = arr.shape
        raw = b''
        for row in arr:
            raw += b'\x00' + row.tobytes()
        compressed = zlib.compress(raw)
        def chunk(ctype, data):
            c = ctype + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        idat = chunk(b'IDAT', compressed)
        iend = chunk(b'IEND', b'')
        with open(path, 'wb') as f:
            f.write(sig + ihdr + idat + iend)
    create_png(img, img_path)

# Reference PDF with image
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), "This is a reference document with an image below.", fontsize=11)
rect = fitz.Rect(72, 100, 272, 300)
page.insert_image(rect, filename=img_path)
ref_path = os.path.join(ref_dir, 'reference_with_image.pdf')
doc.save(ref_path)
doc.close()

# Student PDF with SAME image (copy)
img2 = img.copy()  # Identical copy
img2_path = os.path.join('data', 'test_stu_img.png')
try:
    from PIL import Image as PILImage
    PILImage.fromarray(img2).save(img2_path)
except ImportError:
    create_png(img2, img2_path)

doc2 = fitz.open()
page2 = doc2.new_page()
page2.insert_text((72, 72), "This is a student submission with a copied image below.", fontsize=11)
rect2 = fitz.Rect(72, 100, 272, 300)
page2.insert_image(rect2, filename=img2_path)
student_path = os.path.join('data', 'user_uploads', 'test_student_img.pdf')
os.makedirs(os.path.dirname(student_path), exist_ok=True)
doc2.save(student_path)
doc2.close()

print('Test PDFs with images created')

# Test image similarity directly
from backend.pdf_utils import extract_images, image_similarity

ref_images = extract_images(ref_path)
stu_images = extract_images(student_path)

print(f'Reference images: {len(ref_images)}')
print(f'Student images: {len(stu_images)}')

if ref_images and stu_images:
    for i, ri in enumerate(ref_images):
        for j, si in enumerate(stu_images):
            try:
                diff = image_similarity(ri, si)
                print(f'  Image comparison ref[{i}] vs stu[{j}]: diff={diff:.2f} (threshold=1000)')
                if diff < 1000:
                    print('  -> IMAGE COPY DETECTED!')
            except Exception as e:
                print(f'  Image comparison error: {e}')

# Now test the full engine
from backend.engine import check_plagiarism
results, details, user_chunks, uncited_mask = check_plagiarism(student_path, [ref_path])

for r in results:
    mtypes = r['match_types']
    print(f'\nFull Engine Results:')
    print(f'  Direct: {mtypes["direct"]}, Paraphrase: {mtypes["paraphrase"]}, Semantic: {mtypes["semantic"]}')
    print(f'  Tables: {r["table_matches"]}, Images: {r["image_matches"]}')
    print(f'  Overall: {r["similarity"]}%')
    print(f'\nImage Copy Detection: {"PASS" if r["image_matches"] > 0 else "FAIL"}')
