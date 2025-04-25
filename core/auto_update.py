import subprocess
import os
import time

def should_update_local(local_commit, remote_commit):
    return local_commit != remote_commit

def run_auto_update(neuron_type):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    current_branch = subprocess.getoutput("git rev-parse --abbrev-ref HEAD")
    local_commit = subprocess.getoutput("git rev-parse HEAD")
    os.system("git fetch")
    remote_commit = subprocess.getoutput(f"git rev-parse origin/{current_branch}")

    if should_update_local(local_commit, remote_commit):
        print("Local repo is not up-to-date. Updating...")
        reset_cmd = "git reset --hard " + remote_commit
        process = subprocess.Popen(reset_cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()

        if error:
            print("Error in updating:", error)
        else:
            print("Updated local repo to latest version: {}", format(remote_commit))
            
            print("Running the autoupdate steps...")
            # Run setup script with venv activation
            project_root = os.path.abspath(os.path.join(script_dir, ".."))
            venv_path = f"{project_root}/venv_bitcast"
            setup_cmd = f"source {venv_path}/bin/activate && {project_root}/scripts/setup_env.sh"
            subprocess.run(setup_cmd, shell=True, executable='/bin/bash')
            
            time.sleep(20)
            print("Finished running the autoupdate steps")
            print("Restarting neuron")
            # Run start script with venv activation
            start_cmd = f"source {venv_path}/bin/activate && {project_root}/scripts/start_{neuron_type}.sh"
            subprocess.run(start_cmd, shell=True, executable='/bin/bash')
    else:
        print("Repo is up-to-date.")