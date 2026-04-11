import warnings

import easyocr
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

# Dependency Check & Import
# We will explicitly use PyMuPDF (fitz) to handle PDFs.
try:
    import fitz  # PyMuPDF

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Initialize the OCR Reader
# This is done once to load the models into memory.
reader = easyocr.Reader(['en'], gpu=False)


def run_ocr_on_file(filepath):
    """
    Run OCR on an image or PDF file using a robust, two-step process.
    For PDFs, it converts each page to an image before running OCR.
    """
    full_text_parts = []

    try:
        # PDF Processing
        if filepath.lower().endswith(".pdf"):
            if not PDF_SUPPORT:
                print_dependency_error()
                return "", 0.0

            # Open the PDF file
            doc = fitz.open(filepath)

            # Iterate through each page of the PDF
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Convert page to a pixel map (image)
                pix = page.get_pixmap()
                # Convert the pixel map to a NumPy array for easyocr
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

                # Run OCR on the image array of the current page
                result = reader.readtext(img_array, detail=0, paragraph=True)
                full_text_parts.extend(result)

            doc.close()

        # Image File Processing
        else:
            # For standard image files, process them directly
            result = reader.readtext(filepath, detail=0, paragraph=True)
            full_text_parts.extend(result)

    except Exception as e:
        print(f"OCR process failed for file {filepath}. Error: {e}")
        return "", 0.0

    # Join the text from all parts/pages and return
    return "\n".join(full_text_parts), 0.0


def print_dependency_error():
    """Prints a clear error message if PyMuPDF is not installed."""
    print("\n" + "=" * 60)
    print("FATAL ERROR: PDF processing library is missing.")
    print("Please ensure your virtual environment is active and run:")
    print("\npip install PyMuPDF\n")
    print("=" * 60 + "\n")
