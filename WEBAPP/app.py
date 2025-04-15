from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
from werkzeug.utils import secure_filename
from prog.main import process_files, generate_pdf, generate_top_groups_chart, get_chart_base64

app = Flask(__name__)

# Configuration - adjusted for your project structure
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
RESULTS_FOLDER = os.path.join(os.path.dirname(__file__), 'results')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size

# Ensure folders exist
for folder in [UPLOAD_FOLDER, RESULTS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if the post request has files
    if 'files' not in request.files and 'file' not in request.files:
        return redirect(request.url)

    # Handle multiple files upload
    if 'files' in request.files:
        files = request.files.getlist('files')
    # Handle single file upload
    else:
        files = [request.files['file']]

    if not files or all(file.filename == '' for file in files):
        return redirect(request.url)

    uploaded_filepaths = []
    uploaded_filenames = []

    # Save all uploaded files and collect their filepaths
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_filepaths.append(filepath)
            uploaded_filenames.append(filename)

    if not uploaded_filepaths:
        return redirect(request.url)

    # Process all uploaded files in one batch
    groups = process_files(uploaded_filepaths)

    # Generate PDF report
    output_pdf_name = f"grouped_questions_{uploaded_filenames[0].rsplit('.', 1)[0]}.pdf" if len(
        uploaded_filenames) == 1 else "grouped_questions.pdf"
    output_pdf_path = os.path.join(app.config['RESULTS_FOLDER'], output_pdf_name)
    generate_pdf(groups, output_pdf_path)

    # Generate bar chart for top 10 groups - store in results folder
    chart_path = generate_top_groups_chart(groups, app.config['RESULTS_FOLDER'])
    chart_b64 = get_chart_base64(chart_path)

    return render_template('success.html',
                           filename=", ".join(uploaded_filenames),
                           result_pdf=output_pdf_name,
                           groups=groups,
                           chart_b64=chart_b64)


@app.route('/results/<filename>')
def download_result(filename):
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)


@app.route('/uploads/<filename>')
def download_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    app.run(debug=True)