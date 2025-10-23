import asyncio


from resolution_agent import create_agent_from_prompt, post_message as post_to_resolution_agent
from utils import project_client, tc


async def main() -> None:
    """Create a simple resolution agent and run an interactive chat loop.

    The resolution agent is created from the `resolution_agent_prompt.txt` file
    and has no tools or database connections. You can type messages in the
    terminal; type `exit` to quit.
    """
    # Use the project client within a context manager for the entire session
    with project_client:
        # Create resolution agent and thread from the resolution prompt
        agent, thread = await create_agent_from_prompt()

        try:
            
            print("\n")
            resolution_agent_input = "my cpu is very high!!" # message for resolution agent
            print("Input for resolution agent:", resolution_agent_input)
            
            resolution_agent_output = await post_to_resolution_agent(thread_id=thread.id, content=resolution_agent_input, agent=agent, thread=thread)
            print("Resolution agent output:", resolution_agent_output)
        finally:
            # Cleanup the created agent
            try:
                project_client.agents.delete_agent(agent.id)
                print(f"Deleted agent: {agent.id}")
            except Exception as e:
                print(f"Error deleting agent: {e}")


if __name__ == "__main__":
    print("Starting async program...")
    asyncio.run(main())
    print("Program finished.")

