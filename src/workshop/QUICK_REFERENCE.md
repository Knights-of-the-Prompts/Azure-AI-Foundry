# UI App Quick Reference Card

## 🚀 Quick Start (30 seconds)

```bash
cd src/workshop
cp .env.example .env          # 1. Create config
# Edit .env with your values  # 2. Configure
python check_setup.py         # 3. Verify
python ui_app.py              # 4. Run!
# Open http://localhost:5000  # 5. Use!
```

## 📋 Essential Commands

| Task | Command |
|------|---------|
| **Verify setup** | `python check_setup.py` |
| **Run app** | `python ui_app.py` |
| **Install deps** | `pip install -r requirements.txt` |
| **Azure login** | `az login --use-device-code` |
| **Check Azure** | `az account show` |
| **Change port** | Edit `PORT` in `.env` |

## 🔧 Required Environment Variables

```bash
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
AZURE_RESOURCE_GROUP_NAME=<your-resource-group>
AZURE_PROJECT_NAME=<your-project-name>
PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AGENT_MODEL_DEPLOYMENT_NAME=gpt-4o
```

## 🐛 Debug in VS Code

1. Press `F5` or go to Run and Debug
2. Select "Python Debugger: UI App"
3. Set breakpoints
4. Interact with UI

## ❌ Common Issues

| Error | Fix |
|-------|-----|
| Missing env vars | `cp .env.example .env` and edit |
| Port in use | Change `PORT` in `.env` |
| Not authenticated | `az login --use-device-code` |
| Deps missing | `pip install -r requirements.txt` |

## 📡 API Endpoints

- `GET /` - UI homepage
- `POST /api/start` - Initialize agent
- `POST /api/query` - Send user query
- `POST /api/stop` - Clean up agent

## 💡 Example Queries

Once the agent is started, try:

- "What are the total sales by region?"
- "Show me top 5 products by revenue"
- "Create a chart of monthly sales trends"
- "What is the average order value?"
- "Show sales for product category X"

## 📚 Documentation

| File | Purpose |
|------|---------|
| `DEBUG_GUIDE.md` | Comprehensive debugging guide |
| `SETUP_EXAMPLES.md` | Example outputs and scenarios |
| `README.md` | Workshop overview |
| `.env.example` | Environment variable template |

## 🔍 Verification Checklist

- [ ] `.env` file created and configured
- [ ] Azure authentication completed (`az login`)
- [ ] Dependencies installed
- [ ] Port 5000 available
- [ ] Azure AI Foundry project accessible
- [ ] Model deployment exists

## 🎯 Typical Workflow

1. **First Time**
   ```bash
   cp .env.example .env
   # Edit .env
   az login --use-device-code
   pip install -r requirements.txt
   python check_setup.py
   ```

2. **Every Run**
   ```bash
   python ui_app.py
   # Open http://localhost:5000
   # Click "Start Agent"
   # Enter questions
   ```

3. **Debugging**
   - Use VS Code debugger (F5)
   - Check console for errors
   - Review agent logs
   - Test API endpoints with curl

## 🆘 Get Help

1. Run `python check_setup.py` for diagnostics
2. Check `DEBUG_GUIDE.md` for detailed help
3. Review error messages in terminal
4. Verify Azure credentials and permissions
5. Check Azure AI Foundry portal for service status

---

**Pro Tip:** Keep `check_setup.py` running regularly to catch configuration issues early!
