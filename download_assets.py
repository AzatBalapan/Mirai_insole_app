import os
import requests

# URLs for the assets
assets = {
    "bulma.min.css": "https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css",
    "fontawesome.min.css": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
    "all.min.css": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
    "webfonts/fa-solid-900.woff2": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/webfonts/fa-solid-900.woff2",
    "webfonts/fa-regular-400.woff2": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/webfonts/fa-regular-400.woff2",
    "chart.min.js": "https://cdn.jsdelivr.net/npm/chart.js",
    "chartjs-plugin-zoom.min.js": "https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@1.0.0/dist/chartjs-plugin-zoom.min.js"
}

# Create the static and webfonts folders if they don't exist
os.makedirs("static", exist_ok=True)
os.makedirs("static/webfonts", exist_ok=True)

def download_file(url, filename):
    print(f"Downloading {filename}...")
    response = requests.get(url)
    if response.status_code == 200:
        with open(os.path.join("static", filename), "wb") as file:
            file.write(response.content)
        print(f"{filename} downloaded successfully.")
    else:
        print(f"Failed to download {filename}. Status code: {response.status_code}")

# Download each asset
for filename, url in assets.items():
    download_file(url, filename)

print("All assets downloaded.")
