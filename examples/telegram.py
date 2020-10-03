import requests


def send_message(message):

    '''
    Send as message using the PycharmScript chatbot
    :param message: The message as string
    '''
    # Set up telegram
    # Telegram message
    token = '1339945420:AAFMqMDX9C5i9Mf6eSIPZfyE4Qd5xC9jOtQ'
    method = 'sendMessage'

    requests.post(url='https://api.telegram.org/bot{0}/{1}'.format(token, method),
                             data={'chat_id': 72485920, 'text': message}).json()
