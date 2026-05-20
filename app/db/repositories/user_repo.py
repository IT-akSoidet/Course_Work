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

    async def upsert(
        self,
        telegram_id: int,
        full_name: str,
        username: str | None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, full_name=full_name, username=username)
            self.session.add(user)
            await self.session.flush()
            return user

        changed = False
        if user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if user.username != username:
            user.username = username
            changed = True
        if changed:
            await self.session.flush()
        return user
