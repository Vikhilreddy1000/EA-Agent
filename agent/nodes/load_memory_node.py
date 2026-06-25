from langchain_core.messages import HumanMessage, AIMessage
from agent.memory_service import MemoryService

class LoadMemoryNode:
    async def __call__(self, state):
        history = await MemoryService.load_history(state.user_id)

        messages = []
        for msg in history[-10:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        # Add current message
        # messages.append(HumanMessage(content=state.user_message))

        state.messages = messages
        return state