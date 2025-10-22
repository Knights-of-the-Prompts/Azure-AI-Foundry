#!/usr/bin/env python3
"""
Setup verification script for the UI app.
This script checks if all required environment variables and dependencies are configured.
"""

import os
import sys
from pathlib import Path


def check_env_file():
    """Check if .env file exists"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return False, ".env file not found"
    return True, ".env file exists"


def check_env_variables():
    """Check if required environment variables are set"""
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = {
        "PROJECT_ENDPOINT": "Azure AI Foundry project endpoint URL",
        "AZURE_SUBSCRIPTION_ID": "Azure subscription ID",
        "AZURE_RESOURCE_GROUP_NAME": "Azure resource group name",
        "AZURE_PROJECT_NAME": "Azure AI Foundry project name",
        "AGENT_MODEL_DEPLOYMENT_NAME": "Model deployment name (e.g., gpt-4o)"
    }
    
    missing = []
    configured = []
    
    for var, description in required_vars.items():
        value = os.environ.get(var)
        if not value or value.startswith("<"):
            missing.append((var, description))
        else:
            configured.append((var, description))
    
    return configured, missing


def check_azure_auth():
    """Check if user is authenticated with Azure"""
    import subprocess
    try:
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, "Azure authentication successful"
        else:
            return False, "Not authenticated with Azure"
    except FileNotFoundError:
        return False, "Azure CLI not installed"
    except Exception as e:
        return False, f"Error checking Azure auth: {e}"


def check_dependencies():
    """Check if required Python packages are installed"""
    required_packages = [
        ("flask", "flask"),
        ("azure.ai.projects", "azure.ai.projects"),
        ("azure.ai.agents", "azure.ai.agents"),
        ("azure.identity", "azure.identity"),
        ("dotenv", "python-dotenv"),
        ("aiosqlite", "aiosqlite"),
        ("pandas", "pandas"),
        ("markdown", "markdown"),
        ("bleach", "bleach")
    ]
    
    missing = []
    installed = []
    
    for import_name, package_name in required_packages:
        try:
            __import__(import_name.replace("-", "_"))
            installed.append(package_name)
        except ImportError:
            missing.append(package_name)
    
    return installed, missing


def print_section(title, symbol="="):
    """Print a formatted section header"""
    print(f"\n{symbol * 70}")
    print(f"{title}")
    print(f"{symbol * 70}")


def main():
    """Run all checks and display results"""
    print_section("Azure AI Foundry UI App - Setup Verification", "=")
    
    all_checks_passed = True
    
    # Check .env file
    print_section("1. Environment File Check", "-")
    env_exists, env_msg = check_env_file()
    if env_exists:
        print(f"✓ {env_msg}")
    else:
        print(f"✗ {env_msg}")
        print("\n  Solution:")
        print("    cp .env.example .env")
        print("    # Then edit .env with your actual values")
        all_checks_passed = False
    
    # Check environment variables
    if env_exists:
        print_section("2. Environment Variables Check", "-")
        configured, missing = check_env_variables()
        
        if configured:
            print(f"✓ Configured variables ({len(configured)}):")
            for var, desc in configured:
                print(f"    - {var}")
        
        if missing:
            print(f"\n✗ Missing or incomplete variables ({len(missing)}):")
            for var, desc in missing:
                print(f"    - {var}: {desc}")
            print("\n  Solution: Edit .env file and set these variables")
            print("  See DEBUG_GUIDE.md for detailed instructions")
            all_checks_passed = False
    
    # Check Azure authentication
    print_section("3. Azure Authentication Check", "-")
    auth_ok, auth_msg = check_azure_auth()
    if auth_ok:
        print(f"✓ {auth_msg}")
    else:
        print(f"✗ {auth_msg}")
        print("\n  Solution:")
        print("    az login --use-device-code")
        all_checks_passed = False
    
    # Check dependencies
    print_section("4. Python Dependencies Check", "-")
    installed, missing_deps = check_dependencies()
    
    if installed:
        print(f"✓ Installed packages ({len(installed)}):")
        for pkg in installed[:5]:  # Show first 5
            print(f"    - {pkg}")
        if len(installed) > 5:
            print(f"    ... and {len(installed) - 5} more")
    
    if missing_deps:
        print(f"\n✗ Missing packages ({len(missing_deps)}):")
        for pkg in missing_deps:
            print(f"    - {pkg}")
        print("\n  Solution:")
        print("    pip install -r requirements.txt")
        all_checks_passed = False
    
    # Final summary
    print_section("Summary", "=")
    if all_checks_passed:
        print("✓ All checks passed! You can run the UI app:")
        print("\n    python ui_app.py")
        print("\n  Then open: http://localhost:5000")
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        print("\n  For detailed help, see:")
        print("    - DEBUG_GUIDE.md")
        print("    - docs/docs/getting-started.md")
    
    print("=" * 70 + "\n")
    
    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())
