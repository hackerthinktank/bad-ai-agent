# Vulnerable Ollama Proxy - AI Red Teaming Educational Tool

**⚠️ EXTREMELY IMPORTANT WARNING ⚠️**

**DO NOT USE THIS SCRIPT IN ANY PRODUCTION OR LIVE ENVIRONMENT. IT IS INTENTIONALLY DESIGNED WITH SEVERE SECURITY VULNERABILITIES FOR EDUCATIONAL PURPOSES ONLY. DEPLOYING THIS CODE EXPOSES THE HOST SYSTEM TO REMOTE CODE EXECUTION (RCE).**

## Overview

This Python script implements a simple Flask web server that acts as a proxy between a user and a destination Ollama (or compatible LLM) API endpoint. Its primary function is to:

1.  Receive a JSON request (typically containing a `model` and `prompt`) on its `/api/generate` endpoint.
2.  Forward this request to a configured `DESTINATION_OLLAMA_ENDPOINT`.
3.  Receive the JSON response from the destination endpoint.
4.  **Crucially and Dangerously:** Inspect the `response` field within the received JSON. If this field contains a string that includes a JSON object like `{"command_os": "some_command"}`, the script will attempt to **execute `some_command` as an operating system command** on the server where the proxy is running.
5.  Append the standard output (stdout) of the executed command (if any) to the original `response` text.
6.  Return the potentially modified JSON response to the original caller.

## Purpose: AI Red Teaming Education

This tool is specifically crafted to teach and demonstrate **AI Red Teaming** concepts, particularly focusing on **Indirect Prompt Injection** leading to **Remote Code Execution (RCE)** through manipulating Large Language Model (LLM) outputs.

Students or security researchers can interact with this proxy, sending prompts designed to trick the backing LLM (at `DESTINATION_OLLAMA_ENDPOINT`) into generating a response containing the malicious `{"command_os": "..."}` payload. If successful, the proxy will execute the specified command, demonstrating a critical vulnerability chain.

## How it Works

1.  **Listens:** The Flask app listens on `0.0.0.0:5001` (by default) for POST requests to `/api/generate`.
2.  **Validates Input:** Checks if the request is JSON and contains `model` and `prompt` keys.
3.  **Forwards Request:** Creates a separate thread to send the received JSON payload to the `DESTINATION_OLLAMA_ENDPOINT` via a POST request.
4.  **Receives Response:** Waits for the response from the destination endpoint.
5.  **Parses and Inspects:**
    * Retrieves the value of the `response` key from the destination's JSON response.
    * Uses `extract_braced_content` to find the first `{...}` block within the response string.
    * Uses `execute_command_os_from_string` to:
        * Parse the extracted block as JSON.
        * Check if a `command_os` key exists.
        * **If the key exists, execute its string value using `subprocess.run(command, shell=True, ...)`**. This is the core vulnerability.
        * Capture the `stdout` and `stderr` of the executed command.
6.  **Modifies Response:** If a command was executed successfully, its `stdout` is appended to the original `response` string from the LLM.
7.  **Returns Result:** Sends the final JSON (original or modified) and the status code received from the destination back to the initial client.

## Configuration

Before running, you **MUST** edit the script and set the `DESTINATION_OLLAMA_ENDPOINT` variable:

```python
# !!! IMPORTANT: Replace this with the actual URL of your destination Ollama service !!!
DESTINATION_OLLAMA_ENDPOINT = "http://localhost:11434/api/generate" # Example: Replace with your real endpoint
```

Replace `"http://localhost:11434/api/generate"` with the correct URL for the LLM API you want this proxy to forward requests to.

## Running the Script

1.  **Prerequisites:** Ensure you have Python 3 and the required libraries installed:
    ```bash
    pip install Flask requests
    ```
2.  **Configure:** Edit the script to set the correct `DESTINATION_OLLAMA_ENDPOINT`.
3.  **Run:** Execute the script from your terminal:
    ```bash
    python your_script_name.py
    ```
    (Replace `your_script_name.py` with the actual filename).
4.  **Access:** The proxy will be available at `http://<your-server-ip>:5001/api/generate`.

## Security Vulnerabilities - **INTENTIONAL**

* **Remote Code Execution (RCE):** This is the primary, intentional vulnerability. The `execute_command_os_from_string` function directly takes a string potentially derived from an external LLM's output and executes it as a shell command via `subprocess.run(..., shell=True)`.
    * **`shell=True`:** This is particularly dangerous as it allows shell metacharacters (`;`, `|`, `&&`, `$()`, ``` ` ```, etc.) to be interpreted, making complex command injection easier.
    * **Untrusted Input:** The command originates from the output of the LLM at the `DESTINATION_OLLAMA_ENDPOINT`. An attacker can craft prompts sent *through* this proxy, aiming to make the LLM generate a response containing `{"command_os": "malicious_command"}`. The proxy will blindly execute `malicious_command`.
* **Lack of Input Sanitization:** No significant attempt is made to sanitize the command string before execution.
* **Error Handling Exposure:** While errors are caught, detailed error messages might be returned, potentially revealing information about the server environment or the script's internal state.
* **Denial of Service (DoS):** An attacker could potentially provide commands that consume excessive resources (e.g., `cat /dev/urandom`) or trigger infinite loops if the shell environment allows.

## Disclaimer

This script is provided **AS IS**, purely for educational demonstration of AI security vulnerabilities. The authors and distributors **accept no liability** for any damage caused by the use or misuse of this code. **By running this script, you acknowledge the extreme risks involved and agree that you are solely responsible for any consequences.**

**NEVER deploy this in a production, shared, or untrusted environment.** Use it only in isolated, controlled lab settings specifically designed for security testing and education.

