"""A lightweight stub of aiosqlite for test purposes."""
from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Iterable, Optional


Error = sqlite3.Error
DatabaseError = sqlite3.DatabaseError
OperationalError = sqlite3.OperationalError
IntegrityError = sqlite3.IntegrityError
ProgrammingError = sqlite3.ProgrammingError
NotSupportedError = sqlite3.NotSupportedError
sqlite_version = sqlite3.sqlite_version
sqlite_version_info = tuple(int(part) for part in sqlite3.sqlite_version.split("."))


class _Cursor:
    def __init__(self, cursor: sqlite3.Cursor, loop: asyncio.AbstractEventLoop):
        self._cursor = cursor
        self._loop = loop

    async def fetchone(self):
        return await self._loop.run_in_executor(None, self._cursor.fetchone)

    async def fetchall(self):
        return await self._loop.run_in_executor(None, self._cursor.fetchall)

    async def fetchmany(self, size: Optional[int] = None):
        if size is None:
            return await self._loop.run_in_executor(None, self._cursor.fetchmany)
        return await self._loop.run_in_executor(None, lambda: self._cursor.fetchmany(size))

    async def close(self):
        await self._loop.run_in_executor(None, self._cursor.close)

    @property
    def description(self):
        return self._cursor.description


class Connection:
    def __init__(self, connection: sqlite3.Connection, loop: asyncio.AbstractEventLoop):
        self._connection = connection
        self._loop = loop

    async def execute(self, sql: str, parameters: Iterable[Any] | None = None):
        parameters = parameters or ()

        def _execute():
            cursor = self._connection.cursor()
            cursor.execute(sql, tuple(parameters))
            return cursor

        cursor = await self._loop.run_in_executor(None, _execute)
        return _Cursor(cursor, self._loop)

    async def cursor(self):
        cursor = await self._loop.run_in_executor(None, self._connection.cursor)
        return _Cursor(cursor, self._loop)

    async def commit(self):
        await self._loop.run_in_executor(None, self._connection.commit)

    async def rollback(self):
        await self._loop.run_in_executor(None, self._connection.rollback)

    async def close(self):
        await self._loop.run_in_executor(None, self._connection.close)

    async def executescript(self, script: str):
        await self._loop.run_in_executor(None, lambda: self._connection.executescript(script))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()
        await self.close()


async def connect(database: str, **kwargs) -> Connection:
    loop = asyncio.get_running_loop()

    def _connect():
        connection = sqlite3.connect(database, check_same_thread=False, **kwargs)
        connection.isolation_level = None
        return connection

    connection = await loop.run_in_executor(None, _connect)
    return Connection(connection, loop)