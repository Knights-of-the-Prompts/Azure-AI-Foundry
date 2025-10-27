import os
import time
from typing import Optional, Dict, Any, Tuple

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import DeepResearchTool, MessageRole, ThreadMessage
from dotenv import load_dotenv, find_dotenv

# Load environment variables from a .env file. find_dotenv will search parent
# directories from the current working directory and return the first .env found.
env_path = find_dotenv()
if env_path:
    load_dotenv(env_path)
else:
    # Fallback: attempt to load a .env located at the repository root (two levels up from this file)
    repo_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    if os.path.exists(repo_root_env):
        load_dotenv(repo_root_env)
    else:
        # Last resort: call load_dotenv() without path (will try current working dir)
        load_dotenv()


def _initialize_project_client() -> AIProjectClient:
    return AIProjectClient(
        endpoint=os.environ["PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


def _get_bing_connection_id(project_client: AIProjectClient, bing_name_env: str = "BING_RESOURCE_NAME") -> str:
    return project_client.connections.get(name=os.environ[bing_name_env]).id


def answer_query(
    query: str,
    agent_model_env: str = "AGENT_MODEL_DEPLOYMENT_NAME",
    deep_research_model_env: str = "DEEP_RESEARCH_MODEL_DEPLOYMENT_NAME",
    bing_name_env: str = "BING_RESOURCE_NAME",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Programmatic entry point to send a query to a Deep Research-enabled agent and return
    a structured response. This function is intended to be called by other modules (e.g.,
    the Compliance Manager).

    Returns a dict with keys: status, message_text, citations (list of {title,url}), error
    """
    project_client = _initialize_project_client()
    conn_id = _get_bing_connection_id(project_client, bing_name_env)

    deep_research_tool = DeepResearchTool(
        bing_grounding_connection_id=conn_id,
        deep_research_model=os.environ[deep_research_model_env],
    )

    with project_client:
        with project_client.agents as agents_client:
            # Stronger instructions: request structured citations and a final CITATIONS list when possible.
            agent = agents_client.create_agent(
                model=os.environ[agent_model_env],
                name=f"deep-research-agent-{int(time.time())}",
                instructions=(
                    "You are a helpful Agent that assists in managing security and compliance topics for auditing.\n"
                    "Do not hallucinate. Always cite official sources for factual claims.\n"
                    "When providing factual statements, add URL citations using the agent's citation annotations if available.\n"
                    "Also include, at the end of your reply, a short \"CITATIONS:\" section listing the canonical URLs you used (one per line).\n"
                    "If you cannot find authoritative sources, say so and ask for clarification."
                ),
                tools=deep_research_tool.definitions,
            )

            # Create thread and initial user message
            thread = agents_client.threads.create()
            message = agents_client.messages.create(
                thread_id=thread.id,
                role="user",
                content=query,
            )

            # Start run and poll
            run = agents_client.runs.create(thread_id=thread.id, agent_id=agent.id)
            start = time.time()
            last_message_id: Optional[str] = None

            while run.status in ("queued", "in_progress"):
                if time.time() - start > timeout_seconds:
                    agents_client.delete_agent(agent.id)
                    return {"status": "timeout", "message_text": "", "citations": [], "error": "timeout"}
                time.sleep(1)
                run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)

                # check for new messages but do not print (library callers will handle display)
                response = agents_client.messages.get_last_message_by_role(thread_id=thread.id, role=MessageRole.AGENT)
                if response and response.id != last_message_id:
                    last_message_id = response.id

            # After run finished, fetch final agent message
            final_message = agents_client.messages.get_last_message_by_role(thread_id=thread.id, role=MessageRole.AGENT)

            result: Dict[str, Any] = {"status": run.status, "message_text": "", "citations": [], "error": None}

            if run.status == "failed":
                result["error"] = getattr(run, "last_error", "run_failed")
            elif final_message:
                # Concatenate text parts
                text = "\n\n".join([t.text.value.strip() for t in final_message.text_messages])
                result["message_text"] = text

                # extract unique structured citations (if any)
                seen = set()
                citations = []
                for ann in getattr(final_message, 'url_citation_annotations', []) or []:
                    try:
                        url = ann.url_citation.url
                        title = ann.url_citation.title or url
                    except Exception:
                        continue
                    if url and url not in seen:
                        citations.append({"title": title, "url": url})
                        seen.add(url)

                # Fallback: if no structured annotations, attempt to extract inline URLs from the text
                if not citations and text:
                    import re

                    # Improved URL regex: capture until whitespace or common delimiters
                    found = re.findall(r"https?://[^\s'\"<>()]+", text)
                    for u in found:
                        # normalize: remove surrounding brackets/parentheses/angle-brackets and trailing punctuation
                        u_clean = u.strip("[]()<>")
                        u_clean = u_clean.rstrip('.,;:')
                        if u_clean and u_clean not in seen:
                            citations.append({"title": u_clean, "url": u_clean})
                            seen.add(u_clean)

                result["citations"] = citations

            # Clean up agent to avoid resource leak
            try:
                agents_client.delete_agent(agent.id)
            except Exception:
                pass

            return result


def create_research_summary(
        message : ThreadMessage,
        filepath: str = "research_summary.md"
) -> None:
    if not message:
        print("No message content provided, cannot create research summary.")
        return

    with open(filepath, "w", encoding="utf-8") as fp:
        # Add timestamp and header
        fp.write(f"# Research Summary\n")
        fp.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Write text summary
        text_summary = "\n\n".join([t.text.value.strip() for t in message.text_messages])
        fp.write(text_summary)

        # Write unique URL citations, if present
        if message.url_citation_annotations:
            fp.write("\n\n## References\n")
            seen_urls = set()
            for ann in message.url_citation_annotations:
                url = ann.url_citation.url
                title = ann.url_citation.title or url
                if url not in seen_urls:
                    fp.write(f"- [{title}]({url})\n")
                    seen_urls.add(url)

    print(f"Research summary written to '{filepath}'.")