#!/usr/bin/env python3
"""Gemini MCP Server — exposes Google Gemini as a tool for Claude Code agents."""

import json
import os
import sys
from typing import Any

# MCP protocol over stdio
def send_response(id: Any, result: dict):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()

def send_error(id: Any, code: int, message: str):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()

def read_message() -> dict:
    """Read a JSON-RPC message from stdin (Content-Length framing)."""
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip().lower()] = val.strip()

    content_length = int(headers.get("content-length", 0))
    if content_length == 0:
        return {}

    body = sys.stdin.read(content_length)
    return json.loads(body)


TOOLS = [
    {
        "name": "gemini_review_ui",
        "description": "Send HTML/CSS code to Google Gemini for UI/UX review. Gemini analyzes the design for accessibility, responsiveness, visual hierarchy, RTL support, and modern UI best practices. Returns Gemini's review comments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The HTML/CSS code to review"
                },
                "context": {
                    "type": "string",
                    "description": "What this UI is for (e.g., 'Admin leave management dashboard for Saudi HR platform')"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on: 'accessibility', 'responsive', 'rtl', 'visual', or 'all'",
                    "default": "all"
                }
            },
            "required": ["code", "context"]
        }
    },
    {
        "name": "gemini_suggest_ui",
        "description": "Ask Google Gemini to suggest UI improvements or generate component ideas. Provide a description of what you need and Gemini returns HTML/CSS suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What UI component or improvement you need"
                },
                "design_system": {
                    "type": "string",
                    "description": "CSS variables or design tokens to follow",
                    "default": ""
                },
                "constraints": {
                    "type": "string",
                    "description": "Constraints like 'Arabic-first, mobile-first, dark mode support, vanilla CSS only'",
                    "default": "Arabic-first, mobile-first, dark mode via CSS variables, vanilla HTML/CSS/JS only, Inter font"
                }
            },
            "required": ["description"]
        }
    }
]


def call_gemini(prompt: str) -> str:
    """Call Google Gemini API."""
    api_key = os.environ.get("GOOGLE_AI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GOOGLE_AI_API_KEY or GEMINI_API_KEY environment variable not set"

    import urllib.request
    import urllib.error

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
        }
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"Gemini API error ({e.code}): {body}"
    except Exception as e:
        return f"Gemini API error: {str(e)}"


def handle_tool_call(name: str, args: dict) -> str:
    if name == "gemini_review_ui":
        prompt = f"""You are a senior UI/UX reviewer for a Saudi HR AI platform called Krew.

Review the following HTML/CSS code. Focus on: {args.get('focus', 'all')}

Context: {args['context']}

Requirements:
- Arabic-first (RTL support)
- Mobile-first responsive design
- Dark mode support via CSS variables
- WCAG AA accessibility
- Clean Saudi corporate aesthetic

Code to review:
```html
{args['code']}
```

Provide your review as:
1. **Score**: X/10
2. **Strengths**: What's done well
3. **Issues**: Specific problems with line references
4. **Suggestions**: Concrete improvements with code snippets
5. **Accessibility**: WCAG issues found
6. **RTL Check**: Arabic/RTL specific issues"""
        return call_gemini(prompt)

    elif name == "gemini_suggest_ui":
        prompt = f"""You are a senior UI designer for a Saudi HR AI platform called Krew.

Generate HTML/CSS for: {args['description']}

Design system to follow:
{args.get('design_system', 'Use CSS variables: --accent: #4f46e5, --green: #16a34a, --red: #dc2626, --orange: #ea580c, --surface: #ffffff, --bg: #f5f5f4, --text: #1a1a1a, --border: #e5e5e5, --radius: 12px, --radius-sm: 8px')}

Constraints: {args.get('constraints', 'Arabic-first, mobile-first, dark mode via CSS variables, vanilla HTML/CSS/JS only, Inter font')}

Return:
1. Complete HTML/CSS code (self-contained, inline styles)
2. Dark mode variant (using .dark class)
3. Responsive breakpoints (360px, 768px, 1200px)
4. Notes on RTL considerations"""
        return call_gemini(prompt)

    return f"Unknown tool: {name}"


def main():
    """Main MCP server loop."""
    while True:
        try:
            msg = read_message()
            if not msg:
                break

            method = msg.get("method", "")
            id = msg.get("id")

            if method == "initialize":
                send_response(id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "gemini-mcp", "version": "1.0.0"}
                })

            elif method == "notifications/initialized":
                pass  # No response needed

            elif method == "tools/list":
                send_response(id, {"tools": TOOLS})

            elif method == "tools/call":
                tool_name = msg["params"]["name"]
                tool_args = msg["params"].get("arguments", {})
                result = handle_tool_call(tool_name, tool_args)
                send_response(id, {
                    "content": [{"type": "text", "text": result}]
                })

            elif id is not None:
                send_error(id, -32601, f"Unknown method: {method}")

        except Exception as e:
            if id is not None:
                send_error(id, -32603, str(e))


if __name__ == "__main__":
    main()
