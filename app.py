# ─────────────────────────────────────────────────────────────
# app.py
# ─────────────────────────────────────────────────────────────

import os
import re
import platform
from datetime import datetime

from flask import Flask, request, render_template, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename

# Import your existing estimator functions
# (Adjust the import path if necessary—this assumes you renamed your estimator logic to roofing_estimator_cleaned.py)
from roofing_estimator_cleaned import load_eagleview_geometry, calculate_material_costs

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xml"}

# Ensure the upload folder exists (Render’s container is ephemeral but will persist during a single run)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.urandom(24)  # for flash messages (if desired)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ─────────────────────────────────────────────────────────────
# Utility: check XML extension
# ─────────────────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────────
# Main route: upload page, handle XML + form inputs
# ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        # 1. Ensure file present
        if "xmlfile" not in request.files:
            flash("No file part in the request", "error")
            return redirect(request.url)

        file = request.files["xmlfile"]
        if file.filename == "":
            flash("No XML selected for uploading", "error")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # 2. Save the XML to 'uploads/<secure_filename>'
            filename = secure_filename(file.filename)
            xml_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(xml_path)

            # 3. Run your estimator logic
            #    - load geometry, calculate edge_lengths & area
            #    - get material costs (core_items, optional_items)
            area, edge_lengths = load_eagleview_geometry(xml_path)  # returns (float_area, dict_of_edges)
            core_items, optional_items = calculate_material_costs(area, edge_lengths, "price_list.csv")

            # 4. Render a results page or generate PDF on the fly
            #    For simplicity, we’ll redirect to /results that then triggers PDF generation:
            return redirect(url_for("results", area=area))
        else:
            flash("Allowed file types: .xml", "error")
            return redirect(request.url)

    # GET request → just show the upload form
    return render_template("upload_app.html")


# ─────────────────────────────────────────────────────────────
# Results route: generates PDF and returns it to user
# (you can customize as needed)
# ─────────────────────────────────────────────────────────────
@app.route("/results")
def results():
    # In a more robust design, you’d pass along all the form + XML data via sessions or hidden form fields.
    # For this example, we’ll simply flash a message or display a summary page.
    area = request.args.get("area", None)
    if area is None:
        flash("No estimate data available", "error")
        return redirect(url_for("upload"))

    # For demonstration, we’ll show a “dummy” results page:
    return f"<h2>Success! Calculated roof area = {float(area):.2f} sq ft.</h2>"


# ─────────────────────────────────────────────────────────────
# Local runner (only used when you do `python app.py`)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # The debug server runs on port 5000; Render overrides this with $PORT under Gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)
