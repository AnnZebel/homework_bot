import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ParseStatusError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot, message):
    """Отправка сообщений в Telegram чат."""
    try:
        bot.send_message(chat_id=os.environ['TELEGRAM_CHAT_ID'], text=message)
        logger.debug('Сообщение успешно отправлено в Telegram')
    except telegram.error.TelegramError as e:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {e}')


def get_api_answer(timestamp):
    """Отправка запроса к эндпоинту API-сервиса."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            raise (requests.exceptions.
                   HTTPError(f'Ошибка при запросе к API. Код ответа: '
                             f'{response.status_code}'))
        response = response.json()
        if isinstance(response, dict):
            return response
        else:
            raise TypeError('Ответ API не является словарем.')
    except requests.exceptions.RequestException as e:
        raise TypeError(f'Ошибка при запросе к API: {e}')


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ от эндпоинта пришел не в формате словаря')
    if 'homeworks' not in response:
        raise KeyError('Данных homeworks нет в ответе эндпоинта')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Данные homeworks получены не в виде списка')
    return homeworks


def parse_status(homework):
    """Извлечение статуса."""
    homework_name = homework.get('homework_name')
    status = homework.get('status')

    if homework_name is None:
        raise KeyError('Отсутствует ключ "homework_name"!')
    if status is None:
        logger.debug('Статус домашних работ не изменился.')

    verdict = HOMEWORK_VERDICTS.get(status)
    if homework_name and verdict:
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    raise ParseStatusError(
        f'Неизвестный статус домашней работы {status}.')


def check_tokens():
    """Проверка доступности переменных окружения."""
    for token in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        if token is None:
            logger.critical(
                'Отсутствует обязательная переменная окружения: '
                f'"{token}"!')
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(0)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            if response and check_response(response):
                homework = response.get('homeworks', [])
                if homework:
                    message = parse_status(homework[0])
                    if message:
                        send_message(bot, message)
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
