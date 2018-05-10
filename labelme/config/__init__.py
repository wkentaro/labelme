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
    # Configuration load order:
    #
    #   1. default config (lowest priority)
    #   2. config file passed by command line argument or ~/.labelmerc
    #   3. command line argument (highest priority)

    # 1. default config
    config = get_default_config()

    # save default config to ~/.labelmerc
    home = osp.expanduser('~')
    default_config_file = osp.join(home, '.labelmerc')
    if not osp.exists(default_config_file):
        try:
            with open(default_config_file, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False)
        except Exception:
            logger.warn('Failed to save config: {}'
                        .format(default_config_file))

    # 2. config from yaml file
    if config_file is None:
        config_file = default_config_file
    if osp.exists(config_file):
        with open(config_file) as f:
            user_config = yaml.load(f) or {}
        update_dict(config, user_config, validate_item=validate_config_item)

    # 3. command line argument
    if config_from_args is not None:
        update_dict(config, config_from_args,
                    validate_item=validate_config_item)

    return config
