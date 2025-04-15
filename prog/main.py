import os
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import docx
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Tesseract path (for Windows users)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Load the model
model = SentenceTransformer('all-MiniLM-L6-v2')


def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])


def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text


def extract_text_from_scanned_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text += pytesseract.image_to_string(image) + "\n"
    return text


def extract_questions(text):
    text = text.replace('\n', ' ')
    text = re.sub(r'\b(this question|students.?attempt|consist[s]? of|carries|each question|compulsory)\b.?(?=\d+\s*[\.\)])', '', text, flags=re.IGNORECASE)
    raw_questions = re.split(r'(?:\d+\s*[\.\)]\s*)', text)

    blacklist_keywords = [
        "reg. no", "roll no", "max:instructions", "code", "date", "time", "subject",
        "coimbatore institute", "b.e. degree", "examinations", "branch", "semester",
        "computer science", "engineering", "common to", "autonomous", "institution",
        "part a and part b", "instructions", "max", "tech", "batch"
    ]

    questions = []
    for q in raw_questions:
        q = q.strip()

        if " or " in q.lower():
            parts = re.split(r'\s*\(?OR\)?\s*|\s+or\s+', q, flags=re.IGNORECASE)
        else:
            parts = [q]

        for part in parts:
            sub_parts = re.split(r'(?:\(?[a-dA-D]\)?\s*[\.\)]\s*)', part)
            for sub in sub_parts:
                sub = sub.strip()
                sub = re.sub(r'\(?\s*\d+\s*(marks|mark)?\s*\)?', '', sub, flags=re.IGNORECASE)
                sub = re.sub(r'\b(total|question[s]?|code|date|time|roll no|max:instructions|subject)\b.?:?.*', '', sub, flags=re.IGNORECASE)
                sub = re.sub(r'\b(answer all questions|x=|question no\.? is compulsory)\b.*', '', sub, flags=re.IGNORECASE)

                sub = sub.strip()

                if (len(sub) > 15 and
                    re.search(r'[a-zA-Z]', sub) and
                    len(sub.split()) > 4 and
                    not any(keyword in sub.lower() for keyword in blacklist_keywords)):
                        questions.append(sub)

    return questions


def process_files(file_paths):
    all_questions = []
    for file_path in file_paths:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.txt':
            content = extract_text_from_txt(file_path)
        elif ext == '.docx':
            content = extract_text_from_docx(file_path)
        elif ext == '.pdf':
            content = extract_text_from_pdf(file_path)
            if not content.strip():
                print(f"🔍 OCR on scanned PDF: {file_path}")
                content = extract_text_from_scanned_pdf(file_path)
        else:
            print(f"❌ Unsupported file format: {file_path}")
            continue

        questions = [q.lower().strip() for q in extract_questions(content) if len(q.strip()) > 10]
        all_questions.extend(questions)

    if not all_questions:
        print("⚠️ No questions extracted from uploaded files.")
        return []

    grouped = group_similar_questions(all_questions)
    return grouped


def group_similar_questions(questions, threshold=0.75):
    if not questions:
        print("⚠️ group_similar_questions called with empty list.")
        return []

    embeddings = model.encode(questions)
    if len(embeddings) == 0:
        return []

    sim_matrix = cosine_similarity(embeddings)
    visited = set()
    groups = []

    for i in range(len(questions)):
        if i in visited:
            continue
        group = [questions[i]]
        visited.add(i)
        for j in range(i + 1, len(questions)):
            if j not in visited and sim_matrix[i][j] >= threshold:
                group.append(questions[j])
                visited.add(j)
        groups.append(group)

    groups.sort(key=lambda x: len(x), reverse=True)
    return groups

def generate_pdf(groups, filename):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "📘 Grouped Questions by Similarity")
    y -= 30

    c.setFont("Helvetica", 11)
    for idx, group in enumerate(groups, 1):
        group_title = f"Group {idx} (Count: {len(group)}):"
        print(f"\n🔹 {group_title}")
        if y < 100:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margin, y, "📘 Grouped Questions by Similarity")
            y -= 30
            c.setFont("Helvetica", 11)

        c.drawString(margin, y, group_title)
        y -= 15
        for q in group:
            print(f"   - {q}")
            for line in split_text(q, 100):
                if y < 50:
                    c.showPage()
                    y = height - margin
                c.drawString(margin + 15, y, "- " + line)
                y -= 13
        y -= 10

    c.save()
    print(f"\n📄 PDF saved: {filename}")


def split_text(text, max_chars):
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
