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

def update_summary(parsed_info):
    # Determine award status
    award_status = parsed_info.get("award_status", "")
    if award_status == "竞赛人才":
        summary["竞赛人才"] += 1
    elif award_status == "顶会人才":
        summary["顶会人才"] += 1
    elif award_status == "天才":
        summary["天才"] += 1

    # Determine match status based on highest education level
    education_level = parsed_info.get("education_level", "Bachelor's").strip()
    phd_match_status = parsed_info.get("phd_match_status", "Not Match")
    master_match_status = parsed_info.get("master_match_status", "Not Match")
    bachelor_match_status = parsed_info.get("bachelor_match_status", "Not Match")

    if education_level == "PhD":
        final_match_status = "Match" if phd_match_status == "Match" else "Not Match"
    elif education_level == "Master's":
        final_match_status = "Match" if (master_match_status == "Match" and bachelor_match_status == "Match") else "Not Match"
    else:
        final_match_status = "Match" if bachelor_match_status == "Match" else "Not Match"

    summary[final_match_status] += 1

    # Education level counts
    if education_level == "PhD":
        summary["PhD"] += 1
    elif education_level == "Master's":
        summary["Master's"] += 1
    else:
        summary["Bachelor's"] += 1

    # Job type based on grad_year
    grad_year = parsed_info.get("grad_year", "")
    grad_year_str = str(grad_year)  # Ensure it's a string now
    job_type = "Intern" if (grad_year_str.isdigit() and int(grad_year_str) > 2024) else "FullTime"
    summary[job_type] += 1

    # Chinese vs Non-Chinese name based on model response
    if parsed_info.get("is_chinese_name", "No") == "Yes":
        summary["ChineseName"] += 1
    else:
        summary["NonChineseName"] += 1

    # QS50
    if parsed_info.get("is_qs50", "") == "QS50":
        summary["QS50"] += 1

def process_file(file, args, file_num, total_files):
    print(f'-------------------------------------------------------------------------------------\nProcessing file: {file}...')

    # Extract text from file
    try:
        text_content = extract_text_from_file(file)
        if not text_content.strip():  # Check if text content is empty or just whitespace
            return handle_file_error(file, args, "No text extracted from the resume.", file_num, total_files)
    except Exception as e:
        return handle_file_error(file, args, f"Error extracting text: {e}", file_num, total_files)

    print('Waiting for response from AlexAI...')

    # If target_list is provided, read the file, otherwise use an empty list
    target_school_list = []
    if args.target_list:
        try:
            with open(args.target_list, 'r', encoding='utf-8') as f:
                target_school_list = [x.strip() for x in f.readlines()]
        except Exception as e:
            return handle_file_error(file, args, f"Error reading target school list: {e}", file_num, total_files)
    
    # Load award list
    award_list = []
    if args.award_list:
        try:
            with open(args.award_list, 'r', encoding='utf-8') as f:
                award_list = [x.strip() for x in f.readlines()]
        except Exception as e:
            return handle_file_error(file, args, f"Error reading award list: {e}", file_num, total_files)
        
    # Load award list 2
    award_list2 = []
    if args.award_list2:
        try:
            with open(args.award_list2, 'r', encoding='utf-8') as f:
                award_list2 = [x.strip() for x in f.readlines()]
        except Exception as e:
            return handle_file_error(file, args, f"Error reading award list2: {e}", file_num, total_files)
        
    try:
        # Parse content
        parsed_info = parse_content(text_content, target_school_list, award_list, award_list2)
        if not parsed_info:  # Check if parsed_info is empty or null
            return handle_file_error(file, args, "Parsed content is empty. The resume might lack required information.", file_num, total_files)
    except Exception as e:
        return handle_file_error(file, args, f"Error with AlexAI response: {e}", file_num, total_files)

    # Get the original file extension
    file_extension = os.path.splitext(file)[1]

    # Generate the new filename
    try:
        filename = f"{generate_filename(parsed_info, args)}{file_extension}"
        print(f"\nNew filename: {filename}")
        
        # Ensure the output directory exists
        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)

        # Copy the file to the output directory with the new name
        shutil.copyfile(file, os.path.join(args.output_dir, filename))
        
        # Update summary with current file's parsed info
        update_summary(parsed_info)

        return True, f"Done {file_num}/{total_files} with no problems ✅"
    except Exception as e:
        return handle_file_error(file, args, f"Error renaming file: {e}", file_num, total_files)

def print_summary():
    summary_text = (
        "\n[SUMMARY]\n"
        f"Total 竞赛人才: {summary['竞赛人才']}\n"
        f"Total 顶会人才: {summary['顶会人才']}\n"
        f"Total 天才: {summary['天才']}\n"
        f"Total Matched: {summary['Match']}\n"
        f"Total Not Matched: {summary['Not Match']}\n"
        f"Total PhD: {summary['PhD']}\n"
        f"Total Master's: {summary['Master\'s']}\n"
        f"Total Bachelor's: {summary['Bachelor\'s']}\n"
        f"Total Intern (实习): {summary['Intern']}\n"
        f"Total Full-time (全职): {summary['FullTime']}\n"
        f"Total Chinese Name: {summary['ChineseName']}\n"
        f"Total Non-Chinese Name: {summary['NonChineseName']}\n"
        f"Total QS50: {summary['QS50']}\n"
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
