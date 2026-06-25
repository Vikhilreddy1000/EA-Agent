from agent.memory_service import MemoryService

class SaveMemoryNode:
    async def __call__(self, state):
        await MemoryService.save_message(
            state.user_id, "user", state.user_message
        )

        await MemoryService.save_message(
            state.user_id, "assistant", state.response_message
        )

        return state