import os
from pathlib import Path
import random

from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import ThreadMessage
from azure.storage.blob import BlobServiceClient
import pandas as pd

from terminal_colors import TerminalColors as tc


class Utilities:
    def __init__(self):
        """Initialize the Utilities class with blob storage configuration."""
        self.blob_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("BLOB_CONTAINER_NAME", "datasheets")
        
    def log_msg_green(self, msg: str) -> None:
        """Print a message in green."""
        print(f"{tc.GREEN}{msg}{tc.RESET}")

    def log_msg_purple(self, msg: str) -> None:
        """Print a message in purple."""
        print(f"{tc.PURPLE}{msg}{tc.RESET}")
        
    def upload_to_blob(self, local_file_path: Path, blob_name: str) -> bool:
        """Upload a file to Azure Blob Storage."""
        try:
            if not self.blob_connection_string:
                self.log_msg_purple("⚠️ AZURE_STORAGE_CONNECTION_STRING not set, skipping blob upload")
                return False
                
            blob_service_client = BlobServiceClient.from_connection_string(self.blob_connection_string)
            container_client = blob_service_client.get_container_client(self.container_name)
            
            # Create container if it doesn't exist
            if not container_client.exists():
                self.log_msg_purple(f"Creating container: {self.container_name}")
                container_client.create_container()
            
            # Get blob client and upload the file
            blob_client = container_client.get_blob_client(blob_name)
            with open(local_file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
                
            self.log_msg_green(f"✓ Uploaded to blob storage: {blob_name}")
            return True
            
        except Exception as e:
            self.log_msg_purple(f"Error uploading to blob: {str(e)}")
            return False

    def log_token_blue(self, msg: str) -> None:
        """Print a token in blue."""
        print(f"{tc.BLUE}{msg}{tc.RESET}", end="", flush=True)

    def get_file(self, project_client: AIProjectClient, file_id: str, attachment_name: str) -> None:
        """Retrieve the file and save it to the local disk."""
        self.log_msg_green(f"Getting file with ID: {file_id}")

        file_name, file_extension = os.path.splitext(
            os.path.basename(attachment_name.split(":")[-1]))
        file_name = f"{file_name}.{file_id}{file_extension}"

        env = os.getenv("ENVIRONMENT", "local")
        folder_path = Path(f"{'src/workshop/' if env == 'container' else ''}files")

        folder_path.mkdir(parents=True, exist_ok=True)

        file_path = folder_path / file_name

        # Save the file using a synchronous context manager
        with file_path.open("wb") as file:
            for chunk in project_client.agents.get_file_content(file_id):
                file.write(chunk)

        self.log_msg_green(f"File saved to {file_path}")
        # Cleanup the remote file
        project_client.agents.delete_file(file_id)

    def get_files(self, message: ThreadMessage, project_client: AIProjectClient) -> None:
        """Get the image files from the message and kickoff download."""
        if message.image_contents:
            for index, image in enumerate(message.image_contents, start=0):
                attachment_name = (
                    "unknown" if not message.file_path_annotations else message.file_path_annotations[
                        index].text
                )
                self.get_file(project_client, image.image_file.file_id, attachment_name)
        elif message.attachments:
            for index, attachment in enumerate(message.attachments, start=0):
                attachment_name = (
                    "unknown" if not message.file_path_annotations else message.file_path_annotations[
                        index].text
                )
                self.get_file(project_client, attachment.file_id, attachment_name)

    def copy_template_files(self) -> tuple[bool, str]:
        """Copy all files from template folder to change folder."""
        try:
            template_dir = Path("template")
            change_dir = Path("change")
            
            # Check if template directory exists
            if not template_dir.exists():
                return False, "Template directory does not exist"
                
            # Create change directory
            change_dir.mkdir(exist_ok=True)
            
            # Copy all files from template to change
            files_copied = []
            for file in template_dir.glob("*"):
                if file.is_file():
                    dest_file = change_dir / file.name
                    with file.open("rb") as src, dest_file.open("wb") as dst:
                        dst.write(src.read())
                    files_copied.append(file.name)
                    
            if not files_copied:
                return False, "No files found in template directory to copy"
                
            return True, f"Successfully copied {len(files_copied)} files to change directory"
            
        except Exception as e:
            return False, f"Error copying template files: {str(e)}"

    def modify_and_upload_logs(self) -> tuple[bool, str]:
        """
        Modify a random user's system in logs_table.xlsx using a system from Roles_table.xlsx.
        First copies template files to change folder, then modifies the copy.
        """
        try:
            # First copy template files to change directory
            copy_success, copy_message = self.copy_template_files()
            if not copy_success:
                return False, copy_message
            
            # Set up paths using change directory instead of template
            change_dir = Path("change")
            logs_file = change_dir / "logs_table.xlsx"
            roles_file = change_dir / "Roles_table.xlsx"

            # Ensure change directory exists (should already exist from copy)
            change_dir.mkdir(exist_ok=True)

            # Check for required files
            if not logs_file.exists() or not roles_file.exists():
                return False, "Required Excel files not found in change directory. Please ensure files were copied correctly."
            
            # Read the files
            try:
                logs_df = pd.read_excel(logs_file)
                roles_df = pd.read_excel(roles_file)
            except Exception as e:
                return False, f"Error reading Excel files: {str(e)}"
                
            if 'System' not in roles_df.columns or 'System' not in logs_df.columns:
                return False, "Required 'System' column not found in Excel files"
            
            # Get available systems and randomly select one
            available_systems = roles_df['System'].dropna().unique().tolist()
            if not available_systems:
                return False, "No systems found in Roles table"
            new_system = random.choice(available_systems)
            
            # Select a random user and update their system
            if len(logs_df) == 0:
                return False, "Logs table is empty"
                
            random_index = random.randrange(len(logs_df))
            old_system = logs_df.loc[random_index, 'System']
            logs_df.loc[random_index, 'System'] = new_system
            
            # Save modified file to both directories
            self.log_msg_purple("\nSaving modified files...")
            
            # Save to template directory (original location)
            logs_df.to_excel(logs_file, index=False)
            self.log_msg_purple(f"✓ Saved to template: {logs_file}")
            
            # Upload to blob storage
            blob_upload_success = self.upload_to_blob(
                local_file_path=logs_file,
                blob_name="logs_table.xlsx"
            )
            
            # Log the changes
            self.log_msg_purple("\nModification Summary:")
            self.log_msg_purple(f"• User Index: {random_index}")
            self.log_msg_purple(f"• Old System: {old_system}")
            self.log_msg_purple(f"• New System: {new_system}")
            self.log_msg_purple(f"• Blob Upload: {'✓ Success' if blob_upload_success else '⚠️ Failed'}")
            
            return True, f"Successfully modified logs_table.xlsx with new system assignment{' and uploaded to blob' if blob_upload_success else ''}"
            
        except Exception as e:
            return False, f"Error in modify_and_upload_logs: {str(e)}"
    
    def create_vector_store(self, project_client: AIProjectClient, files: list[Path], vector_name: str) -> None:
        """Create a vector store from a list of files."""
        try:
            self.log_msg_green(f"Creating vector store: {vector_name}")
            
            # Upload files to the project
            file_ids = []
            for file_path in files:
                if not file_path.exists():
                    self.log_msg_purple(f"Warning: File not found: {file_path}")
                    continue
                    
                self.log_msg_purple(f"Uploading {file_path.name}...")
                with open(file_path, "rb") as f:
                    response = project_client.agents.upload_file(f)
                    file_ids.append(response.file_id)
                    self.log_msg_green(f"Uploaded {file_path.name} with ID: {response.file_id}")
            
            if not file_ids:
                raise ValueError("No files were successfully uploaded")
            
            # Create the vector store
            vector_store = project_client.agents.create_vector_store(
                name=vector_name,
                file_ids=file_ids,
            )
            
            self.log_msg_green(f"Successfully created vector store with ID: {vector_store.id}")
            self.log_msg_green(f"Vector store contains {len(file_ids)} files")
            
            return vector_store
            
        except Exception as e:
            self.log_msg_purple(f"Error creating vector store: {str(e)}")
            raise
            
    def download_agent_files(self, project_client: AIProjectClient, thread_id: str, downloads_dir: str = None) -> None:
        """Download all files generated by the agent (code interpreter, etc.)."""
        try:
            messages = project_client.agents.messages.list(thread_id=thread_id)
            
            # Create downloads directory if it doesn't exist
            import os
            if downloads_dir is None:
                env = os.getenv("ENVIRONMENT", "local")
                downloads_dir = f"{'src/workshop/' if env == 'container' else ''}files"
            
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            
            # Get the latest agent message only (to avoid redownloading old files)
            latest_agent_message = None
            for message in messages:
                if message.role.value == "assistant":
                    latest_agent_message = message
                    break
            
            if not latest_agent_message:
                return  # No agent messages to process
            
            # Track downloaded file IDs to avoid duplicates
            downloaded_file_ids = set()
            
            # First, process file path annotations (primary method for code interpreter files)
            if hasattr(latest_agent_message, 'file_path_annotations') and latest_agent_message.file_path_annotations:
                for file_path_annotation in latest_agent_message.file_path_annotations:
                    file_id = file_path_annotation.file_path.file_id
                    
                    if file_id in downloaded_file_ids:
                        continue  # Skip if already downloaded
                    
                    # Get original filename from the annotation text if possible
                    annotation_text = file_path_annotation.text
                    if "/" in annotation_text:
                        original_filename = annotation_text.split("/")[-1]
                    else:
                        original_filename = f"{file_id}_annotation_file"
                    
                    local_path = os.path.join(downloads_dir, original_filename)
                    
                    try:
                        # Download file content from Azure AI
                        file_content_generator = project_client.agents.files.get_content(file_id=file_id)
                        file_content = b''.join(file_content_generator)
                        with open(local_path, "wb") as f:
                            f.write(file_content)
                        self.log_msg_green(f"Downloaded generated file: {local_path}")
                        downloaded_file_ids.add(file_id)
                    except Exception as e:
                        print(f"Error downloading file {file_id}: {e}")
            
            # Second, check content items for any files not caught by annotations
            if hasattr(latest_agent_message, 'content') and latest_agent_message.content:
                for content_item in latest_agent_message.content:
                    file_id = None
                    file_name = None
                    
                    # Check for different types of content
                    if hasattr(content_item, 'type'):
                        # Handle image_file type
                        if content_item.type == 'image_file' and hasattr(content_item, 'image_file'):
                            file_id = content_item.image_file.file_id
                            file_name = f"{file_id}_image.png"
                        
                        # Handle file_path type (for other files)
                        elif content_item.type == 'file_path' and hasattr(content_item, 'file_path'):
                            file_id = content_item.file_path.file_id
                            file_name = f"{file_id}_file"
                    
                    # Skip if no file found or already downloaded
                    if not file_id or file_id in downloaded_file_ids:
                        continue
                    
                    local_path = os.path.join(downloads_dir, file_name)
                    
                    try:
                        # Download file content from Azure AI
                        file_content_generator = project_client.agents.files.get_content(file_id=file_id)
                        file_content = b''.join(file_content_generator)
                        with open(local_path, "wb") as f:
                            f.write(file_content)
                        self.log_msg_green(f"Downloaded file: {local_path}")
                        downloaded_file_ids.add(file_id)
                    except Exception as e:
                        print(f"Error downloading file {file_id}: {e}")
            
        except Exception as e:
            print(f"Error handling file downloads: {e}")

    def create_vector_store(self, project_client: AIProjectClient, files: list[str], vector_name_name: str) -> None:
        """Upload a file to the project."""

        file_ids = []
        env = os.getenv("ENVIRONMENT", "local")
        prefix = "src/workshop/" if env == "container" else ""

        # Upload the files to Azure AI
        for file in files:
            file_path = Path(f"{prefix}{file}")
            self.log_msg_purple(f"Uploading file: {file_path}")
            with file_path.open("rb") as f:
                # Upload file using agents upload_file method
                uploaded_file = project_client.agents.upload_file(file=f, purpose="assistants")
                file_ids.append(uploaded_file.id)

        self.log_msg_purple("Creating the vector store")

        # Create a vector store  using the vector_stores.create_and_poll method
        vector_store = project_client.agents.create_vector_store_and_poll(
            file_ids=file_ids, name=vector_name_name
        )
        self.log_msg_purple(f"Vector store created: {vector_store.id}")
        return vector_store
