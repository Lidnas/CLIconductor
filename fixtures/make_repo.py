import os, subprocess
repo = os.path.join(os.path.dirname(__file__), "repo1")
os.makedirs(repo, exist_ok=True)
# clean
for f in os.listdir(repo):
    p = os.path.join(repo, f)
    if os.path.isfile(p):
        os.remove(p)
# remove .git
import shutil
gitdir = os.path.join(repo, ".git")
if os.path.exists(gitdir):
    shutil.rmtree(gitdir)
subprocess.run(["git", "init"], cwd=repo, check=True)
with open(os.path.join(repo, "calc.py"), "w") as f:
    f.write("def add(a,b):\n    return a - b\n")
with open(os.path.join(repo, "test_calc.py"), "w") as f:
    f.write("from calc import add\n\ndef test_add():\n    assert add(2,3)==5\n")
subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
print("done")