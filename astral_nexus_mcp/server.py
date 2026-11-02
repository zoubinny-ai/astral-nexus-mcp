"""Standalone stdio entry point: python -m integrations.astral_mcp.server."""
from functools import wraps
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from astral_nexus_mcp.engines.birth_time import CalculationError
from mcp_types import ToolAnnotations
from astral_nexus_mcp.tools import calculate_astrology, calculate_bazi

server = MCPServer('Astral Nexus')
annotations = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                              idempotent_hint=True, open_world_hint=False)


def register(function):
    @wraps(function)
    def execute(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CalculationError as exc:
            raise ToolError(f'{exc.code}: {exc.message}') from None
    server.tool(annotations=annotations, structured_output=True)(execute)


register(calculate_astrology)
register(calculate_bazi)

if __name__ == '__main__':
    server.run(transport='stdio')
