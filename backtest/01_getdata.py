import os
import zipfile

# Define the directory containing ZIP files
ZIP_FOLDER = "data/zip"
EXTRACT_FOLDER = "data/extracted"

# Ensure output directory exists
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

# Loop through all ZIP files in the folder
for filename in os.listdir(ZIP_FOLDER):
    if filename.endswith(".zip"):  # Ensure we're handling ZIP files
        zip_path = os.path.join(ZIP_FOLDER, filename)

        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(EXTRACT_FOLDER)
                print(f"Successfully extracted {filename}")

        except zipfile.BadZipFile:
            print(f"Error: {filename} is not a valid ZIP file. Skipping...")

print(f"All available ZIP files have been extracted to '{EXTRACT_FOLDER}'")
