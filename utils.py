import os
import json
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
from openai import OpenAI
from docx import Document  # For .docx files
from docx2txt import process as docx2txt_process  # To extract text from docx
from PIL import Image  # To handle images for OCR from screenshots
from pdf2image import convert_from_path
from pytesseract import image_to_string
from dotenv import load_dotenv  # Ensure this is imported correctly
import re

import platform
import subprocess

# Load environment variables
load_dotenv()

import platform
import subprocess

def extract_text_from_file(file):
    file_extension = os.path.splitext(file)[1]
    text_content = ""

    # Handle PDF files using MuPDF
    if file_extension == ".pdf":
        try:
            pdf_document = fitz.open(file)
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                text_content += page.get_text()

            # If MuPDF fails to extract any text, fallback to OCR
            if len(text_content.strip()) == 0:
                raise ValueError("No text extracted using MuPDF, falling back to OCR...")

        except Exception as e:
            print(f"MuPDF error: {e}")
            print("Falling back to OCR...")
            images = convert_from_path(file)
            for image in images:
                text_content += pytesseract.image_to_string(image)

    # Handle .docx files using python-docx and fallback to docx2txt
    elif file_extension == ".docx":
        try:
            # First try python-docx
            doc = Document(file)
            for paragraph in doc.paragraphs:
                text_content += paragraph.text + "\n"

            # If python-docx fails to extract any text, fallback to docx2txt
            if not text_content.strip():
                print("No text extracted using python-docx, falling back to docx2txt...")
                text_content = docx2txt_process(file)

                if not text_content.strip():
                    raise ValueError("No text extracted using docx2txt either, falling back to OCR...")

        except Exception as e:
            print(f"docx2txt error: {e}")
            print("Falling back to OCR for .docx file...")

            # Convert the document to images and apply OCR
            try:
                doc_images = convert_from_path(file)
                for image in doc_images:
                    text_content += pytesseract.image_to_string(image)

                if not text_content.strip():
                    raise ValueError("OCR failed to extract text from the .docx file.")
            except Exception as e:
                print(f"OCR fallback for .docx failed: {e}")
                text_content = ""  # Set empty to indicate failure

    # Handle .doc files using antiword on Linux/Mac
    elif file_extension == ".doc":
        if platform.system() in ["Linux", "Darwin"]:  # Linux or Mac
            try:
                result = subprocess.run(["antiword", file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                text_content = result.stdout.decode('utf-8')
                if result.returncode != 0:
                    raise Exception(f"antiword error: {result.stderr.decode('utf-8')}")
            except Exception as e:
                print(f"Error processing .doc file: {e}")
                text_content = ""  # Ensure it's not sent empty to OpenAI
        else:
            # If on Windows or other platform without antiword
            print(f"Warning: .doc file processing is not supported on this platform. Skipping file: {file}")
            text_content = ""

    return text_content

def match_awards_with_openai(resume_awards, award_list, award_list2):
    """
    Use OpenAI to match resume awards against two reference lists with high accuracy.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Format lists into readable blocks
    award_list_str = "\n".join(award_list)
    award_list2_str = "\n".join(award_list2)
    resume_awards_str = "\n".join(resume_awards)

    # Refined prompt with clear and concise instructions
    prompt = (
        "You are an award classification assistant. Compare each award in the 'Resume Awards' list against two reference lists:\n"
        "1. List 1 (竞赛人才): Awards representing competitions and challenges.\n"
        "2. List 2 (顶会人才): Awards for top-tier conferences and research achievements.\n\n"
        "Tasks:\n"
        "1. For each award in the 'Resume Awards', find if it matches (exact or semantically) any award in List 1 or List 2.\n"
        "2. If it matches an award in List 1, mark it as 'list': 1.\n"
        "3. If it matches an award in List 2, mark it as 'list': 2.\n"
        "4. If it matches both lists, mark it as 'list': 'Both'.\n"
        "5. If no match is found, set 'list': 'No Awards'.\n\n"
        "Return the results in JSON array format. Each entry should contain:\n"
        "- 'resume_award': The award from the resume.\n"
        "- 'matched_award': The closest matching award from List 1 or List 2.\n"
        "- 'list': 1, 2, 'Both', or 'No Awards'.\n"
        "- 'confidence': 'High' if the match is exact or very close, 'Medium' otherwise.\n\n"
        "Resume Awards:\n"
        f"{resume_awards_str}\n\n"
        "List 1 (竞赛人才):\n"
        f"{award_list_str}\n\n"
        "List 2 (顶会人才):\n"
        f"{award_list2_str}\n\n"
        "Return only valid JSON output."
    )

    # Call OpenAI API
    try:
        print("Sending prompt to OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        # Extract and parse the message content from OpenAI response
        raw_response = completion.choices[0].message.content
        print(f"\nAlexAI response: {raw_response}")

        # Clean the response content by removing any backticks, "json" tags, or extra characters
        cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
        # Remove trailing commas before closing braces/brackets
        cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)
      
        print(f"\nOpenAI Response:\n{cleaned_content}")
        return json.loads(cleaned_content)

    except Exception as e:
        print(f"Error during OpenAI API call: {e}")
        return []

def parse_content(text_content, target_school_list, award_list, award_list2):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    system_message = (
        "You are a professional-grade resume parser. "
        "You will be provided with text content extracted from a resume file. "
        "Your task is to return clean, accurate JSON formatted data with the following keys: "
        "- 'education_level' (highest level of education: Bachelor's, Master's, or PhD)\n"
        "- 'name' (full name of the candidate)\n"
        "- 'major' (in Simplified Chinese)\n"
        "- 'grad_year' (graduation year)\n"
        "- 'phd_school' (in Simplified Chinese only)\n"
        "- 'master_school' (in Simplified Chinese only)\n"
        "- 'bachelor_school' (in Simplified Chinese only)\n"
        "- 'awards' (list of awards or achievements mentioned in the resume, normalized if possible)\n"
        "If not applicable, fill the fields with 'NA'."
    )

    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": text_content}
        ]
    )

    # Extract and parse the message content from OpenAI response
    raw_response = completion.choices[0].message.content
    print(f"\nAlexAI response: {raw_response}")

    # Clean the response content by removing any backticks, "json" tags, or extra characters
    cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
    # Remove trailing commas before closing braces/brackets
    cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

    try:
        # Attempt to parse cleaned content as JSON
        parsed_info = json.loads(cleaned_content)

        # Function to remove text in parentheses
        def clean_school_name(school_name):
            return re.sub(r"\s*\(.*?\)", "", school_name).strip()
        
        # Normalize extracted school names before matching
        parsed_info['phd_school'] = parsed_info.get('phd_school', 'NA')
        parsed_info['master_school'] = parsed_info.get('master_school', 'NA')
        parsed_info['bachelor_school'] = parsed_info.get('bachelor_school', 'NA')

        # Perform match locally, set match status to NA if school is NA
        if parsed_info['phd_school'] == 'NA':
            parsed_info['phd_match_status'] = 'NA'
        else:
            parsed_info['phd_match_status'] = "Match 💚" if parsed_info['phd_school'] in target_school_list else "Not Match 💔"
        print(f"\nPhD School: {parsed_info['phd_school']}, Match Status: {parsed_info['phd_match_status']}")

        if parsed_info['master_school'] == 'NA':
            parsed_info['master_match_status'] = 'NA'
        else:
            parsed_info['master_match_status'] = "Match 💚" if parsed_info['master_school'] in target_school_list else "Not Match 💔"
        print(f"Master's School: {parsed_info['master_school']}, Match Status: {parsed_info['master_match_status']}")

        if parsed_info['bachelor_school'] == 'NA':
            parsed_info['bachelor_match_status'] = 'NA'
        else:
            parsed_info['bachelor_match_status'] = "Match 💚" if parsed_info['bachelor_school'] in target_school_list else "Not Match 💔"
        print(f"Bachelor's School: {parsed_info['bachelor_school']}, Match Status: {parsed_info['bachelor_match_status']}")

        # Extract awards from parsed_info
        parsed_awards = parsed_info.get('awards', [])
        if not parsed_awards:
            parsed_awards = []

        matched_awards = match_awards_with_openai(parsed_awards, award_list, award_list2)
        
        # Determine award status based on matches
        award_status = "No Awards"
        list1_found = False
        list2_found = False

        for match in matched_awards:
            if match.get('confidence') in ['High', 'Medium']:
                if match['list'] == 1:
                    list1_found = True
                elif match['list'] == 2:
                    list2_found = True

        # Determine final award status
        if list1_found and list2_found:
            award_status = "天才"
        elif list1_found:
            award_status = "竞赛人才"
        elif list2_found:
            award_status = "顶会人才"

        parsed_info['award_status'] = award_status
        
        return parsed_info

    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        print(f"Cleaned response: {cleaned_content}")
        raise ValueError(f"Error parsing OpenAI response: {e}")


# Function to sanitize filename components
def sanitize_filename_component(component):
    if component is None:
        component = 'Unknown'  # Default value if None
    elif isinstance(component, int):
        component = str(component)  # Convert integers to strings
    return str(component).replace('/', '_').replace('\\', '_').replace(':', '_').strip()

def generate_filename(parsed_info, args):
    # Function to sanitize filename components
    def sanitize_filename_component(component):
        if component is None:
            component = 'Unknown'  # Default value if None
        elif isinstance(component, int):
            component = str(component)  # Convert integers to strings
        return str(component).replace('/', '_').replace('\\', '_').replace(':', '_').strip()

    # Handle missing or empty fields with default values, using sanitization
    name = sanitize_filename_component(parsed_info.get('name', 'Unknown Name').strip())
    major = sanitize_filename_component(parsed_info.get('major', 'Unknown Major').strip())
    grad_year = sanitize_filename_component(parsed_info.get('grad_year', 'Unknown Year'))

    # Determine the school based on the highest education level
    education_level = parsed_info.get('education_level', "Bachelor's").strip()
    if education_level == "PhD":
        school = sanitize_filename_component(parsed_info.get('phd_school', 'Unknown School').strip())
    elif education_level == "Master's":
        school = sanitize_filename_component(parsed_info.get('master_school', 'Unknown School').strip())
    else:
        school = sanitize_filename_component(parsed_info.get('bachelor_school', 'Unknown School').strip())

    # Match statuses
    phd_match_status = parsed_info.get('phd_match_status', 'NA')
    master_match_status = parsed_info.get('master_match_status', 'NA')
    bachelor_match_status = parsed_info.get('bachelor_match_status', 'NA')

    # Logic to determine final match status
    if education_level == "PhD":
        # If PhD level and PhD school matches, it's a Match
        final_match_status = "Match" if phd_match_status == "Match 💚" else "Not Match"
    elif education_level == "Master's":
        # If Master's level, both Master's and Bachelor's schools must match
        final_match_status = (
            "Match" if master_match_status == "Match 💚" and bachelor_match_status == "Match 💚" else "Not Match"
        )
    elif education_level == "Bachelor's":
        # If Bachelor's level, only Bachelor's school must match
        final_match_status = "Match" if bachelor_match_status == "Match 💚" else "Not Match"
    else:
        # Default to Not Match if no valid education level is provided
        final_match_status = "Not Match"

    # Convert education level to Simplified Chinese
    education_level_ch = {
        "Bachelor's": "本科",
        "Master's": "硕士",
        "PhD": "博士"
    }.get(education_level, "未知")

    # Determine if it's 实习 (intern) or 全职 (full-time)
    job_type = '实习' if grad_year.isdigit() and int(grad_year) > 2024 else '全职'

    # Award status
    award_status = parsed_info.get('award_status', 'No Awards')
    
    # Construct the filename
    filename = f"{final_match_status}-{job_type}-{education_level_ch}-{school}-{grad_year}-{major}-{name}-{award_status}"
    return filename
