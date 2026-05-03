import fnmatch
import os
import re


def extract_description(line):
    """
    Extracts the comment from a line, but only if the # is not inside quotes.
    Returns the description (without the #) or '' if not found.
    """
    # Regex to match: key=value # comment (but # not inside quotes)
    pattern = r'^(.*?)=(.*?)(?<!["\'])#(.*)$'
    match = re.match(pattern, line)
    if match:
        value = match.group(2)
        # Count quotes before # to ensure it's not inside quotes
        before_hash = value
        if before_hash.count('"') % 2 == 0 and before_hash.count("'") % 2 == 0:
            return match.group(3).strip()
    return ""


def create_template_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if fnmatch.fnmatch(file, "*.env") and not fnmatch.fnmatch(
                file, "*.env.template"
            ):
                with open(os.path.join(root, file), "r") as env_file:
                    lines = env_file.readlines()
                    with open(
                        os.path.join(root, f"{file}.template"), "w"
                    ) as template_file:
                        in_metadata_block = False
                        for line in lines:
                            stripped_line = line.strip()

                            if stripped_line in {
                                "# METADATA --- START",
                                "# METADATA. DO NOT CHANGE UNTIL THE END BLOCK",
                            }:
                                in_metadata_block = True
                                template_file.write(line)
                                continue

                            if in_metadata_block:
                                template_file.write(line)
                                if stripped_line in {
                                    "# METADATA --- END",
                                    "# DO NOT CHANGE ENDS HERE",
                                }:
                                    in_metadata_block = False
                                continue

                            # Skip empty lines and pure comments
                            if stripped_line == "" or stripped_line.startswith("#"):
                                template_file.write(line)
                                continue
                            if "=" in line:
                                key, rest = line.split("=", 1)
                                description = extract_description(line)
                                # Remove value and comment from rest
                                new_line = f"{key.strip()}="
                                if description:
                                    new_line += f" # {description}"
                                template_file.write(new_line + "\n")
                            else:
                                template_file.write(line)


def main() -> None:
    """Generate .env.template files for the current working directory.

    Intended for standalone script invocation during repository maintenance.
    When called from server/main.py, create_template_files() is invoked directly
    with the workspace root path instead.
    """
    create_template_files(os.path.join("."))


if __name__ == "__main__":
    main()
