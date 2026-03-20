# manual_npm_bg_test.py
import json
import sys
import time
from src.helius_agent.tools.shell import (
    run_command,
    get_command_status,
    get_command_output,
)

sys.path.insert(0, str("C:/Users/sstha/Desktop/ai_/lang/helius-code/" / "src"))

# start npm init in background
resp = run_command.invoke({"cmd": ["npm", "init", "-y"], "background": True})
print("init resp:", resp)
job_id = json.loads(resp)["job_id"]

# poll status
while True:
    st = json.loads(get_command_status.invoke({"job_id": job_id}))
    print("init status:", st)
    if st.get("status") == "finished":
        break
    time.sleep(1)

print("init output:", get_command_output.invoke({"job_id": job_id}))

# start npm install react
resp = run_command.invoke({"cmd": ["npm", "install", "react"], "background": True})
print("install resp:", resp)
job_id = json.loads(resp)["job_id"]

# poll status
while True:
    st = json.loads(get_command_status.invoke({"job_id": job_id}))
    print("install status:", st)
    if st.get("status") == "finished":
        break
    time.sleep(2)

print("install output:", get_command_output.invoke({"job_id": job_id}))
