from importlib import metadata


installed_packages = None


def get_installed_packages(guess_list: list = None):
    """Установленные пакеты
       https://docs.python.org/3/library/importlib.metadata.html
       :param guess_list: список приложений, которые хотим проверить
    """
    global installed_packages
    if not installed_packages:
        installed_packages = [{
            'name': item.metadata['Name'],
            'name2': item.metadata['Name'].replace('-', '_'), # в именах нет _, заменяется на -
            'version': item.version,
            'description': item.metadata['Description'],
            'summary': item.metadata['Summary'],
            'distr': item,
        } for item in metadata.distributions()]

    result = installed_packages
    if guess_list:
        result = [item for item in result if (item['name'] in guess_list or item['name2'] in guess_list)]
    return result