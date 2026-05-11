from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        full_name: str,
        role_id: int,
        faculty_id: int | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role_id=role_id,
            faculty_id=faculty_id,
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user
