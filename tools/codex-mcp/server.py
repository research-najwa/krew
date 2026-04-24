#!/usr/bin/env python3
"""OpenAI Codex MCP Server — exposes OpenAI models as a code review tool for Claude Code agents."""

import json
import os
import sys
from typing import Any


def send_response(id: Any, result: dict):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()


def send_error(id: Any, code: int, message: str):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()


def read_message() -> dict:
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
        "name": "codex_review",
        "description": "Send code to OpenAI for an independent code review. OpenAI analyzes for bugs, security issues, performance problems, best practices, and suggests fixes. Returns OpenAI's review comments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to review"
                },
                "context": {
                    "type": "string",
                    "description": "What this code does (e.g., 'FastAPI endpoint for approving leave requests in a Saudi HR platform')"
                },
                "language": {
                    "type": "string",
                    "description": "Programming language",
                    "default": "python"
                },
                "focus": {
                    "type": "string",
                    "description": "Review focus: 'security', 'performance', 'bugs', 'best-practices', 'all'",
                    "default": "all"
                }
            },
            "required": ["code", "context"]
        }
    },
    {
        "name": "codex_suggest_fix",
        "description": "Send buggy or problematic code to OpenAI and get a suggested fix with explanation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code that needs fixing"
                },
                "issue": {
                    "type": "string",
                    "description": "Description of the problem or bug"
                },
                "constraints": {
                    "type": "string",
                    "description": "Constraints for the fix (e.g., 'must use async SQLAlchemy, must maintain backwards compatibility')",
                    "default": ""
                }
            },
            "required": ["code", "issue"]
        }
    }
]


def call_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY environment variable not set"

    import urllib.request
    import urllib.error

    url = "https://api.openai.com/v1/chat/completions"

    payload = json.dumps({
        "model": "codex-mini-latest",
        "messages": [
            {"role": "system", "content": "You are an expert code reviewer specializing in Python, FastAPI, async SQLAlchemy, and AI agent systems. You review code for a Saudi HR AI platform called Krew. Be thorough, specific, and provide concrete fixes."},
            {"role": "user", "content": prompt}
        ],
        "max_completion_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    })

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"OpenAI API error ({e.code}): {body}"
    except Exception as e:
        return f"OpenAI API error: {str(e)}"


def handle_tool_call(name: str, args: dict) -> str:
    if name == "codex_review":
        prompt = f"""Review the following {args.get('language', 'python')} code. Focus on: {args.get('focus', 'all')}

Context: {args['context']}

This is for Krew, a Saudi HR AI platform. Key considerations:
- Async Python / FastAPI / SQLAlchemy 2.0
- Multi-tenant (must filter by tenant_id)
- Handles PII (national_id, salary, GOSI data)
- Saudi business rules (weekend = Fri/Sat, Hijri calendar awareness)
- Bilingual Arabic/English support
- AI agents with tool-use loops (Claude API)

Code to review:
```{args.get('language', 'python')}
{args['code']}
```

Provide:
1. **Critical Issues** — Bugs, security vulnerabilities, data integrity risks
2. **Performance** — N+1 queries, blocking I/O, missing indexes
3. **Best Practices** — Type hints, error handling, async patterns
4. **Security** — SQL injection, PII exposure, auth bypass, tenant isolation
5. **Suggested Fixes** — Concrete code snippets for each issue"""
        return call_openai(prompt)

    elif name == "codex_suggest_fix":
        prompt = f"""Fix this code.

Issue: {args['issue']}

Constraints: {args.get('constraints', 'Maintain async SQLAlchemy patterns, keep existing API contract')}

Code:
```
{args['code']}
```

Provide:
1. **Root Cause** — Why this is broken
2. **Fixed Code** — Complete corrected version
3. **Explanation** — What changed and why
4. **Test Case** — How to verify the fix"""
        return call_openai(prompt)

    return f"Unknown tool: {name}"


def main():
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
                    "serverInfo": {"name": "codex-mcp", "version": "1.0.0"}
                })

            elif method == "notifications/initialized":
                pass

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
