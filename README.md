# MCP server for Obsidian (harness-engineered fork)

MCP server to interact with Obsidian via the Local REST API community plugin.

> **Fork notice**
> This is a personal fork of [MarkusPfundstein/mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian), redesigned for use as a long-lived agent harness. The tool surface has been reshaped so the agent makes fewer mistakes by construction (instead of relying on long system-prompt rules to prevent them). See [What's different from upstream](#whats-different-from-upstream) below.
>
> Upstream is the source of truth for the underlying REST integration; changes here focus on agent ergonomics, safety gating, and token efficiency.

<a href="https://glama.ai/mcp/servers/3wko1bhuek"><img width="380" height="200" src="https://glama.ai/mcp/servers/3wko1bhuek/badge" alt="server for Obsidian MCP server" /></a>

## What's different from upstream

Reshaping was driven by [Anthropic's "Writing tools for agents"](https://www.anthropic.com/engineering/writing-tools-for-agents) — the goal is **make invalid states unrepresentable at the tool surface** rather than enforce them via prompt rules. Concretely:

### Safety gates

- **`patch_content (heading, replace)` is gated when the target heading has children.** Without `confirm_wipe=true`, the call is rejected with a redirect to `section_intro_patch`. This eliminates the most common destructive accident: replacing a heading's intro and silently wiping all sub-sections.
- **`delete_file` description and schema reflect that it is destructive and irreversible.** `confirm` is now an enum `[true]` so accidental defaults can't fire it. The description explicitly tells the agent not to use it as a workaround for failed writes.

### Heading-path leniency + healing

- **`patch_content` and `section_intro_patch` accept lenient heading paths.** Leading `#` and whitespace per segment are stripped, and partial paths like `Sub` or `Sub::Leaf` are auto-resolved to the full root-anchored path if the match is unique. Agents no longer need to construct `Top H1::Sub H2` from scratch.
- **On heading-path miss or ambiguity, the file's heading tree is appended to the error.** The agent gets the data it needs to self-correct on the next call instead of looping or escalating to deletion.

### New tools

- **`section_intro_patch`** — surgical edit of a heading's intro region (between the heading and its first child). Children are preserved. Marked PREFERRED in description for editing under any heading with children.
- **`list_headings`** — returns the heading tree of a single file as an indented outline. Cheap proactive recon before patching, typically 1–5% of full-file token cost.
- **`get_section_content`** — returns the content under a single heading (heading line + body + descendants). Replaces full-file reads when only one section is needed.

### Token efficiency

- **JSON-wrapped read responses changed to plain text where appropriate.** `get_file_contents` returned `json.dumps(content)`, which double-encoded the markdown body. Now returns raw markdown.
- **`ensure_ascii=False` on remaining JSON responses.** Korean/CJK content is no longer Unicode-escaped — significant token savings for non-English vaults.
- **`limit` parameters added to listing and search tools** (`list_files_in_vault`, `list_files_in_dir`, `simple_search`, `complex_search`). Truncation appends a hint suggesting how to narrow the query.
- **`get_file_contents` line slicing**: `start_line` / `line_limit` parameters for partial reads of large files, plus a warning when a single line exceeds 5000 chars.
- **`batch_get_file_contents` total-char cap** (`max_total_chars`, default 50000) with a skip notice when reached.

### Removed / restricted

- `put_content` (full-file overwrite) is intentionally **not registered**. Use `append_content` (creates if missing) or `section_intro_patch` instead. Removing the surface eliminates the "rewrite the whole file" misuse pattern.
- `get_periodic_note`, `get_recent_periodic_notes`, and `get_recent_changes` are **not registered** — the periodic-note workflow (daily/weekly/monthly/quarterly/yearly notes) and ad-hoc "recent changes" lookups are unused in this harness. All three classes remain in `tools.py`; re-enable by uncommenting one line in `server.py`.
- `complex_search` description trimmed (examples were duplicated between the body and the parameter description).

### What stays the same

- All upstream tools that were not explicitly changed above keep their existing behavior and signatures.
- The underlying REST integration in `obsidian.py` is unchanged in intent — the helpers in `markdown_section.py` parse markdown locally to enable the leniency / gating features without relying on REST endpoints that don't exist.

## Components

### Tools

- **list_files_in_vault** — Lists files and directories in the vault root (alphabetically sorted, `limit`-truncated).
- **list_files_in_dir** — Lists files and directories in a specific subdirectory.
- **get_file_contents** — Returns a single file's content. Optional `start_line` / `line_limit` for slicing.
- **get_section_content** — Returns the content under one heading (heading + body + descendants). For large files, prefer this over `get_file_contents`.
- **list_headings** — Returns a file's heading tree as an indented outline. Cheap recon before patching.
- **batch_get_file_contents** — Concatenates multiple files with `# {filepath}` headers, capped by `max_total_chars`.
- **simple_search** — Text search across the vault, `limit`-truncated.
- **complex_search** — JsonLogic search (glob, regexp on path/content), `limit`-truncated.
- **append_content** — Appends content to a file (creates if missing).
- **patch_content** — Inserts content relative to a heading / block ref / frontmatter field. Lenient heading paths, healing on miss, `confirm_wipe` gate on destructive `(heading, replace)` calls.
- **section_intro_patch** — Surgical edit of a heading's intro region only. Preserves child sub-headings. **Preferred** for any edit under a heading with children.
- **delete_file** — Permanently removes a file. `confirm: true` required. Use only on explicit user request.

### Example prompts

Its good to first instruct Claude to use Obsidian. Then it will always call the tool.

The use prompts like this:
- Get the contents of the last architecture call note and summarize them
- Search for all files where Azure CosmosDb is mentioned and quickly explain to me the context in which it is mentioned
- Summarize the last meeting notes and put them into a new note 'summary meeting.md'. Add an introduction so that I can send it via email.

## Configuration

### Obsidian REST API Key

There are two ways to configure the environment with the Obsidian REST API Key. 

1. Add to server config (preferred)

```json
{
  "mcp-obsidian": {
    "command": "uvx",
    "args": [
      "mcp-obsidian"
    ],
    "env": {
      "OBSIDIAN_API_KEY": "<your_api_key_here>",
      "OBSIDIAN_HOST": "<your_obsidian_host>",
      "OBSIDIAN_PORT": "<your_obsidian_port>"
    }
  }
}
```
Sometimes Claude has issues detecting the location of uv / uvx. You can use `which uvx` to find and paste the full path in above config in such cases.

2. Create a `.env` file in the working directory with the following required variables:

```
OBSIDIAN_API_KEY=your_api_key_here
OBSIDIAN_HOST=your_obsidian_host
OBSIDIAN_PORT=your_obsidian_port
```

Note:
- You can find the API key in the Obsidian plugin config
- Default port is 27124 if not specified
- Default host is 127.0.0.1 if not specified

## Quickstart

### Install

#### Obsidian REST API

You need the Obsidian REST API community plugin running: https://github.com/coddingtonbear/obsidian-local-rest-api

Install and enable it in the settings and copy the api key.

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`

On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-obsidian": {
      "command": "uv",
      "args": [
        "--directory",
        "<dir_to>/mcp-obsidian",
        "run",
        "mcp-obsidian"
      ],
      "env": {
        "OBSIDIAN_API_KEY": "<your_api_key_here>",
        "OBSIDIAN_HOST": "<your_obsidian_host>",
        "OBSIDIAN_PORT": "<your_obsidian_port>"
      }
    }
  }
}
```
</details>

> **Note**: this fork is not published to PyPI, so the upstream `uvx mcp-obsidian` published-server install does not apply. Use the development configuration above (`uv --directory <path> run mcp-obsidian`) pointing at your local clone of this fork.

## Development

### Building

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-obsidian run mcp-obsidian
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.

You can also watch the server logs with this command:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-mcp-obsidian.log
```
