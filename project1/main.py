import telebot
import json
import os
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class BaseHandler:
    """Базовый класс для управления состоянием пользователя и общими функциями."""
    def __init__(self, bot):
        self.bot = bot
        self.users = {}
        self.data_file = "user_data.json"
        self.load_user_data()

    def load_user_data(self):
        """Загрузка данных пользователей из файла."""
        if os.path.exists(self.data_file):
            with open(self.data_file, "r") as file:
                self.users = json.load(file)
            logger.info("Данные пользователей загружены из файла.")
        else:
            logger.info("Файл с данными пользователей не найден, будет создан новый.")

    def save_user_data(self):
        """Сохранение данных пользователей в файл."""
        with open(self.data_file, "w") as file:
            json.dump(self.users, file, indent=4)
        logger.info("Данные пользователей сохранены в файл.")

    def get_user_state(self, chat_id):
        """Получить текущее состояние пользователя."""
        return self.users.get(str(chat_id), {}).get("state")

    def set_user_state(self, chat_id, state):
        """Установить новое состояние пользователя."""
        chat_id = str(chat_id)
        if chat_id not in self.users:
            self.users[chat_id] = {"expenses": [], "daily_limit": 0, "state": None}
        self.users[chat_id]["state"] = state
        self.save_user_data()


class FinanceBot(BaseHandler):
    """Класс финансового бота, унаследованный от BaseHandler."""
    def __init__(self, token):
        self.bot = telebot.TeleBot(token)
        super().__init__(self.bot)

    def start(self):
        """Запуск бота с настройкой обработчиков."""
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            chat_id = str(message.chat.id)
            self.set_user_state(chat_id, None)
            self.bot.send_message(
                message.chat.id,
                "Добро пожаловать в финансовый бот!\nВыберите действие с помощью кнопок ниже.",
                reply_markup=self.main_menu()
            )
            logger.info(f"Пользователь {chat_id} начал разговор.")

        @self.bot.message_handler(func=lambda message: message.text == "Добавить расход")
        def add_expense(message):
            chat_id = str(message.chat.id)
            self.set_user_state(chat_id, "add_expense")
            msg = self.bot.send_message(message.chat.id, "Введите расход в формате: категория, сумма")
            self.bot.register_next_step_handler(msg, self.process_expense)
            logger.info(f"Пользователь {chat_id} выбрал добавить расход.")

        @self.bot.message_handler(func=lambda message: message.text == "Установить бюджет на день")
        def set_daily_limit(message):
            chat_id = str(message.chat.id)
            self.set_user_state(chat_id, "set_daily_limit")
            msg = self.bot.send_message(message.chat.id, "Введите дневной бюджет (сумма):")
            self.bot.register_next_step_handler(msg, self.process_daily_limit)
            logger.info(f"Пользователь {chat_id} выбрал установить дневной бюджет.")

        @self.bot.message_handler(func=lambda message: message.text == "Просмотр расходов")
        def view_expenses(message):
            chat_id = str(message.chat.id)
            self.set_user_state(chat_id, None)

            expenses = self.users[chat_id]["expenses"]
            if not expenses:
                self.bot.send_message(message.chat.id, "У вас пока нет добавленных расходов.")
            else:
                report = "\n".join(
                    [f"{idx + 1}. {item['category']} ({item['date']}): {item['amount']} руб."
                     for idx, item in enumerate(expenses)]
                )
                self.bot.send_message(message.chat.id, f"Ваши расходы:\n{report}")
            logger.info(f"Пользователь {chat_id} запросил просмотр расходов.")

        @self.bot.message_handler(func=lambda message: message.text == "Удалить расход")
        def delete_expense(message):
            chat_id = str(message.chat.id)
            self.set_user_state(chat_id, "delete_expense")

            expenses = self.users[chat_id]["expenses"]
            if not expenses:
                self.bot.send_message(message.chat.id, "У вас нет расходов для удаления.")
            else:
                report = "\n".join(
                    [f"{idx + 1}. {item['category']}: {item['amount']} руб." for idx, item in enumerate(expenses)]
                )
                msg = self.bot.send_message(
                    message.chat.id,
                    f"Ваши расходы:\n{report}\nВведите номер расхода для удаления:"
                )
                self.bot.register_next_step_handler(msg, self.process_delete_expense)

            logger.info(f"Пользователь {chat_id} выбрал удалить расход.")

        self.bot.polling(none_stop=True)

    def main_menu(self):
        """Создает кнопки для главного меню."""
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("Добавить расход", "Просмотр расходов")
        keyboard.row("Установить бюджет на день", "Удалить расход")
        return keyboard

    def process_expense(self, message):
        """Обрабатывает добавление нового расхода."""
        chat_id = str(message.chat.id)
        try:
            category, amount = message.text.split(",")
            category = category.strip()
            amount = float(amount.strip())
            date = datetime.now().strftime("%Y-%m-%d")
            self.users[chat_id]["expenses"].append({"category": category, "amount": amount, "date": date})
            self.save_user_data()

            # Проверка дневного лимита
            self.check_daily_limit(chat_id)

            self.bot.send_message(message.chat.id, "Расход добавлен!", reply_markup=self.main_menu())
            self.set_user_state(chat_id, None)
            logger.info(f"Пользователь {chat_id} добавил расход: {category}, {amount} руб.")
        except ValueError:
            self.bot.send_message(message.chat.id, "Ошибка! Убедитесь, что вводите данные в формате: категория, сумма.")

    def process_daily_limit(self, message):
        """Обрабатывает установку дневного бюджета."""
        chat_id = str(message.chat.id)
        try:
            self.users[chat_id]["daily_limit"] = float(message.text.strip())
            self.save_user_data()
            self.bot.send_message(
                message.chat.id,
                f"Дневной бюджет установлен: {self.users[chat_id]['daily_limit']} руб.",
                reply_markup=self.main_menu()
            )
            self.set_user_state(chat_id, None)
            logger.info(f"Пользователь {chat_id} установил дневной бюджет: {self.users[chat_id]['daily_limit']} руб.")
        except ValueError:
            self.bot.send_message(message.chat.id, "Ошибка! Введите сумму дневного бюджета числом.")

    def process_delete_expense(self, message):
        """Обрабатывает удаление указанного расхода."""
        chat_id = str(message.chat.id)
        try:
            index = int(message.text.strip()) - 1
            expenses = self.users[chat_id]["expenses"]
            if 0 <= index < len(expenses):
                deleted = expenses.pop(index)
                self.save_user_data()
                self.bot.send_message(
                    message.chat.id,
                    f"Расход {deleted['category']}: {deleted['amount']} руб. удален.",
                    reply_markup=self.main_menu()
                )
                self.set_user_state(chat_id, None)
                logger.info(f"Пользователь {chat_id} удалил расход: {deleted['category']}, {deleted['amount']} руб.")
            else:
                self.bot.send_message(message.chat.id, "Ошибка! Неверный номер расхода.")
        except ValueError:
            self.bot.send_message(message.chat.id, "Ошибка! Введите номер расхода числом.")

    def check_daily_limit(self, chat_id):
        """Проверяет превышение дневного лимита расходов."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_expenses = sum(item["amount"] for item in self.users[chat_id]["expenses"] if item["date"] == today)
        daily_limit = self.users[chat_id].get("daily_limit", 0)

        if daily_limit > 0 and daily_expenses > daily_limit:
            self.bot.send_message(
                chat_id,
                f"Внимание! Вы превысили дневной бюджет: {daily_limit} руб.\nВаши расходы за сегодня: {daily_expenses} руб."
            )
            logger.warning(f"Пользователь {chat_id} превысил дневной бюджет: {daily_expenses} руб. из {daily_limit} руб.")


# Запуск бота
if __name__ == "__main__":
    TOKEN = "8131163460:AAF9rJQzxnBFCAwrWVF4RXHUaU23J6a5TjQ"
    bot = FinanceBot(TOKEN)
    bot.start()

