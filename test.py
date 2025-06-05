import asyncio
from PyCharacterAI import get_client

# Replace with your actual values
TOKEN = "c1eabe9ae9f0d1c7b9756d18d39a8ba93d4a3061"
CHARACTER_ID = "W74N1cyMnHYwd9qKJydn4DzzLpAkd3ccnl-sz3SDOZs"
USER_MESSAGE = "Hello there!"

async def chat_with_character(token, character_id, user_message):
    client = await get_client(token=token)
    try:
        me = await client.account.fetch_me()
        print(f"Logged in as @{me.username}")

        # Create a new chat with the character
        chat, greeting = await client.chat.create_chat(character_id)
        print(f"{greeting.author_name}: {greeting.get_primary_candidate().text}")

        # Send your message
        response = await client.chat.send_message(character_id, chat.chat_id, user_message)
        reply = response.get_primary_candidate().text
        print(f"{response.author_name}: {reply}")
        return reply

    finally:
        await client.close_session()

# Entry point
if __name__ == "__main__":
    asyncio.run(chat_with_character(TOKEN, CHARACTER_ID, USER_MESSAGE))