import sys
import os
import re
import argparse

def patch_file(cfg_path, patch_path, target, flag, delete_count, delete_to_pattern):
    if not os.path.exists(cfg_path):
        print(f"Error: Config file not found: {cfg_path}", file=sys.stderr)
        return False

    try:
        with open(patch_path, 'r') as f:
            patch_content = f.read()
    except IOError:
        print(f"Error: Patch file not readable: {patch_path}", file=sys.stderr)
        return False

    with open(cfg_path, 'r') as f:
        cfg_lines = f.readlines()

    if flag and flag in "".join(cfg_lines):
        print(f"Config already contains flag: '{flag}'. Skipping.")
        return True

    new_lines = []
    insert_idx = -1
    for i, line in enumerate(cfg_lines):
        if re.search(target, line):
            insert_idx = i
            break
        new_lines.append(line)

    if insert_idx == -1:
        print(f"Error: Target pattern '{target}' not found.", file=sys.stderr)
        return False

    new_lines.append(cfg_lines[insert_idx])
    new_lines.append(patch_content)

    del_start = insert_idx + 1
    del_end = del_start

    if delete_count > 0:
        del_end = del_start + delete_count
    elif delete_to_pattern:
        for i in range(del_start, len(cfg_lines)):
            if re.search(delete_to_pattern, cfg_lines[i]):
                del_end = i + 1
                break
        else:
            del_end = len(cfg_lines)

    lines_to_append_from = del_end if del_start < del_end else insert_idx + 1
    new_lines.extend(cfg_lines[lines_to_append_from:])

    temp_path = cfg_path + ".new"
    try:
        with open(temp_path, 'w') as f:
            f.writelines(new_lines)
    except IOError:
        print(f"Error: Failed to write to temp file {temp_path}.", file=sys.stderr)
        return False

    os.rename(cfg_path,cfg_path+".old")
    os.rename(temp_path,cfg_path)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Patch a configuration file by inserting content after a target pattern.')
    parser.add_argument('CONFIG', help='Path to the configuration file to patch (e.g., /etc/nginx/sites-available/default).')
    parser.add_argument('PATCH_FILE', help='Path to the file whose content will be inserted.')
    parser.add_argument('TARGET_PATTERN', help='Regex pattern to find the line to insert AFTER (first match only).')
    parser.add_argument('--flag', required=True, help='Unique string (e.g., lab2_patch) to check if the file is already patched.')
    parser.add_argument('--count', type=int, default=0, help='Number of lines to delete starting AFTER the target line.')
    parser.add_argument('--delete-to', help='Regex pattern to delete up to, starting AFTER the target line.')

    args = parser.parse_args()

    if args.count > 0 and args.delete_to:
        print("Error: Cannot use both --count and --delete-to simultaneously.", file=sys.stderr)
        sys.exit(1)

    if patch_file(args.CONFIG, args.PATCH_FILE, args.TARGET_PATTERN, args.flag, args.count, args.delete_to):
        sys.exit(0)
    else:
        sys.exit(1)
