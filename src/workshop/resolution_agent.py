import os
import time
import asyncio
import logging
from typing import Tuple

from azure.ai.agents.models import MessageRole

from utils import (
    project_client,
    API_DEPLOYMENT_NAME,
    add_agent_tools,
    async_reboot_vm,
    toolset,
    INSTRUCTIONS_FILE,
    cleanup,
    AZURE_RESOURCE_GROUP_NAME,
    AZURE_SUBSCRIPTION_ID,
)
from azure.ai.agents.models import AsyncFunctionTool
import re


logger = logging.getLogger(__name__)


async def async_llm_decide(user_input: str) -> str:
    """Decide whether to 'solve' or 'escalate' based on the input.

    NOTE: This is intentionally simple and keyword-based. Replace this
    implementation with a real LLM call if desired.
    """
    # Simulate async LLM latency
    await asyncio.sleep(0.05)
    text = (user_input or "").lower()
    # crude heuristic: if CPU or high cpu load mentioned -> solve
    if "cpu" in text and ("high" in text or "high cpu" in text or "high cpu load" in text or "cpu usage" in text):
        print("async_llm_decide: returning 'solve'")
        return "solve"
    print("async_llm_decide: returning 'escalate'")
    return "escalate"


async def create_agent_from_prompt(prompt_path: str | None = None) -> Tuple[object, object]:
    """Create an Azure AI Agent using a plain prompt (no tools, no DB).

    Args:
        prompt_path: optional path to the prompt file. If omitted, looks for
            ../instructions/resolution_agent_prompt.txt relative to this file.

    Returns:
        (agent, thread)
    """
    # Default path: reuse INSTRUCTIONS_FILE logic from utils.py (honors ENVIRONMENT)
    if not prompt_path:
        env = os.getenv("ENVIRONMENT", "local")
        prompt_path = f"{'src/workshop/' if env == 'container' else ''}{INSTRUCTIONS_FILE}"

    if not os.path.isfile(prompt_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8", errors="ignore") as f:
        instructions = f.read()
    # Add tools configured in utils (reboot tool)
    try:
        await add_agent_tools()
    except Exception:
        pass

    # Register a simple LLM decision tool (tool 1)
    try:
        llm_tool = AsyncFunctionTool({async_llm_decide})
        toolset.add(llm_tool)
        print("Registered llm decision tool")
    except Exception:
        # ignore if already added or unsupported
        pass

    print("Creating resolution agent...")
    agent = project_client.agents.create_agent(
        model=API_DEPLOYMENT_NAME,
        name="Resolution Agent",
        instructions=instructions,
        temperature=0.0,
        toolset=toolset,
        headers={"x-ms-enable-preview": "true"},
    )
    print(f"Created resolution agent: {agent.id}")

    print("Creating thread for resolution agent...")
    thread = project_client.agents.threads.create()
    print(f"Created thread: {thread.id}")

    return agent, thread


async def create_decision_agent() -> Tuple[object, object]:
    """Create a tiny decision-only agent that replies with exactly 'solve' or 'escalate'.

    This agent is created on-demand and deleted after use. It keeps the model
    call inside the Foundry agent runtime so we use the actual LLM instead of a
    local heuristic.
    Returns (agent, thread)
    """
    instructions = (
        "You are a tiny Decision Agent. When given a user problem description, "
        "respond with exactly one word, either 'solve' or 'escalate'. "
        "Return 'solve' only if the problem explicitly describes high CPU usage "
        "or high CPU load on a VM; otherwise return 'escalate'. Do not add any "
        "other text or punctuation."
    )

    # Ensure shared tools are available (none needed for decision)
    try:
        await add_agent_tools()
    except Exception:
        pass

    print("Creating decision agent...")
    agent = project_client.agents.create_agent(
        model=API_DEPLOYMENT_NAME,
        name="Decision Agent",
        instructions=instructions,
        temperature=0.0,
        headers={"x-ms-enable-preview": "true"},
    )
    print(f"Created decision agent: {agent.id}")

    thread = project_client.agents.threads.create()
    print(f"Created decision thread: {thread.id}")

    return agent, thread


async def post_message(thread_id: str, content: str, agent: object, thread: object, timeout_seconds: int = 120) -> str:
    """Post a message to the resolution agent and print the agent response.

    This is a lightweight variant that does not handle tool calls.
    """
    # -- Workflow implemented as requested (5 explicit steps) --
    try:
        # Step 1: Input comes in (string from terminal)
        user_input = content
        print(f"Step 1: Received input: {user_input}")

        # Step 2: Ask the decision agent (preferred) to return 'solve' or 'escalate'
        print("Step 2: Creating and querying the Decision Agent to determine 'solve' vs 'escalate'...")
        decision = None
        decision_agent = None
        decision_thread = None
        try:
            decision_agent, decision_thread = await create_decision_agent()

            # Post the user's problem to the decision agent's thread
            msg = project_client.agents.messages.create(
                thread_id=decision_thread.id,
                role="user",
                content=user_input,
            )
            print(f"Decision agent message created: {getattr(msg, 'id', '<no-id>')}")

            # Create a run for the decision agent and poll until completion
            run = project_client.agents.runs.create(thread_id=decision_thread.id, agent_id=decision_agent.id)
            print(f"Decision agent run created: {getattr(run, 'id', '<no-id>')}")

            waited = 0
            poll_interval = 1
            timeout = 30
            while run.status in ("queued", "in_progress", "requires_action") and waited < timeout:
                time.sleep(poll_interval)
                waited += poll_interval
                try:
                    run = project_client.agents.runs.get(thread_id=decision_thread.id, run_id=run.id)
                    print(f"Decision run status: {run.status}")
                except Exception as e:
                    logger.debug("Error polling decision run: %s", e)

            if run.status == "completed":
                # Read the agent's last message (should be exactly 'solve' or 'escalate')
                try:
                    resp = project_client.agents.messages.get_last_message_by_role(
                        thread_id=decision_thread.id,
                        role=MessageRole.AGENT,
                    )
                    if resp and getattr(resp, 'text_messages', None):
                        text = "\n".join(t.text.value for t in resp.text_messages)
                        decision = text.strip().lower()
                        print(f"Decision agent replied: {decision}")
                except Exception as e:
                    print(f"Error reading decision agent response: {e}")

        except Exception as e:
            print(f"Decision agent error: {e}")
            logger.debug("Decision agent failure, falling back to local LLM: %s", e)
        finally:
            # Cleanup the temporary decision agent
            try:
                if decision_agent:
                    project_client.agents.delete_agent(decision_agent.id)
                    print(f"Deleted decision agent: {decision_agent.id}")
            except Exception as e:
                print(f"Error deleting decision agent: {e}")

        # Fallback to local LLM decision if agent approach failed
        if not decision:
            print("Falling back to local LLM decision implementation...")
            decision = await async_llm_decide(user_input)

        print(f"Step 3: LLM decision: {decision}")

        # Step 4: If decision == 'solve', reboot the VM
        if decision == "solve":
            print("Step 4: Decision is 'solve' — attempting to reboot VM in Azure environment...")
            # Try to extract VM name and resource group from the input, otherwise use environment
            vm_name = "VirtualMachine"
            resource_group = AZURE_RESOURCE_GROUP_NAME
            subscription_id = AZURE_SUBSCRIPTION_ID

            # crude parsing: look for patterns like 'vm_name=NAME' or 'vm NAME'
            m = re.search(r"vm_name[:= ]+([A-Za-z0-9-]+)", user_input, re.IGNORECASE)
            if m:
                vm_name = m.group(1)
            else:
                m2 = re.search(r"vm[:= ]+([A-Za-z0-9-]+)", user_input, re.IGNORECASE)
                if m2:
                    vm_name = m2.group(1)

            if not vm_name:
                # If VM name not provided in input, try env variable
                vm_name = os.getenv("AZURE_VM_NAME")

            if not vm_name:
                print("VM name not found in input or environment; cannot reboot. Escalating.")
                return "Unfamiliar issue detected, human intervention is needed."

            try:
                reboot_result = await async_reboot_vm(resource_group=resource_group, vm_name=vm_name, subscription_id=subscription_id)
                print(f"Reboot result: {reboot_result}")
                # Step 5: Return solved message
                return "The problem is solved, your virtual machine is rebooted."
            except Exception as e:
                print(f"Error rebooting VM: {e}")
                logger.exception(e)
                return "Unfamiliar issue detected, human intervention is needed."

        # If decision is 'escalate' or anything else -> escalate
        print("Step 4: Decision is 'escalate' — not attempting reboot.")
        # Step 5: Return escalation message
        return "Unfamiliar issue detected, human intervention is needed."

    except Exception as e:
        print(f"Error posting message: {e}")
        logger.exception(e)
        return "Unfamiliar issue detected, human intervention is needed."
