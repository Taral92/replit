import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.agent.tools import create_agent_tools
from services.agent.gateway.tool_gateway import ToolGateway

def test_tool_ordering_is_deterministic():
    gateway = MagicMock(spec=ToolGateway)
    tools1 = create_agent_tools(gateway)
    tools2 = create_agent_tools(gateway)
    
    try:
        from langchain_core.utils.function_calling import convert_to_openai_function
    except ImportError:
        def convert_to_openai_function(t):
            return {"name": t.name, "description": t.description}
    
    schema1 = json.dumps([convert_to_openai_function(t) for t in tools1], sort_keys=True)
    schema2 = json.dumps([convert_to_openai_function(t) for t in tools2], sort_keys=True)
    
    assert schema1 == schema2, "Tool serialization must be deterministic between calls"

@pytest.mark.asyncio
async def test_tool_return_values_are_compact():
    gateway = AsyncMock(spec=ToolGateway)
    gateway.execute_tool = AsyncMock()
    
    from packages.protocol.events import ToolResult
    
    mock_result = ToolResult(
        ok=True,
        summary="Read src/app/page.tsx",
        data={"content": "a" * 10000, "path": "src/app/page.tsx", "total_lines": 500}
    )
    gateway.execute_tool.return_value = mock_result
    
    tools = create_agent_tools(gateway)
    read_tool = next(t for t in tools if t.name == "read_file")
    
    result = await read_tool.ainvoke({"path": "src/app/page.tsx"})
    
    assert isinstance(result, str), "Tool must return a string to the model"
    assert len(result) < 500, f"Tool return string must be < 500 chars (was {len(result)})"
    assert result == "Read src/app/page.tsx"
