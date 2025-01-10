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

from difflib import SequenceMatcher

def exact_match(school_name, target_list):
    """Check for exact string match ignoring leading/trailing whitespace."""
    school_stripped = school_name.strip()
    return any(school_stripped == t.strip() for t in target_list)

def fuzzy_match(school_name, target_list, threshold=0.9):
    """
    Use difflib to see if there's a sufficiently close match (e.g. >= 0.9).
    Return True if we find a match above threshold, else False.
    """
    for t in target_list:
        ratio = SequenceMatcher(None, school_name.strip(), t.strip()).ratio()
        if ratio >= threshold:
            return True
    return False

def check_local_school_matches(parsed_info, target_school_list, fuzzy_threshold=0.9):
    """
    Check local matches for PhD, Master's, Bachelor's schools.
    1. If exact match or fuzzy match >= threshold, mark 'Match'.
    2. Otherwise, mark 'Not Match'.
    Returns a list of degrees that are still 'Not Match' and need OpenAI semantic matching.
    """
    print("[DEBUG] Performing local (exact/fuzzy) school matching...")

    not_matched_degrees = []

    for degree in ['phd', 'master', 'bachelor']:
        school_key = f"{degree}_school"
        match_status_key = f"{degree}_match_status"

        school_name = parsed_info.get(school_key, 'NA')
        if school_name == 'NA':
            print(f"[DEBUG] {degree.capitalize()} school is 'NA' (not provided). Marking as 'Not Match'.")
            parsed_info[match_status_key] = 'Not Match'
            continue

        print(f"[DEBUG] Checking local match for {degree.capitalize()} school: '{school_name}'")

        # 1) Exact match check
        if exact_match(school_name, target_school_list):
            parsed_info[match_status_key] = 'Match'
            print(f"[DEBUG] Exact match found locally for {degree.capitalize()} school: '{school_name}'")
        else:
            # 2) Fuzzy match check
            if fuzzy_match(school_name, target_school_list, fuzzy_threshold):
                parsed_info[match_status_key] = 'Match'
                print(f"[DEBUG] Fuzzy match (>{fuzzy_threshold}) found locally for {degree.capitalize()} school: '{school_name}'")
            else:
                parsed_info[match_status_key] = 'Not Match'
                not_matched_degrees.append(degree)
                print(f"[DEBUG] No local match for {degree.capitalize()} school: '{school_name}'. Will need OpenAI matching.")

    return not_matched_degrees, parsed_info

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
        print(f"[WARNING] Unsupported file extension '{file_extension}'. Returning empty text.")
    
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
        print(f"[ERROR] MuPDF extraction failed: {e}")
        print("[INFO] Falling back to OCR for PDF...")
        text_content = ocr_pdf(file)
    return text_content

def ocr_pdf(file):
    """Perform OCR on a PDF file using pdf2image and pytesseract."""
    print("[DEBUG] Performing OCR on PDF using pdf2image + pytesseract...")
    text_content = ""
    images = convert_from_path(file)
    for i, image in enumerate(images, 1):
        print(f"[DEBUG] OCR processing page {i}/{len(images)}...")
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
            print("[WARNING] No text extracted via python-docx. Trying docx2txt...")
            text_content = docx2txt_process(file)
            if not text_content.strip():
                raise ValueError("No text extracted via docx2txt either.")
    except Exception as e:
        print(f"[ERROR] DOCX extraction failed: {e}")
        print("[INFO] Falling back to OCR for DOCX...")
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

    # Provide explicit instructions about how to treat location suffixes.
    synonyms_instructions = (
        "Important Synonyms / Equivalences:\n"
        "1. 华盛顿大学西雅图分校 = 华盛顿大学 (University of Washington, Seattle)\n"
        "2. 加利福尼亚大学欧文分校 = 加利福尼亚大学欧文 (University of California, Irvine)\n"
        "3. 加利福尼亚大学洛杉矶分校 = 加利福尼亚大学洛杉矶 (University of California, Los Angeles)\n"
        "4. 密歇根大学安娜堡分校 = 密歇根大学 (University of Michigan, Ann Arbor)\n"
        "\n"
        "If a resume school is one of these '分校' forms, treat it the same as the main name.\n"
        "If the strings are literally the same ignoring punctuation, or they match these known variations, return 'Match'.\n"
        "Otherwise check synonyms, alt names, partial matches. If none match, return 'Not Match'.\n"
    )
    
    prompt = (
        "You are a professional school name matcher. Compare each school name from the resume against the target school list.\n"
        "Task:\n"
        "1. If the resume's school name is literally the same (ignoring spaces/punctuation) as a target list entry, return 'Match'.\n"
        "2. If the resume's school name is in the synonyms table below, treat it as the same as the main name.\n"
        "3. Otherwise, check synonyms, alternative names, or partial matches.\n"
        "4. If no match, return 'Not Match'.\n\n"
        # Insert the synonyms instructions here:
        f"{synonyms_instructions}\n"
        "Resume Schools:\n"
        f"- Phd school: {phd_school}\n"
        f"- Master school: {master_school}\n"
        f"- Bachelor school: {bachelor_school}\n\n"
        "Target school list:\n"
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
    - If awards from both lists are matched with confidence, return "高潜".
    - If only list 1 awards are matched, return "竞赛人才".
    - If only list 2 awards are matched, return "顶会人才".
    - Otherwise, return "".
    """
    print("[DEBUG] Determining final award status from matched awards...")
    list1_found = any(match.get("confidence") in ["High", "Medium"] and match.get("list") == 1 
                      for match in matched_awards)
    list2_found = any(match.get("confidence") in ["High", "Medium"] and match.get("list") == 2
                      for match in matched_awards)

    if list1_found and list2_found:
        print("[DEBUG] Both list1 and list2 awards matched. Returning '高潜'.")
        return "高潜"
    elif list1_found:
        print("[DEBUG] Only list1 awards matched. Returning '竞赛人才'.")
        return "竞赛人才"
    elif list2_found:
        print("[DEBUG] Only list2 awards matched. Returning '顶会人才'.")
        return "顶会人才"
    else:
        print("[DEBUG] No awards matched. Returning empty string.")
        return ""
    
def check_local_award_matches(resume_awards, award_list, award_list2, fuzzy_threshold=0.9):
    """
    1. For each award in resume_awards, try exact or fuzzy match against award_list (list1) and award_list2 (list2).
    2. Return:
       - matched_awards: list of dicts with:
         {
           "resume_award": ...,
           "matched_award": ...,
           "list": "1", "2", "Both", or "No Awards",
           "confidence": "High" | "Medium" | "Low"
         }
       - not_matched_awards: list of award strings still 'No Awards' after local matching.
    """
    from difflib import SequenceMatcher

    def best_local_match(award, reference_list):
        """Return (best_match_str, best_ratio) from a reference_list for a single award."""
        best_ratio = 0.0
        best_match_str = None
        for ref in reference_list:
            ratio = SequenceMatcher(None, award.lower().strip(), ref.lower().strip()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_str = ref
        return best_match_str, best_ratio

    matched_awards = []
    not_matched_awards = []

    for aw in resume_awards:
        aw_clean = aw.strip()
        if not aw_clean:
            continue

        # 1) Compare against award_list (list1)
        list1_best, list1_ratio = best_local_match(aw_clean, award_list)

        # 2) Compare against award_list2 (list2)
        list2_best, list2_ratio = best_local_match(aw_clean, award_list2)

        # Decide which list this award belongs to locally
        matched_list = "No Awards"
        matched_ref = ""
        max_ratio = 0.0

        if list1_ratio >= fuzzy_threshold and list2_ratio >= fuzzy_threshold:
            matched_list = "Both"
            matched_ref = f"{list1_best} & {list2_best}"
            max_ratio = max(list1_ratio, list2_ratio)
        elif list1_ratio >= fuzzy_threshold:
            matched_list = "1"
            matched_ref = list1_best
            max_ratio = list1_ratio
        elif list2_ratio >= fuzzy_threshold:
            matched_list = "2"
            matched_ref = list2_best
            max_ratio = list2_ratio
        else:
            # neither matched above threshold
            matched_list = "No Awards"
            matched_ref = "None"
            max_ratio = max(list1_ratio, list2_ratio)

        # Confidence logic
        if max_ratio >= 0.98:
            confidence = "High"
        elif max_ratio >= fuzzy_threshold:
            confidence = "Medium"
        else:
            confidence = "Low"

        if matched_list == "No Awards":
            not_matched_awards.append(aw_clean)

        matched_awards.append({
            "resume_award": aw_clean,
            "matched_award": matched_ref,
            "list": matched_list,
            "confidence": confidence
        })

    return matched_awards, not_matched_awards

def match_awards_with_openai_partially(not_matched_awards, award_list, award_list2):
    """
    Call OpenAI to semantically match awards from 'not_matched_awards' against
    award_list (list1) and award_list2 (list2). Return a list of dicts:
      [
         {
           "resume_award": <str>,
           "matched_award": <str or 'None'>,
           "list": "1", "2", "Both", or "No Awards",
           "confidence": "High" or "Medium" or "Low"
         }
      ]
    Then you can merge it back with the local matched results.
    """
    import os
    import json
    import re
    from difflib import SequenceMatcher
    from openai import OpenAI

    if not not_matched_awards:
        return []  # no partial matching needed

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Convert both lists to strings
    list1_str = "\n".join(award_list)
    list2_str = "\n".join(award_list2)
    not_matched_str = "\n".join(not_matched_awards)

    # We’ll build a prompt akin to your main 'match_awards_with_openai()',
    # but only for the not_matched awards:
    prompt = (
        "You are an award classification assistant. Compare each 'unmatched' award below against two reference lists:\n"
        "List1 (竞赛人才) and List2 (顶会人才).\n\n"
        "- If an unmatched award is semantically or literally close to anything in List1 => 'list': 1\n"
        "- If it's closer or equal to something in List2 => 'list': 2\n"
        "- If it matches awards in both with high confidence => 'list': 'Both'\n"
        "- Otherwise => 'list': 'No Awards'\n\n"
        "We only have these unmatched awards:\n"
        f"{not_matched_str}\n\n"
        "List1 (竞赛人才):\n"
        f"{list1_str}\n\n"
        "List2 (顶会人才):\n"
        f"{list2_str}\n\n"
        "Return valid JSON with an array of results. Each element has:\n"
        "resume_award, matched_award, list, confidence\n"
        "(e.g. \"High\"/\"Medium\"/\"Low\" depending on how sure you are).\n"
    )

    try:
        print("[INFO] Sending partial prompt for award matching to OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_response = completion.choices[0].message.content

        print("[DEBUG] Raw partial OpenAI award matching response:")
        print(raw_response)

        cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
        cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

        matched_awards = json.loads(cleaned_content)

        # Just ensure it's a list of dicts with the needed keys
        final_results = []
        for item in matched_awards:
            # Minimal safety check
            resume_award = item.get("resume_award", "")
            matched_award = item.get("matched_award", "None")
            matched_list = item.get("list", "No Awards")
            confidence = item.get("confidence", "Low")
            final_results.append({
                "resume_award": resume_award,
                "matched_award": matched_award,
                "list": matched_list,
                "confidence": confidence
            })

        return final_results

    except Exception as e:
        print(f"[ERROR] Partial OpenAI matching failed: {e}")
        # If there's an error, just mark them as "No Awards"
        fallback = []
        for na in not_matched_awards:
            fallback.append({
                "resume_award": na,
                "matched_award": "None",
                "list": "No Awards",
                "confidence": "Low"
            })
        return fallback


def match_schools_with_openai_partially(parsed_info, target_school_list, not_matched_degrees):
    """
    Call OpenAI only for degrees in `not_matched_degrees`.
    Keep existing 'Match' statuses as is, do not override them.
    """
    print("\n[INFO] Starting partial semantic school matching via OpenAI...")

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    target_schools_str = "\n".join(target_school_list)

    prompt_lines = []
    if 'phd' in not_matched_degrees:
        prompt_lines.append(f"- PhD: {parsed_info.get('phd_school', 'NA')}")
    if 'master' in not_matched_degrees:
        prompt_lines.append(f"- Master's: {parsed_info.get('master_school', 'NA')}")
    if 'bachelor' in not_matched_degrees:
        prompt_lines.append(f"- Bachelor's: {parsed_info.get('bachelor_school', 'NA')}")

    prompt_schools = "\n".join(prompt_lines)

    synonyms_instructions = (
        "Important Synonyms / Equivalences:\n\n"
        "General Rule:\n"
        "    If the resume's school name contains the format '[UniversityName]大学[Location]分校', "
        "    treat it as referring to the same main institution as '[UniversityName]大学[Location]' or '[UniversityName]大学'.\n"
        "    This means the location suffixes like '分校' do not affect whether it matches the target list.\n\n"
        "Examples:\n"
        "    1. 华盛顿大学西雅图分校 = 华盛顿大学 (University of Washington, Seattle)\n"
        "    2. 加利福尼亚大学欧文分校 = 加利福尼亚大学欧文 (University of California, Irvine)\n"
        "    3. 加利福尼亚大学洛杉矶分校 = 加利福尼亚大学洛杉矶 (University of California, Los Angeles)\n"
        "    4. 密歇根大学安娜堡分校 = 密歇根大学 (University of Michigan)\n\n"
        "These are just a few examples. The same logic applies to any other campus name that ends with '分校'.\n"
        "If the strings are literally the same ignoring punctuation, or they match these known variations (via this rule), return 'Match'.\n"
        "Otherwise, check synonyms, alt names, partial matches. If none match, return 'Not Match'.\n"
    )

    prompt = (
        "You are a professional school name matcher. Compare each school name from the resume (below) "
        "against the target school list.\n\n"
        "Tasks:\n"
        "1. If the resume's school name is literally the same (ignoring spaces/punctuation) as a target list entry, return 'Match'.\n"
        "2. Apply the general rule that any 'X大学[Location]分校' is effectively the same as 'X大学' or 'X大学[Location]', "
        "   including the examples below.\n"
        "3. If it doesn't match literally or via the '分校' rule, check synonyms, alternative names, or partial matches.\n"
        "4. If no match is found, return 'Not Match'.\n\n"
        f"{synonyms_instructions}\n"  # Insert the general rule + examples above
        "Resume Schools:\n"
        f"{prompt_schools}\n\n"
        "Target school list:\n"
        f"{target_schools_str}\n\n"
        "Return the results in JSON format with these keys:\n"
        "- 'phd_match_status': 'Match' or 'Not Match'\n"
        "- 'master_match_status': 'Match' or 'Not Match'\n"
        "- 'bachelor_match_status': 'Match' or 'Not Match'\n"
    )

    try:
        print("[INFO] Sending partial prompt for school matching to OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = completion.choices[0].message.content

        print("[DEBUG] Raw partial OpenAI school matching response:")
        print(raw_response)

        cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
        cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

        match_results = json.loads(cleaned_content)

        if 'phd' in not_matched_degrees:
            parsed_info['phd_match_status'] = match_results.get('phd_match_status', 'Not Match')
        if 'master' in not_matched_degrees:
            parsed_info['master_match_status'] = match_results.get('master_match_status', 'Not Match')
        if 'bachelor' in not_matched_degrees:
            parsed_info['bachelor_match_status'] = match_results.get('bachelor_match_status', 'Not Match')

        print("[INFO] Partial school matching completed. Updated statuses:")
        if 'phd' in not_matched_degrees:
            print(f"  PhD Match: {parsed_info['phd_match_status']}")
        if 'master' in not_matched_degrees:
            print(f"  Master Match: {parsed_info['master_match_status']}")
        if 'bachelor' in not_matched_degrees:
            print(f"  Bachelor Match: {parsed_info['bachelor_match_status']}")
        return parsed_info

    except Exception as e:
        print(f"[ERROR] Partial school matching failed: {e}")
        for deg in not_matched_degrees:
            key = f"{deg}_match_status"
            parsed_info[key] = 'Not Match'
        return parsed_info

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
            print(
                f"[INFO] Resume Award: '{m.get('resume_award')}' => Matched: '{m.get('matched_award')}', "
                f"List: {m.get('list')}, Confidence: {m.get('confidence')}"
            )
        return matched_awards

    except Exception as e:
        print(f"[ERROR] Award matching failed: {e}")
        return []

def parse_content(text_content, target_school_list, award_list, award_list2, qs50_list):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    system_message = (
        "You are a professional-grade resume parser. "
        "You will be provided with text content extracted from a candidate's resume. Your job is to analyze and return a JSON object containing specific fields.\n\n"
        "Your JSON output keys:\n"
        "1. 'education_level': The highest education level (options: '本科', '硕士', '博士', or 'N/A' if unknown). Determine based on the resume.\n"
        "   - If the candidate has a PhD, return '博士'\n"
        "   - If the candidate has a Master's as the highest degree, return '硕士'\n"
        "   - If the candidate has a Bachelor's as the highest degree, return '本科'\n"
        "   - If unsure, return 'N/A'\n\n"
        "2. 'name': The candidate's full name as found on the resume.\n\n"
        "3. 'major': The major (program of study) of the HIGHEST education level, in Simplified Chinese.\n\n"
        "4. 'grad_year': The graduation year of the highest education level:\n"
        "   - If a year range is given (e.g., '08/2022 – Present'), infer that the candidate is still studying and estimate graduation year based on:\n"
        "     - PhD: 4 years after the start year\n"
        "     - Master's: 2 years after the start year\n"
        "     - Bachelor's: 4 years after the start year\n"
        "   - If only one year is given without range, try to infer if it's start or grad year. If uncertain, assume it's the grad year.\n\n"
        "   - If the word 'expected' is beside the year, assume it's the grad year.\n\n"
        "5. 'phd_school', 'master_school', 'bachelor_school': The schools for each degree the candidate has, in Simplified Chinese.\n"
        "   - If the school is known internationally and a recognized Chinese name exists, use that. Example:\n"
        "     - 'Nanyang Technological University Singapore' -> '南洋理工大学'\n"
        "     - 'Zhejiang University' -> '浙江大学'\n"
        "   - If the school name is only in English and no known Chinese translation is commonly used, return the name as is but ideally in Simplified Chinese if known.\n"
        "   - If the candidate does not hold that degree level, return 'NA'.\n\n"
        "6. 'awards': A list of awards the candidate achieved, normalized if possible.\n\n"
        "7. 'candidate_location': The candidate's country location in Simplified Chinese. Determine by priority:\n"
        "   1. If a location is clearly stated at the top (e.g. resume header), use the country location.\n"
        "   2. If not found, use the highest education institution's country location.\n"
        "   3. If the most recent work experience is more recent than the graduation year, use that work experience's country location.\n"
        "   If none can be determined, return '未知'. Examples of countries in Simplified Chinese: '美国', '中国', '英国', etc.\n\n"
        "8. 'is_qs50': If the highest degree institution is in top 50 QS ranking, return 'QS50'. Otherwise '非QS50'. If unsure, assume '非QS50'.\n\n"
        "9. 'is_chinese_name': 'Yes' if the candidate's name is Chinese. Use the 百家姓 (Hundred Family Surnames) as the standard reference for identifying Chinese names. Additionally, if the name consists entirely of Chinese characters, return 'Yes' without further checks. 'No' otherwise.\n\n"
        "10. The logic for determining the final file name outside of this function is based on these values, so ensure accuracy.\n\n"
        "IMPORTANT: For the 'awards' key, please return them **in English** only, even if the resume is partially or fully in Chinese.\n"
        "If you can only find Chinese award names, provide the commonly known English name or a recognized short name in English.\n"
        "Additional Notes:\n"
        "- Do not return 'NA' for a school if it is mentioned. Only return 'NA' if that degree level does not exist.\n"
        "- Awards: just list them. The classification (竞赛人才, 顶会人才, 高潜) will be handled after the award matching step.\n"
        "- Make sure the output is strictly valid JSON without extra commentary.\n"
    )

    print("[DEBUG] Sending resume text to OpenAI for structured parsing...")

    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": text_content},
        ],
        temperature=0,
    )

    raw_response = completion.choices[0].message.content
    print("[DEBUG] Raw OpenAI resume parsing response:")
    print(raw_response)

    cleaned_content = re.sub(r"```json|```", "", raw_response).strip()
    cleaned_content = re.sub(r",\s*([\}\]])", r"\1", cleaned_content)

    try:
        parsed_info = json.loads(cleaned_content)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decoding failed: {e}")
        raise ValueError("Error parsing OpenAI response")

    # Local check for schools (exact/fuzzy)
    not_matched_degrees, parsed_info = check_local_school_matches(
        parsed_info, target_school_list, fuzzy_threshold=0.9
    )

    if not_matched_degrees:
        parsed_info = match_schools_with_openai_partially(parsed_info, target_school_list, not_matched_degrees)

    # Match awards & determine final award status
    parsed_awards = parsed_info.get("awards", [])
    if not parsed_awards:
        # If there's no award in resume, just set status = "No Awards"
        print("[DEBUG] No awards found in the parsed resume. Skipping award matching.")
        parsed_info["award_status"] = "No Awards"
    else:
        # First do local matching
        local_matched_awards, not_matched_awards = check_local_award_matches(
            parsed_awards, award_list, award_list2, fuzzy_threshold=0.9
        )

        # If some are still "No Awards" after local approach, partial GPT match them
        if not_matched_awards:
            partial_matches = match_awards_with_openai_partially(
                not_matched_awards, award_list, award_list2
            )
            # Merge partial_matches with local_matched_awards
            # Key concept: same "resume_award" can appear in partial if it was "No Awards" locally
            # We'll unify them by resume_award
            partial_dict = {pm["resume_award"]: pm for pm in partial_matches}

            final_matched = []
            for item in local_matched_awards:
                if item["list"] == "No Awards":
                    # Overwrite from partial if found
                    pm = partial_dict.get(item["resume_award"])
                    if pm:
                        final_matched.append(pm)
                    else:
                        # Should not happen, but safe fallback
                        final_matched.append(item)
                else:
                    # If local was matched, keep local
                    final_matched.append(item)
        else:
            final_matched = local_matched_awards

        # Now figure out the final award_status
        has_list1 = any(m["list"] in ["1", "Both"] for m in final_matched)
        has_list2 = any(m["list"] in ["2", "Both"] for m in final_matched)

        if has_list1 and has_list2:
            parsed_info["award_status"] = "高潜"
        elif has_list1:
            parsed_info["award_status"] = "竞赛人才"
        elif has_list2:
            parsed_info["award_status"] = "顶会人才"
        else:
            parsed_info["award_status"] = "No Awards"                          
    
    parsed_info["is_qs50"] = determine_qs50(parsed_info, qs50_list)

    print("[DEBUG] Completed parse_content flow. Returning parsed_info.")
    return parsed_info

def determine_qs50(parsed_info, qs50_list, fuzzy_threshold=0.9):
    """
    Override 'is_qs50' by checking if the highest education institution
    is in your local qs50_list. Return 'QS50' or '非QS50'.
    Use fuzzy matching if exact match fails.
    """

    education_level = parsed_info.get("education_level", "N/A")
    if education_level == "博士":
        highest_school = parsed_info.get("phd_school", "")
    elif education_level == "硕士":
        highest_school = parsed_info.get("master_school", "")
    elif education_level == "本科":
        highest_school = parsed_info.get("bachelor_school", "")
    else:
        highest_school = ""

    highest_school = highest_school.strip()
    if not highest_school or highest_school == "NA":
        return "非QS50"

    # 1) Check for exact match
    if highest_school in qs50_list:
        return "QS50"

    # 2) Check for fuzzy match
    for qs_school in qs50_list:
        ratio = SequenceMatcher(None, highest_school, qs_school).ratio()
        if ratio >= fuzzy_threshold:
            return "QS50"

    return "非QS50"

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
    """
    print("[DEBUG] Generating the final filename based on parsed_info...")

    name = sanitize_filename_component(parsed_info.get("name", "Unknown Name"))
    major = sanitize_filename_component(parsed_info.get("major", "Unknown Major"))
    grad_year = sanitize_filename_component(parsed_info.get("grad_year", "Unknown Year"))
    education_level_ch = parsed_info.get("education_level", "N/A").strip()

    phd_school = parsed_info.get("phd_school", "NA")
    master_school = parsed_info.get("master_school", "NA")
    bachelor_school = parsed_info.get("bachelor_school", "NA")

    # Determine highest education level
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
        final_match_status = ("Match"
                              if (master_match_status == "Match"
                                  and bachelor_match_status == "Match") else "Not Match")
    elif level == "Bachelor's":
        final_match_status = "Match" if bachelor_match_status == "Match" else "Not Match"
    else:
        final_match_status = "Not Match"

    # Determine job type
    job_type = "全职"
    if grad_year.isdigit():
        if int(grad_year) > 2025:
            job_type = "实习"

    award_status = parsed_info.get("award_status", "")
    candidate_location = sanitize_filename_component(parsed_info.get("candidate_location", ""))
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
    print(f"[DEBUG] Final filename: '{filename}'")
    return filename
