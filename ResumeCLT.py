from options import parse_args
from utils import extract_text_from_file, parse_content, generate_filename
import os
import shutil

# Summary dictionary to keep track of metrics
summary = {
    "竞赛人才": 0,
    "顶会人才": 0,
    "天才": 0,
    "Match": 0,
    "Not Match": 0,
    "PhD": 0,
    "Master's": 0,
    "Bachelor's": 0,
    "Intern": 0,     # 实习
    "FullTime": 0,   # 全职
    "ChineseName": 0,
    "NonChineseName": 0,
    "QS50": 0
}

def handle_file_error(file, args, error_message, file_num, total_files):
    error_filename = f"ERROR - {os.path.basename(file)}"
    error_filepath = os.path.join(args.output_dir, error_filename)
    shutil.copyfile(file, error_filepath)  # Ensure file is copied to the output directory
    return False, f"Error {file_num}/{total_files} encountered an issue: {error_message} ❌"

def map_education_level(chinese_level):
    """Map Chinese education level to the English labels used in the summary logic."""
    if chinese_level == "博士":
        return "PhD"
    elif chinese_level == "硕士":
        return "Master's"
    elif chinese_level == "本科":
        return "Bachelor's"
    else:
        return "N/A"

def update_summary(parsed_info):
    # Determine award status
    award_status = parsed_info.get("award_status", "")
    if award_status == "竞赛人才":
        summary["竞赛人才"] += 1
    elif award_status == "顶会人才":
        summary["顶会人才"] += 1
    elif award_status == "天才":
        summary["天才"] += 1

    # 1) Convert the Chinese education level to English labels used in summary
    education_level_ch = parsed_info.get("education_level", "N/A").strip()
    education_level_en = map_education_level(education_level_ch)

    # 2) Read the match statuses
    phd_match_status = parsed_info.get("phd_match_status", "Not Match")
    master_match_status = parsed_info.get("master_match_status", "Not Match")
    bachelor_match_status = parsed_info.get("bachelor_match_status", "Not Match")

    # 3) Decide final match status based on the mapped education level
    if education_level_en == "PhD":
        final_match_status = "Match" if phd_match_status == "Match" else "Not Match"
    elif education_level_en == "Master's":
        final_match_status = "Match" if (master_match_status == "Match" and bachelor_match_status == "Match") else "Not Match"
    else:
        # Bachelor's or N/A
        final_match_status = "Match" if bachelor_match_status == "Match" else "Not Match"

    summary[final_match_status] += 1

    # 4) Increment the education level counters (PhD, Master's, Bachelor's)
    if education_level_en == "PhD":
        summary["PhD"] += 1
    elif education_level_en == "Master's":
        summary["Master's"] += 1
    else:
        # If it's "Bachelor's" or "N/A", lump into Bachelor's
        summary["Bachelor's"] += 1

    # 5) Determine job type
    grad_year = parsed_info.get("grad_year", "")
    grad_year_str = str(grad_year)
    job_type = "Intern" if (grad_year_str.isdigit() and int(grad_year_str) > 2025) else "FullTime"
    summary[job_type] += 1

    # 6) Chinese vs Non-Chinese name
    if parsed_info.get("is_chinese_name", "No") == "Yes":
        summary["ChineseName"] += 1
    else:
        summary["NonChineseName"] += 1

    # 7) QS50
    if parsed_info.get("is_qs50", "") == "QS50":
        summary["QS50"] += 1

def process_file(file, args, file_num, total_files):
    print(f"\n-------------------------------------------------------------------------------------")
    print(f"[DEBUG] Starting to process file {file_num}/{total_files}: {file}")

    # Extract text from file
    try:
        text_content = extract_text_from_file(file)
        if not text_content.strip():
            return handle_file_error(file, args, "No text extracted from the resume.", file_num, total_files)
    except Exception as e:
        return handle_file_error(file, args, f"Error extracting text: {e}", file_num, total_files)

    print("[DEBUG] Successfully extracted text. Now sending to OpenAI for parsing...")

    # If target_list is provided, read the file
    target_school_list = []
    if args.target_list:
        try:
            with open(args.target_list, 'r', encoding='utf-8') as f:
                target_school_list = [x.strip() for x in f.readlines()]
            print(f"[DEBUG] Loaded {len(target_school_list)} target schools from {args.target_list}")
        except Exception as e:
            return handle_file_error(file, args, f"Error reading target school list: {e}", file_num, total_files)

    # Load award lists similarly...
    award_list = []
    if args.award_list:
        try:
            with open(args.award_list, 'r', encoding='utf-8') as f:
                award_list = [x.strip() for x in f.readlines()]
            print(f"[DEBUG] Loaded {len(award_list)} items from award list 1: {args.award_list}")
        except Exception as e:
            return handle_file_error(file, args, f"Error reading award list: {e}", file_num, total_files)
        
    award_list2 = []
    if args.award_list2:
        try:
            with open(args.award_list2, 'r', encoding='utf-8') as f:
                award_list2 = [x.strip() for x in f.readlines()]
            print(f"[DEBUG] Loaded {len(award_list2)} items from award list 2: {args.award_list2}")
        except Exception as e:
            return handle_file_error(file, args, f"Error reading award list2: {e}", file_num, total_files)

    # Parse content
    try:
        print("[DEBUG] Parsing resume content with local matching + partial OpenAI matching if needed...")
        parsed_info = parse_content(text_content, target_school_list, award_list, award_list2)
        if not parsed_info:
            return handle_file_error(file, args, "Parsed content is empty.", file_num, total_files)
    except Exception as e:
        return handle_file_error(file, args, f"Error with AlexAI response: {e}", file_num, total_files)

    # Show partial parse_info for debugging
    print("[DEBUG] parse_content returned these fields:")
    print(f"        Name: {parsed_info.get('name')}")
    print(f"        Education Level: {parsed_info.get('education_level')}")
    print(f"        Schools: PhD={parsed_info.get('phd_school')} | Master={parsed_info.get('master_school')} | Bachelor={parsed_info.get('bachelor_school')}")
    print(f"        Match Status: PhD={parsed_info.get('phd_match_status')}, Master={parsed_info.get('master_match_status')}, Bachelor={parsed_info.get('bachelor_match_status')}")
    print(f"        Awards: {parsed_info.get('awards')}")
    print(f"        Award Status: {parsed_info.get('award_status')}")
    print(f"        is_chinese_name: {parsed_info.get('is_chinese_name')}")

    # Generate the new filename
    file_extension = os.path.splitext(file)[1]
    try:
        filename = f"{generate_filename(parsed_info, args)}{file_extension}"
        print(f"[DEBUG] Final filename generated: {filename}")

        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)
            print(f"[DEBUG] Created output directory: {args.output_dir}")

        shutil.copyfile(file, os.path.join(args.output_dir, filename))
        
        update_summary(parsed_info)
        return True, f"Done {file_num}/{total_files} with no problems ✅"

    except Exception as e:
        return handle_file_error(file, args, f"Error renaming file: {e}", file_num, total_files)


def print_summary():
    summary_text = (
        "\n[SUMMARY]\n"
        "========================================\n"
        f" 竞赛人才: {summary['竞赛人才']}\n"
        f" 顶会人才: {summary['顶会人才']}\n"
        f" 天才: {summary['天才']}\n"
        "----------------------------------------\n"
        f" Matched: {summary['Match']}\n"
        f" Not Matched: {summary['Not Match']}\n"
        "----------------------------------------\n"
        f" PhD: {summary['PhD']}\n"
        f" Master's: {summary['Master\'s']}\n"
        f" Bachelor's: {summary['Bachelor\'s']}\n"
        "----------------------------------------\n"
        f" Intern (实习): {summary['Intern']}\n"
        f" FullTime (全职): {summary['FullTime']}\n"
        "----------------------------------------\n"
        f" Chinese Name: {summary['ChineseName']}\n"
        f" Non-Chinese Name: {summary['NonChineseName']}\n"
        "----------------------------------------\n"
        f" QS50: {summary['QS50']}\n"
        "========================================\n"
    )
    print(summary_text)
    return summary_text

def main():
    args = parse_args()

    # Check if args are valid
    if not os.path.exists(args.source_dir):
        print(f"Error: Source directory {args.source_dir} does not exist.")
        return
    if not os.path.exists(args.output_dir):
        print(f"Error: Output directory {args.output_dir} does not exist.")
        return
    if args.target_list and not os.path.exists(args.target_list):
        print(f"Error: Target list file {args.target_list} does not exist.")
        return

    # Get all files with the following extensions: PDF, DOCX, DOC
    files = [file for file in os.listdir(args.source_dir) if file.endswith((".pdf", ".docx", ".doc"))]
    total_files = len(files)
    successfully_processed_count = 0  # Files renamed and created successfully
    error_files_count = 0  # Files that encountered errors and renamed with "ERROR - name"

    # Print initial message with number of resumes
    print(f"\nHello, Amanda! I'm AlexAI. I will now process {total_files} resumes for you.")
    print()

    # Process each file
    for file_num, file in enumerate(files, 1):
        file_path = os.path.join(args.source_dir, file)
        success, result = process_file(file_path, args, file_num, total_files)
        print(result)
        
        # Increment counters based on outcome
        if success:
            successfully_processed_count += 1
        else:
            error_files_count += 1

    # Final message after all files are processed
    print(f"\nAlex is the best ❤️\n")
    print(f"He renamed and created {successfully_processed_count} resumes for you 🥳")
    print(f"{error_files_count} resume(s) were renamed with 'ERROR' due to issues 😡\n")

    # Print summary after all resumes are processed and write to text file
    summary_text = print_summary()

    # Write summary to a text file in the output directory
    summary_file_path = os.path.join(args.output_dir, "summary.txt")
    with open(summary_file_path, "w", encoding="utf-8") as summary_file:
        summary_file.write(summary_text)

if __name__ == "__main__":
    main()
