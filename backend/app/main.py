import os
import io
import zipfile
import tempfile
import logging
from importlib import metadata
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi import FastAPI, Request, UploadFile, File, HTTPException

# Import the functions from our pdf_parser service

from backend.app import html_generator
from backend.app import pdf_parser
from backend.app.exceptions import *

# 1. Create the FastAPI application instance
app = FastAPI(
    title="PDF to HTML Conversion API",
    description="An API to convert uploaded PDF files into responsive HTML documents.",
    version="1.0.0"
)

# 2. Configure CORS (Cross-Origin Resource Sharing)
# This allows our future frontend to communicate with this backend.
# The "*" is a wildcard, which is fine for development, but for production,
# you should restrict this to your actual frontend's domain.
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.exception_handler(PDFProcessingError)
async def pdf_processing_exception_handler(request: Request, exc: PDFProcessingError):
    """
    Handles our custom PDFProcessingError and returns a consistent JSON response.
    """
    logging.error(f"A PDF processing error occurred: {exc.message}")
    return JSONResponse(
        status_code=400, # Bad Request
        content={
            "error": {
                "type": exc.__class__.__name__, # e.g., "InvalidPDFError"
                "message": exc.message
            }
        },
    )


# 3. Set up a basic error handling middleware
# This is a simple catch-all for any unexpected errors.
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        # You should probably log the error here
        logging.error(f"An unexpected error occurred: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": "An internal server error occurred."},
        )


# 4. Create our first endpoint (a "health check")
# This is a simple route to verify that the server is running.
@app.get("/", response_class=FileResponse)
async def read_index():
    """
    Serves the main index.html file.
    """
    return "frontend/index.html"

MAX_FILE_SIZE = 50 * 1024 * 1024

@app.post("/api/v1/pdf-to-html/")
async def convert_pdf_to_html(file: UploadFile = File(...)):
    # --- File Validation (remains the same) ---
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type.")
    
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File size exceeds limit.")

    temp_file_path = ""
    doc = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_file_path = temp_file.name

        doc = pdf_parser.open_pdf_from_path(temp_file_path)
        total_pages = doc.page_count
        
        all_text_data = pdf_parser.extract_text_with_positions(doc)
        all_image_data = pdf_parser.extract_images(doc)
        all_table_data = pdf_parser.extract_tables_with_pdfplumber(temp_file_path) # <-- New call

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # --- LOOP TO GENERATE HTML FOR EACH PAGE USING THE 2-STAGE PROCESS ---
            for page_num in range(total_pages):
                current_page = page_num + 1
                page_text_blocks = all_text_data[page_num]['blocks']
                page_image_data = [img for img in all_image_data if img['page'] == page_num]
                page_tables = next((t['tables'] for t in all_table_data if t['page_number'] == page_num), [])

                # STAGE 1: PDF data to Markdown
                markdown_content = html_generator.generate_markdown_from_data(
                    page_text_blocks=page_text_blocks,
                    page_image_data=page_image_data,
                    page_tables=page_tables
                )
                
                # STAGE 2: Markdown to responsive HTML with navigation
                final_html = html_generator.generate_html_from_markdown(
                    markdown_content=markdown_content,
                    current_page=current_page,
                    total_pages=total_pages
                )
                
                zip_file.writestr(f"page-{current_page}.html", final_html)

            # ... (Adding CSS and Images to the ZIP remains the same) ...
            zip_file.writestr("style.css", "body { font-family: sans-serif; color: #333; margin: 2em; }")
            if all_image_data:
                for image in all_image_data:
                    zip_file.writestr(f"images/{image['name']}", image["bytes"])
        
        zip_buffer.seek(0)
        download_filename = f"converted_{os.path.splitext(file.filename)[0]}.zip" # type: ignore
        return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={download_filename}"})

        
    except PDFProcessingError as e:
        raise e
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred."
        )
    finally:
        if doc:
            doc.close()
        if temp_file_path and os.path.exists(temp_file_path): # type: ignore
            os.remove(temp_file_path)

