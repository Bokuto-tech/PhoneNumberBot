"""
This script runs a Discord bot that monitors multiple websites for new temporary phone numbers 
and sends alerts to a specified Discord channel when new numbers are found.
The bot also cleans up previous messages before sending new ones.
"""

import requests
from bs4 import BeautifulSoup
import json
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import time
import random
import asyncio

# Load environment variables from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# Configuration
WEBSITES = [
    {
        "url": "https://receive-smss.com/",
        "name": "Receive-SMSS",
        "selector": lambda soup: soup.find_all('a', href=lambda x: x and '/sms/' in x)
    },
    {
        "url": "https://quackr.io/",
        "name": "Quackr",
        "selector": lambda soup: soup.find_all('div', class_=lambda x: x and 'number-item' in (x or ''))
    },
    {
        "url": "https://sms24.me/en/numbers",
        "name": "SMS24",
        "selector": lambda soup: soup.find_all('a', class_=lambda x: x and 'number-item' in (x or ''))
    }
]

JSON_FILE = "numbers.json"
CHECK_INTERVAL_MINUTES = 15
# Maximum number of messages to delete (Discord API limit is 100)
MAX_MESSAGES_TO_DELETE = 100
# Only delete messages from the bot itself
DELETE_ONLY_BOT_MESSAGES = True

# Set up Discord bot with necessary permissions
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Function to load previously seen phone numbers
def load_previous_numbers():
    try:
        with open(JSON_FILE, 'r') as f:
            try:
                data = json.load(f)
                print(f"Loaded data type: {type(data)}")
                
                # Check if the loaded data is a list (old format) or dict (new format)
                if isinstance(data, list):
                    print("Converting old numbers format to new format...")
                    return {website["name"]: [] for website in WEBSITES}
                else:
                    # Ensure all websites are in the dictionary
                    for website in WEBSITES:
                        if website["name"] not in data:
                            data[website["name"]] = []
                    return data
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                return {website["name"]: [] for website in WEBSITES}
    except FileNotFoundError:
        print(f"File {JSON_FILE} not found, creating new structure")
        return {website["name"]: [] for website in WEBSITES}

# Function to save the current phone numbers
def save_numbers(numbers):
    with open(JSON_FILE, 'w') as f:
        json.dump(numbers, f, indent=2)

# Function to scrape phone numbers from a website
def scrape_numbers(website):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        print(f"Requesting {website['url']}...")
        response = requests.get(website["url"], headers=headers, timeout=15)
        response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        number_elements = website["selector"](soup)
        numbers = [elem.text.strip() for elem in number_elements if elem.text.strip()]
        
        numbers = [num for num in numbers if any(char.isdigit() for char in num)]
        
        print(f"Found {len(numbers)} numbers on {website['name']}")
        return numbers
    except requests.RequestException as e:
        print(f"Error scraping {website['url']}: {e}")
        return []

# Function to delete previous messages in the channel
async def delete_previous_messages(channel):
    print(f"Cleaning up previous messages in channel {channel.name}...")
    
    try:
        # Get message history
        messages_to_delete = []
        async for message in channel.history(limit=MAX_MESSAGES_TO_DELETE):
            # If DELETE_ONLY_BOT_MESSAGES is True, only delete messages from the bot
            if DELETE_ONLY_BOT_MESSAGES and message.author.id != bot.user.id:
                continue
            messages_to_delete.append(message)
        
        # If there are messages to delete
        if messages_to_delete:
            # Try bulk delete for messages less than 14 days old
            try:
                await channel.purge(limit=MAX_MESSAGES_TO_DELETE, check=lambda m: m.author.id == bot.user.id)
                print(f"Bulk deleted {len(messages_to_delete)} messages")
            except discord.errors.HTTPException:
                # If bulk delete fails (messages older than 14 days), delete one by one
                print("Bulk delete failed, deleting messages one by one...")
                for message in messages_to_delete:
                    try:
                        await message.delete()
                        # Add a small delay to avoid rate limits
                        await asyncio.sleep(0.5)
                    except discord.errors.HTTPException as e:
                        print(f"Error deleting message: {e}")
                print(f"Deleted {len(messages_to_delete)} messages individually")
    except Exception as e:
        print(f"Error while cleaning up messages: {e}")

# Function to send a message, splitting it if necessary
async def send_chunked_message(channel, message_parts, prefix=""):
    chunk = [prefix] if prefix else []
    current_length = len(prefix)
    
    for part in message_parts:
        if current_length + len(part) + 1 > 1900:
            await channel.send("\n".join(chunk))
            chunk = [part]
            current_length = len(part)
        else:
            chunk.append(part)
            current_length += len(part) + 1
    
    if chunk:
        await channel.send("\n".join(chunk))

# Periodic task to check for new phone numbers
@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_numbers():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return
    
    print(f"Bot has permission to send messages: {channel.permissions_for(channel.guild.me).send_messages}")
    
    # Delete previous messages before sending new ones
    await delete_previous_messages(channel)
    
    # Load previous numbers
    previous_numbers = load_previous_numbers()
    current_numbers = {}
    
    # Process each website with a delay between requests
    for website in WEBSITES:
        site_name = website["name"]
        print(f"Checking {site_name}...")
        
        # Get current numbers for this site
        site_numbers = scrape_numbers(website)
        current_numbers[site_name] = site_numbers
        
        # Find new numbers (in current but not in previous)
        prev_site_numbers = set(previous_numbers.get(site_name, []))
        new_site_numbers = [num for num in site_numbers if num not in prev_site_numbers]
        
        print(f"Previous numbers count: {len(prev_site_numbers)}")
        print(f"Current numbers count: {len(site_numbers)}")
        print(f"New numbers count: {len(new_site_numbers)}")
        
        if new_site_numbers:
            # Send alert for this site
            header = f"📱 New phone numbers found on {site_name}:"
            try:
                await channel.send(header)
                print(f"Sent header message to Discord")
                
                # Send the numbers in chunks
                await send_chunked_message(channel, new_site_numbers)
                
                print(f"Sent alert for {len(new_site_numbers)} new numbers from {site_name}")
            except Exception as e:
                print(f"Error sending messages to Discord: {e}")
        else:
            print(f"No new numbers found for {site_name}")
        
        # Add a random delay between requests to avoid being blocked
        if website != WEBSITES[-1]:
            delay = random.uniform(3, 7)
            print(f"Waiting {delay:.1f} seconds before next request...")
            time.sleep(delay)
    
    # Save the current numbers for the next check
    save_numbers(current_numbers)
    print("Saved current numbers to file")

@bot.command(name="check")
async def force_check(ctx):
    """Force the bot to check for new numbers immediately"""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("Checking for new phone numbers...")
        await check_numbers()
        await ctx.send("Check complete!")
    else:
        await ctx.send("You need administrator permissions to use this command.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    check_numbers.start()  # Start the periodic task

# Run the bot with the Discord token
bot.run(DISCORD_TOKEN)
