# from core import exceptions
from importlib import metadata
import fitz
from typing import List, Tuple,Optional
import os
import pprint # A library for "pretty-printing" data
import pdfplumber
import subprocess
import tempfile as python_tempfile

def open_pdf_from_path(file_path: str,password: Optional[str] = None) -> fitz.Document:
    """
    Safely opens a PDF from a file path.

    Args:
        file_path: The full path to the PDF file.
        password: The password for encrypted PDFs.

    Returns:
        A fitz.Document object on success, or raises a ValueError on failure.
    """
    try:
        doc = fitz.open(file_path)
        if doc.is_encrypted:
            if not doc.authenticate(password or ""):
                doc.close()
                # raise exceptions.PasswordProtectedPDFError()
        return doc
    except Exception as e:
        raise e
        # raise exceptions.InvalidPDFError(f"Failed to open file: {e}")

def extract_metadata(doc:fitz.Document) -> dict:
    """
    Extracts metadata from an opened PDF document.

    Args:
        doc: An opened fitz.Document object.

    Returns:
        A dictionary containing the PDF's metadata.
    """
    metadata = doc.metadata
    if metadata is None:
        metadata = {}
    return{
        "page_count": doc.page_count,
        "format": metadata.get("format"),
        "title": metadata.get("title"),
        "author": metadata.get("author"),
        "subject": metadata.get("subject"),
        "producer": metadata.get("producer"),
        "creation_date": metadata.get("creationDate"),
        "modification_date": metadata.get("modDate"),
        "is_encrypted": doc.is_encrypted,
    }


def extract_text_with_positions(docs:fitz.Document) -> List:
    """
    Extracts text along with their positions from each page of the PDF.

    Args:
        doc: An opened fitz.Document object.

    Returns:
        A list of dictionaries, each containing text and its bounding box for each page.
    """
    all_pages_text = []
    for page_num in range(docs.page_count):
        page = docs.load_page(page_num)
        blocks = page.get_text("dict")["blocks"] # type: ignore

#Each block has a type: 0 = text block. Other values (like 1, 2) may mean image, drawing, etc.
        page_text_blocks =[]
        for block in blocks:
            if block["type"] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        page_text_blocks.append({
                            "text": span["text"],
                            "bbox": span["bbox"],  # The coordinates (x0, y0, x1, y1)
                            "font": span["font"],
                            "size": round(span["size"]), # Round size for consistency
                            "color": span["color"],
                        })
        all_pages_text.append({
            "page_number": page_num,
            "blocks": page_text_blocks
        })

    return all_pages_text

def extract_tables_with_pdfplumber(file_path: str) -> list:
    """
    Uses pdfplumber to extract all tables from each page of a PDF.
    """
    print("\n[DEBUG] Extracting tables with pdfplumber...")
    all_tables = []
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Extract tables from the current page
            tables = page.extract_tables()
            if tables:
                print(f"[DEBUG] Page {page_num}: Found {len(tables)} tables.")
                # The result is a list of tables, where each table is a list of rows
                all_tables.append({
                    "page_number": page_num,
                    "tables": tables
                })
    return all_tables

# def extract_images(doc:fitz.Document) -> list:
#     """
#     Extracts images from the PDF and saves them to the specified directory.

#     Args:
#         doc: An opened fitz.Document object.
#         output_dir: Directory where extracted images will be saved.

#     Returns:
#         A list of dictionaries containing image metadata.
#     """
#     print("\n[DEBUG] Extracting images...")
#     all_images = []
#     # Loop through each page
#     for page_num in range(doc.page_count):
#         page = doc.load_page(page_num)

#         # Get a list of all images on the current page
#         image_list = page.get_images(full=True)
#         if image_list:
#             print(f"[DEBUG] Page {page_num}: Found {len(image_list)} images.")


#         # Loop through the images on the page
#         for img_index,img_info in enumerate(image_list):
#             xref = img_info[0]


#             # Extract the raw image data (bytes and extension)
#             base_image = doc.extract_image(xref)
#             image_bytes = base_image["image"]
#             image_ext = base_image["ext"]

#             # Generate a unique name for the image
#             image_name = f"image_{page_num}_{xref}.{image_ext}"

#             all_images.append({
#                 "name": image_name,
#                 "bytes": image_bytes,
#                 "page": page_num
#             })
#     print(f"[DEBUG] PyMuPDF found {len(all_images)} total images in the document.")
#     return all_images



def _extract_images_with_fallback(file_path: str) -> list:
    """
    Fallback function that uses the poppler command-line tool (pdfimages)
    to extract images when PyMuPDF fails.
    """
    print("[DEBUG] PyMuPDF found no images. Trying fallback with Poppler/pdfimages...")
    fallback_images = []
    
    # Create a temporary directory for poppler to save images into
    with python_tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Run the pdfimages command-line tool
            subprocess.run(
                [
                    "pdfimages",
                    "-all",        # Extract all image types (png, jpg, etc.)
                    file_path,     # The path to our PDF
                    os.path.join(temp_dir, "img") # The output path and prefix
                ],
                timeout=30,        # Set a timeout for safety
                check=True,        # Raise an error if the command fails
                capture_output=True # Don't show command output unless there's an error
            )

            # If the command ran successfully, read the images it created
            for filename in os.listdir(temp_dir):
                image_path = os.path.join(temp_dir, filename)
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                
                # We don't know the original page number, so we'll assign it to page 0
                fallback_images.append({
                    "name": filename,
                    "bytes": image_bytes,
                    "page": 0 
                })

        except (subprocess.CalledProcessError, FileNotFoundError):
            # This will happen if poppler isn't installed or if it fails
            print("[ERROR] Fallback image extraction failed. Ensure 'poppler' is installed and in your system's PATH.")
            return [] # Return empty list if fallback fails
            
    print(f"[DEBUG] Poppler fallback found {len(fallback_images)} images.")
    return fallback_images


def extract_images(doc: fitz.Document) -> list:
    """
    Extracts images using PyMuPDF, with a fallback to Poppler if no images are found.
    """
    print("\n[DEBUG] Extracting images with PyMuPDF...")
    all_images = []
    # --- This is the PyMuPDF part (same as before) ---
    for page_num in range(doc.page_count):
        for img_index, img_info in enumerate(doc.get_page_images(page_num, full=True)):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_name = f"image_{page_num}_{xref}.{image_ext}"
            all_images.append({"name": image_name, "bytes": image_bytes, "page": page_num})
    
    print(f"[DEBUG] PyMuPDF found {len(all_images)} total images in the document.")

    # --- THE NEW HYBRID LOGIC ---
    if not all_images and doc.page_count > 0:
        # doc.name will give us the path to the temporary file
        return _extract_images_with_fallback(doc.name) # type: ignore
    
    return all_images




if __name__ == "__main__":
    print("--- Running PDF Parser Test ---")
    
    script_dir = os.path.dirname(__file__)
    sample_pdf_path = os.path.join(script_dir, '..', '..', '..', 'test_pdfs', 'how_to_combine_pictures_as_pdf_files.pdf')
    
    doc = None
    try:
        # 1. Open the document
        doc = open_pdf_from_path(sample_pdf_path)
        
        # 2. Extract and print metadata
        metadata = extract_metadata(doc)
        print("\n--- METADATA ---")
        pprint.pprint(metadata)
        
        # 3. Extract and print text from the first page
        text_data = extract_text_with_positions(doc)
        print("\n--- TEXT FROM PAGE 0 (first 5 spans) ---")
        pprint.pprint(text_data[0]["blocks"][:5])

        # 4. Extract image information (NEW STEP)
        image_data = extract_images(doc)
        print("\n--- IMAGE EXTRACTION ---")
        print(f"Found a total of {len(image_data)} images in the document.")
        if image_data:
            first_image = image_data[0]
            # We print the image name and size in bytes, not the raw data
            print(f"Details of first image: name='{first_image['name']}', size={len(first_image['bytes'])} bytes")

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        
    finally:
        # 5. ALWAYS make sure to close the document
        if doc:
            print("\n[DEBUG] Closing PDF document.")
            doc.close()
    
    print("\n--- Test Finished ---")