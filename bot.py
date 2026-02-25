import discord
from discord import app_commands
from discord.ext import commands
import configparser
import random
import string
import json
import os
import asyncio
from datetime import datetime, timedelta

os.makedirs('database', exist_ok=True)

CONFIG_FILE = 'config.ini'
VALID_KEYS_FILE = 'database/valid_keys.json'
USER_DB_FILE = 'database/user_database.json'
ADMINS_FILE = 'database/admins.json'

if not os.path.exists(CONFIG_FILE):
    default_config = configparser.ConfigParser()
    default_config['Discord'] = {'Token': 'YOUR_BOT_TOKEN_HERE'}
    default_config['Settings'] = {
        'slot_id': 'YOUR_CATEGORY_ID_HERE',
        'Main_Admin_Id': 'YOUR_MAIN_ADMIN_ID_HERE',
        'Gateway_Channel_Id': 'YOUR_GATEWAY_CHANNEL_ID_HERE'
    }
    default_config['Embeds'] = {
        'Thumbnail_Url': 'YOUR_THUMBNAIL_URL_HERE'
    }
    with open(CONFIG_FILE, 'w') as f:
        default_config.write(f)
    print("config.ini created. Fill in Token, slot_id, Main_Admin_Id, and Thumbnail_Url then restart.")
    exit()

for db_file in [VALID_KEYS_FILE, USER_DB_FILE, ADMINS_FILE]:
    if not os.path.exists(db_file):
        with open(db_file, 'w') as f:
            json.dump({}, f, indent=4)

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

TOKEN = config['Discord']['Token']
SLOT_CATEGORY_ID = int(config['Settings']['slot_id'])
MAIN_ADMIN_ID = int(config['Settings']['Main_Admin_Id'])
GATEWAY_CHANNEL_ID = int(config['Settings']['Gateway_Channel_Id'])
THUMBNAIL_URL = config['Embeds']['Thumbnail_Url']
FOOTER_TEXT = "Shampoo MP"

KEY_TYPE_LICENSE = "license"
KEY_TYPE_LICENSE_LIFETIME = "license_lifetime"
KEY_TYPE_EVERYONE = "everyone_ping"
KEY_TYPE_HERE = "here_ping"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def is_admin(user_id: int):
    if user_id == MAIN_ADMIN_ID:
        return True
    admins = load_json(ADMINS_FILE)
    return str(user_id) in admins

def generate_key():
    letters = random.choices(string.ascii_uppercase, k=4)
    numbers = random.choices(string.digits, k=4)
    combined = letters + numbers
    random.shuffle(combined)
    return f"Shampoo-MP-{''.join(combined)}"

def time_remaining(expiry_iso):
    delta = datetime.fromisoformat(expiry_iso) - datetime.utcnow()
    if delta.total_seconds() <= 0:
        return "Expired"
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    return f"{days}d {hours}h {minutes}m"

def find_user_by_channel(channel_id: str):
    user_db = load_json(USER_DB_FILE)
    for uid, data in user_db.items():
        if data.get("slot_channel_id") == channel_id:
            return uid, data
    return None, None

def build_embed(title, description, color):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)
    return embed

def guild_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

async def apply_slot_permissions(channel: discord.TextChannel, owner: discord.Member, guild: discord.Guild):
    await channel.set_permissions(guild.default_role, overwrite=discord.PermissionOverwrite(
        read_messages=True,
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        add_reactions=False,
        mention_everyone=False
    ))
    await channel.set_permissions(owner, overwrite=discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        add_reactions=True,
        manage_channels=True,
        create_public_threads=False,
        create_private_threads=False,
        mention_everyone=False
    ))
    await channel.set_permissions(guild.me, overwrite=discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True,
        manage_channels=True,
        manage_permissions=True
    ))

async def send_slot_created_embed(channel: discord.TextChannel, owner: discord.Member, created_at: str, expiry_iso: str, duration_label: str):
    is_lifetime = expiry_iso is None
    if is_lifetime:
        expiry_text = "♾️ Never — Lifetime Slot"
    else:
        expiry_ts = int(datetime.fromisoformat(expiry_iso).timestamp())
        expiry_text = f"<t:{expiry_ts}:F> (<t:{expiry_ts}:R>)"

    created_ts = int(datetime.fromisoformat(created_at).timestamp())

    embed = discord.Embed(
        title="🎰 Shampoo MP — Slot Created",
        description=f"Welcome {owner.mention}! Your slot is now active and ready to use.",
        color=0xFF4444
    )
    embed.add_field(name="👤 Slot Owner", value=f"{owner.mention} (`{owner.id}`)", inline=True)
    embed.add_field(name="📋 Channel", value=channel.mention, inline=True)
    embed.add_field(name="📅 Created At", value=f"<t:{created_ts}:F>", inline=False)
    embed.add_field(name="⏳ Duration", value=duration_label, inline=True)
    embed.add_field(name="🔚 Expires", value=expiry_text, inline=True)
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━━\n📌 Quick Commands",
        value=(
            "`/ping` — Send an @here or @everyone ping\n"
            "`/stats` — View your slot statistics\n"
            "`/redeem` — Redeem ping keys"
        ),
        inline=False
    )
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)
    await channel.send(embed=embed)

@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.CustomActivity(name="Shampoo MP"))
    print(f"Logged in as {bot.user}")


@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(GATEWAY_CHANNEL_ID)
    if channel is None:
        return
    member_count = member.guild.member_count
    joined_ts = int(member.joined_at.timestamp()) if member.joined_at else int(__import__('datetime').datetime.utcnow().timestamp())
    embed = discord.Embed(
        title="🎉 Welcome to Shampoo MP!",
        description=(
            f"Hey {member.mention}, welcome to **Shampoo MP**!\n\n"
            f"We're glad to have you here. Browse our slots, grab a key, and set up your own space.\n\n"
            f"📌 Use `/redeem` to activate a slot key.\n"
            f"📣 Use `/ping` to ping your slot audience.\n"
            f"📊 Use `/stats` to view your slot stats."
        ),
        color=0xFF4444
    )
    embed.add_field(name="👤 Member", value=f"{member.mention} (`{member.id}`)", inline=True)
    embed.add_field(name="📅 Joined At", value=f"<t:{joined_ts}:F>", inline=True)
    embed.add_field(name="👥 Member Count", value=f"**{member_count}** members", inline=False)
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)
    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    channel = member.guild.get_channel(GATEWAY_CHANNEL_ID)
    if channel is None:
        return
    member_count = member.guild.member_count
    embed = discord.Embed(
        title="👋 Member Left",
        description=(
            f"**{member.name}** has left **Shampoo MP**.\n\n"
            f"We're sorry to see you go. You're always welcome back!"
        ),
        color=0x2b2b2b
    )
    embed.add_field(name="👤 Member", value=f"{member.mention} (`{member.id}`)", inline=True)
    embed.add_field(name="👥 Remaining Members", value=f"**{member_count}** members", inline=False)
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)
    await channel.send(embed=embed)

@bot.tree.command(name="generatekeys", description="Generate keys for slots, @here pings, or @everyone pings")
@app_commands.describe(
    type="Type of key to generate",
    amount="Number of keys to generate",
    duration="Duration in days (only for timed License keys)"
)
@app_commands.choices(type=[
    app_commands.Choice(name="License", value=KEY_TYPE_LICENSE),
    app_commands.Choice(name="License (Lifetime)", value=KEY_TYPE_LICENSE_LIFETIME),
    app_commands.Choice(name="@here Ping", value=KEY_TYPE_HERE),
    app_commands.Choice(name="@everyone Ping", value=KEY_TYPE_EVERYONE),
])
@guild_only()
async def generatekeys(interaction: discord.Interaction, type: str, amount: int, duration: int = None):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    if type == KEY_TYPE_LICENSE and duration is None:
        await interaction.response.send_message("❌ Duration (in days) is required for timed License keys.", ephemeral=True)
        return

    valid_keys = load_json(VALID_KEYS_FILE)
    new_keys = []
    expiry = (datetime.utcnow() + timedelta(days=duration)).isoformat() if (type == KEY_TYPE_LICENSE and duration) else None

    for _ in range(amount):
        key = generate_key()
        while key in valid_keys:
            key = generate_key()
        valid_keys[key] = {
            "type": type,
            "duration_days": duration if type == KEY_TYPE_LICENSE else ("Lifetime" if type == KEY_TYPE_LICENSE_LIFETIME else None),
            "expiry": expiry,
            "generated_at": datetime.utcnow().isoformat(),
            "generated_by": str(interaction.user.id),
            "redeemed": False,
            "redeemed_by": None,
            "redeemed_at": None
        }
        new_keys.append(key)

    save_json(VALID_KEYS_FILE, valid_keys)

    type_label = {
        KEY_TYPE_LICENSE: "License",
        KEY_TYPE_LICENSE_LIFETIME: "Lifetime License",
        KEY_TYPE_EVERYONE: "@everyone Ping",
        KEY_TYPE_HERE: "@here Ping"
    }[type]
    duration_text = f" — {duration} day(s) each" if (type == KEY_TYPE_LICENSE and duration) else (" — Lifetime" if type == KEY_TYPE_LICENSE_LIFETIME else "")
    keys_display = "\n".join(f"`{k}`" for k in new_keys)

    await interaction.response.send_message(
        f"**Generated {amount} {type_label} key(s){duration_text}:**\n\n{keys_display}",
        ephemeral=True
    )

@bot.tree.command(name="sendkey", description="Generate and DM a key directly to a user")
@app_commands.describe(user="The user to send the key to", duration="Duration of the key in days")
@guild_only()
async def sendkey(interaction: discord.Interaction, user: discord.Member, duration: int):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    valid_keys = load_json(VALID_KEYS_FILE)
    expiry = (datetime.utcnow() + timedelta(days=duration)).isoformat()

    key = generate_key()
    while key in valid_keys:
        key = generate_key()

    valid_keys[key] = {
        "type": KEY_TYPE_LICENSE,
        "duration_days": duration,
        "expiry": expiry,
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": str(interaction.user.id),
        "sent_to": str(user.id),
        "redeemed": False,
        "redeemed_by": None,
        "redeemed_at": None
    }
    save_json(VALID_KEYS_FILE, valid_keys)

    embed = discord.Embed(
        title="✨ **Shampoo MP** Subscription Key Delivery",
        description=(
            f"Hello **{user.mention}**, your license key has been generated and delivered!\n\n"
            f"🛡️ **Product**\n"
            f"Shampoo MP - Slots\n\n"
            f"🔑 **License Key**\n"
            f"```{key}```\n"
            f"📅 **Duration:** {duration} day(s)\n"
            f"⏳ **Valid Until:** <t:{int(datetime.fromisoformat(expiry).timestamp())}:F>\n\n"
            f"Use `/redeem` followed by your key to activate your slot."
        ),
        color=0xD2B48C
    )
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)

    try:
        await user.send(embed=embed)
        await interaction.response.send_message(f"✅ Key sent to {user.mention} via DM.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ Could not DM {user.mention}. They may have DMs disabled.", ephemeral=True)

@bot.tree.command(name="redeem", description="Redeem a license key or ping key")
@app_commands.describe(key="The key you want to redeem")
@guild_only()
async def redeem(interaction: discord.Interaction, key: str):
    valid_keys = load_json(VALID_KEYS_FILE)
    user_db = load_json(USER_DB_FILE)
    user_id = str(interaction.user.id)

    if key not in valid_keys:
        await interaction.response.send_message("❌ That key is invalid.", ephemeral=True)
        return

    key_data = valid_keys[key]

    if key_data["redeemed"]:
        await interaction.response.send_message("❌ That key has already been redeemed.", ephemeral=True)
        return

    if key_data.get("expiry") and datetime.fromisoformat(key_data["expiry"]) < datetime.utcnow():
        await interaction.response.send_message("❌ That key has expired.", ephemeral=True)
        return

    key_type = key_data.get("type", KEY_TYPE_LICENSE)

    if key_type in [KEY_TYPE_EVERYONE, KEY_TYPE_HERE]:
        if user_id not in user_db or not user_db[user_id].get("active"):
            await interaction.response.send_message("❌ You need an active slot to redeem ping keys.", ephemeral=True)
            return

        ping_field = "everyone_pings" if key_type == KEY_TYPE_EVERYONE else "here_pings"
        ping_label = "@everyone" if key_type == KEY_TYPE_EVERYONE else "@here"

        valid_keys[key]["redeemed"] = True
        valid_keys[key]["redeemed_by"] = user_id
        valid_keys[key]["redeemed_at"] = datetime.utcnow().isoformat()
        save_json(VALID_KEYS_FILE, valid_keys)

        user_db[user_id][ping_field] = user_db[user_id].get(ping_field, 0) + 1
        save_json(USER_DB_FILE, user_db)

        embed = build_embed(
            title="🔔 Ping Key Redeemed",
            description=(
                f"Your **{ping_label} ping** key has been added to your slot!\n\n"
                f"🏷️ **Key:** `{key}`\n"
                f"📣 **Ping Type:** {ping_label}\n"
                f"🔢 **{ping_label} Pings Available:** {user_db[user_id][ping_field]}\n\n"
                f"Use `/ping` in your slot channel to use it."
            ),
            color=0xD2B48C
        )
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message(f"✅ {ping_label} ping key redeemed! Check your DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"✅ {ping_label} ping key redeemed! You now have {user_db[user_id][ping_field]} {ping_label} ping(s).", ephemeral=True)
        return

    if user_id in user_db and user_db[user_id].get("active"):
        await interaction.response.send_message("❌ You already have an active slot.", ephemeral=True)
        return

    guild = interaction.guild
    category = guild.get_channel(SLOT_CATEGORY_ID)

    if category is None or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("❌ Slot category not found. Please contact an admin.", ephemeral=True)
        return

    is_lifetime = key_type == KEY_TYPE_LICENSE_LIFETIME
    channel_name = f"{interaction.user.name.lower().replace(' ', '-')}-slot"
    channel = await guild.create_text_channel(channel_name, category=category)
    await apply_slot_permissions(channel, interaction.user, guild)

    redeemed_at = datetime.utcnow().isoformat()
    expiry_iso = None if is_lifetime else key_data["expiry"]
    duration_label = "Lifetime" if is_lifetime else f"{key_data['duration_days']} day(s)"

    valid_keys[key]["redeemed"] = True
    valid_keys[key]["redeemed_by"] = user_id
    valid_keys[key]["redeemed_at"] = redeemed_at
    save_json(VALID_KEYS_FILE, valid_keys)

    user_db[user_id] = {
        "username": str(interaction.user),
        "user_id": user_id,
        "active": True,
        "key_redeemed": key,
        "redeemed_at": redeemed_at,
        "expiry": expiry_iso,
        "duration_days": "Lifetime" if is_lifetime else key_data["duration_days"],
        "time_remaining": "Lifetime" if is_lifetime else time_remaining(expiry_iso),
        "slot_channel_id": str(channel.id),
        "slot_channel_name": channel_name,
        "guild_id": str(guild.id),
        "guild_name": guild.name,
        "everyone_pings": 0,
        "here_pings": 0
    }
    save_json(USER_DB_FILE, user_db)

    await send_slot_created_embed(channel, interaction.user, redeemed_at, expiry_iso, duration_label)

    dm_embed = build_embed(
        title=":rocket: **Subscription Activated**",
        description=(
            f"Hey {interaction.user.mention}, your slot subscription is now **live**!\n\n"
            f"A dedicated channel has been created exclusively for you — use it to promote your products, services, or anything you'd like to share with the community.\n\n"
            f"📅 **Duration:** {duration_label}\n"
            + (f"⏳ **Expires:** <t:{int(datetime.fromisoformat(expiry_iso).timestamp())}:F>\n" if not is_lifetime else "♾️ **Expires:** Never\n") +
            f"📦 **Your Channel:** {channel.mention}\n\n"
            f"Make the most of your slot and don't hesitate to reach out to staff if you need any assistance!"
        ),
        color=0xD2B48C
    )

    try:
        await interaction.user.send(embed=dm_embed)
        await interaction.response.send_message("✅ Key redeemed! Check your DMs for details.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"✅ Key redeemed! Your slot channel {channel.mention} has been created. (Enable DMs to receive confirmation)", ephemeral=True)

@bot.tree.command(name="make-slot", description="Assign an existing channel as a lifetime slot for a user")
@app_commands.describe(user="The user to assign the slot to", channel="The existing channel to use as their slot")
@guild_only()
async def make_slot(interaction: discord.Interaction, user: discord.Member, channel: discord.TextChannel):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    user_db = load_json(USER_DB_FILE)
    user_id = str(user.id)

    if user_id in user_db and user_db[user_id].get("active"):
        await interaction.response.send_message(f"❌ {user.mention} already has an active slot.", ephemeral=True)
        return

    existing_uid, _ = find_user_by_channel(str(channel.id))
    if existing_uid is not None:
        await interaction.response.send_message("❌ That channel is already registered as a slot.", ephemeral=True)
        return

    await apply_slot_permissions(channel, user, interaction.guild)

    assigned_at = datetime.utcnow().isoformat()

    user_db[user_id] = {
        "username": str(user),
        "user_id": user_id,
        "active": True,
        "key_redeemed": "MANUAL",
        "redeemed_at": assigned_at,
        "expiry": None,
        "duration_days": "Lifetime",
        "time_remaining": "Lifetime",
        "slot_channel_id": str(channel.id),
        "slot_channel_name": channel.name,
        "guild_id": str(interaction.guild.id),
        "guild_name": interaction.guild.name,
        "everyone_pings": 0,
        "here_pings": 0
    }
    save_json(USER_DB_FILE, user_db)

    await send_slot_created_embed(channel, user, assigned_at, None, "Lifetime")

    try:
        dm_embed = build_embed(
            title=":rocket: **Lifetime Slot Activated**",
            description=(
                f"Hey {user.mention}, your **lifetime** slot has been set up by staff!\n\n"
                f"Your dedicated channel is ready to go — use it to promote your products, services, or anything you'd like to share with the community.\n\n"
                f"♾️ **Duration:** Lifetime\n"
                f"📦 **Your Channel:** {channel.mention}\n\n"
                f"Make the most of your slot and don't hesitate to reach out to staff if you need any assistance!"
            ),
            color=0xD2B48C
        )
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        pass

    await interaction.response.send_message(f"✅ {channel.mention} has been assigned as a lifetime slot for {user.mention}.", ephemeral=True)

@bot.tree.command(name="ping", description="Send a @here or @everyone ping in your slot channel")
@app_commands.describe(type="The type of ping to send")
@app_commands.choices(type=[
    app_commands.Choice(name="@here", value="here"),
    app_commands.Choice(name="@everyone", value="everyone"),
])
@guild_only()
async def ping(interaction: discord.Interaction, type: str):
    user_id = str(interaction.user.id)
    user_db = load_json(USER_DB_FILE)

    if user_id not in user_db or not user_db[user_id].get("active"):
        await interaction.response.send_message("❌ You don't have an active slot.", ephemeral=True)
        return

    if str(interaction.channel_id) != user_db[user_id].get("slot_channel_id"):
        await interaction.response.send_message("❌ You can only use `/ping` inside your own slot channel.", ephemeral=True)
        return

    ping_field = "everyone_pings" if type == "everyone" else "here_pings"
    ping_label = "@everyone" if type == "everyone" else "@here"
    current = user_db[user_id].get(ping_field, 0)

    if current <= 0:
        await interaction.response.send_message(f"❌ You have no **{ping_label}** pings remaining. Redeem a ping key to get more.", ephemeral=True)
        return

    user_db[user_id][ping_field] = current - 1
    save_json(USER_DB_FILE, user_db)

    await interaction.response.send_message("**Pinging...**")
    await interaction.channel.send("@here" if type == "here" else "@everyone")

@bot.tree.command(name="stats", description="View your slot statistics")
@guild_only()
async def stats(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_db = load_json(USER_DB_FILE)

    if user_id not in user_db or not user_db[user_id].get("active"):
        await interaction.response.send_message("❌ You don't have an active slot.", ephemeral=True)
        return

    if str(interaction.channel_id) != user_db[user_id].get("slot_channel_id"):
        await interaction.response.send_message("❌ You can only view stats inside your own slot channel.", ephemeral=True)
        return

    data = user_db[user_id]
    everyone_pings = data.get("everyone_pings", 0)
    here_pings = data.get("here_pings", 0)
    is_lifetime = data.get("duration_days") == "Lifetime"

    def ping_status(count):
        if count == 0:
            return f"🔴 **{count}** — No pings remaining"
        elif count <= 2:
            return f"🟡 **{count}** ping(s) remaining"
        else:
            return f"🟢 **{count}** ping(s) remaining"

    if is_lifetime:
        expiry_text = "♾️ **Never** — Lifetime slot"
    else:
        expiry_ts = int(datetime.fromisoformat(data["expiry"]).timestamp())
        expiry_text = f"<t:{expiry_ts}:F> (<t:{expiry_ts}:R>)"

    embed = discord.Embed(
        title="📊 Slot Statistics",
        description=f"Here's an overview of your current slot subscription, {interaction.user.mention}.",
        color=0xD2B48C
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━━\n📣 Ping Allowances",
        value=(
            f"**@everyone Ping**\n{ping_status(everyone_pings)}\n\n"
            f"**@here Ping**\n{ping_status(here_pings)}\n\n"
            f"*Redeem ping keys with `/redeem` to top up.*"
        ),
        inline=False
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━━\n📦 Slot Info",
        value=(
            f"**Channel:** <#{data['slot_channel_id']}>\n"
            f"**Active Since:** <t:{int(datetime.fromisoformat(data['redeemed_at']).timestamp())}:R>\n"
            f"**Expires:** {expiry_text}\n"
            f"**Duration:** {data['duration_days']}"
        ),
        inline=False
    )
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text=FOOTER_TEXT)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="addadmin", description="Add a user as a bot admin")
@app_commands.describe(user="The user to add as admin")
@guild_only()
async def addadmin(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != MAIN_ADMIN_ID:
        await interaction.response.send_message("❌ Only the main admin can add admins.", ephemeral=True)
        return

    admins = load_json(ADMINS_FILE)
    uid = str(user.id)

    if uid in admins:
        await interaction.response.send_message(f"❌ {user.mention} is already an admin.", ephemeral=True)
        return

    admins[uid] = {
        "username": str(user),
        "user_id": uid,
        "added_by": str(interaction.user.id),
        "added_at": datetime.utcnow().isoformat()
    }
    save_json(ADMINS_FILE, admins)
    await interaction.response.send_message(f"✅ {user.mention} has been added as an admin.", ephemeral=True)

@bot.tree.command(name="removeadmin", description="Remove a user from bot admins")
@app_commands.describe(user="The user to remove from admins")
@guild_only()
async def removeadmin(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != MAIN_ADMIN_ID:
        await interaction.response.send_message("❌ Only the main admin can remove admins.", ephemeral=True)
        return

    admins = load_json(ADMINS_FILE)
    uid = str(user.id)

    if uid not in admins:
        await interaction.response.send_message(f"❌ {user.mention} is not an admin.", ephemeral=True)
        return

    del admins[uid]
    save_json(ADMINS_FILE, admins)
    await interaction.response.send_message(f"✅ {user.mention} has been removed from admins.", ephemeral=True)

@bot.tree.command(name="terminateslot", description="Terminate a user's slot channel")
@app_commands.describe(channel="The slot channel to terminate", reason="Reason for termination")
@guild_only()
async def terminateslot(interaction: discord.Interaction, channel: discord.TextChannel, reason: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    user_id, user_data = find_user_by_channel(str(channel.id))

    if user_id is None:
        await interaction.response.send_message("❌ That channel does not appear to be a registered slot channel.", ephemeral=True)
        return

    guild = interaction.guild
    slot_owner = guild.get_member(int(user_id))

    await channel.set_permissions(guild.default_role, overwrite=discord.PermissionOverwrite(read_messages=False))
    if slot_owner:
        await channel.set_permissions(slot_owner, overwrite=discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            embed_links=False,
            attach_files=False,
            add_reactions=False,
            manage_channels=False,
            manage_permissions=False,
            manage_webhooks=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            mention_everyone=False,
            view_channel=False
        ))

    terminated_at = datetime.utcnow()
    deletion_time = terminated_at + timedelta(hours=8)

    termination_embed = discord.Embed(
        title="🚫 Slot Terminated",
        description=(
            f"This slot has been **terminated** by a member of staff.\n\n"
            f"**Slot Owner:** {slot_owner.mention if slot_owner else f'<@{user_id}>'}\n"
            f"**Channel:** {channel.name}\n"
            f"**Terminated By:** {interaction.user.mention}\n"
            f"**Reason:** {reason}\n"
            f"**Terminated At:** <t:{int(terminated_at.timestamp())}:F>\n\n"
            f"The slot owner has had their access revoked. If you believe this termination was made in error, please contact staff immediately."
        ),
        color=0xFF0000
    )
    termination_embed.set_thumbnail(url=THUMBNAIL_URL)
    termination_embed.set_footer(text=f"⏳ This slot channel will be permanently deleted in 8 hours • {FOOTER_TEXT}")

    await channel.send(embed=termination_embed)

    user_db = load_json(USER_DB_FILE)
    if user_id in user_db:
        user_db[user_id]["active"] = False
        user_db[user_id]["terminated"] = True
        user_db[user_id]["terminated_at"] = terminated_at.isoformat()
        user_db[user_id]["terminated_by"] = str(interaction.user.id)
        user_db[user_id]["termination_reason"] = reason
        save_json(USER_DB_FILE, user_db)

    if slot_owner:
        try:
            dm_embed = build_embed(
                title="🚫 Your Slot Has Been Terminated",
                description=(
                    f"Your slot in **{guild.name}** has been terminated by a staff member.\n\n"
                    f"**Reason:** {reason}\n"
                    f"**Terminated At:** <t:{int(terminated_at.timestamp())}:F>\n"
                    f"**Channel Deletion:** <t:{int(deletion_time.timestamp())}:R>\n\n"
                    f"If you believe this was a mistake, please reach out to the server staff."
                ),
                color=0xFF0000
            )
            await slot_owner.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    await interaction.response.send_message(f"✅ Slot `{channel.name}` has been terminated. The channel will be deleted in 8 hours.", ephemeral=True)

    await asyncio.sleep(28800)
    try:
        await channel.delete(reason=f"Slot terminated by {interaction.user} — {reason}")
    except discord.NotFound:
        pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An error occurred while running this command.", ephemeral=True)
        print(f"Command error: {error}")

bot.run(TOKEN)
