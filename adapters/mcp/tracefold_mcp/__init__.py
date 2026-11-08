"""Tracefold MCP adapter: a thin stdio MCP server that forwards tool calls to the engine's HTTP API.

The adapter holds no findings, parses no files and calls no model. It maps tools to engine endpoints,
preserves engine error codes and renders the engine's own vocabulary.
"""

__version__ = "0.1.0"
