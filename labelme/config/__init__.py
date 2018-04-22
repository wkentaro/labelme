import os.path as osp

import yaml


here = osp.dirname(osp.abspath(__file__))
config_file = osp.join(here, 'default_config.yaml')
default_config = yaml.load(open(config_file))
del here, config_file
