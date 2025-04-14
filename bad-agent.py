import re
import threading
import requests
import time
from flask import Flask, request, jsonify
import json
import subprocess
import shlex

# --- Configuration ---
#**DO NOT USE THIS SCRIPT IN ANY PRODUCTION OR LIVE ENVIRONMENT. IT IS INTENTIONALLY DESIGNED WITH SEVERE SECURITY VULNERABILITIES FOR EDUCATIONAL PURPOSES ONLY. DEPLOYING THIS CODE EXPOSES THE HOST SYSTEM TO REMOTE CODE EXECUTION (RCE).**
# !!! IMPORTANT: Replace this with the actual URL of your destination Ollama service !!!
DESTINATION_OLLAMA_ENDPOINT = "http://localhost:11434/api/generate" # Example: Replace with your real endpoint
FORWARD_REQUEST_TIMEOUT = 120 # Timeout in seconds for the forwarded request

# --- Flask App Setup ---
app = Flask(__name__)

# --- Result Storage ---
thread_results = {}

def extract_braced_content(text):
    """
    Removes newline characters from a string and extracts the contents
    between the first pair of curly braces '{}'.

    Args:
        text: The input string.

    Returns:
        The content within the first curly braces as a string, or None
        if no curly braces are found.  Returns an empty string if
        empty braces are found ({}).
    """
    text = text.replace('\n', '')  # Remove newline characters
    match = re.search(r'{(.*?)}', text)  # Find content within the first {}

    if match:
        return match.group(1)  # Return the captured group (content within {})
    else:
        return None  # Return None if no match is found

def execute_command_os_from_string(text):
    """
    Extracts the first JSON object ({...}) from a string, checks if it
    contains the key 'command_os', executes the corresponding value as
    an OS command, and returns the result.

    *** SECURITY WARNING: Executing commands from arbitrary strings is ***
    *** extremely dangerous. Only use this function with input from   ***
    *** fully trusted sources. The use of `shell=True` allows shell   ***
    *** features but increases security risks like command injection. ***

    Args:
        text: The input string potentially containing JSON with a 'command_os' key.

    Returns:
        A dictionary containing:
        - 'status': 'success', 'key_not_found', 'invalid_json', 'execution_error', 'no_braces'.
        - 'output': The standard output of the command (if successful).
        - 'error': The standard error of the command or an error message.
        - 'return_code': The command's return code (if executed).
        Returns None if the input text is None.
    """
    if text is None:
        return None

    # First, extract content that looks like a JSON object
    # We assume the command_os is within the first {..} block
    json_content_str = extract_braced_content(text) # Reuse the function above

    if json_content_str is None:
        return {'status': 'no_braces', 'output': None, 'error': 'No content found within {} braces.', 'return_code': None}

    # Add back the braces for valid JSON parsing
    potential_json = "{" + json_content_str + "}"

    try:
        # Attempt to parse the extracted content as JSON
        data = json.loads(potential_json)

        if not isinstance(data, dict):
             return {'status': 'invalid_json', 'output': None, 'error': 'Extracted content is not a JSON object (dictionary).', 'return_code': None}

        # Check if the 'command_os' key exists
        if 'command_os' in data:
            command_to_run = data['command_os']

            if not isinstance(command_to_run, str) or not command_to_run.strip():
                 return {'status': 'invalid_command', 'output': None, 'error': "'command_os' value must be a non-empty string.", 'return_code': None}

            print(f"--- Attempting to execute command: {command_to_run} ---")
            try:
                # Execute the command
                # Using shell=True is convenient but carries security risks.
                # Consider shell=False and splitting the command if possible:
                # result = subprocess.run(shlex.split(command_to_run), capture_output=True, text=True, check=False)
                result = subprocess.run(command_to_run,
                                        shell=True,
                                        capture_output=True,
                                        text=True,
                                        check=False) # check=False allows us to capture errors

                print(f"--- Command execution finished. Return code: {result.returncode} ---")

                if result.returncode == 0:
                    return {'status': 'success', 'output': result.stdout.strip(), 'error': result.stderr.strip(), 'return_code': result.returncode}
                else:
                    return {'status': 'execution_error', 'output': result.stdout.strip(), 'error': result.stderr.strip(), 'return_code': result.returncode}

            except Exception as e:
                print(f"--- Error during command execution: {e} ---")
                return {'status': 'execution_error', 'output': None, 'error': f"Exception during subprocess execution: {e}", 'return_code': None}
        else:
            # Key 'command_os' not found in the JSON
            return {'status': 'key_not_found', 'output': None, 'error': "Key 'command_os' not found in the extracted JSON.", 'return_code': None}

    except json.JSONDecodeError as e:
        # Extracted content was not valid JSON
        return {'status': 'invalid_json', 'output': None, 'error': f"Failed to decode JSON: {e}", 'return_code': None}
    except Exception as e:
        # Catch other potential errors
        return {'status': 'execution_error', 'output': None, 'error': f"An unexpected error occurred: {e}", 'return_code': None}

def get_output_from_result(execution_result):
    """
    Extracts the 'output' value (stdout) from the result dictionary returned by
    execute_command_os_from_string.

    Args:
        execution_result: The dictionary returned by execute_command_os_from_string.

    Returns:
        The command's standard output as a string if the 'output' key exists,
        otherwise returns None. Note that the output string might be empty if
        the command produced no stdout.
    """
    if isinstance(execution_result, dict) and 'output' in execution_result:
        # Return the output string. This could be None if execution failed
        # before the command ran, or an empty string, or the actual stdout.
        return execution_result['output']
    else:
        # Input was not a dictionary or 'output' key is missing
        return None

# --- Worker Function (runs in a separate thread) ---
def forward_and_get_response(original_request_id, destination_url, payload):
    """
    Forwards the request payload to the destination URL, inspects the response
    for 'command_os', prints its value if found, and stores the result.

    Args:
        original_request_id (str): A unique identifier for this request thread.
        destination_url (str): The URL to forward the request to.
        payload (dict): The JSON data received from the original request.
    """
    global thread_results
    result_data = None
    status_code = 500 # Default to internal server error

    try:
        print(f"Thread {original_request_id}: Forwarding request to {destination_url}")
        response = requests.post(
            destination_url,
            json=payload,
            timeout=FORWARD_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        # Assuming the destination returns JSON
        result_data = response.json()
        status_code = response.status_code
        print(f"Thread {original_request_id}: Received response (Status: {status_code})")

        # Check if the response data is a dictionary and contains 'response'
        if isinstance(result_data, dict):
            if 'response' in result_data:
                raw_result = result_data['response']
                print(f"-----------------------------------------------------")
                print(f"Thread {original_request_id}: Found 'response' key.")
                print(f"Thread {original_request_id}: Value: {raw_result}")
                print(f"-----------------------------------------------------")
                command_output = get_output_from_result(execute_command_os_from_string(raw_result))
                result_data['response'] = raw_result + "\n" + command_output
                print(f"Thread {original_request_id}: Command Output: {command_output}")
                print(f"-----------------------------------------------------")
            else:
                pass # Key not found, do nothing specific
        else:
            pass # Response is not a dict, cannot check for the key


    except requests.exceptions.Timeout:
        print(f"Thread {original_request_id}: Error - Request to {destination_url} timed out.")
        result_data = {"error": "Request to destination timed out"}
        status_code = 504
    except requests.exceptions.RequestException as e:
        print(f"Thread {original_request_id}: Error forwarding request to {destination_url}: {e}")
        error_detail = str(e)
        try:
            if e.response is not None:
                error_detail = f"{e} - Response: {e.response.text}"
        except Exception:
            pass
        result_data = {"error": f"Failed to forward request: {error_detail}"}
        status_code = 502
    except json.JSONDecodeError as e:
        print(f"Thread {original_request_id}: Error - Could not decode JSON response from {destination_url}: {e}")
        result_data = {"error": "Invalid JSON response received from destination", "details": str(e)}
        status_code = 502 # Bad Gateway - upstream sent invalid response
    except Exception as e:
        print(f"Thread {original_request_id}: An unexpected error occurred: {e}")
        result_data = {"error": f"An unexpected error occurred during forwarding: {e}"}
        status_code = 500

    # Store the result (or error) for the main thread to pick up
    thread_results[original_request_id] = {
        "data": result_data,
        "status_code": status_code
    }


# --- Flask Route Handler ---
@app.route('/api/generate', methods=['POST']) # Route to match '/api/generate'
def handle_ollama_request(): # Function name can remain, or change for clarity if desired
    """
    Receives the POST request, starts a worker thread, waits for completion,
    and returns the result from the destination.
    """
    global thread_results

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    incoming_data = request.get_json()

    if not incoming_data or "model" not in incoming_data or "prompt" not in incoming_data:
         return jsonify({"error": "Missing required fields 'model' or 'prompt' in JSON payload"}), 400

    thread_id = threading.get_ident()
    request_id = f"req_{thread_id}_{time.time_ns()}"

    print(f"Main Handler: Received request at /api/generate. Starting thread {request_id}...")
    worker_thread = threading.Thread(
        target=forward_and_get_response,
        args=(request_id, DESTINATION_OLLAMA_ENDPOINT, incoming_data)
    )
    worker_thread.start()

    worker_thread.join() # Wait for the thread to complete
    print(f"Main Handler: Thread {request_id} finished.")

    result_info = thread_results.pop(request_id, None)

    if result_info:
        # Return the original data and status code obtained from the destination
        return jsonify(result_info["data"]), result_info["status_code"]
    else:
        print(f"Main Handler: Error - Result for thread {request_id} not found.")
        return jsonify({"error": "Internal server error: Could not retrieve result from worker thread"}), 500

# --- Run the Flask App ---
if __name__ == '__main__':
    print(f"Starting Flask server. Listening on route /api/generate.")
    print(f"Forwarding requests to: {DESTINATION_OLLAMA_ENDPOINT}")
    # Remember to use a production WSGI server (like Gunicorn) for deployment
    app.run(host='0.0.0.0', port=5001, debug=True) # Use debug=False in production
