from options import parse_args
from utils import extract_text_from_file, parse_content, generate_filename
import os
import shutil

def handle_file_error(file, args, error_message, file_num, total_files):
    error_filename = f"ERROR - {os.path.basename(file)}"
    error_filepath = os.path.join(args.output_dir, error_filename)
    shutil.copyfile(file, error_filepath)  # Ensure file is copied to the output directory
    return False, f"Error {file_num}/{total_files} encountered an issue: {error_message} ❌"

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
        # Pass the target_school_list to the parse_content function
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
        return True, f"Done {file_num}/{total_files} with no problems ✅"
    except Exception as e:
        return handle_file_error(file, args, f"Error renaming file: {e}", file_num, total_files)

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
            successfully_processed_count += 1  # Increment count for successfully processed files
        else:
            error_files_count += 1  # Increment count for error files

    # Final message after all files are processed
    print(f"\nAlex is the best ❤️\n")
    print(f"He renamed and created {successfully_processed_count} resumes for you 🥳")
    print(f"{error_files_count} resume(s) were renamed with 'ERROR' due to issues 😡\n")

if __name__ == "__main__":
    main()
