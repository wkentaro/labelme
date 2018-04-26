import os
import os.path as osp

import yaml

from labelme import logger


here = osp.dirname(osp.abspath(__file__))


def update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            logger.warn('Skipping unexpected key in config: {}'
                        .format(key))
            continue
        if isinstance(target_dict[key], dict) and \
                isinstance(value, dict):
            update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


# -----------------------------------------------------------------------------


def get_default_config():
    config_file = osp.join(here, 'default_config.yaml')
    with open(config_file) as f:
        config = yaml.load(f)
    return config


def validate_config_item(key, value):
    if key == 'validate_label' and value not in [None, 'exact', 'instance']:
        raise ValueError('Unexpected value `{}` for key `{}`'
                         .format(value, key))


def get_config(config_from_args=None, config_file=None):
    # default config
    config = get_default_config()

    if config_from_args is not None:
        update_dict(config, config_from_args,
                    validate_item=validate_config_item)

    save_config_file = False
    if config_file is None:
        home = os.path.expanduser('~')
        config_file = os.path.join(home, '.labelmerc')
        save_config_file = True

    if os.path.exists(config_file):
        with open(config_file) as f:
            user_config = yaml.load(f) or {}
        update_dict(config, user_config, validate_item=validate_config_item)

    if save_config_file:
        try:
            with open(config_file, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False)
        except Exception:
            logger.warn('Failed to save config: {}'.format(config_file))

    return config
