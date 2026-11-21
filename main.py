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

# Stable foundations requested by the owner. AI-generated categories follow these;
# AI voice rooms are consolidated into a final voice category.
CORE = [
    ("staff", "──── ⟪STAFF GENERAL⟫ ────", True, [("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"), ("💬", "staff-chat", "text"), ("🎉", "staff-promotions", "text"), ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"), ("🎙️", "staff-vc", "voice")]),
    ("welcome", "──── ⟪WELCOME⟫ ────", False, [("🛤️", "invite-tracker", "text"), ("👋", "welcome", "text"), ("🕊️", "goodbye", "text")]),
    ("verification", "──── ⟪VERIFICATION⟫ ────", False, [("✅", "verification", "text")]),
    ("important", "──── ⟪IMPORTANT⟫ ────", False, [("📚", "rules", "text"), ("📣", "announcements", "text"), ("📊", "sab-leaks", "text"), ("🚀", "server-boosts", "text"), ("⚡", "boosters-rewards", "text"), ("📊", "polls", "text"), ("⚠️", "scammers", "text"), ("📝", "applications", "text"), ("🔄", "server-updates", "text"), ("🏅", "hall-of-fame", "text"), ("🎬", "content", "text"), ("🎟️", "support-ticket", "text")]),
    ("middleman", "──── ⟪MIDDLEMAN⟫ ────", False, [("💫", "verified-middleman", "text"), ("🎫", "middleman-ticket", "text"), ("✅", "middleman-vouches", "text")]),
    ("giveaways", "──── ⟪GIVEAWAYS⟫ ────", False, [("🎉", "giveaways", "text"), ("🎰", "flash-giveaways", "text"), ("📸", "giveaways-vouches", "text"), ("🎮", "giveaways-vc", "voice")]),
    ("general", "──── ⟪GENERAL⟫ ────", False, [("💬", "general", "text"), ("📸", "media", "text"), ("⚙️", "commands", "text"), ("📊", "levels", "text"), ("🛠️", "suggestions", "text")]),
]
EMOJI_RULES = {"announcement":"📣", "rules":"📚", "poll":"🗳️", "boost":"🚀", "reward":"🎁", "scam":"⚠️", "application":"📝", "update":"🔄", "hall":"🏅", "content":"🎬", "support":"🎟️", "ticket":"🎫", "middleman":"🤝", "verified":"✅", "vouch":"✅", "giveaway":"🎁", "invite":"🛤️", "welcome":"👋", "goodbye":"🕊️", "general":"💬", "chat":"🗨️", "media":"📸", "photo":"📷", "video":"🎥", "clip":"🎞️", "stream":"📡", "meme":"😂", "suggest":"🛠️", "feedback":"📝", "help":"🆘", "faq":"❓", "bug":"🐛", "staff":"🛡️", "log":"🗂️", "trade":"💱", "market":"🛒", "shop":"🏪", "sell":"🏷️", "buy":"💰", "auction":"🔨", "report":"🚨", "level":"📈", "leaderboard":"🏆", "command":"⚙️", "bot":"🤖", "voice":"🔊", "music":"🎵", "game":"🎮", "team":"👥", "match":"⚔️", "tournament":"🏆", "creator":"✨", "collab":"🤝", "event":"📅", "guide":"🧭", "idea":"💡"}
FALLBACK_EMOJIS = ["🌟", "🧩", "🪄", "🧿", "🌈", "🪐", "🦋", "🍀", "🔥", "💎", "🧸", "🪷", "🌙", "🎨", "🪙", "🧠", "🪁", "💫", "🔮", "🧵", "🎪", "🪸", "🪻", "🧃", "🧊", "🧪", "🧭"]


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def slug(value):
    text = clean_text(value, 120).casefold()
    text = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", text)
    text = re.sub(r"^[^\w]+", "", text, flags=re.UNICODE).replace("_", "-")
    text = "".join(c if c.isalnum() or c in "- " else "-" for c in text)
    return "-".join(text.split()).strip("-")[:72] or "channel"


def name_key(value):
    return "".join(c for c in slug(value) if c.isalnum())


def choose_emoji(name, used):
    normalized = slug(name)
    for word, emoji in sorted(EMOJI_RULES.items(), key=lambda pair: len(pair[0]), reverse=True):
        if word in normalized and emoji not in used:
            used.add(emoji)
            return emoji
    offset = sum(ord(c) for c in normalized) % len(FALLBACK_EMOJIS)
    for i in range(len(FALLBACK_EMOJIS)):
        emoji = FALLBACK_EMOJIS[(offset + i) % len(FALLBACK_EMOJIS)]
        if emoji not in used:
            used.add(emoji)
            return emoji
    return "✨"


def ai_client():
    token = os.getenv("GROQ_API_KEY")
    if not token:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=token)


@asynccontextmanager
async def lifespan(app):
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
        permissions = int(item.get("permissions", 0))
        if not (permissions & 0x8 or permissions & 0x20):
            continue
        gid = int(item["id"])
        has_bot = bot.get_guild(gid) is not None
        result.append({"id": gid, "name": item["name"], "icon": item.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={gid}"})
    return {"guilds": result}


def get_guild(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    if guild.me is None or not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles")
    return guild


def safe_state(guild):
    return {
        "name": guild.name,
        "categories": [
            {"name": category.name, "channels": [channel.name for channel in category.channels]}
            for category in guild.categories[:30]
        ],
    }


def core_plan():
    categories = []
    for _, name, staff_only, definitions in CORE:
        channels = [{"name": f"〔{emoji}〕・{channel_name}", "type": kind, "topic": ""}
                    for emoji, channel_name, kind in definitions]
        categories.append({"name": name, "staff_only": staff_only, "channels": channels})
    return categories


def sanitize_plan(raw_plan, prompt):
    """Keep the AI's prompt-specific design, while enforcing safe names, order and uniqueness."""
    if not isinstance(raw_plan, dict):
        raw_plan = {}
    roles = []
    for item in (raw_plan.get("roles") if isinstance(raw_plan.get("roles"), list) else [])[:8]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 80)
        if not name or name.casefold() in {"everyone", "here", "admin", "administrator", "owner", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name, "color": max(0, min(color, 0xFFFFFF)),
                      "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})

    categories = core_plan()
    seen_category_names = {name_key(item["name"]) for item in categories}
    seen_channel_names = {name_key(channel["name"]) for item in categories for channel in item["channels"]}
    raw_categories = raw_plan.get("categories") if isinstance(raw_plan.get("categories"), list) else []
    voice = []
    for item in raw_categories[:8]:
        if not isinstance(item, dict):
            continue
        category_name = clean_text(item.get("name"), 90)
        category_key = name_key(category_name)
        # AI cannot create a duplicate or reorder/replace a fixed foundation.
        if not category_key or category_key in seen_category_names:
            continue
        if any(category_key == name_key(core_name) for _, core_name, _, _ in CORE):
            continue
        seen_category_names.add(category_key)
        text_channels = []
        channel_specs = item.get("channels") if isinstance(item.get("channels"), list) else []
        for channel in channel_specs[:12]:
            if not isinstance(channel, dict):
                continue
            channel_slug = slug(channel.get("name"))
            channel_key = name_key(channel_slug)
            if not channel_key or channel_key in seen_channel_names:
                continue
            seen_channel_names.add(channel_key)
            kind = "voice" if str(channel.get("type", "text")).casefold() == "voice" else "text"
            topic = clean_text(channel.get("topic"), 900) if kind == "text" else ""
            icon = choose_emoji(channel_slug, set())
            spec = {"name": f"〔{icon}〕・{channel_slug}", "type": kind, "topic": topic}
            if kind == "voice":
                voice.append(spec)
            else:
                text_channels.append(spec)
        if text_channels:
            categories.append({"name": category_name, "staff_only": False, "channels": text_channels})

    # Always provide a general voice room; AI-specified voice rooms go in this final section.
    if not any("communityvoice" == name_key(item["name"]) for item in voice):
        voice.insert(0, {"name": "〔🎙️〕・community-voice", "type": "voice", "topic": ""})
    categories.append({"name": "🎙️ : VOICE LOUNGE : 🎧", "staff_only": False, "channels": voice})
    summary = clean_text(raw_plan.get("summary") or f"AI-designed layout for: {prompt}", 450)
    return {"summary": summary, "roles": roles, "categories": categories}


async def generate_plan(guild, prompt):
    """Use the configured LLM to design for any subject from the user's actual prompt."""
    server_state = safe_state(guild)
    system_message = f"""
You are the built-in AI Discord server architect. Carefully read and follow the user's ENTIRE prompt.
Design for ANY requested subject: games, creators, businesses, schools, clubs, fan communities, support servers, or something else. Do not assume a platform or topic that the user did not state. In particular, never inject Roblox, Minecraft, or any named game unless the user asked for it. Never add unrelated game-specific channels.
Return only a valid JSON object with keys summary, roles, categories. The app itself creates fixed ordered foundations: STAFF GENERAL (private), WELCOME, VERIFICATION, IMPORTANT, MIDDLEMAN, GIVEAWAYS, GENERAL (ends at Suggestions). Do not return or duplicate those. Then return only useful prompt-specific categories in the order that makes sense. Put text channels in those categories; any voice channels you request will be moved to one final VOICE LOUNGE category by the app. Do not create a category called Voice Lounge yourself.
Use concise, tasteful category titles and channel slugs, relevant emojis, and helpful short text-channel topics. Avoid filler, redundant purposes, and duplicate names. Roles should be ordinary community roles only; never grant permissions or suggest administrator/owner roles. Don't duplicate the current server's existing channels: {json.dumps(server_state, ensure_ascii=False)}
Schema example only (do not copy unless it fits the prompt): {{"summary":"A tailored server layout","roles":[{{"name":"Member","color":"5865F2","hoist":false,"mentionable":false}}],"categories":[{{"name":"✨ : YOUR COMMUNITY : ✨","channels":[{{"name":"topic-chat","type":"text","topic":"A short useful description"}},{{"name":"hangout-voice","type":"voice"}}]}}]}}
Limits: max 8 roles, 8 custom categories, 12 channels per category. Be specific to the exact user request.
"""
    response = await ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": system_message}, {"role": "user", "content": prompt}],
        temperature=0.25,
        max_tokens=4500,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    try:
        plan = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI returned invalid JSON: {exc}") from exc
    return sanitize_plan(plan, prompt)


def is_category(channel):
    return isinstance(channel, discord.CategoryChannel)


def is_regular_channel(channel):
    return not is_category(channel) and isinstance(channel, discord.abc.GuildChannel)


async def delete_existing_layout(guild):
    # Destructive reset is only called after the manager presses the explicit confirm button.
    for channel in list(guild.channels):
        if is_regular_channel(channel):
            await channel.delete(reason="User-confirmed Rynnzyr rebuild")
            await asyncio.sleep(0.2)
    for category in reversed(list(guild.categories)):
        await category.delete(reason="User-confirmed Rynnzyr rebuild")
        await asyncio.sleep(0.2)


async def build_fresh_layout(guild, plan):
    await delete_existing_layout(guild)
    created_ids, created = [], []
    role_specs = list(plan.get("roles", []))
    if not any("staff" in role.get("name", "").casefold() for role in role_specs):
        role_specs.append({"name": "Staff", "color": 0x5865F2, "hoist": False, "mentionable": False})
    roles = {}
    for spec in role_specs:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr")
            created_ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        roles[role.name.casefold()] = role
    staff_role = roles.get("staff") or discord.utils.get(guild.roles, name="Staff")

    # Categories are created top-level, sequentially: this preserves intended order and
    # avoids illegal category nesting or unsupported bulk-position APIs.
    for spec in plan["categories"]:
        overwrites = {}
        if spec.get("staff_only"):
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Fresh Rynnzyr layout")
        created_ids.append(f"category:{category.id}")
        created.append(f"Category: {category.name}" + (" (staff-only)" if spec.get("staff_only") else ""))
        for channel_spec in spec["channels"]:
            if channel_spec["type"] == "voice":
                channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Fresh Rynnzyr layout")
            else:
                channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec.get("topic") or None, reason="Fresh Rynnzyr layout")
            created_ids.append(f"channel:{channel.id}")
            created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            await asyncio.sleep(0.2)
    undo_snapshots[guild.id] = created_ids
    return created


def make_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — AI server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if item["type"] == "voice" else "# ") + item["name"] for item in category["channels"]]
        if category.get("staff_only"):
            lines.append("🔒 Staff-only — access through Staff role")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="WARNING: confirmation permanently deletes all existing channels and categories.")
    return embed


class RebuildView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.done = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requesting manager can confirm this destructive rebuild.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Delete all channels & rebuild", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def rebuild(self, interaction, button):
        if self.done:
            await interaction.response.send_message("This blueprint was already handled.", ephemeral=True)
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Rebuild confirmed. Removing old channels and creating the ordered layout…", view=self)
        try:
            changes = await build_fresh_layout(self.guild, self.plan)
            summary = "\n".join(f"• {line}" for line in changes[:35])
            await interaction.followup.send(f"✅ **Fresh layout created.**\n{summary}", ephemeral=True)
        except Exception as exc:
            print(f"Fresh rebuild failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send(f"Rebuild stopped: {type(exc).__name__}: {str(exc)[:600]}. Some existing channels may already be deleted; inspect the server before retrying.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction, button):
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Rebuild cancelled. No server changes were made.", embed=None, view=self)


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(get_guild(req.guild_id), req.prompt)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    raise HTTPException(409, "Destructive rebuild is only available after explicit confirmation in the Discord preview.")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = get_guild(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    deleted = 0
    for entry in reversed(ids):
        kind, raw_id = entry.split(":", 1)
        item = discord.utils.get(guild.roles, id=int(raw_id)) if kind == "role" else guild.get_channel(int(raw_id))
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr")
                deleted += 1
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                pass
    return {"success": True, "deleted": deleted}


@bot.tree.command(name="ping", description="Check that Rynnzyr is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Rynnzyr is online and ready.", ephemeral=True)


@bot.tree.command(name="design", description="Preview and rebuild your community server")
@app_commands.describe(prompt="Describe what kind of community server you want")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
        return
    me = interaction.guild.me
    if me is None or not (me.guild_permissions.manage_channels and me.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        warning = "**Destructive rebuild warning:** confirming permanently deletes every existing channel and category, including all messages. Roles are kept. Nothing changes until you press the red button."
        await interaction.followup.send(warning, embed=make_embed(interaction.guild, plan), view=RebuildView(interaction.guild, plan, interaction.user.id), ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't design that layout. Check Railway logs and AI configuration."
        await interaction.followup.send(message[:1800], ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online as {bot.user}; synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Command sync failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
