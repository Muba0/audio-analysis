import os

def print_directory_structure(root_dir, indent_level=0):
    """
    Recursively prints the directory structure starting from the root directory.

    :param root_dir: The root directory path.
    :param indent_level: The current level of indentation for subdirectories/files.
    """
    try:
        items = os.listdir(root_dir)
    except PermissionError:
        print(" " * indent_level + "[Permission Denied]")
        return

    for item in items:
        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            print(" " * indent_level + f"[DIR] {item}")
            print_directory_structure(item_path, indent_level + 4)
        else:
            print(" " * indent_level + f"[FILE] {item}")

if __name__ == "__main__":
    # Replace with the path to your project directory
    project_directory = input("D:\windsurf\gemini_fastapi").strip()

    if os.path.exists(project_directory):
        print(f"Directory structure of: {project_directory}\n")
        print_directory_structure(project_directory)
    else:
        print(f"The directory '{project_directory}' does not exist.")
