import logging
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from telegram.ext import Updater

from config import PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from exceptions import ParseStatusError, ApiAnswerError

load_dotenv()


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
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено в Telegram')
    except telegram.error.TelegramError as e:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {e}')


def get_api_answer(timestamp):
    """Отправка запроса к эндпоинту API-сервиса."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            raise ApiAnswerError(f'Ошибка при запросе к API. Код ответа: '
                                 f'{response.status_code}')
        response = response.json()
        return response
    except requests.exceptions.RequestException as e:
        raise ApiAnswerError(f'Ошибка при запросе к API: {e}')


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ от эндпоинта пришел не в формате словаря')
    if 'homeworks' not in response:
        raise KeyError('Данных homeworks нет в ответе эндпоинта')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Данные homeworks получены не в виде списка')


def parse_status(homework):
    """Извлечение статуса."""
    if homework is None:
        logger.debug('Отсутствует ответ от API.')
        return
    homework_name = homework.get('homework_name')
    status = homework.get('status')

    if homework_name is None:
        raise KeyError('Отсутствует ключ "homework_name"!')
    if status is None:
        raise ParseStatusError('Статус домашних работ не изменился.')

    verdict = HOMEWORK_VERDICTS.get(status)
    if homework_name and verdict:
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    raise ParseStatusError(
        f'Неизвестный статус домашней работы {status}.')


def check_tokens():
    """Проверка доступности переменных окружения."""
    TOKENS_CHAT_FOR_TELEGRAM = PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    for token in TOKENS_CHAT_FOR_TELEGRAM:
        if token is None:
            logger.critical(
                'Отсутствует обязательная переменная окружения: '
                f'"{token}"!')
    return all(TOKENS_CHAT_FOR_TELEGRAM)


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(0)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    message_error = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_timestamp')
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Статус домашней работы не изменился')
            if response:
                homework = response.get('homeworks', [])
                if homework:
                    message = parse_status(homework[0])
                    if message:
                        send_message(bot, message)
            else:
                logger.debug('Отсутствует ответ от API.')
        except KeyboardInterrupt:
            print('Остановка программы пользователем...')
            break
        except Exception as error:
            logging.error(error)
            if error != message_error:
                logging.error(f'Сбой в работе программы: {error}')
                send_message(bot, message)
                message_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
