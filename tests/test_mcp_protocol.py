"""Optional SDK integration: real subprocess, schema, success and error responses."""
import asyncio
import os
from pathlib import Path
import sys
import pytest

pytest.importorskip('mcp', reason='Install requirements-mcp.txt in the standalone MCP environment')
from mcp import Client, StdioServerParameters

BIRTH = {'birth_date': '2005-12-23', 'local_time': '08:37',
         'timezone': 'Asia/Shanghai', 'location': {'latitude': 31.23, 'longitude': 121.47}}


def test_stdio_tools_and_errors():
    async def run():
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m', 'astral_nexus_mcp.server'],
            cwd=str(Path(__file__).resolve().parents[1]), env=dict(os.environ))
        async with Client(parameters) as client:
            listing = await client.list_tools()
            assert {tool.name for tool in listing.tools} == {'calculate_astrology', 'calculate_bazi'}
            for tool in listing.tools:
                assert tool.annotations.read_only_hint is True
                assert tool.annotations.destructive_hint is False
            for name, service in [('calculate_astrology', 'astrology'), ('calculate_bazi', 'bazi-chart')]:
                result = await client.call_tool(name, {'birth': BIRTH})
                assert not result.is_error
                assert result.structured_content['service_id'] == service
                assert result.structured_content['engine_version']
            for arguments in [
                {'birth': BIRTH | {'timezone': 'invalid'}},
                {'birth': BIRTH | {'local_time': '25:00'}},
                {'birth': BIRTH, 'through_year': 9999},
                {'birth': BIRTH, 'through_year': 2030},
            ]:
                result = await client.call_tool('calculate_bazi', arguments)
                assert result.is_error
    asyncio.run(asyncio.wait_for(run(), timeout=60))
