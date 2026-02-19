# Start Watcher

Start the AI Employee's File System Watcher to monitor the /Inbox folder.

## Instructions

1. **Verify** the vault exists at `AI_Employee_Vault/`

2. **Check** if a watcher process is already running:
   ```bash
   pgrep -f filesystem_watcher.py
   ```
   If already running, report the PID and exit.

3. **Start** the filesystem watcher in the background:
   ```bash
   python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault > AI_Employee_Vault/Logs/watcher.log 2>&1 &
   echo $! > AI_Employee_Vault/Logs/watcher.pid
   ```

4. **Confirm** it started by reading the log after 2 seconds.

5. **Report** to the user:
   - Watcher PID
   - Monitoring path
   - Log file location
   - How to stop it: `kill $(cat AI_Employee_Vault/Logs/watcher.pid)`

## Notes

- The watcher uses PollingObserver on WSL2/Windows (automatic detection)
- Check interval: 2 seconds for WSL2 polling
- All dropped files must be in ALLOWED_EXTENSIONS (see filesystem_watcher.py)
- Drop files into `AI_Employee_Vault/Inbox/` to trigger processing
