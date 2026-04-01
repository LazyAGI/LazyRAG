from lazyllm import AutoModel


def get_model(model_name, cfg):
    m = AutoModel(model=model_name, config=cfg)
    return m
