import logging
import re
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup  # убедимся, что импорт корректен

from config import BOT_TOKEN, ADMIN_CHAT_ID
from database import (get_categories, get_products_by_category, get_product_by_id,
                      save_order, get_user_data, save_user_data, get_orders_by_user,
                      update_order_status, add_product, get_user_id_by_tg)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# Корзина: {user_id: {product_id: quantity}}
user_carts = {}
# Стек состояний для кнопки "Назад": {user_id: [("handler_name", data), ...]}
user_states = {}

class OrderForm(StatesGroup):
    # Явно указываем тип State для устранения предупреждений.
    waiting_for_name: State = State()
    waiting_for_phone: State = State()
    waiting_for_address: State = State()

    # Состояния для добавления товара админом
    admin_add_name: State = State()
    admin_add_desc: State = State()
    admin_add_price: State = State()
    admin_add_category: State = State()
    admin_add_photo: State = State()

def push_state(user_id, handler_name, data=None):
    if user_id not in user_states:
        user_states[user_id] = []
    user_states[user_id].append((handler_name, data))

def pop_state(user_id):
    if user_id in user_states and user_states[user_id]:
        user_states[user_id].pop()

def clear_state(user_id):
    user_states[user_id] = []

def main_menu_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Каталог товаров", callback_data="show_categories"))
    kb.add(InlineKeyboardButton("Корзина", callback_data="show_cart"))
    kb.add(InlineKeyboardButton("Оформить заказ", callback_data="checkout"))
    kb.add(InlineKeyboardButton("История заказов", callback_data="show_history"))
    return kb

async def safe_edit_text(message: types.Message, new_text: str, new_reply_markup=None):
    """
    Безопасная функция для обновления текста сообщения.
    Если текст не меняется, не вызываем edit_text(), чтобы избежать MessageNotModified.
    """
    current_text = message.text
    if current_text != new_text:
        await message.edit_text(new_text, reply_markup=new_reply_markup)
    else:
        # Если текст не изменился, можно просто обновить клавиатуру, если она отличается
        if new_reply_markup:
            await message.edit_reply_markup(new_reply_markup)

async def show_order_confirmation(origin, name, phone, address, is_message=False):
    if isinstance(origin, types.CallbackQuery):
        user_id = origin.from_user.id
    else:
        user_id = origin.from_user.id

    cart = user_carts.get(user_id, {})
    if not cart:
        if isinstance(origin, types.CallbackQuery):
            await safe_edit_text(origin.message, "Корзина пуста!")
        else:
            await origin.answer("Корзина пуста!")
        return

    total_sum = 0
    order_lines = []
    for pid, qty in cart.items():
        product = get_product_by_id(pid)
        if product:
            _, pname, pprice, pdesc, pimg, pcat = product
            sum_line = pprice * qty
            total_sum += sum_line
            order_lines.append(f"{pname} - {qty} шт. - {sum_line} руб.")

    text = "📦 Ваш заказ:\n"
    for l in order_lines:
        text += f"{l}\n"
    text += f"Общая сумма: {total_sum} руб.\n"
    text += f"Контакт: {name}, {phone}\nАдрес доставки: {address}\nПодтвердить заказ?"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Да", callback_data="confirm_order"))
    kb.add(InlineKeyboardButton("Редактировать", callback_data="edit_order"))
    kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))

    push_state(user_id, "checkout_handler")

    if is_message:
        await origin.answer(text, reply_markup=kb)
    else:
        await safe_edit_text(origin.message, text, kb)

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    clear_state(message.from_user.id)
    await message.answer("Привет! Добро пожаловать в наш магазин. Выберите, что вас интересует:", reply_markup=main_menu_keyboard())

@dp.message_handler(commands=['history'])
async def history_command(message: types.Message):
    orders = get_orders_by_user(message.from_user.id, limit=5)
    if not orders:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Перейти в каталог", callback_data="show_categories"))
        await message.answer("У вас пока нет заказов.", reply_markup=kb)
    else:
        text = "🛒 История заказов:\n"
        idx = 1
        for o in orders:
            order_date, order_details, total_price = o
            text += f"{idx}. {order_date}: {order_details}\nИтого: {total_price} руб.\n\n"
            idx += 1
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("В начало", callback_data="go_main"))
        await message.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "show_history")
async def show_history_handler(callback_query: types.CallbackQuery):
    orders = get_orders_by_user(callback_query.from_user.id, limit=5)
    if not orders:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Перейти в каталог", callback_data="show_categories"))
        await safe_edit_text(callback_query.message, "У вас пока нет заказов.", kb)
    else:
        text = "🛒 История заказов:\n"
        idx = 1
        for o in orders:
            order_date, order_details, total_price = o
            text += f"{idx}. {order_date}: {order_details}\nИтого: {total_price} руб.\n\n"
            idx += 1
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
        push_state(callback_query.from_user.id, "show_history_handler")
        await safe_edit_text(callback_query.message, text, kb)

@dp.callback_query_handler(lambda c: c.data == "go_main")
async def go_main_handler(callback_query: types.CallbackQuery):
    clear_state(callback_query.from_user.id)
    await safe_edit_text(callback_query.message, "Выберите, что вас интересует:", main_menu_keyboard())

@dp.callback_query_handler(lambda c: c.data == "go_back")
async def go_back_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if len(user_states.get(user_id, [])) > 1:
        pop_state(user_id)
        prev = user_states[user_id][-1]
        handler_name, data = prev
        if handler_name == "show_categories_handler":
            await show_categories_handler(callback_query)
        elif handler_name == "show_products_handler":
            category = data
            await show_products(callback_query, category)
        elif handler_name == "view_product_handler":
            product_id, category = data
            await view_product(callback_query, product_id, category)
        elif handler_name == "show_cart_handler":
            await show_cart(callback_query)
        elif handler_name == "checkout_handler":
            await safe_edit_text(callback_query.message, "Выберите, что вас интересует:", main_menu_keyboard())
        elif handler_name == "show_history_handler":
            await show_history_handler(callback_query)
        else:
            await go_main_handler(callback_query)
    else:
        await go_main_handler(callback_query)

@dp.callback_query_handler(lambda c: c.data == "show_categories")
async def show_categories_handler(callback_query: types.CallbackQuery):
    categories = get_categories()
    if not categories:
        await safe_edit_text(callback_query.message, "Каталог пуст.", main_menu_keyboard())
        return
    kb = InlineKeyboardMarkup()
    for cat in categories:
        kb.add(InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
    push_state(callback_query.from_user.id, "show_categories_handler")
    await safe_edit_text(callback_query.message, "Выберите категорию:", kb)

async def show_products(callback_query: types.CallbackQuery, category: str):
    products = get_products_by_category(category)
    if not products:
        await safe_edit_text(callback_query.message, "В этой категории пока нет товаров.", main_menu_keyboard())
        return

    text = f"Категория: {category}\n"
    kb = InlineKeyboardMarkup()
    for p in products:
        p_id, name, price, desc, img_url = p
        text += f"{p_id}. {name} - {price} руб.\n"
        kb.add(
            InlineKeyboardButton(f"Посмотреть {p_id}", callback_data=f"view_{p_id}_{category}"),
            InlineKeyboardButton(f"В корзину {p_id}", callback_data=f"add_{p_id}")
        )
    kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
    push_state(callback_query.from_user.id, "show_products_handler", category)
    await safe_edit_text(callback_query.message, text, kb)

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def category_selected(callback_query: types.CallbackQuery):
    category = callback_query.data.split("cat_")[1]
    await show_products(callback_query, category)

async def view_product(callback_query: types.CallbackQuery, product_id: int, category: str):
    product = get_product_by_id(product_id)
    if not product:
        await callback_query.answer("Товар не найден.")
        return
    p_id, name, price, desc, img_url, cat = product
    text = f"<b>{name}</b>\nЦена: {price} руб.\nОписание: {desc}"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Добавить в корзину", callback_data=f"add_{p_id}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
    push_state(callback_query.from_user.id, "view_product_handler", (p_id, cat))
    await safe_edit_text(callback_query.message, text, kb)

@dp.callback_query_handler(lambda c: c.data.startswith("view_"))
async def view_product_handler(callback_query: types.CallbackQuery):
    parts = callback_query.data.split("_")
    product_id = int(parts[1])
    category = parts[2]
    await view_product(callback_query, product_id, category)

@dp.callback_query_handler(lambda c: c.data.startswith("add_"))
async def add_to_cart_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    product_id = int(callback_query.data.split("add_")[1])
    if user_id not in user_carts:
        user_carts[user_id] = {}
    cart = user_carts[user_id]
    cart[product_id] = cart.get(product_id, 0) + 1
    await callback_query.answer("Товар добавлен в корзину!")

@dp.callback_query_handler(lambda c: c.data == "show_cart")
async def show_cart_handler(callback_query: types.CallbackQuery):
    await show_cart(callback_query)

async def show_cart(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    cart = user_carts.get(user_id, {})
    if not cart:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Перейти в каталог", callback_data="show_categories"))
        kb.add(InlineKeyboardButton("В начало", callback_data="go_main"))
        push_state(user_id, "show_cart_handler")
        await safe_edit_text(callback_query.message, "Ваша корзина пуста. Добавьте товары из каталога!", kb)
        return

    text = "🛒 Ваша корзина:\n"
    total_sum = 0
    kb = InlineKeyboardMarkup()
    index = 1
    for pid, qty in cart.items():
        product = get_product_by_id(pid)
        if product:
            p_id, name, price, desc, img_url, category = product
            sum_line = price * qty
            total_sum += sum_line
            text += f"{index}. {name} - {qty} шт. - {sum_line} руб.\n"
            kb.add(
                InlineKeyboardButton("+", callback_data=f"inc_{p_id}"),
                InlineKeyboardButton("-", callback_data=f"dec_{p_id}")
            )
            index += 1
    text += f"Общая сумма: {total_sum} руб."
    kb.add(InlineKeyboardButton("Оформить заказ", callback_data="checkout"))
    kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
    push_state(user_id, "show_cart_handler")
    await safe_edit_text(callback_query.message, text, kb)

@dp.callback_query_handler(lambda c: c.data.startswith("inc_"))
async def increase_quantity_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    product_id = int(callback_query.data.split("inc_")[1])
    cart = user_carts.get(user_id, {})
    if product_id in cart:
        cart[product_id] += 1
    await show_cart(callback_query)

@dp.callback_query_handler(lambda c: c.data.startswith("dec_"))
async def decrease_quantity_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    product_id = int(callback_query.data.split("dec_")[1])
    cart = user_carts.get(user_id, {})
    if product_id in cart:
        cart[product_id] -= 1
        if cart[product_id] <= 0:
            del cart[product_id]
    await show_cart(callback_query)

@dp.callback_query_handler(lambda c: c.data == "checkout")
async def checkout_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    cart = user_carts.get(user_id, {})
    if not cart:
        await callback_query.answer("Ваша корзина пуста!")
        return
    user_info = get_user_data(user_id)
    if user_info:
        _, name, phone, address = user_info
        text = f"Ваши данные:\nИмя: {name}\nТелефон: {phone}\nАдрес: {address}\nИспользовать эти данные?"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Да", callback_data="use_saved_data"))
        kb.add(InlineKeyboardButton("Редактировать", callback_data="edit_data"))
        kb.add(InlineKeyboardButton("Назад", callback_data="go_back"), InlineKeyboardButton("В начало", callback_data="go_main"))
        push_state(user_id, "checkout_handler")
        await safe_edit_text(callback_query.message, text, kb)
    else:
        push_state(user_id, "checkout_handler")
        await safe_edit_text(callback_query.message, "Пожалуйста, введите ваше имя:")
        await OrderForm.waiting_for_name.set()

@dp.callback_query_handler(lambda c: c.data == "use_saved_data", state="*")
async def use_saved_data_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    user = get_user_data(user_id)
    if user:
        _, name, phone, address = user
        await show_order_confirmation(callback_query, name, phone, address)
    else:
        await safe_edit_text(callback_query.message, "Данные не найдены, введите заново ваше имя:")
        await OrderForm.waiting_for_name.set()

@dp.callback_query_handler(lambda c: c.data == "edit_data", state="*")
async def edit_data_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await safe_edit_text(callback_query.message, "Пожалуйста, введите ваше имя:")
    await OrderForm.waiting_for_name.set()

@dp.message_handler(state=OrderForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите номер телефона в формате +7XXXXXXXXXX:")
    await OrderForm.waiting_for_phone.set()

@dp.message_handler(state=OrderForm.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not re.match(r"^\+7\d{10}$", phone):
        await message.answer("❌ Неверный формат. Введите номер телефона в формате +7XXXXXXXXXX:")
        return
    await state.update_data(phone=phone)
    await message.answer("Введите адрес доставки:")
    await OrderForm.waiting_for_address.set()

@dp.message_handler(state=OrderForm.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    phone = data['phone']
    address = message.text
    save_user_data(message.from_user.id, name, phone, address)
    await state.finish()
    await show_order_confirmation(message, name, phone, address, is_message=True)

@dp.callback_query_handler(lambda c: c.data == "edit_order")
async def edit_order_handler(callback_query: types.CallbackQuery):
    await show_cart(callback_query)

@dp.callback_query_handler(lambda c: c.data == "confirm_order")
async def confirm_order_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user_info = get_user_data(user_id)
    if not user_info:
        await safe_edit_text(callback_query.message, "Данные пользователя не найдены, перезапустите заказ.")
        return
    _, name, phone, address = user_info
    cart = user_carts.get(user_id, {})
    if not cart:
        await safe_edit_text(callback_query.message, "Корзина пуста!")
        return
    total_sum = 0
    order_lines = []
    for pid, qty in cart.items():
        product = get_product_by_id(pid)
        if product:
            _, pname, pprice, pdesc, pimg, pcat = product
            sum_line = pprice * qty
            total_sum += sum_line
            order_lines.append(f"{pname} - {qty} шт. - {sum_line} руб.")
    order_details = "\n".join(order_lines)
    user_db_id = get_user_id_by_tg(user_id)
    order_id = save_order(user_db_id, name, phone, address, order_details, total_sum)

    admin_text = f"Новый заказ (ID: {order_id}):\nИмя: {name}\nТелефон: {phone}\nАдрес: {address}\nТовары:\n{order_details}\nОбщая сумма: {total_sum} руб."
    admin_kb = InlineKeyboardMarkup()
    admin_kb.add(InlineKeyboardButton("Подтвердить", callback_data=f"admin_confirm_{order_id}"),
                 InlineKeyboardButton("Отклонить", callback_data=f"admin_decline_{order_id}"))
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text, reply_markup=admin_kb)

    user_carts[user_id] = {}
    clear_state(user_id)
    await safe_edit_text(callback_query.message, "Ваш заказ оформлен! Спасибо за покупку!", main_menu_keyboard())

@dp.callback_query_handler(lambda c: c.data.startswith("admin_confirm_"))
async def admin_confirm_order(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        await callback_query.answer("Нет прав", show_alert=True)
        return
    order_id = int(callback_query.data.split("admin_confirm_")[1])
    update_order_status(order_id, "Принят")
    await safe_edit_text(callback_query.message, "Заказ подтверждён!")

@dp.callback_query_handler(lambda c: c.data.startswith("admin_decline_"))
async def admin_decline_order(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        await callback_query.answer("Нет прав", show_alert=True)
        return
    order_id = int(callback_query.data.split("admin_decline_")[1])
    update_order_status(order_id, "Отклонён")
    await safe_edit_text(callback_query.message, "Заказ отклонён.")

@dp.message_handler(commands=['add_product'])
async def add_product_command(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("У вас нет прав на добавление товаров.")
        return
    await message.answer("Введите название товара:")
    await OrderForm.admin_add_name.set()

@dp.message_handler(state=OrderForm.admin_add_name)
async def admin_add_name_handler(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите описание товара:")
    await OrderForm.admin_add_desc.set()

@dp.message_handler(state=OrderForm.admin_add_desc)
async def admin_add_desc_handler(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите цену товара (число):")
    await OrderForm.admin_add_price.set()

@dp.message_handler(lambda msg: not msg.text.isdigit(), state=OrderForm.admin_add_price)
async def admin_add_price_error(message: types.Message, state: FSMContext):
    await message.answer("Цена должна быть числом, попробуйте ещё раз:")

@dp.message_handler(lambda msg: msg.text.isdigit(), state=OrderForm.admin_add_price)
async def admin_add_price_handler(message: types.Message, state: FSMContext):
    await state.update_data(price=int(message.text))
    await message.answer("Введите категорию товара:")
    await OrderForm.admin_add_category.set()

@dp.message_handler(state=OrderForm.admin_add_category)
async def admin_add_category_handler(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Отправьте фото товара или напишите 'нет', если без фото:")
    await OrderForm.admin_add_photo.set()

@dp.message_handler(state=OrderForm.admin_add_photo, content_types=['photo', 'text'])
async def admin_add_photo_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    desc = data['description']
    price = data['price']
    category = data['category']
    image_url = None
    if message.photo:
        image_url = message.photo[-1].file_id
    elif message.text.lower() == 'нет':
        image_url = None

    add_product(name, price, desc, category, image_url)
    await message.answer("Товар успешно добавлен!")
    await state.finish()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
