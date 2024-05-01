import json

_config_path = 'config.json'

def read_config():
    with open(_config_path, 'r') as f:
        content = f.read()
        return json.loads(content)

def write_config(config_dict):
    with open(_config_path, 'w') as wf:
        wf.write(json.dumps(config_dict, indent=4))
        
def get_all_config_safe():
    config = read_config()
    del config['password']
    del config['secret_key']
    return config

def put_config_by_key(key, value):
    config = read_config()
    config[key] = value
    print(config)
    write_config(config_dict=config)
    
def get_config_by_key(key, default_value=None):
    config = read_config()
    if key in config:
        return config[key]
    else:
        return default_value