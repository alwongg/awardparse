import os
import json
import re
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
from openai import OpenAI
from docx import Document
from docx2txt import process as docx2txt_process
from PIL import Image
from dotenv import load_dotenv
import platform
import subprocess

load_dotenv()

def extract_text_from_file(file):
    """Extract text from various file types (.pdf, .docx, .doc) with fallback OCR."""
    print(f"\n[INFO] Starting text extraction for file: {file}")
    file_extension = os.path.splitext(file)[1].lower()
    text_content = ""

    if file_extension == ".pdf":
        text_content = extract_text_from_pdf(file)
    elif file_extension == ".docx":
        text_content = extract_text_from_docx(file)
    elif file_extension == ".doc":
        text_content = extract_text_from_doc(file)
    else:
        print(f"[WARNING] Unsupported file extension: {file_extension}. Returning empty text.")
    
    return text_content

def extract_text_from_pdf(file):
    """Attempt to extract text from PDF using MuPDF, fallback to OCR if needed."""
    print("[INFO] Detected PDF file. Trying MuPDF text extraction...")
    text_content = ""
    try:
        pdf_document = fitz.open(file)
        for page_num in range(pdf_document.page_count):
            page = pdf_document.load_page(page_num)
            text_content += page.get_text()
        
        if len(text_content.strip()) == 0:
            raise ValueError("No text extracted from PDF via MuPDF.")
    except Exception as e:
        print(f"[ERROR] MuPDF extraction failed: {e}\n[INFO] Falling back to OCR for PDF...")
        text_content = ocr_pdf(file)
    return text_content

def ocr_pdf(file):
    """Perform OCR on a PDF file using pdf2image and pytesseract."""
    text_content = ""
    images = convert_from_path(file)
    for image in images:
        text_content += pytesseract.image_to_string(image)
    return text_content

def extract_text_from_docx(file):
    """Extract text from .docx files using python-docx, fallback to docx2txt or OCR."""
    print("[INFO] Detected DOCX file. Trying python-docx text extraction...")
    text_content = ""
    try:
        doc = Document(file)
        for paragraph in doc.paragraphs:
            text_content += paragraph.text + "\n"
        
        if not text_content.strip():
            print("[WARNING] No text via python-docx. Trying docx2txt...")
            text_content = docx2txt_process(file)
            if not text_content.strip():
                raise ValueError("No text extracted via docx2txt either.")
    except Exception as e:
        print(f"[ERROR] DOCX extraction failed: {e}\n[INFO] Falling back to OCR for DOCX...")
        text_content = ocr_pdf(file)  # Using same OCR method as PDF for simplicity
    
    return text_content

def extract_text_from_doc(file):
    """Extract text from .doc files using antiword on Linux/Mac."""
    print("[INFO] Detected DOC file. Trying antiword text extraction...")
    if platform.system() in ["Linux", "Darwin"]:
        try:
            result = subprocess.run(["antiword", file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            text_content = result.stdout.decode('utf-8')
            if result.returncode != 0:
                raise Exception(f"antiword error: {result.stderr.decode('utf-8')}")
        except Exception as e:
            print(f"[ERROR] antiword failed: {e}. No fallback available for .doc on this platform.")
            text_content = ""
    else:
        print("[WARNING] .doc file processing not supported on this platform.")
        text_content = ""
    return text_content

def match_schools_with_openai(parsed_info, target_school_list):
    """
    Use OpenAI to semantically match schools from the resume against a target school list.
    Updates parsed_info with match status fields.
    """
    print("\n[INFO] Starting semantic school matching via OpenAI...")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    target_schools_str = "\n".join(target_school_list)
    phd_school = parsed_info.get('phd_school', 'NA')
    master_school = parsed_info.get('master_school', 'NA')
    bachelor_school = parsed_info.get('bachelor_school', 'NA')

    prompt = (
        "You are a professional school name matcher. Compare each school name from the resume against the target school list.\n"
        "Tasks:\n"
        "1. For each school, find the best match in the target school list based on semantic similarity.\n"
        "2. Treat synonyms or alternative names as a match. For example, if the resume lists a school name with a country or city prefix (e.g., 新加坡南洋理工大学), treat it as the same as 南洋理工大学.\n"
        "3. Return the match status ('Match' or 'Not Match') for each school (PhD, Master's, Bachelor's).\n"
        "4. If no match is found, return 'Not Match'.\n\n"
        "Resume Schools:\n"
        f"- PhD: {phd_school}\n"
        f"- Master's: {master_school}\n"
        f"- Bachelor's: {bachelor_school}\n\n"
        "Target Schools:\n"
        f"{target_schools_str}\n\n"
        "Return the results in JSON format with the following keys:\n"
        "- 'phd_match_status': 'Match' or 'Not Match'\n"
        "- 'master_match_status': 'Match' or 'Not Match'\n"
        "- 'bachelor_match_status': 'Match' or 'Not Match'\n"
    )

    try:
        print("[INFO] Sending prompt for school matching to OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = completion.choices[0].message.content

        print("[DEBUG] Raw OpenAI school matching response:")
        print(raw_response)

        cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
        cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

        match_results = json.loads(cleaned_content)
        parsed_info['phd_match_status'] = match_results.get('phd_match_status', 'Not Match')
        parsed_info['master_match_status'] = match_results.get('master_match_status', 'Not Match')
        parsed_info['bachelor_match_status'] = match_results.get('bachelor_match_status', 'Not Match')

        print("[INFO] School matching completed.")
        print(f"[INFO] PhD School: '{phd_school}' => {parsed_info['phd_match_status']}")
        print(f"[INFO] Master's School: '{master_school}' => {parsed_info['master_match_status']}")
        print(f"[INFO] Bachelor's School: '{bachelor_school}' => {parsed_info['bachelor_match_status']}")

    except Exception as e:
        print(f"[ERROR] Semantic school matching failed: {e}")
        parsed_info['phd_match_status'] = 'Not Match'
        parsed_info['master_match_status'] = 'Not Match'
        parsed_info['bachelor_match_status'] = 'Not Match'

    return parsed_info

def determine_award_status(matched_awards):
    """
    Determine final award status based on matched awards.
    - If awards from both lists are matched with confidence, return "天才".
    - If only list 1 awards are matched, return "竞赛人才".
    - If only list 2 awards are matched, return "顶会人才".
    - Otherwise, return "".
    """
    list1_found = any(match.get("confidence") in ["High", "Medium"] and match.get("list") == 1 
                      for match in matched_awards)
    list2_found = any(match.get("confidence") in ["High", "Medium"] and match.get("list") == 2
                      for match in matched_awards)

    if list1_found and list2_found:
        return "天才"
    elif list1_found:
        return "竞赛人才"
    elif list2_found:
        return "顶会人才"
    else:
        return ""

def match_awards_with_openai(resume_awards, award_list, award_list2):
    """
    Use OpenAI to match resume awards against two reference lists with high accuracy.
    Return a JSON list of matched results.
    """
    print("\n[INFO] Starting award matching via OpenAI...")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    award_list_str = "\n".join(award_list)
    award_list2_str = "\n".join(award_list2)
    resume_awards_str = "\n".join(resume_awards)

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

    try:
        print("[INFO] Sending prompt for award matching to OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = completion.choices[0].message.content

        print("[DEBUG] Raw OpenAI award matching response:")
        print(raw_response)

        cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
        cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

        matched_awards = json.loads(cleaned_content)
        print("[INFO] Award matching completed.")
        for m in matched_awards:
            print(f"[INFO] Resume Award: '{m.get('resume_award')}' => Matched: '{m.get('matched_award')}', "
                  f"List: {m.get('list')}, Confidence: {m.get('confidence')}")
        return matched_awards

    except Exception as e:
        print(f"[ERROR] Award matching failed: {e}")
        return []

def parse_content(text_content, target_school_list, award_list, award_list2):
    """
    Send extracted resume text to OpenAI for parsing into a structured JSON with the required fields.
    Then perform school name matching, award classification, and return parsed_info dict.
    """

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Updated system message instructions
    system_message = (
        "You are a professional-grade resume parser. "
        "You will be provided with text content extracted from a candidate's resume. Your job is to analyze and return a JSON object containing specific fields.\n\n"
        "Your JSON output keys:\n"
        "1. 'education_level': The highest education level (options: '本科', '硕士', '博士', or 'N/A' if unknown). Determine based on the resume.\n"
        "   - If the candidate has a PhD, return '博士'\n"
        "   - If the candidate has a Master's as the highest degree, return '硕士'\n"
        "   - If the candidate has a Bachelor's as the highest degree, return '本科'\n"
        "   - If unsure, return 'N/A'\n\n"
        "2. 'name': The candidate's full name as found on the resume. If it's in English, return English. If in Chinese, return Chinese.\n\n"
        "3. 'major': The major (program of study) of the HIGHEST education level, in Simplified Chinese.\n\n"
        "4. 'grad_year': The graduation year of the highest education level:\n"
        "   - If a year range is given (e.g., '08/2022 – Present'), infer that the candidate is still studying and estimate graduation year based on:\n"
        "     - PhD: 4 years after the start year\n"
        "     - Master's: 2 years after the start year\n"
        "     - Bachelor's: 4 years after the start year\n"
        "   - If only one year is given without range, try to infer if it's start or grad year. If uncertain, assume it's the grad year.\n\n"
        "5. 'phd_school', 'master_school', 'bachelor_school': The schools for each degree the candidate has, in Simplified Chinese.\n"
        "   - If the school is known internationally and a recognized Chinese name exists, use that. Example:\n"
        "     - 'Nanyang Technological University Singapore' -> '南洋理工大学'\n"
        "     - 'Zhejiang University' -> '浙江大学'\n"
        "   - If the school name is only in English and no known Chinese translation is commonly used, return the name as is but ideally in Simplified Chinese if known.\n"
        "   - If the candidate does not hold that degree level, return 'NA'.\n\n"
        "6. 'awards': A list of awards the candidate achieved, normalized if possible.\n\n"
        "7. 'candidate_location': The candidate's country location in Simplified Chinese. Determine by priority:\n"
        "   1. If a location (country) is clearly stated at the top (e.g. resume header), use that.\n"
        "   2. If not found, use the highest education institution's country location.\n"
        "   3. If the most recent work experience is more recent than the graduation year, use that work experience's country location.\n"
        "   If none can be determined, return '未知'. Examples of countries in Simplified Chinese: '美国', '中国', '英国', etc.\n\n"
        "8. 'is_qs50': If the highest degree institution is in top 50 QS ranking, return 'QS50'. Otherwise '非QS50'. If unsure, assume '非QS50'.\n\n"
        "9. 'is_chinese_name': 'Yes' if the candidate's name is Chinese, 'No' otherwise.\n\n"
        "10. The logic for determining the final file name outside of this function is based on these values, so ensure accuracy.\n\n"
        "Additional Notes:\n"
        "- Do not return 'NA' for a school if it is mentioned. Only return 'NA' if that degree level does not exist.\n"
        "- Awards: just list them. The classification (竞赛人才, 顶会人才, 天才) will be handled after the award matching step.\n"
        "- Make sure the output is strictly valid JSON without extra commentary.\n"
    )

    print("[INFO] Sending resume text to OpenAI for parsing...")
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": text_content},
        ],
        temperature=0,  # reduce randomness for consistency
    )

    raw_response = completion.choices[0].message.content
    print("[DEBUG] Raw OpenAI resume parsing response:")
    print(raw_response)

    # Clean the response for JSON parsing
    cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
    cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

    try:
        parsed_info = json.loads(cleaned_content)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decoding failed: {e}\n[DEBUG] Cleaned response:\n{cleaned_content}")
        raise ValueError("Error parsing OpenAI response")

    # Perform semantic school matching (updates the parsed_info with match status)
    parsed_info = match_schools_with_openai(parsed_info, target_school_list)

    # Match awards and determine award status
    parsed_awards = parsed_info.get("awards", [])
    matched_awards = match_awards_with_openai(parsed_awards, award_list, award_list2)
    parsed_info["award_status"] = determine_award_status(matched_awards)

    return parsed_info

def sanitize_filename_component(component):
    """Sanitize filename components by removing invalid chars and trimming."""
    if component is None:
        return 'Unknown'
    return str(component).replace('/', '_').replace('\\', '_').replace(':', '_').strip()

def generate_filename(parsed_info, args):
    """
    Generate a structured filename using parsed resume info.

    Format:
    [MatchStatus]-[JobType]-[EducationLevelCH]-[Name]-[School]-[Major]-[GradYear]-[AwardStatus(optional)]-[CandidateLocation]-[QS50(if applicable)]

    Where:
    - MatchStatus: "Match" or "Not Match" based on the logic:
      * If highest is PhD: match if phd_school matches target list
      * If highest is Master's: match if master_school and bachelor_school match
      * If highest is Bachelor's: match if bachelor_school matches

    - JobType: "实习" if grad_year > 2024, else "全职"

    - EducationLevelCH: "本科", "硕士", "博士" or "N/A" if unknown

    - Name: Candidate name as given (Chinese or English)

    - School: Highest level school in Simplified Chinese

    - Major: in Simplified Chinese

    - GradYear: The inferred or calculated graduation year

    - AwardStatus (optional): "竞赛人才" or "顶会人才" or "天才", if applicable, otherwise omit

    - CandidateLocation: The candidate's country location in simplified Chinese or "未知"

    - QS50: "QS50" if top 50, else omit
    """

    name = sanitize_filename_component(parsed_info.get("name", "Unknown Name"))
    major = sanitize_filename_component(parsed_info.get("major", "Unknown Major"))
    grad_year = sanitize_filename_component(parsed_info.get("grad_year", "Unknown Year"))
    education_level_ch = parsed_info.get("education_level", "N/A").strip()

    # Schools
    phd_school = parsed_info.get("phd_school", "NA")
    master_school = parsed_info.get("master_school", "NA")
    bachelor_school = parsed_info.get("bachelor_school", "NA")

    # Determine highest education level to pick the school
    if education_level_ch == "博士":
        school = phd_school
        level = "PhD"
    elif education_level_ch == "硕士":
        school = master_school
        level = "Master's"
    elif education_level_ch == "本科":
        school = bachelor_school
        level = "Bachelor's"
    else:
        # If we cannot determine education level, set a default
        school = "NA"
        level = "N/A"

    school = sanitize_filename_component(school)

    # Determine match status
    phd_match_status = parsed_info.get("phd_match_status", "Not Match")
    master_match_status = parsed_info.get("master_match_status", "Not Match")
    bachelor_match_status = parsed_info.get("bachelor_match_status", "Not Match")

    if level == "PhD":
        final_match_status = "Match" if phd_match_status == "Match" else "Not Match"
    elif level == "Master's":
        final_match_status = "Match" if (master_match_status == "Match" and bachelor_match_status == "Match") else "Not Match"
    elif level == "Bachelor's":
        final_match_status = "Match" if bachelor_match_status == "Match" else "Not Match"
    else:
        # If we don't know the level, can't determine match accurately
        # Default to "Not Match"
        final_match_status = "Not Match"

    # Job type based on grad_year
    # If grad_year is numeric and > 2024 => 实习, else 全职
    job_type = "全职"
    if grad_year.isdigit():
        if int(grad_year) > 2024:
            job_type = "实习"

    award_status = parsed_info.get("award_status", "")
    candidate_location = sanitize_filename_component(parsed_info.get("candidate_location", ""))
    # If candidate_location is empty or NA, skip
    if candidate_location in ["", "NA"]:
        candidate_location = ""

    is_qs50 = parsed_info.get("is_qs50", "")
    qs50_label = "QS50" if is_qs50 == "QS50" else ""

    components = [
        final_match_status,
        job_type,
        education_level_ch,
        name,
        school,
        major,
        grad_year,
    ]

    if award_status:
        components.append(award_status)

    if candidate_location:
        components.append(candidate_location)

    if qs50_label:
        components.append(qs50_label)

    filename = "-".join(filter(None, components))
    return filename

