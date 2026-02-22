import datetime
import os

# 1. Record the current timestamp
timestamp = datetime.datetime.now().isoformat()

# 2. Print to terminal
print(f"Timestamp recorded: {timestamp}")

# 3. Persist to storage (append to file so history is kept)
storage_file = "timestamps.txt"

with open(storage_file, "a") as f:
    f.write(timestamp + "\n")

print(f"Saved to: {os.path.abspath(storage_file)}")
