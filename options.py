# Options for ResumeCLT
# --source_dir: Directory where the resume files are stored
# --output_dir: Directory where the output files will be stored
# (optional)
# --target_list: File containing the list of target schools

import argparse

def parse_args():
    parser = argparse.ArgumentParser(description='Options for ResumeCLT')

    parser.add_argument('--source_dir', type=str, required=True,
                        help='Directory where the resume files are stored')
    parser.add_argument('--output_dir', type=str, required=True,
                        help='Directory where the output files will be stored')
    parser.add_argument('--target_list', type=str, required=False,
                        help='File containing the list of target schools')
    parser.add_argument('--award_list', type=str, required=False,
                        help='Path to the award titles list file.')
    parser.add_argument('--award_list2', type=str, required=False,
                        help='Path to the award titles list file.')

    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    print(args)