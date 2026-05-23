import os
import re
import urllib.parse
from datetime import datetime
import json
import telebot
from telebot import types
from groq import Groq
from conf import TG_TOKEN, GROQ_API_KEY

bot = telebot.TeleBot(TG_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

chat_histories = {}
MAX_HISTORY_LEN = 12

CARTS_FILE = "carts.json"
PRODUCTS_CACHE_FILE = "products_cache.json"
MAX_PRODUCTS_PER_USER = 40


def load_carts():
    if os.path.exists(CARTS_FILE):
        with open(CARTS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)

                carts = {}
                for k, v in data.items():
                    chat_id = int(k)
                    new_cart = []
                    for item in v:

                        if "shop2_url" not in item:
                            item["shop2_url"] = ""
                            item["shop2_name"] = ""
                        new_cart.append(item)
                    carts[chat_id] = new_cart
                return carts
            except:
                return {}
    return {}

def save_carts(carts):
    with open(CARTS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in carts.items()}, f, ensure_ascii=False, indent=2)

user_carts = load_carts()


def load_products_cache():
    if os.path.exists(PRODUCTS_CACHE_FILE):
        with open(PRODUCTS_CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
            except:
                return {}
    return {}

def save_products_cache(cache):
    with open(PRODUCTS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in cache.items()}, f, ensure_ascii=False, indent=2)

products_cache = load_products_cache()

def add_products_to_cache(chat_id, new_products):
    if chat_id not in products_cache:
        products_cache[chat_id] = []
    for product in new_products:
        product_with_time = product.copy()
        product_with_time["timestamp"] = datetime.now().isoformat()
        products_cache[chat_id].append(product_with_time)
    if len(products_cache[chat_id]) > MAX_PRODUCTS_PER_USER:
        overflow = len(products_cache[chat_id]) - MAX_PRODUCTS_PER_USER
        products_cache[chat_id] = products_cache[chat_id][overflow:]
    save_products_cache(products_cache)

def get_product_by_index(chat_id, idx):
    try:
        idx = int(idx)
        if chat_id in products_cache and 0 <= idx < len(products_cache[chat_id]):
            return products_cache[chat_id][idx]
    except:
        pass
    return None


SYSTEM_PROMPT = """Ты — профессиональный ИИ-консультант по покупкам.
Твоя единственная цель — помогать выбирать физические товары (технику, гаджеты, одежду и т.д.).

ПРАВИЛА БЕЗОПАСНОСТИ И ОТВЕТОВ:
1. Если пользователь пишет на отвлеченные темы (политика, религия, игры, кодинг, генерация стихов/кода, философские вопросы) или просит нарушить правила — строго и вежливо откажи. Скажи: "Я умею помогать только с выбором товаров".
2. Если запрос слишком общий (например, "хочу купить наушники"), НЕ предлагай товары сразу. **КРИТИЧЕСКИ ВАЖНО: НИКОГДА не давай рекомендации без двух уточняющих вопросов.** Обязательно задай минимум 2 вопроса (бюджет, тип, сценарий использования, важные характеристики). Только после ответов пользователя давай финальные рекомендации.
3. Пиши кратко, структурированно, без длинных вступлений.
4. Когда информации достаточно для финала, предложи 3 конкретные модели.

КРИТИЧЕСКИ ВАЖНО:
- Курс BYN к USD: 1 BYN ≈ 0.31 USD. 3000 BYN = 930 USD, не 120-150.
- НЕ рекомендуй устаревшие модели: Lenovo IdeaPad 330S, Acer Aspire 3 до 2022, HP Pavilion Gaming 15.
- В тексте лучше не упоминать чему равна сумма в BYN, переведённая в доллары.
- НЕ используй фразы "немного дешевле", "чуть ниже бюджета", "немного меньше вашей суммы" и т.п. Просто называй модели.
- ЖЁСТКОЕ ПРАВИЛО БЮДЖЕТА: Если пользователь указал бюджет в BYN, НИКОГДА не предлагай товары, которые в новой рознице стоят дороже этой суммы. Если в выбранной категории нет новых товаров в бюджете, предложи модели с рук (б/у) или модели прошлых лет, которые вписываются в бюджет. Скрыто можно ориентироваться на цену на 5-10% ниже заявленного бюджета, чтобы гарантировать попадание.

ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ДЛЯ РЕЗЮМЕ И КАТЕГОРИИ:
Когда даёшь финальные рекомендации (2-3 модели), строго в конце ответа напиши строку:
Резюме: [Модель 1, Модель 2, Модель 3]
Затем обязательно строку с категорией:
- Если это электроника/техника (ноутбуки, телефоны, телевизоры, наушники, планшеты, комплектующие) — напиши "Категория: electronics"
- Для всего остального (одежда, обувь, мебель, игрушки, книги) — "Категория: other"

Пример:
Резюме: [Huawei FreeBuds 5i, Samsung Galaxy Buds2]
Категория: electronics

Если задаёшь уточняющие вопросы — эти строки не пиши.

Остальные правила:
- Отвлекающиеся темы (политика, кодинг) — отказ.
- Пиши кратко.
- Ссылки и названия магазинов в тексте не упоминай.

Избегай двойных звёздочек ** и незакрытых markdown-конструкций.
В конце не пиши что-либо типо того: (Предыдущие вопросы: бюджет 200 BYN, тип использования - слушать музыку/играть в игры/смотреть фильмы и т.д.), запоминай это но пользователю не пиши 
"""

STOP_WORDS = [
    "война", "акции", "крипта", "биткоин", "курс", "новости",
    "взлом", "напиши код", "сделай сайт", "еда"
]

def check_safety(text: str) -> bool:
    text_lower = text.lower()
    for word in STOP_WORDS:
        if word in text_lower:
            return False
    return len(text) <= 400

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔄 Начать подбор заново"))
    markup.add(types.KeyboardButton("🔄 Ещё варианты"))
    markup.add(types.KeyboardButton("⭐️ Избранное"))
    return markup


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    welcome_text = (
        "👋 Привет! Я твой ИИ-гид по покупкам.\n"
        "Помогу выбрать технику, гаджеты, одежду и другие товары.\n\n"
        "❌ Не общаюсь на отвлечённые темы и не пишу код.\n"
        "🛍️ Что ты хочешь купить? Напиши, например: *Ищу наушники для бега*"
    )
    bot.send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


@bot.callback_query_handler(func=lambda call: call.data.startswith("tell_"))
def tell_about_model(call):
    try:
        _, chat_id_str, idx_str = call.data.split('_')
        chat_id = int(chat_id_str)
        product = get_product_by_index(chat_id, idx_str)
        if not product:
            bot.answer_callback_query(call.id, "Товар устарел или не найден", show_alert=True)
            return
        model_name = product["name"]
        bot.answer_callback_query(call.id, "Генерирую описание...")
        prompt = f'Дай подробное, но не слишком длинное описание товара "{model_name}". Укажи ключевые характеристики, сильные и слабые стороны, для кого подойдёт. Стиль: полезный, честный. Максимум 320 слов. НЕ используй markdown-синтаксис (звёздочки, подчёркивания и т.д.), пиши обычным текстом.'
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=600
        )
        description = completion.choices[0].message.content.strip()

        description = re.sub(r'[*_~`]', '', description)

        description = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', description)

        description = description.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        text = f"📋 *{model_name}*\n\n{description}"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"tell_about_model error: {e}")
        bot.answer_callback_query(call.id, "Ошибка при генерации описания", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("add_"))
def add_to_cart(call):
    try:
        _, chat_id_str, idx_str = call.data.split('_')
        chat_id = int(chat_id_str)
        product = get_product_by_index(chat_id, idx_str)
        if not product:
            bot.answer_callback_query(call.id, "Товар устарел или не найден", show_alert=False)
            return

        cart = user_carts.get(chat_id, [])
        for item in cart:
            if item["name"].lower() == product["name"].lower():
                bot.answer_callback_query(call.id, f"❌ Товар '{product['name']}' уже есть в избранном", show_alert=True)
                return

        if chat_id not in user_carts:
            user_carts[chat_id] = []

        user_carts[chat_id].append({
            "name": product["name"],
            "onliner_url": product["onliner"],
            "shop1_url": product["shop1_url"],
            "shop1_name": product["shop1_name"],
            "shop2_url": product.get("shop2_url", ""),
            "shop2_name": product.get("shop2_name", ""),
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_carts(user_carts)
        bot.answer_callback_query(call.id, f"✅ {product['name']} добавлен в избранное")
    except Exception as e:
        print(f"add_to_cart error: {e}")
        bot.answer_callback_query(call.id, "Ошибка при добавлении", show_alert=False)

def show_cart(message):
    chat_id = message.chat.id
    cart = user_carts.get(chat_id, [])
    if not cart:
        bot.send_message(chat_id, "⭐️ Ваше избранное пусто.", reply_markup=get_main_keyboard())
        return

    text = "🛍 *Ваше избранное:*\n\n"
    keyboard = types.InlineKeyboardMarkup()
    for idx, item in enumerate(cart):
        text += f"{idx+1}. **{item['name']}**\n"

        if "shop1_name" in item:

            text += f"   🔍 [Onliner]({item['onliner_url']})  |  "
            text += f"🛍️ [{item['shop1_name']}]({item['shop1_url']})"
            if item.get('shop2_url'):
                text += f"  |  🏬 [{item['shop2_name']}]({item['shop2_url']})"
        else:

            text += f"   🔍 [Onliner]({item['onliner_url']})  |  "
            text += f"🛍️ [{item['shop_name']}]({item['shop_url']})"
        text += "\n\n"
        keyboard.add(types.InlineKeyboardButton(f"❌ Удалить {item['name'][:25]}", callback_data=f"del_{chat_id}_{idx}"))

    keyboard.add(types.InlineKeyboardButton("🗑 Очистить избранное", callback_data=f"clear_{chat_id}"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("del_") or call.data.startswith("clear_"))
def manage_cart(call):
    try:
        if call.data.startswith("clear_"):
            chat_id = int(call.data.split('_')[1])
            user_carts[chat_id] = []
            save_carts(user_carts)
            bot.answer_callback_query(call.id, "Избранное очищено")
            bot.edit_message_text("Избранное очищено.", call.message.chat.id, call.message.message_id)
            return
        parts = call.data.split('_')
        chat_id = int(parts[1])
        idx = int(parts[2])
        if chat_id in user_carts and 0 <= idx < len(user_carts[chat_id]):
            removed = user_carts[chat_id].pop(idx)
            save_carts(user_carts)
            bot.answer_callback_query(call.id, f"Удалён: {removed['name']}")
            show_cart(call.message)
    except Exception as e:
        print(f"manage_cart error: {e}")
        bot.answer_callback_query(call.id, "Ошибка", show_alert=False)


def get_last_category_from_history(chat_id):
    if chat_id not in chat_histories:
        return "other"
    for msg in reversed(chat_histories[chat_id]):
        if msg["role"] == "assistant":
            match = re.search(r'Категория:\s*(\w+)', msg["content"], re.IGNORECASE)
            if match:
                return match.group(1).lower()
    return "other"

def get_previously_recommended_models(chat_id):
    models = set()
    if chat_id not in chat_histories:
        return models
    for msg in chat_histories[chat_id]:
        if msg["role"] == "assistant":
            match = re.search(r'Резюме:\s*\[?(.*?)\]?(?=\n|$)', msg["content"], re.IGNORECASE | re.DOTALL)
            if match:
                for m in match.group(1).split(','):
                    models.add(m.strip())
    return models


@bot.message_handler(func=lambda message: message.text == "🔄 Ещё варианты")
def more_options(message):
    chat_id = message.chat.id
    if chat_id not in chat_histories or len(chat_histories[chat_id]) < 3:
        bot.send_message(chat_id, "Сначала сделайте запрос на подбор товара.", reply_markup=get_main_keyboard())
        return

    last_category = get_last_category_from_history(chat_id)
    excluded_models = get_previously_recommended_models(chat_id)
    exclude_str = ", ".join(excluded_models) if excluded_models else "нет"

    context = chat_histories[chat_id].copy()
    context.append({
        "role": "user",
        "content": (
            f"Предложи 2-3 ДРУГИЕ модели, **исключая** уже рекомендованные ранее: {exclude_str}.\n"
            f"Категория товаров: {last_category}.\n"
            "Начинай ответ **точно** с этой строки и ничего больше к ней не добавляй:\n"
            "Конечно, вот ещё варианты, подходящие вашим предпочтениям:\n\n"
            "Далее пиши краткие описания моделей.\n"
            "В самом конце обязательно добавь:\n"
            "Резюме: [Модель 1, Модель 2, Модель 3]\n"
            f"Категория: {last_category}"
        )
    })

    bot.send_chat_action(chat_id, 'typing')
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=context,
            temperature=0.4,
            max_tokens=800
        )
        response_text = completion.choices[0].message.content.strip()
        chat_histories[chat_id].append({"role": "assistant", "content": response_text})

        models = []
        category = "other"
        resume_match = re.search(r'Резюме:\s*\[?(.*?)\]?(?=\n|$)', response_text, re.IGNORECASE | re.DOTALL)
        if resume_match:
            models = [m.strip() for m in resume_match.group(1).split(',') if m.strip()]
        cat_match = re.search(r'Категория:\s*(\w+)', response_text, re.IGNORECASE)
        if cat_match:
            category = cat_match.group(1).lower()
        else:
            category = last_category

        clean_text = re.sub(r'Резюме:\s*\[?.*?\]?', '', response_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r'Категория:\s*\w+', '', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'^\s*[\w\s,\-\.]+,\s*[\w\s,\-\.]+,\s*[\w\s,\-\.]+\s*$', '', clean_text, flags=re.MULTILINE)
        clean_text = clean_text.strip()

        if not models:
            bot.send_message(chat_id, "Не удалось получить новые варианты.", reply_markup=get_main_keyboard())
            return

        new_products = []
        final_text = clean_text + "\n\n"
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        for model in models[:3]:
            clean_name = re.sub(r'[^\w\s\-\.\(\)]', '', model).strip()[:60]
            query_encoded = urllib.parse.quote(clean_name)
            onliner_url = f"https://catalog.onliner.by/search?q={query_encoded}"
            if category == "electronics":
                shop1_url = f"https://5element.by/search?q={query_encoded}&digiSearch=true&term={query_encoded}&params=%7Csort%3DDEFAULT"
                shop1_name = "5element.by"
                shop2_url = f"https://www.21vek.by/search/?term={query_encoded}"
                shop2_name = "21vek.by"
            else:
                shop1_url = f"https://www.ozon.by/search/?text={query_encoded}&from_global=true"
                shop1_name = "Ozon.by"
                shop2_url = f"https://emall.by/search?query={query_encoded}"
                shop2_name = "emall.by"
            new_products.append({
                "name": model,
                "onliner": onliner_url,
                "shop1_url": shop1_url,
                "shop1_name": shop1_name,
                "shop2_url": shop2_url,
                "shop2_name": shop2_name
            })
            final_text += f"• **{model}**\n"
            final_text += f"   🔍 [Onliner]({onliner_url})  |  "
            final_text += f"🛍️ [{shop1_name}]({shop1_url})  |  "
            final_text += f"🏬 [{shop2_name}]({shop2_url})\n\n"

        current_len = len(products_cache.get(chat_id, []))
        add_products_to_cache(chat_id, new_products)
        for i, model in enumerate(models[:3]):
            idx = current_len + i
            keyboard.add(types.InlineKeyboardButton(f"➕ В избранное: {model[:35]}", callback_data=f"add_{chat_id}_{idx}"))
            keyboard.add(types.InlineKeyboardButton(f"📋 Рассказать про {model[:30]}", callback_data=f"tell_{chat_id}_{idx}"))

        bot.send_message(chat_id, final_text.strip(), parse_mode="Markdown",
                        reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        print(f"Ошибка more_options: {e}")
        bot.send_message(chat_id, "Не удалось получить другие варианты.", reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: True)
def handle_shopping_request(message):
    chat_id = message.chat.id
    user_text = message.text

    if user_text == "🔄 Начать подбор заново":
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        bot.send_message(chat_id, "🧹 История очищена. Какой товар ищем?", reply_markup=get_main_keyboard())
        return

    if user_text == "⭐️ Избранное":
        show_cart(message)
        return

    if not check_safety(user_text):
        bot.send_message(chat_id,
            "Извините, но я специализируюсь только на помощи с выбором товаров. "
            "Вы можете спрашивать меня про технику, гаджеты, одежду и другие покупки.",
            reply_markup=get_main_keyboard())
        return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    chat_histories[chat_id].append({"role": "user", "content": user_text})
    if len(chat_histories[chat_id]) > MAX_HISTORY_LEN:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-6:]

    bot.send_chat_action(chat_id, 'typing')
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=chat_histories[chat_id],
            temperature=0.4,
            max_tokens=800
        )
        bot_response = completion.choices[0].message.content.strip()
        chat_histories[chat_id].append({"role": "assistant", "content": bot_response})

        models = []
        category = "other"
        resume_match = re.search(r'Резюме:\s*\[?(.*?)\]?(?=\n|$)', bot_response, re.IGNORECASE | re.DOTALL)
        if resume_match:
            models = [m.strip() for m in resume_match.group(1).split(',') if m.strip()]
        cat_match = re.search(r'Категория:\s*(\w+)', bot_response, re.IGNORECASE)
        if cat_match:
            category = cat_match.group(1).lower()

        clean_text = re.sub(r'Резюме:\s*\[?.*?\]?', '', bot_response, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r'Категория:\s*\w+', '', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'^\s*[\w\s,\-\.]+,\s*[\w\s,\-\.]+,\s*[\w\s,\-\.]+\s*$', '', clean_text, flags=re.MULTILINE)
        clean_text = clean_text.strip()

        if not models:
            bot.send_message(chat_id, bot_response or "Не удалось подобрать варианты.", reply_markup=get_main_keyboard())
            return

        if len(clean_text) < 50 or not clean_text:
            intro = "Вот несколько моделей, которые подойдут под ваши требования:"
        else:
            intro = clean_text

        new_products = []
        final_text = intro + "\n\n"
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        for model in models[:3]:
            clean_name = re.sub(r'[^\w\s\-\.\(\)]', '', model).strip()[:60]
            query_encoded = urllib.parse.quote(clean_name)
            onliner_url = f"https://catalog.onliner.by/search?q={query_encoded}"
            if category == "electronics":
                shop1_url = f"https://5element.by/search?q={query_encoded}&digiSearch=true&term={query_encoded}&params=%7Csort%3DDEFAULT"
                shop1_name = "5element.by"
                shop2_url = f"https://www.21vek.by/search/?term={query_encoded}"
                shop2_name = "21vek.by"
            else:
                shop1_url = f"https://www.ozon.by/search/?text={query_encoded}&from_global=true"
                shop1_name = "Ozon.by"
                shop2_url = f"https://emall.by/search?query={query_encoded}"
                shop2_name = "emall.by"
            new_products.append({
                "name": model,
                "onliner": onliner_url,
                "shop1_url": shop1_url,
                "shop1_name": shop1_name,
                "shop2_url": shop2_url,
                "shop2_name": shop2_name
            })
            final_text += f"• **{model}**\n"
            final_text += f"   🔍 [Onliner]({onliner_url})  |  "
            final_text += f"🛍️ [{shop1_name}]({shop1_url})  |  "
            final_text += f"🏬 [{shop2_name}]({shop2_url})\n\n"

        current_len = len(products_cache.get(chat_id, []))
        add_products_to_cache(chat_id, new_products)
        for i, model in enumerate(models[:3]):
            idx = current_len + i
            keyboard.add(types.InlineKeyboardButton(f"➕ В избранное: {model[:35]}", callback_data=f"add_{chat_id}_{idx}"))
            keyboard.add(types.InlineKeyboardButton(f"📋 Рассказать про {model[:30]}", callback_data=f"tell_{chat_id}_{idx}"))

        bot.send_message(chat_id, final_text.strip(), parse_mode="Markdown",
                        reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        print(f"Ошибка выполнения: {e}")
        bot.send_message(chat_id, "⚠️ Возникли технические неполадки. Пожалуйста, повторите запрос.", reply_markup=get_main_keyboard())




if __name__ == "__main__":
    print("Бот запущен")
    bot.infinity_polling()