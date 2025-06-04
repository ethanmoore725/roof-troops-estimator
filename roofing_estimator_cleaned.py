
import os
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap

#─────────────────────────────────────────────────────────────────────────────#
# 1) Load material prices from CSV
#─────────────────────────────────────────────────────────────────────────────#

def load_price_list(csv_path):
    """
    Reads a CSV file with columns: item_name, unit_type, price_per_unit
    Returns a dict mapping item_name.lower() to float(price_per_unit).
    """
    price_list = {}
    with open(csv_path, mode='r', newline='') as file:
        reader = pd.read_csv(file)
        for _, row in reader.iterrows():
            name = str(row.get("item_name", "")).strip().lower()
            try:
                price = float(row.get("price_per_unit", 0))
            except ValueError:
                price = 0.0
            if name:
                price_list[name] = price
    return price_list


#─────────────────────────────────────────────────────────────────────────────#
# 2) Parse EagleView XML → compute total roof area and edge lengths
#─────────────────────────────────────────────────────────────────────────────#

def load_eagleview_geometry(xml_path):
    """
    Parses an EagleView EXPORT XML. Returns (area, edge_lengths_dict).
      - area: float total (sum of unroundedsize for all <POLYGON> in <FACE>)
      - edge_lengths_dict: dict with keys "ridge","hip","valley","eave","rake"
        each a float total length (Euclidean) from <LINE> segments
    If xml_path does not exist or parsing fails, returns (0.0, {}).
    """
    if not os.path.exists(xml_path):
        return 0.0, {}

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception:
        return 0.0, {}

    # Collect all POINT coordinates
    points = {}
    for pt in root.findall(".//POINT"):
        pid = pt.attrib.get("id")
        data = pt.attrib.get("data", "")
        try:
            coords = list(map(float, data.split(",")))  # [x, y, z]
        except ValueError:
            continue
        if pid:
            points[pid] = coords

    # Initialize edge lengths sums
    edge_lengths = {"ridge": 0.0, "hip": 0.0, "valley": 0.0, "eave": 0.0, "rake": 0.0}

    # Sum each LINE segment length if its type matches
    for line in root.findall(".//LINE"):
        kind = line.attrib.get("type", "").strip().lower()
        if kind in edge_lengths:
            path = line.attrib.get("path", "")
            a_id, b_id = path.split(",") if "," in path else (None, None)
            if a_id in points and b_id in points:
                pa = np.array(points[a_id])
                pb = np.array(points[b_id])
                edge_lengths[kind] += float(np.linalg.norm(pa - pb))

    # Sum all FACE areas from unroundedsize
    total_area = 0.0
    for face in root.findall(".//FACE"):
        poly = face.find("POLYGON")
        if poly is not None:
            try:
                raw_area = float(poly.attrib.get("unroundedsize", "0"))
            except ValueError:
                raw_area = 0.0
            total_area += raw_area

    return round(total_area, 2), {k: round(v, 2) for k, v in edge_lengths.items()}


#─────────────────────────────────────────────────────────────────────────────#
# 3) Given (area, edge_lengths) + price_list, compute core & optional items
#─────────────────────────────────────────────────────────────────────────────#

def calculate_material_costs(area, edges, price_list_path):
    """
    Returns two lists of dicts: (core_items, optional_items).

    - area: float total roof sq ft
    - edges: dict { "ridge": float, "hip": float, ... }
    - price_list_path: path to CSV with columns
        item_name, unit_type, price_per_unit

    core_items & optional_items each contain dicts:
        {
          "Material": str title-cased name,
          "Unit Type": str (e.g. "sq ft", "linear ft", "ea"),
          "Unit Price": float,
          "Quantity": float,
          "Total Cost": float
        }
    """

    # Load prices into dict: name → price_per_unit
    price_dict = load_price_list(price_list_path)

    required_items = {
        "dimensional shingle", "synthetic underlayment", "drip edge",
        "starter strip shingles", "hip & ridge shingles", "roofing nails",
        "cap nails", "dumpster"
    }
    optional_items_set = {
        "luxury composite shingle", "ice & water shield", "ridge vent",
        "powered attic fan", "deck intake vent", "gutter guards"
    }
    waste_materials = {"dimensional shingle", "synthetic underlayment", "ice & water shield"}

    core = []
    optional = []

    # Iterate over each price_list entry
    df = pd.read_csv(price_list_path)
    df["item_name"] = df["item_name"].str.strip().str.lower()
    df["unit_type"] = df["unit_type"].str.strip().str.lower()

    for _, row in df.iterrows():
        name = row["item_name"]
        unit = row["unit_type"]
        try:
            price = float(row["price_per_unit"])
        except (ValueError, KeyError):
            price = 0.0

        qty = 0.0

        # Core quantities
        if name == "hip & ridge shingles":
            qty = edges.get("hip", 0.0) + edges.get("ridge", 0.0)
        elif name == "starter strip shingles":
            qty = edges.get("eave", 0.0)
        elif name == "roofing nails":
            qty = area / 100.0
        elif name == "cap nails":
            qty = 1.0
        elif name == "deck intake vent":
            qty = edges.get("eave", 0.0) * 0.75
        elif name == "dumpster":
            qty = 1.0

        # For square‐footage materials (with potential waste)
        elif unit == "sq ft":
            qty = area * 1.10 if name in waste_materials else area

        # For linear‐footage materials
        elif unit == "linear ft":
            if name == "ridge vent":
                qty = edges.get("ridge", 0.0)
            elif name == "gutter guards":
                qty = edges.get("eave", 0.0)
            elif name == "drip edge":
                qty = edges.get("eave", 0.0)

        # For each‐unit materials
        elif unit == "ea":
            qty = 1.0

        cost = round(qty * price, 2)
        item_dict = {
            "Material": name.title(),
            "Unit Type": unit,
            "Unit Price": price,
            "Quantity": round(qty, 2),
            "Total Cost": cost
        }

        if name in required_items:
            core.append(item_dict)
        elif name in optional_items_set:
            optional.append(item_dict)

    return core, optional


#─────────────────────────────────────────────────────────────────────────────#
# 4) Generate a PDF estimate from core/optional items + client/job info
#─────────────────────────────────────────────────────────────────────────────#

def create_estimate_pdf(core, optional,
                        client_name, job_id, job_location,
                        roof_type, pitch_text, output_path):
    """
    Creates a PDF at output_path, drawing:
      • Client Name, Job ID, Location, Roof Type, Pitch
      • List of core materials (Material, Qty, Unit, Cost)
      • List of optional upgrades (Material, Qty, Unit, Cost)
      • Footer and styling (business info, signature lines, terms, etc.)
    """

    # Register Montserrat fonts (adjust paths if needed on the server)
    try:
        pdfmetrics.registerFont(
            TTFont("montserrat-black", "montserrat-black.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("montserrat-bold", "montserrat-bold.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("montserrat-light", "montserrat-light.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("montserrat-regular", "montserrat-regular.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("montserrat-extralightitalic", "montserrat-extralightitalic.ttf")
        )
    except Exception:
        # If the server environment does not have these TTF files,
        # fallback to standard Helvetica
        pass

    c = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER

    # Header
    c.setFont("montserrat-black" if "montserrat-black" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 20)
    c.drawString(160, height - 72, "ROOF TROOPS")

    c.setFont("montserrat-regular" if "montserrat-regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 10)
    c.drawString(160, height - 90, "2200 Bradley Avenue, Louisville, KY 40217")
    c.drawString(160, height - 104, "Phone: (574) 370-6742 | Email: contact@rooftroopsroofing.com")

    # Separator
    c.setLineWidth(1)
    c.line(72, height - 120, width - 72, height - 120)

    # Client / Job Info
    y = height - 144
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    c.drawString(72, y, "FILE INFORMATION")
    y -= 16

    c.setFont("montserrat-regular" if "montserrat-regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 10)
    c.drawString(72, y, f"Client: {client_name}")
    y -= 16
    c.drawString(72, y, f"Job ID: {job_id}")
    y -= 16
    c.drawString(72, y, f"Location: {job_location}")
    y -= 16
    c.drawString(72, y, f"Roof Type: {roof_type}")
    y -= 16
    c.drawString(72, y, f"Pitch: {pitch_text}")
    y -= 24

    # Required Materials Section
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    c.drawString(72, y, "REQUIRED MATERIALS")
    y -= 16

    c.setFont("montserrat-regular" if "montserrat-regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 10)
    for item in core:
        line = f"- {item['Material']}: {item['Quantity']} {item['Unit Type']} = ${item['Total Cost']:.2f}"
        c.drawString(72, y, line)
        y -= 14

    # Optional Upgrades Section
    y -= 12
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    c.drawString(72, y, "OPTIONAL UPGRADES")
    y -= 16

    c.setFont("montserrat-regular" if "montserrat-regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 10)
    for item in optional:
        line = f"- {item['Material']}: {item['Quantity']} {item['Unit Type']} = ${item['Total Cost']:.2f}"
        c.drawString(72, y, line)
        y -= 14

    # Terms & Conditions Section
    y -= 40
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    c.drawString(72, y, "TERMS & CONDITIONS")
    y -= 18

    c.setFont("montserrat-regular" if "montserrat-regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 10)
    notes = [
        "Roof Troops is not responsible for wood that has tended to rot and may need to be replaced.",
        "Remove any items that may be damaged by vibrations during install.",
        "Roof Troops is not qualified to handle hazardous waste products. We will do our best to protect and reschedule if hazardous waste removal is necessary.",
        "Roof Troops may pursue reimbursement from any insurer for code upgrades or other expenses. Such payments may affect the final invoice amount, but are NOT an obligation of the insured.",
        "All work is subject to weather conditions and material availability.",
        "Surplus materials are the property of Roof Troops."
    ]

    text_obj = c.beginText(72, y)
    for note in notes:
        wrapped = textwrap.wrap(note, width=95)
        for i, line in enumerate(wrapped):
            bullet = "• " if i == 0 else "   "
            text_obj.textLine(f"{bullet}{line}")
        text_obj.textLine("")  # blank line after each bullet

    c.drawText(text_obj)

    # Footer: signature lines
    footer_y = text_obj.getY() - 20
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 10)
    c.drawString(72, footer_y, "_________________________")
    c.drawString(300, footer_y, "_________________________")
    footer_y -= 16
    c.drawString(72, footer_y, "CLIENT SIGNATURE")
    c.drawString(300, footer_y, "DATE")

    # Total Estimate Box at Bottom
    total_box_y = 60
    box_width = width - 144  # 72pt margins each side
    c.setFillColorRGB(174/255, 209/255, 159/255)  # light green background
    c.rect(72, total_box_y, box_width, 30, fill=True, stroke=False)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("montserrat-bold" if "montserrat-bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    c.drawString(80, total_box_y + 10, "TOTAL ESTIMATE")

    # Compute grand total from core + optional
    grand_total = sum(item["Total Cost"] for item in core + optional)
    c.drawRightString(width - 80, total_box_y + 10, f"${grand_total:,.2f}")

    # Footer at very bottom
    c.setFont("montserrat-extralightitalic" if "montserrat-extralightitalic" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Oblique", 8)
    c.drawString(72, 30, "www.rooftroopsroofing.com | License #123456 | All rights reserved © 2025")

    c.save()