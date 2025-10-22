# UI App Debugging Guide

This guide helps you run and debug the `ui_app.py` Flask application for the Contoso Sales Analysis Agent.

## Prerequisites

1. **Python 3.12+** installed
2. **Azure AI Foundry Project** configured
3. **Azure Authentication** completed (`az login --use-device-code`)

## Setup Instructions

### 1. Install Dependencies

```bash
cd src/workshop
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the `src/workshop/` directory:

```bash
cp .env.example .env
```

Then edit the `.env` file with your actual values. You can find these values in:
- **Azure Portal**: Navigate to your Resource Group → Azure AI Foundry Project
- **Azure AI Foundry Portal**: Project Settings → Connection String

Required variables:
- `AZURE_SUBSCRIPTION_ID`: Your Azure subscription ID
- `AZURE_RESOURCE_GROUP_NAME`: Resource group name containing your AI Foundry project
- `AZURE_PROJECT_NAME`: Your Azure AI Foundry project name
- `PROJECT_ENDPOINT`: Full project endpoint URL
- `AGENT_MODEL_DEPLOYMENT_NAME`: Model deployment name (e.g., `gpt-4o`)

For detailed instructions, see: [Getting Started Guide](../../docs/docs/getting-started.md)

### 3. Verify Azure Authentication

Ensure you're logged in to Azure:

```bash
az login --use-device-code
az account show
```

## Running the Application

### Basic Run

```bash
cd src/workshop
python ui_app.py
```

The application will start on `http://0.0.0.0:5000` (or the port specified in your `.env` file).

### Access the UI

Open your browser and navigate to:
```
http://localhost:5000
```

## Debugging

### VS Code Debug Configuration

Add this configuration to your `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: UI App",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/src/workshop/ui_app.py",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}/src/workshop",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/src/workshop"
            },
            "justMyCode": false
        }
    ]
}
```

### Common Issues and Solutions

#### 1. KeyError: 'PROJECT_ENDPOINT'

**Problem**: Missing or incorrectly configured `.env` file.

**Solution**: 
- Ensure `.env` file exists in `src/workshop/`
- Verify all required variables are set
- Check that `python-dotenv` is installed

#### 2. Azure Authentication Error

**Problem**: Not authenticated with Azure or wrong subscription.

**Solution**:
```bash
az login --use-device-code
az account set --subscription <SUBSCRIPTION_ID>
```

#### 3. Module Import Errors

**Problem**: Dependencies not installed or wrong Python environment.

**Solution**:
```bash
pip install -r requirements.txt
```

#### 4. Template Not Found

**Problem**: Flask cannot find `index.html` template.

**Solution**: 
- Check that `templates/` directory exists in `src/workshop/`
- Verify the fallback path in `ui_app.py` line 39 is correct
- The app tries to load from: `src/samples/create-mcp-foundry-agents/templates/index.html`

#### 5. Port Already in Use

**Problem**: Another application is using port 5000.

**Solution**:
```bash
# Set a different port in .env
PORT=5001

# Or kill the process using port 5000
lsof -ti:5000 | xargs kill -9
```

## Debugging Tips

1. **Enable Flask Debug Mode**: Set `debug=True` in the `app.run()` call (line 121)
2. **Check Console Output**: The app prints detailed status messages
3. **Test API Endpoints Manually**:
   ```bash
   # Start the agent
   curl -X POST http://localhost:5000/api/start
   
   # Send a query
   curl -X POST http://localhost:5000/api/query \
     -H "Content-Type: application/json" \
     -d '{"query": "What are the total sales?"}'
   
   # Stop the agent
   curl -X POST http://localhost:5000/api/stop
   ```

4. **Check Logs**: Look for error messages in the terminal where you ran `python ui_app.py`

## Architecture Overview

The UI app consists of:

1. **Flask Server** (`ui_app.py`): Handles HTTP requests
2. **Background Event Loop**: Runs async Azure AI Agent operations
3. **Agent Service Integration** (`main.py`): Communicates with Azure AI Foundry
4. **Database Layer** (`sales_data.py`): SQLite database queries

### API Endpoints

- `GET /`: Serve the main UI
- `POST /api/start`: Initialize the agent
- `POST /api/query`: Send user query to the agent
- `POST /api/stop`: Clean up agent resources

## Next Steps

After successfully running the UI:
1. Click "Start Agent" in the UI
2. Wait for initialization (may take 10-30 seconds)
3. Enter questions about sales data
4. View agent responses with charts and analysis

For more information, see the [workshop documentation](../../docs/docs/introduction.md).
