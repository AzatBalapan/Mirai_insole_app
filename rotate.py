import cv2
import numpy as np
import xml.etree.ElementTree as ET

# Define the contours that need to be filled with colors
FILL_CONTOURS = {12, 6, 11, 5, 10, 4, 9, 3}

# Define different colors for each specified contour
FILL_COLORS = [
    (255, 0, 0),  # Blue
    (0, 255, 0),  # Green
    (0, 0, 255),  # Red
    (255, 255, 0),  # Cyan
    (255, 0, 255),  # Magenta
    (0, 255, 255),  # Yellow
    (128, 0, 128),  # Purple
    (0, 128, 255)   # Orange
]

def save_contours_to_xml(contours, output_xml_path):
    """
    Save the contours to an XML file.
    """
    root = ET.Element("Contours")

    for i, contour in enumerate(contours, start=1):
        contour_element = ET.SubElement(root, "Contour", id=str(i))
        for point in contour:
            ET.SubElement(
                contour_element, "Point", x=str(point[0][0]), y=str(point[0][1])
            )

    tree = ET.ElementTree(root)
    tree.write(output_xml_path, encoding="utf-8", xml_declaration=True)
    print(f"Contours saved to '{output_xml_path}'.")


def create_html_viewer(xml_path, html_output_path, annotated_image_path):
    """
    Create an HTML viewer for the contours.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Contours Viewer</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f5f5;
                text-align: center;
            }}
            img {{
                max-width: 90%;
                margin: 20px 0;
            }}
            table {{
                margin: 20px auto;
                border-collapse: collapse;
                width: 90%;
            }}
            table, th, td {{
                border: 1px solid #ccc;
            }}
            th, td {{
                padding: 10px;
                text-align: center;
            }}
            th {{
                background-color: #f0f0f0;
            }}
        </style>
    </head>
    <body>
        <h1>Contours Viewer</h1>
        <img src="{annotated_image_path}" alt="Annotated Insole">
        <h2>Contours Details</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Points</th>
                </tr>
            </thead>
            <tbody id="contours-table">
            </tbody>
        </table>
        <script>
            fetch("{xml_path}")
                .then(response => response.text())
                .then(data => {{
                    const parser = new DOMParser();
                    const xmlDoc = parser.parseFromString(data, "application/xml");
                    const contours = xmlDoc.getElementsByTagName("Contour");

                    const table = document.getElementById("contours-table");
                    for (let contour of contours) {{
                        const id = contour.getAttribute("id");
                        const points = Array.from(contour.getElementsByTagName("Point"))
                            .map(point => `(${{point.getAttribute("x")}}, ${{point.getAttribute("y")}})`)
                            .join(", ");
                        const row = document.createElement("tr");
                        row.innerHTML = `<td>${{id}}</td><td>${{points}}</td>`;
                        table.appendChild(row);
                    }}
                }})
                .catch(error => console.error("Error loading XML:", error));
        </script>
    </body>
    </html>
    """
    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML viewer saved to '{html_output_path}'.")


def process_and_mirror_insole(input_image_path, output_image_path, output_xml_path, output_html_path, scale_factor=1.0, min_contour_area=500):
    """
    Process the insole image, rotate, mirror it, fill specific contours, and generate an HTML viewer.
    """
    # Load the insole image
    insole_image = cv2.imread(input_image_path, cv2.IMREAD_UNCHANGED)
    if insole_image is None:
        print(f"Error: Unable to load image from '{input_image_path}'")
        return

    # Resize the image proportionally
    original_height, original_width = insole_image.shape[:2]
    new_width = int(original_width * scale_factor)
    new_height = int(original_height * scale_factor)
    resized_insole = cv2.resize(insole_image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    # Rotate the resized insole
    rotated_insole = cv2.rotate(resized_insole, cv2.ROTATE_90_CLOCKWISE)

    # Create a mirrored version of the rotated insole
    mirrored_insole = cv2.flip(rotated_insole, 1)

    # Combine the rotated and mirrored insoles side by side
    combined_insole = np.hstack((rotated_insole, mirrored_insole))

    # Annotate contours for both insoles
    gray_combined = cv2.cvtColor(combined_insole, cv2.COLOR_BGR2GRAY)
    _, binary_combined = cv2.threshold(gray_combined, 100, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(binary_combined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    annotated_combined = cv2.cvtColor(gray_combined, cv2.COLOR_GRAY2BGR)

    contour_index = 1
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_contour_area:  # Filter out small areas
            continue

        # Fill specific contours with unique colors
        if contour_index in FILL_CONTOURS:
            color_index = list(FILL_CONTOURS).index(contour_index) % len(FILL_COLORS)
            cv2.drawContours(annotated_combined, [contour], -1, FILL_COLORS[color_index], thickness=cv2.FILLED)
        else:
            cv2.drawContours(annotated_combined, [contour], -1, (0, 255, 0), 2)

        contour_index += 1

    # Save the annotated combined image
    cv2.imwrite(output_image_path, annotated_combined)
    print(f"Annotated mirrored insole image saved to '{output_image_path}'")

    # Save contours to XML
    save_contours_to_xml(contours, output_xml_path)

    # Generate HTML viewer
    create_html_viewer(output_xml_path, output_html_path, output_image_path)


# Paths for input and output
input_image_path = "image_2025-02-03_18-30-42.png"  # Replace with your input image path
output_image_path = "mirrored_insole_annotated.jpg"
output_xml_path = "contours.xml"
output_html_path = "contours_viewer.html"

process_and_mirror_insole(input_image_path, output_image_path, output_xml_path, output_html_path)
