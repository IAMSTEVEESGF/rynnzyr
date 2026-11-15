import discord
from discord.ext import commands
import os
import asyncio
import json
from openai import AsyncOpenAI
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import threading

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize AI
ai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Setup Web Server
app = FastAPI()

# --- THE WEB API ENDPOINT ---
class BuildRequest(BaseModel):
    guild_id: int
    prompt: str

@app.post("/api/build-server")
async def build_server(request: BuildRequest):
    # 1. Ask AI to generate the layout
    system_prompt = """
    You are a Discord server designer. The user will give you a prompt.
    You must output ONLY a JSON object with a "categories" key.
    Inside categories, have a list of objects with "name" and "channels".
    Channels have "name", "emoji", and "type" (text or voice).
    Example:
    {"categories": [{"name": "GENERAL", "channels": [{"name": "chat", "emoji": "💬", "type": "text"}]}]}
    """
    
    response = await ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    layout = json.loads(response.choices[0].message.content)
    
    # 2. Tell the bot to build it
    guild = bot.get_guild(request.guild_id)
    if not guild:
        return {"error": "Bot is not in that server!"}
        
    # Run the build in the background so the website doesn't timeout
    asyncio.create_task(execute_build(guild, layout))
    
    return {"status": "success", "message": "Building started!"}

# --- THE BUILDER LOGIC ---
async def execute_build(guild, layout):
    for category_data in layout.get("categories", []):
        cat_name = f"〔✨ {category_data['name']} 〕"
        category = await guild.create_category(cat_name)
        await asyncio.sleep(2)
        
        for ch in category_data.get("channels", []):
            full_name = f"{ch['emoji']}┃{ch['name']}".lower()
            if ch['type'] == 'voice':
                await guild.create_voice_channel(full_name, category=category)
            else:
                await guild.create_text_channel(full_name, category=category)
            await asyncio.sleep(2) # Prevent rate limits

# --- START BOTH BOT AND WEB SERVER ---
@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")

def run_web_server():
    # This runs the website on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start the website in a separate thread
    threading.Thread(target=run_web_server, daemon=True).start()
    # Start the bot
    bot.run(os.getenv("DISCORD_TOKEN"))
