import asyncpg
from config import DB_Host, DB_Name, DB_User, DB_Pass, DB_Port

async def create_db_pool():
    return await asyncpg.create_pool(database=DB_Name, user=DB_User, password=DB_Pass, host=DB_Host, port=DB_Port)

async def create_hosts_table(pool):
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS hosts (
                user_id VARCHAR(50) NOT NULL,
                hostname VARCHAR(255) NOT NULL,
                ip VARCHAR(255) NOT NULL,
                username VARCHAR(255) NOT NULL,
                password VARCHAR(255),
                identification_file VARCHAR(2500),
                port INTEGER,
                PRIMARY KEY (user_id, hostname)
            );
            CREATE TABLE IF NOT EXISTS live_terminals (
                user_id TEXT NOT NULL,
                hostname TEXT NOT NULL,
                channel_id TEXT NOT NULL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE live_terminals ADD COLUMN is_active BOOLEAN DEFAULT false;            
        ''') 

async def main():
    pool = await create_db_pool()
    await create_hosts_table(pool)
    await pool.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
