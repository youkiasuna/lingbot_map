from huggingface_hub import list_repo_files, hf_hub_download
import sys
import os

repo_id = "robbyant/lingbot-map"
print(f"Listing files in {repo_id}...", flush=True)
try:
    files = list_repo_files(repo_id)
except Exception as e:
    print("ERROR listing repo files:", e)
    sys.exit(1)

# candidate extensions in preferred order
ext_order = ['.pt', '.safetensors', '.pth', '.ckpt', '.bin', '.tar']
candidates = [f for f in files if any(f.endswith(ext) for ext in ext_order)]
if not candidates:
    print("No checkpoint-like files found. Repo files:")
    for f in files:
        print(f)
    sys.exit(1)

# sort candidates by preferred extension order and then name
def score(name):
    for i, ext in enumerate(ext_order):
        if name.endswith(ext):
            return i
    return len(ext_order)

candidates.sort(key=lambda x: (score(x), x))
chosen = candidates[0]
print(f"Chosen file to download: {chosen}", flush=True)

try:
    path = hf_hub_download(repo_id=repo_id, filename=chosen)
    print(f"Downloaded to: {os.path.abspath(path)}")
except Exception as e:
    print("ERROR downloading file:", e)
    sys.exit(1)
