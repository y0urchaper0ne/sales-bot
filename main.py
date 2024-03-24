import re
import logging
import time
from collections import defaultdict

from googleapiclient.discovery import build
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, Application, filters
from telethon.sync import TelegramClient

from config import telegram_id, api_hash, api_id, TOKEN, YOUTUBE_API_KEY

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

tg_channels = []
last_ad_posts = {}

yt_channels = []
last_ad_videos = {}
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

def convert_link_to_text(link):
    """Извлечение названия тг-канала из ссылки"""
    pattern = r'https://t.me/(\w+)'
    match = re.match(pattern, link)
    if match:
        return f"@{match.group(1)}"


async def start(update, context):
    """Функция, запускающая бота"""
    if update.message.from_user.id == telegram_id:
        name = update.message.chat.first_name
        reply_keyboard = [['YouTube', 'Telegram']]
        await update.message.reply_text(f'Привет, {name}! это sales-бот, который поможет тебе находить ' \
                                        f'рекламодателей у блогеров. Выбери платформу для поиска 👇', 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'PLATFORM'
    else: 
        await update.message.reply_text('Похоже, у вас нет доступа')
        return ConversationHandler.END


async def youtube_menu(update, context):
    """Меню раздела ютуб"""
    reply_keyboard = [['Подписаться', 'Поиск рекламы', 'Назад']]
    await update.message.reply_text('Ты можешь подписаться на обновления ютуб-канала или произвести поиск по постам',
                                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return 'YOUTUBE_MENU'


async def youtube_handler(update, context):
    """Обработчик меню ютуба"""
    reply_keyboard = [['Назад']]
    if str(update.message.text) == 'Подписаться':
        await update.message.reply_text(f'Отправь ссылку на ютуб-канал', 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_SUB'
    elif str(update.message.text) == 'Назад':
        reply_keyboard = [['YouTube', 'Telegram']]
        await update.message.reply_text(f'Выбери платформу для поиска 👇', 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'PLATFORM'
    elif str(update.message.text) == 'Поиск рекламы':
        await update.message.reply_text('Отправь ссылку на ютуб-канал',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, 
                                                                         resize_keyboard=True))
        return 'YOUTUBE_CHANNEL'


async def youtube_channel(update, context):
    """Обработчик ютуб-канала для поиска"""
    channel = update.message.text
    if channel.startswith('https://www.youtube.com/@'):
        context.user_data['channel'] = channel
    elif channel == 'Назад':
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по видео',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_MENU'
    else: 
        reply_keyboard = [['Назад']]
        await update.message.reply_text('Некорректный формат, отправьте ссылку на ютуб-канал',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_CHANNEL'
    await update.message.reply_text("Отлично! Теперь укажи количество постов, по которым хочешь произвести поиск")
    return 'YOUTUBE_POSTS'


def get_channel_id(link):
    """Получение channelId по ссылке на канал YouTube."""
    username = link.split('/')[-1].replace('@', '')

    request = youtube.channels().list(
        part="contentDetails",
        forHandle=username
    )
    response = request.execute()
    return response['items'][0]['id']


async def youtube_posts(update, context):
    """Обработчик количества постов и поиск рекламы на канале"""
    if update.message.text == 'Назад': 
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по видео',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_MENU'
    else: 
        if int(update.message.text) > 15:
            reply_keyboard = [['Назад']]
            await update.message.reply_text(f'Слишком большой запрос :(\nВыбери количество видео поменьше',
                                            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
            return 'YOUTUBE_POSTS'     
        else:        
            context.user_data['vids'] = int(update.message.text)
            channel_link = context.user_data['channel']
            max_videos = context.user_data['vids']
            channel_id = get_channel_id(channel_link)
            username = channel_link.split('/')[-1].replace('@', '')

            request = youtube.search().list(part="snippet", 
                                            channelId=channel_id, 
                                            maxResults=max_videos, order="date")
            response = request.execute()

            await update.message.reply_text(f"Ищу рекламу в последних {max_videos} видео канала {username}")
            time.sleep(1)
            advertisers_dict = defaultdict(lambda: [0, []]) 

            for item in response['items']:
                video_id = item['id']['videoId']
                video_info = youtube.videos().list(part='snippet', id=video_id).execute()
                description = video_info['items'][0]['snippet']['description']
                if description != '' and description is not None:
                    if 'erid' in description.lower() or 'реклама' in description.lower():
                        message_link =f"https://www.youtube.com/watch?v={video_id}"
                        matches = re.findall(r'(?:ООО|АО|ИП)\s+([\'"«“”»][^\'"«“”»]+[\'"«“”»])', description)

                        if matches:
                            advertiser = matches[0]
                        else:
                            advertiser = 'Другие'
                            
                        advertisers_dict[advertiser][0] += 1
                        advertisers_dict[advertiser][1].append(message_link)

            reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
            formatted_text = "В канале размещались следующие рекламодатели:\n\n"
            if advertisers_dict:
                for advertiser, (count, links) in advertisers_dict.items():
                    formatted_text += f"{count} раз — {advertiser}:\n"
                    for link in links:
                        formatted_text += f"- {link}\n"
                    formatted_text += "\n"
            else:
                formatted_text = "В постах не было найдено рекламы"

            await update.message.reply_text(formatted_text, 
                                            reply_markup=ReplyKeyboardMarkup(reply_keyboard, 
                                                                            resize_keyboard=True))
            return 'YOUTUBE_MENU'


async def youtube_sub(update, context):
    """Обработчик подписки на ютуб-канал"""
    channel = update.message.text
    if channel.startswith('https://www.youtube.com/@') and get_channel_id(channel) not in yt_channels:
        yt_channels.append(get_channel_id(channel))
    elif channel == 'Назад':
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по видео',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_MENU'
    else: 
        reply_keyboard = [['Назад']]
        await update.message.reply_text('Некорректный формат, отправьте ссылку на ютуб-канал',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'YOUTUBE_SUB'
    reply_keyboard = [['YouTube', 'Telegram']]
    await update.message.reply_text('Канал успешно добавлен!',
                                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return 'PLATFORM'


async def check_ads_videos(update, context):
    """Проверка новых видео на каналах из подписок"""
    global yt_channels, last_ad_videos
    bot = context.bot

    try:
        if len(yt_channels) != 0:
            for channel in yt_channels:
                last_post_id = last_ad_videos.get(channel)
                request = youtube.search().list(part="snippet", 
                                                channelId=channel, 
                                                maxResults=1, order="date")
                response = request.execute()

                for item in response['items']:
                    video_id = item['id']['videoId']
                    video_info = youtube.videos().list(part='snippet', id=video_id).execute()
                    description = video_info['items'][0]['snippet']['description']
                    if (description != '' and description is not None) and last_post_id != video_id:
                        if 'erid' in description.lower() or 'реклама' in description.lower():
                            message_link =f"https://www.youtube.com/watch?v={video_id}"
                            last_ad_videos[channel] = video_id
                            await bot.send_message(telegram_id, f'Новая реклама на канале {channel}: {message_link}')
                

    except Exception as err:
        print(f"Произошла ошибка при доступе к каналу: {err}")


async def telegram_menu(update, context):
    """Меню раздела Telegram"""
    reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
    await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по постам',
                                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return 'TELEGRAM_MENU'


async def telegram_handler(update, context):
    """Обработчик меню телеграма"""
    reply_keyboard = [['Назад']]
    if str(update.message.text) == 'Подписаться':
        await update.message.reply_text(f'Отправь ссылку на телеграм-канал или его @', 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_SUB'
    elif str(update.message.text) == 'Назад':
        reply_keyboard = [['YouTube', 'Telegram']]
        await update.message.reply_text(f'Выбери платформу для поиска 👇', 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'PLATFORM'
    elif str(update.message.text) == 'Поиск рекламы':
        await update.message.reply_text('Отправь ссылку на телеграм-канал или его @',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, 
                                                                         resize_keyboard=True))
        return 'TELEGRAM_CHANNEL'


async def telegram_sub(update, context):
    """Обработчик подписки на тг-канал"""
    channel = update.message.text
    if channel.startswith('@') and channel not in tg_channels:
        tg_channels.append(channel)
    elif channel.startswith('https://t.me') and convert_link_to_text(channel) not in tg_channels:
        tg_channels.append(convert_link_to_text(channel))
    elif channel == 'Назад':
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по постам',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_MENU'
    else: 
        reply_keyboard = [['Назад']]
        await update.message.reply_text('Некорректный формат, отправьте ссылку или @',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_SUB'
    reply_keyboard = [['YouTube', 'Telegram']]
    await update.message.reply_text('Канал успешно добавлен!',
                                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return 'PLATFORM'


async def check_ads_channels(context):
    """Функция проверки новых постов с рекламой"""
    global tg_channels, last_ad_posts
    bot = context.bot
    client = TelegramClient('my-client', api_id, api_hash)

    try:
        await client.start()
        if len(tg_channels) != 0:
            for channel in tg_channels:
                last_post_id = last_ad_posts.get(channel)
                entity = await client.get_entity(channel)
                async for message in client.iter_messages(entity, limit=1):
                    if (message.raw_text != '' and message.raw_text is not None) and last_post_id != message.id:
                        if 'erid' in message.raw_text.lower() or 'реклама' in message.raw_text.lower():
                            last_ad_posts[channel] = message.id
                            message_link = f"https://t.me/{channel[1:]}/{message.id}"
                            await bot.send_message(telegram_id, f'Новая реклама в канале {channel}: {message_link}')

    except Exception as err:
        print(f"Произошла ошибка при доступе к каналу: {err}")
        
    finally:
        await client.disconnect()


async def telegram_channel(update, context):
    """Обработчик телеграм-канала"""
    channel = update.message.text
    if channel.startswith('@'):
        context.user_data['channel'] = channel
    elif channel.startswith('https://t.me'):
        context.user_data['channel'] = convert_link_to_text(channel)
    elif channel == 'Назад':
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по постам',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_MENU'
    else: 
        reply_keyboard = [['Назад']]
        await update.message.reply_text('Некорректный формат, отправьте ссылку или @',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_CHANNEL'
    await update.message.reply_text("Отлично! Теперь укажи количество постов, по которым хочешь произвести поиск")
    return 'TELEGRAM_POSTS'
    

async def telegram_posts(update, context):
    """Обработчик количества постов и поиск"""
    if update.message.text == 'Назад': 
        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        await update.message.reply_text('Ты можешь подписаться на обновления канала или произвести поиск по постам',
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return 'TELEGRAM_MENU'
    else: 
        context.user_data['posts'] = int(update.message.text)
        channel_link = context.user_data['channel']
        num_posts = context.user_data['posts']
        
        await update.message.reply_text(f"Ищу рекламу в последних {num_posts} постах канала {channel_link}")
        advertisers_dict = defaultdict(lambda: [0, []]) 
        client = TelegramClient('anon', api_id, api_hash)
        
        try:
            await client.start()
            entity = await client.get_entity(channel_link)
            async for message in client.iter_messages(entity, limit=num_posts):
                # print(message.raw_text)
                if message.raw_text != '' and message.raw_text is not None:
                    if 'erid' in message.raw_text.lower() or 'реклама' in message.raw_text.lower():
                        message_link = f"https://t.me/{channel_link[1:]}/{message.id}"
                        matches = re.findall(r'(?:ООО|АО|ИП)\s+([\'"«“”»][^\'"«“”»]+[\'"«“”»])', message.text)

                        if matches:
                            advertiser = matches[0]
                        else:
                            advertiser = 'Другие'
                
                        advertisers_dict[advertiser][0] += 1
                        advertisers_dict[advertiser][1].append(message_link)
        
        except Exception as err:
            print(f"Произошла ошибка при доступе к каналу: {err}")
        
        finally:
            await client.disconnect()

        reply_keyboard = [['Подписаться','Поиск рекламы', 'Назад']]
        formatted_text = "В канале размещались следующие рекламодатели:\n\n"
        if advertisers_dict:
            for advertiser, (count, links) in advertisers_dict.items():
                formatted_text += f"{count} раз — {advertiser}:\n"
                for link in links:
                    formatted_text += f"- {link}\n"
                formatted_text += "\n"
        else:
            formatted_text = "В постах не было найдено рекламы"

        await update.message.reply_text(formatted_text, 
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, 
                                                                         resize_keyboard=True))

        return 'TELEGRAM_MENU'


async def cancel(update, context):
    """Завершение бота"""
    await update.message.reply_text('До встречи!', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    """Основная логика рабооты бота"""
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            'PLATFORM': [MessageHandler(filters.Regex('^(YouTube)$'), youtube_menu),
                        MessageHandler(filters.Regex('^(Telegram)$'), telegram_menu)],

            'YOUTUBE_MENU': [MessageHandler(filters.TEXT & ~filters.COMMAND, youtube_handler)],
            'YOUTUBE_SUB': [MessageHandler(filters.TEXT & ~filters.COMMAND, youtube_sub)],
            'YOUTUBE_CHANNEL': [MessageHandler(filters.TEXT & ~filters.COMMAND, youtube_channel)],
            'YOUTUBE_POSTS': [MessageHandler(filters.TEXT & ~filters.COMMAND, youtube_posts)],

            'TELEGRAM_MENU': [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler)],
            'TELEGRAM_SUB': [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_sub)],
            'TELEGRAM_CHANNEL': [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_channel)],
            'TELEGRAM_POSTS': [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_posts)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(conv_handler)
    application.job_queue.run_repeating(check_ads_channels, interval=60, first=0)
    application.job_queue.run_repeating(check_ads_videos, interval=86400, first=0)

    application.run_polling()

if __name__ == "__main__":
    main()
