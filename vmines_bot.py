import os
import json
import random
import asyncio
import datetime
import time
from typing import Dict, List, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
import re

# Конфигурация
BOT_TOKEN = "7567307567:AAHNkw_4gmm90K74W7InOF_GL75bDqfsRk4"
ADMIN_PASSWORD = "1221"
ADMIN_IDS = []  # Здесь будут ID администраторов
BONUS_AMOUNT = (50, 5000)  # Минимальный и максимальный бонус
INITIAL_BALANCE = 5000  # Начальный баланс для новых пользователей

# Коэффициенты для игры в мины (мультипликативные)
MINE_MULTIPLIERS = {
    1: 1.05,   # +5% за каждую клетку
    2: 1.11,   # +11% за каждую клетку
    3: 1.17,   # +17% за каждую клетку
    4: 1.22,   # +22% за каждую клетку
    5: 1.28,   # +28% за каждую клетку
    6: 1.35    # +35% за каждую клетку
}

# Коэффициенты для игры в золото (в обратном порядке)
GOLD_MULTIPLIERS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]

# База данных
class Database:
    def __init__(self, filename="db/users.json"):
        self.filename = filename
        self.data = {}
        self.promocodes = {}
        self.load()
    
    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.data = data.get('users', {})
                    self.promocodes = data.get('promocodes', {})
                    
                    # Загружаем администраторов из базы данных
                    for user_id, user_data in self.data.items():
                        if user_data.get('is_admin', False):
                            ADMIN_IDS.append(int(user_id))
            except:
                self.data = {}
                self.promocodes = {}
        else:
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            self.data = {}
            self.promocodes = {}
    
    def save(self):
        data = {
            'users': self.data,
            'promocodes': self.promocodes
        }
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    def get_user(self, user_id):
        if str(user_id) not in self.data:
            self.data[str(user_id)] = {
                "balance": INITIAL_BALANCE,
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "won_amount": 0,
                "lost_amount": 0,
                "registration_date": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                "last_bonus": None,
                "status": "Игрок",
                "username": "",
                "banned": False,
                "active_game": None,
                "is_admin": False
            }
        return self.data[str(user_id)]
    
    def update_user(self, user_id, data):
        user = self.get_user(user_id)
        user.update(data)
        self.save()
    
    def get_top_users(self, limit=10):
        # Исключаем администраторов из топа
        users = [(uid, data) for uid, data in self.data.items() 
                if not data.get("banned", False) and not data.get("is_admin", False)]
        sorted_users = sorted(users, key=lambda x: x[1]["balance"], reverse=True)
        return sorted_users[:limit]
    
    def add_promocode(self, code, amount, uses=1):
        self.promocodes[code] = {
            'amount': amount,
            'uses': uses,
            'used_by': []
        }
        self.save()
    
    def use_promocode(self, code, user_id):
        if code in self.promocodes:
            promocode = self.promocodes[code]
            if user_id not in promocode['used_by'] and len(promocode['used_by']) < promocode['uses']:
                promocode['used_by'].append(user_id)
                self.save()
                return promocode['amount']
        return 0

# Инициализация базы данных
db = Database()

# Вспомогательные функции
def format_number(num):
    if num >= 1000000:
        return f"{num/1000000:.2f}kk".replace('.', ',')
    elif num >= 1000:
        return f"{num/1000:.1f}k".replace('.', ',')
    return str(num)

def parse_bet(text, user_balance=None):
    text = text.lower().replace(' ', '').replace(',', '.')
    
    # Обработка "все"
    if text == 'все' or text == 'all':
        return user_balance if user_balance is not None else 0
    
    # Обработка числовых значений с приставками
    if 'kk' in text:
        num = float(text.replace('kk', '')) * 1000000
    elif 'k' in text:
        num = float(text.replace('k', '')) * 1000
    else:
        try:
            num = float(text)
        except ValueError:
            return 0
    
    return int(num)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    user_data['username'] = user.username or user.full_name
    db.update_user(user.id, user_data)
    
    welcome_text = (
        "Привет 👋 Я Vmines Bot!\n\n"
        "💣 Этот бот создан что бы играть в игры и веселиться с друзьями или со своей семьёй, "
        "не теряй время и начни играть прямо щас🧨\n\n"
        "🤔 Итак, во что будем играть? Просто напиши /game, и начинай!\n\n"
        "❓Остались еще вопросы — 👉 /help"
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 Список команд:\n\n"
        "🎮 Игровые команды:\n"
        "/game - Меню игр\n"
        "/mines [ставка] [количество мин] - Игра в мины\n"
        "/football [ставка] - Футбол\n"
        "/basketball [ставка] - Баскетбол\n"
        "/gold [ставка] - Игра в золото\n"
        "/roulette [ставка] [цвет/число] - Рулетка\n"
        "/21 [ставка] - Игра 21\n"
        "/cubes [ставка] [число] - Игра в кости\n\n"
        "👤 Команды профиля:\n"
        "/profile - Ваш профиль\n"
        "/balance - Баланс\n"
        "/bonus - Ежедневный бонус\n"
        "/top - Топ игроков\n"
        "/give [сумма] [@username] - Перевести деньги\n"
        "/promo [код] - Активировать промокод\n\n"
        "❓Прочие команды:\n"
        "/start - Начать работы с ботом\n"
        "/help - Помощь"
    )
    
    await update.message.reply_text(help_text)

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💣 Мины", callback_data="game_mines")],
        [InlineKeyboardButton("⚽️ Футбол", callback_data="game_football")],
        [InlineKeyboardButton("🏀 Баскетбол", callback_data="game_basketball")],
        [InlineKeyboardButton("🥇 Золото", callback_data="game_gold")],
        [InlineKeyboardButton("🎰 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton("🃏 21", callback_data="game_twentyone")],
        [InlineKeyboardButton("🎲 Кости", callback_data="game_cubes")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎮 Выберите игру:",
        reply_markup=reply_markup
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    # Получаем место в топе
    top_users = db.get_top_users(10000)
    user_rank = next((i+1 for i, (uid, _) in enumerate(top_users) if uid == str(user.id)), 99999)
    
    profile_text = (
        f"🆔 Профиль: {user.id}\n"
        "·····················\n"
        f"├ 👤 {user.full_name}\n"
        f"├ ⚡️ Статус: {user_data['status']}\n"
        f"├ 🎮 Сыграно игр: {format_number(user_data['games_played'])}\n"
        f"├ 🏆 Место в топе: {format_number(user_rank)}\n"
        f"├ 🟢 Выиграно: {format_number(user_data['won_amount'])} mCoin\n"
        f"├ 📉 Проиграно: {format_number(user_data['lost_amount'])} mCoin\n"
        f"📅 Дата регистрации: {user_data['registration_date']}\n"
        "·····················\n"
        f"💰 Баланс: {format_number(user_data['balance'])} mCoin"
    )
    
    await update.message.reply_text(profile_text)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    balance_text = (
        f"💰Баланс: {format_number(user_data['balance'])} Coin\n"
        "·····················\n"
        f"💣 Сиграно игр: {format_number(user_data['games_played'])}\n"
        f"🗿 Проиграно Coin: {format_number(user_data['lost_amount'])}"
    )
    
    await update.message.reply_text(balance_text)

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    now = datetime.datetime.now()
    
    if user_data['last_bonus']:
        last_bonus = datetime.datetime.strptime(user_data['last_bonus'], "%Y-%m-%d %H:%M:%S")
        time_diff = now - last_bonus
        
        if time_diff.total_seconds() < 24 * 3600:
            next_bonus = last_bonus + datetime.timedelta(hours=24)
            time_left = next_bonus - now
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"Вы уже получали бонус сегодня. Следующий бонус вы сможете получить через {hours}ч {minutes}м"
            )
            return
    
    bonus_amount = random.randint(BONUS_AMOUNT[0], BONUS_AMOUNT[1])
    user_data['balance'] += bonus_amount
    user_data['last_bonus'] = now.strftime("%Y-%m-%d %H:%M:%S")
    db.update_user(user.id, user_data)
    
    await update.message.reply_text(
        f"🎉 Вы получили бонус: {format_number(bonus_amount)} mCoin!\n"
        f"💰 Теперь ваш баланс: {format_number(user_data['balance'])} mCoin"
    )

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = db.get_top_users(10)
    
    if not top_users:
        await update.message.reply_text("📊 Пока нет игроков в топе")
        return
    
    top_text = "🏆 Топ 10 игроков:\n\n"
    
    for i, (user_id, user_data) in enumerate(top_users, 1):
        try:
            user = await context.bot.get_chat(user_id)
            username = user.full_name
        except:
            username = user_data.get('username', 'Неизвестный')
        
        top_text += f"{i}. {username} - {format_number(user_data['balance'])} mCoin\n"
    
    await update.message.reply_text(top_text)

async def give_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    # Проверяем, является ли сообщение ответом на другое
    if update.message.reply_to_message:
        receiver_id = update.message.reply_to_message.from_user.id
        receiver_username = update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.full_name
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: ответьте на сообщение пользователя с /give [сумма]")
            return
        
        try:
            amount = parse_bet(context.args[0], user_data['balance'])
        except:
            await update.message.reply_text("Неверный формат суммы")
            return
    else:
        if len(context.args) < 2:
            await update.message.reply_text("Использование: /give [сумма] [@username] или ответьте на сообщение пользователя с /give [сумма]")
            return
        
        try:
            amount = parse_bet(context.args[0], user_data['balance'])
            receiver_username = context.args[1].replace('@', '')
        except:
            await update.message.reply_text("Неверный формат суммы")
            return
    
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной")
        return
    
    if user_data['balance'] < amount:
        await update.message.reply_text("Недостаточно средств")
        return
    
    # Если не получили receiver_id из ответа, ищем по username
    if not update.message.reply_to_message:
        receiver_id = None
        for uid, data in db.data.items():
            if data.get('username', '').lower() == receiver_username.lower():
                receiver_id = uid
                break
        
        if not receiver_id:
            if receiver_username.isdigit():
                receiver_id = receiver_username
            else:
                await update.message.reply_text("Пользователь не найден")
                return
    
    user_data['balance'] -= amount
    receiver_data = db.get_user(int(receiver_id))
    receiver_data['balance'] += amount
    
    db.update_user(user.id, user_data)
    db.update_user(int(receiver_id), receiver_data)
    
    await update.message.reply_text(
        f"✅ Вы перевели {format_number(amount)} mCoin пользователю @{receiver_username}\n"
        f"💰 Ваш новый баланс: {format_number(user_data['balance'])} mCoin"
    )

async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /promo [код]")
        return
    
    code = context.args[0].upper()
    amount = db.use_promocode(code, user.id)
    
    if amount > 0:
        user_data['balance'] += amount
        db.update_user(user.id, user_data)
        
        await update.message.reply_text(
            f"🎉 Промокод активирован!\n"
            f"💰 Вы получили: {format_number(amount)} mCoin\n"
            f"💰 Теперь ваш баланс: {format_number(user_data['balance'])} mCoin"
        )
    else:
        await update.message.reply_text("❌ Неверный или уже использованный промокод")

# Игра в мины
async def mines_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /mines [ставка] [количество мин]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
        mines_count = int(context.args[1])
    except:
        await update.message.reply_text("Неверный формат ставки или количества мин")
        return
    
    if mines_count < 1 or mines_count > 6:
        await update.message.reply_text("Количество мин должно быть от 1 до 6")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    field = [['❓' for _ in range(5)] for _ in range(5)]
    mines_positions = []
    
    while len(mines_positions) < mines_count:
        pos = (random.randint(0, 4), random.randint(0, 4))
        if pos not in mines_positions:
            mines_positions.append(pos)
    
    game_data = {
        'type': 'mines',
        'bet': bet,
        'mines_count': mines_count,
        'mines_positions': mines_positions,
        'opened_cells': [],
        'base_multiplier': MINE_MULTIPLIERS[mines_count],
        'current_multiplier': 1.0
    }
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    keyboard = []
    for i in range(5):
        row = []
        for j in range(5):
            row.append(InlineKeyboardButton(field[i][j], callback_data=f"mines_{i}_{j}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="mines_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💣 Игра в мины\n"
        f"💰 Ставка: {format_number(bet)} mCoin\n"
        f"💣 Количество мин: {mines_count}\n"
        f"🎯 Множитель за клетку: {game_data['base_multiplier']}x\n"
        f"💰 Текущий множитель: {game_data['current_multiplier']:.2f}x\n"
        f"💰 Можно забрать: {format_number(int(bet * game_data['current_multiplier']))} mCoin\n\n"
        f"Выберите клетку:",
        reply_markup=reply_markup
    )

async def mines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_data = db.get_user(user.id)
    
    if not user_data.get('active_game') or user_data['active_game'].get('type') != 'mines':
        await query.answer("У вас нет активной игры")
        return
    
    game_data = user_data['active_game']
    
    if query.data == "mines_cancel":
        user_data['balance'] += game_data['bet']
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        await query.edit_message_text("❌ Игра отменена. Ставка возвращена.")
        return
    
    if query.data == "mines_cashout":
        win_amount = int(game_data['bet'] * game_data['current_multiplier'])
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        
        # Показываем все мины
        field = [['❓' for _ in range(5)] for _ in range(5)]
        
        for i, j in game_data['mines_positions']:
            field[i][j] = '💣'
        
        for i, j in game_data['opened_cells']:
            if (i, j) not in game_data['mines_positions']:
                field[i][j] = '💎'
        
        field_text = "\n".join(["".join(row) for row in field])
        
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        await query.edit_message_text(
            f"🎉 Вы забрали выигрыш!\n"
            f"💰 Выигрыш: {format_number(win_amount)} mCoin\n\n"
            f"{field_text}\n\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
        return
    
    parts = query.data.split('_')
    i, j = int(parts[1]), int(parts[2])
    
    if (i, j) in game_data['opened_cells']:
        await query.answer("Эта клетка уже открыта")
        return
    
    if (i, j) in game_data['mines_positions']:
        user_data['balance'] -= game_data['bet']
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += game_data['bet']
        
        # Показываем все мины
        field = [['❓' for _ in range(5)] for _ in range(5)]
        
        for x, y in game_data['mines_positions']:
            field[x][y] = '💣'
        
        for x, y in game_data['opened_cells']:
            if (x, y) not in game_data['mines_positions']:
                field[x][y] = '💎'
        
        field[i][j] = '💥'
        
        field_text = "\n".join(["".join(row) for row in field])
        
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        await query.edit_message_text(
            f"💥 Вы попали на мину!\n"
            f"💣 Проигрыш: {format_number(game_data['bet'])} mCoin\n\n"
            f"{field_text}\n\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
        return
    
    # Обновляем множитель
    game_data['current_multiplier'] *= game_data['base_multiplier']
    game_data['opened_cells'].append((i, j))
    opened_count = len(game_data['opened_cells'])
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    field = [['❓' for _ in range(5)] for _ in range(5)]
    
    for x, y in game_data['opened_cells']:
        field[x][y] = '💎'
    
    keyboard = []
    for x in range(5):
        row = []
        for y in range(5):
            if (x, y) in game_data['opened_cells']:
                row.append(InlineKeyboardButton(field[x][y], callback_data=f"mines_{x}_{y}"))
            else:
                row.append(InlineKeyboardButton(field[x][y], callback_data=f"mines_{x}_{y}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("💵 Забрать выигрыш", callback_data="mines_cashout")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    win_amount = int(game_data['bet'] * game_data['current_multiplier'])
    
    await query.edit_message_text(
        f"💣 Игра в мины\n"
        f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n"
        f"💣 Количество мин: {game_data['mines_count']}\n"
        f"🎯 Множитель за клетку: {game_data['base_multiplier']}x\n"
        f"📈 Открыто клеток: {opened_count}\n"
        f"💰 Текущий множитель: {game_data['current_multiplier']:.2f}x\n"
        f"💰 Можно забрать: {format_number(win_amount)} mCoin\n\n"
        f"Выберите клетку:",
        reply_markup=reply_markup
    )
    
    await query.answer()

# Игра в золото
async def gold_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /gold [ставка]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
    except:
        await update.message.reply_text("Неверный формат ставки")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    # Создаем игровое поле
    cells = ['❓'] * 24  # 12 пар ячеек
    mine_positions = [random.randint(0, 1) for _ in range(12)]  # 0 - лево, 1 - право
    
    game_data = {
        'type': 'gold',
        'bet': bet,
        'cells': cells,
        'mine_positions': mine_positions,
        'multipliers': GOLD_MULTIPLIERS,
        'current_level': 0
    }
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    gold_text = (
        f"🤑 {user.full_name}, игра Золото Запада\n"
        "·····················\n"
        f"💰 Ставка: {format_number(bet)} mCoin\n"
        f"⚡️ Сл. Ячейка: {game_data['multipliers'][0]}x / {format_number(int(bet * game_data['multipliers'][0]))} mCoin\n\n"
    )
    
    for i in range(12):
        left_idx = i * 2
        right_idx = i * 2 + 1
        gold_text += f"| {cells[left_idx]} | {cells[right_idx]} | {format_number(int(bet * game_data['multipliers'][i]))} mCoin ({game_data['multipliers'][i]}x)\n"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Лево", callback_data="gold_left"),
         InlineKeyboardButton("➡️ Право", callback_data="gold_right")],
        [InlineKeyboardButton("❌ Отменить", callback_data="gold_cancel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(gold_text, reply_markup=reply_markup)

async def gold_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_data = db.get_user(user.id)
    
    if not user_data.get('active_game') or user_data['active_game'].get('type') != 'gold':
        await query.answer("У вас нет активной игры")
        return
    
    game_data = user_data['active_game']
    
    if query.data == "gold_cancel":
        user_data['balance'] += game_data['bet']
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        await query.edit_message_text("❌ Игра отменена. Ставка возвращена.")
        return
    
    if query.data == "gold_cashout":
        if game_data['current_level'] > 0:
            win_amount = int(game_data['bet'] * game_data['multipliers'][game_data['current_level'] - 1])
        else:
            win_amount = game_data['bet']
            
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        # Показываем все открытые ячейки
        for i in range(game_data['current_level']):
            left_idx = i * 2
            right_idx = i * 2 + 1
            game_data['cells'][left_idx] = '💰'
            game_data['cells'][right_idx] = '💰'
        
        gold_text = f"🎉 Вы забрали выигрыш!\n💰 Выигрыш: {format_number(win_amount)} mCoin\n💰 Новый баланс: {format_number(user_data['balance'])} mCoin\n\n"
        gold_text += f"🤑 {user.full_name}, игра Золото Запада\n·····················\n💰 Ставка: {format_number(game_data['bet'])} mCoin\n⚡️ Результат: Победа! +{format_number(win_amount)} mCoin\n\n"
        
        for i in range(12):
            left_idx = i * 2
            right_idx = i * 2 + 1
            gold_text += f"| {game_data['cells'][left_idx]} | {game_data['cells'][right_idx]} | {format_number(int(game_data['bet'] * game_data['multipliers'][i]))} mCoin ({game_data['multipliers'][i]}x)\n"
        
        await query.edit_message_text(gold_text)
        return
    
    # Обработка выбора лево/право
    current_level = game_data['current_level']
    is_left = query.data == "gold_left"
    
    # Проверяем, попал ли игрок на мину
    mine_position = game_data['mine_positions'][current_level]
    is_mine = (is_left and mine_position == 0) or (not is_left and mine_position == 1)
    
    if is_mine:
        # Игрок нашел взрывающуюся мину
        user_data['balance'] -= game_data['bet']
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += game_data['bet']
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        # Показываем все ячейки с минами
        for i in range(12):
            left_idx = i * 2
            right_idx = i * 2 + 1
            
            if game_data['mine_positions'][i] == 0:
                game_data['cells'][left_idx] = '🧨'  # Мина
                game_data['cells'][right_idx] = '💸'
            else:
                game_data['cells'][left_idx] = '💸'
                game_data['cells'][right_idx] = '🧨'  # Мина
        
        # Помечаем текущий выбор как взорвавшуюся мину
        if is_left:
            game_data['cells'][current_level * 2] = '💥'  # Взрывающаяся мина
        else:
            game_data['cells'][current_level * 2 + 1] = '💥'  # Взрывающаяся мина
        
        gold_text = f"💥 Вы нашли взрывающуюся мину!\n💸 Проигрыш: {format_number(game_data['bet'])} mCoin\n💰 Новый баланс: {format_number(user_data['balance'])} mCoin\n\n"
        gold_text += f"🤑 {user.full_name}, игра Золото Запада\n·····················\n💰 Ставка: {format_number(game_data['bet'])} mCoin\n⚡️ Результат: Мина! Проигрыш\n\n"
        
        for i in range(12):
            left_idx = i * 2
            right_idx = i * 2 + 1
            gold_text += f"| {game_data['cells'][left_idx]} | {game_data['cells'][right_idx]} | {format_number(int(game_data['bet'] * game_data['multipliers'][i]))} mCoin ({game_data['multipliers'][i]}x)\n"
        
        await query.edit_message_text(gold_text)
        return
    else:
        # Игрок нашел золото
        if is_left:
            game_data['cells'][current_level * 2] = '💰'
        else:
            game_data['cells'][current_level * 2 + 1] = '💰'
        
        game_data['current_level'] += 1
        
        # Проверяем, не достигли ли мы конца
        if game_data['current_level'] >= len(game_data['multipliers']):
            # Дошли до конца - автоматически забираем выигрыш
            win_amount = int(game_data['bet'] * game_data['multipliers'][-1])
            user_data['balance'] += win_amount
            user_data['games_played'] += 1
            user_data['wins'] += 1
            user_data['won_amount'] += win_amount
            user_data['active_game'] = None
            db.update_user(user.id, user_data)
            
            # Показываем все ячейки с золотом
            for i in range(24):
                game_data['cells'][i] = '💰'
            
            gold_text = f"🎉 Поздравляем! Вы прошли всю игру!\n💰 Выигрыш: {format_number(win_amount)} mCoin\n💰 Новый баланс: {format_number(user_data['balance'])} mCoin\n\n"
            gold_text += f"🤑 {user.full_name}, игра Золото Запада\n·····················\n💰 Ставка: {format_number(game_data['bet'])} mCoin\n⚡️ Результат: Победа! +{format_number(win_amount)} mCoin\n\n"
            
            for i in range(12):
                left_idx = i * 2
                right_idx = i * 2 + 1
                gold_text += f"| {game_data['cells'][left_idx]} | {game_data['cells'][right_idx]} | {format_number(int(game_data['bet'] * game_data['multipliers'][i]))} mCoin ({game_data['multipliers'][i]}x)\n"
            
            await query.edit_message_text(gold_text)
            return
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    # Формируем текст с ячейками
    gold_text = (
        f"🤑 {user.full_name}, игра Золото Запада\n"
        "·····················\n"
        f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n"
        f"⚡️ Сл. Ячейка: {game_data['multipliers'][game_data['current_level']]}x / {format_number(int(game_data['bet'] * game_data['multipliers'][game_data['current_level']]))} mCoin\n\n"
    )
    
    for i in range(12):
        left_idx = i * 2
        right_idx = i * 2 + 1
        gold_text += f"| {game_data['cells'][left_idx]} | {game_data['cells'][right_idx]} | {format_number(int(game_data['bet'] * game_data['multipliers'][i]))} mCoin ({game_data['multipliers'][i]}x)\n"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Лево", callback_data="gold_left"),
         InlineKeyboardButton("➡️ Право", callback_data="gold_right")],
        [InlineKeyboardButton("💵 Забрать выигрыш", callback_data="gold_cashout")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(gold_text, reply_markup=reply_markup)
    await query.answer()

# Игра в футбол
async def football_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /football [ставка]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
    except:
        await update.message.reply_text("Неверный формат ставки")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    # Создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton("Гол (x1.6)", callback_data="football_goal"),
         InlineKeyboardButton("Мимо (x2.25)", callback_data="football_miss")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение о начале игры
    await update.message.reply_text(
        f"⚽️ Футбол · выбери исход!\n"
        f"·····················\n"
        f"💸 Ставка: {format_number(bet)} coin",
        reply_markup=reply_markup
    )
    
    # Сохраняем данные игры
    game_data = {
        'type': 'football',
        'bet': bet
    }
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)

async def football_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_data = db.get_user(user.id)
    
    if not user_data.get('active_game') or user_data['active_game'].get('type') != 'football':
        await query.answer("У вас нет активной игры")
        return
    
    game_data = user_data['active_game']
    bet = game_data['bet']
    
    # Определяем результат
    is_goal = query.data == "football_goal"
    is_win = random.random() < 0.6 if is_goal else random.random() < 0.4
    
    # Отправляем анимацию
    animation_msg = await query.message.reply_text("⚽️")
    await asyncio.sleep(8)  # Увеличиваем задержку до 8 секунд
    
    if is_win:
        multiplier = 1.6 if is_goal else 2.25
        win_amount = int(bet * multiplier)
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        
        result_text = (
            f"{user.full_name}\n"
            f"🔥 Футбол · Победа!\n"
            f"·····················\n"
            f"💸 Ставка: {format_number(bet)} coin\n"
            f"🎲 Выбрано: {'гол' if is_goal else 'мимо'}\n"
            f"💰 Выигрыш: x{multiplier} / {format_number(win_amount)}"
        )
    else:
        user_data['balance'] -= bet
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += bet
        
        result_text = (
            f"{user.full_name}\n"
            f"⚽️ Футбол · Поражение!\n"
            f"·····················\n"
            f"💸 Ставка: {format_number(bet)} coin\n"
            f"🎲 Выбрано: {'гол' if is_goal else 'мимо'}\n"
            f"💸 Проигрыш: {format_number(bet)}"
        )
    
    user_data['active_game'] = None
    db.update_user(user.id, user_data)
    
    # Удаляем анимацию
    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=animation_msg.message_id)
    
    await query.edit_message_text(result_text)

# Игра в баскетбол
async def basketball_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /basketball [ставка]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
    except:
        await update.message.reply_text("Неверный формат ставки")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    # Создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton("Гол (x2.25)", callback_data="basketball_goal"),
         InlineKeyboardButton("Мимо (x1.6)", callback_data="basketball_miss")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение о начале игры
    await update.message.reply_text(
        f"🏀 Баскетбол · выбери исход!\n"
        f"·····················\n"
        f"💸 Ставка: {format_number(bet)} coin",
        reply_markup=reply_markup
    )
    
    # Сохраняем данные игры
    game_data = {
        'type': 'basketball',
        'bet': bet
    }
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)

async def basketball_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_data = db.get_user(user.id)
    
    if not user_data.get('active_game') or user_data['active_game'].get('type') != 'basketball':
        await query.answer("У вас нет активной игры")
        return
    
    game_data = user_data['active_game']
    bet = game_data['bet']
    
    # Определяем результат
    is_goal = query.data == "basketball_goal"
    is_win = random.random() < 0.45 if is_goal else random.random() < 0.55
    
    # Отправляем анимацию
    animation_msg = await query.message.reply_text("🏀")
    await asyncio.sleep(8)  # Увеличиваем задержку до 8 секунд
    
    if is_win:
        multiplier = 2.25 if is_goal else 1.6
        win_amount = int(bet * multiplier)
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        
        result_text = (
            f"{user.full_name}\n"
            f"🔥 Баскетбол · Победа!\n"
            f"·····················\n"
            f"💸 Ставка: {format_number(bet)} coin\n"
            f"🎲 Выбрано: {'гол' if is_goal else 'мимо'}\n"
            f"💰 Выигрыш: x{multiplier} / {format_number(win_amount)}"
        )
    else:
        user_data['balance'] -= bet
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += bet
        
        result_text = (
            f"{user.full_name}\n"
            f"🏀 Баскетбол · Поражение!\n"
            f"·····················\n"
            f"💸 Ставка: {format_number(bet)} coin\n"
            f"🎲 Выбрано: {'гол' if is_goal else 'мимо'}\n"
            f"💸 Проигрыш: {format_number(bet)}"
        )
    
    user_data['active_game'] = None
    db.update_user(user.id, user_data)
    
    # Удаляем анимацию
    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=animation_msg.message_id)
    
    await query.edit_message_text(result_text)

# Игра в рулетку
async def roulette_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /roulette [ставка] [цвет/число]\nЦвет: к (красный) или ч (черный)\nЧисло: от 0 до 36")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
        choice = context.args[1].lower()
    except:
        await update.message.reply_text("Неверный формат ставки или выбора")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    if choice in ['к', 'красный']:
        bet_type = 'red'
        multiplier = 2
    elif choice in ['ч', 'черный']:
        bet_type = 'black'
        multiplier = 2
    elif choice.isdigit() and 0 <= int(choice) <= 36:
        bet_type = 'number'
        choice_number = int(choice)
        multiplier = 36
    else:
        await update.message.reply_text("Неверный тип ставки. Используйте: к (красный), ч (черный) или число от 0 до 36")
        return
    
    result_number = random.randint(0, 36)
    
    red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    if result_number == 0:
        result_color = 'green'
    elif result_number in red_numbers:
        result_color = 'red'
    else:
        result_color = 'black'
    
    if bet_type == 'number':
        is_win = (choice_number == result_number)
    else:
        is_win = (bet_type == result_color)
    
    message = await update.message.reply_text("🎰 Крутим рулетку...")
    
    for _ in range(5):
        random_num = random.randint(0, 36)
        random_color = 'green' if random_num == 0 else 'red' if random_num in red_numbers else 'black'
        color_emoji = '🟢' if random_color == 'green' else '🔴' if random_color == 'red' else '⚫️'
        await message.edit_text(f"🎰 Рулетка крутится...\n\nВыпало: {random_num} {color_emoji}")
        await asyncio.sleep(0.5)
    
    result_color_emoji = '🟢' if result_color == 'green' else '🔴' if result_color == 'red' else '⚫️'
    
    if is_win:
        win_amount = int(bet * multiplier)
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        
        result_text = (
            f"🎰 Рулетка\n\n"
            f"Ставка: {format_number(bet)} mCoin\n"
            f"Ваш выбор: {choice}\n"
            f"Выпало: {result_number} {result_color_emoji}\n\n"
            f"Итог: победа! 🎉\n\n"
            f"💰 Выигрыш: {format_number(win_amount)} mCoin\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
    else:
        user_data['balance'] -= bet
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += bet
        
        result_text = (
            f"🎰 Руletка\n\n"
            f"Ставка: {format_number(bet)} mCoin\n"
            f"Ваш выбор: {choice}\n"
            f"Выпало: {result_number} {result_color_emoji}\n\n"
            f"Итог: проигрыш 😕\n\n"
            f"💸 Проигрыш: {format_number(bet)} mCoin\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
    
    db.update_user(user.id, user_data)
    await message.edit_text(result_text)

# Игра 21 (двадцать одно)
async def twentyone_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /21 [ставка]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
    except:
        await update.message.reply_text("Неверный формат ставки")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    suits = ['♠️', '♥️', '♦️', '♣️']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
    random.shuffle(deck)
    
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]
    
    game_data = {
        'type': 'twentyone',
        'bet': bet,
        'deck': deck,
        'player_cards': player_cards,
        'dealer_cards': dealer_cards,
        'player_score': calculate_score(player_cards),
        'dealer_score': calculate_score([dealer_cards[0]]),
    }
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    keyboard = [
        [InlineKeyboardButton("➕ Еще карту", callback_data="twentyone_hit"),
         InlineKeyboardButton("✋ Хватит", callback_data="twentyone_stand")],
        [InlineKeyboardButton("❌ Отменить", callback_data="twentyone_cancel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    game_text = (
        f"🃏 Игра 21\n\n"
        f"💰 Ставка: {format_number(bet)} mCoin\n\n"
        f"Ваши карты: {' '.join(player_cards)}\n"
        f"Ваш счет: {game_data['player_score']}\n\n"
        f"Карты дилера: {dealer_cards[0]} ❓\n"
        f"Счет дилера: {game_data['dealer_score']}\n\n"
        f"Выберите действие:"
    )
    
    await update.message.reply_text(game_text, reply_markup=reply_markup)

def calculate_score(cards):
    score = 0
    aces = 0
    
    for card in cards:
        rank = card[:-2]
        if rank in ['J', 'Q', 'K']:
            score += 10
        elif rank == 'A':
            aces += 1
            score += 11
        else:
            score += int(rank)
    
    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    
    return score

async def twentyone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_data = db.get_user(user.id)
    
    if not user_data.get('active_game') or user_data['active_game'].get('type') != 'twentyone':
        await query.answer("У вас нет активной игры")
        return
    
    game_data = user_data['active_game']
    
    if query.data == "twentyone_cancel":
        user_data['balance'] += game_data['bet']
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        await query.edit_message_text("❌ Игра отменена. Ставка возвращена.")
        return
    
    if query.data == "twentyone_hit":
        game_data['player_cards'].append(game_data['deck'].pop())
        game_data['player_score'] = calculate_score(game_data['player_cards'])
        
        if game_data['player_score'] > 21:
            user_data['balance'] -= game_data['bet']
            user_data['games_played'] += 1
            user_data['losses'] += 1
            user_data['lost_amount'] += game_data['bet']
            user_data['active_game'] = None
            db.update_user(user.id, user_data)
            
            game_data['dealer_score'] = calculate_score(game_data['dealer_cards'])
            
            result_text = (
                f"🃏 Игра 21\n\n"
                f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n\n"
                f"Ваши карты: {' '.join(game_data['player_cards'])}\n"
                f"Ваш счет: {game_data['player_score']} (Перебор!)\n\n"
                f"Карты дилера: {' '.join(game_data['dealer_cards'])}\n"
                f"Счет дилера: {game_data['dealer_score']}\n\n"
                f"💸 Проигрыш: {format_number(game_data['bet'])} mCoin\n"
                f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
            )
            
            await query.edit_message_text(result_text)
            return
    
    if query.data == "twentyone_stand" or game_data['player_score'] == 21:
        game_data['dealer_score'] = calculate_score(game_data['dealer_cards'])
        
        while game_data['dealer_score'] < 17:
            game_data['dealer_cards'].append(game_data['deck'].pop())
            game_data['dealer_score'] = calculate_score(game_data['dealer_cards'])
        
        if game_data['dealer_score'] > 21 or game_data['player_score'] > game_data['dealer_score']:
            win_amount = int(game_data['bet'] * 2)
            user_data['balance'] += win_amount
            user_data['games_played'] += 1
            user_data['wins'] += 1
            user_data['won_amount'] += win_amount
            
            result_text = (
                f"🃏 Игра 21\n\n"
                f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n\n"
                f"Ваши карты: {' '.join(game_data['player_cards'])}\n"
                f"Ваш счет: {game_data['player_score']}\n\n"
                f"Карты дилера: {' '.join(game_data['dealer_cards'])}\n"
                f"Счет дилера: {game_data['dealer_score']}\n\n"
                f"🎉 Победа!\n\n"
                f"💰 Выигрыш: {format_number(win_amount)} mCoin\n"
                f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
            )
        elif game_data['player_score'] < game_data['dealer_score']:
            user_data['balance'] -= game_data['bet']
            user_data['games_played'] += 1
            user_data['losses'] += 1
            user_data['lost_amount'] += game_data['bet']
            
            result_text = (
                f"🃏 Игра 21\n\n"
                f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n\n"
                f"Ваши карты: {' '.join(game_data['player_cards'])}\n"
                f"Ваш счет: {game_data['player_score']}\n\n"
                f"Карты дилера: {' '.join(game_data['dealer_cards'])}\n"
                f"Счет дилера: {game_data['dealer_score']}\n\n"
                f"💸 Проигрыш: {format_number(game_data['bet'])} mCoin\n"
                f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
            )
        else:
            user_data['games_played'] += 1
            
            result_text = (
                f"🃏 Игра 21\n\n"
                f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n\n"
                f"Ваши карты: {' '.join(game_data['player_cards'])}\n"
                f"Ваш счет: {game_data['player_score']}\n\n"
                f"Карты дилера: {' '.join(game_data['dealer_cards'])}\n"
                f"Счет дилера: {game_data['dealer_score']}\n\n"
                f"🤝 Ничья! Ставка возвращена\n"
                f"💰 Баланс: {format_number(user_data['balance'])} mCoin"
            )
        
        user_data['active_game'] = None
        db.update_user(user.id, user_data)
        
        await query.edit_message_text(result_text)
        return
    
    user_data['active_game'] = game_data
    db.update_user(user.id, user_data)
    
    keyboard = [
        [InlineKeyboardButton("➕ Еще карту", callback_data="twentyone_hit"),
         InlineKeyboardButton("✋ Хватит", callback_data="twentyone_stand")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    game_text = (
        f"🃏 Игра 21\n\n"
        f"💰 Ставка: {format_number(game_data['bet'])} mCoin\n\n"
        f"Ваши карты: {' '.join(game_data['player_cards'])}\n"
        f"Ваш счет: {game_data['player_score']}\n\n"
        f"Карты дилера: {game_data['dealer_cards'][0]} ❓\n"
        f"Счет дилера: {calculate_score([game_data['dealer_cards'][0]])}\n\n"
        f"Выберите действие:"
    )
    
    await query.edit_message_text(game_text, reply_markup=reply_markup)
    await query.answer()

# Игра в кости с анимацией
async def cubes_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data.get('banned', False):
        await update.message.reply_text("Вы забанены и не можете играть")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /cubes [ставка] [число от 1 до 6]")
        return
    
    try:
        bet = parse_bet(context.args[0], user_data['balance'])
        number = int(context.args[1])
    except:
        await update.message.reply_text("Неверный формат ставки или числа")
        return
    
    if number < 1 or number > 6:
        await update.message.reply_text("Число должно быть от 1 до 6")
        return
    
    if bet <= 0:
        await update.message.reply_text("Ставка должна быть положительной")
        return
    
    if user_data['balance'] < bet:
        await update.message.reply_text("Недостаточно средств")
        return
    
    # Отправляем анимацию
    animation_msg = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(5)  # Ждем завершения анимации
    
    # Получаем результат
    result = animation_msg.dice.value
    
    if result == number:
        win_amount = int(bet * 6)
        user_data['balance'] += win_amount
        user_data['games_played'] += 1
        user_data['wins'] += 1
        user_data['won_amount'] += win_amount
        
        result_text = (
            f"🎲 Кости\n\n"
            f"Ставка: {format_number(bet)} mCoin\n"
            f"Выбрано: {number}\n"
            f"Выпало: {result}\n\n"
            f"Итог: победа! 🎉\n\n"
            f"💰 Выигрыш: {format_number(win_amount)} mCoin\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
    else:
        user_data['balance'] -= bet
        user_data['games_played'] += 1
        user_data['losses'] += 1
        user_data['lost_amount'] += bet
        
        result_text = (
            f"🎲 Кости\n\n"
            f"Ставка: {format_number(bet)} mCoin\n"
            f"Выбрано: {number}\n"
            f"Выпало: {result}\n\n"
            f"Итог: проигрыш 😕\n\n"
            f"💸 Проигрыш: {format_number(bet)} mCoin\n"
            f"💰 Новый баланс: {format_number(user_data['balance'])} mCoin"
        )
    
    db.update_user(user.id, user_data)
    
    await update.message.reply_text(result_text)

# Административные команды
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем, является ли пользователь уже администратором
    user_data = db.get_user(user.id)
    if user_data.get('is_admin', False):
        # Показываем панель администратора
        keyboard = [
            [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
            [InlineKeyboardButton("💸 Забрать деньги", callback_data="admin_take")],
            [InlineKeyboardButton("🔨 Забанить", callback_data="admin_ban")],
            [InlineKeyboardButton("🔓 Разбанить", callback_data="admin_unban")],
            [InlineKeyboardButton("🎫 Создать промокод", callback_data="admin_promo")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛠 Панель администратора\n\nВыберите действие:",
            reply_markup=reply_markup
        )
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /apanel [пароль]")
        return
    
    if context.args[0] != ADMIN_PASSWORD:
        await update.message.reply_text("Неверный пароль")
        return
    
    # Добавляем пользователя в администраторы
    if user.id not in ADMIN_IDS:
        ADMIN_IDS.append(user.id)
    
    user_data['is_admin'] = True
    user_data['status'] = "Администратор"
    db.update_user(user.id, user_data)
    
    keyboard = [
        [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
        [InlineKeyboardButton("💸 Забрать деньги", callback_data="admin_take")],
        [InlineKeyboardButton("🔨 Забанить", callback_data="admin_ban")],
        [InlineKeyboardButton("🔓 Разбанить", callback_data="admin_unban")],
        [InlineKeyboardButton("🎫 Создать промокод", callback_data="admin_promo")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛠 Панель администратора\n\nВыберите действие:",
        reply_markup=reply_markup
    )

async def give_money_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /givemod [сумма] [@username или ID]")
        return
    
    try:
        amount = parse_bet(context.args[0])
        receiver_username = context.args[1].replace('@', '')
    except:
        await update.message.reply_text("Неверный формат суммы")
        return
    
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной")
        return

    # Поиск пользователя по username
    receiver_id = None
    for uid, data in db.data.items():
        if data.get('username', '').lower() == receiver_username.lower():
            receiver_id = uid
            break

    if not receiver_id:
        # Проверяем, если передан ID пользователя
        if receiver_username.isdigit():
            receiver_id = receiver_username
        else:
            await update.message.reply_text("Пользователь не найден")
            return

    # Выдаем деньги
    receiver_data = db.get_user(int(receiver_id))
    receiver_data['balance'] += amount

    db.update_user(int(receiver_id), receiver_data)

    await update.message.reply_text(
        f"✅ Вы выдали {format_number(amount)} mCoin пользователю @{receiver_username}\n"
        f"💰 Его новый баланс: {format_number(receiver_data['balance'])} mCoin"
    )

async def take_money_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /nogive [сумма] [@username или ID]")
        return

    try:
        amount = parse_bet(context.args[0])
        receiver_username = context.args[1].replace('@', '')
    except:
        await update.message.reply_text("Неверный формат суммы")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной")
        return

    # Поиск пользователя по username
    receiver_id = None
    for uid, data in db.data.items():
        if data.get('username', '').lower() == receiver_username.lower():
            receiver_id = uid
            break

    if not receiver_id:
        # Проверяем, если передан ID пользователя
        if receiver_username.isdigit():
            receiver_id = receiver_username
        else:
            await update.message.reply_text("Пользователь не найден")
            return

    # Забираем деньги
    receiver_data = db.get_user(int(receiver_id))

    if receiver_data['balance'] < amount:
        amount = receiver_data['balance']

    receiver_data['balance'] -= amount

    db.update_user(int(receiver_id), receiver_data)

    await update.message.reply_text(
        f"✅ Вы забрали {format_number(amount)} mCoin у пользователя @{receiver_username}\n"
        f"💰 Его новый баланс: {format_number(receiver_data['balance'])} mCoin"
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Использование: /bat [@username или ID]")
        return

    receiver_username = context.args[0].replace('@', '')

    # Поиск пользователя по username
    receiver_id = None
    for uid, data in db.data.items():
        if data.get('username', '').lower() == receiver_username.lower():
            receiver_id = uid
            break

    if not receiver_id:
        # Проверяем, если передан ID пользователя
        if receiver_username.isdigit():
            receiver_id = receiver_username
        else:
            await update.message.reply_text("Пользователь не найден")
            return

    # Баним пользователя
    receiver_data = db.get_user(int(receiver_id))
    receiver_data['banned'] = True

    db.update_user(int(receiver_id), receiver_data)

    await update.message.reply_text(
        f"✅ Пользователь @{receiver_username} забанен"
    )

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Использование: /unban [@username или ID]")
        return

    receiver_username = context.args[0].replace('@', '')

    # Поиск пользователя по username
    receiver_id = None
    for uid, data in db.data.items():
        if data.get('username', '').lower() == receiver_username.lower():
            receiver_id = uid
            break

    if not receiver_id:
        # Проверяем, если передан ID пользователя
        if receiver_username.isdigit():
            receiver_id = receiver_username
        else:
            await update.message.reply_text("Пользователь не найден")
        return

    # Разбаниваем пользователя
    receiver_data = db.get_user(int(receiver_id))
    receiver_data['banned'] = False

    db.update_user(int(receiver_id), receiver_data)

    await update.message.reply_text(
        f"✅ Пользователь @{receiver_username} разбанен"
    )

async def create_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /promomod [промокод] [сумма] [использования=1]")
        return

    code = context.args[0].upper()

    try:
        amount = parse_bet(context.args[1])
        uses = int(context.args[2]) if len(context.args) > 2 else 1
    except:
        await update.message.reply_text("Неверный формат суммы или количества использований")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной")
        return

    # Создаем промокод
    db.add_promocode(code, amount, uses)

    await update.message.reply_text(
        f"✅ Промокод {code} создан\n"
        f"💰 Сумма: {format_number(amount)} mCoin\n"
        f"🔢 Количество использований: {uses}"
    )

# Основная функция
def main():
    # Создаем приложение и передаем ему токен бота
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler(["balance", "b"], balance))
    application.add_handler(CommandHandler("bonus", bonus))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("give", give_money))
    application.add_handler(CommandHandler("promo", promo_command))
    application.add_handler(CommandHandler("mines", mines_game))
    application.add_handler(CommandHandler("gold", gold_game))
    application.add_handler(CommandHandler("football", football_game))
    application.add_handler(CommandHandler("basketball", basketball_game))
    application.add_handler(CommandHandler("roulette", roulette_game))
    application.add_handler(CommandHandler("21", twentyone_game))
    application.add_handler(CommandHandler("cubes", cubes_game))

    # Добавляем обработчики административных команд
    application.add_handler(CommandHandler("apanel", admin_panel))
    application.add_handler(CommandHandler("givemod", give_money_admin))
    application.add_handler(CommandHandler("nogive", take_money_admin))
    application.add_handler(CommandHandler("bat", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("promomod", create_promocode))

    # Добавляем обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(mines_callback, pattern="^mines_"))
    application.add_handler(CallbackQueryHandler(gold_callback, pattern="^gold_"))
    application.add_handler(CallbackQueryHandler(football_callback, pattern="^football_"))
    application.add_handler(CallbackQueryHandler(basketball_callback, pattern="^basketball_"))
    application.add_handler(CallbackQueryHandler(twentyone_callback, pattern="^twentyone_"))

    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()