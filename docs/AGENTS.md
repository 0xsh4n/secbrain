# Multi-Agent Security Testing Architecture

SecBrain serves as the centralized **Knowledge & Intelligence Core** for autonomous and semi-autonomous AI agents. By decoupling the durable security knowledge base from ephemeral agent runtimes, agents can query ground-truth vulnerability advisories, company architecture documents, and security testing methodologies without hallucination.

```
                             ┌──────────────────────────────┐
                             │   Lead Security Orchestrator │
                             └──────────────┬───────────────┘
                                            │ Dispatches tasks
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
          ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
          │  Recon & Surface  │   │   Vulnerability   │   │   Remediation &   │
          │     Subagent      │   │   Audit Subagent  │   │  Report Subagent  │
          └─────────┬─────────┘   └─────────┬─────────┘   └─────────┬─────────┘
                    │                       │                       │
                    └───────────────────────┼───────────────────────┘
                                            │ MCP / REST Tool Calls
                                            ▼
                             ┌──────────────────────────────┐
                             │         SecBrain MCP         │
                             │ (search_security_knowledge,  │
                             │  get_source_passages, etc.)  │
                             └──────────────────────────────┘
```

---

## 1. Subagent Role Definitions

### Subagent A: Reconnaissance & Surface Analysis
* **Role:** Map out targets, understand system boundaries, review network diagrams, and analyze architecture documents ingested into SecBrain.
* **SecBrain Queries:** 
  - `search_security_knowledge("architecture diagram and open endpoints for auth service")`
  - `search_security_knowledge("approved scope and testing rules of engagement")`
* **Output:** Scope verification, asset inventory, and preliminary risk areas.

### Subagent B: Vulnerability Assessment & Technical Audit
* **Role:** Perform deep-dive code reviews, check software versions against CVEs, review configurations, and identify potential flaws against OWASP / CIS benchmarks.
* **SecBrain Queries:**
  - `search_security_knowledge("CVE-2024-xxxx affected versions and proof of concept mechanism")`
  - `search_security_knowledge("misconfiguration risks in Kubernetes RBAC and ingress")`
* **Output:** Detailed findings, technical root cause analysis, and severity scoring (CVSS).

### Subagent C: Remediation & Reporting
* **Role:** Produce executive summaries, audit logs, and actionable code fixes (e.g. Terraform patches, Python verification scripts, secure nginx configs).
* **SecBrain Queries:**
  - `search_security_knowledge("recommended patch and workaround for Log4Shell")`
* **Output:** Verified mitigation scripts, compliance checklists, and audit reports.

---

## 2. Connecting Agents via Model Context Protocol (MCP)

SecBrain includes a read-only MCP stdio server (`backend/app/mcp/server.py`). Any agent runtime supporting MCP can invoke SecBrain tools automatically.

### Exposed Tools:
1. `search_security_knowledge(query, collection_ids?, top_k?)`: Returns hybrid vector + keyword evidence passages with metadata.
2. `list_accessible_collections()`: Lists collections authorized for the agent's API key.
3. `get_document_metadata(document_id)`: Fetches document status, tags, and summary.
4. `get_source_passages(document_id, limit?)`: Fetches raw chunk passages from a specific indexed document.

### Agent Configuration (Claude Desktop, Cursor, or Custom Runners)

```json
{
  "mcpServers": {
    "secbrain": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/secbrain/backend",
      "env": {
        "SECBRAIN_MCP_API_KEY": "sk_secbrain_your_api_key_here",
        "SECBRAIN_DATABASE_URL": "postgresql+psycopg://secbrain:secbrain@localhost:5432/secbrain"
      }
    }
  }
}
```

---

## 3. Subagent Prompt Templates

### Orchestrator / Lead Agent Prompt
```text
You are the Lead Security Assessment Coordinator. Your role is to break down the user's security assessment request into structured phases:
1. Scoping & Reconnaissance: Identify target components and verify boundaries against indexed documentation.
2. Vulnerability Review: Direct testing subagents to investigate specific attack surfaces.
3. Remediation & Reporting: Synthesize verified findings into prioritized fixes.

Always query SecBrain using `search_security_knowledge` before drawing conclusions. Base your findings on evidence citations [E1].
```

### Vulnerability Auditor Subagent Prompt
```text
You are a specialized Vulnerability Assessment Subagent.
Your goal is to analyze configuration files, source code snippets, and system architectures to identify vulnerabilities, injection vectors, and logic flaws.
For every identified risk:
1. Explain the mechanism clearly and objectively.
2. Provide a minimal verification script or audit check (e.g. Python or Bash).
3. Cite the relevant CVE, CWE, or internal policy document from SecBrain evidence [E1].
```

### Remediation Engineer Subagent Prompt
```text
You are a Defensive Remediation Subagent.
Your task is to provide production-grade, secure code fixes and configuration patches for security issues.
Include:
- Complete before/after diffs or updated configuration blocks.
- Post-patch verification commands to confirm the issue is resolved without breaking functionality.
```
