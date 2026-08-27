@echo off
rem Start the ShyBoard MCP bridge. Keep stdout reserved for MCP protocol traffic.
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0mcp_server.py"
