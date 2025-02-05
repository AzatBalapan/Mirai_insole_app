from PIL import Image

# Input and output file paths
input_path = "static/second_insole.png"  # Replace with the path to your input file
output_path = "processed_insole_image.png"

# Open the image
try:
    image = Image.open(input_path)

    # Rotate the image 90 degrees clockwise
    rotated_image_90 = image.rotate(-90, expand=True)

    # Mirror the image (horizontal flip)
    mirrored_image = rotated_image_90.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    # Combine the original (rotated 90 degrees) and mirrored image side-by-side
    combined_width = rotated_image_90.width + mirrored_image.width
    combined_height = max(rotated_image_90.height, mirrored_image.height)
    combined_image = Image.new("RGB", (combined_width, combined_height), (255, 255, 255))

    # Paste the images into the combined image
    combined_image.paste(rotated_image_90, (0, 0))
    combined_image.paste(mirrored_image, (rotated_image_90.width, 0))

    # Save the combined image
    combined_image.save(output_path)
    print(f"Processed image saved at: {output_path}")

except FileNotFoundError:
    print(f"Error: File not found at {input_path}. Please check the path and try again.")
except Exception as e:
    print(f"An error occurred: {e}")