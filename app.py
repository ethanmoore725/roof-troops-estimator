from flask import Flask, render_template, request, send_file
import os
from datetime import datetime
from roofing_estimator_cleaned import (
    load_eagleview_geometry,
    calculate_material_costs,
    create_estimate_pdf
)

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
PDF_FOLDER    = "pdfs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER,    exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        xmlfile = request.files.get("xmlfile")
        if not xmlfile or not xmlfile.filename.lower().endswith(".xml"):
            return "Error: Please upload a valid XML file.", 400

        # 1) Save the uploaded XML:
        xml_path = os.path.join(UPLOAD_FOLDER, xmlfile.filename)
        xmlfile.save(xml_path)

        # 2) Read form fields:
        client_name  = request.form.get("client_name", "")
        job_id       = request.form.get("job_id", "")
        job_location = request.form.get("job_location", "")
        roof_type    = request.form.get("roof_type", "")
        pitch_text   = request.form.get("pitch", "")

        # 3) Run your estimator logic:
        area, edge_lengths = load_eagleview_geometry(xml_path)
        core, optional     = calculate_material_costs(
            area, edge_lengths, "price_list.csv"
        )

        # 4) Generate and save PDF:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_name = f"estimate_{job_id}_{ts}.pdf"
        pdf_path = os.path.join(PDF_FOLDER, pdf_name)

        create_estimate_pdf(
            core, optional,
            client_name, job_id,
            job_location, roof_type,
            pitch_text, pdf_path
        )

        # 5) Return the PDF as a download:
        return send_file(pdf_path, as_attachment=True)

    # If GET, just render the upload form:
    return render_template("upload_app.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
