# import.standard
import time
import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

# import.thirdparty
import discord
from discord import user_command
from discord.ext import commands, menus, tasks

# import.local
from extra import utils
from extra.menu import MemberSnipeLooping, SnipeLooping, prompt_message_guild, prompt_number
from extra.moderation.fakeaccounts import ModerationFakeAccountsTable
from extra.moderation.firewall import (BypassFirewallTable,
                                       ModerationFirewallTable)
from extra.moderation.moderatednicknames import ModeratedNicknamesTable
from extra.moderation.mutedmember import ModerationMutedMemberTable
from extra.moderation.user_muted_galaxies import UserMutedGalaxiesTable
from extra.moderation.userinfractions import ModerationUserInfractionsTable
from extra.moderation.watchlist import ModerationWatchlistTable
from extra.prompt.menu import Confirm
from extra.useful_variables import banned_links
from mysqldb import DatabaseCore

# variables.id
server_id = int(os.getenv('SERVER_ID', 123))
guild_ids: List[int] = [server_id]
gabs_id = int(os.getenv('GABS_ID', 123))

# variables.role
muted_role_id = int(os.getenv('MUTED_ROLE_ID', 123))
timedout_role_id = int(os.getenv('TIMEDOUT_ROLE_ID', 123))
preference_role_id = int(os.getenv('PREFERENCE_ROLE_ID', 123))
## variables.role.staff
mod_role_id = int(os.getenv('MOD_ROLE_ID', 123))
staff_manager_role_id: int = int(os.getenv('STAFF_MANAGER_ROLE_ID', 123))
admin_role_id: int = int(os.getenv('ADMIN_ROLE_ID', 123))
analyst_debugger_role_id: int = int(os.getenv('ANALYST_DEBUGGER_ROLE_ID', 123))
lesson_manager_role_id: int = int(os.getenv('LESSON_MANAGEMENT_ROLE_ID', 123))
event_manager_role_id = int(os.getenv('EVENT_MANAGER_ROLE_ID', 123))
allowed_roles = [int(os.getenv('OWNER_ROLE_ID', 123)), admin_role_id, staff_manager_role_id, mod_role_id]
## variables.role.restricted
native_centish_role_id = int(os.getenv('NATIVE_CENTISH_ID', 123))
based_role_id = int(os.getenv('BASED_ID', 123))
few_braincells_role_id = int(os.getenv('FEW_BRAINCELLS_ID', 123))
met_dnk_irl_role_id = int(os.getenv('MET_DNK_IRL_ID', 123))
sponsor_role_id = int(os.getenv('SPONSOR_ROLE_ID', 123))
sloth_nation_role_id = int(os.getenv('SLOTH_NATION_ROLE_ID', 123))
frog_catcher_role_id = int(os.getenv('FROG_CATCHER_ROLE_ID', 123))
native_ancient_latin_role_id = int(os.getenv('NATIVE_ANCIENT_LATIN_ID', 123))

# variables.textchannel
mod_log_id = int(os.getenv('MOD_LOG_CHANNEL_ID', 123))
spam_log_channel_id = int(os.getenv('SPAM_LOG_CHANNEL_ID', 123))
ban_appeals_channel_id: int = os.getenv("BAN_APPEALS_CHANNEL_ID", 123)
secret_agent_channel_id = int(os.getenv('SECRET_AGENTS_CHANNEL_ID', 123))
error_log_channel_id = int(os.getenv('ERROR_LOG_CHANNEL_ID', 123))
muted_chat_id = int(os.getenv('MUTED_CHANNEL_ID', 123))
watchlist_disallowed_channels = [int(os.getenv('MUTED_CHANNEL_ID', 123))]
frog_catchers_channel_id: int = int(os.getenv("FROG_CATCHERS_CHANNEL_ID", 123))
teacher_applicant_infraction_thread_id: int = int(os.getenv("TEACHER_APPLICANT_INFRACTION_THREAD_ID", 123))
host_applicant_infraction_thread_id: int = int(os.getenv("HOST_APPLICANT_INFRACTION_THREAD_ID", 123))

# list.scam
scamwords = [
    # steam scam
    "steam gift 50$", "50$ steam gift",
    # links
    "steamncommynity.com", "steamcommunity.com/gift-card/pay/50", "airdrop-stake.com", "xcoin-presale.com", "ainexusca.com", "u.to", "e.vg",
    # numbers
    "+1 (618) 913-0036", "+1 (626) 514-0696", "+1 (814) 813-1670",
    # nicks
    "Nicholas_Wallace2", "Kathryn_Aubry115", "Kathryn_Aubry",
    # other
    "teach 20 interested people on how to earn $50k", "more within 72 hours from the crypto market", "massage me for more info", "if interested send me a direct massage. for more info via", "ONLINE ASSISTANT NEEDED URGENTLY", "Job Opportunity: Online Personal Assistant", "Competitive weekly salary of $900", "I have a nice idea and you can get regular income  $50-100 every month", "$50-100 every month", "Don't miss this exciting opportunity! Apply now", "help first 10 interested people how to earn 30k or more in crypto market within 48 hours but you", "10% of your profits Dm", "Hi, I received a referral link for the pre-market of the X token.", "Exclusive bonuses for early stakers and loyal holders!", "Hurry Up! This is a limited-time event"
]

last_deleted_message = []

moderation_cogs: List[commands.Cog] = [
    ModerationFirewallTable, BypassFirewallTable, ModerationMutedMemberTable, 
    ModerationUserInfractionsTable, ModerationWatchlistTable, ModerationFakeAccountsTable,
    ModeratedNicknamesTable, UserMutedGalaxiesTable
]

class Moderation(*moderation_cogs):
    """ Moderation related commands. """

    INVITE_TYPES = [
        "discord.gg/", "discord.com/invites/",
        "discord.gg/events/", "discord.com/events/"
    ]

    def __init__(self, client):
        self.client = client
        self.db = DatabaseCore()
        self.user_last_notification = {}

    @commands.Cog.listener()
    async def on_ready(self):
        self.look_for_expired_tempmutes.start()
        self.check_timeouts_expirations.start()
        self.guild = self.client.get_guild(server_id)
        print('[.cogs] Moderation cog is ready!')

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild: return

        if message.author.bot:
            if not message.webhook_id: return
            else:
                return await self.check_unban_infractions(message)
        
        # Checks if the message is a spam/scam message
        message_content_lower = message.content.lower()
        scam_detected = False
        for word in scamwords:
            word_lower = word.lower()
            # Use regex for whole word or exact match
            if re.search(rf'\b{re.escape(word_lower)}\b', message_content_lower):
                scam_detected = True
                break
        if scam_detected:
            await self.handle_scam(message)
            await message.delete()
            return
        
        # Checks if someone pinged Staff
        await self.check_if_pinged_staff(message)

        # Banned links
        await self.check_banned_links(message)

        # Invite tracker
        msg = str(message.content)
        invite_root = self.get_invite_root(msg.lower().strip())

        if invite_root and invite_root not in ("discord.gg/events/", "discord.com/events/"):
            ctx = await self.client.get_context(message)
            if not await utils.is_allowed([*allowed_roles, sponsor_role_id]).predicate(ctx):
                is_from_guild = await self.check_invite_guild(msg, message.guild, invite_root)

                if not is_from_guild:
                    # return await self._mute_callback(ctx, member=message.author, reason="Invite Advertisement.")
                    
                    timeout_duration = 30 * 60  # 30 minutes in seconds
                    timeout_until = discord.utils.utcnow() + timedelta(seconds=timeout_duration)
                    await message.author.timeout(until=timeout_until, reason="Invite Advertisement.")
                    await message.delete()
                    
                    # send a dm to the user
                    try:
                        await message.author.send(
                            f"**You have been timed out for 30 minutes in Language Sloth.**\n"
                            f"**Reason:** Invite advertisement."
                        )
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """ Checks whether a member is picking roles while muted. """

        member = after  # Alias for the member object that will be updated and used

        # It's a bot
        if member.bot:
            return
        
        # The user left the server
        if not after.guild:
            return

        # Before and After roles
        roles = before.roles
        roles2 = after.roles

        # User lost a role
        if len(roles2) < len(roles):
            return

        new_role = None

        # Gets the new role
        for r2 in roles2:
            if r2 not in roles:
                new_role = r2
                break

        # Checks, just in case, if the new role was found
        if not new_role:
            return
        
        # Check for restricted roles
        await self.check_restricted_roles(member, new_role)

        # Checks whether the user has muted roles in the database
        if await self.get_muted_roles(member.id):
            keep_roles, _ = await self.get_remove_roles(member, keep_roles=allowed_roles)
            muted_role = discord.utils.get(member.guild.roles, id=muted_role_id)
            timedout_role = discord.utils.get(member.guild.roles, id=timedout_role_id)

            # If the user, for some reason, doesn't have the muted role, adds it
            if muted_role not in keep_roles:
                keep_roles.append(muted_role)
                
            # If the user gets silenced has the timeout role is preserved if it is already present
            if timedout_role in member.roles and timedout_role not in keep_roles:
                keep_roles.append(timedout_role)

            # Updates the user roles
            await member.edit(roles=keep_roles)

    async def check_restricted_roles(self, member, new_role):
        """ Checks if a restricted role is added by unauthorized users and removes it.
        :param member: The member that will be updated.
        :param new_role: The new role that was added. """

        guild = self.client.get_guild(server_id)

        # Restricted roles to monitor
        restricted_roles = [
            native_centish_role_id, # Native Centish
            based_role_id, # Based
            few_braincells_role_id, # Few Braincells
            met_dnk_irl_role_id, # Met DNK IRL
            sponsor_role_id, # Server Sponsor
            sloth_nation_role_id, # Sloth Nation
            frog_catcher_role_id, # Frog Catcher
            native_ancient_latin_role_id # Native (ancient) Latin
        ] # these comments were definitely needed fr
        
        # Unrestricted users and bots
        unrestricted = [
            216303189073461248 # Patreon Bot
        ] # these comments ARE definitely needed

        # Check if the new role is restricted
        if new_role.id in restricted_roles:
            # Fetch the audit log to find who added the role
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                if entry.target.id == member.id and new_role in entry.after.roles:
                    moderator = entry.user

                    # Check if the moderator has the staff manager role or admin permissions
                    staff_manager_role = discord.utils.get(guild.roles, id=staff_manager_role_id)
                    if not (moderator.id in unrestricted or staff_manager_role in moderator.roles or moderator.guild_permissions.administrator):
                        # Remove the restricted role
                        await member.remove_roles(new_role)

                        # Send a log to the moderation log channel
                        moderation_log = discord.utils.get(guild.channels, id=mod_log_id)
                        embed = discord.Embed(title='__**Unauthorized Role Addition**__', colour=discord.Colour.red(), timestamp=discord.utils.utcnow())
                        embed.add_field(name='Moderator Info:', value=f'```Name: {moderator.display_name}\nId: {moderator.id}```',
                            inline=False)
                        embed.add_field(name='User Info:', value=f'```Name: {member.display_name}\nId: {member.id}```', inline=False)
                        embed.add_field(name='Role Info:', value=f'{new_role.mention}',
                            inline=False)
                        embed.set_thumbnail(url=moderator.display_avatar)
                        await moderation_log.send(embed=embed)

                        # Send a DM to the moderator
                        try:
                            embed = discord.Embed(
                                title="Unauthorized Role Addition",
                                description=f"`{new_role.name}` is restricted and cannot be added by you.\n-# **The role has been removed from `{member.name}`.**",
                                color=discord.Color.red(),
                                timestamp=discord.utils.utcnow()
                            )
                            await moderator.send(embed=embed)
                        except discord.Forbidden:
                            pass
                    break

    def get_invite_root(self, message: str) -> str:
        """ Gets the invite root from an invite link.
        :param message: The message content. """

        for invite_type in self.INVITE_TYPES:
            if invite_type in message:
                return invite_type
            
        return ""

    async def check_banned_links(self, message: discord.Message) -> None:
        """ Checks if the message sent was or contains a banned link. """

        videos = [v for v in message.attachments if v.content_type in ['video/mp4', 'video/webm']]

        # Checks it in the message attachments
        for video in videos:
            if str(video) in banned_links:
                ctx = await self.client.get_context(message)
                if not await utils.is_allowed(allowed_roles).predicate(ctx):
                    return await self._mute_callback(ctx, member=message.author, reason="Banned Link")

        # Checks it in the message content
        for word in message.content.split():
            if word in banned_links:
                ctx = await self.client.get_context(message)
                if not await utils.is_allowed(allowed_roles).predicate(ctx):
                    return await self._mute_callback(ctx, member=message.author, reason="Banned Link")

    async def handle_scam(self, message):
        ctx = await self.client.get_context(message)
        
        try:
            scam_channel = self.client.get_channel(spam_log_channel_id)
        except discord.NotFound:
            return

        user_id = message.author.id
        current_time = time.time() * 1000  # Convert to milliseconds

        last_notification = self.user_last_notification.get(user_id, 0)
        if current_time - last_notification < 5 * 60 * 1000:
            return

        self.user_last_notification[user_id] = current_time

        embed = discord.Embed(
            color=discord.Color.red(),
            description=f"-# SCAM notification\n-# [Message Link]({message.jump_url})",
            timestamp=discord.utils.utcnow(),
        )

        created_at, joined_at = int(message.author.created_at.timestamp()), int(message.author.joined_at.timestamp())
        
        embed.add_field(name="User", value=f"**ID:** {message.author.id}\n**Username:** {message.author}", inline=True)
        embed.add_field(name="Account Info", value=f"**Created:** <t:{created_at}:F>\n**Joined:** <t:{joined_at}:F>", inline=True)
        embed.add_field(name="Message Content", value=message.content, inline=False)

        embed.set_footer(text="User muted and kicked", icon_url=message.guild.icon.url if message.guild.icon else None)

        if not await utils.is_allowed(allowed_roles).predicate(ctx, member=message.author):
            # Send the embed to the scam channel if the member is not a staff member
            await scam_channel.send(embed=embed)

            # Nitro kick them if the member is not a staff member
            await self.nitro_kick(ctx, member=message.author, internal_use=True)

    async def check_unban_infractions(self, message: discord.Message) -> None:
        """ Checks and send an infractions list of the user from the unban appeal request. """
        
        if message.channel.id == ban_appeals_channel_id:
            if len(message.mentions) > 0 and len(message.role_mentions) > 0:
                unban_requester = message.mentions[0]
                ctx = await self.client.get_context(message)
                ctx.author = unban_requester

                await self.infractions(ctx, message=unban_requester.mention)

    @tasks.loop(minutes=1)
    async def look_for_expired_tempmutes(self) -> None:
        """ Looks for expired tempmutes and unmutes the users. """

        current_ts = await utils.get_timestamp()
        tempmutes = await self.get_expired_tempmutes(current_ts)
        guild = self.client.get_guild(server_id)

        for tm in tempmutes:
            member = discord.utils.get(guild.members, id=tm)
            if not member:
                continue

            try:
                role = discord.utils.get(guild.roles, id=muted_role_id)
                if role:
                    if user_roles := await self.get_muted_roles(member.id):

                        bot = discord.utils.get(guild.members, id=self.client.user.id)

                        member_roles = list([
                            a_role for the_role in user_roles if (a_role := discord.utils.get(guild.roles, id=the_role[1]))
                            and a_role < bot.top_role
                        ])
                        member_roles.extend(member.roles)

                        member_roles = list(set(member_roles))
                        if role in member_roles:
                            member_roles.remove(role)

                        try:
                            await self.remove_all_roles_from_system(member.id)
                        except Exception as e:
                            print(e)
                            pass
                        else:
                            # Update member roles
                            await member.edit(roles=member_roles)
                            
                            current_time = await utils.get_time_now()

                            # Moderation log embed
                            moderation_log = discord.utils.get(guild.channels, id=mod_log_id)
                            embed = discord.Embed(title='__**Unmute**__', colour=discord.Colour.light_grey(), timestamp=current_time)
                            embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                            inline=False)
                            embed.set_thumbnail(url=member.display_avatar)
                            await moderation_log.send(embed=embed)
                            try:
                                await member.send(embed=embed)
                            except:
                                pass

            except Exception as e:
                print(e)
                continue

    async def check_invite_guild(self, msg, guild, invite_root: str):
        """ Checks whether it's a guild invite or not. """

        start_index = msg.index(invite_root)
        end_index = start_index + len(invite_root)
        invite_hash = ''
        for c in msg[end_index:]:
            if c == ' ':
                break

            invite_hash += c

        for char in ['!', '@', '.', '(', ')', '[', ']', '#', '?', ':', ';', '`', '"', "'", ',', '{', '}']:
            invite_hash = invite_hash.replace(char, '')
        invite = invite_root + invite_hash
        inv_code = discord.utils.resolve_invite(invite)
        print(inv_code)
        if inv_code == 'languages':
            return True

        if inv_code in ['TE6hPrn65a']:
            return True

        guild_inv = discord.utils.get(await guild.invites(), code=inv_code)
        if guild_inv:
            return True
        else:
            return False
        
    async def check_if_pinged_staff(self, message: discord.Message) -> None:
        """ Checks whether the member pinged the Staff in the message.
        :param message: The message the member sent. """

        guild = message.guild
        member = message.author

        # If it's Staff, don't check it
        if await utils.is_allowed(allowed_roles).predicate(member=member, channel=message.channel): return
        # Checks for mentioned roles in the message
        if not (mentioned_roles := await utils.get_roles(message)): return

        # Makes a set with the Staff roles
        staff_mentions = set([
            discord.utils.get(guild.roles, id=mod_role_id), # Mod
            discord.utils.get(guild.roles, id=staff_manager_role_id), # Staff Manager
            discord.utils.get(guild.roles, id=admin_role_id) # Admin
        ])

        # Checks whether any of the Staff roles were in the list of roles pinged in the message
        if staff_mentions.intersection(set(mentioned_roles)):
            report_support_channel = discord.utils.get(guild.text_channels, id=int(os.getenv("REPORT_CHANNEL_ID")))
            await message.channel.send(f"You should use {report_support_channel.mention} for help reports!")

    @commands.Cog.listener(name="on_member_join")
    async def on_member_join_check_muted_user(self, member):

        if member.bot:
            return

        if await self.get_muted_roles(member.id):
            muted_role = discord.utils.get(member.guild.roles, id=muted_role_id)
            await member.add_roles(muted_role)

    @commands.Cog.listener(name="on_member_join")
    async def on_member_join_check_account_age_firewall(self, member):

        if member.bot:
            return
        
        firewall_state = await self.get_firewall_state()
        if not firewall_state:
            return
        
        if firewall_state[0]:
            try:
                bypass_check = await self.get_bypass_firewall_user(member.id)
                if bypass_check:
                    return

                firewall_type, firewall_minimum_age, firewall_reason = (
                    await self.get_firewall_type(),
                    await self.get_firewall_min_account_age(),
                    await self.get_firewall_reason(),
                )

                response_type = firewall_type[0] if firewall_type else "timeout"
                minimum_age = firewall_minimum_age[0] if firewall_minimum_age else 43200
                reason = firewall_reason[0] if firewall_reason else "Account is less than 12 hours old."
                current_time, account_age = (
                    await utils.get_timestamp(),
                    member.created_at.timestamp(),
                )
                time_check = current_time - account_age
                if time_check < minimum_age:
                    if response_type == "timeout":
                        from_time = current_time + time_check
                        timedout_until = datetime.fromtimestamp(from_time)

                        timedout_role = discord.utils.get(member.guild.roles, id=timedout_role_id)
                        if timedout_role not in member.roles:
                            await member.add_roles(timedout_role)

                        await member.timeout(until=timedout_until, reason=reason)
                        await member.send(f"**You have been automatically timed-out in the Language Sloth.**\n- **Reason:** {reason}")
                    elif response_type == "kick":
                        await member.kick(reason=reason)
                        await member.send(f"**You have been automatically kicked from the Language Sloth.**\n- **Reason:** {reason}")
                else:
                    return
            except Exception as e:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return

        if len(last_deleted_message) >= 1000:
            last_deleted_message[1:]
        last_deleted_message.append({message.author.id : {"content" : message.content, "time" : (message.created_at).timestamp(), 'channel' : message.channel }})

    async def search_user_deleted_messages(self, member) -> List[Dict]:
        deleteds_messages = []
        for message in last_deleted_message:
            member_id = next(iter(message))
            if member_id == member.id:
                message = message[member_id]
                deleteds_messages.append({"content" : message["content"], "time" : message["time"], "channel" : message["channel"]})

        deleteds_messages = (sorted(deleteds_messages, key = lambda d: d['time']))
        return deleteds_messages


    @commands.command()
    @utils.is_allowed([*allowed_roles, analyst_debugger_role_id], throw_exc=True)
    async def snipe(self, ctx, *, message : str = None):
        """(MOD) Snipes deleted messages.
        :param member: The @ or the ID of one or more users to snipe. (Optional) or
        :param quantity: The quantity of messages to snipe (Optional) """

        member, message_qtd = await utils.greedy_member_reason(ctx, message)

        if not last_deleted_message:
            #await ctx.message.delete()
            return await ctx.send("**I couldn't snipe any message.**")

        if not member:
            if not message_qtd:
                # Gets the last deleted message
                messages: List[Dict] = [last_deleted_message[-1]]

            else:
                # Gets the requested amount of deleted messages
                if int(message_qtd) <= 0:
                    return await ctx.send("**I couldn't snipe any message.**")

                if int(message_qtd) > len(last_deleted_message):
                    message_qtd: int = len(last_deleted_message)

                messages: List[Dict] = sorted(last_deleted_message, key = lambda d:  d[next(iter(d))]['time'])
                messages: List[Dict] = messages[- int(message_qtd): ]
            menu = menus.MenuPages(SnipeLooping(messages))
            #await ctx.message.delete()
            await menu.start(ctx)

        else:
            # Gets all deleted messsages from the user
            messages: List[Dict] = await self.search_user_deleted_messages(member[0])

            if not messages:
                return await ctx.send("**I couldn't snipe any messages from this member.**")

            menu = menus.MenuPages(MemberSnipeLooping(messages, member[0]))
            #await ctx.message.delete()
            await menu.start(ctx)


    # Purge command
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, *, message : str = None):
        """ (MOD) Purges messages.
        :param member: The member from whom to purge the messages. (Optional)
        :param amount: The amount of messages to purge. """

        await ctx.message.delete()

        members, amount = await utils.greedy_member_reason(ctx, message)

        if not members and len(ctx.message.content.split()) > 2:
            return await ctx.send(f"**Use z!purge Member[Optional] amount**", delete_after=5)

        if not amount or not amount.isdigit() or int(amount) < 1:
            return await ctx.send("**Please, insert a valid amount of messages to delete**", delete_after=5)

        perms = ctx.channel.permissions_for(ctx.author)
        if not perms.administrator and not ctx.author.get_role(staff_manager_role_id):
            if int(amount) > 30:
                return await ctx.send(f"**You cannot delete more than `30` messages at a time, {ctx.author.mention}!**")

        # global deleted
        deleted = 0
        if members:
            members_id = [member.id for member in members]
            channel = ctx.channel
            msgs = list(filter(
                lambda m: m.author.id in members_id,
                await channel.history(limit=200).flatten()
            ))
            for _ in range(int(amount)):
                await msgs.pop(0).delete()
                deleted += 1

            await ctx.send(f"**`{deleted}` messages deleted from `{' and '.join(member.name for member in members)}`**",
                delete_after=5)

        else:
            await ctx.channel.purge(limit=int(amount))

    @commands.command()
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def clear(self, ctx):
        """ (MOD) Clears the whole channel. """

        special_channels = {
            int(os.getenv('MUTED_CHANNEL_ID', 123)): 'https://tenor.com/view/you-are-muted-jeremy-clarkson-gif-24026601',
            int(os.getenv('QUESTION_CHANNEL_ID', 123)): '''**Have a question about the server? Ask it here!**\nThe chat will be cleared once questions are answered.'''
        }

        if ctx.channel.id not in special_channels.keys():
            return await ctx.send("**You cannot do that here!**")

        embed = discord.Embed(
        title="Confirmation",
        description="Clear the whole channel, **are you sure?**",
        color=discord.Color.green(),
        timestamp=ctx.message.created_at)
        msg = await ctx.send(embed=embed)

        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check(r, u):
            return r.message.id == msg.id and u.id == ctx.author.id and str(r.emoji) in ['✅', '❌']

        try:
            r, _ = await self.client.wait_for('reaction_add', timeout=60, check=check)
            r = str(r.emoji)
        except asyncio.TimeoutError:
            embed.description = '**Timeout!**'
            return await msg.edit(embed=embed)

        else:
            if r == '❌':
                embed.description = "Good, not doing it then! ❌"
                return await msg.edit(embed=embed)
            else:
                embed.description = "Clearing whole channel..."
                await msg.edit(embed=embed)
                await asyncio.sleep(1)

        while True:
            msgs = await ctx.channel.history().flatten()
            if (lenmsg := len(msgs)) > 0:
                await ctx.channel.purge(limit=lenmsg)
            else:
                break

        if smessage := special_channels.get(ctx.channel.id):
            await ctx.send(smessage)

    # Warns a member
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def fwarn(self, ctx, *, message: Optional[str] = None):
        """ (ADM) Warns't a member in the server.
        :param member: The @ or ID of the user to fwarn.
        :param reason: The reason for fwarning the user. (Optional) """

        await ctx.message.delete()

        members, reason = await utils.greedy_member_reason(ctx, message)

        if not members:
            await ctx.send('**Member not found!**', delete_after=3)
        else:
            for member in members:
                # General embed
                general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_gold())
                general_embed.set_author(name=f'{member} has been warned', icon_url=member.display_avatar)
                await ctx.send(embed=general_embed)

    @commands.command(aliases=["lwarn", "lwarnado", "lwrn", "lw"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def light_warn(self, ctx, *, message: Optional[str] = None) -> None:
        """(MOD) Soft-Warns one or more members.
        :param member: The @ or the ID of one or more users to soft warn.
        :param reason: The reason for warning one or all users. (Optional)"""

        await self._warn_callback(ctx=ctx, message=message, warn_type="lwarn")

    @commands.command(aliases=["warnado", "wrn", "w"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def warn(self, ctx, *, message: Optional[str] = None) -> None:
        """(MOD) Warns one or more members.
        :param member: The @ or the ID of one or more users to warn.
        :param reason: The reason for warning one or all users. (Optional)"""

        await self._warn_callback(ctx=ctx, message=message, warn_type="warn")

    # not removed from the code, just in case we want to use it in the future
    # and also, we need the heavy warn type to exist because of the previous heavy warn infractions
    #
    # @commands.command(aliases=["hwarn", "hwarnado", "hwrn", "hw"])
    # @utils.is_allowed(allowed_roles, throw_exc=True)
    # async def heavy_warn(self, ctx, *, message: Optional[str] = None) -> None:
    #     """(MOD) Warns one or more members.
    #     :param member: The @ or the ID of one or more users to warn.
    #     :param reason: The reason for warning one or all users. (Optional)"""
    #     
    #     await self._warn_callback(ctx=ctx, message=message, warn_type="hwarn")

    async def _warn_callback(self, ctx, *, message: Optional[str] = None, warn_type: str = "warn") -> None:
        """ Callback for the warn commands.
        :param member: The @ or the ID of one or more users to warn.
        :param reason: The reason for warning one or all users. (Optional)
        :param warn_type: The warn type. [light/normal/heavy]"""

        await ctx.message.delete()

        icon = ctx.author.display_avatar
        is_admin = ctx.author.guild_permissions.administrator
        members, reason = await utils.greedy_member_reason(ctx, message)
        ban_reason = "You have been banned from Language Sloth for exceeding the maximum warn limit within 6 months."

        if not members:
            await ctx.send("**Please, inform a member!**", delete_after=3)
        else:
            if not is_admin and (reason is not None and len(reason) > 960):
                return await ctx.send(f"**Please, inform a reason that is lower than or equal to 960 characters, {ctx.author.mention}!**", delete_after=3)
            elif not is_admin and (reason is None or len(reason) < 16):
                return await ctx.send(f"**Please, inform a reason that is higher than 15 characters, {ctx.author.mention}!**", delete_after=3)

            for member in members:
                if ctx.guild.get_member(member.id):
                    # General embed
                    ## Check warn type
                    warn_msg, infr = await self.get_warn_type(warn_type)
                    warn_desc = f'**Reason:** {reason}'
                    user_infractions = await self.get_user_infractions(member.id)
                    hours, days, weeks, ban = await self.get_timeout_time(ctx, member, await self.get_timeout_warns(infr, user_infractions))
                    
                    log_timeout = None # otherwise warn shits itself and dies
                    if ban:
                        warn_desc += '\n**User has exceeded the maximum warn limit within 6 months and will be banned!**'
                    else:
                        if hours > 0:
                            warn_desc += f'\n**Timeout:** {hours}h'
                            log_timeout = f'{hours}h'
                        elif days > 0:
                            warn_desc += f'\n**Timeout:** {days}d'
                            log_timeout = f'{days}d'
                        elif weeks > 0:
                            warn_desc += f'\n**Timeout:** {weeks}w'
                            log_timeout = f'{weeks}w'
                    general_embed = discord.Embed(description=warn_desc, colour=ctx.author.color)
                    general_embed.set_author(name=f'{member} has been {warn_msg}warned', icon_url=member.display_avatar)
                    await ctx.send(embed=general_embed)
                    # Moderation log embed
                    moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                    current_ts = await utils.get_timestamp()
                    infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
                    perpetrator = ctx.author.name if ctx.author else "Unknown"
                    embed = discord.Embed(title=f'__**{warn_type.capitalize()} Warning**__', colour=discord.Colour.dark_gold(),
                                        timestamp=ctx.message.created_at)
                    embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                    inline=False)
                    embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}",
                                    inline=False)
                    if log_timeout:
                        embed.add_field(name='Timeout:', value=f"> {log_timeout}",
                                        inline=False)
                    embed.set_author(name=member)
                    embed.set_thumbnail(url=member.display_avatar)
                    embed.set_footer(text=f"Warned by {ctx.author}", icon_url=ctx.author.display_avatar)
                    await moderation_log.send(embed=embed)
                    # Inserts a infraction into the database
                    await self.insert_user_infraction(
                        user_id=member.id, infr_type=infr, reason=reason,
                        timestamp=current_ts, perpetrator=ctx.author.id)
                    try:
                        await member.send(embed=general_embed)
                    except:
                        pass

                    if ban:
                        # Ban log embed
                        ban_embed = discord.Embed(title='__**Banishment**__', colour=discord.Colour.dark_red(),
                                            timestamp=ctx.message.created_at)
                        ban_embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                        inline=False)
                        ban_embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {ban_reason}")
                        ban_embed.set_author(name=member)
                        ban_embed.set_thumbnail(url=member.display_avatar)
                        ban_embed.set_footer(text=f"Banned by {ctx.author}", icon_url=icon)
                        await moderation_log.send(embed=ban_embed)

                        # Inserts a ban infraction into the database
                        await self.insert_user_infraction(
                            user_id=member.id, infr_type="ban", reason=ban_reason,
                            timestamp=current_ts, perpetrator=ctx.author.id)
                        
                        # General ban embed
                        general_ban_embed = discord.Embed(description=f"**Reason:** {ban_reason}", colour=discord.Colour.dark_red())
                        general_ban_embed.set_author(name=f'{member} has been banned', icon_url=member.display_avatar)
                        await ctx.send(embed=general_ban_embed)

                        # Ban!
                        await member.ban(delete_message_seconds=604800, reason=ban_reason)

                        # Also send the general ban embed to the banned user
                        try:
                            await member.send(embed=general_ban_embed)
                        except:
                            pass
                    else:
                        await self._timeout_callback(ctx, member, warn_type, user_infractions)
                else:
                    await ctx.send(f"**The user `{member}` is not on the server**", delete_after = 5)
    
    async def get_warn_type(self, warn_type: str) -> Tuple[str, str, str, int]:
        """ Gets the warn info based on the warn type.
        :param warn_type: The warn type. [light/normal/heavy] """

        if warn_type == "lwarn":
            return "lightly ", "lwarn"
        elif warn_type == "warn":
            return "", "warn"
        elif warn_type == "hwarn":
            return "heavily ", "hwarn"

    async def get_timeout_warns(self, warn_type: str, infractions: List[List[Union[str, int]]]) -> int:
        """Returns the number of total warns that user has taking all types of warns.
        :param warn_type: The warn type.
        :param infractions: The list of all infractions from a user. """

        weight_map = {
            "lwarn": 0.5,
            "warn": 1,
            "hwarn": 2
        }
        warns = await self.get_warns(infractions)
        lwarns = sum(1 for w in warns if w[1] == "lwarn")
        total = sum(weight_map[w[1]] for w in warns) + weight_map[warn_type]
        if lwarns % 2 > 0 and warn_type != "lwarn":
            total -= weight_map["lwarn"]
        return total

    async def get_warns(self, infractions: List[List[Union[str, int]]]) -> List[List[Union[str, int]]]:
        """Returns the number of total warns that user has taking all types of warns.
        :param infractions: List of all infractions from a user. """

        valid_types = {"lwarn", "warn", "hwarn"}
        six_months_ago = await utils.get_timestamp() - 6*30*24*3600	 # Approach of 30 days per month
        warnings = [w for w in infractions if w[1] in valid_types and w[3] >= six_months_ago]
        return warnings

    async def get_timeout_time(self, ctx: commands.Context, member: discord.Member, warns: int) -> List[int]:
        """Gets the time of a time out based on their number of warnings.
        :param warns: The number of warns the user have. """

        autoBan = False # Auto-ban option for when the user exceeds the maximum warn limit within 6 months
        weight_map = {
            # n: [hour, day, week, ban]
            0: [0, 0, 0, False],
            1: [1, 0, 0, False],	# 1 hour
            2: [3, 0, 0, False],	# 3 hours
            3: [6, 0, 0, False],	# 6 hours
            4: [12, 0, 0, False],	# 12 hours
            5: [0, 1, 0, False],	# 1 day
            6: [0, 2, 0, False],	# 2 days
            7: [0, 3, 0, False],	# 3 days
            8: [0, 0, 1, False] if not autoBan else [0, 0, 0, True] # 1 week or Ban if autoBan variable is True
        }
        
        if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
            index = 0
        elif warns in weight_map:
            index = warns
        elif warns > 8:
            index = 8
        else:
            index = 0
        return weight_map[index]

    async def _timeout_callback(self, ctx: commands.Context, member: discord.Member, warn_type: str, infractions: List[List[Union[str, int]]]) -> None:
        """Times out a user based on their number of warnings.
        :param ctx: The command context.
        :param member: The member to timeout.
        :param warn_type: The warn type. """

        if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
            return

        muted_role = discord.utils.get(ctx.guild.roles, id=muted_role_id)
        if muted_role in member.roles:
            await self._unmute_callback(ctx, member)
          
        warns = await self.get_timeout_warns(warn_type, infractions)
        hours, days, weeks, ban = await self.get_timeout_time(ctx, member, warns)
        
        if hours == 0 and days == 0 and weeks == 0:
            return
        
        timedout_role = discord.utils.get(ctx.guild.roles, id=timedout_role_id)
        if timedout_role not in member.roles:
            await member.add_roles(timedout_role)
        
        timeout_reason = f"{int(warns)} warnings"
        timeout_duration = sum([
            weeks * 604800, # 1 week = 604800 seconds
            days * 86400,   # 1 day = 86400 seconds
            hours * 3600    # 1 hour = 3600 seconds
        ])
        try:
            current_ts = await utils.get_timestamp() + timeout_duration
            timedout_until = datetime.fromtimestamp(current_ts)
            await member.timeout(until=timedout_until, reason=f"Timed out for: {timeout_reason}")
        except:
            pass
    
    @commands.command(aliases=["to"])
    @commands.has_permissions(administrator=True)
    async def timeout(self, ctx, member: discord.Member = None, *, time: str = None):
        """(ADM) Temporarily times out a member and adds the timeout role.
        :param member: The @ or the ID of the user to timeout.
        :param time: The duration of the timeout. """

        await ctx.message.delete()

        if not member:
            return await ctx.send("**Please, specify a member!**", delete_after=3)

        if not time:
            return await ctx.send("**Please, specify a time, all these examples work: `1d`, `3d 12h`, `12h 30m 30s`.**", delete_after=6)

        time_dict, seconds = await utils.get_time_from_text(ctx, time=time)
        if not seconds:
            return

        timedout_role = discord.utils.get(ctx.guild.roles, id=timedout_role_id)
        try:
            timeout_until = discord.utils.utcnow() + timedelta(seconds=seconds)
            await member.timeout(until=timeout_until, reason=f"Timed out by {ctx.author}")
            if timedout_role and timedout_role not in member.roles:
                await member.add_roles(timedout_role)
        except Exception as e:
            print(f"Error timing out user: {e}")
            return await ctx.send(f"**Failed to timeout {member.mention}.**", delete_after=3)

        # General embed
        general_embed = discord.Embed(
            description=f"**For:** `{time_dict['days']}d`, `{time_dict['hours']}h`, `{time_dict['minutes']}m` and `{time_dict['seconds']}s`",
            colour=discord.Colour.orange(),
            timestamp=ctx.message.created_at
        )
        general_embed.set_author(name=f"{member} has been timed out", icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        
    @commands.command(aliases=["rto", "rtimeout", "remove_to"])
    @commands.has_permissions(administrator=True)
    async def remove_timeout(self, ctx, member: discord.Member = None):
        """(ADM) Removes the timeout from a member and removes the timeout role.
        :param member: The @ or the ID of the user to remove the timeout from."""

        await ctx.message.delete()

        if not member:
            return await ctx.send("**Please, specify a member!**", delete_after=3)

        if not member.communication_disabled_until:
            return await ctx.send(f"**{member.mention} is not currently timed out!**", delete_after=3)

        timedout_role = discord.utils.get(ctx.guild.roles, id=timedout_role_id)
        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author}")
            if timedout_role and timedout_role in member.roles:
                await member.remove_roles(timedout_role)
        except Exception as e:
            print(f"Error removing timeout: {e}")
            return await ctx.send(f"**Failed to remove timeout for {member.mention}.**", delete_after=3)

        # General embed
        general_embed = discord.Embed(
            description=f"**Timeout removed.**",
            colour=discord.Colour.green(),
            timestamp=ctx.message.created_at
        )
        general_embed.set_author(name=f"{member} is no longer timed out", icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        
    @tasks.loop(minutes=3)
    async def check_timeouts_expirations(self) -> None:
        """ Task that checks Timeouts expirations. """
        
        guild = self.client.get_guild(server_id)
        role = discord.utils.get(guild.roles, id=timedout_role_id)
        members = role.members
        
        for member in members:
            try:
                timeout_time = member.communication_disabled_until
                if timeout_time is None or (timeout_time and timeout_time.timestamp() < time.time()):
                    await member.remove_roles(role)
            except Exception as e:
                print(e)
                continue

    async def get_remove_roles(self, member: discord.Member, keep_roles: Optional[List[Union[int, discord.Role]]] = []
    ) -> List[List[discord.Role]]:
        """ Gets a list of roles the user will have after removing their roles
        and a list that will be removed from them.
        :param keep_roles: The list of roles to keep. [Optional] """


        bot = discord.utils.get(member.guild.members, id=self.client.user.id)

        keep_roles: List[int] = [
            keep_role if isinstance(keep_role, discord.Role) else
            discord.utils.get(member.guild.roles, id=keep_role)
            for keep_role in keep_roles
        ]

        keep_list = []
        remove_list = []

        for i, member_role in enumerate(member.roles):
            if i == 0:
                continue

            for role in keep_roles:
                if member_role.id == role.id:
                    keep_list.append(role)
                    continue
            
            if member_role < bot.top_role:
                if not member_role.is_premium_subscriber() or not member_role.managed:
                    remove_list.append(member_role)

            if member_role.managed:
                keep_list.append(member_role)

            if member_role.is_premium_subscriber():
                keep_list.append(member_role)

            if member_role >= bot.top_role:
                keep_list.append(member_role)

        return list(set(keep_list)), list(set(remove_list))

    @commands.command()
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def rar(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """ Removes all roles from a user.
        :param member: The member to rar from. """

        author = ctx.author

        if not member:
            return await ctx.send(f"**Please, inform a member to rar, {author.mention}!**")

        keep_roles, _ = await self.get_remove_roles(member, keep_roles=allowed_roles)

        confirm = await Confirm(f"**Are you sure you wanna rar {member.mention}, {author.mention}?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it, then, {author.mention}!**")

        try:
            await member.edit(roles=keep_roles)
        except:
            await ctx.send(f"**For some reason I couldn't do it, {author.mention}!**")
        else:
            await ctx.send(f"**Successfully rar'd `{member}`, {author.mention}!**")

    @commands.command(aliases=['show_muted_roles', 'check_muted', 'muted_roles', 'removed_roles', 'srr', 'see_removed_roles'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def show_removed_roles(self, ctx, member: Union[discord.Member, discord.User] = None) -> None:
        """ Shows the roles that were remove from the user when they got muted.
        :param member: The member to check it. """

        author = ctx.author
        if not member:
            return await ctx.send(f"**Please, inform the member to check the roles, {author.mention}!**")

        if not member.get_role(muted_role_id):
            return await ctx.send(f"**The given user is not even muted, {author.mention}!**")

        roles = await self.get_muted_roles(member.id)
        if not roles:
            return await ctx.send(f"**User had no roles, {author.mention}!**")

        roles = ', '.join([f"<@&{rid[1]}>" for rid in roles if rid[1] != preference_role_id])

        embed: discord.Embed = discord.Embed(
            title="__Removed Roles__",
            description=f"{member.mention} got the following roles removed after being muted:\n\n{roles}",
            color=member.color,
            timestamp=ctx.message.created_at
        )

        await ctx.send(embed=embed)

    @commands.command(name="mute", aliases=["shutup", "shut_up", "stfu", "zitto", "zitta", "shh", "tg", "ta_gueule", "tagueule", "mutado", "xiu", "calaboca", "callate", "calma_calabreso"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def _mute_command(self, ctx, *, message : str = None) -> None:
        """(MOD) Mutes one or more members.
        :param member: The @ or the ID of one or more users to mute.
        :param reason: The reason for muting one or all users. (Optional)"""

        members, reason = await utils.greedy_member_reason(ctx, message)

        await ctx.message.delete()

        if not members:
            return await ctx.send("**Please, inform a member!**", delete_after=3)

        for member in members:
            if ctx.guild.get_member(member.id):
                await self._mute_callback(ctx, member, reason)
            else:
                await ctx.send(f"** The user `{member}` is not on the server**")

    @user_command(name="Mute", guild_ids=guild_ids)
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def _mute_slash(self, ctx, user: discord.Member) -> None:
        """ (MOD) Mutes a member.
        :param member: The @ or the ID of the user to mute.
        :param reason: The reason for the mute. """

        await self._mute_callback(ctx, user)

    async def _mute_callback(self, ctx: commands.Context, member: discord.Member = None, reason: Optional[str] = None):
        """ (MOD) Mutes a member.
        :param member: The @ or the ID of the user to mute.
        :param reason: The reason for the mute. """

        is_admin = ctx.author.guild_permissions.administrator

        answer: discord.PartialMessageable = None
        if isinstance(ctx, commands.Context):
            answer = ctx.send
            try:
                await ctx.message.delete()
            except:
                pass
        else:
            answer = ctx.respond

        role = discord.utils.get(ctx.guild.roles, id=muted_role_id)
        if not member:
            return await ctx.send("**Please, specify a member!**")
        
        if not is_admin and (reason is not None and len(reason) > 960):
            return await ctx.send(f"**Please, inform a reason that is lower than or equal to 960 characters, {ctx.author.mention}!**", delete_after=3)
        elif not is_admin and (reason is None or len(reason) < 16):
            return await ctx.send(f"**Please, inform a reason that is higher than 15 characters, {ctx.author.mention}!**", delete_after=3)
                                  
        if role not in member.roles:
            await member.move_to(None)
            keep_roles, remove_roles = await self.get_remove_roles(member, keep_roles=allowed_roles)

            current_ts = await utils.get_timestamp()
            keep_roles.append(role)

            await member.edit(roles=keep_roles)
            user_role_ids = [(member.id, rr.id, current_ts, None) for rr in remove_roles]
            await self.insert_in_muted(user_role_ids)

            # General embed
            current_time = await utils.get_time_now()
            general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_grey(), timestamp=current_time)
            general_embed.set_author(name=f'{member} has been muted', icon_url=member.display_avatar)
            await answer(embed=general_embed)

            # Sends the muted channel rules to the user
            rules_embed = discord.Embed(
                color=discord.Color.dark_grey(),
                timestamp=current_time,
                description=(
                    "**You have been muted** on The Language Sloth.\n"
                    f"You are **not banned, you can get unmuted by talking to a staff member** in <#{muted_chat_id}>.\n\n"
                    "While you are there, it is especially **important that you refrain from:**\n\n"
                    "**:x: NSFW/Inappropriate Posts\n"
                    ":x: Insulting Staff Members\n"
                    ":x: Pinging Staff Members**\n\n"
                    "Such behaviors, amongst others, **may result in a ban.**\n\n"
                    "Being muted **does not mean you are being punished.**\n"
                    "It means that **a staff member needs to talk to you** to resolve an ongoing case, **cooperate with them and be polite if you want to get unmuted.**"
                )
            )

            try:
                await member.send(embed=rules_embed)
            except:
                pass

            # Moderation log embed
            moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
            infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
            perpetrator = ctx.author.name if ctx.author else "Unknown"
            embed = discord.Embed(title='__**Mute**__', color=discord.Color.dark_grey(),
                                timestamp=current_time)
            embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                            inline=False)
            embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
            embed.set_author(name=member)
            embed.set_thumbnail(url=member.display_avatar)
            embed.set_footer(text=f"Muted by {ctx.author}", icon_url=ctx.author.display_avatar)
            await moderation_log.send(embed=embed)

            # Muted chat embed
            muted_chat = discord.utils.get(ctx.guild.channels, id=muted_chat_id)
            muted_embed = discord.Embed(
                title="You've been muted",
                description=(
                    f"**{member.display_name}**, you have been muted by **{ctx.author.name}**.\n\n"
                    f"**Reason:** {reason}\n\n"
                    "Wait until they are available to talk with you. Do not ping them or any other staff member."
                ),
                color=discord.Color.dark_grey(),
                timestamp=current_time
            )
            muted_embed.set_thumbnail(url=member.display_avatar)
            if ctx.author.id == gabs_id:
                await muted_chat.send(f"{member.mention}")
            else:
                await muted_chat.send(f"{member.mention} {ctx.author.mention}")
            await muted_chat.send(embed=muted_embed)

            # Inserts a infraction into the database
            await self.insert_user_infraction(
                user_id=member.id, infr_type="mute", reason=reason,
                timestamp=current_ts, perpetrator=ctx.author.id)
            try:
                await member.send(embed=general_embed)
            except:
                pass

        else:
            await answer(f'**{member} is already muted!**')

    # Unmutes a member
    @commands.command(name="unmute")
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def _unmute_command(self, ctx, *, message : str = None) -> None:
        """(MOD) Unmutes one or more members instantly or after a determined amount of time.
        :param member: The @ or the ID of one or more users to unmute.
        :param time: The time before unmuting one or all users. (Optional)"""

        await ctx.message.delete()
        members, time = await utils.greedy_member_reason(ctx, message)

        if not members:
            return await ctx.send("**Please, inform a member!**", delete_after=3)

        if time == None:
            for member in members:
                if ctx.guild.get_member(member.id):
                    await self._unmute_callback(ctx, member)
                else:
                    await ctx.send(f"** The user `{member}` is not on the server**")
        else:
            role = discord.utils.get(ctx.guild.roles, id=muted_role_id)
            for member in members:
                if ctx.guild.get_member(member.id):
                    if role in member.roles:
                        current_ts = await utils.get_timestamp()
                        time_dict, seconds = await utils.get_time_from_text(ctx, time)

                        general_embed = discord.Embed(description=f"**In:** `{time_dict['days']}d`, `{time_dict['hours']}h`, `{time_dict['minutes']}m`\n", colour=discord.Colour.dark_grey(), timestamp=ctx.message.created_at)
                        general_embed.set_author(name=f"{member} will be unmuted", icon_url=member.display_avatar)
                        await ctx.send(embed=general_embed)

                        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                        embed = discord.Embed(
                            description=F"**Unmuting** {member.mention}\n **In:** `{time_dict['days']}d`, `{time_dict['hours']}h`, `{time_dict['minutes']}m`\n**Location:** {ctx.channel.mention}",
                            color=discord.Color.lighter_grey(),
                            timestamp=ctx.message.created_at)
                        embed.set_author(name=f"{ctx.author} (ID {ctx.author.id})", icon_url=ctx.author.display_avatar)
                        embed.set_thumbnail(url=member.display_avatar)
                        await moderation_log.send(embed=embed)

                        # Updating the member muted database
                        await ModerationMutedMemberTable.update_mute_time(ctx, member.id, current_ts, seconds)
                    else:
                        await ctx.send(f"User {member} is not muted")
                else:
                    await ctx.send(f"** The user `{member}` is not on the server**")


    @user_command(name="Unmute", guild_ids=guild_ids)
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def _unmute_slash(self, ctx, user: discord.Member) -> None:
        """ (MOD) Mutes a member.
        :param member: The @ or the ID of the user to mute.
        :param reason: The reason for the mute. """

        await self._unmute_callback(ctx, user)

    async def _unmute_callback(self, ctx, member: discord.Member = None) -> None:
        """ (MOD) Unmutes a member.
        :param member: The @ or the ID of the user to unmute. """

        answer: discord.PartialMessageable = None
        if isinstance(ctx, commands.Context):
            answer = ctx.send
            try:
                await ctx.message.delete()
            except:
                pass
        else:
            answer = ctx.respond

        role = discord.utils.get(ctx.guild.roles, id=muted_role_id)
        if not member:
            return await answer("**Please, specify a member!**")

        if not member.get_role(role.id):
            return await answer(f'**{member} is not even muted!**')

        if user_roles := await self.get_muted_roles(member.id):

            bot = discord.utils.get(ctx.guild.members, id=self.client.user.id)

            member_roles = list([
                a_role for the_role in user_roles if (a_role := discord.utils.get(member.guild.roles, id=the_role[1]))
                and a_role < bot.top_role
            ])
            member_roles.extend(member.roles)

            member_roles = list(set(member_roles))
            if role in member_roles:
                member_roles.remove(role)

            try:
                await self.remove_all_roles_from_system(member.id)
            except Exception as e:
                print(e)
                pass

            await member.edit(roles=member_roles)

        try:
            await member.remove_roles(role)
        except:
            pass

        current_time = await utils.get_time_now()
        general_embed = discord.Embed(colour=discord.Colour.light_grey(),
                                        timestamp=current_time)
        general_embed.set_author(name=f'{member} has been unmuted', icon_url=member.display_avatar)
        await answer(embed=general_embed)
        # Moderation log embed
        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
        embed = discord.Embed(title='__**Unmute**__', colour=discord.Colour.light_grey(),
                                timestamp=current_time)
        embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                        inline=False)
        embed.set_author(name=member)
        embed.set_thumbnail(url=member.display_avatar)
        embed.set_footer(text=f"Unmuted by {ctx.author}", icon_url=ctx.author.display_avatar)
        await moderation_log.send(embed=embed)
        try:
            await member.send(embed=general_embed)
        except:
            pass
            
    # Mutes a member temporarily
    @commands.command(aliases=["arab"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def tempmute(self, ctx, member: discord.Member = None, reason: str = None, *, time: str = None):
        """ Mutes a member for a determined amount of time.
        :param member: The @ or the ID of the user to tempmute.
        :param reason: The reason for the tempmute.
        :param time: The time for the mute. """

        await ctx.message.delete()

        role = discord.utils.get(ctx.guild.roles, id=muted_role_id)

        if not member:
            return await ctx.send("**Please, specify a member!**", delete_after=3)

        if not reason:
            return await ctx.send(f"**Specify a reason!**", delete_after=3)

        if not time:
            return await ctx.send('**Inform a time!**', delete_after=3)

        time_dict, seconds = await utils.get_time_from_text(ctx, time=time)
        if not seconds:
            return

        current_ts = await utils.get_timestamp()

        if role not in member.roles:
            await member.move_to(None)
            keep_roles, remove_roles = await self.get_remove_roles(member, keep_roles=allowed_roles)
            keep_roles.append(role)

            await member.edit(roles=keep_roles)
            user_role_ids = [(member.id, rr.id, current_ts, seconds) for rr in remove_roles]
            await self.insert_in_muted(user_role_ids)

            # General embed
            general_embed = discord.Embed(description=f"**For:** `{time_dict['days']}d`, `{time_dict['hours']}h`, `{time_dict['minutes']}m` and `{time_dict['seconds']}s`\n**Reason:** {reason}", colour=discord.Colour.dark_grey(), timestamp=ctx.message.created_at)
            general_embed.set_author(name=f"{member} has been tempmuted", icon_url=member.display_avatar)
            await ctx.send(embed=general_embed)
            # Moderation log embed
            moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
            embed = discord.Embed(
                description=F"**Tempmuted** {member.mention} for `{time_dict['days']}d`, `{time_dict['hours']}h`, `{time_dict['minutes']}m` and `{time_dict['seconds']}s`\n**Reason:** {reason}\n**Location:** {ctx.channel.mention}",
                color=discord.Color.lighter_grey(),
                timestamp=ctx.message.created_at)
            embed.set_author(name=f"{ctx.author} (ID {ctx.author.id})", icon_url=ctx.author.display_avatar)
            embed.set_thumbnail(url=member.display_avatar)
            await moderation_log.send(embed=embed)
            # # Inserts a infraction into the database
            await self.insert_user_infraction(
                user_id=member.id, infr_type="mute", reason=reason,
                timestamp=current_ts, perpetrator=ctx.author.id)
            try:
                await member.send(embed=general_embed)
            except:
                pass
        else:
            await ctx.send(f'**{member} is already muted!**', delete_after=5)

    @commands.command(aliases=['kick_muted_members', 'kickmuted'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def kick_muted(self, ctx, *, reason: Optional[str] = None) -> None:
        """ Kicks all muted members from at least 2 days ago.
        :param reason: The reason for kicking the muted members. [Optional] """

        await ctx.message.delete()
        perpetrator = ctx.author

        muted_role = discord.utils.get(ctx.guild.roles, id=muted_role_id)
        current_ts = await utils.get_timestamp()
        muted_members = [
            muted_member for m in await self.get_muted_members(current_ts, 2) 
            if (muted_member := discord.utils.get(ctx.guild.members, id=m)) and muted_role in muted_member.roles
        ]

        if len(muted_members) == 0:
            return await ctx.send(f"**There are no muted members, {perpetrator.mention}!**")

        confirm = await Confirm(
            f"**Are you sure you want to kick {len(muted_members)} muted members from at least 2 days ago, {perpetrator.mention}?**"
            ).prompt(ctx)

        if confirm:
            kicked_members = []

            current_ts = await utils.get_timestamp()

            for muted_member in muted_members:
                try:
                    # Kicks the muted member
                    await muted_member.kick(reason=reason)
                    # Inserts a infraction into the database
                    await self.insert_user_infraction(
                        user_id=muted_member.id, infr_type="kick", reason=reason,
                        timestamp=current_ts, perpetrator=ctx.author.id)
                except Exception:
                    await ctx.send('**You cannot do that!**', delete_after=3)
                else:
                    kicked_members.append(f"Name: {muted_member.display_name} ({muted_member.id})")

            if len(kicked_members) >= 1:
                # General embed
                general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Color.teal())
                general_embed.set_author(name=f'{len(muted_members)} muted members have been kicked')
                await ctx.send(embed=general_embed)

                # Moderation log embed
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                embed = discord.Embed(title='__**Kick**__', color=discord.Color.teal(),
                                    timestamp=ctx.message.created_at)
                muted_text = '\n'.join(kicked_members)
                embed.add_field(
                    name='User info:', 
                    value=f'```apache\n{muted_text}```', 
                inline=False)
                embed.add_field(name='Reason:', value=f'```{reason}```')
                embed.set_footer(text=f"Kicked by {perpetrator}", icon_url=perpetrator.display_avatar)
                await moderation_log.send(embed=embed)
                
            else:
                await ctx.send(f"**For some reason I couldn't kick any of the {len(muted_members)} muted members, {perpetrator.mention}!**")

        else:
            await ctx.send(f"**Not kicking them, then, {perpetrator.mention}!**")

    @commands.command(aliases=["shush"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def silence(self, ctx, member: discord.Member = None):
        """ Silences a muted member and gives them a timeout for 6 hours. 
        :param member: The @ or the ID of the user. """
        
        await ctx.message.delete()
        
        role = discord.utils.get(ctx.guild.roles, id=muted_role_id)

        if not member:
            return await ctx.send("**Please, specify a member!**", delete_after=3)

        if role in member.roles:
            seconds = 6 * 60 * 60  # 6 hours

            await member.timeout(discord.utils.utcnow() + timedelta(seconds=seconds), reason="Muted user has been silenced for 6 hours.")
            
            timedout_role = discord.utils.get(ctx.guild.roles, id=timedout_role_id)
            if timedout_role not in member.roles:
                await member.add_roles(timedout_role)
            
            current_time = await utils.get_time_now()
            general_embed = discord.Embed(colour=discord.Colour.light_grey(), timestamp=current_time)
            general_embed.set_author(name=f'{member} has been silenced', icon_url=member.display_avatar)
            await ctx.send(embed=general_embed)
            
            moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
            embed = discord.Embed(title='__**Silence**__', colour=discord.Colour.light_grey(),
                                    timestamp=current_time)
            embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                            inline=False)
            embed.set_author(name=member)
            embed.set_thumbnail(url=member.display_avatar)
            embed.set_footer(text=f"Silenced by {ctx.author}", icon_url=ctx.author.display_avatar)
            await moderation_log.send(embed=embed)
        else:
            await ctx.send(f"**{member} is not muted!**", delete_after=5)

    @commands.command(aliases=["unshush"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def unsilence(self, ctx, member: discord.Member = None):
        """ Removes timeout from a muted member if they are already silenced. 
        :param member: The @ or the ID of the user. """
        
        await ctx.message.delete()
        
        role = discord.utils.get(ctx.guild.roles, id=muted_role_id)

        if not member:
            return await ctx.send("**Please, specify a member!**", delete_after=3)

        if role in member.roles and member.communication_disabled_until:
            remaining_time = (member.communication_disabled_until - discord.utils.utcnow()).total_seconds()
            if remaining_time <= 6 * 60 * 60:
                await member.timeout(None)

                timedout_role = discord.utils.get(ctx.guild.roles, id=timedout_role_id)
                if timedout_role in member.roles:
                    await member.remove_roles(timedout_role)

                current_time = await utils.get_time_now()
                embed = discord.Embed(colour=discord.Colour.light_grey(), timestamp=current_time)
                embed.set_author(name=f'{member} has been unsilenced', icon_url=member.display_avatar)
                await ctx.send(embed=embed)
                
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                embed = discord.Embed(title='__**Unsilence**__', colour=discord.Colour.light_grey(),
                                        timestamp=current_time)
                embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                inline=False)
                embed.set_author(name=member)
                embed.set_thumbnail(url=member.display_avatar)
                embed.set_footer(text=f"Unsilenced by {ctx.author}", icon_url=ctx.author.display_avatar)
                await moderation_log.send(embed=embed)
            else:
                await ctx.send(f"**{member}'s timeout is longer than 6 hours!**", delete_after=5)
        else:
            await ctx.send(f"**{member} is not muted or has no timeout!**", delete_after=5)

    @commands.command(aliases=['kickado'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def kick(self, ctx, *, message : str = None):
        """ (MOD) Kicks one or more members from the server.
        :param member: The @ or the ID of one or more users to kick.
        :param reason: The reason for kicking one or all users. (Optional) """

        await ctx.message.delete()

        members, reason = await utils.greedy_member_reason(ctx, message)

        if not members:
            return await ctx.send('**Please, inform a member!**', delete_after=3)

        for member in members:
            if ctx.guild.get_member(member.id):
                if not await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
                    confirm = await Confirm(f"**Are you sure you want to kick {member.mention} from the server, {ctx.author.mention}?**").prompt(ctx)
                    if not confirm:
                        continue

                    # General embed
                    general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.magenta())
                    general_embed.set_author(name=f'{member} has been kicked', icon_url=member.display_avatar)
                    await ctx.send(embed=general_embed)
                    try:
                        await member.send(embed=general_embed)
                    except:
                        pass

                    try:
                        await member.kick(reason=reason)
                    except Exception:
                        await ctx.send('**You cannot do that!**', delete_after=3)
                    else:
                        # Moderation log embed
                        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                        current_ts = await utils.get_timestamp()
                        infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
                        perpetrator = ctx.author.name if ctx.author else "Unknown"
                        embed = discord.Embed(title='__**Kick**__', colour=discord.Colour.magenta(),
                                                timestamp=ctx.message.created_at)
                        embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                        inline=False)
                        embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                        embed.set_author(name=member)
                        embed.set_thumbnail(url=member.display_avatar)
                        embed.set_footer(text=f"Kicked by {ctx.author}", icon_url=ctx.author.display_avatar)
                        await moderation_log.send(embed=embed)
                        # Inserts a infraction into the database
                        await self.insert_user_infraction(
                            user_id=member.id, infr_type="kick", reason=reason,
                            timestamp=current_ts, perpetrator=ctx.author.id)
                else:
                    await ctx.send(f"**You cannot kick a staff member, {ctx.author.mention}!**")
            else:
                await ctx.send(f"** The user `{member}` is not on the server**")

    # Bans a member
    @commands.command(aliases=['banido'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def ban(self, ctx, *, reason: Optional[str] = None):
        """ (ModTeam/ADM) Bans a member from the server.
        :param members: The @ or ID of one or more users to ban.
        :param reason: The reason for banning the user. (Optional)
        
        PS: Needs 4 mods to ban, in a ModTeam ban. """

        await ctx.message.delete()

        channel = ctx.channel
        author = ctx.author
        is_admin = author.guild_permissions.administrator

        members, reason = await utils.greedy_member_reason(ctx, reason)

        if not members:
            return await ctx.send('**Member not found!**', delete_after=3)
        
        if not is_admin and (reason is not None and len(reason) > 960):
            return await ctx.send(f"**Please, inform a reason that is lower than or equal to 960 characters, {ctx.author.mention}!**", delete_after=3)
        elif not is_admin and (reason is None or len(reason) < 16):
            return await ctx.send(f"**Please, inform a reason that is higher than 15 characters, {ctx.author.mention}!**", delete_after=3)
        
        for member in members:
            if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
                if len(members) == 1:
                    return await ctx.send(f"**You cannot ban a staff member, {author.mention}!**")
                else:
                    continue

            should_ban = await utils.is_allowed([staff_manager_role_id]).predicate(ctx)

            if not should_ban:
                mod_ban_embed = discord.Embed(
                    title=f"Ban Request",
                    description=f'''
                    {author.mention} wants to ban {member.mention}, it requires 1 **Staff Manager** or **Admin** ✅ reaction for it!
                    ```Reason: {reason}```''',
                    colour=discord.Colour.dark_red(), timestamp=ctx.message.created_at)
                mod_ban_embed.set_author(name=f'{member} is going to Brazil...', icon_url=member.display_avatar)
                msg = await ctx.send(embed=mod_ban_embed)
                await msg.add_reaction('✅')
                await msg.add_reaction('❌')

                def check_reaction(r, u):
                    if u.bot:
                        return False
                    if r.message.id != msg.id:
                        return False

                    if str(r.emoji) in ['✅', '❌']:
                        perms = channel.permissions_for(u)
                        if staff_manager_role_id in [r.id for r in u.roles] or perms.administrator:
                            return True
                        else:
                            self.client.loop.create_task(
                                msg.remove_reaction(r.emoji, u)
                            )
                            return False
                    else:
                        self.client.loop.create_task(
                            msg.remove_reaction(r.emoji, u)
                        )
                        return False

                while True:
                    try:
                        r, u = await self.client.wait_for('reaction_add', timeout=3600, check=check_reaction)
                    except asyncio.TimeoutError:
                        mod_ban_embed.description = f'Timeout, {member} is not getting banned!'
                        await msg.remove_reaction('✅', self.client.user)
                        await msg.remove_reaction('❌', self.client.user)
                        await msg.edit(embed=mod_ban_embed)
                        break
                    else:
                        if str(r.emoji) == '✅':
                            should_ban = True
                            await msg.remove_reaction('❌', self.client.user)
                            break
                        elif str(r.emoji) == '❌':
                            mod_ban_embed.description = f'Ban request denied.'
                            await msg.remove_reaction('✅', self.client.user)
                            await msg.edit(embed=mod_ban_embed)
                            break

            if not should_ban:
                continue

            perpetrator = ctx.author
            icon = ctx.author.display_avatar

            # Bans and logs
            # General embed
            general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_red())
            general_embed.set_author(name=f'{member} has been banned', icon_url=member.display_avatar)
            await ctx.send(embed=general_embed)
            try:
                await member.send(content="""Hello,

We regret to inform you that you have been banned from our Discord server. Our moderation team has reviewed your behavior and has determined that it violates our server rules.

Please note that our community strives to provide a safe and friendly environment for all our members. We do not tolerate any form of harassment, hate speech, or any other type of inappropriate behavior.

We understand that sometimes mistakes happen and we believe in second chances. We would like to hear your side of the story and see if we can find a way to move forward together.

The appeal process is simple, just join the server below and fill out the form as instructed there. We will review your appeal as soon as possible and get back to you with a decision through our bot.

https://discord.gg/V5XPMyTyrj

We appreciate your understanding and look forward to hearing from you. """, embed=general_embed)
            except Exception:
                pass
            try:
                await member.ban(delete_message_seconds=604800, reason=reason)
            except Exception:
                await ctx.send('**You cannot do that!**', delete_after=3)
            else:
                # Moderation log embed
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                current_ts = await utils.get_timestamp()
                infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
                perpetrator = ctx.author.name if ctx.author else "Unknown"
                embed = discord.Embed(title='__**Banishment**__', colour=discord.Colour.dark_red(),
                                    timestamp=ctx.message.created_at)
                embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                inline=False)
                embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                embed.set_author(name=member)
                embed.set_thumbnail(url=member.display_avatar)
                embed.set_footer(text=f"Banned by {perpetrator}", icon_url=icon)
                await moderation_log.send(embed=embed)
                # Inserts a infraction into the database
                await self.insert_user_infraction(
                user_id=member.id, infr_type="ban", reason=reason,
                timestamp=current_ts, perpetrator=ctx.author.id)
            

    # Bans a member
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def fban(self, ctx, *, message : str = None):
        """ (ADM) Bansn't a member from the server.
        :param member: The @ or ID of the user to ban.
        :param reason: The reason for banning the user. (Optional) """

        await ctx.message.delete()

        members, reason = await utils.greedy_member_reason(ctx, message)

        if not members:
            await ctx.send('**Member not found!**', delete_after=3)
        else:
            for member in members:
                # General embed
                general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_red())
                general_embed.set_author(name=f'{member} has been banned', icon_url=member.display_avatar)
                await ctx.send(embed=general_embed)

    # Unbans a member
    @commands.command()
    @utils.is_allowed([staff_manager_role_id], throw_exc=True)
    async def unban(self, ctx, *, member=None):
        """ (ADM) Unbans a member from the server.
        :param member: The full nickname and # of the user to unban. """

        await ctx.message.delete()
        if not member:
            return await ctx.send('**Please, inform a member!**', delete_after=3)

        banned_users = ctx.guild.bans()
        try:
            member_name, member_discriminator = str(member).split('#')
        except ValueError:
            return await ctx.send('**Wrong parameter!**', delete_after=3)

        async for ban_entry in banned_users:
            user = ban_entry.user

            if (user.name, user.discriminator) == (member_name, member_discriminator):
                await ctx.guild.unban(user)
                # General embed
                general_embed = discord.Embed(colour=discord.Colour.red())
                general_embed.set_author(name=f'{user} has been unbanned', icon_url=user.display_avatar)
                await ctx.send(embed=general_embed)
                # Moderation log embed
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                embed = discord.Embed(title='__**Unbanishment**__', colour=discord.Colour.red(),
                                    timestamp=ctx.message.created_at)
                embed.add_field(name='User info:', value=f'```Name: {user.display_name}\nId: {user.id}```',
                                inline=False)
                embed.set_author(name=user)
                embed.set_thumbnail(url=user.display_avatar)
                embed.set_footer(text=f"Unbanned by {ctx.author}", icon_url=ctx.author.display_avatar)
                await moderation_log.send(embed=embed)
                try:
                    await user.send(embed=general_embed)
                except:
                    pass
                # Unmutes the user if they were muted before being banned
                try:
                    await self.remove_all_roles_from_system(user.id)
                except Exception as e:
                    pass
                return
        else:
            await ctx.send('**Member not found!**', delete_after=3)

    # Bans a member
    @commands.command()
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def softban(self, ctx, member: Optional[discord.Member] = None, *, reason: Optional[str] = None):
        """ (ModTeam/ADM) Softbans a member from the server.
        :param member: The @ or ID of the user to ban.
        :param reason: The reason for banning the user. (Optional) """
    
        await ctx.message.delete()

        channel = ctx.channel
        author = ctx.author

        if not member:
            return await ctx.send(f"**Member not found, {author.mention}!**", delete_after=3)

        should_ban = False
        if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
            return await ctx.send(f"**You cannot softban a staff member, {author.mention}!**")

        should_ban = await utils.is_allowed([staff_manager_role_id]).predicate(ctx)

        if not should_ban:
            mod_softban_embed = discord.Embed(
                title=f"Softban Request (5mins)",
                description=f'''
                {author.mention} wants to softban {member.mention}, it requires 1 **Staff Manager** or **Admin** ✅ reaction for it!
                ```Reason: {reason}```''',
                colour=discord.Colour.dark_purple(), timestamp=ctx.message.created_at)
            mod_softban_embed.set_author(name=f'{member} is going to Brazil, but will come back!', icon_url=member.display_avatar)
            msg = await ctx.send(embed=mod_softban_embed)
            await msg.add_reaction('✅')

            def check_staff_manager(r, u):
                if u.bot:
                    return False
                if r.message.id != msg.id:
                    return

                if str(r.emoji) == '✅':
                    perms = channel.permissions_for(u)
                    if staff_manager_role_id in [r.id for r in u.roles] or perms.administrator:
                        return True
                    else:
                        self.client.loop.create_task(
                            msg.remove_reaction('✅', u)
                            )
                        return False

                else:
                    self.client.loop.create_task(
                        msg.remove_reaction(r.emoji, u)
                        )
                    return False

            while True:
                try:
                    r, u = await self.client.wait_for('reaction_add', timeout=300, check=check_staff_manager)
                except asyncio.TimeoutError:
                    mod_softban_embed.description = f'Timeout, {member} is not getting softbanned!'
                    await msg.remove_reaction('✅', self.client.user)
                    return await msg.edit(embed=mod_softban_embed)
                else:
                    mod_softban_embed.title = f"Softban Request (5mins)"
                    await msg.edit(embed=mod_softban_embed)
                    should_ban = True
                    break

        if not should_ban:
            return

        perpetrator = ctx.author
        icon = ctx.author.display_avatar

        # Bans and logs
        # General embed
        general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_purple())
        general_embed.set_author(name=f'{member} has been softbanned', icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        try:
            await member.send(content="https://discord.gg/languages", embed=general_embed)
        except Exception as e:
            pass
        try:
            await member.ban(delete_message_seconds=86400, reason=reason)
            await member.unban(reason=reason)
        except Exception:
            await ctx.send('**You cannot do that!**', delete_after=3)
        else:
            # Moderation log embed
            moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
            current_ts = await utils.get_timestamp()
            infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
            perpetrator = ctx.author.name if ctx.author else "Unknown"
            embed = discord.Embed(title='__**SoftBanishment**__', colour=discord.Colour.dark_purple(),
                                timestamp=ctx.message.created_at)
            embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                            inline=False)
            embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
            embed.set_author(name=member)
            embed.set_thumbnail(url=member.display_avatar)
            embed.set_footer(text=f"Banned by {perpetrator}", icon_url=icon)
            await moderation_log.send(embed=embed)
            # Inserts a infraction into the database
            await self.insert_user_infraction(
                user_id=member.id, infr_type="softban", reason=reason,
                timestamp=current_ts, perpetrator=ctx.author.id)

    @commands.command(aliases=["nitrokick", "nitro", "nk", "scam", "phish", "phishing"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def nitro_kick(self, ctx, member: Optional[discord.Member] = None, internal_use: bool = False) -> None:
        """ (ModTeam/ADM) Mutes & Softbans a member from the server who's posting Nitro scam links.
        :param member: The @ or ID of the user to nitrokick.
        :param internal_use: Whether to bypass the moderator request process for internal use. """
    
        await ctx.message.delete()

        channel = ctx.channel
        author = ctx.author

        current_ts: int = await utils.get_timestamp()

        reason = "Nitro Scam"

        if not member:
            return await ctx.send(f"**Member not found, {author.mention}!**", delete_after=3)

        if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
            return await ctx.send(f"**You cannot nitrokick a staff member, {author.mention}!**")
        
        perpetrators = []
        confirmations = {}

        should_nitro_kick = internal_use or await utils.is_allowed([staff_manager_role_id]).predicate(channel=ctx.channel, member=author)

        if not should_nitro_kick and not internal_use:
            confirmations[author.id] = author.name
            mod_softban_embed = discord.Embed(
                title=f"NitroKick Request ({len(confirmations)}/3)",
                description=f'''
                {author.mention} wants to nitrokick {member.mention}, it requires 2 more moderator ✅ reactions for it!
                ```Reason: {reason}```''',
                colour=discord.Colour.nitro_pink(), timestamp=ctx.message.created_at)
            mod_softban_embed.set_author(name=f'{member} is being NitroKicked!', icon_url=member.display_avatar)
            msg = await ctx.send(embed=mod_softban_embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            # Prompts for 3 moderator reactions
            def check_mod(r, u):
                if u.bot:
                    return False
                if r.message.id != msg.id:
                    return

                if str(r.emoji) in ["✅", "❌"]:
                    perms = channel.permissions_for(u)
                    if mod_role_id in [r.id for r in u.roles] or perms.administrator:
                        if str(r.emoji) == "✅":
                            confirmations[u.id] = u.name
                        return True
                    else:
                        self.client.loop.create_task(
                            msg.remove_reaction(r.emoji, u)
                        )
                        return False
                else:
                    self.client.loop.create_task(
                        msg.remove_reaction(r.emoji, u)
                    )
                    return False

            while True:
                try:
                    r, u = await self.client.wait_for("reaction_add", timeout=3600, check=check_mod)
                except asyncio.TimeoutError:
                    mod_softban_embed.description = f"Timeout, {member} is not getting nitrobanned!"
                    await msg.remove_reaction("✅", self.client.user)
                    await msg.remove_reaction("❌", self.client.user)
                    return await msg.edit(embed=mod_softban_embed)
                else:
                    mod_softban_embed.title = f"NitroKick Request ({len(confirmations)}/3)"
                    await msg.edit(embed=mod_softban_embed)
                    if str(r.emoji) == "✅":
                        if await utils.is_allowed([staff_manager_role_id]).predicate(channel=ctx.channel, member=u):
                            should_nitro_kick = True
                            await msg.remove_reaction("❌", self.client.user)
                            break
                        elif len(confirmations) >= 0:
                            if len(confirmations) < 3:
                                continue
                            elif len(confirmations) >= 3:
                                should_nitro_kick = True
                                await msg.remove_reaction("❌", self.client.user)
                                break
                    elif str(r.emoji) == "❌":
                        if await utils.is_allowed([staff_manager_role_id]).predicate(channel=ctx.channel, member=u):
                            mod_softban_embed.title = "NitroKick Request"
                            mod_softban_embed.description = "NitroKick request denied."
                            await msg.edit(embed=mod_softban_embed)
                            await msg.remove_reaction("✅", self.client.user)
                            await msg.remove_reaction("❌", self.client.user)
                            break
                        else:
                            await msg.remove_reaction("❌", u)
                            continue
                    else:
                        break

        if not should_nitro_kick:
            return

        # Checks if it was a moderator ban request or just a normal ban
        if len(confirmations) == 0:
            perpetrators = ctx.author
            icon = ctx.author.display_avatar
        else:
            perpetrators = ', '.join(confirmations.values())
            icon = ctx.guild.icon.url

        # Bans and logs
        # General embed
        general_embed = discord.Embed(description=f'**Reason:** {reason}', color=discord.Color.nitro_pink())
        general_embed.set_author(name=f'{member} has been nitrokicked', icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        try:
            await member.send(content="Your account has been compromised and is now sending nitro scam links, please change your password and enable 2 Factor Authentication in order to regain access to our server\n\nhttps://discord.gg/languages", embed=general_embed)
        except Exception as e:
            pass
        try:
            keep_roles, remove_roles = await self.get_remove_roles(member, keep_roles=allowed_roles)

            await member.edit(roles=keep_roles)
            user_role_ids = [(member.id, rr.id, current_ts, None) for rr in remove_roles]
            await self.insert_in_muted(user_role_ids)
            await member.ban(delete_message_seconds=86400, reason=reason)
            await member.unban(reason=reason)
        except Exception:
            await ctx.send('**You cannot do that!**', delete_after=3)
        else:
            # Moderation log embed
            moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
            current_ts = await utils.get_timestamp()
            infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
            perpetrator = ctx.author.name if ctx.author else "Unknown"
            embed = discord.Embed(title='__**NitroKick**__', color=discord.Color.nitro_pink(),
                                timestamp=ctx.message.created_at)
            embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                            inline=False)
            if internal_use:
                embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {self.client.user.name}\n> {reason}")
                embed.set_footer(text=f"Banned by {self.client.user.name}", icon_url=ctx.guild.icon.url)
            else:
                embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                embed.set_footer(text=f"Banned by {perpetrators}", icon_url=icon)
            embed.set_author(name=member)
            embed.set_thumbnail(url=member.display_avatar)
            await moderation_log.send(embed=embed)
            # Inserts a infraction into the database
            if internal_use:
                await self.insert_user_infraction(
                    user_id=member.id, infr_type="mute", reason=reason,
                    timestamp=current_ts, perpetrator=self.client.user.id)
                await self.insert_user_infraction(
                    user_id=member.id, infr_type="softban", reason=reason,
                    timestamp=current_ts, perpetrator=self.client.user.id)
            else:
                await self.insert_user_infraction(
                    user_id=member.id, infr_type="mute", reason=reason,
                    timestamp=current_ts, perpetrator=ctx.author.id)
                await self.insert_user_infraction(
                    user_id=member.id, infr_type="softban", reason=reason,
                    timestamp=current_ts, perpetrator=ctx.author.id)

    # Hackban a member
    @commands.command(aliases=['hban'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def hackban(self, ctx, *, reason: Optional[str] = None):
        """ (ModTeam/ADM) Hackbans a member from the server.
        :param member: The @ or ID of the user to hackban.
        :param reason: The reason for hackbanning the user. (Optional)
        
        PS: Needs 4 mods to hackban, in a ModTeam hackban. """

        await ctx.message.delete()

        channel = ctx.channel
        author = ctx.author
        is_admin = ctx.author.guild_permissions.administrator

        members, reason = await utils.greedy_member_reason(ctx, reason)

        if not members:
            return await ctx.send('**Member not found!**', delete_after=3)

        if not is_admin and (reason is not None and len(reason) > 960):
            return await ctx.send(f"**Please, inform a reason that is lower than or equal to 960 characters, {ctx.author.mention}!**", delete_after=3)
        elif not is_admin and (reason is None or len(reason) < 16):
            return await ctx.send(f"**Please, inform a reason that is higher than 15 characters, {ctx.author.mention}!**", delete_after=3)

        for member in members:
            if isinstance(member, discord.Member):
                if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
                    if len(members) == 1:
                        return await ctx.send(f"**You cannot hackban a staff member, {author.mention}!**")
                    else:
                        continue

            should_ban = await utils.is_allowed([staff_manager_role_id]).predicate(ctx)

            if not should_ban:
                mod_ban_embed = discord.Embed(
                    title=f"Hackban Request",
                    description=f'''
                    {author.mention} wants to hackban {member.mention}, it requires 1 **Staff Manager** or **Admin** ✅ reaction for it!
                    ```Reason: {reason}```''',
                    colour=discord.Colour.dark_teal(), timestamp=ctx.message.created_at)
                mod_ban_embed.set_author(name=f'{member} is going to Brazil 🦜...', icon_url=member.display_avatar)
                msg = await ctx.send(embed=mod_ban_embed)
                await msg.add_reaction('✅')
                await msg.add_reaction('❌')

                def check_reaction(r, u):
                    if u.bot:
                        return False
                    if r.message.id != msg.id:
                        return False

                    if str(r.emoji) in ['✅', '❌']:
                        perms = channel.permissions_for(u)
                        if staff_manager_role_id in [r.id for r in u.roles] or perms.administrator:
                            return True
                        else:
                            self.client.loop.create_task(
                                msg.remove_reaction(r.emoji, u)
                            )
                            return False

                    else:
                        self.client.loop.create_task(
                            msg.remove_reaction(r.emoji, u)
                        )
                        return False

                while True:
                    try:
                        r, u = await self.client.wait_for('reaction_add', timeout=3600, check=check_reaction)
                    except asyncio.TimeoutError:
                        mod_ban_embed.description = f'Timeout, {member} is not getting hackbanned!'
                        await msg.remove_reaction('✅', self.client.user)
                        await msg.remove_reaction('❌', self.client.user)
                        await msg.edit(embed=mod_ban_embed)
                        break
                    else:
                        if str(r.emoji) == '✅':
                            should_ban = True
                            await msg.remove_reaction('❌', self.client.user)
                            break
                        elif str(r.emoji) == '❌':
                            mod_ban_embed.description = f'Ban request denied.'
                            await msg.remove_reaction('✅', self.client.user)
                            await msg.edit(embed=mod_ban_embed)
                            break

            if not should_ban:
                return

            perpetrator = ctx.author
            icon = ctx.author.display_avatar

            try:
                await ctx.guild.ban(member, reason=reason)
                # General embed
                general_embed = discord.Embed(description=f'**Reason:** {reason}', colour=discord.Colour.dark_teal(),
                                            timestamp=ctx.message.created_at)
                general_embed.set_author(name=f'{self.client.get_user(member.id)} has been hackbanned')
                
                await ctx.send(embed=general_embed)
                
                try:
                    await member.send(embed=general_embed)
                except Exception as e:
                    pass

                # Moderation log embed
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                current_ts = await utils.get_timestamp()
                infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
                perpetrator = ctx.author.name if ctx.author else "Unknown"
                embed = discord.Embed(title='__**HackBanishment**__', colour=discord.Colour.dark_teal(),
                                    timestamp=ctx.message.created_at)
                embed.add_field(name='User info:', value=f'```Name: {self.client.get_user(member.id)}\nId: {member.id}```',
                                inline=False)
                embed.add_field(name='Reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                embed.set_author(name=self.client.get_user(ctx.author.id))
                embed.set_footer(text=f"HackBanned by {perpetrator}", icon_url=icon)
                await moderation_log.send(embed=embed)

                # Inserts a infraction into the database
                current_ts = await utils.get_timestamp()
                await self.insert_user_infraction(
                    user_id=member.id, infr_type="hackban", reason=reason,
                    timestamp=current_ts, perpetrator=ctx.author.id)

            except discord.errors.NotFound:
                await ctx.send("**Invalid user id!**", delete_after=3)

    @commands.command(aliases=['fire', 'wall', 'fire_wall'])
    @utils.is_allowed([staff_manager_role_id], throw_exc=True)
    async def firewall(self, ctx) -> None:
        """ Turns on and off the firewall.
        When turned on, it'll kick new members having accounts created in less than the set time. """

        member = ctx.author

        if not await self.check_table_firewall_exists():
            return await ctx.send(f"**It looks like the firewall is on maintenance, {member.mention}!**", delete_after=6)

        firewall_state: Tuple[int] = await self.get_firewall_state()
        if firewall_state and firewall_state[0]:
            confirm = await Confirm(f"The Firewall is activated, do you want to turn it off, {member.mention}?").prompt(ctx)
            if confirm:
                await self.set_firewall_state(0)
                await ctx.send(f"**Firewall deactivated, {member.mention}!**")
                await self.client.get_cog('ReportSupport').audio(member, 'troll_firewall_off')
        else:
            confirm = await Confirm(f"The Firewall is deactivated, do you want to turn it on, {member.mention}?").prompt(ctx)
            if confirm:
                await self.set_firewall_state(1)
                await ctx.send(f"**Firewall activated, {member.mention}!**")
                await self.client.get_cog('ReportSupport').audio(member, 'troll_firewall_on')
                
    @commands.command(aliases=['fw_min_age', 'wall_min_age', 'fw_min'])
    @commands.has_permissions(administrator=True)
    async def firewall_min_age(self, ctx, *, message : str = None) -> None:
        """ Changes the minimum account age limit for the Firewall. """

        member = ctx.author

        if not await self.check_table_firewall_exists():
            return await ctx.send(f"**It looks like the firewall is on maintenance, {member.mention}!**")

        if not message:
            return await ctx.send("**Please specify a time, all these examples work: `1w`, `3d 12h`, `12h 30m 30s` or you can also provide the time like this `43200` directly in seconds.**")

        def look_at_the_time_whoa(time):
            pattern = r'((?P<weeks>\d+)w)?\s*((?P<days>\d+)d)?\s*((?P<hours>\d+)h)?\s*((?P<minutes>\d+)m)?\s*((?P<seconds>\d+)s)?'
            match = re.match(pattern, time)
            
            if not match:
                return None
            
            time_data = match.groupdict(default="0")
            total_seconds = (
                int(time_data["weeks"]) * 604800 +
                int(time_data["days"]) * 86400 +
                int(time_data["hours"]) * 3600 +
                int(time_data["minutes"]) * 60 +
                int(time_data["seconds"])
            )
            
            return total_seconds

        try:
            total_seconds = int(message)
        except ValueError:
            total_seconds = look_at_the_time_whoa(message)
            if total_seconds is None:
                return await ctx.send(f"**Invalid time format, {member.mention}. Examples of working formats: `1w`, `3d 12h`, `12h 30m 30s` or you can also provide the time like this `43200` directly in seconds.**")

        firewall_min_age = await self.get_firewall_min_account_age()
        if firewall_min_age:
            confirm = await Confirm(f"Current firewall minimum account age limit is `{firewall_min_age[0]} seconds`.\nAre you sure you want to change it to `{total_seconds} seconds`, {member.mention}?").prompt(ctx)
            if confirm:
                await self.set_firewall_min_account_age(total_seconds)
                await ctx.send(f"**Firewall minimum account age has been changed to `{total_seconds}`!**")
        else:
            return await ctx.send(f"**Can't get minimum account age limit information. Try resetting the firewall database before changing the limit.**")

    @commands.command(aliases=['fw_reason', 'wall_reason'])
    @commands.has_permissions(administrator=True)
    async def firewall_reason(self, ctx, *, message : str = None) -> None:
        """ Changes the response reason for the Firewall. """

        member = ctx.author
        
        await ctx.message.delete()

        if not await self.check_table_firewall_exists():
            return await ctx.send(f"**It looks like the firewall is on maintenance, {member.mention}!**")

        if not message:
            return await ctx.send("**Please write a reason that's going to change the current one.**")

        firewall_reason = await self.get_firewall_reason()
        if firewall_reason:
            confirm = await Confirm(f"Current firewall response reason is `{firewall_reason[0]}`.\nAre you sure you want to change it to `{message}`, {member.mention}?").prompt(ctx)
            if confirm:
                await self.set_firewall_reason(message)
                await ctx.send(f"**Firewall response reason has been changed to `{message}`!**")
        else:
            return await ctx.send(f"**Can't get firewall's response reason from the database. Try resetting the firewall database before changing the reason.**")
        
    @commands.command(aliases=['fw_type', 'wall_type'])
    @commands.has_permissions(administrator=True)
    async def firewall_type(self, ctx, *, message : str = None) -> None:
        """ Changes the response type for the Firewall. """

        member = ctx.author

        await ctx.message.delete()

        if not await self.check_table_firewall_exists():
            return await ctx.send(f"**It looks like the firewall is on maintenance, {member.mention}!**")

        if not message:
            return await ctx.send("**You haven't provided anything in your message.**\n- Please provide one of these `timeout, kick` response types to change the current one.")
        
        if message not in ["timeout", "kick"]:
            return await ctx.send("**Type you've provided is not a possible response type for the Firewall.**\n- Please provide one of these `timeout, kick` response types to change the current one.")
            
        firewall_type = await self.get_firewall_type()
        if firewall_type:
            if firewall_type[0] != message:            
                confirm = await Confirm(f"Current firewall response type is `{firewall_type[0]}`.\nAre you sure you want to change it to `{message}`, {member.mention}?").prompt(ctx)
                if confirm:
                    await self.set_firewall_type(message)
                    await ctx.send(f"**Firewall response type has been changed to `{message}`!**")
            else:
                return await ctx.send("**Type you've provided is already the current firewall response type.**")
        else:
            return await ctx.send(f"**Can't get firewall's response type from the database. Try resetting the firewall database before changing the reason.**")

    @commands.command(aliases=['bfw', 'bypassfirewall', 'bypass_fire', 'bypassfire'])
    @utils.is_allowed([staff_manager_role_id, mod_role_id], throw_exc=True)
    async def bypass_firewall(self, ctx, user: discord.User = None) -> None:
        """ Makes a user able to bypass the Firewall.
        :param user: The user to make able to do so. """

        member: discord.Member = ctx.author

        if not user:
            return await ctx.send(f"**Please, inform a user, {member.mention}!**")

        if ctx.guild.get_member(user.id):
            return await ctx.send(f"**This user is already in the server, {member.mention}!**")

        if await self.get_bypass_firewall_user(user.id):
            return await ctx.send(f"**This user can already bypass the Firewall, {member.mention}!**")

        await self.insert_bypass_firewall_user(user.id)
        await ctx.send(f"**The `{user}` user can now bypass the Firewall, {member.mention}!**")

    @commands.command(aliases=['ubfw', 'unbypassfirewall', 'unbypass_fire', 'unbypassfire'])
    @utils.is_allowed([staff_manager_role_id], throw_exc=True)
    async def unbypass_firewall(self, ctx, user: discord.User = None) -> None:
        """ Makes a user not able to bypass the Firewall anymore.
        :param user: The user to make able to do so. """

        member: discord.Member = ctx.author

        if not user:
            return await ctx.send(f"**Please, inform a user, {member.mention}!**")

        if not await self.get_bypass_firewall_user(user.id):
            return await ctx.send(f"**This user wasn't able to bypass the Firewall, {member.mention}!**")

        await self.delete_bypass_firewall_user(user.id)
        await ctx.send(f"**The `{user}` user can no longer bypass the Firewall now, {member.mention}!**")

    @commands.command(aliases=['sbfw', 'showbypassfirewall', 'show_bypass_fire', 'showbypassfire'])
    @utils.is_allowed([staff_manager_role_id], throw_exc=True)
    async def show_bypass_firewall(self, ctx) -> None:
        """ Checks the users who are able to bypass the Firewall. """

        member: discord.Member = ctx.author

        bf_users = await self.get_bypass_firewall_users()
        if not bf_users:
            return await ctx.send(f"**No users can bypass the Firewall, {member.mention}!**")
        
        formatted_bf_users: str = '\n'.join([f"**{await self.client.fetch_user(bf_user[0])}** (`{bf_user[0]}`)" for bf_user in bf_users])

        embed: discord.Embed = discord.Embed(
            title="__Bypass Firewall Users__",
            description=formatted_bf_users,
            color=member.color,
            timestamp=ctx.message.created_at
        )
        embed.set_thumbnail(url=ctx.guild.icon)
        embed.set_footer(text=f"Requested by {member}", icon_url=member.display_avatar)
        await ctx.send(embed=embed)



    # Infraction methods
    @commands.command(aliases=['infr', 'show_warnings', 'sw', 'show_bans', 'sb', 'show_muted', 'sm'])
    @commands.check_any(utils.is_allowed([*allowed_roles, event_manager_role_id, lesson_manager_role_id, analyst_debugger_role_id], throw_exc=True), utils.is_subscriber())
    async def infractions(self, ctx, *, message : str = None) -> None:
        """ Shows all infractions of a specific user.
        :param member: The member to show the infractions from. [Optional] [Default = You] """

        allowed_room_and_user = ctx.channel.id not in watchlist_disallowed_channels and any(role.id in allowed_roles for role in ctx.author.roles)

        is_allowed = await utils.is_allowed(allowed_roles).predicate(ctx)
        is_sub = await utils.is_subscriber(throw_exc=False).predicate(ctx)
        is_lesson_manager = await utils.is_allowed([lesson_manager_role_id]).predicate(ctx)
        is_event_manager = await utils.is_allowed([event_manager_role_id]).predicate(ctx)

        # sub, not in sub infr channel
        if not is_allowed and is_sub and not (is_lesson_manager or is_event_manager) and ctx.channel.id != frog_catchers_channel_id:
            return await ctx.send(f"**Subs can only see infractions in the <#{frog_catchers_channel_id}> channel!**")

        # lesson manager, not in the infr thread
        if not is_allowed and is_lesson_manager and not (is_sub or is_event_manager) and ctx.channel.id != teacher_applicant_infraction_thread_id:
            return await ctx.send(f"**Lesson managers can only see infractions in the <#{teacher_applicant_infraction_thread_id}> thread!**")

        # event manager, not in the infr thread
        if not is_allowed and is_event_manager and not (is_sub or is_lesson_manager) and ctx.channel.id != host_applicant_infraction_thread_id:
            return await ctx.send(f"**Event managers can only see infractions in the <#{host_applicant_infraction_thread_id}> channel!**")

        # multiple roles, not in the respective channel/thread
        if not is_allowed and (is_sub or is_lesson_manager or is_event_manager) and ctx.channel.id not in {frog_catchers_channel_id, teacher_applicant_infraction_thread_id, host_applicant_infraction_thread_id}:
            return await ctx.send(f"**Users with multiple roles that has the limited infraction perms can only see infractions in their respective channels: <#{frog_catchers_channel_id}>, <#{teacher_applicant_infraction_thread_id}>, or <#{host_applicant_infraction_thread_id}>!**")

        try:
            await ctx.message.delete()
        except:
            pass

        members, _ = await utils.greedy_member_reason(ctx, message)

        if not members:
            members = [ctx.author]

        for member in members:
            user_infractions, user_warns = await self.get_user_infractions(member.id), await self.get_latest_user_infractions(member.id)

            if user_infractions:
                lwarns = len([w for w in user_warns if w[1] == 'lwarn'])
                warns = len([w for w in user_warns if w[1] == 'warn'])
                hwarns = len([w for w in user_warns if w[1] == 'hwarn'])
                mutes = len([m for m in user_infractions if m[1] == 'mute'])
                kicks = len([k for k in user_infractions if k[1] == 'kick'])
                bans = len([b for b in user_infractions if b[1] == 'ban'])
                softbans = len([sb for sb in user_infractions if sb[1] == 'softban'])
                hackbans = len([hb for hb in user_infractions if hb[1] == 'hackban'])
                wl_entries = len([wl for wl in user_infractions if wl[1] == 'watchlist'])

                non_wl_infractions = lwarns + warns + hwarns + mutes + kicks + bans + softbans + hackbans
                if not allowed_room_and_user and not non_wl_infractions and wl_entries:
                    await ctx.send(f"**<@{member.id}> doesn't have any existent infractions or watchlist entries!**")
                    continue
            else:
                await ctx.send(f"**<@{member.id}> doesn't have any existent infractions or watchlist entries!**")
                continue

            unmute_alert = ''
            if await self.get_muted_roles(member.id):
                times = await self.get_mute_time(member.id)
                if times[1] != None:
                    unmute_alert = f"\u200b\n**♦️ This user will be unmuted <t:{times[0] + times[1]}:R>**\n\n"

            user_infractions = list(user_infractions)
            user_infractions.sort(key=lambda x: x[3], reverse=False) # "reverse=True" for newest to oldest, "reverse=False" for oldest to newest 

            embed = discord.Embed(
                title=f"Infractions for {member}",
                description=f"{unmute_alert}```ini\n[Warns]: {warns+(lwarns/2)+(hwarns*2)} | [Mutes]: {mutes} | [Kicks]: {kicks}\n[Bans]: {bans+softbans} | [Hackbans]: {hackbans} | [Watchlist]: {wl_entries}```",
                color=member.color,
                timestamp=ctx.message.created_at
            )
            embed.set_thumbnail(url=member.display_avatar)
            embed.set_author(name=member.id)    
            embed.set_footer(text=f"Requested by: {ctx.author}", icon_url=ctx.author.display_avatar)

            for _, infr in enumerate(user_infractions):
                infr_date = datetime.fromtimestamp(infr[3]).strftime('%Y/%m/%d at %H:%M')
                perpetrator_member = discord.utils.get(ctx.guild.members, id=infr[5])
                perpetrator = perpetrator_member.name if perpetrator_member else "Unknown"

                if infr[1] == "watchlist":
                    if not allowed_room_and_user: continue

                embed.add_field(
                    name="\u200b",
                    value=f"> **{infr[1]}** #{infr[4]}\n> -# **{infr_date}**\n> -# by {perpetrator}\n> {infr[2]}",
                    inline=False
                )

            await ctx.send(embed=embed)

    @commands.command(aliases=['ri', 'remove_warn', 'remove_warning'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def remove_infraction(self, ctx, infrs_id : commands.Greedy[int] = None):
        """ (MOD) Removes one or more infractions by their IDs.
        :param infr_id: The infraction(s) IDs. """

        author = ctx.author
        icon = ctx.author.display_avatar

        is_staff_manager = await utils.is_allowed([staff_manager_role_id]).predicate(ctx)

        await ctx.message.delete()

        if not infrs_id:
            return await ctx.send("**Please, inform an infraction ID!**", delete_after = 3)

        for infr_id in infrs_id:
            if user_infractions := await self.get_user_infraction_by_infraction_id(infr_id):
                perms = ctx.channel.permissions_for(ctx.author)
                perpetrator_member = discord.utils.get(ctx.guild.members, id=user_infractions[0][5])
                
                if perpetrator_member == ctx.author or (is_staff_manager or perms.administrator):
                    # Moderation log embed
                    member = discord.utils.get(ctx.guild.members, id=user_infractions[0][0])
                    if not perms.administrator:
                        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                        infr_date = datetime.fromtimestamp(user_infractions[0][3]).strftime('%Y/%m/%d at %H:%M')
                        infr_type = user_infractions[0][1]
                        reason = user_infractions[0][2]
                        perpetrator = perpetrator_member.name if perpetrator_member else "Unknown"
                        
                        embed = discord.Embed(title=f'__**Removed Infraction**__ ({infr_type})', colour=discord.Colour.dark_red(),
                                            timestamp=ctx.message.created_at)
                        embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nID: {member.id}```',
                                        inline=False)
                        embed.add_field(name='Infraction info:', value=f"> #{infr_id}\n> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                        embed.set_author(name=member)
                        embed.set_thumbnail(url=member.display_avatar)
                        embed.set_footer(text=f"Removed by {author}", icon_url=icon)
                        await moderation_log.send(embed=embed)
                    # Infraction removal
                    await self.remove_user_infraction(int(infr_id))
                    await ctx.send(f"**Removed infraction with ID `{infr_id}` for {member}**")
                else:
                    await ctx.send(f"**You can only remove infractions issued by yourself!**")
            else:
                await ctx.send(f"**Infraction with ID `{infr_id}` was not found!**")

    @commands.command(aliases=['ris', 'remove_warns', 'remove_warnings'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def remove_infractions(self, ctx, *, message):
        """ (MOD) Removes all infractions for one or more users.
        :param member: The member(s) to get the infractions from. """

        await ctx.message.delete()

        members, _ = await utils.greedy_member_reason(ctx, message)

        if not members:
            return await ctx.send('**Please, inform a member!**', delete_after=3)

        for member in members:
            if user_infractions := await self.get_user_infractions(member.id):
                # Moderation log embed
                perms = ctx.channel.permissions_for(ctx.author)
                if not perms.administrator:
                    moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)

                    if user_infractions:
                        lwarns = len([w for w in user_infractions if w[1] == 'lwarn'])
                        warns = len([w for w in user_infractions if w[1] == 'warn'])
                        hwarns = len([w for w in user_infractions if w[1] == 'hwarn'])
                        mutes = len([m for m in user_infractions if m[1] == 'mute'])
                        kicks = len([k for k in user_infractions if k[1] == 'kick'])
                        bans = len([b for b in user_infractions if b[1] == 'ban'])
                        softbans = len([sb for sb in user_infractions if sb[1] == 'softban'])
                        hackbans = len([hb for hb in user_infractions if hb[1] == 'hackban'])
                        wl_entries = len([wl for wl in user_infractions if wl[1] == 'watchlist'])

                    user_infractions = list(user_infractions)
                    user_infractions.sort(key=lambda x: x[3], reverse=True)

                    embed = discord.Embed(
                        title=f"Removed Infractions for {member}",
                        description=f"```ini\n[Warns]: {warns+(lwarns/2)+(hwarns*2)} | [Mutes]: {mutes} | [Kicks]: {kicks}\n[Bans]: {bans+softbans} | [Hackbans]: {hackbans} | [Watchlist]: {wl_entries}```",
                        colour=discord.Colour.dark_red(),
                        timestamp=ctx.message.created_at
                    )
                    embed.set_thumbnail(url=member.display_avatar)
                    embed.set_author(name=member.id)
                    embed.set_footer(text=f"Removed by: {ctx.author}", icon_url=ctx.author.display_avatar)

                    for _, infr in enumerate(user_infractions):
                        infr_date = datetime.fromtimestamp(infr[3]).strftime('%Y/%m/%d at %H:%M')
                        perpetrator_member = discord.utils.get(ctx.guild.members, id=infr[5])
                        perpetrator = perpetrator_member.name if perpetrator_member else "Unknown"

                        embed.add_field(
                            name="\u200b",
                            value=f"> **{infr[1]}** #{infr[4]}\n> -# **{infr_date}**\n> -# by {perpetrator}\n> {infr[2]}",
                            inline=False
                        )
                    
                    await moderation_log.send(embed=embed)
                
                # Infraction removal    
                await self.remove_user_infractions(member.id)
                await ctx.send(f"**Removed all infractions for {member.mention}!**")
            else:
                await ctx.send(f"**{member.mention} doesn't have any existent infractions!**")		


    @commands.command(aliases=['ei'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def edit_infraction(self, ctx, infractions_ids : commands.Greedy[int] = None, *, reason: Optional[str] = ' ') -> None:
        """(MOD) Edits one or more infractions by their IDs.
        :param infr_id: The infraction(s) ID(s).
        :param reason: The updated reason of the infraction(s)."""
        
        is_admin = ctx.author.guild_permissions.administrator
        
        # Remove numbers with less than 5 digits
        string_ids = [str(int_id) for int_id in infractions_ids]
        for i, infr in enumerate(string_ids):
            if len(infr) < 5:
                reason = ' '.join(string_ids[i:]) + ' ' + reason
                del infractions_ids[i:]
                break

        await ctx.message.delete()
        if not infractions_ids:
            return await ctx.send("**Please, inform an infraction id!**", delete_after=3)

        if not is_admin and (reason is not None and len(reason) > 960):
            return await ctx.send(f"**Please, inform a reason that is lower than or equal to 960 characters, {ctx.author.mention}!**", delete_after=3)
        elif not is_admin and (reason is None or len(reason) < 16):
            return await ctx.send(f"**Please, inform a reason that is higher than 15 characters, {ctx.author.mention}!**", delete_after=3)

        for infr_id in infractions_ids:
            if user_infraction := await self.get_user_infraction_by_infraction_id(infr_id):

                # Get user by id
                member = await self.client.fetch_user(user_infraction[0][0])

                # General embed
                general_embed = discord.Embed(description=f'**New Reason:** {reason}', color=discord.Color.lighter_grey())
                general_embed.set_author(name=f"{member}'s {user_infraction[0][1].capitalize()} reason has been edited", icon_url=member.display_avatar)
                general_embed.set_footer(text=f"Edited by {ctx.author}", icon_url=ctx.author.display_avatar)

                await ctx.send(embed=general_embed)

                # Moderation log embed
                moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
                current_ts = await utils.get_timestamp()
                infr_date = datetime.fromtimestamp(current_ts).strftime('%Y/%m/%d at %H:%M')
                perpetrator = ctx.author.name if ctx.author else "Unknown"

                embed = discord.Embed(title=f'__**{user_infraction[0][1].lower()} Edited**__', colour=discord.Colour.lighter_grey(),
                                    timestamp=ctx.message.created_at)

                embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```',
                                inline=False)
                embed.add_field(name='New reason:', value=f"> -# **{infr_date}**\n> -# by {perpetrator}\n> {reason}")
                embed.set_author(name=member)
                embed.set_thumbnail(url=member.display_avatar)
                embed.set_footer(text=f"Edited by {ctx.author}", icon_url=ctx.author.display_avatar)
                await moderation_log.send(embed=embed)

                try:
                    if user_infraction[0][1] != "watchlist":
                        general_embed.set_footer() # Clears the footer so it doesn't show the staff member in the DM
                        await member.send(embed=general_embed)
                except Exception:
                    pass

                await self.edit_user_infractions(infr_id, reason)

            else:
                await ctx.send(f"**Infraction `{infr_id}` not found**")


    @commands.command()
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def cases(self, ctx, *, message: str = None) -> None:
        """ Shows people that you muted that don't have an unmute time set,
        in other words, people that you still have to deal with their case.
        :param member: The member to show the cases from. [Optional][Default=You] """
        
        await ctx.message.delete()

        perms = ctx.channel.permissions_for(ctx.author)

        staff_manager_role = discord.utils.get(ctx.guild.roles, id=staff_manager_role_id)

        members, _ = await utils.greedy_member_reason(ctx, message)

        if perms.administrator or staff_manager_role in ctx.author.roles:
            members = members if members else [ctx.message.author]
        else:
            if members:
                if members[0] != ctx.message.author:
                    return await ctx.send("**You can't do that!**", delete_after=3)

            members = [ctx.message.author]

        for member in members:
            if await utils.is_allowed(allowed_roles).predicate(channel=ctx.channel, member=member):
                # Gets muted members
                muted_members = await self.get_not_unmuted_members()
                cases = []

                for user_id, mute_ts in muted_members:
                    if ctx.guild.get_member(user_id):

                        # Gets user infractions
                        user_infractions = await self.get_user_infractions(user_id)
                        
                        for _, infraction_type, _, infraction_ts, infraction_id, perpetrator in user_infractions:
                            # If the infraction has the same time as the mute timestamp and the perpetrator is the member add to the cases
                            if infraction_type == 'mute' and infraction_ts == mute_ts and perpetrator == member.id:
                                cases.append([user_id, mute_ts])
                                break
                        
                if cases:
                    # General embed
                    embed = discord.Embed(
                        title = f"Open cases for: {member}",
                        description = '\u200b\n' + ' '.join([f"<@{user_id}> **muted on <t:{mute_ts}:d> at <t:{mute_ts}:t>**\n\n" for user_id, mute_ts in cases]),
                        timestamp=ctx.message.created_at
                    )
                    embed.set_thumbnail(url=member.display_avatar)
                    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar)
                    await ctx.send(embeds=[embed])

                else:
                    if member == ctx.author:
                        await ctx.send(f"**You don't have any open cases**", delete_after=3)
                    else:
                        await ctx.send(f"**{member} does not have any open cases**", delete_after=3)
            else:

                await ctx.send(f"**The user {member} is not a staff member**", delete_after=3)

    @commands.command(aliases=["mn", "md_nickname", "mnick", "m_nick"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def moderate_nickname(self, ctx, member: discord.Member = None) -> None:
        """ Moderates someone's nickname.
        :param member: The member for whom to moderate the nickname. """

        await ctx.message.delete()
        author: discord.Member = ctx.author

        if not member:
            return await ctx.send(f"**Please, inform a member, {author.mention}!**")

        if await self.get_moderated_nickname(member.id):
            return await ctx.send(f"**This user's nickname has already been moderated, {author.mention}!**")

        name = member.name
        nick = member.display_name
        reason: str = f"Improper Nickname: {nick}"

        try:
            await self.insert_moderated_nickname(member.id, nick)
            await member.edit(nick="Moderated Nickname")
        except Exception as e:
            print('Error at Moderate Nickname: ', e)
            return await ctx.send(f"**For some reason I couldn't moderate this user's nickname, {author.mention}!**")

        # General embed
        general_embed = discord.Embed(description=f'**Reason:** {reason}', color=discord.Color.blue())
        general_embed.set_author(name=f'{member} got their nickname moderated.', icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        # Moderation log embed
        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
        embed = discord.Embed(title='__**Moderated Nickname:**__', color=discord.Color.blue(), timestamp=ctx.message.created_at)
        embed.add_field(name='User info:', value=f'```Name: {name}\nId: {member.id}```', inline=False)
        embed.add_field(name='Reason:', value=f'```{reason}```')
        embed.set_author(name=name)
        embed.set_thumbnail(url=member.display_avatar)
        embed.set_footer(text=f"Nickname-moderated by {author}", icon_url=author.display_avatar)
        await moderation_log.send(embed=embed)
        try:
            await member.send(embed=general_embed)
        except:
            pass

    @commands.command(aliases=["umn", "umd_nickname", "umnick", "um_nick"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def unmoderate_nickname(self, ctx, member: discord.Member = None) -> None:
        """ Unmoderates someone's nickname.
        :param member: The member for whom to unmoderate the nickname. """

        author: discord.Member = ctx.author

        if not member:
            return await ctx.send(f"**Please, inform a member, {author.mention}!**")

        if not await self.get_moderated_nickname(member.id):
            return await ctx.send(f"**This user's nickname hasn't been moderated yet, {author.mention}!**")

        try:
            await self.delete_moderated_nickname(member.id)
            await member.edit(nick=None)
        except Exception as e:
            print("Error at Unmoderate Nickname: ", e)
            return await ctx.send(f"**For some reason I couldn't unmoderate this user's nickname, {author.mention}!**")
        
        # General embed
        general_embed = discord.Embed(color=discord.Color.dark_blue())
        general_embed.set_author(name=f'{member} got their nickname unmoderated.', icon_url=member.display_avatar)
        await ctx.send(embed=general_embed)
        # Moderation log embed
        moderation_log = discord.utils.get(ctx.guild.channels, id=mod_log_id)
        embed = discord.Embed(title='__**Unmoderated Nickname:**__', color=discord.Color.dark_blue(), timestamp=ctx.message.created_at)
        embed.add_field(name='User info:', value=f'```Name: {member.display_name}\nId: {member.id}```', inline=False)
        embed.set_author(name=member.display_name)
        embed.set_thumbnail(url=member.display_avatar)
        embed.set_footer(text=f"Nickname-moderated by {author}", icon_url=author.display_avatar)
        await moderation_log.send(embed=embed)
        try:
            await member.send(embed=general_embed)
        except:
            pass

    @commands.command(aliases=["smn", "smnick", "show_mn", "showmn"])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def show_moderated_nickname(self, ctx, member: discord.Member = None) -> None:
        """ Shows the user's previous nickname that got moderated.
        :param member: The member to show. """

        author: discord.Member = ctx.author
        if not member:
            return await ctx.send(f"**Please, inform a member to show, {author.mention}!**")

        if not (mn_user := await self.get_moderated_nickname(member.id)):
            return await ctx.send(f"**This user's nickname hasn't even been moderated, {author.mention}!**")

        embed: discord.Embed = discord.Embed(
            title="__Showing Moderated Nickname__",
            description=f"**User:** {member.mention} ({member.id})\n**Moderated Nickname:** {mn_user[1]}",
            color=member.color,
            timestamp=ctx.message.created_at
        )
        embed.set_thumbnail(url=member.display_avatar)
        embed.set_footer(text=f"Requested by {author}", icon_url=author.display_avatar)

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['minfr', 'muted_infr'])
    @utils.is_allowed([staff_manager_role_id], throw_exc=True)
    async def muted_infractions(self, ctx) -> None:
        """Shows the infractions for all muted members"""

        muted_role = discord.utils.get(ctx.guild.roles, id=muted_role_id)

        muted_members = []

        # Gets all muted members
        for member in ctx.guild.members:
            if muted_role in member.roles:
                muted_members.append(str(member.id))

        if not muted_members:
            return await ctx.send("**There is no muted members**")

        await self.infractions(context=ctx, message=' '.join(muted_members))

    @commands.command(aliases=['aa', 'assign_agent'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def assign_secret_agent(self, ctx, *, message : str = None) -> None:
        """ Assigns member(s) as secret agent(s).
        :param member: The member(s) to assign. """

        author = ctx.author
        is_admin = author.guild_permissions.administrator
        agent_channel = self.client.get_channel(secret_agent_channel_id)

        try:
            await ctx.message.delete()
        except:
            pass

        members, _ = await utils.greedy_member_reason(ctx, message)

        if not members:
            return await ctx.send(f"**Please, inform a member, {author.mention}!**")

        for member in members:
            perms = agent_channel.permissions_for(member)
            if is_admin or ctx.channel.id == secret_agent_channel_id:
                if not perms.view_channel:
                    await agent_channel.set_permissions(member, view_channel=True, send_messages=True)
                    await ctx.send(f"**{member.mention} has been added as an agent, {author.mention}!**")
                else:
                    await ctx.send(f"**{member.mention} is already an agent, {author.mention}!**")
            else:
                await ctx.send(f"**{author.mention}, you can only use this this command in {ctx.channel.mention}!**")
                break

    @commands.command(aliases=['ra', 'revoke_agent'])
    @utils.is_allowed(allowed_roles, throw_exc=True)
    async def revoke_secret_agent(self, ctx, *, message : str = None) -> None:
        """ Revokes secret agent status from member(s).
        :param member: The member(s) to revoke. """

        author = ctx.author
        is_admin = author.guild_permissions.administrator
        agent_channel = self.client.get_channel(secret_agent_channel_id)

        try:
            await ctx.message.delete()
        except:
            pass

        members, _ = await utils.greedy_member_reason(ctx, message)

        if not members:
            return await ctx.send(f"**Please, inform a member, {author.mention}!**")

        for member in members:
            perms = agent_channel.permissions_for(member)
            if is_admin or ctx.channel.id == secret_agent_channel_id:
                if perms.view_channel:
                    await agent_channel.set_permissions(member, overwrite=None)
                    await ctx.send(f"**{member.mention} is no longer an agent, {author.mention}!**")
                else:
                    await ctx.send(f"**{member.mention} is already not an agent, {author.mention}!**")
            else:
                await ctx.send(f"**{author.mention}, you can only use this this command in {ctx.channel.mention}!**")
                break

    @commands.command()
    @utils.not_ready()
    @utils.is_subscriber()
    async def mutevote(self, ctx, member: discord.Member) -> None:
        """ Opens a voting for server muting a member for 5 minutes
        from the voice channels.
        :param member: The member to open the votation for. """
        
        pass


def setup(client):
    client.add_cog(Moderation(client))