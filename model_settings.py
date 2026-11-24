import os


def model_settings(alternate=None):
    vision = tuple(os.getenv('TABLE_VISION_' + key, '') for key in ('BASE_URL', 'MODEL', 'API_KEY'))
    if alternate is True or (alternate is None and all(vision)):
        if not all(vision):
            raise ValueError('公司备用模型配置不完整')
        return vision
    return tuple(os.getenv(key, '') for key in ('DEEPSEEK_BASE_URL', 'DSH_MODEL', 'DEEPSEEK_API_KEY'))
