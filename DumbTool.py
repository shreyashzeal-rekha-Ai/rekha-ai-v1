import os

PROJECT_PATH = r"C:\Users\sonyc\OneDrive\Desktop\Rekha-ai1_CCTV"
OUTPUT_FILE = r"C:\Users\sonyc\OneDrive\Desktop\project_dump.txt"

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "models",
    "clips",
    "logs",
    "training_data",
    ".idea",
    ".vscode"
}

INCLUDE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".env"
}

MAX_FILE_SIZE_MB = 10

print("=" * 80)
print("PROJECT DUMP TOOL")
print("=" * 80)

if not os.path.exists(PROJECT_PATH):
    print("ERROR: Project path not found!")
    print(PROJECT_PATH)
    input("Press Enter...")
    raise SystemExit

print("Scanning:", PROJECT_PATH)

total_files = 0
dumped_files = 0

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:

    out.write("=" * 100 + "\n")
    out.write("PROJECT STRUCTURE\n")
    out.write("=" * 100 + "\n\n")

    for root, dirs, files in os.walk(PROJECT_PATH):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        level = root.replace(PROJECT_PATH, "").count(os.sep)
        indent = "    " * level

        out.write(f"{indent}{os.path.basename(root)}/\n")

        for file in sorted(files):
            out.write(f"{indent}    {file}\n")

    out.write("\n\n")
    out.write("=" * 100 + "\n")
    out.write("FILE CONTENTS\n")
    out.write("=" * 100 + "\n\n")

    for root, dirs, files in os.walk(PROJECT_PATH):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in sorted(files):

            ext = os.path.splitext(file)[1].lower()

            if ext not in INCLUDE_EXTENSIONS and file != ".env":
                continue

            total_files += 1

            path = os.path.join(root, file)

            try:
                size_mb = os.path.getsize(path) / (1024 * 1024)

                if size_mb > MAX_FILE_SIZE_MB:
                    out.write("\n" + "=" * 100 + "\n")
                    out.write(f"FILE: {path}\n")
                    out.write(f"SKIPPED: Too large ({size_mb:.2f} MB)\n")
                    out.write("=" * 100 + "\n\n")
                    continue

                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                out.write("\n" + "=" * 100 + "\n")
                out.write(f"FILE: {path}\n")
                out.write("=" * 100 + "\n\n")
                out.write(content)
                out.write("\n\n")

                dumped_files += 1

            except Exception as e:
                out.write("\n" + "=" * 100 + "\n")
                out.write(f"FILE: {path}\n")
                out.write(f"ERROR: {e}\n")
                out.write("=" * 100 + "\n\n")

print()
print("=" * 80)
print("DONE")
print("=" * 80)
print("Files scanned :", total_files)
print("Files dumped  :", dumped_files)
print("Output file   :", OUTPUT_FILE)
print("=" * 80)