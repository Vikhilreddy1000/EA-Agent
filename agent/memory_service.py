from sqlalchemy import select, desc
from agent.db import AsyncSessionLocal
from agent.models import ChatHistory

class MemoryService:

    @staticmethod
    async def load_history(user_id: str, limit: int = 20):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.user_id == user_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(limit)
            )

            # rows = result.scalars().all()
            rows = list(reversed(result.scalars().all()))

            return [
                {"role": r.role, "content": r.content}
                for r in rows
            ]

    @staticmethod
    async def save_message(user_id: str, role: str, content: str):
        async with AsyncSessionLocal() as session:
            msg = ChatHistory(
                user_id=user_id,
                role=role,
                content=content
            )
            session.add(msg)
            await session.commit()