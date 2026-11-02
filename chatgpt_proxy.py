import sys
import time
import json
import uuid
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

# Fix Unicode encoding on Windows terminals
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

app = Flask(__name__)
CORS(app, origins="*")

# Store pending requests
# Structure: { "task_id": {"prompt": "...", "event": Event(), "response": None} }
tasks = {}
task_queue = []

def extract_user_prompt(messages):
    """
    Extract a clean prompt from the messages list.
    We only send the last user/human message to ChatGPT to keep it concise.
    """
    if not messages:
        return ""

    # Get system message (first message with role=system)
    system_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
    
    # Get all non-system messages
    conversation = [m for m in messages if m.get("role") != "system"]
    
    if not conversation:
        return system_msg[:3000] if system_msg else ""
    
    # Build a prompt that includes the system context and full conversation
    parts = []
    if system_msg:
        # Only include first 1500 chars of system prompt to avoid ChatGPT limit
        parts.append("SYSTEM INSTRUCTIONS:\n" + system_msg[:1500] + "\n\n---\n")
    
    for m in conversation:
        role = m.get("role", "user").upper()
        content = m.get("content", "")
        # Handle content that might be a list (tool calls etc.)
        if isinstance(content, list):
            content = " ".join([
                c.get("text", "") if isinstance(c, dict) else str(c) 
                for c in content
            ])
        parts.append(f"{role}:\n{content}")
    
    return "\n\n".join(parts)

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Mock OpenAI endpoint — queues prompt for Chrome extension."""
    data = request.json
    messages = data.get("messages", [])
    
    prompt = extract_user_prompt(messages)
    
    task_id = str(uuid.uuid4())
    event = threading.Event()
    
    tasks[task_id] = {
        "prompt": prompt,
        "event": event,
        "response": None
    }
    
    with task_available:
        task_queue.append(task_id)
        task_available.notify_all()
        
    print(f"[Proxy] >> Task queued: {task_id[:8]}... ({len(prompt)} chars)")
    
    # Block until the Chrome extension provides the answer (10 min timeout)
    event.wait(timeout=600)
    
    if tasks[task_id]["response"] is None:
        del tasks[task_id]
        return jsonify({"error": {"message": "Timeout: Chrome extension did not respond in 5 minutes.", "type": "timeout"}}), 504
        
    answer = tasks[task_id]["response"]
    del tasks[task_id]
    
    print(f"[Proxy] OK Task done: {task_id[:8]}... ({len(answer)} chars returned)")
    
    return jsonify({
        "id": f"chatcmpl-{task_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "chatgpt-extension"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    })

import threading
task_available = threading.Condition()

@app.route("/poll", methods=["GET"])
def poll_tasks():
    """Chrome extension long-polls this for the next prompt (waits up to 30s)."""
    with task_available:
        if not task_queue:
            task_available.wait(timeout=30.0)
            
        if task_queue:
            task_id = task_queue.pop(0)
            if task_id in tasks:
                return jsonify({"task_id": task_id, "prompt": tasks[task_id]["prompt"]})
                
    return jsonify({"task_id": None, "tasks_processed": 0})

@app.route("/submit", methods=["POST"])
def submit_answer():
    """Chrome extension posts the ChatGPT response here."""
    data = request.json
    task_id = data.get("task_id")
    response = data.get("response", "")
    
    if task_id in tasks:
        tasks[task_id]["response"] = response
        tasks[task_id]["event"].set()
        print(f"[Proxy] << Answer received for {task_id[:8]}...")
        return jsonify({"status": "success"})
    return jsonify({"error": "Task not found"}), 404

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "queue_length": len(task_queue)})

@app.route("/reset", methods=["POST"])
def reset():
    """Clear any stuck queue items so a fresh investigation can start."""
    task_queue.clear()
    tasks.clear()
    print("[Proxy] !! Queue reset by client.")
    return jsonify({"status": "reset", "ok": True})

if __name__ == "__main__":
    print("=" * 50)
    print("  ChatGPT Proxy Server")
    print("  Listening on http://localhost:5000")
    print("=" * 50)
    # Bind to all interfaces so 'localhost' and '127.0.0.1' both work
    app.run(host="0.0.0.0", port=5000, threaded=True)
