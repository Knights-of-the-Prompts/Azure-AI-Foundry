import asyncio
from datetime import date
import logging
import os
import time

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
MAX_COMPLETION_TOKENS = 4096
MAX_PROMPT_TOKENS = 10240
TEMPERATURE = 0.1
TOP_P = 0.1

toolset = AsyncToolSet()
sales_data = SalesData()
utilities = Utilities()


async def async_reboot_vm(resource_group: str, vm_name: str, subscription_id: str | None = None) -> dict:
    """Restart an Azure VM using the Azure Compute SDK.

    This function runs the blocking SDK call inside a thread with
    asyncio.to_thread so it can be registered as an AsyncFunctionTool.
    """
    subscription = subscription_id or AZURE_SUBSCRIPTION_ID

    def _restart():
        try:
            # Import here so the module import doesn't fail when the SDK is not installed
            from azure.mgmt.compute import ComputeManagementClient
        except Exception as e:
            raise RuntimeError(
                "Missing dependency 'azure-mgmt-compute'. Install it in your venv with: pip install azure-mgmt-compute"
            ) from e

        cred = DefaultAzureCredential()
        compute_client = ComputeManagementClient(cred, subscription)
        # begin_restart returns a poller
        poller = compute_client.virtual_machines.begin_restart(resource_group_name=resource_group, vm_name=vm_name)
        poller.result()
        return {"status": "restarted", "resource_group": resource_group, "vm_name": vm_name}

    return await asyncio.to_thread(_restart)

# Project client initialization (outside the context manager for global access)
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

functions = AsyncFunctionTool(
    {
        sales_data.async_fetch_sales_data_using_sqlite_query,
    }
)

# Reboot tool wrapper
reboot_tool = AsyncFunctionTool(
    {
        async_reboot_vm,
    }
)

INSTRUCTIONS_FILE = "../instructions/resolution_agent_prompt.txt"


async def add_agent_tools() -> None:
    """Add configured tools to the global toolset used when creating agents.

    This registers the function-based tools so the agent can call them.
    """
    # Add any existing function tools
    try:
        toolset.add(functions)
    except Exception:
        # ignore if already added or unsupported
        pass

    # Add reboot tool
    try:
        toolset.add(reboot_tool)
    except Exception:
        pass


# async def add_agent_tools() -> None:
#     """Add tools for the agent (kept minimal and safe by default)."""

    # Add the functions tool (uncomment to enable automatic function tool usage)
    # toolset.add(functions)

    # # Add the code interpreter tool
    # code_interpreter = CodeInterpreterTool()
    # toolset.add(code_interpreter)

    # # Add file search tool - uncomment to enable file search capability
    # print("Creating vector store for file search...")
    # try:
    #     vector_store = utilities.create_vector_store(
    #         project_client,
    #         files=[TENTS_DATA_SHEET_FILE],
    #         vector_name_name="Contoso Product Information Vector Store",
    #     )
    #     file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
    #     toolset.add(file_search_tool)
    #     print(f"File search tool added with vector store: {vector_store.id}")
    # except Exception as e:
    #     print(f"Error creating file search tool: {e}")
    #     print("Continuing without file search capability...")


async def initialize() -> tuple[Agent, AgentThread]:
    """Initialize the agent with the sales data schema and instructions.

    Returns:
        tuple[Agent, AgentThread]: created agent and thread objects
    """
    agent = None
    thread = None

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

        # Add agent tools (this must be done inside the context manager)
        await add_agent_tools()

        # Create agent and thread without closing the context manager
        print("Creating agent...")
        agent = project_client.agents.create_agent(
            model=API_DEPLOYMENT_NAME,
            name="Contoso Sales AI Agent",
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
    """Post a message to the Azure AI Agent Service and handle function calls.

    This method will create a message, create a run, poll for results, handle
    any required actions (function/tool calls), and print the agent response.
    """
    try:
        print(f"Creating message in thread {thread_id}...")
        
        # Create message using project_client directly
        message = project_client.agents.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )
        print(f"Message created: {message.id}")

        print(f"Creating run for agent {agent.id}...")
        # Create and poll run
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=agent.id,
        )
        print(f"Run created: {run.id}")
        
        # Enhanced polling with action handling
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
            return
            
        print(f"Run finished with status: {run.status}")
        
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
        elif run.status == "completed":
            # Get the last message from the agent
            try:
                response = project_client.agents.messages.get_last_message_by_role(
                    thread_id=thread_id,
                    role=MessageRole.AGENT,
                )
                if response:
                    print("\nAgent response:")
                    print("\n".join(t.text.value for t in response.text_messages))
                else:
                    print("No response message found")
                
                # Handle file downloads from code interpreter
                try:
                    utilities.download_agent_files(project_client, thread_id)
                except Exception as e:
                    print(f"Error handling file downloads: {e}")
                    
            except Exception as e:
                print(f"Error getting response message: {e}")

    except Exception as e:
        print(f"An error occurred posting the message: {str(e)}")
        import traceback
        traceback.print_exc()
