import asyncio
import json
import os
import re
from contextlib import asynccontextmanager

import discord
import httpx
import uvicorn
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
undo_snapshots: dict[int, list[str]] = {}


def get_ai_client() -> AsyncOpenAI:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("DISCORD_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("DISCORD_TOKEN is missing")
    yield
    if not bot.is_closed():
        await bot.close()


app = FastAPI(title="Rynnzyr Discord Architect", lifespan=lifespan)


class GuildRequest(BaseModel):
    guild_id: int
    prompt: str = ""


class PlanRequest(BaseModel):
    guild_id: int
    prompt: str = Field(min_length=3, max_length=1000)


ChatRequest = PlanRequest


class ApplyRequest(BaseModel):
    guild_id: int
    plan: dict


@app.get("/")
def serve_website():
    try:
        with open("index.html", encoding="utf-8") as page:
            response = HTMLResponse(page.read())
    except FileNotFoundError:
        raise HTTPException(500, "index.html is missing from the deployment")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/login")
def login():
    if not all((CLIENT_ID, REDIRECT_URI)):
        return HTMLResponse("Missing CLIENT_ID or REDIRECT_URI", status_code=500)
    from urllib.parse import urlencode
    query = urlencode({"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"})
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{query}")


@app.get("/callback")
async def callback(code: str | None = None):
    if not code:
        return RedirectResponse("/?error=auth_failed")
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    async with httpx.AsyncClient() as client:
        response = await client.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = response.json().get("access_token")
    if not token:
        return RedirectResponse("/?error=auth_failed")
    redirect = RedirectResponse("/?logged_in=true")
    redirect.set_cookie("discord_token", token, httponly=True, samesite="lax", max_age=604800)
    return redirect


@app.get("/api/user-guilds")
async def user_guilds(request: Request):
    if not bot.is_ready():
        return {"error": "The Discord bot is starting. Please try again."}
    token = request.cookies.get("discord_token")
    if not token:
        raise HTTPException(401, "Not logged in")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise HTTPException(401, "Discord login expired")
    result = []
    for item in response.json():
        perms = int(item.get("permissions", 0))
        if not (perms & 0x8 or perms & 0x20):
            continue
        gid = int(item["id"])
        has_bot = bot.get_guild(gid) is not None
        result.append({"id": gid, "name": item["name"], "icon": item.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={gid}"})
    return {"guilds": result}


def guild_or_error(guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    me = guild.me
    if me is None:
        raise HTTPException(503, "Bot membership is not available yet")
    if not me.guild_permissions.manage_channels:
        raise HTTPException(403, "Bot needs Manage Channels permission")
    if not me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Roles permission")
    return guild


def is_voice_channel(channel):
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


def safe_state(guild: discord.Guild) -> dict:
    roles = [{"name": r.name, "position": r.position} for r in guild.roles if not r.managed]
    categories = [{"name": c.name, "channels": [{"name": ch.name, "type": "voice" if is_voice_channel(ch) else "text"} for ch in c.channels]} for c in guild.categories[:30]]
    return {"name": guild.name, "roles": roles[-20:], "categories": categories,
            "uncategorized": [{"name": ch.name, "type": "voice" if is_voice_channel(ch) else "text"} for ch in guild.channels if ch.category is None and isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel))][:30]}


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def sanitize_name(value, fallback="community"):
    text = clean_text(value, 100).lower()
    text = "".join(c if c.isalnum() or c in "-_ " else "-" for c in text)
    return "-".join(text.split())[:100].strip("-") or fallback


def sanitize_channel_name(value, emoji="💬"):
    raw = clean_text(value, 100)
    match = re.match(r"^[〔【\[（(](.+?)[〕】\]）)]\s*[・•|:：-]*\s*(.*)$", raw)
    icon, body = (clean_text(match.group(1), 12) or emoji, match.group(2)) if match else (clean_text(emoji, 12) or "💬", raw)
    body = body.lower()
    body = "".join(c if c.isalnum() or c in "-_ " else "-" for c in body)
    body = "-".join(body.split()).strip("-")[:75] or "chat"
    return f"〔{icon}〕・{body}"[:100]


def is_staff_category(name):
    low = name.lower()
    return "staff" in low or "mod team" in low or "moderator only" in low


def sanitize_plan(plan: dict) -> dict:
    roles = []
    for item in (plan.get("roles") or [])[:12]:
        if not isinstance(item, dict):
            continue
        name = sanitize_name(item.get("name"), "member").replace("-", " ").title()
        if name.lower() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "#5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name[:100], "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})
    categories, total = [], 0
    for item in (plan.get("categories") or [])[:16]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name") or "✨ : COMMUNITY : ✨", 100)
        channels = []
        for channel in (item.get("channels") or [])[:12]:
            if not isinstance(channel, dict) or total >= 120:
                continue
            kind = "voice" if channel.get("type") == "voice" else "text"
            channels.append({"name": sanitize_channel_name(channel.get("name"), channel.get("emoji", "💬")), "type": kind,
                             "topic": clean_text(channel.get("topic", ""), 1024) if kind == "text" else ""})
            total += 1
        categories.append({"name": name, "staff_only": bool(item.get("staff_only")) or is_staff_category(name), "channels": channels})
    foundation = [
        ("📊 : SERVER INFORMATION : 📊", [("📚", "rules", "text"), ("📣", "announcements", "text"), ("🗳️", "polls", "text")]),
        ("👋 : WELCOME : 👋", [("👋", "welcome", "text"), ("🕊️", "goodbye", "text"), ("🧭", "introductions", "text")]),
        ("✅ : VERIFICATION : ✅", [("✅", "verification", "text"), ("🎭", "get-your-roles", "text")]),
        ("💬 : COMMUNITY : 🎙️", [("💬", "general", "text"), ("📸", "media", "text"), ("💡", "suggestions", "text"), ("🎙️", "community-voice", "voice")]),
        ("🔒 : STAFF GENERAL : 🔒", [("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"), ("💬", "staff-chat", "text"), ("🎉", "staff-promotions", "text"), ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"), ("🎙️", "staff-vc", "voice")]),
    ]
    for category_name, definitions in foundation:
        found = next((c for c in categories if c["name"].casefold() == category_name.casefold()), None)
        if found is None:
            found = {"name": category_name, "staff_only": category_name.startswith("🔒"), "channels": []}
            categories.append(found)
        names = {ch["name"].casefold() for ch in found["channels"]}
        for emoji, channel_name, kind in definitions:
            formatted = sanitize_channel_name(channel_name, emoji)
            if formatted.casefold() not in names and total < 120:
                found["channels"].append({"name": formatted, "type": kind, "topic": ""})
                names.add(formatted.casefold())
                total += 1
        if found["name"].startswith("🔒"):
            found["staff_only"] = True
    return {"summary": clean_text(plan.get("summary") or "A polished server layout", 500), "roles": roles, "categories": categories[:16]}


async def generate_plan(guild: discord.Guild, prompt: str) -> dict:
    instructions = f"""
You are Rynnzyr, an expert Discord community architect. Build a full, polished layout personalized to the user's exact request. Infer community type and create useful, non-duplicate categories and channels specific to the topic. Typical full design: 7-12 categories, 4-9 channels each; smaller request gets a smaller topical design. Keep the core areas SERVER INFORMATION, WELCOME, VERIFICATION, COMMUNITY, STAFF GENERAL and their standard channels, adding topic-specific channels when useful. Add several topic-specific categories; examples: trading -> marketplace, middleman, vouchers, trade-chat; gaming -> game modes, lfg, clips, team voice; creator -> content, fan-art, streams, collabs. Never include unrelated categories.
Style: category titles are decorative dividers, e.g. "📊 : SERVER INFORMATION : 📊" or "✨ : GIVEAWAYS : 🎁". Each channel name uses "〔📚〕・rules" with varied fitting emoji. Use a sensible text/voice mix and useful topics. STAFF GENERAL must have staff_only=true. Do not mark other areas private.
Return only JSON: {{"summary":"...","roles":[{{"name":"Moderator","color":"#5865F2","hoist":false,"mentionable":false}}],"categories":[{{"name":"🎮 : GAME LOUNGE : 🎮","staff_only":false,"channels":[{{"name":"〔🎮〕・game-chat","emoji":"🎮","type":"text","topic":"..."}}]}}]}}
Limits: max 12 roles, 16 categories, 12 channels/category, 120 total. No administrator permission roles. Include staff-rules, staff-announcements, staff-chat, staff-promotions, staff-logs, staff-demotions, staff-vc in private staff area.
Existing server: {json.dumps(safe_state(guild), ensure_ascii=False)}
"""
    response = await get_ai_client().chat.completions.create(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": prompt}], temperature=0.7, max_tokens=6000, response_format={"type": "json_object"})
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content))


async def apply_guild_plan(guild: discord.Guild, plan: dict) -> list[str]:
    plan = sanitize_plan(plan)
    ids, created, roles = [], [], {}
    for spec in plan["roles"]:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr AI server architect")
            ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        roles[role.name.casefold()] = role
    staff_role = next((role for name, role in roles.items() if any(word in name for word in ("staff", "moderator", "mod"))), None) or discord.utils.get(guild.roles, name="Staff")
    if staff_role is None:
        staff_role = await guild.create_role(name="Staff", colour=discord.Colour(0x5865F2), reason="Private staff access role for Rynnzyr")
        ids.append(f"role:{staff_role.id}")
        created.append("Role: Staff (assign to trusted staff members for staff-category access)")
    for spec in plan["categories"]:
        private = bool(spec.get("staff_only"))
        # discord.py requires overwrites to be a dict, even for public categories.
        overwrites = {}
        if private:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True),
            }
        category = discord.utils.get(guild.categories, name=spec["name"])
        if category is None:
            category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Created by Rynnzyr AI server architect")
            ids.append(f"category:{category.id}")
            created.append(f"Category: {category.name}" + (" (private staff area)" if private else ""))
        elif private:
            await category.edit(overwrites=overwrites, reason="Secure staff category for Rynnzyr")
        for channel_spec in spec["channels"]:
            if discord.utils.get(category.channels, name=channel_spec["name"]):
                continue
            if channel_spec["type"] == "voice":
                channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Created by Rynnzyr AI server architect")
            else:
                channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec["topic"] or None, reason="Created by Rynnzyr AI server architect")
            ids.append(f"channel:{channel.id}")
            created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            await asyncio.sleep(0.35)
    undo_snapshots[guild.id] = ids
    return created


def make_plan_embed(guild: discord.Guild, plan: dict) -> discord.Embed:
    embed = discord.Embed(title=f"✨ {guild.name} — Server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if ch["type"] == "voice" else "# ") + ch["name"] for ch in category["channels"]]
        if category.get("staff_only"):
            lines.append("🔒 Private — Staff role access")
        value = "\n".join(lines) or "No channels"
        embed.add_field(name=category["name"], value=value[:1024], inline=True)
    if plan["roles"] and len(embed.fields) < 25:
        embed.add_field(name="Suggested roles", value=", ".join(r["name"] for r in plan["roles"][:12])[:1024], inline=False)
    embed.set_footer(text="Review the layout, then build it or cancel.")
    return embed


class BlueprintView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.finished = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who requested this design can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Build this server", style=discord.ButtonStyle.success, emoji="🏗️")
    async def build_button(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("This blueprint has already been handled.", ephemeral=True)
            return
        self.finished = True
        button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            changes = await apply_guild_plan(self.guild, self.plan)
            result = "\n".join(f"• {item}" for item in changes[:35]) or "Everything already exists."
            await interaction.followup.send(f"✅ **Server built!**\n{result}\n\nAssign trusted members to the **Staff** role for private staff-channel access.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Discord denied a change. Check Manage Channels/Manage Roles permissions and role position.", ephemeral=True)
        except Exception as exc:
            print(f"Blueprint apply failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send("I hit an error while building. Check Railway logs; some changes may already have been applied.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction, button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Blueprint cancelled — no server changes were made.", embed=None, view=self)


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(guild_or_error(req.guild_id), req.prompt)}
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    try:
        return {"success": True, "created": await apply_guild_plan(guild_or_error(req.guild_id), req.plan)}
    except discord.Forbidden:
        raise HTTPException(403, "Bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = guild_or_error(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    if not ids:
        return {"error": "Nothing to undo"}
    deleted = 0
    for entry in reversed(ids):
        kind, raw_id = entry.split(":", 1)
        obj_id = int(raw_id)
        item = discord.utils.get(guild.roles, id=obj_id) if kind == "role" else guild.get_channel(obj_id)
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr AI server architect")
                deleted += 1
                await asyncio.sleep(0.25)
            except discord.Forbidden:
                continue
    return {"success": True, "deleted": deleted}


@bot.tree.command(name="ping", description="Check that Rynnzyr is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Rynnzyr is online and ready.", ephemeral=True)


@bot.tree.command(name="design", description="Preview and build a custom AI-designed server")
@app_commands.describe(prompt="Describe your community and the server you want")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission to use this command.", ephemeral=True)
        return
    me = interaction.guild.me
    if me is None or not (me.guild_permissions.manage_channels and me.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles permissions.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        await interaction.followup.send(embed=make_plan_embed(interaction.guild, plan), view=BlueprintView(interaction.guild, plan, interaction.user.id), ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't design that layout. Check Railway logs and AI API configuration."
        await interaction.followup.send(message[:1800], ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online as {bot.user}; synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Failed to sync application commands: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
