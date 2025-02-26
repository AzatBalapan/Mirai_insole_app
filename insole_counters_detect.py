import cv2
import numpy as np

# Input and output file paths
input_path = "static/processed_insole_image.png"  # Replace with your processed image path
output_path = "specified_contours_filled.png"

# Specify the indices of contours to fill
contours_to_fill = {1, 2, 3, 4, 5, 6, 9, 10}

# Load the image
try:
    # Read the image
    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Could not find the file at {input_path}")

    # Convert the image to grayscale
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply thresholding to create a binary image
    _, binary_image = cv2.threshold(gray_image, 128, 255, cv2.THRESH_BINARY)

    # Find all contours
    contours, _ = cv2.findContours(binary_image, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # Create a copy of the image to draw the filled contours
    output_image = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)

    # Assign unique colors for each contour
    colors = [
        (255, 0, 0),    # Red
        (0, 255, 0),    # Green
        (0, 0, 255),    # Blue
        (255, 255, 0),  # Cyan
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Yellow
        (128, 0, 128),  # Purple
        (0, 128, 128)   # Teal
    ]

    # Iterate over the contours and fill the specified ones
    for idx, contour in enumerate(contours):
        # Check if the contour index is in the specified list
        if (idx + 1) in contours_to_fill:
            color = colors[(idx % len(colors))]  # Cycle through the colors
            cv2.drawContours(output_image, [contour], -1, color, thickness=cv2.FILLED)

    # Save the output image
    cv2.imwrite(output_path, output_image)
    print(f"Specified contours filled and saved at: {output_path}")

except FileNotFoundError as e:
    print(e)
except Exception as e:
    print(f"An error occurred: {e}")
