from flask import Flask, render_template, request, redirect, send_from_directory
import os
from prog.main import process_files, generate_pdf

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files' not in request.files:
        return redirect(request.url)

    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        return redirect(request.url)

    uploaded_filepaths = []
    uploaded_filenames = []

    # Save all uploaded files and collect their filepaths
    for file in files:
        if file and file.filename:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_filepaths.append(filepath)
            uploaded_filenames.append(filename)

    # Process all uploaded files in one batch
    groups = process_files(uploaded_filepaths)

    # Generate PDF report
    output_pdf_name = "grouped_questions.pdf"
    output_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], output_pdf_name)
    generate_pdf(groups, output_pdf_path)  # Fixed order of arguments here

    return render_template('success.html',
                           filename=", ".join(uploaded_filenames),
                           result_pdf=output_pdf_name)


@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    app.run(debug=True)