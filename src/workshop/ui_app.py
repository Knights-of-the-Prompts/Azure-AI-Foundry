import asyncio
import threading
import os
import sys
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Check for required environment variables before importing main
required_env_vars = [
    "PROJECT_ENDPOINT",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_RESOURCE_GROUP_NAME",
    "AZURE_PROJECT_NAME"
]

missing_vars = [var for var in required_env_vars if not os.environ.get(var)]

if missing_vars:
    print("\n" + "="*70)
    print("ERROR: Missing required environment variables!")
    print("="*70)
    print("\nThe following environment variables are not set:")
    for var in missing_vars:
        print(f"  - {var}")
    print("\nPlease create a .env file in src/workshop/ with these variables.")
    print("You can use .env.example as a template:")
    print("  cp .env.example .env")
    print("\nFor detailed setup instructions, see DEBUG_GUIDE.md")
    print("="*70 + "\n")
    sys.exit(1)

# Import utilities from the existing project
from main import initialize, post_message, cleanup, project_client

app = Flask(__name__, template_folder="templates", static_folder="static")

# We'll run the async agent loop in a background event loop thread
loop = asyncio.new_event_loop()
thread = None
agent_and_thread = None


def start_event_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def start_loop_thread():
    """Start the background asyncio event loop thread for handling agent coroutines."""
    global thread
    if thread is None:
        thread = threading.Thread(target=start_event_loop, args=(loop,), daemon=True)
        thread.start()


@app.route("/")
def index():
    # Serve the legacy UI's index.html explicitly from the samples folder to avoid
    # colliding with other apps that share the same `templates` directory.
    try:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        legacy_path = os.path.join(base, 'samples', 'create-mcp-foundry-agents', 'templates', 'index.html')
        if os.path.exists(legacy_path):
            with open(legacy_path, 'r', encoding='utf-8') as fh:
                return fh.read(), 200, {'Content-Type': 'text/html'}
    except Exception:
        pass
    # Fallback to the normal template loader if the legacy file isn't found
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    """Initialize the agent in the event loop and return success/failure."""
    global agent_and_thread

    async def _init():
        return await initialize()

    future = asyncio.run_coroutine_threadsafe(_init(), loop)
    try:
        agent_and_thread = future.result(timeout=30)
        # Return simple HTML success message
        return "<div class=\"ok\">Agent started.</div>", 200, {"Content-Type": "text/html"}
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/query", methods=["POST"])
def api_query():
    """Accept user query, post to agent, and return the agent's response."""
    data = request.json or {}
    query = data.get("query", "")

    if not query:
        return jsonify({"status": "error", "message": "Empty query"}), 400

    if not agent_and_thread:
        return jsonify({"status": "error", "message": "Agent not started"}), 400

    agent, thread_obj = agent_and_thread

    async def _post_and_wait():
        # post_message now returns the response string (or an error description)
        result = await post_message(thread_id=thread_obj.id, content=query, agent=agent, thread=thread_obj)
        return result

    future = asyncio.run_coroutine_threadsafe(_post_and_wait(), loop)
    try:
        result = future.result(timeout=120)
        # `result` is already HTML (converted in post_message). Return HTML directly.
        return result, 200, {"Content-Type": "text/html"}
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Cleanup agent resources."""
    global agent_and_thread

    if not agent_and_thread:
        return jsonify({"status": "ok", "message": "No agent to stop"})

    agent, thread_obj = agent_and_thread

    async def _cleanup():
        await cleanup(agent, thread_obj)

    future = asyncio.run_coroutine_threadsafe(_cleanup(), loop)
    try:
        future.result(timeout=30)
        agent_and_thread = None
        return "<div class=\"ok\">Agent stopped.</div>", 200, {"Content-Type": "text/html"}
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # Start background event loop thread for async agent operations
    start_loop_thread()

    # Start Flask app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
