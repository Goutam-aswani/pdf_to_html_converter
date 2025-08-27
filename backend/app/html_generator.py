import os
from dotenv import load_dotenv
import groq
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from backend.app.config import settings
from pydantic import SecretStr    
load_dotenv()
groq_api_key = SecretStr(settings.groq_api_key)

# def format_data_for_llm(text_data: list, image_data: list) -> str:
#     """Converts both text and image data into a simple string for the LLM."""
#     formatted_strings = []
    
#     # This assumes we are only processing the first page for now
#     page_num = 0
#     formatted_strings.append(f"--- Page {page_num} Content ---")

#     # Format text blocks for the first page
#     page_text_blocks = text_data[0]['blocks'] if text_data else []
#     if not page_text_blocks:
#         formatted_strings.append("No text found on this page.")
#     else:
#         formatted_strings.append("\n**Text Elements:**")
#         for block in page_text_blocks:
#             bbox = [round(c) for c in block['bbox']]
#             formatted_strings.append(
#                 f"- Text: \"{block['text']}\" | Position (x1,y1,x2,y2): {bbox} | Size: {block['size']}"
#             )
            
#     # Format image blocks for the first page
#     page_image_blocks = [img for img in image_data if img['page'] == page_num]
#     if page_image_blocks:
#         formatted_strings.append("\n**Image Elements:**")
#         for image in page_image_blocks:
#             # We need to get the image's bbox from the parser. Let's assume we will add it.
#             # For now, we'll just list the image names.
#             # We will improve this in the next step.
#             formatted_strings.append(f"- Image Filename: \"{image['name']}\"")


#     return "\n".join(formatted_strings)


# def format_data_for_llm(page_text_blocks: list, page_image_data: list) -> str:
#     """Converts a single page's data into a simple string for the LLM."""
#     formatted_strings = ["**Text Elements:**"]
#     for block in page_text_blocks:
#         bbox = [round(c) for c in block['bbox']]
#         formatted_strings.append(
#             f"- Text: \"{block['text']}\" | Position (x1,y1,x2,y2): {bbox} | Size: {block['size']}"
#         )

#     if page_image_data:
#         formatted_strings.append("\n**Image Elements:**")
#         for image in page_image_data:
#             formatted_strings.append(f"- Image Filename: \"{image['name']}\"")
    
#     return "\n".join(formatted_strings)


# In backend/app/services/html_generator.py

def format_data_for_llm(page_text_blocks: list, page_image_data: list, page_tables: list) -> str:
    """Converts a page's text, image, and table data into a string for the LLM."""
    formatted_strings = ["**Text Elements:**"]
    # ... (text formatting remains the same) ...
    for block in page_text_blocks:
        bbox = [round(c) for c in block['bbox']]
        formatted_strings.append(
            f"- Text: \"{block['text']}\" | Position (x1,y1,x2,y2): {bbox} | Size: {block['size']}"
        )
        
    if page_image_data:
        # ... (image formatting remains the same) ...
        formatted_strings.append("\n**Image Elements:**")
        for image in page_image_data:
            formatted_strings.append(f"- Image Filename: \"{image['name']}\"")

    if page_tables:
        formatted_strings.append("\n**PRE-EXTRACTED TABLES (MUST be formatted as Markdown tables):**")
        for i, table in enumerate(page_tables):
            formatted_strings.append(f"\n--- Table {i+1} ---")
            # Convert the list of lists into a simple string representation for the prompt
            table_str = '\n'.join([' | '.join(map(str, row)) for row in table])
            formatted_strings.append(table_str)
            
    return "\n".join(formatted_strings)

def generate_markdown_from_data(page_text_blocks: list, page_image_data: list, page_tables: list) -> str:
    """
    Uses an LLM to convert raw PDF data and structured table data into Markdown.
    Includes a fallback for pages with too much content.
    """
    # Format the data first so we can check its size
    formatted_data = format_data_for_llm(page_text_blocks, page_image_data, page_tables)

    # --- SAFETY VALVE: Check token count before sending to LLM ---
    # A rough estimate: 1 token is about 4 characters. We'll set a safe limit.
    # The Llama3-70b model on Groq has a large context, but the input prompt can still be too large.
    # Let's set a conservative input limit of 15,000 characters.
    MAX_CHARS = 15000 
    if len(formatted_data) > MAX_CHARS:
        print(f"\n[WARNING] Page content is too large ({len(formatted_data)} chars). Using fallback Markdown generator.")
        
        # Create a simple Markdown dump instead of calling the LLM
        fallback_md = [
            "# Page Content Too Large for Detailed Analysis",
            "The following is a raw text dump of the page content. Formatting has been simplified to avoid exceeding AI processing limits.",
            "\n---\n"
        ]
        for block in page_text_blocks:
            fallback_md.append(block['text'])
        
        return "\n\n".join(fallback_md)
    # --- End of Safety Valve ---

    # # If the data is small enough, proceed with the LLM call as normal
    # google_api_key = os.getenv("GOOGLE_API_KEY")
    # if not google_api_key:
    #     raise ValueError("GOOGLE_API_KEY not found in environment variables.")
    # groq_api_key = os.getenv("GROQ_API_KEY")
    # if not groq_api_key:
    #     raise ValueError("GROQ_API_KEY not found in environment variables.")

    llm = ChatGoogleGenerativeAI(
        model = "gemini-2.0-flash-lite",
        google_api_key = settings.google_api_key,
        temperature=0
    )

    system_prompt = (
        "You are an expert document analysis AI. Your task is to synthesize raw text elements and pre-extracted table data into a single, clean Markdown document.\n"
        "1.  **Prioritize Table Data:** Data provided under 'PRE-EXTRACTED TABLES' is highly accurate. You MUST format this data using proper Markdown table syntax (`| Header | ... |`).\n"
        "2.  **Use Text for Context:** Use the 'Text Elements' to create surrounding paragraphs and headings. Do NOT repeat text that is already present in the tables.\n"
        "3.  **Integrate Content:** Merge the tables and other text into a cohesive document.\n"
        "4.  **Handle Images:** Represent any images using Markdown image syntax.\n"
        "Your output must be ONLY the raw Markdown content."
    )
    
    human_prompt = "Here is the data for the page:\n\n{pdf_data}"
    
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain = prompt | llm | StrOutputParser()
    
    print(f"\n[DEBUG] Stage 1: Converting PDF data to Markdown (with pdfplumber tables)...")
    markdown_content = chain.invoke({"pdf_data": formatted_data})
    print(f"[DEBUG] Stage 1: Markdown generated successfully.")
    
    return markdown_content


def generate_html_for_page(page_text_blocks: list, page_image_data: list, current_page: int, total_pages: int) -> str:
    """
    Uses an LLM to generate HTML for a single page, including navigation.
    """
    if not groq_api_key.get_secret_value():
        raise ValueError("GROQ_API_KEY environment variable not set.")

    # llm = ChatGroq(model = "llama3-70B-8192",
    #                 api_key = groq_api_key, 
    #                 temperature=0
    # )
    llm = ChatGoogleGenerativeAI(
        model = "gemini-2.0-flash-lite",
        google_api_key = settings.google_api_key,
        temperature=0
    )
    # llm = ChatOpenAI(
    # model="qwen/qwen-2.5-coder-32b-instruct:free",  # choose from OpenRouter's model list
    # openai_api_base="https://openrouter.ai/api/v1",
    # api_key=settings.qwen_api_key,
    # api_key=settings.qwen_api_key,
# )

    # Create navigation instructions for the prompt
    nav_instructions = f"The current page is {current_page} of {total_pages}. "
    if current_page > 1:
        nav_instructions += f"Include a link to the previous page: '<a href=\"page-{current_page - 1}.html\">Previous</a>'. "
    if current_page < total_pages:
        nav_instructions += f"Include a link to the next page: '<a href=\"page-{current_page + 1}.html\">Next</a>'. "

    system_prompt = (
        "You are an expert web developer creating an HTML representation of a PDF page. "
        "Create a single HTML file using CSS absolute positioning for text and images. "
        "Image `src` attributes must point to the `images/` directory. "
        f"At the bottom of the `<body>`, you MUST add a navigation div. {nav_instructions}"
        "The final output must be ONLY the raw HTML code, starting with <!DOCTYPE html>."
    )
    
    human_prompt = "Here is the data for the page:\n\n{pdf_data}"

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain = prompt | llm | StrOutputParser()
    formatted_data = format_data_for_llm(page_text_blocks, page_image_data)
    
    print(f"\n[DEBUG] Generating HTML for page {current_page}/{total_pages}...")
    html_content = chain.invoke({"pdf_data": formatted_data})
    print(f"[DEBUG] Received HTML for page {current_page}.")
    
    return html_content

# In backend/app/services/html_generator.py

def generate_html_from_markdown(markdown_content: str, current_page: int, total_pages: int) -> str:
    """
    Uses an LLM to convert Markdown into a styled, responsive HTML page with navigation.
    """
    # ... (LLM initialization remains the same) ...
#     llm = ChatOpenAI(
#     model="qwen/qwen-2.5-coder-32b-instruct:free",  # choose from OpenRouter's model list
#     openai_api_base="https://openrouter.ai/api/v1",
#     api_key=settings.qwen_api_key,
# )
    llm = ChatGoogleGenerativeAI(
        model = "gemini-2.0-flash",
        google_api_key = settings.google_api_key,
        temperature=0
    )

    # Create navigation instructions for the prompt
    nav_instructions = ""
    if total_pages > 1:
        nav_links = []
        if current_page > 1:
            nav_links.append(f'<a href="page-{current_page - 1}.html">Previous</a>')
        if current_page < total_pages:
            nav_links.append(f'<a href="page-{current_page + 1}.html">Next</a>')
        
        nav_html = f"<footer><nav>{' | '.join(nav_links)}</nav><p>Page {current_page} of {total_pages}</p></footer>"
        nav_instructions = f"At the end of the `<body>`, before the closing tag, you MUST include this exact navigation HTML: {nav_html}"

    system_prompt = f"""
You are an expert front-end developer. Your task is to convert the given content (in Markdown format) into a complete, production-ready HTML5 document based on the specified design requirements.

DESIGN REQUIREMENTS:
- Layout: Use a single-column, responsive flexbox layout.
- Color scheme: A modern, clean palette with dark grey text (#333), a white background (#FFF), and a subtle blue for links.
- Typography: Use a common sans-serif font like Arial or Helvetica with a base font size of 16px.
- Responsive: The layout must be mobile-first.

OUTPUT FORMAT:
- A complete HTML5 document.
- All CSS must be embedded in a single `<style>` tag in the `<head>`.
- Use a clean, semantic HTML structure (e.g., <main>, <article>, <h1>, <p>).
- {nav_instructions}
- Output ONLY the raw HTML code, starting with <!DOCTYPE html>.
"""
    
    human_prompt = "CONTENT:\n\n{markdown_content}"
    
    # ... (The rest of the function remains the same) ...
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain = prompt | llm | StrOutputParser() # Use StrOutputParser from langchain_core.output_parsers
    
    print(f"\n[DEBUG] Stage 2: Converting Markdown to HTML for page {current_page}...")
    html_content = chain.invoke({"markdown_content": markdown_content})
    print(f"[DEBUG] Stage 2: Responsive HTML generated successfully for page {current_page}.")
    
    return html_content


# if not groq_api_key.get_secret_value():
#         raise ValueError("GROQ_API_KEY environment variable not set.")

#     # llm = ChatGroq(model = "llama3-70B-8192",
#     #                 api_key = groq_api_key, 
#     #                 temperature=0
#     # )
#     llm = ChatGoogleGenerativeAI(
#         model = "gemini-1.5-flash",
#         google_api_key = settings.google_api_key,
#         temperature=0
#     )
# In html_generator.py, replace the test block

if __name__ == "__main__":
    from pdf_parser import open_pdf_from_path, extract_text_with_positions, extract_images

    print("--- Running 2-Stage Generation Test (Full Process) ---")
    
    script_dir = os.path.dirname(__file__)
    sample_pdf_path = os.path.join(script_dir, '..', '..', '..', 'test_pdfs', 'how_to_combine_pictures_as_pdf_files.pdf')
    output_html_path = os.path.join(script_dir, '..', '..', '..', 'output.html')

    doc = None
    try:
        print(f"Loading and parsing PDF from: {sample_pdf_path}")
        doc = open_pdf_from_path(sample_pdf_path)
        text_data = extract_text_with_positions(doc)
        image_data = extract_images(doc)
        
        page_text_blocks = text_data[0]['blocks']
        page_image_data = [img for img in image_data if img['page'] == 0]

        # STAGE 1: Convert PDF data to Markdown
        generated_markdown = generate_markdown_from_data(page_text_blocks, page_image_data)
        
        # STAGE 2: Convert Markdown to responsive HTML
        final_html = generate_html_from_markdown(generated_markdown)
        
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        
        print(f"\n✅ Success! Final HTML file generated at: {output_html_path}")
        print("Open the output.html file in your browser to see the new responsive design.")

    except Exception as e:
        print(f"\n❌ An error occurred during testing: {e}")
        
    finally:
        if doc:
            doc.close()
    
    print("\n--- Test Finished ---")