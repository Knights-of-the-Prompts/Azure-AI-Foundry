# UI App Setup Examples

This document provides examples of the error messages and setup process for the UI app.

## Example 1: Missing Environment Variables

When you try to run `ui_app.py` without a `.env` file, you'll see:

```
======================================================================
ERROR: Missing required environment variables!
======================================================================

The following environment variables are not set:
  - PROJECT_ENDPOINT
  - AZURE_SUBSCRIPTION_ID
  - AZURE_RESOURCE_GROUP_NAME
  - AZURE_PROJECT_NAME

Please create a .env file in src/workshop/ with these variables.
You can use .env.example as a template:
  cp .env.example .env

For detailed setup instructions, see DEBUG_GUIDE.md
======================================================================
```

**Solution:** Create a `.env` file from the template:
```bash
cp .env.example .env
# Then edit .env with your actual Azure credentials
```

## Example 2: Running Setup Verification

The `check_setup.py` script performs comprehensive verification:

```bash
$ python check_setup.py

======================================================================
Azure AI Foundry UI App - Setup Verification
======================================================================

----------------------------------------------------------------------
1. Environment File Check
----------------------------------------------------------------------
✓ .env file exists

----------------------------------------------------------------------
2. Environment Variables Check
----------------------------------------------------------------------
✓ Configured variables (5):
    - PROJECT_ENDPOINT
    - AZURE_SUBSCRIPTION_ID
    - AZURE_RESOURCE_GROUP_NAME
    - AZURE_PROJECT_NAME
    - AGENT_MODEL_DEPLOYMENT_NAME

----------------------------------------------------------------------
3. Azure Authentication Check
----------------------------------------------------------------------
✗ Not authenticated with Azure

  Solution:
    az login --use-device-code

----------------------------------------------------------------------
4. Python Dependencies Check
----------------------------------------------------------------------
✓ Installed packages (9):
    - flask
    - azure.ai.projects
    - azure.ai.agents
    - azure.identity
    - python-dotenv
    ... and 4 more

======================================================================
Summary
======================================================================
✗ Some checks failed. Please fix the issues above.

  For detailed help, see:
    - DEBUG_GUIDE.md
    - docs/docs/getting-started.md
======================================================================
```

## Example 3: Successful Startup

When all requirements are met, the app starts successfully:

```bash
$ python ui_app.py

Using full project endpoint: https://your-resource.services.ai.azure.com/api/projects/your-project
 * Serving Flask app 'ui_app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.1.1.127:5000
Press CTRL+C to quit
```

Then access the UI at: **http://localhost:5000**

## Example 4: UI Interface

The Contoso Sales AI Agent UI includes:

1. **Header Section**
   - App title and description
   - Agent icon (CA)

2. **Control Panel**
   - Text area for entering questions
   - "Start Agent" button - Initialize the AI agent
   - "Submit" button - Send queries (enabled after starting agent)
   - "Stop Agent" button - Clean up resources

3. **Response Area**
   - Displays agent responses with formatted HTML
   - Shows charts and visualizations
   - Real-time status updates

4. **Sample Questions**
   - "What are the total sales by region?"
   - "Show me the top 5 products by revenue"
   - "Create a chart of monthly sales trends"
   - "What is the average order value?"

## Example 5: VS Code Debug Configuration

Three debug configurations are available in VS Code:

1. **Python Debugger: Current File**
   - Debugs the currently open Python file
   - Good for debugging individual modules

2. **Python Debugger: UI App**
   - Launches ui_app.py with proper working directory
   - Standard Flask mode (debug=off)

3. **Python Debugger: UI App (Debug Mode)**
   - Launches with Flask debug mode enabled
   - Auto-reloads on code changes
   - Detailed error pages

**To use:**
1. Open Run and Debug panel (Ctrl+Shift+D or Cmd+Shift+D)
2. Select desired configuration from dropdown
3. Press F5 or click the green play button
4. Set breakpoints in your code
5. Interact with the UI to hit breakpoints

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| `KeyError: 'PROJECT_ENDPOINT'` | Create `.env` file from `.env.example` |
| Port 5000 already in use | Change `PORT` in `.env` or kill process on port 5000 |
| Azure authentication error | Run `az login --use-device-code` |
| Template not found | Check that `templates/` directory exists |
| Dependencies missing | Run `pip install -r requirements.txt` |
| Agent initialization timeout | Verify Azure credentials and model deployment |

## Next Steps

1. ✓ Complete setup using `check_setup.py`
2. ✓ Configure `.env` file with your credentials
3. ✓ Run `python ui_app.py`
4. ✓ Open http://localhost:5000 in your browser
5. Click "Start Agent" and wait for initialization
6. Enter your questions and get AI-powered insights!

For more details, see:
- [DEBUG_GUIDE.md](DEBUG_GUIDE.md) - Comprehensive debugging guide
- [README.md](README.md) - Workshop overview
- [../../docs/docs/getting-started.md](../../docs/docs/getting-started.md) - Full workshop setup
