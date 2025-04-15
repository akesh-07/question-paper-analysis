import os
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import docx
import base64
import matplotlib

matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
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
    text = re.sub(
        r'\b(this question|students.?attempt|consist[s]? of|carries|each question|compulsory)\b.?(?=\d+\s*[\.\)])', '',
        text, flags=re.IGNORECASE)
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
                sub = re.sub(r'\b(total|question[s]?|code|date|time|roll no|max:instructions|subject)\b.?:?.*', '', sub,
                             flags=re.IGNORECASE)
                sub = re.sub(r'\b(answer all questions|x=|question no\.? is compulsory)\b.*', '', sub,
                             flags=re.IGNORECASE)

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


def generate_top_groups_chart(groups, output_dir):
    """Generate a bar chart showing the top 10 groups by frequency"""
    if not groups or len(groups) == 0:
        return None

    # Get top 10 groups by size
    top_groups = groups[:10] if len(groups) > 10 else groups

    # Prepare data for chart
    counts = [len(group) for group in top_groups]

    # Create labels - use truncated first question from each group
    labels = []
    for group in top_groups:
        if not group:  # Skip empty groups
            labels.append("Empty Group")
            continue

        # Get first question and truncate if needed
        first_q = group[0]
        if len(first_q) > 40:
            first_q = first_q[:37] + "..."
        labels.append(first_q)

    # Set styling for the plot
    plt.figure(figsize=(10, 6))
    plt.style.use('ggplot')

    # Create horizontal bar chart
    bars = plt.barh(range(len(counts)), counts, color='#4361ee', alpha=0.8)

    # Add data labels on the bars
    for i, v in enumerate(counts):
        plt.text(v + 0.1, i, str(v), va='center', fontweight='bold')

    # Customize chart appearance
    plt.yticks(range(len(labels)), labels, fontsize=9)
    plt.xlabel('Number of Questions', fontweight='bold')
    plt.title('Top 10 Question Groups by Frequency', fontweight='bold', fontsize=14)
    plt.tight_layout()

    # Add gradient to bars for visual appeal
    for i, bar in enumerate(bars):
        gradient = plt.cm.Blues(i / len(bars))
        bar.set_facecolor(gradient)

    # Save chart as PNG
    chart_path = os.path.join(output_dir, 'top_groups_chart.png')
    plt.savefig(chart_path, dpi=100, bbox_inches='tight')
    plt.close()

    # Return the path to the generated chart
    return chart_path


def get_chart_base64(chart_path):
    """Convert the chart to base64 for embedding in HTML"""
    if not chart_path or not os.path.exists(chart_path):
        return None

    with open(chart_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')