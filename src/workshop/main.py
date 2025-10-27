import asyncio
from datetime import date
import logging
import os
import glob
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    Agent,
    AgentThread,
    AsyncFunctionTool,
    AsyncToolSet,
    CodeInterpreterTool,
    FileSearchTool,
    MessageRole,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from sales_data import SalesData
from terminal_colors import TerminalColors as tc
from utilities import Utilities

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

API_DEPLOYMENT_NAME = os.getenv("AGENT_MODEL_DEPLOYMENT_NAME")
PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
AZURE_SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
AZURE_RESOURCE_GROUP_NAME = os.environ["AZURE_RESOURCE_GROUP_NAME"]
AZURE_PROJECT_NAME = os.environ["AZURE_PROJECT_NAME"]
BING_CONNECTION_NAME = os.getenv("BING_CONNECTION_NAME")

# Set up directory paths
TEMPLATE_DIR = Path("template")
CHANGE_DIR = Path("change")
print("\n📁 Analyzing directory structure:")
print(f"• Template directory path: {TEMPLATE_DIR.absolute()}")
print(f"• Change directory path: {CHANGE_DIR.absolute()}")

def analyze_directory(directory: Path, dir_name: str) -> list[Path]:
    """Analyze directory contents and return list of Excel files."""
    excel_files = []
    
    if directory.exists():
        print(f"\n✓ {dir_name} directory exists")
        print("\nDirectory contents:")
        try:
            # List all files and directories
            for item in directory.iterdir():
                if item.is_file():
                    stats = item.stat()
                    size_kb = stats.st_size / 1024
                    modified = date.fromtimestamp(stats.st_mtime)
                    print(f"📄 {item.name}")
                    print(f"   - Type: File")
                    print(f"   - Size: {size_kb:.1f} KB")
                    print(f"   - Modified: {modified}")
                    if item.suffix.lower() == '.xlsx':
                        excel_files.append(item)
                elif item.is_dir():
                    items = list(item.iterdir())
                    print(f"📂 {item.name}/")
                    print(f"   - Type: Directory")
                    print(f"   - Contains: {len(items)} items")
                    # List contents of subdirectory
                    for subitem in items:
                        print(f"     └─ {subitem.name}")
        except Exception as e:
            print(f"Error reading directory contents: {e}")
    else:
        print(f"\n⚠️ {dir_name} directory does not exist")
        print(f"• Creating directory: {directory.absolute()}")
        directory.mkdir(exist_ok=True)
        print("✓ Directory created successfully")
    
    return excel_files

# Analyze template directory
TEMPLATE_FILES = analyze_directory(TEMPLATE_DIR, "Template")

print(f"\n📊 Excel files summary:")
print(f"• Found {len(TEMPLATE_FILES)} Excel files in template directory")
if TEMPLATE_FILES:
    print("Files available for indexing:")
    for file in TEMPLATE_FILES:
        stats = file.stat()
        print(f"  - {file.name}")
        print(f"    Size: {stats.st_size / 1024:.1f} KB")
        print(f"    Modified: {date.fromtimestamp(stats.st_mtime)}")
else:
    print("No Excel files found in template directory")

MAX_COMPLETION_TOKENS = 4096
MAX_PROMPT_TOKENS = 10240
TEMPERATURE = 0.1
TOP_P = 0.1

sales_data = SalesData()
utilities = Utilities()

# Project client initialization (outside the context manager for global access)
# Try different client initialization approaches
try:
    # Method 1: Full endpoint approach
    if "/api/projects/" in PROJECT_ENDPOINT:
        project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        print(f"Using full project endpoint: {PROJECT_ENDPOINT}")
    else:
        # Method 2: Base endpoint approach
        project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
            subscription_id=AZURE_SUBSCRIPTION_ID,
            resource_group_name=AZURE_RESOURCE_GROUP_NAME,
            project_name=AZURE_PROJECT_NAME,
        )
        print(f"Using base endpoint with project details: {PROJECT_ENDPOINT}")
except Exception as e:
    print(f"Error creating project client: {e}")
    # Fallback: try with just endpoint
    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    print("Using fallback client configuration")


INSTRUCTIONS_FILE = "instructions/instructions_function_calling.txt"
INSTRUCTIONS_FILE = "instructions/instructions_code_interpreter.txt"
INSTRUCTIONS_FILE = "instructions/instructions_file_search.txt"


async def add_agent_tools():
    """Create and return a fresh AsyncToolSet for the agent."""
    toolset = AsyncToolSet()

    # Create the functions tool for this toolset
    functions = AsyncFunctionTool({sales_data.async_fetch_sales_data_using_sqlite_query})
    toolset.add(functions)

    # Add the code interpreter tool
    code_interpreter = CodeInterpreterTool()
    toolset.add(code_interpreter)

    # Add file search tool and set up vector store
    print("\nInitializing file search capability...")
    try:
        if not TEMPLATE_FILES:
            print("\n⚠️  Warning: No Excel files available for search indexing")
            print("Please ensure Excel files are present in the template directory:")
            print(f"→ Directory: {TEMPLATE_DIR.absolute()}")
            print("Expected files:")
            print("  • logs_table.xlsx - Contains logging information")
            print("  • Roles_table.xlsx - Contains role definitions")
            print("\nContinuing without file search capability...")
        else:
            print("\n🔍 Preparing files for search indexing:")
            for file in TEMPLATE_FILES:
                stats = file.stat()
                print(f"• Processing {file.name}")
                print(f"  - Size: {stats.st_size / 1024:.1f} KB")
                print(f"  - Last modified: {date.fromtimestamp(stats.st_mtime)}")
            
            print("\n📑 Creating vector store for file search...")
            # Create the vector store
            try:
                vector_store = utilities.create_vector_store(
                    project_client=project_client,
                    files=TEMPLATE_FILES,
                    vector_name="Contoso Templates Vector Store"
                )
                print("✓ Vector store created successfully")
            except Exception as ve:
                print(f"Error creating vector store: {str(ve)}")
                print("Continuing without file search capability...")
                return toolset
            
            # Add file search tool
            file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
            toolset.add(file_search_tool)
            print(f"✓ File search tool added with vector store: {vector_store.id}")
            
    except Exception as e:
        print(f"Error setting up file search tool: {str(e)}")
        print("Continuing without file search capability...")

    return toolset


async def initialize() -> tuple[Agent, AgentThread]:
    """Initialize the agent with the sales data schema and instructions."""
    agent = None
    thread = None
    
    # Setup directories and copy template files
    print("\n🔄 Setting up working directories...")
    success, message = utilities.copy_template_files()
    if not success:
        print(f"Warning during template copy: {message}")
        return None, None
    else:
        print(message)
    
    # Modify logs table in change directory and upload to blob
    print("\n📝 Modifying and uploading logs table...")
    success, message = utilities.modify_and_upload_logs()
    if not success:
        print(f"Warning during modification: {message}")
    else:
        print(message)

    await sales_data.connect()
    database_schema_string = await sales_data.get_database_info()

    try:
        env = os.getenv("ENVIRONMENT", "local")
        INSTRUCTIONS_FILE_PATH = f"{'src/workshop/' if env == 'container' else ''}{INSTRUCTIONS_FILE}"

        with open(INSTRUCTIONS_FILE_PATH, "r", encoding="utf-8", errors="ignore") as file:
            instructions = file.read()

        # Replace the placeholder with the database schema string
        instructions = instructions.replace("{database_schema_string}", database_schema_string)
        instructions = instructions.replace("{current_date}", date.today().strftime("%Y-%m-%d"))

        # Add agent tools (create a fresh toolset per initialize call)
        toolset = await add_agent_tools()

        # Create agent and thread without closing the context manager
        print("Creating agent...")
        agent = project_client.agents.create_agent(
            model=API_DEPLOYMENT_NAME,
            name="IsoWatch-Infrastructure-AI",
            instructions=instructions,
            toolset=toolset,
            temperature=TEMPERATURE,
            headers={"x-ms-enable-preview": "true"},
        )
        print(f"Created agent, ID: {agent.id}")

        # Create thread
        print("Creating thread...")
        thread = project_client.agents.threads.create()
        print(f"Created thread, ID: {thread.id}")

        return agent, thread

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        raise


async def cleanup(agent: Agent, thread: AgentThread) -> None:
    """Cleanup the resources."""
    try:
        project_client.agents.delete_agent(agent.id)
        print(f"Deleted agent: {agent.id}")
    except Exception as e:
        print(f"Error deleting agent: {e}")
    
    await sales_data.close()


async def post_message(thread_id: str, content: str, agent: Agent, thread: AgentThread) -> None:
    """Post a message to the Azure AI Agent Service."""
    try:
        print(f"Creating message in thread {thread_id}...")
        
        # Create message using project_client directly with retries
        max_attempts = 3
        attempt = 0
        message = None
        while attempt < max_attempts:
            attempt += 1
            try:
                message = project_client.agents.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=content,
                )
                print(f"Message created: {getattr(message, 'id', '<no-id>')}")
                break
            except Exception as e:
                print(f"Error creating message (attempt {attempt}/{max_attempts}): {e}")
                # On final attempt, re-raise to be handled below
                if attempt >= max_attempts:
                    raise
                import time as _time
                _time.sleep(2 * attempt)

        print(f"Creating run for agent {agent.id}...")
        # Create and poll run (with retries)
        run = None
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                run = project_client.agents.runs.create(
                    thread_id=thread.id,
                    agent_id=agent.id,
                )
                print(f"Run created: {getattr(run, 'id', '<no-id>')}")
                break
            except Exception as e:
                print(f"Error creating run (attempt {attempt}/{max_attempts}): {e}")
                if attempt >= max_attempts:
                    raise
                import time as _time
                _time.sleep(2 * attempt)
        
        # Enhanced polling with action handling
        import time
        max_iterations = 120  # Max 2 minutes
        iteration = 0
        
        while run.status in ("queued", "in_progress", "requires_action") and iteration < max_iterations:
            time.sleep(2)  # Increased sleep time
            iteration += 1
            
            try:
                run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
                print(f"Run status: {run.status} (iteration {iteration})")
            except Exception as e:
                print(f"Error getting run status: {e}")
                time.sleep(5)  # Wait longer on error
                continue
            
            # Handle required actions (function calls)
            if run.status == "requires_action" and run.required_action:
                print("Run requires action - handling function calls...")
                
                tool_outputs = []
                try:
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                        print(f"Executing function: {tool_call.function.name}")
                        
                        # Execute the function call
                        if tool_call.function.name == "async_fetch_sales_data_using_sqlite_query":
                            import json
                            args = json.loads(tool_call.function.arguments)
                            result = await sales_data.async_fetch_sales_data_using_sqlite_query(args["sqlite_query"])
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": result
                            })
                    
                    # Submit the tool outputs
                    if tool_outputs:
                        print("Submitting tool outputs...")
                        run = project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        print("Tool outputs submitted successfully")
                except Exception as e:
                    print(f"Error handling tool outputs: {e}")
                    break
        
        if iteration >= max_iterations:
            print("Run timed out after maximum iterations")
            return "(timed out)"
            
        print(f"Run finished with status: {run.status}")
        
        # Log run summary for debugging
        try:
            print(f"Run summary: id={getattr(run, 'id', '<no-id>')} status={getattr(run, 'status', '<no-status>')}")
            print(f"Run last_error: {getattr(run, 'last_error', None)}")
            print(f"Run required_action: {getattr(run, 'required_action', None)}")
        except Exception:
            pass

        if run.status == "failed":
            print(f"Run failed: {getattr(run, 'last_error', '<no-error>')}")
            return f"(run failed: {getattr(run, 'last_error', '<no-error>')})"
        elif run.status == "completed":
            # Get the last message from the agent and return it
            try:
                response = project_client.agents.messages.get_last_message_by_role(
                    thread_id=thread_id,
                    role=MessageRole.AGENT,
                )
                if response and getattr(response, 'text_messages', None):
                    response_text = "\n".join(t.text.value for t in response.text_messages)
                    print("\nAgent response:")
                    print(response_text)
                else:
                    response_text = "(no response)"
                    print("No response message found")

                # Handle file downloads from code interpreter
                try:
                    utilities.download_agent_files(project_client, thread_id)
                except Exception as e:
                    print(f"Error handling file downloads: {e}")

                # Convert markdown/plain text to HTML for consistent UI rendering
                try:
                    import markdown as _md
                    html = _md.markdown(response_text)
                except (ImportError, Exception):
                    html = f"<pre>{response_text}</pre>"

                # Sanitize HTML to prevent XSS before returning to the client
                try:
                    import bleach as _bleach
                    allowed_tags = [
                        'p','br','strong','em','ul','ol','li',
                        'table','thead','tbody','tr','th','td'
                    ]
                    allowed_attrs = {
                        'th': [],
                        'td': [],
                        'a': ['href','title'],
                    }
                    clean = _bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
                except Exception:
                    clean = html

                return clean
            except Exception as e:
                print(f"Error getting response message: {e}")
                return f"(error getting response: {e})"

    except Exception as e:
        print(f"An error occurred posting the message: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"(exception: {e})"


async def main() -> None:
    """
    Main function to run the agent.
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
    """
    # Use the project client within a context manager for the entire session
    with project_client:
        agent, thread = await initialize()

        while True:
            # Get user input prompt in the terminal using a pretty shade of green
            print("\n")
            prompt = input(f"{tc.GREEN}Enter your query (type exit to finish): {tc.RESET}")
            if prompt.lower() == "exit":
                break
            if not prompt:
                continue
            await post_message(agent=agent, thread_id=thread.id, content=prompt, thread=thread)

        await cleanup(agent, thread)


if __name__ == "__main__":
    print("Starting async program...")
    asyncio.run(main())
    print("Program finished.")
