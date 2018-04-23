import os
import os.path as osp

import yaml

from labelme import logger


here = osp.dirname(osp.abspath(__file__))


def update_dict(target_dict, new_dict):
    for key, value in new_dict.items():
        if key not in target_dict:
            logger.warn('Skipping unexpected key in config: {}'
                        .format(key))
            continue
        if isinstance(target_dict[key], dict) and \
                isinstance(value, dict):
            update_dict(target_dict[key], value)
        else:
            target_dict[key] = value


def get_default_config():
    config_file = osp.join(here, 'default_config.yaml')
    config = yaml.load(open(config_file))
    return config


def get_config():
    # default config
    config = get_default_config()

    # shortcuts for actions
    home = os.path.expanduser('~')
    config_file = os.path.join(home, '.labelmerc')

    if os.path.exists(config_file):
        user_config = yaml.load(open(config_file)) or {}
        update_dict(config, user_config)

    # save config
    try:
        yaml.safe_dump(config, open(config_file, 'w'),
                       default_flow_style=False)
    except Exception:
        logger.warn('Failed to save config: {}'.format(config_file))

    return config
