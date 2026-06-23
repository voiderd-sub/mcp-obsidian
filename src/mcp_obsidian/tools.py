from collections.abc import Sequence
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import json
import os
from . import obsidian
from . import markdown_section

api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")

if api_key == "":
    raise ValueError(f"OBSIDIAN_API_KEY environment variable required. Working directory: {os.getcwd()}")

TOOL_LIST_FILES_IN_VAULT = "obsidian_list_files_in_vault"
TOOL_LIST_FILES_IN_DIR = "obsidian_list_files_in_dir"

class ToolHandler():
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()
    
class ListFilesInVaultToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_VAULT)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Returns ROOT directory listing only (alphabetically sorted). "
                "For a specific subdirectory use obsidian_list_files_in_dir. "
                "Output is truncated to `limit` entries; on truncation a hint "
                "is appended."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum entries to return (default 200).",
                        "default": 200,
                        "minimum": 1
                    }
                },
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        limit = args.get("limit", 200)
        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        files = sorted(api.list_files_in_vault())
        total = len(files)
        truncated = files[:limit]
        text = json.dumps(truncated, ensure_ascii=False, indent=2)
        if total > limit:
            text += (
                f"\n\n... ({total - limit} more entries truncated. "
                f"Increase limit or use obsidian_list_files_in_dir for narrower scope.)"
            )

        return [
            TextContent(type="text", text=text)
        ]

class ListFilesInDirToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_DIR)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Lists files and directories in a specific Obsidian directory "
                "(alphabetically sorted). Note that empty directories are not "
                "returned by Obsidian REST API. Output is truncated to `limit` "
                "entries; on truncation a hint is appended."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "Path to list files from (relative to your vault root)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum entries to return (default 500).",
                        "default": 500,
                        "minimum": 1
                    }
                },
                "required": ["dirpath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:

        if "dirpath" not in args:
            raise RuntimeError("dirpath argument missing in arguments")

        limit = args.get("limit", 500)
        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        files = sorted(api.list_files_in_dir(args["dirpath"]))
        total = len(files)
        truncated = files[:limit]
        text = json.dumps(truncated, ensure_ascii=False, indent=2)
        if total > limit:
            text += (
                f"\n\n... ({total - limit} more entries truncated. "
                f"Increase limit or query a deeper subdirectory.)"
            )

        return [
            TextContent(type="text", text=text)
        ]
    
class GetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Return the content of a single file in your vault. "
                "Optionally slice by line range using start_line (0-based) "
                "and line_limit. For large files, prefer slicing or use "
                "obsidian_get_section_content to read just one heading's "
                "section. If a single line exceeds 5000 chars, a warning "
                "is appended."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the relevant file (relative to your vault root).",
                        "format": "path"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "0-based line index to start from (default 0).",
                        "default": 0,
                        "minimum": 0
                    },
                    "line_limit": {
                        "type": "integer",
                        "description": "Maximum lines to return from start_line. Omit for full file.",
                        "minimum": 1
                    }
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing in arguments")

        start_line = args.get("start_line", 0)
        line_limit = args.get("line_limit", None)

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        content = api.get_file_contents(args["filepath"])

        lines = content.splitlines(keepends=True)
        total = len(lines)

        if start_line >= total and total > 0:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"# {args['filepath']} (no content at start_line={start_line}; "
                        f"file has {total} line(s))\n"
                    ),
                )
            ]

        end_line = total if line_limit is None else min(start_line + line_limit, total)
        sliced = lines[start_line:end_line]
        text_out = "".join(sliced)

        sliced_partial = start_line > 0 or end_line < total
        if sliced_partial:
            text_out = (
                f"# {args['filepath']} (lines {start_line}-{end_line - 1} of {total})\n\n"
                + text_out
            )

        # Long-line warning — single very long lines often indicate non-prose
        long_line_indices = [
            start_line + i for i, ln in enumerate(sliced) if len(ln) > 5000
        ]
        if long_line_indices:
            shown = long_line_indices[:5]
            more = "" if len(long_line_indices) <= 5 else f" (+{len(long_line_indices) - 5} more)"
            text_out += (
                f"\n\n(WARNING: line(s) {shown}{more} exceed 5000 chars — file may "
                f"be non-prose. Consider start_line/line_limit to narrow, or use "
                f"obsidian_get_section_content for a specific section.)"
            )

        return [
            TextContent(type="text", text=text_out)
        ]

class SearchToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_simple_search")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Simple text search across all files in the vault. Returns "
                "matching files with context snippets. Results are truncated "
                "to `limit` hits (default 20). On truncation a hint is "
                "appended; refine the query for narrower results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for in the vault."
                    },
                    "context_length": {
                        "type": "integer",
                        "description": "Characters of context around each match (default 100).",
                        "default": 100
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum hits to return (default 20).",
                        "default": 20,
                        "minimum": 1
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise RuntimeError("query argument missing in arguments")

        context_length = args.get("context_length", 100)
        limit = args.get("limit", 20)

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.search(args["query"], context_length)
        total = len(results)
        truncated = results[:limit]

        formatted_results = []
        for result in truncated:
            formatted_matches = []
            for match in result.get('matches', []):
                context = match.get('context', '')
                match_pos = match.get('match', {})
                start = match_pos.get('start', 0)
                end = match_pos.get('end', 0)

                formatted_matches.append({
                    'context': context,
                    'match_position': {'start': start, 'end': end}
                })

            formatted_results.append({
                'filename': result.get('filename', ''),
                'score': result.get('score', 0),
                'matches': formatted_matches
            })

        text = json.dumps(formatted_results, ensure_ascii=False, indent=2)
        if total > limit:
            text += (
                f"\n\n... ({total} total hits, showing {limit}. "
                f"Refine query for narrower results.)"
            )

        return [
            TextContent(type="text", text=text)
        ]
    
class AppendContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_append_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Append content to a new or existing file in the vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to append to the file"
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.append_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully appended content to {args['filepath']}"
           )
       ]
   
class PatchContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_patch_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Insert content relative to a heading, block reference, or "
               "frontmatter field.\n\n"
               "Heading paths use '::' delimiter (e.g. 'Top H1::Sub H2'). "
               "Lenient parsing — leading '#' and whitespace are stripped, "
               "and partial paths (single name like 'Sub' or partial chain "
               "like 'Sub::Leaf') are auto-resolved if the match is unique. "
               "On miss or ambiguity, the file's heading tree is returned in "
               "the error for self-correction.\n\n"
               "IMPORTANT: every operation edits only the BODY under a heading "
               "— the heading line itself is NEVER changed. Putting a heading "
               "line ('## ...') into `content` does NOT rename the heading; it "
               "creates a duplicate (the tool rejects this). To rename a "
               "heading use obsidian_rename_heading; to remove a whole section "
               "use obsidian_delete_section.\n\n"
               "For target_type='heading', `scope` selects how much is edited:\n"
               "  - scope='intro' (default): only the body between the heading "
               "and its first child heading. Child sub-sections are preserved "
               "— the safe, common case.\n"
               "  - scope='section': the whole section including all child "
               "sub-sections. operation='replace' here wipes the children and "
               "requires confirm_wipe=true.\n"
               "Heading edits use local markdown parsing (not the REST heading "
               "matcher), so they are reliable for non-ASCII / CJK headings.\n\n"
               "Note: target_type='block' requires a pre-existing block "
               "reference (^block-id) in the file. target_type='frontmatter' "
               "requires the field to be defined in the YAML frontmatter — "
               "both are rare in practice and go through the REST API."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "operation": {
                       "type": "string",
                       "description": "Operation to perform (append, prepend, or replace)",
                       "enum": ["append", "prepend", "replace"]
                   },
                   "target_type": {
                       "type": "string",
                       "description": "Type of target to patch",
                       "enum": ["heading", "block", "frontmatter"]
                   },
                   "target": {
                       "type": "string",
                       "description": (
                           "For target_type='heading': '::'-delimited heading "
                           "path (e.g. 'Architecture' or 'Top H1::Sub H2::Leaf H3'). "
                           "Lenient — leading '#' and whitespace are stripped. "
                           "For target_type='block': block reference like "
                           "'^block-id' (must already exist). "
                           "For target_type='frontmatter': YAML field name "
                           "(must already exist)."
                       )
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to insert"
                   },
                   "scope": {
                       "type": "string",
                       "description": (
                           "Only for target_type='heading'. 'intro' (default): "
                           "edit only the body before the first child heading, "
                           "preserving sub-sections. 'section': edit the whole "
                           "section including children (replace wipes them, "
                           "needs confirm_wipe). Ignored for block/frontmatter."
                       ),
                       "enum": ["intro", "section"],
                       "default": "intro"
                   },
                   "confirm_wipe": {
                       "type": "boolean",
                       "description": (
                           "Required only when target_type='heading', "
                           "scope='section', operation='replace' AND the target "
                           "heading has child sub-headings. Set true to "
                           "acknowledge that all descendants will be wiped. "
                           "Otherwise omit."
                       ),
                       "default": False
                   }
               },
               "required": ["filepath", "operation", "target_type", "target", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if not all(k in args for k in ["filepath", "operation", "target_type", "target", "content"]):
           raise RuntimeError("filepath, operation, target_type, target and content arguments required")

       filepath = args["filepath"]
       operation = args["operation"]
       target_type = args["target_type"]
       target = args["target"]
       content = args["content"]
       confirm_wipe = args.get("confirm_wipe", False)
       scope = args.get("scope", "intro")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

       # --- Heading: edited locally (parse + put_content). Reliable for
       # non-ASCII headings and fails loudly instead of the REST matcher's
       # silent corruption. block/frontmatter still use the REST PATCH below. ---
       if target_type == "heading":
           if scope not in ("intro", "section"):
               raise RuntimeError(f"invalid scope {scope!r}; must be 'intro' or 'section'")

           target = "::".join(
               markdown_section.normalize_heading_path(seg)
               for seg in target.split("::")
           )
           file_text = api.get_file_contents(filepath)

           # Resolve target level once (None if missing/ambiguous — the apply
           # op below re-raises with the healing tree).
           try:
               level = markdown_section.heading_level(file_text, target)
           except ValueError:
               level = None

           # Guard: a heading line in `content` at the target's level or
           # shallower creates a duplicate/sibling, since the heading line is
           # never replaced.
           if level is not None:
               lead = markdown_section.leading_heading_level(content)
               if lead is not None and lead <= level:
                   raise RuntimeError(
                       f"content starts with a level-{lead} heading, but this "
                       f"operation edits only the body — the heading line is "
                       f"never changed — so it would create a duplicate/sibling "
                       f"heading. To rename the heading use obsidian_rename_heading; "
                       f"for a real sub-section use a deeper heading level."
                   )

           # confirm_wipe gate — only scope='section' replace that wipes children
           n_wiped = 0
           if scope == "section" and operation == "replace" and level is not None:
               if markdown_section.heading_has_children(file_text, target):
                   n_wiped = markdown_section.count_descendant_headings(file_text, target)
                   if not confirm_wipe:
                       raise RuntimeError(
                           f"Heading {target!r} in {filepath} has {n_wiped} "
                           f"descendant heading(s). scope='section' replace would "
                           f"wipe them all.\n"
                           f"  - If intentional, retry with confirm_wipe=true.\n"
                           f"  - To replace only the body and keep sub-sections, "
                           f"use scope='intro' (the default)."
                       )

           try:
               if scope == "intro":
                   new_text = markdown_section.apply_intro_op(file_text, target, operation, content)
               else:
                   new_text = markdown_section.apply_section_op(file_text, target, operation, content)
           except ValueError as e:
               tree = "\n".join(markdown_section.heading_tree_lines(file_text))
               raise RuntimeError(f"{e}\n\nAvailable headings in {filepath}:\n{tree}")

           api.put_content(filepath, new_text)
           success_msg = f"Successfully patched content in {filepath} (heading, scope={scope})"
           if n_wiped > 0:
               success_msg += f" (wiped {n_wiped} child heading(s))"
           return [TextContent(type="text", text=success_msg)]

       # --- block / frontmatter: server-side PATCH (unchanged) ---
       api.patch_content(filepath, operation, target_type, target, content)
       return [TextContent(type="text", text=f"Successfully patched content in {filepath}")]
       
class PutContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_put_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Create a new file in your vault or update the content of an existing one in your vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the relevant file (relative to your vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content of the file you would like to upload"
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.put_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully uploaded content to {args['filepath']}"
           )
       ]
   

class RenameHeadingToolHandler(ToolHandler):
   """Rename a heading: change the heading line's text while keeping its level
   and everything beneath it (body + sub-sections) intact. Local parsing, so
   reliable for non-ASCII headings.
   """
   def __init__(self):
       super().__init__("obsidian_rename_heading")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Rename a heading — change the heading line's TEXT while keeping "
               "its level and everything under it (body + sub-sections) intact. "
               "Use this instead of trying to 'replace' a heading via "
               "obsidian_patch_content, which only edits the body and would "
               "leave the old heading plus a duplicate.\n\n"
               "Local markdown parsing — reliable for non-ASCII / CJK headings. "
               "heading_path uses '::' delimiter and is lenient (leading '#' / "
               "whitespace stripped). On miss or ambiguity the file's heading "
               "tree is returned in the error for self-correction."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "heading_path": {
                       "type": "string",
                       "description": (
                           "'::'-delimited path to the heading to rename. e.g. "
                           "'My H1' or 'My H1::My H2'. Lenient. Must resolve to "
                           "exactly one heading."
                       )
                   },
                   "new_title": {
                       "type": "string",
                       "description": (
                           "New heading text, WITHOUT leading '#'. The heading "
                           "level is preserved automatically."
                       )
                   }
               },
               "required": ["filepath", "heading_path", "new_title"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       for k in ("filepath", "heading_path", "new_title"):
           if k not in args:
               raise RuntimeError(f"{k} argument required")

       heading_path = "::".join(
           markdown_section.normalize_heading_path(seg)
           for seg in args["heading_path"].split("::")
       )

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       text = api.get_file_contents(args["filepath"])

       try:
           new_text = markdown_section.rename_heading(text, heading_path, args["new_title"])
       except ValueError as e:
           tree = "\n".join(markdown_section.heading_tree_lines(text))
           raise RuntimeError(
               f"{e}\n\nAvailable headings in {args['filepath']}:\n{tree}"
           )

       api.put_content(args["filepath"], new_text)
       new_title = markdown_section.normalize_heading_path(args["new_title"])
       return [
           TextContent(
               type="text",
               text=f"Renamed heading {heading_path!r} -> {new_title!r} in {args['filepath']}"
           )
       ]


class DeleteSectionToolHandler(ToolHandler):
   """Delete a heading and its entire section (body + descendants) in place.
   Local parsing; gated by an explicit confirm flag because it is destructive.
   """
   def __init__(self):
       super().__init__("obsidian_delete_section")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "DESTRUCTIVE. Remove a heading and its ENTIRE section (body plus "
               "all descendant sub-sections) from a file. Requires confirm=true. "
               "Use for deleting one section in place — NOT the whole file "
               "(that is obsidian_delete_file).\n\n"
               "Local markdown parsing — reliable for non-ASCII headings. "
               "heading_path is lenient. On miss or ambiguity the heading tree "
               "is returned in the error. If confirm is omitted, the call is "
               "rejected with a count of what would be removed."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "heading_path": {
                       "type": "string",
                       "description": (
                           "'::'-delimited path to the heading whose section "
                           "will be removed. Lenient. Must resolve to exactly "
                           "one heading."
                       )
                   },
                   "confirm": {
                       "type": "boolean",
                       "description": (
                           "Must be exactly true. Deliberate confirmation that "
                           "the heading, its body, and all sub-sections are "
                           "deleted."
                       ),
                       "enum": [True]
                   }
               },
               "required": ["filepath", "heading_path", "confirm"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       for k in ("filepath", "heading_path"):
           if k not in args:
               raise RuntimeError(f"{k} argument required")

       heading_path = "::".join(
           markdown_section.normalize_heading_path(seg)
           for seg in args["heading_path"].split("::")
       )

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       text = api.get_file_contents(args["filepath"])

       try:
           n_desc = markdown_section.count_descendant_headings(text, heading_path)
       except ValueError as e:
           tree = "\n".join(markdown_section.heading_tree_lines(text))
           raise RuntimeError(
               f"{e}\n\nAvailable headings in {args['filepath']}:\n{tree}"
           )

       if args.get("confirm", False) is not True:
           raise RuntimeError(
               f"Deleting section {heading_path!r} would remove the heading and "
               f"{n_desc} descendant heading(s) plus all their content. Retry "
               f"with confirm=true to proceed."
           )

       new_text = markdown_section.delete_section(text, heading_path)
       api.put_content(args["filepath"], new_text)
       suffix = f" ({n_desc} sub-heading(s) included)" if n_desc else ""
       return [
           TextContent(
               type="text",
               text=f"Deleted section {heading_path!r} from {args['filepath']}{suffix}"
           )
       ]


class DeleteFileToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_delete_file")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "DESTRUCTIVE / IRREVERSIBLE. Permanently removes a file or "
               "directory from the vault. Use ONLY when the user explicitly "
               "requests deletion of a specific file.\n\n"
               "DO NOT use as a workaround when a write operation fails — "
               "instead use obsidian_patch_content (heading edits default to "
               "scope='intro', preserving children). To remove just one "
               "section, use obsidian_delete_section rather than deleting the "
               "whole file. DO NOT use to 'replace' a file's content — use "
               "obsidian_append_content (creates if missing) or a scoped "
               "obsidian_patch_content edit."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Exact path the user specified for deletion (relative to vault root).",
                       "format": "path"
                   },
                   "confirm": {
                       "type": "boolean",
                       "description": "Must be exactly true. Required deliberate confirmation gate.",
                       "enum": [True]
                   }
               },
               "required": ["filepath", "confirm"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args:
           raise RuntimeError("filepath argument missing in arguments")

       if args.get("confirm", False) is not True:
           raise RuntimeError("confirm must be set to true (boolean) to delete a file")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.delete_file(args["filepath"])

       return [
           TextContent(
               type="text",
               text=f"Successfully deleted {args['filepath']}"
           )
       ]
   
class ComplexSearchToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_complex_search")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Complex search using a JsonLogic query. Supports standard "
               "JsonLogic operators plus 'glob' and 'regexp'. Results must "
               "be non-falsy. Use for tag/path/content filtering. See the "
               "`query` parameter for syntax examples."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "query": {
                       "type": "object",
                       "description": (
                           "JsonLogic query object. ALWAYS follow these examples.\n"
                           "Ex 1 (all markdown): {\"glob\": [\"*.md\", {\"var\": \"path\"}]}\n"
                           "Ex 2 (markdown containing '1221'): "
                           "{\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, "
                           "{\"regexp\": [\".*1221.*\", {\"var\": \"content\"}]}]}\n"
                           "Ex 3 (markdown in Work folder containing 'Keaton'): "
                           "{\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, "
                           "{\"regexp\": [\".*Work.*\", {\"var\": \"path\"}]}, "
                           "{\"regexp\": [\"Keaton\", {\"var\": \"content\"}]}]}"
                       )
                   },
                   "limit": {
                       "type": "integer",
                       "description": "Maximum hits to return (default 20).",
                       "default": 20,
                       "minimum": 1
                   }
               },
               "required": ["query"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "query" not in args:
           raise RuntimeError("query argument missing in arguments")

       limit = args.get("limit", 20)
       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       results = api.search_json(args.get("query", ""))
       total = len(results) if isinstance(results, list) else 0
       truncated = results[:limit] if isinstance(results, list) else results

       text = json.dumps(truncated, ensure_ascii=False, indent=2)
       if total > limit:
           text += (
               f"\n\n... ({total} total hits, showing {limit}. "
               f"Refine query for narrower results.)"
           )

       return [
           TextContent(type="text", text=text)
       ]

class BatchGetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_batch_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Return the contents of multiple files in your vault, "
                "concatenated with per-file '# {filepath}' headers. Output "
                "is capped at max_total_chars (default 50000); files beyond "
                "the cap are skipped and a notice is appended."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepaths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Path to a file (relative to your vault root)",
                            "format": "path"
                        },
                        "description": "List of file paths to read"
                    },
                    "max_total_chars": {
                        "type": "integer",
                        "description": "Cap on total characters of concatenated output (default 50000).",
                        "default": 50000,
                        "minimum": 1
                    }
                },
                "required": ["filepaths"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepaths" not in args:
            raise RuntimeError("filepaths argument missing in arguments")

        max_total_chars = args.get("max_total_chars", 50000)
        filepaths = args["filepaths"]

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        chunks: list[str] = []
        total_chars = 0
        skipped = 0
        for idx, fp in enumerate(filepaths):
            if total_chars >= max_total_chars:
                skipped = len(filepaths) - idx
                break
            try:
                file_text = api.get_file_contents(fp)
                chunk = f"# {fp}\n\n{file_text}\n\n---\n\n"
            except Exception as e:
                chunk = f"# {fp}\n\nError reading file: {e}\n\n---\n\n"
            chunks.append(chunk)
            total_chars += len(chunk)

        text = "".join(chunks)
        if skipped > 0:
            text += (
                f"\n# {skipped} file(s) skipped — max_total_chars={max_total_chars} reached. "
                f"Reduce filepaths or call again with a higher cap.\n"
            )

        return [
            TextContent(type="text", text=text)
        ]

class PeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_periodic_note")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get current periodic note for the specified period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "type": {
                        "type": "string",
                        "description": "The type of data to get ('content' or 'metadata'). 'content' returns just the content in Markdown format. 'metadata' includes note metadata (including paths, tags, etc.) and the content.",
                        "default": "content",
                        "enum": ["content", "metadata"]
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")
        
        type = args["type"] if "type" in args else "content"
        valid_types = ["content", "metadata"]
        if type not in valid_types:
            raise RuntimeError(f"Invalid type: {type}. Must be one of: {', '.join(valid_types)}")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        content = api.get_periodic_note(period,type)

        return [
            TextContent(
                type="text",
                text=content
            )
        ]
        
class RecentPeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_periodic_notes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get most recent periodic notes for the specified period type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include note content (default: false)",
                        "default": False
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")

        limit = args.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")
            
        include_content = args.get("include_content", False)
        if not isinstance(include_content, bool):
            raise RuntimeError(f"Invalid include_content: {include_content}. Must be a boolean")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.get_recent_periodic_notes(period, limit, include_content)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, ensure_ascii=False, indent=2)
            )
        ]
        
class ListHeadingsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_list_headings")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Returns the heading tree of a single file as an indented "
                "outline. Use BEFORE calling obsidian_patch_content, "
                "obsidian_rename_heading, or obsidian_delete_section when "
                "unsure of the exact heading path. Cheap recon — typically "
                "1-5% of file token cost. On heading-related errors from those "
                "tools, the failing tool already returns the tree in its error "
                "message; this dedicated tool is for proactive lookup."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to vault root).",
                        "format": "path"
                    }
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing in arguments")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        text = api.get_file_contents(args["filepath"])
        tree = "\n".join(markdown_section.heading_tree_lines(text))

        return [
            TextContent(
                type="text",
                text=f"# {args['filepath']}\n{tree}\n",
            )
        ]


class GetSectionContentToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_section_content")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Returns the content under a single heading (heading line + "
                "body + all descendant subsections) from a file. Use this "
                "instead of obsidian_get_file_contents when you only need "
                "one section of a large file — significant token savings.\n\n"
                "heading_path uses '::' delimiter and is lenient — leading "
                "'#' and whitespace are stripped. Set include_heading=false "
                "to exclude the heading line itself. On miss or ambiguity, "
                "the file's heading tree is returned in the error for "
                "self-correction."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to vault root).",
                        "format": "path"
                    },
                    "heading_path": {
                        "type": "string",
                        "description": (
                            "'::'-delimited heading path. e.g. 'My H1' or "
                            "'My H1::My H2'. Lenient — leading '#' and "
                            "whitespace per segment are stripped."
                        )
                    },
                    "include_heading": {
                        "type": "boolean",
                        "description": "Include the heading line itself (default true).",
                        "default": True
                    }
                },
                "required": ["filepath", "heading_path"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args or "heading_path" not in args:
            raise RuntimeError("filepath and heading_path arguments required")

        include_heading = args.get("include_heading", True)

        # L4 leniency
        heading_path = "::".join(
            markdown_section.normalize_heading_path(seg)
            for seg in args["heading_path"].split("::")
        )

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        text = api.get_file_contents(args["filepath"])

        try:
            start_idx, end_idx, lines = markdown_section.section_region(text, heading_path)
        except ValueError as e:
            tree = "\n".join(markdown_section.heading_tree_lines(text))
            raise RuntimeError(
                f"{e}\n\nAvailable headings in {args['filepath']}:\n{tree}"
            )

        if not include_heading:
            start_idx += 1

        section_text = "".join(lines[start_idx:end_idx])
        meta = (
            f"# {args['filepath']} :: {heading_path} "
            f"(lines {start_idx}-{end_idx - 1} of {len(lines)})\n\n"
        )

        return [
            TextContent(type="text", text=meta + section_text)
        ]


class RecentChangesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_changes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get recently modified files in the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only include files modified within this many days (default: 30)",
                        "minimum": 1,
                        "default": 30
                    }
                }
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        limit = args.get("limit", 10)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")

        days = args.get("days", 30)
        if not isinstance(days, int) or days < 1:
            raise RuntimeError(f"Invalid days: {days}. Must be a positive integer")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.get_recent_changes(limit, days)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, ensure_ascii=False, indent=2)
            )
        ]
