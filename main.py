import discord
from discord.ext import commands
import os
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openai import AsyncOpenAI
import threading

# --- 1. SETUP BOT & AI ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY") 
)

# --- 2. SETUP WEBSITE ---
app = FastAPI()
last_actions = {}

class ChatRequest(BaseModel):
    guild_id: int
    prompt: str

@app.get("/")
async def serve_website():
    # This serves the front-end to your browser
    return HTMLResponse(content=open("index.html", "r").read() if os.path.exists("index.html") else "<h1>Website loading...</h1>")

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    guild = bot.get_guild(req.guild_id)
    if not guild:
        return {"error": "Bot is not in this server! Invite it first."}
        
    await bot.loop.run_in_executor(None, lambda: None) # ensure loop is running
    result = await process_ai_request(guild, req.prompt)
    return result

@app.post("/api/undo")
async def undo_endpoint(req: ChatRequest):
    guild = bot.get_guild(req.guild_id)
    if not guild or guild.id not in last_actions:
        return {"error": "Nothing to undo."}
        
    for ch_id, old_name in last_actions[guild.id].items():
        ch = guild.get_channel(ch_id)
        if ch:
            try:
                await ch.edit(name=old_name)
                await asyncio.sleep(1)
            except: pass
            
    del last_actions[guild.id]
    return {"success": "Undid the last action!"}

# --- 3. THE AI LOGIC ---
async def process_ai_request(guild, prompt):
    state_lines = []
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel): continue
        cat_name = ch.category.name if ch.category else "None"
        state_lines.append(f"{ch.id}:{ch.name}|{cat_name}")
        
    server_state_str = "\n".join(state_lines[:40])
    
    system_prompt = f"""
    You are an AI Discord manager. 
    Current server layout (ID:name|Category):
    {server_state_str}
    
    Request: "{prompt}"
    
    Output ONLY commands, one per line. NO other text.
    RENAME|channel_id|new_name
    MOVE|channel_id|new_category
    """

    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b", 
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=1500 
        )
        
        raw = response.choices[0].message.content.replace("```", "").upper()
        
        steps = []
        last_actions[guild.id] = {ch.id: ch.name for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}

        for line in raw.split('\n'):
            line = line.strip()
            if "RENAME|" in line:
                try:
                    p = line.split("RENAME|")[1].split("|")
                    ch_id, new_name = int(p[0].strip()), p[1].strip()
                    ch = guild.get_channel(ch_id)
                    if ch:
                        await ch.edit(name=new_name)
                        steps.append(f"Renamed to {new_name}")
                        await asyncio.sleep(2)
                except: pass
            elif "MOVE|" in line:
                try:
                    p = line.split("MOVE|")[1].split("|")
                    ch_id, cat_name = int(p[0].strip()), p[1].strip()
                    ch = guild.get_channel(ch_id)
                    if ch:
                        cat = discord.utils.get(guild.categories, name=cat_name) or await guild.create_category(cat_name)
                        await ch.edit(category=cat)
                        steps.append(f"Moved to {cat_name}")
                        await asyncio.sleep(2)
                except: pass

        return {"steps": steps, "raw": raw}
    except Exception as e:
        return {"error": str(e)}

# --- 4. START EVERYTHING ---
@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")

def run_web():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
