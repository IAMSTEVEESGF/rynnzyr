import discord
from discord.ext import commands
import os
import asyncio
import uvicorn
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from openai import AsyncOpenAI
from contextlib import asynccontextmanager

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY") 
)

last_actions = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN is missing in Railway Variables!")
    else:
        print("⏳ Starting Discord Bot...")
        asyncio.create_task(bot.start(token)) 
    yield
    if not bot.is_closed():
        await bot.close()

app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    guild_id: int
    prompt: str

# Blocks the browser from caching the old website
@app.get("/")
async def serve_website():
    response = HTMLResponse(content=open("index.html", "r").read())
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/login")
async def login():
    if not CLIENT_ID or not REDIRECT_URI:
        return HTMLResponse("<h1>Error: CLIENT_ID or REDIRECT_URI missing in Railway Variables.</h1>")
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds")

@app.get("/callback")
async def callback(code: str = None):
    if not code:
        return RedirectResponse("/")

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    async with httpx.AsyncClient() as client:
        r = await client.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
        token_data = r.json()
        
    if 'access_token' not in token_data:
        return RedirectResponse("/?error=auth_failed")
        
    redirect = RedirectResponse("/?logged_in=true")
    redirect.set_cookie(key="discord_token", value=token_data['access_token'], httponly=True)
    return redirect

@app.get("/api/user-guilds")
async def get_user_guilds(request: Request):
    if not bot.is_ready():
        return {"error": "The Discord bot is currently offline or starting up."}

    token = request.cookies.get("discord_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
        
    async with httpx.AsyncClient() as client:
        r = await client.get('https://discord.com/api/users/@me/guilds', headers={'Authorization': f'Bearer {token}'})
        user_guilds = r.json()
        
    bot_guild_ids = [g.id for g in bot.guilds]
    
    for g in user_guilds:
        perms = int(g.get('permissions', 0))
        if (perms & 0x8) == 0x8 or (perms & 0x20) == 0x20: 
            g['has_bot'] = int(g['id']) in bot_guild_ids
            g['invite_url'] = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands&guild_id={g['id']}"
        else:
            g['has_bot'] = False
            g['no_perms'] = True

    return {"guilds": [g for g in user_guilds if not g.get('no_perms')]}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not bot.is_ready():
        return {"error": "Bot is offline."}
    return await handle_chat(req.guild_id, req.prompt)

@app.post("/api/undo")
async def undo_endpoint(req: ChatRequest):
    if not bot.is_ready():
        return {"error": "Bot is offline."}
    return await handle_undo(req.guild_id)

async def handle_chat(guild_id, prompt):
    # 1. Try to get server from bot's memory
    guild = bot.get_guild(guild_id)
    
    # 2. If memory fails, FORCE Discord to tell us if the bot is in the server
    if not guild:
        try:
            guild = await bot.fetch_guild(guild_id)
            await guild.fetch_channels()
        except Exception:
            return {"error": "Discord says the bot is NOT in this server. Double check that you invited the correct bot."}
        
    state_lines = []
    count = 0
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel): continue
        cat_name = ch.category.name if ch.category else "None"
        state_lines.append(f"{ch.id}:{ch.name}|{cat_name}")
        count += 1
        if count >= 25: break
        
    server_state_str = "\n".join(state_lines)
    system_prompt = f"""
    You are an AI Discord manager. Current server layout (ID:name|Category):
    {server_state_str}
    Request: "{prompt}"
    Output ONLY commands, one per line. NO other text.
    RENAME|channel_id|new_name
    MOVE|channel_id|new_category
    CREATE_CATEGORY|Category Name
    CREATE_TEXT|channel_name|Category Name
    CREATE_VOICE|channel_name|Category Name
    """
    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b", 
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=1000 
        )
        raw = response.choices[0].message.content.replace("```", "").upper()
        steps = []
        last_actions[guild.id] = {ch.id: ch.name for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}

        for line in raw.split('\n'):
            line = line.strip()
            if "RENAME|" in line:
                try:
                    p = line.split("RENAME|")[1].split("|")
                    ch = guild.get_channel(int(p[0].strip()))
                    if ch:
                        await ch.edit(name=p[1].strip())
                        steps.append(f"Renamed to {p[1].strip()}")
                        await asyncio.sleep(2)
                except: pass
            elif "MOVE|" in line:
                try:
                    p = line.split("MOVE|")[1].split("|")
                    ch = guild.get_channel(int(p[0].strip()))
                    if ch:
                        cat = discord.utils.get(guild.categories, name=p[1].strip()) or await guild.create_category(p[1].strip())
                        await ch.edit(category=cat)
                        steps.append(f"Moved to {p[1].strip()}")
                        await asyncio.sleep(2)
                except: pass
            elif "CREATE_TEXT|" in line:
                try:
                    p = line.split("CREATE_TEXT|")[1].split("|")
                    cat = discord.utils.get(guild.categories, name=p[1].strip()) or await guild.create_category(p[1].strip())
                    await guild.create_text_channel(name=p[0].strip(), category=cat)
                    steps.append(f"Created {p[0].strip()}")
                    await asyncio.sleep(2)
                except: pass
            elif "CREATE_VOICE|" in line:
                try:
                    p = line.split("CREATE_VOICE|")[1].split("|")
                    cat = discord.utils.get(guild.categories, name=p[1].strip()) or await guild.create_category(p[1].strip())
                    await guild.create_voice_channel(name=p[0].strip(), category=cat)
                    steps.append(f"Created {p[0].strip()}")
                    await asyncio.sleep(2)
                except: pass
        return {"steps": steps, "raw": raw}
    except Exception as e:
        return {"error": str(e)}

async def handle_undo(guild_id):
    guild = bot.get_guild(guild_id)
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

@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
