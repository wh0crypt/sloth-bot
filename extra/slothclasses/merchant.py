# import.standard
import os
import random
from datetime import datetime
from typing import Dict, List, Optional, Union

# import.thirdparty
import discord
from discord.ext import commands, menus
from PIL import Image, ImageDraw, ImageFont, ImageOps

# import.local
from extra import utils
from extra.menu import ConfirmSkill, OpenShopLoop, prompt_number
from extra.prompt.menu import Confirm, ConfirmButton
from extra.view import UserPetView
from mysqldb import DatabaseCore
from .player import Player, Skill

# variables.textchannel
bots_and_commands_channel_id = int(os.getenv('BOTS_AND_COMMANDS_CHANNEL_ID', 123))
sloth_subscriber_sub_id = int(os.getenv("SLOTH_SUBSCRIBER_SUB_ID", 123))

class Merchant(Player):

    emoji = '<:Merchant:839498018532753468>'
    food_rate: int = 5

    def __init__(self, client) -> None:
        self.client = client
        self.db = DatabaseCore()

    @commands.command(aliases=['sellpotion', 'potion'])
    @Player.poisoned()
    @Player.skill_on_cooldown()
    @Player.skills_locked()
    @Player.user_is_class('merchant')
    @Player.skill_mark()
    async def sell_potion(self, ctx) -> None:
        """ Puts a changing-SlothClass potion for sale for the price you want.
        Ps: It costs 50łł to do it and the item remains there for 24 hours. """

        if ctx.channel.id != bots_and_commands_channel_id:
            return await ctx.send(f"**{ctx.author.mention}, you can only use this command in {self.bots_txt.mention}!**")

        member = ctx.author

        member_fx = await self.get_user_effects(member)

        if 'knocked_out' in member_fx:
            return await ctx.send(f"**{member.mention}, you can't use your skill, because you are knocked-out!**")

        if await self.get_skill_action_by_user_id_and_skill_type(member.id, 'potion'):
            return await ctx.send(f"**{member.mention}, you already have a potion in your shop!**")

        item_price = await prompt_number(self.client, ctx, f"**{member.mention}, for how much do you want to sell your changing-Sloth-class potion?**", member)
        if item_price is None:
            return

        confirm = await ConfirmSkill(f"**{member.mention}, are you sure you want to spend `50łł` to put a potion in your shop with the price of `{item_price}`łł ?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it, then, {member.mention}!**")

        _, exists = await Player.skill_on_cooldown(skill=Skill.ONE).predicate(ctx)

        user_currency = await self.get_user_currency(member.id)
        if user_currency[1] < 50:
            return await ctx.send(f"**{member.mention}, you don't have `50łł`!**")

        item_emoji = '🍯'

        try:
            current_timestamp = await utils.get_timestamp()
            await self.insert_skill_action(
                user_id=member.id, skill_type="potion", skill_timestamp=current_timestamp,
                target_id=member.id, channel_id=ctx.channel.id, price=item_price, emoji=item_emoji
            )
            await self.client.get_cog('SlothCurrency').update_user_money(member.id, -50)
            if exists:
                await self.update_user_skill_ts(member.id, Skill.ONE, current_timestamp)
            else:
                await self.insert_user_skill_cooldown(ctx.author.id, Skill.ONE, current_timestamp)
            # Updates user's skills used counter
            await self.update_user_skills_used(user_id=member.id)
            open_shop_embed = await self.get_open_shop_embed(
                channel=ctx.channel, perpetrator_id=member.id, price=item_price, item_name='changing-Sloth-class potion', emoji=item_emoji)
            await ctx.send(embed=open_shop_embed)
        except Exception as e:
            print(e)
            return await ctx.send(f"**{member.mention}, something went wrong with it, try again later!**")
        else:
            await ctx.send(f"**{member}, your item is now in the shop, check `z!sloth_shop` to see it there!**")

    @commands.command()
    @Player.poisoned()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def sloth_shop(self, ctx) -> None:
        """ Shows all class related items in the Sloth shop. """

        potions = await self.get_open_shop_items()
        if potions:
            the_menu = menus.MenuPages(source=OpenShopLoop(potions), clear_reactions_after=True)
            await the_menu.start(ctx)
        else:
            return await ctx.send(f"**There are no items in the `Sloth class shop` yet, {ctx.author.mention}!**")

    @commands.group(aliases=['buy_item', 'buyitem', 'purchase'])
    @Player.poisoned()
    async def buy(self, ctx) -> None:
        """ Buys a specific item from a Merchant.
        (Use this without an item name to see what items you can possibly buy with this command)
        
        Ex:
        z!buy ring/potion/pet @member  """
        if ctx.invoked_subcommand:
            return

        cmd = self.client.get_command('buy')
        prefix = self.client.command_prefix
        subcommands = [f"{prefix}{c.qualified_name}" for c in cmd.commands
            ]

        subcommands = '\n'.join(subcommands)
        items_embed = discord.Embed(
            title="__Subcommads__:",
            description=f"```apache\n{subcommands}```",
            color=ctx.author.color,
            timestamp=ctx.message.created_at
        )

        await ctx.send(embed=items_embed)

    @buy.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def potion(self, ctx, member: discord.Member = None) -> None:
        """ Buys a changing-Sloth-class potion from a Merchant.
        :param member: The member from whom to buy it. """

        buyer = ctx.author
        if not member:
            return await ctx.send(f"**Please, inform a `Merchant`, {buyer.mention}!**")

        if not(merchant_item := await self.get_skill_action_by_user_id_and_skill_type(member.id, 'potion')):
            return await ctx.send(
                f"**{member} is either not a `Merchant` or they don't have a potion available for purchase, {buyer.mention}!**")

        user_info = await self.get_user_currency(buyer.id)
        sloth_profile = await self.get_sloth_profile(buyer.id)
        if not user_info or not sloth_profile:
            await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have an account yet. Click [here](https://languagesloth.com/profile/update) to create one!**"))

        elif sloth_profile[1].lower() == 'default':
            await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have a Sloth class yet. Click [here](https://languagesloth.com/profile/slothclass) to choose one!**"))

        elif sloth_profile[5]:
            await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you already have a potion, you can't buy another one!**"))

        elif user_info[1] < merchant_item[7]:
            await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, the potion costs {merchant_item[7]}, but you only have {user_info[1]}łł!**"))

        else:
            confirm = await ConfirmSkill(f"**{buyer.mention}, are you sure you want to buy a `changing-Sloth-class potion` for `{merchant_item[7]}łł`?**").prompt(ctx)
            if not confirm:
                return await ctx.send(f"**Not buying it, then, {buyer.mention}!**")

            if not await self.get_skill_action_by_user_id_and_skill_type(member.id, 'potion'):
                return await ctx.send(f"**{member.mention} doesn't have a potion available for purchase, {buyer.mention}!**")

            try:
                if wired_user := await self.get_skill_action_by_target_id_and_skill_type(target_id=member.id, skill_type='wire'):

                    siphon_percentage = 35
                    cybersloth_money = round((merchant_item[7]*siphon_percentage)/100)
                    target_money = merchant_item[7] - cybersloth_money
                    await self.client.get_cog('SlothCurrency').update_user_money(member.id, target_money)
                    await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, -merchant_item[7])
                    await self.client.get_cog('SlothCurrency').update_user_money(wired_user[0], cybersloth_money)
                    cybersloth = self.client.get_user(wired_user[0])
                    siphon_embed = discord.Embed(
                            title="__Intercepted Purchase__",
                            description=(
                                f"{buyer.mention} bought a `changing-Sloth-class potion` from {member.mention} for `{merchant_item[7]}łł`, "
                                f"but {cybersloth.mention if cybersloth else str(cybersloth)} siphoned off `{siphon_percentage}%` of the price; `{cybersloth_money}łł`! "
                                f"So the Merhcant {member.mention} actually got `{target_money}łł`!"
                            ),
                            color=buyer.color,
                            timestamp=ctx.message.created_at)
                    if cybersloth:
                        siphon_embed.set_thumbnail(url=cybersloth.display_avatar)

                    await ctx.send(
                        content=f"{buyer.mention}, {member.mention}, <@{wired_user[0]}>",
                        embed=siphon_embed)

                else:
                    pass
                    # Updates both buyer and seller's money
                    await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, - merchant_item[7])
                    await self.client.get_cog('SlothCurrency').update_user_money(member.id, merchant_item[7])

                # Gives the buyer their potion and removes the potion from the store
                await self.update_user_has_potion(buyer.id, 1)
                await self.delete_skill_action_by_target_id_and_skill_type(member.id, 'potion')
            except Exception as e:
                print(e)
                await ctx.send(embed=discord.Embed(
                    title="Error!",
                    description=f"**Something went wrong with that purchase, {buyer.mention}!**",
                    color=discord.Color.red(),
                    timestamp=ctx.message.created_at
                    ))

            else:
                await ctx.send(embed=discord.Embed(
                    title="__Successful Acquisition__",
                    description=f"{buyer.mention} bought a `changing-Sloth-class potion` from {member.mention}!",
                    color=discord.Color.green(),
                    timestamp=ctx.message.created_at
                ))

    @buy.command(aliases=['wedding', 'wedding_ring', 'weddingring'])
    @Player.poisoned()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ring(self, ctx, member: discord.Member = None) -> None:
        """ Buys a Wedding Ring from a Merchant.
        :param member: The member from whom to buy it. """

        buyer = ctx.author
        if not member:
            return await ctx.send(f"**Please, inform a `Merchant`, {buyer.mention}!**")

        if not(merchant_item := await self.get_skill_action_by_user_id_and_skill_type(member.id, 'ring')):
            return await ctx.send(
                f"**{member} is either not a `Merchant` or they don't have a ring available for purchase, {buyer.mention}!**")

        user_info = await self.get_user_currency(buyer.id)
        slothprofile = await self.get_sloth_profile(buyer.id)
        
        if not user_info:
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have an account yet. Click [here](https://languagesloth.com/profile/update) to create one!**"))

        if slothprofile[1].lower() == 'default':
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have a Sloth class yet. Click [here](https://languagesloth.com/profile/slothclass) to choose one!**"))

        if slothprofile and slothprofile[7] == 2:
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you already have two `Wedding Rings`, you can't buy another one!**"))

        if user_info[1] < merchant_item[7]:
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, the ring costs {merchant_item[7]}, but you only have {user_info[1]}łł!**"))

        confirm = await ConfirmSkill(f"**{buyer.mention}, are you sure you want to buy a `Wedding Ring` for `{merchant_item[7]}łł`?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not buying it, then, {buyer.mention}!**")

        if not await self.get_skill_action_by_user_id_and_skill_type(member.id, 'ring'):
            return await ctx.send(f"**{member.mention} doesn't have a `Wedding Ring` available for purchase, {buyer.mention}!**")

        try:
            if wired_user := await self.get_skill_action_by_target_id_and_skill_type(target_id=member.id, skill_type='wire'):

                siphon_percentage = 35
                cybersloth_money = round((merchant_item[7]*siphon_percentage)/100)
                target_money = merchant_item[7] - cybersloth_money
                await self.client.get_cog('SlothCurrency').update_user_money(member.id, target_money)
                await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, -merchant_item[7])
                await self.client.get_cog('SlothCurrency').update_user_money(wired_user[0], cybersloth_money)
                cybersloth = self.client.get_user(wired_user[0])
                siphon_embed = discord.Embed(
                        title="__Intercepted Purchase__",
                        description=(
                            f"{buyer.mention} bought a `Wedding Ring` from {member.mention} for `{merchant_item[7]}łł`, "
                            f"but {cybersloth.mention if cybersloth else str(cybersloth)} siphoned off `{siphon_percentage}%` of the price; `{cybersloth_money}łł`! "
                            f"So the Merhcant {member.mention} actually got `{target_money}łł`!"
                        ),
                        color=buyer.color,
                        timestamp=ctx.message.created_at)
                if cybersloth:
                    siphon_embed.set_thumbnail(url=cybersloth.display_avatar)

                await ctx.send(
                    content=f"{buyer.mention}, {member.mention}, <@{wired_user[0]}>",
                    embed=siphon_embed)

            else:
                # Updates both buyer and seller's money
                await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, - merchant_item[7])
                await self.client.get_cog('SlothCurrency').update_user_money(member.id, merchant_item[7])

            # Gives the buyer their ring and removes the potion from the store
            await self.update_user_rings(buyer.id)
            await self.delete_skill_action_by_target_id_and_skill_type(member.id, 'ring')
        except Exception as e:
            print(e)
            await ctx.send(embed=discord.Embed(
                title="Error!",
                description=f"**Something went wrong with that purchase, {buyer.mention}!**",
                color=discord.Color.red(),
                timestamp=ctx.message.created_at
                ))

        else:
            await ctx.send(embed=discord.Embed(
                title="__Successful Acquisition__",
                description=f"{buyer.mention} bought a `Wedding Ring` from {member.mention}!",
                color=discord.Color.green(),
                timestamp=ctx.message.created_at
                ))

    @buy.command(aliases=['pet', 'egg'])
    @Player.poisoned()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pet_egg(self, ctx, member: discord.Member = None) -> None:
        """ Buys a Pet Egg from a Merchant.
        :param member: The member from whom to buy it. """

        buyer = ctx.author
        if not member:
            return await ctx.send(f"**Please, inform a `Merchant`, {buyer.mention}!**")

        if not(merchant_item := await self.get_skill_action_by_user_id_and_skill_type(member.id, 'pet_egg')):
            return await ctx.send(
                f"**{member} is either not a `Merchant` or they don't have a pet egg available for purchase, {buyer.mention}!**")

        user_info = await self.get_user_currency(buyer.id)
        slothprofile = await self.get_sloth_profile(buyer.id)
        
        if not user_info:
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have an account yet. Click [here](https://languagesloth.com/profile/update) to create one!**"))

        if slothprofile[1].lower() == 'default':
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you don't have a Sloth class yet. Click [here](https://languagesloth.com/profile/slothclass) to choose one!**"))

        if await self.get_user_pet(buyer.id):
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, you already have a `Pet`, you can't buy another one!**"))

        if user_info[1] < merchant_item[7]:
            return await ctx.send(embed=discord.Embed(description=f"**{buyer.mention}, the pet egg costs {merchant_item[7]}, but you only have {user_info[1]}łł!**"))

        confirm = await ConfirmSkill(f"**{buyer.mention}, are you sure you want to buy a `Pet Egg` for `{merchant_item[7]}łł`?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not buying it, then, {buyer.mention}!**")

        if not await self.get_skill_action_by_user_id_and_skill_type(member.id, 'pet_egg'):
            return await ctx.send(f"**{member.mention} doesn't have a `Pet Egg` available for purchase, {buyer.mention}!**")

        try:
            if wired_user := await self.get_skill_action_by_target_id_and_skill_type(target_id=member.id, skill_type='wire'):

                siphon_percentage = 35
                cybersloth_money = round((merchant_item[7]*siphon_percentage)/100)
                target_money = merchant_item[7] - cybersloth_money
                await self.client.get_cog('SlothCurrency').update_user_money(member.id, target_money)
                await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, -merchant_item[7])
                await self.client.get_cog('SlothCurrency').update_user_money(wired_user[0], cybersloth_money)
                cybersloth = self.client.get_user(wired_user[0])
                siphon_embed = discord.Embed(
                        title="__Intercepted Purchase__",
                        description=(
                            f"{buyer.mention} bought a `Pet Egg` from {member.mention} for `{merchant_item[7]}łł`, "
                            f"but {cybersloth.mention if cybersloth else str(cybersloth)} siphoned off `{siphon_percentage}%` of the price; `{cybersloth_money}łł`! "
                            f"So the Merhcant {member.mention} actually got `{target_money}łł`!"
                        ),
                        color=buyer.color,
                        timestamp=ctx.message.created_at)
                if cybersloth:
                    siphon_embed.set_thumbnail(url=cybersloth.display_avatar)

                await ctx.send(
                    content=f"{buyer.mention}, {member.mention}, <@{wired_user[0]}>",
                    embed=siphon_embed)

            else:
                # Updates both buyer and seller's money
                await self.client.get_cog('SlothCurrency').update_user_money(buyer.id, - merchant_item[7])
                await self.client.get_cog('SlothCurrency').update_user_money(member.id, merchant_item[7])

            # Gives the buyer their pet egg and removes the potion from the store
            await self.insert_user_pet(buyer.id)
            await self.delete_skill_action_by_target_id_and_skill_type(member.id, 'pet_egg')
        except Exception as e:
            print(e)
            await ctx.send(embed=discord.Embed(
                title="Error!",
                description=f"**Something went wrong with that purchase, {buyer.mention}!**",
                color=discord.Color.red(),
                timestamp=ctx.message.created_at
                ))

        else:
            await ctx.send(embed=discord.Embed(
                title="__Successful Acquisition__",
                description=f"{buyer.mention} bought a `Pet Egg` from {member.mention}!",
                color=discord.Color.green(),
                timestamp=ctx.message.created_at
                ))

    @commands.command()
    @Player.poisoned()
    @Player.skills_used(requirement=5)
    @Player.skill_on_cooldown(skill=Skill.TWO)
    @Player.skills_locked()
    @Player.user_is_class('merchant')
    @Player.skill_mark()
    async def package(self, ctx) -> None:
        """ Buys a package from Dark Sloth Web and has a 35% chance of getting any equippable item from the Leaf Shop. """

        merchant = ctx.author

        if ctx.channel.id != bots_and_commands_channel_id:
            return await ctx.send(f"**{merchant.mention}, you can only use this command in {self.bots_txt.mention}!**")

        merchant_fx = await self.get_user_effects(merchant)
        if 'knocked_out' in merchant_fx:
            return await ctx.send(f"**{merchant.mention}, you can't use your skill, because you are knocked-out!**")

        confirm = await ConfirmSkill(f"**{merchant.mention}, are you sure you want to spend `50łł` to get a random package from the Dark Sloth Web?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not buying it, then!**")

        _, exists = await Player.skill_on_cooldown(skill=Skill.TWO).predicate(ctx)

        # Checks whether user has money
        user_currency = await self.get_user_currency(merchant.id)
        if user_currency[1] >= 50:
            await self.client.get_cog('SlothCurrency').update_user_money(merchant.id, -50)
        else:
            return await ctx.send(f"**{merchant.mention}, you don't have `50łł`!**")

        current_timestamp = await utils.get_timestamp()
        if exists:
            await self.update_user_skill_ts(merchant.id, Skill.TWO, current_timestamp)
        else:
            await self.insert_user_skill_cooldown(ctx.author.id, Skill.TWO, current_timestamp)
        # Updates user's skills used counter
        await self.update_user_skills_used(user_id=merchant.id)

        if random.random() <= 0.35:
            SlothCurrency = self.client.get_cog('SlothCurrency')
            registered_items = await SlothCurrency.get_shop_items()
            random_item = random.choice(registered_items)

            # Checks whether user already has the item
            user_has_item = await SlothCurrency.check_user_has_item(user_id=merchant.id, item_name=random_item[4])
            if user_has_item:
                # Gives the user the price of the item
                await self.client.get_cog('SlothCurrency').update_user_money(merchant.id, random_item[6])
                await ctx.send(f"**{merchant.mention}, you already have the `{random_item[4]}` item, so you got it worth of leaves instead; `{random_item[6]}łł`**")

            else:
                # Gives the user the item
                await SlothCurrency.insert_user_item(merchant.id, random_item[4], 'unequipped', random_item[5], str(random_item[3]).replace('registered_items/', ''))
                await ctx.send(f"**{merchant.mention}, you just got the `{random_item[4]}` item, which is worth `{random_item[6]}łł`**")

        else:
            await ctx.send(f"**{merchant.mention}, you had a `35%` chance of getting something from the Dark Sloth Web, it happened that today wasn't your day!**")

    async def check_shop_potion_items(self) -> None:

        """ Check on-going changing-Sloth-class potion items and their expiration time. """

        transmutations = await self.get_expired_potion_items()
        for tm in transmutations:
            await self.delete_skill_action_by_target_id_and_skill_type(tm[3], 'potion')

            channel = self.bots_txt

            await channel.send(
                content=f"<@{tm[0]}>",
                embed=discord.Embed(
                    description=f"**<@{tm[3]}>'s `changing-Sloth-class potion` has just expired! Then it's been removed from the `Sloth class shop`! 🍯**",
                    color=discord.Color.red()))

    async def check_shop_ring_items(self) -> None:

        """ Check on-going Wedding Ring items and their expiration time. """

        transmutations = await self.get_expired_ring_items()
        for tm in transmutations:
            await self.delete_skill_action_by_target_id_and_skill_type(tm[3], 'ring')

            channel = self.bots_txt

            await channel.send(
                content=f"<@{tm[0]}>",
                embed=discord.Embed(
                    description=f"**<@{tm[3]}>'s `Wedding Ring` has just expired! Then it's been removed from the `Sloth class shop`! 🍯**",
                    color=discord.Color.red()))

    async def check_shop_egg_items(self) -> None:

        """ Check on-going Pet Egg items and their expiration time. """

        transmutations = await self.get_expired_pet_egg_items()
        for tm in transmutations:
            await self.delete_skill_action_by_target_id_and_skill_type(tm[3], 'pet_egg')

            channel = self.bots_txt

            await channel.send(
                content=f"<@{tm[0]}>",
                embed=discord.Embed(
                    description=f"**<@{tm[3]}>'s `Pet Egg` has just expired! Then it's been removed from the `Sloth class shop`! 🥚**",
                    color=discord.Color.red()))

    # ========== Update ===========

    async def update_user_has_potion(self, user_id: int, has_it: int) -> None:
        """ Updates the user's protected state.
        :param user_id: The ID of the member to update.
        :param has_it: Whether it's gonna be set to true or false. """

        await self.db.execute_query("UPDATE SlothProfile SET has_potion = %s WHERE user_id = %s", (has_it, user_id))

    async def update_user_rings(self, user_id: int, increment: int = 1) -> None:
        """ Updates the user's ring counter.
        :param user_id: The ID of the member to update.
        :param increment: Incremention value. Default = 1.
        PS: Increment can be negative. """

        await self.db.execute_query("UPDATE SlothProfile SET rings = rings + %s WHERE user_id = %s", (increment, user_id))

    # ========== Get ===========
    async def get_ring_skill_action_by_user_id(self, user_id: int) -> Union[List[Union[int, str]], None]:
        """ Gets a ring skill action by reaction context.
        :param user_id: The ID of the user of the skill action. """

        return await self.db.execute_query("SELECT * FROM SlothSkills WHERE user_id = %s AND skill_type = 'ring'", (user_id,), fetch="one")

    async def get_open_shop_items(self) -> List[List[Union[str, int]]]:
        """ Gets all open shop items. """

        return await self.db.execute_query("SELECT * FROM SlothSkills WHERE skill_type in ('potion', 'ring', 'pet_egg')", fetch="all")

    async def get_open_shop_embed(self, channel, perpetrator_id: int, price: int, item_name: str, emoji: str = '') -> discord.Embed:
        """ Makes an embedded message for a magic pull action.
        :param channel: The context channel.
        :param perpetrator_id: The ID of the perpetrator of the magic pulling.
        :param price: The price of the item that Merchant put into the shop.
        :param item_name: The name of the item put into the shop. """

        timestamp = await utils.get_timestamp()

        open_shop_embed = discord.Embed(
            title="A Merchant item has been put into the `Sloth Class Shop`!",
            timestamp=datetime.fromtimestamp(timestamp)
        )
        open_shop_embed.description = f"**<@{perpetrator_id}> put a `{item_name}` into the Sloth class shop, for the price of `{price}łł`!** {emoji}"
        open_shop_embed.color = discord.Color.green()

        open_shop_embed.set_thumbnail(url="https://languagesloth.com/media/sloth_classes/Merchant.png")
        open_shop_embed.set_footer(text=channel.guild, icon_url=channel.guild.icon.url)

        return open_shop_embed
        
    @commands.command(aliases=["sellring", "ring"])
    @Player.poisoned()
    @Player.skills_used(requirement=20)
    @Player.skill_on_cooldown(Skill.THREE, 36000)
    @Player.skills_locked()
    @Player.user_is_class('merchant')
    @Player.skill_mark()
    async def sell_ring(self, ctx) -> None:
        """ Puts a Wedding Ring for sale.
        
        * Skill cost: 100łł
        * Cooldown: 10 hours. """

        if ctx.channel.id != bots_and_commands_channel_id:
            return await ctx.send(f"**{ctx.author.mention}, you can only use this command in {self.bots_txt.mention}!**")

        member = ctx.author

        member_fx = await self.get_user_effects(member)

        if 'knocked_out' in member_fx:
            return await ctx.send(f"**{member.mention}, you can't use your skill, because you are knocked-out!**")

        if await self.get_skill_action_by_user_id_and_skill_type(member.id, 'ring'):
            return await ctx.send(f"**{member.mention}, you already have a ring in your shop!**")

        item_price = await prompt_number(self.client, ctx, f"**{member.mention}, for how much do you want to sell your ring?**", member)
        if item_price is None:
            return

        confirm = await ConfirmSkill(f"**{member.mention}, are you sure you want to spend `100łł` to put a ring in your shop with the price of `{item_price}`łł ?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it, then, {member.mention}!**")

        _, exists = await Player.skill_on_cooldown(skill=Skill.THREE, seconds=36000).predicate(ctx)

        user_currency = await self.get_user_currency(member.id)
        if user_currency[1] < 100:
            return await ctx.send(f"**{member.mention}, you don't have `100łł`!**")

        await self.client.get_cog('SlothCurrency').update_user_money(member.id, -100)

        item_emoji = '💍'

        try:
            current_timestamp = await utils.get_timestamp()
            await self.insert_skill_action(
                user_id=member.id, skill_type="ring", skill_timestamp=current_timestamp,
                target_id=member.id, channel_id=ctx.channel.id, price=item_price, emoji=item_emoji
            )
            if exists:
                await self.update_user_skill_ts(member.id, Skill.THREE, current_timestamp)
            else:
                await self.insert_user_skill_cooldown(ctx.author.id, Skill.THREE, current_timestamp)
            # Updates user's skills used counter
            await self.update_user_skills_used(user_id=member.id)
            open_shop_embed = await self.get_open_shop_embed(
                channel=ctx.channel, perpetrator_id=member.id, price=item_price, item_name='Wedding Ring', emoji=item_emoji)
            await ctx.send(embed=open_shop_embed)
        except Exception as e:
            print(e)
            return await ctx.send(f"**{member.mention}, something went wrong with it, try again later!**")
        else:
            await ctx.send(f"**{member}, your item is now in the shop, check `z!sloth_shop` to see it there!**")

    @commands.command()
    @Player.poisoned()
    @commands.cooldown(1, 180, commands.BucketType.user)
    async def marry(self, ctx, suitor: discord.Member = None) -> None:
        """ Marries someone.
        :param suitor: The person to marry.
        PS: You need wedding rings to propose someone, buy one from your local Merchant.
        
        * Cost: 1000łł or 5gł when marrying more than 1 person

        Ps: Both you and your suitor must have a sum of at least 2 rings in order to marry.
        """

        member = ctx.author
        partner_limit = 4
        poly_marriage_price = 3  # Golden leaves
        first_marriage_price = 1000  # Leaves

        if not suitor:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**Please, inform who you want to marry, {member.mention}!**")

        if member.id == suitor.id:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**You cannot marry yourself, {member.mention}!**")

        if await self.get_user_marriage(member.id, suitor.id):
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**You are already married to that person, {member.mention}!**")

        member_marriages = await self.get_user_marriages(member.id)
        if len(member_marriages) >= partner_limit:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**You cannot have more than {partner_limit} partners, {member.mention}!**")

        member_currency = await self.get_user_currency(member.id)

        no_pf_view = discord.ui.View()
        no_pf_view.add_item(discord.ui.Button(style=5, label="Create Account", emoji="🦥", url="https://languagesloth.com/profile/update"))

        if not (sloth_profile := await self.get_sloth_profile(member.id)):
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send("You don't seem to have a Sloth Account, create one by clicking the button below:", view=no_pf_view)

        if not (target_sloth_profile := await self.get_sloth_profile(suitor.id)):
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**Your suitor doesn't have a Sloth Account, tell them to create one before trying this again, {member.mention}!**")

        suitor_marriages = await self.get_user_marriages(suitor.id)
        if len(suitor_marriages) >= partner_limit:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**Your suitor alreay has the limit of {partner_limit} partners, {member.mention}!**")

        p1_rings, p2_rings = sloth_profile[7], target_sloth_profile[7]

        if p1_rings + p2_rings < 2:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**You two don't have enough rings to marry each other! The sum of your rings must be greater or equal to 2, {member.mention}!**")

        # Checks the member's money
        if len(member_marriages) >= 1:  # Poly marriage uses golden leaves
            if member_currency[7] < poly_marriage_price:
                view = None
                is_member_sub = await utils.is_subscriber(check_adm=False, throw_exc=False).predicate(ctx)
                if not is_member_sub:
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(sku_id=sloth_subscriber_sub_id))
                return await ctx.send(
                    f"**For having more than 1 partner it costs `{poly_marriage_price}gł` golden leaves, you have `{member_currency[7]}gł`, {member.mention}!**",
                    view=view
                )
        else:  # Where as normal ones use leaves
            is_suitor_sub = await utils.is_subscriber(check_adm=False, throw_exc=False).predicate(ctx, member=suitor)
            if len(suitor_marriages) > 0 and not is_suitor_sub:
                return await ctx.send(f"**You can only put or join a non-subscriber polygamy if it's not your first marriage, {member.mention}!**")

            if member_currency[1] < 1000:
                self.client.get_command('marry').reset_cooldown(ctx)
                return await ctx.send(f"**You don't have `1000łł` to marry {suitor.mention}, {member.mention}!**")

        # Asks confirmation
        confirm_view = ConfirmButton(member, timeout=60)
        embed = discord.Embed(
            title="__Confirmation__", color=member.color,
            description=f"**Are you sure you wanna marry {suitor.mention}, {member.mention}?**")
        await ctx.send(embed=embed, view=confirm_view)

        await confirm_view.wait()
        if confirm_view.value is None:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**{member.mention}, you took too long to answer...**")

        if not confirm_view.value:
            self.client.get_command('marry').reset_cooldown(ctx)
            return await ctx.send(f"**Not doing it then, {member.mention}!**")

        # Asks confirmation
        confirm_view = ConfirmButton(suitor, timeout=60)
        embed = discord.Embed(
            title="__Do you wanna Marry me?__", color=int('fa377d', 16), timestamp=ctx.message.created_at,
            description=f"**{suitor.mention}, {member.mention} is proposing you for `marriage`, do you accept it? 😳**"
        ).set_thumbnail(url='https://cdn.discordapp.com/emojis/738579957936029837.png?v=1')
        await ctx.send(content=suitor.mention, embed=embed, view=confirm_view)

        await confirm_view.wait()
        if confirm_view.value is None:
            return await ctx.send(f"**{suitor.mention}, you took too long to answer...**")

        if not confirm_view.value:
            return await ctx.send(f"**Not doing it then, {suitor.mention}!**")

        if len(member_marriages) >= 1:
            await self.client.get_cog('SlothCurrency').update_user_premium_money(member.id, -poly_marriage_price)
        else:
            await self.client.get_cog('SlothCurrency').update_user_money(member.id, -first_marriage_price)
            
        # Update ring counters
        if p1_rings == 2 and p2_rings >= 1:
            await self.update_user_rings(member.id, -1)
            await self.update_user_rings(suitor.id, -1)
        elif p1_rings == 2 and p2_rings == 0:
            await self.update_user_rings(member.id, -2)
        elif p1_rings == 1:
            await self.update_user_rings(member.id, -1)
            await self.update_user_rings(suitor.id, -1)
        elif p1_rings == 0:
            await self.update_user_rings(suitor.id, -2)

        # Update marital status
        try:
            await self.insert_user_marriage(user_id=member.id, partner_id=suitor.id)
            filename, filepath = await self.make_marriage_image(member, suitor)
        except Exception as e:
            print(e)
            await ctx.send(f"**Something went wrong with this, {member.mention}!**")
        else:
            marriage_embed = await self.get_marriage_embed(ctx.channel, member, suitor, filename)
            await ctx.send(embed=marriage_embed, file=discord.File(filepath, filename=filename))
        finally:
            os.remove(filepath)

    @commands.command()
    @Player.poisoned()
    @commands.cooldown(1, 180, commands.BucketType.user)
    async def divorce(self, ctx, partner: discord.Member = None) -> None:
        """ Divorces your partner.

        :param partner: The person who to divorce.

        Cost: 500łł """

        member = ctx.author

        if not partner:
            self.client.get_command('divorce').reset_cooldown(ctx)
            return await ctx.send(f"**Please, specify who you want to divorce, {member.mention}!**")

        member_marriage = await self.get_user_marriage(member.id, partner.id)
        if not member_marriage:
            self.client.get_command('divorce').reset_cooldown(ctx)
            return await ctx.send(f"**This person is not married to you, {member.mention}!** 😔")

        partner = discord.utils.get(ctx.guild.members, id=member_marriage['partner'])
        partner = discord.Object(id=member_marriage['partner']) if not partner else partner

        # Checks the member's money
        member_currency = await self.get_user_currency(member.id)
        if member_currency[1] < 500:
            self.client.get_command('divorce').reset_cooldown(ctx)
            return await ctx.send(f"**You don't have `500łł` to divorce <@{partner.id}>, {member.mention}!**")

        # Asks confirmation
        confirm_view = ConfirmButton(member, timeout=60)
        embed = discord.Embed(
            title="__Confirmation__", color=member.color,
            description=f"**Are you really sure you wanna divorce <@{partner.id}>, {member.mention}?**")
        await ctx.send(embed=embed, view=confirm_view)

        await confirm_view.wait()
        if confirm_view.value is None:
            return await ctx.send(f"**{member.mention}, you took too long to answer...**")

        if not confirm_view.value:
            return await ctx.send(f"**Not doing it then, {member.mention}!**")

        await self.client.get_cog('SlothCurrency').update_user_money(member.id, -500)

        # Update marital status
        try:
            await self.delete_user_marriage(member.id, partner.id)
            await self.delete_user_marriage(partner.id, member.id)
            SlothReputation = self.client.get_cog("SlothReputation")
            await SlothReputation.insert_sloth_actions(label="divorce", user_id=member.id, target_id=partner.id)
        except Exception as e:
            print(e)
            await ctx.send(f"**Something went wrong with this, {member.mention}!**")
        else:
            divorce_embed = await self.get_divorce_embed(ctx.channel, member, partner)
            await ctx.send(content=f"<@{partner.id}>", embed=divorce_embed)

    async def get_user_marriage(self, user_id: int, partner_id: int) -> Optional[Dict[str, Optional[int]]]:
        """ Gets the user's partner.
        :param user_id: The ID of the user.
        :param partner_id: The partner ID. """

        marriage = await self._get_user_marriage(user_id, partner_id)
        if not marriage:
            return

        kind = "user" if marriage[0] == user_id else "partner"

        return {
            "user": marriage[0] if kind == "user" else marriage[1],
            "partner": marriage[1] if kind == "user" else marriage[0],
            "timestamp": marriage[2],
            "honeymoon": marriage[3],
        }

    async def get_user_marriages(self, user_id: int) -> List[Dict[str, Optional[int]]]:
        """ Gets the user's partner.
        :param user_id: The ID of the user. """

        marriages = await self._get_user_marriages(user_id)
        if not marriages:
            return []

        marriage_maps: List[Dict[str, Optional[int]]] = []

        for marriage in marriages:

            kind = "user" if marriage[0] == user_id else "partner"

            marriage_maps.append({
                "user": marriage[0] if kind == "user" else marriage[1],
                "partner": marriage[1] if kind == "user" else marriage[0],
                "timestamp": marriage[2],
                "honeymoon": marriage[3],
            })
        return marriage_maps

    async def make_marriage_image(self, p1: discord.Member, p2: discord.Member) -> List[str]:

        filename = f"marriage_{p1.id}_{p2.id}.png"

        medium = ImageFont.truetype("built titling sb.ttf", 60)
        SlothCurrency = self.client.get_cog('SlothCurrency')
        background = Image.open(await SlothCurrency.get_user_specific_type_item(p1.id, 'background'))

        # Get PFPs
        pfp1 = await utils.get_user_pfp(p1, 250)
        pfp2 = await utils.get_user_pfp(p2, 250)

        background.paste(pfp1, (150, 200), pfp1)
        # background.paste(heart, (250, 250), heart)
        background.paste(pfp2, (400, 200), pfp2)

        # Writing names
        draw = ImageDraw.Draw(background)
        W, H = (800,600)

        w1, h1 = draw.textsize(str(p1), font=medium)
        w2, h2 = draw.textsize(str(p2), font=medium)

        draw.text(((W-w1)/2, 50), str(p1), fill="black", font=medium)
        draw.text(((W-w2)/2, 500), str(p2), fill="black", font=medium)

        filepath = f'media/temporary/{filename}'
        background.save(filepath, 'png', quality=90)
        return filename, filepath

    async def get_marriage_embed(self, channel, perpetrator: discord.Member, suitor: discord.Member, filename: str) -> discord.Embed:
        """ Makes an embedded message for a marriage action.
        :param channel: The context channel.
        :param perpetrator: The perpetrator of the proposal.
        :param suitor: The suitor. """

        timestamp = await utils.get_timestamp()

        marriage_embed = discord.Embed(
            title="A Marriage is now being Celebrated!",
            description=f"**{perpetrator.mention} has just married {suitor.mention}!** ❤️💍💍❤️",
            color=int('fa377d', 16),
            timestamp=datetime.fromtimestamp(timestamp)
        )
        
        marriage_embed.set_image(url=f"attachment://{filename}")
        marriage_embed.set_footer(text=channel.guild, icon_url=channel.guild.icon.url)

        return marriage_embed

    async def get_divorce_embed(self, channel, perpetrator: discord.Member, partner: Union[discord.User, discord.Member]) -> discord.Embed:
        """ Makes an embedded message for a divorce action.
        :param channel: The context channel.
        :param perpetrator: The perpetrator of the divorce.
        :param partner: The partner. """

        timestamp = await utils.get_timestamp()

        marriage_embed = discord.Embed(
            title="Oh no, a Marriage has been Ruined!",
            description=f"**{perpetrator.mention} has just divorced <@{partner.id}>!** 💔💔",
            color=int('fa377d', 16),
            timestamp=datetime.fromtimestamp(timestamp)
        )
        
        marriage_embed.set_thumbnail(url="https://media.tenor.com/images/99bba4c52c034aa6c29f51df547b6206/tenor.gif")
        marriage_embed.set_footer(text=channel.guild, icon_url=channel.guild.icon.url)

        return marriage_embed

    @commands.command(aliases=['sell_mascot'])
    @Player.poisoned()
    @Player.skills_used(requirement=50)
    @Player.skill_on_cooldown(skill=Skill.FOUR)
    @Player.skills_locked()
    @Player.user_is_class('merchant')
    @Player.skill_mark()
    async def sell_pet(self, ctx) -> None:
        """ Sells a pet egg.
        
        PS: You must be a responsible parent, otherwise your pet will 'vanish'.
        
        • Delay = 1 day
        • Cost = 500łł
        • Pets stay up to 5 days in the Sloth Shop. """

        
        if ctx.channel.id != bots_and_commands_channel_id:
            return await ctx.send(f"**{ctx.author.mention}, you can only use this command in {self.bots_txt.mention}!**")

        member = ctx.author

        member_fx = await self.get_user_effects(member)

        if 'knocked_out' in member_fx:
            return await ctx.send(f"**{member.mention}, you can't use your skill, because you are knocked-out!**")

        if await self.get_skill_action_by_user_id_and_skill_type(member.id, 'pet_egg'):
            return await ctx.send(f"**{member.mention}, you already have a pet egg in your shop!**")

        item_price = await prompt_number(self.client, ctx, f"**{member.mention}, for how much do you want to sell your pet egg?**", member)
        if item_price is None:
            return

        confirm = await ConfirmSkill(f"**{member.mention}, are you sure you want to spend `500` to put a pet in your shop with the price of `{item_price}`łł ?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it, then, {member.mention}!**")

        _, exists = await Player.skill_on_cooldown(skill=Skill.FOUR).predicate(ctx)

        user_currency = await self.get_user_currency(member.id)
        if user_currency[1] < 500:
            return await ctx.send(f"**{member.mention}, you don't have `500łł`!**")

        await self.client.get_cog('SlothCurrency').update_user_money(member.id, -500)

        item_emoji = '🥚'

        try:
            current_timestamp = await utils.get_timestamp()
            await self.insert_skill_action(
                user_id=member.id, skill_type="pet_egg", skill_timestamp=current_timestamp,
                target_id=member.id, channel_id=ctx.channel.id, price=item_price, emoji=item_emoji
            )
            if exists:
                await self.update_user_skill_ts(member.id, Skill.FOUR, current_timestamp)
            else:
                await self.insert_user_skill_cooldown(ctx.author.id, Skill.FOUR, current_timestamp)
            # Updates user's skills used counter
            await self.update_user_skills_used(user_id=member.id)
            open_shop_embed = await self.get_open_shop_embed(
                channel=ctx.channel, perpetrator_id=member.id, price=item_price, item_name='Pet Egg', emoji=item_emoji)
            await ctx.send(embed=open_shop_embed)
        except Exception as e:
            print(e)
            return await ctx.send(f"**{member.mention}, something went wrong with it, try again later!**")
        else:
            await ctx.send(f"**{member}, your item is now in the shop, check `z!sloth_shop` to see it there!**")

    @commands.group(aliases=["mascot"])
    @Player.poisoned()
    @Player.kidnapped()
    async def pet(self, ctx) -> None:
        """ Command for managing and interacting with a pet.
        (Use this without a subcommand to see all subcommands available) """
        if ctx.invoked_subcommand:
            return

        prefix = self.client.command_prefix
        subcommands = [f"{prefix}{c.qualified_name}" for c in ctx.command.commands
            ]

        subcommands = '\n'.join(subcommands)
        items_embed = discord.Embed(
            title="__Subcommads__:",
            description=f"```apache\n{subcommands}```",
            color=ctx.author.color,
            timestamp=ctx.message.created_at
        )

        await ctx.send(embed=items_embed)

    @pet.command(name="hatch")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def _pet_hatch(self, ctx) -> None:
        """ Hatches your pet egg. """

        member: discord.Member = ctx.author

        user_pet = await self.get_user_pet(member.id)
        if not user_pet:
            return await ctx.send(f"**You don't have an egg to hatch, {member.mention}!**")
        if user_pet[2].lower() != 'egg':
            return await ctx.send(f"**You already hatched your pet egg, {member.mention}!**")
        
        embed: discord.Embed = discord.Embed(
            title="__Pet Breed Selection__",
            color=member.color,
            timestamp=ctx.message.created_at
        )
        embed.set_author(name=member, icon_url=member.display_avatar)
        embed.set_thumbnail(url=member.display_avatar)
        embed.set_footer(text="3 minutes to select", icon_url=ctx.guild.icon.url)

        view: discord.ui.View = UserPetView(member)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        await utils.disable_buttons(view)
        await msg.edit(view=view)

        if view.selected_pet is None:
            return

        if not view.selected_pet:
            return

        await self.update_user_pet_name(member.id, view.selected_pet)
        await self.update_user_pet_breed(member.id, view.selected_pet.lower())
        await ctx.send(f"**Your `Pet Egg` has been successfully hatched into a `{view.selected_pet}`, {member.mention}!**")

    @pet.command(name="change_name", aliases=['name', 'c_name', 'update_name'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def _pet_change_name(self, ctx, *, pet_name: str = None) -> None:
        """ Changes the pet's name.
        :param pet_name: The new pet name to change to.
        
        * Price: 250.
        * Character limit: 25. """

        member: discord.Member = ctx.author
        if not (user_pet := await self.get_user_pet(member.id)):
            return await ctx.send(f"**You don't even have a pet, you cannot change it's name, {member.mention}!**")

        if user_pet[2].lower() == 'Egg':
            return await ctx.send(f"**You cannot change the name of an unhatched egg, {member.mention}!**")

        if not pet_name:
            return await ctx.send(f"**Please, inform a name for your pet, {member.mention}!**")

        if pet_name.lower() == 'egg':
            return await ctx.send(f"**You cannot put that name, {member.mention}!**")

        if len(pet_name) > 25:
            return await ctx.send(f"**The limit of characters for the name is 25, {member.mention}!**")

        SlothCurrency = self.client.get_cog('SlothCurrency')
        user_money = await SlothCurrency.get_user_currency(member.id)
        if user_money[0][1] < 250:
            return await ctx.send(f"**You don't have 250łł to change your pet's nickname, {member.mention}!**")

        confirm = await Confirm(f"**Are you sure you want to spend `250łł` to change your pet's name to `{pet_name}`?**").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it then, {member.mention}!**")

        await SlothCurrency.update_user_money(member.id, -250)
        await self.update_user_pet_name(member.id, pet_name)
        await ctx.send(f"**Successfully updated your pet {user_pet[2]}'s nickname from `{user_pet[2]}` to `{pet_name}`, {member.mention}!**")

    @pet.command(name="see", aliases=["show", "display", "render"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def _pet_see(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None) -> None:
        """ Sees someone's pet.
        :param member: The member from whom to show the pet. [Optional][Default = You] """

        author: discord.Member = ctx.author

        if not member:
            member = author

        user_pet = await self.get_user_pet(member.id)
        if not user_pet:
            if author == member:
                return await ctx.send(f"**You don't have a pet, {member.mention}!**")
            else:
                return await ctx.send(f"**{member} doesn't have a pet, {author.mention}!**")

        # Gets parents' profile pictures
        pet_owner_pfp = await utils.get_user_pfp(member)
        auto_feed = True if user_pet[8] else False

        # Makes the Pet's Image

        small = ImageFont.truetype("built titling sb.ttf", 45)
        background = Image.open(f"./sloth_custom_images/background/base_pet_background.png")
        hud = Image.open(f"./sloth_custom_images/hud/base_pet_hud.png")
        breed = Image.open(f"./sloth_custom_images/pet/{user_pet[2].lower()}.png")

        background.paste(hud, (0, 0), hud)
        background.paste(pet_owner_pfp, (5, 5), pet_owner_pfp)
        background.paste(breed, (0, 0), breed)
        draw = ImageDraw.Draw(background)
        draw.text((320, 5), str(user_pet[1]), fill="white", font=small)
        draw.text((5, 70), f"LP: {user_pet[3]}", fill="red", font=small)
        draw.text((5, 120), f"Food: {user_pet[4]}", fill="brown", font=small)
        draw.text((5, 550), f"Auto Feed: {auto_feed}", fill="black", font=small)
        file_path = f"media/temporary/user_pet-{member.id}.png"
        background.save(file_path)

        # Sends the Pet's Image
        await ctx.send(file=discord.File(file_path))
        return os.remove(file_path)

    async def check_pet_food(self) -> None:
        """ Checks pet food statuses. """

        current_time = await utils.get_time_now()
        current_ts =  current_time.timestamp()
        pets = await self.get_hungry_pets(current_ts)
        SlothCurrency = self.client.get_cog("SlothCurrency")

        for pet in pets:
            if pet[2].lower() == 'egg':
                continue

            try:
                # Checks whether pet has food
                if pet[4] >= 5:
                    # Increments LP if it needs
                    if pet[3] < 100:
                        await self.update_user_pet_lp(pet[0], 5, current_ts)
                    # Subtracts food
                    await self.update_user_pet_food(pet[0], -5, current_ts)

                else:
                    # Autofeeds if it's enabled
                    if pet[8] and not pet[4]:
                        user_currency = await SlothCurrency.get_user_currency(pet[0])
                        money = user_currency[0][1]
                        food_points, req_money = await self.get_required_feed_pet_money(pet[4], money)
                        if user_currency and money >= req_money:
                            await SlothCurrency.update_user_money(pet[0], -req_money)
                            await self.update_user_pet_food(pet[0], food_points, current_ts)

                            embed = discord.Embed(
                                title="__Pet has been Fed__",
                                description=f"**You just auto-fed `{pet[1]}` with `{req_money}łł`, now it has `{food_points}` food points, <@{pet[0]}>!**",
                                color=discord.Color.green(),
                                timestamp=current_time
                            )

                            member = self.client.get_user(pet[0])
                            if member:
                                await member.send(embed=embed)
                            continue

                    # Checks whether pet has lp
                    if pet[3] - 5 > 0: 
                        await self.update_user_pet_lp(pet[0], -5, current_ts)
                        await self.update_user_pet_food(pet[0], 0, current_ts)
                    else:
                        # Pet died
                        channel = self.bots_txt
                        SlothReputation = self.client.get_cog("SlothReputation")
                        await SlothReputation.insert_sloth_actions(label="pet_death", user_id=pet[0], target_id=pet[1])
                        await self.delete_user_pet(pet[0])

                        embed: discord.Embed = discord.Embed(
                            description=f"**Sadly, your pet `{pet[2]}` named `{pet[1]}` starved to death because you didn't feed it for a while. My deepest feelings...**",
                            color=discord.Color.red())

                        file_path = await self.make_pet_death_image(pet)
                        embed.set_image(url="attachment://user_pet_death.png")
                        # Sends the Pet's Image
                        await channel.send(content=f"<@{pet[0]}>", embed=embed, file=discord.File(file_path, filename="user_pet_death.png"))
                        os.remove(file_path)
            except Exception as e:
                print('Pet death error', e)
                pass

    async def make_pet_death_image(self, pet: List[Union[int, str]]) -> str:
        """ Makes an embed for the pet's death.
        :param pet: The data from the dead pet. """
    
        medium = ImageFont.truetype("built titling sb.ttf", 60)
        background = Image.open(f"./sloth_custom_images/background/base_pet_background.png")
        breed = Image.open(f"./sloth_custom_images/pet/{pet[2].lower()}.png")

        background.paste(breed, (0, 0), breed)
        draw = ImageDraw.Draw(background)
        draw.text((320, 260), "R.I.P.", font=medium)
        draw.text((320, 310), str(pet[1]), font=medium)
        file_path = f"media/temporary/user_pet_death-{pet[0]}.png"
        # Makes the image gray
        background = ImageOps.grayscale(background)
        # Saves image
        background.save(file_path)

        return file_path

    @pet.command(name="feed", aliases=["give_food", "f"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def _pet_feed(self, ctx, leaves: str = None) -> None:
        """ Feeds your pet.
        :param leaves: The amount of leaves you want to give to your pet.

        PS: You feed your pet with leaves.
        Each leave gives 5 life points to your pet. """

        member: discord.Member = ctx.author

        if not leaves:
            return await ctx.send(f"**Please, inform an amount of leaves to feed your pet, {member.mention}!**")

        user_pet = await self.get_user_pet(member.id)
        if not user_pet:
            return await ctx.send(f"**You don't have a pet, {member.mention}!**")

        try:
            leaves = int(leaves)
        except ValueError:
            return await ctx.send(f"**Please, inform a valid amount of leaves, {member.mention}!**")

        if leaves <= 0:
            return await ctx.send(f"**Please, inform an amount of leaves that is greater than 0, {member.mention}!**")

        current_ts = await utils.get_timestamp()

        food_points: int = user_pet[4]
        temp_points,temp_leaves, = await self.get_required_feed_pet_money(food_points, leaves)

        confirm_view = ConfirmButton(member, timeout=60)
        msg = await ctx.send(
            content=f"**Are you sure you want to spend `{temp_leaves}` out of `{leaves}łł` to recover `{temp_points}fp` to your pet, {member.mention}!**",
            view=confirm_view)
        await confirm_view.wait()

        SlothCurrency = self.client.get_cog("SlothCurrency")

        user_currency = await self.get_user_currency(member.id)
        if user_currency[1] < temp_leaves:
            return await ctx.send(f"**You don't have `{temp_leaves}` leaves to feed your pet, {member.mention}!**")
        
        if confirm_view.value:
            await SlothCurrency.update_user_money(member.id, -temp_leaves)
            await self.update_user_pet_food(member.id, temp_points, current_ts)
            embed = discord.Embed(
                title="__Pet has been Fed__",
                description=f"**You just fed `{user_pet[1]}` with `{temp_leaves}łł`, now it has `{food_points}` food points, {member.mention}!**",
                color=discord.Color.green(),
                timestamp=ctx.message.created_at
            )

            await ctx.send(embed=embed)
            # Tries to complete a quest, if possible.
            await self.client.get_cog('SlothClass').complete_quest(member.id, 12)

        await utils.disable_buttons(confirm_view)
        await msg.edit(view=confirm_view)

    @pet.command(name="auto_feed", aliases=['af', 'autofeed', 'feed_auto', 'feedauto'])
    async def _pet_auto_feed(self, ctx) -> None:
        """ Puts the pet into the auto feed mode. """

        if not ctx.guild:
            return await ctx.send("**Don't use it here!**")

        member = ctx.author

        user_pet = await self.get_user_pet(member.id)
        if not user_pet:
            return await ctx.send(f"**You don't have a pet, {member.mention}!**")

        auto_feed_int = user_pet[8]
        auto_feed = 'on' if auto_feed_int else 'off'
        reverse_auto_feed = 'off' if auto_feed_int else 'on'

        confirm = await ConfirmSkill(f"Your pet's auto pay mode is currently turned `{auto_feed}`, do you wanna turn it `{reverse_auto_feed}`, {member.mention}?").prompt(ctx)
        if not confirm:
            return await ctx.send(f"**Not doing it then, {member.mention}!**")

        await self.update_pet_auto_feed(member.id, not auto_feed_int)
            
        await ctx.send(f"**Your pet's auto pay mode has been turned `{reverse_auto_feed}`, {member.mention}!**")

    async def get_required_feed_pet_money(self, food_points: int, leaves: int) -> int:
        """ Gets the required amount of leaves to feed the pet,
        and the amount of food points the user can pay for.
        :param food_points: The pet's current food points.
        :param leaves: The user's current amount of leaves. """

        temp_points = temp_leaves = 0
        food_rate: int = self.food_rate  # The life points each leaf gives to the pet

        for _ in range(leaves):
            
            if food_points + food_rate <= 100:
                temp_points += food_rate
                temp_leaves += 1
                food_points += food_rate
            else:
                break

        return temp_points, temp_leaves
