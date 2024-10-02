import asyncio
from datetime import datetime, timedelta, timezone
from interactions import Client, Intents, listen, slash_command, SlashContext, OptionType, slash_option, ActionRow, Button, ButtonStyle, StringSelectMenu, Guild
from interactions.api.events import Component
import os
from party_type import PartyTypeInfo, get_roles_list, resolve_party_type, get_supported_party_types, get_party_type, display_quantity
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Set environment variables
token= os.environ.get("DISCORD_TOKEN")
database_url = os.environ.get("DATABASE_URL")

# Create client for Discord and MongoDB
bot = Client(intents=Intents.DEFAULT)
mongo = MongoClient(database_url)

# Test connection to database
try:
    mongo.admin.command('ping')
    print("Pinged database. You have successfully connected to MongoDB!")
except Exception as e:
    print(e)

# Set database and collections
db = mongo.chapaa
parties_collection = db["parties"]
users_collection = db["users"]

# Create a sequence collection
sequence_collection = db['sequence']

# Get next value in sequence
def get_next_sequence_value(sequence_name):
    result = sequence_collection.find_one_and_update(
        {'ID': sequence_name},
        {'$inc': {'seq': 1}},
        return_document=True
    )
    return result['seq']

# Get current time in Eastern
def get_time():
    return (datetime.utcnow() + timedelta(hours=-5)).strftime('%I:%M %p')

# Party class
class Party:
    def __init__(self, ID, Status, Server, Type, Quantity, Host, Time=None, Multi=None,Roles=None, MessageID=None, ChannelID=None, Responses=None, **kwargs):
        self.ID = ID
        self.Status = Status if Status is not None else "Open"
        self.Server = Server
        self.Type = Type
        self.Quantity = Quantity
        self.Host = Host
        self.Time = Time
        self.Multi = Multi if Multi is not None else True
        self.Roles = Roles if Roles is not None else PartyTypeInfo[Type]["Roles"]
        self.Roles.update(kwargs)
        self.MessageID = MessageID if MessageID is not None else ""
        self.ChannelID = ChannelID if ChannelID is not None else ""
        self.Responses = Responses if Responses is not None else []

    def __str__(self):
        return f"Party(ID={self.ID}, Server={self.Status}, Status={self.Server}, Type={self.Type}, Quantity={self.Quantity}, Host={self.Host}, Time={self.Time}, Multi={self.Multi}, Roles={self.Roles}, MessageID={self.MessageID}, ChannelID={self.ChannelID}, Responses={self.Responses})"
    
    def get_party_type(Type):
        return PartyTypeInfo.get(Type, {})

    def has_user_signed_up(self, user_id):
        for role in self.Roles.values():
            if user_id in role:
                return True
        return False

    def set_user_id_for_role(self, role, user_id):
        if role in self.Roles:
            role_list = self.Roles[role]
            if "Open" in self.Roles[role]:
                open_index = role_list.index("Open")
                role_list[open_index] = user_id
    
    def remove_user_from_role(self, user_id):
       for role, role_list in self.Roles.items():
           if user_id in role_list:
               user_index = role_list.index(user_id)
               role_list[user_index] = "Open"
               return role
           
    def generate_description(self):
        description = f"Hosted by {self.Host}\n"
        
        if self.Time is not None:
            description += f"Start Time: <t:{self.Time}>\n\n"
        else:
            description += "\n"
        
        required_ingredients = PartyTypeInfo.get(self.Type, {}).get("Ingredients", {})

        for role, members in self.Roles.items():
            description += f"**{role}:** {required_ingredients.get(role, 'No ingredients required')}\n"
            
            if members:
                for member in members:
                    description += f"- {member}\n"

        return description

async def edit_message(self, ctx, message_id: int):
    message = await ctx.channel.fetch_message(message_id)
    description = self.generate_description()
    now = get_time()
    embed = {
        "title": f"({self.Status}) {self.Server} {self.Quantity}x {self.Type} Party" if self.Quantity is not None else f"({self.Status}) {self.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(self.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {self.ID} • Last updated at {now} Eastern"
        }
    }
    components: list[ActionRow] = [
        ActionRow(
            Button(
                style=ButtonStyle.GREEN,
                label="Sign Up",
                custom_id="signup",
            ),
            Button(
                style=ButtonStyle.RED,
                label="Unsign Up",
                custom_id="unsignup",
            )
        )
    ]
    await message.edit(embed=embed,components=components)

# Command ping
@slash_command(
        name="ping",
        description="Ping Lil Simp (Administrators only)",
)

async def ping(ctx: SlashContext):
    if ctx.author.guild_permissions.administrator:
        await ctx.send(f"<@&1156819064170229861>")
    else:
        await ctx.send("<@{ctx.author.id}>, you do not have permission to use this command.", ephemeral=True)

# Command party types
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="types",
        sub_cmd_description="Show party types",
)
async def types(ctx: SlashContext):
    description = "The following party types are supported:\n\n* "
    description += '\n* '.join(sorted(get_supported_party_types()))
    description += "\n\nPlease reach out to <@838472003031793684> to request a new party type."
    now = get_time()
    embed = {
        "title": "Party Types",
        "description": description,
        "thumbnail": {
            "url": "https://cdn.discordapp.com/avatars/1167995384526807101/7b70962d167b56169e6b46e6d7c2892e.png",
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"Last updated at {now} Eastern"
        }
    }
    await ctx.send(embed=embed, ephemeral=True, delete_after=60)

# Command create
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="create",
        sub_cmd_description="Create a Palia Party",
)
@slash_option(
    name="type",
    description="Type of party",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="quantity",
    description="Quantity to be made",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="server",
    description="Palia server (NA, EU, or PA)",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="host",
    description="In game name of host",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="time",
    description="Party's planned start time (use https://www.unixtimestamp.com)",
    required=False,
    opt_type=OptionType.INTEGER
)
@slash_option(
    name="multi",
    description="Whether player can have multiple roles (true/false)",
    required=False,
    opt_type=OptionType.BOOLEAN
)
async def create(ctx: SlashContext, type: str, quantity: str, server: str, host: str, time: int = None, multi: bool = True):
    global party

    if ctx.channel.type != 11:
        error_message = await ctx.send(f"<@{ctx.author.id}>, please use #palia-parties channel to post parties.", ephemeral=True, delete_after=15)
        return

    if "palia-parties" not in ctx.channel.parent_channel.name.lower():
        error_message = await ctx.send(f"<@{ctx.author.id}>, please use #palia-parties channel to post parties.", ephemeral=True, delete_after=15)
        return

    resolved_party_type = resolve_party_type(type)
    if resolved_party_type:
        type = resolved_party_type
    else:
        supported_types_str = ', '.join(get_supported_party_types())
        error_message = await ctx.send(f"<@{ctx.author.id}>, sorry {type} party type is not supported.\nThe following party types are currently supported: {supported_types_str}", ephemeral=True, delete_after=15)
        return
    
    if display_quantity(type) == False:
        quantity = None

    next_id = get_next_sequence_value('item_id')
        
    party = Party(ID=next_id, Status="Open", Server=server, Type=type, Quantity=quantity, Host=host, Time=time, Multi=multi, Roles=None)
    description = party.generate_description()
    now = get_time()
    embed = {
        "title": f"({party.Status}) {party.Server} {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Server} {party.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(party.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {party.ID} • Last updated at {now} Eastern"
        }
    }
    
    components: list[ActionRow] = [
        ActionRow(
            Button(
                style=ButtonStyle.GREEN,
                label="Sign Up",
                custom_id="signup",
            ),
            Button(
                style=ButtonStyle.RED,
                label="Unsign Up",
                custom_id="unsignup",
            )
        )
    ]

    posting = await ctx.send(embed=embed,components=components)
    await ctx.channel.edit(name=f"({party.Status}) {party.Server} {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party")
    party.MessageID = posting.id
    party.ChannelID = posting.channel.id

    party_data = {
        "ID": party.ID,
        "Status": party.Status,
        "Type": party.Type,
        "Quantity": party.Quantity,
        "Server": party.Server,
        "Host": party.Host,
        "Time": party.Time,
        "Multi": party.Multi,
        "Roles": party.Roles,
        "MessageID": party.MessageID,
        "ChannelID": party.ChannelID,
        "Responses": []
    }
    parties_collection.insert_one(party_data)

    role_name = get_party_type(type)
    ping = f"<@&{guild_roles_data[ctx.guild_id][role_name]['id']}>"
    channel = bot.get_channel(posting.channel.id)
    await bot.get_channel(posting.channel.id).send(ping)

    party = None

@listen(Component)
async def on_component(event: Component):
    ctx = event.ctx
    signup_message = None
    party = None

    async def retrieve_party(message_id, action):
        nonlocal party
        if action == "signup" or action == "unsignup":
            result = parties_collection.find_one({"MessageID": message_id})
        elif action == "role":
            result = parties_collection.find_one({"Responses": {"$elemMatch": {"$eq": message_id}}})
        party = Party(ID=result['ID'], Status=result['Status'], Server=result['Server'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
        return party

    match ctx.custom_id:
        case "signup":
            await retrieve_party(ctx.message.id, "signup")
            if party.has_user_signed_up(f"<@{ctx.author.id}>") and party.Multi == False:
                await ctx.send(f"<@{ctx.author.id}>, you have already signed up for a role. The party host is limiting users to one role. Please remove your current role to switch roles.", ephemeral=True, delete_after=15)
            else:
                roles_list = get_roles_list(party.Type)
                components = StringSelectMenu(
                    roles_list,
                    placeholder="Choose your role",
                    custom_id="role"
                    )
                signup_message = await ctx.send(f"<@{ctx.author.id}>",components=components, ephemeral=True, delete_after=15)
                parties_collection.update_one({"MessageID": party.MessageID}, {"$push":{"Responses": signup_message.id}})

        case "unsignup":
            await retrieve_party(ctx.message.id, "unsignup")
            while party.has_user_signed_up(f"<@{ctx.author.id}>"): 
                party.remove_user_from_role(f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            confirmation = await ctx.send(f"<@{ctx.author.id}>, you have been removed from the party.", ephemeral=True, delete_after=3)

        case "role":
            await retrieve_party(ctx.message.id, "role")
            selected_role = ctx.values[0]
            party.set_user_id_for_role(selected_role, f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            await ctx.edit_origin(content=f"<@{ctx.author.id}>, you have been added to {selected_role}", components=[])
            
        case "refresh":
            await leaderboard(ctx)
            await ctx.message.delete()

# Notify command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="notify",
        sub_cmd_description="Notify users that party is starting",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def notify(ctx: SlashContext, id: int):
    user_list = []

    result = parties_collection.find_one({"ID": id})
    party = Party(ID=result['ID'], Status=result['Status'], Server=result['Server'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])


    for role_list in party.Roles.values():
        for role in role_list:
            if role != "Open" and role not in user_list:
                user_list.append(role)
    
    user_list_str = ', '.join(user_list)               

    await ctx.send(f"The party is starting now! Please add **{party.Host}** in game and report to their house. {user_list_str}")

# Close command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="close",
        sub_cmd_description="Close a party and record user participation",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def close(ctx: SlashContext, id: int):
    result = parties_collection.find_one({"ID": id})
    party = Party(ID=result['ID'], Status=result['Status'], Server=result['Server'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])

    if ctx.channel_id != result["ChannelID"]:
        error_message = await ctx.send(f"<@{ctx.author.id}>, parties must be closed from their respective thread.", ephemeral=True, delete_after=15)
        return

    if result['Status'] == "Closed":
        error_message = await ctx.send(f"Error: The party has already been closed and participation has already been recorded.", ephemeral=True, delete_after=15)
        return
    
    user_list = []
    for role_list in party.Roles.values():
        for role in role_list:
            if role != "Open" and role not in user_list:
                users_collection.update_one({"ID": role}, {"$push": {"Parties": party.ID}},upsert=True)
                user_list.append(role)
    
    party.Status = "Closed"
    parties_collection.update_one({"ID": id},{"$set": {"Status": "Closed"}})

    description = party.generate_description()
    now = get_time()
    embed = {
        "title": f"({party.Status}) {party.Server} {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Server} {party.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(party.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {party.ID} • Last updated at {now} Eastern"
        }
    }

    oldchannel = bot.get_channel(party.ChannelID)
    target_message = await oldchannel.fetch_message(party.MessageID)
    await target_message.edit(embed=embed,components=[])
    await ctx.channel.edit(name=f"({party.Status}) {party.Server} {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party")
    confirmation = await ctx.send(f"The party has finished and participation has been recorded :partying_face:")
    await ctx.channel.edit(locked=True)

# Update command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="update",
        sub_cmd_description="Update a party",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
@slash_option(
    name="host",
    description="In game name of host",
    required=False,
    opt_type=OptionType.STRING
)
@slash_option(
    name="quantity",
    description="Quantity to be made",
    required=False,
    opt_type=OptionType.STRING
)
@slash_option(
    name="time",
    description="Party's planned start time (use https://www.unixtimestamp.com)",
    required=False,
    opt_type=OptionType.INTEGER
)
async def update(ctx: SlashContext, id: int, host: str = None, quantity: str = None, time: int = None):
    result = parties_collection.find_one({"ID": id})

    if result == None:   
        error_message = await ctx.send(f"<@{ctx.author.id}>, party not found. Please ensure you are specifying a valid Party ID.", ephemeral=True, delete_after=15)
        return

    if ctx.channel_id != result["ChannelID"]:
        error_message = await ctx.send(f"<@{ctx.author.id}>, parties must be deleted from their respective thread.", ephemeral=True, delete_after=15)
        return
    
    if result["Status"] != "Open":
        error_message = await ctx.send(f"<@{ctx.author.id}>, only Open parties may be updated.", ephemeral=True, delete_after=15)
        return
    
    update_data = {}

    if host is not None and result ["Host"] != host:
        update_data["Host"] = host

    if quantity is not None and result ["Quantity"] != quantity:
        update_data["Quantity"] = quantity
    
    if time is not None and result ["Time"] != time:
        update_data["Time"] = time

    if update_data:
        parties_collection.update_one({"ID": id}, {"$set": update_data})
        await ctx.send(f"<@{ctx.author_id}>, Party {id} has been updated. Changes will reflect on next signup/unsignup.", ephemeral=True, delete_after=15)
    else:
        await ctx.send(f"<@{ctx.author_id}>, no updates to Party {id} are needed based on input.", ephemeral=True, delete_after=15)

# Cancel command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="cancel",
        sub_cmd_description="Cancel a party",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def cancel(ctx: SlashContext, id: int):
    result = parties_collection.find_one({"ID": id})

    if result == None:
        error_message = await ctx.send(f"<@{ctx.author.id}>, party not found. Please ensure you are specifying a valid Party ID.", ephemeral=True, delete_after=15)
        return

    if ctx.channel_id != result["ChannelID"]:
        error_message = await ctx.send(f"<@{ctx.author.id}>, parties must be deleted from their respective thread.", ephemeral=True, delete_after=15)
        return
    
    if result["Status"] != "Open":
        error_message = await ctx.send(f"<@{ctx.author.id}>, only Open parties may be canceled.", ephemeral=True, delete_after=15)
        return

    result = parties_collection.delete_one({"ID": id})

    if result.deleted_count != 1:
        error_message = await ctx.send(f"<@{ctx.author.id}>, party unable to be canceled for unknown reason.", ephemeral=True, delete_after=15)
        return
    
    warning_message = await ctx.send(f"Party {id} has been canceled. This thread will self destruct in 30 seconds.")
    await asyncio.sleep(30)
    await warning_message.channel.delete()

# Stats command
@slash_command(
        name="stats",
        description="Displays personal stats for party participation",
)

async def stats(ctx: SlashContext):
    user = users_collection.find_one({"ID": f"<@{ctx.author_id}>"})
    user_parties = user.get("Parties", []) if user else []

    result = users_collection.aggregate([
        {
            '$project': {
                'ID': 1,
                'PartyCount': {'$size': {'$ifNull': ['$Parties', []]}}
            }
        },
        {
            '$sort': {'PartyCount': -1}
        }
    ])
    rank = next((i + 1 for i, doc in enumerate(result) if doc.get('ID') == f"<@{ctx.author_id}>"), None)

    parties = 0
    parties_type = {}
    for party_id in user_parties:
        party = parties_collection.find_one({"ID": party_id}, {"Type": 1})
        if party:
            parties += 1
            party_type = party.get("Type")
            if party_type not in ['Bug Catching', 'Fishing', 'Foraging', 'Hunting', 'Mining']:
                party_type = 'Cooking'
            parties_type[party_type] = parties_type.get(party_type, 0) + 1
    sorted_parties_type = dict(sorted(parties_type.items(), key=lambda x: x[1], reverse=True))

    description = f"**Rank**: #{rank} of {ctx.guild.member_count}\n\n"

    for party_type, count in sorted_parties_type.items():
        description += f"**{party_type.ljust(15)}**: {count}\n"
    
    description += "-----------------\n"
    description += f"**Total Parties**: {parties}"
    
    now = get_time()
    embed = {
        "title": f"User Statistics",
        "description": description,
        "thumbnail": {
            "url": ctx.author.avatar_url,
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"Last updated at {now} Eastern"
        }
    }
    await ctx.send(embed=embed, ephemeral=True)

@listen()
async def on_message_create(event):
    if event.message.author.bot:
        return
    users_collection.update_one({"ID": f"<@{event.message.author.id}>"}, {'$inc': {'MessageCount':1}}, upsert=True)

async def check_voice_loop():
    while True:
        await check_channels()
        await asyncio.sleep(60)

async def check_channels():
    for guild in bot.guilds:
        for channel in guild.channels:
            if channel.type == 2:
                voice_member_ids = getattr(channel, '_voice_member_ids', [])
                for member_id in voice_member_ids:
                    users_collection.update_one({"ID": f"<@{member_id}>"}, {'$inc': {'VoiceMins':1}}, upsert=True)

# Bot is ready
@listen()
async def on_startup():
    print("Bot is ready and online!")

    global guild_roles_data
    guild_roles_data = {}

    for guild in bot.guilds:
        guild_roles = guild.roles

        roles_info = {
            role.name: {
                "id": role.id
            }
            for role in guild_roles
        }
        
        guild_roles_data[guild.id] = roles_info

    await check_voice_loop()

# Start bot
bot.start(token)
