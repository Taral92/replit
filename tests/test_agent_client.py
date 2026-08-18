import asyncio
import socketio
import sys
import json
import time

async def main():
    sio = socketio.AsyncClient()
    
    counts = {
        "tool_calls": 0,
        "dev_server_starts": 0,
        "llm_calls": 0, # not perfectly measurable, but we can guess by agent.status transitions
        "diff_sizes": []
    }
    
    @sio.on('agent.step')
    async def on_step(data):
        print("STEP:", data.get('tool'), data.get('target'))
        counts["tool_calls"] += 1
        if data.get('tool') in ('start_dev_server', 'shell') and ('dev' in str(data.get('args', '')) or data.get('args', {}).get('background') == True):
            counts["dev_server_starts"] += 1
            
    @sio.on('agent.tool.completed')
    async def on_tool_completed(data):
        print("TOOL_COMPLETED:", data.get('tool'))
        if 'diff' in data and data['diff']:
            counts["diff_sizes"].append(len(data['diff']))
            print("Diff received, length:", len(data['diff']))
            
    @sio.on('agent.message')
    async def on_message(data):
        print("MESSAGE:", data.get('content'))
        
    @sio.on('agent.turn.completed')
    async def on_turn_completed(data):
        print("TURN_COMPLETED!", data)
        print("FINAL COUNTS:", json.dumps(counts, indent=2))
        await sio.disconnect()

    @sio.on('agent.status')
    async def on_status(data):
        pass # print("STATUS:", data.get('status'))

    await sio.connect('http://localhost:8000')
    print("Connected!")
    
    await sio.emit('agent.start', {
        'prompt': 'build a simple todo list app in Next.js with minimal design',
        'model': 'auto'
    })
    
    await sio.wait()

if __name__ == '__main__':
    asyncio.run(main())
